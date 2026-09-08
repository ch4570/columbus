"""Temporary, model-free retention fixtures; never inspect actual trial outputs."""
from contextlib import redirect_stderr
from datetime import datetime, timedelta, timezone
import gzip
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / 'evals/quotes-three-arm/retain.py'
spec = importlib.util.spec_from_file_location('quotes_retention_test', SCRIPT)
retention = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retention)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(retention.encoded(value))


def forbidden(*args, **kwargs):
    raise AssertionError('Retention tests cannot start external processes')


class ThreeArmRetentionTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='quotes-retention-test-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.here = self.root / 'cohort'
        self.here.mkdir()
        self.patch(retention, 'HERE', new=self.here)
        self.patch(retention, 'ROOT', new=self.root)
        for name in ('Popen', 'run', 'check_output'):
            self.patch(subprocess, name, side_effect=forbidden)
        for name in ('run.py', 'common.py'):
            (self.here / name).write_bytes(b'fixture-only code marker\n')
        self.hashes = {'fixture.py': retention.digest(b'fixture')}
        self.input_raw = retention.encoded(self.hashes)
        (self.here / 'input-hashes.json').write_bytes(self.input_raw)
        self.patch(retention, 'INPUT_COUNT', new=1)
        self.patch(retention, 'INPUT_SHA256', new=retention.digest(self.input_raw))
        self.clock = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.observation = lambda language, arm: self.root / 'observations' / language / arm
        self.schedule = [(arm, repeat) for repeat in (1, 2) for arm in retention.ARMS]

        def parsed(events):
            return {'turn_failed': any(e.get('type') == 'turn.failed' for e in events),
                    'usage': next((e['usage'] for e in events if e.get('type') == 'turn.completed'), None)}

        self.common = SimpleNamespace(read=lambda path: json.loads(path.read_bytes()),
            sha=lambda path: retention.digest(Path(path).read_bytes()), observation=self.observation,
            schedule=lambda language: self.schedule, argv=lambda output, trial: ['fixture-codex', str(trial)],
            prompt=lambda case, arm, output: 'Fixture prompt π ' + arm + '\n',
            OBSERVE=SimpleNamespace(parse_events=parsed), verify_observation=self.preflight)
        self.patch(retention, 'frozen', return_value=(self.common, self.input_raw, self.hashes, {'fixture.py': 7}))
        self.trial_paths = []
        self.events = {}
        for language in retention.LANGUAGES:
            self.language(language)

    def patch(self, target, name, **kwargs):
        patcher = mock.patch.object(target, name, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def preflight(self, language, arm):
        source = self.observation(language, arm) / 'repository/source.txt'
        return {'passed': True, 'sha256': retention.digest(source.read_bytes())}

    def language(self, language):
        case = {'id': 'fixture-' + language, 'question': 'Fixture', 'findings': []}
        write(self.here / language / 'cases.json', {'cases': [case]})
        (self.here / language / 'SOURCE-REVIEW.md').write_bytes(b'Fixture rubric')
        freezes = {}
        for arm in retention.ARMS:
            output = self.observation(language, arm)
            (output / 'repository').mkdir(parents=True)
            (output / 'repository/source.txt').write_bytes(b'original source\n')
            manifest = {'source_manifest': {'source.txt': self.common.sha(output / 'repository/source.txt')}}
            engine = {'files': {'runtime.py': 'hash'}, 'archive': {'archive_sha256': 'archive-hash'}}
            freezes[arm] = {'manifest': manifest, 'engine': engine}
            for name, value in (('manifest.json', manifest), ('engine.json', engine), ('cases.json', {'cases': [case]})):
                write(output / name, value)
        write(self.here / language / 'freeze.json', freezes)
        preflight = {arm: self.preflight(language, arm) for arm in retention.ARMS}
        group = self.observation(language, 'baseline').parent
        write(group / 'runner.json', {'pid': 100, 'started_at': (self.clock - timedelta(seconds=1)).isoformat(),
              'schedule': self.schedule, 'input_hashes_sha256': retention.INPUT_SHA256})
        write(group / 'runner-terminal.json', {'status': 'all scheduled executions terminated',
              'finished_at': (self.clock + timedelta(seconds=12)).isoformat()})
        for index, (arm, repeat) in enumerate(self.schedule):
            output = self.observation(language, arm)
            trial = output / 'trials' / f"{case['id']}-{arm}-{repeat}"
            trial.mkdir(parents=True)
            self.trial_paths.append(trial)
            prompt = self.common.prompt(case, arm, output).encode()
            (trial / 'prompt.txt').write_bytes(prompt)
            (trial / 'stderr.log').write_bytes(b'raw stderr\r\n')
            write(trial / 'answer.json', {})
            started = self.clock + timedelta(seconds=index * 2)
            write(trial / 'process.json', {'pid': index + 200, 'started_at': started.isoformat()})
            # A failed terminal execution must be preserved without requiring quality success.
            terminal = {'return_code': 1 if index == 0 else 0, 'timed_out': False, 'elapsed_seconds': 1,
                        'finished_at': (started + timedelta(seconds=1)).isoformat()}
            write(trial / 'terminal.json', terminal)
            write(trial / 'invocation.json', {'argv': self.common.argv(output, trial),
                'model_requested': 'gpt-5.6-sol', 'effort_requested': 'xhigh', 'timeout_seconds': 1200,
                'prompt_bytes': len(prompt), 'harness_sha256': self.common.sha(self.here / 'run.py'),
                'common_sha256': self.common.sha(self.here / 'common.py'), 'input_hashes_sha256': retention.INPUT_SHA256})
            events = [{'type': 'turn.failed'}] if index == 0 else [{'type': 'turn.completed',
                      'usage': {'input_tokens': 42, 'cached_input_tokens': 4, 'output_tokens': 7}}]
            raw = b''.join(json.dumps(event).encode() + b'\n' for event in events) + b'\r\n'
            (trial / 'events.jsonl').write_bytes(raw)
            self.events[trial] = raw
            write(trial / 'result.json', {'case': case['id'], 'condition': arm, 'repeat': repeat, **terminal,
                **self.common.OBSERVE.parse_events(events), 'events_sha256': retention.digest(raw),
                'answer': {}, 'preflight': preflight, 'postflight': preflight})

    def capture(self, name='retained', **kwargs):
        output = self.root / name
        result = retention.retain(output, terminal_confirmed=True, **kwargs)
        return output, result

    def test_windows_path_and_fd_ctime_meanings_may_differ_but_both_must_stay_stable(self):
        base = dict(st_dev=1, st_ino=2, st_size=3, st_mtime_ns=4, st_ctime_ns=5)
        path = SimpleNamespace(**base)
        fd = SimpleNamespace(**{**base, 'st_ctime_ns': 9})
        self.assertTrue(retention.unchanged_stats(path, fd, fd, path, windows=True))
        self.assertFalse(retention.unchanged_stats(path, fd, fd, path, windows=False))
        self.assertTrue(retention.unchanged_stats(path, path, path, path, windows=False))
        for position in range(4):
            for field in base:
                with self.subTest(position=position, field=field):
                    snapshots = [path, fd, fd, path]
                    changed = vars(snapshots[position]).copy()
                    changed[field] += 1
                    snapshots[position] = SimpleNamespace(**changed)
                    self.assertFalse(retention.unchanged_stats(*snapshots, windows=True))

    def test_stable_reader_preserves_bytes_with_distinct_windows_fd_ctime(self):
        target = self.root / 'ctime-fixture.json'
        target.write_bytes(b'{"raw":"unchanged"}\r\n')
        real_fstat = retention.os.fstat

        def fd_stat(descriptor):
            actual = real_fstat(descriptor)
            values = {name: getattr(actual, name) for name in
                      ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')}
            values['st_ctime_ns'] += 123456
            return SimpleNamespace(**values)

        with mock.patch.object(retention.sys, 'platform', 'win32'), \
                mock.patch.object(retention.os, 'fstat', side_effect=fd_stat):
            self.assertEqual(retention.stable(target, self.root), b'{"raw":"unchanged"}\r\n')

    def test_all18_and_failed_runs_retained_with_exact_events_and_independent_verify(self):
        output, result = self.capture()
        self.assertTrue(result['verified'])
        self.assertTrue(result['cohort_complete'])
        manifest = json.loads((output / 'RETENTION.json').read_bytes())
        self.assertEqual(len(manifest['trials']), 18)
        self.assertEqual(sum(row['return_code'] == 1 for row in manifest['trials'].values()), 3)
        event_files = [name for name in manifest['files'] if name.endswith('events.jsonl.gz')]
        self.assertEqual(len(event_files), 18)
        for name in event_files:
            original = manifest['files'][name]['original_path']
            self.assertEqual(gzip.decompress((output / name).read_bytes()), Path(original).read_bytes())
        (self.root / 'observations').rename(self.root / 'moved-original-observations')
        self.assertTrue(retention.verify(output)['verified'])

    def test_no_owner_confirmation_or_existing_output_causes_no_write(self):
        output = self.root / 'new'
        with self.assertRaisesRegex(ValueError, 'Owner confirmation'):
            retention.retain(output)
        self.assertFalse(output.exists())
        output.mkdir()
        (output / 'keep').write_bytes(b'untouched')
        with self.assertRaisesRegex(ValueError, 'NEW'):
            retention.retain(output, terminal_confirmed=True)
        self.assertEqual((output / 'keep').read_bytes(), b'untouched')

    def test_default_rejects_missing_result_before_writes_explicit_partial_preserves_raw(self):
        trial = self.trial_paths[0]
        (trial / 'result.json').unlink()
        (trial / 'events.jsonl').write_bytes(b'{malformed original events\x00\r\n')
        (trial.parents[2] / 'runner-terminal.json').unlink()
        output = self.root / 'default'
        with self.assertRaisesRegex(ValueError, 'Complete capture required'):
            retention.retain(output, terminal_confirmed=True)
        self.assertFalse(output.exists())
        output, result = self.capture(allow_incomplete='All original handles closed; parser failure preserved')
        self.assertFalse(result['cohort_complete'])
        manifest = json.loads((output / 'RETENTION.json').read_bytes())
        self.assertEqual(len(manifest['trials']), 18)
        row = manifest['trials']['java/baseline/1']
        self.assertIn('result.json', row['missing_artifacts'])
        self.assertTrue(row['terminal_present'])
        self.assertNotIn('usage', row)
        self.assertNotIn('return_code', row)
        retained = next(name for name, value in manifest['files'].items() if value['original_path'] == str(trial / 'events.jsonl'))
        self.assertEqual(gzip.decompress((output / retained).read_bytes()), b'{malformed original events\x00\r\n')

    def test_absent_slot_and_extra_trial_are_visible_in_incomplete_capture(self):
        missing = self.trial_paths[-1]
        for path in missing.iterdir():
            path.unlink()
        missing.rmdir()
        extra = missing.parent / 'unplanned-attempt'
        extra.mkdir()
        (extra / 'events.jsonl').write_bytes(b'original extra data')
        output, result = self.capture(allow_incomplete='Inspect unplanned and absent evidence')
        self.assertFalse(result['cohort_complete'])
        value = json.loads((output / 'RETENTION.json').read_bytes())
        self.assertEqual(value['trials']['javascript/quotes/2']['missing_artifacts'], sorted(retention.REQUIRED))
        self.assertFalse(value['trials']['javascript/quotes/2']['process_present'])
        self.assertTrue(any('unexpected trial' in issue for issue in value['issues']))
        self.assertTrue(any('/unexpected/unplanned-attempt/events.jsonl' in name for name in value['files']))

    def test_malformed_runner_shape_is_preserved_with_explicit_incomplete_capture(self):
        group = self.observation('java', 'baseline').parent
        write(group / 'runner.json', [])
        output, result = self.capture(allow_incomplete='Original handles closed; malformed runner preserved')
        self.assertFalse(result['cohort_complete'])
        self.assertEqual((output / 'java/runner.json').read_bytes(), (group / 'runner.json').read_bytes())
        self.assertTrue(any('Malformed runner record shape' in issue for issue in result['issues']))

    def test_extra_gzip_named_artifact_cannot_collide_with_compressed_raw_events(self):
        trial = self.trial_paths[0]
        (trial / 'events.jsonl.gz').write_bytes(b'original unexpected gzip-named bytes')
        output, result = self.capture(allow_incomplete='Retain original unexpected artifact without collision')
        self.assertFalse(result['cohort_complete'])
        value = json.loads((output / 'RETENTION.json').read_bytes())
        canonical = 'java/baseline/trials/' + trial.name + '/events.jsonl.gz'
        unexpected = 'java/baseline/unexpected/' + trial.name + '/events.jsonl.gz'
        self.assertEqual(gzip.decompress((output / canonical).read_bytes()), self.events[trial])
        self.assertEqual((output / unexpected).read_bytes(), b'original unexpected gzip-named bytes')
        self.assertNotIn('encoding', value['files'][unexpected])

    def test_derived_trial_summary_must_match_retained_raw_records(self):
        output, _ = self.capture()
        path = output / 'RETENTION.json'
        original = path.read_bytes()
        for field, changed in (('return_code', 999), ('timed_out', True), ('turn_failed', False),
                               ('completed_turns', 7), ('started_at', self.clock.isoformat())):
            with self.subTest(field=field):
                value = json.loads(original)
                row = value['trials']['java/baseline/1']
                if field == 'started_at':
                    changed = (self.clock + timedelta(days=1)).isoformat()
                row[field] = changed
                write(path, value)
                with self.assertRaisesRegex(ValueError, 'summary differs'):
                    retention.verify(output)
        value = json.loads(original)
        value['trials']['java/baseline/1']['terminal']['return_code'] = 999
        write(path, value)
        with self.assertRaisesRegex(ValueError, 'terminal summary differs'):
            retention.verify(output)

    def test_changed_original_during_publication_leaves_rejected_partial_destination(self):
        original_plan = retention.plan

        def changing_plan(*args):
            payloads, manifest, unchanged = original_plan(*args)

            def change():
                (self.trial_paths[0] / 'stderr.log').write_bytes(b'changed during publication')
                unchanged()

            return payloads, manifest, change

        self.patch(retention, 'plan', side_effect=changing_plan)
        output = self.root / 'partial'
        with redirect_stderr(io.StringIO()), self.assertRaisesRegex(ValueError, 'Original evidence changed'):
            retention.retain(output, terminal_confirmed=True)
        self.assertTrue((output / 'INCOMPLETE.json').is_file())
        self.assertFalse((output / 'RETENTION.json').exists())
        self.assertGreater(len(list(output.rglob('*'))), 1)
        with self.assertRaisesRegex(ValueError, 'Capture failed'):
            retention.verify(output)

    def test_mutated_or_extra_retained_files_rejected(self):
        output, _ = self.capture()
        extra = output / 'unexpected'
        extra.write_bytes(b'extra')
        with self.assertRaisesRegex(ValueError, 'extra retained file'):
            retention.verify(output)
        extra.unlink()
        target = next(output.rglob('stderr.log'))
        target.write_bytes(b'edited')
        with self.assertRaisesRegex(ValueError, 'Retained file differs'):
            retention.verify(output)

    def test_report_and_review_only_explicitly_selected_and_hash_bound(self):
        trial = self.trial_paths[0]
        reviews = self.root / 'reviews'
        review = {'answer_sha256': self.common.sha(trial / 'answer.json'),
                  'rubric_sha256': self.common.sha(self.here / 'java/SOURCE-REVIEW.md'),
                  'execution_review': {'events_sha256': self.common.sha(trial / 'events.jsonl'), 'passed': False},
                  'pending': True, 'findings': []}
        path = reviews / 'java/semantic' / (trial.name + '.json')
        write(path, review)
        report = self.root / 'chosen-report.json'
        write(report, {'input_hashes_sha256': retention.INPUT_SHA256, 'experiment_accepted': False})
        output, _ = self.capture(semantic_dir=reviews, report=report)
        value = json.loads((output / 'RETENTION.json').read_bytes())
        self.assertEqual(value['semantic_reviews_retained'], 1)
        self.assertTrue(value['collector_report_requested'])
        self.assertEqual((output / 'collector-report.json').read_bytes(), report.read_bytes())
        write(path, {**review, 'answer_sha256': 'stale'})
        with self.assertRaisesRegex(ValueError, 'Semantic review binding'):
            self.capture(name='bad-review', semantic_dir=reviews)
        self.assertFalse((self.root / 'bad-review').exists())

    def test_frozen_runtime_destination_and_empty_incomplete_reason_rejected(self):
        runtime = self.here / 'runtimes'
        runtime.mkdir()
        with self.assertRaisesRegex(ValueError, 'frozen runtime'):
            retention.retain(runtime / 'new', terminal_confirmed=True)
        with self.assertRaisesRegex(ValueError, 'nonempty reason'):
            retention.retain(self.root / 'new', terminal_confirmed=True, allow_incomplete=' ')

    def test_events_gzip_deterministic_and_unsafe_paths_rejected(self):
        raw = b'\x00exact\r\nUnicode \xe2\x80\xa8\n'
        self.assertEqual(retention.zip_events(raw), retention.zip_events(raw))
        self.assertEqual(gzip.decompress(retention.zip_events(raw)), raw)
        for name in ('', '.', '../a', '/root/file', 'a/../b', './a', 'a\\b', 'C:drive'):
            with self.assertRaises(ValueError):
                retention.relative(name)

    def test_verify_rejects_false_complete_claim_and_empty_extra_directory(self):
        output, _ = self.capture()
        manifest = json.loads((output / 'RETENTION.json').read_bytes())
        manifest['issues'] = ['missing terminal record']
        write(output / 'RETENTION.json', manifest)
        with self.assertRaisesRegex(ValueError, 'completeness claim'):
            retention.verify(output)
        manifest['issues'] = []
        write(output / 'RETENTION.json', manifest)
        (output / 'unlisted-empty-directory').mkdir()
        with self.assertRaisesRegex(ValueError, 'extra retained directory'):
            retention.verify(output)

    def test_selected_report_stale_artifact_binding_rejected_before_any_write(self):
        report = self.root / 'stale-report.json'
        write(report, {'input_hashes_sha256': retention.INPUT_SHA256,
              'trials': {'java/baseline/1': {'artifact_sha256': {'events.jsonl': 'stale'}}}})
        with self.assertRaisesRegex(ValueError, 'report artifact binding'):
            self.capture(report=report)
        self.assertFalse((self.root / 'retained').exists())


if __name__ == '__main__':
    unittest.main()
