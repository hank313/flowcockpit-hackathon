"""
E 模組:雲端增強功能(多條件比較)
輸入候選清單+篩選條件,呼叫 Claude API 產生比較/取捨文字。
失敗、逾時或無網路時回傳 None,呼叫端應維持本地結果,不卡住流程。
"""

import os
from dotenv import load_dotenv
from anthropic import Anthropic, APIConnectionError, APITimeoutError

load_dotenv()

_client = Anthropic()

TIMEOUT_SECONDS = 15.0
MODEL_NAME = "claude-haiku-4-5-20251001"


def get_comparison(candidates: list[dict], conditions: dict) -> str | None:
    """
    candidates: 候選清單,格式對齊 D→A1 規格裡 candidate_card 的 data,例如
        [{"candidate_id": "loc_001", "name": "示範地點A", "attributes": {"indoor": True, "walk_distance_m": 180}}, ...]
    conditions: 目前的篩選條件,例如 {"indoor": True, "has_seating": True, "max_walk_distance_m": 300}

    回傳:一段中文比較/取捨說明文字;若失敗、逾時或無網路,回傳 None。
    """
    if not candidates:
        return None

    prompt = _build_prompt(candidates, conditions)

    for attempt in range(2):  # 最多嘗試2次,應對偶發性網路逾時
        try:
            message = _client.messages.create(
                model=MODEL_NAME,
                max_tokens=300,
                timeout=TIMEOUT_SECONDS,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text.strip()
        except (APIConnectionError, APITimeoutError):
            if attempt == 0:
                continue  # 重試一次
            return None  # 兩次都失敗,維持本地結果,不中斷流程
        except Exception:
            # 任何其他非預期錯誤,同樣安全降級,不讓demo卡住
            return None
    return None


def _build_prompt(candidates: list[dict], conditions: dict) -> str:
    lines = ["以下是候選地點,請用一到兩句話幫使用者比較取捨,語氣自然、口語化:"]
    lines.append(f"使用者目前的條件:{conditions}")
    for c in candidates:
        lines.append(f"- {c.get('name', c.get('candidate_id'))}:{c.get('attributes', {})}")
    return "\n".join(lines)


if __name__ == "__main__":
    # 自我測試:用假資料模擬 D 尚未完成時的整合測試
    fake_candidates = [
        {"candidate_id": "loc_001", "name": "示範地點A", "attributes": {"indoor": True, "walk_distance_m": 500}},
        {"candidate_id": "loc_002", "name": "示範地點B", "attributes": {"indoor": False, "walk_distance_m": 180, "has_shelter": True}},
    ]
    fake_conditions = {"indoor": True, "has_seating": True, "max_walk_distance_m": 300}

    result = get_comparison(fake_candidates, fake_conditions)
    print("comparison_text =", result)
