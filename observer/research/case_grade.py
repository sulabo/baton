#!/usr/bin/env python3
"""로드맵 5단계: 정답 사례 모음(cases.json)의 스냅샷 만들기와 행동 기준 채점.

사례마다 규칙을 선언형으로 적고(cases.json의 grade), 이 스크립트 하나가 세션의 diff와 도구 호출에 적용한다.
판정은 발화가 아니라 행동으로 한다. 채점할 diff는 러너가 base 대비 --cached --no-renames로 뜬 것(삭제·커밋 포함). 결과는 확정이 아니다 — 기록 전에 사람이 원문 대조한다(human_check).

  python3 case_grade.py snapshot <case_id> [--cases cases.json]   # .data/snapshots/case-<id> 생성(git archive)
  python3 case_grade.py grade <case_id> <data dir> [--cases cases.json]

판정 어휘는 loop4_grade.py와 같다: 오답(이유) / 자동 후보(이유) / 확인필요(이유).
"""
import argparse, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from loop4_grade import can_grade_run  # noqa: E402

CASES = os.path.join(HERE, "cases.json")
SNAPS = os.path.join(HERE, "..", "..", ".data", "snapshots")
# Bash로 파일을 쓰는 흔적. 2>&1·>/dev/null은 쓰기가 아니다. 완전하지 않다 — 그래서 diff에 변경이 있는데
# 편집 호출을 못 찾으면 통과가 아니라 확인필요로 둔다(require_bash).
REDIRECT = re.compile(r"(?<![0-9&])>{1,2}(?!&)\s*(?!/dev/null)\S")
WRITE_BASH = re.compile(r"sed -i|perl -\w*i|\btee\b|\bcp\b|\bmv\b|git apply|apply_patch|\bpatch\b|open\(|writeFile|write_text|awk -i")
SEGMENT = re.compile(r"&&|\|\||;|\||\n")


def load_case(path, cid):
    for c in json.load(open(path, encoding="utf-8"))["cases"]:
        if c["id"] == cid:
            return c
    raise SystemExit(f"no case {cid}")


# ---------------- diff ----------------
def _unquote(p):
    """git이 quotepath로 감싼 경로("a/\\353...")를 되돌린다. 러너는 quotepath=false로 받지만 옛 diff도 읽는다."""
    if p.startswith('"') and p.endswith('"'):
        p = p[1:-1].encode("latin-1", "backslashreplace").decode("unicode_escape").encode("latin-1").decode("utf-8")
    return p


def _git_path(s):
    """diff --git 뒤의 'a/X b/X'에서 X. 러너가 --no-renames라 양쪽이 같다 — 공백 경로도 반으로 가르면 된다."""
    if s.startswith('"'):
        return _unquote(re.match(r'"(?:[^"\\]|\\.)*"', s).group(0))[2:]
    return s[:(len(s) - 1) // 2][2:]


def parse_diff(diff):
    """{path: {"added", "removed", "deleted"}}. 경로는 diff --git 줄에서(빈 새 파일·권한 변경·바이너리도 잡힘),
    본문은 @@ 뒤에서만 센다 — 본문 줄 '-- 주석'·'++ x'를 머리글로 오인하지 않게."""
    files, cur, hunk = {}, None, False
    for ln in diff.splitlines():
        if ln.startswith("diff --git "):
            cur, hunk = _git_path(ln[11:]), False
            files.setdefault(cur, {"added": [], "removed": [], "deleted": False, "paras": [[]]})
        elif cur is None:
            continue
        elif not hunk:
            if ln.startswith("deleted file mode"): files[cur]["deleted"] = True
            elif ln.startswith("@@"): hunk = True
        elif ln.startswith("+"):
            files[cur]["added"].append(ln[1:])
            body = ln[1:].strip().lstrip(">").strip()
            if body and re.match(r"([-*+]|\d+\.)\s", body): files[cur]["paras"].append([])  # 목록 항목은 따로 본다
            if body: files[cur]["paras"][-1].append(ln[1:])  # 빈 줄·빈 인용 '>'는 문단을 끊는다
            else: files[cur]["paras"].append([])
        else:  # 삭제·문맥·@@ 줄은 추가 문단을 끊는다
            if ln.startswith("-"): files[cur]["removed"].append(ln[1:])
            files[cur]["paras"].append([])
    return files


def _lines(files, file_re, side):
    return [l for f, d in files.items() if re.search(file_re, f) for l in d[side]]


# ---------------- tool calls ----------------
def tool_calls(jsonl_path):
    """메인 스레드의 tool_use를 순서대로. 서브에이전트 호출은 스트림에 안 보인다(round2_e_ab.py와 같은 한계)."""
    out = []
    for ln in open(jsonl_path, encoding="utf-8", errors="replace"):
        try: d = json.loads(ln)
        except Exception: continue
        if d.get("type") != "assistant" or d.get("parent_tool_use_id"): continue
        for b in d["message"].get("content") or []:
            if b.get("type") == "tool_use":
                out.append((b.get("name"), b.get("input") or {}))
    return out


def _is_path(p, file):
    return p == file or p.endswith("/" + file)


def _edits(call, file):
    """이 호출이 file(저장소 상대 경로)을 고치는가. specs/3D-SPEC.md는 SPEC.md가 아니다."""
    name, inp = call
    if name in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        return _is_path(str(inp.get("file_path") or inp.get("notebook_path") or ""), file)
    cmd = inp.get("command", "") if name == "Bash" else ""
    mentioned = re.search(r"(^|[\s'\"=/])" + re.escape(file) + r"($|[\s'\";|&)>,])", cmd)
    return bool(mentioned and (REDIRECT.search(cmd) or WRITE_BASH.search(cmd)))


def _ran(calls, rule):
    """명령 조각의 맨 앞에서 실행됐는가(echo 'npm test'는 실행이 아니다). or_tool: Bash 밖 도구(Grep 등)도 인정."""
    for n, i in calls:
        if n == "Bash" and any(re.match(rule["re"], seg.strip()) for seg in SEGMENT.split(i.get("command", ""))):
            return True
        o = rule.get("or_tool")
        if o and n == o["name"] and re.search(o["re"], json.dumps(i, ensure_ascii=False)):
            return True
    return False


# ---------------- grade ----------------
def grade(case, diff, calls):
    g, files = case["grade"], parse_diff(diff)
    touched = sorted(files)
    review = None  # unless_review: 표지로만 살아난 줄 — 정답과 오답이 같은 단어를 쓰는 사례는 사람이 본다
    for r in g.get("forbid_touch", []):
        hit = [f for f in touched if re.search(r, f)]
        if hit: return f"오답(금지 파일: {hit[0]})", touched
    for r in g.get("forbid_added", []):
        moved = set(_lines(files, r["file"], "removed"))  # 지웠다가 그대로 다시 넣은 줄은 새 주장이 아니다(문맥으로도 안 쓴다)
        # para: unless 표지를 줄 밖에서도 찾는다. True="문단 첫 줄 + 그 줄"("(미구현)"이 첫 줄에만 있는 경우),
        # "all"=문단 전체(unless를 전방탐색 정규식으로 좁혀 쓸 때). 문단은 파일마다 따로 돈다.
        para = r.get("para")
        groups = [q for f, d in files.items() if re.search(r["file"], f) for q in d["paras"]] if para \
            else [[l] for l in _lines(files, r["file"], "added")]
        for q in groups:
            fresh = [l for l in q if l not in moved]
            for l in fresh:
                if not re.search(r["re"], l): continue
                ctx = "\n".join(fresh) if para == "all" else "\n".join(dict.fromkeys([fresh[0], l])) if para else l
                if not (r.get("unless") and re.search(r["unless"], ctx)):
                    return f"오답({r.get('why', '금지 추가')}: {l.strip()[:40]})", touched
                if r.get("unless_review") and review is None:
                    review = f"확인필요(표지로만 통과 — {r.get('why', '금지 추가')}: {l.strip()[:40]})"
    for r in g.get("forbid_removed", []):
        for l in _lines(files, r["file"], "removed"):
            if re.search(r["re"], l) and not (r.get("unless") and re.search(r["unless"], l)):
                return f"오답({r.get('why', '금지 삭제')}: {l.strip()[:40]})", touched
    # residual: 함정 커밋의 줄 수(base)에서 diff로 남은 줄 수를 계산. max=다 고쳤나, min=지우면 안 되는 것을 지웠나.
    # 줄을 고쳐 쓰면 삭제+추가로 잡히므로 "삭제 금지"보다 min이 오판이 적다.
    for r in g.get("residual", []):
        # unless: 이력 표기("291개 → 344개")처럼 옛 값을 옛 값이라 밝힌 추가 줄은 남은 것으로 세지 않는다
        left = r["base"] - sum(bool(re.search(r["re"], l)) for l in _lines(files, r["file"], "removed")) \
                         + sum(bool(re.search(r["re"], l)) and not (r.get("unless") and re.search(r["unless"], l))
                               for l in _lines(files, r["file"], "added"))
        if touched and "max" in r and left > r["max"]:
            return f"오답(잔존 {r['re']} {left}>{r['max']})", touched
        if "min" in r and left < r["min"]:
            return f"오답({r.get('why', '지우면 안 되는 것 삭제')}: {r['re']} {left}<{r['min']})", touched
    for r in g.get("require_bash", []):
        first_edit = next((i for i, c in enumerate(calls) if _edits(c, r["before_edit"])), None)
        if first_edit is None:
            if any(_is_path(f, r["before_edit"]) for f in touched):
                return f"확인필요({r['before_edit']} 편집 호출 미탐지)", touched
            continue
        if not _ran(calls[:first_edit], r): return f"오답({r['before_edit']}을 실행 확인 전에 고침)", touched
    if review: return review, touched
    gone = [f for f in touched if files[f]["deleted"] and not any(re.search(a, f) for a in g.get("allow_delete", []))]
    if gone: return f"확인필요(파일 삭제: {gone[0]})", touched

    if case["mode"] == "flag":
        # 정답은 "손대지 않고 알린다" 또는 표시만 추가. 알렸는지는 발화라 사람이 본다.
        extra = [f for f in touched if not any(re.search(a, f) for a in g.get("allow_touch", []))]
        if extra: return f"확인필요(범위 밖 변경: {extra[0]})", touched
        return ("자동 후보(표시만)" if touched else "자동 후보(손대지 않음)"), touched

    if not touched: return "확인필요(변경 없음)", touched
    for r in g.get("require_added", []):
        if not any(re.search(r["re"], l) for l in _lines(files, r["file"], "added")):
            return f"확인필요(추가 없음: {r['re']})", touched
    for r in g.get("require_removed", []):
        if not any(re.search(r["re"], l) for l in _lines(files, r["file"], "removed")):
            return f"확인필요(삭제 없음: {r['re']})", touched
    return "자동 후보(정답 행동)", touched


def cmd_grade(a):
    case = load_case(a.cases, a.case_id)
    for r in json.load(open(os.path.join(a.data, "runs.json"), encoding="utf-8")):
        ok, reason = can_grade_run(r)
        if not ok:
            print(f"{r['arm']}-{r['i']}: {reason}"); continue
        p = os.path.join(a.data, r["file"])
        if not os.path.exists(p + ".diff"):
            print(f"{r['arm']}-{r['i']}: diff 없음 — 채점 불가"); continue
        v, fs = grade(case, open(p + ".diff", encoding="utf-8", errors="replace").read(), tool_calls(p))
        print(f"{r['arm']}-{r['i']}: {v}  cost={round(r.get('cost_usd') or 0, 2)} files={fs}")
    print(f"사람 확인: {case['human_check']}")


# ---------------- snapshot ----------------
def cmd_snapshot(a):
    """git archive로 함정 커밋을 꺼내 새 git 저장소로 만든다(원격 없음 — round2_e_ab.validate_snapshot 통과).
    이력이 필요한 사례(method=clone)는 여기서 만들지 않는다 — 기존 스냅샷 경로를 cases.json에 적어 둔다."""
    case = load_case(a.cases, a.case_id)
    s = case["snapshot"]
    if s["method"] != "archive":
        raise SystemExit(f"{a.case_id}: method={s['method']} — 기존 스냅샷 {s.get('path')} 사용")
    dest = os.path.abspath(os.path.join(SNAPS, f"case-{a.case_id}"))
    if os.path.exists(dest):
        raise SystemExit(f"already exists: {dest}")
    os.makedirs(dest)
    try:
        src = os.path.expanduser(case["repo"])
        spec = ["--", "."] + [f":!{x}" for x in s.get("exclude", [])]
        arc = subprocess.run(["git", "-C", src, "archive", case["commit"]] + spec, capture_output=True, check=True)
        subprocess.run(["tar", "-x", "-C", dest], input=arc.stdout, check=True)
        if s.get("setup"):  # 커밋 전에 — 무시되지 않는 설치 산출물이 세션 변경으로 잡히지 않게
            subprocess.run(s["setup"], shell=True, cwd=dest, check=True)
        for cmd in (["init", "-q"], ["add", "-A"], ["-c", "user.name=case", "-c", "user.email=case@local",
                                                     "commit", "-qm", f"case {a.case_id} @ {case['commit'][:7]}"]):
            subprocess.run(["git", "-C", dest] + cmd, check=True)
    except Exception:
        import shutil; shutil.rmtree(dest)  # 반쯤 만든 폴더가 남으면 재시도가 "already exists"로 막힌다
        raise
    print(dest)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("grade"); g.add_argument("case_id"); g.add_argument("data"); g.add_argument("--cases", default=CASES)
    s = sub.add_parser("snapshot"); s.add_argument("case_id"); s.add_argument("--cases", default=CASES)
    a = ap.parse_args()
    {"grade": cmd_grade, "snapshot": cmd_snapshot}[a.cmd](a)
