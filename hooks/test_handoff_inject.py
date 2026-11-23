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
_CFG_ENV = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": _CFG.name, "BATON_LANG": "ko"})  # 한국어 단언은 ko로 고정. 영어는 EnglishInjectTest


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
            result = self.run_hook(root, "엔딩 판정 확인", session_id="s1")  # 색인은 세션 기억을 쓸 수 있을 때만
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("현재 빌드 기준.", result.stdout)  # 개념 절은 넣지 않는다 — 기본 켬인 색인 한 줄만
        self.assertIn("1. 엔딩 판정", result.stdout)

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
            result = self.run_hook(root, "엔딩 판정 확인", {"BATON_CONCEPT_INJECT": "on", "BATON_CONCEPT_INDEX": "off"})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_oversized_concept_section_is_not_truncated(self):
        with tempfile.TemporaryDirectory() as root:
            long_body = "긴문장 " * 500
            self.write(root, "CONCEPTS.md", "## 1. 엔딩 판정\n" + long_body + "\n")
            result = self.run_hook(root, "엔딩 판정 확인", {"BATON_CONCEPT_INJECT": "on", "BATON_CONCEPT_INDEX": "off"})
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


class ConceptIndexHookTest(unittest.TestCase):
    """개념 색인: 세션의 첫 사람 프롬프트에 한 번, 압축 뒤 다시. 인계서와 따로 기억한다."""
    run_hook, write, last_acted = HandoffInjectTest.run_hook, HandoffInjectTest.write, HandoffInjectTest.last_acted
    MAP = "## 1. 엔딩 판정\n- **메타**: 상태=일치 · 파일=`src/end.ts`\n\n## 2. 저장 슬롯\n- **메타**: 상태=일치 · 파일=`src/save.ts`\n"
    INDEX_HEAD = "[baton] 이 저장소 개념 지도(CONCEPTS.md) 색인이다."

    def test_first_human_prompt_only_then_after_compaction(self):
        with tempfile.TemporaryDirectory() as root:
            self.write(root, "CONCEPTS.md", self.MAP)
            tr = os.path.join(root, "t.jsonl")
            self.write(root, "t.jsonl", '{"type":"user"}\n')
            d = {"session_id": "s1", "transcript_path": tr}
            r = self.run_hook(root, '<agent-message from="a">작업 끝', **d)
            self.assertEqual(r.stdout, "")
            self.assertEqual((self.last_acted(root)["concept_index"], self.last_acted(root)["concept_index_skip"]), (None, "machine"))
            first = self.run_hook(root, "세이브 어디서 해?", **d)
            self.assertTrue(first.stdout.startswith(self.INDEX_HEAD), first.stdout)
            self.assertIn("2. 저장 슬롯 · 파일: src/save.ts", first.stdout)
            self.assertEqual(self.last_acted(root)["concept_index"], len(first.stdout))
            again = self.run_hook(root, "엔딩은?", **d)
            self.assertEqual(again.stdout, "")
            self.assertEqual(self.last_acted(root)["concept_index_skip"], "already")
            self.assertIn(self.INDEX_HEAD, self.run_hook(root, "엔딩은?", session_id="s2").stdout)  # 다른 세션은 따로
            with open(tr, "a", encoding="utf-8") as f:
                f.write('{"type":"system","subtype":"compact_boundary"}\n')
            self.assertIn(self.INDEX_HEAD, self.run_hook(root, "엔딩은?", **d).stdout)
            self.assertEqual(self.run_hook(root, "엔딩은?", **d).stdout, "")

    def test_handoff_and_index_are_remembered_separately(self):
        with tempfile.TemporaryDirectory() as root:
            self.write(root, "CONCEPTS.md", self.MAP)
            self.write(root, "HANDOFF.md", "다음 행동\n")
            first = self.run_hook(root, "이어서", session_id="s1").stdout
            self.assertIn("다음 행동", first)
            self.assertLess(first.index("다음 행동"), first.index(self.INDEX_HEAD))  # 인계서 뒤에 색인
            self.assertEqual(self.run_hook(root, "이어서", session_id="s1").stdout, "")
            self.write(root, "HANDOFF.md", "새 다음 행동\n")
            changed = self.run_hook(root, "이어서", session_id="s1").stdout
            self.assertIn("새 다음 행동", changed)
            self.assertNotIn(self.INDEX_HEAD, changed)  # 인계서가 바뀌어도 색인은 세션에 한 번
        with tempfile.TemporaryDirectory() as root:  # 색인을 먼저 넣고, 나중 프롬프트에서 인계서
            self.write(root, "CONCEPTS.md", self.MAP)
            self.write(root, "HANDOFF.md", "다음 행동\n")
            self.assertNotIn("다음 행동", self.run_hook(root, "세이브 고쳐줘", session_id="s1").stdout)
            later = self.run_hook(root, "이어서", session_id="s1").stdout
            self.assertIn("다음 행동", later)
            self.assertNotIn(self.INDEX_HEAD, later)

    def test_index_follows_output_language(self):  # 색인 머리말·항목 낱말도 BATON_LANG을 따른다(지도 언어와 무관)
        with tempfile.TemporaryDirectory() as root:
            self.write(root, "CONCEPTS.md", self.MAP)
            en = self.run_hook(root, "fix the save slot", {"BATON_LANG": "en"}, session_id="s-en").stdout
            self.assertTrue(en.startswith("[baton] Index of this repo's concept map (CONCEPTS.md)."), en)
            self.assertIn("files: src/save.ts", en)
            self.assertNotIn(self.INDEX_HEAD, en)
            ko = self.run_hook(root, "세이브 어디서 해?", {"BATON_LANG": "ko"}, session_id="s-ko").stdout
            self.assertTrue(ko.startswith(self.INDEX_HEAD), ko)

    def test_off_switch_and_no_map(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(self.run_hook(root, "세이브", session_id="s1").stdout, "")
            self.assertEqual(self.last_acted(root)["concept_index_skip"], "no_map")
            self.write(root, "CONCEPTS.md", self.MAP)
            self.assertEqual(self.run_hook(root, "세이브", {"BATON_CONCEPT_INDEX": "off"}, session_id="s1").stdout, "")
            self.assertEqual((self.last_acted(root)["concept_index"], self.last_acted(root)["concept_index_skip"]), (None, "off"))
            self.write(root, "cfg/baton/config.json", json.dumps({"global": {"BATON_CONCEPT_INDEX": "off"}}))
            self.assertEqual(self.run_hook(root, "세이브", {"XDG_CONFIG_HOME": os.path.join(root, "cfg")}, session_id="s1").stdout, "")
            self.assertIn(self.INDEX_HEAD, self.run_hook(root, "세이브", session_id="s1").stdout)  # 끈 동안은 기억하지 않는다
            self.write(root, "CONCEPTS.md", "# 빈 지도\n")
            self.assertEqual(self.run_hook(root, "세이브", session_id="s9").stdout, "")
            self.assertEqual(self.last_acted(root)["concept_index_skip"], "empty")

    def test_no_memory_means_no_index_but_handoff_still_goes_in(self):
        # 기억을 못 쓰면 색인은 매 프롬프트가 아니라 아예 안 넣는다 — 인계서는 예전처럼 넣는다
        with tempfile.TemporaryDirectory() as root:
            self.write(root, "CONCEPTS.md", self.MAP)
            self.write(root, "HANDOFF.md", "다음 행동\n")
            r = self.run_hook(root, "이어서")  # 세션 id 없음
            self.assertIn("다음 행동", r.stdout)
            self.assertNotIn(self.INDEX_HEAD, r.stdout)
            self.assertEqual(self.last_acted(root)["concept_index_skip"], "no_memory")
            self.write(root, "cachefile", "x")  # 캐시 자리가 파일이라 폴더를 못 만든다
            r = self.run_hook(root, "세이브", {"XDG_CACHE_HOME": os.path.join(root, "cachefile")}, session_id="s1")
            self.assertEqual(r.stdout, "")
            self.assertEqual(self.last_acted(root)["concept_index_skip"], "no_memory")

    def test_fail_open_handoff_still_goes_in(self):
        with tempfile.TemporaryDirectory() as root:
            self.write(root, "HANDOFF.md", "다음 행동\n")
            self.write(root, "CONCEPTS.md", self.MAP)
            os.chmod(os.path.join(root, "CONCEPTS.md"), 0)
            try:
                if os.access(os.path.join(root, "CONCEPTS.md"), os.R_OK):
                    self.skipTest("권한을 무시하는 사용자(root)")
                r = self.run_hook(root, "이어서", session_id="s1")
            finally:
                os.chmod(os.path.join(root, "CONCEPTS.md"), 0o600)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("다음 행동", r.stdout)
            self.assertNotIn(self.INDEX_HEAD, r.stdout)
            self.assertEqual(self.last_acted(root)["concept_index_skip"], "error")
            self.assertIn(self.INDEX_HEAD, self.run_hook(root, "세이브", session_id="s1").stdout)  # 실패는 기억하지 않는다

    def test_index_builder_crash_fails_open(self):
        import importlib.util, io
        spec = importlib.util.spec_from_file_location("handoff_inject", HOOK)
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        with tempfile.TemporaryDirectory() as root:
            self.write(root, "HANDOFF.md", "다음 행동\n")
            self.write(root, "CONCEPTS.md", self.MAP)
            out = io.StringIO()
            env = {"CLAUDE_PROJECT_DIR": root, "BATON_LOG": os.path.join(root, ".test-runs.jsonl"),
                   "XDG_CACHE_HOME": os.path.join(root, ".cache")}
            with mock.patch.dict(os.environ, env), mock.patch.object(hook.concepts, "index", side_effect=RuntimeError("x")), \
                    mock.patch.object(sys, "stdin", io.StringIO(json.dumps({"prompt": "이어서", "session_id": "s1"}))), \
                    mock.patch.object(sys, "stdout", out):
                hook.main()
            ctx = json.loads(out.getvalue())["hookSpecificOutput"]["additionalContext"]
            self.assertIn("다음 행동", ctx)
            self.assertNotIn(self.INDEX_HEAD, ctx)
            self.assertEqual(self.last_acted(root)["concept_index_skip"], "error")


class HookOutputBudgetTest(unittest.TestCase):
    """훅 출력은 Claude Code 문서 상한 10,000자 안이고, 신선도 한 줄이 가장 길어도 검사기를 통과한 인계서(8,700자)는 전부 들어간다."""
    DOC_CAP, MARGIN = 10000, 400  # https://code.claude.com/docs/en/hooks "JSON output"
    CHECKER_MAX = 8700  # PR #14가 정하는 lib/handoff_check.MAX_CHARS

    def load(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("handoff_inject", HOOK)
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        return hook

    def test_longest_freshness_line_is_bounded(self):
        hook = self.load()
        rules = hook.rules
        reasons = ["첫 줄 날짜(2026-13-45)가 잘못됐다", "얕은 복제라 그 뒤 커밋 수를 못 셌다", "그 뒤 커밋 수를 못 셌다(git 시한 초과 또는 오류)",
                   "HANDOFF.md가 커밋된 적 없어 그 뒤 커밋 수를 못 셌다", "그 뒤 커밋 수를 못 셌다(git 저장소가 아니거나 시한 초과·오류)",
                   "첫 줄에 작성일이 없고 HANDOFF.md가 커밋된 적 없다", "첫 줄에 작성일이 없고 git 기록도 못 읽었다",
                   "첫 줄에 작성일이 없고 그 뒤 커밋 수를 못 셌다(훅 시한)", "신선도 계산 실패(UnicodeDecodeError)"]
        # 실제로는 함께 나올 수 없는 것까지 전부 붙인 과대 추정 — 묵은 경고·커밋 안내·까닭 모두
        worst = {"written": "2026-01-01", "source": "commit", "days": 9999999, "dirty": False, "commits_after": 9999999,
                 "unknown": reasons}
        line = rules.freshness_line(worst)
        self.assertLessEqual(len(line), rules.FRESHNESS_MAX)
        self.assertFalse(line.endswith("…"), len(line))  # 과대 추정도 자르지 않는다 — 실제 줄은 잘리지 않는다
        for part in ("9999999일 지났다", "`git log --oneline -20 -- .`", reasons[-1]):
            self.assertIn(part, line)
        huge = dict(worst, unknown=["x" * 5000])  # 그래도 넘으면 잘라서 상한을 지킨다
        self.assertEqual(len(rules.freshness_line(huge)), rules.FRESHNESS_MAX)
        self.assertLessEqual(len(rules.freshness_line(dict(worst, written=None, unknown=["x" * 5000]))), rules.FRESHNESS_MAX)

    def test_budget_arithmetic(self):
        hook = self.load()
        head_max = len(hook.HEAD) + 1 + hook.rules.FRESHNESS_MAX
        self.assertLessEqual(head_max + (self.CHECKER_MAX + 1) + hook.TAIL_RESERVE, hook.LIMIT_CHARS)
        self.assertLessEqual(hook.LIMIT_CHARS, self.DOC_CAP - self.MARGIN)
        self.assertEqual(hook.LIMIT, 200)  # 줄 상한은 그대로(소유자 결정 09-22)

    def write_handoff(self, root, chars):
        last = "- 마지막 줄: 다음 행동\n"
        room = chars - len(last)
        text = ("가" * 79 + "\n") * (room // 80) + "나" * (room % 80 - 1) + "\n" + last if room % 80 else ("가" * 79 + "\n") * (room // 80) + last
        self.assertEqual(len(text), chars)
        with open(os.path.join(root, "HANDOFF.md"), "w", encoding="utf-8") as f:
            f.write(text)
        return text, last

    def test_largest_handoff_goes_in_whole_with_longest_freshness_line(self):
        hook = self.load()
        with tempfile.TemporaryDirectory() as root:
            text, last = self.write_handoff(root, self.CHECKER_MAX)
            self.assertLessEqual(text.count("\n"), hook.LIMIT)
            longest = "F" * hook.rules.FRESHNESS_MAX
            with mock.patch.object(hook.rules, "freshness_line", return_value=longest):
                out, h, _ = hook.inject_handoff(root, "이어서", {})
            self.assertIn(longest + "\n\n" + text, out)
            self.assertNotIn("까지만 넣었다", out)
            self.assertEqual(h["lines"], h["total"])
            self.assertLessEqual(len(out), hook.LIMIT_CHARS)

    def big_map(self, n=30):
        return "\n".join("## %d. 개념%02d — 이 개념의 한 줄 요약이다 조금 길게\n- **메타**: 상태=일치 · 파일=%s\n"
                         % (i, i, ",".join("`src/mod%02d/file%d.py`" % (i, k) for k in range(4))) for i in range(1, n + 1))

    def test_largest_handoff_still_whole_with_index_reserved(self):
        # 색인 몫을 먼저 잡아도 8,700자 인계서는 신선도 한 줄이 가장 길 때도 전부 들어간다 — 줄어드는 것은 색인이다
        hook = self.load()
        with tempfile.TemporaryDirectory() as root:
            text, _ = self.write_handoff(root, self.CHECKER_MAX)
            longest = "F" * hook.rules.FRESHNESS_MAX
            with mock.patch.object(hook.rules, "freshness_line", return_value=longest):
                out, h, _ = hook.inject_handoff(root, "이어서", {}, reserve=hook.concepts.INDEX_LIMIT_CHARS + 1)
            self.assertIn(longest + "\n\n" + text, out)
            self.assertEqual(h["lines"], h["total"])
            # 짧은 인계서는 색인 몫을 빼고도 남는다 — 긴 인계서만 잘릴 때 색인 몫을 양보한다
            self.write_handoff(root, 30000)
            with mock.patch.object(hook.rules, "freshness_line", return_value="F" * 100):
                plain, _, _ = hook.inject_handoff(root, "이어서", {})
                reserved, _, _ = hook.inject_handoff(root, "이어서", {}, reserve=1000)
            self.assertLess(len(reserved), len(plain))
            self.assertGreaterEqual(len(reserved) - len(hook.HEAD) - 1 - 100 - hook.TAIL_RESERVE, hook.HANDOFF_KEEP - 1000)

    def run_hook(self, root, prompt):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=root, BATON_LOG=os.path.join(root, "runs.jsonl"),
                   XDG_CACHE_HOME=os.path.join(root, ".cache"))
        r = subprocess.run([sys.executable, HOOK], input=json.dumps({"prompt": prompt, "session_id": "s1"}),
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(root, "runs.jsonl"), encoding="utf-8") as f:
            acted = json.loads(f.read().splitlines()[-1])["acted"]
        return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"], acted

    def test_keep_follows_the_checker_cap(self):
        # 검사기를 통과한 인계서(8,700자)는 색인 몫 때문에 잘리지 않는다. 9,000자는 검사기 상한이 바뀌어도 같은지 보는 값
        hook = self.load()
        self.assertEqual(hook.HANDOFF_KEEP, hook.handoff_check.MAX_CHARS + 1)
        for cap in (8700, 9000):
            with tempfile.TemporaryDirectory() as root, mock.patch.object(hook, "HANDOFF_KEEP", cap + 1):
                text, _ = self.write_handoff(root, cap)
                with mock.patch.object(hook.rules, "freshness_line", return_value="F" * 100):
                    out, h, _ = hook.inject_handoff(root, "이어서", {}, reserve=hook.concepts.INDEX_LIMIT_CHARS + 1)
                self.assertIn(text, out, cap)
                self.assertEqual(h["lines"], h["total"], cap)
                self.assertNotIn("unreserved", h)

    def test_handoff_is_not_cut_for_an_index_that_is_dropped(self):
        # 실험 개념 절까지 같이 들어가 색인 자리가 없으면 색인을 빼고, 색인 몫 때문에 자른 인계서는 되돌린다
        hook = self.load()
        with tempfile.TemporaryDirectory() as root:
            text, last = self.write_handoff(root, 9600)  # 검사기 상한을 넘는다 — 색인 몫을 잡으면 더 잘린다
            section = "## 1. 엔딩 판정\n" + "본문 " * 300 + "\n"
            with open(os.path.join(root, "CONCEPTS.md"), "w", encoding="utf-8") as f:
                f.write(section + "\n" + self.big_map())
            env = dict(os.environ, CLAUDE_PROJECT_DIR=root, BATON_LOG=os.path.join(root, "runs.jsonl"),
                       XDG_CACHE_HOME=os.path.join(root, ".cache"), BATON_CONCEPT_INJECT="on")
            r = subprocess.run([sys.executable, HOOK], input=json.dumps({"prompt": "이어서 엔딩 판정", "session_id": "s1"}),
                               capture_output=True, text=True, env=env)
            ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
            with open(os.path.join(root, "runs.jsonl"), encoding="utf-8") as f:
                acted = json.loads(f.read().splitlines()[-1])["acted"]
            self.assertEqual(acted["concept"], "1")
            self.assertEqual((acted["concept_index"], acted["concept_index_skip"]), (None, "budget"))
            plain, h, _ = hook.inject_handoff(root, "이어서", {})  # 색인 없이 만든 인계서와 같은 줄 수
            self.assertEqual(acted["handoff_lines"], h["lines"])
            self.assertIn("\n".join(text.splitlines()[:h["lines"]]), ctx)

    def test_hook_output_with_big_handoff_and_index_stays_under_limit(self):
        hook = self.load()
        for chars in (self.CHECKER_MAX, 30000, 200):
            with tempfile.TemporaryDirectory() as root:
                text, last = self.write_handoff(root, chars)
                with open(os.path.join(root, "CONCEPTS.md"), "w", encoding="utf-8") as f:
                    f.write(self.big_map())
                ctx, acted = self.run_hook(root, "이어서")
                self.assertLessEqual(len(ctx), hook.LIMIT_CHARS, chars)
                if chars <= self.CHECKER_MAX:
                    self.assertIn(text, ctx)  # 인계서는 줄지 않는다
                    self.assertEqual(acted["handoff_lines"], acted["handoff_total"])
                if acted["concept_index"]:
                    self.assertTrue(ctx[-acted["concept_index"]:].startswith(ConceptIndexHookTest.INDEX_HEAD))  # 맨 뒤에 색인
                    self.assertLessEqual(acted["concept_index"], hook.concepts.INDEX_LIMIT_CHARS)
                else:
                    self.assertEqual(acted["concept_index_skip"], "budget")
                if chars == 200:
                    self.assertTrue(acted["concept_index"])

    def test_cut_handoff_output_stays_under_limit(self):
        hook = self.load()
        with tempfile.TemporaryDirectory() as root:
            self.write_handoff(root, 30000)  # 200줄도 넘는다 — 글자 예산에서 먼저 잘린다
            with mock.patch.object(hook.rules, "freshness_line", return_value="F" * hook.rules.FRESHNESS_MAX):
                out, h, _ = hook.inject_handoff(root, "이어서", {})
            self.assertIn("까지만 넣었다", out)
            self.assertLessEqual(len(out), hook.LIMIT_CHARS)
            self.assertLess(h["lines"], h["total"])

    # 영어 — 머리말이 길어 신선도 상한이 rules.FRESHNESS_MAX_EN이다. 같은 9,600자 안에 검사기 상한 8,700자가 전부 들어가야 한다
    def test_budget_arithmetic_in_english(self):
        hook = self.load()
        head_max = len(hook.HEAD_EN) + 1 + hook.rules.FRESHNESS_MAX_EN
        self.assertLessEqual(head_max + (self.CHECKER_MAX + 1) + hook.TAIL_RESERVE, hook.LIMIT_CHARS)

    def test_longest_real_english_freshness_line_is_bounded(self):
        # 영어는 한국어판처럼 모든 까닭을 다 붙인 과대 추정이 상한에 안 든다 — 실제로 나올 수 있는 조합만 센다(rules.handoff_freshness):
        # 첫 줄 날짜가 잘못됐으면(bad_date) 그 뒤에 git 쪽 까닭이 하나 붙을 수 있고, 그때는 커밋 수를 못 센 것이라 커밋 안내가 없다.
        # 커밋 수를 셌으면 까닭은 bad_date뿐. "no date ..." 앞말은 첫 줄에 날짜가 없을 때만이라 bad_date와 같이 나오지 않고 작성일도 없다.
        # 숫자는 7자리(9999999)로 부풀린다
        rules = self.load().rules
        git_keys = [k for k in rules.WHY if k not in ("bad_date", "crash")]
        bad = rules.unknown_reason("bad_date", "en", "2026-13-45")
        base = {"written": "2026-01-01", "source": "commit", "days": 9999999, "dirty": False, "commits_after": None}
        cases = [dict(base, commits_after=9999999, unknown=[bad]), dict(base, days=-9999999, commits_after=9999999, unknown=[bad]),
                 dict(base, dirty=True, unknown=[bad]),
                 dict(base, written=None, unknown=[rules.unknown_reason("crash", "en", "UnicodeDecodeError")])]
        cases += [dict(base, unknown=[bad, rules.unknown_reason(k, "en")]) for k in git_keys]
        cases += [dict(base, written=None, unknown=[bad, rules.unknown_reason(k, "en")]) for k in git_keys]
        cases += [dict(base, written=None, unknown=[rules.unknown_reason(k, "en", no_date=True)]) for k in git_keys]
        for f in cases:
            line = rules.freshness_line(f, "en")
            self.assertLessEqual(len(line), rules.FRESHNESS_MAX_EN, line)
            self.assertFalse(line.endswith("…"), line)
        line = rules.freshness_line(cases[0], "en")
        for part in ("9999999 days have passed", "`git log --oneline -20 -- .`", "The date in the first lines (2026-13-45) is invalid"):
            self.assertIn(part, line)
        self.assertEqual(len(rules.freshness_line(dict(base, unknown=["x" * 5000]), "en")), rules.FRESHNESS_MAX_EN)  # 넘으면 자른다
        self.assertLessEqual(len(rules.freshness_line(dict(base, written=None, unknown=["x" * 5000]), "en")), rules.FRESHNESS_MAX_EN)

    def test_largest_handoff_goes_in_whole_in_english(self):
        hook = self.load()
        with tempfile.TemporaryDirectory() as root, mock.patch.dict(os.environ, {"BATON_LANG": "en"}):
            text, _ = self.write_handoff(root, self.CHECKER_MAX)
            longest = "F" * hook.rules.FRESHNESS_MAX_EN
            with mock.patch.object(hook.rules, "freshness_line", return_value=longest):
                out, h, _ = hook.inject_handoff(root, "where were we", {})
                reserved, h2, _ = hook.inject_handoff(root, "where were we", {}, reserve=hook.concepts.INDEX_LIMIT_CHARS + 1)
            self.assertTrue(out.startswith(hook.HEAD_EN + "\n" + longest + "\n\n" + text), out[:400])
            self.assertEqual((h["lines"], h2["lines"]), (h["total"], h2["total"]))
            self.assertIn(text, reserved)
            self.assertLessEqual(len(out), hook.LIMIT_CHARS)

    def must_handoff(self, root, chars, lang):
        """필독 항목 3개(각 MUST_ENTRY자를 넘겨 잘리는 길이)를 단 인계서 — 검사기 상한(필독 줄 몫 포함)을 꽉 채운다."""
        hc = self.load().handoff_check
        files = "## 관련 파일·심볼\n" + "".join(f"- `src/f{i}.py` (필독): {'가' * 200}\n" for i in range(3))
        last = "- 마지막 줄: 다음 행동\n"
        extra = max(len(hc.must_read_line(files, "ko")), len(hc.must_read_line(files, "en"))) + 1
        room = hc.MAX_CHARS - extra - len(files) - len(last)
        text = files + ("나" * 79 + "\n") * (room // 80) + ("다" * (room % 80 - 1) + "\n" if room % 80 else "") + last
        self.assertFalse(any("자 — 상한" in x for x in hc.check(text, lang="ko")), len(text))
        self.assertTrue(any("자 — 상한" in x for x in hc.check(text + "a", lang="ko")))  # 꽉 찼다
        with open(os.path.join(root, "HANDOFF.md"), "w", encoding="utf-8") as f:
            f.write(text)
        return text

    def test_largest_handoff_with_must_read_goes_in_whole_in_both_languages(self):
        # 필독 줄은 머리말에 한 번 더 들어간다 — 검사기가 그 몫까지 세므로 통과한 인계서는 신선도 줄이 가장 길어도 전부 들어간다
        hook = self.load()
        for lang, cap in (("ko", hook.rules.FRESHNESS_MAX), ("en", hook.rules.FRESHNESS_MAX_EN)):
            with tempfile.TemporaryDirectory() as root, mock.patch.dict(os.environ, {"BATON_LANG": lang}):
                text = self.must_handoff(root, hook.handoff_check.MAX_CHARS, lang)
                longest = "F" * cap
                with mock.patch.object(hook.rules, "freshness_line", return_value=longest):
                    out, h, _ = hook.inject_handoff(root, "이어서", {})
                    reserved, h2, _ = hook.inject_handoff(root, "이어서", {}, reserve=hook.concepts.INDEX_LIMIT_CHARS + 1)
                must = hook.handoff_check.must_read_line(text, lang)
                self.assertTrue(out.startswith((hook.HEAD if lang == "ko" else hook.HEAD_EN) + "\n" + longest + "\n" + must
                                               + "\n\n" + text), lang)
                self.assertEqual((h["lines"], h2["lines"]), (h["total"], h2["total"]), lang)
                self.assertLessEqual(len(out), hook.LIMIT_CHARS, lang)

    def test_truncation_note_fits_its_reserve_in_both_languages(self):
        hook = self.load()
        for lang, mark in (("ko", "까지만 넣었다"), ("en", "went in (limit 200 lines, 9,600 chars)")):
            with tempfile.TemporaryDirectory() as root, mock.patch.dict(os.environ, {"BATON_LANG": lang}):
                self.write_handoff(root, 30000)
                with mock.patch.object(hook.rules, "freshness_line", return_value="F" * 100):
                    out, h, _ = hook.inject_handoff(root, "이어서", {})
                body = out.split("F" * 100 + "\n\n", 1)[1]
                note = body[body.rindex("\n[baton] "):]
                self.assertIn(mark, note)
                self.assertLessEqual(len(note), hook.TAIL_RESERVE)
                # 줄 수가 아주 커도(7자리) 꼬리 몫 안이다
                with open(os.path.join(root, "HANDOFF.md"), "w", encoding="utf-8") as fh:
                    fh.write("x\n" * 9999999)
                with mock.patch.object(hook.rules, "freshness_line", return_value="F" * 100):
                    out, _, _ = hook.inject_handoff(root, "이어서", {})
                self.assertLessEqual(len(out[out.rindex("\n[baton] "):]), hook.TAIL_RESERVE, lang)


class EnglishInjectTest(unittest.TestCase):
    """BATON_LANG=en이면 머리말·신선도 한 줄·잘림 안내·개념 절 머리말이 영어다. 인계서 본문은 언어와 무관하게 그대로."""

    def run_hook(self, root, prompt, **env):
        e = dict(os.environ, CLAUDE_PROJECT_DIR=root, BATON_LOG=os.path.join(root, "runs.jsonl"),
                 XDG_CACHE_HOME=os.path.join(root, ".cache"), BATON_CONCEPT_INDEX="off", **env)
        r = subprocess.run([sys.executable, HOOK], input=json.dumps({"prompt": prompt}), capture_output=True, text=True, env=e)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"] if r.stdout.strip() else ""

    def git(self, root, *args):
        subprocess.run(["git", "-C", root, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false",
                        *args], check=True, capture_output=True)

    def test_header_and_freshness_line_in_english(self):
        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, "HANDOFF.md"), "w", encoding="utf-8") as f:
                f.write("# Session Handoff (written: 2020-01-01)\n- Next action: x\n")
            self.git(root, "init", "-q"); self.git(root, "add", "HANDOFF.md"); self.git(root, "commit", "-qm", "h")
            for name in ("a", "b"):
                with open(os.path.join(root, name), "w") as f:
                    f.write(name)
                self.git(root, "add", name); self.git(root, "commit", "-qm", name)
            ctx = self.run_hook(root, "where were we?", BATON_LANG="en")
            head, fresh, blank, first = ctx.splitlines()[:4]
            self.assertTrue(head.startswith("[baton] Below is the full HANDOFF.md of this repo (injected because the prompt "
                                            "asks about handoff or progress). No need to open the file again."), head)
            self.assertIn("read it as a hypothesis, not a fact", head)
            self.assertRegex(fresh, r"^\[baton\] This handoff is as of 2020-01-01 \(\d+ days ago, date in its first line\)\. "
                                    r"2 commits since then are not in it — start with `git log --oneline -2 -- \.`\. "
                                    r"\d+ days have passed — first check that the next step still holds\.$")
            self.assertEqual((blank, first), ("", "# Session Handoff (written: 2020-01-01)"))
            ko = self.run_hook(root, "where were we?", BATON_LANG="ko")  # 영어 인계서의 작성일은 한국어 설정에서도 읽는다
            self.assertIn("2020-01-01(", ko.splitlines()[1])
            self.assertIn("첫 줄 작성일", ko.splitlines()[1])

    def test_freshness_reasons_in_english(self):
        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, "HANDOFF.md"), "w", encoding="utf-8") as f:
                f.write("# Notes\nno date here\n")
            fresh = self.run_hook(root, "catch me up", BATON_LANG="en").splitlines()[1]
            self.assertEqual(fresh, "[baton] Could not tell when this handoff was written (no date in the first lines, and "
                                    "could not read the git history either) — first check the facts the next step depends on.")
            with open(os.path.join(root, "HANDOFF.md"), "w", encoding="utf-8") as f:
                f.write("# Session Handoff (written: 2999-01-01)\n")
            fresh = self.run_hook(root, "catch me up", BATON_LANG="en").splitlines()[1]
            self.assertIn("days in the future — check the date", fresh)
            self.assertIn("Could not count the commits since then (not a git repo, or git timed out or failed).", fresh)

    def test_concept_section_head_in_english(self):
        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, "CONCEPTS.md"), "w", encoding="utf-8") as f:
                f.write("## 1. Ending verdict — what decides the ending\nBased on the current build.\n\n## 2. Save slots\nbody\n")
            ctx = self.run_hook(root, "fix the ending verdict", BATON_LANG="en", BATON_CONCEPT_INJECT="on")
            self.assertTrue(ctx.startswith("[baton] Below is the one concept section in this repo's CONCEPTS.md that matches "
                                           "the prompt (experimental feature BATON_CONCEPT_INJECT=on)."), ctx)
            self.assertIn("## 1. Ending verdict", ctx)
            self.assertNotIn("Save slots", ctx)

    def test_must_read_line_follows_freshness_line(self):
        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, "HANDOFF.md"), "w", encoding="utf-8") as f:
                f.write("# Session Handoff (written: 2026-11-23)\n\n## Files and symbols\n- `lib/rules.py` (must read): freshness_line\n"
                        "- `lib/x.py`: other\n\n## Risks and next actions\n- Next action: x\n")
            lines = self.run_hook(root, "where were we", BATON_LANG="en").splitlines()
            self.assertEqual(lines[2], "[baton] Read before acting (marked must read in the handoff): `lib/rules.py`: freshness_line")
            self.assertEqual((lines[3], lines[4]), ("", "# Session Handoff (written: 2026-11-23)"))
            ko = self.run_hook(root, "이어서", BATON_LANG="ko").splitlines()
            self.assertEqual(ko[2], "[baton] 행동 전에 먼저 읽는다(인계서의 필독 표시): `lib/rules.py`: freshness_line")
            with open(os.path.join(root, "HANDOFF.md"), "w", encoding="utf-8") as f:
                f.write("# Session Handoff\n- `x` (must read) 다른 절의 표시\n")
            self.assertEqual(self.run_hook(root, "where were we", BATON_LANG="en").splitlines()[2], "")  # 필독 줄 없음

    def test_locale_fallback_reaches_the_hook(self):
        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, "HANDOFF.md"), "w", encoding="utf-8") as f:
                f.write("next\n")
            env = mock.patch.dict(os.environ); env.start(); self.addCleanup(env.stop)
            for k in ("BATON_LANG", "LC_ALL", "LC_MESSAGES"):
                os.environ.pop(k, None)
            self.assertTrue(self.run_hook(root, "이어서", LANG="ko_KR.UTF-8").startswith("[baton] 아래는 이 저장소 HANDOFF.md의 전문이다"))
            self.assertTrue(self.run_hook(root, "이어서", LANG="C.UTF-8").startswith("[baton] Below is the full HANDOFF.md"))


if __name__ == "__main__":
    unittest.main()
