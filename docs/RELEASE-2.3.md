# SonicForge 2.3

## Русский

Автоматическое определение жанра теперь анализирует музыкальное содержание
предобученной нейросетью MSD musicnn. В редакторе появился явный переключатель дорожки.

- Локальная ONNX-модель входит в сборку; интернет и видеокарта для определения жанров не нужны.
- Анализ нескольких участков песни, несколько подходящих жанров, альтернативы и баллы в журнале. При слабом результате жанр остаётся неопределённым.
- Убраны жанровые совпадения по имени файла, формулы BPM и принудительное назначение первого доступного жанра.
- Существующие пользовательские теги сохраняются без разрешения перезаписи. Ручное редактирование продолжает работать.
- В метаданных добавлен включённый по умолчанию флажок «Не трогать текст песни»: сохраняет встроенный текст, таймкоды и языковые метки при обновлении, полной перезаписи и очистке остальных тегов. Отдельные операции вкладки «Текст песни» управляются независимо.
- Anime, OST, Edit, Nightcore и Slowed показываются отдельно как контекст из имени.
- Ограниченное декодирование, повторное использование модели, фоновая пакетная обработка и отмена.
- Кнопка «Выключить дорожку» / «Включить дорожку», состояние в заголовке и Ctrl+M. Переключается вся дорожка выбранного клипа для прослушивания, экспорта и связанной обработки; Ctrl+Z отменяет действие.

Модель поддерживает Rock, Classic Rock, Pop, Electronic, House, Electro, Jazz,
Metal, Ambient и другие нативные теги. **Classical, Reggae, Techno и Drum and Bass
не поддерживаются автоматически**; их можно вводить вручную. Баллы не являются
калиброванными вероятностями, неизвестные стили могут распознаваться ошибочно.

На небольшой проверочной выборке из 32 фрагментов MagnaTagATune от разных
исполнителей Macro-F1 составил 0.605 против 0.076 старого алгоритма с одинаковым
списком жанров. Это диагностическое сравнение, а не гарантия качества на любой
библиотеке; полнота House, Metal и Folk остаётся низкой. Исходная модель и веса
взяты из оригинального репозитория musicnn с ISC, не из поставки Essentia.
Методика, метрики, ошибки и ограничения: [отчёт](https://github.com/dumuzeyn/SonicForge/blob/v2.3.0/docs/GENRE_CLASSIFICATION.md).

Загрузки: **SonicForge-Setup-2.3.0.exe** — установщик Windows x64;
**SonicForge-2.3.0-windows-x64.zip** — портативная сборка. Распакуйте папку целиком
и сохраняйте `_internal` рядом с SonicForge.exe. **SHA256SUMS.txt** содержит
контрольные суммы обоих файлов.

## English

Automatic genre detection now analyzes musical content with pretrained MSD musicnn.
The editor adds an explicit lane toggle.

- Bundled local ONNX model; genre analysis needs neither internet nor a GPU.
- Multiple song excerpts, multiple genres, alternatives and scores in the log. Weak results leave the genre undefined.
- Removed filename genre matching, BPM formulas and forced first-genre fallback.
- Existing user tags are retained unless overwrite is authorized; manual editing remains available.
- Metadata adds Keep lyrics unchanged, enabled by default: preserves embedded lyrics, timing and language tags when updating, replacing or clearing other metadata. Separate Lyrics-tab operations remain independent.
- Anime, OST, Edit, Nightcore and Slowed are separate filename context.
- Bounded decoding, model reuse, background batch processing and cancellation.
- Enable/disable track button, visible lane status and Ctrl+M. Toggles the selected clip’s entire lane for playback, export and linked processing; Ctrl+Z undoes it.

The model supports Rock, Classic Rock, Pop, Electronic, House, Electro, Jazz,
Metal, Ambient and other native tags. **Classical, Reggae, Techno and Drum and Bass
are not automatically supported** and remain available for manual input. Scores
are not calibrated probabilities; unfamiliar styles can be misclassified.

On a small test set of 32 MagnaTagATune excerpts from different artists, Macro-F1
was 0.605 versus 0.076 for the old algorithm with the same allowed genre list.
This diagnostic comparison does not establish quality across arbitrary music
libraries; House, Metal and Folk recall remains low. Original ISC musicnn weights
were independently exported to ONNX; Essentia distributions are not included.
See the [report](https://github.com/dumuzeyn/SonicForge/blob/v2.3.0/docs/GENRE_CLASSIFICATION.md)
for methodology, errors, measurements and limitations.

Downloads: **SonicForge-Setup-2.3.0.exe** is the Windows x64 installer;
**SonicForge-2.3.0-windows-x64.zip** is the portable build. Extract the complete
folder and retain `_internal` beside SonicForge.exe. **SHA256SUMS.txt** provides
checksums for both files.
