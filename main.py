"""XAU Widget Pro — 任务栏直显实时金价（稳定版）。"""
from __future__ import annotations

import atexit
import ctypes
import json
import os
import sys
import threading
import tkinter as tk
import time
from dataclasses import dataclass
from pathlib import Path

from price_feed import Feed
from tray_icon import Tray

APP_NAME = "XAU Widget Pro"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
POLL = 0.25
LOCK_NAME = "Global\\XAUWidgetPro_SingleInstance"
BASE_W = 108
BASE_H = 34
HWND_TOP = -1
SWP_SHOW = 0x0040
GA_ROOT = 2


def enable_dpi() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def ui_scale() -> float:
    if os.name != "nt":
        return 1.0
    try:
        hdc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)
        ctypes.windll.user32.ReleaseDC(0, hdc)
        return max(1.0, float(dpi) / 96.0)
    except Exception:
        return 1.0


enable_dpi()
SCALE = ui_scale()
WIN_W = max(BASE_W, int(round(BASE_W * SCALE)))
WIN_H = max(BASE_H, int(round(BASE_H * SCALE)))
BG = "#FEFEFE"
TEXT = "#000000"
TRAY_COLOR = "#FFD700"


def _log(message: str) -> None:
    log_dir = Path(os.getenv("APPDATA", str(Path.home()))) / "XAUWidgetPro"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "runtime.log"
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(f"[{stamp}] {message}\n")


class OneLock:
    def __init__(self, name: str) -> None:
        self._handle = None
        if os.name != "nt":
            return
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, False, name)
        if not handle:
            raise RuntimeError("无法创建单实例锁")
        if kernel32.GetLastError() == 183:
            kernel32.CloseHandle(handle)
            raise SystemExit(0)
        self._handle = handle
        atexit.register(self.release)

    def release(self) -> None:
        if self._handle is None or os.name != "nt":
            return
        ctypes.windll.kernel32.CloseHandle(self._handle)
        self._handle = None


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def work_area() -> tuple[int, int, int, int]:
    if os.name != "nt":
        return (0, 0, 1920, 1040)
    rect = RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
    return rect.left, rect.top, rect.right, rect.bottom


def screen_box() -> tuple[int, int, int, int]:
    if os.name != "nt":
        return (0, 0, 1920, 1080)
    user32 = ctypes.windll.user32
    width = user32.GetSystemMetrics(0)
    height = user32.GetSystemMetrics(1)
    return 0, 0, width, height


def taskbar_rect() -> tuple[int, int, int, int]:
    """主任务栏屏幕矩形。找不到时用工作区与屏幕差兜底。"""
    if os.name == "nt":
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW("Shell_TrayWnd", None)
        rect = RECT()
        if hwnd and user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            if rect.right > rect.left and rect.bottom > rect.top:
                return rect.left, rect.top, rect.right, rect.bottom
    sl, _st, sr, sb = screen_box()
    _wl, _wt, _wr, work_bottom = work_area()
    if sb - work_bottom >= 8:
        return sl, work_bottom, sr, sb
    return sl, max(0, sb - 48), sr, sb


def center_in_bar(
    bar: tuple[int, int, int, int],
    win_w: int = WIN_W,
    win_h: int = WIN_H,
) -> tuple[int, int]:
    """把窗口放进任务栏内部并垂直居中；横条靠左，竖条靠下。"""
    left, top, right, bottom = bar
    bar_w = max(1, right - left)
    bar_h = max(1, bottom - top)
    if bar_w >= bar_h:
        return left + 8, top + max(0, (bar_h - win_h) // 2)
    return left + max(0, (bar_w - win_w) // 2), bottom - win_h - 8


def default_pos() -> tuple[int, int]:
    """默认贴在主屏任务栏内部并垂直居中。"""
    return center_in_bar(taskbar_rect())


def in_taskbar_y(
    y: int,
    bar: tuple[int, int, int, int] | None = None,
    win_h: int = WIN_H,
) -> bool:
    _left, top, _right, bottom = bar or taskbar_rect()
    mid = y + win_h // 2
    return top <= mid <= bottom


def clamp_pos(x: int, y: int) -> tuple[int, int]:
    """允许拖到主屏任意位置，包括任务栏区域。"""
    sl, st, sr, sb = screen_box()
    min_x = sl + 4
    max_x = sr - WIN_W - 4
    min_y = st + 4
    max_y = sb - WIN_H - 4
    return min(max(x, min_x), max_x), min(max(y, min_y), max_y)


def show_price(value: float) -> str:
    return f"{round(value, 2):.2f}"


@dataclass
class Cfg:
    x: int | None = None
    y: int | None = None
    autostart: bool = True


class CfgStore:
    def __init__(self) -> None:
        self.base_dir = Path(os.getenv("APPDATA", str(Path.home()))) / "XAUWidgetPro"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.base_dir / "config.json"

    def load(self) -> Cfg:
        if not self.path.exists():
            return Cfg()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            cfg = Cfg(
                x=data.get("x"),
                y=data.get("y"),
                autostart=bool(data.get("autostart", True)),
            )
        except Exception:
            return Cfg()
        dx, dy = default_pos()
        x = dx if cfg.x is None else int(cfg.x)
        cfg.x, cfg.y = clamp_pos(x, dy)
        return cfg

    def save(self, config: Cfg) -> None:
        old: dict = {}
        if self.path.exists():
            try:
                old = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                old = {}
        old.update({"x": config.x, "y": config.y, "autostart": config.autostart})
        self.path.write_text(json.dumps(old, ensure_ascii=False, indent=2), encoding="utf-8")


def find_pythonw() -> str:
    for raw in (os.getenv("XAU_PYTHONW", ""), r"D:\Python\pythonw.exe"):
        if not raw:
            continue
        candidate = Path(raw)
        if candidate.is_file():
            return str(candidate)
    pyw = Path(sys.executable).with_name("pythonw.exe")
    return str(pyw if pyw.is_file() else sys.executable)


def set_auto(enable: bool, script_path: str) -> None:
    import winreg

    command = f'"{find_pythonw()}" "{script_path}"'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_ALL_ACCESS) as key:
        if enable:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass


class App:
    def __init__(self) -> None:
        self.store = CfgStore()
        self.config = self.store.load()
        self.config.autostart = True
        if self.config.x is None or self.config.y is None:
            self.config.x, self.config.y = default_pos()
        self.store.save(self.config)

        self.running = True
        self.drag_start: tuple[int, int] | None = None

        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=BG, highlightthickness=0)
        try:
            self.root.attributes("-transparentcolor", BG)
        except tk.TclError:
            pass

        self.price_label = tk.Label(
            self.root,
            text="----",
            fg=TEXT,
            bg=BG,
            font=("Microsoft YaHei UI Light", 16, "normal"),
            padx=2,
            pady=0,
            borderwidth=0,
            highlightthickness=0,
        )
        self.price_label.place(relx=0.5, rely=0.5, anchor="center")

        for widget in (self.root, self.price_label):
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._drag)
            widget.bind("<ButtonRelease-1>", self._end_drag)
            widget.bind("<Double-Button-1>", lambda _event: self.snap_home())

        self.tray = Tray(
            on_show=lambda: self.root.after(0, self.show),
            on_hide=lambda: self.root.after(0, self.hide),
            on_quit=lambda: self.root.after(0, self.quit),
        )
        self.tray.start()
        set_auto(True, str(Path(__file__).resolve()))

        self.feed = Feed()
        self._quote_lock = threading.Lock()
        self._quote_text = "----"
        self._quote_err = ""
        self._feed_thread = threading.Thread(target=self._fetch_loop, daemon=True)
        self._feed_thread.start()
        self.set_pos()
        self.show()
        self.root.update_idletasks()
        _log(
            f"started hwnd={self.root.winfo_id()} pos=({self.root.winfo_x()},{self.root.winfo_y()}) "
            f"taskbar={taskbar_rect()} scale={SCALE:.2f} size={WIN_W}x{WIN_H}"
        )
        self.root.after(100, self._poll)
        self.root.after(500, self._keep_pos)
        self.root.after(2000, self._keep_pos)

    def set_pos(self) -> None:
        x, y = clamp_pos(int(self.config.x or 0), int(self.config.y or 0))
        self.config.x, self.config.y = x, y
        self.root.geometry(f"{WIN_W}x{WIN_H}+{x}+{y}")

    def _top(self) -> None:
        self._top_at(int(self.config.x or 0), int(self.config.y or 0))

    def _start_drag(self, event: tk.Event) -> None:
        self.drag_start = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def _drag(self, event: tk.Event) -> None:
        if self.drag_start is None:
            return
        dx, dy = self.drag_start
        nx, ny = clamp_pos(event.x_root - dx, event.y_root - dy)
        self.root.geometry(f"+{nx}+{ny}")
        self._top_at(nx, ny)

    def _top_at(self, x: int, y: int) -> None:
        if os.name != "nt":
            return
        raw = int(self.root.winfo_id())
        hwnd = ctypes.windll.user32.GetAncestor(raw, GA_ROOT) or raw
        ctypes.windll.user32.SetWindowPos(
            hwnd,
            HWND_TOP,
            x,
            y,
            WIN_W,
            WIN_H,
            SWP_SHOW,
        )

    def _end_drag(self, _event: tk.Event) -> None:
        self.config.x = self.root.winfo_x()
        self.config.y = self.root.winfo_y()
        self.store.save(self.config)
        self.drag_start = None

    def snap_home(self) -> None:
        self.config.x, self.config.y = default_pos()
        self.store.save(self.config)
        self.set_pos()
        self.show()

    def _keep_pos(self) -> None:
        x = int(self.root.winfo_x())
        y = int(self.root.winfo_y())
        target_x, target_y = clamp_pos(x, y)
        if (x, y) != (target_x, target_y):
            self.config.x, self.config.y = target_x, target_y
            self.store.save(self.config)
            self.set_pos()
        self.show()
        if self.running:
            self.root.after(5000, self._keep_pos)

    def show(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self._top()

    def hide(self) -> None:
        self.root.withdraw()

    def _fetch_loop(self) -> None:
        """后台取价：MT5 关掉后网页请求不能卡住任务栏窗口。"""
        while self.running:
            wait = POLL
            try:
                quote = self.feed.fetch()
                text = show_price(quote.price)
                with self._quote_lock:
                    self._quote_text = text
                    self._quote_err = ""
                if quote.source != "MT5":
                    wait = 1.0
            except Exception as exc:
                with self._quote_lock:
                    self._quote_err = repr(exc)
                _log(f"poll_error {exc!r}")
                wait = 1.0
            time.sleep(wait)

    def _poll(self) -> None:
        if not self.running:
            return
        with self._quote_lock:
            text = self._quote_text
            err = self._quote_err
        if err and text == "----":
            self.price_label.configure(text="----", fg=TEXT)
            self.tray.update("----", TRAY_COLOR)
        else:
            self.price_label.configure(text=text, fg=TEXT)
            self.tray.update(text, TRAY_COLOR)
        self.root.after(int(POLL * 1000), self._poll)

    def quit(self) -> None:
        self.running = False
        self.feed.stop()
        self.tray.stop()
        os._exit(0)

    def wait(self) -> None:
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.quit()


# 兼容旧名
XauWidgetApp = App
SingleInstance = OneLock
ConfigStore = CfgStore
set_autostart = set_auto


if __name__ == "__main__":
    try:
        OneLock(LOCK_NAME)
        App().wait()
    except SystemExit:
        # 已有实例在跑：弹提示，避免用户以为没启动
        try:
            ctypes.windll.user32.MessageBoxW(
                0,
                "XAU Widget Pro 已在运行。\n请看任务栏金色价格条，或托盘图标。",
                APP_NAME,
                0x40,
            )
        except Exception:
            pass
        raise
    except Exception as exc:
        _log(f"startup_error {exc!r}")
        try:
            err = Path(__file__).resolve().parent / "error.log"
            err.write_text(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {exc!r}\n", encoding="utf-8")
            ctypes.windll.user32.MessageBoxW(0, f"启动失败：{exc}", APP_NAME, 0x10)
        except Exception:
            pass
        raise
