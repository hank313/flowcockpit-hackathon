# A1 端:目前進度與尚未解決事項

> 更新日期:2026-10-03 ｜ 對應完整送件截止:2026/10/7(三)12:00
> 測試環境:Android Studio 模擬器(Pixel Tablet)+ 同一台電腦上的 D(`:8000`)與 BC(`:8001`)

本文件整理 **A1/A2 這一端已打通的範圍**,以及**還沒解決、需要各模組對齊或補實作的事項**。每一項都標明「建議負責人」與「驗證程度」:

- **已實測**:有實際執行並看到結果。
- **依程式碼推斷**:讀程式碼得出的結論,尚未實際操作驗證,實作前請先重現一次。

---

## 一、目前已打通的範圍

```
按住麥克風 → App 錄 wav(16kHz/單聲道)→ POST D /api/audio
  → D 轉給 BC /api/intent(faster-whisper + Ollama llama3.2:1b)
  → D 更新任務狀態(version +1)→ WebSocket 推 UI JSON → App 收到並另存 d_output.json
```

| 環節 | 狀態 |
| --- | --- |
| 模擬器錄音、取得 wav | 已實測 |
| App 自動上傳給 D | 已實測(D log 出現 `POST /api/audio 200 OK`) |
| D → BC 辨識(中文) | 已實測。「幫我找一個有室內空間的地方」辨識正確,條件抽成 `indoor: true` |
| D 推播 → App 收到 | 已實測。模擬器 `files/d_output.json` 內含 D 推播的 JSON 與 `raw_text` |
| 連不上 D 時讀 `d_output.json` 當備援 | 已寫,**尚未測試** |

**這次 A1 端新增/修改的檔案**

| 檔案 | 內容 |
| --- | --- |
| `app/.../data/WavRecorder.kt`(新) | 按住期間錄音,放開後存成 `cache/voice.wav` |
| `app/.../data/HttpAiBox.kt`(新) | 上傳錄音、連 WebSocket、另存 `d_output.json`、離線備援 |
| `app/.../MainActivity.kt` | 啟動時要麥克風權限;改用 `HttpAiBox`,位址 `10.0.2.2:8000` |
| `AndroidManifest.xml` | `RECORD_AUDIO`、`INTERNET`、`usesCleartextTraffic` |
| `CockpitController.kt` | 處理中逾時 10 秒 → 30 秒 |
| `libs.versions.toml`、`app/build.gradle.kts` | 加入 OkHttp 4.12.0 |

`AssetJsonAiBox`、`FakeAiBox` 仍保留,沒有刪除;要回到假資料開發時,把 `MainActivity` 的 gateway 換回去即可。

---

## 二、尚未解決事項

優先順序依「是否擋住決賽 Demo 五步驟」排列。Demo 步驟:① 新輸入 ② 改選擇 ③ 斷網 ④ 恢復連網 ⑤ 完成確認。

| # | 事項 | 擋住的步驟 | 建議負責 | 驗證程度 |
| --- | --- | --- | --- | --- |
| 1 | 候選清單是空的 | ①②④ | D(+BC) | 已實測 |
| 2 | 條件欄位名稱與單位不一致 | ①②③ | D、BC | 依程式碼推斷 |
| 3 | 「留下第二個」類語音無法運作 | ② | D、BC | 依程式碼推斷 |
| 4 | D 沒有處理 `UPDATE_FILTER` | ②③ | D | 依程式碼推斷 |
| 5 | 雲端 E 服務不存在 | ④ | E | 已實測 |
| 6 | 確認後面板重新彈出、無「開新任務」 | ⑤ | D、A2 | 依程式碼推斷 |
| 7 | BC 的錯誤被 D 靜默忽略 | ①② | D | 依程式碼推斷 |

### 1. 候選清單是空的(最優先)

**現象**:語音辨識成功後,App 面板有條件開關,但 `candidate_list.items` 永遠是 `[]`。

**原因**
- D 轉給 BC 的是 `/api/intent`,README 明說它「不查地圖」,只回 `intent`、`conditions`、`raw_text`。
- D 的候選只來自雲端 E(`:8002/api/cloud_search_places`),該服務不存在(見 #5)。
- D 已移除內建示範地點,資料庫只存狀態,`candidates_json` 初始即為空陣列。

**建議做法(D)**:改呼叫 BC 的 `/api/audio`(同樣回傳 `bc_to_d`,另多 `places`),再把 `places` 轉成 App 認得的格式:

| BC `places` 欄位 | D → App `candidate_list.items` 欄位 |
| --- | --- |
| `osm_id`(如 `node/2428293148`) | `id` |
| `name` | `name` |
| `categories`(英文代碼 `rest`、`cafe`…) | `tags`(建議轉成中文) |
| `distance_m` | `drive_distance_desc`(例:「直線距離 0.3 公里」) |
| 無 | `drive_eta_desc`(缺少時 App 會略過,不會壞) |

**注意事項**
- BC 的距離是**直線距離**,沒有行駛時間,不要在 UI 宣稱是行車距離。
- 「修改」類語音(如「留下第二個」)BC 回傳 `places: []`,D 應**保留原候選**,不要用空清單覆蓋。
- D 目前沒有傳 `radius_km`、`limit` 給 BC,BC 在沒有半徑時的搜尋範圍**需要確認**。
- 查地點需要 BC 的地圖資料庫 `bc/data/taiwan.sqlite3`,**目前沒有建**。作法見 `bc/README.md`「準備本機地圖資料」(下載 Geofabrik 的 Taiwan `.osm.pbf` 再執行 `build_places.py`,需 `requirements-data.txt`)。在會攔截 HTTPS 的網路下,請用 `curl.exe` 下載(見附錄)。
- App 端**不用改**:字串 id、缺漏欄位現有解析器都能處理。

### 2. 條件欄位名稱與單位不一致

| 意思 | BC 輸出 | D 的 UI 讀取 |
| --- | --- | --- |
| 室內 | `indoor` | `indoor`(一致) |
| 有座位 | `has_seating` | `seating` |
| 行駛範圍 | `max_drive_distance_m`(**公尺**) | `max_drive_min`(**分鐘**) |

D 會把 BC 的條件併入 `filters_json`,但 `UIGenerator` 只讀上表右欄三個鍵,所以語音說的「有座位」、「500 公尺內」不會反映到畫面。單位也不同,不能直接對應,需要約定換算或統一欄位。

另外 D 的預設條件是 `indoor: true`、`seating: true`,語音說「有室內空間」時畫面看起來沒變化,**無法判斷條件有沒有套用**。驗證時請說會改變預設的句子,例如「找室外的地方」。

> 專案規範文件(`FlowCockpit_專案現況與分工.md`)定案的 BC → D 欄位是 `indoor`、`has_seating`、`max_walk_distance_m`,與 BC、D 現況都不完全相同,請 D、BC 一起決定以哪一份為準。

### 3. 「留下第二個」類語音無法運作

BC 要解析「第二個」,需要上位機在 `context_json` 提供上一輪**依顯示順序排列的 `candidate_ids`** 與 `reference_type`,否則回 HTTP 422 `clarification_needed`(`bc/bc_intent.py` 的 `extract`)。目前 App 與 D 都**沒有**送這些資料(D 的 `/api/audio` 只轉發 `type`、`target_candidate_id`)。

**建議做法(D)**:轉發給 BC 時,從目前任務狀態帶入 `context_json`(候選 id 清單、`reference_type`)。

### 4. D 沒有處理 `UPDATE_FILTER`

D 的 `README.md` 有寫,但 `server_d.py` 的 WebSocket 只處理 `SELECT_CANDIDATE`、`CONFIRM_DESTINATION`、`SYNC_REQUEST`;其他動作只會把目前狀態再廣播一次。App 的條件開關(`UserAction.UpdateCondition`)送出 `UPDATE_FILTER` 後**不會有任何效果**。

### 5. 雲端 E 服務不存在

D 會呼叫 `http://127.0.0.1:8002/api/cloud_search_places`,但 `e/` 內沒有這個端點(`cloud_enhance.py`、`integrate_ui.py`、`task_version_guard.py`、`test_claude_api.py` 皆非服務)。D 的 log 每次都會出現「雲端 AI 呼叫略過」。因此 `comparison_panel` 的雲端取捨文字**從未產生過**,Demo 步驟 ④ 目前做不出來。

D 已有 `POST /internal/apply_cloud_comparison`(含過期版本丟棄),E 可直接呼叫它,不一定要走 D 主動呼叫 E 的方向,請 D、E 決定。

### 6. 確認後面板重新彈出、無「開新任務」

- App 按確認時,`CockpitController.onAction` 會先把 `ui` 設為 `null` 並重設 `taskId`、`version`,接著 D 對 `CONFIRM_DESTINATION` 一定會廣播一份 `CONFIRMED` 的 UI,App 會因為 `taskId` 已清空而**接受它,面板再次彈出**。
- D 沒有「開新任務」機制:確認後仍是同一個 `task_id`,狀態一直是 `CONFIRMED`。
- 若 App 改用新的 `task_id` 上傳,`update_task_state` 在資料列不存在時會直接 `return get_or_create_task(...)`,**第一次語音的條件會被丟掉**。

**建議**:D 在確認後不廣播(或廣播時 App 忽略 `status = CONFIRMED`),並提供新任務流程;A2 端配合調整 `HttpAiBox` 的 task_id 管理。目前重新 Demo 的土法是刪除 `d/flowcockpit.db` 後重啟 D。

### 7. BC 的錯誤被 D 靜默忽略

`server_d.py` 的 `/api/audio` 只在 BC 回 200 時才採用結果,其他情況(例如 `no_speech` 未辨識到語音、`clarification_needed`、連不上)都會變成空的 `bc_intent_data`,D 不更新任何內容也不通知 App。

**後果**:使用者說錯話或沒說話時,App 停在「AI 處理中」直到 30 秒逾時才恢復。

**建議(D)**:BC 回 `clarification_needed` 時,在 UI JSON 的 `payload.clarification_needed` 填入問句。A1 的澄清 UI 已經寫好,但 D 的 `build_ui_json` **完全沒有輸出這個欄位**。

---

## 三、A1/A2 自己的待辦

| 事項 | 說明 |
| --- | --- |
| 顯示辨識文字 | D 已送 `raw_text`(在 `filter_controls.data` 內),`UiJsonParser` 沒有讀取,畫面看不到「你說了什麼」。建議在 `AiPanel` 頂端顯示 |
| 錄音/上傳失敗沒有回饋 | 沒有麥克風權限、錄音太短(< 0.3 秒)或上傳失敗時,`HttpAiBox` 靜默返回,麥克風狀態停在「處理中」直到逾時。建議立即回到 Idle 並提示 |
| 連線一建立面板就彈出 | D 在 WebSocket 連上時會推一次目前狀態,App 啟動就顯示 AI 面板。是否要等第一次語音再顯示,請 A1、A2 決定 |
| 離線備援與版本號衝突 | 備援只在「連不上 D 且從未收過即時訊息」時送出。若備援 JSON 的 version 大於 D 之後的版本,`CockpitController` 會把 D 的新訊息當成舊版丟棄,需重啟 App。備援機制**尚未測試** |
| 後端位址寫死 | `MainActivity` 的 `AI_BOX_HOST = "10.0.2.2:8000"` 只適用模擬器。實機平板要改成 AI Box 的區網 IP,建議改成可設定 |
| 明文連線設定 | `usesCleartextTraffic="true"` 是開發用寫法。送件前建議改為 `networkSecurityConfig` 只放行區網位址 |
| 條件調整的語音驗證 | 尚未用「改變預設值」的語音(室外、10 分鐘內…)驗證條件是否真的生效,見 #2 |

---

## 四、其他模組的小問題(順手修)

| 模組 | 問題 |
| --- | --- |
| D | 舊版 `flowcockpit.db` 的資料表欄位與新程式不符(缺 `candidates_json`),會讓 `/ws` 與 `/api/audio` 連續報 `IndexError`。`CREATE TABLE IF NOT EXISTS` 不會升級舊表。本機已把舊檔改名為 `flowcockpit.old-schema.db` 處理。建議 D 加上欄位檢查或遷移 |
| D | `update_task_state` 發生例外時沒有關閉資料庫連線,檔案會一直被佔用,Windows 上無法改名或刪除 |
| D | `d/README.md` 仍寫「內建 8 筆示範地點」與 `UPDATE_FILTER`,與現行程式不符 |
| D | `d/requirements.txt` 原本缺 `httpx`、`python-multipart`,已補上 |
| BC | `app.py` 載入 Whisper 失敗時,真正的錯誤被吞掉,只回「無法載入 Whisper」。建議記錄原始例外,否則難以診斷(見附錄的憑證問題) |
| BC | `run.sh` 只能用 Bash,Windows 需手動啟動(見附錄) |

---

## 附錄:在 Windows 上重現目前環境

### 啟動順序

1. **Ollama**:安裝後會常駐背景(埠 `11434`),需有模型 `llama3.2:1b`(`ollama pull llama3.2:1b`)。
2. **BC**(`bc/`):

   ```powershell
   cd bc
   py -3.12 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   $env:WHISPER_MODEL = "<專案路徑>\bc\models\faster-whisper-small"   # 見下方說明
   $env:PYTHONIOENCODING = "utf-8"
   .\.venv\Scripts\python.exe app.py --serve                          # 127.0.0.1:8001
   ```

3. **D**(`d/`,**必須在 `d/` 目錄下執行**,資料庫用相對路徑):

   ```powershell
   cd d
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe server_d.py                             # 0.0.0.0:8000
   ```

4. **App**:Android Studio 執行到 Pixel Tablet 模擬器。模擬器要開啟 **Extended controls → Microphone → Virtual microphone uses host audio input**,Windows「隱私權 → 麥克風」也要允許,否則錄到的是靜音。

### 若 Python 下載 Whisper 模型失敗(憑證錯誤)

在會做 HTTPS 檢查的網路(學校、公司)下,Python 會出現 `CERTIFICATE_VERIFY_FAILED` 或 `WinError 10054`,BC 回 `asr_load_failed`,但 PowerShell 與 `curl.exe` 正常(它們使用 Windows 憑證庫)。**不要關閉憑證驗證**,改用 `curl.exe` 手動下載模型到本機資料夾,再用 `WHISPER_MODEL` 指向它:

```powershell
$d = "bc\models\faster-whisper-small"; New-Item -ItemType Directory -Force $d
$base = "https://huggingface.co/Systran/faster-whisper-small/resolve/main"
foreach ($f in "config.json","tokenizer.json","vocabulary.txt","model.bin") {
  curl.exe -L --fail --retry 5 -C - -o "$d\$f" "$base/$f"
}
```

`model.bin` 的 SHA256 應為 `3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671`。`bc/models/` 已被 `.gitignore` 忽略。

### 手動測試(不經過 App)

```powershell
# 只測 BC
curl.exe -sS -X POST http://127.0.0.1:8001/api/intent -F "file=@bc\examples\rest-stop.wav" -F "language=zh"
# 測 D → BC 整條
curl.exe -sS -X POST http://127.0.0.1:8000/api/audio -F "file=@bc\examples\rest-stop.wav" -F "task_id=demo_task_001"
# 從模擬器取出 App 錄的音(PowerShell 的 > 會弄壞二進位,要用 Start-Process 導向)
$adb = "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
Start-Process $adb -ArgumentList "exec-out","run-as","com.example.testapp","cat","cache/voice.wav" -RedirectStandardOutput "bc\examples\my-voice.wav" -NoNewWindow -Wait
```

`bc/.gitignore` 已忽略 `*.wav`(僅 `examples/rest-stop.wav` 例外),自己的錄音不會被提交。**請勿覆蓋 `rest-stop.wav`**,它是 BC 共用的範例檔。
