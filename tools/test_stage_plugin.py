#!/usr/bin/env python3
"""stage-plugin.sh: 설치 사본은 git이 아는 파일만, 실패해도 다시 돌릴 수 있고, 저장소 안·중첩 저장소는 거부한다."""
import os
import shutil
import subprocess
import tempfile
import unicodedata
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stage-plugin.sh")


def sh(*args, cwd=None):
    return subprocess.run(list(args), cwd=cwd, capture_output=True, text=True)


class StagePluginTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(); self.repo = os.path.join(self.tmp, "저장소 폴더")
        os.makedirs(os.path.join(self.repo, "tools")); shutil.copy(SCRIPT, os.path.join(self.repo, "tools"))
        for rel, text in {"a.txt": "a", "한글 이름.md": "b", ".gitignore": ".data/\n", ".data/secret.txt": "s", "gone.txt": "g"}.items():
            p = os.path.join(self.repo, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
            self._w(p, text)
        sh("git", "init", "-q", cwd=self.repo); sh("git", "add", "-A", cwd=self.repo)
        sh("git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x", cwd=self.repo)
        self.run_ = lambda dst: sh("bash", os.path.join(self.repo, "tools", "stage-plugin.sh"), dst)
        self.out = os.path.join(self.tmp, "out")

    @staticmethod
    def _w(path, text):
        with open(path, "w", encoding="utf-8") as f: f.write(text)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def files(self):
        return sorted(unicodedata.normalize("NFC", os.path.relpath(os.path.join(d, f), self.out)) for d, _, fs in os.walk(self.out) for f in fs)

    def test_copies_known_files_only_and_skips_deleted_tracked(self):
        os.remove(os.path.join(self.repo, "gone.txt"))
        self._w(os.path.join(self.repo, "new.txt"), "n")
        r = self.run_(self.out)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.files(), [".baton-stage", ".gitignore", "a.txt", "new.txt", "tools/stage-plugin.sh", unicodedata.normalize("NFC", "한글 이름.md")])

    def test_refuses_untracked_nested_repo(self):
        nested = os.path.join(self.repo, "nested"); os.makedirs(nested); sh("git", "init", "-q", cwd=nested)
        self._w(os.path.join(nested, "s.txt"), "s")
        r = self.run_(self.out)
        self.assertNotEqual(r.returncode, 0); self.assertIn("중첩 저장소", r.stderr)
        self.assertFalse(os.path.exists(self.out))

    def test_refuses_targets_inside_repo_including_ignored_and_dotdot(self):
        for dst in (os.path.join(self.repo, "x"), os.path.join(self.repo, ".data", "snap", "stage"), os.path.join(self.tmp, "a", "..", "out")):
            self.assertEqual(self.run_(dst).returncode, 2, dst)
        self.assertFalse(os.path.exists(os.path.join(self.repo, "x")))

    def test_refuses_foreign_folder_but_reruns_over_own_copy(self):
        os.makedirs(self.out); self._w(os.path.join(self.out, "keep"), "k")
        self.assertEqual(self.run_(self.out).returncode, 2)
        self.assertTrue(os.path.exists(os.path.join(self.out, "keep")))
        shutil.rmtree(self.out)
        self.assertEqual(self.run_(self.out).returncode, 0)
        self.assertEqual(self.run_(self.out).returncode, 0)


if __name__ == "__main__":
    unittest.main()
