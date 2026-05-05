from __future__ import annotations

import json
import os
import sys
from typing import Any
from urllib import error, request

NOTION_VERSION = "2022-06-28"
NOTION_BASE_URL = "https://api.notion.com/v1"


class NotionAPIError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def mask_secret(value: str | None) -> str:
    if not value:
        return "missing"
    if len(value) <= 6:
        return "***"
    return f"{value[:3]}...{value[-3:]}"


def build_status_payload(mode: str) -> dict[str, object]:
    token = os.getenv("NOTION_API_TOKEN")
    parent_page = os.getenv("NOTION_PARENT_PAGE_ID")
    return {
        "ability": "notion",
        "mode": mode,
        "connected": bool(token and parent_page),
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


def parse_invoke_input(raw_input: str) -> dict[str, Any] | None:
    if not raw_input.strip():
        return None

    try:
        payload = json.loads(raw_input)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON input: {exc.msg}") from exc

    if not isinstance(payload, dict):
        raise ValueError("Invoke input must be a JSON object")
    return payload


def infer_action_from_raw(raw_input: str) -> str:
    try:
        parsed = parse_invoke_input(raw_input)
    except ValueError:
        return "unknown"
    if not parsed:
        return "invoke"
    action = parsed.get("action")
    return action if isinstance(action, str) else "unknown"


def require_str(payload: dict[str, Any], key: str, action: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{action}: '{key}' is required and must be a non-empty string")
    return value


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


def extract_page_summary(page: dict[str, Any], property_ids: list[str] | None = None) -> dict[str, Any]:
    title = ""
    for prop in page.get("properties", {}).values():
        if isinstance(prop, dict) and prop.get("type") == "title":
            fragments = prop.get("title", [])
            if isinstance(fragments, list):
                title = "".join(
                    frag.get("plain_text", "") for frag in fragments if isinstance(frag, dict)
                )
            break

    selected: dict[str, Any] = {}
    properties = page.get("properties", {})
    if isinstance(properties, dict):
        for prop in properties.values():
            if not isinstance(prop, dict):
                continue
            prop_id = prop.get("id")
            if property_ids and prop_id not in property_ids:
                continue
            if prop_id:
                selected[str(prop_id)] = prop

    return {
        "id": page.get("id"),
        "title": title,
        "last_edited_time": page.get("last_edited_time"),
        "properties": selected,
    }


def handle_list_pages(payload: dict[str, Any], token: str) -> dict[str, Any]:
    action = "list_pages"
    database_id = require_str(payload, "database_id", action)
    mode = payload.get("mode", "summary")
    if mode not in {"summary", "full"}:
        raise ValueError(f"{action}: 'mode' must be 'summary' or 'full'")

    request_payload: dict[str, Any] = {}

    page_size = payload.get("page_size")
    if page_size is not None:
        if not isinstance(page_size, int) or page_size <= 0:
            raise ValueError(f"{action}: 'page_size' must be a positive integer")
        request_payload["page_size"] = page_size

    start_cursor = payload.get("start_cursor")
    if start_cursor is not None:
        if not isinstance(start_cursor, str) or not start_cursor.strip():
            raise ValueError(f"{action}: 'start_cursor' must be a non-empty string")
        request_payload["start_cursor"] = start_cursor

    property_ids = payload.get("property_ids")
    parsed_property_ids: list[str] | None = None
    if property_ids is not None:
        if not isinstance(property_ids, list) or not all(
            isinstance(item, str) and item.strip() for item in property_ids
        ):
            raise ValueError(f"{action}: 'property_ids' must be a list of non-empty strings")
        parsed_property_ids = property_ids

    api_response = notion_request("POST", f"/databases/{database_id}/query", token, request_payload)
    results = api_response.get("results", [])
    if not isinstance(results, list):
        raise NotionAPIError(status=502, code="invalid_response", message="Notion returned invalid list")

    output_results: list[Any]
    if mode == "full":
        output_results = results
    else:
        output_results = [extract_page_summary(page, parsed_property_ids) for page in results]

    return {
        "ok": True,
        "action": action,
        "data": {
            "results": output_results,
            "has_more": bool(api_response.get("has_more", False)),
            "next_cursor": api_response.get("next_cursor"),
        },
    }


def page_belongs_to_database(page: dict[str, Any], database_id: str) -> bool:
    parent = page.get("parent", {})
    if not isinstance(parent, dict):
        return False
    return parent.get("type") == "database_id" and parent.get("database_id") == database_id


def handle_update_page_property(payload: dict[str, Any], token: str) -> dict[str, Any]:
    action = "update_page_property"
    database_id = require_str(payload, "database_id", action)
    page_id = require_str(payload, "page_id", action)
    property_id = require_str(payload, "property_id", action)
    value = payload.get("value")

    if not isinstance(value, dict) or not value:
        raise ValueError(f"{action}: 'value' must be a non-empty object with Notion property payload")

    page = notion_request("GET", f"/pages/{page_id}", token)
    if not page_belongs_to_database(page, database_id):
        raise NotionAPIError(
            status=400,
            code="database_mismatch",
            message="Page does not belong to the provided database_id",
        )

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


def handle_invoke(token: str, raw_input: str) -> dict[str, Any]:
    parsed = parse_invoke_input(raw_input)
    if parsed is None:
        return build_status_payload("invoke")

    action = parsed.get("action")
    if not isinstance(action, str):
        raise ValueError("'action' is required and must be a string")

    if not token:
        raise NotionAPIError(
            status=400,
            code="missing_token",
            message="NOTION_API_TOKEN is required for invoke actions",
        )

    if action == "list_pages":
        return handle_list_pages(parsed, token)
    if action == "update_page_property":
        return handle_update_page_property(parsed, token)

    raise ValueError(f"Unsupported action: {action}")


def main(argv: list[str] | None = None) -> int:
    print("Notion Connector - Starting up...", file=sys.stderr)
    args = argv or sys.argv[1:]
    mode = args[0] if args else "invoke"
    if mode not in {"dev", "invoke"}:
        print(f"Unsupported mode: {mode}", file=sys.stderr)
        return 1

    if mode == "dev":
        print(json.dumps(build_status_payload(mode), indent=2))
        return 0

    token = os.getenv("NOTION_API_TOKEN")
    raw_input = sys.stdin.read()
    action = infer_action_from_raw(raw_input)

    try:
        output = handle_invoke(token or "", raw_input)
        print(json.dumps(output, indent=2))
        return 0
    except ValueError as exc:
        print(json.dumps(build_error(action, "invalid_request", str(exc), 400), indent=2))
        return 1
    except NotionAPIError as exc:
        print(json.dumps(build_error(action, exc.code, exc.message, exc.status), indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
