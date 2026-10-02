#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(__file__)
HOOK = os.path.join(HERE, "handoff-inject.py")
REPO = os.path.dirname(HERE)


_CFG = tempfile.TemporaryDirectory()  # 실제 설정 파일(~/.config/baton/config.json)을 읽지 않는다 — 훅 자식 프로세스도 이 환경을 물려받는다
_CFG_ENV = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": _CFG.name})


def setUpModule():
    _CFG_ENV.start()


def tearDownModule():
    _CFG_ENV.stop(); _CFG.cleanup()


class HandoffInjectTest(unittest.TestCase):
    def run_hook(self, root, prompt, extra_env=None, raw_stdin=None):
        env = os.environ.copy()
        env["CLAUDE_PROJECT_DIR"] = root
        env["BATON_LOG"] = os.path.join(root, ".test-runs.jsonl")  # 실제 캐시에 쓰지 않는다
        if extra_env:
            env.update(extra_env)
        stdin = raw_stdin if raw_stdin is not None else json.dumps({"prompt": prompt})
        r = subprocess.run(
            [sys.executable, HOOK],
            input=stdin,
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        if r.stdout.strip():  # 넣을 것이 있으면 JSON 하나 — 테스트는 그 안의 맥락 텍스트를 본다
            out = json.loads(r.stdout)["hookSpecificOutput"]
            self.assertEqual(out["hookEventName"], "UserPromptSubmit")
            r.stdout = out["additionalContext"]
        return r

    def write(self, root, rel, text):
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def test_handoff_injection_still_works(self):
        with tempfile.TemporaryDirectory() as root:
            self.write(root, "HANDOFF.md", "다음 행동\n")
            result = self.run_hook(root, "핸드오프 읽고 이어서 진행")
        self.assertEqual(result.returncode, 0)
        self.assertIn("HANDOFF.md의 전문", result.stdout)
        self.assertIn("다음 행동", result.stdout)

    def test_concept_injection_is_opt_in(self):
        with tempfile.TemporaryDirectory() as root:
            self.write(root, "CONCEPTS.md", "## 1. 엔딩 판정\n현재 빌드 기준.\n")
            result = self.run_hook(root, "엔딩 판정 확인")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_concept_injection_matches_one_full_root_section(self):
        with tempfile.TemporaryDirectory() as root:
            self.write(
                root,
                "CONCEPTS.md",
                "## 1. 엔딩 판정\n현재 빌드 기준.\n\n## 2. 저장 슬롯\n다른 절.\n",
            )
            result = self.run_hook(root, "엔딩 판정 확인", {"BATON_CONCEPT_INJECT": "on"})
        self.assertEqual(result.returncode, 0)
        self.assertIn("CONCEPTS.md에서 프롬프트와 맞은 개념 한 절", result.stdout)
        self.assertIn("## 1. 엔딩 판정", result.stdout)
        self.assertIn("현재 빌드 기준.", result.stdout)
        self.assertNotIn("## 2. 저장 슬롯", result.stdout)
        self.assertIn("실제 동작은 필요한 경우 코드로 확인한다", result.stdout)

    @unittest.skipUnless(os.path.isfile(os.path.join(REPO, ".data", "snapshots", "steam-2846107-map", "CONCEPTS.md")),
                         "실험 스냅샷(.data/, gitignore)은 소유자 로컬에만 있다")
    def test_real_snapshot_prompt_matches_title_word_before_em_dash(self):
        root = os.path.join(REPO, ".data", "snapshots", "steam-2846107-map")
        prompt = "PLAYER-GUIDE.md의 엔딩 설명이 최신 결정과 맞는지 확인하고, 안 맞으면 고쳐줘."
        result = self.run_hook(root, prompt, {"BATON_CONCEPT_INJECT": "on"})
        self.assertEqual(result.returncode, 0)
        self.assertIn("## 1. 엔딩 판정 — 무엇이 결말을 가르는가", result.stdout)
        self.assertIn("PLAYER-GUIDE.md", result.stdout)
        self.assertNotIn("## 2. 방·챕터 구조", result.stdout)

    def test_concept_injection_uses_docs_concepts_fallback(self):
        with tempfile.TemporaryDirectory() as root:
            self.write(root, "docs/CONCEPTS.md", "## 1. 생각 연결\n문서 아래 지도.\n")
            result = self.run_hook(root, "생각 연결", {"BATON_CONCEPT_INJECT": "on"})
        self.assertEqual(result.returncode, 0)
        self.assertIn("docs/CONCEPTS.md", result.stdout)
        self.assertIn("## 1. 생각 연결", result.stdout)

    def test_ambiguous_concept_matches_are_skipped(self):
        with tempfile.TemporaryDirectory() as root:
            self.write(
                root,
                "CONCEPTS.md",
                "## 1. 엔딩 판정\n첫 절.\n\n## 2. 엔딩 판정 규칙\n둘째 절.\n",
            )
            result = self.run_hook(root, "엔딩 판정 확인", {"BATON_CONCEPT_INJECT": "on"})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_oversized_concept_section_is_not_truncated(self):
        with tempfile.TemporaryDirectory() as root:
            long_body = "긴문장 " * 500
            self.write(root, "CONCEPTS.md", "## 1. 엔딩 판정\n" + long_body + "\n")
            result = self.run_hook(root, "엔딩 판정 확인", {"BATON_CONCEPT_INJECT": "on"})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_malformed_json_and_non_string_prompt_fail_soft(self):
        with tempfile.TemporaryDirectory() as root:
            bad = self.run_hook(root, "", {"BATON_CONCEPT_INJECT": "on"}, raw_stdin="{")
            non_string = self.run_hook(root, "", {"BATON_CONCEPT_INJECT": "on"}, raw_stdin=json.dumps({"prompt": 123}))
        self.assertEqual(bad.returncode, 0)
        self.assertEqual(bad.stdout, "")
        self.assertEqual(non_string.returncode, 0)
        self.assertEqual(non_string.stdout, "")


if __name__ == "__main__":
    unittest.main()
