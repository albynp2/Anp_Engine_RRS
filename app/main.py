"""Engine RRS - API + penyaji frontend (satu proses, satu container)."""
import io
import json
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

from . import (audio, characters, config, db, fonts, images, llm, music, renderer, research, tts, writer)
from .jobs import BusyError, manager, sse_stream

config.ensure_dirs()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    music.ensure_builtin()
    yield


app = FastAPI(title="Engine RRS", lifespan=lifespan)


# ------------------------------------------------------------------ error -> {"error": ...}
@app.exception_handler(HTTPException)
async def http_err(_: Request, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_err(_: Request, exc: RequestValidationError):
    return JSONResponse({"error": "Input tidak valid", "details": str(exc.errors())[:500]}, status_code=422)


@app.exception_handler(ValueError)
async def value_err(_: Request, exc: ValueError):
    return JSONResponse({"error": str(exc)}, status_code=400)


@app.exception_handler(Exception)
async def any_err(_: Request, exc: Exception):
    return JSONResponse({"error": str(exc) or exc.__class__.__name__}, status_code=500)


# ------------------------------------------------------------------ info
@app.get("/api/health")
def health():
    a = manager.active()
    return {"ok": True, "now": config.now_local().isoformat(), "tz": str(config.TZ),
            "openai": llm.ai_available(), "model": config.OPENAI_MODEL, "ffmpeg": renderer.ffmpeg_ok(),
            "edgeTts": tts.available(), "activeJob": a.public() if a else None}


@app.get("/api/config")
def app_config():
    return {"platforms": [{"id": k, "label": v["label"]} for k, v in renderer.PLATFORMS.items()],
            "voices": tts.VOICES, "emotions": writer.EMOTIONS, "imageProviders": images.PROVIDERS,
            "horrorExclude": research.HORROR_DEFAULT_EXCLUDE,
            "horrorQueries": research.HORROR_PRESET_QUERIES,
            "fonts": fonts.list_fonts(), "promptTips": characters.PROMPT_TIPS, "today": config.today_local().isoformat(),
            "defaults": renderer.DEFAULT_OPTS}


@app.get("/api/dashboard")
def dashboard():
    return db.dashboard()


# ------------------------------------------------------------------ artikel / queue
@app.get("/api/articles")
def articles(page: int = 1, limit: int = 25, search: str = "", stage: str = "NEW",
             dateFrom: str = "", dateTo: str = ""):
    return db.list_articles(page, limit, search, stage, dateFrom, dateTo)


@app.get("/api/stories/{story_id}")
def story(story_id: int):
    s = db.get_story(story_id)
    if not s:
        raise HTTPException(404, "Berita tidak ditemukan")
    s["content_preview"] = (s.get("content") or "")[:1500]
    s.pop("content", None)
    s.pop("cluster_json", None)
    return s


@app.put("/api/stories/{story_id}/content")
def set_content(story_id: int, payload: dict = Body(...)):
    text = (payload.get("content") or "").strip()
    if len(text) < 200:
        raise HTTPException(400, "Isi artikel terlalu pendek (minimal 200 huruf).")
    if not db.get_story(story_id):
        raise HTTPException(404, "Berita tidak ditemukan")
    db.execute("UPDATE stories SET content=?, content_status='MANUAL' WHERE id=?", (text[:12000], story_id))
    return {"ok": True, "length": len(text)}


@app.post("/api/queue")
def queue_add(payload: dict = Body(...)):
    ids = [int(x) for x in payload.get("ids", [])]
    return {"inserted": db.queue_add(ids)}


@app.get("/api/queue")
def queue_list():
    return {"items": db.queue_list()}


@app.delete("/api/queue/{story_id}")
def queue_remove(story_id: int):
    if not db.queue_remove(story_id):
        raise HTTPException(409, "Hanya berita yang belum dibuat naskahnya yang bisa dikeluarkan dari antrean.")
    return {"ok": True}


# ------------------------------------------------------------------ jobs
JOB_FUNCS = {"research": research.run_research, "write": writer.run_write, "render": renderer.run_render}


@app.post("/api/jobs/{type_}")
def start_job(type_: str, payload: dict = Body(default={})):
    fn = JOB_FUNCS.get(type_)
    if not fn:
        raise HTTPException(404, "Jenis proses tidak dikenal")
    if type_ == "research":  # validasi cepat sebelum thread jalan
        research.pick_queries(payload.get("mode", "custom"), payload.get("query", ""))
    try:
        job = manager.start(type_, fn, payload)
    except BusyError as e:
        raise HTTPException(409, str(e))
    return {"id": job.id, "type": type_, "status": job.status}


@app.get("/api/jobs/active")
def job_active():
    a = manager.active()
    return a.public() if a else {"id": None}


@app.get("/api/jobs/{job_id}")
def job_get(job_id: str):
    j = manager.get(job_id)
    if not j:
        raise HTTPException(404, "Job tidak ditemukan")
    return j.public()


@app.get("/api/jobs/{job_id}/events")
def job_events(job_id: str):
    j = manager.get(job_id)
    if not j:
        raise HTTPException(404, "Job tidak ditemukan")
    return StreamingResponse(sse_stream(j), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/jobs/{job_id}/cancel")
def job_cancel(job_id: str):
    j = manager.get(job_id)
    if not j:
        raise HTTPException(404, "Job tidak ditemukan")
    j.cancel_flag = True
    return {"ok": True}


# ------------------------------------------------------------------ naskah
@app.get("/api/scripts")
def scripts():
    return {"items": db.list_scripts()}


@app.get("/api/scripts/{story_id}")
def script_get(story_id: int):
    s = db.get_script(story_id)
    if not s:
        raise HTTPException(404, "Naskah tidak ditemukan")
    s["tts_text"] = writer.tts_export(s)
    s["estimated_seconds"] = writer.estimate_seconds(s["segments"])
    up = next(iter(sorted(config.UPLOAD_DIR.glob(f"story_{story_id}_narration.*"))), None)
    s["uploaded_audio"] = up.name if up else None
    return s


@app.put("/api/scripts/{story_id}")
def script_update(story_id: int, payload: dict = Body(...)):
    cur = db.get_script(story_id)
    if not cur:
        raise HTTPException(404, "Naskah tidak ditemukan")
    segs = writer.normalize_segments(payload.get("segments"))
    if len(segs) < 2:
        raise HTTPException(400, "Minimal 2 segmen.")
    data = {**cur, "segments": segs, **writer.derive_fields(segs)}
    for k in ("title", "caption", "hashtags"):
        if k in payload:
            data[k] = str(payload[k])
    s = db.get_story(story_id)
    data["fact_warnings"] = writer.find_unsupported(segs, s.get("content") or "") if s.get("content") else []
    db.save_script(story_id, data)
    return {"ok": True, "fact_warnings": data["fact_warnings"]}


@app.delete("/api/scripts/{story_id}")
def script_delete(story_id: int):
    db.delete_script(story_id)
    return {"ok": True}


@app.post("/api/stories/{story_id}/audio")
def upload_audio(story_id: int, file: UploadFile = File(...)):
    ext = Path(file.filename or "a.mp3").suffix.lower()
    if ext not in (".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".webm"):
        raise HTTPException(400, "Format audio harus mp3/wav/m4a/ogg/flac")
    data = file.file.read()
    if len(data) > 80 * 1024 * 1024:
        raise HTTPException(400, "File audio terlalu besar (maks 80 MB)")
    for old in config.UPLOAD_DIR.glob(f"story_{story_id}_narration.*"):
        old.unlink()
    dest = config.UPLOAD_DIR / f"story_{story_id}_narration{ext}"
    dest.write_bytes(data)
    try:
        dur = len(audio.decode(dest)) / audio.SR
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, str(e))
    return {"ok": True, "seconds": round(dur, 1), "name": dest.name}


@app.delete("/api/stories/{story_id}/audio")
def delete_audio(story_id: int):
    for old in config.UPLOAD_DIR.glob(f"story_{story_id}_narration.*"):
        old.unlink()
    return {"ok": True}


# ------------------------------------------------------------------ karakter
@app.get("/api/characters")
def characters_list():
    return {"items": characters.list_all()}


@app.post("/api/characters")
def characters_create(payload: dict = Body(...)):
    cid = characters.create(payload)
    return characters.get(cid)


@app.put("/api/characters/{cid}")
def characters_update(cid: int, payload: dict = Body(...)):
    if not characters.get(cid):
        raise HTTPException(404, "Karakter tidak ditemukan")
    characters.update(cid, payload)
    return characters.get(cid)


@app.delete("/api/characters/{cid}")
def characters_delete(cid: int):
    characters.delete(cid)
    return {"ok": True}


@app.post("/api/characters/{cid}/image")
def characters_image(cid: int, emotion: str = Form(...), mouth: str = Form("closed"), file: UploadFile = File(...)):
    if not characters.get(cid):
        raise HTTPException(404, "Karakter tidak ditemukan")
    characters.save_image(cid, emotion, mouth, file.file.read())
    return characters.get(cid)


@app.delete("/api/characters/{cid}/image")
def characters_image_delete(cid: int, emotion: str, mouth: str = "closed"):
    characters.delete_image(cid, emotion, mouth)
    return characters.get(cid)


# ------------------------------------------------------------------ musik
@app.get("/api/music")
def music_list():
    return {"items": music.list_all()}


@app.post("/api/music")
def music_upload(name: str = Form(""), source: str = Form(""), license_note: str = Form(""),
                 confirm: str = Form(""), file: UploadFile = File(...)):
    if confirm.lower() not in ("1", "true", "yes", "on"):
        raise HTTPException(400, "Centang konfirmasi bahwa musik ini bebas hak cipta / boleh dipakai komersial.")
    mid = music.add_upload(name, file.filename or "musik.mp3", file.file.read(), source, license_note)
    return {"id": mid}


@app.delete("/api/music/{mid}")
def music_delete(mid: int):
    if not music.delete(mid):
        raise HTTPException(409, "Musik bawaan tidak bisa dihapus.")
    return {"ok": True}


# ------------------------------------------------------------------ render / video
@app.post("/api/uploads/watermark")
def upload_watermark(file: UploadFile = File(...)):
    try:
        img = Image.open(io.BytesIO(file.file.read())).convert("RGBA")
    except Exception:
        raise HTTPException(400, "File bukan gambar yang valid")
    dest = config.UPLOAD_DIR / "watermark.png"
    img.save(dest, "PNG")
    return {"path": str(dest)}


@app.get("/api/fonts")
def fonts_list():
    return {"items": fonts.list_fonts()}


@app.post("/api/fonts")
def fonts_upload(file: UploadFile = File(...)):
    fid = fonts.add_font(file.filename or "font.ttf", file.file.read())
    return {"id": fid, "items": fonts.list_fonts()}


@app.post("/api/render/preview")
def render_preview(payload: dict = Body(default={})):
    return Response(content=renderer.render_preview(payload), media_type="image/png")


@app.get("/api/videos")
def videos(storyId: int = 0):
    return {"items": db.list_videos(storyId or None)}


@app.patch("/api/videos/{vid}")
def video_patch(vid: int, payload: dict = Body(...)):
    if "published" in payload and not db.set_video_published(vid, bool(payload["published"])):
        raise HTTPException(409, "Hanya video yang sudah selesai yang bisa ditandai published.")
    return {"ok": True}


@app.delete("/api/videos/{vid}")
def video_delete(vid: int):
    name = db.delete_video(vid)
    if name:
        (config.OUTPUT_DIR / name).unlink(missing_ok=True)
    return {"ok": True}


@app.get("/api/content-settings")
def settings_get():
    return db.get_content_settings()


@app.put("/api/content-settings")
def settings_put(payload: dict = Body(...)):
    db.put_content_settings(payload)
    return db.get_content_settings()


# ------------------------------------------------------------------ file statis + frontend
app.mount("/media/outputs", StaticFiles(directory=str(config.OUTPUT_DIR)), name="outputs")
app.mount("/media/characters", StaticFiles(directory=str(config.CHAR_DIR)), name="characters")
app.mount("/media/music", StaticFiles(directory=str(config.MUSIC_DIR)), name="music")

DIST = config.FRONTEND_DIST
if (DIST / "index.html").exists():
    if (DIST / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(DIST / "assets")), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        if full_path.startswith(("api/", "media/")):
            raise HTTPException(404, "Tidak ditemukan")
        f = (DIST / full_path).resolve()
        if full_path and f.is_file() and str(f).startswith(str(DIST.resolve())):
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
