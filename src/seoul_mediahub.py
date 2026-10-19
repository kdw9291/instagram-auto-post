"""Current official Seoul articles; labelled event facts outside AI summaries."""
import re
from datetime import datetime,timedelta
from .collector import seoul_url,seoul_key
from .editorial import EvidenceError,KST,load_sources,moment,normalize,unique
from .products import finish,evidence


def make_mediahub(root,entry,at):
    key=entry['id'];url=seoul_url(entry['url'])
    if key!=seoul_key(url):raise EvidenceError('내 손안에 서울 기사 식별 불일치')
    sources=load_sources(root,at,{key:url});text=sources[key]['text']
    header=unique(r'\n발행일\n(20\d{2}\.\d{2}\.\d{2}\. \d{2}:\d{2})\n',text,'공식 발행일')[1]
    published=datetime.strptime(header,'%Y.%m.%d. %H:%M').replace(tzinfo=KST)
    if published!=moment(entry['published']) or not timedelta(0)<=at-published<timedelta(days=7):raise EvidenceError('내 손안에 서울 발행일·7일 기한 확인 필요')
    title=entry['headline']
    if title+'\n내 손안에 서울\n발행일\n' not in text:raise EvidenceError('내 손안에 서울 제목·발행일 경계 불일치')
    # Read only the labelled event overview, after the AI-summary area.
    marker='남산 야간트래킹 ‘반짝반짝 남산밤길’\n'
    if text.count(marker)!=1:raise EvidenceError('공식 행사 개요를 확인할 수 없습니다.')
    article=text.split(marker,1)[1].split('\n중구 상생야장',1)[0]
    normalized=normalize(article)
    schedule=unique(r'○행사일시:(20\d{2})년(\d{1,2})월(\d{1,2})일,(\d{1,2})월(\d{1,2})일오후(\d{1,2})시~(\d{1,2})시\(오후(\d{1,2})시부터접수\)',normalized,'공식 두 회차 일정')
    year,month,day,month2,day2,opening,closing,reception=map(int,schedule.groups())
    if not 1<=reception<opening<closing<=11 or year!=published.year:raise EvidenceError('접수·행사 시간 확인 필요')
    dates=[datetime(year,month,day,opening+12,tzinfo=KST),datetime(year,month2,day2,opening+12,tzinfo=KST)]
    if not dates[0]<dates[1] or any(not -1<=(d-published).days<=90 for d in dates):raise EvidenceError('회차별 날짜 관계 확인 필요')
    remaining=[d for d in dates if d.replace(hour=closing+12)>at]
    if not remaining:raise EvidenceError('종료된 행사입니다.')
    venue=unique(r'※ 집결지\s*:\s*([^\n]{2,60})',article,'공식 집결지')[1].strip()
    limit=int(unique(r'○참여방법:사전신청없이회당현장선착순(\d{1,4})명접수',normalized,'공식 현장 접수')[1])
    if not 1<=limit<=5000 or normalize(venue).split('천우각')[0] not in normalized:raise EvidenceError('참여 인원·장소 확인 필요')
    name='반짝반짝 남산밤길';hours=f'{opening+12:02}:00–{closing+12:02}:00';labels=' · '.join(f'{d:%m/%d}' for d in remaining)
    registration=f'{reception+12:02}:00 현장 접수 · 선착순 {limit}명'
    claims=[evidence(sources,key,'publication',header,'official-publication-header'),evidence(sources,key,'event',name,'labelled-event-heading'),evidence(sources,key,'dates',[d.date().isoformat() for d in remaining],'event-overview-dates'),evidence(sources,key,'hours',hours,'event-overview-hours'),evidence(sources,key,'venue',venue,'event-overview-meeting-place'),evidence(sources,key,'registration',registration,'event-overview-admission')]
    content={'source_id':key,'category':'place','title':'남산의 가을밤\n빛을 따라 걷는 시간','subtitle':name+'\n서울시 공식 행사 안내',
      'intro_heading':'날짜와 접수부터 확인','intro':labels+' · '+hours+'\n'+venue+' 집결\n'+registration,
      'facts':[{'label':'행사 일정','value':labels+' · '+hours},{'label':'집결 장소','value':venue},{'label':'참여 방법','value':registration}],
      'cta':'야간 산책 일정 저장\n출발 전 공식 확인','conditions':'참가비·우천 변경은 공식 안내 확인\n선착순 접수이며 참여를 보장하지 않습니다.',
      'caption':name+' 야간 트래킹 소식입니다.\n서울시 내 손안에 서울 '+f'{published:%Y.%m.%d}'+' 공식 발행 자료 기준.\n일정: '+labels+' · '+hours+'\n집결: '+venue+'\n접수: '+registration+' · 사전 신청 없이 현장 접수\n참가비·준비물·우천 및 당일 운영 변경은 공식 안내에서 확인하세요. 참여를 보장하지 않습니다.',
      'image_subject':'Photorealistic editorial night landscape of a fictional wooded hillside walking trail above Seoul, warm amber pathway lights and distant city bokeh, autumn foliage, quiet blue hour atmosphere, empty trail, no people, faces, signs, logos or readable text. A conceptual scene, not the actual event'}
    content,receipt=finish(content,claims,sources,'seoul-mediahub-labelled-walk-v1')
    content['valid_until']=min(moment(content['valid_until']),published+timedelta(days=7),remaining[0].replace(hour=closing+12)).isoformat()
    content['caption']=content['caption'].replace('직접 사용·시식 후기','직접 방문 후기').replace('실제 제품·발색·단면','실제 행사 현장')
    receipt['scope']='서울시 내 손안에 서울 발행일·AI 요약 밖 행사 개요의 날짜·시간·집결지·현장 접수 대조'
    return content,receipt
