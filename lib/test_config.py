#!/usr/bin/env python3
"""설정 파일: 환경변수 > 저장소 절 > 전역 절 > 기본값, 깨진 파일은 없는 것으로, 쓰기는 600·700·바꿔치기. 훅이 설정을 실제로 읽는다."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.join(os.path.dirname(HERE), "hooks")
sys.path.insert(0, HERE)
import config

KEYS = ("BATON_HANDOFF_NUDGE_FILES", "BATON_SPLIT_RATIOS", "BATON_HANDOFF_TRIGGERS_EXTRA", "BATON_OBSERVE", "BATON_LOG",
        "BATON_HANDOFF_NUDGE", "BATON_HANDOFF_CHECK", "BATON_SPLIT_NOTICE", "BATON_HANDOFF_INJECT", "CLAUDE_PROJECT_DIR")


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.xdg = os.path.join(self.tmp.name, "xdg")
        self.repo = os.path.join(self.tmp.name, "저장소")
        os.makedirs(self.repo)
        env = {k: v for k, v in os.environ.items() if k not in KEYS}
        env["XDG_CONFIG_HOME"] = self.xdg
        p = mock.patch.dict(os.environ, env, clear=True)
        p.start(); self.addCleanup(p.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, data):
        os.makedirs(os.path.dirname(config.path()), exist_ok=True)
        with open(config.path(), "w", encoding="utf-8") as f:
            f.write(data if isinstance(data, str) else json.dumps(data, ensure_ascii=False))

    def test_precedence_env_repo_global_default(self):
        self.assertEqual(config.get("BATON_HANDOFF_NUDGE_FILES", self.repo, "3"), "3")
        self.write({"global": {"BATON_HANDOFF_NUDGE_FILES": "4"}})
        self.assertEqual(config.get("BATON_HANDOFF_NUDGE_FILES", self.repo, "3"), "4")
        self.write({"global": {"BATON_HANDOFF_NUDGE_FILES": "4"}, "repos": {config.repo_key(self.repo): {"BATON_HANDOFF_NUDGE_FILES": 5}}})
        self.assertEqual(config.get("BATON_HANDOFF_NUDGE_FILES", self.repo, "3"), "5")
        self.assertEqual(config.get("BATON_HANDOFF_NUDGE_FILES", None, "3"), "4")  # 저장소를 모르면 전역
        os.environ["BATON_HANDOFF_NUDGE_FILES"] = ""
        self.assertEqual(config.get("BATON_HANDOFF_NUDGE_FILES", self.repo, "3"), "")  # 빈 환경변수도 이긴다(기존 동작 그대로)

    def test_repo_key_normalizes_nfd_and_symlink(self):
        import unicodedata
        link = os.path.join(self.tmp.name, "link")
        os.symlink(self.repo, link)
        self.write({"repos": {config.repo_key(self.repo): {"BATON_SPLIT_RATIOS": "4"}}})
        self.assertEqual(config.get("BATON_SPLIT_RATIOS", link), "4")
        self.assertEqual(config.get("BATON_SPLIT_RATIOS", unicodedata.normalize("NFD", self.repo)), "4")

    def test_bom_stripped_from_terms(self):
        self.write({"global": {"private_terms": ["\ufeff홍길동", "\ufeff"]}})
        self.assertEqual(config.terms("private_terms"), ["홍길동"])

    def test_lists_repo_adds_to_global_and_env_replaces(self):
        self.write({"global": {"private_terms": ["Kim", 3, " ", "kim2"]},
                    "repos": {config.repo_key(self.repo): {"private_terms": ["Lee", "Kim"]}}})
        self.assertEqual(config.terms("private_terms", self.repo), ["Kim", "kim2", "Lee"])
        self.assertEqual(config.terms("private_terms"), ["Kim", "kim2"])
        os.environ["private_terms"] = "x"  # BATON_ 이 아닌 이름은 환경변수로 덮지 않는다
        self.assertEqual(config.terms("private_terms"), ["Kim", "kim2"])
        os.environ["BATON_HANDOFF_TRIGGERS_EXTRA"] = "계속, 지난번 ,"
        self.assertEqual(config.terms("BATON_HANDOFF_TRIGGERS_EXTRA", self.repo), ["계속", "지난번"])

    def test_missing_malformed_and_wrong_types_act_as_absent(self):
        for bad in ("{", "[]", '"x"', json.dumps({"global": [], "repos": "x"}),
                    json.dumps({"global": {"BATON_SPLIT_RATIOS": True, "private_terms": "Kim"},
                                "repos": {config.repo_key(self.repo): ["x"]}})):
            self.write(bad)
            self.assertEqual(config.get("BATON_SPLIT_RATIOS", self.repo, "2,3"), "2,3", bad)
            self.assertEqual(config.terms("private_terms", self.repo), [], bad)
        os.remove(config.path())
        self.assertIsNone(config.load())

    def test_deep_nesting_and_oversize_act_as_absent(self):
        self.write("[" * 200000)  # json이 RecursionError를 낸다
        self.assertIsNone(config.load())
        self.write(json.dumps({"global": {"BATON_SPLIT_RATIOS": "4"}, "pad": "x" * config.MAX_BYTES}))
        self.assertIsNone(config.load())
        self.assertEqual(config.get("BATON_SPLIT_RATIOS", None, "2,3"), "2,3")

    def test_load_parsed_once_until_file_changes(self):
        self.write({"global": {"BATON_SPLIT_RATIOS": "4"}})
        with mock.patch("json.load", wraps=json.load) as jl:
            for _ in range(5):
                config.get("BATON_SPLIT_RATIOS", self.repo)
            self.assertEqual(jl.call_count, 1)
            config.update(None, {"BATON_SPLIT_RATIOS": "5"})
            self.assertEqual(config.get("BATON_SPLIT_RATIOS"), "5")

    def test_repo_key_is_git_toplevel(self):
        subprocess.run(["git", "-C", self.repo, "init", "-q"], check=True)
        app = os.path.join(self.repo, "app", "src"); os.makedirs(app)
        self.assertEqual(config.repo_key(app), config.repo_key(self.repo))
        config.update(self.repo, add={"private_terms": ["홍길동"]})
        self.assertEqual(config.terms("private_terms", app), ["홍길동"])
        plain = os.path.join(self.tmp.name, "plain"); os.makedirs(plain)  # git이 아니면 경로 그대로
        self.assertEqual(config.repo_key(plain), config.repo_key(os.path.realpath(plain)))

    def test_symlinked_config_written_through(self):
        real = os.path.join(self.tmp.name, "dotfiles", "baton.json")
        os.makedirs(os.path.dirname(real))
        with open(real, "w", encoding="utf-8") as f:
            f.write("{}")
        os.makedirs(os.path.dirname(config.path()))
        os.symlink(real, config.path())
        config.update(None, {"BATON_SPLIT_RATIOS": "4"})
        self.assertTrue(os.path.islink(config.path()))
        with open(real, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["global"], {"BATON_SPLIT_RATIOS": "4"})

    def test_unreadable_file_acts_as_absent(self):
        self.write({"global": {"BATON_SPLIT_RATIOS": "4"}})
        with mock.patch("builtins.open", side_effect=PermissionError("권한")):
            self.assertEqual(config.get("BATON_SPLIT_RATIOS", None, "2,3"), "2,3")

    def test_home_unset(self):
        del os.environ["XDG_CONFIG_HOME"]
        os.environ.pop("HOME", None)
        self.assertIsNone(config.path())
        self.assertEqual(config.get("BATON_SPLIT_RATIOS", self.repo, "2,3"), "2,3")
        with self.assertRaises(ValueError):
            config.update(None, {"BATON_SPLIT_RATIOS": "4"})

    def test_write_permissions_and_preserves_other_repos(self):
        other = config.repo_key(os.path.join(self.tmp.name, "다른"))
        p = config.update(other, {"BATON_SPLIT_RATIOS": "4,5"})
        self.assertEqual(oct(os.stat(p).st_mode & 0o777), "0o600")
        self.assertEqual(oct(os.stat(os.path.dirname(p)).st_mode & 0o777), "0o700")
        config.update(self.repo, {"BATON_HANDOFF_NUDGE_FILES": "4"}, add={"private_terms": ["Kim"]})
        config.update(self.repo, add={"private_terms": ["Kim", "Lee"]})
        config.update(None, {"BATON_OBSERVE": "off"})
        data = config.load()
        self.assertEqual(data["repos"][other], {"BATON_SPLIT_RATIOS": "4,5"})
        self.assertEqual(data["repos"][config.repo_key(self.repo)], {"BATON_HANDOFF_NUDGE_FILES": "4", "private_terms": ["Kim", "Lee"]})
        self.assertEqual(data["global"], {"BATON_OBSERVE": "off"})
        self.assertEqual(data["version"], 1)
        self.assertEqual([f for f in os.listdir(os.path.dirname(p)) if f != "config.json"], [])  # 임시 파일이 남지 않는다
        config.update(self.repo, unset=["BATON_HANDOFF_NUDGE_FILES", "private_terms"])
        self.assertNotIn(config.repo_key(self.repo), config.load()["repos"])  # 빈 절은 지운다

    def test_malformed_file_not_overwritten(self):
        self.write("{깨진")
        with self.assertRaises(ValueError):
            config.update(self.repo, {"BATON_SPLIT_RATIOS": "4"})
        with open(config.path(), encoding="utf-8") as f:
            self.assertEqual(f.read(), "{깨진")

    def test_failed_write_leaves_old_file(self):
        config.update(None, {"BATON_SPLIT_RATIOS": "4"})
        with mock.patch("json.dump", side_effect=RuntimeError("디스크")):
            with self.assertRaises(RuntimeError):
                config.update(None, {"BATON_SPLIT_RATIOS": "9"})
        self.assertEqual(config.load()["global"], {"BATON_SPLIT_RATIOS": "4"})
        self.assertEqual(os.listdir(os.path.dirname(config.path())), ["config.json"])

    def test_global_only_keys_ignore_repo_section(self):
        self.write({"repos": {config.repo_key(self.repo): {"BATON_OBSERVE": "off"}}})
        self.assertEqual(config.get("BATON_OBSERVE", self.repo), "")

    def test_status_does_not_echo_private_terms(self):
        config.update(self.repo, {"BATON_SPLIT_RATIOS": "4"}, add={"private_terms": ["비밀이름"]})
        out = "\n".join(config.status(self.repo))
        self.assertIn("BATON_SPLIT_RATIOS=4", out)
        self.assertIn("private_terms: 1개", out)
        self.assertNotIn("비밀이름", out)


class HooksReadConfigTest(unittest.TestCase):
    """훅이 환경변수 대신 설정 파일을 읽고, 환경변수가 여전히 이기고, 깨진 설정에도 조용히 끝나는지."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.tmp.name)
        self.repo = os.path.join(self.root, "repo")
        os.makedirs(self.repo)
        self.xdg = os.path.join(self.root, "xdg")
        self.transcript = os.path.join(self.root, "s.jsonl")
        edits = [{"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Edit", "input": {"file_path": f"/r/{n}.py"}}],
                                                   "usage": {"input_tokens": t}, "model": "m"}} for n, t in (("a", 100), ("b", 450))]
        with open(self.transcript, "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(x) for x in [{"type": "user", "message": {"content": "시작"}}] + edits) + "\n")

    def tearDown(self):
        self.tmp.cleanup()

    def config(self, section):
        os.makedirs(os.path.join(self.xdg, "baton"), exist_ok=True)
        with open(os.path.join(self.xdg, "baton", "config.json"), "w", encoding="utf-8") as f:
            f.write(section if isinstance(section, str) else json.dumps({"repos": {config.repo_key(self.repo): section}}))

    def hook(self, name, payload, **env):
        e = {k: v for k, v in os.environ.items() if k not in KEYS}
        e.update(XDG_CONFIG_HOME=self.xdg, XDG_CACHE_HOME=os.path.join(self.root, "cache"),
                 BATON_LOG=os.path.join(self.root, "runs.jsonl"), CLAUDE_PROJECT_DIR=self.repo, **env)
        r = subprocess.run([sys.executable, os.path.join(HOOKS, name)], input=json.dumps(payload), text=True,
                           capture_output=True, env=e)
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        return json.loads(r.stdout) if r.stdout.strip() else None

    def stop(self, name, sid, **env):
        return self.hook(name, {"hook_event_name": "Stop", "transcript_path": self.transcript, "session_id": sid,
                                "cwd": self.repo}, **env)

    def test_nudge_threshold_from_repo_section_and_env_wins(self):
        self.assertIsNone(self.stop("handoff-check.py", "s1"))  # 기본 3 — 2개로는 안 뜬다
        self.config({"BATON_HANDOFF_NUDGE_FILES": "2"})
        self.assertIsNotNone(self.stop("handoff-check.py", "s2"))
        self.assertIsNone(self.stop("handoff-check.py", "s3", BATON_HANDOFF_NUDGE_FILES="5"))

    def test_split_ratio_and_switch_from_config(self):
        self.config({"BATON_SPLIT_RATIOS": "5"})
        self.assertIsNone(self.stop("split-notice.py", "s1"))  # 4.5배 < 5
        self.config({"BATON_SPLIT_RATIOS": "4"})
        self.assertIn("4배에서", self.stop("split-notice.py", "s2")["systemMessage"])
        self.config({"BATON_SPLIT_NOTICE": "off"})
        self.assertIsNone(self.stop("split-notice.py", "s3"))

    def test_private_terms_block_without_echo(self):
        self.config({"private_terms": ["홍길동"]})
        p = os.path.join(self.repo, "HANDOFF.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write("# Handoff\n- 홍길동 님 요청\n")
        out = self.hook("handoff-check.py", {"hook_event_name": "PostToolUse", "tool_input": {"file_path": p}, "cwd": self.repo})
        self.assertIn("개인 자료 목록 단어 1개", out["reason"])
        self.assertNotIn("홍길동", out["reason"])

    def test_trigger_extra_injects_handoff(self):
        with open(os.path.join(self.repo, "HANDOFF.md"), "w", encoding="utf-8") as f:
            f.write("# 인계\n")
        self.assertIsNone(self.hook("handoff-inject.py", {"prompt": "지난번 거 계속"}))
        self.config({"BATON_HANDOFF_TRIGGERS_EXTRA": ["지난번"]})
        self.assertIn("[baton] 아래는", self.hook("handoff-inject.py", {"prompt": "지난번 거 계속"})["hookSpecificOutput"]["additionalContext"])

    def test_broken_config_falls_back_to_defaults(self):
        p = os.path.join(self.repo, "HANDOFF.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write("# Handoff\n- 경로 /Users/someone/x\n")
        off = {"global": {"BATON_HANDOFF_INJECT": "off", "BATON_SPLIT_NOTICE": "off", "BATON_HANDOFF_CHECK": "off"}}
        for i, bad in enumerate(["{깨진", "[" * 200000, json.dumps(dict(off, pad="x" * (1024 * 1024)))]):
            self.config(bad)  # 깨진 JSON · 깊은 중첩(RecursionError) · 1MB 넘는 파일(안의 off는 무시돼야 한다)
            self.assertIn("[baton] 아래는", self.hook("handoff-inject.py", {"prompt": "이어서"})["hookSpecificOutput"]["additionalContext"])
            self.assertIn("3배에서", self.stop("split-notice.py", f"b{i}")["systemMessage"])  # 기본 문턱 2,3 그대로
            out = self.hook("handoff-check.py", {"hook_event_name": "PostToolUse", "tool_input": {"file_path": p}, "cwd": self.repo})
            self.assertIn("홈 절대경로", out["reason"])

    def test_tilde_log_path_lands_under_home_not_cwd(self):
        home = os.path.join(self.root, "home"); os.makedirs(home)
        self.config(json.dumps({"global": {"BATON_LOG": "~/logs/runs.jsonl"}}))  # 손으로 고친 값도 "~"를 펼친다
        e = {k: v for k, v in os.environ.items() if k not in KEYS}
        e.update(HOME=home, XDG_CONFIG_HOME=self.xdg, CLAUDE_PROJECT_DIR=self.repo)
        subprocess.run([sys.executable, os.path.join(HOOKS, "handoff-inject.py")], input=json.dumps({"prompt": "버그"}),
                       text=True, capture_output=True, env=e, cwd=self.repo, check=True)
        self.assertTrue(os.path.isfile(os.path.join(home, "logs", "runs.jsonl")))
        self.assertFalse(os.path.exists(os.path.join(self.repo, "~")))

    def test_observe_log_has_no_private_term_or_raw_prompt(self):
        self.config({"private_terms": ["홍길동"], "BATON_HANDOFF_TRIGGERS_EXTRA": ["지난번"]})
        p = os.path.join(self.repo, "HANDOFF.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write("# Handoff\n- 홍길동 님 요청\n")
        prompt = "지난번 거 홍길동 님 일 마저 하자"
        self.assertIsNotNone(self.hook("handoff-inject.py", {"prompt": prompt, "session_id": "s1"}))
        self.assertIsNotNone(self.hook("handoff-check.py", {"hook_event_name": "PostToolUse", "tool_input": {"file_path": p},
                                                            "cwd": self.repo, "session_id": "s1"}))
        with open(os.path.join(self.root, "runs.jsonl"), encoding="utf-8") as f:
            log = f.read()
        self.assertEqual(len(log.splitlines()), 2)
        self.assertNotIn("홍길동", log)
        self.assertNotIn(prompt, log)


if __name__ == "__main__":
    unittest.main()
