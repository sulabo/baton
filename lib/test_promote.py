#!/usr/bin/env python3
"""승격 검토(promote.sh). 확인 표시 [V]·[?]만 바뀐 같은 사실은 B절 "탈락"으로 세지 않는다.
인계서 절 제목은 한국어·영어 템플릿 둘 다 읽고, 출력 언어는 BATON_LANG(없으면 로캘)을 따른다."""
import os
import subprocess
import tempfile
import time
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

    def run_promote(self, r, lang="ko", code=0, brief=False, status=False, cwd=None, **env):
        e = {k: v for k, v in os.environ.items() if k not in ("BATON_LANG", "LC_ALL", "LC_MESSAGES", "LANG")}
        e.update({"BATON_LANG": lang} if lang else {}, XDG_CONFIG_HOME=_CFG.name)
        e.update(env)
        args = ["bash", PROMOTE] + (["--brief"] if brief else []) + (["--status"] if status else []) + [r]
        p = subprocess.run(args, capture_output=True, text=True, check=False, env=e, cwd=cwd)
        self.assertEqual(p.returncode, code, p.stdout + p.stderr)
        if brief:
            self.assertEqual(p.stderr, "")  # --brief는 stderr를 stdout으로 낸다 — 스킬 주입에는 둘이 섞여 들어간다
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
                for args, code in ((["--brief", r, k], 0), ([r, k], 2)):  # --brief는 못 돌려도 0(스킬 주입), 전체 형식은 2
                    p = run(*args)
                    self.assertEqual(p.returncode, code, p.stdout)
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
            for args, lang, want, code in ((["--brief", d], "ko", "HANDOFF.md의 커밋된 판이 없어 못 셈 — 0건이 아니라 못 셈.", 0),
                                           ([d], "en", "HANDOFF.md has no committed version, so nothing could be counted (not 0: uncounted).", 2)):
                p = subprocess.run(["bash", PROMOTE, *args], capture_output=True, text=True, env=dict(e, BATON_LANG=lang))
                self.assertEqual(p.returncode, code, p.stdout)
                self.assertTrue(p.stdout.startswith(want), p.stdout)
                self.assertEqual(p.stderr, "")  # fatal 줄을 숨긴다

    def test_errors_unchanged_but_brief_exits_0(self):
        # 1.0.3: 스킬이 --brief를 불러올 때 돌린다(동적 주입). 0이 아니면 스킬이 안 뜨므로 못 돌린 까닭은 출력으로만 말한다
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(self.run_promote(d, "en", brief=True).startswith(f"Not a git repository: {d}"))
            subprocess.run(["git", "init", "-q", d], check=True)
            self.assertTrue(self.run_promote(d, "en", brief=True).startswith("No HANDOFF.md:"))
            self.assertTrue(self.run_promote(d, "en", code=2).startswith("No HANDOFF.md:"))  # 전체 형식은 그대로 2



class PromoteStatusTest(PromoteFixture, unittest.TestCase):
    """--brief --status: 스킬이 불러올 때 돌리는 쓰기 전 상태(1.0.3). git status --short --branch 와 git log --oneline -3 을
    요약 앞에 먼저 낸다 — 시한에 끊겨도 상태는 남게(리뷰 11-26). 어느 길로 못 돌려도 0으로 끝나야 한다 — 0이 아니면 Claude Code가
    스킬을 못 띄워 인계서를 못 쓴다."""

    def repo(self, versions):
        """PromoteBriefTest.repo와 같다 — 같은 내용이 이어지는 판도 커밋되게 판마다 다른 주석 한 줄."""
        return PromoteFixture.repo(self, [v + f"<!-- {i} -->\n" for i, v in enumerate(versions)])

    def git(self, r, *a):
        subprocess.run(["git", "-C", r, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false", *a],
                       check=True, capture_output=True)

    def tmp(self, name="r"):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        return os.path.join(d.name, name)

    def fake_git(self, body):
        """PATH 앞에 끼우는 git — body는 sh 코드, 그 밖에는 진짜 git에 넘긴다."""
        real = subprocess.run(["sh", "-c", "command -v git"], capture_output=True, text=True, check=True).stdout.strip()
        d = self.tmp("bin")
        os.mkdir(d)
        with open(os.path.join(d, "git"), "w") as f:
            f.write(f'#!/bin/sh\n{body}\nexec "{real}" "$@"\n')
        os.chmod(os.path.join(d, "git"), 0o755)
        return d + os.pathsep + os.environ.get("PATH", "")

    def test_status_then_log_then_brief(self):
        r = self.repo([handoff_en(["[V] One fact"], ["None"])] * 3)
        with open(os.path.join(r, "a.txt"), "w") as f:
            f.write("x")
        ls = self.run_promote(r, "en", brief=True, status=True).splitlines()
        self.assertTrue(ls[0].startswith("## "), ls)  # git status --short --branch
        self.assertEqual(ls[1], "?? a.txt")
        self.assertEqual(len(ls), 7, ls)  # 커밋 3개
        self.assertTrue(all(len(x.split(" ", 1)[0]) >= 7 and x.endswith(" x") for x in ls[2:5]), ls)
        self.assertEqual(ls[5:], ["Promotion review (brief) · 3 days reviewed · repeated failures: 0 · dropped: 0 (0 with a decision marker) "
                                  "· rejected list: 0", "  Nothing to promote · all 3 days counted"])
        brief = self.run_promote(r, "en", brief=True)
        self.assertEqual(brief.splitlines(), ls[5:])  # --status 없이는 그대로
        full = self.run_promote(r, "en", status=True).splitlines()  # 전체 형식에도 앞에 붙는다
        self.assertEqual(full[:2], ["## " + ls[0][3:], "?? a.txt"])

    def test_every_failure_path_exits_0_with_a_reason(self):
        d = self.tmp("not a repo")
        os.mkdir(d)
        out = self.run_promote(d, "en", brief=True, status=True)
        self.assertEqual(out, f"Not a git repository: {d}\n")  # git 줄도, 주입 출력에 섞일 사용법 줄도 없이(리뷰 11-26)
        self.git(d, "init", "-q")
        out = self.run_promote(d, "en", brief=True, status=True, LC_ALL="C")
        self.assertTrue(out.startswith("## "), out)
        self.assertTrue(out.splitlines()[1].startswith("fatal: "), out)  # 첫 커밋 전 git log의 fatal 줄도 그대로(종료코드는 보지 않는다)
        self.assertIn("\nNo HANDOFF.md:", out)
        with open(os.path.join(d, "HANDOFF.md"), "w", encoding="utf-8") as f:
            f.write(handoff("[V] 사실"))
        out = self.run_promote(d, "ko", brief=True, status=True)
        self.assertIn("git이 추적하지 않는다", out)
        self.assertIn("\n?? HANDOFF.md\n", out)
        self.git(d, "add", "HANDOFF.md")
        out = self.run_promote(d, "en", brief=True, status=True)
        self.assertIn("\nHANDOFF.md has no committed version", out)
        self.assertIn("\nA  HANDOFF.md\n", out)
        self.git(d, "commit", "-q", "-m", "h")
        out = self.run_promote(d, "en", brief=True, status=True)
        self.assertIn("\nPromotion review (brief) · 1 days reviewed", out)

    def test_cwd_with_spaces_and_subfolder(self):
        r = self.repo([handoff_en(["[V] One fact"], ["None"])] * 2)
        spaced = self.tmp("my repo")  # 치워지는 임시 폴더 안으로 옮긴다
        os.rename(r, spaced)
        self.addCleanup(os.rename, spaced, r)  # 원래 자리로 되돌려 repo()의 정리가 지우게
        sub = os.path.join(spaced, "sub dir")
        os.mkdir(sub)
        with open(os.path.join(sub, "b.txt"), "w") as f:
            f.write("x")
        for cwd in (spaced, sub):  # 스킬은 대화 폴더에서 "."로 부른다 — 하위 폴더여도 루트의 HANDOFF.md를 본다
            with self.subTest(cwd=os.path.basename(cwd)):
                ls = self.run_promote(".", "en", brief=True, status=True, cwd=cwd).splitlines()
                self.assertEqual(ls[-1], "  Nothing to promote · 2 days reviewed, fewer than 3, so no candidate can show up yet")
                self.assertTrue(ls[0].startswith("## "), ls)
                self.assertEqual(ls[1], '?? "sub dir/"')  # 상태도 루트 기준 경로

    def test_unreadable_handoff_says_so(self):
        r = self.repo([handoff_en(["[V] One fact"], ["None"], ["Retry loop / 2026-10-01 / no"])] * 3)
        os.chmod(os.path.join(r, "HANDOFF.md"), 0)
        self.addCleanup(os.chmod, os.path.join(r, "HANDOFF.md"), 0o644)
        head = self.run_promote(r, "en", brief=True).splitlines()[0]
        if os.access(os.path.join(r, "HANDOFF.md"), os.R_OK):  # root는 권한 0도 읽는다 — 그때는 평소대로 센다
            self.assertTrue(head.endswith("rejected list: 1"), head)
        else:
            self.assertTrue(head.endswith("rejected list: not read (HANDOFF.md can't be read)"), head)
            self.assertIn("    (HANDOFF.md can't be read, so the rejected list wasn't read)", self.run_promote(r, "en"))

    def test_git_errors_are_shown_and_exit_0(self):
        r = self.repo([handoff_en(["[V] One fact"], ["None"])] * 3)
        path = self.fake_git('case " $* " in *" status "*|*" log --oneline "*) echo "fatal: boom $3" >&2; exit 128;; esac')
        ls = self.run_promote(r, "en", brief=True, status=True, PATH=path).splitlines()
        self.assertEqual(ls[:2], ["fatal: boom status", "fatal: boom log"])
        self.assertEqual(ls[3:], ["  Nothing to promote · all 3 days counted"])
        path = self.fake_git('echo "fatal: everything is broken" >&2; exit 128')
        out = self.run_promote(r, "en", brief=True, status=True, PATH=path)
        self.assertTrue(out.startswith(f"Not a git repository: {r}\n"), out)

    def test_slow_git_is_cut_off_and_exits_0(self):
        r = self.repo([handoff_en(["[V] One fact"], ["None"])] * 3)
        path = self.fake_git('case " $* " in *" log --format="*) sleep 5;; esac')
        start = time.monotonic()
        out = self.run_promote(r, "en", brief=True, status=True, PATH=path, BATON_PROMOTE_TIMEOUT="1")
        self.assertLess(time.monotonic() - start, 4)  # 끊긴 git이 출력 관을 붙잡지 않는다
        ls = out.splitlines()
        self.assertTrue(ls[0].startswith("## "), ls)  # 셈에서 멈춰도 먼저 낸 상태는 남는다(리뷰 11-26)
        self.assertEqual(len(ls), 5, ls)
        self.assertEqual(ls[-1], "The promotion review did not finish within 1 s and was stopped (not 0: uncounted). "
                                 "If you need it, run promote.sh without --brief")
        ko = self.run_promote(r, "ko", brief=True, PATH=path, BATON_PROMOTE_TIMEOUT="1")
        self.assertTrue(ko.startswith("승격 검토가 1초 안에 끝나지 않아 멈췄다 — 0건이 아니라 못 셈."), ko)
        # 상태 부분에서 멈추면 시한 줄만 남는다
        path = self.fake_git('case " $* " in *" status "*) sleep 5;; esac')
        ls = self.run_promote(r, "en", brief=True, status=True, PATH=path, BATON_PROMOTE_TIMEOUT="1").splitlines()
        self.assertEqual(len(ls), 1, ls)
        self.assertTrue(ls[0].startswith("The promotion review did not finish within 1 s"), ls)

    def test_timeout_kills_the_git_children_and_removes_its_temp_files(self):
        # 리뷰 11-26: 시한에 자식 bash만 끊어 그 자식이 부른 git이 남았고, 출력 임시 파일은 끝날 때 지우지 않는 길이 있었다
        r = self.repo([handoff_en(["[V] One fact"], ["None"])] * 3)
        marker = "37.25"  # 이 테스트의 git만 집는 sleep 값
        path = self.fake_git(f'case " $* " in *" log --format="*) sleep {marker};; esac')
        tmp = self.tmp("tmp")
        os.mkdir(tmp)
        out = self.run_promote(r, "en", brief=True, PATH=path, BATON_PROMOTE_TIMEOUT="1", TMPDIR=tmp)
        self.assertTrue(out.startswith("The promotion review did not finish within 1 s"), out)
        left = ""
        for _ in range(20):  # 신호가 닿을 때까지 잠깐
            left = subprocess.run(["pgrep", "-f", f"sleep {marker}"], capture_output=True, text=True).stdout
            if not left:
                break
            time.sleep(0.1)
        self.assertEqual(left, "")  # 자식이 부른 git(과 그 sleep)까지 묶음째 끊었다
        self.assertEqual(os.listdir(tmp), [])
        self.run_promote(r, "en", brief=True, TMPDIR=tmp)  # 끝까지 돈 길도 치운다
        self.assertEqual(os.listdir(tmp), [])

    def test_slow_language_call_is_inside_the_time_limit(self):
        # 리뷰 11-26: 언어를 정하는 python 호출이 시간 지킴이보다 먼저 돌아 10초 시한 밖이었다
        r = self.repo([handoff_en(["[V] One fact"], ["None"])] * 3)
        real = subprocess.run(["sh", "-c", "command -v python3"], capture_output=True, text=True, check=True).stdout.strip()
        d = self.tmp("pybin")
        os.mkdir(d)
        with open(os.path.join(d, "python3"), "w") as f:
            f.write(f'#!/bin/sh\ncase "$1" in *i18n.py) sleep 5;; esac\nexec "{real}" "$@"\n')
        os.chmod(os.path.join(d, "python3"), 0o755)
        start = time.monotonic()
        out = self.run_promote(r, "ko", brief=True, PATH=d + os.pathsep + os.environ.get("PATH", ""), BATON_PROMOTE_TIMEOUT="1")
        self.assertLess(time.monotonic() - start, 4)
        self.assertTrue(out.startswith("승격 검토가 1초 안에 끝나지 않아 멈췄다"), out)  # 언어를 정하기 전에 끊겨도 셸 규칙의 언어로


if __name__ == "__main__":
    unittest.main()
