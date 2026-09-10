import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from src.server import create_server

class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.server,self.store=create_server(Path(self.temp.name),0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.port=self.server.server_port

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()

    def request(self,method,path,body=None,headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.port)
        conn.request(method,path,body,headers or {})
        response=conn.getresponse();data=response.read();status=response.status;conn.close()
        return status,data

    def test_empty_state_and_path_boundary(self):
        status,data=self.request('GET','/api/state')
        self.assertEqual(status,200);self.assertEqual(json.loads(data)['items'],[])
        self.assertEqual(self.request('GET','/../PROJECT_STATUS.md')[0],404)
        self.assertEqual(self.request('GET','/api/state',headers={'Host':'evil.example'})[0],403)

    def test_settings_requires_same_origin_and_revision(self):
        body=json.dumps({'review':False,'revision':1})
        headers={'Content-Type':'application/json'}
        self.assertEqual(self.request('POST','/api/settings',body,headers)[0],403)
        headers['Origin']=f'http://127.0.0.1:{self.port}'
        self.assertEqual(self.request('POST','/api/settings',body,headers)[0],200)
        self.assertFalse(self.store.snapshot()['settings']['review'])
        self.assertEqual(self.request('POST','/api/settings',body,headers)[0],400)
        self.assertEqual(self.request('POST','/api/publish','{}',headers)[0],404)

    def test_operations_api_origin_revision_and_review_unchanged(self):
        from src.operations import DEFAULT
        body=json.dumps({'values':dict(DEFAULT,daily_food=0),'revision':1})
        headers={'Content-Type':'application/json'}
        self.assertEqual(self.request('POST','/api/operations',body,headers)[0],403)
        headers['Origin']=f'http://127.0.0.1:{self.port}'
        self.assertEqual(self.request('POST','/api/operations',body,headers)[0],200)
        self.assertEqual(self.request('POST','/api/operations',body,headers)[0],400)
        state=self.store.snapshot();self.assertTrue(state['settings']['review'])
        self.assertEqual(state['operations']['settings']['daily_food'],0)

if __name__=='__main__':unittest.main()
