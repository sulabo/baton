#!/usr/bin/env python3
"""개념 지도 후보(설계안 8절): 세션 기록 → 턴 → 별칭·새 개념 후보 → 결정론 검증 → 사람 승격 → 조립기가 그 별칭으로 고른다."""
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import time
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import candidates, compiler, setup_scan, rules

MAP = """# 개념

## 1. 세이브 — 저장과 불러오기

- **메타**: 상태=구현 · 확인=2026-09-01(`0000000`) · 파일=`src/save/save.ts` · 이웃=없음
본문

## 2. 레벨 — 맵 구성

- **메타**: 상태=구현 · 확인=2026-09-01(`0000000`) · 파일=`src/level/map.ts` · 이웃=개념 1(전제) · 별칭=스테이지
"""
FILES = ["src/save/save.ts", "src/level/map.ts", "src/fx/particle.ts", "src/fx/glow.ts", "src/fx/old.ts"]
DAYS = ["2026-09-01", "2026-09-03", "2026-09-05"]


def turn(day, text, *files):
    return {"day": day, "text": text, "files": set(files)}


def user(text, ts, **kw):
    return {"type": "user", "timestamp": ts, "message": {"content": text}, **kw}


def edit(path, ts, name="Edit"):
    return {"type": "assistant", "timestamp": ts,
            "message": {"content": [{"type": "tool_use", "name": name, "input": {"file_path": path}}]}}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.realpath(os.path.join(self.tmp.name, "repo"))
        for f in FILES:
            os.makedirs(os.path.dirname(os.path.join(self.repo, f)), exist_ok=True)
            open(os.path.join(self.repo, f), "w").close()
        with open(os.path.join(self.repo, "CONCEPTS.md"), "w", encoding="utf-8") as fh:
            fh.write(MAP)
        self.home = os.path.join(self.tmp.name, "home")
        p = mock.patch.dict(os.environ, {"HOME": self.home, "XDG_CACHE_HOME": os.path.join(self.tmp.name, "cache")})
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop("CLAUDE_CONFIG_DIR", None)
        os.environ.pop("XDG_CONFIG_HOME", None)  # 실제 설정의 개인 자료 목록을 읽지 않게

    def tearDown(self):
        self.tmp.cleanup()

    def session(self, sid, records, cwd=None, entry="cli", folder=None, subagent=None):
        folder = folder or re.sub(r"[^A-Za-z0-9]", "-", cwd or self.repo)
        d = os.path.join(self.home, ".claude", "projects", folder)
        os.makedirs(d, exist_ok=True)
        head = {"type": "system", "timestamp": "2026-09-01T00:00:00Z", "cwd": cwd or self.repo, "entrypoint": entry}
        with open(os.path.join(d, sid + ".jsonl"), "w", encoding="utf-8") as fh:
            for r in [head] + records:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        if subagent:
            os.makedirs(os.path.join(d, sid, "subagents"), exist_ok=True)
            with open(os.path.join(d, sid, "subagents", "agent-1.jsonl"), "w", encoding="utf-8") as fh:
                for r in subagent:
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        return os.path.join(d, sid + ".jsonl")

    def run_main(self, argv):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return candidates.main(argv)

    def p(self, rel):
        return os.path.join(self.repo, rel)


class PhrasesMoved(unittest.TestCase):
    def test_setup_scan_uses_same_definition(self):
        self.assertIs(setup_scan.phrases, rules.phrases)
        self.assertEqual(rules.phrases("체크포인트 기록 고쳐줘 1 a"),
                         {"체크포인트", "기록", "고쳐줘", "체크포인트 기록", "기록 고쳐줘"})


class Sessions(Base):
    def test_scope_entry_and_duplicate_filters(self):
        mine = self.session("s1", [])
        self.session("s2", [], cwd=os.path.join(self.repo, "src"))                      # 하위 폴더에서 연 세션 — 포함
        self.session("s3", [], cwd=self.repo + "-fix")                                   # 같은 접두사 다른 폴더, 저장소 언급 없음 — 제외
        self.session("s4", [], entry="sdk-cli")                                          # claude -p — 제외
        self.session("s5", [edit(self.p("src/save/save.ts"), "2026-09-02T00:00:00Z")], cwd="/elsewhere")  # 밖에서 열고 이 저장소를 고침 — 포함
        self.session("s6", [edit("/elsewhere/x.ts", "2026-09-02T00:00:00Z")], cwd="/elsewhere")          # 무관 — 세지도 않음
        self.session("s1", [user("긴 사본", "2026-09-02T00:00:00Z")], folder=re.sub(r"[^A-Za-z0-9]", "-", self.repo) + "-old")
        paths, by = candidates.session_files(self.repo)
        self.assertEqual(sorted(os.path.basename(p) for p in paths), ["s1.jsonl", "s2.jsonl", "s5.jsonl"])
        self.assertNotIn(mine, paths)  # 사본 중 더 긴 것을 쓴다
        self.assertEqual(by, {"opened_here": 2, "opened_elsewhere": 1, "non_cli": 1, "duplicate": 1})

    def test_mentions_across_chunk_boundary(self):
        f = os.path.join(self.tmp.name, "x.jsonl")
        needle = (self.repo + "/").encode()
        with mock.patch.object(candidates, "CHUNK", 7):
            for pad in range(0, 15):
                with open(f, "wb") as fh:
                    fh.write(b"a" * pad + needle + b"z")
                self.assertTrue(candidates.mentions(f, needle), pad)
            with open(f, "wb") as fh:
                fh.write(b"a" * 5 + needle[:-1] + b"z")
            self.assertFalse(candidates.mentions(f, needle))

    def test_no_home_means_no_sessions(self):
        with mock.patch.dict(os.environ, {"HOME": ""}):
            self.assertEqual(candidates.session_files(self.repo)[0], [])

    def test_read_turns(self):
        path = self.session("s1", [
            edit(self.p("src/level/map.ts"), "2026-09-01T03:00:00Z"),            # 첫 프롬프트 전 — 어느 턴에도 없음
            user("체크포인트 기록 고쳐줘", "2026-09-01T03:01:00Z"),
            edit(self.p("src/save/save.ts"), "2026-09-01T03:02:00Z"),
            edit(self.p("src/level/map.ts"), "2026-09-01T03:02:30Z", name="Read"),  # 읽기는 안 센다
            edit(self.p("HANDOFF.md"), "2026-09-01T03:02:40Z"),                   # 허브
            edit("/etc/hosts", "2026-09-01T03:02:50Z"),                           # 저장소 밖
            user("<command-name>/clear</command-name>", "2026-09-01T03:03:00Z"),
            edit(self.p("src/fx/glow.ts"), "2026-09-01T03:03:30Z"),
            user("[{\"tool_result\"}]", "2026-09-01T03:03:40Z", isMeta=True),
            {"type": "user", "timestamp": "2026-09-01T03:03:41Z",
             "message": {"content": [{"type": "tool_result", "content": "결과"}, {"type": "text", "text": "도구 결과"}]}},
            user("This session is being continued from a previous conversation", "2026-09-01T03:03:42Z"),
            user("곁가지 프롬프트", "2026-09-01T03:03:43Z", isSidechain=True),
            user("반짝이 효과", "2026-09-01T03:04:00Z"),
        ], subagent=[edit(self.p("src/fx/particle.ts"), "2026-09-01T03:05:00Z", name="Write")])
        turns = candidates.read_turns(self.repo, path)
        self.assertEqual([(t["text"], t["files"]) for t in turns],
                         [("체크포인트 기록 고쳐줘", {"src/save/save.ts"}),
                          (None, {"src/fx/glow.ts"}),
                          ("반짝이 효과", {"src/fx/particle.ts"})])
        self.assertTrue(all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", t["day"]) for t in turns))

    def test_day_is_local_date_and_naive_time_is_utc(self):
        path = self.session("s1", [user("밤 작업", "2026-09-01T23:30:00Z"), user("타임존 없음", "2026-09-02T23:30:00")])
        with mock.patch.dict(os.environ, {"TZ": "Asia/Seoul"}):
            time.tzset()
            try:
                turns = candidates.read_turns(self.repo, path)
            finally:
                os.environ.pop("TZ", None)
        time.tzset()
        self.assertEqual([t["day"] for t in turns], ["2026-09-02", "2026-09-03"])

    def test_resumed_copy_counts_once(self):
        recs = [dict(user("체크포인트 고쳐줘", f"{d}T03:00:00Z"), uuid=f"u{i}") for i, d in enumerate(DAYS)]
        self.session("s1", recs)
        self.session("s2", recs[:2])  # --resume 사본
        with mock.patch.object(candidates.compiler, "git", return_value=None):
            d = candidates.scan(self.repo)
        self.assertEqual(d["counts"]["prompt_turns"], 3)
        self.assertEqual(d["sessions_by"]["turn_copied"], 2)


class Build(Base):
    def test_alias_candidate_needs_three_days_and_unmatched_prompt(self):
        turns = [turn(d, "체크포인트 기록 고쳐줘", "src/save/save.ts") for d in DAYS]
        turns += [turn(DAYS[0], "세이브 체크포인트 손봐", "src/save/save.ts")]     # 제목으로 이미 맞음 — 관찰 아님
        turns += [turn(d, "웨이브 순서", "src/level/map.ts") for d in DAYS[:2]]  # 이틀뿐
        d = candidates.build(self.repo, turns)
        got = {(a["concept"], a["phrase"]): a for a in d["aliases"]}
        self.assertIn(("1", "체크포인트"), got)
        self.assertEqual((got[("1", "체크포인트")]["days"], got[("1", "체크포인트")]["hits"],
                          got[("1", "체크포인트")]["misfires"]), (3, 3, 0))
        self.assertFalse(any(a["concept"] == "2" for a in d["aliases"]))
        self.assertGreater(d["rejected"]["days"], 0)
        self.assertLessEqual(len([a for a in d["aliases"] if a["concept"] == "1"]), candidates.MAX_ALIASES_PER_CONCEPT)

    def test_misfire_duplicate_and_trigger_are_rejected(self):
        turns = [turn(d, "슬롯 정리 이어서 고쳐줘 스테이지", "src/save/save.ts") for d in DAYS]
        turns += [turn(d, "슬롯 얘기만", "src/fx/old.ts") for d in DAYS] + [turn(DAYS[0], "슬롯 질문")]
        d = candidates.build(self.repo, turns)
        phrases = {a["phrase"] for a in d["aliases"]}
        self.assertNotIn("슬롯", phrases)          # 다른 프롬프트 4번 > 적중 3번
        self.assertNotIn("스테이지", phrases)      # 개념 2의 별칭과 중복
        self.assertFalse(any("이어서" in p for p in phrases))  # 인계 트리거 말
        self.assertIn("고쳐줘", phrases)
        self.assertGreater(d["rejected"]["misfire"], 0)
        self.assertGreater(d["rejected"]["duplicate"], 0)

    def test_new_concept_groups_phrases_by_file_set(self):
        turns = [turn(d, "반짝이 효과 넣어", "src/fx/particle.ts", "src/fx/glow.ts", "src/level/map.ts") for d in DAYS]
        turns += [turn(DAYS[0], "반짝이 한 번", "src/fx/old.ts")]                  # 한 턴만 — 후보 파일 아님
        turns += [turn(d, "웨이브 순서", "src/fx/particle.ts") for d in DAYS[:1]]
        d = candidates.build(self.repo, turns)
        self.assertEqual(len(d["concepts"]), 1)
        c = d["concepts"][0]
        self.assertEqual(c["files"], ["src/fx/glow.ts", "src/fx/particle.ts"])
        self.assertEqual(c["related"], ["2"])
        # 날 같으면 오발화 적은 순, 상한 3개 — '반짝이'는 '반짝이 한 번' 턴(후보 파일 안 고침)에 걸려 오발화 1이라 밀린다
        self.assertEqual([n["phrase"] for n in c["names"]], ["넣어", "반짝이 효과", "효과"])
        self.assertLessEqual(len(c["names"]), candidates.MAX_NAMES)
        self.assertEqual((c["days"], c["hits"]), (3, 3))

    def test_new_concept_is_deterministic_across_hash_seeds(self):
        code = ("import sys, json; sys.path.insert(0, %r); import candidates\n"
                "T = lambda d, x, *f: {'day': d, 'text': x, 'files': set(f)}\n"
                "ts = [T(d, '반짝이 효과', 'src/fx/particle.ts', 'src/fx/glow.ts', 'src/save/save.ts') for d in %r]\n"
                "ts += [T(d, '효과 넣어', 'src/fx/particle.ts', 'src/fx/glow.ts', 'src/level/map.ts') for d in %r]\n"
                "print(json.dumps(candidates.build(%r, ts)['concepts'], ensure_ascii=False))") % (HERE, DAYS, DAYS, self.repo)
        outs = {subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                               env={**os.environ, "PYTHONHASHSEED": str(seed)}).stdout for seed in range(6)}
        self.assertEqual(len(outs), 1, outs)
        self.assertEqual(json.loads(outs.pop())[0]["related"], ["1", "2"])  # 합쳐진 구절들의 턴 전부로

    def test_two_word_phrase_only_from_adjacent_words(self):
        self.assertNotIn("checkpoint slot", rules.phrases("checkpoint.slot 봐줘"))
        self.assertNotIn("slot 체크포인트", rules.phrases("slot, 체크포인트\n기록"))
        self.assertIn("체크포인트 기록", rules.phrases("체크포인트 기록"))
        turns = [turn(d, "checkpoint.slot 봐줘", "src/save/save.ts") for d in DAYS]
        d = candidates.build(self.repo, turns)
        self.assertTrue(d["aliases"])
        for a in d["aliases"]:                     # 후보는 전부 그 프롬프트에 부분 문자열로 있다 → 승격하면 조립기가 고른다
            self.assertIn(a["phrase"], "checkpoint.slot 봐줘")

    def test_untracked_file_is_not_unbound(self):
        turns = [turn(d, "반짝이 효과", "src/fx/particle.ts", "src/fx/glow.ts") for d in DAYS]
        with mock.patch.object(candidates.compiler, "git", return_value="src/fx/particle.ts\0"):
            d = candidates.build(self.repo, turns)
        self.assertEqual([c["files"] for c in d["concepts"]], [["src/fx/particle.ts"]])  # glow.ts는 추적 안 됨

    def test_new_concept_needs_unmatched_prompt_and_existing_unbound_file(self):
        turns = [turn(d, "세이브 반짝이", "src/fx/particle.ts", "src/fx/glow.ts") for d in DAYS]   # 제목으로 맞음
        turns += [turn(d, "유령 파일", "src/gone.ts", "src/gone2.ts") for d in DAYS]              # 지금 없는 파일
        self.assertEqual(candidates.build(self.repo, turns)["concepts"], [])

    def test_dismissed_is_not_emitted(self):
        turns = [turn(d, "체크포인트", "src/save/save.ts") for d in DAYS]
        cid = candidates.cand_id("alias|1|체크포인트")
        d = candidates.build(self.repo, turns, {cid})
        self.assertEqual(d["aliases"], [])
        self.assertEqual(d["rejected"]["dismissed"], 1)

    def test_zero_reasons_are_told_apart(self):
        base = {"aliases": [], "concepts": [], "rejected": {}, "map": "CONCEPTS.md"}
        z = lambda **c: candidates.render({**base, "counts": {"sessions": 1, "turns": 1, "prompt_turns": 1, "edit_turns": 1,
                                                               "concept_turns": 1, "unbound_turns": 0, "concepts": 2,
                                                               "alias_observed": 0, "concept_observed": 0, **c}})
        self.assertIn("재료 부족", z(prompt_turns=0))
        self.assertIn("관찰 0", z())
        self.assertIn("검증에서 모두 빠졌다", z(alias_observed=3))
        d = candidates.build(self.repo, [turn(x, "슬롯 이어서 해줘", "src/save/save.ts") for x in DAYS])
        self.assertEqual(d["rejected"].get("trigger"), 3)   # '이어서'·'슬롯 이어서'·'이어서 해줘'는 관찰 전에 빠지지만 수는 남는다
        self.assertNotIn("이어서", {a["phrase"] for a in d["aliases"]})

    def test_no_map(self):
        os.remove(os.path.join(self.repo, "CONCEPTS.md"))
        d = candidates.build(self.repo, [turn(x, "반짝이", "src/fx/glow.ts", "src/fx/particle.ts") for x in DAYS])
        self.assertEqual(d["counts"]["concepts"], 0)
        self.assertEqual(d["aliases"], [])
        self.assertIn("지도", candidates.render({**d, "counts": {"sessions": 0, **d["counts"]}}))


class Promote(Base):
    def read_map(self):
        with open(os.path.join(self.repo, "CONCEPTS.md"), encoding="utf-8") as fh:
            return fh.read()

    def test_adds_field_or_appends_and_keeps_other_lines(self):
        candidates.promote_alias(self.repo, "1", "체크포인트")
        candidates.promote_alias(self.repo, "2", "웨이브")
        after = self.read_map()
        self.assertIn("· 이웃=없음 · 별칭=체크포인트\n", after)
        self.assertIn("· 별칭=스테이지, 웨이브\n", after)
        self.assertEqual([l for l in after.splitlines() if "메타" not in l], [l for l in MAP.splitlines() if "메타" not in l])
        g = compiler.graph(self.repo)
        self.assertEqual(g["nodes"]["1"]["aliases"], ["체크포인트"])
        self.assertEqual(g["nodes"]["2"]["aliases"], ["스테이지", "웨이브"])

    def test_keeps_human_written_value_and_crlf(self):
        with open(os.path.join(self.repo, "CONCEPTS.md"), "w", encoding="utf-8", newline="") as fh:
            fh.write(MAP.replace("별칭=스테이지", "별칭=스테이지(옛 이름), `맵`").replace("\n", "\r\n"))
        candidates.promote_alias(self.repo, "2", "웨이브")
        candidates.promote_alias(self.repo, "1", "체크포인트")
        with open(os.path.join(self.repo, "CONCEPTS.md"), encoding="utf-8", newline="") as fh:
            after = fh.read()
        self.assertIn("· 별칭=스테이지(옛 이름), `맵`, 웨이브\r\n", after)
        self.assertIn("· 이웃=없음 · 별칭=체크포인트\r\n", after)
        self.assertEqual(after.count("\r\n"), MAP.count("\n"))

    def test_replaces_empty_value_and_ignores_lookalike_key(self):
        with open(os.path.join(self.repo, "CONCEPTS.md"), "w", encoding="utf-8") as fh:
            fh.write(MAP.replace("· 이웃=없음\n", "· 옛별칭=세이브 · 이웃=없음 · 별칭=없음\n"))
        line = candidates.promote_alias(self.repo, "1", "체크포인트")
        self.assertTrue(line.endswith("· 옛별칭=세이브 · 이웃=없음 · 별칭=체크포인트"), line)
        self.assertEqual(compiler.graph(self.repo)["nodes"]["1"]["aliases"], ["체크포인트"])

    def test_fenced_example_section_is_not_the_concept(self):
        # 펜스 안의 '## 2.'와 메타 줄은 예시다 — 같은 번호 절로 세지도, 그 메타 줄에 쓰지도 않는다(concepts.walk와 같은 규칙)
        example = "\n```\n## 2. 예시\n- **메타**: 상태=구현 · 파일=없음 · 이웃=없음\n```\n"
        with open(os.path.join(self.repo, "CONCEPTS.md"), "w", encoding="utf-8") as fh:
            fh.write(MAP.replace("본문\n", "본문\n" + example))
        candidates.promote_alias(self.repo, "2", "웨이브")
        after = self.read_map()
        self.assertIn(example, after)
        self.assertIn("· 별칭=스테이지, 웨이브\n", after)

    def test_unclosed_fence_names_the_lost_part(self):
        with open(os.path.join(self.repo, "CONCEPTS.md"), "w", encoding="utf-8") as fh:
            fh.write(MAP.replace("본문\n", "```\n"))
        with self.assertRaises(ValueError) as e:
            candidates.promote_alias(self.repo, "2", "웨이브")
        self.assertIn("열린 채", str(e.exception))

    def test_duplicate_section_number_is_refused(self):
        with open(os.path.join(self.repo, "CONCEPTS.md"), "a", encoding="utf-8") as fh:
            fh.write("\n## 2. 레벨 사본\n\n- **메타**: 상태=구현 · 파일=없음 · 이웃=없음\n")
        with self.assertRaises(ValueError):
            candidates.promote_alias(self.repo, "2", "웨이브")

    def test_rejects_bad_input(self):
        for bad in ("a", "x, y", "x (y)", "`x`", "x · y", "없음", "x\ty", "x\ry"):
            with self.assertRaises(ValueError):
                candidates.promote_alias(self.repo, "1", bad)
        with self.assertRaises(ValueError):
            candidates.promote_alias(self.repo, "9", "체크포인트")
        with self.assertRaises(ValueError):
            candidates.promote_alias(self.repo, "2", "스테이지")
        self.assertEqual(self.read_map(), MAP)
        self.assertEqual(self.run_main(["promote-alias", "1", self.repo]), 2)               # 구절을 빼먹음
        self.assertEqual(self.run_main(["promote-alias", "1", "체크", "포인트", self.repo]), 2)  # 따옴표 없이 쪼개짐
        self.assertEqual(self.read_map(), MAP)

    def test_private_terms_and_home_path_are_refused_without_echo(self):
        cfg = os.path.join(self.tmp.name, "config")
        os.makedirs(os.path.join(cfg, "baton"))
        with open(os.path.join(cfg, "baton", "config.json"), "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "global": {"private_terms": ["홍길동"]}}, fh, ensure_ascii=False)
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": cfg}):
            for bad in ("홍길동 세이브", "/home/someone 세이브", "token=abcd1234efgh"):
                with self.assertRaises(ValueError) as e:
                    candidates.promote_alias(self.repo, "1", bad)
                self.assertNotIn(bad.split()[0], str(e.exception))  # 걸린 값을 다시 출력하지 않는다
            candidates.promote_alias(self.repo, "1", "체크포인트")  # 걸리지 않는 구절은 그대로 쓴다
            candidates.promote_alias(self.repo, "1", "Session Handoff 형식")  # 인계서 구조 검사(필수 절 등)는 별칭에 안 건다
        self.assertIn("· 별칭=체크포인트, Session Handoff 형식\n", self.read_map())


class EndToEnd(Base):
    def test_observe_validate_promote_then_compiler_picks(self):
        for i, day in enumerate(DAYS):
            self.session(f"s{i}", [
                user("체크포인트 기록 고쳐줘", f"{day}T03:00:00Z"),
                edit(self.p("src/save/save.ts"), f"{day}T03:01:00Z"),
                user("반짝이 효과 넣어", f"{day}T04:00:00Z"),
                edit(self.p("src/fx/particle.ts"), f"{day}T04:01:00Z"),
                edit(self.p("src/fx/glow.ts"), f"{day}T04:02:00Z"),
            ])
        before = sorted(os.listdir(self.repo))
        d = candidates.scan(self.repo)
        self.assertEqual(sorted(os.listdir(self.repo)), before)                  # 저장소 안에는 아무것도 안 쓴다
        self.assertTrue(d["cache"].startswith(os.path.join(self.tmp.name, "cache", "baton", "candidates")))
        with open(d["cache"], encoding="utf-8") as fh:
            raw = fh.read()
        for prompt in ("체크포인트 기록 고쳐줘", "반짝이 효과 넣어"):
            self.assertNotIn(prompt, raw)                                         # 프롬프트 원문은 안 남긴다
        self.assertEqual(os.stat(os.path.dirname(d["cache"])).st_mode & 0o777, 0o700)
        self.assertEqual(self.run_main(["scan", self.repo, "--json"]), 0)
        self.assertEqual(d["counts"]["sessions"], 3)
        self.assertIn(("1", "체크포인트"), {(a["concept"], a["phrase"]) for a in d["aliases"]})
        self.assertEqual(d["concepts"][0]["files"], ["src/fx/glow.ts", "src/fx/particle.ts"])
        self.assertIn("체크포인트", candidates.render(d))

        g = compiler.graph(self.repo)
        self.assertNotIn("1", [n for n, _, k in compiler.concept_matches(g, "체크포인트 손봐", []) if k == "prompt"])
        self.assertEqual(self.run_main(["promote-alias", "1", "체크포인트", self.repo]), 0)
        hits = compiler.concept_matches(compiler.graph(self.repo), "체크포인트 손봐", [])
        self.assertEqual(hits[0][:1] + hits[0][2:], ("1", "prompt"))
        self.assertIn("별칭 '체크포인트'", hits[0][1])

        d = candidates.scan(self.repo)                                            # 승격된 것은 다시 안 나온다
        self.assertNotIn("체크포인트", {a["phrase"] for a in d["aliases"]})
        cid = d["concepts"][0]["id"]
        self.assertEqual(self.run_main(["dismiss", cid, self.repo]), 0)
        d = candidates.scan(self.repo)
        self.assertEqual(d["concepts"], [])
        self.assertEqual([x["id"] for x in d["dismissed"]], [cid])               # 다시 만들어도 버린 목록은 이어받는다
        self.assertEqual(self.run_main(["dismiss", "deadbeef", self.repo]), 1)


if __name__ == "__main__":
    unittest.main()
