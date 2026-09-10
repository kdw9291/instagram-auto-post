import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from src.editorial import make_apma, EvidenceError, SOURCE_URLS
from src.store import Store


class EditorialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.at = datetime.now(timezone.utc)
        start = self.at - timedelta(days=1)
        end = self.at + timedelta(days=30)
        table = [['가격', '18,000원', '9,000원'], ['대상', '성인 (만 19세 이상)', '어린이']]
        self.sources = {
            'apma-guide': {'text': '《Sol LeWitt: Open Structure》\n관람안내\n관 람 시 간\n화~일요일10:00~18:00\n매주 월요일, 매년 1월 1일, 설/추석 연휴\n이번 전시의 관람을 위해서는 온라인 사전 예약이 필요합니다.\n물품보관소 화~일요일10:00~18:00', 'tables': [table]},
            'apma-faq': {'text': '오전 10시부터 오후 6시까지(입장마감은 오후 5시 30분)\n정기휴관일은 매주 월요일, 1월 1일 / 설, 추석 연휴입니다.\n서울특별시 용산구 한강대로 100에 위치', 'tables': []},
            'apgroup-exhibition': {'text': f'솔 르윗\n전시제목: 《Sol LeWitt: Open Structure》\n전시기간: {start.year}년 {start.month}월 {start.day}일 (화) ~ {end.year}년 {end.month}월 {end.day}일 (일)\n전시장소: 아모레퍼시픽미술관 (서울시 용산구 한강대로 100)', 'tables': [table]},
        }
        self.write_sources()

    def write_sources(self, age=0):
        directory = self.root / 'data/runtime/collection'
        directory.mkdir(parents=True, exist_ok=True)
        report = {'sources': []}
        for key, source in self.sources.items():
            snapshot = dict(source, url=SOURCE_URLS[key], checked_at=(self.at-timedelta(hours=age)).isoformat())
            raw = json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode()
            digest = hashlib.sha256(raw).hexdigest()
            (directory / f'{key}-{digest}.json').write_bytes(raw)
            report['sources'].append(dict(id=key, status='ok', url=snapshot['url'], checked_at=snapshot['checked_at'], snapshot_hash=digest))
        (directory / 'report.json').write_text(json.dumps(report), encoding='utf-8')

    def test_real_manuscript_has_evidence_and_correct_adult_fee(self):
        content, receipt = make_apma(self.root, self.at)
        self.assertFalse(content['sample'])
        self.assertEqual(len(receipt['claims']), 12)
        self.assertIn('18,000원', content['caption'])
        self.assertIn('17:30', content['caption'])

    def test_price_follows_target_column_and_conflicts_fail(self):
        self.sources['apgroup-exhibition']['tables'] = [[['가격', '9,000원', '18,000원'], ['대상', '어린이', '성인(만 19세 이상)']]]
        self.write_sources()
        make_apma(self.root, self.at)
        self.sources['apgroup-exhibition']['tables'][0][0][2] = '20,000원'
        self.write_sources()
        with self.assertRaises(EvidenceError): make_apma(self.root, self.at)

    def test_missing_reservation_blocks_draft(self):
        self.sources['apma-guide']['text'] = self.sources['apma-guide']['text'].replace('온라인 사전 예약', '현장 구매')
        self.write_sources()
        with self.assertRaises(EvidenceError): make_apma(self.root, self.at)

    def test_stale_and_future_sources_block(self):
        for age in (13, -1):
            with self.subTest(age=age):
                self.write_sources(age)
                with self.assertRaises(EvidenceError): make_apma(self.root, self.at)

    def test_snapshot_tampering_blocks(self):
        path = next((self.root / 'data/runtime/collection').glob('apma-guide-*.json'))
        path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaises(EvidenceError): make_apma(self.root, self.at)

    def test_approval_is_idempotent_and_invalidated_by_missing_source(self):
        store = Store(self.root)
        store.produce()
        item = store.snapshot()['items'][0]
        self.assertEqual(item['state'], 'waiting')
        store.action(item['id'], item['version'], 'approve')
        store.produce()
        self.assertEqual(store.snapshot()['items'][0]['approval'], item['version'])
        (self.root / 'data/runtime/collection/report.json').unlink()
        with self.assertRaises(EvidenceError): store.action(item['id'], item['version'], 'approve')
        item = store.snapshot()['items'][0]
        self.assertEqual(item['state'], 'needs_verification')
        self.assertIsNone(item['approval'])

    def test_manual_edit_is_preserved_and_requires_reverification(self):
        store = Store(self.root)
        store.produce()
        item = store.snapshot()['items'][0]
        store.action(item['id'], item['version'], 'edit', '사용자 수정 문구')
        store.produce()
        updated = store.snapshot()['items'][0]
        self.assertEqual(updated['content']['caption'], '사용자 수정 문구')
        self.assertFalse(updated['can_approve'])

    def test_review_off_creates_ready_without_approval(self):
        store = Store(self.root)
        store.settings(False, 1)
        store.produce()
        item = store.snapshot()['items'][0]
        self.assertEqual(item['state'], 'ready')
        self.assertIsNone(item['approval'])
        self.assertFalse(store.snapshot()['publishing'])


if __name__ == '__main__': unittest.main()
