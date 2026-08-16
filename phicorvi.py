#!/usr/bin/env python3
"""
PhiCorvi -- a small control panel for a local Japanese voice.

Everything the bridge does, with buttons instead of a terminal: start and stop it,
pick which voices it offers, preview them, and copy the URL to paste into Yomitan.

Needs only Python 3 and a running VOICEVOX engine. No libraries to install.
Run it with:  python3 phicorvi.py
"""

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from tkinter import messagebox, ttk

# Packaged as a one-file .exe, __file__ points into a temporary extraction folder
# that is deleted on exit -- settings saved there would vanish every run. Sit next
# to the executable the user actually double-clicked instead.
if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "phicorvi_config.json")

DEFAULTS = {
    "engine": "http://127.0.0.1:50021",
    "port": 8772,
    "speakers": [19, 96],
    "speed": 0.95,
    "intonation": 0.9,
    "theme": "light",
    "was_running": True,
}

# Ports Chromium refuses to open (ERR_UNSAFE_PORT), plus ones commonly taken by
# other Japanese-mining tools. Warn rather than let people debug silent audio.
BLOCKED_PORTS = {
    5060: "SIP - browsers refuse to connect",
    5061: "SIP-TLS - browsers refuse to connect",
}
BUSY_PORTS = {5050: "local-audio-yomichan", 8765: "AnkiConnect", 8770: "Forvo server"}

# Daylight sky above, night sky below. The accent is the same blue shifted for
# contrast, so the app reads as one colour scheme in either mode.
PALETTES = {
    "light": {
        "bg": "#e7f2fb",
        "surface": "#ffffff",
        "field": "#ffffff",
        "readonly": "#f2f8fd",
        "ink": "#10293f",
        "muted": "#456780",
        "faint": "#53748d",
        "border": "#b9d9f1",
        "accent": "#0f66b0",
        "accent_ink": "#ffffff",
        "accent_hover": "#0b5390",
        "sel_bg": "#cfe6fa",
        "ok": "#1f7a4d",
        "bad": "#b3261e",
    },
    "dark": {
        "bg": "#0d1a26",
        "surface": "#152736",
        "field": "#1b2f42",
        "readonly": "#16293a",
        "ink": "#dceaf6",
        "muted": "#8fadc7",
        "faint": "#7c9db8",
        "border": "#2a4b68",
        "accent": "#4ea8e8",
        "accent_ink": "#08151f",
        "accent_hover": "#6bbcf2",
        "sel_bg": "#24506f",
        "ok": "#5cc98d",
        "bad": "#ff8f85",
    },
}

state = dict(DEFAULTS)
_cache = {}
_names = {}
_server = None
_server_thread = None


# ---------------------------------------------------------------- engine calls

def _post(path, data=None):
    req = urllib.request.Request(
        state["engine"] + path,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method="POST",
    )
    return urllib.request.urlopen(req, timeout=30).read()


def engine_alive():
    try:
        urllib.request.urlopen(state["engine"] + "/version", timeout=3).read()
        return True
    except Exception:
        return False


def fetch_voices():
    raw = urllib.request.urlopen(state["engine"] + "/speakers", timeout=15).read()
    out = []
    for sp in json.loads(raw):
        for st in sp["styles"]:
            out.append((st["id"], sp["name"], st["name"]))
    return sorted(out)


def synthesize(text, speaker):
    key = (speaker, text, state["speed"], state["intonation"])
    if key in _cache:
        return _cache[key]
    q = json.loads(
        _post("/audio_query?speaker=%d&text=%s" % (speaker, urllib.parse.quote(text)))
    )
    q["speedScale"] = state["speed"]
    q["intonationScale"] = state["intonation"]
    audio = _post("/synthesis?speaker=%d" % speaker, json.dumps(q).encode())
    if len(_cache) >= 256:
        _cache.clear()
    _cache[key] = audio
    return audio


def play_wav(data):
    path = os.path.join(tempfile.gettempdir(), "voicevox_preview.wav")
    with open(path, "wb") as fh:
        fh.write(data)
    system = platform.system()
    try:
        if system == "Windows":
            import winsound

            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        elif system == "Darwin":
            subprocess.Popen(["afplay", path])
        else:
            for player in ("paplay", "aplay", "ffplay"):
                if shutil.which(player):
                    args = [player, path]
                    if player == "ffplay":
                        args = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path]
                    subprocess.Popen(args, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
                    return True
            return False
    except Exception:
        return False
    return True


# ------------------------------------------------------------------ the bridge

class Handler(BaseHTTPRequestHandler):
    def _send(self, body, ctype, status=200):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        # Speak the reading, not the kanji -- TTS mispronounces rare words otherwise.
        text = (params.get("reading") or params.get("term") or [""])[0].strip()
        speakers = list(state["speakers"]) or [DEFAULTS["speakers"][0]]

        if not text:
            self._send(b'{"type":"audioSourceList","audioSources":[]}', "application/json")
            return
        try:
            if parsed.path.rstrip("/") in ("", "/list"):
                # Echo back whichever host the caller used: Manatan rejects any URL
                # whose host looks local, so a hardcoded "localhost" would get the
                # whole list discarded.
                host = self.headers.get("Host") or "localhost:%d" % state["port"]
                srcs = [
                    {
                        "name": _names.get(sid, "speaker %d" % sid),
                        "url": "http://%s/audio.wav?speaker=%d&reading=%s"
                        % (host, sid, urllib.parse.quote(text)),
                    }
                    for sid in speakers
                ]
                body = json.dumps(
                    {"type": "audioSourceList", "audioSources": srcs}, ensure_ascii=False
                ).encode("utf-8")
                self._send(body, "application/json; charset=utf-8")
            else:
                asked = (params.get("speaker") or [""])[0]
                sid = int(asked) if asked.isdigit() else speakers[0]
                self._send(synthesize(text, sid), "audio/wav")
        except urllib.error.URLError as exc:
            self._send(
                ("VOICEVOX unreachable at %s (%s)" % (state["engine"], exc)).encode(),
                "text/plain",
                502,
            )

    def log_message(self, *args):
        pass


def start_bridge():
    global _server, _server_thread
    _server = ThreadingHTTPServer(("127.0.0.1", state["port"]), Handler)
    _server_thread = threading.Thread(target=_server.serve_forever, daemon=True)
    _server_thread.start()


def stop_bridge():
    global _server, _server_thread
    if _server:
        _server.shutdown()
        _server.server_close()
    _server, _server_thread = None, None


def bridge_running():
    return _server is not None


# ------------------------------------------------------------------------- gui

PLACEHOLDER = "search, e.g. whisper or sasayaki"


class App:
    def __init__(self, root):
        self.root = root
        root.title("PhiCorvi")
        root.minsize(700, 680)
        root.geometry("760x720")

        self.all_voices = []
        self.filtered = []
        self.hints = []

        load_config()
        self.style = ttk.Style()
        self.style.theme_use("clam")

        self.outer = ttk.Frame(root, padding=14)
        self.outer.pack(fill="both", expand=True)
        self.outer.columnconfigure(0, weight=1)

        self._build_status(self.outer)
        self._build_voices(self.outer)
        self._build_tuning(self.outer)
        self._build_connect(self.outer)
        self.outer.rowconfigure(1, weight=1)

        self.port_var.set(str(state["port"]))
        self.speed_var.set("%.2f" % state["speed"])
        self.intonation_var.set("%.2f" % state["intonation"])
        self.apply_theme()
        self.refresh_selected()
        self.update_urls()

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.poll_status()
        self.load_voices_async()
        # Pick up where the last session left off, so opening the app is usually
        # the only step -- forgetting to press Start is the classic way to end up
        # with silent lookups.
        if state.get("was_running"):
            self.root.after(400, self.autostart)

    def autostart(self):
        if bridge_running():
            return
        try:
            start_bridge()
        except OSError:
            return  # something else holds the port; leave it to the user
        self.start_btn.configure(text="Stop")
        self.refresh_status_colors()

    # -- theming ----------------------------------------------------------

    @property
    def colors(self):
        return PALETTES.get(state["theme"], PALETTES["light"])

    def apply_theme(self):
        c = self.colors
        s = self.style
        self.root.configure(bg=c["bg"])

        s.configure(".", background=c["bg"], foreground=c["ink"],
                    fieldbackground=c["field"], bordercolor=c["border"],
                    lightcolor=c["border"], darkcolor=c["border"],
                    focuscolor=c["accent"])
        s.configure("TFrame", background=c["bg"])
        s.configure("TLabel", background=c["bg"], foreground=c["ink"])
        s.configure("Hint.TLabel", background=c["bg"], foreground=c["faint"])
        s.configure("TSeparator", background=c["border"])

        s.configure("TLabelframe", background=c["surface"], bordercolor=c["border"],
                    lightcolor=c["border"], darkcolor=c["border"], relief="solid",
                    borderwidth=1)
        s.configure("TLabelframe.Label", background=c["surface"],
                    foreground=c["accent"], font=("TkDefaultFont", 9, "bold"))
        s.configure("Card.TFrame", background=c["surface"])
        s.configure("Card.TLabel", background=c["surface"], foreground=c["ink"])
        s.configure("CardHint.TLabel", background=c["surface"], foreground=c["faint"])

        s.configure("TButton", background=c["surface"], foreground=c["ink"],
                    bordercolor=c["border"], padding=(10, 5), relief="flat")
        s.map("TButton",
              background=[("pressed", c["sel_bg"]), ("active", c["sel_bg"])],
              foreground=[("disabled", c["faint"])])

        s.configure("Accent.TButton", background=c["accent"],
                    foreground=c["accent_ink"], bordercolor=c["accent"],
                    padding=(10, 6), relief="flat",
                    font=("TkDefaultFont", 9, "bold"))
        s.map("Accent.TButton",
              background=[("pressed", c["accent_hover"]), ("active", c["accent_hover"])],
              foreground=[("active", c["accent_ink"])])

        s.configure("TEntry", fieldbackground=c["field"], foreground=c["ink"],
                    bordercolor=c["border"], insertcolor=c["ink"], padding=4)
        s.map("TEntry", fieldbackground=[("readonly", c["readonly"])],
              foreground=[("readonly", c["muted"])])
        s.configure("TSpinbox", fieldbackground=c["field"], foreground=c["ink"],
                    bordercolor=c["border"], arrowcolor=c["accent"],
                    insertcolor=c["ink"], padding=3)

        for box in (self.available, self.selected):
            box.configure(bg=c["field"], fg=c["ink"], selectbackground=c["sel_bg"],
                          selectforeground=c["ink"], highlightthickness=1,
                          highlightbackground=c["border"],
                          highlightcolor=c["accent"], borderwidth=0,
                          relief="flat")

        for label in self.hints:
            label.configure(style="CardHint.TLabel")

        self.search.configure(
            foreground=c["faint"] if self.search.get() == PLACEHOLDER else c["ink"])
        self.theme_btn.configure(
            text="Dark theme" if state["theme"] == "light" else "Light theme")
        self.refresh_status_colors()

    def toggle_theme(self):
        state["theme"] = "dark" if state["theme"] == "light" else "light"
        self.apply_theme()
        save_config()

    # -- sections ---------------------------------------------------------

    def _build_status(self, parent):
        box = ttk.LabelFrame(parent, text=" Status ", padding=12)
        box.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        box.columnconfigure(1, weight=1)

        ttk.Label(box, text="VOICEVOX engine", style="Card.TLabel").grid(
            row=0, column=0, sticky="w")
        self.engine_label = ttk.Label(box, text="checking...", style="Card.TLabel")
        self.engine_label.grid(row=0, column=1, sticky="w", padx=(10, 0))

        ttk.Label(box, text="Bridge", style="Card.TLabel").grid(
            row=1, column=0, sticky="w", pady=(6, 0))
        self.bridge_label = ttk.Label(box, text="stopped", style="Card.TLabel")
        self.bridge_label.grid(row=1, column=1, sticky="w", padx=(10, 0), pady=(6, 0))

        side = ttk.Frame(box, style="Card.TFrame")
        side.grid(row=0, column=2, rowspan=2, sticky="e")
        self.start_btn = ttk.Button(side, text="Start", width=13,
                                    style="Accent.TButton", command=self.toggle_bridge)
        self.start_btn.pack()
        self.theme_btn = ttk.Button(side, text="Dark theme", width=13,
                                    command=self.toggle_theme)
        self.theme_btn.pack(pady=(6, 0))

    def _build_voices(self, parent):
        box = ttk.LabelFrame(parent, text=" Voices ", padding=12)
        box.grid(row=1, column=0, sticky="nsew")
        box.columnconfigure(0, weight=3)
        box.columnconfigure(2, weight=2)
        box.rowconfigure(2, weight=1)

        ttk.Label(box, text="Available", style="Card.TLabel").grid(
            row=0, column=0, sticky="w")
        ttk.Label(box, text="Used by Yomitan (in order)", style="Card.TLabel").grid(
            row=0, column=2, sticky="w")

        self.search_var = tk.StringVar()
        self.search = ttk.Entry(box, textvariable=self.search_var)
        self.search.grid(row=1, column=0, sticky="ew", pady=(5, 7))
        self.search.insert(0, PLACEHOLDER)
        self.search.bind("<FocusIn>", self._search_focus)
        self.search.bind("<FocusOut>", self._search_blur)

        self.available = tk.Listbox(box, exportselection=False, activestyle="none",
                                    height=9)
        self.available.grid(row=2, column=0, sticky="nsew")
        self.available.bind("<Double-Button-1>", lambda e: self.add_voice())

        mid = ttk.Frame(box, style="Card.TFrame")
        mid.grid(row=2, column=1, padx=12, sticky="n")
        ttk.Button(mid, text="Add →", width=11, command=self.add_voice).pack(pady=2)
        ttk.Button(mid, text="← Remove", width=11, command=self.remove_voice).pack(pady=2)
        ttk.Separator(mid, orient="horizontal").pack(fill="x", pady=9)
        ttk.Button(mid, text="Move up", width=11, command=lambda: self.move(-1)).pack(pady=2)
        ttk.Button(mid, text="Move down", width=11, command=lambda: self.move(1)).pack(pady=2)
        ttk.Separator(mid, orient="horizontal").pack(fill="x", pady=9)
        ttk.Button(mid, text="Preview", width=11, style="Accent.TButton",
                   command=self.preview).pack(pady=2)

        self.selected = tk.Listbox(box, exportselection=False, activestyle="none",
                                   height=9)
        self.selected.grid(row=2, column=2, sticky="nsew")

        hint = ttk.Label(
            box,
            text="Yomitan plays the first voice that works. Preview uses whichever row "
                 "is highlighted.",
            wraplength=660, style="CardHint.TLabel")
        hint.grid(row=3, column=0, columnspan=3, sticky="w", pady=(9, 0))
        self.hints.append(hint)

        # Attach last: setting the placeholder text fires this, and the listbox it
        # filters has to exist by then.
        self.search_var.trace_add("write", lambda *_: self.apply_filter())

    def _build_tuning(self, parent):
        box = ttk.LabelFrame(parent, text=" Settings ", padding=12)
        box.grid(row=2, column=0, sticky="ew", pady=(12, 0))

        ttk.Label(box, text="Port", style="Card.TLabel").grid(row=0, column=0, sticky="w")
        self.port_var = tk.StringVar()
        ttk.Entry(box, textvariable=self.port_var, width=8).grid(
            row=0, column=1, padx=(8, 22))

        ttk.Label(box, text="Speed", style="Card.TLabel").grid(row=0, column=2, sticky="w")
        self.speed_var = tk.StringVar()
        ttk.Spinbox(box, from_=0.5, to=1.5, increment=0.05, width=6,
                    textvariable=self.speed_var).grid(row=0, column=3, padx=(8, 22))

        ttk.Label(box, text="Intonation", style="Card.TLabel").grid(
            row=0, column=4, sticky="w")
        self.intonation_var = tk.StringVar()
        ttk.Spinbox(box, from_=0.0, to=1.5, increment=0.05, width=6,
                    textvariable=self.intonation_var).grid(row=0, column=5, padx=(8, 0))

        hint = ttk.Label(box, text="Lower intonation = flatter, calmer delivery.",
                         style="CardHint.TLabel")
        hint.grid(row=1, column=0, columnspan=6, sticky="w", pady=(9, 0))
        self.hints.append(hint)

    def _build_connect(self, parent):
        box = ttk.LabelFrame(parent, text=" Connect ", padding=12)
        box.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        box.columnconfigure(1, weight=1)

        ttk.Label(box, text="Yomitan", style="Card.TLabel").grid(row=0, column=0, sticky="w")
        self.yomitan_var = tk.StringVar()
        ttk.Entry(box, textvariable=self.yomitan_var, state="readonly").grid(
            row=0, column=1, sticky="ew", padx=10)
        ttk.Button(box, text="Copy", width=9,
                   command=lambda: self.copy(self.yomitan_var.get())).grid(row=0, column=2)

        ttk.Label(box, text="Manatan", style="Card.TLabel").grid(
            row=1, column=0, sticky="w", pady=(7, 0))
        self.manatan_var = tk.StringVar()
        ttk.Entry(box, textvariable=self.manatan_var, state="readonly").grid(
            row=1, column=1, sticky="ew", padx=10, pady=(7, 0))
        ttk.Button(box, text="Copy", width=9,
                   command=lambda: self.copy(self.manatan_var.get())).grid(
            row=1, column=2, pady=(7, 0))

        hint = ttk.Label(
            box,
            text="Yomitan: Settings → Audio → add a Custom URL (JSON) source, "
                 "paste, then drag it to the top of the list.",
            wraplength=660, style="CardHint.TLabel")
        hint.grid(row=2, column=0, columnspan=3, sticky="w", pady=(9, 0))
        self.hints.append(hint)

    # -- helpers ----------------------------------------------------------

    def _search_focus(self, _):
        if self.search.get() == PLACEHOLDER:
            self.search.delete(0, "end")
            self.search.configure(foreground=self.colors["ink"])

    def _search_blur(self, _):
        if not self.search.get():
            self.search.insert(0, PLACEHOLDER)
            self.search.configure(foreground=self.colors["faint"])

    def search_text(self):
        value = self.search_var.get()
        return "" if value == PLACEHOLDER else value.lower().strip()

    def label_for(self, sid):
        return _names.get(sid, "speaker %d" % sid)

    def copy(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    # -- voices -----------------------------------------------------------

    def load_voices_async(self):
        def work():
            try:
                voices = fetch_voices()
            except Exception:
                voices = []
            self.root.after(0, lambda: self.on_voices(voices))

        threading.Thread(target=work, daemon=True).start()

    def on_voices(self, voices):
        self.all_voices = voices
        for sid, speaker, style in voices:
            _names[sid] = "%s (%s)" % (speaker, style)
        self.apply_filter()
        self.refresh_selected()

    def apply_filter(self):
        needle = self.search_text()
        # "whisper" is the word an English speaker reaches for; the styles are
        # actually named in Japanese, so translate the query for them.
        aliases = {"whisper": ("ささやき", "ヒソヒソ"),
                   "sasayaki": ("ささやき",),
                   "hisohiso": ("ヒソヒソ",)}
        wanted = aliases.get(needle)

        self.filtered = []
        for sid, speaker, style in self.all_voices:
            label = "%s (%s)" % (speaker, style)
            if not needle:
                ok = True
            elif wanted:
                ok = any(w in style for w in wanted)
            else:
                ok = needle in label.lower() or needle == str(sid)
            if ok:
                self.filtered.append((sid, label))

        self.available.delete(0, "end")
        for sid, label in self.filtered:
            self.available.insert("end", "  %-4d %s" % (sid, label))

    def refresh_selected(self):
        self.selected.delete(0, "end")
        for sid in state["speakers"]:
            self.selected.insert("end", "  %-4d %s" % (sid, self.label_for(sid)))
        self.update_urls()

    def add_voice(self):
        pick = self.available.curselection()
        if not pick:
            return
        sid = self.filtered[pick[0]][0]
        if sid in state["speakers"]:
            return
        state["speakers"].append(sid)
        self.refresh_selected()
        save_config()

    def remove_voice(self):
        pick = self.selected.curselection()
        if not pick or len(state["speakers"]) <= 1:
            return
        del state["speakers"][pick[0]]
        self.refresh_selected()
        save_config()

    def move(self, delta):
        pick = self.selected.curselection()
        if not pick:
            return
        i = pick[0]
        j = i + delta
        if not 0 <= j < len(state["speakers"]):
            return
        speakers = state["speakers"]
        speakers[i], speakers[j] = speakers[j], speakers[i]
        self.refresh_selected()
        self.selected.selection_set(j)
        save_config()

    def preview(self):
        sid = None
        pick = self.selected.curselection()
        if pick:
            sid = state["speakers"][pick[0]]
        else:
            pick = self.available.curselection()
            if pick:
                sid = self.filtered[pick[0]][0]
        if sid is None:
            messagebox.showinfo("Preview", "Pick a voice from either list first.")
            return

        self.read_tuning()

        def work():
            try:
                audio = synthesize(
                    "こんばんは、ゆっくり "
                    "やすんでね", sid)
                ok = play_wav(audio)
            except Exception as exc:
                self.root.after(0, lambda: messagebox.showerror(
                    "Preview failed",
                    "Could not reach the VOICEVOX engine.\n\n%s" % exc))
                return
            if not ok:
                self.root.after(0, lambda: messagebox.showinfo(
                    "No audio player",
                    "The voice was generated but no audio player was found.\n"
                    "It still works in Yomitan."))

        threading.Thread(target=work, daemon=True).start()

    # -- run/stop ---------------------------------------------------------

    def read_tuning(self):
        try:
            state["speed"] = float(self.speed_var.get())
            state["intonation"] = float(self.intonation_var.get())
        except ValueError:
            pass

    def toggle_bridge(self):
        if bridge_running():
            stop_bridge()
            self.start_btn.configure(text="Start")
            state["was_running"] = False
            save_config()
            self.update_urls()
            self.refresh_status_colors()
            return

        try:
            port = int(self.port_var.get())
        except ValueError:
            messagebox.showerror("Bad port", "The port has to be a number, e.g. 8772.")
            return

        if port in BLOCKED_PORTS:
            messagebox.showerror(
                "Port not usable",
                "Port %d is %s.\n\nYomitan would never be able to reach it. "
                "Try 8772 instead." % (port, BLOCKED_PORTS[port]))
            return
        if port in BUSY_PORTS:
            if not messagebox.askyesno(
                "Port probably in use",
                "Port %d is normally used by %s.\n\nStart anyway?"
                    % (port, BUSY_PORTS[port])):
                return

        state["port"] = port
        self.read_tuning()
        try:
            start_bridge()
        except OSError as exc:
            messagebox.showerror(
                "Could not start",
                "Port %d is already being used by another program.\n\n%s" % (port, exc))
            return

        self.start_btn.configure(text="Stop")
        state["was_running"] = True
        save_config()
        self.update_urls()
        self.refresh_status_colors()

    def update_urls(self):
        port = state["port"]
        try:
            port = int(self.port_var.get())
        except (ValueError, AttributeError):
            pass
        self.yomitan_var.set("http://localhost:%d/?term={term}&reading={reading}" % port)
        self.manatan_var.set(
            "http://localtest.me:%d/audio.wav?term={term}&reading={reading}" % port)

    def poll_status(self):
        def work():
            alive = engine_alive()
            self.root.after(0, lambda: self.show_status(alive))

        threading.Thread(target=work, daemon=True).start()
        self.root.after(5000, self.poll_status)

    def show_status(self, alive):
        self._engine_alive = alive
        self.refresh_status_colors()
        if not self.all_voices and alive:
            self.load_voices_async()

    def refresh_status_colors(self):
        c = self.colors
        alive = getattr(self, "_engine_alive", None)
        if alive is None:
            self.engine_label.configure(text="checking…", foreground=c["muted"])
        elif alive:
            self.engine_label.configure(text="●  connected", foreground=c["ok"])
        else:
            self.engine_label.configure(
                text="○  not running — open the VOICEVOX app first",
                foreground=c["bad"])
        if bridge_running():
            self.bridge_label.configure(
                text="●  running on port %d" % state["port"], foreground=c["ok"])
        else:
            self.bridge_label.configure(text="○  stopped", foreground=c["muted"])

    def on_close(self):
        self.read_tuning()
        save_config()
        stop_bridge()
        self.root.destroy()


# ---------------------------------------------------------------------- config

def load_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            saved = json.load(fh)
        for key in DEFAULTS:
            if key in saved:
                state[key] = saved[key]
        if not state["speakers"]:
            state["speakers"] = list(DEFAULTS["speakers"])
        if state["theme"] not in PALETTES:
            state["theme"] = "light"
    except Exception:
        pass


def save_config():
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
    except Exception:
        pass


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
