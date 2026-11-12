# Engine RRS v3 — Berita → Naskah → Video (lokal, Docker)

Satu container: web UI + API + pembuat video. Data semua di folder `data/` (database, gambar, avatar, musik, video).

## Jalankan

1. Install **Docker Desktop**.
2. Salin `.env.example` jadi `.env`, isi `OPENAI_API_KEY`.
3. Di folder ini:
   ```
   docker compose up --build
   ```
4. Buka **http://localhost:8000**

Berikutnya cukup `docker compose up`. Berhenti dengan `Ctrl+C` atau `docker compose down`. Data tetap aman di `data/`.

### Pindahin data dari engine lama
Salin `database/horror.db` lama ke `data/horror.db` **sebelum** pertama kali jalan. Skema otomatis di-upgrade, artikel & naskah lama tetap ada.

## Alur pemakaian

| Menu | Fungsi |
|---|---|
| **Dashboard** | Total artikel, naskah, video jadi, published, yang masih proses; aktivitas 14 hari (WIB); artikel terbaru. Semua dihitung dari database yang sama dengan menu lain. |
| **Research RRS** | Mode *Horor/Pembunuhan/Kriminal* (kata kunci otomatis) atau *Input sendiri*. Tanggal kosong atau "Hari ini saja" = hari ini (WIB); kalau tidak, pakai tanggal pilihan. Exclude boleh kosong. "Maksimum kandidat AI" = berapa berita yang dinilai AI (satu request ringkas). |
| **Artikel Gallery** | Berita terurut skor tertinggi. Centang → masukkan ke Production Queue. |
| **Production Queue** | Centang berita → AI menulis naskah dari **isi artikel asli**. Kalau isi tidak bisa diambil, tempel manual (tombol *Isi manual*). |
| **Story Writer** | Cek & edit naskah per segmen (teks, emosi, prompt gambar). Ada cek fakta otomatis: angka/nama yang tidak ada di sumber diberi peringatan. Ada teks siap tempel untuk Google AI Studio. |
| **Content Management** | Pilih naskah → platform (FB Reels, YT Shorts, TikTok, IG Reels) → karakter → suara → musik → Generate video. Pengaturan tersimpan sebagai template. |
| **Settings** | Karakter avatar, library musik, status sistem. |

### Cara skor dihitung
`skor akhir = 55% popularitas + 45% penilaian AI`. Popularitas = berapa banyak artikel & **media berbeda** yang meliput kejadian yang sama. (Jumlah pengunjung per berita tidak tersedia dari sumber gratis, jadi ini indikator terbaik yang jujur.) AI hanya menerima judul ringkas kandidat teratas, bukan seluruh hasil pencarian, supaya hemat token.

### Setup karakter (Settings → Karakter)
1. Buat avatar dari foto di AI gambar favorit (prompt siap pakai ada di Settings), **upload** sebagai *Netral · tutup*.
2. Klik di gambar tepat di tengah mulut. Mulut akan bergerak mengikuti suara.
3. Opsional tapi bikin jauh lebih hidup: upload versi *sedih / marah / kaget* (alis berubah) dan *mulut terbuka*. Per segmen, app memilih gambar sesuai emosi naskah.
4. Karakter lalu muncul di dropdown Content Management.

### Mengatur tampilan video (Content Management)
Semua bisa digeser dan langsung terlihat di **Preview** (otomatis ikut berubah setelah klik *Buat preview*):
- **Avatar:** ukuran (tinggi), posisi horizontal (kiri/tengah/kanan), posisi vertikal. *Otomatis* = di atas area yang tertutup tombol platform.
- **Subtitle:** jenis tulisan, ukuran, warna, outline, kotak latar + transparansi, HURUF BESAR, posisi (x/y), lebar area, maks. baris.
- **Judul di atas video:** isi (judul naskah / teks sendiri / tanpa), dan semua pengaturan gaya & posisi yang sama dengan subtitle.
- **Font:** 10 pilihan bawaan; bisa **upload font sendiri** (.ttf / .otf) di bagian subtitle atau judul.
- Semua pengaturan tersimpan otomatis sebagai template.

### Gerak avatar
Mulut dianalisis dari audio ±4x lebih rapat dari frame rate, dengan buka cepat & tutup lebih pelan seperti bibir asli. Bentuk mulut ikut "warna" suara (vokal i/e lebar, o/u bulat). Kepala juga bernapas, bergoyang halus, dan mengangguk mengikuti energi suara, plus gaya khusus per emosi. Kalau lu upload gambar *mulut terbuka*, transisi tutup↔buka di-blend halus. Ini bukan lip-sync per huruf, tapi cukup natural untuk video pendek.

### Suara
- **TTS otomatis (edge-tts)**: gratis, tempo & nada berubah per emosi segmen. Butuh internet.
- **Upload audio**: buat di Google AI Studio → Generate Speech dengan teks dari Story Writer, upload file di Content Management. Batas antar segmen dicari otomatis dari jeda suara (beri jeda ~1 detik antar paragraf).

### Musik
4 musik bawaan disintesis app sendiri (bebas hak cipta). Bisa upload musik lain; wajib centang konfirmasi lisensi.

## Yang perlu lu tahu (jujur)
- **Sudah dites otomatis**: database & dashboard, filter tanggal WIB, popularitas, ekstraksi isi artikel, cek fakta, alur riset→queue→naskah (AI & internet dipalsukan), render video lengkap (avatar, emosi, subtitle, musik, FFmpeg), pengaturan posisi/ukuran/gaya tulisan, dan kehalusan gerak mulut.
- **Belum bisa dites di tempat gua**: panggilan nyata ke OpenAI, Google News, edge-tts, Pollinations, decode link Google News format baru, server FastAPI sungguhan, dan `docker build`. Kalau ada yang error di laptop lu, lihat panel Log / pesan error di UI — kirim ke gua.
- Link Google News kadang tidak bisa di-decode → artikel ditandai "Isi gagal diambil"; pakai *Isi manual*. App **tidak akan** menulis naskah dari judul saja.
- Gerak mulut berbasis analisis suara (bukan lip-sync fonem). Ekspresi detail (alis, dll) datang dari gambar emosi yang lu upload.
- "Published" = penanda manual. App belum upload otomatis ke platform.
- Gambar AI gratis (Pollinations) kualitas & ketersediaannya di luar kendali kita; kalau gagal otomatis pakai latar gradient.
- Render HD ±1–2 menit per video di laptop biasa. Pakai kualitas *Draft* untuk tes cepat.

## Struktur
```
app/            backend (FastAPI): research, scorer, article_fetch, writer, tts, images, renderer, ...
frontend/src/   React UI (build otomatis di Docker)
tests/          tes offline: docker compose exec rrs python -m tests.test_research
data/           database & media (volume)
```

## Troubleshooting
- *"OPENAI_API_KEY belum diisi"* → isi `.env`, lalu `docker compose up --build` ulang.
- *Port 8000 dipakai* → ganti `127.0.0.1:8000:8000` di `docker-compose.yml`.
- *Render gagal di 'Suara narasi'* → edge-tts butuh internet; atau pakai mode Upload audio.
- Reset total: hentikan container, hapus isi `data/` (database ikut hilang).
