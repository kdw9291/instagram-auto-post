import unittest
from src.news_links import match
from src.collector import classify

class NewsLinksTests(unittest.TestCase):
    def setUp(self):
        self.draft={'source_id':'official-1','category':'beauty','names':['베리어 리커버리 버블 클렌저'],'urls':['https://www.apgroup.com/int/ko/news/2026-09-03-2.html']}
        self.candidate={'title':'일리윤 베리어 리커버리 버블 클렌저 출시','category':'beauty'}
    def test_exact_long_name_links_official_only(self):
        self.assertEqual(match(self.candidate,[self.draft])['source_id'],'official-1')
    def test_brand_alone_and_short_name_do_not_link(self):
        self.assertIsNone(match(dict(self.candidate,title='일리윤 새 제품 출시'),[self.draft]))
        self.assertIsNone(match(dict(self.candidate,title='새 크림 출시'),[dict(self.draft,names=['크림'])]))
    def test_ambiguous_matches_and_category_mismatch_block(self):
        self.assertIsNone(match(self.candidate,[self.draft,dict(self.draft,source_id='other')]))
        self.assertIsNone(match(dict(self.candidate,category='food'),[self.draft]))
    def test_added_rss_allowlist_preserves_host_boundary(self):
        from src.collector import fetch_allowed
        calls=[]
        def transport(url):
            calls.append(url)
            return 'User-agent: *\nAllow: /' if url.endswith('robots.txt') else '<rss/>'
        for url in ('https://www.hankyung.com/feed/economy','https://mediahub.seoul.go.kr/news/rss/06'):
            self.assertEqual(fetch_allowed(url,transport),'<rss/>')
            with self.assertRaises(ValueError):fetch_allowed(url+'?redirect=bad',transport)

    def test_product_variant_is_not_base_product(self):
        self.assertIsNone(match(dict(self.candidate,title='베리어 리커버리 버블 클렌저플러스 출시'),[self.draft]))

    def test_bank_and_store_business_are_not_food(self):
        for title in ['은행 없으면 편의점 가지 뭐','편의점 매출 증가','CU 채용 확대']:
            self.assertIsNone(classify(title))
        self.assertEqual(classify('CU 신상 도시락 출시'),'food')

if __name__=='__main__':unittest.main()
