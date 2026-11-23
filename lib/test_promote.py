#!/usr/bin/env python3
"""승격 검토(promote.sh). 확인 표시 [V]·[?]만 바뀐 같은 사실은 B절 "탈락"으로 세지 않는다.
인계서 절 제목은 한국어·영어 템플릿 둘 다 읽고, 출력 언어는 BATON_LANG(없으면 로캘)을 따른다."""
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROMOTE = os.path.join(HERE, "promote.sh")


def handoff(*facts):
    return "# Session Handoff\n\n## 확인된 사실과 결정\n" + "".join(f"- {x}\n" for x in facts) + "\n## 관련 파일·심볼\n- a\n"


def handoff_en(facts, failed=(), rejected=()):
    return ("# Session Handoff (written: 2026-10-01)\n\n## Verified facts and decisions\n" + "".join(f"- {x}\n" for x in facts)
            + "\n## Files and symbols\n- a\n\n## Failed approaches (do not retry)\n" + "".join(f"- {x}\n" for x in failed)
            + "\n## Verification evidence\n- ran it\n\n## Promotion candidates (to DECISIONS.md)\n- None\n\n"
            + "### Rejected (do not raise again)\n" + "".join(f"- {x}\n" for x in rejected))


class PromoteTest(unittest.TestCase):
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

    def run_promote(self, r, lang="ko", code=0, **env):
        e = {k: v for k, v in os.environ.items() if k not in ("BATON_LANG", "LC_ALL", "LC_MESSAGES", "LANG")}
        e.update({"BATON_LANG": lang} if lang else {}, **env)
        p = subprocess.run(["bash", PROMOTE, r], capture_output=True, text=True, check=False, env=e)
        self.assertEqual(p.returncode, code, p.stdout + p.stderr)
        return p.stdout

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


if __name__ == "__main__":
    unittest.main()
