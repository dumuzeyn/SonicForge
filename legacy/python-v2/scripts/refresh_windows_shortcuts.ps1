param(
    [Parameter(Mandatory = $true)]
    [string[]]$ApplicationPaths
)
$ErrorActionPreference = 'Stop'

# Update only shortcuts targeting explicitly supplied Sonic Forge executables.
# Keep paths, arguments, names and pinning; never delete the Windows icon cache.
$ValidApplications = @{}
foreach ($ApplicationPath in $ApplicationPaths) {
    $ResolvedApplication = [IO.Path]::GetFullPath($ApplicationPath)
    if ([IO.Path]::GetFileName($ResolvedApplication) -ine 'SonicForge.exe') {
        throw "Not a Sonic Forge executable: $ResolvedApplication"
    }
    $IconPath = Join-Path (Split-Path -Parent $ResolvedApplication) '_internal\assets\sonic_forge_mark.ico'
    if ((Test-Path -LiteralPath $ResolvedApplication -PathType Leaf) -and
        (Test-Path -LiteralPath $IconPath -PathType Leaf)) {
        $ValidApplications[$ResolvedApplication] = $IconPath
    }
}
if (-not $ValidApplications.Count) { throw 'No complete Sonic Forge application found' }

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class SonicForgeShortcutNotification {
    [DllImport("shell32.dll")]
    public static extern void SHChangeNotify(int change, uint flags, IntPtr item1, IntPtr item2);
}
'@

$ShortcutShell = New-Object -ComObject WScript.Shell
$ShortcutRoots = @(
    [Environment]::GetFolderPath('Desktop'),
    (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu'),
    (Join-Path $env:APPDATA 'Microsoft\Internet Explorer\Quick Launch\User Pinned')
) | Select-Object -Unique
$BackupRoot = Join-Path (Split-Path -Parent $PSScriptRoot) ('build\shortcut-backups\' + [guid]::NewGuid().ToString('N'))
foreach ($ShortcutRoot in $ShortcutRoots) {
    if (-not (Test-Path -LiteralPath $ShortcutRoot)) { continue }
    foreach ($ShortcutFile in Get-ChildItem -LiteralPath $ShortcutRoot -Filter *.lnk -Recurse -ErrorAction SilentlyContinue) {
        $Shortcut = $ShortcutShell.CreateShortcut($ShortcutFile.FullName)
        if (-not $Shortcut.TargetPath) { continue }
        try { $TargetPath = [IO.Path]::GetFullPath($Shortcut.TargetPath) } catch { continue }
        if (-not $ValidApplications.ContainsKey($TargetPath)) { continue }
        $ExpectedIcon = $ValidApplications[$TargetPath] + ',0'
        if ($Shortcut.IconLocation -ne $ExpectedIcon) {
            New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
            $BackupPath = Join-Path $BackupRoot ([guid]::NewGuid().ToString('N') + '-' + $ShortcutFile.Name)
            Copy-Item -LiteralPath $ShortcutFile.FullName -Destination $BackupPath
            $Shortcut.IconLocation = $ExpectedIcon
            $Shortcut.Save()
        }
        $NotificationPath = [Runtime.InteropServices.Marshal]::StringToHGlobalUni($ShortcutFile.FullName)
        try {
            # SHCNE_UPDATEITEM / SHCNF_PATHW: notify the shell about this shortcut.
            [SonicForgeShortcutNotification]::SHChangeNotify(0x2000, 0x0005, $NotificationPath, [IntPtr]::Zero)
        } finally {
            [Runtime.InteropServices.Marshal]::FreeHGlobal($NotificationPath)
        }
        [PSCustomObject]@{ Shortcut = $ShortcutFile.FullName; Target = $TargetPath; Icon = $Shortcut.IconLocation }
    }
}
# Icon resources were replaced as well: ask the shell to refresh its cache.
[SonicForgeShortcutNotification]::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)
