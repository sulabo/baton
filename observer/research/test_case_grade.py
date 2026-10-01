import json, os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # 저장소 루트에서 돌려도 import되게
import case_grade as cg  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def diff(path, added=(), removed=()):
    body = "".join(f"-{l}\n" for l in removed) + "".join(f"+{l}\n" for l in added)
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n{body}"


def case(mode="fix", **grade):
    return {"id": "t", "mode": mode, "grade": grade}


class ParseDiff(unittest.TestCase):
    def test_korean_path_with_space(self):
        files = cg.parse_diff(diff("사본/문서 v5.md", ["새 줄"], ["옛 줄"]))
        self.assertEqual(files, {"사본/문서 v5.md": {"added": ["새 줄"], "removed": ["옛 줄"], "deleted": False,
                                                           "paras": [[], ["새 줄"]]}})

    def test_quoted_octal_path(self):
        q = '"a/\\353\\263\\265.md"'  # 복.md, quotepath=true 출력
        d = f"diff --git {q} {q}\n--- {q}\n+++ {q.replace('a/', 'b/')}\n@@\n+x\n"
        self.assertIn("복.md", cg.parse_diff(d))

    def test_deleted_file_keeps_old_path(self):
        d = "diff --git a/x.md b/x.md\n--- a/x.md\n+++ /dev/null\n@@\n-gone\n"
        self.assertEqual(cg.parse_diff(d)["x.md"]["removed"], ["gone"])


class Grade(unittest.TestCase):
    def test_residual_max_catches_leftover(self):
        c = case(residual=[{"file": "^copy/", "re": "1\\.0만", "base": 2, "max": 0}])
        v, _ = cg.grade(c, diff("copy/a.md", ["1.2만"], ["1.0만"]), [])
        self.assertTrue(v.startswith("오답(잔존"), v)
        v, _ = cg.grade(c, diff("copy/a.md", ["1.2만", "1.2만"], ["1.0만", "1.0만"]), [])
        self.assertTrue(v.startswith("자동 후보"), v)

    def test_residual_min_allows_rewrite_but_not_delete(self):
        c = case(residual=[{"file": "^D\\.md$", "re": "F14", "base": 1, "min": 1}])
        self.assertTrue(cg.grade(c, diff("D.md", ["| F14 | 1.2만 (완료)"], ["| F14 | 1.2만"]), [])[0].startswith("자동 후보"))
        self.assertTrue(cg.grade(c, diff("D.md", [], ["| F14 | 1.2만"]), [])[0].startswith("오답"))

    def test_forbid_added_skips_moved_lines_and_unless(self):
        c = case(forbid_added=[{"file": "^D\\.md$", "re": "이유", "unless": "소유자"}])
        self.assertTrue(cg.grade(c, diff("D.md", ["- 이유: 옛 이유"], ["- 이유: 옛 이유"]), [])[0].startswith("자동 후보"))
        self.assertTrue(cg.grade(c, diff("D.md", ["- 이유: 소유자 확인 필요"]), [])[0].startswith("자동 후보"))
        self.assertTrue(cg.grade(c, diff("D.md", ["- 이유: 지어낸 이유"]), [])[0].startswith("오답"))

    def test_forbid_added_para_unless(self):
        # 표지("미구현")가 문단 첫 줄에만 있어도 같은 문단의 다음 줄은 통과, 빈 줄 뒤 새 문단은 따로 본다
        r = {"file": "^G\\.md$", "re": "생쥐", "unless": "미구현"}
        case_ = lambda rule: case("flag", forbid_added=[rule], allow_touch=["\\.md$"])
        marked = ["> 새 방 (미구현).", "> 유리관 속 생쥐가 나옵니다."]
        self.assertTrue(cg.grade(case_(r), diff("G.md", marked), [])[0].startswith("오답"))
        self.assertTrue(cg.grade(case_(dict(r, para=True)), diff("G.md", marked), [])[0].startswith("자동 후보"))
        split = ["> 새 방 (미구현).", "", "생쥐를 구하면 끝."]
        self.assertTrue(cg.grade(case_(dict(r, para=True)), diff("G.md", split), [])[0].startswith("오답"))
        # 리뷰 재현(09-29): 빈 인용 '>'도 문단을 끊는다 / 같은 문장이 표지 없는 다른 파일 문단에 있으면 잡는다
        # / 표지가 첫 줄이 아닌 다른 문장에만 있으면 잡는다
        quote = ["> 새 방 (미구현)", ">", "> 생쥐를 구할 수 있습니다."]
        self.assertTrue(cg.grade(case_(dict(r, para=True)), diff("G.md", quote), [])[0].startswith("오답"))
        dup = diff("G.md", marked) + diff("G.md".replace("G", "W"), ["## 새 방", "", "> 유리관 속 생쥐가 나옵니다."])
        rw = dict(r, file="^[GW]\\.md$", para=True)
        self.assertTrue(cg.grade(case("flag", forbid_added=[rw], allow_touch=["\\.md$"]), dup, [])[0].startswith("오답"))
        late = ["> 새 방 추가! 생쥐를 구하세요.", "> 소리는 나중에 (미구현)."]
        self.assertTrue(cg.grade(case_(dict(r, para=True)), diff("G.md", late), [])[0].startswith("오답"))
        # 목록 항목은 문단이 따로다 — 첫 항목의 표지가 다음 항목을 살리지 않는다
        items = ["- 엔딩: 바뀔 예정(미구현)", "- 새 방: 생쥐를 구하세요"]
        self.assertTrue(cg.grade(case_(dict(r, para=True)), diff("G.md", items), [])[0].startswith("오답"))

    def test_unless_review_and_residual_unless(self):
        # 표지로만 살아난 줄은 자동 후보가 아니라 확인필요(정답·오답이 같은 단어를 쓰는 사례)
        r = {"file": "^S\\.md$", "re": "52°", "unless": "당시", "unless_review": True}
        self.assertTrue(cg.grade(case(forbid_added=[r]), diff("S.md", ["당시 52°였다"]), [])[0].startswith("확인필요"))
        self.assertTrue(cg.grade(case(forbid_added=[r]), diff("S.md", ["52°가 기준"]), [])[0].startswith("오답"))
        # residual의 unless: 옛 값을 옛 값이라 밝힌 추가 줄은 남은 것으로 세지 않는다
        res = [{"file": "^A\\.md$", "re": "291개", "base": 1, "max": 0, "unless": "→|이전"}]
        self.assertTrue(cg.grade(case(residual=res), diff("A.md", ["291개 → 344개"], ["291개"]), [])[0].startswith("자동 후보"))
        self.assertTrue(cg.grade(case(residual=res), diff("A.md", ["지금 291개"], ["291개"]), [])[0].startswith("오답"))

    def test_require_bash_before_edit(self):
        c = case(require_bash=[{"re": "npm test", "before_edit": "SPEC.md"}], require_added=[{"file": "SPEC", "re": "442"}])
        d = diff("SPEC.md", ["442 tests"], ["159 tests"])
        edit = ("Edit", {"file_path": "/s/SPEC.md"})
        self.assertTrue(cg.grade(c, d, [edit, ("Bash", {"command": "npm test"})])[0].startswith("오답"))
        self.assertTrue(cg.grade(c, d, [("Bash", {"command": "npm test"}), edit])[0].startswith("자동 후보"))
        sed = ("Bash", {"command": "sed -i '' 's/159/442/' SPEC.md"})
        self.assertTrue(cg.grade(c, d, [sed])[0].startswith("오답"))

    def test_flag_mode(self):
        c = case("flag", forbid_touch=["^src/"], allow_touch=["\\.md$"])
        self.assertEqual(cg.grade(c, "", [])[0], "자동 후보(손대지 않음)")
        self.assertEqual(cg.grade(c, diff("NOTE.md", ["미결"]), [])[0], "자동 후보(표시만)")
        self.assertTrue(cg.grade(c, diff("x.json", ["{}"]), [])[0].startswith("확인필요(범위 밖"))
        self.assertTrue(cg.grade(c, diff("src/a.ts", ["x"]), [])[0].startswith("오답(금지 파일"))

    def test_hunk_lines_that_look_like_headers(self):
        d = "diff --git a/a.sql b/a.sql\n--- a/a.sql\n+++ b/a.sql\n@@ -1,2 +1,2 @@\n--- 주석\n+++ x\n keep\n"
        self.assertEqual(cg.parse_diff(d)["a.sql"]["removed"], ["-- 주석"])
        self.assertEqual(cg.parse_diff(d)["a.sql"]["added"], ["++ x"])

    def test_empty_new_file_and_deletion(self):
        empty_new = "diff --git a/src/brand new.ts b/src/brand new.ts\nnew file mode 100644\nindex 0000000..e69de29\n"
        deleted = ("diff --git a/copy/b.md b/copy/b.md\ndeleted file mode 100644\n"
                   "--- a/copy/b.md\n+++ /dev/null\n@@ -1 +0,0 @@\n-1.0만\n")
        files = cg.parse_diff(empty_new + deleted)
        self.assertIn("src/brand new.ts", files)
        self.assertTrue(files["copy/b.md"]["deleted"])
        self.assertTrue(cg.grade(case(forbid_touch=["^src/"]), empty_new, [])[0].startswith("오답"))
        # 파일을 지워서 잔존 개수를 맞추면 통과가 아니라 사람 확인
        c = case(residual=[{"file": "^copy/", "re": "1\\.0만", "base": 1, "max": 0}])
        self.assertTrue(cg.grade(c, deleted, [])[0].startswith("확인필요(파일 삭제"))

    def test_bash_edit_detection_edges(self):
        c = case(require_bash=[{"re": "npm (run )?test", "before_edit": "SPEC.md"}], require_added=[{"file": "SPEC", "re": "442"}])
        d = diff("SPEC.md", ["442 tests"], ["159 tests"])
        grep = ("Bash", {"command": "grep -n tests SPEC.md 2>&1"})          # 읽기 — 편집 아님
        other = ("Edit", {"file_path": "/s/specs/3D-SPEC.md"})               # 다른 파일
        py = ("Bash", {"command": "python3 - <<EOF\nopen('SPEC.md','w').write(x)\nEOF"})
        echo = ("Bash", {"command": "echo 'npm test'"})
        test = ("Bash", {"command": "cd /s && npm test 2>&1 | tail"})
        self.assertTrue(cg.grade(c, d, [grep, other, test, py])[0].startswith("자동 후보"))
        self.assertTrue(cg.grade(c, d, [echo, py])[0].startswith("오답"))
        self.assertTrue(cg.grade(c, d, [test])[0].startswith("확인필요(SPEC.md 편집 호출 미탐지"))

    def test_fix_mode_no_change_needs_human(self):
        self.assertEqual(cg.grade(case(), "", [])[0], "확인필요(변경 없음)")


@unittest.skipUnless(os.path.exists(os.path.join(HERE, "cases.json")),
                     "cases.json은 다른 저장소의 커밋·프롬프트를 인용해 공개 저장소에 올리지 않는다(10-01 소유자 결정) — 로컬에서만 돈다")
class CasesFile(unittest.TestCase):
    """cases.json 자체의 형식 — 실제 데이터에 대한 원문 대조는 base·정정 diff 점검(09-28)으로 했다."""
    def setUp(self):
        with open(os.path.join(HERE, "cases.json"), encoding="utf-8") as f:
            self.cases = json.load(f)["cases"]

    def test_ids_unique_and_fields_present(self):
        ids = [c["id"] for c in self.cases]
        self.assertEqual(len(ids), len(set(ids)))
        for c in self.cases:
            for k in ("repo", "commit", "type", "mode", "snapshot", "prompt", "max_turns", "correct", "forbidden", "grade", "human_check", "status"):
                self.assertIn(k, c, f"{c['id']}: {k}")
            self.assertIn(c["mode"], ("fix", "flag"))
            self.assertIn(c["type"], ("미구현", "낡은 문서", "미결", "중복 정본", "결정 위반"))

    def test_ending_case_rejects_loop4_wrong_answer(self):
        # 루프 4에서 첫 채점기가 정답으로 넘긴 오답: 본문에 잔상 수 규칙을 한정어 없이 썼다
        c = next(c for c in self.cases if c["id"] == "ending-2846107")
        bad = diff("PLAYER-GUIDE.md", ["엔딩은 마지막 방의 잔상 수로 갈린다.", "> 예정된 변경입니다"])
        self.assertTrue(cg.grade(c, bad, [])[0].startswith("오답"))
        good = diff("PLAYER-GUIDE.md", ["> 잔상 수로 가르는 규칙은 예정(미구현)이다."])
        self.assertTrue(cg.grade(c, good, [])[0].startswith("자동 후보"))
        # 09-29 리뷰가 만든 오답: '현재 빌드'·'아직'이 한정어처럼 보여도 미구현 규칙을 현재형으로 말한다
        for line in ("현재 빌드에서도 엔딩은 잔상 수로 갈린다.", "잔상 수로 갈린다. 아직 못 본 엔딩이 있다면 다시."):
            self.assertTrue(cg.grade(c, diff("PLAYER-GUIDE.md", [line]), [])[0].startswith("오답"), line)
        # loop4 지도 없음 3번(사람 판정 정답)의 실제 표현
        real = diff("PLAYER-GUIDE.md", ["지금 빌드는 아직 런 누적 DEBT로 엔딩을", "> 코드(`endingFor(debt)`)는 아직 이 결정대로 바뀌지 않았습니다."])
        self.assertTrue(cg.grade(c, real, [])[0].startswith("자동 후보"))


if __name__ == "__main__":
    unittest.main()
