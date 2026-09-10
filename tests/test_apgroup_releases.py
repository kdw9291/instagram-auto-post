import io
import json
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from PIL import Image
from src.collector import Collector,apgroup_url,fetch_allowed
from src.apgroup_releases import make_news
from src.editorial import EvidenceError
from src.store import Store
from src.news_images import tick

LIST='https://www.apgroup.com/int/ko/news/news.html'

class ApgroupNewsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/'config').mkdir()
        (self.root/'config/sources.json').write_text(json.dumps({'sources':[{'id':'apgroup-discovery','url':LIST,'kind':'html'}]}))
        self.date=datetime.now(timezone(timedelta(hours=9))).replace(hour=0,minute=0,second=0,microsecond=0)
        end=self.date+timedelta(days=3)
        self.urls=[f'https://www.apgroup.com/int/ko/news/{self.date:%Y-%m-%d}-{n}.html' for n in (1,2)]
        self.keys=[f'ap-news-{self.date:%Y-%m-%d}-{n}' for n in (1,2)]
        self.titles=["설화수, '시간 여행' 선보여", "일리윤, 새 클렌저 출시"]
        self.bodies=[f"북촌 설화수의 집에서 진행되는 '시간 여행' 프로그램은 {self.date.month}월 {self.date.day}일부터 {end.month}월 {end.day}일까지 운영된다.\n온라인 테스트를 완료한 고객은 북촌 설화수의 집에서 현장 프로그램을 체험할 수 있다.", "일리윤이 첫 제품으로 '새 버블 클렌저'를 선보였다.\n사용 시 치료 효과가 뛰어나고 0세부터 안전하다. 가격 99,000원."]
        self.calls=[]
    def transport(self,url):
        self.calls.append(url)
        if url.endswith('/robots.txt'):return 'User-agent: *\nAllow: /'
        if url==LIST:return ''.join(f'<a href="{u}">브랜드 {t} {self.date:%Y-%m-%d}</a>' for u,t in zip(self.urls,self.titles))
        i=self.urls.index(url)
        return f'<h1>{self.titles[i]}</h1><p>브랜드</p><p>{self.date:%Y-%m-%d}</p><p>{self.bodies[i]}</p><p>목록</p><p>FOOTER</p>'
    def collect(self,force=False):return Collector(self.root,self.transport).run(force)
    def test_discover_both_categories_and_cache(self):
        report=self.collect();self.assertEqual(len(report['sources']),3)
        self.collect();self.assertEqual(self.calls.count(self.urls[0]),1)
        self.assertEqual([make_news(self.root,k)[0]['category'] for k in self.keys],['place','beauty'])
    def test_beauty_never_copies_efficacy_or_unverified_price(self):
        self.collect();c,r=make_news(self.root,self.keys[1])
        self.assertIn('새 버블 클렌저',c['caption'])
        for term in ('치료 효과','0세','99,000','안전하다'):self.assertNotIn(term,c['caption'])
        self.assertEqual(len(r['claims']),3)
    def test_news_link_requires_current_official_evidence(self):
        from src.discovery import sync
        from email.utils import format_datetime
        self.bodies[1]="일리윤이 신제품 '베리어 리커버리 버블 클렌저'를 출시했다."
        report=self.collect()
        report['sources'].append({'id':'rss','status':'ok','url':'https://www.hankyung.com/feed/life','checked_at':datetime.now(timezone.utc).isoformat(),'candidates':[{'title':'일리윤 베리어 리커버리 버블 클렌저 출시','url':'https://www.hankyung.com/article/123','category':'beauty','published_at':format_datetime(self.date)}]})
        linked=next(c for c in sync(self.root,report) if c['source_id']=='rss')
        self.assertEqual(linked['state'],'linked')
        self.assertEqual(linked['official']['source_id'],self.keys[1])
        self.bodies[1]=self.bodies[1].replace('출시했다','출시하지 않았다');self.collect(True)
        self.assertEqual(next(c for c in sync(self.root,report) if c['source_id']=='rss')['state'],'discovered')

    def test_exhibition_explicit_reservation_and_ambiguity(self):
        end=self.date+timedelta(days=3)
        self.titles[0]="설화수, '새로운 빛' 전시"
        self.bodies[0]=f"서울 미술관에서 진행되는 '새로운 빛' 전시는 {self.date.month}월 {self.date.day}일부터 {end.month}월 {end.day}일까지 운영된다.\n'새로운 빛'은 사전 예약 후 참여할 수 있다."
        self.collect();c,r=make_news(self.root,self.keys[0])
        self.assertIn('사전 예약 후 참여',c['caption'])
        self.assertNotIn('무료',c['caption'])
        self.bodies[0]+="\n'새로운 빛'은 현장 접수 후 참여할 수 있다."
        self.collect(True)
        with self.assertRaises(EvidenceError):make_news(self.root,self.keys[0])

    def test_recent_dynamic_news_precede_fixed_sources(self):
        from src.editorial import editorial_adapters
        self.collect()
        ids=[key for key,maker in editorial_adapters(self.root)]
        self.assertEqual(ids[:2],self.keys)
        self.assertEqual(ids[2],'apma-auto-4128332')

    def test_additional_product_launch_sentence(self):
        self.bodies[1]="일리윤이 신제품 '새 버블 클렌저'를 출시했다."
        self.collect();c,r=make_news(self.root,self.keys[1])
        self.assertIn('새 버블 클렌저',c['caption'])
        self.bodies[1]=self.bodies[1].replace('출시했다','출시하지 않았다');self.collect(True)
        with self.assertRaises(EvidenceError):make_news(self.root,self.keys[1])

    def test_missing_affirmative_launch_blocks(self):
        self.bodies[1]=self.bodies[1].replace('선보였다','선보이지 않았다');self.collect()
        with self.assertRaises(EvidenceError):make_news(self.root,self.keys[1])
    def test_participation_and_conflicting_dates_block(self):
        original=self.bodies[0]
        for body in (original.replace('온라인 테스트를 완료한 고객은','누구나'),original+'\n'+original,original+'\n초청 고객을 추첨한다.'):
            self.bodies[0]=body;self.collect(True)
            with self.assertRaises(EvidenceError):make_news(self.root,self.keys[0])
    def test_url_boundary_and_expired_list(self):
        for u in (self.urls[0]+'?next=x',self.urls[0]+'#x',self.urls[0].replace('www.apgroup.com','www.apgroup.com.evil.test'),self.urls[0].replace('https:','http:'),LIST):
            with self.subTest(url=u),self.assertRaises(ValueError):apgroup_url(u)
        with self.assertRaises(ValueError):fetch_allowed(self.urls[0],self.transport)
        self.date-=timedelta(days=8);self.collect();self.assertNotIn(self.urls[0],self.calls)
    def test_channel_claim_requires_matching_body(self):
        self.titles[1]='일리윤, 병의원 판매 클렌저 출시';self.collect()
        with self.assertRaises(EvidenceError):make_news(self.root,self.keys[1])
    def test_ended_program_blocks_even_with_fresh_news(self):
        start=self.date-timedelta(days=3);end=self.date-timedelta(days=1)
        self.bodies[0]=f"북촌 설화수의 집에서 진행되는 '시간 여행' 프로그램은 {start.month}월 {start.day}일부터 {end.month}월 {end.day}일까지 운영된다.\n온라인 테스트를 완료한 고객은 북촌 설화수의 집에서 참여한다."
        self.collect()
        with self.assertRaises(EvidenceError):make_news(self.root,self.keys[0])
    def test_new_place_images_cards_and_source_change_invalidates_approval(self):
        self.collect();(self.root/'config/images.json').write_text(json.dumps({'required':True,'provider':'comfyui-local','checkpoint':'test'}))
        store=Store(self.root);store.produce();self.assertEqual(store.snapshot()['items'],[])
        data=io.BytesIO();Image.new('RGB',(832,1088),'gray').save(data,format='PNG')
        def engine(path,body=None,binary=False):
            if path.startswith('/object_info'):return {'CheckpointLoaderSimple':{'input':{'required':{'ckpt_name':[['test']]}}}}
            if path=='/prompt':return {'prompt_id':'job'}
            if path.startswith('/history'):return {'job':{'status':{'completed':True},'outputs':{'7':{'images':[{'filename':'one.png','type':'output'}]}}}}
            return data.getvalue()
        for _ in range(4):tick(self.root,engine)
        store.produce();items=store.snapshot()['items'];self.assertEqual(len(items),2)
        for i in items:self.assertEqual(i['state'],'waiting');self.assertEqual(len(i['cards']),4)
        item=next(i for i in items if i['content']['category']=='place');store.action(item['id'],item['version'],'approve')
        self.bodies[0]=self.bodies[0].replace('온라인 테스트를 완료한 고객은','누구나');self.collect(True)
        item=next(i for i in store.snapshot()['items'] if i['id']==item['id'])
        self.assertEqual(item['state'],'needs_verification');self.assertIsNone(item['approval'])

if __name__=='__main__':unittest.main()
