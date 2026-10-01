#!/usr/bin/env python3
"""북극성 길 단계 3 훅: HANDOFF.md를 쓰면 검사해 모델에게 돌려주고, 인계서 없이 파일을 여럿 고치면 세션에 한 번 제안한다."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "handoff-check.py")
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
from test_handoff_check import GOOD


def edit(path, name="Edit"):
    return json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": name, "input": {"file_path": path}}]}})


class HandoffCheckHookTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.transcript = os.path.join(self.root, "s.jsonl")
        self.log = os.path.join(self.root, "runs.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, payload, extra_env=None, raw=None):
        env = os.environ.copy()
        env["XDG_CACHE_HOME"] = os.path.join(self.root, "cache")  # 실제 캐시에 쓰지 않는다
        env["BATON_LOG"] = self.log
        for k in ("BATON_HANDOFF_CHECK", "BATON_HANDOFF_NUDGE", "BATON_HANDOFF_NUDGE_FILES"):
            env.pop(k, None)
        env.update(extra_env or {})
        r = subprocess.run([sys.executable, HOOK], input=raw if raw is not None else json.dumps(payload),
                           text=True, capture_output=True, env=env, check=False)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else None

    # PostToolUse — 검사
    def handoff(self, text):
        p = os.path.join(self.root, "HANDOFF.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def post(self, path, tool="Write", **kw):
        return self.run_hook({"hook_event_name": "PostToolUse", "tool_name": tool, "session_id": "s1",
                              "tool_input": {"file_path": path}, "cwd": self.root}, **kw)

    def test_good_handoff_silent(self):
        self.assertIsNone(self.post(self.handoff(GOOD)))

    def test_bad_handoff_returns_reason_to_model(self):
        out = self.post(self.handoff("# Session Handoff\n"))
        self.assertEqual(out["decision"], "block")
        self.assertIn("필수 절 없음", out["reason"])
        with open(self.log, encoding="utf-8") as f:
            self.assertEqual(json.loads(f.readline())["event"], "handoff_check")

    def test_relative_path_resolved_against_cwd(self):
        self.handoff("# Session Handoff\n")
        self.assertEqual(self.post("HANDOFF.md", tool="Edit")["decision"], "block")

    def test_other_format_handoff_not_forced_into_template(self):
        self.assertIsNone(self.post(self.handoff("# Handoff\n## Status\n- done\n")))
        out = self.post(self.handoff("# Handoff\n- path /Users/someone/x\n"))
        self.assertIn("홈 절대경로", out["reason"])  # 형식이 달라도 비밀값·경로는 본다

    def test_other_files_and_switch_ignored(self):
        other = os.path.join(self.root, "README.md")
        with open(other, "w", encoding="utf-8") as f:
            f.write("# 인계서 아님\n")
        self.assertIsNone(self.post(other))
        self.assertIsNone(self.post(self.handoff("# Session Handoff\n"), extra_env={"BATON_HANDOFF_CHECK": "off"}))

    # Stop — 제안
    def write(self, lines):
        with open(self.transcript, "w", encoding="utf-8") as f:
            f.write("\n".join([json.dumps({"type": "user", "message": {"content": "시작"}})] + lines + ["{깨진 줄"]) + "\n")

    def stop(self, sid="s1", **kw):
        out = self.run_hook({"hook_event_name": "Stop", "transcript_path": self.transcript, "session_id": sid}, **kw)
        return out["systemMessage"] if out else None

    def test_nudges_once_after_three_files(self):
        self.write([edit("/r/a.py"), edit("/r/b.py")])
        self.assertIsNone(self.stop())
        self.write([edit("/r/a.py"), edit("/r/b.py"), edit("/r/a.py"), edit("/r/c.py", "Write")])
        msg = self.stop()
        self.assertIn("파일 3개", msg)
        self.assertIsNone(self.stop())  # 세션에 한 번
        self.assertIsNotNone(self.stop(sid="s2"))

    def test_handoff_write_resets_count(self):
        self.write([edit("/r/a.py"), edit("/r/b.py"), edit("/r/c.py"), edit("/r/HANDOFF.md", "Write"), edit("/r/d.py")])
        self.assertIsNone(self.stop())

    def test_threshold_and_switch(self):
        self.write([edit("/r/a.py")])
        self.assertIsNotNone(self.stop(extra_env={"BATON_HANDOFF_NUDGE_FILES": "1"}))
        self.write([edit("/r/a.py"), edit("/r/b.py"), edit("/r/c.py")])
        self.assertIsNone(self.stop(sid="s3", extra_env={"BATON_HANDOFF_NUDGE": "off"}))

    def test_sidechain_and_duplicate_paths_not_counted(self):
        side = json.loads(edit("/r/x.py")); side["isSidechain"] = True
        self.write([edit("/r/a.py"), edit("/r/./a.py"), edit("/r/b.py"), json.dumps(side)])
        self.assertIsNone(self.stop())

    def test_non_dict_tool_input_fails_open(self):
        self.assertIsNone(self.run_hook({"hook_event_name": "PostToolUse", "tool_input": "x"}))

    def test_bad_input_fails_open(self):
        self.write([edit("/r/a.py"), edit("/r/b.py"), edit("/r/c.py")])
        self.assertIsNone(self.stop(sid="../x"))
        self.assertIsNone(self.run_hook(None, raw="not json"))
        self.assertIsNone(self.run_hook({"hook_event_name": "Stop", "transcript_path": "/없음", "session_id": "s1"}))


if __name__ == "__main__":
    unittest.main()
