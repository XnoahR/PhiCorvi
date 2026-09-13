### PhiCorvi Sentence Audio

Mengisi field audio yang kosong — audio kata dan audio kalimat — dengan minta
PhiCorvi membacakannya. Butuh aplikasi **PhiCorvi** hidup waktu mengisi.

- **bridge** — alamat PhiCorvi. Biarkan `http://localhost:8772` kecuali portnya kamu ubah.
- **speaker** — biarkan `0` supaya ikut suara nomor 1 di jendela PhiCorvi.
  Ganti urutannya di sana (tombol ↑↓), audio kalimatnya ikut berubah. Isi angka
  di sini cuma kalau kamu sengaja mau audio kalimat memakai suara yang berbeda
  dari yang dipakai Yomitan.
- **format** — `mp3` (kecil, disarankan) atau `wav`.
- **auto** — `true` berarti kartu yang baru kamu mining langsung diisi sendiri.
  Lebih gampang lewat **Tools → PhiCorvi → Isi audio otomatis saat mining**. Matikan kalau audio kalimatmu sudah datang dari sumber lain —
  mining anime dengan asbplayer misalnya — supaya tidak ada sintesis yang
  percuma dan menghambat.
- **max_chars** — kalimat lebih panjang dari ini dilewati.
- **tag** — tag yang ditempel supaya audio TTS bisa dibedakan dari rekaman asli.
- **targets** — satu entri per note type. Tiap entri boleh punya dua pasangan:
  - `sentence` → `audio` — kalimat contoh dan field audionya
  - `word` → `word_audio` — katanya dan field audionya

  Keduanya boleh diisi daftar: dicoba berurutan, yang pertama ada isinya dipakai.
  Untuk `sentence` itu berguna kalau `{sentence}` Yomitan kamu matikan tapi versi
  furiganya tetap terisi — ruby-nya dibuang, jadi yang dibacakan tetap kalimat biasa.

  Untuk `word`, **taruh field bacaannya lebih dulu** (`ExpressionReading`, atau
  `WordReadingHiragana` di JPMN). Katanya dibacakan dari kana, bukan dari kanji —
  引数 keluar ひきすう, dan tidak ada mesin yang menebak itu dari kanjinya. Jangan
  pakai field berformat `単語[たんご]`: kurungnya dibuang dan yang terbaca kanjinya.

  Pasangan yang tidak disebut ya tidak diisi. Entri lama yang cuma punya
  `sentence`/`audio` tetap jalan seperti dulu.

  > Anki menyimpan config-mu sendiri begitu kamu pernah membukanya, jadi target
  > baru di versi ini **tidak otomatis masuk**. Buka config add-on, klik
  > **Restore Defaults**, lalu ubah lagi yang kamu perlukan. Atau tambahkan
  > `word` dan `word_audio` ke tiap entrimu dengan tangan.

Mengisi banyak kartu sekaligus: **Tools → PhiCorvi → Isi audio yang kosong…**
Untuk kartu tertentu saja: pilih di Browse, lalu menu **Notes → PhiCorvi: isi audio**.

- **auto_limit** — berapa kartu paling banyak diisi sekali sapuan otomatis. Sisanya disusul sapuan berikutnya.
- **check_updates** — cek sekali sehari apakah ada versi baru di GitHub. Matikan kalau tidak mau add-on menghubungi internet sama sekali.
