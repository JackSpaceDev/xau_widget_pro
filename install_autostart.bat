@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHON_EXE="
if exist "D:\Python\python.exe" set "PYTHON_EXE=D:\Python\python.exe"
if "%PYTHON_EXE%"=="" set "PYTHON_EXE=python"

"%PYTHON_EXE%" -c "from pathlib import Path; import sys; sys.path.insert(0, r'%~dp0'.rstrip('\\')); from main import ConfigStore, set_autostart; s=ConfigStore(); c=s.load(); c.autostart=True; c.stick_left_bottom=True; c.always_on_top=True; s.save(c); p=str(Path(r'%~dp0main.py').resolve()); set_autostart(True, p); print('开机自启已开启:', p)"

if errorlevel 1 (
  echo [ERROR] 设置失败
  pause
  exit /b 1
)

echo.
echo 下次登录 Windows 后会自动显示金价小组件。
pause
