@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$root=(Resolve-Path '%~dp0').Path; $desktop=[Environment]::GetFolderPath('Desktop'); $w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut((Join-Path $desktop 'ORBIT.lnk')); $s.TargetPath=(Join-Path $root 'launcher.bat'); $s.WorkingDirectory=$root; $s.IconLocation=((Join-Path $root 'ORBIT.ico') + ',0'); $s.Description='ORBIT Portable Console Launcher'; $s.Save()"
if errorlevel 1 (
  echo No se pudo crear el acceso directo.
  pause
  exit /b 1
)
echo Acceso directo ORBIT creado en el escritorio.
timeout /t 2 >nul
