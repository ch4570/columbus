"""Bounded read requests and deterministic races; synthetic evidence only."""
from contextlib import contextmanager
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_retention(cohort):
    path = ROOT / 'evals' / cohort / 'retain.py'
    spec = importlib.util.spec_from_file_location(
        '_sized_read_' + cohort.replace('-', '_'), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RETENTIONS = tuple((name, load_retention(name)) for name in (
    'source-call-sites-cohort', 'quotes-three-arm'))


@contextmanager
def observe_reads(retention, before_read=None, *, read_limit=None):
    """Delegate real descriptor reads/stat calls; only observe the request."""
    original_fdopen = retention.os.fdopen
    requests, results = [], []

    class ObservedStream:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *exception):
            return self.stream.__exit__(*exception)

        def fileno(self):
            return self.stream.fileno()

        def read(self, size):
            requests.append(size)
            if before_read is not None:
                before_read()
            raw = self.stream.read(size if read_limit is None else min(size, read_limit))
            results.append(raw)
            return raw

    def fdopen(*args, **kwargs):
        return ObservedStream(original_fdopen(*args, **kwargs))

    with mock.patch.object(retention.os, 'fdopen', side_effect=fdopen):
        yield requests, results


class RetentionSizedReadTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='retention-sized-read-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.path = self.root / 'evidence.bin'

    def test_empty_and_tiny_files_request_size_plus_one_and_preserve_bytes(self):
        for name, retention in RETENTIONS:
            for raw in (b'', b'x', b'\x00\xff\r\n', 'tiny \u03c0\n'.encode('utf-8')):
                with self.subTest(cohort=name, raw=raw):
                    self.path.write_bytes(raw)
                    with observe_reads(retention) as (requests, results):
                        self.assertEqual(retention.stable(self.path, self.root), raw)
                    self.assertEqual(requests, [len(raw) + 1])
                    self.assertEqual(results, [raw])

    def test_maximum_boundary_is_inclusive_with_one_extra_read_byte(self):
        # Lower only the cap, avoiding a 128 MiB fixture in a boundary unit test.
        limit = 16
        for name, retention in RETENTIONS:
            for size in (limit - 1, limit):
                with self.subTest(cohort=name, size=size):
                    raw = bytes(range(size))
                    self.path.write_bytes(raw)
                    with mock.patch.object(retention, 'MAX_FILE', limit), \
                            observe_reads(retention) as (requests, results):
                        self.assertEqual(retention.stable(self.path, self.root), raw)
                    self.assertEqual(requests, [size + 1])
                    self.assertEqual(results, [raw])

    def test_oversized_file_is_rejected_before_opening(self):
        for name, retention in RETENTIONS:
            with self.subTest(cohort=name):
                self.path.write_bytes(b'x' * 17)
                with mock.patch.object(retention, 'MAX_FILE', 16), \
                        mock.patch.object(retention.os, 'open') as opened:
                    with self.assertRaisesRegex(ValueError, 'oversized evidence'):
                        retention.stable(self.path, self.root)
                    opened.assert_not_called()

    def test_growth_during_read_is_rejected_without_expanding_request(self):
        original = b'old!'
        for name, retention in RETENTIONS:
            for suffix in (b'+', b'+' * 1024):
                with self.subTest(cohort=name, growth=len(suffix)):
                    self.path.write_bytes(original)

                    def grow():
                        with self.path.open('ab') as stream:
                            stream.write(suffix)

                    with observe_reads(retention, grow) as (requests, results):
                        with self.assertRaisesRegex(ValueError, 'Evidence changed during read'):
                            retention.stable(self.path, self.root)
                    self.assertEqual(requests, [len(original) + 1])
                    self.assertEqual(results, [original + b'+'])

    def test_growth_at_maximum_boundary_is_rejected(self):
        original = b'full'
        for name, retention in RETENTIONS:
            with self.subTest(cohort=name):
                self.path.write_bytes(original)

                def grow():
                    with self.path.open('ab') as stream:
                        stream.write(b'+')

                with mock.patch.object(retention, 'MAX_FILE', len(original)), \
                        observe_reads(retention, grow) as (requests, results):
                    with self.assertRaisesRegex(ValueError, 'Evidence changed during read'):
                        retention.stable(self.path, self.root)
                self.assertEqual(requests, [len(original) + 1])
                self.assertEqual(results, [original + b'+'])

    def test_shrink_during_read_is_rejected(self):
        original = b'longer'
        for name, retention in RETENTIONS:
            for remaining in (b'', original[:1]):
                with self.subTest(cohort=name, size=len(remaining)):
                    self.path.write_bytes(original)

                    def shrink():
                        with self.path.open('r+b') as stream:
                            stream.truncate(len(remaining))

                    with observe_reads(retention, shrink) as (requests, results):
                        with self.assertRaisesRegex(ValueError, 'Evidence changed during read'):
                            retention.stable(self.path, self.root)
                    self.assertEqual(requests, [len(original) + 1])
                    self.assertEqual(results, [remaining])

    def test_short_read_with_unchanged_metadata_is_rejected(self):
        original = b'full contents'
        for name, retention in RETENTIONS:
            for limit in (0, len(original) - 1):
                with self.subTest(cohort=name, returned_bytes=limit):
                    self.path.write_bytes(original)
                    before = self.path.stat()
                    with observe_reads(retention, read_limit=limit) as (requests, results):
                        with self.assertRaisesRegex(ValueError, 'Evidence changed during read'):
                            retention.stable(self.path, self.root)
                    self.assertEqual(requests, [len(original) + 1])
                    self.assertEqual(results, [original[:limit]])
                    after = self.path.stat()
                    for field in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns'):
                        self.assertEqual(getattr(after, field), getattr(before, field))

    def test_size_change_between_stat_and_open_uses_validated_size_and_rejects(self):
        original = b'old!'
        for name, retention in RETENTIONS:
            for changed in (b'', b'new content' * 128):
                with self.subTest(cohort=name, size=len(changed)):
                    self.path.write_bytes(original)
                    original_open = retention.os.open

                    def change_then_open(path, flags):
                        self.assertEqual(Path(path), self.path)
                        self.path.write_bytes(changed)
                        return original_open(path, flags)

                    with mock.patch.object(retention.os, 'open', side_effect=change_then_open) as opened, \
                            observe_reads(retention) as (requests, results):
                        with self.assertRaisesRegex(ValueError, 'Evidence changed during read'):
                            retention.stable(self.path, self.root)
                    opened.assert_called_once()
                    self.assertEqual(requests, [len(original) + 1])
                    self.assertEqual(results, [changed[:len(original) + 1]])

    def test_same_size_replacement_between_stat_and_open_is_rejected(self):
        original, changed = b'old!', b'new!'
        for name, retention in RETENTIONS:
            with self.subTest(cohort=name):
                self.path.write_bytes(original)
                replacement = self.root / 'replacement.bin'
                replacement.write_bytes(changed)
                original_open = retention.os.open

                def replace_then_open(path, flags):
                    self.assertEqual(Path(path), self.path)
                    # No descriptor is open yet: replacement works on Windows too.
                    os.replace(replacement, self.path)
                    return original_open(path, flags)

                with mock.patch.object(retention.os, 'open', side_effect=replace_then_open) as opened, \
                        observe_reads(retention) as (requests, results):
                    with self.assertRaisesRegex(ValueError, 'Evidence changed during read'):
                        retention.stable(self.path, self.root)
                opened.assert_called_once()
                self.assertEqual(requests, [len(original) + 1])
                self.assertEqual(results, [changed])


if __name__ == '__main__':
    unittest.main()
