"""Physical source coordinates survive Unicode separators and bounded receipts."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from columbus.index import RepositoryIndex
from columbus.presentation import render
from columbus.receipts import ReceiptFile


class SourceLineTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.index = RepositoryIndex(self.root / '.columbus/index.sqlite')

    def test_unicode_separators_preserve_exact_symbol_source_and_physical_line_numbers(self):
        for separator in ('\u0085', '\u2028', '\u2029', '\x0b', '\x0c'):
            for newline in ('\n', '\r\n', '\r'):
                with self.subTest(separator=repr(separator), newline=repr(newline)):
                    target = f'def target(): return "x{separator}TARGET_BODY"'
                    source = f'def before(): return "x{separator}y"{newline}{target}{newline}'
                    (self.root / 'sample.py').write_bytes(source.encode('utf-8'))
                    self.index.refresh(self.root)
                    symbol = self.index.symbol('target')
                    self.assertEqual(target, symbol['source'])
                    self.assertEqual((2, 2), (symbol['start_line'], symbol['excerpt_end_line']))
                    for fmt in ('json', 'text'):
                        packet = self.index.context(symbol['id'], budget_bytes=2048, output_format=fmt)
                        self.assertEqual([target], [item['source'] for item in packet['items']])
                        output = render(packet, fmt)
                        self.assertEqual(packet['used_bytes'], len(output.encode('utf-8')))
                        self.assertLessEqual(packet['used_bytes'], 2048)
                        if fmt == 'text':
                            self.assertIn('2| def target()', output)
                            self.assertNotIn('3| ', output)
                            self.assertNotIn(separator, output)

    def test_small_budget_receipts_preserve_unicode_source_and_every_offset(self):
        source = 'def target():\n    value = "' + '\u2028한' * 600 + '"\n    return "TAIL"\n'
        (self.root / 'sample.py').write_bytes(source.replace('\n', '\r\n').encode('utf-8'))
        self.index.refresh(self.root)
        normalized = source.rstrip('\n')
        symbol_id = self.index.search('target')['hits'][0]['id']
        for fmt in ('json', 'text'):
            receipt_path = self.root / '.columbus' / (fmt + '.json')
            seen, pieces = set(), []
            for _ in range(40):
                receipt = ReceiptFile(str(receipt_path), self.index.status())
                packet = self.index.context(symbol_id, receipt=receipt.data,
                                            budget_bytes=2048, output_format=fmt)
                for item in packet['items']:
                    start, end = item['source_start_offset'], item['source_end_offset']
                    self.assertEqual(normalized[start:end], item['source'])
                    self.assertFalse(seen.intersection(range(start, end)))
                    seen.update(range(start, end))
                    pieces.append(item['source'])
                self.assertLessEqual(len(render(packet, fmt).encode('utf-8')), 2048)
                receipt.save(packet)
                if not packet['items']:
                    break
            else:
                self.fail('Receipt did not finish a bounded source fixture')
            self.assertIn('TAIL', ''.join(pieces))
            self.assertEqual(600, ''.join(pieces).count('\u2028'))
            self.assertTrue({i for i, c in enumerate(normalized) if c != '\n'} <= seen)

    def test_receipt_from_old_unicode_line_view_does_not_hide_unread_source(self):
        source = 'def before(): return "x\u2028y"\ndef target(): return "TARGET_BODY"\n'
        (self.root / 'sample.py').write_text(source, encoding='utf-8')
        self.index.refresh(self.root)
        receipt = ReceiptFile(str(self.root / '.columbus/old.json'), self.index.status())
        receipt.data['files']['sample.py'] = {
            'source_hash': hashlib.sha256(source.encode('utf-8')).hexdigest(),
            'source_view_hash': hashlib.sha256('\n'.join(source.splitlines()).encode('utf-8')).hexdigest(),
            'spans': [[0, len(source)]],
        }
        packet = self.index.context('sample.py::target:function', receipt=receipt.data)
        self.assertEqual(['def target(): return "TARGET_BODY"'], [i['source'] for i in packet['items']])
        self.assertEqual(0, packet['receipt']['seen_source_bytes'])


if __name__ == '__main__':
    unittest.main()
