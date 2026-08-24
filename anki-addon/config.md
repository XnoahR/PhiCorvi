### PhiCorvi Sentence Audio

Butuh aplikasi **PhiCorvi** hidup (dan VOICEVOX di dalamnya) waktu mengisi audio.

- **bridge** — alamat PhiCorvi. Biarkan `http://localhost:8772` kecuali portnya kamu ubah.
- **speaker** — biarkan `0` supaya ikut suara nomor 1 di jendela PhiCorvi.
  Ganti urutannya di sana (tombol ↑↓), audio kalimatnya ikut berubah. Isi angka
  di sini cuma kalau kamu sengaja mau audio kalimat memakai suara yang berbeda
  dari yang dipakai Yomitan.
- **format** — `mp3` (kecil, disarankan) atau `wav`.
- **auto** — `true` berarti kartu yang baru kamu mining langsung diisi sendiri.
  Lebih gampang lewat **Tools → PhiCorvi → Isi audio kalimat otomatis saat
  mining**. Matikan kalau audio kalimatmu sudah datang dari sumber lain —
  mining anime dengan asbplayer misalnya — supaya tidak ada sintesis yang
  percuma dan menghambat.
- **max_chars** — kalimat lebih panjang dari ini dilewati.
- **tag** — tag yang ditempel supaya audio TTS bisa dibedakan dari rekaman asli.
- **targets** — pasangan note type + nama field. Tambah sendiri kalau note type kamu lain.
  `sentence` boleh diisi daftar: dicoba berurutan, yang pertama ada isinya dipakai.
  Berguna kalau `{sentence}` Yomitan kamu matikan tapi versi furiganya tetap terisi —
  ruby-nya dibuang, jadi yang dibacakan tetap kalimat biasa.

Mengisi banyak kartu sekaligus: **Tools → PhiCorvi: isi audio kalimat kosong…**
Untuk kartu tertentu saja: pilih di Browse, lalu menu **Notes**.

- **auto_limit** — berapa kartu paling banyak diisi sekali sapuan otomatis. Sisanya disusul sapuan berikutnya.
- **check_updates** — cek sekali sehari apakah ada versi baru di GitHub. Matikan kalau tidak mau add-on menghubungi internet sama sekali.
