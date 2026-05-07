from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "main.py"
SPEC = importlib.util.spec_from_file_location("chores_main", MODULE_PATH)
assert SPEC is not None
main = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["chores_main"] = main
SPEC.loader.exec_module(main)

from abilities.services import shared_observability as shared  # noqa: E402


class ChoresTests(unittest.TestCase):
    def test_emit_writes_human_log(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), patch.dict(os.environ, {}, clear=True):
            main.configure_logger()
            main.emit("run_completed", result="ok")
        line = out.getvalue().strip()
        self.assertRegex(
            line,
            r"^\[INFO\] \[\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\] \[chores\] \[run_completed\] \[result=ok\]$",
        )

    def test_emit_debug_hidden_by_default(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), patch.dict(os.environ, {}, clear=True):
            main.configure_logger()
            main.emit_debug(
                "chore_skipped", chore_id="codex-init", reason="outside_window"
            )
        self.assertEqual(out.getvalue(), "")

    def test_emit_debug_visible_with_env_level(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), patch.dict(
            os.environ, {"ROBIN_LOG_LEVEL": "debug"}, clear=False
        ):
            main.configure_logger()
            main.emit_debug(
                "chore_skipped", chore_id="codex-init", reason="outside_window"
            )
        line = out.getvalue().strip()
        self.assertIn("[DEBUG]", line)
        self.assertIn("[chore_skipped]", line)
        self.assertIn("[chore_id=codex-init reason=outside_window]", line)

    def test_error_routes_to_stderr(self) -> None:
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(
            err
        ), patch.dict(os.environ, {}, clear=True):
            main.configure_logger()
            main.emit_error("run_failed", message="boom")
        self.assertEqual(out.getvalue(), "")
        self.assertIn("[ERROR]", err.getvalue())

    def test_is_due_in_window_when_not_succeeded_today(self) -> None:
        chore = main.Chore("codex-init", "desc", 9, "echo ok", True)
        now = datetime.fromisoformat("2026-05-07T09:10:00+02:00")
        due, reason = main.is_due(chore, {}, now)
        self.assertTrue(due)
        self.assertEqual(reason, "due")

    def test_is_due_skips_after_success(self) -> None:
        chore = main.Chore("codex-init", "desc", 9, "echo ok", True)
        now = datetime.fromisoformat("2026-05-07T09:10:00+02:00")
        due, reason = main.is_due(chore, {"last_success_date": "2026-05-07"}, now)
        self.assertFalse(due)
        self.assertEqual(reason, "already_succeeded_today")

    def test_is_due_skips_outside_window(self) -> None:
        chore = main.Chore("codex-init", "desc", 9, "echo ok", True)
        now = datetime.fromisoformat("2026-05-07T08:59:00+02:00")
        due, reason = main.is_due(chore, {}, now)
        self.assertFalse(due)
        self.assertEqual(reason, "outside_window")

    def test_load_and_save_state_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            data = {"codex-init": {"last_success_date": "2026-05-07", "last_error": ""}}
            main.save_state(path, data)
            loaded = main.load_state(path)
            self.assertEqual(loaded["codex-init"]["last_success_date"], "2026-05-07")

    def test_build_status_payload_invalid_timezone(self) -> None:
        config = main.Config(
            timezone_name="Mars/Olympus",
            state_file=Path("/tmp/state.json"),
            codex_init_command='codex exec "Reply with exactly: ok"',
        )
        payload = main.build_status_payload(config)
        self.assertFalse(payload["ok"])
        self.assertFalse(payload["checks"]["timezone_valid"])
        self.assertIn("last_run", payload)
        self.assertIn("last_log_path", payload)

    def test_run_once_retries_until_success_across_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "state.json"
            config = main.Config(
                timezone_name="Europe/Paris",
                state_file=state_file,
                codex_init_command='codex exec "Reply with exactly: ok"',
            )
            with patch.object(
                main,
                "now_in_timezone",
                return_value=datetime.fromisoformat("2026-05-07T09:05:00+02:00"),
            ), patch.object(
                main,
                "run_shell_command",
                return_value=main.subprocess.CompletedProcess(
                    args=["cmd"], returncode=1, stdout="", stderr="boom"
                ),
            ):
                outcome = main.run_once(config)
                self.assertEqual(outcome.exit_code, 1)
                self.assertEqual(outcome.result, "failed")

            failed_state = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertEqual(failed_state["codex-init"]["last_error"], "boom")
            self.assertNotIn("last_success_date", failed_state["codex-init"])

            with patch.object(
                main,
                "now_in_timezone",
                return_value=datetime.fromisoformat("2026-05-07T09:10:00+02:00"),
            ), patch.object(
                main,
                "run_shell_command",
                return_value=main.subprocess.CompletedProcess(
                    args=["cmd"], returncode=0, stdout="ok\n", stderr=""
                ),
            ):
                outcome = main.run_once(config)
                self.assertEqual(outcome.exit_code, 0)
                self.assertEqual(outcome.result, "ok")

            success_state = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertEqual(
                success_state["codex-init"]["last_success_date"], "2026-05-07"
            )
            self.assertEqual(success_state["codex-init"]["last_error"], "")

    def test_run_once_skips_after_success_same_day(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "state.json"
            state_file.write_text(
                json.dumps(
                    {
                        "codex-init": {
                            "last_success_date": "2026-05-07",
                            "last_error": "",
                        }
                    }
                ),
                encoding="utf-8",
            )
            config = main.Config(
                timezone_name="Europe/Paris",
                state_file=state_file,
                codex_init_command='codex exec "Reply with exactly: ok"',
            )
            with patch.object(
                main,
                "now_in_timezone",
                return_value=datetime.fromisoformat("2026-05-07T09:15:00+02:00"),
            ), patch.object(main, "run_shell_command") as run_cmd:
                outcome = main.run_once(config)
                self.assertEqual(outcome.exit_code, 0)
                self.assertEqual(outcome.result, "ok")
                run_cmd.assert_not_called()

    def test_status_payload_reports_latest_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {
                "ROBIN_RUN_LEDGER_DIR": str(Path(tmp) / ".robin"),
                "ROBIN_LOG_RUNS_DIR": str(Path(tmp) / ".robin" / "logs"),
            },
            clear=False,
        ):
            main.configure_logger()
            run = main.ServiceRun(
                main.load_observability_config(main.ROOT),
                service=main.SERVICE_NAME,
                command="./bin/chores run",
                log_level=main.resolve_log_level(),
                log_format=main.LOG_FORMAT,
            )
            run.start()
            main.emit("run_completed", result="ok")
            run.finish(main.RunOutcome(result="ok", exit_code=0))

            payload = main.build_status_payload(
                main.Config(
                    timezone_name="Europe/Paris",
                    state_file=Path(tmp) / "state.json",
                    codex_init_command='codex exec "Reply with exactly: ok"',
                )
            )

        self.assertEqual(payload["last_run"]["result"], "ok")
        self.assertEqual(payload["last_log_path"], payload["last_run"]["log_path"])

    def test_print_history_show_log_includes_log_contents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {
                "ROBIN_RUN_LEDGER_DIR": str(Path(tmp) / ".robin"),
                "ROBIN_LOG_RUNS_DIR": str(Path(tmp) / ".robin" / "logs"),
            },
            clear=False,
        ):
            main.configure_logger()
            run = main.ServiceRun(
                main.load_observability_config(main.ROOT),
                service=main.SERVICE_NAME,
                command="./bin/chores run",
                log_level=main.resolve_log_level(),
                log_format=main.LOG_FORMAT,
            )
            with contextlib.redirect_stdout(io.StringIO()):
                run.start()
                main.emit("chore_started", chore_id="codex-init", command="echo ok")
                run.finish(main.RunOutcome(result="ok", exit_code=0))
            result = CliRunner().invoke(
                main.app, ["history", "--show-log", "--limit", "1"]
            )
        self.assertEqual(result.exit_code, 0)
        self.assertIn('"result": "ok"', result.output)
        self.assertIn("[chore_started]", result.output)

    def test_history_prunes_old_records_and_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {
                "ROBIN_RUN_LEDGER_DIR": str(Path(tmp) / ".robin"),
                "ROBIN_LOG_RUNS_DIR": str(Path(tmp) / ".robin" / "logs"),
            },
            clear=False,
        ):
            config = main.load_observability_config(main.ROOT)
            old_log = config.logs_dir / main.SERVICE_NAME / "2026-01-01-oldrun.log"
            old_log.parent.mkdir(parents=True, exist_ok=True)
            old_log.write_text("old log\n", encoding="utf-8")
            old_time = datetime.now(timezone.utc) - timedelta(days=45)
            os.utime(old_log, (old_time.timestamp(), old_time.timestamp()))
            old_record = main.RunRecord(
                event="run_finished",
                run_id="oldrun",
                service=main.SERVICE_NAME,
                command="./bin/chores run",
                started_at=(old_time - timedelta(minutes=1))
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z"),
                finished_at=old_time.replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z"),
                duration_ms=1000,
                result="ok",
                exit_code=0,
                failure_code=None,
                message=None,
                log_path=str(old_log),
                metadata={},
            )
            main.append_record(config, old_record)

            history = shared.get_run_history(config, main.SERVICE_NAME, limit=10)

        self.assertEqual(history, [])
        self.assertFalse(old_log.exists())


if __name__ == "__main__":
    unittest.main()
