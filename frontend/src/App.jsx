import React, { useEffect, useState } from 'react';
import { BarChart3, Clapperboard, FileText, Images, ListChecks, Search, Settings as Cog, Skull, Film } from 'lucide-react';
import { api, ErrorModal } from './ui.jsx';
import { Dashboard, Research } from './pages/DashboardResearch.jsx';
import { Gallery, Queue } from './pages/GalleryQueue.jsx';
import { StoryWriter } from './pages/StoryWriter.jsx';
import { ContentManagement } from './pages/ContentManagement.jsx';
import { Settings } from './pages/Settings.jsx';
import { Album } from './pages/Album.jsx';

const NAV = [
  ['dashboard', 'Dashboard', BarChart3],
  ['research', 'Research RRS', Search],
  ['gallery', 'Artikel Gallery', Images],
  ['queue', 'Production Queue', ListChecks],
  ['writer', 'Story Writer', FileText],
  ['content', 'Content Management', Clapperboard],
  ['album', 'Album', Film],
  ['settings', 'Settings', Cog],
];

export default function App() {
  const [page, setPage] = useState(() => (location.hash.slice(1) || 'dashboard'));
  const [error, setError] = useState('');
  const [health, setHealth] = useState(null);
  const go = (p) => { setPage(p); location.hash = p; window.scrollTo(0, 0); };

  useEffect(() => {
    const t = () => api('/health').then(setHealth).catch(() => setHealth(null));
    t();
    const i = setInterval(t, 20000);
    const onHash = () => setPage(location.hash.slice(1) || 'dashboard');
    window.addEventListener('hashchange', onHash);
    return () => { clearInterval(i); window.removeEventListener('hashchange', onHash); };
  }, []);

  const props = { go, onError: setError };
  const view = {
    dashboard: <Dashboard {...props} />, research: <Research {...props} />, gallery: <Gallery {...props} />,
    queue: <Queue {...props} />, writer: <StoryWriter {...props} />, content: <ContentManagement {...props} />, album: <Album {...props} />,
    settings: <Settings {...props} />,
  }[page] || <Dashboard {...props} />;
  const label = (NAV.find((n) => n[0] === page) || NAV[0])[1];

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand"><div className="brand-mark"><Skull size={22} /></div>
          <div><b>RRS</b><strong>ENGINE</strong><small>NEWS → SCRIPT → VIDEO</small></div></div>
        <nav>
          {NAV.map(([id, text, Icon]) => (
            <button key={id} className={`nav-item ${page === id ? 'active' : ''}`} onClick={() => go(id)}>
              <Icon size={16} /><span>{text}</span></button>))}
        </nav>
        <div className="side-bottom">
          <div className="sys-mini">
            <div className="sys-head"><span>Sistem</span></div>
            <div><i className={`dot ${health ? 'green' : 'red'}`} /> Server <b>{health ? 'online' : 'offline'}</b></div>
            <div><i className={`dot ${health && health.openai ? 'green' : 'red'}`} /> OpenAI <b>{health && health.openai ? 'siap' : 'belum'}</b></div>
            <div><i className={`dot ${health && health.ffmpeg ? 'green' : 'red'}`} /> FFmpeg <b>{health && health.ffmpeg ? 'siap' : 'tidak ada'}</b></div>
          </div>
          <span className="version">v3.0 · LOCAL DOCKER</span>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <div className="crumb"><span>RRS</span> / <b>{label}</b></div>
          <div className="top-actions"><div className="api-pill"><i className={`dot ${health ? 'green' : 'red'}`} />
            {health ? `${health.tz} · ${health.now.slice(11, 16)}` : 'server offline'}</div></div>
        </header>
        <main className="content">{view}</main>
      </div>
      <ErrorModal error={error} onClose={() => setError('')} />
    </div>
  );
}
