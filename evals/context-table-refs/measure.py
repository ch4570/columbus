"""Replay frozen caller packets, then repaginate with only the new renderer."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import columbus.presentation as old
from columbus.archive import callers_archive

root = Path(__file__).resolve().parents[2]
trial = Path(sys.argv[1])
output = Path(sys.argv[2])
candidate_path = root / 'skills/columbus/scripts/columbus/presentation.py'
spec = importlib.util.spec_from_file_location('candidate_presentation', candidate_path)
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)
assert Path(old.__file__).read_bytes() != candidate_path.read_bytes()
assert (trial / 'runtime/columbus/archive.py').read_bytes() == (root / 'skills/columbus/scripts/columbus/archive.py').read_bytes()
oracle = json.loads((root / 'evals/archive-force-bytes-v3/oracle.json').read_text())
expected = sorted((r['path'], r['qualname'], r['line']) for r in oracle['targets']['force_bytes']['calls'])
actual_pages = json.loads((root / 'evals/archive-force-bytes-v3/actual-pages.json').read_text())['pages']


def decode_check(packet, rendered):
    files, nodes, edges, contexts, source_lines = {}, {}, [], [], []
    section = None
    for line in rendered.splitlines():
        if line.startswith(('files ', 'nodes ', 'edges ')):
            section = line.split()[0]
        elif line.startswith('call_context:'):
            section = 'contexts'
        elif line.startswith('['):
            row = json.loads(line)
            if section == 'files':
                files[row[0]] = row[1:]
            elif section == 'nodes':
                nodes[row[0]] = dict(row[2], path=files[row[1]][0], source_hash=files[row[1]][1])
            elif section == 'edges':
                edges.append(dict(row[3], source=nodes[row[0]]['id'], target=nodes[row[1]]['id'], path=files[row[2]][0]))
        elif section == 'contexts' and line.startswith('{'):
            c = json.loads(line)
            node = nodes[c.pop('source_node')]
            path, digest = files[c.pop('file_number')]
            contexts.append(dict(c, source_id=node['id'], path=path, source_hash=digest))
            source_lines.append([])
        elif section == 'contexts':
            source_lines[-1].append(line)
    assert list(nodes.values()) == packet['nodes']
    assert edges == packet['edges']
    assert contexts == [{k: v for k, v in c.items() if k != 'source'} for c in packet['call_context']]
    assert source_lines == [[f'{n}| {old._line(line)}' for n, line in enumerate(c['source'].split('\n'), c['start_line'])] for c in packet['call_context']]


def pages():
    offset = 0
    packets = []
    sites = []
    while offset is not None:
        packet = callers_archive(trial / 'graph.jsonl.xz', 'django.utils.encoding.force_bytes',
            repo=trial / 'repository', context_lines=12, output_format='text', budget_bytes=30000,
            offset=offset, path='django/*')
        packets.append(packet)
        nodes = {n['id']: n for n in packet['nodes']}
        sites.extend((e['path'], nodes[e['source']]['id'].split('::', 1)[1].rsplit(':', 1)[0], e['line']) for e in packet['edges'])
        offset = packet['next_offset']
    assert sorted(sites) == expected
    return packets


before = pages()
rows = []
for packet, recorded in zip(before, actual_pages, strict=True):
    previous = old.archive_neighbors_text(packet)
    revised = candidate.archive_neighbors_text(packet)
    assert hashlib.sha256(previous.encode()).hexdigest() == recorded['output_sha256']
    decode_check(packet, revised)
    rows.append({'offset': packet['offset'], 'before_bytes': len(previous.encode()),
                 'after_same_packet_bytes': len(revised.encode()), 'contexts': len(packet['call_context'])})
old.archive_neighbors_text = candidate.archive_neighbors_text
after = pages()
for packet in after:
    rendered = old.archive_neighbors_text(packet)
    assert len(rendered.encode()) <= 30000
    decode_check(packet, rendered)
result = {'same_packet_pages': rows, 'all_fields_and_source_display_preserved': True,
          'before_matches_completed_trial_outputs': True, 'complete_oracle_sites': len(expected),
          'new_pages': [{'offset': p['offset'], 'next_offset': p['next_offset'], 'edges': len(p['edges']),
                         'bytes': len(old.archive_neighbors_text(p).encode())} for p in after],
          'candidate_renderer_sha256': hashlib.sha256(candidate_path.read_bytes()).hexdigest(),
          'model_trial': False, 'token_savings_claimed': False}
output.write_text(json.dumps(result, indent=2) + '\n')
print(result)
