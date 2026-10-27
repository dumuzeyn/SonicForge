param()
$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
. (Join-Path $PSScriptRoot 'release_common.ps1')
function Run([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed ($LASTEXITCODE)" }
}
if (-not (Test-Path -LiteralPath "$Root\dist\SonicForge\SonicForge.exe")) {
    throw 'Build the application first with scripts/build_native.ps1 -Deploy'
}
$BundleManifest = Test-BundleManifest $Root "$Root\dist\SonicForge"
$Compiler = Join-Path $Root 'build\qt\Tools\mingw1310_64\bin'
$CMake = Join-Path $Root 'build\native-tools\cmake\bin\cmake.exe'
$Ninja = Join-Path $Root 'build\native-tools\bin\ninja.exe'
if (-not (Test-Path -LiteralPath $CMake)) { $CMake = (Get-Command cmake -ErrorAction Stop).Source }
if (-not (Test-Path -LiteralPath $Ninja)) { $Ninja = (Get-Command ninja -ErrorAction Stop).Source }
$Iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $Iscc) { throw 'Install Inno Setup 6 to build the installer' }
$PreviousPath = $env:PATH
try {
    $env:PATH = "$Compiler;$(Split-Path -Parent $Ninja);" + $env:PATH
    Run $CMake @('-S', "$Root\packaging", '-B', "$Root\build\packaging", '-G', 'Ninja',
        '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_CXX_COMPILER=g++', '-DCMAKE_RC_COMPILER=windres', "-DCMAKE_MAKE_PROGRAM=$Ninja")
    Run $CMake @('--build', "$Root\build\packaging")
    Sign-ReleaseFile "$Root\build\packaging\SonicForge-Uninstall.exe"
    Run $Iscc @('/Qp', "/O$Root\build\packaging", "$Root\packaging\SonicForge.iss")
    Sign-ReleaseFile "$Root\build\packaging\SonicForge-Setup.exe"
    Install-ArtifactFile $Root "$Root\build\packaging\SonicForge-Uninstall.exe" "$Root\dist\SonicForge-Uninstall.exe"
    Install-ArtifactFile $Root "$Root\build\packaging\SonicForge-Setup.exe" "$Root\dist\SonicForge-Setup.exe"
    @{sourceDigest=$BundleManifest.sourceDigest;setupSha256=(Get-FileHash -LiteralPath "$Root\dist\SonicForge-Setup.exe").Hash.ToLowerInvariant();uninstallSha256=(Get-FileHash -LiteralPath "$Root\dist\SonicForge-Uninstall.exe").Hash.ToLowerInvariant()} | ConvertTo-Json | Set-Content -LiteralPath "$Root\dist\installer-build.json" -Encoding utf8
    Write-DistributionChecksums $Root
} finally { $env:PATH = $PreviousPath }
