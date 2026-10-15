@echo off
setlocal
cd /d "%~dp0.."
if not exist .venv\Scripts\python.exe (
 py -3.12 -m venv .venv
 if errorlevel 1 goto :failure
 .venv\Scripts\python.exe -m pip install -r requirements.txt
 if errorlevel 1 goto :failure
)
set "DATABASE_URL=sqlite:///warehouse.db"
if not exist warehouse.db (
 echo Create an administrator. Password must be 10+ characters.
 .venv\Scripts\python.exe -m server.cli init
 if errorlevel 1 goto :failure
 .venv\Scripts\python.exe -m server.cli demo
 if errorlevel 1 goto :failure
)
echo Local server: http://127.0.0.1:8765
start "" http://127.0.0.1:8765
.venv\Scripts\python.exe -m uvicorn server.app:app --host 127.0.0.1 --port 8765
goto :eof
:failure
echo Setup failed. See the error above. Python 3.12 is required.
pause
exit /b 1
