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
