import unittest
from unittest.mock import patch
from datetime import datetime,timezone
from src.collector import rss_data,classify
class ExpandedSourcesTests(unittest.TestCase):
    def test_seoul_local_date_and_duplicate(self):
        item='<item><title>한강 드론라이트쇼 안내</title><link>https://news.seoul.go.kr/culture/archives/1</link><pubDate>2026-09-08 10:50:17</pubDate></item>'
        with patch('src.collector.utcnow',return_value=datetime(2026,9,11,tzinfo=timezone.utc)):
            result=rss_data('<rss><channel>'+item+item.replace('archives/1','archives/2')+'</channel></rss>','https://news.seoul.go.kr/culture/feed')
        self.assertEqual(len(result['candidates']),1);self.assertIn('+0900',result['candidates'][0]['published_at'])
    def test_other_retailers(self):
        for title in ('GS25 신제품 김밥 출시','이마트 신상 도시락 출시','세븐일레븐 신제품 과자 출시'):self.assertEqual(classify(title),'food')
    def test_gifts_remain_excluded(self):
        self.assertIsNone(classify('뷰티 선물 세트 출시'))
        self.assertIsNone(classify('설화수 기획 세트 출시'))
