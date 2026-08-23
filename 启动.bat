@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHON_EXE="
if exist "D:\Python\python.exe" set "PYTHON_EXE=D:\Python\python.exe"
if "%PYTHON_EXE%"=="" set "PYTHON_EXE=python"

set "PYTHONW_EXE="
if exist "D:\Python\pythonw.exe" set "PYTHONW_EXE=D:\Python\pythonw.exe"
if "%PYTHONW_EXE%"=="" set "PYTHONW_EXE=%PYTHON_EXE%"

rem 结束旧实例，避免单实例锁导致“点了没反应”
for /f "tokens=2 delims==" %%i in ('wmic process where "CommandLine like '%%xau_widget_pro%%main.py%%'" get ProcessId /value 2^>nul ^| find "ProcessId"') do (
  taskkill /PID %%i /F >nul 2>nul
)
timeout /t 1 /nobreak >nul

"%PYTHON_EXE%" -m pip install -r requirements.txt -q
if errorlevel 1 (
  echo [ERROR] 依赖安装失败
  pause
  exit /b 1
)

start "" "%PYTHONW_EXE%" "%~dp0main.py"
echo 已启动：请看任务栏右侧金色金价（可拖动；双击复位）。
timeout /t 2 /nobreak >nul
