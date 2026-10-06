from PyInstaller.utils.hooks import collect_data_files
from importlib.metadata import distribution
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent

licenses = []
for name in ('demucs', 'torch', 'torchaudio'):
    for item in distribution(name).files:
        if 'dist-info' in str(item) and item.name.upper() == 'LICENSE':
            licenses.append((str(distribution(name).locate_file(item)), 'licenses/' + name))

a = Analysis([str(ROOT / 'scripts/stem_worker.py')], pathex=[], binaries=[],
             datas=[(str(ROOT / 'build/stem-model/955717e8-8726e21a.th'), 'model')] + collect_data_files('demucs') + licenses,
             hiddenimports=['demucs.htdemucs', 'demucs.hdemucs', 'demucs.demucs', 'numpy.core.multiarray', 'numpy.core.numeric'],
             hookspath=[], runtime_hooks=[],
             excludes=['tkinter', 'IPython', 'pytest', 'matplotlib', 'scipy', 'torchvision', 'pandas', 'tensorboard'],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='SonicForgeSeparator', console=True, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name='SonicForgeSeparator', upx=False)
