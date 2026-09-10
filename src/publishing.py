"""Durable publishing preparation. No live transport is configured by the app."""
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from .artifacts import valid_bundle
from .editorial import verify_content


def now():return datetime.now(timezone.utc)


class Outbox:
    def __init__(self,store):
        self.store=store
        self.path=store.root/'data/runtime/publishing.sqlite3'
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS jobs(
                id TEXT PRIMARY KEY,item_id TEXT,version TEXT,source_id TEXT,
                due TEXT,state TEXT,children TEXT DEFAULT '[]',container TEXT,
                media_id TEXT,error TEXT,updated TEXT)""")

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=30);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()

    def eligible(self,db,item_id,version):
        row=db.execute('SELECT * FROM items WHERE id=?',(item_id,)).fetchone()
        if not row or row['version']!=version:raise ValueError('완성본 버전 변경')
        content=json.loads(row['content'])
        mode=db.execute('SELECT review FROM settings WHERE id=1').fetchone()[0]
        if content['sample']:raise ValueError('샘플 발행 금지')
        if row['state'] not in ('ready','approved'):raise ValueError('완성본 확인 또는 검증 대기')
        if (mode or row['review']) and row['approval']!=version:raise ValueError('현재 버전 승인 필요')
        if datetime.fromisoformat(content['valid_until'])<=now():raise ValueError('정보 기한 경과')
        if not valid_bundle(self.store.root,item_id,version,content):raise ValueError('미디어 무결성 오류')
        verify_content(self.store.root,content)
        return row,content

    def schedule(self,item_id,version,due=None):
        due=due or now()
        if not isinstance(due,datetime) or due.tzinfo is None:raise ValueError('예약 시각에 시간대 필요')
        with self.store.connect() as source:
            source.execute('BEGIN IMMEDIATE')
            row,content=self.eligible(source,item_id,version)
            if due>=datetime.fromisoformat(content['valid_until']):raise ValueError('정보 기한 이후 예약 불가')
            key=hashlib.sha256((item_id+':'+version).encode()).hexdigest()
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                previous=db.execute("SELECT 1 FROM jobs WHERE source_id=? AND state IN ('published','uncertain','sending')",(row['source_id'],)).fetchone()
                if previous:raise ValueError('이미 발행했거나 전송 결과 확인 중인 소재')
                db.execute("INSERT OR IGNORE INTO jobs(id,item_id,version,source_id,due,state,updated) VALUES(?,?,?,?,?,'prepared',?)",(key,item_id,version,row['source_id'],due.astimezone(timezone.utc).isoformat(),now().isoformat()))
        return key

    def prepare(self):
        with self.store.connect() as db:
            items=db.execute("SELECT id,version FROM items WHERE state IN ('ready','approved')").fetchall()
        for item in items:
            try:self.schedule(item['id'],item['version'])
            except (ValueError,OSError):pass
        with self.connect() as db:
            jobs=db.execute("SELECT * FROM jobs WHERE state IN ('prepared','containers','ready')").fetchall()
        for job in jobs:
            try:
                with self.store.connect() as source:self.eligible(source,job['item_id'],job['version'])
            except (ValueError,OSError):
                self.change(job['id'],state='cancelled',error='버전·승인·근거 또는 미디어 변경')

    def export(self,key):
        """Prepare deterministic JPEGs locally; uploading is a separate integration."""
        from PIL import Image
        with self.store.connect() as source:
            source.execute('BEGIN IMMEDIATE')
            with self.connect() as db:job=db.execute('SELECT * FROM jobs WHERE id=?',(key,)).fetchone()
            if not job:raise ValueError('발행 작업 없음')
            row,content=self.eligible(source,job['item_id'],job['version'])
            directory=self.store.root/'data/runtime/publish-packages'/key
            manifest=directory/'manifest.json'
            import io
            base=self.store.root/'assets/images/generated'/job['item_id']/job['version']
            buffers=[];cards=[]
            for index in range(1,5):
                buffer=io.BytesIO()
                with Image.open(base/f'card-{index}.png') as image:
                    image.convert('RGB').save(buffer,format='JPEG',quality=95,subsampling=0)
                raw=buffer.getvalue();buffers.append(raw)
                cards.append({'file':f'card-{index}.jpg','sha256':hashlib.sha256(raw).hexdigest()})
            saved={'item_id':job['item_id'],'version':job['version'],'caption':content['caption'],'cards':cards}
            if manifest.exists():
                if json.loads(manifest.read_text(encoding='utf-8'))!=saved:raise ValueError('발행 명세가 승인 원본과 다릅니다.')
                for card in cards:
                    if hashlib.sha256((directory/card['file']).read_bytes()).hexdigest()!=card['sha256']:raise ValueError('발행 JPEG 변경 감지')
                return saved
            directory.mkdir(parents=True,exist_ok=True)
            for card,raw in zip(cards,buffers):(directory/card['file']).write_bytes(raw)
            temp=manifest.with_suffix('.tmp');temp.write_text(json.dumps(saved,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(manifest)
            return saved

    def change(self,key,**values):
        allowed={'state','children','container','media_id','error'}
        if not set(values)<=allowed:raise ValueError('잘못된 상태 필드')
        values['updated']=now().isoformat()
        with self.connect() as db:
            db.execute('UPDATE jobs SET '+','.join(k+'=?' for k in values)+' WHERE id=?',(*values.values(),key))

    def rows(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT id,item_id,version,due,state,media_id,error FROM jobs ORDER BY due DESC LIMIT 30')]

    def step(self,key,api,urls):
        """Injected adapter only; caller must supply verified hosted JPEGs and account.

        No runtime worker invokes this until account/hosting integration is complete.
        Persist sending before each mutation; an interrupted write is never repeated.
        """
        with self.store.connect() as source:
            source.execute('BEGIN IMMEDIATE')
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                job=db.execute('SELECT * FROM jobs WHERE id=?',(key,)).fetchone()
                if not job:raise ValueError('발행 작업 없음')
                if job['state'] in ('published','uncertain','cancelled','failed'):return
                if job['state']=='sending':
                    db.execute("UPDATE jobs SET state='uncertain',error='전송 결과 확인 필요' WHERE id=?",(key,));return
                if datetime.fromisoformat(job['due'])>now():return
            try:row,content=self.eligible(source,job['item_id'],job['version'])
            except (ValueError,OSError):
                self.change(key,state='cancelled',error='발행 직전 검증 실패');return
            children=json.loads(job['children'])
            if job['container']:
                status=api.status(job['container'])
                if status=='PUBLISHED':self.change(key,state='published');return
                if status in ('ERROR','EXPIRED'):self.change(key,state='failed',error='컨테이너 처리 실패');return
                if status!='FINISHED':return
                self.change(key,state='sending')
                try:
                    media=api.publish(job['container'])
                    if not isinstance(media,str) or not media:raise ValueError('게시 식별자 없음')
                    self.change(key,state='published',media_id=media)
                except (OSError,ValueError,KeyError,TypeError):self.change(key,state='uncertain',error='게시 응답 확인 필요; 자동 재전송 안 함')
                return
            if len(urls)!=4:raise ValueError('검증된 카드 URL 4개 필요')
            if len(children)==4:
                statuses=[api.status(child) for child in children]
                if any(status in ('ERROR','EXPIRED') for status in statuses):
                    self.change(key,state='failed',error='카드 컨테이너 처리 실패');return
                if any(status!='FINISHED' for status in statuses):return
            self.change(key,state='sending')
            try:
                if len(children)<4:
                    child=api.image(urls[len(children)])
                    if not isinstance(child,str) or not child:raise ValueError('이미지 컨테이너 식별자 없음')
                    children.append(child);self.change(key,state='containers',children=json.dumps(children))
                else:
                    container=api.carousel(children,content['caption'])
                    if not isinstance(container,str) or not container:raise ValueError('캐러셀 식별자 없음')
                    self.change(key,state='ready',container=container)
            except (OSError,ValueError,KeyError,TypeError):self.change(key,state='uncertain',error='컨테이너 응답 확인 필요; 자동 재전송 안 함')
