from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "main.py"
SPEC = importlib.util.spec_from_file_location("auto_coder_main", MODULE_PATH)
assert SPEC is not None
main = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["auto_coder_main"] = main
SPEC.loader.exec_module(main)


class AutoCoderTests(unittest.TestCase):
    def test_install_cron_uses_env_wrapper(self) -> None:
        result = CliRunner().invoke(main.app, ["install-cron"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("*/5 * * * *", result.output)
        self.assertIn(f"cd {main.ROOT} &&", result.output)
        self.assertIn(
            f"{main.RUN_WITH_ENV_BIN} {main.AUTO_CODER_BIN} run", result.output
        )

    def config(self) -> main.Config:
        return main.Config(
            notion_database_id="db1",
            apps_root=Path("/tmp/apps").resolve(),
            status_property="Status",
            project_property="Project",
            error_log_property="Error Log",
            codex_model="gpt-5.3-codex",
            git_completion_mode="auto_merge_main",
            openrouter_api_key="test-key",
            commit_model="openrouter/gpt-oss-120b",
            commit_max_context_tokens=16000,
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
                            {"id": "todo-id", "name": "Todo"},
                            {"id": "progress-id", "name": "In Progress"},
                            {"id": "done-id", "name": "Done"},
                            {"id": "blocked-id", "name": "Blocked"},
                        ],
                    },
                    {
                        "name": "Project",
                        "property_id": "project-id",
                        "type": "select",
                        "options": [],
                    },
                    {
                        "name": "Error Log",
                        "property_id": "error-log-id",
                        "type": "rich_text",
                        "options": [],
                    },
                ]
            }
        }

    def test_discover_schema_binds_required_options(self) -> None:
        bindings = main.discover_schema(self.schema_payload(), self.config())
        self.assertEqual(bindings.status.options_by_name["Todo"], "todo-id")
        self.assertEqual(bindings.error_log.property_id, "error-log-id")

    def test_select_todo_page_returns_first_todo(self) -> None:
        bindings = main.discover_schema(self.schema_payload(), self.config())
        payload = {
            "data": {
                "results": [
                    {
                        "id": "done",
                        "properties": {
                            "Status": {"type": "status", "status": {"name": "Done"}}
                        },
                    },
                    {
                        "id": "todo",
                        "properties": {
                            "Status": {"type": "status", "status": {"name": "Todo"}}
                        },
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
                    {
                        "type": "heading_1",
                        "heading_1": {"rich_text": [{"plain_text": "Task"}]},
                    },
                    {
                        "type": "paragraph",
                        "paragraph": {"rich_text": [{"plain_text": "Build it"}]},
                    },
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
                    {
                        "type": "heading_1",
                        "heading_1": {"rich_text": [{"plain_text": "Task"}]},
                    },
                    {
                        "type": "paragraph",
                        "paragraph": {"rich_text": [{"plain_text": "Build it"}]},
                    },
                    {
                        "type": "heading_2",
                        "heading_2": {
                            "rich_text": [{"plain_text": "Acceptance Criteria"}]
                        },
                    },
                    {
                        "type": "paragraph",
                        "paragraph": {"rich_text": [{"plain_text": "Works"}]},
                    },
                    {
                        "type": "heading_2",
                        "heading_2": {"rich_text": [{"plain_text": "Verification"}]},
                    },
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
            main.validate_repo(Path("/tmp/definitely-missing-robin-repo"))
        self.assertEqual(ctx.exception.failure_code, "missing_repo")

    def test_validate_repo_uses_git_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            responses = [
                main.subprocess.CompletedProcess(["git"], 0, "true\n", ""),
                main.subprocess.CompletedProcess(["git"], 0, "", ""),
                main.subprocess.CompletedProcess(["git"], 0, "", ""),
            ]
            with patch.object(main, "git", side_effect=responses) as git:
                main.validate_repo(repo)
            self.assertEqual(git.call_count, 3)

    def test_validate_repo_does_not_check_worktree_cleanliness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            responses = [
                main.subprocess.CompletedProcess(["git"], 0, "true\n", ""),
                main.subprocess.CompletedProcess(["git"], 0, "", ""),
                main.subprocess.CompletedProcess(["git"], 0, "", ""),
            ]
            with patch.object(main, "git", side_effect=responses) as git:
                main.validate_repo(repo)
            commands = [call.args[1:] for call in git.call_args_list]
            self.assertNotIn(("status", "--porcelain"), commands)

    def test_prepare_git_branch_uses_latest_main_and_timestamp_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            with (
                patch.object(main, "git") as git,
                patch.object(main, "datetime") as mock_datetime,
            ):
                mock_datetime.utcnow.return_value.strftime.return_value = (
                    "20260507-123456"
                )
                branch = main.prepare_git_branch(repo, "12345678-abcd", "My Task")
        self.assertEqual(branch, "robin/12345678-my-task-20260507-123456")
        commands = [call.args[1:] for call in git.call_args_list]
        self.assertEqual(
            commands,
            [
                ("checkout", "main"),
                ("fetch", "origin", "main"),
                ("reset", "--hard", "origin/main"),
                ("clean", "-fd"),
                ("checkout", "-b", "robin/12345678-my-task-20260507-123456"),
            ],
        )

    def test_build_codex_command_uses_expected_boundary(self) -> None:
        command = main.build_codex_command(Path("/tmp/apps/sample"), "gpt-5.3-codex")
        self.assertEqual(command[:4], ["codex", "exec", "-C", "/tmp/apps/sample"])
        self.assertIn("workspace-write", command)

    def test_codex_report_requires_verification_evidence(self) -> None:
        self.assertFalse(main.codex_report_is_usable("", ""))
        self.assertTrue(main.codex_report_is_usable("Verification passed: pytest", ""))
        with self.assertRaises(main.AutoCoderError) as ctx:
            main.codex_report_is_usable("verification failed", "")
        self.assertEqual(ctx.exception.failure_code, "test_failure")

    def test_emit_writes_human_log(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), patch.dict(os.environ, {}, clear=True):
            main.configure_logger()
            main.emit("run_completed", result="no_task")
        line = out.getvalue().strip()
        self.assertRegex(
            line,
            r"^\[INFO\] \[\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\] \[auto-coder\] \[run_completed\] \[result=no_task\]$",
        )

    def test_emit_debug_hidden_by_default(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), patch.dict(os.environ, {}, clear=True):
            main.configure_logger()
            main.emit_debug("progress", stage="repo_validate")
        self.assertEqual(out.getvalue(), "")

    def test_emit_debug_visible_with_env_level(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), patch.dict(
            os.environ, {"ROBIN_LOG_LEVEL": "debug"}, clear=False
        ):
            main.configure_logger()
            main.emit_debug("progress", stage="repo_validate")
        line = out.getvalue().strip()
        self.assertIn("[DEBUG]", line)
        self.assertIn("[progress]", line)
        self.assertIn("[stage=repo_validate]", line)

    def test_warn_level_suppresses_info(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), patch.dict(
            os.environ, {"ROBIN_LOG_LEVEL": "warn"}, clear=False
        ):
            main.configure_logger()
            main.emit("run_started", database_id="db1")
        self.assertEqual(out.getvalue(), "")

    def test_message_fields_are_sorted(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), patch.dict(os.environ, {}, clear=True):
            main.configure_logger()
            main.emit("task_selected", title="Task", task_id="t1", project="p1")
        line = out.getvalue().strip()
        self.assertIn("[project=p1 task_id=t1 title=Task]", line)

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
                openrouter_api_key="",
                commit_model="openrouter/gpt-oss-120b",
                commit_max_context_tokens=16000,
            )
            payload = main.build_status_payload(config)
            self.assertFalse(payload["ok"])
            self.assertIn("last_run", payload)
            self.assertIn("last_log_path", payload)

    def test_run_once_missing_database_reports_failed_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            outcome = main.run_once(
                main.Config(
                    notion_database_id="",
                    apps_root=Path(tmp),
                    status_property="Status",
                    project_property="Project",
                    error_log_property="Error Log",
                    codex_model="gpt-5.3-codex",
                    git_completion_mode="auto_merge_main",
                    openrouter_api_key="",
                    commit_model="openrouter/gpt-oss-120b",
                    commit_max_context_tokens=16000,
                )
            )
        self.assertEqual(outcome.result, "failed")
        self.assertEqual(outcome.failure_code, "notion_update_failure")

    def test_history_show_log_includes_recorded_log(self) -> None:
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
                command="./bin/auto-coder run",
                log_level=main.resolve_log_level(),
                log_format=main.LOG_FORMAT,
            )
            with contextlib.redirect_stdout(io.StringIO()):
                run.start()
                main.emit("run_completed", result="no_task")
                run.finish(main.RunOutcome(result="no_task", exit_code=0))
            result = CliRunner().invoke(main.app, ["history", "--run-id", run.run_id])
        self.assertEqual(result.exit_code, 0)
        self.assertIn('"result": "no_task"', result.output)
        self.assertIn(f'"run_id": "{run.run_id}"', result.output)
        self.assertIn("[run_completed]", result.output)

    def test_fallback_commit_message_is_conventional(self) -> None:
        message = main.build_fallback_commit_message(
            "task-123",
            "Fix API error handling",
            "src/api.py\nsrc/utils.py",
            "2 files changed, 12 insertions(+), 3 deletions(-)",
        )
        self.assertTrue(message.startswith("fix:"))
        self.assertIn("Notion task: task-123", message)
        self.assertIn("Files changed:", message)

    def test_validate_generated_commit_message_rejects_invalid_subject(self) -> None:
        with self.assertRaises(ValueError):
            main.validate_generated_commit_message("bad subject\n\n- changed file")

    def test_build_diff_payload_truncates_large_diff(self) -> None:
        large_diff = (
            "diff --git a/a.py b/a.py\n+line\n" * 300
            + "diff --git a/b.py b/b.py\n+line\n" * 300
        )
        payload = main.build_diff_payload(large_diff, 2000)
        self.assertLessEqual(len(payload), 2100)
        self.assertIn("truncated", payload)

    def test_generate_commit_message_falls_back_when_openrouter_response_invalid(
        self,
    ) -> None:
        config = self.config()
        repo = Path("/tmp/apps/sample")
        responses = [
            main.subprocess.CompletedProcess(["git"], 0, "src/main.py\n", ""),
            main.subprocess.CompletedProcess(
                ["git"], 0, "1 file changed, 2 insertions(+)\n", ""
            ),
            main.subprocess.CompletedProcess(
                ["git"], 0, "diff --git a/src/main.py b/src/main.py\n+x\n", ""
            ),
        ]

        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, exc_type, exc, tb) -> bool:
                return False

            def read(self) -> bytes:
                return b'{"choices":[{"message":{"content":"invalid"}}]}'

        with patch.object(main, "git", side_effect=responses), patch.object(
            main.urllib.request, "urlopen", return_value=FakeResponse()
        ):
            message = main.generate_commit_message_with_openrouter(
                repo, config, "task-1", "Add behavior"
            )
        self.assertTrue(message.startswith("feat:"))
        self.assertIn("Notion task: task-1", message)

    def test_complete_git_workflow_uses_generated_message(self) -> None:
        repo = Path("/tmp/apps/sample")
        config = self.config()
        responses = [
            main.subprocess.CompletedProcess(["git"], 0, " M src/main.py\n", ""),
            main.subprocess.CompletedProcess(["git"], 0, "", ""),
            main.subprocess.CompletedProcess(["git"], 0, "", ""),
            main.subprocess.CompletedProcess(["git"], 0, "", ""),
            main.subprocess.CompletedProcess(["git"], 0, "", ""),
            main.subprocess.CompletedProcess(["git"], 0, "", ""),
        ]
        with patch.object(main, "git", side_effect=responses) as git_mock, patch.object(
            main,
            "generate_commit_message_with_openrouter",
            return_value="feat: update parser\n\n- improve coverage\n\nNotion task: task-1",
        ):
            main.complete_git_workflow(
                repo, config, "task-1", "Update parser", "robin/task-1-update-parser"
            )
        commit_call = git_mock.call_args_list[2]
        self.assertEqual(commit_call.args[1], "commit")
        self.assertEqual(commit_call.args[2], "-m")
        self.assertIn("feat: update parser", commit_call.args[3])

    def test_run_command_single_calls_run_once_once(self) -> None:
        fake_service_run = MagicMock()
        outcome = main.RunOutcome(result="no_task", exit_code=0)
        with patch.object(main, "load_config", return_value=self.config()), patch.object(
            main, "run_once", return_value=outcome
        ) as run_once_mock, patch.object(
            main, "run_watch_loop"
        ) as run_watch_loop_mock, patch.object(
            main, "ServiceRun", return_value=fake_service_run
        ):
            result = CliRunner().invoke(main.app, ["run"])
        self.assertEqual(result.exit_code, 0)
        run_once_mock.assert_called_once()
        run_watch_loop_mock.assert_not_called()
        fake_service_run.start.assert_called_once()
        fake_service_run.finish.assert_called_once_with(outcome)

    def test_run_command_watch_calls_watch_loop(self) -> None:
        fake_service_run = MagicMock()
        outcome = main.RunOutcome(result="ok", exit_code=0)
        with patch.object(main, "load_config", return_value=self.config()), patch.object(
            main, "run_watch_loop", return_value=outcome
        ) as run_watch_loop_mock, patch.object(main, "run_once") as run_once_mock, patch.object(
            main, "ServiceRun", return_value=fake_service_run
        ):
            result = CliRunner().invoke(main.app, ["run", "--watch"])
        self.assertEqual(result.exit_code, 0)
        run_watch_loop_mock.assert_called_once_with(self.config(), 10)
        run_once_mock.assert_not_called()
        fake_service_run.finish.assert_called_once_with(outcome)

    def test_run_watch_loop_sleeps_only_after_no_task(self) -> None:
        config = self.config()
        outcomes = [
            main.RunOutcome(result="no_task", exit_code=0),
            main.RunOutcome(result="ok", exit_code=0),
            main.RunOutcome(result="blocked", exit_code=1),
            main.RunOutcome(result="failed", exit_code=1),
            KeyboardInterrupt(),
        ]
        with patch.object(main, "run_once", side_effect=outcomes), patch.object(
            main.time, "sleep"
        ) as sleep_mock:
            with self.assertRaises(KeyboardInterrupt):
                main.run_watch_loop(config, 10)
        sleep_mock.assert_called_once_with(10)

    def test_run_watch_cli_keyboard_interrupt_exits_zero(self) -> None:
        fake_service_run = MagicMock()
        with patch.object(main, "load_config", return_value=self.config()), patch.object(
            main, "run_watch_loop", side_effect=KeyboardInterrupt()
        ), patch.object(main, "ServiceRun", return_value=fake_service_run):
            result = CliRunner().invoke(main.app, ["run", "--watch"])
        self.assertEqual(result.exit_code, 0)
        finish_outcome = fake_service_run.finish.call_args.args[0]
        self.assertEqual(finish_outcome.exit_code, 0)

    def test_run_watch_rejects_invalid_poll_interval(self) -> None:
        result = CliRunner().invoke(
            main.app, ["run", "--watch", "--poll-interval-seconds", "0"]
        )
        self.assertNotEqual(result.exit_code, 0)


if __name__ == "__main__":
    unittest.main()
