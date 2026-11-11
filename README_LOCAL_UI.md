# Horror Content Factory — Local UI

## Menjalankan aplikasi

1. Pastikan file `.env` berada di folder `PROJECT` dan berisi `OPENAI_API_KEY=...`.
2. Jangan membagikan `.env` atau memasukkan API key ke Git.
3. Di Windows, klik dua kali `run_app.bat`.
4. Tunggu instalasi pertama selesai. Browser akan membuka dashboard Streamlit.
5. Untuk penggunaan berikutnya, klik `run_app.bat` lagi.

Aplikasi berjalan lokal di komputer sendiri. Jendela terminal yang terbuka adalah proses server lokal; penggunaan sehari-hari dilakukan dari browser, bukan mengetik command Python.

## Fitur UI

- **Overview:** ringkasan artikel, antrean, naskah, dan status pipeline.
- **Research:** menjalankan pipeline riset Google News, filter, ranking lokal, AI scoring, dan queue.
- **Story Writer:** memilih satu topik dan menghasilkan satu naskah.
- **Generated Scripts:** membaca naskah yang sudah disimpan.
- **System Check:** memeriksa lokasi database, tabel, jumlah data, dan konfigurasi API tanpa menampilkan nilai API key.

## Database

Database utama berada di `database/horror.db`. Modul aplikasi harus menggunakan `database.database.get_connection()` atau `DB_PATH`; jangan membuat koneksi dengan `sqlite3.connect("horror.db")` karena itu bisa membuat database kedua di working directory.

## Jika aplikasi gagal dibuka

- Pastikan Python 3.11 tersedia (`py -3.11`).
- Pastikan `.env` berada di root folder `PROJECT`.
- Lihat pesan error di jendela yang muncul setelah `run_app.bat` dijalankan.
- Pada instalasi pertama, komputer perlu internet untuk memasang dependency dan untuk fitur Google News/OpenAI.

## Batasan versi ini

UI mencakup riset, antrean, penulisan naskah, dan pemantauan. Rendering video, text-to-speech, dan publikasi otomatis belum dibuat.
