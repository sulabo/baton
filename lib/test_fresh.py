#!/usr/bin/env python3
"""fresh.sh 로드맵 7단계: 확인 이후 새 결정의 '관련' 줄이 가리킨 개념을 재확인 대상으로 올린다."""
import os
import subprocess
import tempfile
import unittest

FRESH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fresh.sh")


def git(root, *args):
    return subprocess.run(["git", "-C", root, *args], check=True, capture_output=True, text=True).stdout.strip()


class FreshPointedTest(unittest.TestCase):
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

    def fresh(self):
        r = subprocess.run(["bash", FRESH, os.path.join(self.root, "CONCEPTS.md"), self.root], capture_output=True, text=True)
        return r.stdout

    def line(self, out, num):
        return next(l for l in out.splitlines() if l.startswith(num + " "))

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


if __name__ == "__main__":
    unittest.main()
