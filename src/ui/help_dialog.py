"""Local, structured help with stable navigation and a centered window."""
import tkinter as tk
from tkinter import ttk

from .theme import COLORS, FONTS
from .widgets import RoundedButton
from .windowing import _primary_work_area, show_centered


class HelpDialog(tk.Toplevel):
    def __init__(self, app, page, content_provider, focused_tip=None):
        super().__init__(app)
        self.withdraw()
        self.app = app
        self.provider = content_provider
        self.previous_grab = app.grab_current()
        self.page = page
        self.cards = []
        self.labels = []
        self.buttons = {}
        self.configure(bg=COLORS['bg'])
        self.title(app.t('help'))
        app.set_window_icon(self)
        self.transient(app)
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.bind('<Escape>', lambda _event: self.close())
        self.bind('<MouseWheel>', self._wheel)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        heading = ttk.Frame(self, padding=(20, 16))
        heading.grid(row=0, column=0, columnspan=2, sticky='ew')
        heading.columnconfigure(0, weight=1)
        self.title_label = ttk.Label(heading, font=FONTS['title'])
        self.title_label.grid(row=0, column=0, sticky='w')
        ttk.Label(heading, text='F1', foreground=COLORS['accent'], font=FONTS['button']).grid(row=0, column=1)
        ttk.Label(heading, text=self.tr('Выберите раздел слева — действия и параметры объяснены отдельно.',
                                      'Choose a section on the left for actions and parameter explanations.'),
                  style='Secondary.TLabel').grid(row=1, column=0, sticky='w', pady=(5, 0))

        sidebar = ttk.Frame(self, padding=(16, 0, 10, 0))
        sidebar.grid(row=1, column=0, sticky='ns')
        for name in ('editor', 'metadata', 'audio', 'cover', 'lyrics', 'processing', 'settings'):
            button = RoundedButton(sidebar, text=app.t('tab_' + name), width=15,
                                   command=lambda selected=name: self.show_page(selected))
            button.pack(fill=tk.X, pady=(0, 6))
            self.buttons[name] = button

        viewport = ttk.Frame(self, padding=(0, 0, 16, 0))
        viewport.grid(row=1, column=1, sticky='nsew')
        viewport.columnconfigure(0, weight=1)
        viewport.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(viewport, bg=COLORS['bg'], highlightthickness=0, width=570)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        scroll = ttk.Scrollbar(viewport, command=self.canvas.yview)
        scroll.grid(row=0, column=1, sticky='ns')
        self.canvas.configure(yscrollcommand=scroll.set)
        self.content = ttk.Frame(self.canvas)
        self.content_item = self.canvas.create_window(0, 0, anchor='nw', window=self.content)
        self.content.columnconfigure(0, weight=1)
        self.content.bind('<Configure>', lambda _event: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', self._resize)

        footer = ttk.Frame(self, padding=(20, 12))
        footer.grid(row=2, column=0, columnspan=2, sticky='ew')
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, text=self.tr('Esc — закрыть • Справка не меняет настройки и файлы',
                                     'Esc to close • Help does not change settings or files'),
                  style='Secondary.TLabel').grid(row=0, column=0, sticky='w')
        self.close_button = RoundedButton(footer, text=self.tr('Понятно', 'Got it'), command=self.close, primary=True)
        self.close_button.grid(row=0, column=1, padx=(12, 0))
        self.show_page(page, focused_tip)
        left, top, right, bottom = _primary_work_area(app)
        self.centering = show_centered(self, min(880, right - left - 40), min(680, bottom - top - 40), parent=app)
        if self.previous_grab:
            self.grab_set()
        self.close_button.focus_set()

    def tr(self, russian, english):
        return russian if self.app.language == 'ru' else english

    def show_page(self, page, focused_tip=None):
        self.page = page
        self.title_label.configure(text=self.app.t('tab_' + page) + ' · ' + self.tr('Справка', 'Help'))
        for name, button in self.buttons.items():
            button.configure(style='Selected.Tab.TButton' if name == page else 'Tab.TButton')
        for widget in self.content.winfo_children():
            widget.destroy()
        self.cards.clear()
        self.labels.clear()
        guide, parameters = self.provider(page)
        if focused_tip:
            self._card(self.tr('Выбранный параметр', 'Focused parameter'), focused_tip, '?', accent=True)
        self._heading(self.tr('Как пользоваться', 'Quick start'))
        for index, paragraph in enumerate(guide.split('\n'), 1):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            number, separator, rest = paragraph.partition('. ')
            numbered = separator and number.isdigit()
            self._card(self.tr('Шаг ', 'Step ') + number if numbered else self.tr('Важно знать', 'Good to know'),
                       rest if numbered else paragraph, number if numbered else 'i')
        self._heading(self.tr('Параметры и действия', 'Parameters and actions'))
        for parameter in parameters:
            title, description, *identity = parameter
            self._card(title, description, self._parameter_icon(identity[0] if identity else "", title))
        self.canvas.yview_moveto(0)
        self._wrap(max(570, self.canvas.winfo_width()))

    def _heading(self, title):
        ttk.Label(self.content, text=title, font=FONTS['section'], foreground=COLORS['accent']).grid(
            row=len(self.content.winfo_children()) - 1, column=0, sticky='w', pady=(8, 8), padx=2)

    @staticmethod
    def _parameter_icon(identity, title):
        value = f"{identity} {title}".casefold()
        choices = (
            (("play", "preview", "прослуш", "воспроиз"), "▶"),
            (("stop", "стоп", "останов"), "■"),
            (("save", "embed", "сохран", "запис", "встро"), "↧"),
            (("load", "source", "choose", "откры", "выб", "папк", "файл"), "⌂"),
            (("cover", "облож", "image", "картин"), "◈"),
            (("lyrics", "текст", "language", "язык", "transcri"), "A"),
            (("audio", "sound", "гром", "bass", "treble", "звук", "lufs", "peak"), "♪"),
            (("time", "speed", "fade", "attack", "release", "длитель", "скорост"), "⏱"),
            (("stereo", "width", "простран", "channel"), "↔"),
            (("check", "overwrite", "protect", "limit", "авто", "защит", "перезап"), "✓"),
            (("analy", "recogn", "распозн", "анализ"), "⌕"),
            (("metadata", "artist", "album", "genre", "title", "тег", "исполн", "назван"), "≡"),
            (("setting", "profile", "quality", "format", "парамет", "профил", "качеств"), "⚙"),
        )
        for needles, icon in choices:
            if any(needle in value for needle in needles):
                return icon
        return "i"

    def _card(self, title, description, badge, accent=False):
        card = tk.Frame(self.content, bg=COLORS['surface'], highlightthickness=1,
                        highlightbackground=COLORS['accent'] if accent else COLORS['border'], padx=14, pady=12)
        card.grid(row=len(self.content.winfo_children()) - 1, column=0, sticky='ew', pady=(0, 8))
        card.columnconfigure(1, weight=1)
        tk.Label(card, text=badge, bg=COLORS['button'], fg=COLORS['accent'], width=3,
                 font=FONTS['button'], padx=3, pady=5).grid(row=0, column=0, rowspan=2, sticky='n', padx=(0, 12))
        tk.Label(card, text=title, bg=COLORS['surface'], fg=COLORS['text'], font=FONTS['button'],
                 anchor='w', justify='left').grid(row=0, column=1, sticky='ew')
        label = tk.Label(card, text=description, bg=COLORS['surface'], fg=COLORS['secondary'],
                         font=FONTS['body'], anchor='w', justify='left', wraplength=460)
        label.grid(row=1, column=1, sticky='ew', pady=(5, 0))
        self.cards.append(card)
        self.labels.append(label)

    def _wrap(self, width):
        for label in self.labels:
            label.configure(wraplength=max(140, width - 100))

    def _resize(self, event):
        self.canvas.itemconfigure(self.content_item, width=event.width)
        self._wrap(event.width)

    def _wheel(self, event):
        if event.delta:
            self.canvas.yview_scroll(-1 if event.delta > 0 else 1, 'units')
        return 'break'

    def close(self):
        self.destroy()
        if self.previous_grab and self.previous_grab.winfo_exists() and self.previous_grab.winfo_viewable():
            self.previous_grab.grab_set()


class HelpPanel(ttk.Frame):
    """The same structured guidance inside a normal application section."""

    # Both hosts share card construction, semantic icons and text wrapping.
    tr = HelpDialog.tr
    _heading = HelpDialog._heading
    _card = HelpDialog._card
    _parameter_icon = staticmethod(HelpDialog._parameter_icon)
    _wrap = HelpDialog._wrap
    _resize = HelpDialog._resize
    _wheel = HelpDialog._wheel

    def __init__(self, parent, app, content_provider):
        super().__init__(parent, style='Surface.TFrame')
        self.app = app
        self.provider = content_provider
        self.page = 'editor'
        self.cards = []
        self.labels = []
        self.buttons = {}
        self.rendered_language = None
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        heading = ttk.Frame(self, style='Surface.TFrame')
        heading.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 16))
        self.title_label = ttk.Label(heading, style='Surface.TLabel', font=FONTS['title'])
        self.title_label.pack(anchor='w')
        self.intro_label = ttk.Label(heading, style='SurfaceSecondary.TLabel')
        self.intro_label.pack(anchor='w', pady=(5, 0))
        sidebar = ttk.Frame(self, style='Surface.TFrame')
        sidebar.grid(row=1, column=0, sticky='ns', padx=(0, 16))
        for name in ('editor', 'metadata', 'audio', 'cover', 'lyrics', 'processing', 'settings'):
            button = RoundedButton(sidebar, text=app.t('tab_' + name), width=15,
                                   command=lambda selected=name: self.show_page(selected))
            button.pack(fill=tk.X, pady=(0, 6))
            self.buttons[name] = button
        viewport = ttk.Frame(self, style='Surface.TFrame')
        viewport.grid(row=1, column=1, sticky='nsew')
        viewport.columnconfigure(0, weight=1)
        viewport.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(viewport, bg=COLORS['surface'], highlightthickness=0, width=540)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        scroll = ttk.Scrollbar(viewport, command=self.canvas.yview)
        scroll.grid(row=0, column=1, sticky='ns')
        self.canvas.configure(yscrollcommand=scroll.set)
        self.content = ttk.Frame(self.canvas, style='Surface.TFrame')
        self.content.columnconfigure(0, weight=1)
        self.content_item = self.canvas.create_window(0, 0, anchor='nw', window=self.content)
        self.content.bind('<Configure>', lambda _event: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', self._resize)
        self.canvas.bind('<MouseWheel>', self._wheel)
        self.refresh_language()

    def show_page(self, page, focused_tip=None):
        HelpDialog.show_page(self, page, focused_tip)
        self.rendered_language = self.app.language
        def bind_wheel(widget):
            widget.bind('<MouseWheel>', self._wheel)
            for child in widget.winfo_children():
                bind_wheel(child)
        bind_wheel(self.content)

    def ensure_page(self, page):
        if page != self.page or self.rendered_language != self.app.language:
            self.show_page(page)

    def refresh_language(self):
        self.intro_label.configure(text=self.tr('Выберите раздел слева — действия и параметры объяснены отдельно.',
                                               'Choose a section on the left for actions and parameter explanations.'))
        for name, button in self.buttons.items():
            button.configure(text=self.app.t('tab_' + name))
        if self.rendered_language is not None:
            self.show_page(self.page)
