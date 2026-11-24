#!/usr/bin/env python3
"""Tests for compact_ab.py: stream parsing on the shapes seen in the 2026-11-23 probes (zero-usage compact result,
cumulative child totals), the budget guard, the arm order, the diff rules, and the hidden baton harness against a
reference implementation (so a harness bug cannot pass as a model failure)."""
import json, os, subprocess, sys, tempfile, unittest

TMP = tempfile.mkdtemp()
os.environ["CVH_DATA"] = TMP
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import compact_ab as cab  # noqa: E402


def write_stream(lines):
    fd, p = tempfile.mkstemp(suffix=".jsonl", dir=TMP)
    with os.fdopen(fd, "w") as f:
        for d in lines:
            f.write(json.dumps(d) + "\n")
        f.write("not json\n")
    return p


COMPACT = [
    {"type": "system", "subtype": "hook_started", "hook_name": "PreCompact:manual"},
    {"type": "system", "subtype": "init", "session_id": "child"},
    {"type": "system", "subtype": "compact_boundary", "compact_metadata": {"trigger": "manual", "pre_tokens": 88858, "post_tokens": 16523}},
    {"type": "result", "subtype": "success", "is_error": False, "session_id": "child", "num_turns": 0, "total_cost_usd": 0.88628,
     "usage": {"input_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 0},
     "modelUsage": {"claude-opus-5-5": {"inputTokens": 39328, "outputTokens": 5928, "cacheReadInputTokens": 112550,
                                        "cacheCreationInputTokens": 73710, "costUSD": 0.88628}}},
]
PARENT = {"inputTokens": 4, "outputTokens": 2074, "cacheReadInputTokens": 63244, "cacheCreationInputTokens": 73116, "cost": 0.63907}


class ParseTest(unittest.TestCase):
    def test_compact_result_cost_lives_in_modelusage(self):
        p = cab.parse(write_stream(COMPACT))
        self.assertEqual(p["boundary"][0]["pre_tokens"], 88858)
        self.assertEqual(p["turns"], 0)
        d = cab.delta(cab.usage_of(p["result"]), PARENT)
        self.assertAlmostEqual(d["cost"], 0.24721, places=5)
        self.assertEqual(d["inputTokens"], 39324)
        self.assertEqual(d["cacheCreationInputTokens"], 594)

    def test_turns_by_message_id_and_hook_injection(self):
        msg = lambda mid, cc, cr: {"type": "assistant", "message": {"id": mid, "usage": {"input_tokens": 2, "cache_creation_input_tokens": cc, "cache_read_input_tokens": cr}}}
        p = cab.parse(write_stream([
            {"type": "system", "subtype": "hook_response", "hook_event": "UserPromptSubmit", "stdout": "[baton] handoff ..."},
            msg("m1", 1739, 87054), msg("m1", 1739, 87054), msg("m2", 5570, 88793),
            {"type": "assistant", "parent_tool_use_id": "x", "message": {"id": "sub", "usage": {"input_tokens": 9}}},
        ]))
        self.assertEqual(p["turns"], 2)
        self.assertEqual(p["first"]["cache_read_input_tokens"], 87054)
        self.assertEqual(p["last_ctx"], 2 + 5570 + 88793)
        self.assertTrue(p["inject"])

    def test_rate_limit_only_on_error(self):
        ok = {"result": {"is_error": False, "result": "we discussed the rate limit"}}
        bad = {"result": {"is_error": True, "result": "You've hit your session limit"}}
        self.assertFalse(cab.rate_limited(ok, ""))
        self.assertTrue(cab.rate_limited(bad, ""))
        self.assertTrue(cab.rate_limited({"result": None}, "API Error: 529 overloaded"))


class BudgetTest(unittest.TestCase):
    def test_guard(self):
        cab.guard(4.0, total=72.4)
        with self.assertRaises(cab.Stop):
            cab.guard(4.0, total=72.6)

    def test_ledger_starts_with_probes(self):
        cab.ledger_add(dict(kind="next", tag="x", charged=1.25))
        self.assertAlmostEqual(cab.spent(), cab.PROBE_USD + 1.25)


class OrderTest(unittest.TestCase):
    def test_abba(self):
        self.assertEqual("".join(a for a, _ in cab.order(5, "C")), "CHHCCHHCCH")
        self.assertEqual("".join(a for a, _ in cab.order(5, "H")), "HCCHHCCHHC")
        self.assertEqual(cab.order(2, "C"), [("C", 1), ("H", 1), ("H", 2), ("C", 2)])

    def test_round2_keeps_one_arm(self):
        self.assertEqual(cab.order(5, "H", "H"), [("H", i) for i in range(1, 6)])
        self.assertEqual(cab.order(5, "C", "H"), [("H", i) for i in range(1, 6)])


class Round2Test(unittest.TestCase):
    def test_parse_reads_baton_version_and_stop_blocks(self):
        p = cab.parse(write_stream([
            {"type": "system", "subtype": "init", "plugins": [{"name": "omc", "version": "5"}, {"name": "baton", "version": "1.0.0-beta.5"}]},
            {"type": "system", "subtype": "hook_response", "hook_event": "Stop", "stdout": '{"continue":true}'},
            {"type": "system", "subtype": "hook_response", "hook_event": "Stop", "stdout": '{"decision": "block", "reason": "x"}'},
        ]))
        self.assertEqual((p["baton"], p["stop_blocks"]), ("1.0.0-beta.5", 1))
        self.assertEqual(cab.parse(write_stream([{"type": "system", "subtype": "init"}]))["baton"], None)

    def test_seed_copies_only_the_kept_arm(self):
        src = tempfile.mkdtemp(dir=TMP)
        s_file = os.path.join(src, "S.jsonl")
        open(s_file, "w").write("x")
        build = dict(done=True, sid="S", project_dir=src, S_file=dict(size=1, mtime=os.path.getmtime(s_file)))
        os.makedirs(os.path.join(src, "state"))
        rows = {"C1": {"arm": "C", "ok": True}, "H1": {"arm": "H", "ok": True}}
        json.dump(dict(snapshot={}, repo="/r", build=build, transitions=rows, next=rows), open(os.path.join(src, "state", "seedt.json"), "w"))
        cab.cmd_seed(type("A", (), dict(src=src, name="seedt", keep="C"))())
        st = cab.load_state("seedt")
        self.assertEqual((sorted(st["transitions"]), sorted(st["next"])), (["C1"], ["C1"]))
        self.assertEqual(st["build"]["sid"], "S")
        with self.assertRaises(SystemExit):  # never overwrites
            cab.cmd_seed(type("A", (), dict(src=src, name="seedt", keep="C"))())


DIFF = """diff --git a/lib/handoff_stats.py b/lib/handoff_stats.py
--- a/lib/handoff_stats.py
+++ b/lib/handoff_stats.py
@@ -1,1 +1,2 @@
 x
+from dateutil import parser
diff --git a/hooks/handoff-inject.py b/hooks/handoff-inject.py
--- a/hooks/handoff-inject.py
+++ b/hooks/handoff-inject.py
@@ -1,1 +1,1 @@
-a
+b
"""


class RulesTest(unittest.TestCase):
    def test_rules(self):
        spec = json.load(open(os.path.join(HERE, "compact_ab", "baton.json")))
        got = cab.rules_check(spec["rules"], DIFF, [("Bash", {"command": "ls"})])
        self.assertEqual(got, {"F3": False, "F4": False})
        clean = "diff --git a/lib/handoff_stats.py b/lib/handoff_stats.py\n@@ -1 +1 @@\n+# no dateutil here\n"
        self.assertEqual(cab.rules_check(spec["rules"], clean, [("Bash", {"command": "pip install x"})]), {"F3": True, "F4": False})
        self.assertEqual(cab.rules_check(spec["rules"], clean, []), {"F3": True, "F4": True})
        quoted = [("Bash", {"command": "cat > HANDOFF.md <<'EOF'\n- never pip install anything\nEOF"})]
        self.assertEqual(cab.rules_check(spec["rules"], clean, quoted), {"F3": True, "F4": True})
        ran = [("Bash", {"command": "cd lib && python3 -m pip install python-dateutil"})]
        self.assertEqual(cab.rules_check(spec["rules"], clean, ran), {"F3": True, "F4": False})


REFERENCE = '''"""Summarize a handoff.

Usage:
  python3 lib/handoff_stats.py <path> [--min-date YYYY-MM-DD|YYYY.MM.DD]
"""
import argparse, re, sys
D = re.compile(r"(\\d{4})[-.](\\d{2})[-.](\\d{2})")
def sections(t):
    out = []
    for ln in t.splitlines():
        if ln.startswith("## "): out.append([ln[3:], []])
        elif out: out[-1][1].append(ln)
    return out
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("path"); ap.add_argument("--min-date")
    a = ap.parse_args(); secs = sections(open(a.path).read())
    if a.min_date:
        lo = D.search(a.min_date).groups()
        secs = [s for s in secs if D.search(s[0]) and D.search(s[0]).groups() >= lo]
        if not secs: print(f"baton: no sections on or after {a.min_date}"); return
    body = "\\n".join(l for s in secs for l in s[1])
    print(f"baton: sections={len(secs)} open={body.count('- [ ]')} done={body.count('- [x]')}")
main()
'''


class HiddenHarnessTest(unittest.TestCase):
    def run_hidden(self, src):
        with tempfile.TemporaryDirectory() as r:
            os.makedirs(os.path.join(r, "lib"))
            with open(os.path.join(r, "lib", "handoff_stats.py"), "w") as f:
                f.write(src)
            out = subprocess.run([sys.executable, "-I", os.path.join(HERE, "compact_ab", "baton_hidden.py"), r],
                                 capture_output=True, text=True, timeout=120).stdout
            return json.loads(out.strip().splitlines()[-1])

    def test_reference_passes_everything(self):
        got = self.run_hidden(REFERENCE)
        for k in ("baseline", "core", "F1", "F2", "F5", "F6"):
            self.assertTrue(got[k], k)
        self.assertEqual(got["core_any"], "--min-date")

    def test_wrong_flag_name_fails_core_and_F2_but_is_diagnosed(self):
        got = self.run_hidden(REFERENCE.replace("--min-date", "--since").replace("a.min_date", "a.since"))
        self.assertFalse(got["core"])
        self.assertFalse(got["F2"])
        self.assertEqual(got["core_any"], "--since")

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as r:
            out = subprocess.run([sys.executable, "-I", os.path.join(HERE, "compact_ab", "baton_hidden.py"), r],
                                 capture_output=True, text=True, timeout=60).stdout
            got = json.loads(out.strip().splitlines()[-1])
        self.assertFalse(any(v for k, v in got.items() if k != "core_any"))


def _state(cc, hc, ck, hk):
    tr, nx = {}, {}
    for arm, costs, ks in (("C", cc, ck), ("H", hc, hk)):
        for i, (x, kk) in enumerate(zip(costs, ks), 1):
            tr[f"{arm}{i}"] = {"arm": arm, "delta": {"cost": 0.5, "inputTokens": 0}, "first": {}}
            nx[f"{arm}{i}"] = {"arm": arm, "ok": True, "correct": kk, "delta": {"cost": x}}
    return {"transitions": tr, "next": nx}


class VerdictTest(unittest.TestCase):
    def test_rule(self):
        f = lambda v: [v] * 5
        v = lambda *s: cab.verdict({str(i): x for i, x in enumerate(s)}).split("  ")[0]
        self.assertEqual(v(_state(f(2.0), f(1.2), f(1), f(1)), _state(f(2.0), f(1.3), f(1), f(1))), "VERDICT: handoff better")
        self.assertEqual(v(_state(f(2.0), f(2.0), f(1), f(1)), _state(f(2.0), f(1.9), f(1), f(1))), "VERDICT: no difference detected")
        self.assertEqual(v(_state(f(1.2), f(2.0), f(1), f(1)), _state(f(1.3), f(2.0), f(1), f(1))), "VERDICT: compact better")
        self.assertEqual(v(_state(f(2.0), f(2.0), f(1), [0, 0, 1, 0, 1]), _state(f(2.0), f(2.0), f(1), [0, 1, 0, 1, 1])), "VERDICT: compact better")
        self.assertTrue(v(_state(f(2.0), f(1.0), f(1), f(1))).startswith("VERDICT: inconclusive"))


if __name__ == "__main__":
    unittest.main()
