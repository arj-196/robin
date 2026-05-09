# Robin

Robin is an internal-first monorepo of agent-facing abilities. Each
ability is self-contained, directly executable, and documented in its own
folder.

## Repository Shape

```text
.
├── CONTEXT.md
├── README.md
├── .env.example
├── justfile
├── bin/
│   ├── auto-coder
│   ├── chores
│   └── notion
└── abilities/
    ├── apps/
    │   └── history-dashboard/
    ├── connectors/
    │   └── notion/
    └── services/
        ├── auto-coder/
        └── chores/
```

## Core Ideas

- `ability` is the canonical unit in this repo.
- Abilities are grouped by `type`, not by runtime.
- Discovery is filesystem-first: each ability directory carries a lightweight `ability.yaml`.
- Python abilities should expose their CLI through `Typer`.
- Usage guidance lives in per-ability `README.md` files instead of a strict repo-wide contract.

## Direct Commands

Use the checked-in shims directly:

```bash
./bin/notion --help
./bin/notion status
./bin/auto-coder status
./bin/auto-coder history
./bin/chores status
./bin/chores history
./bin/history-dashboard help
./bin/history-dashboard serve
```

If you add `bin/` to your `PATH`, the same commands can be run as:

```bash
notion --help
notion list-pages --database-id your-database-id --json
auto-coder status
auto-coder history
chores status
chores history
history-dashboard status
```

## Metadata

Each ability keeps a minimal `ability.yaml` for discovery and execution hints.
The file is intentionally lightweight and may contain only:

- `id`
- `type`
- `runtime`
- `description`
- `command`

The manifest is not a lifecycle contract. It does not define required commands,
entrypoint equality rules, or environment validation.

## Soft Conventions

Abilities may expose commands such as `install`, `dev`, `test`, or `build` when
those workflows make sense, but the repository does not require a shared command
set.

## Configuration

Local development uses a single root `.env` file for convenience.

```bash
cp .env.example .env
```

Cron runs with a minimal environment and may not include user-level install
paths. If cron cannot find tools like `uv`, set `PATH` in `.env` to the same
value you use interactively. `bin/run-with-env` treats `.env` values as
authoritative, including `PATH`.

Example:

```bash
PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
```

Cron-invoked services also support shared observability settings:

- `ROBIN_RUN_LEDGER_DIR`
- `ROBIN_LOG_RUNS_DIR`
- `ROBIN_TELEGRAM_BOT_TOKEN`
- `ROBIN_TELEGRAM_CHAT_ID`

History dashboard auth can be configured with:

- `HISTORY_DASHBOARD_AUTH_USERNAME`
- `HISTORY_DASHBOARD_AUTH_PASSWORD`

When both are set, the dashboard requires HTTP Basic Auth. If either is unset,
auth is disabled.

## Sample Abilities

- `notion`: a Python connector with a Typer CLI for inspecting status, listing
  database pages, and updating a page property.
- `history-dashboard`: a Next.js app for cross-service run history and logs.
- `auto-coder`: a Python service for Notion-driven coding automation.
- `chores`: a Python service for cron-driven scheduled operational chores.

## Notion Terminology

In this repository, a row or record in a Notion database is called a
**database page**. Older references to "item" map to the same concept.
