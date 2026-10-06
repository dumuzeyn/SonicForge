<p align="center"><img src="assets/sonic_forge_mark.png" width="120" alt="SonicForge application icon"></p>

# SonicForge 2.0 · Sound Forge

[Русское руководство](README.md) · [Download for Windows](https://github.com/dumuzeyn/SonicForge/releases/tag/v2.0.0) · [License](LICENSE)

A desktop application for audio editing, processing music copies, editing tags, transcribing lyrics and making cover art. Author: Зейналов У.Р.о. (Dumuzeyn).

## Install and start

1. Download **SonicForge-Setup-2.0.0.exe** from the release page and run it. This is the complete installer, not a standalone launcher missing its libraries.
2. Select an installation folder. The desktop shortcut is optional. Installation normally requires no administrator rights and is scoped to the current user.
3. Start SonicForge. The packaged application does not require a separate Python or FFmpeg installation for audio processing or artwork.
4. Open Settings to choose the interface language. Use the Help tab or F1 for instructions.

Windows x64; the build targets Windows 10/11. The installer registers Open with for MP3, WAV, FLAC, M4A, AAC, OGG, OPUS and WMA without changing default applications.

If a portable archive is attached, extract the **entire** archive and open **SonicForge/SonicForge.exe**. Keep **_internal** beside the executable.

## Two independent workflows

| Task | Workspace | Output action |
| --- | --- | --- |
| Arrange clips, edit multiple tracks, split and mix | Editor | Export… |
| Process audio, tags, lyrics and covers for a file or folder | Configure the relevant tabs, then Processing | Run |
| Hear an audio setting | Audio | Create comparison → Original / Processed |
| Inspect artwork | Cover art | Preview cover |
| Save manually corrected lyrics into the selected song | Lyrics | Save into song |

Editor tracks are not the batch source. Audio-tab settings do not affect Editor clips. A preview does not start Processing.

## Audio editor

![Two synthetic practice clips on separate tracks](docs/images/editor-en.png)

The screenshot uses synthetic practice audio, not a copyrighted commercial song. Both clips begin at zero; the red cursor is at 4 seconds and the selected range is 3–6 seconds.

### Importing and reading the timeline

Add audio accepts one or multiple files; each starts at zero on a **new** track. Dropping files from Explorer onto a lane places them around the drop position. Drop into New track to create another lane. Clips on one track cannot overlap: occupied space moves an incoming clip to the next free position to the right.

The horizontal axis is project time. Vertical grid marks align moments across tracks. The waveform shows an amplitude envelope: taller sections are generally louder, but it is **not a spectrum, lyric display or exact LUFS measurement**. Empty space contains no clips. Click a track number to toggle its sound; muted tracks are excluded from the mix.

| Tool | Function |
| --- | --- |
| Click a clip | Selects it and sets the red cursor for a split or playback start |
| Drag a clip | Moves it in time or to another track, without cutting it |
| Shift-drag | Selects time inside the selected clip |
| From, To, Select | Set clip-relative bounds in seconds, with 0.001-second steps |
| Start selection | Marks the cursor; Finish selection marks the end, including during playback |
| Zoom selection | Magnifies the selected range |
| −, +, Whole song | Adjust the view only; they do not alter sound or duration |
| Split | Cuts the selected clip at the cursor |
| Remove selection | Removes the selected range and joins the remaining parts without a gap, with up to 40 ms smoothing to reduce clicks |
| Duplicate | Adds a copy of the clip to the project |
| Remove clip | Removes a project clip, not the source file on disk |
| Undo, Redo | Navigate the project edit history |

The counter is current position / total project duration, not processing time remaining. Scrollbars move the timeline view. A highlighted range is a time selection, not a separate track.

### Selected clip inspector

| Field | Meaning |
| --- | --- |
| Start, End | Source-file bounds; hidden parts remain in the original |
| Position | Clip start on the project timeline |
| Track | Lane number, starting at 1 |
| Gain, dB | 0 is neutral, negative is quieter, positive is louder |
| Fade in / out, seconds | Smooth volume changes at the clip edges |
| Apply changes | Confirms inspector edits; typing numbers does not export audio |

Play prepares a temporary mix from the cursor. Stop stops playback. Cancel task requests cancellation of the current Editor background operation. Waveforms, previews and exports are prepared outside the main interface loop.

### Vocals, drafts and export

Vocals and instruments offers vocals + accompaniment or vocals + drums + bass + other. The selected clip is replaced by component clips on separate lanes at a common position. One Undo restores the original clip. Separation uses a local worker, may take minutes and can leave bleed or artifacts; it cannot guarantee original studio stems. Stem WAVs are kept in the user's SonicForge/editor-stems folder.

The Draft menu saves/opens **.sfproject** files containing source paths and edits, **not embedded audio**. Keep referenced media in place. Export… writes a new WAV, MP3 or M4A from enabled tracks, using 44.1 kHz, stereo and peak limiting. Existing destinations and source files cannot be overwritten.

| Shortcut | Action |
| --- | --- |
| Ctrl+I | Add audio |
| Ctrl+K | Split at cursor |
| Ctrl+Shift+X | Remove selection |
| Ctrl+D / Delete | Duplicate / remove clip |
| Ctrl+Z / Ctrl+Y or Ctrl+Shift+Z | Undo / redo |
| Ctrl+S / Ctrl+O / Ctrl+E | Save draft / open draft / export |
| Ctrl+Shift+V / Ctrl+Shift+B | Separate into 2 / 4 components |
| Space on timeline / Esc | Play toggle / stop and cancel unfinished selection or task |

Russian keyboard layout is supported. Text fields retain their normal text-editing shortcuts.

## Batch source and destination

Batch-tool tabs share Source and destination at the top.

- File selects one song; Folder selects a directory of supported files.
- Output folder and Choose control where finished copies are written.
- The default is a sibling **SonicForgeProgect** folder; its spelling is retained for compatibility: C:\Music\Album → C:\Music\SonicForgeProgect.
- Finished projects and working folders are excluded from repeated traversal. Selecting a source does not analyze it.
- Source and output must differ. Processing works on staged copies and retains originals.

An intentional exception is Save into song in the Lyrics workspace: it changes lyric tags in the **selected MP3**. Work on a copy if you want to preserve its old lyrics.

## Metadata

![Main metadata fields filled for a practice recording](docs/images/metadata-en.png)

Tags describe a file; they are not its filename and do not modify its waveform. Fill fields, then enable Metadata in Processing.

| Field | Purpose |
| --- | --- |
| Title | Track title; processing can fall back to the filename |
| Artist | Performer of the individual track |
| Album | Release title |
| Album artist | Overall release performer, which can differ from track artist |
| Composer | Music composer |
| Genre | Genre tag; automatic suggestions are heuristic, not authoritative |
| Year / date | For example 2026 |
| Track number | For example 3 or 3/12 |
| Comment | Plain tag, not an artwork-generation instruction |
| Additional fields | Disc number, publisher, copyright and an additional lyric text tag |

Actions can read the selected file's tags, open additional fields or create a copy without metadata. Normal updates retain old values for empty additional fields. Overwrite genre permits replacing an existing genre. Overwrite all metadata removes old tags and retains only values being written: check this carefully. Use Lyrics for synchronized lines.

## Audio: profiles, sliders and comparison

![Audio profiles, smooth sliders and actual processing values](docs/images/audio-en.png)

1. Select one source file.
2. Choose the desired profile and strength.
3. Optionally Analyze, then Apply recommendation separately.
4. Create comparison, then switch between Original and Processed.
5. To save a finished copy, enable Audio in Processing and Run.

Analyze measures loudness, dynamics, frequency balance and signs of stationary noise without writing files. Recommendations do not apply themselves. Comparison prepares temporary excerpts, approximately up to 25 seconds, matched in perceived loudness so you can assess tone instead of just preferring the louder version. Recreate comparison after changing settings.

| Control | Effect |
| --- | --- |
| Balanced | Neutral macros with automatic noise checks |
| Preserve character | Neutral tone and no automatic denoising; normalization still applies |
| Louder and denser | Higher target loudness, compression and slight bass/treble accents |
| Clean sound | Automatic noise checks and a small treble adjustment |
| More bass / Brighter and clearer / Wider | Emphasize bass, treble or stereo width respectively |
| Custom | Manually adjusted macro sliders |
| Profile strength | Scales macro changes; **0% is not full bypass**: normalization and independently enabled effects remain |
| Loudness | Target integrated LUFS, not speaker playback volume |
| Character | Treble boost/cut |
| Bass | Low-frequency boost/cut |
| Space | Stereo-width adjustment, not real spatial detail from mono |
| Automatically remove noticeable noise | Applies cleanup only when stationary-noise indicators are detected |
| Protect against clipping | Limits peaks; cannot repair distortion already recorded |

Slider percentages are relative adjustments, not a spectrum. Exactly what changes reports **actual** LUFS, dB, dBTP, width and enabled effects. LUFS closer to zero is louder; 0 dB EQ is neutral; ×1.00 width/gain is unchanged. Warnings and recommendations are not guarantees.

### Advanced audio: enhancement

![Normalization, EQ and frequency-cut settings](docs/images/audio-advanced-en.png)

Scroll down in this window for noise, compressor and output options.

| Parameter | Meaning |
| --- | --- |
| Integrated loudness, LUFS | Normalization target, default −14; maximum loudness is not necessary |
| True-peak limit, dBTP | Peak target, default −1.5 |
| Loudness range, LU | Target dynamics, default 11; lower suggests steadier volume, not an exact guaranteed measured LRA |
| Final gain | Post-normalization multiplier, default 1; increasing it can drive the limiter |
| Bass / mid / treble, dB | Shelves around 110 and 7200 Hz and a mid EQ around 1100 Hz; 0 is neutral; reset returns neutral gain |
| Stereo width | 0–2, original width 1; excessive widening can harm mono compatibility |
| Low cut / high cut, Hz | High-pass removes frequencies below its cutoff, low-pass above; values act only when enabled |
| Denoising | Off, automatic or manual; excessive reduction can introduce artifacts |
| Compressor | Reduces the loud/quiet difference; does not remove noise |
| Threshold, dB | Level where compression starts |
| Ratio | Greater ratios reduce exceedances more strongly: 3:1 is stronger than 1.5:1 |
| Attack / release, ms | How quickly compression engages and relaxes; milliseconds, not seconds |
| Makeup, dB | Gain following compression |
| Sample rate | As source, 44.1 or 48 kHz; unsupported MP3 rates use the nearest valid rate |
| Channels | As source, mono or stereo; duplicating mono does not create spatial information |
| MP3 quality | Maximum (VBR q0), high (VBR q2), medium (192 kbit/s); higher bitrate cannot recover lost information |

Precise values survive comparison and processing. Choosing a new profile or moving macros intentionally recalculates related parameters; check the summary afterward.

### Tempo and effects

![The selected Tempo and effects page](docs/images/audio-effects-en.png)

| Parameter | Usage |
| --- | --- |
| Pitch, semitones | 0 is original; +12 / −12 is an octave up/down with duration compensation |
| Speed | 1 is original; 1.1 is faster, 0.9 slower; tempo changes while preserving pitch |
| Reverb | 0 is off; implemented as short echoes/reflections, not a full concert-hall simulation |
| Fade in / out, seconds | Gradual volume change over the specified time; use durations shorter than the recording |

Done closes the window. These settings affect batch audio, not Editor clips.

## Cover art: generated or your own image

![Artwork preview and the custom-image button](docs/images/cover-en.png)

Music2Picture analyzes audio and draws procedural abstract artwork locally. Spectrum, rhythm, harmony and structural features influence palette, density, curvature, grain and composition. It is an artistic interpretation, **not a scientific spectrum plot or a literal picture of the song's story**.

| Control | Function |
| --- | --- |
| Style | One of five pattern/palette combinations |
| Seed | Integer variation; matching source, settings and version help reproduce a pattern |
| Size, px | Square output side; upscaling does not add real detail to a supplied photograph |
| Lyrics for cover | Uses available lyrics to influence mood/colors; disabling excludes them from analysis |
| Title | Centered lettering from tags or filename |
| Artist | Extra lettering when title is enabled |
| Embed in file | Inserts artwork into output audio during the cover stage |
| Do not change cover | Retains existing artwork instead of replacing it |
| Preview cover | Displays a smaller version without changing the source |
| Choose your image | PNG, JPEG or WebP; validates and fits it to the requested square |
| Use generation | Switches back after choosing a custom image |

Styles: modern artwork; modern artwork with classic colors; a 50/50 blend; classic pattern with modern colors; classic Music2Picture. The classic variant uses a [pinned Music2Picture revision](https://github.com/dumuzeyn/Music2Picture/tree/342013aaa8bdb4cb86c8c14fec0acb038e50b5ca).

Mood is handled internally; the current window has no manual scene-description field. A custom image replaces generation and does not use generator-specific controls. Its original is unchanged. Processing saves a full PNG in covers and embeds it if enabled. A preview does not mean the song already contains the picture.

## Lyrics

![Practice lyrics entered manually, not a recognition result](docs/images/lyrics-en.png)

1. Select one file in Source.
2. Load existing reads tags or a neighboring TXT/LRC without recognition.
3. Recognize starts local transcription; lines appear as they are processed.
4. Review words manually. Double-click selects a Unicode word, including internal apostrophes/hyphens. Ctrl+A/C/X/V/Z also work with a Russian keyboard layout.
5. Save the corrected text using Save into song / the save button.

| Setting | Meaning |
| --- | --- |
| Auto | Russian and English stay native; other languages default to Russian sound spelling |
| Russian / English | Forces the recognition language |
| Other → English / Russian letters | Chooses an approximate sound-spelling alphabet |
| MP3 format | ID3 USLT inside the song; timed lines can use [mm:ss.xx] |
| TXT for other formats | Plain text beside the output file |
| LRC for other formats | Timestamped lines; precise timings cannot be reconstructed from untimed manual text |
| Overwrite lyrics | Allows batch processing to replace existing lyrics |
| Lyrics for cover | Uses available/reviewed lyrics for artwork |

Sound spelling is **not translation** or guaranteed exact phonetics. Ambiguous pronunciation, uncertain language and mixed-language songs require review. Language probability is not word accuracy.

Recognition uses faster-whisper with large-v3-turbo. First use needs a network download of roughly 1.6 GB; later runs use the local cache. Georgian acoustic recognition may require an additional roughly 1.6 GB download. The local language classifier and stem worker are bundled. Opening the app does not start these tools or load speech weights into memory. Audio is not uploaded to a transcription server.

Uncertain introductions and words are rechecked in shifted excerpts; repeated choruses can help verify weak words. This reduces spurious insertions but cannot guarantee error-free lyrics. CPU processing can take minutes. Uncertain results request review instead of being labeled automatically correct.

MP3 saving updates lyric ID3 frames while retaining MPEG audio bytes, artwork and unrelated frames. Normal ID3v2.3/v2.4 tags are supported; complex or damaged headers are rejected for writing rather than risking unrelated tags. Untimed manual lines do not receive invented timestamps. Timestamped USLT is not standard SYLT, and not every player displays it in sync.

## Processing: write finished copies

![Selected stages and separate lyric progress](docs/images/processing-en.png)

1. Check source and destination.
2. Enable only needed stages: Audio, Metadata, Lyrics, Cover.
3. Configure those tabs. Editor edits are not a Processing stage.
4. Run, wait for completion and inspect the log.
5. Open the output folder, listen and check tags.

Processing uses a temporary staging folder and publishes completed results after the selected stages. Originals are retained. The audio stage converts outputs to MP3; without it, source-format copies are prepared for other stages. Cover PNGs are kept separately in covers.

The moving top indicator means the application is working; **it is not an exact percentage or remaining-time prediction**. The lyric block distinguishes preparation, loading, language detection, transcription, verification and saving. Recognition progress is approximately based on processed audio time. Final counts distinguish newly saved lyrics, preserved existing text, items needing review and failures. Needs review does not mean correct lyrics were already embedded.

Stop requests cancellation. Completed actions are not automatically undone: inspect the log and output folder. Copy log copies visible messages; Clear log clears the display, not files.

## Help and settings

![Help instructions and parameter/action explanations](docs/images/help-en.png)

Help shows instructions for a selected topic. F1 opens a separate help window for the current tool. Right-click a control to show its explanation; right-click again to dismiss it. Tips do not depend on accidental hovering.

![Language, transparent splash preference and project buttons](docs/images/settings-en.png)

Settings switches Russian/English immediately while keeping the project and entered values. This is **not lyric-recognition language**. The loading-screen preference applies to future launches. The transparent splash uses the application icon.

Project buttons open the repository and author-support page in an external browser only when clicked. Raw addresses do not occupy the interface. Author support is a **voluntary donation**: it unlocks no features and does not alter access to tools.

## Safety and limitations

Only declared audio formats and PNG/JPEG/WebP custom images are accepted. Local regular-file type, extension and signatures are checked; links and devices are rejected. Images have 50 MB and 50-million-pixel limits and undergo structural verification. External tools receive separate argument lists without a command shell. Media is not executed as software.

These measures reduce risks, not eliminate them. Use trusted media, retain backups and keep decoders current. Only process music and images you have permission to use; the app grants no rights to other people's songs.

Troubleshooting:

- No waveform: wait for background reading and inspect any error.
- Comparison playback disabled: Create comparison for one file first.
- Preview did not change the song: expected; use Processing for a copy.
- Missing draft audio: restore the original media at its saved paths.
- Wrong lyrics/language: choose language manually and review words; an estimate is not a guarantee.
- Old sound after editing settings: recreate comparison.
- EXE fails after being moved: keep the whole portable folder or use the installer.

## Source, tests and building

Source runs need Python 3.12 and FFmpeg on PATH:

~~~powershell
python -m pip install -r requirements.txt
python music_polisher_gui.py
~~~

Tests:

~~~powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests
~~~

Windows packaging also requires Inno Setup 6. The current profile expects FFmpeg in C:\ffmpeg with its LICENSE and README. The CPU stem worker is built in an isolated environment:

~~~powershell
.\build_windows.ps1
~~~

Outputs: dist\SonicForge\SonicForge.exe with _internal, and **dist\SonicForge-Setup-2.0.0.exe**. The build script does not forcibly close an open portable project. Build directories, local validation, caches and binary releases are excluded from source commits.

Command-line tools: easy_music_process.py for full processing; music2picture.py covers / describe for artwork/descriptions; music_metadata.py for tags. Use --help for arguments and test file-changing operations on copies.

scripts/capture_readme_screenshots.py reproduces the screenshots using a separate test window, synthetic audio and original practice text. It does not open user projects or run speech recognition.

## License and author

Original code, artwork and documentation use the [SonicForge Noncommercial and Educational License](LICENSE). Personal noncommercial use, study, learning, modification and noncommercial redistribution with the license retained are permitted. Commercial use requires the author's prior written permission. This is a source-available license with restrictions, not unrestricted open source.

Third-party components retain their own licenses and rights; SonicForge's restriction does not extend to them. See [component notices](THIRD_PARTY_NOTICES.md). Author: **Зейналов У.Р.о. / Dumuzeyn**.
