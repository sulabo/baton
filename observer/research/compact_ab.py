#!/usr/bin/env python3
"""Compact vs handoff A/B: at a task boundary in a long session, is "/compact and keep going" or
"write HANDOFF.md and start a new session" better for the next task? See docs/research/compact-vs-handoff.md.

One long session S per repo is built from a scripted prompt list (build). Every run forks S:
  arm C: claude -p "/compact" --resume S --fork-session      -> C_i ; next: claude -p "이어서 해줘" --resume C_i
  arm H: claude -p "핸드오프 작성해줘" --resume S --fork-session -> HANDOFF.md patch ; next: new session, same prompt
All phases run one at a time in the same snapshot path (S's transcript holds absolute paths into it).

  python3 compact_ab.py snapshot --name baton --src ~/baton-wt/exp [--commit HEAD] [--setup "npm ci"]
  python3 compact_ab.py build --spec compact_ab/baton.json
  python3 compact_ab.py transitions --spec compact_ab/baton.json [--n 5]
  python3 compact_ab.py next --spec compact_ab/baton.json [--n 5]
  python3 compact_ab.py report [--repo baton]
  python3 compact_ab.py ledger

Cost accounting: total_cost_usd and modelUsage of a --resume/--fork-session child INCLUDE the parent's usage
(probed 2026-11-23 on 6 parent->child pairs), so every phase is charged child minus parent. The /compact call
reports result.usage = 0 and num_turns = 0; its tokens exist only in modelUsage. Raw data never goes in a repo.
"""
import argparse, json, os, re, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import round2_e_ab as r2  # noqa: E402
from case_grade import parse_diff, tool_calls, SEGMENT  # noqa: E402

DATA = os.path.expanduser(os.environ.get("CVH_DATA", "~/.cache/baton/experiments/compact-vs-handoff"))
SNAPS = os.path.expanduser(os.environ.get("CVH_SNAPS", os.path.join(DATA, "snapshots")))  # round 2 reuses round 1's snapshots
LEDGER = os.path.join(DATA, "ledger.jsonl")
CAP_USD = float(os.environ.get("CVH_CAP_USD", 77.0))      # hard stop (lead, 2026-11-23): reported total_cost_usd, probes included; owner approved $80
PROBE_USD = float(os.environ.get("CVH_PROBE_USD", 2.902))  # feasibility probes run 2026-11-23 before this runner existed
# Round 2 (2026-11-24, handoff arm only after the beta.5 fix): CVH_DATA=<new folder> CVH_CAP_USD=40 CVH_PROBE_USD=0
# CVH_BATON=1.0.0-beta.5 — every phase must load exactly that baton version (round 1 mixed beta.3 and beta.4).
BATON_REQUIRED = os.environ.get("CVH_BATON")
MARGIN = 0.5            # a turn can overshoot --max-budget-usd
CAPS = {"build": 2.0, "transition": 3.0, "next": 4.0, "followup": 4.0}  # transition 2.0 -> 3.0 after cold H forks hit the cap (2026-11-24)
# Fitted from the four opus probe deltas (exact solve, $/token): used only to reprice cache state, never as billing.
PRICE = {"in": 3.96e-6, "cw": 8.00e-6, "cr": 0.201e-6, "out": 19.95e-6}
TURNS = {"build": 25, "transition": 15, "next": 30, "followup": 30}
FLAGS = ["--output-format", "stream-json", "--verbose", "--include-hook-events"]
NEXT_PROMPT = "이어서 해줘"
FOLLOWUP_PROMPT = "알아서 판단해서 진행해줘"  # exploratory, added 2026-11-24 after pilot H1 stopped to ask
HANDOFF_PROMPT = "핸드오프 작성해줘"
EXCLUDE = [":(exclude).omc", ":(exclude).omx"]
RATE = re.compile(r"rate.?limit|overloaded|\b429\b|\b529\b|session limit|usage limit|hit your|limit reached", re.I)
BACKOFF = (120, 900)    # seconds before the 2nd and 3rd attempt; a 3rd rate-limit failure stops the runner


class Stop(Exception):
    pass


# ---------------- ledger ----------------
def ledger_rows():
    if not os.path.exists(LEDGER):
        return []
    return [json.loads(ln) for ln in open(LEDGER) if ln.strip()]


def spent():
    rows = ledger_rows()
    if not rows:
        return PROBE_USD
    return sum(r["charged"] for r in rows)


def ledger_add(row):
    os.makedirs(DATA, exist_ok=True)
    if not os.path.exists(LEDGER):
        with open(LEDGER, "w") as f:
            f.write(json.dumps(dict(ts=time.strftime("%FT%T"), kind="probes", tag="feasibility", charged=PROBE_USD)) + "\n")
    row = dict(ts=time.strftime("%FT%T"), **row)
    with open(LEDGER, "a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def guard(cap, total=None):
    """Refuse to start a phase whose worst case could cross the hard cap."""
    total = spent() if total is None else total
    if total + cap + MARGIN > CAP_USD:
        raise Stop(f"budget: spent {total:.2f} + cap {cap} + margin {MARGIN} > {CAP_USD}")


# ---------------- stream parsing ----------------
def parse(path):
    """Numbers only from a stream-json file. Main-thread turns are counted per API message id."""
    p = dict(result=None, boundary=[], first=None, last_ctx=None, turns=0, ups=[], inject=False, hooks={},
             baton=None, stop_blocks=0)
    seen = set()
    for ln in open(path, encoding="utf-8", errors="replace"):
        try:
            d = json.loads(ln)
        except Exception:
            continue
        t, st = d.get("type"), d.get("subtype")
        if t == "system" and st == "init":
            p["baton"] = next((x.get("version") for x in d.get("plugins") or [] if x.get("name") == "baton"), None)
        elif t == "system" and st == "hook_response" and d.get("hook_event") == "Stop":
            out = (d.get("stdout") or "") + (d.get("output") or "")
            p["stop_blocks"] += '"decision": "block"' in out or '"decision":"block"' in out
        elif t == "system" and st == "compact_boundary":
            p["boundary"].append(d.get("compact_metadata") or {})
        elif t == "system" and st == "hook_started":
            k = d.get("hook_name") or "?"
            p["hooks"][k] = p["hooks"].get(k, 0) + 1
        elif t == "system" and st == "hook_response" and d.get("hook_event") == "UserPromptSubmit":
            out = (d.get("stdout") or "") + (d.get("output") or "")
            p["ups"].append(len(out))
            p["inject"] = p["inject"] or "[baton" in out
        elif t == "assistant" and not d.get("parent_tool_use_id"):
            mid = (d.get("message") or {}).get("id") or d.get("uuid")
            if mid in seen:
                continue
            seen.add(mid)
            u = (d.get("message") or {}).get("usage") or {}
            tok = {k: u.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")}
            p["turns"] += 1
            p["last_ctx"] = sum(tok.values())
            if p["first"] is None:
                p["first"] = tok
        elif t == "result":
            p["result"] = d
    return p


def usage_of(result):
    """modelUsage summed over models (cumulative over the transcript under --resume)."""
    keys = ("inputTokens", "cacheCreationInputTokens", "cacheReadInputTokens", "outputTokens")
    tot = dict.fromkeys(keys, 0)
    for u in ((result or {}).get("modelUsage") or {}).values():
        for k in keys:
            tot[k] += u.get(k) or 0
    tot["cost"] = (result or {}).get("total_cost_usd") or 0.0
    return tot


def delta(child, parent):
    return {k: round(child[k] - parent.get(k, 0), 6) for k in child}


def rate_limited(p, err_text):
    res = p["result"]
    if res is None:
        return bool(RATE.search(err_text or ""))
    return bool(res.get("is_error") and RATE.search(str(res.get("result") or "")))


# ---------------- snapshot hygiene ----------------
def validate(repo):
    from pathlib import Path
    path, base = Path(repo).resolve(), Path(SNAPS).resolve()
    if base not in path.parents or not (path / ".git").is_dir():
        raise ValueError(f"not an experiment snapshot: {repo}")
    if subprocess.run(["git", "-C", str(path), "remote"], capture_output=True, text=True, check=True).stdout.strip():
        raise ValueError("snapshot must have no remote")


r2.validate_snapshot = validate  # round2's reset/clean_leftovers call it; point them at this experiment's tree


def git(repo, *args, **kw):
    g = ["git", "-C", repo, "-c", "core.fsmonitor=", "-c", "core.hooksPath=/dev/null", "-c", "core.quotepath=false"]
    return subprocess.run(g + list(args), capture_output=True, text=True, **kw)


def head(repo):
    return git(repo, "rev-parse", "HEAD", check=True).stdout.strip()


def project_dir(sid):
    import glob
    hits = glob.glob(os.path.expanduser(f"~/.claude/projects/*/{sid}.jsonl"))
    return os.path.dirname(hits[0]) if hits else None


def quarantine_memory(pdir, tag):
    """Auto-memory would be a third carrier of facts and leak across runs: move it out before every phase."""
    if not pdir:
        return 0
    mem = os.path.join(pdir, "memory")
    if not os.path.isdir(mem) or not os.listdir(mem):
        return 0
    n = len(os.listdir(mem))
    dest = os.path.join(DATA, "quarantine", f"{time.strftime('%Y%m%dT%H%M%S')}-{tag}")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.move(mem, dest)
    return n


def fresh(repo, base, pdir, tag):
    """Reset to base and drop session leftovers. A plugin hook can still be writing .omc/state when the session
    exits (2026-11-23: git clean failed with 'Directory not empty'), so retry after killing leftovers."""
    for attempt in range(5):
        try:
            r2.kill_leftovers(repo)
            r2.reset(repo, base)
            r2.clean_leftovers(repo, r2.ignored_set(repo))
            break
        except subprocess.CalledProcessError:
            time.sleep(3)
            shutil.rmtree(os.path.join(repo, ".omc"), ignore_errors=True)
    else:
        raise Stop(f"cleanup failed 5 times ({tag})")
    return quarantine_memory(pdir, tag)


def tree_of_worktree(repo):
    """Tree id of the current working tree (untracked included) without committing; index restored."""
    git(repo, "add", "-A", check=True)
    t = git(repo, "write-tree", check=True).stdout.strip()
    git(repo, "reset", "-q", check=True)
    return t


def diff_against(repo, tree, out):
    git(repo, "add", "-A")
    d = git(repo, "diff", "--cached", "--no-renames", "--no-ext-diff", "--no-textconv", "--binary", tree, "--", ".", *EXCLUDE).stdout
    git(repo, "reset", "-q")
    with open(out, "w") as f:
        f.write(d)
    return d


# ---------------- one claude call ----------------
def phase(kind, repo, tag, args, parent, run_dir, extra=None):
    """Run one claude call with budget guard, rate-limit backoff and ledger entry. Returns (parse, delta usage)."""
    cap = CAPS[kind]
    for attempt in range(len(BACKOFF) + 1):
        guard(cap)
        out = os.path.join(run_dir, f"{tag}.jsonl" if attempt == 0 else f"{tag}.a{attempt + 1}.jsonl")
        cmd = ["claude", "-p"] + args + FLAGS + ["--max-budget-usd", str(cap)]
        t0 = time.time()
        with open(out, "w") as fo, open(out + ".err", "w") as fe:
            rc = subprocess.run(cmd, cwd=repo, stdin=subprocess.DEVNULL, stdout=fo, stderr=fe,
                                env={**os.environ, "BATON_OBSERVE": "off"}).returncode
        dt = round(time.time() - t0)
        p = parse(out)
        err = open(out + ".err", errors="replace").read()
        if p["result"] is not None:
            du = delta(usage_of(p["result"]), parent)
            charged = max(du["cost"], 0.0)
        else:
            du, charged = None, cap  # unknown spend: charge the worst case
        limited = rate_limited(p, err)
        ledger_add(dict(kind=kind, repo=os.path.basename(repo), tag=tag, attempt=attempt + 1, rc=rc, seconds=dt,
                        charged=round(charged, 6), cost_reported=(p["result"] or {}).get("total_cost_usd"),
                        rate_limited=limited, baton=p["baton"], stop_blocks=p["stop_blocks"], **(extra or {})))
        if BATON_REQUIRED and p["baton"] != BATON_REQUIRED:
            raise Stop(f"{tag}: baton {p['baton']} loaded, {BATON_REQUIRED} required (do not update the plugin mid-run)")
        print(f"  {tag} a{attempt + 1}: rc={rc} {dt}s charged=${charged:.3f} total=${spent():.2f}"
              f"{' RATE-LIMITED' if limited else ''}", flush=True)
        if not limited:
            return p, du, out, dt
        if attempt < len(BACKOFF):
            wait = BACKOFF[attempt]
            m = re.search(r"resets (\d{1,2})(?::(\d{2}))?\s*(am|pm)", str((p["result"] or {}).get("result")) + err, re.I)
            if m and attempt == 0:  # a usage window with a stated reset time: wait for it once (cap 5.5 h)
                import datetime as dtm
                hh = int(m.group(1)) % 12 + (12 if m.group(3).lower() == "pm" else 0)
                now = dtm.datetime.now()
                at = now.replace(hour=hh, minute=int(m.group(2) or 0), second=0, microsecond=0)
                if at <= now:
                    at += dtm.timedelta(days=1)
                wait = min((at - now).total_seconds() + 180, 5.5 * 3600)
            print(f"  backing off {wait:.0f}s", flush=True)
            time.sleep(wait)
    raise Stop("rate limit persists after backoff")


def ok_result(p):
    res = p["result"]
    return res is not None and not res.get("is_error") and res.get("subtype") in ("success", "error_max_turns")


# ---------------- state ----------------
def state_path(name):
    return os.path.join(DATA, "state", f"{name}.json")


def load_state(name):
    p = state_path(name)
    return json.load(open(p)) if os.path.exists(p) else {}


def save_state(name, st):
    os.makedirs(os.path.dirname(state_path(name)), exist_ok=True)
    with open(state_path(name) + ".tmp", "w") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    os.replace(state_path(name) + ".tmp", state_path(name))


def order(n, start, arm=None):
    """Counterbalanced ABBA order: C H H C C H H C C H (start=C) or its mirror. Returns [(arm, i)].
    arm="H" keeps only that arm (round 2 reruns the handoff arm; the C rows are seeded from round 1)."""
    if arm:
        return [x for x in order(n, start) if x[0] == arm]
    pat = "CHHC" if start == "C" else "HCCH"
    seq, counts = [], {"C": 0, "H": 0}
    while min(counts.values()) < n:
        for arm in pat:
            if counts[arm] < n:
                counts[arm] += 1
                seq.append((arm, counts[arm]))
    return seq


# ---------------- commands ----------------
def cmd_snapshot(a):
    dest = os.path.join(SNAPS, a.name)
    if os.path.exists(dest):
        sys.exit(f"exists: {dest}")
    os.makedirs(dest)
    arc = subprocess.run(["git", "-C", os.path.expanduser(a.src), "archive", a.commit], capture_output=True, check=True)
    subprocess.run(["tar", "-x", "-C", dest], input=arc.stdout, check=True)
    for rel in a.remove:
        full = os.path.join(dest, rel)
        if os.path.isdir(full):
            shutil.rmtree(full)
        elif os.path.exists(full):
            os.remove(full)
    if a.setup:
        subprocess.run(a.setup, shell=True, cwd=dest, check=True)
    for c in (["init", "-q"], ["add", "-A"], ["-c", "user.name=snap", "-c", "user.email=snap@local", "commit", "-qm", "snapshot"]):
        subprocess.run(["git", "-C", dest] + c, check=True)
    src_head = subprocess.run(["git", "-C", os.path.expanduser(a.src), "rev-parse", a.commit], capture_output=True, text=True).stdout.strip()
    man = dict(name=a.name, src_commit=src_head, removed=a.remove, setup=a.setup, B0=head(dest), made=time.strftime("%FT%T"))
    st = load_state(a.name)
    st.update(snapshot=man, repo=dest)
    save_state(a.name, st)
    print(json.dumps(man))


def cmd_build(a):
    spec = load_spec(a.spec)
    name = spec["name"]
    st = load_state(name)
    repo = st["repo"]
    validate(repo)
    run_dir = os.path.join(DATA, "runs", name)
    os.makedirs(run_dir, exist_ok=True)
    b = st.setdefault("build", {"steps": [], "sid": None, "total": usage_of(None)})
    if b.get("done"):
        sys.exit("build already done")
    plan = [("p", i, t) for i, t in enumerate(spec["prompts"])]
    k = len(b["steps"])
    fails = 0
    while True:
        done_core = k >= len(plan)
        if done_core:
            ctx = b["steps"][-1]["last_ctx"] if b["steps"] else 0
            pads_used = sum(1 for s in b["steps"] if s["kind"] == "pad")
            if ctx < spec["target_ctx"] and pads_used < len(spec["pad"]):
                step = ("pad", pads_used, spec["pad"][pads_used])
            elif not any(s["kind"] == "final" for s in b["steps"]):
                step = ("final", 0, spec["final"])
            else:
                break
        else:
            step = plan[k]
        kind, idx, text = step
        tag = f"build-{len(b['steps']) + 1:02d}-{kind}{idx}"
        args = [text, "--max-turns", str(TURNS["build"])] + (["--resume", b["sid"]] if b["sid"] else [])
        p, du, out, dt = phase("build", repo, tag, args, b["total"], run_dir)
        if not ok_result(p):
            fails += 1
            print(f"  build step failed: {(p['result'] or {}).get('subtype')}", flush=True)
            if fails >= 2:
                raise Stop("build: same step failed twice")
            continue
        fails = 0
        if p["boundary"]:
            raise Stop(f"build hit a compaction at step {tag}: {p['boundary']}")
        sid = p["result"]["session_id"]
        if b["sid"] and sid != b["sid"]:
            raise Stop(f"resume changed the session id {b['sid']} -> {sid}")
        b["sid"] = sid
        b["total"] = usage_of(p["result"])
        b["steps"].append(dict(kind=kind, idx=idx, tag=tag, last_ctx=p["last_ctx"], turns=p["turns"], seconds=dt, delta=du))
        k += 1
        save_state(name, st)
        print(f"  ctx={p['last_ctx']} cumulative=${b['total']['cost']:.2f}", flush=True)
    # switch point: commit whatever the build left uncommitted, drop harness state, quarantine memory
    r2.kill_leftovers(repo)
    shutil.rmtree(os.path.join(repo, ".omc"), ignore_errors=True)
    git(repo, "add", "-A", check=True)
    if git(repo, "diff", "--cached", "--quiet").returncode:
        git(repo, "-c", "user.name=build", "-c", "user.email=build@local", "commit", "-qm", "post-build (uncommitted work)", check=True)
    b["B1"] = head(repo)
    pdir = project_dir(b["sid"])
    b["project_dir"] = pdir
    b["memory_after_build"] = quarantine_memory(pdir, "after-build")
    f = os.path.join(pdir, b["sid"] + ".jsonl")
    b["S_file"] = dict(size=os.path.getsize(f), mtime=os.path.getmtime(f))
    b["done"] = True
    b["finished"] = time.strftime("%FT%T")
    save_state(name, st)
    print(f"build done: sid={b['sid']} B1={b['B1'][:8]} ctx={b['steps'][-1]['last_ctx']} cost=${b['total']['cost']:.2f}"
          f" memory_moved={b['memory_after_build']}")


def check_S(b):
    f = os.path.join(b["project_dir"], b["sid"] + ".jsonl")
    now = dict(size=os.path.getsize(f), mtime=os.path.getmtime(f))
    if now != b["S_file"]:
        raise Stop(f"S transcript changed: {b['S_file']} -> {now}")


def cmd_transitions(a):
    spec = load_spec(a.spec)
    name = spec["name"]
    st = load_state(name)
    repo, b = st["repo"], st["build"]
    assert b.get("done"), "build first"
    run_dir = os.path.join(DATA, "runs", name)
    os.makedirs(run_dir, exist_ok=True)  # round 2 skips build, which used to create it
    tr = st.setdefault("transitions", {})
    fails = 0
    for arm, i in order(a.n, spec["start"], a.arm):
        tag = f"{arm}{i}"
        if tr.get(tag, {}).get("ok"):
            continue
        prev = tr.get(tag, {}).get("failed_attempts", [])
        if tag in tr:  # keep the failed attempt's raw files and record
            k = len(prev) + 1
            for ext in (".jsonl", ".jsonl.err"):
                f = os.path.join(run_dir, f"{tag}-t{ext}")
                if os.path.exists(f):
                    os.replace(f, os.path.join(run_dir, f"{tag}-t.fail{k}{ext}"))
            prev = prev + [{kk: tr[tag].get(kk) for kk in ("subtype", "delta", "first", "seconds")}]
        mem = fresh(repo, b["B1"], b["project_dir"], f"{name}-{tag}-t")
        if arm == "C":
            args = ["/compact", "--resume", b["sid"], "--fork-session"]
        else:
            args = [HANDOFF_PROMPT, "--resume", b["sid"], "--fork-session", "--max-turns", str(TURNS["transition"])]
        p, du, out, dt = phase("transition", repo, f"{tag}-t", args, b["total"], run_dir, dict(arm=arm, i=i))
        check_S(b)
        rec = dict(arm=arm, i=i, seconds=dt, delta=du, memory_moved_before=mem, turns=p["turns"],
                   first=p["first"], hooks=p["hooks"], subtype=(p["result"] or {}).get("subtype"),
                   baton=p["baton"], stop_blocks=p["stop_blocks"])
        okr = p["result"] is not None and not p["result"].get("is_error")
        if arm == "C":
            rec["boundary"] = p["boundary"][-1] if p["boundary"] else None
            rec["sid"] = (p["result"] or {}).get("session_id")
            rec["total"] = usage_of(p["result"])
            rec["ok"] = okr and bool(p["boundary"]) and rec["sid"] != b["sid"]
        else:
            r2.kill_leftovers(repo)
            patch = os.path.join(run_dir, f"{tag}.patch")
            d = diff_against(repo, b["B1"], patch)
            files = sorted(parse_diff(d))
            rec["patch_files"] = files
            ho = os.path.join(repo, "HANDOFF.md")
            rec["handoff_bytes"] = os.path.getsize(ho) if os.path.exists(ho) else 0
            rec["ok"] = okr and "HANDOFF.md" in files
        rec["failed_attempts"] = prev
        tr[tag] = rec
        save_state(name, st)
        fresh(repo, b["B1"], b["project_dir"], f"{name}-{tag}-t-after")
        fails = 0 if rec["ok"] else fails + 1
        print(f"{tag} transition ok={rec['ok']} cost=${(du or {}).get('cost', 0):.3f}", flush=True)
        if fails >= 2:
            raise Stop("two transitions in a row failed")


def cmd_next(a):
    spec = load_spec(a.spec)
    name = spec["name"]
    st = load_state(name)
    repo, b = st["repo"], st["build"]
    run_dir = os.path.join(DATA, "runs", name)
    os.makedirs(run_dir, exist_ok=True)
    tr, nx = st["transitions"], st.setdefault("next", {})
    fails = 0
    for arm, i in order(a.n, spec["start"], a.arm):
        tag = f"{arm}{i}"
        if tag in nx and nx[tag].get("ok") is not None and not a.redo:
            if not a.no_followup:
                followup(spec, st, tag, run_dir)
            continue
        if a.followups_only:
            continue
        t = tr.get(tag)
        if not t or not t.get("ok"):
            print(f"{tag}: no valid transition, skipped", flush=True)
            continue
        mem = fresh(repo, b["B1"], b["project_dir"], f"{name}-{tag}-n")
        if arm == "H":
            ap = git(repo, "apply", "--binary", os.path.join(run_dir, f"{tag}.patch"))
            if ap.returncode:
                raise Stop(f"{tag}: patch did not apply: {ap.stderr[:200]}")
            args, parent = [NEXT_PROMPT, "--max-turns", str(TURNS["next"])], usage_of(None)
        else:
            args, parent = [NEXT_PROMPT, "--resume", t["sid"], "--max-turns", str(TURNS["next"])], t["total"]
        base_tree = tree_of_worktree(repo)
        git_cfg = os.path.join(repo, ".git", "config")
        cfg = open(git_cfg, "rb").read()
        p, du, out, dt = phase("next", repo, f"{tag}-n", args, parent, run_dir, dict(arm=arm, i=i))
        open(git_cfg, "wb").write(cfg)  # a session-planted fsmonitor/filter must not run in the grader's git
        killed = r2.kill_leftovers(repo)
        d = diff_against(repo, base_tree, os.path.join(run_dir, f"{tag}.next.diff"))
        commits = git(repo, "log", "--format=%s", f"{b['B1']}..HEAD").stdout.split("\n")
        g = grade(spec, repo, d, tool_calls(out))
        rec = dict(arm=arm, i=i, seconds=dt, delta=du, turns=p["turns"], num_turns=(p["result"] or {}).get("num_turns"),
                   first=p["first"], last_ctx=p["last_ctx"], ups=p["ups"], inject=p["inject"],
                   subtype=(p["result"] or {}).get("subtype"), ok=ok_result(p), memory_moved_before=mem,
                   killed=killed, outside=r2.outside_paths(out, repo), commits=[c for c in commits if c][:10],
                   baton=p["baton"], stop_blocks=p["stop_blocks"],
                   files=sorted(parse_diff(d)), **g)
        rec["sid"] = (p["result"] or {}).get("session_id")
        rec["total"] = usage_of(p["result"])
        nx[tag] = rec
        save_state(name, st)
        fresh(repo, b["B1"], b["project_dir"], f"{name}-{tag}-n-after")
        if not a.no_followup:
            followup(spec, st, tag, run_dir)
        fails = 0 if rec["ok"] else fails + 1
        print(f"{tag} next ok={rec['ok']} correct={g['correct']} score={g['score']:.2f} cost=${(du or {}).get('cost', 0):.3f}"
              f" turns={rec['num_turns']}", flush=True)
        if fails >= 2:
            raise Stop("two next-task runs in a row failed")


def followup(spec, st, tag, run_dir):
    """Exploratory (not in the verdict): a run that left the target file untouched gets one neutral reply in the
    same session, then is graded again on the cumulative diff. Same treatment for both arms."""
    name, repo, b = spec["name"], st["repo"], st["build"]
    rec = st["next"][tag]
    if "followup" in rec or not rec.get("ok") or spec["target"] in rec["files"]:
        return
    if not rec.get("sid"):  # rows graded before sid/total were stored
        p0 = parse(os.path.join(run_dir, f"{tag}-n.jsonl"))
        rec["sid"], rec["total"] = p0["result"]["session_id"], usage_of(p0["result"])
    fresh(repo, b["B1"], b["project_dir"], f"{name}-{tag}-f")
    if rec["arm"] == "H":
        git(repo, "apply", "--binary", os.path.join(run_dir, f"{tag}.patch"), check=True)
    base_tree = tree_of_worktree(repo)
    nd = os.path.join(run_dir, f"{tag}.next.diff")
    if os.path.getsize(nd):
        git(repo, "apply", "--binary", nd, check=True)
    git_cfg = os.path.join(repo, ".git", "config")
    cfg = open(git_cfg, "rb").read()
    p, du, out, dt = phase("followup", repo, f"{tag}-f", [FOLLOWUP_PROMPT, "--resume", rec["sid"], "--max-turns", str(TURNS["followup"])],
                           rec["total"], run_dir, dict(arm=rec["arm"], i=rec["i"]))
    open(git_cfg, "wb").write(cfg)
    r2.kill_leftovers(repo)
    d = diff_against(repo, base_tree, os.path.join(run_dir, f"{tag}.followup.diff"))
    g = grade(spec, repo, d, tool_calls(os.path.join(run_dir, f"{tag}-n.jsonl")) + tool_calls(out))
    rec["followup"] = dict(delta=du, num_turns=(p["result"] or {}).get("num_turns"), ok=ok_result(p), seconds=dt,
                           files=sorted(parse_diff(d)), outside=r2.outside_paths(out, repo), **g)
    save_state(name, st)
    fresh(repo, b["B1"], b["project_dir"], f"{name}-{tag}-f-after")
    print(f"{tag} followup ok={rec['followup']['ok']} correct={g['correct']} score={g['score']:.2f} cost=${(du or {}).get('cost', 0):.3f}", flush=True)


# ---------------- grading ----------------
def rules_check(rules, diff, calls=()):
    """forbid_touch: path regex; forbid_added: {file, re} on added lines; forbid_bash: regex on Bash commands
    the next-task session ran. Returns {fact: honored}."""
    files = parse_diff(diff)
    out = {}
    for r in rules:
        fact, ok = r["fact"], True
        if r["type"] == "forbid_touch":
            ok = not any(re.search(r["re"], f) for f in files)
        elif r["type"] == "forbid_added":
            ok = not any(re.search(r["re"], ln) for f, dd in files.items() if re.search(r["file"], f) for ln in dd["added"])
        elif r["type"] == "forbid_bash":
            # executed only: the pattern must start a command segment (a rule quoted in a heredoc is not a run;
            # game-repo H2 was a false positive before this fix, 2026-11-24)
            ok = not any(n == "Bash" and any(re.match(r["re"], seg.strip()) for seg in SEGMENT.split(i.get("command", "")))
                         for n, i in calls)
        else:
            raise ValueError(f"unknown rule type {r['type']}")
        out[fact] = out.get(fact, True) and ok
    return out


def grade(spec, repo, diff, calls):
    hidden = os.path.join(os.path.dirname(spec["_path"]), spec["hidden"])
    try:
        h = subprocess.run([sys.executable, "-I", hidden, repo], capture_output=True, text=True, timeout=600)
        tests = json.loads(h.stdout.strip().splitlines()[-1])
    except Exception as e:  # a broken hidden harness must not look like a model failure
        raise Stop(f"hidden tests crashed: {e!r}")
    rules = rules_check(spec["rules"], diff, calls)
    checks = {}
    for fact in spec["checks"]:
        vals = [tests[fact]] if fact in tests else []
        vals += [rules[fact]] if fact in rules else []
        checks[fact] = bool(vals) and all(vals)
    correct = all(checks[f] for f in spec["hard"])
    return dict(checks=checks, tests=tests, rules=rules, correct=correct,
                score=sum(checks.values()) / len(checks), n_tool_calls=len(calls))


def cmd_regrade(a):
    """Recompute rule checks from the saved next-task diffs and tool calls (hidden-test results are stored)."""
    spec = load_spec(a.spec)
    st = load_state(spec["name"])
    run_dir = os.path.join(DATA, "runs", spec["name"])
    for tag, rec in sorted(st.get("next", {}).items()):
        for key, diff_f, calls in (("", f"{tag}.next.diff", [f"{tag}-n.jsonl"]),
                                   ("followup", f"{tag}.followup.diff", [f"{tag}-n.jsonl", f"{tag}-f.jsonl"])):
            r = rec.get(key) if key else rec
            if key and (not r or not r.get("ok")):
                continue
            c = [x for f in calls for x in tool_calls(os.path.join(run_dir, f))]
            rules = rules_check(spec["rules"], open(os.path.join(run_dir, diff_f)).read(), c)
            checks = {f: all(([r["tests"][f]] if f in r["tests"] else []) + ([rules[f]] if f in rules else [])) for f in spec["checks"]}
            new = dict(rules=rules, checks=checks, correct=all(checks[f] for f in spec["hard"]), score=sum(checks.values()) / len(checks))
            if new["correct"] != r["correct"] or new["score"] != r["score"]:
                print(f"{spec['name']} {tag}{'-' + key if key else ''}: correct {r['correct']} -> {new['correct']}, score {r['score']:.3f} -> {new['score']:.3f}")
                r.setdefault("grade_history", []).append({k: r[k] for k in ("rules", "checks", "correct", "score")})
            r.update(new)
    save_state(spec["name"], st)


def load_spec(path):
    spec = json.load(open(path))
    spec["_path"] = path
    return spec


# ---------------- report ----------------
def cmd_report(a):
    import statistics as stt
    names = [a.repo] if a.repo else sorted(os.path.basename(p)[:-5] for p in os.listdir(os.path.join(DATA, "state")) if p.endswith(".json"))
    def rng(v):
        v = [x for x in v if x is not None]
        return f"{stt.median(v):.3g} [{min(v):.3g}-{max(v):.3g}]" if v else "-"
    for name in names:
        st = load_state(name)
        b = st.get("build", {})
        print(f"=== {name}: build ctx={b.get('steps', [{}])[-1].get('last_ctx')} cost=${b.get('total', {}).get('cost', 0):.2f}")
        for arm in ("C", "H"):
            rows = [(st["transitions"][t], r) for t, r in st.get("next", {}).items() if r["arm"] == arm and r["ok"]]
            if not rows:
                continue
            tot = lambda k: [tt["delta"][k] + r["delta"][k] for tt, r in rows]
            print(f" {arm} n={len(rows)} correct={sum(r['correct'] for _, r in rows)} score={rng([r['score'] for _, r in rows])}"
                  f" cost_warm={rng([warm_cost(tt) + r['delta']['cost'] for tt, r in rows])} cost_raw={rng(tot('cost'))}"
                  f" next_cost={rng([r['delta']['cost'] for _, r in rows])}"
                  f" trans_warm={rng([warm_cost(tt) for tt, _ in rows])} trans_raw={rng([tt['delta']['cost'] for tt, _ in rows])}")
            print(f"    input(in+cc+cr)={rng([sum(tt['delta'][k] + r['delta'][k] for k in ('inputTokens', 'cacheCreationInputTokens', 'cacheReadInputTokens')) for tt, r in rows])}"
                  f" cache_read={rng(tot('cacheReadInputTokens'))} cache_create={rng(tot('cacheCreationInputTokens'))}"
                  f" uncached={rng(tot('inputTokens'))} output={rng(tot('outputTokens'))}")
            fu = [r for _, r in rows if r.get("followup", {}).get("ok")]
            bad = [r["i"] for _, r in rows if "followup" in r and not r["followup"].get("ok")]
            after = [r["followup"]["correct"] if r.get("followup", {}).get("ok") else r["correct"] for _, r in rows]
            if bad:
                print(f"    exploratory follow-ups invalid (interrupted): {arm}{bad}")
            print(f"    exploratory: stopped without touching the target={len(fu)}; correct after one neutral reply="
                  f"{sum(after)}/{len(rows)}; follow-up cost={rng([r['followup']['delta']['cost'] for r in fu])}")
            print(f"    next turns={rng([r['num_turns'] for _, r in rows])} first_ctx={rng([sum(r['first'].values()) for _, r in rows if r['first']])}"
                  f" checks=" + " ".join(f"{f}:{sum(r['checks'][f] for _, r in rows)}" for f in rows[0][1]["checks"]))
    states = {n: load_state(n) for n in names}
    print("primary (warm-normalized transition cost):", verdict(states, True))
    print("sensitivity (raw reported cost):          ", verdict(states, False))
    print(f"ledger total ${spent():.2f} of ${CAP_USD}")


def warm_cost(t):
    """Transition cost had S's prompt cache been warm, as at a real task boundary (deviation, 2026-11-24):
    C reprices its uncached input as cache reads (a warm compaction read 237,700 of 239,748 from cache);
    H reprices its first turn's cache creation as cache reads (a warm H fork's first turn creates 0)."""
    d = t["delta"]
    if t["arm"] == "C":
        return d["cost"] - d["inputTokens"] * (PRICE["in"] - PRICE["cr"])
    first = (t.get("first") or {}).get("cache_creation_input_tokens", 0)
    return d["cost"] - first * (PRICE["cw"] - PRICE["cr"])


def run_cost(st, tag, r, warm=True):
    t = st["transitions"][tag]
    return (warm_cost(t) if warm else t["delta"]["cost"]) + r["delta"]["cost"]


def verdict(states, warm=True):
    """The pre-registered decision rule (docs/research/compact-vs-handoff.md)."""
    import math, statistics as stt
    pairs, ratios, cheaper_h, k, n = {}, [], 0, {"C": 0, "H": 0}, {"C": 0, "H": 0}
    for name, st in states.items():
        cost = {"C": [], "H": []}
        for tag, r in st.get("next", {}).items():
            if not r.get("ok"):
                continue
            arm = r["arm"]
            cost[arm].append(run_cost(st, tag, r, warm))
            k[arm] += r["correct"]
            n[arm] += 1
        pairs[name] = min(len(cost["C"]), len(cost["H"]))
        if pairs[name] >= 3:
            ratio = stt.median(cost["H"]) / stt.median(cost["C"])
            ratios.append(ratio)
            cheaper_h += ratio < 1
    eligible = [x for x in pairs if pairs[x] >= 3]
    if len(eligible) < 2:
        return f"VERDICT: inconclusive (repos with >=3 valid pairs: {eligible}; pairs={pairs})"
    N = min(n.values())
    a, b = max(1, round(N / 15)), math.ceil(0.2 * N)
    r = stt.median(ratios)
    m = len(ratios)
    if (k["H"] >= k["C"] - a and r <= 0.85 and cheaper_h >= m - 1) or (k["H"] - k["C"] >= b and r <= 1.10):
        v = "handoff better"
    elif (k["C"] >= k["H"] - a and 1 / r <= 0.85 and (m - cheaper_h) >= m - 1) or (k["C"] - k["H"] >= b and 1 / r <= 1.10):
        v = "compact better"
    elif (k["H"] - k["C"] >= b and r > 1.10) or (k["C"] - k["H"] >= b and 1 / r > 1.10):
        v = "trade-off"
    else:
        v = "no difference detected"
    return (f"VERDICT: {v}  (k_C={k['C']}/{n['C']} k_H={k['H']}/{n['H']} r=median H/C cost={r:.3f} per-repo={[round(x, 3) for x in ratios]}"
            f" a={a} b={b} repos={eligible})")


def cmd_seed(a):
    """Round 2: copy a round-1 state (snapshot, build S and the kept arm's transitions/next rows) into CVH_DATA.
    The snapshot tree and S's transcript stay where round 1 made them; nothing in the source folder is written."""
    src = os.path.join(os.path.expanduser(a.src), "state", f"{a.name}.json")
    dst = state_path(a.name)
    if os.path.exists(dst):
        sys.exit(f"exists: {dst}")
    st = json.load(open(src))
    keep = lambda rows: {t: r for t, r in rows.items() if r.get("arm") == a.keep}
    new = dict(snapshot=st["snapshot"], repo=st["repo"], build=st["build"], transitions=keep(st.get("transitions", {})),
               next=keep(st.get("next", {})), seeded=dict(src=src, keep=a.keep, at=time.strftime("%FT%T")))
    check_S(new["build"])
    save_state(a.name, new)
    print(f"seeded {a.name}: {len(new['transitions'])} transitions, {len(new['next'])} next rows of arm {a.keep}")


def cmd_ledger(a):
    by = {}
    for r in ledger_rows():
        by[r["kind"]] = by.get(r["kind"], 0) + r["charged"]
    print(json.dumps({k: round(v, 3) for k, v in by.items()}), f"total ${spent():.2f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot"); s.add_argument("--name", required=True); s.add_argument("--src", required=True)
    s.add_argument("--commit", default="HEAD"); s.add_argument("--setup"); s.add_argument("--remove", nargs="*", default=["HANDOFF.md", "handoffs"])
    for c in ("build", "transitions", "next", "regrade"):
        x = sub.add_parser(c); x.add_argument("--spec", required=True); x.add_argument("--n", type=int, default=5)
        x.add_argument("--redo", action="store_true")
        x.add_argument("--no-followup", action="store_true"); x.add_argument("--followups-only", action="store_true")
        x.add_argument("--arm", choices=("C", "H"))
    e = sub.add_parser("seed"); e.add_argument("--src", required=True); e.add_argument("--name", required=True)
    e.add_argument("--keep", default="C", choices=("C", "H"))
    r = sub.add_parser("report"); r.add_argument("--repo")
    sub.add_parser("ledger")
    a = ap.parse_args()
    if getattr(a, "spec", None):
        a.spec = os.path.abspath(a.spec)
    fn = {"snapshot": cmd_snapshot, "build": cmd_build, "transitions": cmd_transitions, "next": cmd_next,
          "report": cmd_report, "ledger": cmd_ledger, "regrade": cmd_regrade, "seed": cmd_seed}[a.cmd]
    try:
        fn(a)
    except Stop as e:
        print(f"STOP: {e}", flush=True)
        sys.exit(3)
    except Exception:
        import traceback
        traceback.print_exc()
        print("STOP: unexpected error", flush=True)
        sys.exit(4)
