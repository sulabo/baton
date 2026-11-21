#!/usr/bin/env python3
"""그림자 측정: 로그와 세션 기록을 잇고, 정답은 "그 턴에 처음 만진 기존 파일"이며, 표본이 모자라면 못 셌다."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import compile_eval as ce


def tool(name, path, ts, sid="s1"):
    return {"type": "assistant", "timestamp": ts, "sessionId": sid,
            "message": {"content": [{"type": "tool_use", "name": name, "input": {"file_path": path}}]}}


def user(text, ts):
    return {"type": "user", "timestamp": ts, "message": {"content": text}}


class JoinTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.realpath(self.tmp.name)
        self.repo = os.path.join(self.home, "repo")
        os.makedirs(os.path.join(self.repo, "src"))
        g = lambda *a: subprocess.run(["git", "-C", self.repo, "-c", "user.email=t@t", "-c", "user.name=t",
                                       "-c", "commit.gpgsign=false", *a], check=True, capture_output=True, text=True)
        g("init", "-q")
        for f in ("src/a.py", "src/b.py", "src/c.py", "README.md"):
            with open(os.path.join(self.repo, f), "w") as fh:
                fh.write(f)
        g("add", "-A"); g("commit", "-qm", "c")
        self.head = g("rev-parse", "HEAD").stdout.strip()
        p = mock.patch.dict(os.environ, {"HOME": self.home}); p.start(); self.addCleanup(p.stop)
        ce._trees.clear()

    def tearDown(self):
        self.tmp.cleanup()

    def session(self, recs, sub=()):
        d = os.path.join(self.home, ".claude", "projects", "p")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "s1.jsonl"), "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n")
        if sub:
            sd = os.path.join(d, "s1", "subagents"); os.makedirs(sd)
            with open(os.path.join(sd, "x.jsonl"), "w", encoding="utf-8") as f:
                f.write("\n".join(json.dumps(r) for r in sub) + "\n")

    def rec(self, prompt, files, nograph=(), ts="2026-10-07T10:00:00+0900", sid="s1", mode="shadow"):
        return {"event": "prompt", "ts": ts, "session_id": sid, "repo": self.repo,
                "prompt_sha1": hashlib.sha1(prompt.encode()).hexdigest()[:12],
                "compile": {"mode": mode, "head": self.head[:12], "files": list(files), "src": "p" * len(files),
                            "kinds": ["prompt"], "ms": 12,
                            "baselines": {"nograph": list(nograph), "folder": [], "handoff": []}}}

    def test_label_is_first_touch_of_existing_files_in_turn(self):
        A, B, C = (os.path.join(self.repo, "src", x) for x in ("a.py", "b.py", "c.py"))
        self.session([user("첫 질문", "2026-10-07T01:00:00Z"),
                      tool("Read", A, "2026-10-07T01:00:05Z"),
                      user("세이브 고쳐줘", "2026-10-07T01:01:00Z"),
                      tool("Read", A, "2026-10-07T01:01:05Z"),                       # 이미 만진 파일 — 정답 아님
                      tool("Edit", B, "2026-10-07T01:01:06Z"),
                      tool("Write", os.path.join(self.repo, "src", "new.py"), "2026-10-07T01:01:07Z"),  # HEAD에 없음
                      tool("Read", os.path.join(self.repo, "README.md"), "2026-10-07T01:01:08Z"),      # 허브
                      user("다음", "2026-10-07T01:02:00Z"),
                      tool("Read", os.path.join(self.repo, "src", "c.py"), "2026-10-07T01:02:05Z")],   # 다음 턴
                     sub=[tool("Read", C, "2026-10-07T01:01:09Z")])                   # 서브에이전트도 센다
        ts, n = ce.turns([self.rec("세이브 고쳐줘", ["src/b.py", "src/a.py"], nograph=["src/c.py"])])
        self.assertEqual(n["turns"], 1)
        self.assertEqual(ts[0]["label"], {"src/b.py", "src/c.py"})
        self.assertEqual(ce.recall(ts[0], "compiler"), 0.5)
        self.assertEqual(ce.precision(ts[0], "compiler"), 0.5)
        self.assertEqual(ce.recall(ts[0], "nograph"), 0.5)

    def test_time_fallback_join_and_stage_counts(self):
        self.session([user("  공백 붙은 질문  ", "2026-10-07T01:00:00Z"),
                      tool("Read", os.path.join(self.repo, "src", "b.py"), "2026-10-07T01:00:05Z")])
        recs = [self.rec("다른 해시", ["src/b.py"], ts="2026-10-07T09:59:40+0900"),           # 해시는 안 맞고 프롬프트가 20초 뒤
                self.rec("x", [], ts="2026-10-07T12:00:00+0900"),                           # 시각도 멀다
                self.rec("x", [], sid="없는세션")]
        ts, n = ce.turns(recs)
        self.assertEqual((n["turns"], n["no_prompt_match"], n["no_transcript"]), (1, 1, 1))

    def test_records_keep_shadow_only(self):
        log = os.path.join(self.home, "runs.jsonl")
        with open(log, "w", encoding="utf-8") as f:
            err = self.rec("e", []); err["compile"] = {"mode": "shadow", "error": "RuntimeError"}
            for r in (self.rec("a", []), self.rec("b", [], mode="on"), {"event": "prompt", "compile": None}, err,
                      {"event": "split"}, self.rec("c", [], ts="2026-09-01T00:00:00+0900")):
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        n, recs = ce.records(log, None)
        self.assertEqual(n, {"prompt_records": 5, "compile_off": 1, "compile_on": 1, "compile_error": 1})
        self.assertEqual(len(recs), 2)
        n, recs = ce.records(log, "2026-10-01")
        self.assertEqual((n["prompt_records"], len(recs)), (3, 1))

    def test_repeated_prompt_joins_nearest_turn(self):
        A, B = (os.path.join(self.repo, "src", x) for x in ("a.py", "b.py"))
        self.session([user("계속", "2026-10-07T01:00:00Z"), tool("Read", A, "2026-10-07T01:00:05Z"),
                      user("계속", "2026-10-07T01:05:00Z"), tool("Read", B, "2026-10-07T01:05:05Z")])
        recs = [self.rec("계속", ["src/a.py"], ts="2026-10-07T10:00:01+0900"),
                self.rec("계속", ["src/b.py"], ts="2026-10-07T10:05:01+0900")]
        ts, n = ce.turns(recs)
        self.assertEqual([t["label"] for t in ts], [{"src/a.py"}, {"src/b.py"}])
        self.assertEqual([ce.recall(t, "compiler") for t in ts], [1.0, 1.0])

    def test_join_is_order_free_and_prompt_not_before_record(self):
        prompts = [(ce.when("2026-10-07T01:00:00Z"), {"h"})]
        early = {"ts": "2026-10-07T09:00:00+0900", "prompt_sha1": "h"}       # 한 시간 앞선 기록 — 기록에 없는 다른 "계속"
        right = {"ts": "2026-10-07T10:00:00+0900", "prompt_sha1": "h"}
        self.assertEqual(ce.join([early, right], prompts), [None, 0])
        late = {"ts": "2026-10-07T10:00:30+0900", "prompt_sha1": "x"}        # 프롬프트가 기록보다 30초 앞섬 — 시각 대체도 안 붙는다
        self.assertEqual(ce.join([late], prompts), [None])

    def test_pasted_command_tag_is_not_a_command(self):
        self.session([user("이 기록 봐: <command-name>/x</command-name>", "2026-10-07T01:00:00Z"),
                      tool("Read", os.path.join(self.repo, "src", "a.py"), "2026-10-07T01:00:05Z")])
        ts, n = ce.turns([self.rec("이 기록 봐: <command-name>/x</command-name>", ["src/a.py"],
                                   ts="2026-10-07T09:50:00+0900")])            # 10분 차 — 시각 대체(60초)로는 못 잇고 해시로만
        self.assertEqual(n["turns"], 1)

    def test_slash_command_is_turn_boundary_and_joinable(self):
        A, B = (os.path.join(self.repo, "src", x) for x in ("a.py", "b.py"))
        cmd = "<command-name>/baton-explain</command-name>\n<command-args>세이브</command-args>"
        self.session([user("세이브 고쳐줘", "2026-10-07T01:00:00Z"), tool("Read", A, "2026-10-07T01:00:05Z"),
                      user(cmd, "2026-10-07T01:00:30Z"), tool("Read", B, "2026-10-07T01:00:35Z")])
        recs = [self.rec("세이브 고쳐줘", ["src/a.py"], ts="2026-10-07T10:00:00+0900"),
                self.rec("/baton-explain 세이브", ["src/b.py"], ts="2026-10-07T10:00:30+0900")]
        ts, n = ce.turns(recs)
        self.assertEqual([t["label"] for t in ts], [{"src/a.py"}, {"src/b.py"}])  # 앞 턴 정답이 명령 턴까지 늘지 않는다

    def test_candidates_limited_to_files_in_head(self):
        new = os.path.join(self.repo, "src", "new.py")
        with open(new, "w") as fh:
            fh.write("x")
        self.session([user("세이브", "2026-10-07T01:00:00Z"), tool("Read", new, "2026-10-07T01:00:03Z"),
                      tool("Read", os.path.join(self.repo, "src", "a.py"), "2026-10-07T01:00:05Z")])
        r = self.rec("세이브", ["src/new.py", "src/a.py"], nograph=["src/new.py"])
        ts, n = ce.turns([r])
        self.assertEqual(ts[0]["arms"]["compiler"], ["src/a.py"])
        self.assertEqual(ts[0]["arms"]["nograph"], [])
        self.assertEqual(ts[0]["src"], "p")
        self.assertEqual(n["first_touch_not_in_head"], 1)

    def test_main_reports_uncounted_when_empty(self):
        out = subprocess.run([sys.executable, os.path.join(HERE, "compile_eval.py"), "--log",
                              os.path.join(self.home, "없음.jsonl")], capture_output=True, text=True,
                             env=dict(os.environ, HOME=self.home), check=True).stdout
        self.assertIn("판정: 못 셌다 — 측정 턴 0개", out)


class VerdictTest(unittest.TestCase):
    def turns(self, n_sessions, per, comp_hit, nog_hit):
        out = []
        for s in range(n_sessions):
            for i in range(per):
                out.append({"session": f"s{s}", "label": {"x"}, "src": "p", "kinds": ["prompt"], "ms": 5,
                            "arms": {"compiler": ["x"] if (s * per + i) % 10 < comp_hit else ["y"],
                                     "nograph": ["x"] if (s * per + i) % 10 < nog_hit else ["y"],
                                     "folder": [], "handoff": []}})
        return out

    def test_too_few_is_uncounted(self):
        self.assertEqual(ce.evaluate(self.turns(4, 10, 9, 1))["verdict"], "못 셌다")   # 세션 4개
        self.assertEqual(ce.evaluate(self.turns(5, 5, 9, 1))["verdict"], "못 셌다")    # 턴 25개

    def test_pass_and_fail(self):
        self.assertEqual(ce.evaluate(self.turns(6, 10, 6, 2))["verdict"], "합격")
        r = ce.evaluate(self.turns(6, 10, 2, 2))
        self.assertEqual(r["verdict"], "판정 불가")
        self.assertEqual(ce.evaluate(self.turns(6, 10, 1, 6))["verdict"], "불합격")

    def test_source_and_prompt_concept_counts(self):
        r = ce.evaluate(self.turns(1, 10, 3, 0))
        self.assertEqual(r["by_source"]["프롬프트 개념"], {"picked": 10, "hit": 3})
        self.assertEqual((r["prompt_concept_turns"], r["prompt_concept_hit"]), (10, 3))
        r = ce.evaluate(self.turns(1, 10, 3, 3))                 # 그래프 없이도 뽑혔을 적중은 개념 적중으로 안 센다
        self.assertEqual(r["prompt_concept_hit"], 0)

    def test_bar_boundary(self):
        self.assertEqual(ce.evaluate(self.turns(6, 10, 5, 4))["verdict"], "합격")      # 정확히 +10%p(0.5−0.4=0.0999…)는 합격
        below = self.turns(6, 20, 0, 0)
        for t in below[::20]:
            t["arms"]["compiler"] = ["x"]                                             # 세션마다 20턴 중 1턴만 더 맞힘: +5%p
        r = ce.evaluate(below)
        self.assertGreater(r["ci"][0], 0)
        self.assertEqual(r["verdict"], "불합격")                                       # 하한 > 0이어도 +10%p 미만이면 불합격


if __name__ == "__main__":
    unittest.main()
