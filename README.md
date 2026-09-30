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

## 五個模組與負責人

請每個人在自己的區塊底下,把「負責人」填上、並隨時更新「目前狀態」。格式不拘,重點是讓別人(跟別人的AI)看得懂你做到哪、輸出/輸入格式長怎樣。

### A1 — Android UI 元件開發

負責範圍:候選卡片、條件控制、比較與確認面板三類 Compose 元件,以及依 JSON 決定渲染哪個元件的渲染器。

- 負責人:
- 目前狀態:
- 對外接口(其他人要對接的格式):

### A2 — Android 互動邏輯、狀態管理與多螢幕

負責範圍:麥克風/觸控輸入事件、WebSocket client、行駛模式收合/展開動畫、中斷恢復邏輯。

- 負責人:
- 目前狀態:
- 對外接口(其他人要對接的格式):

### BC — 語音與本地AI

負責範圍:faster-whisper 語音辨識、Ollama 跑 Qwen3-1.7B 做意圖/條件抽取(輸出結構化JSON)。

- 負責人:
- 目前狀態:
- 對外接口(其他人要對接的格式):

### D — 任務狀態與後端

負責範圍:SQLite 任務狀態(task_id/version)、示範地點資料、生成式UI JSON組裝與驗證、WebSocket server。

- 負責人:
- 目前狀態:
- 對外接口(其他人要對接的格式):

### E — 雲端整合與系統整合

負責範圍:Claude API 多條件比較、斷網/恢復連網 fallback、端到端整合測試、demo腳本、簡報/影片/揭露表。

- 負責人:
- 目前狀態:
- 對外接口(其他人要對接的格式):

---

## 共用規範(所有人先對齊)

在各自開始寫程式前,先在這裡定案下面幾個格式,避免各做各的:

1. **JSON UI 描述格式**(例如 `{"component": "candidate_card", "data": {...}}`)
2. **條件 JSON 格式**(例如 `{"indoor": true, "seating": true, "distance": "near"}`)
3. **task_id / version 規則**
4. **WebSocket 訊息包格式**(例如外層都包 `{"task_id":..., "version":..., "payload":{...}}`)

> 待補:上面四項的實際定案內容,由 A1/A2/BC/D 討論後填在這裡。

---

## 重要時程

- 2026/10/7(三)12:00:完整送件截止(報名表+提案簡報+3分鐘影片+AI技術揭露表)
- 2026/10/14(三):初審結果公告
- 2026/10/20(二):決賽
