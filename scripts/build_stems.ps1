$ErrorActionPreference = 'Stop'
$StemRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $StemRoot
$StemPython = Join-Path $StemRoot 'build\stem-python\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $StemPython)) {
    python -m venv build/stem-python
    if ($LASTEXITCODE -ne 0) { throw 'Could not create isolated separation runtime' }
}
& $StemPython -c "import importlib.metadata as m; assert m.version('torch') == '2.11.0+cpu'; assert m.version('torchaudio') == '2.11.0+cpu'; assert m.version('demucs') == '4.0.1'; import PyInstaller"
if ($LASTEXITCODE -ne 0) {
    & $StemPython -m pip install torch==2.11.0 torchaudio==2.11.0 --index-url https://download.pytorch.org/whl/cpu
    if ($LASTEXITCODE -ne 0) { throw 'CPU separation dependencies could not be installed' }
    & $StemPython -m pip install demucs==4.0.1 pyinstaller==6.20.0
    if ($LASTEXITCODE -ne 0) { throw 'Separation build dependencies could not be installed' }
}
& $StemPython scripts/stem_worker.py --prepare-model build/stem-model
if ($LASTEXITCODE -ne 0) { throw 'Separation model verification failed' }
& $StemPython -m PyInstaller --noconfirm --distpath build/separator --workpath build/separator-work packaging/SonicForgeSeparator.spec
if ($LASTEXITCODE -ne 0) { throw 'Separation worker build failed' }
