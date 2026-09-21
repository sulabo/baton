#!/usr/bin/env python3
"""Round1-B: 세션 상태(직전 프롬프트)로 라우팅하면 NO_MATCH가 줄어드는가.

읽기 전용. tasks.jsonl의 accepted 프롬프트만 쓴다.
"""
import json, random, sys
from pathlib import Path

OBS = "/Users/seongwoo/Documents/바이브 코딩/baton/observer"
sys.path.insert(0, OBS)
import baton_rules  # noqa: E402

BATON = Path("/Users/seongwoo/Documents/일자리/경력 기술서 26.05/.baton")
RULES = json.loads((BATON / "rules.json").read_text(encoding="utf-8"))

rows = [json.loads(l) for l in open(BATON / "tasks.jsonl", encoding="utf-8") if l.strip()]
acc = [r for r in rows if r["extractor_decision"] == "accepted"]
# 세션 = file. 세션 안에서 ts 오름차순으로 정렬해 "직전"을 정의한다.
by_file = {}
for r in acc:
    by_file.setdefault(r["file"], []).append(r)
for f in by_file:
    by_file[f].sort(key=lambda r: r["ts"])

# 각 행에 (세션, 세션내 index)를 매긴다. 출력 순서는 원본 순서를 유지.
pos = {}
for f, rs in by_file.items():
    for i, r in enumerate(rs):
        pos[r["id"]] = (f, i)


def ctx_text(r, n):
    """현재 프롬프트 앞에 같은 세션의 직전 accepted 프롬프트 n개를 이어 붙인다."""
    f, i = pos[r["id"]]
    prev = by_file[f][max(0, i - n):i]
    return "\n".join([p["text"] for p in prev] + [r["text"]]), [p["text"] for p in prev]


def first_text(r):
    """현재 프롬프트 + 그 세션의 첫 accepted 프롬프트."""
    f, i = pos[r["id"]]
    first = by_file[f][0]
    if first["id"] == r["id"]:
        return r["text"], []
    return first["text"] + "\n" + r["text"], [first["text"]]


def dist(texts):
    d = {"MATCHED": 0, "AMBIGUOUS": 0, "NO_MATCH": 0}
    states = {}
    for rid, t in texts:
        st, val, why = baton_rules.classify_task_type(t, RULES)
        d[st] += 1
        states[rid] = (st, val, why)
    return d, states


def line(label, d):
    n = sum(d.values())
    return (f"| {label} | {d['MATCHED']} | {d['AMBIGUOUS']} | {d['NO_MATCH']} | "
            f"{100*d['NO_MATCH']/n:.0f}% |")


print(f"accepted n = {len(acc)} · 세션(file) 수 = {len(by_file)}")
print("| 조건 | MATCHED | AMBIGUOUS | NO_MATCH | NO_MATCH 비율 |")
print("|---|---|---|---|---|")

base_d, base_s = dist([(r["id"], r["text"]) for r in acc])
print(line("단독", base_d))

results = {}
for n in (1, 2, 3):
    d, s = dist([(r["id"], ctx_text(r, n)[0]) for r in acc])
    results[n] = (d, s)
    print(line(f"N={n}", d))

fd, fs = dist([(r["id"], first_text(r)[0]) for r in acc])
print(line("첫 프롬프트", fd))

# 창 크기별 전이 (기준선 대비)
print()
for n in (1, 2, 3):
    d, s = results[n]
    n2m = [r for r in acc if base_s[r["id"]][0] == "NO_MATCH" and s[r["id"]][0] == "MATCHED"]
    n2a = [r for r in acc if base_s[r["id"]][0] == "NO_MATCH" and s[r["id"]][0] == "AMBIGUOUS"]
    m2a = [r for r in acc if base_s[r["id"]][0] == "MATCHED" and s[r["id"]][0] == "AMBIGUOUS"]
    m2m_diff = [r for r in acc if base_s[r["id"]][0] == "MATCHED" and s[r["id"]][0] == "MATCHED"
                and base_s[r["id"]][1] != s[r["id"]][1]]
    print(f"N={n}: NO_MATCH→MATCHED {len(n2m)} · NO_MATCH→AMBIGUOUS {len(n2a)} · "
          f"MATCHED→AMBIGUOUS {len(m2a)} · MATCHED이나 종류 바뀜 {len(m2m_diff)}")

# 맥락이 없는 행 (세션 첫 프롬프트) — 창을 붙여도 바뀔 수 없다
no_ctx = [r for r in acc if pos[r["id"]][1] == 0]
print(f"세션 첫 프롬프트(붙일 맥락 없음) = {len(no_ctx)} / {len(acc)}")
nm_no_ctx = [r for r in no_ctx if base_s[r["id"]][0] == "NO_MATCH"]
print(f"  그중 단독 NO_MATCH = {len(nm_no_ctx)}")

# 4번: N=2에서 NO_MATCH→MATCHED 10건 고정 seed 추출
print("\n=== N=2, NO_MATCH→MATCHED 표본 10건 (seed 20260922) ===")
d2, s2 = results[2]
flips = [r for r in acc if base_s[r["id"]][0] == "NO_MATCH" and s2[r["id"]][0] == "MATCHED"]
flips.sort(key=lambda r: r["id"])
rng = random.Random(20260922)
sample = rng.sample(flips, min(10, len(flips)))
for k, r in enumerate(sample, 1):
    _, prev = ctx_text(r, 2)
    st, val, why = s2[r["id"]]
    print(f"\n--- {k}. id={r['id']} file={r['file'][:8]} boundary={r.get('boundary_type')} ---")
    for j, p in enumerate(prev, 1):
        print(f"  [맥락 -{len(prev)-j+1}] {p!r}")
    print(f"  [현재]     {r['text']!r}")
    print(f"  [판정]     {val}  근거어={why}")

# --- 보조 측정: 붙은 라벨이 "앞 프롬프트의 라벨 물려받기"에 불과한가 ---
print("\n=== 보조 측정 ===")
# 정의 A: 앞 2건 중 하나라도 단독 MATCHED이고 같은 라벨 (구조적으로 자명 — 근거로 쓰지 말 것)
# 정의 B: 바로 직전 1건이 단독 MATCHED이고 같은 라벨 (정보가 있는 수치)
inh_a = inh_b = inh_b_amb = 0
for r in flips:
    f, i = pos[r["id"]]
    prev_rows = by_file[f][max(0, i - 2):i]
    lab = s2[r["id"]][1]
    if any(base_s[p["id"]][0] == "MATCHED" and base_s[p["id"]][1] == lab for p in prev_rows):
        inh_a += 1
    st, val, _ = base_s[prev_rows[-1]["id"]]
    if st == "MATCHED" and val == lab:
        inh_b += 1
    if (st == "MATCHED" and val == lab) or (st == "AMBIGUOUS" and lab in val):
        inh_b_amb += 1
print(f"N=2 flips {len(flips)}")
print(f"  정의 A 앞 2건 중 하나와 라벨 일치 = {inh_a} (자명)")
print(f"  정의 B 바로 직전 1건과 라벨 일치 = {inh_b}")
print(f"  정의 B' 직전 1건이 AMBIGUOUS 후보에 포함까지 허용 = {inh_b_amb}")
noise = [r for r in flips if r["text"].startswith("[Image") or r["text"].startswith("(Re-invocation")]
print(f"  현재 프롬프트가 이미지 자리표시자/스킬 재호출 문구인 것 = {len(noise)}")

import re as _re
hand = [r for r in acc if "핸드오프" in r["text"] or "인계" in r["text"]]
conf = [r for r in acc if _re.search(r"맞(는|지|나)", r["text"])]
for name, grp in (("핸드오프류", hand), ("확인질문류", conf)):
    b = sum(1 for r in grp if base_s[r["id"]][0] == "NO_MATCH")
    fl = sum(1 for r in grp if base_s[r["id"]][0] == "NO_MATCH" and s2[r["id"]][0] == "MATCHED")
    print(f"  {name}: 전체 {len(grp)} · 단독 NO_MATCH {b} · N=2에서 MATCHED {fl}")
