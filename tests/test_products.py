import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch
from src.products import make_hera, make_bakery, HERA_URLS, BAKERY_URLS
from src.editorial import EvidenceError
from src.store import Store


class ProductTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.at=datetime.now(timezone.utc)
        self.date=self.at.replace(day=1)
        self.urls={**HERA_URLS,**BAKERY_URLS}
        self.sources={
          'hera-release':{'text':f'{self.date:%Y.%m.%d}\n센슈얼 샤인 틴트\n총 2가지 컬러\n{self.date.month}월 1일 카카오톡 선물하기 선런칭'},
          'hera-product':{'text':'센슈얼 샤인 틴트\nSENSUAL SHINE TINT\n5g\n구매하러 가기,'+HERA_URLS['hera-store']+'\n센슈얼 샤인 틴트 컬러\n66호 / 베스티\n352호 / 루비\n[필수]'},
          'hera-store':{'text':'NEW 센슈얼 샤인 틴트 5g\nselected option\n66 베스티\n352 루비\n네이버페이', 'fields':{'price_origin':['10 % 40,000 원'],'price_discount':['36,000 원']}},
          'bgf-bakery':{'text':f'BAKE405 리브랜딩! CU, 편의점 베이커리 2.0시대 연다\n{self.date:%Y.%m.%d}\n‘마블크림 시리즈’(각 3,200원)\nBAKE405 마블크림 시리즈는 {self.date.month}월부터 순차 출시된다. 1일 ‘마블초코크림빵’을 시작으로 3일 ‘마블레몬피쵸크림빵’을 선보인다. 이어 9일 ‘마블딸기연유크림빵’, 16일 ‘마블시나몬메이플크림빵’을 출시한다.'}}
        self.write()

    def write(self):
        out=self.root/'data/runtime/collection';out.mkdir(parents=True,exist_ok=True)
        report={'sources':[]}
        for key,data in self.sources.items():
            source=dict(data,url=self.urls[key],checked_at=self.at.isoformat(),tables=[])
            raw=json.dumps(source,ensure_ascii=False,sort_keys=True).encode();h=hashlib.sha256(raw).hexdigest()
            (out/f'{key}-{h}.json').write_bytes(raw)
            report['sources'].append(dict(id=key,status='ok',url=self.urls[key],checked_at=self.at.isoformat(),snapshot_hash=h))
        (out/'report.json').write_text(json.dumps(report),encoding='utf-8')

    def test_hera_uses_original_price_and_verified_options(self):
        c,r=make_hera(self.root,self.at)
        self.assertIn('40,000원',c['caption']);self.assertNotIn('36,000',c['caption'])
        self.assertIn('2가지 컬러',c['title']);self.assertEqual(len(r['claims']),7)

    def test_hera_rejects_capacity_option_and_link_mismatch(self):
        for key,old,new in [('hera-store','5g','3g'),('hera-store','352 루비','353 루비'),('hera-product',HERA_URLS['hera-store'],'https://example.com/')]:
            with self.subTest(key=key,old=old):
                original=self.sources[key]['text'];self.sources[key]['text']=original.replace(old,new);self.write()
                with self.assertRaises(EvidenceError):make_hera(self.root,self.at)
                self.sources[key]['text']=original

    def test_hera_does_not_promote_missing_original_price(self):
        self.sources['hera-store']['fields'].pop('price_origin');self.write()
        with self.assertRaises(EvidenceError):make_hera(self.root,self.at)

    def test_bakery_preserves_announced_dates_after_they_pass(self):
        c,r=make_bakery(self.root,self.at)
        self.assertEqual(len(r['claims']),6)
        self.assertIn('발표',c['caption']);self.assertIn('09',c['intro'])
        self.assertIn('실제 출시·입고를 보장하지 않습니다',c['caption'])

    def test_bakery_missing_schedule_or_price_blocks(self):
        original=self.sources['bgf-bakery']['text']
        for old in ('16일','각 3,200원'):
            self.sources['bgf-bakery']['text']=original.replace(old,'누락');self.write()
            with self.assertRaises(EvidenceError):make_bakery(self.root,self.at)

    def test_failed_category_does_not_stop_other_draft(self):
        self.sources.pop('hera-store');self.write()
        store=Store(self.root);store.produce()
        self.assertEqual([i['content']['category'] for i in store.snapshot()['items']],['food'])

    def test_approval_and_visual_revision_invalidation(self):
        store=Store(self.root);store.produce()
        item=next(i for i in store.snapshot()['items'] if i['content']['category']=='beauty')
        store.action(item['id'],item['version'],'approve')
        with patch('src.products.visual_revision',return_value='changed-background'):
            updated=next(i for i in store.snapshot()['items'] if i['id']==item['id'])
            self.assertEqual(updated['state'],'needs_verification');self.assertIsNone(updated['approval'])
            store.produce()
            updated=next(i for i in store.snapshot()['items'] if i['id']==item['id'])
            self.assertEqual(updated['state'],'waiting');self.assertNotEqual(updated['version'],item['version'])

    def test_news_image_required_and_tamper_invalidates_approval(self):
        from src.news_images import tick
        from PIL import Image
        import io
        (self.root/'config').mkdir()
        (self.root/'config/images.json').write_text(json.dumps({'required':True,'provider':'comfyui-local','checkpoint':'test'}))
        store=Store(self.root);store.produce()
        self.assertEqual(store.snapshot()['items'],[])
        data=io.BytesIO();Image.new('RGB',(832,1088),'gray').save(data,format='PNG')
        def transport(path,body=None,binary=False):
            if path.startswith('/object_info'):return {'CheckpointLoaderSimple':{'input':{'required':{'ckpt_name':[['test']]}}}}
            if path=='/prompt':return {'prompt_id':'test-job'}
            if path.startswith('/history'):return {'test-job':{'status':{'completed':True},'outputs':{'7':{'images':[{'filename':'one.png','type':'output'}]}}}}
            return data.getvalue()
        tick(self.root,transport);tick(self.root,transport);store.produce()
        item=store.snapshot()['items'][0]
        self.assertEqual(item['state'],'waiting')
        store.action(item['id'],item['version'],'approve')
        image=self.root/'assets/images/news'/f"{item['content']['news_image']['id']}.png"
        image.write_bytes(b'changed')
        item=store.snapshot()['items'][0]
        self.assertEqual(item['state'],'needs_verification');self.assertIsNone(item['approval'])


if __name__=='__main__':unittest.main()
