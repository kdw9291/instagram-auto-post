import unittest
from datetime import datetime
from src.seoul_events import extract, URLS
from src.editorial import EvidenceError, KST

class SeoulEventTests(unittest.TestCase):
    def setUp(self):
        self.at=datetime(2026,9,11,tzinfo=KST)
        texts=['AI 요약\n하반기 행사 개요\n9.12.(토) 20:30~20:45 뚝섬한강공원 수변무대 현장 방문(무료 공연) 기상 취소 19:30~21:25',
               'AI 요약\n지난 공연들의 뜨거운 열기를 이어 2026. 9. 12.(토) 20:30 - 20:45 뚝섬한강공원 수변무대 K-야구, 서울 나잇 기상 취소 19:00~21:15']
        self.sources={k:dict(text=t,url=u,hash='a'*64) for (k,u),t in zip(URLS.items(),texts)}
    def test_common_facts_only(self):
        claims,end=extract(self.sources,self.at)
        self.assertEqual(len(claims),9)
        self.assertEqual(end.hour,20)
        self.assertFalse(any('19:' in str(c['value']) for c in claims))
    def test_changed_show_is_blocked(self):
        self.sources['seoul-event-534306']['text']=self.sources['seoul-event-534306']['text'].replace('20:30','21:30')
        with self.assertRaises(EvidenceError):extract(self.sources,self.at)
    def test_ai_summary_cannot_supply_missing_fact(self):
        key='seoul-event-534345'
        self.sources[key]['text']='현장 방문(무료 공연)\n'+self.sources[key]['text'].replace('현장 방문(무료 공연)','')
        with self.assertRaises(EvidenceError):extract(self.sources,self.at)
    def test_finished_event_is_blocked(self):
        with self.assertRaises(EvidenceError):extract(self.sources,datetime(2026,9,12,20,45,tzinfo=KST))
