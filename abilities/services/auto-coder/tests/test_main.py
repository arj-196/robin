from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
import sys
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "main.py"
SPEC = importlib.util.spec_from_file_location("auto_coder_main", MODULE_PATH)
assert SPEC is not None
main = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["auto_coder_main"] = main
SPEC.loader.exec_module(main)


class AutoCoderTests(unittest.TestCase):
    def config(self) -> main.Config:
        return main.Config(
            notion_database_id="db1",
            apps_root=Path("/tmp/apps").resolve(),
            status_property="Status",
            project_property="Project",
            error_log_property="Error Log",
            codex_model="gpt-5.3-codex",
            git_completion_mode="auto_merge_main",
        )

    def schema_payload(self) -> dict[str, object]:
        return {
            "data": {
                "editable_properties": [
                    {
                        "name": "Status",
                        "property_id": "status-id",
                        "type": "status",
                        "options": [
                            {"id": "todo-id", "name": "To do"},
                            {"id": "progress-id", "name": "In Progress"},
                            {"id": "done-id", "name": "Done"},
                            {"id": "blocked-id", "name": "Blocked"},
                        ],
                    },
                    {"name": "Project", "property_id": "project-id", "type": "select", "options": []},
                    {"name": "Error Log", "property_id": "error-log-id", "type": "rich_text", "options": []},
                ]
            }
        }

    def test_discover_schema_binds_required_options(self) -> None:
        bindings = main.discover_schema(self.schema_payload(), self.config())
        self.assertEqual(bindings.status.options_by_name["To do"], "todo-id")
        self.assertEqual(bindings.error_log.property_id, "error-log-id")

    def test_select_todo_page_returns_first_todo(self) -> None:
        bindings = main.discover_schema(self.schema_payload(), self.config())
        payload = {
            "data": {
                "results": [
                    {
                        "id": "done",
                        "properties": {"Status": {"type": "status", "status": {"name": "Done"}}},
                    },
                    {
                        "id": "todo",
                        "properties": {"Status": {"type": "status", "status": {"name": "To do"}}},
                    },
                ]
            }
        }
        page = main.select_todo_page(payload, bindings)
        self.assertIsNotNone(page)
        self.assertEqual(page["id"], "todo")

    def test_extract_task_sections_requires_all_sections(self) -> None:
        payload = {
            "data": {
                "blocks": [
                    {"type": "heading_1", "heading_1": {"rich_text": [{"plain_text": "Task"}]}},
                    {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "Build it"}]}},
                ]
            }
        }
        with self.assertRaises(main.AutoCoderError) as ctx:
            main.extract_task_sections(payload)
        self.assertEqual(ctx.exception.failure_code, "insufficient_spec")

    def test_extract_task_sections_success(self) -> None:
        payload = {
            "data": {
                "blocks": [
                    {"type": "heading_1", "heading_1": {"rich_text": [{"plain_text": "Task"}]}},
                    {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "Build it"}]}},
                    {
                        "type": "heading_2",
                        "heading_2": {"rich_text": [{"plain_text": "Acceptance Criteria"}]},
                    },
                    {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "Works"}]}},
                    {"type": "heading_2", "heading_2": {"rich_text": [{"plain_text": "Verification"}]}},
                    {"type": "code", "code": {"rich_text": [{"plain_text": "pytest"}]}},
                ]
            }
        }
        sections = main.extract_task_sections(payload)
        self.assertEqual(sections.task, "Build it")
        self.assertEqual(sections.verification, "pytest")

    def test_resolve_repo_rejects_path_escape(self) -> None:
        with self.assertRaises(main.AutoCoderError) as ctx:
            main.resolve_repo(Path("/tmp/apps").resolve(), "../secret")
        self.assertEqual(ctx.exception.failure_code, "unknown_project")

    def test_resolve_repo_allows_child_repo(self) -> None:
        repo = main.resolve_repo(Path("/tmp/apps").resolve(), "sample")
        self.assertEqual(repo, Path("/tmp/apps/sample").resolve())

    def test_validate_repo_rejects_missing_repo(self) -> None:
        with self.assertRaises(main.AutoCoderError) as ctx:
            main.validate_repo(Path("/tmp/definitely-missing-hermes-repo"))
        self.assertEqual(ctx.exception.failure_code, "missing_repo")

    def test_validate_repo_uses_git_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            responses = [
                main.subprocess.CompletedProcess(["git"], 0, "true\n", ""),
                main.subprocess.CompletedProcess(["git"], 0, "", ""),
                main.subprocess.CompletedProcess(["git"], 0, "", ""),
                main.subprocess.CompletedProcess(["git"], 0, "", ""),
            ]
            with patch.object(main, "git", side_effect=responses) as git:
                main.validate_repo(repo)
            self.assertEqual(git.call_count, 4)

    def test_validate_repo_rejects_dirty_worktree_from_mocked_git(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            responses = [
                main.subprocess.CompletedProcess(["git"], 0, "true\n", ""),
                main.subprocess.CompletedProcess(["git"], 0, "", ""),
                main.subprocess.CompletedProcess(["git"], 0, " M file.py\n", ""),
            ]
            with patch.object(main, "git", side_effect=responses):
                with self.assertRaises(main.AutoCoderError) as ctx:
                    main.validate_repo(repo)
            self.assertEqual(ctx.exception.failure_code, "missing_repo")

    def test_build_codex_command_uses_expected_boundary(self) -> None:
        command = main.build_codex_command(Path("/tmp/apps/sample"), "gpt-5.3-codex")
        self.assertEqual(command[:4], ["codex", "exec", "-C", "/tmp/apps/sample"])
        self.assertIn("--ask-for-approval", command)
        self.assertIn("workspace-write", command)

    def test_codex_report_requires_verification_evidence(self) -> None:
        self.assertFalse(main.codex_report_is_usable("", ""))
        self.assertTrue(main.codex_report_is_usable("Verification passed: pytest", ""))
        with self.assertRaises(main.AutoCoderError) as ctx:
            main.codex_report_is_usable("verification failed", "")
        self.assertEqual(ctx.exception.failure_code, "test_failure")

    def test_emit_writes_json(self) -> None:
        with patch("typer.echo") as echo:
            main.emit("run_completed", result="no_task")
        payload = json.loads(echo.call_args.args[0])
        self.assertEqual(payload["event"], "run_completed")
        self.assertEqual(payload["result"], "no_task")

    def test_status_payload_reports_missing_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = main.Config(
                notion_database_id="",
                apps_root=Path(tmp),
                status_property="Status",
                project_property="Project",
                error_log_property="Error Log",
                codex_model="gpt-5.3-codex",
                git_completion_mode="auto_merge_main",
            )
            payload = main.build_status_payload(config)
            self.assertFalse(payload["ok"])


if __name__ == "__main__":
    unittest.main()
