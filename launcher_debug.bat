@echo off
setlocal
cd /d "%~dp0"
set "PORTABLE_LAUNCHER_ROOT=%~dp0"
title ORBIT - Modo diagnostico

if exist "runtime\python.exe" (
  "runtime\python.exe" launcher.py
  echo.
  echo ORBIT ha terminado. El registro tambien esta en data\logs\orbit.log
  pause
  goto :eof
)

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 launcher.py
  pause
  goto :eof
)

where python >nul 2>nul
if %errorlevel%==0 (
  python launcher.py
  pause
  goto :eof
)

echo No se ha encontrado Python. Ejecuta Preparar_USB.bat.
pause
