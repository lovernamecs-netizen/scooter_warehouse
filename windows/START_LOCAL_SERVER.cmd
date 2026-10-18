@echo off
setlocal
cd /d "%~dp0.."
if not exist .venv\Scripts\python.exe (
 echo Python environment is missing. Follow README installation steps first.
 goto :failure
)
rem Existing data only. Configure WAREHOUSE_DATA_DIR or DATABASE_URL externally.
rem First-time initialization is a separate, explicit administrator operation.
.venv\Scripts\python.exe windows\start_local.py
if errorlevel 1 goto :failure
goto :eof
:failure
echo Setup failed. See the error above. Python 3.12 is required.
pause
exit /b 1
