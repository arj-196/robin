# Notion Connector CLI Skill Guide

This guide explains how a coding agent should use the Notion connector CLI at `./bin/notion`.

## Purpose

Use this CLI to:
- check connector status
- list database pages
- fetch full page content (recursive blocks)
- inspect database property schema/options
- update page properties by option ID

## Prerequisites

- `NOTION_API_KEY` must be set for all API-backed commands.
- `NOTION_PARENT_PAGE_ID` is optional and only shown in `status`.

Example:

```bash
export NOTION_API_KEY=ntn_xxx
```

## Command Reference

### 1) `status`

Command:

```bash
./bin/notion status
./bin/notion status --json
```

JSON shape:

```json
{
  "ability": "notion",
  "connected": true,
  "workspace": {
    "parent_page_id": "optional",
    "token_preview": "ntn...abc"
  }
}
```

### 2) `list-pages`

Command:

```bash
./bin/notion list-pages --database-id <database-id>
./bin/notion list-pages --database-id <database-id> --page-size 25 --start-cursor <cursor> --json
```

Notes:
- JSON returns full raw Notion page objects in `data.results`.
- No summary/full mode toggle exists.

JSON shape:

```json
{
  "ok": true,
  "action": "list_pages",
  "data": {
    "results": [/* raw Notion pages */],
    "has_more": false,
    "next_cursor": null
  }
}
```

### 3) `get-page-content`

Command:

```bash
./bin/notion get-page-content --page-id <page-id>
./bin/notion get-page-content --page-id <page-id> --json
```

Notes:
- Fetches page metadata plus all descendant blocks recursively.
- Handles block children pagination internally.

JSON shape:

```json
{
  "ok": true,
  "action": "get_page_content",
  "data": {
    "page": {/* raw Notion page object */},
    "blocks": [/* recursive block tree; child blocks in `children` */]
  }
}
```

Human mode:
- prints `Page: <title> [<id>]`
- then renders readable block content (headings, lists, todos, quote, code, etc.)

### 4) `get-database-properties`

Command:

```bash
./bin/notion get-database-properties --database-id <database-id>
./bin/notion get-database-properties --database-id <database-id> --json
```

Use this before updates to discover:
- property IDs
- property types
- allowed option IDs for `status` / `select` / `multi_select`

JSON shape:

```json
{
  "ok": true,
  "action": "get_database_properties",
  "data": {
    "database": {
      "id": "<database-id>",
      "title": "Tasks",
      "url": "https://www.notion.so/..."
    },
    "properties_raw": {/* full raw Notion properties object */},
    "editable_properties": [
      {
        "name": "Progress",
        "property_id": "abc123",
        "type": "status",
        "options": [
          {"id": "opt1", "name": "In Progress", "color": "blue"}
        ],
        "update_hint": {"status": {"name": "<option-name>"}}
      }
    ]
  }
}
```

### 5) `update-page-property`

Command:

```bash
./bin/notion update-page-property \
  --page-id <page-id> \
  --property-id <property-id> \
  --property-type <status|select|multi_select|rich_text|text> \
  --value-id <option-id> [--value-id <option-id> ...]

./bin/notion update-page-property \
  --page-id <page-id> \
  --property-id <property-id> \
  --property-type <rich_text|text> \
  --text "<message>"

./bin/notion update-page-property \
  --page-id <page-id> \
  --property-id <property-id> \
  --property-type <rich_text|text> \
  --text ""

./bin/notion update-page-property ... --json
```

Rules:
- `--property-type` is mandatory.
- `status` and `select` require exactly one `--value-id` and reject `--text`.
- `multi_select` requires one or more `--value-id` and rejects `--text`.
- `rich_text` and `text` require `--text`, reject `--value-id`, allow `--text ""` to clear, and reject whitespace-only text like `"   "`.

JSON shape:

```json
{
  "ok": true,
  "action": "update_page_property",
  "data": {
    "page_id": "<page-id>",
    "last_edited_time": "2026-05-05T13:00:00.000Z",
    "updated_property": {
      "property_id": "<property-id>",
      "value": {/* property value returned by Notion, or submitted value fallback */}
    }
  }
}
```

## Error Handling Contract

For command failures:
- with `--json`: structured error JSON is printed
- without `--json`: a single-line human error is printed to stderr

Structured error shape:

```json
{
  "ok": false,
  "action": "<action_name>",
  "error": {
    "code": "invalid_request|missing_token|network_error|...",
    "message": "human-readable message",
    "status": 400
  }
}
```

## Recommended Agent Workflow

1. Run `get-database-properties --database-id ... --json`.
2. Find the target property by `name` and capture its `property_id`, `type`, and valid option `id`s.
3. Run `update-page-property` using `property_id`, mandatory `property_type`, and either option `value_id`(s) or `--text` for rich text.
4. If task description/body is needed, run `get-page-content --page-id ... --json`.
