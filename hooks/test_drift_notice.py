#!/usr/bin/env python3
"""SessionStart 훅: 알릴 것이 있을 때만 JSON additionalContext 하나를 내고, 자기 캐시 밖의 파일은 지우지 않는다."""
import json
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "drift-notice.sh")
ROOT = os.path.dirname(HERE)
STALE_MAP = "# 개념\n\n## 1. 세이브 — 저장\n- **메타**: 확인 2026-09-01 · 파일 a.txt · 커밋 0000000\n본문\n"


class DriftNoticeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        self.cache = os.path.join(self.tmp.name, "cache")
        os.makedirs(self.repo)
        self.git("init", "-q")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *a):
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=self.repo, check=True,
                       capture_output=True)

    def commit(self, files):
        for rel, text in files.items():
            with open(os.path.join(self.repo, rel), "w", encoding="utf-8") as f:
                f.write(text)
        self.git("add", ".")
        self.git("commit", "-qm", "c")

    def run_hook(self):
        env = dict(os.environ, XDG_CACHE_HOME=self.cache, CLAUDE_PLUGIN_ROOT=ROOT)
        r = subprocess.run(["bash", HOOK], cwd=self.repo, env=env, capture_output=True, text=True, check=False)
        self.assertEqual(r.returncode, 0, r.stderr)
        if not r.stdout.strip():
            return None
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "SessionStart")
        return out["additionalContext"]

    def test_silent_without_map(self):
        self.commit({"a.txt": "a\n"})
        self.assertIsNone(self.run_hook())

    def test_missing_meta_is_reported_not_silent(self):
        self.commit({"CONCEPTS.md": "## 1. 세이브 — 저장\n본문\n"})
        self.assertIn("메타 줄이 없다", self.run_hook())

    def test_stale_reported_and_only_own_cache_cleaned(self):
        self.commit({"CONCEPTS.md": STALE_MAP, "a.txt": "a\n"})
        baton = os.path.join(self.cache, "baton")
        keep = [os.path.join(baton, "runs.jsonl"), os.path.join(baton, "plugin", "f")]  # 관찰 로그·설치 사본
        old = os.path.join(baton, "drift", "old")
        for p in keep + [old]:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w") as f:
                f.write("x")
            os.utime(p, (0, 0))
        self.assertIn("재확인 대상 1건", self.run_hook())
        for p in keep:
            self.assertTrue(os.path.exists(p), p)
        self.assertFalse(os.path.exists(old))


if __name__ == "__main__":
    unittest.main()
