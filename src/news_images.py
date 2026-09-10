"""Per-news, persistent local image jobs. No paid nodes or cloud fallback."""
import hashlib
import io
import json
import sqlite3
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlencode
from PIL import Image

POLICY='news-photo-v1'
ENDPOINT='http://127.0.0.1:8188'

class ImagePending(ValueError):pass

def settings(root):
    path=Path(root)/'config/images.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'required':False}

def brief(content,config=None):
    subject=content.get('image_subject')
    if not subject:raise ImagePending('뉴스별 이미지 장면 설명이 필요합니다.')
    prompt=('Photorealistic editorial photograph, portrait composition. '+subject+
            '. Natural material texture, realistic shadows, elegant directional light, 50mm lens. '
            'Focal scene in upper two thirds, calm dark lower third for a title. '
            'Fictional illustrative scene inspired by the news, not documentary evidence. '
            'No text, logos, brand packaging, real artwork replicas, people or watermark.')
    identity={k:content.get(k) for k in ('source_id','title','intro','facts','image_subject')}
    config=config or {}
    generation={k:config.get(k) for k in ('provider','checkpoint')}
    generation['steps']=min(40,max(12,config.get('steps',24)))
    key=hashlib.sha256(json.dumps([POLICY,identity,generation],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    return key,prompt

def connect(root):
    path=Path(root)/'data/runtime/images.sqlite3';path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path,timeout=30);db.row_factory=sqlite3.Row
    db.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, source_id TEXT, prompt TEXT, state TEXT, remote_id TEXT, sha TEXT, error TEXT, next_try REAL DEFAULT 0, created REAL, attempts INTEGER DEFAULT 0)')
    return db

def rows(root):
    db=connect(root)
    try:return [dict(r) for r in db.execute('SELECT id,source_id,state,error,created FROM jobs ORDER BY created DESC LIMIT 30')]
    finally:db.close()

def attach(root,content,enqueue=False):
    if not settings(root).get('required') or content.get('sample'):return content
    key,prompt=brief(content,settings(root));db=connect(root)
    try:
        with db:
            if enqueue:
                db.execute("UPDATE jobs SET state='superseded' WHERE source_id=? AND id<>? AND state='queued'",(content['source_id'],key))
                db.execute('INSERT OR IGNORE INTO jobs(id,source_id,prompt,state,created) VALUES(?,?,?,?,?)',(key,content['source_id'],prompt,'queued',time.time()))
                db.execute("UPDATE jobs SET state='queued',next_try=0,error=NULL WHERE id=? AND state='cancelled'",(key,))
            row=db.execute('SELECT * FROM jobs WHERE id=?',(key,)).fetchone()
        if not row or row['state']!='ready':raise ImagePending('뉴스별 이미지 생성 대기')
        path=Path(root)/'assets/images/news'/f'{key}.png'
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha']:raise ImagePending('뉴스 이미지 파일 무결성 확인 실패')
        return dict(content,news_image={'id':key,'sha256':row['sha'],'policy':POLICY})
    finally:db.close()

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('로컬 이미지 엔진 리다이렉트 차단')

def call(path,body=None,binary=False):
    request=urllib.request.Request(ENDPOINT+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    with opener.open(request,timeout=8) as response:
        raw=response.read(20_000_001)
    if len(raw)>20_000_000:raise ValueError('이미지 응답 크기 초과')
    return raw if binary else json.loads(raw)

def workflow(prompt,key,config):
    return {
      '1':{'class_type':'CheckpointLoaderSimple','inputs':{'ckpt_name':config['checkpoint']}},
      '2':{'class_type':'CLIPTextEncode','inputs':{'clip':['1',1],'text':prompt}},
      '3':{'class_type':'CLIPTextEncode','inputs':{'clip':['1',1],'text':'drawing, illustration, cartoon, text, letters, logo, watermark, blurry, deformed'}},
      '4':{'class_type':'EmptyLatentImage','inputs':{'width':832,'height':1088,'batch_size':1}},
      '5':{'class_type':'KSampler','inputs':{'model':['1',0],'positive':['2',0],'negative':['3',0],'latent_image':['4',0],'seed':int(key[:12],16),'steps':min(40,max(12,config.get('steps',24))),'cfg':6.5,'sampler_name':'euler','scheduler':'normal','denoise':1}},
      '6':{'class_type':'VAEDecode','inputs':{'samples':['5',0],'vae':['1',2]}},
      '7':{'class_type':'SaveImage','inputs':{'images':['6',0],'filename_prefix':'auto-insta/'+key}},
    }

def tick(root,transport=call):
    config=settings(root)
    if not config.get('required'):return
    if config.get('provider')!='comfyui-local':raise ValueError('등록되지 않은 이미지 공급자')
    from .operations import settings as operation_settings
    retry=operation_settings(root)
    db=connect(root)
    try:
        with db:
            db.execute("UPDATE jobs SET state='queued',remote_id=NULL,error=NULL WHERE state='failed' AND next_try>0 AND next_try<=? AND attempts<=?",(time.time(),retry['retry_limit']))
        lost=db.execute("SELECT * FROM jobs WHERE state='uncertain' AND next_try<=? ORDER BY created LIMIT 1",(time.time(),)).fetchone()
        if lost:
            try:
                history=transport('/history');queue=transport('/queue')
                prompts=[(pid,entry.get('prompt',[])) for pid,entry in history.items()]
                prompts += [(p[1],p) for p in queue.get('queue_running',[])+queue.get('queue_pending',[]) if len(p)>3]
                match=next((pid for pid,p in prompts if len(p)>3 and p[3].get('client_id')==lost['id']),None)
                with db:
                    if match:db.execute("UPDATE jobs SET state='submitted',remote_id=?,error=NULL WHERE id=?",(match,lost['id']))
                    else:db.execute('UPDATE jobs SET next_try=? WHERE id=?',(time.time()+300,lost['id']))
            except (OSError,ValueError,KeyError,TypeError):
                with db:db.execute('UPDATE jobs SET next_try=? WHERE id=?',(time.time()+300,lost['id']))
        with db:
            db.execute('BEGIN IMMEDIATE')
            # An interrupted POST may have been accepted: never blindly submit twice.
            db.execute("UPDATE jobs SET state='uncertain',error='전송 결과 확인 필요' WHERE state='submitting' AND next_try<?",(time.time(),))
            row=db.execute("SELECT * FROM jobs WHERE state='submitted' ORDER BY created LIMIT 1").fetchone()
            if not row:
                if db.execute("SELECT 1 FROM jobs WHERE state='submitting'").fetchone():return
                row=db.execute("SELECT * FROM jobs WHERE state='queued' AND next_try<=? ORDER BY created LIMIT 1",(time.time(),)).fetchone()
            if not row:return
        key=row['id']
        if row['state']=='submitted':
            try:
                history=transport('/history/'+row['remote_id']);entry=history.get(row['remote_id'])
                if not entry:return
                status=entry.get('status',{})
                if status.get('status_str')=='error':
                    with db:db.execute("UPDATE jobs SET state='failed',error='로컬 생성 실패',next_try=? WHERE id=?",(time.time()+retry['retry_minutes']*60,key))
                    return
                if not status.get('completed'):return
                images=entry.get('outputs',{}).get('7',{}).get('images',[])
                if len(images)!=1:raise ValueError('생성 이미지 수 불일치')
                img=images[0]
                if img.get('type')!='output':raise ValueError('출력 이미지가 아닙니다.')
                raw=transport('/view?'+urlencode({k:img.get(k,'') for k in ('filename','subfolder','type')}),binary=True)
                with Image.open(io.BytesIO(raw)) as decoded:
                    if decoded.width<512 or decoded.height<512 or decoded.width*decoded.height>16_000_000:raise ValueError('이미지 규격 오류')
                    decoded.verify()
                out=Path(root)/'assets/images/news';out.mkdir(parents=True,exist_ok=True)
                temp=out/f'{key}.tmp';temp.write_bytes(raw);temp.replace(out/f'{key}.png')
                with db:db.execute("UPDATE jobs SET state='ready',sha=?,error=NULL WHERE id=?",(hashlib.sha256(raw).hexdigest(),key))
            except OSError as e:
                with db:db.execute('UPDATE jobs SET error=? WHERE id=?',('결과 조회 재시도: '+str(e)[:100],key))
            except (ValueError,KeyError) as e:
                with db:db.execute("UPDATE jobs SET state='failed',error=?,next_try=? WHERE id=?",(type(e).__name__+': '+str(e)[:100],time.time()+retry['retry_minutes']*60,key))
            return
        from .operations import generation_allowed
        if not generation_allowed(root,row['source_id']):
            with db:db.execute("UPDATE jobs SET state='cancelled',error='보류 또는 원고 기한 경과' WHERE id=?",(key,))
            return
        try:
            info=transport('/object_info/CheckpointLoaderSimple')
            names=info['CheckpointLoaderSimple']['input']['required']['ckpt_name'][0]
            if config['checkpoint'] not in names:raise ValueError('로컬 생성 모델 설치 대기')
        except (OSError,ValueError,KeyError) as e:
            with db:db.execute('UPDATE jobs SET error=?,next_try=? WHERE id=?',(str(e)[:150],time.time()+300,key))
            return
        with db:
            updated=db.execute("UPDATE jobs SET state='submitting',next_try=?,attempts=attempts+1 WHERE id=? AND state='queued'",(time.time()+60,key)).rowcount
        if not updated:return
        try:
            result=transport('/prompt',{'prompt':workflow(row['prompt'],key,config),'client_id':key})
            if result.get('node_errors') or not result.get('prompt_id'):raise ValueError('생성 요청 검증 실패')
            with db:db.execute("UPDATE jobs SET state='submitted',remote_id=?,error=NULL WHERE id=?",(result['prompt_id'],key))
        except (OSError,ValueError) as e:
            with db:db.execute("UPDATE jobs SET state='uncertain',error=? WHERE id=?",(str(e)[:150],key))
    finally:db.close()
