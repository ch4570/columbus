"""Receiver-specific guidance does not relax saved declaration selection."""
import copy
import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from columbus.archive import (_overload_receiver_hint, archive, search_archive,
                              source_archive, source_archive_many)
from columbus.cli import main
from columbus.index import RepositoryIndex


class ArchiveReceiverGuidanceTests(unittest.TestCase):
    def test_companion_receivers_reject_with_guidance_and_exact_id_batch_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body = ('package p\nclass RequestBody {\n  companion object {\n'
                    '    fun ByteString.toRequestBody(type: String?): Int = 1\n'
                    '    fun FileDescriptor.toRequestBody(type: String?): Int = 2\n'
                    '    fun String.toRequestBody(type: String?): Int = 3\n'
                    '    fun ByteArray.toRequestBody(type: String?): Int = 4\n'
                    '    fun String.same(): Int = 5\n'
                    '    fun String.same(x: Int): Int = x\n  }\n}\n')
            (root / 'Body.kt').write_bytes(body.encode('utf-8'))
            index = RepositoryIndex(root / '.columbus/index.sqlite')
            index.refresh(root)
            for codec in ('gzip', 'xz'):
                artifact = root / (codec + '.graph')
                archive(index, artifact, codec)
                query = 'p.RequestBody.Companion.toRequestBody'
                rows = search_archive(artifact, query, limit=50)['items']
                self.assertEqual(len(rows), 4)
                for alias in (query, 'RequestBody.Companion.toRequestBody'):
                    with self.subTest(codec=codec, query=alias):
                        with patch('columbus.sync_state.read_stable',
                                   side_effect=AssertionError('Ambiguity must reject before reading source')):
                            with self.assertRaises(ValueError) as rejected:
                                source_archive_many(artifact, [alias], root, overloads=True)
                        message = str(rejected.exception)
                        self.assertIn('ambiguous', message)
                        self.assertIn('different Kotlin receiver identities', message)
                        for receiver in ('ByteString', 'FileDescriptor', 'String', 'ByteArray'):
                            self.assertIn(repr(receiver), message)
                        self.assertIn('same owner and receiver', message)
                        self.assertIn('batch selected exact IDs', message)
                        self.assertIn('archive-source without --overloads', message)
                ids = [row['id'] for row in rows if row['id'].endswith(('@String', '@ByteArray'))]
                self.assertEqual(len(ids), 2)
                batch = source_archive_many(artifact, ids, root)
                self.assertEqual({node['id'] for node in batch['targets']}, set(ids))
                self.assertEqual(batch['total_lines'], 2)
                # Exact rank still wins, and same-receiver families still group.
                exact = source_archive_many(artifact, ids[:1], root, overloads=True)
                self.assertEqual(exact['sources'][0]['source'], source_archive(artifact, ids[0], root)['source'])
                same = source_archive_many(artifact, ['RequestBody.Companion.same'], root, overloads=True)
                self.assertEqual(len(same['targets']), 2)
                self.assertTrue(all(node['id'].endswith('@String') for node in same['targets']))
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    code = main(['archive-source', query, '--overloads', '--input', str(artifact), '--repo', str(root)])
                self.assertEqual(code, 2)
                self.assertEqual(out.getvalue(), '')
                self.assertIn('batch selected exact IDs', err.getvalue())

    @staticmethod
    def nodes(receivers):
        return [dict(id=f'Body.kt::p.Body.read:method()@{receiver}', path='Body.kt',
                     parent_id='Body.kt::p.Body:class', qualname='p.Body.read', kind='method',
                     language='kotlin', receiver_type=receiver, parameter_types=[], local=False,
                     fidelity='ast') for receiver in receivers]

    def test_receiver_labels_are_escaped_bounded_and_truncation_is_explicit(self):
        receivers = [f'{number:02d}\x1b[31m\n\t\u202e' + '\U0001f34b' * 100 for number in range(9)]
        hint = _overload_receiver_hint(self.nodes(receivers))
        self.assertIsInstance(hint, str)
        self.assertTrue(hint.isascii())
        self.assertNotIn('\x1b', hint)
        self.assertNotIn('\n', hint)
        self.assertIn('\\x1b', hint)
        self.assertIn('\\n', hint)
        self.assertIn('\\u202e', hint)
        self.assertIn('...', hint)
        self.assertIn('1 more', hint)
        self.assertNotIn("'08", hint)
        self.assertLessEqual(len(hint.encode('ascii')), 8 * 96 + 32)

    def test_other_ambiguities_do_not_claim_receiver_only_conflict(self):
        nodes = self.nodes(['String', 'Int'])
        self.assertIsNotNone(_overload_receiver_hint(nodes))
        for key, value in (('path', 'Other.kt'), ('parent_id', 'Other'), ('qualname', 'p.Other.read'),
                           ('receiver_type', None), ('local', True), ('fidelity', 'fallback'),
                           ('parameter_types', None)):
            changed = copy.deepcopy(nodes)
            changed[1][key] = value
            with self.subTest(key=key):
                self.assertIsNone(_overload_receiver_hint(changed))
        self.assertIsNone(_overload_receiver_hint([]))
        self.assertIsNone(_overload_receiver_hint(self.nodes(['String'])))
        duplicate = nodes + [copy.deepcopy(nodes[0])]
        self.assertIsNone(_overload_receiver_hint(duplicate))
        java = self.nodes(['String', 'Int'])
        for node in java:
            node['language'] = 'java'
        self.assertIsNone(_overload_receiver_hint(java))

    def test_cli_help_explains_same_owner_and_receiver_boundary(self):
        output = io.StringIO()
        with redirect_stdout(output), self.assertRaises(SystemExit) as exit_status:
            main(['archive-source', '--help'])
        self.assertEqual(exit_status.exception.code, 0)
        help_text = ' '.join(output.getvalue().split())
        self.assertIn('same owner and receiver', help_text)
        self.assertIn('batch exact IDs from archive-search for different receivers', help_text)


if __name__ == '__main__':
    unittest.main()
