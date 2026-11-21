#!/usr/bin/env python3
"""zero-guard.sh: 검사 스크립트를 '실행'했고 그 출력에 0건 신호가 있을 때만 상기시킨다.

2026-11-21 baton 자기 개념 지도 작업: 스크립트 이름과 '없음'이 입력 어디에든 같이 있으면 울려서,
`cat lib/fresh.sh`·`grep ... fresh.sh` 같은 읽기 호출 대부분에서 알림이 떴다.
"""
import json
import os
import subprocess
import unittest

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zero-guard.sh")


def run(command, stdout="", stderr="", response=None):
    data = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": command},
            "tool_response": response if response is not None else {"stdout": stdout, "stderr": stderr}}
    r = subprocess.run(["bash", HOOK], input=json.dumps(data, ensure_ascii=False), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout) if r.stdout.strip() else None


class ZeroGuardTest(unittest.TestCase):
    def test_reading_the_script_is_silent(self):
        self.assertIsNone(run("cat lib/fresh.sh", stdout='case "$files" in *없음*) ... 0건'))

    def test_grepping_for_the_script_is_silent(self):
        self.assertIsNone(run("grep -n fresh.sh README.md", stdout="README.md:3: /drift 의존 없음"))

    def test_script_name_only_in_output_is_silent(self):
        self.assertIsNone(run("ls lib", stdout="check.sh\nfresh.sh\n없음"))

    def test_running_fresh_with_zero_fires(self):
        out = run('bash lib/fresh.sh "$PWD/CONCEPTS.md" "$PWD"', stdout="결정·지침 변동: … 이후 커밋 0건\n")
        self.assertIn("0건", out["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PostToolUse")

    def test_running_via_plugin_root_and_chain_fires(self):
        cmd = 'cd repo && "$CLAUDE_PLUGIN_ROOT/lib/check.sh" CONCEPTS.md | tail -3'
        self.assertIsNotNone(run(cmd, stdout="지적 총 0건"))

    def test_running_with_nonzero_output_is_silent(self):
        self.assertIsNone(run("bash lib/promote.sh . 8", stdout="[A] 반복 실패\n    → 2건\n"))

    def test_zero_only_in_command_text_is_silent(self):
        self.assertIsNone(run("bash lib/fresh.sh CONCEPTS.md # 0건이면 끝", stdout="요약: 재확인 2 · 신선 3"))

    def test_string_tool_response(self):  # 응답이 문자열인 형식(Codex 등)도 읽는다
        self.assertIsNotNone(run("lib/check.sh CONCEPTS.md", response="지적 총 0건"))

    def test_wrappers_that_the_old_hook_caught(self):  # PR #11 리뷰: 이 PR에서 놓치게 된 실행 형태
        for cmd in ('timeout 60 bash lib/fresh.sh CONCEPTS.md .', "sudo -u x lib/check.sh CONCEPTS.md",
                    'bash -c "lib/fresh.sh CONCEPTS.md ."', "rtk bash lib/fresh.sh CONCEPTS.md .",
                    "bash -o pipefail lib/fresh.sh CONCEPTS.md .", "rtk proxy lib/check.sh CONCEPTS.md",
                    "nice -n 5 lib/promote.sh . 8", "env -u FOO X=1 bash -lc 'cd r && lib/check.sh m'"):
            with self.subTest(cmd=cmd):
                self.assertIsNotNone(run(cmd, stdout="지적 총 0건"))

    def test_readers_stay_silent_even_wrapped(self):
        for cmd in ("timeout 5 cat lib/fresh.sh", 'bash -c "grep -n x lib/check.sh"', "rtk grep 0건 lib/fresh.sh"):
            with self.subTest(cmd=cmd):
                self.assertIsNone(run(cmd, stdout="0건 없음"))

    def test_summary_line_with_zero_rechecks_fires(self):  # fresh.sh 요약 줄
        self.assertIsNotNone(run("bash lib/fresh.sh CONCEPTS.md .", stdout="요약: 재확인 0 · 신선 3 · 규칙 개념 0"))

    def test_bad_input_is_silent(self):
        r = subprocess.run(["bash", HOOK], input="not json", capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
