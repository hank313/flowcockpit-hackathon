# FlowCockpit 整合展示系統

這個資料夾是 FlowCockpit 的完整整合版本，包含：

- `A1/`：Android 平板 App。
- `bc/`：離線語音辨識、意圖解析與臺灣 OSM 地點搜尋。
- `d/`：系統調度、狀態管理、條件篩選及平板 UI 資料。
- `e/`：可選的 Claude 雲端 AI 取捨分析。
- `run_system.py`：一次啟動 BC、D、E。

## 重要：不要把 API Key 上傳 Git

`.env` 已被 `.gitignore` 排除，請勿使用 `git add -f .env`。即使 API Key 只有少量額度、日後會更換，公開後仍可能被機器人立即取得、消耗額度或造成帳號風險；而且刪除檔案不會自動清除 Git 歷史。

Repository 只提供 `.env.example`。每位使用者需自行複製成 `.env` 並填入自己的金鑰：

```powershell
Copy-Item .env.example .env
notepad .env
```

內容格式：

```dotenv
ANTHROPIC_API_KEY=your_key_here
```

沒有 Claude Key 也能執行離線核心功能，只是不會顯示「雲端 AI 取捨分析」。

## 快速下載 Android APK

[從 Google Drive 下載 FlowCockpit APK](https://drive.google.com/file/d/14pqAOPNbt7nutAwvTxjBMPxafR1DOyde/view?usp=sharing)

請確認 Google Drive 權限設定為「知道連結的任何人皆可檢視」。下載到 Android 平板後開啟 APK；若系統阻擋，依提示允許該檔案管理器或瀏覽器「安裝未知應用程式」。更新舊版時選擇「更新」。

目前 App 最低支援 Android 14（API 34）。

## Windows 電腦第一次安裝

### 1. 必要軟體

- Windows 10/11 64 位元。
- Python 3.11 或 3.12 64 位元。
- [Ollama](https://ollama.com/download/windows)。
- Android Studio 只有需要自行編譯 APK 時才必須安裝；使用上方 APK 不需要開 Android Studio。

### 2. 建立 Python 環境

在本資料夾開啟 PowerShell：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 3. 安裝本機意圖模型

安裝並啟動 Ollama 後執行：

```powershell
ollama pull llama3.2:1b
ollama list
```

若 Ollama 沒有自動在背景執行，可另外開一個 PowerShell：

```powershell
ollama serve
```

### 4. 建立離線臺灣地點資料庫

地圖資料約數百 MB，不放進 Git。第一次安裝需下載並建立資料庫：

```powershell
.\.venv\Scripts\python.exe -m pip install -r bc\requirements-data.txt
New-Item -ItemType Directory -Force bc\data
Invoke-WebRequest https://download.geofabrik.de/asia/taiwan-latest.osm.pbf -OutFile bc\data\taiwan.osm.pbf
.\.venv\Scripts\python.exe bc\build_places.py bc\data\taiwan.osm.pbf --source-url https://download.geofabrik.de/asia/taiwan-latest.osm.pbf
```

完成後應存在：

```text
bc\data\taiwan.sqlite3
```

### 5. 設定 Claude（選用）

```powershell
Copy-Item .env.example .env
notepad .env
```

將自己的 `ANTHROPIC_API_KEY` 填入 `.env`。不要把 `.env` 傳給別人或提交至 Git。

### 6. 啟動前檢查

```powershell
.\.venv\Scripts\python.exe run_system.py --check
```

## 每次展示：電腦端流程

### 1. 建立區域網路

讓筆電和平板連上同一台手機熱點或同一個 Wi-Fi。手機熱點重新啟動後，筆電 IP 可能改變。

### 2. 啟動系統

```powershell
cd D:\flowcockpit-hackathon-main\FlowCockpit_Integrated_Demo
.\.venv\Scripts\python.exe run_system.py
```

請保持這個 PowerShell 開啟，並關閉筆電睡眠。Android Studio與瀏覽器都不必開啟。

成功時會看到 BC、D、E 的 `Application startup complete`。若出現錯誤 `10048`，代表系統已經在執行，請勿重複啟動。可以用以下指令確認：

```powershell
Get-NetTCPConnection -LocalPort 8000,8001,8002 -State Listen
```

### 3. 確認後端狀態

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/system/status
```

有網路且 Claude 設定完成時，預期類似：

```json
{"d":true,"bc":true,"cloud":true,"mode":"hybrid"}
```

### 4. 查詢筆電 IP

```powershell
ipconfig
```

找到目前連線中「Wi-Fi」介面卡的 `IPv4 位址`，例如：

```text
192.168.0.190
```

不要使用 VMware、Tailscale、`169.254.x.x` 或已中斷介面卡的位址。

## 每次展示：Android 平板流程

1. 安裝並開啟 FlowCockpit APK。
2. 平板與筆電連到同一個手機熱點／Wi-Fi。
3. 點 App 右下角「連線設定」。
4. 輸入筆電的 `IPv4:8000`，例如：

   ```text
   192.168.0.190:8000
   ```

5. 按「儲存並連線」。
6. 第一次錄音時允許麥克風權限。
7. 按住麥克風至少 1 秒，說完後再放開。

Windows 第一次收到連線時若跳出防火牆詢問，請允許 Python 使用「私人網路」。

## 驗證平板是否連上筆電

在筆電執行：

```powershell
Get-NetTCPConnection -LocalPort 8000 |
Select-Object RemoteAddress, RemotePort, State
```

若看到平板 IP 且狀態為 `Established`，代表 App 的 WebSocket 已連線，例如：

```text
RemoteAddress  RemotePort  State
192.168.0.242  56796       Established
0.0.0.0        0           Listen
```

送出語音後，App 應依序出現：

1. 「語音已送出，正在辨識」。
2. 「你剛剛說」及實際辨識文字。
3. 候選地點與篩選條件。
4. 有網路時顯示「雲端 AI 取捨分析」。

## 建議測試提示詞

成功率較高的基本查詢：

- 「找附近的咖啡店」
- 「找附近有座位的咖啡店」
- 「找附近的餐廳」
- 「找附近的便利商店」
- 「找附近的公園」
- 「找附近的廁所」
- 「找附近的加油站」
- 「找附近的醫院」
- 「找附近的景點」
- 「找附近的住宿」
- 「找附近的停車場」
- 「找一個可以休息的地方」

包含條件的查詢：

- 「找十公里內的咖啡店」
- 「找室內有座位的餐廳」
- 「找有餐飲的休息地點」
- 「找不用開太遠的便利商店」

建議 Demo 依序測試：

1. 「找附近的咖啡店」
2. 「找附近的公園」
3. 「找附近的加油站」

## 離線展示流程

離線是「沒有網際網路」，不是切斷平板與筆電的區域網路：

1. 保持手機熱點開啟，筆電和平板都不要斷線。
2. 關閉手機的行動數據。
3. 再說一個全新的提示詞，例如「找附近十公里內的加油站」。
4. 本機語音辨識、意圖解析、OSM 地點搜尋及篩選仍可使用。
5. 離線時不會出現「雲端 AI 取捨分析」，App 會說明雲端 AI 暫時沒有回覆。
6. 恢復行動數據後，下一次查詢會自動恢復 Claude 分析，不必重啟 App。

若要確認筆電真的無法連到 Claude：

```powershell
Test-NetConnection api.anthropic.com -Port 443
```

`TcpTestSucceeded : False` 表示目前無法使用 Claude 網路服務。

## 常見問題

### App 完全沒有反應

- 確認 `run_system.py` 還在執行。
- 確認平板與筆電在同一個區域網路。
- 重新執行 `ipconfig`；手機熱點重開後 IP 可能改變。
- 在 App「連線設定」更新成最新的 `IPv4:8000`。
- 按住麥克風至少 1 秒。

新版 App 會直接顯示錄音過短、上傳失敗與處理逾時等錯誤，不再靜默卡住。

### 出現 `Errno 10048`

代表 8000／8001／8002 已被另一套 FlowCockpit 使用。若 `/api/system/status` 正常，就直接使用既有服務，不要再次執行 `run_system.py`。

### 能找到地點但沒有 AI 分析

- 離線狀態下是正常行為。
- 確認 `.env` 有自己的 `ANTHROPIC_API_KEY`。
- 確認 API 帳戶仍有額度且筆電可連網。

### 如何停止系統

回到執行 `run_system.py` 的 PowerShell，按 `Ctrl+C`。

## 自行編譯 APK（選用）

用 Android Studio 開啟 `A1` 資料夾，等待 Gradle Sync 完成，再選擇：

```text
Build > Build APK(s)
```

輸出位置：

```text
A1\app\build\outputs\apk\debug\app-debug.apk
```

也可以在 PowerShell 使用 Android Studio 內建的 Java：

```powershell
cd A1
$env:JAVA_HOME='D:\Android\Android Studio\jbr'
.\gradlew.bat assembleDebug
```

如果 Android Studio 安裝在其他位置，請將 `JAVA_HOME` 改成該安裝目錄內的 `jbr`。

## 授權與資料來源

地點資料來自 OpenStreetMap／Geofabrik。詳細資料授權與來源請參考 `bc/README.md` 及建置後的 `bc/data/ATTRIBUTION.md`。
