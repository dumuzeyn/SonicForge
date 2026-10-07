# SonicForge 2.1

## Русский

Обновление обложек, распознавания текста песни и устойчивости обработки больших папок.

- **Свой стиль обложки:** современный органический рисунок или классический Music2Picture, палитра без программного ограничения количества цветов, добавление/редактирование/удаление цветов и изменение их порядка. Есть детализация, контраст, насыщенность, мягкость фона и предпросмотр.
- **Читаемые названия:** исправлено уменьшение надписей из-за коротких слов, включая «Im so sorry». Названия автоматически переносятся, исполнитель остаётся второстепенной надписью, фильтры фона не размывают текст.
- **Распознавание:** повторное использование декодированного аудио и загруженной модели, перепроверка сомнительных фрагментов. Неуверенный результат показывается для ручной проверки, а не выдаётся за отсутствие слов.
- **Устойчивость:** распознавание выполняется в отдельном процессе; ошибка одной песни не должна закрывать интерфейс или останавливать остальные файлы. Добавлены контроль доступной памяти, освобождение ресурсов, ограничение журнала и более подробные сообщения об ошибках.
- **Сохранность музыки:** обработка звука выключена по умолчанию и включается явно. Сохранение текста MP3 сохраняет звуковые байты, обложку и прочие теги; папки ранее созданных проектов исключаются из повторного обхода исходной коллекции.
- Обновлены русский и английский разделы руководства, скриншоты, справка и проверки приложения.

### Скачать

- **SonicForge-Setup-2.1.0.exe** — полный установщик Windows x64. Рекомендуется большинству пользователей.
- **SonicForge-2.1.0-windows-x64.zip** — портативная сборка. Распакуйте всю папку и запускайте SonicForge.exe вместе с каталогом _internal.
- **SHA256SUMS.txt** — контрольные суммы файлов.

Первое распознавание может потребовать загрузки речевой модели. Песни не отправляются на сервер распознавания. Проверяйте распознанные слова вручную: безошибочный результат не гарантируется.

Сохраните открытый проект перед установкой обновления. Условия некоммерческого и учебного использования собственного кода сохранены; сторонние компоненты сохраняют свои лицензии.

---

## English

An update to cover customization, lyric recognition and large-folder processing stability.

- **Custom artwork:** modern organic textures or classic Music2Picture, a palette without a software color-count cap, add/edit/remove controls and color ordering. Detail, contrast, saturation, background softness and preview are available.
- **Readable titles:** short words no longer force tiny lettering, including “Im so sorry”. Titles wrap automatically, artist credits stay secondary and background filters leave lettering sharp.
- **Recognition:** decoded audio and loaded speech weights are reused, and uncertain excerpts are rechecked. Uncertain results are shown for review rather than reported as missing lyrics.
- **Stability:** recognition runs in a separate process; one song's failure is contained instead of closing the interface or stopping the remaining files. Available-memory checks, resource recycling, bounded logs and clearer errors have been added.
- **Music preservation:** audio processing is off by default and must be selected explicitly. MP3 lyric saving preserves audio bytes, artwork and other tags; previously generated project folders are excluded from source-collection scans.
- Updated Russian/English documentation, screenshots, help and application checks.

### Downloads

- **SonicForge-Setup-2.1.0.exe** — complete Windows x64 installer, recommended for most users.
- **SonicForge-2.1.0-windows-x64.zip** — portable build. Extract the entire folder and keep SonicForge.exe with its _internal directory.
- **SHA256SUMS.txt** — download checksums.

First-time recognition may need a speech-weight download. Songs are not uploaded to a transcription server. Review recognized words manually; error-free transcription is not guaranteed.

Save open projects before updating. Noncommercial/educational terms for original code remain unchanged; third-party components retain their respective licenses.
