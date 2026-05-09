# Auto-coder Service

The auto-coder service is a single-run worker intended to be called by cron.
The checked-in `./bin/auto-coder` shim runs it in Docker by default.
Each run claims at most one Notion task, delegates repository edits to Codex,
and completes the git workflow when Codex reports successful verification.
For local long-running usage, watch mode can continuously poll and process tasks
one after another.

## Commands

```bash
./bin/auto-coder status
./bin/auto-coder history
./bin/auto-coder run
./bin/auto-coder run --drain
./bin/auto-coder run --watch
./bin/auto-coder run --watch --poll-interval-seconds 10
./bin/auto-coder install-cron
./bin/auto-coder install-cron --drain
```

- `./bin/auto-coder run` processes at most one task and exits (cron-friendly).
- `./bin/auto-coder run --drain` processes all pending `Todo` tasks before exiting.
- `./bin/auto-coder run --watch` keeps running, polling for new Todo tasks.
- Watch mode sleeps only when no task is available, and continues after blocked/failed tasks.
- Only one auto-coder instance can run at a time; overlapping runs exit immediately.
- The first Dockerized run builds the `robin-auto-coder` image if it is missing.
- `ROBIN_HOME` is mounted read-write at `/robin-home` inside the container.
- `AUTO_CODER_APPS_ROOT` is mounted read-write at `/apps` inside the container.
- Host `~/.codex` is mounted read-write for Codex CLI authentication and state.

## Required Environment

- `NOTION_API_KEY`: required by `./bin/notion`
- `NOTION_TASK_DATABASE_ID`: Notion task database
- `AUTO_CODER_APPS_ROOT`: root directory containing target repositories, defaults to `~/apps`
- `ROBIN_HOME`: base directory for Robin runtime files, defaults to `.robin` under repo root

Optional field-name configuration:

- `AUTO_CODER_STATUS_PROPERTY`, defaults to `Status`
- `AUTO_CODER_PROJECT_PROPERTY`, defaults to `Project`
- `AUTO_CODER_ERROR_LOG_PROPERTY`, defaults to `Error Log`
- `AUTO_CODER_CODEX_MODEL`, defaults to `gpt-5.3-codex`
- `AUTO_CODER_CODEX_SANDBOX`, defaults to `workspace-write`
- `AUTO_CODER_GIT_COMPLETION_MODE`, defaults to `auto_merge_main`
- `OPENROUTER_API_KEY`, used to generate diff-aware commit messages
- `AUTO_CODER_COMMIT_MODEL`, defaults to `openrouter/gpt-oss-120b`
- `AUTO_CODER_COMMIT_MAX_CONTEXT_TOKENS`, defaults to `16000`
- `AUTO_CODER_LOCKS_DIR`, defaults to `locks` (relative to `ROBIN_HOME` unless absolute)
- `ROBIN_RUN_LEDGER_DIR`, defaults to `run-ledger` (relative to `ROBIN_HOME` unless absolute)
- `ROBIN_LOG_RUNS_DIR`, defaults to `logs` (relative to `ROBIN_HOME` unless absolute)
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

- a `run ledger` entry at `<ROBIN_HOME>/<ROBIN_RUN_LEDGER_DIR>/run-ledger.jsonl`
- a dedicated `run log` file at `<ROBIN_HOME>/<ROBIN_LOG_RUNS_DIR>/auto-coder/<YYYY-MM-DD>-<run_id>.log`

Codex subprocess stdout/stderr is streamed into the same run log with
`codex_stream` events for end-to-end debugging.

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
`--sandbox <AUTO_CODER_CODEX_SANDBOX>`. For this POC, Codex's reported verification is
trusted; the service does not rerun verification commands.
