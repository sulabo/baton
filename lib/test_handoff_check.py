#!/usr/bin/env python3
"""북극성 길 단계 3: 인계서 검사기. 템플릿대로 쓴 인계서는 통과하고, 어긴 곳은 줄 번호와 종류로 잡는다."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import handoff_check


_CFG = tempfile.TemporaryDirectory()  # 실제 설정 파일(~/.config/baton/config.json)을 읽지 않는다 — 훅 자식 프로세스도 이 환경을 물려받는다
# 한국어 메시지를 보는 테스트는 BATON_LANG=ko로 고정한다(로캘과 무관하게). 영어 테스트는 각자 en으로 덮는다
_CFG_ENV = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": _CFG.name, "BATON_LANG": "ko"})


def setUpModule():
    _CFG_ENV.start()


def tearDownModule():
    _CFG_ENV.stop(); _CFG.cleanup()

GOOD = """# Session Handoff (작성: 2026-10-01)

## 목표와 완료 조건
- 목표: 검사기

## 확인된 사실과 결정
- 없음

## 관련 파일·심볼
- `lib/handoff_check.py`

## 이미 한 변경
- 없음

## 실패한 접근법 (다시 시도 금지)
- 없음

## 검증 증거
- 명령: python3 -m unittest

## 남은 리스크와 다음 행동
- 다음 행동: 설치

## 승격 후보 (DECISIONS.md로 올릴 것)
- 없음
"""


class HandoffCheckTest(unittest.TestCase):
    def test_template_passes(self):
        self.assertEqual(handoff_check.check(GOOD), [])

    def test_repo_handoff_passes(self):
        # 저장소에 실제로 올라간 인계서가 검사기와 어긋나면 둘 중 하나가 틀렸다
        path = os.path.join(os.path.dirname(HERE), "HANDOFF.md")
        if not os.path.isfile(path):
            self.skipTest("HANDOFF.md 없음")
        self.assertEqual(handoff_check.check_file(path), [])

    def test_section_variants_accepted(self):
        text = GOOD.replace("## 실패한 접근법 (다시 시도 금지)", "## E. 실패한 접근법")
        self.assertEqual(handoff_check.check(text), [])

    def test_missing_sections_named(self):
        text = GOOD.replace("## 검증 증거", "## 메모").replace("## 승격 후보 (DECISIONS.md로 올릴 것)", "## 기타")
        out = handoff_check.check(text)
        self.assertEqual(len(out), 1)
        self.assertIn("검증 증거", out[0])
        self.assertIn("승격 후보", out[0])

    def test_line_and_char_limits(self):
        self.assertTrue(any("201줄" in x for x in handoff_check.check(GOOD + "-\n" * (201 - GOOD.count("\n")))))
        over = GOOD + "가" * (handoff_check.MAX_CHARS + 1 - len(GOOD))
        self.assertTrue(any(f"상한 {handoff_check.MAX_CHARS:,}자" in x for x in handoff_check.check(over)))
        self.assertFalse(any("자 — 상한" in x for x in handoff_check.check(over[:-1])))

    def test_long_code_block(self):
        block = "```\n" + "x\n" * 25 + "```\n"
        out = handoff_check.check(GOOD + block)
        self.assertTrue(any("코드 블록이 25줄" in x for x in out), out)
        self.assertEqual(handoff_check.check(GOOD + "```\n" + "x\n" * 20 + "```\n"), [])

    def test_diff_detected(self):
        out = handoff_check.check(GOOD + "diff --git a/x b/x\n@@ -1,2 +1,3 @@\n")
        self.assertTrue(any("전체 diff" in x and "2개" in x for x in out), out)

    def test_secrets_reported_without_value(self):
        token = "gh" + "p_" + "A1b2" * 9  # 저장소 비밀 스캐너에 걸리지 않게 실행 중에 만든다
        out = handoff_check.check(GOOD + f"- 토큰 {token}\n- 경로 /Users/someone/x\n- api_key = abcdef123456\n")
        joined = "\n".join(out)
        self.assertIn("API 토큰", joined)
        self.assertIn("홈 절대경로", joined)
        self.assertIn("비밀번호·키 대입", joined)
        self.assertNotIn(token, joined)
        self.assertNotIn("someone", joined)

    def test_tilde_path_and_prose_not_flagged(self):
        self.assertEqual(handoff_check.check(GOOD + "- `~/baton`에서 작업. token 수가 줄었다. password는 없다\n"), [])

    def kinds(self, line):
        return [x for x in handoff_check.check(GOOD + line + "\n") if "의심 값" in x]

    def test_env_var_and_other_secret_formats_caught(self):
        # 리뷰(10-01)에서 빠졌던 형식들. 값은 실행 중에 만든다(저장소 비밀 스캐너 회피)
        v = "Ab3" + "x9Kq" * 3
        for line in [f"DB_PASSWORD={v}", f"export OPENAI_API_KEY={v}", f"client_secret: {v}", f"GITHUB_TOKEN={v}",
                     f"token = {v}", "sk" + "_live_" + "a1B2" * 6, "gl" + "pat-" + "a1B2" * 6,
                     "Bearer eyJ" + "hbGciOiJIUzI1" + ".eyJ" + "zdWIiOiIxMjM0" + ".sig"]:
            self.assertTrue(self.kinds(line), line)

    def test_code_names_branches_and_urls_not_flagged(self):
        for line in ["- api_key = os.environ['X']로 읽도록 바꿨다", "- access_token: refresh_token.py에서 갱신한다",
                     "- 브랜치 sk-feature-handoff-validator-v2", "- 공유 폴더 /Users/Shared/data",
                     "- 문서 https://example.com/home/docs/", "- secret: 환경변수에서 읽는다", "- max_tokens=4096으로 올렸다"]:
            self.assertEqual(handoff_check.check(GOOD + line + "\n"), [], line)

    def test_particles_periods_and_korean_labels(self):
        v = "Ab3" + "x9Kq" * 3
        for line in [f"- DB_PASSWORD={v}로 바꿨다", f"- access_token={v}. 다음 단계", f"- 비밀번호: {v}", f"- token：{v}"]:
            self.assertTrue(self.kinds(line), line)
        self.assertEqual(handoff_check.check(GOOD + "- token=abc123.split()으로 나눈다\n"), [])

    def test_long_lines_stay_fast(self):
        import time
        for line in ["_" * 20000, "가" * 20000, "가_" * 10000, "a_b_c_d_" * 2500]:
            t = time.time(); handoff_check.check(GOOD + line + "\n")
            self.assertLess(time.time() - t, 1.0, line[:10])

    def test_heading_level_and_bold_variants(self):
        text = GOOD.replace("## 이미 한 변경", "#### 이미 한 변경").replace("## 목표와 완료 조건", "## **목표와 완료 조건**")
        self.assertEqual(handoff_check.check(text), [])

    # 경고: 확인된 사실과 결정 절의 [V]·[?] 표시
    def facts(self, body):
        return GOOD.replace("## 확인된 사실과 결정\n- 없음\n", "## 확인된 사실과 결정\n" + body)

    def test_marks_present_silent(self):
        text = self.facts("- [V] 테스트 168개 통과\n- [?] Codex도 같을 것\n  둘째 줄로 이어 쓴 설명\n- 결론 먼저, 근거 뒤 [V]\n")
        self.assertEqual(handoff_check.warnings(text), [])
        self.assertEqual(handoff_check.warnings(GOOD), [])  # "- 없음"은 주장이 아니다
        self.assertEqual(handoff_check.check(text), [])  # 경고는 문제 목록에 섞이지 않는다

    def test_marks_missing_named_by_line(self):
        text = self.facts("- [V] 확인함\n- 기억으로 적음\n1. 번호 목록도 센다\n- 이어 쓴 줄에 표시\n  [?] 여기\n")
        out = handoff_check.warnings(text)
        self.assertEqual(len(out), 1, out)
        lines = text.splitlines()
        missing = [n for n, ln in enumerate(lines, 1) if ln in ("- 기억으로 적음", "1. 번호 목록도 센다")]
        self.assertIn(f"4개 중 2개", out[0])
        self.assertIn(f"({missing[0]}, {missing[1]}줄)", out[0])
        self.assertNotIn("기억으로", out[0])  # 줄 번호와 종류만, 내용은 옮기지 않는다

    def test_section_absent_left_to_section_check(self):
        text = GOOD.replace("## 확인된 사실과 결정\n- 없음\n", "")
        self.assertEqual(handoff_check.warnings(text), [])
        self.assertIn("확인된 사실과 결정", handoff_check.check(text)[0])

    def test_uncountable_format_reported_not_zero(self):
        for body in ["표시 없는 산문 한 문단이다.\n", "| 사실 | 근거 |\n|---|---|\n| a | b |\n", "```\n- [V] 코드 안\n```\n", ""]:
            out = handoff_check.warnings(self.facts(body))
            self.assertEqual(len(out), 1, (body, out))
            self.assertIn("셀 수 없다", out[0])
        out = handoff_check.warnings(self.facts("- [V] 목록\n산문 한 줄\n"))
        self.assertEqual(len(out), 1, out)
        self.assertIn("목록이 아닌 줄 1개", out[0])
        self.assertIn("세지 못했다", out[0])

    def test_untouched_skill_template_warns(self):
        # 템플릿을 고치지 않고 남기면 통과하면 안 된다 — 안내는 주석이라 세지 않고, 빈 "-" 항목이 걸린다. 영어·한국어 템플릿 둘 다
        with open(os.path.join(os.path.dirname(HERE), "skills", "baton", "SKILL.md"), encoding="utf-8") as f:
            skill = f.read()
        templates = [b.split("\n```", 1)[0] for b in skill.split("```markdown\n")[1:]]
        self.assertEqual([t.splitlines()[0] for t in templates],
                         ["# Session Handoff (written: YYYY-MM-DD)", "# Session Handoff (작성: YYYY-MM-DD)"])
        for template in templates:
            out = handoff_check.warnings(template)
            self.assertEqual(len(out), 1, out)
            self.assertIn("1개 중 1개에 [V]·[?] 표시 없음", out[0])
            self.assertFalse(any("필수 절 없음" in x for x in handoff_check.check(template)), template[:40])  # 8절이 다 있다
            en = handoff_check.warnings(template, lang="en")
            self.assertIn("1 of 1 items in the Verified facts and decisions section have no [V]/[?] mark", en[0])
        self.assertEqual(handoff_check.warnings(self.facts("<!-- 안내 -->\n- [V] 확인함\n")), [])

    def unmarked_lines(self, body):
        """경고에 나온 표시 없는 줄 번호들을, 사실 절 안의 상대 줄(1부터)로."""
        text = self.facts(body)
        start = text.splitlines().index("## 확인된 사실과 결정") + 1
        for x in handoff_check.warnings(text):
            if "표시 없음" in x:
                nums = x.split("(", 1)[1].split("줄)", 1)[0]
                return [int(n) - start for n in nums.split(", ")]
        return []

    def test_nested_children_counted_separately(self):
        # 리뷰(11-21): 자식이 부모에 흡수되면 누락을 양쪽 방향으로 놓쳤다
        self.assertEqual(self.unmarked_lines("- [V] 부모\n  - 자식 표시 없음\n"), [2])
        self.assertEqual(self.unmarked_lines("- 부모 표시 없음\n  - [V] 자식\n"), [1])
        self.assertEqual(self.unmarked_lines("- [V] a\n    1. 깊은 자식\n\t- 탭 자식\n  이어 쓴 줄 [?]\n"), [2])

    def test_subsections_stay_inside_facts(self):
        # 리뷰(11-21): ### 하위 절이 있으면 "셀 수 없다"고 잘못 말하고 하위 절의 누락도 놓쳤다
        body = "### 사실\n- [V] a\n### 결정\n- b 표시 없음\n##### 메모\n- [?] c\n"
        out = handoff_check.warnings(self.facts(body))
        self.assertFalse(any("셀 수 없다" in x or "목록이 아닌" in x for x in out), out)
        self.assertEqual(self.unmarked_lines(body), [4])
        # 같은 단계 이상의 제목은 절을 끝낸다
        self.assertEqual(self.unmarked_lines("- [V] a\n# 부록\n- 절 밖\n"), [])

    def test_marks_in_code_or_comment_not_counted(self):
        self.assertEqual(self.unmarked_lines("- `arr[V]` 코드 안 표시\n- 주장 <!-- [V] -->\n- [V] 진짜 `x`\n"), [1, 2])

    def test_fences_and_multiline_comments(self):
        out = handoff_check.warnings(self.facts("- [V] a\n```\n- 코드 속 주장\n```\n"))
        self.assertEqual(len(out), 1, out)
        self.assertIn("목록이 아닌 줄 1개", out[0])  # 여는 fence 줄
        for body in ["<!--\n안내\n-->\n- [V] a\n", "- [V] a\n<!--\n- 옛 주장\n-->\n", "- [V] a <!-- 메모\n- 옛 주장\n-->\n"]:
            self.assertEqual(handoff_check.warnings(self.facts(body)), [], body)

    def test_marks_not_forced_on_other_formats(self):
        other = "# Handoff\n## 확인된 사실\n- 표시 없음\n"
        self.assertEqual(handoff_check.warnings(other, strict=False), [])
        self.assertTrue(handoff_check.warnings(other, strict=True))

    def test_cli_warning_keeps_exit_zero(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "HANDOFF.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write(self.facts("- 표시 없음\n"))
            r = subprocess.run([sys.executable, os.path.join(HERE, "handoff_check.py"), p],
                               capture_output=True, text=True, check=False)
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertIn("경고:", r.stdout)
            self.assertIn("경고만 있음", r.stdout)

    def test_home_path_variants(self):
        for line in ["cd /Users/someone 에서 실행", "/root/.ssh 확인", "C:\\Users\\someone\\x", "- 경로:/Users/someone/x",
                     "- 작업폴더/Users/someone/x", "- file:///Users/someone/x", "d:\\users\\me"]:
            self.assertTrue(any("홈 절대경로" in x for x in self.kinds(line)), line)

    def test_fence_edge_cases(self):
        out = handoff_check.check(GOOD + "```\n" + "x\n" * 50)
        self.assertTrue(any("닫히지 않았다" in x for x in out), out)
        nested = "````\n```\ninner\n```\n" + "x\n" * 25 + "````\n"  # 안쪽 ``` 은 닫는 표지가 아니다
        self.assertTrue(any("코드 블록이 28줄" in x for x in handoff_check.check(GOOD + nested)))

    def test_headings_inside_code_or_loose_matches_do_not_count(self):
        text = GOOD.replace("## 검증 증거", "## 메모") + "```\n## 검증 증거\n```\n"
        self.assertIn("검증 증거", handoff_check.check(text)[0])
        text = GOOD.replace("## 목표와 완료 조건", "## 다음 목표 없음")
        self.assertIn("목표와 완료 조건", handoff_check.check(text)[0])

    def test_private_terms_reported_without_value(self):
        out = handoff_check.check(GOOD + "- 홍길동 님 요청\n- 메일 KIM@corp.io 확인\n- 홍길동 다시\n", private_terms=["홍길동", "kim@corp.io", " "])
        joined = "\n".join(out)
        self.assertIn("개인 자료 목록 단어 2개 발견", joined)
        self.assertIn(f"{GOOD.count(chr(10)) + 1}, {GOOD.count(chr(10)) + 2}, {GOOD.count(chr(10)) + 3}줄", joined)
        self.assertNotIn("홍길동", joined)
        self.assertNotIn("corp.io", joined.lower())
        self.assertEqual(handoff_check.check(GOOD + "- skim 했다\n", private_terms=["kim"]), [])  # 영숫자 사이에 낀 것은 아니다
        self.assertEqual(handoff_check.check(GOOD + "- 홍길동\n"), [])  # 목록이 없으면 검사하지 않는다

    def test_check_file_reads_private_terms_from_config(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "HANDOFF.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write(GOOD + "- 홍길동\n")
            self.assertEqual(handoff_check.check_file(p), [])
            cfg = os.path.join(os.environ["XDG_CONFIG_HOME"], "baton", "config.json")
            os.makedirs(os.path.dirname(cfg), exist_ok=True)
            with open(cfg, "w", encoding="utf-8") as f:
                f.write('{"global": {"private_terms": ["홍길동"]}}')
            self.addCleanup(os.remove, cfg)
            self.assertTrue(any("개인 자료 목록" in x for x in handoff_check.check_file(p)))

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "HANDOFF.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write(GOOD)
            ok = subprocess.run([sys.executable, os.path.join(HERE, "handoff_check.py"), p], capture_output=True, text=True)
            self.assertEqual(ok.returncode, 0, ok.stdout)
            with open(p, "w", encoding="utf-8") as f:
                f.write("# 빈 인계서\n")
            bad = subprocess.run([sys.executable, os.path.join(HERE, "handoff_check.py"), p], capture_output=True, text=True)
            self.assertEqual(bad.returncode, 1)
            self.assertIn("필수 절 없음", bad.stdout)


GOOD_EN = """# Session Handoff (written: 2026-10-01)

## Goal and done criteria
- Goal: checker

## Verified facts and decisions
- None

## Files and symbols
- `lib/handoff_check.py`

## Changes made
- None

## Failed approaches (do not retry)
- None

## Verification evidence
- Command: python3 -m unittest

## Risks and next actions
- Next action: install

## Promotion candidates (to DECISIONS.md)
- None

### Rejected (do not raise again)
- None
"""


class EnglishHandoffTest(unittest.TestCase):
    """영어 템플릿 인계서도 같은 검사를 받고, 메시지는 BATON_LANG을 따른다. 빠진 절 이름은 파일이 쓴 언어로."""

    def setUp(self):
        env = mock.patch.dict(os.environ, {"BATON_LANG": "en"}); env.start(); self.addCleanup(env.stop)

    def facts(self, body):
        return GOOD_EN.replace("## Verified facts and decisions\n- None\n", "## Verified facts and decisions\n" + body)

    def test_english_template_passes_both_languages(self):
        self.assertEqual(handoff_check.check(GOOD_EN), [])
        self.assertEqual(handoff_check.check(GOOD_EN, lang="ko"), [])
        self.assertEqual(handoff_check.warnings(GOOD_EN), [])  # "- None"은 주장이 아니다
        lower = GOOD_EN.replace("## Changes made", "## E. changes made").replace("## Goal and", "## **GOAL and")
        self.assertEqual(handoff_check.check(lower), [])  # 영어 머리말은 대소문자·번호·굵게를 가리지 않는다

    def test_missing_sections_named_in_the_files_language(self):
        text = GOOD_EN.replace("## Verification evidence", "## Notes")
        self.assertEqual(handoff_check.check(text), ["missing required sections: Verification evidence"])
        self.assertEqual(handoff_check.check(text, lang="ko"), ["필수 절 없음: Verification evidence"])  # 틀은 메시지 언어, 이름은 파일 언어
        self.assertEqual(handoff_check.check(GOOD.replace("## 검증 증거", "## 메모")), ["missing required sections: 검증 증거"])
        self.assertEqual(handoff_check.check("# Session Handoff (written: 2026-10-01)\n", lang="ko")[0],
                         "필수 절 없음: Goal and done criteria, Verified facts and decisions, Files and symbols, Changes made, "
                         "Failed approaches, Verification evidence, Risks and next actions, Promotion candidates")
        self.assertIn("목표와 완료 조건", handoff_check.check("# Session Handoff (작성: 2026-10-01)\n")[0])

    def test_problem_messages_in_english(self):
        token = "gh" + "p_" + "A1b2" * 9
        out = handoff_check.check(GOOD_EN + f"- token {token}\n- path /Users/someone/x\n- api_key = abcdef123456\n")
        n = GOOD_EN.count("\n")
        self.assertEqual(out, [f"line {n + 1}: looks like an API token — remove it or write it generically (~/, <key>)",
                               f"line {n + 2}: looks like an absolute home path — remove it or write it generically (~/, <key>)",
                               f"line {n + 3}: looks like a password or key assignment — remove it or write it generically (~/, <key>)"])
        self.assertNotIn(token, "\n".join(out))
        over = GOOD_EN + "a" * (handoff_check.MAX_CHARS + 1 - len(GOOD_EN))
        self.assertIn("8,701 chars — over the 8,700-char limit (the part past it will not be injected into the next session)",
                      handoff_check.check(over))
        self.assertTrue(any(x.startswith("201 lines — over the 200-line limit")
                            for x in handoff_check.check(GOOD_EN + "-\n" * (201 - GOOD_EN.count("\n")))))
        self.assertTrue(any("the code block at line" in x and "has 25 lines" in x
                            for x in handoff_check.check(GOOD_EN + "```\n" + "x\n" * 25 + "```\n")))
        self.assertTrue(any("is not closed" in x for x in handoff_check.check(GOOD_EN + "```\nx\n")))
        self.assertTrue(any(x.startswith("2 lines look like a full diff")
                            for x in handoff_check.check(GOOD_EN + "diff --git a/x b/x\n@@ -1,2 +1,3 @@\n")))
        out = handoff_check.check(GOOD_EN + "- Jane Roe asked\n", private_terms=["jane roe"])
        self.assertEqual(out, [f"1 word(s) from your private-words list found (lines {n + 1}) — remove them or write them generically"])

    def test_english_marks_warnings(self):
        self.assertEqual(handoff_check.warnings(self.facts("- [V] ran the tests\n- [?] Codex is the same\n")), [])
        out = handoff_check.warnings(self.facts("- [V] checked\n- recalled claim\n"))
        self.assertEqual(len(out), 1, out)
        self.assertTrue(out[0].startswith("warning: 1 of 2 items in the Verified facts and decisions section have no [V]/[?] mark"))
        self.assertNotIn("recalled", out[0])  # 줄 번호와 종류만, 내용은 옮기지 않는다
        out = handoff_check.warnings(self.facts("Prose only.\n"))
        self.assertIn("has no list items", out[0])
        out = handoff_check.warnings(self.facts("- [V] list\nprose line\n"))
        self.assertIn("1 line(s) in the Verified facts and decisions section are not list items", out[0])
        self.assertEqual(handoff_check.warnings("# Handoff\n## Verified facts\n- no mark\n", strict=False), [])  # 다른 형식은 밀지 않는다

    def test_leaks_kinds_in_english_on_request(self):
        self.assertEqual(handoff_check.leaks("/Users/someone/x"), ["홈 절대경로"])  # 기본은 한국어(부르는 쪽 문장이 한국어)
        self.assertEqual(handoff_check.leaks("/Users/someone/x Jane", ["jane"], lang="en"),
                         ["absolute home path", "word from the private-words list"])

    def cli(self, text, env):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "HANDOFF.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write(text)
            e = {k: v for k, v in os.environ.items() if k not in ("BATON_LANG", "LC_ALL", "LC_MESSAGES", "LANG")}
            e.update(env)
            r = subprocess.run([sys.executable, os.path.join(HERE, "handoff_check.py"), p], capture_output=True, text=True, env=e)
            return r.returncode, r.stdout.replace(p, "HANDOFF.md")

    def test_cli_in_english_and_locale_fallback(self):
        self.assertEqual(self.cli(GOOD_EN, {"BATON_LANG": "en"}), (0, "HANDOFF.md: no problems\n"))
        code, out = self.cli(self.facts("- no mark\n"), {"BATON_LANG": "en"})
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("warning: "), out)
        self.assertTrue(out.endswith("HANDOFF.md: no problems (warnings only — not blocking)\n"), out)
        self.assertEqual(self.cli("# Session Handoff\n", {"BATON_LANG": "en"})[0], 1)
        # BATON_LANG이 없으면 로캘을 따른다
        self.assertEqual(self.cli(GOOD_EN, {"LANG": "ko_KR.UTF-8"}), (0, "HANDOFF.md: 문제 없음\n"))
        self.assertEqual(self.cli(GOOD_EN, {"LANG": "C.UTF-8"}), (0, "HANDOFF.md: no problems\n"))


class InjectBudgetTest(unittest.TestCase):
    """검사를 통과한 인계서는 주입에서 잘리지 않는다 — 두 상한이 따로 박혀 있어 갈라지면 여기서 깨진다."""

    HOOK = os.path.join(os.path.dirname(HERE), "hooks", "handoff-inject.py")

    def test_checker_limit_fits_inject_budget(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("handoff_inject", self.HOOK)
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        self.assertEqual(handoff_check.MAX_LINES, hook.LIMIT)
        # 신선도 한 줄이 가장 길 때의 본문 예산(머리말 + 줄바꿈 + 신선도 + 꼬리 안내 몫을 뺀 것)에 검사기 상한 + 끝 줄바꿈이 들어간다
        self.assertLessEqual(handoff_check.MAX_CHARS + 1,
                             hook.LIMIT_CHARS - len(hook.HEAD) - 1 - hook.rules.FRESHNESS_MAX - hook.TAIL_RESERVE)
        # 영어 머리말·영어 신선도 상한으로도 같다
        self.assertLessEqual(handoff_check.MAX_CHARS + 1,
                             hook.LIMIT_CHARS - len(hook.HEAD_EN) - 1 - hook.rules.FRESHNESS_MAX_EN - hook.TAIL_RESERVE)

    def test_largest_passing_handoff_is_injected_whole(self):
        with tempfile.TemporaryDirectory() as root:
            last = "- 마지막 줄: 다음 행동\n"
            head = GOOD + "\n"
            room = handoff_check.MAX_CHARS - len(head) - len(last)  # 이 만큼을 80자 줄로 채운다
            pad = ("가" * 79 + "\n") * (room // 80) + "나" * (room % 80)
            text = head + pad + ("\n" if room % 80 else "") + last
            text = text[:-len(last) - 1] + last if len(text) > handoff_check.MAX_CHARS else text
            self.assertEqual(len(text), handoff_check.MAX_CHARS)
            self.assertLessEqual(len(text), handoff_check.MAX_CHARS)
            self.assertLessEqual(text.count("\n"), handoff_check.MAX_LINES)
            self.assertFalse(any("자 — 상한" in x or "줄 — 상한" in x for x in handoff_check.check(text)))
            with open(os.path.join(root, "HANDOFF.md"), "w", encoding="utf-8") as f:
                f.write(text)
            for lang in ("ko", "en"):  # 영어 머리말이 더 길어도 같다
                env = dict(os.environ, CLAUDE_PROJECT_DIR=root, BATON_LOG=os.path.join(root, "runs.jsonl"),
                           XDG_CACHE_HOME=os.path.join(root, ".cache"), BATON_LANG=lang)
                r = subprocess.run([sys.executable, self.HOOK], input='{"prompt": "어디까지 했지? 이어서"}',
                                   text=True, capture_output=True, env=env, check=False)
                ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
                self.assertIn(last, ctx)
                self.assertNotIn("까지만 넣었다", ctx)
                self.assertNotIn("went in (limit", ctx)


if __name__ == "__main__":
    unittest.main()
