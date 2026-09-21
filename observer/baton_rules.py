#!/usr/bin/env python3
"""BATON V0 — STEP 1·2. 규칙 초안과 분포 채점. 라벨 없이도 돈다(정확도만 라벨이 필요).

  baton_rules.py rules <project_root>   .baton/rules.json  (구조에서만. 과거 기록을 보지 않는다)
  baton_rules.py score <project_root>   .baton/calibration.md  (MATCHED/AMBIGUOUS/NO_MATCH 분포)

전역 규칙 v0.1.0은 내장·고정. 도메인은 unconfigured로 시작하고 evidence 적중만 보고한다.
YAML 의존을 피하려고 V0는 rules.json 을 쓴다 (스펙의 rules.yaml 과 형식만 다르고 내용은 같다).
"""
import glob, hashlib, json, os, re, subprocess, sys, unicodedata
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
GLOBAL_RULES = {                       # 제품 내장. 프로젝트를 보기 전에 고정. 바꾸지 않는다.
    "version": "v0.1.0",
    "task_types": {
        "debugging":      ["고쳐", "안 돼", "안돼", "에러", "오류", "버그", "실패", "깨졌", "왜 안"],
        "implementation": ["만들어", "추가해", "구현", "넣어", "붙여", "생성"],
        "design":         ["설계", "구조", "아키텍처", "어떻게 할지", "방향"],
        "question":       ["뭐야", "뭔데", "왜", "어때", "설명해", "알려줘", "이해"],
        "refactor":       ["리팩", "정리해", "깔끔", "줄여", "단순"],
        "test":           ["테스트", "검증", "확인해", "돌려"],
        "documentation":  ["문서", "README", "적어", "기록", "정리본"],
    },
}
GOV = {"AGENTS.md", "CLAUDE.md", "DECISIONS.md", "TODO.md", "HANDOFF.md", "CONCEPTS.md"}

def norm(p): return unicodedata.normalize("NFC", str(Path(p).expanduser().resolve()))
def sha(s): return hashlib.sha256(s.encode("utf-8")).hexdigest()
def now(): return datetime.now(timezone.utc).isoformat()

def project_evidence(root):
    """개념 지도 절 이름 · AGENTS.md 절 제목 · 최상위 폴더. 과거 기록은 보지 않는다."""
    ev = {"from_concepts": [], "from_agents_md": [], "from_dirs": []}
    cm = next((p for p in glob.glob(f"{root}/**/CONCEPTS.md", recursive=True) if "node_modules" not in p), None)
    if cm:
        out = subprocess.run([sys.executable, str(HERE.parent / "lib" / "concepts.py"), cm, "sections"],
                             capture_output=True, text=True).stdout
        ev["from_concepts"] = [l.split("\t", 1)[1].split("—")[0].strip() for l in out.splitlines() if "\t" in l]
    ag = Path(root) / "AGENTS.md"
    if ag.exists():
        ev["from_agents_md"] = [re.sub(r"[（(].*$", "", l[3:]).strip() for l in ag.read_text(encoding="utf-8").splitlines() if l.startswith("## ")]
    ev["from_dirs"] = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))
                             and not d.startswith(".") and d not in ("node_modules", "dist", "build"))
    return ev

def cmd_rules(a):
    root = norm(a.project_root); out = Path(root) / ".baton"
    rules = {"global_rules": GLOBAL_RULES, "domains": {"status": "unconfigured"},
             "domain_evidence": project_evidence(root), "generated_at": now(),
             "note": "domain_evidence는 도메인이 아니라 어휘다. 도메인은 사람이 configure에서 정한다."}
    out.mkdir(exist_ok=True)
    (out / "rules.json").write_text(json.dumps(rules, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ev = rules["domain_evidence"]
    print(f"rules.json · 전역 {GLOBAL_RULES['version']} · 개념 {len(ev['from_concepts'])} · AGENTS 절 {len(ev['from_agents_md'])} · 폴더 {len(ev['from_dirs'])}")
    print(f"  개념 예: {ev['from_concepts'][:4]}")

def classify_task_type(text, rules):
    hits = {t: [v for v in verbs if v in text] for t, verbs in rules["global_rules"]["task_types"].items()}
    hit_types = [t for t, v in hits.items() if v]
    if len(hit_types) == 1: return "MATCHED", hit_types[0], hits[hit_types[0]]
    if len(hit_types) > 1:  return "AMBIGUOUS", hit_types, {t: hits[t] for t in hit_types}
    return "NO_MATCH", None, []

def evidence_hits(text, ev):
    return {src: [t for t in terms if len(t) >= 2 and t.lower() in text.lower()] for src, terms in ev.items()}

def cmd_score(a):
    root = norm(a.project_root); out = Path(root) / ".baton"
    rules = json.loads((out / "rules.json").read_text(encoding="utf-8"))
    run = json.loads((out / "run.json").read_text(encoding="utf-8"))
    rows = [json.loads(l) for l in open(out / "tasks.jsonl", encoding="utf-8") if l.strip()]
    acc = [r for r in rows if r["extractor_decision"] == "accepted"]
    dist, amb_ex, no_ex, ev_any = {"MATCHED": 0, "AMBIGUOUS": 0, "NO_MATCH": 0}, [], [], 0
    per_type = {}
    for r in acc:
        st, val, why = classify_task_type(r["text"], rules)
        dist[st] += 1
        if st == "MATCHED": per_type[val] = per_type.get(val, 0) + 1
        if st == "AMBIGUOUS" and len(amb_ex) < 5: amb_ex.append((r["text"][:60], val))
        if st == "NO_MATCH" and len(no_ex) < 5: no_ex.append(r["text"][:60])
        if any(evidence_hits(r["text"], rules["domain_evidence"]).values()): ev_any += 1
    n = len(acc); pct = lambda k: f"{100*dist[k]/n:.0f}%"
    fp = {"rules_sha256": sha(json.dumps(rules, sort_keys=True, ensure_ascii=False)),
          "corpus_sha256": sha("".join(r["id"] for r in acc)), "script_sha256": sha(open(__file__, encoding="utf-8").read())}
    md = [f"# calibration — run #1", "",
          f"evaluation_status BASELINE · evaluation_type operator-informed retrospective",
          f"global_rules {rules['global_rules']['version']} · domains {rules['domains']['status']}",
          f"rules_sha256 {fp['rules_sha256'][:12]} · corpus_sha256 {fp['corpus_sha256'][:12]} · script_sha256 {fp['script_sha256'][:12]}",
          f"source_manifest_sha256 {run['source_manifest_sha256'][:12]} · cutoff {run['measurement_cutoff'][:10]} · 생성 {now()[:19]}", "",
          "**정확도는 없다. 라벨이 없다.** 아래는 규칙이 스스로 어떻게 판단했는지의 분포다.",
          "전역 규칙 점수는 author-exposed baseline이다. 이 문서 작성자는 이 말뭉치를 봤다.", "",
          f"## 전역 규칙 — 작업 종류  [MEASURED] n={n} (accepted 프롬프트 전부)", "",
          f"| 상태 | 건수 | 비율 |", "|---|---|---|",
          f"| MATCHED | {dist['MATCHED']} | {pct('MATCHED')} |",
          f"| AMBIGUOUS | {dist['AMBIGUOUS']} | {pct('AMBIGUOUS')} |",
          f"| NO_MATCH | {dist['NO_MATCH']} | {pct('NO_MATCH')} |", "",
          "MATCHED 내 종류: " + " · ".join(f"{k} {v}" for k, v in sorted(per_type.items(), key=lambda x: -x[1])), "",
          "AMBIGUOUS 예시 (규칙이 둘 이상에 걸림):", *[f"- {t} → {v}" for t, v in amb_ex], "",
          "NO_MATCH 예시 (규칙 어휘에 없음):", *[f"- {t}" for t in no_ex], "",
          f"## 프로젝트 규칙 — 도메인", "",
          f"domains.status = unconfigured → 도메인 채점 없음. 사람이 configure 하기 전이다.",
          f"domain_evidence 어휘가 하나라도 등장한 프롬프트: {ev_any} / {n} ({100*ev_any/n:.0f}%)  [MEASURED]", "",
          "## 다음", "",
          "- AMBIGUOUS와 NO_MATCH 예시를 보고 규칙을 고치면 run #2이고 evaluation_status는 TUNED_ON_SEEN_CORPUS다.",
          "- 정확도를 알려면 0-A·0-B·2 라벨이 필요하다. 필수가 아니다. 분포만으로 맹점은 보인다."]
    (out / "calibration.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md[9:17])); print(f"  evidence 등장 {ev_any}/{n} · → {out/'calibration.md'}")

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("rules", "score"): sub.add_parser(c).add_argument("project_root")
    a = ap.parse_args(); {"rules": cmd_rules, "score": cmd_score}[a.cmd](a)
