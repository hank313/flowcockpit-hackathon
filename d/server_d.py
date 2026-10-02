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

# BC 模組服務位址 (BC 啟動時請帶 --port 8001)
BC_API_URL = os.getenv("BC_API_URL", "http://127.0.0.1:8001")
# E 模組 (雲端增強) 位址
CLOUD_API_URL = os.getenv("CLOUD_API_URL", "http://127.0.0.1:8002")

# ==========================================
# 1. 資料庫初始化 (支援儲存外部動態 POI)
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 示範/預設地點表 (離線備用)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pois (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        is_indoor INTEGER NOT NULL,
        has_seating INTEGER NOT NULL,
        drive_km REAL NOT NULL,
        drive_minutes INTEGER NOT NULL,
        tags TEXT NOT NULL
    )
    """)

    # 任務狀態表 (新增動態地點快取動態支援)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS task_states (
        task_id TEXT PRIMARY KEY,
        version INTEGER NOT NULL,
        filters_json TEXT NOT NULL,
        candidates_json TEXT NOT NULL,     -- 完整儲存當前候選清單物件
        selected_id TEXT,                  -- 支援數字 ID 或 BC 的 osm_id (字串)
        comparison_text TEXT,
        status TEXT NOT NULL,
        updated_at REAL NOT NULL
    )
    """)

    cursor.execute("SELECT COUNT(*) FROM pois")
    if cursor.fetchone()[0] == 0:
        sample_pois = [
            (1, "星巴克 國道門市", 1, 1, 2.5, 4, "室內,空調,咖啡,有插座"),
            (2, "全家便利商店 休息站店", 1, 1, 1.2, 2, "室內,便利店,輕食,有座位"),
            (3, "林間步道觀景涼亭", 0, 1, 6.8, 11, "戶外,通風,風景好,有長椅"),
            (4, "國道服務區 主建築美食街", 1, 1, 3.0, 5, "室內,熱食,座位多,洗手間"),
            (5, "得來速 快速取餐點", 0, 0, 2.0, 3, "免下車,快速,外帶"),
            (6, "露天景觀咖啡座", 0, 1, 7.5, 12, "戶外遮陽,有座位,氣氛佳"),
            (7, "綠能生態停車休憩區", 0, 0, 1.0, 2, "戶外,停車方便,活動筋骨"),
            (8, "24H 自助圖書休息站", 1, 1, 4.5, 7, "室內安靜,冷氣,閱讀區,充電")
        ]
        cursor.executemany("INSERT INTO pois VALUES (?, ?, ?, ?, ?, ?, ?)", sample_pois)
        conn.commit()

    conn.close()

init_db()

# ==========================================
# 2. 任務狀態管理 (State Manager)
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
            initial_filters = {"indoor": True, "seating": True, "max_drive_min": 10}
            # 預設自本地備用資料撈取
            cursor.execute("SELECT * FROM pois WHERE is_indoor=1 LIMIT 4")
            raw_pois = cursor.fetchall()
            initial_candidates = []
            for r in raw_pois:
                initial_candidates.append({
                    "id": str(r[0]),
                    "name": r[1],
                    "tags": r[6].split(","),
                    "drive_distance_desc": f"行駛距離 {r[4]} 公里",
                    "drive_eta_desc": f"行駛時間約 {r[5]} 分鐘"
                })

            cursor.execute("""
                INSERT INTO task_states VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task_id, 1, json.dumps(initial_filters),
                json.dumps(initial_candidates, ensure_ascii=False),
                None, "", "IN_PROGRESS", time.time()
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
    def update_task_state(
        task_id: str,
        new_filters: Optional[Dict[str, Any]] = None,
        new_candidates: Optional[List[Dict[str, Any]]] = None,
        selected_id: Optional[str] = None,
        comparison_text: Optional[str] = None,
        status: Optional[str] = None
    ) -> Dict[str, Any]:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM task_states WHERE task_id = ?", (task_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return StateManager.get_or_create_task(task_id)

        current_ver = row["version"]
        current_filters = json.loads(row["filters_json"])
        current_candidates = json.loads(row["candidates_json"])
        current_selected = row["selected_id"]
        current_comp_text = row["comparison_text"]
        current_status = row["status"]

        if new_filters is not None:
            current_filters.update(new_filters)
            current_ver += 1

        if new_candidates is not None:
            current_candidates = new_candidates
            current_ver += 1

        if selected_id is not None:
            current_selected = str(selected_id)
            current_ver += 1

        if comparison_text is not None:
            current_comp_text = comparison_text
            current_ver += 1

        if status:
            current_status = status
            current_ver += 1

        cursor.execute("""
            UPDATE task_states
            SET version = ?, filters_json = ?, candidates_json = ?, 
                selected_id = ?, comparison_text = ?, status = ?, updated_at = ?
            WHERE task_id = ?
        """, (
            current_ver,
            json.dumps(current_filters, ensure_ascii=False),
            json.dumps(current_candidates, ensure_ascii=False),
            current_selected,
            current_comp_text,
            current_status,
            time.time(),
            task_id
        ))
        conn.commit()
        conn.close()
        return StateManager.get_or_create_task(task_id)

# ==========================================
# 3. 生成式 UI 組裝器
# ==========================================
class UIGenerator:
    @staticmethod
    def build_ui_json(task: Dict[str, Any]) -> Dict[str, Any]:
        filters = task["filters"]
        ui_components = [
            {
                "component": "filter_controls",
                "data": {
                    "filters": [
                        {"id": "indoor", "label": "室內空間", "value": filters.get("indoor", True), "type": "TOGGLE"},
                        {"id": "seating", "label": "有座位", "value": filters.get("seating", True), "type": "TOGGLE"},
                        {"id": "max_drive_min", "label": "車程範圍", "value": f"<= {filters.get('max_drive_min', 10)} 分鐘", "type": "STEPPER"}
                    ]
                }
            },
            {
                "component": "candidate_list",
                "data": {
                    "selected_id": task["selected_id"],
                    "items": task["candidates"]  # 直接取用動態更新的候選地點
                }
            }
        ]

        if task.get("comparison_text") or task.get("status") == "CONFIRMED":
            ui_components.append({
                "component": "comparison_panel",
                "data": {
                    "visible": True,
                    "status": task["status"],
                    "selected_id": task["selected_id"],
                    "cloud_enhanced_text": task.get("comparison_text", "")
                }
            })

        return {
            "task_id": task["task_id"],
            "version": task["version"],
            "type": "UI_UPDATE",
            "timestamp": int(time.time()),
            "payload": {
                "layout": "VERTICAL",
                "components": ui_components
            }
        }

# ==========================================
# 4. FastAPI & WebSocket
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

@app.get("/", response_class=HTMLResponse)
async def get_demo_dashboard():
    for path in ("dashboard.html", "d/dashboard.html"):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
    return "<h3>dashboard.html not found</h3>"

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        current_task = StateManager.get_or_create_task("demo_task_001")
        initial_ui = UIGenerator.build_ui_json(current_task)
        await websocket.send_text(json.dumps(initial_ui, ensure_ascii=False))

        while True:
            raw_text = await websocket.receive_text()
            data = json.loads(raw_text)
            
            msg_type = data.get("type")
            payload = data.get("payload", {})
            task_id = data.get("task_id", "demo_task_001")

            if msg_type == "TOUCH_ACTION":
                action = payload.get("action")
                if action == "SELECT_CANDIDATE":
                    task = StateManager.update_task_state(task_id, selected_id=str(payload.get("candidate_id")))
                elif action == "CONFIRM_DESTINATION":
                    task = StateManager.update_task_state(task_id, status="CONFIRMED")
                else:
                    task = StateManager.get_or_create_task(task_id)

                await manager.broadcast(UIGenerator.build_ui_json(task))

            elif msg_type == "SYNC_REQUEST":
                task = StateManager.get_or_create_task(task_id)
                await websocket.send_text(json.dumps(UIGenerator.build_ui_json(task), ensure_ascii=False))

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WS Error: {e}")
        manager.disconnect(websocket)

# ==========================================
# 5. 端到端音訊/意圖/離線優先整合
# ==========================================

def convert_bc_places_to_candidates(bc_places: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """將 BC 回傳的真實雲林地點，轉為符合 UI JSON 規範的行駛資訊結構"""
    candidates = []
    for idx, p in enumerate(bc_places):
        dist_m = p.get("distance_m") or 2000.0
        # 大圓距離換算預估行駛公里與時間
        drive_km = round((dist_m * 1.35) / 1000.0, 1)
        drive_min = max(2, math.ceil(drive_km / 35.0 * 60))

        tags = [p.get("district", "雲林")]
        matched = p.get("matched_tags", {})
        if matched.get("amenity"): tags.append(matched["amenity"])
        if matched.get("bench") == "yes": tags.append("有長椅")

        candidates.append({
            "id": p.get("osm_id", str(idx + 1)),
            "name": p.get("name", "推薦休息點"),
            "tags": tags,
            "drive_distance_desc": f"行駛距離 {drive_km} 公里",
            "drive_eta_desc": f"行駛時間約 {drive_min} 分鐘",
            "latitude": p.get("latitude"),
            "longitude": p.get("longitude"),
            "address": p.get("address", "")
        })
    return candidates

async def trigger_cloud_enhancement(task_id: str, base_version: int, candidates: List[Dict[str, Any]]):
    """雲端非同步增強 (斷網自動跳過，不卡住本地操作)"""
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            res = await client.post(
                f"{CLOUD_API_URL}/api/cloud_compare",
                json={"task_id": task_id, "base_version": base_version, "candidates": candidates}
            )
            if res.status_code == 200:
                cloud_data = res.json()
                comp_text = cloud_data.get("comparison_text", "")
                await apply_cloud_comparison({
                    "task_id": task_id,
                    "base_version": base_version,
                    "comparison_text": comp_text
                })
    except Exception:
        # 完全離線時正常略過，維持本地 AI 結果
        pass

@app.post("/api/audio")
async def handle_audio_pipeline(
    file: UploadFile = File(...),
    task_id: str = Form("demo_task_001"),
    latitude: Optional[float] = Form(23.71),
    longitude: Optional[float] = Form(120.54)
):
    """
    接收音訊 -> 送 BC 本地搜尋 -> 立即推播本地真地點 -> 非同步嘗試雲端
    """
    audio_bytes = await file.read()
    candidates = []

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            files = {"file": (file.filename, audio_bytes, file.content_type or "audio/m4a")}
            data = {"language": "zh", "latitude": latitude, "longitude": longitude, "limit": 5}
            bc_res = await client.post(f"{BC_API_URL}/api/audio", files=files, data=data)
            if bc_res.status_code == 200:
                bc_data = bc_res.json()
                places = bc_data.get("places", [])
                candidates = convert_bc_places_to_candidates(places)
    except Exception as e:
        print(f"呼叫 BC 失敗，使用本地預設: {e}")

    # 更新任務候選地點並廣播
    if candidates:
        task = StateManager.update_task_state(task_id, new_candidates=candidates)
    else:
        task = StateManager.get_or_create_task(task_id)

    ui_json = UIGenerator.build_ui_json(task)
    await manager.broadcast(ui_json)

    # 嘗試連網強化 (離線自動略過)
    asyncio.create_task(trigger_cloud_enhancement(task_id, task["version"], task["candidates"]))

    return {"status": "ok", "task_id": task_id, "version": task["version"], "count": len(task["candidates"])}

@app.post("/api/intent")
@app.post("/internal/apply_bc_filters")
async def handle_intent_and_filters(req: Dict[str, Any]):
    task_id = req.get("task_id", "demo_task_001")
    # 若直接傳入 BC 的 places 清單
    if "places" in req:
        candidates = convert_bc_places_to_candidates(req["places"])
        task = StateManager.update_task_state(task_id, new_candidates=candidates)
    else:
        filters = req.get("filters", {})
        task = StateManager.update_task_state(task_id, new_filters=filters)

    ui_json = UIGenerator.build_ui_json(task)
    await manager.broadcast(ui_json)

    asyncio.create_task(trigger_cloud_enhancement(task_id, task["version"], task["candidates"]))
    return {"status": "ok", "version": task["version"]}

@app.post("/internal/apply_cloud_comparison")
async def apply_cloud_comparison(req: Dict[str, Any]):
    task_id = req.get("task_id", "demo_task_001")
    req_version = req.get("base_version")
    comp_text = req.get("comparison_text", "")

    task = StateManager.get_or_create_task(task_id)
    if req_version and req_version < task["version"]:
        return {"status": "discarded", "reason": "stale_version"}

    updated_task = StateManager.update_task_state(task_id, comparison_text=comp_text)
    await manager.broadcast(UIGenerator.build_ui_json(updated_task))
    return {"status": "applied", "version": updated_task["version"]}

if __name__ == "__main__":
    uvicorn.run("server_d:app", host="0.0.0.0", port=8000, reload=True)
