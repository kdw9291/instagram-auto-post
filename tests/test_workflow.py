import copy
import json
import tempfile
import unittest
from pathlib import Path
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
from src.store import Store, now, validate

ROOT = Path(__file__).resolve().parents[1]

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root/'data/inbox').mkdir(parents=True)
        self.c = {'source_id':'demo','sample':True,'category':'place','title':'테스트 전시','subtitle':'디자인 샘플','intro_heading':'전시 안내','intro':'테스트용 설명','facts':[{'label':'관람','value':'공식 안내 확인'}],'cta':'저장하기','conditions':'테스트 데이터','source_label':'예시 출처','sources':['https://example.com'],'caption':'샘플 캡션','verified_at':now().isoformat(),'valid_until':(now()+timedelta(hours=2)).isoformat()}
        self.store = Store(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def ingest(self, content=None):
        c = content or self.c
        (self.root/'data/inbox'/f"{c['source_id']}.json").write_text(json.dumps(c), encoding='utf-8')
        self.store.ingest()
        return next(i for i in self.store.snapshot()['items'] if i['source_id']==c['source_id'])

    def test_render_and_deduplicate_persist(self):
        item=self.ingest()
        self.store.ingest()
        self.assertEqual(len(Store(self.root).snapshot()['items']),1)
        self.assertEqual(item['state'],'waiting')
        for path in (self.root/'assets/images/generated').rglob('*.png'):
            with Image.open(path) as im:
                self.assertEqual(im.size,(1080,1350))
                im.verify()
        self.assertEqual(len(list((self.root/'assets/images/generated').rglob('*.png'))),4)

    def test_approval_edit_stale_version(self):
        item=self.ingest()
        self.store.action(item['id'],item['version'],'approve')
        self.store.action(item['id'],item['version'],'edit',self.c['caption']+'\n추가 안내')
        updated=self.store.snapshot()['items'][0]
        self.assertIsNone(updated['approval'])
        self.assertEqual(updated['state'],'waiting')
        with self.assertRaises(ValueError):
            self.store.action(item['id'],item['version'],'approve')

    def test_on_off_on_retains_existing_requirement(self):
        old=self.ingest()
        self.store.settings(False,1)
        c=copy.deepcopy(self.c);c['source_id']='second'
        new=self.ingest(c)
        self.assertEqual(new['state'],'ready')
        self.assertEqual(next(i for i in self.store.snapshot()['items'] if i['id']==old['id'])['state'],'waiting')
        self.store.settings(True,2)
        self.assertTrue(all(i['state']=='waiting' for i in self.store.snapshot()['items']))
        with self.assertRaises(ValueError):
            self.store.settings(False,2)

    def test_hold_prevents_reimport(self):
        item=self.ingest()
        self.store.action(item['id'],item['version'],'hold')
        self.c['caption']+='\n변경'
        item=self.ingest()
        self.assertEqual(item['state'],'held')

    def test_real_input_cannot_bypass_fact_verification(self):
        self.c.update(sample=False,verified_at=now().isoformat(),valid_until=(now()+timedelta(hours=2)).isoformat())
        self.store.settings(False,1)
        item=self.ingest()
        self.assertEqual(item['state'],'needs_verification')
        with self.assertRaises(ValueError):self.store.action(item['id'],item['version'],'approve')

    def test_expired_real_content(self):
        self.c.update(sample=False,verified_at=(now()-timedelta(days=2)).isoformat(),valid_until=(now()-timedelta(days=1)).isoformat())
        item=self.ingest()
        self.assertEqual(item['state'],'expired')
        with self.assertRaises(ValueError):self.store.action(item['id'],item['version'],'approve')

    def test_rejected_source_and_overflow(self):
        self.c['sources']=['javascript:alert(1)']
        with self.assertRaises(ValueError):validate(self.c)
        self.c['sources']=['https://example.com'];self.c['title']='가'*400
        (self.root/'data/inbox/bad.json').write_text(json.dumps(self.c),encoding='utf-8')
        self.store.ingest()
        self.assertEqual(self.store.snapshot()['items'],[])

    def test_double_approval_is_idempotent(self):
        item=self.ingest()
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _:self.store.action(item['id'],item['version'],'approve'),range(2)))
        self.assertEqual(sum('샘플 완성본 승인' in e['message'] for e in self.store.snapshot()['events']),1)

    def test_media_tampering_blocks_approval(self):
        item=self.ingest()
        path=self.root/'assets/images/generated'/item['id']/item['version']/'card-1.png'
        path.write_bytes(b'changed image')
        with self.assertRaises(ValueError):self.store.action(item['id'],item['version'],'approve')

    def test_topic_change_invalidates_approval_and_media_version(self):
        item=self.ingest();self.store.action(item['id'],item['version'],'approve')
        self.c['title']='주말 데이트 안내'
        self.c['subtitle']='산책 코스 안내'
        updated=self.ingest()
        self.assertNotEqual(item['version'],updated['version'])
        self.assertIsNone(updated['approval'])
        self.assertEqual(updated['background']['topic'],'outing')

if __name__=='__main__':unittest.main()
