"""Opt-in call-site CLI dispatch is read-only and leaves legacy selection alone."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from columbus.cli import main
from columbus.index import compact


class SourceCallsCliTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name).resolve()
        (self.repo / '.columbus.json').write_bytes(b'{invalid configuration')

    def invoke(self, *options):
        output, error = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = main(['archive-source', 'First', 'Second', '--input', 'unopened.gz',
                         '--repo', str(self.repo), *options])
        return code, output.getvalue(), error.getvalue()

    def test_json_dispatch_preserves_queries_options_and_exact_rendering(self):
        packet = {'source': '한글', 'call_sites': {'semantic_complete': False}}
        with patch('columbus.cli.RepositoryIndex', side_effect=AssertionError('index opened')), \
                patch('columbus.source_calls.source_calls_archive', return_value=packet) as query:
            code, output, error = self.invoke('--call-sites', '--overloads', '--offset', '3',
                                              '--limit', '8', '--budget-bytes', '9000')
        self.assertEqual((code, output, error), (0, compact(packet) + '\n', ''))
        query.assert_called_once_with('unopened.gz', ['First', 'Second'], self.repo, 8, 9000, 3,
                                      output_format='json', overloads=True)
        self.assertFalse((self.repo / '.columbus').exists())

    def test_text_dispatch_uses_module_renderer_without_extra_newline(self):
        packet = {'source': 'x'}
        with patch('columbus.cli.RepositoryIndex', side_effect=AssertionError('index opened')), \
                patch('columbus.source_calls.source_calls_archive', return_value=packet) as query, \
                patch('columbus.source_calls.source_calls_text', return_value='exact\n') as render:
            code, output, error = self.invoke('--call-sites', '--format', 'text')
        self.assertEqual((code, output, error), (0, 'exact\n', ''))
        self.assertEqual(query.call_args.kwargs, {'output_format': 'text', 'overloads': False})
        render.assert_called_once_with(packet)

    def test_unsupported_options_reject_before_source_or_index_access(self):
        for options in [('--db', ''), ('--db', 'existing.sqlite'),
                        ('--telemetry', ''), ('--telemetry', 'events.jsonl'), ('--pretty',)]:
            with self.subTest(options=options), \
                    patch('columbus.cli.RepositoryIndex', side_effect=AssertionError('index opened')), \
                    patch('columbus.source_calls.source_calls_archive') as query:
                code, output, error = self.invoke('--call-sites', *options)
            self.assertEqual(code, 2)
            self.assertEqual(output, '')
            self.assertIn(options[0], error)
            query.assert_not_called()
        self.assertEqual([p.name for p in self.repo.iterdir()], ['.columbus.json'])

    def test_failure_has_no_partial_stdout_and_escapes_untrusted_diagnostic(self):
        message = 'bad\x1b[31m\npath\u2028'
        with patch('columbus.cli.RepositoryIndex', side_effect=AssertionError('index opened')), \
                patch('columbus.source_calls.source_calls_archive', side_effect=ValueError(message)):
            code, output, error = self.invoke('--call-sites')
        self.assertEqual((code, output), (2, ''))
        self.assertEqual(error, 'columbus: ' + json.dumps(message, ensure_ascii=True)[1:-1] + '\n')

    def test_legacy_batch_does_not_dispatch_opt_in_module(self):
        packet = {'targets': [], 'sources': [], 'revision': 'legacy'}
        with patch('columbus.cli.RepositoryIndex'), \
                patch('columbus.archive.source_archive_many', return_value=packet) as legacy, \
                patch('columbus.source_calls.source_calls_archive', side_effect=AssertionError('opt-in invoked')):
            code, output, error = self.invoke()
        self.assertEqual((code, output, error), (0, compact(packet) + '\n', ''))
        legacy.assert_called_once_with('unopened.gz', ['First', 'Second'], self.repo, 120, 12000, 0,
                                       output_format='json', overloads=False)


if __name__ == '__main__':
    unittest.main()
