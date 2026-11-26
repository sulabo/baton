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


def edit(path):
    return json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Edit", "input": {"file_path": path}}]}})


def prompt(text):
    return json.dumps({"type": "user", "message": {"content": text}})


WORK = edit("/repo/a.py")  # 마지막 인계서 뒤에 고친 파일 하나 — 맥락 까닭은 이것이 있어야 나온다(11-25)
RATIOS = {"BATON_SPLIT_RATIOS": "2,3"}  # 예전 배수 규칙을 직접 정해 둔 사용자


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
        for k in ("BATON_SPLIT_NOTICE", "BATON_SPLIT_TOKENS", "BATON_SPLIT_RATIOS", "BATON_HANDOFF_NUDGE", "BATON_HANDOFF_NUDGE_FILES"):
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

    def events(self):
        p = os.path.join(self.root, "runs.jsonl")
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]

    def test_below_threshold_is_silent(self):
        # 첫 호출의 6배지만 25만 토큰 아래 — 기본 문턱은 호출 맥락의 절대 토큰 수다(11-25)
        self.write([call(40000), WORK, call(240000)])
        self.assertIsNone(self.message(self.run_hook()))

    def test_default_bands_are_250k_and_450k_once_each(self):
        self.write([call(76000), WORK, call(250000)])
        self.assertIsNone(self.message(self.run_hook()))  # 25만 "넘음"이라 딱 25만은 아니다
        self.write([call(76000), WORK, call(250000), call(251000)])
        self.assertEqual(self.message(self.run_hook()), "[baton] 대화가 25만 토큰을 넘었어요(7만 6천 → 25만 1천 토큰).\n"
                                                        "만든 사람의 기록으로 계산하면, 이 크기부터는 새 대화로 넘어가는 쪽이 대개 더 싸요.\n"
                                                        "넘어가는 법: \"인계서 써 줘\" → /clear → \"이어서\"\n"
                                                        "이 알림은 한 번만 나와요.")
        self.assertIsNone(self.message(self.run_hook()))  # 같은 문턱 다시 안 울림
        self.write([call(76000), WORK, call(251000), call(449000)])
        self.assertIsNone(self.message(self.run_hook()))
        self.write([call(76000), WORK, call(251000), call(460000)])
        self.assertTrue(self.message(self.run_hook()).startswith("[baton] 대화가 45만 토큰을 넘었어요(7만 6천 → 46만 토큰).\n"))
        self.assertIsNone(self.message(self.run_hook()))
        self.assertEqual([e["band"] for e in self.events()], [250000, 450000])

    def test_no_edit_since_handoff_is_silent_and_band_waits(self):
        # 11-25 실사용: 질문만 한 턴 뒤에 인계서를 다시 쓰게 했다. 마지막 인계서 뒤 고친 파일이 0개면 알리지도 않고
        # 문턱도 남기지 않는다 — 나중에 파일을 고친 Stop에서 그 문턱을 한 번 알린다
        self.write([call(40000), call(260000)])
        self.assertIsNone(self.message(self.run_hook()))
        self.write([call(40000), WORK, edit("/repo/HANDOFF_track.md"), prompt("질문만"), call(260000)])
        self.assertIsNone(self.message(self.run_hook()))
        self.assertEqual(self.events(), [])
        self.assertFalse(os.path.exists(os.path.join(self.root, "cache", "baton", "split", "s1.json")))
        self.write([call(40000), WORK, edit("/repo/HANDOFF_track.md"), prompt("질문만"), call(260000), edit("/repo/b.py"),
                    call(262000)])
        self.assertIn("대화가 25만 토큰을 넘었어요(4만 → 26만 2천 토큰)", self.message(self.run_hook()))

    def test_explicit_ratios_keep_the_old_rule_and_wording(self):
        self.write([call(200000), WORK, call(300000)])
        self.assertIsNone(self.message(self.run_hook(extra_env=RATIOS)))  # 1.5배 — 30만이어도 배수 규칙이면 안 울린다
        self.write([call(40000), WORK, call(85000)])
        self.assertEqual(self.message(self.run_hook(extra_env=RATIOS)), "[baton] 대화가 처음보다 2배 넘게 길어졌어요(4만 → 8만 5천 토큰).\n"
                                                                       "하던 일이 끝났다면 새 대화로 넘어가 보세요.\n"
                                                                       "넘어가는 법: \"인계서 써 줘\" → /clear → \"이어서\"\n"
                                                                       "이 알림은 한 번만 나와요.")
        self.write([call(40000), WORK, call(85000), call(130000)])
        self.assertTrue(self.message(self.run_hook(extra_env=RATIOS)).startswith(
            "[baton] 대화가 처음보다 3배 넘게 길어졌어요(4만 → 13만 토큰).\n"))
        self.assertEqual([e["band"] for e in self.events()], [2.0, 3.0])
        en = self.message(self.run_hook(sid="e", extra_env=dict(RATIOS, BATON_LANG="en")))
        self.assertEqual(en, "[baton] This conversation is now more than 3× as long as at the start (40K → 130K tokens).\n"
                             "If you're done with the current task, try moving to a new conversation.\n"
                             "To move: \"write a handoff\" → /clear → \"where were we\"\n"
                             "You'll see this notice only once.")
        self.write([call(40000), WORK, call(90000)])
        self.assertIsNone(self.message(self.run_hook(sid="r4", extra_env={"BATON_SPLIT_RATIOS": "4"})))
        msg = self.message(self.run_hook(sid="r15", extra_env={"BATON_SPLIT_RATIOS": "1.5,4"}))
        self.assertTrue(msg.startswith("[baton] 대화가 처음보다 1.5배 넘게 길어졌어요(4만 → 9만 토큰).\n"), msg)
        self.assertNotIn("아낄 수 있어요", msg)  # 절감 추정은 어느 문턱에서도 말하지 않는다(11-24)
        # 둘 다 정했으면 새 키(토큰)가 이긴다
        self.assertIn("8만 토큰을 넘었어요", self.message(self.run_hook(sid="both", extra_env={"BATON_SPLIT_RATIOS": "4",
                                                                                          "BATON_SPLIT_TOKENS": "80000"})))

    def test_state_is_per_session(self):
        self.write([call(40000), WORK, call(260000)])
        self.assertIsNotNone(self.message(self.run_hook(sid="a")))
        self.assertIsNotNone(self.message(self.run_hook(sid="b")))

    def test_sidechain_and_synthetic_are_ignored(self):
        # 걸러야 할 줄을 맨 앞과 맨 끝에 둔다 — 필터가 빠지면 끝 값이 30만이 되어 울리거나 첫 값이 5,000으로 찍힌다
        self.write([call(5000, sidechain=True), call(5000, model="<synthetic>"), call(40000), WORK, call(50000),
                    call(300000, sidechain=True), call(300000, model="<synthetic>")])
        self.assertIsNone(self.message(self.run_hook()))
        self.write([call(5000, sidechain=True), call(5000, model="<synthetic>"), call(40000), WORK, call(260000)])
        self.assertIn("(4만 → 26만 토큰)", self.message(self.run_hook()))

    def test_long_transcript_reads_tail_only(self):
        # 512KB 넘는 기록: 끝에서 잘린 한글 멀티바이트 줄을 버리고 마지막 호출을 읽는다
        # 채움 줄은 모델의 긴 답(사용량 없음) — 사람 프롬프트로 채우면 턴이 바뀌어 이번 턴에 한 일이 없어진다(1.0.2)
        pad = json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "가" * 3000}]}}, ensure_ascii=False)
        self.write([call(40000), WORK] + [pad] * 300 + [call(260000)])
        self.assertGreater(os.path.getsize(self.transcript), 512 * 1024)
        self.assertIn("(4만 → 26만 토큰)", self.message(self.run_hook()))

    def test_no_repeat_after_compaction(self):
        # 압축으로 맥락이 줄었다가 다시 문턱을 넘어도 같은 문턱은 다시 울리지 않는다
        self.write([call(40000), WORK, call(260000)])
        self.assertIsNotNone(self.message(self.run_hook()))
        self.write([call(40000), WORK, call(260000), call(30000), call(270000)])
        self.assertIsNone(self.message(self.run_hook()))
        # 한 번에 두 문턱을 넘어 높은 쪽(45만)만 알렸으면, 압축 뒤 25만~45만에서 낮은 문턱을 다시 묻지 않는다(11-25 노트)
        self.write([call(40000), WORK, call(460000)])
        self.assertIn("45만 토큰을 넘었어요", self.message(self.run_hook(sid="jump")))
        self.write([call(40000), WORK, call(460000), call(30000), WORK, call(300000)])
        self.assertIsNone(self.message(self.run_hook(sid="jump")))

    def test_unwritable_state_means_no_notice(self):
        # 한 번만 알린다는 약속을 못 지키면 알리지 않는다 — 상태 폴더 자리에 파일을 둬서 쓰기를 막는다
        os.makedirs(os.path.join(self.root, "cache", "baton"))
        open(os.path.join(self.root, "cache", "baton", "split"), "w").close()
        self.write([call(40000), WORK, call(260000)])
        self.assertIsNone(self.message(self.run_hook()))

    def test_odd_lines_fail_open(self):
        # 형식이 다른 줄(배열·문자열 message·숫자 아닌 usage)이 섞여도 오류 없이 나머지로 판단한다
        odd = ['["assistant"]', json.dumps({"type": "assistant", "message": "assistant"}),
               json.dumps({"type": "assistant", "message": {"usage": {"input_tokens": "x"}}}), "{깨진 줄 assistant"]
        self.write(odd + [call(40000)] + odd + [WORK, call(260000)] + odd)
        self.assertIn("(4만 → 26만 토큰)", self.message(self.run_hook()))

    def test_session_id_with_path_chars_is_ignored(self):
        self.write([call(40000), WORK, call(260000)])
        self.assertIsNone(self.message(self.run_hook(sid="../x")))

    def test_off_switch_and_custom_tokens(self):
        self.write([call(40000), WORK, call(260000)])
        self.assertIsNone(self.message(self.run_hook(extra_env={"BATON_SPLIT_NOTICE": "off"})))
        self.assertIsNone(self.message(self.run_hook(extra_env={"BATON_SPLIT_TOKENS": "300000"})))
        msg = self.message(self.run_hook(extra_env={"BATON_SPLIT_TOKENS": "100000,300000"}))
        self.assertTrue(msg.startswith("[baton] 대화가 10만 토큰을 넘었어요(4만 → 26만 토큰).\n"), msg)
        for i, bad in enumerate(({"BATON_SPLIT_TOKENS": "x"}, {"BATON_SPLIT_TOKENS": "0"}, {"BATON_SPLIT_TOKENS": "-250000"},
                                 {"BATON_SPLIT_TOKENS": "250_000"}, {"BATON_SPLIT_TOKENS": ""}, {"BATON_SPLIT_RATIOS": "abc"},
                                 {"BATON_SPLIT_RATIOS": "0.5"})):
            with self.subTest(bad=bad):  # /baton-setup apply가 받지 않는 값은 새 토큰 기본값으로(배수의 abc도 예전 배수가 아니라)
                self.assertTrue(self.message(self.run_hook(sid=f"bad{i}", extra_env=bad)).startswith(
                    "[baton] 대화가 25만 토큰을 넘었어요(4만 → 26만 토큰).\n"))

    def test_bad_input_fails_open(self):
        for stdin in ("", "not json", "[]", json.dumps({"transcript_path": "/없는/경로.jsonl", "session_id": "x"})):
            result = self.run_hook(raw_stdin=stdin)
            self.assertEqual(result.returncode, 0, stdin)
            self.assertEqual(result.stdout, "", stdin)

    def test_english_notice(self):
        self.write([call(40000), WORK, call(260000)])
        msg = self.message(self.run_hook(extra_env={"BATON_LANG": "en"}))
        self.assertEqual(msg, "[baton] The conversation passed 250K tokens (40K → 260K tokens).\n"
                              "By a recount of the author's sessions, from this size on, moving to a new conversation is usually cheaper.\n"
                              "To move: \"write a handoff\" → /clear → \"where were we\"\n"
                              "You'll see this notice only once.")
        self.write([call(40000), WORK, call(260000), call(460000)])
        second = self.message(self.run_hook(extra_env={"BATON_LANG": "en"}))
        self.assertTrue(second.startswith("[baton] The conversation passed 450K tokens (40K → 460K tokens).\n"), second)
        self.assertNotIn("save", second)  # 절감 추정은 말하지 않는다(11-24 /compact 맞대기 실험과 맞지 않음)

    def test_korean_token_counts(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("split_notice", SPLIT)
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        for n, want in ((85312, "8만 5천"), (172480, "17만 2천"), (40000, "4만"), (9500, "9천"), (999, "999"),
                        (1234567, "123만 4천"), (100000, "10만")):
            self.assertEqual(mod.man(n), want)
        self.assertEqual((mod.band_label("ko", 250000), mod.band_label("en", 450000)), ("25만 토큰", "450K tokens"))

    def test_locale_decides_without_baton_lang(self):
        self.write([call(40000), WORK, call(260000)])
        drop = ("BATON_LANG", "LC_ALL", "LC_MESSAGES")
        self.assertIn("대화가 25만 토큰을 넘었어요", self.message(self.run_hook(sid="k", extra_env={"LANG": "ko_KR.UTF-8"}, unset=drop)))
        self.assertIn("The conversation passed 250K tokens", self.message(self.run_hook(sid="e", extra_env={"LANG": "C.UTF-8"}, unset=drop)))

    def test_non_claude_transcript_is_silent(self):
        # Codex 기록 모양(type=response_item)에는 맥락 정보가 없어 아무것도 내지 않는다
        lines = [json.dumps({"type": "response_item", "payload": {"type": "message", "role": "assistant"}})] * 3
        self.write(lines)
        self.assertIsNone(self.message(self.run_hook()))


class AutoSplitTest(unittest.TestCase):
    """맥락 문턱(기본 25만·45만 토큰)에서 모델이 인계서를 남기고 승인된 한 줄로 알린다(소유자 결정 11-24·11-25). /compact는 권하지 않는다.
    파일 고침 자동 쓰기와 같은 Stop 결정 — 한 Stop에 많아야 한 번 묻는다. 마지막 인계서 뒤 고친 파일이 없으면 묻지 않는다."""
    setUp, tearDown, write, run_hook, events = (SplitNoticeTest.setUp, SplitNoticeTest.tearDown, SplitNoticeTest.write,
                                                SplitNoticeTest.run_hook, SplitNoticeTest.events)

    def run_auto(self, sid="s1", extra_env=None, **payload):
        env = dict({"BATON_HANDOFF_AUTO": "on"}, **(extra_env or {}))
        stdin = json.dumps(dict({"transcript_path": self.transcript, "session_id": sid, "hook_event_name": "Stop",
                                 "cwd": self.root}, **payload))
        r = self.run_hook(sid=sid, extra_env=env, raw_stdin=stdin)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else None

    def test_threshold_asks_the_model_once_per_band(self):
        self.write([call(76000), WORK, call(260000)])
        out = self.run_auto()
        self.assertEqual(set(out), {"decision", "reason"})
        reason = out["reason"]
        self.assertTrue(reason.startswith("[baton] 이 대화의 맥락이 25만 토큰을 넘었다(7만 6천 → 26만 토큰). 만든 사람의 기록으로 계산하면, "
                                          "이 크기부터는 이어 가는 것보다 인계서를 쓰고 새 대화로 넘기는 쪽이 대개 더 싸다. "
                                          "지금 baton 인계서 스킬("), reason)
        self.assertIn("/compact는 권하지 않는다.", reason)
        self.assertIn('그다음 사용자에게 이 한 줄만 쓰고 턴을 끝낸다: "대화가 25만 토큰을 넘어서 인계서를 남겨 뒀어요. '
                      '만든 사람의 기록으로 계산하면, 이 크기부터는 새 대화에서 "이어서"라고 하는 쪽이 대개 더 싸요."', reason)
        self.assertTrue(reason.endswith("이 요청은 맥락 문턱마다 한 번만 나온다."), reason)
        self.assertNotIn("아낄", reason)
        self.assertIsNone(self.run_auto())  # 같은 문턱은 다시 안 묻는다
        self.write([call(76000), WORK, call(260000), call(460000)])
        self.assertIn("45만 토큰을 넘었다", self.run_auto()["reason"])  # 다음 문턱은 한 번 더
        self.assertEqual([(e["event"], e["band"], e["mode"]) for e in self.events()],
                         [("split_notice", 250000, "ask"), ("split_notice", 450000, "ask")])

    def test_no_edit_since_handoff_never_blocks_and_asks_after_an_edit(self):
        # 11-25 실사용: 질문만 한 턴(고친 파일 0개) 뒤에 막고 인계서를 다시 쓰게 했다 — 묻지도 알리지도 않고 문턱도 남기지 않는다
        h = os.path.join(self.root, "HANDOFF.md")
        self.write([call(76000), edit(f"{self.root}/a.py"), edit(h), prompt("이건 뭐야?"), call(260000)])
        self.assertIsNone(self.run_auto())
        self.assertEqual(self.events(), [])
        self.write([call(76000), edit(f"{self.root}/a.py"), edit(h), prompt("이건 뭐야?"), call(260000), prompt("고쳐 줘"),
                    edit(f"{self.root}/b.py"), call(265000)])
        out = self.run_auto()
        self.assertEqual(out["decision"], "block")
        self.assertIn("25만 토큰을 넘었다(7만 6천 → 26만 5천 토큰)", out["reason"])
        self.assertNotIn("파일 1개를 고쳤다", out["reason"])  # 파일 수 까닭(기본 3개)은 그대로
        self.assertEqual([e["mode"] for e in self.events()], ["ask"])

    def test_question_or_read_only_turn_waits_for_a_turn_that_works(self):
        # 1.0.1 재돌림(대화 6개, Stop 155곳): 막힘 10번 중 5번이 질문·읽기만 한 턴 끝이었다(앞선 턴에 한 일이 있어서).
        # 소유자 결정 11-26: 이번 턴에 일했을 때만 묻는다. 문턱은 남겨 뒀다가 다음에 일한 턴 끝에 한 번
        r = self.root
        tool = lambda name, **inp: json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]}})
        reads = [tool("Read", file_path=f"{r}/a.py"), tool("Bash", command="git log --oneline -3"), tool("Grep", pattern="x"),
                 tool("Bash", command="python3 x.py > /tmp/o.txt")]
        for i, turn in enumerate(([prompt("이건 뭐야?")], [prompt("어디 봐 줘")] + reads)):
            with self.subTest(i=i):
                self.write([call(40000), WORK, call(100000)] + turn + [call(260000)])
                self.assertIsNone(self.run_auto(sid=f"q{i}"))
                self.assertIsNone(self.run_auto(sid=f"n{i}", extra_env={"BATON_HANDOFF_AUTO": "off"}))  # 알림으로도 안 나온다
        self.assertEqual(self.events(), [])
        self.assertFalse(os.path.exists(os.path.join(self.root, "cache", "baton", "split", "q0.json")))  # 문턱이 남지 않았다
        self.write([call(40000), WORK, call(100000), prompt("이건 뭐야?"), call(260000), prompt("그럼 고쳐 줘"), edit(f"{r}/b.py"),
                    call(262000)])
        self.assertIn("25만 토큰을 넘었다(4만 → 26만 2천 토큰)", self.run_auto(sid="q0")["reason"])
        self.assertIsNone(self.run_auto(sid="q0"))
        self.write([call(40000), edit(f"{r}/a.py"), edit(f"{r}/b.py"), edit(f"{r}/c.py"), prompt("질문만"), call(50000)])
        self.assertIn("파일 3개를 고쳤다", self.run_auto(sid="f", extra_env={"BATON_SPLIT_NOTICE": "off"})["reason"])  # 파일 수 까닭은 그대로

    def test_english_ask(self):
        self.write([call(76000), WORK, call(260000)])
        reason = self.run_auto(extra_env={"BATON_LANG": "en"})["reason"]
        self.assertTrue(reason.startswith("[baton] This conversation's context passed 250K tokens (76K → 260K tokens). "
                                          "By a recount of the author's sessions, from this size on, writing a handoff and moving to a "
                                          "new conversation is usually cheaper than continuing. Write or update HANDOFF.md"), reason)
        self.assertIn("Do not suggest /compact.", reason)
        self.assertIn('Then end your turn with exactly this one line to the user: "The conversation passed 250K tokens, so I '
                      'saved a handoff. By a recount of the author\'s sessions, from this size on, starting a new conversation and saying '
                      '"where were we" is usually cheaper."', reason)
        self.assertTrue(reason.endswith("baton asks for this once per context threshold."), reason)

    def test_explicit_ratios_ask_keeps_old_wording(self):
        self.write([call(40000), WORK, call(85000)])
        reason = self.run_auto(extra_env=RATIOS)["reason"]
        self.assertTrue(reason.startswith("[baton] 이 대화의 맥락이 처음보다 2배 넘게 커졌다(4만 → 8만 5천 토큰). 지금 baton 인계서 스킬("),
                        reason)
        self.assertIn('그다음 사용자에게 이 한 줄만 쓰고 턴을 끝낸다: "대화가 처음보다 2배 넘게 길어져서 인계서를 남겨 뒀어요. '
                      '하던 일이 끝났다면 새 대화에서 "이어서"라고 하면 이어 갈 수 있어요."', reason)
        en = self.run_auto(sid="e", extra_env=dict(RATIOS, BATON_LANG="en"))["reason"]
        self.assertTrue(en.startswith("[baton] This conversation's context is now more than 2× its size at the start "
                                      "(40K → 85K tokens). Write or update HANDOFF.md"), en)
        self.assertIn('"This conversation is now more than 2× as long as at the start, so I saved a handoff. If you\'re done '
                      'with the current task, start a new conversation and say "where were we"."', en)

    def test_never_blocks_while_stop_hook_active_and_retries_later(self):
        self.write([call(40000), WORK, call(260000)])
        self.assertIsNone(self.run_auto(stop_hook_active=True))
        self.assertEqual(self.events(), [])  # 상태도 안 남긴다
        self.assertEqual(self.run_auto()["decision"], "block")

    def test_handoff_written_this_turn_waits_for_work_after_it(self):
        # 리뷰 11-25: 이번 턴에 인계서를 썼고 그 뒤 일이 없으면 조용하고 문턱도 남기지 않는다. 그 뒤에 일했으면 인계서가 다시 낡았다 — 묻는다
        h = os.path.join(self.root, "HANDOFF.md")
        self.write([call(40000), prompt("이어서 해 줘"), WORK, edit(h), call(260000)])
        self.assertIsNone(self.run_auto())
        self.assertEqual(self.events(), [])
        self.assertFalse(os.path.exists(os.path.join(self.root, "cache", "baton", "split", "s1.json")))  # 문턱이 남지 않았다
        self.write([call(40000), prompt("이어서 해 줘"), WORK, edit(h), call(260000), edit(f"{self.root}/b.py"), call(262000)])
        out = self.run_auto()
        self.assertEqual(out["decision"], "block")
        self.assertIn("25만 토큰을 넘었다(4만 → 26만 2천 토큰)", out["reason"])
        self.write([call(40000), prompt("x"), edit(h), WORK, call(85000)])  # 배수 규칙도 같다 — 알리기만 하던 길은 없다
        self.assertEqual(self.run_auto(sid="r", extra_env=RATIOS)["decision"], "block")

    def test_stop_hook_continuation_never_blocks_and_keeps_the_band(self):
        # 자동 쓰기로 이어 간 턴(stop_hook_active)은 막지도 알리지도 않는다 — 문턱을 남기지 않아 다음 턴 끝에 묻는다
        self.write([call(40000), prompt("x"), edit(os.path.join(self.root, "HANDOFF.md")), WORK, call(260000)])
        self.assertIsNone(self.run_auto(stop_hook_active=True))
        self.assertEqual(self.events(), [])
        self.assertEqual(self.run_auto()["decision"], "block")

    def test_cost_claim_only_from_the_supported_band(self):
        # 리뷰 11-25: 재계산은 15만에서 대개 손해였다 — 25만 아래 문턱(낮춘 값)에서는 "대개 더 싸요"라고 하지 않는다
        self.write([call(40000), WORK, call(160000)])
        low = self.run_auto(extra_env={"BATON_SPLIT_TOKENS": "150000"})["reason"]
        self.assertIn("이 대화의 맥락이 15만 토큰을 넘었다(4만 → 16만 토큰). 지금 baton 인계서 스킬(", low)
        self.assertIn('"대화가 15만 토큰을 넘어서 인계서를 남겨 뒀어요. 하던 일이 끝났다면 새 대화에서 "이어서"라고 하면 이어 갈 수 있어요."', low)
        self.assertNotIn("싸", low)
        en = self.run_auto(sid="e", extra_env={"BATON_SPLIT_TOKENS": "150000", "BATON_LANG": "en"})["reason"]
        self.assertIn('"The conversation passed 150K tokens, so I saved a handoff. If you\'re done with this, you can continue in a new '
                      'conversation by saying "where were we"."', en)
        self.assertNotIn("cheaper", en)
        note = self.run_auto(sid="n", extra_env={"BATON_SPLIT_TOKENS": "150000", "BATON_HANDOFF_AUTO": "off"})["systemMessage"]
        self.assertEqual(note.splitlines()[:2], ["[baton] 대화가 15만 토큰을 넘었어요(4만 → 16만 토큰).", "하던 일이 끝났다면 새 대화로 넘어가 보세요."])
        mixed = self.run_auto(sid="m", extra_env={"BATON_SPLIT_TOKENS": "150000,250000"})  # 높은 문턱은 그대로 비용 문장
        self.assertIsNotNone(mixed)
        self.write([call(40000), WORK, call(160000), call(260000)])
        self.assertIn("만든 사람의 기록으로 계산하면", self.run_auto(sid="m", extra_env={"BATON_SPLIT_TOKENS": "150000,250000"})["reason"])

    def agent(self, tid, kind=None, agent_id=None, edits=None):
        """메인 기록의 Agent 호출 줄(+ 결과 줄). edits가 목록이면 그 서브에이전트 기록(<세션>/subagents/agent-<id>.jsonl)을 만든다."""
        inp = {"prompt": "x", **({"subagent_type": kind} if kind else {})}
        lines = [json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": tid, "name": "Agent", "input": inp}]}})]
        if agent_id:
            lines.append(json.dumps({"type": "user", "toolUseResult": {"agentId": agent_id},
                                     "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "content": "done"}]}}))
        if edits is not None:
            d = os.path.join(os.path.splitext(self.transcript)[0], "subagents")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, f"agent-{agent_id}.jsonl"), "w", encoding="utf-8") as f:
                for name, inp2 in edits:
                    f.write(json.dumps({"type": "assistant", "isSidechain": True, "agentId": agent_id,
                                        "message": {"content": [{"type": "tool_use", "name": name, "input": inp2}]}}) + "\n")
        return lines

    def test_read_only_delegation_is_not_work(self):
        # 리뷰 11-25: 질문만 한 턴의 Explore 위임이 막았다 — 서브에이전트가 실제로 고쳤을 때만 일로 센다
        h = os.path.join(self.root, "HANDOFF.md")
        reads = [("Read", {"file_path": "/r/a.py"}), ("Bash", {"command": "git log --oneline -3 | cat"})]
        self.write([call(40000), WORK, edit(h), prompt("이건 왜 이래?")] + self.agent("t1", "Explore", "a1", reads) + [call(260000)])
        self.assertIsNone(self.run_auto())
        self.write([call(40000), WORK, edit(h), prompt("q")] + self.agent("t1", "oh-my-claudecode:executor", "a1", reads) + [call(260000)])
        self.assertIsNone(self.run_auto(sid="exec-read"))  # 기록이 있으면 종류가 아니라 실제로 한 일로 본다
        self.write([call(40000), WORK, edit(h), prompt("고쳐 줘")]
                   + self.agent("t2", "oh-my-claudecode:executor", "a2", [("Edit", {"file_path": "/r/a.py"})]) + [call(260000)])
        self.assertEqual(self.run_auto(sid="exec-edit")["decision"], "block")
        self.write([call(40000), WORK, edit(h), prompt("q")]
                   + self.agent("t3", "Explore", "a3", [("Bash", {"command": "python3 gen.py > out.json"})]) + [call(260000)])
        self.assertEqual(self.run_auto(sid="explore-wrote")["decision"], "block")  # 종류가 읽기여도 실제로 쓰면 일이다

    def test_delegation_without_a_subagent_record_falls_back_to_its_kind(self):
        h = os.path.join(self.root, "HANDOFF.md")
        for i, (kind, asks) in enumerate((("Explore", False), ("Plan", False), ("oh-my-claudecode:code-reviewer", False),
                                          ("oh-my-claudecode:verifier", False), (None, True), ("oh-my-claudecode:executor", True))):
            with self.subTest(kind=kind):
                self.write([call(40000), edit(h), prompt("q")] + self.agent(f"t{i}", kind) + [call(260000)])  # 결과가 아직 없음
                out = self.run_auto(sid=f"k{i}")
                self.assertEqual(out is not None, asks, out)
        side = json.dumps({"type": "assistant", "isSidechain": True,
                           "message": {"content": [{"type": "tool_use", "name": "Edit", "input": {"file_path": "/r/a.py"}}]}})
        self.write([call(40000), edit(h), prompt("q")] + self.agent("t9", "Explore") + [side, call(260000)])  # 옛 형식: 사이드체인 줄
        self.assertEqual(self.run_auto(sid="old")["decision"], "block")

    def test_request_blob_replay_is_not_work(self):
        # 리뷰 11-25: api-request-blob 줄은 앞선 호출(Agent·Edit·Bash)을 다시 담는다 — 인계서 뒤의 blob을 새 일로 세면 질문만 한 턴을 막는다
        h = os.path.join(self.root, "HANDOFF.md")
        def blob(*blocks):
            return json.dumps({"type": "api-request-blob", "hash": "x", "message": {"role": "assistant", "content": list(blocks)}})
        old_agent = {"type": "tool_use", "id": "t0", "name": "Agent", "input": {"prompt": "x", "subagent_type": "oh-my-claudecode:executor"}}
        old_edit = {"type": "tool_use", "name": "Edit", "input": {"file_path": f"{self.root}/a.py"}}
        for i, b in enumerate((old_agent, old_edit, {"type": "tool_use", "name": "Bash", "input": {"command": "echo x > out.txt"}})):
            with self.subTest(block=b["name"]):
                self.write([call(40000), WORK, edit(h), prompt("이건 뭐야?"), blob(b), call(260000)])
                self.assertIsNone(self.run_auto(sid=f"blob{i}"))
        r = self.root  # 파일 수 까닭(F)과 /baton-setup 분포의 edit_paths도 blob을 세지 않는다
        self.write([call(40000), blob(*[{"type": "tool_use", "name": "Edit", "input": {"file_path": f"{r}/{n}.py"}} for n in "abc"]),
                    call(50000)])
        self.assertIsNone(self.run_auto(sid="blobF", extra_env={"BATON_SPLIT_NOTICE": "off"}))

    def test_corrupt_subagent_record_falls_back_to_its_kind(self):
        h = os.path.join(self.root, "HANDOFF.md")
        d = os.path.join(os.path.splitext(self.transcript)[0], "subagents")
        os.makedirs(d, exist_ok=True)
        for i, (kind, asks) in enumerate((("Explore", False), ("oh-my-claudecode:executor", True))):
            with self.subTest(kind=kind):
                with open(os.path.join(d, f"agent-c{i}.jsonl"), "w", encoding="utf-8") as f:
                    f.write("{깨진 줄\nnot json\n")  # 있지만 읽히는 줄이 없다
                self.write([call(40000), edit(h), prompt("q")] + self.agent(f"t{i}", kind, f"c{i}") + [call(260000)])
                self.assertEqual(self.run_auto(sid=f"c{i}") is not None, asks)

    def test_bash_handoff_write_also_resets_the_file_count(self):
        # 리뷰 11-25: 파일 수 까닭(F)도 Bash로 쓴 인계서에서 처음부터 센다 — 세는 것은 그대로 편집 도구의 파일
        bash = lambda c: json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": c}}]}})
        r, off = self.root, {"BATON_SPLIT_NOTICE": "off"}
        three = [edit(f"{r}/a.py"), edit(f"{r}/b.py"), edit(f"{r}/c.py")]
        self.write([call(40000)] + three + [bash("cat <<'EOF' > HANDOFF.md\n# x\nEOF"), call(50000)])
        self.assertIsNone(self.run_auto(extra_env=off))
        self.write([call(40000)] + three + [bash("cat HANDOFF.md"), call(50000)])
        self.assertIn("파일 3개를 고쳤다", self.run_auto(sid="read", extra_env=off)["reason"])
        self.write([call(40000)] + three + [bash("sed -i '' 's/a/b/' x.py"), call(50000)])  # Bash 쓰기는 F의 파일 수에 더하지 않는다
        self.assertIn("파일 3개를 고쳤다", self.run_auto(sid="sed", extra_env=off)["reason"])

    def test_new_session_would_start_almost_as_large(self):
        # split_sim.split_dollars와 같은 조건: 마지막 맥락이 첫 호출 + 2만 4천(인계서 4천 + 여유 2만)을 넘어야 묻는다
        self.write([call(240000), WORK, call(264000)])
        self.assertIsNone(self.run_auto())
        self.write([call(240000), WORK, call(264000), call(265000)])
        self.assertIn("25만 토큰을 넘었다(24만 → 26만 5천 토큰)", self.run_auto()["reason"])
        self.write([call(40000), WORK, call(64000)])  # 배수 규칙에도 같다(1.6배지만 첫 + 2만 4천 이하)
        self.assertIsNone(self.run_auto(sid="r", extra_env={"BATON_SPLIT_RATIOS": "1.2"}))
        self.write([call(40000), WORK, call(64000), call(65000)])
        self.assertIn("1.2배 넘게 커졌다", self.run_auto(sid="r", extra_env={"BATON_SPLIT_RATIOS": "1.2"})["reason"])

    def test_delegation_and_bash_writes_count_as_work(self):
        # 리뷰 11-25: 편집 도구만 세면 위임(Agent·Task)이나 Bash로 한 일 뒤에도 묻지 않았다. Bash로 쓴 인계서는 인계서 쓰기다
        def tool(name, **inp):
            return json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]}})
        for i, work in enumerate((tool("Agent", prompt="x"), tool("Task", prompt="x"), tool("Bash", command="sed -i '' 's/a/b/' f.py"),
                                  tool("Bash", command="python3 gen.py > out.json"), tool("Bash", command="git mv a.py b.py"))):
            with self.subTest(i=i):
                self.write([call(40000), work, call(260000)])
                self.assertEqual(self.run_auto(sid=f"w{i}")["decision"], "block")
        for i, quiet in enumerate((tool("Bash", command="awk '$1>3' f.txt; git log --oneline -3"),
                                   tool("Bash", command="python3 x.py > /tmp/out.txt 2>&1"), tool("Read", file_path="/r/a.py"),
                                   tool("Bash", command="cp a.py b.py; cat <<'EOF' > HANDOFF.md\n# x\nEOF"))):
            with self.subTest(quiet=i):
                self.write([call(40000), quiet, call(260000)])
                self.assertIsNone(self.run_auto(sid=f"q{i}"))
        sub = json.dumps({"type": "assistant", "isSidechain": True,
                          "message": {"content": [{"type": "tool_use", "name": "Edit", "input": {"file_path": "/r/a.py"}}]}})
        self.write([call(40000), sub, call(260000)])  # 위임 안의 편집 줄 자체는 세지 않는다 — 메인 스레드의 Agent 호출로 센다
        self.assertIsNone(self.run_auto(sid="side"))

    def test_foreign_handoff_and_auto_off_fall_back_to_notice(self):
        self.write([call(40000), WORK, call(260000)])
        with open(os.path.join(self.root, "HANDOFF.md"), "w", encoding="utf-8") as f:
            f.write("# Project notes\n## Goal\n- ship\n")
        out = self.run_auto()
        self.assertEqual(set(out), {"systemMessage"})
        self.assertTrue(out["systemMessage"].startswith("[baton] 대화가 25만 토큰을 넘었어요(4만 → 26만 토큰).\n만든 사람의 기록으로"))
        self.assertEqual((self.events()[-1]["mode"], self.events()[-1]["fallback"]), ("notice", "foreign_handoff"))
        os.remove(os.path.join(self.root, "HANDOFF.md"))
        self.assertEqual(set(self.run_auto(sid="off", extra_env={"BATON_HANDOFF_AUTO": "off"})), {"systemMessage"})
        self.assertIsNone(self.run_auto(sid="no", extra_env={"BATON_SPLIT_NOTICE": "off"}))  # 맥락 알림을 끄면 아무것도 없다

    def test_both_reasons_in_one_stop_ask_once(self):
        r = self.root
        self.write([call(40000), edit(f"{r}/a.py"), edit(f"{r}/b.py"), edit(f"{r}/c.py"), call(260000)])
        out = self.run_auto()
        self.assertEqual(set(out), {"decision", "reason"})  # 묻기는 하나
        reason = out["reason"]
        self.assertTrue(reason.startswith("[baton] 이 세션에서 인계서(HANDOFF.md·HANDOFF_*.md)를 마지막으로 쓴 뒤 파일 3개를 고쳤다: "
                                          "a.py, b.py, c.py. 이 대화의 맥락이 25만 토큰을 넘었다(4만 → 26만 토큰)."), reason)
        self.assertEqual(reason.count("그다음 사용자에게 이 한 줄만 쓰고"), 1)
        self.assertIsNone(self.run_auto())  # 두 까닭 모두 상태가 남았다
        self.assertEqual(sorted(e["event"] for e in self.events()), ["handoff_auto", "split_notice"])
        off = self.run_auto(sid="o", extra_env={"BATON_HANDOFF_AUTO": "off"})  # 못 물으면 알림 하나에 둘 다
        self.assertEqual(set(off), {"systemMessage"})
        self.assertIn("25만 토큰을 넘었어요", off["systemMessage"])
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
                    call(260000)])
        both = self.run_auto(sid="b")  # 맥락도 넘으면 한 번에 둘 다 묻는다
        self.assertEqual(set(both), {"decision", "reason"})
        self.assertIn("25만 토큰을 넘었다", both["reason"])
        self.assertEqual([e["mode"] for e in self.events() if e["event"] == "split_notice"], ["ask"])

    def test_registered_split_notice_script_prints_nothing(self):
        self.write([call(40000), WORK, call(260000), call(460000)])
        r = subprocess.run([sys.executable, SPLIT], input=json.dumps({"transcript_path": self.transcript, "session_id": "s1",
                                                                     "hook_event_name": "Stop"}),
                           text=True, capture_output=True, env=dict(os.environ, XDG_CACHE_HOME=os.path.join(self.root, "c")))
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))  # 두 번 묻지 않게 — 결정은 handoff-check.py


if __name__ == "__main__":
    unittest.main()
