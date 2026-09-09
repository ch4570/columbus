"""Check binary/text transitions through complete snapshot refreshes."""
import hashlib
import json
from pathlib import Path
import tempfile
from columbus.index import RepositoryIndex
asset=Path('/tmp/columbus-django-evaluation/tests/mail/attachments/file_png.txt').read_bytes()
with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);(root/'valid.py').write_text('def valid(): pass\n')
    index=RepositoryIndex(root/'.columbus/index.sqlite');index.refresh(root)
    file=root/'file_png.txt';file.write_bytes(asset)
    binary=index.refresh(root,fast=True)
    assert 'file_png.txt' in binary['inventory']['binary_paths'] and binary['files']==1
    file.write_text('Now ordinary text')
    text=index.refresh(root,fast=True)
    assert text['files']==2 and text['refresh']['parsed_files']>=1
    file.write_bytes(asset)
    restored=index.refresh(root,fast=True)
    assert restored['files']==1 and restored['refresh']['removed_files']==1
    assert index.search('valid')['hits'][0]['name']=='valid'
    print(json.dumps({'asset_sha256':hashlib.sha256(asset).hexdigest(),'fixed':True,'binary_excluded':True,'text_transition_indexed':True,'binary_transition_removed':True,'valid_source_retained':True},indent=2))
