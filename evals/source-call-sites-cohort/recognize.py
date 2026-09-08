"""Combine unchanged legacy receipts with independently bound source/call receipts.

Only this new prospective cohort receives the additional recognizer. Historical
receipts, frozen inputs and results are not edited or regraded.

This adapter requires the cohort's authoritative common pre/postflight checks.
When no successful command can be a source/call delivery, it skips that
recognizer's full snapshot load. The standalone recognizer remains strict even
for empty streams; this adapter is not a replacement for frozen-input preflight.
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sys

_COMMON_PATH = Path(__file__).resolve().with_name('common.py')
_COMMON_KEY = '_source_call_cohort_' + hashlib.sha256(str(_COMMON_PATH).encode()).hexdigest()[:16]
if _COMMON_KEY not in sys.modules:
    _SPEC = importlib.util.spec_from_file_location(_COMMON_KEY, _COMMON_PATH)
    _COMMON = importlib.util.module_from_spec(_SPEC)
    sys.modules[_COMMON_KEY] = _COMMON
    _SPEC.loader.exec_module(_COMMON)
common = sys.modules[_COMMON_KEY]

LEGACY = common.module('unchanged_quotes_recognizer', common.HERE.parent / 'quotes-three-arm/recognize.py')
SOURCE_CALLS = common.module('source_calls_recognizer', common.HERE.parent / 'exploration/source_call_evidence.py')
VERSION = 'source-call-sites-cohort-evidence-v1'


def binding(observation):
    observation = Path(observation)
    manifest = common.read(observation / 'manifest.json')
    engine = common.read(observation / 'engine.json')
    frozen = engine['archive']
    common.require(manifest['source_manifest'] == frozen['source_manifest'], 'Source binding differs')
    common.require(engine['files'] == frozen['runtime_manifest'], 'Runtime binding differs')
    return {'repository': observation / 'repository', 'archive': observation / 'graph.jsonl.xz',
            'invocation_prefix': (sys.executable, '-B', str(observation / 'runtime/columbus.py')),
            'archive_sha256': frozen['archive_sha256'], 'runtime_inventory': engine['files'],
            'source_manifest': manifest['source_manifest'], 'revision': frozen['revision']}


def _has_source_call_candidate(events, prefix):
    """Necessary conditions only: false positives still receive full validation."""
    for event in events:
        if not isinstance(event, dict) or event.get('type') != 'item.completed':
            continue
        item = event.get('item')
        if (not isinstance(item, dict) or item.get('type') != 'command_execution'
                or not isinstance(item.get('id'), str) or not item['id']
                or item.get('status') != 'completed' or type(item.get('exit_code')) is not int
                or item['exit_code'] != 0):
            continue
        try:
            words = SOURCE_CALLS._shell_words(item['command'])
            if words and Path(words[0]).name in {'sh', 'bash', 'zsh'}:
                if len(words) != 3 or words[1] not in {'-c', '-lc'}:
                    continue
                words = SOURCE_CALLS._shell_words(words[2])
            if (tuple(words[:3]) == tuple(prefix) and 'archive-source' in words[3:]
                    and '--call-sites' in words[3:]):
                return True
        except SOURCE_CALLS._ERRORS:
            continue
    return False


def evidence(events, observation, relationships):
    # Materialize once so the legacy pass cannot consume a one-shot stream.
    events = list(events)
    old = LEGACY.evidence(events, observation, relationships)
    frozen = binding(observation)
    combined = {'source_call_receipts': [], 'relationship_receipts': []}
    if _has_source_call_candidate(events, frozen['invocation_prefix']):
        combined = SOURCE_CALLS.evidence(events, binding=frozen, relationships=relationships)
    relationships_received = old['relationship_receipts'] + combined['relationship_receipts']
    return {**old, 'recognizer_version': VERSION,
            'source_calls_used': bool(combined['source_call_receipts']),
            'source_call_receipts': combined['source_call_receipts'],
            'relationship_receipts': relationships_received,
            'relationship_used': bool(relationships_received)}
