"""Tes render end-to-end offline. Jalankan: python -m tests.test_render [folder_output]"""
import io
import json
import os
import subprocess
import sys
import tempfile

os.environ["DATA_DIR"] = tempfile.mkdtemp()

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from app import audio, characters, config, db, music, renderer, tts  # noqa: E402
from app.jobs import Job  # noqa: E402


def avatar(emotion="neutral", open_mouth=False) -> bytes:
    im = Image.new("RGBA", (600, 900), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([120, 560, 480, 900], 60, fill=(40, 60, 110, 255))      # badan
    d.ellipse([160, 120, 440, 470], fill=(236, 190, 150, 255))                  # kepala
    d.ellipse([160, 80, 440, 260], fill=(30, 22, 20, 255))                      # rambut
    d.ellipse([220, 270, 270, 310], fill=(255, 255, 255, 255))
    d.ellipse([330, 270, 380, 310], fill=(255, 255, 255, 255))
    d.ellipse([238, 280, 258, 300], fill=(20, 20, 20, 255))
    d.ellipse([348, 280, 368, 300], fill=(20, 20, 20, 255))
    by = {"neutral": (250, 250), "sad": (230, 250), "angry": (262, 240), "surprised": (225, 225)}[emotion]
    d.line([215, by[0], 275, by[1]], fill=(30, 22, 20, 255), width=8)           # alis kiri
    d.line([325, by[1], 385, by[0]], fill=(30, 22, 20, 255), width=8)           # alis kanan
    if open_mouth:
        d.ellipse([260, 380, 340, 430], fill=(60, 10, 20, 255))
    else:
        d.line([265, 400, 335, 400], fill=(120, 40, 50, 255), width=6)
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


def fake_speech(seconds: float, sr=audio.SR) -> np.ndarray:
    t = np.arange(int(seconds * sr)) / sr
    syl = np.clip(np.sin(2 * np.pi * 3.6 * t), 0, 1) ** 0.7        # suku kata ~3.6 Hz
    word = (np.sin(2 * np.pi * 0.7 * t) > -0.6).astype(np.float32)  # jeda antar kata
    return (0.5 * syl * word * np.sin(2 * np.pi * 180 * t)).astype(np.float32)


def setup():
    db.init_db()
    music.ensure_builtin()
    sid, _ = db.upsert_candidate(dict(title="Penampakan misterius di Jembatan Cipularang bikin warga geger",
                                      url="http://x/1", source="Kompas", published_date="2026-11-12"))
    segs = [
        {"text": "Warga Bogor geger setelah sosok putih terlihat di dekat jembatan pada Selasa malam.",
         "emotion": "surprised", "image_prompt": "foggy bridge at night"},
        {"text": "Menurut saksi bernama Rudi, kejadian itu berlangsung sekitar pukul sepuluh malam dan sempat direkam.",
         "emotion": "serious", "image_prompt": "dark village road"},
        {"text": "Kepala desa mengatakan belum ada bukti pasti dan meminta warga tidak menyebarkan kabar belum jelas.",
         "emotion": "sad", "image_prompt": "village hall"},
        {"text": "Polisi mengaku sudah menerima laporan dan akan mengecek lokasi besok.", "emotion": "angry",
         "image_prompt": "police car night"},
        {"text": "Bagaimana menurut kamu? Tulis di kolom komentar.", "emotion": "neutral", "image_prompt": ""},
    ]
    from app import writer
    d = {"title": "Sosok Putih di Jembatan", "segments": segs, "caption": "c", "hashtags": "#a"}
    d.update(writer.derive_fields(segs))
    db.save_script(sid, d)
    cid = characters.create({"name": "Tes", "voice": "id-ID-ArdiNeural", "mouth_x": 0.5, "mouth_y": 0.445,
                             "mouth_w": 0.13})
    characters.save_image(cid, "neutral", "closed", avatar("neutral"))
    characters.save_image(cid, "sad", "closed", avatar("sad"))
    characters.save_image(cid, "angry", "closed", avatar("angry"))
    characters.save_image(cid, "surprised", "closed", avatar("surprised"))
    characters.save_image(cid, "surprised", "open", avatar("surprised", True))
    return sid, cid


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height,duration",
                          "-of", "json", str(path)], capture_output=True).stdout
    return json.loads(out)["streams"]


def run(outdir=None):
    sid, cid = setup()
    # --- mode upload
    arr = np.concatenate([fake_speech(3.0), np.zeros(int(0.5 * audio.SR), np.float32), fake_speech(3.2),
                          np.zeros(int(0.5 * audio.SR), np.float32), fake_speech(3.0),
                          np.zeros(int(0.5 * audio.SR), np.float32), fake_speech(2.5),
                          np.zeros(int(0.5 * audio.SR), np.float32), fake_speech(2.0)])
    audio.write_wav(config.UPLOAD_DIR / f"story_{sid}_narration.wav", arr)
    mus = music.list_all()[0]["id"]
    job = Job("render", {})
    res = renderer.run_render(job, {"storyIds": [sid], "platforms": ["tiktok", "facebook_reels"],
                                    "characterId": cid, "voiceMode": "upload", "imageProvider": "gradient",
                                    "musicId": mus, "musicVolume": 10, "quality": "draft",
                                    "watermarkText": "@channelku", "headline": {"mode": "title"}})
    print("UPLOAD:", res)
    assert len(res["videos"]) == 2 and not res["failed"], res
    f = config.OUTPUT_DIR / res["videos"][0]["file"]
    st = probe(f)
    print(st)
    assert any(s["codec_name"] == "h264" for s in st) and any(s["codec_name"] == "aac" for s in st)
    vids = db.list_videos()
    assert all(v["status"] == "DONE" for v in vids)
    print("stage:", db.get_story(sid)["stage"])
    assert db.get_story(sid)["stage"] == "RENDERED"

    # --- mode tts (edge-tts dipalsukan dengan nada sintetis)
    def fake_synth(text, voice, emotion="neutral", retries=3):
        p = config.MEDIA_DIR / f"fake_{abs(hash(text))}.wav"
        audio.write_wav(p, fake_speech(max(1.2, len(text) / 16)))
        return p
    tts.synth = fake_synth
    job2 = Job("render", {})
    res2 = renderer.run_render(job2, {"storyIds": [sid], "platforms": ["instagram_reels"], "characterId": cid,
                                      "voiceMode": "tts", "imageProvider": "gradient", "quality": "draft"})
    print("TTS:", res2)
    assert len(res2["videos"]) == 1 and not res2["failed"]

    png = renderer.render_preview({"characterId": cid, "platforms": ["tiktok"], "emotion": "surprised",
                                   "watermarkText": "@channelku"})
    assert png[:4] == b"\x89PNG"
    if outdir:
        os.makedirs(outdir, exist_ok=True)
        open(os.path.join(outdir, "preview.png"), "wb").write(png)
        for i, t in enumerate((1.0, 4.5, 8.5, 12.0)):
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", str(f), "-frames:v", "1",
                            os.path.join(outdir, f"frame{i}.png")])
        print("frame contoh di", outdir)
    print("SEMUA OK")


if __name__ == "__main__":
    db.init_db() if False else None
    run(sys.argv[1] if len(sys.argv) > 1 else None)


def layout_previews(outdir):
    """Preview dengan posisi/ukuran/gaya berbeda -> cek visual."""
    sid, cid = setup()
    base = {"characterId": cid, "platforms": ["tiktok"], "emotion": "surprised",
            "text": "Warga Bogor geger setelah sosok putih terlihat di dekat jembatan pada Selasa malam.",
            "title": "Sosok Putih di Jembatan Cipularang"}
    variants = {
        "a_default": {},
        "b_custom": {"avatar": {"heightPct": 30, "x": 22, "bottom": 96},
                     "subtitle": {"y": 40, "x": 60, "size": 4.6, "font": "liberation-serif-bold", "color": "#ffe14d",
                                  "strokeColor": "#7a0010", "strokeWidth": 14, "box": True, "boxOpacity": 70,
                                  "uppercase": True, "width": 70},
                     "headline": {"y": 90, "size": 4.0, "font": "dejavu-mono-bold", "box": False, "strokeWidth": 12,
                                  "color": "#ff4d5e"}},
        "c_big_avatar_no_sub": {"avatar": {"heightPct": 55, "x": 50, "bottom": 100},
                                "subtitle": {"enabled": False}, "headline": {"mode": "custom", "text": "BREAKING NEWS", "y": 12}},
    }
    os.makedirs(outdir, exist_ok=True)
    for name, v in variants.items():
        open(os.path.join(outdir, f"layout_{name}.png"), "wb").write(renderer.render_preview({**base, **v}))
    print("layout preview di", outdir)
