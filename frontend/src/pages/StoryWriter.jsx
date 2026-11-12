import React, { useEffect, useState } from 'react';
import { AlertTriangle, ArrowDown, ArrowUp, Copy, ExternalLink, FileText, Plus, RefreshCw, Save, Trash2, X } from 'lucide-react';
import { api, EMOTION_LABEL, JobPanel, StageBadge, useConfig, useJob } from '../ui.jsx';

export function StoryWriter({ go, onError }) {
  const cfg = useConfig();
  const [list, setList] = useState([]);
  const [cur, setCur] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [copied, setCopied] = useState(false);
  const loadList = () => api('/scripts').then((d) => setList(d.items)).catch((e) => onError(e.message));
  const open = (id) => api(`/scripts/${id}`).then((s) => { setCur(s); setDirty(false); }).catch((e) => onError(e.message));
  const hook = useJob('write', () => { loadList(); if (cur) open(cur.story_id); });
  useEffect(() => { loadList(); }, []);

  const edit = (patch) => { setCur((c) => ({ ...c, ...patch })); setDirty(true); };
  const setSeg = (i, patch) => edit({ segments: cur.segments.map((s, k) => (k === i ? { ...s, ...patch } : s)) });
  const move = (i, d) => {
    const a = [...cur.segments]; const j = i + d;
    if (j < 0 || j >= a.length) return;
    [a[i], a[j]] = [a[j], a[i]]; edit({ segments: a });
  };
  const save = async () => {
    try {
      const r = await api(`/scripts/${cur.story_id}`, { method: 'PUT', body: { title: cur.title, caption: cur.caption, hashtags: cur.hashtags, segments: cur.segments } });
      await open(cur.story_id); loadList(); return r;
    } catch (e) { onError(e.message); }
  };
  const del = async () => {
    if (!confirm('Hapus naskah ini? Berita kembali ke status antre.')) return;
    await api(`/scripts/${cur.story_id}`, { method: 'DELETE' }).catch((e) => onError(e.message));
    setCur(null); loadList();
  };
  const rewrite = () => {
    if (!confirm('Tulis ulang dengan AI? Naskah lama (termasuk editan lu) akan diganti.')) return;
    hook.start({ storyIds: [cur.story_id], force: true }).catch((e) => onError(e.message));
  };
  const copy = async () => { await navigator.clipboard.writeText(cur.tts_text); setCopied(true); setTimeout(() => setCopied(false), 1500); };
  const emotions = cfg ? cfg.emotions : Object.keys(EMOTION_LABEL);

  return (
    <>
      <div className="page-heading"><div><div className="eyebrow">STORY WRITER</div><h1>Naskah</h1>
        <p>Cek dan edit naskah hasil AI. Tiap segmen punya emosi suara & karakter, serta prompt gambar.</p></div></div>
      <JobPanel title="Menulis ulang naskah" hook={hook} />
      <div className="two-col" style={{ gridTemplateColumns: '0.8fr 1.6fr' }}>
        <div className="card library-card">
          <div className="card-heading"><div><h3>Daftar naskah</h3><p>{list.length} naskah</p></div></div>
          <div className="script-list">
            {list.length === 0 && <div className="empty-small">Belum ada naskah. Tulis dari Production Queue.</div>}
            {list.map((s) => (
              <button key={s.story_id} className="script-item" onClick={() => open(s.story_id)}
                style={cur && cur.story_id === s.story_id ? { background: '#1a2430' } : null}>
                <span className="script-icon"><FileText size={15} /></span>
                <span><b>{s.title}</b><small>{s.source} · terbit {(s.published_date || s.published || '').slice(0, 10) || '—'} · {s.words} kata · {s.segment_count} segmen</small></span>
                {s.fact_warnings && s.fact_warnings.length > 0 && <AlertTriangle size={14} color="#ffb86b" />}
              </button>
            ))}
          </div>
        </div>
        <div className="card form-card">
          {!cur && <div className="empty-small">Pilih naskah di sebelah kiri.</div>}
          {cur && (<>
            <div className="card-heading"><div><h3>Edit naskah</h3>
              <p>Perkiraan durasi {cur.estimated_seconds} detik · <StageBadge stage={cur.stage} /> · <span className="badge blue">Sumber: {cur.source || '—'}</span> · <span className="badge">Terbit: {(cur.published_date || cur.published || '').slice(0, 10) || '—'}</span> · <a href={cur.url} target="_blank" rel="noreferrer" style={{ color: '#6baaff' }}><ExternalLink size={10} /> sumber: {cur.source}</a></p></div></div>
            {cur.fact_warnings && cur.fact_warnings.length > 0
              ? <div className="warn-box"><b><AlertTriangle size={13} /> Periksa — kata/angka ini tidak ditemukan di artikel sumber:</b><br />{cur.fact_warnings.join(', ')}<br /><small>Bisa jadi salah tulis atau tambahan AI. Hapus/ubah kalau memang tidak ada di berita.</small></div>
              : <div className="ok-box">Cek fakta otomatis: semua nama & angka di naskah ditemukan di artikel sumber.</div>}
            <div className="ok-box" style={{ marginBottom: 12 }}><b>Sumber berita</b><br />{cur.source || '—'} · terbit {(cur.published_date || cur.published || '').slice(0, 10) || '—'}<br /><small>Metadata ini ikut dibawa ke Content Management dan dapat ditampilkan di video.</small></div>
            <label>Judul video</label>
            <input className="wide" value={cur.title || ''} onChange={(e) => edit({ title: e.target.value })} />
            <label>Segmen narasi <span>satu segmen = satu bagian suara & satu gambar</span></label>
            {cur.segments.map((s, i) => (
              <div className="seg-row" key={i}>
                <div className="n">{i + 1}</div>
                <textarea value={s.text} onChange={(e) => setSeg(i, { text: e.target.value })} />
                <select value={s.emotion} onChange={(e) => setSeg(i, { emotion: e.target.value })}>
                  {emotions.map((e) => <option key={e} value={e}>{EMOTION_LABEL[e] || e}</option>)}
                </select>
                <div style={{ display: 'grid', gap: 4 }}>
                  <button className="btn secondary tiny" onClick={() => move(i, -1)}><ArrowUp size={10} /></button>
                  <button className="btn secondary tiny" onClick={() => move(i, 1)}><ArrowDown size={10} /></button>
                  <button className="btn secondary tiny" onClick={() => edit({ segments: cur.segments.filter((_, k) => k !== i) })}><X size={10} /></button>
                </div>
                <input className="img" placeholder="prompt gambar (English)" value={s.image_prompt || ''} onChange={(e) => setSeg(i, { image_prompt: e.target.value })} />
              </div>
            ))}
            <button className="btn secondary tiny" style={{ marginTop: 10 }} onClick={() => edit({ segments: [...cur.segments, { text: '', emotion: 'neutral', image_prompt: '' }] })}><Plus size={11} /> Tambah segmen</button>
            <label>Caption</label>
            <textarea className="wide" rows={3} value={cur.caption || ''} onChange={(e) => edit({ caption: e.target.value })} />
            <label>Hashtag</label>
            <input className="wide" value={cur.hashtags || ''} onChange={(e) => edit({ hashtags: e.target.value })} />
            {cur.fact_boundary && <p className="hint">Belum dikonfirmasi sumber: {cur.fact_boundary}</p>}
            <div className="sticky-actions">
              <div className="row-actions">
                <button className="btn secondary" onClick={rewrite} disabled={hook.running}><RefreshCw size={13} /> Tulis ulang AI</button>
                <button className="btn secondary" onClick={del}><Trash2 size={13} /> Hapus</button></div>
              <button className="btn primary" disabled={!dirty} onClick={save}><Save size={14} /> {dirty ? 'Simpan perubahan' : 'Tersimpan'}</button>
            </div>
            <label>Teks untuk Google AI Studio (Generate Speech) <span>opsional, untuk suara hasil upload</span></label>
            <textarea className="copy-area" readOnly value={cur.tts_text} />
            <div className="row-actions" style={{ marginTop: 8 }}>
              <button className="btn secondary tiny" onClick={copy}><Copy size={11} /> {copied ? 'Tersalin!' : 'Salin teks'}</button>
              <button className="btn secondary tiny" onClick={() => go('content')}>Lanjut ke Content Management</button>
            </div>
            <p className="hint">Simpan perubahan dulu sebelum menyalin. Setelah suara dibuat, upload file audionya di Content Management (mode "Upload audio").</p>
          </>)}
        </div>
      </div>
    </>
  );
}
