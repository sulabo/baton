#!/usr/bin/env python3
"""북극성 길 단계 3 훅: HANDOFF.md를 쓰면 검사해 모델에게 돌려주고, 인계서 없이 파일을 여럿 고치면 세션에 한 번
모델에게 인계서를 쓰게 한다(BATON_HANDOFF_AUTO, 기본 켬) — 끄면 예전처럼 사용자에게 제안만 한다."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "handoff-check.py")
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
from test_handoff_check import GOOD, GOOD_EN


_CFG = tempfile.TemporaryDirectory()  # 실제 설정 파일(~/.config/baton/config.json)을 읽지 않는다 — 훅 자식 프로세스도 이 환경을 물려받는다
_CFG_ENV = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": _CFG.name, "BATON_LANG": "ko"})  # 한국어 단언은 ko로 고정


def setUpModule():
    _CFG_ENV.start()


def tearDownModule():
    _CFG_ENV.stop(); _CFG.cleanup()


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
        for k in ("BATON_HANDOFF_CHECK", "BATON_HANDOFF_NUDGE", "BATON_HANDOFF_NUDGE_FILES", "BATON_HANDOFF_AUTO"):
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

    def test_missing_marks_warn_without_blocking(self):
        text = GOOD.replace("## 확인된 사실과 결정\n- 없음\n", "## 확인된 사실과 결정\n- 표시 없는 주장\n")
        out = self.post(self.handoff(text))
        self.assertNotIn("decision", out)
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        self.assertIn("[V]·[?] 표시 없음", ctx)
        with open(self.log, encoding="utf-8") as f:
            rec = json.loads(f.readline())
        self.assertEqual((rec["problems"], rec["warnings"]), (0, 1))

    def test_warning_crash_keeps_blocking_problems(self):
        # 리뷰(11-21): warnings()에서 예외가 나면 막아야 할 문제까지 함께 사라졌다. 훅을 프로세스 안에서 돌려 예외를 넣는다
        import contextlib, importlib.util, io
        spec = importlib.util.spec_from_file_location("handoff_check_hook", HOOK)
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        path = self.handoff("# Session Handoff\n")
        buf = io.StringIO()
        env = {"XDG_CACHE_HOME": os.path.join(self.root, "cache"), "BATON_LOG": self.log}
        with mock.patch.dict(os.environ, env), mock.patch.object(hook.handoff_check, "warnings", side_effect=ValueError), \
                mock.patch.object(hook.handoff_check, "read", wraps=hook.handoff_check.read) as rd, \
                contextlib.redirect_stdout(buf):
            hook.on_edit({"tool_input": {"file_path": path}, "session_id": "s1"})
        out = json.loads(buf.getvalue())
        self.assertEqual(out["decision"], "block")
        self.assertIn("필수 절 없음", out["reason"])
        self.assertEqual(rd.call_count, 1)  # 파일은 한 번만 읽는다

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

    # Stop — 제안(BATON_HANDOFF_AUTO=off). 자동 쓰기는 아래 AutoWrite 테스트
    def write(self, lines):
        with open(self.transcript, "w", encoding="utf-8") as f:
            f.write("\n".join([json.dumps({"type": "user", "message": {"content": "시작"}})] + lines + ["{깨진 줄"]) + "\n")

    def stop(self, sid="s1", extra_env=None, **kw):
        env = dict({"BATON_HANDOFF_AUTO": "off"}, **(extra_env or {}))
        out = self.run_hook({"hook_event_name": "Stop", "transcript_path": self.transcript, "session_id": sid},
                            extra_env=env, **kw)
        return out["systemMessage"] if out else None

    def auto(self, sid="s1", extra_env=None, **payload):
        """자동 쓰기 켬(기본)의 Stop 출력 dict 또는 None."""
        return self.run_hook(dict({"hook_event_name": "Stop", "transcript_path": self.transcript, "session_id": sid,
                                   "cwd": "/r"}, **payload), extra_env=extra_env)

    def events(self):
        if not os.path.exists(self.log):
            return []
        with open(self.log, encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]

    def test_auto_write_blocks_once_with_reason_for_the_model(self):
        self.write([edit("/r/a.py"), edit("/r/b.py"), edit("/r/sub/c.py", "Write")])
        out = self.auto()
        self.assertEqual(set(out), {"decision", "reason"})  # Stop 훅 형식: decision "block" + reason(모델이 받는다)
        self.assertEqual(out["decision"], "block")
        reason = out["reason"]
        self.assertIn("파일 3개를 고쳤다: a.py, b.py, sub/c.py.", reason)  # cwd(/r) 기준 상대 경로
        self.assertIn("BATON_HANDOFF_AUTO=off", reason)
        self.assertIn("기억으로 새로 쓰지 말고 지금 HANDOFF.md에서 시작해 아직 참인 줄은 그대로 옮긴다.", reason)
        self.assertIn("마지막 커밋판에서 빠진 줄을 알려 준다.", reason)
        checker = reason.split('python3 "', 1)[1].split('"', 1)[0]
        self.assertTrue(os.path.isfile(checker), checker)  # 검사기 경로는 실제 플러그인 파일
        skill = reason.split("baton 인계서 스킬(", 1)[1].split("의 ", 1)[0]
        with open(skill, encoding="utf-8") as f:
            self.assertIn("## When the Stop hook asks", f.read())  # 요청이 가리키는 스킬 절이 실제로 있다
        self.assertEqual([(e["event"], e["files"]) for e in self.events()], [("handoff_auto", 3)])
        self.assertIsNone(self.auto())  # 세션에 한 번
        self.assertIsNone(self.stop())  # 자동 쓰기를 했으면 같은 세션에 제안도 없다
        self.assertEqual(self.auto(sid="s2")["decision"], "block")

    def test_auto_write_never_blocks_while_stop_hook_active(self):
        self.write([edit("/r/a.py"), edit("/r/b.py"), edit("/r/c.py")])
        self.assertIsNone(self.auto(stop_hook_active=True))
        self.assertEqual(self.events(), [])
        self.assertEqual(self.auto()["decision"], "block")  # 상태를 남기지 않았다 — 다음 턴 끝에 다시 본다
        self.assertIsNotNone(self.stop(sid="s2", raw=json.dumps({"hook_event_name": "Stop", "transcript_path": self.transcript,
                                                                  "session_id": "s2", "stop_hook_active": True})))  # 제안은 예전 그대로

    def test_auto_write_follows_threshold_resets_and_switches(self):
        self.write([edit("/r/a.py"), edit("/r/b.py")])
        self.assertIsNone(self.auto())
        self.write([edit("/r/a.py"), edit("/r/b.py"), edit("/r/c.py"), edit("/r/HANDOFF.md", "Write"), edit("/r/d.py")])
        self.assertIsNone(self.auto())  # 인계서를 쓴 뒤로는 1개
        self.write([edit("/r/a.py"), edit("/r/b.py"), edit("/r/c.py")])
        self.assertIsNone(self.auto(sid="s3", extra_env={"BATON_HANDOFF_NUDGE": "off"}))  # 끄면 둘 다 없다
        self.assertIsNone(self.auto(sid="s3", extra_env={"BATON_HANDOFF_NUDGE": "off", "BATON_HANDOFF_AUTO": "off"}))
        self.assertEqual(self.auto(sid="s4", extra_env={"BATON_HANDOFF_NUDGE_FILES": "4"}), None)
        self.assertIn("systemMessage", self.auto(sid="s5", extra_env={"BATON_HANDOFF_AUTO": "off"}))

    def test_auto_write_lists_at_most_ten_files(self):
        self.write([edit(f"/r/f{i:02}.py") for i in range(12)] + [edit("/elsewhere/x.py")])
        reason = self.auto()["reason"]
        self.assertIn("f08.py 외 3개.", reason)
        self.assertNotIn("f10.py", reason)
        reason = self.auto(sid="s2", extra_env={"BATON_LANG": "en"})["reason"]
        self.assertIn("/elsewhere/x.py, f00.py", reason)  # cwd 밖은 경로 그대로
        self.assertIn("f08.py, and 3 more.", reason)

    def test_codex_transcript_gets_neither(self):
        # Codex 기록(~/.codex/sessions)에는 "tool_use" 편집 줄이 없다 — 편집은 custom_tool_call apply_patch(11-23 실제 기록)
        patch = {"type": "response_item", "payload": {"type": "custom_tool_call", "name": "apply_patch",
                                                      "input": "*** Begin Patch\n*** Update File: /r/a.py\n*** End Patch"}}
        with open(self.transcript, "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(patch) for _ in range(5)) + "\n")
        self.assertIsNone(self.auto())
        self.assertIsNone(self.stop(sid="s2"))

    def test_english_messages(self):
        en = {"BATON_LANG": "en"}
        self.write([edit("/r/a.py"), edit("/r/b.py"), edit("/r/c.py")])
        reason = self.auto(extra_env=en)["reason"]
        self.assertTrue(reason.startswith("[baton] You edited 3 files in this session since the handoff (HANDOFF.md or "
                                          "HANDOFF_*.md) was last written: a.py, b.py, c.py. Write or update HANDOFF.md"), reason)
        self.assertIn("section 'When the Stop hook asks'", reason)
        self.assertIn("Skip the promotion review and do not commit.", reason)
        self.assertIn("Start from the current HANDOFF.md and carry forward every line that is still true; do not rewrite it "
                      "from memory.", reason)
        self.assertIn("it lists lines that were dropped since the last committed version.", reason)
        self.assertIn("Then end your turn with one line to the user saying the handoff was updated and that "
                      "BATON_HANDOFF_AUTO=off turns this off.", reason)
        msg = self.stop(sid="s2", extra_env=en)
        self.assertTrue(msg.startswith("[baton] You edited 3 files in this session, and the handoff"), msg)
        self.assertIn("once per session", msg)
        out = self.post(self.handoff("# Session Handoff (written: 2026-11-23)\n- path /Users/someone/x\n"), extra_env=en)
        self.assertTrue(out["reason"].startswith("[baton] The HANDOFF.md you just wrote has handoff-check problems. "
                                                 "Fix them and save again:\n- missing required sections: Goal and done criteria"),
                        out["reason"])
        self.assertIn("\n- line 2: looks like an absolute home path", out["reason"])
        self.assertNotIn("someone", out["reason"])
        text = GOOD_EN.replace("## Verified facts and decisions\n- None\n", "## Verified facts and decisions\n- no mark\n")
        ctx = self.post(self.handoff(text), extra_env=en)["hookSpecificOutput"]["additionalContext"]
        self.assertTrue(ctx.startswith("[baton] Handoff-check warnings for the HANDOFF.md you just wrote (not blocking):\n- warning: "), ctx)
        self.assertIsNone(self.post(self.handoff(GOOD_EN), extra_env=en))  # 영어 템플릿은 조용히 통과
        self.assertIsNone(self.post(self.handoff(GOOD_EN)))  # 메시지가 한국어여도 영어 파일을 읽는다

    def test_dropped_lines_warned_against_last_commit(self):
        sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
        from test_handoff_check import DropCheckTest, git_repo
        p = self.handoff(DropCheckTest.OLD)
        self.assertIsNone(self.post(p))  # git 저장소가 아니면 비교할 판이 없다 — 조용하다
        g = git_repo(self.root); g("add", "HANDOFF.md"); g("commit", "-qm", "h")
        self.assertIsNone(self.post(p))  # 커밋판과 같다
        self.handoff(GOOD)
        ctx = self.post(p)["hookSpecificOutput"]["additionalContext"]
        self.assertTrue(ctx.startswith("[baton] 방금 쓴 HANDOFF.md 검사 경고(막지 않음):\n- 경고: 결정·제약으로 보이는 줄 1개"), ctx)
        self.assertIn("\n- 경고: 마지막 커밋판에 있던 줄 2개가 새 인계서에 없다", ctx)
        self.assertIn("\n    - [실패한 접근법] rtk가 감싼 diff 출력을 믿기 — md5로 확인", ctx)
        en = self.post(p, extra_env={"BATON_LANG": "en"})["hookSpecificOutput"]["additionalContext"]
        self.assertIn("\n- warning: 2 line(s) from the last committed version are not in the new handoff", en)
        self.assertIn("\n    - [Failed approaches] rtk가 감싼 diff", en)
        self.handoff("# Session Handoff\n")  # 막는 문제가 있으면 빠진 줄 경고도 같은 reason에 붙는다
        out = self.post(p)
        self.assertEqual(out["decision"], "block")
        self.assertIn("결정·제약으로 보이는 줄", out["reason"])

    def test_output_is_capped(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("handoff_check_hook", HOOK)
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        for lang in ("ko", "en"):
            t = hook.handoff_check.tr(lang)
            out = hook.capped("x" * 20000, t)
            self.assertEqual(len(out), hook.OUT_MAX)
            self.assertTrue(out.endswith("python3 lib/handoff_check.py HANDOFF.md" + ("" if lang == "ko" else " for all of it")), out[-80:])
            self.assertEqual(hook.capped("짧다", t), "짧다")

    def test_locale_fallback_reaches_the_hook(self):
        self.write([edit("/r/a.py"), edit("/r/b.py"), edit("/r/c.py")])
        env = mock.patch.dict(os.environ); env.start(); self.addCleanup(env.stop)
        for k in ("BATON_LANG", "LC_ALL", "LC_MESSAGES"):
            os.environ.pop(k, None)
        self.assertIn("파일 3개를 고쳤다", self.auto(extra_env={"LANG": "ko_KR.UTF-8"})["reason"])
        self.assertIn("You edited 3 files", self.auto(sid="s2", extra_env={"LANG": "C.UTF-8"})["reason"])

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

    def test_named_handoff_write_resets_count(self):
        self.write([edit("/r/a.py"), edit("/r/b.py"), edit("/r/c.py"), edit("/r/HANDOFF_track.md", "Write"), edit("/r/d.py")])
        self.assertIsNone(self.stop())
        self.write([edit("/r/HANDOFF_a.md"), edit("/r/handoff-b.md"), edit("/r/HANDOFF_c.md")])
        self.assertIsNone(self.stop(sid="s2"))  # 이름 붙은 인계서는 '다른 파일'로 세지 않는다
        self.write([edit("/r/a.py"), edit("/r/b.py"), edit("/r/HANDOFFS.md"), edit("/r/HANDOFF_.md")])
        self.assertIsNotNone(self.stop(sid="s3"))  # 구분자 뒤 이름이 없거나 구분자가 없으면 인계서가 아니다

    def test_named_handoff_logged_not_checked(self):
        p = os.path.join(self.root, "HANDOFF_track.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write("# 다른 형식\n" + "가" * 20000)
        out = self.run_hook({"hook_event_name": "PostToolUse", "tool_name": "Write", "session_id": "s1",
                             "tool_input": {"file_path": p}})
        self.assertIsNone(out)  # 주입되지 않는 파일이라 길이 등으로 막지 않는다
        with open(self.log, encoding="utf-8") as f:
            ev = [json.loads(l) for l in f if l.strip()]
        self.assertEqual([e["event"] for e in ev], ["handoff_write"])
        self.assertTrue(ev[0]["named"])

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
