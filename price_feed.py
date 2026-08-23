"""金价数据源：优先 MT5，其次金十，再回退 TradingView / XAUS 现货。"""
from __future__ import annotations

import os
import subprocess
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


def mt5_running() -> bool:
    if os.name != "nt":
        return False
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq terminal64.exe"],
            capture_output=True,
            text=True,
            timeout=2,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return False
    return "terminal64.exe" in result.stdout.lower()


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
        self._start_mt5()

    def _start_mt5(self) -> None:
        if not _HAS_MT5:
            return
        now = time.time()
        if now - self._last_try < MT5_RETRY:
            return
        self._last_try = now

        if not mt5_running():
            self.mt5_ok = False
            return

        try:
            info = mt5.terminal_info()
            if info is None:
                if not mt5.initialize():
                    return
        except Exception:
            if not mt5.initialize():
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

    def _stop_mt5(self) -> None:
        self.mt5_ok = False
        if _HAS_MT5:
            try:
                mt5.shutdown()
            except Exception:
                pass

    def fetch(self) -> Quote:
        if self.mt5_ok or _HAS_MT5:
            if not self.mt5_ok:
                self._start_mt5()
            if self.mt5_ok:
                try:
                    tick = mt5.symbol_info_tick(self.symbol)
                    if tick is not None and tick.bid > 0:
                        return Quote(price=float(tick.bid), source="MT5", symbol=self.symbol)
                except Exception:
                    pass
                self._stop_mt5()

        if self._jin10 is not None:
            try:
                price = self._jin10.get_price()
                return Quote(price=price, source="JIN10", symbol="XAUUSD")
            except Exception:
                self._jin10.reset()

        return self._fetch_web_cached()

    def _fetch_web_cached(self) -> Quote:
        """缓存 web 结果 2 秒，避免 0.25s 轮询打爆 API。"""
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
                r = requests.post(TV_SCAN_URL, json=body, headers=HEADERS, timeout=6)
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
        r = requests.get(XAUS_URL, headers=HEADERS, timeout=8)
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
