# A1 端:目前進度與尚未解決事項

> 更新日期:2026-10-03(已對照 D 的 commit `219b1ae`,並含本機對 D 與 BC 的修改) ｜ 對應完整送件截止:2026/10/7(三)12:00
> 測試環境:Android Studio 模擬器(Pixel Tablet)+ 同一台電腦上的 D(`:8000`)與 BC(`:8001`)

本文件整理 **A1/A2 這一端已打通的範圍**,以及**還沒解決、需要各模組對齊或補實作的事項**。每一項都標明「建議負責人」與「驗證程度」:

- **已實測**:有實際執行並看到結果。
- **依程式碼推斷**:讀程式碼得出的結論,尚未實際操作驗證,實作前請先重現一次。

---

## 一、目前已打通的範圍

```
按住麥克風 → App 錄 wav(16kHz/單聲道)→ POST D /api/audio
  → D 轉給 BC /api/intent(faster-whisper + Ollama llama3.2:1b)取得意圖與條件
  → D 向 BC /api/text 查「實際地點」(BC 本機 OSM 資料庫,30 萬筆)
  → D 更新任務狀態(version +1)→ WebSocket 推 UI JSON → App 渲染,並另存 d_output.json
```

| 環節 | 狀態 |
| --- | --- |
| 模擬器錄音、取得 wav | 已實測 |
| App 自動上傳給 D | 已實測 |
| D → BC 辨識(中文) | 已實測。「幫我找一個有室內空間的地方」辨識正確,條件抽成 `indoor: true`。BC 辨識約 1.4 秒(RTX 5070 Ti 筆電) |
| **BC 地圖資料庫** | **已建立**:`bc/data/taiwan.sqlite3`,304,219 筆地點、22 縣市、368 鄉鎮,OSM 快照 2026-10-02 |
| **候選為實際地點** | **已實測**:語音「請幫我找一個可以休息的地方」與「幫我找一個有室內空間的地方」,D 都推出 5 筆實際地點(摩爾花園、全家便利商店、一品鍋、桃花源餐廳斗六總店、斗六市未命名公園),不含任何示範資料。整段約 4–6 秒 |
| D 推播 → App 收到 | 已實測(模擬器 `files/d_output.json` 內含 D 推播的 JSON) |
| 連不上 D 時讀 `d_output.json` 當備援 | 已寫,**尚未測試** |

**這次 A1 端新增/修改的檔案**

| 檔案 | 內容 |
| --- | --- |
| `app/.../data/WavRecorder.kt`(新) | 按住期間錄音,放開後存成 `cache/voice.wav` |
| `app/.../data/HttpAiBox.kt`(新) | 上傳錄音、連 WebSocket、另存 `d_output.json`;離線備援改為「錄音送不出去且從未連上 D」時才顯示 |
| `app/.../MainActivity.kt` | 啟動時要麥克風權限;改用 `HttpAiBox`,位址 `10.0.2.2:8000` |
| `AndroidManifest.xml` | `RECORD_AUDIO`、`INTERNET`、`usesCleartextTraffic` |
| `CockpitController.kt` | 處理中逾時 10 秒 → 30 秒;**錄音送出並收到結果後才顯示 AI 建議面板**(啟動、收合、確認之後 D 推來的狀態只記錄版本,不顯示) |
| `libs.versions.toml`、`app/build.gradle.kts` | 加入 OkHttp 4.12.0 |

`AssetJsonAiBox`、`FakeAiBox` 仍保留,沒有刪除;要回到假資料開發時,把 `MainActivity` 的 gateway 換回去即可。

---

## 二、本機對 D 與 BC 的修改(尚未 commit,請 D、BC 負責人審閱)

**D(`d/server_d.py`)**:目標是「只用實際地點,不用示範地點」。

| 改動 | 說明 |
| --- | --- |
| 移除 `FALLBACK_PLACES` | 寫死的 3 筆店家整個刪除。新任務與 `RESET_TASK` 的初始候選為空(App 會顯示既有的「沒有符合條件的地點」提示) |
| 新增 `fetch_real_places` | 向 BC `/api/text` 查地點。**BC 的「休息設施」類別(長椅、野餐桌、車站月台)在 OSM 很稀疏**:雲科大預設座標 3 公里內為 0 筆(最近的是 3.4 公里外的斗六火車站月台)。所以「找休息地點」改查休息設施、咖啡店、便利商店、公園、餐廳五類,依距離合併取前 5 筆 |
| 觸發規則 | 意圖是 `search_rest_stop`,**或語音含條件**(BC 遇到條件不回地點,交給 D 篩選)→ 查上述五類。其他找地點的語音(例如「找加油站」)→ 照使用者說的話查 |
| 搜尋半徑 | 取自 `max_drive_distance_m` 條件(預設 3000 公尺;語音說「500 公尺內」會覆蓋)。BC 的距離是**直線距離** |
| 保留原候選的情況 | BC 辨識出錯(沒有意圖資料)、語音不是找地點(`chat`、`clarify`)、BC 地點查詢連不上 |
| 查不到時 | 候選清單設為空,原因記在資料庫的 `error_message`(**目前不會送給 App**,見 #5) |
| 其他 | 重新搜尋後清除舊選取;查地點逾時 5 秒 → 15 秒 |
| **候選池與條件篩選** | 每次語音搜尋把查到的地點(五類各最多 20 筆,合併後依距離排序)存成**候選池**,畫面顯示的是池中符合目前條件的前 5 筆。App 按「室內／有座位／有餐飲」開關或 1／3／5／10 km 按鈕(`UPDATE_FILTER`)時,**從候選池重新篩選(即時)**;只有距離放寬到超出候選池的半徑時,才用同樣的搜尋方式重新查詢(約 3 秒)。已選地點若被篩掉會清除選取 |
| 開關語意 | 室內/有座位/有餐飲:**開 = 只顯示有該屬性的地點,關 = 只顯示沒有該屬性的地點**(例如關閉「室內」只顯示室外)。語音說「室外」(BC 回 `indoor: false`)也一樣只找室外地點。**預設三個開關都是開**(`DEFAULT_FILTERS`;「有餐飲」原本預設是關,在這個語意下預設會變成「只找沒有餐飲的地點」而查不到東西,所以改成開) |
| 屬性推測 | OSM 沒有可靠的室內/座位欄位,D 依類別推測:**餐廳、咖啡店 = 室內、有座位、有餐飲**;**便利商店 = 室內、有餐飲、座位視為沒有**(座位不明);**長椅、野餐桌、有標座位數的地點 = 有座位**;公園 = 戶外、沒有座位(除非標了長椅) |
| 限制 | 候選池只存在記憶體,D 重啟後遺失(此時只能再篩選畫面上現有的候選,補不回已被篩掉的)。**預設(三個開關都開)只會看到餐廳/咖啡店**;要看便利商店需關閉「有座位」,要看公園需關閉「室內」「有座位」「有餐飲」三個。**只關閉「室內」會得到 0 筆**(室外且有座位且有餐飲的地點不存在),畫面會顯示「沒有符合條件的地點」 |

已實測(D 直接測,以及在模擬器的 App 上實際點擊):
- 預設(三個開關都開):5 筆都是室內、有座位、有餐飲的餐廳。
- **取消「有座位」→ 只剩沒有座位的(5 間全家便利商店)**;再選回 → 又只剩有座位的。
- **取消「室內」「有座位」「有餐飲」→ 只剩室外、無座位、無餐飲的地點(5 個公園)**。在模擬器的 App 上實際連點三個開關也驗證通過。
- 取消「室內」但「有座位」「有餐飲」仍開 → 0 筆;室內開、有座位關、有餐飲開 → 便利商店,加上距離 1 km → 0 筆(最近的全家 1038 m)。
- 距離按鈕:1 km → 剩 917 m 那 1 筆(App 上實際點「1 km」,一品鍋 1.4 km 等超出範圍的地點消失),0.5 km → 0 筆,放寬到 10 km → 重新查詢補回。
- 其他:不限半徑、半徑 0.3 公里(查不到)、指定類別(加油站 3 筆、咖啡店 0 筆)、BC 無法連線(保留原候選)皆符合預期。

**App(A1 端)**:`CockpitController` 新增 `awaitingResult`,按住麥克風放開時設為 true,收合面板、按確認時設為 false;收到 D 的訊息時仍記錄 `taskId`、`version`,但 `awaitingResult` 為 false 就不更新畫面。已在模擬器實測:剛啟動沒有面板;閒置時 D 推播了 5 筆候選,面板**仍沒有出現**;按住麥克風、放開、收到結果後面板才出現。

**BC(`bc/build_places.py`)**:在 `target.replace(DB_PATH)` 前加上 `db.close()`。原因是 `with sqlite3.connect() as db` 只提交、不關閉連線,Linux 可以替換仍開啟的檔案,**Windows 不行**(`WinError 32`),導致建庫在最後一步失敗。Linux 上行為不變。

---

## 三、尚未解決事項

優先順序依「是否擋住決賽 Demo 五步驟」排列。Demo 步驟:① 新輸入 ② 改選擇 ③ 斷網 ④ 恢復連網 ⑤ 完成確認。

**自上一版審查後已解決**:候選改為實際地點(本機修改,見上節)、條件欄位統一為 `indoor`/`has_seating`/`max_drive_distance_m`(D `219b1ae`,與 BC 一致)、`CONFIRM_DESTINATION` 會記錄所選候選(D `219b1ae`)、`UPDATE_FILTER` 與 `RESET_TASK` 已實作(D)、BC 出錯時不再重置候選(本機修改)、**行駛距離與「室內/有座位/有餐飲」開關都會篩選候選,開 = 只顯示有、關 = 只顯示沒有(本機修改)**、**餐廳、咖啡店不再被標成「沒有座位」(本機修改)**、**AI 建議面板只在錄音送出並收到結果後才顯示(本機修改)**。

| # | 事項 | 擋住的步驟 | 建議負責 | 驗證程度 |
| --- | --- | --- | --- | --- |
| 1 | 「室內/有座位/有餐飲」是依類別推測的,不是真實資料 | ①②③ | D | 已實測 |
| 2 | 「留下第二個」類語音無法運作 | ② | D、BC | 部分實測 |
| 3 | App 沒用 `RESET_TASK`(面板彈回的問題已由新的顯示規則擋住) | ⑤ | A2、D | 依程式碼推斷 |
| 4 | 雲端 E 完全沒接上(**暫緩,目前不需要**) | ④ | E、D | 已實測 |
| 5 | 辨識文字與錯誤訊息沒有送到 App | ①② | D、A1 | 已實測 |
| 6 | 距離標示與「不用開太遠」的坑 | ① | D、A1 | 部分實測 |
| 7 | 候選資料品質(未命名地點、類別不精準) | ① | D | 已實測 |

### 1. 「室內/有座位/有餐飲」是依類別推測的,不是真實資料

開關與距離按鈕現在都會篩選候選(見第二節)。但**篩選依據的屬性不是真實資料**:OSM 沒有可靠的「室內」「有座位」欄位,BC 自己也說這兩項「尚未由此服務驗證」,D 只能依類別推測。實際會碰到的誤差:

| 情況 | 說明 |
| --- | --- |
| 便利商店被視為「沒有座位」 | 台灣不少便利商店有內用座位,但 OSM 沒標,D 無從得知,所以預設(有座位開)下**看不到便利商店** |
| 公園被視為「戶外、沒有座位」 | 公園多半有長椅,但只有 OSM 標了 `bench=yes` 才算有座位 |
| 餐廳、咖啡店一律視為「室內、有座位」 | 若是純外帶的店(例如攤販、飲料店)會判斷錯 |

**畫面上沒有標示這些屬性是推測的**,使用者會以為是確認過的資料。若 Demo 要讓條件完全可信,需要有這些屬性的資料(例如自建示範地點),或在畫面標示「推測」。

### 2. 「留下第二個」類語音無法運作

| 操作 | 結果 |
| --- | --- |
| 模擬 BC 回傳目標(`type=modify`、`target_candidate_id`) | 候選從多筆剩 1 筆,`selected_id` 設為該筆(已實測) |
| 實際語音「留下第二個」,BC 沒有候選上下文 | BC 回 HTTP **422** `clarification_needed`:「請由 D 傳入上一輪依顯示順序排列的 candidate_ids」(已實測) |

D 目前**沒有**把 `context_json`(候選 id 清單、`reference_type`)帶給 BC,所以真實語音一定走到 422。本機修改後 D 遇到 BC 出錯會**保留原候選**(不再重置),但「留下第二個」仍然做不到。另外 Demo 步驟 ② 是「留下第二個,**其他換成較近的**」,目前只做到「只留 1 筆」。

D 在 BC 出錯時,資料庫的 `raw_text` 會變成預設值「找休息處」(使用者沒說過這句),`error_message` 只有「BC 端錯誤: HTTP 422」,BC 給的澄清問句被丟掉。

**建議(D)**:轉發給 BC 時帶 `context_json`(依顯示順序的 `candidate_ids` 與 `reference_type`);BC 回 422 時,把 `error.message` 填進 UI JSON 的 `payload.clarification_needed`。A1 的澄清 UI 已寫好,D 的 `build_ui_json` 有輸出這個欄位,但**目前沒有任何地方會設值**。

### 3. App 沒用 `RESET_TASK`

- 原本的問題:App 按確認時會先清空面板,接著 D 對 `CONFIRM_DESTINATION` 廣播新的 UI,App 會再次彈出面板。**新的顯示規則(錄音送出並收到結果後才顯示)已擋住這個情況**:按確認時 `awaitingResult` 設為 false,D 回推的狀態只記錄版本、不更新畫面(依程式碼推斷,尚未實測確認流程)。
- D 的 `RESET_TASK` 實測可用(版本號遞增、候選與條件還原),但 **App 沒有對應的 `UserAction`,從不送它**。目前重新 Demo 要靠測試腳本送 `RESET_TASK`,或刪除 `d/flowcockpit.db` 後重啟 D。

**建議**:A2 在 `UserAction` 加 `ResetTask` 並於確認後送出。

### 4. 雲端 E 完全沒接上(暫緩,目前不需要)

> 已決定先不做雲端 E,以下僅供之後接手時參考。

- D 最新版**沒有任何呼叫 E 的程式**(`CLOUD_API_URL` 有定義但沒被使用)。`comparison_text` 欄位永遠是空的,比較面板的雲端取捨文字從未產生過,Demo 步驟 ④ 做不出來。
- E 目前只有函式 `get_comparison(candidates, conditions)`(`e/cloud_enhance.py`),**不是 HTTP 服務**,`e/` 內沒有任何端點。它拿**已有的候選**請 Claude 寫比較文字,不找地點;傳入空清單直接回 `None`。
- E 讀候選的 `attributes` 欄位(`candidate_id`、`name`、`attributes`),D 的候選是 `{id, name, indoor, has_seating, ...}`,**欄位對不上**,需要轉換。
- BC 是純本機離線,**不使用雲端**。候選一律由 BC 的本機資料庫提供,E 只負責比較文字,這符合企劃書 Stage 9,也讓斷網時(步驟 ③)核心操作仍可用。
- E 需要 `.env` 內的 Claude API Key,以及 `anthropic`、`python-dotenv` 套件。

### 5. 辨識文字與錯誤訊息沒有送到 App

D 最新版的 UI JSON **只有** `components` 與 `clarification_needed`,**不再包含 `raw_text` 與 `error_message`**,兩者只存在資料庫。所以 App 畫面看不到「你說了什麼」,查不到地點時也只能顯示 App 內建的「沒有符合條件的地點」,看不到具體原因(例如「直線距離 3 公里內找不到休息地點」)。

**建議**:D 在 UI JSON 加回 `raw_text`、`error_message`(位置自訂,與 A1 約定);A1 在 `AiPanel` 顯示辨識文字,並解析 `error_message`。

### 6. 距離標示與「不用開太遠」的坑

- **App 卡片寫「行駛 917 m」,但這是直線距離。** BC 的 `distance_m` 是直線距離(BC 明說不是行駛路程);D 把它原樣放進 `drive_distance_m`,App 的 `Attributes.kt` 把這個欄位顯示成「行駛 …」。D 另外算的 `drive_time_min`(距離 × 1.35 ÷ 時速 35 公里)**沒有送給 App**。建議改標「直線距離」,或與 D 約定欄位。
- **「不用開太遠」會讓搜尋範圍縮到 300 公尺。** BC 把「不用開太遠、不要開太遠、少開一點、開近一點」轉成 `max_drive_distance_m`,預設值 **300 公尺**(`short_drive_distance_m`),D 沒有傳自訂值,所以半徑變成 0.3 公里,附近多半查不到。建議 D 轉發時帶 `context_json` 設 `short_drive_distance_m`(例如 3000)。「不用走太遠」(用「走」不是「開」)BC 不會轉成距離條件,不受影響。
- `or 1500` 問題:D 轉換時 `distance_m` 缺少或剛好是 0 會被當成 1500 公尺。有座標時 BC 一定回距離,實際影響很小。

### 7. 候選資料品質

| 項目 | 說明 |
| --- | --- |
| 未命名地點 | OSM 沒有名稱的地點,BC 用泛稱(如「斗六市未命名公園」)當名稱並標 `name_is_label`,D 沒處理,可能出現多張看不出差別的卡片 |
| 類別不精準 | 為了湊到 5 筆,D 會合併休息設施、咖啡店、便利商店、公園、餐廳,而不是只有使用者說的類別 |
| 資料不即時 | OSM 離線快照(2026-10-02),無法確認營業時間與是否有空位(BC 回應已註明) |

---

## 四、A1/A2 自己的待辦

| 事項 | 說明 |
| --- | --- |
| 顯示辨識文字與錯誤 | 見 #5,需要 D 先送 |
| 送出 `RESET_TASK` | 見 #3,`UserAction` 加 `ResetTask`,確認後送出 |
| 距離標示 | 見 #6,「行駛」改「直線距離」或與 D 約定 |
| 錄音/上傳失敗沒有回饋 | 沒有麥克風權限、錄音太短(< 0.3 秒)或上傳失敗時,`HttpAiBox` 靜默返回,麥克風狀態停在「處理中」直到逾時。建議立即回到 Idle 並提示 |
| 離線備援與版本號衝突 | 備援只在「按麥克風錄音送不出去,且從未收過 D 的即時訊息」時顯示(讀 `d_output.json`)。若備援 JSON 的 version 大於 D 之後的版本,`CockpitController` 會把 D 的新訊息當成舊版丟棄,需重啟 App。備援機制**尚未測試** |
| 收到結果前的空窗 | 面板現在要等結果才出現。按下麥克風到收到結果約 4–6 秒,這段時間只有麥克風上的「AI 處理中」轉圈,可考慮加更明顯的等待提示 |
| 後端位址寫死 | `MainActivity` 的 `AI_BOX_HOST = "10.0.2.2:8000"` 只適用模擬器。實機平板要改成 AI Box 的區網 IP,建議改成可設定 |
| 明文連線設定 | `usesCleartextTraffic="true"` 是開發用寫法。送件前建議改為 `networkSecurityConfig` 只放行區網位址 |
| 定位 | 目前座標是 D 寫死的預設值(`23.718645, 120.573271`)。實機要改成裝置定位,模擬器可在 Extended controls → Location 設定,再由 App 把座標一併上傳 |

---

## 五、其他模組的小問題(順手修)

| 模組 | 問題 |
| --- | --- |
| D | **每次改資料表欄位,舊的 `flowcockpit.db` 都會讓 D 直接壞掉。** 已發生三次(缺 `candidates_json`、缺 `error_message`、缺 `clarification_needed`),每次都是 `/api/audio` 回 HTTP 500。`CREATE TABLE IF NOT EXISTS` 不會升級舊表。拉到新版的人都要先刪除 `d/flowcockpit.db`;建議 D 加上欄位檢查或遷移。本機已把舊檔改名備份(`flowcockpit.old-schema*.db`,共三份,皆被 git 忽略,可直接刪除) |
| D | `update_task_state` 發生例外時沒有關閉資料庫連線,檔案會一直被佔用,Windows 上無法改名或刪除 |
| D | WebSocket 迴圈的 `except` 靜默吞掉所有例外,出錯時完全沒有 log,不易除錯 |
| D | `d/README.md` 仍寫「內建 8 筆示範地點」、`/internal/apply_bc_filters`、`/internal/apply_cloud_comparison` 與舊的 UI 格式,與現行程式不符 |
| D | 每次語音會呼叫 BC 多次(`/api/intent` 加查地點),各跑一次 Ollama。目前這台機器(RTX 5070 Ti 筆電)單次約 0.5–0.9 秒、整段約 4–6 秒,沒有問題;但在沒有 GPU 的 AI Box 上**需要重測**,D 的逾時是意圖 25 秒、地點 15 秒 |
| BC | `app.py` 載入 Whisper 失敗時,真正的錯誤被吞掉,只回「無法載入 Whisper」。建議記錄原始例外,否則難以診斷(見附錄的憑證問題) |
| BC | `run.sh` 只能用 Bash,Windows 需手動啟動(見附錄) |
| BC | `build_places.py` 在 Windows 建庫失敗,已在本機修正(見第二節) |

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

3. **D**(`d/`,**必須在 `d/` 目錄下執行**,資料庫用相對路徑;**拉到新版後先刪除舊的 `flowcockpit.db`**):

   ```powershell
   cd d
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe server_d.py                             # 0.0.0.0:8000
   ```

4. **App**:Android Studio 執行到 Pixel Tablet 模擬器。模擬器要開啟 **Extended controls → Microphone → Virtual microphone uses host audio input**,Windows「隱私權 → 麥克風」也要允許,否則錄到的是靜音。

### 建立 BC 的地圖資料庫(實際地點的來源)

沒有 `bc/data/taiwan.sqlite3` 時,BC 查地點會回 503 `places_unavailable`,D 就查不到任何地點。約 1–2 分鐘、下載 312 MB、產生 189 MB 的資料庫;`bc/data/` 已被 `.gitignore` 忽略。

```powershell
cd bc
.\.venv\Scripts\python.exe -m pip install -r requirements-data.txt     # osmium、shapely
curl.exe -fL --retry 5 -C - -o data\taiwan.osm.pbf https://download.geofabrik.de/asia/taiwan-latest.osm.pbf
.\.venv\Scripts\python.exe build_places.py data\taiwan.osm.pbf --source-url https://download.geofabrik.de/asia/taiwan-latest.osm.pbf
```

建好後 BC 不需要重啟(每次查詢才開資料庫),可用 `curl.exe http://127.0.0.1:8001/api/places/info` 確認筆數。`build_places.py` 需要含 `db.close()` 修正才能在 Windows 完成(見第二節)。

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
# 只測 BC 辨識
curl.exe -sS -X POST http://127.0.0.1:8001/api/intent -F "file=@bc\examples\rest-stop.wav" -F "language=zh"
# 測 D → BC → 實際地點整條
curl.exe -sS -X POST http://127.0.0.1:8000/api/audio -F "file=@bc\examples\rest-stop.wav" -F "task_id=demo_task_001"
# 從模擬器取出 App 錄的音(PowerShell 的 > 會弄壞二進位,要用 Start-Process 導向)
$adb = "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
Start-Process $adb -ArgumentList "exec-out","run-as","com.example.testapp","cat","cache/voice.wav" -RedirectStandardOutput "bc\examples\my-voice.wav" -NoNewWindow -Wait
```

`bc/.gitignore` 已忽略 `*.wav`(僅 `examples/rest-stop.wav` 例外),自己的錄音不會被提交。**請勿覆蓋 `rest-stop.wav`**,它是 BC 共用的範例檔。

> 以 WebSocket 測試 D(`UPDATE_FILTER`、`RESET_TASK`、`CONFIRM_DESTINATION`)時,訊息格式為 `{"task_id","version","type":"TOUCH_ACTION","payload":{"action":...}}`,連線位址 `ws://127.0.0.1:8000/ws`。測完建議送一次 `RESET_TASK` 還原狀態。
