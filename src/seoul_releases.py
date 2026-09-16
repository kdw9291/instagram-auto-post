"""Fail-closed adapters for dynamically discovered Seoul culture releases."""
import json
import re
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path

from .collector import seoul_url
from .editorial import EvidenceError, KST, load_sources, moment, normalize
from .products import evidence, finish


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
