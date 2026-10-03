import asyncio
import json
import logging
import math
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx
from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import uvicorn

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = os.getenv("FLOWCOCKPIT_DB_PATH", str(BASE_DIR / "flowcockpit.db"))
BC_API_URL = os.getenv("BC_API_URL", "http://127.0.0.1:8001")
CLOUD_API_URL = os.getenv("CLOUD_API_URL", "http://127.0.0.1:8002")
CLOUD_RETRY_SECONDS = tuple(
    float(value)
    for value in os.getenv("CLOUD_RETRY_SECONDS", "0,5,15").split(",")
    if value.strip()
)

logger = logging.getLogger("flowcockpit.d")
UNSET = object()

# ==========================================
# 1. 資料庫初始化
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS task_states (
        task_id TEXT PRIMARY KEY,
        version INTEGER NOT NULL,
        intent TEXT,
        raw_text TEXT,
        filters_json TEXT NOT NULL,
        candidates_json TEXT NOT NULL,
        selected_id TEXT,
        comparison_text TEXT,
        status TEXT NOT NULL,
        clarification_needed TEXT,
        error_message TEXT,
        updated_at REAL NOT NULL,
        cloud_status TEXT
    )
    """)
    # 舊版資料庫不會因 CREATE TABLE IF NOT EXISTS 自動增加欄位，啟動時做輕量遷移。
    expected_columns = {
        "intent": "TEXT",
        "raw_text": "TEXT",
        "filters_json": "TEXT NOT NULL DEFAULT '{}'",
        "candidates_json": "TEXT NOT NULL DEFAULT '[]'",
        "selected_id": "TEXT",
        "comparison_text": "TEXT",
        "status": "TEXT NOT NULL DEFAULT 'IN_PROGRESS'",
        "clarification_needed": "TEXT",
        "error_message": "TEXT",
        "updated_at": "REAL NOT NULL DEFAULT 0",
        "cloud_status": "TEXT",
    }
    existing = {row[1] for row in cursor.execute("PRAGMA table_info(task_states)")}
    for name, definition in expected_columns.items():
        if name not in existing:
            cursor.execute(f"ALTER TABLE task_states ADD COLUMN {name} {definition}")
    conn.commit()
    conn.close()

init_db()

# 候選地點一律來自 BC 的本機 OSM 資料庫(實際地點),不使用示範資料。
# 新任務在第一次語音查詢之前候選為空。

# 預設條件。室內/有座位/有餐飲三個開關:開 = 必須符合,關 = 不限制。
# 新的一次語音搜尋會回到這組預設，再套用這次語音中明確說出的條件，
# 避免上一輪的條件讓不同類別的搜尋全部被排除。
DEFAULT_FILTERS = {
    "indoor": False,
    "has_seating": False,
    "has_food": False,
    "max_drive_distance_m": 10000,
}

# ==========================================
# 2. 任務狀態管理
# ==========================================
class StateManager:
    @staticmethod
    def get_or_create_task(task_id: str = "demo_task_001") -> Dict[str, Any]:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM task_states WHERE task_id = ?", (task_id,))
        row = cursor.fetchone()
        
        if not row:
            initial_filters = dict(DEFAULT_FILTERS)
            cursor.execute("""
                INSERT INTO task_states VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task_id, 1, "search_rest_stop", "預設休息推薦",
                json.dumps(initial_filters),
                json.dumps([]),
                None, "", "IN_PROGRESS", None, "", time.time(), "idle"
            ))
            conn.commit()
            cursor.execute("SELECT * FROM task_states WHERE task_id = ?", (task_id,))
            row = cursor.fetchone()
            
        task = dict(row)
        task["filters"] = json.loads(task["filters_json"])
        task["candidates"] = json.loads(task["candidates_json"])
        conn.close()
        return task

    @staticmethod
    def reset_task(task_id: str = "demo_task_001") -> Dict[str, Any]:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT version FROM task_states WHERE task_id = ?", (task_id,))
        row = cursor.fetchone()
        next_ver = (row["version"] + 1) if row else 1

        initial_filters = dict(DEFAULT_FILTERS)
        cursor.execute("""
            UPDATE task_states
            SET version = ?, intent = 'search_rest_stop', raw_text = '新任務開始',
                filters_json = ?, candidates_json = ?, selected_id = NULL,
                comparison_text = '', status = 'IN_PROGRESS', clarification_needed = NULL,
                error_message = '', updated_at = ?, cloud_status = 'idle'
            WHERE task_id = ?
        """, (
            next_ver, json.dumps(initial_filters),
            json.dumps([]),
            time.time(), task_id
        ))
        conn.commit()
        conn.close()
        return StateManager.get_or_create_task(task_id)

    @staticmethod
    def update_task_state(
        task_id: str,
        intent: Optional[str] = None,
        raw_text: Optional[str] = None,
        new_filters: Optional[Dict[str, Any]] = None,
        new_candidates: Optional[List[Dict[str, Any]]] = None,
        selected_id: Any = UNSET,
        comparison_text: Any = UNSET,
        clarification_needed: Any = UNSET,
        status: Any = UNSET,
        error_message: Any = UNSET,
        cloud_status: Any = UNSET,
    ) -> Dict[str, Any]:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM task_states WHERE task_id = ?", (task_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return StateManager.get_or_create_task(task_id)

        current_ver = row["version"] + 1
        current_intent = intent if intent is not None else row["intent"]
        current_raw_text = raw_text if raw_text is not None else row["raw_text"]
        
        current_filters = json.loads(row["filters_json"])
        if new_filters:
            current_filters.update(new_filters)

        current_candidates = new_candidates if new_candidates is not None else json.loads(row["candidates_json"])
        current_selected = row["selected_id"] if selected_id is UNSET else selected_id
        current_comp_text = row["comparison_text"] if comparison_text is UNSET else comparison_text
        current_clarify = row["clarification_needed"] if clarification_needed is UNSET else clarification_needed
        current_status = row["status"] if status is UNSET else status
        current_err = row["error_message"] if error_message is UNSET else error_message
        current_cloud_status = row["cloud_status"] if cloud_status is UNSET else cloud_status

        cursor.execute("""
            UPDATE task_states
            SET version = ?, intent = ?, raw_text = ?, filters_json = ?, 
                candidates_json = ?, selected_id = ?, comparison_text = ?, 
                clarification_needed = ?, status = ?, error_message = ?, updated_at = ?, cloud_status = ?
            WHERE task_id = ?
        """, (
            current_ver, current_intent, current_raw_text,
            json.dumps(current_filters, ensure_ascii=False),
            json.dumps(current_candidates, ensure_ascii=False),
            current_selected, current_comp_text, current_clarify, current_status, current_err,
            time.time(), current_cloud_status, task_id
        ))
        conn.commit()
        conn.close()
        return StateManager.get_or_create_task(task_id)

# ==========================================
# 3. 生成式 UI 組裝器 (嚴格對齊 A1 UiJsonParser.kt)
# ==========================================
class UIGenerator:
    @staticmethod
    def build_ui_json(task: Dict[str, Any]) -> Dict[str, Any]:
        filters = task["filters"]
        candidates = task["candidates"]
        selected_id = task.get("selected_id")

        components = []

        # 1. 條件控制元件 (type: condition_control)
        components.append({
            "type": "condition_control",
            "id": "cond_1",
            "data": {
                "filters": filters
            }
        })

        # 2. 候選卡片清單 (逐筆展開為 type: candidate_card)
        for p in candidates:
            p_id = str(p.get("id"))
            components.append({
                "type": "candidate_card",
                "id": f"card_{p_id}",
                "data": {
                    "candidate_id": p_id,
                    "name": p.get("name"),
                    "attributes": {
                        "indoor": p.get("indoor", True),
                        "has_seating": p.get("has_seating", True),
                        "has_food": p.get("has_food", False),
                        "straight_line_distance_m": p.get("drive_distance_m", 1500),
                        "drive_time_min": p.get("drive_time_min")
                    },
                    "selected": (p_id == str(selected_id))
                }
            })

        # 3. 比較與確認面板 (type: compare_confirm_panel)
        if candidates:
            # 優先取前 3 個候選
            candidate_ids = [str(c.get("id")) for c in candidates[:3]]
            if selected_id and str(selected_id) not in candidate_ids:
                candidate_ids = candidate_ids[:2] + [str(selected_id)]

            components.append({
                "type": "compare_confirm_panel",
                "id": "panel_1",
                "data": {
                    "candidate_ids": candidate_ids,
                    "comparison_text": task.get("comparison_text") or None,
                    "confirm_enabled": task.get("status") != "CONFIRMED"
                }
            })

        payload = {
            "components": components,
            "clarification_needed": task.get("clarification_needed") or None,
            "raw_text": task.get("raw_text") or None,
            "error_message": task.get("error_message") or None,
            "cloud_status": task.get("cloud_status") or (
                "enhanced" if task.get("comparison_text") else "idle"
            ),
            "task_status": task.get("status"),
        }

        return {
            "task_id": task["task_id"],
            "version": task["version"],
            "type": "ui_update",
            "payload": payload
        }

def convert_bc_places_to_candidates(bc_places: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    candidates = []
    for idx, p in enumerate(bc_places):
        dist = p.get("distance_m")
        dist_m = int(dist) if dist is not None else 1500
        drive_min = max(2, math.ceil((dist_m * 1.35 / 1000.0) / 35.0 * 60))
        cats = p.get("categories", [])
        matched = p.get("matched_tags", {})
        # 室內/座位/餐飲是依 OSM 類別推測的(OSM 沒有可靠的欄位):
        # 餐廳、咖啡店 = 室內有座位有餐飲;便利商店 = 室內有餐飲(座位不明,視為沒有);
        # 長椅、野餐桌、有標座位數的地點 = 有座位
        food = "food" in cats or "cafe" in cats
        convenience = "convenience" in cats

        candidates.append({
            "id": p.get("osm_id", f"loc_{idx+1:03d}"),
            "name": p.get("name", "推薦休息點"),
            "indoor": food or convenience,
            "has_seating": food or "rest" in cats or matched.get("bench") == "yes" or "seats" in matched,
            "has_food": food or convenience,
            "drive_distance_m": dist_m,
            "drive_time_min": drive_min,
            "address": p.get("address", "")
        })
    return candidates

# ==========================================
# 4. WebSocket 管理 (對齊 A1 UserAction.kt)
# ==========================================
app = FastAPI(title="FlowCockpit Backend Module D")

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        text_data = json.dumps(message, ensure_ascii=False)
        for connection in self.active_connections:
            try:
                await connection.send_text(text_data)
            except Exception:
                pass

manager = ConnectionManager()


async def apply_cloud_comparison(task_id: str, base_version: int) -> bool:
    """向 E 取得比較文字；只有任務仍停在請求版本時才套用，避免過期回覆覆蓋新操作。"""
    task = StateManager.get_or_create_task(task_id)
    if task["version"] != base_version or not task["candidates"] or task["status"] == "CONFIRMED":
        return False
    body = {
        "task_id": task_id,
        "base_version": base_version,
        "candidates": task["candidates"],
        "conditions": task["filters"],
        "raw_text": task.get("raw_text"),
    }
    try:
        async with httpx.AsyncClient(timeout=18.0) as client:
            response = await client.post(f"{CLOUD_API_URL}/api/compare", json=body)
        if response.status_code != 200:
            return False
        comparison_text = response.json().get("comparison_text")
        if not comparison_text:
            return False
    except Exception as exc:
        logger.info("Cloud enhancement unavailable: %s", exc)
        return False

    current = StateManager.get_or_create_task(task_id)
    if current["version"] != base_version or current["status"] == "CONFIRMED":
        return False
    updated = StateManager.update_task_state(
        task_id, comparison_text=comparison_text, cloud_status="enhanced"
    )
    await manager.broadcast(UIGenerator.build_ui_json(updated))
    return True


async def enhance_with_retry(task_id: str, base_version: int) -> None:
    for delay_seconds in CLOUD_RETRY_SECONDS or (0,):
        if delay_seconds:
            await asyncio.sleep(delay_seconds)
        current = StateManager.get_or_create_task(task_id)
        if current["version"] != base_version:
            return
        if await apply_cloud_comparison(task_id, base_version):
            return
    current = StateManager.get_or_create_task(task_id)
    if current["version"] == base_version and current.get("cloud_status") == "processing":
        updated = StateManager.update_task_state(task_id, cloud_status="local_only")
        await manager.broadcast(UIGenerator.build_ui_json(updated))


def schedule_cloud_enhancement(task: Dict[str, Any]) -> None:
    if task.get("candidates") and task.get("status") != "CONFIRMED":
        asyncio.create_task(enhance_with_retry(task["task_id"], task["version"]))

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        current_task = StateManager.get_or_create_task("demo_task_001")
        # 連線即推播目前 UI 結構
        await websocket.send_text(json.dumps(UIGenerator.build_ui_json(current_task), ensure_ascii=False))

        while True:
            raw_text = await websocket.receive_text()
            data = json.loads(raw_text)
            
            # 支援直接傳入 UserAction 或包在 Envelope 內
            payload = data.get("payload", data)
            action = payload.get("action")
            task_id = data.get("task_id", "demo_task_001")

            # 對齊 A1 UserAction: select_candidate
            if action in ["select_candidate", "SELECT_CANDIDATE"]:
                cand_id = payload.get("candidate_id")
                task = StateManager.get_or_create_task(task_id)
                # 再次點擊相同卡片則取消選取
                new_sel = None if str(task.get("selected_id")) == str(cand_id) else str(cand_id)
                task = StateManager.update_task_state(
                    task_id, selected_id=new_sel, comparison_text=None,
                    clarification_needed=None, error_message=None,
                    cloud_status="processing" if task.get("candidates") else "not_applicable",
                )

            # 對齊 A1 UserAction: update_condition
            elif action in ["update_condition", "UPDATE_FILTER"]:
                if "key" in payload:
                    new_filters = {payload["key"]: payload.get("value")}
                else:
                    new_filters = payload.get("filters", {})
                task = StateManager.get_or_create_task(task_id)
                merged = {**task["filters"], **new_filters}
                # 條件(室內/有座位/有餐飲/行駛距離)變動:從候選池重新篩選;
                # 還沒搜尋過(例如 D 剛重啟)時,只能再篩選畫面上現有的候選
                places = await pool_for_filters(task_id, merged)
                if places is None:
                    places = task["candidates"]
                new_candidates = apply_filters(places, merged)
                kept_ids = {str(c.get("id")) for c in new_candidates}
                new_selected = UNSET if str(task.get("selected_id")) in kept_ids else None
                task = StateManager.update_task_state(
                    task_id, new_filters=new_filters, new_candidates=new_candidates,
                    selected_id=new_selected, comparison_text=None,
                    clarification_needed=None, error_message=None,
                    cloud_status="processing" if new_candidates else "not_applicable",
                )

            # 對齊 A1 UserAction: confirm
            elif action in ["confirm", "CONFIRM_DESTINATION"]:
                cand_id = payload.get("candidate_id")
                task = StateManager.update_task_state(task_id, selected_id=str(cand_id) if cand_id else None, status="CONFIRMED")

            elif action == "RESET_TASK":
                SEARCH_POOL.pop(task_id, None)
                task = StateManager.reset_task(task_id)

            else:
                task = StateManager.get_or_create_task(task_id)

            await manager.broadcast(UIGenerator.build_ui_json(task))
            if action not in ("CONFIRM_DESTINATION", "confirm", "RESET_TASK"):
                schedule_cloud_enhancement(task)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        logger.exception("WebSocket handler failed")
        if websocket in manager.active_connections:
            manager.disconnect(websocket)

# ==========================================
# 5. 音訊與 BC 鏈路處理
# ==========================================

# BC 的「休息設施」類別(長椅、野餐桌)在 OSM 很稀疏,實測雲科大附近 3 公里內為 0 筆,
# 所以「找休息地點」改查這幾類常見的休息場所,依距離合併。
REST_STOP_QUERIES = ["找休息地點", "找咖啡店", "找便利商店", "找公園", "找餐廳"]
CATEGORY_QUERIES = {
    "rest": "找休息地點",
    "park": "找公園",
    "cafe": "找咖啡店",
    "food": "找餐廳",
    "toilet": "找廁所",
    "convenience": "找便利商店",
    "fuel": "找加油站",
    "medical": "找醫院",
    "attraction": "找景點",
    "lodging": "找住宿",
    "parking": "找停車場",
    "water": "找飲水機",
}
MAX_CANDIDATES = 5      # 畫面上顯示的候選數
POOL_SIZE = 100         # 候選池:一次查到的地點(五類各最多 20 筆),條件變動時從中重新篩選
POOL_QUERY_LIMIT = 20   # BC /api/text 每次查詢的筆數上限(BC 最多 20)

async def _bc_text(client: httpx.AsyncClient, text: str, latitude: float, longitude: float, radius_km: Optional[float]):
    body = {"text": text, "latitude": latitude, "longitude": longitude, "limit": POOL_QUERY_LIMIT}
    if radius_km:
        body["radius_km"] = radius_km
    return await client.post(f"{BC_API_URL}/api/text", json=body)

def _bc_error(res: httpx.Response) -> str:
    try:
        detail = res.json().get("error", {}).get("message", "")
    except ValueError:
        detail = ""
    return f"BC 地點查詢失敗 (HTTP {res.status_code}): {detail}"

async def fetch_real_places(raw_text: str, latitude: float, longitude: float,
                            radius_km: Optional[float], rest_stop: bool,
                            category: Optional[str] = None):
    """向 BC /api/text 取得實際地點(來自 BC 本機 OSM 資料庫)。
    rest_stop=True:找休息地點(意圖是休息,或語音含條件而 BC 不替 D 查地點),查常見休息類型並依距離合併。
    rest_stop=False:照使用者說的話查(例如「找咖啡店」)。
    回傳 (places, message):places 是依距離排序的候選池(尚未套用篩選條件),
    None 代表 BC 無法使用,呼叫端應保留原候選。"""
    if category in CATEGORY_QUERIES and category != "rest":
        queries = [CATEGORY_QUERIES[category]]
    else:
        queries = REST_STOP_QUERIES if rest_stop else [raw_text]
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            results = await asyncio.gather(
                *[_bc_text(client, q, latitude, longitude, radius_km) for q in queries]
            )
    except Exception as e:
        return None, f"無法連線 BC 地點查詢: {e}"

    places: Dict[str, Dict[str, Any]] = {}
    message, error = "", ""
    for res in results:
        if res.status_code != 200:
            error = _bc_error(res)
            continue
        data = res.json()
        message = data.get("reply", "") or message
        for p in data.get("places", []):
            places.setdefault(p["osm_id"], p)

    if places:
        nearest = sorted(places.values(), key=lambda p: (p.get("distance_m") is None, p.get("distance_m") or 0))
        return convert_bc_places_to_candidates(nearest[:POOL_SIZE]), ""
    if error and not message:   # 每次查詢都失敗 → BC 無法使用
        return None, error
    if rest_stop:
        scope = f"直線距離 {radius_km:g} 公里內" if radius_km else "附近"
        return [], f"{scope}找不到休息地點(已查休息設施、咖啡店、便利商店、公園、餐廳)"
    return [], message or "BC 查無符合的地點"

# 最近一次語音搜尋的候選池與搜尋方式(座標、查詢文字、是否為休息地點、搜尋半徑)。
# 開關或距離按鈕變動時,從候選池重新篩選;範圍放寬到超出候選池的半徑時,才用同樣方式重新查詢。
# 只存在記憶體,D 重啟後遺失(此時只能再篩選畫面上現有的候選,補不回已被篩掉的)。
SEARCH_POOL: Dict[str, Dict[str, Any]] = {}

def _distance_limit(filters: Dict[str, Any]) -> Optional[float]:
    max_m = filters.get("max_drive_distance_m")
    if isinstance(max_m, bool) or not isinstance(max_m, (int, float)) or max_m <= 0:
        return None
    return max_m

def apply_filters(places: List[Dict[str, Any]], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
    """依篩選條件取出要顯示的候選。室內/有座位/有餐飲:True = 只留有該屬性的地點,
    False/None = 不限制。這讓平板上的關閉狀態符合一般篩選器的操作直覺。
    行駛距離上限是直線距離。"""
    max_m = _distance_limit(filters)
    result = []
    for c in places:
        if max_m is not None and c.get("drive_distance_m", 0) > max_m:
            continue
        if any(filters.get(key) is True and not bool(c.get(key))
               for key in ("indoor", "has_seating", "has_food")):
            continue
        result.append(c)
    return result[:MAX_CANDIDATES]

async def pool_for_filters(task_id: str, filters: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """取得目前搜尋的候選池。距離範圍放寬到超出候選池的半徑時,用同樣方式重新查詢。
    回傳 None 代表還沒有搜尋過(例如 D 剛重啟)。"""
    pool = SEARCH_POOL.get(task_id)
    if not pool:
        return None
    max_m = _distance_limit(filters)
    if pool["radius_m"] is not None and (max_m is None or max_m > pool["radius_m"]):
        found, _ = await fetch_real_places(
            pool["raw_text"], pool["latitude"], pool["longitude"],
            max_m / 1000.0 if max_m else None, pool["rest_stop"], pool.get("category"),
        )
        if found is not None:
            pool["places"], pool["radius_m"] = found, max_m
    return pool["places"]

@app.post("/api/audio")
async def handle_audio_pipeline(
    file: UploadFile = File(...),
    task_id: str = Form("demo_task_001"),
    latitude: Optional[float] = Form(23.718645),
    longitude: Optional[float] = Form(120.573271),
    type: Optional[str] = Form(None),
    target_candidate_id: Optional[str] = Form(None)
):
    audio_bytes = await file.read()
    bc_intent_data = {}
    err_msg = ""
    clarification = None
    task = StateManager.get_or_create_task(task_id)

    form_data = {"language": "zh", "latitude": latitude, "longitude": longitude}
    if type: form_data["type"] = type
    if target_candidate_id: form_data["target_candidate_id"] = target_candidate_id
    context = {
        "candidate_ids": [str(candidate.get("id")) for candidate in task["candidates"]],
        "reference_type": type or "modify",
        # 「不用開太遠」採產品合理預設，避免 BC 的通用 300m 預設讓 Demo 幾乎必定空結果。
        "short_drive_distance_m": 3000,
    }
    form_data["context_json"] = json.dumps(context, ensure_ascii=False)

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            files = {"file": (file.filename, audio_bytes, file.content_type or "audio/wav")}
            bc_res = await client.post(f"{BC_API_URL}/api/intent", files=files, data=form_data)
            if bc_res.status_code == 200:
                bc_intent_data = bc_res.json()
            else:
                try:
                    bc_error = bc_res.json().get("error", {})
                    detail = bc_error.get("message") or ""
                    if bc_error.get("code") == "clarification_needed":
                        clarification = detail or "請再說明要操作哪一個候選地點"
                        bc_intent_data = {"intent": "clarify"}
                    err_msg = f"BC 端錯誤: HTTP {bc_res.status_code}" + (f" - {detail}" if detail else "")
                except ValueError:
                    err_msg = f"BC 端錯誤: HTTP {bc_res.status_code}"
    except Exception as e:
        err_msg = f"無法連線 BC 語音: {e}"
        bc_intent_data = {}

    raw_text = bc_intent_data.get("raw_text") or task.get("raw_text") or ""
    reference = bc_intent_data.get("reference", {})
    target_id = reference.get("target_candidate_id") or bc_intent_data.get("target_candidate_id")

    candidates = task["candidates"]

    # 處理「留下第 N 個」或指定候選
    if target_id and candidates:
        matched = [c for c in candidates if str(c.get("id")) == str(target_id)]
        if matched:
            candidates = matched
            selected_target = str(target_id)
        else:
            selected_target = UNSET
            clarification = "指定的候選已不在目前清單，請重新選擇"
    else:
        conditions = bc_intent_data.get("conditions") or {}
        intent = bc_intent_data.get("intent")
        category = bc_intent_data.get("category")
        # 每次新的語音搜尋都清掉上一輪條件，再套用這次明確說出的條件。
        merged = {**DEFAULT_FILTERS, **conditions}
        found, place_msg = None, ""
        # BC 出錯(沒有意圖資料)或不是找地點的語音:保留原候選,不重新搜尋
        if bc_intent_data and intent not in ("chat", "clarify"):
            # 搜尋半徑取自「最大行駛距離」條件,BC 的距離是直線距離
            max_m = _distance_limit(merged)
            rest_stop = category == "rest" or (category is None and intent == "search_rest_stop")
            found, place_msg = await fetch_real_places(
                raw_text, latitude, longitude, max_m / 1000.0 if max_m else None,
                rest_stop, category,
            )
            if found is not None:
                SEARCH_POOL[task_id] = {
                    "raw_text": raw_text, "latitude": latitude, "longitude": longitude,
                    "rest_stop": rest_stop, "category": category,
                    "radius_m": max_m, "places": found,
                }
        if found is not None:   # None = 沒有搜尋,或 BC 無法使用 → 保留原候選
            candidates = apply_filters(found, merged)
            selected_target = None
            if found and not candidates:
                place_msg = f"找到 {len(found)} 筆地點,但都不符合目前的篩選條件(室內/有座位/有餐飲/距離)"
        else:
            selected_target = UNSET
        if place_msg:
            err_msg = f"{err_msg} | {place_msg}" if err_msg else place_msg

    task = StateManager.update_task_state(
        task_id=task_id,
        intent=bc_intent_data.get("intent"),
        raw_text=raw_text,
        new_filters=merged if not target_id else None,
        new_candidates=candidates,
        selected_id=selected_target,
        comparison_text=None,
        clarification_needed=clarification,
        error_message=err_msg or None,
        cloud_status="processing" if candidates else "not_applicable",
        status="IN_PROGRESS",
    )

    await manager.broadcast(UIGenerator.build_ui_json(task))
    schedule_cloud_enhancement(task)
    return {
        "status": "ok",
        "version": task["version"],
        "candidates_count": len(candidates),
        # HTTP 也直接帶回 UI；即使 WebSocket 暫時斷線，App 仍能顯示本次結果。
        "ui": UIGenerator.build_ui_json(task),
    }


@app.post("/api/cloud/refresh")
async def refresh_cloud(task_id: str = "demo_task_001"):
    task = StateManager.get_or_create_task(task_id)
    if task.get("cloud_status") != "enhanced":
        applied = await apply_cloud_comparison(task_id, task["version"])
        task = StateManager.get_or_create_task(task_id)
        if not applied and task.get("cloud_status") == "processing":
            task = StateManager.update_task_state(task_id, cloud_status="local_only")
    return {
        "status": task.get("cloud_status") or "local_only",
        "version": task["version"],
        "ui": UIGenerator.build_ui_json(task),
    }


@app.get("/api/system/status")
async def system_status():
    async def reachable(url: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                return (await client.get(url)).status_code < 500
        except Exception:
            return False

    async def cloud_ready() -> bool:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{CLOUD_API_URL}/health")
            return response.status_code == 200 and response.json().get("status") == "ready"
        except Exception:
            return False

    bc_ok, cloud_ok = await asyncio.gather(reachable(f"{BC_API_URL}/api/places/info"), cloud_ready())
    return {"d": True, "bc": bc_ok, "cloud": cloud_ok, "mode": "hybrid" if cloud_ok else "offline"}

@app.get("/", response_class=HTMLResponse)
async def get_demo_dashboard():
    for path in (BASE_DIR / "dashboard.html", Path("dashboard.html")):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
    return "<h3>dashboard.html not found</h3>"

if __name__ == "__main__":
    uvicorn.run("server_d:app", host="0.0.0.0", port=8000, reload=True)
