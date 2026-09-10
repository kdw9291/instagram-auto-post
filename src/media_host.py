"""Signed Cloudinary uploads with immutable IDs and byte-for-byte delivery checks."""
import base64
import hashlib
import json
import re
import time
import urllib.request
from urllib.parse import urlencode
from .instagram_api import NoRedirect


def request(method,url,body=None,headers=None):
    try:
        req=urllib.request.Request(url,data=body,method=method,headers=headers or {})
        with urllib.request.build_opener(NoRedirect()).open(req,timeout=20) as response:
            raw=response.read(8_000_001)
        if len(raw)>8_000_000:raise ValueError('응답 상한')
        return raw
    except (OSError,ValueError):raise OSError('이미지 저장소 응답 확인 실패') from None


class Cloudinary:
    def __init__(self,credentials,transport=request):
        self.cloud=credentials['cloud_name'];self.key=credentials['api_key'];self.secret=credentials['api_secret'];self.transport=transport
        if not all(isinstance(value,str) for value in (self.cloud,self.key,self.secret)) or not re.fullmatch(r'[a-z0-9_-]{1,80}',self.cloud) or not self.key.isdigit() or not self.secret:raise ValueError('Cloudinary 인증 형식 확인 필요')

    def capacity(self):
        auth=base64.b64encode((self.key+':'+self.secret).encode()).decode()
        result=json.loads(self.transport('GET','https://api.cloudinary.com/v1_1/'+self.cloud+'/usage',headers={'Authorization':'Basic '+auth}))
        credits=result.get('credits',{});used=credits.get('usage');limit=credits.get('limit')
        if str(result.get('plan','')).lower()!='free' or type(used) not in (int,float) or type(limit) not in (int,float) or not 0<=used<limit*.8:raise ValueError('무료 플랜·사용량 확인 필요 또는 80% 상한 도달')
        return {'used':used,'limit':limit}

    def upload(self,raw,kind='image'):
        if kind not in ('image','video'):raise ValueError('미디어 유형 오류')
        valid=raw.startswith(b'\xff\xd8') if kind=='image' else raw[4:8]==b'ftyp'
        if not valid or len(raw)>8_000_000:raise ValueError('미디어 형식·크기 확인 필요')
        extension='jpg' if kind=='image' else 'mp4'
        mime='image/jpeg' if kind=='image' else 'video/mp4'
        digest=hashlib.sha256(raw).hexdigest();public_id='auto-insta/'+digest
        params={'overwrite':'false','public_id':public_id,'timestamp':str(int(time.time()))}
        signature=hashlib.sha1(('&'.join(k+'='+params[k] for k in sorted(params))+self.secret).encode()).hexdigest()
        values=dict(params,signature=signature,api_key=self.key,file='data:'+mime+';base64,'+base64.b64encode(raw).decode())
        result=json.loads(self.transport('POST','https://api.cloudinary.com/v1_1/'+self.cloud+'/'+kind+'/upload',urlencode(values).encode(),{'Content-Type':'application/x-www-form-urlencoded'}))
        version=result.get('version')
        if result.get('public_id')!=public_id or type(version) is not int or version<=0:raise ValueError('업로드 응답 식별 불일치')
        url=f'https://res.cloudinary.com/{self.cloud}/{kind}/upload/v{version}/{public_id}.{extension}'
        self.verify(url,digest,kind)
        return url

    def verify(self,url,digest,kind='image'):
        if kind not in ('image','video'):raise ValueError('미디어 유형 오류')
        extension='jpg' if kind=='image' else 'mp4'
        pattern=r'https://res\.cloudinary\.com/'+re.escape(self.cloud)+'/'+kind+r'/upload/v[1-9][0-9]*/auto-insta/'+re.escape(digest)+r'\.'+extension
        if not re.fullmatch(pattern,url):raise ValueError('등록된 원본 이미지 URL이 아닙니다.')
        if hashlib.sha256(self.transport('GET',url)).hexdigest()!=digest:raise ValueError('공개 이미지가 승인 원본과 다릅니다.')
