"""Source-reviewed target census for the issue #4 navigation file.

This checks a saved full index against manually selected declarations. It is
not a compiler oracle, a runtime dispatch claim or corpus-wide precision.
"""
import argparse
from collections import Counter
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import zlib

p = argparse.ArgumentParser()
p.add_argument('repo', type=Path)
p.add_argument('database', type=Path)
p.add_argument('output', type=Path)
p.add_argument('--runtime', type=Path, required=True)
a = p.parse_args()
runtime_hashes = {}
current_runtime = Path(__file__).resolve().parents[2] / 'skills/columbus/scripts'
for source in sorted(a.runtime.rglob('*.py')):
    relative = source.relative_to(a.runtime)
    assert source.read_bytes() == (current_runtime / relative).read_bytes(), relative
    runtime_hashes[str(relative)] = hashlib.sha256(source.read_bytes()).hexdigest()
base = 'src/main/java/org/springframework/'
path = base + 'core/io/DefaultResourceLoader.java'
# These target declarations were reviewed from imports, receiver declarations,
# argument expressions and declaration signatures, separately from graph IDs.
expected = [
    (107, 'ClassUtils.getDefaultClassLoader()', 'util/ClassUtils.java', 'org.springframework.util.ClassUtils.getDefaultClassLoader:method()'),
    (169, 'new ClassPathResource(location.substring(CLASSPATH_URL_PREFIX.length()), getClassLoader())', 'core/io/ClassPathResource.java', 'org.springframework.core.io.ClassPathResource:class'),
    (172, 'new ClassPathAllResource(location.substring(CLASSPATH_ALL_URL_PREFIX.length()), getClassLoader())', 'core/io/DefaultResourceLoader.java', 'org.springframework.core.io.DefaultResourceLoader.ClassPathAllResource:class'),
    (177, 'ResourceUtils.toURL(location)', 'util/ResourceUtils.java', 'org.springframework.util.ResourceUtils.toURL:method(String)'),
    (178, 'ResourceUtils.isFileURL(url)', 'util/ResourceUtils.java', 'org.springframework.util.ResourceUtils.isFileURL:method(URL)'),
    (178, 'new FileUrlResource(url)', 'core/io/FileUrlResource.java', 'org.springframework.core.io.FileUrlResource:class'),
    (178, 'new UrlResource(url)', 'core/io/UrlResource.java', 'org.springframework.core.io.UrlResource:class'),
    (199, 'new ClassPathContextResource(path, getClassLoader())', 'core/io/DefaultResourceLoader.java', 'org.springframework.core.io.DefaultResourceLoader.ClassPathContextResource:class'),
    (282, 'StringUtils.applyRelativePath(getPath(), relativePath)', 'util/StringUtils.java', 'org.springframework.util.StringUtils.applyRelativePath:method(String,String)'),
    (283, 'new ClassPathAllResource(pathToUse, getClassLoader())', 'core/io/DefaultResourceLoader.java', 'org.springframework.core.io.DefaultResourceLoader.ClassPathAllResource:class'),
    (310, 'StringUtils.applyRelativePath(getPath(), relativePath)', 'util/StringUtils.java', 'org.springframework.util.StringUtils.applyRelativePath:method(String,String)'),
    (311, 'new ClassPathContextResource(pathToUse, getClassLoader())', 'core/io/DefaultResourceLoader.java', 'org.springframework.core.io.DefaultResourceLoader.ClassPathContextResource:class'),
]
with closing(sqlite3.connect(a.database.resolve().as_uri() + '?mode=ro', uri=True)) as c:
    hashes = dict(c.execute('SELECT path,hash FROM files'))
    facts = json.loads(zlib.decompress(c.execute('SELECT parsed FROM files WHERE path=?', (path,)).fetchone()[0]))
    calls = [r for r in facts['references'] if r['kind'] == 'calls']
    nodes = {r[0] for r in c.execute('SELECT id FROM symbols')}
    edges = list(c.execute("SELECT line,evidence,target FROM edges WHERE path=? AND kind='calls'", (path,)))
assert all(hashlib.sha256((a.repo / name).read_bytes()).hexdigest() == h for name, h in hashes.items())
reviewed = [(line, evidence, base + target_path + '::' + declaration) for line, evidence, target_path, declaration in expected]
actual = [(r['line'], r['evidence'], r['target']) for r in calls if r['resolved']]
assert Counter(actual) == Counter(reviewed)
assert Counter(edges) == Counter(reviewed)
assert all(target in nodes for _, _, target in reviewed)
gaps = []
for line, evidence, declaration in [
    (158, 'getProtocolResolvers()', 'DefaultResourceLoader.getProtocolResolvers()'),
    (159, 'protocolResolver.resolve(location, this)', 'ProtocolResolver.resolve(String, ResourceLoader)'),
    (166, 'getResourceByPath(location)', 'DefaultResourceLoader.getResourceByPath(String)'),
]:
    matches = [r for r in calls if (r['line'], r['evidence']) == (line, evidence)]
    assert len(matches) == 1 and not matches[0]['resolved']
    gaps.append({'reference': matches[0], 'source_reviewed_static_declaration': declaration})
result = {
    'saved_runtime_matches_current': True,
    'runtime_sha256': runtime_hashes,
    'database_sha256': hashlib.sha256(a.database.read_bytes()).hexdigest(),
    'all_indexed_source_hashes_verified': len(hashes),
    'source_hashes': {name: hashes[name] for name in sorted({path, base + 'core/io/ProtocolResolver.java'} | {base + r[2] for r in expected})},
    'extracted_call_references': len(calls),
    'reviewed_emitted_method_targets': sum(':method(' in r[2] for r in reviewed),
    'reviewed_emitted_constructed_classes': sum(r[2].endswith(':class') for r in reviewed),
    'reviewed_targets': reviewed,
    'unresolved_reasons': dict(Counter(r['reason'] for r in calls if not r['resolved'])),
    'source_reviewed_known_gaps': gaps,
    'constructor_overload_accuracy_claimed': False,
    'runtime_dispatch_accuracy_claimed': False,
    'corpus_precision_or_recall_claimed': False,
}
a.output.write_text(json.dumps(result, indent=2) + '\n')
print({k: v for k, v in result.items() if k.startswith('reviewed_emitted') or k == 'extracted_call_references'})
