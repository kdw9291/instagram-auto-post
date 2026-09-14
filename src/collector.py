"""Bounded official-page/RSS discovery and explicit source text comparisons.

Metadata and comparison results never constitute editorial/publishing approval.
"""
import argparse
import hashlib
import json
import re
import urllib.request
import urllib.error
import urllib.robotparser
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime, format_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, urljoin, parse_qsl
from urllib.parse import quote

USER_AGENT = 'AutoInstaResearch/0.1'
MAX_BYTES = 2000000
# Exact endpoints: externally sourced URLs cannot turn this into a general proxy.
ALLOWED = {
 'https://news.seoul.go.kr/culture/archives/534130',
 'https://news.seoul.go.kr/safe/archives/518514?listPage=1',
 'https://news.seoul.go.kr/gov/archives/580737',
 'https://www.seoulphil.or.kr/perf/view?flag=list&langCd=ko&menuFlag=MFLG0001&perfNo=7597',
 'https://news.seoul.go.kr/culture/archives/534345',
 'https://news.seoul.go.kr/culture/archives/534306',
 'https://stories.amorepacific.com/feed/',
 'https://www.shinsegaegroupnewsroom.com/feed/',
 'https://news.seoul.go.kr/culture/feed',
 'https://seoulboard.seoul.go.kr/rss/RSSGenerator?bbsNo=158',

 'https://www.hankyung.com/feed/economy',
 'https://mediahub.seoul.go.kr/news/rss/06',
 'https://www.apgroup.com/int/ko/news/news.html',
 'https://apma.amorepacific.com/visit/guide.do',
 'https://apma.amorepacific.com/visit/faq/faq.do',
 'https://apma.amorepacific.com/contents/exhibition/4128332/view.do',
 'https://www.lghnh.com/news/press/list.jsp',
 'https://www.hankyung.com/feed/life',
 'https://www.apgroup.com/int/ko/news/2026-08-21-2.html',
 'https://stories.amorepacific.com/'+quote('아모레퍼시픽-헤라-선명한-컬러와-크리스탈-광채-담')+'/',
 'https://hera.com/product/'+quote('센슈얼-샤인-틴트')+'/232/category/60/display/1/',
 'https://www.amoremall.com/kr/ko/product/detail?onlineProdSn=70922&onlineProdCode=111070002495',
 'https://origin.bgf.co.kr/bgflive/view/?id=2024&categoryId=1',
 'https://origin.bgf.co.kr/bgflive/detail/?category=pr',
}

def utcnow():return datetime.now(timezone.utc)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('리다이렉트 대상 확인 전 수집 보류')

def request(url):
    opener=urllib.request.build_opener(NoRedirect())
    req=urllib.request.Request(url,headers={'User-Agent':USER_AGENT,'Accept':'text/html,application/rss+xml,application/xml,text/plain'})
    with opener.open(req,timeout=12) as response:
        data=response.read(MAX_BYTES+1)
        if len(data)>MAX_BYTES:raise ValueError('응답 크기 상한 초과')
        return data.decode(response.headers.get_content_charset() or 'utf-8',errors='replace')

def bgf_url(url):
    p=urlsplit(url)
    pairs=parse_qsl(p.query,keep_blank_values=True)
    q=dict(pairs)
    if p.scheme!='https' or p.netloc!='origin.bgf.co.kr' or p.path!='/bgflive/view/' or p.fragment or len(pairs)!=2 or set(q)!={'id','categoryId'} or q['categoryId']!='1' or not re.fullmatch(r'[1-9][0-9]{0,7}',q['id']):
        raise ValueError('지원하지 않는 BGF 기사 주소')
    return 'https://origin.bgf.co.kr/bgflive/view/?id='+q['id']+'&categoryId=1'


def apgroup_url(url):
    p=urlsplit(url)
    if p.scheme!='https' or p.netloc!='www.apgroup.com' or p.query or p.fragment or not re.fullmatch(r'/int/ko/news/20\d{2}-\d{2}-\d{2}(?:-\d{1,2})?\.html',p.path):
        raise ValueError('지원하지 않는 아모레퍼시픽 기사 주소')
    return url


def shinsegae_url(url):
    p=urlsplit(url)
    if p.scheme!='https' or p.netloc!='www.shinsegaegroupnewsroom.com' or p.query or p.fragment or not re.fullmatch(r'/[a-z0-9][a-z0-9-]{2,150}/',p.path):
        raise ValueError('지원하지 않는 신세계 뉴스룸 주소')
    # The RSS entry for this release points at its image-only MEDIA page.
    if p.path=='/diptyque-les-rituels-de-soin-seongsu-popup-3/':
        return 'https://www.shinsegaegroupnewsroom.com/diptyque-les-rituels-de-soin-seongsu-popup/'
    return url


def apgroup_category(title):
    if any(w in title for w in ('선물','기획 세트','모집','연구회','대상 수상')):return None
    if any(w in title for w in ('전시','팝업','시간 여행')):return 'place'
    if '출시' in title and any(w in title for w in ('일리윤','라네즈','헤라','설화수','프리메라','에스트라','이니스프리')):return 'beauty'
    return None


def apgroup_list(raw,url):
    page=Page();page.feed(raw);candidates=[];seen=set()
    for link in page.links:
        text=' '.join(link['text'].split())
        m=re.fullmatch(r'브랜드 (.+) (20\d{2}-\d{2}-\d{2})',text)
        if not m:continue
        category=apgroup_category(m[1])
        if not category:continue
        try:
            target=apgroup_url(urljoin(url,link['href']))
            date=datetime.fromisoformat(m[2]).replace(tzinfo=timezone(timedelta(hours=9)))
        except ValueError:continue
        if target in seen:continue
        seen.add(target)
        candidates.append({'title':m[1],'url':target,'category':category,'published_at':format_datetime(date),'status':'discovered'})
    return {'title':'아모레퍼시픽 새 브랜드 소식','text':'\n'.join(page.parts),'candidates':candidates[:30]}


def apgroup_sources(results,at):
    sources=[];seen={s['url'] for s in results}
    for source in results:
        if source['id']!='apgroup-discovery' or source.get('status')!='ok':continue
        checked=datetime.fromisoformat(source['checked_at'])
        if checked.tzinfo is None or not timedelta(0)<=at-checked<timedelta(hours=12):continue
        for c in source.get('candidates',[]):
            try:
                url=apgroup_url(c['url']);date=parsedate_to_datetime(c['published_at'])
            except (ValueError,TypeError,KeyError):continue
            if c.get('category') not in ('beauty','place') or date.tzinfo is None or not timedelta(0)<=at-date<timedelta(days=7) or url in seen:continue
            seen.add(url);key='ap-news-'+urlsplit(url).path.rsplit('/',1)[1][:-5]
            sources.append({'id':key,'url':url,'kind':'html','name':'아모레퍼시픽 새 '+('장소 소식' if c['category']=='place' else '뷰티 소식'),'category':c['category'],'adapter':'apgroup-release','headline':c['title'],'published':date.isoformat()})
    return sources[:5]


def shinsegae_sources(results,at):
    sources=[];seen={s['url'] for s in results}
    for source in results:
        if source['id']!='shinsegae-rss' or source.get('status')!='ok':continue
        checked=datetime.fromisoformat(source['checked_at'])
        if checked.tzinfo is None or not timedelta(0)<=at-checked<timedelta(hours=12):continue
        for c in source.get('candidates',[]):
            try:url=shinsegae_url(c['url']);date=parsedate_to_datetime(c['published_at'])
            except (ValueError,TypeError,KeyError):continue
            if c.get('category') not in ('place','beauty','food') or date.tzinfo is None or not timedelta(0)<=at-date<timedelta(days=7) or url in seen:continue
            seen.add(url);key='ssg-news-'+hashlib.sha256(url.encode()).hexdigest()[:16]
            sources.append({'id':key,'url':url,'kind':'html','name':'신세계 뉴스룸 새 소식','category':c['category'],'adapter':'shinsegae-release','headline':c['title'],'published':date.isoformat()})
    return sources[:8]


def fetch_allowed(url, transport=request, robots_cache=None, discovered=False):
    if discovered=='apgroup':apgroup_url(url)
    elif discovered=='bgf':bgf_url(url)
    elif discovered=='shinsegae':shinsegae_url(url)
    elif url not in ALLOWED:raise ValueError('등록되지 않은 수집 주소')
    parts=urlsplit(url);origin=f'{parts.scheme}://{parts.netloc}'
    cache=robots_cache if robots_cache is not None else {}
    if origin not in cache:
        try:rules=transport(origin+'/robots.txt')
        except urllib.error.HTTPError as e:
            if e.code==404:rules='User-agent: *\nAllow: /'
            else:raise
        parser=urllib.robotparser.RobotFileParser();parser.parse(rules.splitlines());cache[origin]=parser
    if not cache[origin].can_fetch(USER_AGENT,url):raise ValueError('robots.txt에서 수집 제한')
    return transport(url)

class Page(HTMLParser):
    def __init__(self):
        super().__init__();self.skip=0;self.title_depth=0;self.title=[];self.parts=[];self.links=[];self.anchor=None
        self.tables=[];self.table=None;self.row=None;self.cell=None;self.table_depth=0
        self.div_depth=0;self.captures=[];self.fields={}
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='div':
            self.div_depth+=1
            classes=a.get('class','').split()
            if 'priceInfo__inner-item' in classes:
                for kind in ('origin','discount'):
                    if kind in classes:self.captures.append({'depth':self.div_depth,'key':'price_'+kind,'text':''})
        if tag in ('script','style','noscript','template'):self.skip+=1
        if tag=='title':self.title_depth+=1
        if tag=='a':self.anchor={'href':a.get('href',''),'text':''}
        if tag=='table':
            self.table_depth+=1
            if self.table_depth==1:self.table=[];self.table_supported=True
            else:self.table_supported=False
        if tag=='tr' and self.table_depth==1:self.row=[]
        if tag in ('td','th') and self.row is not None and self.table_depth==1:
            self.cell=''
            if a.get('rowspan','1')!='1' or a.get('colspan','1')!='1':self.table_supported=False
    def handle_endtag(self,tag):
        if tag=='div':
            for capture in self.captures[:]:
                if capture['depth']==self.div_depth:
                    self.fields.setdefault(capture['key'],[]).append(' '.join(capture['text'].split()))
                    self.captures.remove(capture)
            self.div_depth=max(0,self.div_depth-1)
        if tag in ('script','style','noscript','template'):self.skip=max(0,self.skip-1)
        if tag=='title':self.title_depth=max(0,self.title_depth-1)
        if tag=='a' and self.anchor:
            self.links.append(self.anchor);self.anchor=None
        if tag in ('td','th') and self.cell is not None and self.row is not None and self.table_depth==1:
            self.row.append(' '.join(self.cell.split()));self.cell=None
        if tag=='tr' and self.row is not None and self.table_depth==1:
            self.table.append(self.row);self.row=None
        if tag=='table' and self.table_depth:
            self.table_depth-=1
            if self.table_depth==0:
                if self.table_supported:self.tables.append(self.table)
                self.table=None;self.row=None;self.cell=None
    def handle_data(self,data):
        if not self.skip and data.strip():
            for capture in self.captures:capture['text']+=data.strip()+' '
            self.parts.append(data.strip())
            if self.title_depth:self.title.append(data.strip())
            if self.anchor:self.anchor['text']+=data.strip()+' '
            if self.cell is not None:self.cell+=data.strip()+' '

def normalize(value):return re.sub(r'\s+','',value).replace('～','~').replace('–','-')

def classify(title):
    if any(x in title for x in ('선물세트','선물 세트','기획 세트','생활소품','치료','환자','주가','실적','ATM','은행','현금인출','채용','모집')):return None
    if any(brand in title for brand in ('CU','GS25','세븐일레븐','이마트','롯데마트','홈플러스','트레이더스')) and any(action in title for action in ('출시','신상','신제품')) and any(w in title for w in ('빵','베이커리','베이글','쿠키','과자','아이스크림','젤라또','도시락','간편식','김밥','라면','우동','커피','라테')):return 'food'
    if any(w in title for w in ('편의점','마트')) and not any(w in title for w in ('출시','신상','신제품','먹거리','디저트','빵','도시락','김밥','라면','과자','아이스크림')):return None
    cafe=any(brand in title for brand in ('스타벅스','투썸','메가MGC커피','컴포즈커피','이디야','파리바게뜨','뚜레쥬르')) and any(action in title for action in ('출시','선보인다','신메뉴')) and any(w in title for w in ('커피','라떼','음료','티','케이크','샌드위치','디저트','빵'))
    if cafe:return 'food'
    for category, words in [('place',('전시','팝업','미술관','데이트','문화행사','빛축제','야간개장','드론라이트쇼','드론 라이트쇼','메이커 페어','북촌음악회','시간 여행','무료 공연','축제','플리마켓')),('beauty',('화장품','립스틱','틴트','스킨케어','뷰티 신상','클렌저','세럼','선크림','쿠션','에센스','립밤','향수','바디케어','바디 컬렉션','헤어케어')),('food',('편의점','마트 신상','신상 먹거리','신상 디저트','신제품 빵'))]:
        if any(word in title for word in words):return category
    return None

def page_data(raw,url):
    page=Page();page.feed(raw)
    text='\n'.join(page.parts)
    keywords=('전시','팝업','신제품','출시','기획세트','립','뷰티','편의점','디저트','신상')
    candidates=[];seen=set()
    for link in page.links:
        title=' '.join(link['text'].split());target=urljoin(url,link['href'])
        if target in seen or not any(k in title for k in keywords):continue
        if urlsplit(target).scheme!='https' or urlsplit(target).netloc!=urlsplit(url).netloc:continue
        if not 8<=len(title)<=180:continue
        category=classify(title)
        if not category:continue
        seen.add(target);candidates.append({'title':title,'url':target,'category':category,'status':'needs_date','published_at':None})
    return {'title':' '.join(page.title),'text':text,'tables':page.tables,'fields':page.fields,'candidates':candidates[:30]}

def rss_data(raw,url):
    if '<!DOCTYPE' in raw.upper() or '<!ENTITY' in raw.upper():raise ValueError('XML 선언 제한')
    root=ET.fromstring(raw);candidates=[];seen=set();seen_titles=set()
    for item in root.findall('.//item')[:100]:
        title=item.findtext('title','').strip();target=item.findtext('link','').strip()
        if urlsplit(target).scheme!='https' or urlsplit(target).netloc!=urlsplit(url).netloc:continue
        category=classify(title)
        if not title or not category or target in seen or normalize(title) in seen_titles:continue
        published=item.findtext('pubDate');status='needs_date'
        if published:
            try:
                if url=='https://news.seoul.go.kr/culture/feed' and re.fullmatch(r'20\d{2}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}',published):
                    date=datetime.fromisoformat(published).replace(tzinfo=timezone(timedelta(hours=9)))
                    published=format_datetime(date)
                else:date=parsedate_to_datetime(published)
                if date.tzinfo is None:raise ValueError('missing timezone')
                if date>utcnow()+timedelta(minutes=10) or date<utcnow()-timedelta(days=7):continue
                status='discovered'
            except (ValueError,TypeError):pass
        seen.add(target);seen_titles.add(normalize(title))
        candidates.append({'title':title[:180],'url':target,'category':category,'published_at':published, 'status':status})
    return {'title':root.findtext('./channel/title','RSS'),'text':'','candidates':candidates,'fetched_count':len(root.findall('.//item'))}

# Exact, bounded comparison against this previously researched example only.
CHECKS = {
 'apma-guide': [('관람시간','10:00'),('관람 종료','18:00'),('요금 표기','18,000'),('성인 기준','19세'),('정기 휴관','월요일'),('예약 조건','온라인 사전 예약이 필요합니다')],
 'apma-faq': [('입장마감','입장마감은 오후 5시 30분')],
 'apma-exhibition': [('전시 대상','르윗')],
 'apgroup-exhibition': [('전시 대상','르윗'),('시작일','2026년 9월 1일'),('종료일','2027년 2월 28일')]
}

def compare(source_id,text):
    normalized=normalize(text)
    return [{'field':field,'expected':expected,'status':'matched' if normalize(expected) in normalized else 'not_found'} for field,expected in CHECKS.get(source_id,[])]

def dynamic_sources(results,at):
    sources=[];seen={s['url'] for s in results}
    for source in results:
        if source['id']!='bgf-discovery' or source.get('status')!='ok':continue
        checked=datetime.fromisoformat(source['checked_at'])
        if checked.tzinfo is None or not timedelta(0)<=at-checked<timedelta(hours=12):continue
        for c in source.get('candidates',[]):
            if c.get('category')!='food':continue
            m=re.fullmatch(r'보도자료 (\d{2})\.(\d{2})\.(\d{2}) (.+)',c.get('title',''))
            if not m:continue
            try:
                date=datetime(2000+int(m[1]),int(m[2]),int(m[3]),tzinfo=timezone(timedelta(hours=9)))
                url=bgf_url(c['url'])
            except (ValueError,KeyError):continue
            if not timedelta(0)<=at-date<timedelta(days=7) or url in seen:continue
            seen.add(url)
            key='bgf-news-'+dict(parse_qsl(urlsplit(url).query))['id']
            sources.append({'id':key,'url':url,'kind':'html','name':'BGF 새 출시 자료','adapter':'bgf-release','headline':m[4],'published':date.isoformat()})
    return sources[:5]


class Collector:
    def __init__(self,root,transport=request):
        self.root=Path(root);self.transport=transport
        self.directory=self.root/'data/runtime/collection';self.directory.mkdir(parents=True,exist_ok=True)
        self.config=self.root/'config/sources.json'
        self.report=self.directory/'report.json'

    def run(self,force=False):
        if not self.config.exists():return {'sources':[]}
        config=json.loads(self.config.read_text(encoding='utf-8'))
        previous=json.loads(self.report.read_text(encoding='utf-8')) if self.report.exists() else {'sources':[]}
        old={s['id']:s for s in previous['sources']};results=[];robots={}
        pending=list(config['sources'])
        for source in pending:
            prior=old.get(source['id']);at=utcnow()
            if prior and not force and datetime.fromisoformat(prior['next_check'])>at and all(prior.get(k)==source.get(k) for k in ('url','headline','published')):
                results.append(prior)
                if source['id']=='bgf-discovery':pending.extend(dynamic_sources(results,at))
                if source['id']=='apgroup-discovery':pending.extend(apgroup_sources(results,at))
                if source['id']=='shinsegae-rss':pending.extend(shinsegae_sources(results,at))
                continue
            result={**source,'checked_at':at.isoformat(),'next_check':(at+timedelta(hours=max(1,config.get('interval_hours',6)))).isoformat(),'candidates':[],'checks':[]}
            try:
                discovered={'apgroup-release':'apgroup','bgf-release':'bgf','shinsegae-release':'shinsegae'}.get(source.get('adapter'),False)
                raw=fetch_allowed(source['url'],self.transport,robots,discovered=discovered)
                parsed=(apgroup_list if source['id']=='apgroup-discovery' else rss_data if source['kind']=='rss' else page_data)(raw,source['url'])
                if source['kind']=='html' and source['id'] not in ('lghnh-news','bgf-discovery','apgroup-discovery'):parsed['candidates']=[]
                if source['id']=='bgf-discovery':parsed['candidates']=[c for c in parsed['candidates'] if c['title'].startswith('보도자료 ')]
                result.update(status='ok',title=parsed['title'],candidates=parsed['candidates'],checks=compare(source['id'],parsed['text']),fetched_count=parsed.get('fetched_count'),sha256=hashlib.sha256(raw.encode()).hexdigest())
                snapshot={'url':source['url'],'checked_at':result['checked_at'],'text':parsed['text'],'tables':parsed.get('tables',[]),'fields':parsed.get('fields',{})}
                payload=json.dumps(snapshot,ensure_ascii=False,sort_keys=True)
                result['snapshot_hash']=hashlib.sha256(payload.encode()).hexdigest()
                snapshot_path=self.directory/f"{source['id']}-{result['snapshot_hash']}.json"
                snapshot_path.write_text(payload,encoding='utf-8')
                # Source material stays local; no article/media redistribution.
                (self.directory/f"{source['id']}.txt").write_text(parsed['text'],encoding='utf-8')
            except (ValueError,OSError,ET.ParseError) as e:
                result.update(status='unavailable',error=f'{type(e).__name__}: {e}')
            results.append(result)
            if source['id']=='bgf-discovery':pending.extend(dynamic_sources(results,at))
            if source['id']=='apgroup-discovery':pending.extend(apgroup_sources(results,at))
            if source['id']=='shinsegae-rss':pending.extend(shinsegae_sources(results,at))
        report={'updated_at':utcnow().isoformat(),'sources':results,'notice':'발견·문자열 대조 결과이며 원고 전체 사실 검증이나 발행 승인이 아닙니다.'}
        temp=self.report.with_suffix('.tmp');temp.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(self.report)
        return report

def main():
    p=argparse.ArgumentParser();p.add_argument('--force',action='store_true');args=p.parse_args()
    result=Collector(Path(__file__).resolve().parents[1]).run(args.force)
    for s in result['sources']:
        print(json.dumps({'id':s['id'],'status':s['status'],'candidates':len(s['candidates']),'checks':s['checks'],'error':s.get('error')},ensure_ascii=False))

if __name__=='__main__':main()
