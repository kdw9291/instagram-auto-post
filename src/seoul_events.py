"""Bounded Seoul event verification; AI summaries are never evidence."""
import re
from datetime import datetime, timezone, timedelta
from .editorial import EvidenceError, KST, load_sources, moment
from .products import evidence, finish

URLS={f'seoul-event-{n}':f'https://news.seoul.go.kr/culture/archives/{n}' for n in ('534345','534306')}

def extract(sources, at):
    general=sources['seoul-event-534345']['text']
    detail=sources['seoul-event-534306']['text']
    # These markers occur in the publisher's article, after its AI summary.
    if '\n하반기 행사 개요\n' not in general or '지난 공연들의 뜨거운 열기를 이어' not in detail:
        raise EvidenceError('서울시 원문 본문 경계를 확인할 수 없습니다.')
    general=general.split('\n하반기 행사 개요\n',1)[1].split('AI생성태그',1)[0]
    detail=detail.split('지난 공연들의 뜨거운 열기를 이어',1)[1].split('AI생성태그',1)[0]
    compact=lambda t:re.sub(r'\s+','',t)
    g,d=compact(general),compact(detail)
    required_g=('9.12.(토)','20:30~20:45','뚝섬한강공원수변무대','현장방문(무료공연)')
    required_d=('2026.9.12.(토)','20:30-20:45','뚝섬한강공원수변무대','K-야구,서울나잇')
    if not all(x in g for x in required_g) or not all(x in d for x in required_d):
        raise EvidenceError('행사 날짜·장소·메인 공연 시간 대조 실패')
    if not all('기상' in t and '취소' in t for t in (g,d)):
        raise EvidenceError('기상 취소 조건 확인 실패')
    end=datetime(2026,9,12,20,45,tzinfo=KST)
    if not datetime(2026,9,7,tzinfo=KST)<=at<end:
        raise EvidenceError('드론쇼 안내 제작 기한이 아닙니다.')
    claims=[]
    for key in URLS:
        for field,value in [('date','2026-09-12'),('venue','뚝섬한강공원 수변무대'),('main_show','20:30–20:45'),('weather','기상 상황에 따라 지연·취소 가능')]:
            claims.append(evidence(sources,key,field,value,'publisher-body-after-ai-summary'))
    claims.append(evidence(sources,'seoul-event-534345','admission','현장 방문 · 무료 공연','publisher-body-admission'))
    return claims,end

def make_drone(root,at=None):
    at=at or datetime.now(timezone.utc)
    sources=load_sources(root,at,URLS);claims,end=extract(sources,at)
    c={'source_id':'seoul-drone-20260912','category':'place',
       'title':'토요일 한강에서\n야구 테마 드론쇼','subtitle':'9월 12일 · 뚝섬한강공원',
       'intro_heading':'밤하늘에서 만나는 야구','intro':'K-야구, 서울 나잇\n2026.09.12 토요일\n뚝섬한강공원 수변무대',
       'facts':[{'label':'메인 드론쇼','value':'20:30–20:45'},{'label':'관람 안내','value':'현장 방문 · 무료 공연'},{'label':'방문 전 확인','value':'기상 상황에 따라 지연·취소 가능'}],
       'cta':'일정 저장하고\n방문 전 다시 확인','conditions':'전체 행사 시간은 공식 안내를 확인하세요.\n날씨에 따라 공연이 변경될 수 있습니다.',
       'caption':'9월 12일 토요일, 뚝섬한강공원 수변무대에서 야구 테마 드론쇼가 안내됐습니다.\n메인 드론쇼: 20:30–20:45\n관람: 현장 방문 · 무료 공연\n기상 상황에 따라 지연·취소될 수 있습니다. 전체 행사 시간은 공식 안내 간 차이가 있어 표기하지 않았습니다. 출발 전 최신 공지를 확인하세요.',
       'image_subject':'Photorealistic editorial concept of luminous drones forming an abstract baseball above a broad Seoul riverside at night, distant city lights reflected on water, no text, no logos, imagined scene not actual event footage'}
    c,r=finish(c,claims,sources,'seoul-drone-crosscheck-v1')
    c['valid_until']=min(moment(c['valid_until']),end).isoformat()
    c['caption']=c['caption'].replace('직접 사용·시식 후기','직접 방문 후기').replace('실제 제품·발색·단면','실제 행사 현장')
    r['scope']='서울시 두 원문 본문 날짜·장소·메인 공연 시간 대조'
    r['omitted_fields']=['전체 행사 시간: 원문 간 불일치']
    return c,r
