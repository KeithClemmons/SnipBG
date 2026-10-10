"""
SnipBG - a simple, fully offline background remover.

Drop photos in, pick a background, click Remove background. Everything else
lives under "More options". Runs locally using the InSPyReNet model.
"""

import os
import queue
import subprocess
import sys
import threading
from collections import OrderedDict

import tkinter as tk
from tkinter import filedialog, colorchooser, messagebox

import numpy as np
from PIL import Image, ImageOps, ImageTk

import core
import batch
import config
import video as videomod

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    _DND = True
except Exception:
    _DND = False

APP_NAME = "SnipBG"
APP_VERSION = "1.1.0"
# Bundled files live in sys._MEIPASS when running as the packaged .exe
HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))

# ----- palette -----
BG         = "#14141c"   # main area
SIDEBAR    = "#1b1b26"   # right panel
SURFACE    = "#232331"   # cards / inputs
SURFACE_HI = "#2e2e42"   # hover / thumbnails
BORDER     = "#3a3a52"
ACCENT     = "#7c5cf6"   # purple (matches icon)
ACCENT_HI  = "#9077ff"
TEXT       = "#ececf4"
MUTED      = "#8b8ba3"
DIM        = "#5d5d75"
OK         = "#3ccf8e"
ERR        = "#f2637a"

WIN = sys.platform == "win32"
MAC = sys.platform == "darwin"

# Tk sizes fonts in points; macOS renders them noticeably smaller, so bump them there.
F = "Segoe UI" if WIN else "Helvetica Neue" if MAC else "DejaVu Sans"
_FS = 2 if MAC else 0


def _font(size, bold=False):
    if bold:
        return ("Segoe UI Semibold", size) if WIN else (F, size + _FS, "bold")
    return (F, size + _FS)


FONT     = _font(10)
FONT_S   = _font(9)
FONT_B   = _font(10, True)
FONT_SEC = _font(8, True)
FONT_BIG = _font(13, True)
FONT_H   = _font(16, True)
FONT_BTN = _font(11, True)


def wheel_steps(e):
    """Normalize a mouse-wheel event to +/- scroll steps on every platform."""
    if getattr(e, "num", None) in (4, 5):          # Linux/X11 wheel buttons
        return -1 if e.num == 4 else 1
    if WIN:
        return int(-e.delta / 120)
    return -1 if e.delta > 0 else 1 if e.delta < 0 else 0   # macOS: small raw deltas


def bind_wheel(widget, handler, all_widgets=False):
    method = widget.bind_all if all_widgets else widget.bind
    for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        method(seq, handler)


def open_path(path):
    """Open a folder or file with the system's default app."""
    if WIN:
        os.startfile(path)
    else:
        subprocess.Popen(["open" if MAC else "xdg-open", path])


def reveal_file(path):
    """Show a file selected in Explorer/Finder (Linux just opens its folder)."""
    path = os.path.normpath(path)
    if WIN:
        subprocess.Popen(["explorer", "/select,", path])
    elif MAC:
        subprocess.Popen(["open", "-R", path])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path)])

PREVIEW_MAX = 1400   # live preview works on a downscaled copy for speed
MATTE_CACHE = 30     # how many full-res mattes to keep for instant re-runs

SCALE = 1.0


def px(n):
    return int(round(n * SCALE))


def checker(w, h, size=10):
    ys, xs = np.indices((h, w))
    odd = ((xs // size + ys // size) % 2).astype(bool)
    arr = np.empty((h, w, 3), np.uint8)
    arr[:] = (236, 236, 242)
    arr[odd] = (206, 206, 216)
    return Image.fromarray(arr)


# =========================================================================== #
# Small flat widgets
# =========================================================================== #
class Button(tk.Label):
    KINDS = {
        "primary":   (ACCENT, ACCENT_HI, "#ffffff"),
        "secondary": (SURFACE_HI, "#3a3a52", TEXT),
        "ghost":     (None, SURFACE_HI, MUTED),
    }

    def __init__(self, parent, text, command, kind="secondary", font=FONT_B,
                 padx=12, pady=6, **kw):
        bg, hover, fg = self.KINDS[kind]
        self._bg = bg or parent["bg"]
        self._hover, self._fg = hover, fg
        super().__init__(parent, text=text, bg=self._bg, fg=fg, font=font,
                         padx=px(padx), pady=px(pady), cursor="hand2", **kw)
        self.command = command
        self.enabled = True
        self.bind("<Enter>", lambda e: self.enabled and self.config(bg=self._hover))
        self.bind("<Leave>", lambda e: self.config(bg=self._bg))
        self.bind("<ButtonRelease-1>", self._click)

    def _click(self, _e):
        if self.enabled and self.command:
            self.command()

    def set_enabled(self, on):
        self.enabled = on
        self.config(fg=self._fg if on else DIM, cursor="hand2" if on else "arrow",
                    bg=self._bg)


class Segmented(tk.Frame):
    """A row of mutually exclusive choices bound to a StringVar."""

    def __init__(self, parent, options, variable):
        super().__init__(parent, bg=SURFACE, padx=2, pady=2)
        self.var = variable
        self.labels = {}
        for i, (value, label) in enumerate(options):
            lb = tk.Label(self, text=label, font=FONT_S, bg=SURFACE, fg=MUTED,
                          padx=px(6), pady=px(4), cursor="hand2")
            lb.grid(row=0, column=i, sticky="nsew")
            self.columnconfigure(i, weight=1, uniform="seg")
            lb.bind("<Button-1>", lambda e, v=value: self.var.set(v))
            self.labels[value] = lb
        variable.trace_add("write", lambda *_: self._render())
        self._render()

    def _render(self):
        cur = str(self.var.get())
        for value, lb in self.labels.items():
            sel = str(value) == cur
            lb.config(bg=ACCENT if sel else SURFACE, fg="#ffffff" if sel else MUTED)


class Switch(tk.Canvas):
    """iOS-style on/off toggle bound to a BooleanVar."""

    def __init__(self, parent, variable):
        self.W, self.H = px(34), px(18)
        super().__init__(parent, width=self.W, height=self.H, bg=parent["bg"],
                         highlightthickness=0, cursor="hand2")
        self.var = variable
        self.bind("<Button-1>", lambda e: self.var.set(not self.var.get()))
        variable.trace_add("write", lambda *_: self._draw())
        self._draw()

    def _draw(self):
        self.delete("all")
        on = bool(self.var.get())
        W, H = self.W - 1, self.H - 1
        c = ACCENT if on else BORDER
        self.create_oval(0, 0, H, H, fill=c, outline=c)
        self.create_oval(W - H, 0, W, H, fill=c, outline=c)
        self.create_rectangle(H / 2, 0, W - H / 2, H, fill=c, outline=c)
        x = W - H / 2 if on else H / 2
        r = H / 2 - px(3)
        self.create_oval(x - r, H / 2 - r, x + r, H / 2 + r, fill="#ffffff", outline="")


class ScrollFrame(tk.Frame):
    """Vertically scrollable frame (mouse wheel) for the options panel."""

    def __init__(self, parent, bg):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>",
                        lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfig(self._win, width=e.width))
        self.canvas.pack(fill="both", expand=True)
        self.bind("<Enter>", lambda e: bind_wheel(self, self._wheel, all_widgets=True))
        self.bind("<Leave>", lambda e: [self.unbind_all(s) for s in
                                        ("<MouseWheel>", "<Button-4>", "<Button-5>")])

    def _wheel(self, e):
        if self.inner.winfo_height() > self.canvas.winfo_height():
            self.canvas.yview_scroll(wheel_steps(e), "units")


class Item:
    def __init__(self, path, rel):
        self.path = path
        self.rel = rel
        self.kind = core.kind_of(path)
        self.status = "pending"    # pending | working | done | error
        self.out = None
        self.error = None
        self.thumb = None


# =========================================================================== #
# App
# =========================================================================== #
class App:
    SWATCHES = [("transparent", "None"), ("white", "White"), ("black", "Black"),
                ("custom", "Color"), ("blur", "Blur"), ("image", "Photo")]

    def __init__(self, root):
        self.root = root
        root.title(APP_NAME)
        root.geometry(f"{px(1180)}x{px(760)}")
        root.minsize(px(900), px(600))
        root.configure(bg=BG)
        try:
            if WIN:
                root.iconbitmap(default=os.path.join(HERE, "snipbg.ico"))
            elif not MAC:   # macOS takes the icon from the .app bundle
                self._icon = tk.PhotoImage(file=os.path.join(HERE, "snipbg.png"))
                root.iconphoto(True, self._icon)
        except Exception:
            pass

        self.items = []
        self.sel = None
        self.s = config.load_settings()
        self.outdir = config.get_output_dir() or batch.default_output_dir()
        self.q = queue.Queue()
        self.busy = False

        self.mattes = OrderedDict()
        self._matte_lock = threading.Lock()
        self._src = None            # (path, downscaled RGB) for the selected item
        self._result = None         # (path, RGBA) live result for the selected item
        self._render_job = None
        self._render_token = 0
        self._display_job = None
        self._save_job = None
        self._photo = None
        self._thumb_refs = []

        self._make_vars()
        self._build()
        self._wire_traces()
        self._refresh_all()

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.bind("<Left>", lambda e: self._step(-1))
        root.bind("<Right>", lambda e: self._step(1))
        root.bind("<Delete>", lambda e: self.remove_selected())
        root.bind("<Command-o>" if MAC else "<Control-o>", lambda e: self.add_files())
        root.after(100, self._drain)

    # ------------------------------------------------------------------ vars
    def _make_vars(self):
        s = self.s
        self.v = {
            "background": tk.StringVar(value=s.background),
            "blur_strength": tk.IntVar(value=s.blur_strength),
            "quality": tk.StringVar(value=s.quality),
            "gpu": tk.BooleanVar(value=s.gpu),
            "shadow": tk.IntVar(value=s.shadow),
            "shadow_type": tk.StringVar(value=s.shadow_type),
            "despill": tk.IntVar(value=s.despill),
            "center": tk.BooleanVar(value=s.center),
            "sticker": tk.BooleanVar(value=s.sticker),
            "sticker_thickness": tk.IntVar(value=s.sticker_thickness),
            "sticker_color": tk.StringVar(value=s.sticker_color),
            "upscale": tk.StringVar(value=str(s.enhance_scale) if s.enhance else "off"),
            "resize": tk.StringVar(value=s.resize),
            "fmt": tk.StringVar(value=s.fmt),
            "compression": tk.StringVar(value=s.compression),
            "name_pattern": tk.StringVar(value=s.name_pattern),
            "alpha_mask": tk.BooleanVar(value=s.alpha_mask),
            "video_speed": tk.StringVar(value=str(s.video_speed)),
            "video_format": tk.StringVar(value=s.video_format),
        }
        self.view = tk.StringVar(value="after")
        self.more_open = tk.BooleanVar(value=False)

    def _wire_traces(self):
        for var in self.v.values():
            var.trace_add("write", lambda *_: self._on_settings_changed())
        self.view.trace_add("write", lambda *_: self._render_display())

    def _sync(self):
        v, s = self.v, self.s
        s.background = v["background"].get()
        s.blur_strength = int(v["blur_strength"].get())
        s.quality = v["quality"].get()
        s.gpu = bool(v["gpu"].get())
        s.shadow = int(v["shadow"].get())
        s.shadow_type = v["shadow_type"].get()
        s.despill = int(v["despill"].get())
        s.center = bool(v["center"].get())
        s.sticker = bool(v["sticker"].get())
        s.sticker_thickness = int(v["sticker_thickness"].get())
        s.sticker_color = v["sticker_color"].get()
        up = v["upscale"].get()
        s.enhance = up != "off"
        if s.enhance:
            s.enhance_scale = int(up)
        s.resize = v["resize"].get().strip()
        s.fmt = v["fmt"].get()
        s.compression = v["compression"].get()
        s.name_pattern = v["name_pattern"].get()
        s.alpha_mask = bool(v["alpha_mask"].get())
        s.video_speed = int(v["video_speed"].get())
        s.video_format = v["video_format"].get()

    def _on_settings_changed(self):
        try:
            self._sync()
        except (tk.TclError, ValueError):
            return
        self._update_dynamic_rows()
        self._draw_swatches()
        self._schedule_render()
        if self._save_job:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(600, self._save_config)

    def _save_config(self):
        self._save_job = None
        try:
            config.save_settings(self.s)
        except Exception:
            pass

    # ----------------------------------------------------------------- build
    def _build(self):
        # right sidebar
        side = tk.Frame(self.root, bg=SIDEBAR, width=px(310))
        side.pack(side="right", fill="y")
        side.pack_propagate(False)
        self._build_sidebar(side)

        # main area
        main = tk.Frame(self.root, bg=BG, padx=px(22), pady=px(18))
        main.pack(side="left", fill="both", expand=True)

        head = tk.Frame(main, bg=BG)
        head.pack(fill="x")
        tk.Label(head, text="SnipBG", font=FONT_H, fg=TEXT, bg=BG).pack(side="left")
        tk.Label(head, text="   Remove backgrounds. Nothing leaves your computer.",
                 font=FONT, fg=MUTED, bg=BG).pack(side="left", pady=(px(4), 0))

        # preview card
        card = tk.Frame(main, bg=SURFACE)
        card.pack(fill="both", expand=True, pady=(px(14), 0))
        bar = tk.Frame(card, bg=SURFACE, padx=px(12), pady=px(8))
        bar.pack(fill="x")
        self.name_lbl = tk.Label(bar, text="", font=FONT_B, fg=TEXT, bg=SURFACE, anchor="w")
        self.name_lbl.pack(side="left", fill="x", expand=True)
        self.view_seg = Segmented(bar, [("before", "Before"), ("after", "After")], self.view)
        self.view_seg.pack(side="right")
        self.canvas = tk.Canvas(card, bg="#101017", highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self._schedule_display())
        self.canvas.bind("<Button-1>", lambda e: (not self.items) and self.add_files())

        # thumbnail strip
        strip_head = tk.Frame(main, bg=BG)
        strip_head.pack(fill="x", pady=(px(14), px(6)))
        self.count_lbl = tk.Label(strip_head, text="", font=FONT_SEC, fg=MUTED, bg=BG)
        self.count_lbl.pack(side="left")
        Button(strip_head, "Clear all", self.clear, kind="ghost", font=FONT_S,
               padx=8, pady=2).pack(side="right")
        Button(strip_head, "Add folder", self.add_folder, kind="ghost", font=FONT_S,
               padx=8, pady=2).pack(side="right")
        Button(strip_head, "Add photos", self.add_files, kind="ghost", font=FONT_S,
               padx=8, pady=2).pack(side="right")

        self.TH = px(68)
        self.strip = tk.Canvas(main, bg=BG, height=self.TH + px(6), highlightthickness=0, bd=0)
        self.strip.pack(fill="x")
        self.strip.bind("<Button-1>", self._strip_click)
        # Right-click is Button-2 on macOS (plus Control-click).
        for seq in (("<Button-2>", "<Control-Button-1>") if MAC else ("<Button-3>",)):
            self.strip.bind(seq, self._strip_right_click)
        bind_wheel(self.strip, lambda e: self.strip.xview_scroll(wheel_steps(e) * 3, "units"))

        if _DND:
            for w in (self.root, self.canvas, self.strip):
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self._on_drop)

    def _build_sidebar(self, side):
        pad = px(20)

        # fixed bottom: save location + big action button
        bottom = tk.Frame(side, bg=SIDEBAR, padx=pad, pady=px(16))
        bottom.pack(side="bottom", fill="x")
        tk.Frame(side, bg=BORDER, height=1).pack(side="bottom", fill="x")

        tk.Label(bottom, text="SAVE TO", font=FONT_SEC, fg=MUTED, bg=SIDEBAR).pack(anchor="w")
        row = tk.Frame(bottom, bg=SIDEBAR)
        row.pack(fill="x", pady=(px(4), px(12)))
        self.out_lbl = tk.Label(row, text="", font=FONT_S, fg=TEXT, bg=SIDEBAR, anchor="w")
        self.out_lbl.pack(side="left", fill="x", expand=True)
        Button(row, "Open", self.open_output, kind="ghost", font=FONT_S, padx=6, pady=2).pack(side="right")
        Button(row, "Change", self.choose_out, kind="ghost", font=FONT_S, padx=6, pady=2).pack(side="right")

        self.go_btn = Button(bottom, "Remove background", self.start, kind="primary",
                             font=FONT_BTN, pady=11)
        self.go_btn.pack(fill="x")

        self.prog = tk.Canvas(bottom, height=px(4), bg=SURFACE, highlightthickness=0, bd=0)
        self.prog.pack(fill="x", pady=(px(10), px(6)))
        self.prog.bind("<Configure>", lambda e: self._draw_progress())
        self._progress = 0.0
        self.status_lbl = tk.Label(bottom, text="Ready", font=FONT_S, fg=MUTED, bg=SIDEBAR,
                                   anchor="w", justify="left", wraplength=px(270))
        self.status_lbl.pack(fill="x")

        # scrollable top: background + more options
        sf = ScrollFrame(side, SIDEBAR)
        sf.pack(fill="both", expand=True)
        body = tk.Frame(sf.inner, bg=SIDEBAR, padx=pad, pady=px(18))
        body.pack(fill="both", expand=True)

        tk.Label(body, text="BACKGROUND", font=FONT_SEC, fg=MUTED, bg=SIDEBAR).pack(anchor="w")
        grid = tk.Frame(body, bg=SIDEBAR)
        grid.pack(fill="x", pady=(px(8), 0))
        self.swatches = {}
        for i, (key, label) in enumerate(self.SWATCHES):
            cell = tk.Frame(grid, bg=SIDEBAR)
            cell.grid(row=i // 3, column=i % 3, padx=(0 if i % 3 == 0 else px(6), 0), pady=(0, px(8)),
                      sticky="nsew")
            grid.columnconfigure(i % 3, weight=1, uniform="sw")
            ring = tk.Frame(cell, bg=SIDEBAR, padx=2, pady=2)
            ring.pack(fill="x")
            cv = tk.Canvas(ring, height=px(40), width=px(76), bg=SURFACE,
                           highlightthickness=0, bd=0, cursor="hand2")
            cv.pack(fill="x")
            cap = tk.Label(cell, text=label, font=FONT_S, fg=MUTED, bg=SIDEBAR)
            cap.pack()
            for w in (cv, cap):
                w.bind("<Button-1>", lambda e, k=key: self._pick_background(k))
            cv.bind("<Configure>", lambda e: self._draw_swatches())
            self.swatches[key] = (ring, cv, cap)

        self.blur_row = tk.Frame(body, bg=SIDEBAR)
        self.blur_row.pack(fill="x")
        self.blur_inner = self._slider(self.blur_row, "Blur amount", "blur_strength", 1, 100,
                                       lambda n: f"{n}")

        # More options toggle
        self.more_btn = Button(body, "", self._toggle_more, kind="ghost", font=FONT_B,
                               padx=0, pady=6, anchor="w")
        self.more_btn.pack(fill="x", pady=(px(14), 0))
        self.more = tk.Frame(body, bg=SIDEBAR)
        self._build_more(self.more)
        self._update_more_btn()

    def _build_more(self, f):
        self._section(f, "Quality")
        self._seg_row(f, "AI model", "quality", [("base", "Best"), ("fast", "Fast")])
        if not MAC:   # CUDA only; Macs have no NVIDIA GPUs
            self._switch_row(f, "Use GPU (NVIDIA)", "gpu")

        self._section(f, "Effects")
        self._slider(f, "Drop shadow", "shadow", 0, 100, lambda n: "Off" if n == 0 else f"{n}%")
        self.shadow_row = tk.Frame(f, bg=SIDEBAR)
        self.shadow_row.pack(fill="x")
        self.shadow_inner = self._seg_row(self.shadow_row, "Shadow style", "shadow_type",
                                          [("classic", "Below"), ("gimp-style", "Angled"),
                                           ("soft", "Glow")], pack=False)
        self._slider(f, "Clean edges", "despill", 0, 100, lambda n: "Off" if n == 0 else f"{n}%")
        self._switch_row(f, "Center subject", "center")
        self._switch_row(f, "Sticker outline", "sticker")
        self.sticker_row = tk.Frame(f, bg=SIDEBAR)
        self.sticker_row.pack(fill="x")
        self.sticker_inner = tk.Frame(self.sticker_row, bg=SIDEBAR)
        self._slider(self.sticker_inner, "Outline width", "sticker_thickness", 8, 32, lambda n: f"{n}")
        self._seg_row(self.sticker_inner, "Outline color", "sticker_color",
                      [("white", "White"), ("black", "Black"), ("gray", "Gray")])

        self._section(f, "Size")
        self._seg_row(f, "AI upscale", "upscale",
                      [("off", "Off"), ("2", "2×"), ("3", "3×"), ("4", "4×")])
        lab = tk.Frame(f, bg=SIDEBAR)
        lab.pack(fill="x", pady=(px(8), px(4)))
        tk.Label(lab, text="Resize to", font=FONT, fg=TEXT, bg=SIDEBAR).pack(side="left")
        tk.Label(lab, text="e.g. 1080x1080", font=FONT_S, fg=DIM, bg=SIDEBAR).pack(side="right")
        tk.Entry(f, textvariable=self.v["resize"], font=FONT, bg=SURFACE, fg=TEXT,
                 insertbackground=TEXT, relief="flat", highlightthickness=1,
                 highlightbackground=BORDER, highlightcolor=ACCENT).pack(fill="x", ipady=px(4))

        self._section(f, "Output file")
        self._seg_row(f, "Format", "fmt", [("png", "PNG"), ("webp", "WebP")])
        self._seg_row(f, "File size", "compression",
                      [("none", "Full"), ("lossless", "Optimized"), ("256colors", "Small")])
        self._seg_row(f, "File name", "name_pattern",
                      [("original", "photo"), ("original-no-bg", "photo - no-bg"),
                       ("numbered-original", "001 - photo")])
        self._switch_row(f, "Also save mask", "alpha_mask")
        wm = tk.Frame(f, bg=SIDEBAR)
        wm.pack(fill="x", pady=(px(8), 0))
        tk.Label(wm, text="Watermark", font=FONT, fg=TEXT, bg=SIDEBAR).pack(side="left")
        Button(wm, "✕", self._clear_watermark, kind="ghost", font=FONT_S, padx=4, pady=1).pack(side="right")
        Button(wm, "Choose", self._pick_watermark, kind="ghost", font=FONT_S, padx=6, pady=1).pack(side="right")
        self.wm_lbl = tk.Label(f, text="", font=FONT_S, fg=MUTED, bg=SIDEBAR, anchor="w")
        self.wm_lbl.pack(fill="x")

        self._section(f, "Video & GIF")
        self._seg_row(f, "Frames", "video_speed",
                      [("1", "All"), ("2", "1/2"), ("3", "1/3"), ("4", "1/4")])
        self._seg_row(f, "Video file", "video_format",
                      [("mov-prores", "MOV (clear)"), ("mp4", "MP4 (green)")])
        tk.Frame(f, bg=SIDEBAR, height=px(8)).pack()

    # ------------------------------------------------------- sidebar helpers
    def _section(self, parent, title):
        tk.Label(parent, text=title.upper(), font=FONT_SEC, fg=MUTED, bg=SIDEBAR).pack(
            anchor="w", pady=(px(18), px(2)))

    def _seg_row(self, parent, label, key, options, pack=True):
        box = tk.Frame(parent, bg=SIDEBAR)
        if pack:
            box.pack(fill="x")
        tk.Label(box, text=label, font=FONT, fg=TEXT, bg=SIDEBAR).pack(anchor="w", pady=(px(8), px(4)))
        Segmented(box, options, self.v[key]).pack(fill="x")
        return box

    def _switch_row(self, parent, label, key):
        row = tk.Frame(parent, bg=SIDEBAR)
        row.pack(fill="x", pady=(px(10), 0))
        tk.Label(row, text=label, font=FONT, fg=TEXT, bg=SIDEBAR).pack(side="left")
        Switch(row, self.v[key]).pack(side="right")
        return row

    def _slider(self, parent, label, key, frm, to, fmt):
        box = tk.Frame(parent, bg=SIDEBAR)
        box.pack(fill="x")
        top = tk.Frame(box, bg=SIDEBAR)
        top.pack(fill="x", pady=(px(8), 0))
        tk.Label(top, text=label, font=FONT, fg=TEXT, bg=SIDEBAR).pack(side="left")
        val = tk.Label(top, text="", font=FONT_S, fg=MUTED, bg=SIDEBAR)
        val.pack(side="right")
        var = self.v[key]
        tk.Scale(box, from_=frm, to=to, orient="horizontal", variable=var, showvalue=0,
                 bg="#c9c9db", troughcolor=SURFACE_HI, activebackground="#ffffff",
                 highlightthickness=0, bd=0, sliderrelief="flat", sliderlength=px(18),
                 width=px(10)).pack(fill="x", pady=(px(4), 0))

        def show(*_):
            try:
                val.config(text=fmt(int(var.get())))
            except tk.TclError:
                pass
        var.trace_add("write", show)
        show()
        return box

    def _toggle_more(self):
        self.more_open.set(not self.more_open.get())
        if self.more_open.get():
            self.more.pack(fill="x")
        else:
            self.more.pack_forget()
        self._update_more_btn()

    def _update_more_btn(self):
        arrow = "▾" if self.more_open.get() else "▸"
        self.more_btn.config(text=f"{arrow}  More options")

    def _update_dynamic_rows(self):
        def show(inner, on):
            if on and not inner.winfo_manager():
                inner.pack(fill="x")
            elif not on and inner.winfo_manager():
                inner.pack_forget()
        show(self.blur_inner, self.s.background == "blur")
        show(self.shadow_inner, self.s.shadow > 0 and not self.s.sticker)
        show(self.sticker_inner, self.s.sticker)
        self.wm_lbl.config(text=os.path.basename(self.s.watermark) if self.s.watermark else "None")

    # -------------------------------------------------------------- swatches
    def _draw_swatches(self):
        cur = self.s.background
        for key, (ring, cv, cap) in self.swatches.items():
            sel = key == cur
            ring.config(bg=ACCENT if sel else SIDEBAR)
            cap.config(fg=TEXT if sel else MUTED)
            cv.delete("all")
            w = max(cv.winfo_width(), px(60))
            h = max(cv.winfo_height(), px(40))
            if key == "transparent":
                sz = px(8)
                for y in range(0, h, sz):
                    for x in range(0, w, sz):
                        c = "#ececf2" if ((x // sz + y // sz) % 2 == 0) else "#c9c9d6"
                        cv.create_rectangle(x, y, x + sz, y + sz, fill=c, outline="")
            elif key == "white":
                cv.create_rectangle(0, 0, w, h, fill="#ffffff", outline="")
            elif key == "black":
                cv.create_rectangle(0, 0, w, h, fill="#000000", outline=BORDER)
            elif key == "custom":
                cv.create_rectangle(0, 0, w, h, fill=self.s.bg_color, outline="")
                cv.create_text(w - px(10), px(10), text="✎", fill=self._contrast(self.s.bg_color),
                               font=FONT_S)
            elif key == "blur":
                for i, c in enumerate(("#5b6f92", "#6d84a8", "#8fa3c1", "#b4c2d6")):
                    r = (4 - i) * px(9)
                    cv.create_oval(w / 2 - r * 1.4, h / 2 - r, w / 2 + r * 1.4, h / 2 + r,
                                   fill=c, outline="")
            elif key == "image":
                cv.create_rectangle(0, 0, w, h, fill=SURFACE_HI, outline="")
                name = os.path.basename(self.s.bg_image) if self.s.bg_image else "Choose…"
                cv.create_text(w / 2, h / 2, text=name[:12], fill=MUTED, font=FONT_S)

    @staticmethod
    def _contrast(hexcol):
        try:
            r, g, b = core._hex_to_rgb(hexcol)
            return "#000000" if (r * 299 + g * 587 + b * 114) / 1000 > 140 else "#ffffff"
        except Exception:
            return "#000000"

    def _pick_background(self, key):
        if key == "custom":
            c = colorchooser.askcolor(self.s.bg_color, title="Background color")[1]
            if not c:
                return
            self.s.bg_color = c
        elif key == "image":
            p = filedialog.askopenfilename(title="Background photo",
                                           filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp")])
            if not p:
                if not self.s.bg_image:
                    return
            else:
                self.s.bg_image = p
        self.v["background"].set(key)
        self._on_settings_changed()

    def _pick_watermark(self):
        p = filedialog.askopenfilename(title="Watermark (PNG)", filetypes=[("PNG", "*.png")])
        if p:
            self.s.watermark = p
            self._on_settings_changed()

    def _clear_watermark(self):
        self.s.watermark = ""
        self._on_settings_changed()

    # ----------------------------------------------------------------- files
    def add_files(self):
        if self.busy:
            return
        exts = " ".join("*" + e for e in core.IMAGE_EXTS + core.GIF_EXTS + core.VIDEO_EXTS)
        paths = filedialog.askopenfilenames(title="Choose photos",
                                            filetypes=[("Photos & videos", exts), ("All files", "*.*")])
        if paths:
            self._add_paths(list(paths))

    def add_folder(self):
        if self.busy:
            return
        d = filedialog.askdirectory(title="Choose a folder")
        if d:
            self._add_paths([d])

    def _on_drop(self, event):
        if not self.busy:
            self._add_paths(list(self.root.tk.splitlist(event.data)))

    def _add_paths(self, paths):
        existing = {it.path for it in self.items}
        first_new = None
        for path, rel in core.discover_inputs(paths):
            if path in existing:
                continue
            it = Item(path, rel)
            it.thumb = self._make_thumb(it)
            self.items.append(it)
            existing.add(path)
            if first_new is None:
                first_new = len(self.items) - 1
        if first_new is None:
            if paths:
                self._set_status("No supported photos or videos found there.")
            return
        self._select(first_new)
        self._refresh_all()

    def _make_thumb(self, it):
        if it.kind == "video":
            return None
        try:
            im = Image.open(it.path)
            im.draft("RGB", (self.TH * 2, self.TH * 2))
            im = ImageOps.exif_transpose(im).convert("RGB")
            return ImageTk.PhotoImage(ImageOps.fit(im, (self.TH, self.TH)))
        except Exception:
            return None

    def remove_selected(self):
        if self.busy or self.sel is None or not self.items:
            return
        self._remove(self.sel)

    def _remove(self, idx):
        del self.items[idx]
        if not self.items:
            self.sel = None
            self._src = self._result = None
        else:
            self._select(min(idx, len(self.items) - 1))
        self._refresh_all()

    def clear(self):
        if self.busy:
            return
        self.items.clear()
        self.sel = None
        self._src = self._result = None
        self._set_status("Ready")
        self._set_progress(0)
        self._refresh_all()

    def _cur(self):
        if self.sel is None or self.sel >= len(self.items):
            return None
        return self.items[self.sel]

    def _step(self, d):
        if isinstance(self.root.focus_get(), tk.Entry):
            return
        if self.items and self.sel is not None:
            self._select(max(0, min(len(self.items) - 1, self.sel + d)))
            self._draw_strip()

    def _select(self, idx):
        self.sel = idx
        it = self.items[idx]
        self._result = None
        self._src = None
        if it.kind != "video":
            try:
                im = Image.open(it.path)
                im.draft("RGB", (PREVIEW_MAX, PREVIEW_MAX))
                im = ImageOps.exif_transpose(im).convert("RGB")
                im.thumbnail((PREVIEW_MAX, PREVIEW_MAX))
                self._src = (it.path, im)
            except Exception:
                self._src = None
        self._load_result_for_current()

    def _load_result_for_current(self):
        it = self._cur()
        if not it:
            return
        if it.kind == "image" and self._matte_get((it.path, self.s.quality)) is not None:
            self._schedule_render(0)
        elif it.kind == "gif" and it.status == "done" and it.out:
            try:
                im = Image.open(it.out).convert("RGBA")
                im.thumbnail((PREVIEW_MAX, PREVIEW_MAX))
                self._result = (it.path, im)
            except Exception:
                pass
        self._render_display()

    # ----------------------------------------------------------------- strip
    def _draw_strip(self):
        c = self.strip
        c.delete("all")
        self._thumb_refs = []
        T, gap, y = self.TH, px(8), px(3)
        for i, it in enumerate(self.items):
            x = i * (T + gap) + 2
            c.create_rectangle(x, y, x + T, y + T, fill=SURFACE_HI, outline="")
            if it.thumb:
                c.create_image(x, y, image=it.thumb, anchor="nw")
                self._thumb_refs.append(it.thumb)
            else:
                label = "VIDEO" if it.kind == "video" else "?"
                c.create_text(x + T / 2, y + T / 2, text=label, fill=MUTED, font=FONT_SEC)
            if i == self.sel:
                c.create_rectangle(x - 1, y - 1, x + T + 1, y + T + 1, outline=ACCENT, width=3)
            badge = {"done": (OK, "✓"), "working": (ACCENT, "…"), "error": (ERR, "!")}.get(it.status)
            if badge:
                r = px(9)
                bx, by = x + T - r - 3, y + r + 3
                c.create_oval(bx - r, by - r, bx + r, by + r, fill=badge[0], outline="")
                c.create_text(bx, by, text=badge[1], fill="#ffffff", font=FONT_SEC)
        # trailing "+" tile
        x = len(self.items) * (T + gap) + 2
        c.create_rectangle(x, y, x + T, y + T, outline=BORDER, dash=(4, 3))
        c.create_text(x + T / 2, y + T / 2, text="+", fill=MUTED, font=FONT_BIG)
        c.configure(scrollregion=(0, 0, x + T + 4, T + px(6)))

    def _strip_index(self, e):
        T, gap = self.TH, px(8)
        x = self.strip.canvasx(e.x)
        return int(x // (T + gap)), (x % (T + gap)) <= T

    def _strip_click(self, e):
        idx, on_tile = self._strip_index(e)
        if not on_tile:
            return
        if idx < len(self.items):
            self._select(idx)
            self._draw_strip()
        elif idx == len(self.items):
            self.add_files()

    def _strip_right_click(self, e):
        idx, on_tile = self._strip_index(e)
        if on_tile and idx < len(self.items) and not self.busy:
            m = tk.Menu(self.root, tearoff=0, bg=SURFACE, fg=TEXT, activebackground=ACCENT,
                        activeforeground="#ffffff", bd=0)
            m.add_command(label="Remove from list", command=lambda: self._remove(idx))
            it = self.items[idx]
            if it.out and os.path.exists(it.out):
                m.add_command(label="Show saved file",
                              command=lambda: reveal_file(it.out))
            m.tk_popup(e.x_root, e.y_root)

    # --------------------------------------------------------------- preview
    def _schedule_display(self):
        if self._display_job:
            self.root.after_cancel(self._display_job)
        self._display_job = self.root.after(60, self._render_display)

    def _render_display(self):
        self._display_job = None
        c = self.canvas
        c.delete("all")
        W, H = c.winfo_width(), c.winfo_height()
        if W < 10 or H < 10:
            return
        it = self._cur()
        if not it:
            self.name_lbl.config(text="")
            m = px(28)
            c.create_rectangle(m, m, W - m, H - m, outline=BORDER, dash=(6, 4), width=2)
            c.create_text(W / 2, H / 2 - px(30), text="⬇", fill=ACCENT, font=_font(28))
            c.create_text(W / 2, H / 2 + px(14), text="Drop photos or folders here",
                          fill=TEXT, font=FONT_BIG)
            c.create_text(W / 2, H / 2 + px(42), text="or click to browse  ·  JPG, PNG, WebP, GIF, MP4, MOV",
                          fill=MUTED, font=FONT_S)
            return

        self.name_lbl.config(text=os.path.basename(it.path))
        has_result = self._result is not None and self._result[0] == it.path
        show_after = self.view.get() == "after" and has_result
        img = self._result[1] if show_after else (self._src[1] if self._src else None)

        if img is None:
            msg = "Video selected — no preview" if it.kind == "video" else "Can't preview this file"
            if it.status == "done":
                msg = "Done — saved to your output folder"
            c.create_text(W / 2, H / 2, text=msg, fill=MUTED, font=FONT)
        else:
            pad = px(16)
            scale = min((W - pad * 2) / img.width, (H - pad * 2) / img.height, 1.0)
            dw, dh = max(1, int(img.width * scale)), max(1, int(img.height * scale))
            disp = img.resize((dw, dh), Image.LANCZOS)
            if disp.mode == "RGBA":
                base = checker(dw, dh, px(10))
                base.paste(disp, (0, 0), disp)
                disp = base
            self._photo = ImageTk.PhotoImage(disp)
            c.create_image(W // 2, H // 2, image=self._photo)

        # status pill
        pill = None
        if it.status == "working":
            pill = ("Removing background…", ACCENT)
        elif it.status == "error":
            pill = ("Failed: " + (it.error or "unknown error")[:80], ERR)
        elif self.view.get() == "after" and not has_result and it.kind == "image":
            pill = ("Not processed yet — click Remove background", SURFACE_HI)
        if pill:
            t = c.create_text(W / 2, H - px(30), text=pill[0], fill="#ffffff", font=FONT_S)
            x0, y0, x1, y1 = c.bbox(t)
            r = c.create_rectangle(x0 - px(12), y0 - px(6), x1 + px(12), y1 + px(6),
                                   fill=pill[1], outline="")
            c.tag_lower(r, t)

    # live re-render from the cached matte when settings change
    def _schedule_render(self, delay=150):
        if self._render_job:
            self.root.after_cancel(self._render_job)
        self._render_job = self.root.after(delay, self._start_render)

    def _start_render(self):
        self._render_job = None
        it = self._cur()
        if not it or it.kind != "image" or not self._src or self._src[0] != it.path:
            return
        matte = self._matte_get((it.path, self.s.quality))
        if matte is None:
            if self._result and self._result[0] == it.path:
                self._result = None
                self._render_display()
            return
        self._render_token += 1
        tok = self._render_token
        s = self.s.copy()
        s.enhance = False   # upscaling is slow; it's applied when saving
        src = self._src[1]
        m = matte.resize(src.size, Image.BILINEAR)
        threading.Thread(target=self._render_worker, args=(tok, it.path, src, m, s),
                         daemon=True).start()

    def _render_worker(self, tok, path, src, matte, s):
        try:
            out, _ = core.process_image(src, s, matte)
        except Exception:
            out = None
        self.q.put(("preview", (tok, path, out)))

    # ------------------------------------------------------------ mattes
    def _matte_get(self, key):
        with self._matte_lock:
            m = self.mattes.get(key)
            if m is not None:
                self.mattes.move_to_end(key)
            return m

    def _matte_put(self, key, m):
        with self._matte_lock:
            self.mattes[key] = m
            while len(self.mattes) > MATTE_CACHE:
                self.mattes.popitem(last=False)

    # ---------------------------------------------------------------- output
    def _short_path(self, p):
        parts = os.path.normpath(p).split(os.sep)
        return p if len(parts) <= 3 else "…" + os.sep + os.sep.join(parts[-2:])

    def choose_out(self):
        d = filedialog.askdirectory(title="Save results to", initialdir=self.outdir)
        if d:
            self.outdir = os.path.normpath(d)
            config.set_output_dir(self.outdir)
            self._refresh_all()

    def open_output(self):
        os.makedirs(self.outdir, exist_ok=True)
        open_path(self.outdir)

    # ------------------------------------------------------------------- run
    def start(self):
        if self.busy:
            return
        if not self.items:
            self.add_files()
            return
        self._sync()
        if any(it.kind == "video" for it in self.items) and not videomod.have_ffmpeg():
            if not messagebox.askyesno(APP_NAME,
                                       "Videos need ffmpeg, which isn't installed, so they will be "
                                       "skipped.\n\nInstall it with:  winget install Gyan.FFmpeg"
                                       "\n\nContinue with the other files?"):
                return
        try:
            os.makedirs(self.outdir, exist_ok=True)
        except OSError as e:
            messagebox.showerror(APP_NAME, f"Can't use that output folder:\n{e}")
            return
        config.set_output_dir(self.outdir)
        self.busy = True
        for it in self.items:
            it.status, it.error = "pending", None
        self.go_btn.set_enabled(False)
        self.go_btn.config(text="Working…")
        self._set_progress(0)
        self._draw_strip()
        threading.Thread(target=self._worker, args=(list(self.items), self.s.copy(), self.outdir),
                         daemon=True).start()

    def _worker(self, items, s, outdir):
        total, ok, fail = len(items), 0, 0
        for i, it in enumerate(items, 1):
            self.q.put(("item", (it, "working", None)))
            self.q.put(("status", (f"Working on {i} of {total}: {os.path.basename(it.path)}",
                                   (i - 1) / total)))
            sub = os.path.join(outdir, it.rel) if it.rel else outdir
            out = os.path.join(sub, core.build_name(it.path, s, index=i))
            try:
                os.makedirs(sub, exist_ok=True)
                if it.kind == "image":
                    src = ImageOps.exif_transpose(Image.open(it.path)).convert("RGB")
                    key = (it.path, s.quality)
                    matte = self._matte_get(key)
                    if matte is None:
                        if (s.quality, s.gpu) not in core._remover_cache:
                            self.q.put(("status", ("Loading the AI model (the first run downloads "
                                                   "it, ~350 MB)…", (i - 1) / total)))
                        matte = core.get_matte(src, s)
                        self._matte_put(key, matte)
                    rgba, _ = core.process_image(src, s, matte)
                    core.save_output(rgba, out, s, matte)
                elif it.kind == "gif":
                    out = videomod.process_gif(it.path, out, s)
                else:
                    out = videomod.process_video(it.path, out, s)
                ok += 1
                self.q.put(("item", (it, "done", out)))
            except Exception as e:
                fail += 1
                self.q.put(("item", (it, "error", str(e))))
        self.q.put(("finished", (ok, fail)))

    def _drain(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "status":
                    text, frac = payload
                    self._set_status(text)
                    self._set_progress(frac)
                elif kind == "item":
                    it, status, extra = payload
                    it.status = status
                    if status == "done":
                        it.out = extra
                    elif status == "error":
                        it.error = extra
                    self._draw_strip()
                    if it is self._cur():
                        if status == "done":
                            self.view.set("after")
                            self._load_result_for_current()
                        else:
                            self._render_display()
                elif kind == "preview":
                    tok, path, out = payload
                    it = self._cur()
                    if tok == self._render_token and it and it.path == path and out is not None:
                        self._result = (path, out)
                        self._render_display()
                elif kind == "finished":
                    ok, fail = payload
                    self.busy = False
                    self.go_btn.set_enabled(True)
                    self._set_progress(1)
                    if fail:
                        self._set_status(f"Saved {ok}, {fail} failed. Select a red item to see why.")
                    else:
                        self._set_status(f"Done! Saved {ok} file{'s' if ok != 1 else ''}. "
                                         "Click Open to see them.")
                    self._refresh_all()
        except queue.Empty:
            pass
        self.root.after(80, self._drain)

    # -------------------------------------------------------------- refresh
    def _set_status(self, text):
        self.status_lbl.config(text=text)

    def _set_progress(self, frac):
        self._progress = max(0.0, min(1.0, frac))
        self._draw_progress()

    def _draw_progress(self):
        c = self.prog
        c.delete("all")
        w = c.winfo_width()
        if self._progress > 0:
            c.create_rectangle(0, 0, w * self._progress, px(4), fill=ACCENT, outline="")

    def _refresh_all(self):
        n = len(self.items)
        self.count_lbl.config(text=f"{n} FILE{'S' if n != 1 else ''}" if n else "NO FILES YET")
        if not self.busy:
            self.go_btn.config(text="Remove background" if n <= 1 else f"Remove background  ·  {n} files")
        self.out_lbl.config(text="📁  " + self._short_path(self.outdir))
        self._update_dynamic_rows()
        self._draw_swatches()
        self._draw_strip()
        self._render_display()

    def _on_close(self):
        try:
            self._sync()
            config.save_settings(self.s)
        except Exception:
            pass
        self.root.destroy()


def _selftest(spec):
    """Headless check used by build_installer.bat: SNIPBG_SELFTEST="input.jpg|out_dir"."""
    src, out = spec.split("|", 1)
    try:
        s = core.Settings()
        rgba, matte = core.process_image(Image.open(src), s)
        os.makedirs(out, exist_ok=True)
        core.save_output(rgba, os.path.join(out, "selftest.png"), s, matte)
        return 0
    except Exception:
        import traceback
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "selftest_error.txt"), "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
        return 1


def main():
    global SCALE, _DND
    # The windowed .exe has no console; give libraries that print somewhere harmless to write.
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w"))
    if os.environ.get("SNIPBG_SELFTEST"):
        sys.exit(_selftest(os.environ["SNIPBG_SELFTEST"]))
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SnipBG.BackgroundRemover")
        ctypes.windll.shcore.SetProcessDpiAwareness(1)   # crisp text on high-DPI screens
    except Exception:
        pass
    root = None
    if _DND:
        try:
            root = TkinterDnD.Tk()
        except Exception:   # tkdnd library missing for this platform: run without drag & drop
            _DND = False
    if root is None:
        root = tk.Tk()
    SCALE = max(1.0, root.winfo_fpixels("1i") / 96.0)
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
