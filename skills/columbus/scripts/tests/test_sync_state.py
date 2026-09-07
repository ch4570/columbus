"""Stable reads retain file identity and change detection across Windows APIs."""
import ctypes
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from columbus import sync_state


class StableReadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'source.py'
        self.data = b'def stable(): return 1\n'
        self.source.write_bytes(self.data)

    def metadata(self, **changed):
        actual = self.source.stat()
        values = {name: getattr(actual, name) for name in
                  ('st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_ino', 'st_dev')}
        return SimpleNamespace(**{**values, **changed})

    def test_creation_and_change_ctime_difference_is_not_a_source_change(self):
        # CPython Windows versions disagree on whether ctime means creation.
        stats = [self.metadata(st_ctime_ns=value) for value in (100, 200, 200, 100)]
        with patch.object(sync_state, 'WINDOWS', True), \
                patch.object(sync_state.os, 'fstat', side_effect=stats), \
                patch.object(sync_state, '_windows_change_time', return_value=900):
            data, signature = sync_state.read_stable(self.root, 'source.py')
        self.assertEqual(data, self.data)
        self.assertEqual(signature[2], 900)

    def test_same_size_restored_mtime_change_during_read_is_rejected(self):
        with patch.object(sync_state, 'WINDOWS', True), \
                patch.object(sync_state.os, 'fstat', return_value=self.metadata()), \
                patch.object(sync_state, '_windows_change_time', side_effect=[100, 100, 200, 200]):
            with self.assertRaisesRegex(sync_state.SnapshotChanged, 'while being read'):
                sync_state.read_stable(self.root, 'source.py')

    def test_replaced_inode_or_device_is_rejected_even_with_equal_timestamps(self):
        for field in ('st_ino', 'st_dev'):
            with self.subTest(field=field):
                before = self.metadata()
                replacement = self.metadata(**{field: getattr(before, field) + 1})
                with patch.object(sync_state, 'WINDOWS', True), \
                        patch.object(sync_state.os, 'fstat', side_effect=[before, replacement, replacement, replacement]), \
                        patch.object(sync_state, '_windows_change_time', return_value=100):
                    with self.assertRaisesRegex(sync_state.SnapshotChanged, 'while being read'):
                        sync_state.read_stable(self.root, 'source.py')

    def test_changed_discovery_signature_is_rejected_before_reading(self):
        expected = sync_state.stat_signature(self.metadata())
        expected[2] = 100
        with patch.object(sync_state, 'WINDOWS', True), \
                patch.object(sync_state, '_windows_change_time', return_value=200):
            with self.assertRaisesRegex(sync_state.SnapshotChanged, 'during sync'):
                sync_state.read_stable(self.root, 'source.py', expected)


class WindowsChangeTimeTests(unittest.TestCase):
    def setUp(self):
        sync_state._windows_change_reader.cache_clear()
        self.addCleanup(sync_state._windows_change_reader.cache_clear)

    def reader(self, query):
        library = SimpleNamespace(GetFileInformationByHandleEx=query)
        with patch.dict(sys.modules, {'msvcrt': SimpleNamespace(get_osfhandle=lambda fd: fd + 200)}), \
                patch.object(ctypes, 'WinDLL', return_value=library, create=True):
            return sync_state._windows_change_reader()

    def test_filetime_layout_epoch_and_borrowed_handle_are_correct(self):
        def information(handle, kind, buffer, size):
            self.assertEqual((handle, kind, size), (207, 0, 40))
            self.assertEqual(type(buffer._obj).ChangeTime.offset, 24)
            self.assertEqual(type(buffer._obj).FileAttributes.offset, 32)
            buffer._obj.ChangeTime = 116_444_736_000_000_000 + 12_345
            return 1

        query = Mock(side_effect=information)
        self.assertEqual(self.reader(query)(7), 1_234_500)
        query.assert_called_once()

    def test_failed_or_unavailable_change_time_never_becomes_valid_metadata(self):
        reader = self.reader(Mock(return_value=0))
        with patch.object(ctypes, 'get_last_error', return_value=5, create=True), \
                patch.object(ctypes, 'WinError', return_value=OSError(5, 'denied'), create=True):
            with self.assertRaises(OSError):
                reader(7)
        sync_state._windows_change_reader.cache_clear()
        with self.assertRaisesRegex(OSError, 'change time is unavailable'):
            self.reader(Mock(return_value=1))(7)


if __name__ == '__main__':
    unittest.main()
