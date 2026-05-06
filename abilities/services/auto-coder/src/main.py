from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer

app = typer.Typer(help="Cron-friendly autonomous coding service for Hermes.", no_args_is_help=True)

STATUS_TO_DO = "Todo"
STATUS_IN_PROGRESS = "In Progress"
STATUS_DONE = "Done"
STATUS_BLOCKED = "Blocked"

ROOT = Path(__file__).resolve().parents[4]
NOTION_BIN = ROOT / "bin" / "notion"
AUTO_CODER_BIN = ROOT / "bin" / "auto-coder"


@dataclass(frozen=True)
class Config:
    notion_database_id: str
    apps_root: Path
    status_property: str
    project_property: str
    error_log_property: str
    codex_model: str
    git_completion_mode: str


@dataclass(frozen=True)
class PropertyBinding:
    name: str
    property_id: str
    property_type: str
    options_by_name: dict[str, str]


@dataclass(frozen=True)
class SchemaBindings:
    status: PropertyBinding
    project: PropertyBinding
    error_log: PropertyBinding


@dataclass(frozen=True)
class TaskSections:
    task: str
    acceptance_criteria: str
    verification: str
    full_body: str


class AutoCoderError(Exception):
    def __init__(self, failure_code: str, message: str) -> None:
        super().__init__(message)
        self.failure_code = failure_code
        self.message = message


class CommandError(RuntimeError):
    def __init__(self, command: list[str], returncode: int, stdout: str, stderr: str) -> None:
        super().__init__(stderr or stdout or f"Command failed with exit code {returncode}")
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def summarize_command_output(text: str, limit: int = 1200) -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit]}...[truncated]"


def format_command_error(exc: CommandError) -> str:
    command = " ".join(exc.command)
    stderr = summarize_command_output(exc.stderr)
    stdout = summarize_command_output(exc.stdout)
    details: list[str] = [f"Command failed (exit {exc.returncode}): {command}"]
    if stderr:
        details.append(f"stderr: {stderr}")
    if stdout:
        details.append(f"stdout: {stdout}")
    return "\n".join(details)


def emit(event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    typer.echo(json.dumps(payload, sort_keys=True))


def emit_error(event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    typer.echo(json.dumps(payload, sort_keys=True), err=True)


def expand_path(value: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(value))).resolve()


def load_config() -> Config:
    return Config(
        notion_database_id=os.getenv("NOTION_TASK_DATABASE_ID", "").strip(),
        apps_root=expand_path(os.getenv("APPS_ROOT", "~/apps")),
        status_property=os.getenv("AUTO_CODER_STATUS_PROPERTY", "Status").strip() or "Status",
        project_property=os.getenv("AUTO_CODER_PROJECT_PROPERTY", "Project").strip() or "Project",
        error_log_property=os.getenv("AUTO_CODER_ERROR_LOG_PROPERTY", "Error Log").strip() or "Error Log",
        codex_model=os.getenv("AUTO_CODER_CODEX_MODEL", "gpt-5.3-codex").strip()
        or "gpt-5.3-codex",
        git_completion_mode=os.getenv(
            "AUTO_CODER_GIT_COMPLETION_MODE", "auto_merge_main"
        ).strip()
        or "auto_merge_main",
    )


def run_command(
    command: list[str],
    cwd: Path | None = None,
    input_text: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise CommandError(command, result.returncode, result.stdout, result.stderr)
    return result


def run_json_command(command: list[str], cwd: Path | None = None) -> dict[str, Any]:
    # print command for debugging, but don't log the full output since it may contain sensitive information.
    emit("debug_run_command", command=command, cwd=str(cwd) if cwd else None)
    try:
        result = run_command(command, cwd=cwd)
    except CommandError as exc:
        raise AutoCoderError("notion_update_failure", format_command_error(exc)) from exc
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AutoCoderError("notion_update_failure", f"Invalid JSON from command: {command}") from exc
    if not isinstance(payload, dict):
        raise AutoCoderError("notion_update_failure", f"Unexpected JSON payload from command: {command}")
    if payload.get("ok") is False:
        error = payload.get("error", {})
        message = error.get("message") if isinstance(error, dict) else None
        raise AutoCoderError("notion_update_failure", str(message or "Notion command failed"))
    return payload


def notion_command(*args: str) -> list[str]:
    return [str(NOTION_BIN), *args, "--json"]


def discover_schema(properties_payload: dict[str, Any], config: Config) -> SchemaBindings:
    data = properties_payload.get("data", {})
    properties = data.get("editable_properties", []) if isinstance(data, dict) else []
    if not isinstance(properties, list):
        raise AutoCoderError("insufficient_spec", "Notion database properties are not readable")

    by_name = {item.get("name"): item for item in properties if isinstance(item, dict)}
    status = bind_property(by_name, config.status_property, [STATUS_TO_DO, STATUS_IN_PROGRESS, STATUS_DONE, STATUS_BLOCKED])
    project = bind_property(by_name, config.project_property, [])
    error_log = bind_text_property(by_name, config.error_log_property)
    return SchemaBindings(status=status, project=project, error_log=error_log)


def bind_property(
    properties_by_name: dict[Any, dict[str, Any]],
    name: str,
    required_options: list[str],
) -> PropertyBinding:
    prop = properties_by_name.get(name)
    if not isinstance(prop, dict):
        raise AutoCoderError("insufficient_spec", f"Missing Notion property: {name}")
    property_id = prop.get("property_id")
    property_type = prop.get("type")
    if not isinstance(property_id, str) or not isinstance(property_type, str):
        raise AutoCoderError("insufficient_spec", f"Invalid Notion property metadata: {name}")

    options: dict[str, str] = {}
    raw_options = prop.get("options", [])
    if isinstance(raw_options, list):
        for option in raw_options:
            if not isinstance(option, dict):
                continue
            option_name = option.get("name")
            option_id = option.get("id")
            if isinstance(option_name, str) and isinstance(option_id, str):
                options[option_name] = option_id

    missing = [option for option in required_options if option not in options]
    if missing:
        raise AutoCoderError(
            "insufficient_spec",
            f"Property {name} is missing option(s): {', '.join(missing)}",
        )

    return PropertyBinding(
        name=name,
        property_id=property_id,
        property_type=property_type,
        options_by_name=options,
    )


def bind_text_property(
    properties_by_name: dict[Any, dict[str, Any]],
    name: str,
) -> PropertyBinding:
    prop = properties_by_name.get(name)
    if not isinstance(prop, dict):
        raise AutoCoderError("insufficient_spec", f"Missing Notion property: {name}")
    property_id = prop.get("property_id")
    property_type = prop.get("type")
    if not isinstance(property_id, str) or not isinstance(property_type, str):
        raise AutoCoderError("insufficient_spec", f"Invalid Notion property metadata: {name}")
    if property_type not in {"rich_text", "text"}:
        raise AutoCoderError(
            "insufficient_spec",
            f"Property {name} must be a text property (rich_text/text), got: {property_type}",
        )
    return PropertyBinding(
        name=name,
        property_id=property_id,
        property_type=property_type,
        options_by_name={},
    )


def update_option_property(page_id: str, binding: PropertyBinding, option_id: str) -> None:
    run_json_command(
        notion_command(
            "update-page-property",
            "--page-id",
            page_id,
            "--property-id",
            binding.property_id,
            "--property-type",
            binding.property_type,
            "--value-id",
            option_id,
        )
    )


def update_text_property(page_id: str, binding: PropertyBinding, text_value: str) -> None:
    run_json_command(
        notion_command(
            "update-page-property",
            "--page-id",
            page_id,
            "--property-id",
            binding.property_id,
            "--property-type",
            binding.property_type,
            "--text",
            text_value,
        )
    )


def set_status(page_id: str, bindings: SchemaBindings, status: str) -> None:
    update_option_property(page_id, bindings.status, bindings.status.options_by_name[status])


def set_error_log(page_id: str, bindings: SchemaBindings, value: str) -> None:
    update_text_property(page_id, bindings.error_log, value)


def block_task(page_id: str, bindings: SchemaBindings, failure_code: str, message: str) -> None:
    set_status(page_id, bindings, STATUS_BLOCKED)
    set_error_log(page_id, bindings, f"{failure_code}: {message}")


def get_property_value(page: dict[str, Any], binding: PropertyBinding) -> str:
    properties = page.get("properties", {})
    if not isinstance(properties, dict):
        return ""
    prop = properties.get(binding.name)
    if not isinstance(prop, dict):
        for candidate in properties.values():
            if isinstance(candidate, dict) and candidate.get("id") == binding.property_id:
                prop = candidate
                break
    if not isinstance(prop, dict):
        return ""

    prop_type = prop.get("type")
    value = prop.get(prop_type) if isinstance(prop_type, str) else None
    if isinstance(value, dict):
        if prop_type in {"status", "select"}:
            name = value.get("name")
            return name if isinstance(name, str) else ""
        if prop_type == "title":
            return rich_text_plain_text(value.get("title"))
        if prop_type in {"rich_text", "text"}:
            return rich_text_plain_text(value.get("rich_text"))
    if isinstance(value, list):
        if prop_type == "multi_select":
            return ", ".join(item.get("name", "") for item in value if isinstance(item, dict))
        return rich_text_plain_text(value)
    if isinstance(value, str):
        return value
    return ""


def extract_page_title(page: dict[str, Any]) -> str:
    properties = page.get("properties", {})
    if not isinstance(properties, dict):
        return "untitled"
    for prop in properties.values():
        if isinstance(prop, dict) and prop.get("type") == "title":
            title = prop.get("title", [])
            text = rich_text_plain_text(title)
            return text or "untitled"
    return "untitled"


def select_todo_page(pages_payload: dict[str, Any], bindings: SchemaBindings) -> dict[str, Any] | None:
    data = pages_payload.get("data", {})
    results = data.get("results", []) if isinstance(data, dict) else []
    if not isinstance(results, list):
        raise AutoCoderError("insufficient_spec", "Notion page list is not readable")
    for page in results:
        if isinstance(page, dict) and get_property_value(page, bindings.status) == STATUS_TO_DO:
            return page
    return None


def rich_text_plain_text(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    parts: list[str] = []
    for item in value:
        if isinstance(item, dict) and isinstance(item.get("plain_text"), str):
            parts.append(item["plain_text"])
    return "".join(parts)


def render_block(block: dict[str, Any]) -> str:
    block_type = block.get("type")
    if not isinstance(block_type, str):
        return ""
    content = block.get(block_type, {})
    if not isinstance(content, dict):
        return ""
    if block_type in {
        "paragraph",
        "heading_1",
        "heading_2",
        "heading_3",
        "bulleted_list_item",
        "numbered_list_item",
        "to_do",
        "quote",
        "toggle",
        "callout",
        "code",
    }:
        return rich_text_plain_text(content.get("rich_text"))
    return ""


def flatten_blocks(blocks: list[dict[str, Any]]) -> list[tuple[str, str]]:
    flattened: list[tuple[str, str]] = []
    for block in blocks:
        block_type = block.get("type")
        text = render_block(block)
        if isinstance(block_type, str):
            flattened.append((block_type, text))
        children = block.get("children")
        if isinstance(children, list):
            flattened.extend(flatten_blocks([child for child in children if isinstance(child, dict)]))
    return flattened


def extract_task_sections(page_content_payload: dict[str, Any]) -> TaskSections:
    data = page_content_payload.get("data", {})
    blocks = data.get("blocks", []) if isinstance(data, dict) else []
    if not isinstance(blocks, list):
        raise AutoCoderError("insufficient_spec", "Page content blocks are not readable")

    current: str | None = None
    sections: dict[str, list[str]] = {
        "Task": [],
        "Acceptance Criteria": [],
        "Verification": [],
    }
    body_lines: list[str] = []
    heading_names = set(sections)

    for block_type, text in flatten_blocks([block for block in blocks if isinstance(block, dict)]):
        clean_text = text.strip()
        if block_type in {"heading_1", "heading_2", "heading_3"} and clean_text in heading_names:
            current = clean_text
            body_lines.append(f"# {clean_text}")
            continue
        if clean_text:
            body_lines.append(clean_text)
            if current:
                sections[current].append(clean_text)

    missing = [name for name, lines in sections.items() if not "\n".join(lines).strip()]
    if missing:
        raise AutoCoderError(
            "insufficient_spec",
            f"Missing required page section content: {', '.join(missing)}",
        )

    return TaskSections(
        task="\n".join(sections["Task"]).strip(),
        acceptance_criteria="\n".join(sections["Acceptance Criteria"]).strip(),
        verification="\n".join(sections["Verification"]).strip(),
        full_body="\n".join(body_lines).strip(),
    )


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug[:48] or "task"


def resolve_repo(apps_root: Path, project: str) -> Path:
    if not project.strip():
        raise AutoCoderError("unknown_project", "Project value is empty")
    raw = Path(project)
    if raw.is_absolute() or ".." in raw.parts:
        raise AutoCoderError("unknown_project", f"Unsafe project value: {project}")
    repo = (apps_root / raw).resolve()
    try:
        repo.relative_to(apps_root.resolve())
    except ValueError as exc:
        raise AutoCoderError("unknown_project", f"Project escapes APPS_ROOT: {project}") from exc
    return repo


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run_command(["git", *args], cwd=repo, check=check)


def validate_repo(repo: Path) -> None:
    if not repo.exists() or not repo.is_dir():
        raise AutoCoderError("missing_repo", f"Repository does not exist: {repo}")
    if git(repo, "rev-parse", "--is-inside-work-tree", check=False).returncode != 0:
        raise AutoCoderError("missing_repo", f"Not a git repository: {repo}")
    if git(repo, "show-ref", "--verify", "--quiet", "refs/heads/main", check=False).returncode != 0:
        raise AutoCoderError("missing_repo", "Repository has no local main branch")
    status = git(repo, "status", "--porcelain").stdout.strip()
    if status:
        raise AutoCoderError("missing_repo", "Repository worktree is not clean")
    conflicts = git(repo, "diff", "--name-only", "--diff-filter=U").stdout.strip()
    if conflicts:
        raise AutoCoderError("missing_repo", "Repository has unresolved merge conflicts")


def build_codex_prompt(
    repo: Path,
    task_id: str,
    title: str,
    sections: TaskSections,
) -> str:
    return f"""You are Codex working inside a target repository for Hermes auto-coder.

Target repository: {repo}
Notion task ID: {task_id}
Task title: {title}

Rules:
- Inspect the repository before editing.
- Implement the task end-to-end.
- Stay inside the target repository.
- Run the verification described below and report exact results.
- Incomplete or unverified work counts as failure.
- Do not merge, push, or update Notion; the orchestration service owns git completion and Notion updates.

Task:
{sections.task}

Acceptance Criteria:
{sections.acceptance_criteria}

Verification:
{sections.verification}

Full Notion body:
{sections.full_body}
"""


def build_codex_command(repo: Path, model: str) -> list[str]:
    return [
        "codex",
        "exec",
        "-C",
        str(repo),
        "--model",
        model,
        "--ask-for-approval",
        "never",
        "--sandbox",
        "workspace-write",
    ]


def codex_report_is_usable(stdout: str, stderr: str) -> bool:
    combined = f"{stdout}\n{stderr}".lower()
    if not combined.strip():
        return False
    if "verification" not in combined and "test" not in combined and "check" not in combined:
        return False
    failure_markers = [
        "verification failed",
        "tests failed",
        "test failed",
        "failed verification",
    ]
    if any(marker in combined for marker in failure_markers):
        raise AutoCoderError("test_failure", "Codex reported verification failure")
    return True


def run_codex(repo: Path, config: Config, prompt: str) -> None:
    result = run_command(build_codex_command(repo, config.codex_model), cwd=repo, input_text=prompt, check=False)
    if result.returncode != 0:
        raise AutoCoderError("codex_failure", result.stderr or result.stdout or "Codex failed")
    if not codex_report_is_usable(result.stdout, result.stderr):
        raise AutoCoderError("codex_failure", "Codex output did not include usable verification evidence")


def prepare_git_branch(repo: Path, task_id: str, title: str) -> str:
    branch = f"hermes/{task_id[:8]}-{slugify(title)}"
    try:
        git(repo, "checkout", "main")
        git(repo, "pull", "--ff-only")
        git(repo, "checkout", "-b", branch)
        return branch
    except CommandError as exc:
        raise AutoCoderError("merge_failure", str(exc)) from exc


def complete_git_workflow(repo: Path, task_id: str, title: str, branch: str) -> None:
    try:
        status = git(repo, "status", "--porcelain").stdout.strip()
        if not status:
            raise AutoCoderError("codex_failure", "Codex completed without producing repository changes")
        git(repo, "add", "-A")
        git(repo, "commit", "-m", f"{title}\n\nNotion task: {task_id}")
        git(repo, "checkout", "main")
        git(repo, "merge", "--no-ff", branch, "-m", f"Merge {branch}")
        git(repo, "push", "origin", "main")
    except CommandError as exc:
        raise AutoCoderError("merge_failure", str(exc)) from exc


def get_page_id(page: dict[str, Any]) -> str:
    page_id = page.get("id")
    if not isinstance(page_id, str) or not page_id:
        raise AutoCoderError("insufficient_spec", "Selected Notion page has no ID")
    return page_id


def run_once(config: Config) -> int:
    if not config.notion_database_id:
        emit_error("run_failed", failure_code="notion_update_failure", message="NOTION_TASK_DATABASE_ID is required")
        return 1
    if config.git_completion_mode != "auto_merge_main":
        emit_error(
            "run_failed",
            failure_code="out_of_scope",
            message=f"Unsupported completion mode: {config.git_completion_mode}",
        )
        return 1

    emit("run_started", database_id=config.notion_database_id)
    emit("progress", stage="notion_status_check")
    run_json_command(notion_command("status"))
    emit("progress", stage="notion_load_database_properties")
    properties = run_json_command(
        notion_command("get-database-properties", "--database-id", config.notion_database_id)
    )
    emit("progress", stage="notion_bind_schema")
    bindings = discover_schema(properties, config)
    emit("progress", stage="notion_list_pages")
    pages = run_json_command(notion_command("list-pages", "--database-id", config.notion_database_id))
    page = select_todo_page(pages, bindings)
    if page is None:
        emit("run_completed", result="no_task")
        return 0

    page_id = get_page_id(page)
    title = extract_page_title(page)
    project = get_property_value(page, bindings.project)
    try:
        emit("task_selected", task_id=page_id, title=title, project=project)
        emit("progress", stage="task_claim", task_id=page_id)
        set_status(page_id, bindings, STATUS_IN_PROGRESS)
        set_error_log(page_id, bindings, "")
        emit("task_claimed", task_id=page_id)
        emit("progress", stage="task_load_content", task_id=page_id)
        page_content = run_json_command(notion_command("get-page-content", "--page-id", page_id))
        emit("progress", stage="task_extract_sections", task_id=page_id)
        sections = extract_task_sections(page_content)
        emit("progress", stage="repo_resolve", task_id=page_id, project=project)
        repo = resolve_repo(config.apps_root, project)
        emit("progress", stage="repo_validate", task_id=page_id, repo=str(repo))
        validate_repo(repo)
        emit("progress", stage="git_prepare_branch", task_id=page_id)
        branch = prepare_git_branch(repo, page_id, title)
        emit("progress", stage="codex_build_prompt", task_id=page_id)
        prompt = build_codex_prompt(repo, page_id, title, sections)
        emit("progress", stage="codex_execute", task_id=page_id, branch=branch, model=config.codex_model)
        run_codex(repo, config, prompt)
        emit("codex_finished", task_id=page_id, success=True)
        emit("progress", stage="git_complete_workflow", task_id=page_id, branch=branch)
        complete_git_workflow(repo, page_id, title, branch)
        emit("progress", stage="notion_mark_done", task_id=page_id)
        set_status(page_id, bindings, STATUS_DONE)
        set_error_log(page_id, bindings, "")
        emit("run_completed", result="done", task_id=page_id)
        return 0
    except AutoCoderError as exc:
        emit("progress", stage="task_mark_blocked", task_id=page_id, failure_code=exc.failure_code)
        emit_error("task_blocked", task_id=page_id, failure_code=exc.failure_code, message=exc.message)
        try:
            block_task(page_id, bindings, exc.failure_code, exc.message)
        except Exception as block_exc:  # noqa: BLE001 - final reconciliation should be visible.
            emit_error(
                "run_failed",
                task_id=page_id,
                failure_code="notion_update_failure",
                message=str(block_exc),
            )
            return 1
        emit("run_completed", result="blocked", task_id=page_id, failure_code=exc.failure_code)
        return 1
    except Exception as exc:  # noqa: BLE001 - ensure uncaught errors are surfaced as structured output.
        emit_error(
            "run_failed",
            task_id=page_id,
            failure_code="internal_error",
            message=str(exc) or exc.__class__.__name__,
        )
        return 1


def build_status_payload(config: Config) -> dict[str, Any]:
    return {
        "ability": "auto-coder",
        "ok": bool(config.notion_database_id)
        and NOTION_BIN.exists()
        and shutil.which("codex") is not None
        and config.apps_root.exists(),
        "checks": {
            "notion_database_id": bool(config.notion_database_id),
            "notion_cli": NOTION_BIN.exists(),
            "codex_cli": shutil.which("codex") is not None,
            "apps_root": str(config.apps_root),
            "apps_root_exists": config.apps_root.exists(),
            "git_completion_mode": config.git_completion_mode,
            "codex_model": config.codex_model,
        },
    }


@app.command()
def status() -> None:
    """Validate local configuration and tool availability."""
    payload = build_status_payload(load_config())
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    if not payload["ok"]:
        raise typer.Exit(code=1)


@app.command("install-cron")
def install_cron(
    schedule: str = typer.Option("*/15 * * * *", help="Cron schedule expression to print."),
) -> None:
    """Print a crontab entry for this service without installing it."""
    command = f"cd {ROOT} && {AUTO_CODER_BIN} run"
    typer.echo(f"{schedule} {command}")


@app.command()
def run() -> None:
    """Process at most one Notion task."""
    raise typer.Exit(code=run_once(load_config()))


if __name__ == "__main__":
    app()
