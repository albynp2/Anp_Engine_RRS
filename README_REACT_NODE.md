# Horror Content Factory — React + Node.js + Python

## Arsitektur

- `frontend/`: React + Vite UI di `http://127.0.0.1:5173`
- `backend/`: Express API di `http://127.0.0.1:3001`
- `python_engine/worker.py`: bridge JSON-line yang memanggil modul Python lama
- `research/`, `ai/`, `production/`, `database/`: Python engine yang dipertahankan
- Database tunggal: `database/horror.db`
- API key: `.env` di root project. Jangan commit/share file ini.

## Instalasi Windows

1. Install Node.js LTS (termasuk npm) dan Python 3.11+.
2. Extract project ke folder lokal, misalnya `C:\DATA_Alby\Data_pirbadi_alby\PROJECT`.
3. Copy `.env.example` menjadi `.env`, lalu isi `OPENAI_API_KEY=...`.
4. Jika database lama sudah ada, pastikan file target ada di `database/horror.db`. Backup sebelum mengubah database.
5. Double-click `run_app.bat`. Launcher membuat `.venv`, memasang dependency Python dan Node, lalu membuka UI.
6. UI: `http://127.0.0.1:5173`; API health: `http://127.0.0.1:3001/api/health`.

Pertama kali jalan membutuhkan koneksi internet untuk instalasi paket. Setelah paket terpasang, UI berjalan lokal; riset RSS dan OpenAI tetap membutuhkan internet.

## Jika launcher gagal

- Pastikan `node --version`, `npm --version`, dan `py -3.11 --version` berjalan di terminal baru.
- Cek jendela `HCF Node API` dan `HCF React UI` untuk error pertama.
- Kalau `python` tidak terdeteksi, launcher mengatur `PYTHON_EXECUTABLE` ke `.venv` project.
- Pastikan port 3001 dan 5173 belum dipakai aplikasi lain.
- Pastikan API key valid dan memiliki akses API.

## Progress dan log

Endpoint riset/generate membuat satu job aktif. Progress, stage, log, dan hasil dikirim via Server-Sent Events (SSE) ke React. Refresh halaman tidak menghentikan job; endpoint `/api/jobs/:id` dapat membaca snapshot job selama server tetap berjalan.

## API

- `GET /api/health`
- `GET /api/dashboard`
- `GET /api/articles?page=1&limit=25&search=&status=ALL`
- `GET /api/queue?status=ALL`
- `GET /api/scripts`
- `POST /api/jobs/research`
- `POST /api/jobs/generate`
- `GET /api/jobs/:id/events` (SSE)
- `GET /api/jobs/:id`
- `POST /api/queue/select` with `{ "ids": [1,2] }`
- `PATCH /api/queue/:queueId/status` with `{ "status": "SELECTED" }`

## Status and limitations

`SELECTED`, `WRITTEN`, `RENDERED`, `PUBLISHED`, and `FAILED` can be tracked in the queue. Rendering, TTS, and platform publishing are not implemented here; changing a status in UI only updates the database, it does not render/upload a video. Article Library selection adds an existing article to the queue; Research runs local filtering/clustering and OpenAI scoring.

## Database safety

The bridge uses `database/database.py` which resolves `database/horror.db` from its own file location. The root `horror.db`, if present, is not used by this UI. Do not delete the old root DB until you have confirmed its migration and backed it up.


## Dashboard activity chart
The Research Activity chart reads real daily story insertion counts from `stories.created_at` for the last 14 days. It no longer uses hard-coded illustrative values. Existing articles imported earlier will contribute to the current day only if their `created_at` timestamps fall within this 14-day window. The Total Articles card shows the complete count in the configured SQLite database.
