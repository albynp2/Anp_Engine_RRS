'''JSON-line worker used by the local Node.js API. Never print secrets.'''
import sys, json, traceback
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from database.database import create_database, get_connection, save_story, get_story_status, get_story_id_by_url, queue_selected_topic, get_queue_items, save_generated_story, mark_queue_status, story_already_written

import sys
from contextlib import redirect_stdout

# Simpan stdout asli untuk komunikasi JSON dengan Node.js.
PROTOCOL_STDOUT = sys.stdout

# Hindari crash ketika terminal Windows menerima karakter Unicode.
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(
        encoding="utf-8",
        errors="replace"
    )

def emit(kind, **kwargs):
    message = {
        "type": kind,
        **kwargs
    }

    # ASCII JSON aman untuk encoding terminal Windows.
    print(
        json.dumps(message, ensure_ascii=True),
        file=PROTOCOL_STDOUT,
        flush=True
    )

def query_all(sql, params=()):
    conn=get_connection(); conn.row_factory=__import__('sqlite3').Row
    try: return [dict(r) for r in conn.execute(sql,params).fetchall()]
    finally: conn.close()

def run_research(cfg):
    from datetime import datetime
    from email.utils import parsedate_to_datetime
    from research.researcher import search_google_news
    from research.popularity import analyze_popularity
    from ai.scorer import score_stories
    queries=[str(x).strip() for x in cfg.get('queries',[]) if str(x).strip()]
    excludes=[str(x).strip().lower() for x in cfg.get('excludedKeywords',[]) if str(x).strip()]
    if not queries: raise ValueError('Tambahkan minimal satu query RSS.')
    today=datetime.now().strftime('%Y-%m-%d')
    if cfg.get('todayOnly'):
        start=end=today
    else:
        start=cfg.get('startDate') or datetime.now().strftime('%Y-%m-01')
        end=cfg.get('endDate') or today
    if start>end: raise ValueError('Tanggal mulai tidak boleh melewati tanggal akhir.')
    create_database(); all_items=[]
    for i,q in enumerate(queries,1):
        emit('progress',percent=int(5+25*i/len(queries)),stage=f'RSS {i}/{len(queries)}: {q}')
        try: all_items.extend(search_google_news(q,start,(datetime.strptime(end,'%Y-%m-%d').date().fromordinal(datetime.strptime(end,'%Y-%m-%d').date().toordinal()+1)).isoformat()))
        except Exception as e: emit('log',level='warning',message=f'Query gagal ({q}): {e}')
    emit('progress',percent=35,stage='Deduplication dan filter')
    dedup={}
    for item in all_items:
        url=item.get('url','').strip()
        if not url: continue
        title=(item.get('title') or '').lower()
        if any(k in title for k in excludes): continue
        pub=item.get('published','')
        try:
            dt=parsedate_to_datetime(pub).date()
            if not (datetime.strptime(start,'%Y-%m-%d').date() <= dt <= datetime.strptime(end,'%Y-%m-%d').date()): continue
        except Exception: continue
        dedup[url]=item
    filtered=list(dedup.values())
    emit('log',message=f'{len(all_items)} hasil mentah; {len(filtered)} lolos filter/dedup.')
    emit('progress',percent=48,stage='Analisis popularitas lokal (TF-IDF/clustering)')
    ranked=analyze_popularity(filtered) if filtered else []
    emit('progress',percent=62,stage='Menyimpan artikel ke SQLite')
    new_count=0
    for item in filtered:
        if get_story_status(item['url']) is None: save_story(item); new_count+=1
    emit('log',message=f'{new_count} artikel baru disimpan; {len(filtered)-new_count} sudah ada.')
    limit=max(1,min(int(cfg.get('topCandidates',30)),50))
    candidates=[]
    for topic in ranked[:limit]:
        candidates.append({k:topic.get(k) for k in ['title','url','source','published','popularity_score','coverage_count','unique_source_count','query_count']})
    if not candidates:
        emit('progress',percent=100,stage='Selesai: tidak ada kandidat yang lolos')
        return {'rawCount':len(all_items),'filteredCount':len(filtered),'newCount':new_count,'scoredCount':0,'queuedCount':0,'mode':'local-only' if cfg.get('localOnly') else 'ai-scoring'}
    if cfg.get('localOnly'):
        emit('log',level='info',message=f'Mode hemat token aktif: {len(candidates)} kandidat dianalisis lokal; OpenAI scoring dilewati.')
        emit('progress',percent=100,stage='Riset lokal selesai — OpenAI tidak dipanggil')
        return {'rawCount':len(all_items),'filteredCount':len(filtered),'newCount':new_count,'scoredCount':0,'queuedCount':0,'localCandidates':len(candidates),'mode':'local-only'}
    emit('progress',percent=72,stage=f'AI scoring {len(candidates)} kandidat')
    scored=score_stories(candidates)
    top=scored.get('top_10',[])
    queued=0
    for rank,item in enumerate(top,1):
        try: idx=int(item.get('id',0))-1
        except Exception: continue
        if idx<0 or idx>=len(candidates): continue
        topic=candidates[idx]; sid=get_story_id_by_url(topic['url'])
        if sid is None: continue
        if queue_selected_topic(sid,rank,topic.get('popularity_score',0),item.get('overall_score',0)): queued+=1
    emit('progress',percent=100,stage='Research dan AI scoring selesai')
    return {'rawCount':len(all_items),'filteredCount':len(filtered),'newCount':new_count,'scoredCount':len(top),'queuedCount':queued}

def run_generate(cfg):
    from research.writer import generate_story
    story_id=int(cfg['storyId'])
    rows=query_all('''SELECT q.id queue_id,q.story_id,q.rank,q.research_popularity,q.overall_score,s.title,s.url,s.source,s.published FROM production_queue q JOIN stories s ON s.id=q.story_id WHERE q.story_id=? ORDER BY q.id DESC LIMIT 1''',(story_id,))
    if not rows: raise ValueError('Artikel belum ada di production queue. Masukkan ke antrean dulu.')
    story=rows[0]
    if story_already_written(story_id): raise ValueError('Artikel ini sudah memiliki naskah. Cek Story Library.')
    emit('progress',percent=15,stage='Menyiapkan konteks artikel')
    emit('progress',percent=30,stage='Memanggil OpenAI untuk membuat narasi')
    result=generate_story(story)
    emit('progress',percent=85,stage='Menyimpan hasil narasi ke database')
    save_generated_story(story_id,result); mark_queue_status(story['queue_id'],'WRITTEN')
    emit('progress',percent=100,stage='Narasi berhasil dibuat')
    return {'storyId':story_id,'title':result.get('title',''),'result':result}

def run_action(action,cfg):
    create_database()
    if action=='dashboard':
        counts={r['status']:r['n'] for r in query_all('SELECT status,COUNT(*) n FROM stories GROUP BY status')}
        queue={r['status']:r['n'] for r in query_all('SELECT status,COUNT(*) n FROM production_queue GROUP BY status')}
        queue_total=query_all('SELECT COUNT(*) n FROM production_queue')[0]['n']
        total=query_all('SELECT COUNT(*) n FROM stories')[0]['n']
        written=query_all('SELECT COUNT(*) n FROM generated_stories')[0]['n']
        # Real activity: number of stories first saved to SQLite per day, last 14 days.
        # Fill missing dates with zero so the chart is continuous and never uses demo values.
        from datetime import date, timedelta
        activity_rows = query_all("""
            SELECT date(created_at) AS day, COUNT(*) AS articles
            FROM stories
            WHERE date(created_at) >= date('now', '-13 days')
              AND date(created_at) <= date('now')
            GROUP BY date(created_at)
            ORDER BY day
        """)
        activity_map = {r['day']: int(r['articles']) for r in activity_rows if r.get('day')}
        today = date.today()
        research_activity = [
            {'day': (today - timedelta(days=offset)).isoformat(),
             'articles': activity_map.get((today - timedelta(days=offset)).isoformat(), 0)}
            for offset in range(13, -1, -1)
        ]
        return {'totalArticles':total,'queueTotal':queue_total,'written':written,'storyStatuses':counts,'queueStatuses':queue,'researchActivity':research_activity,'recentArticles':query_all('SELECT s.id,s.title,s.url,s.source,s.published,s.status,q.status queue_status,q.overall_score FROM stories s LEFT JOIN production_queue q ON q.story_id=s.id ORDER BY s.id DESC LIMIT 8'),'recentScripts':query_all('SELECT g.id,g.story_id,g.title,g.created_at,s.title source_title FROM generated_stories g JOIN stories s ON s.id=g.story_id ORDER BY g.id DESC LIMIT 5')}
    if action=='articles':
        page=max(1,int(cfg.get('page',1))); limit=min(100,max(10,int(cfg.get('limit',25)))); offset=(page-1)*limit
        search=f"%{cfg.get('search','').strip()}%"; status=cfg.get('status','ALL')
        where='WHERE (s.title LIKE ? OR s.source LIKE ? OR s.url LIKE ?)'; params=[search,search,search]
        if status!='ALL': where+=' AND COALESCE(q.status,s.status)=?'; params.append(status)
        total=query_all(f'SELECT COUNT(*) n FROM stories s {where}',params)[0]['n']
        rows=query_all(f'''SELECT s.id,s.title,s.url,s.source,s.published,s.status,q.status queue_status,q.rank,q.overall_score,CASE WHEN g.id IS NULL THEN 0 ELSE 1 END has_script FROM stories s LEFT JOIN production_queue q ON q.story_id=s.id LEFT JOIN generated_stories g ON g.story_id=s.id {where} ORDER BY s.id DESC LIMIT ? OFFSET ?''',params+[limit,offset])
        return {'items':rows,'total':total,'page':page,'limit':limit}
    if action=='queue':
        status=cfg.get('status','ALL')
        where=''; params=[]
        if status!='ALL': where='WHERE q.status=?'; params=[status]
        return {'items':query_all(f'''SELECT q.id queue_id,q.story_id,q.rank,q.research_popularity,q.overall_score,q.status queue_status,s.title,s.url,s.source,s.published,CASE WHEN g.id IS NULL THEN 0 ELSE 1 END has_script FROM production_queue q JOIN stories s ON s.id=q.story_id LEFT JOIN generated_stories g ON g.story_id=s.id {where} ORDER BY q.rank,q.id DESC LIMIT 300''',params)}
    if action=='scripts': return {'items':query_all('SELECT g.*,s.url,s.source,s.published FROM generated_stories g JOIN stories s ON s.id=g.story_id ORDER BY g.id DESC LIMIT 300')}
    if action=='select_articles':
        ids=[int(x) for x in cfg.get('ids',[])]; inserted=0
        for rank,sid in enumerate(ids,1):
            rows=query_all('SELECT id FROM stories WHERE id=?',(sid,))
            if rows and queue_selected_topic(sid,rank,0,0): inserted+=1
        return {'inserted':inserted,'requested':len(ids)}
    if action=='set_queue_status':
        qid=int(cfg['queueId']); status=str(cfg['status']).upper()
        if status not in {'SELECTED','WRITTEN','RENDERED','PUBLISHED','FAILED'}: raise ValueError('Status tidak valid.')
        from database.database import mark_queue_status
        mark_queue_status(qid,status); return {'queueId':qid,'status':status}
    if action=='research': return run_research(cfg)
    if action=='generate': return run_generate(cfg)
    if action=='system':
        import os
        return {'databasePath':str((ROOT/'database'/'horror.db').resolve()),'databaseExists':(ROOT/'database'/'horror.db').exists(),'apiKeyConfigured':bool(os.getenv('OPENAI_API_KEY')),'projectRoot':str(ROOT)}
    raise ValueError(f'Action tidak dikenal: {action}')

if __name__=='__main__':
    try:
        payload=json.loads(sys.stdin.read() or '{}')
        result=run_action(payload.get('action',''),payload.get('config',{}))
        emit('result',data=result)
    except Exception as exc:
        emit('error',message=str(exc),traceback=traceback.format_exc())
        sys.exit(1)
