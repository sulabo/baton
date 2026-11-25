#!/usr/bin/env python3
"""승격 검토(promote.sh). 확인 표시 [V]·[?]만 바뀐 같은 사실은 B절 "탈락"으로 세지 않는다.
인계서 절 제목은 한국어·영어 템플릿 둘 다 읽고, 출력 언어는 BATON_LANG(없으면 로캘)을 따른다."""
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROMOTE = os.path.join(HERE, "promote.sh")
_CFG = tempfile.TemporaryDirectory()  # 실제 설정 파일(~/.config/baton/config.json, 전역 BATON_LANG 등)을 읽지 않는다


def tearDownModule():
    _CFG.cleanup()


def handoff(*facts):
    return "# Session Handoff\n\n## 확인된 사실과 결정\n" + "".join(f"- {x}\n" for x in facts) + "\n## 관련 파일·심볼\n- a\n"


def handoff_en(facts, failed=(), rejected=()):
    return ("# Session Handoff (written: 2026-10-01)\n\n## Verified facts and decisions\n" + "".join(f"- {x}\n" for x in facts)
            + "\n## Files and symbols\n- a\n\n## Failed approaches (do not retry)\n" + "".join(f"- {x}\n" for x in failed)
            + "\n## Verification evidence\n- ran it\n\n## Promotion candidates (to DECISIONS.md)\n- None\n\n"
            + "### Rejected (do not raise again)\n" + "".join(f"- {x}\n" for x in rejected))


class PromoteFixture:
    """저장소 만들기·스크립트 부르기. 테스트가 없는 섞어 쓰는 클래스 — 두 테스트 클래스가 서로의 테스트를 다시 돌리지 않게."""

    def repo(self, versions):
        """판마다 하루씩 다른 날짜로 HANDOFF.md를 커밋한 저장소."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        r = tmp.name
        git = ["git", "-C", r, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false"]
        subprocess.run(["git", "init", "-q", r], check=True)
        for day, text in enumerate(versions, 1):
            with open(os.path.join(r, "HANDOFF.md"), "w", encoding="utf-8") as f:
                f.write(text)
            date = f"2026-10-0{day}T10:00:00+0900"
            env = dict(os.environ, GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
            subprocess.run(git + ["add", "HANDOFF.md"], check=True)
            subprocess.run(git + ["commit", "-q", "-m", "x"], check=True, env=env)
        return r

    def run_promote(self, r, lang="ko", code=0, brief=False, **env):
        e = {k: v for k, v in os.environ.items() if k not in ("BATON_LANG", "LC_ALL", "LC_MESSAGES", "LANG")}
        e.update({"BATON_LANG": lang} if lang else {}, XDG_CONFIG_HOME=_CFG.name)
        e.update(env)
        p = subprocess.run(["bash", PROMOTE] + (["--brief"] if brief else []) + [r], capture_output=True, text=True, check=False, env=e)
        self.assertEqual(p.returncode, code, p.stdout + p.stderr)
        return p.stdout


class PromoteTest(PromoteFixture, unittest.TestCase):

    def test_mark_change_is_not_a_drop(self):
        # 리뷰(11-21) 재현 저장소와 같은 이력: [?]로 이틀 있던 사실이 최신판에서 [V]로 확인됐다
        out = self.run_promote(self.repo([
            handoff("[?] 배포는 금지 상태가 유지된다"),
            handoff("[?] 배포는 금지 상태가 유지된다", "[V] 기타"),
            handoff("[V] 배포는 금지 상태가 유지된다"),
        ]))
        self.assertIn("탈락 총 0건", out)
        self.assertNotIn("배포는 금지", out.split("[B]", 1)[1].split("[C]", 1)[0])

    def test_real_drop_still_reported(self):
        out = self.run_promote(self.repo([
            handoff("[?] 배포는 금지 상태가 유지된다"),
            handoff("[V] 배포는 금지 상태가 유지된다"),
            handoff("[V] 다른 사실"),
        ]))
        self.assertIn("탈락 총 1건", out)
        self.assertIn("- 배포는 금지 상태가 유지된다", out)

    def test_english_handoff_read_and_english_output(self):
        r = self.repo([
            handoff_en(["[?] Deploys are forbidden for now", "[V] Other"], ["Caching the index: stale after rebase"]),
            handoff_en(["[V] Deploys are forbidden for now", "[V] Other"], ["Caching the index: stale after rebase"]),
            handoff_en(["[V] Other"], ["Caching the index: stale after rebase"], ["Retry loop / 2026-10-03 / owner said no"]),
        ])
        out = self.run_promote(r, "en")
        self.assertIn("  ·  reviewed 3 days (3 versions by commit, but only one per day is counted)", out)
        a = out.split("[A]", 1)[1].split("[B]", 1)[0]
        self.assertIn("Repeated failures — constraints that survived on 3 or more different days", a)
        self.assertIn("    3 days: - Caching the index: stale after rebase", a)
        self.assertIn("    → 1 found\n", a)
        self.assertNotIn("could not be counted", a)  # 영어 절 제목을 읽었다 — 형식 불일치가 아니다
        b = out.split("[B]", 1)[1].split("[C]", 1)[0]
        self.assertIn("── With a decision marker (1) — look at these first", b)  # "forbidden"은 결정 표지
        self.assertIn("      - Deploys are forbidden for now", b)
        self.assertIn("→ 1 dropped in total.", b)
        self.assertIn("    already rejected: - Retry loop / 2026-10-03 / owner said no", out)
        ko = self.run_promote(r, "ko")  # 같은 영어 인계서를 한국어 출력으로
        self.assertIn("    3 일: - Caching the index", ko)
        self.assertIn("탈락 총 1건", ko)
        self.assertIn("    이미 기각: - Retry loop", ko)

    def test_placeholder_items_are_not_entries(self):
        # 11-23 ~/baton: 기각 절에 "- 없음"만 있는데 "이미 기각: - 없음"이 나왔다. 반복 실패·탈락에도 자리표시를 세지 않는다
        ko = ("# Session Handoff\n\n## 확인된 사실과 결정\n- {fact}\n\n## 관련 파일·심볼\n- a\n\n"
              "## 실패한 접근법 (다시 시도 금지)\n- 없음\n\n## 검증 증거\n- {ev}\n\n### 기각됨 (다시 올리지 않는다)\n{rej}")
        r = self.repo([ko.format(fact="없음", ev="1일", rej="- 없음\n"), ko.format(fact="없음", ev="2일", rej="- 없음\n"),
                       ko.format(fact="[V] 새 사실", ev="3일", rej="- 없음\n")])
        out = self.run_promote(r)
        self.assertIn("    → 0건", out)  # "- 없음"이 3일 살아남은 반복 실패가 아니다
        self.assertNotIn("형식 불일치", out)  # "- 없음"만 있는 절도 절은 있다 — 못 센 판이 아니다
        self.assertIn("탈락 총 0건", out)  # "- 없음"이 최신판에서 빠진 것은 탈락이 아니다
        self.assertIn("    (기각 목록 없음)", out)
        self.assertNotIn("이미 기각", out)
        en = handoff_en(["None"], ["None"], ["None"])
        for rej in ("- None\n", "- none.\n", "- -\n", "- \n", "- **없음**\n"):
            r = self.repo([en[:en.index("### Rejected")] + "### Rejected (do not raise again)\n" + rej])
            self.assertIn("    (no rejected list)", self.run_promote(r, "en"), rej)
        r = self.repo([ko.format(fact="없음", ev="x", rej="- 없음\n- 캐시 재도입 / 2026-10-01 / 소유자가 거절\n")])
        self.assertIn("    이미 기각: - 캐시 재도입 / 2026-10-01 / 소유자가 거절", self.run_promote(r))  # 진짜 항목은 그대로
        self.assertNotIn("이미 기각: - 없음", self.run_promote(r))

    def test_language_without_python(self):
        # 리뷰(11-23): python3이 없으면 한국어 로캘 사용자가 영어를 받았다 — 셸에서 BATON_LANG > LC_ALL > LC_MESSAGES > LANG을 본다
        with tempfile.TemporaryDirectory() as d:
            bin_ = os.path.join(d, "bin"); os.mkdir(bin_)
            with open(os.path.join(bin_, "python3"), "w") as f:
                f.write("#!/bin/sh\nexit 127\n")
            os.chmod(os.path.join(bin_, "python3"), 0o755)
            path = bin_ + os.pathsep + os.environ.get("PATH", "")
            for env, ko in (({"LANG": "ko_KR.UTF-8"}, True), ({"LANG": "kok_IN.UTF-8"}, False), ({"LANG": "C.UTF-8"}, False),
                            ({"LC_ALL": "ko", "LANG": "C"}, True), ({"LC_ALL": "", "LC_MESSAGES": "ko-KR", "LANG": "C"}, True),
                            ({"LC_ALL": "C", "LANG": "ko_KR.UTF-8"}, False), ({"LANG": "KO_kr"}, True), ({"LANG": "ko@x"}, True),
                            ({"LANG": "ko_KR.UTF-8", "BATON_LANG": "EN"}, False), ({"LANG": "C", "BATON_LANG": " ko "}, True), ({}, False)):
                out = self.run_promote(os.path.join(d, "missing"), None, code=2, PATH=path, **env)
                self.assertTrue(out.startswith("git 저장소가 아니다" if ko else "Not a git repository"), (env, out))

    def test_english_errors_and_locale_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            out = self.run_promote(d, "en", code=2)
            self.assertTrue(out.startswith(f"Not a git repository: {d}\nUsage: promote.sh"), out)
            subprocess.run(["git", "init", "-q", d], check=True)
            self.assertTrue(self.run_promote(d, "en", code=2).startswith("No HANDOFF.md:"))
            open(os.path.join(d, "HANDOFF.md"), "w").close()
            self.assertIn("git does not track it", self.run_promote(d, "en", code=2))
            self.assertIn("git이 추적하지 않는다", self.run_promote(d, None, code=2, LANG="ko_KR.UTF-8"))
            self.assertIn("git does not track it", self.run_promote(d, None, code=2, LANG="C.UTF-8"))


class PromoteBriefTest(PromoteFixture, unittest.TestCase):
    """--brief: 인계서를 쓸 때 스킬이 부르는 요약. 8줄 안, 중요한 것 먼저, 비었으면 그렇다고 한 줄(2026-11-25).
    전체 출력을 tail·head로 자르다 머리 줄이 잘려 다시 부르던 것(실험 2차 game 저장소 5번 중 4번)을 없애려고."""

    def repo(self, versions):
        """같은 내용이 이어지는 판도 커밋되게 판마다 다른 주석 한 줄을 붙인다(절 추출은 '- ' 줄만 본다)."""
        return super().repo([v + f"<!-- {i} -->\n" for i, v in enumerate(versions)])

    def lines(self, out):
        ls = out.splitlines()
        self.assertLessEqual(len(ls), 8, out)
        return ls

    def test_empty_says_nothing_to_promote_and_all_counted(self):
        r = self.repo([handoff_en(["[V] One fact"], ["None"])] * 3)
        self.assertEqual(self.lines(self.run_promote(r, brief=True)),
                         ["승격 검토(요약) · 검토 3일 · 반복 실패 0건 · 탈락 0건(결정 표지 0건) · 기각 목록 0개",
                          "  올릴 것 없음 · 검토 3일 모두 셈"])
        self.assertEqual(self.lines(self.run_promote(r, "en", brief=True))[1], "  Nothing to promote · all 3 days counted")
        # 3일이 안 되면 후보가 나올 수 없다 — "모두 셈"이라고 하지 않는다
        two = self.repo([handoff_en(["[V] One fact"], ["None"])] * 2)
        self.assertEqual(self.lines(self.run_promote(two, brief=True))[1], "  올릴 것 없음 · 검토 2일 — 3일이 안 돼 후보가 아직 나올 수 없다")
        self.assertEqual(self.lines(self.run_promote(two, "en", brief=True))[1],
                         "  Nothing to promote · 2 days reviewed, fewer than 3, so no candidate can show up yet")

    def test_candidates_first_and_capped_at_8_lines(self):
        fails = [f"Approach {i}: failed" for i in range(10)]
        r = self.repo([handoff_en(["[V] Deploys are forbidden for now", "[V] Other"], fails),
                       handoff_en(["[V] Deploys are forbidden for now", "[V] Other"], fails),
                       handoff_en(["[V] Other"], fails, ["Retry loop / 2026-10-03 / owner said no"])])
        ls = self.lines(self.run_promote(r, "en", brief=True))
        self.assertEqual(ls[0], "Promotion review (brief) · 3 days reviewed · repeated failures: 10 · dropped: 1 "
                                "(1 with a decision marker) · rejected list: 1")
        self.assertTrue(ls[1].startswith("  [A] 3 days: - Approach "), ls)
        self.assertEqual(ls[-1], "  … and 5 more. Run promote.sh without --brief for all of them")  # 후보 11건 중 6건만
        self.assertEqual(len(ls), 8)
        few = self.repo([handoff_en(["[V] Deploys are forbidden for now"], ["Caching: stale"]),
                         handoff_en(["[V] Deploys are forbidden for now"], ["Caching: stale"]),
                         handoff_en(["[V] Other"], ["Caching: stale"])])
        self.assertEqual(self.lines(self.run_promote(few, "ko", brief=True))[1:],
                         ["  [A] 3일: - Caching: stale", "  [B] - Deploys are forbidden for now"])

    def test_uncounted_versions_are_said_not_zero(self):
        other = "# Notes\n\n## Something else\n- x\n"
        r = self.repo([other, other, handoff("[V] 사실")])
        ls = self.lines(self.run_promote(r, brief=True))
        self.assertEqual(ls[1], "  못 셈: 반복 실패 형식 불일치 판 3개 · 탈락 절 형식이 다른 판 2개 — 0건이 아니라 못 셈")
        self.assertEqual(ls[2], "  찾은 후보 없음 — 위의 못 센 판 때문에 '없음'이 아니다")
        ls = self.lines(self.run_promote(self.repo([other]), "en", brief=True))
        self.assertIn("dropped: not counted", ls[0])
        self.assertIn("the latest version has no 'Verified facts and decisions' section", ls[1])

    def test_unmarked_drops_are_counted_not_promoted(self):
        r = self.repo([handoff_en(["[V] A note"], ["None"]), handoff_en(["[V] A note"], ["None"]),
                       handoff_en(["[V] Another fact"], ["None"])])
        self.assertEqual(self.lines(self.run_promote(r, brief=True))[1],
                         "  올릴 것 없음(결정 표지 붙은 후보 없음) · 표지 없는 탈락 1건은 대개 끝난 작업 메모 · 검토 3일 모두 셈")

    def test_brief_anywhere_and_versions_must_be_a_number(self):
        r = self.repo([handoff_en(["[V] One fact"], ["None"])] * 3)
        e = dict(os.environ, BATON_LANG="en", XDG_CONFIG_HOME=_CFG.name)
        run = lambda *a: subprocess.run(["bash", PROMOTE, *a], capture_output=True, text=True, env=e)
        first = run("--brief", r, "8").stdout
        self.assertEqual(run(r, "--brief", "8").stdout, first)  # 어느 자리에 와도 같다
        self.assertEqual(run(r, "8", "--brief").stdout, first)
        self.assertEqual(len(first.splitlines()), 2)
        for k in ("x", "0", "-3", "2.5", "08"):  # 빈 값은 빠진 것과 같다(기본 8)
            with self.subTest(k=k):
                p = run("--brief", r, k)
                self.assertEqual(p.returncode, 2, p.stdout)
                self.assertTrue(p.stdout.startswith(f"The number of versions must be a whole number of 1 or more: {k}\n"
                                                    "Usage: promote.sh [--brief]"), p.stdout)

    def test_staged_but_never_committed_handoff_is_uncounted(self):
        # 리뷰 11-25: 스테이징만 한 인계서(첫 커밋 전)에서 git이 fatal을 stderr에 내고 "검토 0일"로 이어 갔다
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True)
            with open(os.path.join(d, "HANDOFF.md"), "w", encoding="utf-8") as f:
                f.write(handoff("[V] 사실"))
            subprocess.run(["git", "-C", d, "add", "HANDOFF.md"], check=True)
            e = dict(os.environ, XDG_CONFIG_HOME=_CFG.name)
            for args, lang, want in ((["--brief", d], "ko", "HANDOFF.md의 커밋된 판이 없어 못 셈 — 0건이 아니라 못 셈."),
                                     ([d], "en", "HANDOFF.md has no committed version, so nothing could be counted (not 0: uncounted).")):
                p = subprocess.run(["bash", PROMOTE, *args], capture_output=True, text=True, env=dict(e, BATON_LANG=lang))
                self.assertEqual(p.returncode, 2, p.stdout)
                self.assertTrue(p.stdout.startswith(want), p.stdout)
                self.assertEqual(p.stderr, "")  # fatal 줄을 숨긴다

    def test_errors_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(self.run_promote(d, "en", code=2, brief=True).startswith(f"Not a git repository: {d}"))
            subprocess.run(["git", "init", "-q", d], check=True)
            self.assertTrue(self.run_promote(d, "en", code=2, brief=True).startswith("No HANDOFF.md:"))


if __name__ == "__main__":
    unittest.main()
