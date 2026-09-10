import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from src.reels import build


class ReelTests(unittest.TestCase):
    def test_sample_is_not_rendered(self):
        with self.assertRaises(ValueError):build(Path('.'),'item','version',{'sample':True})

    def test_cached_video_integrity_and_separate_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);content={'sample':False,'caption':'caption'}
            def render(command,**kwargs):Path(command[-1]).write_bytes(b'video fixture')
            with patch('src.reels.valid_bundle',return_value=True),patch('src.reels.verify_content'),patch('src.reels.encoder',return_value='ffmpeg'),patch('src.reels.subprocess.run',side_effect=render) as run:
                result=build(root,'item','version',content)
                self.assertIsNone(result['approval'])
                self.assertEqual(result['status'],'awaiting_review')
                self.assertEqual(build(root,'item','version',content),result)
                self.assertEqual(run.call_count,1)
                (root/result['path']).write_bytes(b'tampered')
                with self.assertRaises(ValueError):build(root,'item','version',content)
