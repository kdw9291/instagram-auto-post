"""Bounded beauty launches and dated place programs from official AP news."""
import json
import re
from pathlib import Path
from functools import partial
from datetime import datetime, timezone, timedelta
from .collector import apgroup_url, apgroup_category
from .editorial import EvidenceError, load_sources, moment, KST, unique
from .products import finish, evidence


def make_news(root,key,at=None):
    at=at or datetime.now(timezone.utc)
    try:
        report=json.loads((Path(root)/'data/runtime/collection/report.json').read_text(encoding='utf-8'))
        entry=next(s for s in report['sources'] if s['id']==key and s.get('adapter')=='apgroup-release')
        url=apgroup_url(entry['url']);published=moment(entry['published']);title=entry['headline']
        if key!='ap-news-'+url.rsplit('/',1)[1][:-5] or published.strftime('%Y-%m-%d') not in url:raise EvidenceError('기사 식별·발표일 불일치')
        if not timedelta(0)<=at-published<timedelta(days=7):raise EvidenceError('뉴스 7일 기한 경과')
        sources=load_sources(root,at,{key:url});text=sources[key]['text']
        header=title+'\n브랜드\n'+published.strftime('%Y-%m-%d')
        if text.count(header)!=1:raise EvidenceError('목록·기사 제목과 날짜 불일치')
        article=text.split(header,1)[1].split('\n목록\n',1)[0]
        category=apgroup_category(title)
        if category!=entry['category']:raise EvidenceError('분야 분류 불일치')
        claims=[evidence(sources,key,'publication',published.date().isoformat(),'article-header')]
        if category=='beauty':c=beauty(key,title,article,published,sources,claims)
        elif category=='place':c=place(key,title,article,published,sources,claims,at)
        else:raise EvidenceError('지원하지 않는 기사')
        end=c.pop('_ends',published+timedelta(days=7))
        c,receipt=finish(c,claims,sources,'apgroup-new-news-v1')
        c['valid_until']=min(moment(c['valid_until']),published+timedelta(days=7),end).isoformat()
        if category=='place':c['caption']=c['caption'].replace('직접 사용·시식 후기','직접 방문 후기').replace('실제 제품·발색·단면','실제 행사 현장·작품')
        receipt['scope']='아모레퍼시픽 기사 제목·발표일·선택 문장 대조'
        return c,receipt
    except EvidenceError:raise
    except (OSError,ValueError,TypeError,KeyError,IndexError,StopIteration) as e:raise EvidenceError('새 뷰티·장소 원문을 확인할 수 없습니다.') from e


def beauty(key,title,article,published,sources,claims):
    brand=title.split(',',1)[0]
    if not re.fullmatch(r'[가-힣]{2,8}',brand) or brand not in article:raise EvidenceError('브랜드 식별 불일치')
    m=unique(r"(?:첫 제품으로|신제품) ['‘]([^'’]{2,40})['’](?:를|을) (?:선보였다|출시했다)\.",article,'제품 출시 문장')
    name=m[1]
    scenes=[(('클렌저','클렌징','팩폼'),'클렌저','Extreme macro photograph of airy white cleansing foam and clear water bubbles on frosted glass, soft clean daylight, only foam and water'),(('크림','세럼'),'스킨케어','Extreme macro photograph of creamy white emulsion spread on frosted glass, soft ivory light, only cream texture'),(('틴트','립스틱'),'립 제품','Extreme macro photograph of ruby red glossy gel pigment on glass, luminous shine, only gel texture')]
    choice=next(((label,scene) for words,label,scene in scenes if any(w in name for w in words)),None)
    if not choice:raise EvidenceError('제품 이미지 장면 규칙 없음')
    label,scene=choice
    channel='공식 판매처 확인'
    if '병의원 판매' in title:
        if not re.search(re.escape(name)+r"['’]는[^.\n]*국내 병의원에서 만나볼 수 있다\.",article):raise EvidenceError('판매 채널 문장 없음')
        channel='병의원 판매 · 취급 문의'
    claims.extend([evidence(sources,key,'brand',brand,'headline-brand'),evidence(sources,key,'product',name,'first-product-launch-sentence')])
    if channel!='공식 판매처 확인':claims.append(evidence(sources,key,'channel',channel,'product-sales-sentence'))
    return {'source_id':key,'category':'beauty','title':brand+' 새 '+label+'\n공식 출시 소식','subtitle':name+'\n브랜드 공식 발표 기준',
        'intro_heading':'새 제품 소식','intro':name+f'\n{published:%Y.%m.%d} 공식 발표\n제품 사용 후기는 아닙니다.',
        'facts':[{'label':'공식 발표일','value':f'{published:%Y.%m.%d}'},{'label':'판매 안내','value':channel},{'label':'구매 전 확인','value':'가격·재고·사용 안내는 판매처 확인'}],
        'cta':'제품 소식 저장\n판매처에서 확인','conditions':'개인별 사용 적합성을 판단하지 않습니다.\n효능·안전성을 보증하는 후기가 아닙니다.',
        'caption':f'{brand}의 {name} 출시 소식입니다. {published:%Y.%m.%d} 공식 자료에서 신제품 발표를 확인했습니다.\n판매 안내: {channel}. 가격·재고·사용 안내는 판매처에서 확인하세요. 효능·개인별 적합성에 대한 판단은 포함하지 않았습니다.',
        'image_subject':scene+'. Editorial visual inspired by a new beauty product, no packaging or writing'}


def place(key,title,article,published,sources,claims,at):
    names=re.findall(r"['‘]([^'’]{2,40})['’]",title)
    if len(names)!=1:raise EvidenceError('행사 이름이 모호합니다.')
    name=names[0]
    pattern=r"([가-힣A-Za-z0-9 ·]{2,35})에서 진행되는 ['‘]"+re.escape(name)+r"['’] (?:프로그램|전시|팝업)(?:은|는) (\d{1,2})월 (\d{1,2})일부터 (?:(\d{1,2})월 )?(\d{1,2})일까지 운영된다\."
    m=unique(pattern,article,'장소·운영 기간');venue=m[1].strip()
    start=datetime(published.year,int(m[2]),int(m[3]),tzinfo=KST);end=datetime(published.year,int(m[4] or m[2]),int(m[5]),tzinfo=KST)+timedelta(days=1)
    if not start<end or not -7<=(start-published).days<=90 or end<=at:raise EvidenceError('행사 기간이 모호하거나 종료됐습니다.')
    conditions=[]
    if '온라인 테스트를 완료한 고객은 '+venue+'에서' in article:conditions.append('온라인 테스트 완료 후 참여')
    for phrase,label in [('사전 예약 후 참여할 수 있다.','사전 예약 후 참여'),('현장 접수 후 참여할 수 있다.','현장 접수 후 참여')]:
        if re.search(r"['‘]"+re.escape(name)+r"['’](?:은|는) "+re.escape(phrase),article):conditions.append(label)
    if len(conditions)!=1:raise EvidenceError('현재 지원하는 참가 조건이 없거나 모호합니다.')
    condition=conditions[0]
    extra='운영시간·참여 세부 조건은 공식 안내 확인'
    if '추첨' in article:
        if "'북촌의 밤' 프로그램은 추첨을 통해 선정된 고객을 대상으로" not in article:raise EvidenceError('추첨 대상 프로그램 분리 확인 필요')
        extra='별도 야간 프로그램은 추첨 선정 대상'
    if '북촌' in venue:scene='Fictional Korean hanok courtyard with wooden doors and a quiet stone path, warm autumn afternoon sunlight, cultural walk atmosphere, no people or signage'
    elif any(w in venue for w in ('미술관','전시장','갤러리')):scene='Fictional contemporary museum gallery, simple architectural volumes, spacious interior, soft daylight, no identifiable artworks or people'
    elif any(w in venue for w in ('팝업','쇼룸')):scene='Fictional contemporary pop-up showroom with modular display plinths, warm spotlights and natural materials, no products, logos or people'
    else:raise EvidenceError('장소 관련 이미지 장면 규칙 없음')
    period=f'{start:%Y.%m.%d} — {end-timedelta(days=1):%m.%d}'
    claims.extend([evidence(sources,key,'program',name,'program-schedule-sentence'),evidence(sources,key,'venue',venue,'same-program-venue'),evidence(sources,key,'period',period,'same-program-dates'),evidence(sources,key,'participation',condition,'same-program-participation-sentence')])
    if '추첨' in article:claims.append(evidence(sources,key,'separate_night_program',extra,'night-program-selection'))
    return {'source_id':key,'category':'place','title':'북촌 새 프로그램\n일정과 참여 조건' if '북촌' in venue else '새 전시·팝업\n일정과 참여 조건','subtitle':name,'intro_heading':'일정부터 확인해요','intro':venue+'\n'+period+'\n'+condition,
        'facts':[{'label':'진행 장소','value':venue},{'label':'참여 조건','value':condition},{'label':'추가 확인','value':extra}],
        'cta':'방문 전 확인\n참여 조건과 시간','conditions':'운영시간·예약 여부는 공식 안내 확인\n'+extra,'caption':name+' 프로그램 소식입니다.\n장소: '+venue+'\n기간: '+period+'\n참여 조건: '+condition+'\n'+extra+'\n입장료·운영시간·예약 조건은 공식 안내에서 확인하세요.',
        'image_subject':scene+'. Photographic editorial interpretation, not a real venue photograph','_ends':end}


def adapters(root):
    try:report=json.loads((Path(root)/'data/runtime/collection/report.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):return []
    return [(s['id'],partial(make_news,key=s['id'])) for s in report.get('sources',[]) if s.get('adapter')=='apgroup-release' and re.fullmatch(r'ap-news-20\d{2}-\d{2}-\d{2}(?:-\d{1,2})?',s.get('id',''))]
