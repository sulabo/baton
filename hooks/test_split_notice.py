#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(__file__)
HOOK = os.path.join(HERE, "split-notice.py")


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
        env.pop("BATON_SPLIT_NOTICE", None)
        env.pop("BATON_SPLIT_RATIOS", None)
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

    def test_each_band_notifies_once(self):
        self.write([call(40000), call(85000)])
        first = self.message(self.run_hook())
        self.assertEqual(first, "[baton] 대화가 처음보다 2배 길어졌어요(4만 → 8만 5천 토큰).\n"
                                "하던 일이 끝났다면 새 대화로 넘어가 보세요. 지난 대화로 계산해 보면 비용을 35~45% 아낄 수 있어요.\n"
                                "넘어가는 법: \"인계서 써 줘\" → /clear → \"이어서\"\n"
                                "이 알림은 한 번만 나와요.")
        self.assertIsNone(self.message(self.run_hook()))  # 같은 문턱 다시 안 울림

        self.write([call(40000), call(85000), call(130000)])
        third = self.message(self.run_hook())
        self.assertEqual(third, "[baton] 대화가 처음보다 3배 길어졌어요(4만 → 13만 토큰).\n"
                                "하던 일이 끝났다면 새 대화로 넘어가 보세요. 지난 대화로 계산해 보면 비용을 30~34% 아낄 수 있어요.\n"
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
        self.assertTrue(msg.startswith("[baton] 대화가 처음보다 1.5배 길어졌어요(4만 → 9만 토큰).\n"), msg)
        self.assertNotIn("아낄 수 있어요", msg)  # 1.5배는 재계산한 적이 없다 — 절감 몫을 말하지 않는다

    def test_bad_input_fails_open(self):
        for stdin in ("", "not json", "[]", json.dumps({"transcript_path": "/없는/경로.jsonl", "session_id": "x"})):
            result = self.run_hook(raw_stdin=stdin)
            self.assertEqual(result.returncode, 0, stdin)
            self.assertEqual(result.stdout, "", stdin)

    def test_english_notice(self):
        self.write([call(40000), call(85000)])
        msg = self.message(self.run_hook(extra_env={"BATON_LANG": "en"}))
        self.assertEqual(msg, "[baton] This conversation is now 2× as long as at the start (40K → 85K tokens).\n"
                              "If you're done with the current task, try moving to a new conversation. Based on past "
                              "conversations, that can save 35–45% of the cost.\n"
                              "To move: \"write a handoff\" → /clear → \"where were we\"\n"
                              "You'll see this notice only once.")
        self.write([call(40000), call(85000), call(130000)])
        third = self.message(self.run_hook(extra_env={"BATON_LANG": "en"}))
        self.assertTrue(third.startswith("[baton] This conversation is now 3× as long as at the start (40K → 130K tokens).\n"))
        self.assertIn("that can save 30–34% of the cost.", third)
        self.write([call(40000), call(85000), call(130000), call(170000)])
        self.assertNotIn("save", self.message(self.run_hook(sid="en4", extra_env={"BATON_LANG": "en", "BATON_SPLIT_RATIOS": "4"})))

    def test_korean_token_counts(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("split_notice", HOOK)
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        for n, want in ((85312, "8만 5천"), (172480, "17만 2천"), (40000, "4만"), (9500, "9천"), (999, "999"),
                        (1234567, "123만 4천"), (100000, "10만")):
            self.assertEqual(mod.man(n), want)

    def test_locale_decides_without_baton_lang(self):
        self.write([call(40000), call(90000)])
        drop = ("BATON_LANG", "LC_ALL", "LC_MESSAGES")
        self.assertIn("대화가 처음보다 2배 길어졌어요", self.message(self.run_hook(sid="k", extra_env={"LANG": "ko_KR.UTF-8"}, unset=drop)))
        self.assertIn("2× as long as at the start", self.message(self.run_hook(sid="e", extra_env={"LANG": "C.UTF-8"}, unset=drop)))

    def test_non_claude_transcript_is_silent(self):
        # Codex 기록 모양(type=response_item)에는 맥락 정보가 없어 아무것도 내지 않는다
        lines = [json.dumps({"type": "response_item", "payload": {"type": "message", "role": "assistant"}})] * 3
        self.write(lines)
        self.assertIsNone(self.message(self.run_hook()))


if __name__ == "__main__":
    unittest.main()
