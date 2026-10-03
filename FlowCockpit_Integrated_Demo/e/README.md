# E - 雲端增強服務

E 接收 D 提供的候選與條件，呼叫 Claude 產生一至兩句中文取捨分析。沒有 API Key、斷網或逾時時回傳 `local_only`，不阻塞 BC/D 的離線核心流程。

## 啟動

在專案根目錄建立 `.env`：

```env
ANTHROPIC_API_KEY=your_key_here
ANTHROPIC_MODEL=claude-haiku-4-5-20251001
```

建議直接由根目錄統一啟動：

```powershell
python run_system.py
```

單獨啟動 E：

```powershell
python -m uvicorn server_e:app --app-dir e --host 127.0.0.1 --port 8002
```

端點：

- `GET /health`：`ready` 或 `offline_only`
- `POST /api/compare`：輸入 `task_id`、`base_version`、`candidates`、`conditions`

D 會先推送本地 UI，再非同步呼叫 E；只有 `task_id` 與 `base_version` 仍是最新版本時才採用回覆。D 預設於 0、5、15 秒重試，恢復外網後可自動補上分析，也可呼叫 `POST /api/cloud/refresh` 手動觸發。
