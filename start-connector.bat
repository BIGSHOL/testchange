@echo off
chcp 65001 > nul
set PY311=C:\Users\user\AppData\Local\Programs\Python\Python311\python.exe
cd /d "D:\시험지 한글화"
echo MathGen HWP Connector  (127.0.0.1:8765, engine=hwpx, COM)
echo 중지하려면 Ctrl+C
"%PY311%" -m server.connector --host 127.0.0.1 --port 8765
pause
