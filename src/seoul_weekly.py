"""Cross-checked current-week Seoul event bundle from official pages."""
from datetime import datetime, timedelta, timezone

from .editorial import EvidenceError, KST, load_sources, moment, normalize
from .products import evidence, finish

URLS={
 'seoul-calendar-202609':'https://news.seoul.go.kr/culture/archives/534130',
 'seoul-safety-202609':'https://news.seoul.go.kr/safe/archives/518514?listPage=1',
 'seoul-market-202609':'https://news.seoul.go.kr/gov/archives/580737',
 'seoul-phil-202609':'https://www.seoulphil.or.kr/perf/view?flag=list&langCd=ko&menuFlag=MFLG0001&perfNo=7597',
}


def publisher_body(text,marker):
    positions=[];start=0
    while True:
        found=text.find(marker,start)
        if found<0:break
        positions.append(found);start=found+len(marker)
    if not positions:raise EvidenceError('서울시 기사 본문 경계를 확인할 수 없습니다.')
    body=text[positions[-1]:].split('AI생성태그',1)[0]
    if len(normalize(body))<50:raise EvidenceError('서울시 기사 본문이 비어 있습니다.')
    return body


def make_weekly(root,at=None):
    at=at or datetime.now(timezone.utc)
    try:
        sources=load_sources(root,at,URLS)
        calendar=normalize(sources['seoul-calendar-202609']['text'])
        safety=normalize(publisher_body(sources['seoul-safety-202609']['text'],'2026년 서울안전한마당'))
        market_raw=sources['seoul-market-202609']['text']
        if '\n수정일\n2026-09-11\n' not in market_raw:raise EvidenceError('서로장터 본문 경계를 확인할 수 없습니다.')
        market=normalize(market_raw.split('\n수정일\n2026-09-11\n',1)[1].split('\n2026 추석맞이 서로장터\n2026 추석맞이 서로장터\n',1)[0])
        phil=normalize(sources['seoul-phil-202609']['text'])
        safety_required=('2026.9.17.','9.19.','10:00','17:00','여의도공원문화의마당','70개')
        market_required=('9.15.','9.17.','10:00','19:00','서울광장')
        phil_required=('2026.9.19.','19:00','서울어린이대공원숲속의무대','무료','별도신청없이')
        if not all(x in safety for x in safety_required):raise EvidenceError('서울안전한마당 일정·장소·프로그램 확인 실패')
        if not all(x in market for x in market_required):raise EvidenceError('서로장터 일정·시간·장소 확인 실패')
        if not all(x in phil for x in phil_required):raise EvidenceError('파크 콘서트 일정·장소·무료 관람 확인 실패')
        safety_calendar=('서울안전한마당' in calendar and '여의도공원' in calendar and
                         any(x in calendar for x in ('2026-09-17','9.17')) and any(x in calendar for x in ('2026-09-19','9.19')))
        if not safety_calendar:
            raise EvidenceError('문화달력의 서울안전한마당 교차 확인 실패')
        park_calendar=(all(x in calendar for x in ('파크콘서트','서울어린이대공원','무료')) and
                       any(x in calendar for x in ('2026-09-19','9.19')))
        if not park_calendar:
            raise EvidenceError('문화달력의 파크 콘서트 교차 확인 실패')
        end=datetime(2026,9,17,19,0,tzinfo=KST)
        if not datetime(2026,9,12,tzinfo=KST)<=at<end:
            raise EvidenceError('이번 주 서울 행사 묶음의 제작 기한이 아닙니다.')
        events=[
          {'label':'9/15–17 · 서로장터','value':'10:00–19:00 · 서울광장'},
          {'label':'9/17–19 · 서울안전한마당','value':'10:00–17:00 · 여의도공원'},
          {'label':'9/19 · 서울시향 파크 콘서트','value':'19:00 · 어린이대공원 · 무료'},
        ]
        claims=[]
        for field,value in [('safety',events[1]),('park_concert',events[2])]:
            claims.append(evidence(sources,'seoul-calendar-202609',field,value,'monthly-calendar'))
        claims.extend([
          evidence(sources,'seoul-safety-202609','safety',events[1],'publisher-body-after-ai-summary'),
          evidence(sources,'seoul-market-202609','market',events[0],'publisher-body-structured-schedule'),
          evidence(sources,'seoul-phil-202609','park_concert',events[2],'official-performance-detail'),
        ])
        c={'source_id':'seoul-weekly-20260914','category':'place','title':'이번 주 서울에서\n가볼 만한 행사 3','subtitle':'장터 · 체험 · 무료 공연\n공식 일정만 모았어요','intro_heading':'날짜별로 골라 보세요','intro':'9/15–17 서울광장 서로장터\n9/17–19 여의도 서울안전한마당\n9/19 서울시향 무료 공연',
           'facts':events,'cta':'주말 일정 저장\n출발 전 최신 공지 확인','conditions':'서로장터 원문의 요일 표기가 달라 날짜만 사용했습니다.\n우천·현장 사정에 따른 변경을 확인하세요.',
           'caption':'이번 주 서울 공식 행사 3곳을 모았습니다.\n① 9/15–17 10:00–19:00 추석맞이 서로장터 · 서울광장\n② 9/17–19 10:00–17:00 서울안전한마당 · 여의도공원 문화의 마당\n③ 9/19 19:00 서울시향 파크 콘서트 · 서울어린이대공원 숲속의무대 · 무료, 별도 신청 없음\n서로장터 원문은 요일 표기가 서로 달라 날짜만 사용했습니다. 우천·현장 사정에 따른 변경은 출발 전 공식 공지에서 확인하세요.',
           'image_subject':'Photorealistic editorial collage-like Seoul autumn weekend scene in one coherent frame: civic plaza market canopies, hands-on safety activity tents and an outdoor classical concert stage among green trees, distant people without identifiable faces, no signs, logos or writing'}
        c,r=finish(c,claims,sources,'seoul-weekly-crosscheck-v1')
        c['valid_until']=min(moment(c['valid_until']),end).isoformat()
        c['caption']=c['caption'].replace('직접 사용·시식 후기','직접 방문 후기').replace('실제 제품·발색·단면','실제 행사 현장')
        r['scope']='서울시 개별 행사 원문과 9월 문화달력 일정 교차 대조'
        r['omitted_fields']=['서로장터 요일: 같은 원문 안에서 날짜와 불일치']
        return c,r
    except EvidenceError:raise
    except (OSError,ValueError,KeyError,TypeError,IndexError) as e:
        raise EvidenceError('이번 주 서울 행사 원문을 검증할 수 없습니다.') from e
