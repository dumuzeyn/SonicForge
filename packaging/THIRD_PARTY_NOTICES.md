# SonicForge 3.1: third-party components

SonicForge's own code and original vector tool icons remain under the repository's LICENSE. Each dependency retains its own license. This document does not change those licenses.

| Component | Version / source | License |
|---|---|---|
| Qt Core, Gui, Widgets, Network, Concurrent, Multimedia, Svg | 6.10.0, dynamically linked, unmodified official MinGW binaries | LGPL 3.0 (included); alternative upstream licenses remain available |
| whisper.cpp / ggml | revision in `dependencies.json` | MIT |
| OpenAI Whisper large-v3 and large-v3-turbo weights, Q5_0 conversions | pinned model URLs and SHA-256 in `models/manifest.json` | MIT |
| Wav2Vec2 base-960h and large-xlsr-53-russian, quantized ONNX conversions | pinned models in `models/manifest.json`, vocabularies in `native/resources/ctc-*.json`; sources below | Apache 2.0, included |
| demucs.cpp | revision in `dependencies.json` | MIT |
| HTDemucs weights, F16 conversion | pinned model URL and SHA-256 in `models/manifest.json` | MIT |
| Eigen | revision in `dependencies.json`, MPL2-only build | MPL 2.0 |
| ONNX Runtime | 1.21.0, CPU, dynamically loaded | MIT; bundled upstream ThirdPartyNotices.txt |
| MSD musicnn | revision and model hash in `models/genre/manifest.json` | ISC (`models/genre/LICENSE.musicnn.txt`) |
| AnyAscii transliteration data | static Unicode table in `native/resources/transliteration.json`, derived from AnyAscii 0.3.3 | MIT |
| MinGW-w64, GCC libstdc++, libgcc, libgomp, winpthreads | GCC 13.1.0, Qt toolchain | respective upstream licenses; GCC Runtime Library Exception applies where specified |
| FFmpeg command-line tools | Gyan 2025-12-31 full build | GPL 3.0; separate executables invoked through QProcess, see FFmpeg-build.txt |
| FFmpeg libraries used by Qt Multimedia | supplied by official Qt 6.10.0 distribution | LGPL 2.1 or later, subject to upstream notices |
| Noto Sans, Noto Serif, Oswald, Unbounded | supplied font files | SIL OFL 1.1, included with each font |
| Microsoft Visual C++ runtime | app-local runtime for ONNX Runtime | Microsoft Visual Studio redistributable terms |

Qt is dynamically linked. Users may replace its DLLs and plugins with ABI-compatible modified builds. SonicForge imposes no additional restriction on reverse engineering for debugging modifications to the LGPL components. No Qt source modifications are made. Full corresponding Qt sources, including build scripts, are available at https://download.qt.io/archive/qt/6.10/6.10.0/single/ and https://code.qt.io/qt/ (tag v6.10.0). Qt's FFmpeg sources are available from https://download.qt.io/development_releases/prebuilt/ffmpeg/ and the Qt Multimedia source archive; the deployed DLL filenames identify the FFmpeg major versions. FFmpeg CLI build details and source commit are in FFmpeg-build.txt; sources: https://github.com/FFmpeg/FFmpeg/commit/38e89fe502 and https://www.gyan.dev/ffmpeg/builds/.

Native build scripts pin all neural engine revisions. The sole demucs.cpp portability adaptation changes its model loader's narrow `fopen` to `_wfopen(std::filesystem::u8path(...))` on Windows; CMake generates that translation unit in `build/native`, preserving the upstream checkout. The ggml Windows compatibility header supplies a missing Windows SDK type for MinGW 13.1. Both changes are included in the public SonicForge sources.

Microsoft runtime distribution terms: https://visualstudio.microsoft.com/license-terms/vs2022-cruntime/ . Qt attribution and embedded third-party software details: https://doc.qt.io/qt-6/licenses-used-in-qt.html . All source links refer to upstream software; SonicForge's application license remains separate.
