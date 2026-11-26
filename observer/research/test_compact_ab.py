#!/usr/bin/env python3
"""Tests for compact_ab.py: stream parsing on the shapes seen in the 2026-11-23 probes (zero-usage compact result,
cumulative child totals), the budget guard, the arm order, the diff rules, and the hidden baton harness against a
reference implementation (so a harness bug cannot pass as a model failure)."""
import json, os, subprocess, sys, tempfile, unittest

TMP = tempfile.mkdtemp()
os.environ["CVH_DATA"] = TMP
os.environ.update(CVH_CAP_USD="77", CVH_PROBE_USD="2.902")  # the round-1 defaults, whatever the shell exports
for k in ("CVH_BATON", "CVH_OMC", "CVH_CLI", "CVH_SNAPS", "CVH_MODEL", "CVH_EFFORT", "CVH_CLAUDE_BIN", "CVH_LOCK_HELD"):
    os.environ.pop(k, None)
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

    def test_seed_multi_source(self):
        """Round 3: C rows from one folder, H rows from another; C transcripts backed up with sha256, H patches
        copied, next rows kept as t1, `next` empty, the sources never written, and an existing state never replaced."""
        pdir = tempfile.mkdtemp(dir=TMP)
        for sid in ("S", "c1"):
            open(os.path.join(pdir, sid + ".jsonl"), "w").write(sid)
        build = dict(done=True, sid="S", project_dir=pdir, S_file=dict(size=1, mtime=os.path.getmtime(os.path.join(pdir, "S.jsonl"))))
        srcs = []
        for arm, extra in (("C", {"sid": "c1"}), ("H", {})):
            src = tempfile.mkdtemp(dir=TMP)
            os.makedirs(os.path.join(src, "state"))
            os.makedirs(os.path.join(src, "runs", "seedt"))
            open(os.path.join(src, "runs", "seedt", "H1.patch"), "w").write("diff --git a/HANDOFF.md b/HANDOFF.md\n")
            rows = {"C1": dict(arm="C", ok=True, **({"sid": "c1"} if arm == "C" else {})), "H1": {"arm": "H", "ok": True}}
            nx = {t: dict(r, total={"cost": 1.0}) for t, r in rows.items()}
            json.dump(dict(snapshot={}, repo="/r", build=build, transitions=rows, next=nx), open(os.path.join(src, "state", "seedt.json"), "w"))
            srcs.append(f"{src}:{arm}")
        before = {f: open(os.path.join(src, "state", "seedt.json")).read() for src in (x.rsplit(":", 1)[0] for x in srcs) for f in [src]}
        cab.cmd_seed(type("A", (), dict(sources=srcs, name="seedt"))())
        st = cab.load_state("seedt")
        self.assertEqual(sorted(st["transitions"]), ["C1", "H1"])
        self.assertEqual(st["transitions"]["C1"]["reused_from"], srcs[0].rsplit(":", 1)[0])
        self.assertEqual(sorted(st["t1"]), ["C1", "H1"])
        self.assertEqual(st["next"], {})
        self.assertEqual(sorted(st["parents"]), ["S", "c1"])
        self.assertTrue(os.path.exists(os.path.join(cab.DATA, "backup", "seedt", "c1.jsonl")))
        self.assertEqual(st["transitions"]["H1"]["patch_sha256"], cab.sha256_file(os.path.join(cab.DATA, "runs", "seedt", "H1.patch")))
        self.assertEqual(before, {src: open(os.path.join(src, "state", "seedt.json")).read() for src in before})
        with self.assertRaises(SystemExit):  # never overwrites
            cab.cmd_seed(type("A", (), dict(sources=srcs, name="seedt"))())
        open(os.path.join(pdir, "c1.jsonl"), "a").write("changed")
        with self.assertRaises(cab.Stop):  # a reused compaction must stay byte-identical
            cab.check_parents(st)


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


# ---------------- round 3 and W ----------------
def git_repo():
    r = tempfile.mkdtemp(dir=TMP)
    g = lambda *a, env=None: subprocess.run(["git", "-C", r, *a], check=True, capture_output=True, text=True,
                                            env={**os.environ, **(env or {})}).stdout.strip()
    g("init", "-q")
    return r, g


ME = {"GIT_AUTHOR_NAME": "build", "GIT_AUTHOR_EMAIL": "build@local", "GIT_COMMITTER_NAME": "build", "GIT_COMMITTER_EMAIL": "build@local"}


class StartStateTest(unittest.TestCase):
    def test_drop_files_keeps_parent_message_author(self):
        r, g = git_repo()
        open(os.path.join(r, "a.txt"), "w").write("a")
        g("add", "-A"); g("commit", "-qm", "first", env=ME)
        open(os.path.join(r, "HANDOFF.md"), "w").write("written by the build session")
        open(os.path.join(r, "b.txt"), "w").write("b")
        g("add", "-A"); g("commit", "-qm", "post-build (uncommitted work)", env=ME)
        b1 = g("rev-parse", "HEAD")
        new = cab.drop_files(r, b1, ["HANDOFF.md"])
        self.assertEqual(g("ls-tree", "--name-only", new).split(), ["a.txt", "b.txt"])
        for fmt in ("%P", "%B", "%an %ae %aI", "%cn %ce %cI"):
            self.assertEqual(g("log", "-1", f"--format={fmt}", new), g("log", "-1", f"--format={fmt}", b1))
        self.assertEqual(g("rev-parse", "HEAD"), b1)  # HEAD is not moved; fresh() resets to the new base later
        self.assertEqual(g("rev-parse", "refs/exp/start"), new)

    def test_materialize_applies_the_patch_outside_the_repo(self):
        r, g = git_repo()
        open(os.path.join(r, "HANDOFF.md"), "w").write("old\n")
        g("add", "-A"); g("commit", "-qm", "b1", env=ME)
        b1 = g("rev-parse", "HEAD")
        open(os.path.join(r, "HANDOFF.md"), "w").write("new\n")
        patch = os.path.join(TMP, "h.patch")
        open(patch, "w").write(g("diff", "HEAD") + "\n")
        g("checkout", "-q", "--", "HANDOFF.md")
        self.assertEqual(cab.materialize(r, b1, patch), b"new\n")
        self.assertEqual(open(os.path.join(r, "HANDOFF.md")).read(), "old\n")  # the snapshot is untouched
        open(patch, "a").write("diff --git a/x b/x\n")
        with self.assertRaises(cab.Stop):  # one file only
            cab.materialize(r, b1, patch)

    def test_fact_tags(self):
        r, g = git_repo()
        open(os.path.join(r, "lib.py"), "w").write('"""stdlib only."""\n')
        g("add", "-A"); g("commit", "-qm", "x", env=ME)
        tags = cab.fact_tags(r, {"F1": r"\d{4}\.\d{2}\.\d{2}", "F4": "stdlib"})
        self.assertEqual((tags["F1"]["tag"], tags["F4"]["tag"], tags["F4"]["files"]), ("conversation-only", "also-in-repo", ["lib.py"]))


def transcript_rows(t1=True):
    u = lambda uid, parent, content, **k: dict(type="user", uuid=uid, parentUuid=parent, message={"content": content}, **k)
    rows = [u("s1", None, "build prompt"), {"type": "system", "subtype": "compact_boundary", "uuid": "b"},
            u("sum", "b", "This session is being continued", isCompactSummary=True),
            u("cav", "s1", "<local-command-caveat>x</local-command-caveat>", isMeta=True),
            u("cmd", "cav", "<command-name>/compact</command-name>"),
            {"type": "attachment", "uuid": "att", "parentUuid": "cmd"}]
    if t1:
        rows += [u("t1p", "att", "이어서 해줘"), {"type": "assistant", "uuid": "t1a", "parentUuid": "t1p"},
                 u("tr", "t1a", [{"type": "tool_result", "content": "ok"}])]
    return rows


class CutTest(unittest.TestCase):
    def write(self, rows):
        fd, p = tempfile.mkstemp(suffix=".jsonl", dir=TMP)
        with os.fdopen(fd, "w") as f:
            for d in rows:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
        return p

    def test_cut_is_the_entry_before_the_first_real_prompt(self):
        self.assertEqual(cab.cut_of(self.write(transcript_rows())), {"at": "att", "drops": "t1p", "prompt": "이어서 해줘",
                                                                     "discard_entries": 3, "discard_prompts": ["이어서 해줘"]})
        later = transcript_rows() + [dict(type="user", uuid="u2", parentUuid="tr", message={"content": "알아서 판단해서 진행해줘"})]
        self.assertEqual(cab.cut_of(self.write(later))["discard_prompts"], ["이어서 해줘", "알아서 판단해서 진행해줘"])
        with self.assertRaises(cab.Stop):
            cab.cut_of(self.write(transcript_rows()[:1]))

    def test_cut_problems(self):
        pdir = tempfile.mkdtemp(dir=TMP)
        fork = transcript_rows(t1=False) + [dict(type="user", uuid="n1", parentUuid="att", message={"content": "지난번 작업에 이어서"})]
        open(os.path.join(pdir, "fork.jsonl"), "w").write("\n".join(json.dumps(d, ensure_ascii=False) for d in fork))
        st = {"build": {"project_dir": pdir}, "transitions": {"C1": {"sid": "c1", "cut": {"at": "att", "drops": "t1p", "prompt": "이어서 해줘"}}}}
        p = {"result": {"session_id": "fork"}, "first": {"a": 60000}}
        self.assertEqual(cab.cut_problems(st, "C1", p, {"a": 62000}), [])
        self.assertEqual(len(cab.cut_problems(st, "C1", p, {"a": 70000})), 1)  # first turn off by > 10%
        self.assertEqual(cab.cut_problems(st, "C1", {"result": {"session_id": "c1"}, "first": None}, None), ["no new session id"])
        open(os.path.join(pdir, "bad.jsonl"), "w").write("\n".join(json.dumps(d, ensure_ascii=False) for d in transcript_rows()))
        self.assertEqual(len(cab.cut_problems(st, "C1", {"result": {"session_id": "bad"}, "first": None}, None)), 2)


class Round3Test(unittest.TestCase):
    def test_order_with_z_and_pilot(self):
        self.assertEqual(cab.order(2, "C", z=1), [("Z", 1), ("C", 1), ("H", 1), ("H", 2), ("C", 2)])
        self.assertEqual(cab.pilot_order("C"), [("Z", 1), ("C", 1), ("H", 1)])
        self.assertEqual(cab.pilot_order("H"), [("Z", 1), ("H", 1), ("C", 1)])

    def test_parse_reads_versions_and_plugins(self):
        p = cab.parse(write_stream([{"type": "system", "subtype": "init", "claude_code_version": "2.1.331",
                                     "skills": ["a", "baton:baton", "baton:driftmap"],
                                     "plugins": [{"name": "oh-my-claudecode", "version": "5.8.7", "source": "oh-my-claudecode@omc", "path": "/o"},
                                                 {"name": "baton", "version": "1.0.0", "source": "baton@inline", "path": TMP}]}]))
        self.assertEqual((p["cli"], p["omc"], p["baton"], p["skills"]), ("2.1.331", "5.8.7", "1.0.0", ["baton:baton", "baton:driftmap"]))
        self.assertIsNone(cab.plugin_problem(p, TMP))
        self.assertIn("not the staged build", cab.plugin_problem(p, "/elsewhere"))
        p["plugins"].append({"name": "baton", "version": "1.0.0", "source": "baton@baton", "path": "/i"})
        self.assertEqual(cab.plugin_problem(p, TMP), "2 baton plugins loaded")
        old = cab.OMC_REQUIRED
        try:
            cab.OMC_REQUIRED = "5.8.4"
            self.assertIn("OMC 5.8.7 loaded, 5.8.4 required", cab.version_problem(p))
        finally:
            cab.OMC_REQUIRED = old
        p["plugins"] = p["plugins"][:2]
        self.assertIn("session-only plugin(s) ['baton']", cab.version_problem(p))  # staged baton only with plugin_dir
        self.assertIsNone(cab.version_problem(p, TMP))
        p["plugins"].append({"name": "host-view", "version": "0.2.0", "source": "host-view@inline", "path": "/h"})
        self.assertIn("['host-view']", cab.version_problem(p, TMP))
        old = (cab.BATON_REQUIRED, cab.BATON_INSTALLED)
        try:  # W2: staged 1.0.0 (CVH_BATON) and installed 0.9 (CVH_BATON_INSTALLED) are checked apart
            cab.BATON_REQUIRED, cab.BATON_INSTALLED = "1.0.0", "0.9"
            p["plugins"] = p["plugins"][:2]
            self.assertIsNone(cab.version_problem(p, TMP))
            self.assertIn("baton 1.0.0 loaded, 0.9 required", cab.version_problem(p))
        finally:
            cab.BATON_REQUIRED, cab.BATON_INSTALLED = old
            p["plugins"].append({"name": "host-view", "version": "0.2.0", "source": "host-view@inline", "path": "/h"})
        os.environ["CLAUDE_CODE_PLUGIN_DIRS"] = "/h"
        try:
            self.assertNotIn("CLAUDE_CODE_PLUGIN_DIRS", cab.child_env())
            self.assertEqual(cab.child_env()["BATON_OBSERVE"], "off")
        finally:
            del os.environ["CLAUDE_CODE_PLUGIN_DIRS"]

    def test_cost_lines(self):
        t_c = {"arm": "C", "delta": {"cost": 1.1, "inputTokens": 227000, "cacheReadInputTokens": 12000}, "first": {}}
        t_h = {"arm": "H", "delta": {"cost": 2.4, "inputTokens": 2, "cacheReadInputTokens": 0}, "first": {"cache_creation_input_tokens": 230000}}
        r = {"delta": {"cost": 1.3}, "first": {"cache_read_input_tokens": 14000}}
        st = {"transitions": {"C1": t_c, "H1": t_h}}
        cold = 1.3 + 14000 * (8.00e-6 - 0.201e-6)
        self.assertAlmostEqual(cab.next_cold(r), cold)
        self.assertAlmostEqual(cab.run_cost(st, "C1", r, "morning"), 1.1 + 12000 * (3.96e-6 - 0.201e-6) + cold)
        self.assertAlmostEqual(cab.run_cost(st, "C1", r, "evening"), 1.1 - 227000 * (3.96e-6 - 0.201e-6) + cold)
        self.assertAlmostEqual(cab.run_cost(st, "H1", r, "morning"), cab.run_cost(st, "H1", r, "evening"))
        self.assertAlmostEqual(cab.run_cost(st, "H1", r, "evening"), 2.4 - 230000 * (8.00e-6 - 0.201e-6) + cold)
        self.assertAlmostEqual(cab.run_cost(st, "C1", r, "raw"), 2.4)
        self.assertAlmostEqual(cab.run_cost(st, "C1", r, False), 2.4)  # old API

    def test_verdict_ignores_z_and_reads_t1(self):
        f = lambda v: [v] * 5
        sts = [_state(f(2.0), f(1.2), f(1), f(1)), _state(f(2.0), f(1.3), f(1), f(1))]
        for st in sts:
            st["next"]["Z1"] = {"arm": "Z", "ok": True, "correct": True, "delta": {"cost": 0.1}}
            st["t1"], st["next"] = st["next"], {}
        v = cab.verdict({str(i): x for i, x in enumerate(sts)}, "raw", "T1").split("  ")[0]
        self.assertEqual(v, "VERDICT: handoff better")
        self.assertTrue(cab.verdict({str(i): x for i, x in enumerate(sts)}, "raw", "T2").startswith("VERDICT: inconclusive"))

    def test_handoff_reads_and_diagnostics(self):
        calls = [("Read", {"file_path": "/s/HANDOFF.md"}), ("Bash", {"command": "cat HANDOFF.md | head"}),
                 ("Bash", {"command": "git add HANDOFF.md"}), ("Read", {"file_path": "/s/lib/x.py"})]
        self.assertEqual(cab.handoff_reads(calls), 2)
        diff = "diff --git a/lib/handoff_stats.py b/lib/handoff_stats.py\n@@ -1 +1,2 @@\n x\n+    p.add_argument('--min-date')\n"
        got = cab.diagnostics({"diag": {"step4": "--min-date", "since": "--since"}}, diff, calls)
        self.assertEqual(got, {"handoff_reads": 2, "third_carrier": [], "step4": True, "since": False})

    def test_baton_t2_prompt_triggers_injection(self):
        spec = json.load(open(os.path.join(HERE, "compact_ab", "baton_t2.json")))
        sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
        import rules
        self.assertIn("이어서", rules.trigger_words(TMP, spec["next_prompt"]))

    def test_baton_t2_grader_self_test(self):
        spec = cab.load_spec(os.path.join(HERE, "compact_ab", "baton_t2.json"))
        got = cab.selftest(spec, TMP)
        self.assertEqual(len(got), 8)
        for good, line in got:
            self.assertTrue(good, line)
        spec["selftest"]["mutants"]["core2"] = [["no such text", "x"]]
        self.assertFalse(all(g for g, _ in cab.selftest(spec, TMP)))  # a mutant that edits nothing fails loudly


class GateTest(unittest.TestCase):
    def setup(self, z_correct=False, cost=2.0, carriers=(5, 5)):
        paths = []
        for (name, start), nc in zip((("ga", "C"), ("gb", "H")), carriers):
            sp = os.path.join(TMP, f"{name}.json")
            json.dump({"name": name, "start": start, "hard": ["core2", "F1"]}, open(sp, "w"))
            row = lambda arm, ok=True: {"arm": arm, "ok": True, "correct": ok, "checks": {"core2": True}, "delta": {"cost": cost}}
            tr = {f"{arm}{i}": {"arm": arm, "ok": True} for arm, k in (("C", nc), ("H", 5)) for i in range(1, k + 1)}
            cab.save_state(name, {"transitions": tr, "t1": {}, "start": {"base": "b"},
                                  "next": {"Z1": row("Z", z_correct), "C1": row("C"), "H1": row("H")}})
            paths.append(sp)
        return type("A", (), dict(spec=paths, revised=None))()

    def test_gate_picks_n_by_simulating_the_guard(self):
        old = cab.CAP_USD
        try:
            a = self.setup()
            cab.CAP_USD = 1000.0
            cab.cmd_gate(a)
            self.assertEqual(cab.load_state("ga")["gate"]["n"], 5)
            cab.CAP_USD = cab.spent() + 30  # n=4 needs 11 runs x 2.2 + 4.5 before the last one; n=5 needs 15 x 2.2 + 4.5
            cab.cmd_gate(a)
            self.assertEqual(cab.load_state("gb")["gate"]["n"], 5)  # decided once: a rerun keeps n
            a = self.setup()
            cab.cmd_gate(a)
            self.assertEqual(cab.load_state("gb")["gate"]["n"], 4)
            cab.CAP_USD = cab.spent() + 3.0
            with self.assertRaises(cab.Stop):
                cab.cmd_gate(self.setup())
            with self.assertRaises(cab.Stop):  # Z1 correct: revise T2
                cab.CAP_USD = 1000.0
                cab.cmd_gate(self.setup(z_correct=True))
            cab.cmd_gate(self.setup(carriers=(5, 4)))  # four fresh compactions cap that repo at n = 4
            self.assertEqual((cab.load_state("ga")["gate"]["n"], cab.load_state("gb")["gate"]["n"]), (5, 4))
        finally:
            cab.CAP_USD = old

    def test_revision_once_then_z_only_and_flagged(self):
        old = cab.CAP_USD
        try:
            cab.CAP_USD = 1000.0
            a = self.setup(z_correct=True)
            rd = os.path.join(cab.DATA, "runs", "ga")
            os.makedirs(rd, exist_ok=True)
            open(os.path.join(rd, "Z1-n.jsonl"), "w").close()
            open(os.path.join(rd, "H1.handoff.md"), "w").close()
            spec_a = json.load(open(a.spec[0]))
            spec_a["revised_prompt"] = "revised"
            json.dump(spec_a, open(a.spec[0], "w"))
            cab.cmd_gate(type("A", (), dict(spec=a.spec, revised="ga"))())
            st = cab.load_state("ga")
            self.assertEqual((sorted(st["excluded"]), st["next"]), (["C1", "H1", "Z1"], {}))
            self.assertTrue(os.path.exists(os.path.join(rd, "Z1-n.jsonl.pre-revision")))
            self.assertTrue(os.path.exists(os.path.join(rd, "H1.handoff.md")))  # carriers are never renamed
            self.assertEqual(cab.pilot_seq(spec_a, st), [("Z", 1)])
            self.assertEqual(cab.carrier_args(cab.load_spec(a.spec[0]), st, "Z", "Z1")[0][0], "revised")
            with self.assertRaises(cab.Stop):  # once only
                cab.cmd_gate(type("A", (), dict(spec=a.spec, revised="ga"))())
            st["next"]["Z1"] = {"arm": "Z", "ok": True, "correct": True, "checks": {"core2": True}, "delta": {"cost": 2.0}}
            cab.save_state("ga", st)
            other = cab.load_state("gb")
            other["next"]["Z1"]["correct"] = False
            cab.save_state("gb", other)
            cab.cmd_gate(type("A", (), dict(spec=a.spec, revised=None))())
            self.assertTrue(cab.load_state("ga")["gate"]["carrier_insensitive"])
        finally:
            cab.CAP_USD = old


class StopFileTest(unittest.TestCase):
    def test_stop_file_stops_before_a_call(self):
        open(os.path.join(cab.DATA, "STOP"), "w").close()
        try:
            with self.assertRaises(cab.Stop):
                cab.phase("probe", TMP, "x", [], {}, TMP)
        finally:
            os.remove(os.path.join(cab.DATA, "STOP"))


class Round3GuardTest(unittest.TestCase):
    def test_gate_and_regrade_refuse_round1_data(self):
        sp = os.path.join(TMP, "old.json")
        json.dump({"name": "old", "start": "C", "hard": ["core2"]}, open(sp, "w"))
        cab.save_state("old", {"transitions": {}, "next": {}})  # a round-1/2 state: no start
        with self.assertRaises(cab.Stop):
            cab.cmd_gate(type("A", (), dict(spec=[sp], revised="old"))())
        with self.assertRaises(cab.Stop):
            cab.cmd_regrade(type("A", (), dict(spec=sp))())
        keep = os.environ.pop("CVH_DATA")
        try:
            with self.assertRaises(cab.Stop):  # CVH_DATA unset: the default would be round 1's folder
                cab.require_round3({"x": {"start": {"base": "b"}}})
        finally:
            os.environ["CVH_DATA"] = keep
        cab.require_round3({"x": {"start": {"base": "b"}}})

    def test_compaction_ok(self):
        p = lambda pre: {"boundary": [{"trigger": "manual", "pre_tokens": pre}]}
        self.assertTrue(cab.compaction_ok(p(217000), {"cost": 1.1}))
        self.assertFalse(cab.compaction_ok(p(0), {"cost": 1.1}))
        self.assertFalse(cab.compaction_ok(p(217000), {"cost": 0.0}))
        self.assertFalse(cab.compaction_ok({"boundary": []}, {"cost": 1.1}))


class WTest(unittest.TestCase):
    def test_staged_tree_ignores_pycache(self):
        d = tempfile.mkdtemp(dir=TMP)
        os.makedirs(os.path.join(d, "lib", "__pycache__"))
        open(os.path.join(d, "lib", "a.py"), "w").write("x")
        h = cab.staged_tree(d)
        open(os.path.join(d, "lib", "__pycache__", "a.pyc"), "w").write("y")
        self.assertEqual(cab.staged_tree(d), h)
        open(os.path.join(d, "lib", "a.py"), "w").write("z")
        self.assertNotEqual(cab.staged_tree(d), h)

    def wstate(self, w_warm, w_marks, r2_warm=(0.73,) * 5, written=None):
        mk = lambda ok: {"F1": True, "F2": ok}
        tr = {f"H{i}": {"arm": "H", "ok": True, "delta": {"cost": c}, "first": {}, "handoff_markers": mk(True), "added_markers": mk(True)}
              for i, c in enumerate(r2_warm, 1)}
        w = {f"W{i}": {"arm": "W", "i": i, "ok": True, "valid": True, "written": True if written is None else written[i - 1],
                       "warm": c, "markers": mk(True), "added_markers": mk(m)} for i, (c, m) in enumerate(zip(w_warm, w_marks), 1)}
        return {"transitions": tr, "write": w}

    def test_wverdict(self):
        v = lambda *s: cab.wverdict({str(i): x for i, x in enumerate(s)}).split("  ")[0]
        five = [True] * 5
        self.assertEqual(v(self.wstate([0.5] * 5, five), self.wstate([0.6] * 5, five)), "W VERDICT: cheaper")
        self.assertEqual(v(self.wstate([0.5] * 5, five), self.wstate([0.6] * 4 + [0.6], [False] + [True] * 4)), "W VERDICT: cheaper")
        self.assertEqual(v(self.wstate([0.5] * 5, [False] + [True] * 4), self.wstate([0.6] * 5, [False] + [True] * 4)), "W VERDICT: loses facts")
        self.assertEqual(v(self.wstate([0.5] * 5, five), self.wstate([0.8] * 5, five)), "W VERDICT: not cheaper")
        self.assertTrue(v(self.wstate([0.5] * 2, [True] * 2), self.wstate([0.6] * 5, five)).startswith("W VERDICT: inconclusive"))
        # a valid run that wrote no handoff counts as missing every required marker (no survivorship)
        nowrite = [False, False] + [True] * 3
        self.assertEqual(v(self.wstate([0.5] * 5, five, written=nowrite), self.wstate([0.6] * 5, five)), "W VERDICT: loses facts")
        # required = markers in the added lines of every round-2 patch: F1 only if one patch did not add F2
        st = self.wstate([0.5] * 5, five)
        st["transitions"]["H3"]["added_markers"]["F2"] = False
        self.assertEqual(cab.w_required(st), ["F1"])

    def test_wverdict_against_a_reference_w(self):
        """W2: with ref_states the reference is the earlier W's valid runs; round 2 still gives the required markers."""
        five = [True] * 5
        a, b = self.wstate([0.5] * 5, five, r2_warm=(0.4,) * 5), self.wstate([0.5] * 5, five, r2_warm=(0.4,) * 5)
        v = lambda ref: cab.wverdict({"a": a, "b": b}, ref).split("  ")[0]
        self.assertEqual(v(None), "W VERDICT: not cheaper")  # against round 2 (0.4)
        ref = {"a": self.wstate([0.6] * 5, five), "b": self.wstate([0.6] * 5, five)}
        self.assertEqual(v(ref), "W VERDICT vs the reference W: cheaper")
        ref["b"] = self.wstate([0.45] * 5, five)
        self.assertEqual(v(ref), "W VERDICT vs the reference W: not cheaper")
        ref["b"]["write"] = dict(list(ref["b"]["write"].items())[:2])
        self.assertTrue(v(ref).startswith("W VERDICT vs the reference W: inconclusive (b: 2 valid reference"))
        self.assertIn("vs ref W 0.600", cab.wverdict({"a": a}, {"a": self.wstate([0.6] * 5, five)}))

    def test_leak_forms_and_staged_checks(self):
        for x in ("~/.claude/plugins/cache/baton/baton/1.0.0/lib/promote.sh", "$HOME/.claude/plugins/cache/baton/x",
                  "${HOME}/.claude/plugins/cache/baton/x", os.path.expanduser("~/.claude/plugins/cache/baton/baton")):
            self.assertTrue(cab.LEAK.search(x), x)
        self.assertFalse(cab.LEAK.search("/tmp/plugin/baton/lib/promote.sh"))
        d = tempfile.mkdtemp(dir=TMP)
        os.makedirs(os.path.join(d, ".claude-plugin"))
        json.dump({"version": "1.0.0", "skills": ["./skills/driftmap/", "./skills/baton/"]}, open(os.path.join(d, ".claude-plugin", "plugin.json"), "w"))
        self.assertEqual(cab.staged_skills(d), ["baton:baton", "baton:driftmap"])
        probe = {"runs": {"staged": {"plugins": [{"name": "baton", "version": "1.0.0"}], "skills": ["baton:driftmap", "baton:baton"]}}}
        self.assertIsNone(cab.staged_problem(d, probe))
        probe["runs"]["staged"]["skills"].append("baton:baton-setup")
        self.assertIn("rerun wprobe", cab.staged_problem(d, probe))
        old = cab.BATON_REQUIRED
        try:
            cab.BATON_REQUIRED = "1.0.1"
            self.assertIn("CVH_BATON=1.0.1", cab.staged_problem(d))
        finally:
            cab.BATON_REQUIRED = old


class ReviewFixTest(unittest.TestCase):
    def test_validity(self):
        r = lambda st, err=False, **k: dict({"result": {"subtype": st, "is_error": err}}, **k)
        self.assertTrue(cab.ok_result(r("success")))
        self.assertTrue(cab.ok_result(r("error_max_turns", True)))  # pre-registered: a valid, graded run
        self.assertTrue(cab.ok_result(r("error_max_budget_usd", True)))
        self.assertFalse(cab.ok_result(r("success", True)))  # an API error
        self.assertFalse(cab.ok_result(r("error_during_execution", True)))
        self.assertFalse(cab.ok_result(r("success", rate_limited=True)))
        self.assertFalse(cab.ok_result({"result": None}))

    def test_injection_split(self):
        ups = lambda out: {"type": "system", "subtype": "hook_response", "hook_event": "UserPromptSubmit", "stdout": out}
        index = "[baton] 이 저장소 개념 지도(CONCEPTS.md) 색인이다. 작업에 맞는 개념의 파일부터 연다."
        handoff = json.dumps({"hookSpecificOutput": {"additionalContext": "[baton] 아래는 이 저장소 HANDOFF.md의 전문이다(…)"}})  # escaped
        p = cab.parse(write_stream([ups(index)]))
        self.assertEqual((p["inject"], p["inject_handoff"], p["inject_concept"]), (True, False, True))
        p = cab.parse(write_stream([ups(handoff)]))
        self.assertEqual((p["inject_handoff"], p["inject_concept"]), (True, False))
        p = cab.parse(write_stream([ups("[baton] Below is this repo's full HANDOFF.md, injected because …")]))
        self.assertTrue(p["inject_handoff"])

    def test_dropped_attachments(self):
        rows = [{"type": "system", "subtype": "compact_boundary", "uuid": "b"},
                {"type": "attachment", "uuid": "a1", "attachment": {"type": "compact_file_reference", "filename": "/r/HANDOFF.md"}},
                {"type": "attachment", "uuid": "a2", "attachment": {"type": "file", "filename": "/r/HANDOFF.md", "content": {}}},
                {"type": "attachment", "uuid": "cut", "attachment": {"type": "file", "filename": "/r/x.ts"}},
                {"type": "attachment", "uuid": "a3", "attachment": {"type": "file", "filename": "/r/HANDOFF.md"}}]
        fd, f = tempfile.mkstemp(suffix=".jsonl", dir=TMP)
        with os.fdopen(fd, "w") as fh:
            fh.write("\n".join(json.dumps(d) for d in rows))
        self.assertEqual(cab.dropped_attachments(f, ["HANDOFF.md"], until="cut"), ["HANDOFF.md"])
        self.assertEqual(cab.dropped_attachments(f, ["HANDOFF.md"]), ["HANDOFF.md", "HANDOFF.md"])
        self.assertEqual(cab.dropped_attachments(f, []), [])

    def test_main_sequence_interleaves_pairs(self):
        sts = {"a": {"next": {"Z1": {}, "C1": {}, "H1": {}}}, "b": {"next": {"Z1": {}, "H1": {}, "C1": {}}}}
        seq = cab.main_sequence([{"name": "a", "start": "C"}, {"name": "b", "start": "H"}], sts, {"a": 3, "b": 2})
        self.assertEqual(seq, [("a", "H", 2), ("a", "C", 2), ("b", "C", 2), ("b", "H", 2), ("a", "C", 3), ("a", "H", 3)])

    def test_t1_keeps_the_reused_compaction(self):
        st = {"transitions": {"C1": {"arm": "C", "fork": True}}, "reused": {"C1": {"arm": "C", "reused_from": "r1"}}}
        self.assertEqual(cab.trans_for(st, "C1", "T1")["reused_from"], "r1")
        self.assertTrue(cab.trans_for(st, "C1", "T2")["fork"])

    def test_child_env_and_third_carrier(self):
        keep = {k: os.environ.get(k) for k in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "ANTHROPIC_MODEL")}
        os.environ.update(CLAUDECODE="1", CLAUDE_CODE_SESSION_ID="x", ANTHROPIC_MODEL="m")
        try:
            env = cab.child_env()
            self.assertNotIn("CLAUDECODE", env)
            self.assertNotIn("CLAUDE_CODE_SESSION_ID", env)
            self.assertEqual(env["DISABLE_AUTOUPDATER"], "1")
            self.assertIn("ANTHROPIC_MODEL", cab.env_names(env))
        finally:
            for k, v in keep.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        calls = [("mcp__plugin_oh-my-claudecode_t__session_search", {}), ("Read", {"file_path": os.path.expanduser("~/.claude/projects/p/x.jsonl")}),
                 ("Bash", {"command": "cat ~/.omc/state/x"}), ("Read", {"file_path": "/r/lib/x.py"}), ("mcp__x__notepad_read", {})]
        self.assertEqual(cab.third_carrier(calls), ["Bash", "Read", "mcp__plugin_oh-my-claudecode_t__session_search", "mcp__x__notepad_read"])

    def test_phase_ledger_pending_rows_and_clean_retry(self):
        """A pending row at the cap, then the correction; a rate limit goes back to prepare() before the retry."""
        fake = os.path.join(TMP, "fakeclaude")
        cnt = os.path.join(TMP, "fakecount")
        open(fake, "w").write(f"""#!{sys.executable}
import json, os, sys
if "--version" in sys.argv: print("9.9.9 (Claude Code)"); sys.exit(0)
n = int(open({cnt!r}).read()) if os.path.exists({cnt!r}) else 0
open({cnt!r}, "w").write(str(n + 1))
print(json.dumps({{"type": "system", "subtype": "init", "session_id": "s", "plugins": [], "model": "m"}}))
res = {{"type": "result", "subtype": "success", "is_error": n == 0, "result": "You've hit your session limit" if n == 0 else "ok",
       "session_id": "s", "total_cost_usd": 0.25, "modelUsage": {{"m": {{"inputTokens": 1}}}}}}
print(json.dumps(res))
""")
        os.chmod(fake, 0o755)
        old = (cab.CLAUDE_BIN, cab.BACKOFF, cab.LEDGER)
        led = os.path.join(TMP, "ledger-phase.jsonl")
        try:
            cab.CLAUDE_BIN, cab.BACKOFF, cab.LEDGER = fake, (0, 0), led
            cab._cli_ok.clear()
            calls = []
            p, du, out, dt = cab.phase("probe", TMP, "t", [], cab.usage_of(None), TMP, prepare=lambda: calls.append(1))
            self.assertEqual(calls, [1])
            self.assertFalse(p["rate_limited"])
            rows = [r for r in cab.ledger_rows() if r.get("tag") == "t"]
            self.assertEqual([r["phase"] for r in rows], ["pending", "final", "pending", "final"])
            self.assertAlmostEqual(sum(r["charged"] for r in rows), 0.5)
            self.assertIn("env_names", rows[1])
        finally:
            cab.CLAUDE_BIN, cab.BACKOFF, cab.LEDGER = old
            cab._cli_ok.clear()


if __name__ == "__main__":
    unittest.main()
