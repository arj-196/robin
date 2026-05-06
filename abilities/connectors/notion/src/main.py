from __future__ import annotations

import json
import os
from typing import Any
from urllib import error, request

import typer

NOTION_VERSION = "2022-06-28"
NOTION_BASE_URL = "https://api.notion.com/v1"

app = typer.Typer(help="Direct CLI for the Hermes Notion connector.", no_args_is_help=True)


class NotionAPIError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


class InvalidRequestError(ValueError):
    def __init__(self, action: str, message: str) -> None:
        super().__init__(message)
        self.action = action


def mask_secret(value: str | None) -> str:
    if not value:
        return "missing"
    if len(value) <= 6:
        return "***"
    return f"{value[:3]}...{value[-3:]}"


def build_status_payload() -> dict[str, object]:
    token = os.getenv("NOTION_API_KEY")
    parent_page = os.getenv("NOTION_PARENT_PAGE_ID")
    return {
        "ability": "notion",
        "connected": bool(token),
        "workspace": {
            "parent_page_id": parent_page or "missing",
            "token_preview": mask_secret(token),
        },
    }


def build_error(action: str, code: str, message: str, status: int = 400) -> dict[str, Any]:
    return {
        "ok": False,
        "action": action,
        "error": {
            "code": code,
            "message": message,
            "status": status,
        },
    }


def notion_request(
    method: str,
    path: str,
    token: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{NOTION_BASE_URL}{path}"
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    req = request.Request(url=url, method=method, data=body)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Notion-Version", NOTION_VERSION)
    req.add_header("Content-Type", "application/json")

    try:
        with request.urlopen(req, timeout=30) as response:
            data = response.read().decode("utf-8")
            return json.loads(data) if data else {}
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {}

        raise NotionAPIError(
            status=exc.code,
            code=str(parsed.get("code") or "http_error"),
            message=str(parsed.get("message") or raw or "Notion API request failed"),
        ) from exc
    except error.URLError as exc:
        raise NotionAPIError(status=503, code="network_error", message=str(exc.reason)) from exc


def extract_page_title(page: dict[str, Any]) -> str:
    title = ""
    for prop in page.get("properties", {}).values():
        if isinstance(prop, dict) and prop.get("type") == "title":
            fragments = prop.get("title", [])
            if isinstance(fragments, list):
                title = "".join(
                    frag.get("plain_text", "") for frag in fragments if isinstance(frag, dict)
                )
            break
    return title

def require_token(action: str) -> str:
    token = os.getenv("NOTION_API_KEY", "").strip()
    if not token:
        raise NotionAPIError(
            status=400,
            code="missing_token",
            message=f"NOTION_API_KEY is required for {action}.",
        )
    return token


def list_pages(
    token: str,
    database_id: str,
    page_size: int | None = None,
    start_cursor: str | None = None,
) -> dict[str, Any]:
    action = "list_pages"
    if page_size is not None and page_size <= 0:
        raise InvalidRequestError(action, "'page_size' must be a positive integer")
    if start_cursor is not None and not start_cursor.strip():
        raise InvalidRequestError(action, "'start_cursor' must be a non-empty string")

    request_payload: dict[str, Any] = {}
    if page_size is not None:
        request_payload["page_size"] = page_size
    if start_cursor is not None:
        request_payload["start_cursor"] = start_cursor

    api_response = notion_request("POST", f"/databases/{database_id}/query", token, request_payload)
    results = api_response.get("results", [])
    if not isinstance(results, list):
        raise NotionAPIError(status=502, code="invalid_response", message="Notion returned invalid list")

    return {
        "ok": True,
        "action": action,
        "data": {
            "results": results,
            "has_more": bool(api_response.get("has_more", False)),
            "next_cursor": api_response.get("next_cursor"),
        },
    }


def list_block_children(token: str, block_id: str) -> list[dict[str, Any]]:
    all_results: list[dict[str, Any]] = []
    start_cursor: str | None = None

    while True:
        path = f"/blocks/{block_id}/children"
        if start_cursor:
            path = f"{path}?start_cursor={start_cursor}"
        response = notion_request("GET", path, token)
        results = response.get("results", [])
        if not isinstance(results, list):
            raise NotionAPIError(
                status=502,
                code="invalid_response",
                message="Notion returned invalid block children list",
            )
        all_results.extend(result for result in results if isinstance(result, dict))
        if not response.get("has_more"):
            break
        next_cursor = response.get("next_cursor")
        if not isinstance(next_cursor, str) or not next_cursor:
            raise NotionAPIError(
                status=502,
                code="invalid_response",
                message="Notion returned invalid next_cursor for block pagination",
            )
        start_cursor = next_cursor

    return all_results


def expand_blocks_recursive(token: str, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    for block in blocks:
        block_copy = dict(block)
        if bool(block_copy.get("has_children")) and isinstance(block_copy.get("id"), str):
            children = list_block_children(token, block_copy["id"])
            block_copy["children"] = expand_blocks_recursive(token, children)
        expanded.append(block_copy)
    return expanded


def get_page_content(token: str, page_id: str) -> dict[str, Any]:
    action = "get_page_content"
    if not page_id.strip():
        raise InvalidRequestError(action, "'page_id' must be a non-empty string")

    page = notion_request("GET", f"/pages/{page_id}", token)
    root_blocks = list_block_children(token, page_id)
    blocks = expand_blocks_recursive(token, root_blocks)

    return {
        "ok": True,
        "action": action,
        "data": {
            "page": page,
            "blocks": blocks,
        },
    }


def normalize_database_property(name: str, prop: dict[str, Any]) -> dict[str, Any]:
    prop_type = prop.get("type")
    prop_id = prop.get("id")
    normalized: dict[str, Any] = {
        "name": name,
        "property_id": prop_id if isinstance(prop_id, str) else None,
        "type": prop_type if isinstance(prop_type, str) else "unknown",
        "options": [],
        "update_hint": "Use Notion property payload shape for this type, e.g. {'<type>': ...}",
    }

    if isinstance(prop_type, str) and prop_type in {"status", "select", "multi_select"}:
        option_container = prop.get(prop_type, {})
        options = option_container.get("options", []) if isinstance(option_container, dict) else []
        normalized_options: list[dict[str, Any]] = []
        if isinstance(options, list):
            for option in options:
                if not isinstance(option, dict):
                    continue
                normalized_options.append(
                    {
                        "id": option.get("id"),
                        "name": option.get("name"),
                        "color": option.get("color"),
                    }
                )
        normalized["options"] = normalized_options

        if prop_type == "status":
            normalized["update_hint"] = {"status": {"name": "<option-name>"}}
        elif prop_type == "select":
            normalized["update_hint"] = {"select": {"name": "<option-name>"}}
        else:
            normalized["update_hint"] = {"multi_select": [{"name": "<option-name>"}]}

    return normalized


def extract_database_title(database: dict[str, Any]) -> str:
    title_parts = database.get("title", [])
    return extract_rich_text_plain_text(title_parts)


def get_database_properties(token: str, database_id: str) -> dict[str, Any]:
    action = "get_database_properties"
    if not database_id.strip():
        raise InvalidRequestError(action, "'database_id' must be a non-empty string")

    database = notion_request("GET", f"/databases/{database_id}", token)
    properties = database.get("properties")
    if not isinstance(properties, dict):
        raise NotionAPIError(
            status=502,
            code="invalid_response",
            message="Notion returned invalid database properties",
        )

    editable_properties: list[dict[str, Any]] = []
    for prop_name, prop in properties.items():
        if isinstance(prop_name, str) and isinstance(prop, dict):
            editable_properties.append(normalize_database_property(prop_name, prop))

    return {
        "ok": True,
        "action": action,
        "data": {
            "database": {
                "id": database.get("id"),
                "title": extract_database_title(database),
                "url": database.get("url"),
            },
            "properties_raw": properties,
            "editable_properties": editable_properties,
        },
    }


def update_page_property(
    token: str,
    page_id: str,
    property_id: str,
    value: dict[str, Any],
) -> dict[str, Any]:
    action = "update_page_property"
    if not value:
        raise InvalidRequestError(action, "'value' must be a non-empty JSON object")

    update_payload = {"properties": {property_id: value}}
    updated_page = notion_request("PATCH", f"/pages/{page_id}", token, update_payload)

    return {
        "ok": True,
        "action": action,
        "data": {
            "page_id": updated_page.get("id"),
            "last_edited_time": updated_page.get("last_edited_time"),
            "updated_property": {
                "property_id": property_id,
                "value": updated_page.get("properties", {}).get(property_id, value),
            },
        },
    }


def build_option_property_value(
    action: str,
    property_type: str,
    value_ids: list[str],
    text: str | None = None,
) -> dict[str, Any]:
    normalized_type = property_type.strip().lower()
    clean_value_ids = [value_id.strip() for value_id in value_ids if value_id.strip()]
    has_text_argument = text is not None
    clean_text = text.strip() if isinstance(text, str) else ""

    if normalized_type in {"status", "select"}:
        if clean_text:
            raise InvalidRequestError(
                action,
                f"'--text' is not allowed when '--property-type {normalized_type}' is used",
            )
        if len(clean_value_ids) != 1:
            raise InvalidRequestError(
                action,
                f"'{normalized_type}' requires exactly one '--value-id'",
            )
        return {normalized_type: {"id": clean_value_ids[0]}}

    if normalized_type == "multi_select":
        if clean_text:
            raise InvalidRequestError(
                action,
                "'--text' is not allowed when '--property-type multi_select' is used",
            )
        if not clean_value_ids:
            raise InvalidRequestError(action, "'multi_select' requires at least one '--value-id'")
        return {"multi_select": [{"id": value_id} for value_id in clean_value_ids]}

    if normalized_type in {"rich_text", "text"}:
        if clean_value_ids:
            raise InvalidRequestError(
                action,
                f"'--value-id' is not allowed when '--property-type {normalized_type}' is used",
            )
        if not has_text_argument:
            raise InvalidRequestError(
                action,
                f"'{normalized_type}' requires '--text' (use '--text \"\"' to clear)",
            )
        if text == "":
            return {"rich_text": []}
        if not clean_text:
            raise InvalidRequestError(
                action,
                f"'{normalized_type}' does not allow whitespace-only '--text' (use '--text \"\"' to clear)",
            )
        return {"rich_text": [{"type": "text", "text": {"content": clean_text}}]}

    raise InvalidRequestError(
        action,
        "'property_type' must be one of: status, select, multi_select, rich_text, text",
    )


def emit_json(payload: dict[str, Any]) -> None:
    typer.echo(json.dumps(payload, indent=2))


def emit_human_status(payload: dict[str, Any]) -> None:
    workspace = payload["workspace"]
    typer.echo("Notion connector status")
    typer.echo(f"Connected: {'yes' if payload['connected'] else 'no'}")
    typer.echo(f"Token: {workspace['token_preview']}")
    typer.echo(f"Parent page: {workspace['parent_page_id']}")


def emit_human_list(payload: dict[str, Any]) -> None:
    results = payload["data"]["results"]
    typer.echo(f"Found {len(results)} database page(s)")
    for page in results:
        title = extract_page_title(page) or "untitled"
        page_id = page.get("id", "unknown")
        typer.echo(f"- {title} [{page_id}]")
    typer.echo(f"Has more: {'yes' if payload['data']['has_more'] else 'no'}")
    next_cursor = payload["data"]["next_cursor"]
    if next_cursor:
        typer.echo(f"Next cursor: {next_cursor}")


def emit_human_update(payload: dict[str, Any]) -> None:
    data = payload["data"]
    typer.echo(f"Updated property {data['updated_property']['property_id']} on page {data['page_id']}")
    typer.echo(f"Last edited: {data['last_edited_time']}")


def emit_human_database_properties(payload: dict[str, Any]) -> None:
    data = payload["data"]
    database = data["database"]
    title = database.get("title") or "untitled database"
    database_id = database.get("id", "unknown")
    typer.echo(f"Database: {title} [{database_id}]")
    properties = data.get("editable_properties", [])
    if not properties:
        typer.echo("[no properties]")
        return

    for prop in properties:
        name = prop.get("name", "unknown")
        prop_type = prop.get("type", "unknown")
        prop_id = prop.get("property_id", "unknown")
        typer.echo(f"- {name} ({prop_type}) [{prop_id}]")
        options = prop.get("options", [])
        if isinstance(options, list) and options:
            for option in options:
                option_name = option.get("name", "unknown")
                option_id = option.get("id", "unknown")
                typer.echo(f"  - option: {option_name} [{option_id}]")


def extract_rich_text_plain_text(rich_text: Any) -> str:
    if not isinstance(rich_text, list):
        return ""
    fragments: list[str] = []
    for item in rich_text:
        if isinstance(item, dict):
            text = item.get("plain_text")
            if isinstance(text, str):
                fragments.append(text)
    return "".join(fragments)


def render_blocks(blocks: list[dict[str, Any]], indent: int = 0, numbered_index: int = 1) -> list[str]:
    lines: list[str] = []
    current_number = numbered_index

    for block in blocks:
        block_type = block.get("type")
        if not isinstance(block_type, str):
            continue

        nested_indent = indent + 1
        line_prefix = "  " * indent
        content = block.get(block_type, {})
        if not isinstance(content, dict):
            content = {}

        block_lines: list[str] = []
        if block_type == "paragraph":
            text = extract_rich_text_plain_text(content.get("rich_text"))
            block_lines.append(f"{line_prefix}{text}" if text else f"{line_prefix}[empty:paragraph]")
        elif block_type == "heading_1":
            text = extract_rich_text_plain_text(content.get("rich_text"))
            block_lines.append(f"{line_prefix}# {text}" if text else f"{line_prefix}# [empty]")
        elif block_type == "heading_2":
            text = extract_rich_text_plain_text(content.get("rich_text"))
            block_lines.append(f"{line_prefix}## {text}" if text else f"{line_prefix}## [empty]")
        elif block_type == "heading_3":
            text = extract_rich_text_plain_text(content.get("rich_text"))
            block_lines.append(f"{line_prefix}### {text}" if text else f"{line_prefix}### [empty]")
        elif block_type == "bulleted_list_item":
            text = extract_rich_text_plain_text(content.get("rich_text"))
            block_lines.append(f"{line_prefix}- {text}" if text else f"{line_prefix}- [empty]")
        elif block_type == "numbered_list_item":
            text = extract_rich_text_plain_text(content.get("rich_text"))
            block_lines.append(f"{line_prefix}{current_number}. {text}" if text else f"{line_prefix}{current_number}. [empty]")
            current_number += 1
        elif block_type == "to_do":
            text = extract_rich_text_plain_text(content.get("rich_text"))
            checked = bool(content.get("checked"))
            marker = "[x]" if checked else "[ ]"
            block_lines.append(f"{line_prefix}{marker} {text}" if text else f"{line_prefix}{marker} [empty]")
        elif block_type == "toggle":
            text = extract_rich_text_plain_text(content.get("rich_text"))
            block_lines.append(f"{line_prefix}> {text}" if text else f"{line_prefix}> [empty]")
        elif block_type == "quote":
            text = extract_rich_text_plain_text(content.get("rich_text"))
            block_lines.append(f"{line_prefix}> {text}" if text else f"{line_prefix}> [empty]")
        elif block_type == "code":
            text = extract_rich_text_plain_text(content.get("rich_text"))
            language = content.get("language")
            language_str = language if isinstance(language, str) else "plain text"
            block_lines.append(f"{line_prefix}```{language_str}")
            if text:
                for code_line in text.splitlines():
                    block_lines.append(f"{line_prefix}{code_line}")
            else:
                block_lines.append(f"{line_prefix}[empty]")
            block_lines.append(f"{line_prefix}```")
        elif block_type == "callout":
            text = extract_rich_text_plain_text(content.get("rich_text"))
            icon = content.get("icon")
            icon_text = "!"
            if isinstance(icon, dict):
                if icon.get("type") == "emoji" and isinstance(icon.get("emoji"), str):
                    icon_text = icon["emoji"]
            block_lines.append(f"{line_prefix}{icon_text} {text}" if text else f"{line_prefix}{icon_text} [empty]")
        elif block_type == "divider":
            block_lines.append(f"{line_prefix}{'-' * 24}")
        else:
            block_lines.append(f"{line_prefix}[unsupported:{block_type}]")

        lines.extend(block_lines)

        children = block.get("children")
        if isinstance(children, list):
            typed_children = [child for child in children if isinstance(child, dict)]
            lines.extend(render_blocks(typed_children, indent=nested_indent))

    return lines


def emit_human_page_content(payload: dict[str, Any]) -> None:
    page = payload["data"]["page"]
    blocks = payload["data"]["blocks"]
    title = extract_page_title(page) or "untitled"
    page_id = page.get("id", "unknown")
    typer.echo(f"Page: {title} [{page_id}]")
    typer.echo("")
    rendered_lines = render_blocks(blocks)
    if not rendered_lines:
        typer.echo("[no content]")
        return
    for line in rendered_lines:
        typer.echo(line)


def exit_with_error(action: str, exc: Exception, json_output: bool) -> None:
    if isinstance(exc, NotionAPIError):
        payload = build_error(action, exc.code, exc.message, exc.status)
    elif isinstance(exc, InvalidRequestError):
        payload = build_error(exc.action, "invalid_request", str(exc), 400)
    else:
        payload = build_error(action, "invalid_request", str(exc), 400)

    if json_output:
        emit_json(payload)
    else:
        typer.echo(f"{payload['error']['code']}: {payload['error']['message']}", err=True)
    raise typer.Exit(code=1)


@app.command("status")
def status(json_output: bool = typer.Option(False, "--json", help="Emit structured JSON.")) -> None:
    payload = build_status_payload()
    if json_output:
        emit_json(payload)
        return
    emit_human_status(payload)


@app.command("list-pages")
def list_pages_command(
    database_id: str = typer.Option(..., "--database-id", help="Target Notion database ID."),
    page_size: int | None = typer.Option(None, "--page-size", help="Limit the number of results."),
    start_cursor: str | None = typer.Option(None, "--start-cursor", help="Pagination cursor."),
    json_output: bool = typer.Option(False, "--json", help="Emit structured JSON."),
) -> None:
    try:
        payload = list_pages(
            token=require_token("list-pages"),
            database_id=database_id,
            page_size=page_size,
            start_cursor=start_cursor,
        )
    except (InvalidRequestError, NotionAPIError) as exc:
        exit_with_error("list_pages", exc, json_output)

    if json_output:
        emit_json(payload)
        return
    emit_human_list(payload)


@app.command("get-page-content")
def get_page_content_command(
    page_id: str = typer.Option(..., "--page-id", help="Target page ID."),
    json_output: bool = typer.Option(False, "--json", help="Emit structured JSON."),
) -> None:
    try:
        payload = get_page_content(
            token=require_token("get-page-content"),
            page_id=page_id,
        )
    except (InvalidRequestError, NotionAPIError) as exc:
        exit_with_error("get_page_content", exc, json_output)

    if json_output:
        emit_json(payload)
        return
    emit_human_page_content(payload)


@app.command("get-database-properties")
def get_database_properties_command(
    database_id: str = typer.Option(..., "--database-id", help="Target Notion database ID."),
    json_output: bool = typer.Option(False, "--json", help="Emit structured JSON."),
) -> None:
    try:
        payload = get_database_properties(
            token=require_token("get-database-properties"),
            database_id=database_id,
        )
    except (InvalidRequestError, NotionAPIError) as exc:
        exit_with_error("get_database_properties", exc, json_output)

    if json_output:
        emit_json(payload)
        return
    emit_human_database_properties(payload)


@app.command("update-page-property")
def update_page_property_command(
    page_id: str = typer.Option(..., "--page-id", help="Target page ID."),
    property_id: str = typer.Option(..., "--property-id", help="Property ID to update."),
    property_type: str = typer.Option(
        ...,
        "--property-type",
        help="Property type: status, select, multi_select, rich_text, or text.",
    ),
    value_ids: list[str] = typer.Option([], "--value-id", help="Option ID value. Repeat for multi_select."),
    text: str | None = typer.Option(None, "--text", help="Text content for rich_text/text properties."),
    json_output: bool = typer.Option(False, "--json", help="Emit structured JSON."),
) -> None:
    action = "update_page_property"
    try:
        value = build_option_property_value(action, property_type, value_ids, text=text)
        payload = update_page_property(
            token=require_token("update-page-property"),
            page_id=page_id,
            property_id=property_id,
            value=value,
        )
    except (InvalidRequestError, NotionAPIError) as exc:
        exit_with_error(action, exc, json_output)

    if json_output:
        emit_json(payload)
        return
    emit_human_update(payload)


if __name__ == "__main__":
    app(prog_name="notion")
