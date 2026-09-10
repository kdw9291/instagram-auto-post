"""Bounded product adapters: facts and announced schedules, never reviews."""
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from .editorial import EvidenceError, KST, load_sources, moment, normalize, unique
from .render import visual_revision

HERA_URLS={
 'hera-release':'https://stories.amorepacific.com/'+quote('아모레퍼시픽-헤라-선명한-컬러와-크리스탈-광채-담')+'/',
 'hera-product':'https://hera.com/product/'+quote('센슈얼-샤인-틴트')+'/232/category/60/display/1/',
 'hera-store':'https://www.amoremall.com/kr/ko/product/detail?onlineProdSn=70922&onlineProdCode=111070002495',
}
BAKERY_URLS={'bgf-bakery':'https://origin.bgf.co.kr/bgflive/view/?id=2024&categoryId=1'}

def publication(text, at):
    m=unique(r'^((?:20)\d{2})\.(\d{2})\.(\d{2})$',text,'발표일')
    date=datetime(*map(int,m.groups()),tzinfo=KST)
    if not timedelta(0)<=at-date<timedelta(days=30):raise EvidenceError('신제품 발표가 최근 30일 범위가 아닙니다.')
    return date

def evidence(sources, key, field, value, locator):
    s=sources[key]
    return {'field':field,'value':value,'source_id':key,'url':s['url'],'snapshot_hash':s['hash'],'locator':locator}

def finish(content,claims,sources,policy):
    checked=min(moment(s['checked_at']) for s in sources.values())
    content.update(sample=False,verified_at=checked.isoformat(),valid_until=(checked+timedelta(hours=12)).isoformat(),
                   sources=[s['url'] for s in sources.values()],source_label=f'공식 자료 기준\n확인 {checked.astimezone(KST):%Y.%m.%d}',editorial_policy=policy,visual_revision=visual_revision())
    content['caption']+='\n\n공식 자료를 정리한 정보이며 직접 사용·시식 후기가 아닙니다. 배경은 AI 콘셉트이며 실제 제품·발색·단면이 아닙니다.\n출처:\n'+'\n'.join(content['sources'])+f'\n확인: {checked.astimezone(KST):%Y.%m.%d}'
    return content,{'policy':policy,'status':'verified','scope':'지정 제품 공식 자료 규칙 검증','claims':claims}

def make_hera(root,at=None):
    at=at or datetime.now(timezone.utc)
    try:
        sources=load_sources(root,at,HERA_URLS)
        release=sources['hera-release']['text'];product=sources['hera-product']['text'];shop=sources['hera-store']['text']
        published=publication(release,at)
        for body in (release,product,shop):
            if '센슈얼 샤인 틴트' not in body:raise EvidenceError('헤라 제품 식별이 다릅니다.')
        if HERA_URLS['hera-store'] not in product:raise EvidenceError('헤라의 공식 구매 연결을 확인할 수 없습니다.')
        # Same named product and capacity, not a related lipstick recommendation.
        caps=re.findall(r'센슈얼 샤인 틴트\s+SENSUAL SHINE TINT\s+(\d+)g',product)
        if not caps or len(set(caps))!=1:raise EvidenceError('제품 용량이 모호합니다.')
        grams=int(caps[0])
        if f'NEW 센슈얼 샤인 틴트 {grams}g' not in shop:raise EvidenceError('공식몰 제품 용량이 다릅니다.')
        option_block=product.split('센슈얼 샤인 틴트 컬러\n',1)[1].split('[필수]',1)[0]
        options=re.findall(r'^(\d+)호\s*/\s*([^\n]+)$',option_block,re.MULTILINE)
        if not options or len({o[0] for o in options})!=len(options):raise EvidenceError('색상 옵션이 모호합니다.')
        count=int(unique(r'총\s*(\d+)가지 컬러',release,'출시 색상 수')[1])
        if count!=len(options):raise EvidenceError('출시 자료와 제품 색상 수가 다릅니다.')
        launch=unique(r'(\d+)월\s*(\d+)일 카카오톡 선물하기 선런칭',release,'선런칭 일정')
        launch_date=datetime(published.year,int(launch[1]),int(launch[2]),tzinfo=KST)
        if abs((launch_date-published).days)>30:raise EvidenceError('선런칭 연도·발표일 관계가 모호합니다.')
        fields=sources['hera-store']['fields'];origin=fields.get('price_origin',[])
        if len(origin)!=1:raise EvidenceError('할인 전 가격 영역이 모호합니다.')
        price=int(unique(r'([\d,]+)\s*원',origin[0],'할인 전 표시가')[1].replace(',',''))
        if price<=0:raise EvidenceError('정상 표시가가 아닙니다.')
        selected=shop.split('selected option\n',1)[1].split('네이버페이',1)[0]
        for code,name in options:
            if normalize(code+' '+name) not in normalize(selected):raise EvidenceError('공식몰과 색상 옵션이 다릅니다.')
        claims=[evidence(sources,'hera-release','product','센슈얼 샤인 틴트','release-name'),evidence(sources,'hera-product','capacity',grams,'name-capacity'),evidence(sources,'hera-release','launch',launch_date.date().isoformat(),'prelaunch-sentence'),evidence(sources,'hera-product','options',[f'{n}호 {v}' for n,v in options],'product-options'),evidence(sources,'hera-release','option_count',count,'color-count'),evidence(sources,'hera-store','list_price',price,'price_origin'),evidence(sources,'hera-product','store_link',HERA_URLS['hera-store'],'purchase-link')]
        date=launch_date.strftime('%Y.%m.%d')
        c={'source_id':'hera-auto-70922','category':'beauty','title':f'헤라의 새 틴트\n{count}가지 컬러', 'subtitle':'센슈얼 샤인 틴트\n공식 제품 정보',
           'intro_heading':'컬러부터 확인해요','intro':f'{grams}g · {count}가지 색상\n{date} 선런칭 발표\n실제 발색은 공식 안내에서 확인',
           'facts':[{'label':'제품 구성','value':f'{grams}g · {count}색'},{'label':'아모레몰 할인 전 표시가','value':f'{price:,}원'},{'label':'구매 전 확인','value':'옵션·혜택별 결제금액 확인'}],
           'cta':'내 컬러는\n공식 안내에서','conditions':'실제 발색·재고는 판매처에서 확인\n할인 전 표시가와 결제금액은 다릅니다.',
           'caption':f'헤라 센슈얼 샤인 틴트 공식 정보.\n{date} 선런칭 발표 기준, {grams}g·{count}가지 색상입니다.\n아모레몰 할인 전 표시가: {price:,}원. 옵션·혜택별 최종 결제금액과 재고는 판매처에서 확인하세요.\n색상: '+', '.join(f'{n}호 {v}' for n,v in options)}
        c['image_subject']='Extreme macro studio photograph of flowing thick translucent ruby red gel and muted rose gel smeared across frosted glass, beautiful glossy liquid pigment texture with delicate highlights and tiny bubbles, abstract organic curved waves, shallow depth of field, soft pink background, frame filled entirely by gel and glass'
        return finish(c,claims,sources,'hera-evidence-v1')
    except EvidenceError:raise
    except (KeyError,IndexError,TypeError,ValueError,OSError) as e:raise EvidenceError('헤라 원문 또는 배경 자산을 확인할 수 없습니다.') from e

def make_bakery(root,at=None):
    at=at or datetime.now(timezone.utc)
    try:
        sources=load_sources(root,at,BAKERY_URLS);body=sources['bgf-bakery']['text'];published=publication(body,at)
        text=normalize(body)
        if 'BAKE405리브랜딩!CU,편의점베이커리2.0시대연다' not in text:raise EvidenceError('BGF 발표 대상이 다릅니다.')
        price=int(unique(r'‘마블크림시리즈’\(각([\d,]+)원\)',text,'시리즈 발표 가격')[1].replace(',',''))
        schedule=unique(r'BAKE405마블크림시리즈는(\d+)월부터순차출시된다\.(.+?)출시한다\.',text,'출시 일정 문단')
        month=int(schedule[1]);paragraph=schedule[2]
        pattern=r'(\d+)일(?:(?!\d+일).)*?‘(마블[^’]+크림빵)’'
        matches=list(re.finditer(pattern,paragraph))
        if len(matches)!=4 or len({m[2] for m in matches})!=4:raise EvidenceError('제품별 출시 일정이 모호합니다.')
        products=[]
        for m in matches:
            date=datetime(published.year,month,int(m[1]),tzinfo=KST)
            if abs((date-published).days)>30:raise EvidenceError('출시 연도·발표일 관계가 모호합니다.')
            products.append({'name':m[2],'announced_date':date.date().isoformat()})
        claims=[evidence(sources,'bgf-bakery','list_price',price,'series-price'),evidence(sources,'bgf-bakery','publication',published.date().isoformat(),'publication-date')]
        claims += [evidence(sources,'bgf-bakery','announced_launch',p,'schedule-paragraph') for p in products]
        lines=[f"{p['announced_date'][5:].replace('-','/')} · {p['name']}" for p in products]
        c={'source_id':'bgf-auto-2024','category':'food','title':f'CU 새 빵 라인업\n{month}월 일정 한눈에','subtitle':'BAKE405 마블크림 시리즈\nBGF 공식 발표 일정',
           'intro_heading':'네 가지 출시 일정','intro':'\n'.join(lines),
           'facts':[{'label':'시리즈 발표 가격','value':f'각 {price:,}원'},{'label':'판매 채널','value':'CU · 매장별 취급·재고 확인'},{'label':'일정 기준','value':f'{published:%Y.%m.%d} BGF 발표'}],
           'cta':'출시 일정 저장\n재고는 따로 확인','conditions':'발표 일정이며 입고 보장이 아닙니다.\n제품 외관·맛을 재현한 배경이 아닙니다.',
           'caption':f'CU BAKE405 마블크림 시리즈. BGF가 {published:%Y.%m.%d} 발표한 출시 일정과 가격입니다.\n'+'\n'.join(lines)+f'\n발표 가격은 각 {price:,}원입니다. 발표 일정이며 실제 출시·입고를 보장하지 않습니다. 매장별 취급과 재고를 확인하세요.'}
        c['image_subject']='A bakery editorial still life about a new braided cream bread series, fictional twisted pastries on parchment with chocolate, lemon, strawberries and cinnamon ingredients, warm morning side light, no branded packaging'
        return finish(c,claims,sources,'bgf-evidence-v1')
    except EvidenceError:raise
    except (KeyError,IndexError,TypeError,ValueError,OSError) as e:raise EvidenceError('BGF 원문 또는 배경 자산을 확인할 수 없습니다.') from e
