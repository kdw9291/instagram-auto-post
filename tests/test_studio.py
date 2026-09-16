import json,tempfile,unittest
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch
from src.store import Store,now
from src.studio import Studio
from src.server import create_server

class StudioTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.store=Store(self.root);self.studio=Studio(self.store)
        content={'sample':False,'caption':'test','valid_until':(now()+timedelta(hours=1)).isoformat()}
        with self.store.connect() as db:
            db.execute("INSERT INTO items(id,source_id,content,version,state,review,created) VALUES('item','source',?,'version','waiting',1,?)",(json.dumps(content),now().isoformat()))
        for name,value in [('valid_bundle',True),('verify_content',True),('reel_info',{'sha256':'video'})]:
            p=patch('src.studio.'+name,return_value=value);p.start();self.addCleanup(p.stop)
    def test_no_work_on_open(self):
        with patch('src.collector.Collector.run') as collect,patch('src.store.Store.produce') as produce:
            server,_=create_server(self.root,0);server.server_close()
            collect.assert_not_called();produce.assert_not_called()
    def test_selected_formats_only(self):
        with patch.object(self.studio,'start',side_effect=lambda fn:fn()),patch.object(self.store,'action') as approve,patch.object(self.studio,'publish') as publish:
            self.studio.request_publish('item','version',['reel'],'video')
            self.assertEqual([c.args[1] for c in publish.call_args_list],['reel'])
            approve.assert_called_once_with('item','version','approve')
            self.assertEqual([r['kind'] for r in self.studio.posts()],['reel'])
    def test_changed_video_and_version_rejected(self):
        for version,sha in [('other','video'),('version','other'),('version',None)]:
            with self.assertRaises(ValueError):self.studio.request_publish('item',version,['reel'],sha)
        self.assertEqual(self.studio.posts(),[])
    def test_duplicate_and_restart_never_resend(self):
        with self.store.connect() as db:db.execute("INSERT INTO studio_posts(source_id,kind,state) VALUES('source','reel','processing')")
        studio=Studio(self.store)
        self.assertEqual(studio.posts()[0]['state'],'interrupted')
        with self.assertRaises(ValueError):studio.request_publish('item','version',['reel'],'video')
    def test_both_records_survive_failure(self):
        def publish(item,kind,sha):
            if kind=='cards':self.studio.change('source',kind,state='published',media_id='done')
            else:raise OSError('response lost')
        with patch.object(self.studio,'start',side_effect=lambda fn:fn()),patch.object(self.store,'action'),patch.object(self.studio,'publish',side_effect=publish):
            with self.assertRaises(OSError):self.studio.request_publish('item','version',['cards','reel'],'video')
        self.assertEqual({r['kind']:r['state'] for r in self.studio.posts()},{'cards':'published','reel':'interrupted'})
        with self.store.connect() as db:self.assertEqual(db.execute("SELECT state FROM items WHERE source_id='source'").fetchone()[0],'published')

    def test_published_item_is_synced_and_can_publish_missing_format(self):
        with self.store.connect() as db:db.execute("INSERT INTO studio_posts(source_id,kind,item_id,version,state) VALUES('source','cards','item','version','published')")
        studio=Studio(self.store)
        with self.store.connect() as db:self.assertEqual(db.execute("SELECT state FROM items WHERE id='item'").fetchone()[0],'published')
        with patch.object(studio,'start',side_effect=lambda fn:fn()),patch.object(self.store,'action') as approve,patch.object(studio,'publish') as publish:
            studio.request_publish('item','version',['reel'],'video')
        approve.assert_not_called();publish.assert_called_once()

if __name__=='__main__':unittest.main()
