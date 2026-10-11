@echo off
cd /d "%~dp0"
set "PY="

REM 1) official py launcher
where py >nul 2>nul && set "PY=py"

REM 2) common base conda pythons
if not defined PY for %%P in (
  "%USERPROFILE%\miniconda3\python.exe"
  "%USERPROFILE%\anaconda3\python.exe"
) do if not defined PY if exist "%%~P" set "PY=%%~P"

REM 3) PATH python, but skip the Windows Store stub (WindowsApps)
if not defined PY for /f "delims=" %%G in ('where python 2^>nul') do if not defined PY ( echo %%G| find /i "WindowsApps" >nul || set "PY=%%G" )

if not defined PY (
  echo Python not found. Install Python, or open index.html directly.
  pause
  exit /b 1
)
echo Using Python: %PY%
"%PY%" serve.py
pause
