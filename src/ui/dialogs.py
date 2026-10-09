import tkinter as tk
from tkinter import ttk, colorchooser

from .theme import COLORS, SPACING, SIZES, FONTS
from .widgets import RoundedButton, SquareCheckbutton, ToolTip, ModernScale
from .windowing import show_centered


class CenteredDialog(tk.Toplevel):
    def show(self):
        self.centering = show_centered(self, *self._dialog_size, parent=self.app)
        self.app.set_window_icon(self)
        self.grab_set()
        self.lift()

    def close(self):
        self._dialog_size = (self.winfo_width(), self.winfo_height())
        self.grab_release()
        self.withdraw()


class CustomCoverDialog(CenteredDialog):
    """Stage edits locally; applying selects the custom generated style."""
    def __init__(self, app):
        super().__init__(app)
        self.withdraw()
        self.app = app
        self._dialog_size = (700, 670)
        self.title(app.t("custom_style_title"))
        self.configure(bg=COLORS["bg"])
        self.minsize(650, 650)
        self.transient(app)
        from music2picture_v2.custom_style import CustomCoverSettings
        settings = CustomCoverSettings.parse(app.custom_cover_settings)
        self.patterns = {app.t("custom_pattern_modern"): "modern",
                         app.t("custom_pattern_legacy"): "legacy"}
        self.pattern = tk.StringVar(self, next(label for label, key in self.patterns.items()
                                             if key == settings.pattern))
        self.variables = {key: tk.DoubleVar(self, getattr(settings, key))
                          for key in ("detail", "contrast", "saturation", "softness")}
        self.colors = list(settings.colors)
        self.positions = list(settings.positions)
        self._palette_drag = None
        self._palette_drag_origin = None
        self._palette_drag_moved = False
        self._palette_draw_job = None
        self._gradient_image = None
        body = ttk.Frame(self, padding=SPACING["lg"])
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(1, weight=1)
        ttk.Label(body, text=app.t("custom_style_description"), wraplength=590,
                  style="Secondary.TLabel").grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        ttk.Label(body, text=app.t("custom_pattern")).grid(row=1, column=0, sticky="w", padx=(0, 16))
        self.pattern_combo = ttk.Combobox(body, textvariable=self.pattern, values=tuple(self.patterns),
                                         state="readonly")
        self.pattern_combo.grid(row=1, column=1, sticky="ew")
        palette = ttk.Frame(body)
        palette.grid(row=2, column=0, columnspan=2, sticky="ew", pady=12)
        palette.columnconfigure(0, weight=1)
        ttk.Label(palette, text=app.t("custom_palette")).grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.palette_count = ttk.Label(palette, style="Secondary.TLabel")
        self.palette_count.grid(row=0, column=2, sticky="e", pady=(0, 6))
        self.palette_list = tk.Listbox(
            palette, height=4, font=FONTS["body"], exportselection=False,
            bg=COLORS["field"], fg=COLORS["text"], relief="flat", borderwidth=0,
            highlightthickness=1, highlightbackground=COLORS["border"], activestyle="none",
        )
        self.palette_list.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(palette, orient="vertical", command=self.palette_list.yview)
        scrollbar.grid(row=1, column=1, sticky="ns", padx=(0, 8))
        self.palette_list.configure(yscrollcommand=scrollbar.set)
        self.palette_list.bind("<<ListboxSelect>>", self._update_palette_actions)
        self.palette_list.bind("<Double-Button-1>", lambda _event: self.edit_color())
        self.palette_list.bind("<Delete>", lambda _event: self.remove_color())
        self.palette_list.bind("<Left>", lambda event: self._nudge_palette_color(-1, event))
        self.palette_list.bind("<Right>", lambda event: self._nudge_palette_color(1, event))
        buttons = ttk.Frame(palette)
        buttons.grid(row=1, column=2, sticky="n")
        RoundedButton(buttons, text=app.t("custom_palette_add"), command=self.add_color).grid(row=0, column=0, sticky="ew", padx=3)
        self.edit_button = RoundedButton(buttons, text=app.t("custom_palette_edit"), command=self.edit_color)
        self.edit_button.grid(row=0, column=1, sticky="ew", padx=3)
        self.remove_button = RoundedButton(buttons, text=app.t("custom_palette_remove"), command=self.remove_color)
        self.remove_button.grid(row=1, column=0, sticky="ew", padx=3, pady=4)
        moves = ttk.Frame(buttons)
        moves.grid(row=1, column=1, sticky="ew", padx=3, pady=4)
        self.up_button = RoundedButton(moves, text="↑", width=1, command=lambda: self.move_color(-1))
        self.up_button.pack(side=tk.LEFT)
        self.down_button = RoundedButton(moves, text="↓", width=1, command=lambda: self.move_color(1))
        self.down_button.pack(side=tk.RIGHT)
        ToolTip(self.up_button, lambda: app.t("custom_palette_up"))
        ToolTip(self.down_button, lambda: app.t("custom_palette_down"))
        self.gradient = tk.Canvas(palette, height=52, highlightthickness=0, borderwidth=0,
                                  bg=COLORS["bg"], cursor="hand2", takefocus=True)
        self.gradient.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        self.gradient.bind("<Configure>", self._draw_gradient)
        self.gradient.bind("<Button-1>", self._start_palette_drag)
        self.gradient.bind("<B1-Motion>", self._drag_palette_color)
        self.gradient.bind("<ButtonRelease-1>", self._end_palette_drag)
        self.gradient.bind("<Double-Button-1>", lambda _event: self.edit_color())
        self.gradient.bind("<Left>", lambda event: self._nudge_palette_color(-1, event))
        self.gradient.bind("<Right>", lambda event: self._nudge_palette_color(1, event))
        ttk.Label(palette, text=app.t("custom_palette_drag"), style="Secondary.TLabel",
                  wraplength=590).grid(row=3, column=0, columnspan=3, sticky="w")
        self._refresh_palette()
        self.scales = {}
        for row, (key, lower, upper) in enumerate(
                (("detail", 0, 100), ("contrast", 50, 150), ("saturation", 0, 150), ("softness", 0, 100)), start=3):
            ttk.Label(body, text=app.t("custom_" + key)).grid(row=row, column=0, sticky="w", padx=(0, 16))
            slider = ModernScale(body, variable=self.variables[key], from_=lower, to=upper,
                                 surface=False, show_value=True, height=46,
                                 value_formatter=lambda value: f"{value:.0f}%")
            slider.grid(row=row, column=1, sticky="ew", pady=3)
            ToolTip(slider, lambda key=key: app.t("tip_custom_" + key))
            self.scales[key] = slider
        ttk.Label(body, text=app.t("custom_style_hint"), wraplength=590,
                  style="Secondary.TLabel").grid(row=7, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        body.rowconfigure(8, weight=1)
        actions = ttk.Frame(body)
        actions.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        RoundedButton(actions, text=app.t("custom_reset"), command=self.reset).pack(side=tk.LEFT)
        RoundedButton(actions, text=app.t("custom_cancel"), command=self.close).pack(side=tk.RIGHT)
        RoundedButton(actions, text=app.t("custom_apply"), style="Primary.TButton",
                      command=self.apply).pack(side=tk.RIGHT, padx=8)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda _event: self.close())
        self.show()

    def _selected_color(self):
        selection = self.palette_list.curselection()
        return selection[0] if selection else None

    def add_color(self, color=None):
        if color is None:
            _, color = colorchooser.askcolor(self.colors[-1], parent=self,
                                            title=self.app.t("custom_palette_add"))
        if color:
            import numpy as np
            evenly_spaced = np.allclose(self.positions, np.linspace(0, 1, len(self.colors)), rtol=0, atol=1e-9)
            self.colors.append(color)
            if evenly_spaced:
                self.positions = list(np.linspace(0, 1, len(self.colors)))
            else:
                # Never move explicitly placed stops when extending the palette.
                self.positions.append(1.0)
            self._refresh_palette(len(self.colors) - 1)

    def edit_color(self):
        index = self._selected_color()
        if index is None:
            return
        _, color = colorchooser.askcolor(self.colors[index], parent=self,
                                        title=self.app.t("custom_palette_edit"))
        if color:
            self.colors[index] = color
            self._refresh_palette(index)

    def remove_color(self):
        index = self._selected_color()
        if index is not None and len(self.colors) > 1:
            self.colors.pop(index)
            self.positions.pop(index)
            self._refresh_palette(min(index, len(self.colors) - 1))

    def move_color(self, direction):
        index = self._selected_color()
        if index is not None and 0 <= index + direction < len(self.colors):
            other = index + direction
            self.colors[index], self.colors[other] = self.colors[other], self.colors[index]
            self._refresh_palette(other)

    def _refresh_palette(self, selection=0):
        from PIL import ImageColor
        if len(self.positions) != len(self.colors):
            import numpy as np
            self.positions = list(np.linspace(0, 1, len(self.colors)))
        self.palette_list.delete(0, tk.END)
        for index, color in enumerate(self.colors):
            self.palette_list.insert(tk.END, f"  {index + 1}.  {color.upper()} · {self.positions[index]:.1%}")
            red, green, blue = ImageColor.getrgb(color)
            foreground = "#ffffff" if .2126 * red + .7152 * green + .0722 * blue < 140 else "#181824"
            self.palette_list.itemconfigure(index, background=color, foreground=foreground,
                                            selectbackground=COLORS["accent"], selectforeground="#ffffff")
        self.palette_list.selection_set(selection)
        self.palette_list.activate(selection)
        self.palette_list.see(selection)
        self.palette_count.configure(text=self.app.t("custom_palette_count").format(count=len(self.colors)))
        self._update_palette_actions()

    def _update_palette_actions(self, _event=None):
        index = self._selected_color()
        for button, enabled in ((self.edit_button, index is not None),
                                (self.remove_button, index is not None and len(self.colors) > 1),
                                (self.up_button, index is not None and index > 0),
                                (self.down_button, index is not None and index < len(self.colors) - 1)):
            button.configure(state="normal" if enabled else "disabled")
        self._draw_gradient()

    def _palette_x(self, position):
        return 10 + position * max(1, self.gradient.winfo_width() - 20)

    def _start_palette_drag(self, event):
        self.gradient.focus_set()
        selected = self._selected_color()
        # Overlapping stops remain accessible by selecting their list row.
        if selected is not None and abs(self._palette_x(self.positions[selected]) - event.x) <= 9:
            index = selected
        else:
            index = min(range(len(self.colors)), key=lambda item: abs(self._palette_x(self.positions[item]) - event.x))
        self._palette_drag = index
        self._palette_drag_origin = event.x
        self._palette_drag_moved = False
        self._refresh_palette(index)

    def _place_palette_color(self, index, position):
        from bisect import bisect_right
        position = min(1.0, max(0.0, position))
        if position == self.positions[index]:
            return index
        color = self.colors.pop(index)
        self.positions.pop(index)
        index = bisect_right(self.positions, position)
        self.colors.insert(index, color)
        self.positions.insert(index, position)
        return index

    def _drag_palette_color(self, event):
        if self._palette_drag is None:
            return
        if not self._palette_drag_moved and abs(event.x - self._palette_drag_origin) < 3:
            return
        self._palette_drag_moved = True
        position = (event.x - 10) / max(1, self.gradient.winfo_width() - 20)
        self._palette_drag = self._place_palette_color(self._palette_drag, position)
        # Coalesce dense mouse events, including palettes with thousands of stops.
        if self._palette_draw_job is None:
            self._palette_draw_job = self.after_idle(self._refresh_dragged_palette)

    def _refresh_dragged_palette(self):
        self._palette_draw_job = None
        if self._palette_drag is not None:
            self._refresh_palette(self._palette_drag)

    def _end_palette_drag(self, event):
        if self._palette_drag is not None:
            self._drag_palette_color(event)
            if self._palette_draw_job is not None:
                self.after_cancel(self._palette_draw_job)
                self._palette_draw_job = None
            self._refresh_palette(self._palette_drag)
            self._palette_drag = None
            self._palette_drag_origin = None

    def _nudge_palette_color(self, direction, event):
        index = self._selected_color()
        if index is not None:
            step = .001 if event.state & 1 else .01
            index = self._place_palette_color(index, self.positions[index] + direction * step)
            self._refresh_palette(index)
        return "break"

    def _draw_gradient(self, *_):
        import numpy as np
        from PIL import Image, ImageDraw, ImageTk
        from music2picture_v2.custom_style import palette_rgb
        width = max(21, self.gradient.winfo_width())
        scale = 3
        raster = Image.new("RGB", (width * scale, 52 * scale), COLORS["bg"])
        strip = Image.fromarray(palette_rgb(self.colors, np.linspace(0, 1, width - 20), self.positions)[None, ...])
        raster.paste(strip.resize(((width - 20) * scale, 24 * scale), Image.Resampling.BILINEAR), (10 * scale, 2 * scale))
        draw = ImageDraw.Draw(raster)
        selected = self._selected_color()
        # Draw at most one unselected handle per pixel; never limit stored colors.
        handles = {round(self._palette_x(position)): index for index, position in enumerate(self.positions)}
        indices = [index for index in handles.values() if index != selected]
        if selected is not None:
            indices.append(selected)
        for index in indices:
            x = self._palette_x(self.positions[index]) * scale
            points = [(x, 25 * scale), (x + 7 * scale, 33 * scale),
                      (x + 7 * scale, 46 * scale), (x - 7 * scale, 46 * scale),
                      (x - 7 * scale, 33 * scale)]
            draw.polygon(points, fill=self.colors[index])
            draw.line(points + [points[0]], fill=COLORS["accent"] if index == selected else COLORS["border"],
                      width=(2 if index == selected else 1) * scale, joint="curve")
            if index == selected:
                draw.ellipse((x - 2 * scale, 36 * scale, x + 2 * scale, 40 * scale), fill="#ffffff")
        photo = ImageTk.PhotoImage(raster.resize((width, 52), Image.Resampling.LANCZOS), master=self)
        self.gradient.delete("all")
        self.gradient.create_image(0, 0, anchor="nw", image=photo)
        self._gradient_image = photo

    def reset(self):
        from music2picture_v2.custom_style import CustomCoverSettings
        defaults = CustomCoverSettings()
        self.pattern.set(next(label for label, key in self.patterns.items() if key == defaults.pattern))
        for key, variable in self.variables.items():
            variable.set(getattr(defaults, key))
        self.colors = list(defaults.colors)
        self.positions = list(defaults.positions)
        self._refresh_palette()

    def apply(self):
        settings = {key: variable.get() for key, variable in self.variables.items()}
        settings["colors"] = list(self.colors)
        settings["positions"] = list(self.positions)
        settings["pattern"] = self.patterns[self.pattern.get()]
        if self.app.apply_custom_cover_settings(settings):
            self.close()

    def close(self):
        if self._palette_draw_job is not None:
            self.after_cancel(self._palette_draw_job)
            self._palette_draw_job = None
        self._palette_drag = None
        widgets = []
        pending = list(self.winfo_children())
        while pending:
            widget = pending.pop()
            widgets.append(widget)
            pending.extend(widget.winfo_children())
        self.grab_release()
        self.destroy()
        # Release Tcl variables on the UI thread, not later during a worker's
        # garbage collection (which can block or fail Tk calls).
        for scale in self.scales.values():
            scale.variable = None
        self.scales.clear()
        self.variables.clear()
        self.pattern = None
        self._gradient_image = None
        for widget in widgets:
            if isinstance(widget, RoundedButton):
                widget._raster = None
                widget.font = None
                widget.command = None


class AdvancedAudioDialog(CenteredDialog):
    def __init__(self, app):
        super().__init__(app)
        self.withdraw()
        self._dialog_size = (760, 690)
        self.app = app
        self.localized = []
        self.title(app.t("advanced_title"))
        self.configure(bg=COLORS["bg"])
        self.geometry("760x690")
        self.minsize(720, 650)
        self.transient(app)
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda _event: self.close())
        self.bind("<F1>", lambda _event: self.app.view.show_help("audio"))
        self.show()

    def _text(self, widget, key):
        widget.configure(text=self.app.t(key))
        self.localized.append((widget, key))
        if self.app.t("tip_" + key) != "tip_" + key:
            self._tip(widget, "tip_" + key)
        return widget

    def _tip(self, widget, key):
        widget.help_key = key
        ToolTip(widget, lambda: self.app.t(key))

    def _build(self):
        body = ttk.Frame(self, padding=SPACING["lg"])
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self.notebook = ttk.Notebook(body)
        self.notebook.grid(row=0, column=0, sticky="nsew")
        self.enhancement_page = ttk.Frame(self.notebook)
        self.enhancement_page.columnconfigure(0, weight=1)
        self.enhancement_page.rowconfigure(0, weight=1)
        self.enhancement_canvas = tk.Canvas(
            self.enhancement_page,
            bg=COLORS["bg"],
            highlightthickness=0,
            borderwidth=0,
        )
        enhancement_scrollbar = ttk.Scrollbar(
            self.enhancement_page,
            orient="vertical",
            command=self.enhancement_canvas.yview,
        )
        self.enhancement_canvas.configure(yscrollcommand=enhancement_scrollbar.set)
        self.enhancement_canvas.grid(row=0, column=0, sticky="nsew")
        enhancement_scrollbar.grid(row=0, column=1, sticky="ns")
        self.enhancement_tab = ttk.Frame(self.enhancement_canvas, padding=SPACING["md"])
        self.enhancement_window = self.enhancement_canvas.create_window(
            (0, 0), window=self.enhancement_tab, anchor="nw"
        )
        self.enhancement_tab.bind("<Configure>", self._update_enhancement_scroll_region)
        self.enhancement_canvas.bind("<Configure>", self._resize_enhancement_content)
        self.bind("<MouseWheel>", self._scroll_enhancement)
        self.effects_tab = ttk.Frame(self.notebook, padding=SPACING["md"])
        self.notebook.add(self.enhancement_page, text=self.app.t("enhancement"))
        self.notebook.add(self.effects_tab, text=self.app.t("effects"))
        self._build_enhancement(self.enhancement_tab)
        self._build_effects(self.effects_tab)

        warning = ttk.Label(
            body, textvariable=self.app.audio_warning_var, style="Secondary.TLabel",
            foreground=COLORS["danger"], wraplength=680,
        )
        warning.grid(row=1, column=0, sticky="ew", pady=(SPACING["sm"], 0))
        close = RoundedButton(
            body,
            text=self.app.t("close"),
            width=SIZES["button_width"],
            command=self.close,
        )
        self.localized.append((close, "close"))
        close.grid(row=2, column=0, sticky="e", pady=(SPACING["sm"], 0))

    def _update_enhancement_scroll_region(self, _event=None):
        self.enhancement_canvas.configure(scrollregion=self.enhancement_canvas.bbox("all"))

    def _resize_enhancement_content(self, event):
        self.enhancement_canvas.itemconfigure(self.enhancement_window, width=event.width)

    def _scroll_enhancement(self, event):
        self.enhancement_canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    def _section(self, parent, key, row):
        frame = ttk.Labelframe(parent, text=self.app.t(key), style="Surface.TLabelframe", padding=SPACING["sm"])
        self.localized.append((frame, key))
        frame.grid(row=row, column=0, sticky="ew", pady=(0, SPACING["sm"]))
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        return frame

    def _fields(self, frame, fields, start_row=0, resettable=()):
        for index, (key, var_name, minimum, maximum, step) in enumerate(fields):
            column = index % 2
            row = start_row + (index // 2) * 2
            label = ttk.Label(frame, text=self.app.t(key), style="SurfaceSecondary.TLabel")
            self.localized.append((label, key))
            label.grid(row=row, column=column, sticky="w", padx=(0 if column == 0 else SPACING["sm"], 0))
            spin = ttk.Spinbox(
                frame, textvariable=app_var(self.app, var_name), from_=minimum, to=maximum,
                increment=step, width=14,
            )
            spin.grid(row=row + 1, column=column, sticky="ew", padx=(0 if column == 0 else SPACING["sm"], 0), pady=(2, SPACING["xs"]))
            self._tip(label, f"tip_{key}")
            self._tip(spin, f"tip_{key}")
            if var_name in resettable:
                spin.bind("<Double-Button-1>", lambda _event, variable=app_var(self.app, var_name): variable.set(0))

    def _build_enhancement(self, parent):
        parent.columnconfigure(0, weight=1)
        normalization = self._section(parent, "normalization", 0)
        self._fields(normalization, (
            ("integrated_lufs", "integrated_lufs_var", -30, -5, .5),
            ("true_peak", "true_peak_var", -9, 0, .1),
            ("lra", "lra_var", 1, 20, .5),
            ("final_gain", "final_gain_var", .5, 2, .05),
        ))
        equalizer = self._section(parent, "equalizer", 1)
        self._fields(equalizer, (
            ("bass_gain", "bass_gain_var", -12, 12, .5),
            ("mid_gain", "mid_gain_var", -12, 12, .5),
            ("treble_gain", "treble_gain_var", -12, 12, .5),
            ("stereo_width", "stereo_width_var", 0, 2, .05),
        ), resettable=("bass_gain_var", "mid_gain_var", "treble_gain_var"))
        filters = self._section(parent, "filters", 2)
        low_cut = SquareCheckbutton(filters, self.app.highpass_enabled_var, self.app.t("highpass_enabled"), fixed_width=220)
        high_cut = SquareCheckbutton(filters, self.app.lowpass_enabled_var, self.app.t("lowpass_enabled"), fixed_width=220)
        self.localized.extend(((low_cut, "highpass_enabled"), (high_cut, "lowpass_enabled")))
        low_cut.grid(row=0, column=0, sticky="w")
        high_cut.grid(row=0, column=1, sticky="w", padx=(SPACING["sm"], 0))
        self._tip(low_cut, "tip_highpass_enabled")
        self._tip(high_cut, "tip_lowpass_enabled")
        highpass = ttk.Spinbox(filters, textvariable=self.app.highpass_hz_var, from_=10, to=500, increment=5)
        highpass.grid(row=1, column=0, sticky="ew")
        lowpass = ttk.Spinbox(filters, textvariable=self.app.lowpass_hz_var, from_=4000, to=24000, increment=100)
        lowpass.grid(row=1, column=1, sticky="ew", padx=(SPACING["sm"], 0))
        self._tip(highpass, "tip_highpass_hz")
        self._tip(lowpass, "tip_lowpass_hz")
        dynamics = self._section(parent, "noise_and_dynamics", 3)
        denoise_label = ttk.Label(dynamics, text=self.app.t("denoise_mode"), style="SurfaceSecondary.TLabel")
        self.localized.append((denoise_label, "denoise_mode"))
        denoise_label.grid(row=0, column=0, sticky="w")
        self.denoise_combo = ttk.Combobox(dynamics, textvariable=self.app.denoise_mode_var, values=self.app.audio_option_values("denoise"), state="readonly")
        self.denoise_combo.grid(row=1, column=0, sticky="ew", padx=(0, SPACING["sm"]))
        self.denoise_combo.bind("<<ComboboxSelected>>", lambda _event: self.app.denoise_mode_changed())
        self._tip(denoise_label, "tip_denoise_mode")
        self._tip(self.denoise_combo, "tip_denoise_mode")
        compressor = SquareCheckbutton(dynamics, self.app.compressor_var, self.app.t("compressor"), fixed_width=220)
        self.localized.append((compressor, "compressor"))
        compressor.grid(row=0, column=1, sticky="w")
        self._tip(compressor, "tip_compressor")
        self._fields(dynamics, (
            ("compressor_threshold", "compressor_threshold_var", -60, 0, 1),
            ("compressor_ratio", "compressor_ratio_var", 1, 20, .5),
            ("compressor_attack", "compressor_attack_var", 1, 200, 1),
            ("compressor_release", "compressor_release_var", 20, 2000, 10),
            ("compressor_makeup", "compressor_makeup_var", 0, 18, .5),
        ), start_row=2)
        output = self._section(parent, "audio_output", 4)
        self.output_combos = []
        for column, (key, variable, kind) in enumerate((
            ("sample_rate", self.app.sample_rate_var, "sample_rate"),
            ("channel_layout", self.app.channels_var, "channels"),
        )):
            label = ttk.Label(output, text=self.app.t(key), style="SurfaceSecondary.TLabel")
            self.localized.append((label, key))
            label.grid(row=0, column=column, sticky="w", padx=(0 if column == 0 else SPACING["sm"], 0))
            combo = ttk.Combobox(output, textvariable=variable, values=self.app.audio_option_values(kind), state="readonly")
            combo.grid(row=1, column=column, sticky="ew", padx=(0 if column == 0 else SPACING["sm"], 0))
            self._tip(label, f"tip_{key}")
            self._tip(combo, f"tip_{key}")
            self.output_combos.append((combo, kind))
        quality_label = ttk.Label(output, text=self.app.t("mp3_quality"), style="SurfaceSecondary.TLabel")
        self.localized.append((quality_label, "mp3_quality"))
        quality_label.grid(row=2, column=0, sticky="w", pady=(SPACING["xs"], 0))
        self.quality_combo = ttk.Combobox(output, textvariable=self.app.mp3_quality_var, values=self.app.audio_option_values("quality"), state="readonly")
        self.quality_combo.grid(row=3, column=0, columnspan=2, sticky="ew")
        self._tip(quality_label, "tip_mp3_quality")
        self._tip(self.quality_combo, "tip_mp3_quality")

    def _build_effects(self, parent):
        parent.columnconfigure(0, weight=1)
        effects = self._section(parent, "effects", 0)
        self._fields(effects, (
            ("pitch_semitones", "pitch_semitones_var", -12, 12, .5),
            ("playback_speed", "playback_speed_var", .5, 2, .05),
            ("reverb_mix", "reverb_mix_var", 0, 1, .05),
            ("fade_in", "fade_in_var", 0, 30, .5),
            ("fade_out", "fade_out_var", 0, 30, .5),
        ))

    def apply_language(self):
        self.title(self.app.t("advanced_title"))
        for widget, key in self.localized:
            widget.configure(text=self.app.t(key))
        self.notebook.tab(self.enhancement_page, text=self.app.t("enhancement"))
        self.notebook.tab(self.effects_tab, text=self.app.t("effects"))
        self.denoise_combo.configure(values=self.app.audio_option_values("denoise"))
        for combo, kind in self.output_combos:
            combo.configure(values=self.app.audio_option_values(kind))
        self.quality_combo.configure(values=self.app.audio_option_values("quality"))

    def close(self):
        self.app.refresh_audio_warning()
        super().close()


def app_var(app, name):
    return getattr(app, name)


class AdditionalMetadataDialog(CenteredDialog):
    FIELDS = (
        ("disc", "disc_var"),
        ("publisher", "publisher_var"),
        ("copyright", "copyright_var"),
        ("lyrics", "lyrics_var"),
    )

    def __init__(self, app):
        super().__init__(app)
        self.withdraw()
        self._dialog_size = (680, 330)
        self.app = app
        self.localized = []
        self.title(app.t("additional_metadata_title"))
        self.configure(bg=COLORS["bg"])
        self.geometry("680x330")
        self.resizable(False, False)
        self.transient(app)
        self._build()
        self.bind("<Escape>", lambda _event: self.close())
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<F1>", lambda _event: self.app.view.show_help("metadata"))
        self.show()

    def _build(self):
        body = ttk.Labelframe(
            self,
            text=self.app.t("additional_metadata_title"),
            style="Surface.TLabelframe",
            padding=SPACING["lg"],
        )
        self.localized.append((body, "additional_metadata_title"))
        body.pack(fill=tk.BOTH, expand=True, padx=SPACING["lg"], pady=SPACING["lg"])
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        for index, (key, var_name) in enumerate(self.FIELDS):
            column = index % 2
            row = (index // 2) * 2
            label = ttk.Label(
                body,
                text=self.app.t(key),
                style="SurfaceSecondary.TLabel",
            )
            self.localized.append((label, key))
            label.grid(
                row=row,
                column=column,
                sticky="w",
                padx=(0 if column == 0 else SPACING["sm"], SPACING["sm"] if column == 0 else 0),
            )
            entry = ttk.Entry(body, textvariable=getattr(self.app, var_name))
            ToolTip(label, lambda k=key: self.app.t("tip_" + k))
            ToolTip(entry, lambda k=key: self.app.t("tip_" + k))
            entry.grid(
                row=row + 1,
                column=column,
                sticky="ew",
                padx=(0 if column == 0 else SPACING["sm"], SPACING["sm"] if column == 0 else 0),
                pady=(SPACING["xs"], SPACING["md"]),
            )
        close = RoundedButton(
            body,
            text=self.app.t("close"),
            width=SIZES["button_width"],
            command=self.close,
        )
        self.localized.append((close, "close"))
        close.grid(row=4, column=0, columnspan=2, sticky="e", pady=(SPACING["sm"], 0))

    def apply_language(self):
        self.title(self.app.t("additional_metadata_title"))
        for widget, key in self.localized:
            widget.configure(text=self.app.t(key))

    def close(self):
        super().close()
