# SonicForge 3.2.1

- Metadata processing automatically selects the single highest-scoring genre, including low-confidence results. A manually entered value takes priority; alternatives remain in the log.
- A single-song edit retains the source filename in its output name and title metadata, including split clips and stems on separate tracks.
- Selecting a source folder now places the default `SonicForgeProgect` output beside that folder.
- M2Pv3 maps slow sections to blue/violet, medium sections to blue/green and fast sections to red. Colors follow local rhythm changes throughout the song.
- Tempo analysis now considers stable accents, spectral changes and transient decay. Frequent notes in a slow melody no longer automatically select double or triple tempo. Color and texture share the same rhythm estimate.

Validation includes all three CTest suites, the packaged application with a system-only PATH, and installation, upgrade and removal of the full payload while preserving user files. Regression cases cover slow melodies with frequent notes, fast drums over sustained chords, tempo changes, different volume levels and stationary noise. The tested recording of `Fallen Down` now has an estimated primary pulse of approximately 66 BPM.

## Downloads

- `SonicForge-Setup.exe` — Windows installer and updater for the current user.
- `SonicForge-Uninstall.exe` — launches the installed application's standard uninstaller.
- `SonicForge-windows-x64.zip` — portable package; extract it completely and run `SonicForge/SonicForge.exe`.
- `SHA256SUMS.txt` — SHA-256 checksums for the three files above.

Large Whisper, CTC and HTDemucs models are downloaded on demand and verified with SHA-256. The genre model is included. Release files are not Authenticode-signed because a publisher certificate has not been configured.
