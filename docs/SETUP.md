# Give Yomitan a local Japanese TTS voice

Run VOICEVOX on your own machine, use it as a Yomitan audio source, and mine that
audio straight into Anki. No internet, no rate limits, no missing words.

Every word gets audio — even rare ones JapanesePod101 and Forvo have never heard of.
VOICEVOX has ~99 voices including several whisper styles, so you can pick something
that isn't fatiguing to hear a few hundred times a night.

*Tested on Linux with Yomitan 26.5 and VOICEVOX ENGINE (Docker). Works the same on
Windows and macOS.*

---

## 1. Run the VOICEVOX engine

Easiest with Docker — this pulls about 1.9 GB and listens on port `50021`:

```
docker run -d --name voicevox --restart unless-stopped \
  -p 127.0.0.1:50021:50021 \
  voicevox/voicevox_engine:cpu-ubuntu20.04-latest
```

No Docker? Install the **VOICEVOX app** instead — it ships the same engine and opens
the same port automatically while the app is running.

Check it's alive:

```
curl http://127.0.0.1:50021/version
```

> **Why `--restart unless-stopped`**
> Without it the container dies whenever the Docker daemon restarts — which
> snap-packaged Docker does on auto-update — and your audio silently stops working.

---

## 2. Save the bridge script

VOICEVOX and Yomitan don't speak the same language. VOICEVOX wants a two-step POST;
Yomitan wants a JSON list of audio URLs. This ~90-line script sits between them.

Save as `voicevox_bridge.py`. Needs Python 3, no libraries to install.

```python
#!/usr/bin/env python3
"""VOICEVOX -> Yomitan audio bridge."""

import json, os, sys, urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VOICEVOX_URL = os.environ.get("VOICEVOX_URL", "http://127.0.0.1:50021")
PORT = int(os.environ.get("PORT", "8772"))

# Voice ids offered to Yomitan, in order. Run with --list to see them all.
SPEAKERS = [int(s) for s in os.environ.get("SPEAKERS", "19,96").split(",") if s.strip()]

SPEED_SCALE = float(os.environ.get("SPEED_SCALE", "0.95"))
INTONATION_SCALE = float(os.environ.get("INTONATION_SCALE", "0.9"))

_cache, _names = {}, {}


def _post(path, data=None):
    req = urllib.request.Request(
        VOICEVOX_URL + path, data=data,
        headers={"Content-Type": "application/json"} if data else {}, method="POST")
    return urllib.request.urlopen(req, timeout=30).read()


def list_speakers():
    raw = urllib.request.urlopen(VOICEVOX_URL + "/speakers", timeout=15).read()
    for sp in json.loads(raw):
        for st in sp["styles"]:
            yield st["id"], sp["name"], st["name"]


def load_names():
    try:
        for sid, sp, st in list_speakers():
            _names[sid] = "%s (%s)" % (sp, st)
    except Exception:
        pass


def synthesize(text, speaker):
    key = (speaker, text)
    if key in _cache:
        return _cache[key]
    q = json.loads(_post("/audio_query?speaker=%d&text=%s"
                         % (speaker, urllib.parse.quote(text))))
    q["speedScale"] = SPEED_SCALE
    q["intonationScale"] = INTONATION_SCALE
    audio = _post("/synthesis?speaker=%d" % speaker, json.dumps(q).encode())
    if len(_cache) >= 256:
        _cache.clear()
    _cache[key] = audio
    return audio


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
        u = urllib.parse.urlparse(self.path)
        p = urllib.parse.parse_qs(u.query)
        # Speak the reading, not the kanji -- TTS mispronounces rare words otherwise.
        text = (p.get("reading") or p.get("term") or [""])[0].strip()
        if not text:
            self._send(b'{"type":"audioSourceList","audioSources":[]}', "application/json")
            return
        try:
            if u.path.rstrip("/") in ("", "/list"):
                host = self.headers.get("Host") or "localhost:%d" % PORT
                srcs = [{"name": _names.get(sid, "speaker %d" % sid),
                         "url": "http://%s/audio.wav?speaker=%d&reading=%s"
                                % (host, sid, urllib.parse.quote(text))}
                        for sid in SPEAKERS]
                body = json.dumps({"type": "audioSourceList", "audioSources": srcs},
                                  ensure_ascii=False).encode("utf-8")
                self._send(body, "application/json; charset=utf-8")
            else:
                req = (p.get("speaker") or [""])[0]
                self._send(synthesize(text, int(req) if req.isdigit() else SPEAKERS[0]),
                           "audio/wav")
        except urllib.error.URLError as e:
            self._send(("VOICEVOX unreachable at %s (%s)" % (VOICEVOX_URL, e)).encode(),
                       "text/plain", 502)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    if "--list" in sys.argv:
        for sid, sp, st in sorted(list_speakers()):
            print("%4d  %s (%s)" % (sid, sp, st))
        raise SystemExit(0)
    load_names()
    print("bridge on http://localhost:%d  voices: %s" % (PORT, SPEAKERS))
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
```

---

## 3. Start it

```
python3 voicevox_bridge.py
```

Leave the terminal open — closing it stops the bridge. Test in your browser:

```
http://localhost:8772/?term=猫&reading=ねこ
```

You should see JSON listing one audio URL per voice. If you do, you're done with the
hard part.

> **Don't change the port to 5060 or 5061**
> Those are SIP, and Chromium refuses to connect to them — you get `ERR_UNSAFE_PORT`
> and the extension never even sends a request. Also avoid ports you already use:
> `5050` (local-audio-yomichan), `8765` (AnkiConnect), `8770` (Forvo server).
> `8772` is clear.

---

## 4. Add it to Yomitan

1. Yomitan Settings → **Audio** → Configure audio playback sources
2. Add a source, type **Custom URL (JSON)**
3. URL: `http://localhost:8772/?term={term}&reading={reading}`
4. Drag it to the **top** of the list

Hover a word. It should speak.

> **Audio sources are per-profile**
> If you have multiple Yomitan profiles, adding the source to one does nothing in the
> others. Switch to the profile you actually read with and add it there too.

---

## 5. Mine it into Anki

Nothing extra to configure. Yomitan's `{audio}` field marker pulls from whatever audio
source it used — so once VOICEVOX sits at the top of the list, mined cards get
VOICEVOX audio.

In Yomitan Settings → Anki → your term model, put `{audio}` in your audio field.
Yomitan downloads the file and hands it to AnkiConnect like any other source.

Because the bridge answers for *every* word, you stop getting cards with silent audio
fields — the usual failure when JapanesePod101 and Forvo don't have an entry.

> **Keep a real-recording source too**
> Human recordings beat TTS for pitch accent. Put NHK/Forvo/JapanesePod101 *above*
> VOICEVOX and Yomitan uses the real recording when one exists, falling back to
> VOICEVOX only when nothing else has the word. Put VOICEVOX first only if you want
> one consistent voice everywhere.

---

## Choosing a voice

List everything your engine has:

```
python3 voicevox_bridge.py --list
```

The whisper styles, which are much easier on the ears for repeated listening:

| ID | Voice |
|----|-------|
| 19 | 九州そら (ささやき) |
| 22 | ずんだもん (ささやき) |
| 36 | 四国めたん (ささやき) |
| 37 | 四国めたん (ヒソヒソ) |
| 38 | ずんだもん (ヒソヒソ) |
| 71 | 満別花丸 (ささやき) |
| 96 | 中部つるぎ (ヒソヒソ) |

Set which ones the bridge offers with `SPEAKERS` — first one wins by default:

```
SPEAKERS=19,96 python3 voicevox_bridge.py
```

Softer delivery without changing voice — lower `INTONATION_SCALE` flattens the pitch:

```
SPEED_SCALE=0.9 INTONATION_SCALE=0.7 python3 voicevox_bridge.py
```

To make any of this permanent, edit the matching line near the top of the script.

---

## When it stops working

Check in this order — it's almost always the first two:

- **Is the bridge running?** It doesn't survive reboots or closing the terminal.
  Start it again.
- **Is the engine running?** `curl http://127.0.0.1:50021/version`. Docker containers
  without a restart policy die on daemon updates.
- **Does the URL open in your browser?** If the address bar can't load it, neither can
  Yomitan. `ERR_UNSAFE_PORT` means you picked a blocked port.
- **Right profile?** Audio sources don't carry across Yomitan profiles.
- **Is it at the top of the source list?** Yomitan plays the first source that returns
  audio.

---

## Appendix: Manatan

Manatan's popup dictionary can use the bridge, with two differences.

Use `localtest.me` instead of `localhost`. Manatan fetches audio through its own
server, and that proxy rejects loopback addresses with `403 Forbidden audio host`.
`localtest.me` is a public DNS name that resolves to `127.0.0.1`, so it passes the
check and still reaches your machine:

```
http://localtest.me:8772/audio.wav?term={term}&reading={reading}
```

Paste that into Audio Sources → **Custom Word Audio URL**.

> **Manatan can't make it the default**
> Its source order is hardcoded — JapanesePod101, LanguagePod101, Jisho, TTS, then
> custom — and isn't reorderable. On Auto it finds JapanesePod101 first and never
> reaches VOICEVOX. You can right-click the speaker button and pick Custom URL per
> word, but the choice resets on the next lookup. For automatic playback, use Yomitan.
