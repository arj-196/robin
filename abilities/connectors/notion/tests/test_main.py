from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from abilities.connectors.notion.src import main


class NotionAbilityTests(unittest.TestCase):
    def test_mask_secret_handles_missing_value(self) -> None:
        self.assertEqual(main.mask_secret(None), "missing")

    def test_status_payload_exposes_ability_name(self) -> None:
        payload = main.build_status_payload("invoke")
        self.assertEqual(payload["ability"], "notion")

    def test_parse_rejects_invalid_json(self) -> None:
        with self.assertRaises(ValueError):
            main.parse_invoke_input("{")

    def test_handle_invoke_rejects_missing_action(self) -> None:
        with self.assertRaises(ValueError):
            main.handle_invoke("token", json.dumps({"database_id": "db1"}))

    def test_handle_list_pages_rejects_invalid_mode(self) -> None:
        payload = {
            "action": "list_pages",
            "database_id": "db1",
            "mode": "bad-mode",
        }
        with self.assertRaises(ValueError):
            main.handle_list_pages(payload, "token")

    @patch("abilities.connectors.notion.src.main.notion_request")
    def test_list_pages_summary_mode(self, mock_notion_request) -> None:
        mock_notion_request.return_value = {
            "results": [
                {
                    "id": "page-1",
                    "last_edited_time": "2026-05-05T12:00:00.000Z",
                    "properties": {
                        "Title": {
                            "id": "title",
                            "type": "title",
                            "title": [{"plain_text": "Task A"}],
                        },
                        "Status": {
                            "id": "status-id",
                            "type": "status",
                            "status": {"name": "Todo"},
                        },
                    },
                }
            ],
            "has_more": True,
            "next_cursor": "cursor-1",
        }

        response = main.handle_invoke(
            "token",
            json.dumps(
                {
                    "action": "list_pages",
                    "database_id": "db1",
                    "mode": "summary",
                    "property_ids": ["status-id"],
                }
            ),
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["action"], "list_pages")
        self.assertEqual(response["data"]["next_cursor"], "cursor-1")
        page = response["data"]["results"][0]
        self.assertEqual(page["id"], "page-1")
        self.assertEqual(page["title"], "Task A")
        self.assertEqual(sorted(page["properties"].keys()), ["status-id"])

    @patch("abilities.connectors.notion.src.main.notion_request")
    def test_list_pages_full_mode(self, mock_notion_request) -> None:
        raw_page = {"id": "page-raw", "properties": {"A": {"id": "a"}}}
        mock_notion_request.return_value = {
            "results": [raw_page],
            "has_more": False,
            "next_cursor": None,
        }

        response = main.handle_invoke(
            "token",
            json.dumps({"action": "list_pages", "database_id": "db1", "mode": "full"}),
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["results"][0], raw_page)

    @patch("abilities.connectors.notion.src.main.notion_request")
    def test_update_page_property_success(self, mock_notion_request) -> None:
        mock_notion_request.side_effect = [
            {
                "id": "page-1",
                "parent": {"type": "database_id", "database_id": "db1"},
            },
            {
                "id": "page-1",
                "last_edited_time": "2026-05-05T13:00:00.000Z",
                "properties": {
                    "status-id": {
                        "id": "status-id",
                        "type": "status",
                        "status": {"name": "Done"},
                    }
                },
            },
        ]

        response = main.handle_invoke(
            "token",
            json.dumps(
                {
                    "action": "update_page_property",
                    "database_id": "db1",
                    "page_id": "page-1",
                    "property_id": "status-id",
                    "value": {"status": {"name": "Done"}},
                }
            ),
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["action"], "update_page_property")
        self.assertEqual(response["data"]["page_id"], "page-1")
        self.assertEqual(response["data"]["updated_property"]["property_id"], "status-id")

    @patch("abilities.connectors.notion.src.main.notion_request")
    def test_update_page_rejects_database_mismatch(self, mock_notion_request) -> None:
        mock_notion_request.return_value = {
            "id": "page-1",
            "parent": {"type": "database_id", "database_id": "db-other"},
        }

        with self.assertRaises(main.NotionAPIError) as ctx:
            main.handle_invoke(
                "token",
                json.dumps(
                    {
                        "action": "update_page_property",
                        "database_id": "db1",
                        "page_id": "page-1",
                        "property_id": "status-id",
                        "value": {"status": {"name": "Done"}},
                    }
                ),
            )

        self.assertEqual(ctx.exception.code, "database_mismatch")

    def test_handle_invoke_requires_token_for_actions(self) -> None:
        with self.assertRaises(main.NotionAPIError) as ctx:
            main.handle_invoke("", json.dumps({"action": "list_pages", "database_id": "db1"}))
        self.assertEqual(ctx.exception.code, "missing_token")

    @patch("abilities.connectors.notion.src.main.handle_invoke")
    @patch("sys.stdin.read")
    def test_main_emits_standardized_error_envelope(self, mock_read, mock_handle_invoke) -> None:
        mock_read.return_value = '{"action":"list_pages"}'
        mock_handle_invoke.side_effect = ValueError("bad request")

        with patch("builtins.print") as mock_print:
            exit_code = main.main(["invoke"])

        self.assertEqual(exit_code, 1)
        printed = mock_print.call_args[0][0]
        payload = json.loads(printed)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "invalid_request")

    @patch("abilities.connectors.notion.src.main.handle_invoke")
    @patch("sys.stdin.read")
    def test_main_preserves_no_input_status_behavior(self, mock_read, mock_handle_invoke) -> None:
        mock_read.return_value = ""
        mock_handle_invoke.return_value = main.build_status_payload("invoke")

        with patch("builtins.print") as mock_print:
            exit_code = main.main(["invoke"])

        self.assertEqual(exit_code, 0)
        payload = json.loads(mock_print.call_args[0][0])
        self.assertEqual(payload["ability"], "notion")


if __name__ == "__main__":
    unittest.main()
