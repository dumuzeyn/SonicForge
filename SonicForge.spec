# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules
from huggingface_hub import hf_hub_download
from lyrics_engine.language_identifier import REPO, REVISION
from importlib.metadata import distributions


whisper_datas = collect_data_files('faster_whisper')
ct2_binaries = collect_dynamic_libs('ctranslate2')
language_datas = [(hf_hub_download(REPO, filename, revision=REVISION), 'models/language_id')
                  for filename in ('voxlingua107.onnx', 'lang_map.json')]

# Preserve upstream terms, including transitive runtime components.
license_datas = []
runtime_names = {'av', 'numpy', 'pillow', 'psutil', 'faster-whisper', 'ctranslate2',
                 'onnxruntime', 'anyascii', 'tkinterdnd2', 'huggingface-hub', 'tokenizers',
                 'safetensors', 'requests', 'certifi', 'charset-normalizer', 'idna', 'urllib3',
                 'tqdm', 'pyyaml', 'packaging', 'filelock', 'fsspec', 'sympy', 'mpmath',
                 'coloredlogs', 'humanfriendly', 'flatbuffers', 'protobuf', 'ftfy', 'wcwidth'}
for package in distributions():
    name = package.metadata.get('Name', '').lower().replace('_', '-')
    if name not in runtime_names:
        continue
    for item in package.files or ():
        if 'dist-info' in str(item) and any(word in item.name.upper() for word in ('LICENSE', 'COPYING', 'NOTICE')):
            license_datas.append((str(package.locate_file(item)), 'licenses/' + name))


a = Analysis(
    ['music_polisher_gui.py'],
    pathex=[],
    binaries=[('C:\\ffmpeg\\bin\\ffmpeg.exe', 'ffmpeg')] + ct2_binaries,
    datas=[
        ('Normalize-Music.py', '.'),
        ('assets\\sonic_forge_mark.ico', 'assets'),
        ('assets\\sonic_forge_mark.png', 'assets'),
        ('assets\\fonts', 'assets\\fonts'),
        ('packaging\\LANGUAGE_MODELS.txt', 'licenses'),
        ('packaging\\Apache-2.0.txt', 'licenses'),
        ('packaging/SEPARATION_ENGINE.txt', 'licenses'),
        ('LICENSE', 'licenses/sonicforge'),
        ('THIRD_PARTY_NOTICES.md', 'licenses/sonicforge'),
        ('C:/ffmpeg/LICENSE', 'licenses/ffmpeg'),
        ('C:/ffmpeg/README.txt', 'licenses/ffmpeg'),
        ('build/separator/SonicForgeSeparator', 'separator'),
    ] + license_datas + whisper_datas + language_datas + collect_data_files('anyascii') + collect_data_files('tkinterdnd2'),
    hiddenimports=collect_submodules('music2picture_v2') + [
        'faster_whisper',
        'faster_whisper.audio',
        'faster_whisper.tokenizer',
        'faster_whisper.transcribe',
        'ctranslate2',
        'av',
        'ftfy',
        'anyascii',
        'onnxruntime',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['scripts/splash_runtime.py'],
    excludes=[
        'IPython',
        'jedi',
        'jsonschema',
        'matplotlib',
        'nbformat',
        'pandas',
        'pytest',
        'scipy',
        'tensorflow',
        'torchaudio',
        'torch',
        'torchvision',
        'mutagen',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    name='SonicForge',
    exclude_binaries=True,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\sonic_forge_mark.ico'],
    version='packaging\\version_info.txt',
    manifest='packaging\\SonicForge.manifest',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name='SonicForge',
)
