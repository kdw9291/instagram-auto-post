import io
import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from PIL import Image
from src.news_images import brief, attach, tick, rows, ImagePending
from src.discovery import sync

class NewsImageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/'config').mkdir()
        (self.root/'config/images.json').write_text(json.dumps({'required':True,'provider':'comfyui-local','checkpoint':'model.safetensors'}))
        self.content={'source_id':'news-1','sample':False,'title':'새 뉴스','intro':'원문 요약','facts':[{'label':'가격','value':'1000원'}],'image_subject':'A bakery counter with twisted bread'}

    def queue(self):
        with self.assertRaises(ImagePending):attach(self.root,self.content,enqueue=True)

    def test_one_image_per_news_not_per_poll(self):
        self.queue();self.queue();self.assertEqual(len(rows(self.root)),1)
        changed=dict(self.content,verified_at='tomorrow')
        self.assertEqual(brief(changed)[0],brief(self.content)[0])
        self.assertNotEqual(brief(dict(self.content,title='다른 뉴스'))[0],brief(self.content)[0])
        self.assertNotEqual(brief(self.content,{'checkpoint':'a'})[0],brief(self.content,{'checkpoint':'b'})[0])

    def test_generate_attach_and_tamper_blocks(self):
        self.queue();calls=[];data=io.BytesIO();Image.new('RGB',(832,1088),'gray').save(data,format='PNG')
        def transport(path,body=None,binary=False):
            calls.append(path)
            if path.startswith('/object_info'):return {'CheckpointLoaderSimple':{'input':{'required':{'ckpt_name':[['model.safetensors']]}}}}
            if path=='/prompt':return {'prompt_id':'job-1'}
            if path.startswith('/history'):return {'job-1':{'status':{'completed':True},'outputs':{'7':{'images':[{'filename':'one.png','subfolder':'','type':'output'}]}}}}
            return data.getvalue()
        tick(self.root,transport);tick(self.root,transport);tick(self.root,transport)
        content=attach(self.root,self.content);self.assertEqual(calls.count('/prompt'),1)
        image=self.root/'assets/images/news'/f"{content['news_image']['id']}.png";image.write_bytes(b'tampered')
        with self.assertRaises(ImagePending):attach(self.root,self.content)

    def test_blank_image_is_failed_and_retry_changes_seed(self):
        from src.news_images import connect
        self.queue();calls=[];data=io.BytesIO();Image.new('RGB',(832,1088),'black').save(data,format='PNG')
        def transport(path,body=None,binary=False):
            if path.startswith('/object_info'):return {'CheckpointLoaderSimple':{'input':{'required':{'ckpt_name':[['model.safetensors']]}}}}
            if path=='/prompt':calls.append(body['prompt']['5']['inputs']['seed']);return {'prompt_id':'job-'+str(len(calls))}
            if path.startswith('/history'):return {f'job-{len(calls)}':{'status':{'completed':True},'outputs':{'7':{'images':[{'filename':'blank.png','subfolder':'','type':'output'}]}}}}
            return data.getvalue()
        tick(self.root,transport);tick(self.root,transport);tick(self.root,transport)
        self.assertEqual(rows(self.root)[0]['state'],'failed')
        db=connect(self.root)
        with db:db.execute('UPDATE jobs SET next_try=1')
        db.close();tick(self.root,transport);tick(self.root,transport);tick(self.root,transport)
        self.assertEqual(len(calls),2);self.assertNotEqual(calls[0],calls[1])

    def test_uncertain_submit_is_not_repeated(self):
        self.queue();calls=[]
        def transport(path,body=None,binary=False):
            calls.append(path)
            if path.startswith('/object_info'):return {'CheckpointLoaderSimple':{'input':{'required':{'ckpt_name':[['model.safetensors']]}}}}
            raise OSError('lost response')
        tick(self.root,transport);tick(self.root,transport)
        self.assertEqual(calls.count('/prompt'),1);self.assertEqual(rows(self.root)[0]['state'],'uncertain')

    def test_missing_model_never_uses_shared_background(self):
        self.queue()
        tick(self.root,lambda *a,**k:{'CheckpointLoaderSimple':{'input':{'required':{'ckpt_name':[[]]}}}})
        with self.assertRaises(ImagePending):attach(self.root,self.content)

    def test_confirmed_failure_retries_with_limit_but_not_uncertain(self):
        from src.news_images import connect
        from src.operations import update, DEFAULT
        update(self.root,dict(DEFAULT,retry_limit=1),1)
        self.queue();calls=[]
        def transport(path,body=None,binary=False):
            calls.append(path)
            if path.startswith('/object_info'):return {'CheckpointLoaderSimple':{'input':{'required':{'ckpt_name':[['model.safetensors']]}}}}
            if path=='/prompt':return {'prompt_id':'job-1'}
            if path.startswith('/history'):return {'job-1':{'status':{'completed':True,'status_str':'error'}}}
            raise AssertionError(path)
        tick(self.root,transport);tick(self.root,transport)
        for _ in range(2):
            db=connect(self.root)
            with db:db.execute('UPDATE jobs SET next_try=1')
            db.close();tick(self.root,transport);tick(self.root,transport)
        self.assertEqual(calls.count('/prompt'),2)
        self.assertEqual(rows(self.root)[0]['state'],'failed')

    def test_discovery_deduplication_and_expiry(self):
        at=datetime.now(timezone.utc);title=f'보도자료 {at:%y.%m.%d} 편의점 신상'
        c={'title':title,'url':'https://example.com/item?id=1&utm_source=rss','category':'food'}
        report={'sources':[{'id':'rss','status':'ok','checked_at':at.isoformat(),'candidates':[c,dict(c,url='https://example.com/item?id=1')]}]}
        result=sync(self.root,report,at);self.assertEqual(len(result),1);self.assertEqual(result[0]['state'],'discovered')
        result=sync(self.root,{'sources':[]},at+timedelta(days=8));self.assertEqual(result[0]['state'],'expired')

if __name__=='__main__':unittest.main()
