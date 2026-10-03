import os
import sys
import tempfile
import unittest
import asyncio
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["FLOWCOCKPIT_DB_PATH"] = str(Path(TEMP_DIR.name) / "test.db")
sys.path.insert(0, str(ROOT / "d"))
sys.path.insert(0, str(ROOT / "e"))
sys.path.insert(0, str(ROOT / "bc"))

import server_d  # noqa: E402
import server_e  # noqa: E402
from bc_intent import extract as extract_bc_intent  # noqa: E402


class SystemIntegrationTest(unittest.TestCase):
    def setUp(self):
        server_d.SEARCH_POOL.clear()
        server_d.StateManager.reset_task("demo_task_001")

    def test_ui_contract_contains_android_fields(self):
        task = server_d.StateManager.update_task_state(
            "demo_task_001",
            raw_text="找室內休息地點",
            new_candidates=[{
                "id": "node/1",
                "name": "測試咖啡店",
                "indoor": True,
                "has_seating": True,
                "has_food": True,
                "drive_distance_m": 900,
                "drive_time_min": 3,
            }],
            error_message=None,
        )
        message = server_d.UIGenerator.build_ui_json(task)
        self.assertEqual(message["type"], "ui_update")
        self.assertEqual(message["payload"]["raw_text"], "找室內休息地點")
        card = next(c for c in message["payload"]["components"] if c["type"] == "candidate_card")
        self.assertEqual(card["data"]["attributes"]["straight_line_distance_m"], 900)

    def test_nullable_state_can_be_cleared(self):
        server_d.StateManager.update_task_state(
            "demo_task_001", selected_id="node/1", comparison_text="舊比較", error_message="舊錯誤"
        )
        task = server_d.StateManager.update_task_state(
            "demo_task_001", selected_id=None, comparison_text=None, error_message=None
        )
        self.assertIsNone(task["selected_id"])
        self.assertIsNone(task["comparison_text"])
        self.assertIsNone(task["error_message"])

    def test_disabled_boolean_filters_mean_unrestricted(self):
        places = [
            {
                "id": "outdoor",
                "indoor": False,
                "has_seating": False,
                "has_food": False,
                "drive_distance_m": 500,
            },
            {
                "id": "cafe",
                "indoor": True,
                "has_seating": True,
                "has_food": True,
                "drive_distance_m": 800,
            },
        ]
        unrestricted = server_d.apply_filters(places, {
            "indoor": False,
            "has_seating": False,
            "has_food": False,
            "max_drive_distance_m": 10000,
        })
        self.assertEqual([place["id"] for place in unrestricted], ["outdoor", "cafe"])
        seating_only = server_d.apply_filters(places, {
            "has_seating": True,
            "max_drive_distance_m": 10000,
        })
        self.assertEqual([place["id"] for place in seating_only], ["cafe"])

    def test_search_defaults_are_unrestricted_and_ten_kilometres(self):
        self.assertEqual(server_d.DEFAULT_FILTERS, {
            "indoor": False,
            "has_seating": False,
            "has_food": False,
            "max_drive_distance_m": 10000,
        })

    def test_bc_preserves_category_when_query_has_conditions(self):
        intent, clarification = extract_bc_intent(
            "找附近有座位的咖啡廳", action="search", category="cafe"
        )
        self.assertIsNone(clarification)
        self.assertEqual(intent.category, "cafe")
        self.assertTrue(intent.conditions.has_seating)

    def test_e_degrades_without_api_key(self):
        previous = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            client = TestClient(server_e.app)
            response = client.post("/api/compare", json={
                "task_id": "demo_task_001",
                "base_version": 1,
                "candidates": [{"id": "node/1", "name": "測試地點"}],
                "conditions": {"indoor": True},
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], "local_only")
        finally:
            if previous is not None:
                os.environ["ANTHROPIC_API_KEY"] = previous

    def test_cloud_result_applies_only_to_current_version(self):
        task = server_d.StateManager.update_task_state(
            "demo_task_001",
            new_candidates=[{"id": "node/1", "name": "測試咖啡店"}],
        )

        class FakeResponse:
            status_code = 200

            @staticmethod
            def json():
                return {"comparison_text": "雲端比較完成"}

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return None

            async def post(self, *_args, **_kwargs):
                return FakeResponse()

        original = server_d.httpx.AsyncClient
        server_d.httpx.AsyncClient = lambda **_kwargs: FakeClient()
        try:
            applied = asyncio.run(server_d.apply_cloud_comparison(task["task_id"], task["version"]))
            self.assertTrue(applied)
            updated = server_d.StateManager.get_or_create_task(task["task_id"])
            self.assertEqual(updated["comparison_text"], "雲端比較完成")
            self.assertFalse(asyncio.run(server_d.apply_cloud_comparison(task["task_id"], task["version"])))
        finally:
            server_d.httpx.AsyncClient = original


if __name__ == "__main__":
    unittest.main()
