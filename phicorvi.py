#!/usr/bin/env python3
"""
PhiCorvi -- a small control panel for a local Japanese voice.

Everything the bridge does, with buttons instead of a terminal: start and stop it,
pick which voices it offers, preview them, and copy the link to paste into Yomitan.

Needs only Python 3 and a running VOICEVOX engine. No libraries to install.
Run it with:  python3 phicorvi.py
"""

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from tkinter import filedialog, messagebox, ttk

# Packaged as a one-file .exe, __file__ points into a temporary extraction folder
# that is deleted on exit -- settings saved there would vanish every run. Sit next
# to the executable the user actually double-clicked instead.
if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "phicorvi_config.json")

VERSION = "1.3.0"
REPO = "XnoahR/PhiCorvi"
RELEASES = "https://github.com/%s/releases/latest" % REPO

DEFAULTS = {
    "engine": "http://127.0.0.1:50021",
    "port": 8772,
    "speakers": [19, 96],
    "speed": 0.95,
    "intonation": 0.9,
    "theme": "dark",
    "was_running": True,
    "check_updates": True,
    "watch_clipboard": False,
    "clipboard_max_chars": 200,
}

# Only speak things that actually look Japanese. Without this the watcher reads
# out every URL, file path and snippet of code you copy.
JAPANESE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")

# Ports Chromium refuses to open (ERR_UNSAFE_PORT), plus ones commonly taken by
# other Japanese-mining tools. Warn rather than let people debug silent audio.
BLOCKED_PORTS = {
    5060: "reserved for internet calling",
    5061: "reserved for internet calling",
}
BUSY_PORTS = {5050: "local-audio-yomichan", 8765: "AnkiConnect", 8770: "Forvo server"}

PREVIEW_TEXT = "こんばんは、ゆっくり やすんでね"

# Groups built from the style name are exact -- VOICEVOX publishes those.
STYLE_GROUPS = {
    "ASMR": ("ささやき", "ヒソヒソ", "囁き", "内緒話"),
    "Sweet": ("あまあま", "ぶりっ子"),
    "Tsundere": ("ツンツン", "ツンギレ"),
    "Sexy": ("セクシー", "クイーン"),
    "Calm": ("おちつき", "のんびり", "しっとり", "読み聞かせ", "低血圧"),
    "Energetic": ("元気", "熱血", "わーい", "うきうき", "たのしい", "喜び", "楽々"),
}

# VOICEVOX publishes no gender field, so this is hand-maintained and may be
# wrong or incomplete. Characters left out simply don't appear under Female or
# Male -- they are still findable by name and in every style group. Correct it
# freely; nothing else depends on it.
FEMALE = {
    "四国めたん", "春日部つむぎ", "波音リツ", "雨晴はう", "冥鳴ひまり", "九州そら",
    "もち子さん", "WhiteCUL", "後鬼", "No.7", "櫻歌ミコ", "小夜/SAYO",
    "ナースロボ＿タイプＴ", "春歌ナナ", "猫使アル", "猫使ビィ", "中国うさぎ",
    "あいえるたん", "満別花丸", "琴詠ニア", "Voidoll", "ぞん子",
}
MALE = {
    "玄野武宏", "白上虎太郎", "青山龍星", "剣崎雌雄", "ちび式じい",
    "†聖騎士 紅桜†", "雀松朱司", "麒ヶ島宗麟",
}
TOMBOY = {"波音リツ"}

FILTERS = ["All", "ASMR", "Female", "Male", "Tomboy", "Sweet", "Tsundere", "Sexy",
           "Calm", "Energetic"]

PALETTES = {
    "dark": {
        "bg": "#0e1116",
        "surface": "#161a21",
        "raised": "#1d222c",
        "field": "#11151b",
        "ink": "#e7ebf2",
        "muted": "#98a3b3",
        "faint": "#7d8899",
        "border": "#262d39",
        "accent": "#38bdf8",
        "accent_ink": "#04222f",
        "accent_hover": "#61ccfa",
        "ok": "#34d399",
        "bad": "#f87171",
        "warn": "#fbbf24",
    },
    "light": {
        "bg": "#eef4f9",
        "surface": "#ffffff",
        "raised": "#f5f9fc",
        "field": "#ffffff",
        "ink": "#0d1a25",
        "muted": "#44586a",
        "faint": "#53687b",
        "border": "#d2e2ef",
        "accent": "#0277b5",
        "accent_ink": "#ffffff",
        "accent_hover": "#01608f",
        "ok": "#046c47",
        "bad": "#b3261e",
        "warn": "#8a5a08",
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


def latest_release():
    """Which release is newest, without touching GitHub's API.

    /releases/latest is a redirect to /releases/tag/<tag>, so a HEAD request
    lands on the answer with no body to download. The API is the obvious route
    and the wrong one: it allows 60 unauthenticated calls an hour counted per
    IP address, and behind a shared one -- a phone network, a campus, a CDN --
    that budget is routinely spent by strangers before the app ever asks. The
    redirect carries no such limit.
    """
    try:
        req = urllib.request.Request(RELEASES, method="HEAD",
                                     headers={"User-Agent": "PhiCorvi/%s" % VERSION})
        with urllib.request.urlopen(req, timeout=10) as resp:
            final = resp.geturl()
    except Exception:
        return None
    found = re.search(r"/tag/v?([0-9]+(?:\.[0-9]+)*)", final or "")
    return found.group(1) if found else None


def newer(candidate, current):
    """Compare dotted versions numerically. "1.10.0" beats "1.9.0", which string
    comparison gets backwards."""
    try:
        a = [int(x) for x in candidate.split(".")]
        b = [int(x) for x in current.split(".")]
    except (AttributeError, ValueError):
        return False
    return a > b


def to_mp3(wav):
    """Anki syncs its media folder, so a quarter-megabyte wav per sentence adds
    up fast across thousands of cards. mp3 is about a tenth of that. Without
    ffmpeg we hand the wav back unchanged rather than fail.

    Both sides go through real files, not pipes. Writing mp3 to a pipe leaves
    out the Xing header, because ffmpeg cannot seek back to fill it in -- the
    audio still plays, but every player reads the wrong duration from it, and
    some cut the sentence off partway.
    """
    exe = shutil.which("ffmpeg")
    if not exe:
        return wav, "wav"
    tmp = tempfile.mkdtemp(prefix="phicorvi_")
    src, dst = os.path.join(tmp, "in.wav"), os.path.join(tmp, "out.mp3")
    try:
        with open(src, "wb") as fh:
            fh.write(wav)
        proc = subprocess.run(
            [exe, "-hide_banner", "-loglevel", "error", "-y", "-i", src,
             "-codec:a", "libmp3lame", "-qscale:a", "6", "-ac", "1", dst],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        if proc.returncode == 0 and os.path.getsize(dst) > 0:
            with open(dst, "rb") as fh:
                return fh.read(), "mp3"
    except Exception:
        pass
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return wav, "wav"


def play_wav(data):
    path = os.path.join(tempfile.gettempdir(), "phicorvi_preview.wav")
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
    def _send(self, body, ctype, status=200, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        # Speak the reading, not the kanji -- TTS mispronounces rare words otherwise.
        text = (params.get("text") or params.get("reading")
                or params.get("term") or [""])[0].strip()
        speakers = list(state["speakers"]) or [DEFAULTS["speakers"][0]]

        if not text:
            self._send(b'{"type":"audioSourceList","audioSources":[]}', "application/json")
            return
        try:
            if parsed.path.rstrip("/") == "/tts":
                # Whole sentences, for the Anki add-on. Separate from /audio.wav
                # because that one exists to satisfy Yomitan's JSON source shape.
                asked = (params.get("speaker") or [""])[0]
                sid = int(asked) if asked.isdigit() else speakers[0]
                audio = synthesize(text, sid)
                if (params.get("format") or ["mp3"])[0] == "mp3":
                    audio, kind = to_mp3(audio)
                else:
                    kind = "wav"
                # Say which voice actually spoke. A caller that leaves the choice
                # to PhiCorvi still has to name the file it gets back, and two
                # voices reading the same sentence must not collide.
                self._send(audio, "audio/mpeg" if kind == "mp3" else "audio/wav",
                           extra={"X-Speaker": str(sid)})
            elif parsed.path.rstrip("/") in ("", "/list"):
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


# ------------------------------------------------------------------- scrolling

class ScrollList(ttk.Frame):
    """A vertically scrolling column of rows. Listbox can't hold buttons, and a
    per-row play button is the only way to make 'preview which voice?' obvious."""

    def __init__(self, parent, height=170):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0, height=height)
        self.sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.body = ttk.Frame(self.canvas, style="Card.TFrame")
        self.window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")

        self.canvas.configure(yscrollcommand=self.sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.sb.pack(side="right", fill="y")

        self.body.bind("<Configure>", self._on_body)
        self.canvas.bind("<Configure>", self._on_canvas)
        # Tagged so the app can find which scroller the pointer is over. Binding
        # the wheel per-widget here would fight the page's own scrolling.
        self.canvas._scroller = self
        self.body._scroller = self

    def _on_body(self, _):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._sync_scrollbar()

    def _on_canvas(self, event):
        self.canvas.itemconfigure(self.window, width=event.width)
        # Shrinking the window changes what fits without changing the content,
        # so the scrollbar has to be re-checked here as well as on <Configure>
        # of the body -- otherwise it never appears when you resize down.
        self._sync_scrollbar()

    def _sync_scrollbar(self):
        # Only show the scrollbar when there is something to scroll to -- a dead
        # scrollbar next to two rows reads as "something is cut off".
        needed = self.can_scroll()
        if needed and not self.sb.winfo_ismapped():
            self.sb.pack(side="right", fill="y")
        elif not needed and self.sb.winfo_ismapped():
            self.sb.pack_forget()

    def can_scroll(self):
        box = self.canvas.bbox("all")
        return bool(box) and box[3] > self.canvas.winfo_height() + 2

    def scroll(self, event):
        if getattr(event, "num", None) == 4:
            step = -1
        elif getattr(event, "num", None) == 5:
            step = 1
        else:
            step = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(step, "units")

    def clear(self):
        for child in self.body.winfo_children():
            child.destroy()

    def paint(self, bg):
        self.canvas.configure(bg=bg)


# ------------------------------------------------------------------------- gui

class App:
    def __init__(self, root):
        self.root = root
        root.title("PhiCorvi %s" % VERSION)
        # Small enough to fit a short screen; the page scrolls, so nothing is
        # ever unreachable no matter how far it is squashed.
        root.minsize(520, 380)
        tall = min(880, root.winfo_screenheight() - 140)
        root.geometry("700x%d" % max(420, tall))

        self.all_voices = []
        self.engine_ok = None
        self._last_clip = ""
        self._filter_job = None
        self.advanced_open = False
        self.group = "All"

        load_config()
        self.style = ttk.Style()
        self.style.theme_use("clam")

        self.page = ScrollList(root, height=600)
        self.page.pack(fill="both", expand=True)
        self.outer = ttk.Frame(self.page.body, padding=16)
        self.outer.pack(fill="both", expand=True)
        self.outer.columnconfigure(0, weight=1)

        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            root.bind_all(seq, self.on_wheel)

        self._build_header()
        self._build_sentence()
        self._build_chosen()
        self._build_library()
        self._build_connect()
        self._build_advanced()

        self.apply_theme()
        self.set_group("All")
        self.render_chosen()
        self.update_urls()

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.poll_status()
        self.poll_clipboard()
        self.check_update()
        self.load_voices_async()
        if state.get("was_running"):
            self.root.after(400, self.autostart)

    # -- theme ------------------------------------------------------------

    @property
    def c(self):
        return PALETTES.get(state["theme"], PALETTES["dark"])

    def apply_theme(self):
        c, s = self.c, self.style
        self.root.configure(bg=c["bg"])

        s.configure(".", background=c["bg"], foreground=c["ink"],
                    fieldbackground=c["field"], bordercolor=c["border"],
                    lightcolor=c["border"], darkcolor=c["border"],
                    focuscolor=c["accent"], borderwidth=0)
        s.configure("TFrame", background=c["bg"])
        s.configure("TLabel", background=c["bg"], foreground=c["ink"])
        s.configure("TSeparator", background=c["border"])

        s.configure("Card.TFrame", background=c["surface"])
        s.configure("Card.TLabel", background=c["surface"], foreground=c["ink"])
        s.configure("CardMuted.TLabel", background=c["surface"], foreground=c["muted"])
        s.configure("CardFaint.TLabel", background=c["surface"], foreground=c["faint"])
        s.configure("Row.TFrame", background=c["surface"])
        s.configure("Rank.TLabel", background=c["surface"], foreground=c["accent"],
                    font=("TkDefaultFont", 9, "bold"))
        s.configure("Section.TLabel", background=c["bg"], foreground=c["muted"],
                    font=("TkDefaultFont", 9, "bold"))
        s.configure("Quiet.TLabel", background=c["bg"], foreground=c["faint"])

        s.configure("TCombobox", fieldbackground=c["field"], background=c["raised"],
                    foreground=c["ink"], arrowcolor=c["accent"],
                    bordercolor=c["border"], lightcolor=c["border"],
                    darkcolor=c["border"], selectbackground=c["field"],
                    selectforeground=c["ink"], padding=5)
        s.map("TCombobox", fieldbackground=[("readonly", c["field"])],
              foreground=[("readonly", c["ink"])],
              selectbackground=[("readonly", c["field"])],
              selectforeground=[("readonly", c["ink"])])
        # The dropdown is a plain Tk listbox and ignores ttk styling entirely.
        self.root.option_add("*TCombobox*Listbox.background", c["surface"])
        self.root.option_add("*TCombobox*Listbox.foreground", c["ink"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", c["accent"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", c["accent_ink"])
        s.configure("Big.TLabel", background=c["surface"], foreground=c["ink"],
                    font=("TkDefaultFont", 14, "bold"))

        s.configure("TButton", background=c["raised"], foreground=c["ink"],
                    bordercolor=c["border"], relief="flat", padding=(12, 7))
        s.map("TButton", background=[("active", c["border"]), ("pressed", c["border"])],
              foreground=[("disabled", c["faint"])])

        s.configure("Accent.TButton", background=c["accent"], foreground=c["accent_ink"],
                    relief="flat", padding=(14, 8), font=("TkDefaultFont", 10, "bold"))
        s.map("Accent.TButton", background=[("active", c["accent_hover"]),
                                            ("pressed", c["accent_hover"])],
              foreground=[("active", c["accent_ink"])])

        s.configure("Icon.TButton", background=c["surface"], foreground=c["muted"],
                    relief="flat", padding=(6, 3), font=("TkDefaultFont", 10))
        s.map("Icon.TButton", background=[("active", c["raised"])],
              foreground=[("active", c["accent"]), ("disabled", c["border"])])

        s.configure("Play.TButton", background=c["surface"], foreground=c["accent"],
                    relief="flat", padding=(7, 3), font=("TkDefaultFont", 11))
        s.map("Play.TButton", background=[("active", c["raised"])])

        s.configure("Link.TButton", background=c["bg"], foreground=c["muted"],
                    relief="flat", padding=(2, 2))
        s.map("Link.TButton", background=[("active", c["bg"])],
              foreground=[("active", c["accent"])])

        s.configure("Card.TCheckbutton", background=c["surface"], foreground=c["muted"],
                    focuscolor=c["accent"])
        s.map("Card.TCheckbutton",
              background=[("active", c["surface"])],
              foreground=[("active", c["ink"])],
              indicatorcolor=[("selected", c["accent"]), ("!selected", c["field"])])

        # Bigger than a chip on purpose. These two are the things people reach
        # for while reading, and both used to be a checkbox and a text link --
        # targets you have to aim at rather than just hit.
        s.configure("Toggle.TButton", background=c["raised"], foreground=c["ink"],
                    relief="flat", padding=(16, 10),
                    font=("TkDefaultFont", 10))
        s.map("Toggle.TButton", background=[("active", c["border"])],
              foreground=[("active", c["ink"])])
        s.configure("ToggleOn.TButton", background=c["accent"],
                    foreground=c["accent_ink"], relief="flat", padding=(16, 10),
                    font=("TkDefaultFont", 10, "bold"))
        s.map("ToggleOn.TButton", background=[("active", c["accent_hover"])],
              foreground=[("active", c["accent_ink"])])

        s.configure("Chip.TButton", background=c["surface"], foreground=c["muted"],
                    relief="flat", padding=(11, 5), font=("TkDefaultFont", 9))
        s.map("Chip.TButton", background=[("active", c["raised"])],
              foreground=[("active", c["ink"])])
        s.configure("ChipOn.TButton", background=c["accent"], foreground=c["accent_ink"],
                    relief="flat", padding=(11, 5),
                    font=("TkDefaultFont", 9, "bold"))
        s.map("ChipOn.TButton", background=[("active", c["accent_hover"])],
              foreground=[("active", c["accent_ink"])])

        s.configure("TEntry", fieldbackground=c["field"], foreground=c["ink"],
                    bordercolor=c["border"], insertcolor=c["ink"], padding=7)
        s.configure("TSpinbox", fieldbackground=c["field"], foreground=c["ink"],
                    bordercolor=c["border"], arrowcolor=c["accent"],
                    insertcolor=c["ink"], padding=5)
        s.configure("Vertical.TScrollbar", background=c["raised"],
                    troughcolor=c["bg"], bordercolor=c["bg"],
                    arrowcolor=c["muted"], relief="flat")
        s.map("Vertical.TScrollbar", background=[("active", c["border"])])

        for widget in (self.header, self.chosen_card, self.library_card,
                       self.connect_card):
            widget.configure(style="Card.TFrame")
        self.page.paint(c["bg"])
        self.chosen_list.paint(c["surface"])
        self.library_list.paint(c["surface"])

        self.theme_btn.configure(text="☀  Light" if state["theme"] == "dark"
                                 else "☾  Dark")
        self.render_status()
        self.render_chosen()
        self.render_library()

    def on_wheel(self, event):
        widget = self.root.winfo_containing(event.x_root, event.y_root)
        while widget is not None:
            scroller = getattr(widget, "_scroller", None)
            # Skip a list that has nothing to scroll, so the wheel keeps working
            # over a short list instead of dying there.
            if scroller is not None and scroller.can_scroll():
                scroller.scroll(event)
                return "break"
            widget = getattr(widget, "master", None)
        if self.page.can_scroll():
            self.page.scroll(event)
        return "break"

    def toggle_theme(self):
        state["theme"] = "light" if state["theme"] == "dark" else "dark"
        self.apply_theme()
        save_config()

    # -- header -----------------------------------------------------------

    def _build_header(self):
        card = ttk.Frame(self.outer, style="Card.TFrame", padding=16)
        card.grid(row=0, column=0, sticky="ew")
        card.columnconfigure(0, weight=1)
        self.header = card

        left = ttk.Frame(card, style="Card.TFrame")
        left.grid(row=0, column=0, sticky="w")
        self.state_label = ttk.Label(left, text="Starting…", style="Big.TLabel")
        self.state_label.pack(anchor="w")
        self.state_hint = ttk.Label(left, text="", style="CardMuted.TLabel",
                                    wraplength=380, justify="left")
        self.state_hint.pack(anchor="w", pady=(3, 0))

        # The headline says what to do; these two say which half is at fault, so
        # you can still see both pieces at a glance.
        dots = ttk.Frame(left, style="Card.TFrame")
        dots.pack(anchor="w", pady=(9, 0))
        self.engine_dot = ttk.Label(dots, text="● VOICEVOX", style="CardFaint.TLabel")
        self.engine_dot.pack(side="left")
        self.bridge_dot = ttk.Label(dots, text="● PhiCorvi", style="CardFaint.TLabel")
        self.bridge_dot.pack(side="left", padx=(16, 0))


        # Stays empty unless there is genuinely something newer, so it never
        # becomes a strip of chrome people learn to look past.
        self.update_note = ttk.Label(left, text="", style="CardFaint.TLabel",
                                     cursor="hand2", wraplength=380, justify="left")
        self.update_note.pack(anchor="w", pady=(10, 0))
        self.update_note.bind("<Button-1>", lambda _e: webbrowser.open(RELEASES))

        right = ttk.Frame(card, style="Card.TFrame")
        right.grid(row=0, column=1, sticky="e")
        self.power_btn = ttk.Button(right, text="Stop", width=11,
                                    style="Accent.TButton", command=self.toggle_bridge)
        self.power_btn.pack()
        self.theme_btn = ttk.Button(right, text="☾  Dark", width=11,
                                    style="Link.TButton", command=self.toggle_theme)
        self.theme_btn.pack(pady=(8, 0))

    def check_update(self):
        """One request at startup, off the UI thread, and silent about every
        outcome except an update actually being available."""
        if not state.get("check_updates", True):
            return

        def work():
            found = latest_release()
            if not found or not newer(found, VERSION):
                return
            try:
                self.root.after(0, lambda: self.show_update(found))
            except Exception:
                pass  # window closed while we were asking

        threading.Thread(target=work, daemon=True).start()

    def show_update(self, found):
        self.update_note.configure(
            text="Versi %s sudah keluar — kamu pakai %s. Klik di sini untuk unduh."
            % (found, VERSION))

    def on_clip_toggle(self):
        state["watch_clipboard"] = not bool(state.get("watch_clipboard", False))
        save_config()
        self.render_clip()
        if state["watch_clipboard"]:
            # whatever is already on the clipboard should not fire immediately
            try:
                self._last_clip = self.root.clipboard_get()
            except Exception:
                self._last_clip = ""
            self.clip_note.configure(text="Blok kalimat lalu Ctrl+C.")
        else:
            self.clip_note.configure(
                text="Nyalakan, lalu blok kalimat apa pun dan tekan Ctrl+C.")

    def render_status(self):
        c = self.c
        running = bridge_running()
        if self.engine_ok is False:
            title, hint, colour = (
                "VOICEVOX is not open",
                "Open the VOICEVOX app and wait a few seconds. It's the part that "
                "actually makes the sound.",
                c["bad"])
        elif not running:
            title, hint, colour = (
                "Paused",
                "Yomitan won't get audio until you press Start.",
                c["warn"])
        elif self.engine_ok is None:
            title, hint, colour = ("Checking…", "", c["muted"])
        else:
            title, hint, colour = (
                "Ready",
                "Hover a Japanese word in Yomitan and it will speak.",
                c["ok"])
        self.state_label.configure(text=title, foreground=colour)
        self.state_hint.configure(text=hint)
        self.power_btn.configure(text="Stop" if running else "Start")

        if self.engine_ok is None:
            self.engine_dot.configure(text="○ VOICEVOX", foreground=c["faint"])
        elif self.engine_ok:
            self.engine_dot.configure(text="● VOICEVOX  connected", foreground=c["ok"])
        else:
            self.engine_dot.configure(text="○ VOICEVOX  not open", foreground=c["bad"])

        if running:
            self.bridge_dot.configure(text="● PhiCorvi  port %d" % state["port"],
                                      foreground=c["ok"])
        else:
            self.bridge_dot.configure(text="○ PhiCorvi  stopped", foreground=c["faint"])

    # -- chosen voices ----------------------------------------------------

    def _build_sentence(self):
        """The two things people use while reading, at a size you can hit.

        Both were afterthoughts before -- a checkbox in a corner and a text link
        in a section header. They are the reason the app is open at all."""
        hdr = ttk.Frame(self.outer)
        hdr.grid(row=1, column=0, sticky="ew", pady=(18, 6))
        hdr.columnconfigure(0, weight=1)
        ttk.Label(hdr, text="KALIMAT", style="Section.TLabel").grid(
            row=0, column=0, sticky="w")

        card = ttk.Frame(self.outer, style="Card.TFrame", padding=(14, 12))
        card.grid(row=2, column=0, sticky="ew")
        card.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=1)

        self.clip_btn = ttk.Button(card, command=self.on_clip_toggle)
        self.clip_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(card, text="Tulis atau tempel teks\u2026", style="Toggle.TButton",
                   command=self.open_speak_window).grid(row=0, column=1, sticky="ew",
                                                        padx=(6, 0))

        self.clip_note = ttk.Label(card, text="", style="CardMuted.TLabel",
                                   wraplength=420, justify="left")
        self.clip_note.grid(row=1, column=0, columnspan=2, sticky="w", pady=(10, 0))
        self.render_clip()

    def render_clip(self):
        on = bool(state.get("watch_clipboard", False))
        self.clip_btn.configure(
            text=("\u25cf  Membaca yang saya salin" if on
                  else "\u25cb  Bacakan yang saya salin"),
            style="ToggleOn.TButton" if on else "Toggle.TButton")
        if on and not self.clip_note.cget("text"):
            self.clip_note.configure(text="Blok kalimat lalu Ctrl+C.")
        elif not on:
            self.clip_note.configure(
                text="Nyalakan, lalu blok kalimat apa pun dan tekan Ctrl+C.")

    def _build_chosen(self):
        hdr = ttk.Frame(self.outer)
        hdr.grid(row=3, column=0, sticky="ew", pady=(18, 6))
        hdr.columnconfigure(0, weight=1)
        ttk.Label(hdr, text="VOICES YOMITAN WILL USE",
                  style="Section.TLabel").grid(row=0, column=0, sticky="w")
        card = ttk.Frame(self.outer, style="Card.TFrame", padding=(4, 8))
        card.grid(row=4, column=0, sticky="ew")
        self.chosen_card = card
        self.chosen_list = ScrollList(card, height=80)
        self.chosen_list.pack(fill="x", expand=True)
        # Outside the scrolling area: inside it, this note counted towards the
        # content height and produced a scrollbar for two voices.
        self.chosen_note = ttk.Label(
            card, text="Top voice is used first. The others are backups.",
            style="CardFaint.TLabel", padding=(14, 6))
        self.chosen_note.pack(anchor="w")

    def render_chosen(self):
        c = self.c
        # Grow with the number of voices instead of reserving a fixed block, so
        # two voices don't leave a hole and eight don't squeeze the library.
        rows = max(2, min(len(state["speakers"]), 4))
        self.chosen_list.canvas.configure(height=rows * 42)
        self.chosen_list.clear()
        for rank, sid in enumerate(state["speakers"], 1):
            row = ttk.Frame(self.chosen_list.body, style="Row.TFrame", padding=(10, 5))
            row.pack(fill="x")
            row.columnconfigure(2, weight=1)

            ttk.Label(row, text="%d" % rank, style="Rank.TLabel", width=2).grid(
                row=0, column=0)
            ttk.Button(row, text="▶", style="Play.TButton", width=3,
                       command=lambda s=sid: self.preview(s)).grid(row=0, column=1,
                                                                   padx=(4, 8))
            ttk.Label(row, text=_names.get(sid, "speaker %d" % sid),
                      style="Card.TLabel").grid(row=0, column=2, sticky="w")

            first, last = rank == 1, rank == len(state["speakers"])
            up = ttk.Button(row, text="↑", style="Icon.TButton", width=2,
                            command=lambda i=rank - 1: self.move(i, -1))
            up.grid(row=0, column=3)
            up.state(["disabled"] if first else ["!disabled"])
            down = ttk.Button(row, text="↓", style="Icon.TButton", width=2,
                              command=lambda i=rank - 1: self.move(i, 1))
            down.grid(row=0, column=4)
            down.state(["disabled"] if last else ["!disabled"])
            rm = ttk.Button(row, text="✕", style="Icon.TButton", width=2,
                            command=lambda s=sid: self.remove_voice(s))
            rm.grid(row=0, column=5, padx=(4, 0))
            rm.state(["disabled"] if len(state["speakers"]) <= 1 else ["!disabled"])


    # -- library ----------------------------------------------------------

    def _build_library(self):
        bar = ttk.Frame(self.outer)
        bar.grid(row=5, column=0, sticky="ew", pady=(18, 0))
        bar.columnconfigure(0, weight=1)
        header = ttk.Frame(bar)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        ttk.Label(header, text="ADD A VOICE", style="Section.TLabel").grid(
            row=0, column=0, sticky="w")
        ttk.Label(header, text="type a name, or \"whisper\" for the soft ones",
                  style="Section.TLabel").grid(row=0, column=1, sticky="e")
        self.search_var = tk.StringVar()
        entry = ttk.Entry(bar, textvariable=self.search_var)
        entry.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self.search_entry = entry
        self.search_var.trace_add("write", lambda *_: self.debounce_filter())

        chips = ttk.Frame(bar)
        chips.grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.chips = {}
        for i, name in enumerate(FILTERS):
            btn = ttk.Button(chips, text=name, style="Chip.TButton",
                             command=lambda n=name: self.set_group(n))
            btn.grid(row=i // 5, column=i % 5, padx=(0, 6), pady=2, sticky="w")
            self.chips[name] = btn

        card = ttk.Frame(self.outer, style="Card.TFrame", padding=(4, 8))
        card.grid(row=6, column=0, sticky="ew", pady=(8, 0))
        self.library_card = card
        self.library_list = ScrollList(card, height=190)
        self.library_list.pack(fill="both", expand=True)

    def set_group(self, name):
        self.group = name
        for label, btn in self.chips.items():
            btn.configure(style="ChipOn.TButton" if label == name else "Chip.TButton")
        self.render_library()

    def debounce_filter(self):
        if self._filter_job:
            self.root.after_cancel(self._filter_job)
        self._filter_job = self.root.after(160, self.render_library)

    def in_group(self, speaker, style, group):
        if group == "All":
            return True
        if group == "Female":
            return speaker in FEMALE
        if group == "Male":
            return speaker in MALE
        if group == "Tomboy":
            return speaker in TOMBOY or "ボーイ" in style
        return any(word in style for word in STYLE_GROUPS.get(group, ()))

    def matches(self, sid, speaker, style):
        if not self.in_group(speaker, style, self.group):
            return False
        needle = self.search_var.get().lower().strip()
        if not needle:
            return True
        # "whisper" is what an English speaker types; the styles are named in
        # Japanese, so translate it rather than return nothing.
        if needle in ("whisper", "soft", "asmr", "bisik"):
            return any(w in style for w in STYLE_GROUPS["ASMR"])
        return needle in ("%s %s" % (speaker, style)).lower() or needle == str(sid)

    def render_library(self):
        self._filter_job = None
        self.library_list.clear()

        if not self.all_voices:
            msg = ("Waiting for VOICEVOX…" if self.engine_ok is not True
                   else "No voices found.")
            ttk.Label(self.library_list.body, text=msg, style="CardFaint.TLabel",
                      padding=14).pack(anchor="w")
            return

        shown = 0
        for sid, speaker, style in self.all_voices:
            if not self.matches(sid, speaker, style):
                continue
            shown += 1
            chosen = sid in state["speakers"]
            row = ttk.Frame(self.library_list.body, style="Row.TFrame", padding=(10, 4))
            row.pack(fill="x")
            row.columnconfigure(1, weight=1)

            ttk.Button(row, text="▶", style="Play.TButton", width=3,
                       command=lambda s=sid: self.preview(s)).grid(row=0, column=0,
                                                                   padx=(0, 8))
            ttk.Label(row, text="%s (%s)" % (speaker, style),
                      style="Card.TLabel" if not chosen else "CardFaint.TLabel").grid(
                row=0, column=1, sticky="w")
            if chosen:
                ttk.Label(row, text="added", style="CardFaint.TLabel").grid(row=0,
                                                                            column=2)
            else:
                ttk.Button(row, text="+  Add", style="Icon.TButton",
                           command=lambda s=sid: self.add_voice(s)).grid(row=0,
                                                                         column=2)
        if not shown:
            ttk.Label(self.library_list.body,
                      text="Nothing matches that. Try a shorter word.",
                      style="CardFaint.TLabel", padding=14).pack(anchor="w")

    # -- speak any text ---------------------------------------------------

    def open_speak_window(self):
        if getattr(self, "_speak", None) is not None and self._speak.winfo_exists():
            self._speak.lift()
            return
        if not self.all_voices:
            messagebox.showinfo("No voices yet",
                                "Open the VOICEVOX app first, then try again.")
            return

        c = self.c
        win = tk.Toplevel(self.root)
        self._speak = win
        win.title("Speak any text")
        win.configure(bg=c["bg"])
        win.geometry("560x380")
        win.minsize(460, 340)

        wrap = ttk.Frame(win, padding=14)
        wrap.pack(fill="both", expand=True)
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(1, weight=1)

        ttk.Label(wrap, text="PASTE JAPANESE TEXT",
                  style="Section.TLabel").grid(row=0, column=0, sticky="w")

        box = tk.Text(wrap, height=7, wrap="word", bd=0, relief="flat",
                      bg=c["field"], fg=c["ink"], insertbackground=c["ink"],
                      highlightthickness=1, highlightbackground=c["border"],
                      highlightcolor=c["accent"], padx=10, pady=8)
        box.grid(row=1, column=0, sticky="nsew", pady=(6, 6))
        box.focus_set()

        info = ttk.Label(wrap, text="", style="Quiet.TLabel")
        info.grid(row=2, column=0, sticky="w")

        bar = ttk.Frame(wrap)
        bar.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        bar.columnconfigure(1, weight=1)

        labels, by_label = [], {}
        for sid, speaker, style in self.all_voices:
            label = "%s (%s)" % (speaker, style)
            labels.append(label)
            by_label[label] = sid
        start = _names.get(state["speakers"][0], labels[0])
        voice = tk.StringVar(value=start if start in by_label else labels[0])

        ttk.Label(bar, text="Voice").grid(row=0, column=0, padx=(0, 8))
        combo = ttk.Combobox(bar, textvariable=voice, values=labels,
                             state="readonly", width=24)
        combo.grid(row=0, column=1, sticky="w")

        play = ttk.Button(bar, text="\u25b6  Play", style="Accent.TButton")
        play.grid(row=0, column=2, padx=(8, 0))
        save = ttk.Button(bar, text="Save\u2026")
        save.grid(row=0, column=3, padx=(6, 0))

        def written():
            return box.get("1.0", "end-1c").strip()

        def refresh(*_):
            n = len(written())
            if not n:
                info.configure(text="")
            else:
                # Measured on a mid-range CPU: about nine characters a second.
                info.configure(text="%d characters  \u00b7  around %d seconds to make"
                                    % (n, max(1, round(n / 9.0))))

        box.bind("<KeyRelease>", refresh)
        box.bind("<<Paste>>", lambda e: box.after(30, refresh))

        def busy(on, label="\u25b6  Play"):
            for btn in (play, save):
                btn.state(["disabled"] if on else ["!disabled"])
            play.configure(text="Making\u2026" if on else label)

        def generate(then):
            body = written()
            if not body:
                messagebox.showinfo("Nothing to say",
                                    "Paste some Japanese text first.", parent=win)
                return
            busy(True)

            def work():
                try:
                    audio = synthesize(body, by_label[voice.get()])
                except Exception:
                    self.root.after(0, lambda: (busy(False), messagebox.showerror(
                        "Could not make audio",
                        "PhiCorvi couldn't reach VOICEVOX.\n\n"
                        "Make sure the VOICEVOX app is open.", parent=win)))
                    return
                self.root.after(0, lambda: (busy(False), then(audio)))

            threading.Thread(target=work, daemon=True).start()

        def do_play():
            generate(lambda audio: play_wav(audio) or None)

        def do_save():
            def store(audio):
                types = [("WAV audio", "*.wav")]
                ext = ".wav"
                if shutil.which("ffmpeg"):
                    types.insert(0, ("MP3 audio", "*.mp3"))
                    ext = ".mp3"
                path = filedialog.asksaveasfilename(
                    parent=win, defaultextension=ext, filetypes=types,
                    initialfile="phicorvi" + ext)
                if not path:
                    return
                try:
                    if path.lower().endswith(".mp3"):
                        proc = subprocess.run(
                            ["ffmpeg", "-y", "-f", "wav", "-i", "pipe:0",
                             "-b:a", "64k", "-ac", "1", path],
                            input=audio, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
                        if proc.returncode != 0:
                            raise OSError("ffmpeg failed")
                    else:
                        with open(path, "wb") as fh:
                            fh.write(audio)
                except Exception as exc:
                    messagebox.showerror("Could not save",
                                         "%s" % exc, parent=win)
                    return
                info.configure(text="Saved to %s" % os.path.basename(path))

            generate(store)

        play.configure(command=do_play)
        save.configure(command=do_save)

        hint = "Long passages take a while \u2014 roughly a second for every nine characters."
        if not shutil.which("ffmpeg"):
            hint += "  Install ffmpeg to save as MP3 instead of large WAV files."
        ttk.Label(wrap, text=hint, style="Quiet.TLabel",
                  wraplength=500, justify="left").grid(row=4, column=0, sticky="w",
                                                       pady=(10, 0))

        win.protocol("WM_DELETE_WINDOW",
                     lambda: (setattr(self, "_speak", None), win.destroy()))

    # -- connect ----------------------------------------------------------

    def _build_connect(self):
        ttk.Label(self.outer, text="CONNECT", style="Section.TLabel").grid(
            row=5, column=0, sticky="w", pady=(18, 6))
        card = ttk.Frame(self.outer, style="Card.TFrame", padding=14)
        card.grid(row=6, column=0, sticky="ew")
        card.columnconfigure(0, weight=1)
        self.connect_card = card

        ttk.Label(card, text="Yomitan → Settings → Audio → add a source of type "
                             "\"Custom URL (JSON)\" → paste → drag it to the top.",
                  style="CardMuted.TLabel", wraplength=430,
                  justify="left").grid(row=0, column=0, sticky="w")

        buttons = ttk.Frame(card, style="Card.TFrame")
        buttons.grid(row=0, column=1, sticky="e", padx=(12, 0))
        self.copy_btn = ttk.Button(buttons, text="Copy link", width=13,
                                   style="Accent.TButton",
                                   command=lambda: self.copy(self.yomitan_url, self.copy_btn,
                                                             "Copy link"))
        self.copy_btn.pack()
        self.copy_manatan_btn = ttk.Button(buttons, text="for Manatan", width=13,
                                           style="Link.TButton",
                                           command=lambda: self.copy(
                                               self.manatan_url, self.copy_manatan_btn,
                                               "for Manatan"))
        self.copy_manatan_btn.pack(pady=(6, 0))

    def copy(self, text, button, label):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        button.configure(text="Copied ✓")
        self.root.after(1400, lambda: button.configure(text=label))

    def update_urls(self):
        port = state["port"]
        self.yomitan_url = "http://localhost:%d/?term={term}&reading={reading}" % port
        self.manatan_url = ("http://localtest.me:%d/audio.wav?term={term}&reading={reading}"
                            % port)

    # -- advanced ---------------------------------------------------------

    def _build_advanced(self):
        self.adv_toggle = ttk.Button(self.outer, text="▸  Advanced settings",
                                     style="Link.TButton", command=self.toggle_advanced)
        self.adv_toggle.grid(row=7, column=0, sticky="w", pady=(12, 0))

        self.adv = ttk.Frame(self.outer, style="Card.TFrame", padding=14)
        self.adv.columnconfigure(6, weight=1)

        ttk.Label(self.adv, text="Port", style="Card.TLabel").grid(row=0, column=0)
        self.port_var = tk.StringVar(value=str(state["port"]))
        ttk.Entry(self.adv, textvariable=self.port_var, width=7).grid(
            row=0, column=1, padx=(8, 20))
        ttk.Label(self.adv, text="Speed", style="Card.TLabel").grid(row=0, column=2)
        self.speed_var = tk.StringVar(value="%.2f" % state["speed"])
        ttk.Spinbox(self.adv, from_=0.5, to=1.5, increment=0.05, width=5,
                    textvariable=self.speed_var).grid(row=0, column=3, padx=(8, 20))
        ttk.Label(self.adv, text="Intonation", style="Card.TLabel").grid(row=0, column=4)
        self.intonation_var = tk.StringVar(value="%.2f" % state["intonation"])
        ttk.Spinbox(self.adv, from_=0.0, to=1.5, increment=0.05, width=5,
                    textvariable=self.intonation_var).grid(row=0, column=5, padx=(8, 0))

        ttk.Label(self.adv, text="Lower intonation sounds flatter and calmer. "
                                 "Changing the port needs a restart of the link above.",
                  style="CardFaint.TLabel", wraplength=520,
                  justify="left").grid(row=1, column=0, columnspan=7, sticky="w",
                                       pady=(10, 0))

    def toggle_advanced(self):
        self.advanced_open = not self.advanced_open
        if self.advanced_open:
            self.adv.grid(row=8, column=0, sticky="ew", pady=(8, 0))
            self.adv_toggle.configure(text="▾  Advanced settings")
        else:
            self.adv.grid_remove()
            self.adv_toggle.configure(text="▸  Advanced settings")

    def read_tuning(self):
        try:
            state["speed"] = float(self.speed_var.get())
            state["intonation"] = float(self.intonation_var.get())
        except ValueError:
            pass

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
        self.render_library()
        self.render_chosen()

    def add_voice(self, sid):
        if sid not in state["speakers"]:
            state["speakers"].append(sid)
            self.render_chosen()
            self.render_library()
            save_config()

    def remove_voice(self, sid):
        if sid in state["speakers"] and len(state["speakers"]) > 1:
            state["speakers"].remove(sid)
            self.render_chosen()
            self.render_library()
            save_config()

    def move(self, index, delta):
        target = index + delta
        speakers = state["speakers"]
        if 0 <= target < len(speakers):
            speakers[index], speakers[target] = speakers[target], speakers[index]
            self.render_chosen()
            save_config()

    def preview(self, sid):
        self.read_tuning()

        def work():
            try:
                audio = synthesize(PREVIEW_TEXT, sid)
            except Exception:
                self.root.after(0, lambda: messagebox.showerror(
                    "Can't play that",
                    "PhiCorvi couldn't reach VOICEVOX.\n\n"
                    "Make sure the VOICEVOX app is open, then try again."))
                return
            if not play_wav(audio):
                self.root.after(0, lambda: messagebox.showinfo(
                    "No audio player found",
                    "The voice was created, but this computer has no player "
                    "PhiCorvi knows how to use.\n\nIt will still work in Yomitan."))

        threading.Thread(target=work, daemon=True).start()

    # -- run/stop ---------------------------------------------------------

    def autostart(self):
        if bridge_running():
            return
        try:
            start_bridge()
        except OSError:
            return
        self.render_status()

    def toggle_bridge(self):
        if bridge_running():
            stop_bridge()
            state["was_running"] = False
            save_config()
            self.render_status()
            return

        try:
            port = int(self.port_var.get())
        except ValueError:
            messagebox.showerror("Check the port",
                                 "The port has to be a number, like 8772.")
            return
        if port in BLOCKED_PORTS:
            messagebox.showerror(
                "That port won't work",
                "Port %d is %s, and browsers refuse to open it.\n\n"
                "Yomitan would never reach PhiCorvi. Try 8772." % (port, BLOCKED_PORTS[port]))
            return
        if port in BUSY_PORTS and not messagebox.askyesno(
                "Port may be taken",
                "Port %d is normally used by %s.\n\nStart anyway?"
                % (port, BUSY_PORTS[port])):
            return

        state["port"] = port
        self.read_tuning()
        try:
            start_bridge()
        except OSError:
            messagebox.showerror(
                "Port already in use",
                "Another program is already using port %d.\n\n"
                "Open Advanced settings and pick a different number, "
                "like 8773." % port)
            return
        state["was_running"] = True
        save_config()
        self.update_urls()
        self.render_status()

    # -- read what you copy -----------------------------------------------

    def poll_clipboard(self):
        """Speak Japanese text as soon as it lands on the clipboard, so reading
        a novel means select + copy instead of select, copy, switch window,
        paste, click."""
        self.root.after(400, self.poll_clipboard)
        if not state.get("watch_clipboard", False):
            return
        try:
            text = self.root.clipboard_get()
        except Exception:
            return                      # empty, or not text at all
        text = (text or "").strip()
        if not text or text == self._last_clip:
            return
        self._last_clip = text

        if not JAPANESE.search(text):
            return
        limit = int(conf_int("clipboard_max_chars", 200))
        if len(text) > limit:
            self.clip_note.configure(
                text="dilewati: %d karakter, batas %d" % (len(text), limit))
            return

        sid = state["speakers"][0] if state["speakers"] else 19
        self.clip_note.configure(text="membacakan: %s" % text[:28])

        def work():
            try:
                play_wav(synthesize(text, sid))
            except Exception:
                self.root.after(0, lambda: self.clip_note.configure(
                    text="gagal - VOICEVOX terbuka?"))

        threading.Thread(target=work, daemon=True).start()

    def poll_status(self):
        def work():
            alive = engine_alive()
            self.root.after(0, lambda: self.on_status(alive))

        threading.Thread(target=work, daemon=True).start()
        self.root.after(5000, self.poll_status)

    def on_status(self, alive):
        was = self.engine_ok
        self.engine_ok = alive
        self.render_status()
        if alive and not self.all_voices:
            self.load_voices_async()
        elif was is not alive and not alive:
            self.render_library()

    def on_close(self):
        self.read_tuning()
        save_config()
        stop_bridge()
        self.root.destroy()


# ---------------------------------------------------------------------- config

def conf_int(key, fallback):
    try:
        return int(state.get(key, fallback))
    except (TypeError, ValueError):
        return fallback


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
            state["theme"] = "dark"
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
