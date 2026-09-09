"""Fail closed if a candidate wheel was not loaded or annotations regress."""
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'skills/columbus/scripts'))
from columbus.jvm import parse_jvm
import tree_sitter_java
from tree_sitter import Language, Parser

assert version('tree-sitter-java') == '0.23.5+columbus.1'
parser = Parser(Language(tree_sitter_java.language()))
cases = {
    'primitive': ('class C { void run(int @A ... values) {} }', False),
    'array': ('class C { void run(int @A [] @B ... values) {} }', False),
    'generic': ('class C { void run(@A Class<?> @B ... values) {} }', False),
    'invalid_after_ellipsis': ('class C { void run(int ... @A values) {} }', True),
}
results = {}
for name, (source, expected) in cases.items():
    raw = source.encode()
    tree = parser.parse(raw)
    parsed = parse_jvm('C.java', source)
    assert tree.root_node.has_error == expected, name
    assert parsed['partial'] == expected, name
    nodes = [tree.root_node]
    annotations = []
    while nodes:
        node = nodes.pop()
        if node.type in {'annotation', 'marker_annotation'}:
            annotations.append(raw[node.start_byte:node.end_byte].decode())
        nodes.extend(node.named_children)
    if not expected:
        assert sorted(annotations) == (['@A'] if name == 'primitive' else ['@A', '@B']), name
    results[name] = {'partial': parsed['partial'], 'annotations': sorted(annotations)}
root = Path(tree_sitter_java.__file__).parent
binaries = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir() if p.suffix in {'.so', '.pyd'}}
assert binaries, 'Missing native grammar binary'
report = {'python': sys.version, 'platform': platform.platform(), 'package_version': version('tree-sitter-java'),
          'module_path': str(root), 'binary_sha256': binaries, 'fixtures': results}
Path(sys.argv[1]).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report))
