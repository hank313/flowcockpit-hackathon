import asyncio
import json
import websockets

async def test_touch():
    # 明確指定 127.0.0.1 避免 Windows 下 localhost 解析問題
    uri = "ws://127.0.0.1:8000/ws"
    
    try:
        async with websockets.connect(uri) as websocket:
            # 1. 接收連線後的初始化 UI
            init_msg = await websocket.recv()
            print("【1. 連線成功，收到初始 UI JSON】:")
            print(json.loads(init_msg))

            # 2. 模擬觸控選擇候選地點 2
            touch_event = {
                "task_id": "demo_task_001",
                "version": 1,
                "type": "TOUCH_ACTION",
                "payload": {
                    "action": "SELECT_CANDIDATE",
                    "candidate_id": 2
                }
            }
            print("\n【2. 送出模擬觸控事件 (選擇地點 2)...】")
            await websocket.send(json.dumps(touch_event))

            # 3. 接收後端處理完廣播回來的最新 UI JSON
            updated_msg = await websocket.recv()
            print("\n【3. 收到後端推播的更新 UI (selected_id 應為 2)】:")
            print(json.dumps(json.loads(updated_msg), indent=2, ensure_ascii=False))

    except Exception as e:
        print(f"連線失敗，請確認 server_d.py 是否已先行啟動！錯誤資訊: {e}")

if __name__ == "__main__":
    asyncio.run(test_touch())