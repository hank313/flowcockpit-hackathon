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
# 1. 資料庫初始化 (具備保底種子資料，保證絕不為空)
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
        error_message TEXT,
        updated_at REAL NOT NULL
    )
    """)
    conn.commit()
    conn.close()

init_db()

# 雲林基準保底地點 (以防 BC 與 E 皆未啟動時前端白畫面)
FALLBACK_PLACES = [
    {
        "id": "node/101",
        "name": "星巴克 雲林斗六門市",
        "tags": ["斗六市", "咖啡店", "休息設施", "室內", "有座位"],
        "drive_distance_desc": "行駛距離 2.5 公里",
        "drive_eta_desc": "行駛時間約 4 分鐘",
        "latitude": 23.7021,
        "longitude": 120.5312,
        "address": "雲林縣斗六市雲林路二段180號"
    },
    {
        "id": "node/102",
        "name": "全家便利商店 斗六民生店",
        "tags": ["斗六市", "便利商店", "休息設施", "室內", "有座位"],
        "drive_distance_desc": "行駛距離 1.2 公里",
        "drive_eta_desc": "行駛時間約 2 分鐘",
        "latitude": 23.7095,
        "longitude": 120.5432,
        "address": "雲林縣斗六市民生路"
    },
    {
        "id": "way/203",
        "name": "斗六人文公園 休憩步道",
        "tags": ["斗六市", "公園", "休息設施", "戶外", "有座位"],
        "drive_distance_desc": "行駛距離 4.2 公里",
        "drive_eta_desc": "行駛時間約 7 分鐘",
        "latitude": 23.6934,
        "longitude": 120.5345,
        "address": "雲林縣斗六市大學路三段"
    }
]

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
            cursor.execute("""
                INSERT INTO task_states VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task_id, 1, "search_rest_stop", "預設休息推薦",
                json.dumps(initial_filters),
                json.dumps(FALLBACK_PLACES, ensure_ascii=False),
                None, "", "IN_PROGRESS", "", time.time()
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
        """解決事項 #6: 開新任務"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT version FROM task_states WHERE task_id = ?", (task_id,))
        row = cursor.fetchone()
        next_ver = (row["version"] + 1) if row else 1

        initial_filters = {"indoor": True, "seating": True, "max_drive_min": 10}
        cursor.execute("""
            UPDATE task_states
            SET version = ?, intent = 'search_rest_stop', raw_text = '新任務開始',
                filters_json = ?, candidates_json = ?, selected_id = NULL,
                comparison_text = '', status = 'IN_PROGRESS', error_message = '',
                updated_at = ?
            WHERE task_id = ?
        """, (
            next_ver, json.dumps(initial_filters),
            json.dumps(FALLBACK_PLACES, ensure_ascii=False),
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
        current_status = status if status is not None else row["status"]
        current_err = error_message if error_message is not None else row["error_message"]

        cursor.execute("""
            UPDATE task_states
            SET version = ?, intent = ?, raw_text = ?, filters_json = ?, 
                candidates_json = ?, selected_id = ?, comparison_text = ?, 
                status = ?, error_message = ?, updated_at = ?
            WHERE task_id = ?
        """, (
            current_ver, current_intent, current_raw_text,
            json.dumps(current_filters, ensure_ascii=False),
            json.dumps(current_candidates, ensure_ascii=False),
            current_selected, current_comp_text, current_status, current_err,
            time.time(), task_id
        ))
        conn.commit()
        conn.close()
        return StateManager.get_or_create_task(task_id)

# ==========================================
# 3. 生成式 UI 組裝器 (解決事項 #2 欄位統一)
# ==========================================
class UIGenerator:
    @staticmethod
    def build_ui_json(task: Dict[str, Any]) -> Dict[str, Any]:
        filters = task["filters"]
        ui_components = [
            {
                "component": "filter_controls",
                "data": {
                    "raw_text": task.get("raw_text", ""),
                    "error_message": task.get("error_message", ""),
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
                    "items": task["candidates"]  # 保證非空清單
                }
            }
        ]

        # 僅在有比較文字或已確認狀態時顯示比較面板 (解決事項 #6 彈出問題)
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

def convert_bc_places_to_candidates(bc_places: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """將 BC 回傳的真實雲林地點轉換為統一單位（公里、分鐘）"""
    candidates = []
    for idx, p in enumerate(bc_places):
        dist_m = p.get("distance_m") or 1500.0
        drive_km = round((dist_m * 1.35) / 1000.0, 1)
        drive_min = max(2, math.ceil(drive_km / 35.0 * 60))

        tags = [p.get("district", "雲林")]
        matched = p.get("matched_tags", {})
        if matched.get("amenity"): tags.append(matched["amenity"])
        if matched.get("bench") == "yes": tags.append("有長椅")

        candidates.append({
            "id": p.get("osm_id", f"poi_{idx+1}"),
            "name": p.get("name", "推薦休息點"),
            "tags": tags,
            "drive_distance_desc": f"行駛距離 {drive_km} 公里",
            "drive_eta_desc": f"行駛時間約 {drive_min} 分鐘",
            "latitude": p.get("latitude"),
            "longitude": p.get("longitude"),
            "address": p.get("address", "")
        })
    return candidates

# ==========================================
# 4. WebSocket 管理 (解決事項 #4 UPDATE_FILTER)
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
        await websocket.send_text(json.dumps(UIGenerator.build_ui_json(current_task), ensure_ascii=False))

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
                elif action == "UPDATE_FILTER":
                    # 解決事項 #4: 處理條件變更
                    task = StateManager.update_task_state(task_id, new_filters=payload.get("filters"))
                elif action == "CONFIRM_DESTINATION":
                    task = StateManager.update_task_state(task_id, status="CONFIRMED")
                elif action == "RESET_TASK":
                    # 解決事項 #6: 開新任務
                    task = StateManager.reset_task(task_id)
                else:
                    task = StateManager.get_or_create_task(task_id)

                await manager.broadcast(UIGenerator.build_ui_json(task))

            elif msg_type == "SYNC_REQUEST":
                task = StateManager.get_or_create_task(task_id)
                await websocket.send_text(json.dumps(UIGenerator.build_ui_json(task), ensure_ascii=False))

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        manager.disconnect(websocket)

# ==========================================
# 5. 音訊鏈路整合 (解決事項 #1, #3, #7)
# ==========================================

async def fetch_bc_places_fallback(keyword: str, lat: float, lon: float) -> List[Dict[str, Any]]:
    """向 BC 的 /api/text 請求真實 OSM 地點清單"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.post(
                f"{BC_API_URL}/api/text",
                json={"text": keyword, "latitude": lat, "longitude": lon, "limit": 5}
            )
            if res.status_code == 200:
                data = res.json()
                if data.get("places"):
                    return convert_bc_places_to_candidates(data["places"])
    except Exception:
        pass
    return FALLBACK_PLACES

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

    # 1. 呼叫 BC /api/intent 提取意圖
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            files = {"file": (file.filename, audio_bytes, file.content_type or "audio/wav")}
            bc_res = await client.post(f"{BC_API_URL}/api/intent", files=files, data=form_data)
            if bc_res.status_code == 200:
                bc_intent_data = bc_res.json()
            else:
                err_msg = f"BC 端回傳錯誤碼: {bc_res.status_code}"
    except Exception as e:
        # 解決事項 #7: 不靜默吞噬錯誤
        err_msg = f"無法連線 BC 語音服務: {str(e)}"
        bc_intent_data = {
            "intent": "search_rest_stop",
            "raw_text": "本地語音解析離線",
            "conditions": {}
        }

    raw_text = bc_intent_data.get("raw_text", "找休息處")
    
    # 2. 解決事項 #3: 處理「留下第 N 個」或指定候選對象
    reference = bc_intent_data.get("reference", {})
    target_id = reference.get("target_candidate_id") or bc_intent_data.get("target_candidate_id")

    task = StateManager.get_or_create_task(task_id)
    candidates = task["candidates"]

    if target_id and candidates:
        # 使用者表示要選中或只留下該目標
        matched = [c for c in candidates if c["id"] == target_id]
        if matched:
            candidates = matched
            selected_target = target_id
        else:
            selected_target = target_id
    else:
        # 解決事項 #1: 重新查詢保證候選清單不為空
        candidates = await fetch_bc_places_fallback(raw_text, latitude, longitude)
        selected_target = None

    # 更新狀態
    task = StateManager.update_task_state(
        task_id=task_id,
        intent=bc_intent_data.get("intent"),
        raw_text=raw_text,
        new_filters=bc_intent_data.get("conditions"),
        new_candidates=candidates,
        selected_id=selected_target,
        error_message=err_msg
    )

    # 3. 立即推播 UI，保障本地離線能立即看到結果
    await manager.broadcast(UIGenerator.build_ui_json(task))

    # 4. 背景嘗試雲端 E（斷網或無 E 服務時自動略過，不卡住）
    asyncio.create_task(try_cloud_comparison(task_id, task["version"], candidates))

    return {"status": "ok", "version": task["version"], "candidates_count": len(candidates), "error": err_msg}

async def try_cloud_comparison(task_id: str, base_version: int, candidates: List[Dict[str, Any]]):
    """雲端 E 服務嘗試"""
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            res = await client.post(
                f"{CLOUD_API_URL}/api/cloud_compare",
                json={"task_id": task_id, "candidates": candidates}
            )
            if res.status_code == 200:
                data = res.json()
                task = StateManager.get_or_create_task(task_id)
                if base_version == task["version"]:
                    updated = StateManager.update_task_state(task_id, comparison_text=data.get("comparison_text", ""))
                    await manager.broadcast(UIGenerator.build_ui_json(updated))
    except Exception:
        pass

@app.get("/", response_class=HTMLResponse)
async def get_demo_dashboard():
    for path in ("dashboard.html", "d/dashboard.html"):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
    return "<h3>dashboard.html not found</h3>"

if __name__ == "__main__":
    uvicorn.run("server_d:app", host="0.0.0.0", port=8000, reload=True)
