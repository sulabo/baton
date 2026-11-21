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

    def fresh(self, cwd=None):
        r = subprocess.run(["bash", FRESH, os.path.join(self.root, "CONCEPTS.md"), self.root], capture_output=True, text=True,
                           cwd=cwd)
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


if __name__ == "__main__":
    unittest.main()
