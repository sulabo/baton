#!/usr/bin/env python3
"""세션 끊기 재계산(비용 0): 실제 세션 기록을 두고 "맥락이 문턱을 넘을 때 인계서를 쓰고 새 세션으로 넘어갔다면"을 다시 셈한다.
   split_sim.py [--since YYYY-MM-DD] [--ratio 2.0] [--handoff 4000] [--reorient 3] [--min-calls 40]

모델(근사 — 반사실이라 상한에 가깝다):
- 새 세션의 호출 맥락 = 새 세션 첫 맥락(원 세션의 첫 호출 맥락 + 인계서 토큰) + 끊은 뒤 새로 쌓인 몫(원래 맥락 − 끊은 시점 맥락).
- 끊을 때마다 방향 잡기 호출 `reorient`회를 더한다(인계서 주입 실험에서 상태 세션이 약 3턴).
- 끊는 시점: 새 세션 기준 맥락이 첫 맥락 × ratio를 넘을 때. 여러 번 끊을 수 있다.
- 가정: 끊은 뒤에도 같은 작업을 같은 순서로 한다. 실제로는 넘어간 세션이 이미 읽은 것을 다시 읽을 수 있다 — 그만큼 절감이 줄어든다.
- 비용 가중(API 단가 비율): 세션 맥락 중 이전 호출과 겹치는 몫은 캐시 읽기(0.1), 새로 붙은 몫은 캐시 생성(1.25)으로 친다. 구독 한도가 이렇게 세는지는 미확인.
"""
import argparse, json, os, statistics, sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import usage_week as u


def call_contexts(path):
    """메인 스레드 API 호출의 맥락 토큰(입력+캐시생성+캐시읽기), 호출 순서대로."""
    out, seen = [], set()
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for ln in fh:
            try: d = json.loads(ln)
            except json.JSONDecodeError: continue
            if d.get("isSidechain") or d.get("type") != "assistant": continue
            m = d.get("message") or {}
            if m.get("model") == "<synthetic>" or m.get("id") in seen: continue
            seen.add(m.get("id"))
            out.append(sum((m.get("usage") or {}).get(k, 0) or 0 for k in u.TOKEN_KEYS))
    return out


def weighted(ctxs):
    """호출마다 앞 호출과 겹치는 몫은 캐시 읽기(0.1), 새로 붙은 몫은 캐시 생성(1.25).
    맥락이 줄어든 호출(새 세션·압축)은 앞 세션의 이력을 이어받지 못한다 — 겹치는 몫을 고정 앞부분(첫 호출 맥락)까지로만 친다."""
    total, prev = 0.0, 0
    first = ctxs[0] if ctxs else 0
    for c in ctxs:
        shared = min(prev, c) if c >= prev else min(first, c)
        total += 0.1 * shared + 1.25 * (c - shared)
        prev = c
    return total


def simulate(ctxs, ratio=2.0, handoff=4000, reorient=3):
    """(끊은 뒤 호출 맥락 목록, 끊은 횟수)."""
    if not ctxs: return [], 0
    first = ctxs[0]
    base, cut_at, out, cuts = first, ctxs[0], [], 0
    for c in ctxs:
        cur = base + max(c - cut_at, 0)
        if cur > first * ratio:
            cuts += 1
            base, cut_at = first + handoff, c
            out.extend([base] * reorient)  # 새 세션에서 인계서를 보고 방향을 잡는 호출
            cur = base
        out.append(cur)
    return out, cuts


def main(argv):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--since", type=lambda v: date.fromisoformat(v), default=date(2026, 8, 31))
    p.add_argument("--ratio", type=float, default=2.0)
    p.add_argument("--handoff", type=int, default=4000)
    p.add_argument("--reorient", type=int, default=3)
    p.add_argument("--min-calls", type=int, default=40)
    a = p.parse_args(argv)
    sessions, _ = u.collect("*", a.since)
    rows = []
    for s in sessions:
        ctxs = call_contexts(s["file"])
        if len(ctxs) < a.min_calls: continue
        sim, cuts = simulate(ctxs, a.ratio, a.handoff, a.reorient)
        rows.append((1 - sum(sim) / sum(ctxs), 1 - weighted(sim) / weighted(ctxs), cuts, len(ctxs)))
    if not rows:
        print("대상 세션 0개 — 조건을 확인한다(0건이 아니라 못 셈일 수 있다)"); return
    raw, wt, cuts, n = zip(*rows)
    print(f"[ESTIMATE] 세션 끊기 재계산 · 세션 {len(rows)}개(호출 {a.min_calls}회 이상) · 문턱 첫 맥락×{a.ratio} · 인계서 {a.handoff}토큰 · 방향 잡기 {a.reorient}회")
    print(f"  절감(토큰) 중앙값 {statistics.median(raw):.1%} · 사분위 {statistics.quantiles(raw, n=4)[0]:.1%}~{statistics.quantiles(raw, n=4)[2]:.1%}")
    print(f"  절감(비용 가중) 중앙값 {statistics.median(wt):.1%} · 사분위 {statistics.quantiles(wt, n=4)[0]:.1%}~{statistics.quantiles(wt, n=4)[2]:.1%}")
    print(f"  끊은 횟수 중앙값 {statistics.median(cuts):.0f}회 · 세션 호출 중앙값 {statistics.median(n):.0f}")


if __name__ == "__main__":
    main(sys.argv[1:])
