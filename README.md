# PhiCorvi

Give Yomitan a local Japanese voice. Every word gets audio — including the rare ones
JapanesePod101 and Forvo have never heard of — and it lands in your Anki cards
automatically.

<p align="center">
  <img src="docs/img/phicorvi-dark.png" alt="PhiCorvi in dark theme" width="420">
  <img src="docs/img/phicorvi-light.png" alt="PhiCorvi in light theme" width="420">
</p>

PhiCorvi connects [VOICEVOX](https://voicevox.hiroshiba.jp/) (a free Japanese speech
engine that runs on your own machine) to [Yomitan](https://yomitan.wiki/), which can't
talk to it directly. Point Yomitan at PhiCorvi and it just works.

- ~99 voices, including several whisper styles that don't get tiring after 300 lookups
- Works offline, no rate limits, no missing entries
- Mined Anki cards stop having silent audio fields
- One window: start, stop, pick voices, preview, copy the URL
- Reads whole sentences and paragraphs too, not just single words

*Named after φ Corvi, a star in Corvus — the crow. Crows imitate human speech, which is
more or less the job.*

---

## Download

**Windows:** grab `PhiCorvi.exe` from the
[latest release](https://github.com/XnoahR/PhiCorvi/releases/latest). Nothing to
install — double-click it. Python is bundled inside.

Windows will likely say *"Windows protected your PC"* the first time. That's what it
says about any new app without a paid code-signing certificate. Click **More info** →
**Run anyway**, or read the source here first — it's all in `phicorvi.py`.

**macOS / Linux:** run from source, `python3 phicorvi.py`. Needs Python 3 and nothing
else — the app only uses the standard library.

---

## Quick start

**1. Install and open [VOICEVOX](https://voicevox.hiroshiba.jp/).** Leave it running —
it's the part that actually speaks.

**2. Open PhiCorvi.** It starts the bridge itself, and the Status panel tells you
whether it can see VOICEVOX.

**3. Click **Copy** next to "Yomitan"** in the Connect panel.

**4. In Yomitan**: Settings → Audio → Configure audio playback sources → add a source
of type **Custom URL (JSON)** → paste → drag it to the **top** of the list.

Hover a Japanese word. It should speak.

For Anki, put `{audio}` in your audio field under Settings → Anki. Nothing else to
configure.

---

## The app

| | |
|---|---|
| **Start / Stop** | Runs the bridge. Remembers its state and restores it next launch. |
| **Voices** | Filter by group (ASMR, Female, Male, Tomboy, Sweet, Tsundere, Sexy, Calm, Energetic) or search by name. Add as many as you like and set their order. |
| **Preview** | Every row has its own ▶ button, so you always hear the voice you clicked. |
| **Copy** | Ready-to-paste URLs for Yomitan and Manatan. |
| **Speak any text** | Paste a sentence or a whole paragraph, hear it, and save it as a file. |
| **Settings** | Port, speed, intonation. Lower intonation = flatter, calmer. |
| **Theme** | Light and dark, both blue. |

Settings save to `phicorvi_config.json` beside the script.

### Whisper voices

Easiest on the ears when you're looking up hundreds of words a night:

| ID | Voice |
|----|-------|
| 19 | 九州そら (ささやき) |
| 22 | ずんだもん (ささやき) |
| 36 | 四国めたん (ささやき) |
| 37 | 四国めたん (ヒソヒソ) |
| 38 | ずんだもん (ヒソヒソ) |
| 71 | 満別花丸 (ささやき) |
| 96 | 中部つるぎ (ヒソヒソ) |

IDs come from your engine — the app lists whatever yours has.

---

## No-GUI version

`phicorvi_cli.py` is the same bridge without the window, for a server or if you prefer
a terminal:

```
python3 phicorvi_cli.py                     # defaults
SPEAKERS=19,96 python3 phicorvi_cli.py      # pick voices
python3 phicorvi_cli.py --list              # show every voice id
```

Configured entirely by environment variables: `SPEAKERS`, `PORT`, `SPEED_SCALE`,
`INTONATION_SCALE`, `VOICEVOX_URL`.

---

## Running VOICEVOX in Docker

If you'd rather not install the app:

```
docker run -d --name voicevox --restart unless-stopped \
  -p 127.0.0.1:50021:50021 \
  voicevox/voicevox_engine:cpu-ubuntu20.04-latest
```

`--restart unless-stopped` matters. Without it the container dies whenever the Docker
daemon restarts — which snap-packaged Docker does on auto-update — and your audio stops
with no visible reason.

---

## Troubleshooting

Check in this order. It's almost always the first one.

**No sound.** Is PhiCorvi still open? Is VOICEVOX still open? Both have to be running.

**Still no sound.** Paste the Yomitan URL into your browser's address bar. If the
browser can't load it, Yomitan can't either — that separates "the bridge is broken"
from "Yomitan is misconfigured" in one step.

**`ERR_UNSAFE_PORT` in the browser.** You changed the port to one Chromium refuses to
open. **5060 and 5061 are blocked** (they're SIP). Use 8772, or anything not on
[Chromium's blocked port list](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/net/base/port_util.cc).
PhiCorvi warns you before starting on a known-bad port.

**Port already in use.** Other Japanese-mining tools commonly hold `5050`
(local-audio-yomichan), `8765` (AnkiConnect) and `8770` (Forvo server). Pick another.

**Audio works for some words but not others.** Yomitan plays the *first* source that
returns audio. If VOICEVOX isn't at the top of the list, the sources above it win
whenever they have the word.

**Nothing happens at all, no errors.** Yomitan's audio sources are **per-profile**.
Adding the source to one profile does nothing in the others — switch to the profile
you actually read with and add it there too.

---

## A note on pitch accent

Synthesized speech approximates pitch accent; it doesn't reproduce it reliably. If
you're studying accent seriously, keep a real-recording source (NHK, Forvo,
JapanesePod101) **above** PhiCorvi. Yomitan then uses the human recording whenever one
exists and falls back to PhiCorvi only for words nothing else covers — which still
kills the silent-audio-field problem without trading away accuracy.

Put PhiCorvi first only if you want one consistent voice everywhere.

---

## Manatan

Manatan works too, with two differences.

Use `localtest.me` instead of `localhost` — Manatan fetches audio through its own
server, and that proxy rejects loopback addresses with `403 Forbidden audio host`.
`localtest.me` is a public DNS name that resolves to `127.0.0.1`, so it passes the check
and still reaches your machine. The app's "Manatan" Copy button gives you the right URL.

Manatan's source order is hardcoded — JapanesePod101, LanguagePod101, Jisho, TTS, then
custom — and can't be reordered, so on Auto it never reaches PhiCorvi. You can
right-click the speaker button and pick Custom URL per word, but the choice resets on
the next lookup. For automatic playback, use Yomitan.

---

## Setup guides

- **[Panduan Bahasa Indonesia](docs/PANDUAN-id.md)** — panduan lengkap pakai aplikasi,
  ditulis untuk yang belum terbiasa hal teknis
- [English](docs/SETUP.md) — manual setup without the app
- [Bahasa Indonesia (manual)](docs/SETUP-id.md) — cara manual tanpa aplikasi

---

## Licence

MIT. VOICEVOX itself has its own terms — each voice has its own rules about
[how generated audio may be used](https://voicevox.hiroshiba.jp/term/), and most
require crediting the character if you publish the audio. Personal study and Anki cards
are fine.
