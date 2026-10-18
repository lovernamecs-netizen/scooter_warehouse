@echo off
setlocal
cd /d "%~dp0"
set "CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if not exist "%CSC%" set "CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe"
if not exist "%CSC%" (
 echo .NET Framework 4 compiler is required.
 pause
 exit /b 1
)
"%CSC%" /nologo /target:winexe /out:ScooterWarehouse.exe /reference:System.Windows.Forms.dll /reference:System.Drawing.dll Launcher.cs
if errorlevel 1 (
 pause
 exit /b 1
)
echo Built ScooterWarehouse.exe
start "" ScooterWarehouse.exe
