"""
E 模組:把雲端比較文字合併進 D 產生的 UI JSON 裡。
D 尚未完成前,用符合 README 定案格式的假資料測試這段合併邏輯;
等 D 完成後,只要把 fake_d_output() 換成真正呼叫 D 的服務即可,合併邏輯不用改。
"""

import copy

from cloud_enhance import get_comparison


def enrich_with_comparison(ui_json: dict, candidates: list[dict], conditions: dict) -> dict:
    """
    在 D 產生的 UI JSON 裡找到 compare_confirm_panel,
    把雲端比較結果填進它的 comparison_text 欄位。
    找不到該元件、或雲端呼叫失敗(回傳None)時,原樣回傳,不報錯、不中斷流程。
    """
    result = copy.deepcopy(ui_json)

    panel = next(
        (c for c in result.get("components", []) if c.get("type") == "compare_confirm_panel"),
        None,
    )
    if panel is None:
        return result  # 這次畫面沒有比較面板,不需要處理

    comparison_text = get_comparison(candidates, conditions)
    if comparison_text is not None:
        panel["data"]["comparison_text"] = comparison_text

    return result


def fake_d_output() -> dict:
    """模擬 D 尚未完成前,D→A1 格式的假輸出,結構照 README 定案格式。"""
    return {
        "components": [
            {"type": "condition_control", "id": "cond_1",
             "data": {"filters": {"indoor": True, "has_seating": True, "max_walk_distance_m": 300}}},
            {"type": "candidate_card", "id": "card_loc_001",
             "data": {"candidate_id": "loc_001", "name": "示範地點A",
                      "attributes": {"indoor": True, "walk_distance_m": 500}, "selected": False}},
            {"type": "candidate_card", "id": "card_loc_002",
             "data": {"candidate_id": "loc_002", "name": "示範地點B",
                      "attributes": {"indoor": False, "walk_distance_m": 180, "has_shelter": True}, "selected": False}},
            {"type": "compare_confirm_panel", "id": "panel_1",
             "data": {"candidate_ids": ["loc_001", "loc_002"], "comparison_text": None, "confirm_enabled": True}},
        ],
        "clarification_needed": None,
    }


if __name__ == "__main__":
    import json

    d_output = fake_d_output()
    candidates = [c["data"] for c in d_output["components"] if c["type"] == "candidate_card"]
    conditions = next(
        c["data"]["filters"] for c in d_output["components"] if c["type"] == "condition_control"
    )

    final_json = enrich_with_comparison(d_output, candidates, conditions)
    print(json.dumps(final_json, ensure_ascii=False, indent=2))
