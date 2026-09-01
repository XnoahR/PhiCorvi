# Irodori: read your mined sentences in a voice you choose

VOICEVOX ships its own characters, and it stays PhiCorvi's default. This guide
is about the other option: **Irodori** copies a voice from one short recording
while it reads. Give it ten seconds of somebody talking, and your mined
sentences come back in that voice.

**Time:** about 20 minutes, most of it waiting on a download.
**Needs:** an NVIDIA card, and the Anki add-on installed -- **Download engine**
puts the engine inside the add-on's folder, which is the one folder every user
has and which survives add-on upgrades.

> **No graphics card?** **Fish Audio** does the same job on their servers: pick
> it under Engine on the Reading tab, paste a key and a voice link, and there is
> nothing to install. You give up working offline, and your sentences go to
> their machines. Everything below is about running it yourself instead.

---

## Read this first

Irodori is heavy, and it is better to know now than halfway in.

| | |
|---|---|
| **Graphics card** | NVIDIA, 4 GB VRAM or more. It runs without one, at 18× realtime -- roughly a minute a sentence, which is not usable. |
| **Disk** | ~5 GB downloaded, ~6 GB used. The installer asks for 11 GB free as headroom. Stoppable and resumable. |
| **Speed** | ~5 seconds per new sentence. Replaying a card is free. |
| **Internet** | Only for the download. After that it runs entirely offline. |

If Irodori is not running, sentences fall back to VOICEVOX, so a card is never
left without audio.

---

## 1. Download the engine

Open PhiCorvi, go to the **Reading** tab, press **Download engine**.

The dialog names the size and the destination before anything downloads.
Everything lands inside your Anki add-on folder rather than somewhere you have
to remember -- and that folder survives add-on upgrades.

It fetches its own Python, so the machine needs neither Python nor git.

The model itself is only **1.3 GB**. The rest is PyTorch and the CUDA libraries,
around 7 GB, which is the entry cost of any neural TTS rather than anything
particular to Irodori. If you already have a PyTorch install, much of it is
shared and the real growth is far smaller.

> **If it stops partway**, press it again. Whatever finished is skipped.

---

## 2. Start it

Still on the Reading tab, press **Start**.

Loading the model takes about half a minute. The note counts the seconds and
shows what the server itself is saying, so a slow start is distinguishable from
a hung one. If it dies, the last three lines of its log are shown instead of a
blank failure.

Once it answers, the **Irodori** dot on Home turns green.

---

## 3. Give it a voice

Irodori has no catalogue of voices. You supply one.

Press **Add…** beside *Reference voice* and pick a recording. The filename
becomes the voice name. That is the whole step -- no training, nothing to wait
for.

### What the recording needs to be

Only the **first 8 seconds** are used, and they need to be the right 8 seconds:

| Requirement | Why |
|---|---|
| **One speaker** | Two voices blend into an average that is nobody |
| **No music** | It gets copied into the voice, and you hear it in *every* sentence |
| **No echo** | The room is copied too, and everything sounds like a cave |
| **Speech, not reactions** | Yelps, laughs and grunts are not how a person talks |
| **10 seconds or more** | Less than that and the voice is not fully described |

> **The usual cause of a bad clone is the material, not the settings.** If it
> does not sound right, change the recording before changing anything else.

### Where to get one

If you mine anime, asbplayer already cuts audio per line -- exactly the shape
this needs. Take a few lines from one character **with no background music**,
join them, done. Quiet indoor scenes are usually cleanest; action scenes almost
always have a score under them.

A TTS site with character voices works too, since its output is clean by
construction. Render 10-15 seconds of Japanese, download the WAV, bring it in
with **Add…**.

### Keeping several characters

A voice is a folder of recordings:

```
<add-on>/user_files/irodori/voice_model/
    bocchi/     bocchi.mp3
    nijika/     nijika.mp3
    waguri/     1-waguri2.mp3
```

The folder name is the voice name. Add a character by making a folder and
dropping a recording in -- nothing to restart.

Where a folder holds several files they are joined in filename order, so **the
first file decides the voice**. Prefix them with numbers if you want to control
that.

---

## 4. Optional: scene tone

A sentence read flat is fine. If you would rather it sounded like the scene it
came from, turn on **Scene tone**.

A language model reads each mined sentence and marks it up with the emoji
Irodori understands as delivery instructions -- a chuckle here, a gasp there.

Fill in the **Scene tone** tab with an API key of your own, a model name, and
the address of any OpenAI-compatible endpoint.

> **Your sentence is never reworded.** The reply is only used when removing the
> emoji gives your sentence back character for character, so a model that
> paraphrases, drops a clause, or "corrects" a rare kanji is discarded. In a
> vocabulary tool, a card that reads back something other than what you mined is
> worse than a card read flatly.

Three things worth knowing:

- **It only runs on whole sentences.** Yomitan word lookups skip it -- a single
  word has no scene to have a tone.
- **One call per new sentence**, and the answer is kept, so replaying is free.
  On a free provider that call is usually the slowest part of the chain, and its
  latency varies more than the synthesis does.
- **Every failure is silent and harmless.** No key, no answer, a bad reply, and
  the sentence is simply read plainly.

---

## When something is wrong

**Reference voice is empty.** The server is not running. Press **Start**; the
list fills itself once it answers.

**The button says "Running" and cannot be pressed.** The engine is up, but
something other than PhiCorvi started it -- a terminal, most likely. PhiCorvi
will not stop a process it does not own.

**It does not sound like the person.** Listen to the first 8 seconds of the
recording. That is the only part used, and music, laughter or a second speaker
in there is what gets copied.

**Sentences come back in a VOICEVOX voice.** Irodori is down and PhiCorvi fell
back so the card would still have audio. Start it again; `/tts` replies carry an
`X-Engine` header naming whichever one actually spoke.

**Ports.** Anki listens on 5050. Irodori uses 8088 and PhiCorvi 8772, so nothing
collides by default -- but if you change them, avoid 5050.
