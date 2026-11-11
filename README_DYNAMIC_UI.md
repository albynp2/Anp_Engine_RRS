# Horror Content Factory — Dynamic Local UI

## Start
1. Keep your existing `.env` in the project root (same folder as `app.py`).
2. Keep your own `database/horror.db` in `database/`.
3. Install dependencies if needed: `python -m pip install -r requirements.txt`.
4. Double-click `run_app.bat`.

## UI pages
- **Overview**: counts and queue status.
- **Research Settings**: edit Google News RSS queries, excluded keywords, inclusive start/end dates, and candidate limit. Clicking the button starts the pipeline.
- **Article Library**: search saved articles, filter status, inspect article metadata, and manually add selected articles to the production queue.
- **Production Queue**: see queue items and update statuses.
- **Story Writer**: choose a queued article and generate one narrative at a time.
- **Generated Scripts**: browse generated narratives.
- **System Check**: verify database path, table availability, SQLite integrity, Python environment, and API key presence.

## Database and secrets
- Main database: `database/horror.db`.
- `.env` belongs in the project root and should contain `OPENAI_API_KEY=...`.
- Do not commit or share `.env` or your API key.
- This ZIP intentionally does not contain `.env`, database files, or Python cache folders.

## Important notes
- RSS and AI calls require internet access.
- Manual article selection queues an article with neutral scores (0) because it was selected by the user rather than AI-scored.
- Rendering, TTS, and automated publishing are not implemented in this build. The UI can display/update those statuses, but it does not actually render or publish videos.
- During research, the UI displays stage progress and keeps the captured process log available for inspection.
