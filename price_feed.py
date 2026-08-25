"""金价数据源：优先 MT5，其次金十，再回退 TradingView / XAUS 现货。"""
from __future__ import annotations

import ctypes
import os
import time
from dataclasses import dataclass

import requests

from jin10_client import Jin10, load_token

try:
    import MetaTrader5 as mt5

    _HAS_MT5 = True
except Exception:
    mt5 = None
    _HAS_MT5 = False

SYMBOLS = ("XAUUSDm", "XAUUSD", "XAUUSD.", "GOLD", "GOLDm")

# TradingView Scanner — 与 MT5 差距 <$0.2
TV_SCAN_URL = "https://scanner.tradingview.com/cfd/scan"
TV_TICKERS = ("FX_IDC:XAUUSD", "TVC:GOLD", "OANDA:XAUUSD", "FOREXCOM:XAUUSD")

# XAUS.com — 免费现货兜底
XAUS_URL = "https://xaus.com/api/v1/spot"

HEADERS = {"User-Agent": "Mozilla/5.0 (XAUWidgetPro)"}
MT5_RETRY = 5.0
WEB_CACHE_SEC = 2.0
PROC_CACHE_SEC = 1.0
WEB_TIMEOUT = 2.5
TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE = 0xFFFFFFFF


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", ctypes.c_ulong),
        ("cntUsage", ctypes.c_ulong),
        ("th32ProcessID", ctypes.c_ulong),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", ctypes.c_ulong),
        ("cntThreads", ctypes.c_ulong),
        ("th32ParentProcessID", ctypes.c_ulong),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", ctypes.c_ulong),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


_proc_ok = False
_proc_at = 0.0


def _scan_terminal() -> bool:
    if os.name != "nt":
        return False
    kernel32 = ctypes.windll.kernel32
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap in (0, INVALID_HANDLE):
        return False
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        if not kernel32.Process32FirstW(snap, ctypes.byref(entry)):
            return False
        while True:
            if entry.szExeFile.lower() == "terminal64.exe":
                return True
            if not kernel32.Process32NextW(snap, ctypes.byref(entry)):
                return False
    finally:
        kernel32.CloseHandle(snap)


def mark_mt5_gone() -> None:
    global _proc_ok, _proc_at
    _proc_ok = False
    _proc_at = time.time()


def mt5_running(force: bool = False) -> bool:
    """本机是否有 MT5 终端进程。关终端后必须马上返回 False，避免卡在 MT5 API。"""
    global _proc_ok, _proc_at
    now = time.time()
    if not force and now - _proc_at < PROC_CACHE_SEC:
        return _proc_ok
    _proc_ok = _scan_terminal()
    _proc_at = now
    return _proc_ok


@dataclass(frozen=True)
class Quote:
    price: float
    source: str
    symbol: str


class Feed:
    def __init__(self) -> None:
        self.mt5_ok = False
        self.symbol = "XAUUSD"
        self._last_try = 0.0
        self._jin10: Jin10 | None = None
        token = load_token()
        if token:
            self._jin10 = Jin10(token)
        self._web_cache: Quote | None = None
        self._web_cache_at = 0.0
        self._last_quote: Quote | None = None

    def _start_mt5(self) -> None:
        if not _HAS_MT5:
            return
        now = time.time()
        if now - self._last_try < MT5_RETRY:
            return
        self._last_try = now

        if not mt5_running(force=True):
            self.mt5_ok = False
            return

        try:
            info = mt5.terminal_info()
            if info is None:
                if not mt5.initialize():
                    self.mt5_ok = False
                    return
        except Exception:
            try:
                if not mt5.initialize():
                    self.mt5_ok = False
                    return
            except Exception:
                self.mt5_ok = False
                return

        for name in SYMBOLS:
            info = mt5.symbol_info(name)
            if info is None:
                continue
            if not info.visible:
                mt5.symbol_select(name, True)
            self.symbol = name
            self.mt5_ok = True
            return
        self.mt5_ok = False

    def _drop_mt5(self) -> None:
        """终端已关时只清标记，不调用 shutdown（会死等）。"""
        self.mt5_ok = False
        mark_mt5_gone()

    def _stop_mt5(self) -> None:
        self.mt5_ok = False
        if not _HAS_MT5:
            return
        if not mt5_running():
            return
        try:
            mt5.shutdown()
        except Exception:
            pass

    def _fetch_mt5(self) -> Quote | None:
        if not _HAS_MT5:
            return None
        if not mt5_running():
            self._drop_mt5()
            return None
        if not self.mt5_ok:
            self._start_mt5()
        if not self.mt5_ok:
            return None
        try:
            tick = mt5.symbol_info_tick(self.symbol)
            if tick is not None and tick.bid > 0:
                return Quote(price=float(tick.bid), source="MT5", symbol=self.symbol)
        except Exception:
            pass
        self._drop_mt5()
        return None

    def fetch(self) -> Quote:
        quote = self._fetch_mt5()
        if quote is not None:
            self._last_quote = quote
            return quote

        if self._jin10 is not None:
            try:
                price = self._jin10.get_price()
                quote = Quote(price=price, source="JIN10", symbol="XAUUSD")
                self._last_quote = quote
                return quote
            except Exception:
                self._jin10.reset()

        try:
            quote = self._fetch_web_cached()
            self._last_quote = quote
            return quote
        except Exception:
            if self._last_quote is not None:
                return self._last_quote
            raise

    def _fetch_web_cached(self) -> Quote:
        """缓存 web 结果 2 秒，避免 0.25s 轮询超限。"""
        now = time.time()
        if self._web_cache and (now - self._web_cache_at) < WEB_CACHE_SEC:
            return self._web_cache
        quote = self._fetch_web()
        self._web_cache = quote
        self._web_cache_at = now
        return quote

    def _get_tv(self) -> float:
        """TradingView Scanner — close 字段与 MT5 Bid 差距 <$0.2。"""
        for ticker in TV_TICKERS:
            try:
                body = {
                    "symbols": {"tickers": [ticker]},
                    "columns": ["close"],
                }
                r = requests.post(TV_SCAN_URL, json=body, headers=HEADERS, timeout=WEB_TIMEOUT)
                r.raise_for_status()
                rows = r.json().get("data", [])
                if rows:
                    price = float(rows[0]["d"][0])
                    if price > 0:
                        return price
            except Exception:
                continue
        raise RuntimeError("TradingView all tickers failed")

    def _get_xaus(self) -> float:
        """XAUS.com 现货兜底。"""
        r = requests.get(XAUS_URL, headers=HEADERS, timeout=WEB_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        price = float(data.get("spot_usd_oz") or data["xau"]["price"])
        if price <= 0:
            raise ValueError("XAUS price invalid")
        return price

    def _fetch_web(self) -> Quote:
        for fn, src in [
            (self._get_tv, "TV"),
            (self._get_xaus, "SPOT"),
        ]:
            try:
                return Quote(price=fn(), source=src, symbol="XAUUSD")
            except Exception:
                continue
        raise RuntimeError("所有数据源均不可用")

    def stop(self) -> None:
        self._stop_mt5()


# 兼容旧名
PriceFeed = Feed
mt5_process_running = mt5_running
