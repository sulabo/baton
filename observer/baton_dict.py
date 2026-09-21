#!/usr/bin/env python3
"""개인 사전 초안. 사용자가 실제로 쓴 프롬프트에서 동사·구를 빈도순으로 뽑는다.

  baton_dict.py build <project_root> [--top 30]    .baton/dict.json · dict.md

분류기가 아니다. 어떤 말이 어떤 작업 종류인지는 아직 모른다. 이 단계는
"이 사람은 이렇게 말한다"의 목록이고, 일반 사전(v0.1.0)에 없는 것을 표시한다.
사전을 만든 시점(source_until)을 기록한다. 그 뒤 프롬프트가 나중에 시험 집합이 된다.
"""
import json, re, sys, hashlib, unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent)); import baton_rules as R

# 한국어 서술어 어미. 이걸로 끝나는 토큰을 '동사 후보'로 본다. 형태소 분석기 없이 가는 V0 근사.
ENDINGS = ("해줘", "해줄래", "해주", "하자", "해봐", "해보자", "해볼까", "할까", "할게", "해", "줘", "봐줘", "줄래",
           "봐", "보자", "하고", "하면", "해서", "했어", "했는데", "하는", "하기", "되지", "맞지", "맞나", "맞는거지",
           "있어", "없어", "인데", "야", "자")
STOP = {"그", "이", "저", "그리고", "그런데", "근데", "일단", "우선", "지금", "이제", "좀", "조금", "다시", "그냥", "너", "내가", "나는"}
V010 = {v for vs in R.GLOBAL_RULES["task_types"].values() for v in vs}

def norm(p): return unicodedata.normalize("NFC", str(Path(p).expanduser().resolve()))
def tokens(text):
    return [t for t in re.split(r"[\s,.!?~…\"'()\[\]/·:]+", text) if t and t not in STOP]

def build(root, top):
    out = Path(root) / ".baton"
    rows = [json.loads(l) for l in open(out / "tasks.jsonl", encoding="utf-8") if l.strip()]
    acc = [r for r in rows if r["extractor_decision"] == "accepted" and r.get("text")]
    verbs, grams, ex = Counter(), Counter(), defaultdict(list)
    for r in acc:
        toks = tokens(r["text"])
        seen_v, seen_g = set(), set()
        for t in toks:
            if t.endswith(ENDINGS) and len(t) >= 2 and t not in seen_v:
                verbs[t] += 1; seen_v.add(t)
                if len(ex[t]) < 2: ex[t].append(r["text"][:50])
        for a, b in zip(toks, toks[1:]):
            g = f"{a} {b}"
            if g not in seen_g and len(a) >= 2 and len(b) >= 2:
                grams[g] += 1; seen_g.add(g)
                if len(ex[g]) < 2: ex[g].append(r["text"][:50])
    def in_v010(tok): return any(v in tok for v in V010)
    vlist = [{"token": t, "count": c, "in_v010": in_v010(t), "examples": ex[t]} for t, c in verbs.most_common(top)]
    glist = [{"gram": g, "count": c, "examples": ex[g]} for g, c in grams.most_common(top) if c >= 3]
    until = max((r["ts"] for r in acc if r.get("ts")), default=None)
    d = {"built_at": datetime.now(timezone.utc).isoformat(), "source_until": until, "n_prompts": len(acc),
         "note": "분류기가 아니다. 빈도 목록이다. 작업 종류 대응은 사람이 붙인다. source_until 이후 프롬프트가 시험 집합.",
         "verbs": vlist, "bigrams": glist,
         "corpus_sha256": hashlib.sha256("".join(r["text"] for r in acc).encode()).hexdigest()}
    (out / "dict.json").write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    covered = sum(1 for r in acc if any(t.endswith(ENDINGS) and in_v010(t) for t in tokens(r["text"])))
    md = [f"# 개인 사전 초안 — {len(acc)}개 프롬프트 · {until[:10] if until else '?'}까지", "",
          "분류기가 아니다. 이 사람이 실제로 쓰는 말의 빈도 목록이다. **일반 사전에 있음**은 v0.1.0 동사가 그 토큰 안에 있다는 뜻.", "",
          f"[MEASURED] v0.1.0 동사가 든 서술어를 하나라도 가진 프롬프트: {covered}/{len(acc)} ({100*covered/len(acc):.0f}%)", "",
          "## 동사 후보 (빈도순)", "", "| 토큰 | 횟수 | 일반 사전에 | 예 |", "|---|---|---|---|",
          *[f"| {v['token']} | {v['count']} | {'있음' if v['in_v010'] else '**없음**'} | {v['examples'][0]} |" for v in vlist], "",
          "## 자주 붙는 두 단어 (3회 이상)", "", "| 구 | 횟수 | 예 |", "|---|---|---|",
          *[f"| {g['gram']} | {g['count']} | {g['examples'][0]} |" for g in glist]]
    (out / "dict.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(md[4]); print()
    print("동사 후보 상위:", " · ".join(f"{v['token']}({v['count']}{'' if v['in_v010'] else '*'})" for v in vlist[:18]))
    print("  (*는 일반 사전에 없는 것)")
    print("두 단어 구 상위:", " · ".join(f"{g['gram']}({g['count']})" for g in glist[:10]))
    print(f"→ {out/'dict.md'}")

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); s = ap.add_subparsers(dest="cmd", required=True)
    b = s.add_parser("build"); b.add_argument("project_root"); b.add_argument("--top", type=int, default=30)
    a = ap.parse_args(); build(norm(a.project_root), a.top)
