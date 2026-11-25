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
# 한국어 단언은 ko로 고정. 캐시(세션당 한 번 상태 파일·관찰 로그)도 모듈 전체를 임시 폴더로 — 실제 ~/.cache/baton에 남기지 않는다
_CFG_ENV = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": _CFG.name, "BATON_LANG": "ko",
                                        "XDG_CACHE_HOME": os.path.join(_CFG.name, "cache"),
                                        "BATON_LOG": os.path.join(_CFG.name, "cache", "runs.jsonl")})


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
        env["CLAUDE_PROJECT_DIR"] = self.root  # Stop의 저장소 루트(HANDOFF.md 형식 확인) — 테스트를 돌리는 세션의 저장소를 보지 않게
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

    def passed(self, out):
        """깨끗한 저장의 통과 한 줄(11-25). 이 줄이 없으면 모델이 검사기를 손으로 다시 돌렸다."""
        self.assertEqual(set(out), {"hookSpecificOutput"})
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        return out["hookSpecificOutput"]["additionalContext"]

    def test_good_handoff_says_passed_in_one_line(self):
        n, m = len(GOOD.splitlines()), len(GOOD)
        self.assertEqual(self.passed(self.post(self.handoff(GOOD))), f"[baton] HANDOFF.md 검사 통과({n}줄·{m:,}자).")
        self.assertEqual(self.passed(self.post(self.handoff(GOOD), extra_env={"BATON_LANG": "en"})),
                         f"[baton] HANDOFF.md check passed ({n} lines, {m:,} chars).")
        self.assertIsNone(self.post(self.handoff(GOOD), extra_env={"BATON_HANDOFF_CHECK": "off"}))  # 끄면 통과 줄도 없다

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

    def test_check_that_could_not_run_is_not_called_passed(self):
        # 리뷰 11-25: 경고 규칙·빠진 줄 검사가 오류로 못 돌았는데 "검사 통과"라고 했다 — 대신 검사기를 직접 돌리라고 한다
        import contextlib, importlib.util, io
        spec = importlib.util.spec_from_file_location("handoff_check_hook", HOOK)
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        env = {"XDG_CACHE_HOME": os.path.join(self.root, "cache"), "BATON_LOG": self.log}
        warn = GOOD.replace("## 확인된 사실과 결정\n- 없음\n", "## 확인된 사실과 결정\n- 표시 없는 주장\n")
        for lang, note in (("ko", "[baton] HANDOFF.md 검사 일부를 돌리지 못했어요 — 검사기를 직접 돌려 주세요."),
                           ("en", "[baton] Part of the HANDOFF.md check couldn't run — run the checker yourself.")):
            for broken, text in (("warnings", GOOD), ("drop_warnings", GOOD), ("drop_warnings", warn)):
                with self.subTest(lang=lang, broken=broken, warned=text is warn):
                    buf = io.StringIO()
                    with mock.patch.dict(os.environ, dict(env, BATON_LANG=lang)), \
                            mock.patch.object(hook.handoff_check, broken, side_effect=ValueError), contextlib.redirect_stdout(buf):
                        hook.on_edit({"tool_input": {"file_path": self.handoff(text)}, "session_id": "s1"})
                    ctx = self.passed(json.loads(buf.getvalue()))
                    if text is GOOD:
                        self.assertEqual(ctx, note)
                    else:  # 경고는 그대로 내고, 못 돈 검사도 함께 알린다
                        self.assertTrue(ctx.endswith("\n" + note), ctx)
                        self.assertIn("[V]", ctx)
                    self.assertNotIn("검사 통과", ctx)
                    self.assertNotIn("check passed", ctx)

    def test_relative_path_resolved_against_cwd(self):
        self.handoff("# Session Handoff\n")
        self.assertEqual(self.post("HANDOFF.md", tool="Edit")["decision"], "block")

    def test_other_format_handoff_not_forced_into_template(self):
        self.assertIn("검사 통과", self.passed(self.post(self.handoff("# Handoff\n## Status\n- done\n"))))  # 막지도 경고하지도 않는다
        for text in ("# Project notes\n## Goal\n- ship\n## Related files\n- a.py\n## Next steps\n- review\n",
                     "# 메모\n## 목표\n- 출시\n## 관련 파일\n- a.py\n## Risks\n- 없음\n"):
            for lang in ("ko", "en"):  # 리뷰 11-23
                self.assertIn(("검사 통과", "check passed")[lang == "en"],
                              self.passed(self.post(self.handoff(text), extra_env={"BATON_LANG": lang})), (text, lang))
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
        self.assertIn('그다음 사용자에게 이 한 줄만 쓰고 턴을 끝낸다: "인계서를 고쳐 뒀어요. 이 기능을 끄려면 '
                      'BATON_HANDOFF_AUTO=off로 설정하세요."', reason)  # 사용자가 보는 한 줄도 해요체
        self.assertIn("기억으로 새로 쓰지 말고 지금 HANDOFF.md에서 시작해 아직 참인 줄은 그대로 옮긴다.", reason)
        self.assertIn("마지막 커밋판에서 빠진 줄을 알려 준다.", reason)
        self.assertNotIn("python3", reason)  # 검사기를 손으로 돌리라고 하지 않는다 — 저장 훅이 돌린다(권한 확인이 끼어들지 않게, 리뷰 11-23)
        skill = reason.split("baton 인계서 스킬(", 1)[1].split("의 ", 1)[0]
        with open(skill, encoding="utf-8") as f:
            self.assertIn("## When the Stop hook asks", f.read())  # 요청이 가리키는 스킬 절이 실제로 있다
        self.assertEqual([(e["event"], e["files"]) for e in self.events()], [("handoff_auto", 3)])
        self.assertIsNone(self.auto())  # 세션에 한 번
        self.assertIsNone(self.stop())  # 자동 쓰기를 했으면 같은 세션에 제안도 없다
        self.assertEqual(self.auto(sid="s2")["decision"], "block")

    def test_auto_write_only_for_absent_or_baton_handoff(self):
        # 리뷰(11-23): 저장소 루트의 HANDOFF.md가 남의 형식이면 모델에게 다시 쓰라고 하지 않는다 — 사용자에게 제안만
        self.write([edit("/r/a.py"), edit("/r/b.py"), edit("/r/c.py")])
        self.assertEqual(self.auto(sid="none")["decision"], "block")  # 인계서 없음 → 자동 쓰기
        self.handoff(GOOD_EN)
        self.assertEqual(self.auto(sid="ours")["decision"], "block")  # baton 형식 → 자동 쓰기
        self.handoff("# Project notes\n## Goal\n- ship\n## Next steps\n- review\n")
        out = self.auto(sid="foreign")
        self.assertEqual(set(out), {"systemMessage"})
        self.assertIn("파일을 3개 고쳤는데", out["systemMessage"])
        self.assertEqual([(e["event"], e.get("fallback")) for e in self.events()],
                         [("handoff_auto", None), ("handoff_auto", None), ("handoff_nudge", "foreign_handoff")])
        self.assertIsNone(self.auto(sid="foreign"))  # 세션에 한 번은 그대로

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
        self.assertIn("When you save it, the save-time check reports problems and lines dropped since the last committed "
                      "version.", reason)
        self.assertNotIn("python3", reason)
        self.assertIn('Then end your turn with exactly this one line to the user: "I updated the handoff. To turn this off, '
                      'set BATON_HANDOFF_AUTO=off."', reason)
        msg = self.stop(sid="s2", extra_env=en)
        self.assertEqual(msg, "[baton] You changed 3 files, but the handoff hasn't changed.\n"
                              "If you're done with the current task, try saying \"write a handoff\". "
                              "The next conversation won't have to search from scratch.\n"
                              "You'll see this suggestion only once per conversation.")
        out = self.post(self.handoff("# Session Handoff (written: 2026-11-23)\n- path /Users/someone/x\n"), extra_env=en)
        self.assertTrue(out["reason"].startswith("[baton] The HANDOFF.md you just wrote has handoff-check problems. "
                                                 "Fix them and save again:\n- missing required sections: Goal and done criteria"),
                        out["reason"])
        self.assertIn("\n- line 2: looks like an absolute home path", out["reason"])
        self.assertNotIn("someone", out["reason"])
        text = GOOD_EN.replace("## Verified facts and decisions\n- None\n", "## Verified facts and decisions\n- no mark\n")
        ctx = self.post(self.handoff(text), extra_env=en)["hookSpecificOutput"]["additionalContext"]
        self.assertTrue(ctx.startswith("[baton] Handoff-check warnings for the HANDOFF.md you just wrote (not blocking):\n- warning: "), ctx)
        self.assertTrue(self.passed(self.post(self.handoff(GOOD_EN), extra_env=en)).startswith(
            "[baton] HANDOFF.md check passed ("))  # 영어 템플릿은 통과 한 줄만
        self.assertTrue(self.passed(self.post(self.handoff(GOOD_EN))).startswith("[baton] HANDOFF.md 검사 통과("))  # 메시지가 한국어여도 영어 파일을 읽는다

    def test_dropped_lines_warned_against_last_commit(self):
        sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
        from test_handoff_check import DropCheckTest, git_repo
        p = self.handoff(DropCheckTest.OLD)
        self.assertIn("검사 통과", self.passed(self.post(p)))  # git 저장소가 아니면 비교할 판이 없다 — 경고 없이 통과
        g = git_repo(self.root); g("add", "HANDOFF.md"); g("commit", "-qm", "h")
        self.assertIn("검사 통과", self.passed(self.post(p)))  # 커밋판과 같다
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

    def test_big_drop_check_keeps_the_secret_block_and_hook_timeout(self):
        # 리뷰(11-23): 빠진 줄 검사가 10초 훅 시한을 넘기면 훅이 죽어 비밀값 막기까지 사라졌다
        import time
        from test_handoff_check import DropCostTest, git_repo
        old = DropCostTest.big(None, self.root)
        p = self.handoff(old)
        g = git_repo(self.root); g("add", "HANDOFF.md", "DECISIONS.md"); g("commit", "-qm", "h")
        token = "gh" + "p_" + "A1b2" * 9
        self.handoff(GOOD + f"- 토큰 {token}\n")
        t = time.monotonic()
        out = self.post(p)
        took = time.monotonic() - t
        self.assertLess(took, 5.0, took)  # 훅 시한 10초 훨씬 안
        self.assertEqual(out["decision"], "block")
        self.assertIn("API 토큰 의심 값", out["reason"])
        self.assertNotIn(token, out["reason"])
        self.assertIn("마지막 커밋판에 있던 줄 2000개가 새 인계서에 없다", out["reason"])
        self.assertLessEqual(len(out["reason"]), 9600)

    def test_stalled_git_keeps_the_secret_block(self):
        # 리뷰(11-23): exec 안 하는 git 감싸개 밑에서 cat-file이 멈추면 읽기가 30.2초 걸려 훅이 죽고 비밀값 막기가 사라졌다
        import time
        from test_handoff_check import git_repo, stalling_git
        p = self.handoff(GOOD)
        g = git_repo(self.root); g("add", "HANDOFF.md"); g("commit", "-qm", "h")
        token = "gh" + "p_" + "A1b2" * 9
        self.handoff(GOOD + f"- 토큰 {token}\n")
        t = time.monotonic()
        out = self.post(p, extra_env={"PATH": stalling_git(self.root, "29.75")})
        took = time.monotonic() - t
        self.assertLess(took, 5.0, took)  # 훅 시한 10초 훨씬 안
        self.assertEqual(out["decision"], "block")
        self.assertIn("API 토큰 의심 값", out["reason"])
        self.assertTrue(out["reason"].endswith("\n- 빠진 줄은 확인하지 못했어요(이전 판을 읽지 못함)."), out["reason"])  # 막기가 먼저, 못 읽음은 한 줄
        time.sleep(0.2)
        self.assertEqual(subprocess.run(["pgrep", "-f", "sleep 29.75"], capture_output=True, text=True).stdout.split(), [])

    def test_drop_check_skipped_for_time_says_so(self):
        import contextlib, importlib.util, io
        spec = importlib.util.spec_from_file_location("handoff_check_hook", HOOK)
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        path = self.handoff(GOOD)
        for lang, want in (("ko", "빠진 줄 검사를 건너뛰었다 — 빠진 줄 0개가 아니라 안 봤다"), ("en", "not zero dropped lines, just not checked")):
            buf = io.StringIO()
            env = {"XDG_CACHE_HOME": os.path.join(self.root, "cache"), "BATON_LOG": self.log, "BATON_LANG": lang}
            with mock.patch.dict(os.environ, env), mock.patch.object(hook, "HOOK_DEADLINE", 0), contextlib.redirect_stdout(buf):
                hook.on_edit({"tool_input": {"file_path": path}, "session_id": "s1"})
            ctx = json.loads(buf.getvalue())["hookSpecificOutput"]["additionalContext"]
            self.assertIn(want, ctx)
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": os.path.join(self.root, "cache"), "BATON_LOG": self.log}), \
                mock.patch.object(hook, "HOOK_DEADLINE", 0), contextlib.redirect_stdout(buf):
            hook.on_edit({"tool_input": {"file_path": self.handoff("# Notes\n## Status\n- ok\n")}, "session_id": "s1"})
        out = json.loads(buf.getvalue())  # 다른 형식 파일에는 건너뛴 검사를 말하지 않는다 — 빠진 줄은 baton 형식에서만 본다
        self.assertIn(out["hookSpecificOutput"]["additionalContext"],  # 언어는 이 테스트 환경의 로캘을 따른다
                      ("[baton] HANDOFF.md 검사 통과(3줄·23자).", "[baton] HANDOFF.md check passed (3 lines, 23 chars)."))

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
        self.assertEqual(msg, "[baton] 파일을 3개 고쳤는데 인계서는 그대로예요.\n"
                              "하던 일이 끝났다면 \"인계서 써 줘\"라고 해 보세요. 다음 대화가 처음부터 다시 찾지 않아도 돼요.\n"
                              "이 제안은 한 대화에 한 번만 나와요.")
        self.assertIsNone(self.stop())  # 세션에 한 번
        self.assertIsNotNone(self.stop(sid="s2"))

    def test_nudge_singular_in_english(self):
        self.write([edit("/r/a.py")])
        msg = self.stop(extra_env={"BATON_LANG": "en", "BATON_HANDOFF_NUDGE_FILES": "1"})
        self.assertTrue(msg.startswith("[baton] You changed 1 file, but the handoff hasn't changed.\n"), msg)

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


class BashWritesTest(unittest.TestCase):
    """넘길 일 세기의 Bash 판정과 시간 상한(리뷰 11-25). 프로세스 안에서 모듈을 불러 직접 본다."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location("handoff_check_hook", HOOK)
        cls.hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.hook)

    def test_cases(self):
        cases = {  # 명령 → (파일을 쓰는가, 인계서를 쓰는가)
            "cat <<'EOF' > HANDOFF.md\n# x\nEOF": (True, True), "echo hi | tee HANDOFF.md": (True, True),
            'echo hi > "HANDOFF.md"': (True, True), "mv draft.md HANDOFF.md": (True, True), "cp /tmp/h.md ./HANDOFF_track.md": (True, True),
            "python3 x.py > out.txt": (True, False), "python3 x.py 1> out.txt": (True, False), "python3 x.py &> out.log": (True, False),
            "python3 x.py >| out.txt": (True, False), "sed --in-place 's/a/b/' f": (True, False), "sed -Ei 's/a/b/' f": (True, False),
            "rtk proxy git mv a b": (True, False), "echo x | tee -a log.txt": (True, False),
            "cat <<A <<B\nbody a > x\nA\nbody b > y\nB\necho z > real.txt": (True, False),
            "python3 x.py 2> err.log": (False, False), 'python3 x.py > "$TMPDIR/o.txt"': (False, False),
            "python3 x.py > ${TMPDIR}/o.txt": (False, False), "python3 x.py > /tmp/o.txt": (False, False),
            "cat tee.txt; echo cp mv": (False, False), "(( a > 3 )) && echo ok": (False, False), "[[ $a > b ]] && echo ok": (False, False),
            "awk '$1>3' f.txt": (False, False), "python3 - <<'EOF'\nprint(1 > 2)\nEOF": (False, False), "ls 2>&1 | head": (False, False),
            "sed -n '1,5p' f": (False, False), "cat HANDOFF.md": (False, False), "cat <<<'here > x'": (False, False),
            # 문서에 적은 한계(docstring ponytail) — 바뀌면 문서도 고친다
            "sudo -u bob cp a b": (False, False), "timeout 10 cp a b": (False, False), "git -C repo mv a b": (False, False),
        }
        for cmd, want in cases.items():
            with self.subTest(cmd=cmd):
                self.assertEqual(self.hook.bash_writes(cmd), want)

    def test_pathological_command_is_fast(self):
        # 리뷰 11-25: 정규식 heredoc 처리가 << 많은 99KB 명령에서 3.75초 — 줄 단위 한 번 + 명령당 16KB 상한
        import time
        for cmd in ("<<a\n" * 25000, "cat <<EOF\n" + "x << y > z\n" * 20000 + "EOF\n", "sed " * 30000 + "-n x"):
            t = time.monotonic()
            self.hook.bash_writes(cmd)
            self.assertLess(time.monotonic() - t, 0.5, len(cmd))
        t = time.monotonic()
        self.hook.strip_heredocs("cat <<a <<b\n" + "line\n" * 200000)  # 상한 없이도 줄 수에 비례
        self.assertLess(time.monotonic() - t, 1.0)

    def test_work_counting_has_a_deadline_and_stop_falls_back_to_edits(self):
        import contextlib, io, tempfile, time
        with tempfile.TemporaryDirectory() as d:
            tr = os.path.join(d, "s.jsonl")
            usage = lambda c: json.dumps({"type": "assistant", "message": {"model": "m", "usage": {"input_tokens": c}}})
            with open(tr, "w", encoding="utf-8") as f:
                f.write("\n".join([usage(40000), edit("/r/a.py"), usage(260000)]) + "\n")
            self.assertIsNone(self.hook.work_since_handoff(tr, deadline=time.monotonic() - 1))  # 시한을 넘기면 None
            self.assertEqual(self.hook.work_since_handoff(tr), ["/r/a.py"])
            env = {"XDG_CACHE_HOME": os.path.join(d, "cache"), "BATON_LOG": os.path.join(d, "runs.jsonl"), "BATON_LANG": "ko",
                   "XDG_CONFIG_HOME": os.path.join(d, "cfg"), "BATON_HANDOFF_AUTO": "on"}
            buf = io.StringIO()
            with mock.patch.dict(os.environ, env), mock.patch.object(self.hook, "WORK_BUDGET", -1), contextlib.redirect_stdout(buf):
                self.hook.on_stop({"transcript_path": tr, "session_id": "s1", "hook_event_name": "Stop", "cwd": d})
            self.assertIn("25만 토큰을 넘었다", json.loads(buf.getvalue())["reason"])  # 시한을 넘겨도 편집 도구 세기로 묻는다


if __name__ == "__main__":
    unittest.main()
