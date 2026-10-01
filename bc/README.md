# 臺灣離線語音地點搜尋

音訊 → 本機 faster-whisper → Ollama `llama3.2:1b` → 本機 SQLite 地點查詢。

成功回應包含 `places`（地點清單）、`reply`（文字回覆）與 `bc_to_d`（傳給 D 的意圖條件），支援地點類別、縣市、鄉鎮市區、名稱及指定座標半徑搜尋。距離為直線距離，不提供導航。

儲存庫只包含程式碼、依賴設定與操作說明。錄音、模型、地圖資料、測試程式、測試結果及本機環境均不提交。

## 安裝

需要 Python（含 venv、pip）及 [Ollama](https://ollama.com/)。以下為 Bash 指令：

```bash
git clone https://github.com/hank313/flowcockpit-hackathon.git
cd flowcockpit-hackathon/bc
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
ollama pull llama3.2:1b
```

若 Ollama 尚未執行，在另一個終端啟動 `ollama serve`。

## 準備本機地圖資料

clone 後需要先建立資料庫；Git 不包含 `data/`。從 [Geofabrik Taiwan](https://download.geofabrik.de/asia/taiwan.html) 下載 Taiwan `.osm.pbf`，然後執行：

```bash
.venv/bin/python -m pip install -r requirements-data.txt
mkdir -p data
curl -fL --retry 3 https://download.geofabrik.de/asia/taiwan-latest.osm.pbf -o data/taiwan.osm.pbf
.venv/bin/python build_places.py data/taiwan.osm.pbf \
  --source-url https://download.geofabrik.de/asia/taiwan-latest.osm.pbf
```

程式依臺灣 22 個縣市邊界擷取地點，包含澎湖、金門與連江，建立 `data/taiwan.sqlite3`、`metadata.json`、`ATTRIBUTION.md` 與行政邊界。原始檔中鄰近國外的地點不納入。若縣市界缺漏，使用其 subarea 邊界聯集並記錄於 metadata。擷取檔缺少遠方島嶼成員時，只恢復檔內已閉合的行政區外環，不人工連接缺漏邊界；覆蓋限制記錄於 `partial_boundaries`。22 縣市皆可查詢，但不保證所有偏遠島嶼及所有設施都已收錄。建置失敗時保留原資料庫。`osmium`、`shapely` 只在建置資料時需要。

本機已建置的快照日期為 `2026-09-29T20:22:51Z`，共 300,695 筆地點、22 縣市及 368 鄉鎮市區邊界。高雄市界由行政區聯集合成；旗津區僅含擷取檔中可重建的閉合外環，遠方島嶼可能缺漏。40 筆地點可辨識縣市，但無法配對行政區，`district` 為空字串。實際安裝版本以 `/api/places/info` 為準，下載 latest 重建時筆數會改變。

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
bash run.sh --text '找雲林虎尾的咖啡店' --limit 3
bash run.sh --text '找台北市中正區的咖啡店' --limit 3
bash run.sh --text '找高雄市的公園' --limit 3
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

「台／臺」皆可查詢。僅說「中正區」等重複行政區名稱時，程式會請你補充縣市。指定縣市與行政區時會同時篩選；未指定區域則查詢全臺資料。搜尋半徑仍為直線距離，與 BC → D 的行駛距離條件不同。

## 回應格式

一般查詢的回應包含 `places`、`reply` 與 `bc_to_d`：

```json
{"places": [], "reply": "查詢結果的文字說明", "bc_to_d": {"intent":"search_rest_stop","conditions":{},"raw_text":"找休息地點"}}
```

地點包含名稱、OSM ID、縣市 `county`、鄉鎮市區 `district`、緯經度、類別、地址、來源連結及距離。未命名地點使用顯示標籤，`name_is_label=true`；面狀地點的座標是代表點，不是入口。

模型負責解析搜尋需求；地名、座標與查詢回覆由資料庫和程式提供。一般聊天則回傳空的 `places` 與模型回答。

## 設定與限制

- `OLLAMA_URL`：預設 `http://127.0.0.1:11434`。
- `OLLAMA_MODEL`：預設 `llama3.2:1b`。
- `WHISPER_MODEL`：預設 `small`，使用 CPU int8。
- `bash run.sh --serve --port 8001`：指定服務埠。
- 音訊上限 25 MiB、5 分鐘、轉錄 6000 字；一次處理一段音訊。
- 地點資料只涵蓋已標註設施，無法確認即時營業、空位及通行權限。休息查詢需要座椅等相關標註。
- 1B 模型可能誤判意圖；目前支援單一類別、地名、縣市、鄉鎮市區和半徑，不支援複雜否定、價格或即時條件。

## BC → D 意圖介面

`POST /api/text` 與 `POST /api/audio` 在原回應中新增 `bc_to_d`。新增的 `POST /api/intent` 則只回傳 BC → D 物件，不需要地圖資料庫。

**`reference.type` 完全由上位機輸入**，不交由模型分類，也沒有預設操作。它是非空操作字串（英文字母開頭，允許英數字、底線與連字號），具體操作是否可執行由 D 決定。

上位機已知道目標時，文字／意圖 API 的請求可以是：

```json
{
  "text": "找個室內、有座位、不用開太遠的地方",
  "reference": {"type":"modify","target_candidate_id":"loc_002"}
}
```

`POST /api/intent` 回傳：

```json
{
  "intent":"search_rest_stop",
  "conditions":{"indoor":true,"has_seating":true,"max_drive_distance_m":300},
  "reference":{"type":"modify","target_candidate_id":"loc_002"},
  "raw_text":"找個室內、有座位、不用開太遠的地方"
}
```

如果要從語音／文字解析「第二個」，上位機需提供 **上一輪畫面的實際顯示順序**：

```json
{
  "text":"留下第二個",
  "reference_type":"modify",
  "candidate_ids":["loc_001","loc_002","loc_003"]
}
```

程式只解析索引，將第二筆 ID 與上位機的 type 組成 `reference`。傳入完整 `reference` 時以上位機指定的目標為準；若同時提供 `reference_type` 且與 `reference.type` 不符，回傳 422。

音訊 API 使用 multipart 表單中的 `context_json` 欄位傳入上下文：

```bash
curl http://127.0.0.1:8000/api/audio   -F 'file=@recording.wav' -F 'language=zh'   -F 'context_json={"reference_type":"modify","candidate_ids":["loc_001","loc_002"]}'
```

命令列可使用 `--context-json`，內容與音訊表單相同。

- 未提及的條件不輸出；未指定候選時不輸出 `reference`。原始輸入／Whisper 逐字稿直接保留為 `raw_text`，不使用模型改寫版本。
- `indoor` 支援室內、室外與常見否定；`has_seating` 支援座位、座椅、坐下與常見否定。條件由明確語句規則抽取，模型用於搜尋意圖分類；非任意自然語言條件推理。
- 「行駛三百公尺內」、「開車0.5公里內」抽取為 300、500 公尺。「不用開太遠」採明示的預設 300 公尺；上位機可傳 `short_drive_distance_m` 調整此產品預設。
- 「5公里內」搜尋半徑不會轉成行駛距離。此 BC 服務沒有行車路網。
- 有新增條件或 `reference` 時，`/api/text` 和 `/api/audio` 回傳 `places: []`，將條件交由 D 執行；不宣稱已完成室內、座位、行駛條件篩選或修改 D 任務。沒有這些條件的既有查詢仍可使用本機地圖。
- 「第二個」缺少候選清單或 type 時，`/api/intent` 回傳 422 `clarification_needed`；合併介面回傳 `bc_to_d.intent="clarify"` 與說明，不編造候選 ID。
- `intent` 值為 `search_rest_stop`、`search_place`、`chat`，需要釐清時為 `clarify`。D 需依其任務流程處理；本程式沒有直接傳送資料到 D 的網路服務。

距離欄位已改為 `max_drive_distance_m`（公尺）；上位機預設參數改為 `short_drive_distance_m`，測試程式對應 `--short-drive-distance-m`。舊的步行欄位不再輸出，舊參數會被 API 拒絕。明確步行語句不會被轉成行駛距離。`不用開太遠` 保留原本可設定的 300 公尺預設；實際行駛路程須由 D 或路網服務驗證。
