@echo off
setlocal
cd /d "%~dp0.."
set "DATABASE_URL=sqlite:///warehouse.db"
set /p "BACKUP_NAME=Backup filename (example: backup-2026-10-05.swh): "
.venv\Scripts\python.exe -m server.cli backup --file "%BACKUP_NAME%"
pause
