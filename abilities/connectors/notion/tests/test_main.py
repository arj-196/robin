from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from typer.testing import CliRunner

from abilities.connectors.notion.src import main


class NotionAbilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()

    def test_mask_secret_handles_missing_value(self) -> None:
        self.assertEqual(main.mask_secret(None), "missing")

    def test_status_payload_exposes_ability_name(self) -> None:
        payload = main.build_status_payload()
        self.assertEqual(payload["ability"], "notion")

    def test_extract_rich_text_plain_text(self) -> None:
        self.assertEqual(
            main.extract_rich_text_plain_text(
                [
                    {"plain_text": "Add "},
                    {"plain_text": "commit hash"},
                ]
            ),
            "Add commit hash",
        )

    def test_render_blocks_formats_multiple_types(self) -> None:
        blocks = [
            {"type": "heading_1", "heading_1": {"rich_text": [{"plain_text": "Task"}]}},
            {
                "type": "to_do",
                "to_do": {"rich_text": [{"plain_text": "Ship it"}], "checked": True},
            },
            {
                "type": "numbered_list_item",
                "numbered_list_item": {"rich_text": [{"plain_text": "First"}]},
            },
            {
                "type": "numbered_list_item",
                "numbered_list_item": {"rich_text": [{"plain_text": "Second"}]},
            },
            {
                "type": "quote",
                "quote": {"rich_text": [{"plain_text": "Remember context"}]},
            },
            {
                "type": "code",
                "code": {
                    "language": "python",
                    "rich_text": [{"plain_text": "print('ok')"}],
                },
            },
            {"type": "divider", "divider": {}},
            {"type": "mystery_type", "mystery_type": {}},
        ]

        rendered = main.render_blocks(blocks)

        self.assertIn("# Task", rendered)
        self.assertIn("[x] Ship it", rendered)
        self.assertIn("1. First", rendered)
        self.assertIn("2. Second", rendered)
        self.assertIn("> Remember context", rendered)
        self.assertIn("```python", rendered)
        self.assertIn("print('ok')", rendered)
        self.assertIn("------------------------", rendered)
        self.assertIn("[unsupported:mystery_type]", rendered)

    def test_render_blocks_nested_indentation(self) -> None:
        blocks = [
            {
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [{"plain_text": "Parent"}]},
                "children": [
                    {
                        "type": "to_do",
                        "to_do": {"rich_text": [{"plain_text": "Child"}], "checked": False},
                    }
                ],
            }
        ]

        rendered = main.render_blocks(blocks)
        self.assertIn("- Parent", rendered)
        self.assertIn("  [ ] Child", rendered)

    def test_normalize_database_property_status(self) -> None:
        normalized = main.normalize_database_property(
            "Progress",
            {
                "id": "progress-id",
                "type": "status",
                "status": {
                    "options": [
                        {"id": "opt-1", "name": "Not Started", "color": "gray"},
                        {"id": "opt-2", "name": "Done", "color": "green"},
                    ]
                },
            },
        )

        self.assertEqual(normalized["name"], "Progress")
        self.assertEqual(normalized["property_id"], "progress-id")
        self.assertEqual(normalized["type"], "status")
        self.assertEqual(len(normalized["options"]), 2)
        self.assertEqual(normalized["options"][0]["id"], "opt-1")
        self.assertEqual(normalized["update_hint"], {"status": {"name": "<option-name>"}})

    @patch("abilities.connectors.notion.src.main.notion_request")
    def test_get_database_properties_success(self, mock_notion_request) -> None:
        mock_notion_request.return_value = {
            "id": "db1",
            "url": "https://notion.so/db1",
            "title": [{"plain_text": "Tasks"}],
            "properties": {
                "Progress": {
                    "id": "progress-id",
                    "type": "status",
                    "status": {
                        "options": [
                            {"id": "s1", "name": "Backlog", "color": "gray"},
                            {"id": "s2", "name": "Done", "color": "green"},
                        ]
                    },
                },
                "Estimate": {
                    "id": "est-id",
                    "type": "number",
                    "number": {"format": "number"},
                },
            },
        }

        payload = main.get_database_properties("token", "db1")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["action"], "get_database_properties")
        self.assertEqual(payload["data"]["database"]["id"], "db1")
        self.assertEqual(payload["data"]["database"]["title"], "Tasks")
        self.assertIn("Progress", payload["data"]["properties_raw"])
        editable = payload["data"]["editable_properties"]
        self.assertEqual(len(editable), 2)
        progress = next(item for item in editable if item["name"] == "Progress")
        self.assertEqual(progress["property_id"], "progress-id")
        self.assertEqual(progress["options"][0]["id"], "s1")

    @patch("abilities.connectors.notion.src.main.notion_request")
    def test_get_database_properties_invalid_properties_shape(self, mock_notion_request) -> None:
        mock_notion_request.return_value = {
            "id": "db1",
            "properties": [],
        }

        with self.assertRaises(main.NotionAPIError) as ctx:
            main.get_database_properties("token", "db1")

        self.assertEqual(ctx.exception.code, "invalid_response")

    @patch("abilities.connectors.notion.src.main.notion_request")
    def test_list_pages_returns_raw_pages(self, mock_notion_request) -> None:
        raw_page = {"id": "page-raw", "properties": {"A": {"id": "a"}}}
        mock_notion_request.return_value = {
            "results": [raw_page],
            "has_more": False,
            "next_cursor": None,
        }

        response = main.list_pages("token", "db1")

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["results"][0], raw_page)

    @patch("abilities.connectors.notion.src.main.notion_request")
    def test_update_page_property_success(self, mock_notion_request) -> None:
        mock_notion_request.return_value = {
            "id": "page-1",
            "last_edited_time": "2026-05-05T13:00:00.000Z",
            "properties": {
                "status-id": {
                    "id": "status-id",
                    "type": "status",
                    "status": {"id": "done-id"},
                }
            },
        }

        response = main.update_page_property(
            "token",
            "page-1",
            "status-id",
            {"status": {"id": "done-id"}},
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["action"], "update_page_property")
        self.assertEqual(response["data"]["page_id"], "page-1")
        self.assertEqual(response["data"]["updated_property"]["property_id"], "status-id")

    def test_build_option_property_value_status(self) -> None:
        value = main.build_option_property_value("update_page_property", "status", ["opt-1"])
        self.assertEqual(value, {"status": {"id": "opt-1"}})

    def test_build_option_property_value_select(self) -> None:
        value = main.build_option_property_value("update_page_property", "select", ["opt-1"])
        self.assertEqual(value, {"select": {"id": "opt-1"}})

    def test_build_option_property_value_multi_select(self) -> None:
        value = main.build_option_property_value("update_page_property", "multi_select", ["opt-1", "opt-2"])
        self.assertEqual(value, {"multi_select": [{"id": "opt-1"}, {"id": "opt-2"}]})

    def test_build_option_property_value_rich_text(self) -> None:
        value = main.build_option_property_value(
            "update_page_property",
            "rich_text",
            [],
            text="error details",
        )
        self.assertEqual(
            value,
            {"rich_text": [{"type": "text", "text": {"content": "error details"}}]},
        )

    def test_build_option_property_value_text_alias(self) -> None:
        value = main.build_option_property_value(
            "update_page_property",
            "text",
            [],
            text="error details",
        )
        self.assertEqual(
            value,
            {"rich_text": [{"type": "text", "text": {"content": "error details"}}]},
        )

    def test_build_option_property_value_status_requires_exactly_one(self) -> None:
        with self.assertRaises(main.InvalidRequestError):
            main.build_option_property_value("update_page_property", "status", [])
        with self.assertRaises(main.InvalidRequestError):
            main.build_option_property_value("update_page_property", "status", ["a", "b"])

    def test_build_option_property_value_select_requires_exactly_one(self) -> None:
        with self.assertRaises(main.InvalidRequestError):
            main.build_option_property_value("update_page_property", "select", [])
        with self.assertRaises(main.InvalidRequestError):
            main.build_option_property_value("update_page_property", "select", ["a", "b"])

    def test_build_option_property_value_multi_select_requires_at_least_one(self) -> None:
        with self.assertRaises(main.InvalidRequestError):
            main.build_option_property_value("update_page_property", "multi_select", [])

    def test_build_option_property_value_text_requires_text_argument(self) -> None:
        with self.assertRaises(main.InvalidRequestError):
            main.build_option_property_value("update_page_property", "rich_text", [], text=None)

    def test_build_option_property_value_text_allows_explicit_empty_for_clear(self) -> None:
        value = main.build_option_property_value("update_page_property", "rich_text", [], text="")
        self.assertEqual(value, {"rich_text": []})

        value_alias = main.build_option_property_value("update_page_property", "text", [], text="")
        self.assertEqual(value_alias, {"rich_text": []})

    def test_build_option_property_value_text_rejects_whitespace_only(self) -> None:
        with self.assertRaises(main.InvalidRequestError):
            main.build_option_property_value("update_page_property", "text", [], text="  ")

    def test_build_option_property_value_rejects_mixed_inputs(self) -> None:
        with self.assertRaises(main.InvalidRequestError):
            main.build_option_property_value("update_page_property", "status", ["opt-1"], text="x")
        with self.assertRaises(main.InvalidRequestError):
            main.build_option_property_value("update_page_property", "multi_select", ["opt-1"], text="x")
        with self.assertRaises(main.InvalidRequestError):
            main.build_option_property_value("update_page_property", "rich_text", ["opt-1"], text="x")
        with self.assertRaises(main.InvalidRequestError):
            main.build_option_property_value("update_page_property", "text", ["opt-1"], text="x")

    def test_build_option_property_value_invalid_type(self) -> None:
        with self.assertRaises(main.InvalidRequestError):
            main.build_option_property_value("update_page_property", "number", ["a"])

    def test_update_page_property_rejects_empty_value(self) -> None:
        with self.assertRaises(main.InvalidRequestError):
            main.update_page_property(
                "token",
                "page-1",
                "status-id",
                {},
            )

    def test_require_token_rejects_missing_env(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(main.NotionAPIError) as ctx:
                main.require_token("list-pages")
        self.assertEqual(ctx.exception.code, "missing_token")

    def test_status_cli_json(self) -> None:
        result = self.runner.invoke(main.app, ["status", "--json"])

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["ability"], "notion")

    @patch("abilities.connectors.notion.src.main.notion_request")
    def test_list_pages_cli_json(self, mock_notion_request) -> None:
        mock_notion_request.return_value = {"results": [], "has_more": False, "next_cursor": None}

        with patch.dict("os.environ", {"NOTION_API_KEY": "secret_test_token"}, clear=True):
            result = self.runner.invoke(
                main.app,
                ["list-pages", "--database-id", "db1", "--json"],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["action"], "list_pages")

    @patch("abilities.connectors.notion.src.main.notion_request")
    def test_get_page_content_recursive_and_paginated(self, mock_notion_request) -> None:
        mock_notion_request.side_effect = [
            {"id": "page-1", "properties": {}},
            {
                "results": [{"id": "block-1", "has_children": True}],
                "has_more": True,
                "next_cursor": "root-next",
            },
            {
                "results": [{"id": "block-2", "has_children": False}],
                "has_more": False,
                "next_cursor": None,
            },
            {
                "results": [{"id": "block-1-1", "has_children": False}],
                "has_more": False,
                "next_cursor": None,
            },
        ]

        payload = main.get_page_content("token", "page-1")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["action"], "get_page_content")
        self.assertEqual(payload["data"]["page"]["id"], "page-1")
        self.assertEqual(len(payload["data"]["blocks"]), 2)
        self.assertEqual(payload["data"]["blocks"][0]["id"], "block-1")
        self.assertEqual(payload["data"]["blocks"][0]["children"][0]["id"], "block-1-1")
        self.assertEqual(payload["data"]["blocks"][1]["id"], "block-2")

    @patch("abilities.connectors.notion.src.main.notion_request")
    def test_get_page_content_propagates_api_errors(self, mock_notion_request) -> None:
        mock_notion_request.side_effect = main.NotionAPIError(404, "object_not_found", "missing page")

        with self.assertRaises(main.NotionAPIError) as ctx:
            main.get_page_content("token", "missing-page")

        self.assertEqual(ctx.exception.code, "object_not_found")

    @patch("abilities.connectors.notion.src.main.notion_request")
    def test_get_page_content_cli_json(self, mock_notion_request) -> None:
        mock_notion_request.side_effect = [
            {"id": "page-1", "properties": {}},
            {"results": [], "has_more": False, "next_cursor": None},
        ]

        with patch.dict("os.environ", {"NOTION_API_KEY": "secret_test_token"}, clear=True):
            result = self.runner.invoke(
                main.app,
                ["get-page-content", "--page-id", "page-1", "--json"],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["action"], "get_page_content")
        self.assertEqual(payload["data"]["page"]["id"], "page-1")

    @patch("abilities.connectors.notion.src.main.notion_request")
    def test_get_page_content_cli_human_renders_content(self, mock_notion_request) -> None:
        mock_notion_request.side_effect = [
            {
                "id": "page-1",
                "properties": {
                    "Title": {
                        "type": "title",
                        "title": [{"plain_text": "My Task"}],
                    }
                },
            },
            {
                "results": [
                    {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "Do this now"}]}},
                    {"type": "to_do", "to_do": {"rich_text": [{"plain_text": "Verify"}], "checked": False}},
                ],
                "has_more": False,
                "next_cursor": None,
            },
        ]

        with patch.dict("os.environ", {"NOTION_API_KEY": "secret_test_token"}, clear=True):
            result = self.runner.invoke(
                main.app,
                ["get-page-content", "--page-id", "page-1"],
            )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Page: My Task [page-1]", result.stdout)
        self.assertIn("Do this now", result.stdout)
        self.assertIn("[ ] Verify", result.stdout)
        self.assertNotIn("Top-level blocks:", result.stdout)

    @patch("abilities.connectors.notion.src.main.notion_request")
    def test_get_database_properties_cli_json(self, mock_notion_request) -> None:
        mock_notion_request.return_value = {
            "id": "db1",
            "title": [{"plain_text": "Tasks"}],
            "properties": {
                "Progress": {
                    "id": "progress-id",
                    "type": "status",
                    "status": {"options": [{"id": "s1", "name": "Done", "color": "green"}]},
                }
            },
        }

        with patch.dict("os.environ", {"NOTION_API_KEY": "secret_test_token"}, clear=True):
            result = self.runner.invoke(
                main.app,
                ["get-database-properties", "--database-id", "db1", "--json"],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["action"], "get_database_properties")
        self.assertEqual(payload["data"]["database"]["id"], "db1")
        self.assertEqual(payload["data"]["editable_properties"][0]["name"], "Progress")

    @patch("abilities.connectors.notion.src.main.notion_request")
    def test_get_database_properties_cli_human(self, mock_notion_request) -> None:
        mock_notion_request.return_value = {
            "id": "db1",
            "title": [{"plain_text": "Tasks"}],
            "properties": {
                "Progress": {
                    "id": "progress-id",
                    "type": "status",
                    "status": {"options": [{"id": "s1", "name": "Done", "color": "green"}]},
                },
                "Effort": {
                    "id": "effort-id",
                    "type": "number",
                    "number": {"format": "number"},
                },
            },
        }

        with patch.dict("os.environ", {"NOTION_API_KEY": "secret_test_token"}, clear=True):
            result = self.runner.invoke(
                main.app,
                ["get-database-properties", "--database-id", "db1"],
            )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Database: Tasks [db1]", result.stdout)
        self.assertIn("- Progress (status) [progress-id]", result.stdout)
        self.assertIn("option: Done [s1]", result.stdout)
        self.assertIn("- Effort (number) [effort-id]", result.stdout)

    @patch("abilities.connectors.notion.src.main.notion_request")
    def test_update_page_property_cli_json(self, mock_notion_request) -> None:
        mock_notion_request.return_value = {
            "id": "page-1",
            "last_edited_time": "2026-05-05T13:00:00.000Z",
            "properties": {"status-id": {"status": {"id": "done-id"}}},
        }

        with patch.dict("os.environ", {"NOTION_API_KEY": "secret_test_token"}, clear=True):
            result = self.runner.invoke(
                main.app,
                [
                    "update-page-property",
                    "--page-id",
                    "page-1",
                    "--property-id",
                    "status-id",
                    "--property-type",
                    "status",
                    "--value-id",
                    "done-id",
                    "--json",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["page_id"], "page-1")

    @patch("abilities.connectors.notion.src.main.notion_request")
    def test_update_page_property_cli_rich_text_json(self, mock_notion_request) -> None:
        mock_notion_request.return_value = {
            "id": "page-1",
            "last_edited_time": "2026-05-05T13:00:00.000Z",
            "properties": {
                "error-log-id": {
                    "rich_text": [{"type": "text", "plain_text": "rate limit"}],
                }
            },
        }

        with patch.dict("os.environ", {"NOTION_API_KEY": "secret_test_token"}, clear=True):
            result = self.runner.invoke(
                main.app,
                [
                    "update-page-property",
                    "--page-id",
                    "page-1",
                    "--property-id",
                    "error-log-id",
                    "--property-type",
                    "rich_text",
                    "--text",
                    "rate limit",
                    "--json",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["page_id"], "page-1")

    @patch("abilities.connectors.notion.src.main.notion_request")
    def test_update_page_property_cli_multi_select_json(self, mock_notion_request) -> None:
        mock_notion_request.return_value = {
            "id": "page-1",
            "last_edited_time": "2026-05-05T13:00:00.000Z",
            "properties": {"tags-id": {"multi_select": [{"id": "t1"}, {"id": "t2"}]}},
        }

        with patch.dict("os.environ", {"NOTION_API_KEY": "secret_test_token"}, clear=True):
            result = self.runner.invoke(
                main.app,
                [
                    "update-page-property",
                    "--page-id",
                    "page-1",
                    "--property-id",
                    "tags-id",
                    "--property-type",
                    "multi_select",
                    "--value-id",
                    "t1",
                    "--value-id",
                    "t2",
                    "--json",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["page_id"], "page-1")

    def test_update_page_property_cli_requires_property_type(self) -> None:
        with patch.dict("os.environ", {"NOTION_API_KEY": "secret_test_token"}, clear=True):
            result = self.runner.invoke(
                main.app,
                [
                    "update-page-property",
                    "--page-id",
                    "page-1",
                    "--property-id",
                    "status-id",
                    "--value-id",
                    "done-id",
                    "--json",
                ],
            )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Missing option '--property-type'", result.stderr)

    def test_update_page_property_cli_requires_value_id_for_status(self) -> None:
        with patch.dict("os.environ", {"NOTION_API_KEY": "secret_test_token"}, clear=True):
            result = self.runner.invoke(
                main.app,
                [
                    "update-page-property",
                    "--page-id",
                    "page-1",
                    "--property-id",
                    "status-id",
                    "--property-type",
                    "status",
                    "--json",
                ],
            )
        self.assertNotEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertIn("requires exactly one '--value-id'", payload["error"]["message"])

    def test_update_page_property_cli_requires_text_for_rich_text(self) -> None:
        with patch.dict("os.environ", {"NOTION_API_KEY": "secret_test_token"}, clear=True):
            result = self.runner.invoke(
                main.app,
                [
                    "update-page-property",
                    "--page-id",
                    "page-1",
                    "--property-id",
                    "error-log-id",
                    "--property-type",
                    "rich_text",
                    "--json",
                ],
            )
        self.assertNotEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertIn("requires '--text'", payload["error"]["message"])

    @patch("abilities.connectors.notion.src.main.notion_request")
    def test_update_page_property_cli_allows_empty_text_to_clear(self, mock_notion_request) -> None:
        mock_notion_request.return_value = {
            "id": "page-1",
            "last_edited_time": "2026-05-05T13:00:00.000Z",
            "properties": {
                "error-log-id": {
                    "rich_text": [],
                }
            },
        }

        with patch.dict("os.environ", {"NOTION_API_KEY": "secret_test_token"}, clear=True):
            result = self.runner.invoke(
                main.app,
                [
                    "update-page-property",
                    "--page-id",
                    "page-1",
                    "--property-id",
                    "error-log-id",
                    "--property-type",
                    "rich_text",
                    "--text",
                    "",
                    "--json",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["page_id"], "page-1")
        mock_notion_request.assert_called_once_with(
            "PATCH",
            "/pages/page-1",
            "secret_test_token",
            {"properties": {"error-log-id": {"rich_text": []}}},
        )

    def test_update_page_property_cli_rejects_mixed_text_and_value_id(self) -> None:
        with patch.dict("os.environ", {"NOTION_API_KEY": "secret_test_token"}, clear=True):
            result = self.runner.invoke(
                main.app,
                [
                    "update-page-property",
                    "--page-id",
                    "page-1",
                    "--property-id",
                    "status-id",
                    "--property-type",
                    "status",
                    "--value-id",
                    "done-id",
                    "--text",
                    "should fail",
                    "--json",
                ],
            )
        self.assertNotEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertIn("'--text' is not allowed", payload["error"]["message"])

    def test_bin_help_invocation(self) -> None:
        result = self.runner.invoke(main.app, ["--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Direct CLI for the Robin Notion connector", result.stdout)


if __name__ == "__main__":
    unittest.main()
