"""Observe an installed Java grammar without rewriting source or runtime pins."""
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys
from columbus.jvm import parse_jvm
import tree_sitter_java
from tree_sitter import Language, Parser

root = Path(sys.argv[1])
output = Path(sys.argv[2])
fixtures = {
    'primitive': 'class C { void run(int @A ... values) {} }',
    'array': 'class C { void run(int @A [] @B ... values) {} }',
    'generic': 'class C { void run(@A Class<?> @B ... values) {} }',
    'invalid_after_ellipsis': 'class C { void run(int ... @A values) {} }',
}
parser = Parser(Language(tree_sitter_java.language()))
grammar_dir = Path(tree_sitter_java.__file__).parent
report = {'grammar_files_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(grammar_dir.glob('*')) if p.suffix in {'.so', '.pyd'}},
          'analyzer_sha256': hashlib.sha256(Path('skills/columbus/scripts/columbus/jvm.py').read_bytes()).hexdigest(),
          'grammar_package_version': version('tree-sitter-java'), 'runtime_version': version('tree-sitter'),
          'fixtures': {}, 'corpus': {'files': 0, 'partial': [], 'symbols': 0, 'references': 0, 'source_hashes': {}}}
for name, source in fixtures.items():
    raw = source.encode()
    pending = [parser.parse(raw).root_node]
    spans = []
    while pending:
        node = pending.pop()
        if node.type in {'spread_parameter', 'annotation', 'marker_annotation'}:
            spans.append({'kind': node.type, 'start_byte': node.start_byte, 'end_byte': node.end_byte,
                          'source': raw[node.start_byte:node.end_byte].decode()})
        pending.extend(reversed(node.named_children))
    report['fixtures'][name] = {'source': source, 'ast_spans': spans, 'sha256': hashlib.sha256(source.encode()).hexdigest(),
                               'parsed': parse_jvm('C.java', source)}
for path in sorted(root.rglob('*.java')):
    if any(p in {'.git', 'build', 'target', '.columbus'} for p in path.relative_to(root).parts):
        continue
    raw = path.read_bytes()
    rel = path.relative_to(root).as_posix()
    parsed = parse_jvm(rel, raw.decode('utf-8'))
    corpus = report['corpus']
    corpus['files'] += 1
    corpus['symbols'] += len(parsed['symbols'])
    corpus['references'] += len(parsed['references'])
    corpus['source_hashes'][rel] = hashlib.sha256(raw).hexdigest()
    if parsed['partial']:
        corpus['partial'].append({'path': rel, 'diagnostics': parsed['diagnostics']})
output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'files': report['corpus']['files'], 'partial_files': len(report['corpus']['partial']),
                  'fixtures_partial': {k: v['parsed']['partial'] for k, v in report['fixtures'].items()}}))
