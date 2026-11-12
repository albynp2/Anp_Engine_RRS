import React, { useEffect, useState } from 'react';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { CheckCircle2, FileText, Film, Loader2, Newspaper, Search, Send } from 'lucide-react';
import { api, JobPanel, Score, StageBadge, STAGE_LABEL, useConfig, useJob } from '../ui.jsx';

const Stat = ({ icon: I, tone, label, value, sub }) => (
  <div className="card stat">
    <div className={`stat-icon ${tone}`}><I size={18} /></div>
    <div className="stat-copy"><span>{label}</span><strong>{value}</strong><small>{sub}</small></div>
  </div>
);

export function Dashboard({ go, onError }) {
  const [d, setD] = useState(null);
  useEffect(() => {
    const load = () => api('/dashboard').then(setD).catch((e) => onError(e.message));
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, []);
  if (!d) return <div className="muted">Memuat dashboard…</div>;
  const t = d.totals;
  const chart = d.activity.map((a) => ({ ...a, label: a.day.slice(5) }));
  const stages = ['NEW', 'QUEUED', 'WRITTEN', 'RENDERING', 'RENDERED', 'PUBLISHED'];
  const maxStage = Math.max(1, ...stages.map((s) => t.stages[s] || 0));
  return (
    <>
      <div className="page-heading">
        <div><div className="eyebrow">LAPORAN KONTEN</div><h1>Dashboard</h1>
          <p>Data langsung dari database · zona waktu WIB · {d.today}</p></div>
        <button className="btn primary" onClick={() => go('research')}><Search size={14} /> Riset berita baru</button>
      </div>
      <div className="stats-grid">
        <Stat icon={Newspaper} tone="red" label="Total artikel" value={t.articles} sub={`${t.stages.NEW} belum diproses`} />
        <Stat icon={FileText} tone="purple" label="Naskah ditulis" value={t.scriptsWritten} sub="tersimpan di Story Writer" />
        <Stat icon={Film} tone="blue" label="Video jadi" value={t.videosDone} sub="sudah dirender" />
        <Stat icon={Send} tone="green" label="Published" value={t.published} sub="ditandai terbit" />
        <Stat icon={Loader2} tone="orange" label="Masih proses" value={t.inProgress} sub="antre / naskah / render" />
      </div>
      <div className="dashboard-grid">
        <div className="card chart-card">
          <div className="card-heading"><div><h3>Aktivitas 14 hari terakhir</h3><p>Artikel masuk, naskah ditulis, dan video published per hari</p></div></div>
          <div className="chart">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chart}>
                <CartesianGrid stroke="#1d2935" vertical={false} />
                <XAxis dataKey="label" stroke="#6f8093" fontSize={10} />
                <YAxis allowDecimals={false} stroke="#6f8093" fontSize={10} width={28} />
                <Tooltip contentStyle={{ background: '#0b121b', border: '1px solid #293846', fontSize: 11 }} />
                <Area type="monotone" dataKey="articles" name="Artikel" stroke="#f04452" fill="#f0445233" />
                <Area type="monotone" dataKey="scripts" name="Naskah" stroke="#b783ff" fill="#b783ff22" />
                <Area type="monotone" dataKey="published" name="Published" stroke="#4bd6a3" fill="#4bd6a322" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <div className="chart-foot">
            <span><i className="legend red-bg" />Artikel</span>
            <span><i className="legend" style={{ background: '#b783ff' }} />Naskah</span>
            <span><i className="legend" style={{ background: '#4bd6a3' }} />Published</span>
          </div>
        </div>
        <div className="card status-card">
          <div className="card-heading"><div><h3>Status konten</h3><p>Posisi tiap artikel di pipeline</p></div></div>
          {stages.map((s, i) => (
            <div className="status-row" key={s}>
              <div><i className={`status-dot s${i}`} />{STAGE_LABEL[s]}</div><b>{t.stages[s] || 0}</b>
              <div className="mini-track"><span style={{ width: `${((t.stages[s] || 0) / maxStage) * 100}%` }} /></div>
            </div>
          ))}
        </div>
      </div>
      <div className="card" style={{ padding: 18 }}>
        <div className="card-heading"><div><h3>Artikel terbaru</h3><p>8 artikel terakhir masuk ke database</p></div>
          <button className="text-btn" onClick={() => go('gallery')}>Lihat semua</button></div>
        <div className="table-wrap"><table>
          <thead><tr><th>Judul</th><th>Media</th><th>Skor</th><th>Status</th><th>Masuk</th></tr></thead>
          <tbody>
            {d.recent.length === 0 && <tr><td colSpan={5} className="empty">Belum ada artikel. Mulai dari menu Research RRS.</td></tr>}
            {d.recent.map((r) => (
              <tr key={r.id}><td><span className="article-title">{r.title}</span></td><td>{r.source}</td>
                <td><Score value={r.overall_score} /></td><td><StageBadge stage={r.stage} /></td><td>{r.created_local}</td></tr>
            ))}
          </tbody>
        </table></div>
      </div>
    </>
  );
}

export function Research({ go, onError }) {
  const cfg = useConfig();
  const [f, setF] = useState({ mode: 'horror', query: '', todayOnly: false, startDate: '', endDate: '', exclude: '', maxCandidates: 15, useAI: true });
  const [excludeTouched, setTouched] = useState(false);
  const hook = useJob('research');
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));

  useEffect(() => {  // isi default exclude hanya untuk mode horor, kosong untuk input sendiri
    if (!cfg || excludeTouched) return;
    set('exclude', f.mode === 'horror' ? cfg.horrorExclude.join(', ') : '');
  }, [cfg, f.mode]);

  const run = () => hook.start(f).catch((e) => onError(e.message));
  const res = hook.job && hook.job.status === 'completed' ? hook.job.result : null;
  const noDates = !f.todayOnly && !f.startDate && !f.endDate;
  return (
    <>
      <div className="page-heading"><div><div className="eyebrow">RESEARCH RRS</div><h1>Cari berita viral</h1>
        <p>Berita asli dari Google News · dinilai berdasarkan banyaknya media yang meliput</p></div></div>
      <div className="two-col">
        <div className="card form-card">
          <label>Mode pencarian</label>
          <div className="radio-cards">
            <div className={`radio-card ${f.mode === 'horror' ? 'on' : ''}`} onClick={() => { set('mode', 'horror'); setTouched(false); }}>
              <b>Horor · Pembunuhan · Kriminal</b><small>Kata kunci sudah diatur otomatis ({cfg ? cfg.horrorQueries.length : 8} pencarian).</small></div>
            <div className={`radio-card ${f.mode === 'custom' ? 'on' : ''}`} onClick={() => { set('mode', 'custom'); setTouched(false); }}>
              <b>Input sendiri</b><small>Cari topik apa pun sesuai kata kunci yang lu tulis.</small></div>
          </div>
          {f.mode === 'custom' && (<>
            <label>Kata kunci <span>satu baris = satu pencarian (maks 6)</span></label>
            <textarea rows={3} value={f.query} onChange={(e) => set('query', e.target.value)} placeholder="kisah horor indonesia hari ini viral" />
          </>)}
          <label className="check-label"><input type="checkbox" checked={f.todayOnly} onChange={(e) => set('todayOnly', e.target.checked)} />
            Hari ini saja<span>Kalau dicentang, tanggal di bawah diabaikan.</span></label>
          <div className="form-row">
            <div><label>Tanggal mulai</label><input type="date" disabled={f.todayOnly} value={f.startDate} onChange={(e) => set('startDate', e.target.value)} /></div>
            <div><label>Tanggal akhir</label><input type="date" disabled={f.todayOnly} value={f.endDate} onChange={(e) => set('endDate', e.target.value)} /></div>
          </div>
          <p className="hint">{f.todayOnly || noDates ? 'Rentang: hari ini (WIB).' : 'Rentang sesuai tanggal yang dipilih (WIB). Kosong salah satu = dilengkapi otomatis.'}</p>
          <label>Exclude <span>kata yang dibuang dari judul · boleh dikosongkan</span></label>
          <textarea rows={2} value={f.exclude} onChange={(e) => { setTouched(true); set('exclude', e.target.value); }} placeholder="film, trailer, netflix" />
          <label>Maksimum kandidat AI <span>{f.maxCandidates} berita</span></label>
          <input type="range" min={5} max={40} value={f.maxCandidates} onChange={(e) => set('maxCandidates', +e.target.value)} />
          <div className="range-meta"><span>Hemat token</span><span>Lebih banyak pilihan</span></div>
          <label className="check-label"><input type="checkbox" checked={f.useAI} onChange={(e) => set('useAI', e.target.checked)} />
            Nilai dengan AI<span>1 request ringkas untuk semua kandidat. Dimatikan = skor hanya dari popularitas.</span></label>
          <button className="btn primary full" disabled={hook.running} onClick={run}><Search size={14} /> {hook.running ? 'Sedang mencari…' : 'Mulai riset'}</button>
        </div>
        <div className="card pipeline-card">
          <div className="card-heading"><div><h3>Cara kerja skor</h3><p>Transparan, bisa dicek</p></div></div>
          {[['1', 'Kumpulkan', 'Berita dari beberapa pencarian, difilter tanggal & exclude, duplikat dibuang.'],
            ['2', 'Popularitas', 'Berita yang sama dikelompokkan. Makin banyak artikel & media berbeda yang meliput, makin tinggi.'],
            ['3', 'Penilaian AI', 'Hanya kandidat teratas dikirim ke AI (judul singkat saja) untuk menilai kecocokan & potensi.'],
            ['4', 'Skor akhir', '55% popularitas + 45% AI. Gallery diurutkan dari skor tertinggi.']].map(([n, b, s]) => (
            <div className="pipeline-step" key={n}><div className="step-number">{n}</div><div><b>{b}</b><small>{s}</small></div></div>))}
          <p className="hint">Catatan: jumlah pengunjung per berita tidak tersedia dari sumber gratis, jadi indikatornya adalah banyaknya media yang meliput kejadian yang sama.</p>
        </div>
      </div>
      <div style={{ marginTop: 16 }}><JobPanel title="Riset berita" hook={hook} /></div>
      {res && (
        <div className="card form-card" style={{ marginTop: 14 }}>
          <div className="card-heading"><div><h3><CheckCircle2 size={15} className="accent" /> Hasil riset</h3>
            <p>{res.message || `${res.found} berita ditemukan → ${res.topics} topik → ${res.saved} masuk gallery (${res.newArticles} baru, ${res.rejectedByAI} ditolak AI)`}</p></div>
            <button className="btn primary" onClick={() => go('gallery')}>Buka Gallery</button></div>
        </div>
      )}
    </>
  );
}
