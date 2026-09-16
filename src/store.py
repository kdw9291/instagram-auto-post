"""Persistent local production queue. Publishing is deliberately unconnected."""
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from .render import RENDER_VERSION, visual_revision
from .artifacts import build_bundle, valid_bundle
from .backgrounds import topic_for, background_label
from .editorial import editorial_adapters, verify_content, EvidenceError
from .news_images import attach, rows as image_jobs, ImagePending
from .discovery import sync as sync_discovery
from . import operations

def now():
    return datetime.now(timezone.utc)

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

def timestamp(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError('날짜에 시간대가 필요합니다.')
    return result

def validate(c):
    if not isinstance(c, dict):
        raise ValueError('자료는 JSON 객체여야 합니다.')
    if c.get('category') not in ('place', 'beauty', 'food'):
        raise ValueError('지원하지 않는 분야입니다.')
    for key in ('source_id', 'title', 'subtitle', 'intro_heading', 'intro', 'cta', 'conditions', 'source_label', 'caption'):
        if not isinstance(c.get(key), str) or not c[key].strip():
            raise ValueError(f'필수 정보 누락: {key}')
    if len(c['caption']) > 2200:
        raise ValueError('캡션은 2,200자 이하여야 합니다.')
    if not isinstance(c.get('sample'), bool):
        raise ValueError('샘플 여부를 명시해야 합니다.')
    if not isinstance(c.get('facts'), list) or not 1 <= len(c['facts']) <= 3:
        raise ValueError('핵심 조건은 1–3개로 정리해야 합니다.')
    for fact in c['facts']:
        if not isinstance(fact, dict) or not all(isinstance(fact.get(k), str) and fact[k].strip() for k in ('label', 'value')):
            raise ValueError('핵심 조건의 이름과 값이 필요합니다.')
    if not isinstance(c.get('sources'), list) or not c['sources']:
        raise ValueError('출처가 필요합니다.')
    for source in c['sources']:
        if not isinstance(source, str) or urlparse(source).scheme != 'https' or not urlparse(source).hostname:
            raise ValueError('유효한 HTTPS 출처가 필요합니다.')
    if timestamp(c['verified_at']) >= timestamp(c['valid_until']):
        raise ValueError('정보 유효기한이 확인 시각 이후여야 합니다.')
    # Presence/schema validation does not claim remote fact verification.

class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.db = self.root / 'data/runtime/queue.sqlite3'
        self.db.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1), review INTEGER NOT NULL, revision INTEGER NOT NULL);
              INSERT OR IGNORE INTO settings VALUES(1,1,1);
              CREATE TABLE IF NOT EXISTS items (id TEXT PRIMARY KEY, source_id TEXT UNIQUE, content TEXT NOT NULL, version TEXT NOT NULL, state TEXT NOT NULL, review INTEGER NOT NULL, approval TEXT, created TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, at TEXT, message TEXT);
              CREATE TABLE IF NOT EXISTS imports (hash TEXT PRIMARY KEY);
            ''')
            if 'verification' not in [r['name'] for r in db.execute('PRAGMA table_info(items)')]:
                db.execute('ALTER TABLE items ADD COLUMN verification TEXT')
        operations.settings(self.root)
        from .publishing import Outbox
        self.outbox=Outbox(self)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def event(self, db, message):
        db.execute('INSERT INTO events(at,message) VALUES(?,?)', (now().isoformat(), message))

    def expire(self, db):
        for row in db.execute("SELECT * FROM items WHERE state NOT IN ('held','expired','published')").fetchall():
            c = json.loads(row['content'])
            if not c['sample'] and timestamp(c['valid_until']) <= now():
                db.execute("UPDATE items SET state='expired', approval=NULL WHERE id=?", (row['id'],))
                self.event(db, '정보 유효기한이 지나 제작물을 만료 처리했습니다.')

    def snapshot(self):
        with self.connect() as db:
            self.expire(db)
            settings = dict(db.execute('SELECT * FROM settings').fetchone())
            items = []
            for row in db.execute('SELECT * FROM items ORDER BY created DESC'):
                item = dict(row)
                item['content'] = json.loads(item['content'])
                item['verification'] = json.loads(item['verification']) if item['verification'] else None
                if not item['content']['sample'] and item['state'] in ('waiting','ready','approved'):
                    try:verify_content(self.root,item['content'])
                    except EvidenceError:
                        db.execute("UPDATE items SET state='needs_verification',approval=NULL WHERE id=?",(item['id'],))
                        item['state']='needs_verification';item['approval']=None
                item['can_approve'] = item['state'] in ('waiting','ready') and (item['content']['sample'] or bool(item['verification'] and item['verification'].get('status')=='verified'))
                item['cards'] = [f"/media/{item['id']}/{item['version']}/card-{i}.png" for i in range(1,5)]
                item['background'] = {'topic':topic_for(item['content']),'label':background_label(item['content'])}
                items.append(item)
            report_path = self.root / 'data/runtime/collection/report.json'
            report = json.loads(report_path.read_text(encoding='utf-8')) if report_path.exists() else {'sources':[]}
            # Never return stored full source texts via the dashboard.
            return {'settings': {'review': bool(settings['review']), 'revision': settings['revision']}, 'items': items,
                    'events': [dict(r) for r in db.execute('SELECT * FROM events ORDER BY id DESC LIMIT 30')],
                    'account': None, 'publishing': False, 'publish_jobs':self.outbox.rows(), 'operations':operations.snapshot(self.root), 'collection': report,'image_jobs':image_jobs(self.root),'candidates':sync_discovery(self.root,report)}

    def ingest(self):
        for path in sorted((self.root / 'data/inbox').glob('*.json')):
            if path.stat().st_size > 1000000:
                continue
            raw = path.read_bytes()
            h = hashlib.sha256(visual_revision().encode() + raw).hexdigest()
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                if db.execute('SELECT 1 FROM imports WHERE hash=?', (h,)).fetchone():
                    continue
                try:
                    c = json.loads(raw)
                    validate(c)
                    item_id = digest(c['source_id'])[:16]
                    old = db.execute('SELECT * FROM items WHERE source_id=?', (c['source_id'],)).fetchone()
                    if old and old['state'] in ('held','published'):
                        self.event(db, ('게시한' if old['state']=='published' else '보류한')+' 소재의 자동 재요청을 건너뛰었습니다.')
                    else:
                        version = build_bundle(self.root,item_id,c)
                        review = bool(db.execute('SELECT review FROM settings').fetchone()[0]) or bool(old and old['review'])
                        # Real input still needs an independently verified collection adapter.
                        state = ('waiting' if review else 'ready') if c['sample'] else 'needs_verification'
                        db.execute('''INSERT INTO items(id,source_id,content,version,state,review,approval,created) VALUES(?,?,?,?,?,?,NULL,?) ON CONFLICT(source_id) DO UPDATE SET
                           content=excluded.content, version=excluded.version,state=excluded.state,review=excluded.review,approval=NULL,verification=NULL''',
                           (item_id, c['source_id'], json.dumps(c, ensure_ascii=False), version, state, int(review), now().isoformat()))
                        self.event(db, '자료를 읽어 카드 4장을 제작했습니다. ' + ('디자인 샘플입니다.' if c['sample'] else '원문 자동 검증 연결을 기다립니다.'))
                except (ValueError, KeyError, TypeError, OSError) as e:
                    self.event(db, f'자료 자동 처리 보류: {path.name} · {e}')
                db.execute('INSERT INTO imports VALUES(?)', (h,))

    def produce(self):
        for source_id,maker in editorial_adapters(self.root):self.produce_one(source_id,maker)

    def produce_one(self,source_id,maker):
        """Only the internal adapter can create an evidence-verified real draft."""
        with self.connect() as db:
            existing=db.execute('SELECT state FROM items WHERE source_id=?',(source_id,)).fetchone()
            if existing and existing['state'] in ('held','published'):return
        try:
            content,receipt=maker(self.root)
            validate(content)
            if not operations.admit(self.root,content,receipt):return
            item_id=digest(content['source_id'])[:16]
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                old=db.execute('SELECT * FROM items WHERE id=?',(item_id,)).fetchone()
                old_receipt=json.loads(old['verification']) if old and old['verification'] else {}
                if old and (old['state'] in ('held','published') or old_receipt.get('status')=='manual_edit'):return
                content=attach(self.root,content,enqueue=True)
                if old and json.loads(old['content'])==content and old['state']!='needs_verification':return
                version=build_bundle(self.root,item_id,content)
                review=bool(db.execute('SELECT review FROM settings').fetchone()[0]) or bool(old and old['review'])
                state='waiting' if review else 'ready'
                db.execute('''INSERT INTO items(id,source_id,content,version,state,review,approval,created,verification)
                   VALUES(?,?,?,?,?,?,NULL,?,?) ON CONFLICT(id) DO UPDATE SET content=excluded.content,
                   version=excluded.version,state=excluded.state,review=excluded.review,approval=NULL,verification=excluded.verification''',
                   (item_id,content['source_id'],json.dumps(content,ensure_ascii=False),version,state,int(review),now().isoformat(),json.dumps(receipt,ensure_ascii=False)))
                self.event(db,'공식 근거를 연결해 원고와 카드 4장을 자동 제작했습니다. 완성본 확인 설정을 적용합니다.')
        except (EvidenceError,ValueError,OSError) as e:
            with self.connect() as db:
                state='awaiting_image' if isinstance(e,ImagePending) else 'needs_verification'
                db.execute("UPDATE items SET state=?,approval=NULL WHERE source_id=? AND state NOT IN ('held','expired','published')",(state,source_id))
                message=f'자동 원고 보완 대기: {source_id} · {e}'
                last=db.execute("SELECT message FROM events WHERE message LIKE ? ORDER BY id DESC LIMIT 1",(f'자동 원고 보완 대기: {source_id} · %',)).fetchone()
                if not last or last['message']!=message:self.event(db,message)

    def settings(self, review, revision):
        if not isinstance(review, bool) or type(revision) is not int:
            raise ValueError('올바른 설정 값이 필요합니다.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT * FROM settings').fetchone()
            if revision != current['revision']:
                raise ValueError('다른 화면에서 설정이 변경되었습니다. 새로고침해 주세요.')
            if review and not current['review']:
                db.execute("UPDATE items SET review=1, state=CASE WHEN state='ready' AND approval IS NULL THEN 'waiting' ELSE state END WHERE state NOT IN ('held','expired','published')")
            db.execute('UPDATE settings SET review=?, revision=revision+1', (int(review),))
            self.event(db, '완성본 확인을 ' + ('ON' if review else 'OFF') + '으로 저장했습니다. 기존 확인 요구는 유지됩니다.')

    def action(self, item_id, version, action, caption=None):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM items WHERE id=?', (item_id,)).fetchone()
            if not row or row['version'] != version:
                raise ValueError('새 완성본이 있습니다. 새로고침 후 확인해 주세요.')
            c = json.loads(row['content'])
            if row['state'] in ('held', 'expired', 'published') or (not c['sample'] and timestamp(c['valid_until']) <= now()):
                raise ValueError('보류 또는 만료된 제작물입니다.')
            if action == 'approve':
                if not valid_bundle(self.root,item_id,version,c):
                    raise ValueError('미리보기 미디어가 변경되었거나 누락되어 승인할 수 없습니다.')
                if row['state'] not in ('waiting', 'ready', 'approved'):
                    raise ValueError('원문 검증이 끝나지 않아 승인할 수 없습니다.')
                if not c['sample']:
                    receipt=json.loads(row['verification']) if row['verification'] else {}
                    if receipt.get('status')!='verified':raise ValueError('검증 기록이 없습니다.')
                    verify_content(self.root,c)
                db.execute("UPDATE items SET state='approved', approval=? WHERE id=?", (version, item_id))
                if row['approval'] != version:
                    self.event(db, ('샘플 ' if c['sample'] else '')+'완성본 승인을 기록했습니다. 계정 미연결로 게시하지 않습니다.')
            elif action == 'hold':
                db.execute("UPDATE items SET state='held', approval=NULL WHERE id=?", (item_id,))
                self.event(db, '이번 소재를 보류했습니다. 자동 재요청하지 않습니다.')
            elif action == 'edit':
                if not isinstance(caption, str) or not caption.strip():
                    raise ValueError('캡션을 입력해 주세요.')
                c['caption'] = caption.strip()
                validate(c)
                version = build_bundle(self.root,item_id,c)
                state = ('waiting' if row['review'] else 'ready') if c['sample'] else 'needs_verification'
                db.execute('UPDATE items SET content=?, version=?, approval=NULL,state=?,verification=? WHERE id=?', (json.dumps(c, ensure_ascii=False), version, state, json.dumps({'status':'manual_edit'}),item_id))
                self.event(db, '캡션 새 버전을 저장하고 이전 승인을 해제했습니다. 사실 검증은 별도 필요합니다.')
            else:
                raise ValueError('지원하지 않는 동작입니다.')
