# Hermes Tools

Hermes Tools is an internal-first monorepo of agent-facing abilities. Each
ability is a discoverable unit that Hermes can invoke through a manifest-backed
CLI contract.

## Repository Shape

```text
.
├── CONTEXT.md
├── README.md
├── .env.example
├── ability-registry.yaml
├── abilityctl.py
├── justfile
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
- Python and TypeScript are both first-class runtimes.
- Every ability is discoverable through `ability-registry.yaml`.
- Every ability declares its contract in a local `ability.yaml`.

## Standard Lifecycle

Each ability exposes the same high-level commands:

- `install`
- `dev`
- `test`
- `build` when relevant
- `invoke`

Use the shared control script directly:

```bash
uv run --with pyyaml python abilityctl.py list
uv run --with pyyaml python abilityctl.py validate
uv run --with pyyaml python abilityctl.py run notion install
uv run --with pyyaml python abilityctl.py run dashboard invoke
```

Or through `just` if it is installed locally:

```bash
just list
just validate
just install notion
just invoke dashboard
```

## Configuration

Local development uses a single root `.env` file for convenience. Each ability
must explicitly declare the environment variables it consumes in its
`ability.yaml`.

Start from:

```bash
cp .env.example .env
```

## Sample Abilities

- `notion`: a Python connector with JSON-over-stdin `invoke` actions for Notion
  database pages, including listing pages from a database and updating a
  specific page property by `property_id`.
- `dashboard`: a TypeScript app stub that exposes a minimal HTTP dashboard and
  CLI invocation surface.

## Notion Terminology

In this repository, a row/record in a Notion database is called a
**database page**. Older references to "item" map to the same concept.
