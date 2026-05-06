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

./bin/notion update-page-property \
  --page-id your-page-id \
  --property-id error-log-id \
  --property-type rich_text \
  --text "Error: upstream timeout"
```

If `bin/` is on your `PATH`, you can run `notion ...` directly.

When invoking through `just`, quoted multi-word values are preserved:

```bash
just notion update-page-property \
  --page-id your-page-id \
  --property-id error-log-id \
  --property-type rich_text \
  --text "hello world"
```

## Output Modes

- Default output is human-readable terminal text.
- Add `--json` to `status`, `list-pages`, `get-database-properties`, `get-page-content`, or `update-page-property` for structured output.
- `list-pages --json` returns full raw Notion page objects in `data.results`.
- `get-database-properties --json` returns raw database properties plus normalized editable property metadata (IDs, types, and options for status/select-like fields).
- `get-page-content --json` returns full page metadata and recursively expanded block content.

## Property Update Inputs

`update-page-property` uses direct property IDs and supports option and rich text updates.

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

# rich_text/text: non-empty text value
./bin/notion update-page-property \
  --page-id your-page-id \
  --property-id error-log-id \
  --property-type rich_text \
  --text "Rate limit from provider"

# rich_text/text: clear existing value
./bin/notion update-page-property \
  --page-id your-page-id \
  --property-id error-log-id \
  --property-type rich_text \
  --text ""
```

Rules:
- `status` and `select` require exactly one `--value-id` and reject `--text`.
- `multi_select` requires one or more `--value-id` and rejects `--text`.
- `rich_text` and `text` require `--text`, reject `--value-id`, allow `--text ""` to clear, and reject whitespace-only text like `"   "`.

## Notes

- In this repo, a record or row in a Notion database is called a **database page**.
