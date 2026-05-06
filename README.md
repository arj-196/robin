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
│   ├── dashboard
│   └── notion
└── abilities/
    ├── apps/
    │   └── dashboard/
    ├── connectors/
    │   └── notion/
    └── services/
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
./bin/dashboard help
./bin/dashboard serve
```

If you add `bin/` to your `PATH`, the same commands can be run as:

```bash
notion --help
notion list-pages --database-id your-database-id --json
dashboard status
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

## Sample Abilities

- `notion`: a Python connector with a Typer CLI for inspecting status, listing
  database pages, and updating a page property.
- `dashboard`: a TypeScript app with direct `status` and `serve` commands.

## Notion Terminology

In this repository, a row or record in a Notion database is called a
**database page**. Older references to "item" map to the same concept.
