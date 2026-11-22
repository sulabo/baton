#!/usr/bin/env python3
"""concepts.index — 개념 색인(세션 첫 프롬프트에 넣는 개념마다 한 줄)."""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import concepts

HEAD = concepts.INDEX_HEAD.format(path="CONCEPTS.md")
MAP = """# 지도

## 요약

| # | 개념 | 상태 | 심각도 | 한 줄 |
|---|---|---|---|---|
| 2 | 저장 | 미결 | 낮음 | 저장 슬롯이 셋이다 |
| **1** | 엔딩 | 일치 | — | 결말은 점수로 가른다 |

## 1. 엔딩 판정 — 무엇이 결말을 가르는가

- **메타**: 상태=일치 · 확인=2026-11-20(`9cd1928`) · 파일=`src/end.ts`,`src/score.ts`,`src/a.ts`,`src/b.ts`,`src/c.ts` · 이웃=없음 · 문서=`docs/g.md`

본문.

## 2. 저장 슬롯

- **메타**: 상태=미결 · 확인=2026-11-20(`9cd1928`) · 파일=`src/save.ts` · 이웃=개념 1(전제) · 문서=없음
"""


class IndexFormatTest(unittest.TestCase):
    def test_one_line_per_concept_with_summary_and_files(self):
        out = concepts.index(MAP)
        self.assertEqual(out, "\n".join([
            HEAD,
            "1. 엔딩 판정 — 무엇이 결말을 가르는가 · 파일: src/end.ts, src/score.ts, src/a.ts (+2)",  # 제목의 '—' 뒤가 요약
            "2. 저장 슬롯 · 파일: src/save.ts",  # 제목에 '—'가 없으면 요약 없이 — 요약표의 한 줄 칸('저장 슬롯이 셋이다')은 읽지 않는다
        ]) + "\n")
        self.assertEqual(out, concepts.index(MAP))  # 결정론

    def test_docs_path_goes_into_header(self):
        out = concepts.index(MAP, path="docs/CONCEPTS.md")
        self.assertTrue(out.startswith("[baton] 이 저장소 개념 지도(docs/CONCEPTS.md) 색인이다."))

    def test_no_map_and_empty_map(self):
        self.assertEqual(concepts.index(""), "")
        self.assertEqual(concepts.index("# 지도\n\n## 요약\n\n없음\n"), "")
        self.assertEqual(concepts.index("## 1. 하나\n- **메타**: 상태=폐기됨 · 파일=`a.py`\n"), "")  # 폐기만 있으면 빈 색인

    def test_cli(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "CONCEPTS.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write(MAP)
            r = subprocess.run([sys.executable, os.path.join(HERE, "concepts.py"), p, "index"],
                               capture_output=True, text=True, check=True)
        self.assertEqual(r.stdout, concepts.index(MAP))


class IndexQuirkTest(unittest.TestCase):
    def test_meta_value_with_middle_dot_continues_previous_key(self):
        text = "## 1. 하나\n- **메타**: 상태=일치 · 파일=src/a.py · src/b.py · 이웃=없음\n"
        self.assertIn("1. 하나 · 파일: src/a.py, src/b.py\n", concepts.index(text))

    def test_files_with_and_without_backticks_line_numbers_and_notes(self):
        text = ("## 1. 하나\n- **메타**: 상태=일치 · 파일=`a.py:12`(코드), b/c.py, `a.py` · 이웃=없음\n\n"
                "## 2. 규칙\n- **메타**: 상태=일치 · 파일=없음(규칙 개념) · 이웃=없음\n\n"
                "## 3. 메타 없음\n본문만.\n")
        out = concepts.index(text).splitlines()
        self.assertEqual(out[1:], ["1. 하나 · 파일: a.py, b/c.py", "2. 규칙", "3. 메타 없음"])

    def test_retired_concepts_are_skipped_by_meta_or_table(self):
        text = ("| # | 개념 | 상태 | 한 줄 |\n|---|---|---|---|\n| 2 | 둘 | 폐기됨 | 옛것 |\n\n"
                "## 1. 하나\n- **메타**: 상태=폐기됨(2026-11-01) · 파일=`a.py`\n\n## 2. 둘\n본문.\n\n## 3. 셋\n- **메타**: 상태=일치\n")
        self.assertEqual(concepts.index(text).splitlines()[1:], ["3. 셋"])

    def test_table_without_known_header_is_not_read_and_fenced_headings_are_not_concepts(self):
        text = "| a | b |\n|---|---|\n| 1 | 요약 아님 |\n\n```\n## 9. 예시\n```\n## 1. 하나\n"
        self.assertEqual(concepts.index(text).splitlines()[1:], ["1. 하나"])


class IndexBudgetTest(unittest.TestCase):
    def big_map(self, n):
        parts = []
        for i in range(1, n + 1):
            files = ",".join("`src/mod%02d/file%d.py`" % (i, k) for k in range(4))
            parts.append("## %d. 개념%02d — 이 개념의 한 줄 요약이다 조금 길게\n- **메타**: 상태=일치 · 파일=%s\n" % (i, i, files))
        return "\n".join(parts)

    def test_fits_under_default_limit(self):
        for n in (1, 5, 12, 30):
            out = concepts.index(self.big_map(n))
            self.assertLessEqual(len(out), concepts.INDEX_LIMIT_CHARS, n)
            self.assertTrue(out.startswith(HEAD))

    def test_shrink_order_summaries_then_files_then_concepts(self):
        text = self.big_map(12)
        full = concepts.index(text, 10 ** 6)
        self.assertEqual(full.count("한 줄 요약"), 12)
        # 요약을 뒤쪽부터 뗀다 — 파일 셋은 그대로
        out = concepts.index(text, len(full) - 1)
        self.assertEqual(out.count("한 줄 요약"), 11)
        self.assertNotIn("요약이다", out.splitlines()[-1])
        self.assertEqual(out.count("(+1)"), 12)
        # 요약을 다 뗀 다음에야 파일을 줄인다
        no_sum = concepts.index(text, len(full) - 12 * len(" — 이 개념의 한 줄 요약이다 조금 길게"))
        self.assertEqual((no_sum.count("한 줄 요약"), no_sum.count("(+1)")), (0, 12))
        one = concepts.index(text, len(no_sum) - 1)
        self.assertEqual((one.count("(+1)"), one.count("(+3)")), (11, 1))
        self.assertNotIn("…", one)
        # 파일까지 다 줄여도 안 맞으면 뒤쪽 개념을 빼고 몇 개 더 있는지 말한다
        cut = concepts.index(text, 400)
        self.assertLessEqual(len(cut), 400)
        self.assertNotIn("(+1)", cut)
        lines = cut.splitlines()
        shown = len(lines) - 2
        self.assertEqual(lines[-1], "… %d개 더 — CONCEPTS.md 요약표" % (12 - shown))
        self.assertGreater(shown, 0)

    def test_too_small_for_one_concept_is_empty(self):
        self.assertEqual(concepts.index(self.big_map(3), len(HEAD) + 5), "")
        self.assertEqual(concepts.index(self.big_map(3), 0), "")


class RealMapTest(unittest.TestCase):
    def test_this_repo_map_first_files_exist(self):
        root = os.path.dirname(HERE)
        with open(os.path.join(root, "CONCEPTS.md"), encoding="utf-8") as f:
            out = concepts.index(f.read())
        self.assertLessEqual(len(out), concepts.INDEX_LIMIT_CHARS)
        firsts = [l.split(" · 파일: ", 1)[1].split(", ")[0].split(" (+")[0] for l in out.splitlines()[1:] if " · 파일: " in l]
        self.assertGreater(len(firsts), 5)
        self.assertEqual([p for p in firsts if not os.path.exists(os.path.join(root, p))], [])


if __name__ == "__main__":
    unittest.main()
