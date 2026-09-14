"""Explicit per-asset rights registry. Absence of restrictions is not permission."""
import hashlib,io,json,re,urllib.request,socket,ipaddress
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit
from PIL import Image

PERMISSIONS=('commercial','social','edit','video','hosting')

def registry(root):
    try:return json.loads((Path(root)/'config/media-rights.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):return {'mode':'rights_verified_first','assets':[]}

def approved(root,content):
    cfg=registry(root)
    if cfg.get('mode')!='rights_verified_first':return None
    for entry in cfg.get('assets',[]):
        try:
            if entry['source_id']!=content['source_id'] or entry['source_url'] not in content['sources']:continue
            if entry['status']!='allowed' or entry.get('subject_verified') is not True:continue
            if not all(entry['permissions'].get(p) is True for p in PERMISSIONS):continue
            until=datetime.fromisoformat(entry['valid_until'])
            if until.tzinfo is None or until<=datetime.now(timezone.utc):continue
            if not all(isinstance(entry[k],str) and entry[k].strip() for k in ('credit','rights_url','rights_text','checked_at')):continue
            if not re.fullmatch('[a-f0-9]{64}',entry['image_sha256']):continue
            evidence=Path(root)/'data/rights'/entry['evidence_file']
            if not evidence.resolve().is_relative_to((Path(root)/'data/rights').resolve()):continue
            if hashlib.sha256(evidence.read_bytes()).hexdigest()!=entry['evidence_sha256']:continue
            url=urlsplit(entry['image_url'])
            if url.scheme!='https' or not url.hostname or url.username or url.password or url.port not in (None,443):continue
            return entry
        except (OSError,ValueError,KeyError,TypeError):continue
    return None

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('이미지 리다이렉트 차단')

def download(url):
    host=urlsplit(url).hostname
    if not all(ipaddress.ip_address(r[4][0]).is_global for r in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)):
        raise ValueError('공개 이미지 주소 필요')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    with opener.open(urllib.request.Request(url,headers={'User-Agent':'AutoInstaMedia/1.0'}),timeout=15) as response:
        if response.headers.get_content_type() not in ('image/jpeg','image/png','image/webp'):raise ValueError('이미지 형식 오류')
        raw=response.read(8_000_001)
    if len(raw)>8_000_000:raise ValueError('이미지 크기 초과')
    return raw

def select(root,content,acquire=False,transport=None):
    entry=approved(root,content)
    if entry is None:return None
    try:
        rawpath=Path(root)/'data/runtime/provided-originals'/entry['image_sha256']
        if rawpath.exists():raw=rawpath.read_bytes()
        elif acquire:raw=(transport or download)(entry['image_url'])
        else:return None
        if hashlib.sha256(raw).hexdigest()!=entry['image_sha256']:return None
        with Image.open(io.BytesIO(raw)) as im:
            if min(im.size)<720 or im.width*im.height>25_000_000 or getattr(im,'n_frames',1)!=1:return None
            im.load();buf=io.BytesIO();im.convert('RGB').save(buf,format='PNG');png=buf.getvalue()
        digest=hashlib.sha256(png).hexdigest();path=Path(root)/'assets/images/news'/f'{digest}.png'
        if acquire:
            rawpath.parent.mkdir(parents=True,exist_ok=True);rawpath.write_bytes(raw)
            path.parent.mkdir(parents=True,exist_ok=True)
            if not path.exists():path.write_bytes(png)
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:return None
        proof=hashlib.sha256(json.dumps(entry,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        return {'id':digest,'sha256':digest,'kind':'provided','policy':'verified-rights-v1','rights_hash':proof,'credit':entry['credit'],'source_url':entry['source_url'],'image_url':entry['image_url'],'rights_url':entry['rights_url']}
    except (OSError,ValueError,KeyError,Image.DecompressionBombError):return None

def attach_provided(content,asset):
    caption=re.sub(r'배경은 [^\n]*?\.(?=\n|$)','',content['caption'])
    caption+='\n사진 제공: '+asset['credit']+'\n사진 출처: '+asset['source_url']+'\n이용 조건: '+asset['rights_url']+'\n사진 편집: 카드 비율 조정·텍스트 배치. 마지막 브랜드 카드는 AI 제작입니다.'
    if len(caption)>2200:return None
    return dict(content,news_image=asset,caption=caption,conditions=content.get('conditions','').replace('배경은 실제 제품 사진이 아닙니다.',''))
