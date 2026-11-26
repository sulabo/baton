#!/usr/bin/env python3
"""zero-guard.sh: 검사 스크립트를 '실행'했고 그 출력에 0건 신호가 있을 때만 상기시킨다.

2026-11-21 baton 자기 개념 지도 작업: 스크립트 이름과 '없음'이 입력 어디에든 같이 있으면 울려서,
`cat lib/fresh.sh`·`grep ... fresh.sh` 같은 읽기 호출 대부분에서 알림이 떴다.
"""
import json
import os
import subprocess
import tempfile
import unittest

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zero-guard.sh")


# 모델에게(additionalContext): 지시. 사용자에게(systemMessage): 무슨 일인지
KO_MSG = "[baton] 0건이 나왔다. 진짜 없는 것인지, 형식이 안 맞아 못 센 것인지 구분해서 보고한다. 형식 불일치 줄을 먼저 확인한다."
EN_MSG = ("[baton] The output has a zero count. Before you report it, tell whether there really is nothing or whether nothing "
          "could be counted because the format did not match. Check the lines that did not match the format first.")
KO_USER = "[baton] 결과가 0이에요. 정말 없는 건지, 형식이 달라 못 센 건지 AI가 확인하게 했어요."
EN_USER = ("[baton] The result is 0. baton asked the AI to check whether there's really nothing or a different format kept it "
           "from counting.")
LOCALE = ("BATON_LANG", "LC_ALL", "LC_MESSAGES", "LANG")


def run(command, stdout="", stderr="", response=None, env=None, cwd=None):
    """env: 알림 언어를 정하는 환경변수(기본 BATON_LANG=ko — 기존 테스트는 한국어 알림을 본다)."""
    data = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": command},
            "tool_response": response if response is not None else {"stdout": stdout, "stderr": stderr}}
    e = {k: v for k, v in os.environ.items() if k not in LOCALE}
    e["XDG_CONFIG_HOME"] = os.path.join(os.devnull, "none")  # 실제 설정 파일의 BATON_LANG을 읽지 않는다
    e.update(env if env is not None else {"BATON_LANG": "ko"})
    r = subprocess.run(["bash", HOOK], input=json.dumps(data, ensure_ascii=False), capture_output=True, text=True, env=e,
                       cwd=cwd)
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

    def test_only_scripts_in_a_lib_folder_fire(self):
        # 1.0.3: 플러그인의 검사 스크립트는 <플러그인 루트>/lib/에 있다 — 저장소 자기 check.sh가 낸 "Errors: 0"에는 울리지 않는다
        for cmd in ("./check.sh", "bash scripts/check.sh --all", "check.sh", "sh tools/fresh.sh", "cd lib && ./promote.sh"):
            with self.subTest(cmd=cmd):
                self.assertIsNone(run(cmd, stdout="Errors: 0"))
        for cmd in ("bash /opt/plugins/baton/1.0.3/lib/fresh.sh CONCEPTS.md .", 'bash "$CLAUDE_PLUGIN_ROOT"/lib/check.sh m',
                    "L=/opt/baton/lib; bash $L/fresh.sh CONCEPTS.md .", 'bash "${B}/check.sh" m'):
            with self.subTest(cmd=cmd):  # 폴더가 변수 하나면 값을 모른다 — 실행으로 본다
                self.assertIsNotNone(run(cmd, stdout="지적 총 0건"))

    def test_sourcing_other_files_is_silent(self):
        self.assertIsNone(run(". ./env.sh && cat lib/fresh.sh", stdout="없음"))

    def test_english_zero_signals_fire(self):  # 검사 스크립트의 영어 출력(BATON_LANG=en)
        for out in ("Total findings: 0", "    No findings", "Summary: re-check 0 · fresh 3 · rule concepts 0",
                    "    Concepts: 12 · metadata lines: 0", "No metadata lines at all (3 concepts).",
                    "Decision and instruction changes: 0 commits since the oldest check (abc1234)",
                    "Related entries ... — **this is not 0, they could not be counted**:",
                    "    ── Without a marker: 0 (usually notes on finished work)", "    → 0 found", "    → 0 dropped in total.",
                    "    The latest version has no 'Verified facts and decisions' section — this signal cannot be counted "
                    "(not 0: uncounted)", "    (no rejected list)",
                    "  Format: dated headings · new decisions 0 · Related: lines 0 · gaps 0",
                    "  Format: table (decision IDs) · new decision rows 0",
                    "No metadata lines at all (concepts: 3). **Freshness can't be computed — this is not 0, it could not be counted.**",
                    "    No findings (evidence paths: 0, all tracked relative to the repo root)"):
            with self.subTest(out=out):
                self.assertIsNotNone(run("bash lib/fresh.sh CONCEPTS.md .", stdout=out))

    def test_english_nonzero_output_is_silent(self):
        for out in ("Summary: re-check 2 · fresh 3 · rule concepts 0", "Total findings: 10", "    → 2 found",
                    "  Format: dated headings · new decisions 0 · gaps 0\nSummary: re-check 3 · fresh 1 · rule concepts 0",
                    "  형식: 날짜 헤딩 · 새 결정 0건 · 구멍 0건\n요약: 재확인 3 · 신선 1 · 규칙 개념 0",
                    "    Concepts: 12 · metadata lines: 12", "Total findings: 3", "    ── Without a marker: 3",
                    "checked at 2026-11-23 10:05 (`9cd1928`)", "    References: 26 · one way only: 0"):
            with self.subTest(out=out):
                self.assertIsNone(run("bash lib/check.sh CONCEPTS.md", stdout=out))

    def test_zero_beside_a_nonzero_result_is_silent(self):
        # 2026-11-23: 재확인 14건인 fresh.sh 출력에서 울렸다 — 표의 개념 이름("0건과 못 셈의 구분")과 부분 수("커밋 0건")에 걸렸다.
        # 머리 결과(재확인 수·지적 총수)가 0이 아니면 나머지 줄의 0은 세부다
        ko = ("#    개념   상태   판정\n2    0건과 못 셈의 구분   해소됨   신선\n3    점수   일치   재확인 필요 — 커밋 1건\n\n"
              "요약: 재확인 14 · 신선 1 · 규칙 개념 0\n결정·지침 변동: 가장 오래된 확인(c1f68c2) 이후 커밋 0건\n")
        en = ("#    Concept   Status   Verdict\n2    zero vs none: 0 items   resolved   fresh\n\n"
              "Summary: re-check 14 · fresh 1 · rule concepts 0\n"
              "Decision and instruction changes: 0 commits since the oldest check (abc1234)\n")
        for out in (ko, en):
            with self.subTest(out=out[:40]):
                self.assertIsNone(run("bash lib/fresh.sh CONCEPTS.md .", stdout=out))
        for out in ("[4] 닫힌 상태 어휘 밖의 말을 쓰는가\n    지적 없음 (7종 확인)\n\n지적 총 3건",
                    "[4] Status words outside the closed list\n    No findings (7 kinds checked)\n\nTotal findings: 3"):
            with self.subTest(out=out[-16:]):
                self.assertIsNone(run("bash lib/check.sh CONCEPTS.md", stdout=out))
        for out in ("    참조 26건 · 한쪽만 0건", "    References: 26 · one way only: 0"):  # 머리 줄이 없을 때: 여러 수 요약 줄의 0
            with self.subTest(out=out):
                self.assertIsNone(run("bash lib/promote.sh . 8", stdout=out))

    def test_promote_brief_counted_zero_is_silent_uncounted_fires(self):
        # promote.sh --brief(11-25)의 끝 줄은 " · " 옆에 검토 일수를 둔다 — 다 셌는데 0이면 다시 묻지 않는다(다시 부르는 호출을 줄이려고)
        cmd = "${CLAUDE_PLUGIN_ROOT}/lib/promote.sh --brief .; git status --short --branch"
        for out in ("승격 검토(요약) · 검토 3일 · 반복 실패 0건 · 탈락 0건(결정 표지 0건) · 기각 목록 0개\n  올릴 것 없음 · 검토 3일 모두 셈",
                    "Promotion review (brief) · 3 days reviewed · repeated failures: 0 · dropped: 0 (0 with a decision marker) · "
                    "rejected list: 0\n  Nothing to promote · all 3 days counted"):
            with self.subTest(out=out[-12:]):
                self.assertIsNone(run(cmd, stdout=out))
        self.assertIsNone(run(cmd, stdout="승격 검토(요약) · 검토 2일 · 반복 실패 0건 · 탈락 0건(결정 표지 0건) · 기각 목록 0개\n"
                                           "  올릴 것 없음 · 검토 2일 — 3일이 안 돼 후보가 아직 나올 수 없다"))
        self.assertIsNotNone(run(cmd, stdout="승격 검토(요약) · 검토 3일 · 반복 실패 0건 · 탈락 0건(결정 표지 0건) · 기각 목록 0개\n"
                                              "  못 셈: 반복 실패 형식 불일치 판 3개 — 0건이 아니라 못 셈\n"
                                              "  찾은 후보 없음 — 위의 못 센 판 때문에 '없음'이 아니다"))
        self.assertIsNotNone(run(cmd, stdout="승격 검토(요약) · 검토 0일 · 반복 실패 0건 · 탈락 못 셈 · 기각 목록 0개\n"
                                              "  못 셈: 최신판에 '확인된 사실과 결정' 절 없음 — 0건이 아니라 못 셈"))

    def test_git_log_titles_in_the_same_call_do_not_fire(self):
        # 스킬의 한 호출(promote --brief; git status; git log --oneline): 커밋 제목의 "없음"·"0건"·"못 셈"에는 울리지 않는다
        cmd = "${CLAUDE_PLUGIN_ROOT}/lib/promote.sh --brief .; git status --short --branch; git log --oneline -3"
        out = ("승격 검토(요약) · 검토 3일 · 반복 실패 0건 · 탈락 0건(결정 표지 0건) · 기각 목록 0개\n  올릴 것 없음 · 검토 3일 모두 셈\n"
               "## main...origin/main\n M lib/a.py\n"
               "6abf18b handoff: 승격 후보 없음\n7ccabe6 fix: 0건 알림\n1388afd zero-guard: 0건이 아니라 못 셈 구분\n")
        self.assertIsNone(run(cmd, stdout=out))
        uncounted = out.replace("  올릴 것 없음 · 검토 3일 모두 셈\n", "  못 셈: 반복 실패 형식 불일치 판 3개 — 0건이 아니라 못 셈\n")
        self.assertIsNotNone(run(cmd, stdout=uncounted))  # promote 자기 줄의 못 셈은 그대로 울린다

    def test_none_word_beside_a_nonzero_count_is_silent(self):
        # 11-25 실사용: "지적 1건: 정본 없음"(1건을 찾았고, 그 내용이 "정본 없음")에 울렸다. 0이 아닌 수가 있는 칸의 맨 "없음"은 0이 아니다
        for out in ("지적 1건: 정본 없음", "  지적 2건 — 근거 파일 없음 · 끊긴 참조 없음", "[3] 정본 없음"):
            with self.subTest(out=out):
                self.assertIsNone(run("bash lib/check.sh CONCEPTS.md", stdout=out))
        for out in ("지적 0건: 정본 없음", "정본 없음", "  지적 없음 · 0건", "    지적 없음 (7종 확인)"):  # 0 신호, 앞에 수 없는 "없음"은 그대로
            with self.subTest(out=out):
                self.assertIsNotNone(run("bash lib/check.sh CONCEPTS.md", stdout=out))

    def test_real_zero_result_still_fires(self):
        for out in ("2    0건과 못 셈의 구분   해소됨   신선\n요약: 재확인 0 · 신선 15 · 규칙 개념 0",
                    "2    zero vs none   resolved   fresh\nSummary: re-check 0 · fresh 15 · rule concepts 0",
                    "    지적 없음\n\n지적 총 0건", "    No findings\n\nTotal findings: 0",
                    "    참조 0건 · 한쪽만 0건", "    References: 0 · one way only: 0"):
            with self.subTest(out=out[-24:]):
                self.assertIsNotNone(run("bash lib/fresh.sh CONCEPTS.md .", stdout=out))
        # 못 셈 신호는 머리 결과가 0이 아니어도 울린다
        for out in ("[6] 메타 줄 (신선도 계산의 전제)\n    개념 15개 중 메타 줄 0개\n\n지적 총 2건",
                    "[6] Metadata lines (needed to compute freshness)\n    Concepts: 3 · metadata lines: 0\n\nTotal findings: 2",
                    "No metadata lines at all (3 concepts). Freshness can't be computed.",
                    "요약: 재확인 4 · 신선 1 · 규칙 개념 0\n새 결정의 '관련' 중 개념 절과 못 이은 것 — **0건이 아니라 못 셌다**:"):
            with self.subTest(out=out[-24:]):
                self.assertIsNotNone(run("bash lib/check.sh CONCEPTS.md", stdout=out))

    def test_message_language(self):
        out = run("bash lib/check.sh CONCEPTS.md", stdout="지적 총 0건")
        self.assertEqual((out["systemMessage"], out["hookSpecificOutput"]["additionalContext"]), (KO_USER, KO_MSG))
        for stdout in ("지적 총 0건", "Total findings: 0"):  # 출력 언어와 알림 언어는 따로다
            out = run("bash lib/check.sh CONCEPTS.md", stdout=stdout, env={"BATON_LANG": "en"})
            self.assertEqual((out["systemMessage"], out["hookSpecificOutput"]["additionalContext"]), (EN_USER, EN_MSG))

    def test_locale_decides_without_baton_lang(self):
        self.assertEqual(run("lib/check.sh m", stdout="Total findings: 0", env={"LANG": "ko_KR.UTF-8"})["systemMessage"], KO_USER)
        self.assertEqual(run("lib/check.sh m", stdout="Total findings: 0", env={"LANG": "C.UTF-8"})["systemMessage"], EN_USER)

    def test_repo_modules_are_not_imported(self):
        # 훅은 사용자 저장소에서 돈다. 그곳의 copy.py(config가 부른다)·json.py가 표준 모듈 대신 불리면 안 된다(python3 -I)
        with tempfile.TemporaryDirectory() as d:
            mark = os.path.join(d, "imported")
            for name in ("copy", "json", "re", "i18n", "config"):
                with open(os.path.join(d, name + ".py"), "w", encoding="utf-8") as f:
                    f.write(f"open({mark!r}, 'a').write({name!r} + '\\n')\nraise ImportError('planted')\n")
            out = run("bash lib/check.sh CONCEPTS.md", stdout="지적 총 0건", env={"BATON_LANG": "en"}, cwd=d)
            self.assertEqual(out["systemMessage"], EN_USER)
            self.assertFalse(os.path.exists(mark), open(mark).read() if os.path.exists(mark) else "")

    def test_bad_input_is_silent(self):
        r = subprocess.run(["bash", HOOK], input="not json", capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
