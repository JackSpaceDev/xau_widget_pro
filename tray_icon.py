"""系统托盘图标：在任务栏通知区显示实时金价。"""
from __future__ import annotations

import threading
from typing import Callable, Optional

import pystray
from PIL import Image, ImageDraw, ImageFont


GOLD = "#FFD700"


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("segoeui.ttf", "arialbd.ttf", "arial.ttf", "msyh.ttc"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make_icon(price_text: str, color: str = "#FFD700") -> Image.Image:
    img = Image.new("RGBA", (72, 36), (20, 20, 20, 255))
    draw = ImageDraw.Draw(img)
    font = load_font(13)
    draw.text((4, 8), price_text, fill=color, font=font)
    return img


class Tray:
    def __init__(
        self,
        on_show: Optional[Callable[[], None]] = None,
        on_hide: Optional[Callable[[], None]] = None,
        on_quit: Optional[Callable[[], None]] = None,
    ) -> None:
        self._on_show = on_show
        self._on_hide = on_hide
        self._on_quit = on_quit
        self.icon: pystray.Icon | None = None
        self._thread: Optional[threading.Thread] = None

    def _menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem("显示价格", self._call_show, default=True),
            pystray.MenuItem("隐藏价格", self._call_hide),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", self._call_quit),
        )

    def _call_show(self, _icon=None, _item=None) -> None:
        if self._on_show:
            self._on_show()

    def _call_hide(self, _icon=None, _item=None) -> None:
        if self._on_hide:
            self._on_hide()

    def _call_quit(self, _icon=None, _item=None) -> None:
        if self._on_quit:
            self._on_quit()

    def start(self) -> None:
        self.icon = pystray.Icon(
            "xau_widget_pro",
            make_icon("----"),
            "XAUUSD 金价",
            menu=self._menu(),
        )
        self._thread = threading.Thread(target=self.icon.run, daemon=True)
        self._thread.start()

    def update(self, price_text: str, color: str = "#FFD700") -> None:
        if self.icon is None:
            return
        self.icon.icon = make_icon(price_text, color)
        self.icon.title = f"XAUUSD  {price_text}"

    def stop(self) -> None:
        if self.icon is not None:
            self.icon.stop()


# 兼容旧名
TrayController = Tray
make_price_icon = make_icon
