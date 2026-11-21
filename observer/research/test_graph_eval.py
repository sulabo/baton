#!/usr/bin/env python3
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import graph_eval as ge


def commits(*groups, t0=1000):
    """[(시각, 해시, 파일들)] — 시각은 10씩 증가."""
    return [(t0 + 10 * i, f"h{i}", list(fs)) for i, fs in enumerate(groups)]


class GraphTest(unittest.TestCase):
    def test_pair_needs_three_distinct_commits(self):
        cs = commits(["a", "b"], ["a", "b"], ["a", "c"], ["a", "c"], ["a", "c"])
        g = ge.build_graph(cs, float("inf"))
        self.assertEqual(g["a"], ["c"])          # a–b는 2회라 간선 없음
        self.assertNotIn("b", g)

    def test_hub_and_giant_commits_are_ignored(self):
        cs = commits(*[["a", "HANDOFF.md"]] * 3, *[[f"f{i}" for i in range(21)]] * 3)
        self.assertEqual(ge.build_graph(cs, float("inf")), {})

    def test_no_leak_from_commits_after_start(self):
        cs = commits(["a", "b"], ["a", "b"], ["a", "b"])           # 시각 1000·1010·1020
        self.assertEqual(ge.build_graph(cs, 1020), {})              # 1020 이전은 2회뿐
        self.assertEqual(ge.build_graph(cs, 1021)["a"], ["b"])

    def test_top_k_and_tie_break(self):
        cs = commits(*[["s", f"n{i}"] for i in range(7) for _ in range(3)])
        self.assertEqual(len(ge.build_graph(cs, float("inf"))["s"]), ge.TOP_K)

    def test_e1_case_scores_graph_and_baselines(self):
        cs = commits(*[["src/a.py", "src/b.py"]] * 3, ["lib/z.py", "lib/y.py"])
        r = ge.e1_case(cs, 10_000, ["src/a.py", "HANDOFF.md", "src/b.py", "lib/new.py"])
        self.assertEqual(r["n_truth"], 2)          # b.py·new.py (허브 제외)
        self.assertEqual(r["graph"], 0.5)
        self.assertEqual(r["dir"], 0.5)            # 같은 폴더 최근순에 b.py
        self.assertTrue(r["has_nb"])

    def test_hist_status_counts_new_files(self):
        cs = commits(["a", "b"])                                    # 시각 1000
        self.assertEqual(ge.hist_status(cs + [(2000, "x", ["c"])], 1500, ["a", "c", "d"]), {"before": 1, "after": 1, "never": 1})

    def test_e1_case_needs_seed_and_followup(self):
        self.assertIsNone(ge.e1_case([], 0, ["a.py"]))
        self.assertIsNone(ge.e1_case([], 0, ["a.py", "a.py"]))


class ConceptTest(unittest.TestCase):
    MAP = ("## 1. 세이브 — 저장\n- **메타**: 상태=일치 · 확인=2026-09-01(`abc1234`) · 파일=`src/save.ts`,`src/shared.ts` · 이웃=없음\n"
           "## 2. 카메라 — 시점\n- **메타**: 상태=일치 · 확인=2026-09-01(`abc1234`) · 파일=`src/cam/`,`src/shared.ts` · 이웃=없음\n"
           "## 3. 규칙 — 말투\n- **메타**: 상태=일치 · 확인=2026-09-01(`abc1234`) · 파일=없음(규칙 개념) · 이웃=없음\n")

    def test_parse_map_and_touched(self):
        secs, cmap = ge.parse_map(self.MAP)
        self.assertEqual(len(secs), 3)
        self.assertEqual(cmap["3"], [])
        self.assertEqual(ge.touched(cmap, ["src/cam/view.ts"]), {"2"})   # 폴더 아래
        self.assertEqual(ge.touched(cmap, ["src/camera.ts"]), set())     # 접두어만 같은 것은 아님

    def test_concept_edges_skip_shared_files(self):
        _, cmap = ge.parse_map(self.MAP)
        # 공유 파일 shared.ts를 통해서만 이어지면 개념 간선이 생기면 안 된다
        self.assertEqual(ge.concept_edges({"src/shared.ts": ["src/save.ts"], "src/save.ts": ["src/shared.ts"]}, cmap), set())
        # 폴더로 적힌 개념: 그래프 노드는 파일이다
        self.assertEqual(ge.concept_edges({"src/save.ts": ["src/cam/view.ts"]}, {"1": ["src/save.ts"], "2": ["src/cam/"]}), {("1", "2")})

    def test_aliases_need_three_days_and_low_misfire(self):
        secs, cmap = ge.parse_map(self.MAP)
        title = lambda text: {n for n, _ in ge.rules.concept_hits(secs, text)}
        hist = [(f"2026-09-0{d}", "저장 버그 고쳐줘", ["src/save.ts"]) for d in (1, 2)]
        self.assertEqual(ge.mine_aliases(hist, cmap, title), {})         # 이틀뿐
        hist.append(("2026-09-03", "저장 버그 다시", ["src/save.ts"]))
        self.assertEqual(ge.mine_aliases(hist, cmap, title).get("저장"), "1")
        noisy = hist + [(f"2026-09-1{d}", "저장 말고 다른 거", ["other.py"]) for d in range(4)]
        self.assertNotIn("저장", ge.mine_aliases(noisy, cmap, title))   # 잘못 걸린 횟수 4 > 맞은 3

    def test_e2_case_alias_adds_recall_only_from_history(self):
        secs, cmap = ge.parse_map(self.MAP)
        hist = [(f"2026-09-0{d}", "저장 버그", ["src/save.ts"]) for d in (1, 2, 3)]
        r = ge.e2_case(secs, cmap, hist, "저장이 또 깨졌어", ["src/save.ts"])
        self.assertEqual((r["base"], r["alias"], r["truth"]), ([], ["1"], ["1"]))
        self.assertEqual(ge.e2_case(secs, cmap, [], "저장이 또 깨졌어", ["src/save.ts"])["alias"], [])  # 이력 없으면 별칭 없음


class EditPathsTest(unittest.TestCase):
    def test_merges_main_and_subagent_edits_in_time_order(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            main = os.path.join(d, "s1.jsonl")
            sub = os.path.join(d, "s1", "subagents"); os.makedirs(sub)
            rec = lambda ts, p: json.dumps({"timestamp": ts, "message": {"content": [{"type": "tool_use", "name": "Edit", "input": {"file_path": p}}]}})
            open(main, "w").write(rec("2026-09-01T00:00:03Z", "/r/c.py") + "\n" + rec("2026-09-01T00:00:01Z", "/r/a.py") + "\n")
            open(os.path.join(sub, "agent-x.jsonl"), "w").write(rec("2026-09-01T00:00:02Z", "/r/b.py") + "\n")
            self.assertEqual(ge.edit_paths(main), ["/r/a.py", "/r/b.py", "/r/c.py"])


class TruthSeqTest(unittest.TestCase):
    def test_read_label_keeps_only_files_existing_before_start(self):
        cs = commits(["a.py", "b.py"])                                   # 시각 1000
        s = {"edits": ["new.py"], "reads": ["a.py", "new.py", "HANDOFF.md", "b.py"], "start": 1500}
        self.assertEqual(ge.truth_seq(s, "edit", cs), ["new.py"])
        self.assertEqual(ge.truth_seq(s, "read", cs), ["a.py", "b.py"])  # 새 파일·허브는 빠짐
        self.assertEqual(ge.truth_seq(dict(s, start=999), "read", cs), [])  # 시작 뒤 커밋은 모름


class StatsTest(unittest.TestCase):
    def test_boot_ci_and_verdict(self):
        rows = [{"g": 1.0, "b": 0.0}] * 30
        ci = ge.boot_ci([[x] for x in rows], lambda xs: sum(x["g"] - x["b"] for x in xs) / len(xs), reps=200)
        self.assertEqual(ci, (1.0, 1.0, 1.0))
        self.assertEqual(ge.verdict(30, ci, ci), "합격")
        self.assertTrue(ge.verdict(5, ci, ci).startswith("못 셌다"))
        self.assertTrue(ge.verdict(30, (0.05, -0.1, 0.2), ci).startswith("판정 불가"))
        self.assertEqual(ge.verdict(30, (0.05, 0.01, 0.1), ci), "불합격")   # 하한은 넘지만 +10%p 미달


class GitTest(unittest.TestCase):
    def test_repo_commits_reads_files_and_skips_merges(self):
        with tempfile.TemporaryDirectory() as d:
            run = lambda *a: subprocess.run(["git", "-C", d, "-c", "commit.gpgsign=false", "-c", "user.name=t", "-c", "user.email=t@t", *a],
                                            check=True, capture_output=True)
            run("init", "-q")
            for name in ("a.txt", "b.txt"):
                open(os.path.join(d, name), "w").write(name)
            run("add", "."); run("commit", "-qm", "one")
            out = ge.repo_commits(d)
            self.assertEqual(len(out), 1)
            self.assertEqual(sorted(out[0][2]), ["a.txt", "b.txt"])

    def test_korean_paths_are_unquoted_and_nfc(self):
        import unicodedata
        with tempfile.TemporaryDirectory() as d:
            run = lambda *a: subprocess.run(["git", "-C", d, "-c", "commit.gpgsign=false", "-c", "user.name=t", "-c", "user.email=t@t", *a],
                                            check=True, capture_output=True)
            run("init", "-q")
            for name in ("세이브.md", "b.txt"):
                open(os.path.join(d, name), "w").write(name)
            run("add", "."); run("commit", "-qm", "one")
            self.assertIn("세이브.md", ge.repo_commits(d)[0][2])
            self.assertEqual(ge.nfc(unicodedata.normalize("NFD", "세이브")), "세이브")


if __name__ == "__main__":
    unittest.main()
