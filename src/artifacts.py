"""Content-addressed card bundles; approval covers caption and rendered bytes."""
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from .render import render_cards

def fingerprint(content, hashes):
    return hashlib.sha256(json.dumps({'content':content,'cards':hashes},ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def build_bundle(root,item_id,content):
    base=Path(root)/'assets/images/generated'/item_id;base.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base,prefix='staging-') as temp:
        paths=render_cards(content,temp,root)
        hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
        version=fingerprint(content,hashes);target=base/version
        if not target.exists():
            # Temporary and target are under the same explicit artifact directory.
            shutil.copytree(temp,target)
        elif not valid_bundle(root,item_id,version,content):
            raise ValueError('기존 미디어가 변경되었습니다. 기존 버전을 덮어쓰지 않습니다.')
        return version

def valid_bundle(root,item_id,version,content):
    base=Path(root)/'assets/images/generated'/item_id/version
    try:hashes=[hashlib.sha256((base/f'card-{i}.png').read_bytes()).hexdigest() for i in range(1,5)]
    except OSError:return False
    return fingerprint(content,hashes)==version
