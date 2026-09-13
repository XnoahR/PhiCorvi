"""
PhiCorvi Sentence Audio -- fills a card's empty audio fields, the word's and
the sentence's, by having PhiCorvi read them.

Mining a word from a novel gives you the sentence as text, but nothing to
listen to: there is no recording of a novel line the way there is for an anime
subtitle. This asks PhiCorvi to read it instead. The word is read from its
reading field where the note type has one -- a mined 引数 is ひきすう, and no
engine reading the kanji cold would get that right.

Audio comes from PhiCorvi's bridge rather than straight from VOICEVOX, because
PhiCorvi runs outside the Anki sandbox where ffmpeg lives, and can hand back
mp3. The same sentence as a wav is roughly ten times the size, which matters
once it is multiplied by a few thousand cards and synced.
"""

import hashlib
import html
import json
import os
import re
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request

from anki import hooks
from aqt import gui_hooks, mw
from aqt.qt import QAction
from aqt.utils import askUser, showInfo, showWarning, tooltip

ADDON = __name__.split(".")[0]
VERSION = "1.6.0"
REPO = "XnoahR/PhiCorvi"
RELEASES = "https://github.com/%s/releases/latest" % REPO
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "user_files", "phicorvi.log")


def log(msg):
    """An add-on that fails silently is indistinguishable from one that never
    loaded, which makes it impossible to tell apart from the outside. Every
    decision that ends in "do nothing" says so here."""
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write("%s  %s\n" % (time.strftime("%H:%M:%S"), msg))
    except Exception:
        pass


DEFAULTS = {
    "bridge": "http://localhost:8772",
    "speaker": 0,
    "format": "mp3",
    "auto": True,
    "max_chars": 200,
    "auto_limit": 25,
    "check_updates": True,
    "tag": "phicorvi-tts",
    "targets": [],
}


def conf():
    cfg = dict(DEFAULTS)
    try:
        cfg.update(mw.addonManager.getConfig(ADDON) or {})
    except Exception:
        pass
    return cfg


# ------------------------------------------------------------------ the text

SOUND = re.compile(r"\[sound:[^]]*\]")
# <rt> is the reading; <rp> is the bracket a browser shows when it cannot
# render ruby. Both are furigana scaffolding -- dropping only <rt> leaves
# the sentence littered with empty ()().
RT = re.compile(r"<(rt|rp)[^>]*>.*?</\1>", re.S | re.I)
BR = re.compile(r"<br\s*/?>|</(?:div|p|li)>", re.I)
TAG = re.compile(r"<[^>]+>")
BRACKET = re.compile(r"\[[^]]*\]")          # Anki-style furigana: 漢字[かんじ]
_JP = "\u3000-\u303f\u3040-\u30ff\u4e00-\u9fff\uff00-\uffef"
# Japanese does not space its words, so a space between two kana is noise.
# Between Latin words it is not: strip it and VOICEVOX reads BOCCHI THE ROCK
# as one run-on word.
GLUE = re.compile(r"(?<=[%s])[ \t\u3000]+(?=[%s])" % (_JP, _JP))
RUNS = re.compile(r"[ \t\u3000]{2,}")
STOPS = "。．！？!?、，,」』）)"


def clean(raw):
    """Turn a mined sentence field into something worth reading aloud.

    The field is HTML: Yomitan bolds the target word, and line breaks arrive as
    <br>. Reading the markup out loud is obviously wrong, but so is deleting a
    <br> outright -- two clauses would run together with no pause.
    """
    if not raw:
        return ""
    text = SOUND.sub("", raw)
    text = RT.sub("", text)                  # ruby scaffolding, never the base text
    text = BR.sub("\n", text)
    text = TAG.sub("", text)
    text = html.unescape(text)
    text = BRACKET.sub("", text)
    out = []
    for part in (p.strip() for p in text.split("\n")):
        if not part:
            continue
        if out and out[-1][-1] not in STOPS:
            out.append("、")
        out.append(part)
    text = "".join(out)
    text = GLUE.sub("", text)
    text = RUNS.sub(" ", text)
    return text.strip()


HAS_JP = re.compile(r"[぀-ヿ一-鿿]")


# ------------------------------------------------------------------ the audio

def fetch(text, cfg, nada=True):
    """Ask PhiCorvi to read something.

    The voice is deliberately not sent unless someone has pinned one here: two
    places holding a voice setting means the one you cannot see wins, and it did
    -- every mined sentence came out in the whisper voice while the app showed
    something else. Left at 0, PhiCorvi's own first voice is used, so changing it
    in the app changes it here.

    `nada` is off for single words. A word has no scene to have a tone, and on
    an engine that marks tone up with a language model, asking for one buys ten
    seconds of queue per word for nothing. A bridge that predates the
    parameter ignores it and behaves as it always did.
    """
    params = {"text": text, "format": cfg["format"]}
    if not nada:
        params["nada"] = "0"
    try:
        pinned = int(cfg["speaker"])
    except (TypeError, ValueError):
        pinned = 0
    if pinned > 0:
        params["speaker"] = pinned

    url = "%s/tts?%s" % (cfg["bridge"].rstrip("/"), urllib.parse.urlencode(params))
    with urllib.request.urlopen(url, timeout=120) as resp:
        data = resp.read()
        kind = "mp3" if "mpeg" in (resp.headers.get("Content-Type") or "") else "wav"
        # Whichever voice actually spoke, so the filename tells two of them apart
        voice = (resp.headers.get("X-Speaker") or "").strip() or str(pinned)
    if not data:
        raise ValueError("bridge returned nothing")
    return data, kind, voice


def store(col, text, speaker, data, kind):
    """Name the file after the sentence, so re-running never piles up copies of
    audio that is byte-for-byte identical."""
    digest = hashlib.sha1(("%s|%s" % (speaker, text)).encode("utf-8")).hexdigest()[:12]
    return col.media.write_data("phicorvi-%s.%s" % (digest, kind), data)


# ---------------------------------------------------------------- the targets

def resolved(col):
    """Every field the config asks to fill and the collection actually has.

    One entry per audio field, not per target: a target may name a sentence pair
    and a word pair, and each entry carries every name and ordinal it will need.
    Looking the target back up by note type later is how the second pair came to
    search with the first pair's audio field -- the lookup found the first match
    and stopped.

    A pair may list several source fields. People turn off Yomitan's plain
    {sentence} when a source gives it messy text, and keep only the furigana
    one; JPMN keeps the word's reading in a field of its own. The first field
    with something in it is read, so nobody has to change their mining setup to
    suit this add-on.
    """
    out = []
    for t in conf()["targets"]:
        model = col.models.by_name(t.get("notetype", ""))
        if not model:
            continue
        ords = {f["name"]: f["ord"] for f in model["flds"]}
        for jenis, k_src, k_audio in (("sentence", "sentence", "audio"),
                                      ("word", "word", "word_audio")):
            wanted = t.get(k_src)
            wanted = [wanted] if isinstance(wanted, str) else list(wanted or [])
            names = [n for n in wanted if n in ords]
            audio = t.get(k_audio)
            if names and audio in ords:
                out.append({
                    "mid": model["id"], "notetype": t["notetype"], "jenis": jenis,
                    "src_names": names, "src_ords": [ords[n] for n in names],
                    "audio_name": audio, "audio_ord": ords[audio],
                })
    return out


def pending(col, extra=""):
    """Notes with something to read and no audio for it, grouped by note.

    Grouped, because a note can need both its word and its sentence filled, and
    two Note objects for one id written in the same batch overwrite each other:
    the second was loaded before the first was saved, and carries the old empty
    field back over the new one. One Note per id, every field on it.
    """
    per_note = {}
    for spec in resolved(col):
        any_src = " or ".join('-"%s:"' % n for n in spec["src_names"])
        query = '"note:%s" "%s:" (%s)' % (
            spec["notetype"].replace('"', '\\"'), spec["audio_name"], any_src)
        if extra:
            query = "%s (%s)" % (query, extra)
        try:
            ids = col.find_notes(query)
        except Exception:
            log("pencarian gagal: %s" % query)
            continue
        for nid in ids:
            per_note.setdefault(nid, []).append(spec)
    return sorted(per_note.items())


def fill(col, jobs, cfg, on_progress=None):
    """Synthesize and write. Returns (done, skipped, [errors]).

    `done` counts fields, not notes: a note that got both its word and its
    sentence counts twice, and that is the number the person waiting sees.
    """
    done = skipped = 0
    errors = []
    notes = []
    limit = int(cfg["max_chars"])
    for i, (nid, specs) in enumerate(jobs):
        if on_progress and not on_progress(i, len(jobs)):
            break
        note = col.get_note(nid)
        changed = False
        for spec in specs:
            a_ord = spec["audio_ord"]
            if note.fields[a_ord].strip():
                skipped += 1
                continue
            text = ""
            for s_ord in spec["src_ords"]:
                text = clean(note.fields[s_ord])
                if text:
                    break
            if not text or not HAS_JP.search(text) or len(text) > limit:
                skipped += 1
                continue
            try:
                data, kind, voice = fetch(text, cfg, nada=spec["jenis"] == "sentence")
                name = store(col, text, voice, data, kind)
            except Exception as exc:
                errors.append("%s: %s" % (text[:24], exc))
                if len(errors) >= 5:
                    break
                continue
            note.fields[a_ord] = "[sound:%s]" % name
            changed = True
            done += 1
        if changed:
            if cfg["tag"]:
                note.add_tag(cfg["tag"])
            notes.append(note)
            if len(notes) >= 20:
                col.update_notes(notes)
                notes = []
        if len(errors) >= 5:
            break
    if notes:
        col.update_notes(notes)
    return done, skipped, errors


# ------------------------------------------------------- automatic, on mining

_scheduled = False


def _after_add(*args):
    """note_will_be_added fires before the note has an id, so we cannot act on
    it directly -- just note that something arrived and look shortly after.

    Everything here is wrapped: this runs inside col.add_note(), so an exception
    escaping would abort the add itself and break mining outright. A sentence
    with no audio is a small loss; a card that refuses to be created is not.
    """
    global _scheduled
    try:
        cfg = conf()
        if not cfg["auto"]:
            log("hook: kartu ditambah, tapi auto=false")
            return
        if _scheduled:
            return
        if mw is None or mw.col is None:
            log("hook: kartu ditambah, tapi mw/col belum siap")
            return
        _scheduled = True
        log("hook: kartu ditambah, sapuan dijadwalkan 2.5 dtk lagi")
        mw.progress.single_shot(2500, _sweep, True)
    except Exception:
        _scheduled = False
        log("hook: error\n" + traceback.format_exc())


def _sweep():
    global _scheduled
    _scheduled = False
    if mw.col is None or not conf()["auto"]:
        return
    cfg = conf()
    # "added:1" means everything added today, not just the card you just mined.
    # Mine fifty words in one sitting and an uncapped sweep would tie VOICEVOX up
    # for minutes with no progress bar and no way out -- while you are still
    # trying to mine. Take a bite, then come back for the rest.
    log("sapuan: mulai")
    found = pending(mw.col, "added:1")
    log("sapuan: %d kartu perlu audio" % len(found))
    limit = max(1, int(cfg.get("auto_limit", 25)))
    jobs, rest = found[:limit], len(found) - limit
    if not jobs:
        return

    def work():
        return fill(mw.col, jobs, cfg)

    def done(fut):
        try:
            n, _skipped, errors = fut.result()
        except Exception:
            log("sapuan: meledak\n" + traceback.format_exc())
            tooltip("PhiCorvi: gagal, lihat phicorvi.log")
            return
        log("sapuan: selesai, terisi %d, error %s" % (n, errors or "tidak ada"))
        if n:
            mw.reset()
            tooltip("PhiCorvi: %d audio ditambahkan" % n)
        elif errors:
            tooltip("PhiCorvi: gagal - %s" % errors[0][:60])
        if rest > 0:
            _after_add()

    mw.taskman.run_in_background(work, done)


# --------------------------------------------------------------- manual, bulk

def run_bulk(nids=None):
    if mw.col is None:
        return
    cfg = conf()
    if nids is None:
        jobs = pending(mw.col)
        where = "seluruh koleksi"
    else:
        wanted = set(nids)
        jobs = [j for j in pending(mw.col) if j[0] in wanted]
        where = "kartu terpilih"
    n_kolom = sum(len(specs) for _, specs in jobs)
    # Dicatat sebelum dialog apa pun: "tidak jalan" tanpa log berarti menebak
    # apakah yang kosong itu pencariannya, koneksinya, atau memang kartunya.
    log("bulk: %s -> %d note, %d kolom" % (where, len(jobs), n_kolom))
    if not jobs:
        showInfo("Tidak ada kolom audio yang perlu diisi (%s).\n\n"
                 "Yang dicari: note type di daftar targets, field sumbernya ada "
                 "isinya, field audionya kosong." % where)
        return
    try:
        urllib.request.urlopen(cfg["bridge"].rstrip("/") + "/list?term=%E7%8C%AB", timeout=5).read()
    except Exception as exc:
        log("bulk: PhiCorvi tidak menjawab di %s: %s" % (cfg["bridge"], exc))
        showWarning(
            "PhiCorvi tidak menjawab di %s.\n\n"
            "Buka aplikasi PhiCorvi dulu, pastikan mesin suaranya hidup, "
            "lalu coba lagi." % cfg["bridge"]
        )
        return
    if not askUser(
        "Isi %d kolom audio di %d note (%s)?\n\n"
        "Perkiraan waktu: sekitar %d menit.\n"
        "Suara: %s. Bisa dibatalkan di tengah jalan."
        % (n_kolom, len(jobs), where, max(1, round(n_kolom * 2.5 / 60)),
           "ikut PhiCorvi" if int(cfg["speaker"] or 0) <= 0
           else "speaker %s" % cfg["speaker"])
    ):
        log("bulk: dibatalkan di dialog")
        return

    def work(col):
        def progress(i, total):
            if mw.progress.want_cancel():
                return False
            mw.taskman.run_on_main(
                lambda: mw.progress.update(
                    label="PhiCorvi: %d / %d note" % (i, total), value=i, max=total
                )
            )
            return True

        return fill(col, jobs, cfg, progress)

    def done(result):
        n, skipped, errors = result
        log("bulk: selesai, terisi %d, dilewati %d, error %s" % (n, skipped, errors or "tidak ada"))
        mw.reset()
        msg = "Selesai: %d kolom audio terisi." % n
        if skipped:
            msg += "\n%d dilewati (sudah ada audio, kosong, atau terlalu panjang)." % skipped
        if errors:
            msg += "\n\nGagal:\n" + "\n".join(errors[:5])
        showInfo(msg)

    from aqt.operations import QueryOp

    QueryOp(parent=mw, op=work, success=done).with_progress(
        "PhiCorvi: membuat audio"
    ).run_in_background()


def on_browser_menus(browser):
    act = QAction("PhiCorvi: isi audio", browser)
    act.triggered.connect(lambda _=False, b=browser: run_bulk(b.selected_notes()))
    browser.form.menu_Notes.addAction(act)


def check_update():
    """Anki updates add-ons it installed from AnkiWeb; this one arrives as a
    file, so nobody would ever hear about a new version without opening GitHub
    to look. Once a day, in the background, and silent unless there is news.

    The version comes from the /releases/latest redirect rather than the API,
    whose 60-an-hour unauthenticated budget is counted per IP and is routinely
    already spent by strangers on a shared address.
    """
    if not conf().get("check_updates", True):
        return
    stamp = os.path.join(os.path.dirname(LOG), "lastcheck")
    try:
        if time.time() - os.path.getmtime(stamp) < 86400:
            return
    except OSError:
        pass

    def work():
        try:
            req = urllib.request.Request(
                RELEASES, method="HEAD",
                headers={"User-Agent": "PhiCorviSentenceAudio/%s" % VERSION})
            with urllib.request.urlopen(req, timeout=10) as resp:
                final = resp.geturl()
        except Exception:
            return None
        os.makedirs(os.path.dirname(stamp), exist_ok=True)
        open(stamp, "w").close()
        found = re.search(r"/tag/v?([0-9]+(?:\.[0-9]+)*)", final or "")
        return found.group(1) if found else None

    def done(fut):
        try:
            found = fut.result()
        except Exception:
            return
        if not found:
            return
        try:
            new = [int(x) for x in found.split(".")]
            cur = [int(x) for x in VERSION.split(".")]
        except ValueError:
            return
        if new > cur:
            log("versi %s tersedia (terpasang %s)" % (found, VERSION))
            tooltip("PhiCorvi Sentence Audio %s sudah keluar "
                    "(kamu pakai %s) - Tools > PhiCorvi" % (found, VERSION), period=8000)

    mw.taskman.run_in_background(work, done)


def set_auto(on):
    """Flip automatic filling without opening the config.

    Mining from video already brings its own audio, and having a second one
    synthesised over every card makes that slower for no gain -- so this has to
    be reachable in a second, not buried in a JSON file."""
    raw = mw.addonManager.getConfig(ADDON) or {}
    raw["auto"] = bool(on)
    mw.addonManager.writeConfig(ADDON, raw)
    log("auto -> %s" % bool(on))
    tooltip("Audio otomatis: %s" % ("nyala" if on else "mati"), period=3000)


HOME = os.path.dirname(os.path.abspath(__file__))


def say_hello():
    """Beri tahu PhiCorvi di mana add-on ini berada.

    PhiCorvi memasang mesin Irodori ke dalam folder add-on, karena itulah satu-
    satunya folder yang pasti dimiliki setiap pengguna -- mereka tidak menarik
    repo. Tapi PhiCorvi tidak bisa menebaknya dengan andal: folder data Anki
    berbeda di empat platform, dan nama folder add-on bisa berupa nomor
    AnkiWeb. Yang tahu persis letaknya hanya add-on itu sendiri.

    Dijalankan di luar thread utama dan gagal diam-diam: PhiCorvi mungkin belum
    menyala, dan itu bukan alasan menahan Anki saat dibuka.
    """
    url = "%s/hello?home=%s" % (conf()["bridge"].rstrip("/"),
                                urllib.parse.quote(HOME))
    try:
        with urllib.request.urlopen(url, timeout=4) as r:
            jawab = json.loads(r.read().decode("utf-8", "replace"))
        log("hello -> %s, engine di %s"
            % (jawab.get("ok"), jawab.get("engine_home")))
    except Exception as exc:
        log("hello gagal (PhiCorvi belum jalan?): %s" % exc)


def setup():
    menu = mw.form.menuTools.addMenu("PhiCorvi")

    auto = QAction("Isi audio otomatis saat mining", mw)
    auto.setCheckable(True)
    auto.setChecked(bool(conf()["auto"]))
    auto.setToolTip("Matikan kalau audio kalimatnya sudah datang dari sumber "
                    "lain, misalnya asbplayer waktu mining anime")
    auto.toggled.connect(set_auto)
    menu.addAction(auto)

    menu.addSeparator()
    act = QAction("Isi audio yang kosong…", mw)
    act.triggered.connect(lambda _=False: run_bulk(None))
    menu.addAction(act)
    mw.progress.single_shot(8000, check_update, True)
    # Menyentuh jaringan, jadi jangan di thread utama saat Anki baru dibuka.
    threading.Thread(target=say_hello, daemon=True).start()


log("--- add-on dimuat ---")
hooks.note_will_be_added.append(_after_add)
gui_hooks.browser_menus_did_init.append(on_browser_menus)
gui_hooks.main_window_did_init.append(setup)
