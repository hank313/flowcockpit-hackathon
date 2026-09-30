"""
E 模組:task_id / version 比對邏輯
對應 WebSocket 訊息格式裡的 {"task_id": ..., "version": ...} 欄位。
任何收到的訊息(尤其是斷網後恢復連網時的延遲雲端回覆),
在真正套用/顯示前都要先問過這個 Guard,過期的訊息直接丟棄,
避免覆蓋掉使用者最新的操作結果。
"""


class TaskVersionGuard:
    def __init__(self):
        self._current_task_id: str | None = None
        self._current_version: int = -1

    def is_fresh(self, task_id: str, version: int) -> bool:
        """只檢查,不更新狀態。用於 E 收到雲端回覆時,判斷這個回覆是否還對應目前任務。"""
        if task_id != self._current_task_id:
            return True  # 不同task_id代表是全新任務,直接採用
        return version >= self._current_version

    def update(self, task_id: str, version: int) -> None:
        """任務狀態(通常由 D)有新變動時呼叫,更新目前追蹤的最新版本。"""
        self._current_task_id = task_id
        self._current_version = version

    def accept_if_fresh(self, task_id: str, version: int) -> bool:
        """檢查並在通過時順便更新狀態。回傳 True 代表這則訊息夠新、應該處理。"""
        if self.is_fresh(task_id, version):
            self.update(task_id, version)
            return True
        return False


if __name__ == "__main__":
    guard = TaskVersionGuard()

    # 模擬情境:D 建立新任務,version從0開始
    print(guard.accept_if_fresh("task_20261001_0001", 0))   # True,新任務,採用

    # 使用者操作,D把version推進到3
    print(guard.accept_if_fresh("task_20261001_0001", 3))   # True,版本較新,採用

    # 斷網期間送出的雲端請求,回來時已經是version=1(比目前的3還舊)
    print(guard.accept_if_fresh("task_20261001_0001", 1))   # False,過期,丟棄

    # 使用者開了全新的任務
    print(guard.accept_if_fresh("task_20261002_0007", 0))   # True,不同task_id視為新任務
