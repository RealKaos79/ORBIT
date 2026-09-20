$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$Runtime = Join-Path $Root "runtime"
$Version = "3.14.7"

$DetectedArch = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
switch ($DetectedArch.ToUpperInvariant()) {
    "AMD64" {
        $Package = "python-$Version-embeddable-amd64.zip"
        $ExpectedSha256 = "76c3c0384ab3f822486f32450f3a4d20f5d65ad0ec32ee34290971aa0eb817e6"
        $ArchName = "Windows x64"
    }
    "ARM64" {
        $Package = "python-$Version-embeddable-arm64.zip"
        $ExpectedSha256 = "b777fa08b68a177e350f8730c3e97a2b216d81e3eb5d183b039c65d43a6a2b3e"
        $ArchName = "Windows ARM64"
    }
    "X86" {
        $Package = "python-$Version-embeddable-win32.zip"
        $ExpectedSha256 = "c784a4596d706d647d430286e2db1d1e3dcc1acb8bc6993fabf147fc00606e18"
        $ArchName = "Windows x86"
    }
    default { throw "Arquitectura de Windows no compatible: $DetectedArch" }
}

$Url = "https://www.python.org/ftp/python/$Version/$Package"
$Zip = Join-Path $env:TEMP "orbit-python-$Version-$DetectedArch.zip"

Write-Host ""
Write-Host "ORBIT - Preparando runtime portable para $ArchName" -ForegroundColor Cyan
Write-Host ""

$NeedInstall = -not (Test-Path (Join-Path $Runtime "python.exe"))
if (-not $NeedInstall) {
    Write-Host "Comprobando el runtime portable existente..."
    Push-Location $Root
    try {
        & (Join-Path $Runtime "python.exe") -c "from app.server import LauncherServer; print('Runtime ORBIT correcto')"
        if ($LASTEXITCODE -ne 0) { $NeedInstall = $true }
    }
    catch { $NeedInstall = $true }
    finally { Pop-Location }
    if (-not $NeedInstall) {
        Write-Host "El runtime portable ya existe y funciona." -ForegroundColor Green
    }
}

if ($NeedInstall) {
    if (Test-Path $Runtime) { Remove-Item $Runtime -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $Runtime | Out-Null
    Write-Host "Descargando Python embebido oficial $Version desde python.org..."
    Invoke-WebRequest -Uri $Url -OutFile $Zip -UseBasicParsing

    Write-Host "Verificando integridad SHA-256..."
    $ActualSha256 = (Get-FileHash -Path $Zip -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ActualSha256 -ne $ExpectedSha256) {
        Remove-Item $Zip -Force -ErrorAction SilentlyContinue
        throw "La verificacion SHA-256 ha fallado. No se instalara el runtime descargado."
    }

    Write-Host "Extrayendo runtime..."
    Expand-Archive -Path $Zip -DestinationPath $Runtime -Force
    Remove-Item $Zip -Force -ErrorAction SilentlyContinue
}

$Pth = Get-ChildItem -Path $Runtime -Filter "python*._pth" | Select-Object -First 1
if (-not $Pth) {
    throw "No se encontro el archivo python*._pth dentro del runtime."
}

$Lines = Get-Content $Pth.FullName
if ($Lines -notcontains "..") {
    $NewLines = @()
    foreach ($Line in $Lines) {
        $NewLines += $Line
        if ($Line -eq ".") { $NewLines += ".." }
    }
    if ($NewLines -notcontains "..") { $NewLines += ".." }
    Set-Content -Path $Pth.FullName -Value $NewLines -Encoding ASCII
}

Write-Host "Comprobando runtime y codigo ORBIT..."
Push-Location $Root
try {
    & (Join-Path $Runtime "python.exe") -c "from app.server import LauncherServer; from app.services.dialogs import open_dialog; print('Runtime ORBIT correcto')"
    if ($LASTEXITCODE -ne 0) { throw "La comprobacion del runtime ha fallado." }
}
finally {
    Pop-Location
}

@"
ORBIT Portable Runtime
Python: $Version
Architecture: $ArchName
Source: python.org official embeddable distribution
SHA256: $ExpectedSha256
Prepared: $(Get-Date -Format s)
"@ | Set-Content -Path (Join-Path $Runtime "RUNTIME_INFO.txt") -Encoding UTF8

Write-Host ""
Write-Host "Listo. Este USB ya puede ejecutar ORBIT sin instalar Python." -ForegroundColor Green
Write-Host "Abre launcher.bat para iniciar la consola." -ForegroundColor Green
Write-Host ""
Read-Host "Pulsa Enter para cerrar"
