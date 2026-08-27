@echo off
cd /d "%~dp0"
if exist "%~dp0venv\Scripts\pythonw.exe" (
  start "" "%~dp0venv\Scripts\pythonw.exe" "%~dp0start_xixi_desktop.py"
) else if exist "%~dp0.venv\Scripts\pythonw.exe" (
  start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0start_xixi_desktop.py"
) else (
  echo Python environment not found. Install requirements first.
  pause
)
