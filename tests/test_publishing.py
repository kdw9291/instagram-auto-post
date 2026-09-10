import json
import tempfile
import unittest
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from src.store import Store,now
from src.publishing import Outbox

class FakeAPI:
    def __init__(self):self.calls=[];self.fail=False;self.code='FINISHED'
    def image(self,url):self.calls.append('image');return str(len(self.calls))
    def carousel(self,children,caption):self.calls.append('carousel');return 'container'
    def status(self,key):return self.code
    def publish(self,key):
        self.calls.append('publish')
        if self.fail:raise OSError('lost response')
        return 'media'

class PublishingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.store=Store(self.root);self.box=self.store.outbox
        self.content={'sample':False,'valid_until':(now()+timedelta(hours=2)).isoformat(),'caption':'test'}
        with self.store.connect() as db:
            db.execute("INSERT INTO items(id,source_id,content,version,state,review,approval,created,verification) VALUES('item','source',?,'version','approved',1,'version',?,?)",(json.dumps(self.content),now().isoformat(),json.dumps({'status':'verified'})))
        # Boundary checks are real; source adapters and card hashing have their own integration tests.
        for name in ('valid_bundle','verify_content'):
            patcher=patch('src.publishing.'+name,return_value=True);patcher.start();self.addCleanup(patcher.stop)
        self.urls=['https://images.example/card-'+str(i)+'.jpg' for i in range(4)]
    def mutate(self,sql):
        with self.store.connect() as db:db.execute(sql)
    def test_jpeg_export_and_tampering(self):
        from PIL import Image
        base=self.root/'assets/images/generated/item/version';base.mkdir(parents=True)
        for i in range(1,5):Image.new('RGB',(1080,1350),'white').save(base/f'card-{i}.png')
        key=self.box.schedule('item','version');manifest=self.box.export(key)
        self.assertEqual(len(manifest['cards']),4)
        target=self.root/'data/runtime/publish-packages'/key/'card-1.jpg'
        with Image.open(target) as image:self.assertEqual(image.format,'JPEG');self.assertEqual(image.size,(1080,1350))
        target.write_bytes(b'tampered')
        with self.assertRaises(ValueError):self.box.export(key)

    def test_approval_and_sample_gate(self):
        self.mutate("UPDATE items SET approval=NULL")
        with self.assertRaises(ValueError):self.box.schedule('item','version')
        self.mutate("UPDATE items SET approval='version',content=json_set(content,'$.sample',json('true'))")
        with self.assertRaises(ValueError):self.box.schedule('item','version')
    def test_schedule_dedup_and_restart(self):
        keys=[self.box.schedule('item','version') for _ in range(2)]
        self.assertEqual(keys[0],keys[1]);self.assertEqual(len(Outbox(self.store).rows()),1)
    def test_concurrent_schedule_dedup(self):
        with ThreadPoolExecutor(2) as pool:keys=list(pool.map(lambda _:self.box.schedule('item','version'),range(2)))
        self.assertEqual(keys[0],keys[1]);self.assertEqual(len(self.box.rows()),1)
    def test_due_and_expiry(self):
        key=self.box.schedule('item','version',now()+timedelta(minutes=30));api=FakeAPI()
        self.box.step(key,api,self.urls);self.assertEqual(api.calls,[])
        with self.assertRaises(ValueError):self.box.schedule('item','version',now()+timedelta(days=1))
    def test_success_once_and_source_dedup(self):
        key=self.box.schedule('item','version');api=FakeAPI()
        for _ in range(10):self.box.step(key,api,self.urls)
        self.assertEqual(api.calls.count('image'),4);self.assertEqual(api.calls.count('publish'),1)
        self.assertEqual(self.box.rows()[0]['media_id'],'media')
        with self.assertRaises(ValueError):self.box.schedule('item','version')
    def test_uncertain_publish_is_never_repeated(self):
        key=self.box.schedule('item','version');api=FakeAPI();api.fail=True
        for _ in range(10):self.box.step(key,api,self.urls)
        self.assertEqual(api.calls.count('publish'),1);self.assertEqual(self.box.rows()[0]['state'],'uncertain')
    def test_interrupted_write_never_repeats(self):
        key=self.box.schedule('item','version');self.box.change(key,state='sending');api=FakeAPI()
        self.box.step(key,api,self.urls)
        self.assertEqual(api.calls,[]);self.assertEqual(self.box.rows()[0]['state'],'uncertain')
    def test_revocation_prevents_network(self):
        key=self.box.schedule('item','version');self.mutate("UPDATE items SET state='held',approval=NULL")
        api=FakeAPI();self.box.step(key,api,self.urls)
        self.assertEqual(api.calls,[]);self.assertEqual(self.box.rows()[0]['state'],'cancelled')
    def test_tamper_and_fact_failure_block(self):
        with patch('src.publishing.valid_bundle',return_value=False),self.assertRaises(ValueError):self.box.schedule('item','version')
        with patch('src.publishing.verify_content',side_effect=ValueError('changed')),self.assertRaises(ValueError):self.box.schedule('item','version')
    def test_global_review_on_blocks_ready(self):
        self.mutate("UPDATE items SET review=0,state='ready',approval=NULL")
        with self.assertRaises(ValueError):self.box.schedule('item','version')
        self.mutate('UPDATE settings SET review=0');self.box.schedule('item','version')
    def test_container_error_never_publishes(self):
        key=self.box.schedule('item','version');api=FakeAPI();api.code='ERROR'
        for _ in range(8):self.box.step(key,api,self.urls)
        self.assertNotIn('publish',api.calls);self.assertEqual(self.box.rows()[0]['state'],'failed')

class InstagramAdapterTests(unittest.TestCase):
    def test_carousel_request_contract_without_network(self):
        from src.instagram_api import InstagramAPI
        calls=[]
        def transport(method,path,values):
            calls.append((method,path,values))
            return {'id':'123','status_code':'FINISHED'}
        api=InstagramAPI('1234','v25.0','test-token','https://images.example',transport)
        self.assertEqual(api.image('https://images.example/1.jpg'),'123')
        api.carousel(['1','2','3','4'],'caption');api.status('123');api.publish('123')
        self.assertEqual(calls[1][2]['media_type'],'CAROUSEL')
        self.assertEqual(calls[3][1],'1234/media_publish')
        self.assertNotIn('test-token',repr(calls))
        with self.assertRaises(ValueError):api.image('https://other.example/1.jpg')
        with self.assertRaises(ValueError):api.image('https://images.example/1.png')

if __name__=='__main__':unittest.main()
