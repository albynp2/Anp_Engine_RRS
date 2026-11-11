# Horror Content Factory — Manual Development Guide (Windows)

Panduan ini untuk menjalankan aplikasi tanpa `run_app.bat`, langsung dari terminal VS Code.

## Arsitektur

- `frontend/`: React + Vite UI (default `http://127.0.0.1:5173`)
- `backend/`: Node.js + Express API (default `http://127.0.0.1:3001`)
- `python_engine/worker.py`: worker untuk riset, database, scoring, dan pembuatan narasi
- `research/`, `ai/`, `production/`, `database/`: Python engine lama yang dipakai worker
- `database/horror.db`: database SQLite utama. Jangan menyimpan API key di database.
- `.env`: konfigurasi lokal dan API key; jangan commit ke Git.

## Prasyarat

1. Node.js LTS (npm ikut terpasang).
2. Python 3.11 atau lebih baru. Python 3.11 direkomendasikan untuk kompatibilitas dependency.
3. VS Code.

Cek instalasi di terminal PowerShell:

```powershell
node --version
npm --version
py -3.11 --version
```

Jika perintah `py -3.11` tidak tersedia, gunakan `python --version` dan sesuaikan perintah venv di bawah.

## Setup pertama kali

Buka folder root `Horror_Content_Factory_React_Node` di VS Code. Pastikan `.env` berada di root yang sama dengan folder `backend`, `frontend`, dan `database`.

Buat `.env` dari template:

```powershell
Copy-Item .env.example .env
notepad .env
```

Contoh isi `.env`:

```dotenv
OPENAI_API_KEY=masukkan_api_key_di_sini
API_PORT=3001
# Opsional; launcher manual akan memakai .venv jika variabel ini disetel:
# PYTHON_EXECUTABLE=C:\path\ke\project\.venv\Scripts\python.exe
```

Jangan pernah membagikan `.env` atau memasukkan API key ke GitHub.

Buat Python virtual environment dan pasang dependency:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Pasang dependency Node secara terpisah:

```powershell
cd backend
npm install
cd ..\frontend
npm install
cd ..
```

Pastikan database utama tersedia di `database\horror.db`. Backup database sebelum menyalin/mengganti file database.

## Menjalankan manual di VS Code

Buka **3 terminal terpisah** di VS Code, semuanya dari folder root project.

### Terminal 1 — Python environment check (opsional)

```powershell
.\.venv\Scripts\python.exe -c "import feedparser, sklearn, openai; print('Python dependencies OK')"
```

### Terminal 2 — Backend Node.js

```powershell
cd backend
$env:PYTHON_EXECUTABLE = (Resolve-Path ..\.venv\Scripts\python.exe).Path
npm run dev
```

Backend API akan tersedia di `http://127.0.0.1:3001`. Health check: `http://127.0.0.1:3001/api/health`.

### Terminal 3 — Frontend React + Vite

```powershell
cd frontend
npm run dev
```

Buka `http://127.0.0.1:5173` di browser. Jangan tutup kedua terminal server saat aplikasi digunakan.

## Build untuk memeriksa UI

Dari terminal root:

```powershell
cd frontend
npm run build
```

## Fitur Research UI

- **Hanya tanggal hari ini** aktif secara default. Ketika dicentang, tanggal start/end mengikuti tanggal lokal komputer.
- Jika checkbox dimatikan, pilih tanggal mulai dan tanggal akhir sendiri; kedua tanggal bersifat inklusif.
- **Maximum AI candidates** dapat diatur 1–50.
- **Mode hemat token: tanpa OpenAI scoring** tetap menjalankan RSS, filter, deduplikasi, clustering, popularity scoring lokal, dan penyimpanan artikel. Mode ini melewati panggilan OpenAI untuk scoring, sehingga biaya token scoring = nol. Pembuatan narasi tetap menggunakan OpenAI bila fitur writer dijalankan.
- Untuk hemat token tetapi tetap memakai AI, turunkan kandidat ke 5–15. Payload scoring hanya memuat metadata ringkas, tidak mengirim seluruh artikel cluster.

## Error popup, log, dan cancel

Saat proses gagal, UI menampilkan popup error beserta traceback yang tersedia dan tombol Copy error. Panel Process Log menampilkan event proses. Tombol **Batalkan proses** meminta backend menghentikan worker aktif; pembatalan tidak selalu dapat menghentikan request eksternal yang sudah diterima oleh penyedia API.

## Cara customize UI

- Layout, halaman, tabel, interaksi, state: `frontend/src/App.jsx`
- Warna, spacing, responsive styles, modal: `frontend/src/styles.css`
- Entry point React: `frontend/src/main.jsx`
- API routes, job lifecycle, SSE, cancel endpoint: `backend/server.js`
- Pipeline riset, query SQLite, event progress: `python_engine/worker.py`
- Query Google News RSS: `research/researcher.py`
- Popularity / TF-IDF / clustering: `research/popularity.py`
- Prompt AI scoring: `ai/scorer.py`
- Prompt penulisan narasi: `research/writer.py`
- Koneksi dan query database: `database/database.py`

## Dashboard dan database

Kartu Dashboard menggunakan query SQLite:

- Total articles: jumlah baris pada `stories`.
- In production queue: jumlah baris pada `production_queue` (total, bukan hanya item yang tampil di tabel).
- Scripts written: jumlah baris pada `generated_stories`.
- Rendered / Published: jumlah status pada `production_queue`.
- Research activity: artikel yang pertama kali tersimpan per tanggal berdasarkan `stories.created_at` untuk 14 hari terakhir.

Karena Research Activity menunjukkan **artikel yang baru disimpan per hari**, artikel duplikat yang ditemukan kembali tidak menambah grafik. Ini disengaja agar grafik tidak menggelembungkan angka.

## Troubleshooting

- `python` tidak ditemukan: pastikan `PYTHON_EXECUTABLE` di Terminal 2 menunjuk ke `.venv\Scripts\python.exe`.
- `API disconnected`: pastikan backend berjalan dan cek `/api/health`.
- `Database Connected` tetapi artikel 0: cek path `databasePath` pada `/api/health` dan pastikan itu database yang benar.
- Port terpakai: tutup proses Node lama atau ubah `API_PORT` di `.env` dan perbarui alamat API di `frontend/src/App.jsx`.
- Error Python: gunakan popup Copy error atau panel Process Log untuk traceback.

## Keamanan dan batasan

Aplikasi ditujukan untuk penggunaan lokal. API binding saat ini menggunakan loopback (`127.0.0.1`). Jangan expose backend ke jaringan publik tanpa autentikasi dan kontrol keamanan. Jangan menganggap metadata RSS sebagai verifikasi fakta; review sumber sebelum membuat narasi.

## Migrasi database SQLite lama ke schema dashboard terbaru

Schema `database/horror.db` adalah schema kanonis yang dipakai dashboard. Aplikasi akan menambahkan kolom kompatibilitas yang hilang (misalnya `production_queue.status` dan metadata naskah) tanpa menghapus record yang sudah ada.

### Migrasi database lama (merge, bukan overwrite)

1. Stop backend dan frontend terlebih dahulu.
2. Buat backup manual database lama dan target.
3. Buka terminal PowerShell dari root project.
4. Jalankan salah satu perintah berikut:

```powershell
# Jika database lama berada di PROJECT/horror.db:
python tools/migrate_legacy_database.py

# Jika database lama ada di lokasi lain:
python tools/migrate_legacy_database.py "C:\\DATA_Alby\\Data_pirbadi_alby\\PROJECT\\horror.db"

# Alias lama juga tersedia:
python tools/migrate_db.py "C:\\path\\to\\old\\horror.db"
```

Script akan:

- Membaca database sumber dalam mode read-only; file sumber tidak diubah/dihapus.
- Memastikan schema target sesuai versi dashboard terbaru.
- Membuat backup otomatis `database/horror_backup_before_legacy_migration_YYYYMMDD_HHMMSS.db` jika target sudah ada.
- Merge `stories`, `production_queue`, dan `generated_stories` (serta nama tabel legacy umum `articles`, `news`, `queue`, `scripts`, dan sejenisnya).
- Mencocokkan story berdasarkan URL dan memetakan ulang `story_id`, supaya hubungan antrean dan naskah tidak bergantung pada ID lama.
- Melewati record yang sudah ada dan menampilkan progress bar serta jumlah inserted/skipped/invalid.

**Catatan:** migrasi tidak menghapus tabel tambahan milik database lama dan tidak menghapus file sumber. Jika database lama menggunakan nama tabel atau kolom khusus yang tidak dikenali, jangan hapus sumber; kirim output migrasi untuk pemetaan tambahan.

Setelah migrasi, cek `http://127.0.0.1:3001/api/health` dan Dashboard. Pastikan `databasePath` menunjuk ke folder project yang sedang dijalankan dan angka total artikel sesuai.
