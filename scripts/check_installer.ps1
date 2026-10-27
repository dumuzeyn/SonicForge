param([switch]$FullPayload)
$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$TestId = [guid]::NewGuid().ToString().ToUpperInvariant()
$TestRoot = Join-Path $Root "build\installer-check\$TestId"
$InstallDir = Join-Path $TestRoot 'installed'
$Source = Join-Path $TestRoot 'source'
$RegistryKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{$TestId}_is1"
$SandboxKey = "HKCU:\Software\SonicForgePackagingTest\$TestId"
$Group = "Sonic Forge Packaging Check $TestId"
$GroupPath = Join-Path ([Environment]::GetFolderPath('Programs')) $Group
$Iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $Iscc) { throw 'Install Inno Setup 6 first' }
if (-not (Test-Path -LiteralPath "$Root\dist\SonicForge-Uninstall.exe")) { throw 'Build the installer first' }
New-Item -ItemType Directory -Path "$Source\assets" -Force | Out-Null
New-Item -ItemType Directory -Path "$Source\models" -Force | Out-Null
Set-Content -LiteralPath "$Source\models\ggml-test.bin" -Value 'optional model'
Set-Content -LiteralPath "$Source\models\ctc-test.onnx" -Value 'optional alignment model'
# Use a tiny payload and a unique AppId, shortcut group and registry namespace.
# Never install or uninstall the user's actual application during this check.
Copy-Item -LiteralPath "$Root\dist\SonicForge-Uninstall.exe" -Destination "$Source\SonicForge.exe"
if ($FullPayload) {
    & robocopy "$Root\dist\SonicForge" $Source /E /XF 'ggml-*.bin' 'ctc-*.onnx' /NFL /NDL /NJH /NJS /NP
    if ($LASTEXITCODE -ge 8) { throw 'Failed to prepare the actual bundle fixture' }
}
Copy-Item -LiteralPath "$Root\assets\sonic_forge_mark.ico" -Destination "$Source\assets"
$Script = Get-Content -LiteralPath "$Root\packaging\SonicForge.iss" -Raw
$Script = $Script.Replace('LicenseFile=..\LICENSE', "LicenseFile=$Root\LICENSE")
$Script = $Script.Replace('SetupIconFile=..\assets\sonic_forge_mark.ico', "SetupIconFile=$Root\assets\sonic_forge_mark.ico")
$Script = $Script.Replace('"Software\', '"Software\SonicForgePackagingTest\' + $TestId + '\')
$Script = $Script.Replace('Dumuzeyn.SonicForge', "Dumuzeyn.SonicForge.PackagingCheck.$TestId")
$Script = $Script.Replace('DefaultGroupName=Sonic Forge', "DefaultGroupName=$Group")
$FixtureScript = Join-Path $TestRoot 'check.iss'
Set-Content -LiteralPath $FixtureScript -Value $Script -Encoding utf8
& $Iscc /Qp "/DSourceRoot=$Source" "/DMyAppId=$TestId" "/O$TestRoot" '/FSetup-Check' $FixtureScript
if ($LASTEXITCODE -ne 0) { throw 'Installer fixture compilation failed' }
function RunAndWait([string]$Path, [string]$Arguments) {
    $Process = Start-Process -FilePath $Path -ArgumentList $Arguments -WindowStyle Hidden -PassThru
    if (-not $Process.WaitForExit(120000)) { Stop-Process -Id $Process.Id; throw "Installer check timed out: $Path" }
    if ($Process.ExitCode -ne 0) { throw "$Path failed ($($Process.ExitCode))" }
}
function RemoveTestInstallation {
    if (-not (Test-Path -LiteralPath $RegistryKey)) { return }
    $Entry = Get-ItemProperty -LiteralPath $RegistryKey
    if ($Entry.InstallLocation.TrimEnd('\') -ine $InstallDir) { throw 'Unexpected test installation path; refusing uninstall' }
    $Uninstaller = Join-Path $InstallDir 'unins000.exe'
    RunAndWait $Uninstaller "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOG=`"$TestRoot\uninstall.log`""
    # Inno's parent can exit before its helper finishes removing the executable.
    $CleanupDeadline = [Diagnostics.Stopwatch]::StartNew()
    while ((Test-Path -LiteralPath $Uninstaller) -and $CleanupDeadline.Elapsed.TotalSeconds -lt 15) {
        Start-Sleep -Milliseconds 100
    }
}
try {
    $Arguments = "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DIR=`"$InstallDir`" /GROUP=`"$Group`" /TASKS=`"`" /LOG=`"$TestRoot\install.log`""
    RunAndWait "$TestRoot\Setup-Check.exe" $Arguments
    $Entry = Get-ItemProperty -LiteralPath $RegistryKey
    if ($Entry.DisplayName -ne 'Sonic Forge' -or $Entry.SystemComponent -eq 1 -or
        $Entry.InstallLocation.TrimEnd('\') -ine $InstallDir -or
        -not $Entry.UninstallString -or -not $Entry.QuietUninstallString) { throw 'Invalid Windows application-list registration' }
    foreach ($File in @('SonicForge.exe', 'unins000.exe', 'unins000.dat')) {
        if (-not (Test-Path -LiteralPath "$InstallDir\$File")) { throw "Missing installed file: $File" }
    }
    if ($FullPayload) {
        if ((Get-FileHash "$InstallDir\SonicForge.exe").Hash -ne (Get-FileHash "$Root\dist\SonicForge\SonicForge.exe").Hash) { throw 'Installed executable differs from the verified bundle' }
        RunAndWait "$InstallDir\SonicForge.exe" "--build-info `"$TestRoot\installed-build-info.json`""
        $Actual = Get-Content "$TestRoot\installed-build-info.json" -Raw | ConvertFrom-Json
        $Expected = Get-Content "$Root\dist\SonicForge\build-info.json" -Raw | ConvertFrom-Json
        if ($Actual.sourceDigest -ne $Expected.sourceDigest) { throw 'Installed build identity differs' }
    }
    if ((Test-Path -LiteralPath "$InstallDir\models\ggml-test.bin") -or (Test-Path -LiteralPath "$InstallDir\models\ctc-test.onnx")) { throw 'Optional large models leaked into the lightweight installer' }
    $Shell = New-Object -ComObject WScript.Shell
    $Links = @(Get-ChildItem -LiteralPath $GroupPath -Filter *.lnk)
    $Targets = @($Links | ForEach-Object { $Shell.CreateShortcut($_.FullName).TargetPath })
    if ($Targets -notcontains "$InstallDir\SonicForge.exe" -or $Targets -notcontains "$InstallDir\unins000.exe") {
        throw 'Application or uninstall Start menu shortcut is missing'
    }
    # Reinstall using the same identity: updates must retain a single entry/log.
    RunAndWait "$TestRoot\Setup-Check.exe" $Arguments
    if (@(Get-ChildItem -LiteralPath $InstallDir -Filter 'unins*.exe').Count -ne 1) { throw 'Upgrade duplicated the uninstaller' }
    Set-Content -LiteralPath "$InstallDir\user-project.txt" -Value 'keep user files'
    RemoveTestInstallation
    if (Test-Path -LiteralPath $RegistryKey) { throw 'Uninstall registry entry was retained' }
    if (Test-Path -LiteralPath "$InstallDir\SonicForge.exe") { throw 'Application was not removed' }
    if (Test-Path -LiteralPath "$InstallDir\unins000.exe") { throw 'Uninstaller was not removed' }
    if (Test-Path -LiteralPath $GroupPath) { throw 'Start menu shortcuts were retained' }
    if ((Get-Content -LiteralPath "$InstallDir\user-project.txt" -Raw).Trim() -ne 'keep user files') { throw 'User file was changed' }
    New-Item -ItemType Directory -Path "$Root\validation" -Force | Out-Null
    @{complete=$true;fullPayload=[bool]$FullPayload;testId=$TestId;logs=$TestRoot;sourceDigest=$(if($FullPayload){$Expected.sourceDigest}else{''});userFilePreserved=$true;checkedAt=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json | Set-Content "$Root\validation\installer-check.json" -Encoding utf8
    Write-Host 'PASS: install, Windows registration, launch/uninstall shortcuts, upgrade, uninstall, user-file preservation.'
    Write-Host "Logs: $TestRoot"
} finally {
    RemoveTestInstallation
    if (Test-Path -LiteralPath $SandboxKey) { Remove-Item -LiteralPath $SandboxKey -Recurse -Force }
}
