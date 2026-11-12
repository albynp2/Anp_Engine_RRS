import React, { useEffect, useRef, useState } from 'react';
import { Check, Download, Eye, Film, Trash2, Upload } from 'lucide-react';
import { api, JobPanel, useConfig, useJob } from '../ui.jsx';

const merge = (d, s) => {
  const out = { ...d };
  Object.keys(s || {}).forEach((k) => {
    out[k] = d[k] && typeof d[k] === 'object' && !Array.isArray(d[k]) && s[k] && typeof s[k] === 'object' ? merge(d[k], s[k]) : s[k];
  });
  return out;
};

/** Slider yang bisa "Otomatis" (nilai null = ikut safe zone platform / pengaturan karakter). */
function AutoSlider({ label, value, def, min, max, step = 1, unit = '%', onChange }) {
  const auto = value === null || value === undefined || value === '';
  return (
    <div>
      <label>{label} <span>{auto ? 'otomatis' : `${value}${unit}`}</span></label>
      <input type="range" min={min} max={max} step={step} value={auto ? def : value} disabled={auto} onChange={(e) => onChange(+e.target.value)} />
      <label className="check-label" style={{ marginTop: 4 }}><input type="checkbox" checked={auto} onChange={(e) => onChange(e.target.checked ? null : def)} />Otomatis</label>
    </div>
  );
}

const Slide = ({ label, value, min, max, step = 1, unit = '', onChange }) => (
  <div>
    <label>{label} <span>{value}{unit}</span></label>
    <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(+e.target.value)} />
  </div>
);

const ColorField = ({ label, value, onChange }) => (
  <div>
    <label>{label}</label>
    <input type="color" value={value} onChange={(e) => onChange(e.target.value)} style={{ width: '100%', height: 34, border: '1px solid #293846', borderRadius: 8, background: '#0a121b', padding: 2 }} />
  </div>
);

/** Kontrol gaya teks: dipakai untuk subtitle & judul. */
function TextStyle({ v, set, fonts, onFontUpload, yDef }) {
  return (
    <>
      <div className="form-row">
        <div><label>Jenis tulisan (font)</label>
          <select value={v.font} onChange={(e) => set({ font: e.target.value })}>
            {fonts.map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}</select>
          <label className="btn secondary tiny" style={{ marginTop: 6 }}><Upload size={10} /> Upload font (.ttf/.otf)
            <input type="file" accept=".ttf,.otf" hidden onChange={(e) => e.target.files[0] && onFontUpload(e.target.files[0])} /></label></div>
        <Slide label="Ukuran tulisan" value={v.size} min={1.5} max={8} step={0.1} unit="%" onChange={(x) => set({ size: x })} />
      </div>
      <div className="form-row">
        <ColorField label="Warna tulisan" value={v.color} onChange={(x) => set({ color: x })} />
        <ColorField label="Warna outline" value={v.strokeColor} onChange={(x) => set({ strokeColor: x })} />
      </div>
      <div className="form-row">
        <Slide label="Tebal outline" value={v.strokeWidth} min={0} max={25} unit="%" onChange={(x) => set({ strokeWidth: x })} />
        <div><label>Huruf</label>
          <label className="check-label"><input type="checkbox" checked={v.uppercase} onChange={(e) => set({ uppercase: e.target.checked })} />HURUF BESAR SEMUA</label></div>
      </div>
      <label className="check-label"><input type="checkbox" checked={v.box} onChange={(e) => set({ box: e.target.checked })} />Kotak latar di belakang tulisan</label>
      {v.box && (
        <div className="form-row">
          <ColorField label="Warna kotak" value={v.boxColor} onChange={(x) => set({ boxColor: x })} />
          <Slide label="Transparansi kotak" value={v.boxOpacity} min={10} max={100} unit="%" onChange={(x) => set({ boxOpacity: x })} />
        </div>)}
      <div className="form-row">
        <Slide label="Posisi horizontal (tengah)" value={v.x} min={5} max={95} unit="%" onChange={(x) => set({ x })} />
        <AutoSlider label="Posisi vertikal (tengah)" value={v.y} def={yDef} min={3} max={97} onChange={(y) => set({ y })} />
      </div>
      <div className="tag-row">
        <span className="muted" style={{ fontSize: 10 }}>Posisi cepat:</span>
        {[['Atas', 10], ['Tengah atas', 30], ['Tengah', 50], ['Tengah bawah', 68], ['Bawah', 82]].map(([t, y]) => (
          <button key={t} className="btn secondary tiny" onClick={() => set({ y })}>{t}</button>))}
        <button className="btn secondary tiny" onClick={() => set({ y: null, x: 50 })}>Reset otomatis</button>
      </div>
      <div className="form-row">
        <Slide label="Lebar area teks" value={v.width} min={30} max={100} unit="%" onChange={(x) => set({ width: x })} />
        <div><label>Maks. baris</label>
          <select value={v.maxLines} onChange={(e) => set({ maxLines: +e.target.value })}>{[1, 2, 3, 4].map((n) => <option key={n} value={n}>{n} baris</option>)}</select></div>
      </div>
    </>
  );
}

export function ContentManagement({ go, onError }) {
  const cfg = useConfig();
  const [scripts, setScripts] = useState([]);
  const [sel, setSel] = useState(new Set());
  const [chars, setChars] = useState([]);
  const [tracks, setTracks] = useState([]);
  const [videos, setVideos] = useState([]);
  const [fonts, setFonts] = useState([]);
  const [o, setO] = useState(null);
  const [audio, setAudio] = useState({});
  const [preview, setPreview] = useState(null);
  const [live, setLive] = useState(false);
  const [emo, setEmo] = useState('neutral');
  const loaded = useRef(false);

  const loadVideos = () => api('/videos').then((d) => setVideos(d.items)).catch(() => {});
  const hook = useJob('render', () => loadVideos());

  useEffect(() => {
    if (!cfg) return;
    setFonts(cfg.fonts || []);
    Promise.all([api('/scripts'), api('/characters'), api('/music'), api('/content-settings')]).then(([s, c, m, st]) => {
      setScripts(s.items); setChars(c.items); setTracks(m.items);
      const merged = merge(cfg.defaults, st.config || {});
      if (!merged.characterId && c.items[0]) merged.characterId = c.items[0].id;
      setO(merged); loaded.current = true;
    }).catch((e) => onError(e.message));
    loadVideos();
  }, [cfg]);

  useEffect(() => {  // simpan pengaturan otomatis (template)
    if (!loaded.current || !o) return;
    const t = setTimeout(() => api('/content-settings', { method: 'PUT', body: o }).catch(() => {}), 600);
    return () => clearTimeout(t);
  }, [o]);

  useEffect(() => {  // status audio upload per naskah terpilih
    [...sel].forEach((id) => {
      if (audio[id] === undefined) api(`/scripts/${id}`).then((s) => setAudio((a) => ({ ...a, [id]: s.uploaded_audio }))).catch(() => {});
    });
  }, [sel]);

  const firstScript = o ? (scripts.find((s) => sel.has(s.story_id)) || scripts[0]) : null;
  const makePreview = async () => {
    try {
      const blob = await api('/render/preview', { method: 'POST', body: { ...o, title: firstScript ? firstScript.title : '', text: firstScript ? firstScript.hook : '', emotion: emo, level: 0.8 } });
      setPreview((old) => { if (old) URL.revokeObjectURL(old); return URL.createObjectURL(blob); });
    } catch (e) { setLive(false); onError(e.message); }
  };
  useEffect(() => {  // preview otomatis ikut berubah saat pengaturan digeser
    if (!live || !o) return;
    const t = setTimeout(makePreview, 450);
    return () => clearTimeout(t);
  }, [o, live, emo, sel, scripts]);

  if (!cfg || !o) return <div className="muted">Memuat…</div>;
  const set = (k, v) => setO((x) => ({ ...x, [k]: v }));
  const setG = (g) => (patch) => setO((x) => ({ ...x, [g]: { ...x[g], ...patch } }));
  const toggle = (id) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const togglePlat = (p) => set('platforms', o.platforms.includes(p) ? o.platforms.filter((x) => x !== p) : [...o.platforms, p]);
  const char = chars.find((c) => c.id === Number(o.characterId));
  const missingAudio = o.voiceMode === 'upload' && [...sel].some((id) => !audio[id]);
  const canRender = sel.size > 0 && o.platforms.length > 0 && !missingAudio && !hook.running;

  const upAudio = async (id, file) => {
    const fd = new FormData(); fd.append('file', file);
    try { const r = await api(`/stories/${id}/audio`, { method: 'POST', body: fd }); setAudio((a) => ({ ...a, [id]: r.name })); }
    catch (e) { onError(e.message); }
  };
  const upWatermark = async (file) => {
    const fd = new FormData(); fd.append('file', file);
    try { const r = await api('/uploads/watermark', { method: 'POST', body: fd }); set('watermarkImagePath', r.path); }
    catch (e) { onError(e.message); }
  };
  const upFont = (target) => async (file) => {
    const fd = new FormData(); fd.append('file', file);
    try { const r = await api('/fonts', { method: 'POST', body: fd }); setFonts(r.items); setG(target)({ font: r.id }); }
    catch (e) { onError(e.message); }
  };
  const render = () => hook.start({ ...o, storyIds: [...sel] }).catch((e) => onError(e.message));
  const publish = (v) => api(`/videos/${v.id}`, { method: 'PATCH', body: { published: !v.published_at } }).then(loadVideos).catch((e) => onError(e.message));
  const delVideo = (v) => confirm('Hapus video ini?') && api(`/videos/${v.id}`, { method: 'DELETE' }).then(loadVideos);
  const platLabel = (id) => (cfg.platforms.find((p) => p.id === id) || {}).label || id;
  const charH = char ? Math.round(char.height_pct * 100) : 38;

  return (
    <>
      <div className="page-heading"><div><div className="eyebrow">CONTENT MANAGEMENT</div><h1>Generate video</h1>
        <p>Pilih naskah → karakter membacakan berita → atur tampilan → video siap untuk Reels / Shorts / TikTok.</p></div></div>
      <div className="content-studio">
        <div style={{ display: 'grid', gap: 16 }}>
          <div className="card form-card">
            <div className="card-heading"><div><h3>1. Pilih naskah</h3><p>{scripts.length} naskah tersedia</p></div></div>
            {scripts.length === 0 && <div className="empty-small">Belum ada naskah. Buat di Production Queue.</div>}
            {scripts.map((s) => (
              <label className="script-select" key={s.story_id}>
                <input type="checkbox" checked={sel.has(s.story_id)} onChange={() => toggle(s.story_id)} />
                <span><b>{s.title}</b><small>{s.words} kata · {s.segment_count} segmen · {s.stage}</small></span>
                {o.voiceMode === 'upload' && sel.has(s.story_id) && (
                  <span style={{ flex: 'none' }}>
                    {audio[s.story_id] ? <span className="badge green"><Check size={10} /> audio ada</span> : <span className="badge red">butuh audio</span>}
                    <label className="btn secondary tiny" style={{ marginLeft: 6 }}><Upload size={10} /> Upload
                      <input type="file" accept="audio/*" hidden onChange={(e) => e.target.files[0] && upAudio(s.story_id, e.target.files[0])} /></label>
                  </span>)}
              </label>
            ))}
          </div>

          <div className="card form-card">
            <div className="card-heading"><div><h3>2. Platform</h3><p>Safe zone otomatis disesuaikan per platform (9:16)</p></div></div>
            <div className="tag-row">{cfg.platforms.map((p) => (
              <label key={p.id} className={`radio-card ${o.platforms.includes(p.id) ? 'on' : ''}`} style={{ padding: '8px 12px' }}>
                <input type="checkbox" hidden checked={o.platforms.includes(p.id)} onChange={() => togglePlat(p.id)} />{p.label}</label>))}</div>
          </div>

          <div className="card form-card">
            <div className="card-heading"><div><h3>3. Karakter & suara</h3><p>Karakter diatur di Settings → Karakter</p></div></div>
            <label>Karakter (avatar yang membacakan)</label>
            <select value={o.characterId || ''} onChange={(e) => set('characterId', e.target.value ? Number(e.target.value) : null)}>
              <option value="">Tanpa avatar (hanya gambar + subtitle)</option>
              {chars.map((c) => <option key={c.id} value={c.id}>{c.name}{c.has_avatar ? '' : ' (belum ada gambar)'}</option>)}
            </select>
            {chars.length === 0 && <p className="hint">Belum ada karakter. <button className="text-btn" onClick={() => go('settings')}>Buat di Settings</button></p>}
            <label>Sumber suara</label>
            <div className="radio-cards">
              <div className={`radio-card ${o.voiceMode === 'tts' ? 'on' : ''}`} onClick={() => set('voiceMode', 'tts')}><b>TTS otomatis (edge-tts)</b><small>Gratis, emosi lewat tempo & nada per segmen.</small></div>
              <div className={`radio-card ${o.voiceMode === 'upload' ? 'on' : ''}`} onClick={() => set('voiceMode', 'upload')}><b>Upload audio sendiri</b><small>Dari Google AI Studio. Teksnya disalin di Story Writer.</small></div>
            </div>
            {o.voiceMode === 'tts' && (<><label>Suara <span>kosong = suara bawaan karakter</span></label>
              <select value={o.voice} onChange={(e) => set('voice', e.target.value)}>
                <option value="">Ikuti karakter{char ? ` (${char.voice})` : ''}</option>
                {cfg.voices.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}</select></>)}
            {missingAudio && <p className="hint accent">Upload audio untuk semua naskah terpilih (tombol Upload di daftar naskah).</p>}
          </div>

          <div className="card form-card">
            <div className="card-heading"><div><h3>4. Gambar & musik</h3></div></div>
            <div className="form-row">
              <div><label>Gambar scene</label>
                <select value={o.imageProvider} onChange={(e) => set('imageProvider', e.target.value)}>
                  {cfg.imageProviders.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}</select></div>
              <Slide label="Maks gambar per video" value={o.maxImages} min={3} max={14} onChange={(x) => set('maxImages', x)} />
            </div>
            <div className="form-row">
              <div><label>Musik latar</label>
                <select value={o.musicId || ''} onChange={(e) => set('musicId', e.target.value ? Number(e.target.value) : null)}>
                  <option value="">Tanpa musik</option>
                  {tracks.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select></div>
              <Slide label="Volume musik" value={o.musicVolume} min={3} max={40} unit="%" onChange={(x) => set('musicVolume', x)} />
            </div>
          </div>

          <div className="card form-card">
            <div className="card-heading"><div><h3>5. Tata letak avatar</h3><p>Ukuran & posisi karakter di layar. Hasilnya langsung terlihat di preview.</p></div></div>
            <div className="form-row">
              <AutoSlider label="Ukuran avatar (tinggi)" value={o.avatar.heightPct} def={charH} min={15} max={95} onChange={(v) => setG('avatar')({ heightPct: v })} />
              <Slide label="Posisi horizontal (tengah)" value={o.avatar.x} min={5} max={95} unit="%" onChange={(v) => setG('avatar')({ x: v })} />
            </div>
            <AutoSlider label="Posisi vertikal (dasar avatar dari atas layar)" value={o.avatar.bottom} def={88} min={30} max={105} onChange={(v) => setG('avatar')({ bottom: v })} />
            <div className="tag-row">
              <span className="muted" style={{ fontSize: 10 }}>Posisi cepat:</span>
              <button className="btn secondary tiny" onClick={() => setG('avatar')({ x: 50 })}>Tengah</button>
              <button className="btn secondary tiny" onClick={() => setG('avatar')({ x: 24 })}>Kiri</button>
              <button className="btn secondary tiny" onClick={() => setG('avatar')({ x: 76 })}>Kanan</button>
              <button className="btn secondary tiny" onClick={() => setG('avatar')({ heightPct: null, x: 50, bottom: null })}>Reset otomatis</button>
            </div>
            <p className="hint">Otomatis = avatar berada di atas area yang tertutup tombol platform. Nilai manual bisa melewati safe zone, jadi cek di preview.</p>
          </div>

          <div className="card form-card">
            <div className="card-heading"><div><h3>6. Subtitle</h3></div></div>
            <label className="check-label"><input type="checkbox" checked={o.subtitle.enabled} onChange={(e) => setG('subtitle')({ enabled: e.target.checked })} />Tampilkan subtitle</label>
            {o.subtitle.enabled && <TextStyle v={o.subtitle} set={setG('subtitle')} fonts={fonts} onFontUpload={upFont('subtitle')} yDef={62} />}
          </div>

          <div className="card form-card">
            <div className="card-heading"><div><h3>7. Judul di atas video</h3></div></div>
            <div className="form-row">
              <div><label>Isi judul</label>
                <select value={o.headline.mode} onChange={(e) => setG('headline')({ mode: e.target.value })}>
                  <option value="title">Judul naskah</option><option value="custom">Teks sendiri</option><option value="none">Tanpa judul</option></select></div>
              {o.headline.mode === 'custom' && <div><label>Teks judul</label><input type="text" className="wide" value={o.headline.text} onChange={(e) => setG('headline')({ text: e.target.value })} /></div>}
            </div>
            {o.headline.mode !== 'none' && <TextStyle v={o.headline} set={setG('headline')} fonts={fonts} onFontUpload={upFont('headline')} yDef={12} />}
          </div>

          <div className="card form-card">
            <div className="card-heading"><div><h3>8. Watermark & kualitas</h3></div></div>
            <div className="form-row">
              <div><label>Watermark teks</label><input type="text" className="wide" placeholder="@namachannel" value={o.watermarkText} onChange={(e) => set('watermarkText', e.target.value)} /></div>
              <div><label>Posisi</label>
                <select value={o.watermarkPosition} onChange={(e) => set('watermarkPosition', e.target.value)}>
                  {['top-right', 'top-left', 'center', 'bottom-left', 'bottom-right'].map((p) => <option key={p}>{p}</option>)}</select></div>
            </div>
            <div className="form-row">
              <Slide label="Opacity watermark" value={o.watermarkOpacity} min={5} max={100} unit="%" onChange={(x) => set('watermarkOpacity', x)} />
              <div><label>Logo (gambar) <span>{o.watermarkImagePath ? 'terpasang' : 'opsional'}</span></label>
                <div className="row-actions"><label className="btn secondary tiny"><Upload size={10} /> Pilih
                  <input type="file" accept="image/*" hidden onChange={(e) => e.target.files[0] && upWatermark(e.target.files[0])} /></label>
                  {o.watermarkImagePath && <button className="btn secondary tiny" onClick={() => set('watermarkImagePath', '')}>Hapus</button>}</div></div>
            </div>
            <label>Kualitas</label>
            <select value={o.quality} onChange={(e) => set('quality', e.target.value)}>
              <option value="hd">HD 1080×1920 · 30 fps (hasil akhir)</option><option value="draft">Draft 540×960 · 24 fps (cepat, untuk tes)</option></select>
          </div>
        </div>

        <div style={{ display: 'grid', gap: 16, alignSelf: 'start', position: 'sticky', top: 86 }}>
          <div className="card form-card">
            <div className="card-heading"><div><h3>Preview tampilan</h3><p>{live ? 'Otomatis ikut berubah saat pengaturan digeser' : 'Satu frame contoh dengan pengaturan sekarang'}</p></div></div>
            {preview ? <img className="preview-img" src={preview} alt="preview" /> : <div className="video-preview-frame" style={{ minHeight: 220 }}><div className="preview-center">Belum ada preview</div></div>}
            <div className="form-row">
              <div><label>Emosi contoh</label>
                <select value={emo} onChange={(e) => setEmo(e.target.value)}>{cfg.emotions.map((e) => <option key={e} value={e}>{e}</option>)}</select></div>
              <div style={{ alignSelf: 'end' }}><button className="btn secondary full" onClick={() => { setLive(true); makePreview(); }}><Eye size={13} /> {live ? 'Segarkan' : 'Buat preview'}</button></div>
            </div>
            <div className="render-summary">
              <div><span>Naskah</span><b>{sel.size}</b></div><div><span>Platform</span><b>{o.platforms.length}</b></div>
              <div><span>Karakter</span><b>{char ? char.name : 'tanpa'}</b></div><div><span>Total video</span><b>{sel.size * o.platforms.length}</b></div>
            </div>
            <button className="btn primary full" disabled={!canRender} onClick={render}><Film size={14} /> {hook.running ? 'Sedang render…' : 'Generate video'}</button>
            <p className="hint">Preview memakai platform pertama yang dipilih. Waktu render kira-kira 1–2 menit per video HD. Pengaturan tersimpan otomatis sebagai template.</p>
          </div>
        </div>
      </div>

      <div style={{ marginTop: 16 }}><JobPanel title="Render video" hook={hook} /></div>

      <div className="card form-card" style={{ marginTop: 6 }}>
        <div className="card-heading"><div><h3>Video hasil</h3><p>{videos.length} video</p></div></div>
        {videos.length === 0 && <div className="empty-small">Belum ada video.</div>}
        {videos.map((v) => (
          <div className="video-card" key={v.id}>
            {v.status === 'DONE' ? <video src={`/media/outputs/${v.path}`} controls preload="metadata" /> : <div className="video-preview-frame" style={{ width: 120, minHeight: 200 }} />}
            <div>
              <b style={{ fontSize: 12 }}>{v.title || `Naskah #${v.story_id}`}</b>
              <div className="tag-row">
                <span className="badge blue">{platLabel(v.platform)}</span>
                <span className={`badge ${v.status === 'DONE' ? 'green' : v.status === 'FAILED' ? 'red' : 'orange'}`}>{v.status}</span>
                {v.published_at && <span className="badge green">Published</span>}
                {v.character_name && <span className="badge">{v.character_name}</span>}
                {v.duration && <span className="badge">{Math.round(v.duration)} dtk</span>}</div>
              {v.error && <p className="hint accent">{v.error}</p>}
              <div className="row-actions" style={{ marginTop: 8 }}>
                {v.status === 'DONE' && <a className="btn secondary tiny" href={`/media/outputs/${v.path}`} download><Download size={11} /> Unduh</a>}
                {v.status === 'DONE' && <button className="btn secondary tiny" onClick={() => publish(v)}><Check size={11} /> {v.published_at ? 'Batal published' : 'Tandai published'}</button>}
                <button className="btn secondary tiny" onClick={() => delVideo(v)}><Trash2 size={11} /></button></div>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
