#!/usr/bin/env python3
"""BATON V0 — STEP 0. 사람 프롬프트 추출과 작업 경계 후보. 아무것도 바꾸지 않는다.

  baton_init.py extract <project_root>          .baton/tasks.jsonl · run.json
  baton_init.py sample  <project_root> [--seed N]  .baton/samples/0A.jsonl · 0B.jsonl
  baton_init.py label   <project_root> --step 0A|0B [--show] [--answer ID y|n|u]   .baton/labels.jsonl
    대화형. 규칙 예측은 보여주지 않는다(이 조각에는 없다). 0B는 앞 프롬프트를 같이 보여 준다.

이 조각의 범위: Claude Code 세션 기록만. Codex 세션 파일은 프롬프트 레코드 형식을 아직
확인하지 않아 --source codex 는 거부한다(스텁 아님, 범위 밖). 규칙·채점(STEP 1·2)은 없다.
"""
import argparse, glob, hashlib, json, os, random, sys, tempfile, unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

SHORT = 15
GAP_BUCKETS = [("gap_0_15", 0, 15), ("gap_15_30", 15, 30), ("gap_30_60", 30, 60), ("gap_60_plus", 60, None)]

def norm(p): return unicodedata.normalize("NFC", str(Path(p).expanduser().resolve()))
def sha(s): return hashlib.sha256(s.encode("utf-8")).hexdigest()
def now(): return datetime.now(timezone.utc)

def content_schema(c):
    if isinstance(c, str): return "plain_string"
    if isinstance(c, list):
        kinds = {x.get("type") for x in c if isinstance(x, dict)}
        if kinds == {"text"}: return "text_block_only"
        if kinds <= {"text", "image"} and "text" in kinds: return "text_with_image"
        if "tool_result" in kinds and kinds - {"tool_result"}: return "mixed"
        if "tool_result" in kinds: return "tool_result"
        return "other_list"
    return "other"

def human_text(c, schema):
    if schema == "plain_string": return c.strip()
    if schema in ("text_block_only", "text_with_image"):
        return " ".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text").strip()
    return None

def parse_ts(s):
    try: return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError): return None

def bucket(gap):
    for name, lo, hi in GAP_BUCKETS:
        if gap >= lo and (hi is None or gap < hi): return name
    return None

def claude_files_for(root):
    """폴더명은 한글이 대시로 바뀌어 역산이 안 된다. 파일 안 cwd로 맞춘다."""
    out = []
    for f in glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl")):
        try:
            for line in open(f, encoding="utf-8", errors="ignore"):
                d = json.loads(line) if line.strip() else None
                if d and d.get("cwd"):
                    if norm(d["cwd"]) == root: out.append(f)
                    break
        except (json.JSONDecodeError, OSError): continue
    return sorted(out)

def extract(root, source):
    if source != "claude":
        sys.exit("이 조각은 Claude Code 소스만 다룬다. Codex 세션의 프롬프트 레코드 형식은 아직 확인 전이라 범위 밖.")
    files = claude_files_for(root)
    cutoff = (now() + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    manifest = "\n".join(f"{f} {os.path.getsize(f)}" for f in files)
    rows, counts = [], {"raw_user_events": 0, "accepted": 0, "accepted_ge15": 0,
                        "session_first": 0, "gap_ge30": 0, "skipped_after_cutoff": 0, "negative_gap_clamped": 0}
    schema_pop, bucket_pop = {}, {n: 0 for n, _, _ in GAP_BUCKETS}; bucket_pop["SESSION_FIRST"] = 0
    for f in files:
        prev = None
        for line in open(f, encoding="utf-8", errors="ignore"):
            try: d = json.loads(line)
            except json.JSONDecodeError: continue
            if d.get("type") != "user": continue
            ts = parse_ts(d.get("timestamp", ""))
            if ts and ts >= cutoff: counts["skipped_after_cutoff"] += 1; continue
            counts["raw_user_events"] += 1
            c = d.get("message", {}).get("content")
            schema = content_schema(c)
            text = human_text(c, schema)
            row = {"id": f"{os.path.basename(f)[:8]}:{counts['raw_user_events']}", "source": "claude",
                   "file": os.path.basename(f), "ts": ts.isoformat() if ts else None, "content_schema": schema}
            key = ("accepted" if text and not text.startswith("<") else "rejected", schema)
            schema_pop[f"{key[0]}/{key[1]}"] = schema_pop.get(f"{key[0]}/{key[1]}", 0) + 1
            if not text or text.startswith("<"):
                row.update(extractor_decision="rejected",
                           reject_reason="system_tag" if text else schema)
                rows.append(row); continue
            counts["accepted"] += 1
            if len(text) >= SHORT: counts["accepted_ge15"] += 1
            row.update(extractor_decision="accepted", text=text, short_prompt=len(text) < SHORT)
            if prev is None:
                row.update(boundary_type="SESSION_FIRST", gap_minutes=None); bucket_pop["SESSION_FIRST"] += 1
                if len(text) >= SHORT: counts["session_first"] += 1
            elif ts and prev:
                gap = (ts - prev).total_seconds() / 60
                if gap < 0: counts["negative_gap_clamped"] += 1; gap = 0.0   # 밀리초 순서 뒤바뀜
                b = bucket(gap)
                row.update(boundary_type="GAP_CANDIDATE", gap_minutes=round(gap, 1), gap_bucket=b)
                if b: bucket_pop[b] += 1
                if gap >= 30 and len(text) >= SHORT: counts["gap_ge30"] += 1
            else:
                row.update(boundary_type="NONE", gap_minutes=None)
            if ts: prev = ts
            rows.append(row)
    stamps = [parse_ts(r["ts"]) for r in rows if r.get("ts")]
    run = {"run_status": "OK", "stage": "extract", "evaluation_status": "BASELINE",
           "source": source, "project_root": root, "session_files": len(files),
           "measurement_cutoff": cutoff.isoformat(), "time_range": [min(stamps).date().isoformat(), max(stamps).date().isoformat()] if stamps else None,
           "source_manifest_sha256": sha(manifest), "script_sha256": sha(open(__file__, encoding="utf-8").read()),
           "counts": counts, "union_session_first_gap30_ge15": counts["session_first"] + counts["gap_ge30"],
           "content_schema_population": schema_pop, "gap_bucket_population": bucket_pop,
           "extracted_at": now().isoformat()}
    return rows, run

def write_atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    with os.fdopen(fd, "w", encoding="utf-8") as fh: fh.write(text)
    os.replace(tmp, path)

def cmd_extract(a):
    root = norm(a.project_root); out = Path(root) / ".baton"
    rows, run = extract(root, a.source)
    write_atomic(out / "tasks.jsonl", "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    write_atomic(out / "run.json", json.dumps(run, ensure_ascii=False, indent=2) + "\n")
    c = run["counts"]
    print("[MEASURED, PRE-VALIDATION]")
    print(f"  실행: python3 observer/baton_init.py extract {a.project_root!r}   (script sha256 앞 12자 {run['script_sha256'][:12]})")
    print(f"  Source: {run['source']} · session files {run['session_files']} · 기간 {run['time_range']} · cutoff {run['measurement_cutoff'][:10]} 미만")
    print(f"  Raw user-type events: {c['raw_user_events']}   (cutoff 이후 제외 {c['skipped_after_cutoff']})")
    print(f"  Extractor accepted (구조 필터만): {c['accepted']}   그중 15자 이상: {c['accepted_ge15']}")
    print(f"  Among 15자 이상: SESSION_FIRST {c['session_first']} · gap>=30분 {c['gap_ge30']} · union {run['union_session_first_gap30_ge15']}")
    print(f"  구간 모집단: " + " · ".join(f"{k} {v}" for k, v in run["gap_bucket_population"].items()))
    print(f"  구조 모집단: " + " · ".join(f"{k} {v}" for k, v in sorted(run["content_schema_population"].items())))
    print(f"  → {out/'tasks.jsonl'} · {out/'run.json'}")

def stratified(rows, key, target, seed):
    strata = {}
    for r in rows: strata.setdefault(key(r), []).append(r)
    rnd = random.Random(seed); picked, meta = [], []
    for name, pop in sorted(strata.items()):
        n = min(target, len(pop)); rnd.shuffle(pop)
        for r in pop[:n]: picked.append({**r, "stratum": name})
        meta.append({"stratum": name, "population_n": len(pop), "sample_n": n, "sampling": "random",
                     "seed": seed, "exhausted": n == len(pop)})
    return picked, meta

def cmd_sample(a):
    root = norm(a.project_root); out = Path(root) / ".baton"
    rows = [json.loads(l) for l in open(out / "tasks.jsonl", encoding="utf-8") if l.strip()]
    a_rows, a_meta = stratified(rows, lambda r: f"{r['extractor_decision']}/{r['content_schema']}", 5, a.seed)
    acc = [r for r in rows if r["extractor_decision"] == "accepted" and r.get("boundary_type") in ("SESSION_FIRST", "GAP_CANDIDATE")]
    b_rows, b_meta = stratified(acc, lambda r: "SESSION_FIRST" if r["boundary_type"] == "SESSION_FIRST" else r.get("gap_bucket") or "gap_unknown", 10, a.seed)
    for name, picked, meta in (("0A", a_rows, a_meta), ("0B", b_rows, b_meta)):
        body = json.dumps({"sampling_meta": meta}, ensure_ascii=False) + "\n" + \
               "".join(json.dumps({k: v for k, v in r.items() if k != "text"} | {"text": r.get("text")}, ensure_ascii=False) + "\n" for r in picked)
        write_atomic(out / "samples" / f"{name}.jsonl", body)
        print(f"  {name}: " + " · ".join(f"{m['stratum']} {m['sample_n']}/{m['population_n']}{' EXHAUSTED' if m['exhausted'] else ''}" for m in meta))
    print("  라벨링 화면에서 규칙 예측을 숨긴다 — 이 조각에는 예측 자체가 없다.")

QUESTION = {"0A": "사람이 친 프롬프트인가? (도구 결과·시스템 메시지가 아닌)",
            "0B": "앞 프롬프트와 다른 새 작업의 시작인가?"}

def load_samples(out, step):
    lines = [l for l in open(out / "samples" / f"{step}.jsonl", encoding="utf-8") if l.strip()]
    return json.loads(lines[0])["sampling_meta"], [json.loads(l) for l in lines[1:]]

def load_labels(out):
    p = out / "labels.jsonl"
    return {(r["step"], r["id"]): r for r in (json.loads(l) for l in open(p, encoding="utf-8") if l.strip())} if p.exists() else {}

def previous_prompt(rows, r):
    """0-B 판단에는 앞 프롬프트가 필요하다. 같은 파일의 직전 accepted 행."""
    same = [x for x in rows if x["file"] == r["file"] and x["extractor_decision"] == "accepted" and x.get("ts") and x["ts"] < r["ts"]]
    return same[-1]["text"] if same else None

def cmd_label(a):
    root = norm(a.project_root); out = Path(root) / ".baton"
    rows = [json.loads(l) for l in open(out / "tasks.jsonl", encoding="utf-8") if l.strip()]
    meta, samples = load_samples(out, a.step); done = load_labels(out)
    pending = [r for r in samples if (a.step, r["id"]) not in done]
    print(f"[{a.step}] 표본 {len(samples)} · 답함 {len(samples)-len(pending)} · 남음 {len(pending)}")
    if a.answer:
        sid, ans = a.answer
        r = next((x for x in samples if x["id"] == sid), None)
        if not r: sys.exit(f"표본에 없는 id: {sid}")
        with open(out / "labels.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"step": a.step, "id": sid, "stratum": r["stratum"], "answer": ans,
                                 "labeled_at": now().isoformat()}, ensure_ascii=False) + "\n")
        print(f"  기록: {sid} → {ans}"); return
    for r in pending:
        print("\n" + "─" * 60)
        print(f"id {r['id']} · 층 {r['stratum']} · 구조 {r['content_schema']}")
        if a.step == "0B":
            pv = previous_prompt(rows, r)
            print(f"앞 프롬프트: {pv[:120] if pv else '(없음 — 세션 첫 프롬프트)'}")
            print(f"공백: {r.get('gap_minutes')}분")
        print(f"이 프롬프트: {(r.get('text') or '(텍스트 없음 — ' + r['content_schema'] + ')')[:200]}")
        print(f"질문: {QUESTION[a.step]}  [y/n/u=모르겠음/q=중단]")
        if a.show: continue
        ans = input("> ").strip().lower()
        if ans == "q": break
        if ans not in ("y", "n", "u"): print("  y/n/u 중 하나"); continue
        with open(out / "labels.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"step": a.step, "id": r["id"], "stratum": r["stratum"], "answer": ans,
                                 "labeled_at": now().isoformat()}, ensure_ascii=False) + "\n")
    if a.show: print("\n(--show: 보기만. 답은 --show 없이 다시 실행)")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract"); e.add_argument("project_root"); e.add_argument("--source", default="claude")
    s = sub.add_parser("sample"); s.add_argument("project_root"); s.add_argument("--seed", type=int, default=20260921)
    l = sub.add_parser("label"); l.add_argument("project_root"); l.add_argument("--step", choices=["0A", "0B"], required=True)
    l.add_argument("--show", action="store_true", help="답하지 않고 보기만"); l.add_argument("--answer", nargs=2, metavar=("ID", "Y_N_U"))
    a = ap.parse_args(); {"extract": cmd_extract, "sample": cmd_sample, "label": cmd_label}[a.cmd](a)
