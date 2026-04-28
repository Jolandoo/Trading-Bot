@echo off
REM =============================================================================
REM start.bat — Lance le bot + le dashboard en deux fenêtres séparées
REM =============================================================================
REM Usage : double-clic, ou `start.bat` depuis le terminal
REM Pour stopper : ferme simplement les deux fenêtres (Ctrl+C dans chacune)
REM =============================================================================

SET PYTHONIOENCODING=utf-8

REM Fenêtre 1 : le bot de trading
start "Trading Bot" cmd /k "cd /d %~dp0 && python main.py"

REM Petit délai pour laisser le bot s'initialiser avant le dashboard
timeout /t 3 /nobreak >nul

REM Fenêtre 2 : le dashboard FastAPI
start "Dashboard" cmd /k "cd /d %~dp0 && python -m uvicorn dashboard.server:app --host 127.0.0.1 --port 8000"

REM Délai pour laisser uvicorn démarrer
timeout /t 4 /nobreak >nul

REM Ouvre le dashboard dans le navigateur par défaut
start http://127.0.0.1:8000

echo.
echo ============================================================
echo   Bot + Dashboard lances dans deux fenetres separees
echo   Dashboard : http://127.0.0.1:8000
echo   Pour arreter : fermez les deux fenetres (Ctrl+C)
echo ============================================================
echo.
