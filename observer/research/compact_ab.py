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

Round 3 (next day, different task; docs/research/compact-vs-handoff-r3.md): seed --from <r1>:C --from <r2>:H, startstate,
probe-cut, preflight, next --pilot, gate, next, report --task T1|T2. Write-cost re-measure (W): seed --from <r2>:H,
startstate, wstage, wprobe, write, wreport. W2 (docs/research/handoff-write-w2.md): the same with CVH_WREF=<W's folder>,
plus wenv ($0) after wprobe.

Cost accounting: total_cost_usd and modelUsage of a --resume/--fork-session child INCLUDE the parent's usage
(probed 2026-11-23 on 6 parent->child pairs), so every phase is charged child minus parent. The /compact call
reports result.usage = 0 and num_turns = 0; its tokens exist only in modelUsage. Raw data never goes in a repo.
"""
import argparse, hashlib, json, os, re, shutil, subprocess, sys, tempfile, time

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
# W2 (2026-11-26): the staged build (CVH_BATON) and the owner's install may differ in version; CVH_BATON_INSTALLED is the
# installed one (preflight, and any call without --plugin-dir). Unset: the same as CVH_BATON, as in rounds 1-3 and W.
BATON_INSTALLED = os.environ.get("CVH_BATON_INSTALLED") or BATON_REQUIRED
# W2: CVH_WREF=<an earlier W data folder> also judges the new W runs against that folder's valid W runs (not only round 2).
WREF = os.environ.get("CVH_WREF")
# W2 (amendment 3, before any W2 run): against CVH_WREF, "cheaper" needs the W2/W median warm-cost ratio <= this in both
# repos. Used only with a reference W; W's own rule against round 2 has no margin.
W2_RATIO = 0.90
# Round 3 (2026-11-25): also pin OMC and the Claude Code CLI (round 2 drifted from OMC 5.8.4 to 5.8.7 mid-run, unnoticed).
OMC_REQUIRED = os.environ.get("CVH_OMC")
CLI_REQUIRED = os.environ.get("CVH_CLI")
# Review fixes (2026-11-25): pin the model (checked on every init line) and the effort level. Rounds 1-2 ran every
# session at effort xhigh (their transcripts' assistant entries); the owner's settings now give high, so round 3 and
# W pass --effort and check each new assistant entry's effort in the session transcript.
MODEL_REQUIRED = os.environ.get("CVH_MODEL")
EFFORT = os.environ.get("CVH_EFFORT")
# The CLI binary, resolved once to its versioned executable, so an update of the `claude` symlink mid-run changes nothing.
CLAUDE_BIN = os.path.realpath(os.environ.get("CVH_CLAUDE_BIN") or shutil.which("claude") or "claude")
MARGIN = 0.5            # a turn can overshoot --max-budget-usd
CAPS = {"build": 2.0, "transition": 3.0, "next": 4.0, "followup": 4.0, "probe": 1.0}  # transition 2.0 -> 3.0 after cold H forks hit the cap (2026-11-24)
# Fitted from the four opus probe deltas (exact solve, $/token): used only to reprice cache state, never as billing.
PRICE = {"in": 3.96e-6, "cw": 8.00e-6, "cr": 0.201e-6, "out": 19.95e-6}
TURNS = {"build": 25, "transition": 15, "next": 30, "followup": 30, "probe": 1}
FLAGS = ["--output-format", "stream-json", "--verbose", "--include-hook-events"]
NEXT_PROMPT = "이어서 해줘"
FOLLOWUP_PROMPT = "알아서 판단해서 진행해줘"  # exploratory, added 2026-11-24 after pilot H1 stopped to ask
HANDOFF_PROMPT = "핸드오프 작성해줘"
PROBE_PROMPT = "OK라고만 답해"
INSTALLED_BATON = os.path.expanduser("~/.claude/plugins/cache/baton/")  # W must never touch the installed build
CUT_TOL = 0.10          # a truncated fork's first turn must be within 10% of round 1's T1 first turn
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
# baton 1.0.0's injection headers (hooks/handoff-inject.py HEAD/HEAD_EN; the concept index and concept section heads)
HANDOFF_HEADS = ("HANDOFF.md의 전문", "this repo's full HANDOFF.md")
CONCEPT_HEADS = ("개념 지도(CONCEPTS.md) 색인", "concept map (CONCEPTS.md)", "맞은 개념 한 절", "one concept section")


def hook_context(stdout):
    """A hook's additionalContext when its stdout is JSON (the raw text may hold escaped characters)."""
    try:
        j = json.loads(stdout or "")
    except Exception:
        return ""
    ctx = (j.get("hookSpecificOutput") or {}).get("additionalContext") if isinstance(j, dict) else None
    return ctx if isinstance(ctx, str) else ""


def parse(path):
    """Numbers only from a stream-json file. Main-thread turns are counted per API message id."""
    p = dict(result=None, boundary=[], first=None, last_ctx=None, turns=0, ups=[], inject=False, hooks={},
             baton=None, stop_blocks=0, omc=None, cli=None, plugins=None, skills=[], ctx_sum=0, model=None,
             inject_handoff=False, inject_concept=False, msg_ids=[])
    seen = set()
    for ln in open(path, encoding="utf-8", errors="replace"):
        try:
            d = json.loads(ln)
        except Exception:
            continue
        t, st = d.get("type"), d.get("subtype")
        if t == "system" and st == "init":
            if p["plugins"] is None:  # versions come from the call's first init line
                p["plugins"] = [{k: x.get(k) for k in ("name", "source", "path", "version")} for x in d.get("plugins") or []]
                ver = lambda n: next((x["version"] for x in p["plugins"] if x["name"] == n), None)
                p["baton"], p["omc"], p["cli"] = ver("baton"), ver("oh-my-claudecode"), d.get("claude_code_version")
                p["model"] = d.get("model")
                p["skills"] = [x for x in d.get("skills") or [] if x.startswith("baton:")]
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
            text = out + hook_context(d.get("stdout"))
            p["inject"] = p["inject"] or "[baton" in out  # rounds 1-2: any baton line (the concept index matches too)
            p["inject_handoff"] = p["inject_handoff"] or any(h in text for h in HANDOFF_HEADS)
            p["inject_concept"] = p["inject_concept"] or any(h in text for h in CONCEPT_HEADS)
        elif t == "assistant" and not d.get("parent_tool_use_id"):
            mid = (d.get("message") or {}).get("id") or d.get("uuid")
            if mid in seen:
                continue
            seen.add(mid)
            p["msg_ids"].append(mid)
            u = (d.get("message") or {}).get("usage") or {}
            tok = {k: u.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")}
            p["turns"] += 1
            p["last_ctx"] = sum(tok.values())
            p["ctx_sum"] += p["last_ctx"]
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
def plugin_problem(p, staged):
    """W: the staged build must be the only baton loaded, and from the staged folder (its version string may equal
    the installed one, so the path is the guard)."""
    batons = [x for x in p["plugins"] or [] if x["name"] == "baton"]
    if len(batons) != 1:
        return f"{len(batons)} baton plugins loaded"
    if batons[0]["source"] == "baton@baton" or os.path.realpath(batons[0]["path"] or "") != os.path.realpath(staged):
        return f"baton loaded from {batons[0]['path']} ({batons[0]['source']}), not the staged build {staged}"
    return None


def version_problem(p, plugin_dir=None):
    for want, got, what in ((BATON_REQUIRED if plugin_dir else BATON_INSTALLED, p["baton"], "baton"), (OMC_REQUIRED, p["omc"], "OMC"),
                            (CLI_REQUIRED, p["cli"], "Claude Code"), (MODEL_REQUIRED, p.get("model"), "model")):
        if want and got != want:
            return f"{what} {got} loaded, {want} required (do not update anything mid-run)"
    inline = [x["name"] for x in p["plugins"] or [] if (x["source"] or "").endswith("@inline") and not (plugin_dir and x["name"] == "baton")]
    if inline:  # rounds 1-2 loaded no session-only plugin
        return f"unexpected session-only plugin(s) {inline}"
    return None


# Never inherited by a child call (2026-11-25). CLAUDE_CODE_PLUGIN_DIRS: the launching terminal injected its own viewer
# plugin into every child call; rounds 1-2 had none. The rest mark the launcher as a Claude Code session and would tie
# the child to it (identity, messaging socket, notes folder, the parent's effort as seen by its hooks).
HOST_ENV_DROP = ("CLAUDE_CODE_PLUGIN_DIRS", "CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_CHILD_SESSION",
                 "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SESSION_ATTENDED", "CLAUDE_CODE_MESSAGING_SOCKET",
                 "CLAUDE_CODE_MESSAGING_TOKEN", "CLAUDE_CODE_CHILD_NOTES_DIR", "CLAUDE_CODE_EXECPATH", "CLAUDE_PID",
                 "CLAUDE_EFFORT")


def child_env():
    env = {k: v for k, v in os.environ.items() if k not in HOST_ENV_DROP}
    env["BATON_OBSERVE"] = "off"
    env["DISABLE_AUTOUPDATER"] = "1"
    return env


def env_names(env):
    """Names (never values) of the CLAUDE*/ANTHROPIC* variables a child call still sees; recorded per call."""
    return sorted(k for k in env if k.startswith(("CLAUDE", "ANTHROPIC")))


_cli_ok = []


def ensure_cli():
    """Before this process's first paid call: the pinned binary must report the required version."""
    if _cli_ok:
        return
    out = subprocess.run([CLAUDE_BIN, "--version"], capture_output=True, text=True, stdin=subprocess.DEVNULL,
                         env=child_env()).stdout.split()
    got = out[0] if out else None
    if CLI_REQUIRED and got != CLI_REQUIRED:
        raise Stop(f"{CLAUDE_BIN} reports {got}, {CLI_REQUIRED} required")
    _cli_ok.append(got)


def session_effort(sid, msg_ids):
    """Effort levels on this call's own assistant entries (matched by API message id) in the session transcript."""
    pdir = project_dir(sid) if sid else None
    if not pdir or not msg_ids:
        return []
    want = set(msg_ids)
    return sorted({d.get("perTurnEffort") or d.get("effort") or "?" for d in read_rows(os.path.join(pdir, sid + ".jsonl"))
                   if d.get("type") == "assistant" and (d.get("message") or {}).get("id") in want})


def phase(kind, repo, tag, args, parent, run_dir, extra=None, plugin_dir=None, prepare=None):
    """Run one claude call with budget guard, rate-limit backoff and ledger entries. Returns (parse, delta usage).
    plugin_dir (W): the call must load exactly that baton build (checked on the init line).
    Ledger: a pending row at the cap before the call, then a correction to the reported delta (a killed call stays
    charged at its cap). Rate limit: prepare() restores the clean start state before the retry; without prepare
    (a resumed session, which a retry would extend) the limited result is returned for the caller to record invalid."""
    cap = CAPS[kind]
    for attempt in range(len(BACKOFF) + 1):
        if os.path.exists(os.path.join(DATA, "STOP")):  # graceful stop: `touch $CVH_DATA/STOP`, remove it to resume
            raise Stop(f"STOP file in {DATA}: stopped before {tag}")
        ensure_cli()
        guard(cap)
        out = os.path.join(run_dir, f"{tag}.jsonl" if attempt == 0 else f"{tag}.a{attempt + 1}.jsonl")
        cmd = [CLAUDE_BIN, "-p"] + args + FLAGS + ["--max-budget-usd", str(cap)] + (["--effort", EFFORT] if EFFORT else [])
        if plugin_dir:
            cmd += ["--plugin-dir", plugin_dir, "--settings", os.path.join(DATA, "settings-w.json")]
        env = child_env()
        base = dict(kind=kind, repo=os.path.basename(repo), tag=tag, attempt=attempt + 1, **(extra or {}))
        ledger_add(dict(base, phase="pending", charged=cap))
        t0 = time.time()
        with open(out, "w") as fo, open(out + ".err", "w") as fe:
            rc = subprocess.run(cmd, cwd=repo, stdin=subprocess.DEVNULL, stdout=fo, stderr=fe, env=env).returncode
        dt = round(time.time() - t0)
        p = parse(out)
        err = open(out + ".err", errors="replace").read()
        if p["result"] is not None:
            du = delta(usage_of(p["result"]), parent)
            charged = max(du["cost"], 0.0)
        else:
            du, charged = None, cap  # unknown spend: charge the worst case
        limited = rate_limited(p, err)
        p["rate_limited"] = limited
        p["efforts"] = session_effort((p["result"] or {}).get("session_id"), p["msg_ids"])
        ledger_add(dict(base, phase="final", charged=round(charged - cap, 6), cost=round(charged, 6), rc=rc, seconds=dt,
                        cost_reported=(p["result"] or {}).get("total_cost_usd"), rate_limited=limited, baton=p["baton"],
                        omc=p["omc"], cli=p["cli"], model=p["model"], efforts=p["efforts"], stop_blocks=p["stop_blocks"],
                        env_names=env_names(env), bin=CLAUDE_BIN))
        bad = version_problem(p, plugin_dir) or (plugin_dir and plugin_problem(p, plugin_dir))
        if not bad and EFFORT and any(e != EFFORT for e in p["efforts"]):
            bad = f"effort {p['efforts']} used, {EFFORT} required"
        if bad:
            raise Stop(f"{tag}: {bad}")
        print(f"  {tag} a{attempt + 1}: rc={rc} {dt}s charged=${charged:.3f} total=${spent():.2f}"
              f"{' RATE-LIMITED' if limited else ''}", flush=True)
        if not limited or prepare is None:
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
            print(f"  backing off {wait:.0f}s, then back to the clean start state", flush=True)
            time.sleep(wait)
            prepare()
    raise Stop("rate limit persists after backoff")


VALID_ERRORS = ("error_max_turns", "error_max_budget_usd")


def ok_result(p):
    """Valid (graded) run: a result line that is a success, or that ended on the turn or budget cap (pre-registered:
    error_max_turns is a valid run; error_max_budget_usd likewise, its cost recorded). Any other error is invalid."""
    res = p["result"]
    if res is None or p.get("rate_limited"):
        return False
    return res.get("subtype") in VALID_ERRORS or (res.get("subtype") == "success" and not res.get("is_error"))


def cap_charge(kind, tag, charged):
    """When a delta check says the reported delta cannot be trusted, charge that call at its cap."""
    if CAPS[kind] > charged:
        ledger_add(dict(kind=kind, tag=f"{tag}-cap-correction", phase="correction", charged=round(CAPS[kind] - charged, 6)))


def delta_ok(du, p):
    """The child's delta must cover at least 95% of the call's own main-thread input (parent rule still holds)."""
    if du is None:
        return True
    got = sum(du.get(k, 0) for k in ("inputTokens", "cacheCreationInputTokens", "cacheReadInputTokens"))
    return got >= 0.95 * p["ctx_sum"]


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


def order(n, start, arm=None, z=0):
    """Counterbalanced ABBA order: C H H C C H H C C H (start=C) or its mirror. Returns [(arm, i)].
    arm="H" keeps only that arm (round 2 reruns the handoff arm; the C rows are seeded from round 1).
    z: that many no-carrier Z runs first (round 3 pilot)."""
    if arm:
        return [x for x in order(n, start) if x[0] == arm]
    if z:
        return [("Z", k) for k in range(1, z + 1)] + order(n, start)
    pat = "CHHC" if start == "C" else "HCCH"
    seq, counts = [], {"C": 0, "H": 0}
    while min(counts.values()) < n:
        for arm in pat:
            if counts[arm] < n:
                counts[arm] += 1
                seq.append((arm, counts[arm]))
    return seq


def pilot_order(start):
    """Round 3 pilot: Z1, then the first C and first H of the ABBA order."""
    return order(1, start, z=1)


def rows(st, task=None):
    """Next-task rows: T1 = the planned task (seeded round-1/2 records in round 3, `next` in rounds 1-2); else `next`."""
    return st["t1"] if task == "T1" and "t1" in st else st.get("next", {})


def start_base(st):
    return (st.get("start") or {}).get("base") or st["build"]["B1"]


def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def sig(path):
    return dict(size=os.path.getsize(path), mtime=os.path.getmtime(path), sha256=sha256_file(path))


def transcript(b, sid):
    return os.path.join(b["project_dir"], sid + ".jsonl")


def check_parents(st):
    """Round 3: S and every reused compaction must keep size, mtime and sha256 across every call (draft guard)."""
    for sid, want in (st.get("parents") or {}).items():
        now = sig(transcript(st["build"], sid))
        if now != want:
            raise Stop(f"parent transcript {sid} changed: {want} -> {now}")


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


def dropped_attachments(path, names, until=None):
    """`file` attachments (files Claude Code re-attaches after a compaction) whose basename is in `names`, from the
    last compact boundary up to the entry `until` (inclusive) or the end. Review fix 2026-11-25: every reused
    game-repo compaction carried the build-written HANDOFF.md this way, which B1' was meant to remove."""
    rows_ = read_rows(path)
    bi = max((i for i, d in enumerate(rows_) if d.get("type") == "system" and d.get("subtype") == "compact_boundary"), default=None)
    hits = []
    for d in rows_[bi:] if bi is not None else []:
        att = d.get("attachment") or {}
        if d.get("type") == "attachment" and att.get("type") == "file" and os.path.basename(att.get("filename") or "") in names:
            hits.append(os.path.basename(att["filename"]))
        if until and d.get("uuid") == until:
            break
    return hits


def compaction_ok(p, du):
    """A compaction happened and was paid for: a compact boundary with pre_tokens > 0, and a positive cost delta."""
    return bool(p["boundary"]) and (p["boundary"][-1].get("pre_tokens") or 0) > 0 and (du or {}).get("cost", 0) > 0


def cmd_transitions(a):
    spec = load_spec(a.spec)
    name = spec["name"]
    st = load_state(name)
    repo, b = st["repo"], st["build"]
    assert b.get("done"), "build first"
    run_dir = os.path.join(DATA, "runs", name)
    os.makedirs(run_dir, exist_ok=True)  # round 2 skips build, which used to create it
    tr = st.setdefault("transitions", {})
    base = start_base(st)  # round 3: fresh compactions run on the round-3 start state (the game repo's B1')
    fresh_c = getattr(a, "fresh", False)
    if fresh_c:  # round-3 fallback: fresh day-2 compactions replace every reused one (kept under "reused" for T1)
        for tag in sorted(t for t, r in tr.items() if r.get("arm") == "C" and r.get("reused_from")):
            st.setdefault("reused", {})[tag] = tr.pop(tag)
        save_state(name, st)
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
        prepare = lambda: fresh(repo, base, b["project_dir"], f"{name}-{tag}-t")
        mem = prepare()
        check_parents(st)
        if arm == "C":
            args = ["/compact", "--resume", b["sid"], "--fork-session"]
        else:
            args = [HANDOFF_PROMPT, "--resume", b["sid"], "--fork-session", "--max-turns", str(TURNS["transition"])]
        p, du, out, dt = phase("transition", repo, f"{tag}-t", args, b["total"], run_dir, dict(arm=arm, i=i), prepare=prepare)
        check_S(b)
        check_parents(st)
        rec = dict(arm=arm, i=i, seconds=dt, delta=du, memory_moved_before=mem, turns=p["turns"],
                   first=p["first"], hooks=p["hooks"], subtype=(p["result"] or {}).get("subtype"),
                   baton=p["baton"], omc=p["omc"], cli=p["cli"], stop_blocks=p["stop_blocks"], fork=fresh_c, base=base)
        okr = ok_result(p) and delta_ok(du, p)
        if arm == "C":
            rec["boundary"] = p["boundary"][-1] if p["boundary"] else None
            rec["sid"] = (p["result"] or {}).get("session_id")
            rec["total"] = usage_of(p["result"])
            rec["ok"] = okr and compaction_ok(p, du) and rec["sid"] != b["sid"]
            if rec["ok"] and fresh_c:
                f = transcript(b, rec["sid"])
                rec["dropped_attached"] = dropped_attachments(f, spec.get("drop_at_start") or [])
                rec["ok"] = not rec["dropped_attached"]
                if rec["ok"]:
                    st.setdefault("parents", {})[rec["sid"]] = sig(f)  # the new carrier must stay unchanged too
        else:
            r2.kill_leftovers(repo)
            patch = os.path.join(run_dir, f"{tag}.patch")
            d = diff_against(repo, base, patch)
            files = sorted(parse_diff(d))
            rec["patch_files"] = files
            ho = os.path.join(repo, "HANDOFF.md")
            rec["handoff_bytes"] = os.path.getsize(ho) if os.path.exists(ho) else 0
            rec["ok"] = okr and "HANDOFF.md" in files
        rec["failed_attempts"] = prev
        tr[tag] = rec
        save_state(name, st)
        fresh(repo, base, b["project_dir"], f"{name}-{tag}-t-after")
        if rec.get("dropped_attached"):
            raise Stop(f"{tag}: the fresh compaction re-attached {rec['dropped_attached']} although the start state lacks it")
        fails = 0 if rec["ok"] else fails + 1
        print(f"{tag} transition ok={rec['ok']} cost=${(du or {}).get('cost', 0):.3f}", flush=True)
        if fails >= 2:
            raise Stop("two transitions in a row failed")


def place_carrier(st, tag, repo, run_dir):
    """Put H's handoff on the clean start state: round 3 writes the stored full file (sha checked first);
    rounds 1-2 apply the patch. C and Z put nothing in the tree."""
    t = st["transitions"].get(tag) or {}
    if t.get("arm") != "H":
        return
    if "handoff_sha256" in t:
        data = open(os.path.join(run_dir, f"{tag}.handoff.md"), "rb").read()
        if hashlib.sha256(data).hexdigest() != t["handoff_sha256"]:
            raise Stop(f"{tag}: stored handoff sha256 mismatch (invalid run)")
        with open(os.path.join(repo, "HANDOFF.md"), "wb") as f:
            f.write(data)
        return
    ap = git(repo, "apply", "--binary", os.path.join(run_dir, f"{tag}.patch"))
    if ap.returncode:
        raise Stop(f"{tag}: patch did not apply: {ap.stderr[:200]}")


def carrier_args(spec, st, arm, tag):
    """(claude args, parent usage) for the next task of one arm. A repo revised at the pilot gate uses the
    pre-registered revised prompt."""
    prompt = spec["revised_prompt"] if st.get("revision") else spec.get("next_prompt", NEXT_PROMPT)
    turns = ["--max-turns", str(TURNS["next"])]
    if arm in ("H", "Z"):
        return [prompt] + turns, usage_of(None)
    t = st["transitions"][tag]
    if t.get("cut"):  # round 3: round 1's compaction, truncated just before its T1 prompt (probe-cut)
        pc = st.get("probe_cut") or {}
        if not pc.get("ok"):
            raise Stop("C reuse needs a passed probe-cut (or the fresh-compaction fallback)")
        parent = {"compaction": t["total"], "t1": (st["t1"].get(tag) or {}).get("total"), "none": usage_of(None)}[pc["rule"]]
        cut = t["cut"]
        return [prompt, "--resume", t["sid"], "--resume-session-at", cut["at"], "--fork-session"] + turns, parent
    if t.get("fork"):  # round-3 fallback: fresh compaction, forked so the carrier stays unchanged
        return [prompt, "--resume", t["sid"], "--fork-session"] + turns, t["total"]
    return [prompt, "--resume", t["sid"]] + turns, t["total"]  # rounds 1-2


def first_prompt_after_boundary(rows_):
    """(index, entry, text) of the first real user prompt after the last compact_boundary, or None."""
    bi = max((i for i, d in enumerate(rows_) if d.get("type") == "system" and d.get("subtype") == "compact_boundary"), default=None)
    if bi is None:
        return None
    for i in range(bi + 1, len(rows_)):
        text = real_prompt(rows_[i])
        if text:
            return i, rows_[i], text
    return None


def read_rows(path):
    out = []
    for ln in open(path, encoding="utf-8", errors="replace"):
        try:
            out.append(json.loads(ln))
        except Exception:
            pass
    return out


def real_prompt(d):
    if d.get("type") != "user" or d.get("isMeta") or d.get("isCompactSummary"):
        return None
    c = (d.get("message") or {}).get("content")
    text = c if isinstance(c, str) else "".join(x.get("text", "") for x in c or [] if isinstance(x, dict) and x.get("type") == "text")
    return text.strip() if text.strip() and not text.lstrip().startswith("<") else None


def cut_of(path):
    """Truncation point for reusing a round-1 compaction: the entry just before its first real prompt (T1's).
    Also summarizes what the truncation discards. The CLI's own --resume-drops-turn check refuses these resumes
    because T1's async PostToolUse hook responses sit in that range (probe, 2026-11-25), so the runner checks the
    range itself: exactly one real prompt, T1's, and nothing else from another turn."""
    rows_ = read_rows(path)
    hit = first_prompt_after_boundary(rows_)
    if not hit:
        raise Stop(f"no prompt after a compact boundary in {path}")
    i, d, text = hit
    ci = next(k for k, x in enumerate(rows_) if x.get("uuid") == d["parentUuid"])
    rest = rows_[ci + 1:]
    prompts = [p_ for p_ in (real_prompt(x) for x in rest) if p_]
    return dict(at=d["parentUuid"], drops=d["uuid"], prompt=text[:40], discard_entries=len(rest),
                discard_prompts=[p_[:40] for p_ in prompts])


def cut_problems(st, tag, p, first_ref):
    """Per-run checks of a truncated fork: new session id, no T1 entry in the fork, first turn within CUT_TOL."""
    t, out = st["transitions"][tag], []
    sid = (p["result"] or {}).get("session_id")
    if not sid or sid == t["sid"]:
        return ["no new session id"]
    f = transcript(st["build"], sid)
    if not os.path.exists(f):
        return ["fork transcript missing"]
    rows_ = read_rows(f)
    if any(d.get("uuid") == t["cut"]["drops"] for d in rows_):
        out.append("T1 prompt entry present in the fork")
    hit = first_prompt_after_boundary(rows_)
    if hit and hit[2].startswith(t["cut"]["prompt"]):
        out.append("first prompt after the boundary is still T1's")
    if first_ref and p["first"]:
        got, ref = sum(p["first"].values()), sum(first_ref.values())
        if abs(got - ref) > CUT_TOL * ref:
            out.append(f"first turn {got} vs round-1 T1 {ref}")
    return out


def handoff_reads(calls):
    """How often the session looked at HANDOFF.md (Read, or a Bash cat/head/sed/grep/less of it)."""
    n = 0
    for name, i in calls:
        if name == "Read" and str(i.get("file_path", "")).endswith("HANDOFF.md"):
            n += 1
        elif name == "Bash" and re.search(r"\b(cat|head|tail|sed|grep|less|wc)\b[^|;&]*HANDOFF\.md", i.get("command", "")):
            n += 1
    return n


THIRD_TOOL = re.compile(r"session_search|memory|notepad|wiki", re.I)
THIRD_PATH = re.compile(r"/\.claude/projects/|~/\.omc\b|\$\{?HOME\}?/\.omc\b|" + re.escape(os.path.expanduser("~/.omc")))


def all_calls(path):
    """Every tool call in a stream, subagents included (name, input)."""
    out = []
    for d in read_rows(path):
        if d.get("type") == "assistant":
            out += [(c.get("name"), c.get("input") or {}) for c in (d.get("message") or {}).get("content") or []
                    if isinstance(c, dict) and c.get("type") == "tool_use"]
    return out


def third_carrier(calls):
    """Calls that could carry facts from outside the arm: session search, memory/notepad/wiki tools, or a path into
    the transcript folders or OMC's global state (diagnostic, counted per run)."""
    return sorted({n for n, i in calls if THIRD_TOOL.search(n or "") or THIRD_PATH.search(json.dumps(i, ensure_ascii=False))})


def diagnostics(spec, d, calls, every_call=()):
    diag = spec.get("diag") or {}
    files = parse_diff(d)
    added = [ln for f, dd in files.items() for ln in dd["added"]]
    return dict(handoff_reads=handoff_reads(calls), third_carrier=third_carrier(list(every_call) or calls),
                **{k: any(re.search(rx, ln) for ln in added) for k, rx in diag.items()})


def pilot_seq(spec, st):
    """Pilot: Z1 and the first C/H pair; after a pre-registered T2 revision only Z1 (the pair joins the main block)."""
    return [("Z", 1)] if st.get("revision") else pilot_order(spec["start"])


def main_sequence(specs, states, ns, skip_done=True):
    """Main block, interleaved by pairs: each repo's ABBA order (n per repo) cut into consecutive pairs, pairs
    alternating between repos, so a budget stop leaves the repos balanced. Returns [(name, arm, i)]."""
    pairs = []
    for sp in specs:
        nx = states[sp["name"]].get("next", {})
        seq = [(sp["name"], arm, i) for arm, i in order(ns[sp["name"]], sp["start"]) if not (skip_done and f"{arm}{i}" in nx)]
        pairs.append([seq[k:k + 2] for k in range(0, len(seq), 2)])
    return [x for j in range(max((len(p) for p in pairs), default=0)) for p in pairs if j < len(p) for x in p[j]]


def cmd_next(a):
    specs = [load_spec(os.path.abspath(x)) for x in a.spec]
    states = {sp["name"]: load_state(sp["name"]) for sp in specs}
    by_name = {sp["name"]: sp for sp in specs}
    for sp in specs:
        if "next_prompt" in sp and not states[sp["name"]].get("start"):
            raise Stop(f"{sp['name']}: round 3 needs startstate first")
    if a.followups_only:
        seq = [(sp["name"], r["arm"], r["i"]) for sp in specs for _, r in sorted(states[sp["name"]].get("next", {}).items())]
    elif a.pilot:
        seq = [(sp["name"], arm, i) for sp in specs for arm, i in pilot_seq(sp, states[sp["name"]])]
    elif all("next_prompt" in sp for sp in specs):
        missing = [n for n, st in states.items() if not (st.get("gate") or {}).get("n")]
        if missing:
            raise Stop(f"main block needs a passed gate for {missing} (python3 compact_ab.py gate ...)")
        seq = main_sequence(specs, states, {n: st["gate"]["n"] for n, st in states.items()}, skip_done=False)
    else:  # rounds 1-2
        seq = [(sp["name"], arm, i) for sp in specs for arm, i in order(a.n, sp["start"], a.arm)]
    fails = 0
    for name, arm, i in seq:
        sp, st = by_name[name], states[name]
        run_dir = os.path.join(DATA, "runs", name)
        os.makedirs(run_dir, exist_ok=True)
        if a.followups_only:
            if not a.no_followup:
                followup(sp, st, f"{arm}{i}", run_dir)
            continue
        rec = next_one(sp, st, arm, i, a, run_dir)
        if rec is None:
            continue
        if not a.no_followup:
            followup(sp, st, f"{arm}{i}", run_dir)
        fails = 0 if rec["ok"] else fails + 1
        if fails >= 2:
            raise Stop("two next-task runs in a row failed")


def next_one(spec, st, arm, i, a, run_dir):
    """One next-task run from the clean start state. Returns its record, or None when skipped."""
    name, repo, b = spec["name"], st["repo"], st["build"]
    tr, nx = st["transitions"], st.setdefault("next", {})
    base = start_base(st)
    round3 = "next_prompt" in spec
    tag = f"{arm}{i}"
    prev = []
    if tag in nx and nx[tag].get("ok") is not None and not a.redo:
        if not (getattr(a, "retry_invalid", False) and nx[tag]["ok"] is False):
            return None
        prev = nx[tag].get("failed_attempts", [])  # rerun an invalid run once more; keep its raw files and record
        for ext in (".jsonl", ".jsonl.err"):
            f = os.path.join(run_dir, f"{tag}-n{ext}")
            if os.path.exists(f):
                os.replace(f, os.path.join(run_dir, f"{tag}-n.fail{len(prev) + 1}{ext}"))
        prev = prev + [{k: nx[tag].get(k) for k in ("subtype", "delta", "first", "seconds", "problems", "sid")}]
    t = tr.get(tag)
    if arm != "Z" and (not t or not t.get("ok")):
        print(f"{name} {tag}: no valid transition, skipped", flush=True)
        return None
    mem = fresh(repo, base, b["project_dir"], f"{name}-{tag}-n")
    check_parents(st)
    git_cfg = os.path.join(repo, ".git", "config")
    cfg = open(git_cfg, "rb").read()
    place_carrier(st, tag, repo, run_dir)
    base_tree = tree_of_worktree(repo)
    def prepare():  # after a rate limit: back to exactly this start state
        fresh(repo, base, b["project_dir"], f"{name}-{tag}-n-retry")
        open(git_cfg, "wb").write(cfg)
        place_carrier(st, tag, repo, run_dir)
        if tree_of_worktree(repo) != base_tree:
            raise Stop(f"{tag}: start state differs on retry")
    args, parent = carrier_args(spec, st, arm, tag)
    p, du, out, dt = phase("next", repo, f"{tag}-n", args, parent, run_dir, dict(arm=arm, i=i), prepare=prepare)
    open(git_cfg, "wb").write(cfg)  # a session-planted fsmonitor/filter must not run in the grader's git
    killed = r2.kill_leftovers(repo)
    check_parents(st)
    d = diff_against(repo, base_tree, os.path.join(run_dir, f"{tag}.next.diff"))
    commits = git(repo, "log", "--format=%s", f"{base}..HEAD").stdout.split("\n")
    calls = tool_calls(out)
    g = grade(spec, repo, d, calls)
    rec = dict(arm=arm, i=i, seconds=dt, delta=du, turns=p["turns"], num_turns=(p["result"] or {}).get("num_turns"),
               first=p["first"], last_ctx=p["last_ctx"], ups=p["ups"], inject=p["inject"],
               inject_handoff=p["inject_handoff"], inject_concept=p["inject_concept"],
               subtype=(p["result"] or {}).get("subtype"), ok=ok_result(p), memory_moved_before=mem,
               killed=killed, outside=r2.outside_paths(out, repo), commits=[c for c in commits if c][:10],
               baton=p["baton"], omc=p["omc"], cli=p["cli"], model=p["model"], efforts=p["efforts"],
               stop_blocks=p["stop_blocks"], boundaries=len(p["boundary"]), files=sorted(parse_diff(d)), **g)
    if round3:
        rec["diag"] = diagnostics(spec, d, calls, all_calls(out))
        rec["flags"] = ["H run without a handoff injection"] if arm == "H" and not p["inject_handoff"] else []
        if st.get("revision"):
            rec["revised_prompt"] = True
    problems = []
    if arm == "C" and t.get("cut"):
        problems += cut_problems(st, tag, p, (st["t1"].get(tag) or {}).get("first"))
    elif arm == "C" and t.get("fork") and (p["result"] or {}).get("session_id") in (None, t["sid"]):
        problems.append("no new session id")
    if not delta_ok(du, p):  # the parent rule must still explain this run's usage
        problems.append(f"delta input below main-thread input {p['ctx_sum']}")
        cap_charge("next", f"{name}-{tag}-n", max((du or {}).get("cost", 0), 0))
    if p.get("rate_limited"):
        problems.append("rate limited")
    rec["problems"] = problems
    rec["ok"] = rec["ok"] and not problems
    rec["sid"] = (p["result"] or {}).get("session_id")
    rec["total"] = usage_of(p["result"])
    rec["failed_attempts"] = prev
    nx[tag] = rec
    save_state(name, st)
    fresh(repo, base, b["project_dir"], f"{name}-{tag}-n-after")
    print(f"{name} {tag} next ok={rec['ok']} correct={g['correct']} score={g['score']:.2f} cost=${(du or {}).get('cost', 0):.3f}"
          f" turns={rec['num_turns']}{' problems=' + str(problems) if problems else ''}{' flags=' + str(rec.get('flags')) if rec.get('flags') else ''}",
          flush=True)
    return rec


def followup(spec, st, tag, run_dir):
    """Exploratory (not in the verdict): a run that left the target file untouched gets one neutral reply in the
    same session, then is graded again on the cumulative diff. Same treatment for C and H (Z: none). A rate limit
    is not retried (the resumed session would hold the cut-off attempt): the follow-up is recorded invalid and the
    runner stops."""
    name, repo, b = spec["name"], st["repo"], st["build"]
    rec = st["next"][tag]
    if "followup" in rec or not rec.get("ok") or spec["target"] in rec["files"] or rec["arm"] == "Z":  # Z: descriptive pilot only
        return
    if not rec.get("sid"):  # rows graded before sid/total were stored
        p0 = parse(os.path.join(run_dir, f"{tag}-n.jsonl"))
        rec["sid"], rec["total"] = p0["result"]["session_id"], usage_of(p0["result"])
    base = start_base(st)
    fresh(repo, base, b["project_dir"], f"{name}-{tag}-f")
    place_carrier(st, tag, repo, run_dir)
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
    check_parents(st)
    d = diff_against(repo, base_tree, os.path.join(run_dir, f"{tag}.followup.diff"))
    g = grade(spec, repo, d, tool_calls(os.path.join(run_dir, f"{tag}-n.jsonl")) + tool_calls(out))
    problems = (["rate limited"] if p.get("rate_limited") else [])
    if not delta_ok(du, p):
        problems.append(f"delta input below main-thread input {p['ctx_sum']}")
        cap_charge("followup", f"{name}-{tag}-f", max((du or {}).get("cost", 0), 0))
    rec["followup"] = dict(delta=du, num_turns=(p["result"] or {}).get("num_turns"), ok=ok_result(p) and not problems,
                           problems=problems, seconds=dt, files=sorted(parse_diff(d)), outside=r2.outside_paths(out, repo), **g)
    save_state(name, st)
    fresh(repo, base, b["project_dir"], f"{name}-{tag}-f-after")
    print(f"{name} {tag} followup ok={rec['followup']['ok']} correct={g['correct']} score={g['score']:.2f} cost=${(du or {}).get('cost', 0):.3f}", flush=True)
    if p.get("rate_limited"):
        raise Stop(f"{tag}: rate limited during an exploratory follow-up (recorded invalid); rerun later")


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


def require_round3(states):
    """Commands that rewrite round-3/W records must never touch the round-1/2 folders (the default CVH_DATA)."""
    if not os.environ.get("CVH_DATA"):
        raise Stop("CVH_DATA is not set: refusing to modify the default (round-1) data folder")
    old = [n for n, st in states.items() if not st.get("start")]
    if old:
        raise Stop(f"{old}: no round-3 start state in {DATA}; refusing to modify round-1/2 records")


def cmd_regrade(a):
    """Recompute rule checks from the saved next-task diffs and tool calls (hidden-test results are stored).
    Round-3/W data only (review fix, 2026-11-25)."""
    spec = load_spec(a.spec)
    st = load_state(spec["name"])
    require_round3({spec["name"]: st})
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
    task = getattr(a, "task", None)
    round3 = task in ("T1", "T2")
    names = [a.repo] if a.repo else sorted(os.path.basename(p)[:-5] for p in os.listdir(os.path.join(DATA, "state")) if p.endswith(".json"))
    def rng(v):
        v = [x for x in v if x is not None]
        return f"{stt.median(v):.3g} [{min(v):.3g}-{max(v):.3g}]" if v else "-"
    for name in names:
        st = load_state(name)
        b = st.get("build", {})
        print(f"=== {name} ({task or 'rounds 1-2'}): build ctx={b.get('steps', [{}])[-1].get('last_ctx')} cost=${b.get('total', {}).get('cost', 0):.2f}")
        if round3 and (st.get("start") or {}).get("fact_tags"):
            print("    fact tags at the start state:", {f: x["tag"] for f, x in st["start"]["fact_tags"].items()})
        if task == "T1" and (st.get("start") or {}).get("B1_had_handoff"):
            print("    FLAG: B1 held a HANDOFF.md the build session wrote; every T1 C run here had it injected (re-analysis only)")
        rr = rows(st, task)
        for arm in ("C", "H", "Z"):
            sel = [(tag, r) for tag, r in sorted(rr.items()) if r["arm"] == arm and r["ok"]]
            if not sel:
                continue
            if arm == "Z":  # descriptive only: no carrier, no transition
                print(f" Z (no carrier, descriptive) n={len(sel)} correct={sum(r['correct'] for _, r in sel)}"
                      f" checks={[r['checks'] for _, r in sel]} next_raw={rng([r['delta']['cost'] for _, r in sel])}"
                      f" next_cold={rng([next_cold(r) for _, r in sel])} turns={rng([r['num_turns'] for _, r in sel])}")
                continue
            tt = lambda tag: trans_for(st, tag, task)
            tot = lambda k: [tt(tag)["delta"][k] + r["delta"][k] for tag, r in sel]
            costs = " ".join(f"cost_{ln}={rng([run_cost(st, tag, r, ln, task) for tag, r in sel])}"
                             for ln in (("morning", "evening", "raw") if round3 else ("warm", "raw")))
            print(f" {arm} n={len(sel)} correct={sum(r['correct'] for _, r in sel)} score={rng([r['score'] for _, r in sel])} {costs}")
            print(f"    next_raw={rng([r['delta']['cost'] for _, r in sel])} next_cold={rng([next_cold(r) for _, r in sel])}"
                  f" trans_warm={rng([warm_cost(tt(tag)) for tag, _ in sel])} trans_raw={rng([tt(tag)['delta']['cost'] for tag, _ in sel])}"
                  + (f" compact_morning={rng([compact_morning(tt(tag)) for tag, _ in sel])}" if arm == "C" else ""))
            print(f"    input(in+cc+cr)={rng([sum(tt(tag)['delta'][k] + r['delta'][k] for k in ('inputTokens', 'cacheCreationInputTokens', 'cacheReadInputTokens')) for tag, r in sel])}"
                  f" cache_read={rng(tot('cacheReadInputTokens'))} cache_create={rng(tot('cacheCreationInputTokens'))}"
                  f" uncached={rng(tot('inputTokens'))} output={rng(tot('outputTokens'))}")
            fu = [r for _, r in sel if r.get("followup", {}).get("ok")]
            bad = [r["i"] for _, r in sel if "followup" in r and not r["followup"].get("ok")]
            after = [r["followup"]["correct"] if r.get("followup", {}).get("ok") else r["correct"] for _, r in sel]
            if bad:
                print(f"    exploratory follow-ups invalid (interrupted): {arm}{bad}")
            print(f"    exploratory: stopped without touching the target={len(fu)}; correct after one neutral reply="
                  f"{sum(after)}/{len(sel)}; follow-up cost={rng([r['followup']['delta']['cost'] for r in fu])}")
            print(f"    next turns={rng([r['num_turns'] for _, r in sel])} first_ctx={rng([sum(r['first'].values()) for _, r in sel if r['first']])}"
                  f" checks=" + " ".join(f"{f}:{sum(r['checks'][f] for _, r in sel)}" for f in sel[0][1]["checks"]))
            if task == "T2":
                dg = [r.get("diag", {}) for _, r in sel]
                print("    diagnostics: " + " ".join(f"{k}={sum(bool(x.get(k)) for x in dg)}" for k in sorted({k for x in dg for k in x}))
                      + f" inject_handoff={sum(bool(r.get('inject_handoff')) for _, r in sel)}"
                      f" inject_concept={sum(bool(r.get('inject_concept')) for _, r in sel)}"
                      f" flagged={[r['i'] for _, r in sel if r.get('flags')]} efforts={sorted({e for _, r in sel for e in r.get('efforts') or []})}"
                      f" stop_blocks={sum(r.get('stop_blocks', 0) for _, r in sel)}"
                      f" boundaries={sum(r.get('boundaries', 0) for _, r in sel)} own_tests={sum(bool(r['tests'].get('own_tests_pass')) for _, r in sel)}")
        invalid = sorted(tag for tag, r in rr.items() if not r.get("ok"))
        if invalid:
            print(f"    invalid runs: {invalid}")
        if task == "T2" and (st.get("excluded") or (st.get("gate") or {}).get("carrier_insensitive")):
            print(f"    T2 revised once: excluded {sorted(st.get('excluded', {}))};"
                  f" carrier-insensitive={(st.get('gate') or {}).get('carrier_insensitive')}")
    states = {n: load_state(n) for n in names}
    if round3:
        for ln in ("morning", "evening", "raw"):
            print(f"{task} {ln:8s}:", verdict(states, ln, task))
    else:
        print("primary (warm-normalized transition cost):", verdict(states, "warm"))
        print("sensitivity (raw reported cost):          ", verdict(states, "raw"))
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


def next_cold(r):
    """Round 3: the day-2 session's cost with its first turn priced fully cold (its cache reads repriced as writes)."""
    return r["delta"]["cost"] + (r.get("first") or {}).get("cache_read_input_tokens", 0) * (PRICE["cw"] - PRICE["cr"])


def compact_morning(t):
    """Round 3: a compaction run the next morning, nothing warm (its cache reads repriced as uncached input)."""
    return t["delta"]["cost"] + t["delta"]["cacheReadInputTokens"] * (PRICE["in"] - PRICE["cr"])


LINES = ("warm", "raw", "morning", "evening")


def trans_for(st, tag, task=None):
    """The transition a row was run on: T1 rows keep round 1's reused compaction even after fresh ones replaced it."""
    if task == "T1" and tag in st.get("reused", {}):
        return st["reused"][tag]
    return st["transitions"][tag]


def run_cost(st, tag, r, line="warm", task=None):
    """Transition + next-task cost on one cost line. warm/raw: rounds 1-2 (raw next task). morning/evening: round 3
    (C = compact_morning or compact_evening, H = handoff_evening, both + next_cold). True/False = warm/raw (old API)."""
    line = {True: "warm", False: "raw"}.get(line, line)
    t = trans_for(st, tag, task)
    if line == "raw":
        return t["delta"]["cost"] + r["delta"]["cost"]
    if line == "warm":
        return warm_cost(t) + r["delta"]["cost"]
    trans = compact_morning(t) if t["arm"] == "C" and line == "morning" else warm_cost(t)
    return trans + next_cold(r)


def verdict(states, line="warm", task=None):
    """The pre-registered decision rule (docs/research/compact-vs-handoff.md; round 3: compact-vs-handoff-r3.md).
    Arms C and H only (Z is descriptive)."""
    import math, statistics as stt
    pairs, ratios, cheaper_h, k, n = {}, [], 0, {"C": 0, "H": 0}, {"C": 0, "H": 0}
    for name, st in states.items():
        cost = {"C": [], "H": []}
        for tag, r in rows(st, task).items():
            if not r.get("ok") or r.get("arm") not in cost or r.get("excluded"):
                continue
            arm = r["arm"]
            cost[arm].append(run_cost(st, tag, r, line, task))
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
    """Copy earlier states into CVH_DATA: --from <data folder>:<arm>, repeatable (round 3: r1:C and r2:H; W: r2:H).
    Build S comes from the first source. Each source gives its arm's transitions (the carriers) and its next rows,
    kept as `t1` (the planned-task records); `next` starts empty. Reused C transcripts are backed up with their
    sha256, H patches are copied, and S's and every C transcript's size/mtime/sha256 become the parent guard.
    The source folders are only read."""
    dst = state_path(a.name)
    if os.path.exists(dst):
        sys.exit(f"exists: {dst}")
    new, srcs = None, []
    run_dir = os.path.join(DATA, "runs", a.name)
    for item in a.sources:
        src, arm = item.rsplit(":", 1)
        src = os.path.expanduser(src)
        st = json.load(open(os.path.join(src, "state", f"{a.name}.json")))
        if new is None:
            new = dict(snapshot=st["snapshot"], repo=st["repo"], build=st["build"], transitions={}, t1={}, next={}, parents={})
        elif st["build"]["sid"] != new["build"]["sid"]:
            sys.exit(f"{src}: a different long session S")
        for tag, r in sorted(st.get("transitions", {}).items()):
            if r.get("arm") != arm:
                continue
            new["transitions"][tag] = dict(r, reused_from=src)
            n = st.get("next", {}).get(tag)
            if n:
                n = dict(n, reused_from=src)
                if not n.get("total"):  # round-1 rows graded before sid/total were stored
                    rp = parse(os.path.join(src, "runs", a.name, f"{tag}-n.jsonl"))
                    n["sid"], n["total"] = rp["result"]["session_id"], usage_of(rp["result"])
                new["t1"][tag] = n
            if arm == "H":
                os.makedirs(run_dir, exist_ok=True)
                dst_patch = os.path.join(run_dir, f"{tag}.patch")
                shutil.copy2(os.path.join(src, "runs", a.name, f"{tag}.patch"), dst_patch)
                new["transitions"][tag]["patch_sha256"] = sha256_file(dst_patch)
        srcs.append(dict(src=src, arm=arm))
    b = new["build"]
    check_S(b)
    new["parents"][b["sid"]] = sig(transcript(b, b["sid"]))
    for tag, r in new["transitions"].items():
        if r["arm"] == "C":
            f = transcript(b, r["sid"])
            new["parents"][r["sid"]] = sig(f)
            bk = os.path.join(DATA, "backup", a.name, os.path.basename(f))
            os.makedirs(os.path.dirname(bk), exist_ok=True)
            shutil.copy2(f, bk)
            if sha256_file(bk) != new["parents"][r["sid"]]["sha256"]:
                raise Stop(f"backup of {tag} differs from its transcript")
    new["seeded"] = dict(sources=srcs, at=time.strftime("%FT%T"))
    save_state(a.name, new)
    print(f"seeded {a.name}: transitions {sorted(new['transitions'])}, t1 rows {len(new['t1'])}, parents {len(new['parents'])}")


def materialize(repo, commit, patch):
    """The full HANDOFF.md an H patch leaves on top of `commit`, rebuilt in a temp folder outside the snapshot."""
    with open(patch, encoding="utf-8", errors="replace") as f:
        files = parse_diff(f.read())
    if set(files) != {"HANDOFF.md"}:
        raise Stop(f"{patch} touches {sorted(files)}, not only HANDOFF.md")
    with tempfile.TemporaryDirectory() as d:
        old = subprocess.run(["git", "-C", repo, "show", f"{commit}:HANDOFF.md"], capture_output=True)
        if old.returncode == 0:
            with open(os.path.join(d, "HANDOFF.md"), "wb") as f:
                f.write(old.stdout)
        subprocess.run(["git", "apply", "--binary", os.path.abspath(patch)], cwd=d, check=True, capture_output=True)
        with open(os.path.join(d, "HANDOFF.md"), "rb") as f:
            return f.read()


def drop_files(repo, commit, paths):
    """`commit`'s tree minus `paths`, as a new commit with the same parents, message, author and committer.
    Round 3's game-repo start state B1': B1 without the HANDOFF.md the build session wrote itself."""
    with tempfile.TemporaryDirectory() as d:
        env = {**os.environ, "GIT_INDEX_FILE": os.path.join(d, "index")}
        git(repo, "read-tree", commit, env=env, check=True)
        git(repo, "rm", "--cached", "-q", "--", *paths, env=env, check=True)
        tree = git(repo, "write-tree", env=env, check=True).stdout.strip()
    meta = git(repo, "log", "-1", "--format=%an%x00%ae%x00%aI%x00%cn%x00%ce%x00%cI%x00%P%x00%B", commit, check=True).stdout
    an, ae, ad, cn, ce, cd, parents, msg = meta.split("\0", 7)
    env = {**os.environ, "GIT_AUTHOR_NAME": an, "GIT_AUTHOR_EMAIL": ae, "GIT_AUTHOR_DATE": ad,
           "GIT_COMMITTER_NAME": cn, "GIT_COMMITTER_EMAIL": ce, "GIT_COMMITTER_DATE": cd}
    par = [x for p_ in parents.split() for x in ("-p", p_)]
    new = git(repo, "commit-tree", tree, *par, input=msg.rstrip("\n") + "\n", env=env, check=True).stdout.strip()
    git(repo, "update-ref", "refs/exp/start", new, check=True)  # keep it reachable
    return new


def fact_tags(repo, markers):
    """Which planted facts are also written in the start-state tree (marker regex in any tracked text file)."""
    files = [f for f in git(repo, "ls-files", "-z", check=True).stdout.split("\0") if f]
    out = {}
    for fact, rx in markers.items():
        hits = []
        for f in files:
            try:
                with open(os.path.join(repo, f), encoding="utf-8") as fh:
                    if re.search(rx, fh.read()):
                        hits.append(f)
            except (UnicodeDecodeError, OSError):
                continue
        out[fact] = dict(tag="also-in-repo" if hits else "conversation-only", files=hits[:10])
    return out


def markers_in(text, markers):
    return {f: bool(re.search(rx, text)) for f, rx in markers.items()}


def cmd_startstate(a):
    """Round 3 / W, $0: fix the start state (B1, or B1 minus `drop_at_start`), store every H handoff as a full file
    with its sha256 and markers, tag the facts conversation-only or also-in-repo, and compute each reused
    compaction's cut. Never moves an existing start state."""
    spec = load_spec(a.spec)
    name = spec["name"]
    st = load_state(name)
    repo, b = st["repo"], st["build"]
    validate(repo)
    if st.get("start"):
        sys.exit(f"{name}: start state already set: {st['start']['base']}")
    run_dir = os.path.join(DATA, "runs", name)
    os.makedirs(run_dir, exist_ok=True)
    fresh(repo, b["B1"], b["project_dir"], f"{name}-startstate")
    drop = spec.get("drop_at_start") or []
    base = drop_files(repo, b["B1"], drop) if drop else b["B1"]
    for tag, t in sorted(st["transitions"].items()):
        if t["arm"] == "H":
            if sha256_file(os.path.join(run_dir, f"{tag}.patch")) != t["patch_sha256"]:
                raise Stop(f"{tag}: patch changed since seed")
            data = materialize(repo, b["B1"], os.path.join(run_dir, f"{tag}.patch"))
            with open(os.path.join(run_dir, f"{tag}.handoff.md"), "wb") as f:
                f.write(data)
            t["handoff_sha256"] = hashlib.sha256(data).hexdigest()
            t["handoff_markers"] = markers_in(data.decode("utf-8", "replace"), spec["markers"])
            with open(os.path.join(run_dir, f"{tag}.patch"), encoding="utf-8", errors="replace") as f:
                t["added_markers"] = markers_in(added_text(f.read()), spec["markers"])
        elif t["arm"] == "C" and spec.get("task") == "T2" and not t.get("fork"):
            t["cut"] = cut_of(transcript(b, t["sid"]))
            if t["cut"]["prompt"] != NEXT_PROMPT or t["cut"]["discard_prompts"] != [NEXT_PROMPT]:
                raise Stop(f"{tag}: cut {t['cut']} does not isolate round 1's T1 turn")
    fresh(repo, base, b["project_dir"], f"{name}-startstate-base")
    had = git(repo, "cat-file", "-e", f"{b['B1']}:HANDOFF.md").returncode == 0
    st["start"] = dict(base=base, B1=b["B1"], dropped=drop, B1_had_handoff=had,
                       fact_tags=fact_tags(repo, spec["markers"]), made=time.strftime("%FT%T"))
    save_state(name, st)
    print(json.dumps({k: v for k, v in st["start"].items() if k != "fact_tags"}),
          {f: x["tag"] for f, x in st["start"]["fact_tags"].items()})


def cmd_probe_effort(a):
    """Round 3, about $0.2, before the first fresh compaction (review fix 2026-11-25): one new one-word session through
    the same call path, which must record perTurnEffort == CVH_EFFORT on its assistant entry. A compaction records
    no assistant entry, so its effort cannot be checked; this probe shows the pin takes effect before money is spent."""
    if not EFFORT:
        raise Stop("CVH_EFFORT is not set")
    done = os.path.join(DATA, "effort-probe.json")
    if os.path.exists(done) and json.load(open(done)).get("ok") and json.load(open(done)).get("required") == EFFORT:
        print(f"effort probe already passed: {open(done).read().strip()[:160]}")  # a resumed chain does not pay again
        return
    spec = load_spec(a.spec)
    st = load_state(spec["name"])
    require_round3({spec["name"]: st})
    repo, b = st["repo"], st["build"]
    run_dir = os.path.join(DATA, "runs", spec["name"])
    os.makedirs(run_dir, exist_ok=True)
    prepare = lambda: fresh(repo, start_base(st), b["project_dir"], f"{spec['name']}-probe-effort")
    prepare()
    p, du, out, dt = phase("probe", repo, "probe-effort", [PROBE_PROMPT, "--max-turns", str(TURNS["probe"])], usage_of(None),
                           run_dir, dict(arm="effort"), prepare=prepare)
    r2.kill_leftovers(repo)
    sid = (p["result"] or {}).get("session_id")
    pdir = project_dir(sid) if sid else None
    want = set(p["msg_ids"])
    per = [d.get("perTurnEffort") for d in (read_rows(os.path.join(pdir, sid + ".jsonl")) if pdir else [])
           if d.get("type") == "assistant" and (d.get("message") or {}).get("id") in want]
    prepare()
    res = dict(ok=bool(per) and all(x == EFFORT for x in per), per_turn_effort=per, required=EFFORT, model=p["model"],
               cost=round((du or {}).get("cost", 0), 4), sid=sid, at=time.strftime("%FT%T"))
    with open(os.path.join(DATA, "effort-probe.json"), "w") as f:
        json.dump(res, f, indent=1)
    print(json.dumps(res))
    if not res["ok"]:
        raise Stop(f"effort probe: perTurnEffort {per}, {EFFORT} required")


def cmd_probe_cut(a):
    """Round 3, about $0.5: one truncated fork of a reused compaction with a one-word prompt. Verifies the parent is
    unchanged, a new session id, no T1 entry in the fork, the first turn within CUT_TOL of round 1's T1 first turn,
    and fixes which parent the child's cumulative usage includes (the cost delta rule for every C run)."""
    spec = load_spec(a.spec)
    name = spec["name"]
    st = load_state(name)
    repo, b = st["repo"], st["build"]
    tag = a.tag
    t = st["transitions"][tag]
    run_dir = os.path.join(DATA, "runs", name)
    fresh(repo, start_base(st), b["project_dir"], f"{name}-probe-cut")
    check_parents(st)
    cut = t["cut"]
    if cut["discard_prompts"] != [NEXT_PROMPT]:
        raise Stop(f"{tag}: the truncation would discard prompts {cut['discard_prompts']}, not only T1's")
    args = [PROBE_PROMPT, "--resume", t["sid"], "--resume-session-at", cut["at"], "--fork-session", "--max-turns", str(TURNS["probe"])]
    # charged against the compaction total for now; corrected below once the parent rule is known
    p, du, out, dt = phase("probe", repo, f"probe-cut-{tag}", args, t["total"], run_dir, dict(arm="C", i=t["i"]),
                           prepare=lambda: fresh(repo, start_base(st), b["project_dir"], f"{name}-probe-cut"))
    r2.kill_leftovers(repo)
    problems = []
    try:
        check_parents(st)
    except Stop as e:
        problems.append(str(e))
    problems += cut_problems(st, tag, p, (st["t1"].get(tag) or {}).get("first")) if p["result"] else ["no result line"]
    child, rule, fits, parents = usage_of(p["result"]), None, {}, {}
    own = p["ctx_sum"]
    for k, parent in (("compaction", t["total"]), ("t1", (st["t1"].get(tag) or {}).get("total")), ("none", usage_of(None))):
        if not parent:
            continue
        dd = delta(child, parent)
        parents[k], fits[k] = dd, dd["inputTokens"] + dd["cacheCreationInputTokens"] + dd["cacheReadInputTokens"]
        if rule is None and own and abs(fits[k] - own) <= 0.05 * own:
            rule = k
    if rule is None:
        problems.append(f"child usage fits no parent (own main-thread input {own}, deltas {fits})")
    charged = max((du or {}).get("cost", CAPS["probe"]), 0.0) if p["result"] else CAPS["probe"]
    true = max(parents[rule]["cost"], 0.0) if rule else max(charged, CAPS["probe"])  # unknown: charge at least the cap
    if abs(true - charged) > 1e-6:
        ledger_add(dict(kind="probe", tag=f"probe-cut-{tag}-correction", charged=round(true - charged, 6), rule=rule))
    fresh(repo, start_base(st), b["project_dir"], f"{name}-probe-cut-after")
    st["probe_cut"] = dict(ok=not problems, problems=problems, rule=rule, own_input=own, deltas=fits, repo=name, tag=tag,
                           cost=round(true, 4), sid=(p["result"] or {}).get("session_id"), first=p["first"], seconds=dt,
                           reply=((p["result"] or {}).get("result") or "")[:80], subtype=(p["result"] or {}).get("subtype"),
                           at=time.strftime("%FT%T"))
    save_state(name, st)
    share_probe_cut(st["probe_cut"])
    print(json.dumps(st["probe_cut"], ensure_ascii=False), f"ledger total ${spent():.2f}")
    if problems:
        raise Stop("probe-cut failed: use the pre-registered fallback (transitions --arm C --fresh, n = 4)")


def share_probe_cut(pc):
    """One probe (pre-registered) fixes the CLI path and the parent rule for every repo; each C run still gets its
    own cut checks and delta check."""
    sd = os.path.join(DATA, "state")
    for f in sorted(os.listdir(sd)):
        name = f[:-5]
        st = load_state(name)
        if f.endswith(".json") and any(t.get("cut") for t in st.get("transitions", {}).values()) and st.get("probe_cut") != pc:
            st["probe_cut"] = pc
            save_state(name, st)


def installed():
    """The owner's install as files say it ($0, no session): plugin versions/paths and the CLI version."""
    d = json.load(open(os.path.expanduser("~/.claude/plugins/installed_plugins.json")))
    d = d.get("plugins", d)
    rec = lambda k: (d.get(k) or [{}])[0]
    out = subprocess.run([CLAUDE_BIN, "--version"], capture_output=True, text=True, stdin=subprocess.DEVNULL,
                         env=child_env()).stdout.split()
    return dict(baton=rec("baton@baton").get("version"), baton_path=rec("baton@baton").get("installPath"),
                omc=rec("oh-my-claudecode@omc").get("version"), cli=out[0] if out else None)


def selftest(spec, repo):
    """Grader self-test ($0): the reference implementation passes every hidden check, each mutant fails exactly its
    own check, and each rule mutant (a synthetic diff or command) fails exactly its own fact. Returns [(ok, line)]."""
    t, here = spec["selftest"], os.path.dirname(spec["_path"])
    hidden = os.path.join(here, spec["hidden"])
    ref = open(os.path.join(here, t["reference"]), encoding="utf-8").read()
    rule_facts = {r["fact"] for r in spec["rules"]}
    hidden_checks = [c for c in spec["checks"] if c not in rule_facts]
    def run(src):
        with tempfile.TemporaryDirectory() as r:
            for rel in t.get("copy", []):
                shutil.copy2(os.path.join(repo, rel), os.path.join(r, rel))
            for rel in t.get("link", []):
                os.symlink(os.path.join(repo, rel), os.path.join(r, rel))
            tgt = os.path.join(r, spec["target"])
            os.makedirs(os.path.dirname(tgt), exist_ok=True)
            with open(tgt, "w", encoding="utf-8") as f:
                f.write(src)
            h = subprocess.run([sys.executable, "-I", hidden, r], capture_output=True, text=True, timeout=600)
            return json.loads(h.stdout.strip().splitlines()[-1])
    got = run(ref)
    out = [(all(got.get(c) for c in hidden_checks), f"self-test: reference passes {hidden_checks}")]
    for check, edits in t["mutants"].items():
        src = ref
        for old, new in edits:
            if old not in src:
                out.append((False, f"self-test: mutant {check}: {old!r} not in the reference"))
                break
            src = src.replace(old, new)
        else:
            failed = [c for c in hidden_checks if not run(src).get(c)]
            out.append((failed == [check], f"self-test: mutant {check} fails exactly {failed}"))
    for m in t["rule_mutants"]:
        res = rules_check(spec["rules"], m.get("diff", ""), [tuple(c) for c in m.get("calls", [])])
        failed = sorted(f for f, v in res.items() if not v)
        out.append((failed == [m["fact"]], f"self-test: rule mutant {m['fact']} ({m['what']}) fails exactly {failed}"))
    return out


def cmd_preflight(a):
    """$0, no claude session: the checks the pre-registration lists before the first paid call. Exit 3 on any failure."""
    fails = []
    def ok(cond, what):
        print(f"  {'PASS' if cond else 'FAIL'} {what}", flush=True)
        if not cond:
            fails.append(what)
    iv = installed()
    for key, want in (("baton", BATON_INSTALLED), ("omc", OMC_REQUIRED), ("cli", CLI_REQUIRED)):
        ok(want is not None and iv[key] == want, f"installed {key} {iv[key]} == required {want}")
    ok("/versions/" not in CLAUDE_BIN or os.path.basename(CLAUDE_BIN) == CLI_REQUIRED, f"pinned binary {CLAUDE_BIN}")
    ok(bool(MODEL_REQUIRED) and bool(EFFORT), f"model pinned {MODEL_REQUIRED}, effort pinned {EFFORT}")
    leaked = [k for k in HOST_ENV_DROP if k in child_env()]
    ok(not leaked and child_env().get("DISABLE_AUTOUPDATER") == "1",
       f"child env: none of the dropped variables, autoupdater off; still passed: {env_names(child_env())}")
    ok(spent() + MARGIN < CAP_USD, f"ledger ${spent():.2f} of cap ${CAP_USD}")
    for path in a.spec:
        spec = load_spec(os.path.abspath(path))
        name = spec["name"]
        st = load_state(name)
        repo, b = st["repo"], st["build"]
        print(f"== {name} ({spec.get('task')})")
        try:
            validate(repo)
            ok(True, "snapshot has no remote")
        except ValueError as e:
            ok(False, str(e))
        mem = os.path.join(b["project_dir"], "memory")
        ok(not (os.path.isdir(mem) and os.listdir(mem)), "auto-memory folder is empty")
        try:
            check_parents(st)
            ok(bool(st.get("parents")), f"{len(st.get('parents') or {})} parent transcripts unchanged (size, mtime, sha256)")
        except Stop as e:
            ok(False, str(e))
        start = st.get("start") or {}
        ok(bool(start), "start state set")
        if start:
            ok(git(repo, "cat-file", "-e", f"{start['base']}^{{commit}}").returncode == 0, f"start base {start['base'][:10]} exists")
            for f in start["dropped"]:
                ok(git(repo, "cat-file", "-e", f"{start['base']}:{f}").returncode != 0, f"{f} absent at the start base")
            ok(bool(start.get("fact_tags")), "fact tags stored: " + str({f: x["tag"] for f, x in start.get("fact_tags", {}).items()}))
        run_dir = os.path.join(DATA, "runs", name)
        for tag, t in sorted(st["transitions"].items()):
            if t["arm"] == "H":
                pf, hf = os.path.join(run_dir, f"{tag}.patch"), os.path.join(run_dir, f"{tag}.handoff.md")
                ok(os.path.exists(pf) and sha256_file(pf) == t.get("patch_sha256"), f"{tag} patch sha256")
                ok(os.path.exists(hf) and sha256_file(hf) == t.get("handoff_sha256"), f"{tag} handoff sha256")
            elif spec.get("task") == "T2" and getattr(a, "before_fresh", False) and spec.get("drop_at_start") and not t.get("fork"):
                print(f"  PENDING {tag} carrier: reused compaction, to be replaced by a fresh one on the start state (Deviation 4)")
            elif spec.get("task") == "T2":
                ok(bool(t.get("fork")) or (bool(t.get("cut")) and t["cut"].get("discard_prompts") == [NEXT_PROMPT]),
                   f"{tag} carrier: " + (f"cut {t['cut']['at'][:8]}, discards {t['cut'].get('discard_entries')} entries with prompts"
                                         f" {t['cut'].get('discard_prompts')}" if t.get("cut") else "fresh compaction on the start state"))
                f = transcript(b, t["sid"]) if t.get("sid") else ""
                if not os.path.exists(f):
                    ok(False, f"{tag} carrier transcript missing: {f}")
                    continue
                hits = dropped_attachments(f, start.get("dropped") or spec.get("drop_at_start") or [], until=(t.get("cut") or {}).get("at"))
                ok(not hits, f"{tag} carrier re-attaches no dropped file between boundary and {'cut' if t.get('cut') else 'end'} {hits or ''}")
        if spec.get("task") == "T2":
            sys.path.insert(0, os.path.join(iv["baton_path"], "lib"))  # the installed hook's own trigger rule
            import rules
            hits = rules.trigger_words(repo, spec["next_prompt"])
            ok(bool(hits), f"T2 prompt matches the installed baton's trigger words {hits}")
            if st.get("revision"):
                ok(bool(rules.trigger_words(repo, spec["revised_prompt"])), "revised T2 prompt matches the trigger words")
            for good, line in selftest(spec, repo):
                ok(good, line)
            if start and spec.get("start_expect"):  # the hidden checks on the untouched start state
                fresh(repo, start["base"], b["project_dir"], f"{name}-preflight")
                got = json.loads(subprocess.run([sys.executable, "-I", os.path.join(os.path.dirname(spec["_path"]), spec["hidden"]), repo],
                                                capture_output=True, text=True, timeout=600).stdout.strip().splitlines()[-1])
                fresh(repo, start["base"], b["project_dir"], f"{name}-preflight-after")
                ok({k: got.get(k) for k in spec["start_expect"]} == spec["start_expect"],
                   f"hidden checks on the start state {({k: got.get(k) for k in spec['start_expect']})}")
            pc = st.get("probe_cut") or {}
            fallback = any(t.get("fork") for t in st["transitions"].values())
            ok(pc.get("ok") or fallback, f"probe-cut {'passed (rule ' + str(pc.get('rule')) + ')' if pc.get('ok') else 'not passed'}"
               f"{' / fallback compactions' if fallback else ''}")
        if spec.get("task") == "W":
            dst, man_path, probe_path = w_paths()
            probe = json.load(open(probe_path)) if os.path.exists(probe_path) else None
            bad = staged_problem(dst, probe) if os.path.exists(dst) else "nothing staged"
            ok(not bad, f"staged build: {bad or 'version and skills as probed'}")
            ok(bool(w_required(st)), f"W required facts (added lines of every round-2 patch): {w_required(st)}")
    if fails:
        raise Stop(f"preflight: {len(fails)} check(s) failed")
    print("preflight: all checks passed")


def revise(spec, st):
    """The pre-registered one-time T2 revision of a repo whose Z1 was correct: its pilot rows move to `excluded`
    (exploratory, never in the verdict; raw files renamed .pre-revision), and its runs use spec["revised_prompt"]."""
    import glob
    name = spec["name"]
    if st.get("revision"):
        raise Stop(f"{name}: T2 was already revised once (pre-registered: at most one revision)")
    if not spec.get("revised_prompt"):
        raise Stop(f"{name}: the spec has no pre-registered revised_prompt")
    run_dir = os.path.join(DATA, "runs", name)
    exc = st.setdefault("excluded", {})
    for tag in ("Z1", "C1", "H1"):
        if tag in st.get("next", {}):
            exc[tag] = dict(st["next"].pop(tag), excluded="pilot run before the pre-registered T2 revision")
            for pat in (f"{tag}-n*", f"{tag}-f*", f"{tag}.next.diff", f"{tag}.followup.diff"):
                for f in glob.glob(os.path.join(run_dir, pat)):
                    os.replace(f, f + ".pre-revision")
    st["revision"] = dict(at=time.strftime("%FT%T"), prompt_sha256=hashlib.sha256(spec["revised_prompt"].encode()).hexdigest())
    save_state(name, st)
    print(f"{name}: T2 revised; excluded {sorted(exc)}; rerun the pilot (Z1 only), then the gate")


def cmd_gate(a):
    """Round 3 pilot gate ($0) over all repos. Z1 correct -> revise that repo's T2 once (`gate --revised <repo>`,
    then the pilot reruns Z1 only); if Z1 is correct again after the revision, the repo is flagged carrier-insensitive
    and the run continues. C1 and H1 both failing the core check -> task or grader defect (stop). Then n per repo =
    the largest of 5, 4, 3 (never more than the repo's valid carriers per arm: 4 for fresh compactions) for which the
    interleaved main block, priced at the measured median next-task cost per arm and repo + 10%, passes the runtime
    guard before every call."""
    import statistics as stt
    specs = [load_spec(os.path.abspath(p)) for p in a.spec]
    states = {sp["name"]: load_state(sp["name"]) for sp in specs}
    require_round3(states)
    if getattr(a, "revised", None):
        sp = next((x for x in specs if x["name"] == a.revised), None)
        if not sp:
            raise Stop(f"--revised {a.revised}: not among the specs")
        return revise(sp, states[a.revised])
    if all(st.get("gate") for st in states.values()):  # decided once; a resumed chain keeps the same n
        print("gate already passed:", {n: st["gate"]["n"] for n, st in states.items()})
        return
    stops, insensitive = [], {}
    for sp in specs:
        name, st = sp["name"], states[sp["name"]]
        nx = st.get("next", {})
        missing = [f"{x}{i}" for x, i in pilot_seq(sp, st) if not nx.get(f"{x}{i}", {}).get("ok")]
        if missing:
            stops.append(f"{name}: pilot rows missing or invalid: {missing} (rerun them with next --pilot --retry-invalid)")
            continue
        if nx["Z1"]["correct"]:
            if st.get("revision"):
                insensitive[name] = True
            else:
                stops.append(f"{name}: Z1 correct without any carrier -> {os.path.join(DATA, 'run.sh')} revise {name} "
                             f"(applies the pre-registered revision, reruns Z1 only, then continues the chain)")
        if not st.get("revision"):
            core = sp["hard"][0]
            if not nx["C1"]["checks"][core] and not nx["H1"]["checks"][core]:
                stops.append(f"{name}: C1 and H1 both fail {core} -> task or grader defect (fix once, log it)")
    for x in stops:
        print(x, flush=True)
    if stops:
        raise Stop("gate did not pass")
    caps = {sp["name"]: min([5] + [sum(1 for t in states[sp["name"]]["transitions"].values() if t["arm"] == arm and t.get("ok"))
                                   for arm in ("C", "H")]) for sp in specs}
    def median_cost(st, arm):
        rows_ = [r for r in list(st["next"].values()) + list(st.get("excluded", {}).values()) if r["arm"] == arm and r.get("ok")]
        rows_ = rows_ or [r for r in st["t1"].values() if r["arm"] == arm and r.get("ok")]  # no pilot pair yet (revised repo)
        return stt.median(r["delta"]["cost"] for r in rows_) * 1.1
    med = {(n, arm): median_cost(st, arm) for n, st in states.items() for arm in ("C", "H")}
    def projection(n):
        """Simulate the interleaved main block with the runtime guard: (fits, projected spend)."""
        ns = {name: min(n, c) for name, c in caps.items()}
        total, need = spent(), 0.0
        for name, arm, i in main_sequence(specs, states, ns):
            if total + CAPS["next"] + MARGIN > CAP_USD:
                return False, need
            total, need = total + med[(name, arm)], need + med[(name, arm)]
        return True, need
    n = next((k for k in range(5, 2, -1) if min(min(k, c) for c in caps.values()) >= 3 and projection(k)[0]), None)
    if n is None:
        raise Stop(f"gate: spent ${spent():.2f}; even n=3 would be refused by the ${CAP_USD} guard -> inconclusive")
    need = projection(n)[1]
    for name, st in states.items():
        st["gate"] = dict(n=min(n, caps[name]), carriers=caps[name], projection=round(need, 2), spent=round(spent(), 2),
                          carrier_insensitive=insensitive.get(name, False), at=time.strftime("%FT%T"))
        save_state(name, st)
    print(f"gate passed: n per repo {({k: min(n, c) for k, c in caps.items()})}; spent ${spent():.2f},"
          f" projected main block ${need:.2f}, cap ${CAP_USD}; carrier-insensitive {sorted(insensitive) or 'none'}")


# ---------------- W: write-cost re-measure ----------------
def staged_tree(path):
    """sha256 over (relative path, file sha256) of a staged plugin folder; __pycache__ is ignored (hooks import lib)."""
    h = hashlib.sha256()
    for root, dirs, files in os.walk(path):
        dirs[:] = sorted(x for x in dirs if x != "__pycache__")
        for f in sorted(files):
            full = os.path.join(root, f)
            h.update(f"{os.path.relpath(full, path)}\0{sha256_file(full)}\n".encode())
    return h.hexdigest()


def w_paths():
    return os.path.join(DATA, "plugin", "baton"), os.path.join(DATA, "plugin", "manifest.json"), os.path.join(DATA, "wprobe.json")


def cmd_wstage(a):
    """W, $0: copy the plugin build at --src (the files git knows there: tracked plus untracked-not-ignored, minus
    deleted; the list tools/stage-plugin.sh uses) into DATA/plugin/baton, and write its manifest and the per-run
    settings file that disables the installed baton@baton. The source tree is only read (git --no-optional-locks).
    Refused once any W run exists, so all W runs use one build."""
    sd = os.path.join(DATA, "state")
    if not a.check and os.path.isdir(sd) and any(json.load(open(os.path.join(sd, f))).get("write") for f in os.listdir(sd) if f.endswith(".json")):
        sys.exit("W runs exist: the staged build is frozen")
    src = os.path.realpath(os.path.expanduser(a.src))
    g = lambda *x: subprocess.run(["git", "--no-optional-locks", "-C", src, *x], capture_output=True, check=True).stdout
    gone = {x for x in g("ls-files", "-d", "-z").split(b"\0") if x}
    keep = sorted(x.decode() for x in g("ls-files", "-co", "--exclude-standard", "-z").split(b"\0") if x and x not in gone)
    if any(x.endswith("/") for x in keep):
        sys.exit("untracked folder (nested repo?) in the source")
    dst, man_path, _ = w_paths()
    if a.check and os.path.isdir(sd) and any(json.load(open(os.path.join(sd, f))).get("write") for f in os.listdir(sd) if f.endswith(".json")):
        print("W runs exist: the frozen staged build is used (every run re-checks its tree hash)")
        return
    if a.check:  # $0: is the staged build still what the source tree holds now?
        with tempfile.TemporaryDirectory() as d:
            for rel in keep:
                os.makedirs(os.path.dirname(os.path.join(d, rel)), exist_ok=True)
                shutil.copy2(os.path.join(src, rel), os.path.join(d, rel))
            same = staged_tree(d) == json.load(open(man_path))["tree"]
        print(f"staged build {'matches' if same else 'DIFFERS FROM'} {src} now")
        if not same:
            raise Stop("the source tree changed since staging: restage (wstage) before W, or keep the staged build on purpose")
        return
    shutil.rmtree(dst, ignore_errors=True)
    for rel in keep:
        os.makedirs(os.path.dirname(os.path.join(dst, rel)), exist_ok=True)
        shutil.copy2(os.path.join(src, rel), os.path.join(dst, rel))
    man = dict(path=dst, src=src, head=g("rev-parse", "HEAD").decode().strip(),
               uncommitted=sorted(ln[3:] for ln in g("status", "--porcelain").decode().splitlines()),
               version=json.load(open(os.path.join(dst, ".claude-plugin", "plugin.json")))["version"],
               skill_sha256=sha256_file(os.path.join(dst, "skills", "baton", "SKILL.md")),
               hooks_sha256=sha256_file(os.path.join(dst, "hooks", "hooks.json")), files=len(keep),
               tree=staged_tree(dst), staged=time.strftime("%FT%T"))
    with open(man_path, "w") as f:
        json.dump(man, f, indent=1)
    with open(os.path.join(DATA, "settings-w.json"), "w") as f:
        json.dump({"enabledPlugins": {"baton@baton": False}}, f)
    print(json.dumps({k: v for k, v in man.items() if k != "uncommitted"}), f"uncommitted files: {len(man['uncommitted'])}")


def owner_files():
    """Hashes that prove a probe left the owner's install alone: settings, plugin records, installed baton files."""
    iv = installed()
    return dict(settings=sha256_file(os.path.expanduser("~/.claude/settings.json")),
                installed_plugins=sha256_file(os.path.expanduser("~/.claude/plugins/installed_plugins.json")),
                installed_baton=staged_tree(iv["baton_path"]), baton_version=iv["baton"])


LEAK = re.compile(r"(~|\$\{?HOME\}?|" + re.escape(os.path.expanduser("~")) + r")/\.claude/plugins/cache/baton\b")


def staged_skills(dst):
    """Skill names the staged build declares (plugin.json `skills` folders), as Claude Code lists them."""
    m = json.load(open(os.path.join(dst, ".claude-plugin", "plugin.json")))
    return sorted("baton:" + os.path.basename(x.rstrip("/")) for x in m.get("skills") or [])


def staged_problem(dst, probe=None):
    """$0 before W's first paid call: the staged version string must be the required baton version, and (after a
    probe) the same version and skills as the probed build."""
    ver = json.load(open(os.path.join(dst, ".claude-plugin", "plugin.json"))).get("version")
    if BATON_REQUIRED and ver != BATON_REQUIRED:
        return f"staged build version {ver}, CVH_BATON={BATON_REQUIRED}"
    if probe:
        st_ = probe["runs"]["staged"]
        pv = next((x["version"] for x in st_["plugins"] if x["name"] == "baton"), None)
        if ver != pv or staged_skills(dst) != sorted(st_["skills"]):
            return f"staged build {ver} {staged_skills(dst)} differs from the probed {pv} {sorted(st_['skills'])}: rerun wprobe"
    return None


def added_text(diff_text, path="HANDOFF.md"):
    return "\n".join((parse_diff(diff_text).get(path) or {}).get("added", []))


def drift_reset(repo):
    """W2 (amendment 5): from 1.0.2, hooks/drift-notice.sh shows the same concept-map notice at most once a day, keeping
    what it showed in ${XDG_CACHE_HOME:-~/.cache}/baton/drift/shown-<cksum of "lang|map path">, outside the snapshot.
    Every W run carried that notice, so before each run only those files of this repo's maps (both languages) are
    removed; the notice's other cache files stay. Returns the removed paths."""
    root = git(repo, "rev-parse", "--show-toplevel").stdout.strip() or repo  # the hook's ROOT and find, exactly
    maps = subprocess.run(["find", root, "-maxdepth", "2", "-name", "CONCEPTS.md", "-not", "-path", "*/node_modules/*"],
                          capture_output=True, text=True).stdout.splitlines()
    d = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "baton", "drift")
    out = []
    for m in filter(None, maps):
        for lang in ("ko", "en"):
            ck = subprocess.run(["cksum"], input=f"{lang}|{m}".encode(), capture_output=True, check=True).stdout.decode()
            f = os.path.join(d, "shown-" + ck.strip().replace(" ", ""))
            if os.path.isfile(f):
                os.remove(f)
                out.append(f)
    return out


GIT_STATUS_HEAD = re.compile(r"(?m)^## (?:No commits yet on \S+|HEAD \(no branch\)|\S+(?:\.\.\.\S+)?(?: \[[^\]\n]+\])?)$")
GIT_ONELINE = re.compile(r"(?m)^[0-9a-f]{7,40} \S")
GIT_COMMIT = re.compile(r"\bgit\b[^|;&\n]*?\bcommit\b")


def write_metrics(path):
    """W2 descriptive metrics (amendments 2 and 7) from a write's raw stream, main thread only:
    state_filled: the Skill tool result (with the skill text loaded after it) holds `git status --short --branch` and
      `git log --oneline` output and no "[run this first" placeholder;
    write_commit_one_message: one assistant message holds both a Write/Edit of HANDOFF.md and a `git commit` Bash call;
    commits: Bash calls that run `git commit`; posttool_blocks: PostToolUse hook responses with "decision": "block"."""
    out = dict(state_filled=False, write_commit_one_message=False, commits=0, posttool_blocks=0)
    msgs, skill_ids, skill_text, capture = {}, set(), [], False
    for d in read_rows(path):
        t = d.get("type")
        if t == "system" and d.get("subtype") == "hook_response" and d.get("hook_event") == "PostToolUse":
            o = (d.get("stdout") or "") + (d.get("output") or "")
            out["posttool_blocks"] += '"decision": "block"' in o or '"decision":"block"' in o
        if d.get("parent_tool_use_id") or t not in ("assistant", "user"):
            continue
        content = (d.get("message") or {}).get("content")
        blocks = content if isinstance(content, list) else [{"type": "text", "text": content or ""}]
        if t == "assistant":
            capture = False
            mid = (d.get("message") or {}).get("id") or d.get("uuid")
            for x in blocks:
                if isinstance(x, dict) and x.get("type") == "tool_use":
                    msgs.setdefault(mid, []).append((x.get("name"), x.get("input") or {}))
                    if x.get("name") == "Skill":
                        skill_ids.add(x.get("id"))
            continue
        for x in blocks:
            if not isinstance(x, dict):
                continue
            if x.get("type") == "tool_result" and x.get("tool_use_id") in skill_ids:
                capture = True
                c = x.get("content")
                skill_text.append(c if isinstance(c, str) else json.dumps(c, ensure_ascii=False))
            elif x.get("type") == "text" and capture:
                skill_text.append(x.get("text") or "")
    text = "\n".join(skill_text)
    out["state_filled"] = bool(GIT_STATUS_HEAD.search(text) and GIT_ONELINE.search(text)) and "[run this first" not in text
    commit = lambda n, i: n == "Bash" and bool(GIT_COMMIT.search(i.get("command") or ""))
    ho = lambda n, i: n in ("Write", "Edit", "MultiEdit") and re.search(r"(^|/)HANDOFF\.md$", str(i.get("file_path") or ""))
    out["commits"] = sum(commit(n, i) for calls in msgs.values() for n, i in calls)
    out["write_commit_one_message"] = any(any(ho(n, i) for n, i in calls) and any(commit(n, i) for n, i in calls)
                                          for calls in msgs.values())
    return out


def init_line(path):
    return next((d for d in read_rows(path) if d.get("type") == "system" and d.get("subtype") == "init"), None)


def cmd_wenv(a):
    """W2, $0 (amendment 4; the lead runs it once after wprobe and before W1): the environment around baton, the
    staged probe session's init line against the reference W's W1 init line in the same repo: non-baton plugin names
    and versions, MCP server names, tool count, skill count. Prints the differences; reads only."""
    if not WREF:
        raise Stop("wenv needs CVH_WREF (the reference W folder)")
    name = load_spec(a.spec)["name"]
    probe_path = w_paths()[2]
    probe = json.load(open(probe_path)) if os.path.exists(probe_path) else {}
    mine = ((probe.get("runs") or {}).get("staged") or {}).get("stream") or os.path.join(DATA, "runs", name, "wprobe-staged.jsonl")
    ref = os.path.join(os.path.expanduser(WREF), "runs", name, "W1-t.jsonl")
    lines = {}
    for label, f in (("W W1", ref), ("W2 probe", mine)):
        d = init_line(f) if os.path.exists(f) else None
        if not d:
            raise Stop(f"no init line in {f}")
        lines[label] = {"plugins (not baton)": sorted(f"{x.get('name')} {x.get('version')}" for x in d.get("plugins") or [] if x.get("name") != "baton"),
                        "MCP servers": sorted(x.get("name") for x in d.get("mcp_servers") or []),
                        "tools": len(d.get("tools") or []), "skills": len(d.get("skills") or []),
                        "skills (not baton)": len([x for x in d.get("skills") or [] if not x.startswith("baton:")])}
    a_, b_ = lines["W W1"], lines["W2 probe"]
    diffs = [k for k in a_ if a_[k] != b_[k]]
    for k in a_:
        if a_[k] == b_[k]:
            print(f"  same {k}: {a_[k] if not isinstance(a_[k], list) else len(a_[k])}")
        elif isinstance(a_[k], list):
            print(f"  DIFFERS {k}: only in W W1 {sorted(set(a_[k]) - set(b_[k]))}, only in the W2 probe {sorted(set(b_[k]) - set(a_[k]))}")
        else:
            print(f"  DIFFERS {k}: W W1 {a_[k]}, W2 probe {b_[k]}")
    print(f"wenv: {len(diffs)} difference(s) ({ref} vs {mine})")


def cmd_wprobe(a):
    """W, about $0.6: two new one-word sessions in the snapshot at B1 — the installed setup (control) and the staged
    build (--plugin-dir + --settings disabling baton@baton). Passes when the staged session loads exactly one baton,
    from the staged folder, with the same plugin names, baton skills and hook counts per event as the control, and
    the owner's settings, plugin records and installed baton files are byte-identical before and after."""
    spec = load_spec(a.spec)
    st = load_state(spec["name"])
    repo, b = st["repo"], st["build"]
    dst, man_path, probe_path = w_paths()
    man = json.load(open(man_path))
    bad = staged_problem(dst)
    if bad:
        raise Stop(bad)
    run_dir = os.path.join(DATA, "runs", spec["name"])
    os.makedirs(run_dir, exist_ok=True)
    before = owner_files()
    res = {}
    for kind, pdir in (("control", None), ("staged", dst)):
        prepare = lambda: fresh(repo, b["B1"], b["project_dir"], f"wprobe-{kind}")
        prepare()
        p, du, out, dt = phase("probe", repo, f"wprobe-{kind}", [PROBE_PROMPT, "--max-turns", str(TURNS["probe"])],
                               usage_of(None), run_dir, dict(arm=kind), plugin_dir=pdir, prepare=prepare)
        r2.kill_leftovers(repo)
        res[kind] = dict(plugins=p["plugins"], skills=p["skills"], hooks=p["hooks"], baton=p["baton"], omc=p["omc"],
                         cli=p["cli"], subtype=(p["result"] or {}).get("subtype"), cost=(du or {}).get("cost"), seconds=dt,
                         stream=out)
    fresh(repo, b["B1"], b["project_dir"], "wprobe-after")
    after = owner_files()
    c, s_ = res["control"], res["staged"]
    batons = [x for x in s_["plugins"] if x["name"] == "baton"]
    checks = {
        "staged: one baton, from the staged folder": plugin_problem(dict(plugins=s_["plugins"]), dst) is None,
        "control: the installed baton@baton": any(x["source"] == "baton@baton" for x in c["plugins"]),
        "same plugin names": sorted(x["name"] for x in c["plugins"]) == sorted(x["name"] for x in s_["plugins"]),
        "same baton skills": c["skills"] == s_["skills"] and len(s_["skills"]) > 0,
        "same hook counts per event": c["hooks"] == s_["hooks"],
        "staged version = manifest": bool(batons) and batons[0]["version"] == man["version"],
        "owner files unchanged": before == after,
    }
    out = dict(ok=all(checks.values()), checks=checks, before=before, after=after, manifest_tree=man["tree"],
               hooks_sha256=sha256_file(os.path.join(dst, "hooks", "hooks.json")), runs=res, at=time.strftime("%FT%T"))
    with open(probe_path, "w") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    for k, v in checks.items():
        print(f"  {'PASS' if v else 'FAIL'} {k}")
    print(f"  staged baton: {batons}  hooks: {s_['hooks']}  ledger ${spent():.2f}")
    if not out["ok"]:
        raise Stop("wprobe failed: no safe way to load the staged build was proven")


def cmd_write(a):
    """W: rerun only round 2's handoff-writing transition (same S, switch point B1, prompt and turn cap) with the
    staged build, n per repo, alternating repos (W1 of each, then W2 of each, ...) so a budget stop leaves the repos
    balanced. Every run must load the staged build (init line), leave S unchanged, keep the staged folder unchanged,
    never use the installed baton's files in a tool call, and leave a HANDOFF.md."""
    dst, man_path, probe_path = w_paths()
    probe = json.load(open(probe_path)) if os.path.exists(probe_path) else {}
    if not probe.get("ok"):
        raise Stop("wprobe has not passed")
    man = json.load(open(man_path))
    if probe.get("manifest_tree") != man["tree"] and probe.get("hooks_sha256") != man.get("hooks_sha256"):
        raise Stop("the staged build's hooks.json differs from the probed one: rerun wprobe before W")
    bad = staged_problem(dst, probe)
    if bad:
        raise Stop(bad)
    specs = [load_spec(os.path.abspath(p)) for p in a.spec]
    states = {sp["name"]: load_state(sp["name"]) for sp in specs}
    for name, st in states.items():
        validate(st["repo"])
        frozen = st.setdefault("stage", man)
        if frozen["tree"] != man["tree"]:
            raise Stop(f"{name}: the staged build changed after the first W run")
    fails = 0
    for i in range(1, a.n + 1):
        for sp in specs:
            name = sp["name"]
            st = states[name]
            rec = write_one(sp, st, i, dst)
            if rec is None:
                continue
            fails = 0 if rec["valid"] else fails + 1
            if fails >= 2:
                raise Stop("two W runs in a row were invalid (harness failures)")


def write_one(spec, st, i, dst):
    """One W run. Valid unless a harness failure (no result line, an error result other than the turn or budget
    cap, a broken cost delta, the wrong build or a tool call into the installed build); only invalid runs are rerun.
    A valid run that hit the turn or budget cap or wrote no HANDOFF.md is a valid failure: its cost counts and its
    markers count as missing (no survivorship)."""
    name, repo, b = spec["name"], st["repo"], st["build"]
    run_dir = os.path.join(DATA, "runs", name)
    os.makedirs(run_dir, exist_ok=True)
    w = st.setdefault("write", {})
    tag = f"W{i}"
    if w.get(tag, {}).get("valid"):
        return None
    if staged_tree(dst) != st["stage"]["tree"]:
        raise Stop("the staged build changed on disk")
    prev = w.get(tag, {}).get("failed_attempts", [])
    if tag in w:  # keep the invalid attempt's raw files and record
        for ext in (".jsonl", ".jsonl.err"):
            f = os.path.join(run_dir, f"{tag}-t{ext}")
            if os.path.exists(f):
                os.replace(f, os.path.join(run_dir, f"{tag}-t.fail{len(prev) + 1}{ext}"))
        prev = prev + [{k: w[tag].get(k) for k in ("subtype", "delta", "first", "seconds", "leak", "problems")}]
    reset = []  # W2 (amendment 5): the drift notice's "shown" state, removed before each attempt so the input matches W's

    def prepare():
        m = fresh(repo, b["B1"], b["project_dir"], f"{name}-{tag}")
        reset.extend(drift_reset(repo))
        return m
    mem = prepare()
    check_S(b)
    check_parents(st)
    args = [HANDOFF_PROMPT, "--resume", b["sid"], "--fork-session", "--max-turns", str(TURNS["transition"])]
    p, du, out, dt = phase("transition", repo, f"{tag}-t", args, b["total"], run_dir, dict(arm="W", i=i),
                           plugin_dir=dst, prepare=prepare)
    check_S(b)
    check_parents(st)
    r2.kill_leftovers(repo)
    calls, every = tool_calls(out), all_calls(out)
    leak = sorted({n_ for n_, inp in every if LEAK.search(json.dumps(inp, ensure_ascii=False))})
    d = diff_against(repo, b["B1"], os.path.join(run_dir, f"{tag}.patch"))
    files = sorted(parse_diff(d))
    ho = os.path.join(repo, "HANDOFF.md")
    text = open(ho, "rb").read() if os.path.exists(ho) else b""
    with open(os.path.join(run_dir, f"{tag}.handoff.md"), "wb") as f:
        f.write(text)
    problems = [] if ok_result(p) else [f"result {(p['result'] or {}).get('subtype')}"]
    if not delta_ok(du, p):
        problems.append(f"delta input below main-thread input {p['ctx_sum']}")
        cap_charge("transition", f"{name}-{tag}-t", max((du or {}).get("cost", 0), 0))
    if leak:
        problems.append(f"tool call into the installed build: {leak}")
    written = "HANDOFF.md" in files
    rec = dict(arm="W", i=i, seconds=dt, delta=du, turns=p["turns"], num_turns=(p["result"] or {}).get("num_turns"),
               first=p["first"], hooks=p["hooks"], subtype=(p["result"] or {}).get("subtype"), baton=p["baton"],
               omc=p["omc"], cli=p["cli"], model=p["model"], efforts=p["efforts"], stop_blocks=p["stop_blocks"],
               memory_moved_before=mem, patch_files=files, written=written,
               handoff_bytes=len(text), handoff_sha256=hashlib.sha256(text).hexdigest(),
               markers=markers_in(text.decode("utf-8", "replace"), spec["markers"]),
               added_markers=markers_in(added_text(d) if written else "", spec["markers"]),
               skills=[x.get("skill") for n_, x in calls if n_ == "Skill"], n_tool_calls=len(calls), leak=leak,
               third_carrier=third_carrier(every), problems=problems, failed_attempts=prev, valid=not problems,
               drift_notice_reset=reset, **write_metrics(out))
    rec["ok"] = rec["valid"]  # "ok" = a valid run, as in the other phases; `written` says whether it wrote a handoff
    rec["warm"] = warm_cost(dict(rec, arm="H")) if du else None
    w[tag] = rec
    save_state(name, st)
    fresh(repo, b["B1"], b["project_dir"], f"{name}-{tag}-after")
    if leak:
        raise Stop(f"{name} {tag}: a tool call used the installed baton build ({leak})")
    print(f"{name} {tag} write valid={rec['valid']} written={written} turns={rec['turns']} warm=${rec['warm'] or 0:.3f}"
          f" raw=${(du or {}).get('cost', 0):.3f} added-line markers={sum(rec['added_markers'].values())}/{len(rec['added_markers'])}"
          f"{' problems=' + str(problems) if problems else ''}", flush=True)
    return rec


def w_required(st):
    """Facts W must carry in a repo: the markers found in the ADDED lines of every round-2 handoff patch there.
    (The game repo's B1 already held a build-written handoff with every marker, so whole-file markers say nothing.)"""
    ref = [t for t in st["transitions"].values() if t["arm"] == "H" and t.get("ok")]
    return sorted(f for f in ref[0]["added_markers"] if all(t["added_markers"][f] for t in ref)) if ref else []


def wverdict(states, ref_states=None):
    """W decision rule (pre-registered in docs/research/compact-vs-handoff-r3.md, before any W run; amended by
    Deviations 9-10 before any W run): 'cheaper' only if the median warm-normalized write cost of the valid W runs is
    lower than round 2's in both repos AND at most one valid W run misses a required marker in its handoff's added
    lines (a run that wrote no handoff misses them all); 'loses facts' if more miss; otherwise 'not cheaper'. Each
    repo needs >= 3 valid W runs, else 'inconclusive'. W2 (pre-registered in docs/research/handoff-write-w2.md before any
    W2 run, amended before any W2 run): with ref_states (CVH_WREF's states) the reference is that folder's valid W runs
    instead of round 2, and 'cheaper' needs the W2/W median ratio <= W2_RATIO in both repos; lower in both repos but
    above W2_RATIO in some repo is 'not shown cheaper'; not lower in both repos is 'not cheaper'. Two lines follow it:
    the mechanism (median assistant calls lower by >= 1 in both repos) and the margin-free comparison. The required
    markers stay round 2's."""
    import statistics as stt
    w2 = ref_states is not None
    lower, ratio, fewer, total, kept, per = {}, {}, {}, 0, 0, {}
    head, me, rl = ("W2 VERDICT vs W", "W2", "W") if w2 else ("W VERDICT", "W", "r2")
    for name, st in states.items():
        need = w_required(st)
        w = [r for r in st.get("write", {}).values() if r.get("valid", r.get("ok"))]
        if len(w) < 3:
            return f"{head}: inconclusive ({name}: {len(w)} valid {me} runs)"
        if not w2:
            mr = stt.median(warm_cost(t) for t in st["transitions"].values() if t["arm"] == "H" and t.get("ok"))
        else:
            ref = [r for r in (ref_states.get(name) or {}).get("write", {}).values() if r.get("valid", r.get("ok"))]
            if len(ref) < 3:
                return f"{head}: inconclusive ({name}: {len(ref)} valid reference W runs)"
            mr = stt.median(r["warm"] for r in ref)
            cw, cr = stt.median(r["turns"] for r in w), stt.median(r["turns"] for r in ref)
            fewer[name] = (cr - cw >= 1, f"{name} {me} {cw:g} vs {rl} {cr:g}")
        mw = stt.median(r["warm"] for r in w)
        lower[name], ratio[name] = mw < mr, mw / mr
        miss = [r["i"] for r in w if not (r.get("written", True) and all((r.get("added_markers") or {}).get(f) for f in need))]
        total, kept = total + len(w), kept + len(w) - len(miss)
        per[name] = f"warm {me} {mw:.3f} vs {rl} {mr:.3f} (ratio {mw / mr:.2f}); required (added lines) {need}; {me} runs missing one: {miss}"
    if kept < total - 1:
        v = "loses facts"
    elif not all(lower.values()):
        v = "not cheaper"
    elif w2 and not all(x <= W2_RATIO for x in ratio.values()):
        v = "not shown cheaper"
    else:
        v = "cheaper"
    out = f"{head}: {v}  (valid runs with every required marker {kept}/{total}; " + "; ".join(f"{k}: {x}" for k, x in per.items()) + ")"
    if w2:
        out += (f"\nW2 mechanism (median assistant calls lower by >= 1 in both repos): "
                f"{'confirmed' if all(x for x, _ in fewer.values()) else 'not confirmed'} ({'; '.join(s for _, s in fewer.values())})"
                f"\nW2 descriptive, no margin: median warm cost lower than W's in both repos: {'yes' if all(lower.values()) else 'no'}"
                f" (ratios {', '.join(f'{k} {x:.2f}' for k, x in ratio.items())}; the rule needs <= {W2_RATIO:.2f} in both)")
    return out


def cmd_wreport(a):
    """Reads only. This folder's write runs (called W2 when CVH_WREF is set) against round 2 and, with CVH_WREF,
    against that folder's W runs. Per run: the descriptive metrics (a run recorded before W2 gets them from its raw
    stream), first-turn input, the PostToolUse/PostToolUseFailure hook counts, and the required markers missing from
    the added lines and from the whole file."""
    import statistics as stt
    sd = os.path.join(DATA, "state")
    names = sorted(f[:-5] for f in os.listdir(sd) if f.endswith(".json"))
    me = "W2" if WREF else "W"
    def rng(v):
        v = [x for x in v if x is not None]
        return f"{stt.median(v):.3g} [{min(v):.3g}-{max(v):.3g}]" if v else "-"
    first_in = lambda r: sum((r.get("first") or {}).values()) if r.get("first") else None  # cache creation + read + input
    def per_run(label, w, need, run_dir):
        for tag, r in sorted(w.items(), key=lambda x: x[1].get("i", 0)):
            raw = os.path.join(run_dir, f"{tag}-t.jsonl")
            m = r if "commits" in r else write_metrics(raw) if os.path.exists(raw) else {}
            post = {k: v for k, v in sorted((r.get("hooks") or {}).items()) if k.startswith("PostToolUse")}
            miss = lambda key: [f for f in need if not (r.get(key) or {}).get(f)]
            reset = "" if "drift_notice_reset" not in r else f" drift-notice state removed {len(r['drift_notice_reset'])}"
            print(f"    {label} {tag}{'' if r.get('ok') else ' (invalid)'}: calls={r.get('turns')} warm=${r.get('warm') or 0:.3f}"
                  f" raw=${(r.get('delta') or {}).get('cost', 0):.3f} first_in={first_in(r)} state_filled={m.get('state_filled')}"
                  f" write+commit one message={m.get('write_commit_one_message')} commits={m.get('commits')}"
                  f" posttool_blocks={m.get('posttool_blocks')} stop_blocks={r.get('stop_blocks')} hooks={post}"
                  f" missing required: added lines {miss('added_markers')}, whole file {miss('markers')}{reset}")
    states = {}
    for name in names:
        st = states[name] = load_state(name)
        ref = [t for t in st["transitions"].values() if t["arm"] == "H" and t.get("ok")]
        w = [r for r in st.get("write", {}).values() if r.get("ok")]
        print(f"=== {name}: staged build {(st.get('stage') or {}).get('head', '?')[:8]} + {len((st.get('stage') or {}).get('uncommitted', []))} uncommitted files")
        for label, rr, warm in (("round 2", ref, [warm_cost(t) for t in ref]), (me, w, [r["warm"] for r in w])):
            print(f" {label:7s} n={len(rr)} assistant calls={rng([r['turns'] for r in rr])} warm=${rng(warm)}"
                  f" raw=${rng([r['delta']['cost'] for r in rr])} bytes={rng([r.get('handoff_bytes') for r in rr])}"
                  f" first_cc={rng([(r.get('first') or {}).get('cache_creation_input_tokens') for r in rr])}"
                  f" first_in={rng([first_in(r) for r in rr])}")
        need = w_required(st)
        print(f"    required facts (markers in the added lines of every round-2 patch): {need}")
        if w:
            print(f"    {me} missing required (added lines): {[[f for f in need if not (r.get('added_markers') or {}).get(f)] or 'none' for r in w]}"
                  f" written={sum(bool(r.get('written')) for r in w)}/{len(w)} stop_blocks={sum(r['stop_blocks'] for r in w)}"
                  f" skills={sorted({s for r in w for s in r['skills'] if s})} third_carrier={sorted({x for r in w for x in r.get('third_carrier') or []})}"
                  f" efforts={sorted({e for r in w for e in r.get('efforts') or []})}")
        per_run(me, st.get("write", {}), need, os.path.join(DATA, "runs", name))
        bad = sorted(t for t, r in st.get("write", {}).items() if not r.get("ok"))
        if bad:
            print(f"    invalid {me} runs (harness failures, rerun): {bad}")
    print(("(secondary: W2 runs by W's rule vs round 2) " if WREF else "") + wverdict(states))
    if WREF:
        ref_dir = os.path.expanduser(WREF)
        refs = {}
        for n in names:  # a repo without a reference state file loads as {}: wverdict then says inconclusive
            p = os.path.join(ref_dir, "state", f"{n}.json")
            refs[n] = json.load(open(p)) if os.path.exists(p) else {}
        for name in names:
            rw = {t: r for t, r in refs[name].get("write", {}).items() if r.get("valid", r.get("ok"))}
            v = list(rw.values())
            print(f"=== {name}: reference W ({WREF}) n={len(v)} assistant calls={rng([r['turns'] for r in v])}"
                  f" warm=${rng([r['warm'] for r in v])} raw=${rng([r['delta']['cost'] for r in v])}"
                  f" first_in={rng([first_in(r) for r in v])}")
            per_run("W", rw, w_required(states[name]), os.path.join(ref_dir, "runs", name))
        print(wverdict(states, refs))
    print(f"ledger total ${spent():.2f} of ${CAP_USD}")


def cmd_ledger(a):
    by = {}
    for r in ledger_rows():
        by[r["kind"]] = by.get(r["kind"], 0) + r["charged"]
    print(json.dumps({k: round(v, 3) for k, v in by.items()}), f"total ${spent():.2f}")


LOCK_FILE = os.path.expanduser("~/.cache/baton/experiments/.compact_ab.lock")


def lock():
    """One runner at a time: round 3 and W share the snapshot paths (one session per path). run.sh holds the same
    lock for its whole chain (lockf) and sets CVH_LOCK_HELD=1 for its own steps."""
    import fcntl
    if os.environ.get("CVH_LOCK_HELD") == "1":
        return None
    f = open(LOCK_FILE, "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise Stop("another compact_ab run holds the snapshot lock")
    return f


PAID = {"build", "transitions", "next", "probe-cut", "probe-effort", "wprobe", "write"}
LOCKED = PAID | {"startstate", "gate", "regrade", "wstage", "preflight"}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot"); s.add_argument("--name", required=True); s.add_argument("--src", required=True)
    s.add_argument("--commit", default="HEAD"); s.add_argument("--setup"); s.add_argument("--remove", nargs="*", default=["HANDOFF.md", "handoffs"])
    for c in ("build", "transitions", "next", "regrade"):
        x = sub.add_parser(c); x.add_argument("--n", type=int, default=5)
        x.add_argument("--spec", required=True, action="append" if c == "next" else None,
                       help="next: repeatable; the main block interleaves the repos by pairs")
        x.add_argument("--redo", action="store_true")
        x.add_argument("--no-followup", action="store_true"); x.add_argument("--followups-only", action="store_true")
        x.add_argument("--arm", choices=("C", "H"))
        x.add_argument("--pilot", action="store_true", help="round 3: Z1 and the first C/H pair only")
        x.add_argument("--fresh", action="store_true", help="round 3 fallback: fresh compactions replace the reused ones")
        x.add_argument("--retry-invalid", action="store_true", help="rerun runs recorded invalid (harness failures); raw files kept")
    e = sub.add_parser("seed"); e.add_argument("--name", required=True)
    e.add_argument("--from", dest="sources", action="append", required=True, help="<data folder>:<arm>, repeatable")
    for c in ("startstate", "probe-cut", "probe-effort", "wprobe", "wenv"):
        x = sub.add_parser(c); x.add_argument("--spec", required=True); x.add_argument("--tag")
    for c in ("preflight", "gate", "write"):
        x = sub.add_parser(c); x.add_argument("--spec", action="append", required=True); x.add_argument("--n", type=int, default=5)
        if c == "gate":
            x.add_argument("--revised", help="apply the pre-registered one-time T2 revision to this repo")
        if c == "preflight":
            x.add_argument("--before-fresh", action="store_true",
                           help="before the fresh compactions: report reused carriers of a repo with drop_at_start as pending")
    x = sub.add_parser("wstage"); x.add_argument("--src", required=True)
    x.add_argument("--check", action="store_true", help="$0: only compare the staged build with the source tree")
    sub.add_parser("wreport")
    r = sub.add_parser("report"); r.add_argument("--repo"); r.add_argument("--task", choices=("T1", "T2"))
    sub.add_parser("ledger")
    a = ap.parse_args()
    if isinstance(getattr(a, "spec", None), str):
        a.spec = os.path.abspath(a.spec)
    fn = {"snapshot": cmd_snapshot, "build": cmd_build, "transitions": cmd_transitions, "next": cmd_next,
          "report": cmd_report, "ledger": cmd_ledger, "regrade": cmd_regrade, "seed": cmd_seed,
          "startstate": cmd_startstate, "probe-cut": cmd_probe_cut, "probe-effort": cmd_probe_effort, "preflight": cmd_preflight, "gate": cmd_gate,
          "wstage": cmd_wstage, "wprobe": cmd_wprobe, "wenv": cmd_wenv, "write": cmd_write, "wreport": cmd_wreport}[a.cmd]
    try:
        held = lock() if a.cmd in LOCKED else None
        fn(a)
    except Stop as e:
        print(f"STOP: {e}", flush=True)
        sys.exit(3)
    except Exception:
        import traceback
        traceback.print_exc()
        print("STOP: unexpected error", flush=True)
        sys.exit(4)
