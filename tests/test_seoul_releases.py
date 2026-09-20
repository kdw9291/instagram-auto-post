import hashlib
import json
import tempfile
import unittest
from datetime import datetime
from email.utils import format_datetime
from pathlib import Path

from src.collector import seoul_index, seoul_sources, seoul_url
from src.editorial import EvidenceError, KST
from src.seoul_releases import make_release


class SeoulReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.at=datetime(2026,9,16,12,tzinfo=KST)
        self.url='https://news.seoul.go.kr/culture/archives/534430';self.key='seoul-culture-534430'

    def write_source(self,text,title='2026 서울로미디어캔버스 세 번째 전시',article_id='534430',published=None):
        self.url=f'https://news.seoul.go.kr/culture/archives/{article_id}';self.key=f'seoul-culture-{article_id}'
        out=self.root/'data/runtime/collection';out.mkdir(parents=True)
        source={'url':self.url,'checked_at':self.at.isoformat(),'text':text,'tables':[],'fields':{}}
        raw=json.dumps(source,ensure_ascii=False,sort_keys=True).encode();digest=hashlib.sha256(raw).hexdigest()
        (out/f'{self.key}-{digest}.json').write_bytes(raw)
        entry={'id':self.key,'url':self.url,'kind':'html','adapter':'seoul-release','headline':title,'published':(published or datetime(2026,9,15,15,50,tzinfo=KST)).isoformat(),'status':'ok','checked_at':self.at.isoformat(),'snapshot_hash':digest}
        (out/'report.json').write_text(json.dumps({'sources':[entry]},ensure_ascii=False),encoding='utf-8')

    def test_dynamic_source_and_strict_url(self):
        report=[{'id':'seoul-culture-home','status':'ok','url':'https://news.seoul.go.kr/culture','checked_at':self.at.isoformat(),'candidates':[{'title':'2026 서울로미디어캔버스 세 번째 전시','url':self.url,'category':'place','published_at':format_datetime(datetime(2026,9,15,15,50,tzinfo=KST))}]}]
        result=seoul_sources(report,self.at)
        self.assertEqual(result[0]['id'],self.key);self.assertEqual(result[0]['adapter'],'seoul-release')
        for bad in ('http://news.seoul.go.kr/culture/archives/1','https://news.seoul.go.kr/safe/archives/1','https://news.seoul.go.kr/culture/archives/1?x=1'):
            with self.assertRaises(ValueError):seoul_url(bad)

    def test_media_canvas_article(self):
        self.write_source('2026 서울로미디어캔버스 세 번째 전시\n수정일 2026-09-15\n전시 기간 : 2026년 9월 21일~2026년 11월 30일 (운영시간은 조정 될 수 있습니다.)\n전시 시간 : 19시~23시\n전시 작품 : 신진예술가 지원공모전 20작품, 네이처 프로젝트전 4작품 (총24점)')
        content,receipt=make_release(self.root,self.key,self.at)
        self.assertIn('미디어아트',content['title']);self.assertIn('총 24점',content['caption']);self.assertEqual(len(receipt['claims']),5)

    def test_work_count_mismatch_is_blocked(self):
        self.write_source('2026 서울로미디어캔버스 세 번째 전시\n전시 기간 : 2026년 9월 21일~2026년 11월 30일\n전시 시간 : 19시~23시\n전시 작품 : 신진예술가 지원공모전 20작품, 네이처 프로젝트전 4작품 (총25점)')
        with self.assertRaises(EvidenceError):make_release(self.root,self.key,self.at)

    def test_culture_home_extracts_dated_event_cards(self):
        raw='''<a href="https://news.seoul.go.kr/culture/archives/534453"><strong class="tit">서울생활사박물관, 한가위 문화행사</strong><em class="txt">설명</em><em class="date">2026-09-17</em></a>
        <li><a href="https://news.seoul.go.kr/culture/archives/534430"><span class="title-ellipsis">2026 서울로미디어캔버스 세 번째 전시</span><span class="date"><em>등록일:</em>2026-09-15</span></a></li>'''
        result=seoul_index(raw,'https://news.seoul.go.kr/culture')
        self.assertEqual([c['url'].rsplit('/',1)[1] for c in result['candidates']],['534453','534430'])
        self.assertTrue(all(c['status']=='discovered' for c in result['candidates']))

    def test_labelled_free_holiday_event(self):
        self.at=datetime(2026,9,20,12,tzinfo=KST)
        title="서울생활사박물관, 한가위 '문화가 흐르는 박물관' 개최(2026.9.26.토)"
        text=title+'\nAI 요약\n요약은 근거가 아닙니다.\n한가위를 맞이해 서울생활사박물관에서 문화행사 <한가위, 문화가 흐르는 박물관>을 개최합니다.\n일 시:\n2026년 9월 26일(토) 13시~17시\n장 소:\n서울생활사박물관 일대(실내외)\n참여방법:\n현장참여(선착순), 무료\nAI생성태그'
        self.write_source(text,title,'534453',datetime(2026,9,17,tzinfo=KST))
        content,receipt=make_release(self.root,self.key,self.at)
        self.assertIn('무료 박물관 행사',content['title']);self.assertIn('13:00–17:00',content['caption'])
        self.assertEqual(len(receipt['claims']),6);self.assertIn('실제 행사 현장',content['caption'])


if __name__=='__main__':unittest.main()
