@echo off
chcp 65001 >nul
echo ===================================================
echo   Установка и настройка Circle to Search Windows
echo ===================================================

:: 1. Проверка наличия Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ОШИБКА] Python не найден в системе. Установите Python 3.10+ и добавьте его в PATH.
    pause
    exit /b
)

:: 2. Установка зависимостей
echo [1/2] Установка необходимых библиотек...
python -m pip install -r "%~dp0requirements.txt"

:: 3. Создание ярлыка на Рабочем столе через PowerShell
echo [2/2] Создание ярлыка на Рабочем столе...
set SCRIPT_DIR=%~dp0
set TARGET_FILE=%SCRIPT_DIR%circle_to_search.pyw

powershell -NoProfile -Command ^
    "$ws = New-Object -ComObject WScript.Shell; " ^
    "$desktop = [Environment]::GetFolderPath('Desktop'); " ^
    "$shortcut = $ws.CreateShortcut(\"$desktop\Circle to Search.lnk\"); " ^
    "$shortcut.TargetPath = 'pythonw.exe'; " ^
    "$shortcut.Arguments = '\"%TARGET_FILE%\"'; " ^
    "$shortcut.WorkingDirectory = '%SCRIPT_DIR%'; " ^
    "$shortcut.Description = 'Circle to Search for Windows'; " ^
    "$shortcut.Save()"

echo.
echo Все готово! Ярлык 'Circle to Search' создан на Рабочем столе.
pause