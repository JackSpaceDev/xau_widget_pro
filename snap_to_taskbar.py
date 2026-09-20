"""Reset XAU widget position onto the taskbar and restart."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from main import default_pos  # noqa: E402


def stop_old() -> None:
    try:
        import psutil  # type: ignore
    except ImportError:
        psutil = None
    if psutil is None:
        # fallback: wmic-like via powershell simple filter
        cmd = (
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.CommandLine -match 'xau_widget_pro\\\\(main|run)\\.py' } | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            check=False,
            capture_output=True,
        )
        return
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmd = " ".join(proc.info.get("cmdline") or [])
        except Exception:
            continue
        if "xau_widget_pro" in cmd and ("main.py" in cmd or "run.py" in cmd):
            proc.kill()


def main() -> None:
    stop_old()
    time.sleep(0.4)
    x, y = default_pos()
    cfg_path = Path(os.environ.get("APPDATA", str(Path.home()))) / "XAUWidgetPro" / "config.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if cfg_path.exists():
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["x"] = x
    data["y"] = y
    data["user_positioned"] = False
    cfg_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"config -> ({x}, {y})")

    pyw = Path(r"D:\Python\pythonw.exe")
    exe = str(pyw if pyw.is_file() else sys.executable)
    subprocess.Popen([exe, str(ROOT / "main.py")], cwd=str(ROOT))
    print("restarted")


if __name__ == "__main__":
    main()
