import React, { useEffect, useState } from 'react';
import { Copy, Plus, Trash2, Upload } from 'lucide-react';
import { api, EMOTION_LABEL, useConfig } from '../ui.jsx';

function AvatarSlot({ char, emotion, mouth, onChange, onError }) {
  const has = char.images[emotion][mouth];
  const url = `/media/characters/${char.id}/${emotion}_${mouth}.png?v=${char._v || 0}`;
  const upload = async (file) => {
    const fd = new FormData(); fd.append('emotion', emotion); fd.append('mouth', mouth); fd.append('file', file);
    try { onChange(await api(`/characters/${char.id}/image`, { method: 'POST', body: fd })); } catch (e) { onError(e.message); }
  };
  const remove = async () => {
    try { onChange(await api(`/characters/${char.id}/image?emotion=${emotion}&mouth=${mouth}`, { method: 'DELETE' })); } catch (e) { onError(e.message); }
  };
  return (
    <div className="av-slot">
      {has ? <img src={url} alt="" /> : <div className="ph">—</div>}
      <div>{EMOTION_LABEL[emotion]} · {mouth === 'closed' ? 'tutup' : 'buka'}</div>
      <label><Upload size={10} /> {has ? 'Ganti' : 'Upload'}<input type="file" accept="image/*" onChange={(e) => e.target.files[0] && upload(e.target.files[0])} /></label>
      {has && !(emotion === 'neutral' && mouth === 'closed') && <button className="text-btn" style={{ marginLeft: 6 }} onClick={remove}>hapus</button>}
    </div>
  );
}

function CharacterEditor({ char, voices, tips, onSaved, onDeleted, onError }) {
  const [c, setC] = useState(char);
  const [showAll, setShowAll] = useState(false);
  const [copied, setCopied] = useState('');
  useEffect(() => setC(char), [char.id, char.images, char.has_avatar]);
  const set = (k, v) => setC((x) => ({ ...x, [k]: v }));
  const save = async () => {
    try {
      const r = await api(`/characters/${c.id}`, { method: 'PUT', body: { name: c.name, voice: c.voice, height_pct: c.height_pct, mouth_x: c.mouth_x, mouth_y: c.mouth_y, mouth_w: c.mouth_w, frame_style: c.frame_style } });
      onSaved({ ...r, _v: Date.now() }, 'Data karakter berhasil tersimpan.');
    } catch (e) { onError(e.message); }
  };
  const pick = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    set('mouth_x', +((e.clientX - r.left) / r.width).toFixed(3)); set('mouth_y', +((e.clientY - r.top) / r.height).toFixed(3));
  };
  const copy = async (key, text) => { await navigator.clipboard.writeText(text); setCopied(key); setTimeout(() => setCopied(''), 1400); };
  const emotions = ['neutral', 'serious', 'sad', 'angry', 'scared', 'surprised', 'happy'];
  const shown = showAll ? emotions : ['neutral', 'sad', 'angry', 'surprised', 'happy'];
  const variant = (emo, mouth) => tips.variant.replace('{emosi}', tips.emotions[emo]).replace('{mulut}', tips.mouths[mouth]);
  return (
    <div className="card form-card" style={{ marginBottom: 14 }}>
      <div className="card-heading"><div><h3>{c.name}</h3><p>{c.has_avatar ? 'Siap dipakai' : 'Upload gambar "Netral · tutup" dulu'}</p></div>
        <div className="row-actions"><button className="btn primary tiny" onClick={save}>Simpan</button>
          <button className="btn secondary tiny" onClick={() => confirm(`Hapus karakter ${c.name}?`) && onDeleted(c.id)}><Trash2 size={11} /></button></div></div>
      <div className="form-row">
        <div><label>Nama</label><input type="text" className="wide" value={c.name} onChange={(e) => set('name', e.target.value)} /></div>
        <div><label>Suara bawaan</label><select value={c.voice} onChange={(e) => set('voice', e.target.value)}>{voices.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}</select></div>
      </div>
      <div className="form-row">
        <div><label>Tinggi avatar di video <span>{Math.round(c.height_pct * 100)}% layar</span></label>
          <input type="range" min={0.2} max={0.6} step={0.01} value={c.height_pct} onChange={(e) => set('height_pct', +e.target.value)} /></div>
        <div><label>Bentuk bingkai</label><select value={c.frame_style} onChange={(e) => set('frame_style', e.target.value)}>
          <option value="none">Apa adanya (PNG transparan ideal)</option><option value="rounded">Kotak membulat</option><option value="circle">Lingkaran (potong bagian wajah)</option></select></div>
      </div>

      <label>Gambar karakter <span>wajib: Netral · tutup. Emosi lain & mulut terbuka opsional</span></label>
      <div className="avatar-grid">
        {shown.map((e) => (
          <React.Fragment key={e}>
            <AvatarSlot char={c} emotion={e} mouth="closed" onChange={onSaved} onError={onError} />
            <AvatarSlot char={c} emotion={e} mouth="open" onChange={onSaved} onError={onError} />
          </React.Fragment>))}
      </div>
      <button className="text-btn" onClick={() => setShowAll(!showAll)}>{showAll ? 'Sembunyikan emosi lain' : 'Tampilkan semua emosi (serius, takut, senang)'}</button>
      <p className="hint">Tanpa gambar emosi/mulut terbuka, app tetap menggerakkan mulut otomatis (elips di titik mulut) dan emosi lewat gerak tubuh + warna. Gambar emosi membuat alis/ekspresi berubah beneran.</p>

      {c.has_avatar && (<>
        <label>Posisi mulut <span>klik di gambar tepat di tengah mulut · hanya untuk gerak mulut otomatis</span></label>
        <div className="mouth-pick" onClick={pick}><img src={`/media/characters/${c.id}/neutral_closed.png?v=${c._v || 0}`} alt="" />
          <i style={{ left: `${c.mouth_x * 100}%`, top: `${c.mouth_y * 100}%` }} /></div>
        <label>Lebar mulut <span>{Math.round(c.mouth_w * 100)}% lebar gambar</span></label>
        <input type="range" min={0.05} max={0.4} step={0.01} value={c.mouth_w} onChange={(e) => set('mouth_w', +e.target.value)} />
      </>)}

      <label>Prompt siap pakai untuk AI gambar <span>supaya wajah & gaya konsisten</span></label>
      <div className="tag-row">
        <button className="btn secondary tiny" onClick={() => copy('base', tips.base)}><Copy size={10} /> {copied === 'base' ? 'Tersalin' : 'Avatar dari foto'}</button>
        {emotions.map((e) => <button key={e} className="btn secondary tiny" onClick={() => copy(e, variant(e, 'closed'))}><Copy size={10} /> {copied === e ? 'Tersalin' : EMOTION_LABEL[e]}</button>)}
        <button className="btn secondary tiny" onClick={() => copy('open', variant('neutral', 'open'))}><Copy size={10} /> {copied === 'open' ? 'Tersalin' : 'Mulut terbuka'}</button>
      </div>
    </div>
  );
}

export function Settings({ onError }) {
  const cfg = useConfig();
  const [chars, setChars] = useState([]);
  const [tracks, setTracks] = useState([]);
  const [health, setHealth] = useState(null);
  const [newName, setNewName] = useState('');
  const [mf, setMf] = useState({ name: '', source: '', license_note: '', confirm: false, file: null });
  const [notice, setNotice] = useState('');
  const loadChars = () => api('/characters').then((d) => setChars(d.items)).catch((e) => onError(e.message));
  const loadTracks = () => api('/music').then((d) => setTracks(d.items)).catch((e) => onError(e.message));
  useEffect(() => { loadChars(); loadTracks(); api('/health').then(setHealth).catch(() => {}); }, []);

  const replace = (c, message = '') => { setChars((list) => list.map((x) => (x.id === c.id ? { ...c, _v: Date.now() } : x))); if (message) { setNotice(message); setTimeout(() => setNotice(''), 2200); } };
  const create = async () => {
    try { const c = await api('/characters', { method: 'POST', body: { name: newName } }); setNewName(''); setChars((l) => [...l, c]); setNotice('Karakter berhasil ditambahkan.'); setTimeout(() => setNotice(''), 2200); }
    catch (e) { onError(e.message); }
  };
  const addMusic = async () => {
    const fd = new FormData();
    fd.append('name', mf.name); fd.append('source', mf.source); fd.append('license_note', mf.license_note);
    fd.append('confirm', mf.confirm ? 'true' : ''); fd.append('file', mf.file);
    try { await api('/music', { method: 'POST', body: fd }); setMf({ name: '', source: '', license_note: '', confirm: false, file: null }); loadTracks(); }
    catch (e) { onError(e.message); }
  };
  return (
    <>
      <div className="page-heading"><div><div className="eyebrow">SETTINGS</div><h1>Pengaturan</h1><p>Karakter avatar, library musik, dan status sistem.</p></div></div>
      {notice && <div className="ok-box" style={{ position: 'sticky', top: 72, zIndex: 20, marginBottom: 12 }}>✓ {notice}</div>}

      <div className="card settings-card" style={{ marginBottom: 16 }}>
        <div className="card-heading"><div><h3>Status sistem</h3><p>API key hanya dibaca dari file .env, tidak pernah tampil di sini</p></div></div>
        {health && [
          ['OpenAI API key', health.openai ? `Terpasang · model ${health.model}` : 'BELUM diisi (isi OPENAI_API_KEY di .env)', health.openai],
          ['FFmpeg (render video)', health.ffmpeg ? 'Tersedia' : 'Tidak ditemukan', health.ffmpeg],
          ['edge-tts (suara gratis)', health.edgeTts ? 'Tersedia' : 'Tidak terpasang', health.edgeTts],
          ['Zona waktu', `${health.tz} · sekarang ${health.now.slice(0, 16).replace('T', ' ')}`, true],
        ].map(([a, b, ok]) => (<div className="setting-row" key={a}><div><b>{a}</b><small>{b}</small></div><span className={`badge ${ok ? 'green' : 'red'}`}>{ok ? 'OK' : 'PERIKSA'}</span></div>))}
      </div>

      <div className="card settings-card" style={{ marginBottom: 16 }}>
        <div className="card-heading"><div><h3>Karakter avatar</h3><p>Upload avatar hasil AI gambar. Di Content Management tinggal pilih dari dropdown.</p></div></div>
        {cfg && chars.map((c) => <CharacterEditor key={c.id} char={c} voices={cfg.voices} tips={cfg.promptTips} onSaved={replace}
          onDeleted={(id) => api(`/characters/${id}`, { method: 'DELETE' }).then(loadChars).catch((e) => onError(e.message))} onError={onError} />)}
        <div className="row-actions"><input type="text" className="wide" style={{ maxWidth: 260 }} placeholder="Nama karakter baru" value={newName} onChange={(e) => setNewName(e.target.value)} />
          <button className="btn primary" disabled={!newName.trim()} onClick={create}><Plus size={13} /> Tambah karakter</button></div>
      </div>

      <div className="card settings-card">
        <div className="card-heading"><div><h3>Library musik latar</h3><p>Musik bawaan disintesis sendiri oleh app (bebas hak cipta). Upload musik lain bila lisensinya jelas.</p></div></div>
        {tracks.map((t) => (
          <div className="setting-row" key={t.id}>
            <div><b>{t.name}</b><small>{t.license_note || t.source}</small>
              <audio controls preload="none" src={`/media/music/${t.filename}`} style={{ height: 30, marginTop: 6 }} /></div>
            {t.builtin ? <span className="badge green">bawaan</span>
              : <button className="btn secondary tiny" onClick={() => confirm('Hapus musik ini?') && api(`/music/${t.id}`, { method: 'DELETE' }).then(loadTracks)}><Trash2 size={11} /></button>}
          </div>))}
        <div className="form-card" style={{ marginTop: 18 }}>
          <b style={{ fontSize: 12 }}>Tambah musik sendiri</b>
          <div className="form-row">
            <div><label>Nama</label><input type="text" className="wide" value={mf.name} onChange={(e) => setMf({ ...mf, name: e.target.value })} /></div>
            <div><label>Sumber / link lisensi</label><input type="text" className="wide" placeholder="mis. pixabay.com/music" value={mf.source} onChange={(e) => setMf({ ...mf, source: e.target.value })} /></div>
          </div>
          <label>File musik <span>mp3 / wav / m4a / ogg</span></label>
          <input type="file" accept="audio/*" onChange={(e) => setMf({ ...mf, file: e.target.files[0] })} />
          <label className="check-label"><input type="checkbox" checked={mf.confirm} onChange={(e) => setMf({ ...mf, confirm: e.target.checked })} />
            Saya memastikan musik ini bebas hak cipta / boleh dipakai komersial<span>Tanggung jawab lisensi ada di pengguna. Cek ketentuan situs sumbernya.</span></label>
          <button className="btn primary" disabled={!mf.file || !mf.confirm} onClick={addMusic}><Upload size={13} /> Upload musik</button>
        </div>
      </div>
    </>
  );
}
