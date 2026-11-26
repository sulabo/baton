#!/usr/bin/env python3
"""Hidden acceptance checks for the baton round-3 different task (T2: `--by-date` in lib/handoff_stats.py).
Runs from outside the snapshot:
  python3 -I baton_t2_hidden.py <snapshot>   -> last stdout line is a JSON dict of booleans (+ diagnostics)
Never copied into the snapshot, so the sessions cannot read it."""
import ast, json, os, re, subprocess, sys, tempfile

R = sys.argv[1]
CLI = os.path.join(R, "lib", "handoff_stats.py")
FLAG = "--by-date"
EMPTY = "baton: no dated sections"

# core2: dashed dates out of order, a dateless section, a fenced '## ' line that is not a heading
A = """# Handoff

## 2026-11-18 old work
- [x] a
- [ ] b

## Notes
- [ ] g

## 2026-11-25 new
- [x] f

```text
## 2026-11-19 not a heading
```

## 2026-11-20 mid
- [x] c
- [ ] d
- [ ] e
"""
A_WANT = ["2026-11-25 open=0 done=1", "2026-11-20 open=2 done=1", "2026-11-18 open=1 done=1"]
# F1: dotted and dashed headings mixed; dotted dates must be recognized and printed with dashes
B = """## 2026.11.18 a
- [ ] x

## 2026-11-22 c
- [ ] z
- [x] w

## 2026.11.21 b
- [x] y
"""
B_WANT = ["2026-11-22 open=1 done=1", "2026-11-21 open=0 done=1", "2026-11-18 open=1 done=0"]
E = """# Handoff

## Notes
- [ ] a

## Plan
- [x] b
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


def count_lines(out):
    """Every output line that reports counts, whitespace-normalized (a dateless or dotted line is a wrong line)."""
    return [" ".join(ln.split()) for ln in out.splitlines() if re.search(r"\bopen\s*=", ln)]


res = {}
exists = os.path.isfile(CLI)
rc, out = run([FLAG], A)
rc_e, out_e = run([FLAG], E)
res["core2"] = (exists and rc == 0 and count_lines(out) == A_WANT
                and rc_e == 0 and EMPTY in out_e and not count_lines(out_e))
rc, out = run([FLAG], B)
res["F1"] = exists and rc == 0 and sorted(count_lines(out)) == sorted(B_WANT)  # order is core2's job
try:
    doc = ast.get_docstring(ast.parse(open(CLI, encoding="utf-8").read())) or ""
except Exception:
    doc = ""
def usage_block(doc):
    """The docstring's Usage block: the 'Usage' line and the indented or blank lines after it."""
    lines, out = doc.splitlines(), []
    for k, ln in enumerate(lines):
        if ln.strip().startswith("Usage"):
            out.append(ln)
            for nxt in lines[k + 1:]:
                if nxt.strip() and not nxt[:1].isspace():
                    break
                out.append(nxt)
            break
    return "\n".join(out)


res["F5"] = FLAG in usage_block(doc)  # the option must be listed in the Usage block itself
rc, out = run([], A)  # diagnostic: the existing summary line still works
res["baseline"] = exists and rc == 0 and bool(re.search(r"sections\s*=\s*4\b.*open\s*=\s*4\b.*done\s*=\s*3\b", out))
t = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "lib", "-p", "test_handoff_stats.py"],
                   cwd=R, capture_output=True, text=True, timeout=300) if exists else None
res["own_tests_pass"] = bool(t and t.returncode == 0)
print(json.dumps(res))
