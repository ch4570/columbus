import importlib.metadata
import unittest
from unittest.mock import patch

from columbus.cli import doctor
from columbus.languages import JVM_DEPENDENCIES


class DoctorVersionTests(unittest.TestCase):
    def test_public_pin_accepts_local_build_but_rejects_other_releases(self):
        for installed, expected in [('0.23.5', True), ('0.23.5+columbus.1', True),
                                    ('0.23.6', False), ('0.23.6+columbus.1', False),
                                    ('0.23.5rc1', False), (None, False)]:
            with self.subTest(installed=installed):
                def version(name):
                    if name != 'tree-sitter-java':
                        return JVM_DEPENDENCIES[name]
                    if installed is None:
                        raise importlib.metadata.PackageNotFoundError(name)
                    return installed
                with patch('columbus.cli.importlib.metadata.version', side_effect=version):
                    report = doctor()
                self.assertEqual(expected, report['ready'])
                self.assertEqual(installed, report['dependencies']['tree-sitter-java']['installed'])
