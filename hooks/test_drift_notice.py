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
        self.assertEqual(self.run_hook(), "[baton] 개념 지도에 확인 기록(메타 줄)이 없어서 어떤 개념이 바뀌었는지 셀 수 없어요(개념 1개).\n"
                                          "채우려면 /drift를 실행하거나 \"개념 지도 갱신해 줘\"라고 해 보세요.")

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
        self.assertEqual(self.run_hook(), "[baton] 개념 지도에서 다시 확인할 개념이 1개 있어요(그대로인 개념 0개). 자세히 보려면 /drift")
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
        self.assertIn("다시 확인할 개념이 1개 있어요(그대로인 개념 0개)", msg)


    def test_parser_warning_is_announced_even_with_zero_stale(self):
        # 열린 채 끝난 코드 펜스 뒤의 개념은 표에 없다 — 재확인 0건이어도 조용하면 '다 신선'으로 읽힌다
        self.commit({"a.txt": "a\n"})
        base = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=self.repo, capture_output=True,
                              text=True, check=True).stdout.strip()
        meta = "- **메타**: 상태=일치 · 확인=2026-11-21(`%s`) · 파일=`a.txt` · 이웃=없음\n" % base
        self.commit({"CONCEPTS.md": "## 1. 앞\n" + meta + "```\n안 닫힘\n\n## 2. 뒤\n" + meta})
        self.assertEqual(self.run_hook(), "[baton] 개념 지도의 3번째 줄에서 연 코드 블록이 닫히지 않아서, 그 뒤 개념 1개를 읽지 못했어요. "
                                          "자세히 보려면 /drift")


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
        self.assertIn("\n개념 2개 중 1개는 확인 기록(메타 줄)이 없어서 세지 못했어요.", msg)

    def test_repo_local_module_is_not_imported(self):  # 알림 JSON을 만드는 python3 -c가 저장소의 json.py를 불러오면 안 된다
        marker = os.path.join(self.tmp.name, "planted-ran")
        self.commit({"CONCEPTS.md": STALE_MAP, "a.txt": "a\n",
                     "json.py": "open(%r, 'w').write('x')\nraise RuntimeError('planted json.py')\n" % marker})
        self.assertIn("개념 지도에서 다시 확인할 개념이 1개 있어요", self.run_hook())
        self.assertFalse(os.path.exists(marker))


class DriftNoticeEnglishTest(DriftNoticeTest):
    """BATON_LANG=en: 같은 경우의 영어 알림. 위 한국어 테스트를 물려받아 한국어도 같이 돈다."""

    def head(self):
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=self.repo, capture_output=True, text=True,
                              check=True).stdout.strip()

    def en_meta(self, h):
        return "- **Meta**: status=agrees · checked=2026-11-21(`%s`) · files=`a.txt` · neighbors=none\n" % h

    def test_missing_meta_in_english(self):
        self.commit({"CONCEPTS.md": "## 1. save — saving\nbody\n"})
        self.assertEqual(self.run_hook("en"), "[baton] The concept map has no check records (metadata lines), so baton can't "
                                              "tell which concepts changed (1 concept).\n"
                                              "To fill them in, run /drift or say \"update the concept map\".")

    def test_stale_singular_plural_and_partial_meta(self):
        self.commit({"a.txt": "a\n", "b.txt": "b\n"})
        h = self.head()
        self.commit({"CONCEPTS.md": "## 1. one\n" + self.en_meta(h) + "## 2. two\nbody\n", "a.txt": "b\n"})
        self.assertEqual(self.run_hook("en"), "[baton] 1 concept in the concept map needs another look (0 unchanged). "
                                              "For details: /drift\n"
                                              "1 of 2 concepts has no check record (metadata line), so it wasn't counted.")
        self.commit({"CONCEPTS.md": "## 1. one\n" + self.en_meta(h) + "## 2. two\n" + self.en_meta(h) +
                                    "## 3. three\n" + self.en_meta(h).replace("a.txt", "b.txt")})
        self.assertEqual(self.run_hook("en"), "[baton] 2 concepts in the concept map need another look (1 unchanged). "
                                              "For details: /drift")

    def test_fence_warning_in_english(self):
        self.commit({"a.txt": "a\n"})
        meta = self.en_meta(self.head())
        self.commit({"CONCEPTS.md": "## 1. front\n" + meta + "```\nopen\n\n## 2. back\n" + meta})
        self.assertEqual(self.run_hook("en"), "[baton] In the concept map, a code block opened at line 3 is never closed, so "
                                              "1 concept after it couldn't be read. For details: /drift")

    def test_language_is_part_of_the_cache_key(self):
        self.commit({"CONCEPTS.md": STALE_MAP, "a.txt": "a\n"})
        self.assertIn("개념 지도에서 다시 확인할 개념이 1개 있어요", self.run_hook("ko"))
        self.assertEqual(self.run_hook("en"), "[baton] 1 concept in the concept map needs another look (0 unchanged). "
                                              "For details: /drift")
        self.assertIn("개념 지도에서 다시 확인할 개념이 1개 있어요", self.run_hook("ko"))

    def test_locale_fallback(self):
        self.commit({"CONCEPTS.md": STALE_MAP, "a.txt": "a\n"})
        self.assertIn("개념 지도에서 다시 확인할 개념이 1개 있어요", self.run_hook(None, LANG="ko_KR.UTF-8"))
        self.assertIn("1 concept in the concept map needs another look", self.run_hook(None, LANG="C.UTF-8"))

    def test_unreadable_summary_is_reported(self):  # fresh.sh가 요약 줄 없이 끝나면 '못 셌다' — 캐시 자리에 요약 없는 출력을 둔다
        self.commit({"CONCEPTS.md": STALE_MAP, "a.txt": "a\n"})
        self.run_hook("en")
        drift = os.path.join(self.cache, "baton", "drift")
        for name in os.listdir(drift):
            with open(os.path.join(drift, name), "w") as f:
                f.write("garbage")
        self.assertEqual(self.run_hook("en"), "[baton] Couldn't read the concept map's check results, so baton can't tell which "
                                              "concepts changed. Try /drift to check it directly.")
        self.assertIn("개념 지도에서 다시 확인할 개념이 1개 있어요", self.run_hook("ko"))  # 한국어 캐시 키는 따로다 — 새로 계산해 채운다
        for name in os.listdir(drift):
            with open(os.path.join(drift, name), "w") as f:
                f.write("garbage")
        self.assertEqual(self.run_hook("ko"), "[baton] 개념 지도의 확인 결과를 읽지 못해서 바뀐 개념을 셀 수 없어요. "
                                              "/drift로 직접 확인해 보세요.")


    def test_fence_warning_with_stale_concepts_and_raw_fallback(self):
        self.commit({"a.txt": "a\n", "b.txt": "b\n"})
        h = self.head()
        self.commit({"CONCEPTS.md": "## 1. one\n" + self.en_meta(h) + "## 2. two\n" + self.en_meta(h).replace("a.txt", "b.txt")
                                    + "```\nopen\n\n## 3. three\n" + self.en_meta(h) + "## 4. four\n" + self.en_meta(h),
                     "a.txt": "changed\n"})
        self.assertEqual(self.run_hook("ko"), "[baton] 개념 지도에서 다시 확인할 개념이 1개 있어요(그대로인 개념 1개). 자세히 보려면 /drift\n"
                                              "개념 지도의 5번째 줄에서 연 코드 블록이 닫히지 않아서, 그 뒤 개념 2개를 읽지 못했어요.")
        self.assertEqual(self.run_hook("en"), "[baton] 1 concept in the concept map needs another look (1 unchanged). "
                                              "For details: /drift\n"
                                              "In the concept map, a code block opened at line 5 is never closed, so 2 concepts "
                                              "after it couldn't be read.")
        drift = os.path.join(self.cache, "baton", "drift")  # 경고에서 숫자를 못 꺼내면 원문을 쓴다 — 캐시 자리에 그런 출력을 둔다

        def cached(text):
            for name in os.listdir(drift):
                with open(os.path.join(drift, name), "w", encoding="utf-8") as f:
                    f.write(text)
        cached("요약: 재확인 0 · 신선 1 · 규칙 개념 0\n주의: 코드 펜스 문제\n")
        self.assertEqual(self.run_hook("ko"), "[baton] 개념 지도 일부를 읽지 못했어요: 코드 펜스 문제. 자세히 보려면 /drift")
        cached("Summary: re-check 0 · fresh 1 · rule concepts 0\nWarning: a code fence problem\n")
        self.assertEqual(self.run_hook("en"), "[baton] Part of the concept map couldn't be read: a code fence problem. "
                                              "For details: /drift")

    def test_unreadable_map_is_reported(self):
        self.commit({"CONCEPTS.md": STALE_MAP})
        broken = os.path.join(self.tmp.name, "plugin")  # 파서가 없는 플러그인 자리 — 개념 지도를 못 읽는다
        os.makedirs(os.path.join(broken, "lib"))
        for f in ("i18n.py", "config.py", "lib.sh"):
            os.symlink(os.path.join(ROOT, "lib", f), os.path.join(broken, "lib", f))
        self.assertEqual(self.run_hook("ko", CLAUDE_PLUGIN_ROOT=broken),
                         "[baton] 개념 지도를 읽지 못해서 바뀐 개념을 셀 수 없어요. /drift로 직접 확인해 보세요.")
        self.assertEqual(self.run_hook("en", CLAUDE_PLUGIN_ROOT=broken),
                         "[baton] Couldn't read the concept map, so baton can't tell which concepts changed. "
                         "Try /drift to check it directly.")


if __name__ == "__main__":
    unittest.main()
