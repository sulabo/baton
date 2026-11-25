#!/usr/bin/env python3
"""/baton-setup 스캐너: 가짜 세션 기록(임시 HOME)으로 문턱 제안·표본 하한·트리거·개인 자료 후보를 세고, apply는 고른 것만 쓴다."""
import json
import os
import re
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
CLEAN = ("CLAUDE_PROJECT_DIR", "BATON_HANDOFF_TRIGGERS_EXTRA", "BATON_SPLIT_RATIOS", "BATON_SPLIT_TOKENS", "BATON_HANDOFF_NUDGE_FILES")
LOCALE = ("BATON_LANG", "LC_ALL", "LC_MESSAGES", "LANG")
HANGUL = re.compile("[\uac00-\ud7a3]")


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


class ScanFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.realpath(self.tmp.name)
        self.repo = os.path.join(self.home, "work", "내 저장소")
        os.makedirs(self.repo)
        env = {k: v for k, v in os.environ.items() if k not in CLEAN}
        env.update(HOME=self.home, XDG_CONFIG_HOME=os.path.join(self.home, "xdg"), BATON_LANG="ko")  # 한국어 출력을 보는 테스트
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


class ScanTest(ScanFixture):
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
        self.assertIsNone(r["nudge"]["recommend"])
        self.assertIn("10개 미만", r["nudge"]["reason"])
        self.assertIn("표본 5개", setup_scan.render(r))

    def test_context_threshold_is_not_proposed_from_history(self):
        # 배수 규칙은 11-25 재계산에서 손해 쪽이었다 — 이 사용자 기록이 크게 불어도 맥락 문턱은 제안하지 않고 기본값과 출처만 보인다
        for _ in range(12):
            self.add(session(self.repo, "작업", [100] + [800] * 30))
        r = self.scan()
        self.assertNotIn("growth", r)
        out = setup_scan.render(r)
        self.assertIn("1) 맥락 문턱 BATON_SPLIT_TOKENS (기본 250000,450000 — 호출 맥락 토큰)", out)
        self.assertIn("2026-11-25 재계산에서 정한 값이다 — 만든 사람 한 명의 대화 50개", out)
        self.assertIn("  제안 없음 (지금 적용 값 250000,450000 — 코드 기본값)", out)
        for gone in ("재계산 절감", "사분위", "배 —", "예전 배수 규칙"):
            self.assertNotIn(gone, out)

    def test_small_window_compactions_are_pointed_out(self):
        # 리뷰 11-25: 20만 창은 25만 전에 자동 압축된다 — 첫 문턱을 넘은 대화가 없고 그 전에 압축된 대화가 있으면 한 줄로 알린다
        for _ in range(3):
            self.add(session(self.repo, "작업", [100000, 150000, 190000, 60000, 120000]))
        self.add(session(self.repo, "작업", [100000, 120000]))
        r = self.scan()
        self.assertEqual({k: r["window"][k] for k in ("band", "counted", "passed", "compacted")},
                         {"band": 250000, "counted": 4, "passed": 0, "compacted": 3})
        line = "  이 저장소 대화 4개 중 25만 토큰을 넘은 대화가 없고 3개는 그 전에 압축됐다(맥락이 40% 넘게 줄어듦)"
        self.assertIn(line, setup_scan.render(r))
        self.assertIn("apply --set BATON_SPLIT_TOKENS=<값>으로 낮출 수는 있지만, 그 크기에서 새로 시작하는 쪽이 더 싼지는 재지 않았다"
                      "(100만 토큰 창 기록에서 15만은 대개 손해였다)", setup_scan.render(r))  # 낮추라고 권하지 않는다(리뷰 11-25)
        with mock.patch.dict(os.environ, {"BATON_SPLIT_TOKENS": "150000"}):  # 이미 낮췄으면(첫 문턱을 넘은 대화가 있으면) 말하지 않는다
            self.assertNotIn("압축됐다", setup_scan.render(self.scan()))
        with mock.patch.dict(os.environ, {"BATON_SPLIT_RATIOS": "2,3"}):  # 배수 규칙이면 이 줄은 없다
            self.assertIsNone(self.scan()["window"])
        self.add(session(self.repo, "작업", [100000, 260000]))  # 한 번이라도 넘었으면 창이 작다고 하지 않는다
        self.assertNotIn("압축됐다", setup_scan.render(self.scan()))

    def test_split_value_in_effect_names_the_rule_that_applies(self):
        # 기본은 토큰 문턱(11-25). 배수만 직접 정한 사람은 배수 값이, 둘 다 정했으면 토큰 값이 지금 적용 값이다
        self.assertIn("(지금 적용 값 250000,450000 — 코드 기본값)", setup_scan.render(self.scan()))
        with mock.patch.dict(os.environ, {"BATON_SPLIT_RATIOS": "2.5,3.5"}):
            out = setup_scan.render(self.scan())
            self.assertIn("(지금 적용 값 2.5,3.5 — 설정 파일·환경변수에서. 그대로 둔다)", out)
            self.assertIn("예전 배수 규칙(BATON_SPLIT_RATIOS, 첫 호출의 몇 배)이 적용된다. 토큰 기본값으로 돌아가려면 "
                          "apply --unset BATON_SPLIT_RATIOS", out)
            with mock.patch.dict(os.environ, {"BATON_SPLIT_TOKENS": "300000"}):
                out = setup_scan.render(self.scan())
                self.assertIn("(지금 적용 값 300000 — 설정 파일·환경변수에서. 그대로 둔다)", out)
                self.assertNotIn("예전 배수 규칙", out)
        with mock.patch.dict(os.environ, {"BATON_SPLIT_RATIOS": "abc"}):  # 훅이 받지 않는 배수 값 — 훅처럼 토큰 기본값으로 본다(리뷰 11-25)
            out = setup_scan.render(self.scan())
            self.assertIn("  제안 없음 (지금 적용 값 250000,450000 — 코드 기본값)", out)
            self.assertNotIn("예전 배수 규칙", out)

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

    def test_named_handoff_counts_as_written(self):
        for _ in range(10):  # 트랙마다 HANDOFF_*.md만 쓰는 사람도 인계서를 쓴 세션으로 센다
            self.add(session(self.repo, "작업", [100, 110], edits=["a.py", "b.py", "c.py", "HANDOFF_track.md"]))
        n = self.scan()["nudge"]
        self.assertNotIn("인계서를 쓴 세션이 0개", n.get("reason") or "")
        self.assertEqual(sum(b["wrote"] for b in n["buckets"]), 10)

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
        self.assertEqual(r["nudge"]["counted"], 3)  # 세는 길을 실제로 탔다
        self.assertEqual(snap(), before)  # 설정·캐시·관찰 로그·저장소 어디에도 안 쓴다


class ApplyFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(self.repo)
        self.env = {k: v for k, v in os.environ.items() if k not in CLEAN}
        self.env["XDG_CONFIG_HOME"] = os.path.join(self.tmp.name, "xdg")
        self.env["HOME"] = os.path.join(self.tmp.name, "home")
        self.env["BATON_LANG"] = "ko"  # 한국어 출력을 보는 테스트 — 영어는 EnglishApplyTest
        self.cfg = os.path.join(self.env["XDG_CONFIG_HOME"], "baton", "config.json")

    def tearDown(self):
        self.tmp.cleanup()

    def apply(self, *args):
        return subprocess.run([sys.executable, SCRIPT, "apply", *args], capture_output=True, text=True, env=self.env)

    def data(self):
        with open(self.cfg, encoding="utf-8") as f:
            return json.load(f)


class ApplyTest(ApplyFixture):
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


class LanguageProposalTest(ScanFixture):
    """사람 프롬프트의 언어로 BATON_LANG을 제안한다 — 고른 경우에만 apply가 쓴다(다른 제안과 같다)."""

    def locale(self, **env):
        for k in LOCALE:
            os.environ.pop(k, None)
        os.environ.update(env)

    def prompts(self, ko, en, other=()):
        for i in range(ko):
            self.add(session(self.repo, f"버그 {i} 고쳐줘", [100, 110]))
        for i in range(en):
            self.add(session(self.repo, f"fix bug {i}", [100, 110]))
        if other:
            self.add(session(self.repo, other[0], [100, 110], more=list(other[1:])))

    def test_mostly_korean_proposes_ko_over_english_locale(self):
        self.locale(LANG="C.UTF-8")
        self.prompts(3, 1)
        lg = self.scan()["language"]
        self.assertEqual((lg["counted"], lg["korean"], lg["other"], lg["current"], lg["source"]), (4, 3, 1, "en", "LANG=C.UTF-8"))
        self.assertEqual(lg["recommend"], "ko")
        self.assertIn("LANG=C.UTF-8", lg["reason"])

    def test_mostly_english_proposes_en_over_korean_locale(self):
        self.locale(LANG="ko_KR.UTF-8")
        self.prompts(1, 3)
        lg = self.scan()["language"]
        self.assertEqual((lg["recommend"], lg["current"]), ("en", "ko"))
        self.assertIn("한글 프롬프트 25%", lg["reason"])  # 출력은 로캘대로 한국어

    def test_same_language_from_locale_is_still_proposed_to_pin_it(self):
        self.locale(LANG="ko_KR.UTF-8")
        self.prompts(3, 0)
        lg = self.scan()["language"]
        self.assertEqual(lg["recommend"], "ko")
        self.assertIn("설정한 값이 아니다", lg["reason"])

    def test_already_set_is_not_proposed(self):
        self.locale(BATON_LANG="ko")
        self.prompts(3, 1)
        self.assertIsNone(self.scan()["language"]["recommend"])
        self.locale(LANG="C.UTF-8")
        config.update(None, {"BATON_LANG": "en"})
        self.prompts(0, 5)  # 이제 영어가 많다 — 설정 파일의 en과 같다
        lg = self.scan()["language"]
        self.assertEqual((lg["recommend"], lg["source"]), (None, "config"))
        self.assertIn("already en", lg["reason"])

    def test_env_override_is_named_in_the_reason(self):
        self.locale(BATON_LANG="en")
        self.prompts(3, 0)
        lg = self.scan()["language"]
        self.assertEqual(lg["recommend"], "ko")
        self.assertIn("environment variable wins over the config file", lg["reason"])

    def test_tie_and_no_letters(self):
        self.locale(LANG="C.UTF-8")
        self.prompts(1, 1, other=("1", "?", "..."))
        lg = self.scan()["language"]
        self.assertEqual((lg["counted"], lg["skipped"], lg["recommend"]), (2, 3, None))
        self.assertIn("half of the prompts", lg["reason"])

    def test_no_prompts_is_uncounted(self):
        self.locale(BATON_LANG="ko")
        lg = self.scan()["language"]
        self.assertEqual((lg["counted"], lg["recommend"]), (0, None))
        self.assertIn("0건이 아니라 못 셈", lg["reason"])
        self.assertIn("7) 출력 언어 BATON_LANG", setup_scan.render(self.scan()))

    def test_proposal_is_written_only_by_apply(self):
        self.locale(LANG="C.UTF-8")
        self.prompts(3, 0)
        self.scan()
        self.assertIsNone(config.load())  # 스캔은 쓰지 않는다
        env = dict(os.environ)
        r = subprocess.run([sys.executable, SCRIPT, "apply", "--global", "--set", "BATON_LANG=ko"], capture_output=True,
                           text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Wrote to the global section", r.stdout)  # 언어는 쓰기 전에 정한다 — 이 실행은 아직 로캘의 en
        self.assertEqual(config.load()["global"], {"BATON_LANG": "ko"})
        self.assertEqual(self.scan()["language"]["source"], "config")


class EnglishScanTest(ScanFixture):
    """BATON_LANG=en이면 스캔 보고 전체가 영어다(저장소 경로·사용자 자료만 원문)."""

    def setUp(self):
        super().setUp()
        os.environ["BATON_LANG"] = "en"

    def english(self, out):
        for p in (self.repo, config.repo_key(self.repo)):
            out = out.replace(p, "<repo>")
        self.assertIsNone(HANGUL.search(out), out)
        return out

    def test_empty_history(self):
        out = self.english(setup_scan.render(self.scan()))
        self.assertIn("That means could not count, not 0", out)
        self.assertIn("Sample of 0: fewer than 10", out)
        self.assertIn("Session logs: 0 session files for this repo's folder → 0 usable sessions", out)
        self.assertIn("Not \"no candidates\" but too small a sample", out)
        self.assertIn("1) Context thresholds BATON_SPLIT_TOKENS (default 250000,450000, context tokens per call)\n"
                      "  Set by the 2026-11-25 recount: an estimate from one person's 50 sessions", out)
        self.assertIn("  No proposal (value in effect now: 250000,450000, the code default)", out)
        self.assertIn("not a git repo: the handoff promotion review (/promote)", out)
        self.assertIn("Output language: en (source: the BATON_LANG environment variable)", out)
        self.assertIn("Codex sessions are not counted", out)

    def test_small_window_line_in_english(self):
        for _ in range(2):
            self.add(session(self.repo, "work", [100000, 190000, 60000]))
        out = self.english(setup_scan.render(self.scan()))
        self.assertIn("  None of the 2 sessions in this repo passed 250K tokens, and 2 were compacted before that (context "
                      "dropped by more than 40%), so with a small context window (such as 200K) this rule doesn't fire. You can "
                      "lower it with apply --set BATON_SPLIT_TOKENS=<value>, but whether starting fresh is cheaper at that size "
                      "wasn't measured (in the 1M-window sessions, 150K was usually a loss)", out)

    def test_full_report(self):
        g = lambda *a: subprocess.run(["git", "-C", self.repo, *a], capture_output=True, text=True, check=True)
        g("init", "-q")
        with open(os.path.join(self.repo, "notes.md"), "w", encoding="utf-8") as f:
            f.write("ProjX notes. Mail boss@corp.io\n")
        g("add", "-A"); g("-c", "user.name=Test Person", "-c", "user.email=tp@corp.io", "commit", "-qm", "x")
        for i in range(12):
            self.add(session(self.repo, "same as yesterday please", [100] + [800] * 30, read_handoff=i < 3,
                             edits=["a.py", "b.py", "c.py", "d.py", "e.py"], handoff_after=4 if i % 2 else None))
        self.add(session("/elsewhere/ProjX", "x", [1]), project="p2")
        r = self.scan()
        out = self.english(setup_scan.render(r))
        self.assertIn("  No proposal (value in effect now: 250000,450000, the code default)", out)  # 크게 부는 기록이어도
        self.assertNotIn("recomputed saving", out)
        self.assertIn("files edited 5 or more: sessions 6 · wrote a handoff 0 (0%)", out)
        self.assertIn("HANDOFF.md: edits 6", out)
        self.assertIn("'yesterday' — first prompts of such sessions: 3 · other prompts it also matches: 9", out)
        self.assertIn("Test Person — git author or email · files in this repo that contain it: 0", out)
        self.assertIn("ProjX — other project name · files in this repo that contain it: 1", out)
        self.assertIn("boss@corp.io — email in a file", out)
        self.assertIn("no HANDOFF.md yet", out)
        self.assertIn("no CONCEPTS.md (commits: 1, tracked files: 1)", out)
        self.assertIn("Session logs: 12 session files for this repo's folder → 12 usable sessions", out)
        self.assertIn("Human prompts counted: 12 · with Korean: 0 · other languages: 12", out)
        self.assertIn("Proposal: no change — 0% of the prompts are in Korean, and the output is already en", out)
        self.english(json.dumps(r, ensure_ascii=False))  # --json의 이유 문장도 영어

    def test_locale_reaches_the_report(self):
        del os.environ["BATON_LANG"]
        for k in ("LC_ALL", "LC_MESSAGES"):
            os.environ.pop(k, None)
        os.environ["LANG"] = "ko_KR.UTF-8"
        self.assertIn("읽기만 했다", setup_scan.render(self.scan()))
        os.environ["LANG"] = "C.UTF-8"
        self.english(setup_scan.render(self.scan()))


class EnglishApplyTest(ApplyFixture):
    def setUp(self):
        super().setUp()
        self.env["BATON_LANG"] = "en"

    def test_english_output_and_errors(self):
        r = self.apply(self.repo, "--set", "BATON_HANDOFF_NUDGE_FILES=4", "--private-term", "Hong", "--trigger", "last time")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("[baton-setup] Wrote to the section for", r.stdout)
        self.assertIn("Added 1 word to the private-words list (this output does not show them)", r.stdout)
        self.assertIn("Added extra trigger phrases: last time", r.stdout)
        self.assertIn("To undo: apply --unset <key>", r.stdout)
        self.assertNotIn("Hong", r.stdout)
        self.assertIsNone(HANGUL.search(r.stdout), r.stdout)
        r = self.apply(self.repo, "--remove-term", "hong", "--remove-term", "Kim")
        self.assertIn("Removed 1 of 2 words from the private-words list from the section for", r.stdout)
        self.assertIn("The rest were not in this section", r.stdout)
        r = self.apply(self.repo, "--unset", "BATON_HANDOFF_NUDGE_FILES")
        self.assertIn("BATON_HANDOFF_NUDGE_FILES removed", r.stdout)
        for args, msg in ((("--set", "BATON_SPLIT_RATIOS=0"), "must be numbers of 1 or more"),
                          (("--set", "BATON_NOPE=1"), "unknown setting: BATON_NOPE. Keys you can set:"),
                          (("--set", "BATON_LANG=kr"), "BATON_LANG: must be one of ko, en, auto"),
                          (("--trigger", "a"), "trigger phrase: must be at least two characters long"),
                          (("--set", "BATON_LOG=/x"), "can only go in the global section. Add --global"),
                          ((), "nothing to change")):
            r = self.apply(self.repo, *args)
            self.assertEqual(r.returncode, 2, args)
            self.assertIn(msg, r.stderr)
            self.assertIsNone(HANGUL.search(r.stderr), r.stderr)
        h = subprocess.run([sys.executable, SCRIPT, "apply", "--help"], capture_output=True, text=True, env=self.env)
        self.assertIn("write to the global section", h.stdout)
        self.assertIsNone(HANGUL.search(h.stdout), h.stdout)

    def test_english_broken_config(self):
        os.makedirs(os.path.dirname(self.cfg))
        with open(self.cfg, "w", encoding="utf-8") as f:
            f.write("{broken")
        r = self.apply(self.repo, "--set", "BATON_SPLIT_RATIOS=3,4")
        self.assertIn("[baton-setup] Could not write:", r.stderr)
        self.assertIn("Not overwriting it", r.stderr)

    def test_locale_fallback(self):
        env = {k: v for k, v in self.env.items() if k not in LOCALE}
        for lang, want in (("ko_KR.UTF-8", "되돌리기"), ("C.UTF-8", "To undo")):
            r = subprocess.run([sys.executable, SCRIPT, "apply", self.repo, "--trigger", "지난번"], capture_output=True,
                               text=True, env=dict(env, LANG=lang))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn(want, r.stdout)


if __name__ == "__main__":
    unittest.main()
