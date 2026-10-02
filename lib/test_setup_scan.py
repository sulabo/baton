#!/usr/bin/env python3
"""/baton-setup 스캐너: 가짜 세션 기록(임시 HOME)으로 문턱 제안·표본 하한·트리거·개인 자료 후보를 세고, apply는 고른 것만 쓴다."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import config
import setup_scan

SCRIPT = os.path.join(HERE, "setup_scan.py")
CLEAN = ("CLAUDE_PROJECT_DIR", "BATON_HANDOFF_TRIGGERS_EXTRA", "BATON_SPLIT_RATIOS", "BATON_HANDOFF_NUDGE_FILES")


def session(cwd, prompt, ctxs, edits=(), handoff_after=None, read_handoff=False, more=(), injected=False):
    """세션 기록 한 개. ctxs: 호출별 맥락 토큰. edits: 편집 파일 이름들. handoff_after: 그 수만큼 편집한 뒤 HANDOFF.md를 쓴다.
    more: 뒤이은 사람 프롬프트들. injected: 훅이 인계서를 넣은 기록을 남긴다."""
    recs = [{"type": "user", "cwd": cwd, "entrypoint": "cli", "timestamp": "2026-09-29T01:00:00Z", "message": {"content": prompt}}]
    paths = [os.path.join(cwd, e) for e in edits]
    if handoff_after is not None:
        paths.insert(handoff_after, os.path.join(cwd, "HANDOFF.md"))
    for i, c in enumerate(ctxs):
        content = []
        if i == 0 and read_handoff:
            content.append({"type": "tool_use", "name": "Read", "input": {"file_path": os.path.join(cwd, "HANDOFF.md")}})
        if i == len(ctxs) - 1:
            content += [{"type": "tool_use", "name": "Edit", "input": {"file_path": p}} for p in paths]
        recs.append({"type": "assistant", "cwd": cwd, "message": {"id": f"m{i}", "model": "claude-x", "content": content,
                                                                  "usage": {"input_tokens": c}}})
    if injected:
        recs.insert(1, {"type": "attachment", "attachment": {"hookEvent": "UserPromptSubmit", "content": "[baton] 아래는 …"}})
    recs += [{"type": "user", "cwd": cwd, "message": {"content": m}} for m in more]
    return recs


class ScanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.realpath(self.tmp.name)
        self.repo = os.path.join(self.home, "work", "내 저장소")
        os.makedirs(self.repo)
        env = {k: v for k, v in os.environ.items() if k not in CLEAN}
        env.update(HOME=self.home, XDG_CONFIG_HOME=os.path.join(self.home, "xdg"))
        for p in (mock.patch.dict(os.environ, env, clear=True),
                  mock.patch.object(setup_scan.usage_week, "experimental", lambda cwd: not cwd)):  # 임시 폴더도 실사용으로 센다
            p.start(); self.addCleanup(p.stop)
        self.n = 0

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, recs, project="proj"):
        self.n += 1
        p = os.path.join(self.home, ".claude", "projects", project, f"s{self.n}.jsonl")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n")

    def scan(self):
        return setup_scan.scan(config.repo_key(self.repo))

    def test_sessions_matched_by_cwd_only(self):
        self.add(session(self.repo, "버그 고쳐줘", [100, 120]))
        self.add(session(os.path.join(self.home, "other"), "버그 고쳐줘", [100, 120]), project="other")
        r = self.scan()
        self.assertEqual((r["sessions"]["files"], r["sessions"]["usable"]), (1, 1))
        self.assertIn("Codex 세션은 세지 않음", r["codex"])

    def test_sample_floor_keeps_defaults(self):
        for _ in range(5):
            self.add(session(self.repo, "작업", [100, 500, 900], edits=["a.py", "b.py", "c.py", "d.py"], handoff_after=4))
        r = self.scan()
        self.assertEqual(r["growth"]["counted"], 5)
        self.assertIsNone(r["growth"]["recommend"])
        self.assertIn("10개 미만", r["growth"]["reason"])
        self.assertIsNone(r["nudge"]["recommend"])
        self.assertIn("10개 미만", r["nudge"]["reason"])
        self.assertIn("표본 5개", setup_scan.render(r))

    def test_growth_recommends_higher_band_when_cost_stays_late(self):
        # 모든 세션이 8배까지 크게 분다 — 4배에 닿은 뒤에도 비용 대부분이 남으므로 2배보다 높은 문턱을 권한다
        for _ in range(12):
            self.add(session(self.repo, "작업", [100] + [800] * 30))
        g = self.scan()["growth"]
        self.assertEqual((g["counted"], g["uncounted"]), (12, 0))
        self.assertEqual(g["quartiles"], [8.0, 8.0, 8.0])
        self.assertEqual(g["recommend"], "4,5")
        self.assertTrue(all(c["reach"] == 1.0 for c in g["candidates"]))

    def test_growth_short_sessions_keep_default_and_missing_usage_uncounted(self):
        for _ in range(11):
            self.add(session(self.repo, "작업", [100, 110, 120]))
        self.add(session(self.repo, "작업", [0, 100]))
        g = self.scan()["growth"]
        self.assertEqual((g["counted"], g["uncounted"]), (11, 1))
        self.assertIsNone(g["recommend"])
        self.assertIn("남지 않는다", g["reason"])

    def test_nudge_boundary_and_handoff_names(self):
        for _ in range(4):
            self.add(session(self.repo, "작업", [100, 110], edits=["a.py"]))
            self.add(session(self.repo, "작업", [100, 110], edits=["a.py", "b.py", "c.py"]))
            self.add(session(self.repo, "작업", [100, 110], edits=["a.py", "b.py", "c.py", "d.py", "e.py", "HANDOFF-x.md"],
                             handoff_after=5))
        self.add(session(self.repo, "질문만", [100, 110]))
        n = self.scan()["nudge"]
        self.assertEqual((n["counted"], n["excluded"]), (12, 1))
        self.assertEqual(n["recommend"], "4")
        self.assertEqual(n["names"], {"HANDOFF.md": 4, "HANDOFF-x.md": 4})
        self.assertEqual([b["wrote"] for b in n["buckets"]], [0, 0, 0, 0, 4])

    def test_nudge_without_any_handoff_keeps_default(self):
        for _ in range(10):
            self.add(session(self.repo, "작업", [100, 110], edits=["a.py", "b.py"]))
        n = self.scan()["nudge"]
        self.assertIsNone(n["recommend"])
        self.assertIn("인계서를 쓴 세션이 0개", n["reason"])

    def test_trigger_candidates_and_existing_extra_excluded(self):
        self.add(session(self.repo, "저번 세션 계속 가자", [100, 110], read_handoff=True))
        self.add(session(self.repo, "저번 세션 계속 하자", [100, 110], read_handoff=True))
        self.add(session(self.repo, "이어서 하자", [100, 110], read_handoff=True))  # 지금 트리거가 맞은 세션은 빼고 센다
        self.add(session(self.repo, "버그 고쳐줘", [100, 110], more=["이제 계속 해줘"]))  # 세션 중간 프롬프트에도 훅은 걸린다
        self.add(session(self.repo, "이어서", [100, 110], injected=True, more=["계속"]))  # 훅이 넣은 세션은 "안 읽음"이 아니다
        t = self.scan()["triggers"]
        self.assertEqual((t["sessions_read_untriggered"], t["sessions_not_read"], t["other_prompts"]), (2, 1, 5))
        c = {x["phrase"]: (x["read"], x["other_prompts"]) for x in t["candidates"]}
        self.assertEqual(c["저번 세션"], (2, 0))
        self.assertEqual(c["계속"], (2, 2))
        self.assertNotIn("하자", c)  # 한 세션에만 나온 말은 후보가 아니다
        config.update(config.repo_key(self.repo), add={"BATON_HANDOFF_TRIGGERS_EXTRA": ["저번"]})
        t = self.scan()["triggers"]
        self.assertEqual((t["sessions_read_untriggered"], t["candidates"]), (0, []))
        self.assertIn("표본 부족", setup_scan.render(self.scan()))

    def test_no_sessions_reported_as_uncounted(self):
        out = setup_scan.render(self.scan())
        self.assertIn("0건이 아니라 못 셈", out)
        self.assertIn("표본 0개", out)

    def test_private_candidates_from_git_user_and_other_projects(self):
        g = lambda *a: subprocess.run(["git", "-C", self.repo, *a], capture_output=True, text=True, check=True)
        g("init", "-q")
        with open(os.path.join(self.repo, "notes.md"), "w", encoding="utf-8") as f:
            f.write("ProjX 참고. 연락 boss@corp.io, 예시 a@example.com\n")
        g("add", "-A"); g("-c", "user.name=Test Person", "-c", "user.email=tp@corp.io", "commit", "-qm", "x")
        self.add(session("/elsewhere/ProjX", "x", [1]), project="p2")
        self.add(session("/elsewhere/Unrelated", "x", [1]), project="p3")
        p = setup_scan.private_candidates(config.repo_key(self.repo))
        terms = {c["term"]: (c["source"], c["files"]) for c in p["candidates"]}
        self.assertEqual(terms["Test Person"][0], "git 작성자·이메일")
        self.assertIn("tp@corp.io", terms)
        self.assertEqual(terms["ProjX"], ("다른 프로젝트 이름", 1))
        self.assertEqual(terms["boss@corp.io"], ("파일 속 이메일", 1))
        self.assertNotIn("Unrelated", terms)  # 이 저장소에 안 나오는 이름은 제안하지 않는다
        self.assertNotIn("a@example.com", terms)
        self.assertTrue(any("다른 프로젝트 2개" in x for x in p["notes"]))

    def test_subfolder_of_this_repo_is_not_another_project(self):
        subprocess.run(["git", "-C", self.repo, "init", "-q"], check=True)
        os.makedirs(os.path.join(self.repo, "frontend"))
        with open(os.path.join(self.repo, "notes.md"), "w", encoding="utf-8") as f:
            f.write("frontend 폴더 참고\n")
        self.add(session(os.path.join(self.repo, "frontend"), "x", [1]), project="p2")
        terms = [c["term"] for c in setup_scan.private_candidates(config.repo_key(self.repo))["candidates"]]
        self.assertNotIn("frontend", terms)

    def test_repo_without_commits_is_not_called_non_git(self):
        subprocess.run(["git", "-C", self.repo, "init", "-q"], check=True)
        notes = setup_scan.private_candidates(config.repo_key(self.repo))["notes"]
        self.assertIn("커밋이 아직 없어 git 작성자를 못 셈", notes)

    def test_not_a_git_repo_is_uncounted(self):
        p = setup_scan.private_candidates(config.repo_key(self.repo))
        self.assertTrue(any("못 셈" in x for x in p["notes"]))
        self.assertIn("git 저장소가 아니다", setup_scan.repo_advice(config.repo_key(self.repo))[0])

    def test_scan_writes_nothing(self):
        cache = tempfile.mkdtemp(); self.addCleanup(__import__("shutil").rmtree, cache)
        os.environ["XDG_CACHE_HOME"] = cache
        for _ in range(3):
            self.add(session(self.repo, "작업", [100, 300, 500], edits=["a.py", "b.py"], handoff_after=2, read_handoff=True))
        snap = lambda: [sorted(os.walk(d)) for d in (self.home, cache)]
        before = snap()
        r = self.scan()
        setup_scan.render(r)
        self.assertEqual((r["growth"]["counted"], r["nudge"]["counted"]), (3, 3))  # 세는 길을 실제로 탔다
        self.assertEqual(snap(), before)  # 설정·캐시·관찰 로그·저장소 어디에도 안 쓴다


class ApplyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(self.repo)
        self.env = {k: v for k, v in os.environ.items() if k not in CLEAN}
        self.env["XDG_CONFIG_HOME"] = os.path.join(self.tmp.name, "xdg")
        self.env["HOME"] = os.path.join(self.tmp.name, "home")
        self.cfg = os.path.join(self.env["XDG_CONFIG_HOME"], "baton", "config.json")

    def tearDown(self):
        self.tmp.cleanup()

    def apply(self, *args):
        return subprocess.run([sys.executable, SCRIPT, "apply", *args], capture_output=True, text=True, env=self.env)

    def data(self):
        with open(self.cfg, encoding="utf-8") as f:
            return json.load(f)

    def test_writes_only_chosen_values_without_echoing_terms(self):
        r = self.apply(self.repo, "--set", "BATON_HANDOFF_NUDGE_FILES=4", "--private-term", "홍길동", "--trigger", "지난번")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("홍길동", r.stdout)
        self.assertIn("되돌리기", r.stdout)
        self.assertEqual(self.data()["repos"][config.repo_key(self.repo)],
                         {"BATON_HANDOFF_NUDGE_FILES": "4", "private_terms": ["홍길동"], "BATON_HANDOFF_TRIGGERS_EXTRA": ["지난번"]})
        self.assertEqual(self.data()["global"], {})
        self.assertEqual(oct(os.stat(self.cfg).st_mode & 0o777), "0o600")
        self.assertEqual(self.apply(self.repo, "--unset", "BATON_HANDOFF_NUDGE_FILES").returncode, 0)
        self.assertNotIn("BATON_HANDOFF_NUDGE_FILES", self.data()["repos"][config.repo_key(self.repo)])

    def test_global_and_rejections(self):
        self.assertEqual(self.apply("--global", "--set", "BATON_OBSERVE=off").returncode, 0)
        self.assertEqual(self.data()["global"], {"BATON_OBSERVE": "off"})
        bad = [("--set", "BATON_NOPE=1"), ("--set", "BATON_SPLIT_RATIOS"), ("--set", "BATON_LOG=/x"), (),
               ("--set", "BATON_SPLIT_RATIOS="), ("--set", "BATON_SPLIT_RATIOS=0"), ("--set", "BATON_SPLIT_RATIOS=2,nan"),
               ("--set", "BATON_SPLIT_RATIOS=2,inf"), ("--set", "BATON_HANDOFF_NUDGE_FILES=0"), ("--set", "BATON_HANDOFF_NUDGE_FILES=2.5"),
               ("--set", "BATON_HANDOFF_INJECT=of"), ("--trigger", "가"), ("--private-term", "x")]
        for args in bad:
            r = self.apply(self.repo, *args)
            self.assertEqual(r.returncode, 2, args)
        self.assertNotIn("repos", {k: v for k, v in self.data().items() if v})
        self.assertEqual(self.apply("--global", "--set", "BATON_LOG=~/l.jsonl", "--set", "BATON_OBSERVE=ON").returncode, 0)
        self.assertEqual(self.data()["global"]["BATON_LOG"], os.path.join(self.env["HOME"], "l.jsonl"))  # "~"를 펼쳐 저장한다
        self.assertEqual(self.apply(self.repo, "--set", "BATON_SPLIT_RATIOS=2.5, 3.5").returncode, 0)

    def test_terms_from_file_or_stdin_and_removal(self):
        f = os.path.join(self.tmp.name, "terms.txt")
        with open(f, "w", encoding="utf-8") as fh:
            fh.write("홍길동\n\n  ProjX  \n")
        r = self.apply(self.repo, "--private-terms-file", f)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("홍길동", r.stdout + r.stderr)
        r = subprocess.run([sys.executable, SCRIPT, "apply", self.repo, "--private-terms-file", "-"], input="이몽룡\n",
                           capture_output=True, text=True, env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        key = config.repo_key(self.repo)
        self.assertEqual(self.data()["repos"][key]["private_terms"], ["홍길동", "ProjX", "이몽룡"])
        self.assertEqual(self.apply(self.repo, "--remove-term", "ProjX", "--trigger", "지난번").returncode, 0)
        self.assertEqual(self.data()["repos"][key]["private_terms"], ["홍길동", "이몽룡"])
        self.assertEqual(self.apply(self.repo, "--remove-term", "홍길동", "--remove-term", "이몽룡", "--remove-trigger", "지난번").returncode, 0)
        self.assertNotIn(key, self.data()["repos"])  # 다 빼면 절도 지운다
        self.assertEqual(self.apply(self.repo, "--private-terms-file", "/없는/파일").returncode, 2)

    def test_bom_and_non_utf8_terms_files(self):
        f = os.path.join(self.tmp.name, "terms.txt")
        with open(f, "w", encoding="utf-8-sig") as fh:  # 메모장 등이 붙이는 BOM
            fh.write("홍길동\n")
        self.assertEqual(self.apply(self.repo, "--private-terms-file", f).returncode, 0)
        r = subprocess.run([sys.executable, SCRIPT, "apply", self.repo, "--private-terms-file", "-"], input="\ufeff이몽룡\n",
                           capture_output=True, text=True, env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.data()["repos"][config.repo_key(self.repo)]["private_terms"], ["홍길동", "이몽룡"])
        with open(f, "wb") as fh:
            fh.write("성춘향\n".encode("cp949"))
        r = self.apply(self.repo, "--private-terms-file", f)
        self.assertEqual(r.returncode, 2)
        self.assertIn("UTF-8", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_remove_reports_actual_count_and_other_section(self):
        self.assertEqual(self.apply(self.repo, "--private-term", "Kim").returncode, 0)
        self.assertEqual(self.apply("--global", "--private-term", "Lee").returncode, 0)
        f = os.path.join(self.tmp.name, "rm.txt")
        with open(f, "w", encoding="utf-8") as fh:
            fh.write("kim\nLee\n")
        r = self.apply(self.repo, "--remove-terms-file", f)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("2개 중 1개를", r.stdout)  # Kim은 대소문자 무시로 빠지고, Lee는 이 절에 없었다
        self.assertIn("다른 전역 절에 남아 여전히 적용된다", r.stdout)
        self.assertNotIn("Lee", r.stdout); self.assertNotIn("kim", r.stdout.lower())
        self.assertNotIn(config.repo_key(self.repo), self.data()["repos"])
        r = self.apply(self.repo, "--remove-term", "없는단어")
        self.assertIn("1개 중 0개를", r.stdout)

    def test_subfolder_session_uses_repo_root_section(self):
        # apply는 저장소 최상위에서(CLAUDE_PROJECT_DIR 없음), Claude Code는 하위 폴더 app에서 연 경우 — 훅이 같은 절을 찾아야 한다
        subprocess.run(["git", "-C", self.repo, "init", "-q"], check=True)
        app = os.path.join(self.repo, "app"); os.makedirs(app)
        r = subprocess.run([sys.executable, SCRIPT, "apply", "--private-terms-file", "-", "--trigger", "지난번"], input="홍길동\n",
                           cwd=self.repo, capture_output=True, text=True, env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        handoff = os.path.join(app, "HANDOFF.md")
        with open(handoff, "w", encoding="utf-8") as fh:
            fh.write("# Handoff\n- 홍길동 님 요청\n")
        env = dict(self.env, CLAUDE_PROJECT_DIR=app, BATON_LOG=os.path.join(self.tmp.name, "runs.jsonl"))
        hook = lambda name, payload: subprocess.run([sys.executable, os.path.join(os.path.dirname(HERE), "hooks", name)],
                                                    input=json.dumps(payload), capture_output=True, text=True, env=env)
        out = hook("handoff-check.py", {"hook_event_name": "PostToolUse", "tool_input": {"file_path": handoff}, "cwd": app})
        self.assertIn("개인 자료 목록 단어 1개", json.loads(out.stdout)["reason"])
        out = hook("handoff-inject.py", {"prompt": "지난번 거"})
        self.assertIn("[baton] 아래는", out.stdout)

    def test_broken_config_refused_and_kept(self):
        os.makedirs(os.path.dirname(self.cfg))
        with open(self.cfg, "w", encoding="utf-8") as f:
            f.write("{깨진")
        r = self.apply(self.repo, "--set", "BATON_SPLIT_RATIOS=3,4")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("덮어쓰지 않는다", r.stderr)
        with open(self.cfg, encoding="utf-8") as f:
            self.assertEqual(f.read(), "{깨진")


if __name__ == "__main__":
    unittest.main()
