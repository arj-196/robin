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
./bin/history-dashboard serve --background
```

These app and service shims use Docker by default. The first run builds the
ability image if it is missing, then runs the command in a container. Cron on
Ubuntu should call the same checked-in shims; cron remains the scheduler while
Docker is the execution engine.

If you add `bin/` to your `PATH`, the same commands can be run as:

```bash
notion --help
notion list-pages --database-id your-database-id --json
auto-coder status
auto-coder history
chores status
chores history
history-dashboard status
history-dashboard serve --background
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

Each Dockerized ability wrapper loads the root `.env` file directly. Host paths
such as `ROBIN_HOME` and `AUTO_CODER_APPS_ROOT` are resolved on the host by the
owning wrapper and mounted to stable container paths. Inside containers,
`ROBIN_HOME` is `/robin-home` and `AUTO_CODER_APPS_ROOT` is `/apps`.

The host must have Docker installed, and the cron user must be allowed to run
`docker`. Service containers mount host `~/.codex` so the Codex CLI can use the
same authentication state as the host.

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
