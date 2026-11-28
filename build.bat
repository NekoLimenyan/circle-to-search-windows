@echo off
chcp 65001 >nul
title Збірка релізу Circle to Search

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: Закриваємо запущений процес, щоб розблокувати dist\CircleToSearch.exe
taskkill /F /IM CircleToSearch.exe >nul 2>&1

if exist ".venv\Scripts\python.exe" (
    set "PY_EXE=.venv\Scripts\python.exe"
) else (
    set "PY_EXE=python"
)

echo [1/4] Перевірка PyInstaller та залежностей...
"%PY_EXE%" -m pip install --upgrade pyinstaller -r requirements.txt
if %errorlevel% neq 0 (
    echo [ПОМИЛКА] Не вдалося встановити залежності.
    pause
    exit /b 1
)

echo.
echo [2/4] Генерація іконки лупи...
"%PY_EXE%" -c "from app.icon_gen import generate_lens_icon; generate_lens_icon('app/circle_to_search.ico')"

echo.
echo [3/4] Компіляція портативного CircleToSearch.exe...
"%PY_EXE%" -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name "CircleToSearch" ^
    --icon "app\circle_to_search.ico" ^
    --hidden-import winocr ^
    --hidden-import winrt.runtime ^
    --hidden-import winrt.system ^
    --hidden-import winrt.windows.foundation ^
    --hidden-import winrt.windows.foundation.collections ^
    --hidden-import winrt.windows.globalization ^
    --hidden-import winrt.windows.graphics.imaging ^
    --hidden-import winrt.windows.media.ocr ^
    --hidden-import winrt.windows.storage.streams ^
    --collect-submodules winrt ^
    "circle_to_search.pyw"

if %errorlevel% neq 0 (
    echo [ПОМИЛКА] Збірка EXE завершилася з помилкою.
    pause
    exit /b 1
)

echo.
echo [4/4] Пошук Inno Setup для створення інсталятора...
set "ISCC="
if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"

if defined ISCC (
    "%ISCC%" "%SCRIPT_DIR%installer.iss"
    echo.
    echo ===================================================
    echo   Готово! Зібрано обидва файли у папці dist\:
    echo   1. CircleToSearch.exe       (Портативна версія^)
    echo   2. CircleToSearch-Setup.exe (Інсталятор Windows^)
    echo ===================================================
) else (
    echo [ІНФО] Inno Setup 6 не знайдено — зібрано лише портативний EXE.
    echo Щоб збирати інсталятор, встановіть Inno Setup 6 та запустіть build.bat знову.
)

explorer /select,"%SCRIPT_DIR%dist\CircleToSearch-Setup.exe"
pause