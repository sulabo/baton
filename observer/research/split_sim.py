#!/usr/bin/env python3
"""세션 끊기 재계산(비용 0): 실제 세션 기록을 두고 "맥락이 문턱을 넘을 때 인계서를 쓰고 새 세션으로 넘어갔다면"을 다시 셈한다.
   split_sim.py [--since YYYY-MM-DD] [--ratio 2.0] [--handoff 4000] [--reorient 3] [--min-calls 40]
   split_sim.py --tokens [150,200,250,...] [--since YYYY-MM-DD] [--min-calls N]   달러 손익, 절대 토큰 문턱
     문턱은 설정 키처럼 토큰 수(250000)로도, 천 단위(250)로도 준다 — 1000 아래 값은 천 단위로 읽는다
     2026-11-25 재계산(docs/research/LOOP_PLAN.md)은 --tokens --since 2026-10-01 --min-calls 20

--tokens(달러 손익, 2026-11-25): 인계서 쓰기 비용을 넣는다 — 끊는 시점 맥락을 WRITE_READS(6)번 캐시 읽기 + 고정분
(23만 토큰에서 합이 $0.69가 되게 맞춤, docs/research/compact-vs-handoff.md). 새 세션은 첫 맥락+인계서를 한 번 캐시 쓰기,
방향 잡기 `reorient`회는 캐시 읽기. 그 뒤 증분은 원 세션과 같다고 둔다. 첫 압축(맥락이 앞 호출의 60% 아래) 전까지만 본다.
단가는 PRICES 두 모델로 함께 보인다. 문턱마다 그 문턱을 넘은 세션 수, 끊어서 이득 본 비율, 손익 중앙값·합계.

--ratio(아래, 2026-09-30): 상대 가중이고 인계서 쓰기 비용을 넣지 않았다 — 그 절감 추정(2배 35~45%)은 그래서 컸다.
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
    """메인 스레드 API 호출의 맥락 토큰(입력+캐시생성+캐시읽기), 호출 순서대로.
    usage가 없거나 합이 0인 줄은 건너뛴다 — 0이 들어가면 until_compaction이 그 자리를 압축으로 읽어 세션을 일찍 자른다(리뷰 11-25.
    2026-10-01 이후 실제 기록에는 그런 줄이 0개였다 — 재계산 수치는 그대로)."""
    out, seen = [], set()
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for ln in fh:
            try: d = json.loads(ln)
            except json.JSONDecodeError: continue
            if not isinstance(d, dict) or d.get("isSidechain") or d.get("type") != "assistant": continue
            m = d.get("message") or {}
            if m.get("model") == "<synthetic>" or m.get("id") in seen: continue
            ctx = sum((m.get("usage") or {}).get(k, 0) or 0 for k in u.TOKEN_KEYS)
            if ctx <= 0: continue
            seen.add(m.get("id"))
            out.append(ctx)
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


PRICES = {  # $/MTok — 캐시 읽기·캐시 쓰기
    "실험맞춤": {"read": 0.201, "write": 8.00},  # compact 맞대기 실험 비용에 맞춘 값(1시간 캐시 쓰기)
    "표준비율": {"read": 0.396, "write": 4.95},  # 표준 단가 비율(5분 캐시 쓰기)
}
WRITE_READS, CAL_CTX, CAL_COST = 6, 230_000, 0.69  # 인계서 쓰기: 끊는 시점 맥락 6번 읽기 + 고정분(23만에서 $0.69)
SWEEP = "150,200,250,300,350,400,450,500,600"


def fixed_part(pr):
    """인계서 쓰기의 고정분 $ — 23만 토큰 맥락에서 쓰기 전체가 $0.69가 되게 맞춘 나머지."""
    return CAL_COST - WRITE_READS * CAL_CTX * pr["read"] / 1e6


def dollars(ctxs, pr):
    """호출마다 앞 호출과 겹치는 몫은 캐시 읽기, 새로 붙은 몫은 캐시 쓰기로 친 $."""
    t, prev = 0.0, 0
    for c in ctxs:
        shared = min(prev, c)
        t += (shared * pr["read"] + (c - shared) * pr["write"]) / 1e6
        prev = c
    return t


def split_dollars(ctxs, tokens, pr, handoff=4000, reorient=3):
    """(맥락이 tokens를 넘을 때마다 끊었다면 든 $, 끊은 횟수). 끊는 호출 자리에 인계서 쓰기·새 세션 시작·방향 잡기가 들어간다.
    새 세션 첫 맥락보다 2만 토큰 이상 크지 않으면 끊지 않는다(끊자마자 다시 끊지 않게)."""
    first = ctxs[0]
    base, cut_at, t, cuts, prev = first, 0, 0.0, 0, 0
    for c in ctxs:
        cur = base + max(c - cut_at, 0) if cuts else c
        if cur > tokens and cur > first + handoff + 20_000:
            cuts += 1
            t += WRITE_READS * cur * pr["read"] / 1e6 + fixed_part(pr)  # 인계서 쓰기
            base, cut_at = first + handoff, c
            t += base * pr["write"] / 1e6 + reorient * base * pr["read"] / 1e6  # 새 세션 시작 + 방향 잡기
            prev = base
            continue
        shared = min(prev, cur)
        t += (shared * pr["read"] + (cur - shared) * pr["write"]) / 1e6
        prev = cur
    return t, cuts


def until_compaction(ctxs):
    """첫 압축(맥락이 앞 호출의 60% 아래로 떨어짐) 전까지의 호출."""
    for i in range(1, len(ctxs)):
        if ctxs[i] < 0.6 * ctxs[i - 1]:
            return ctxs[:i]
    return ctxs


def sweep(data, thresholds, pr, handoff=4000, reorient=3):
    """문턱(토큰)마다 (넘은 세션 수, 이득 본 비율, 손익 중앙값, 손익 합계, 넘은 뒤 남은 호출 중앙값). 넘은 세션이 3개 미만이면 수만."""
    out = []
    for T in thresholds:
        rows = []
        for d in data:
            if max(d) <= T:
                continue
            idx = next(i for i, c in enumerate(d) if c > T)
            rows.append((dollars(d, pr) - split_dollars(d, T, pr, handoff, reorient)[0], len(d) - idx))
        sv = [r[0] for r in rows]
        out.append((T, len(rows)) if len(rows) < 3 else
                   (T, len(rows), sum(x > 0 for x in sv) / len(sv), statistics.median(sv), sum(sv),
                    statistics.median(r[1] for r in rows)))
    return out


def tokens_arg(v):
    """--tokens 값 → 문턱 토큰 목록. 1000 아래는 천 단위(250 → 250000), 그 위는 토큰 수 그대로(BATON_SPLIT_TOKENS와 같다).
    비었거나 숫자가 아니면 오류 — 조용히 배수 모드로 넘어가지 않게(리뷰 11-25)."""
    try:
        xs = [int(x) for x in v.split(",") if x.strip()]
    except ValueError:
        xs = []
    if not xs or min(xs) <= 0:
        raise argparse.ArgumentTypeError(f"쉼표로 나눈 양의 정수여야 한다(예: 250000,450000 또는 250,450): {v!r}")
    return [x * 1000 if x < 1000 else x for x in xs]


def main_tokens(a):
    sessions, _ = u.collect("*", a.since)
    data = [d for d in (until_compaction(call_contexts(s["file"])) for s in sessions) if len(d) >= a.min_calls]
    if not data:
        print("대상 세션 0개 — 조건을 확인한다(0건이 아니라 못 셈일 수 있다)"); return
    print(f"[ESTIMATE] 끊기 손익($) · 세션 {len(data)}개({a.since}~, 호출 {a.min_calls}회 이상, 첫 압축 전까지) · "
          f"첫 호출 맥락 중앙값 {statistics.median(d[0] for d in data) / 1e3:.0f}K · "
          f"최대 맥락 중앙값 {statistics.median(max(d) for d in data) / 1e3:.0f}K · 인계서 {a.handoff}토큰 · 방향 잡기 {a.reorient}회")
    for name, pr in PRICES.items():
        print(f"\n[{name}] 읽기 ${pr['read']}/MTok·쓰기 ${pr['write']}/MTok, 인계서 쓰기 = 맥락 {WRITE_READS}번 읽기 + 고정분 "
              f"${fixed_part(pr):.2f}")
        print("  문턱  도달세션  이득본비율  손익중앙값  손익합계   도달뒤남은호출중앙값")
        for r in sweep(data, a.tokens, pr, a.handoff, a.reorient):
            if len(r) == 2:
                print(f"  {r[0] // 1000:>3}K  {r[1]:>4}  (표본 부족)"); continue
            T, n, share, med, total, left = r
            print(f"  {T // 1000:>3}K  {n:>6}  {share:>8.0%}  {med:>+9.2f}$  {total:>+8.2f}$  {left:>6.0f}")


def main(argv):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--since", type=lambda v: date.fromisoformat(v), default=date(2026, 8, 31))
    p.add_argument("--ratio", type=float, default=2.0)
    p.add_argument("--tokens", nargs="?", type=tokens_arg, const=tokens_arg(SWEEP), default=None,
                   help=f"달러 손익을 절대 문턱(토큰 수, 1000 아래는 천 단위, 쉼표 구분)으로 본다. 값을 빼면 {SWEEP}(천 단위)")
    p.add_argument("--handoff", type=int, default=4000)
    p.add_argument("--reorient", type=int, default=3)
    p.add_argument("--min-calls", type=int, default=40)
    a = p.parse_args(argv)
    if a.tokens is not None:
        return main_tokens(a)
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
