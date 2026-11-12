import React, { useEffect, useState } from 'react';
import { ExternalLink, ListPlus, PenLine, Search, Trash2 } from 'lucide-react';
import { api, JobPanel, Pager, Score, StageBadge, useJob } from '../ui.jsx';

export function Gallery({ go, onError }) {
  const [q, setQ] = useState({ search: '', stage: 'NEW', dateFrom: '', dateTo: '', page: 1 });
  const [data, setData] = useState({ items: [], total: 0, limit: 25 });
  const [sel, setSel] = useState(new Set());
  const load = () => {
    const p = new URLSearchParams({ page: q.page, limit: 25, search: q.search, stage: q.stage, dateFrom: q.dateFrom, dateTo: q.dateTo });
    api('/articles?' + p).then((d) => { setData(d); setSel(new Set()); }).catch((e) => onError(e.message));
  };
  useEffect(load, [q.page, q.stage, q.dateFrom, q.dateTo]);
  const upd = (k, v) => setQ((x) => ({ ...x, [k]: v, page: k === 'page' ? v : 1 }));
  const selectable = data.items.filter((a) => a.stage === 'NEW');
  const toggle = (id) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const addToQueue = async () => {
    try { await api('/queue', { method: 'POST', body: { ids: [...sel] } }); go('queue'); }
    catch (e) { onError(e.message); }
  };
  return (
    <>
      <div className="page-heading"><div><div className="eyebrow">ARTIKEL GALLERY</div><h1>Pilih berita</h1>
        <p>Diurutkan dari skor AI + popularitas tertinggi. Centang berita yang mau dijadikan naskah.</p></div></div>
      <div className="card library-card">
        <div className="toolbar">
          <div className="searchbox"><Search size={14} /><input placeholder="Cari judul / media…" value={q.search}
            onChange={(e) => setQ({ ...q, search: e.target.value })} onKeyDown={(e) => e.key === 'Enter' && upd('search', q.search)} /></div>
          <input type="date" className="wide" style={{ width: 150 }} value={q.dateFrom} onChange={(e) => upd('dateFrom', e.target.value)} title="Terbit dari" />
          <input type="date" className="wide" style={{ width: 150 }} value={q.dateTo} onChange={(e) => upd('dateTo', e.target.value)} title="Terbit sampai" />
          <select value={q.stage} onChange={(e) => upd('stage', e.target.value)}>
            <option value="NEW">Belum diproses</option><option value="ALL">Semua</option>
          </select>
        </div>
        <div className="table-wrap"><table>
          <thead><tr><th className="chk-cell"><input type="checkbox" checked={selectable.length > 0 && sel.size === selectable.length}
            onChange={(e) => setSel(e.target.checked ? new Set(selectable.map((a) => a.id)) : new Set())} /></th>
            <th>Judul</th><th>Liputan</th><th>Popularitas</th><th>AI</th><th>Skor akhir</th><th>Status</th></tr></thead>
          <tbody>
            {data.items.length === 0 && <tr><td colSpan={7} className="empty">Belum ada artikel di sini. Jalankan Research RRS dulu.</td></tr>}
            {data.items.map((a) => (
              <tr key={a.id}>
                <td className="chk-cell">{a.stage === 'NEW' && <input type="checkbox" checked={sel.has(a.id)} onChange={() => toggle(a.id)} />}</td>
                <td><span className="article-title">{a.title}</span>
                  <small>{a.source} · {a.published_date || ''}</small>
                  <a href={a.url} target="_blank" rel="noreferrer"><ExternalLink size={10} /> buka sumber</a></td>
                <td><Score value={a.coverage_count} sub={`${a.unique_source_count || 0} media`} /></td>
                <td><Score value={a.popularity_score} /></td>
                <td title={a.ai_reason || ''}><Score value={a.ai_score} sub={a.ai_reason ? a.ai_reason.slice(0, 22) : ''} /></td>
                <td><Score value={a.overall_score} /></td>
                <td><StageBadge stage={a.stage} /></td>
              </tr>
            ))}
          </tbody>
        </table></div>
        <Pager page={data.page || 1} limit={data.limit} total={data.total} onPage={(p) => upd('page', p)} />
        <div className="sticky-actions"><span className="muted">{sel.size} berita dipilih</span>
          <button className="btn primary" disabled={!sel.size} onClick={addToQueue}><ListPlus size={14} /> Masukkan ke Production Queue</button></div>
      </div>
    </>
  );
}

export function Queue({ go, onError }) {
  const [items, setItems] = useState([]);
  const [sel, setSel] = useState(new Set());
  const [dur, setDur] = useState(60);
  const [manual, setManual] = useState(null);
  const [text, setText] = useState('');
  const load = () => api('/queue').then((d) => setItems(d.items)).catch((e) => onError(e.message));
  const hook = useJob('write', () => { setSel(new Set()); load(); });
  useEffect(() => { load(); }, []);
  const toggle = (id) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const waiting = items.filter((i) => i.stage === 'QUEUED');
  const write = () => hook.start({ storyIds: [...sel], durationSeconds: dur }).catch((e) => onError(e.message));
  const remove = (id) => api(`/queue/${id}`, { method: 'DELETE' }).then(load).catch((e) => onError(e.message));
  const saveManual = async () => {
    try { await api(`/stories/${manual.story_id}/content`, { method: 'PUT', body: { content: text } }); setManual(null); setText(''); load(); }
    catch (e) { onError(e.message); }
  };
  const csLabel = { OK: ['green', 'Isi artikel OK'], FAILED: ['red', 'Isi gagal diambil'], MANUAL: ['blue', 'Isi manual'] };
  return (
    <>
      <div className="page-heading"><div><div className="eyebrow">PRODUCTION QUEUE</div><h1>Antrean naskah</h1>
        <p>Centang berita lalu AI menulis naskah dari isi artikel asli (tanpa menambah fakta). Hasilnya ada di Story Writer.</p></div>
        <button className="btn secondary" onClick={() => go('gallery')}><ListPlus size={14} /> Tambah dari Gallery</button></div>
      <JobPanel title="Menulis naskah" hook={hook} />
      <div className="card library-card">
        <div className="table-wrap"><table>
          <thead><tr><th className="chk-cell"><input type="checkbox" checked={waiting.length > 0 && sel.size === waiting.length}
            onChange={(e) => setSel(e.target.checked ? new Set(waiting.map((i) => i.story_id)) : new Set())} /></th>
            <th>Berita</th><th>Skor</th><th>Isi artikel</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {items.length === 0 && <tr><td colSpan={6} className="empty">Antrean kosong. Pilih berita di Artikel Gallery.</td></tr>}
            {items.map((i) => {
              const cs = csLabel[i.content_status];
              return (
                <tr key={i.story_id}>
                  <td className="chk-cell">{i.stage === 'QUEUED' && <input type="checkbox" checked={sel.has(i.story_id)} onChange={() => toggle(i.story_id)} />}</td>
                  <td><span className="article-title">{i.title}</span><small>{i.source}</small></td>
                  <td><Score value={i.overall_score} /></td>
                  <td>{cs ? <span className={`badge ${cs[0]}`}>{cs[1]}</span> : <span className="muted">diambil saat menulis</span>}</td>
                  <td><StageBadge stage={i.stage} /></td>
                  <td><div className="row-actions">
                    {i.stage === 'QUEUED' && <>
                      <button className="btn secondary tiny" onClick={() => { setManual(i); setText(''); }}><PenLine size={11} /> Isi manual</button>
                      <button className="btn secondary tiny" onClick={() => remove(i.story_id)}><Trash2 size={11} /></button></>}
                    {i.stage !== 'QUEUED' && i.stage !== 'NEW' && <button className="btn secondary tiny" onClick={() => go('writer')}>Buka naskah</button>}
                  </div></td>
                </tr>
              );
            })}
          </tbody>
        </table></div>
        <div className="sticky-actions">
          <span className="muted">{sel.size} dipilih</span>
          <div className="row-actions">
            <select value={dur} onChange={(e) => setDur(+e.target.value)}>
              {[30, 45, 60, 75, 90].map((s) => <option key={s} value={s}>Target {s} detik</option>)}
            </select>
            <button className="btn primary" disabled={!sel.size || hook.running} onClick={write}><PenLine size={14} /> Tulis naskah dengan AI</button>
          </div>
        </div>
      </div>
      {manual && (
        <div className="modal-backdrop" onClick={() => setManual(null)}>
          <div className="card modal form-card" onClick={(e) => e.stopPropagation()}>
            <div className="card-heading"><div><h3>Tempel isi artikel</h3><p>{manual.title}</p></div></div>
            <p className="hint">Dipakai bila isi artikel tidak bisa diambil otomatis. Buka link sumber, salin teks beritanya, tempel di sini (min. 200 huruf).</p>
            <textarea rows={12} value={text} onChange={(e) => setText(e.target.value)} />
            <div className="modal-actions">
              <button className="btn secondary" onClick={() => setManual(null)}>Batal</button>
              <button className="btn primary" disabled={text.trim().length < 200} onClick={saveManual}>Simpan isi</button></div>
          </div>
        </div>
      )}
    </>
  );
}
