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

    def run_hook(self, lang="ko", **extra):
        env = dict(os.environ, XDG_CACHE_HOME=self.cache, CLAUDE_PLUGIN_ROOT=ROOT, BATON_LANG=lang)
        if lang is None:  # 로캘로 정하게 — 실제 설정 파일의 BATON_LANG도 안 읽게 한다
            for k in ("BATON_LANG", "LC_ALL", "LC_MESSAGES", "LANG"):
                env.pop(k, None)
            env["XDG_CONFIG_HOME"] = os.path.join(self.tmp.name, "cfg")
        env.update(extra)
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

    def test_concept_name_with_fresh_word_is_not_counted_as_fresh(self):
        # 2026-11-21: 표의 '신선' 글자를 세서, 이름에 '신선'이 든 재확인 개념이 신선으로도 세어졌다
        self.commit({"a.txt": "a\n"})
        base =subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=self.repo, capture_output=True,
                              text=True, check=True).stdout.strip()
        self.commit({"CONCEPTS.md": "## 1. 신선도 계산 — 판정\n\n- **메타**: 상태=일치 · 확인=2026-11-21(`%s`) · "
                                    "파일=`a.txt` · 이웃=없음\n" % base, "a.txt": "b\n"})
        msg = self.run_hook()
        self.assertIn("재확인 대상 1건 (신선 0건)", msg)


    def test_parser_warning_is_announced_even_with_zero_stale(self):
        # 열린 채 끝난 코드 펜스 뒤의 개념은 표에 없다 — 재확인 0건이어도 조용하면 '다 신선'으로 읽힌다
        self.commit({"a.txt": "a\n"})
        base = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=self.repo, capture_output=True,
                              text=True, check=True).stdout.strip()
        meta = "- **메타**: 상태=일치 · 확인=2026-11-21(`%s`) · 파일=`a.txt` · 이웃=없음\n" % base
        self.commit({"CONCEPTS.md": "## 1. 앞\n" + meta + "```\n안 닫힘\n\n## 2. 뒤\n" + meta})
        msg = self.run_hook()
        self.assertIsNotNone(msg)
        self.assertIn("코드 펜스", msg)


    def test_heading_in_closed_fence_does_not_trigger_notice(self):  # 재현 저장소 t6
        self.commit({"a.txt": "a\n"})
        base = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=self.repo, capture_output=True,
                              text=True, check=True).stdout.strip()
        self.commit({"CONCEPTS.md": "## 1. 개념\n- **메타**: 상태=일치 · 확인=2026-11-21(`%s`) · 파일=`a.txt` · 이웃=없음\n\n"
                                    "예시:\n```\n## 2. 예시 개념\n```\n" % base})
        self.assertIsNone(self.run_hook())

    def test_meta_count_uses_parser_not_grep(self):  # 펜스 밖 개념 둘 중 하나만 메타 줄 — 펜스 안 예시는 세지 않는다
        self.commit({"a.txt": "a\n"})
        self.commit({"CONCEPTS.md": "## 1. 개념\n- **메타**: 상태=일치 · 확인=2026-11-21(`0000000`) · 파일=`a.txt` · 이웃=없음\n"
                                    "```\n## 3. 예시\n- **메타**: 예시 줄\n```\n## 2. 둘째\n본문\n"})
        msg = self.run_hook()
        self.assertIn("개념 2개 중 메타 줄 1개", msg)


class DriftNoticeEnglishTest(DriftNoticeTest):
    """BATON_LANG=en: 같은 경우의 영어 알림. 위 한국어 테스트를 물려받아 한국어도 같이 돈다."""

    def head(self):
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=self.repo, capture_output=True, text=True,
                              check=True).stdout.strip()

    def en_meta(self, h):
        return "- **Meta**: status=agrees · checked=2026-11-21(`%s`) · files=`a.txt` · neighbors=none\n" % h

    def test_missing_meta_in_english(self):
        self.commit({"CONCEPTS.md": "## 1. save — saving\nbody\n"})
        self.assertEqual(self.run_hook("en"), "[baton] The concept map has no metadata lines (concepts: 1).\n"
                                              "  Freshness can't be computed — this is not 0, it is unknown.\n"
                                              "  To fill them in: /drift or the driftmap skill")

    def test_stale_singular_plural_and_partial_meta(self):
        self.commit({"a.txt": "a\n", "b.txt": "b\n"})
        h = self.head()
        self.commit({"CONCEPTS.md": "## 1. one\n" + self.en_meta(h) + "## 2. two\nbody\n", "a.txt": "b\n"})
        self.assertEqual(self.run_hook("en"), "[baton] 1 concept in the concept map needs a re-check (0 fresh). Details: /drift\n"
                                              "  Only 1 of 2 concepts have a metadata line — the other 1 can't be counted at all.")
        self.commit({"CONCEPTS.md": "## 1. one\n" + self.en_meta(h) + "## 2. two\n" + self.en_meta(h) +
                                    "## 3. three\n" + self.en_meta(h).replace("a.txt", "b.txt")})
        self.assertEqual(self.run_hook("en"), "[baton] 2 concepts in the concept map need a re-check (1 fresh). Details: /drift")

    def test_fence_warning_in_english(self):
        self.commit({"a.txt": "a\n"})
        meta = self.en_meta(self.head())
        self.commit({"CONCEPTS.md": "## 1. front\n" + meta + "```\nopen\n\n## 2. back\n" + meta})
        self.assertEqual(self.run_hook("en"), "[baton] 0 concepts in the concept map need a re-check (1 fresh). Details: /drift\n"
                                              "  a code fence opened at line 3 is never closed — 1 concept after it could not be read")

    def test_language_is_part_of_the_cache_key(self):
        self.commit({"CONCEPTS.md": STALE_MAP, "a.txt": "a\n"})
        self.assertIn("재확인 대상 1건", self.run_hook("ko"))
        self.assertEqual(self.run_hook("en"), "[baton] 1 concept in the concept map needs a re-check (0 fresh). Details: /drift")
        self.assertIn("재확인 대상 1건", self.run_hook("ko"))

    def test_locale_fallback(self):
        self.commit({"CONCEPTS.md": STALE_MAP, "a.txt": "a\n"})
        self.assertIn("재확인 대상 1건", self.run_hook(None, LANG="ko_KR.UTF-8"))
        self.assertIn("1 concept in the concept map needs a re-check", self.run_hook(None, LANG="C.UTF-8"))

    def test_unreadable_summary_is_reported(self):  # fresh.sh가 요약 줄 없이 끝나면 '못 셌다' — 캐시 자리에 요약 없는 출력을 둔다
        self.commit({"CONCEPTS.md": STALE_MAP, "a.txt": "a\n"})
        self.run_hook("en")
        drift = os.path.join(self.cache, "baton", "drift")
        for name in os.listdir(drift):
            with open(os.path.join(drift, name), "w") as f:
                f.write("garbage")
        self.assertEqual(self.run_hook("en"), "[baton] Could not read the freshness summary of the concept map — this is not 0, "
                                              "it could not be counted. Run /drift to see it.")


if __name__ == "__main__":
    unittest.main()
