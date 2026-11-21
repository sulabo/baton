#!/usr/bin/env python3
"""온톨로지·개념 그래프 오프라인 평가 — docs/research/ONTOLOGY_DESIGN.md P1·E1·E2 (비용 0, 동작 변경 없음).

정답은 행동이다(10-04 소유자 결정): 세션이 첫 파일을 고친 뒤 이어서 고친 파일(E1), 첫 프롬프트 뒤 고친 파일이 속한 개념(E2).
누설 방지: 세션마다 그 세션 시작 이전 자료만 쓴다 — 그래프는 시작 전 커밋, 별칭은 시작 전 세션의 프롬프트,
개념 지도는 시작 시점 커밋의 CONCEPTS.md.

  python3 observer/research/graph_eval.py prepare   # 세션↔저장소 대응표·제외 목록·남는 시험 세션 수(평가 전 고정)
  python3 observer/research/graph_eval.py e1        # 파일 그래프 recall@5 대 기준선 둘 + 개념 간선 수
  python3 observer/research/graph_eval.py e2        # 제목 매처 대 별칭 포함 매처
  … --label read                                    # 3-2절 새 실험: 정답 = 읽은 기존 파일(Read 도구, 시작 전 이력에 있던 것)

산출물은 저장소 밖 ~/.cache/baton/eval/ (실제 경로가 들어가므로). 화면에는 저장소 별칭(r1, r2 …)만 낸다.
합격선은 설계안 3절 그대로 — 여기서 바꾸지 않는다.
"""
import argparse, collections, glob, hashlib, json, os, random, statistics, subprocess, sys, unicodedata
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "lib"))
sys.path.insert(0, HERE)
import compiler, concepts, rules, setup_scan, usage_week


_CACHE = compiler.cache_dir()  # 조립기와 같은 위치 규칙(상대 XDG_CACHE_HOME 무시) — 정할 수 없으면 None
OUT = os.path.join(os.path.dirname(_CACHE), "eval") if _CACHE else None


def out_dir():
    """산출물 폴더(실제 저장소 경로가 들어가므로 700). 정할 수 없으면 멈춘다 — 작업 폴더 안에 만들지 않는다."""
    if not OUT:
        sys.exit("캐시 폴더를 정할 수 없다(절대 경로인 XDG_CACHE_HOME·HOME이 없음)")
    os.makedirs(OUT, mode=0o700, exist_ok=True)
    return OUT

# ── 평가 전에 고정한 값 (설계안 2·3절) ─────────────────────────────────
HUB_NAMES = {"HANDOFF.md", "DECISIONS.md", "CONCEPTS.md", "README.md", "AGENTS.md", "CLAUDE.md", ".gitignore",
             "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Cargo.lock", "uv.lock", "Gemfile.lock"}
MAX_COMMIT_FILES = 20      # 이보다 큰 커밋은 학습에서 뺀다
MIN_PAIR_COMMITS = 3       # 서로 다른 커밋 3회 이상 함께 바뀐 쌍만 간선
TOP_K = 5                  # 노드당 이웃 수 = 예측 수
EDIT_TOOLS = {"Write", "Edit", "MultiEdit"}
MIN_REPO_COMMITS = 30      # 유효 커밋(파일 2~20개)이 이보다 적은 저장소는 사전 제외
COMMIT_CUTOFF = "2026-09-20"
ALIAS_MIN_DAYS = 3         # promote.sh와 같은 문턱
MIN_SESSIONS = 20          # 미만이면 "못 셌다"
PASS_DIFF = 0.10
BOOT = 10000


def is_hub(path):
    return os.path.basename(path) in HUB_NAMES


# ── git ────────────────────────────────────────────────────────────────

def git(root, *args):
    return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, errors="ignore").stdout


def nfc(path):
    """macOS git은 한글 경로를 분해형(NFD)으로, 세션 기록은 조합형(NFC)으로 준다 — 맞추지 않으면 전부 저장소 밖으로 잡힌다."""
    return unicodedata.normalize("NFC", path)


def repo_root(cwd):
    out = git(cwd, "rev-parse", "--show-toplevel").strip() if cwd and os.path.isdir(cwd) else ""
    return nfc(out) if out else None


def repo_commits(root):
    """[(커밋 시각 epoch, 해시, [파일])] 오래된 순. 병합 커밋은 뺀다."""
    out, cur = [], None
    for ln in git(root, "-c", "core.quotepath=false", "log", "--all", "--no-merges", "--reverse", "--format=%x00%ct %H", "--name-only").splitlines():
        if ln.startswith("\x00"):
            ct, h = ln[1:].split(" ", 1)
            cur = (int(ct), h, []); out.append(cur)
        elif ln.strip() and cur:
            cur[2].append(nfc(ln.strip()))
    return out


def valid(files):
    return 2 <= len(files) <= MAX_COMMIT_FILES


# ── E1: 파일 그래프 ────────────────────────────────────────────────────

def build_graph(commits, before):
    """before(epoch) 이전 커밋으로 {파일: [이웃 상위 K]}. 거대 커밋·허브 파일 제외, 쌍은 서로 다른 커밋 3회 이상."""
    pair, last = collections.Counter(), {}
    for ct, _, files in commits:
        if ct >= before or len(files) > MAX_COMMIT_FILES:
            continue
        fs = sorted({f for f in files if not is_hub(f)})
        for i, a in enumerate(fs):
            for b in fs[i + 1:]:
                pair[a, b] += 1; last[a, b] = ct
    nb = collections.defaultdict(list)
    for (a, b), n in pair.items():
        if n >= MIN_PAIR_COMMITS:
            nb[a].append((n, last[a, b], b)); nb[b].append((n, last[a, b], a))
    return {f: [x for _, _, x in sorted(v, key=lambda t: (-t[0], -t[1], t[2]))[:TOP_K]] for f, v in nb.items()}


def last_touch(commits, before):
    """before 이전에 파일마다 마지막으로 바뀐 시각(허브 제외)."""
    out = {}
    for ct, _, files in commits:
        if ct < before:
            for f in files:
                if not is_hub(f): out[f] = ct
    return out


def recency(touch, seed, same_dir):
    d = os.path.dirname(seed)
    cands = [f for f in touch if f != seed and (not same_dir or os.path.dirname(f) == d)]
    return sorted(cands, key=lambda f: (-touch[f], f))[:TOP_K]


def recall(pred, truth):
    return len(set(pred) & set(truth)) / len(truth) if truth else None


def seed_truth(edits):
    """(씨앗 = 처음 고친 허브 아닌 파일, 정답 = 그 뒤 고친 다른 파일들) 또는 None. prepare의 후보 수도 이것으로 센다."""
    seq = list(dict.fromkeys(f for f in edits if not is_hub(f)))
    return (seq[0], seq[1:]) if len(seq) >= 2 else None


def hist_status(commits, start, files):
    """파일마다 처음 커밋된 때가 세션 시작 전/후/없음인지 센다 — "새 파일이라 못 맞힘" 진단의 근거."""
    first = {}
    for ct, _, fs in commits:
        for f in fs:
            first.setdefault(f, ct)
    c = collections.Counter("never" if f not in first else "before" if first[f] < start else "after" for f in files)
    return {k: c.get(k, 0) for k in ("before", "after", "never")}


def e1_case(commits, start, edits):
    """시험 세션 하나 → {graph, dir, repo} recall@5. 씨앗·정답이 없으면 None."""
    st = seed_truth(edits)
    if not st:
        return None
    seed, truth = st
    g, touch = build_graph(commits, start), last_touch(commits, start)
    return {"graph": recall(g.get(seed, []), truth), "dir": recall(recency(touch, seed, True), truth),
            "repo": recall(recency(touch, seed, False), truth), "n_truth": len(truth), "has_nb": seed in g,
            "hist": hist_status(commits, start, [seed, *truth])}


def concept_edges(graph, cmap):
    """파일 간선에서 개념 간선 파생. 두 개 이상의 개념에 속한 파일은 아예 뺀다(공유 파일이 간접 근거가 되지 않게)."""
    def sole(f):  # 폴더로 적힌 개념도 소속으로 센다(touched와 같은 규칙)
        cs = touched(cmap, [f])
        return next(iter(cs)) if len(cs) == 1 else None
    edges = set()
    for a, nbs in graph.items():
        for b in nbs:
            ca, cb = sole(a), sole(b)
            if ca and cb and ca != cb:
                edges.add(tuple(sorted((ca, cb))))
    return edges


# ── E2: 개념 매처 ─────────────────────────────────────────────────────

def parse_map(text):
    """CONCEPTS.md 본문 → (sections[(번호, 이름, 본문)], {번호: [파일 경로]}). '없음' 파일은 뺀다."""
    secs = list(concepts.walk(text.splitlines()))
    files = {}
    for num, _, body in secs:
        meta = next((ln for ln in body if concepts.META.match(ln)), "")
        raw = concepts.field(meta, "파일")
        files[num] = [p.strip().strip("`") for p in raw.split(",") if p.strip().strip("`") and not p.strip().startswith("없음")]
    return secs, files


def touched(cmap, edits):
    """세션이 고친 파일이 속한 개념 번호. 경로가 같거나 그 폴더 아래면 속한다."""
    out = set()
    for c, files in cmap.items():
        for f in files:
            base = f.rstrip("/")
            if any(e == base or e.startswith(base + "/") for e in edits):
                out.add(c); break
    return out


def phrases_v1(prompt):
    """10-04 사전 등록 때의 구절 정의(rules.phrases의 10-07 이전판) — E2 재측정이 같은 방법을 쓰도록 고정한다.
    10-07판은 두 단어 묶음을 원문에서 공백 하나로 붙어 있던 것만 만든다(설계안 8절)."""
    ws = [w.lower() for w in rules.WORD.findall(prompt)[:20]]
    ok = [w if len(w) >= 2 and not w.isdigit() and w not in rules.GENERIC_WORDS else None for w in ws]
    return {w for w in ok if w} | {f"{a} {b}" for a, b in zip(ok, ok[1:]) if a and b}


def mine_aliases(history, cmap, title_hit):
    """이전 세션들 [(날짜, 첫 프롬프트, 고친 파일)] → {구절: 개념}. 서로 다른 날 3일 이상 그 개념을 고치기 전에 나왔고,
    다른 개념만 고친(또는 개념 밖) 세션 프롬프트에 걸린 횟수가 맞은 횟수 이하인 구절. 제목 단어로 이미 맞는 것은 뺀다."""
    days, fires = collections.defaultdict(set), collections.Counter()
    for day, prompt, edits in history:
        cs = touched(cmap, edits)
        for ph in phrases_v1(prompt):
            for c in cs:
                days[ph, c].add(day)
    out = {}
    for (ph, c), ds in days.items():
        if len(ds) < ALIAS_MIN_DAYS or c in title_hit(ph):
            continue
        hits = sum(1 for _, p, e in history if ph in p.casefold() and c in touched(cmap, e))
        miss = sum(1 for _, p, e in history if ph in p.casefold() and c not in touched(cmap, e))
        if miss <= hits and (ph not in out or hits > out[ph][1]):
            out[ph] = (c, hits)
    return {ph: c for ph, (c, _) in out.items()}


def e2_case(secs, cmap, history, prompt, edits):
    truth = touched(cmap, edits)
    if not truth:
        return None
    title = lambda text: {n for n, _ in rules.concept_hits(secs, text)}
    base = title(prompt)
    aliases = mine_aliases(history, cmap, title)
    alias = base | {c for ph, c in aliases.items() if ph in prompt.casefold()}
    return {"truth": sorted(truth), "base": sorted(base), "alias": sorted(alias), "n_aliases": len(aliases)}


# ── 통계 ───────────────────────────────────────────────────────────────

def boot_ci(groups, diff_of, reps=BOOT, seed=0):
    """groups: [[세션 결과…]…]를 단위로 다시 뽑는다. 세션 단위면 원소 하나짜리 묶음들. (점추정, 2.5%, 97.5%)."""
    rng = random.Random(seed)
    flat = [x for g in groups for x in g]
    point = diff_of(flat)
    vals = sorted(diff_of([x for _ in groups for x in rng.choice(groups)]) for _ in range(reps))
    return point, vals[int(reps * 0.025)], vals[int(reps * 0.975) - 1]


def verdict(n, sess_ci, repo_ci, extra_ok=True):
    if n < MIN_SESSIONS:
        return f"못 셌다(시험 세션 {n}개 < {MIN_SESSIONS})"
    ok = sess_ci[0] >= PASS_DIFF and sess_ci[1] > 0 and repo_ci[1] > 0 and extra_ok
    return "합격" if ok else ("판정 불가(구간이 0을 걸침)" if sess_ci[1] <= 0 < sess_ci[2] or repo_ci[1] <= 0 < repo_ci[2] else "불합격")


# ── 세션 수집 ─────────────────────────────────────────────────────────

def edit_paths(session_file):
    return tool_paths(session_file, EDIT_TOOLS)


def tool_paths(session_file, tools):
    """세션이 tools로 다룬 파일 경로를 시각순으로 — 메인 스레드와 서브에이전트(<세션>/subagents/*.jsonl) 모두.
    "세션이 한 일"이 정답이므로 위임한 것도 센다(첫 실행은 메인만 세어 빠졌다 — 10-04 코드 검토)."""
    files = [session_file] + sorted(glob.glob(os.path.join(session_file[:-len(".jsonl")], "subagents", "*.jsonl")))
    out = []
    for f in files:
        with open(f, encoding="utf-8", errors="ignore") as fh:
            for ln in fh:
                if '"tool_use"' not in ln:
                    continue
                try: d = json.loads(ln)
                except ValueError: continue
                m = d.get("message") if isinstance(d, dict) else None
                for b in (m.get("content") if isinstance(m, dict) and isinstance(m.get("content"), list) else []):
                    if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") in tools:
                        fp = (b.get("input") or {}).get("file_path")
                        if isinstance(fp, str): out.append((d.get("timestamp") or "", fp))
    return [p for _, p in sorted(out, key=lambda t: t[0])]


def sessions():
    """[{file, root, rel_edits, start(epoch), day, prompt}] — usage_week.collect의 거르기(sdk·임시·중복 제외) 위에서."""
    got, _ = usage_week.collect()
    roots, out = {}, []
    for s in got:
        if not s["start"]:
            continue
        cwd = s["cwd"]
        if cwd not in roots:
            roots[cwd] = repo_root(cwd)
        root = roots[cwd]
        if not root:
            continue
        def rel(paths):  # ponytail: cwd 저장소 밖 파일(다른 저장소)은 버린다
            out = []
            for p in paths:
                ap = p if os.path.isabs(p) else os.path.join(cwd, p)
                r = os.path.relpath(nfc(os.path.realpath(ap)), nfc(os.path.realpath(root)))
                if not r.startswith(".."):
                    out.append(r)
            return out
        out.append({"file": s["file"], "root": root, "edits": rel(edit_paths(s["file"])), "reads": rel(tool_paths(s["file"], {"Read"})),
                    "start": s["start"].timestamp(),
                    "day": s["start"].date().isoformat(), "prompt": s["prompt"]})
    return sorted(out, key=lambda s: s["start"])


def truth_seq(s, lab, commits):
    """정답 재료: edit = 고친 파일(3절), read = 읽은 파일 중 시작 전 이력에 있던 것(3-2절)."""
    if lab == "edit":
        return s["edits"]
    known = last_touch(commits, s["start"])
    return [f for f in s["reads"] if f in known]


def label(root):
    return "r" + hashlib.sha1(root.encode()).hexdigest()[:6]


def prepare(lab):
    ss = sessions()
    cutoff = datetime.fromisoformat(COMMIT_CUTOFF).timestamp()
    repos = {}
    for s in ss:
        repos.setdefault(s["root"], []).append(s)
    table, excluded = [], []
    for root, group in repos.items():
        commits = repo_commits(root)
        n_valid = sum(1 for ct, _, f in commits if ct < cutoff and valid(f))
        e1_n = sum(1 for s in group if seed_truth(truth_seq(s, lab, commits)))
        row = {"repo": label(root), "root": root, "sessions": len(group), "e1_candidates": e1_n, "valid_commits_before_cutoff": n_valid}
        (table if n_valid >= MIN_REPO_COMMITS else excluded).append(row)
    out_dir()
    fixed = {"made": datetime.now().astimezone().isoformat(timespec="seconds"), "label": lab, "cutoff": COMMIT_CUTOFF,
             "min_repo_commits": MIN_REPO_COMMITS, "included": table, "excluded": excluded,
             "sessions": [{"repo": label(s["root"]), "file": s["file"], "day": s["day"]} for s in ss if s["root"] in {r["root"] for r in table}]}
    with open(os.path.join(OUT, "mapping.json"), "w", encoding="utf-8") as f:
        json.dump(fixed, f, ensure_ascii=False, indent=1)
    show = lambda rows: [{k: v for k, v in r.items() if k != "root"} for r in rows]
    print(json.dumps({"included": show(table), "excluded": show(excluded),
                      "e1_test_sessions_total": sum(r["e1_candidates"] for r in table),
                      "saved": os.path.join(OUT, "mapping.json")}, ensure_ascii=False, indent=1))


def load_fixed():
    path = os.path.join(out_dir(), "mapping.json")
    if not os.path.isfile(path):
        sys.exit("먼저 prepare를 돌려 대응표를 고정한다.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run_e1(lab):
    fixed = load_fixed()
    keep = {r["root"] for r in fixed["included"]}
    by_repo, commits = collections.defaultdict(list), {}
    for s in sessions():
        if s["root"] not in keep:
            continue
        cs = commits.setdefault(s["root"], repo_commits(s["root"]))
        r = e1_case(cs, s["start"], truth_seq(s, lab, cs))
        if r: by_repo[s["root"]].append(r)
    groups = [g for g in by_repo.values() if g]
    flat = [x for g in groups for x in g]
    if not flat:
        print(json.dumps({"verdict": f"못 셌다(시험 세션 0개 — 거르기 조건 확인 필요)"}, ensure_ascii=False)); return
    mean = lambda xs, k: statistics.fmean(x[k] for x in xs)
    best = max(("dir", "repo"), key=lambda k: mean(flat, k))
    diff = lambda xs: mean(xs, "graph") - mean(xs, best)
    sess = boot_ci([[x] for x in flat], diff)
    repo = boot_ci(groups, diff)
    # 개념 간선: 지금 지도가 있는 포함 저장소에서, 전체 이력 그래프로
    cedges = {}
    for root in keep:
        path, _ = rules.concept_path(root)
        if path:
            with open(path, encoding="utf-8") as f:
                _, cmap = parse_map(f.read())
            g = build_graph(commits.get(root) or repo_commits(root), float("inf"))
            cedges[label(root)] = {"concepts": len(cmap), "edges": len(concept_edges(g, cmap))}
    edge_ok = all(v["edges"] <= 2 * v["concepts"] for v in cedges.values())
    res = {"n": len(flat), "repos": {label(r): len(g) for r, g in by_repo.items()},
           "recall@5": {k: round(mean(flat, k), 3) for k in ("graph", "dir", "repo")}, "best_baseline": best,
           "diff_session_ci": [round(v, 3) for v in sess], "diff_repo_ci": [round(v, 3) for v in repo],
           "seed_has_neighbors": sum(1 for x in flat if x["has_nb"]), "concept_edges": cedges,
           "truth_files_history": {k: sum(x["hist"][k] for x in flat) for k in ("before", "after", "never")},
           "verdict": verdict(len(flat), sess, repo, edge_ok)}
    save("e1" if lab == "edit" else f"e1-{lab}", res, flat)


def run_e2(lab):
    name = "e2" if lab == "edit" else f"e2-{lab}"
    fixed = load_fixed()
    keep = {r["root"] for r in fixed["included"]}
    by_repo, hist = collections.defaultdict(list), collections.defaultdict(list)
    commits = {}
    no_map = 0
    for s in sessions():
        if s["root"] not in keep:
            continue
        cs = commits.setdefault(s["root"], repo_commits(s["root"]))
        head = next((h for ct, h, _ in reversed(cs) if ct < s["start"]), None)
        text = None
        for rel in ("CONCEPTS.md", "docs/CONCEPTS.md"):
            if head and not text:
                text = git(s["root"], "show", f"{head}:{rel}") or None
        if text:
            secs, cmap = parse_map(text)
            r = e2_case(secs, cmap, hist[s["root"]], s["prompt"], truth_seq(s, lab, cs))
            if r: by_repo[s["root"]].append(r)
        else:
            no_map += 1
        hist[s["root"]].append((s["day"], s["prompt"], truth_seq(s, lab, cs)))
    groups = [g for g in by_repo.values() if g]
    flat = [x for g in groups for x in g]

    def rec(xs, k): return statistics.fmean(len(set(x[k]) & set(x["truth"])) / len(x["truth"]) for x in xs)
    def prec(xs, k):
        hit, n = sum(len(set(x[k]) & set(x["truth"])) for x in xs), sum(len(x[k]) for x in xs)
        return hit / n if n else None
    if not flat:
        save(name, {"n": 0, "no_map_sessions": no_map, "verdict": f"못 셌다(시험 세션 0개 < {MIN_SESSIONS})"}, flat); return
    diff = lambda xs: rec(xs, "alias") - rec(xs, "base")
    sess, repo = boot_ci([[x] for x in flat], diff), boot_ci(groups, diff)
    pb, pa = prec(flat, "base"), prec(flat, "alias")
    res = {"n": len(flat), "no_map_sessions": no_map, "repos": {label(r): len(g) for r, g in by_repo.items()},
           "recall": {"base": round(rec(flat, "base"), 3), "alias": round(rec(flat, "alias"), 3)},
           "precision": {"base": pb and round(pb, 3), "alias": pa and round(pa, 3)},
           "diff_session_ci": [round(v, 3) for v in sess], "diff_repo_ci": [round(v, 3) for v in repo],
           "verdict": verdict(len(flat), sess, repo, pb is None or (pa is not None and pa >= pb))}
    save(name, res, flat)


def save(name, res, rows):
    out_dir()
    with open(os.path.join(OUT, f"{name}.json"), "w", encoding="utf-8") as f:
        json.dump({"result": res, "rows": rows}, f, ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["prepare", "e1", "e2"])
    ap.add_argument("--label", choices=["edit", "read"], default="edit", help="정답: 고친 파일(3절) 또는 읽은 기존 파일(3-2절)")
    a = ap.parse_args()
    {"prepare": prepare, "e1": run_e1, "e2": run_e2}[a.cmd](a.label)


if __name__ == "__main__":
    main()
