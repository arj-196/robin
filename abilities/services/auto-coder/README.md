# Auto-coder Service

The auto-coder service is a single-run worker intended to be called by cron.
Each run claims at most one Notion task, delegates repository edits to Codex,
and completes the git workflow when Codex reports successful verification.

## Commands

```bash
./bin/auto-coder status
./bin/auto-coder run
./bin/auto-coder install-cron
```

## Required Environment

- `NOTION_API_KEY`: required by `./bin/notion`
- `NOTION_TASK_DATABASE_ID`: Notion task database
- `APPS_ROOT`: root directory containing target repositories, defaults to `~/apps`

Optional field-name configuration:

- `AUTO_CODER_STATUS_PROPERTY`, defaults to `Status`
- `AUTO_CODER_PROJECT_PROPERTY`, defaults to `Project`
- `AUTO_CODER_ERROR_LOG_PROPERTY`, defaults to `Error Log`
- `AUTO_CODER_CODEX_MODEL`, defaults to `gpt-5.3-codex`
- `AUTO_CODER_GIT_COMPLETION_MODE`, defaults to `auto_merge_main`
- `OPENROUTER_API_KEY`, used to generate diff-aware commit messages
- `AUTO_CODER_COMMIT_MODEL`, defaults to `openrouter/gpt-oss-120b`
- `AUTO_CODER_COMMIT_MAX_CONTEXT_TOKENS`, defaults to `16000`
- `ROBIN_LOG_LEVEL`, defaults to `info` (`debug|info|warn|error`)

## Service Logs

`run` outputs human-readable service events in this format:

`[LEVEL] [TIME] [SERVICE] [EVENT] [MESSAGE]`

- `TIME` is ISO-8601 UTC (`Z`)
- `MESSAGE` is deterministic `key=value` pairs
- `DEBUG` events are hidden unless `ROBIN_LOG_LEVEL=debug`

## Task Format

The Notion page body must contain these headings:

- `Task`
- `Acceptance Criteria`
- `Verification`

Tasks missing any required section are marked `Blocked` with
`insufficient_spec`.

## Safety Boundary

The service resolves `Project` to `APPS_ROOT/<Project>`, rejects paths that
escape `APPS_ROOT`, requires a clean local `main` branch, and invokes Codex with
`--sandbox workspace-write`. For this POC, Codex's reported verification is
trusted; the service does not rerun verification commands.
