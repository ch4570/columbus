"""Exercise real-source receipt reuse before a continuous model evaluation."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'skills/columbus/scripts'))
from columbus.index import RepositoryIndex
from columbus.presentation import render
from columbus.receipts import ReceiptFile

source = ROOT / 'skills/columbus/scripts/columbus/receipts.py'
raw = source.read_bytes()
queries = ['ReceiptFile', 'ReceiptFile.save', 'ReceiptFile']
report = {'source': source.relative_to(ROOT).as_posix(), 'source_sha256': hashlib.sha256(raw).hexdigest(),
          'queries': queries, 'budget_bytes': 16000, 'conditions': {}}
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    target = root / 'receipts.py'
    target.write_bytes(raw)
    index = RepositoryIndex(root / '.columbus/index.sqlite')
    index.refresh(root)
    report['analyzer_fingerprint'] = index.status()['analyzer_fingerprint']
    for condition in ['without_receipt', 'retained_receipt']:
        receipt_path = root / '.columbus/session.json'
        delivered = set()
        records = []
        for query in queries:
            receipt = ReceiptFile(str(receipt_path), index.status()) if condition == 'retained_receipt' else None
            packet = index.context(query, path='receipts.py', budget_bytes=16000,
                                   output_format='json', receipt=receipt.data if receipt else None)
            response = render(packet, 'json')
            assert len(response.encode()) <= 16000
            duplicate = 0
            source_bytes = 0
            for item in packet['items']:
                text = item.get('source', '')
                if not text:
                    continue
                assert item['source_hash'] == hashlib.sha256(raw).hexdigest()
                start, end = item['source_start_offset'], item['source_end_offset']
                assert text == raw.decode()[start:end]
                positions = set(range(start, end))
                duplicate += len(delivered & positions)
                delivered.update(positions)
                source_bytes += len(text.encode())
            if receipt:
                assert duplicate == 0
                receipt.save(packet)
            records.append({'query': query, 'response_bytes': len(response.encode()),
                            'source_bytes': source_bytes, 'repeated_characters': duplicate,
                            'receipt_status': packet.get('receipt'), 'items': len(packet['items'])})
        report['conditions'][condition] = records
    assert report['conditions']['retained_receipt'][0]['source_bytes'] > 0
    assert all(r['source_bytes'] == 0 for r in report['conditions']['retained_receipt'][1:])
    assert any(r['repeated_characters'] > 0 for r in report['conditions']['without_receipt'][1:])
    # A new agent/context uses a fresh receipt and must receive the source again.
    fresh = ReceiptFile(str(root / '.columbus/new-agent.json'), index.status())
    packet = index.context(queries[0], path='receipts.py', budget_bytes=16000, receipt=fresh.data)
    assert any(item.get('source') for item in packet['items'])
    # Changed bytes invalidate old delivered ranges after a real resync.
    changed = raw + b'\n# change after delivery\n'
    target.write_bytes(changed)
    index.refresh(root, fast=True)
    prior = ReceiptFile(str(root / '.columbus/session.json'), index.status())
    packet = index.context(queries[0], path='receipts.py', budget_bytes=16000, receipt=prior.data)
    assert any(item.get('source') for item in packet['items'])
    assert all(item['source_hash'] == hashlib.sha256(changed).hexdigest()
               for item in packet['items'] if item.get('source'))
    report['fresh_agent_reemits'] = True
    report['changed_source_reemits'] = True
output = Path(sys.argv[1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))
