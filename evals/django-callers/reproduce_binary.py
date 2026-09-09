"""Retain the whole-index failure without replaying a long full-repo index."""
import hashlib
import json
from pathlib import Path
import tempfile
from columbus.index import RepositoryIndex
from columbus.discovery import discover
asset=Path('/tmp/columbus-django-evaluation/tests/mail/attachments/file_png.txt').read_bytes()
with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);(root/'valid.py').write_text('def valid(): pass\n')
    index=RepositoryIndex(root/'.columbus/index.sqlite');before=index.refresh(root)
    (root/'file_png.txt').write_bytes(asset)
    paths,inventory=discover(root)
    assert 'file_png.txt' in paths
    try:index.refresh(root)
    except ValueError as error:
        message=str(error);assert 'Binary source is excluded' in message
    else:raise AssertionError('Expected observed failure')
    assert index.status()['revision']==before['revision']
    print(json.dumps({'asset_sha256':hashlib.sha256(asset).hexdigest(),'asset_bytes':len(asset),'discovered_as_source':True,'error':message,'prior_snapshot_preserved':True,'fixed':False},indent=2))
