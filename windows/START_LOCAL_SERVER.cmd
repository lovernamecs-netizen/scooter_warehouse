@echo off
setlocal
cd /d "%~dp0.."
call :find_python
if defined WAREHOUSE_PYTHON goto :run
echo Installing Python 3.12 for this PC...
powershell.exe -NoProfile -Command "$ErrorActionPreference='Stop'; $p=Join-Path $env:TEMP ('warehouse-python-'+[guid]::NewGuid().ToString('N')+'.exe'); [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile $p; $s=Get-AuthenticodeSignature -LiteralPath $p; if($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch 'Python Software Foundation'){throw 'Python installer signature verification failed'}; $r=Start-Process -FilePath $p -ArgumentList @('InstallAllUsers=0','Include_test=0') -Wait -PassThru; if($r.ExitCode -notin @(0,3010)){exit 1}"
if errorlevel 1 goto :failure
call :find_python
if not defined WAREHOUSE_PYTHON goto :failure
:run
"%WAREHOUSE_PYTHON%" windows\prepare_runtime.py
if errorlevel 1 goto :failure
exit /b 0

:find_python
set "WAREHOUSE_PYTHON="
call :probe "%CD%\.venv\Scripts\python.exe"
if defined WAREHOUSE_PYTHON exit /b 0
call :probe "%CD%\.venv-local\Scripts\python.exe"
if defined WAREHOUSE_PYTHON exit /b 0
for /f "delims=" %%P in ('py -3.12 -I -c "import sys; print(sys.executable)" 2^>nul') do call :probe "%%P"
if defined WAREHOUSE_PYTHON exit /b 0
for /f "delims=" %%P in ('powershell.exe -NoProfile -Command "foreach($h in @('HKCU:','HKLM:')){$k=Get-Item ($h+'\Software\Python\PythonCore\3.12\InstallPath') -ErrorAction SilentlyContinue; if($k){$k.GetValue('ExecutablePath'); if($k.GetValue('')){Join-Path $k.GetValue('') 'python.exe'}}}" 2^>nul') do call :probe "%%P"
if defined WAREHOUSE_PYTHON exit /b 0
call :probe "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if defined WAREHOUSE_PYTHON exit /b 0
call :probe "%ProgramFiles%\Python312\python.exe"
exit /b 0

:probe
if defined WAREHOUSE_PYTHON exit /b 0
if not exist "%~1" exit /b 0
"%~1" -I -c "import sys,struct; sys.exit(0 if sys.version_info[:2]==(3,12) and struct.calcsize('P')==8 else 1)" >nul 2>&1
if not errorlevel 1 set "WAREHOUSE_PYTHON=%~1"
exit /b 0
:failure
echo Setup failed. Check the message above and run this file again.
pause
exit /b 1
