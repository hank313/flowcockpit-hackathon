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

# 基準保底地點 (完全符合 A1 attributes 與 FakeAiBox 規格)
FALLBACK_PLACES = [
    {
        "id": "loc_001",
        "name": "星巴克 雲林斗六門市",
        "indoor": True,
        "has_seating": True,
        "has_food": True,
        "drive_distance_m": 2500,
        "drive_time_min": 4,
        "address": "雲林縣斗六市雲林路二段180號"
    },
    {
        "id": "loc_002",
        "name": "麥當勞-斗六雲林餐廳",
        "indoor": True,
        "has_seating": True,
        "has_food": True,
        "drive_distance_m": 1800,
        "drive_time_min": 3,
        "address": "雲林縣斗六市民生路"
    },
    {
        "id": "loc_003",
        "name": "河濱公園涼亭",
        "indoor": False,
        "has_seating": True,
        "has_food": False,
        "drive_distance_m": 2500,
        "drive_time_min": 5,
        "address": "雲林縣斗六市大學路三段"
    }
]

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
            initial_filters = {
                "indoor": True,
                "has_seating": True,
                "has_food": False,
                "max_drive_distance_m": 3000
            }
            cursor.execute("""
                INSERT INTO task_states VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task_id, 1, "search_rest_stop", "預設休息推薦",
                json.dumps(initial_filters),
                json.dumps(FALLBACK_PLACES, ensure_ascii=False),
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

        initial_filters = {
            "indoor": True,
            "has_seating": True,
            "has_food": False,
            "max_drive_distance_m": 3000
        }
        cursor.execute("""
            UPDATE task_states
            SET version = ?, intent = 'search_rest_stop', raw_text = '新任務開始',
                filters_json = ?, candidates_json = ?, selected_id = NULL,
                comparison_text = '', status = 'IN_PROGRESS', clarification_needed = NULL,
                error_message = '', updated_at = ?
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
        dist_m = int(p.get("distance_m") or 1500)
        drive_min = max(2, math.ceil((dist_m * 1.35 / 1000.0) / 35.0 * 60))
        cats = p.get("categories", [])
        matched = p.get("matched_tags", {})

        candidates.append({
            "id": p.get("osm_id", f"loc_{idx+1:03d}"),
            "name": p.get("name", "推薦休息點"),
            "indoor": "cafe" in cats or "food" in cats or "convenience" in cats,
            "has_seating": matched.get("bench") == "yes" or "rest" in cats,
            "has_food": "food" in cats or "cafe" in cats or "convenience" in cats,
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
                task = StateManager.update_task_state(task_id, new_filters=new_filters)

            # 對齊 A1 UserAction: confirm
            elif action in ["confirm", "CONFIRM_DESTINATION"]:
                cand_id = payload.get("candidate_id")
                task = StateManager.update_task_state(task_id, selected_id=str(cand_id) if cand_id else None, status="CONFIRMED")

            elif action == "RESET_TASK":
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
        # 向 BC /api/text 請求真實地點清單
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(
                    f"{BC_API_URL}/api/text",
                    json={"text": raw_text, "latitude": latitude, "longitude": longitude, "limit": 5}
                )
                if res.status_code == 200 and res.json().get("places"):
                    candidates = convert_bc_places_to_candidates(res.json()["places"])
                else:
                    candidates = FALLBACK_PLACES
        except Exception:
            candidates = FALLBACK_PLACES
        selected_target = None

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
