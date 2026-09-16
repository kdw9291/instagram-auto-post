"""New BGF URLs, constrained announcement facts; unsupported articles fail closed."""
import json
import re
from pathlib import Path
from functools import partial
from datetime import datetime, timezone, timedelta
from .collector import bgf_url
from .editorial import EvidenceError, load_sources, moment, normalize, KST
from .products import finish, evidence

SCENES=[
    (('빵','베이커리','베이글'), 'Fresh fictional bakery bread on parchment, warm window light, appetizing baked texture'),
    (('쿠키','과자'), 'Fictional cookies and crackers on a ceramic plate, crisp baked texture, warm cafe light'),
    (('아이스크림','젤라또'), 'Fictional ice cream scoops in a plain ceramic bowl, soft creamy texture, cool studio light'),
    (('도시락','김밥'), 'Fictional Korean rice lunch and vegetable side dishes in a plain lunch box, natural daylight'),
    (('라면','우동'), 'Fictional steaming noodle soup in a plain ceramic bowl, appetizing noodles, soft side light'),
    (('커피','라테'), 'Fictional iced coffee in a plain clear glass, realistic condensation, soft cafe window light'),
]


def student_meal_lineup(article,published):
    """Parse the two named products in the 2026 culinary-school release.

    The third award entry is deliberately omitted because the article does not
    name it or give an exact launch date.
    """
    text=normalize(article)
    first=re.search(r"첫상품은이달(\d{1,2})일출시한‘([^‘’()]{2,40})\(([\d,]+)원\)’이다\.",text)
    second=re.search(r"오는(\d{1,2})일에는2위수상작인‘([^‘’]{2,40})’을내놓는다\.",text)
    if not first or not second:return None
    if text.count(first.group(0))!=1 or text.count(second.group(0))!=1:
        raise EvidenceError('학생 레시피 제품 일정이 여러 번 나타납니다.')
    if '수상작1~3위의레시피를CU간편식으로개발해이달부터순차적으로출시한다.' not in text:
        raise EvidenceError('학생 레시피 라인업의 출시 범위를 확인할 수 없습니다.')
    products=[]
    for day,name in ((first[1],first[2]),(second[1],second[2])):
        launch=datetime(published.year,published.month,int(day),tzinfo=KST)
        if not 0<=(launch-published).days+7<=67:raise EvidenceError('제품 출시일 범위 확인 필요')
        products.append({'name':name.strip(),'launch':launch})
    price=int(first[3].replace(',',''))
    if not 0<price<100000:raise EvidenceError('첫 제품 가격 범위 확인 필요')
    return products,price


def rescene_bakery_lineup(article,published):
    """Parse the five named breads and one shared sequential launch date."""
    text=normalize(article)
    expected=['원이의옥수수크림빵','미나미의메론빵','메이의시나몬롤','제나의딸기샌드','리브의초코호떡']
    if '5종을이달' not in text or not any(name in text for name in expected):return None
    launch_match=re.search(r'5종을이달(\d{1,2})일부터순차적으로선보인다\.',text)
    if not launch_match or text.count(launch_match.group(0))!=1:
        raise EvidenceError('리센느 베이커리 출시 시작일을 확인할 수 없습니다.')
    for name in expected:
        if len(re.findall(r'‘(?:BAKE405)?'+re.escape(name)+r'’',text))!=1:
            raise EvidenceError('리센느 베이커리 제품명이 모호합니다.')
    launch=datetime(published.year,published.month,int(launch_match[1]),tzinfo=KST)
    if not 0<=(launch-published).days<=31:raise EvidenceError('리센느 베이커리 출시일 범위 확인 필요')
    return [re.sub(r'(원이|미나미|메이|제나|리브)의',r'\1 ',name) for name in expected],launch


def make_release(root,key,at=None):
    at=at or datetime.now(timezone.utc)
    try:
        report=json.loads((Path(root)/'data/runtime/collection/report.json').read_text(encoding='utf-8'))
        entry=next(s for s in report['sources'] if s['id']==key and s.get('adapter')=='bgf-release')
        url=bgf_url(entry['url'])
        if key!='bgf-news-'+re.search(r'id=(\d+)',url)[1]:raise EvidenceError('기사 식별자 불일치')
        sources=load_sources(root,at,{key:url});source=sources[key]
        title=entry['headline'];published=moment(entry['published'])
        if not timedelta(0)<=at-published<timedelta(days=7):raise EvidenceError('새 소식 7일 기한 경과')
        body=source['text']
        header=title+'\n보도자료\n'+published.astimezone(KST).strftime('%Y.%m.%d')
        if body.count(header)!=1:raise EvidenceError('목록과 기사 제목·발표일 불일치')
        article=body.split(header,1)[1].split('\n이전글',1)[0]
        if any(w in title for w in ('맥주','소주','와인','주류','음주','담배','건강기능','치료','선물세트','생활소품')):
            raise EvidenceError('현재 자동 출시 편집 범위 밖')
        if 'CU' not in title or '출시' not in title:raise EvidenceError('CU 출시 발표 제목이 필요합니다.')
        lineup=student_meal_lineup(article,published)
        if lineup:
            products,price=lineup;name=' · '.join(p['name'] for p in products);launch=None
            scene='Fictional Korean convenience-store lunch boxes with rice and colorful side dishes on a clean table, natural daylight, no branded packaging or writing'
            claims=[evidence(sources,key,'products',[p['name'] for p in products],'two-named-product-sentences'),evidence(sources,key,'announced_launch',[p['launch'].date().isoformat() for p in products],'same-product-date-sentences'),evidence(sources,key,'first_product_price',price,'first-product-parentheses'),evidence(sources,key,'publication',published.date().isoformat(),'article-header'),evidence(sources,key,'announcement','CU 간편식 순차 출시','lineup-launch-sentence')]
            lines=[f"{p['launch']:%m/%d} · {p['name']}" for p in products]
            c={'source_id':key,'category':'food','title':'학생 레시피로 만든\nCU 간편식 2종','subtitle':'한국조리과학고 수상작\nBGF 공식 발표 기준',
               'intro_heading':'확인된 두 가지 일정','intro':'\n'.join(lines),
               'facts':[{'label':'첫 제품 발표 가격','value':f'{price:,}원'},{'label':'판매 채널','value':'전국 CU · 매장별 취급 확인'},{'label':'추가 수상작','value':'제품명·정확한 날짜 미공개'}],
               'cta':'출시 일정 저장\n입고·재고는 매장 확인','conditions':'발표 일정이며 실제 입고를 보장하지 않습니다.\n이름이 공개되지 않은 3위 제품은 제외했습니다.',
               'caption':'한국조리과학고 학생 레시피로 만든 CU 간편식 소식입니다. BGF가 '+f'{published:%Y.%m.%d} 공개한 자료에서 확인했습니다.\n'+'\n'.join(lines)+f'\n첫 제품 발표 가격: {price:,}원. 이름과 정확한 날짜가 공개되지 않은 3위 제품은 제외했습니다. 매장별 취급·입고·재고를 확인하세요.',
               'image_subject':scene+'. Editorial photograph inspired by a student recipe convenience store food announcement'}
            c,receipt=finish(c,claims,sources,'bgf-student-lineup-v1')
            c['valid_until']=min(moment(c['valid_until']),published+timedelta(days=7)).isoformat()
            receipt['scope']='BGF 학생 레시피 기사에서 이름이 공개된 2개 제품·일정·첫 제품 가격 대조'
            receipt['omitted_fields']=['3위 제품: 이름과 정확한 출시일 미공개']
            return c,receipt
        bakery=rescene_bakery_lineup(article,published)
        if bakery:
            products,launch=bakery
            claims=[evidence(sources,key,'products',products,'five-named-product-paragraphs'),evidence(sources,key,'announced_launch',launch.date().isoformat(),'sequential-launch-sentence'),evidence(sources,key,'publication',published.date().isoformat(),'article-header'),evidence(sources,key,'announcement','CU BAKE405 베이커리 5종 순차 출시','lineup-launch-sentence')]
            lines=['원이 · 옥수수 크림빵','미나미 · 메론빵','메이 · 시나몬 롤','제나 · 딸기 샌드','리브 · 초코 호떡']
            c={'source_id':key,'category':'food','title':'CU 신상 빵 5종\n리센느 취향을 담다','subtitle':f'{launch:%m/%d}부터 순차 출시 발표\nBGF 공식 자료 기준',
               'intro_heading':'멤버별 다섯 가지 맛','intro':'\n'.join(lines[:3])+'\n외 2종',
               'facts':[{'label':'출시 시작 발표','value':f'{launch:%Y.%m.%d}부터 순차 출시'},{'label':'제품 구성','value':'옥수수·메론·시나몬·딸기·초코'},{'label':'판매 채널','value':'CU · 매장별 취급·입고 확인'}],
               'cta':'다섯 가지 취향 저장\n재고는 매장 확인','conditions':'가격은 공식 기사에 명시되지 않았습니다.\n발표 일정이며 매장별 입고는 다를 수 있습니다.',
               'caption':'CU BAKE405 리센느 컬래버 베이커리 5종 소식입니다. BGF가 '+f'{published:%Y.%m.%d} 공개한 자료에서 {launch:%Y.%m.%d}부터 순차 출시한다고 발표했습니다.\n'+'\n'.join(lines)+'\n가격은 기사에 명시되지 않았습니다. 실제 출시·취급·입고·재고는 매장에서 확인하세요.',
               'image_subject':'A realistic editorial bakery still life with five fictional pastries inspired by corn cream bread, melon bread, cinnamon roll, strawberry cream sandwich and chocolate hotteok, warm cafe daylight, no branded packaging, people or readable text'}
            c,receipt=finish(c,claims,sources,'bgf-rescene-bakery-v1')
            c['valid_until']=min(moment(c['valid_until']),published+timedelta(days=7)).isoformat()
            receipt['scope']='BGF 리센느 베이커리 기사에서 5개 제품명과 순차 출시 시작일 대조'
            receipt['omitted_fields']=['가격: 공식 기사에 명시되지 않음','포토카드: 먹거리 정보 중심 편집에서 제외']
            return c,receipt
        scheduled=list(re.finditer(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일\s*출시하는\s*‘([^‘’]{2,60}?)\(\s*([\d,]+)\s*원\s*\)\s*’",' '.join(article.split())))
        launch=None;price=None
        if scheduled:
            if len(scheduled)!=1:raise EvidenceError('한 원고에 담을 출시 제품이 여러 개입니다.')
            m=scheduled[0];name=m[3].strip();price=int(m[4].replace(',',''))
            launch=datetime(published.year,int(m[1]),int(m[2]),tzinfo=KST)
            if not 0<price<100000 or not 0<=(launch-published).days<=60:raise EvidenceError('출시 일정·가격 범위 확인 필요')
        else:
            names=re.findall(r'[‘“「]([^’”」]{2,24})[’”」]',title)
            if len(names)!=1:raise EvidenceError('제품명이 명확한 제목이 필요합니다.')
            name=names[0]
            match=re.search(r'[‘“「]'+re.escape(normalize(name))+r'[’”」](?:을|를)출시(?:한다|했다|했다고밝혔다)\.',normalize(article))
            if not match:raise EvidenceError('본문의 명시적 출시 문장 없음')
        scene=next((scene for words,scene in SCENES if any(w in name for w in words)),None)
        if not scene:raise EvidenceError('제품과 관련된 이미지 장면 규칙 없음')
        claims=[evidence(sources,key,'product',name,'dated-product-sentence' if launch else 'headline-and-launch-sentence'),evidence(sources,key,'publication',published.date().isoformat(),'article-header'),evidence(sources,key,'announcement','CU 출시 발표','affirmative-launch-sentence')]
        c={'source_id':key,'category':'food','title':'CU 출시 소식\n'+name,'subtitle':'BGF 공식 보도자료\n가격·재고는 판매처 확인',
           'intro_heading':'새로 발표한 먹거리','intro':name+'\nCU 출시 소식을 공식 자료에서 확인했어요.\n직접 시식한 후기는 아닙니다.',
           'facts':[{'label':'발표일','value':f'{published:%Y.%m.%d}'},{'label':'판매 채널','value':'CU · 매장별 취급 확인'},{'label':'구매 전 확인','value':'가격·입고·재고는 판매처 확인'}],
           'cta':'새 소식 저장\n구매 전 매장 확인','conditions':'발표일은 실제 입고일이 아닙니다.\n배경은 실제 제품 사진이 아닙니다.',
           'caption':f'CU의 {name} 출시 소식입니다. BGF가 {published:%Y.%m.%d} 공개한 자료에서 출시 발표를 확인했습니다.\n가격·취급 매장·실제 입고와 재고는 판매처에서 확인하세요.',
           'image_subject':scene+'. Editorial photograph inspired by a new convenience store food announcement, no branded packaging'}
        if launch:
            claims += [evidence(sources,key,'announced_launch',launch.date().isoformat(),'dated-product-sentence'),evidence(sources,key,'announced_price',price,'same-product-parentheses')]
            c.update(title=f'CU 신상 먹거리\n{launch:%m/%d} 출시 발표',subtitle=name+'\nBGF 공식 발표 기준',
                     intro=name+f'\n{launch:%Y.%m.%d} 출시 예정 발표\n실제 입고·재고는 매장에서 확인',
                     facts=[{'label':'제품 발표 가격','value':f'{price:,}원'},{'label':'출시 예정일 발표','value':f'{launch:%Y.%m.%d}'},{'label':'판매 채널','value':'CU · 매장별 취급·재고 확인'}],
                     caption=f'CU의 {name} 소식입니다. BGF가 {published:%Y.%m.%d} 공개한 자료에서 {launch:%Y.%m.%d} 출시 예정, {price:,}원으로 발표했습니다.\n발표 일정과 가격이며 실제 입고·재고·결제금액은 매장에서 확인하세요.')
        c,receipt=finish(c,claims,sources,'bgf-new-release-v1')
        c['valid_until']=min(moment(c['valid_until']),published+timedelta(days=7)).isoformat()
        receipt['scope']='BGF 제목·발표일·본문 출시 문장 규칙 대조'
        return c,receipt
    except EvidenceError:raise
    except (OSError,ValueError,KeyError,TypeError,IndexError,StopIteration) as e:raise EvidenceError('새 기사 원문을 검증할 수 없습니다.') from e


def adapters(root):
    try:report=json.loads((Path(root)/'data/runtime/collection/report.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):return []
    return [(s['id'],partial(make_release,key=s['id'])) for s in report.get('sources',[]) if s.get('adapter')=='bgf-release' and re.fullmatch(r'bgf-news-[1-9][0-9]{0,7}',s.get('id',''))]
