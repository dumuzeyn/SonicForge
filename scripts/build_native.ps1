param(
    [switch]$Deploy,
    [switch]$Installer,
    [switch]$Portable,
    [switch]$WhisperVulkan,
    [string]$FfmpegRoot = 'C:\ffmpeg',
    [string]$VCRuntimeRoot = "$env:WINDIR\System32",
    [int]$Jobs = 2
)
$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
. (Join-Path $PSScriptRoot 'release_common.ps1')
Set-Location -LiteralPath $Root
function Run([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed ($LASTEXITCODE)" }
}
function Download([string]$Url, [string]$Destination, [string]$Sha256) {
    if (Test-Path -LiteralPath $Destination) {
        if ((Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash.ToLowerInvariant() -eq $Sha256) { return }
        throw "Checksum mismatch: $Destination"
    }
    New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
    Invoke-WebRequest -Uri $Url -OutFile ($Destination+'.download')
    if ((Get-FileHash -LiteralPath ($Destination+'.download') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Sha256) { throw "Download checksum mismatch: $Url" }
    Move-Item -LiteralPath ($Destination+'.download') -Destination $Destination
}
function Recycle([string]$Path) {
    $Absolute = [IO.Path]::GetFullPath($Path)
    if (-not $Absolute.StartsWith($Root+[IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Refusing path outside repository' }
    if (-not (Test-Path -LiteralPath $Absolute)) { return }
    Add-Type -AssemblyName Microsoft.VisualBasic
    if (Test-Path -LiteralPath $Absolute -PathType Container) {
        [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory($Absolute, 'OnlyErrorDialogs', 'SendToRecycleBin', 'ThrowException')
    } else {
        [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile($Absolute, 'OnlyErrorDialogs', 'SendToRecycleBin', 'ThrowException')
    }
}
$Lock = Get-Content native/dependencies.json -Raw | ConvertFrom-Json
$Tools = Join-Path $Root 'build\native-tools'
$Qt = Join-Path $Root "build\qt\$($Lock.qt)\mingw_64"
$Compiler = Join-Path $Root 'build\qt\Tools\mingw1310_64\bin'
$CMake = Join-Path $Tools 'cmake\bin\cmake.exe'
if (-not (Test-Path -LiteralPath $CMake)) { $CMake=(Get-Command cmake -ErrorAction Stop).Source }
$Ctest=Join-Path (Split-Path -Parent $CMake) 'ctest.exe'
$Ninja=Join-Path $Tools 'bin\ninja.exe'
if (-not (Test-Path -LiteralPath $Ninja)) { $Ninja=(Get-Command ninja -ErrorAction Stop).Source }
if (-not (Test-Path -LiteralPath "$Qt\bin\qmake.exe") -or -not (Test-Path -LiteralPath "$Compiler\g++.exe")) {
    throw 'Install Qt 6.10.0 for MinGW 13.1 x64 (Multimedia, SVG and Image Formats), CMake and Ninja. See README.md.'
}
if (-not (Test-Path -LiteralPath "$Qt\plugins\imageformats\qwebp.dll")) { throw 'Qt Image Formats module is required' }
$env:PATH="$Compiler;$(Split-Path -Parent $Ninja);$(Split-Path -Parent $CMake);$Qt\bin;"+$env:PATH
New-Item -ItemType Directory -Path build/native-deps,validation -Force | Out-Null
foreach ($Dependency in @(@('whisper','https://github.com/ggml-org/whisper.cpp.git',$Lock.whisper), @('demucs','https://github.com/sevagh/demucs.cpp.git',$Lock.demucs))) {
    $Directory = "build/native-deps/$($Dependency[0])"
    if (-not (Test-Path -LiteralPath "$Directory/.git")) {
        Run git @('clone','--filter=blob:none',$Dependency[1],$Directory)
        Run git @('-C',$Directory,'checkout','--detach',$Dependency[2])
    }
    if ((git -C $Directory rev-parse HEAD) -ne $Dependency[2]) { throw "Unexpected dependency revision: $Directory" }
}
Run git @('-C','build/native-deps/demucs','submodule','update','--init','--depth','1')
if ((git -C build/native-deps/demucs/vendor/eigen rev-parse HEAD) -ne $Lock.eigen) { throw 'Unexpected Eigen revision' }
$VulkanOption = if ($WhisperVulkan) { 'ON' } else { 'OFF' }
Run $CMake @('-S','.','-B','build/native','-G','Ninja','-DCMAKE_BUILD_TYPE=Release',"-DCMAKE_PREFIX_PATH=$Qt",'-DCMAKE_C_COMPILER=gcc','-DCMAKE_CXX_COMPILER=g++',"-DCMAKE_MAKE_PROGRAM=$Ninja", "-DGGML_VULKAN=$VulkanOption" )
Run $CMake @('--build','build/native','-j',"$Jobs")
Run $Ctest @('--test-dir','build/native','--output-on-failure')
if (-not ($Deploy -or $Installer -or $Portable)) { return }
$Canonical = Assert-WorkspacePath $Root (Join-Path $Root 'dist\SonicForge')
$Target = Assert-WorkspacePath $Root (Join-Path $Root 'build\deploy-stage')
$TargetExe = Join-Path $Target 'SonicForge.exe'
$Running = Get-CimInstance Win32_Process -Filter "Name='SonicForge.exe'" | Where-Object { $_.ExecutablePath -eq (Join-Path $Canonical 'SonicForge.exe') }
if ($Running) { throw 'Закройте SonicForge перед обновлением сборки; открытый проект не будет прерван.' }
Recycle $Target
New-Item -ItemType Directory -Path $Target -Force | Out-Null
foreach ($File in @('ffmpeg.exe','ffprobe.exe')) {
    if (-not (Test-Path -LiteralPath "$FfmpegRoot\bin\$File")) { throw "Missing $FfmpegRoot\bin\$File" }
}
New-Item -ItemType Directory -Path "$Target\tools","$Target\models\genre","$Target\assets\fonts","$Target\licenses" -Force | Out-Null
$OrtArchive = Join-Path $Tools 'onnxruntime-win-x64-1.21.0.zip'
Download $Lock.onnxruntime.url $OrtArchive $Lock.onnxruntime.sha256
$OrtRoot = Join-Path $Tools 'onnxruntime-win-x64-1.21.0'
if (-not (Test-Path -LiteralPath "$OrtRoot\lib\onnxruntime.dll")) { Expand-Archive -LiteralPath $OrtArchive -DestinationPath $Tools }
Copy-Item -LiteralPath build/native/SonicForge.exe -Destination $TargetExe -Force
Run "$Qt\bin\windeployqt.exe" @('--release','--no-opengl-sw','--translations','ru,en','--include-plugins','qoffscreen',$TargetExe)
Copy-Item "$Compiler\libgomp-1.dll" $Target -Force
Copy-Item "$OrtRoot\lib\*.dll" "$Target\tools" -Force
$RuntimeLock = Get-Content native/runtime-lock.json -Raw | ConvertFrom-Json
foreach ($Entry in $RuntimeLock.files.PSObject.Properties) {
    $RuntimeFile = if ($Entry.Name -in @('ffmpeg.exe','ffprobe.exe')) { Join-Path "$FfmpegRoot\bin" $Entry.Name } else { Join-Path $VCRuntimeRoot $Entry.Name }
    if ((Get-FileHash -LiteralPath $RuntimeFile).Hash.ToLowerInvariant() -ne $Entry.Value.sha256) { throw "Runtime does not match native/runtime-lock.json: $RuntimeFile" }
}
foreach ($File in @('msvcp140.dll','msvcp140_1.dll','vcruntime140.dll','vcruntime140_1.dll')) { Copy-Item -LiteralPath "$VCRuntimeRoot\$File" -Destination $Target -Force }
Copy-Item "$FfmpegRoot\bin\ffmpeg.exe","$FfmpegRoot\bin\ffprobe.exe" "$Target\tools" -Force
Copy-Item assets/fonts/* "$Target\assets\fonts" -Force
Copy-Item assets/sonic_forge_mark.ico "$Target\assets" -Force
Copy-Item assets/models/genre/* "$Target\models\genre" -Force
$Models = Get-Content native/resources/models.json -Raw | ConvertFrom-Json
foreach ($Kind in @('speech','speech_fast','alignment_ru','alignment_en','stems')) {
    $Model = $Models.$Kind
    $Cache = Join-Path $Root ('build\native-models\'+$Model.file)
    Download $Model.url $Cache $Model.sha256
    Copy-Item -LiteralPath $Cache -Destination "$Target\models\$($Model.file)" -Force
}
Copy-Item native/resources/models.json "$Target\models\manifest.json" -Force
Copy-Item native/dependencies.json "$Target\licenses\dependencies.json" -Force
Copy-Item LICENSE $Target -Force
Copy-Item packaging/THIRD_PARTY_NOTICES.md "$Target\licenses" -Force
Copy-Item packaging/licenses/* "$Target\licenses" -Force
foreach ($Module in @('qtbase','qtsvg','qtmultimedia','qtimageformats')) { Copy-Item "$Qt\sbom\$Module-$($Lock.qt).spdx.json" "$Target\licenses" -Force }
Copy-Item build/native-deps/whisper/LICENSE "$Target\licenses\whisper-MIT.txt" -Force
Copy-Item build/native-deps/demucs/LICENSE "$Target\licenses\demucs-MIT.txt" -Force
Copy-Item build/native-deps/demucs/vendor/eigen/COPYING.MPL2 "$Target\licenses\Eigen-MPL2.txt" -Force
Copy-Item "$OrtRoot\LICENSE" "$Target\licenses\onnxruntime-MIT.txt" -Force
Copy-Item "$OrtRoot\ThirdPartyNotices.txt" "$Target\licenses\onnxruntime-third-party.txt" -Force
Copy-Item "$FfmpegRoot\LICENSE" "$Target\licenses\FFmpeg-GPL3.txt" -Force
Copy-Item "$FfmpegRoot\README.txt" "$Target\licenses\FFmpeg-build.txt" -Force
Copy-Item "$Compiler\..\licenses\gcc\*" "$Target\licenses" -Force
Copy-Item "$Compiler\..\licenses\winpthreads\*" "$Target\licenses" -Force
Set-Content -LiteralPath "$Target\qt.conf" -Encoding ascii -Value "[Paths]`nPrefix=.`nPlugins=.`nTranslations=translations"
$OldPlatform = $env:QT_QPA_PLATFORM
try {
    $env:QT_QPA_PLATFORM='offscreen'
    $Smoke = Start-Process -FilePath $TargetExe -ArgumentList '--smoke-test',"`"$Root\validation\packaged-ui`"" -WindowStyle Hidden -PassThru
    if (-not $Smoke.WaitForExit(120000)) { Stop-Process -Id $Smoke.Id; throw 'Packaged UI check timed out; canonical bundle unchanged' }
    if ($Smoke.ExitCode -ne 0) { throw 'Packaged UI check failed; canonical bundle unchanged' }
} finally { $env:QT_QPA_PLATFORM=$OldPlatform }
Recycle "$Target\_internal"
$Forbidden = Get-ChildItem -LiteralPath $Target -Recurse -File | Where-Object { $_.Extension -in '.py','.pyc','.pyd' -or $_.Name -match '^python.*\.dll$' }
if ($Forbidden) { throw 'Python runtime found in native distribution' }
Sign-ReleaseFile $TargetExe
Write-BundleManifest $Root $Target
& (Join-Path $PSScriptRoot 'check_native.ps1') -Application 'build\deploy-stage\SonicForge.exe'
$Rollback = Assert-WorkspacePath $Root (Join-Path $Root 'build\deploy-rollback')
Recycle $Rollback
$HadCanonical = Test-Path -LiteralPath $Canonical
try {
    if ($HadCanonical) { Move-Item -LiteralPath $Canonical -Destination $Rollback }
    Move-Item -LiteralPath $Target -Destination $Canonical
} catch {
    if (-not (Test-Path -LiteralPath $Canonical) -and (Test-Path -LiteralPath $Rollback)) { Move-Item -LiteralPath $Rollback -Destination $Canonical }
    throw
}
$Target = $Canonical
Recycle $Rollback
if ($Installer) {
    & (Join-Path $PSScriptRoot 'build_installer.ps1')
}
if ($Portable) {
    $Zip = Join-Path $Root 'dist\SonicForge-windows-x64.zip'
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $StagedZip = Assert-WorkspacePath $Root (Join-Path $Root 'build\SonicForge-windows-x64.zip')
    if (Test-Path -LiteralPath $StagedZip) { Remove-Item -LiteralPath $StagedZip }
    # Release assets must fit GitHub's 2 GiB limit. Keep optional neural models
    # in the local bundle; the portable app downloads missing models on demand.
    $Archive = [IO.Compression.ZipFile]::Open($StagedZip, [IO.Compression.ZipArchiveMode]::Create)
    try {
        foreach ($File in Get-ChildItem -LiteralPath $Target -Recurse -File) {
            $Relative = $File.FullName.Substring($Target.TrimEnd('\').Length + 1).Replace('\','/')
            if ($Relative -match '^models/(ggml-.*\.bin|ctc-.*\.onnx)$') { continue }
            [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($Archive, $File.FullName, 'SonicForge/'+$Relative, [IO.Compression.CompressionLevel]::Fastest) | Out-Null
        }
    } finally { $Archive.Dispose() }
    if ((Get-Item -LiteralPath $StagedZip).Length -ge 2GB) { throw 'Portable archive exceeds GitHub release asset size limit' }
    Install-ArtifactFile $Root $StagedZip $Zip
}
Write-DistributionChecksums $Root
Write-Host 'Готово: dist\SonicForge обновлён на месте.'
