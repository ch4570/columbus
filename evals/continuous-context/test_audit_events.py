import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('audit_events', Path(__file__).with_name('audit_events.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class EventAuditTests(unittest.TestCase):
    def test_complete_continuation_preserves_usage_without_aggregation(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for number in range(2):
                path = Path(directory) / f'{number}.jsonl'
                path.write_text('\n'.join(json.dumps(e) for e in self.events(number)))
                paths.append(path)
            result = m.audit(paths)
            self.assertEqual(2, len(result['captures']))
            self.assertNotIn('total_input_tokens', result)
            self.assertEqual(101, result['captures'][1]['reported_usage']['input_tokens'])

    @staticmethod
    def events(number=0):
        return [{'type': 'thread.started', 'thread_id': '00000000-0000-0000-0000-000000000001'},
                {'type': 'turn.started'}, {'type': 'turn.completed',
                 'usage': {'input_tokens': 100+number, 'cached_input_tokens': 50, 'output_tokens': 10}}]

    def test_rejects_other_thread_incomplete_duplicate_and_invalid_usage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root/'first.jsonl'
            first.write_text('\n'.join(map(json.dumps, self.events())))
            variants = []
            events = self.events(1); events[0]['thread_id'] = '00000000-0000-0000-0000-000000000002'; variants.append(events)
            variants.append(self.events(1)[:-1])
            variants.append(self.events(1)+[{'type': 'turn.started'}])
            events = self.events(1); events[-1]['usage']['cached_input_tokens'] = 999; variants.append(events)
            events = self.events(1); events[-1]['usage']['input_tokens'] = True; variants.append(events)
            variants.append(self.events())
            for n, events in enumerate(variants):
                with self.subTest(variant=n):
                    path=root/f'{n}.jsonl';path.write_text('\n'.join(map(json.dumps, events)))
                    with self.assertRaises(ValueError): m.audit([first,path])


if __name__ == '__main__':
    unittest.main()
