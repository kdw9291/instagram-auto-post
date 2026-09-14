import unittest,tempfile,json,hashlib,io
from pathlib import Path
from datetime import datetime,timedelta,timezone
from PIL import Image
from src.provided_images import select,attach_provided
class ProvidedTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        (self.root/'config').mkdir();(self.root/'data/rights').mkdir(parents=True)
        proof=b'fixture permission';(self.root/'data/rights/proof.txt').write_bytes(proof)
        buf=io.BytesIO();Image.new('RGB',(800,1000)).save(buf,format='PNG');self.raw=buf.getvalue()
        self.c={'source_id':'news','sources':['https://example.com/news'],'caption':'본문\n배경은 AI 콘셉트입니다.\n출처','conditions':'안내'}
        self.e={'source_id':'news','source_url':self.c['sources'][0],'status':'allowed','subject_verified':True,'permissions':{k:True for k in ('commercial','social','edit','video','hosting')},'valid_until':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),'credit':'Example','rights_url':'https://example.com/license','rights_text':'fixture permission','checked_at':datetime.now(timezone.utc).isoformat(),'image_sha256':hashlib.sha256(self.raw).hexdigest(),'evidence_file':'proof.txt','evidence_sha256':hashlib.sha256(proof).hexdigest(),'image_url':'https://example.com/image.png'}
        self.save()
    def save(self): (self.root/'config/media-rights.json').write_text(json.dumps({'mode':'rights_verified_first','assets':[self.e]}))
    def test_acquire_and_offline_verify(self):
        a=select(self.root,self.c,True,lambda u:self.raw);self.assertEqual(a['kind'],'provided')
        self.assertEqual(select(self.root,self.c),a)
        c=attach_provided(self.c,a);self.assertIn('사진 제공: Example',c['caption']);self.assertNotIn('배경은 AI 콘셉트',c['caption'])
    def test_unknown_and_denied_no_download(self):
        for status in ('unknown','denied'):
            self.e['status']=status;self.save();self.assertIsNone(select(self.root,self.c,True,lambda u:self.fail('download')))
    def test_expiry_revokes(self):
        select(self.root,self.c,True,lambda u:self.raw)
        self.e['valid_until']='2000-01-01T00:00:00+00:00';self.save();self.assertIsNone(select(self.root,self.c))
    def test_tampered_evidence_and_media(self):
        self.assertIsNone(select(self.root,self.c,True,lambda u:b'wrong'))
        (self.root/'data/rights/proof.txt').write_text('changed');self.assertIsNone(select(self.root,self.c,True,lambda u:self.fail('download')))
    def test_missing_edit_permission(self):
        self.e['permissions']['edit']=False;self.save();self.assertIsNone(select(self.root,self.c,True,lambda u:self.fail('download')))
    def test_policy_change_changes_approval_asset(self):
        a=select(self.root,self.c,True,lambda u:self.raw);self.e['credit']='New';self.save();b=select(self.root,self.c);self.assertNotEqual(a['rights_hash'],b['rights_hash'])
if __name__=='__main__':unittest.main()
