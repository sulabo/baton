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

    def test_generic_headings_do_not_make_a_file_ours(self):
        # 리뷰(11-23): 흔한 영어 제목을 앞머리로 세어 남의 HANDOFF.md를 저장할 때마다 "missing required sections"로 막았다
        foreign_en = "# Project notes\n## Goal\n- ship it\n## Related files\n- a.py\n## Next steps\n- review\n"
        foreign_ko = "# 메모\n## 목표\n- 출시\n## 관련 파일\n- a.py\n## Risks\n- 없음\n"
        for text in (foreign_en, foreign_ko):
            for lang in ("ko", "en"):
                self.assertEqual(handoff_check.check(text, strict=False, lang=lang), [], (text, lang))
                self.assertEqual(handoff_check.warnings(text, strict=False, lang=lang), [], (text, lang))
            self.assertFalse(handoff_check.looks_ours(text))
            self.assertEqual(handoff_check.drop_warnings("x/HANDOFF.md", text, old=text + "## Failed approaches\n- x y z\n",
                                                         private_terms=[], strict=False), [])
        # 한국어 판정은 main과 같다 — 한국어 템플릿 절 앞머리 3개면 baton 형식
        self.assertTrue(handoff_check.check("# 메모\n## 목표\n## 관련 파일\n## 다음 행동\n", strict=False)[0].startswith("missing"))
        # 진짜 영어 인계서는 제목이 없어도 템플릿 제목 그대로 3개면 검사한다(굵게·뒤 괄호 허용)
        real = "# Handoff\n## Goal and done criteria\n## **Verified facts and decisions**\n## Failed approaches (do not retry)\n"
        self.assertTrue(handoff_check.looks_ours(real))
        self.assertEqual(handoff_check.check(real, strict=False),
                         ["missing required sections: Files and symbols, Changes made, Verification evidence, "
                          "Risks and next actions, Promotion candidates"])
        self.assertTrue(handoff_check.check("# Session Handoff (written: 2026-11-23)\n", strict=False))  # 제목만으로도 baton 형식

    def test_problem_messages_in_english(self):
        token = "gh" + "p_" + "A1b2" * 9
        out = handoff_check.check(GOOD_EN + f"- token {token}\n- path /Users/someone/x\n- api_key = abcdef123456\n")
        n = GOOD_EN.count("\n")
        self.assertEqual(out, [f"line {n + 1}: looks like an API token — remove it or write it generically (~/, <key>)",
                               f"line {n + 2}: looks like an absolute home path — remove it or write it generically (~/, <key>)",
                               f"line {n + 3}: looks like a password or key assignment — remove it or write it generically (~/, <key>)"])
        self.assertNotIn(token, "\n".join(out))
        over = GOOD_EN + "a" * (handoff_check.MAX_CHARS + 1 - len(GOOD_EN))
        self.assertIn("8,701 chars — over the 8,700-char limit (the part past it will not be injected into the next session). "
                      "Cut 1 more char — largest sections: Promotion candidates (to DECISIONS.md) 8,355 chars, "
                      "Verification evidence 57 chars", handoff_check.check(over))
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


def gone(*a, **k):
    """dropped()의 빠진 항목 목록만(본 항목 수·전체 수는 뺀다)."""
    out, done, total = handoff_check.dropped(*a, **k)
    assert done == total, (done, total)  # 시한 없이 부르면 다 본다
    return out


def git_repo(root):
    subprocess.run(["git", "init", "-q", root], check=True)
    return lambda *a: subprocess.run(["git", "-C", root, "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                                      "-c", "commit.gpgsign=false", *a], check=True, capture_output=True)


class DropCheckTest(unittest.TestCase):
    """저장 때 마지막 커밋판보다 빠진 줄을 경고한다(막지 않음). 이어 가야 하는 절은 모두, 사실·다음 행동은 결정·제약 표지가 있는 줄만."""
    OLD = GOOD.replace("## 확인된 사실과 결정\n- 없음\n", "## 확인된 사실과 결정\n- [V] 테스트 168개 통과(11-23)\n"
                       "- [V] 소유자 결정: 배포는 사람이 한다\n").replace(
        "## 실패한 접근법 (다시 시도 금지)\n- 없음\n", "## 실패한 접근법 (다시 시도 금지)\n- rtk가 감싼 diff 출력을 믿기 — md5로 확인\n"
        "- 세션 기억 파일을 잠금 없이 동시에 쓰기\n").replace(
        "## 남은 리스크와 다음 행동\n- 다음 행동: 설치\n", "## 남은 리스크와 다음 행동\n- 다음 행동: 설치 스크립트 고치기\n")

    def test_dropped_lines_by_section_rule(self):
        new = self.OLD.replace("- rtk가 감싼 diff 출력을 믿기 — md5로 확인\n", "").replace(
            "- [V] 테스트 168개 통과(11-23)\n", "").replace("- [V] 소유자 결정: 배포는 사람이 한다\n", "")
        self.assertEqual(gone(self.OLD, new),
                         [(0, "[V] 소유자 결정: 배포는 사람이 한다"), (1, "rtk가 감싼 diff 출력을 믿기 — md5로 확인")])
        # 표지 없는 끝난 사실(테스트 통과)은 지워도 알리지 않는다. 고쳐 쓴 줄·다른 절로 옮긴 줄·DECISIONS.md로 올린 줄은 빠진 것이 아니다
        moved = new.replace("## 이미 한 변경\n- 없음\n", "## 이미 한 변경\n- 다음 행동이던 설치 스크립트를 고쳤다\n").replace(
            "- 다음 행동: 설치 스크립트 고치기\n", "- 다음 행동: 배포\n") + "- rtk가 감싼 diff 출력은 믿지 않는다 — md5로\n"
        self.assertEqual(gone(self.OLD, moved, decisions="## 배포는 사람이 한다(소유자 결정)\n"), [])
        self.assertEqual(gone(GOOD, GOOD.replace("## 실패한 접근법 (다시 시도 금지)\n- 없음\n",
                                                                  "## 실패한 접근법 (다시 시도 금지)\n")), [])  # 자리표시는 줄이 아니다

    def test_english_sections_and_markers(self):
        old = GOOD_EN.replace("## Failed approaches (do not retry)\n- None\n",
                              "## Failed approaches (do not retry)\n- Trusting the wrapped diff output — check with md5\n").replace(
            "### Rejected (do not raise again)\n- None\n", "### Rejected (do not raise again)\n- Retry loop / 2026-10-03 / owner said no\n"
        ).replace("## Risks and next actions\n- Next action: install\n",
                  "## Risks and next actions\n- Never push to main directly\n- Next action: install the hook\n")
        self.assertEqual(gone(old, GOOD_EN),
                         [(1, "Trusting the wrapped diff output — check with md5"), (2, "Never push to main directly"),
                          (4, "Retry loop / 2026-10-03 / owner said no")])
        self.assertEqual(gone(old, old.replace("Trusting the wrapped diff output", "Trusted wrapped diff outputs")), [])

    def test_warning_messages(self):
        many = self.OLD.replace("## 실패한 접근법 (다시 시도 금지)\n", "## 실패한 접근법 (다시 시도 금지)\n"
                                + "".join(f"- 실패 사례 번호{i:02d} 다른 내용{i:02d}\n" for i in range(10)) + "- 경로 /Users/someone/x 에서 실패\n")
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "HANDOFF.md")  # 옆에 DECISIONS.md가 없는 곳 — 저장소의 진짜 DECISIONS.md를 읽지 않게
        out = handoff_check.drop_warnings(path, GOOD, lang="ko", old=many, private_terms=[])
        self.assertEqual(len(out), 2, out)
        self.assertTrue(out[0].startswith("경고: 결정·제약으로 보이는 줄 1개가 마지막 커밋판에서 빠졌다 — DECISIONS.md로 옮겼는지"), out[0])
        self.assertIn("\n    - [확인된 사실과 결정] [V] 소유자 결정: 배포는 사람이 한다", out[0])
        self.assertTrue(out[1].startswith("경고: 마지막 커밋판에 있던 줄 13개가 새 인계서에 없다 — 아직 참이면 되살리고"), out[1])
        self.assertEqual(out[1].count("\n    - [실패한 접근법]"), 7)  # 내용은 모두 합쳐 8줄까지
        self.assertTrue(out[1].endswith("\n    - … 외 6개"), out[1])
        self.assertNotIn("someone", "\n".join(out))
        en = handoff_check.drop_warnings(path, GOOD, lang="en", old=many, private_terms=[])
        self.assertTrue(en[0].startswith("warning: 1 line(s) that look like a decision or constraint are gone since the last "
                                         "committed version — check that they moved to DECISIONS.md, otherwise restore them:"))
        self.assertIn("\n    - [Verified facts and decisions] [V] 소유자 결정", en[0])
        self.assertTrue(en[1].endswith("\n    - … and 6 more"), en[1])
        hidden = handoff_check.drop_warnings(path, GOOD, lang="en", old=GOOD.replace(
            "## 실패한 접근법 (다시 시도 금지)\n- 없음\n", "## 실패한 접근법 (다시 시도 금지)\n- 경로 /Users/someone/x 에서 실패\n"), private_terms=[])
        self.assertIn("(content hidden — matched the leak check)", hidden[0])  # 개인 자료 단어에도 맞는 중립 문구(리뷰 11-23)
        ko = handoff_check.drop_warnings(path, GOOD, lang="ko", old=GOOD.replace(
            "## 실패한 접근법 (다시 시도 금지)\n- 없음\n", "## 실패한 접근법 (다시 시도 금지)\n- 홍길동 요청으로 바꾼 방식\n"),
            private_terms=["홍길동"])
        self.assertIn("(내용 생략 — 유출 검사에 걸림)", ko[0])
        self.assertNotIn("홍길동", ko[0])
        self.assertEqual(handoff_check.drop_warnings(path, GOOD, old=""), [])
        with open(os.path.join(tmp.name, "DECISIONS.md"), "w", encoding="utf-8") as f:
            f.write("## 11-23 배포는 사람이 한다 (소유자 결정)\n")
        self.assertEqual(len(handoff_check.drop_warnings(path, GOOD, lang="ko", old=many, private_terms=[])), 1)  # 결정 기록으로 올라갔다

    def test_against_git_head_and_silent_without_history(self):
        with tempfile.TemporaryDirectory() as root:
            p = os.path.join(root, "HANDOFF.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write(self.OLD)
            self.assertIsNone(handoff_check.committed(p))  # git 저장소가 아니다 — 말하지 않는다
            self.assertEqual(handoff_check.drop_warnings(p, GOOD), [])
            g = git_repo(root)
            self.assertEqual(handoff_check.drop_warnings(p, GOOD), [])  # 미추적
            g("add", "HANDOFF.md"); g("commit", "-qm", "h")
            out = handoff_check.drop_warnings(p, GOOD)
            self.assertEqual(len(out), 2, out)
            with open(p, "w", encoding="utf-8") as f:
                f.write(GOOD)
            r = subprocess.run([sys.executable, os.path.join(HERE, "handoff_check.py"), p], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout)  # 경고만 — 막지 않는다
            self.assertIn("마지막 커밋판에 있던 줄 2개", r.stdout)
            self.assertIn("경고만 있음", r.stdout)


def stalling_git(root, seconds="17.25"):
    """cat-file에서 멈추는 git 감싸개(exec하지 않는 #!/bin/sh — 손자 sleep이 파이프를 잡는다). 다른 하위 명령은 진짜 git으로.
    돌려주는 값: 이 폴더를 앞에 붙인 PATH."""
    import shutil
    real = shutil.which("git")
    bin_ = os.path.join(root, "fakebin")
    os.makedirs(bin_, exist_ok=True)
    with open(os.path.join(bin_, "git"), "w") as f:
        f.write(f'#!/bin/sh\ncase "$*" in *cat-file*) sleep {seconds}; : ;; *) exec "{real}" "$@" ;; esac\n')
    os.chmod(os.path.join(bin_, "git"), 0o755)
    return bin_ + os.pathsep + os.environ.get("PATH", "")


class CommittedTimeoutTest(unittest.TestCase):
    """committed()는 git이 멈춰도 시한 안에 돌아오고 남은 프로세스가 없다(리뷰 11-23: exec 안 하는 감싸개에서 시한 3초가 30.2초)."""

    def test_stalled_wrapper_returns_within_timeout(self):
        import time
        with tempfile.TemporaryDirectory() as root:
            p = os.path.join(root, "HANDOFF.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write(GOOD)
            g = git_repo(root); g("add", "HANDOFF.md"); g("commit", "-qm", "h")
            self.assertEqual(handoff_check.committed(p), GOOD)
            with mock.patch.dict(os.environ, {"PATH": stalling_git(root)}):
                t = time.monotonic()
                with self.assertRaises(handoff_check.ReadFailed):  # 시한 초과는 "이전 판 없음"이 아니다
                    handoff_check.committed(p, 1.0)
                took = time.monotonic() - t
                warned = {lang: handoff_check.drop_warnings(p, GOOD, lang, private_terms=[], deadline=time.monotonic() + 1)
                          for lang in ("ko", "en")}
            self.assertLess(took, 1.8, took)
            self.assertEqual(warned, {"ko": ["빠진 줄은 확인하지 못했어요(이전 판을 읽지 못함)."],
                                      "en": ["Dropped lines weren't checked (couldn't read the previous version)."]})
            time.sleep(0.2)
            left = subprocess.run(["pgrep", "-f", "sleep 17.25"], capture_output=True, text=True).stdout.split()
            self.assertEqual(left, [])  # 손자까지 묶음째 끝냈다

    def test_no_previous_version_is_silent_but_failures_are_not(self):
        with tempfile.TemporaryDirectory() as root:
            p = os.path.join(root, "HANDOFF.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write(GOOD)
            self.assertIsNone(handoff_check.committed(p))  # 저장소 아님
            g = git_repo(root)
            self.assertIsNone(handoff_check.committed(p))  # 커밋 없음
            with open(os.path.join(root, "a"), "w") as f:
                f.write("a")
            g("add", "a"); g("commit", "-qm", "a")
            self.assertIsNone(handoff_check.committed(p))  # 미추적
            self.assertIsNone(handoff_check.committed(os.path.join(root, "NOPE.md")))  # 디스크에도 HEAD에도 없는 경로
            for env in ({"LC_ALL": "ko_KR.UTF-8", "LANG": "ko_KR.UTF-8"}, {}):  # git 메시지 언어와 무관하다
                with mock.patch.dict(os.environ, env):
                    self.assertEqual(handoff_check.drop_warnings(p, GOOD, "ko", private_terms=[]), [])
            bin_ = os.path.join(root, "badbin"); os.mkdir(bin_)
            with open(os.path.join(bin_, "git"), "w") as f:
                f.write('#!/bin/sh\necho "fatal: unable to read 1234abcd: corrupt loose object" >&2\nexit 128\n')
            os.chmod(os.path.join(bin_, "git"), 0o755)
            with mock.patch.dict(os.environ, {"PATH": bin_ + os.pathsep + os.environ["PATH"]}):
                with self.assertRaises(handoff_check.ReadFailed):  # 알 수 없는 실패는 못 읽음
                    handoff_check.committed(p)
            with mock.patch.dict(os.environ, {"PATH": os.path.join(root, "nowhere")}):
                self.assertEqual(handoff_check.drop_warnings(p, GOOD, "en", private_terms=[]),
                                 ["Dropped lines weren't checked (couldn't read the previous version)."])  # git이 없다


class DropCostTest(unittest.TestCase):
    """빠진 줄 검사는 입력이 커도 훅 시한(10초) 훨씬 안에 끝나고, 시한·크기 상한에 걸리면 다 못 봤다고 말한다(리뷰 11-23)."""

    def big(self, root, items=2000, decision_lines=20000):
        old = GOOD.replace("## 실패한 접근법 (다시 시도 금지)\n- 없음\n", "## 실패한 접근법 (다시 시도 금지)\n"
                           + "".join(f"- 접근{i}가 실패 이유{i} 기록{i} 다시{i}\n" for i in range(items)))
        with open(os.path.join(root, "DECISIONS.md"), "w", encoding="utf-8") as f:
            f.write("".join(f"## 결정 {i} — 공통 낱말 다시 실패 기록 이유 {i * 7}\n" for i in range(decision_lines)))
        return old

    def test_large_input_finishes_fast(self):
        import time
        with tempfile.TemporaryDirectory() as root:
            old = self.big(root)
            t = time.monotonic()
            out = handoff_check.drop_warnings(os.path.join(root, "HANDOFF.md"), GOOD, lang="en", old=old, private_terms=[],
                                              deadline=time.monotonic() + 60)  # 시한에 기대지 않고도 빨라야 한다
            took = time.monotonic() - t
            self.assertLess(took, 2.0, took)  # 이전: 빠진 줄 200개 × 2만 줄 11.6초, 2,000개 94초
            self.assertTrue(any("2000 line(s) from the last committed version are not in the new handoff" in x for x in out), out)
            self.assertTrue(any("(DECISIONS.md is large; only its first 256 KB was compared)" in x for x in out), out)

    def test_deadline_and_size_caps_are_reported(self):
        with tempfile.TemporaryDirectory() as root:
            old = self.big(root, items=50, decision_lines=10)
            out, done, total = handoff_check.dropped(old, GOOD, deadline=0)  # 시한이 이미 지났다
            self.assertEqual((out, done, total), ([], 0, 50))
            path = os.path.join(root, "HANDOFF.md")
            ko = handoff_check.drop_warnings(path, GOOD, lang="ko", old=old, private_terms=[], deadline=0)
            self.assertEqual(ko, ["경고: 빠진 줄 검사를 다 못 했다(마지막 커밋판 항목 50개 중 0개만 봤다) — 아래 목록은 일부다. "
                                  "0개여도 '빠진 줄 없음'이 아니다"])
            en = handoff_check.drop_warnings(path, GOOD, lang="en", old=old + "x" * (handoff_check.DROP_READ_MAX + 10),
                                             private_terms=[])
            self.assertIn("the last committed version is large, only its first 256 KB was read", en[0])
            self.assertIn("50 line(s) from the last committed version are not in the new handoff", en[1])

    def test_keep_rule_unchanged_by_the_index(self):
        # 색인(비둘기집) 비교는 예전의 "한 줄이 열쇠의 DROP_KEEP 이상을 가진다"와 같은 답을 낸다
        import random
        rnd = random.Random(5)
        words = [f"w{i}" for i in range(30)]
        for _ in range(200):
            old_line = " ".join(rnd.sample(words, rnd.randint(1, 8)))
            new = "\n".join(" ".join(rnd.sample(words, rnd.randint(1, 8))) for _ in range(5))
            keys = handoff_check.line_keys(old_line)
            slow = not any(len(keys & handoff_check.line_keys(l)) >= handoff_check.DROP_KEEP * len(keys) for l in new.splitlines())
            fast = bool(gone("# Session Handoff\n## 실패한 접근법\n- " + old_line + "\n", new))
            self.assertEqual(fast, slow, (old_line, new))


class MustReadTest(unittest.TestCase):
    """"관련 파일·심볼"(Files and symbols) 절의 (필독)·(must read) 표시 — 최대 3개, 주입 머리말에 한 줄로 다시 들어간다."""
    def files(self, body, base=GOOD, head="## 관련 파일·심볼\n- `lib/handoff_check.py`\n"):
        return base.replace(head, head.split("\n", 1)[0] + "\n" + body)

    def test_marked_entries_both_languages(self):
        text = self.files("- `lib/a.py` (필독): parse / 이유\n- `lib/b.py`: 그냥\n- `hooks/c.py`(Must Read): run\n")
        self.assertEqual(handoff_check.must_read(text), ["`lib/a.py`: parse / 이유", "`hooks/c.py`: run"])
        self.assertEqual(handoff_check.must_read_line(text, "ko"),
                         "[baton] 행동 전에 먼저 읽는다(인계서의 필독 표시): `lib/a.py`: parse / 이유 · `hooks/c.py`: run")
        self.assertEqual(handoff_check.must_read_line(text, "en"),
                         "[baton] Read before acting (marked must read in the handoff): `lib/a.py`: parse / 이유 · `hooks/c.py`: run")
        self.assertEqual(handoff_check.must_read_line(GOOD + "- `x` (필독)\n", "ko"), "")  # 다른 절의 표시는 아니다
        en = self.files("- `a.py` (must read): x\n", base=GOOD_EN, head="## Files and symbols\n- `lib/handoff_check.py`\n")
        self.assertEqual(handoff_check.must_read(en), ["`a.py`: x"])

    def test_more_than_three_warns_and_only_three_shown(self):
        text = self.files("".join(f"- `f{i}.py` (필독): {'x' * 200}\n" for i in range(4)))
        self.assertEqual(handoff_check.warnings(text), ["경고: 필독 표시가 4개 — 주입 맨 앞에는 앞의 3개만 올라간다. "
                                                        "행동 전에 꼭 읽을 3개만 남긴다"])
        self.assertIn("warning: 4 entries are marked must read", handoff_check.warnings(text, lang="en")[0])
        line = handoff_check.must_read_line(text, "en")
        self.assertEqual(line.count("`f"), 3)
        self.assertNotIn("f3.py", line)
        self.assertTrue(all(len(p) <= handoff_check.MUST_ENTRY for p in line.split(": ", 1)[1].split(" · ")))
        self.assertEqual(handoff_check.warnings(self.files("- `a` (필독)\n- `b` (필독)\n- `c` (필독)\n")), [])

    def test_char_limit_counts_the_must_read_line(self):
        marked = self.files("- `lib/a.py` (필독): 먼저 읽는다\n")
        extra = max(len(handoff_check.must_read_line(marked, "ko")), len(handoff_check.must_read_line(marked, "en"))) + 1
        fits = marked + "가" * (handoff_check.MAX_CHARS - extra - len(marked))
        self.assertFalse(any("자 — 상한" in x for x in handoff_check.check(fits)))
        out = handoff_check.check(fits + "가")
        self.assertTrue(any(f"— 필독 줄 {extra:,}자 포함. 1자 더 줄인다 — 큰 절: " in x for x in out), out)
        self.assertTrue(any(f"— including the {extra:,}-char must-read line. Cut 1 more char" in x
                            for x in handoff_check.check(fits + "a", lang="en")))
        over = GOOD + "가" * (handoff_check.MAX_CHARS + 1 - len(GOOD))
        self.assertIn(f"{handoff_check.MAX_CHARS + 1:,}자 — 상한 8,700자를 넘는다(넘친 뒤쪽은 다음 세션에 주입되지 않는다). "
                      f"1자 더 줄인다 — 큰 절: 승격 후보 (DECISIONS.md로 올릴 것) 8,472자, 관련 파일·심볼 38자",
                      handoff_check.check(over))  # 표시가 없으면 필독 몫 없이

    def test_over_limit_says_how_much_and_where(self):
        # 11-25 실사용: 9,617자 인계서를 줄이는 편집이 막히기만 하고 얼마나·어디를 줄일지는 없었다 — 넘친 양과 큰 절 둘
        text = GOOD.replace("## 이미 한 변경\n- 없음\n", "## 이미 한 변경\n" + ("- " + "바꿈" * 50 + "\n") * 100 + "\n")
        line = handoff_check.size_problems(text, "ko")
        self.assertEqual(line, [f"{len(text):,}자 — 상한 8,700자를 넘는다(넘친 뒤쪽은 다음 세션에 주입되지 않는다). "
                                f"{len(text) - 8700:,}자 더 줄인다 — 큰 절: 이미 한 변경 {len('## 이미 한 변경') + 1 + 103 * 100 + 2:,}자, "
                                f"관련 파일·심볼 38자"])
        self.assertIn(line[0], handoff_check.check(text))  # check()가 같은 줄을 낸다(저장 훅은 이것으로 크기 문제를 가린다)
        self.assertEqual(handoff_check.size_problems(GOOD, "ko"), [])
        # 제목에 비밀값·개인 자료 단어가 있으면 이름 대신 줄 번호, 코드 블록 안 제목은 절이 아니다, 40자 넘는 제목은 자른다
        odd = ("# Session Handoff\n## 홍길동 메모\n" + "가\n" * 3000 + "## /Users/bob 경로\n" + "나\n" * 2000
               + "## " + "긴" * 50 + "\n```\n## 코드 안\n" + "다\n" * 1000 + "```\n")
        names = [n for n, _ in handoff_check.biggest_sections(odd, ["홍길동"], "ko", n=3)]
        self.assertEqual(names, ["2줄의 절", "3003줄의 절", "긴" * 39 + "…"])
        self.assertNotIn("홍길동", " ".join(handoff_check.size_problems(odd, "ko", ["홍길동"])))


class PluginRootTest(unittest.TestCase):
    """스킬·명령 본문은 중괄호 ${CLAUDE_PLUGIN_ROOT}만 쓴다 — Claude Code는 그 꼴만 본문에 바꿔 넣고, Bash 환경에는 변수가 없다
    (code.claude.com/docs/en/plugins-reference "Environment variables", docs/en/skills "String substitutions").
    allowed-tools의 Bash(…) 패턴은 본문이 시키는 명령과 앞머리가 같아야 미리 허용된다. 읽기만 하는 promote.sh·handoff_check.py만
    미리 허용한다 — /baton-explain은 $ARGUMENTS를 heredoc으로 넘기므로 줄바꿈 뒤 명령이 허용에 묻어 갈 수 있어 미리 허용하지 않는다(리뷰 11-23)."""
    FILES = ("skills/baton/SKILL.md", "commands/promote.md")

    def test_explain_is_not_preapproved(self):
        with open(os.path.join(os.path.dirname(HERE), "commands", "baton-explain.md"), encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn("allowed-tools", text.split("\n---\n", 1)[0])
        self.assertNotRegex(text, r"\$CLAUDE_PLUGIN_ROOT")
        self.assertIn('python3 "${CLAUDE_PLUGIN_ROOT}/lib/rules.py" explain - <<\'BATON_PROMPT\'', text)

    def test_braced_root_and_matching_allowed_tools(self):
        import re
        for rel in self.FILES:
            with open(os.path.join(os.path.dirname(HERE), rel), encoding="utf-8") as f:
                text = f.read()
            self.assertNotRegex(text, r"\$CLAUDE_PLUGIN_ROOT", rel)
            front, body = text.split("\n---\n", 1)
            tools = re.search(r"^allowed-tools: (.+)$", front, re.M)
            self.assertTrue(tools, rel)
            prefixes = re.findall(r"Bash\(([^)]*?) \*\)", tools.group(1))
            self.assertTrue(prefixes, rel)
            for pre in prefixes:
                self.assertIn("${CLAUDE_PLUGIN_ROOT}/lib/", pre)
                self.assertIn(pre + " ", body, (rel, pre))  # 본문 명령이 같은 앞머리로 시작한다
            for cmd in re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/lib/[\w.]+", body):  # 본문이 부르는 스크립트는 모두 미리 허용된다
                self.assertTrue(any(cmd in pre for pre in prefixes), (rel, cmd))


class DoctorSkillShadowTest(unittest.TestCase):
    def test_doctor_lists_every_plugin_skill_name(self):
        # 1.0.2: 같은 이름의 개인 스킬(~/.claude/skills/handoff·ontology)이 플러그인 스킬을 가렸다(11-25 실사용, 9월 사본) —
        # /baton-doctor의 ls가 플러그인 스킬 이름(SKILL.md의 name:)을 빠짐없이 본다. 스킬 이름을 바꾸면 이 줄도 바꿔야 한다
        import glob, re
        root = os.path.dirname(HERE)
        names = []
        for p in glob.glob(os.path.join(root, "skills", "*", "SKILL.md")):
            with open(p, encoding="utf-8") as f:
                names.append(re.search(r"^name: (\S+)$", f.read(), re.M).group(1))
        with open(os.path.join(root, "commands", "baton-doctor.md"), encoding="utf-8") as f:
            doctor = f.read()
        line = re.search(r'^ls -d "\$\{CLAUDE_CONFIG_DIR:-\$HOME/\.claude\}"/skills/\{([^}]*)\} 2>/dev/null', doctor, re.M)
        self.assertTrue(line, "doctor has no personal-skill check")
        self.assertEqual(sorted(line.group(1).split(",")), sorted(names))
        self.assertIn("handoff", names)
        self.assertIn("ontology", names)
        for n in names:
            self.assertIn(f"`{n}`", doctor.split(line.group(0), 1)[1])  # 경고 문장이 이름을 말한다


class SkillCostRulesTest(unittest.TestCase):
    """인계서 쓰기 호출을 줄이는 스킬 규칙(11-25)과 그 리뷰 반영. 문장이 빠지면 모델이 예전처럼 다시 부른다.
    줄바꿈 위치에 기대지 않게 공백을 하나로 모은 뒤 본다."""

    def setUp(self):
        with open(os.path.join(os.path.dirname(HERE), "skills", "baton", "SKILL.md"), encoding="utf-8") as f:
            raw = f.read()
        self.skill = " ".join(raw.split())
        self.stop = " ".join(raw.split("## When the Stop hook asks", 1)[1].split("## Templates", 1)[0].split())

    def test_commit_only_the_handoff_and_keep_the_one_line_output(self):
        self.assertIn('git add HANDOFF.md && git commit -m "handoff: <topic>" -- HANDOFF.md', self.skill)  # 미리 스테이징된 파일 제외
        self.assertNotIn("commit -q", self.skill)  # 한 줄 출력 [branch sha]이 증거다

    def test_check_line_that_could_not_run_means_run_the_checker(self):
        self.assertIn("part of the check couldn't run", self.skill)
        self.assertIn("검사 일부를 돌리지 못했어요", self.skill)
        self.assertIn("if it says part of the check couldn't run, run the checker", self.stop)

    def test_confirmed_facts_have_limits(self):
        self.assertIn("unless you edited a file that fact depends on after you saw it", self.skill)
        self.assertIn("Anything known only from a compaction summary is `[?]`", self.skill)

    def test_stop_hook_path_has_its_own_check_call(self):
        self.assertIn("there is no step 1 call on this path", self.stop)
        self.assertIn("1M-token context window", self.stop)
        self.assertIn("`Agent`/`Task` call whose subagent edited or wrote files", self.stop)
        self.assertIn("below 250K it makes no cost claim", self.stop)
        self.assertIn("also under the ratio rule", self.stop)


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
