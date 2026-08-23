"""XAU Widget Pro 入口。"""
from main import App, OneLock, LOCK_NAME

if __name__ == "__main__":
    try:
        OneLock(LOCK_NAME)
        App().wait()
    except SystemExit:
        raise
