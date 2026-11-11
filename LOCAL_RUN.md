# Engine RRS — Local Windows Package

Package ini adalah full source Engine RRS untuk dijalankan secara lokal.

## Struktur
- `frontend/` — React + Vite UI
- `backend/` — Node.js + Express API
- `python_engine/` — worker Python
- `research/` — RSS research, popularity, writer
- `ai/` — OpenAI scoring
- `database/` — SQLite database layer
- `dashboard/` — dashboard utilities
- `tools/` — database/status utilities

## Prasyarat
- Windows 10/11
- Python 3.11+ (disarankan 3.11)
- Node.js 18+
- npm
- Git opsional

## Setup
1. Copy `.env.example` menjadi `.env` di root project.
2. Isi API key yang dibutuhkan di `.env`. Jangan commit `.env`.
3. Buat virtual environment:
   `python -m venv .venv`
4. Aktifkan:
   `\.venv\Scripts\activate`
5. Install Python:
   `pip install -r requirements.txt`
6. Install backend:
   `cd backend`
   `npm install`
7. Install frontend:
   `cd ..\frontend`
   `npm install`

## Menjalankan
Gunakan `run_app.bat` jika tersedia, atau jalankan komponen secara terpisah:

### Backend
`cd backend`
`npm start`

### Frontend
`cd frontend`
`npm run dev`

### Python worker
Ikuti konfigurasi worker yang ada di `python_engine/worker.py` dan dokumentasi project.

## Catatan keamanan
- Jangan masukkan API key ke source code.
- Jangan commit `.env`.
- Jangan memasukkan `node_modules`, `.venv`, cache, atau database runtime ke GitHub kecuali memang diperlukan.

## Status package
Package ini menggabungkan source full `HCF_Upgrade_2_1_Source.zip` dengan patch RSS terbaru yang tersedia di `HCF_RSS_Fix.zip` untuk:
- `frontend/src/App.jsx`
- `research/researcher.py`
- `python_engine/worker.py`
