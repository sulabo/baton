#!/usr/bin/env python3
"""북극성 길 단계 1: 규칙 판단(MATCHED/AMBIGUOUS/NO_MATCH)과 훅의 관찰 로그. 행동은 그대로여야 한다."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rules

HOOK = os.path.join(os.path.dirname(HERE), "hooks", "handoff-inject.py")
MAP = "## 1. 세이브 — 저장 규칙\n본문1\n\n## 2. 카메라 — 시점\n본문2\n"


_TMP = [tempfile.TemporaryDirectory()]
_CFG_ENV = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": _TMP[0].name})  # 실제 설정 파일을 읽지 않는다(훅 자식 프로세스도)


def setUpModule():
    _CFG_ENV.start()


def repo(files):
    t = tempfile.TemporaryDirectory(); _TMP.append(t)  # 모듈 끝(tearDownModule)에서 지운다
    for rel, text in files.items():
        p = os.path.join(t.name, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f: f.write(text)
    return t.name


def tearDownModule():
    _CFG_ENV.stop()
    for t in _TMP: t.cleanup()


def read_log(path):
    if not os.path.exists(path): return []
    with open(path, encoding="utf-8") as f: return [json.loads(l) for l in f]


class DecideTest(unittest.TestCase):
    def test_handoff_state_and_file(self):
        d = rules.decide(repo({"HANDOFF.md": "x"}), "이어서 진행해줘")["handoff"]
        self.assertEqual((d["state"], d["file"]), ("MATCHED", True))
        self.assertEqual(rules.decide(repo({}), "이어서")["handoff"]["file"], False)
        self.assertEqual(rules.decide(repo({}), "버그 고쳐줘")["handoff"]["state"], "NO_MATCH")

    def test_english_trigger_phrases(self):
        r = repo({"HANDOFF.md": "x"})
        for p in ("Where were we?", "pick up where we left off", "Let's pick things back up where we stopped",
                  "catch me up on this repo", "how far did we get?", "continue from the last session",
                  "read the hand-off and go"):
            self.assertEqual(rules.decide(r, p)["handoff"]["state"], "MATCHED", p)
        # 단어 하나·다른 뜻은 걸리지 않는다
        for p in ("continue", "please continue the refactor", "show the progress bar", "what's the status code?",
                  "resume the download", "where were the logs written?", "last session cookie expired",
                  "the payload handed off to a worker"):
            self.assertEqual(rules.decide(r, p)["handoff"]["state"], "NO_MATCH", p)

    def test_concept_states(self):
        r = repo({"CONCEPTS.md": MAP})
        self.assertEqual(rules.decide(r, "세이브 고쳐줘")["concepts"]["state"], "MATCHED")
        self.assertEqual(rules.decide(r, "세이브랑 카메라")["concepts"]["state"], "AMBIGUOUS")
        self.assertEqual(rules.decide(r, "빌드 돌려줘")["concepts"]["state"], "NO_MATCH")
        self.assertEqual(rules.decide(r, "저장 규칙 고쳐줘")["concepts"]["state"], "NO_MATCH")  # 제목의 — 뒤 설명은 매칭에 안 쓴다
        self.assertEqual(rules.decide(repo({}), "세이브")["concepts"]["state"], "NO_MAP")  # 지도 없음은 0이 아니라 못 셈

    def test_task_type_states(self):
        self.assertEqual(rules.classify_task_type("버그 고쳐줘")[:2], ("MATCHED", "debugging"))
        self.assertEqual(rules.classify_task_type("버그 고쳐서 테스트 돌려")[0], "AMBIGUOUS")
        self.assertEqual(rules.classify_task_type("ㅇㅋ")[0], "NO_MATCH")

    def test_explain_reports_missing_handoff_and_map(self):
        out = rules.explain(repo({}), "이어서 세이브")
        self.assertIn("HANDOFF.md가 없어 못 넣는다", out)
        self.assertIn("후보를 못 셌다", out)

    def test_trigger_extra_from_config_extends_default(self):
        env = mock.patch.dict(os.environ); env.start(); self.addCleanup(env.stop)
        os.environ.pop("BATON_HANDOFF_TRIGGERS_EXTRA", None)  # 환경변수가 설정 파일을 덮지 않게
        r = repo({"HANDOFF.md": "x"})
        default = rules.decide(r, "지난번 거 계속 이어서")["handoff"]
        self.assertEqual(default["words"], ["이어서"])  # 설정이 없으면 기존 TRIGGER 그대로
        cfg = os.path.join(os.environ["XDG_CONFIG_HOME"], "baton", "config.json")
        os.makedirs(os.path.dirname(cfg), exist_ok=True)
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump({"repos": {rules.config.repo_key(r): {"BATON_HANDOFF_TRIGGERS_EXTRA": ["지난번", "LAST TIME"]}}}, f)
        self.addCleanup(os.remove, cfg)
        self.assertEqual(rules.decide(r, "지난번 거 계속 이어서")["handoff"]["words"], ["이어서", "지난번"])
        self.assertEqual(rules.decide(r, "pick up from last time")["handoff"]["state"], "MATCHED")  # 대소문자 무시
        self.assertEqual(rules.decide(r, "버그 고쳐줘")["handoff"]["state"], "NO_MATCH")
        self.assertEqual(rules.decide(repo({}), "지난번 거")["handoff"]["state"], "NO_MATCH")  # 다른 저장소에는 안 퍼진다

    def test_trigger_words_deduplicated_and_domain_unconfigured(self):
        d = rules.decide(repo({}), "이어서 이어서 이어서 인계")
        self.assertEqual(d["handoff"]["words"], ["이어서", "인계"])
        self.assertEqual(d["domain"]["state"], "UNCONFIGURED")

    def test_explain_reads_stdin_and_respects_injection_off(self):
        r = repo({"HANDOFF.md": "x"})
        p = subprocess.run([sys.executable, os.path.join(HERE, "rules.py"), "explain", "-", r],
                           input='이어서 `rm -rf x` $(echo hi) "따옴표"', capture_output=True, text=True,
                           env=dict(os.environ, BATON_HANDOFF_INJECT="off"))
        self.assertEqual(p.returncode, 0)
        self.assertIn("BATON_HANDOFF_INJECT=off라 넣지 않는다", p.stdout)

    def test_repo_root_survives_missing_git(self):
        env = dict(os.environ, PATH="/nonexistent"); env.pop("CLAUDE_PROJECT_DIR", None)
        d = repo({})
        r = subprocess.run([sys.executable, HOOK], input=json.dumps({"prompt": "이어서", "cwd": d}),
                           capture_output=True, text=True, env=dict(env, BATON_LOG=os.path.join(d, "l.jsonl")))
        self.assertEqual((r.returncode, r.stderr), (0, ""))

    def test_machine_prompt(self):
        for p in ['<agent-message from="a3d1">\n[Subagent] HANDOFF 갱신했다', '  <task-notification>\n인계 완료',
                  'Another Claude session sent a message: <cross-session-message from="uds:/tmp/x">이어서']:
            self.assertTrue(rules.machine_prompt(p), p)
        for p in ["핸드오프 읽고 이어서", "이 <agent-message> 태그가 왜 인계를 부르지?", "<agent-messages> 이어서", "<agent-message-x> 이어서", ""]:
            self.assertFalse(rules.machine_prompt(p), p)
        out = rules.explain(repo({"HANDOFF.md": "a\n"}), '<agent-message from="x">이어서')
        self.assertIn("다른 세션·작업 알림이 보낸 메시지라 넣지 않는다", out)
        r = repo({"HANDOFF.md": "a\n", "CONCEPTS.md": "## 1. 세이브\n본문\n"})
        d = rules.decide(r, '<agent-message from="x">세이브 고쳐줘, 이어서')
        self.assertTrue(d["machine"])
        self.assertEqual((d["concepts"]["state"], d["concepts"]["candidates"]), ("MACHINE", []))  # 0이 아니라 안 셈
        self.assertEqual(d["task_type"]["state"], "MACHINE")
        out = rules.explain(r, '<agent-message from="x">세이브 고쳐줘, 이어서')
        self.assertIn("작업 종류 MACHINE — 다른 세션·작업 알림이 보낸 메시지라 세지 않았다", out)
        self.assertNotIn("MACHINE — 없음", out)  # "없음"은 0건으로 읽힌다
        self.assertEqual(rules.decide(r, "세이브 고쳐줘")["concepts"]["state"], "MATCHED")
        self.assertFalse(rules.decide(r, "세이브 고쳐줘")["machine"])
        self.assertIn("HANDOFF.md가 없어", rules.explain(repo({}), '<agent-message from="x">이어서'))  # 훅과 같은 순서


def git(root, *args):
    subprocess.run(["git", "-C", root, "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                   check=True, capture_output=True)


class FreshnessTest(unittest.TestCase):
    """인계서는 작성 시점의 가설 — 주입 때 작성일·며칠 전·그 뒤 커밋 수를 사실로 붙인다."""
    TODAY = __import__("datetime").date(2026, 11, 8)

    def test_header_date_and_stale_warning(self):
        text = "# Session Handoff (작성: 2026-10-01 · 메모)\n"
        f = rules.handoff_freshness(repo({"HANDOFF.md": text}), text, self.TODAY)
        self.assertEqual((f["written"], f["source"], f["days"], f["commits_after"]), ("2026-10-01", "header", 38, None))
        line = rules.freshness_line(f)
        self.assertIn("2026-10-01(38일 전, 첫 줄 작성일) 기준", line)
        self.assertIn("38일 지났다", line)

    def test_fresh_handoff_has_no_warning(self):
        f = rules.handoff_freshness(repo({}), "# Session Handoff (작성: 2026-11-08)\n", self.TODAY)
        line = rules.freshness_line(f)
        self.assertIn("(오늘,", line)
        self.assertNotIn("지났다", line)

    def test_no_date_and_no_git_says_it_could_not_count(self):
        f = rules.handoff_freshness(repo({}), "# 메모\n작성자 없음\n", self.TODAY)
        self.assertIsNone(f["written"])
        self.assertIn("작성일을 못 셌다", rules.freshness_line(f))  # 빈 줄이면 '신선함'으로 읽힌다

    def test_bad_date_is_not_a_crash(self):
        f = rules.handoff_freshness(repo({}), "# Session Handoff (작성: 2026-13-45)\n", self.TODAY)
        self.assertIsNone(f["written"])
        line = rules.freshness_line(f)
        self.assertIn("첫 줄 날짜(2026-13-45)가 잘못됐다", line)  # 못 센 까닭을 사실대로
        self.assertNotIn("작성일이 없고", line)  # "잘못됐다"와 "없다"가 겹쳐 모순되지 않는다

    def test_header_date_but_git_failed_says_count_unknown(self):
        with mock.patch.object(rules, "_git", return_value=None):  # 시한 초과·git 오류
            line = rules.freshness_line(rules.handoff_freshness(repo({}), "# Session Handoff (작성: 2026-11-08)\n", self.TODAY))
        self.assertIn("그 뒤 커밋 수를 못 셌다", line)
        untracked = repo({"HANDOFF.md": "x", "a": "a"})  # 다른 파일 커밋은 있고 인계서만 미추적(커밋 0개면 log가 실패해 앞 문구)
        git(untracked, "init", "-q"); git(untracked, "add", "a"); git(untracked, "commit", "-qm", "a")
        line = rules.freshness_line(rules.handoff_freshness(untracked, "# Session Handoff (작성: 2026-11-08)\n", self.TODAY))
        self.assertIn("커밋된 적 없어 그 뒤 커밋 수를 못 셌다", line)

    def test_date_label_variants(self):
        for line in ("# Session Handoff (작성일: 2026-10-01)", "# Handoff — 2026-10-01 작성", "# Handoff (Written: 2026-10-01)",
                     "# Session Handoff\n> 작성 2026-10-01"):
            self.assertEqual(rules.header_date(line + "\n"), "2026-10-01", line)
        self.assertEqual(rules.header_date("# 10-07 결정 정리 (작성: 2026-10-08)\n"), "2026-10-08")
        self.assertIsNone(rules.header_date("# a\nb\nc\n작성: 2026-10-01\n"))  # 첫 3줄만 본다

    def test_signed_log_output_and_crash_fall_back(self):
        # log.showSignature=true면 서명 확인 줄이 stdout에 섞였다(리뷰 재현: 훅 exit 1, 인계서 주입 사라짐)
        many = 'Good "git" signature for t@example.com with ED25519 key SHA256:x\nabc123 2026-10-01'
        with mock.patch.object(rules, "_git", return_value=many):
            f = rules.handoff_freshness(repo({}), "# Session Handoff (작성: 2026-10-01)\n", self.TODAY)
        self.assertEqual((f["written"], f["commits_after"]), ("2026-10-01", None))
        with mock.patch.object(rules, "handoff_freshness", side_effect=RuntimeError("x")):
            f = rules.safe_freshness(repo({}), "x")
        self.assertIn("신선도 계산 실패(RuntimeError)", rules.freshness_line(f))

    def test_git_budget_exhausted_returns_none(self):
        self.assertIsNone(rules._git(repo({}), 0, "status"))  # 시한이 이미 지났으면 git을 부르지 않는다

    def test_expired_hook_deadline_calls_no_git_and_says_so(self):
        # 훅 전체 시한이 이미 지났으면 git을 하나도 부르지 않고 못 셌다고 적는다 — 작성일·나이는 첫 줄로 센다
        with mock.patch.object(rules.subprocess, "run") as run:
            f = rules.handoff_freshness(repo({}), "# Session Handoff (작성: 2026-10-01)\n", self.TODAY, deadline=0)
            g = rules.safe_freshness(repo({}), "# 메모\n", deadline=0)
        run.assert_not_called()
        self.assertEqual((f["written"], f["days"], f["commits_after"]), ("2026-10-01", 38, None))
        self.assertIn("그 뒤 커밋 수를 못 셌다(훅 시한)", rules.freshness_line(f))
        self.assertIn("첫 줄에 작성일이 없고 그 뒤 커밋 수를 못 셌다(훅 시한)", rules.freshness_line(g))

    def test_signature_config_does_not_break_real_git(self):
        r = repo({"HANDOFF.md": "# Session Handoff\n"})
        git(r, "init", "-q"); git(r, "add", "HANDOFF.md"); git(r, "commit", "-qm", "h")
        git(r, "config", "log.showSignature", "true")  # 서명 없는 커밋이어도 설정이 켜져 있는 저장소
        f = rules.handoff_freshness(r, "# Session Handoff\n")
        self.assertEqual((f["source"], f["commits_after"]), ("commit", 0))

    def test_shallow_clone_does_not_claim_no_commits(self):
        src = repo({"HANDOFF.md": "# Session Handoff\n"})
        git(src, "init", "-q"); git(src, "add", "HANDOFF.md"); git(src, "commit", "-qm", "h")
        for name in ("a", "b"):
            with open(os.path.join(src, name), "w") as fh: fh.write(name)
            git(src, "add", name); git(src, "commit", "-qm", name)
        dst = os.path.join(repo({}), "clone")
        git(os.path.dirname(dst), "clone", "-q", "--depth", "1", "file://" + src, dst)
        f = rules.handoff_freshness(dst, "# Session Handoff\n")
        self.assertIsNone(f["commits_after"])  # 경계 커밋이 HANDOFF.md를 만든 것처럼 보여 0으로 나왔었다
        line = rules.freshness_line(f)
        self.assertIn("얕은 복제", line)
        self.assertNotIn("그 뒤 커밋은 없다", line)

    def test_subfolder_project_counts_only_its_folder_and_untracked_says_so(self):
        r = repo({"app/HANDOFF.md": "# Session Handoff\n", "other/x": "x"})
        git(r, "init", "-q"); git(r, "add", "app"); git(r, "commit", "-qm", "h")
        git(r, "add", "other"); git(r, "commit", "-qm", "other")  # 다른 폴더 커밋 — 이 프로젝트 인계서와 무관
        f = rules.handoff_freshness(os.path.join(r, "app"), "# Session Handoff\n")
        self.assertEqual(f["commits_after"], 0)
        untracked = repo({"HANDOFF.md": "# Session Handoff\n"}); git(untracked, "init", "-q")
        f = rules.handoff_freshness(untracked, "# Session Handoff\n")
        self.assertIn("커밋된 적 없다", rules.freshness_line(f))

    def test_future_date_flags_without_stale_warning(self):
        line = rules.freshness_line(rules.handoff_freshness(repo({}), "# Session Handoff (작성: 2026-12-01)\n", self.TODAY))
        self.assertIn("23일 뒤 — 날짜 확인 필요", line)
        self.assertNotIn("지났다", line)

    def test_commits_after_handoff_and_dirty(self):
        r = repo({"HANDOFF.md": "# Session Handoff\n"})
        git(r, "init", "-q"); git(r, "add", "HANDOFF.md"); git(r, "commit", "-qm", "handoff")
        for name in ("a", "b"):
            with open(os.path.join(r, name), "w") as f: f.write(name)
            git(r, "add", name); git(r, "commit", "-qm", name)
        f = rules.handoff_freshness(r, "# Session Handoff\n")
        self.assertEqual((f["source"], f["days"], f["commits_after"], f["dirty"]), ("commit", 0, 2, False))  # 작성일 없으면 커밋일
        self.assertIn("그 뒤 커밋 2개는 인계서에 없다 — `git log --oneline -2 -- .`", rules.freshness_line(f))
        with open(os.path.join(r, "HANDOFF.md"), "a") as fh: fh.write("수정 중\n")
        f = rules.handoff_freshness(r, "# Session Handoff\n")
        self.assertEqual((f["dirty"], f["commits_after"]), (True, None))  # 쓰는 중이면 커밋 수는 의미가 없다
        self.assertIn("커밋 안 한 수정 중", rules.freshness_line(f))

    def test_hook_puts_freshness_under_head_and_logs_it(self):
        r = repo({"HANDOFF.md": "# Session Handoff (작성: 2020-01-01)\n다음 행동\n"})
        log = os.path.join(r, "runs.jsonl")
        p = subprocess.run([sys.executable, HOOK], input=json.dumps({"prompt": "이어서"}), capture_output=True, text=True,
                           env=dict(os.environ, CLAUDE_PROJECT_DIR=r, BATON_LOG=log))
        ctx = json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]
        head, fresh, blank = ctx.splitlines()[:3]
        self.assertIn("가설로 읽고", head)
        self.assertNotIn("그대로 이어서 진행한다", head)
        self.assertIn("파일을 다시 열 필요 없다", head)  # 재독 0/5를 만든 문장은 그대로(루프 2)
        self.assertIn("2020-01-01(", fresh)
        self.assertIn("지났다", fresh)
        self.assertEqual(blank, "")
        self.assertGreater(read_log(log)[0]["acted"]["handoff_days"], 2000)

    def test_explain_shows_freshness(self):
        r = repo({"HANDOFF.md": "# Session Handoff (작성: 2020-01-01)\n"})
        self.assertIn("2020-01-01(", rules.explain(r, "이어서"))
        # 넣지 않을 때는 신선도를 세지 않는다(git을 부르지 않는다) — 기계 프롬프트·끄기·트리거 없음
        with mock.patch.object(rules, "safe_freshness", side_effect=AssertionError("넣지 않는데 셌다")):
            for p in ('<agent-message from="x">이어서', "세이브 고쳐줘"):
                self.assertNotIn("2020-01-01(", rules.explain(r, p), p)
            with mock.patch.dict(os.environ, {"BATON_HANDOFF_INJECT": "off"}):
                self.assertNotIn("2020-01-01(", rules.explain(r, "이어서"))


class ExplainIndexTest(unittest.TestCase):
    def test_explain_shows_index_size_and_why_not(self):
        r = repo({"CONCEPTS.md": MAP})
        out = rules.explain(r, "카메라 어디서 돌려?")
        self.assertRegex(out, r"개념 색인 넣는다 — [0-9,]+자·개념 2개")
        self.assertIn("넣지 않는다 — 다른 세션", rules.explain(r, '<agent-message from="a">x'))
        with mock.patch.dict(os.environ, {"BATON_CONCEPT_INDEX": "off"}):
            self.assertIn("개념 색인 넣지 않는다 — BATON_CONCEPT_INDEX=off", rules.explain(r, "x"))
        self.assertIn("개념 색인 넣지 않는다 — 개념 지도(CONCEPTS.md)가 없다", rules.explain(repo({}), "x"))
        self.assertIn("넣을 개념이 없다", rules.explain(repo({"CONCEPTS.md": "# 빈 지도\n"}), "x"))


class ObserveLogTest(unittest.TestCase):
    def run_hook(self, root, prompt, **env):
        log = os.path.join(root, "runs.jsonl")
        e = dict(os.environ, CLAUDE_PROJECT_DIR=root, BATON_LOG=log, XDG_CACHE_HOME=root, **env)  # 세션별 주입 기억도 실제 캐시에 안 쓴다
        r = subprocess.run([sys.executable, HOOK], input=json.dumps({"prompt": prompt, "session_id": "s1"}),
                           capture_output=True, text=True, env=e)
        return r, read_log(log)

    def test_logs_decision_and_what_was_acted(self):
        r, recs = self.run_hook(repo({"HANDOFF.md": "a\nb\n", "CONCEPTS.md": MAP}), "이어서 세이브 고쳐줘")
        self.assertIn("[baton] 아래는", r.stdout)
        self.assertEqual(len(recs), 1)
        rec = recs[0]
        self.assertEqual(rec["session_id"], "s1")
        self.assertEqual(rec["decision"]["handoff"]["state"], "MATCHED")
        self.assertEqual(rec["decision"]["concepts"]["candidates"], [{"num": "1", "name": "세이브"}])
        self.assertGreater(rec["acted"].pop("concept_index"), 0)  # 개념 색인은 기본 켬 — 세션 첫 프롬프트에 넣은 글자 수
        self.assertEqual(rec["acted"], {"handoff_lines": 2, "handoff_total": 2, "handoff_days": None,  # 작성일·git 없음 — 못 셈
                                        "handoff_commits_after": None, "handoff_skip": None,
                                        "concept": None, "concept_index_skip": None})  # 개념 절 주입은 기본 끔 — 관찰만
        self.assertNotIn("이어서 세이브 고쳐줘", json.dumps(rec, ensure_ascii=False))  # 프롬프트 원문은 남기지 않는다(맞은 규칙 어휘만)

    def test_log_is_private_and_surrogate_prompt_still_logged(self):
        root = repo({})
        r, recs = self.run_hook(root, "이어서 \ud800")
        self.assertEqual(len(recs), 1)
        self.assertEqual(oct(os.stat(os.path.join(root, "runs.jsonl")).st_mode & 0o777), "0o600")

    def test_observe_off_and_log_failure_do_not_change_output(self):
        root = repo({"HANDOFF.md": "a\n"})
        r1, recs = self.run_hook(root, "이어서", BATON_OBSERVE="off")
        self.assertEqual(recs, [])
        r2 = subprocess.run([sys.executable, HOOK], input=json.dumps({"prompt": "이어서"}), capture_output=True, text=True,
                            env=dict(os.environ, CLAUDE_PROJECT_DIR=root, BATON_LOG="/dev/null/x/runs.jsonl"))
        self.assertEqual((r2.returncode, r2.stdout), (0, r1.stdout))


if __name__ == "__main__":
    unittest.main()
