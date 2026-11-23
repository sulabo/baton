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


KO_MSG = "[baton] 0건이 나왔다. 진짜 없는 것인지, 형식이 안 맞아 못 센 것인지 구분해서 보고한다. 형식 불일치 줄을 먼저 확인한다."
EN_MSG = ("[baton] The output has a zero count. Before you report it, tell whether there really is nothing or whether nothing "
          "could be counted because the format did not match. Check the lines that did not match the format first.")
LOCALE = ("BATON_LANG", "LC_ALL", "LC_MESSAGES", "LANG")


def run(command, stdout="", stderr="", response=None, env=None):
    """env: 알림 언어를 정하는 환경변수(기본 BATON_LANG=ko — 기존 테스트는 한국어 알림을 본다)."""
    data = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": command},
            "tool_response": response if response is not None else {"stdout": stdout, "stderr": stderr}}
    e = {k: v for k, v in os.environ.items() if k not in LOCALE}
    e["XDG_CONFIG_HOME"] = os.path.join(os.devnull, "none")  # 실제 설정 파일의 BATON_LANG을 읽지 않는다
    e.update(env if env is not None else {"BATON_LANG": "ko"})
    r = subprocess.run(["bash", HOOK], input=json.dumps(data, ensure_ascii=False), capture_output=True, text=True, env=e)
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

    def test_sourced_scripts_fire(self):  # PR #11 재검증: '. lib/fresh.sh'·'source lib/fresh.sh'
        for cmd in (". lib/fresh.sh CONCEPTS.md .", "source lib/fresh.sh CONCEPTS.md .",
                    "find . -name CONCEPTS.md | xargs lib/check.sh", "printf '%s' CONCEPTS.md | xargs -0 -n1 bash lib/check.sh",
                    "ls | xargs -I{} sh -c 'lib/fresh.sh {} .'"):
            with self.subTest(cmd=cmd):
                self.assertIsNotNone(run(cmd, stdout="지적 총 0건"))

    def test_sourcing_other_files_is_silent(self):
        self.assertIsNone(run(". ./env.sh && cat lib/fresh.sh", stdout="없음"))

    def test_english_zero_signals_fire(self):  # 검사 스크립트의 영어 출력(BATON_LANG=en)
        for out in ("Total findings: 0", "    No findings", "Summary: re-check 0 · fresh 3 · rule concepts 0",
                    "    12 concepts, 0 metadata lines", "     D3: not mentioned in the concept map — check which concept it touches",
                    "1    lives     agrees          needs a re-check — no baseline",
                    "Related entries ... — **this is not 0, they could not be counted**:",
                    "    ── Without a marker: 0 (usually notes on finished work)", "    → 0 items", "    → 0 dropped in total.",
                    "    The latest version has no section — this signal cannot be counted (not 0: uncounted)"):
            with self.subTest(out=out):
                self.assertIsNotNone(run("bash lib/fresh.sh CONCEPTS.md .", stdout=out))

    def test_english_nonzero_output_is_silent(self):
        for out in ("Summary: re-check 2 · fresh 3 · rule concepts 0", "Total findings: 10", "    → 2 items",
                    "    12 concepts, 12 metadata lines", "Total findings: 3", "    ── Without a marker: 3",
                    "checked at 2026-11-23 10:05 (`9cd1928`)", "    References: 26 · one way only: 0.5"):
            with self.subTest(out=out):
                self.assertIsNone(run("bash lib/check.sh CONCEPTS.md", stdout=out))

    def test_message_language(self):
        out = run("bash lib/check.sh CONCEPTS.md", stdout="지적 총 0건")
        self.assertEqual((out["systemMessage"], out["hookSpecificOutput"]["additionalContext"]), (KO_MSG, KO_MSG))
        for stdout in ("지적 총 0건", "Total findings: 0"):  # 출력 언어와 알림 언어는 따로다
            out = run("bash lib/check.sh CONCEPTS.md", stdout=stdout, env={"BATON_LANG": "en"})
            self.assertEqual((out["systemMessage"], out["hookSpecificOutput"]["additionalContext"]), (EN_MSG, EN_MSG))

    def test_locale_decides_without_baton_lang(self):
        self.assertEqual(run("lib/check.sh m", stdout="Total findings: 0", env={"LANG": "ko_KR.UTF-8"})["systemMessage"], KO_MSG)
        self.assertEqual(run("lib/check.sh m", stdout="Total findings: 0", env={"LANG": "C.UTF-8"})["systemMessage"], EN_MSG)

    def test_bad_input_is_silent(self):
        r = subprocess.run(["bash", HOOK], input="not json", capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
