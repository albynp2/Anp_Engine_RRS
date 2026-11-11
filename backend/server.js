import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import { spawn } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import crypto from 'node:crypto';
import fs from 'node:fs';

dotenv.config({ path: path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../.env') });
const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const WORKER = path.join(ROOT, 'python_engine', 'worker.py');
const PORT = Number(process.env.API_PORT || 3001);
const PYTHON = process.env.PYTHON_EXECUTABLE || 'python';
const app = express();
app.use(cors({ origin: ['http://localhost:5173', 'http://127.0.0.1:5173'] }));
app.use(express.json({ limit: '12mb' }));
const jobs = new Map();
let activeJob = null;

function sendEvent(job, event) {
  const payload = `data: ${JSON.stringify(event)}\n\n`;
  job.events.push(event);
  if (job.events.length > 500) job.events.shift();
  for (const res of job.clients) res.write(payload);
}
function startJob(action, config) {
  if (activeJob && jobs.get(activeJob)?.status === 'running') {
    const err = new Error('Masih ada proses yang berjalan. Tunggu sampai selesai.'); err.status = 409; throw err;
  }
  const id = crypto.randomUUID();
  const job = { id, action, status: 'running', progress: 0, stage: 'Menyiapkan proses', logs: [], events: [], clients: new Set(), startedAt: new Date().toISOString(), finishedAt: null, result: null, error: null };
  jobs.set(id, job); activeJob = id;
  sendEvent(job, { type: 'job', id, status: 'running', action });
  const child = spawn(PYTHON, ['-u', WORKER], { cwd: ROOT, env: { ...process.env, PYTHONUNBUFFERED: '1' }, windowsHide: true });
  job.child = child;
  let stdoutBuffer = '';
  child.stdin.write(JSON.stringify({ action, config })); child.stdin.end();
  child.stdout.setEncoding('utf8'); child.stdout.on('data', chunk => {
    stdoutBuffer += chunk;
    const lines = stdoutBuffer.split(/\r?\n/); stdoutBuffer = lines.pop() || '';
    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const evt = JSON.parse(line);
        if (evt.type === 'progress') { job.progress = Number(evt.percent || job.progress); job.stage = evt.stage || job.stage; }
        if (evt.type === 'log') job.logs.push({ time: new Date().toISOString(), level: evt.level || 'info', message: evt.message || '' });
        if (evt.type === 'error') { job.error = evt.message; job.logs.push({ time: new Date().toISOString(), level: 'error', message: evt.message }); }
        if (evt.type === 'result') job.result = evt.data;
        sendEvent(job, evt);
      } catch { job.logs.push({ time: new Date().toISOString(), level: 'info', message: line }); sendEvent(job, { type: 'log', message: line }); }
    }
  });
  child.stderr.setEncoding('utf8'); child.stderr.on('data', chunk => {
    const msg = chunk.trim(); if (!msg) return;
    // tqdm writes to stderr; forward it as progress detail/log instead of losing it.
    for (const line of msg.split(/\r?\n/).filter(Boolean)) {
      job.logs.push({ time: new Date().toISOString(), level: 'detail', message: line });
      sendEvent(job, { type: 'log', level: 'detail', message: line });
    }
  });
  child.on('error', err => {
    job.status = 'failed'; job.error = `Gagal menjalankan Python (${PYTHON}): ${err.message}`; job.finishedAt = new Date().toISOString();
    sendEvent(job, { type: 'error', message: job.error }); sendEvent(job, { type: 'complete', status: job.status, error: job.error }); if (activeJob === id) activeJob = null;
  });
  child.on('close', code => {
    if (stdoutBuffer.trim()) { try { const evt=JSON.parse(stdoutBuffer); if(evt.type==='result')job.result=evt.data; sendEvent(job,evt); } catch {} }
    if (job.status === 'cancelling') job.status = 'cancelled';
    else job.status = code === 0 && !job.error ? 'completed' : 'failed';
    if (job.status === 'completed') job.progress = 100;
    if (job.status === 'failed' && !job.error) { job.error = `Python worker berhenti dengan exit code ${code}.`; sendEvent(job, { type: 'error', message: job.error, traceback: job.logs.slice(-30).map(x => x.message).join('\n') }); }
    job.finishedAt = new Date().toISOString();
    sendEvent(job, { type: 'complete', status: job.status, progress: job.progress, result: job.result, error: job.error });
    for (const res of job.clients) res.end(); job.clients.clear(); if (activeJob === id) activeJob = null;
  });
  return { id, action, status: job.status };
}
function pythonRead(action, config={}) {
  return new Promise((resolve,reject)=>{
    const child=spawn(PYTHON,['-u',WORKER],{cwd:ROOT,env:{...process.env,PYTHONUNBUFFERED:'1'},windowsHide:true});
    let stdout='',stderr=''; child.stdout.setEncoding('utf8'); child.stderr.setEncoding('utf8');
    child.stdout.on('data',x=>stdout+=x); child.stderr.on('data',x=>stderr+=x);
    child.on('error',reject); child.on('close',code=>{
      const lines=stdout.trim().split(/\r?\n/); let last=null;
      for(const line of lines){try{const e=JSON.parse(line);if(e.type==='result')last=e.data;if(e.type==='error'){const er=new Error(e.message);er.details=e.traceback;return reject(er)}}catch{}}
      if(code!==0 || last===null) return reject(new Error(stderr || 'Python worker gagal. Pastikan dependency terpasang.'));
      resolve(last);
    });
    child.stdin.end(JSON.stringify({action,config}));
  });
}
app.get('/api/health', async (_req,res)=>{ try { const data=await pythonRead('system'); res.json({ok:true,api:'online',...data}); } catch(e){res.status(500).json({ok:false,error:e.message});} });
app.get('/api/dashboard', async (_req,res)=>{try{res.json(await pythonRead('dashboard'))}catch(e){res.status(500).json({error:e.message,details:e.details||e.stack||''})}});
app.get('/api/articles', async (req,res)=>{try{res.json(await pythonRead('articles',{page:req.query.page||1,limit:req.query.limit||25,search:req.query.search||'',status:req.query.status||'ALL'}))}catch(e){res.status(500).json({error:e.message,details:e.details||e.stack||''})}});
app.get('/api/queue', async (req,res)=>{try{res.json(await pythonRead('queue',{status:req.query.status||'ALL'}))}catch(e){res.status(500).json({error:e.message,details:e.details||e.stack||''})}});
app.get('/api/scripts', async (_req,res)=>{try{res.json(await pythonRead('scripts'))}catch(e){res.status(500).json({error:e.message,details:e.details||e.stack||''})}});
app.get('/api/content-settings', async (_req,res)=>{try{res.json(await pythonRead('content_settings'))}catch(e){res.status(500).json({error:e.message,details:e.details||e.stack||''})}});
app.put('/api/content-settings', async (req,res)=>{try{res.json(await pythonRead('save_content_settings',req.body||{}))}catch(e){res.status(400).json({error:e.message,details:e.details||e.stack||''})}});
app.post('/api/jobs/research', (req,res)=>{try{res.status(202).json(startJob('research',req.body||{}))}catch(e){res.status(e.status||500).json({error:e.message,details:e.details||e.stack||''})}});
app.post('/api/jobs/generate', (req,res)=>{try{res.status(202).json(startJob('generate',{storyId:req.body?.storyId}))}catch(e){res.status(e.status||500).json({error:e.message,details:e.details||e.stack||''})}});
app.post('/api/jobs/generate-bulk', (req,res)=>{try{res.status(202).json(startJob('generate_bulk',{storyIds:req.body?.storyIds||[]}))}catch(e){res.status(e.status||500).json({error:e.message,details:e.details||e.stack||''})}});
app.post('/api/queue/select', async(req,res)=>{try{res.json(await pythonRead('select_articles',{ids:req.body?.ids||[]}))}catch(e){res.status(500).json({error:e.message,details:e.details||e.stack||''})}});
app.patch('/api/queue/:queueId/status', async(req,res)=>{try{res.json(await pythonRead('set_queue_status',{queueId:req.params.queueId,status:req.body?.status}))}catch(e){res.status(400).json({error:e.message,details:e.details||e.stack||''})}});
app.post('/api/jobs/:id/cancel', (req,res)=>{const j=jobs.get(req.params.id);if(!j)return res.status(404).json({error:'Job tidak ditemukan'});if(j.status!=='running')return res.status(409).json({error:`Job berstatus ${j.status}, tidak bisa dibatalkan.`});j.status='cancelling';j.logs.push({time:new Date().toISOString(),level:'warning',message:'Pembatalan diminta dari UI.'});sendEvent(j,{type:'log',level:'warning',message:'Pembatalan diminta dari UI.'});j.child?.kill('SIGTERM');res.json({ok:true,id:j.id,status:j.status});});
app.get('/api/jobs/:id', (req,res)=>{const j=jobs.get(req.params.id); if(!j)return res.status(404).json({error:'Job tidak ditemukan'}); res.json({id:j.id,action:j.action,status:j.status,progress:j.progress,stage:j.stage,logs:j.logs,result:j.result,error:j.error,startedAt:j.startedAt,finishedAt:j.finishedAt})});
app.get('/api/jobs/:id/events', (req,res)=>{const j=jobs.get(req.params.id);if(!j)return res.status(404).end();res.setHeader('Content-Type','text/event-stream');res.setHeader('Cache-Control','no-cache');res.setHeader('Connection','keep-alive');res.flushHeaders?.();j.clients.add(res);for(const evt of j.events)res.write(`data: ${JSON.stringify(evt)}\n\n`);req.on('close',()=>j.clients.delete(res));});
app.listen(PORT,'127.0.0.1',()=>console.log(`HCF API running at http://127.0.0.1:${PORT}`));
