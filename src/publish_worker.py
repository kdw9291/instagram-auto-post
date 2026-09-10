"""Opt-in live publishing; all credential and approval gates precede upload."""
import json
import hashlib
from datetime import datetime,timezone
from pathlib import Path
from .credentials import load_secret
from .instagram_api import InstagramAPI
from .media_host import Cloudinary


def tick(store):
    path=store.root/'config/publishing.json'
    if not path.exists():return
    config=json.loads(path.read_text(encoding='utf-8'))
    if config.get('enabled') is not True:return
    if config.get('provider')!='cloudinary':raise ValueError('이미지 저장소 설정 확인 필요')
    jobs=[j for j in store.outbox.rows() if j['state'] in ('prepared','containers','ready','sending')]
    if not jobs:return
    selected=sorted(jobs,key=lambda j:j['due'])[0]
    if datetime.fromisoformat(selected['due'])>datetime.now(timezone.utc):return
    key=selected['id']
    directory=store.root/'data/runtime/publish-packages'/key
    last=directory/'last-attempt.txt'
    if last.exists() and datetime.now(timezone.utc).timestamp()-float(last.read_text())<60:return
    directory.mkdir(parents=True,exist_ok=True);last.write_text(str(datetime.now(timezone.utc).timestamp()))
    api=InstagramAPI(config['user_id'],config['api_version'],load_secret(store.root,'instagram-token'),'https://res.cloudinary.com')
    if api.profile()['username']!=config['username']:raise ValueError('운영 계정 불일치')
    if not api.limit()['available']:return
    host=Cloudinary(json.loads(load_secret(store.root,'cloudinary')))
    host.capacity()
    manifest=store.outbox.export(key);record=directory/'hosted.json'
    hosted=json.loads(record.read_text(encoding='utf-8')) if record.exists() else {}
    urls=[]
    for card in manifest['cards']:
        digest=card['sha256'];url=hosted.get(digest)
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            store.outbox.eligible(db,manifest['item_id'],manifest['version'])
            if url:host.verify(url,digest)
            else:
                raw=(directory/card['file']).read_bytes()
                if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('업로드 직전 JPEG 변경')
                url=host.upload(raw);host.verify(url,digest);hosted[digest]=url
                temp=record.with_suffix('.tmp');temp.write_text(json.dumps(hosted),encoding='utf-8');temp.replace(record)
        urls.append(url)
    store.outbox.step(key,api,urls)
