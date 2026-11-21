#!/usr/bin/env python3
"""설계안 7절 — 맥락 조립기 그림자 측정. 판단 로그의 compile(shadow) 기록과 세션 기록을 이어 붙여,
"조립기가 골랐을 파일"과 "그 턴에 세션이 처음 만진 기존 파일"을 기준선(nograph·folder·handoff)과 함께 비교한다.

   compile_eval.py [--log 경로] [--since YYYY-MM-DD] [--json]

   - 잇기: 세션 id로 세션 기록(~/.claude/projects/*/<id>.jsonl)을 찾고, 프롬프트 해시(훅과 같은 sha1 앞 12자)로 사람 프롬프트를 맞춘다.
     같은 문장이 여러 번이면("계속") 기록 시각에 가장 가까운 것, 한 프롬프트는 한 기록에만. 해시가 안 맞으면(앞뒤 공백 등)
     아직 안 쓰인 프롬프트 중 기록 시각이 60초 안인 가장 가까운 것으로. 슬래시 명령(`<command-name>`)도 턴 경계로 센다.
   - 정답: 그 프롬프트부터 다음 사람 프롬프트 전까지 처음 만진 파일 중 기록된 HEAD에 있던 것(허브 제외). 서브에이전트 포함.
     후보도 같은 HEAD에 있던 파일로만 비교한다 — 커밋 안 된 파일을 한쪽(인계서·개념) 후보만 낼 수 있어 기울어지지 않게.
   - 단계마다 수를 낸다 — 0이면 어느 단계에서 0이 됐는지 보인다(0건을 "없음"으로 읽지 않는다).
"""
import argparse, glob, hashlib, json, os, random, re, statistics, subprocess, sys, unicodedata
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "measure"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "lib"))
from extract_prompts import human_text
import compiler, runlog

# ── 사전 등록한 값(설계안 7절) ─────────────────────────────────────────
MIN_TURNS, MIN_SESSIONS = 30, 5
PASS_DIFF = 0.10
BOOT = 10000
JOIN_SECONDS = 60          # 해시가 안 맞을 때 시각만으로 잇는 폭
HASH_MAX_SECONDS = 1800    # 해시가 맞아도 이보다 늦은 프롬프트는 짝이 아니다(큐 지연 감안)
SKEW = 5                   # 훅은 사용자 메시지가 기록되기 전에 돈다 — 프롬프트가 기록보다 이만큼 넘게 앞서면 짝이 아니다
NOT_HUMAN = ("This session is being continued", "Another Claude session sent", "[Request interrupted")
ARMS = ("compiler", "nograph", "folder", "handoff")
COMMAND = re.compile(r"(?:<command-message>.*?</command-message>\s*)?<command-name>\s*(/[^<\s]+)\s*</command-name>", re.S)
COMMAND_ARGS = re.compile(r"<command-args>(.*?)</command-args>", re.S)
SRC_NAMES = {"p": "프롬프트 개념", "h": "인계서", "f": "작업 파일 개념", "n": "이웃 개념", "d": "같은 폴더 최근순"}


def sha(text):
    return hashlib.sha1(text.encode("utf-8", "surrogatepass")).hexdigest()[:12]


def when(ts):
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).timestamp()
    except ValueError:
        return None


def nfc(s):
    return unicodedata.normalize("NFC", s)


def log_path(arg):
    if arg:
        return os.path.expanduser(arg)
    return os.path.join(runlog.cache_dir() or os.path.expanduser("~/.cache/baton"), "runs.jsonl")  # 훅이 쓰는 자리(lib/runlog.py)


def records(path, since):
    """(단계 수, mode=shadow·오류 없는 compile 기록). 단계 수는 프롬프트 기록·조립기 꺼짐·켬(on)·오류를 따로 센다."""
    n = {"prompt_records": 0, "compile_off": 0, "compile_on": 0, "compile_error": 0}
    out = []
    for p in (path + ".1", path):  # 돌린 로그도 본다
        try:
            fh = open(p, encoding="utf-8", errors="ignore")
        except OSError:
            continue
        with fh:
            for ln in fh:
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                if not isinstance(r, dict) or r.get("event") != "prompt":
                    continue
                if since and str(r.get("ts", ""))[:10] < since:
                    continue
                n["prompt_records"] += 1
                c = r.get("compile")
                if not isinstance(c, dict):
                    n["compile_off"] += 1
                elif c.get("error"):
                    n["compile_error"] += 1
                elif c.get("mode") == "on":
                    n["compile_on"] += 1
                elif c.get("mode") == "shadow" and r.get("session_id"):
                    out.append(r)
    return n, out


def transcript(session_id):
    hits = glob.glob(os.path.expanduser(f"~/.claude/projects/*/{glob.escape(session_id)}.jsonl"))
    return hits[0] if hits else None


def read_session(path):
    """(사람 프롬프트 [(시각, 해시)], 만진 파일 [(시각, 절대경로)]) — 메인과 서브에이전트."""
    prompts, touches = [], []
    files = [path] + sorted(glob.glob(os.path.join(path[:-len(".jsonl")], "subagents", "*.jsonl")))
    for i, f in enumerate(files):
        with open(f, encoding="utf-8", errors="ignore") as fh:
            for ln in fh:
                try:
                    d = json.loads(ln)
                except ValueError:
                    continue
                if not isinstance(d, dict):
                    continue
                t = when(d.get("timestamp"))
                if t is None:
                    continue
                if i == 0 and d.get("type") == "user" and not d.get("isMeta") and not d.get("isCompactSummary") \
                        and not d.get("isSidechain"):
                    text = human_text((d.get("message") or {}).get("content"))
                    cmd = COMMAND.match((text or "").lstrip()) if (text or "").lstrip().startswith("<command-") else None
                    if cmd:  # 슬래시 명령 — 훅은 "/이름 인자"를 받는다
                        args = COMMAND_ARGS.search(text)
                        typed = (cmd.group(1) + " " + (args.group(1).strip() if args else "")).strip()
                        prompts.append((t, {sha(typed), sha(cmd.group(1))}))
                    elif text and not text.startswith("<") and not text.startswith(NOT_HUMAN):
                        prompts.append((t, {sha(text), sha(text + "\n")}))
                m = d.get("message") if d.get("type") == "assistant" else None
                for b in (m.get("content") if isinstance(m, dict) and isinstance(m.get("content"), list) else []):
                    if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") in compiler.TOUCH_TOOLS:
                        inp = b.get("input") if isinstance(b.get("input"), dict) else {}
                        fp = inp.get("file_path") or inp.get("notebook_path")
                        if isinstance(fp, str):
                            touches.append((t, fp))
    prompts.sort(key=lambda x: x[0])
    touches.sort(key=lambda x: x[0])
    return prompts, touches


_trees = {}


def tree(repo, head):
    """그 HEAD에 있던 파일 집합. 못 읽으면 None."""
    key = (repo, head)
    if key not in _trees:
        try:
            r = subprocess.run(["git", "-C", repo, "-c", "core.quotepath=false", "ls-tree", "-r", "--name-only", head],
                               capture_output=True, text=True, errors="ignore", timeout=30)
            _trees[key] = {nfc(x) for x in r.stdout.splitlines()} if r.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            _trees[key] = None
    return _trees[key]


def join(rs, prompts):
    """기록마다 프롬프트 인덱스(못 맞추면 None).
    1단계: 해시가 맞는 (기록, 프롬프트) 짝을 전부 모아 시각 차이 순으로, 겹치지 않게 배정(기록 순서가 결과를 바꾸지 않게).
    2단계: 남은 기록은 안 쓰인 프롬프트 중 60초 안. 둘 다 프롬프트가 기록보다 SKEW초 넘게 앞서면 짝이 아니다."""
    ok = lambda t, pt, cap: t is not None and -SKEW <= pt - t <= cap
    times = [when(r.get("ts")) for r in rs]
    pairs = sorted((abs(pt - times[k]), k, i) for k, r in enumerate(rs) for i, (pt, hs) in enumerate(prompts)
                   if r.get("prompt_sha1") in hs and ok(times[k], pt, HASH_MAX_SECONDS))
    used, idx = set(), {}
    for _, k, i in pairs:
        if k not in idx and i not in used:
            idx[k] = i; used.add(i)
    pairs = sorted((abs(pt - times[k]), k, i) for k in range(len(rs)) if k not in idx
                   for i, (pt, _) in enumerate(prompts) if i not in used and ok(times[k], pt, JOIN_SECONDS))
    for _, k, i in pairs:
        if k not in idx and i not in used:
            idx[k] = i; used.add(i)
    return [idx.get(k) for k in range(len(rs))]


def turns(recs):
    """[{session, arms: {이름: [파일]}, src, label, kinds}] 와 단계별 수."""
    n = {"shadow": len(recs), "no_transcript": 0, "no_prompt_match": 0, "no_head": 0, "empty_label": 0,
         "first_touch_not_in_head": 0, "tail_cut": 0, "git_failed": 0, "turns": 0}
    by_sid, out = {}, []
    for r in recs:
        by_sid.setdefault(r["session_id"], []).append(r)
    for sid, rs in by_sid.items():
        path = transcript(sid)
        if not path:
            n["no_transcript"] += len(rs)
            continue
        prompts, touches = read_session(path)
        for r, i in zip(rs, join(rs, prompts)):
            c = r["compile"]
            if i is None:
                n["no_prompt_match"] += 1
                continue
            start = prompts[i][0]
            end = prompts[i + 1][0] if i + 1 < len(prompts) else float("inf")
            repo = r.get("repo") or ""
            existed = tree(repo, c.get("head") or "") if c.get("head") else None
            if existed is None:
                n["no_head"] += 1
                continue
            before = {compiler.rel_in(repo, p) for t, p in touches if t < start}
            label, missing = [], set()
            for t, p in touches:
                rel = compiler.rel_in(repo, p)
                if start <= t < end and rel and rel not in before and rel not in label and not compiler.is_hub(rel):
                    if rel in existed:
                        label.append(rel)
                    else:
                        missing.add(rel)
            n["first_touch_not_in_head"] += len(missing)
            if not label:
                n["empty_label"] += 1
                continue
            b = c.get("baselines") or {}
            keep = lambda fs: [f for f in fs or [] if f in existed]
            files, src = c.get("files") or [], c.get("src", "")
            pairs = [(f, s) for f, s in zip(files, src) if f in existed]
            n["tail_cut"] += bool((c.get("seeds") or {}).get("tail_cut"))
            n["git_failed"] += (c.get("seeds") or {}).get("git_ok") is False
            out.append({"session": sid, "label": set(label), "src": "".join(s for _, s in pairs),
                        "kinds": c.get("kinds") or [], "ms": c.get("ms"),
                        "arms": {"compiler": [f for f, _ in pairs], "nograph": keep(b.get("nograph")),
                                 "folder": keep(b.get("folder")), "handoff": keep(b.get("handoff"))}})
    n["turns"] = len(out)
    return out, n


def recall(t, arm):
    return len(set(t["arms"][arm]) & t["label"]) / len(t["label"])


def precision(t, arm):
    return len(set(t["arms"][arm]) & t["label"]) / len(t["arms"][arm]) if t["arms"][arm] else None


def boot_diff(ts, a, b, seed=7):
    """세션 단위 부트스트랩 — recall(a) − recall(b) 턴 평균의 95% 구간."""
    sess = {}
    for t in ts:
        sess.setdefault(t["session"], []).append(recall(t, a) - recall(t, b))
    keys = sorted(sess)
    rnd, means = random.Random(seed), []
    for _ in range(BOOT):
        xs = [x for k in (rnd.choice(keys) for _ in keys) for x in sess[k]]
        means.append(sum(xs) / len(xs))
    means.sort()
    return means[int(0.025 * BOOT)], means[int(0.975 * BOOT) - 1]


def evaluate(ts):
    sessions = {t["session"] for t in ts}
    res = {"turns": len(ts), "sessions": len(sessions)}
    if not ts:
        res["verdict"] = "못 셌다"
        return res
    res["recall"] = {a: statistics.mean(recall(t, a) for t in ts) for a in ARMS}
    res["precision"] = {a: (statistics.mean(xs) if xs else None)
                        for a in ARMS for xs in [[p for p in (precision(t, a) for t in ts) if p is not None]]}
    hits = {k: 0 for k in SRC_NAMES}
    picked = {k: 0 for k in SRC_NAMES}
    for t in ts:
        for f, code in zip(t["arms"]["compiler"], t["src"]):
            picked[code] = picked.get(code, 0) + 1
            hits[code] = hits.get(code, 0) + (f in t["label"])
    res["by_source"] = {SRC_NAMES.get(k, k): {"picked": picked[k], "hit": hits[k]} for k in picked}
    pt = [t for t in ts if "prompt" in t["kinds"]]
    res["prompt_concept_turns"] = len(pt)
    # 그래프 없이도 뽑혔을 파일(nograph에도 있는 것)은 빼고 센다 — 인계서와 겹친 개념 파일을 그래프 적중으로 부풀리지 않게
    res["prompt_concept_hit"] = sum(1 for t in pt if any(c == "p" and f in t["label"] and f not in t["arms"]["nograph"]
                                                         for f, c in zip(t["arms"]["compiler"], t["src"])))
    ms = [t["ms"] for t in ts if isinstance(t.get("ms"), (int, float))]
    res["ms"] = {"median": statistics.median(ms), "max": max(ms)} if ms else None
    diff = res["recall"]["compiler"] - res["recall"]["nograph"]
    res["diff"] = diff
    if len(ts) < MIN_TURNS or len(sessions) < MIN_SESSIONS:
        res["verdict"] = "못 셌다"
        return res
    lo, hi = boot_diff(ts, "compiler", "nograph")
    res["ci"] = [lo, hi]
    pc, pn = res["precision"]["compiler"], res["precision"]["nograph"]
    # 설계안 7절: 합격 = 점추정 +10%p 이상·하한 > 0·precision 하락 없음. 구간이 0을 걸치면 판정 불가. 그 밖은 전부 불합격.
    if diff >= PASS_DIFF - 1e-9 and lo > 0 and (pn is None or (pc is not None and pc >= pn)):
        res["verdict"] = "합격"
    elif lo <= 0 <= hi:
        res["verdict"] = "판정 불가"
    else:
        res["verdict"] = "불합격"
    return res


def render(n, res):
    pct = lambda x: "-" if x is None else f"{x * 100:.1f}%"
    L = ["맥락 조립기 그림자 측정 (설계안 7절)", "",
         f"단계: 프롬프트 기록 {n['prompt_records']} (조립기 기록 없음 {n['compile_off']}(꺼짐·조립기 전 판) · 켬 {n['compile_on']}은 측정 밖 · 오류 {n['compile_error']})"
         f" → 그림자 기록 {n['shadow']} → 세션 기록 없음 {n['no_transcript']} · 프롬프트 못 맞춤 {n['no_prompt_match']}"
         f" · HEAD 못 읽음 {n['no_head']} · 정답 빈 턴 {n['empty_label']} → 측정 턴 {n['turns']}(세션 {res['sessions']})",
         f"  (정답에서 뺀 첫 만짐 — HEAD에 없던 파일 {n['first_touch_not_in_head']}개 · 세션 기록 끝만 읽은 턴 {n['tail_cut']}개"
         f" · git log 실패로 같은 폴더 후보가 빈 턴 {n['git_failed']}개)"]
    if not res["turns"]:
        L += ["", f"판정: 못 셌다 — 측정 턴 0개(필요: {MIN_TURNS}턴·{MIN_SESSIONS}세션). 위 단계 수에서 어디서 0이 됐는지 본다."]
        return "\n".join(L)
    L += ["", "recall(정답 중 골라 둔 비율) · precision(고른 것 중 정답 비율), 턴 평균:"]
    for a in ARMS:
        L.append(f"  {a:9s} recall {pct(res['recall'][a])} · precision {pct(res['precision'][a])}")
    L += ["", f"개념 그래프가 보탠 몫(조립기 − nograph): {res['diff'] * 100:+.1f}%p"
          + (f", 95% 구간 [{res['ci'][0] * 100:+.1f}, {res['ci'][1] * 100:+.1f}]%p" if "ci" in res else "")]
    L += ["출처별(고른 수 → 맞힌 수): " + " · ".join(f"{k} {v['picked']}→{v['hit']}" for k, v in res["by_source"].items())]
    L += [f"프롬프트로 개념이 맞은 턴 {res['prompt_concept_turns']}개 중 그 개념 파일(그래프 없이는 안 뽑혔을 것)이 정답에 든 턴 {res['prompt_concept_hit']}개"]
    if res.get("ms"):
        L += [f"걸린 시간: 중앙값 {res['ms']['median']}ms · 최대 {res['ms']['max']}ms"]
    need = "" if res["verdict"] != "못 셌다" else f" (필요: 정답 있는 턴 {MIN_TURNS}개·세션 {MIN_SESSIONS}개)"
    L += ["", f"판정: {res['verdict']}{need} — 합격선: 차이 +{PASS_DIFF * 100:.0f}%p 이상·하한 > 0·precision이 nograph 이상"]
    return "\n".join(L)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--log")
    ap.add_argument("--since")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    rn, recs = records(log_path(a.log), a.since)
    ts, n = turns(recs)
    n.update(rn)
    res = evaluate(ts)
    print(json.dumps({"stages": n, **res}, ensure_ascii=False, indent=2) if a.json else render(n, res))


if __name__ == "__main__":
    main(sys.argv[1:])
