from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import typer
from loguru import logger

DEFAULT_RETENTION_DAYS = 30
DEFAULT_ROBIN_HOME = ".robin"
DEFAULT_RUN_LEDGER_DIR = "run-ledger"
DEFAULT_LOG_RUNS_DIR = "logs"
RUN_LEDGER_FILENAME = "run-ledger.jsonl"


@dataclass(frozen=True)
class ObservabilityConfig:
    root: Path
    ledger_dir: Path
    logs_dir: Path
    telegram_bot_token: str
    telegram_chat_id: str
    retention_days: int = DEFAULT_RETENTION_DAYS

    @property
    def ledger_path(self) -> Path:
        return self.ledger_dir / RUN_LEDGER_FILENAME


@dataclass(frozen=True)
class RunOutcome:
    result: str
    exit_code: int
    failure_code: str | None = None
    message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RunRecord:
    event: str
    run_id: str
    service: str
    command: str
    started_at: str
    finished_at: str | None
    duration_ms: int | None
    result: str | None
    exit_code: int | None
    failure_code: str | None
    message: str | None
    log_path: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": self.event,
            "run_id": self.run_id,
            "service": self.service,
            "command": self.command,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "result": self.result,
            "exit_code": self.exit_code,
            "failure_code": self.failure_code,
            "message": self.message,
            "log_path": self.log_path,
            "metadata": self.metadata,
        }


class ServiceRun:
    def __init__(
        self,
        config: ObservabilityConfig,
        *,
        service: str,
        command: str,
        log_level: str,
        log_format: str,
    ) -> None:
        self.config = config
        self.service = service
        self.command = command
        self.run_id = uuid.uuid4().hex[:12]
        self.started_at = datetime.now(timezone.utc)
        self.log_path = (
            config.logs_dir
            / service
            / f"{self.started_at.date().isoformat()}-{self.run_id}.log"
        )
        self._log_level = log_level
        self._log_format = log_format
        self._sink_id: int | None = None
        self._finished = False

    def start(self) -> None:
        prune_observability_artifacts(self.config)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.touch(exist_ok=True)
        self._sink_id = logger.add(
            self.log_path,
            level=self._log_level,
            format=self._log_format,
            colorize=False,
        )
        append_record(
            self.config,
            RunRecord(
                event="run_started",
                run_id=self.run_id,
                service=self.service,
                command=self.command,
                started_at=format_time_utc(self.started_at),
                finished_at=None,
                duration_ms=None,
                result=None,
                exit_code=None,
                failure_code=None,
                message=None,
                log_path=str(self.log_path),
                metadata={},
            ),
        )

    def finish(self, outcome: RunOutcome) -> RunRecord:
        if self._finished:
            raise RuntimeError("Run already finished")
        finished_at = datetime.now(timezone.utc)
        duration_ms = max(
            0, int((finished_at - self.started_at).total_seconds() * 1000)
        )
        record = RunRecord(
            event="run_finished",
            run_id=self.run_id,
            service=self.service,
            command=self.command,
            started_at=format_time_utc(self.started_at),
            finished_at=format_time_utc(finished_at),
            duration_ms=duration_ms,
            result=outcome.result,
            exit_code=outcome.exit_code,
            failure_code=outcome.failure_code,
            message=outcome.message,
            log_path=str(self.log_path),
            metadata=outcome.metadata,
        )
        append_record(self.config, record)
        self._finished = True
        self._remove_sink()
        if outcome.result == "failed":
            send_telegram_failure(self.config, record)
        return record

    def _remove_sink(self) -> None:
        if self._sink_id is not None:
            logger.remove(self._sink_id)
            self._sink_id = None


def format_time_utc(value: datetime | None = None) -> str:
    current = value or datetime.now(timezone.utc)
    return current.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_log_level() -> str:
    configured = os.getenv("ROBIN_LOG_LEVEL", "info").strip().lower()
    return {
        "debug": "DEBUG",
        "info": "INFO",
        "warn": "WARNING",
        "warning": "WARNING",
        "error": "ERROR",
    }.get(configured, "INFO")


def resolve_robin_home(root: Path) -> Path:
    configured = os.getenv("ROBIN_HOME", DEFAULT_ROBIN_HOME).strip() or DEFAULT_ROBIN_HOME
    expanded = Path(os.path.expandvars(os.path.expanduser(configured)))
    if not expanded.is_absolute():
        expanded = root / expanded
    return expanded.resolve()


def expand_observability_path(root: Path, robin_home: Path, value: str) -> Path:
    expanded = Path(os.path.expandvars(os.path.expanduser(value)))
    if not expanded.is_absolute():
        expanded = robin_home / expanded
    return expanded.resolve()


def load_observability_config(root: Path) -> ObservabilityConfig:
    robin_home = resolve_robin_home(root)
    return ObservabilityConfig(
        root=root,
        ledger_dir=expand_observability_path(
            root,
            robin_home,
            os.getenv("ROBIN_RUN_LEDGER_DIR", DEFAULT_RUN_LEDGER_DIR).strip()
            or DEFAULT_RUN_LEDGER_DIR,
        ),
        logs_dir=expand_observability_path(
            root,
            robin_home,
            os.getenv("ROBIN_LOG_RUNS_DIR", DEFAULT_LOG_RUNS_DIR).strip()
            or DEFAULT_LOG_RUNS_DIR,
        ),
        telegram_bot_token=os.getenv("ROBIN_TELEGRAM_BOT_TOKEN", "").strip(),
        telegram_chat_id=os.getenv("ROBIN_TELEGRAM_CHAT_ID", "").strip(),
    )


def prune_observability_artifacts(config: ObservabilityConfig) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=config.retention_days)
    records = read_all_records(config)
    kept: list[RunRecord] = []
    changed = False
    for record in records:
        started = parse_time(record.started_at)
        if started is None or started >= cutoff:
            kept.append(record)
        else:
            changed = True
    if changed:
        write_all_records(config, kept)

    if not config.logs_dir.exists():
        return
    for path in config.logs_dir.rglob("*.log"):
        try:
            modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except FileNotFoundError:
            continue
        if modified_at < cutoff:
            path.unlink(missing_ok=True)


def append_record(config: ObservabilityConfig, record: RunRecord) -> None:
    config.ledger_dir.mkdir(parents=True, exist_ok=True)
    with config.ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")


def read_all_records(config: ObservabilityConfig) -> list[RunRecord]:
    if not config.ledger_path.exists():
        return []
    records: list[RunRecord] = []
    for line in config.ledger_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        records.append(
            RunRecord(
                event=str(payload.get("event") or ""),
                run_id=str(payload.get("run_id") or ""),
                service=str(payload.get("service") or ""),
                command=str(payload.get("command") or ""),
                started_at=str(payload.get("started_at") or ""),
                finished_at=_optional_string(payload.get("finished_at")),
                duration_ms=_optional_int(payload.get("duration_ms")),
                result=_optional_string(payload.get("result")),
                exit_code=_optional_int(payload.get("exit_code")),
                failure_code=_optional_string(payload.get("failure_code")),
                message=_optional_string(payload.get("message")),
                log_path=str(payload.get("log_path") or ""),
                metadata=_normalize_metadata(payload.get("metadata")),
            )
        )
    return records


def write_all_records(config: ObservabilityConfig, records: list[RunRecord]) -> None:
    config.ledger_dir.mkdir(parents=True, exist_ok=True)
    with config.ledger_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")


def get_run_history(
    config: ObservabilityConfig, service: str, limit: int | None = None
) -> list[RunRecord]:
    prune_observability_artifacts(config)
    records = [
        record
        for record in read_all_records(config)
        if record.service == service and record.event == "run_finished"
    ]
    records.sort(key=lambda item: item.finished_at or item.started_at, reverse=True)
    if limit is None:
        return records
    return records[: max(0, limit)]


def get_all_run_history(
    config: ObservabilityConfig, limit: int | None = None
) -> list[RunRecord]:
    prune_observability_artifacts(config)
    records = [record for record in read_all_records(config) if record.event == "run_finished"]
    records.sort(key=lambda item: item.finished_at or item.started_at, reverse=True)
    if limit is None:
        return records
    return records[: max(0, limit)]


def get_latest_run(config: ObservabilityConfig, service: str) -> RunRecord | None:
    history = get_run_history(config, service, limit=1)
    return history[0] if history else None


def get_run_by_id(
    config: ObservabilityConfig, service: str, run_id: str
) -> RunRecord | None:
    history = get_run_history(config, service, limit=None)
    for record in history:
        if record.run_id == run_id:
            return record
    return None


def read_log_text(record: RunRecord) -> str:
    path = Path(record.log_path)
    if not path.exists():
        raise FileNotFoundError(record.log_path)
    return path.read_text(encoding="utf-8")


def read_log_tail_text(record: RunRecord, max_chars: int = 12000) -> str:
    text = read_log_text(record)
    if len(text) <= max_chars:
        return text
    return "...[truncated]\n" + text[-max_chars:]


def print_run_history(
    root: Path,
    service: str,
    limit: int,
    show_log: bool,
    run_id: str | None = None,
) -> None:
    config = load_observability_config(root)
    if run_id is not None:
        record = get_run_by_id(config, service, run_id)
        if record is None:
            raise typer.BadParameter(f"Run not found for service {service}: {run_id}")
        history = [record]
    else:
        history = get_run_history(config, service, limit=limit)

    if not show_log and run_id is None:
        typer.echo(
            json.dumps(
                [record.to_dict() for record in history], indent=2, sort_keys=True
            )
        )
        return

    for index, record in enumerate(history):
        if index > 0:
            typer.echo("\n" + ("-" * 60))
        typer.echo(json.dumps(record.to_dict(), indent=2, sort_keys=True))
        typer.echo("\n--- log ---")
        try:
            typer.echo(read_log_text(record).rstrip("\n"))
        except FileNotFoundError as exc:
            raise typer.BadParameter(f"Run log is missing: {exc}") from exc


def register_history_command(app: typer.Typer, *, root: Path, service: str) -> None:
    @app.command()
    def history(
        limit: int = typer.Option(10, min=1, help="Number of completed runs to show."),
        show_log: bool = typer.Option(
            False, "--show-log", help="Print the stored run log contents."
        ),
        run_id: str | None = typer.Option(
            None, "--run-id", help="Show exactly one completed run by run ID."
        ),
    ) -> None:
        """Show recent run history from the local run ledger."""
        print_run_history(
            root=root, service=service, limit=limit, show_log=show_log, run_id=run_id
        )


def send_telegram_failure(config: ObservabilityConfig, record: RunRecord) -> None:
    if not config.telegram_bot_token or not config.telegram_chat_id:
        return
    message = build_telegram_message(record)
    data = urllib.parse.urlencode(
        {
            "chat_id": config.telegram_chat_id,
            "text": message,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{config.telegram_bot_token}/sendMessage",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10):
            return
    except (urllib.error.URLError, TimeoutError):
        return


def build_telegram_message(record: RunRecord) -> str:
    lines = [
        f"Robin service failure: {record.service}",
        f"run_id={record.run_id}",
        f"result={record.result or 'failed'}",
        f"failure_code={record.failure_code or 'unknown'}",
        f"duration_ms={record.duration_ms if record.duration_ms is not None else 'unknown'}",
        f"log_path={record.log_path}",
    ]
    if record.message:
        lines.append(f"message={summarize_text(record.message, 500)}")
    return "\n".join(lines)


def summarize_text(text: str, limit: int = 500) -> str:
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit] + "...[truncated]"


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    string_value = str(value)
    return string_value if string_value else None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            continue
        if isinstance(item, (str, int, float, bool)) or item is None:
            normalized[key] = item
        else:
            normalized[key] = str(item)
    return normalized
