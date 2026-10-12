# SonicForge 2.3.1

## Русский

- Импорт TXT/LRC и ручной ввод строк с таймкодами `[00:20.62]текст`.
- Показ/скрытие таймкодов, вставка времени в строку и вставка с курсора редактора.
- Перед распознаванием программа отделяет вокал существующей локальной моделью HTDemucs, затем запускает Whisper. Флажок позволяет сравнить результат с исходным миксом.
- Сохраняется начало песни и время вступления. Повторное распознавание использует временный кэш вокала; отмена работает на обоих этапах.
- Сохранение простого текста, ручное редактирование и защита текста в метаданных продолжают работать. Ошибочные LRC не сохраняются с потерей строк.
- Автоматическая обработка сохраняет существующий простой или синхронизированный текст без включённой перезаписи; ручная запись остаётся отдельным действием.

Проверено на реальном пользовательском MP3; оригинал не изменён. Без проверенной
расшифровки рост точности/WER не измерен. Разделение может как помочь, так и
ухудшить отдельные слова. Проверяйте результат перед сохранением. Распознавание
требует уже загруженных весов Whisper или их загрузки при первом использовании.
Подробности и воспроизводимая проверка: [документация](https://github.com/dumuzeyn/SonicForge/blob/v2.3.1/docs/LYRICS_TIMING_AND_VOCALS.md).

**SonicForge-Setup-2.3.1.exe** — установщик; **SonicForge-2.3.1-windows-x64.zip** —
портативная сборка. Распакуйте папку полностью. Контрольные суммы: **SHA256SUMS.txt**.

## English

- Import TXT/LRC and enter timestamped lines such as `[00:20.62]lyrics`.
- Show/hide timing, insert a line timestamp or use the audio editor cursor.
- Recognize the vocal stem separated by the existing local HTDemucs model, followed by Whisper. Disable vocal separation to compare recognition of the original mix.
- Preserve the full song timeline and intro. Reuse the latest temporary vocal stem; both processing stages support cancellation.
- Retain plain-text saving, manual editing and metadata lyric protection. Reject malformed or mixed LRC rather than losing lines.
- Preserve existing plain or timed lyrics during automatic processing unless overwrite is enabled; manual saving remains explicit.

Checked on a real user-provided MP3 with an unchanged original. Without an
independently checked transcript, accuracy improvement/WER is not measured.
Separation can help or damage particular words; review before saving. Whisper
requires existing cached weights or the existing first-use download.
See the [documentation](https://github.com/dumuzeyn/SonicForge/blob/v2.3.1/docs/LYRICS_TIMING_AND_VOCALS.md).

Download **SonicForge-Setup-2.3.1.exe** or extract the complete
**SonicForge-2.3.1-windows-x64.zip**. Checksums are in **SHA256SUMS.txt**.
