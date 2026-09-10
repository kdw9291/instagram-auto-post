"""Instagram Login publishing adapter; intentionally not wired to a live worker."""
import json
import re
import urllib.request
from urllib.parse import urlencode,urlsplit

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('API 리다이렉트 차단')

class InstagramAPI:
    def __init__(self,user_id,version,token,media_origin,transport=None):
        if not re.fullmatch(r'[0-9]+',user_id) or not re.fullmatch(r'v[0-9]+\.0',version):raise ValueError('계정 ID·API 버전 확인 필요')
        origin=urlsplit(media_origin)
        if origin.scheme!='https' or not origin.hostname or origin.username or origin.password or origin.port or origin.path not in ('','/') or origin.query or origin.fragment:raise ValueError('공개 HTTPS 이미지 호스트 필요')
        if not token or any(c in token for c in '\r\n'):raise ValueError('유효한 인증 필요')
        self.user_id=user_id;self.version=version;self.origin='https://'+origin.netloc
        self.transport=transport or self._transport(token)

    def _transport(self,token):
        def call(method,path,values):
            url='https://graph.instagram.com/'+self.version+'/'+path
            data=urlencode(values).encode()
            if method=='GET':url+='?'+data.decode();data=None
            request=urllib.request.Request(url,data=data,method=method,headers={'Authorization':'Bearer '+token,'Content-Type':'application/x-www-form-urlencoded'})
            try:
                opener=urllib.request.build_opener(NoRedirect())
                with opener.open(request,timeout=15) as response:
                    raw=response.read(1_000_001)
                if len(raw)>1_000_000:raise ValueError('응답 상한')
                result=json.loads(raw)
                if not isinstance(result,dict) or 'error' in result:raise ValueError('API 응답 오류')
                return result
            except (OSError,ValueError):
                # Never persist exception URLs, token-bearing requests, or response bodies.
                raise OSError('Instagram API 응답 확인 실패') from None
        return call

    def image(self,url):
        parsed=urlsplit(url)
        if parsed.scheme+'://'+parsed.netloc!=self.origin or parsed.fragment or parsed.query or not parsed.path.endswith('.jpg'):raise ValueError('등록된 JPEG 주소 필요')
        return self.transport('POST',self.user_id+'/media',{'image_url':url,'is_carousel_item':'true'})['id']

    def carousel(self,children,caption):
        if len(children)!=4 or any(not isinstance(x,str) or not x.isdigit() for x in children):raise ValueError('카드 컨테이너 4개 필요')
        return self.transport('POST',self.user_id+'/media',{'media_type':'CAROUSEL','children':','.join(children),'caption':caption})['id']

    def reel(self,url,caption):
        parsed=urlsplit(url)
        if parsed.scheme+'://'+parsed.netloc!=self.origin or parsed.fragment or parsed.query or not parsed.path.endswith('.mp4'):raise ValueError('등록된 MP4 주소 필요')
        return self.transport('POST',self.user_id+'/media',{'media_type':'REELS','video_url':url,'caption':caption,'share_to_feed':'true'})['id']

    def status(self,container):
        if not str(container).isdigit():raise ValueError('컨테이너 ID 오류')
        return self.transport('GET',container,{'fields':'status_code'})['status_code']

    def publish(self,container):
        if not str(container).isdigit():raise ValueError('컨테이너 ID 오류')
        return self.transport('POST',self.user_id+'/media_publish',{'creation_id':container})['id']

    def profile(self):
        result=self.transport('GET','me',{'fields':'user_id,username'})
        if str(result.get('user_id'))!=self.user_id:raise ValueError('연결 계정 ID 불일치')
        return {'user_id':str(result['user_id']),'username':result.get('username')}

    def limit(self):
        data=self.transport('GET',self.user_id+'/content_publishing_limit',{'fields':'quota_usage,config'}).get('data',[])
        if len(data)!=1:raise ValueError('게시 한도 응답 확인 필요')
        usage=data[0].get('quota_usage');total=data[0].get('config',{}).get('quota_total')
        if type(usage) is not int or type(total) is not int or usage<0 or total<=0:raise ValueError('게시 한도 확인 필요')
        return {'usage':usage,'total':total,'available':usage<total}
