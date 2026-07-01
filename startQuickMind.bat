@echo off
title QuickMind - AION App
echo.
echo  === QuickMind ===
echo.
cd /d "C:\code\python\QuickMind"

:: Activer le venv si present
if exist "C:\code\python\QuickMind\.venv\Scripts\activate.bat" (
    call "C:\code\python\QuickMind\.venv\Scripts\activate.bat"
) else (
    echo [WARN] Venv absent - Python systeme
)

:: Lancer l'app
echo  Demarrage QuickMind...
"C:\code\python\QuickMind\.venv\Scripts\python.exe" run_api.py

pause