$ErrorActionPreference = 'Stop'
function Assert-WorkspacePath([string]$Root, [string]$Path) {
    $absolute = [IO.Path]::GetFullPath($Path)
    if (-not $absolute.StartsWith([IO.Path]::GetFullPath($Root).TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) { throw "Path outside workspace: $absolute" }
    if ((Test-Path -LiteralPath $absolute) -and ((Get-Item -LiteralPath $absolute).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "Refusing a linked directory: $absolute" }
    return $absolute
}
function Get-SourceDigest([string]$Root, [string]$RecordPath = '') {
    $paths = @(foreach ($folder in @('native','scripts','packaging')) {
        Get-ChildItem -LiteralPath (Join-Path $Root $folder) -Recurse -File | ForEach-Object {
            $relative = $_.FullName.Substring($Root.TrimEnd('\').Length + 1).Replace('\','/')
            if ($relative -match '^(native/.*\.(cpp|h|inc|rc|in)|native/resources/.*\.json|scripts/.*\.ps1|packaging/.*\.(iss|cpp|rc|manifest))$') { $relative }
        }
    }) + @('CMakeLists.txt','packaging/CMakeLists.txt','native/dependencies.json','native/runtime-lock.json')
    [string[]]$paths = @($paths | Select-Object -Unique)
    [Array]::Sort($paths, [StringComparer]::Ordinal)
    $record = [Text.StringBuilder]::new()
    foreach ($relative in $paths) {
        if (Test-Path -LiteralPath (Join-Path $Root $relative)) { [void]$record.Append($relative).Append(':').Append((Get-FileHash -LiteralPath (Join-Path $Root $relative)).Hash.ToLowerInvariant()).Append("`n") }
    }
    $sha = [Security.Cryptography.SHA256]::Create()
    if ($RecordPath) { [IO.File]::WriteAllText($RecordPath, $record.ToString(), [Text.UTF8Encoding]::new($false)) }
    try { return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($record.ToString())))).Replace('-','').ToLowerInvariant() } finally { $sha.Dispose() }
}
function Install-ArtifactFile([string]$Root, [string]$Source, [string]$Destination) {
    $Source = Assert-WorkspacePath $Root $Source
    $Destination = Assert-WorkspacePath $Root $Destination
    $expected = (Get-FileHash -LiteralPath $Source).Hash
    $backup = Assert-WorkspacePath $Root (Join-Path "$Root\build" ([IO.Path]::GetFileName($Destination) + '.previous'))
    if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup }
    if (Test-Path -LiteralPath $Destination) { [IO.File]::Replace($Source, $Destination, $backup) } else { [IO.File]::Move($Source, $Destination) }
    if ((Get-FileHash -LiteralPath $Destination).Hash -ne $expected) {
        if (Test-Path -LiteralPath $backup) { [IO.File]::Replace($backup, $Destination, $null) }
        throw "Artifact publication failed: $Destination"
    }
    if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup }
}
function Sign-ReleaseFile([string]$Path) {
    if (-not $env:SF_SIGN_CERT_SHA1) { Write-Host "Unsigned (no publisher certificate configured): $([IO.Path]::GetFileName($Path))"; return }
    $tool = Get-Command signtool -ErrorAction SilentlyContinue
    $signTool = if ($tool) { $tool.Source } else { Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe" -ErrorAction SilentlyContinue | Sort-Object FullName | Select-Object -Last 1 -ExpandProperty FullName }
    if (-not $signTool) { throw 'Windows SDK SignTool is required for publisher signing' }
    & $signTool sign /sha1 $env:SF_SIGN_CERT_SHA1 /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 $Path
    if ($LASTEXITCODE -ne 0 -or (Get-AuthenticodeSignature -LiteralPath $Path).Status -ne 'Valid') { throw "Signing failed: $Path" }
}
function Write-BundleManifest([string]$Root, [string]$Bundle) {
    $infoPath = Join-Path $Bundle 'build-info.json'
    $process = Start-Process -FilePath (Join-Path $Bundle 'SonicForge.exe') -ArgumentList "--build-info `"$infoPath`"" -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(30000)) { Stop-Process -Id $process.Id; throw 'Build identity check timed out' }
    if ($process.ExitCode -ne 0) { throw 'Build identity check failed' }
    $info = Get-Content -LiteralPath $infoPath -Raw | ConvertFrom-Json
    if ($info.sourceDigest -ne (Get-SourceDigest $Root)) { throw 'The application was not built from the current source files' }
    $files = @(Get-ChildItem -LiteralPath $Bundle -Recurse -File | Where-Object Name -ne 'build-manifest.json' | ForEach-Object {
        $relative = $_.FullName.Substring($Bundle.TrimEnd('\').Length + 1).Replace('\','/')
        @{path=$relative;sha256=(Get-FileHash -LiteralPath $_.FullName).Hash.ToLowerInvariant();optional=($relative -match '^models/(ggml-.*\.bin|ctc-.*\.onnx)$')}
    })
    $manifest = @{schema=1;version=$info.version;sourceDigest=$info.sourceDigest;commit=(git -C $Root rev-parse HEAD);dirty=([bool](git -C $Root status --porcelain));files=$files;publisherSignature=(Get-AuthenticodeSignature -LiteralPath (Join-Path $Bundle 'SonicForge.exe')).Status.ToString()}
    $manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $Bundle 'build-manifest.json') -Encoding utf8
}
function Test-BundleManifest([string]$Root, [string]$Bundle) {
    $manifest = Get-Content -LiteralPath (Join-Path $Bundle 'build-manifest.json') -Raw | ConvertFrom-Json
    if ($manifest.sourceDigest -ne (Get-SourceDigest $Root)) { throw 'Bundle is stale. Run scripts/build_native.ps1 -Deploy first.' }
    foreach ($file in $manifest.files) {
        $path = [IO.Path]::GetFullPath((Join-Path $Bundle $file.path))
        if (-not $path.StartsWith([IO.Path]::GetFullPath($Bundle).TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid manifest path' }
        if (-not (Test-Path -LiteralPath $path)) { if ($file.optional) { continue }; throw "Missing bundle file: $path" }
        if ((Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant() -ne $file.sha256) { throw "Bundle checksum mismatch: $path" }
    }
    return $manifest
}
function Write-DistributionChecksums([string]$Root) {
    $dist = Join-Path $Root 'dist'
    $manifest = Get-Content -LiteralPath "$dist\SonicForge\build-manifest.json" -Raw | ConvertFrom-Json
    $names = @()
    $installerRecord = Join-Path $dist 'installer-build.json'
    if (Test-Path -LiteralPath $installerRecord) {
        $record = Get-Content -LiteralPath $installerRecord -Raw | ConvertFrom-Json
        if ($record.sourceDigest -eq $manifest.sourceDigest -and (Get-FileHash -LiteralPath "$dist\SonicForge-Setup.exe").Hash.ToLowerInvariant() -eq $record.setupSha256 -and (Get-FileHash -LiteralPath "$dist\SonicForge-Uninstall.exe").Hash.ToLowerInvariant() -eq $record.uninstallSha256) { $names += @('SonicForge-Setup.exe','SonicForge-Uninstall.exe') }
    }
    $zip = Join-Path $dist 'SonicForge-windows-x64.zip'
    if (Test-Path -LiteralPath $zip) {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $archive = [IO.Compression.ZipFile]::OpenRead($zip)
        try { $entry = $archive.GetEntry('SonicForge/build-info.json'); if ($entry) { $reader=[IO.StreamReader]::new($entry.Open()); try { $info=$reader.ReadToEnd()|ConvertFrom-Json; if($info.sourceDigest -eq $manifest.sourceDigest){$names+='SonicForge-windows-x64.zip'} } finally {$reader.Dispose()} } } finally {$archive.Dispose()}
    }
    $sums = foreach ($name in $names) { $path=Join-Path $dist $name;if(Test-Path -LiteralPath $path){(Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant()+'  '+$name} }
    $sums | Set-Content -LiteralPath "$dist\SHA256SUMS.txt" -Encoding ascii
}
