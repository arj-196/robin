# Auto-coder Service

The auto-coder service is a single-run worker intended to be called by cron.
Each run claims at most one Notion task, delegates repository edits to Codex,
and completes the git workflow when Codex reports successful verification.

## Commands

```bash
./bin/auto-coder status
./bin/auto-coder history
./bin/auto-coder run
./bin/auto-coder install-cron
```

## Required Environment

- `NOTION_API_KEY`: required by `./bin/notion`
- `NOTION_TASK_DATABASE_ID`: Notion task database
- `AUTO_CODER_APPS_ROOT`: root directory containing target repositories, defaults to `~/apps`

Optional field-name configuration:

- `AUTO_CODER_STATUS_PROPERTY`, defaults to `Status`
- `AUTO_CODER_PROJECT_PROPERTY`, defaults to `Project`
- `AUTO_CODER_ERROR_LOG_PROPERTY`, defaults to `Error Log`
- `AUTO_CODER_CODEX_MODEL`, defaults to `gpt-5.3-codex`
- `AUTO_CODER_GIT_COMPLETION_MODE`, defaults to `auto_merge_main`
- `OPENROUTER_API_KEY`, used to generate diff-aware commit messages
- `AUTO_CODER_COMMIT_MODEL`, defaults to `openrouter/gpt-oss-120b`
- `AUTO_CODER_COMMIT_MAX_CONTEXT_TOKENS`, defaults to `16000`
- `ROBIN_RUN_LEDGER_DIR`, defaults to `.robin`
- `ROBIN_LOG_RUNS_DIR`, defaults to `.robin/logs`
- `ROBIN_TELEGRAM_BOT_TOKEN`, optional Telegram bot token for failure alerts
- `ROBIN_TELEGRAM_CHAT_ID`, optional Telegram chat ID for failure alerts
- `ROBIN_LOG_LEVEL`, defaults to `info` (`debug|info|warn|error`)

## Service Logs

`run` outputs human-readable service events in this format:

`[LEVEL] [TIME] [SERVICE] [EVENT] [MESSAGE]`

- `TIME` is ISO-8601 UTC (`Z`)
- `MESSAGE` is deterministic `key=value` pairs
- `DEBUG` events are hidden unless `ROBIN_LOG_LEVEL=debug`

Each cron execution also creates:

- a `run ledger` entry in `.robin/run-ledger.jsonl`
- a dedicated `run log` file at `.robin/logs/auto-coder/<YYYY-MM-DD>-<run_id>.log`

Use `./bin/auto-coder history --limit 10` to inspect recent finished runs.
Add `--show-log` to print the stored log contents for those runs.

## Task Format

The Notion page body must contain these headings:

- `Task`
- `Acceptance Criteria`
- `Verification`

Tasks missing any required section are marked `Blocked` with
`insufficient_spec`.

## Safety Boundary

The service resolves `Project` to `AUTO_CODER_APPS_ROOT/<Project>`, rejects paths that
escape `AUTO_CODER_APPS_ROOT`, requires a clean local `main` branch, and invokes Codex with
`--sandbox workspace-write`. For this POC, Codex's reported verification is
trusted; the service does not rerun verification commands.
