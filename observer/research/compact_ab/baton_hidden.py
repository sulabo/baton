#!/usr/bin/env python3
"""Hidden acceptance checks for the baton next task (step 4 of lib/handoff_stats.py). Runs from outside the snapshot:
  python3 -I baton_hidden.py <snapshot>   -> last stdout line is a JSON dict of booleans (+ diagnostics)
Never copied into the snapshot, so the sessions cannot read it."""
import ast, json, os, re, subprocess, sys, tempfile

R = sys.argv[1]
CLI = os.path.join(R, "lib", "handoff_stats.py")
FLAG = "--min-date"

A = """# Handoff

## 2026-11-18 old work
- [x] a
- [ ] b

## 2026-11-20 mid
- [x] c
- [ ] d
- [ ] e

## 2026-11-25 new
- [x] f

## Notes
- [ ] g
"""
B = """## 2026.11.18 a
- [ ] x

## 2026.11.21 b
- [x] y

## 2026-11-22 c
- [ ] z
"""


def run(args, text):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "HANDOFF.md")
        with open(p, "w") as f:
            f.write(text)
        try:
            r = subprocess.run([sys.executable, CLI, p] + args, capture_output=True, text=True, timeout=30, cwd=R)
            return r.returncode, r.stdout
        except Exception:
            return 99, ""


def nums(out):
    def g(k):
        m = re.search(k + r"\s*[=:]\s*(\d+)", out)
        return int(m.group(1)) if m else None
    return g("sections"), g("open"), g("done")


res = {}
exists = os.path.isfile(CLI)
rc, out = run([], A)
res["baseline"] = exists and rc == 0 and nums(out) == (4, 4, 3)
rc, out = run([FLAG, "2026-11-20"], A)
res["core"] = exists and rc == 0 and nums(out) == (2, 2, 2)
res["core_any"] = None  # diagnostic: the filter works under some other flag name
for flag in (FLAG, "--since", "--from", "--after", "--date", "--min_date", "--start", "--from-date"):
    rc2, out2 = run([flag, "2026-11-20"], A)
    if rc2 == 0 and nums(out2) == (2, 2, 2):
        res["core_any"] = flag
        break
rc, out = run([FLAG, "2026.11.20"], B)
res["F1"] = exists and rc == 0 and nums(out) == (2, 1, 1)
rc_min, _ = run([FLAG, "2026-11-20"], A)
rc_since, out_since = run(["--since", "2026-11-20"], A)
# violated only if --since actually filters (an alias); a rejected or ignored --since is fine
res["F2"] = exists and rc_min == 0 and not (rc_since == 0 and nums(out_since) == (2, 2, 2))
try:
    doc = ast.get_docstring(ast.parse(open(CLI, encoding="utf-8").read())) or ""
except Exception:
    doc = ""
res["F5"] = FLAG in doc and "Usage" in doc
rc, out = run([FLAG, "2099-01-01"], A)
res["F6"] = exists and rc == 0 and "no sections on or after 2099-01-01" in out
t = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "lib", "-p", "test_handoff_stats.py"],
                   cwd=R, capture_output=True, text=True, timeout=300) if exists else None
res["own_tests_pass"] = bool(t and t.returncode == 0)
print(json.dumps(res))
