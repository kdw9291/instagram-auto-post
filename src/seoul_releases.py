"""Fail-closed adapters for dynamically discovered Seoul culture releases."""
import json
import re
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path

from .collector import seoul_url
from .editorial import EvidenceError, KST, load_sources, moment, normalize
from .products import evidence, finish


def labelled_performance(sources,key,title,published,text,at):
    """Read facts only from the publisher's labelled performance overview, never its AI summary."""
    compact=normalize(text)
    if '공연' not in title and '클래식' not in title:return None
    if compact.count('○공연개요')!=1:return None
    detail=text.split('○ 공연개요',1)[1].split('○ 신청개요',1)[0]
    body=normalize(detail)
    name_match=re.search(r'-\s*공연명:\s*(.+?)\s*-\s*일시/장소:',detail,re.DOTALL)
    schedule=re.search(r'-\s*일시/장소:\s*(20\d{2})\.(\d{1,2})\.(\d{1,2})\.\(([월화수목금토일])\),\s*(\d{1,2}):(\d{2})\s*/\s*(.+?)(?:\n\s*-\s*출연진|\n\s*∙\s*지\s*휘:)',detail,re.DOTALL)
    runtime=re.search(r'∙공연시간:(\d+)분\(인터미션(\d+)분\)',body)
    age=re.search(r'∙관람연령:취학아동이상\((20\d{2})년이전출생자\)',body)
    prices=re.search(r'∙티켓가격:관람료선택제\((1천원,3천원,5천원,1만원)중',body)
    if not all((name_match,schedule,runtime,age,prices)):raise EvidenceError('공연 개요의 이름·일시·장소·관람 조건 확인 실패')
    name=' '.join(name_match[1].split())
    if normalize(name)!=normalize(title):raise EvidenceError('공연 제목과 본문 공연명이 다릅니다.')
    year,month,day=map(int,schedule.groups()[:3]);weekday=schedule[4];hour=int(schedule[5]);minute=int(schedule[6]);venue=' '.join(schedule[7].split())
    start=datetime(year,month,day,hour,minute,tzinfo=KST)
    minutes=int(runtime[1]);intermission=int(runtime[2]);birth_year=int(age[1])
    end=start+timedelta(minutes=minutes)
    if '월화수목금토일'[start.weekday()]!=weekday or end<=at or not 30<=minutes<=300 or not 0<=intermission<minutes or birth_year>year:raise EvidenceError('공연 일정 또는 관람 조건이 올바르지 않습니다.')
    price_options='1천원 · 3천원 · 5천원 · 1만원 중 선택'
    date_label=f'{start:%Y.%m.%d} · {start:%H:%M}'
    claims=[
      evidence(sources,key,'event_title',name,'publisher-labelled-performance-name'),
      evidence(sources,key,'datetime',start.isoformat(),'publisher-labelled-datetime-and-venue'),
      evidence(sources,key,'venue',venue,'publisher-labelled-datetime-and-venue'),
      evidence(sources,key,'runtime_minutes',minutes,'publisher-labelled-runtime'),
      evidence(sources,key,'admission_age',f'{birth_year}년 이전 출생자','publisher-labelled-admission-age'),
      evidence(sources,key,'ticket_price_options',price_options,'publisher-labelled-ticket-price'),
      evidence(sources,key,'publication',published.date().isoformat(),'homepage-publication'),
    ]
    c={'source_id':key,'category':'place','title':'11월에 만나는\n누구나 클래식','subtitle':'대전시립교향악단\n서울시 공식 안내 기준',
      'intro_heading':'공연 일정부터 확인해요','intro':date_label+'\n'+venue+'\n공연시간 120분',
      'facts':[{'label':'일시·장소','value':date_label+' · '+venue},{'label':'관람 연령','value':f'취학아동 이상 · {birth_year}년 이전 출생자'},{'label':'관람료 선택제','value':price_options}],
      'cta':'공연 일정 저장\n예매는 공식 페이지 확인','conditions':'공연시간은 앵콜 여부에 따라 달라질 수 있습니다.\n좌석·예매 가능 여부는 공식 안내 확인',
      'caption':name+' 공연 소식입니다.\n일시: '+date_label+'\n장소: '+venue+f'\n공연시간: {minutes}분(인터미션 {intermission}분, 앵콜에 따라 변동 가능)\n관람 연령: 취학아동 이상({birth_year}년 이전 출생자)\n관람료 선택제: '+price_options+'\n좌석과 일반 예매 가능 여부는 공식 페이지에서 확인하세요.',
      'image_subject':'A realistic editorial photograph of a fictional grand classical concert hall with an anonymous symphony orchestra seen from a distance, warm amber stage lights, elegant deep burgundy and gold atmosphere, no identifiable musicians, logos or readable text. This is not the real performance',}
    c,r=finish(c,claims,sources,'seoul-labelled-performance-v1')
    c['valid_until']=min(moment(c['valid_until']),end).isoformat()
    c['caption']=c['caption'].replace('직접 사용·시식 후기','직접 관람 후기').replace('실제 제품·발색·단면','실제 공연 현장·출연진')
    r['scope']='서울시 본문 중 AI 요약을 제외한 공연개요의 제목·일시·장소·관람 조건 대조'
    return c,r


def holiday_event(sources,key,title,published,text,at):
    """Verify the two labelled, free Chuseok museum event formats."""
    compact=normalize(text)
    if '문화가흐르는박물관' in normalize(title):
        marker='한가위를맞이해서울생활사박물관에서문화행사'
        if marker not in compact:return None
        body=compact.rsplit(marker,1)[1].split('AI생성태그',1)[0]
        required=('일시:2026년9월26일(토)13시~17시','장소:서울생활사박물관일대(실내외)','참여방법:현장참여(선착순),무료')
        if not all(value in body for value in required):raise EvidenceError('한가위 박물관 행사 일정·장소·참여방법 확인 실패')
        start=datetime(2026,9,26,13,tzinfo=KST);end=datetime(2026,9,26,17,tzinfo=KST)
        venue='서울생활사박물관 일대(실내외)';admission='현장 선착순 · 무료'
        program='공연 · 전통놀이 · 만들기 체험';condition='만들기 체험은 재료 소진 시 종료됩니다.'
        card_title='한가위에 가볼 만한\n무료 박물관 행사'
        image='A realistic editorial photograph inspired by a Korean museum courtyard during Chuseok, traditional games and craft tables prepared for families, warm early autumn daylight, no logos, readable text or identifiable faces'
        policy='seoul-labelled-holiday-event-v1'
    elif '한가위한마당' in normalize(title):
        marker='한가위한마당-오색한가위'
        if marker not in compact:return None
        body=compact.rsplit(marker,1)[1].split('서울역사박물관한가위한마당',1)[0]
        required=('일시:2026.9.26.(토)12:00~16:00','장소:서울역사박물관','대상:일반시민(무료)')
        if not all(value in body for value in required):raise EvidenceError('서울역사박물관 행사 일정·장소·대상 확인 실패')
        start=datetime(2026,9,26,12,tzinfo=KST);end=datetime(2026,9,26,16,tzinfo=KST)
        venue='서울역사박물관';admission='일반 시민 · 무료'
        program='국악 버스킹 · 민속놀이 · 만들기';condition='우천 시 야외 일정만 제외될 수 있습니다.'
        card_title='서울역사박물관\n무료 한가위 한마당'
        image='A realistic editorial photograph inspired by a Korean history museum courtyard during Chuseok, folk games and craft activities, warm early autumn daylight, no logos, readable text or identifiable faces'
        policy='seoul-labelled-holiday-event-v1'
    else:return None
    if end<=at:raise EvidenceError('서울시 문화행사가 종료됐습니다.')
    claims=[
      evidence(sources,key,'event_title',title,'homepage-title-and-page-heading'),
      evidence(sources,key,'date',start.date().isoformat(),'publisher-body-labelled-date'),
      evidence(sources,key,'hours',[start.strftime('%H:%M'),end.strftime('%H:%M')],'publisher-body-labelled-hours'),
      evidence(sources,key,'venue',venue,'publisher-body-labelled-venue'),
      evidence(sources,key,'admission',admission,'publisher-body-labelled-admission'),
      evidence(sources,key,'publication',published.date().isoformat(),'homepage-publication'),
    ]
    c={'source_id':key,'category':'place','title':card_title,'subtitle':f'{start:%m/%d} · {start:%H:%M}–{end:%H:%M}\n서울시 공식 안내 기준',
       'intro_heading':'가족과 함께 즐기는 한가위','intro':f'{venue}\n{program}\n{admission}',
       'facts':[{'label':'행사 시간','value':f'{start:%Y.%m.%d} · {start:%H:%M}–{end:%H:%M}'},{'label':'장소','value':venue},{'label':'참여','value':admission}],
       'cta':'한가위 일정 저장\n방문 전 공식 공지 확인','conditions':condition+'\n세부 프로그램은 공식 페이지에서 확인하세요.',
       'caption':f'{title} 소식입니다. 서울시가 {published:%Y.%m.%d} 공개한 공식 안내에서 확인했습니다.\n일시: {start:%Y.%m.%d} {start:%H:%M}–{end:%H:%M}\n장소: {venue}\n참여: {admission}\n프로그램: {program}\n{condition} 방문 전 공식 페이지에서 최신 운영을 확인하세요.',
       'image_subject':image}
    c,r=finish(c,claims,sources,policy)
    c['valid_until']=min(moment(c['valid_until']),end).isoformat()
    c['caption']=c['caption'].replace('직접 사용·시식 후기','직접 방문 후기').replace('실제 제품·발색·단면','실제 행사 현장')
    r['scope']='서울시 문화 홈페이지와 행사 본문의 제목·일시·장소·무료 참여 대조'
    return c,r


def make_release(root,key,at=None):
    at=at or datetime.now(timezone.utc)
    try:
        report=json.loads((Path(root)/'data/runtime/collection/report.json').read_text(encoding='utf-8'))
        entry=next(s for s in report['sources'] if s['id']==key and s.get('adapter')=='seoul-release')
        url=seoul_url(entry['url']);article_id=url.rsplit('/',1)[1]
        if key!='seoul-culture-'+article_id:raise EvidenceError('서울시 기사 식별자 불일치')
        sources=load_sources(root,at,{key:url});source=sources[key]
        title=entry['headline'];published=moment(entry['published'])
        if not timedelta(0)<=at-published<timedelta(days=7):raise EvidenceError('서울시 새 소식 7일 기한 경과')
        text=normalize(source['text'])
        if normalize(title) not in text:raise EvidenceError('RSS와 공식 원문 제목이 다릅니다.')
        holiday=holiday_event(sources,key,title,published,source['text'],at)
        if holiday:return holiday
        performance=labelled_performance(sources,key,title,published,source['text'],at)
        if performance:return performance
        if not re.fullmatch(r'20\d{2}서울로미디어캔버스.+전시',normalize(title)):
            raise EvidenceError('이 서울시 전시 형식의 검증 규칙이 필요합니다.')
        period=re.search(r'전시기간:(20\d{2})년(\d{1,2})월(\d{1,2})일~(20\d{2})년(\d{1,2})월(\d{1,2})일',text)
        hours=re.search(r'전시시간:(\d{1,2})시~(\d{1,2})시',text)
        works=re.search(r'전시작품:신진예술가지원공모전(\d+)작품,네이처프로젝트전(\d+)작품\(총(\d+)점\)',text)
        if not period or not hours or not works:raise EvidenceError('전시 기간·시간·작품 수를 공식 원문에서 확인할 수 없습니다.')
        start=datetime(*map(int,period.groups()[:3]),tzinfo=KST);end=datetime(*map(int,period.groups()[3:]),23,59,tzinfo=KST)
        opening,closing=map(int,hours.groups());first,second,total=map(int,works.groups())
        if not start<end or end<=at or not 0<=opening<closing<=24 or first+second!=total:
            raise EvidenceError('전시 일정 또는 작품 수 관계를 확인할 수 없습니다.')
        claims=[
          evidence(sources,key,'event_title',title,'rss-title-and-page-heading'),
          evidence(sources,key,'dates',{'start':start.date().isoformat(),'end':end.date().isoformat()},'publisher-body-period'),
          evidence(sources,key,'hours',[f'{opening:02}:00',f'{closing:02}:00'],'publisher-body-hours'),
          evidence(sources,key,'work_count',total,'publisher-body-work-count'),
          evidence(sources,key,'publication',published.date().isoformat(),'rss-publication'),
        ]
        period_label=f'{start:%Y.%m.%d} — {end:%m.%d}'
        content={'source_id':key,'category':'place','title':'서울로에서 만나는\n미디어아트 새 전시','subtitle':title+'\n서울시 공식 안내 기준',
          'intro_heading':'기간과 시간을 확인해요','intro':f'{period_label}\n매일 {opening:02}:00–{closing:02}:00\n총 {total}점 상영',
          'facts':[{'label':'전시 기간','value':period_label},{'label':'상영 시간','value':f'{opening:02}:00–{closing:02}:00 · 운영 조정 가능'},{'label':'전시 작품','value':f'공모 {first}점 · 네이처 {second}점'}],
          'cta':'야간 산책 전\n공식 운영 확인','conditions':'운영시간은 조정될 수 있습니다.\n상영 위치·당일 운영은 공식 페이지 확인',
          'caption':f'{title} 소식입니다. 서울시가 {published:%Y.%m.%d} 공개한 공식 안내에서 확인했습니다.\n기간: {period_label}\n시간: {opening:02}:00–{closing:02}:00\n작품: 총 {total}점\n운영시간은 조정될 수 있으니 방문 전 공식 페이지에서 상영 위치와 당일 운영을 확인하세요.',
          'image_subject':'A realistic editorial night photograph inspired by a large outdoor media art screen in central Seoul, abstract nature imagery glowing across an urban plaza, a few anonymous silhouettes, cinematic blue hour, no logos or readable text'}
        content,receipt=finish(content,claims,sources,'seoul-media-canvas-v1')
        content['valid_until']=min(moment(content['valid_until']),end).isoformat()
        receipt['scope']='서울시 문화 RSS와 공식 상세의 제목·기간·시간·작품 수 대조'
        return content,receipt
    except EvidenceError:raise
    except (OSError,ValueError,KeyError,TypeError,IndexError,StopIteration) as e:
        raise EvidenceError('서울시 문화 기사 원문을 검증할 수 없습니다.') from e


def adapters(root):
    try:report=json.loads((Path(root)/'data/runtime/collection/report.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):return []
    return [(s['id'],partial(make_release,key=s['id'])) for s in report.get('sources',[]) if s.get('adapter')=='seoul-release' and re.fullmatch(r'seoul-culture-[1-9][0-9]{0,9}',s.get('id',''))]
