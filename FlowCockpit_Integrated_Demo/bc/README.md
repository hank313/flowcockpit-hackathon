# 臺灣離線語音地點搜尋

音訊 → 本機 faster-whisper → Ollama `llama3.2:1b` → 本機 SQLite 地點查詢。

成功回應包含 `places`（地點清單）、`reply`（文字回覆）與 `bc_to_d`（傳給 D 的意圖條件），支援地點類別、縣市、鄉鎮市區、名稱及指定座標半徑搜尋。距離為直線距離，不提供導航。

儲存庫包含程式碼、依賴設定、操作說明，以及供下載驗證的 `examples/` 範例音訊、JSON、Python 程式。`data/last_location.json` 位置紀錄也納入 Git。私人錄音、模型、地圖資料庫、內部測試檔、原始測試日誌及本機環境不提交；README 保留驗證結果摘要。

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

clone 後需要先建立資料庫；Git 不包含地圖資料庫；`data/` 中僅 `last_location.json` 納入版本控制。從 [Geofabrik Taiwan](https://download.geofabrik.de/asia/taiwan.html) 下載 Taiwan `.osm.pbf`，然後執行：

```bash
.venv/bin/python -m pip install -r requirements-data.txt
mkdir -p data
curl -fL --retry 3 https://download.geofabrik.de/asia/taiwan-latest.osm.pbf -o data/taiwan.osm.pbf
.venv/bin/python build_places.py data/taiwan.osm.pbf \
  --source-url https://download.geofabrik.de/asia/taiwan-latest.osm.pbf
```

程式依臺灣 22 個縣市邊界擷取地點，包含澎湖、金門與連江，建立 `data/taiwan.sqlite3`、`metadata.json`、`ATTRIBUTION.md` 與行政邊界。原始檔中鄰近國外的地點不納入。若縣市界缺漏，使用其 subarea 邊界聯集並記錄於 metadata。擷取檔缺少遠方島嶼成員時，只恢復檔內已閉合的行政區外環，不人工連接缺漏邊界；覆蓋限制記錄於 `partial_boundaries`。22 縣市皆可查詢，但不保證所有偏遠島嶼及所有設施都已收錄。建置失敗時保留原資料庫。`osmium`、`shapely` 只在建置資料時需要。

本機已建置的快照日期為 `2026-09-29T20:22:51Z`，共 300,695 筆地點、22 縣市及 368 鄉鎮市區邊界。高雄市界由行政區聯集合成；旗津區僅含擷取檔中可重建的閉合外環，遠方島嶼可能缺漏。40 筆地點可辨識縣市，但無法配對行政區，`district` 為空字串。實際安裝版本以 `/api/places/info` 為準，下載 latest 重建時筆數會改變。

也可以將先前建立的 `data/` 複製到專案根目錄，在本機使用；其中地圖資料不會被 Git 追蹤，位置紀錄 `last_location.json` 除外。若沒有資料庫，搜尋介面會回傳 `places_unavailable`。

地圖資料 © OpenStreetMap contributors，依 [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) 授權；來源與說明見 [OpenStreetMap](https://www.openstreetmap.org/copyright)。程式碼的開源授權尚未指定。

## 啟動

```bash
bash run.sh
```

預設監聽 `127.0.0.1:8001`，API 基底網址為 `http://127.0.0.1:8001`。指定其他 port：

```bash
bash run.sh --serve --port 8002
```

## API 端口與路徑總覽

以下所有路徑共用 **8001** port：

| 方法 | 路徑 | 輸入格式／必要欄位 | 用途與回傳 |
| --- | --- | --- | --- |
| POST | `/api/audio` | `multipart/form-data`；`file` 音訊檔 | 語音轉文字、解析意圖；回傳 `places`、`reply`、`bc_to_d` |
| POST | `/api/text` | `application/json`；`text` | 文字搜尋／解析意圖；回傳 `places`、`reply`、`bc_to_d` |
| POST | `/api/intent` | JSON 的 `text`，或 multipart 的 `file` 音訊 | 只回傳 BC → D 物件：`intent`、`conditions`、`raw_text`，以及有指定時的 `reference`；不查地圖 |
| GET | `/api/location` | 無 | 最近一次成功請求提供的經緯度、UTC 更新時間與來源 API；無紀錄時 404 |
| GET | `/api/places/info` | 無 | 地點數量、覆蓋範圍、資料日期、來源及授權 |
| GET | `/docs` | 無 | Swagger 互動測試頁 |
| GET | `/redoc` | 無 | API 文件閱讀頁 |
| GET | `/openapi.json` | 無 | OpenAPI 規格，供上位機或工具串接 |
| GET | `/` | 無 | 重新導向 `/docs` |

本機測試頁：[http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs)。

**選填欄位：**

- `/api/audio`：表單可帶 `language`（預設 `auto`，中文可填 `zh`）、`instruction`、`latitude`、`longitude`、`radius_km`、`limit`、`type`、`target_candidate_id`、`context_json`。
- `/api/text`：JSON 可帶 `instruction`、`latitude`、`longitude`、`radius_km`、`limit`；上位機上下文 `reference`、`reference_type`、`candidate_ids`、`short_drive_distance_m` 直接放在 JSON 最外層。
- `/api/intent`：JSON 使用相同文字請求結構；音訊使用 multipart 的 `file`、`language`（預設 `auto`）、`context_json`（預設 `{}`），另可直接傳 `latitude`、`longitude`、`type`、`target_candidate_id`；JSON 文字請求也支援這四個欄位。只做意圖抽取，不查地圖；座標轉交 D，音訊表單不接受 `radius_km`。JSON 的搜尋半徑與筆數不會觸發地點查詢。
- 音訊的上位機上下文放入 `context_json`（JSON 字串）。`reference.type` 由上位機指定；完整範例見下方「BC → D 意圖介面」。

`latitude`、`longitude` 必須成對提供。搜尋 `radius_km` 是直線半徑（公里），需要中心座標；`limit` 預設 5、範圍 1–20。`max_drive_distance_m` 是交給 D 的行駛距離條件（公尺），不是搜尋半徑。

快速確認服務與 BC → D：

```bash
curl http://127.0.0.1:8001/api/places/info

curl http://127.0.0.1:8001/api/intent \
  -H 'Content-Type: application/json' \
  -d '{"text":"找個室內、有座位、行駛500公尺內的地方","reference":{"type":"modify","target_candidate_id":"loc_002"}}'
```

**上位機在另一台電腦時：** 預設 `127.0.0.1` 只接受本機連線。停止原服務後，在 `bc` 目錄用以下方式監聽區網：

```bash
.venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port 8001
```

上位機改用 `http://伺服器區網IP:8001/api/audio` 等網址，且網路需允許 TCP 8001。`0.0.0.0` 是伺服器監聽設定，不是客戶端目的位址；Ollama 的預設 `11434` 是另一個服務，不是本程式 API port。

首次辨識會下載 Whisper 模型至 `models/`。模型與地圖準備完成後，查詢在本機執行。Swagger 頁面需要 CDN，完全離線時可使用命令列或 HTTP API。

## 每個 API 的使用範例

以下使用 Bash／curl。服務需先啟動；`recording.wav` 請換成自己的音訊檔案。回傳內容為格式示例，地點、筆數與辨識文字會依輸入及資料版本改變。

### POST /api/audio：語音輸入，同時輸出地點、回覆與 BC → D

假設音訊內容是「請幫我找一個可以休息的地方」，以上位機提供的座標搜尋 5 公里內地點：

```bash
curl -sS -X POST http://127.0.0.1:8001/api/audio \
  -F 'file=@recording.wav' \
  -F 'language=zh' \
  -F 'latitude=25.033' \
  -F 'longitude=121.565' \
  -F 'radius_km=5' \
  -F 'limit=1'
```

成功回傳示例（地點物件僅列部分欄位）：

```json
{
  "places": [
    {
      "osm_id": "node/2428293148",
      "name": "市政府(松壽)",
      "county": "臺北市",
      "district": "信義區",
      "latitude": 25.0360098,
      "longitude": 121.5646026,
      "categories": ["rest"],
      "distance_m": 337.1
    }
  ],
  "reply": "以指定座標搜尋直線距離5公里內的休息設施；離線資料無法確認目前是否有空位。",
  "bc_to_d": {
    "intent": "search_rest_stop",
    "conditions": {},
    "raw_text": "請幫我找一個可以休息的地方"
  }
}
```

音訊包含「找個室內、有座位、行駛500公尺內的地方」，且上位機指定修改 `loc_002` 時：

```bash
curl -sS -X POST http://127.0.0.1:8001/api/audio \
  -F 'file=@recording.wav' \
  -F 'language=zh' \
  -F 'context_json={"reference":{"type":"modify","target_candidate_id":"loc_002"}}'
```

此時回傳 `places: []`，`bc_to_d.conditions` 包含 `indoor: true`、`has_seating: true`、`max_drive_distance_m: 500`，`reference` 保留上位機指定值。完整外層格式與下方文字 API 的條件範例相同，`raw_text` 則來自實際語音辨識。

音訊也可直接傳經緯度、type 與候選 ID，不必包在 `context_json`：

```bash
curl -sS http://127.0.0.1:8001/api/audio \
  -F 'file=@examples/rest-stop.wav' \
  -F 'language=zh' \
  -F 'latitude=23.718645' \
  -F 'longitude=120.573271' \
  -F 'type=modify' \
  -F 'target_candidate_id=loc_002'
```

回應仍為 `places`、`reply`、`bc_to_d`。`bc_to_d` 包含原樣傳入的 `latitude`、`longitude`、`type`，以及組成的 `reference`；其內容與下方 `/api/intent` 經緯度範例相同。指定操作時由 D 處理，`places` 為空。成功處理後的位置可用 `/api/location` 查詢。

### POST /api/text：文字搜尋與條件抽取

指定縣市、行政區及類別：

```bash
curl -sS -X POST http://127.0.0.1:8001/api/text \
  -H 'Content-Type: application/json' \
  -d '{"text":"找台北市中正區的咖啡店","limit":1}'
```

成功回傳示例（地點物件僅列部分欄位）：

```json
{
  "places": [
    {
      "osm_id": "node/3725707064",
      "name": "初聲咖啡店",
      "county": "臺北市",
      "district": "中正區",
      "latitude": 25.0418715,
      "longitude": 121.5109423,
      "categories": ["cafe"],
      "distance_m": null
    }
  ],
  "reply": "找到符合條件的地點：初聲咖啡店。未提供目前位置，這些結果未按距離排序。",
  "bc_to_d": {
    "intent": "search_place",
    "conditions": {},
    "raw_text": "找台北市中正區的咖啡店"
  }
}
```

上位機指定操作與目標，並抽取條件：

```bash
curl -sS -X POST http://127.0.0.1:8001/api/text \
  -H 'Content-Type: application/json' \
  -d '{"text":"找個室內、有座位、行駛500公尺內的地方","reference":{"type":"modify","target_candidate_id":"loc_002"}}'
```

回傳格式：

```json
{
  "places": [],
  "reply": "已抽取指定候選的操作與條件，交由 D 模組處理；此服務未修改任務狀態。",
  "bc_to_d": {
    "intent": "search_rest_stop",
    "conditions": {
      "indoor": true,
      "has_seating": true,
      "max_drive_distance_m": 500
    },
    "reference": {
      "type": "modify",
      "target_candidate_id": "loc_002"
    },
    "raw_text": "找個室內、有座位、行駛500公尺內的地方"
  }
}
```

### POST /api/intent：文字或音訊直接取得 BC → D JSON

**音訊輸入：** 直接上傳音訊即可，不必先呼叫 `/api/audio`。此端點不會讀取先前請求的音訊；每次音訊請求都要上傳 `file`。

```bash
curl -sS -X POST http://127.0.0.1:8001/api/intent \
  -F 'file=@recording.wav' \
  -F 'language=zh'
```

音訊內容若為「找個室內、有座位、行駛500公尺內的地方」，成功時直接得到 `intent`、`conditions`、`raw_text`；未提供上位機上下文時不輸出 `reference`。

**音訊直接傳經緯度、操作與目標 ID：**

```bash
curl -sS -X POST http://127.0.0.1:8001/api/intent \
  -F 'file=@recording.wav' \
  -F 'language=zh' \
  -F 'latitude=23.718645' \
  -F 'longitude=120.573271' \
  -F 'type=modify' \
  -F 'target_candidate_id=loc_002'
```

假設語音為「請幫我找一個可以休息的地方」，回傳示例：

```json
{
  "intent": "search_rest_stop",
  "conditions": {},
  "reference": {"type": "modify", "target_candidate_id": "loc_002"},
  "raw_text": "請幫我找一個可以休息的地方",
  "latitude": 23.718645,
  "longitude": 120.573271,
  "type": "modify"
}
```

- 經緯度為 WGS84 十進位度數，須成對提供；緯度 -90～90、經度 -180～180，不接受 NaN／Infinity。回傳保留上位機傳入的座標，不由模型推測，也不在此介面搜尋地點或計算路線。
- `type` 由上位機指定（英文字母開頭，允許英數、底線、連字號，最多 64 字），原樣回傳；只傳 `type` 時不編造目標 ID。
- `target_candidate_id` 是非空、無空白、最多 128 字的候選 ID。直接提供目標時需同時指定 `type`，或沿用上下文的 `reference_type`／`reference.type`。目標會放在回應的 `reference.target_candidate_id`。
- 舊的 `context_json` 仍可使用；直接欄位與上下文的 type 或目標不同時回傳 422。未提供的座標及頂層 `type` 不輸出。
- JSON 文字也可直接傳入這些欄位：

```bash
curl -sS http://127.0.0.1:8001/api/intent \
  -H 'Content-Type: application/json' \
  -d '{"text":"找休息地點","latitude":23.718645,"longitude":120.573271,"type":"modify","target_candidate_id":"loc_002"}'
```

**音訊加上位機操作：**

```bash
curl -sS -X POST http://127.0.0.1:8001/api/intent \
  -F 'file=@recording.wav' \
  -F 'language=zh' \
  -F 'context_json={"reference":{"type":"modify","target_candidate_id":"loc_002"}}'
```

支援與 `/api/audio` 相同的音訊格式、25 MiB／5 分鐘限制及語音辨識模型。若指定「第二個」等候選但缺少候選清單或 type，回傳 422 `clarification_needed`。格式錯誤的上下文也會回傳 422，不會忽略後繼續執行。

**原有 JSON 文字輸入仍可使用：**

```bash
curl -sS -X POST http://127.0.0.1:8001/api/intent \
  -H 'Content-Type: application/json' \
  -d '{"text":"找個室內、有座位、行駛500公尺內的地方","reference":{"type":"modify","target_candidate_id":"loc_002"}}'
```

此介面直接回傳以下物件，沒有 `places`、`reply` 或外層 `bc_to_d`：

```json
{
  "intent": "search_rest_stop",
  "conditions": {
    "indoor": true,
    "has_seating": true,
    "max_drive_distance_m": 500
  },
  "reference": {
    "type": "modify",
    "target_candidate_id": "loc_002"
  },
  "raw_text": "找個室內、有座位、行駛500公尺內的地方"
}
```

### GET /api/places/info：查看本機地點資料

```bash
curl -sS http://127.0.0.1:8001/api/places/info
```

回傳示例（僅列部分欄位）：

```json
{
  "region": "臺灣",
  "schema_version": 2,
  "osm_timestamp": "2026-09-29T20:22:51Z",
  "place_count": 300695,
  "district_count": 368,
  "attribution": "© OpenStreetMap contributors",
  "license": "ODbL 1.0"
}
```

完整結果另含 `counties`、`county_counts`、`category_counts`、來源 URL、SHA-256 與邊界覆蓋限制；此請求不呼叫 Ollama。

### GET /api/location：查詢最近一次位置

```bash
curl -sS http://127.0.0.1:8001/api/location
```

成功回傳示例：

```json
{
  "latitude": 23.718645,
  "longitude": 120.573271,
  "updated_at": "2026-10-02T09:22:00+00:00",
  "source": "/api/audio"
}
```

- 只保留**最近一次成功儲存的位置**，不是歷史軌跡。`updated_at` 是伺服器儲存時間（UTC），不是 GPS 採樣時間。
- `/api/audio` 以及 `/api/intent` 的音訊／JSON 請求，只要成功並明確提供成對經緯度，就更新紀錄；未提供座標或處理失敗時保留原紀錄。不從模型回答或逐字稿推測紀錄位置。
- 寫入 `data/last_location.json`，採原子替換；重新啟動服務後仍可查詢。紀錄不存在時回傳 404 `location_not_found`，檔案損壞或無法讀寫時回傳 503 `location_unavailable`。
- 此版本是**整個服務共用一筆紀錄**，沒有依使用者或裝置區分。Git 中附帶的是範例位置，下載後未送出新座標前，查到的是該紀錄。
- 位置紀錄已納入 Git；重新推送 `data/last_location.json` 時會更新共享的位置內容。地圖資料庫仍不推送。

### GET /docs：互動測試頁

瀏覽器開啟 [Swagger UI](http://127.0.0.1:8001/docs)，展開 API → **Try it out** → 填入資料 → **Execute**。音訊可直接選取檔案。

```bash
curl -sS http://127.0.0.1:8001/docs
```

回傳 HTTP 200 與 HTML 頁面，不是 JSON。

### GET /redoc：API 閱讀文件

瀏覽器開啟 [ReDoc](http://127.0.0.1:8001/redoc)，查看請求與回應欄位結構。

```bash
curl -sS http://127.0.0.1:8001/redoc
```

回傳 HTTP 200 與 HTML 頁面。Swagger／ReDoc 的前端資源需要 CDN。

### GET /openapi.json：取得 OpenAPI 規格

```bash
curl -sS http://127.0.0.1:8001/openapi.json
```

回傳 HTTP 200 與 JSON，包含 `openapi`、`info`、`paths`、`components` 等欄位；上位機可用來產生 API 客戶端或檢查資料結構。

### GET /：導向互動文件

```bash
curl -sS -D - -o /dev/null http://127.0.0.1:8001/
```

回傳 HTTP 307，回應標頭包含 `location: /docs`。自動跟隨導向：

```bash
curl -sS -L http://127.0.0.1:8001/
```

最後取得 Swagger HTML 頁面。

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
curl http://127.0.0.1:8001/api/text \
  -H 'Content-Type: application/json' \
  -d '{"text":"找一個休息地點","latitude":23.71,"longitude":120.54,"radius_km":5,"limit":5}'
```

音訊 API：

```bash
curl http://127.0.0.1:8001/api/audio \
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
- `bash run.sh --serve --port 8001`：指定服務埠（預設 8001）。
- 音訊上限 25 MiB、5 分鐘、轉錄 6000 字；一次處理一段音訊。
- 地點資料只涵蓋已標註設施，無法確認即時營業、空位及通行權限。休息查詢需要座椅等相關標註。
- 1B 模型可能誤判意圖；目前支援單一類別、地名、縣市、鄉鎮市區和半徑，不支援複雜否定、價格或即時條件。

## BC → D 意圖介面

`POST /api/text` 與 `POST /api/audio` 在原回應中新增 `bc_to_d`。`POST /api/intent` 接受 JSON 文字或 multipart 音訊，只回傳 BC → D 物件，不需要地圖資料庫。

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
curl http://127.0.0.1:8001/api/audio   -F 'file=@recording.wav' -F 'language=zh'   -F 'context_json={"reference_type":"modify","candidate_ids":["loc_001","loc_002"]}'
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

## 下載範例與驗證結果

`examples/rest-stop.wav` 是合成語音「請幫我找一個可以休息的地方」，不是私人錄音。`examples/intent-request.json` 提供文字、經緯度、type 與候選 ID。`examples/verify_api.py` 會依序呼叫文字意圖、音訊意圖、音訊完整回應及位置查詢，印出實際 JSON 並檢查關鍵欄位。

在 `bc` 目錄安裝依賴及 Whisper／Ollama 模型並啟動服務後，另一個終端執行：

```bash
.venv/bin/python examples/verify_api.py
```

跨電腦可使用：

```bash
.venv/bin/python examples/verify_api.py --base-url http://伺服器區網IP:8001
```

成功最後會印出 `PASS：文字、音訊、操作欄位與位置紀錄驗證完成。`；失敗時印出錯誤並以非零狀態結束。這組範例會把位置更新成 `23.718645, 120.573271`。因為提供完整 reference，範例不會執行地圖搜尋，無需先建置全臺資料庫；Ollama 與 Whisper 仍需可用。

2026-10-02 實際驗證（Whisper `small`、Ollama `llama3.2:1b`、port 8001）：

| 驗證項目 | 結果 |
| --- | --- |
| JSON `/api/intent` | HTTP 200；抽取室內、座位與 `max_drive_distance_m: 500` |
| 音訊 `/api/intent` | HTTP 200；直接回傳 BC → D，辨識出範例語音，保留座標及 `modify / loc_002` |
| 音訊 `/api/audio` | HTTP 200；回傳 `places`、`reply`、`bc_to_d`，BC → D 保留相同座標及操作 |
| `/api/location` | HTTP 200；與輸入經緯度相同，source 依序為 `/api/intent`、`/api/audio` |
| 服務重啟後查位置 | HTTP 200；座標、來源及更新時間完整保留 |
| 內部自動檢查 | 50 項通過，包含經緯度範圍、成對欄位、type／ID 衝突、失敗不覆寫、缺少／損壞紀錄及既有搜尋回歸 |

本次提交的範例位置紀錄 `updated_at` 為 `2026-10-02T09:22:40.941438+00:00`，source 為 `/api/audio`。其他人執行驗證後時間會更新；原始測試日誌與內部測試檔不納入 Git。
