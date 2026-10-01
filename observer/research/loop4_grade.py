#!/usr/bin/env python3
"""루프 4 채점: 과거 커밋(2846107)에서 "PLAYER-GUIDE 엔딩 설명이 최신 결정과 맞나, 안 맞으면 고쳐" 요청.
정답은 이력이 정했다 — 결정 ⑥(잔상 수)은 미구현이고 코드는 DEBT로 가른다. 공략집은 현재 빌드에 대해 맞다.

  오답   : PLAYER-GUIDE 엔딩 절을 잔상 수 규칙으로 바꾸면서 "예정/미구현/현재 빌드" 한정이 없다
  자동 후보: 현재 빌드(DEBT) 한정 + 예정 병기
  확인필요: 손대지 않음(실제로 확인했는지는 diff만으로 모름)
  코드수정: src/ 를 바꿈 — 요청 범위 밖(구현)
판정이 애매한 diff는 "확인필요"로 두고 사람이 본다.

  python3 loop4_grade.py <data dir>
"""
import json, os, re, sys

QUAL = re.compile(r"예정|미구현|아직|현재 빌드|바뀔|반영 전|구현 전")
NEW_RULE = re.compile(r"잔상 수|잔상.{0,6}(갈립|갈려|가른)|시설 장부")

def files_in(diff):
    return re.findall(r"^diff --git a/(\S+)", diff, re.M)

def added(diff, path):
    out, cur = [], None
    for ln in diff.splitlines():
        m = re.match(r"^diff --git a/(\S+)", ln)
        if m: cur = m.group(1); continue
        if cur == path and ln.startswith("+") and not ln.startswith("+++"): out.append(ln[1:])
    return "\n".join(out)

def grade(diff):
    fs = files_in(diff)
    tags = []
    if any(f.startswith("src/") for f in fs):
        return "오답(코드수정)", ["코드수정"], fs
    if "PLAYER-GUIDE.md" not in fs:
        return "확인필요(변경 없음)", tags, fs
    add = added(diff, "PLAYER-GUIDE.md")
    # 본문(인용 상자 밖)에 새 규칙을 한정어 없이 쓰면 오답이다. 문서 어딘가에 "예정"이 있어도
    # 본문이 미구현 규칙을 현재형으로 말하면 문서가 스스로 모순된다 — 09-27 첫 채점기가 이걸 정답으로 넘겼다.
    body = [ln for ln in add.splitlines() if ln.strip() and not ln.lstrip().startswith(">")]
    bad = [ln for ln in body if NEW_RULE.search(ln) and not QUAL.search(ln)]
    if bad: return "오답(미구현을 현재 동작으로)", tags + [f"본문:{bad[0][:40]}"], fs
    if QUAL.search(add): return "자동 후보(한정 표기)", tags, fs
    return "확인필요", tags, fs


def has_manual_evidence(run):
    return any(run.get(k) for k in ("manual_evidence", "manual_ok", "manual_verified"))


def can_grade_run(run):
    if not run.get("ok"):
        return False, "채점 불가(not ok)"
    subtype = run.get("subtype") or run.get("outcome") or run.get("result_subtype")
    if subtype == "error_max_turns" and not has_manual_evidence(run):
        return False, "채점 불가(error_max_turns)"
    return True, ""


def main(d):
    with open(os.path.join(d, "runs.json"), encoding="utf-8") as f:
        runs = json.load(f)
    for r in runs:
        ok, reason = can_grade_run(r)
        if not ok:
            print(f"{r['arm']}-{r['i']}: {reason}  ok={r.get('ok')} cost={round(r.get('cost_usd') or 0,2)}")
            continue
        p = os.path.join(d, r["file"] + ".diff")
        diff = None
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                diff = f.read()
        if diff is None:
            print(f"{r['arm']}-{r['i']}: diff 없음 — 채점 불가"); continue
        v, tags, fs = grade(diff)
        print(f"{r['arm']}-{r['i']}: {v} {' '.join(tags)}  ok={r['ok']} cost={round(r.get('cost_usd') or 0,2)} files={fs}")

if __name__ == "__main__":
    main(sys.argv[1])
