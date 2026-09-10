import json
import tempfile
import unittest
from pathlib import Path
from datetime import timedelta
from email.utils import format_datetime
from src.collector import Collector,fetch_allowed,page_data,rss_data,compare,utcnow
from src.backgrounds import topic_for

URL='https://www.hankyung.com/feed/life'

class CollectionTests(unittest.TestCase):
    def test_nested_tables_do_not_crash_or_supply_price_evidence(self):
        result=page_data('<table><tr><td>대상<table><tr><td>가격</td></tr></table></td></tr></table>',URL)
        self.assertEqual(result['tables'],[])

    def test_price_scopes_exclude_recommendation_prices(self):
        result=page_data('<p>추천상품 90,000원</p><div class="priceInfo__inner-item origin"><em>10%</em><span>40,000원</span></div><div class="priceInfo__inner-item discount">36,000원</div>',URL)
        self.assertEqual(result['fields']['price_origin'],['10% 40,000원'])

    def test_merged_table_cells_are_not_price_evidence(self):
        result=page_data('<table><tr><td colspan="2">가격</td><td>18,000원</td></tr></table>',URL)
        self.assertEqual(result['tables'],[])

    def test_unlisted_url_is_not_requested(self):
        calls=[]
        with self.assertRaises(ValueError):fetch_allowed('http://127.0.0.1/private',lambda u:calls.append(u))
        self.assertEqual(calls,[])

    def test_robots_denial_stops_page_request(self):
        calls=[]
        def transport(url):calls.append(url);return 'User-agent: *\nDisallow: /feed/'
        with self.assertRaises(ValueError):fetch_allowed(URL,transport)
        self.assertEqual(calls,['https://www.hankyung.com/robots.txt'])

    def test_robots_cached_per_run(self):
        calls=[];cache={}
        def transport(url):calls.append(url);return 'User-agent: *\nAllow: /' if url.endswith('robots.txt') else 'page'
        self.assertEqual(fetch_allowed(URL,transport,cache),'page')
        fetch_allowed(URL,transport,cache)
        self.assertEqual(sum(u.endswith('robots.txt') for u in calls),1)

    def test_hidden_script_is_not_evidence(self):
        parsed=page_data('<title>안내</title><script>17:30</script><style>예약</style><p>입장마감은 오후 5시 30분</p>',URL)
        self.assertNotIn('17:30',parsed['text'])
        self.assertEqual(compare('apma-faq',parsed['text'])[0]['status'],'matched')
        self.assertEqual(compare('apma-faq','다른 운영 안내')[0]['status'],'not_found')

    def test_rss_dates_categories_and_duplicate_filter(self):
        recent=format_datetime(utcnow());old=format_datetime(utcnow()-timedelta(days=9))
        def item(title,link,date):return f'<item><title>{title}</title><link>{link}</link><pubDate>{date}</pubDate></item>'
        raw='<rss><channel><title>소식</title>'+item('새 전시 개막','https://www.hankyung.com/article/1',recent)*2+item('선물세트 출시','https://www.hankyung.com/article/2',recent)+item('립스틱 출시','https://www.hankyung.com/article/3',old)+item('편의점 신상','http://localhost/x',recent)+'</channel></rss>'
        result=rss_data(raw,URL)
        self.assertEqual(len(result['candidates']),1)
        self.assertEqual(result['candidates'][0]['category'],'place')
        self.assertEqual(result['fetched_count'],5)

    def test_xml_entities_rejected(self):
        with self.assertRaises(ValueError):rss_data('<!DOCTYPE rss><rss/>',URL)

    def test_failure_is_saved_and_backoff_prevents_repeat(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'config').mkdir()
            (root/'config/sources.json').write_text(json.dumps({'sources':[{'id':'news','url':URL,'kind':'rss'}]}))
            calls=[]
            def fail(url):calls.append(url);raise OSError('offline')
            collector=Collector(root,fail)
            self.assertEqual(collector.run()['sources'][0]['status'],'unavailable')
            collector.run()
            self.assertEqual(len(calls),1)

    def test_topics_follow_subject(self):
        for category,title,expected in [('place','솔 르윗 전시','exhibition'),('place','주말 데이트','outing'),('beauty','새로운 립 틴트','lip'),('beauty','스킨케어','skincare'),('food','신상 크루아상','bakery'),('food','간편식','food')]:
            self.assertEqual(topic_for({'category':category,'title':title}),expected)
