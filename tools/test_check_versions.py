#!/usr/bin/env python3
"""check_versions.py: 매니페스트 세 곳과 CHANGELOG 맨 위 버전이 하나라도 다르면 실패한다."""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_versions  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class CheckVersionsTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        for path, _ in check_versions.MANIFESTS:
            os.makedirs(os.path.join(self.root, os.path.dirname(path)), exist_ok=True)
            shutil.copy(os.path.join(REPO, path), os.path.join(self.root, path))
        self.write_changelog("## [Unreleased]\n\n## [2.0.0] — 2026-12-01\n\n## [1.0.0] — 2026-11-01\n")
        for path, _ in check_versions.MANIFESTS:
            self.set_version(path, "2.0.0")

    def tearDown(self):
        shutil.rmtree(self.root)

    def write_changelog(self, text):
        with open(os.path.join(self.root, "CHANGELOG.md"), "w", encoding="utf-8") as f:
            f.write("# Changelog\n\n" + text)

    def set_version(self, path, version):
        full = os.path.join(self.root, path)
        with open(full, encoding="utf-8") as f:
            data = json.load(f)
        (data["plugins"][0] if "plugins" in data else data)["version"] = version
        with open(full, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def test_all_agree_skipping_unreleased(self):
        self.assertEqual(check_versions.check(self.root), [])
        self.assertEqual(check_versions.check(self.root, tag="v2.0.0"), [])

    def test_each_single_manifest_bump_fails(self):
        for path, _ in check_versions.MANIFESTS:
            with self.subTest(path=path):
                self.set_version(path, "2.0.1")
                errors = check_versions.check(self.root)
                self.assertEqual(len(errors), 1)
                self.assertIn(path, errors[0])
                self.set_version(path, "2.0.0")

    def test_changelog_only_bump_fails_all_three(self):
        self.write_changelog("## [2.1.0] — 2026-12-02\n")
        self.assertEqual(len(check_versions.check(self.root)), 3)

    def test_tag_mismatch_and_missing_heading(self):
        self.assertEqual(len(check_versions.check(self.root, tag="v2.0.1")), 1)
        self.write_changelog("no headings\n")
        self.assertIn("no '## [x.y.z]' heading", check_versions.check(self.root)[0])


if __name__ == "__main__":
    unittest.main()
