# Panduan PhiCorvi — Suara Jepang Otomatis di Yomitan

Panduan ini bikin setiap kata yang kamu hover di Yomitan langsung ada suaranya,
termasuk kata-kata langka yang biasanya sunyi. Kartu Anki hasil mining juga otomatis
ada audionya.

**Butuh waktu:** sekitar 15 menit, sekali setup doang.
**Perlu jago komputer?** Nggak. Cuma download, klik, sama copy-paste.

---

## Butuh Dua Aplikasi

| Aplikasi | Gunanya |
|----------|---------|
| **VOICEVOX** | Yang bikin suaranya (mesin suaranya) |
| **PhiCorvi** | Yang menyambungkan VOICEVOX ke Yomitan |

Dua-duanya gratis. Dua-duanya harus **tetap terbuka** selama kamu belajar.

> **Kenapa harus dua?**
> VOICEVOX itu yang bisa ngomong, tapi dia nggak ngerti Yomitan. PhiCorvi jadi
> penerjemah di tengahnya. Tanpa PhiCorvi, Yomitan nggak tahu cara minta suara ke
> VOICEVOX.

---

## Langkah 1 — Download VOICEVOX

1. Buka **https://voicevox.hiroshiba.jp**
2. Klik tombol download, pilih versi Windows
3. Install seperti aplikasi biasa (klik Next terus sampai selesai)
4. **Buka aplikasinya, biarkan terbuka**

Pertama kali dibuka agak lama karena dia menyiapkan model suaranya. Sabar aja.

---

## Langkah 2 — Download PhiCorvi

1. Buka **https://github.com/XnoahR/PhiCorvi/releases**
2. Di bagian paling atas, cari file **`PhiCorvi.exe`**
3. Klik untuk download
4. Pindahkan ke folder yang gampang dicari, misalnya bikin folder `PhiCorvi` di Documents

> **Windows bilang "Windows protected your PC"?**
> Ini normal dan bukan virus. Windows selalu curiga sama aplikasi baru yang belum
> dibeli sertifikatnya (harganya jutaan per tahun).
>
> Klik **More info** → **Run anyway**.
>
> Kalau kamu ragu, kode programnya terbuka dan bisa dilihat siapa aja di
> https://github.com/XnoahR/PhiCorvi

> **Kenapa filenya sekitar 10-15 MB?**
> Karena Python-nya ikut dibundel di dalam, jadi kamu nggak perlu install Python
> terpisah. Tinggal klik dua kali, jalan.

---

## Langkah 3 — Buka PhiCorvi

Klik dua kali **`PhiCorvi.exe`**.

Akan muncul jendela seperti ini:

```
┌─ Status ──────────────────────────────────────────┐
│  VOICEVOX engine   ●  connected          [ Start ]│
│  Bridge            ●  running on port 8772        │
└───────────────────────────────────────────────────┘
```

**Cek bagian Status:**

- **VOICEVOX engine: ● connected** (hijau) → bagus, VOICEVOX-nya kebaca
- **○ not running** (merah) → aplikasi VOICEVOX-nya belum dibuka. Buka dulu, tunggu
  beberapa detik, nanti berubah sendiri jadi hijau.

**Bridge** biasanya langsung `running` sendiri. Kalau masih `stopped`, klik tombol
**Start**.

Sudah. Jendela ini biarkan terbuka (boleh di-minimize).

---

## Langkah 4 — Sambungkan ke Yomitan

1. Di PhiCorvi, klik tombol **Copy** yang di sebelah tulisan **Yomitan**
2. Buka pengaturan Yomitan (klik ikon Yomitan → **Settings**)
3. Cari bagian **Audio**
4. Klik **Configure audio playback sources**
5. Klik tombol tambah, pilih jenis **Custom URL (JSON)**
6. Klik kolom URL-nya, tekan **Ctrl+V** (paste)
7. **Geser sumber ini ke paling atas** di daftar

Selesai! Coba hover kata Jepang mana aja — harusnya langsung bunyi.

> **Punya beberapa profil Yomitan?**
> Pengaturan audio di Yomitan itu **beda-beda tiap profil**. Jadi kalau kamu punya
> profil "bilingual" dan "monolingual" misalnya, kamu harus tambahkan sumber ini di
> tiap profil yang kamu pakai. Ini penyebab paling sering "kok nggak bunyi ya".

---

## Langkah 5 — Biar Masuk ke Kartu Anki

Nggak ada setting tambahan.

Cek aja di pengaturan Yomitan → **Anki** → di kolom audio kamu sudah ada tulisan:

```
{audio}
```

Kalau sudah ada, otomatis kartu yang kamu mining ada suaranya.

> **Saran soal pitch accent**
> Suara buatan (TTS) itu pitch accent-nya cuma mendekati, nggak selalu akurat. Kalau
> kamu serius belajar pitch accent, taruh sumber rekaman asli (NHK / Forvo /
> JapanesePod101) **di atas** PhiCorvi.
>
> Nanti Yomitan pakai rekaman manusia kalau ada, dan PhiCorvi cuma dipakai buat kata
> yang nggak ada rekamannya. Jadi kamu tetap dapat dua-duanya: akurat *dan* nggak ada
> kartu yang sunyi.
>
> Taruh PhiCorvi paling atas cuma kalau kamu mau semua suaranya seragam satu orang.

---

## Cara Menambah dan Mengganti Suara

Ada sekitar **99 suara** di VOICEVOX. Semuanya bisa dipakai.

Di jendela PhiCorvi, bagian **Voices**:

- Kotak **kiri** = semua suara yang tersedia
- Kotak **kanan** = suara yang dipakai Yomitan (sesuai urutan)

### Menambah suara

1. Di kotak pencarian kiri, ketik `whisper` (buat cari suara berbisik)
   atau ketik nama karakternya
2. Klik suara yang kamu mau
3. Klik tombol **Preview** dulu buat dengar contohnya
4. Kalau suka, klik **Add →**

Suaranya langsung pindah ke kotak kanan. Nggak perlu restart apa-apa.

### Mengatur urutan

Yomitan pakai suara **paling atas** dulu. Kalau gagal, baru turun ke bawahnya.

Klik suara di kotak kanan, lalu:

- **Move up** — naikkan
- **Move down** — turunkan
- **← Remove** — hapus dari daftar

### Suara berbisik (paling nyaman buat belajar)

Ini yang paling enak didengar kalau kamu hover ratusan kata semalam:

| Nomor | Nama |
|-------|------|
| 19 | 九州そら (ささやき) |
| 22 | ずんだもん (ささやき) |
| 36 | 四国めたん (ささやき) |
| 37 | 四国めたん (ヒソヒソ) |
| 38 | ずんだもん (ヒソヒソ) |
| 71 | 満別花丸 (ささやき) |
| 96 | 中部つるぎ (ヒソヒソ) |

Ketik `whisper` di kotak pencarian, semua ini langsung muncul.

### Bikin suaranya lebih lembut

Di bagian **Settings**:

- **Speed** — kecepatan bicara. Kecilkan jadi `0.90` biar lebih pelan
- **Intonation** — naik-turun nada. Kecilkan jadi `0.70` biar lebih datar dan kalem

Semua pengaturan tersimpan otomatis.

---

## Ganti Tema Terang / Gelap

Klik tombol **Dark theme** / **Light theme** di pojok kanan atas. Pilihannya diingat.

---

## Kalau Tiba-tiba Nggak Bunyi

Cek berurutan. Hampir selalu penyebabnya nomor 1.

**1. PhiCorvi-nya masih kebuka?**
Kalau komputer habis restart, kamu harus buka lagi `PhiCorvi.exe`. Dia nggak jalan
sendiri.

**2. VOICEVOX-nya masih kebuka?**
Lihat bagian Status di PhiCorvi. Kalau merah, buka aplikasi VOICEVOX.

**3. Bridge-nya sudah "running"?**
Kalau masih `stopped`, klik **Start**.

**4. Profil Yomitan-nya sudah benar?**
Pengaturan audio beda-beda tiap profil.

**5. Sudah digeser ke paling atas?**
Kalau ada sumber lain di atasnya, sumber itu yang menang duluan.

> **Yang paling sering kejadian:** habis restart komputer, lupa buka PhiCorvi lagi.
> Kalau tiba-tiba sunyi, itu tersangka utamanya.

### Kalau muncul error "Port already in use"

Berarti ada program lain yang pakai port yang sama. Di bagian **Settings**, ganti
angka **Port** jadi angka lain, misalnya `8773`, lalu klik **Start** lagi.

Jangan pakai `5060` atau `5061` — browser menolak dua port itu, jadi Yomitan nggak
akan bisa nyambung. PhiCorvi akan kasih peringatan kalau kamu salah pilih.

---

## Buat Pengguna Manatan

Bisa juga, tapi ada dua catatan.

Klik tombol **Copy** yang di sebelah **Manatan** (bukan yang Yomitan — alamatnya
beda). Paste ke Manatan → Audio Sources → **Custom Word Audio URL**.

Tapi di Manatan urutan sumber suaranya **nggak bisa diubah**. Dia selalu coba
JapanesePod101 duluan, jadi PhiCorvi nggak akan kepakai otomatis. Kamu bisa klik kanan
tombol speaker terus pilih Custom URL, tapi pilihannya balik lagi tiap ganti kata.

Jadi kalau mau yang otomatis, pakai Yomitan.

---

## Catatan Soal Hak Pakai Suara

Suara VOICEVOX gratis dipakai, tapi tiap karakter punya aturannya sendiri. Untuk
belajar pribadi dan kartu Anki, bebas.

Kalau kamu mau **upload audionya** (misalnya ke YouTube atau TikTok), biasanya wajib
mencantumkan nama karakternya. Cek aturan lengkapnya di
https://voicevox.hiroshiba.jp/term/

---

## Buat Pengguna Mac dan Linux

Belum ada file `.exe` buat Mac/Linux, tapi bisa jalan langsung dari kode:

1. Install Python 3 dari https://python.org
2. Download `phicorvi.py` dari https://github.com/XnoahR/PhiCorvi
3. Jalankan: `python3 phicorvi.py`

Tampilan dan cara pakainya sama persis.
