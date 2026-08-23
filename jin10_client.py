"""金十数据 MCP 客户端：获取 XAUUSD 等品种报价。"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests

MCP_URL = "https://mcp.jin10.com/mcp"
PROTOCOL_VERSION = "2025-11-25"
TOKEN_KEYS = ("JIN10_API_TOKEN", "JIN10_BEARER_TOKEN")


def load_token() -> str:
    for key in TOKEN_KEYS:
        value = os.getenv(key, "").strip()
        if value:
            return value
    config_path = Path(os.getenv("APPDATA", str(Path.home()))) / "XAUWidgetPro" / "config.json"
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            return str(data.get("jin10_token", "")).strip()
        except Exception:
            return ""
    return ""


def parse_sse(text: str) -> dict[str, Any]:
    data_lines: list[str] = []
    for line in text.splitlines():
        if line == "":
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    if not data_lines:
        raise RuntimeError("金十 MCP 响应为空")
    payload = json.loads("\n".join(data_lines))
    if "error" in payload:
        err = payload["error"]
        raise RuntimeError(f"金十 MCP 错误 {err.get('code')}: {err.get('message')}")
    return payload


def pick_data(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("isError"):
        raise RuntimeError(f"金十工具错误: {result}")
    if isinstance(result.get("structuredContent"), dict):
        return result["structuredContent"]
    for item in result.get("content") or []:
        if item.get("type") == "text" and item.get("text"):
            try:
                parsed = json.loads(item["text"])
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue
    if isinstance(result, dict):
        return result
    raise RuntimeError("无法解析金十报价数据")


class Jin10:
    def __init__(self, token: str) -> None:
        self.token = token.strip()
        self.session_id: str | None = None
        self.req_id = 0
        self.ok = False

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        return headers

    def _next_id(self) -> int:
        self.req_id += 1
        return self.req_id

    def _post(self, body: dict[str, Any], *, want_resp: bool = True) -> dict[str, Any] | None:
        response = requests.post(MCP_URL, headers=self._headers(), json=body, timeout=15)
        session_id = response.headers.get("mcp-session-id")
        if session_id:
            self.session_id = session_id
        if not want_resp:
            if response.status_code not in (200, 202):
                raise RuntimeError(f"金十 MCP 请求失败: HTTP {response.status_code}")
            return None
        if not response.ok:
            raise RuntimeError(f"金十 MCP 请求失败: HTTP {response.status_code} {response.text[:200]}")
        payload = parse_sse(response.text)
        return payload.get("result")

    def connect(self) -> None:
        self._post(
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "xau_widget_pro", "version": "1.0.0"},
                },
            }
        )
        self._post(
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            },
            want_resp=False,
        )
        self.ok = True

    def get_price(self) -> float:
        if not self.token:
            raise RuntimeError("未配置金十 Token")
        if not self.ok:
            self.connect()
        result = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "tools/call",
                "params": {"name": "get_quote", "arguments": {"code": "XAUUSD"}},
            }
        )
        data = pick_data(result or {})
        price = data.get("close", data.get("price"))
        if price is None:
            raise RuntimeError(f"金十报价字段缺失: {data}")
        value = float(price)
        if value <= 0:
            raise ValueError("金十报价无效")
        return value

    def reset(self) -> None:
        self.session_id = None
        self.ok = False


# 兼容旧名
Jin10Client = Jin10
load_jin10_token = load_token
