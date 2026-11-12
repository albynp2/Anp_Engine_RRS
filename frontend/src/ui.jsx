import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, Loader2, X } from 'lucide-react';

export async function api(path, { method = 'GET', body } = {}) {
  const isForm = typeof FormData !== 'undefined' && body instanceof FormData;
  const res = await fetch('/api' + path, {
    method,
    headers: body && !isForm ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? (isForm ? body : JSON.stringify(body)) : undefined,
  });
  const ct = res.headers.get('content-type') || '';
  const data = ct.includes('json') ? await res.json().catch(() => null) : await res.blob();
  if (!res.ok) throw new Error((data && data.error) || `Permintaan gagal (${res.status})`);
  return data;
}

export const STAGE_LABEL = {
  NEW: 'Baru', QUEUED: 'Antre', WRITTEN: 'Naskah siap', RENDERING: 'Render…',
  RENDERED: 'Video jadi', PUBLISHED: 'Published',
};
export const EMOTION_LABEL = {
  neutral: 'Netral', serious: 'Serius', sad: 'Sedih', angry: 'Marah',
  scared: 'Takut', surprised: 'Kaget', happy: 'Senang',
};

export const StageBadge = ({ stage }) => (
  <span className={`badge stage-${stage}`}>{STAGE_LABEL[stage] || stage}</span>
);

export const Score = ({ value, sub }) => (
  <span className="score">{value == null ? '–' : Number(value).toFixed(1)}{sub && <small>{sub}</small>}</span>
);

export function ErrorModal({ error, onClose }) {
  if (!error) return null;
  return (
    <div className="modal-backdrop error-backdrop" onClick={onClose}>
      <div className="card modal error-modal" onClick={(e) => e.stopPropagation()}>
        <div className="card-heading"><h3><AlertTriangle size={17} /> Terjadi kesalahan</h3></div>
        <div className="error-message">{error}</div>
        <div className="modal-actions"><button className="btn primary" onClick={onClose}>Tutup</button></div>
      </div>
    </div>
  );
}

/** Menjalankan job di backend + progres via SSE. Job aktif dipulihkan saat halaman dibuka lagi. */
export function useJob(type, onDone) {
  const [job, setJob] = useState(null);
  const [logs, setLogs] = useState([]);
  const doneRef = useRef(onDone);
  doneRef.current = onDone;
  const esRef = useRef(null);

  const attach = useCallback((id) => {
    if (esRef.current) esRef.current.close();
    setJob({ id, type, status: 'running', progress: 0, stage: 'Mulai' });
    const es = new EventSource(`/api/jobs/${id}/events`);
    esRef.current = es;
    es.onmessage = (m) => {
      const e = JSON.parse(m.data);
      const time = new Date().toLocaleTimeString('id-ID');
      if (e.type === 'progress') setJob((j) => ({ ...j, progress: e.percent, stage: e.stage }));
      else if (e.type === 'log') setLogs((l) => [...l.slice(-300), { level: e.level, message: e.message, time }]);
      else if (e.type === 'error') setLogs((l) => [...l, { level: 'error', message: e.message, time }]);
      else if (e.type === 'complete') {
        setJob((j) => ({ ...j, status: e.status, progress: e.progress, result: e.result, error: e.error }));
        es.close();
        if (doneRef.current) doneRef.current(e);
      }
    };
    es.onerror = () => es.close();
  }, [type]);

  useEffect(() => {
    api('/jobs/active').then((a) => { if (a.id && a.type === type) attach(a.id); }).catch(() => {});
    return () => { if (esRef.current) esRef.current.close(); };
  }, [type, attach]);

  const start = async (payload) => {
    setLogs([]);
    const j = await api(`/jobs/${type}`, { method: 'POST', body: payload });
    attach(j.id);
  };
  const cancel = () => job && api(`/jobs/${job.id}/cancel`, { method: 'POST' }).catch(() => {});
  const running = !!job && (job.status === 'running' || job.status === 'queued');
  return { job, logs, start, cancel, running };
}

export function JobPanel({ title, hook }) {
  const { job, logs, cancel, running } = hook;
  if (!job) return null;
  const label = { running: 'Berjalan', queued: 'Antre', completed: 'Selesai', failed: 'Gagal', cancelled: 'Dibatalkan' }[job.status];
  return (
    <div className="card job-card">
      <div className="job-title">
        <div><span className={`badge ${job.status === 'completed' ? 'green' : job.status === 'failed' ? 'red' : 'orange'}`}>{label}</span>
          <h3>{title}</h3><p>{job.stage}</p></div>
        {running && <div className="job-controls"><Loader2 size={16} className="spin" />
          <button className="danger-small" onClick={cancel}><X size={13} /> Batalkan</button></div>}
      </div>
      <div className="progress-track"><div style={{ width: `${job.progress || 0}%` }} /></div>
      <div className="progress-meta"><b>{Math.round(job.progress || 0)}%</b><span>{job.stage}</span></div>
      {job.error && <div className="alert"><span>{job.error}</span></div>}
      {logs.length > 0 && (
        <div className="log-panel">
          <div className="log-head"><span>LOG</span><span>{logs.length} baris</span></div>
          <div style={{ maxHeight: 220, overflow: 'auto' }}>
            {logs.slice(-60).map((l, i) => (
              <div key={i} className={`log-line ${l.level}`}><time>{l.time}</time><span>{l.message}</span></div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function Pager({ page, limit, total, onPage }) {
  const pages = Math.max(1, Math.ceil(total / limit));
  return (
    <div className="pagination">
      <span>{total} artikel · halaman {page}/{pages}</span>
      <div>
        <button className="btn secondary tiny" disabled={page <= 1} onClick={() => onPage(page - 1)}>Sebelumnya</button>
        <button className="btn secondary tiny" disabled={page >= pages} onClick={() => onPage(page + 1)}>Berikutnya</button>
      </div>
    </div>
  );
}

export function useConfig() {
  const [cfg, setCfg] = useState(null);
  useEffect(() => { api('/config').then(setCfg).catch(() => {}); }, []);
  return cfg;
}
