"""
PhiCorvi Sentence Audio -- fills a card's sentence-audio field by speaking the
sentence with VOICEVOX.

Mining a word from a novel gives you the sentence as text, but nothing to
listen to: there is no recording of a novel line the way there is for an anime
subtitle. This asks PhiCorvi to read it instead.

Audio comes from PhiCorvi's bridge rather than straight from VOICEVOX, because
PhiCorvi runs outside the Anki sandbox where ffmpeg lives, and can hand back
mp3. The same sentence as a wav is roughly ten times the size, which matters
once it is multiplied by a few thousand cards and synced.
"""

import hashlib
import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from anki import hooks
from aqt import gui_hooks, mw
from aqt.qt import QAction
from aqt.utils import askUser, showInfo, showWarning, tooltip

ADDON = __name__.split(".")[0]

DEFAULTS = {
    "bridge": "http://localhost:8772",
    "speaker": 19,
    "format": "mp3",
    "auto": True,
    "max_chars": 200,
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

def fetch(text, cfg):
    url = "%s/tts?%s" % (
        cfg["bridge"].rstrip("/"),
        urllib.parse.urlencode(
            {"text": text, "speaker": int(cfg["speaker"]), "format": cfg["format"]}
        ),
    )
    with urllib.request.urlopen(url, timeout=120) as resp:
        data = resp.read()
        kind = "mp3" if "mpeg" in (resp.headers.get("Content-Type") or "") else "wav"
    if not data:
        raise ValueError("bridge returned nothing")
    return data, kind


def store(col, text, speaker, data, kind):
    """Name the file after the sentence, so re-running never piles up copies of
    audio that is byte-for-byte identical."""
    digest = hashlib.sha1(("%s|%s" % (speaker, text)).encode("utf-8")).hexdigest()[:12]
    return col.media.write_data("phicorvi-%s.%s" % (digest, kind), data)


# ---------------------------------------------------------------- the targets

def resolved(col):
    """Config targets paired with the ordinals they actually map to, skipping
    any whose note type or field the collection does not have."""
    out = []
    for t in conf()["targets"]:
        model = col.models.by_name(t.get("notetype", ""))
        if not model:
            continue
        ords = {f["name"]: f["ord"] for f in model["flds"]}
        if t.get("sentence") in ords and t.get("audio") in ords:
            out.append((model["id"], t["notetype"], ords[t["sentence"]], ords[t["audio"]]))
    return out


def pending(col, extra=""):
    """Note ids that have a sentence but no sentence audio."""
    found = []
    for _mid, name, s_ord, a_ord in resolved(col):
        t = next(x for x in conf()["targets"] if x["notetype"] == name)
        query = '"note:%s" "%s:" -"%s:"' % (
            name.replace('"', '\\"'), t["audio"], t["sentence"])
        if extra:
            query = "%s (%s)" % (query, extra)
        try:
            ids = col.find_notes(query)
        except Exception:
            continue
        found.extend((nid, s_ord, a_ord) for nid in ids)
    return found


def fill(col, jobs, cfg, on_progress=None):
    """Synthesize and write. Returns (done, skipped, [errors])."""
    done = skipped = 0
    errors = []
    notes = []
    limit = int(cfg["max_chars"])
    for i, (nid, s_ord, a_ord) in enumerate(jobs):
        if on_progress and not on_progress(i, len(jobs)):
            break
        note = col.get_note(nid)
        if note.fields[a_ord].strip():
            skipped += 1
            continue
        text = clean(note.fields[s_ord])
        if not text or not HAS_JP.search(text) or len(text) > limit:
            skipped += 1
            continue
        try:
            data, kind = fetch(text, cfg)
            name = store(col, text, cfg["speaker"], data, kind)
        except Exception as exc:
            errors.append("%s: %s" % (text[:24], exc))
            if len(errors) >= 5:
                break
            continue
        note.fields[a_ord] = "[sound:%s]" % name
        if cfg["tag"]:
            note.add_tag(cfg["tag"])
        notes.append(note)
        done += 1
        if len(notes) >= 20:
            col.update_notes(notes)
            notes = []
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
        if not conf()["auto"] or _scheduled or mw is None or mw.col is None:
            return
        _scheduled = True
        mw.progress.single_shot(2500, _sweep, True)
    except Exception:
        _scheduled = False


def _sweep():
    global _scheduled
    _scheduled = False
    if mw.col is None or not conf()["auto"]:
        return
    jobs = pending(mw.col, "added:1")
    if not jobs:
        return
    cfg = conf()

    def work():
        return fill(mw.col, jobs, cfg)

    def done(fut):
        try:
            n, _skipped, errors = fut.result()
        except Exception:
            return
        if n:
            mw.reset()
            tooltip("PhiCorvi: %d audio kalimat ditambahkan" % n)
        elif errors:
            tooltip("PhiCorvi: gagal - %s" % errors[0][:60])

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
    if not jobs:
        showInfo("Tidak ada kartu yang perlu diisi (%s)." % where)
        return
    try:
        urllib.request.urlopen(cfg["bridge"].rstrip("/") + "/list?term=%E7%8C%AB", timeout=5).read()
    except Exception:
        showWarning(
            "PhiCorvi tidak menjawab di %s.\n\n"
            "Buka aplikasi PhiCorvi dulu, pastikan VOICEVOX-nya hidup, "
            "lalu coba lagi." % cfg["bridge"]
        )
        return
    if not askUser(
        "Isi audio kalimat untuk %d kartu (%s)?\n\n"
        "Perkiraan waktu: sekitar %d menit.\n"
        "Suara: speaker %s. Bisa dibatalkan di tengah jalan."
        % (len(jobs), where, max(1, round(len(jobs) * 2.5 / 60)), cfg["speaker"])
    ):
        return

    def work(col):
        def progress(i, total):
            if mw.progress.want_cancel():
                return False
            mw.taskman.run_on_main(
                lambda: mw.progress.update(
                    label="PhiCorvi: %d / %d kalimat" % (i, total), value=i, max=total
                )
            )
            return True

        return fill(col, jobs, cfg, progress)

    def done(result):
        n, skipped, errors = result
        mw.reset()
        msg = "Selesai: %d kartu terisi." % n
        if skipped:
            msg += "\n%d dilewati (sudah ada audio, kosong, atau terlalu panjang)." % skipped
        if errors:
            msg += "\n\nGagal:\n" + "\n".join(errors[:5])
        showInfo(msg)

    from aqt.operations import QueryOp

    QueryOp(parent=mw, op=work, success=done).with_progress(
        "PhiCorvi: membuat audio kalimat"
    ).run_in_background()


def on_browser_menus(browser):
    act = QAction("PhiCorvi: isi audio kalimat", browser)
    act.triggered.connect(lambda _=False, b=browser: run_bulk(b.selected_notes()))
    browser.form.menu_Notes.addAction(act)


def setup():
    act = QAction("PhiCorvi: isi audio kalimat kosong…", mw)
    act.triggered.connect(lambda _=False: run_bulk(None))
    mw.form.menuTools.addAction(act)


hooks.note_will_be_added.append(_after_add)
gui_hooks.browser_menus_did_init.append(on_browser_menus)
gui_hooks.main_window_did_init.append(setup)
