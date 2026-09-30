# 雲林離線語音地點搜尋

音訊 → 本機 faster-whisper → Ollama `llama3.2:1b` → 本機 SQLite 地點查詢。

成功回應分成 `places`（地點清單）與 `reply`（文字回覆），支援地點類別、鄉鎮、名稱及指定座標半徑搜尋。距離為直線距離，不提供導航。

儲存庫只包含程式碼、依賴設定與操作說明。錄音、模型、地圖資料、測試程式、測試結果及本機環境均不提交。

## 安裝

需要 Python（含 venv、pip）及 [Ollama](https://ollama.com/)。以下為 Bash 指令：

```bash
git clone https://github.com/YOUR_USERNAME/ollama-audio-json.git
cd ollama-audio-json
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
ollama pull llama3.2:1b
```

若 Ollama 尚未執行，在另一個終端啟動 `ollama serve`。

## 準備本機地圖資料

clone 後需要先建立資料庫；Git 不包含 `data/`。從 [Geofabrik Taiwan](https://download.geofabrik.de/asia/taiwan.html) 下載 Taiwan `.osm.pbf`，然後執行：

```bash
.venv/bin/python -m pip install -r requirements-data.txt
.venv/bin/python build_places.py /完整路徑/taiwan.osm.pbf \
  --source-url '實際下載的 Geofabrik URL'
```

程式依雲林縣界及其 20 個鄉鎮擷取地點，建立 `data/yunlin.sqlite3`、來源資訊與行政邊界。建置失敗時保留原資料庫。`osmium`、`shapely` 只在建置資料時需要。

也可以將先前建立的 `data/` 複製到專案根目錄，在本機使用；它不會被 Git 追蹤。若沒有資料庫，搜尋介面會回傳 `places_unavailable`。

地圖資料 © OpenStreetMap contributors，依 [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) 授權；來源與說明見 [OpenStreetMap](https://www.openstreetmap.org/copyright)。程式碼的開源授權尚未指定。

## 啟動

```bash
bash run.sh
```

開啟 http://127.0.0.1:8000/docs：

- `POST /api/audio`：上傳音訊，中文可指定 `language=zh`。
- `POST /api/text`：直接以文字查詢。
- `GET /api/places/info`：查看本機資料日期、範圍及來源。

首次辨識會下載 Whisper 模型至 `models/`。模型與地圖準備完成後，查詢在本機執行。Swagger 頁面需要 CDN，完全離線時可使用命令列或 HTTP API。

## 查詢

```bash
bash run.sh --text '找一個休息地點'
bash run.sh --text '找虎尾的咖啡店' --limit 3
bash run.sh recording.wav --language zh > result.json
```

指定中心與半徑：

```bash
bash run.sh --text '找一個休息地點' \
  --latitude 23.71 --longitude 120.54 --radius-km 5
```

文字 API：

```bash
curl http://127.0.0.1:8000/api/text \
  -H 'Content-Type: application/json' \
  -d '{"text":"找一個休息地點","latitude":23.71,"longitude":120.54,"radius_km":5,"limit":5}'
```

音訊 API：

```bash
curl http://127.0.0.1:8000/api/audio \
  -F 'file=@recording.m4a' -F 'language=zh' \
  -F 'latitude=23.71' -F 'longitude=120.54' -F 'radius_km=5'
```

也可以在 `instruction` 寫「座標23.71, 120.54，查詢5公里內的目標點」。明確欄位優先於 instruction，instruction 優先於語音中的座標及半徑。

座標順序為緯度、經度，兩者須一起提供。指定半徑時必須有搜尋中心。先篩選範圍，再依直線距離排序及限制筆數；找不到時不會自動擴大範圍。未提供位置時不宣稱最近。`limit` 預設 5，上限 20。

## 回應格式

成功回應固定只有 `places` 與 `reply`：

```json
{"places": [], "reply": "查詢結果的文字說明"}
```

地點包含名稱、OSM ID、鄉鎮、緯經度、類別、地址、來源連結及距離。未命名地點使用顯示標籤，`name_is_label=true`；面狀地點的座標是代表點，不是入口。

模型負責解析搜尋需求；地名、座標與查詢回覆由資料庫和程式提供。一般聊天則回傳空的 `places` 與模型回答。

## 設定與限制

- `OLLAMA_URL`：預設 `http://127.0.0.1:11434`。
- `OLLAMA_MODEL`：預設 `llama3.2:1b`。
- `WHISPER_MODEL`：預設 `small`，使用 CPU int8。
- `bash run.sh --serve --port 8001`：指定服務埠。
- 音訊上限 25 MiB、5 分鐘、轉錄 6000 字；一次處理一段音訊。
- 地點資料只涵蓋已標註設施，無法確認即時營業、空位及通行權限。休息查詢需要座椅等相關標註。
- 1B 模型可能誤判意圖；目前支援單一類別、地名、鄉鎮和半徑，不支援複雜否定、價格或即時條件。
