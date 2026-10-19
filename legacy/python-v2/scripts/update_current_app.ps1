param(
    [Parameter(Mandatory = $true)][string]$Source,
    [Parameter(Mandatory = $true)][string[]]$Targets,
    [string[]]$Files = @()
)
$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$SourceRoot = (Resolve-Path -LiteralPath $Source).Path
$SourceExe = Join-Path $SourceRoot 'SonicForge.exe'
if (-not (Test-Path -LiteralPath $SourceExe -PathType Leaf) -or
    -not (Test-Path -LiteralPath (Join-Path $SourceRoot '_internal\assets\sonic_forge_mark.ico'))) {
    throw 'Source is not a complete SonicForge bundle.'
}
$TargetRoots = @($Targets | ForEach-Object { (Resolve-Path -LiteralPath $_).Path })
foreach ($TargetRoot in $TargetRoots) {
    if ($TargetRoot -eq $SourceRoot -or
        -not (Test-Path -LiteralPath (Join-Path $TargetRoot 'SonicForge.exe') -PathType Leaf)) {
        throw "Target must be an existing, different SonicForge installation: $TargetRoot"
    }
}

function Assert-TargetsClosed {
    $Running = @(Get-CimInstance Win32_Process -Filter "Name='SonicForge.exe'")
    foreach ($TargetRoot in $TargetRoots) {
        if ($Running | Where-Object { $_.ExecutablePath -eq (Join-Path $TargetRoot 'SonicForge.exe') }) {
            throw "Save your project and close SonicForge before updating: $TargetRoot"
        }
    }
}

function Get-BundleHash([string]$Path) {
    $Stream = [IO.File]::OpenRead($Path)
    try { return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($Stream)) }
    finally { $Stream.Dispose() }
}

Assert-TargetsClosed
$Changes = @()
$SourceFiles = if ($Files.Count) {
    foreach ($File in $Files) {
        $Selected = [IO.Path]::GetFullPath((Join-Path $SourceRoot $File))
        if (-not $Selected.StartsWith($SourceRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase) -or
            -not (Test-Path -LiteralPath $Selected -PathType Leaf)) {
            throw "Requested file outside or missing from the source bundle: $File"
        }
        Get-Item -LiteralPath $Selected
    }
} else { Get-ChildItem -LiteralPath $SourceRoot -File -Recurse }
foreach ($SourceFile in $SourceFiles) {
    $RelativePath = [IO.Path]::GetRelativePath($SourceRoot, $SourceFile.FullName)
    $SourceHash = Get-BundleHash $SourceFile.FullName
    foreach ($TargetRoot in $TargetRoots) {
        $Destination = [IO.Path]::GetFullPath((Join-Path $TargetRoot $RelativePath))
        if (-not $Destination.StartsWith($TargetRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw "File outside the application directory: $Destination"
        }
        $Exists = Test-Path -LiteralPath $Destination -PathType Leaf
        if ($Exists -and (Get-Item -LiteralPath $Destination).Length -eq $SourceFile.Length -and
            (Get-BundleHash $Destination) -eq $SourceHash) {
            continue
        }
        $Changes += [PSCustomObject]@{
            Source = $SourceFile.FullName; Destination = $Destination
            Root = $TargetRoot; Relative = $RelativePath; Existed = $Exists; Hash = $SourceHash
        }
    }
}

# Do not terminate open instances; check again after preparing the plan.
Assert-TargetsClosed
$BackupRoot = Join-Path $RepoRoot ('build\app-update-backups\' + [guid]::NewGuid().ToString('N'))
foreach ($Change in $Changes) {
    if ($Change.Existed) {
        $TargetIndex = [Array]::IndexOf($TargetRoots, $Change.Root)
        $Backup = Join-Path (Join-Path $BackupRoot ([string]$TargetIndex)) $Change.Relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $Backup) -Force | Out-Null
        Copy-Item -LiteralPath $Change.Destination -Destination $Backup
    }
}
Assert-TargetsClosed
foreach ($Change in $Changes) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $Change.Destination) -Force | Out-Null
    Copy-Item -LiteralPath $Change.Source -Destination $Change.Destination -Force
    if ((Get-BundleHash $Change.Destination) -ne $Change.Hash) {
        throw "Updated file verification failed: $($Change.Destination). Backup: $BackupRoot"
    }
}
foreach ($TargetRoot in $TargetRoots) {
    $Count = @($Changes | Where-Object Root -eq $TargetRoot).Count
    Write-Output "Updated $Count files in existing application: $TargetRoot"
}
if ($Changes.Count) { Write-Output "Previous changed files backed up: $BackupRoot" }
