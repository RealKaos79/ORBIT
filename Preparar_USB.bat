@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Preparar_USB.ps1"
if errorlevel 1 pause
