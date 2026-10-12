# Timed lyrics and vocal recognition

SonicForge 2.3.1 accepts pasted or imported UTF-8 TXT/LRC. Each timed lyric line
starts with `[mm:ss.xx]`, for example `[00:20.62]First line`. LRC supports repeated
timestamps, metadata headers and millisecond offsets. Invalid seconds, malformed
timestamps and mixed timed/untimed lines are rejected rather than silently lost.
The time field inserts/replaces the current line's timestamp; the cursor button
uses the audio editor's current position. This is manual line timing, not forced
word alignment. Automatic recognition supplies ASR segment start times.

Turning timestamp display off retains times when editing the same number of
nonempty lines. Changing the line count in plain mode drops timing: enter explicit
times again or save plain text. Plain lyrics never acquire invented zero times.
MP3 stores LRC text in ID3 USLT, as before; this does not produce SYLT frames and
some players will not treat USLT as synchronized lyrics. Other audio formats use
TXT/LRC sidecars. Import changes only the editor; Save is the explicit write action.
The Metadata tab's Keep lyrics unchanged option remains independent.
Automatic GUI and batch recognition preserve existing plain or timed lyrics
unless Overwrite lyrics is enabled. Save into song remains an explicit manual
replacement action; recognition can still display a new result for review.

## Audio path

The default path is original audio → bundled HTDemucs `htdemucs` vocal stem →
existing isolated faster-whisper `large-v3-turbo`, CPU int8 → existing acoustic
verification → reviewable lines. The existing separator processes bounded chunks
and runs in its own worker; it is not a frequency filter. The vocal option can be
disabled to recognize the original mix. Cancellation reaches separation and ASR.
Separation errors are reported; they never silently fall back to the mix.

No time trimming is performed, including during instrumental introductions.
The vocal duration must match the original within 50 ms. Only the latest vocal
stem is cached in an owned temporary directory, keyed by source path, size and
modification time; other stems are discarded. Repeating recognition of unchanged
audio reuses that stem. Closing the service removes the cache. The ASR worker is
reused under its existing bounded lifecycle. GUI and batch operations remain
background tasks. Files over 30 minutes are rejected by the current ASR limit.

HTDemucs is already distributed with SonicForge; this change introduces no new
weights. Demucs code and the original pretrained weights are distributed under
MIT ([upstream license](https://github.com/facebookresearch/demucs/blob/main/LICENSE),
[model instructions](https://github.com/facebookresearch/demucs#models)).
Whisper weights are MIT ([upstream](https://github.com/openai/whisper#license));
faster-whisper is MIT ([upstream](https://github.com/SYSTRAN/faster-whisper/blob/master/LICENSE)).
ASR weights still need the existing first-use download or a populated local cache.
Once present, these models work locally without a GPU or required connection.

## Reproducible check and limitations

`python tools/check_lyrics_vocals.py AUDIO --duration 45 --language ru --output validation/check/result.json`
performs read-only mix/vocals A/B recognition using the same ASR worker and checks
the original file's SHA-256 before and after. Use `--reference independently_checked.txt`
to additionally compute normalized word error rate; the reference is never passed
to recognition. Generated text and source-specific artifacts stay in ignored
`validation/` and are not published with the repository.

On the user-supplied 88.328-second MP3, a 45-second excerpt produced 2 segments /
39 characters from the mix (54.50 s including cold ASR loading), and 4 segments /
199 characters after separation (69.59 s including 37.25 s separation, with warm
ASR). The original hash matched. The mix included an apparent subtitle-credit
insertion; vocal recognition produced longer sung lines but still contains
suspect words. No independent checked transcript was supplied, so WER and an
accuracy improvement are **not measured**. Confidence scores are not word accuracy.
This single song is an integration check, not a general quality benchmark.

Separation costs extra CPU time and temporary disk space and can remove consonants
or harmonies. ASR may invent or mishear lyrics in either mode; review is required.
Do not use the larger amount of returned text or model confidence as proof of
correctness. The first mix run and warm vocal run are not equal-load speed benchmarks.

The full 88.328-second song was subsequently checked in both modes: mix 57.89 s,
17 segments / 591 characters; vocals 136.41 s (86.42 s preparing the vocal stem),
14 segments / 589 characters. The original hash again matched and all vocal
segment starts/ends were monotonic and within the song duration. This run overlapped
application packaging and is a functional timing observation, not an isolated
performance benchmark. Counts/confidence cannot establish which transcript is
more accurate; the reference limitation still applies. A reviewable LRC was saved
locally, without writing recognition into the original MP3.

Validation: 140 focused tests passed, covering LRC validation and round trips,
GUI import/edit/timing, actual service routing to the vocal stem, temporary cache
reuse/invalidation/cleanup, errors, timeline mismatch, cancellation, multi-song
batch routing, original tag preservation and the existing recognition tests.
The Windows bundle was checked for embedded vocal code and lyric controls; the
native EXE opened its main window and closed normally.
