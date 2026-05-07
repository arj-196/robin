from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import typer
from loguru import logger

app = typer.Typer(help="Cron-driven operational chore runner for Robin.", no_args_is_help=True)

ROOT = Path(__file__).resolve().parents[4]
CHORES_BIN = ROOT / "bin" / "chores"
DEFAULT_TIMEZONE = "Europe/Paris"
DEFAULT_STATE_FILE = ".robin/chores-state.json"
DEFAULT_CODEX_INIT_COMMAND = 'codex exec "Reply with exactly: ok"'
SERVICE_NAME = "chores"
LEVEL_MAP = {
    "debug": "DEBUG",
    "info": "INFO",
    "warn": "WARNING",
    "warning": "WARNING",
    "error": "ERROR",
}
LOG_FORMAT = "[<level>{level}</level>] [{extra[time_utc]}] [{extra[service]}] [{extra[event]}] [{message}]"


@dataclass(frozen=True)
class Config:
    timezone_name: str
    state_file: Path
    codex_init_command: str


@dataclass(frozen=True)
class Chore:
    id: str
    description: str
    window_hour: int
    action_command: str
    retry_until_success_in_window: bool


class ChoresError(Exception):
    pass


def emit(event: str, **fields: Any) -> None:
    log_event("INFO", event, **fields)


def emit_error(event: str, **fields: Any) -> None:
    log_event("ERROR", event, **fields)


def emit_debug(event: str, **fields: Any) -> None:
    log_event("DEBUG", event, **fields)


def format_time_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


def format_message(fields: dict[str, Any]) -> str:
    if not fields:
        return "-"
    return " ".join(f"{key}={format_value(fields[key])}" for key in sorted(fields))


def configure_logger() -> None:
    configured = LEVEL_MAP.get(os.getenv("ROBIN_LOG_LEVEL", "info").strip().lower(), "INFO")
    logger.remove()
    logger.add(
        sys.stdout,
        level=configured,
        format=LOG_FORMAT,
        colorize=None,
        filter=lambda record: record["level"].name != "ERROR",
    )
    logger.add(
        sys.stderr,
        level=configured,
        format=LOG_FORMAT,
        colorize=None,
        filter=lambda record: record["level"].name == "ERROR",
    )


def log_event(level: str, event: str, **fields: Any) -> None:
    logger.bind(
        time_utc=format_time_utc(),
        service=SERVICE_NAME,
        event=event,
    ).log(level, format_message(fields))


configure_logger()


def expand_path(value: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(value))).resolve()


def load_config() -> Config:
    return Config(
        timezone_name=os.getenv("CHORES_TIMEZONE", DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE,
        state_file=expand_path(os.getenv("CHORES_STATE_FILE", DEFAULT_STATE_FILE).strip() or DEFAULT_STATE_FILE),
        codex_init_command=os.getenv("CHORES_CODEX_INIT_COMMAND", DEFAULT_CODEX_INIT_COMMAND).strip()
        or DEFAULT_CODEX_INIT_COMMAND,
    )


def build_chores(config: Config) -> list[Chore]:
    return [
        Chore(
            id="codex-init",
            description="Initialize Codex usage window in the morning",
            window_hour=9,
            action_command=config.codex_init_command,
            retry_until_success_in_window=True,
        )
    ]


def load_state(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ChoresError(f"Invalid state JSON at {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ChoresError(f"Invalid state format at {path}: expected object")
    parsed: dict[str, dict[str, str]] = {}
    for key, value in payload.items():
        if isinstance(key, str) and isinstance(value, dict):
            parsed[key] = {k: str(v) for k, v in value.items() if isinstance(k, str)}
    return parsed


def save_state(path: Path, state: dict[str, dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def now_in_timezone(timezone_name: str) -> datetime:
    try:
        tz = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ChoresError(f"Invalid timezone: {timezone_name}") from exc
    return datetime.now(tz)


def is_due(chore: Chore, chore_state: dict[str, str], now_local: datetime) -> tuple[bool, str]:
    today = now_local.date().isoformat()
    if chore_state.get("last_success_date") == today:
        return (False, "already_succeeded_today")
    if now_local.hour != chore.window_hour:
        return (False, "outside_window")
    return (True, "due")


def run_shell_command(command: str) -> subprocess.CompletedProcess[str]:
    parts = shlex.split(command)
    if not parts:
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="Empty command")
    return subprocess.run(parts, text=True, capture_output=True, check=False)


def summarize(text: str, limit: int = 1200) -> str:
    trimmed = text.strip()
    if len(trimmed) <= limit:
        return trimmed
    return trimmed[:limit] + "...[truncated]"


def build_status_payload(config: Config) -> dict[str, Any]:
    timezone_ok = True
    timezone_error = ""
    try:
        ZoneInfo(config.timezone_name)
    except ZoneInfoNotFoundError:
        timezone_ok = False
        timezone_error = f"Unknown timezone: {config.timezone_name}"

    command_parts = shlex.split(config.codex_init_command)
    command_bin = command_parts[0] if command_parts else ""
    codex_command_resolves = bool(command_bin) and shutil.which(command_bin) is not None

    return {
        "ability": "chores",
        "ok": timezone_ok and codex_command_resolves,
        "checks": {
            "timezone": config.timezone_name,
            "timezone_valid": timezone_ok,
            "timezone_error": timezone_error,
            "state_file": str(config.state_file),
            "codex_init_command": config.codex_init_command,
            "codex_init_command_binary": command_bin,
            "codex_init_command_binary_resolves": codex_command_resolves,
        },
    }


def run_once(config: Config) -> int:
    chores = build_chores(config)
    now_local = now_in_timezone(config.timezone_name)
    state = load_state(config.state_file)

    emit("run_started", timezone=config.timezone_name, now=now_local.isoformat(), total_chores=len(chores))

    any_failed = False
    for chore in chores:
        chore_state = state.get(chore.id, {})
        due, reason = is_due(chore, chore_state, now_local)

        if not due:
            emit_debug("chore_skipped", chore_id=chore.id, reason=reason)
            continue

        emit("chore_started", chore_id=chore.id, command=chore.action_command)
        result = run_shell_command(chore.action_command)
        attempted_at = now_local.isoformat()

        if result.returncode == 0 and bool(result.stdout.strip()):
            new_state = dict(chore_state)
            new_state["last_success_date"] = now_local.date().isoformat()
            new_state["last_attempt_at"] = attempted_at
            new_state["last_error"] = ""
            state[chore.id] = new_state
            emit(
                "chore_succeeded",
                chore_id=chore.id,
                stdout=summarize(result.stdout),
            )
        else:
            any_failed = True
            failure_detail = result.stderr.strip() or "empty stdout or non-zero exit"
            new_state = dict(chore_state)
            new_state["last_attempt_at"] = attempted_at
            new_state["last_error"] = summarize(failure_detail)
            state[chore.id] = new_state
            emit_error(
                "chore_failed",
                chore_id=chore.id,
                exit_code=result.returncode,
                stderr=summarize(result.stderr),
                stdout=summarize(result.stdout),
            )

    save_state(config.state_file, state)
    emit("run_completed", result="failed" if any_failed else "ok")
    return 1 if any_failed else 0


@app.command()
def status() -> None:
    """Validate local configuration and command availability."""
    payload = build_status_payload(load_config())
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    if not payload["ok"]:
        raise typer.Exit(code=1)


@app.command("install-cron")
def install_cron(
    schedule: str = typer.Option("*/5 * * * *", help="Cron schedule expression to print."),
) -> None:
    """Print a crontab entry for this service without installing it."""
    command = f"cd {ROOT} && {CHORES_BIN} run"
    typer.echo(f"{schedule} {command}")


@app.command()
def run() -> None:
    """Evaluate all chores and execute due chores."""
    try:
        code = run_once(load_config())
    except ChoresError as exc:
        emit_error("run_failed", message=str(exc))
        raise typer.Exit(code=1) from exc
    raise typer.Exit(code=code)


if __name__ == "__main__":
    app()
