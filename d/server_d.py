import asyncio
import json
import math
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional
import httpx
from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import uvicorn

DB_PATH = "flowcockpit.db"
BC_API_URL = os.getenv("BC_API_URL", "http://127.0.0.1:8001")
CLOUD_API_URL = os.getenv("CLOUD_API_URL", "http://127.0.0.1:8002")

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
        updated_at REAL NOT NULL
    )
    """)
    conn.commit()
    conn.close()

init_db()

# 候選地點一律來自 BC 的本機 OSM 資料庫(實際地點),不使用示範資料。
# 新任務在第一次語音查詢之前候選為空。

# 預設條件。室內/有座位/有餐飲三個開關:開 = 只顯示有該屬性的地點,關 = 只顯示沒有該屬性的地點。
# 三個預設都是開,畫面上的開關狀態才與預設顯示的候選一致(餐廳、咖啡店:室內、有座位、有餐飲)。
DEFAULT_FILTERS = {
    "indoor": True,
    "has_seating": True,
    "has_food": True,
    "max_drive_distance_m": 3000,
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
                INSERT INTO task_states VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task_id, 1, "search_rest_stop", "預設休息推薦",
                json.dumps(initial_filters),
                json.dumps([]),
                None, "", "IN_PROGRESS", None, "", time.time()
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
                error_message = '', updated_at = ?
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
        selected_id: Optional[str] = None,
        comparison_text: Optional[str] = None,
        clarification_needed: Optional[str] = None,
        status: Optional[str] = None,
        error_message: Optional[str] = None
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
        current_selected = selected_id if selected_id is not None else row["selected_id"]
        current_comp_text = comparison_text if comparison_text is not None else row["comparison_text"]
        current_clarify = clarification_needed if clarification_needed is not None else row["clarification_needed"]
        current_status = status if status is not None else row["status"]
        current_err = error_message if error_message is not None else row["error_message"]

        cursor.execute("""
            UPDATE task_states
            SET version = ?, intent = ?, raw_text = ?, filters_json = ?, 
                candidates_json = ?, selected_id = ?, comparison_text = ?, 
                clarification_needed = ?, status = ?, error_message = ?, updated_at = ?
            WHERE task_id = ?
        """, (
            current_ver, current_intent, current_raw_text,
            json.dumps(current_filters, ensure_ascii=False),
            json.dumps(current_candidates, ensure_ascii=False),
            current_selected, current_comp_text, current_clarify, current_status, current_err,
            time.time(), task_id
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
                        "drive_distance_m": p.get("drive_distance_m", 1500)
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
                    "confirm_enabled": True
                }
            })

        payload = {
            "components": components,
            "clarification_needed": task.get("clarification_needed") or None
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
                task = StateManager.update_task_state(task_id, selected_id=new_sel)

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
                new_selected = None if str(task.get("selected_id")) in kept_ids else ""   # 已選的被篩掉就清除選取
                task = StateManager.update_task_state(
                    task_id, new_filters=new_filters, new_candidates=new_candidates, selected_id=new_selected
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

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)

# ==========================================
# 5. 音訊與 BC 鏈路處理
# ==========================================

# BC 的「休息設施」類別(長椅、野餐桌)在 OSM 很稀疏,實測雲科大附近 3 公里內為 0 筆,
# 所以「找休息地點」改查這幾類常見的休息場所,依距離合併。
REST_STOP_QUERIES = ["找休息地點", "找咖啡店", "找便利商店", "找公園", "找餐廳"]
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
                            radius_km: Optional[float], rest_stop: bool):
    """向 BC /api/text 取得實際地點(來自 BC 本機 OSM 資料庫)。
    rest_stop=True:找休息地點(意圖是休息,或語音含條件而 BC 不替 D 查地點),查常見休息類型並依距離合併。
    rest_stop=False:照使用者說的話查(例如「找咖啡店」)。
    回傳 (places, message):places 是依距離排序的候選池(尚未套用篩選條件),
    None 代表 BC 無法使用,呼叫端應保留原候選。"""
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
    False = 只留沒有該屬性的地點(例如關閉「室內」只顯示室外);沒有這個條件(None)則不限。
    行駛距離上限是直線距離。"""
    max_m = _distance_limit(filters)
    result = []
    for c in places:
        if max_m is not None and c.get("drive_distance_m", 0) > max_m:
            continue
        if any(
            filters.get(key) in (True, False) and bool(c.get(key)) != filters[key]
            for key in ("indoor", "has_seating", "has_food")
        ):
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
            max_m / 1000.0 if max_m else None, pool["rest_stop"],
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

    form_data = {"language": "zh", "latitude": latitude, "longitude": longitude}
    if type: form_data["type"] = type
    if target_candidate_id: form_data["target_candidate_id"] = target_candidate_id

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            files = {"file": (file.filename, audio_bytes, file.content_type or "audio/wav")}
            bc_res = await client.post(f"{BC_API_URL}/api/intent", files=files, data=form_data)
            if bc_res.status_code == 200:
                bc_intent_data = bc_res.json()
            else:
                err_msg = f"BC 端錯誤: HTTP {bc_res.status_code}"
    except Exception as e:
        err_msg = f"無法連線 BC 語音: {e}"
        bc_intent_data = {"intent": "search_rest_stop", "raw_text": "找休息地點"}

    raw_text = bc_intent_data.get("raw_text", "找休息處")
    reference = bc_intent_data.get("reference", {})
    target_id = reference.get("target_candidate_id") or bc_intent_data.get("target_candidate_id")

    task = StateManager.get_or_create_task(task_id)
    candidates = task["candidates"]

    # 處理「留下第 N 個」或指定候選
    if target_id and candidates:
        matched = [c for c in candidates if str(c.get("id")) == str(target_id)]
        if matched:
            candidates = matched
            selected_target = str(target_id)
        else:
            selected_target = str(target_id)
    else:
        conditions = bc_intent_data.get("conditions") or {}
        intent = bc_intent_data.get("intent")
        merged = {**task["filters"], **conditions}   # 語音條件優先於目前設定
        found, place_msg = None, ""
        # BC 出錯(沒有意圖資料)或不是找地點的語音:保留原候選,不重新搜尋
        if bc_intent_data and intent not in ("chat", "clarify"):
            # 搜尋半徑取自「最大行駛距離」條件,BC 的距離是直線距離
            max_m = _distance_limit(merged)
            rest_stop = intent == "search_rest_stop" or bool(conditions)
            found, place_msg = await fetch_real_places(
                raw_text, latitude, longitude, max_m / 1000.0 if max_m else None, rest_stop
            )
            if found is not None:
                SEARCH_POOL[task_id] = {
                    "raw_text": raw_text, "latitude": latitude, "longitude": longitude,
                    "rest_stop": rest_stop, "radius_m": max_m, "places": found,
                }
        if found is not None:   # None = 沒有搜尋,或 BC 無法使用 → 保留原候選
            candidates = apply_filters(found, merged)
            selected_target = ""    # 重新搜尋後清除舊選取(None 代表不變更)
            if found and not candidates:
                place_msg = f"找到 {len(found)} 筆地點,但都不符合目前的篩選條件(室內/有座位/有餐飲/距離)"
        else:
            selected_target = None
        if place_msg:
            err_msg = f"{err_msg} | {place_msg}" if err_msg else place_msg

    task = StateManager.update_task_state(
        task_id=task_id,
        intent=bc_intent_data.get("intent"),
        raw_text=raw_text,
        new_filters=bc_intent_data.get("conditions"),
        new_candidates=candidates,
        selected_id=selected_target,
        error_message=err_msg
    )

    await manager.broadcast(UIGenerator.build_ui_json(task))
    return {"status": "ok", "version": task["version"], "candidates_count": len(candidates)}

@app.get("/", response_class=HTMLResponse)
async def get_demo_dashboard():
    for path in ("dashboard.html", "d/dashboard.html"):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
    return "<h3>dashboard.html not found</h3>"

if __name__ == "__main__":
    uvicorn.run("server_d:app", host="0.0.0.0", port=8000, reload=True)
