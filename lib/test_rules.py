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


class ObserveLogTest(unittest.TestCase):
    def run_hook(self, root, prompt, **env):
        log = os.path.join(root, "runs.jsonl")
        e = dict(os.environ, CLAUDE_PROJECT_DIR=root, BATON_LOG=log, **env)
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
        self.assertEqual(rec["acted"], {"handoff_lines": 2, "handoff_total": 2, "concept": None})  # 개념 주입은 기본 끔 — 관찰만
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
