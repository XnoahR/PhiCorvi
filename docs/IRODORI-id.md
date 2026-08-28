# Panduan Irodori — Kalimat Anki Dibaca Suara Pilihanmu

VOICEVOX punya karakternya sendiri, dan itu tetap bawaan PhiCorvi. Panduan ini
untuk hal lain: **Irodori** bisa menirukan suara siapa pun dari satu rekaman
pendek. Kasih dia klip sepuluh detik, dan kalimat mining-mu dibacakan dengan
suara itu.

**Butuh waktu:** sekitar 20 menit, kebanyakan nunggu download.
**Perlu jago komputer?** Nggak. Tapi butuh kartu grafis NVIDIA, dan add-on
Anki-nya sudah terpasang — **Download engine** menaruh mesinnya di dalam folder
add-on itu, karena cuma folder itu yang pasti dimiliki semua orang dan selamat
waktu add-on diperbarui.

---

## Baca Ini Dulu

Irodori berat, dan lebih baik kamu tahu sekarang daripada di tengah jalan.

| | |
|---|---|
| **Kartu grafis** | NVIDIA, minimal 4 GB VRAM. Tanpa itu jalan juga, tapi 18× lebih lambat — satu kalimat semenit. Praktis nggak kepakai. |
| **Ruang disk** | Unduhan ~5 GB, terpakai ~6 GB. Pemasangnya minta 11 GB kosong sebagai jaga-jaga. Bisa dihentikan lalu disambung. |
| **Kecepatan** | ~5 detik per kalimat baru. Kartu yang sama diputar ulang gratis. |
| **Internet** | Cuma sekali waktu download. Setelah itu jalan sepenuhnya offline. |

VOICEVOX tetap dipakai kalau Irodori mati, jadi kartumu nggak akan pernah
kosong audionya.

---

## Langkah 1 — Download Mesinnya

Buka PhiCorvi, masuk tab **Reading**, klik **Download engine**.

Kotak konfirmasi bakal nyebutin ukurannya dan folder tujuannya sebelum ada yang
diunduh. Semuanya masuk ke folder add-on Anki-mu, bukan ke sembarang tempat —
dan folder itu selamat kalau add-on-nya diperbarui.

Yang diunduh: mesin Python-nya sendiri (jadi komputermu nggak perlu punya
Python), sumber servernya, dan bobot modelnya.

Modelnya sendiri cuma **1,3 GB**. Sisanya PyTorch dan pustaka CUDA — sekitar
7 GB, dan itu ongkos masuk semua TTS neural, bukan sesuatu yang khas Irodori.
Kalau kamu sudah pernah memasang sesuatu berbasis PyTorch, sebagiannya dipakai
bersama dan yang benar-benar bertambah jauh lebih kecil.

> **Kalau berhenti di tengah**, tinggal klik lagi. Yang sudah terunduh dilewati.

---

## Langkah 2 — Nyalakan

Masih di tab Reading, klik **Start**.

Loading modelnya makan sekitar setengah menit. Catatannya bakal ngitung detik
dan nunjukin apa yang lagi dikerjakan servernya, jadi kamu tahu itu jalan bukan
nyangkut. Kalau gagal, tiga baris terakhir lognya langsung ditampilin.

Kalau sudah hidup, titik **Irodori** di halaman Home berubah hijau.

---

## Langkah 3 — Kasih Dia Suara

Irodori nggak punya koleksi suara. Kamu yang kasih.

Klik **Add…** di sebelah *Reference voice*, pilih satu rekaman. Nama filenya
jadi nama suaranya. Selesai — nggak ada training, nggak ada tunggu-tunggu.

### Rekamannya harus kayak gimana

Cuma **8 detik pertama** yang dipakai, tapi syaratnya cukup ketat:

| Syarat | Kenapa |
|---|---|
| **Satu orang** | Dua suara nyampur jadi satu suara rata-rata yang bukan siapa-siapa |
| **Nggak ada musik** | Musiknya ikut ditiru, dan kedengeran di **setiap** kalimatmu |
| **Nggak ada gema** | Ruangannya ikut ditiru, suaranya jadi kayak di gua |
| **Orang ngomong** | Bukan teriakan, tawa, atau gumaman — itu bukan cara orang bicara |
| **10 detik ke atas** | Kurang dari itu ciri suaranya belum kebaca lengkap |

> **Yang paling sering bikin gagal:** bahannya jelek, bukan setelannya. Kalau
> hasilnya nggak mirip, ganti rekamannya dulu sebelum utak-atik yang lain.

### Dari mana dapat rekamannya

Kalau kamu mining anime, asbplayer sudah motong audio per kalimat — itu persis
bentuk yang dibutuhkan. Ambil beberapa baris karakter yang sama **tanpa musik
latar**, sambung, selesai. Adegan tenang di dalam ruangan biasanya paling
bersih; adegan aksi hampir selalu ada BGM-nya.

Situs TTS yang punya model karakter juga bisa — keluarannya memang bersih.
Render 10–15 detik teks Jepang, download WAV, masukin lewat **Add…**.

### Nyusun banyak karakter

Suara itu satu folder berisi rekaman:

```
<folder add-on>/user_files/irodori/voice_model/
    bocchi/     bocchi.mp3
    nijika/     nijika.mp3
    waguri/     1-waguri2.mp3
```

Nama foldernya jadi nama suaranya. Nambah karakter = bikin folder, jatuhin
rekaman, selesai — nggak perlu restart apa pun.

Kalau satu folder isinya beberapa file, semuanya disambung urut nama, jadi
**file pertama yang nentuin suaranya**. Kasih awalan angka kalau mau ngatur
urutannya.

---

## Langkah 4 (Opsional) — Nada Adegan

Kalimat dibaca datar itu wajar. Tapi kalau mau kalimatnya kedengeran sesuai
suasananya, nyalakan **Scene tone**.

Cara kerjanya: sebuah model bahasa baca kalimat mining-mu, lalu nyisipin emoji
yang dimengerti Irodori sebagai petunjuk cara membaca — kikik di sini, kaget di
situ.

Isi tab **Scene tone** dengan API key punyamu sendiri, nama model, dan alamat
layanan apa pun yang formatnya cocok-OpenAI.

> **Kalimatmu nggak akan pernah diubah kata-katanya.** Jawaban modelnya cuma
> dipakai kalau setelah emoji dicabut hasilnya sama persis huruf per huruf. Model
> yang parafrase, hapus klausa, atau "betulin" kanji langka bakal ditolak. Di
> aplikasi kosakata, kartu yang bacanya beda dari yang kamu mining itu lebih
> buruk daripada kartu yang dibaca datar.

Tiga hal yang perlu diketahui:

- **Cuma jalan buat kalimat utuh.** Hover kata di Yomitan dilewati — satu kata
  nggak punya adegan.
- **Satu panggilan per kalimat baru**, jawabannya disimpan. Di layanan gratis
  panggilan ini biasanya bagian paling lambat, dan waktunya naik-turun.
- **Semua kegagalan diam dan aman.** Nggak ada key, nggak ada jawaban, jawaban
  ngawur — kalimatnya tetap dibaca, cuma tanpa emoji.

---

## Kalau Ada Masalah

**Reference voice-nya kosong.** Servernya belum jalan. Klik **Start**; daftarnya
keisi sendiri begitu servernya jawab.

**Tombolnya bilang "Running" tapi nggak bisa diklik.** Servernya hidup tapi
bukan PhiCorvi yang nyalain — mungkin dari terminal. PhiCorvi nggak bisa matiin
yang bukan miliknya.

**Suaranya nggak mirip.** Cek 8 detik pertama rekamannya. Itu satu-satunya
bagian yang dipakai, dan kalau di situ ada musik, tawa, atau orang lain, itu
yang ditiru.

**Kalimatnya kedengeran suara VOICEVOX.** Irodori mati, dan PhiCorvi jatuh
balik biar kartumu tetap ada audionya. Nyalakan lagi; jawaban `/tts` bawa header
`X-Engine` yang nyebutin siapa yang benar-benar ngomong.

**Anki nggak nemu servernya.** Anki pakai port 5050. Irodori pakai 8088 dan
PhiCorvi 8772, jadi harusnya nggak tabrakan — tapi kalau kamu ganti, hindari
5050.
