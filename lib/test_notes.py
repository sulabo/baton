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


DOT_MAP = """# 지도

## 요약

| # | 개념 | 상태 | 심각도 | 한 줄 |
|---|---|---|---|---|
| 1 | 버튼 | 일치 | — | 버튼 줄 |
| 2 | 색 | 일치 | — | 색 줄 |
| 3 | 글꼴 | 일치 | — | 글꼴 줄 |

## 1. 버튼

- **메타**: 상태=일치 · 확인=2026-09-01(`0000000`) · 파일=ui/button.py · ui/theme.py · 이웃=개념 2(정본) · 개념 3(전제) · 문서=docs/a.md · docs/b.md

- **정해진 것**: a

## 2. 색

- **메타**: 상태=일치 · 확인=2026-09-01(`0000000`) · 파일=`ui/color.py` · `ui/theme.py` · 이웃=개념 1(정본)

- **정해진 것**: b

## 3. 글꼴

- **메타**: 상태=일치 · 확인=2026-09-01(`0000000`) · 파일=ui/font.py · 이웃=개념 1(전제)

- **정해진 것**: c
"""


class MiddleDotValueTest(unittest.TestCase):
    """다른 저장소 지도(US-5)의 꼴: 메타 값 안에 ' · '. 내용은 지어낸 것."""

    def test_round_trip(self):
        ns = notes.to_notes(DOT_MAP)          # 다르면 to_notes가 거절한다
        self.assertEqual(notes.to_concepts_md(ns), DOT_MAP)
        n = notes.parse_note("ui/버튼.md", ns["ui/버튼.md"])
        self.assertEqual(n["fm"]["files"], ["ui/button.py", "ui/theme.py"])
        self.assertEqual(n["fm"]["docs"], ["docs/a.md", "docs/b.md"])
        self.assertEqual(n["neighbors"], [("정본", ["색"]), ("전제", ["글꼴"])])
        self.assertEqual(notes.parse_note("ui/색.md", ns["ui/색.md"])["fm"]["files"], ["ui/color.py", "ui/theme.py"])
        self.assertEqual(notes.check(ns), [])

    def test_parse_meta_continuation(self):
        m = notes.parse_meta("- **메타**: 상태=일치 · 파일=a.py · b.py · 이웃=개념 2(정본) · 개념 5(전제)")
        self.assertEqual(m, {"상태": "일치", "파일": "a.py · b.py", "이웃": "개념 2(정본) · 개념 5(전제)"})
        with self.assertRaises(ValueError):
            notes.parse_meta("- **메타**: a.py · 상태=일치")


class MalformedExportTest(unittest.TestCase):
    """export가 내용을 조용히 버리거나 옮기지 않는다 — 되살리거나, 첫 다른 줄을 대며 거절한다."""

    def refused(self, text):
        with self.assertRaises(ValueError) as cm:
            notes.to_notes(text)
        return str(cm.exception)

    def test_text_before_meta_is_kept(self):
        text = MAP.replace("## 2. 레벨\n\n", "## 2. 레벨\n\n> 메타 줄 앞의 글\n")
        ns = notes.to_notes(text)
        self.assertIn(notes.MARK_META, ns[S2])
        self.assertEqual(notes.to_concepts_md(ns), text)

    def test_no_blank_around_meta_is_kept(self):
        text = MAP.replace("## 2. 레벨\n\n", "## 2. 레벨\n")
        self.assertEqual(notes.to_concepts_md(notes.to_notes(text)), text)

    def test_table_row_without_section(self):
        msg = self.refused(MAP.replace("| 1 | 세이브 |", "| 3 | 유령 | 일치 | — | x |\n| 1 | 세이브 |"))
        self.assertIn("유령", msg)

    def test_interleaved_heading(self):
        self.refused(MAP.replace("## 2. 레벨", "## 메모\n\n글\n\n## 2. 레벨"))

    def test_header_bold_order_crlf_spacing(self):
        self.refused(MAP.replace("| # | 개념 |", "| # | 이름 |"))
        self.refused(MAP.replace("| 2 | 레벨 |", "| **2** | 레벨 |"))
        self.refused(MAP.replace("파일=`src/level/map.py` · 이웃=개념 1(정본)", "이웃=개념 1(정본) · 파일=`src/level/map.py`"))
        self.refused(MAP.replace("\n", "\r\n"))
        self.refused(MAP.replace("`src/save/save.py`,`src/save/load.py`", "`src/save/save.py`, `src/save/load.py`,`x/y.py`"))

    def test_comma_space_is_preserved(self):
        text = MAP.replace("`src/save/save.py`,`src/save/load.py`", "`src/save/save.py`, `src/save/load.py`")
        self.assertEqual(notes.to_concepts_md(notes.to_notes(text)), text)

    def test_duplicate_section_and_missing_neighbor(self):
        self.assertIn("둘 이상", self.refused(MAP + "\n## 2. 또 레벨\n\n- **메타**: 상태=일치 · 확인=x · 파일=`a` · 이웃=없음\n"))
        self.assertIn("개념 9", self.refused(MAP.replace("이웃=개념 1(정본)", "이웃=개념 9(정본)")))

    def test_title_colliding_with_index(self):
        text = MAP.replace("## 2. 레벨", "## 2. _색인").replace("파일=`src/level/map.py`", "파일=없음(규칙 개념)")
        self.assertIn("겹친다", self.refused(text))

    def test_cli_writes_nothing_when_refused(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "CONCEPTS.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write(MAP.replace("| # | 개념 |", "| # | 이름 |"))
            with self.assertRaises(SystemExit) as cm:
                notes.main(["export", src, os.path.join(d, "out")])
            self.assertIn("다르다", str(cm.exception.code))
            self.assertFalse(os.path.exists(os.path.join(d, "out")))


class MalformedNotesTest(unittest.TestCase):
    def setUp(self):
        self.ns = notes.to_notes(MAP)

    def test_duplicate_no_refused_in_build(self):
        ns = edit(self.ns, S2, "no: 2", "no: 1")
        with self.assertRaises(ValueError) as cm:
            notes.to_concepts_md(ns)
        self.assertIn("no 1가 노트 2개", str(cm.exception))
        self.assertTrue(any("no 1가 노트 2개" in p for p in notes.check(ns)))

    def test_non_integer_or_missing_no(self):
        ns = edit(self.ns, S2, "no: 2", "no: 둘")
        with self.assertRaises(ValueError) as cm:
            notes.to_concepts_md(ns)
        self.assertIn("정수가 아니다", str(cm.exception))
        self.assertTrue(any("no가 정수가 아니다" in p for p in notes.check(ns)))
        self.assertEqual(notes.match(ns, "레벨이 이상해 src/level/map.py"), [])
        self.assertEqual(notes.match_paths(ns, "src/level/map.py"), [])
        ns = edit(self.ns, S2, "no: 2\n", "")
        self.assertEqual(notes.match(ns, "레벨이 이상해"), [])
        self.assertEqual(notes.match_paths(ns, "src/level/map.py"), [])

    def test_unindented_block_list(self):
        ns = edit(self.ns, S1, 'aliases: ["세이브", "저장"]', "aliases:\n- 세이브\n- 저장")
        self.assertEqual(notes.to_concepts_md(ns), MAP)

    def test_flow_list_from_spec_example(self):
        ns = edit(self.ns, S1, 'aliases: ["세이브", "저장"]', "aliases: [세이브, 저장]")
        self.assertEqual(notes.to_concepts_md(ns), MAP)

    def test_unreadable_frontmatter_line(self):
        ns = edit(self.ns, S1, "no: 1\n", "no: 1\n그냥 글\n")
        self.assertTrue(any("머리 항목 줄을 못 읽었다" in p for p in notes.check(ns)))
        with self.assertRaises(ValueError):
            notes.to_concepts_md(ns)

    def test_nfd_names(self):
        nfd = lambda s: notes.unicodedata.normalize("NFD", s)
        ns = dict(self.ns)
        ns[nfd(S2)] = ns.pop(S2)                                      # macOS가 돌려준 NFD 파일 이름
        self.assertEqual(notes.to_concepts_md(ns), MAP)
        self.assertEqual(notes.check(ns), [])
        ns = edit(self.ns, S1, "[[레벨]]", "[[%s]]" % nfd("레벨"))     # NFD 링크 대상
        self.assertEqual(notes.to_concepts_md(ns), MAP)
        self.assertEqual(notes.check(ns), [])
        dup = edit(self.ns, S1, '"저장"', '"%s"' % nfd("레벨"))
        self.assertTrue(any("'레벨'가 노트끼리 겹친다" in p for p in notes.check(dup)))
        short = edit(self.ns, S2, "aliases: []", 'aliases: ["%s"]' % nfd("저"))   # NFD로는 2글자, NFC로는 1글자
        self.assertEqual(notes.match(short, "저 고쳐"), [])

    def test_links_in_code_fence_ignored(self):
        ns = edit(self.ns, S1, "- **정해진 것**: a", "- **정해진 것**: a\n\n```\n[[없는 노트]]\n```")
        self.assertEqual(notes.check(ns), [])
        ns = edit(self.ns, S1, "- **정해진 것**: a", "- **정해진 것**: a [[없는 노트]]")
        self.assertTrue(any("[[없는 노트]] 노트가 없다" in p for p in notes.check(ns)))

    def test_unknown_key_and_missing_title(self):
        ns = edit(self.ns, S1, "no: 1\n", 'no: 1\ntags: ["x"]\ncolor: "red"\n')
        out = notes.check(ns)
        self.assertTrue(any("모르는 머리 항목 'color'" in p for p in out), out)
        self.assertFalse(any("'tags'" in p for p in out), out)
        out = notes.check(edit(self.ns, S2, "# 레벨\n", ""))
        self.assertTrue(any("'# 제목' 줄이 없다" in p for p in out), out)


class ParticleDecisionTest(unittest.TestCase):
    """2글자 한글 별칭 + 조사 떼기: 적중과 알려진 오탐을 함께 박는다(소유자가 정할 열린 질문 — notes.PARTICLES 주석)."""

    def setUp(self):
        ns = edit(notes.to_notes(MAP), S2, "aliases: []", 'aliases: ["개념", "설계"]')
        self.ns = ns

    def test_hit(self):
        self.assertEqual(notes.match(self.ns, "저장을 다시"), [1])

    def test_known_false_positives(self):
        self.assertEqual(notes.match(self.ns, "개념도 그려 줘"), [2])   # '개념도'(그림) → '개념' + 조사 '도'
        self.assertEqual(notes.match(self.ns, "설계도 보여 줘"), [2])

    def test_machine_regex_is_pr16s(self):
        self.assertTrue(notes.machine_prompt("<task-notification>\n세이브를</task-notification>"))
        self.assertTrue(notes.machine_prompt("<agent-message/>"))
        self.assertFalse(notes.machine_prompt("<agent-messages 얘기> 세이브를 고쳐"))
        self.assertFalse(notes.machine_prompt("<task-notification-log> 세이브를 고쳐"))  # \b였다면 기계로 쳤다
        self.assertEqual(notes.match(self.ns, "<agent-messages 얘기> 세이브를 고쳐"), [1])


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
