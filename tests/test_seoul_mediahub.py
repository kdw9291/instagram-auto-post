import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime,timedelta
from src.collector import Collector,seoul_url
from src.editorial import EvidenceError,KST
from src.seoul_releases import make_release

URL='https://mediahub.seoul.go.kr/archives/2019741'
TITLE="가을밤 '반짝반짝 남산밤길' 걸어요! 700명 현장 접수"
KEY='seoul-mediahub-2019741'
BODY='남산 야간트래킹 ‘반짝반짝 남산밤길’\n○ 행사일시 : 2026년 10월 21일, 11월 21일 오후 7시~9시 (오후 6시부터 접수)\n○ 코스 : 남산골한옥마을→남산팔각정\n※ 집결지 : 남산골한옥마을 천우각\n○ 참여방법 : 사전 신청 없이 회당 현장 선착순 700명 접수\n중구 상생야장'

class SeoulMediahubTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.at=datetime(2026,10,19,10,tzinfo=KST);self.body=BODY;self.date='2026.10.19. 08:57'
        (self.root/'config').mkdir();(self.root/'config/sources.json').write_text(json.dumps({'sources':[{'id':KEY,'url':URL,'kind':'html','adapter':'seoul-release','headline':TITLE,'published':'2026-10-19T08:57:00+09:00'}]}))
    def collect(self):
        def transport(url):
            if url.endswith('/robots.txt'):return 'User-agent: *\nAllow: /'
            self.assertEqual(url,URL)
            return '<p>'+TITLE+'</p><p>내 손안에 서울</p><p>발행일</p><p>'+self.date+'</p><p>AI 요약</p><p>행사 무료, 500명이라는 잘못된 요약</p><p>'+self.body+'</p>'
        with patch('src.collector.utcnow',return_value=self.at):return Collector(self.root,transport).run(True)
    def test_official_overview_not_ai_summary(self):
        self.collect();c,r=make_release(self.root,KEY,self.at)
        for value in ('10/21','11/21','19:00–21:00','18:00','700명','남산골한옥마을 천우각'):self.assertIn(value,c['caption'])
        self.assertNotIn('무료',c['caption']);self.assertEqual(len(r['claims']),6)
    def test_invalid_body_or_publication_blocks(self):
        for body in (BODY+BODY,BODY.replace('700명 접수','700명 추후 안내'),BODY.replace('오후 6시','오후 10시'),BODY.replace('10월 21일','13월 21일')):
            self.body=body;self.collect()
            with self.assertRaises(EvidenceError):make_release(self.root,KEY,self.at)
        self.body=BODY;self.date='2026.10.18. 08:57';self.collect()
        with self.assertRaises(EvidenceError):make_release(self.root,KEY,self.at)
    def test_expired_news_and_url_boundaries(self):
        self.collect()
        with self.assertRaises(EvidenceError):make_release(self.root,KEY,self.at+timedelta(days=8))
        for bad in (URL+'?x=1',URL+'#x',URL.replace('https:','http:'),URL.replace('mediahub.seoul.go.kr','mediahub.seoul.go.kr.evil.test')):
            with self.assertRaises(ValueError):seoul_url(bad)

    def test_previous_unsupported_press_receipt_is_not_requeued(self):
        from src.collector import retained_official_sources
        bad={'id':'seoul-press-468296','url':'https://www.seoul.go.kr/news/news_report.do?nttNo=468296&srchCtgry=466','adapter':'seoul-release','published':self.at.isoformat(),'category':'place'}
        self.assertEqual(retained_official_sources(self.root,[],{'sources':[bad]},self.at),[])

if __name__=='__main__':unittest.main()
