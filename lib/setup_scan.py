#!/usr/bin/env python3
"""/baton-setup 스캐너 — 이 사용자의 과거 기록으로 baton 문턱과 개인 자료 목록 후보를 제안한다. 읽기만 한다.

  setup_scan.py [저장소 루트] [--json]     제안만 출력한다. 아무것도 바꾸지 않는다
  setup_scan.py apply [저장소 루트] [--global] [--set 키=값]... [--unset 키]... [--private-term 단어]... [--trigger 말]...
        [--private-terms-file 경로|-] [--remove-terms-file 경로|-] [--remove-term 단어]... [--remove-trigger 말]...
      사용자가 고른 것만 설정 파일(lib/config.py)에 쓴다. --global이면 전역 절, 아니면 이 저장소 절. 값은 키마다 검사한다.
  저장소 루트를 빼면 CLAUDE_PROJECT_DIR, 없으면 지금 폴더. 어느 쪽이든 git 최상위로 모은다(config.repo_key — 훅도 같은 함수를 쓴다).

읽는 것: 이 저장소 최상위 폴더에서 연 Claude Code 세션 기록(~/.claude/projects/*/*.jsonl), git 이력, 추적 파일과
무시되지 않은 미추적 파일(git grep --untracked), 다른 프로젝트 세션 기록의 cwd(프로젝트 이름 후보를 만들려고).
세는 방법은 기존 측정 코드를 그대로 쓴다 — 저장소별 세션 파일은 observer/baton_init.py, 세션 고르기·첫 프롬프트·인계서 재독은
observer/research/usage_week.py, 맥락 크기와 끊기 재계산은 observer/research/split_sim.py, 편집 파일은 hooks/handoff-check.py.
프롬프트 원문은 관찰 로그(~/.cache/baton/runs.jsonl)에 쓰지 않는다. 다만 스캔 출력(트리거 후보 말·개인 자료 후보)과
apply 명령줄은 스킬로 돌리면 에이전트 맥락과 Claude Code 세션 기록에 남는다 — 개인 자료는 --private-terms-file로 넘기거나 세션 밖 터미널에서 돌린다.
"""
import argparse, collections, getpass, glob, importlib.util, json, os, re, statistics, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "observer"))
sys.path.insert(0, os.path.join(ROOT, "observer", "research"))
import config, rules
import baton_init, split_sim, usage_week

_spec = importlib.util.spec_from_file_location("handoff_check_hook", os.path.join(ROOT, "hooks", "handoff-check.py"))
hc = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(hc)

MIN_SESSIONS = 10  # 이보다 적으면 문턱을 바꾸자고 하지 않는다 — 몇 세션의 우연에 문턱이 흔들린다
DEFAULT_RATIOS = "2,3"
RATIO_CANDIDATES = (1.5, 2.0, 2.5, 3.0, 4.0)
COST_SHARE = 0.85
DEFAULT_NUDGE = 3
NUDGE_MARGIN = 0.10
HANDOFF_NAME = re.compile(r"(?i)^handoff.*\.md$")
WORD = re.compile(r"[0-9A-Za-z가-힣]+")
EMAIL = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
PLACEHOLDER = re.compile(r"(?i)@(example\.(com|org|net)|test|localhost)$")
# ponytail: Codex 세션(~/.codex/sessions)은 세지 않는다 — 저장소에는 파일 연결 검증(observer/measure/codex_join_census.py)만 있고
# 프롬프트·토큰·편집 레코드 형식을 읽는 코드가 없다. 형식을 확인해 usage_week처럼 읽는 함수를 만들면 여기에 더한다
CODEX_NOTE = "Codex 세션은 세지 않음 — Codex 세션 파일의 프롬프트·호출 형식을 이 저장소 코드가 아직 다루지 않는다(observer/baton_init.py와 같은 범위)"


def pct(x):
    return f"{x:.0%}"


def git(root, *args):
    """git 출력(문자열). 실패하면 None — 0건과 못 셈을 구분하려고."""
    try:
        r = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode in (0, 1) else None  # git grep은 못 찾으면 1


# ── 세션 ──────────────────────────────────────────────────────────────

def load_sessions(root):
    files = baton_init.claude_files_for(root)
    sessions, skipped = usage_week.collect(files=files)
    return sessions, skipped, len(files)


def quartiles(xs):
    if len(xs) < 2:
        return [xs[0]] * 3 if xs else []
    q = statistics.quantiles(xs, n=4)
    return [q[0], statistics.median(xs), q[2]]


def cost_after(ctxs, ratio):
    """맥락이 첫 호출의 ratio배에 처음 닿은 호출부터 끝까지의 비용(split_sim.weighted와 같은 가중)."""
    i = next((k for k, c in enumerate(ctxs) if c >= ctxs[0] * ratio), None)
    return 0.0 if i is None else split_sim.weighted(ctxs) - split_sim.weighted(ctxs[:i])


def growth(sessions):
    """세션마다 최대 맥락 ÷ 첫 호출 맥락. 끊기 문턱 후보마다 닿는 세션 비율, 그 뒤에 남은 비용 몫, 재계산 절감(split_sim)."""
    rows, bad = [], 0
    for s in sessions:
        ctxs = split_sim.call_contexts(s["file"])
        if ctxs and ctxs[0] > 0:
            rows.append(ctxs)
        else:
            bad += 1
    out = {"counted": len(rows), "uncounted": bad, "uncounted_reason": "첫 호출 맥락 토큰이 기록에 없음",
           "recommend": None}
    if not rows:
        out["reason"] = "센 세션이 없어 기본값 유지"
        return out
    g = sorted(max(c) / c[0] for c in rows)
    base = sum(split_sim.weighted(c) for c in rows)
    out["quartiles"] = [round(x, 2) for x in quartiles(g)]
    out["candidates"] = [{"ratio": r, "reach": sum(x >= r for x in g) / len(g),
                          "cost_after": sum(cost_after(c, r) for c in rows) / base,
                          "saving": 1 - sum(split_sim.weighted(split_sim.simulate(c, r)[0]) for c in rows) / base}
                         for r in RATIO_CANDIDATES]
    # 기본값 2배의 근거와 같은 방법: "비용의 85%가 맥락이 첫 호출의 2배를 넘은 뒤에 나갔다"(세션 60개).
    # 이 사용자에게서 비용의 85% 이상이 아직 뒤에 남아 있는 가장 높은 문턱을 고른다 — 늦게 알릴수록 알림이 덜 뜨고, 85%는 여전히 잡는다.
    # ponytail: 문턱 후보는 RATIO_CANDIDATES 다섯 개뿐이고 둘째 알림은 첫째+1배로 둔다. 절감 재계산은 반사실 상한이라
    # 낮은 문턱을 늘 유리하게 보이므로 고르는 데 쓰지 않고 보여 주기만 한다. 실사용 로그가 쌓이면 실제로 넘긴 비율로 바꾼다
    ok = [c["ratio"] for c in out["candidates"] if c["cost_after"] >= COST_SHARE]
    if len(rows) < MIN_SESSIONS:
        out["reason"] = f"센 세션 {len(rows)}개 — {MIN_SESSIONS}개 미만이라 기본값 {DEFAULT_RATIOS} 유지"
    elif not ok:
        out["reason"] = (f"어느 문턱에서도 비용의 {COST_SHARE:.0%}가 뒤에 남지 않는다(세션이 크게 불지 않는다) — "
                         f"알림으로 아낄 몫이 작아 기본값 {DEFAULT_RATIOS} 유지")
    elif max(ok) == 2.0:
        out["reason"] = f"비용의 {COST_SHARE:.0%} 이상이 뒤에 남는 가장 높은 문턱이 기본값과 같은 2배 — 유지"
    else:
        best = max(ok)
        out["recommend"] = f"{best:g},{best + 1:g}"
        share = next(c["cost_after"] for c in out["candidates"] if c["ratio"] == best)
        out["reason"] = (f"{best:g}배에 닿은 뒤에도 비용의 {share:.0%}가 남는다 — 비용의 {COST_SHARE:.0%} 이상이 남는 가장 높은 문턱"
                         f"(기본값 2배를 정한 방법과 같다)")
    return out


def nudge(sessions):
    """인계서(HANDOFF.md)를 쓰기 전에 고친 파일 수(안 썼으면 세션 전체)별로 인계서를 쓴 비율 — 기본 문턱 3을 정한 방법.
    여기서는 대화형 세션만 센다(usage_week 필터). 기본값의 세션 94개 측정은 실험·SDK 세션까지 센 분모라 값이 다를 수 있다."""
    rows, zero, names = [], 0, collections.Counter()
    for s in sessions:
        before, wrote = set(), False
        for fp in hc.edit_paths(s["file"]):
            if HANDOFF_NAME.match(os.path.basename(fp)):
                names[os.path.basename(fp)] += 1
            if hc.is_handoff(fp):
                wrote = True
            elif not wrote:
                before.add(os.path.normpath(fp))
        if before:
            rows.append((len(before), wrote))
        else:
            zero += 1
    out = {"counted": len(rows), "excluded": zero, "excluded_reason": "인계서를 쓰기 전 고친 파일 0개 — 제안 대상이 아님",
           "names": dict(names.most_common()), "recommend": None}
    buckets = []
    for lo, hi, label in ((1, 1, "1개"), (2, 2, "2개"), (3, 3, "3개"), (4, 4, "4개"), (5, None, "5개 이상")):
        b = [w for k, w in rows if k >= lo and (hi is None or k <= hi)]
        buckets.append({"files": label, "sessions": len(b), "wrote": sum(b)})
    out["buckets"] = buckets
    gaps = {}
    for n in range(2, 7):
        low = [w for k, w in rows if k < n]
        high = [w for k, w in rows if k >= n]
        if len(low) >= 3 and len(high) >= 3:
            gaps[n] = sum(high) / len(high) - sum(low) / len(low)
    if len(rows) < MIN_SESSIONS:
        out["reason"] = f"센 세션 {len(rows)}개 — {MIN_SESSIONS}개 미만이라 기본값 {DEFAULT_NUDGE} 유지"
    elif not any(w for _, w in rows):
        out["reason"] = f"인계서를 쓴 세션이 0개라 경계를 못 정한다 — 기본값 {DEFAULT_NUDGE} 유지"
    elif not gaps:
        out["reason"] = f"양쪽(문턱 미만·이상)에 세션이 3개씩 모이는 문턱이 없다 — 기본값 {DEFAULT_NUDGE} 유지"
    else:
        best = max(gaps, key=gaps.get)
        # ponytail: 경계 하나만 본다. 문턱 이상에서 인계서를 10%p 이상 더 쓰고, 그 차이가 기본값 3의 차이보다 10%p 이상 클 때만 바꾼다
        # (잡음으로 문턱이 흔들리지 않게). 기본값 3 쪽에 세션이 3개씩 안 모여 차이를 못 셀 때는 -inf로 쳐서 최선 문턱을 권한다
        if gaps[best] < NUDGE_MARGIN:
            out["reason"] = (f"고친 파일 수와 인계서 작성 사이에 뚜렷한 경계가 없다(가장 큰 차이 {gaps[best] * 100:+.0f}%p) — "
                             f"기본값 {DEFAULT_NUDGE} 유지")
        elif best != DEFAULT_NUDGE and gaps[best] - gaps.get(DEFAULT_NUDGE, float("-inf")) >= NUDGE_MARGIN:
            out["recommend"] = str(best)
            out["reason"] = f"{best}개를 경계로 인계서 작성 비율 차이가 가장 크다({gaps[best] * 100:+.0f}%p)"
        else:
            out["reason"] = f"기본값 {DEFAULT_NUDGE}이 이미 경계에 가깝다({gaps.get(DEFAULT_NUDGE, gaps[best]) * 100:+.0f}%p) — 유지"
    return out


def phrases(prompt):
    """첫 프롬프트 앞 20단어의 한 단어·두 단어 묶음. 흔한 말·한 글자·숫자는 뺀다."""
    # ponytail: 조사를 떼지 않는다('계속해'와 '계속'을 따로 센다). 앞 20단어만 본다(긴 프롬프트의 본문이 후보를 덮지 않게)
    ws = [w.lower() for w in WORD.findall(prompt)[:20]]
    ok = [w if len(w) >= 2 and not w.isdigit() and w not in rules.GENERIC_WORDS else None for w in ws]
    out = {w for w in ok if w}
    out |= {f"{a} {b}" for a, b in zip(ok, ok[1:]) if a and b}
    return out


def triggers(sessions, root):
    """에이전트가 처음 5호출 안에 HANDOFF.md를 읽었는데 지금 트리거가 첫 프롬프트에 안 맞은 세션들의 자주 나온 말.
    후보마다 그 밖의 사람 프롬프트 중 몇 개에 걸리는지도 센다 — 훅은 모든 프롬프트를 대소문자 무시 부분 문자열로 보므로
    그만큼 인계서가 더 들어간다(그중 일부는 맞는 주입일 수 있다 — 상한)."""
    read = [s for s in sessions if s["reread"] and not rules.trigger_words(root, s["prompt"])]
    hit = collections.Counter()
    for s in read:
        hit.update(phrases(s["prompt"]))
    rid = {id(s) for s in read}
    others = [p.casefold() for s in sessions for i, p in enumerate(s["prompts"]) if not (i == 0 and id(s) in rid)]
    fires = {p: sum(p in q for q in others) for p, n in hit.items() if n >= 2}
    cands = sorted(fires, key=lambda p: (-hit[p], fires[p], p))[:10]
    return {"sessions_read_untriggered": len(read), "other_prompts": len(others),
            "sessions_not_read": sum(1 for s in sessions if not s["reread"] and not s["injected"]),  # 훅이 이미 넣은 세션은 "안 읽음"이 아니다
            "candidates": [{"phrase": p, "read": hit[p], "other_prompts": fires[p]} for p in cands]}


# ── 저장소 ────────────────────────────────────────────────────────────

def other_projects(root):
    """~/.claude/projects 아래 폴더마다 세션 하나의 cwd 끝 이름. 이 저장소는 뺀다."""
    names = set()
    for d in glob.glob(os.path.expanduser("~/.claude/projects/*/")):
        for f in glob.glob(os.path.join(d, "*.jsonl"))[:3]:
            cwd = None
            try:
                with open(f, encoding="utf-8", errors="ignore") as fh:
                    for i, line in enumerate(fh):
                        if i > 50: break
                        try: rec = json.loads(line)
                        except ValueError: continue
                        if isinstance(rec, dict) and isinstance(rec.get("cwd"), str):
                            cwd = rec["cwd"]; break
            except OSError:
                continue
            if cwd:
                if config.repo_key(cwd) != root and not usage_week.experimental(cwd):  # 이 저장소 하위 폴더에서 연 세션도 같은 저장소
                    names.add(os.path.basename(cwd.rstrip("/")))
                break
    return names


def private_candidates(root):
    """개인 자료 목록 후보. 사람이 고른다 — 스캐너는 제안만."""
    out, notes = [], []

    def files_with(term):
        r = git(root, "grep", "-I", "-i", "-F", "-l", "--untracked", "-e", term)
        return None if r is None else len(r.splitlines())

    log = git(root, "log", "--format=%an%x00%ae%x00%cn%x00%ce")
    seen = set()
    if log is None and git(root, "rev-parse", "--git-dir") is not None:
        notes.append("커밋이 아직 없어 git 작성자를 못 셈")
    elif log is None:
        notes.append("git 저장소가 아니거나 git이 없어 작성자·추적 파일을 못 셈")
    else:
        for v in sorted({x.strip() for x in log.replace("\n", "\0").split("\0") if x.strip()}):
            seen.add(v.lower()); out.append({"term": v, "source": "git 작성자·이메일", "files": files_with(v)})
    try:
        user = getpass.getuser()
    except Exception:
        user = None
        notes.append("OS 사용자 이름을 못 읽음")
    if user and user.lower() not in seen:
        seen.add(user.lower()); out.append({"term": user, "source": "OS 사용자 이름", "files": files_with(user)})
    proj = other_projects(root)
    if not os.path.isdir(os.path.expanduser("~/.claude/projects")):
        notes.append("~/.claude/projects가 없어 다른 프로젝트 이름을 못 셈")
    own = os.path.basename(root).lower()
    shown = 0
    for name in sorted(proj):
        if len(name) < 3 or name.lower() in seen or name.lower() == own or name.lower() in rules.GENERIC_WORDS:
            continue
        n = files_with(name)
        if n:
            seen.add(name.lower()); shown += 1
            out.append({"term": name, "source": "다른 프로젝트 이름", "files": n})
    notes.append(f"다른 프로젝트 {len(proj)}개 이름 중 이 저장소 파일에 나오는 것 {shown}개")
    found = git(root, "grep", "-I", "-h", "-o", "-E", "--untracked", "-e", EMAIL)
    if found is not None:
        for e, n in collections.Counter(found.split()).most_common():
            if e.lower() not in seen and not PLACEHOLDER.search(e):
                seen.add(e.lower()); out.append({"term": e, "source": "파일 속 이메일", "files": files_with(e)})
    return {"candidates": out, "notes": notes}


def repo_advice(root):
    tips = []
    if git(root, "rev-parse", "--git-dir") is None:
        return ["git 저장소가 아니다 — 인계서 승격 검토(/promote)와 개념 지도 신선도(/drift)가 동작하지 않는다"]
    has_handoff = os.path.isfile(os.path.join(root, "HANDOFF.md"))
    tracked = bool((git(root, "ls-files", "HANDOFF.md") or "").strip())
    if has_handoff and not tracked:
        tips.append("HANDOFF.md가 git에 추적되지 않는다 — `git add HANDOFF.md` 하지 않으면 승격 검토가 불가능하다")
    elif not has_handoff:
        tips.append("HANDOFF.md가 아직 없다 — 첫 작업 덩어리가 끝나면 '핸드오프 작성해줘'")
    else:
        tips.append("HANDOFF.md 추적됨")
    tips.append("DECISIONS.md 있음" if os.path.isfile(os.path.join(root, "DECISIONS.md"))
                else "DECISIONS.md가 없다 — 결정이 인계서에만 살다가 사라질 수 있다. 결정이 나오면 /decision으로 시작한다")
    if rules.concept_path(root)[0]:
        tips.append("CONCEPTS.md 있음")
    else:
        commits = (git(root, "rev-list", "--count", "HEAD") or "0").strip() or "0"
        nfiles = len((git(root, "ls-files") or "").splitlines())
        # ponytail: 개념 지도를 권할 크기 기준(커밋 50·파일 30)은 경험칙이다 — 측정한 값이 아니다
        big = int(commits) >= 50 and nfiles >= 30 if commits.isdigit() else False
        tips.append(f"CONCEPTS.md 없음 — 커밋 {commits}개·추적 파일 {nfiles}개. "
                    + ("개념 지도를 시작할 만하다(driftmap 스킬, 경험칙 기준 커밋 50·파일 30)" if big
                       else "아직 작아 개념 지도는 미뤄도 된다(경험칙 기준 커밋 50·파일 30)"))
    return tips


def scan(root):
    sessions, skipped, nfiles = load_sessions(root)
    current = {k: config.get(k, root, None) for k in config.SCALAR_KEYS}
    return {
        "repo": root, "min_sessions": MIN_SESSIONS,
        "config": {"path": config.path(), "status": config.status(root),
                   "current": {k: v for k, v in current.items() if v is not None}},
        "sessions": {"files": nfiles, "usable": len(sessions), "excluded": skipped},
        "codex": CODEX_NOTE,
        "growth": growth(sessions),
        "nudge": nudge(sessions),
        "triggers": triggers(sessions, root),
        "private_terms": private_candidates(root),
        "advice": repo_advice(root),
    }


def render(r):
    s, g, n, t, p = r["sessions"], r["growth"], r["nudge"], r["triggers"], r["private_terms"]
    ex = s["excluded"]
    cur = r["config"]["current"]
    now = lambda k, d: f" (지금 적용 값 {cur[k]} — 설정 파일·환경변수에서. 그대로 둔다)" if k in cur else f" (지금 적용 값 {d} — 코드 기본값)"
    L = [f"[baton-setup] {r['repo']} — 읽기만 했다. 아무것도 바꾸지 않았다.", ""]
    L += ["설정"] + [f"  {x}" for x in r["config"]["status"]] + [""]
    L.append(f"세션 기록: 이 저장소 폴더의 세션 파일 {s['files']}개 → 쓸 수 있는 세션 {s['usable']}개")
    L.append(f"  제외: 중복 사본 {ex['duplicate']} · 호출/사람 프롬프트 없음 {ex['empty']} · 실험·임시 폴더 {ex['experimental']} · "
             f"claude -p·SDK {ex['non_cli']}")
    L.append(f"  {r['codex']}")
    if not s["files"]:
        L.append("  이 저장소 폴더에서 연 Claude Code 세션 기록을 못 찾았다 — 0건이 아니라 못 셈"
                 "(다른 폴더에서 열었거나, 기록이 지워졌거나, ~/.claude/projects가 없다)")
    if s["usable"] < r["min_sessions"]:
        L.append(f"  표본 {s['usable']}개 — {r['min_sessions']}개 미만이라 문턱은 기본값을 권한다(몇 세션의 우연에 흔들린다)")
    L += ["", f"1) 세션 끊기 알림 문턱 BATON_SPLIT_RATIOS (기본 {DEFAULT_RATIOS})",
          f"  센 세션 {g['counted']}개 / 못 센 {g['uncounted']}개({g['uncounted_reason']})"]
    if g.get("quartiles"):
        q = g["quartiles"]
        L.append(f"  최대 맥락 ÷ 첫 호출 맥락: 사분위 {q[0]:g} · 중앙 {q[1]:g} · {q[2]:g}배")
        L += [f"    {c['ratio']:g}배 — 닿는 세션 {pct(c['reach'])} · 닿은 뒤 남은 비용 {pct(c['cost_after'])} · "
              f"재계산 절감(추정 상한) {pct(c['saving'])}" for c in g["candidates"]]
    L.append(f"  제안: {g['recommend'] or '바꾸지 않음'} — {g['reason']}{now('BATON_SPLIT_RATIOS', DEFAULT_RATIOS)}")
    L += ["", f"2) 인계서 제안 문턱 BATON_HANDOFF_NUDGE_FILES (기본 {DEFAULT_NUDGE})",
          f"  센 세션 {n['counted']}개 / 제외 {n['excluded']}개({n['excluded_reason']})"]
    L += [f"    고친 파일 {b['files']}: 세션 {b['sessions']} · 인계서 씀 {b['wrote']}"
          + (f" ({pct(b['wrote'] / b['sessions'])})" if b["sessions"] else "") for b in n["buckets"]]
    L.append(f"  제안: {n['recommend'] or '바꾸지 않음'} — {n['reason']}{now('BATON_HANDOFF_NUDGE_FILES', DEFAULT_NUDGE)}")
    L += ["", "3) 실제로 쓴 인계서 파일 이름(설정 아님, 보고만)"]
    if n["names"]:
        L += [f"    {k}: 편집 {v}회" + ("" if k == "HANDOFF.md" else " — 주입 훅은 HANDOFF.md만 읽는다") for k, v in n["names"].items()]
    else:
        L.append(f"    세션 {s['usable']}개에서 HANDOFF*.md 편집 0회(이 저장소 폴더의 Claude Code 세션만 셌다)")
    L += ["", "4) 인계 트리거 추가 말 후보 BATON_HANDOFF_TRIGGERS_EXTRA",
          f"  처음 5호출 안에 HANDOFF.md를 읽었는데 지금 트리거가 안 맞은 세션 {t['sessions_read_untriggered']}개 · "
          f"인계서를 안 읽고 주입도 없던 세션 {t['sessions_not_read']}개 · 그 밖의 사람 프롬프트 {t['other_prompts']}개"]
    if t["candidates"]:
        L += [f"    '{c['phrase']}' — 읽은 세션 첫 프롬프트 {c['read']}개 · 그 밖의 프롬프트 {c['other_prompts']}개에도 걸린다"
              f"(그만큼 인계서가 더 들어간다 — 상한)" for c in t["candidates"]]
    elif t["sessions_read_untriggered"] < 2:
        L.append("    후보 없음이 아니라 표본 부족 — 그런 세션이 2개 이상이어야 반복된 말을 셀 수 있다")
    else:
        L.append("    두 세션 이상에서 반복된 말이 없다")
    L += ["", "5) 개인 자료 목록 후보 private_terms (고른 것만 인계서 검사가 막는다)"]
    L += [f"    {c['term']} — {c['source']} · 이 저장소 파일 {'못 셈' if c['files'] is None else str(c['files']) + '개'}에 나옴"
          for c in p["candidates"]] or ["    후보 0개"]
    L += [f"    ({x})" for x in p["notes"]]
    L += ["", "6) 저장소 권고(보고만)"] + [f"  - {x}" for x in r["advice"]]
    return "\n".join(L)


# ── 적용 ──────────────────────────────────────────────────────────────

def apply(argv):
    ap = argparse.ArgumentParser(prog="setup_scan.py apply", description="사용자가 고른 값만 설정 파일에 쓴다")
    ap.add_argument("repo", nargs="?")
    ap.add_argument("--global", dest="is_global", action="store_true", help="전역 절에 쓴다(기본: 이 저장소 절)")
    ap.add_argument("--set", action="append", default=[], metavar="키=값")
    ap.add_argument("--unset", action="append", default=[], metavar="키")
    ap.add_argument("--private-term", action="append", default=[], metavar="단어")
    ap.add_argument("--private-terms-file", metavar="경로", help="한 줄에 하나. '-'면 표준 입력 — 단어가 명령줄·세션 기록에 안 남는다")
    ap.add_argument("--remove-term", action="append", default=[], metavar="단어")
    ap.add_argument("--remove-terms-file", metavar="경로", help="뺄 단어 파일(한 줄에 하나, '-'면 표준 입력)")
    ap.add_argument("--trigger", action="append", default=[], metavar="말")
    ap.add_argument("--remove-trigger", action="append", default=[], metavar="말")
    a = ap.parse_args(argv)
    sets = {}
    for kv in a.set:
        k, sep, v = kv.partition("=")
        if not sep or k not in config.SCALAR_KEYS:
            ap.error(f"모르는 설정: {k or kv} — 쓸 수 있는 키: {', '.join(config.SCALAR_KEYS)}")
        why = config.invalid(k, v)
        if why:
            ap.error(f"{k}: {why}")
        sets[k] = os.path.expanduser(v.strip()) if k == "BATON_LOG" else v.strip()  # "~/…"를 펼쳐 둔다
    for k in a.unset:
        if k not in config.SCALAR_KEYS + config.LIST_KEYS:
            ap.error(f"모르는 키: {k}")
    def read_terms(path, flag):
        """단어 파일(또는 '-' 표준 입력)의 줄들. BOM은 뗀다. 못 읽으면 단어를 출력하지 않고 멈춘다."""
        if not path:
            return []
        try:
            with (sys.stdin if path == "-" else open(path, encoding="utf-8-sig")) as f:
                return f.read().lstrip("\ufeff").splitlines()
        except UnicodeDecodeError:
            ap.error(f"{flag}: UTF-8로 읽히지 않는다 — UTF-8로 저장한 뒤 다시 한다")
        except OSError as e:
            ap.error(f"{flag}을 못 읽었다: {e.strerror}")

    lists = {"add": {"private_terms": a.private_term + read_terms(a.private_terms_file, "--private-terms-file"),
                     "BATON_HANDOFF_TRIGGERS_EXTRA": a.trigger},
             "remove": {"private_terms": a.remove_term + read_terms(a.remove_terms_file, "--remove-terms-file"),
                        "BATON_HANDOFF_TRIGGERS_EXTRA": a.remove_trigger}}
    for op in lists:
        for k in lists[op]:
            items = [x.strip() for x in lists[op][k] if x.strip()]
            if op == "add" and any(config.invalid(k, x) for x in items):
                ap.error(f"{'개인 자료 단어' if k == 'private_terms' else '트리거 말'}: {config.invalid(k, 'x')}")  # 단어는 다시 출력하지 않는다
            lists[op][k] = items
        lists[op] = {k: v for k, v in lists[op].items() if v}
    add, remove = lists["add"], lists["remove"]
    repo = None if a.is_global else config.repo_key(a.repo or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    if repo and any(k in config.GLOBAL_ONLY for k in list(sets) + a.unset):
        ap.error(f"{', '.join(config.GLOBAL_ONLY)}는 전역에만 둔다 — --global을 붙인다")
    if not (sets or a.unset or add or remove):
        ap.error("바꿀 것이 없다")
    removed = {}
    try:
        p = config.update(repo, sets, a.unset, add, remove, removed)
    except (ValueError, OSError) as e:
        sys.exit(f"[baton-setup] 쓰지 못했다: {e}")
    where = "전역 절" if repo is None else f"저장소 절({repo})"
    print(f"[baton-setup] {p}의 {where}에 썼다(파일 600).")
    for k, v in sets.items():
        print(f"  {k}={v}")
    for k in a.unset:
        print(f"  {k} 지움 — 이제 전역 절·코드 기본값을 따른다")
    if "private_terms" in add:
        print(f"  개인 자료 목록 단어 {len(add['private_terms'])}개 추가(이 출력에는 단어를 적지 않는다)")
    if "BATON_HANDOFF_TRIGGERS_EXTRA" in add:
        print(f"  인계 트리거 추가 말 추가: {', '.join(add['BATON_HANDOFF_TRIGGERS_EXTRA'])}")
    data = config.load() or {}
    for k, items in remove.items():
        name = "개인 자료 목록 단어" if k == "private_terms" else "인계 트리거 추가 말"
        print(f"  {name} {len(items)}개 중 {removed.get(k, 0)}개를 {where}에서 뺌"
              + (" — 나머지는 이 절에 없었다" if removed.get(k, 0) < len(items) else ""))
        # 다른 절에 남아 있으면 여전히 적용된다 — 저장소 절에서 뺐으면 전역 절, 전역에서 뺐으면 저장소 절들을 본다
        others = [data.get("global")] if repo else list((data.get("repos") or {}).values())
        drop = {x.casefold() for x in items}
        left = sum(1 for sec in others if isinstance(sec, dict) and isinstance(sec.get(k), list)
                   and any(isinstance(x, str) and x.strip().casefold() in drop for x in sec[k]))
        if left:
            print(f"  주의: 뺀 것 일부가 다른 {'전역 절' if repo else f'저장소 절 {left}곳'}에 남아 여전히 적용된다"
                  f"({'--global을 붙여' if repo else '그 저장소에서'} 다시 뺀다)")
    print("  되돌리기: apply --unset <키> · --remove-terms-file <경로> · --remove-trigger <말>(전역이면 --global). "
          "같은 이름의 환경변수가 설정 파일보다 우선한다")


def main(argv):
    if argv and argv[0] == "apply":
        return apply(argv[1:])
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("repo", nargs="?")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    r = scan(config.repo_key(a.repo or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()))
    print(json.dumps(r, ensure_ascii=False, indent=2) if a.json else render(r))


if __name__ == "__main__":
    main(sys.argv[1:])
