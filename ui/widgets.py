import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from PIL import Image, ImageDraw, ImageTk
from functools import lru_cache

from .theme import COLORS, FONTS, SIZES


class ToolTip:
    def __init__(self, widget, text_provider, delay=450, title_provider=None):
        self.widget = widget
        self.text_provider = text_provider
        self.delay = delay
        self.title_provider = title_provider
        self.window = None
        self.after_id = None
        widget.help_text_provider = text_provider
        widget.bind("<ButtonPress-3>", self._toggle, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress-1>", self._hide, add="+")
        widget.bind("<ButtonPress-2>", self._hide, add="+")
        widget.bind("<Destroy>", self._hide, add="+")
        widget.bind("<FocusOut>", self._hide, add="+")

    def _toggle(self, _event=None):
        if self.window is not None:
            self._hide()
        else:
            current = getattr(self.widget._root(), '_active_tooltip', None)
            if current is not None:
                current._hide()
            self.widget._root()._active_tooltip = self
            self._cancel()
            self._show()
        return 'break'

    def _schedule(self, _event=None):
        self._cancel()
        self.after_id = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self.after_id is not None:
            try:
                self.widget.after_cancel(self.after_id)
            except tk.TclError:
                pass
            self.after_id = None

    def _show(self):
        self.after_id = None
        text = self.text_provider()
        if not text or self.window is not None:
            return
        self.window = tk.Toplevel(self.widget)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.configure(bg=COLORS["border"])
        card = tk.Frame(self.window, bg=COLORS["surface"], padx=14, pady=12)
        card.pack(padx=1, pady=1)
        card.columnconfigure(1, weight=1)
        ru = getattr(self.widget._root(), 'language', 'ru') == 'ru'
        generic = 'Подсказка' if ru else 'Tip'
        try:
            title = self.title_provider() if self.title_provider else self.widget.cget('text')
        except tk.TclError:
            title = generic
        tk.Label(card, text='i', bg=COLORS['button'], fg=COLORS['accent'], font=FONTS['button'],
                 width=2, pady=3).grid(row=0, column=0, sticky='n', padx=(0, 9))
        tk.Label(card, text=title or generic, bg=COLORS['surface'], fg=COLORS['accent'],
                 font=FONTS['button'], justify='left', wraplength=SIZES['tooltip_width'] - 40).grid(
                     row=0, column=1, sticky='w')
        label = tk.Label(
            card,
            text=text,
            justify="left",
            wraplength=SIZES["tooltip_width"],
            bg=COLORS["surface"],
            fg=COLORS["secondary"],
            font=FONTS["body"],
            relief="flat",
        )
        label.grid(row=1, column=0, columnspan=2, sticky='w', pady=(9, 0))
        tk.Label(card, text='F1  ·  ' + ('Подробнее' if ru else 'More help'), bg=COLORS['surface'],
                 fg=COLORS['accent'], font=FONTS['small']).grid(row=2, column=0, columnspan=2,
                                                            sticky='w', pady=(10, 0))
        self.window.update_idletasks()
        x = self.widget.winfo_rootx()
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        max_x = self.widget.winfo_screenwidth() - self.window.winfo_reqwidth() - 8
        max_y = self.widget.winfo_screenheight() - self.window.winfo_reqheight() - 8
        if y > max_y:
            y = self.widget.winfo_rooty() - self.window.winfo_reqheight() - 8
        self.window.geometry(f"+{max(8, min(x, max_x))}+{max(8, y)}")
        self.window.deiconify()

    def _hide(self, _event=None):
        self._cancel()
        if self.window is not None:
            try:
                self.window.destroy()
            except tk.TclError:
                pass
            self.window = None


def widget_background(widget):
    if not isinstance(widget, ttk.Widget):
        try:
            return widget.cget("background")
        except tk.TclError:
            return COLORS["bg"]
    return ttk.Style(widget).lookup(widget.cget("style") or widget.winfo_class(), "background") or COLORS["bg"]


@lru_cache(maxsize=128)
def _rounded_surface(width, height, background, fill, outline, focused):
    scale = 4
    raster = Image.new("RGB", (width * scale, height * scale), background)
    draw = ImageDraw.Draw(raster)
    draw.rounded_rectangle((scale, scale, (width-1)*scale, (height-1)*scale),
                           radius=min(8, height/2-1)*scale, fill=fill,
                           outline=outline, width=(2 if focused else 1)*scale)
    return raster.resize((width, height), Image.Resampling.LANCZOS)


class RoundedButton(tk.Canvas):
    """Lightweight pill control with keyboard focus, text and disabled feedback."""
    def __init__(self, parent, text="", command=None, primary=False, width=None, style=None, state="normal"):
        self.text = text
        self.command = command
        self.primary = primary
        self.style_name = style or ("Primary.TButton" if primary else "Editor.TButton")
        self.enabled = state != "disabled"
        self.hover = False
        self.pressed = False
        self.font = tkfont.Font(root=parent, font=FONTS["button"])
        self.minimum_width = 0 if width is None else width * self.font.measure("0") + 32
        super().__init__(parent, width=max(self.minimum_width, self.font.measure(self._display_text()) + 32), height=SIZES['control_height'],
                         bg=widget_background(parent), highlightthickness=0, bd=0,
                         takefocus=self.enabled, cursor="hand2" if self.enabled else "arrow")
        self._shape = self.create_image(0, 0, anchor="nw")
        self._raster = None
        self._render_key = None
        self._text = self.create_text(0, 0, font=self.font)
        self.bind("<Configure>", self._draw)
        self.bind("<Enter>", lambda _e: self._hover(True))
        self.bind("<Leave>", lambda _e: self._hover(False))
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<space>", lambda _e: self.invoke())
        self.bind("<Return>", lambda _e: self.invoke())
        self.bind("<FocusIn>", self._draw)
        self.bind("<FocusOut>", self._draw)

    def configure(self, cnf=None, **kwargs):
        if "text" in kwargs:
            self.text = kwargs.pop("text")
            kwargs["width"] = max(self.minimum_width, self.font.measure(self._display_text()) + 32)
        if "style" in kwargs:
            self.style_name = kwargs.pop("style")
        if "state" in kwargs:
            self.enabled = kwargs.pop("state") != "disabled"
            kwargs["cursor"] = "hand2" if self.enabled else "arrow"
            kwargs["takefocus"] = self.enabled
        super().configure(cnf, **kwargs)
        self._draw()

    config = configure

    def cget(self, key):
        if key == "text":
            return self.text
        if key == "state":
            return "normal" if self.enabled else "disabled"
        if key == "style":
            return self.style_name
        if key == "command":
            return self.command
        return super().cget(key)

    def keys(self):
        return super().keys() + ["text", "style", "command"]

    def _display_text(self):
        return self.text

    def state(self, statespec=None):
        if statespec is not None:
            if "disabled" in statespec:
                self.configure(state="disabled")
            elif "!disabled" in statespec:
                self.configure(state="normal")
        return () if self.enabled else ("disabled",)

    def _hover(self, value):
        self.hover = value
        if not value:
            self.pressed = False
        self._draw()

    def _press(self, _event):
        if self.enabled:
            self.focus_set()
            self.pressed = True
            self._draw()

    def _release(self, event):
        pressed = self.pressed
        self.pressed = False
        self._draw()
        if pressed and 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height():
            self.invoke()

    def invoke(self):
        if self.enabled and self.command:
            self.command()
        return "break"

    def _draw(self, *_args):
        width, height = max(30, self.winfo_width()), max(30, self.winfo_height())
        primary = self.style_name in {"Primary.TButton", "Selected.Tab.TButton"}
        danger = self.style_name == "Danger.TButton"
        color = (COLORS["accent_pressed"] if self.pressed else COLORS["accent_hover"] if self.hover else COLORS["accent"]
                 ) if primary else (COLORS["button_pressed"] if self.pressed else COLORS["button_hover"] if self.hover else COLORS["button"])
        if danger:
            color = COLORS["danger_surface_pressed"] if self.pressed else COLORS["danger_surface_hover"] if self.hover else COLORS["danger_surface"]
        if not self.enabled:
            color = COLORS["button_disabled"]
        focused = self.focus_get() is self and self.enabled
        outline = COLORS["accent"] if focused else color
        # Tk also accepts Windows theme names such as SystemButtonFace;
        # resolve those to actual RGB channels before handing them to Pillow.
        background = tuple(channel // 257 for channel in self.winfo_rgb(self.cget("background")))
        key = (width, height, background, color, outline, focused)
        if key != self._render_key:
            self._raster = ImageTk.PhotoImage(_rounded_surface(*key), master=self)
            self.itemconfigure(self._shape, image=self._raster)
            self._render_key = key
        self.coords(self._text, width / 2, height / 2)
        self.itemconfigure(self._text, text=self._display_text(),
                           fill=COLORS["disabled"] if not self.enabled else COLORS["white"] if primary else COLORS["danger"] if danger else COLORS["button_text"])


class RibbonTab(RoundedButton):
    """Flat section tab attached to a shared ribbon and its content surface."""

    def _draw(self, *_args):
        width, height = max(1, self.winfo_width()), max(1, self.winfo_height())
        selected = self.style_name == "Selected.Tab.TButton"
        color = (COLORS["surface"] if selected else COLORS["accent_pressed"] if self.pressed
                 else COLORS["accent_hover"] if self.hover else COLORS["accent"])
        foreground = COLORS["button_text"] if selected else COLORS["white"]
        if not self.enabled:
            foreground = COLORS["disabled"]
        focused = self.focus_get() is self and self.enabled
        key = (width, height, color, focused, selected)
        if key != self._render_key:
            raster = Image.new("RGB", (width, height), color)
            if focused:
                # Focus is inside the tab, never an underline below the strip.
                ImageDraw.Draw(raster).rectangle((4, 4, width-5, height-5),
                                                outline=COLORS["border_active"] if selected else COLORS["white"])
            self._raster = ImageTk.PhotoImage(raster, master=self)
            self.itemconfigure(self._shape, image=self._raster)
            self._render_key = key
        self.coords(self._text, width / 2, height / 2)
        self.itemconfigure(self._text, text=self._display_text(), fill=foreground)


class RoundedMenuButton(RoundedButton):
    def __init__(self, parent, text="", menu=None, **kwargs):
        self.menu = menu
        super().__init__(parent, text=text, command=self._open_menu, **kwargs)
        self.bind("<Down>", lambda _event: self.invoke())

    def configure(self, cnf=None, **kwargs):
        if "menu" in kwargs:
            self.menu = kwargs.pop("menu")
        super().configure(cnf, **kwargs)

    config = configure

    def cget(self, key):
        return self.menu if key == "menu" else super().cget(key)

    def _display_text(self):
        return self.text if "▾" in self.text else self.text + " ▾"

    def _open_menu(self):
        if self.menu is not None:
            try:
                self.menu.tk_popup(self.winfo_rootx(), self.winfo_rooty() + self.winfo_height() + 4)
            finally:
                self.menu.grab_release()


class ThemedMenu(tk.Menu):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, background=COLORS["surface"], foreground=COLORS["text"],
                         activebackground=COLORS["button_hover"], activeforeground=COLORS["button_text"],
                         disabledforeground=COLORS["disabled"], font=FONTS["body"],
                         relief="flat", borderwidth=1, **kwargs)


class ModernScale(tk.Canvas):
    def __init__(
        self,
        parent,
        *,
        from_=0,
        to=100,
        variable=None,
        command=None,
        width=120,
        height=30,
        surface=True,
        show_value=False,
        value_formatter=None,
    ):
        self.minimum = float(from_)
        self.maximum = float(to)
        self.variable = variable if variable is not None else tk.DoubleVar(value=self.minimum)
        self.command = command
        self.hovered = False
        self.show_value = show_value
        self.value_formatter = value_formatter or (lambda value: f"{value:g}")
        background = COLORS["surface"] if surface else COLORS["bg"]
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=background,
            highlightthickness=0,
            borderwidth=0,
            takefocus=True,
            cursor="hand2",
        )
        self.bind("<Configure>", self._redraw)
        self.bind("<Button-1>", self._move)
        self.bind("<B1-Motion>", self._move)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<FocusIn>", self._redraw)
        self.bind("<FocusOut>", self._redraw)
        self.bind("<Left>", lambda _event: self._step(-1))
        self.bind("<Right>", lambda _event: self._step(1))
        self.bind("<Home>", lambda _event: self._set_value(self.minimum))
        self.bind("<End>", lambda _event: self._set_value(self.maximum))
        self._raster_item = self.create_image(0, 0, anchor="nw")
        self._raster = None
        self._render_key = None
        self._redraw_after = None
        self._value_text = self.create_text(
            0, 0, text="", fill=COLORS["accent_pressed"], font=FONTS["small"], anchor="ne"
        )
        self._variable_trace = self.variable.trace_add("write", self._redraw)
        self.bind("<Destroy>", self._dispose, add="+")

    def _geometry(self):
        radius = 9 if self.hovered or self.focus_get() is self else 8
        start = radius + 5
        end = max(start + 1, self.winfo_width() - radius - 5)
        center_y = self.winfo_height() - radius - 5 if self.show_value else self.winfo_height() / 2
        return start, end, center_y, radius

    def _redraw(self, *_args):
        if self._redraw_after is None and self.winfo_exists():
            self._redraw_after = self.after_idle(self._render)

    def _render(self):
        self._redraw_after = None
        if not self.winfo_exists():
            return
        start, end, center_y, radius = self._geometry()
        span = self.maximum - self.minimum
        fraction = 0.0 if span == 0 else (float(self.variable.get()) - self.minimum) / span
        fraction = max(0.0, min(1.0, fraction))
        thumb_x = start + (end - start) * fraction
        zero_fraction = 0.0 if not (self.minimum < 0 < self.maximum) else (-self.minimum / span)
        fill_start = start + (end - start) * zero_fraction
        focused = self.focus_get() is self
        width, height = max(1, self.winfo_width()), max(1, self.winfo_height())
        key = (width, height, fraction, self.hovered, focused, self.show_value)
        if key != self._render_key:
            # Tk Canvas curves are not antialiased. Render at four times the
            # current physical pixel size, then downsample the edges.
            scale = 4
            raster = Image.new("RGB", (width * scale, height * scale), self.cget("background"))
            draw = ImageDraw.Draw(raster)

            def rounded_box(box, rounding, color):
                draw.rounded_rectangle(tuple(round(v * scale) for v in box),
                                       radius=round(rounding * scale), fill=color)

            def circle(x, y, r, color):
                draw.ellipse(tuple(round(v * scale) for v in (x-r, y-r, x+r, y+r)), fill=color)

            rounded_box((start, center_y-2, end, center_y+2), 2, COLORS["border"])
            if abs(thumb_x - fill_start) > 0.1:
                rounded_box((min(fill_start, thumb_x), center_y-2,
                             max(fill_start, thumb_x), center_y+2), 2, COLORS["accent"])
            if self.minimum < 0 < self.maximum:
                rounded_box((fill_start-.5, center_y-5, fill_start+.5, center_y+5), .5,
                            COLORS["border_active"])
            if self.hovered or focused:
                circle(thumb_x, center_y, radius+4, COLORS["elevated"])
            circle(thumb_x, center_y, radius+1, self.cget("background"))
            circle(thumb_x, center_y, radius,
                   COLORS["accent_hover"] if self.hovered else COLORS["accent"])
            circle(thumb_x, center_y, 2.5, COLORS["white"])
            raster = raster.resize((width, height), Image.Resampling.LANCZOS)
            self._raster = ImageTk.PhotoImage(raster, master=self)
            self.itemconfigure(self._raster_item, image=self._raster)
            self._render_key = key
        if self.show_value:
            self.coords(self._value_text, end, 1)
            self.itemconfigure(
                self._value_text,
                text=self.value_formatter(float(self.variable.get())),
                state="normal",
            )
        else:
            self.itemconfigure(self._value_text, state="hidden")

    def _dispose(self, event):
        if event.widget is not self:
            return
        if self._redraw_after is not None:
            self.after_cancel(self._redraw_after)
            self._redraw_after = None
        self.variable.trace_remove("write", self._variable_trace)
        self._raster = None

    def _set_value(self, value):
        value = max(self.minimum, min(self.maximum, float(value)))
        if abs(float(self.variable.get()) - value) < .0001:
            return "break"
        self.variable.set(value)
        if self.command is not None:
            self.command(str(value))
        return "break"

    def _move(self, event):
        self.focus_set()
        start, end, _center_y, _radius = self._geometry()
        fraction = (event.x - start) / max(1, end - start)
        return self._set_value(self.minimum + max(0.0, min(1.0, fraction)) * (self.maximum - self.minimum))

    def _step(self, direction):
        step = (self.maximum - self.minimum) / 100.0
        return self._set_value(float(self.variable.get()) + direction * step)

    def _enter(self, _event=None):
        self.hovered = True
        self._redraw()

    def _leave(self, _event=None):
        self.hovered = False
        self._redraw()


class SquareCheckbutton(tk.Frame):
    def __init__(
        self,
        parent,
        variable,
        text="",
        command=None,
        surface=True,
        fixed_width=None,
    ):
        self.background = COLORS["surface"] if surface else COLORS["bg"]
        super().__init__(
            parent,
            bg=self.background,
            height=26,
            takefocus=True,
            highlightthickness=1,
            highlightbackground=self.background,
            highlightcolor=COLORS["accent"],
            cursor="hand2",
        )
        self.variable = variable
        self.command = command
        self.enabled = True
        self.minimum_width = fixed_width
        if fixed_width is not None:
            self.configure(width=fixed_width)
            self.pack_propagate(False)
        self.canvas = tk.Canvas(
            self,
            width=20,
            height=20,
            bg=self.background,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.label = tk.Label(
            self,
            text=text,
            bg=self.background,
            fg=COLORS["text"],
            font=FONTS["body"],
            cursor="hand2",
            anchor="w",
        )
        self.canvas.pack(side=tk.LEFT, padx=(1, 7))
        self.label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        for widget in (self, self.canvas, self.label):
            widget.bind("<Button-1>", self._toggle, add="+")
        self.bind("<space>", self._toggle, add="+")
        self.bind("<Return>", self._toggle, add="+")
        self.bind("<FocusIn>", self._redraw, add="+")
        self.bind("<FocusOut>", self._redraw, add="+")
        self._raster = None
        self._raster_item = self.canvas.create_image(0, 0, anchor="nw")
        self._variable_trace = self.variable.trace_add("write", self._redraw)
        self.bind("<Destroy>", self._dispose, add="+")
        self._fit_text()
        self._redraw()

    def configure(self, cnf=None, **kwargs):
        text = kwargs.pop("text", None)
        state = kwargs.pop("state", None)
        if text is not None:
            self.label.configure(text=text)
            self._fit_text()
        if state is not None:
            self.enabled = str(state) != "disabled"
            self.configure_cursor()
            self._redraw()
        if kwargs:
            super().configure(cnf, **kwargs)

    config = configure

    def _fit_text(self):
        if self.minimum_width is None:
            return
        font = tkfont.Font(font=self.label.cget("font"))
        required = font.measure(self.label.cget("text")) + 38
        super().configure(width=max(self.minimum_width, required))

    def configure_cursor(self):
        cursor = "hand2" if self.enabled else "arrow"
        for widget in (self, self.canvas, self.label):
            widget.configure(cursor=cursor)

    def _toggle(self, _event=None):
        if not self.enabled:
            return "break"
        self.focus_set()
        self.variable.set(not bool(self.variable.get()))
        if self.command:
            self.command()
        return "break"

    def _redraw(self, *_args):
        selected = bool(self.variable.get())
        if not self.enabled:
            border = COLORS["border"]
            fill = COLORS["surface_alt"]
            label_color = COLORS["disabled"]
        else:
            border = COLORS["accent"] if selected else COLORS["border_active"]
            fill = COLORS["accent"] if selected else COLORS["field"]
            label_color = COLORS["text"]
        scale = 4
        raster = Image.new("RGB", (20*scale, 20*scale), self.background)
        draw = ImageDraw.Draw(raster)
        draw.rounded_rectangle((2*scale, 2*scale, 18*scale, 18*scale), radius=3*scale,
                               outline=border, fill=fill, width=scale)
        if selected:
            ink = COLORS["white"] if self.enabled else COLORS["disabled"]
            draw.line([(6*scale, 10*scale), (9*scale, 13*scale), (14*scale, 7*scale)],
                      fill=ink, width=2*scale, joint="curve")
            for x, y in ((6, 10), (9, 13), (14, 7)):
                draw.ellipse(((x-1)*scale, (y-1)*scale, (x+1)*scale, (y+1)*scale), fill=ink)
        self._raster = ImageTk.PhotoImage(raster.resize((20, 20), Image.Resampling.LANCZOS), master=self)
        self.canvas.itemconfigure(self._raster_item, image=self._raster)
        super().configure(highlightbackground=COLORS["accent"] if self.enabled and self.focus_get() is self else self.background)
        self.label.configure(fg=label_color)

    def _dispose(self, event):
        if event.widget is self:
            self.variable.trace_remove("write", self._variable_trace)
            self._raster = None
