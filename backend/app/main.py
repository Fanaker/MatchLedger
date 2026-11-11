"""MatchLedger API. Local SQLite storage; no cloud account or external APIs required."""
from __future__ import annotations
import csv
import io
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel

from .reconciliation import parse_csv, reconcile, summarize
from .demo import generate

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get('MATCHLEDGER_DATA', ROOT / '.data'))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB = DATA_DIR / 'matchledger.sqlite3'
SAMPLE_DIR = ROOT / 'sample-data'

app = FastAPI(title='MatchLedger API', version='1.0.0', description='Conciliación de movimientos de dos orígenes CSV')
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173', 'http://localhost:8000', 'http://127.0.0.1:8000'], allow_credentials=True, allow_methods=['*'], allow_headers=['*'])


def connection():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_storage():
    with connection() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL,
            source_a TEXT NOT NULL, source_b TEXT NOT NULL, payload TEXT NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, created_at TEXT NOT NULL,
            kind TEXT NOT NULL, message TEXT NOT NULL)''')


def audit(sid, kind, msg):
    with connection() as c:
        c.execute('INSERT INTO audit_events (session_id, created_at, kind, message) VALUES(?,?,?,?)', (sid, datetime.now(timezone.utc).isoformat(), kind, msg))


def save_session(title, source_a, source_b, data):
    sid = 'SES-' + uuid4().hex[:10].upper()
    now = datetime.now(timezone.utc).isoformat()
    with connection() as c:
        c.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?)', (sid, title[:100], now, source_a[:80], source_b[:80], json.dumps(data, ensure_ascii=False)))
    audit(sid, 'created', f'Conciliación creada: {title}')
    return sid


def get_session(sid):
    with connection() as c:
        row = c.execute('SELECT * FROM sessions WHERE id = ?', (sid,)).fetchone()
    if row is None:
        raise HTTPException(404, 'Conciliación no encontrada')
    data = json.loads(row['payload'])
    return {**dict(row), 'data': data, 'summary': summarize(data)}


def session_summary(row):
    data = json.loads(row['payload'])
    return {k: row[k] for k in ('id', 'title', 'created_at', 'source_a', 'source_b')} | {'summary': summarize(data)}


def current():
    with connection() as c:
        row = c.execute('SELECT * FROM sessions ORDER BY created_at DESC LIMIT 1').fetchone()
    return get_session(row['id']) if row else None

init_storage()
if not list(SAMPLE_DIR.glob('*.csv')):
    generate(SAMPLE_DIR)
with connection() as c:
    existing = c.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]
if not existing:
    a, b = generate(SAMPLE_DIR)
    sid = save_session('Cierre comercial · Octubre 2026', 'Banco empresa', 'ERP comercial', reconcile(parse_csv(a.read_bytes(), 'A'), parse_csv(b.read_bytes(), 'B')))
    audit(sid, 'import', 'Se cargaron dos archivos CSV de demostración')


@app.get('/api/health')
def health():
    return {'status': 'ok', 'app': 'MatchLedger', 'version': '1.0.0'}


@app.get('/api/dashboard')
def dashboard():
    value = current()
    return {'session': {k: value[k] for k in ('id','title','created_at','source_a','source_b')} if value else None,
            'summary': value['summary'] if value else None,
            'entries': value['data']['entries'] if value else [],
            'history': list_sessions(), 'activity': activity()['events']}


@app.get('/api/sessions')
def list_sessions():
    with connection() as c:
        rows = c.execute('SELECT * FROM sessions ORDER BY created_at DESC LIMIT 30').fetchall()
    return [session_summary(r) for r in rows]


@app.get('/api/sessions/{sid}')
def detail(sid: str):
    session = get_session(sid)
    return {k: session[k] for k in ('id','title','created_at','source_a','source_b','summary')} | {'entries': session['data']['entries']}


@app.post('/api/reconcile')
async def upload_and_reconcile(source_a: UploadFile = File(...), source_b: UploadFile = File(...), title: str = Form('Nueva conciliación')):
    for upload in (source_a, source_b):
        if not upload.filename or not upload.filename.lower().endswith('.csv'):
            raise HTTPException(400, 'Selecciona archivos con extensión .csv')
    try:
        left = parse_csv(await source_a.read(), 'A')
        right = parse_csv(await source_b.read(), 'B')
    except ValueError as err:
        raise HTTPException(422, str(err)) from None
    sid = save_session(title or 'Nueva conciliación', source_a.filename, source_b.filename, reconcile(left, right))
    audit(sid, 'import', f'Archivos importados: {len(left)} movimientos de A y {len(right)} de B')
    return detail(sid)


class Resolution(BaseModel):
    entry_id: str
    candidate_id: str | None = None
    action: str  # accept | dismiss
    note: str = ''


@app.post('/api/sessions/{sid}/resolve')
def resolve(sid: str, body: Resolution):
    item = get_session(sid)
    entries = item['data']['entries']
    record = next((x for x in entries if x['id'] == body.entry_id), None)
    if not record or record['status'] != 'review':
        raise HTTPException(400, 'La operación no requiere revisión.')
    potential_orphans = {c['id']: c for e in entries if e['status'] == 'review' for c in e['candidates']}
    if body.action == 'accept':
        chosen = next((c for c in record['candidates'] if c['id'] == body.candidate_id), None)
        if not chosen:
            raise HTTPException(400, 'Selecciona una contraparte válida.')
        already_used = any(e['right'] and e['right']['id'] == chosen['id'] and e['status'] == 'matched' for e in entries)
        if already_used:
            raise HTTPException(409, 'La contraparte ya fue utilizada.')
        record.update(status='matched', right=chosen, candidates=[], score=100, reason='Validado manualmente: ' + (body.note.strip()[:100] or 'Coincidencia confirmada'))
        # Remove other now-unavailable candidates and materialize empty-review cases as unmatched.
        for other in entries:
            if other['status'] == 'review' and other['id'] != record['id']:
                other['candidates'] = [c for c in other['candidates'] if c['id'] != chosen['id']]
                if not other['candidates']:
                    other.update(status='only_a', reason='Sin contraparte disponible tras revisión')
        audit(sid, 'resolved', f'Coincidencia aprobada: {body.entry_id}')
    elif body.action == 'dismiss':
        record.update(status='only_a', candidates=[], reason='Descartado durante revisión: ' + body.note.strip()[:100])
        audit(sid, 'resolved', f'Coincidencia descartada: {body.entry_id}')
    else:
        raise HTTPException(400, 'Acción no válida.')
    # Once a review is closed, previously reserved counterparts can become
    # unmatched items; preserve them rather than silently omitting them.
    held_ids = {c['id'] for e in entries if e['status'] == 'review' for c in e['candidates']}
    represented_ids = {e['right']['id'] for e in entries if e['right']}
    for cid, record_b in potential_orphans.items():
        if cid not in held_ids and cid not in represented_ids:
            entries.append({'id': 'ML-' + cid, 'status': 'only_b', 'left': None,
                'right': record_b, 'candidates': [],
                'reason': 'Sin contraparte tras revisión manual', 'score': None})
    with connection() as c:
        c.execute('UPDATE sessions SET payload=? WHERE id=?', (json.dumps(item['data'], ensure_ascii=False), sid))
    return detail(sid)


@app.get('/api/activity')
def activity():
    with connection() as c:
        rows = c.execute('SELECT * FROM audit_events ORDER BY id DESC LIMIT 20').fetchall()
    return {'events': [dict(r) for r in rows]}


@app.get('/api/demo/{which}')
def demo_file(which: str):
    names = {'a': 'banco_octubre_2026.csv', 'b': 'erp_octubre_2026.csv'}
    if which not in names:
        raise HTTPException(404, 'Archivo no encontrado')
    return FileResponse(SAMPLE_DIR / names[which], filename=names[which], media_type='text/csv')


@app.get('/api/sessions/{sid}/export')
def export(sid: str):
    item = get_session(sid)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['estado', 'fecha_banco', 'referencia_banco', 'detalle_banco', 'monto_banco', 'fecha_erp', 'referencia_erp', 'detalle_erp', 'monto_erp', 'observacion'])
    for e in item['data']['entries']:
        a, b = e.get('left') or {}, e.get('right') or {}
        writer.writerow([e['status'], a.get('date',''), a.get('reference',''), a.get('description',''), a.get('amount',''),
                         b.get('date',''), b.get('reference',''), b.get('description',''), b.get('amount',''), e['reason']])
    output.seek(0)
    return StreamingResponse(iter([('\ufeff'+output.getvalue()).encode('utf-8')]), media_type='text/csv; charset=utf-8',
                             headers={'Content-Disposition': f'attachment; filename="matchledger_{sid}.csv"'})
