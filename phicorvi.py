#!/usr/bin/env python3
"""
PhiCorvi -- a small control panel for a local Japanese voice.

Everything the bridge does, with buttons instead of a terminal: start and stop it,
pick which voices it offers, preview them, and copy the link to paste into Yomitan.

Needs only Python 3 and a running VOICEVOX engine. No libraries to install.
Run it with:  python3 phicorvi.py
"""

import base64
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import tkinter as tk
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import zipfile
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

VERSION = "1.3.1"
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
    # Voice conversion, off unless you point it somewhere. PhiCorvi never ships
    # or installs this: it is another local service, the same way VOICEVOX is,
    # and an empty address simply means the VOICEVOX voice is the final voice.
    # Which engine reads the sentence. VOICEVOX is the default and always
    # will be: its readings come from a dictionary, so a rare word is spoken
    # correctly rather than guessed at -- which matters more in a vocabulary
    # tool than the voice does. Irodori is a neural engine that clones a voice
    # from one reference clip, so it needs no conversion stage after it.
    "tts_engine": "voicevox",
    "irodori": "http://127.0.0.1:8088",
    "irodori_voice": "",
    # Skrip yang menyalakan server Irodori. PhiCorvi tidak pernah memasangnya
    # sendiri: bobot modelnya saja ribuan kali ukuran exe ini. Yang
    # ditunjuk di sini skrip milikmu sendiri, karena jalur checkpoint, perangkat,
    # dan presisinya berbeda di tiap mesin.
    "irodori_launcher": "",
    # Tempat add-on Anki berada, disebutkan sendiri oleh add-on lewat bridge.
    # Engine dipasang di dalamnya, karena folder itulah satu-satunya yang pasti
    # dimiliki pengguna biasa -- mereka tidak menarik repo ini.
    "anki_addon_dir": "",
    # Scene tone. A model reads the mined sentence and marks it up with the
    # emoji Irodori understands, so the line is read with expression instead of
    # flat. Off by default: it needs a key of your own, it costs a call, and
    # every sentence is read perfectly well without it.
    "emotion_on": False,
    "emotion_url": "https://api.deepseek.com/v1/chat/completions",
    "emotion_key": "",
    "emotion_model": "deepseek-chat",
}

# Irodori reads these emoji as delivery instructions -- they are annotations,
# not characters to pronounce. The full table is in the model card's
# EMOJI_ANNOTATIONS.md; this is the subset that suits reading prose. The rest
# are audio-drama effects (phone filter, echo, chewing, humming) that would
# only produce odd noises in the middle of a novel.
#
# Repeating one strengthens it, and placement matters: attached to the clause
# it belongs to, not piled at the end of the sentence.
EMOJI = {
    "😊": "cheerful, glad",
    "😆": "joyful, laughing",
    "🤭": "chuckle, giggle, suppressed laugh",
    "😏": "teasing, playfully sweet",
    "😌": "relieved, contented",
    "😎": "confident, proud",
    "🫶": "gentle, tender",
    "🫣": "shy, bashful",
    "😰": "panicked, agitated, stuttering",
    "😟": "anxious, worried",
    "🥺": "trembling voice, timid",
    "😲": "surprised, struck with awe",
    "😮": "gasp",
    "😠": "angry, displeased, sulking",
    "😒": "tutting, clicking the tongue",
    "🙄": "exasperated",
    "😭": "sobbing, crying, sorrowful",
    "😖": "pained, agonised",
    "😪": "sleepy, languid",
    "🥱": "yawn",
    "😮‍💨": "breath, sigh",
    "🌬️": "out of breath, heavy breathing",
    "🤧": "coughing, sniffling, clearing the throat",
    "👂": "whisper, close to the ear",
    "⏸️": "pause, silence",
    "🐢": "slowly",
    "⏩": "fast, rapid-fire",
    "💪": "with effort, forcefully",
    "🤔": "questioning, wondering",
    "🙏": "pleading",
    "😱": "scream, shriek",
    "📖": "narration, monologue",
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


# Written next to the config and handed to the interpreter. It exists because
# PyTorch 2.6 flipped `torch.load` to weights_only=True, and the hubert
# checkpoint fairseq loads is not weights-only -- without this the server starts
# happily and then fails on the first sentence. The exception is narrowed to
# that one file: a third-party voice model still goes through the safe loader.







def irodori_on():
    return (str(state.get("tts_engine") or "voicevox") == "irodori"
            and bool(str(state.get("irodori") or "").strip()))


def irodori_voices():
    """Suara yang tersedia: folder karakter dulu, lalu berkas datar milik server.

    Folder karakter dibaca dari disk dan bukan ditanyakan ke server, karena
    server memang tidak tahu keberadaannya -- ia hanya menerima jalurnya saat
    permintaan datang.
    """
    pak = voice_packs()
    if not str(state.get("irodori") or "").strip():
        return pak
    base = state["irodori"].rstrip("/")
    for path in ("/v1/audio/voices", "/v1/voices", "/voices"):
        try:
            raw = urllib.request.urlopen(base + path, timeout=5).read()
            data = json.loads(raw)
            if isinstance(data, dict):
                data = data.get("voices") or data.get("data") or []
            names = [d.get("id") or d.get("name") if isinstance(d, dict) else d
                     for d in data]
            names = [str(n) for n in names if n]
            if names:
                # Folder karakter di depan: itu yang dirawat orang, sedangkan
                # berkas datar sisa percobaan lama.
                datar = [n for n in sorted(names) if n not in pak]
                return pak + datar
        except Exception:
            continue
    return pak


def irodori_alive():
    if not str(state.get("irodori") or "").strip():
        return False
    base = state["irodori"].rstrip("/")
    for path in ("/v1/models", "/health", "/"):
        try:
            urllib.request.urlopen(base + path, timeout=3).read()
            return True
        except Exception:
            continue
    return False


# Yang diterima server sebagai klip acuan. Ia memindai foldernya tiap kali
# permintaan datang, jadi menambah berkas tidak perlu menyalakan ulang apa pun.
VOICE_EXT = (".wav", ".flac", ".mp3", ".m4a", ".ogg", ".opus", ".aac", ".webm")


def voice_model_dir():
    """Perpustakaan suara: satu folder per karakter, isinya rekamannya.

    Server sendiri hanya memindai berkas di tingkat atas folder voices/ dan
    memakai nama berkas sebagai nama suara -- ia tidak turun ke subfolder. Jadi
    susunan bersarang ini milik PhiCorvi, dan jalurnya diserahkan ke server
    lewat `ref_wavs`, yang memang menerima daftar jalur dan menggabungkannya.
    """
    return os.path.join(irodori_home(), "voice_model")


def pack_files(nama):
    """Rekaman di dalam satu folder karakter, urut nama.

    Urutan itu penting: server menggabungkan lalu memotong di batas durasi
    acuan, jadi berkas pertama yang menentukan warna suaranya.
    """
    nama = (nama or "").strip()
    if not nama or os.sep in nama or nama in (".", ".."):
        return []
    d = os.path.join(voice_model_dir(), nama)
    try:
        return [os.path.join(d, n) for n in sorted(os.listdir(d))
                if os.path.splitext(n)[1].lower() in VOICE_EXT]
    except OSError:
        return []


def voice_packs():
    """Nama karakter yang punya setidaknya satu rekaman, urut abjad."""
    keluar = []
    try:
        for n in sorted(os.listdir(voice_model_dir())):
            if pack_files(n):
                keluar.append(n)
    except OSError:
        pass
    return keluar

# Proses server Irodori, kalau PhiCorvi yang menyalakannya.
_iro_proc = None


def irodori_serve_running():
    return _iro_proc is not None and _iro_proc.poll() is None


def irodori_serve_start():
    """Nyalakan server Irodori sebagai anak proses aplikasi ini.

    Mengembalikan None kalau berhasil, atau satu kalimat yang menjelaskan apa
    yang menghentikannya. Skripnya harus berjalan di depan -- yang melepaskan
    diri ke latar tidak bisa dihentikan lagi dari sini.
    """
    global _iro_proc
    if irodori_serve_running():
        return None
    skrip = str(state.get("irodori_launcher") or "").strip()
    if not skrip or not os.path.isfile(skrip):
        return "No launcher given, or that path is not a file."
    if os.name != "nt" and not os.access(skrip, os.X_OK):
        return "The launcher is not executable (chmod +x it)."
    # Ke berkas, bukan ke DEVNULL. Membuangnya berarti tidak ada yang bisa
    # ditampilkan selama pemuatan yang setengah menit itu, dan tidak ada alasan
    # yang bisa disebut kalau ia mati saat menyala.
    catatan = irodori_log_path()
    try:
        os.makedirs(os.path.dirname(catatan), exist_ok=True)
        keluaran = open(catatan, "wb")
    except OSError:
        keluaran = subprocess.DEVNULL
    kwargs = {"stdout": keluaran, "stderr": subprocess.STDOUT,
              "cwd": os.path.dirname(skrip) or None}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        _iro_proc = subprocess.Popen([skrip], **kwargs)
    except OSError as exc:
        return "Could not start it: %s" % exc
    return None


def irodori_log_path():
    return os.path.join(irodori_home(), "server.log")


def irodori_log_tail(n=1):
    """Baris terakhir yang berarti dari log server.

    Baris kosong dan garis palang uvicorn dilewati: yang dicari kalimat yang
    bisa ditunjukkan ke orang, bukan hiasan."""
    try:
        with open(irodori_log_path(), "rb") as fh:
            try:
                fh.seek(-8192, os.SEEK_END)
            except OSError:
                fh.seek(0)
            baris = fh.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return []
    bersih = []
    for b in baris:
        b = b.strip()
        if not b or set(b) <= set("-=_ "):
            continue
        # Awalan logging python tidak memberi tahu apa pun kepada pembaca.
        # Dipotong sepanjang awalannya saja: memecah di ":" ikut memakan
        # "http:" dan mengubah alamat jadi "//127.0.0.1:8088".
        for awalan in ("INFO:", "WARNING:", "ERROR:", "CRITICAL:", "DEBUG:"):
            if b.startswith(awalan):
                b = b[len(awalan):].strip()
                break
        # Nama modul yang menyusul, kalau ada: "irodori_openai_tts.app:pesan".
        b = re.sub(r"^[A-Za-z_][\w.]*:", "", b).strip()
        bersih.append(b)
    return bersih[-n:]


def irodori_serve_stop():
    global _iro_proc
    if not irodori_serve_running():
        _iro_proc = None
        return
    try:
        _iro_proc.terminate()
        _iro_proc.wait(timeout=10)
    except Exception:
        try:
            _iro_proc.kill()
        except Exception:
            pass
    _iro_proc = None



# ---------------------------------------------------------------- installer
# Irodori is a neural engine: its weights alone are a hundred times this app.
# So PhiCorvi does not ship it -- it fetches it on request, into its own folder,
# and nobody has to find a directory or read an install guide.
#
# Everything below is standard library. Adding a downloader must not be what
# finally makes the exe big.

IRODORI_REPO_TAR = ("https://github.com/Aratako/Irodori-TTS-Server"
                    "/archive/refs/heads/main.tar.gz")

# uv brings its own Python, so the machine needs neither Python nor git.
UV_ASSET = {
    "nt": "uv-x86_64-pc-windows-msvc.zip",
    "posix": "uv-x86_64-unknown-linux-gnu.tar.gz",
}
UV_URL = "https://github.com/astral-sh/uv/releases/latest/download/%s"

# The int8 checkpoint, not the full one: measured on a GTX 1650 it needs
# 1534 MiB of VRAM against 3190, downloads 2 GB smaller, and runs 12% slower.
# That trade buys every 2 GB card, which the full checkpoint simply cannot fit.
Q = "https://huggingface.co/Aratako/Irodori-TTS-v4-Small-Quantized/resolve/main"
DAC = "https://huggingface.co/Aratako/Semantic-DACVAE-Japanese-32dim/resolve/main"
IRODORI_WEIGHTS = [
    (Q + "/int8-weight-only/model.safetensors", "int8/model.safetensors", 914316834),
    (DAC + "/weights.pth", "codec/weights.pth", 429620065),
    (Q + "/tokenizer/tokenizer.json", "tokenizer/tokenizer.json", 6718495),
    (Q + "/tokenizer/tokenizer_config.json", "tokenizer/tokenizer_config.json", 668),
]

_install_thread = None
_install_stop = False


ANKI_DATA = (
    # Windows, macOS, Linux, lalu Flatpak. Anki menaruh addons21 langsung di
    # bawah folder ini, bukan di dalam profil.
    os.path.join(os.environ.get("APPDATA", ""), "Anki2"),
    os.path.expanduser("~/Library/Application Support/Anki2"),
    os.path.join(os.environ.get("XDG_DATA_HOME", ""), "Anki2"),
    os.path.expanduser("~/.local/share/Anki2"),
    os.path.expanduser("~/.var/app/net.ankiweb.Anki/data/Anki2"),
)


def find_anki_addon():
    """Folder add-on PhiCorvi di dalam Anki, kalau bisa ditemukan.

    Jalur yang disebutkan add-on sendiri selalu menang: ia tahu persis di mana
    ia berada, sedangkan menebak berarti empat tata letak platform dan nama
    folder yang bisa berupa nomor AnkiWeb. Pemindaian hanya cadangan untuk
    keadaan Anki belum pernah dibuka sejak add-on ini dipasang.
    """
    disebut = str(state.get("anki_addon_dir") or "").strip()
    if disebut and os.path.isdir(disebut):
        return disebut
    for dasar in ANKI_DATA:
        if not dasar:
            continue
        addons = os.path.join(dasar, "addons21")
        if not os.path.isdir(addons):
            continue
        try:
            nama = sorted(os.listdir(addons))
        except OSError:
            continue
        for n in nama:
            folder = os.path.join(addons, n)
            if not os.path.isdir(folder):
                continue
            if n == "phicorvi_sentence":
                return folder
            try:
                with open(os.path.join(folder, "manifest.json"),
                          encoding="utf-8") as fh:
                    if json.load(fh).get("package") == "phicorvi_sentence":
                        return folder
            except Exception:
                continue
    return ""


def irodori_home():
    """Di mana engine dipasang.

    Di dalam add-on Anki kalau ada: itu folder yang pasti dimiliki setiap
    pengguna, sedangkan letak exe ini bisa di mana saja. Ditaruh di user_files
    dan bukan di akar add-on karena Anki menghapus seluruh isi folder add-on
    saat memperbarui -- user_files satu-satunya yang selamat.

    Pemasangan yang sudah terlanjur ada di sebelah exe tetap dipakai, supaya
    menemukan Anki belakangan tidak membuat sepuluh gigabyte jadi yatim.
    """
    sebelah = os.path.join(os.path.dirname(CONFIG_PATH), "irodori")
    if os.path.isdir(os.path.join(sebelah, "server")):
        return sebelah
    addon = find_anki_addon()
    if addon:
        return os.path.join(addon, "user_files", "irodori")
    return sebelah


def irodori_launcher_written():
    nama = "serve.bat" if os.name == "nt" else "serve.sh"
    return os.path.join(irodori_home(), nama)


def has_nvidia():
    try:
        p = subprocess.run(["nvidia-smi", "-L"], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=8)
        return p.returncode == 0
    except Exception:
        return False


def _ruang_bebas(path):
    try:
        return shutil.disk_usage(path).free
    except Exception:
        return None


def _unduh(url, tujuan, lapor, label, perkiraan=0):
    """Unduh yang bisa disambung. Sekali unduhan 3 GB putus di 90%, memulai
    dari nol lagi adalah cara paling cepat kehilangan kepercayaan orang."""
    os.makedirs(os.path.dirname(tujuan), exist_ok=True)
    bagian = tujuan + ".part"
    ada = os.path.getsize(bagian) if os.path.exists(bagian) else 0
    if os.path.exists(tujuan) and (not perkiraan
                                   or os.path.getsize(tujuan) == perkiraan):
        lapor("%s sudah ada" % label, 1.0)
        return None
    req = urllib.request.Request(url, headers={"User-Agent": "PhiCorvi"})
    if ada:
        req.add_header("Range", "bytes=%d-" % ada)
    try:
        r = urllib.request.urlopen(req, timeout=60)
    except Exception as exc:
        if ada:
            # Server yang menolak Range: mulai ulang sekali, jangan menyerah.
            os.remove(bagian)
            return _unduh(url, tujuan, lapor, label, perkiraan)
        return "%s: %s" % (label, exc)
    total = perkiraan or 0
    try:
        panjang = int(r.headers.get("Content-Length") or 0)
        total = total or (panjang + ada)
    except Exception:
        pass
    if r.status == 200:
        ada = 0                      # server mengabaikan Range
    mode = "ab" if ada else "wb"
    sudah = ada
    with open(bagian, mode) as fh:
        while True:
            if _install_stop:
                return "dibatalkan"
            blok = r.read(1 << 20)
            if not blok:
                break
            fh.write(blok)
            sudah += len(blok)
            lapor("%s  %.0f/%.0f MB" % (label, sudah / 2 ** 20,
                                        (total or sudah) / 2 ** 20),
                  (sudah / total) if total else None)
    os.replace(bagian, tujuan)
    return None


def _rentang(lapor, awal, lebar):
    """Pelapor yang memetakan 0..1 sebuah langkah ke sepotong batang utuh."""
    def dalam(teks, pecahan=None):
        lapor(teks, None if pecahan is None else awal + lebar * pecahan)
    return dalam


def irodori_install(lapor):
    """Pasang server Irodori ke dalam folder PhiCorvi.

    Mengembalikan None kalau berhasil, atau satu kalimat yang menjelaskan apa
    yang menghentikannya. Tiap langkah bisa dijalankan ulang: yang sudah ada
    dilewati, yang setengah jadi disambung.
    """
    rumah = irodori_home()
    gpu = has_nvidia()
    perlu = (11 if gpu else 4) * 1024 ** 3
    bebas = _ruang_bebas(os.path.dirname(CONFIG_PATH))
    if bebas is not None and bebas < perlu:
        return ("Needs about %d GB free, and there is %.1f GB."
                % (perlu // 1024 ** 3, bebas / 1024 ** 3))

    # 1. uv -- membawa Python-nya sendiri, jadi mesin ini tidak perlu punya.
    alat = os.path.join(rumah, "tools")
    uv = os.path.join(alat, "uv.exe" if os.name == "nt" else "uv")
    if not os.path.exists(uv):
        aset = UV_ASSET["nt" if os.name == "nt" else "posix"]
        paket = os.path.join(alat, aset)
        salah = _unduh(UV_URL % aset, paket, _rentang(lapor, 0.0, 0.03),
                       "uv")
        if salah:
            return salah
        try:
            if aset.endswith(".zip"):
                with zipfile.ZipFile(paket) as z:
                    z.extractall(alat)
            else:
                with tarfile.open(paket) as t:
                    t.extractall(alat)
        except Exception as exc:
            return "Could not unpack uv: %s" % exc
        for akar, _, berkas in os.walk(alat):
            for b in berkas:
                if b in ("uv", "uv.exe"):
                    ketemu = os.path.join(akar, b)
                    if ketemu != uv:
                        shutil.move(ketemu, uv)
                    break
        if not os.path.exists(uv):
            return "uv was downloaded but not found after unpacking."
        if os.name != "nt":
            os.chmod(uv, 0o755)

    # 2. sumber server
    server = os.path.join(rumah, "server")
    if not os.path.exists(os.path.join(server, "pyproject.toml")):
        tar = os.path.join(rumah, "server.tar.gz")
        salah = _unduh(IRODORI_REPO_TAR, tar, _rentang(lapor, 0.03, 0.02),
                       "server source")
        if salah:
            return salah
        try:
            with tarfile.open(tar) as t:
                t.extractall(rumah)
        except Exception as exc:
            return "Could not unpack the server: %s" % exc
        # Tarball GitHub membungkus semuanya dalam satu folder bernama cabang.
        for nama in os.listdir(rumah):
            penuh = os.path.join(rumah, nama)
            if os.path.isdir(penuh) and nama.startswith("Irodori-TTS-Server"):
                if os.path.exists(server):
                    shutil.rmtree(server)
                shutil.move(penuh, server)
                break
        try:
            os.remove(tar)
        except OSError:
            pass
    if not os.path.exists(os.path.join(server, "pyproject.toml")):
        return "The server source did not unpack as expected."

    # 3. lingkungan Python -- langkah terberat, dan satu-satunya yang tidak
    #    bisa dilaporkan per megabyte karena uv yang memegang unduhannya.
    lapor("Installing Python packages (this is the long part)", None)
    extra = "cu128" if gpu else "cpu"
    env = dict(os.environ)
    # Mode tautan dibiarkan pada bawaan uv: ia mencoba hardlink dan jatuh ke
    # salin sendiri kalau cache dan venv beda filesystem. Memaksa "copy"
    # menggandakan berkas yang sudah ada di cache -- hampir 8 GB percuma pada
    # pemasangan yang cache-nya sedisk.
    env["UV_HTTP_TIMEOUT"] = "600"
    kwargs = {"cwd": server, "env": env,
              "stdout": subprocess.DEVNULL, "stderr": subprocess.PIPE}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        p = subprocess.run([uv, "sync", "--extra", extra], **kwargs)
    except Exception as exc:
        return "uv could not run: %s" % exc
    if p.returncode != 0:
        ekor = (p.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        return "uv sync failed: %s" % (ekor[-1] if ekor else p.returncode)

    # 4. bobot model
    model = os.path.join(rumah, "models")
    for i, (url, rel, besar) in enumerate(IRODORI_WEIGHTS):
        salah = _unduh(url, os.path.join(model, rel),
                       _rentang(lapor, 0.60 + 0.09 * i, 0.09),
                       rel.split("/")[0], besar)
        if salah:
            return salah

    # 5. peluncur
    py = os.path.join(server, ".venv",
                      "Scripts" if os.name == "nt" else "bin",
                      "python.exe" if os.name == "nt" else "python")
    jalur = irodori_launcher_written()
    baris = {
        "MODEL_DEVICE": "cuda" if gpu else "cpu",
        "CODEC_DEVICE": "cuda" if gpu else "cpu",
        "MODEL_PRECISION": "bf16" if gpu else "fp32",
        "CODEC_PRECISION": "fp32",
        "CHECKPOINT": os.path.join(model, "int8", "model.safetensors"),
        # Berkas, bukan folder: pemuatnya membuka jalur ini langsung.
        "CODEC_REPO": os.path.join(model, "codec", "weights.pth"),
        # 16, bukan 32: diukur 1,00x waktu-nyata lawan 1,53x, dan sapuan
        # mutu menunjukkan dataran di bawah 16 -- jadi separuh waktunya
        # dibayar untuk selisih yang tidak terdengar.
        "DEFAULT_NUM_STEPS": "16",
        "DEFAULT_MAX_REF_SECONDS": "8",
        "PRELOAD": "true",
        "MODEL_LOAD_TIMEOUT": "1200",
        # Bawaannya melepas cache tiap sepuluh sintesis. Di kartu 4 GB itu
        # terlambat: VRAM menanjak ke 3,1 GB lalu satu kalimat panjang
        # kehabisan tempat. Melepas tiap kali hampir tak berbiaya.
        "EMPTY_CACHE_INTERVAL": "1",
        "VOICES_DIR": os.path.join(rumah, "voices"),
    }
    port = 8088
    try:
        alamat = str(state.get("irodori") or "")
        port = int(alamat.rsplit(":", 1)[1])
    except Exception:
        pass
    try:
        os.makedirs(baris["VOICES_DIR"], exist_ok=True)
        if os.name == "nt":
            isi = ["@echo off"]
            isi += ['set "IRODORI_%s=%s"' % (k, v) for k, v in baris.items()]
            isi.append('"%s" -m irodori_openai_tts --host 127.0.0.1 --port %d'
                       % (py, port))
        else:
            isi = ["#!/bin/bash", "set -u"]
            isi += ['export IRODORI_%s="%s"' % (k, v) for k, v in baris.items()]
            # exec supaya SIGTERM dari PhiCorvi sampai ke python, bukan ke shell.
            isi.append('exec "%s" -m irodori_openai_tts --host 127.0.0.1 --port %d'
                       % (py, port))
        with open(jalur, "w", encoding="utf-8") as fh:
            fh.write("\n".join(isi) + "\n")
        if os.name != "nt":
            os.chmod(jalur, 0o755)
    except OSError as exc:
        return "Could not write the launcher: %s" % exc

    state["irodori_launcher"] = jalur
    lapor("Ready. Put a reference clip in %s" % baris["VOICES_DIR"], 1.0)
    return None


def irodori_install_running():
    return _install_thread is not None and _install_thread.is_alive()


def irodori_install_start(lapor, selesai):
    global _install_thread, _install_stop
    if irodori_install_running():
        return
    _install_stop = False

    def kerja():
        try:
            salah = irodori_install(lapor)
        except Exception as exc:                 # noqa: BLE001
            salah = "Unexpected: %s" % exc
        selesai(salah)

    _install_thread = threading.Thread(target=kerja, daemon=True)
    _install_thread.start()


def irodori_install_cancel():
    global _install_stop
    _install_stop = True


def emotion_on():
    return (bool(state.get("emotion_on"))
            and bool(str(state.get("emotion_key") or "").strip())
            and irodori_on())


# Sentences repeat -- the same card is previewed, replayed, re-mined -- and the
# tone of a sentence never changes, so one answer is kept for the whole session.
_marked = {}

EMOTE_SYSTEM = ("出力は挿入後の文の一行のみ。思考や説明や引用符を書かないこと。")

EMOTE_PROMPT = (
    "あなたはライトノベルの一文に朗読用の絵文字注釈を入れる編集者です。\n"
    "次の文に、下の絵文字だけを使って1〜3個を挿入してください。\n"
    "規則:\n"
    "1. 元の文字は一切変更・削除・追加しないこと。絵文字を挿入するだけ。\n"
    "2. 絵文字は、それが表す部分の直前か直後に置くこと。文末にまとめない。\n"
    "3. 地の文なら場面の空気に合うものを選ぶ。強めたいときは同じ絵文字を繰り返す。\n"
    "4. 考えを書かず、挿入後の文だけを一行で出力する。\n"
    "使える絵文字:\n%s\n\n文: %s"
)


def find_marked(balas, asli):
    """Kalimat bertanda yang tersembunyi di mana pun dalam balasan.

    Model penalar menumpahkan alur pikirnya ke jawaban dan kadang kehabisan
    token sebelum menyimpulkan -- kandidat yang benar tetap ada, tapi terkubur
    di tengah prosa Inggris. Mencocokkan per baris melewatkannya.

    Jadi balasan dipindai untuk potongan mana pun yang, setelah emoji dicabut,
    sama persis dengan kalimat asli. Yang terakhir dipakai: kalau model
    menimbang beberapa pilihan, yang belakangan itu keputusannya.
    """
    urut = sorted(EMOJI, key=len, reverse=True)
    n, m = len(balas), len(asli)
    ketemu = ""
    mulai = 0
    while mulai < n:
        i, j = mulai, 0
        while j < m and i < n:
            if balas[i] == asli[j]:
                i += 1
                j += 1
                continue
            for e in urut:
                if balas.startswith(e, i):
                    i += len(e)
                    break
            else:
                break
        if j == m:
            # Emoji yang menempel di ekor masih bagian dari kalimat itu.
            lanjut = True
            while lanjut:
                lanjut = False
                for e in urut:
                    if balas.startswith(e, i):
                        i += len(e)
                        lanjut = True
                        break
            potong = balas[mulai:i]
            if potong != asli and strip_emoji(potong) == asli:
                ketemu = potong
        mulai += 1
    return ketemu


def strip_emoji(s):
    """The sentence with every allowed annotation taken back out."""
    # Longest first: 😮‍💨 contains 😮, and removing the short one first would
    # leave the zero-width joiner and the wind behind as stray characters.
    for e in sorted(EMOJI, key=len, reverse=True):
        s = s.replace(e, "")
    return s


def emote_for(text):
    """The sentence marked up with delivery emoji, or the sentence untouched.

    The reply is only accepted when removing the annotations gives back the
    original character for character. That is what keeps a mined line safe: a
    model that paraphrases, "corrects" a rare kanji, or drops a clause fails
    the check and is discarded, so what gets read is always what was mined.

    Every failure path returns the original text. A tone is a nicety; a silent
    audio field in Anki is not, so nothing here may raise at the caller.
    """
    if not emotion_on():
        return text
    asli = (text or "").strip()
    if not asli:
        return text
    if asli in _marked:
        return _marked[asli]
    hasil = asli
    daftar = "\n".join("%s = %s" % (e, k) for e, k in EMOJI.items())
    # Dua percobaan. Penyedia yang sama menjawab berbeda untuk kalimat yang
    # sama walau suhunya nol, jadi sebagian kegagalan hilang begitu saja kalau
    # ditanya ulang; percobaan kedua sedikit dihangatkan supaya tidak menempuh
    # jalan pikiran yang sama persis. Panggilan kedua hanya terjadi saat gagal.
    for percobaan, suhu in ((0, 0), (1, 0.4)):
        try:
            body = json.dumps({
                "model": str(state.get("emotion_model") or "deepseek-chat"),
                "messages": [{"role": "system", "content": EMOTE_SYSTEM},
                             {"role": "user",
                              "content": EMOTE_PROMPT % (daftar, asli)}],
                "temperature": suhu,
                # Longgar dengan sengaja: model penalar menghabiskan jatahnya
                # untuk berpikir, dan yang terpotong di tengah tidak pernah
                # sampai ke jawabannya.
                "max_tokens": 1500,
            }).encode()
            req = urllib.request.Request(
                str(state.get("emotion_url") or "").strip(), data=body,
                method="POST",
                headers={"Content-Type": "application/json",
                         "Authorization": "Bearer %s"
                                          % str(state.get("emotion_key") or "").strip()})
            raw = json.loads(urllib.request.urlopen(req, timeout=60).read())
            said = raw["choices"][0]["message"]["content"] or ""
            ketemu = find_marked(said, asli)
            if ketemu:
                hasil = ketemu
                break
        except Exception:
            pass
    if len(_marked) >= 512:
        _marked.clear()
    _marked[asli] = hasil
    return hasil


def irodori_speak(text, fmt="wav", voice=None):
    """One sentence, one voice, one request. The server names its own formats,
    so mp3 comes straight back and the ffmpeg step is skipped entirely."""
    nama = str(state.get("irodori_voice") if voice is None else voice).strip()
    payload = {"model": "irodori-tts", "input": text, "voice": nama,
               "response_format": fmt}
    berkas = pack_files(nama)
    if berkas:
        # Folder karakter: jalurnya dikirim apa adanya, karena server tidak
        # memindai subfolder dan tidak akan menemukannya lewat nama saja.
        payload["voice"] = "none"
        payload["irodori"] = {"ref_wavs": berkas}
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        state["irodori"].rstrip("/") + "/v1/audio/speech", data=body,
        method="POST", headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=900).read()










def synthesize(text, speaker, jejak=None, nada=False):
    """`jejak`, kalau diberikan, diisi mesin yang benar-benar membaca kalimat
    ini. Lewat dict dan bukan variabel modul karena bridge melayani beberapa
    permintaan sekaligus, dan jawaban yang benar untuk satu permintaan bukan
    jawaban yang benar untuk yang lain."""
    # Everything that can change the sound belongs in the key: the engine, the
    # voice, the tuning, and the conversion model. Leave one out and a setting
    # change quietly serves the old clip.
    # Marked up before the key is built, not after: the annotations change the
    # sound, so leaving them out would serve a flat clip for a sentence now read
    # with expression. The second call costs nothing -- emote_for keeps its own
    # answers. Only Irodori understands the emoji, so VOICEVOX never sees them.
    #
    # `nada` mati secara bawaan, dan itu yang menentukan: satu kata dari Yomitan
    # tidak punya nada adegan untuk dibaca, jadi memanggil model bahasa untuknya
    # membeli sepuluh detik antrean demi sesuatu yang tidak dipakai. Hanya
    # pemanggil yang benar-benar mengirim kalimat yang menyalakannya.
    diucap = emote_for(text) if (nada and irodori_on()) else text
    if jejak is not None:
        jejak["engine"] = "voicevox"
    key = (state.get("tts_engine"), speaker, text, diucap,
           state["speed"], state["intonation"],
           state.get("irodori_voice") if irodori_on() else "")
    if key in _cache:
        if jejak is not None and irodori_on():
            # Yang tersimpan di cache hanya hasil yang tidak jatuh-balik, jadi
            # kalau Irodori mesinnya, klip inilah yang ia hasilkan.
            jejak["engine"] = "irodori"
        return _cache[key]
    jatuh_balik = False
    if irodori_on():
        try:
            audio = irodori_speak(diucap, "wav")
        except Exception:
            # Prinsip yang sama dengan konversi: kalimat dengan suara yang salah
            # mengalahkan kalimat yang tidak pernah datang -- dan di add-on
            # Anki, gagal berarti kolom audionya kosong selamanya.
            if not engine_alive():
                raise
            jatuh_balik = True
        if not jatuh_balik:
            if jejak is not None:
                jejak["engine"] = "irodori"
            if len(_cache) >= 256:
                _cache.clear()
            _cache[key] = audio
            return audio
    q = json.loads(
        _post("/audio_query?speaker=%d&text=%s" % (speaker, urllib.parse.quote(text)))
    )
    q["speedScale"] = state["speed"]
    q["intonationScale"] = state["intonation"]
    audio = _post("/synthesis?speaker=%d" % speaker, json.dumps(q).encode())
    # Hasil jatuh-balik tidak disimpan: kalau tidak, membetulkan server Irodori
    # tidak akan terdengar sampai cache-nya penuh atau aplikasinya dibuka ulang.
    if not jatuh_balik:
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

    def _status(self):
        """What is set up and what is answering, in one request.

        The Anki add-on already talks to this bridge, so it can learn where the
        engine lives and whether it is up without guessing at folder layouts --
        Anki's own data folder differs on four platforms, and the add-on folder
        may be named after its AnkiWeb id.

        The API key is never part of this. Whether one is set is useful to a
        caller; the key itself is nobody else's business, and this port answers
        anything on the machine.
        """
        rumah = irodori_home()
        peluncur = str(state.get("irodori_launcher") or "")
        return {
            "app": "PhiCorvi",
            "version": VERSION,
            "engine": "irodori" if irodori_on() else "voicevox",
            "voicevox": {
                "url": state.get("engine"),
                "alive": engine_alive(),
            },
            "irodori": {
                "url": state.get("irodori"),
                "alive": irodori_alive(),
                "voice": state.get("irodori_voice") or "",
                "home": rumah,
                "installed": os.path.isdir(os.path.join(rumah, "server")),
                "launcher": peluncur,
                "managed": bool(peluncur) and os.path.isfile(peluncur),
                "running": irodori_serve_running(),
                "voices_dir": os.path.join(rumah, "voices"),
            },
            "anki_addon": find_anki_addon(),
            "scene_tone": {
                "on": bool(state.get("emotion_on")),
                "ready": emotion_on(),
                "model": state.get("emotion_model") or "",
                "has_key": bool(str(state.get("emotion_key") or "").strip()),
            },
        }

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        # Sebelum penjaga teks di bawah: /status tidak membawa kalimat, dan
        # penjaga itu menjawab semua permintaan tanpa teks dengan daftar kosong.
        if parsed.path.rstrip("/") == "/hello":
            # Add-on menyebutkan letaknya sendiri. Satu-satunya cara yang tidak
            # menebak: ia tahu persis di mana ia dipasang, apa pun nama
            # foldernya dan di tata letak platform mana pun.
            rumah = (params.get("home") or [""])[0].strip()
            diterima = bool(rumah) and os.path.isdir(rumah)
            if diterima and rumah != state.get("anki_addon_dir"):
                state["anki_addon_dir"] = rumah
                save_config()
            self._send(json.dumps({"ok": diterima,
                                   "engine_home": irodori_home()}).encode(),
                       "application/json")
            return

        if parsed.path.rstrip("/") == "/status":
            self._send(json.dumps(self._status(), ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")
            return

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
                jejak = {}
                # Kalimat utuh dari add-on Anki: di sinilah nada adegan berarti.
                audio = synthesize(text, sid, jejak, nada=True)
                if (params.get("format") or ["mp3"])[0] == "mp3":
                    audio, kind = to_mp3(audio)
                else:
                    kind = "wav"
                # Say which voice actually spoke. A caller that leaves the choice
                # to PhiCorvi still has to name the file it gets back, and two
                # voices reading the same sentence must not collide.
                # Mesinnya ikut disebut: jatuh-balik ke VOICEVOX terdengar
                # seperti kartu yang berhasil, dan tanpa ini tidak ada cara
                # mengetahui kartu mana yang sebenarnya tidak dibaca Irodori.
                self._send(audio, "audio/mpeg" if kind == "mp3" else "audio/wav",
                           extra={"X-Speaker": str(sid),
                                  "X-Engine": jejak.get("engine", "voicevox")})
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
                # Yomitan: satu kata, tanpa nada adegan.
                self._send(synthesize(text, sid), "audio/wav")
        except urllib.error.URLError as exc:
            # Menyebut mesin yang benar-benar gagal. Sebelumnya selalu tertulis
            # "VOICEVOX unreachable" walaupun yang mati Irodori, yang mengirim
            # orang mencari-cari di tempat yang salah.
            who, where = ("Irodori", state.get("irodori")) if irodori_on() \
                else ("VOICEVOX", state.get("engine"))
            self._send(
                ("%s unreachable at %s (%s)" % (who, where, exc)).encode(),
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
        self.group = "All"

        load_config()
        self.style = ttk.Style()
        self.style.theme_use("clam")

        self.page = ScrollList(root, height=600)
        self.page.pack(fill="both", expand=True)
        self.outer = ttk.Frame(self.page.body, padding=(16, 12, 16, 16))
        self.outer.pack(fill="both", expand=True)
        self.outer.columnconfigure(0, weight=1)

        # Tab di puncak jendela. Setelan dulu bersembunyi di balik tombol di
        # dasar halaman, jadi mengubah apa pun berarti menggulung melewati
        # seluruh daftar suara lebih dulu.
        self.tabs = ttk.Notebook(self.outer)
        self.tabs.grid(row=0, column=0, sticky="ew")
        self.home = ttk.Frame(self.tabs, style="Card.TFrame", padding=(2, 10))
        self.home.columnconfigure(0, weight=1)
        self.tabs.add(self.home, text="  Home  ")

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
        # Ditunda sedikit supaya jendelanya muncul dulu: ini menyentuh jaringan.
        if (state.get("tts_engine") == "irodori"
                and str(state.get("irodori") or "").strip()):
            root.after(500, self.find_iro)
        self.render_chosen()
        self.update_urls()

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.poll_status()
        self.poll_clipboard()
        self.check_update()
        self.load_voices_async()
        # The voice server is remembered the same way the link is: whatever was
        # on last time comes back on, so the app is opened once and not twice.
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

        # Tab panel lanjutan. Tanpa ini "clam" memberinya abu-abu
        # bawaannya sendiri, yang di tema gelap jadi kotak terang di
        # tengah kartu.
        s.configure("TNotebook", background=c["surface"], borderwidth=0,
                    tabmargins=(0, 0, 0, 0))
        s.configure("TNotebook.Tab", background=c["bg"],
                    foreground=c["muted"], padding=(14, 7), borderwidth=0)
        s.map("TNotebook.Tab",
              background=[("selected", c["surface"]), ("active", c["raised"])],
              foreground=[("selected", c["accent"]), ("active", c["ink"])])

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
        card = ttk.Frame(self.home, style="Card.TFrame", padding=16)
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
        self.engine_dot.grid(row=0, column=0, sticky="w")
        self.bridge_dot = ttk.Label(dots, text="● PhiCorvi", style="CardFaint.TLabel")
        self.bridge_dot.grid(row=0, column=1, sticky="w", padx=(16, 0))
        # Irodori ikut di sini, bukan hanya di tabnya: yang membaca kalimatmu
        # adalah bagian dari "apakah ini siap dipakai", dan itu pertanyaan yang
        # dijawab halaman depan.
        #
        # Barisnya sendiri: bertiga sebaris menabrak tombol Start pada lebar
        # jendela yang wajar, dan yang ketiga terpotong di tengah kata.
        self.irodori_dot = ttk.Label(dots, text="○ Irodori", style="CardFaint.TLabel")
        self.irodori_dot.grid(row=1, column=0, columnspan=2, sticky="w",
                              pady=(4, 0))


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
        # Siapa yang sebenarnya akan membaca kalimat berikutnya. Sebelumnya
        # bagian ini menganggap VOICEVOX selalu mesinnya, jadi orang yang sudah
        # pindah ke Irodori tetap dimarahi "VOICEVOX is not open" padahal
        # kalimatnya terbaca dengan baik.
        pakai_iro = state.get("tts_engine") == "irodori"
        iro_ok = bool(getattr(self, "iro_hidup", False))
        suara = str(state.get("irodori_voice") or "").strip()
        if pakai_iro and iro_ok:
            pembaca = "Irodori" + (" · %s" % suara if suara else "")
        elif self.engine_ok:
            # Jatuh-balik itu perilaku yang disengaja, jadi disebut apa adanya
            # -- bukan disembunyikan di balik "Ready" yang sama saja bunyinya.
            pembaca = "VOICEVOX" + (" — Irodori is not running" if pakai_iro else "")
        else:
            pembaca = ""

        if not pembaca and self.engine_ok is not None:
            title, hint, colour = (
                ("Nothing can read yet" if pakai_iro else "VOICEVOX is not open"),
                ("Press Start on the Reading tab to run Irodori, or open the "
                 "VOICEVOX app — PhiCorvi falls back to it."
                 if pakai_iro else
                 "Open the VOICEVOX app and wait a few seconds. It's the part "
                 "that actually makes the sound."),
                c["bad"])
        elif not running:
            title, hint, colour = (
                "Paused",
                "Yomitan won't get audio until you press Start.",
                c["warn"])
        elif not pembaca:
            title, hint, colour = ("Checking…", "", c["muted"])
        else:
            title, hint, colour = (
                "Ready",
                "Read by %s. Hover a Japanese word in Yomitan and it will speak."
                % pembaca,
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

        if state.get("tts_engine") != "irodori":
            # Disembunyikan, bukan diredupkan: orang yang memakai VOICEVOX tidak
            # perlu satu baris tambahan tentang mesin yang tidak mereka pakai.
            self.irodori_dot.grid_remove()
        elif getattr(self, "iro_menunggu", False):
            self.irodori_dot.grid()
            self.irodori_dot.configure(text="◐ Irodori  loading", foreground=c["warn"])
        elif getattr(self, "iro_hidup", False):
            self.irodori_dot.grid()
            suara = str(state.get("irodori_voice") or "").strip()
            self.irodori_dot.configure(
                text="● Irodori  %s" % (suara or "ready"), foreground=c["ok"])
        else:
            self.irodori_dot.grid()
            self.irodori_dot.configure(text="○ Irodori  not running",
                                       foreground=c["bad"])

    # -- chosen voices ----------------------------------------------------

    def _build_sentence(self):
        """The two things people use while reading, at a size you can hit.

        Both were afterthoughts before -- a checkbox in a corner and a text link
        in a section header. They are the reason the app is open at all."""
        hdr = ttk.Frame(self.home)
        hdr.grid(row=1, column=0, sticky="ew", pady=(18, 6))
        hdr.columnconfigure(0, weight=1)
        ttk.Label(hdr, text="KALIMAT", style="Section.TLabel").grid(
            row=0, column=0, sticky="w")

        card = ttk.Frame(self.home, style="Card.TFrame", padding=(14, 12))
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
        hdr = ttk.Frame(self.home)
        hdr.grid(row=3, column=0, sticky="ew", pady=(18, 6))
        hdr.columnconfigure(0, weight=1)
        ttk.Label(hdr, text="VOICES YOMITAN WILL USE",
                  style="Section.TLabel").grid(row=0, column=0, sticky="w")
        card = ttk.Frame(self.home, style="Card.TFrame", padding=(4, 8))
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
        bar = ttk.Frame(self.home)
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

        card = ttk.Frame(self.home, style="Card.TFrame", padding=(4, 8))
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
                    audio = synthesize(body, by_label[voice.get()], nada=True)
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
        ttk.Label(self.home, text="CONNECT", style="Section.TLabel").grid(
            row=7, column=0, sticky="w", pady=(18, 6))
        card = ttk.Frame(self.home, style="Card.TFrame", padding=14)
        card.grid(row=8, column=0, sticky="ew")
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
        # Tiga topik yang tidak saling berhubungan: bagaimana kalimat dibaca,
        # suara apa yang membacanya, dan dengan nada apa. Masing-masing satu tab
        # di sebelah Home, jadi tidak ada yang tersembunyi di dasar halaman.
        #
        # Lebar bungkus tiap catatan mengikuti jendela, bukan angka tetap.
        self.notes = []

        # -- Reading ------------------------------------------------------
        baca = self._tab("Reading")

        angka = ttk.Frame(baca, style="Card.TFrame")
        angka.grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(angka, text="Port", style="Card.TLabel").grid(row=0, column=0)
        self.port_var = tk.StringVar(value=str(state["port"]))
        ttk.Entry(angka, textvariable=self.port_var, width=7).grid(
            row=0, column=1, padx=(8, 20))
        ttk.Label(angka, text="Speed", style="Card.TLabel").grid(row=0, column=2)
        self.speed_var = tk.StringVar(value="%.2f" % state["speed"])
        ttk.Spinbox(angka, from_=0.5, to=1.5, increment=0.05, width=5,
                    textvariable=self.speed_var).grid(row=0, column=3, padx=(8, 20))
        ttk.Label(angka, text="Intonation", style="Card.TLabel").grid(row=0, column=4)
        self.intonation_var = tk.StringVar(value="%.2f" % state["intonation"])
        ttk.Spinbox(angka, from_=0.0, to=1.5, increment=0.05, width=5,
                    textvariable=self.intonation_var).grid(row=0, column=5, padx=(8, 0))

        self._note(baca, "Lower intonation sounds flatter and calmer. Changing "
                         "the port needs a restart of the link above.", 1)

        ttk.Separator(baca, orient="horizontal").grid(
            row=2, column=0, columnspan=3, sticky="ew", pady=(14, 12))

        # Mesin pembaca kalimat. VOICEVOX lebih dulu karena bacaannya berasal
        # dari kamus; Irodori mengkloning suara dari satu klip acuan.
        ttk.Label(baca, text="Engine", style="Card.TLabel").grid(
            row=3, column=0, sticky="w")
        self.engine_var = tk.StringVar(
            value="Irodori" if state.get("tts_engine") == "irodori" else "VOICEVOX")
        eng = ttk.Combobox(baca, state="readonly", width=12,
                           values=["VOICEVOX", "Irodori"],
                           textvariable=self.engine_var)
        eng.grid(row=3, column=1, sticky="w", padx=(10, 0))
        eng.bind("<<ComboboxSelected>>", self.on_engine_pick)

        ttk.Label(baca, text="Irodori address", style="CardFaint.TLabel").grid(
            row=4, column=0, sticky="w", pady=(8, 0))
        self.iro_var = tk.StringVar(value=state.get("irodori") or "")
        ttk.Entry(baca, textvariable=self.iro_var).grid(
            row=4, column=1, sticky="ew", padx=(10, 8), pady=(8, 0))
        self.iro_btn = ttk.Button(baca, text="Find", command=self.find_iro)
        self.iro_btn.grid(row=4, column=2, sticky="w", pady=(8, 0))

        ttk.Label(baca, text="Server", style="CardFaint.TLabel").grid(
            row=5, column=0, sticky="w", pady=(8, 0))
        self.iro_launch_var = tk.StringVar(value=state.get("irodori_launcher") or "")
        ttk.Entry(baca, textvariable=self.iro_launch_var).grid(
            row=5, column=1, sticky="ew", padx=(10, 8), pady=(8, 0))
        self.iro_run_btn = ttk.Button(baca, text="Start",
                                      command=self.toggle_iro_server)
        self.iro_run_btn.grid(row=5, column=2, sticky="w", pady=(8, 0))

        self.iro_get_btn = ttk.Button(baca, text="Download engine",
                                      command=self.toggle_iro_install)
        self.iro_get_btn.grid(row=6, column=1, columnspan=2, sticky="w",
                              padx=(10, 0), pady=(8, 0))

        ttk.Label(baca, text="Reference voice", style="CardFaint.TLabel").grid(
            row=7, column=0, sticky="w", pady=(8, 0))
        # Bisa diketik, bukan readonly: a server that will not list its voices
        # leaves you with a name you know and nowhere to put it.
        self.iro_pick = ttk.Combobox(baca, values=[])
        self.iro_pick.grid(row=7, column=1, sticky="ew", padx=(10, 8), pady=(8, 0))
        self.iro_pick.bind("<<ComboboxSelected>>", self.on_iro_pick)
        self.iro_pick.bind("<Return>", self.on_iro_pick)
        # Tanpa <FocusOut>: ia menyimpan apa pun yang sedang tertampil ketika
        # fokus berpindah -- termasuk saat dropdown dibuka -- dan pernah
        # mengganti suara yang dipilih tanpa ada yang memilihnya. Memilih dari
        # daftar atau menekan Enter itu perbuatan yang disengaja; kehilangan
        # fokus bukan.
        self.iro_add_btn = ttk.Button(baca, text="Add…",
                                      command=self.add_iro_voice)
        self.iro_add_btn.grid(row=7, column=2, sticky="w", pady=(8, 0))

        self.iro_note = self._note(baca, self.engine_text(), 8)

        # -- Scene tone ---------------------------------------------------
        # Only Irodori can be told how to read something, so this does nothing
        # while VOICEVOX is the engine -- said in the note rather than by
        # greying the tab out, which hides why it is unavailable.
        self.emo = self._tab("Scene tone")

        judul = ttk.Frame(self.emo, style="Card.TFrame")
        judul.grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(judul, text="Mark sentences with tone",
                  style="Card.TLabel").grid(row=0, column=0, sticky="w")
        self.emo_on_var = tk.BooleanVar(value=bool(state.get("emotion_on")))
        ttk.Checkbutton(judul, text="on", variable=self.emo_on_var,
                        command=self.on_emotion_toggle).grid(
            row=0, column=1, sticky="w", padx=(12, 0))

        self.emo_key_var = tk.StringVar(value=state.get("emotion_key") or "")
        self.emo_model_var = tk.StringVar(value=state.get("emotion_model") or "")
        self.emo_url_var = tk.StringVar(value=state.get("emotion_url") or "")
        for i, (teks, var, sembunyi) in enumerate((
                ("API key", self.emo_key_var, True),
                ("Model", self.emo_model_var, False),
                ("Address", self.emo_url_var, False))):
            ttk.Label(self.emo, text=teks, style="CardFaint.TLabel").grid(
                row=i + 1, column=0, sticky="w", pady=(8, 0))
            ttk.Entry(self.emo, textvariable=var,
                      show="•" if sembunyi else "").grid(
                row=i + 1, column=1, columnspan=2, sticky="ew",
                padx=(10, 0), pady=(8, 0))

        self.emo_note = self._note(self.emo, self.emotion_text(), 4)

        self.tabs.bind("<Configure>", self.reflow_notes)

    def _tab(self, judul):
        f = ttk.Frame(self.tabs, style="Card.TFrame", padding=14)
        # Kolom isian yang melar, bukan kolom label: label tetap selebar katanya
        # dan kotaknya yang mengambil sisa ruang.
        f.columnconfigure(1, weight=1)
        self.tabs.add(f, text="  %s  " % judul)
        return f

    def _note(self, induk, teks, baris):
        lab = ttk.Label(induk, text=teks, style="CardFaint.TLabel", justify="left")
        lab.grid(row=baris, column=0, columnspan=3, sticky="w", pady=(10, 0))
        self.notes.append(lab)
        return lab

    def reflow_notes(self, _event=None):
        """Lebar bungkus catatan mengikuti panel.

        Angka tetap berarti jendela tetap: pada 520 px, lebar minimum jendela
        ini, catatan selebar 520 px menembus tepinya. Nilai lama dibandingkan
        dulu karena mengubah wraplength mengubah ukuran yang diminta, dan itu
        memicu <Configure> lagi.
        """
        lebar = max(240, self.tabs.winfo_width() - 70)
        for lab in getattr(self, "notes", ()):
            if int(lab.cget("wraplength") or 0) != lebar:
                lab.configure(wraplength=lebar)

    def emotion_text(self):
        if not self.emo_on_var.get():
            return ("Off. Sentences are read in one even tone. Turn this on and "
                    "a model marks each mined sentence with the emoji Irodori "
                    "reads as delivery, so a line sounds like the scene it "
                    "came from.")
        if state.get("tts_engine") != "irodori":
            return ("Needs Irodori as the engine above: VOICEVOX would read the "
                    "emoji out loud rather than act on them.")
        if not str(self.emo_key_var.get() or "").strip():
            return ("Needs a key of your own for the address above. Without one "
                    "every sentence is read plainly, which is what happens now.")
        return ("A model inserts up to three of %d emoji into each sentence. The "
                "reply is only used when taking the emoji back out gives your "
                "sentence character for character, so a mined line can never be "
                "reworded. The answer is kept: one call however often you "
                "replay it." % len(EMOJI))

    def on_emotion_toggle(self):
        self.read_tuning()
        _cache.clear()          # kalimat lama dibaca dengan nada yang lain
        _marked.clear()
        self.emo_note.configure(text=self.emotion_text())

    def read_tuning(self):
        try:
            state["speed"] = float(self.speed_var.get())
            state["intonation"] = float(self.intonation_var.get())
        except ValueError:
            pass
        try:
            state["tts_engine"] = ("irodori"
                                   if self.engine_var.get() == "Irodori"
                                   else "voicevox")
            state["irodori"] = self.iro_var.get().strip()
            state["irodori_launcher"] = self.iro_launch_var.get().strip()
        except (ValueError, AttributeError):
            pass
        try:
            state["emotion_on"] = bool(self.emo_on_var.get())
            state["emotion_key"] = self.emo_key_var.get().strip()
            state["emotion_model"] = self.emo_model_var.get().strip()
            state["emotion_url"] = self.emo_url_var.get().strip()
        except (ValueError, AttributeError):
            pass

    # -- voice model ------------------------------------------------------

    # -- reading engine ---------------------------------------------------

    def toggle_iro_install(self):
        """Ambil mesinnya, ke dalam folder aplikasi ini.

        Bobot modelnya seratus kali ukuran aplikasi ini, jadi tidak ikut
        dikirim. Yang penting: tidak ada yang perlu mencari direktori, memasang
        Python, atau membaca panduan -- uv membawa Python-nya sendiri.
        """
        if irodori_install_running():
            irodori_install_cancel()
            self.iro_get_btn.configure(text="Stopping…", state="disabled")
            return
        besar = 11 if has_nvidia() else 4
        if not messagebox.askokcancel(
                "Download Irodori",
                "This downloads about %d GB into\n%s\n\n"
                "It can be stopped and resumed. Continue?"
                % (besar, irodori_home())):
            return
        self.iro_get_btn.configure(text="Stop")

        def lapor(teks, pecahan=None):
            # Dipanggil dari thread pengunduh; Tk hanya boleh disentuh dari
            # thread utamanya.
            self.root.after(0, lambda: self.iro_note.configure(text=teks))

        def selesai(salah):
            self.root.after(0, lambda: self.iro_install_done(salah))

        irodori_install_start(lapor, selesai)

    def iro_install_done(self, salah):
        self.iro_get_btn.configure(text="Download engine", state="normal")
        if salah:
            self.iro_note.configure(text=salah)
            return
        self.iro_launch_var.set(state.get("irodori_launcher") or "")
        self.refresh_iro_server()
        self.iro_note.configure(
            text="Installed. Press Start to run it — the first launch loads the "
                 "model, which takes about half a minute.")

    def toggle_iro_server(self):
        self.read_tuning()
        if irodori_serve_running():
            irodori_serve_stop()
            self.iro_menunggu = False
            self.clear_iro_voices()
            self.iro_note.configure(
                text="Irodori server stopped. Sentences fall back to VOICEVOX "
                     "until you start it again.")
            self.refresh_iro_server()
            return
        salah = irodori_serve_start()
        if salah:
            self.iro_note.configure(text=salah)
            self.refresh_iro_server()
            return
        # Memuat checkpoint makan puluhan detik; bertanya sekarang selalu gagal.
        self.refresh_iro_server()
        self.iro_t0 = time.time()
        self.iro_menunggu = True
        self.detak_iro()
        self.root.after(4000, self.tunggu_iro, 45)

    def detak_iro(self):
        """Detik berjalan plus apa yang sedang dikatakan server.

        Kalimat diam selama tiga puluh detik tidak bisa dibedakan dari aplikasi
        yang menggantung. Angka yang bertambah bisa.
        """
        if not getattr(self, "iro_menunggu", False):
            return
        lewat = int(time.time() - getattr(self, "iro_t0", time.time()))
        ekor = irodori_log_tail(1)
        kabar = ekor[0][:90] if ekor else "starting the process"
        self.iro_note.configure(
            text="Starting Irodori — %ds\n%s" % (lewat, kabar))
        self.root.after(700, self.detak_iro)

    def tunggu_iro(self, sisa):
        self.refresh_iro_server()
        if not irodori_serve_running():
            self.iro_menunggu = False
            ekor = irodori_log_tail(3)
            self.iro_note.configure(
                text="The server stopped while starting up.\n%s"
                     % ("\n".join(ekor) if ekor else "Its log said nothing."))
            self.clear_iro_voices()
            return

        def kerja():
            hidup = irodori_alive()
            self.root.after(0, lambda: self.lanjut_iro(hidup, sisa))

        threading.Thread(target=kerja, daemon=True).start()

    def lanjut_iro(self, hidup, sisa):
        if hidup:
            self.iro_menunggu = False
            self.find_iro()
            return
        if sisa <= 0:
            self.iro_menunggu = False
            ekor = irodori_log_tail(3)
            self.iro_note.configure(
                text="No answer at %s after %d seconds.\n%s"
                     % (state.get("irodori"), int(time.time() - self.iro_t0),
                        "\n".join(ekor) if ekor else "Its log said nothing."))
            return
        self.root.after(3000, self.tunggu_iro, sisa - 1)

    def add_iro_voice(self):
        """Salin satu rekaman ke folder voices, dan pakai namanya.

        Tidak ada konversi: server menerima delapan format apa adanya. Tidak ada
        pemotongan juga -- panjang acuan dibatasi di sisi server, jadi rekaman
        satu menit sama baiknya dengan yang delapan detik dan tidak perlu
        disiapkan lebih dulu.
        """
        self.read_tuning()
        jenis = [("Audio", " ".join("*" + e for e in VOICE_EXT)), ("All files", "*.*")]
        asal = filedialog.askopenfilename(title="Pick a reference recording",
                                          filetypes=jenis)
        if not asal:
            return
        if os.path.splitext(asal)[1].lower() not in VOICE_EXT:
            self.iro_note.configure(
                text="Irodori reads %s. That file is none of them."
                     % ", ".join(e[1:] for e in VOICE_EXT))
            return
        tujuan_dir = os.path.join(irodori_home(), "voices")
        nama = os.path.basename(asal)
        tujuan = os.path.join(tujuan_dir, nama)
        try:
            os.makedirs(tujuan_dir, exist_ok=True)
            if os.path.abspath(asal) != os.path.abspath(tujuan):
                shutil.copy2(asal, tujuan)
        except OSError as exc:
            self.iro_note.configure(text="Could not copy it: %s" % exc)
            return
        # Nama berkas tanpa ekstensi jadi nama suaranya, itu aturan servernya.
        state["irodori_voice"] = os.path.splitext(nama)[0]
        _cache.clear()
        self.iro_pick.set(state["irodori_voice"])
        if irodori_alive():
            self.find_iro()
        else:
            self.iro_note.configure(
                text="Added %s. Press Start to run the engine and hear it."
                     % state["irodori_voice"])

    def clear_iro_voices(self):
        """Daftar suara dikosongkan saat tidak ada yang menjawab.

        Daftar yang tertinggal dari server yang sudah mati membuat tampilan
        berbohong: terlihat siap padahal tidak ada apa pun di belakangnya.
        Nama yang dipilih tetap disimpan -- itu setelan, bukan laporan.
        """
        self.iro_pick.configure(values=[])
        self.iro_hidup = False
        self.refresh_iro_server()

    def refresh_iro_server(self):
        """Tombol melaporkan keadaan server, bukan siapa yang menyalakannya.

        Sebelumnya ia hanya melihat apakah PhiCorvi yang memiliki prosesnya, jadi
        server yang dinyalakan dari terminal membuat tombolnya berkata "Start"
        sementara daftar suaranya penuh -- dua pernyataan yang benar sendiri-
        sendiri dan berbohong kalau dibaca bersama.
        """
        if irodori_serve_running():
            self.iro_run_btn.configure(text="Stop", state="normal")
        elif getattr(self, "iro_hidup", False):
            # Hidup, tapi bukan anak proses ini: tidak ada yang bisa dihentikan
            # dari sini, dan menawarkan "Start" cuma akan gagal merebut port.
            self.iro_run_btn.configure(text="Running", state="disabled")
        else:
            self.iro_run_btn.configure(text="Start", state="normal")

    def engine_text(self):
        if state.get("tts_engine") == "irodori":
            nama = str(state.get("irodori_voice") or "").strip()
            luar = getattr(self, "iro_hidup", False) and not irodori_serve_running()
            if nama:
                return ("Sentences are read by Irodori in the voice of %s.%s"
                        % (nama,
                           " The engine is already running — something other "
                           "than PhiCorvi started it, so PhiCorvi cannot stop "
                           "it." if luar else
                           " It reads the sentence and copies that voice in one "
                           "step."))
            return ("Irodori reads the sentence and copies a voice from one "
                    "recording. Press Start to run it, Add… to bring a "
                    "recording in, or type a name and press Enter.")
        return ("VOICEVOX reads from a dictionary, so rare words are spoken "
                "correctly rather than guessed at. Its voices come from the "
                "list on Home.")

    def on_engine_pick(self, _event=None):
        self.read_tuning()
        _cache.clear()          # kalimat lama dibaca mesin yang lain
        self.iro_note.configure(text=self.engine_text())
        # Daftar suara hanya berarti untuk Irodori, dan menunggu ditekan
        # membuat kotaknya tampak rusak. Diambil sendiri begitu mesinnya dipilih.
        if state["tts_engine"] == "irodori" and str(state.get("irodori") or "").strip():
            self.find_iro()
        # Only Irodori can be told a tone, so switching engines changes whether
        # the row below does anything at all.
        self.emo_note.configure(text=self.emotion_text())

    def find_iro(self):
        self.read_tuning()
        if not str(state.get("irodori") or "").strip():
            self.iro_note.configure(text="No address given for Irodori.")
            return
        self.iro_btn.configure(state="disabled", text="…")

        def work():
            names = irodori_voices()
            alive = bool(names) or irodori_alive()
            self.root.after(0, lambda: self.on_iro_voices(names, alive))

        threading.Thread(target=work, daemon=True).start()

    def on_iro_voices(self, names, alive):
        self.iro_btn.configure(state="normal", text="Find")
        self.iro_hidup = bool(names) or bool(alive)
        self.refresh_iro_server()
        self.iro_pick.configure(values=names)
        if names:
            want = state.get("irodori_voice") or ""
            if want not in names:
                # "none" berarti membaca tanpa acuan sama sekali, dan ia berdiri
                # paling depan secara abjad -- memilihnya sebagai bawaan justru
                # mematikan kloning suara yang jadi alasan memakai Irodori.
                nyata = [n for n in names if n != "none"]
                want = nyata[0] if nyata else names[0]
            self.iro_pick.set(want)
            self.on_iro_pick()
            # on_iro_pick tidak berbuat apa-apa kalau namanya tidak berubah,
            # dan setelah menyala itu meninggalkan catatan "Starting - 12s"
            # tergantung di layar seolah ia masih memuat.
            self.iro_note.configure(text=self.engine_text())
            return
        self.clear_iro_voices()
        if alive:
            # Server ada tapi tidak mau menyebut daftarnya. Namanya masih bisa
            # diketik -- ia hanya membaca folder voices/ saat permintaan datang.
            self.iro_note.configure(
                text="Server is up but did not list its voices. Type the file "
                     "name from its voices/ folder, without the extension.")
        else:
            self.iro_note.configure(
                text="Nothing answered at %s. Press Start to run the engine."
                     % state.get("irodori"))

    def on_iro_pick(self, _event=None):
        name = self.iro_pick.get().strip()
        if not name or name == state.get("irodori_voice"):
            return
        state["irodori_voice"] = name
        _cache.clear()
        self.iro_note.configure(text=self.engine_text())

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
                play_wav(synthesize(text, sid, nada=True))
            except Exception:
                self.root.after(0, lambda: self.clip_note.configure(
                    text="gagal - VOICEVOX terbuka?"))

        threading.Thread(target=work, daemon=True).start()

    def poll_status(self):
        def work():
            alive = engine_alive()
            # Menumpang denyut yang sudah ada daripada memasang timer kedua:
            # dua pemeriksa yang berdetak sendiri-sendiri akan menampilkan dua
            # jawaban berbeda tentang hal yang sama.
            iro = irodori_alive() if state.get("tts_engine") == "irodori" else False
            self.root.after(0, lambda: self.on_status(alive, iro))

        threading.Thread(target=work, daemon=True).start()
        self.root.after(5000, self.poll_status)

    def on_status(self, alive, iro=None):
        was = self.engine_ok
        self.engine_ok = alive
        if iro is not None and not getattr(self, "iro_menunggu", False):
            sebelum = getattr(self, "iro_hidup", False)
            self.iro_hidup = iro
            if sebelum != iro:
                # Mati diam-diam harus terlihat: daftar suaranya ikut kosong.
                self.refresh_iro_server()
                if not iro:
                    self.clear_iro_voices()
                else:
                    self.find_iro()
        self.render_status()
        if alive and not self.all_voices:
            self.load_voices_async()
        elif was is not alive and not alive:
            self.render_library()

    def on_close(self):
        # Anak proses yang hidup lebih lama dari induknya menahan port dan
        # satu setengah gigabyte model tanpa ada yang memakainya.
        irodori_serve_stop()
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
