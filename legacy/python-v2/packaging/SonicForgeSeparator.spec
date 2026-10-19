from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs
from importlib.metadata import distributions
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent

licenses = []
for package in distributions():
    name = package.metadata.get('Name', '').lower().replace('_', '-')
    if name in ('pip', 'setuptools', 'wheel', 'pyinstaller', 'pyinstaller-hooks-contrib'):
        continue
    for item in package.files or ():
        if 'dist-info' in str(item) and any(word in item.name.upper() for word in ('LICENSE', 'COPYING', 'NOTICE')):
            licenses.append((str(package.locate_file(item)), 'licenses/' + name))

a = Analysis([str(ROOT / 'scripts/stem_worker.py')], pathex=[str(ROOT / 'src')], binaries=collect_dynamic_libs('ctranslate2'),
             datas=[(str(ROOT / 'build/stem-model/955717e8-8726e21a.th'), 'model')] + collect_data_files('demucs') + collect_data_files('faster_whisper') + licenses,
             hiddenimports=['demucs.htdemucs', 'demucs.hdemucs', 'demucs.demucs', 'numpy.core.multiarray', 'numpy.core.numeric'],
             hookspath=[], runtime_hooks=[],
             excludes=['tkinter', 'IPython', 'pytest', 'matplotlib', 'scipy', 'torchvision', 'pandas', 'tensorboard'],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='SonicForgeSeparator', console=True, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name='SonicForgeSeparator', upx=False)
