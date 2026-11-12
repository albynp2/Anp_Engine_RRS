import React, { useEffect, useMemo, useState } from 'react';
import { Download, Film, Trash2 } from 'lucide-react';
import { api } from '../ui.jsx';

export function Album({ onError }) {
  const [videos, setVideos] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    api('/videos').then((d) => setVideos(d.items.filter((v) => v.status === 'DONE'))).catch((e) => onError(e.message)).finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  const groups = useMemo(() => {
    const map = new Map();
    videos.forEach((v) => {
      const key = v.story_id;
      if (!map.has(key)) map.set(key, { storyId: key, title: v.title || `Berita #${key}`, videos: [] });
      map.get(key).videos.push(v);
    });
    return [...map.values()];
  }, [videos]);

  const del = (v) => {
    if (!confirm('Hapus video ini dari Album?')) return;
    api(`/videos/${v.id}`, { method: 'DELETE' }).then(load).catch((e) => onError(e.message));
  };

  return (
    <>
      <div className="page-heading">
        <div><div className="eyebrow">ALBUM</div><h1>Album Video</h1>
          <p>Kumpulan video yang sudah selesai digenerate, dikelompokkan berdasarkan judul berita.</p></div>
      </div>
      {loading && <div className="muted">Memuat album…</div>}
      {!loading && groups.length === 0 && <div className="card empty-small">Belum ada video yang selesai digenerate.</div>}
      <div style={{ display: 'grid', gap: 18 }}>
        {groups.map((g) => (
          <section className="card form-card" key={g.storyId}>
            <div className="card-heading">
              <div><h3>{g.title}</h3><p>{g.videos.length} video · Story #{g.storyId}</p></div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 14 }}>
              {g.videos.map((v) => (
                <div className="video-card" key={v.id} style={{ display: 'block' }}>
                  <video src={`/media/outputs/${v.path}`} controls preload="metadata" style={{ width: '100%', maxHeight: 420 }} />
                  <div style={{ paddingTop: 8 }}>
                    <div className="tag-row">
                      <span className="badge blue">{v.platform}</span>
                      {v.character_name && <span className="badge">{v.character_name}</span>}
                      {v.duration && <span className="badge">{Math.round(v.duration)} dtk</span>}
                    </div>
                    <div className="row-actions" style={{ marginTop: 8 }}>
                      <a className="btn secondary tiny" href={`/media/outputs/${v.path}`} download><Download size={11} /> Unduh</a>
                      <button className="btn secondary tiny" onClick={() => del(v)}><Trash2 size={11} /> Hapus</button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
    </>
  );
}
