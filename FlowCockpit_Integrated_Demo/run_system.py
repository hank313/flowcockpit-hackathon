"""用一個指令啟動 FlowCockpit 的 BC、D、E 三個服務。"""

from __future__ import annotations

import argparse
import importlib.util
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def dependency_check(include_bc: bool, include_cloud: bool) -> list[str]:
    required = ["fastapi", "uvicorn", "httpx", "multipart"]
    if include_bc:
        required.extend(["faster_whisper", "opencc"])
    if include_cloud:
        required.extend(["anthropic", "dotenv"])
    return sorted({name for name in required if importlib.util.find_spec(name) is None})


def command(app_dir: str, app: str, host: str, port: int) -> list[str]:
    return [
        sys.executable, "-m", "uvicorn", app,
        "--app-dir", str(ROOT / app_dir),
        "--host", host, "--port", str(port),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="啟動 FlowCockpit 整合服務")
    parser.add_argument("--host", default="0.0.0.0", help="D 對 Android 監聽的位址")
    parser.add_argument("--skip-bc", action="store_true", help="BC 已在別處執行時使用")
    parser.add_argument("--no-cloud", action="store_true", help="只展示離線核心，不啟動 E")
    parser.add_argument("--check", action="store_true", help="只檢查依賴與必要資料")
    args = parser.parse_args()

    missing = dependency_check(not args.skip_bc, not args.no_cloud)
    map_db = ROOT / "bc" / "data" / "taiwan.sqlite3"
    if missing:
        print("缺少 Python 套件：" + ", ".join(missing))
        print(f"請執行：{sys.executable} -m pip install -r {ROOT / 'requirements.txt'}")
        return 2
    if not args.skip_bc and not map_db.exists():
        print(f"警告：找不到 {map_db}，BC 語音可用，但實際地點搜尋會回 places_unavailable。")
    if not args.no_cloud and not os.getenv("ANTHROPIC_API_KEY") and not (ROOT / ".env").exists():
        print("提示：未找到 ANTHROPIC_API_KEY，E 會以 local_only 安全降級。")
    if args.check:
        print("FlowCockpit 啟動前檢查完成。")
        return 0

    specs: list[tuple[str, list[str]]] = []
    if not args.skip_bc:
        specs.append(("BC", command("bc", "app:app", "127.0.0.1", 8001)))
    if not args.no_cloud:
        specs.append(("E", command("e", "server_e:app", "127.0.0.1", 8002)))
    specs.append(("D", command("d", "server_d:app", args.host, 8000)))

    processes: list[tuple[str, subprocess.Popen]] = []
    try:
        for name, args_list in specs:
            print(f"啟動 {name}: {' '.join(args_list)}")
            processes.append((name, subprocess.Popen(args_list, cwd=ROOT)))
        print("D Dashboard: http://127.0.0.1:8000")
        print("系統狀態: http://127.0.0.1:8000/api/system/status")
        while True:
            for name, process in processes:
                code = process.poll()
                if code is not None:
                    raise RuntimeError(f"{name} 已停止（exit {code}）")
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n正在停止 FlowCockpit...")
        return_code = 0
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return_code = 1
    else:
        return_code = 0
    finally:
        for _, process in processes:
            if process.poll() is None:
                process.terminate()
        for _, process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
