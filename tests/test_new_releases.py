import io
import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from PIL import Image
from src.collector import Collector, bgf_url, fetch_allowed
from src.new_releases import make_release
from src.editorial import EvidenceError
from src.store import Store
from src.news_images import tick, rows

LIST='https://origin.bgf.co.kr/bgflive/detail/?category=pr'
URL='https://origin.bgf.co.kr/bgflive/view/?id=9999&categoryId=1'

class NewReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/'config').mkdir()
        (self.root/'config/sources.json').write_text(json.dumps({'sources':[{'id':'bgf-discovery','url':LIST,'kind':'html'}]}))
        self.date=datetime.now(timezone(timedelta(hours=9)))
        self.title='CU, ‘초코쿠키’ 출시'
        self.sentence='CU는 ‘초코쿠키’를 출시한다.'
        self.calls=[]
        self.link=URL
    def transport(self,url):
        self.calls.append(url)
        if url.endswith('/robots.txt'):return 'User-agent: *\nAllow: /'
        if url==LIST:return f'<a href="{self.link}">보도자료 {self.date:%y.%m.%d} {self.title}</a>'
        if url==URL:return f'<h1>{self.title}</h1><p>보도자료</p><p>{self.date:%Y.%m.%d}</p><p>{self.sentence}</p>'
        raise AssertionError('unexpected network target '+url)
    def collect(self,force=False):return Collector(self.root,self.transport).run(force)
    def test_new_url_fetch_composition_and_cache(self):
        report=self.collect();self.assertEqual(len(report['sources']),2)
        c,r=make_release(self.root,'bgf-news-9999')
        self.assertEqual(c['source_id'],'bgf-news-9999');self.assertIn('초코쿠키',c['title'])
        self.assertNotIn('3,200',c['caption']);self.assertEqual(len(r['claims']),3)
        self.collect();self.assertEqual(self.calls.count(URL),1)
    def test_expired_and_external_candidates_are_not_fetched(self):
        self.date-=timedelta(days=8);self.collect();self.assertNotIn(URL,self.calls)
        self.date+=timedelta(days=8);self.link='https://127.0.0.1/private';self.collect(True)
        self.assertNotIn(self.link,self.calls)
    def test_strict_url_validation(self):
        for u in ('http://origin.bgf.co.kr/bgflive/view/?id=1&categoryId=1',URL+'&id=2',URL+'&redirect=foo',URL.replace('origin.bgf.co.kr','origin.bgf.co.kr.evil.test'),URL+'#x',URL.replace('9999','../1')):
            with self.subTest(url=u),self.assertRaises(ValueError):bgf_url(u)
        self.assertEqual(bgf_url('https://origin.bgf.co.kr/bgflive/view/?categoryId=1&id=9999'),URL)
        with self.assertRaises(ValueError):fetch_allowed(URL,self.transport)
    def test_title_only_and_negative_launch_are_blocked(self):
        for sentence in ('가격은 추후 공개됩니다.','CU는 ‘초코쿠키’를 출시하지 않는다.','CU는 ‘초코쿠키’를 출시할 예정이다.'):
            self.sentence=sentence;self.collect(True)
            with self.assertRaises(EvidenceError):make_release(self.root,'bgf-news-9999')
    def test_mismatched_header_and_snapshot_tamper_are_blocked(self):
        report=self.collect();entry=report['sources'][-1]
        entry['headline']='CU, ‘다른쿠키’ 출시'
        (self.root/'data/runtime/collection/report.json').write_text(json.dumps(report))
        with self.assertRaises(EvidenceError):make_release(self.root,'bgf-news-9999')
        report=self.collect(True);entry=report['sources'][-1]
        (self.root/'data/runtime/collection'/f"{entry['id']}-{entry['snapshot_hash']}.json").write_text('{}')
        with self.assertRaises(EvidenceError):make_release(self.root,'bgf-news-9999')
    def test_dated_product_price_uses_same_sentence(self):
        self.title='CU, 가을 간편식 출시'
        self.sentence=f"{self.date.month}월 {self.date.day}일 출시하는 ‘풍성한 정찬 도시락 (6,500 원)’은 신제품이다. 다른 쿠키는 9,900원이다."
        self.collect();c,r=make_release(self.root,'bgf-news-9999')
        self.assertIn('6,500원',c['caption']);self.assertNotIn('9,900',c['caption'])
        self.assertEqual(len(r['claims']),5)
        self.sentence+=' '+self.sentence;self.collect(True)
        with self.assertRaises(EvidenceError):make_release(self.root,'bgf-news-9999')

    def test_paused_category_defers_before_image_creation(self):
        from src.operations import update,DEFAULT
        self.collect();store=Store(self.root)
        (self.root/'config/images.json').write_text(json.dumps({'required':True,'provider':'comfyui-local','checkpoint':'test'}))
        update(self.root,dict(DEFAULT,daily_food=0),1)
        store.produce();self.assertEqual(rows(self.root),[])
        self.assertEqual(store.snapshot()['operations']['deferred'][0]['reason'],'분야 제작 일시 정지')
        update(self.root,DEFAULT,2);store.produce()
        self.assertEqual(rows(self.root)[0]['state'],'queued')

    def test_new_url_to_generated_cards_and_approval_invalidation(self):
        self.collect()
        (self.root/'config/images.json').write_text(json.dumps({'required':True,'provider':'comfyui-local','checkpoint':'test'}))
        store=Store(self.root);store.produce();self.assertEqual(store.snapshot()['items'],[])
        self.assertEqual(rows(self.root)[0]['source_id'],'bgf-news-9999')
        data=io.BytesIO();Image.new('RGB',(832,1088),'gray').save(data,format='PNG')
        def engine(path,body=None,binary=False):
            if path.startswith('/object_info'):return {'CheckpointLoaderSimple':{'input':{'required':{'ckpt_name':[['test']]}}}}
            if path=='/prompt':return {'prompt_id':'job'}
            if path.startswith('/history'):return {'job':{'status':{'completed':True},'outputs':{'7':{'images':[{'filename':'one.png','type':'output'}]}}}}
            return data.getvalue()
        tick(self.root,engine);tick(self.root,engine);store.produce()
        item=store.snapshot()['items'][0];self.assertEqual(item['state'],'waiting');self.assertEqual(len(item['cards']),4)
        store.action(item['id'],item['version'],'approve')
        self.sentence='CU는 ‘초코쿠키’를 출시하지 않는다.';self.collect(True)
        item=store.snapshot()['items'][0];self.assertEqual(item['state'],'needs_verification');self.assertIsNone(item['approval'])

if __name__=='__main__':unittest.main()
