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

# BC 與 E 模組端點設定
BC_API_URL = os.getenv("BC_API_URL", "http://127.0.0.1:8001")
CLOUD_API_URL = os.getenv("CLOUD_API_URL", "http://127.0.0.1:8002")

# ==========================================
# 1. 資料庫初始化 (移除假資料，僅儲存狀態)
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 任務狀態表 (持久化任務、意圖、篩選條件與動態候選名單)
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
        updated_at REAL NOT NULL
    )
    """)
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
            cursor.execute("""
                INSERT INTO task_states VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task_id, 1, "search_rest_stop", "", json.dumps(initial_filters),
                json.dumps([]), None, "", "IN_PROGRESS", time.time()
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
        intent: Optional[str] = None,
        raw_text: Optional[str] = None,
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

        cursor.execute("""
            UPDATE task_states
            SET version = ?, intent = ?, raw_text = ?, filters_json = ?, 
                candidates_json = ?, selected_id = ?, comparison_text = ?, 
                status = ?, updated_at = ?
            WHERE task_id = ?
        """, (
            current_ver, current_intent, current_raw_text,
            json.dumps(current_filters, ensure_ascii=False),
            json.dumps(current_candidates, ensure_ascii=False),
            current_selected, current_comp_text, current_status,
            time.time(), task_id
        ))
        conn.commit()
        conn.close()
        return StateManager.get_or_create_task(task_id)

# ==========================================
# 3. 生成式 UI 組裝器 (A1 JSON 規範)
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
                    "items": task["candidates"]
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
# 5. 端到端流程：HMI -> BC (/api/intent) -> 雲端 AI (E)
# ==========================================

async def query_cloud_ai_for_places(task_id: str, base_version: int, intent_info: Dict[str, Any]):
    """將 BC 抽出的意圖與經緯度發送給雲端 AI 尋找推薦地點及決策說明"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(
                f"{CLOUD_API_URL}/api/cloud_search_places",
                json={
                    "task_id": task_id,
                    "base_version": base_version,
                    "intent": intent_info.get("intent"),
                    "raw_text": intent_info.get("raw_text"),
                    "conditions": intent_info.get("conditions", {}),
                    "latitude": intent_info.get("latitude"),
                    "longitude": intent_info.get("longitude")
                }
            )
            if res.status_code == 200:
                cloud_data = res.json()
                new_candidates = cloud_data.get("candidates", [])
                comparison_text = cloud_data.get("comparison_text", "")
                
                # 檢查版本是否過期
                task = StateManager.get_or_create_task(task_id)
                if base_version < task["version"]:
                    return

                updated_task = StateManager.update_task_state(
                    task_id=task_id,
                    new_candidates=new_candidates if new_candidates else None,
                    comparison_text=comparison_text
                )
                await manager.broadcast(UIGenerator.build_ui_json(updated_task))
    except Exception as e:
        print(f"雲端 AI 呼叫略過 (離線模式或超時): {e}")

@app.post("/api/audio")
async def handle_audio_pipeline(
    file: UploadFile = File(...),
    task_id: str = Form("demo_task_001"),
    latitude: Optional[float] = Form(23.718645),
    longitude: Optional[float] = Form(120.573271),
    type: Optional[str] = Form(None),
    target_candidate_id: Optional[str] = Form(None)
):
    """
    1. 接收來自 HMI 的語音及座標
    2. 呼叫 BC 新端點 POST /api/intent 取得 BC -> D JSON
    3. 更新 D 模組狀態並將意圖與座標轉發雲端 AI
    """
    audio_bytes = await file.read()
    bc_intent_data = {}

    form_data = {
        "language": "zh",
        "latitude": latitude,
        "longitude": longitude
    }
    if type:
        form_data["type"] = type
    if target_candidate_id:
        form_data["target_candidate_id"] = target_candidate_id

    # 轉發至 BC 的 POST /api/intent
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            files = {"file": (file.filename, audio_bytes, file.content_type or "audio/wav")}
            bc_res = await client.post(f"{BC_API_URL}/api/intent", files=files, data=form_data)
            if bc_res.status_code == 200:
                bc_intent_data = bc_res.json()
    except Exception as e:
        print(f"呼叫 BC /api/intent 失敗: {e}")
        bc_intent_data = {
            "intent": "search_rest_stop",
            "raw_text": "語音解析失敗，啟動備用語音意圖",
            "latitude": latitude,
            "longitude": longitude
        }

    # 依 BC 意圖更新任務狀態
    extracted_conditions = bc_intent_data.get("conditions", {})
    task = StateManager.update_task_state(
        task_id=task_id,
        intent=bc_intent_data.get("intent"),
        raw_text=bc_intent_data.get("raw_text"),
        new_filters=extracted_conditions if extracted_conditions else None
    )

    # 先推播一次 UI 讓 HMI 呈現說明的 raw_text
    ui_json = UIGenerator.build_ui_json(task)
    await manager.broadcast(ui_json)

    # 帶著 BC 輸出的意圖與經緯度非同步發給雲端 AI
    asyncio.create_task(query_cloud_ai_for_places(task_id, task["version"], bc_intent_data))

    return {
        "status": "ok",
        "task_id": task_id,
        "version": task["version"],
        "bc_intent": bc_intent_data
    }

@app.post("/internal/apply_cloud_comparison")
async def apply_cloud_comparison(req: Dict[str, Any]):
    task_id = req.get("task_id", "demo_task_001")
    req_version = req.get("base_version")
    comp_text = req.get("comparison_text", "")
    new_candidates = req.get("candidates")

    task = StateManager.get_or_create_task(task_id)
    if req_version and req_version < task["version"]:
        return {"status": "discarded", "reason": "stale_version"}

    updated_task = StateManager.update_task_state(
        task_id=task_id,
        new_candidates=new_candidates,
        comparison_text=comp_text
    )
    await manager.broadcast(UIGenerator.build_ui_json(updated_task))
    return {"status": "applied", "version": updated_task["version"]}

if __name__ == "__main__":
    uvicorn.run("server_d:app", host="0.0.0.0", port=8000, reload=True)
