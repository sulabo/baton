#!/usr/bin/env python3
"""북극성 길 단계 3: 인계서 검사기. 템플릿대로 쓴 인계서는 통과하고, 어긴 곳은 줄 번호와 종류로 잡는다."""
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
_CFG_ENV = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": _CFG.name})


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
        self.assertTrue(any("상한 9,000자" in x for x in handoff_check.check(GOOD + "가" * 9000)))

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


if __name__ == "__main__":
    unittest.main()
