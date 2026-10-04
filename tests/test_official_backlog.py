import json
import sqlite3
import tempfile
import unittest
import hashlib
from contextlib import closing
from datetime import timedelta
from pathlib import Path
from email.utils import format_datetime
from src.collector import Collector,utcnow
from src.discovery import sync


class OfficialBacklogTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);(self.root/'config').mkdir()
        self.feed='https://www.shinsegaegroupnewsroom.com/feed/'
        self.url='https://www.shinsegaegroupnewsroom.com/fresh-autumn-popup-3/'
        self.article=self.url.replace('-3/','/')
        self.key='ssg-news-'+hashlib.sha256(self.article.encode()).hexdigest()[:16]
        (self.root/'config/sources.json').write_text(json.dumps({'sources':[{'id':'shinsegae-rss','name':'공식 RSS','url':self.feed,'kind':'rss'}]}))
        self.calls=[]
        self.remember()

    def remember(self,age=3,url=None):
        at=utcnow()
        sync(self.root,{'sources':[{'id':'shinsegae-rss','status':'ok','url':self.feed,'checked_at':at.isoformat(),'candidates':[{'title':'새 가을 팝업 소식','url':url or self.url,'category':'place','published_at':format_datetime(at-timedelta(days=age))}]}]},at)

    def transport(self,url):
        self.calls.append(url)
        if url.endswith('/robots.txt'):return 'User-agent: *\nAllow: /'
        if url==self.feed:return '<rss><channel><title>최신 10개 글에는 이전 팝업이 없음</title></channel></rss>'
        if url==self.article:return '<h1>새 가을 팝업 소식</h1><p>공식 기사 본문입니다. 일정과 장소를 본문에서 다시 검증합니다.</p>'
        raise AssertionError('unexpected URL '+url)

    def test_candidate_survives_feed_rollover_and_cached_next_run(self):
        collector=Collector(self.root,self.transport)
        report=collector.run(True)
        self.assertIn(self.article,self.calls)
        source=next(s for s in report['sources'] if s['id']==self.key)
        self.assertEqual(source['adapter'],'shinsegae-release')
        self.assertLess(source['published'],source['checked_at'])
        collector.run();self.assertEqual(self.calls.count(self.article),1)

    def test_expired_and_untrusted_urls_are_not_replayed(self):
        self.remember(age=8);self.remember(url='https://evil.example/fresh-autumn-popup-3/')
        report=Collector(self.root,self.transport).run(True)
        self.assertNotIn(self.article,self.calls)
        self.assertEqual(len(report['sources']),1)

    def test_published_candidate_is_not_fetched_again(self):
        with closing(sqlite3.connect(self.root/'data/runtime/queue.sqlite3')) as db:
            with db:
                db.execute('CREATE TABLE items(source_id TEXT,state TEXT)')
                db.execute("INSERT INTO items VALUES(?,'published')",(self.key,))
        report=Collector(self.root,self.transport).run(True)
        self.assertNotIn(self.article,self.calls)
        self.assertEqual(len(report['sources']),1)

    def test_published_source_keeps_frozen_receipt_without_refresh(self):
        collector=Collector(self.root,self.transport);first=collector.run(True)
        original=next(s for s in first['sources'] if s['id']==self.key)
        with closing(sqlite3.connect(self.root/'data/runtime/queue.sqlite3')) as db:
            with db:
                db.execute('CREATE TABLE items(source_id TEXT,state TEXT)')
                db.execute("INSERT INTO items VALUES(?,'published')",(self.key,))
        second=collector.run(True)
        frozen=next(s for s in second['sources'] if s['id']==self.key)
        self.assertEqual(frozen,original)
        self.assertEqual(self.calls.count(self.article),1)
