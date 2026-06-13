@echo off
REM Launcher script for Datamosh GUI (PySide6) on Windows.
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"

if not exist "%SCRIPT_DIR%main.py" (
    echo Error: main.py not found in %SCRIPT_DIR% 1>&2
    exit /b 1
)

where python >nul 2>&1
if errorlevel 1 (
    echo Error: python not found. Install Python 3.10+ from python.org. 1>&2
    exit /b 1
)

where ffmpeg >nul 2>&1
if errorlevel 1 echo Warning: ffmpeg not found in PATH. Normalization/render may fail. 1>&2

where ffprobe >nul 2>&1
if errorlevel 1 echo Warning: ffprobe not found in PATH. Timeline frame analysis may fail. 1>&2

python -c "import PySide6" >nul 2>&1
if errorlevel 1 (
    echo Error: PySide6 is not installed. Run: pip install -r requirements.txt 1>&2
    exit /b 1
)

python "%SCRIPT_DIR%main.py" %*
