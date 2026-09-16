"""Evidence-bound APMA adapter and deterministic editorial composition.

No LLM or inferred reviews. Unsupported sources remain discovery candidates.
"""
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .collector import normalize

KST=timezone(timedelta(hours=9))
POLICY='apma-evidence-v1'
SOURCE_URLS={
 'apma-guide':'https://apma.amorepacific.com/visit/guide.do',
 'apma-faq':'https://apma.amorepacific.com/visit/faq/faq.do',
 'apgroup-exhibition':'https://www.apgroup.com/int/ko/news/2026-08-21-2.html',
}

class EvidenceError(ValueError):pass

def moment(value):
    result=datetime.fromisoformat(value)
    if result.tzinfo is None:raise EvidenceError('근거 시각에 시간대가 없습니다.')
    return result

def load_sources(root,at,urls=None):
    directory=Path(root)/'data/runtime/collection'
    try:report=json.loads((directory/'report.json').read_text(encoding='utf-8'))
    except (OSError,ValueError) as e:raise EvidenceError('수집 결과를 기다립니다.') from e
    entries={s['id']:s for s in report['sources']};sources={}
    for key,url in (urls or SOURCE_URLS).items():
        entry=entries.get(key,{})
        h=entry.get('snapshot_hash','')
        if entry.get('status')!='ok' or entry.get('url')!=url or not re.fullmatch('[a-f0-9]{64}',h):
            raise EvidenceError(f'{key}: 정상 수집 근거가 없습니다.')
        try:
            raw=(directory/f'{key}-{h}.json').read_bytes()
            if hashlib.sha256(raw).hexdigest()!=h:raise EvidenceError(f'{key}: 원문 무결성 확인 실패')
            source=json.loads(raw)
        except (OSError,ValueError) as e:raise EvidenceError(f'{key}: 원문 스냅샷을 확인할 수 없습니다.') from e
        checked=moment(source['checked_at'])
        if source['url']!=url or source['checked_at']!=entry['checked_at']:
            raise EvidenceError(f'{key}: 원문과 수집 기록 불일치')
        if checked>at+timedelta(minutes=5) or at-checked>=timedelta(hours=12):
            raise EvidenceError(f'{key}: 원문 확인 기한이 지났습니다.')
        source['hash']=h;sources[key]=source
    return sources

def unique(pattern,text,field):
    matches=list(re.finditer(pattern,text,re.MULTILINE))
    if len(matches)!=1:raise EvidenceError(f'{field}: 근거가 없거나 여러 값이 있습니다.')
    return matches[0]

def adult_price(source):
    found=[]
    for table_index,table in enumerate(source['tables']):
        prices=[r for r in table if r and r[0]=='가격'];targets=[r for r in table if r and r[0]=='대상']
        if len(prices)!=1 or len(targets)!=1 or len(prices[0])!=len(targets[0]):continue
        for col,target in enumerate(targets[0][1:],start=1):
            age=re.fullmatch(r'성인\s*\(만\s*(\d+)세\s*이상\)',target)
            if not age:continue
            price=re.fullmatch(r'([\d,]+)원',prices[0][col])
            if not price:raise EvidenceError('성인 요금 형식을 확인할 수 없습니다.')
            found.append(({'amount':int(price[1].replace(',','')),'age':int(age[1])},f'table:{table_index},column:{col}'))
    if len(found)!=1:raise EvidenceError('성인 대상과 같은 열의 요금을 확인할 수 없습니다.')
    return found[0]

def extract(sources,at):
    claims=[];values={}
    def claim(field,value,key,locator):
        source=sources[key]
        claims.append({'field':field,'value':value,'source_id':key,'url':source['url'],'snapshot_hash':source['hash'],'locator':locator})
        if field in values and values[field]!=value:raise EvidenceError(f'{field}: 공식 출처의 값이 서로 다릅니다.')
        values[field]=value
    news=sources['apgroup-exhibition']['text'];guide=sources['apma-guide']['text'];faq=sources['apma-faq']['text']
    match=unique(r'^전시제목:\s*《([^》]+)》$',news,'전시 제목')
    title=match[1].strip();claim('event_title',title,'apgroup-exhibition',f'text:{match.start()}:{match.end()}')
    if title!='Sol LeWitt: Open Structure' or '솔 르윗' not in news:
        raise EvidenceError('현재 전시의 제목·작가 어댑터가 필요합니다.')
    if normalize('《'+title+'》') not in normalize(guide):raise EvidenceError('관람 안내가 다른 전시를 가리킵니다.')
    claim('event_title',title,'apma-guide','current-exhibition-heading')
    dates=unique(r'^전시기간:\s*(\d{4})년\s*(\d+)월\s*(\d+)일\s*\([^)]+\)\s*~\s*(\d{4})년\s*(\d+)월\s*(\d+)일\s*\([^)]+\)',news,'전시 기간')
    start=datetime(*map(int,dates.groups()[:3]),tzinfo=KST).date();end=datetime(*map(int,dates.groups()[3:]),tzinfo=KST).date()
    if not start<=at.astimezone(KST).date()<=end:raise EvidenceError('현재 관람 가능한 전시 기간이 아닙니다.')
    claim('dates',{'start':start.isoformat(),'end':end.isoformat()},'apgroup-exhibition',f'text:{dates.start()}:{dates.end()}')
    hours=unique(r'관람안내\s+관\s*람\s*시\s*간\s+화~일요일\s*(\d{2}:\d{2})\s*~\s*(\d{2}:\d{2})',guide,'관람 시간')
    opening,closing=hours.groups()
    if not opening<closing:raise EvidenceError('관람 시간 순서를 확인할 수 없습니다.')
    claim('hours',[opening,closing],'apma-guide',f'text:{hours.start()}:{hours.end()}')
    faq_hours=unique(r'오전\s*(\d+)시부터\s*오후\s*(\d+)시까지\(입장마감은\s*오후\s*(\d+)시\s*(\d+)분\)',faq,'FAQ 관람 시간')
    h1,h2,h3,minute=map(int,faq_hours.groups());cutoff=f'{h3%12+12:02}:{minute:02}'
    claim('hours',[f'{h1:02}:00',f'{h2%12+12:02}:00'],'apma-faq',f'text:{faq_hours.start()}:{faq_hours.end()}')
    if not opening<cutoff<closing:raise EvidenceError('입장마감이 관람시간 범위를 벗어납니다.')
    claim('last_entry',cutoff,'apma-faq',f'text:{faq_hours.start()}:{faq_hours.end()}')
    closure=unique(r'^매주 월요일, 매년 1월 1일, 설/추석 연휴$',guide,'휴관 조건')
    claim('closures','월요일 · 1월 1일 · 설·추석 연휴','apma-guide',f'text:{closure.start()}:{closure.end()}')
    if '정기휴관일은 매주 월요일, 1월 1일 / 설, 추석 연휴입니다.' not in faq:raise EvidenceError('FAQ 휴관 조건이 다릅니다.')
    claim('closures',values['closures'],'apma-faq','closure-sentence')
    reservation=unique(r'^이번 전시의 관람을 위해서는 온라인 사전 예약이 필요합니다\.$',guide,'예약 조건')
    claim('reservation','온라인 사전예약 필수','apma-guide',f'text:{reservation.start()}:{reservation.end()}')
    place=unique(r'^전시장소:\s*아모레퍼시픽미술관\s*\(서울시 용산구 한강대로 (\d+)\)',news,'장소')
    address=f'서울 용산구 한강대로 {place[1]}'
    if f'서울특별시 용산구 한강대로 {place[1]}에 위치' not in faq:raise EvidenceError('공식 출처의 주소가 일치하지 않습니다.')
    claim('address',address,'apgroup-exhibition',f'text:{place.start()}:{place.end()}')
    for key in ('apma-guide','apgroup-exhibition'):
        price,locator=adult_price(sources[key]);claim('adult_price',price,key,locator)
    return values,claims

def compose(values,claims,sources):
    dates=values['dates'];period=f"{dates['start'].replace('-','.')} — {dates['end'].replace('-','.')}"
    opening,closing=values['hours'];last=values['last_entry'];price=values['adult_price']
    fee=f"성인(만 {price['age']}세 이상) {price['amount']:,}원"
    checked=min(moment(s['checked_at']) for s in sources.values())
    end=datetime.fromisoformat(dates['end']+'T'+closing).replace(tzinfo=KST)
    valid_until=min(checked+timedelta(hours=12),end)
    facts=[{'label':'관람시간 · 입장마감','value':f'{opening}–{closing} · {last} 입장마감'}, {'label':'휴관일','value':values['closures']},{'label':'관람료','value':fee}]
    caption=f"용산에서 만나는 솔 르윗 전시.\n\n{values['event_title']}\n기간: {period}\n장소: 아모레퍼시픽미술관 · {values['address']}\n관람: {opening}–{closing} · 입장마감 {last}\n휴관: {values['closures']}\n관람료: {fee}\n{values['reservation']}. 방문일과 잔여 티켓은 공식 홈페이지에서 확인하세요.\n\n공식 자료를 정리한 정보이며 직접 방문 후기가 아닙니다. 배경은 전시 주제 일러스트입니다.\n출처:\n"+'\n'.join(SOURCE_URLS.values())+f"\n확인: {checked.astimezone(KST):%Y.%m.%d}"
    return {'source_id':'apma-auto-4128332','sample':False,'category':'place','title':'용산에서 만나는\n솔 르윗 전시','subtitle':f'아모레퍼시픽미술관\n{period}',
      'intro_heading':'전시 일정과 장소','intro':f"{values['event_title']}\n{period}\n{values['address']}", 'facts':facts,'cta':'온라인\n사전예약 필수',
      'conditions':'방문일과 잔여 티켓은\n공식 홈페이지에서 확인하세요.', 'source_label':f'APMA 공식 자료 대조\n확인 {checked.astimezone(KST):%Y.%m.%d}',
      'sources':list(SOURCE_URLS.values()),'caption':caption,'verified_at':checked.isoformat(),'valid_until':valid_until.isoformat(),
      'editorial_policy':POLICY}

def make_apma(root,at=None):
    at=at or datetime.now(timezone.utc)
    try:
        sources=load_sources(root,at);values,claims=extract(sources,at)
        content=compose(values,claims,sources)
        content['image_subject']='An imagined contemporary art exhibition about modular geometric structures, white open cubic forms in a spacious museum gallery, architectural perspective, a quiet Seoul culture magazine mood'
        from .render import visual_revision
        content['visual_revision']=visual_revision()
        content['caption']=content['caption'].replace('배경은 전시 주제 일러스트입니다.','배경은 AI 전시 공간 콘셉트이며 실제 현장·작품이 아닙니다.')
        return content,{'policy':POLICY,'claims':claims,'status':'verified','scope':'APMA 전시 자료 전용 규칙 검증'}
    except EvidenceError:raise
    except (KeyError,TypeError,IndexError,ValueError,OSError) as e:raise EvidenceError('원문 또는 배경 자산을 확인할 수 없습니다.') from e

def verify_content(root,content):
    maker=dict(editorial_adapters(root)).get(content.get('source_id'))
    if maker is None:raise EvidenceError('등록된 원고 어댑터가 없습니다.')
    expected,receipt=maker(root)
    from .news_images import attach, ImagePending
    try:expected=attach(root,expected)
    except ImagePending as e:raise EvidenceError(str(e)) from e
    if content!=expected:raise EvidenceError('현재 문구와 근거로 생성한 원고가 다릅니다.')
    return receipt

def editorial_adapters(root=None):
    from .products import make_hera, make_bakery
    from .seoul_events import make_drone
    from .new_releases import adapters
    from .apgroup_releases import adapters as ap_adapters
    from .shinsegae_releases import adapters as shinsegae_adapters
    from .seoul_weekly import make_weekly
    from .seoul_releases import adapters as seoul_release_adapters
    fixed=[('apma-auto-4128332',make_apma),('hera-auto-70922',make_hera),('bgf-auto-2024',make_bakery)]
    dynamic=adapters(root)+ap_adapters(root)+shinsegae_adapters(root)+seoul_release_adapters(root) if root is not None else []
    if root is not None:
        try:
            report=json.loads((Path(root)/'data/runtime/collection/report.json').read_text(encoding='utf-8'))
            if any(s.get('adapter')=='seoul-event' for s in report['sources']):dynamic.append(('seoul-drone-20260912',make_drone))
            weekly={'seoul-calendar-202609','seoul-safety-202609','seoul-market-202609','seoul-phil-202609'}
            if weekly.issubset({s.get('id') for s in report['sources']}):dynamic.append(('seoul-weekly-20260914',make_weekly))
            dates={s['id']:moment(s['published']).timestamp() for s in report['sources'] if s.get('published')}
            dynamic.sort(key=lambda pair:(-dates.get(pair[0],0),pair[0]))
        except (OSError,ValueError,KeyError):pass
    return dynamic+fixed
