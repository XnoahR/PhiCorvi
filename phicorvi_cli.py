#!/usr/bin/env python3
"""
PhiCorvi (no-GUI) -- VOICEVOX to Yomitan / Manatan audio bridge.

Turns a local VOICEVOX ENGINE into a Yomitan-compatible audio source, so
looking up a word plays it in a whisper ("ASMR"-style) synthesized voice.

Run VOICEVOX ENGINE first (it must be listening on VOICEVOX_URL), then:

    python3 phicorvi_cli.py

Endpoints:
    /                       -> Yomitan "Custom URL (JSON)" audioSourceList,
                               one entry per voice in SPEAKERS
    /audio.wav?reading=...  -> the synthesized audio itself
                               (add &speaker=NN to pick a specific voice)

Wire it up:
    Yomitan  : Custom URL (JSON)
               -> http://localhost:8772/?term={term}&reading={reading}
    Manatan  : Custom Word Audio URL
               -> http://localtest.me:8772/audio.wav?term={term}&reading={reading}

Manatan must use "localtest.me" rather than "localhost". Its audio proxy refuses
loopback and private addresses outright ("403 Forbidden audio host"), and every
lookup is fetched server-side through that proxy. localtest.me is a public DNS
name that resolves to 127.0.0.1, so it clears the host check and still reaches
this bridge.

List the voice ids your engine offers with:  phicorvi_cli.py --list
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VOICEVOX_URL = os.environ.get("VOICEVOX_URL", "http://127.0.0.1:50021")

# Not 5060/5061: those are SIP, which Chromium refuses to connect to
# (ERR_UNSAFE_PORT), so no browser extension can ever reach them.
PORT = int(os.environ.get("PORT", "8772"))

# Voices offered in the JSON list, in order. Yomitan falls back down this list
# when an entry fails, and Manatan's plain-audio endpoint uses the first one.
SPEAKERS = [
    int(s) for s in os.environ.get("SPEAKERS", "19,96").split(",") if s.strip()
]

# A whisper style reads softer than the same speaker's normal style. Nudging the
# speed down and the intonation flat pushes it further toward the ASMR sound.
SPEED_SCALE = float(os.environ.get("SPEED_SCALE", "0.95"))
INTONATION_SCALE = float(os.environ.get("INTONATION_SCALE", "0.9"))
VOLUME_SCALE = float(os.environ.get("VOLUME_SCALE", "1.0"))

CACHE_LIMIT = 256
_cache = {}
_names = {}


def _post(path, data=None):
    req = urllib.request.Request(
        VOICEVOX_URL + path,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method="POST",
    )
    return urllib.request.urlopen(req, timeout=30).read()


def list_speakers():
    raw = urllib.request.urlopen(VOICEVOX_URL + "/speakers", timeout=15).read()
    for speaker in json.loads(raw):
        for style in speaker["styles"]:
            yield style["id"], speaker["name"], style["name"]


def load_names():
    """Label the JSON entries with real voice names, so the source list in
    Yomitan reads '九州そら (ささやき)' instead of a bare number."""
    try:
        for sid, speaker, style in list_speakers():
            _names[sid] = "%s (%s)" % (speaker, style)
    except Exception:
        pass  # labels are cosmetic; a bare id still works


def label(sid):
    return _names.get(sid, "speaker %d" % sid)


def synthesize(text, speaker):
    key = (speaker, text)
    if key in _cache:
        return _cache[key]
    query = json.loads(
        _post("/audio_query?speaker=%d&text=%s" % (speaker, urllib.parse.quote(text)))
    )
    query["speedScale"] = SPEED_SCALE
    query["intonationScale"] = INTONATION_SCALE
    query["volumeScale"] = VOLUME_SCALE
    audio = _post("/synthesis?speaker=%d" % speaker, json.dumps(query).encode())
    if len(_cache) >= CACHE_LIMIT:
        _cache.clear()
    _cache[key] = audio
    return audio


class Handler(BaseHTTPRequestHandler):
    def _send(self, body, ctype, status=200):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        # Chromium blocks public-context requests into the private network
        # (localhost) unless the response opts in explicitly.
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        # The reading is what should actually be spoken -- feeding raw kanji to a
        # TTS engine is how you get the wrong pronunciation on rarer words.
        text = (params.get("reading") or params.get("term") or [""])[0].strip()

        if not text:
            self._send(b'{"type":"audioSourceList","audioSources":[]}', "application/json")
            return

        try:
            if parsed.path.rstrip("/") in ("", "/list"):
                # Hand back the same host the caller used. Manatan refuses to
                # fetch anything whose host looks local, so a hardcoded
                # "localhost" here would get the whole list thrown away even
                # when the list itself was requested over an accepted name.
                host = self.headers.get("Host") or "localhost:%d" % PORT
                sources = [
                    {
                        "name": label(sid),
                        "url": "http://%s/audio.wav?speaker=%d&reading=%s"
                        % (host, sid, urllib.parse.quote(text)),
                    }
                    for sid in SPEAKERS
                ]
                body = json.dumps(
                    {"type": "audioSourceList", "audioSources": sources},
                    ensure_ascii=False,
                ).encode("utf-8")
                self._send(body, "application/json; charset=utf-8")
            else:
                requested = (params.get("speaker") or [""])[0]
                speaker = int(requested) if requested.isdigit() else SPEAKERS[0]
                self._send(synthesize(text, speaker), "audio/wav")
        except urllib.error.URLError as exc:
            msg = ("VOICEVOX unreachable at %s (%s)" % (VOICEVOX_URL, exc)).encode()
            self._send(msg, "text/plain", 502)

    def log_message(self, fmt, *args):
        if os.environ.get("BRIDGE_LOG"):
            sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))
            sys.stderr.flush()


if __name__ == "__main__":
    if "--list" in sys.argv:
        for sid, speaker, style in sorted(list_speakers()):
            print("%4d  %s (%s)" % (sid, speaker, style))
        raise SystemExit(0)

    load_names()
    print("bridge  : http://localhost:%d" % PORT)
    print("engine  : %s" % VOICEVOX_URL)
    print("voices  : %s" % ", ".join("%d %s" % (s, label(s)) for s in SPEAKERS))
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
