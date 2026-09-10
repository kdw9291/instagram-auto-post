"""User-started desktop production and explicit format-specific publication."""
import hashlib
import json
import threading
import time
from pathlib import Path
from .artifacts import valid_bundle
from .editorial import verify_content
from .reels import POLICY, build as build_reel


def reel_info(root,item):
    key=hashlib.sha256((item['version']+POLICY).encode()).hexdigest()
    base=Path(root)/'assets/videos/generated'/item['id']/key
    try:
        data=json.loads((base/'manifest.json').read_text(encoding='utf-8'))
        if data['card_version']!=item['version'] or data['caption']!=item['content']['caption'] or data['policy']!=POLICY:return None
        if hashlib.sha256((base/'reel.mp4').read_bytes()).hexdigest()!=data['sha256']:return None
        return {'sha256':data['sha256'],'url':f"/video/{item['id']}/{key}/reel.mp4",'path':base/'reel.mp4'}
    except (OSError,ValueError,KeyError):return None


class Studio:
    def __init__(self,store):
        self.store=store;self.lock=threading.Lock();self.status={'busy':False,'stage':'idle','message':'새 콘텐츠 만들기를 눌러 시작하세요.'}
        with store.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS studio_posts(source_id TEXT,kind TEXT,item_id TEXT,version TEXT,
                sha TEXT,state TEXT,container TEXT,media_id TEXT,link TEXT,error TEXT,PRIMARY KEY(source_id,kind))''')
            db.execute("UPDATE studio_posts SET state='interrupted',error='중단된 작업입니다. 발행 상태 확인이 필요합니다.' WHERE state IN ('queued','working','creating','processing','sending')")
        # Preserve pre-studio published records. Never treat old approvals as new publish commands.
        for row in store.outbox.rows():
            if row['state']!='published':continue
            with store.connect() as db:
                item=db.execute('SELECT source_id FROM items WHERE id=?',(row['item_id'],)).fetchone()
                if item:db.execute("INSERT OR IGNORE INTO studio_posts(source_id,kind,item_id,version,state,media_id) VALUES(?,'cards',?,?,'published',?)",(item[0],row['item_id'],row['version'],row['media_id']))
    def posts(self):
        with self.store.connect() as db:return [dict(r) for r in db.execute('SELECT * FROM studio_posts')]

    def update(self,message,stage='working'):
        self.status={'busy':True,'stage':stage,'message':message}

    def start(self,fn):
        if not self.lock.acquire(False):raise ValueError('진행 중인 작업이 끝난 뒤 시도해 주세요.')
        self.update('작업을 시작합니다.')
        def run():
            try:fn()
            except Exception:
                self.status={'busy':False,'stage':'error','message':'작업이 중단됐습니다. 연결·근거·처리 기록을 확인해 주세요.'}
            finally:
                self.status=dict(self.status,busy=False);self.lock.release()
        threading.Thread(target=run,daemon=True).start()

    def produce(self):
        from .collector import Collector
        from .news_images import tick,rows
        before={i['id']:i['version'] for i in self.store.snapshot()['items']}
        self.update('공식 뉴스와 새 소식을 확인하고 있습니다.','collection')
        Collector(self.store.root).run(force=True)
        self.store.snapshot();self.store.ingest();self.store.produce()
        deadline=time.monotonic()+1200
        while time.monotonic()<deadline:
            pending=[r for r in rows(self.store.root) if r['state'] in ('queued','submitted','submitting')]
            if not pending:break
            self.update('뉴스에 맞는 이미지를 만들고 있습니다. 잠시 기다려 주세요.','images')
            tick(self.store.root);self.store.produce();time.sleep(3)
        self.store.produce()
        for item in self.store.snapshot()['items']:
            if item['content']['sample'] or item['state'] not in ('waiting','ready','approved'):continue
            self.update('카드뉴스를 30초 릴스로 만들고 있습니다.','reels')
            try:build_reel(self.store.root,item['id'],item['version'],item['content'])
            except (ValueError,OSError):
                with self.store.connect() as db:self.store.event(db,'릴스 제작 보류: '+item['content']['title'].replace('\n',' '))
        items=[i for i in self.store.snapshot()['items'] if not i['content']['sample']]
        new_count=sum(i['id'] not in before for i in items)
        updated=sum(i['id'] in before and before[i['id']]!=i['version'] for i in items)
        posted={p['source_id'] for p in self.posts() if p['state']=='published' and p['kind']=='cards'}
        ready=[i for i in items if i['state'] in ('waiting','ready','approved') and i['source_id'] not in posted]
        videos=sum(reel_info(self.store.root,i) is not None for i in ready)
        message=f'새 소재 {new_count}건 · 기존 원고 갱신 {updated}건 · 확인 가능한 카드 {len(ready)}건 / 릴스 {videos}건.'
        if not new_count:message+=' 이번 수집에서 새 제작물로 추가된 소재는 없습니다. 기존 완성본은 제작물 목록에서 확인하세요.'
        if not ready:message+=' 현재 확인 가능한 완성본이 없습니다. 아래 수집·근거 및 운영 한도 기록을 확인하세요.'
        self.status={'busy':False,'stage':'done','message':message,'result':{'new':new_count,'updated':updated,'ready':len(ready),'reels':videos}}


    def validate(self,item_id,version,sha=None):
        with self.store.connect() as db:
            row=db.execute('SELECT * FROM items WHERE id=?',(item_id,)).fetchone()
            if not row or row['version']!=version:raise ValueError('완성본이 바뀌었습니다. 새 버전을 확인해 주세요.')
            item=dict(row);item['content']=json.loads(item['content'])
        if item['state'] not in ('waiting','ready','approved') or item['content']['sample']:raise ValueError('게시할 수 있는 실제 완성본이 아닙니다.')
        if not valid_bundle(self.store.root,item_id,version,item['content']):raise ValueError('카드 무결성 오류')
        verify_content(self.store.root,item['content'])
        from .store import timestamp,now
        if timestamp(item['content']['valid_until'])<=now():raise ValueError('정보가 만료됐습니다. 새 콘텐츠 만들기로 재검증해 주세요.')
        reel=reel_info(self.store.root,item)
        if sha is not None and (not reel or reel['sha256']!=sha):raise ValueError('릴스가 변경되었거나 아직 준비되지 않았습니다.')
        return item,reel

    def request_publish(self,item_id,version,formats,sha):
        if formats not in (['cards'],['reel'],['cards','reel']):raise ValueError('게시 형식을 선택해 주세요.')
        if self.status['busy']:raise ValueError('진행 중인 작업이 끝난 뒤 게시해 주세요.')
        item,reel=self.validate(item_id,version,sha if 'reel' in formats else None)
        if 'reel' in formats and not sha:raise ValueError('확인한 영상의 버전이 필요합니다.')
        with self.store.connect() as db:
            for kind in formats:
                if db.execute('SELECT 1 FROM studio_posts WHERE source_id=? AND kind=?',(item['source_id'],kind)).fetchone():raise ValueError('이미 게시했거나 처리 기록이 있는 형식입니다. 기록을 먼저 확인해 주세요.')
        def work():
            try:
                self.validate(item_id,version,sha if 'reel' in formats else None)
                self.store.action(item_id,version,'approve')
                with self.store.connect() as db:
                    for kind in formats:db.execute("INSERT INTO studio_posts(source_id,kind,item_id,version,sha,state) VALUES(?,?,?,?,?,'queued')",(item['source_id'],kind,item_id,version,sha if kind=='reel' else None))
                for kind in formats:self.publish(item,kind,sha)
                self.status={'busy':False,'stage':'done','message':'게시 처리를 마쳤습니다. 형식별 결과와 링크를 확인해 주세요.'}
            except Exception:
                with self.store.connect() as db:db.execute("UPDATE studio_posts SET state='interrupted',error='연결 또는 처리 상태 확인 필요. 자동 재전송하지 않습니다.' WHERE source_id=? AND state IN ('queued','working','creating','processing','sending')",(item['source_id'],))
                raise
        self.start(work)

    def change(self,source,kind,**values):
        if not set(values)<={'state','container','media_id','link','error'}:raise ValueError('상태 필드 오류')
        with self.store.connect() as db:db.execute('UPDATE studio_posts SET '+','.join(k+'=?' for k in values)+' WHERE source_id=? AND kind=?',(*values.values(),source,kind))

    def publish(self,item,kind,sha):
        from .credentials import load_secret
        from .instagram_api import InstagramAPI
        from .media_host import Cloudinary
        cfg=json.loads((self.store.root/'config/publishing.json').read_text(encoding='utf-8'))
        api=InstagramAPI(cfg['user_id'],cfg['api_version'],load_secret(self.store.root,'instagram-token'),'https://res.cloudinary.com')
        if api.profile()['username']!=cfg['username'] or not api.limit()['available']:raise ValueError('계정·한도 확인 필요')
        host=Cloudinary(json.loads(load_secret(self.store.root,'cloudinary')));host.capacity()
        source=item['source_id'];self.change(source,kind,state='working')
        self.update(('카드뉴스' if kind=='cards' else '릴스')+'를 게시하고 있습니다. 창을 닫지 마세요.','publishing')
        current,reel=self.validate(item['id'],item['version'],sha if kind=='reel' else None)
        if kind=='cards':
            key=self.store.outbox.schedule(item['id'],item['version']);manifest=self.store.outbox.export(key)
            directory=self.store.root/'data/runtime/publish-packages'/key;urls=[]
            for card in manifest['cards']:
                self.validate(item['id'],item['version']);raw=(directory/card['file']).read_bytes()
                if hashlib.sha256(raw).hexdigest()!=card['sha256']:raise ValueError('JPEG 무결성 오류')
                urls.append(host.upload(raw))
            for _ in range(60):
                self.store.outbox.step(key,api,urls)
                state=next(j for j in self.store.outbox.rows() if j['id']==key)
                if state['state'] in ('published','failed','uncertain','cancelled'):
                    self.change(source,kind,state=state['state'],media_id=state['media_id'],error=state['error']);break
                time.sleep(5)
            else:self.change(source,kind,state='interrupted',error='처리 시간 초과. 상태 확인 필요');return
            media=state['media_id']
        else:
            raw=reel['path'].read_bytes()
            if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('영상 무결성 오류')
            url=host.upload(raw,'video')
            self.validate(item['id'],item['version'],sha)
            self.change(source,kind,state='creating')
            container=api.reel(url,current['content']['caption']);self.change(source,kind,state='processing',container=container)
            for _ in range(60):
                status=api.status(container)
                if status=='FINISHED':break
                if status=='EXPIRED':self.change(source,kind,state='failed',error='영상 컨테이너 만료');return
                time.sleep(5) # ERROR may become FINISHED, observed in the first live Reel.
            else:self.change(source,kind,state='interrupted',error='영상 처리 지연. 상태 확인 필요');return
            self.validate(item['id'],item['version'],sha)
            self.change(source,kind,state='sending');media=api.publish(container);self.change(source,kind,state='published',media_id=media)
        if media:
            result=api.transport('GET',media,{'fields':'id,permalink'})
            self.change(source,kind,link=result.get('permalink'))
