# Horror Content Factory — Upgrade 2.1

## Included

- Articles Library excludes any article already present in `production_queue` without deleting the article from SQLite.
- Available articles sort by saved AI score, then local popularity score, then parsed publication date (newest first).
- URL tracking parameters are normalized when hiding duplicate URLs in the library.
- SQLite migration adds local ranking metadata and a `content_settings` table without dropping existing records.
- AI Scoring shows saved scoring values from the production queue and links to Research & RSS, where scoring is run.
- Production Queue supports selecting multiple `SELECTED` records and running Write Story as a bulk job. Status becomes `WRITTEN` only after the narrative is saved.
- Story Writer lists saved narratives and allows selecting them for Content Management.
- Content Management stores a video profile in SQLite: Facebook Reels, TikTok, Instagram Reels, YouTube Shorts, and landscape preset; aspect ratio, resolution, FPS, duration, template, headline/lower-third, watermark text/image/opacity/position, voice mode, visual mode, subtitles, and music policy.
- Express exposes `GET/PUT /api/content-settings` and `POST /api/jobs/generate-bulk`.

## Upgrade safely on Windows

1. Stop the backend and frontend terminal windows (`Ctrl+C`).
2. Back up your existing `database\horror.db` and `.env` somewhere outside the project folder.
3. Extract this update ZIP to a temporary folder.
4. Copy the extracted project files over the existing project folder, allowing overwrite for source files. Do **not** replace your `.env` or `database\horror.db` with a file from the ZIP; this update intentionally excludes both.
5. Keep your existing `.venv`, `frontend\node_modules`, and `backend\node_modules`. No new npm packages are required by this update.
6. Run `run_app.bat` as usual. The Python worker will apply additive SQLite migrations on startup.
7. Test in this order: API health → Articles Library → Production Queue bulk Write Story → Story Writer → Content Management save/reload.

## Important current limitation

Content Management now saves and previews the render profile and watermark asset. It does not yet render video. FFmpeg orchestration, actual TTS provider integration, AI image/video provider integration, subtitle timing, render jobs, and final MP4 output are the next implementation stage. Choosing an audio policy is not a guarantee that an asset is copyright-safe; use only media and voices with appropriate rights.
