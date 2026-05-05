# Notion Connector Ability

This ability lets Hermes interact with Notion database pages.

## What It Does

- List pages from a Notion database.
- Update one property on a specific database page.

In this repo, a record/row in a Notion database is called a **database page**.

## Prerequisites

Set these in your root `.env`:

```bash
NOTION_API_TOKEN=secret_...
NOTION_PARENT_PAGE_ID=optional-legacy-value
```

`NOTION_API_TOKEN` is required for actionable `invoke` requests.

## Run Modes

- `dev`: prints connector status payload.
- `invoke`: reads JSON from `stdin` and returns JSON to `stdout`.

Examples:

```bash
uv run --project abilities/connectors/notion python abilities/connectors/notion/src/main.py dev
uv run --project abilities/connectors/notion python abilities/connectors/notion/src/main.py invoke
```

Or via control plane:

```bash
uv run --with pyyaml python abilityctl.py run notion invoke
```

## Invoke Contract

Input is a JSON object with an `action` field.

### 1) `list_pages`

Request:

```json
{
  "action": "list_pages",
  "database_id": "<notion_database_id>",
  "mode": "summary",
  "page_size": 10,
  "start_cursor": "optional-cursor",
  "property_ids": ["status-id", "owner-id"]
}
```

Fields:

- `database_id` (required): target Notion database.
- `mode` (optional): `summary` or `full` (default: `summary`).
- `page_size` (optional): positive integer.
- `start_cursor` (optional): pagination cursor.
- `property_ids` (optional): property IDs to include in summary mode.

Response:

```json
{
  "ok": true,
  "action": "list_pages",
  "data": {
    "results": [],
    "has_more": false,
    "next_cursor": null
  }
}
```

### 2) `update_page_property`

Request:

```json
{
  "action": "update_page_property",
  "database_id": "<notion_database_id>",
  "page_id": "<notion_page_id>",
  "property_id": "status-id",
  "value": {
    "status": { "name": "Done" }
  }
}
```

Fields:

- `database_id` (required): used to verify page belongs to expected database.
- `page_id` (required): page to update.
- `property_id` (required): canonical Notion property ID.
- `value` (required): raw Notion property payload.

Response:

```json
{
  "ok": true,
  "action": "update_page_property",
  "data": {
    "page_id": "...",
    "last_edited_time": "...",
    "updated_property": {
      "property_id": "status-id",
      "value": {}
    }
  }
}
```

## Error Envelope

Errors use a standard shape:

```json
{
  "ok": false,
  "action": "list_pages",
  "error": {
    "code": "invalid_request",
    "message": "...",
    "status": 400
  }
}
```

Common error codes:

- `invalid_request`
- `missing_token`
- `database_mismatch`
- Notion API upstream codes (for example auth/validation failures)

## CLI Examples

List pages:

```bash
cat <<'JSON' | uv run --project abilities/connectors/notion python abilities/connectors/notion/src/main.py invoke
{
  "action": "list_pages",
  "database_id": "your-database-id",
  "mode": "summary",
  "page_size": 5
}
JSON
```

Update one property:

```bash
cat <<'JSON' | uv run --project abilities/connectors/notion python abilities/connectors/notion/src/main.py invoke
{
  "action": "update_page_property",
  "database_id": "your-database-id",
  "page_id": "your-page-id",
  "property_id": "status-id",
  "value": {
    "status": { "name": "In Progress" }
  }
}
JSON
```
