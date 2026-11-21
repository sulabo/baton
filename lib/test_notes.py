#!/usr/bin/env python3
"""개념 지도 ↔ 옵시디언 노트: 왕복 동일·폴더 규칙·검사·낱말 단위 별칭 찾기·경로 찾기."""
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import notes

MAP = """# 지도

> 머리말

## 요약

| # | 개념 | 상태 | 심각도 | 한 줄 |
|---|---|---|---|---|
| 2 | 레벨 | 미구현 | 낮음 | 레벨 한 줄 |
| 1 | 세이브 | 일치 | — | 세이브: 한 줄 # 주석 아님 |

## 1. 세이브 — 저장과 불러오기

- **메타**: 상태=일치 · 확인=2026-09-01(`0000000`) · 파일=`src/save/save.py`,`src/save/load.py` · 이웃=개념 2(전제) · 문서=`README.md` · 별칭=세이브, 저장

- **정해진 것**: a
- **실제 동작**:
  - `src/save/save.py:3`
- **설명된 곳**: c
- **어긋남**: 없음.

## 2. 레벨

- **메타**: 상태=미구현 · 확인=2026-09-01(`0000000`) · 파일=`src/level/map.py` · 이웃=개념 1(정본)

- **정해진 것**: b

## 유지 규칙

- x
"""
S1, S2 = "src/save/세이브 — 저장과 불러오기.md", "src/level/레벨.md"


def edit(ns, path, old, new):
    assert old in ns[path], (path, old)
    ns = dict(ns)
    ns[path] = ns[path].replace(old, new)
    return ns


class RoundTripTest(unittest.TestCase):
    def test_repo_map_is_byte_identical(self):
        path = os.path.join(HERE, "..", "CONCEPTS.md")
        with open(path, encoding="utf-8", newline="") as fh:
            text = fh.read()
        ns = notes.to_notes(text)
        self.assertEqual(len(ns), 14 + 1)
        self.assertEqual(notes.to_concepts_md(ns), text)
        self.assertEqual(notes.check(ns), [])

    def test_sample_round_trip_and_note_shape(self):
        ns = notes.to_notes(MAP)
        self.assertEqual(sorted(ns), sorted([S1, S2, notes.INDEX]))
        self.assertEqual(notes.to_concepts_md(ns), MAP)
        n = notes.parse_note(S1, ns[S1])
        self.assertEqual(n["fm"]["aliases"], ["세이브", "저장"])
        self.assertEqual(n["fm"]["table_name"], "세이브")
        self.assertEqual(n["fm"]["summary"], "세이브: 한 줄 # 주석 아님")
        self.assertEqual(n["neighbors"], [("전제", ["레벨"])])
        self.assertNotIn("table_name", notes.parse_note(S2, ns[S2])["fm"])

    def test_table_order_mismatch_then_severity_then_number(self):
        ns = edit(notes.to_notes(MAP), S1, 'status: "일치"', 'status: "중복 정본"')
        ns = edit(ns, S1, 'severity: "—"', 'severity: "중간"')
        rows = [l for l in notes.to_concepts_md(ns).split("\n") if l.startswith("| 1 ") or l.startswith("| 2 ")]
        self.assertEqual([r[:4] for r in rows], ["| 1 ", "| 2 "])

    def test_one_sided_link_appears_on_both_sides(self):
        ns = edit(notes.to_notes(MAP), S2, "- 정본: [[세이브 — 저장과 불러오기]]", "")
        out = notes.to_concepts_md(ns)
        self.assertIn("· 이웃=개념 1(전제)\n", out)        # 레벨 쪽: 반대쪽에서 계산
        self.assertIn("· 이웃=개념 2(전제) · ", out)       # 세이브 쪽: 적힌 그대로
        self.assertEqual(notes.check(ns), [])

    def test_grouped_neighbors_are_one_bullet(self):
        text = MAP.replace("이웃=개념 2(전제)", "이웃=개념 1·2(전제)")
        ns = notes.to_notes(text)
        self.assertIn("- 전제: [[세이브 — 저장과 불러오기]], [[레벨]]", ns[S1])
        self.assertEqual(notes.to_concepts_md(ns), text)

    def test_obsidian_block_list_is_read(self):
        ns = edit(notes.to_notes(MAP), S1, 'aliases: ["세이브", "저장"]', "aliases:\n  - 세이브\n  - 저장")
        self.assertEqual(notes.to_concepts_md(ns), MAP)

    def test_unknown_meta_key_is_not_dropped(self):
        with self.assertRaises(ValueError):
            notes.to_notes(MAP.replace(" · 별칭=", " · 옛것=x · 별칭="))

    def test_sanitized_file_name(self):
        self.assertEqual(notes.stem('A/B: 테스트? "x" [y]#^|*<>\\', 3), "A-B- 테스트- -x- -y--------")
        self.assertEqual(notes.stem(" .. ", 3), "개념 3")


class FolderTest(unittest.TestCase):
    def test_rule(self):
        f = notes.folder
        self.assertEqual(f(["hooks/split-notice.py"]), "hooks")
        self.assertEqual(f(["hooks/split-notice.py", "hooks/hooks.json"]), "hooks")
        self.assertEqual(f(["lib/a/x.py", "lib/a/y.py"]), "lib/a")
        self.assertEqual(f(["lib/a/x.py", "lib/b/y.py"]), "lib")
        self.assertEqual(f(["hooks/x.py", "lib/y.py"]), "")             # 여러 폴더 → 루트
        self.assertEqual(f([".claude-plugin/plugin.json"]), "")          # 점 폴더 → 루트
        self.assertEqual(f([".github/workflows/ci.yml"]), "")
        self.assertEqual(f([]), "")                                      # files 비었음 → 루트
        self.assertEqual(f([".gitignore", "lib/handoff_check.py"]), "")  # 루트 파일이 섞임
        self.assertEqual(f(["./lib/x.py"]), "lib")

    def test_empty_files_note_goes_to_root(self):
        text = MAP.replace("파일=`src/level/map.py`", "파일=없음(규칙 개념)")
        ns = notes.to_notes(text)
        self.assertIn("레벨.md", ns)
        self.assertEqual(notes.to_concepts_md(ns), text)


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.ns = notes.to_notes(MAP)

    def test_clean(self):
        self.assertEqual(notes.check(self.ns), [])

    def test_missing_link_target(self):
        out = notes.check(edit(self.ns, S2, "[[세이브 — 저장과 불러오기]]", "[[세이브 — 옛 이름]]"))
        self.assertTrue(any("[[세이브 — 옛 이름]] 노트가 없다" in p for p in out), out)

    def test_duplicate_alias_casefolded(self):
        ns = edit(self.ns, S1, '"저장"', '"Save"')
        ns = edit(ns, S2, "aliases: []", 'aliases: ["save"]')
        out = notes.check(ns)
        self.assertTrue(any("'save'가 노트끼리 겹친다" in p for p in out), out)

    def test_alias_equal_to_other_title(self):
        out = notes.check(edit(self.ns, S1, '"저장"', '"레벨"'))
        self.assertTrue(any("'레벨'가 노트끼리 겹친다" in p for p in out), out)

    def test_folder_differs(self):
        ns = dict(self.ns)
        ns["레벨.md"] = ns.pop(S2)
        out = notes.check(ns)
        self.assertTrue(any("레벨.md: 노트 폴더가 '(루트)'인데" in p and "'src/level'" in p for p in out), out)

    def test_missing_frontmatter_key(self):
        out = notes.check(edit(self.ns, S2, 'docs: []\n', ""))
        self.assertTrue(any("머리 항목 'docs'가 없다" in p for p in out), out)

    def test_home_path_and_private_word(self):
        home = "/" + "Users/nobody/x"
        out = notes.check(edit(self.ns, S1, "- **정해진 것**: a", "- **정해진 것**: " + home))
        self.assertTrue(any("홈 절대경로" in p for p in out), out)
        self.assertNotIn(home, "\n".join(out))
        out = notes.check(edit(self.ns, S1, "- **정해진 것**: a", "- **정해진 것**: 비밀프로젝트"), ["비밀프로젝트"])
        self.assertTrue(any("개인 자료 목록 단어" in p for p in out), out)

    def test_unreadable_neighbor_line(self):
        out = notes.check(edit(self.ns, S2, "- 정본: [[", "- 정본 [["))
        self.assertTrue(any("## 이웃의 줄을 못 읽었다" in p for p in out), out)
        with self.assertRaises(ValueError):
            notes.to_concepts_md(edit(self.ns, S2, "- 정본: [[", "- 정본 [["))


class MatchTest(unittest.TestCase):
    def setUp(self):
        self.ns = edit(notes.to_notes(MAP), S2, "aliases: []", 'aliases: ["세이", "x"]')

    def test_particle_is_stripped(self):
        self.assertEqual(notes.match(self.ns, "세이브를 고쳐 줘"), [1])
        self.assertEqual(notes.match(self.ns, "세이브에서 막혀"), [1])
        self.assertEqual(notes.match(self.ns, "저장을 다시"), [1])

    def test_no_substring_match(self):
        self.assertEqual(notes.match(self.ns, "세이브파일 고쳐 줘"), [])
        self.assertEqual(notes.match(self.ns, "저장소 정리"), [])     # 2글자 한글 별칭 '저장'이 더 긴 낱말 안에
        self.assertEqual(notes.match(self.ns, "저장소를 정리"), [])
        self.assertNotIn(2, notes.match(self.ns, "세이브를 고쳐"))     # 2글자 '세이'가 '세이브' 안에

    def test_short_alias_ignored(self):
        self.assertEqual(notes.match(self.ns, "x 고쳐"), [])

    def test_title_words_and_case(self):
        self.assertEqual(notes.match(self.ns, "레벨이 이상해"), [2])
        ns = edit(self.ns, S1, '"저장"', '"Save Slot"')
        self.assertEqual(notes.match(ns, "the save slot is broken"), [1])
        self.assertEqual(notes.match(ns, "save the slot"), [])

    def test_machine_prompt_gets_nothing(self):
        for p in ("<task-notification>세이브를 고쳐 src/save/save.py</task-notification>",
                  "Another Claude session sent a message: <cross-session-message>세이브를</cross-session-message>"):
            self.assertEqual(notes.match(self.ns, p), [])
            self.assertEqual(notes.match_paths(self.ns, p), [])

    def test_paths_are_separate(self):
        self.assertEqual(notes.match_paths(self.ns, "src/save/save.py:3를 봐"), [1])
        self.assertEqual(notes.match(self.ns, "src/save/save.py:3를 봐"), [])
        self.assertEqual(notes.match_paths(self.ns, "`src/level/map.py`가 이상해."), [2])
        self.assertEqual(notes.match_paths(self.ns, "/" + "tmp/repo/src/level/map.py 열어"), [2])
        self.assertEqual(notes.match_paths(self.ns, "src/level/map.pyc 지워"), [])
        self.assertEqual(notes.match_paths(self.ns, "xsrc/level/map.py"), [])
        self.assertEqual(notes.match_paths(self.ns, "세이브를 고쳐"), [])


class CliTest(unittest.TestCase):
    def test_export_build_check_match(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "CONCEPTS.md")
            with open(src, "w", encoding="utf-8", newline="") as fh:
                fh.write(MAP)
            vault = os.path.join(d, "concepts")
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(notes.main(["export", src, vault]), 0)
            self.assertIn("노트 2개(루트 0 · 하위 폴더 2)", out.getvalue())
            os.makedirs(os.path.join(vault, ".obsidian"))
            with open(os.path.join(vault, ".obsidian", "x.md"), "w") as fh:
                fh.write("[[없는 노트]]")
            with redirect_stdout(io.StringIO()) as out:
                notes.main(["build", vault])
            self.assertEqual(out.getvalue(), MAP)
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(notes.main(["check", vault]), 0)
            with redirect_stdout(io.StringIO()) as out:
                notes.main(["match", vault, "세이브를 src/level/map.py"])
            self.assertEqual(out.getvalue(), "별칭: 1 세이브 — 저장과 불러오기\n경로: 2 레벨\n")
            with self.assertRaises(SystemExit):   # 이미 있는 노트는 덮어쓰지 않는다
                notes.main(["export", src, vault])


if __name__ == "__main__":
    unittest.main()
