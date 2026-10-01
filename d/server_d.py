import asyncio
import json
import sqlite3
import time
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn

DB_PATH = "flowcockpit.db"

# ==========================================
# 1. 資料庫初始化 (示範資料與任務狀態表)
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 示範地點表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pois (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        is_indoor INTEGER NOT NULL,      -- 1: 室內, 0: 室外
        has_seating INTEGER NOT NULL,    -- 1: 有座, 0: 無座
        walk_minutes INTEGER NOT NULL,   -- 步行分鐘
        drive_minutes INTEGER NOT NULL,  -- 開車/行程時間
        tags TEXT NOT NULL               -- 逗號分隔標籤
    )
    """)

    # 任務狀態表 (支援中斷恢復與版本追蹤)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS task_states (
        task_id TEXT PRIMARY KEY,
        version INTEGER NOT NULL,
        filters_json TEXT NOT NULL,
        candidate_ids_json TEXT NOT NULL,
        selected_id INTEGER,
        comparison_text TEXT,
        status TEXT NOT NULL,            -- 'IN_PROGRESS', 'CONFIRMED'
        updated_at REAL NOT NULL
    )
    """)

    # 寫入 8 筆情境示範資料 (若無資料)
    cursor.execute("SELECT COUNT(*) FROM pois")
    if cursor.fetchone()[0] == 0:
        sample_pois = [
            (1, "星巴克 國道門市", 1, 1, 2, 5, "室內,空調,咖啡,有插座"),
            (2, "全家便利商店 休息站店", 1, 1, 1, 3, "室內,便利店,輕食,有座位"),
            (3, "林間步道觀景涼亭", 0, 1, 8, 12, "戶外,通風,風景好,有長椅"),
            (4, "國道服務區 主建築美食街", 1, 1, 3, 6, "室內,熱食,座位多,洗手間"),
            (5, "得來速 快速取餐點", 0, 0, 0, 4, "免下車,快速,外帶"),
            (6, "露天景觀咖啡座", 0, 1, 5, 10, "戶外遮陽,有座位,氣氛佳"),
            (7, "綠能生態停車休憩區", 0, 0, 1, 2, "戶外,停車方便,活動筋骨"),
            (8, "24H 自助圖書休息站", 1, 1, 4, 8, "室內安靜,冷氣,閱讀區,充電")
        ]
        cursor.executemany(
            "INSERT INTO pois VALUES (?, ?, ?, ?, ?, ?, ?)", sample_pois
        )
        conn.commit()

    conn.close()

init_db()

# ==========================================
# 2. 任務狀態管理 (State Manager)
# ==========================================
class StateManager:
    @staticmethod
    def get_or_create_task(task_id: str = "default_task") -> Dict[str, Any]:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM task_states WHERE task_id = ?", (task_id,))
        row = cursor.fetchone()
        
        if not row:
            initial_filters = {"indoor": True, "seating": True, "max_walk_min": 10}
            candidates = StateManager.query_candidates(conn, initial_filters)
            cursor.execute("""
                INSERT INTO task_states VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task_id,
                1,
                json.dumps(initial_filters),
                json.dumps([c["id"] for c in candidates]),
                None,
                "",
                "IN_PROGRESS",
                time.time()
            ))
            conn.commit()
            cursor.execute("SELECT * FROM task_states WHERE task_id = ?", (task_id,))
            row = cursor.fetchone()
            
        task = dict(row)
        task["filters"] = json.loads(task["filters_json"])
        task["candidate_ids"] = json.loads(task["candidate_ids_json"])
        conn.close()
        return task

    @staticmethod
    def query_candidates(conn: sqlite3.Connection, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        query = "SELECT * FROM pois WHERE 1=1"
        params = []

        if filters.get("indoor") is not None:
            query += " AND is_indoor = ?"
            params.append(1 if filters["indoor"] else 0)

        if filters.get("seating") is not None:
            query += " AND has_seating = ?"
            params.append(1 if filters["seating"] else 0)

        if "max_walk_min" in filters:
            query += " AND walk_minutes <= ?"
            params.append(filters["max_walk_min"])

        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        results = []
        for r in rows:
            results.append({
                "id": r[0],
                "name": r[1],
                "is_indoor": bool(r[2]),
                "has_seating": bool(r[3]),
                "walk_minutes": r[4],
                "drive_minutes": r[5],
                "tags": r[6].split(",")
            })
        return results

    @staticmethod
    def update_task_state(
        task_id: str,
        new_filters: Optional[Dict[str, Any]] = None,
        selected_id: Optional[int] = None,
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
        current_candidate_ids = json.loads(row["candidate_ids_json"])
        current_selected = row["selected_id"]
        current_comp_text = row["comparison_text"]
        current_status = row["status"]

        # 更新條件與候選
        if new_filters:
            current_filters.update(new_filters)
            new_candidates = StateManager.query_candidates(conn, current_filters)
            current_candidate_ids = [c["id"] for c in new_candidates]
            current_ver += 1  # 狀態改變，版號累加

        if selected_id is not None:
            current_selected = selected_id
            current_ver += 1

        if comparison_text is not None:
            current_comp_text = comparison_text
            current_ver += 1

        if status:
            current_status = status
            current_ver += 1

        cursor.execute("""
            UPDATE task_states
            SET version = ?, filters_json = ?, candidate_ids_json = ?, 
                selected_id = ?, comparison_text = ?, status = ?, updated_at = ?
            WHERE task_id = ?
        """, (
            current_ver,
            json.dumps(current_filters),
            json.dumps(current_candidate_ids),
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
# 3. 生成式 UI 組裝器 (符合 A1 規範)
# ==========================================
class UIGenerator:
    @staticmethod
    def build_ui_json(task: Dict[str, Any]) -> Dict[str, Any]:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # 查出當前 candidate_ids 的詳細資訊
        candidate_ids = task["candidate_ids"]
        candidates = []
        if candidate_ids:
            placeholders = ",".join("?" * len(candidate_ids))
            cursor.execute(f"SELECT * FROM pois WHERE id IN ({placeholders})", candidate_ids)
            for r in cursor.fetchall():
                candidates.append({
                    "id": r[0],
                    "name": r[1],
                    "tags": r[6].split(","),
                    "distance_desc": f"步行約 {r[4]} 分鐘",
                    "eta_desc": f"車程約 {r[5]} 分鐘"
                })
        conn.close()

        filters = task["filters"]
        ui_components = [
            {
                "component": "filter_controls",
                "data": {
                    "filters": [
                        {"id": "indoor", "label": "室內空間", "value": filters.get("indoor", True), "type": "TOGGLE"},
                        {"id": "seating", "label": "有座位", "value": filters.get("seating", True), "type": "TOGGLE"},
                        {"id": "max_walk_min", "label": "步行範圍", "value": f"<= {filters.get('max_walk_min', 10)} 分鐘", "type": "STEPPER"}
                    ]
                }
            },
            {
                "component": "candidate_list",
                "data": {
                    "selected_id": task["selected_id"],
                    "items": candidates
                }
            }
        ]

        # 雲端比較文字或完成狀態
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
# 4. FastAPI & WebSocket 管理
# ==========================================
app = FastAPI()

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
            await connection.send_text(text_data)

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # 連線建立時，先下發目前的任務最新狀態
        current_task = StateManager.get_or_create_task("demo_task_001")
        initial_ui = UIGenerator.build_ui_json(current_task)
        await websocket.send_text(json.dumps(initial_ui, ensure_ascii=False))

        while True:
            raw_text = await websocket.receive_text()
            data = json.loads(raw_text)
            
            msg_type = data.get("type")
            payload = data.get("payload", {})
            task_id = data.get("task_id", "demo_task_001")

            # 情況 A：A2 傳來的觸控操作 (TOUCH_ACTION)
            if msg_type == "TOUCH_ACTION":
                action = payload.get("action")
                if action == "SELECT_CANDIDATE":
                    task = StateManager.update_task_state(task_id, selected_id=payload.get("candidate_id"))
                elif action == "UPDATE_FILTER":
                    task = StateManager.update_task_state(task_id, new_filters=payload.get("filters"))
                elif action == "CONFIRM_DESTINATION":
                    task = StateManager.update_task_state(task_id, status="CONFIRMED")
                else:
                    task = StateManager.get_or_create_task(task_id)

                await manager.broadcast(UIGenerator.build_ui_json(task))

            # 情況 B：A2 重新上線要資料 (STATE_REQ / 中斷恢復)
            elif msg_type == "SYNC_REQUEST":
                task = StateManager.get_or_create_task(task_id)
                await websocket.send_text(json.dumps(UIGenerator.build_ui_json(task), ensure_ascii=False))

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WS Error: {e}")
        manager.disconnect(websocket)

# ==========================================
# 5. 提供給 BC (本地 AI) 與 E (雲端) 呼叫的內部 API
# ==========================================
@app.post("/internal/apply_bc_filters")
async def apply_bc_filters(req: Dict[str, Any]):
    """BC 抽取出的條件由此注入 (e.g. {"indoor": True, "seating": True})"""
    task_id = req.get("task_id", "demo_task_001")
    filters = req.get("filters", {})
    task = StateManager.update_task_state(task_id, new_filters=filters)
    ui_json = UIGenerator.build_ui_json(task)
    await manager.broadcast(ui_json)
    return {"status": "ok", "version": task["version"]}

@app.post("/internal/apply_cloud_comparison")
async def apply_cloud_comparison(req: Dict[str, Any]):
    """E 取得 Claude API 結論後由此注入，附帶過期防護"""
    task_id = req.get("task_id", "demo_task_001")
    req_version = req.get("base_version")
    comp_text = req.get("comparison_text", "")

    task = StateManager.get_or_create_task(task_id)
    # 過期檢查：如果當前版號已經超前，捨棄此雲端回覆
    if req_version and req_version < task["version"]:
        return {"status": "discarded", "reason": "stale_version"}

    updated_task = StateManager.update_task_state(task_id, comparison_text=comp_text)
    await manager.broadcast(UIGenerator.build_ui_json(updated_task))
    return {"status": "applied", "version": updated_task["version"]}

if __name__ == "__main__":
    uvicorn.run("server_d:app", host="0.0.0.0", port=8000, reload=True)