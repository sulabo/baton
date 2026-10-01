#!/usr/bin/env python3
"""Round2-E A/B: does injecting a session-start card (observer/card.py) reduce what the
agent reads on its own in the first K turns?

Two arms, same first prompt, real `claude -p` sessions in an isolated snapshot copy of the
target repo (no remote, reset with git between runs). Make the snapshot from the WORKING TREE
including untracked-but-not-ignored files (`git ls-files -co --exclude-standard -z | tar --null -T -`),
and put it somewhere that outlives the session (not the session scratchpad) — see round2-E-ab.md. Arm "on" adds a SessionStart hook
that prints the card; arm "off" adds nothing. Runs alternate off/on to spread time drift.

  python3 round2_e_ab.py snapshot --src <repo> --dest <baton>/.data/snapshots/<name>
  python3 round2_e_ab.py run   --repo <snapshot> --data <dir> --n 5 [--max-turns 6] [--prompt ...] [--max-usd 12]
  python3 round2_e_ab.py count --repo <snapshot> --data <dir> [--k 5]

Reads are counted the same way as round1_e.py (Read file_path, Grep/Glob path, and file
tokens inside Bash commands) so the two rounds compare. Sub-agent reads are not visible in
the stream-json main thread and are not counted.
"""
import json, os, re, sys, signal, subprocess, statistics, time, argparse, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from round1_e import bash_files, EXT, IS_HANDOFF  # noqa: E402

PROMPT = "핸드오프 읽고 이어서 해줘"
CARD = os.path.join(HERE, "..", "card.py")
ONDEMAND = os.path.join(HERE, "..", "..", "hooks", "handoff-inject.py")  # 플러그인 훅 그대로

# ---------------- run ----------------
FULL_HEAD = ("[baton] 아래는 이 저장소 HANDOFF.md의 전문이다(세션 시작 시 자동 주입). "
             "파일을 다시 열 필요 없다. 그대로 이어서 진행한다.")

def settings_for(arm):
    """arm 'on': 3절 카드(card.py, 구 헤더). 'card4': 4절 카드+다시 열 필요 없다 헤더. 'full': HANDOFF.md 전문. 'off': 없음."""
    if arm == "on":
        cmd = f'python3 "{os.path.abspath(CARD)}" "$CLAUDE_PROJECT_DIR/HANDOFF.md"'
    elif arm == "card4":
        cmd = f'python3 "{os.path.abspath(CARD)}" "$CLAUDE_PROJECT_DIR/HANDOFF.md" --with-next --limit 6144'
    elif arm == "full":
        cmd = f'printf "%s\\n\\n" "{FULL_HEAD}"; cat "$CLAUDE_PROJECT_DIR/HANDOFF.md"'
    elif arm in ("ondemand", "concept"):
        prefix = "BATON_CONCEPT_INJECT=on BATON_HANDOFF_INJECT=off " if arm == "concept" else ""
        # SessionStart는 프롬프트를 못 본다. UserPromptSubmit에서 프롬프트가 인계를 가리킬 때만 전문을 넣는다.
        return json.dumps({"hooks": {"UserPromptSubmit": [{"hooks": [
            {"type": "command", "command": f'{prefix}python3 "{os.path.abspath(ONDEMAND)}"', "timeout": 10}]}]}}, ensure_ascii=False)
    elif arm == "noomc":
        # 주입 없음 + OMC 플러그인 끔. 첫 턴 컨텍스트에서 OMC 몫을 분리한다.
        return json.dumps({"enabledPlugins": {"oh-my-claudecode@omc": False}}, ensure_ascii=False)
    else:
        return None
    return json.dumps({"hooks": {"SessionStart": [{"matcher": "*", "hooks": [
        {"type": "command", "command": cmd, "timeout": 10}]}]}}, ensure_ascii=False)

def validate_snapshot(repo):
    """Refuse destructive resets outside the experiment snapshot tree."""
    from pathlib import Path
    path = Path(repo).resolve()
    base = Path(HERE).parents[1] / ".data" / "snapshots"
    # 문자열 대신 같은 폴더인지로 비교 — 한글 경로는 넘긴 문자열과 getcwd()의 유니코드 정규화(NFC/NFD)가 다를 수 있다(09-29)
    inside = base.is_dir() and any(p.is_dir() and p.samefile(base) for p in path.parents)
    if not inside or not (path / ".git").is_dir():
        raise ValueError("run requires a dedicated .data/snapshots git copy")
    remotes = subprocess.run(["git", "-C", str(path), "remote"], capture_output=True, text=True, check=True)
    if remotes.stdout.strip():
        raise ValueError("snapshot must have no remote")


def reset(repo, base="HEAD"):
    """base로 되돌린다 — 세션이 커밋해 HEAD가 움직였어도 스냅샷 커밋으로 돌아간다."""
    validate_snapshot(repo)
    subprocess.run(["git", "-C", repo, "reset", "-q", "--hard", base], check=True)
    subprocess.run(["git", "-C", repo, "clean", "-fdq"], check=True)

SESSION_STATE = (".omc", ".omx")  # 하네스 런타임 상태 — 스냅샷 내용이 아니므로 실행마다 지운다


def _nfc(p):
    return unicodedata.normalize("NFC", os.path.realpath(os.path.expanduser(p)))


def ignored_set(repo):
    """gitignore에 걸린 경로(디렉터리 단위). 실행 전후를 비교해 세션이 새로 만든 것만 지운다."""
    # check=True: 실행 전 조회가 조용히 실패하면 빈 집합이 되어 setup 산출물까지 지운다(09-29 리뷰)
    out = subprocess.run(["git", "-C", repo, "ls-files", "-z", "-o", "-i", "--exclude-standard", "--directory"],
                         capture_output=True, text=True, check=True).stdout
    return {x for x in out.split("\0") if x}


def clean_leftovers(repo, before):
    """세션이 새로 만든 무시 대상(npm install 산출물 등)과 하네스 상태를 지운다 — git clean은 무시 대상을 안 지운다.
    ponytail: 디렉터리 단위 비교라 실행 전부터 있던 node_modules/ 안의 변경은 되돌리지 않는다(setup 산출물 보존이 우선)."""
    import shutil
    validate_snapshot(repo)
    new = ignored_set(repo) - before
    # 세션이 폴더의 추적 파일을 다 지우면 git이 그 폴더를 통째로 무시 대상으로 다시 보고한다 — 실행 전 항목의 상위면 남긴다(09-29 리뷰)
    # 반대로 실행 전 폴더의 하위로 새로 보고된 것(add -f·gitignore 변경 탓)도 남긴다 — setup 산출물 보존이 우선
    new = {x for x in new if not any(b.startswith(x.rstrip("/") + "/") or (b.endswith("/") and x.startswith(b)) for b in before)}
    # 하네스 상태는 git clean으로 추적 안 된 것만 지운다 — 커밋된 .omc/skills는 남고, 링크는 파일로 다뤄 링크만 지운다
    state = [x for x in SESSION_STATE if os.path.lexists(os.path.join(repo, x))]
    if state:
        subprocess.run(["git", "-C", repo, "-c", "core.fsmonitor=", "clean", "-ffdxq", "--"] + state, check=True)
    gone = sorted(new) + state
    root = os.path.realpath(repo) + os.sep
    for rel in gone:
        full = os.path.join(repo, rel.rstrip("/"))  # 끝 "/"가 있으면 islink가 링크를 풀어 판정한다
        if os.path.islink(full) or not os.path.isdir(full):
            if os.path.lexists(full): os.remove(full)  # 링크는 링크만 지운다 — 가리키는 대상은 스냅샷 밖일 수 있다
        elif os.path.realpath(full).startswith(root):
            shutil.rmtree(full)
    return gone


def kill_leftovers(repo):
    """세션이 띄우고 안 끈 프로세스(dev 서버 등)를 끈다 — 작업 폴더(cwd)가 스냅샷 안인 것만(09-29 vite :5199가 남았다)."""
    root, pid, killed = _nfc(repo), None, []
    keep, q = set(), os.getpid()  # 러너 자신과 조상(스냅샷 안에서 러너를 띄운 셸 등)은 남긴다
    while q > 1 and q not in keep:
        keep.add(q)
        q = int(subprocess.run(["ps", "-o", "ppid=", "-p", str(q)], capture_output=True, text=True).stdout.strip() or 0)
    out = subprocess.run(["lsof", "-a", "-d", "cwd", "-F", "pn"], capture_output=True, text=True).stdout
    for ln in out.splitlines():
        if ln.startswith("p"): pid = int(ln[1:])
        elif ln.startswith("n") and pid and pid not in keep:
            cwd = _nfc(ln[1:])
            if cwd == root or cwd.startswith(root + os.sep):
                name = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
                try: os.kill(pid, signal.SIGTERM); killed.append(f"{pid} {name[:60]}")  # 무엇을 껐는지 기록에 남긴다
                except ProcessLookupError: pass
    return killed


HOME_SKIP = (os.path.join(os.path.expanduser("~"), ".claude"),)  # 하네스 설정·스킬 읽기는 프로젝트 정보가 아니다


def outside_paths(jsonl_path, repo):
    """세션이 스냅샷 밖 홈 경로를 건드렸는지(휴리스틱) — 도구 인자의 절대 경로와 Bash 명령 안의 홈 경로.
    ponytail: 문자열 추출이라 변수·상대 경로(../..)로 나간 것은 못 잡는다. 막는 장치가 아니라 기록이다."""
    root, home, hits = _nfc(repo), _nfc("~"), []
    def check(path):
        full = _nfc(path)
        if full.startswith(home + os.sep) and not (full == root or full.startswith(root + os.sep)) \
                and not any(full == _nfc(x) or full.startswith(_nfc(x) + os.sep) for x in HOME_SKIP):
            hits.append(path.strip()[:100])
    with open(jsonl_path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    for ln in lines:
        try: d = json.loads(ln)
        except Exception: continue
        if d.get("type") != "assistant": continue
        for b in d["message"].get("content") or []:
            if b.get("type") != "tool_use": continue
            inp = b.get("input") or {}
            for k in ("file_path", "path", "notebook_path"):
                v = inp.get(k)
                if isinstance(v, str) and v.startswith(("/", "~")): check(v)
            cmd = inp.get("command")
            if isinstance(cmd, str):
                flat = unicodedata.normalize("NFC", cmd.replace('"', "").replace("'", "")).replace("~/", home + "/")
                for m in re.finditer(re.escape(home) + r"/[^;|&\n)<>]*", flat):
                    check(m.group(0).split(" -")[0].rstrip())
    return list(dict.fromkeys(hits))[:10]


def run_one(repo, arm, out_path, max_turns, prompt=PROMPT, max_usd=None, plugin_dir=None, confine=False):
    cmd = ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose",
           "--max-turns", str(max_turns)]
    if max_usd is not None:
        cmd += ["--max-budget-usd", str(max_usd)]
    cmd += ["--include-hook-events"]
    if plugin_dir:  # 설치 없이 이 세션에서만 플러그인을 불러온다(4단계: driftmap 스킬)
        cmd += ["--plugin-dir", plugin_dir]
    st = settings_for(arm)
    if confine:  # 스냅샷 밖 읽기 막기(09-29): Bash는 샌드박스 denyRead/allowRead, 도구는 blockReadsOutsideWorkingDirectories
        merged = json.loads(st) if st else {}
        merged["sandbox"] = {"enabled": True, "filesystem": {"denyRead": ["~/"], "allowRead": [os.path.abspath(repo)]},
                              "allowUnsandboxedCommands": False,
                              "failIfUnavailable": True}  # 샌드박스가 못 뜨면 조용히 없이 돌지 않게  # dangerouslyDisableSandbox 재시도로 빠져나가지 못하게(09-29 리뷰)
        merged.setdefault("permissions", {})["blockReadsOutsideWorkingDirectories"] = True
        st = json.dumps(merged, ensure_ascii=False)
    if st:
        cmd += ["--settings", st]
    t0 = time.time()
    with open(out_path, "w") as fo, open(out_path + ".err", "w") as fe:
        # 실험 세션의 훅 판단이 실사용 관찰 로그(~/.cache/baton/runs.jsonl)에 섞이지 않게 끈다
        p = subprocess.run(cmd, cwd=repo, stdin=subprocess.DEVNULL, stdout=fo, stderr=fe,
                           env={**os.environ, "BATON_OBSERVE": "off"})
    return p.returncode, time.time() - t0

def cmd_run(a):
    validate_snapshot(a.repo)
    os.makedirs(a.data, exist_ok=True)
    index_path = os.path.join(a.data, "runs.json")
    index = []
    if os.path.exists(index_path):
        with open(index_path) as stream:
            index = json.load(stream)
    done = {(r["arm"], r["i"]) for r in index}
    arms = a.arms.split(",")
    if set(arms) - {"off", "on", "full", "card4", "ondemand", "noomc", "concept"}:
        raise ValueError("unknown experiment arm")
    order = [(arm, i) for i in range(1, a.n + 1) for arm in arms]
    fails = 0
    spent = sum(r.get("cost_usd") or 0 for r in index)
    # 재개 때는 첫 실행의 base를 쓴다 — 격리 없는 모드에서 세션 커밋 뒤 러너가 죽으면 HEAD가 오염돼 있다(09-29 리뷰)
    base = next((r["base"] for r in index if r.get("base")), None) or \
        subprocess.run(["git", "-C", a.repo, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    for arm, i in order:
        if (arm, i) in done: continue
        if a.max_usd and spent >= a.max_usd:
            print(f"STOP: budget {a.max_usd} USD reached (spent {spent:.2f})", flush=True); sys.exit(1)
        run_repo = a.repo
        if getattr(a, "isolated_runs", False):
            import shutil
            run_repo = os.path.join(os.path.dirname(a.repo), os.path.basename(a.repo) + "-" + os.path.basename(os.path.abspath(a.data)) + f"-{arm}-{i}")
            if os.path.exists(run_repo):
                raise ValueError(f"isolated run path already exists: {run_repo}")
            shutil.copytree(a.repo, run_repo, ignore=shutil.ignore_patterns(".omc", ".omx"))
        reset(run_repo, base)
        clean_leftovers(run_repo, ignored_set(run_repo))  # 이전 실험의 .omc가 첫 실행에만 보이지 않게 세션 전에도 지운다
        before = ignored_set(run_repo)
        git_config = os.path.join(run_repo, ".git", "config")
        with open(git_config, "rb") as f: config_bytes = f.read()
        out = os.path.join(a.data, f"{arm}-{i}.jsonl")
        rc, dt = run_one(run_repo, arm, out, a.max_turns, a.prompt,
                              a.max_usd - spent if a.max_usd else None, getattr(a, "plugin_dir", None),
                              getattr(a, "confine_reads", False))
        killed, leftovers, outside, iso_err = [], [], [], None
        # 세션이 .git/config에 심은 fsmonitor·filter를 러너의 git이 실행하지 않게 먼저 되돌린다(09-29 2차 리뷰)
        with open(git_config, "wb") as f: f.write(config_bytes)
        try:
            killed = kill_leftovers(run_repo)  # diff 전에 끈다 — 살아 있는 dev 서버가 diff 중에 파일을 바꾸지 않게
        except Exception as e: iso_err = f"kill: {e!r}"
        # 다음 reset이 지우기 전에 세션이 남긴 변경을 보존한다(채점용).
        # 세션이 .git/config에 넣은 fsmonitor·훅·textconv를 러너가 실행하지 않게 끈다(09-29 리뷰)
        g = ["git", "-C", run_repo, "-c", "core.fsmonitor=", "-c", "core.hooksPath=/dev/null", "-c", "core.quotepath=false"]
        with open(out + ".diff", "w") as fd:
            # 스테이징·커밋·삭제까지 잡으려고 전부 올린 뒤 base와 비교한다(add -N + 작업트리 diff는 삭제·커밋을 놓쳤다 — 09-29 리뷰).
            # 한글 경로를 그대로(quotepath=false), 사용자 diff 도구 없이 — case_grade.py가 경로로 채점한다. 하네스 상태는 뺀다.
            subprocess.run(g + ["add", "-A"], check=False)
            subprocess.run(g + ["diff", "--cached", "--no-renames", "--no-ext-diff", "--no-textconv", base,
                                "--", ".", ":(exclude).omc", ":(exclude).omx"], stdout=fd, check=False)
        for key, step in (("clean", lambda: clean_leftovers(run_repo, before)), ("outside", lambda: outside_paths(out, run_repo))):
            try:
                if key == "clean": leftovers = step()
                else: outside = step()
            except Exception as e: iso_err = (iso_err + " / " if iso_err else "") + f"{key}: {e!r}"  # 비용 기록이 빠지지 않게 계속 간다
        if iso_err: print(f"  isolation error: {iso_err}", flush=True)
        if killed or leftovers or outside:
            print(f"  isolation: killed={killed} cleaned={leftovers[:5]} outside={outside[:3]}", flush=True)
        res = tail_result(out)
        # max-turns 도달은 claude가 rc=1·subtype=error_max_turns로 끝낸다. 측정에는 첫 K턴만 쓰므로 정상이다.
        ok = res is not None and res.get("subtype") in ("success", "error_max_turns")
        # 사용량 한도 등은 subtype=success인데 is_error=True로 온다(결과 텍스트 "session limit"). 데이터 아님.
        if ok and res.get("is_error") and res.get("subtype") == "success":
            ok = False
            print(f"  not ok: {str(res.get('result'))[:80]}", flush=True)
        print(f"{arm}-{i}: rc={rc} {dt:.0f}s turns={res and res.get('num_turns')} "
              f"cost={res and round(res.get('total_cost_usd', 0), 2)} sid={res and res.get('session_id')}",
              flush=True)
        index.append(dict(arm=arm, i=i, rc=rc, subtype=res and res.get("subtype"), seconds=round(dt), file=os.path.basename(out),
                          session_id=res and res.get("session_id"),
                          num_turns=res and res.get("num_turns"),
                          cost_usd=res and res.get("total_cost_usd"),
                          model=res and res.get("model"), prompt=a.prompt, ok=ok, repo=run_repo,
                          killed=killed, cleaned=leftovers, outside=outside, confine=getattr(a, "confine_reads", False),
                          base=base, isolation_error=iso_err))
        spent += (res and res.get("total_cost_usd")) or 0
        with open(index_path, "w") as f:
            json.dump(index, f, ensure_ascii=False, indent=1)
        fails = 0 if ok else fails + 1
        if fails >= 2:
            print("STOP: same failure twice in a row", flush=True); sys.exit(1)
    reset(a.repo, base)

def tail_result(path):
    res = None
    for ln in open(path, encoding="utf-8"):
        try: d = json.loads(ln)
        except Exception: continue
        if d.get("type") == "result": res = d
        if d.get("type") == "system" and d.get("subtype") == "init": model = d.get("model")
    if res is not None:
        try: res["model"] = model
        except NameError: pass
    return res

# ---------------- count ----------------
def tokens_of(path):
    """(첫 턴 컨텍스트, 세션 누적 입력) — 입력은 input+cache_creation+cache_read. result.usage는 누적값이다."""
    first, total = None, None
    for ln in open(path, encoding="utf-8"):
        try: d = json.loads(ln)
        except Exception: continue
        u = None
        if d.get("type") == "assistant" and first is None and not d.get("parent_tool_use_id"):
            u = d["message"].get("usage") or {}
            first = sum(u.get(k, 0) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
        if d.get("type") == "result":
            u = d.get("usage") or {}
            total = sum(u.get(k, 0) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    return first, total

def turns_of(path):
    """Main-thread assistant tool_use blocks grouped by API message id, in order."""
    turns, seen, card_seen, texts = [], {}, False, []
    for ln in open(path, encoding="utf-8"):
        try: d = json.loads(ln)
        except Exception: continue
        if d.get("type") == "system" and d.get("subtype") == "hook_response":
            if "[baton" in (d.get("stdout") or d.get("output") or ""): card_seen = True
        if d.get("type") != "assistant" or d.get("parent_tool_use_id"): continue
        mid = d["message"].get("id") or d.get("uuid")
        if mid not in seen:
            seen[mid] = len(turns); turns.append([])
        for b in d["message"].get("content") or []:
            if isinstance(b, dict) and b.get("type") == "tool_use":
                turns[seen[mid]].append(b)
            elif isinstance(b, dict) and b.get("type") == "text":
                texts.append(b.get("text", ""))
    return turns, card_seen, texts

def rel(p, repo):
    p = os.path.normpath(p)
    if p == repo: return None
    if p.startswith(repo + "/"): return p[len(repo) + 1:]
    return None

def measure(path, repo, k):
    turns, card_seen, texts = turns_of(path)
    tok_first, tok_total = tokens_of(path)
    reads, outside, n_read_tool, n_bash_files, agents = [], 0, 0, 0, 0
    for t in turns[:k]:
        for b in t:
            name, inp = b.get("name"), b.get("input", {}) or {}
            cands = []
            if name == "Read":
                if inp.get("file_path"): cands.append(inp["file_path"]); n_read_tool += 1
            elif name in ("Grep", "Glob"):
                if inp.get("path") and EXT.search(inp["path"]): cands.append(inp["path"])
            elif name == "Bash":
                bf = bash_files(inp.get("command", "")); n_bash_files += len(bf); cands.extend(bf)
            elif name in ("Task", "Agent"):
                agents += 1
            for fp in cands:
                if fp.startswith("/"):
                    r = rel(fp, repo)
                    if r is None: outside += 1; continue
                else:
                    r = fp
                reads.append(r)
    uniq = sorted(set(reads))
    total, missing = 0, 0
    for p in uniq:
        ap = os.path.join(repo, p)
        if os.path.isfile(ap): total += os.path.getsize(ap)
        else: missing += 1
    return dict(nturns=len(turns), uniq=uniq, n_uniq=len(uniq), bytes=total, missing=missing,
                outside=outside, n_read_tool=n_read_tool, n_bash_files=n_bash_files,
                handoff=sum(1 for p in uniq if IS_HANDOFF.search(p)), card_seen=card_seen,
                agents=agents, ntext=sum(len(t) for t in texts), tok_first=tok_first, tok_total=tok_total)

def med(v): return statistics.median(v) if v else None
def mean(v): return statistics.mean(v) if v else None

def cmd_count(a):
    index = json.load(open(os.path.join(a.data, "runs.json")))
    rows = []
    for r in index:
        if not r.get("ok"): continue
        m = measure(os.path.join(a.data, r["file"]), r.get("repo", a.repo), a.k)
        m.update(arm=r["arm"], i=r["i"], api_turns=r.get("num_turns"), cost=r.get("cost_usd"))
        rows.append(m)
    prompts = sorted({r.get("prompt") or PROMPT for r in index})
    print(f"=== ROUND2-E A/B  K={a.k}  prompt={prompts}  repo={a.repo}")
    print(f"{'run':7} {'card':4} {'trn':>3} {'files':>5} {'bytes':>8} {'HO':>2} {'out':>3} {'Read':>4} {'bashF':>5} {'agent':>5} {'cost':>6} {'tok1':>6} {'tokIn':>7}  files read (first K turns)")
    for m in rows:
        print(f"{m['arm']+'-'+str(m['i']):7} {str(m['card_seen'])[:1]:4} {m['nturns']:3d} {m['n_uniq']:5d} {m['bytes']:8d} "
              f"{m['handoff']:2d} {m['outside']:3d} {m['n_read_tool']:4d} {m['n_bash_files']:5d} {m['agents']:5d} "
              f"{(m['cost'] or 0):6.2f} {m['tok_first'] or 0:6d} {m['tok_total'] or 0:7d}  {', '.join(m['uniq'])[:110]}")
    print("\n=== AGGREGATE (per arm) ===")
    print(f"{'arm':4} {'n':>2} {'files med':>9} {'files mean':>10} {'bytes med':>10} {'bytes mean':>11} {'HO read':>8} {'card':>5} {'turns med':>9} {'cost mean':>9} {'tok1 med':>8} {'tokIn med':>9}")
    for arm in ("off", "on", "full", "card4", "ondemand", "noomc", "concept"):
        s = [m for m in rows if m["arm"] == arm]
        if not s: continue
        f = [m["n_uniq"] for m in s]; b = [m["bytes"] for m in s]; t = [m["nturns"] for m in s]
        print(f"{arm:4} {len(s):2d} {med(f):9.1f} {mean(f):10.1f} {med(b):10,.0f} {mean(b):11,.0f} "
              f"{sum(1 for m in s if m['handoff'])}/{len(s):<5} {sum(1 for m in s if m['card_seen'])}/{len(s):<2} "
              f"{med(t):9.1f} {mean([m['cost'] or 0 for m in s]):9.2f} "
              f"{med([m['tok_first'] or 0 for m in s]):8,.0f} {med([m['tok_total'] or 0 for m in s]):9,.0f}")
    print("\n=== NOT COUNTED ===")
    print("runs not ok (excluded):", [f"{r['arm']}-{r['i']}" for r in index if not r.get("ok")])
    print("reads outside snapshot (summed):", sum(m["outside"] for m in rows))
    print("read files missing on disk (summed):", sum(m["missing"] for m in rows))
    print("sub-agent launches in first K turns (their reads are invisible here):", sum(m["agents"] for m in rows))
    print("runs with fewer than K turns:", [f"{m['arm']}-{m['i']}({m['nturns']})" for m in rows if m["nturns"] < a.k])

# ---------------- snapshot ----------------
def cmd_snapshot(a):
    """작업 트리를 미추적 포함·ignore 제외로 떠 원격 없는 저장소로 만든다. 매니페스트는 스냅샷 밖(<dest>.manifest.json)에 둔다
    — 안에 두면 실험 세션이 읽는다."""
    src, dest = os.path.abspath(a.src), os.path.abspath(a.dest)
    if os.path.exists(dest): sys.exit(f"exists: {dest}")
    os.makedirs(dest)
    ls = subprocess.run(["git", "-C", src, "ls-files", "-co", "--exclude-standard", "-z"], capture_output=True, check=True).stdout
    # -c는 작업 트리에서 지운 추적 파일도 낸다. 실제로 있는 것만 담는다(없으면 tar가 실패한다).
    ls = b"\0".join(x for x in ls.split(b"\0") if x and os.path.lexists(os.path.join(src.encode(), x))) + b"\0"
    t1 = subprocess.Popen(["tar", "--null", "-T", "-", "-cf", "-"], cwd=src, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    t2 = subprocess.Popen(["tar", "-x", "-C", dest], stdin=t1.stdout)
    t1.stdin.write(ls); t1.stdin.close(); t1.stdout.close(); t2.wait(); t1.wait()
    if t1.returncode or t2.returncode: sys.exit("tar failed")
    subprocess.run(["git", "init", "-q"], cwd=dest, check=True)
    subprocess.run(["git", "add", "-A"], cwd=dest, check=True)
    subprocess.run(["git", "-c", "user.name=snap", "-c", "user.email=snap@local", "commit", "-qm", "snapshot"], cwd=dest, check=True)
    head = subprocess.run(["git", "-C", src, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", src, "status", "--porcelain"], capture_output=True, text=True).stdout.count("\n")
    n = len([x for x in ls.split(b"\0") if x])
    man = dict(src=src, src_head=head, src_dirty_entries=dirty, files=n, made=time.strftime("%Y-%m-%dT%H:%M:%S"))
    json.dump(man, open(dest.rstrip("/") + ".manifest.json", "w"), ensure_ascii=False, indent=1)
    print(json.dumps(man, ensure_ascii=False))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("--repo", required=True); r.add_argument("--data", required=True)
    r.add_argument("--n", type=int, default=5); r.add_argument("--max-turns", type=int, default=6)
    r.add_argument("--arms", default="off,on", help="comma list, run order interleaved: off,on,full,card4,ondemand,noomc")
    r.add_argument("--isolated-runs", action="store_true", help="fresh snapshot path per run; omit OMC/OMX runtime memory")
    r.add_argument("--plugin-dir", default=None, help="load a plugin for these sessions only (no install)")
    r.add_argument("--confine-reads", action="store_true",
                   help="sandbox Bash reads to the snapshot and block tool reads outside it (changes conditions vs runs without it)")
    r.add_argument("--prompt", default=PROMPT); r.add_argument("--max-usd", type=float, default=0.0)
    sn = sub.add_parser("snapshot"); sn.add_argument("--src", required=True); sn.add_argument("--dest", required=True)
    c = sub.add_parser("count"); c.add_argument("--repo", required=True); c.add_argument("--data", required=True)
    c.add_argument("--k", type=int, default=5)
    a = ap.parse_args()
    if a.cmd == "snapshot": cmd_snapshot(a); sys.exit(0)
    a.repo = os.path.abspath(a.repo)
    (cmd_run if a.cmd == "run" else cmd_count)(a)
