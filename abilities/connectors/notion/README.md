# Notion Connector Ability

This ability exposes Notion as a direct `Typer` CLI for Hermes.

## Prerequisites

Set these in your root `.env`:

```bash
NOTION_API_KEY=secret_...
NOTION_PARENT_PAGE_ID=optional-legacy-value
```

`NOTION_API_KEY` is required for API-backed commands.

## Commands

```bash
./bin/notion --help
./bin/notion status
./bin/notion list-pages --database-id your-database-id
./bin/notion list-pages --database-id your-database-id --json
./bin/notion get-database-properties --database-id your-database-id --json
./bin/notion get-page-content --page-id your-page-id --json
./bin/notion update-page-property \
  --page-id your-page-id \
  --property-id status-id \
  --property-type status \
  --value-id done-option-id
```

If `bin/` is on your `PATH`, you can run `notion ...` directly.

## Output Modes

- Default output is human-readable terminal text.
- Add `--json` to `status`, `list-pages`, `get-database-properties`, `get-page-content`, or `update-page-property` for structured output.
- `list-pages --json` returns full raw Notion page objects in `data.results`.
- `get-database-properties --json` returns raw database properties plus normalized editable property metadata (IDs, types, and options for status/select-like fields).
- `get-page-content --json` returns full page metadata and recursively expanded block content.

## Property Update Inputs

`update-page-property` uses direct option IDs.

Examples:

```bash
# status/select: exactly one value ID
./bin/notion update-page-property \
  --page-id your-page-id \
  --property-id status-id \
  --property-type status \
  --value-id done-option-id

# multi_select: one or more value IDs
./bin/notion update-page-property \
  --page-id your-page-id \
  --property-id tags-id \
  --property-type multi_select \
  --value-id tag-option-id-1 \
  --value-id tag-option-id-2
```

## Notes

- In this repo, a record or row in a Notion database is called a **database page**.
