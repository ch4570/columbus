#!/usr/bin/env python3
"""Publish reviewed measurements without reasoning transcripts or local account paths."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

from factorial import summarize
from factorial_metrics import parse_events, summarize_attempts
from observe import manifest


def publish(output: Path, destination: Path, *, pilot: Path | None = None) -> dict:
    """Keep failures and hashes, but leave raw event/stderr transcripts local."""
    report = summarize(output)
    roots = [(str(output), '$RUN')]
    if pilot is not None:
        # A pilot may use an earlier frozen parser. Its archived summary preserves
        # that interpretation; never silently relabel it as a controlled trial.
        pilot_summary = json.loads((pilot / 'summary.json').read_text(encoding='utf-8'))
        if manifest(pilot / 'repository') != pilot_summary['manifest']['source_manifest']:
            raise ValueError('Pilot source snapshot changed')
        for record in pilot_summary['attempts']:
            directory = pilot / 'trials' / record['attempt_id']
            sealed = json.loads((directory / 'capture.json').read_text())
            required = {'attempt.json', 'result.json', 'events.jsonl', 'prompt.txt', 'stderr.log'}
            if set(sealed) not in (required, required | {'answer.json'}):
                raise ValueError('Invalid pilot capture inventory')
            if any(sha256((directory / name).read_bytes()).hexdigest() != digest for name, digest in sealed.items()):
                raise ValueError('Pilot captured evidence changed')
            captured = json.loads((directory / 'result.json').read_text())
            if any(record.get(key) != value for key, value in captured.items() if key not in {'quality', 'success'}):
                raise ValueError('Pilot derived measurements differ from its capture')
            review = record.get('prose_review', {})
            if record['success'] and (not captured['success'] or review.get('passed') is not True or
                    review.get('answer_sha256') != sha256(json.dumps(record['answer'], sort_keys=True, ensure_ascii=False).encode()).hexdigest()):
                raise ValueError('Pilot success lacks its answer-bound review')
            events = directory / 'events.jsonl'
            if sha256(events.read_bytes()).hexdigest() != record['events_sha256']:
                raise ValueError('Pilot raw event evidence changed')
            observed = parse_events([json.loads(line) for line in events.read_text().split('\n') if line.strip()])
            for key in ('input_tokens', 'cached_input_tokens', 'output_tokens'):
                if (record.get('usage') or {}).get(key) != (observed.get('usage') or {}).get(key):
                    raise ValueError('Pilot token counts disagree with raw events')
            record['usage_with_current_aliases'] = observed['usage']
        pilot_summary['totals'] = summarize_attempts(pilot_summary['attempts'])
        report['instrumentation_pilot'] = pilot_summary
        roots.append((str(pilot), '$PILOT'))
    report['publication'] = {
        'scope': 'All controlled attempts plus separately identified instrumentation pilot; no reasoning transcripts.',
        'paths': 'Absolute local runtime paths are display labels, not executable replay commands.',
        'raw_evidence': 'Original captures, frozen protocol/engine/source and private archive retained locally; hashes preserved.',
        'billing': 'No account rate or provider bill supplied; cost_per_successful_task remains unknown.',
        'overhead': 'Engineering and independent prose-review agent usage is not exposed by this CLI cohort and is excluded; '
                    'the full research bill is unknown, not the sum of reported cohort tokens alone.'}
    notes = output / 'observer-notes.json'
    report['observer_notes'] = json.loads(notes.read_text()) if notes.exists() else {}
    for contrast, amortization in report.get('elapsed_amortization', {}).items():
        tool_arm = contrast.split('-')[1]
        used = any(record.get('arm') == tool_arm and record.get('columbus_commands', 0) > 0
                   for record in report['attempts'])
        if not used:
            amortization['unattributed_formula_reuse_count'] = amortization['reuse_count_for_elapsed_break_even']
            amortization['reuse_count_for_elapsed_break_even'] = None
            amortization['note'] = ('No Columbus command was observed in this tool arm. Wall-time differences '
                                    'cannot establish index reuse/payback; the raw formula is retained separately, not endorsed.')
    all_attempts = [*report['attempts'], *report.get('instrumentation_pilot', {}).get('attempts', [])]
    report['all_observed_model_calls'] = {
        'attempts': len(all_attempts),
        'unknown_usage_attempts': sum(not record.get('usage_complete') for record in all_attempts),
        'known_reported_usage': {key: sum((record.get('usage') or {}).get(key, 0) or 0 for record in all_attempts)
                                 for key in ('input_tokens', 'cached_input_tokens', 'output_tokens')},
        'note': 'Reported counters include the instrumentation pilot and failures with reported usage. '
                'If any usage is missing these are partial sums, not complete totals or a billing estimate.'}
    # Serialized metadata includes prompts/commands and answers, but never raw
    # event text. Replacement cannot weaken the original answer/source hashes.
    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    replacements = [(sys.executable, '$PYTHON'), (str(Path(sys.executable).resolve()), '$PYTHON'),
                    *roots, (str(Path(__file__).resolve().parents[2]), '$CHECKOUT')]
    for original, label in sorted(replacements, key=lambda pair: len(pair[0]), reverse=True):
        encoded = encoded.replace(json.dumps(original, ensure_ascii=False)[1:-1], label)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(encoded + '\n')
    return {'output': str(destination), 'attempts': len(report['attempts']),
            'pilot_attempts': len(report.get('instrumentation_pilot', {}).get('attempts', []))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--destination', required=True, type=Path)
    parser.add_argument('--pilot', type=Path)
    args = parser.parse_args()
    print(json.dumps(publish(args.output.expanduser().resolve(), args.destination.expanduser().absolute(),
                             pilot=args.pilot.expanduser().resolve() if args.pilot else None)))


if __name__ == '__main__':
    main()
