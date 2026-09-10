const $ = (s) => document.querySelector(s);
const labels = {waiting:'확인 대기',ready:'자동 검수 후 준비',approved:'승인 기록',held:'이번 건 보류',expired:'정보 만료',needs_verification:'원문 검증 대기',awaiting_image:'뉴스 이미지 생성 대기'};
const categories = {place:'가볼 곳',beauty:'뷰티 신상',food:'신상 먹거리'};
let state, selected, slide = 0, busy = false;
function el(tag, text, cls) { const e=document.createElement(tag); if(text!==undefined)e.textContent=text; if(cls)e.className=cls;return e; }
function message(text) { $('#status').textContent=text; }
async function api(path, body) {
  const response=await fetch(path, body ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)} : {});
  const result=await response.json();if(!response.ok)throw Error(result.error || '요청을 처리하지 못했습니다.');return result;
}
function modeHelp() {
  $('#mode-help').textContent=$('#review').checked?'ON · 완성본 확인 후 발행하는 방식입니다. 연결 전에는 게시하지 않습니다.':'OFF · 새 제작물부터 확인 요청을 생략합니다. 기존 확인 대기물은 유지되며 자동 검수는 계속 필요합니다.';
}
const operationFields=[['daily_place','가볼 곳 · 하루 제작량',0,20],['daily_beauty','뷰티 · 하루 제작량',0,20],['daily_food','먹거리 · 하루 제작량',0,20],['max_pending','미완료 제작물 최대 건수',1,50],['duplicate_days','같은 제품·행사 중복 방지 일수',0,30],['retry_limit','이미지 실패 추가 재시도 횟수',0,5],['retry_minutes','실패 후 재시도 간격 · 분',1,120]];
for(const [key,label,min,max] of operationFields){const wrap=el('label',label);wrap.htmlFor=key;const input=el('input');input.id=key;input.type='number';input.min=min;input.max=max;input.step=1;input.required=true;wrap.append(input);$('#operation-fields').append(wrap);}
function renderOperations(){
  const ops=state.operations;
  for(const [key] of operationFields)$('#'+key).value=ops.settings[key];
  $('#operation-summary').textContent=`미완료 ${ops.pending}건 / 상한 ${ops.settings.max_pending}건. 기존 완성본·진행 중 제작은 유지합니다. 실패가 확정된 이미지 요청만 재시도합니다.`;
  $('#operation-deferred').replaceChildren(...ops.deferred.map(d=>el('p',d.title+' · '+d.reason,'muted')));
}
async function refresh() {
  state=await api('/api/state');
  const available=i=>!i.content.sample && ['waiting','ready','approved'].includes(i.state) && !(state.studio_posts||[]).some(p=>p.source_id===i.source_id && p.kind==='cards' && p.state==='published');
  state.items.sort((a,b)=>Number(available(b))-Number(available(a)));
  const current=state.items.find(i=>i.id===selected);
  if(!current || !available(current)){selected=state.items.find(available)?.id || state.items[0]?.id;slide=0;}

  $('#review').checked=state.settings.review;modeHelp();
  $('#count').textContent=`확인 가능 ${state.items.filter(available).length}건 / 전체 ${state.items.length}건`;
  const list=$('#items');list.replaceChildren();
  if(!state.items.length)list.append(el('p','준비된 제작물이 없습니다. 새 콘텐츠 만들기를 눌러 시작하세요.','empty'));
  state.items.forEach(item=>{
    const b=el('button',undefined,'item'+(item.id===selected?' selected':''));
    const img=el('img');img.src=item.cards[0];img.alt='';b.append(img,el('strong',item.content.title),el('small',(item.content.sample?'샘플 · ':'')+labels[item.state]));
    b.setAttribute('aria-pressed',String(item.id===selected));
    b.onclick=()=>{selected=item.id;slide=0;renderDetail();document.querySelectorAll('.item').forEach(x=>{x.classList.toggle('selected',x===b);x.setAttribute('aria-pressed',String(x===b));});};list.append(b);
  });
  $('#produce').disabled=Boolean(state.studio?.busy);$('#studio-progress').textContent=state.studio?.message||'새 콘텐츠 만들기로 시작하세요.';
  renderDetail();
  renderCollection();
  renderOperations();
  const jobs=el('section');jobs.append(el('h2','뉴스별 이미지 제작'));
  const jobLabels={queued:'생성 대기',submitting:'생성 요청 중',submitted:'이미지 생성 중',ready:'이미지 생성 완료',failed:'생성 실패 · 보류',uncertain:'요청 결과 확인 중',superseded:'새 원고로 교체',cancelled:'보류·만료로 생성 중단'};
  const newsNames={'apma-auto-4128332':'솔 르윗 전시','hera-auto-70922':'헤라 새 틴트','bgf-auto-2024':'CU 새 빵'};
  (state.image_jobs || []).filter((j,i,all)=>all.findIndex(x=>x.source_id===j.source_id)===i).forEach(j=>jobs.append(el('p',`${newsNames[j.source_id] || state.items.find(i=>i.source_id===j.source_id)?.content.title || '새 뉴스'} · ${jobLabels[j.state] || j.state}${j.error?' · 생성 상태를 확인하고 있습니다.':''}`)));
  jobs.append(el('h2','발행 준비'));
  jobs.append(el('p','게시 버튼을 누른 형식만 발행합니다. 처리 중에는 창을 닫지 마세요.'));
  const publishLabels={prepared:'계정·이미지 주소 연결 대기',containers:'미디어 준비 중',ready:'발행 준비됨',sending:'전송 중',uncertain:'전송 결과 확인 필요',published:'게시 완료',cancelled:'변경·만료로 취소',failed:'발행 준비 실패'};
  if(!(state.publish_jobs||[]).length)jobs.append(el('p','발행 준비 중인 원고가 없습니다.'));
  (state.publish_jobs||[]).forEach(j=>jobs.append(el('p',(state.items.find(i=>i.id===j.item_id)?.content.title||'이전 원고')+' · '+publishLabels[j.state])));
  jobs.append(el('h2','새 소재 대기열'));
  const candidateLabels={linked:'공식 원문 연결됨',discovered:'원문 검증 연결 대기',needs_date:'발표일 보완 대기',expired:'기한 경과',registered:'자동 제작 원문으로 등록됨',checking:'새 원문 자동 검증 대상'};
  (state.candidates || []).forEach(c=>{const p=el('p'),a=el('a',c.title);a.href=c.url;a.target='_blank';a.rel='noopener noreferrer';p.append(a,el('small',' · '+candidateLabels[c.state]));if(c.official){const official=el('a',' · 공식 근거: '+c.official.name);official.href=c.official.url;official.target='_blank';official.rel='noopener noreferrer';p.append(official);}jobs.append(p);});
  const statusNames={queued:'게시 대기',working:'업로드 중',creating:'영상 준비 중',processing:'영상 처리 중',sending:'게시 전송 중',published:'게시 완료',interrupted:'처리 상태 확인 필요',failed:'처리 실패',uncertain:'결과 확인 필요',cancelled:'취소됨'};
  (state.studio_posts||[]).forEach(p=>{const line=el('p',(p.kind==='cards'?'카드뉴스':'릴스')+' · '+(statusNames[p.state]||p.state));if(p.link){const a=el('a',' 게시물 열기');a.href=p.link;a.target='_blank';a.rel='noopener noreferrer';line.append(a);}jobs.append(line);});
  $('#collection').append(jobs);
  $('#events').replaceChildren(...state.events.map(event=>{const li=el('li',event.message);const time=el('time',new Date(event.at).toLocaleString('ko-KR'));time.dateTime=event.at;li.append(time);return li;}));
}
async function act(action, item, caption) {
  await run(async()=>{await api('/api/action',{id:item.id,version:item.version,action,caption});await refresh();message(action==='approve'?'완성본 승인을 기록했습니다. 계정 연결 전으로 실제 게시하지 않습니다.':action==='edit'?'새 캡션을 저장했습니다. 이전 승인은 해제됩니다.':'이번 소재를 보류했습니다.');});
}
function renderDetail() {
  const target=$('#detail'), item=state.items.find(i=>i.id===selected);target.replaceChildren();
  if(!item){target.append(el('p','완성본이 준비되면 여기에 표시됩니다.','empty'));return;}
  const c=item.content, top=el('div',undefined,'detail-top');top.append(el('span',categories[c.category],'tag'),el('span',labels[item.state],'tag'),el('span',c.sample?'디자인 샘플':'공식 자료 자동 원고','tag'));
  target.append(top,el('h2',c.title.replaceAll('\n',' ')));
  const preview=el('div',undefined,'preview'), image=el('img');image.src=item.cards[slide];image.alt=`${c.title.replaceAll('\n',' ')} 카드 ${slide+1}/4. 전체 정보는 아래 캡션과 출처에서 확인할 수 있습니다.`;preview.append(image);target.append(preview);
  const slides=el('div',undefined,'slides');slides.setAttribute('aria-label','카드 선택');
  for(let i=0;i<4;i++){const b=el('button',String(i+1));b.setAttribute('aria-label',`${i+1}번 카드 보기`);b.setAttribute('aria-pressed',String(i===slide));b.onclick=()=>{slide=i;image.src=item.cards[slide];image.alt=`${c.title.replaceAll('\n',' ')} 카드 ${slide+1}/4. 정보는 아래 캡션 참조.`;download.href=item.cards[slide];download.download=`card-${slide+1}.png`;slides.querySelectorAll('button').forEach((x,j)=>x.setAttribute('aria-pressed',String(j===i)));};slides.append(b);}target.append(slides);
  const download=el('a','현재 카드 PNG 내려받기','download');download.href=item.cards[slide];download.download=`card-${slide+1}.png`;target.append(download);
  if(item.reel){const video=el('video');video.src=item.reel.url;video.controls=true;video.preload='metadata';video.setAttribute('aria-label','30초 릴스 미리보기');video.className='reel-preview';target.append(el('h3','30초 릴스'),video);}else if(!c.sample){target.append(el('p','릴스 미준비 · 새 콘텐츠 만들기로 영상까지 제작하세요.','muted'));}
  const label=el('label','캡션','caption-label');label.htmlFor='caption';const caption=el('textarea');caption.id='caption';caption.value=c.caption;caption.maxLength=2200;target.append(label,caption);
  const actions=el('div',undefined,'actions');
  const approve=el('button',c.sample?'샘플 · 게시 불가':'카드만 게시');approve.disabled=true;approve.onclick=()=>publishFormats(item,['cards']);
  const save=el('button','캡션 변경 저장','secondary');save.disabled=['held','expired'].includes(item.state);save.onclick=()=>act('edit',item,caption.value);
  const reelButton=el('button','릴스만 게시','secondary'),both=el('button','둘 다 게시');reelButton.onclick=()=>publishFormats(item,['reel']);both.onclick=()=>publishFormats(item,['cards','reel']);
  const posted=(kind)=>(state.studio_posts||[]).some(p=>p.source_id===item.source_id && p.kind===kind);
  const setButtons=()=>{const blocked=state.studio?.busy||c.sample||!['waiting','ready','approved'].includes(item.state)||caption.value!==c.caption;approve.disabled=blocked||posted('cards');reelButton.disabled=blocked||!item.reel||posted('reel');both.disabled=approve.disabled||reelButton.disabled;};setButtons();caption.addEventListener('input',setButtons);
  const hold=el('button','이번 건 보류','secondary');hold.disabled=['held','expired'].includes(item.state);hold.onclick=()=>act('hold',item);actions.append(both,approve,reelButton,save,hold);target.append(actions);
  target.append(el('p',c.sample?'샘플은 디자인 확인용입니다.': '공식 자료의 항목별 대조로 작성했습니다. 캡션을 직접 변경하면 근거 재검증 전 승인이 보류됩니다. 게시 버튼을 누르면 확인한 버전을 실제 Instagram에 게시합니다.','muted'));
  const details=el('details');details.append(el('summary','출처와 정보 확인일'));c.sources.forEach(url=>{const p=el('p'),a=el('a',url);a.href=url;a.target='_blank';a.rel='noopener noreferrer';p.append(a);details.append(p);});details.append(el('p',`원고 확인: ${new Date(c.verified_at).toLocaleString('ko-KR')} · ${item.background.label}`));target.append(details);
  if(!c.sample){
    details.append(el('p',`정보 유효기한: ${new Date(c.valid_until).toLocaleString('ko-KR')}`));
    const fields={event_title:'전시 제목',dates:'기간',hours:'관람시간',last_entry:'입장마감',closures:'휴관일',reservation:'예약',address:'주소',adult_price:'성인 요금',product:'제품명',capacity:'용량',launch:'선런칭 발표',options:'색상 옵션',option_count:'색상 수',list_price:'표시·발표 가격',store_link:'공식 구매 연결',publication:'발표일',announced_launch:'제품별 발표 일정'};
    const evidence=el('details');evidence.append(el('summary',`항목별 근거 ${(item.verification?.claims || []).length}건`));
    (item.verification?.claims || []).forEach(claim=>{const p=el('p'),a=el('a',`${fields[claim.field] || claim.field} · ${claim.source_id}`);a.href=claim.url;a.target='_blank';a.rel='noopener noreferrer';p.append(a);evidence.append(p);});target.append(evidence);
  }
}
function renderCollection() {
  const target=$('#collection');target.replaceChildren();
  if(!state.collection.sources.length){target.append(el('p','첫 인터넷 수집을 기다리고 있습니다.','muted'));return;}
  state.collection.sources.forEach(source=>{
    const section=el('article',undefined,'source-row');section.append(el('h3',source.name));
    const matched=source.checks.filter(c=>c.status==='matched').length;
    section.append(el('p',source.status==='ok'?`조회 성공 · 분야 후보 ${source.candidates.length}건${source.checks.length?` · 조사 기준 표기 ${matched}/${source.checks.length}개 발견`:''}`:'접근 실패 · 자동 보류'));
    if(source.checks.some(c=>c.status!=='matched'))section.append(el('p','확인되지 않은 항목: '+source.checks.filter(c=>c.status!=='matched').map(c=>c.field).join(', '),'muted'));
    const a=el('a','공식 출처 열기');a.href=source.url;a.target='_blank';a.rel='noopener noreferrer';section.append(a,el('p',`확인: ${new Date(source.checked_at).toLocaleString('ko-KR')}`,'muted'));
    if(source.candidates.length){const details=el('details');details.append(el('summary','발견한 소식 보기'));source.candidates.slice(0,10).forEach(c=>{const p=el('p'),link=el('a',c.title);link.href=c.url;link.target='_blank';link.rel='noopener noreferrer';p.append(link);details.append(p);});section.append(details);}
    target.append(section);
  });
}
async function run(fn) { if(busy)return;busy=true;document.body.setAttribute('aria-busy','true');try{await fn();}catch(e){message(e.message);}finally{busy=false;document.body.removeAttribute('aria-busy');} }
$('#settings-form').onsubmit=e=>{e.preventDefault();run(async()=>{await api('/api/settings',{review:$('#review').checked,revision:state.settings.revision});await refresh();message(`완성본 확인 ${state.settings.review?'ON':'OFF'}으로 저장했습니다.`);});};
$('#review').onchange=modeHelp;$('#refresh').onclick=()=>run(refresh);
run(refresh);

$('#operations-form').onsubmit=e=>{e.preventDefault();run(async()=>{const values=Object.fromEntries(operationFields.map(([key])=>[key,Number($('#'+key).value)]));await api('/api/operations',{values,revision:state.operations.settings.revision});await refresh();message('운영 한도를 저장했습니다. 새 제작부터 적용합니다.');});};

async function publishFormats(item,formats){await run(async()=>{await api('/api/publish-formats',{id:item.id,version:item.version,formats,sha:item.reel?.sha256});message('게시를 시작했습니다. 완료까지 창을 열어두세요.');await refresh();});}
$('#produce').onclick=()=>run(async()=>{await api('/api/produce',{});await refresh();});
setInterval(async()=>{if(!busy && state?.studio?.busy){try{const next=await api('/api/state');$('#studio-progress').textContent=next.studio.message;state.studio=next.studio;if(!next.studio.busy)await refresh();}catch(e){message('작업실 연결을 확인해 주세요.');}}},3000);
