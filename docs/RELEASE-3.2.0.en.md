# SonicForge 3.2.0

[English README](../README.en.md) · [Download this release](https://github.com/dumuzeyn/SonicForge/releases/tag/v3.2.0)

Reliability improvements following the October 25, 2026 audit.

- Project saving and opening, autosave and recovery. Projects retain the edit, timestamped lyrics, cover design and settings.
- Backups for replaced lyrics and exports, atomic writes, SHA-256 source checks, rollback of batch publication and separate reports for failed tracks.
- Preserved SYLT and language-specific MP3 lyric tracks, timestamp scaling when speed changes, damaged-ID3 validation and support for common ID3v2.2/v2.3/v2.4 tags.
- Large edits export without overflowing the Windows command line or appending unbounded silence. Internal processing uses float PCM, with selectable sample rate, channels and WAV bit depth, plus FLAC and Opus export. Preview uses the selected final codec and quality; processing with the limiter enabled checks true peak after encoding.
- Whole-recording analysis, bounded undo history, efficient drawing of the visible timeline, precise numeric input, standard text editing menus and persistent audio settings.
- Cache limits and cleanup, managed cancellation and timeouts, repair of damaged models in a writable user folder, and bounded-memory alignment of long lyrics.
- Compact installer and portable ZIP with large models downloaded on demand. Windows installed-app registration, a Start menu uninstall shortcut and a standalone uninstall launcher. Distribution updates are staged and verified before replacement.
- Build provenance manifests, pinned runtime hashes, additional regression checks and a Windows packaging workflow.

## Downloads

- `SonicForge-Setup.exe`: install or update the application for the current Windows user.
- `SonicForge-Uninstall.exe`: find the installed copy and open its standard uninstall confirmation.
- `SonicForge-windows-x64.zip`: extract everything and run `SonicForge/SonicForge.exe`.
- `SHA256SUMS.txt`: SHA-256 checksums for the three files above.

The installer and ZIP exclude large Whisper, CTC and HTDemucs models. Internet access is needed for their first download; processing runs locally after that. Model files are checked with SHA-256 and stored in the user data folder. Uninstall preserves settings and personal audio files.

## Validation and limits

Validation covered three CTest suites, the packaged app with a system-only PATH, installation/upgrade/uninstall of the real bundle, four float32 stems and synthetic Russian/English speech with Whisper Large. Word error rates on these short samples were 5.26% and 0%; maximum line-onset errors after accounting for the 45 ms lead were 50 and 70 ms. These results do not establish accuracy on arbitrary singing.

The release is not Authenticode-signed: a trusted publisher signature requires a publisher certificate. Recognition, vocal separation, denoising and genre inference can make mistakes; listen to and review the results. The standard build uses the CPU. An optional Whisper Vulkan build requires an SDK and compatible driver and has not been separately validated.
