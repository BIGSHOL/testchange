@echo off
REM MathGen HWP connector - COM mode (engine=hwp, requires Hancom Office).
REM Generates real .hwp via Hancom COM (Task 4 - COM E2E).
REM Note: Hancom launches in background during conversion. If it hangs,
REM       press Ctrl+C and kill Hwp.exe in Task Manager. Try start-connector.bat first.
cd /d "%~dp0"
set "MATHGEN_HWP_ENGINE=hwp"
set "MATHGEN_HWP_NO_TOKEN=1"
echo [MathGen] Starting HWP connector  engine=hwp (Hancom COM .hwp)
echo   URL   : http://127.0.0.1:8765
echo   Token : %LOCALAPPDATA%\mathgen-connector\token.txt
echo   Stop  : close this window or press Ctrl+C
echo.
if not exist ".\.venv\Scripts\python.exe" (
  echo [ERROR] .venv\Scripts\python.exe not found in %CD%
  pause
  exit /b 1
)
".\.venv\Scripts\python.exe" -m server.connector
echo.
echo [MathGen] Connector exited with code %ERRORLEVEL%.
pause
