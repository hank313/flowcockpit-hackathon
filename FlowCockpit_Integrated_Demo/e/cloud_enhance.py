"""
E 模組:雲端增強功能(多條件比較)
輸入候選清單+篩選條件,呼叫 Claude API 產生比較/取捨文字。
失敗、逾時或無網路時回傳 None,呼叫端應維持本地結果,不卡住流程。
"""

import os
import ssl
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:  # 允許在未安裝雲端依賴時以離線模式啟動
    load_dotenv = None

# .env 放在專案根目錄(e/ 的上一層),不管從哪個資料夾執行這支程式都能找到
if load_dotenv is not None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

TIMEOUT_SECONDS = 15.0
MODEL_NAME = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")


def get_comparison(candidates: list[dict], conditions: dict, raw_text: str | None = None) -> str | None:
    """
    candidates: 候選清單,格式對齊 D→A1 規格裡 candidate_card 的 data,例如
        [{"candidate_id": "loc_001", "name": "示範地點A", "attributes": {"indoor": True, "walk_distance_m": 180}}, ...]
    conditions: 目前的篩選條件,例如 {"indoor": True, "has_seating": True, "max_walk_distance_m": 300}

    回傳:一段中文比較/取捨說明文字;若失敗、逾時或無網路,回傳 None。
    """
    if not candidates or not os.getenv("ANTHROPIC_API_KEY"):
        return None

    try:
        from anthropic import Anthropic, APIConnectionError, APITimeoutError
        import httpx
        import truststore
    except ImportError:
        return None

    # Windows 校園／公司網路常由系統憑證庫信任代理 CA，但 certifi 不認得。
    # truststore 沿用 Windows 信任鏈；綁定 0.0.0.0 避免可解析但無法連線的 IPv6 路徑。
    ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    transport = httpx.HTTPTransport(
        verify=ssl_context,
        local_address=os.getenv("ANTHROPIC_LOCAL_ADDRESS", "0.0.0.0"),
        retries=1,
    )

    prompt = _build_prompt(candidates, conditions, raw_text)

    with httpx.Client(transport=transport, timeout=TIMEOUT_SECONDS) as http_client:
        client = Anthropic(http_client=http_client, max_retries=0)
        for attempt in range(2):  # 最多嘗試2次,應對偶發性網路逾時
            try:
                message = client.messages.create(
                    model=MODEL_NAME,
                    max_tokens=300,
                    messages=[{"role": "user", "content": prompt}],
                )
                return message.content[0].text.strip()
            except (APIConnectionError, APITimeoutError):
                if attempt == 0:
                    continue  # 重試一次
                return None  # 兩次都失敗,維持本地結果,不中斷流程
            except Exception:
                # 驗證失敗、額度不足或其他錯誤同樣安全降級,不讓 demo 卡住。
                return None
    return None


def _candidate_attributes(candidate: dict[str, Any]) -> dict[str, Any]:
    attributes = candidate.get("attributes")
    if isinstance(attributes, dict):
        return attributes
    return {
        key: candidate.get(key)
        for key in ("indoor", "has_seating", "has_food", "drive_distance_m", "drive_time_min")
        if candidate.get(key) is not None
    }


def _build_prompt(candidates: list[dict], conditions: dict, raw_text: str | None = None) -> str:
    lines = ["以下是候選地點,請用一到兩句話幫使用者比較取捨,語氣自然、口語化:"]
    if raw_text:
        lines.append(f"使用者實際說的是:{raw_text}")
    lines.append(f"使用者目前的條件:{conditions}")
    for c in candidates:
        lines.append(f"- {c.get('name', c.get('candidate_id', c.get('id')))}:{_candidate_attributes(c)}")
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
