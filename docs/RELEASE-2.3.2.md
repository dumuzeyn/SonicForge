# SonicForge 2.3.2

## Русский

- Распознавание проверяет песню с `00:00` отрывками по 20 секунд, с перекрытием 6 секунд. Первую минуту и вступление не пропускает.
- На стыках сопоставляются слова и их время: одинаковое вхождение оставляется один раз, текст внутри слова не режется. Повторения в других местах песни сохраняются.
- Если отдельный отрывок не дал текста, допускается одна повторная попытка при заданном или уверенно определённом языке. Раньше повторялся только полностью пустой результат всей песни, поэтому найденный поздний припев не помогал восстановить начало.
- Перепроверка использует отрывки не длиннее 20 секунд; восстановление первой фразы работает и после минуты.
- Предположения в полной цифровой тишине отбрасываются. Тихое ненулевое пение не фильтруется порогом энергии. Подготовка вокала, таймкоды, отмена и защита существующего текста сохранены.

155 тестов прошли. Отделение вокала и распознавание проверены на реальных MP3.
Короткие отрывки и перекрытие не гарантируют правильность каждого слова; ASR
может ошибаться, особенно на тихом вокале и фоне музыки. Полная точность/WER
без проверенной расшифровки не измерена. [Метод и проверки](https://github.com/dumuzeyn/SonicForge/blob/v2.3.2/docs/LYRICS_TIMING_AND_VOCALS.md).

**SonicForge-Setup-2.3.2.exe** — установщик Windows x64;
**SonicForge-2.3.2-windows-x64.zip** — полная портативная папка.
Контрольные суммы: **SHA256SUMS.txt**.

## English

- Recognize from `00:00` using 20-second excerpts with 6-second overlap; retain the intro and first minute.
- Stitch timed words at overlap boundaries, keeping the same occurrence once without cutting word text. Preserve repetitions elsewhere in the song.
- Retry an empty excerpt once when language is explicitly selected or acoustically supported. Previously only an entirely empty song result was retried, so a recognized late chorus could leave the opening missing.
- Limit shifted verification excerpts to 20 seconds; recover a first phrase after one minute too.
- Reject guesses timed inside exact digital silence without imposing an energy threshold on quiet singing. Retain vocal preparation, original timing, cancellation and existing lyric protection.

155 tests passed, with real MP3 vocal/recognition checks. Short windows and overlap
do not guarantee word accuracy. Full accuracy/WER is not measured without an
independent transcript. [Method and checks](https://github.com/dumuzeyn/SonicForge/blob/v2.3.2/docs/LYRICS_TIMING_AND_VOCALS.md).

Downloads: **SonicForge-Setup-2.3.2.exe**, **SonicForge-2.3.2-windows-x64.zip**,
and **SHA256SUMS.txt**. Extract the entire portable folder.
