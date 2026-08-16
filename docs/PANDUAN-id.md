# Panduan PhiCorvi — Suara Jepang Custom di Yomitan

Panduan ini bikin setiap kata yang kamu hover di Yomitan punya suara — dan kamu bisa
pilih suaranya sendiri. Mau yang kawaii, tsundere, ngambek, sampai ASMR, semuanya ada.
Kartu Anki hasil mining juga otomatis ikut ada audionya.

**Butuh waktu:** sekitar 15 menit, sekali setup doang.
**Perlu jago komputer?** Nggak. Cuma download, klik, sama copy-paste.

---

## Butuh Dua Aplikasi

| Aplikasi | Gunanya |
|----------|---------|
| **VOICEVOX** | Mesin suaranya — ini yang benar-benar ngomong |
| **PhiCorvi** | Penyambung VOICEVOX ke Yomitan |

Dua-duanya gratis, dua-duanya jalan di komputer sendiri (nggak butuh internet), dan
**dua-duanya harus terbuka** selama kamu belajar.

> **Kenapa harus dua?**
> VOICEVOX bisa ngomong tapi nggak ngerti Yomitan. PhiCorvi jadi penerjemah di
> tengahnya. Kalau salah satu ditutup, suaranya hilang.

---

## Langkah 1 — Install VOICEVOX

1. Buka **https://voicevox.hiroshiba.jp**
2. Download versi Windows, install seperti aplikasi biasa
3. **Buka aplikasinya, biarkan terbuka**

Pertama kali dibuka agak lama karena menyiapkan model suara. Sabar aja.

---

## Langkah 2 — Download PhiCorvi

1. Buka **https://github.com/XnoahR/PhiCorvi/releases/latest**
2. Download file **`PhiCorvi.exe`**
3. Taruh di folder yang gampang dicari, misalnya bikin folder `PhiCorvi` di Documents

> **Muncul "Windows protected your PC"?**
> Normal, bukan virus. Windows selalu curiga sama aplikasi baru yang belum punya
> sertifikat berbayar (harganya jutaan per tahun).
>
> Klik **More info** → **Run anyway**.
>
> Kalau ragu, kode programnya terbuka dan bisa diperiksa siapa saja di
> https://github.com/XnoahR/PhiCorvi

---

## Langkah 3 — Buka PhiCorvi

Klik dua kali **`PhiCorvi.exe`**. Yang pertama kamu lihat adalah status di bagian atas:

| Tulisannya | Artinya |
|------------|---------|
| **Ready** (hijau) | Semua beres, tinggal dipakai |
| **VOICEVOX is not open** (merah) | Aplikasi VOICEVOX belum dibuka |
| **Paused** (kuning) | Klik tombol **Start** |

Kalau merah, buka aplikasi VOICEVOX dulu, tunggu beberapa detik — nanti berubah
sendiri jadi **Ready**.

Kalau sudah **Ready**, jendelanya boleh di-minimize. Jangan ditutup.

---

## Langkah 4 — Sambungkan ke Yomitan

1. Di PhiCorvi, klik tombol biru **Copy link**
2. Buka pengaturan Yomitan → bagian **Audio**
3. Klik **Configure audio playback sources**
4. Tambah sumber baru, pilih jenis **Custom URL (JSON)**
5. Klik kolom URL, tekan **Ctrl+V**
6. **Geser sumber ini ke paling atas**

Selesai. Coba hover kata Jepang — harusnya langsung bunyi.

> **Punya beberapa profil Yomitan?**
> Pengaturan audio di Yomitan itu **beda-beda tiap profil**. Kalau kamu punya profil
> "bilingual" dan "monolingual", tambahkan sumber ini di tiap profil yang kamu pakai.
> Ini penyebab paling sering "kok udah dipasang tapi nggak bunyi".

---

## Langkah 5 — Biar Masuk ke Kartu Anki

Nggak ada setting tambahan.

Cek di pengaturan Yomitan → **Anki** → pastikan di kolom audio ada tulisan `{audio}`.
Kalau sudah, kartu hasil mining otomatis ada suaranya.

> **Saran soal pitch accent**
> Suara buatan (TTS) pitch accent-nya cuma mendekati, nggak selalu akurat. Kalau kamu
> serius belajar pitch accent, taruh sumber rekaman asli (NHK / Forvo /
> JapanesePod101) **di atas** PhiCorvi.
>
> Yomitan akan pakai rekaman manusia kalau ada, dan PhiCorvi cuma dipakai buat kata
> yang nggak ada rekamannya. Jadi kamu dapat dua-duanya: akurat *dan* nggak ada kartu
> yang sunyi.
>
> Taruh PhiCorvi paling atas cuma kalau kamu mau semua suaranya seragam satu orang.

---

## Cara Ganti dan Menambah Suara

Ada **99 suara** di VOICEVOX. Semuanya bisa dipakai.

Jendela PhiCorvi punya dua bagian:

- **VOICES YOMITAN WILL USE** (atas) — suara yang sedang dipakai, sesuai urutan
- **ADD A VOICE** (bawah) — semua suara yang tersedia

### Dengar dulu sebelum pilih

Tiap baris punya tombol **▶** di sebelah kiri. Klik tombol itu, suaranya langsung
diputar. Yang kamu klik, itu yang bunyi — jadi bisa coba-coba sepuasnya dulu.

### Cari pakai grup

Di bawah kolom pencarian ada tombol-tombol grup:

| Grup | Isinya |
|------|--------|
| **All** | Semua suara |
| **ASMR** | Suara berbisik — paling nyaman buat hover ratusan kata |
| **Female** | Karakter perempuan |
| **Male** | Karakter laki-laki |
| **Tomboy** | Suara tomboy |
| **Sweet** | Manja, imut (あまあま) |
| **Tsundere** | Judes-judes gimana gitu (ツンツン) |
| **Sexy** | Dewasa, berat (セクシー) |
| **Calm** | Tenang, pelan |
| **Energetic** | Ceria, semangat |

Klik grupnya, daftarnya langsung tersaring. Atau ketik nama karakternya di kolom
pencarian kalau sudah tahu mau yang mana.

### Menambah suara

Klik **+ Add** di baris suara yang kamu mau. Langsung pindah ke daftar atas, nggak
perlu restart apa-apa.

### Mengatur urutan

Yomitan pakai suara **nomor 1** dulu. Kalau gagal, baru turun ke nomor 2, dan
seterusnya.

Di daftar atas, tiap baris ada tombol:

- **↑ ↓** — naik/turunkan urutannya
- **✕** — hapus dari daftar

### Bikin suaranya lebih lembut

Klik **Advanced settings** di paling bawah:

- **Speed** — kecepatan bicara. Kecilkan ke `0.90` biar lebih pelan
- **Intonation** — naik-turun nada. Kecilkan ke `0.70` biar lebih datar dan kalem

Semua pengaturan tersimpan otomatis.

---

## Ganti Tema Terang / Gelap

Klik tombol **☾ Dark** / **☀ Light** di pojok kanan atas. Pilihannya diingat.

---

## Kalau Tiba-tiba Nggak Bunyi

Cek berurutan. Hampir selalu penyebabnya nomor 1.

**1. PhiCorvi-nya masih kebuka?**
Habis restart komputer, kamu harus buka lagi `PhiCorvi.exe`. Dia nggak jalan sendiri.

**2. Statusnya "Ready"?**
Kalau merah, buka aplikasi VOICEVOX. Kalau kuning, klik **Start**.

**3. Profil Yomitan-nya sudah benar?**
Pengaturan audio beda-beda tiap profil.

**4. Sudah digeser ke paling atas?**
Kalau ada sumber lain di atasnya, itu yang menang duluan.

> **Yang paling sering kejadian:** habis restart komputer, lupa buka PhiCorvi lagi.

### Muncul "Port already in use"

Ada program lain yang pakai nomor yang sama. Klik **Advanced settings**, ganti angka
**Port** jadi `8773`, lalu klik **Start** lagi.

Jangan pakai `5060` atau `5061` — browser menolak dua nomor itu, jadi Yomitan nggak
akan bisa nyambung. PhiCorvi akan memperingatkan kalau kamu salah pilih.

---

## Buat Pengguna Manatan

Bisa juga, tapi ada dua catatan.

Klik tombol **for Manatan** (bukan yang biru — alamatnya beda). Paste ke Manatan →
Audio Sources → **Custom Word Audio URL**.

Tapi di Manatan urutan sumber suara **nggak bisa diubah**. Dia selalu coba
JapanesePod101 duluan, jadi PhiCorvi nggak kepakai otomatis. Bisa klik kanan tombol
speaker lalu pilih Custom URL, tapi pilihannya balik lagi tiap ganti kata.

Kalau mau otomatis, pakai Yomitan.

---

## Catatan Hak Pakai Suara

Suara VOICEVOX gratis dipakai, tapi tiap karakter punya aturan sendiri. Untuk belajar
pribadi dan kartu Anki, bebas.

Kalau mau **upload audionya** (YouTube, TikTok, dll), biasanya wajib mencantumkan nama
karakternya. Aturan lengkapnya: https://voicevox.hiroshiba.jp/term/

---

## Buat Pengguna Mac dan Linux

Belum ada `.exe`, tapi bisa jalan langsung dari kode:

1. Install Python 3 dari https://python.org
2. Download `phicorvi.py` dari https://github.com/XnoahR/PhiCorvi
3. Jalankan: `python3 phicorvi.py`

Tampilan dan cara pakainya sama persis.
