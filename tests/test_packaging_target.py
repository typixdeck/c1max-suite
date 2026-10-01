"""Prevent source-only packaging from relabelling stale native binaries."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('build_debs', Path(__file__).parents[1] / 'tools/build_debs.py')
build_debs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_debs)


class PackagingTargetTests(unittest.TestCase):
    def args(self, **kwargs):
        return SimpleNamespace(**dict(python_only=True, target_os='raspios-trixie', apps=['piano', 'dosbox', 'ps1']) | kwargs)

    def test_explicit_source_only_target_does_not_read_or_forge_host_os(self):
        with patch.object(Path, 'read_text', side_effect=AssertionError('host OS must remain untouched')):
            self.assertEqual(build_debs.target_codename(self.args()), 'trixie')

    def test_source_only_cannot_publish_native_or_held_camera(self):
        for name in sorted(build_debs.NATIVE | {'camera'}):
            with self.subTest(app=name), self.assertRaises(ValueError):
                build_debs.target_codename(self.args(apps=['piano', name]))

    def test_target_required_and_cannot_override_native_host(self):
        with self.assertRaises(ValueError):
            build_debs.target_codename(self.args(target_os=None))
        with self.assertRaises(ValueError):
            build_debs.target_codename(self.args(python_only=False))
        with patch.object(build_debs.platform, 'system', return_value='Darwin'), self.assertRaises(ValueError):
            build_debs.target_codename(self.args(python_only=False, target_os=None))


if __name__ == '__main__':
    unittest.main()
