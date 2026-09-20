@echo off
setlocal
cd /d "%~dp0"
title ORBIT - Limpiar cache antigua v0.1.5

echo.
echo Este proceso elimina SOLO el perfil/caché de Edge que ORBIT v0.1.5 creó en el USB.
echo No elimina juegos, carátulas, configuración, estadísticas ni emuladores.
echo.
if not exist "data\browser-profile" (
  echo No existe cache antigua que limpiar.
  pause
  exit /b 0
)

echo Cierra ORBIT antes de continuar.
choice /C SN /N /M "Eliminar data\browser-profile ahora? [S/N]: "
if errorlevel 2 exit /b 0

rmdir /S /Q "data\browser-profile"
if exist "data\browser-profile" (
  echo.
  echo No se pudo eliminar toda la cache. Reinicia Windows y vuelve a ejecutar este archivo.
) else (
  echo.
  echo Cache antigua eliminada correctamente.
)
pause
