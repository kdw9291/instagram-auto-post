import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
from concurrent.futures import ThreadPoolExecutor
from src.operations import admit,settings,update,DEFAULT,snapshot,connection,generation_allowed
from src.store import Store

class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);Store(self.root)
        self.at=datetime.now(timezone.utc)
    def content(self,key,category='food',at=None):
        return {'source_id':key,'category':category,'title':key,'valid_until':((at or self.at)+timedelta(hours=12)).isoformat()}
    def save(self,**kw):update(self.root,dict(DEFAULT,**kw),settings(self.root)['revision'])
    def test_revision_validation_and_persistence(self):
        self.save(daily_food=0)
        self.assertEqual(settings(self.root)['daily_food'],0)
        with self.assertRaises(ValueError):update(self.root,DEFAULT,1)
        with self.assertRaises(ValueError):self.save(daily_food=True)
        with self.assertRaises(ValueError):self.save(max_pending=0)
        self.assertFalse(admit(self.root,self.content('one'),{},self.at))
    def test_daily_counts_reservations_once_and_kst_reset(self):
        at=datetime(2026,9,9,14,59,tzinfo=timezone.utc)
        self.assertTrue(admit(self.root,self.content('one',at=at),{},at))
        self.assertTrue(admit(self.root,self.content('one',at=at),{},at))
        self.assertFalse(admit(self.root,self.content('two',at=at),{},at))
        self.assertTrue(admit(self.root,self.content('two',at=at),{},at+timedelta(minutes=2)))
    def test_shared_backlog_and_expired_reservation(self):
        self.save(max_pending=1)
        self.assertTrue(admit(self.root,self.content('one'),{},self.at))
        self.assertFalse(admit(self.root,self.content('two','beauty'),{},self.at))
        later=self.at+timedelta(days=1)
        self.assertTrue(admit(self.root,self.content('two','beauty',later),{},later))
    def test_cross_url_exact_product_duplicate_and_disable(self):
        self.save(daily_food=3)
        receipt={'claims':[{'field':'product','value':'초코 쿠키'}]}
        self.assertTrue(admit(self.root,self.content('one'),receipt,self.at))
        self.assertFalse(admit(self.root,self.content('two'),receipt,self.at))
        self.save(daily_food=3,duplicate_days=0)
        self.assertTrue(admit(self.root,self.content('two'),receipt,self.at))
    def test_concurrent_workers_cannot_oversubscribe(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda k:admit(self.root,self.content(k),{},self.at),['one','two']))
        self.assertEqual(sum(results),1)
    def test_expired_reservation_stops_generation(self):
        admit(self.root,self.content('one'),{},self.at)
        with connection(self.root) as db:
            with db:db.execute('UPDATE admissions SET until=?',((self.at-timedelta(seconds=1)).isoformat(),))
        self.assertFalse(generation_allowed(self.root,'one'))
    def test_lowering_limits_preserves_started_work_and_review(self):
        admit(self.root,self.content('one'),{},self.at);self.save(daily_food=0)
        self.assertTrue(admit(self.root,self.content('one'),{},self.at))
        self.assertTrue(Store(self.root).snapshot()['settings']['review'])
        self.assertEqual(snapshot(self.root)['pending'],1)

if __name__=='__main__':unittest.main()
