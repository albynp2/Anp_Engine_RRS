# Horror Content Factory — React + Node.js + Python

Versi UI lokal berbasis **React + Vite**, **Node.js + Express**, dan Python engine. Database utama tetap SQLite di `database/horror.db`.

## Mulai cepat (Windows)

1. Install Node.js LTS dan Python 3.11+.
2. Salin `.env.example` menjadi `.env` di root project dan isi `OPENAI_API_KEY`.
3. Pastikan database utama ada di `database/horror.db` (backup dulu sebelum menyalin database lama).
4. Untuk setup otomatis, jalankan `run_app.bat`.
5. Untuk development manual dari VS Code, ikuti **[README_CUSTOMIZE_AND_RUN.md](README_CUSTOMIZE_AND_RUN.md)**.
6. UI: `http://127.0.0.1:5173`; API health: `http://127.0.0.1:3001/api/health`.

## Fitur Research terbaru

- Checkbox **Hanya tanggal hari ini**; jika tidak dicentang, pilih tanggal mulai dan akhir secara manual.
- Maximum AI candidates bisa diatur dari **1 sampai 50**.
- **Mode hemat token: tanpa OpenAI scoring** menjalankan RSS, filter, deduplikasi, TF-IDF, popularity analysis, dan penyimpanan secara lokal tanpa memanggil OpenAI untuk scoring.
- Kandidat untuk AI dikirim sebagai metadata ringkas, bukan seluruh isi cluster.
- Progress dan log dikirim secara real-time dari Python worker melalui Node API (SSE).
- Error menampilkan popup dengan detail/traceback yang tersedia; proses riset yang berjalan bisa diminta batal dari UI.

## Dashboard dan data

Kartu total artikel, antrean produksi, naskah, render, dan publikasi mengambil hitungan dari SQLite. Research Activity menampilkan artikel baru yang pertama kali disimpan per hari selama 14 hari terakhir, bukan hasil pencarian mentah dan bukan data dummy.

## Struktur ringkas

```text
PROJECT/
├── .env
├── backend/                 # Node.js + Express API
├── frontend/                # React + Vite UI
├── python_engine/worker.py  # Job runner, progress events, DB queries
├── database/horror.db      # Database utama
├── research/                # RSS, TF-IDF, clustering
├── ai/                      # AI scoring
├── production/              # Story generation runner
├── requirements.txt
├── run_app.bat
└── README_CUSTOMIZE_AND_RUN.md
```

Jangan commit `.env`, jangan mengunggah API key, dan jangan menghapus database lama sebelum memverifikasi backup. Lihat panduan manual untuk instalasi, menjalankan `npm run dev`, menyesuaikan UI, dan troubleshooting.

## Legacy SQLite migration

Database utama mengikuti schema dashboard di `database/horror.db`. Untuk merge database lama tanpa menimpa database utama, jalankan dari folder root:

```powershell
python tools/migrate_legacy_database.py "C:\\path\\to\\old\\horror.db"
```

Jika database lama masih di `PROJECT/horror.db`, jalankan `python tools/migrate_legacy_database.py` tanpa argumen. Script membuat backup target, membaca sumber secara read-only, memetakan ulang `story_id` berdasarkan URL, menampilkan progress, dan tidak menghapus sumber. Lihat `README_CUSTOMIZE_AND_RUN.md` untuk detail.
