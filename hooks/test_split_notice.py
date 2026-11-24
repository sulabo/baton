#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(__file__)
HOOK = os.path.join(HERE, "handoff-check.py")  # Stop 결정은 handoff-check.py on_stop 한 곳(11-24). split-notice.py는 재기·문장만
SPLIT = os.path.join(HERE, "split-notice.py")


def call(ctx, sidechain=False, model="claude-opus-5-5"):
    """메인 스레드 assistant 한 줄. 맥락은 input 1 + 캐시 생성 + 캐시 읽기로 나눠 담는다."""
    return json.dumps({
        "type": "assistant",
        "isSidechain": sidechain,
        "message": {
            "model": model,
            "usage": {"input_tokens": 1, "cache_creation_input_tokens": 1000, "cache_read_input_tokens": ctx - 1001},
        },
    })


class SplitNoticeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.transcript = os.path.join(self.root, "s.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, lines):
        with open(self.transcript, "w", encoding="utf-8") as f:
            f.write("\n".join([json.dumps({"type": "user", "message": {"content": "시작"}})] + lines) + "\n")

    def run_hook(self, sid="s1", extra_env=None, raw_stdin=None, unset=()):
        env = os.environ.copy()
        env["XDG_CACHE_HOME"] = os.path.join(self.root, "cache")  # 실제 캐시에 쓰지 않는다
        env["XDG_CONFIG_HOME"] = os.path.join(self.root, "config")  # 실제 설정 파일을 읽지 않는다
        env["BATON_LOG"] = os.path.join(self.root, "runs.jsonl")
        for k in ("BATON_SPLIT_NOTICE", "BATON_SPLIT_RATIOS", "BATON_HANDOFF_NUDGE", "BATON_HANDOFF_NUDGE_FILES"):
            env.pop(k, None)
        env["BATON_HANDOFF_AUTO"] = "off"  # 알림 문장을 보는 테스트 — 자동 쓰기(묻기)는 AutoSplitTest
        env["CLAUDE_PROJECT_DIR"] = self.root  # 저장소 루트의 HANDOFF.md 형식을 이 임시 폴더에서 본다
        env["BATON_LANG"] = "ko"  # 한국어 알림을 보는 테스트 — 영어는 extra_env로 덮는다
        if extra_env:
            env.update(extra_env)
        for k in unset:
            env.pop(k, None)
        stdin = raw_stdin if raw_stdin is not None else json.dumps(
            {"transcript_path": self.transcript, "session_id": sid, "hook_event_name": "Stop"})
        return subprocess.run([sys.executable, HOOK], input=stdin, text=True,
                              capture_output=True, env=env, check=False)

    def message(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)["systemMessage"] if result.stdout.strip() else None

    def test_below_threshold_is_silent(self):
        self.write([call(40000), call(70000)])
        self.assertIsNone(self.message(self.run_hook()))

    def test_band_is_a_floor_not_the_real_ratio(self):
        # 리뷰(11-24): 5만 → 14만 5천(2.9배)인데 "2배 길어졌어요"라고 했다 — 넘은 문턱이라 "2배 넘게"로 말한다
        self.write([call(50000), call(145000)])
        self.assertTrue(self.message(self.run_hook()).startswith("[baton] 대화가 처음보다 2배 넘게 길어졌어요(5만 → 14만 5천 토큰).\n"))
        self.assertTrue(self.message(self.run_hook(sid="e", extra_env={"BATON_LANG": "en"})).startswith(
            "[baton] This conversation is now more than 2× as long as at the start (50K → 145K tokens).\n"))

    def test_each_band_notifies_once(self):
        self.write([call(40000), call(85000)])
        first = self.message(self.run_hook())
        self.assertEqual(first, "[baton] 대화가 처음보다 2배 넘게 길어졌어요(4만 → 8만 5천 토큰).\n"
                                "하던 일이 끝났다면 새 대화로 넘어가 보세요.\n"
                                "넘어가는 법: \"인계서 써 줘\" → /clear → \"이어서\"\n"
                                "이 알림은 한 번만 나와요.")
        self.assertIsNone(self.message(self.run_hook()))  # 같은 문턱 다시 안 울림

        self.write([call(40000), call(85000), call(130000)])
        third = self.message(self.run_hook())
        self.assertEqual(third, "[baton] 대화가 처음보다 3배 넘게 길어졌어요(4만 → 13만 토큰).\n"
                                "하던 일이 끝났다면 새 대화로 넘어가 보세요.\n"
                                "넘어가는 법: \"인계서 써 줘\" → /clear → \"이어서\"\n"
                                "이 알림은 한 번만 나와요.")
        self.assertIsNone(self.message(self.run_hook()))

        with open(os.path.join(self.root, "runs.jsonl"), encoding="utf-8") as f:
            events = [json.loads(ln) for ln in f]
        self.assertEqual([e["band"] for e in events], [2.0, 3.0])

    def test_state_is_per_session(self):
        self.write([call(40000), call(90000)])
        self.assertIsNotNone(self.message(self.run_hook(sid="a")))
        self.assertIsNotNone(self.message(self.run_hook(sid="b")))

    def test_sidechain_and_synthetic_are_ignored(self):
        # 걸러야 할 줄을 맨 앞과 맨 끝에 둔다 — 필터가 빠지면 첫 값이 5,000이 되거나 끝 값이 200K가 되어 울린다
        self.write([call(5000, sidechain=True), call(5000, model="<synthetic>"), call(40000), call(50000),
                    call(200000, sidechain=True), call(200000, model="<synthetic>")])
        self.assertIsNone(self.message(self.run_hook()))

    def test_long_transcript_reads_tail_only(self):
        # 512KB 넘는 기록: 끝에서 잘린 한글 멀티바이트 줄을 버리고 마지막 호출을 읽는다
        pad = json.dumps({"type": "user", "message": {"content": "가" * 3000}}, ensure_ascii=False)
        self.write([call(40000)] + [pad] * 300 + [call(90000)])
        self.assertGreater(os.path.getsize(self.transcript), 512 * 1024)
        self.assertIn("(4만 → 9만 토큰)", self.message(self.run_hook()))

    def test_no_repeat_after_compaction(self):
        # 압축으로 맥락이 줄었다가 다시 2배를 넘어도 같은 문턱은 다시 울리지 않는다
        self.write([call(40000), call(90000)])
        self.assertIsNotNone(self.message(self.run_hook()))
        self.write([call(40000), call(90000), call(30000), call(95000)])
        self.assertIsNone(self.message(self.run_hook()))

    def test_unwritable_state_means_no_notice(self):
        # 한 번만 알린다는 약속을 못 지키면 알리지 않는다 — 상태 폴더 자리에 파일을 둬서 쓰기를 막는다
        os.makedirs(os.path.join(self.root, "cache", "baton"))
        open(os.path.join(self.root, "cache", "baton", "split"), "w").close()
        self.write([call(40000), call(90000)])
        self.assertIsNone(self.message(self.run_hook()))

    def test_odd_lines_fail_open(self):
        # 형식이 다른 줄(배열·문자열 message·숫자 아닌 usage)이 섞여도 오류 없이 나머지로 판단한다
        odd = ['["assistant"]', json.dumps({"type": "assistant", "message": "assistant"}),
               json.dumps({"type": "assistant", "message": {"usage": {"input_tokens": "x"}}}), "{깨진 줄 assistant"]
        self.write(odd + [call(40000)] + odd + [call(90000)] + odd)
        self.assertIn("(4만 → 9만 토큰)", self.message(self.run_hook()))

    def test_session_id_with_path_chars_is_ignored(self):
        self.write([call(40000), call(90000)])
        self.assertIsNone(self.message(self.run_hook(sid="../x")))

    def test_off_switch_and_custom_ratios(self):
        self.write([call(40000), call(90000)])
        self.assertIsNone(self.message(self.run_hook(extra_env={"BATON_SPLIT_NOTICE": "off"})))
        self.assertIsNone(self.message(self.run_hook(extra_env={"BATON_SPLIT_RATIOS": "4"})))
        msg = self.message(self.run_hook(extra_env={"BATON_SPLIT_RATIOS": "1.5,4"}))
        self.assertTrue(msg.startswith("[baton] 대화가 처음보다 1.5배 넘게 길어졌어요(4만 → 9만 토큰).\n"), msg)
        self.assertNotIn("아낄 수 있어요", msg)  # 절감 추정은 어느 문턱에서도 말하지 않는다(11-24)

    def test_bad_input_fails_open(self):
        for stdin in ("", "not json", "[]", json.dumps({"transcript_path": "/없는/경로.jsonl", "session_id": "x"})):
            result = self.run_hook(raw_stdin=stdin)
            self.assertEqual(result.returncode, 0, stdin)
            self.assertEqual(result.stdout, "", stdin)

    def test_english_notice(self):
        self.write([call(40000), call(85000)])
        msg = self.message(self.run_hook(extra_env={"BATON_LANG": "en"}))
        self.assertEqual(msg, "[baton] This conversation is now more than 2× as long as at the start (40K → 85K tokens).\n"
                              "If you're done with the current task, try moving to a new conversation.\n"
                              "To move: \"write a handoff\" → /clear → \"where were we\"\n"
                              "You'll see this notice only once.")
        self.write([call(40000), call(85000), call(130000)])
        third = self.message(self.run_hook(extra_env={"BATON_LANG": "en"}))
        self.assertTrue(third.startswith("[baton] This conversation is now more than 3× as long as at the start (40K → 130K tokens).\n"))
        self.assertNotIn("save", third)  # 절감 추정은 뺐다(11-24 /compact 맞대기 실험과 맞지 않음)
        self.write([call(40000), call(85000), call(130000), call(170000)])
        self.assertNotIn("save", self.message(self.run_hook(sid="en4", extra_env={"BATON_LANG": "en", "BATON_SPLIT_RATIOS": "4"})))

    def test_korean_token_counts(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("split_notice", SPLIT)
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        for n, want in ((85312, "8만 5천"), (172480, "17만 2천"), (40000, "4만"), (9500, "9천"), (999, "999"),
                        (1234567, "123만 4천"), (100000, "10만")):
            self.assertEqual(mod.man(n), want)

    def test_locale_decides_without_baton_lang(self):
        self.write([call(40000), call(90000)])
        drop = ("BATON_LANG", "LC_ALL", "LC_MESSAGES")
        self.assertIn("대화가 처음보다 2배 넘게 길어졌어요", self.message(self.run_hook(sid="k", extra_env={"LANG": "ko_KR.UTF-8"}, unset=drop)))
        self.assertIn("more than 2× as long as at the start", self.message(self.run_hook(sid="e", extra_env={"LANG": "C.UTF-8"}, unset=drop)))

    def test_non_claude_transcript_is_silent(self):
        # Codex 기록 모양(type=response_item)에는 맥락 정보가 없어 아무것도 내지 않는다
        lines = [json.dumps({"type": "response_item", "payload": {"type": "message", "role": "assistant"}})] * 3
        self.write(lines)
        self.assertIsNone(self.message(self.run_hook()))



def edit(path):
    return json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Edit", "input": {"file_path": path}}]}})


def prompt(text):
    return json.dumps({"type": "user", "message": {"content": text}})


class AutoSplitTest(unittest.TestCase):
    """맥락 문턱(2·3배)에서 모델이 인계서를 남기고 승인된 한 줄로 알린다(소유자 결정 11-24). /compact는 권하지 않는다.
    파일 고침 자동 쓰기와 같은 Stop 결정 — 한 Stop에 많아야 한 번 묻는다."""
    setUp, tearDown, write, run_hook = SplitNoticeTest.setUp, SplitNoticeTest.tearDown, SplitNoticeTest.write, SplitNoticeTest.run_hook

    def run_auto(self, sid="s1", extra_env=None, **payload):
        env = dict({"BATON_HANDOFF_AUTO": "on"}, **(extra_env or {}))
        stdin = json.dumps(dict({"transcript_path": self.transcript, "session_id": sid, "hook_event_name": "Stop",
                                 "cwd": self.root}, **payload))
        r = self.run_hook(sid=sid, extra_env=env, raw_stdin=stdin)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else None

    def events(self):
        p = os.path.join(self.root, "runs.jsonl")
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]

    def test_threshold_asks_the_model_once_per_band(self):
        self.write([call(40000), call(85000)])
        out = self.run_auto()
        self.assertEqual(set(out), {"decision", "reason"})
        reason = out["reason"]
        self.assertTrue(reason.startswith("[baton] 이 대화의 맥락이 처음보다 2배 넘게 커졌다(4만 → 8만 5천 토큰). 지금 baton 인계서 스킬("), reason)
        self.assertIn("/compact는 권하지 않는다.", reason)
        self.assertIn('그다음 사용자에게 이 한 줄만 쓰고 턴을 끝낸다: "대화가 처음보다 2배 넘게 길어져서 인계서를 남겨 뒀어요. '
                      '하던 일이 끝났다면 새 대화에서 "이어서"라고 하면 이어 갈 수 있어요."', reason)
        self.assertTrue(reason.endswith("이 요청은 맥락 문턱마다 한 번만 나온다."), reason)
        self.assertNotIn("아낄", reason)
        self.assertIsNone(self.run_auto())  # 같은 문턱은 다시 안 묻는다
        self.write([call(40000), call(85000), call(130000)])
        self.assertIn("3배 넘게 커졌다", self.run_auto()["reason"])  # 다음 문턱은 한 번 더
        self.assertEqual([(e["event"], e["band"], e["mode"]) for e in self.events()],
                         [("split_notice", 2.0, "ask"), ("split_notice", 3.0, "ask")])

    def test_english_ask(self):
        self.write([call(40000), call(85000)])
        reason = self.run_auto(extra_env={"BATON_LANG": "en"})["reason"]
        self.assertTrue(reason.startswith("[baton] This conversation's context is now more than 2× its size at the start "
                                          "(40K → 85K tokens). Write or update HANDOFF.md"), reason)
        self.assertIn("Do not suggest /compact.", reason)
        self.assertIn('Then end your turn with exactly this one line to the user: "This conversation is now more than 2× as '
                      'long as at the start, so I saved a handoff. If you\'re done with the current task, start a new '
                      'conversation and say "where were we"."', reason)
        self.assertTrue(reason.endswith("baton asks for this once per context threshold."), reason)

    def test_never_blocks_while_stop_hook_active_and_retries_later(self):
        self.write([call(40000), call(85000)])
        self.assertIsNone(self.run_auto(stop_hook_active=True))
        self.assertEqual(self.events(), [])  # 상태도 안 남긴다
        self.assertEqual(self.run_auto()["decision"], "block")

    def test_handoff_already_updated_this_turn_only_informs(self):
        self.write([call(40000), prompt("이어서 해 줘"), edit(os.path.join(self.root, "HANDOFF.md")), call(85000)])
        out = self.run_auto()
        self.assertEqual(out, {"systemMessage": "[baton] 대화가 처음보다 2배 넘게 길어졌어요(4만 → 8만 5천 토큰). 인계서는 이번 턴에 "
                                                "이미 남겨 뒀어요.\n하던 일이 끝났다면 새 대화에서 \"이어서\"라고 하면 이어 갈 수 있어요."})
        self.assertEqual(self.events()[-1]["mode"], "saved")
        self.write([call(40000), prompt("x"), edit(os.path.join(self.root, "HANDOFF.md")), call(130000)])
        en = self.run_auto(sid="e", extra_env={"BATON_LANG": "en"})
        self.assertEqual(en["systemMessage"], "[baton] This conversation is now more than 3× as long as at the start (40K → 130K "
                                              "tokens). The handoff was already saved in this turn.\nIf you're done with the "
                                              "current task, start a new conversation and say \"where were we\".")
        # 앞 턴에 쓴 인계서는 "이번 턴"이 아니다 — 묻는다
        self.write([call(40000), edit(os.path.join(self.root, "HANDOFF.md")), prompt("다음 일"), call(85000)])
        self.assertEqual(self.run_auto(sid="t2")["decision"], "block")

    def test_stop_hook_continuation_after_writing_informs_saved(self):
        # 자동 쓰기로 이어 간 턴(stop_hook_active)에서 인계서를 쓴 뒤 문턱을 넘으면 묻지 않고 알린다
        self.write([call(40000), prompt("x"), edit(os.path.join(self.root, "HANDOFF.md")), call(85000)])
        out = self.run_auto(stop_hook_active=True)
        self.assertIn("인계서는 이번 턴에 이미 남겨 뒀어요", out["systemMessage"])

    def test_foreign_handoff_and_auto_off_fall_back_to_notice(self):
        self.write([call(40000), call(85000)])
        with open(os.path.join(self.root, "HANDOFF.md"), "w", encoding="utf-8") as f:
            f.write("# Project notes\n## Goal\n- ship\n")
        out = self.run_auto()
        self.assertEqual(set(out), {"systemMessage"})
        self.assertTrue(out["systemMessage"].startswith("[baton] 대화가 처음보다 2배 넘게 길어졌어요(4만 → 8만 5천 토큰).\n하던 일이"))
        self.assertEqual((self.events()[-1]["mode"], self.events()[-1]["fallback"]), ("notice", "foreign_handoff"))
        os.remove(os.path.join(self.root, "HANDOFF.md"))
        self.assertEqual(set(self.run_auto(sid="off", extra_env={"BATON_HANDOFF_AUTO": "off"})), {"systemMessage"})
        self.assertIsNone(self.run_auto(sid="no", extra_env={"BATON_SPLIT_NOTICE": "off"}))  # 맥락 알림을 끄면 아무것도 없다

    def test_both_reasons_in_one_stop_ask_once(self):
        r = self.root
        self.write([call(40000), edit(f"{r}/a.py"), edit(f"{r}/b.py"), edit(f"{r}/c.py"), call(85000)])
        out = self.run_auto()
        self.assertEqual(set(out), {"decision", "reason"})  # 묻기는 하나
        reason = out["reason"]
        self.assertTrue(reason.startswith("[baton] 이 세션에서 인계서(HANDOFF.md·HANDOFF_*.md)를 마지막으로 쓴 뒤 파일 3개를 고쳤다: "
                                          "a.py, b.py, c.py. 이 대화의 맥락이 처음보다 2배 넘게 커졌다(4만 → 8만 5천 토큰)."), reason)
        self.assertEqual(reason.count("그다음 사용자에게 이 한 줄만 쓰고"), 1)
        self.assertIsNone(self.run_auto())  # 두 까닭 모두 상태가 남았다
        self.assertEqual(sorted(e["event"] for e in self.events()), ["handoff_auto", "split_notice"])
        off = self.run_auto(sid="o", extra_env={"BATON_HANDOFF_AUTO": "off"})  # 못 물으면 알림 하나에 둘 다
        self.assertEqual(set(off), {"systemMessage"})
        self.assertIn("2배 넘게 길어졌어요", off["systemMessage"])
        self.assertIn("파일을 3개 고쳤는데 인계서는 그대로예요", off["systemMessage"])

    def test_handoff_written_then_edits_in_same_turn_still_asks(self):
        # 이번 턴에 인계서를 쓴 뒤 파일 3개를 더 고쳤으면 다시 낡았다 — 알림으로 떨어지지 않고 묻는다(리뷰 11-24)
        r = self.root
        self.write([call(40000), prompt("x"), edit(f"{r}/HANDOFF.md"), edit(f"{r}/a.py"), edit(f"{r}/b.py"), edit(f"{r}/c.py"),
                    call(50000)])
        out = self.run_auto()
        self.assertEqual(out["decision"], "block")
        self.assertIn("파일 3개를 고쳤다", out["reason"])
        self.write([call(40000), prompt("x"), edit(f"{r}/HANDOFF.md"), edit(f"{r}/a.py"), edit(f"{r}/b.py"), edit(f"{r}/c.py"),
                    call(85000)])
        both = self.run_auto(sid="b")  # 맥락도 넘으면 한 번에 둘 다 — "이미 남겨 뒀어요"와 "그대로예요"가 섞이지 않는다
        self.assertEqual(set(both), {"decision", "reason"})
        self.assertIn("2배 넘게 커졌다", both["reason"])
        self.assertEqual([e["mode"] for e in self.events() if e["event"] == "split_notice"], ["ask"])

    def test_registered_split_notice_script_prints_nothing(self):
        self.write([call(40000), call(85000), call(130000)])
        r = subprocess.run([sys.executable, SPLIT], input=json.dumps({"transcript_path": self.transcript, "session_id": "s1",
                                                                     "hook_event_name": "Stop"}),
                           text=True, capture_output=True, env=dict(os.environ, XDG_CACHE_HOME=os.path.join(self.root, "c")))
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))  # 두 번 묻지 않게 — 결정은 handoff-check.py


if __name__ == "__main__":
    unittest.main()
