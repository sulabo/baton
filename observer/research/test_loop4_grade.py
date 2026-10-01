#!/usr/bin/env python3
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import loop4_grade


def diff_for(path, added_lines):
    body = "\n".join("+" + line for line in added_lines)
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@\n{body}\n"


class Loop4GradeTest(unittest.TestCase):
    def test_no_player_guide_edits_require_manual_confirmation(self):
        verdict, tags, files = loop4_grade.grade("")
        self.assertEqual(verdict, "확인필요(변경 없음)")
        self.assertEqual(tags, [])
        self.assertEqual(files, [])

    def test_code_only_diff_fails_overall(self):
        verdict, tags, files = loop4_grade.grade(diff_for("src/render/hud.ts", ["const x = 1;"]))
        self.assertEqual(verdict, "오답(코드수정)")
        self.assertEqual(tags, ["코드수정"])
        self.assertEqual(files, ["src/render/hud.ts"])

    def test_current_style_claim_with_qualifier_only_in_quote_is_wrong(self):
        diff = diff_for(
            "PLAYER-GUIDE.md",
            [
                "엔딩은 잔상 수로 갈린다.",
                "> 예정된 규칙은 아직 미구현이다.",
            ],
        )
        verdict, tags, _ = loop4_grade.grade(diff)
        self.assertEqual(verdict, "오답(미구현을 현재 동작으로)")
        self.assertIn("본문:엔딩은 잔상 수로 갈린다.", tags)

    def test_valid_qualified_candidate_is_marked_as_automatic_candidate(self):
        diff = diff_for("PLAYER-GUIDE.md", ["현재 빌드에서는 DEBT 기준이고, 잔상 수 규칙은 아직 미구현이다."])
        verdict, tags, files = loop4_grade.grade(diff)
        self.assertEqual(verdict, "자동 후보(한정 표기)")
        self.assertEqual(tags, [])
        self.assertEqual(files, ["PLAYER-GUIDE.md"])

    def test_run_filter_skips_not_ok_and_error_max_turns_without_manual_evidence(self):
        self.assertEqual(loop4_grade.can_grade_run({"ok": False}), (False, "채점 불가(not ok)"))
        self.assertEqual(loop4_grade.can_grade_run({"ok": True, "subtype": "error_max_turns"}), (False, "채점 불가(error_max_turns)"))
        self.assertEqual(loop4_grade.can_grade_run({"ok": True, "subtype": "error_max_turns", "manual_evidence": "read transcript"}), (True, ""))

    def test_main_prints_ungradable_and_automatic_candidate(self):
        with tempfile.TemporaryDirectory() as d:
            runs = [
                {"arm": "off", "i": 1, "file": "off-1", "ok": False, "cost_usd": 1.2},
                {"arm": "map", "i": 1, "file": "map-1", "ok": True, "subtype": "error_max_turns", "cost_usd": 2.3},
                {"arm": "concept", "i": 1, "file": "concept-1", "ok": True, "cost_usd": 3.4},
            ]
            with open(os.path.join(d, "runs.json"), "w", encoding="utf-8") as f:
                json.dump(runs, f)
            with open(os.path.join(d, "concept-1.diff"), "w", encoding="utf-8") as f:
                f.write(diff_for("PLAYER-GUIDE.md", ["현재 빌드에서는 DEBT 기준이고, 잔상 수 규칙은 아직 미구현이다."]))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                loop4_grade.main(d)
        text = out.getvalue()
        self.assertIn("off-1: 채점 불가(not ok)", text)
        self.assertIn("map-1: 채점 불가(error_max_turns)", text)
        self.assertIn("concept-1: 자동 후보(한정 표기)", text)


if __name__ == "__main__":
    unittest.main()
