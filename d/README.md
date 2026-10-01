# FlowCockpit Backend (Module D: Task State & Orchestrator)

> 2026 AI 座艙感知與視覺化 Hackathon ｜ FlowCockpit 隨境座艙專案

本模組為 AI Box 上的核心後端服務，負責：
1. **任務狀態管理與版本控制**（基於 SQLite 實現狀態持久化與斷點續接）
2. **POI 示範資料庫查詢**（過濾篩選候選地點）
3. **動態生成式 UI JSON 組裝**（依據 A2UI 規格供前端 Android Compose 渲染）
4. **WebSocket 雙向通訊**（即時同步介面狀態、接收觸控事件）
5. **本地 AI (BC) 與雲端增強 (E) 之內部 API 對接**

---

## 快速開始

### 1. 安裝環境
建議在 Python 3.10+ 環境下執行：

\`\`\`bash
# 建立並啟用虛擬環境
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安裝依賴
pip install -r requirements.txt
\`\`\`

### 2. 啟動後端服務
\`\`\`bash
python server_d.py
\`\`\`
服務啟動後將監聽 `http://0.0.0.0:8000`，並自動建立 `flowcockpit.db` 示範資料庫。

---

## 介面規格與對接說明

### 1. Android WebSocket 通訊 (`ws://<IP>:8000/ws`)
- **連線初始化**：連線建立時，後端會主動下發目前 `task_id` 的最新 UI JSON。
- **客戶端觸控事件 (TOUCH_ACTION)**：
  \`\`\`json
  {
    "task_id": "demo_task_001",
    "version": 1,
    "type": "TOUCH_ACTION",
    "payload": {
      "action": "SELECT_CANDIDATE",
      "candidate_id": 2
    }
  }
  \`\`\`
- **狀態重新同步 (SYNC_REQUEST)**：當中斷或切換模式後重新連線，Android 可主動請求狀態：
  \`\`\`json
  {
    "task_id": "demo_task_001",
    "type": "SYNC_REQUEST"
  }
  \`\`\`

### 2. 本地 AI 條件注入 (`POST /internal/apply_bc_filters`)
由 **模組 BC** 呼叫，將語音抽取的結構化篩選條件注入並自動廣播 UI 更新：
\`\`\`bash
curl -X POST http://localhost:8000/internal/apply_bc_filters \
  -H "Content-Type: application/json" \
  -d '{"task_id": "demo_task_001", "filters": {"indoor": true, "seating": true}}'
\`\`\`

### 3. 雲端增強分析注入 (`POST /internal/apply_cloud_comparison`)
由 **模組 E** 呼叫，帶入 Claude API 生成的比較建議。內建版本防護，過期回覆會被自動拋棄：
\`\`\`bash
curl -X POST http://localhost:8000/internal/apply_cloud_comparison \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "demo_task_001",
    "base_version": 1,
    "comparison_text": "雲端分析建議：星巴克適合商務辦公，美食街適合用餐需求。"
  }'
\`\`\`

---

## 本地測試
啟動 `server_d.py` 後，開啟另一終端機執行模擬客戶端：
\`\`\`bash
python test_client.py
\`\`\`