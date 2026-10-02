```markdown
# FlowCockpit Backend (Module D: 任務狀態與後端調度服務)

> 2026 AI 座艙感知與視覺化 Hackathon ｜ 實作組 ｜ FlowCockpit 隨境座艙專案

本模組為 AI Box 的核心調度服務與狀態中心，負責維護多輪對話任務的生命週期、持久化篩選狀態、POI 地點查詢，以及動態組裝符合生成式 UI 規範的 JSON 封包推播給 Android 端[cite: 1, 15]。

---

## 核心功能與架構定位

1. **任務進度接續與版本控制 (State Continuity & Versioning)**
   - 使用 SQLite 本機資料庫（`flowcockpit.db`）持久化任務狀態（`task_id`、`version`、篩選條件、候選清單、已選項目、雲端分析說明）[cite: 1, 15]。
   - 每次條件或選擇變更，`version` 嚴格累加 $+1$[cite: 15]；支援網路中斷恢復與行駛模式切換後的無縫還原[cite: 1]。
2. **POI 示範資料庫查詢**
   - 內建 8 筆真實情境示範地點資料，支援 `indoor`（室內/室外）、`seating`（有座位/無座位）、`max_drive_min`（最大行駛時間）與 `max_drive_km`（最大行駛距離）多維度條件篩選[cite: 15]。
3. **動態生成式 UI 組裝 (Generative UI Assembler)**
   - 依據當前任務狀態，即時組裝包含 `filter_controls`、`candidate_list`、`comparison_panel` 的結構化 UI JSON，並推播給 Android 原生 Jetpack Compose 渲染[cite: 1, 15]。
4. **WebSocket 雙向通訊管理**
   - 管理 Android HMI 連線，支援連線建立時自動同步最新狀態、接收觸控操作事件（`TOUCH_ACTION`）及斷線重連狀態還原請求（`SYNC_REQUEST`）[cite: 1, 15]。
5. **本地 AI (BC) 與雲端增強 (E) 內部接口**
   - 提供專用 HTTP POST 端點接收語音抽取條件，並內建雲端模型回傳的過期版本拋棄防護機制[cite: 1, 15]。

---

## 檔案結構說明

```text
d/
├── server_d.py            # 後端主程式 (FastAPI + WebSocket + SQLite)
├── dashboard.html         # Web 視覺化 Demo 與除錯控制台
├── mock_ui_payload.json   # 供前端 A1/A2 對齊之標準 UI 描述範例檔
├── test_client.py         # 模擬 A2 觸控與 WebSocket 測試腳本
├── requirements.txt       # Python 相依套件清單
└── README.md              # 模組說明文件

```

---

## 環境建置與啟動

### 1. 安裝套件

請於虛擬環境中安裝必要依賴：

```bash
pip install -r requirements.txt

```

*(主要依賴：`fastapi`、`uvicorn`、`websockets`、`pydantic`)*

### 2. 啟動後端服務

```bash
python server_d.py

```

* 服務將運行於 `http://0.0.0.0:8000`。


* 初次啟動時會自動建立 `flowcockpit.db` 並植入 8 筆示範地點資料。


* 瀏覽器開啟 `http://127.0.0.1:8000` 即可進入內建的視覺化 Demo 控制台。



### 3. 本地 WebSocket 測試

啟動伺服器後，可在另一終端機執行測試客戶端模擬觸控操作：

```bash
python test_client.py

```

---

## 跨模組介面通訊規格

### 1. 給 A1 / A2（Android 端）通訊協定



#### A. 連線端點

* **WebSocket URL**: `ws://<AI_BOX_IP>:8000/ws`

* 建立連線後，伺服器會立即主動推送一次當前 `task_id` 的最新 UI JSON（格式同 `mock_ui_payload.json`）。



#### B. Android 發送觸控操作事件 (`TOUCH_ACTION`)



當使用者在車機上點選卡片或手動切換開關時，透過 WebSocket 傳送：

* **選擇特定地點卡片**：


```json
{
  "task_id": "demo_task_001",
  "version": 1,
  "type": "TOUCH_ACTION",
  "payload": {
    "action": "SELECT_CANDIDATE",
    "candidate_id": 2
  }
}

```


* **調整篩選條件**：


```json
{
  "task_id": "demo_task_001",
  "version": 1,
  "type": "TOUCH_ACTION",
  "payload": {
    "action": "UPDATE_FILTER",
    "filters": {
      "indoor": false,
      "max_drive_min": 15
    }
  }
}

```


* **確認導航目的地**：


```json
{
  "task_id": "demo_task_001",
  "version": 1,
  "type": "TOUCH_ACTION",
  "payload": {
    "action": "CONFIRM_DESTINATION"
  }
}

```



#### C. 中斷恢復請求 (`SYNC_REQUEST`)



當 App 從背景喚醒或切換回可操作模式時，主動請求目前最新狀態：

```json
{
  "task_id": "demo_task_001",
  "type": "SYNC_REQUEST"
}

```

---

### 2. 給 BC 模組（本地語音與 AI 條件抽取）



當本地模型解析完使用者語音後，透過 HTTP POST 將篩選條件注入 D 模組：

* **端點**: `POST /internal/apply_bc_filters`

* **Request Body 範例**：


```json
{
  "task_id": "demo_task_001",
  "filters": {
    "indoor": true,
    "seating": true,
    "max_drive_min": 10
  }
}

```


* **Response**: `{"status": "ok", "version": 2}`

* **效果**: 後端自動重新查詢符合的地點，更新版號並即時廣播最新 UI 給連線中的 Android。



---

### 3. 給 E 模組（雲端增強分析）



當連網狀態下由 Claude API 完成多地點比較時，將決策說明附加至任務狀態：

* **端點**: `POST /internal/apply_cloud_comparison`

* **Request Body 範例**：


```json
{
  "task_id": "demo_task_001",
  "base_version": 1,
  "comparison_text": "Claude 雲端建議：若追求快速補給，推薦【全家便利商店 休息站店】（車程僅2分鐘）；若需要完整正餐或多樣飲食選擇，建議前往【國道服務區 主建築美食街】。"
}

```


* **防護機制**:


* 若目前任務版本已因使用者的新操作而超前（`base_version < current_version`），後端將回傳 `{"status": "discarded", "reason": "stale_version"}`，確保過期的雲端回覆不會覆蓋使用者當前操作。





---

## 內建 POI 地點資料清單 (示範資料庫)

系統預載之示範地點與預設行駛參數如下表所示：

| ID | 地點名稱 | 室內 | 座位 | 行駛里程 (`drive_km`) | 行駛時間 (`drive_minutes`) | 標籤 (`tags`) |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 星巴克 國道門市 | 是 | 是 | 2.5 km | 4 分鐘 | 室內, 空調, 咖啡, 有插座

 |
| 2 | 全家便利商店 休息站店 | 是 | 是 | 1.2 km | 2 分鐘 | 室內, 便利店, 輕食, 有座位

 |
| 3 | 林間步道觀景涼亭 | 否 | 是 | 6.8 km | 11 分鐘 | 戶外, 通風, 風景好, 有長椅

 |
| 4 | 國道服務區 主建築美食街 | 是 | 是 | 3.0 km | 5 分鐘 | 室內, 熱食, 座位多, 洗手間

 |
| 5 | 得來速 快速取餐點 | 否 | 否 | 2.0 km | 3 分鐘 | 免下車, 快速, 外帶

 |
| 6 | 露天景觀咖啡座 | 否 | 是 | 7.5 km | 12 分鐘 | 戶外遮陽, 有座位, 氣氛佳

 |
| 7 | 綠能生態停車休憩區 | 否 | 否 | 1.0 km | 2 分鐘 | 戶外, 停車方便, 活動筋骨

 |
| 8 | 24H 自助圖書休息站 | 是 | 是 | 4.5 km | 7 分鐘 | 室內安靜, 冷氣, 閱讀區, 充電

 |

---

## 生成式 UI 封包範例 (`mock_ui_payload.json`)

後端廣播給 Android Compose 端之標準封包格式（對應 `mock_ui_payload.json` 檔案）如下：

```json
{
  "task_id": "demo_task_001",
  "version": 1,
  "type": "UI_UPDATE",
  "timestamp": 1727835200,
  "payload": {
    "layout": "VERTICAL",
    "components": [
      {
        "component": "filter_controls",
        "data": {
          "filters": [
            {
              "id": "indoor",
              "label": "室內空間",
              "value": true,
              "type": "TOGGLE"
            },
            {
              "id": "seating",
              "label": "有座位",
              "value": true,
              "type": "TOGGLE"
            },
            {
              "id": "max_drive_min",
              "label": "車程範圍",
              "value": "<= 10 分鐘",
              "type": "STEPPER"
            }
          ]
        }
      },
      {
        "component": "candidate_list",
        "data": {
          "selected_id": 2,
          "items": [
            {
              "id": 1,
              "name": "星巴克 國道門市",
              "tags": [
                "室內",
                "空調",
                "咖啡",
                "有插座"
              ],
              "drive_distance_desc": "行駛距離 2.5 公里",
              "drive_eta_desc": "行駛時間約 4 分鐘"
            },
            {
              "id": 2,
              "name": "全家便利商店 休息站店",
              "tags": [
                "室內",
                "便利店",
                "輕食",
                "有座位"
              ],
              "drive_distance_desc": "行駛距離 1.2 公里",
              "drive_eta_desc": "行駛時間約 2 分鐘"
            },
            {
              "id": 4,
              "name": "國道服務區 主建築美食街",
              "tags": [
                "室內",
                "熱食",
                "座位多",
                "洗手間"
              ],
              "drive_distance_desc": "行駛距離 3.0 公里",
              "drive_eta_desc": "行駛時間約 5 分鐘"
            },
            {
              "id": 8,
              "name": "24H 自助圖書休息站",
              "tags": [
                "室內安靜",
                "冷氣",
                "閱讀區",
                "充電"
              ],
              "drive_distance_desc": "行駛距離 4.5 公里",
              "drive_eta_desc": "行駛時間約 7 分鐘"
            }
          ]
        }
      },
      {
        "component": "comparison_panel",
        "data": {
          "visible": true,
          "status": "IN_PROGRESS",
          "selected_id": 2,
          "cloud_enhanced_text": "Claude 雲端建議：若行程緊湊追求快速補給，推薦【全家便利商店 休息站店】（車程僅2分鐘）；若需要完整正餐或多樣飲食選擇，建議前往【國道服務區 主建築美食街】。"
        }
      }
    ]
  }
}

```

```

```
