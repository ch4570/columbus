"""Provenance gates reject candidate bytes that were not the tested binaries."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'evals/java-grammar'))
spec = importlib.util.spec_from_file_location('grammar_aggregate', ROOT/'evals/java-grammar/aggregate.py')
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


class AggregateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='columbus aggregate gates ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.wheels = []
        for platform in a.PLATFORMS:
            folder = self.root/f'java-candidate-{platform}-py3.11'
            folder.mkdir()
            wheel = folder/f'tree_sitter_java-{a.VERSION}-cp39-abi3-{platform.replace("-", "_")}.whl'
            self.write_wheel(wheel, b'tested binary')
            self.wheels.append(wheel)
            provenance = {'upstream_revision': a.REVISION, 'package_version': a.VERSION,
                          'generator': 'tree-sitter-cli@0.27.0', 'abi': 14,
                          'patch_sha256': a.sha(ROOT/'evals/java-grammar/dimensions.patch'),
                          'files_sha256': {name: 'same reviewed source' for name in ('grammar.js', 'src/parser.c', 'src/node-types.json', 'bindings/python/tree_sitter_java/binding.c', 'LICENSE')}}
            runtime = {'package_version': a.VERSION,
                       'fixtures': {name: {'partial': name == 'invalid_after_ellipsis'} for name in ('primitive', 'array', 'generic', 'invalid_after_ellipsis')},
                       'binary_sha256': {'_binding.abi3.so': hashlib.sha256(b'tested binary').hexdigest()}}
            for name, data in [('provenance', provenance), ('runtime', runtime), ('distribution', {'status': 'passed', 'bundled_java_default': True})]:
                a.dump(folder/(name+'.json'), data)

    def write_wheel(self, path, binary):
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('tree_sitter_java.dist-info/METADATA', f'Name: tree-sitter-java\nVersion: {a.VERSION}\n')
            archive.writestr('tree_sitter_java.dist-info/licenses/LICENSE', 'fixture license')
            archive.writestr('tree_sitter_java/_binding.abi3.so', binary)

    def test_changed_native_binary_is_rejected_despite_passing_receipt(self):
        self.assertEqual(len(a.select(self.root)), 3)
        self.write_wheel(self.wheels[1], b'untested replacement')
        with self.assertRaisesRegex(ValueError, 'differs from tested native binary'):
            a.select(self.root)

    def test_different_generated_parser_and_missing_platform_are_rejected(self):
        path = self.wheels[0].parent/'provenance.json'
        original = json.loads(path.read_text())
        altered = json.loads(path.read_text())
        altered['files_sha256']['src/parser.c'] = 'different generated parser'
        a.dump(path, altered)
        with self.assertRaisesRegex(ValueError, 'generated sources disagree'):
            a.select(self.root)
        a.dump(path, original)
        self.wheels[2].unlink()
        with self.assertRaisesRegex(ValueError, 'Expected one candidate wheel'):
            a.select(self.root)


if __name__ == '__main__':
    unittest.main()
