#!/usr/bin/env python3
"""맥락 조립기: 개념 그래프(파일·이웃·별칭)로 고르고, 이미 만진 파일은 빼고, 기준선을 같은 자리에서 남긴다. 훅 연결은 아직 없다."""
import json
import os
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import compiler
import concepts

MAP = """# 개념

## 1. 세이브 — 저장과 불러오기
- **메타**: 상태=구현 · 확인=2026-09-01(`0000000`) · 파일=`src/save/save.ts`,`src/save/load.ts`,`README.md` · 이웃=개념 2(전제) · 별칭=저장 슬롯
본문

## 2. 레벨 — 맵 구성
- **메타**: 상태=구현 · 확인=2026-09-01(`0000000`) · 파일=`src/level/map.ts`,`src/shared/util.ts` · 이웃=개념 1(전제)

## 3. 사운드 — 효과음
- **메타**: 상태=미구현 · 확인=2026-09-01(`0000000`) · 파일=`src/shared/util.ts` · 이웃=없음

## 4. 입력 — 키 처리
- **메타**: 상태=구현 · 확인=2026-09-01(`0000000`) · 파일=`src/shared/util.ts`,`src/input/keys.ts` · 이웃=없음
"""
HANDOFF = "# Session Handoff\n## 관련 파일\n- `src/level/map.ts:12` 맵\n- `HANDOFF.md`\n- `없는/파일.ts`\n- `src/save/save.ts`\n"
DECISIONS = """# 결정
## 2026-09-20 — 세이브는 로컬에만
- 관련: 개념 1
## 2026-09-25 — 맵 크기 고정
본문에 `map.ts` 언급
## 2026-09-10 — 무관한 결정
- 관련: 개념 9

| ID | 결정 | 근거 |
|---|---|---|
| P1 | 슬롯 셋 (2026-09-28) | `load.ts` 기준 |
"""
FILES = ["src/save/save.ts", "src/save/load.ts", "src/save/old.ts", "src/level/map.ts", "src/level/tiles.ts",
         "src/shared/util.ts", "src/input/keys.ts", "README.md"]


def tool_use(name, path, ts):
    return {"type": "assistant", "timestamp": ts,
            "message": {"content": [{"type": "tool_use", "name": name, "input": {"file_path": path}}]}}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.realpath(os.path.join(self.tmp.name, "repo"))
        os.makedirs(self.repo)
        p = mock.patch.dict(os.environ, {"XDG_CACHE_HOME": os.path.join(self.tmp.name, "cache"),
                                         "XDG_CONFIG_HOME": os.path.join(self.tmp.name, "cfg"), "BATON_LANG": "ko"})
        p.start(); self.addCleanup(p.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel, text):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def git(self, *a):
        subprocess.run(["git", "-C", self.repo, "-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgsign=false",
                        *a], check=True, capture_output=True)

    def commit(self, files, when):
        for f in files:
            self.write(f, f + "\n" + when + "\n")
        self.git("add", "-A")
        env = dict(os.environ, GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when)
        subprocess.run(["git", "-C", self.repo, "-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgsign=false",
                        "commit", "-qm", when], check=True, capture_output=True, env=env)

    def fixture(self):
        self.git("init", "-q")
        self.commit(FILES, "2026-09-01T00:00:00")
        self.commit(["src/save/old.ts"], "2026-09-02T00:00:00")
        self.commit(["src/level/tiles.ts"], "2026-09-03T00:00:00")
        self.write("CONCEPTS.md", MAP)
        self.write("HANDOFF.md", HANDOFF)
        self.write("DECISIONS.md", DECISIONS)

    def transcript(self, recs, sub=()):
        path = os.path.join(self.tmp.name, "sess.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n")
        if sub:
            d = os.path.join(self.tmp.name, "sess", "subagents")
            os.makedirs(d)
            with open(os.path.join(d, "a.jsonl"), "w", encoding="utf-8") as f:
                f.write("\n".join(json.dumps(r, ensure_ascii=False) for r in sub) + "\n")
        return path


class GraphTest(Base):
    def test_meta_fields_parsed(self):
        self.write("CONCEPTS.md", MAP)
        g = compiler.graph(self.repo)
        self.assertEqual(g["rel"], "CONCEPTS.md")
        self.assertEqual(g["nodes"]["1"]["files"], ["src/save/save.ts", "src/save/load.ts", "README.md"])
        self.assertEqual(g["nodes"]["1"]["neighbors"], ["2"])
        self.assertEqual(g["nodes"]["1"]["aliases"], ["저장 슬롯"])
        self.assertEqual(g["nodes"]["3"]["neighbors"], [])
        self.assertEqual(g["nodes"]["1"]["title"], "세이브")

    def test_map_files_outside_repo_dropped_and_normalized(self):
        self.write("CONCEPTS.md", "## 1. 세이브\n- **메타**: 파일=`../outside.txt`,`/etc/hosts`,`./src/a.ts` · 이웃=없음\n")
        self.assertEqual(compiler.graph(self.repo)["nodes"]["1"]["files"], ["src/a.ts"])

    def test_no_map_is_none(self):
        self.assertIsNone(compiler.graph(self.repo))

    def test_field_anchor_and_loose_spacing(self):
        f = concepts.field
        # 다른 키 속의 같은 이름은 안 걸린다
        self.assertEqual(f("- **메타**: 근거파일=`x.py` · 파일=`a.py`", "파일"), "`a.py`")
        self.assertEqual(f("- **메타**: 옛별칭=세이브 · 이웃=없음", "별칭"), "")
        # 공백이 없거나 여러 칸인 손글씨 줄도 main 이전처럼 읽는다(fresh.sh·check.sh·세션 알림이 조용히 '?'로 바뀌지 않게)
        self.assertEqual(f("- **메타**:상태=구현 · 파일=`a.py`", "상태"), "구현")
        self.assertEqual(f("- **메타**:  상태=구현 · 파일=`a.py`", "상태"), "구현")
        self.assertEqual(f("- **메타**: 상태=구현 ·  파일=`a.py`", "파일"), "`a.py`")
        self.assertEqual(f("- **메타**: 상태=구현 ·파일=`a.py`", "파일"), "`a.py`")
        self.assertEqual(f("- **메타**: 상태=일치 · 확인=2026-09-01(`abc1234`)", "확인"), "2026-09-01(`abc1234`)")
        # 파서 명령 출력으로도 같다
        path = os.path.join(self.tmp.name, "loose.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("## 1. 세이브\n- **메타**:상태=구현 · 확인=2026-09-01(`abc1234`) · 파일=`a.py` · 이웃=없음\n")
        out = subprocess.run([sys.executable, os.path.join(HERE, "concepts.py"), path, "meta"],
                             capture_output=True, text=True, check=True).stdout
        self.assertEqual(out, "1\t세이브\t구현\t2026-09-01\tabc1234\t`a.py`\t없음\t-\n")

    def test_uses_main_parser_fences_and_warnings(self):
        # 닫힌 펜스 안의 예시 절은 노드가 아니고, 숫자 없는 제목이 절을 닫는다(lib/concepts.py walk)
        self.write("CONCEPTS.md", MAP.replace("본문\n", "```\n## 9. 예시\n- **메타**: 파일=`src/x.ts` · 이웃=없음\n```\n\n## 유지 규칙\n"))
        g = compiler.graph(self.repo)
        self.assertEqual(sorted(g["nodes"]), ["1", "2", "3", "4"])
        self.assertEqual(g["warnings"], [])
        # 열린 채 끝난 펜스 뒤 개념은 못 읽는다 — 0으로 숨기지 않고 경고로 낸다
        self.write("CONCEPTS.md", MAP.replace("본문\n", "```\n"))
        g = compiler.graph(self.repo)
        self.assertEqual(sorted(g["nodes"]), ["1"])
        self.assertEqual(len(g["warnings"]), 1)
        self.assertIn("개념 3개를 못 읽었다", g["warnings"][0])
        self.assertEqual(compiler.select(self.repo, "세이브", None)["map_warnings"], g["warnings"])

    def test_matches_title_alias_file_and_one_hop(self):
        self.write("CONCEPTS.md", MAP)
        g = compiler.graph(self.repo)
        self.assertEqual(compiler.concept_matches(g, "세이브 고쳐줘", []),
                         [("1", "제목 '세이브'", "prompt"), ("2", "개념 1의 이웃", "neighbor")])
        self.assertEqual(compiler.concept_matches(g, "저장 슬롯이 이상해", [])[0], ("1", "별칭 '저장 슬롯'", "prompt"))
        self.assertEqual(compiler.concept_matches(g, "이거 봐줘", ["src/level/map.ts"]),
                         [("2", "작업 파일 src/level/map.ts", "file"), ("1", "개념 2의 이웃", "neighbor")])
        # 프롬프트로 맞은 개념이 작업 파일로 맞은 개념보다 앞이다
        self.assertEqual([m[0] for m in compiler.concept_matches(g, "입력 봐줘", ["src/level/map.ts"])][:2], ["4", "2"])

    def test_shared_and_hub_files_do_not_pick_concepts(self):
        self.write("CONCEPTS.md", MAP)
        g = compiler.graph(self.repo)
        # util.ts는 개념 셋에 걸렸다(공유 파일), README.md는 허브 — 둘 다 개념을 고르는 근거가 아니다
        self.assertEqual(compiler.concept_matches(g, "이거 봐줘", ["src/shared/util.ts", "README.md"]), [])


class SeedTest(Base):
    def test_handoff_files_exist_only_and_no_hubs(self):
        self.fixture()
        self.assertEqual(compiler.handoff_files(self.repo), ["src/level/map.ts", "src/save/save.ts"])

    def test_session_files_main_and_subagents_newest_first(self):
        self.fixture()
        nfd = unicodedata.normalize("NFD", os.path.join(self.repo, "src/save/load.ts"))
        tr = self.transcript([tool_use("Read", os.path.join(self.repo, "src/level/map.ts"), "2026-10-01T00:00:01Z"),
                              tool_use("Edit", "/elsewhere/x.ts", "2026-10-01T00:00:02Z"),
                              tool_use("Bash", os.path.join(self.repo, "README.md"), "2026-10-01T00:00:03Z")],
                             sub=[tool_use("Read", nfd, "2026-10-01T00:00:04Z")])
        self.assertEqual(compiler.session_files(self.repo, tr), (["src/save/load.ts", "src/level/map.ts"], False))

    def test_missing_transcript_is_empty(self):
        self.assertEqual(compiler.session_files(self.repo, None), ([], False))
        self.assertEqual(compiler.session_files(self.repo, os.path.join(self.tmp.name, "없음.jsonl")), ([], False))

    def test_long_transcript_marks_tail_cut(self):
        self.fixture()
        pad = {"type": "user", "message": {"content": "x" * 1000}}
        tr = self.transcript([pad] * 600 + [tool_use("Read", os.path.join(self.repo, "src/level/map.ts"), "2026-10-01T00:00:01Z")])
        self.assertEqual(compiler.session_files(self.repo, tr), (["src/level/map.ts"], True))


class SelectTest(Base):
    def test_order_skip_and_baselines(self):
        self.fixture()
        tr = self.transcript([tool_use("Read", os.path.join(self.repo, "src/save/save.ts"), "2026-10-01T00:00:01Z")])
        p = compiler.select(self.repo, "세이브 고쳐줘", tr)
        paths = [f["path"] for f in p["files"]]
        self.assertNotIn("src/save/save.ts", paths)                        # 이미 연 파일은 다시 가리키지 않는다
        self.assertEqual(paths[0], "src/save/load.ts")                      # 직접 맞은 개념의 파일이 맨 앞
        self.assertEqual(p["files"][1], {"path": "src/level/map.ts", "why": "인계서 작업 파일", "src": "h"})  # 개념 2 것이지만 인계서가 먼저
        self.assertEqual(compiler.summary(p)["src"][:2], "ph")
        self.assertEqual([c["kind"] for c in p["concepts"]], ["prompt", "file"])
        self.assertIn("src/save/old.ts", paths)                            # 같은 폴더 최근순
        self.assertNotIn("README.md", paths)                               # 허브
        self.assertEqual(p["state"], "MATCHED")
        self.assertEqual([c["num"] for c in p["concepts"]], ["1", "2"])
        # 그래프를 빼면 인계서 → 같은 폴더 순서뿐이다(load.ts도 save.ts 옆이라 뒤에 들어온다)
        self.assertEqual(p["baselines"]["nograph"], ["src/level/map.ts"] + [f for f in p["baselines"]["folder"] if f != "src/level/map.ts"])
        self.assertEqual(p["baselines"]["handoff"], ["src/level/map.ts"])
        self.assertEqual(p["seeds"], {"handoff": 2, "session": 1, "tail_cut": False, "git_ok": True})
        self.assertLessEqual(len(paths), compiler.MAX_FILES)

    def test_state_counts_prompt_matches_only(self):
        self.fixture()
        p = compiler.select(self.repo, "오늘 날씨 어때", None)
        self.assertEqual(p["state"], "NO_MATCH")                          # 인계서 파일로 개념 2가 붙어도 프롬프트 판정은 아니다
        self.assertIn("2", [c["num"] for c in p["concepts"]])

    def test_folder_recency_newest_first(self):
        self.fixture()
        p = compiler.select(self.repo, "아무 말", None)
        level = [f for f in p["baselines"]["folder"] if f.startswith("src/level/")]
        self.assertEqual(level, ["src/level/tiles.ts", "src/level/map.ts"])

    def test_decisions_by_concept_ref_file_name_and_table(self):
        self.fixture()
        p = compiler.select(self.repo, "세이브 고쳐줘", None)
        self.assertEqual([d["date"] for d in p["decisions"]], ["2026-09-28", "2026-09-25", "2026-09-20"])
        self.assertEqual(p["decisions"][2]["title"], "세이브는 로컬에만")

    def test_no_map_no_git_still_works(self):
        self.write("HANDOFF.md", HANDOFF)
        self.write("src/level/map.ts", "x")
        p = compiler.select(self.repo, "세이브", None)
        self.assertEqual(p["state"], "NO_MAP")
        self.assertEqual([f["path"] for f in p["files"]], ["src/level/map.ts"])
        self.assertEqual(p["head"], "")

    def test_project_dir_below_git_root_uses_relative_paths(self):
        self.fixture()
        sub = os.path.join(self.repo, "src")
        head, times = compiler.last_commit_times(sub)
        self.assertIn("level/tiles.ts", times)                    # 하위 폴더 기준 — 씨앗(rel_in)과 같은 기준
        self.assertNotIn("src/level/tiles.ts", times)
        self.assertNotIn("README.md", times)                      # 하위 폴더 밖은 버린다

    def test_git_log_failure_not_cached_as_empty(self):
        self.fixture()
        real = compiler.git
        fail = lambda repo, *a: None if a[0] == "log" else real(repo, *a)
        with mock.patch.object(compiler, "git", side_effect=fail):
            self.assertIsNone(compiler.last_commit_times(self.repo)[1])
            self.assertFalse(compiler.select(self.repo, "세이브", None)["seeds"]["git_ok"])  # 측정이 그 턴을 가려낼 수 있게
        with mock.patch.object(compiler.time, "time", return_value=compiler.time.time() + compiler.FAIL_RETRY + 1):
            self.assertIn("src/level/tiles.ts", compiler.last_commit_times(self.repo)[1])  # 재시도 뒤에는 채워진다

    def test_no_home_no_cache_dir(self):
        with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": "", "HOME": ""}):
            self.assertIsNone(compiler.cache_dir())
        with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": "rel/cache", "HOME": "/h"}):
            self.assertEqual(compiler.cache_dir(), "/h/.cache/baton/compile")   # 상대 XDG는 무시(규약), 현재 폴더에 안 만든다
        with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": "rel/cache", "HOME": "rel"}):
            self.assertIsNone(compiler.cache_dir())
            self.fixture()
            self.assertTrue(compiler.last_commit_times(self.repo)[1])
        self.assertFalse(os.path.exists(os.path.join(self.repo, ".cache")))

    def test_commit_times_cached_by_head(self):
        self.fixture()
        head, times = compiler.last_commit_times(self.repo)
        with mock.patch.object(compiler, "git", side_effect=lambda repo, *a: head + "\n" if a[0] == "rev-parse" else
                               self.fail("HEAD가 같으면 git log를 다시 부르지 않는다")):
            self.assertEqual(compiler.last_commit_times(self.repo), (head, times))

    def test_render_budget_and_empty(self):
        self.fixture()
        p = compiler.select(self.repo, "세이브 고쳐줘", None)
        text = compiler.render(p)
        self.assertIn("관련 개념 (CONCEPTS.md)", text)
        self.assertIn("- 1. 세이브 — 제목 '세이브'", text)
        self.assertLessEqual(len(compiler.render(p, 300)), 300)
        self.assertEqual(compiler.render(p, 10), "")
        self.assertEqual(compiler.render({"concepts": [], "files": [], "decisions": []}), "")

    def test_summary_has_no_prompt(self):
        self.fixture()
        s = compiler.summary(compiler.select(self.repo, "세이브 비밀단어 고쳐줘", None))
        self.assertNotIn("비밀단어", json.dumps(s, ensure_ascii=False))


EN_MAP = """# Concepts

## 1. save — saving and loading
- **Meta**: status=agrees · checked=2026-09-01(`0000000`) · files=`src/save/save.ts`,`src/save/load.ts`,`README.md` · neighbors=Concept 2(premise) · aliases=checkpoint
body

## 2. level — map layout
- **Meta**: status=agrees · checked=2026-09-01(`0000000`) · files=`src/level/map.ts`,`src/shared/util.ts` · neighbors=Concept 1(premise)

## 3. sound — effects
- **Meta**: status=not built yet · checked=2026-09-01(`0000000`) · files=none(rule concept) · neighbors=none
"""


class EnglishMapTest(Base):
    """영어 지도(files=·neighbors=·aliases=·Concept N)도 같은 그래프가 되고, BATON_LANG=en이면 이유·머리말이 영어다."""

    def test_graph_reads_english_keys(self):
        self.write("CONCEPTS.md", EN_MAP)
        g = compiler.graph(self.repo)
        self.assertEqual(g["nodes"]["1"]["files"], ["src/save/save.ts", "src/save/load.ts", "README.md"])
        self.assertEqual(g["nodes"]["1"]["neighbors"], ["2"])
        self.assertEqual(g["nodes"]["2"]["neighbors"], ["1"])
        self.assertEqual(g["nodes"]["1"]["aliases"], ["checkpoint"])
        self.assertEqual(g["nodes"]["3"]["files"], [])
        self.assertEqual(g["nodes"]["1"]["title"], "save")

    def test_english_reasons_and_render(self):
        self.fixture()
        self.write("CONCEPTS.md", EN_MAP)
        self.write("DECISIONS.md", "# Decisions\n## 2026-09-20 — saves stay local\n- Related: Concept 1\n")
        with mock.patch.dict(os.environ, {"BATON_LANG": "en"}):
            self.assertEqual(compiler.concept_matches(compiler.graph(self.repo), "the checkpoint is broken", []),
                             [("1", "alias 'checkpoint'", "prompt"), ("2", "neighbor of concept 1", "neighbor")])
            p = compiler.select(self.repo, "fix the checkpoint", None)
            text = compiler.render(p)
        self.assertEqual(p["lang"], "en")
        self.assertTrue(text.startswith("[baton] Context assembly — navigation anchors picked from the prompt and the working "
                                        "files. Don't read them all; open only what you need. Check actual behavior in the code.\n"))
        # 인계서의 작업 파일(src/level/map.ts·src/save/save.ts)이 씨앗이다 — 개념 2는 작업 파일로 맞는다
        self.assertIn("\nRelated concepts (CONCEPTS.md)\n- 1. save — alias 'checkpoint' · working file src/save/save.ts\n"
                      "- 2. level — working file src/level/map.ts\n", text)
        self.assertIn("\nFiles worth reading (not opened in this session yet)\n- src/save/save.ts — concept 1\n", text)
        self.assertIn("- src/level/map.ts — working file in the handoff\n- src/shared/util.ts — concept 2 (working file)\n", text)
        self.assertIn("- src/level/tiles.ts — same folder as a working file, recent commit\n", text)
        self.assertIn("\nRelated decisions (DECISIONS.md)\n- 2026-09-20 saves stay local\n", text)

    def test_explain_cli_in_english(self):
        self.fixture()
        env = dict(os.environ, BATON_LANG="en")
        explain = lambda repo: subprocess.run([sys.executable, os.path.join(HERE, "compiler.py"), "explain", "zzz", repo],
                                              capture_output=True, text=True, env=env).stdout
        self.assertIn("\n[baton] Context assembly — navigation anchors", explain(self.repo))
        self.write("CONCEPTS.md", "## 1. a\n```\nopen\n## 2. b\n")
        self.assertIn("\n[baton] map warning: a code fence opened at line 2 is never closed — 1 concept after it could not be read\n",
                      explain(self.repo))
        empty = os.path.join(self.tmp.name, "empty")
        os.makedirs(empty)
        self.assertTrue(explain(empty).endswith("\n[baton] Nothing selected — nothing is added\n"))
        r = subprocess.run([sys.executable, os.path.join(HERE, "compiler.py")], capture_output=True, text=True, env=env)
        self.assertIn('compiler.py explain "<prompt>" [repo root]', r.stderr)

if __name__ == "__main__":
    unittest.main()
