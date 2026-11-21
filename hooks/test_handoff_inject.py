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
    def run_hook(self, root, prompt, extra_env=None, raw_stdin=None, **data):
        env = os.environ.copy()
        env["CLAUDE_PROJECT_DIR"] = root
        env["BATON_LOG"] = os.path.join(root, ".test-runs.jsonl")  # 실제 캐시에 쓰지 않는다
        env["XDG_CACHE_HOME"] = os.path.join(root, ".cache")  # 세션별 주입 기억도
        if extra_env:
            env.update(extra_env)
        stdin = raw_stdin if raw_stdin is not None else json.dumps(dict(data, prompt=prompt))
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

    def last_acted(self, root):
        with open(os.path.join(root, ".test-runs.jsonl"), encoding="utf-8") as f:
            return json.loads(f.read().splitlines()[-1])["acted"]

    def test_machine_prompts_get_nothing(self):
        # 11-18 실사용: 다른 세션 메시지 본문의 "handoff"·"인계"가 트리거에 걸려 인계서가 들어갔다
        with tempfile.TemporaryDirectory() as root:
            self.write(root, "HANDOFF.md", "다음 행동\n")
            self.write(root, "CONCEPTS.md", "## 1. 엔딩 판정\n본문.\n")
            on = {"BATON_CONCEPT_INJECT": "on"}
            for p in ['<agent-message from="a3d1">\n[Subagent] HANDOFF 갱신, 엔딩 판정 이어서', "<task-notification>\n인계 엔딩 판정",
                      'Another Claude session sent a message:\n<agent-message from="a6f2">\n[Subagent hand-back] handoff 이어서']:
                r = self.run_hook(root, p, on, session_id="s1")
                self.assertEqual((r.returncode, r.stdout), (0, ""), p)
                self.assertEqual(self.last_acted(root)["handoff_skip"], "machine")
            r = self.run_hook(root, "다른 세션이 보낸 <agent-message>에 인계라고 써 있던데 이어서 해줘", session_id="s1")
            self.assertIn("다음 행동", r.stdout)  # 사람이 그 태그를 말한 것은 막지 않는다
            self.assertIsNone(self.last_acted(root)["handoff_skip"])

    def test_same_session_gets_same_handoff_once(self):
        with tempfile.TemporaryDirectory() as root:
            self.write(root, "HANDOFF.md", "다음 행동\n")
            first = self.run_hook(root, "핸드오프 읽고 이어서", session_id="s1")
            again = self.run_hook(root, "인계서대로 이어서", session_id="s1")
            other = self.run_hook(root, "이어서", session_id="s2")
            no_id = [self.run_hook(root, "이어서") for _ in range(2)]  # 세션 id가 없으면 예전처럼 매번 넣는다
            self.assertIn("다음 행동", first.stdout)
            self.assertEqual((again.returncode, again.stdout), (0, ""))
            self.assertIn("다음 행동", other.stdout)
            self.assertTrue(all("다음 행동" in r.stdout for r in no_id))
            self.write(root, "HANDOFF.md", "새 다음 행동\n")
            changed = self.run_hook(root, "이어서", session_id="s1")
            self.assertIn("새 다음 행동", changed.stdout)  # 파일이 바뀌면 다시 넣는다
            self.run_hook(root, "이어서", session_id="s1")
            self.assertEqual(self.last_acted(root)["handoff_skip"], "already")
            seen = os.path.join(root, ".cache", "baton", "injected")
            self.assertEqual({oct(os.stat(os.path.join(seen, n)).st_mode & 0o777) for n in os.listdir(seen)}, {"0o600"})

    def test_reinjects_after_compaction_only(self):
        with tempfile.TemporaryDirectory() as root:
            self.write(root, "HANDOFF.md", "다음 행동\n")
            tr = os.path.join(root, "t.jsonl")
            self.write(root, "t.jsonl", '{"type":"user"}\n')
            d = {"session_id": "s1", "transcript_path": tr}
            self.assertIn("다음 행동", self.run_hook(root, "이어서", **d).stdout)
            with open(tr, "a", encoding="utf-8") as f:  # 인계서 본문에 그 말이 있어도(JSON 안이라 따옴표가 이스케이프된다) 압축이 아니다
                f.write(json.dumps({"type": "user", "message": {"content": '"subtype":"compact_boundary"'}}) + "\n")
            self.assertEqual(self.run_hook(root, "이어서", **d).stdout, "")
            with open(tr, "a", encoding="utf-8") as f:
                f.write('{"type":"system","subtype":"compact_boundary","content":"Conversation compacted"}\n')
            self.assertIn("다음 행동", self.run_hook(root, "이어서", **d).stdout)
            self.assertEqual(self.run_hook(root, "이어서", **d).stdout, "")  # 압축 뒤 다시 넣었으면 그 시점부터 다시 센다
            with open(tr, "a", encoding="utf-8") as f:  # Codex 세션 기록의 압축 줄
                f.write('{"timestamp":"t","ordinal":9,"type":"compacted","payload":{}}\n')
            self.assertIn("다음 행동", self.run_hook(root, "이어서", **d).stdout)
            self.write(root, "t.jsonl", "{}\n")  # 기록이 줄었다 — 다시 쓰였으니 확인 못 함, 넣는 쪽
            self.assertIn("다음 행동", self.run_hook(root, "이어서", **d).stdout)
            gone = dict(d, transcript_path=os.path.join(root, "없음.jsonl"))
            self.assertEqual(self.run_hook(root, "이어서", **gone).stdout, "")  # 기록을 못 읽으면 또 넣지 않는 쪽

    def test_old_session_memories_are_pruned_and_bad_memory_fails_open(self):
        with tempfile.TemporaryDirectory() as root:
            self.write(root, "HANDOFF.md", "다음 행동\n")
            seen = os.path.join(root, ".cache", "baton", "injected")
            self.write(root, ".cache/baton/injected/old.json", "{}")
            os.utime(os.path.join(seen, "old.json"), (0, 0))
            self.run_hook(root, "이어서", session_id="s0")
            self.run_hook(root, "이어서", session_id="s1")
            self.assertNotIn("old.json", os.listdir(seen))
            self.assertEqual(self.run_hook(root, "이어서", session_id="s0").stdout, "")  # 다른 세션의 최근 기억은 남는다
            for name in os.listdir(seen):
                self.write(root, os.path.join(".cache/baton/injected", name), "{깨진")
            self.assertIn("다음 행동", self.run_hook(root, "이어서", session_id="s1").stdout)

    def test_freshness_only_when_injected(self):
        # 신선도는 git을 최대 3초 부른다 — machine·already로 건너뛸 때는 세지 않고, 로그도 null
        with tempfile.TemporaryDirectory() as root:
            self.write(root, "HANDOFF.md", "# Session Handoff (작성: 2020-01-01)\n다음 행동\n")
            first = self.run_hook(root, "이어서", session_id="s1")
            self.assertIn("2020-01-01(", first.stdout.splitlines()[1])
            acted = self.last_acted(root)
            self.assertGreater(acted["handoff_days"], 2000)
            self.assertIsNone(acted["handoff_commits_after"])  # git 저장소가 아니다 — 못 셈
            for p in ("이어서", '<agent-message from="a">이어서'):
                self.assertEqual(self.run_hook(root, p, session_id="s1").stdout, "")
                acted = self.last_acted(root)
                self.assertIn(acted["handoff_skip"], ("already", "machine"))
                self.assertEqual((acted["handoff_days"], acted["handoff_commits_after"]), (None, None))
        import importlib.util
        spec = importlib.util.spec_from_file_location("handoff_inject", HOOK)
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        with tempfile.TemporaryDirectory() as root:
            self.write(root, "HANDOFF.md", "다음 행동\n")
            with mock.patch.object(hook.rules, "safe_freshness", side_effect=AssertionError("건너뛰는데 셌다")):
                self.assertEqual(hook.inject_handoff(root, "이어서", {}, machine=True), ("", None, "machine"))
                with mock.patch.object(hook, "already_injected", return_value=True):
                    self.assertEqual(hook.inject_handoff(root, "이어서", {}), ("", None, "already"))

    def slow_git_repo(self, root, sleep):
        """HANDOFF.md를 커밋한 저장소와, 부를 때마다 sleep초 쉬고 진짜 git을 부르는 가짜 git 폴더."""
        import shutil
        real = shutil.which("git")
        if not real or not shutil.which("bash"):
            self.skipTest("git·bash 필요")
        repo = os.path.join(root, "repo")
        self.write(repo, "HANDOFF.md", "# Session Handoff (작성: 2020-01-01)\n다음 행동\n")
        for args in (["init", "-q"], ["add", "HANDOFF.md"], ["commit", "-qm", "h"]):
            subprocess.run([real, "-C", repo, "-c", "user.name=t", "-c", "user.email=t@example.com", *args], check=True)
        self.write(root, "bin/git", f'#!/bin/bash\nsleep {sleep}\nexec "{real}" "$@"\n')
        os.chmod(os.path.join(root, "bin", "git"), 0o755)
        return repo, os.path.join(root, "bin")

    def test_freshness_stops_at_hook_deadline(self):
        # 훅 시한(시작 + HOOK_DEADLINE)이 거의 다 됐으면 신선도는 남은 만큼만 쓰고, 못 셌다고 적고 인계서는 넣는다
        import importlib.util, time
        spec = importlib.util.spec_from_file_location("handoff_inject", HOOK)
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        with tempfile.TemporaryDirectory() as root:
            repo, bin_dir = self.slow_git_repo(root, 5)
            with mock.patch.dict(os.environ, {"PATH": bin_dir + os.pathsep + os.environ.get("PATH", "")}):
                t = time.monotonic()
                out, h, skip = hook.inject_handoff(repo, "이어서", {}, hook_deadline=time.monotonic() + 0.4)
                took = time.monotonic() - t
        self.assertLess(took, 1.5)  # 시한이 없으면 git 하나에 5초를 기다렸다
        self.assertIsNone(skip)
        self.assertIn("다음 행동", out)
        self.assertIn("못 셌다", out.splitlines()[1])
        self.assertIsNone(h["commits_after"])

    def test_slow_git_hook_stays_under_timeout(self):
        # Codex(CLAUDE_PROJECT_DIR 없음)·설정에 저장소 절 — repo_root·repo_key·신선도가 모두 git을 부르는 가장 긴 길
        import time
        with tempfile.TemporaryDirectory() as root:
            repo, bin_dir = self.slow_git_repo(root, 1)
            self.write(root, "cfg/baton/config.json", json.dumps({"repos": {"/elsewhere": {}}}))
            env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
            env.update(PATH=bin_dir + os.pathsep + os.environ.get("PATH", ""), XDG_CONFIG_HOME=os.path.join(root, "cfg"),
                       XDG_CACHE_HOME=os.path.join(root, "cache"), BATON_LOG=os.path.join(root, "runs.jsonl"))
            t = time.monotonic()
            r = subprocess.run([sys.executable, HOOK], input=json.dumps({"prompt": "이어서", "session_id": "s1"}),
                               capture_output=True, text=True, cwd=repo, env=env)
            took = time.monotonic() - t
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertLess(took, 9.5)
        ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("다음 행동", ctx)
        self.assertIn("2020-01-01(", ctx.splitlines()[1])

    def test_compacted_since_edges(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("handoff_inject", HOOK)
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "t.jsonl")
            with open(path, "wb") as f:
                f.write(b"x" * 100)
            self.assertFalse(hook.compacted_since(path, 0))
            self.assertTrue(hook.compacted_since(path, -5))  # 깨진 기억은 넣는 쪽
            self.assertTrue(hook.compacted_since(path, 200))  # 기록이 줄었다
            with mock.patch.object(hook, "SEEN_SCAN_MAX", 50):
                self.assertTrue(hook.compacted_since(path, 0))  # 너무 많이 자랐으면 읽지 않고 넣는다
            self.assertFalse(hook.compacted_since(None, 0))  # 기록 경로가 없으면 같은 내용을 또 넣지 않는다

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
