#!/usr/bin/env python3
"""fresh.sh 로드맵 7단계: 확인 이후 새 결정의 '관련' 줄이 가리킨 개념을 재확인 대상으로 올린다."""
import os
import subprocess
import tempfile
import unittest

FRESH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fresh.sh")


def git(root, *args):
    return subprocess.run(["git", "-C", root, *args], check=True, capture_output=True, text=True).stdout.strip()


class RepoCase(unittest.TestCase):
    """임시 git 저장소에서 fresh.sh를 돌리는 공통 바탕."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = self.tmp.name
        git(self.root, "init", "-q"); git(self.root, "config", "user.email", "t@t"); git(self.root, "config", "user.name", "t")
        self.write("src/a.ts", "a\n"); self.write("DECISIONS.md", "# 결정\n")
        self.base = self.commit("base")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel, text, mode="w"):
        path = os.path.join(self.root, rel); os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, mode, encoding="utf-8") as f: f.write(text)

    def commit(self, msg):
        git(self.root, "add", "-A"); git(self.root, "commit", "-qm", msg)
        return git(self.root, "rev-parse", "--short", "HEAD")

    def concepts(self, h1, h2=None):
        h2 = h2 or h1
        self.write("CONCEPTS.md",
                   f"## 1. 세이브 — 저장 규칙\n- **메타**: 상태=일치 · 확인=2026-09-01(`{h1}`) · 파일=`src/a.ts` · 이웃=없음\n\n"
                   f"## 2. 마스킹 규칙 — 산출물\n- **메타**: 상태=일치 · 확인=2026-09-01(`{h2}`) · 파일=없음(규칙 개념) · 이웃=없음\n")

    def fresh(self, cwd=None, lang="ko", name="CONCEPTS.md"):
        r = subprocess.run(["bash", FRESH, os.path.join(self.root, name), self.root], capture_output=True, text=True,
                           cwd=cwd, env=dict(os.environ, BATON_LANG=lang))
        return r.stdout

    def line(self, out, num):
        return next(l for l in out.splitlines() if l.startswith(num + " "))


class FreshPointedTest(RepoCase):

    def test_no_new_decision_keeps_fresh(self):
        self.concepts(self.base); self.commit("map")
        out = self.fresh()
        self.assertIn("신선", self.line(out, "1"))
        self.assertIn("규칙 개념", self.line(out, "2"))

    def test_decision_pointing_by_number_marks_code_concept(self):
        self.concepts(self.base); self.commit("map")
        self.write("DECISIONS.md", "## 2026-09-30 세이브 바꿈\n- 관련: 개념 1\n", "a"); self.commit("dec")
        out = self.fresh()
        self.assertIn("재확인 필요 — 확인 이후 새 결정이 '관련'으로 가리킴", self.line(out, "1"))
        self.assertIn("규칙 개념", self.line(out, "2"))

    def test_rule_concept_pointed_by_name_in_table_cell(self):
        self.concepts(self.base); self.commit("map")
        self.write("DECISIONS.md", '| P1 | 마스킹 개정 | 이유 - 관련: [[p]] · CONCEPTS 개념 "마스킹 규칙" |\n', "a"); self.commit("dec")
        self.assertIn("가리킴", self.line(self.fresh(), "2"))

    def test_decision_before_concept_check_is_ignored(self):
        self.write("DECISIONS.md", "## 2026-09-02 옛 결정\n- 관련: 개념 1\n", "a"); later = self.commit("old dec")
        self.concepts(later); self.commit("map")
        self.assertIn("신선", self.line(self.fresh(), "1"))

    def test_unknown_name_is_reported_not_silently_zero(self):
        self.concepts(self.base); self.commit("map")
        self.write("DECISIONS.md", '## 2026-09-30 x\n- 관련: 개념 "없는 이름"\n', "a"); self.commit("dec")
        out = self.fresh()
        self.assertIn("못 셌다", out); self.assertIn("없는 이름", out)

    def test_pointed_keeps_original_verdict(self):
        self.concepts(self.base); self.commit("map")
        self.write("src/a.ts", "b\n"); self.commit("code")
        self.write("DECISIONS.md", "## 2026-09-30 x\n- 관련: 개념 1\n", "a"); self.commit("dec")
        l = self.line(self.fresh(), "1")
        self.assertIn("커밋 1건", l); self.assertIn("새 결정이 '관련'으로 가리킴", l)

    def test_counts_and_negations_are_not_pointers(self):
        self.concepts(self.base); self.commit("map")
        self.write("DECISIONS.md", "## 2026-09-30 x\n- 관련: CONCEPTS.md 개념 1개 추가\n- 관련: 없음 (개념 1은 변경 없음)\n", "a"); self.commit("dec")
        self.assertIn("신선", self.line(self.fresh(), "1"))

    def test_second_quoted_name_and_unknown_number_are_reported(self):
        self.concepts(self.base); self.commit("map")
        self.write("DECISIONS.md", '## 2026-09-30 x\n- 관련: 개념 "마스킹 규칙"·"없는 이름" · 개념 9\n', "a"); self.commit("dec")
        out = self.fresh()
        self.assertIn("가리킴", self.line(out, "2")); self.assertIn("없는 이름", out); self.assertIn("개념 9(절 없음)", out)

    def test_number_before_the_word_related_is_not_a_pointer(self):
        self.concepts(self.base); self.commit("map")
        self.write("DECISIONS.md", "## 2026-09-30 개념 1을 다룬 결정\n- 관련: 없음\n", "a"); self.commit("dec")
        self.assertIn("신선", self.line(self.fresh(), "1"))


class FreshDocsTest(RepoCase):
    """메타 줄의 '문서' 항목. 2026-11-21 baton 저장소: README를 통째로 다시 쓴 PR #8 뒤에도 fresh.sh가 12개 모두 '신선'을 냈다."""

    def map_with_docs(self, h, docs="`README.md`", files="`src/a.ts`"):
        self.write("CONCEPTS.md",
                   f"## 1. 세이브 — 저장 규칙\n- **메타**: 상태=일치 · 확인=2026-09-01(`{h}`) · 파일={files} · 이웃=없음 · 문서={docs}\n")

    def setUp(self):
        super().setUp()
        self.write("README.md", "# readme\n"); self.base = self.commit("readme")

    def test_readme_rewrite_marks_concept_for_recheck(self):
        self.map_with_docs(self.base); self.commit("map")
        self.write("README.md", "# rewritten\n"); self.commit("readme rewrite")
        self.assertIn("재확인 필요 — 문서 커밋 1건", self.line(self.fresh(), "1"))

    def test_untouched_docs_stay_fresh(self):
        self.map_with_docs(self.base); self.commit("map")
        self.assertIn("신선", self.line(self.fresh(), "1"))

    def test_code_and_docs_both_moved(self):
        self.map_with_docs(self.base); self.commit("map")
        self.write("src/a.ts", "b\n"); self.write("README.md", "# b\n"); self.commit("both")
        l = self.line(self.fresh(), "1")
        self.assertIn("커밋 1건", l); self.assertIn("문서 커밋 1건", l)

    def test_rule_concept_with_moved_doc(self):
        self.map_with_docs(self.base, files="없음(규칙 개념)"); self.commit("map")
        self.write("README.md", "# b\n"); self.commit("readme")
        self.assertIn("재확인 필요 — 문서 커밋 1건 (규칙 개념)", self.line(self.fresh(), "1"))

    def test_missing_doc_path_is_reported(self):
        self.map_with_docs(self.base, docs="`README.md`,`docs/gone.md`"); self.commit("map")
        self.assertIn("문서 경로 소실 1개", self.line(self.fresh(), "1"))

    def test_summary_line(self):
        self.map_with_docs(self.base); self.commit("map")
        self.write("README.md", "# b\n"); self.commit("readme")
        self.assertIn("요약: 재확인 1 · 신선 0", self.fresh())


class ParserTrailingSectionTest(unittest.TestCase):
    """숫자 없는 ## 절(일치 확인된 것·유지 규칙 등)은 앞 개념 절에 붙지 않는다. 2026-11-21 baton CONCEPTS.md에서 발견."""

    def test_unnumbered_heading_closes_concept(self):
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import concepts
        lines = ["## 1. 하나", "본문", "## 2. 둘", "본문 2", "## 유지 규칙", "개념 1을 번호로 부른다", "# 끝"]
        secs = list(concepts.walk(lines))
        self.assertEqual([n for n, _, _ in secs], ["1", "2"])
        self.assertEqual(secs[-1][2], ["본문 2"])

    def test_numbered_subsection_still_in_body(self):
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import concepts
        secs = list(concepts.walk(["## 1. 하나", "### 소절", "본문"]))
        self.assertEqual(secs[0][2], ["### 소절", "본문"])


class FreshReviewFixTest(RepoCase):
    """PR #11 독립 리뷰(2026-11-21)가 재현한 엣지. 각 테스트는 리뷰 전 코드에서 실패했다."""

    def map1(self, h, files="`src/a.ts`", docs=None):
        d = f" · 문서={docs}" if docs else ""
        self.write("CONCEPTS.md", f"## 1. 세이브\n- **메타**: 상태=일치 · 확인=2026-11-21({h}) · 파일={files} · 이웃=없음{d}\n")

    def test_renamed_doc_is_recheck_not_fresh(self):  # 리뷰 t3
        self.write("README.md", "r\n"); base = self.commit("readme")
        self.map1(f"`{base}`", docs="`README.md`"); self.commit("map")
        git(self.root, "mv", "README.md", "GUIDE.md"); self.commit("rename doc")
        l = self.line(self.fresh(), "1")
        self.assertTrue(l.split(None, 3)[3].startswith("재확인 필요"), l)
        self.assertIn("문서 커밋 1건", l)

    def test_never_existing_doc_path_is_recheck(self):
        self.map1(f"`{self.base}`", docs="`docs/nope.md`"); self.commit("map")
        self.assertIn("재확인 필요 — 문서 경로 소실 1개", self.line(self.fresh(), "1"))

    def test_partly_gone_code_path_is_recheck(self):  # 코드 쪽도 같은 규칙
        self.map1(f"`{self.base}`", files="`src/a.ts`,`src/gone.ts`"); self.commit("map")
        self.assertIn("재확인 필요 — 경로 소실 1개", self.line(self.fresh(), "1"))

    def test_baseline_outside_current_history(self):  # 리뷰 t2: 다른 가지의 커밋
        git(self.root, "checkout", "-qb", "side"); self.write("x.txt", "x\n"); side = self.commit("side")
        git(self.root, "checkout", "-q", "-"); self.map1(f"`{side}`"); self.commit("map")
        self.assertIn("재확인 필요 — 기준이 현재 이력 밖", self.line(self.fresh(), "1"))

    def test_space_in_doc_path(self):  # 리뷰 t1 개념 2
        self.write("docs/한글 문서.md", "a\n"); base = self.commit("doc")
        self.map1(f"`{base}`", docs="`docs/한글 문서.md`"); self.commit("map")
        self.write("docs/한글 문서.md", "b\n"); self.commit("edit")
        l = self.line(self.fresh(), "1")
        self.assertIn("문서 커밋 1건", l); self.assertNotIn("소실", l)

    def test_glob_is_resolved_at_repo_root_not_cwd(self):  # 리뷰 t1 개념 6
        self.write("docs/g.md", "a\n"); base = self.commit("doc")
        self.map1(f"`{base}`", docs="`docs/*.md`"); self.commit("map")
        self.write("docs/g.md", "b\n"); self.commit("edit")
        other = os.path.join(self.tmp.name, "elsewhere"); os.makedirs(os.path.join(other, "docs"))
        for n in ("p.md", "q.md"):
            open(os.path.join(other, "docs", n), "w").close()
        l = self.line(self.fresh(cwd=other), "1")
        self.assertIn("문서 커밋 1건", l); self.assertNotIn("소실", l)

    def test_rule_concept_without_baseline_says_docs_unchecked(self):  # 리뷰 6
        self.write("CONCEPTS.md", "## 1. 규칙\n- **메타**: 상태=일치 · 확인=2026-11-21(해시 미상) · 파일=없음(규칙 개념) · 이웃=없음 · 문서=`DECISIONS.md`\n"
                                  "## 2. 규칙2\n- **메타**: 상태=일치 · 확인=2026-11-21(`deadbee`) · 파일=없음(규칙 개념) · 이웃=없음 · 문서=`DECISIONS.md`\n")
        self.commit("map")
        out = self.fresh()
        self.assertIn("문서 못 봄", self.line(out, "1")); self.assertIn("문서 못 봄", self.line(out, "2"))


class ParserFenceTest(unittest.TestCase):
    """코드 펜스 안의 '# 주석'은 제목이 아니다(PR #11 리뷰: OTHER_HEADING이 펜스 안에서 개념 절을 닫았다)."""

    def test_comment_inside_fence_does_not_close_concept(self):
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import concepts
        lines = ["## 1. 첫 개념", "본문", "```bash", "# 주석 한 줄", "lib/fresh.sh CONCEPTS.md", "```",
                 "- **메타**: 상태=일치 · 확인=2026-11-21(`abc1234`) · 파일=`a.py`", "개념 2 참조", "",
                 "## 2. 둘째", "- **메타**: 상태=일치 · 확인=2026-11-21(`abc1234`) · 파일=`b.py`",
                 "~~~", "## 9. 펜스 안의 가짜 절", "~~~"]
        secs = list(concepts.walk(lines))
        self.assertEqual([n for n, _, _ in secs], ["1", "2"])
        self.assertIn("개념 2 참조", secs[0][2])
        self.assertTrue(any(l.startswith("- **메타**") for l in secs[0][2]))


class FollowupTest(RepoCase):
    """PR #11 재검증(2026-11-21)에서 남은 것. 각 테스트는 고치기 전 코드에서 실패했다."""

    def check(self, lang="ko"):
        r = subprocess.run(["bash", os.path.join(os.path.dirname(FRESH), "check.sh"), os.path.join(self.root, "CONCEPTS.md")],
                           capture_output=True, text=True, env=dict(os.environ, BATON_LANG=lang))
        return r.returncode, r.stdout

    def unclosed_map(self):
        self.write("CONCEPTS.md", f"## 1. 앞\n- **메타**: 상태=일치 · 확인=2026-11-21(`{self.base}`) · 파일=`src/a.ts` · 이웃=없음\n"
                                  "```\n열고 안 닫음\n\n"
                                  f"## 2. 뒤\n- **메타**: 상태=일치 · 확인=2026-11-21(`{self.base}`) · 파일=`src/a.ts` · 이웃=없음\n")
        self.commit("map")

    def test_unclosed_fence_is_warned_by_fresh(self):  # 재현 저장소 t4
        self.unclosed_map()
        out = self.fresh()
        self.assertIn("주의: 코드 펜스가 3줄에서 열린 채 파일이 끝난다", out)
        self.assertIn("개념 1개를 못 읽었다", out)

    def test_unclosed_fence_is_a_finding_in_check(self):
        self.unclosed_map()
        rc, out = self.check()
        self.assertEqual(rc, 1, out); self.assertIn("코드 펜스가 3줄에서 열린 채", out)

    def test_heading_inside_closed_fence_is_not_warned(self):  # 재현 저장소 t6: 정상으로 닫힌 펜스 안의 예시 제목
        self.write("CONCEPTS.md", f"## 1. 앞\n- **메타**: 상태=일치 · 확인=2026-11-21(`{self.base}`) · 파일=`src/a.ts` · 이웃=없음\n"
                                  "예시:\n```\n## 9. 예시\n```\n")
        self.commit("map")
        out = self.fresh()
        self.assertNotIn("주의:", out)
        _, chk = self.check()
        self.assertIn("[7] 파서가 끝까지 읽었는가", chk)
        self.assertEqual(chk.split("[7]", 1)[1].splitlines()[1].strip(), "지적 없음", chk)

    def test_rule_concept_with_lost_baseline_is_recheck(self):  # 세션 알림이 울려야 한다
        self.write("CONCEPTS.md", "## 1. 규칙\n- **메타**: 상태=일치 · 확인=2026-11-21(`deadbee`) · 파일=없음(규칙 개념) · 이웃=없음\n")
        self.commit("map")
        out = self.fresh()
        self.assertIn("재확인 필요 — 기준 소실 (규칙 개념)", self.line(out, "1"))
        self.assertIn("요약: 재확인 1", out)


CHECK = os.path.join(os.path.dirname(FRESH), "check.sh")
EN_MAP = ("## 1. save — save rules\n- **Meta**: status=agrees · checked=2026-09-01(`{h1}`) · files={f1} · neighbors=none{d}\n\n"
          "## 2. masking rule — outputs\n- **Meta**: status=agrees · checked=2026-09-01(`{h2}`) · files=none(rule concept)"
          " · neighbors=none\n")
KO_MAP = ("## 1. 세이브 — 저장 규칙\n- **메타**: 상태=일치 · 확인=2026-09-01(`{h1}`) · 파일={f1} · 이웃=없음{d}\n\n"
          "## 2. 마스킹 규칙 — 산출물\n- **메타**: 상태=일치 · 확인=2026-09-01(`{h2}`) · 파일=없음(규칙 개념) · 이웃=없음\n")


def verdict(line):
    """표 한 줄의 판정 칸. 영어 표는 칸 사이가 두 칸 이상이다."""
    import re
    return re.split(r"\s{2,}", line.strip(), maxsplit=3)[-1]


class FreshEnglishTest(RepoCase):
    """BATON_LANG=en: fresh.sh의 영어 메시지. 지도는 영어 지도(- **Meta**: status=… · files=…)."""

    def en_map(self, h1, h2=None, docs=None, f1="`src/a.ts`"):
        self.write("CONCEPTS.md", EN_MAP.format(h1=h1, h2=h2 or h1, f1=f1, d=f" · docs={docs}" if docs else ""))
        self.commit("map")

    def out(self):
        return self.fresh(lang="en")

    def test_fresh_rule_concept_and_summary(self):
        self.en_map(self.base)
        out = self.out()
        self.assertEqual(verdict(self.line(out, "1")), "fresh")
        self.assertEqual(verdict(self.line(out, "2")), "rule concept — tracked only through decision changes")
        self.assertIn("\nSummary: re-check 0 · fresh 1 · rule concepts 1\n", out)
        self.assertTrue(out.startswith("#    Concept        Status   Verdict\n---- -------------- -------- ---"), out)

    def test_commit_count_singular_and_plural(self):
        self.en_map(self.base)
        self.write("src/a.ts", "b\n"); self.commit("c1")
        self.assertEqual(verdict(self.line(self.out(), "1")), "needs a re-check — 1 commit")
        self.write("src/a.ts", "c\n"); self.commit("c2")
        self.assertEqual(verdict(self.line(self.out(), "1")), "needs a re-check — 2 commits")

    def test_doc_verdicts(self):
        self.write("README.md", "r\n"); base = self.commit("readme")
        self.en_map(base, docs="`README.md`,`docs/gone.md`")
        self.assertEqual(verdict(self.line(self.out(), "1")), "needs a re-check — 1 doc path gone")
        self.en_map(base, docs="`README.md`")
        self.write("README.md", "s\n"); self.commit("readme 2")
        self.assertEqual(verdict(self.line(self.out(), "1")), "needs a re-check — 1 doc commit")
        self.write("src/a.ts", "b\n"); self.write("README.md", "t\n"); self.commit("both")
        self.assertEqual(verdict(self.line(self.out(), "1")), "needs a re-check — 1 commit · 2 doc commits")

    def test_rule_concept_with_moved_doc(self):
        self.write("README.md", "r\n"); base = self.commit("readme")
        self.write("CONCEPTS.md", "## 1. rule\n- **Meta**: status=agrees · checked=2026-09-01(`%s`) · files=none · neighbors=none"
                                  " · docs=`README.md`\n" % base); self.commit("map")
        self.write("README.md", "s\n"); self.commit("readme 2")
        self.assertEqual(verdict(self.line(self.out(), "1")), "needs a re-check — 1 doc commit (rule concept)")

    def test_baseline_verdicts(self):
        git(self.root, "checkout", "-qb", "side"); self.write("x.txt", "x\n"); side = self.commit("side")
        git(self.root, "checkout", "-q", "-")
        self.write("CONCEPTS.md",
                   "## 1. a\n- **Meta**: status=agrees · checked=unknown · files=`src/a.ts` · neighbors=none\n"
                   "## 2. b\n- **Meta**: status=agrees · checked=2026-09-01(`deadbee`) · files=`src/a.ts` · neighbors=none\n"
                   f"## 3. c\n- **Meta**: status=agrees · checked=2026-09-01(`{side}`) · files=`src/a.ts` · neighbors=none\n"
                   "## 4. d\n- **Meta**: status=agrees · checked=2026-09-01(`deadbee`) · files=none(rule concept) · neighbors=none\n"
                   "## 5. e\n- **Meta**: status=agrees · checked=2026-09-01(hash unknown) · files=none(rule concept)"
                   " · neighbors=none · docs=`DECISIONS.md`\n")
        self.commit("map")
        out = self.out()
        self.assertEqual(verdict(self.line(out, "1")), "needs a re-check — no baseline")
        self.assertEqual(verdict(self.line(out, "2")), "needs a re-check — baseline lost")
        self.assertEqual(verdict(self.line(out, "3")), "needs a re-check — baseline outside the current history")
        self.assertEqual(verdict(self.line(out, "4")), "needs a re-check — baseline lost (rule concept)")
        self.assertEqual(verdict(self.line(out, "5")),
                         "rule concept — tracked only through decision changes (no baseline — docs not checked)")
        self.assertIn("Summary: re-check 4 · fresh 0 · rule concepts 1", out)

    def test_path_verdicts(self):
        self.write(".gitignore", "nested/\n"); self.write("nested/x.ts", "x\n")  # 디스크에는 있고 이 저장소는 추적 안 함
        self.commit("nested")
        self.write("CONCEPTS.md",
                   f"## 1. a\n- **Meta**: status=agrees · checked=2026-09-01(`{self.base}`) · files=`src/gone.ts` · neighbors=none\n"
                   f"## 2. b\n- **Meta**: status=agrees · checked=2026-09-01(`{self.base}`) · files=`src/a.ts`,`src/gone.ts`"
                   " · neighbors=none\n"
                   f"## 3. c\n- **Meta**: status=agrees · checked=2026-09-01(`{self.base}`) · files=`nested/x.ts` · neighbors=none\n"
                   f"## 4. d\n- **Meta**: status=agrees · checked=2026-09-01(`{self.base}`) · files=`src/a.ts`,`nested/x.ts`"
                   " · neighbors=none\n"
                   f"## 5. e\n- **Meta**: status=agrees · checked=2026-09-01(`{self.base}`) · files= · neighbors=none\n")
        self.commit("map")
        out = self.out()
        self.assertEqual(verdict(self.line(out, "1")), "needs a re-check — 1 path gone")
        self.assertEqual(verdict(self.line(out, "2")), "needs a re-check — 1 path gone")
        self.assertEqual(verdict(self.line(out, "5")), "needs a re-check — path gone")  # 파일 목록이 비었다
        self.assertEqual(verdict(self.line(out, "3")), "needs a re-check — not tracked")
        self.assertEqual(verdict(self.line(out, "4")), "fresh (1 untracked file excluded)")

    def test_related_line_points_and_unknowns_are_reported(self):
        self.en_map(self.base)
        self.write("DECISIONS.md", '## 2026-09-30 save changed\n- Related: Concept 1 · concept "masking rule"\n', "a")
        self.commit("dec")
        out = self.out()
        self.assertEqual(verdict(self.line(out, "1")), "needs a re-check — a decision added since the check points to it (Related)")
        self.assertEqual(verdict(self.line(out, "2")),
                         "needs a re-check — a decision added since the check points to it (Related) (rule concept)")
        self.assertIn("Decision and instruction changes: 1 commit since the oldest check (%s)" % self.base, out)
        self.assertIn("  Format: dated headings · new decisions 1 · Related: lines 1 · gaps 0", out)

    def test_pointer_keeps_verdict_and_negation_and_unknowns(self):
        self.en_map(self.base)
        self.write("src/a.ts", "b\n"); self.commit("code")
        self.write("DECISIONS.md", '## 2026-09-30 x\n- Related: Concept 1\n## 2026-10-01 y\n'
                                   '- Related: concept "no such name" · Concept 9 · Concept 2 is unchanged\n## 2026-10-02 z\n', "a")
        self.commit("dec")
        out = self.out()
        self.assertEqual(verdict(self.line(out, "1")), "needs a re-check — 1 commit · a new decision points to it (Related)")
        self.assertEqual(verdict(self.line(out, "2")), "rule concept — tracked only through decision changes")
        self.assertIn("Related entries in new decisions that match no concept section (name mismatch, number with no section, "
                      "parser failure) — **this is not 0, they could not be counted**:\n     Concept 9 (no section)\n"
                      "     no such name\n", out)
        self.assertIn("  Format: dated headings · new decisions 3 · Related: lines 2 · gaps 1\n"
                      "  → A decision without a Related: line doesn't say which concepts it touched. "
                      "Report it as a gap in the update path.", out)

    def test_table_and_unknown_decision_formats(self):
        self.en_map(self.base)
        self.write("DECISIONS.md", "| ID | decision | why |\n|---|---|---|\n| P1 | keep saves local | privacy |\n")
        self.commit("dec")
        out = self.out()
        self.assertIn("  Format: table (decision IDs) · new decision rows 1  — P1 \n"
                      "  → This format has no Related: lines. To see which concept a decision touches, find its ID in the "
                      "concept sections.\n     P1: not mentioned in the concept map — check which concept it touches", out)
        self.write("DECISIONS.md", "decided things, no headings\n"); self.commit("dec 2")
        self.assertIn("  Unknown format — **this is not 0, it could not be counted.** Open DECISIONS.md and check it directly.",
                      self.out())

    def test_no_meta_partial_meta_fence_and_mixed_files(self):
        self.write("CONCEPTS.md", "## 1. a\nbody\n"); self.commit("map")
        r = subprocess.run(["bash", FRESH, os.path.join(self.root, "CONCEPTS.md"), self.root], capture_output=True, text=True,
                           env=dict(os.environ, BATON_LANG="en"))
        self.assertEqual(r.returncode, 2)
        self.assertTrue(r.stdout.startswith("No metadata lines at all (concepts: 1). **Freshness can't be computed — this is "
                                            "not 0, it could not be counted.**"), r.stdout)
        self.assertIn("  - **Meta**: status=… · checked=YYYY-MM-DD(`hash`) · files=`path from the repo root` · neighbors=…",
                      r.stdout)
        meta = f"- **Meta**: status=agrees · checked=2026-09-01(`{self.base}`) · files=`src/a.ts`,`DECISIONS.md` · neighbors=none\n"
        self.write("CONCEPTS.md", "## 1. a\n" + meta + "## 2. b\nbody\n## 3. c\n" + meta + "```\nopen\n\n## 4. d\n" + meta)
        self.commit("map 2")
        self.write("DECISIONS.md", "## 2026-09-30 x\n- Related: none\n", "a"); self.commit("dec")  # 이 경고는 결정 변동이 있을 때만 나온다
        out = self.out()
        self.assertTrue(out.startswith("Warning: only 2 of 3 concepts have a metadata line. The rest are not in the table.\n\n"
                                       "Warning: a code fence opened at line 7 is never closed — 1 concept after it could not "
                                       "be read\n\n#"), out)
        self.assertIn("\nWarning: instruction or decision files are listed in files= (concepts: 2).\n", out)


class EnglishMapParityTest(RepoCase):
    """같은 내용의 한국어 지도와 영어 지도는 파서·check.sh·fresh.sh에서 같게 읽힌다 — 이름·상태 낱말만 다르다."""

    def both(self, h1, f1="`src/a.ts`", docs=None):
        d = docs or ""
        self.write("KO.md", KO_MAP.format(h1=h1, h2=h1, f1=f1, d=d and f" · 문서={d}"))
        self.write("CONCEPTS.md", EN_MAP.format(h1=h1, h2=h1, f1=f1, d=d and f" · docs={d}"))
        self.commit("maps")

    def meta(self, name):
        import sys
        r = subprocess.run([sys.executable, os.path.join(os.path.dirname(FRESH), "concepts.py"), os.path.join(self.root, name),
                            "meta"], capture_output=True, text=True, check=True)
        return [l.split("\t") for l in r.stdout.splitlines()]

    def test_parser_reads_the_same_fields(self):
        self.write("README.md", "r\n"); base = self.commit("readme")
        self.both(base, docs="`README.md`")
        ko, en = self.meta("KO.md"), self.meta("CONCEPTS.md")
        self.assertEqual(len(ko), 2)
        for k, e in zip(ko, en):
            # 번호·날짜·해시·문서는 같다. 이름·상태·이웃('없음'/'none')·규칙 개념의 파일 값은 지도의 낱말 그대로
            self.assertEqual([k[i] for i in (0, 3, 4, 7)], [e[i] for i in (0, 3, 4, 7)])
        self.assertEqual(ko[0][5], en[0][5])
        self.assertEqual(en[0][1:3], ["save", "agrees"])
        self.assertEqual(en[1][5], "none(rule concept)")

    def test_same_verdicts_in_both_output_languages(self):
        self.write("README.md", "r\n"); base = self.commit("readme")
        self.both(base, docs="`README.md`")
        self.write("src/a.ts", "b\n"); self.write("README.md", "s\n"); self.commit("both moved")
        self.write("DECISIONS.md", '## 2026-09-30 x\n- 관련: 개념 2\n- Related: Concept 2\n', "a"); self.commit("dec")
        for lang in ("ko", "en"):
            ko, en = self.fresh(lang=lang, name="KO.md"), self.fresh(lang=lang)
            with self.subTest(lang=lang):
                self.assertEqual([verdict(self.line(ko, n)) for n in "12"], [verdict(self.line(en, n)) for n in "12"])
                self.assertEqual(ko.split("\n\n", 1)[1], en.split("\n\n", 1)[1])  # 요약 줄·결정 변동도 같다
        self.assertEqual(verdict(self.line(self.fresh(lang="ko"), "1")), "재확인 필요 — 커밋 1건 · 문서 커밋 1건")

    def test_check_finds_the_same(self):
        self.both(self.base)
        for name, row in (("KO.md", "| 1 | 세이브 | 일치 |\n| 2 | 마스킹 규칙 | 일치 |\n"), ("CONCEPTS.md", "| 1 | save | agrees |\n")):
            with open(os.path.join(self.root, name), "a", encoding="utf-8") as f:  # 요약표(영어 지도는 2번 행이 빠졌다)와 약칭 근거
                f.write("\n| # | c | s |\n|---|---|---|\n" + row.replace("| 2 | 마스킹 규칙 | 일치 |\n", "") + "\nsee `a.ts:1`\n")
        self.commit("tables")
        for lang in ("ko", "en"):
            outs = []
            for name in ("KO.md", "CONCEPTS.md"):
                r = subprocess.run(["bash", CHECK, os.path.join(self.root, name)], capture_output=True, text=True,
                                   env=dict(os.environ, BATON_LANG=lang))
                outs.append((r.returncode, r.stdout.split("\n", 2)[2]))  # 첫 줄(파일 이름)만 다르다
            with self.subTest(lang=lang):
                self.assertEqual(outs[0], outs[1])
                self.assertEqual(outs[0][0], 1)
                self.assertIn({"ko": "경로 누락: `a.ts` → 루트 상대로는 `src/a.ts`",
                               "en": "Incomplete path: `a.ts` → relative to the repo root it is `src/a.ts`"}[lang], outs[0][1])
                self.assertIn({"ko": "본문에만 있고 표에 없음: 개념 2", "en": "Has a section but is not in the table: concept 2"}[lang],
                              outs[0][1])


class CheckEnglishTest(RepoCase):
    """check.sh·lib.sh의 영어 메시지."""

    def run_check(self, lang="en", path="CONCEPTS.md"):
        r = subprocess.run(["bash", CHECK] + ([path] if path is not None else []), capture_output=True, text=True,
                           env=dict(os.environ, BATON_LANG=lang), cwd=self.root)
        return r.returncode, r.stdout, r.stderr

    def test_clean_map_lists_every_check(self):
        self.write("CONCEPTS.md", "| # | Concept | Status | Severity | One line |\n|---|---|---|---|---|\n| 1 | save | agrees | — | x |\n"
                                  "| 2 | rule | resolved(2026-09-01) | — | y |\n\n" +
                                  EN_MAP.format(h1=self.base, h2=self.base, f1="`src/a.ts`", d="")
                                  .replace("status=agrees · checked=2026-09-01(`%s`) · files=none" % self.base,
                                           "status=resolved(2026-09-01) · checked=2026-09-01(`%s`) · files=none" % self.base)
                                  + "\nSee `src/a.ts:1`.\n")
        self.commit("map")
        rc, out, _ = self.run_check()
        self.assertEqual(rc, 0, out)
        self.assertEqual(out.splitlines(), [
            "Checking: %s/CONCEPTS.md" % os.path.basename(self.root),
            "Repo root: %s" % os.path.basename(self.root),
            "",
            "[1] Summary table rows and concept sections match one to one",
            "[2] Evidence paths can be used to compute freshness",
            "    No findings (evidence paths: 1, all tracked relative to the repo root)",
            "[3] References between concepts go both ways",
            "    References: 0 · one way only: 0",
            "[4] Status words outside the closed list",
            "    No findings (distinct values checked: 2)",
            "[5] The files= entry lists only evidence of actual behavior",
            "    No findings",
            "[6] Metadata lines (needed to compute freshness)",
            "    Concepts: 2 · metadata lines: 2",
            "[7] The parser read to the end (no code fence left open)",
            "    No findings",
            "",
            "Total findings: 0"])

    def test_findings(self):
        self.write(".gitignore", "nested/\n"); self.write("nested/n.ts", "n\n")  # 디스크에는 있고 추적 안 함(중첩 저장소와 같게 보인다)
        self.write("src/deep/b.ts", "b\n"); self.write("src/very-short.ts", "s\n"); self.commit("files")
        self.write("CONCEPTS.md",
                   "| # | Concept | Status |\n|---|---|---|\n| 1 | a | agrees |\n| 9 | ghost | agrees |\n\n"
                   "## 1. a\n- **Meta**: status=done · checked=unknown · files=`src/a.ts`,`AGENTS.md` · neighbors=Concept 2(premise)\n"
                   "Evidence `deep/b.ts:1` `short.ts:2` `nested/n.ts:3` `missing.ts:4`\n\n"
                   "## 2. b\nno metadata line\n```\nopen fence\n\n## 3. c\n")
        self.commit("map")
        rc, out, _ = self.run_check()
        self.assertEqual(rc, 1)
        for want in ("    In the table but has no section: concept 9",
                     "    Has a section but is not in the table: concept 2",
                     "    Incomplete path: `deep/b.ts` → relative to the repo root it is `src/deep/b.ts`",
                     "    Short name: `short.ts` → the actual file is `src/very-short.ts`",
                     "    Not tracked (nested repo): `nested/n.ts` — run git log in that repo separately",
                     "    Broken reference: `missing.ts` — no file with that name in the repo",
                     "    → 4 of 4 evidence paths can't be used to compute freshness as written",
                     "    One way only: concept 1 points to concept 2, but 2 does not point back",
                     "    References: 1 · one way only: 1",
                     "    Not in the closed list: 'done'",
                     "    Concepts that list instruction or decision files: 1 — this breaks the freshness signal",
                     "    Concepts: 2 · metadata lines: 1",
                     "    a code fence opened at line 12 is never closed — 1 concept after it could not be read",
                     "Total findings: 11"):
            with self.subTest(want=want):
                self.assertIn(want + "\n", out)

    def test_korean_and_english_status_words_are_both_closed(self):
        lines = "".join(f"## {i}. c{i}\n- **Meta**: status={s} · checked=unknown · files=`src/a.ts` · neighbors=none\n"
                        for i, s in enumerate(["agrees", "Not built yet", "stale doc", "undecided", "two sources of truth",
                                               "could not check", "resolved(2026-01-01)", "retired(2026-01-02, merged)",
                                               "일치", "중복 정본", "해소됨(2026-01-01)"], 1))
        self.write("CONCEPTS.md", lines); self.commit("map")
        rc, out, _ = self.run_check()
        self.assertIn("[4] Status words outside the closed list\n    No findings (distinct values checked: 11)\n", out)

    def test_usage_and_missing_file(self):
        rc, _, err = self.run_check(path=None)
        self.assertEqual(rc, 2)
        self.assertEqual(err.splitlines()[0], "Usage: check.sh <path to CONCEPTS.md>")
        rc, _, err = self.run_check(path="nope.md")
        self.assertEqual((rc, err.strip()), (2, "No file at that path: nope.md"))
        r = subprocess.run(["bash", FRESH], capture_output=True, text=True, env=dict(os.environ, BATON_LANG="en"), cwd=self.root)
        self.assertEqual(r.stderr.splitlines()[0], "Usage: fresh.sh <path to CONCEPTS.md> [repo root]")
        r = subprocess.run(["bash", FRESH], capture_output=True, text=True, env=dict(os.environ, BATON_LANG="ko"), cwd=self.root)
        self.assertEqual(r.stderr.splitlines()[0], "사용법: fresh.sh <CONCEPTS.md 경로> [저장소 루트]")


class LocaleFallbackTest(RepoCase):
    """BATON_LANG이 없으면 로캘을 따른다 — ko_KR이면 한국어, C.UTF-8이면 영어. 실제 설정 파일은 읽지 않게 따로 둔다."""

    def run_with(self, script, locale):
        env = {k: v for k, v in os.environ.items() if k not in ("BATON_LANG", "LC_ALL", "LC_MESSAGES", "LANG")}
        env.update(LANG=locale, XDG_CONFIG_HOME=os.path.join(self.root, ".cfg"))
        r = subprocess.run(["bash", script, os.path.join(self.root, "CONCEPTS.md"), self.root], capture_output=True,
                           text=True, env=env)
        return r.stdout

    def test_locale_picks_the_language(self):
        self.write("CONCEPTS.md", EN_MAP.format(h1=self.base, h2=self.base, f1="`src/a.ts`", d="")); self.commit("map")
        self.assertIn("요약: 재확인 0 · 신선 1 · 규칙 개념 1", self.run_with(FRESH, "ko_KR.UTF-8"))
        self.assertIn("Summary: re-check 0 · fresh 1 · rule concepts 1", self.run_with(FRESH, "C.UTF-8"))
        self.assertIn("\n지적 총 1건\n", self.run_with(CHECK, "ko_KR.UTF-8"))  # 요약표가 없다 — 1건
        self.assertIn("\nTotal findings: 1\n", self.run_with(CHECK, "C.UTF-8"))


class VerdictDocsTest(unittest.TestCase):
    """fresh.sh가 내는 판정 이름이 문서 판정 표에 모두 있다 — 한국어 이름은 docs/GUIDE.ko.md, 영어 이름은 docs/GUIDE.md와
    skills/driftmap/SKILL.md(영어 정본). 이름은 fresh.sh의 언어별 메시지 묶음에서 읽는다. 수가 든 판정은 수 자리를 N으로 둔다."""
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def read(self, rel):
        with open(os.path.join(self.ROOT, rel), encoding="utf-8") as f:
            return f.read()

    def tables(self):
        """{'ko': {변수: 값}, 'en': {변수: 값}} — fresh.sh 맨 앞 'if [ "$L" = ko ]; then … else … fi' 묶음."""
        import re
        src = self.read("lib/fresh.sh")
        m = re.search(r'if \[ "\$L" = ko \]; then\n(.*?)\nelse\n(.*?)\nfi\n', src, re.S)
        self.assertIsNotNone(m, "fresh.sh 메시지 묶음을 못 찾았다")
        pair = lambda block: dict(re.findall(r'\b([A-Z_]+)="([^"]*)"', block))
        return {"ko": pair(m.group(1)), "en": pair(m.group(2))}

    def labels(self, t):
        n = lambda f: f.split("|")[-1].replace("%s", "N")  # 영어는 '단수|복수' — 문서는 복수 꼴로 적는다
        rc = t["V_RC"] + " — "
        out = {t["V_FRESH"], t["V_TRACK"], rc + t["V_NOBASE"], rc + t["V_LOST"], rc + t["V_OUTSIDE"], rc + t["V_GONE"],
               rc + t["V_UNTR"], rc + n(t["N_COMMIT"]), rc + n(t["N_DOCC"])}
        return out, n(t["N_DOCGONE"])

    def test_every_verdict_name_is_in_the_docs(self):
        t = self.tables()
        self.assertEqual(set(t["ko"]), set(t["en"]), "두 언어 묶음의 변수가 같아야 한다")
        ko, ko_docgone = self.labels(t["ko"])
        en, en_docgone = self.labels(t["en"])
        self.assertEqual(len(ko), 9)
        self.assertEqual(len(en), 9)
        for rel, labels in (("docs/GUIDE.ko.md", ko | {t["ko"]["V_RC"] + " — " + ko_docgone}),
                            ("skills/driftmap/SKILL.md", en | {t["en"]["V_RC"] + " — " + en_docgone}),
                            # docs/GUIDE.md는 문서 판정 둘을 한 칸에 'N doc commits · doc paths gone'으로 적는다
                            ("docs/GUIDE.md", en | {"doc paths gone"})):
            text = self.read(rel)
            for label in sorted(labels):
                with self.subTest(doc=rel, label=label):
                    self.assertIn(label, text)

    def test_verdict_count_matches_across_docs(self):
        self.assertIn("nine verdicts", self.read("skills/driftmap/SKILL.md"))
        self.assertIn("nine verdicts", self.read("docs/GUIDE.md"))
        self.assertIn("판정은 아홉 가지", self.read("docs/GUIDE.ko.md"))
        self.assertIn("outside the current history", self.read("docs/GUIDE.md"))

    def test_rule_concept_without_hash_reason_is_written(self):  # 해시 미상 규칙 개념이 알림을 안 내는 이유
        self.assertIn("A rule concept whose recorded commit is unknown does not trigger the notice",
                      self.read("skills/driftmap/SKILL.md"))
        self.assertIn("미상인 규칙 개념은 알림을 내지 않습니다", self.read("docs/GUIDE.ko.md"))
        self.assertIn("A rule concept whose commit is unknown does not trigger the notice", self.read("docs/GUIDE.md"))


class GuideOutputTest(RepoCase):
    """docs/GUIDE.md·GUIDE.ko.md의 예시 출력(목숨·점수·레벨)이 실제 fresh.sh 출력과 같다. 영어 예시는 영어 지도로, 한국어 예시는 한국어 지도로."""
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def doc_block(self, rel, head):
        with open(os.path.join(self.ROOT, rel), encoding="utf-8") as f:
            lines = f.read().splitlines()
        i = lines.index(head)
        j = next(k for k in range(i, len(lines)) if lines[k].startswith(("Summary:", "요약:")))
        return "\n".join(lines[i:j + 1])

    def demo(self, en):
        os.remove(os.path.join(self.root, "DECISIONS.md"))  # 예시 저장소에는 결정 기록이 없다
        self.write("src/lives.ts", "3\n"); self.write("src/score.ts", "10\n"); self.write("src/levels.ts", "[]\n")
        h = self.commit("demo")
        if en:
            meta = "- **Meta**: status={s} · checked={c} · files=`src/{f}.ts` · neighbors={n}"
            rows = [("lives — starting number of lives", "agrees", f"2026-11-20(`{h}`)", "lives", "Concept 2(premise)"),
                    ("score — points per coin", "agrees", f"2026-11-20(`{h}`)", "score", "Concept 1(premise)"),
                    ("levels — level list, still empty", "not built yet", "unknown", "levels", "none")]
        else:
            meta = "- **메타**: 상태={s} · 확인={c} · 파일=`src/{f}.ts` · 이웃={n}"
            rows = [("목숨 — 시작할 때 목숨 수", "일치", f"2026-11-20(`{h}`)", "lives", "개념 2(전제)"),
                    ("점수 — 코인 하나당 점수", "일치", f"2026-11-20(`{h}`)", "score", "개념 1(전제)"),
                    ("레벨 — 레벨 목록, 아직 비어 있음", "미구현", "미상", "levels", "없음")]
        self.write("CONCEPTS.md", "".join(f"## {i}. {t}\n\n" + meta.format(s=s, c=c, f=f, n=n) + "\n\n"
                                          for i, (t, s, c, f, n) in enumerate(rows, 1)))
        self.commit("map")
        self.write("src/lives.ts", "4\n"); self.commit("lives")

    def test_english_example_matches_real_output(self):
        self.demo(en=True)
        out = self.fresh(lang="en").rstrip("\n")
        self.assertEqual(out, self.doc_block("docs/GUIDE.md", "#    Concept   Status          Verdict"))

    def test_korean_example_matches_real_output(self):
        self.demo(en=False)
        out = self.fresh(lang="ko").rstrip("\n")
        self.assertEqual(out, self.doc_block("docs/GUIDE.ko.md", "#    개념                 상태       판정"))


if __name__ == "__main__":
    unittest.main()
