$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root

# Never discard an open project's unsaved edits during a build.
$TargetExe = [System.IO.Path]::GetFullPath((Join-Path $Root "dist\SonicForge\SonicForge.exe"))
$RunningTarget = Get-CimInstance Win32_Process -Filter "Name='SonicForge.exe'" |
    Where-Object { $_.ExecutablePath -eq $TargetExe }
if ($RunningTarget) {
    throw "Close the portable SonicForge application before rebuilding."
}

& (Join-Path $Root 'scripts\build_stems.ps1')
python -m PyInstaller --noconfirm packaging/SonicForge.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

$IsccCandidates = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
)
$Iscc = $IsccCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $Iscc) { throw "Inno Setup 6 is not installed" }
& $Iscc "packaging\SonicForge.iss"
if ($LASTEXITCODE -ne 0) { throw "Installer build failed" }

$Exe = Get-Item -LiteralPath "dist\SonicForge\SonicForge.exe"
$Installer = Get-Item -LiteralPath "dist\SonicForge-Setup-2.0.0.exe"
if ($Exe.VersionInfo.ProductName -ne "SonicForge") { throw "Invalid ProductName in EXE" }
if ($Exe.VersionInfo.ProductVersion -ne "2.0.0") { throw "Invalid ProductVersion in EXE" }
Write-Host "Built $($Exe.FullName)"
Write-Host "Built $($Installer.FullName)"
& (Join-Path $Root 'scripts\refresh_windows_shortcuts.ps1') -ApplicationPaths @($Exe.FullName)
