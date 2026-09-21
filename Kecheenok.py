#!/usr/bin/env python3
"""
██╗  ██╗███████╗ ██████╗██╗███╗   ██╗ ██████╗ ██╗  ██╗
██║ ██╔╝██╔════╝██╔════╝██║████╗  ██║██╔═══██╗██║ ██╔╝
█████╔╝ █████╗  ██║     ██║██╔██╗ ██║██║   ██║█████╔╝
██╔═██╗ ██╔══╝  ██║     ██║██║╚██╗██║██║   ██║██╔═██╗
██║  ██╗███████╗╚██████╗██║██║ ╚████║╚██████╔╝██║  ██╗
╚═╝  ╚═╝╚══════╝ ╚═════╝╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝  ╚═╝
  v3.1 — YouTube downloader & audio FX toolkit
"""

from __future__ import annotations

import os
import sys
import shutil
import subprocess
import zipfile
import urllib.request
import threading
import tkinter as tk
import tkinter.font
from tkinter import ttk, filedialog, messagebox


# ---------------------------------------------------------------------------
# Pomocné funkce pro běh jako .exe (PyInstaller)
# ---------------------------------------------------------------------------
FROZEN = getattr(sys, "frozen", False)
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def app_dir() -> str:
    """Složka, kde leží .exe (nebo skript). Stabilnější než os.getcwd()."""
    if FROZEN:
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def run_quiet(cmd, **kwargs):
    """subprocess.run bez okna konzole a bez stdin (nutné pro --noconsole)."""
    kwargs.setdefault("stdin", subprocess.DEVNULL)
    if CREATE_NO_WINDOW:
        kwargs.setdefault("creationflags", CREATE_NO_WINDOW)
    return subprocess.run(cmd, **kwargs)


# ---------------------------------------------------------------------------
# Paleta & typografie
# ---------------------------------------------------------------------------
BG        = "#080b10"
SURFACE   = "#0e1117"
SURFACE2  = "#151b24"
SURFACE3  = "#1c2333"
BORDER    = "#252d3d"
ACCENT    = "#00d4ff"     # cyan — hlavní
ACCENT2   = "#7c4dff"     # fialová — akční tlačítko
GREEN     = "#00e676"
WARN      = "#ffab40"
RED       = "#ff4f6b"
TEXT      = "#dde3f0"
MUTED     = "#55637a"
DIM       = "#2a3447"

# Fonty se nastaví až po vytvoření hlavního okna (init_fonts)
_MONO    = "TkFixedFont"
FONT     = (_MONO, 10)
FONT_SM  = (_MONO, 9)
FONT_BIG = (_MONO, 13, "bold")
FONT_LBL = ("Segoe UI", 10)


def init_fonts(root: tk.Tk):
    global _MONO, FONT, FONT_SM, FONT_BIG
    avail = set(tkinter.font.families(root))
    _MONO = "TkFixedFont"
    for f in ("Consolas", "JetBrains Mono", "Cascadia Code", "Courier New", "DejaVu Sans Mono"):
        if f in avail:
            _MONO = f
            break
    FONT     = (_MONO, 10)
    FONT_SM  = (_MONO, 9)
    FONT_BIG = (_MONO, 13, "bold")


LOGO = (
    "██╗  ██╗███████╗ ██████╗██╗███╗   ██╗ ██████╗ ██╗  ██╗\n"
    "██║ ██╔╝██╔════╝██╔════╝██║████╗  ██║██╔═══██╗██║ ██╔╝\n"
    "█████╔╝ █████╗  ██║     ██║██╔██╗ ██║██║   ██║█████╔╝ \n"
    "██╔═██╗ ██╔══╝  ██║     ██║██║╚██╗██║██║   ██║██╔═██╗ \n"
    "██║  ██╗███████╗╚██████╗██║██║ ╚████║╚██████╔╝██║  ██╗\n"
    "╚═╝  ╚═╝╚══════╝ ╚═════╝╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝  ╚═╝"
)

# ---------------------------------------------------------------------------
# Kvalita / formáty
# ---------------------------------------------------------------------------
QUALITY_MAP = {
    "4K  (2160p)":     "bv*[vcodec^=avc][height<=2160]+ba[acodec^=mp4a]/best[ext=mp4]/best",
    "FHD (1080p)":     "bv*[vcodec^=avc][height<=1080]+ba[acodec^=mp4a]/best[ext=mp4]/best",
    "HD  (720p)":      "bv*[vcodec^=avc][height<=720]+ba[acodec^=mp4a]/best[ext=mp4]/best",
    "SD  (480p)":      "bv*[vcodec^=avc][height<=480]+ba[acodec^=mp4a]/best[ext=mp4]/best",
    "LOW (360p)":      "bv*[vcodec^=avc][height<=360]+ba[acodec^=mp4a]/best[ext=mp4]/best",
    "MP3 (audio)":     "bestaudio/best",
    "FLAC (lossless)": "bestaudio/best",
    "WAV (raw)":       "bestaudio/best",
}

AUDIO_POSTPROC = {
    "MP3 (audio)":     ("mp3",  "320"),
    "FLAC (lossless)": ("flac", None),
    "WAV (raw)":       ("wav",  None),
}

AUDIO_EXTS = (".mp3", ".flac", ".wav", ".m4a", ".opus", ".ogg", ".aac")


# ---------------------------------------------------------------------------
# ffmpeg helpers
# ---------------------------------------------------------------------------

def ffmpeg_local_bin() -> str:
    return os.path.join(app_dir(), "ffmpeg_bin", "bin")


def add_local_ffmpeg_to_path():
    """Pokud už je ffmpeg stažený vedle programu, přidej ho do PATH."""
    b = ffmpeg_local_bin()
    if os.path.isdir(b) and b not in os.environ.get("PATH", ""):
        os.environ["PATH"] = b + os.pathsep + os.environ.get("PATH", "")


def is_ffmpeg_installed() -> bool:
    add_local_ffmpeg_to_path()
    try:
        run_quiet(["ffmpeg", "-version"],
                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError, OSError):
        return False


def download_ffmpeg(log_cb):
    if sys.platform != "win32":
        log_cb("[WARN] ffmpeg nenalezen. Nainstaluj ho přes správce balíčků "
               "(např. sudo apt install ffmpeg).")
        return

    log_cb("[INFO] ffmpeg nenalezen — stahuji automaticky...")
    ffmpeg_dir = os.path.join(app_dir(), "ffmpeg_bin")
    os.makedirs(ffmpeg_dir, exist_ok=True)
    zip_path = os.path.join(ffmpeg_dir, "ffmpeg.zip")
    url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    log_cb(f"[INFO] Zdroj: {url}")

    # Normální User-Agent, Python-urllib bývá blokovaný (403)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    })

    with urllib.request.urlopen(req, timeout=60) as resp, open(zip_path, "wb") as out:
        total = int(resp.headers.get("Content-Length", 0))
        done = 0
        last_pct = -1
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if total > 0:
                pct = int(done * 100 / total)
                if pct != last_pct:
                    last_pct = pct
                    log_cb(f"[INFO] Stahování ffmpeg... {min(pct, 100)}%", replace=True)

    log_cb("[INFO] Rozbaluji ffmpeg...")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(ffmpeg_dir)

    extracted = next(
        (d for d in os.listdir(ffmpeg_dir)
         if os.path.isdir(os.path.join(ffmpeg_dir, d)) and d != "bin"),
        None,
    )
    if extracted is None:
        raise RuntimeError("Po rozbalení ffmpeg nebyla nalezena žádná složka.")

    bin_src = os.path.join(ffmpeg_dir, extracted, "bin")
    bin_dst = os.path.join(ffmpeg_dir, "bin")
    os.makedirs(bin_dst, exist_ok=True)

    for exe in ("ffmpeg.exe", "ffprobe.exe"):
        src = os.path.join(bin_src, exe)
        dst = os.path.join(bin_dst, exe)
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.move(src, dst)

    try:
        os.remove(zip_path)
    except OSError:
        pass

    # Pouze pro běžící proces (žádné setx — ořezává a ničí systémový PATH)
    os.environ["PATH"] = bin_dst + os.pathsep + os.environ.get("PATH", "")
    log_cb(f"[INFO] ffmpeg připraven ✅  ({bin_dst})")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_time_to_seconds(s: str) -> float | None:
    """'HH:MM:SS', 'MM:SS', nebo sekundy jako string → float. None při chybě."""
    s = s.strip()
    if not s:
        return None
    try:
        parts = [float(p) for p in s.split(":")]
    except ValueError:
        return None
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return None


def seconds_to_hhmmss(secs: float) -> str:
    secs = int(secs)
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


# ---------------------------------------------------------------------------
# Hlavní aplikace
# ---------------------------------------------------------------------------

class KecInokApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Kečínok v3.1  ·  YouTube downloader & FX toolkit")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)
        self.root.minsize(760, 560)

        # ── State ──
        self.url_rows:  list[dict] = []
        self.out_dir    = tk.StringVar(value=os.path.join(app_dir(), "downloads"))
        self.quality    = tk.StringVar(value="HD  (720p)")
        self.out_tmpl   = tk.StringVar(value="%(title)s [%(id)s].%(ext)s")
        self.running    = False
        self._last_was_progress = False

        # Trim
        self.trim_enabled = tk.BooleanVar(value=False)
        self.trim_start   = tk.StringVar(value="")
        self.trim_end     = tk.StringVar(value="")

        # FX
        self.fx: dict[str, dict] = {
            "speed":    {"var": tk.BooleanVar(), "val": tk.DoubleVar(value=1.0)},
            "pitch":    {"var": tk.BooleanVar(), "val": tk.IntVar(value=0)},
            "bass":     {"var": tk.BooleanVar(), "val": tk.IntVar(value=15)},
            "reverb":   {"var": tk.BooleanVar(), "val": tk.IntVar(value=40)},
            "echo":     {"var": tk.BooleanVar(), "val": tk.IntVar(value=300)},
            "stereo":   {"var": tk.BooleanVar(), "val": tk.DoubleVar(value=3.0)},
            "loudnorm": {"var": tk.BooleanVar()},
        }
        self.fc_var = tk.StringVar(value="acopy")
        self.fx_val_labels: dict[str, tuple] = {}

        self._build_ui()
        self._ensure_ffmpeg()

    # ── ffmpeg async check ────────────────────────────────────────────────

    def _ensure_ffmpeg(self):
        def _work():
            try:
                if is_ffmpeg_installed():
                    self._log("[CHECK] ffmpeg nalezen ✅")
                else:
                    download_ffmpeg(self._log)
            except Exception as e:
                self._log(f"[ERROR] ❌ ffmpeg se nepodařilo připravit: {e}")
                self._log("[TIP]  Stáhni ffmpeg ručně (gyan.dev) a dej ffmpeg.exe + "
                          "ffprobe.exe do složky ffmpeg_bin\\bin vedle programu.")
        threading.Thread(target=_work, daemon=True).start()

    # ── UI builder ────────────────────────────────────────────────────────

    def _build_ui(self):
        root = self.root

        # Logo panel
        logo_frame = tk.Frame(root, bg=BG)
        logo_frame.pack(fill="x", pady=(10, 0))

        tk.Label(
            logo_frame, text=LOGO,
            fg=ACCENT, bg=BG,
            font=(_MONO, 7), justify="center",
        ).pack()

        tk.Label(
            logo_frame,
            text="v3.1  ·  youtube downloader  ·  audio fx  ·  trim",
            fg=MUTED, bg=BG, font=FONT_SM,
        ).pack(pady=(2, 8))

        # Divider
        tk.Frame(root, bg=BORDER, height=1).pack(fill="x", padx=12)

        # Notebook
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook",     background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=SURFACE2, foreground=MUTED,
                        font=FONT, padding=[14, 7])
        style.map("TNotebook.Tab",
                  background=[("selected", SURFACE3)],
                  foreground=[("selected", ACCENT)])
        style.configure("TFrame", background=BG)

        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True, padx=8, pady=6)

        self.tab_dl   = ttk.Frame(nb, style="TFrame")
        self.tab_fx   = ttk.Frame(nb, style="TFrame")
        self.tab_trim = ttk.Frame(nb, style="TFrame")
        self.tab_log  = ttk.Frame(nb, style="TFrame")

        nb.add(self.tab_dl,   text="  ⬇  Stahování  ")
        nb.add(self.tab_fx,   text="  🎛  Audio FX  ")
        nb.add(self.tab_trim, text="  ✂  Trim  ")
        nb.add(self.tab_log,  text="  📋  Log  ")

        self._build_download_tab()
        self._build_fx_tab()
        self._build_trim_tab()
        self._build_log_tab()

        # Run button
        btn_frame = tk.Frame(root, bg=BG)
        btn_frame.pack(fill="x", padx=8, pady=(2, 10))

        self.run_btn = tk.Button(
            btn_frame,
            text="⬇   SPUSTIT KEČÍNOK   ⬇",
            bg=ACCENT2, fg="white",
            activebackground="#5c35cc", activeforeground="white",
            font=FONT_BIG, bd=0, cursor="hand2", pady=12,
            command=self._run,
        )
        self.run_btn.pack(fill="x")

        # Status bar
        self.status_var = tk.StringVar(value="připraven")
        status_bar = tk.Frame(root, bg=SURFACE, height=22)
        status_bar.pack(fill="x")
        tk.Label(status_bar, textvariable=self.status_var,
                 fg=MUTED, bg=SURFACE, font=FONT_SM,
                 anchor="w").pack(side="left", padx=8)

    # ── Tab: Stahování ────────────────────────────────────────────────────

    def _build_download_tab(self):
        f = self.tab_dl

        # URL vstupy
        self._section(f, "URL VSTUPY")
        self.url_container = tk.Frame(f, bg=BG)
        self.url_container.pack(fill="x", padx=10, pady=2)
        self._add_url_row()

        tk.Button(
            f, text="＋  přidat URL",
            bg=SURFACE2, fg=ACCENT2,
            font=FONT_SM, bd=0, relief="flat", cursor="hand2",
            padx=10, pady=4,
            command=self._add_url_row,
        ).pack(anchor="w", padx=10, pady=(0, 4))

        # Kvalita
        self._section(f, "KVALITA / FORMÁT")
        q_frame = tk.Frame(f, bg=BG)
        q_frame.pack(fill="x", padx=10, pady=4)

        qualities = list(QUALITY_MAP.keys())
        cols = 4
        for i, q in enumerate(qualities):
            is_audio = q.startswith(("MP3", "FLAC", "WAV"))
            fg_sel = GREEN if is_audio else ACCENT
            btn = tk.Radiobutton(
                q_frame, text=q,
                variable=self.quality, value=q,
                bg=SURFACE2, fg=TEXT,
                selectcolor=SURFACE3,
                activebackground=SURFACE2, activeforeground=fg_sel,
                font=FONT_SM, indicatoron=False,
                bd=1, relief="flat",
                padx=6, pady=6, cursor="hand2",
                highlightthickness=1,
                highlightbackground=BORDER,
            )
            btn.grid(row=i // cols, column=i % cols, padx=3, pady=3, sticky="ew")

        for c in range(cols):
            q_frame.columnconfigure(c, weight=1)

        # Výstupní složka
        self._section(f, "VÝSTUP")
        dir_frame = tk.Frame(f, bg=BG)
        dir_frame.pack(fill="x", padx=10, pady=4)

        tk.Entry(
            dir_frame, textvariable=self.out_dir,
            bg=SURFACE2, fg=TEXT, insertbackground=ACCENT,
            font=FONT, bd=0, relief="flat",
        ).pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 6))

        tk.Button(
            dir_frame, text="📁  procházet",
            bg=SURFACE3, fg=TEXT,
            font=FONT_SM, bd=0, relief="flat", cursor="hand2",
            padx=8, pady=5,
            command=self._browse_dir,
        ).pack(side="left")

        self._section(f, "ŠABLONA SOUBORU")
        tk.Entry(
            f, textvariable=self.out_tmpl,
            bg=SURFACE2, fg=TEXT, insertbackground=ACCENT,
            font=FONT, bd=0, relief="flat",
        ).pack(fill="x", padx=10, pady=4, ipady=6)

        tk.Label(
            f,
            text="  dostupné proměnné: %(title)s  %(id)s  %(uploader)s  %(upload_date)s  %(ext)s",
            fg=MUTED, bg=BG, font=FONT_SM, anchor="w",
        ).pack(fill="x", padx=10)

    def _add_url_row(self):
        row_frame = tk.Frame(self.url_container, bg=BG)
        row_frame.pack(fill="x", pady=2)

        idx_lbl = tk.Label(
            row_frame,
            text=f"{len(self.url_rows) + 1:02d}",
            fg=MUTED, bg=BG, font=FONT_SM, width=3,
        )
        idx_lbl.pack(side="left", padx=(0, 4))

        var = tk.StringVar()
        entry = tk.Entry(
            row_frame, textvariable=var,
            bg=SURFACE2, fg=TEXT, insertbackground=ACCENT,
            font=FONT, bd=0, relief="flat",
        )
        entry.pack(side="left", fill="x", expand=True, ipady=6)
        entry.insert(0, "https://")

        def _clear(e):
            if entry.get() in ("https://", ""):
                entry.delete(0, "end")

        def _refill(e):
            if not entry.get():
                entry.insert(0, "https://")

        entry.bind("<FocusIn>", _clear)
        entry.bind("<FocusOut>", _refill)

        def _remove():
            if len(self.url_rows) <= 1:
                return
            row_data = next((r for r in self.url_rows if r["frame"] is row_frame), None)
            if row_data:
                self.url_rows.remove(row_data)
            row_frame.destroy()
            self._reindex_urls()

        tk.Button(
            row_frame, text="✕",
            bg=BG, fg=RED,
            font=FONT_SM, bd=0, cursor="hand2",
            padx=6,
            command=_remove,
        ).pack(side="left", padx=4)

        self.url_rows.append({"var": var, "entry": entry, "frame": row_frame, "idx_lbl": idx_lbl})

    def _reindex_urls(self):
        for i, row in enumerate(self.url_rows):
            row["idx_lbl"].config(text=f"{i + 1:02d}")

    def _browse_dir(self):
        d = filedialog.askdirectory(initialdir=self.out_dir.get())
        if d:
            self.out_dir.set(d)

    # ── Tab: Audio FX ─────────────────────────────────────────────────────

    def _build_fx_tab(self):
        f = self.tab_fx
        self._section(f, "AUDIO EFEKTY")

        fx_defs = [
            ("speed",  "⏩ Tempo",          "zrychlení / zpomalení",        0.5,  2.0,  0.05, "×",  "%.2f"),
            ("pitch",  "🎼 Pitch",           "výška tónu v semitonech",      -12,  12,   1,    "st", "%+d"),
            ("bass",   "🔊 Bass boost",      "zesílení basů (+ limiter)",    5,    30,   1,    "dB", "+%d"),
            ("reverb", "🏛  Reverb",         "prostorový dozvuk",            0,    100,  5,    "%",  "%d"),
            ("echo",   "🔁 Echo",            "ozvěna v milisekundách",       100,  800,  50,   "ms", "%d"),
            ("stereo", "↔  Stereo widener",  "rozšíření stereo pole",        1.0,  10.0, 0.5,  "",   "%.1f"),
        ]

        for key, name, desc, lo, hi, step, unit, fmt in fx_defs:
            row = tk.Frame(f, bg=SURFACE, bd=0)
            row.pack(fill="x", padx=8, pady=2, ipady=5)

            tk.Checkbutton(
                row, variable=self.fx[key]["var"],
                bg=SURFACE, fg=TEXT, selectcolor=SURFACE3,
                activebackground=SURFACE,
                command=self._update_filterchain,
            ).pack(side="left", padx=(6, 2))

            tk.Label(
                row, text=name,
                bg=SURFACE, fg=TEXT, font=(_MONO, 10, "bold"),
                width=20, anchor="w",
            ).pack(side="left")

            tk.Label(
                row, text=desc,
                bg=SURFACE, fg=MUTED, font=FONT_SM, anchor="w",
            ).pack(side="left", expand=True, fill="x")

            val_lbl = tk.Label(row, text="—", bg=SURFACE, fg=ACCENT, font=FONT, width=8)
            val_lbl.pack(side="right", padx=(0, 8))
            self.fx_val_labels[key] = (val_lbl, fmt, unit)

            tk.Scale(
                row, variable=self.fx[key]["val"],
                from_=lo, to=hi, resolution=step,
                orient="horizontal", length=140,
                bg=SURFACE, fg=TEXT, troughcolor=DIM,
                highlightthickness=0, sliderrelief="flat", bd=0,
                command=lambda _=None, k=key: self._update_filterchain(),
            ).pack(side="right", padx=4)

        # loudnorm
        ln_row = tk.Frame(f, bg=SURFACE)
        ln_row.pack(fill="x", padx=8, pady=2, ipady=5)
        tk.Checkbutton(
            ln_row, variable=self.fx["loudnorm"]["var"],
            bg=SURFACE, fg=TEXT, selectcolor=SURFACE3,
            activebackground=SURFACE,
            command=self._update_filterchain,
        ).pack(side="left", padx=(6, 2))
        tk.Label(ln_row, text="📊 Loudnorm",
                 bg=SURFACE, fg=TEXT, font=(_MONO, 10, "bold"),
                 width=20, anchor="w").pack(side="left")
        tk.Label(ln_row, text="EBU R128 normalizace hlasitosti",
                 bg=SURFACE, fg=MUTED, font=FONT_SM).pack(side="left")
        tk.Label(ln_row, text="auto", bg=SURFACE, fg=MUTED, font=FONT_SM).pack(side="right", padx=8)

        # Filterchain preview
        self._section(f, "FFMPEG FILTERCHAIN")
        fc_frame = tk.Frame(f, bg=SURFACE2, bd=1, relief="flat")
        fc_frame.pack(fill="x", padx=8, pady=4)
        tk.Label(fc_frame, text="-af", fg=MUTED, bg=SURFACE2, font=FONT_SM).pack(side="left", padx=8)
        tk.Entry(
            fc_frame, textvariable=self.fc_var,
            state="readonly",
            readonlybackground=SURFACE2, fg=GREEN,
            font=FONT, bd=0, relief="flat",
        ).pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))

        self._update_filterchain()

    def _update_filterchain(self):
        filters = []
        fx = self.fx

        if fx["speed"]["var"].get():
            v = fx["speed"]["val"].get()
            filters.append(f"atempo={v:.2f}")
            self._set_fx_label("speed", v)
        else:
            self._set_fx_label("speed", None)

        if fx["pitch"]["var"].get():
            st = fx["pitch"]["val"].get()
            ratio = 2 ** (st / 12)
            inv = 1.0 / ratio
            filters.append(f"asetrate=44100*{ratio:.4f},aresample=44100,atempo={inv:.4f}")
            self._set_fx_label("pitch", st)
        else:
            self._set_fx_label("pitch", None)

        if fx["bass"]["var"].get():
            db = fx["bass"]["val"].get()
            filters.append(f"bass=g={db}:f=100:w=0.6")
            filters.append("alimiter=limit=1.0:level=false")
            self._set_fx_label("bass", db)
        else:
            self._set_fx_label("bass", None)

        if fx["reverb"]["var"].get():
            wet = fx["reverb"]["val"].get() / 100
            filters.append(f"aecho=0.8:0.88:60:{wet:.2f}")
            self._set_fx_label("reverb", fx["reverb"]["val"].get())
        else:
            self._set_fx_label("reverb", None)

        if fx["echo"]["var"].get():
            delay = fx["echo"]["val"].get()
            filters.append(f"aecho=0.8:0.6:{delay}:0.4")
            self._set_fx_label("echo", delay)
        else:
            self._set_fx_label("echo", None)

        if fx["stereo"]["var"].get():
            w = fx["stereo"]["val"].get()
            filters.append(f"stereotools=mlev={w:.1f}")
            self._set_fx_label("stereo", w)
        else:
            self._set_fx_label("stereo", None)

        if fx["loudnorm"]["var"].get():
            filters.append("loudnorm=I=-16:TP=-1.5:LRA=11")

        self.fc_var.set(",".join(filters) if filters else "acopy")

    def _set_fx_label(self, key: str, val):
        if key not in self.fx_val_labels:
            return
        lbl, fmt, unit = self.fx_val_labels[key]
        if val is None:
            lbl.config(text="—", fg=MUTED)
        else:
            try:
                txt = (fmt % val) + unit
            except TypeError:
                txt = str(val) + unit
            lbl.config(text=txt, fg=ACCENT)

    # ── Tab: Trim ─────────────────────────────────────────────────────────

    def _build_trim_tab(self):
        f = self.tab_trim

        self._section(f, "OŘEZ ČASOVÉHO ÚSEKU")

        toggle_row = tk.Frame(f, bg=BG)
        toggle_row.pack(fill="x", padx=10, pady=8)
        tk.Checkbutton(
            toggle_row,
            text="  Aktivovat trim  —  ořízne video/audio na zadaný úsek",
            variable=self.trim_enabled,
            bg=BG, fg=TEXT,
            selectcolor=SURFACE3,
            activebackground=BG, activeforeground=ACCENT,
            font=FONT,
            command=self._toggle_trim_ui,
        ).pack(anchor="w")

        self.trim_frame = tk.Frame(f, bg=SURFACE, bd=1, relief="flat")
        self.trim_frame.pack(fill="x", padx=10, pady=4)

        inner = tk.Frame(self.trim_frame, bg=SURFACE)
        inner.pack(fill="x", padx=14, pady=12)

        # Start
        tk.Label(inner, text="START", fg=MUTED, bg=SURFACE, font=FONT_SM, anchor="w", width=8).grid(
            row=0, column=0, sticky="w", pady=2)
        self.trim_start_entry = tk.Entry(
            inner, textvariable=self.trim_start,
            bg=SURFACE3, fg=TEXT, insertbackground=ACCENT,
            font=(_MONO, 12), bd=0, relief="flat", width=14, justify="center",
        )
        self.trim_start_entry.grid(row=0, column=1, padx=8, ipady=8)
        tk.Label(inner, text="HH:MM:SS  nebo sekundy", fg=MUTED, bg=SURFACE, font=FONT_SM).grid(
            row=0, column=2, sticky="w")

        # End
        tk.Label(inner, text="KONEC", fg=MUTED, bg=SURFACE, font=FONT_SM, anchor="w", width=8).grid(
            row=1, column=0, sticky="w", pady=2)
        self.trim_end_entry = tk.Entry(
            inner, textvariable=self.trim_end,
            bg=SURFACE3, fg=TEXT, insertbackground=ACCENT,
            font=(_MONO, 12), bd=0, relief="flat", width=14, justify="center",
        )
        self.trim_end_entry.grid(row=1, column=1, padx=8, ipady=8)
        tk.Label(inner, text="HH:MM:SS  nebo sekundy  (prázdné = do konce)",
                 fg=MUTED, bg=SURFACE, font=FONT_SM).grid(row=1, column=2, sticky="w")

        # Délka výpočet (live preview)
        self.trim_duration_lbl = tk.Label(inner, text="", fg=ACCENT, bg=SURFACE, font=FONT)
        self.trim_duration_lbl.grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))

        self.trim_start.trace_add("write", self._update_trim_preview)
        self.trim_end.trace_add("write", self._update_trim_preview)

        # Příklady
        self._section(f, "PŘÍKLADY")
        examples = [
            ("Prvních 30 sekund",  "0",     "30"),
            ("Od 1:30 do 4:00",    "1:30",  "4:00"),
            ("Od 45 s do konce",   "45",    ""),
            ("Minuty 10–15",       "10:00", "15:00"),
        ]
        eg_frame = tk.Frame(f, bg=BG)
        eg_frame.pack(fill="x", padx=10)
        for label, start, end in examples:
            def _apply(s=start, e=end):
                self.trim_start.set(s)
                self.trim_end.set(e)
                self.trim_enabled.set(True)
                self._toggle_trim_ui()

            row = tk.Frame(eg_frame, bg=SURFACE2)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=label, fg=TEXT, bg=SURFACE2, font=FONT_SM,
                     width=28, anchor="w").pack(side="left", padx=8)
            tk.Label(row, text=f"start: {start or '—':>8}   konec: {end or 'EOF':>8}",
                     fg=MUTED, bg=SURFACE2, font=FONT_SM).pack(side="left")
            tk.Button(
                row, text="použít",
                bg=SURFACE3, fg=ACCENT, font=FONT_SM,
                bd=0, relief="flat", cursor="hand2", padx=8, pady=3,
                command=_apply,
            ).pack(side="right", padx=6, pady=3)

        # Poznámka
        tk.Label(
            f,
            text=("  ℹ  Trim se provede přes ffmpeg po stažení. U videa se kvůli přesnému "
                  "ořezu překóduje obraz (trvá o něco déle), audio se ořezává rychle."),
            fg=MUTED, bg=BG, font=FONT_SM, anchor="w", wraplength=700, justify="left",
        ).pack(fill="x", padx=10, pady=6)

        self._toggle_trim_ui()

    def _toggle_trim_ui(self):
        enabled = self.trim_enabled.get()
        state = "normal" if enabled else "disabled"
        bg = SURFACE3 if enabled else DIM
        fg = TEXT if enabled else MUTED
        for widget in (self.trim_start_entry, self.trim_end_entry):
            widget.config(state=state, bg=bg, fg=fg)
        self._update_trim_preview()

    def _update_trim_preview(self, *_):
        if not self.trim_enabled.get():
            self.trim_duration_lbl.config(text="")
            return
        start_s = parse_time_to_seconds(self.trim_start.get())
        end_s   = parse_time_to_seconds(self.trim_end.get())
        if start_s is None:
            self.trim_duration_lbl.config(text="→  zadej čas startu", fg=WARN)
            return
        if end_s is not None and end_s <= start_s:
            self.trim_duration_lbl.config(text="⚠  KONEC musí být za STARTem", fg=RED)
            return
        if end_s is not None:
            dur = end_s - start_s
            self.trim_duration_lbl.config(
                text=f"→  délka úseku: {seconds_to_hhmmss(dur)}  ({dur:.1f} s)", fg=ACCENT,
            )
        else:
            self.trim_duration_lbl.config(
                text=f"→  start: {seconds_to_hhmmss(start_s)}  →  do konce souboru", fg=ACCENT,
            )

    # ── Tab: Log ──────────────────────────────────────────────────────────

    def _build_log_tab(self):
        f = self.tab_log

        toolbar = tk.Frame(f, bg=SURFACE)
        toolbar.pack(fill="x")
        tk.Label(toolbar, text="  výstup", fg=MUTED, bg=SURFACE, font=FONT_SM).pack(side="left", padx=4)
        tk.Button(
            toolbar, text="vymazat",
            bg=SURFACE, fg=MUTED, font=FONT_SM,
            bd=0, relief="flat", cursor="hand2", padx=8, pady=3,
            command=self._clear_log,
        ).pack(side="right")

        self.log_text = tk.Text(
            f, bg="#06090e", fg="#7ee8a2",
            font=(_MONO, 10), bd=0,
            state="disabled", wrap="word",
            insertbackground=ACCENT,
        )
        sb = tk.Scrollbar(f, command=self.log_text.yview, bg=SURFACE, troughcolor=SURFACE2)
        self.log_text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log_text.pack(fill="both", expand=True, padx=2, pady=2)

        self._log("Kečínok v3.1 ✅  připraven")
        self._log("Přidej URL → vyber kvalitu → (volitelně FX/Trim) → SPUSTIT\n")

    def _log(self, msg: str, replace: bool = False):
        """Thread-safe log. replace=True přepíše předchozí řádek (progress)."""
        def _do():
            self.log_text.config(state="normal")
            if replace and self._last_was_progress:
                # smaž poslední řádek (text končí "\n")
                self.log_text.delete("end-2l linestart", "end-1c")
            self.log_text.insert("end", msg + "\n")
            self._last_was_progress = replace
            self.log_text.see("end")
            self.log_text.config(state="disabled")
        self.root.after(0, _do)

    def _clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")
        self._last_was_progress = False

    def _set_status(self, msg: str):
        self.root.after(0, lambda: self.status_var.set(msg))

    # ── Helper: sekce nadpis ──────────────────────────────────────────────

    def _section(self, parent: tk.Widget, text: str):
        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill="x", padx=8, pady=(10, 2))
        tk.Frame(frame, bg=ACCENT, width=3, height=14).pack(side="left")
        tk.Label(frame, text=f"  {text}",
                 fg=ACCENT, bg=BG, font=(_MONO, 8)).pack(side="left")

    # ── Validace trimmingu ────────────────────────────────────────────────

    def _validate_trim(self):
        """Vrátí (start_s, end_s) nebo None při chybě. end_s může být None."""
        if not self.trim_enabled.get():
            return (None, None)
        start_s = parse_time_to_seconds(self.trim_start.get())
        end_s   = parse_time_to_seconds(self.trim_end.get())
        if start_s is None:
            messagebox.showerror("Trim", "Neplatný čas STARTU!\nPoužij formát HH:MM:SS nebo sekundy.")
            return None
        if end_s is not None and end_s <= start_s:
            messagebox.showerror("Trim", "KONEC musí být za STARTem!")
            return None
        return (start_s, end_s)

    # ── Stahování ─────────────────────────────────────────────────────────

    def _run(self):
        if self.running:
            return

        urls = [
            r["var"].get().strip()
            for r in self.url_rows
            if r["var"].get().strip() not in ("", "https://")
        ]
        if not urls:
            messagebox.showwarning("Kečínok", "Zadej aspoň jednu URL!")
            return

        trim = self._validate_trim()
        if trim is None:
            return

        self.running = True
        self.run_btn.config(state="disabled", text="⏳  probíhá stahování...")
        self._set_status("stahování...")
        threading.Thread(target=self._download_thread, args=(urls, trim), daemon=True).start()

    def _download_thread(self, urls: list[str], trim: tuple):
        import re
        import tempfile

        def strip_ansi(s: str) -> str:
            return re.sub(r"\x1b\[[0-9;]*m", "", s or "")

        app = self

        class YDLLogger:
            """Přesměruje výstup yt-dlp do logu (nutné pro --noconsole)."""
            def debug(self, msg):
                pass
            def info(self, msg):
                pass
            def warning(self, msg):
                app._log(f"[WARN] {strip_ansi(msg)}")
            def error(self, msg):
                app._log(f"[ERR]  {strip_ansi(msg)}")

        tmp_dir = None
        downloaded_files: list[str] = []

        try:
            try:
                from yt_dlp import YoutubeDL
            except ImportError:
                if FROZEN:
                    raise RuntimeError(
                        "yt-dlp není v .exe zabalený. Zkompiluj znovu s "
                        "--collect-all yt_dlp."
                    )
                self._log("[INFO] Instaluji yt-dlp...")
                run_quiet(
                    [sys.executable, "-m", "pip", "install", "yt-dlp"],
                    check=True, capture_output=True,
                )
                from yt_dlp import YoutubeDL

            try:
                from yt_dlp.version import __version__ as ytdlp_ver
                self._log(f"[INFO] yt-dlp verze: {ytdlp_ver}")
            except Exception:
                pass

            quality   = self.quality.get()
            fmt       = QUALITY_MAP[quality]
            out_dir   = self.out_dir.get()
            template  = self.out_tmpl.get()
            fc        = self.fc_var.get()
            apply_fx  = fc != "acopy"
            trim_start_s, trim_end_s = trim
            apply_trim = trim_start_s is not None

            needs_postproc = apply_fx or apply_trim
            if needs_postproc:
                tmp_dir = tempfile.mkdtemp(prefix="kecinok_")
                dl_dir  = tmp_dir
            else:
                dl_dir  = out_dir

            os.makedirs(out_dir, exist_ok=True)

            def _pp_hook(d):
                if d.get("status") == "finished":
                    fp = (d.get("info_dict", {}).get("filepath")
                          or d.get("filepath")
                          or d.get("filename", ""))
                    if fp and os.path.isfile(fp) and fp not in downloaded_files:
                        downloaded_files.append(fp)
                        self._log(f"[✅] Připraven: {os.path.basename(fp)}")

            def _progress_hook(d):
                if d["status"] == "downloading":
                    fn  = strip_ansi(os.path.basename(d.get("filename", "?")))
                    pct = strip_ansi(d.get("_percent_str", "?%")).strip()
                    spd = strip_ansi(d.get("_speed_str", "?")).strip()
                    eta = strip_ansi(d.get("_eta_str", "?")).strip()
                    self._log(f"[DL]  {fn}  {pct}  @ {spd}  ETA {eta}", replace=True)
                    self._set_status(f"stahování {pct}")
                elif d["status"] == "finished":
                    fn = strip_ansi(os.path.basename(d.get("filename", "?")))
                    self._log(f"[→]   merge/postprocess: {fn}")

            ydl_opts: dict = {
                "format":               fmt,
                "outtmpl":              os.path.join(dl_dir, template),
                "merge_output_format":  "mp4",
                "progress_hooks":       [_progress_hook],
                "postprocessor_hooks":  [_pp_hook],
                "logger":               YDLLogger(),
                "noprogress":           True,
                "retries":              10,
                "fragment_retries":     10,
                "extractor_retries":    3,
                "socket_timeout":       30,
                "extractor_args":       {"youtube": {"player_client": ["default", "web_safari"]}},
            }

            local_bin = ffmpeg_local_bin()
            if os.path.isdir(local_bin):
                ydl_opts["ffmpeg_location"] = local_bin

            if quality in AUDIO_POSTPROC:
                codec, bitrate = AUDIO_POSTPROC[quality]
                pp: dict = {"key": "FFmpegExtractAudio", "preferredcodec": codec}
                if bitrate:
                    pp["preferredquality"] = bitrate
                ydl_opts["postprocessors"] = [pp]

            self._log(f"\n[INFO] Startuji — {len(urls)} URL(s)...")

            with YoutubeDL(ydl_opts) as ydl:
                ydl.download(urls)

            # Fallback: pokud pp_hook nic nenachytal
            if needs_postproc and not downloaded_files and tmp_dir:
                for root_, _, files in os.walk(tmp_dir):
                    for fn in files:
                        fp = os.path.join(root_, fn)
                        if os.path.isfile(fp):
                            downloaded_files.append(fp)
                self._log(f"[INFO] Fallback scan: {len(downloaded_files)} soubor(ů)")

            # ── Postprocessing: FX + Trim ──────────────────────────────────
            if needs_postproc and downloaded_files:
                for src in downloaded_files:
                    name = os.path.basename(src)
                    dst  = os.path.join(out_dir, name)
                    is_audio_file = name.lower().endswith(AUDIO_EXTS)
                    self._log(f"\n[PP]  {name}")

                    cmd = ["ffmpeg", "-y"]

                    if apply_trim:
                        cmd += ["-ss", str(trim_start_s)]
                        if trim_end_s is not None:
                            cmd += ["-to", str(trim_end_s)]
                        self._log(f"      trim: {seconds_to_hhmmss(trim_start_s)} → "
                                  f"{seconds_to_hhmmss(trim_end_s) if trim_end_s else 'EOF'}")

                    cmd += ["-i", src]
                    cmd += ["-map", "0:v?", "-map", "0:a"]

                    # Video: při trimu překódovat kvůli přesnosti (copy řeže po keyframech)
                    if apply_trim and not is_audio_file:
                        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]
                    else:
                        cmd += ["-c:v", "copy"]

                    if apply_fx:
                        self._log(f"      fx:   {fc}")
                        cmd += ["-af", fc]
                        if name.lower().endswith(".mp3"):
                            cmd += ["-b:a", "320k"]
                        elif not is_audio_file:
                            cmd += ["-c:a", "aac", "-b:a", "192k"]
                    else:
                        cmd += ["-c:a", "copy"]

                    cmd.append(dst)

                    result = run_quiet(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                    )

                    if result.returncode != 0:
                        self._log(f"[WARN] ffmpeg selhal pro {name}:")
                        for line in result.stderr.strip().splitlines()[-5:]:
                            self._log(f"       {line}")
                        shutil.copy2(src, dst)
                        self._log("[WARN] Uloženo bez postprocessingu (fallback).")
                    else:
                        self._log(f"[✅]  Hotovo: {name}")

            elif needs_postproc and not downloaded_files:
                self._log("[WARN] Žádné soubory k postprocessingu.")

            self._log(f"\n[DONE] ✅  Vše dokončeno! → {out_dir}")
            self._set_status(f"hotovo — {len(downloaded_files)} soubor(ů)")

        except Exception as e:
            self._log(f"\n[ERROR] ❌  {e}")
            self._set_status("chyba — viz Log")
        finally:
            if tmp_dir:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            self.running = False
            self.root.after(0, lambda: self.run_btn.config(
                state="normal", text="⬇   SPUSTIT KEČÍNOK   ⬇",
            ))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    # U --noconsole buildů je sys.stdout / sys.stderr None a print() by spadl
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")

    print(__doc__)

    root = tk.Tk()
    root.geometry("820x700")
    root.minsize(760, 560)
    init_fonts(root)
    KecInokApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
