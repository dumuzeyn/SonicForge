# Third-party components

The [SonicForge license](../LICENSE) applies only to original project works.
It does not restrict rights granted by the licenses below. Retain upstream
notices when redistributing. The packaged `licenses` directory contains
upstream license texts collected from the installed distributions; font
notices are next to the font files. This inventory does not replace those texts.

| Component | Use | Upstream terms / source |
| --- | --- | --- |
| Python, Tcl/Tk | Runtime and desktop interface | PSF / Tcl/Tk licenses; [Python](https://www.python.org/), [Tcl/Tk](https://www.tcl.tk/) |
| NumPy | Signal and image calculations | BSD-3-Clause and bundled notices; [source](https://github.com/numpy/numpy) |
| Pillow | Image decoding and artwork | MIT-CMU; [source](https://github.com/python-pillow/Pillow) |
| PyAV | Container metadata and audio decoding | BSD-3-Clause; linked FFmpeg libraries keep their LGPL terms; [source](https://github.com/PyAV-Org/PyAV) |
| faster-whisper, CTranslate2 | Local speech transcription | MIT; [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [CTranslate2](https://github.com/OpenNMT/CTranslate2) |
| ONNX Runtime | Local language identification | MIT; [source](https://github.com/microsoft/onnxruntime) |
| VoxLingua107 classifier / ONNX export | Acoustic language classifier | Apache-2.0; [pinned model details](../packaging/LANGUAGE_MODELS.txt) |
| Specialized Georgian transcription weights | Optional downloaded speech model | Publisher-declared MIT; [revision and source](../packaging/LANGUAGE_MODELS.txt); not redistributed in the installer |
| AnyAscii | Transliterating text | ISC; [source](https://github.com/anyascii/anyascii) |
| psutil | Task/process control | BSD-3-Clause; [source](https://github.com/giampaolo/psutil) |
| tkinterdnd2 / tkdnd | File drag-and-drop | MIT / BSD-style upstream notices; [source](https://github.com/pmgagne/tkinterdnd2) |
| Demucs / HTDemucs | Separate local stem worker | MIT; [source and checkpoint](../packaging/SEPARATION_ENGINE.txt) |
| PyTorch / torchaudio | Separate stem runtime | BSD-style upstream licenses; [source](https://github.com/pytorch/pytorch), [torchaudio](https://github.com/pytorch/audio) |
| Noto Sans, Noto Serif, Oswald, Unbounded | Cover lettering | SIL OFL-1.1; [bundled notices](../assets/fonts/README.md) |
| FFmpeg executable | Independent command-line media tool, called through subprocess arguments | GPL-3.0; unmodified separate executable, not linked into original SonicForge code. [Distributor](https://www.gyan.dev/ffmpeg/builds/), [exact FFmpeg source revision](https://github.com/FFmpeg/FFmpeg/commit/38e89fe502). Its original LICENSE and build README are bundled in `licenses/ffmpeg`. GPL rights apply to this tool, not the noncommercial project license. |
| PyInstaller bootloader | Executable packaging | GPL with the upstream bootloader exception; [terms](https://pyinstaller.org/en/stable/license.html) |

The test-only independent tag checker is GPL-2.0-or-later and is **not**
included in the application runtime or EXE. It is installed only through
`requirements/development.txt`. [Source and terms](https://github.com/quodlibet/mutagen).

The installer does not download or run supplied media as programs. Browser
links are opened only following an explicit click. Local processing is not
a promise of perfect decoding, recognition or security.
