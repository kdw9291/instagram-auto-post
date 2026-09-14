import hashlib
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from src.collector import shinsegae_url
from src.editorial import EvidenceError, KST
from src.seoul_weekly import URLS as SEOUL_URLS, make_weekly
from src.shinsegae_releases import make_release


class FixtureMixin:
    def write_sources(self,entries):
        out=self.root/'data/runtime/collection';out.mkdir(parents=True,exist_ok=True);report={'sources':[]}
        for entry,text in entries:
            source={'url':entry['url'],'checked_at':self.at.isoformat(),'text':text,'tables':[]}
            raw=json.dumps(source,ensure_ascii=False,sort_keys=True).encode();h=hashlib.sha256(raw).hexdigest()
            (out/f"{entry['id']}-{h}.json").write_bytes(raw)
            report['sources'].append(dict(entry,status='ok',checked_at=self.at.isoformat(),snapshot_hash=h))
        (out/'report.json').write_text(json.dumps(report,ensure_ascii=False),encoding='utf-8')


class ShinsegaeTests(unittest.TestCase,FixtureMixin):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.at=datetime(2026,9,14,12,tzinfo=KST)

    def item(self,url,title,category,body):
        key='ssg-news-'+hashlib.sha256(url.encode()).hexdigest()[:16]
        entry={'id':key,'url':url,'adapter':'shinsegae-release','headline':title,'category':category,'published':datetime(2026,9,14,tzinfo=KST).isoformat()}
        self.write_sources([(entry,title+'\n도구 보기\n'+body+'\n보도자료 다운로드')]);return key

    def test_tenmonths_popup(self):
        url='https://www.shinsegaegroupnewsroom.com/shinsegae-international-popup-service/'
        key=self.item(url,'텐먼스, 성수에 팝업 열고 스타일링 서비스 운영','place','텐먼스는 오는 10월 11일까지 서울 성수동에서 첫 팝업스토어를 연다. 당신만의 텐먼스 – 1:1 스타일링 클래스는 1:1 예약제로 운영한다. 충분한 공식 본문 설명입니다.')
        c,r=make_release(self.root,key,self.at)
        self.assertIn('텐먼스 성수',c['title']);self.assertEqual(c['category'],'place')
        self.assertEqual(len(r['claims']),4)

    def test_body_not_ai_summary_and_url_mapping(self):
        media='https://www.shinsegaegroupnewsroom.com/diptyque-les-rituels-de-soin-seongsu-popup-3/'
        self.assertEqual(shinsegae_url(media),'https://www.shinsegaegroupnewsroom.com/diptyque-les-rituels-de-soin-seongsu-popup/')
        bad='텐먼스는 오는 10월 11일까지 서울 성수동에서 첫 팝업스토어. 당신만의 텐먼스 – 1:1 스타일링 클래스 사전예약\n도구 보기\n본문에는 일정이 없습니다. 본문 설명만 길게 채워 두어 요약이 근거가 되지 않게 검사합니다.'
        url='https://www.shinsegaegroupnewsroom.com/shinsegae-international-popup-service/'
        key=self.item(url,'텐먼스, 성수에 팝업 열고 스타일링 서비스 운영','place',bad.split('도구 보기\n',1)[1])
        with self.assertRaises(EvidenceError):make_release(self.root,key,self.at)

    def test_diptyque_and_starbucks_selected_articles(self):
        dip='https://www.shinsegaegroupnewsroom.com/diptyque-les-rituels-de-soin-seongsu-popup/'
        dip_body='신제품 출시를 기념해 오는 12일부터 16일까지 성수 팝업을 운영한다. 레 리츄엘 드 수앙 컬렉션을 소개한다. [딥티크 정보] - 일자: 9월 12일~16일 - 운영시간: 오전 11시-오후 8시(16일은 오후 7시 종료) - 장소: 서울특별시 성동구 성수이로18길 8. 공식 행사 본문입니다.'
        key=self.item(dip,'딥티크, 웰빙 바디 컬렉션 출시 및 성수 팝업스토어 운영','place',dip_body)
        c,_=make_release(self.root,key,self.at);self.assertIn('딥티크 성수',c['title'])
        star='https://www.shinsegaegroupnewsroom.com/autumn-starbucks-launch-sweetpotato/'
        key=self.item(star,'스타벅스, ‘카스텔라 고구마 라떼’ 출시','food','스타벅스 코리아가 카스텔라 고구마 라떼를 오는 15일부터 전국 스타벅스 매장에서 선보인다. 가을 신제품을 소개하는 공식 발표 본문이며 판매 여부는 매장에서 확인한다.')
        c,_=make_release(self.root,key,self.at);self.assertIn('카스텔라 고구마 라떼',c['title'])


class SeoulWeeklyTests(unittest.TestCase,FixtureMixin):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.at=datetime(2026,9,14,12,tzinfo=KST)
        texts={
          'seoul-calendar-202609':'서울안전한마당 9.17~9.19 여의도공원 / 파크 콘서트 9.19 서울어린이대공원 무료',
          'seoul-safety-202609':'AI 요약\n2026년 서울안전한마당\n2026. 9. 17.(목) ~ 9. 19.(토) 10:00~17:00 여의도공원 문화의 마당 6개 분야 70개 프로그램을 운영합니다. 시민이 참여할 수 있는 안전 행사 상세 본문입니다.',
          'seoul-market-202609':'안내\n수정일\n2026-09-11\n9.15.(화)~9.17.(목) 10:00~19:00 서울광장 일대에서 운영합니다. 지역 농수특산물을 만나는 공식 행사 상세 본문입니다.\n2026 추석맞이 서로장터\n2026 추석맞이 서로장터\n태그',
          'seoul-phil-202609':'2026.9.19. 토요일 19:00 서울어린이대공원 숲속의무대 관람료 무료 별도 신청 없이 관람 약 1시간 30분',
        }
        entries=[]
        for key,url in SEOUL_URLS.items():entries.append(({'id':key,'url':url,'adapter':'seoul-weekly'},texts[key]))
        self.entries=entries;self.write_sources(entries)

    def test_weekly_bundle_uses_three_verified_events(self):
        c,r=make_weekly(self.root,self.at)
        self.assertEqual(len(c['facts']),3);self.assertIn('행사 3',c['title'])
        self.assertIn('요일 표기',c['conditions']);self.assertEqual(len(r['claims']),5)

    def test_missing_body_fact_and_expiry_block(self):
        changed=[]
        for e,t in self.entries:changed.append((e,t.replace('70개','여러') if e['id']=='seoul-safety-202609' else t))
        self.write_sources(changed)
        with self.assertRaises(EvidenceError):make_weekly(self.root,self.at)
        self.write_sources(self.entries)
        with self.assertRaises(EvidenceError):make_weekly(self.root,datetime(2026,9,17,19,tzinfo=KST))


if __name__=='__main__':unittest.main()
