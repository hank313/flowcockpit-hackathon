# FlowCockpit 隨境座艙

> 2026 AI 座艙感知與視覺化 Hackathon｜實作組｜Hybrid AI (Offline First, Cloud Enhanced)

這個 repo 是團隊共用的程式碼倉庫。**每個人負責一塊模組,請把你那塊的進度、接口格式、遇到的問題更新在下面對應的區塊**,讓大家(以及大家各自在用的 AI 助理)都能看到目前狀態,避免到最後對接不上。

---

## 專案簡介

FlowCockpit 讓使用者以自然語言描述需求,由 AI 理解意圖,組合出當下可操作的介面,並在操作中斷、車輛狀態切換或外部網路中斷後保留任務進度。首個端到端情境:「途中挑選休息地點」。

## 系統架構

```
Android HMI App  ←Ethernet/WebSocket→  AI Box(Python)  ←(連網時)→  Cloud LLM
```

- Android:Kotlin + Jetpack Compose,Android 14+,Target SDK 34
- AI Box:x86 筆電,跑本地語音辨識 + 本地小模型 + 任務狀態管理
- 離線時本地 AI 完成核心操作;連網後雲端模型補充多條件比較/取捨說明

詳細規劃文件:`FlowCockpit_提案草案.pdf`、`FlowCockpit_參賽簡報_v3.pptx`、`FlowCockpit_專案現況與分工.md`

---

## 五個工作項目與內容

以下是目前規劃的五塊工作內容,實際由誰負責、進度到哪,請自行在群組/自己的AI裡對齊,或之後再回來這份README補充。

### A1 — Android UI 元件開發

負責範圍:候選卡片、條件控制、比較與確認面板三類 Compose 元件,以及依 JSON 決定渲染哪個元件的渲染器。

### A2 — Android 互動邏輯、狀態管理與多螢幕

負責範圍:麥克風/觸控輸入事件、WebSocket client、行駛模式收合/展開動畫、中斷恢復邏輯。

### BC — 語音與本地AI

負責範圍:faster-whisper 語音辨識、Ollama 跑 Qwen3-1.7B 做意圖/條件抽取(輸出結構化JSON)。

### D — 任務狀態與後端

負責範圍:SQLite 任務狀態(task_id/version)、示範地點資料、生成式UI JSON組裝與驗證、WebSocket server。

### E — 雲端整合與系統整合

負責範圍:Claude API 多條件比較、斷網/恢復連網 fallback、端到端整合測試、demo腳本、簡報/影片/揭露表。

---

## 共用規範(A1、A2、BC、D 請直接照這個做)

E 的雲端增強功能由同一人負責整合,格式不在此強制規範。

### BC → D:意圖抽取後的條件

```json
{
  "intent": "search_rest_stop",
  "conditions": { "indoor": true, "has_seating": true, "max_walk_distance_m": 300 },
  "reference": { "type": "modify", "target_candidate_id": "loc_002" },
  "raw_text": "找個室內、有座位、不用走太遠的地方"
}
```

`reference` 選填,用於「留下第二個」這類指涉性修改。

### D → A1:生成式UI描述(渲染依據)

```json
{
  "components": [
    { "type": "condition_control", "id": "cond_1", "data": { "filters": { "indoor": true } } },
    { "type": "candidate_card", "id": "card_loc_002", "data": { "candidate_id": "loc_002", "name": "示範地點A", "attributes": {}, "selected": false } },
    { "type": "compare_confirm_panel", "id": "panel_1", "data": { "candidate_ids": ["loc_001", "loc_002"], "comparison_text": null, "confirm_enabled": true } }
  ],
  "clarification_needed": null
}
```

`type` 只會是 `condition_control` / `candidate_card` / `compare_confirm_panel` 三種固定值。`clarification_needed` 有值時代表AI聽不懂,顯示澄清問題UI。

### WebSocket 外層包裝(A2 ↔ D)

```json
{ "task_id": "task_20261001_0001", "version": 4, "type": "ui_update", "payload": {} }
```

`type`:`ui_update`(D→A2)、`user_action`(A2→D)、`voice_input`(A2→D)。`version` 由 D 遞增,收到較舊版本一律丟棄。

---

## 重要時程

- 2026/10/7(三)12:00:完整送件截止(報名表+提案簡報+3分鐘影片+AI技術揭露表)
- 2026/10/14(三):初審結果公告
- 2026/10/20(二):決賽
