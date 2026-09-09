#!/usr/bin/env python3
"""Publish reviewed measurements without reasoning transcripts or local account paths."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shlex
import sys

from factorial import summarize
from factorial_metrics import parse_events, summarize_attempts
from observe import manifest


def _display_paths(value, replacements):
    """Redact string values; normalize path separators only outside free text."""
    replacements = sorted(replacements, key=lambda pair: len(pair[0]), reverse=True)

    def replace(item, *, free_text=False):
        if isinstance(item, dict):
            return {key: replace(child, free_text=free_text or key in {'command', 'commands', 'prompt', 'answer',
                                                                       'quote', 'explanation', 'note', 'notes'})
                    for key, child in item.items()}
        if isinstance(item, list):
            return [replace(child, free_text=free_text) for child in item]
        if not isinstance(item, str):
            return item
        for original, label in replacements:
            if item == original:
                return label
            if not free_text and item.startswith(original + '\\'):
                return label + item[len(original):].replace('\\', '/')
        for original, label in replacements:
            item = item.replace(original, label)
        return item

    return replace(value)


def _recorded_paths(report, label):
    """Recover exact runtime prefixes from recorded metadata and command argv."""
    replacements = []

    def absolute(value):
        if not isinstance(value, str):
            return None
        path = PureWindowsPath(value) if PureWindowsPath(value).is_absolute() else PurePosixPath(value)
        return path if path.is_absolute() and path.name else None

    def add(value, replacement):
        if path := absolute(str(value)):
            replacements.extend((original, replacement) for original in {str(value), str(path), path.as_posix()})

    def command_paths(command, depth=0):
        variants = [command] if isinstance(command, list) else []
        if isinstance(command, str):
            try:
                variants.append(shlex.split(command))
                # Keep quotes so a quoted ";" or Python source is never treated
                # as a shell boundary. We only inspect command-start tokens;
                # the original command text is not rebuilt from these tokens.
                lexer = shlex.shlex(command, posix=False, punctuation_chars=';&|\n')
                lexer.whitespace = ' \t\r'
                lexer.whitespace_split = True
                segment = []
                for token in lexer:
                    if token and set(token) <= set(';&|\n'):
                        variants.append(segment)
                        segment = []
                    else:
                        segment.append(token)
                variants.append(segment)
            except ValueError:
                pass
        for argv in variants:
            if not argv or not all(isinstance(arg, str) for arg in argv):
                continue
            position = 0
            while position < len(argv) and re.match(r'^[A-Za-z_][A-Za-z_0-9]*=', argv[position]):
                position += 1
            if position < len(argv) and PurePosixPath(argv[position].strip('\'"')).name == 'env':
                position += 1
                while position < len(argv):
                    option = argv[position]
                    if option in {'-u', '--unset', '-C', '--chdir'}:
                        position += 2
                    elif (option in {'-i', '--ignore-environment', '--'} or
                          option.startswith(('--unset=', '--chdir=')) or
                          re.match(r'^[A-Za-z_][A-Za-z_0-9]*=', option)):
                        position += 1
                    else:
                        break
            argv = argv[position:]
            if not argv:
                continue
            executable = argv[0].strip('\'"')
            path = absolute(executable)
            if path and re.fullmatch(r'python(?:\d+(?:\.\d+)*)?(?:\.exe)?', path.name, re.IGNORECASE):
                add(executable, '$PYTHON')
            elif path and path.name.lower() in {'codex', 'codex.exe'}:
                add(executable, '$CODEX')
            if depth == 0 and path and path.name in {'sh', 'bash', 'zsh'}:
                for option, script in zip(argv, argv[1:]):
                    if option in {'-c', '-lc'}:
                        command_paths(script, depth=1)

    metadata = report.get('manifest', {})
    for container in (metadata, metadata.get('engine', {}), metadata.get('protocol', {})):
        if not isinstance(container, dict):
            continue
        for key in ('python', 'resolved_python'):
            add(container.get(key), '$PYTHON')
        add(container.get('checkout'), '$CHECKOUT')
        repository = absolute(container.get('repository'))
        if repository and repository.name == 'repository':
            add(repository.parent, label)
        command_paths(container.get('command'))
    for record in report['attempts']:
        argv = record.get('invocation', [])
        if isinstance(argv, list):
            command_paths(argv)
            for option, value in zip(argv, argv[1:]):
                path = absolute(value)
                if path is None:
                    continue
                if option == '--output-schema' and path.name == 'answer.schema.json':
                    add(path.parent, label)
                elif (option, path.name) in {('-C', 'scratch'), ('--output-last-message', 'answer.json')}:
                    if path.parent.parent.name == 'trials':
                        add(path.parents[2], label)
                elif option == '--add-dir' and path.parts[-3:] == ('repository', '.columbus', 'sessions'):
                    add(path.parents[2], label)
        for command in record.get('commands', []):
            command_paths(command.get('command') if isinstance(command, dict) else command)
    return replacements


def publish(output: Path, destination: Path, *, pilot: Path | None = None) -> dict:
    """Keep failures and hashes, but leave raw event/stderr transcripts local."""
    if pilot is not None and pilot.resolve() == output.resolve():
        raise ValueError('Pilot must be a distinct cohort, not the controlled observation directory')
    report = summarize(output)
    roots = [(str(output), '$RUN'), *_recorded_paths(report, '$RUN')]
    if pilot is not None:
        # A pilot may use an earlier frozen parser. Its archived summary preserves
        # that interpretation; never silently relabel it as a controlled trial.
        pilot_summary = json.loads((pilot / 'summary.json').read_text(encoding='utf-8'))
        if manifest(pilot / 'repository') != pilot_summary['manifest']['source_manifest']:
            raise ValueError('Pilot source snapshot changed')
        records = pilot_summary['attempts']
        identifiers = [record.get('attempt_id') for record in records if isinstance(record, dict)]
        trials = pilot / 'trials'
        directories = list(trials.iterdir()) if trials.exists() else []
        if (len(identifiers) != len(records) or
                any(not isinstance(identifier, str) or not identifier or identifier in {'.', '..'} or
                    '/' in identifier or '\\' in identifier for identifier in identifiers) or
                len(set(identifiers)) != len(identifiers) or
                set(identifiers) != {directory.name for directory in directories} or
                any(directory.is_symlink() or not directory.is_dir() or not (directory / 'attempt.json').is_file()
                    for directory in directories)):
            raise ValueError('Pilot attempt inventory differs from its summary')
        for record in pilot_summary['attempts']:
            directory = pilot / 'trials' / record['attempt_id']
            sealed = json.loads((directory / 'capture.json').read_text(encoding='utf-8'))
            required = {'attempt.json', 'result.json', 'events.jsonl', 'prompt.txt', 'stderr.log'}
            if set(sealed) not in (required, required | {'answer.json'}):
                raise ValueError('Invalid pilot capture inventory')
            if any(sha256((directory / name).read_bytes()).hexdigest() != digest for name, digest in sealed.items()):
                raise ValueError('Pilot captured evidence changed')
            started = json.loads((directory / 'attempt.json').read_text(encoding='utf-8'))
            captured = json.loads((directory / 'result.json').read_text(encoding='utf-8'))
            if (started.get('attempt_id') != directory.name or
                    any(captured.get(key) != value for key, value in started.items())):
                raise ValueError('Pilot started attempt differs from its directory or result')
            if any(record.get(key) != value for key, value in captured.items() if key not in {'quality', 'success'}):
                raise ValueError('Pilot derived measurements differ from its capture')
            review = record.get('prose_review', {})
            if record['success'] and (not captured['success'] or review.get('passed') is not True or
                    review.get('answer_sha256') != sha256(json.dumps(record['answer'], sort_keys=True, ensure_ascii=False).encode()).hexdigest()):
                raise ValueError('Pilot success lacks its answer-bound review')
            events = directory / 'events.jsonl'
            if sha256(events.read_bytes()).hexdigest() != record['events_sha256']:
                raise ValueError('Pilot raw event evidence changed')
            observed = parse_events([json.loads(line) for line in events.read_text(encoding='utf-8').split('\n') if line.strip()])
            for key in ('input_tokens', 'cached_input_tokens', 'output_tokens'):
                if (record.get('usage') or {}).get(key) != (observed.get('usage') or {}).get(key):
                    raise ValueError('Pilot token counts disagree with raw events')
            record['usage_with_current_aliases'] = observed['usage']
        pilot_summary['totals'] = summarize_attempts(pilot_summary['attempts'])
        report['instrumentation_pilot'] = pilot_summary
        roots.extend([(str(pilot), '$PILOT'), *_recorded_paths(pilot_summary, '$PILOT')])
    report['publication'] = {
        'scope': 'All controlled attempts plus separately identified instrumentation pilot; no reasoning transcripts.',
        'paths': 'Absolute local runtime paths are display labels, not executable replay commands.',
        'raw_evidence': 'Original captures, frozen protocol/engine/source and private archive retained locally; hashes preserved.',
        'billing': 'No account rate or provider bill supplied; cost_per_successful_task remains unknown.',
        'overhead': 'Engineering and independent prose-review agent usage is not exposed by this CLI cohort and is excluded; '
                    'the full research bill is unknown, not the sum of reported cohort tokens alone.'}
    notes = output / 'observer-notes.json'
    report['observer_notes'] = json.loads(notes.read_text(encoding='utf-8')) if notes.exists() else {}
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
    # Metadata includes prompts/commands and answers, but never raw event text.
    # Redact before JSON escaping, preserving source and regex backslashes.
    replacements = [(sys.executable, '$PYTHON'), (str(Path(sys.executable).resolve()), '$PYTHON'),
                    *roots, (str(Path(__file__).resolve().parents[2]), '$CHECKOUT')]
    encoded = json.dumps(_display_paths(report, replacements), ensure_ascii=False, indent=2)
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
