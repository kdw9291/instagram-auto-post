"""Atomic production admission and revisioned user controls, local SQLite."""
import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
from pathlib import Path

KST=timezone(timedelta(hours=9))
DEFAULT={'daily_place':1,'daily_beauty':1,'daily_food':1,'max_pending':6,'duplicate_days':7,'retry_limit':2,'retry_minutes':15}
LIMITS={'daily_place':(0,20),'daily_beauty':(0,20),'daily_food':(0,20),'max_pending':(1,50),'duplicate_days':(0,30),'retry_limit':(0,5),'retry_minutes':(1,120)}

@contextmanager
def connection(root):
    path=Path(root)/'data/runtime/queue.sqlite3';path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path,timeout=30);db.row_factory=sqlite3.Row
    try:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='operation_settings'").fetchone():
            with db:
                db.execute('CREATE TABLE IF NOT EXISTS operation_settings(id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER,value TEXT)')
                db.execute('INSERT OR IGNORE INTO operation_settings VALUES(1,1,?)',(json.dumps(DEFAULT),))
                db.execute('CREATE TABLE IF NOT EXISTS admissions(source_id TEXT PRIMARY KEY,category TEXT,topic TEXT,created TEXT,until TEXT,granted INTEGER,reason TEXT,title TEXT)')
        yield db
    finally:db.close()

def settings(root):
    with connection(root) as db:
        r=db.execute('SELECT * FROM operation_settings').fetchone()
        return dict(json.loads(r['value']),revision=r['revision'])

def update(root,values,revision):
    if set(values)!=set(DEFAULT) or type(revision)!=int:raise ValueError('운영 설정 항목을 확인하세요.')
    for k,(low,high) in LIMITS.items():
        if type(values[k])!=int or not low<=values[k]<=high:raise ValueError('운영 설정 범위를 확인하세요: '+k)
    with connection(root) as db:
        with db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('UPDATE operation_settings SET value=?,revision=revision+1 WHERE id=1 AND revision=?',(json.dumps(values),revision)).rowcount:raise ValueError('운영 설정이 변경됐습니다. 새로고침 후 저장하세요.')

def topic(content,receipt):
    names=[str(c['value']) for c in receipt.get('claims',[]) if c.get('field') in ('product','program','event_title') and isinstance(c.get('value'),str)]
    name=names[0] if names else content['title']
    return hashlib.sha256((content['category']+re.sub(r'[^가-힣a-z0-9]','',name.lower())).encode()).hexdigest()

def items(db):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='items'").fetchone():return []
    return [dict(r,content=json.loads(r['content'])) for r in db.execute('SELECT * FROM items') if not json.loads(r['content']).get('sample')]

def pending(existing,reservations,at):
    ids={i['source_id'] for i in existing if i['state'] in ('waiting','ready','awaiting_image','needs_verification') and datetime.fromisoformat(i['content']['valid_until'])>at}
    ids.update(r['source_id'] for r in reservations if r['granted'] and datetime.fromisoformat(r['until'])>at and r['source_id'] not in {i['source_id'] for i in existing})
    return len(ids)

def admit(root,content,receipt,at=None):
    at=at or datetime.now(timezone.utc)
    with connection(root) as db:
        with db:
            db.execute('BEGIN IMMEDIATE')
            cfg=json.loads(db.execute('SELECT value FROM operation_settings').fetchone()[0]);existing=items(db)
            if any(i['source_id']==content['source_id'] for i in existing):return True
            reservations=[dict(r) for r in db.execute('SELECT * FROM admissions')]
            old=next((r for r in reservations if r['source_id']==content['source_id']),None)
            if old and old['granted'] and datetime.fromisoformat(old['until'])>at:return True
            day=at.astimezone(KST).date();cat=content['category'];key=topic(content,receipt)
            used={i['source_id'] for i in existing if i['content']['category']==cat and datetime.fromisoformat(i['created']).astimezone(KST).date()==day}
            used.update(r['source_id'] for r in reservations if r['category']==cat and r['granted'] and datetime.fromisoformat(r['created']).astimezone(KST).date()==day)
            known=[(topic(i['content'],json.loads(i.get('verification') or '{}')),i['created']) for i in existing]
            known += [(r['topic'],r['created']) for r in reservations if r['granted'] and r['source_id']!=content['source_id']]
            reason=''
            if cfg['daily_'+cat]==0:reason='분야 제작 일시 정지'
            elif any(t==key and timedelta(0)<=at-datetime.fromisoformat(d)<timedelta(days=cfg['duplicate_days']) for t,d in known):reason='같은 제품·행사 중복 기간'
            elif len(used)>=cfg['daily_'+cat]:reason='오늘 분야별 제작량 도달'
            elif pending(existing,reservations,at)>=cfg['max_pending']:reason='미완료 제작물 상한 도달'
            db.execute('INSERT INTO admissions VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET category=excluded.category,topic=excluded.topic,created=excluded.created,until=excluded.until,granted=excluded.granted,reason=excluded.reason,title=excluded.title',
                       (content['source_id'],cat,key,at.isoformat(),content['valid_until'],int(not reason),reason,content['title']))
            return not reason

def snapshot(root):
    at=datetime.now(timezone.utc)
    with connection(root) as db:
        records=[dict(r) for r in db.execute('SELECT * FROM admissions')];existing=items(db)
        waiting=[{'title':r['title'],'reason':r['reason']} for r in records if not r['granted'] and datetime.fromisoformat(r['until'])>at]
        return {'settings':settings(root),'pending':pending(existing,records,at),'deferred':waiting[:30]}


def generation_allowed(root,source_id):
    at=datetime.now(timezone.utc)
    with connection(root) as db:
        existing=next((i for i in items(db) if i['source_id']==source_id),None)
        if existing and existing['state']=='held':return False
        reservation=db.execute('SELECT * FROM admissions WHERE source_id=?',(source_id,)).fetchone()
        return not reservation or (bool(reservation['granted']) and datetime.fromisoformat(reservation['until'])>at)
