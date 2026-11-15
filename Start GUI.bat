@echo off
setlocal
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
    echo Project Python environment not found. Follow README.md setup first.
    pause
    exit /b 1
)
"venv\Scripts\python.exe" "main.py"
if errorlevel 1 (
    echo.
    echo The application stopped with an error. See the message above.
    pause
)
