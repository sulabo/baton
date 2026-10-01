#!/usr/bin/env python3
"""Round1-E: does a session-start state card (previous HANDOFF.md) cover the files
an agent reads on its own in the first K assistant turns?

READ-ONLY. No commits. Run: python3 round1_e.py
"""
import json, glob, os, re, subprocess, statistics, collections
from datetime import datetime, timezone

REPO = "<project>"
SESS = "~/.claude/projects/<transcript-dir>"
KS = (3, 5, 10)
EXT = re.compile(r"\.(md|css|astro|ts|tsx|js|jsx|json|py|html|yml|yaml|sh|mjs|txt|csv|svg|png|jpg|pdf)$", re.I)

def git(*a):
    return subprocess.run(["git", "-C", REPO, *a], capture_output=True, text=True).stdout

# ---------- handoff versions ----------
def handoff_versions():
    out = []
    for line in git("log", "--format=%H %aI", "--", "HANDOFF.md").splitlines():
        h, iso = line.split(" ", 1)
        out.append((datetime.fromisoformat(iso), h))
    out.sort()
    return out

SEC_FILES = re.compile(r"^#+.*관련 파일")
SEC_GOAL  = re.compile(r"^#+.*(목표|완료 조건)")
SEC_NEVER = re.compile(r"^#+.*(실패한 접근|다시 시도 금지|다시 하지 말)")

def split_sections(text):
    secs, cur, body = [], None, []
    for ln in text.splitlines():
        if ln.startswith("#"):
            if cur is not None: secs.append((cur, "\n".join(body)))
            cur, body = ln, []
        else:
            body.append(ln)
    if cur is not None: secs.append((cur, "\n".join(body)))
    return secs

def handoff_paths(text):
    """Path-like backtick tokens inside any '관련 파일' section."""
    paths = set()
    for head, body in split_sections(text):
        if SEC_FILES.search(head):
            for tok in re.findall(r"`([^`]+)`", body):
                tok = tok.strip()
                if " " in tok and not EXT.search(tok): continue
                if EXT.search(tok) or tok.endswith("/") or ("/" in tok and not tok.startswith("-")):
                    paths.add(tok.lstrip("./"))
    return paths

def card_bytes(text):
    keep = [h + "\n" + b for h, b in split_sections(text)
            if SEC_GOAL.search(h) or SEC_FILES.search(h) or SEC_NEVER.search(h)]
    return len("\n".join(keep).encode("utf-8")), len(keep)

# ---------- sessions ----------
SKIP_USER = ("<local-command-caveat>", "<command-name>", "Another Claude session sent a message:",
             "<system-reminder>", "Caveat:")

def human_prompts(path):
    """(ts, text) of human prompts on the main thread."""
    res = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line: continue
        try: d = json.loads(line)
        except Exception: continue
        if d.get("type") != "user" or d.get("isMeta") or d.get("isSidechain"): continue
        c = d.get("message", {}).get("content")
        if isinstance(c, str): txt = c
        elif isinstance(c, list):
            if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c): continue
            txt = " ".join(b.get("text", "") for b in c if isinstance(b, dict))
        else: continue
        t = txt.strip()
        if not t or t.startswith(SKIP_USER): continue
        res.append((datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00")), t))
    return res

def assistant_turns(path, t0):
    """After t0, main-thread assistant events grouped into turns by requestId (order preserved)."""
    turns, seen = [], {}
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line: continue
        try: d = json.loads(line)
        except Exception: continue
        if d.get("type") != "assistant" or d.get("isSidechain"): continue
        ts = datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00"))
        if ts < t0: continue
        rid = d.get("requestId") or d.get("uuid")
        if rid not in seen:
            seen[rid] = len(turns); turns.append([])
        c = d.get("message", {}).get("content")
        if isinstance(c, list):
            for b in c:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    turns[seen[rid]].append(b)
    return turns

BASH_SKIP = re.compile(r"^(-|https?:|/dev/|node_modules/)")
def bash_files(cmd):
    """File targets named in a Bash command (cat/sed/head/grep/awk/... all included).
    Heuristic: any token with a known file extension, or a repo-relative path token."""
    out = set()
    if not cmd: return out
    # drop the `cd "<dir>"` argument so the repo root itself is not counted
    body = re.sub(r"""cd\s+(?:"[^"]*"|'[^']*'|\S+)""", " ", cmd)
    for tok in re.findall(r"""(?:"([^"]+)"|'([^']+)'|([^\s'"|&;<>()$`]+))""", body):
        t = next((x for x in tok if x), "")
        t = t.strip().strip(",")
        if not t or BASH_SKIP.match(t): continue
        if ":" in t and not t.startswith("/"):      # git show <hash>:path
            t = t.split(":", 1)[1]
        if not EXT.search(t): continue
        if "*" in t or "?" in t: continue          # glob patterns are not a file read
        out.add(t.lstrip("./"))
    return out

def rel(p):
    p = os.path.normpath(p)
    if p.startswith(REPO + "/"): return p[len(REPO) + 1:]
    return None  # outside repo

IS_HANDOFF = re.compile(r"(^|/)HANDOFF[^/]*\.md$", re.I)

def covered(relpath, hp):
    base = os.path.basename(relpath)
    if relpath in hp or base in hp: return True
    for h in hp:
        if h.endswith("/") and relpath.startswith(h.rstrip("/") + "/"): return True
        if h == relpath or (h and relpath.endswith("/" + h)): return True
    return False

def covered_strict(relpath, hp):
    if relpath in hp: return True
    return any(h.endswith("/") and relpath.startswith(h.rstrip("/") + "/") for h in hp)

def main():
    hv = handoff_versions()
    files = sorted(glob.glob(SESS))
    rows, skipped = [], collections.Counter()
    for f in files:
        sid = os.path.basename(f)[:8]
        hp_list = human_prompts(f)
        if not hp_list:
            skipped["no_human_prompt"] += 1; continue
        t0, first_prompt = hp_list[0]
        prev = [(d, h) for d, h in hv if d <= t0]
        if not prev:
            skipped["no_handoff_before_T0"] += 1
            rows.append(dict(sid=sid, t0=t0, handoff=None)); continue
        hcommit = prev[-1][1]
        text = git("show", f"{hcommit}:HANDOFF.md")
        hp = handoff_paths(text)
        cbytes, nsec = card_bytes(text)
        turns = assistant_turns(f, t0)
        row = dict(sid=sid, t0=t0, handoff=hcommit, hpaths=len(hp), card=cbytes, nsec=nsec,
                   prompt=first_prompt[:60].replace("\n", " "),
                   handoff_word=("핸드오프" in first_prompt or "HANDOFF" in first_prompt))
        for K in KS:
            reads, outside, nread, nbash = [], 0, 0, 0
            for t in turns[:K]:
                for b in t:
                    cands = []
                    if b.get("name") == "Read":
                        fp = b.get("input", {}).get("file_path")
                        if fp: cands.append(fp); nread += 1
                    elif b.get("name") in ("Grep", "Glob"):
                        fp = b.get("input", {}).get("path")
                        if fp and EXT.search(fp): cands.append(fp)
                    elif b.get("name") == "Bash":
                        bf = bash_files(b.get("input", {}).get("command", ""))
                        nbash += len(bf); cands.extend(bf)
                    for fp in cands:
                        if fp.startswith("/"):
                            r = rel(fp)
                            if r is None: outside += 1; continue
                        else:
                            r = fp
                        reads.append(r)
            row[f"nread{K}"], row[f"nbash{K}"] = nread, nbash
            uniq = sorted(set(reads))
            row[f"R{K}"] = uniq
            row[f"out{K}"] = outside
            row[f"cov{K}"] = (sum(covered(p, hp) for p in uniq) / len(uniq)) if uniq else None
            row[f"str{K}"] = (sum(covered_strict(p, hp) for p in uniq) / len(uniq)) if uniq else None
            row[f"hcv{K}"] = (sum(covered(p, hp) or bool(IS_HANDOFF.search(p)) for p in uniq) / len(uniq)) if uniq else None
            row[f"nho{K}"] = sum(1 for p in uniq if IS_HANDOFF.search(p))
        # bytes of R5 files (current on-disk size)
        tot, miss = 0, 0
        for p in row["R5"]:
            ap = os.path.join(REPO, p)
            if os.path.isfile(ap):
                tot += os.path.getsize(ap); continue
            blob = subprocess.run(["git", "-C", REPO, "show", f"{hcommit}:{p}"],
                                  capture_output=True)
            if blob.returncode == 0 and blob.stdout:
                tot += len(blob.stdout)
            else:
                miss += 1
        row["r5bytes"], row["r5missing"] = tot, miss
        row["nturns"] = len(turns)
        rows.append(row)

    def agg(key, subset=None):
        vs = [r[key] for r in rows if r.get("handoff") and r.get(key) is not None
              and (subset is None or subset(r))]
        return (len(vs), statistics.mean(vs) if vs else None,
                statistics.median(vs) if vs else None)

    print("=== SESSIONS ===", len(files), "skipped:", dict(skipped))
    print(f"{'sid':9} {'handoff':8} {'hp':>3} {'trn':>4} {'R3':>3} {'R5':>3} {'R10':>4} "
          f"{'cov3':>6} {'cov5':>6} {'cov10':>6} {'str5':>6} {'HO?':>4} {'card':>6} {'r5B':>8}  prompt")
    for r in rows:
        if not r.get("handoff"):
            print(f"{r['sid']:9} {'NONE':8}"); continue
        fmt = lambda v: f"{v*100:5.0f}%" if v is not None else "    -"
        print(f"{r['sid']:9} {r['handoff'][:7]:8} {r['hpaths']:3d} {r['nturns']:4d} "
              f"{len(r['R3']):3d} {len(r['R5']):3d} {len(r['R10']):4d} "
              f"{fmt(r['cov3']):>6} {fmt(r['cov5']):>6} {fmt(r['cov10']):>6} {fmt(r['str5']):>6} "
              f"{str(r['handoff_word']):>4} {r['card']:6d} {r['r5bytes']:8d}  {r['prompt']}")

    print("\n=== AGGREGATE (sessions with a handoff) ===")
    for K in KS:
        n, m, md = agg(f"cov{K}")
        ns, ms, mds = agg(f"str{K}")
        nh, mh, mdh = agg(f"hcv{K}")
        print(f"K={K:2d}  loose n={n} mean={m and round(m*100,1)}% median={md and round(md*100,1)}%   "
              f"strict n={ns} mean={ms and round(ms*100,1)}% median={mds and round(mds*100,1)}%   "
              f"+HANDOFF.md n={nh} mean={mh and round(mh*100,1)}% median={mdh and round(mdh*100,1)}%")
    print("sessions whose handoff has NO '관련 파일' section:",
          sum(1 for r in rows if r.get("handoff") and r["hpaths"] == 0))
    print("sessions that re-read HANDOFF.md within first 5 turns:",
          sum(1 for r in rows if r.get("handoff") and r.get("nho5", 0) > 0), "/",
          sum(1 for r in rows if r.get("handoff")))

    sub = lambda r: r["handoff_word"]
    nho = sum(1 for r in rows if r.get("handoff") and r["handoff_word"])
    print(f"\n=== HANDOFF-WORD SESSIONS: {nho}/{len(files)} ===")
    for K in KS:
        n, m, md = agg(f"cov{K}", sub)
        nh, mh, mdh = agg(f"hcv{K}", sub)
        print(f"K={K:2d}  n={n} mean={m and round(m*100,1)}% median={md and round(md*100,1)}%"
              f"   +HANDOFF.md mean={mh and round(mh*100,1)}% median={mdh and round(mdh*100,1)}%")

    r5b = [r["r5bytes"] for r in rows if r.get("handoff") and r["R5"]]
    cds = [r["card"] for r in rows if r.get("handoff") and r["R5"]]
    print(f"\n=== BYTES (sessions with >=1 read in first 5 turns, n={len(r5b)}) ===")
    print(f"R5 read-file bytes   median={statistics.median(r5b):,.0f} mean={statistics.mean(r5b):,.0f}")
    print(f"card bytes           median={statistics.median(cds):,.0f} mean={statistics.mean(cds):,.0f}")
    print(f"ratio card/R5 median = {statistics.median(cds)/statistics.median(r5b):.3f}")

    print("\n=== NOT COUNTED ===")
    print("sessions with 0 Read in first 5 turns:",
          sum(1 for r in rows if r.get("handoff") and not r["R5"]))
    print("sessions with 0 Read in first 10 turns:",
          sum(1 for r in rows if r.get("handoff") and not r["R10"]))
    print("reads outside repo (K=5, summed):", sum(r.get("out5", 0) for r in rows if r.get("handoff")))
    print("reads outside repo (K=10, summed):", sum(r.get("out10", 0) for r in rows if r.get("handoff")))
    print("R5 files missing on disk (summed):", sum(r.get("r5missing", 0) for r in rows if r.get("handoff")))
    print("sessions with no handoff commit before T0:", skipped["no_handoff_before_T0"])
    print("sessions with no human prompt found:", skipped["no_human_prompt"])
    print("handoff versions total:", len(hv))

def tool_census():
    """Why Bash counts as a read channel: tool_use tallies across all 24 sessions."""
    names, readish, nbash = collections.Counter(), 0, 0
    for f in sorted(glob.glob(SESS)):
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if not line: continue
            try: d = json.loads(line)
            except Exception: continue
            if d.get("type") != "assistant": continue
            c = d.get("message", {}).get("content")
            if not isinstance(c, list): continue
            for b in c:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    names[b.get("name")] += 1
                    if b.get("name") == "Bash":
                        nbash += 1
                        if re.search(r"\b(cat|head|tail|sed -n|less)\b", b.get("input", {}).get("command", "")):
                            readish += 1
    for k, v in names.most_common(10): print(f"  {k:24} {v}")
    print(f"  Bash commands containing cat/head/tail/sed -n: {readish} / {nbash}")

if __name__ == "__main__":
    import sys
    if "--tools" in sys.argv: tool_census()
    else: main()
