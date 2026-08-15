# Bikin Yomitan Punya Suara Jepang Sendiri (Tanpa Internet)

Panduan ini bikin komputer kamu punya "pengisi suara" Jepang sendiri. Jadi setiap kata
yang kamu hover di Yomitan langsung ada suaranya — termasuk kata-kata langka yang
biasanya nggak ada suaranya sama sekali.

**Keuntungannya:**

- Semua kata ada suaranya, nggak ada lagi kartu Anki yang audionya kosong
- Nggak butuh internet, jadi nggak lemot
- Ada banyak pilihan suara (sekitar 99), termasuk suara berbisik yang enak didengar
  walaupun kamu dengerin ratusan kali semalam

**Butuh waktu:** sekitar 20-30 menit, sekali setup doang.

**Tenang, nggak perlu jago komputer.** Cuma copy-paste. Ikutin aja urutannya.

---

## Yang Perlu Disiapkan

Cuma dua aplikasi, dua-duanya gratis:

1. **VOICEVOX** — ini yang bikin suaranya
2. **Python** — buat jalanin satu file kecil (nanti dijelasin)

---

## Langkah 1 — Pasang VOICEVOX

1. Buka **voicevox.hiroshiba.jp**
2. Download versi buat komputer kamu (Windows / Mac / Linux)
3. Install biasa aja, kayak install aplikasi lain
4. **Buka aplikasinya, lalu biarkan terbuka**

Aplikasi ini harus tetap kebuka selama kamu belajar. Kalau ditutup, suaranya hilang.

> **Kenapa harus dibuka terus?**
> Karena VOICEVOX itu yang "ngomong". Kalau aplikasinya ketutup, ya nggak ada yang
> ngomong. Anggap aja kayak Anki — harus kebuka biar bisa dipakai.

---

## Langkah 2 — Pasang Python

Python itu program buat menjalankan file di Langkah 3. Nggak usah dipelajari, cuma
perlu dipasang.

1. Buka **python.org/downloads**
2. Klik tombol download yang besar (Download Python)
3. Jalankan file yang terdownload

**PENTING BUAT PENGGUNA WINDOWS:**
Di layar pertama installer, ada kotak centang kecil di bawah tulisannya:

```
[ ] Add python.exe to PATH
```

**Centang kotak itu dulu** sebelum klik Install. Kalau kelewatan, nanti filenya nggak
mau jalan dan kamu harus install ulang. Ini kesalahan paling sering terjadi.

Mac dan Linux biasanya Python-nya sudah ada, jadi bisa skip langkah ini.

---

## Langkah 3 — Simpan File Penghubung

VOICEVOX dan Yomitan itu nggak bisa langsung ngobrol — bahasanya beda. Jadi kita butuh
satu file kecil sebagai "penerjemah" di tengah-tengah mereka.

Caranya:

1. Buka **Notepad** (Windows) atau **TextEdit** (Mac)
2. Copy semua tulisan di bawah ini, paste ke situ
3. Save dengan nama: **`voicevox_bridge.py`**

Simpan di tempat yang gampang kamu temukan, misalnya Desktop.

> **Buat pengguna Windows:** waktu Save, di bagian "Save as type" pilih **All Files**
> dulu. Kalau nggak, nanti namanya jadi `voicevox_bridge.py.txt` dan nggak bisa jalan.
>
> **Buat pengguna Mac (TextEdit):** klik menu Format → **Make Plain Text** dulu sebelum
> menyimpan.

Ini isi filenya — copy semuanya, dari atas sampai bawah:

```python
#!/usr/bin/env python3
"""Penghubung VOICEVOX ke Yomitan."""

import json, os, sys, urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VOICEVOX_URL = os.environ.get("VOICEVOX_URL", "http://127.0.0.1:50021")
PORT = int(os.environ.get("PORT", "8772"))

# Nomor suara yang dipakai. Ganti angkanya kalau mau suara lain (lihat daftar di bawah).
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
        # Yang dibaca itu cara bacanya (hiragana), bukan kanjinya, biar nggak salah baca.
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
            self._send(("VOICEVOX tidak terhubung di %s (%s)" % (VOICEVOX_URL, e)).encode(),
                       "text/plain", 502)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    if "--list" in sys.argv:
        for sid, sp, st in sorted(list_speakers()):
            print("%4d  %s (%s)" % (sid, sp, st))
        raise SystemExit(0)
    load_names()
    print("Penghubung jalan di http://localhost:%d  suara: %s" % (PORT, SPEAKERS))
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
```

---

## Langkah 4 — Jalankan Filenya

**Klik dua kali file `voicevox_bridge.py` yang tadi kamu simpan.**

Akan muncul jendela hitam dengan tulisan seperti ini:

```
Penghubung jalan di http://localhost:8772  suara: [19, 96]
```

**Jangan ditutup jendela hitam itu.** Biarkan terbuka selama kamu belajar. Kalau
ditutup, suaranya berhenti.

### Cara mengecek berhasil atau nggak

Buka browser kamu, ketik alamat ini:

```
http://localhost:8772/?term=猫&reading=ねこ
```

Kalau muncul tulisan berantakan yang isinya ada nama-nama Jepang, **berarti berhasil.**
Bagian tersulit sudah lewat.

Kalau muncul tulisan error, cek dulu:

- VOICEVOX-nya sudah dibuka belum?
- Jendela hitamnya masih kebuka?

> **Jendela hitamnya langsung ketutup sendiri?**
> Berarti Python-nya belum kepasang, atau waktu install lupa mencentang
> "Add python.exe to PATH". Install ulang Python-nya, jangan lupa centang kotaknya.

---

## Langkah 5 — Sambungkan ke Yomitan

1. Buka pengaturan Yomitan (klik ikon Yomitan → gerigi/Settings)
2. Cari bagian **Audio**
3. Klik **Configure audio playback sources**
4. Klik tombol tambah, pilih jenis **Custom URL (JSON)**
5. Di kolom URL, isi dengan ini (copy-paste aja):

```
http://localhost:8772/?term={term}&reading={reading}
```

6. **Geser ke paling atas** di daftar itu

Selesai. Coba hover kata Jepang mana aja — harusnya langsung bunyi.

> **Punya lebih dari satu profil Yomitan?**
> Pengaturan suara itu beda-beda tiap profil. Jadi kalau kamu punya beberapa profil,
> kamu harus tambahkan ini di tiap profil yang kamu pakai. Kalau cuma ditambahin di
> satu profil, di profil lain nggak akan bunyi.

---

## Langkah 6 — Biar Ikut Masuk ke Kartu Anki

Nggak ada setting tambahan. Yomitan otomatis pakai suara yang lagi aktif.

Pastikan aja di pengaturan Yomitan → Anki, di kolom audio kamu sudah ada tulisan:

```
{audio}
```

Nah sekarang setiap kartu yang kamu mining bakal ada suaranya. Nggak ada lagi kartu
dengan audio kosong.

> **Saran: jangan taruh VOICEVOX paling atas kalau kamu peduli pitch accent**
> Suara rekaman orang asli itu lebih akurat pitch accent-nya daripada suara robot.
> Jadi lebih baik taruh sumber rekaman asli (NHK / Forvo / JapanesePod101) **di atas**
> VOICEVOX. Nanti Yomitan pakai rekaman asli kalau ada, dan baru pakai VOICEVOX kalau
> kata itu nggak ada rekamannya.
>
> Taruh VOICEVOX paling atas cuma kalau kamu memang mau semua suaranya seragam.

---

## Ganti Suara

Ada sekitar 99 suara. Yang paling enak buat belajar itu suara berbisik, karena nggak
bikin capek telinga:

| Nomor | Nama Suara |
|-------|------------|
| 19 | 九州そら (berbisik) |
| 22 | ずんだもん (berbisik) |
| 36 | 四国めたん (berbisik) |
| 37 | 四国めたん (berbisik pelan) |
| 38 | ずんだもん (berbisik pelan) |
| 71 | 満別花丸 (berbisik) |
| 96 | 中部つるぎ (berbisik pelan) |

**Cara gantinya:**

1. Klik kanan file `voicevox_bridge.py` → Open with → Notepad
2. Cari baris yang ada tulisan `SPEAKERS`
3. Ganti angka `19,96` jadi nomor suara yang kamu mau
4. Save, tutup jendela hitamnya, lalu klik dua kali lagi filenya

Kalau mau dengar semua pilihan suaranya dulu, buka aplikasi VOICEVOX — di situ bisa
dicoba satu-satu sambil lihat namanya.

**Mau suaranya lebih pelan dan lembut?** Di file yang sama, cari baris
`INTONATION_SCALE` lalu ganti `0.9` jadi `0.7`.

---

## Kalau Tiba-tiba Nggak Bunyi

Cek berurutan dari atas — biasanya penyebabnya nomor 1 atau 2:

1. **Jendela hitamnya masih kebuka?** Kalau komputer habis restart atau jendelanya
   ketutup, klik dua kali lagi file `voicevox_bridge.py`.
2. **Aplikasi VOICEVOX-nya kebuka?** Harus tetap terbuka.
3. **Coba buka alamat tesnya di browser** (yang di Langkah 4). Kalau browser aja nggak
   bisa buka, berarti Yomitan juga nggak bisa.
4. **Profil Yomitan-nya sudah benar?** Pengaturan suara beda-beda tiap profil.
5. **Sudah digeser ke paling atas?** Yomitan pakai sumber suara paling atas dulu.

> **Yang paling sering terjadi:** habis restart komputer, lupa jalanin lagi filenya.
> Kalau tiba-tiba nggak bunyi, itu tersangka utamanya.

---

## Tambahan: Buat Pengguna Manatan

Bisa dipakai di Manatan juga, tapi ada dua hal yang beda.

**Pertama**, jangan pakai `localhost`, tapi pakai `localtest.me`:

```
http://localtest.me:8772/audio.wav?term={term}&reading={reading}
```

Paste itu ke Audio Sources → **Custom Word Audio URL**.

Kenapa? Karena Manatan menolak alamat yang mengarah ke komputer sendiri. `localtest.me`
itu alamat internet yang sebenarnya menunjuk balik ke komputer kamu, jadi Manatan mau
menerimanya.

**Kedua**, di Manatan urutan sumber suaranya nggak bisa diubah. Dia selalu coba
JapanesePod101 duluan, jadi VOICEVOX-nya nggak akan kepakai otomatis. Kamu bisa klik
kanan tombol speaker lalu pilih Custom URL, tapi pilihannya balik lagi tiap ganti kata.

Jadi kalau mau yang otomatis, pakai Yomitan aja.

---

## Catatan Buat Yang Mau Lebih Simpel

Kalau kamu terbiasa pakai Docker, VOICEVOX bisa dijalankan tanpa install aplikasinya:

```
docker run -d --name voicevox --restart unless-stopped \
  -p 127.0.0.1:50021:50021 \
  voicevox/voicevox_engine:cpu-ubuntu20.04-latest
```

Kalau nggak paham Docker itu apa, abaikan aja bagian ini — pakai aplikasi VOICEVOX
biasa sudah cukup dan hasilnya sama persis.
