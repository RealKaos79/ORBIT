@echo off
setlocal
cd /d "%~dp0"
set "PORTABLE_LAUNCHER_ROOT=%~dp0"
title ORBIT Portable Console Launcher

rem Prefer pythonw.exe so ORBIT keeps running independently of a console window.
if exist "runtime\pythonw.exe" (
  start "ORBIT" /D "%~dp0" "%~dp0runtime\pythonw.exe" "%~dp0launcher.py"
  exit /b 0
)

rem Fallback for an older/incomplete portable runtime.
if exist "runtime\python.exe" (
  "runtime\python.exe" launcher.py
  if errorlevel 1 (
    echo.
    echo ORBIT se ha cerrado por un error.
    echo Consulta data\logs\orbit.log o ejecuta launcher_debug.bat.
    echo.
    pause
  )
  goto :eof
)

where pyw >nul 2>nul
if %errorlevel%==0 (
  start "ORBIT" /D "%~dp0" pyw -3 "%~dp0launcher.py"
  exit /b 0
)

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 launcher.py
  if errorlevel 1 pause
  goto :eof
)

where python >nul 2>nul
if %errorlevel%==0 (
  python launcher.py
  if errorlevel 1 pause
  goto :eof
)

echo.
echo No se ha encontrado Python.
echo Ejecuta Preparar_USB.bat para instalar el runtime portable dentro del USB.
echo.
pause
