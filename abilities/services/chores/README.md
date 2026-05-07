# Chores Service

The chores service is a single-run worker intended to be called by cron.
Each run evaluates registered chores, executes due chores, and persists
attempt/success state for daily dedupe and retries.

## Commands

```bash
./bin/chores status
./bin/chores history
./bin/chores run
./bin/chores install-cron
```

## Configuration

- `CHORES_TIMEZONE`: timezone used for due checks, defaults to `Europe/Paris`
- `CHORES_STATE_FILE`: JSON state file path, defaults to `.robin/chores-state.json`
- `CHORES_CODEX_INIT_COMMAND`: command for Codex initialization chore
- `ROBIN_RUN_LEDGER_DIR`: directory containing `run-ledger.jsonl`, defaults to `.robin`
- `ROBIN_LOG_RUNS_DIR`: directory containing per-run log files, defaults to `.robin/logs`
- `ROBIN_TELEGRAM_BOT_TOKEN`: optional Telegram bot token for failure alerts
- `ROBIN_TELEGRAM_CHAT_ID`: optional Telegram chat ID for failure alerts
- `ROBIN_LOG_LEVEL`: log verbosity, defaults to `info` (`debug|info|warn|error`)

Default Codex init command:

```bash
codex exec "Reply with exactly: ok"
```

## Service Logs

`run` outputs human-readable service events in this format:

`[LEVEL] [TIME] [SERVICE] [EVENT] [MESSAGE]`

- `TIME` is ISO-8601 UTC (`Z`)
- `MESSAGE` is deterministic `key=value` pairs
- `DEBUG` events are hidden unless `ROBIN_LOG_LEVEL=debug`

Each cron execution also creates:

- a `run ledger` entry in `.robin/run-ledger.jsonl`
- a dedicated `run log` file at `.robin/logs/chores/<YYYY-MM-DD>-<run_id>.log`

Use `./bin/chores history --limit 10` to inspect recent finished runs.
Add `--show-log` to print the stored log contents for those runs.

## Current Chores

- `codex-init`: runs once per day between 09:00-09:59 in configured timezone,
  then records success for the local date.
