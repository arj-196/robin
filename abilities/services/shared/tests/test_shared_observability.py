from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import typer

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from abilities.services import shared_observability as shared  # noqa: E402


class SharedObservabilityTests(unittest.TestCase):
    def append_finished_run(
        self,
        config: shared.ObservabilityConfig,
        *,
        service: str,
        run_id: str,
        finished_at: str,
        log_text: str = "log line\n",
        create_log: bool = True,
    ) -> shared.RunRecord:
        log_path = config.logs_dir / service / f"2026-05-07-{run_id}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if create_log:
            log_path.write_text(log_text, encoding="utf-8")
        record = shared.RunRecord(
            event="run_finished",
            run_id=run_id,
            service=service,
            command=f"./bin/{service} run",
            started_at="2026-05-07T08:00:00Z",
            finished_at=finished_at,
            duration_ms=1000,
            result="ok",
            exit_code=0,
            failure_code=None,
            message=None,
            log_path=str(log_path),
            metadata={},
        )
        shared.append_record(config, record)
        return record

    def test_print_run_history_returns_json_array_for_list_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {
                "ROBIN_RUN_LEDGER_DIR": str(Path(tmp) / ".robin"),
                "ROBIN_LOG_RUNS_DIR": str(Path(tmp) / ".robin" / "logs"),
            },
            clear=False,
        ):
            config = shared.load_observability_config(ROOT)
            self.append_finished_run(
                config,
                service="auto-coder",
                run_id="older",
                finished_at="2026-05-07T08:01:00Z",
            )
            self.append_finished_run(
                config,
                service="auto-coder",
                run_id="newer",
                finished_at="2026-05-07T08:02:00Z",
            )
            self.append_finished_run(
                config,
                service="chores",
                run_id="other-service",
                finished_at="2026-05-07T08:03:00Z",
            )

            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                shared.print_run_history(
                    ROOT, "auto-coder", limit=10, show_log=False, run_id=None
                )

        payload = json.loads(out.getvalue())
        self.assertEqual([item["run_id"] for item in payload], ["newer", "older"])

    def test_print_run_history_run_id_auto_includes_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {
                "ROBIN_RUN_LEDGER_DIR": str(Path(tmp) / ".robin"),
                "ROBIN_LOG_RUNS_DIR": str(Path(tmp) / ".robin" / "logs"),
            },
            clear=False,
        ):
            config = shared.load_observability_config(ROOT)
            self.append_finished_run(
                config,
                service="auto-coder",
                run_id="matchme",
                finished_at="2026-05-07T08:02:00Z",
                log_text="matched log\n",
            )
            self.append_finished_run(
                config,
                service="auto-coder",
                run_id="other",
                finished_at="2026-05-07T08:01:00Z",
                log_text="other log\n",
            )

            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                shared.print_run_history(
                    ROOT, "auto-coder", limit=1, show_log=False, run_id="matchme"
                )

        output = out.getvalue()
        self.assertIn('"run_id": "matchme"', output)
        self.assertIn("matched log", output)
        self.assertNotIn('"run_id": "other"', output)

    def test_print_run_history_unknown_run_id_raises_bad_parameter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {
                "ROBIN_RUN_LEDGER_DIR": str(Path(tmp) / ".robin"),
                "ROBIN_LOG_RUNS_DIR": str(Path(tmp) / ".robin" / "logs"),
            },
            clear=False,
        ):
            with self.assertRaises(typer.BadParameter) as ctx:
                shared.print_run_history(
                    ROOT, "auto-coder", limit=10, show_log=False, run_id="missing"
                )

        self.assertEqual(
            str(ctx.exception), "Run not found for service auto-coder: missing"
        )

    def test_print_run_history_run_id_is_scoped_by_service(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {
                "ROBIN_RUN_LEDGER_DIR": str(Path(tmp) / ".robin"),
                "ROBIN_LOG_RUNS_DIR": str(Path(tmp) / ".robin" / "logs"),
            },
            clear=False,
        ):
            config = shared.load_observability_config(ROOT)
            self.append_finished_run(
                config,
                service="chores",
                run_id="shared-id",
                finished_at="2026-05-07T08:03:00Z",
            )

            with self.assertRaises(typer.BadParameter) as ctx:
                shared.print_run_history(
                    ROOT, "auto-coder", limit=10, show_log=False, run_id="shared-id"
                )

        self.assertEqual(
            str(ctx.exception), "Run not found for service auto-coder: shared-id"
        )

    def test_print_run_history_missing_log_raises_bad_parameter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {
                "ROBIN_RUN_LEDGER_DIR": str(Path(tmp) / ".robin"),
                "ROBIN_LOG_RUNS_DIR": str(Path(tmp) / ".robin" / "logs"),
            },
            clear=False,
        ):
            config = shared.load_observability_config(ROOT)
            self.append_finished_run(
                config,
                service="auto-coder",
                run_id="nolog",
                finished_at="2026-05-07T08:02:00Z",
                create_log=False,
            )

            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(typer.BadParameter) as ctx:
                    shared.print_run_history(
                        ROOT, "auto-coder", limit=10, show_log=True, run_id=None
                    )

        self.assertIn("Run log is missing:", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
