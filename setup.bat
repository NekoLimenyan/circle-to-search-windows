@echo off
chcp 65001 >nul
title Встановлення Circle to Search для Windows

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

if exist ".venv\Scripts\python.exe" (
    set "PY_EXE=.venv\Scripts\python.exe"
    set "PYW_EXE=.venv\Scripts\pythonw.exe"
) else (
    python --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo [ПОМИЛКА] Python не знайдено у PATH.
        pause
        exit /b 1
    )
    set "PY_EXE=python"
    set "PYW_EXE=pythonw"
)

echo [1/3] Встановлення залежностей...
"%PY_EXE%" -m pip install -r requirements.txt

echo.
set /p ADD_STARTUP="[2/3] Додати ярлик в автозавантаження Windows? (Y/N): "
if /i "%ADD_STARTUP%"=="Y" (
    "%PY_EXE%" -m app.shortcut --startup
) else (
    "%PY_EXE%" -m app.shortcut
)

echo.
echo [3/3] Запуск Circle to Search...
start "" "%PYW_EXE%" "%SCRIPT_DIR%circle_to_search.pyw"
timeout /t 2 >nul