"""Fail-closed adapters for selected official Shinsegae newsroom articles."""
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path

from .collector import shinsegae_url
from .editorial import EvidenceError, KST, load_sources, moment, normalize
from .products import evidence, finish


def article_body(text):
    if '\n도구 보기\n' not in text:raise EvidenceError('신세계 기사 본문 경계를 확인할 수 없습니다.')
    body=text.split('\n도구 보기\n',1)[1]
    for marker in ('\n보도자료 다운로드','\n관련 태그','\n이전글'):
        body=body.split(marker,1)[0]
    if len(normalize(body))<50:raise EvidenceError('신세계 기사 본문이 비어 있습니다.')
    return body


def popup_content(key,url,title,article,published,at,sources,claims):
    text=normalize(article)
    if url.endswith('/shinsegae-international-popup-service/'):
        required=('텐먼스는오는10월11일까지서울성수동에서첫팝업스토어',
                  '당신만의텐먼스-1:1스타일링클래스','1:1예약제로운영')
        if not all(x in text for x in required):raise EvidenceError('텐먼스 기간·장소·프로그램·예약 조건 확인 실패')
        end=datetime(published.year,10,12,tzinfo=KST)
        if at>=end:raise EvidenceError('텐먼스 팝업이 종료됐습니다.')
        name='텐먼스 성수 팝업';period=f'{published.year}.09 — 10.11'
        facts=[{'label':'운영 기간','value':'2026.10.11까지'},{'label':'진행 지역','value':'서울 성수동'},{'label':'대표 프로그램','value':'1:1 스타일링 클래스 · 사전예약'}]
        conditions='정확한 주소·운영시간·예약 가능 여부는\n텐먼스 공식 인스타그램에서 확인하세요.'
        caption='텐먼스가 서울 성수동에서 첫 팝업스토어를 운영합니다.\n기간: 2026.10.11까지\n대표 프로그램: 당신만의 텐먼스 – 1:1 스타일링 클래스(사전예약)\n정확한 주소·운영시간·예약 가능 여부와 구매 혜택 조건은 공식 안내에서 확인하세요.'
        scene='Photorealistic fictional Seongsu fashion pop-up showroom with long neutral-toned garments, fitting mirrors and tailoring table, warm autumn daylight, no people, logos or writing'
        locator='publisher-body-tenmonths-popup'
    elif url.endswith('/diptyque-les-rituels-de-soin-seongsu-popup/'):
        required=('일자:9월12일','16일','운영시간:오전11시-오후8시','16일은오후7시','서울특별시성동구성수이로18길8','레리츄엘드수앙')
        if not all(x in text for x in required):raise EvidenceError('딥티크 기간·시간·주소·컬렉션 확인 실패')
        end=datetime(published.year,9,16,19,0,tzinfo=KST)
        if at>=end:raise EvidenceError('딥티크 팝업이 종료됐습니다.')
        name='딥티크 성수 팝업';period='2026.09.12 — 09.16'
        facts=[{'label':'운영시간','value':'11:00–20:00 · 9/16은 19:00 종료'},{'label':'주소','value':'서울 성동구 성수이로18길 8'},{'label':'소개 컬렉션','value':'레 리츄엘 드 수앙'}]
        conditions='방문 전 운영 변경과 현장 입장 조건을\n딥티크 공식 안내에서 확인하세요.'
        caption='딥티크 레 리츄엘 드 수앙 성수 팝업 소식입니다.\n기간: 2026.09.12–09.16\n시간: 11:00–20:00(9/16은 19:00 종료)\n주소: 서울 성동구 성수이로18길 8\n방문 전 운영 변경과 현장 입장 조건을 공식 안내에서 확인하세요.'
        scene='Photorealistic fictional luxury fragrance and body-care pop-up in Seongsu, cream stone basins, amber glass silhouettes and soft water reflections, no labels, logos, people or writing'
        locator='publisher-body-diptyque-popup'
    else:raise EvidenceError('지원하지 않는 신세계 장소 기사입니다.')
    claims.extend([evidence(sources,key,'event',name,locator),evidence(sources,key,'period',period,locator),evidence(sources,key,'official_details',facts,locator)])
    return {'source_id':key,'category':'place','title':name+'\n방문 전 핵심 정보','subtitle':period+'\n신세계 공식 발표 기준','intro_heading':'일정과 장소부터 확인','intro':facts[0]['value']+'\n'+facts[1]['value']+'\n'+facts[2]['value'],'facts':facts,
        'cta':'일정 저장하고\n방문 전 공식 확인','conditions':conditions,'caption':caption,
        'image_subject':scene+'. Editorial interpretation, not an actual venue photograph','_ends':end}


def food_content(key,title,article,published,sources,claims):
    text=normalize(article)
    names=re.findall(r'[‘“]([^’”]{2,45})[’”]',title)
    if '스타벅스' not in title or '출시' not in title or len(names)!=1:
        raise EvidenceError('지원하는 스타벅스 신메뉴 제목이 아닙니다.')
    name=names[0]
    m=re.search(r'오는(\d{1,2})일부터전국스타벅스매장',text)
    if not m or name not in article:raise EvidenceError('스타벅스 제품·출시일·판매 채널 확인 실패')
    launch=datetime(published.year,published.month,int(m[1]),tzinfo=KST)
    if not -7<=(launch-published).days<=31:raise EvidenceError('스타벅스 출시일 범위 확인 필요')
    claims.extend([evidence(sources,key,'product',name,'headline-product'),evidence(sources,key,'announced_launch',launch.date().isoformat(),'publisher-body-launch'),evidence(sources,key,'channel','전국 스타벅스 매장','same-launch-sentence')])
    return {'source_id':key,'category':'food','title':'스타벅스 가을 신메뉴\n'+name,'subtitle':f'{launch:%m/%d} 출시 발표\n공식 자료 기준','intro_heading':'제철 재료를 담은 메뉴','intro':name+f'\n{launch:%Y.%m.%d} 출시 발표\n전국 스타벅스 매장',
        'facts':[{'label':'출시 예정일','value':f'{launch:%Y.%m.%d}'},{'label':'판매 채널','value':'전국 스타벅스 매장'},{'label':'구매 전 확인','value':'매장별 판매·재고·가격 확인'}],
        'cta':'신메뉴 일정 저장\n판매 여부는 매장 확인','conditions':'공식 출시 발표를 정리한 정보입니다.\n맛·품질에 대한 시식 후기가 아닙니다.',
        'caption':f'스타벅스 {name} 출시 소식입니다. 공식 자료에서 {launch:%Y.%m.%d}부터 전국 스타벅스 매장 출시 예정임을 확인했습니다. 가격·판매 여부·재고는 매장에서 확인하세요.',
        'image_subject':'Photorealistic fictional autumn cafe drink with golden sweet-potato colored foam beside roasted chestnuts and a plain castella cake, warm window light, no cup logo, packaging or writing'}


def beauty_content(key,url,title,article,published,sources,claims):
    text=normalize(article)
    if url!='https://www.shinsegaegroupnewsroom.com/collection-perfume-launch/' or title!='로에베 퍼퓸, ‘크래프티드 컬렉션’ 신규 향수 5종 출시':
        raise EvidenceError('지원하지 않는 신세계 뷰티 기사입니다.')
    if '크래프티드컬렉션(CraftedCollection)’에신규향수5종을추가하며라인업을확대한다.' not in text:
        raise EvidenceError('향수 컬렉션과 신규 제품 수 확인 실패')
    products=re.findall(r'<([^<>]{2,45} EDP)>',article)
    expected=['필드 다이어리 EDP','스위트 우드랜드 EDP','로즈토피아 EDP','스모키 레인 EDP','버던트 그로브 EDP']
    if products!=expected:raise EvidenceError('신규 향수 5종 이름 확인 실패')
    price=re.search(r'가격은오드퍼퓸(\d+)ml에(\d+)만(\d+)천원대다\.',text)
    if not price:raise EvidenceError('향수 용량·발표 가격 확인 실패')
    volume=int(price[1]);announced=int(price[2])*10000+int(price[3])*1000
    if volume!=100 or announced!=533000:raise EvidenceError('향수 용량·발표 가격이 예상 범위와 다릅니다.')
    claims.extend([
      evidence(sources,key,'collection','크래프티드 컬렉션','publisher-body-collection'),
      evidence(sources,key,'products',products,'publisher-body-five-products'),
      evidence(sources,key,'capacity_ml',volume,'publisher-body-price-sentence'),
      evidence(sources,key,'announced_price_krw',announced,'publisher-body-price-sentence'),
    ])
    names=' · '.join(name.replace(' EDP','') for name in products)
    return {'source_id':key,'category':'beauty','title':'로에베 퍼퓸\n새 향수 5종','subtitle':'크래프티드 컬렉션\n신세계 공식 발표 기준',
      'intro_heading':'자연에서 영감 받은 다섯 향','intro':names+'\n각 제품은 오 드 퍼퓸 100ml',
      'facts':[{'label':'제품 수','value':'신규 향수 5종'},{'label':'용량','value':'각 100ml 오 드 퍼퓸'},{'label':'발표 가격','value':'각 53만3천원대'}],
      'cta':'다섯 가지 향을\n공식 안내에서 비교','conditions':'공식 출시 자료를 정리한 정보입니다.\n향의 느낌은 개인마다 다를 수 있습니다.',
      'caption':'로에베 퍼퓸 크래프티드 컬렉션 신규 향수 5종 출시 소식입니다.\n제품: '+', '.join(products)+f'\n용량·발표 가격: 각 {volume}ml · {announced:,}원대\n공식 출시 자료를 정리했으며 직접 사용 후기가 아닙니다. 판매처별 재고와 실제 결제금액은 구매 전 확인하세요.',
      'image_subject':'Photorealistic botanical ingredient still life on dark stone, five separate natural arrangements of mandarin peel, rose petals, rain-dark cedar wood, pistachios and glossy green leaves, delicate morning mist and refined soft gallery light, close-up nature magazine composition, no manufactured objects, containers, bottles, packaging, text, letters, labels or logos'}


def hangawi_content(key,url,title,article,published,at,sources,claims):
    text=normalize(article)
    if url!='https://www.shinsegaegroupnewsroom.com/a-hangawi-cultural-vacation-to-starfield/' or '스타필드로 떠나는 ‘한가위 문화 바캉스’' not in title:
        raise EvidenceError('지원하지 않는 신세계 장소 기사입니다.')
    required=(
      '스타필드하남은9월19일부터10월1일까지‘벌룬테마여행’을콘셉트로',
      '‘바우덕이풍물놀이’가스타필드수원(9/24)과안성(9/25)에서차례로진행',
      '스타필드고양(9/25)은한국민속촌출신배우들',
      '별마당도서관은코엑스몰(9/25)과수원(9/26)에서추석특집콘서트',
    )
    if not all(value in text for value in required):raise EvidenceError('스타필드 점포별 한가위 일정 확인 실패')
    end=datetime(published.year,10,2,tzinfo=KST)
    if at>=end:raise EvidenceError('스타필드 한가위 행사가 종료됐습니다.')
    schedule=[
      {'place':'스타필드 하남','date':'09.19–10.01','program':'벌룬 테마 여행'},
      {'place':'스타필드 수원·안성','date':'09.24·09.25','program':'바우덕이 풍물놀이'},
      {'place':'스타필드 고양','date':'09.25','program':'조선 퍼레이드·마당극'},
      {'place':'코엑스몰·수원','date':'09.25·09.26','program':'한가위 국악 콘서트'},
    ]
    claims.extend([
      evidence(sources,key,'event','스타필드 한가위 문화 바캉스','publisher-body-event'),
      evidence(sources,key,'schedule',schedule,'publisher-body-store-schedule'),
    ])
    return {'source_id':key,'category':'place','title':'스타필드 한가위\n문화 일정 모음','subtitle':'09/24–10/01 남은 일정\n신세계 공식 발표 기준',
      'intro_heading':'점포마다 다른 한가위 문화 행사','intro':'하남 · 수원 · 안성 · 고양 · 코엑스몰\n벌룬 전시 · 전통 공연 · 국악 콘서트',
      'facts':[{'label':'하남','value':'10/01까지 벌룬 테마 여행'},{'label':'전통 공연','value':'수원 9/24 · 안성·고양 9/25'},{'label':'국악 콘서트','value':'코엑스몰 9/25 · 수원 9/26'}],
      'cta':'가까운 점포 일정 저장\n방문 전 시간 확인','conditions':'기사에 없는 세부 시간·참여 조건은\n각 점포 공식 안내에서 확인하세요.',
      'caption':'스타필드 한가위 문화 바캉스의 남은 일정을 정리했습니다.\n하남: 10/1까지 벌룬 테마 여행\n수원: 9/24 바우덕이 풍물놀이 · 9/26 한가위 국악 콘서트\n안성: 9/25 바우덕이 풍물놀이\n고양: 9/25 조선 퍼레이드·마당극\n코엑스몰: 9/25 한가위 국악 콘서트\n세부 시간·위치·참여 조건은 방문 전 각 점포 공식 안내에서 확인하세요.',
      'image_subject':'Photorealistic fictional Korean shopping atrium during Chuseok, elegant moon jar inspired balloon art, subtle traditional folk performance stage and warm festive lighting, spacious family culture event atmosphere, no logos, writing or identifiable faces','_ends':end}


def make_release(root,key,at=None):
    at=at or datetime.now(timezone.utc)
    try:
        report=json.loads((Path(root)/'data/runtime/collection/report.json').read_text(encoding='utf-8'))
        entry=next(s for s in report['sources'] if s['id']==key and s.get('adapter')=='shinsegae-release')
        url=shinsegae_url(entry['url'])
        expected='ssg-news-'+hashlib.sha256(url.encode()).hexdigest()[:16]
        if key!=expected:raise EvidenceError('신세계 기사 식별자 불일치')
        sources=load_sources(root,at,{key:url});source=sources[key]
        title=entry['headline'];published=moment(entry['published'])
        if not timedelta(0)<=at-published<timedelta(days=7):raise EvidenceError('신세계 새 소식 7일 기한 경과')
        body=source['text']
        if title not in body:raise EvidenceError('목록과 신세계 기사 제목 불일치')
        article=article_body(body);claims=[evidence(sources,key,'publication',published.date().isoformat(),'rss-publication')]
        category=entry.get('category')
        if category=='place':
            content=hangawi_content(key,url,title,article,published,at,sources,claims) if url.endswith('/a-hangawi-cultural-vacation-to-starfield/') else popup_content(key,url,title,article,published,at,sources,claims)
        elif category=='beauty':content=beauty_content(key,url,title,article,published,sources,claims)
        elif category=='food':content=food_content(key,title,article,published,sources,claims)
        else:raise EvidenceError('지원하지 않는 신세계 기사 분야입니다.')
        end=content.pop('_ends',published+timedelta(days=7))
        content,receipt=finish(content,claims,sources,'shinsegae-selected-release-v1')
        content['valid_until']=min(moment(content['valid_until']),published+timedelta(days=7),end).isoformat()
        if category=='place':content['caption']=content['caption'].replace('직접 사용·시식 후기','직접 방문 후기').replace('실제 제품·발색·단면','실제 행사 현장')
        receipt['scope']='신세계 뉴스룸 본문에서 선택 기사 일정·장소·제품 문장 대조'
        return content,receipt
    except EvidenceError:raise
    except (OSError,ValueError,KeyError,TypeError,IndexError,StopIteration) as e:
        raise EvidenceError('신세계 새 소식 원문을 검증할 수 없습니다.') from e


def adapters(root):
    try:report=json.loads((Path(root)/'data/runtime/collection/report.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):return []
    return [(s['id'],partial(make_release,key=s['id'])) for s in report.get('sources',[]) if s.get('adapter')=='shinsegae-release' and re.fullmatch(r'ssg-news-[a-f0-9]{16}',s.get('id',''))]
