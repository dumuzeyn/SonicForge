"""Independent editor tab. Workers never call Tk; timeline edits never touch files."""
import copy
import math
from pathlib import Path
import queue
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinterdnd2 import DND_FILES, COPY, REFUSE_DROP
from PIL import Image, ImageTk

from audio_editor import Cancelled, Timeline, read_waveform, render, remove_audio_selection
from .theme import COLORS, FONTS, TRACK_COLORS
from .widgets import RoundedButton, RoundedMenuButton, ThemedMenu, ToolTip


TEXT = {
    "ru": {
        "title": "Аудиоредактор", "intro": "Соберите звук на дорожках. Оригиналы не меняются; результат сохраняется отдельно.",
        "add": "＋ Добавить аудио", "undo": "↶ Отмена", "redo": "↷ Повтор", "draft": "Черновик ▾",
        "open_draft": "Открыть черновик…", "save_draft": "Сохранить черновик…",
        "new": "Новый проект", "new_confirm": "Начать новый проект? Сохраните черновик, если хотите вернуться к правкам.",
        "play": "▶ Прослушать", "stop": "■ Стоп", "export": "Экспорт…", "cancel": "Отменить задачу",
        "split": "Разделить", "duplicate": "Дублировать", "delete": "Удалить фрагмент",
        "fit": "Вся песня", "zoom": "Масштаб", "lane": "Дорожка", "mute": "Без звука",
        "start": "Начало, с", "end": "Конец, с", "position": "Позиция, с",
        "gain": "Громкость, dB", "fade_in": "Появление, с", "fade_out": "Затухание, с",
        "apply": "Применить правки", "selection": "Фрагмент",
        "bounds": "Границы в исходнике", "placement": "Положение в проекте", "sound": "Звук фрагмента",
        "range_title": "Выделение", "range_start": "От, с", "range_end": "До, с",
        "set_range": "Выделить", "zoom_range": "К выделению", "length": "Длина: {value:.3f} с",
        "begin_range": "Начать выделение", "finish_range": "Завершить выделение",
        "cursor_range_error": "Курсор должен находиться внутри выбранного фрагмента.",
        "cursor_range_tip": "Первое нажатие отмечает текущую позицию красного курсора, второе — конец выделения. Работает во время прослушивания; можно также переместить курсор вручную. Esc отменяет незавершённый выбор. Звук не меняется.",
        "range_error": "Укажите начало и конец внутри фрагмента; длина выделения — не менее 0,010 с.",
        "set_range_tip": "Время от начала выбранного фрагмента, а не исходного файла или проекта. Шаг стрелок — 1 мс. «Выделить» подтверждает границы; звук не меняется до «Удалить выделение».",
        "zoom_range_tip": "Приближает выделенный участок для точной проверки границ. «Вся песня» возвращает общий вид.",
        "empty": "Нет аудио",
        "drop_invalid": "Перетащите аудиофайлы, а не папки или другие документы.",
        "new_lane": "Новая дорожка",
        "stems": "Вокал и инструменты", "stems_two": "Вокал + инструментарий",
        "stems_four": "Вокал / ударные / бас / остальное", "separating": "Разделяю на составляющие…",
        "stem_progress": "Разделение: {value:.0f}%",
        "stems_tip": "Разделяет выбранный фрагмент локально на 2 или 4 составляющие и заменяет его отдельными дорожками. Можно отменить. Исходник не меняется. Обработка может занять несколько минут; возможны остаточные примеси звуков.",
        "hint": "Щелчок — курсор и выбор • Потяните фрагмент — перенос • Shift + потяните — диапазон обрезки",
        "timeline": "Шкала и фрагменты",
        "shortcuts": "Горячие клавиши",
        "shortcuts_tip": "Ctrl+I — добавить аудио; Ctrl+K — разделить; Ctrl+Shift+X — обрезать выделение; Ctrl+D — дублировать; Delete — удалить фрагмент; Ctrl+Z — отменить; Ctrl+Y / Ctrl+Shift+Z — повторить; Ctrl+S / Ctrl+O — сохранить / открыть черновик; Ctrl+E — экспорт. Ctrl+Shift+V — вокал и инструментарий; Ctrl+Shift+B — четыре составляющие. На шкале: пробел — прослушать / остановить, Esc — остановить и отменить задачу. Сочетания работают в русской и английской раскладках; в полях остаётся обычное редактирование текста.",
        "trim": "Удалить выделение", "ready": "Готово", "importing": "Читаю аудио и строю волну…",
        "cutting": "Удаляю выделение и сглаживаю стык…",
        "rendering": "Собираю звук…", "saved": "Сохранено: {path}", "playing": "Воспроизведение: {time}",
        "stopped": "Остановлено", "error": "Не удалось завершить: {error}",
        "preview": "Прослушивание начинается с курсора. Первый запуск собирает звук в фоне; повторный использует готовую копию.",
        "export_tip": "Смешивает включённые дорожки в новый WAV, MP3 или M4A. Общий лимитер защищает от перегруза. Не относится к «Выполнению».",
        "add_tip": "Добавляет каждую песню на отдельную дорожку с начала шкалы. Перетащите файл на нужное место шкалы для точного размещения. Исходники не изменяются.",
        "draft_tip": "Черновик хранит пути и правки, не копии аудио. Исходные файлы должны оставаться на месте.",
        "split_tip": "Разрезает выбранный фрагмент в позиции курсора. Исходный файл остаётся целым.",
        "duplicate_tip": "Создаёт копию выбранного фрагмента сразу после него на той же дорожке.",
        "delete_tip": "Удаляет только фрагмент из проекта. Файл на диске не удаляется. Можно отменить.",
        "trim_tip": "Удаляет из выбранного фрагмента диапазон, выделенный Shift + перетаскиванием, и соединяет оставшиеся части без паузы. Короткий перекрёстный переход до 40 мс уменьшает щелчки. Музыкальный переход зависит от места разреза. Остальные фрагменты и исходный файл не меняются. Можно отменить.",
        "lane_tip": "Выбор дорожки для нового файла или переноса выбранного фрагмента. Отключённая дорожка не звучит и не экспортируется.",
        "start_tip": "Откуда брать звук в исходном файле, в секундах. Для обрезки увеличьте начало или уменьшите конец.",
        "end_tip": "Где закончить звук в исходном файле. Должно быть позже начала и не длиннее оригинала.",
        "position_tip": "Когда фрагмент начинается в проекте. Фрагменты на разных дорожках могут звучать одновременно.",
        "gain_tip": "0 dB — исходная громкость; +6 dB — примерно вдвое больше амплитуда, −6 dB — вдвое меньше. Не нормализация.",
        "fade_in_tip": "Плавный рост от тишины до громкости фрагмента. 0 отключает. Время не длиннее фрагмента.",
        "fade_out_tip": "Плавное затухание в конце фрагмента. 0 отключает. Время не длиннее фрагмента.",
        "apply_tip": "Применяет поля к выбранному фрагменту. Изменения слышны в следующем прослушивании и экспорте.",
        "undo_tip": "Отменяет последнюю правку проекта, включая удаление и выключение дорожки. Не отменяет экспорт файла.",
        "redo_tip": "Возвращает отменённую правку. Новая правка очищает историю повтора.",
        "fit_tip": "Показывает всю длительность проекта. Масштаб меняет только отображение, не звук.",
        "stop_tip": "Останавливает прослушивание. Не меняет фрагменты или файлы.",
        "cancel_tip": "Прерывает чтение или сборку аудио. Незавершённый выходной файл удаляется.",
    },
    "en": {
        "title": "Audio editor", "intro": "Arrange audio on lanes. Originals stay intact; export creates a separate file.",
        "add": "＋ Add audio", "undo": "↶ Undo", "redo": "↷ Redo", "draft": "Draft ▾",
        "open_draft": "Open draft…", "save_draft": "Save draft…", "new": "New project",
        "new_confirm": "Start a new project? Save a draft first if you want to return to these edits.",
        "play": "▶ Listen", "stop": "■ Stop", "export": "Export…", "cancel": "Cancel task",
        "split": "Split", "duplicate": "Duplicate", "delete": "Remove clip", "fit": "Fit song", "zoom": "Zoom",
        "lane": "Lane", "mute": "Mute", "start": "Start, s", "end": "End, s",
        "position": "Position, s", "gain": "Volume, dB", "fade_in": "Fade in, s", "fade_out": "Fade out, s",
        "apply": "Apply edits", "selection": "Clip",
        "bounds": "Source boundaries", "placement": "Project placement", "sound": "Clip sound",
        "range_title": "Selection", "range_start": "From, s", "range_end": "To, s",
        "set_range": "Select", "zoom_range": "Zoom selection", "length": "Length: {value:.3f} s",
        "begin_range": "Start selection", "finish_range": "Finish selection",
        "cursor_range_error": "Place the cursor inside the selected clip.",
        "cursor_range_tip": "First click marks the red cursor's current position, second click marks the selection end. Works during playback or with manual cursor movement. Esc cancels the unfinished selection. Audio stays intact.",
        "range_error": "Enter start and end within the clip; selection must be at least 0.010 s long.",
        "set_range_tip": "Times relative to the selected clip, not the source file or project. Arrow step: 1 ms. Select confirms the range; audio stays intact until Remove selection.",
        "zoom_range_tip": "Zooms into the selected range to check its boundaries. Fit song restores the full view.",
        "empty": "No audio",
        "drop_invalid": "Drop audio files, not folders or other documents.",
        "new_lane": "New lane",
        "stems": "Vocals and instruments", "stems_two": "Vocals + instrumental",
        "stems_four": "Vocals / drums / bass / other", "separating": "Separating components…",
        "stem_progress": "Separation: {value:.0f}%",
        "stems_tip": "Locally separates the selected clip into 2 or 4 components and replaces it with separate lanes. Undo is available. Originals stay intact. May take minutes; residual audio bleed is possible.",
        "hint": "Click: cursor / selection • Drag clip: move • Shift + drag: trim range",
        "timeline": "Timeline and clips",
        "shortcuts": "Keyboard shortcuts",
        "shortcuts_tip": "Ctrl+I: add audio; Ctrl+K: split; Ctrl+Shift+X: trim selection; Ctrl+D: duplicate; Delete: remove clip; Ctrl+Z: undo; Ctrl+Y / Ctrl+Shift+Z: redo; Ctrl+S / Ctrl+O: save / open draft; Ctrl+E: export. Ctrl+Shift+V: vocals and instrumental; Ctrl+Shift+B: four components. On the timeline: Space to play / stop, Esc to stop and cancel the task. Shortcuts work in Russian and English layouts; input fields retain normal text editing.",
        "trim": "Remove selection", "ready": "Ready", "importing": "Reading audio and building waveform…",
        "cutting": "Removing selection and smoothing the join…",
        "rendering": "Rendering audio…", "saved": "Saved: {path}", "playing": "Playing: {time}",
        "stopped": "Stopped", "error": "Could not finish: {error}",
        "preview": "Playback starts at the cursor. First playback renders in the background; repeats reuse the cached mix.",
        "export_tip": "Mixes unmuted lanes into a new WAV, MP3 or M4A. A final limiter protects peaks. Independent of Processing.",
        "add_tip": "Adds each song to a separate lane at the start of the timeline. Drop a file onto a specific timeline position for precise placement. Originals stay intact.",
        "draft_tip": "Drafts store paths and edits, not audio copies. Keep the original files in place.",
        "split_tip": "Splits the selected clip at the cursor without changing its source file.",
        "duplicate_tip": "Copies the selected clip immediately after it on the same lane.",
        "delete_tip": "Removes a clip from the project only, not its source file. Undo is available.",
        "trim_tip": "Removes the Shift-drag range from the selected clip and joins the remaining parts without a gap. A short crossfade of up to 40 ms reduces clicks. Musical continuity depends on the cut position. Other clips and the source file remain unchanged. Undo is available.",
        "lane_tip": "Lane for imports or moving the selected clip. Muted lanes are excluded from playback and export.",
        "start_tip": "Starting time in the source file. Increase start or decrease end to trim.",
        "end_tip": "Ending time in the source file, after the start and within the original duration.",
        "position_tip": "Starting time on the project timeline. Different lanes can play simultaneously.",
        "gain_tip": "0 dB keeps original volume. +6 dB roughly doubles amplitude; −6 dB halves it. Not normalization.",
        "fade_in_tip": "Gradual volume rise from silence. 0 disables. Must fit within the clip.",
        "fade_out_tip": "Gradual volume drop at the end. 0 disables. Must fit within the clip.",
        "apply_tip": "Updates the selected clip. Edits affect the next playback and export.",
        "undo_tip": "Undoes a timeline change, including removal or mute. Does not undo exported files.",
        "redo_tip": "Restores an undone edit. A new edit clears redo history.",
        "fit_tip": "Displays the full project. Zoom affects display only, not audio.",
        "stop_tip": "Stops playback without changing clips or files.",
        "cancel_tip": "Cancels decoding or rendering and removes incomplete output.",
    },
}


TEXT['ru']['export_tip'] = 'Смешивает включённые дорожки в новый WAV, MP3 или M4A. Экспорт доступен в обоих режимах; при связанной обработке вручную экспортировать не нужно.'
TEXT['en']['export_tip'] = 'Mixes unmuted lanes into a new WAV, MP3 or M4A. Export works in either mode; linked processing needs no manual export.'


def clock(seconds):
    return f"{int(seconds) // 60:02d}:{seconds % 60:05.2f}"


class AudioEditor(ttk.Frame):
    def __init__(self, parent, app, header_parent=None):
        super().__init__(parent, style="Surface.TFrame")
        self.app = app
        self.header_parent = header_parent
        self.project = Timeline()
        self.selected = None
        self.cursor = 0
        self.range = None
        self._range_clip_id = None
        self._cursor_selection = None
        self.zoom = 1
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.worker = None
        self._task_active = False
        self._pipeline_busy = False
        self._after = None
        self._draw_after = None
        self._play_after = None
        self._playing = False
        self._preview_cache = None
        self._drag = None
        self._drag_preview = None
        self.localized = []
        self.controls = []
        self.tips = []
        self.fields = {}
        self.inspector_controls = []
        self.selection_controls = []
        self.selection_fields = {key: tk.StringVar(value="0.000") for key in ('start', 'end')}
        self._selection_clip = None
        self.selection_length = tk.StringVar(value="—")
        self.clip_length = tk.StringVar(value="—")
        self.lane = tk.IntVar(value=1)
        self.status = tk.StringVar(value=self.tr("ready"))
        self.selected_text = tk.StringVar(value=self.tr("selection"))
        self.counter = tk.StringVar(value="00:00.00 / 00:00.00")
        self._temp = None  # No filesystem work until the first preview.
        self._build()
        # Tk Entry/Canvas class handlers can consume Control keys before the
        # toplevel binding sees them. Route editor actions before those classes.
        self._shortcut_tag = 'SonicForgeEditor:' + self._w
        self.app.bind_class(self._shortcut_tag, '<KeyPress>', self._shortcut)
        def bind_editor(widget):
            widget.bindtags((self._shortcut_tag, *widget.bindtags()))
            for child in widget.winfo_children():
                bind_editor(child)
        bind_editor(self)
        if self.header_parent is not None:
            bind_editor(self.header_parent)
        self._shortcut_binding = self.app.bind('<KeyPress>', self._shortcut, add='+')
        self.bind("<Destroy>", self._on_destroy, add="+")

    def tr(self, key):
        return TEXT[self.app.language][key]

    def label(self, parent, key, **kwargs):
        widget = ttk.Label(parent, text=self.tr(key), **kwargs)
        self.localized.append((widget, key))
        return widget

    def tip(self, widget, key):
        title_key = 'play' if key == 'preview' else ('timeline' if key == 'hint' else key.removesuffix('_tip'))
        shortcuts = {'add_tip': 'Ctrl+I', 'split_tip': 'Ctrl+K', 'trim_tip': 'Ctrl+Shift+X',
                     'duplicate_tip': 'Ctrl+D', 'delete_tip': 'Delete', 'undo_tip': 'Ctrl+Z',
                     'redo_tip': 'Ctrl+Y / Ctrl+Shift+Z', 'export_tip': 'Ctrl+E',
                     'stems_tip': 'Ctrl+Shift+V / Ctrl+Shift+B', 'preview': 'Space',
                     'draft_tip': 'Ctrl+S / Ctrl+O'}
        suffix = '\n\n' + shortcuts[key] if key in shortcuts else ''
        self.tips.append(ToolTip(widget, lambda: self.tr(key) + suffix,
                                title_provider=lambda: TEXT[self.app.language].get(title_key, self.tr('title'))))
        return widget

    def button(self, parent, key, command, primary=False, tip=None):
        button = RoundedButton(parent, text=self.tr(key), command=command, primary=primary)
        self.localized.append((button, key))
        self.controls.append(button)
        self.tip(button, tip or key + "_tip")
        return button

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        header = self.header_parent if self.header_parent is not None else self
        header.columnconfigure(0, weight=1)
        self.label(header, "title", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        toolbar = ttk.Frame(header, style="Surface.TFrame")
        toolbar.grid(row=2, column=0, sticky="ew", pady=(6, 4))
        self.button(toolbar, "add", self.choose_audio, True).pack(side=tk.LEFT, padx=(0, 12))
        self.undo_button = self.button(toolbar, "undo", lambda: self.history(False))
        self.undo_button.pack(side=tk.LEFT, padx=(0, 4))
        self.redo_button = self.button(toolbar, "redo", lambda: self.history(True))
        self.redo_button.pack(side=tk.LEFT)
        self.stems_button = RoundedMenuButton(toolbar, text=self.tr('stems'))
        self.stems_button.pack(side=tk.LEFT, padx=(12, 0))
        self.controls.append(self.stems_button)
        self.localized.append((self.stems_button, 'stems'))
        self.tip(self.stems_button, 'stems_tip')
        self.stems_menu = ThemedMenu(self.stems_button, tearoff=False)
        self.stems_button.configure(menu=self.stems_menu)
        for mode, key in (('two', 'stems_two'), ('four', 'stems_four')):
            self.stems_menu.add_command(label=self.tr(key), accelerator='Ctrl+Shift+' + ('V' if mode == 'two' else 'B'),
                                        command=lambda selected=mode: self.separate_stems(selected))
        draft = RoundedMenuButton(toolbar, text=self.tr("draft"))
        draft.pack(side=tk.RIGHT)
        self.controls.append(draft)
        self.localized.append((draft, "draft"))
        self.tip(draft, "draft_tip")
        self.menu = ThemedMenu(draft, tearoff=False)
        draft.configure(menu=self.menu)
        for key, command in (("new", self.new), ("open_draft", self.open_draft), ("save_draft", self.save_draft)):
            self.menu.add_command(label=self.tr(key), command=command)

        canvas_frame = ttk.Frame(self, style="Surface.TFrame")
        canvas_frame.grid(row=3, column=0, sticky="nsew")
        canvas_frame.columnconfigure(0, weight=1)
        canvas_frame.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(canvas_frame, width=600, height=150, background=COLORS["timeline"],
                                highlightthickness=1, highlightbackground=COLORS["border"], takefocus=True)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        xscroll = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self._scroll_x)
        yscroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self._scroll_y)
        xscroll.grid(row=1, column=0, sticky="ew")
        yscroll.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(xscrollcommand=xscroll.set, yscrollcommand=yscroll.set)
        self.canvas.bind("<Configure>", lambda _e: self.schedule_draw())
        self.canvas.bind("<Button-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._motion)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind('<MouseWheel>', lambda event: self._scroll_y('scroll', -1 if event.delta > 0 else 1, 'units'))
        self.canvas.drop_target_register(DND_FILES)
        self.canvas.dnd_bind('<<DropEnter>>', self._drop_enter)
        self.canvas.dnd_bind('<<DropPosition>>', self._drop_enter)
        self.canvas.dnd_bind('<<DropLeave>>', self._drop_leave)
        self.canvas.dnd_bind('<<Drop>>', self._drop_files)
        self.tip(self.canvas, "hint")

        navigation = ttk.Frame(self, style="Surface.TFrame")
        navigation.grid(row=4, column=0, sticky="ew", pady=(8, 4))
        ttk.Label(navigation, textvariable=self.counter, font=FONTS["section"], style="Surface.TLabel").pack(side=tk.LEFT)
        self.button(navigation, "fit", self.fit).pack(side=tk.RIGHT)
        for label, multiplier in (("＋", 1.5), ("−", 1 / 1.5)):
            button = RoundedButton(navigation, text=label, width=3, command=lambda m=multiplier: self.change_zoom(m), style="Editor.TButton")
            button.pack(side=tk.RIGHT, padx=3)
            self.tip(button, "fit_tip")
        self.label(navigation, "zoom", style="SurfaceSecondary.TLabel").pack(side=tk.RIGHT, padx=8)

        tools = ttk.Frame(self, style="Surface.TFrame")
        tools.grid(row=6, column=0, sticky="ew", pady=(6, 6))
        for key in ("split", "trim", "duplicate", "delete"):
            button = self.button(tools, key, lambda operation=key: self.edit(operation))
            button.pack(side=tk.LEFT, padx=(0, 6))
            if key == 'trim':
                self.trim_button = button

        selection = ttk.Frame(self, style="Surface.TFrame")
        selection.grid(row=5, column=0, sticky="ew", pady=(4, 0))
        self.label(selection, "range_title", style="Surface.TLabel").pack(side=tk.LEFT, padx=(0, 12))
        for key in ('start', 'end'):
            self.label(selection, 'range_' + key, style="SurfaceSecondary.TLabel").pack(side=tk.LEFT, padx=(0, 5))
            spin = ttk.Spinbox(selection, textvariable=self.selection_fields[key], from_=0,
                               to=14400, increment=.001, width=10, format="%.3f")
            spin.pack(side=tk.LEFT, padx=(0, 12))
            self.controls.append(spin)
            self.selection_controls.append(spin)
            self.tip(spin, 'set_range_tip')
            spin.bind('<Return>', lambda _event: self.set_selection())
        select_button = self.button(selection, 'set_range', self.set_selection)
        select_button.pack(side=tk.LEFT)
        self.selection_controls.append(select_button)
        self.cursor_selection_button = self.button(selection, 'begin_range', self.toggle_cursor_selection, tip='cursor_range_tip')
        # Reserve the longer caption in both languages so toggling never shifts
        # fields or neighbouring buttons.
        self.cursor_selection_button.minimum_width = max(
            self.cursor_selection_button.font.measure(TEXT[language][key]) + 32
            for language in ('ru', 'en') for key in ('begin_range', 'finish_range'))
        self.cursor_selection_button.configure(text=self.tr('begin_range'))
        self.cursor_selection_button.pack(side=tk.LEFT, padx=(6, 0))
        self.zoom_range_button = self.button(selection, 'zoom_range', self.zoom_selection)
        self.zoom_range_button.pack(side=tk.LEFT, padx=6)
        ttk.Label(selection, textvariable=self.selection_length, style="SurfaceSecondary.TLabel").pack(side=tk.RIGHT)

        inspector = ttk.Labelframe(self, text=self.tr("selection"), padding=8, style="Surface.TLabelframe")
        inspector.grid(row=7, column=0, sticky="ew")
        self.inspector = inspector
        self.inspector_groups = []
        for column, (title, keys) in enumerate((('bounds', ('start', 'end')),
                                               ('placement', ('position', 'lane')),
                                               ('sound', ('gain', 'fade_in', 'fade_out')))):
            inspector.columnconfigure(column, weight=1, uniform="groups")
            group = ttk.Frame(inspector, style="Surface.TFrame")
            group.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 12, 0))
            group.columnconfigure(1, weight=1)
            self.inspector_groups.append(group)
            self.label(group, title, style="Surface.TLabel", font=FONTS['section']).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
            for row, key in enumerate(keys, 1):
                self.label(group, key, style="SurfaceSecondary.TLabel").grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
                if key == 'lane':
                    spin = ttk.Entry(group, textvariable=self.lane, width=10)
                else:
                    variable = tk.StringVar(value="0.000")
                    self.fields[key] = variable
                    spin = ttk.Spinbox(group, textvariable=variable, from_=-60 if key == "gain" else 0,
                                       to=18 if key == "gain" else 14400, increment=.1 if key == 'gain' else .001,
                                       format="%.3f", width=9)
                spin.grid(row=row, column=1, sticky="ew", pady=2)
                self.controls.append(spin)
                self.inspector_controls.append(spin)
                self.tip(spin, key + "_tip")
                spin.bind('<Return>', lambda _event: self.apply())
        ttk.Label(self.inspector_groups[0], textvariable=self.clip_length, style="SurfaceSecondary.TLabel").grid(
            row=3, column=0, columnspan=2, sticky='w', pady=2)
        apply_button = self.button(self.inspector_groups[1], "apply", self.apply, primary=True)
        apply_button.grid(row=3, column=0, columnspan=2, sticky='e', pady=2)
        self.inspector_controls.append(apply_button)

        transport = ttk.Frame(self, style="Surface.TFrame")
        transport.grid(row=8, column=0, sticky="ew", pady=(8, 0))
        self.button(transport, "play", self.preview, True, "preview").pack(side=tk.LEFT, padx=(0, 6))
        self.stop_button = self.button(transport, "stop", self.stop)
        self.stop_button.pack(side=tk.LEFT)
        self.button(transport, "export", self.export, True).pack(side=tk.RIGHT)
        self.cancel_button = RoundedButton(transport, text=self.tr("cancel"), command=self.cancel_task, state="disabled")
        self.localized.append((self.cancel_button, "cancel"))
        self.cancel_button.pack(side=tk.RIGHT, padx=8)
        self.tip(self.cancel_button, "cancel_tip")
        self.progress = ttk.Progressbar(self, mode="indeterminate", style="Thin.Horizontal.TProgressbar")
        self.progress.grid(row=9, column=0, sticky="ew", pady=(8, 3))
        ttk.Label(self, textvariable=self.status, style="SurfaceSecondary.TLabel", wraplength=800).grid(row=10, column=0, sticky="w")
        self.refresh()

    def _shortcut(self, event):
        widget = event.widget
        if (self.app.view.active_tab != 'editor' or widget.winfo_toplevel() is not self.app
                or event.state & (0x8 | 0x20000)):
            return None
        control, shift = bool(event.state & 4), bool(event.state & 1)
        letter = str(event.keysym).lower()
        if sys.platform == 'win32':
            letter = {73: 'i', 75: 'k', 88: 'x', 68: 'd', 90: 'z', 89: 'y',
                      83: 's', 79: 'o', 69: 'e', 86: 'v', 66: 'b',
                      32: 'space', 27: 'escape', 46: 'delete'}.get(event.keycode, letter)
        letter = {'cyrillic_sha': 'i', 'cyrillic_el': 'k', 'cyrillic_che': 'x',
                  'cyrillic_ve': 'd', 'cyrillic_ya': 'z', 'cyrillic_en': 'y',
                  'cyrillic_yeru': 's', 'cyrillic_shcha': 'o', 'cyrillic_u': 'e',
                  'cyrillic_em': 'v', 'cyrillic_i': 'b'}.get(letter, letter)
        if isinstance(widget, (tk.Entry, tk.Text, ttk.Entry, ttk.Spinbox, ttk.Combobox)):
            # Undo/redo in the editor's numeric inspector is project history,
            # including after Apply. Other text shortcuts remain native.
            numeric_editor_field = widget in self.inspector_controls + self.selection_controls
            if not (numeric_editor_field and control and letter in ('z', 'y')):
                return None
        if not control and letter == 'escape':
            self.stop()
            self.cancel_task()
            self._cursor_selection = None
            self.range = None
            self._range_clip_id = None
            self.refresh()
            return 'break'
        actions = {
            (True, False, 'i'): self.choose_audio,
            (True, False, 'k'): lambda: self.edit('split'),
            (True, True, 'x'): lambda: self.edit('trim'),
            (True, False, 'd'): lambda: self.edit('duplicate'),
            (False, False, 'delete'): lambda: self.edit('delete'),
            (True, False, 'z'): lambda: self.history(False),
            (True, True, 'z'): lambda: self.history(True),
            (True, False, 'y'): lambda: self.history(True),
            (True, False, 's'): self.save_draft,
            (True, False, 'o'): self.open_draft,
            (True, False, 'e'): self.export,
            (True, True, 'v'): lambda: self.separate_stems('two'),
            (True, True, 'b'): lambda: self.separate_stems('four'),
        }
        if widget is self.canvas:
            actions[(False, False, 'space')] = self.preview
        action = actions.get((control, shift, letter))
        if action is None:
            return None
        if not self.is_busy:
            action()
        return 'break'

    def apply_language(self):
        for widget, key in self.localized:
            widget.configure(text=self.tr(key))
        for index, key in enumerate(("new", "open_draft", "save_draft")):
            self.menu.entryconfigure(index, label=self.tr(key))
        for index, key in enumerate(('stems_two', 'stems_four')):
            self.stems_menu.entryconfigure(index, label=self.tr(key))
        self.status.set(self.tr("ready") if not self.is_busy else self.tr("rendering"))
        self.refresh()

    @property
    def is_busy(self):
        return self._task_active or self._pipeline_busy

    def set_pipeline_busy(self, value):
        self._pipeline_busy = value
        self._set_busy(self._task_active)

    def cancel_task(self):
        if self._pipeline_busy:
            self.app.stop_processing()
        else:
            self.cancel.set()

    def _set_busy(self, value):
        self._task_active = value
        value = self.is_busy
        for widget in self.controls:
            widget.configure(state="disabled" if value else "normal")
        self.cancel_button.configure(state="normal" if value else "disabled")
        self.stop_button.configure(state="normal")
        self.progress.start(15) if value else self.progress.stop()
        if not value:
            self.refresh()
        if hasattr(self.app, 'view'):
            self.app.view.update_editor_pipeline()

    def _task(self, operation, work):
        if self.is_busy:
            return
        self.stop()
        self.cancel.clear()
        self._set_busy(True)
        self.status.set(self.tr("importing" if operation in {"import", "draft"} else "rendering"))
        if operation == 'stems':
            self.status.set(self.tr('separating'))
        elif operation == 'cut':
            self.status.set(self.tr('cutting'))
        def run():
            try:
                self.events.put((operation, work()))
            except Cancelled:
                self.events.put(("cancelled", None))
            except Exception as exc:
                self.events.put(("error", str(exc)))
        self.worker = threading.Thread(target=run, daemon=True)
        self.worker.start()
        self._after = self.after(50, self._poll)

    def _poll(self):
        self._after = None
        try:
            operation, result = self.events.get_nowait()
        except queue.Empty:
            self._after = self.after(50, self._poll)
            return
        if operation == 'progress':
            self.status.set(self.tr('stem_progress').format(value=result * 100))
            self._after = self.after(50, self._poll)
            return
        self._set_busy(False)
        try:
            if operation == "import":
                sources, lane, position, separate_lanes = result
                # Validate the complete import before changing the live timeline.
                project = copy.deepcopy(self.project)
                selected = self.selected
                for source in sources:
                    added = project.add(source, lane, position)
                    selected = added.id
                    if separate_lanes:
                        lane += 1
                    elif position is not None:
                        position += added.duration
                self.project = project
                self.selected = selected
                if selected:
                    self.lane.set(project.get(selected).lane + 1)
                self.changed()
                self.fit()
                self.status.set(self.tr("ready"))
            elif operation == 'cut':
                source, original_clip, join = result
                if self.project.get(original_clip.id) != original_clip:
                    raise ValueError('Clip changed during editing; repeat the selection')
                self.project.replace_audio(original_clip.id, source)
                self.selected = original_clip.id
                self.cursor = min(join, original_clip.position + source.duration)
                self.changed()
                self.status.set(self.tr('ready'))
            elif operation == 'stems':
                sources, original_clip = result
                before = self.project._snapshot()
                project = copy.deepcopy(self.project)
                project.delete(original_clip.id)
                first_new_lane = self._lane_count()
                selected = None
                for index, source in enumerate(sources):
                    lane = original_clip.lane if index == 0 else first_new_lane + index - 1
                    added = project.add(source, lane, original_clip.position)
                    project.update(added.id, gain=original_clip.gain, fade_in=min(original_clip.fade_in, added.duration),
                                   fade_out=min(original_clip.fade_out, added.duration))
                    selected = selected or added.id
                # Replacing a clip with its components is one undoable action.
                project._undo = [*self.project._undo, before][-100:]
                project._redo.clear()
                self.project = project
                self.selected = selected
                self.changed()
                self.fit()
                self.status.set(self.tr('ready'))
            elif operation == "draft":
                self.project = result
                self.selected = self.project.clips[0].id if self.project.clips else None
                self.cursor = 0
                self.changed()
                self.fit()
                self.status.set(self.tr("ready"))
            elif operation == "preview":
                path, signature, start = result
                self._preview_cache = (signature, start, path)
                self._play(path, start)
            elif operation == "export":
                self.status.set(self.tr("saved").format(path=result))
            elif operation == "error":
                self.status.set(self.tr("error").format(error=result))
                messagebox.showerror(self.tr("title"), result, parent=self)
            else:
                self.status.set(self.tr("stopped"))
        except (ValueError, KeyError, StopIteration) as exc:
            self.status.set(self.tr("error").format(error=exc))
        self.refresh()

    def choose_audio(self):
        if self.is_busy:
            return
        paths = filedialog.askopenfilenames(parent=self, title=self.tr("add"),
                    filetypes=[("Audio", "*.mp3 *.wav *.flac *.m4a *.aac *.ogg *.opus *.wma")])
        if paths:
            self.import_files(paths)

    def separate_stems(self, mode):
        if self.is_busy or not self.selected:
            return
        from stem_separation import separate_clip
        clip = self.project.get(self.selected)
        def work():
            paths = separate_clip(clip.source, clip.start, clip.end, mode, self.cancel,
                                  lambda value: self.events.put(('progress', value)))
            return [read_waveform(path, self.cancel) for path in paths], clip
        self._task('stems', work)

    def import_files(self, paths, *, lane=None, position=None):
        if self.is_busy:
            return
        try:
            separate_lanes = lane is None
            if separate_lanes:
                lane = max((clip.lane + 1 for clip in self.project.clips), default=0)
                position = 0.0
            if not isinstance(lane, int) or lane < 0:
                raise ValueError(self.tr("lane_tip"))
        except (ValueError, tk.TclError) as exc:
            self.status.set(str(exc))
            return
        # Cached peaks are reused for files unchanged since their first import.
        cached = dict(self.project.sources)
        def load():
            sources = []
            for path in paths:
                path = Path(path).resolve()
                stat = path.stat()
                source = cached.get(str(path))
                if not source or source.stamp != (stat.st_size, stat.st_mtime_ns):
                    source = read_waveform(path, self.cancel)
                sources.append(source)
            return sources, lane, position, separate_lanes
        self._task("import", load)

    def _drop_enter(self, event):
        if self.is_busy:
            return REFUSE_DROP
        if hasattr(event, 'y_root') and self._drop_lane(self.canvas.canvasy(event.y_root - self.canvas.winfo_rooty())) is None:
            return REFUSE_DROP
        self.canvas.configure(highlightbackground=COLORS['accent'])
        return COPY

    def _drop_leave(self, _event=None):
        self.canvas.configure(highlightbackground=COLORS['border'])

    def _drop_files(self, event):
        self._drop_leave()
        if self.is_busy:
            return REFUSE_DROP
        try:
            paths = self.tk.splitlist(event.data)
            extensions = {'.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg', '.opus', '.wma'}
            if not paths or any(Path(path).suffix.lower() not in extensions or not Path(path).is_file() for path in paths):
                self.status.set(self.tr('drop_invalid'))
                return REFUSE_DROP
            x = self.canvas.canvasx(event.x_root - self.canvas.winfo_rootx())
            y = self.canvas.canvasy(event.y_root - self.canvas.winfo_rooty())
            lane = self._drop_lane(y)
            if lane is None:
                return REFUSE_DROP
            position = max(0, (x - 85) / self._scale())
            self.import_files(paths, lane=lane, position=position)
        except (tk.TclError, OSError, ValueError, TypeError):
            self.status.set(self.tr('drop_invalid'))
            return REFUSE_DROP
        return COPY

    def changed(self):
        self.stop()
        self._preview_cache = None
        self.range = None
        self._range_clip_id = None
        self._cursor_selection = None
        self._drag_preview = None
        self.refresh()
        self.app._editor_project_changed()

    def refresh(self):
        if self.selected and not any(c.id == self.selected for c in self.project.clips):
            self.selected = None
        if self._cursor_selection and self._cursor_selection[0] != self.selected:
            self._cursor_selection = None
            self.range = None
            self._range_clip_id = None
        if self.selected:
            clip = self.project.get(self.selected)
            name = Path(clip.source).name
            self.inspector.configure(text=name[:72])
            for key, var in self.fields.items():
                var.set(f"{getattr(clip, key):.3f}")
            self.lane.set(clip.lane + 1)
            self.clip_length.set(self.tr('length').format(value=clip.duration))
        else:
            self.inspector.configure(text=self.tr("selection"))
            self.clip_length.set('—')
        field_state = 'normal' if self.selected and not self.is_busy else 'disabled'
        for widget in self.inspector_controls:
            widget.configure(state=field_state)
        for widget in self.selection_controls:
            widget.configure(state=field_state if not self._cursor_selection else 'disabled')
        self.cursor_selection_button.configure(text=self.tr('finish_range' if self._cursor_selection else 'begin_range'), state=field_state)
        self._sync_selection_fields()
        self.undo_button.configure(state="normal" if self.project._undo and not self.is_busy else "disabled")
        self.redo_button.configure(state="normal" if self.project._redo and not self.is_busy else "disabled")
        self.trim_button.configure(state='normal' if self._trim_range() and not self.is_busy and not self._drag and not self._cursor_selection else 'disabled')
        self.zoom_range_button.configure(state='normal' if self._trim_range() and not self.is_busy else 'disabled')
        self.stems_button.configure(state='normal' if self.selected and not self.is_busy else 'disabled')
        self.counter.set(f"{clock(self.cursor)} / {clock(self.project.duration)}")
        self.schedule_draw()

    def schedule_draw(self):
        if self._draw_after is None:
            self._draw_after = self.after_idle(self.draw)

    def _scale(self):
        return max(1, self.canvas.winfo_width() - 90) / max(10, self.project.duration) * self.zoom

    def _lane_count(self):
        try:
            selected_lane = max(1, self.lane.get())
        except tk.TclError:
            selected_lane = 1
        preview_lane = self._drag_preview[1] + 1 if self._drag_preview else 1
        return max(selected_lane, preview_lane, max((c.lane + 1 for c in self.project.clips), default=1))

    def _drop_lane(self, y):
        count = self._lane_count()
        requested = max(0, int((y - 35) / 76))
        if requested < count:
            return requested
        return count

    def draw(self):
        self._draw_after = None
        canvas = self.canvas
        canvas.delete("all")
        self._range_overlay_photo = None
        scale = self._scale()
        duration = max(10, self.project.duration)
        width = max(canvas.winfo_width(), duration * scale + 95)
        lanes = self._lane_count()
        height = max(canvas.winfo_height(), 35 + lanes * 76 + 62)
        canvas.configure(scrollregion=(0, 0, width, height))
        step = max(.1, 10 ** math.floor(math.log10(max(.1, 110 / scale))))
        if 110 / scale / step > 5:
            step *= 10
        elif 110 / scale / step > 2:
            step *= 5
        elif 110 / scale / step > 1:
            step *= 2
        first_tick = max(0, int((canvas.canvasx(0) - 85) / scale / step))
        last_tick = min(int(duration / step) + 1, int((canvas.canvasx(canvas.winfo_width()) - 85) / scale / step) + 2)
        for index in range(first_tick, min(first_tick + 1000, last_tick)):
            value = index * step
            x = 85 + value * scale
            canvas.create_line(x, 26, x, height, fill=COLORS["border"])
            canvas.create_text(x + 3, 13, text=clock(value), anchor="w", fill=COLORS["secondary"], font=FONTS["small"])
        first_visible = max(0, int((canvas.canvasy(0) - 35) / 76))
        last_visible = min(lanes, int((canvas.canvasy(canvas.winfo_height()) - 35) / 76) + 2)
        for lane in range(first_visible, last_visible):
            top = 35 + lane * 76
            muted = lane in self.project.muted
            canvas.create_rectangle(0, top, 78, top + 68, fill=COLORS["surface_alt"], outline="")
            canvas.create_text(39, top + 24, text=f"{self.tr('lane')} {lane + 1}", font=FONTS["small"], fill=COLORS["text"])
            canvas.create_text(39, top + 45, text=self.tr("mute") if muted else "♫", fill=COLORS["danger"] if muted else COLORS["accent"])
        if canvas.canvasy(canvas.winfo_height()) + 80 >= 35 + lanes * 76:
            top = 35 + lanes * 76
            canvas.create_rectangle(4, top + 6, width - 4, top + 56, outline=COLORS['border_active'], dash=(5, 4))
            canvas.create_text(39, top + 31, text='＋', fill=COLORS['accent'], font=FONTS['title'])
            canvas.create_text(96, top + 31, text=self.tr('new_lane'), anchor='w', fill=COLORS['secondary'], font=FONTS['body'])
        palette = TRACK_COLORS
        for clip in self.project.clips:
            lane, position = clip.lane, clip.position
            if self._drag_preview and self._drag_preview[0] == clip.id:
                _, lane, position = self._drag_preview
            x1, x2 = 85 + position * scale, 85 + (position + clip.duration) * scale
            top = 35 + lane * 76
            if top + 76 < canvas.canvasy(0) or top > canvas.canvasy(canvas.winfo_height()):
                continue
            color = COLORS["elevated"] if lane in self.project.muted else palette[lane % len(palette)]
            tag = "clip:" + clip.id
            canvas.create_rectangle(x1, top + 3, x2, top + 65, fill=color,
                                    outline=COLORS["accent"] if clip.id == self.selected else COLORS["border_active"],
                                    width=2 if clip.id == self.selected else 1, tags=(tag,))
            name = Path(clip.source).stem
            chars = max(0, int((x2 - x1 - 12) / 7))
            if chars > 3:
                canvas.create_text(x1 + 6, top + 14, text=name[:chars], anchor="w", fill=COLORS["text"], font=FONTS["small"], tags=(tag,))
            source = self.project.sources[clip.source]
            visible_left = max(x1, canvas.canvasx(0))
            visible_right = min(x2, canvas.canvasx(canvas.winfo_width()))
            if visible_right <= visible_left:
                continue
            count = min(400, max(1, int((visible_right - visible_left) / 3)))
            for index in range(count):
                x = visible_left + (index + .5) / count * (visible_right - visible_left)
                at = clip.start + (x - x1) / scale
                peak_index = min(len(source.peaks) - 1, int(at / source.duration * len(source.peaks)))
                peak = source.peaks[peak_index] if source.peaks else 0
                amp = max(1, min(18, peak * 18 * 10 ** (clip.gain / 20)))
                canvas.create_line(x, top + 43 - amp, x, top + 43 + amp, fill=COLORS["accent"], tags=(tag,))
        if not self.project.clips:
            canvas.create_text(max(150, canvas.winfo_width() / 2), 70, text=self.tr("empty"), fill=COLORS["secondary"], font=FONTS["body"])
        bounds = self._trim_range()
        if bounds:
            a, b = bounds
            top = 35 + self.project.get(self.selected).lane * 76
            canvas.create_rectangle(85 + a * scale, top + 3, 85 + b * scale, top + 65,
                                    outline=COLORS["accent"], tags='selection-range')
            left = max(85 + a * scale, canvas.canvasx(0))
            right = min(85 + b * scale, canvas.canvasx(canvas.winfo_width()))
            if right > left:
                overlay = Image.new("RGBA", (max(1, math.ceil(right-left)), 62), COLORS['accent'])
                overlay.putalpha(45)
                self._range_overlay_photo = ImageTk.PhotoImage(overlay, master=canvas)
                canvas.create_image(left, top + 3, image=self._range_overlay_photo, anchor='nw')
            for value in bounds:
                x = 85 + value * scale
                canvas.create_line(x, top + 3, x, top + 65, fill=COLORS['accent'], width=2, tags='selection-range')
        self.draw_cursor()

    def draw_cursor(self):
        self.canvas.delete("cursor")
        x = 85 + self.cursor * self._scale()
        self.canvas.create_line(x, 23, x, max(self.canvas.winfo_height(), 35 + self._lane_count() * 76 + 62),
                                fill=COLORS["danger"], width=2, tags="cursor")
        self.counter.set(f"{clock(self.cursor)} / {clock(self.project.duration)}")

    def _time(self, event):
        return max(0, (self.canvas.canvasx(0) + event.x - 85) / self._scale())

    def _scroll_x(self, *args):
        self.canvas.xview(*args)
        self.schedule_draw()

    def _scroll_y(self, *args):
        self.canvas.yview(*args)
        self.schedule_draw()

    def _press(self, event):
        if self.is_busy:
            return
        self.stop()
        self.canvas.focus_set()
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        if self._cursor_selection:
            self.cursor = min(self.project.duration, self._time(event))
            self._drag = (self._time(event), None, False)
            self._update_cursor_selection()
            self.draw_cursor()
            return
        self.range = None
        self._range_clip_id = None
        self._drag_preview = None
        if x < 80 and 35 <= y < 35 + self._lane_count() * 76:
            self.project.toggle_mute(max(0, int((y - 35) / 76)))
            self.changed()
            return
        selecting = bool(event.state & 1)
        # The cursor and clips have distinct drag targets. Grabbing the red line
        # must never move the clip underneath it.
        cursor_hit = not selecting and abs(x - (85 + self.cursor * self._scale())) <= 5
        self.cursor = min(self.project.duration, self._time(event))
        if cursor_hit:
            self._drag = (self._time(event), None, False)
            self.refresh()
            return
        hit = None
        for item in reversed(self.canvas.find_overlapping(x, y, x, y)):
            tag = next((t for t in self.canvas.gettags(item) if t.startswith("clip:")), None)
            if tag:
                hit = tag[5:]
                break
        self.selected = hit if hit else (self.selected if selecting else None)
        clip = self.project.get(self.selected) if self.selected else None
        self._range_clip_id = clip.id if selecting and clip else None
        self._drag = (self._time(event), clip, selecting)
        self.refresh()

    def _motion(self, event):
        if not self._drag or self.is_busy:
            return
        at, clip, selecting = self._drag
        if selecting and clip:
            self.range = (at, min(self.project.duration, self._time(event)))
            self._sync_selection_fields()
            self.schedule_draw()
        elif clip:
            # Move the entire displayed clip live, without changing the model
            # or creating undo entries until the mouse is released.
            lane = self._drop_lane(self.canvas.canvasy(event.y))
            position = max(0, clip.position + self._time(event) - at)
            if lane is None:
                return
            position = self.project.free_position(lane, position, clip.duration, exclude=clip.id)
            self._drag_preview = (clip.id, lane, position)
            self.schedule_draw()
        elif not selecting:
            self.cursor = min(self.project.duration, self._time(event))
            self._update_cursor_selection()
            self.draw_cursor()

    def _release(self, event):
        if not self._drag or self.is_busy:
            return
        at, clip, selecting = self._drag
        self._drag = None
        self._drag_preview = None
        delta = self._time(event) - at
        if selecting:
            self.range = (at, self._time(event)) if clip and abs(delta * self._scale()) > 3 else None
            if not self._trim_range():
                self.range = None
                self._range_clip_id = None
            self.refresh()
        lane = self._drop_lane(self.canvas.canvasy(event.y))
        if clip and not selecting and lane is not None and (abs(delta * self._scale()) > 3 or lane != clip.lane):
            try:
                moved = self.project.update(clip.id, position=max(0, clip.position + delta), lane=lane)
                self.changed()
            except ValueError as exc:
                self.status.set(self.tr("error").format(error=exc))
        self.schedule_draw()

    def apply(self):
        if not self.selected or self.is_busy:
            return
        try:
            changes = {key: float(var.get().replace(",", ".")) for key, var in self.fields.items()}
            changes["lane"] = self.lane.get() - 1
            self.project.update(self.selected, **changes)
            self.changed()
            self.status.set(self.tr("ready"))
        except (ValueError, tk.TclError) as exc:
            self.status.set(self.tr("error").format(error=exc))

    def edit(self, operation):
        if not self.selected or self.is_busy:
            return
        try:
            if operation == "split":
                self.selected = self.project.split(self.selected, self.cursor).id
            elif operation == "duplicate":
                self.selected = self.project.duplicate(self.selected).id
            elif operation == "delete":
                self.project.delete(self.selected)
            elif operation == "trim":
                bounds = self._trim_range()
                if not bounds or self._drag or self._cursor_selection:
                    raise ValueError(self.tr("trim_tip"))
                clip = self.project.get(self.selected)
                a, b = bounds
                if clip.duration - (b - a) < .01:
                    self.project.delete(clip.id)
                else:
                    source = self.project.sources[clip.source]
                    self._task('cut', lambda: (remove_audio_selection(source, clip, a, b, self.cancel), clip, a))
                    return
            self.changed()
        except (ValueError, StopIteration) as exc:
            self.status.set(self.tr("error").format(error=exc))

    def _trim_range(self):
        if not self.range or not self.selected or self._range_clip_id != self.selected:
            return None
        try:
            clip = self.project.get(self.selected)
            a, b = sorted(self.range)
            a, b = max(a, clip.position), min(b, clip.position + clip.duration)
            return (a, b) if b - a >= .01 else None
        except StopIteration:
            return None

    def _sync_selection_fields(self):
        bounds = self._trim_range()
        if self.selected:
            clip = self.project.get(self.selected)
            if bounds:
                for key, value in zip(('start', 'end'), bounds):
                    self.selection_fields[key].set(f'{value - clip.position:.3f}')
            elif self._selection_clip != (clip.id, clip.duration):
                self.selection_fields['start'].set('0.000')
                self.selection_fields['end'].set(f'{clip.duration:.3f}')
            self._selection_clip = (clip.id, clip.duration)
        else:
            self._selection_clip = None
            for variable in self.selection_fields.values():
                variable.set('0.000')
        self.selection_length.set(self.tr('length').format(value=bounds[1] - bounds[0]) if bounds else '—')

    def set_selection(self):
        if not self.selected or self.is_busy:
            return
        try:
            clip = self.project.get(self.selected)
            start, end = (float(self.selection_fields[key].get().replace(',', '.')) for key in ('start', 'end'))
            if not all(math.isfinite(v) for v in (start, end)) or not (0 <= start < end <= clip.duration + 1e-6) or end - start < .01 - 1e-9:
                raise ValueError(self.tr('range_error'))
            self.stop()
            self._cursor_selection = None
            self.range = (clip.position + start, clip.position + min(end, clip.duration))
            self._range_clip_id = clip.id
            self.cursor = self.range[0]
            self.refresh()
            self.status.set(self.tr('ready'))
        except (ValueError, tk.TclError) as exc:
            self.status.set(self.tr('error').format(error=exc))

    def toggle_cursor_selection(self):
        if self.is_busy or not self.selected:
            return
        if self._playing:
            self.cursor = min(self.project.duration, self._play_origin + time.monotonic() - self._play_started)
        clip = self.project.get(self.selected)
        if not self._cursor_selection:
            if not clip.position <= self.cursor <= clip.position + clip.duration:
                self.status.set(self.tr('error').format(error=self.tr('cursor_range_error')))
                return
            self._cursor_selection = (clip.id, self.cursor)
            self.range = None
            self._range_clip_id = clip.id
            self._update_cursor_selection()
        else:
            self._update_cursor_selection()
            if not self._trim_range():
                self.status.set(self.tr('error').format(error=self.tr('range_error')))
                return
            self._cursor_selection = None
        self.refresh()

    def _update_cursor_selection(self):
        if not self._cursor_selection:
            return
        identifier, start = self._cursor_selection
        clip = self.project.get(identifier)
        end = min(clip.position + clip.duration, max(clip.position, self.cursor))
        self.range = (start, end)
        self._range_clip_id = identifier
        a, b = sorted((start, end))
        self.selection_fields['start'].set(f'{a - clip.position:.3f}')
        self.selection_fields['end'].set(f'{b - clip.position:.3f}')
        self.selection_length.set(self.tr('length').format(value=b - a))
        self.schedule_draw()

    def zoom_selection(self):
        bounds = self._trim_range()
        if bounds and not self.is_busy:
            a, b = bounds
            self.zoom = min(4096, max(1, max(10, self.project.duration) / max(.02, b - a) * .75))
            self.draw()
            width = float(self.canvas.cget('scrollregion').split()[2])
            left = max(0, 85 + a * self._scale() - self.canvas.winfo_width() * .125)
            self.canvas.xview_moveto(left / width)
            self.schedule_draw()

    def history(self, redo):
        if not self.is_busy:
            self.project.redo() if redo else self.project.undo()
            self.changed()

    def fit(self):
        self.zoom = 1
        self.canvas.xview_moveto(0)
        self.schedule_draw()

    def change_zoom(self, multiplier):
        self.zoom = max(1, min(4096, self.zoom * multiplier))
        self.schedule_draw()

    def preview(self):
        if self.is_busy or not self.project.clips:
            return
        if self._playing:
            self.stop()
            return
        start = self.cursor
        if start >= self.project.duration:
            self.status.set(self.tr('stopped'))
            return
        signature = repr((self.project.clips, sorted(self.project.muted)))
        if self._preview_cache and self._preview_cache[:2] == (signature, start):
            self._play(self._preview_cache[2], start)
            return
        if self._temp is None:
            self._temp = tempfile.TemporaryDirectory(prefix="sonicforge-listen-")
        target = Path(self._temp.name) / (str(time.time_ns()) + ".wav")
        project = copy.deepcopy(self.project)
        self._task("preview", lambda: (render(project, target, self.cancel, start=start), signature, start))

    def _play(self, path, start):
        try:
            import winsound
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        except (ImportError, RuntimeError) as exc:
            self.status.set(self.tr("error").format(error=exc))
            return
        self._playing = True
        self._play_origin = start
        self._play_started = time.monotonic()
        self._tick()

    def _tick(self):
        self._play_after = None
        if not self._playing:
            return
        self.cursor = min(self.project.duration, self._play_origin + time.monotonic() - self._play_started)
        self._update_cursor_selection()
        self.draw_cursor()
        # Keep the playhead visible when listening in a zoomed view.
        x = 85 + self.cursor * self._scale()
        left, right = self.canvas.canvasx(0), self.canvas.canvasx(self.canvas.winfo_width())
        if x > right - 24 or x < left:
            width = float(self.canvas.cget('scrollregion').split()[2])
            self.canvas.xview_moveto(max(0, x - self.canvas.winfo_width() * .2) / width)
            self.schedule_draw()
        self.status.set(self.tr("playing").format(time=clock(self.cursor)))
        if self.cursor >= self.project.duration:
            self.stop()
        else:
            self._play_after = self.after(80, self._tick)

    def stop(self):
        if self._playing:
            try:
                import winsound
                winsound.PlaySound(None, winsound.SND_PURGE)
            except (ImportError, RuntimeError):
                pass
        self._playing = False
        if self._play_after:
            self.after_cancel(self._play_after)
            self._play_after = None

    def export(self):
        if self.is_busy or not self.project.clips:
            return
        path = filedialog.asksaveasfilename(parent=self, title=self.tr("export"), defaultextension=".wav",
                    initialfile="SonicForge-edit.wav", filetypes=[("WAV", "*.wav"), ("MP3", "*.mp3"), ("M4A", "*.m4a")])
        if path:
            project = copy.deepcopy(self.project)
            self._task("export", lambda: render(project, path, self.cancel))

    def new(self):
        if self.is_busy:
            return
        if self.project.clips and not messagebox.askyesno(self.tr("title"), self.tr("new_confirm"), parent=self):
            return
        self.project = Timeline()
        self.selected = None
        self.cursor = 0
        self.changed()

    def save_draft(self):
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".sfproject", filetypes=[("Sonic Forge project", "*.sfproject")])
        if path:
            try:
                self.project.save(path)
                self.status.set(self.tr("saved").format(path=path))
            except OSError as exc:
                self.status.set(self.tr("error").format(error=exc))

    def open_draft(self):
        if self.is_busy:
            return
        if self.project.clips and not messagebox.askyesno(self.tr("title"), self.tr("new_confirm"), parent=self):
            return
        path = filedialog.askopenfilename(parent=self, filetypes=[("Sonic Forge project", "*.sfproject")])
        if path:
            self._task("draft", lambda: Timeline.load(path, self.cancel))

    def _on_destroy(self, event):
        if event.widget is self:
            self.app.unbind_class(self._shortcut_tag, '<KeyPress>')
            if self._shortcut_binding:
                try:
                    self.app.unbind('<KeyPress>', self._shortcut_binding)
                except tk.TclError:
                    pass
            self.cancel.set()
            self.stop()
            for identifier in (self._after, self._draw_after):
                if identifier:
                    self.after_cancel(identifier)
            # A rendering worker may still own files; clean up after it exits.
            if self._temp:
                worker, temporary = self.worker, self._temp
                def cleanup():
                    if worker:
                        worker.join()
                    temporary.cleanup()
                threading.Thread(target=cleanup, daemon=True).start()
