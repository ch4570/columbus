"""Text resource output must retain the same uncertainty and evidence as JSON."""
from pathlib import Path
import tempfile
import unittest

from columbus.index import RepositoryIndex
from columbus.presentation import render
from columbus.resource_navigation import resources


class NavigationPresentationTests(unittest.TestCase):
    def test_dynamic_resource_keeps_expression_reason_hash_and_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'repo'
            root.mkdir()
            (root / 'Routes.kt').write_text('''
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.GetMapping
@RequestMapping("${base}")
class Routes {
 @GetMapping("/items") fun route() {}
}
''')
            index = RepositoryIndex(Path(directory) / 'index.sqlite')
            index.refresh(root)
            packet = resources(index, output_format='text', budget_bytes=4000)
            rendered = render(packet, 'text')
            item = packet['items'][0]
            self.assertIn('${base}', rendered)
            self.assertIn(item['source_hash'], rendered)
            self.assertIn('evidence=', rendered)
            self.assertIn('http=', rendered)
            self.assertIn('resolution=dynamic', rendered)
            for limitation in item['limitations']:
                self.assertIn(limitation, rendered)
            self.assertLessEqual(len(rendered.encode()), 4000)
            self.assertEqual(len(rendered.encode()), packet['used_bytes'])


if __name__ == '__main__':
    unittest.main()
