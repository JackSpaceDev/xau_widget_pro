# xau_widget_pro · 任务栏直显实时金价

在 Windows **任务栏区域直接显示** XAUUSD 实时价格（两位小数）。价格条无底色、黑色数字；托盘图标作为备用入口。

## 怎么看

1. 看**天气/小组件**和**开始键**之间的空档（开始与搜索几乎贴在一起，放不下）
2. 会看到黑色价格数字，例如 **`4061.04`**（无背景框）
3. 按住数字可拖动
4. 双击数字会重新贴回该空档
5. 托盘图标可作为备用入口，右键可显示、隐藏或退出

## 快速开始

双击 `启动.bat`

## 开机自启

双击 `install_autostart.bat`，或程序启动时会自动写入登录启动项。

## 数据源（优先级）

1. **MT5 Bid** — 实时，`XAUUSDm` / `XAUUSD`
2. **金十 MCP** — 需配置 `JIN10_API_TOKEN`（可选）
3. **TradingView** — Scanner API `FX_IDC:XAUUSD`，与 MT5 差距 <$0.2
4. **XAUS.com** — 免费现货兜底，与 MT5 差距 ~$3

MT5 开启时用 MT5；关闭后自动回退到 TradingView，误差 <0.01%。  
Web API 结果缓存 2 秒，避免高频轮询超限。

## 文件

```text
xau_widget_pro/
├─ main.py          # 任务栏直显主程序（App / Feed / Tray）
├─ tray_icon.py     # 托盘备用入口
├─ price_feed.py    # MT5 / API 数据源
├─ jin10_client.py  # 金十报价（可选）
├─ run.py           # 入口（同 main）
├─ 启动.bat
└─ install_autostart.bat
```

命名约定：短词为主（`App` / `Feed` / `Tray` / `Cfg` / `show_price` / `clamp_pos`）。
