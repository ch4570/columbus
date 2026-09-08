"""Combine unchanged legacy receipts with independently bound source/call receipts.

Only this new prospective cohort receives the additional recognizer. Historical
receipts, frozen inputs and results are not edited or regraded.
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


def evidence(events, observation, relationships):
    old = LEGACY.evidence(events, observation, relationships)
    combined = SOURCE_CALLS.evidence(events, binding=binding(observation), relationships=relationships)
    relationships_received = old['relationship_receipts'] + combined['relationship_receipts']
    return {**old, 'recognizer_version': VERSION,
            'source_calls_used': bool(combined['source_call_receipts']),
            'source_call_receipts': combined['source_call_receipts'],
            'relationship_receipts': relationships_received,
            'relationship_used': bool(relationships_received)}
