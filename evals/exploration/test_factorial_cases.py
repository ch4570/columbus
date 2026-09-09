"""Fault-oriented checks for the synthetic factorial fixture and quality oracle."""
import copy
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('factorial_cases', HERE / 'factorial_cases.py')
factorial_cases = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(factorial_cases)


class FactorialCaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'synthetic repository'
        self.root.mkdir()
        factorial_cases.build_fixture(self.root)
        self.cases = factorial_cases.cases()

    def answer(self, case):
        explanations = {
            'retry-calculation': 'Retry is allowed when retryable and attempt < 4; '
                                 'the delay is 2 ** attempt; otherwise return None.',
            'checkout-dispatch': 'The constructor supplies the gateway used by gateway.charge(sku).',
            'gateway-contract': 'The interface declares charge without specifying a concrete implementation.',
            'reflective-construction': 'The runtime className selects Class.forName(className), '
                                       'which constructs a gateway through its no-argument constructor.',
            'python-indirect-route': 'ROUTES[name] selects the handler that handler(payload) invokes.',
        }
        findings = []
        for expected in case['findings']:
            oracle = expected['oracle']
            findings.append({
                'id': expected['id'],
                **{key: oracle[key] for key in ('path', 'start_line', 'end_line', 'quote')},
                'explanation': explanations.get(expected['id'],
                    'The function returns ' + oracle['facts'].get('return_value', '') + '.'),
                'facts': [{'key': key, 'value': value} for key, value in oracle['facts'].items()],
            })
        return {'findings': findings, 'complete': case['expected_complete'],
                'limitations': list(case['required_limitations'])}

    def grade(self, answer, case=None):
        return factorial_cases.grade(answer, self.cases[0] if case is None else case, self.root)

    def inventory(self, root=None):
        root = self.root if root is None else root
        return {path.relative_to(root).as_posix(): path.read_bytes()
                for path in root.rglob('*') if path.is_file()}

    def test_fixture_is_reproducible_with_25_targets_and_200_distractors(self):
        another = Path(self.temporary.name) / 'second'
        another.mkdir()
        factorial_cases.build_fixture(another)
        files = self.inventory()
        self.assertEqual(files, self.inventory(another))
        self.assertEqual(len(files), 230)
        self.assertEqual(sum(path.startswith('commerce/') for path in files), 25)
        self.assertEqual(sum(path.startswith('catalog/') for path in files), 200)
        self.assertEqual(sum(b'def checkout_rule():' in data for data in files.values()), 25)
        self.assertTrue(all(path.endswith(('.py', '.java')) for path in files))

    def test_builder_refuses_missing_nonempty_and_symlink_roots_without_writes(self):
        before = self.inventory()
        with self.assertRaisesRegex(ValueError, 'empty'):
            factorial_cases.build_fixture(self.root)
        self.assertEqual(self.inventory(), before)
        absent = Path(self.temporary.name) / 'absent'
        with self.assertRaises(ValueError):
            factorial_cases.build_fixture(absent)
        self.assertFalse(absent.exists())
        target = Path(self.temporary.name) / 'empty-target'
        target.mkdir()
        linked = Path(self.temporary.name) / 'linked-root'
        try:
            linked.symlink_to(target, target_is_directory=True)
        except OSError:
            self.skipTest('Symlinks unavailable on this platform')
        with self.assertRaises(ValueError):
            factorial_cases.build_fixture(linked)
        self.assertEqual(list(target.iterdir()), [])

    def test_catalog_is_json_serializable_fresh_and_exposes_public_fact_requirements(self):
        self.assertEqual(json.loads(json.dumps(self.cases)), self.cases)
        self.assertEqual([len(case['findings']) for case in self.cases], [1, 25, 4])
        self.assertEqual(len({case['id'] for case in self.cases}), 3)
        for case in self.cases:
            for finding in case['findings']:
                for key in finding['oracle']['facts']:
                    self.assertIn(key, finding['description'])
        self.cases[0]['findings'][0]['oracle']['facts']['otherwise'] = 'mutated'
        self.assertEqual(factorial_cases.cases()[0]['findings'][0]['oracle']['facts']['otherwise'], 'None')

    def test_answer_schema_closes_every_object_and_uses_key_value_fact_arrays(self):
        schema = factorial_cases.ANSWER_SCHEMA
        self.assertEqual(json.loads(json.dumps(schema)), schema)

        def visit(node):
            if node.get('type') == 'object':
                self.assertIs(node.get('additionalProperties'), False)
                self.assertEqual(set(node['required']), set(node['properties']))
                for value in node['properties'].values():
                    visit(value)
            if node.get('type') == 'array':
                visit(node['items'])

        visit(schema)
        facts = schema['properties']['findings']['items']['properties']['facts']
        self.assertEqual(facts['type'], 'array')
        self.assertEqual(set(facts['items']['properties']), {'key', 'value'})

    def test_all_complete_source_grounded_answers_pass_without_writing_fixture(self):
        before = self.inventory()
        for case in self.cases:
            with self.subTest(case=case['id']):
                grade = self.grade(self.answer(case), case)
                self.assertTrue(grade['passed'], grade['reasons'])
                self.assertIs(grade['prose_review_required'], True)
                self.assertEqual(grade['checked_findings'], len(case['findings']))
                self.assertEqual(grade['required_findings'], len(case['findings']))
        self.assertEqual(self.inventory(), before)

    def test_known_range_uses_physical_crlf_cr_lf_and_keeps_unicode_inside_line(self):
        source = (self.root / 'billing/retry.py').read_bytes().decode('utf-8')
        self.assertIn('\r\n', source)
        self.assertIn('\r', source.replace('\r\n', ''))
        self.assertIn('\n', source.replace('\r\n', ''))
        lines = re.split(r'\r\n|\r|\n', source)
        self.assertEqual(lines[20], 'def retry_delay(attempt, retryable):')
        self.assertIn('\u0085\u2028\u2029', lines[21])
        self.assertEqual(lines[24], '    return 2 ** attempt')
        answer = self.answer(self.cases[0])
        self.assertEqual(answer['findings'][0]['quote'], '\n'.join(lines[20:25]))
        self.assertTrue(self.grade(answer)['passed'])

    def test_unicode_splitlines_line_numbers_do_not_pass_as_physical_positions(self):
        source = (self.root / 'billing/retry.py').read_bytes().decode('utf-8')
        naive_start = source.splitlines().index('def retry_delay(attempt, retryable):') + 1
        self.assertGreater(naive_start, 21)
        answer = self.answer(self.cases[0])
        answer['findings'][0].update(start_line=naive_start, end_line=naive_start + 4)
        grade = self.grade(answer)
        self.assertFalse(grade['passed'])
        self.assertIn('physical source range', ' '.join(grade['reasons']))

    def test_wrong_function_path_range_and_noninteger_positions_are_rejected(self):
        for update in ({'path': 'billing/missing.py'}, {'path': '../outside.py'},
                       {'path': str(self.root / 'billing/retry.py')},
                       {'start_line': 27, 'end_line': 28,
                        'quote': 'def retry_delay_decoy(attempt):\n    return 999'},
                       {'start_line': 20}, {'end_line': 26}, {'start_line': True},
                       {'start_line': 21.0}, {'end_line': '25'}):
            with self.subTest(update=update):
                answer = self.answer(self.cases[0])
                answer['findings'][0].update(update)
                self.assertFalse(self.grade(answer)['passed'])

    def test_quotes_must_preserve_indentation_unicode_and_every_cited_line(self):
        good = self.answer(self.cases[0])['findings'][0]['quote']
        for wrong in (good.replace('    ', ''), good.replace('\u2028', '\n'),
                      good.replace('\u0085', ''), good.replace('        return None', '        ...'),
                      good + '\n', 'def retry_delay(attempt, retryable):'):
            with self.subTest(quote=wrong):
                answer = self.answer(self.cases[0])
                answer['findings'][0]['quote'] = wrong
                self.assertFalse(self.grade(answer)['passed'])

    def test_structured_fact_truth_is_required_even_with_correct_quote_and_prose(self):
        for key, value in (('delay_seconds', '3 ** attempt'), ('otherwise', '0'),
                           ('retry_allowed_when', 'not retryable or attempt >= 4')):
            with self.subTest(key=key):
                answer = self.answer(self.cases[0])
                for fact in answer['findings'][0]['facts']:
                    if fact['key'] == key:
                        fact['value'] = value
                grade = self.grade(answer)
                self.assertFalse(grade['passed'])
                self.assertIn('source semantics', ' '.join(grade['reasons']))

    def test_observed_nul_prefixed_unicode_corruption_fails_despite_correct_facts(self):
        for replace_all in (False, True):
            answer = self.answer(self.cases[0])
            quote = answer['findings'][0]['quote'].replace('\u0085', '\x00' + '85')
            if replace_all:
                quote = quote.replace('\u2028', '\x00' + '28').replace('\u2029', '\x00' + '29')
            answer['findings'][0]['quote'] = quote
            result = self.grade(answer)
            self.assertFalse(result['passed'])
            self.assertTrue(any('quotation' in reason for reason in result['reasons']))
            self.assertFalse(any('structured facts' in reason for reason in result['reasons']))

    def test_missing_duplicate_unknown_and_untyped_fact_records_are_rejected(self):
        expected = self.answer(self.cases[0])['findings'][0]['facts']
        for facts in ([], expected[:-1], [*expected, expected[0]],
                      [*expected, {'key': 'invented', 'value': 'assertion'}],
                      [{'key': 'otherwise', 'value': None}], {'otherwise': 'None'},
                      [{'key': [], 'value': 'None'}],
                      [{**expected[0], 'extra': 'unsupported'}, *expected[1:]]):
            with self.subTest(facts=facts):
                answer = self.answer(self.cases[0])
                answer['findings'][0]['facts'] = facts
                self.assertFalse(self.grade(answer)['passed'])

    def test_paraphrased_prose_is_not_rejected_by_keyword_matching_and_needs_review(self):
        answer = self.answer(self.cases[0])
        answer['findings'][0]['explanation'] = (
            'Eligible retries below the cutoff wait an exponentially increasing number of seconds; '
            'ineligible requests receive no delay value.')
        grade = self.grade(answer)
        self.assertTrue(grade['passed'], grade['reasons'])
        self.assertIs(grade['prose_review_required'], True)

    def test_empty_prose_fails_and_machine_pass_never_substitutes_for_prose_review(self):
        for explanation in ('', '  \n ', None):
            answer = self.answer(self.cases[0])
            answer['findings'][0]['explanation'] = explanation
            grade = self.grade(answer)
            self.assertFalse(grade['passed'])
            self.assertIs(grade['prose_review_required'], True)
        answer = self.answer(self.cases[0])
        answer['findings'][0]['explanation'] = 'This unrelated claim must be checked by the separate reviewer.'
        grade = self.grade(answer)
        self.assertTrue(grade['passed'])
        self.assertIs(grade['prose_review_required'], True)

    def test_contiguous_context_surrounding_required_evidence_is_accepted(self):
        for case, finding_id, start, end in (
                (self.cases[0], 'retry-calculation', 20, 26),
                (self.cases[2], 'checkout-dispatch', 1, 9)):
            with self.subTest(case=case['id']):
                answer = self.answer(case)
                finding = next(item for item in answer['findings'] if item['id'] == finding_id)
                source = (self.root / finding['path']).read_bytes().decode('utf-8')
                lines = re.split(r'\r\n|\r|\n', source)
                finding.update(start_line=start, end_line=end, quote='\n'.join(lines[start - 1:end]))
                grade = self.grade(answer, case)
                self.assertTrue(grade['passed'], grade['reasons'])

    def test_surrounding_context_still_requires_whole_quote_and_40_line_limit(self):
        answer = self.answer(self.cases[2])
        finding = answer['findings'][0]
        finding.update(start_line=1, end_line=9)
        self.assertFalse(self.grade(answer, self.cases[2])['passed'])
        answer = self.answer(self.cases[0])
        answer['findings'][0].update(start_line=1, end_line=41)
        self.assertFalse(self.grade(answer)['passed'])

    def test_public_prompts_define_completeness_without_revealing_expected_boolean(self):
        case = self.cases[2]
        public = json.dumps({'question': case['question'], 'findings': [
            {key: finding[key] for key in ('id', 'description')} for finding in case['findings']],
            'schema': factorial_cases.ANSWER_SCHEMA})
        self.assertNotIn('complete=false', public)
        self.assertNotIn('False for', public)
        self.assertNotIn('expected_complete', public)
        self.assertNotIn('oracle', public)

    def test_first_20_candidates_never_pass_and_missing_ids_are_reported(self):
        case = self.cases[1]
        for complete in (True, False):
            with self.subTest(complete=complete):
                answer = self.answer(case)
                answer['findings'] = answer['findings'][:20]
                answer['complete'] = complete
                grade = self.grade(answer, case)
                self.assertFalse(grade['passed'])
                reasons = ' '.join(grade['reasons'])
                for number in range(20, 25):
                    self.assertIn(f'checkout-rule-{number:02}', reasons)

    def test_well_spread_missing_candidates_cannot_be_replaced_by_duplicates(self):
        case = self.cases[1]
        answer = self.answer(case)
        for index in (1, 12, 24):
            answer['findings'][index] = copy.deepcopy(answer['findings'][0])
        grade = self.grade(answer, case)
        self.assertFalse(grade['passed'])
        reasons = ' '.join(grade['reasons'])
        self.assertIn('duplicate', reasons)
        for number in (1, 12, 24):
            self.assertIn(f'checkout-rule-{number:02}', reasons)

    def test_all_broad_candidates_need_their_own_source_return_value(self):
        case = self.cases[1]
        answer = self.answer(case)
        answer['findings'][24]['facts'][0]['value'] = 'checkout-00-allowed'
        self.assertFalse(self.grade(answer, case)['passed'])
        answer = self.answer(case)
        answer['findings'][24]['path'] = answer['findings'][0]['path']
        answer['findings'][24]['quote'] = answer['findings'][0]['quote']
        self.assertFalse(self.grade(answer, case)['passed'])

    def test_partial_dispatch_needs_false_complete_and_both_explicit_limitations(self):
        case = self.cases[2]
        good = self.answer(case)
        self.assertFalse(good['complete'])
        self.assertTrue(self.grade(good, case)['passed'])
        for update in ({'complete': True}, {'complete': 0}, {'limitations': []},
                       {'limitations': good['limitations'][:1]},
                       {'limitations': [*good['limitations'], 'all-callees-independent']},
                       {'limitations': [*good['limitations'], good['limitations'][0]]}):
            with self.subTest(update=update):
                answer = self.answer(case)
                answer.update(update)
                self.assertFalse(self.grade(answer, case)['passed'])

    def test_partial_analysis_still_requires_every_jvm_and_python_evidence_item(self):
        case = self.cases[2]
        for missing in range(len(case['findings'])):
            answer = self.answer(case)
            removed = answer['findings'].pop(missing)
            grade = self.grade(answer, case)
            self.assertFalse(grade['passed'])
            self.assertIn(removed['id'], ' '.join(grade['reasons']))

    def test_partial_graph_does_not_authorize_inventing_a_concrete_implementation(self):
        case = self.cases[2]
        answer = self.answer(case)
        contract = next(finding for finding in answer['findings'] if finding['id'] == 'gateway-contract')
        next(fact for fact in contract['facts'] if fact['key'] == 'concrete_implementation')['value'] = 'StripeGateway'
        self.assertFalse(self.grade(answer, case)['passed'])

    def test_changed_missing_or_symlink_source_cannot_validate_an_oracle_quote(self):
        case = self.cases[0]
        path = self.root / case['findings'][0]['oracle']['path']
        original = path.read_bytes()
        path.write_bytes(original + b'# changed fixture\n')
        self.assertFalse(self.grade(self.answer(case))['passed'])
        path.unlink()
        self.assertFalse(self.grade(self.answer(case))['passed'])
        outside = Path(self.temporary.name) / 'outside.py'
        outside.write_bytes(original)
        try:
            path.symlink_to(outside)
        except OSError:
            self.skipTest('Symlinks unavailable on this platform')
        self.assertFalse(self.grade(self.answer(case))['passed'])
        self.assertEqual(outside.read_bytes(), original)

    def test_malformed_answers_fail_without_exceptions(self):
        good = self.answer(self.cases[0])
        for answer in (None, [], 'not-json', {}, {'findings': []},
                       {**good, 'extra': True}, {**good, 'complete': 1},
                       {**good, 'findings': None}, {**good, 'findings': [None]},
                       {**good, 'limitations': [{}]}, {**good, 'limitations': None},
                       {**good, 'findings': [{**good['findings'][0], 'id': []}]},
                       {**good, 'findings': [{**good['findings'][0], 'id': 'invented-id'}]}):
            with self.subTest(answer=answer):
                grade = self.grade(answer)
                self.assertFalse(grade['passed'])
                self.assertTrue(grade['reasons'])


if __name__ == '__main__':
    unittest.main()
