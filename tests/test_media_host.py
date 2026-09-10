import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from src.media_host import Cloudinary
from src.publish_worker import tick


class MediaHostTests(unittest.TestCase):
    def test_video_upload_and_wrong_media_path(self):
        raw=b'\x00\x00\x00\x20ftypisom';digest=hashlib.sha256(raw).hexdigest()
        def transport(method,url,body=None,headers=None):
            if method=='POST':
                self.assertTrue(url.endswith('/video/upload'))
                return json.dumps({'public_id':'auto-insta/'+digest,'version':1})
            return raw
        host=self.host(transport);url=host.upload(raw,'video')
        self.assertTrue(url.endswith('.mp4'))
        with self.assertRaises(ValueError):host.verify(url,digest)

    def test_reels_request_and_url_boundary(self):
        from src.instagram_api import InstagramAPI
        calls=[]
        def transport(method,path,values):calls.append(values);return {'id':'123'}
        api=InstagramAPI('123','v25.0','dummy','https://res.cloudinary.com',transport)
        self.assertEqual(api.reel('https://res.cloudinary.com/test/video.mp4','caption'),'123')
        self.assertEqual(calls[0]['media_type'],'REELS')
        with self.assertRaises(ValueError):api.reel('https://other.example/video.mp4','caption')

    def host(self,transport):
        return Cloudinary({'cloud_name':'test','api_key':'123','api_secret':'dummy'},transport)

    def test_free_budget_fail_closed(self):
        for data in ({}, {'plan':'Paid','credits':{'usage':0,'limit':25}},
                     {'plan':'Free','credits':{'usage':20,'limit':25}}):
            with self.assertRaises(ValueError):
                self.host(lambda *a,**k:json.dumps(data)).capacity()
        self.assertEqual(self.host(lambda *a,**k:json.dumps({'plan':'Free','credits':{'usage':1,'limit':25}})).capacity()['used'],1)

    def test_upload_and_delivery_binding(self):
        from urllib.parse import parse_qs
        raw=b'\xff\xd8test';digest=hashlib.sha256(raw).hexdigest();calls=[]
        def transport(method,url,body=None,headers=None):
            calls.append((method,url))
            if method=='POST':
                params=parse_qs(body.decode())
                self.assertEqual(params['overwrite'],['false'])
                self.assertNotIn('api_secret',params)
                self.assertEqual(params['public_id'],['auto-insta/'+digest])
                return json.dumps({'public_id':'auto-insta/'+digest,'version':1})
            return raw
        host=self.host(transport);url=host.upload(raw)
        self.assertEqual(len(calls),2)
        with self.assertRaises(ValueError):host.verify(url+'?transform=1',digest)
        with self.assertRaises(ValueError):self.host(lambda *a,**k:b'changed').verify(url,digest)

    def test_invalid_credentials(self):
        with self.assertRaises(ValueError):Cloudinary({'cloud_name':'test','api_key':123,'api_secret':'dummy'})

    def test_disabled_worker_never_loads_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'config').mkdir()
            (root/'config/publishing.json').write_text('{"enabled":false}')
            with patch('src.publish_worker.load_secret') as secret:
                tick(SimpleNamespace(root=root));secret.assert_not_called()
