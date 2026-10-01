#!/usr/bin/env python3
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import usage_week


def user(text, ts="2026-09-29T01:00:00Z", **kw):
    return {"type": "user", "timestamp": ts, "cwd": kw.pop("cwd", "/Users/x/repo"), "entrypoint": kw.pop("entrypoint", "cli"),
            "message": {"content": text}, **kw}


def asst(mid, inp, cache_read=0, sidechain=False, tool=None, bash=None, model="claude-x"):
    content = []
    if tool: content.append({"type": "tool_use", "name": "Read", "input": tool if isinstance(tool, dict) else {"file_path": tool}})
    if bash: content.append({"type": "tool_use", "name": "Bash", "input": {"command": bash}})
    return {"type": "assistant", "isSidechain": sidechain,
            "message": {"id": mid, "model": model, "content": content, "usage": {"input_tokens": inp, "cache_read_input_tokens": cache_read}}}


def hook(content, event="UserPromptSubmit"):
    return {"type": "attachment", "attachment": {"type": "hook_success", "hookEvent": event, "content": content}}


def write_jsonl(path, records):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


class UsageWeekTest(unittest.TestCase):
    def session(self, records):
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        self.addCleanup(os.unlink, f.name)
        return usage_week.session_of(f.name)

    def reread(self, *calls):
        return self.session([user("이어서")] + list(calls))["reread"]

    def test_same_message_id_counted_once(self):
        s = self.session([user("이 버그 고쳐줘"), asst("m1", 100, 900), asst("m1", 100, 900), asst("m2", 50, 1000)])
        self.assertEqual(s["calls"], 2)
        self.assertEqual(s["tokens"], 2050)
        self.assertEqual(s["first"], 1000)

    def test_sidechain_and_synthetic_calls_excluded(self):
        s = self.session([user("이 버그 고쳐줘"), asst("m1", 10), asst("sub", 999, sidechain=True), asst("syn", 0, model="<synthetic>")])
        self.assertEqual((s["calls"], s["tokens"]), (1, 10))

    def test_status_session_uses_hook_trigger_on_first_prompt_only(self):
        self.assertTrue(self.session([user("이어서 진행하자"), asst("m1", 1)])["status"])
        self.assertFalse(self.session([user("이 버그 고쳐줘"), user("어디까지 했어?"), asst("m1", 1)])["status"])

    def test_other_named_handoff_is_not_a_status_session(self):
        for p in ("HANDOFF-draft.md 읽고 이어서 해줘", "HANDOFF-draft 파일을 읽고 이어서 제작해줘"):
            s = self.session([user(p), asst("m1", 1)])
            self.assertFalse(s["status"], p); self.assertTrue(s["other_handoff"], p)

    def test_injection_detected_only_from_prompt_hook(self):
        self.assertTrue(self.session([user("이어서"), hook("[baton] 아래는 이 저장소 HANDOFF.md의 전문이다"), asst("m1", 1)])["injected"])
        self.assertFalse(self.session([user("이어서"), hook("[baton] 아래는 …", event="SessionStart"), asst("m1", 1)])["injected"])

    def test_non_prompt_records_are_not_the_first_prompt(self):
        s = self.session([user("<command-name>/clear</command-name>"), user("This session is being continued from 이어서"),
                          user("요약", isCompactSummary=True), user("이 버그 고쳐줘"), asst("m1", 1)])
        self.assertFalse(s["status"])

    def test_no_calls_or_no_prompt_returns_none(self):
        self.assertIsNone(self.session([user("안녕")]))
        self.assertIsNone(self.session([asst("m1", 1)]))

    def test_open_window_tokens(self):
        s = self.session([user("이어서")] + [asst(f"m{i}", 10) for i in range(7)])
        self.assertEqual((s["open"], s["tokens"], s["reread"]), (50, 70, None))

    def test_reread_counts_real_reads_only(self):
        self.assertEqual(self.reread(asst("m1", 1, tool="/r/HANDOFF.md")), "full")
        self.assertEqual(self.reread(asst("m1", 1, bash='cd /r && cat "HANDOFF.md" | wc -l')), "full")
        self.assertEqual(self.reread(asst("m1", 1, tool={"file_path": "/r/HANDOFF.md", "offset": 200})), "partial")
        self.assertEqual(self.reread(asst("m1", 1, bash="sed -n '200,260p' HANDOFF.md")), "partial")
        self.assertIsNone(self.reread(asst("m1", 1, bash="ls -la HANDOFF.md hooks/")))
        self.assertIsNone(self.reread(asst("m1", 1, bash="find . -newer HANDOFF.md -type f")))
        self.assertIsNone(self.reread(asst("m1", 1, tool="/r/HANDOFF_old.md")))
        self.assertEqual(self.reread(asst("m1", 1, bash="cat HANDOFF.md | head -250")), "partial")
        self.assertEqual(self.reread(asst("m1", 1, bash="rtk proxy cat HANDOFF.md")), "full")
        for w in ("cat > HANDOFF.md <<'EOF'\nx\nEOF", "cat a b > HANDOFF.md", "sed -i '' 's/a/b/' HANDOFF.md", "sed 's/^/l /' > $T/HANDOFF.md"):
            self.assertIsNone(self.reread(asst("m1", 1, bash=w)), w)

    def test_reread_after_open_window_is_ignored(self):
        self.assertIsNone(self.reread(*[asst(f"m{i}", 1) for i in range(5)], asst("m9", 1, tool="/r/HANDOFF.md")))

    def test_runner_and_temp_sessions_are_experimental(self):
        self.assertTrue(usage_week.experimental("/Users/x/baton/.data/snapshots/case-a"))
        self.assertTrue(usage_week.experimental("/Users/x/baton/.data/ctx-breakdown/base-0"))
        self.assertTrue(usage_week.experimental("/private/tmp/claude-501/x/scratchpad"))
        self.assertTrue(usage_week.experimental(None))
        self.assertFalse(usage_week.experimental("/Users/x/Documents/repo"))

    def test_collect_dedups_copies_and_drops_non_cli(self):
        with tempfile.TemporaryDirectory() as home:
            proj = os.path.join(home, ".claude", "projects")
            write_jsonl(os.path.join(proj, "a", "s1.jsonl"), [user("이어서"), asst("m1", 5)])
            write_jsonl(os.path.join(proj, "b", "s1.jsonl"), [user("이어서"), asst("m1", 5), asst("m2", 5)])
            write_jsonl(os.path.join(proj, "a", "s3.jsonl"), [user("이어서", entrypoint="claude-vscode"), asst("m1", 5)])
            write_jsonl(os.path.join(proj, "a", "s2.jsonl"), [user("이어서", entrypoint="sdk-cli"), asst("m1", 5)])
            with mock.patch.dict(os.environ, {"HOME": home}):
                out, sk = usage_week.collect()
        self.assertEqual(sorted((os.path.basename(s["file"]), s["calls"]) for s in out), [("s1.jsonl", 2), ("s3.jsonl", 1)])
        self.assertEqual((sk["duplicate"], sk["non_cli"]), (1, 1))

    def test_start_is_local_time(self):
        with mock.patch.dict(os.environ, {"TZ": "Asia/Seoul"}):
            import time; time.tzset()
            s = self.session([user("이어서", ts="2026-09-06T15:30:00Z"), asst("m1", 1)])  # KST 월 00:30
        time.tzset()
        self.assertEqual(s["start"].isocalendar()[1], 37)


if __name__ == "__main__":
    unittest.main()
