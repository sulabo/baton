#!/usr/bin/env python3
"""로드맵 1단계: 실제 대화형 세션 기록에서 세션별 API 호출 수·입력 토큰 합·첫 호출 컨텍스트를 뽑아 주별로 묶는다.
   usage_week.py [프로젝트 폴더 glob 조각] [--since YYYY-MM-DD] [--sessions]

   - 대상: ~/.claude/projects/<pat>/*.jsonl (메인 세션만 — 서브에이전트 기록은 <세션>/subagents/ 아래라 빠진다)
     같은 세션 파일이 폴더 이름 변경으로 두 폴더에 복사돼 있다(game·game-old 13개) — 세션 id(파일 이름)로 한 번만 센다
   - 제외: cwd가 baton `.data/` 아래거나 임시 폴더인 세션, entrypoint가 sdk로 시작하는 세션(`claude -p`·SDK 스크립트) — 실험·자동 실행이다
   - 입력 토큰 = API 호출별 input+cache_creation+cache_read 합. 같은 호출이 블록마다 여러 줄로 찍히므로 message.id로 한 번만 센다
   - "상태 세션" = 첫 사람 프롬프트가 훅 TRIGGER에 맞는 세션. "주입" = UserPromptSubmit 훅 기록에 `[baton] 아래는`이 있는 세션
     첫 프롬프트가 다른 이름의 인계서(HANDOFF-x.md 등)를 가리키면 훅이 넣지 않는 파일이라 상태 세션에서 빼고 따로 센다
   - 여는 구간: 실사용 세션은 호출 중앙값 115라(09-29) 세션 전체로는 주입 효과(호출 2~3개 절감)가 묻힌다.
     그래서 첫 OPEN개 호출의 토큰 합과, 그 안에서 에이전트가 HANDOFF.md를 실제로 읽었는지를 따로 센다.
     읽기 = Read 도구 또는 cat·sed·head 같은 읽기 명령. `ls HANDOFF.md`·`find -newer HANDOFF.md`처럼 이름만 나온 것은 읽기가 아니다
     (주입 세션 11개 중 5개가 이름만 나와 옛 부분 문자열 판정이 재독으로 셌다 — 09-30 리뷰). 일부만 읽은 것(offset·줄 범위)은 따로 센다
   - 날짜·주는 로컬 시간대(KST)로 자른다
   - 설치 전에는 주입이 0이어야 한다. 0이 아니면 러너 세션이 섞였다는 뜻이니 제외 규칙부터 본다"""
import argparse, glob, importlib.util, json, os, re, statistics, sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "measure"))
from extract_prompts import human_text

_spec = importlib.util.spec_from_file_location("handoff_inject", os.path.join(REPO, "hooks", "handoff-inject.py"))
_hook = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_hook)
TRIGGER = _hook.TRIGGER
MARK = "[baton] 아래는"
OPEN = 5
TOKEN_KEYS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
NOT_HUMAN = ("This session is being continued", "Another Claude session sent", "[Request interrupted")
OTHER_HANDOFF = re.compile(r"HANDOFF[-_][^\s`'\"]+")  # 프롬프트는 .md를 빼고 말하기도 한다("HANDOFF-draft 파일을 읽고")
READ_CMD = re.compile(r"^\s*(?:rtk\s+(?:proxy\s+)?)?(cat|sed|head|tail|less|more|grep|rg|bat|nl|awk)\b(.*)$", re.S)
NARROW = re.compile(r"^\s*(?:rtk\s+(?:proxy\s+)?)?(head|tail|grep|rg|sed\s+-n)\b")
WRITE = re.compile(r">>?\s*\S*HANDOFF\.md|\bsed\s+-i\b")
HANDOFF_ARG = re.compile(r"(?:^|[\s/'\"])HANDOFF\.md(?:$|[\s'\"])")


def experimental(cwd):
    return not cwd or "/.data/" in cwd or cwd.startswith(("/private/tmp/", "/tmp/", "/private/var/folders/"))


def handoff_read(block):
    """tool_use 하나가 HANDOFF.md를 읽었나. 'full'·'partial'·None."""
    if block.get("type") != "tool_use":
        return None
    inp = block.get("input") or {}
    if block.get("name") == "Read":
        if os.path.basename(str(inp.get("file_path", ""))) != "HANDOFF.md":
            return None
        return "partial" if inp.get("offset") or inp.get("limit") else "full"
    if block.get("name") == "Bash":
        best = None
        for cmd in re.split(r"\|\||&&|[;&\n]", str(inp.get("command", ""))):
            stages = cmd.split("|")
            for i, seg in enumerate(stages):
                m = READ_CMD.match(seg)
                if not m or not HANDOFF_ARG.search(m.group(2)) or WRITE.search(seg):
                    continue  # 이름만 나오거나, HANDOFF.md에 쓰는 명령(cat > · sed -i)은 읽기가 아니다
                narrow = m.group(1) in ("head", "tail", "grep", "rg") or (m.group(1) == "sed" and "-n" in m.group(2)) \
                    or any(NARROW.match(t) for t in stages[i + 1:])  # cat HANDOFF.md | head -250
                if not narrow: return "full"
                best = "partial"
        return best
    return None


def session_of(path):
    """세션 하나 요약. 메인 스레드 API 호출이 없거나 사람 프롬프트가 없으면 None."""
    calls, first_prompt, start, cwd, entry, injected, reread, prompts = {}, None, None, None, None, False, None, []
    with open(path, encoding="utf-8", errors="ignore") as fh:
        lines = fh.readlines()
    for ln in lines:
        try: d = json.loads(ln)
        except json.JSONDecodeError: continue
        cwd = cwd or d.get("cwd")
        a = d.get("attachment") or {}
        if a.get("hookEvent") == "UserPromptSubmit" and MARK in json.dumps(a.get("content"), ensure_ascii=False):
            injected = True
        if d.get("isSidechain"): continue
        if d.get("type") == "user" and not d.get("isMeta") and not d.get("isCompactSummary"):
            text = human_text(d.get("message", {}).get("content"))
            if text and not text.startswith("<") and not text.startswith(NOT_HUMAN):
                prompts.append(text)  # 사람 프롬프트 전부(lib/setup_scan.py가 트리거 후보가 걸릴 프롬프트 수를 센다)
                if first_prompt is None:
                    first_prompt, entry = text, d.get("entrypoint")
                    try: start = datetime.fromisoformat(d.get("timestamp", "").replace("Z", "+00:00")).astimezone()
                    except ValueError: pass
        if d.get("type") == "assistant":
            m = d.get("message") or {}
            if m.get("model") == "<synthetic>": continue
            mid = m.get("id") or d.get("uuid")
            if mid not in calls:
                u = m.get("usage") or {}
                calls[mid] = sum(u.get(k, 0) or 0 for k in TOKEN_KEYS)
            if len(calls) <= OPEN and reread != "full":
                for b in m.get("content") or []:
                    kind = isinstance(b, dict) and handoff_read(b)
                    if kind: reread = "full" if kind == "full" else reread or "partial"
    if not calls or first_prompt is None:
        return None
    other = bool(OTHER_HANDOFF.search(first_prompt))
    return {
        "file": path, "cwd": cwd, "entry": entry, "start": start, "calls": len(calls), "prompt": first_prompt, "prompts": prompts,
        "tokens": sum(calls.values()), "first": next(iter(calls.values())),
        "open": sum(list(calls.values())[:OPEN]), "reread": reread,
        "status": bool(TRIGGER.search(first_prompt)) and not other, "other_handoff": other, "injected": injected,
    }


def collect(pat="*", since=None, files=None):
    """files를 주면 glob 대신 그 세션 파일들만 고른다(lib/setup_scan.py가 저장소별 파일 목록을 넘긴다)."""
    out, by_id = [], {}
    skipped = {"experimental": 0, "non_cli": 0, "empty": 0, "duplicate": 0, "before_since": 0}
    for f in files if files is not None else glob.glob(os.path.expanduser(f"~/.claude/projects/{pat}/*.jsonl")):
        by_id.setdefault(os.path.basename(f), []).append(f)
    for sid in sorted(by_id):
        copies = sorted(by_id[sid], key=os.path.getsize, reverse=True)  # 폴더 이름 변경으로 생긴 사본 — 가장 긴 것을 쓴다
        skipped["duplicate"] += len(copies) - 1
        f = copies[0]
        s = session_of(f)
        if s is None: skipped["empty"] += 1; continue
        if experimental(s["cwd"]): skipped["experimental"] += 1; continue
        if not s["entry"] or s["entry"].startswith("sdk"): skipped["non_cli"] += 1; continue  # claude -p·SDK. IDE 같은 대화형은 남긴다
        if since and s["start"] and s["start"].date() < since: skipped["before_since"] += 1; continue
        out.append(s)
    return out, skipped


def week_table(sessions):
    """주 × 주입 여부로 상태 세션을 나눈다. 설치 뒤에는 주입 안 된 상태 세션(HANDOFF.md 없는 저장소 등)이 섞이기 때문이다."""
    rows = {}
    for s in sessions:
        if not s["start"]: continue
        y, w, _ = s["start"].isocalendar()
        rows.setdefault(f"{y}-W{w:02d}", []).append(s)
    lines = ["| 주 | 세션 | 상태 세션(주입/비주입) | 다른 인계서 | 묶음 | 호출 중앙값 | 토큰 중앙값 | 첫 호출 | 여는 구간 토큰 | 재독(일부) |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for wk in sorted(rows):
        ss = rows[wk]; st = [s for s in ss if s["status"]]
        inj = [s for s in st if s["injected"]]
        head = f"| {wk} | {len(ss)} | {len(st)} ({len(inj)}/{len(st) - len(inj)}) | {sum(s['other_handoff'] for s in ss)} "
        groups = [("주입", inj), ("비주입", [s for s in st if not s["injected"]])]
        groups = [(n, g) for n, g in groups if g] or [("-", [])]
        for i, (name, g) in enumerate(groups):
            med = lambda k: f"{statistics.median(s[k] for s in g):,.0f}" if g else "-"
            full = sum(s["reread"] == "full" for s in g); part = sum(s["reread"] == "partial" for s in g)
            lines.append((head if i == 0 else "| | | | ") +
                         f"| {name} | {med('calls')} | {med('tokens')} | {med('first')} | {med('open')} | {full + part}/{len(g)} ({part}) |")
    return "\n".join(lines)


def main(argv):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("pattern", nargs="?", default="*")
    p.add_argument("--since", type=lambda v: datetime.fromisoformat(v).date(), help="로컬 날짜. 주 경계(월요일)로 주면 첫 주가 잘리지 않는다")
    p.add_argument("--sessions", action="store_true")
    a = p.parse_args(argv)
    sessions, sk = collect(a.pattern, a.since)
    print("[MEASURED] 대화형 세션 기록 · 메인 스레드만 · 서브에이전트 토큰 미포함 · 로컬 시간대")
    print(f"  pattern {a.pattern!r} · 세션 {len(sessions)} · 제외: 실험 폴더 {sk['experimental']} · cli 아님 {sk['non_cli']}"
          f" · 중복 파일 {sk['duplicate']} · 호출/프롬프트 없음 {sk['empty']} · --since 이전 {sk['before_since']}")
    print(week_table(sessions))
    if a.sessions:
        for s in sorted((s for s in sessions if s["start"]), key=lambda s: s["start"]):
            if s["status"]:
                print(f"  {s['start']:%m-%d %H:%M} calls={s['calls']} tokens={s['tokens']:,} first={s['first']:,} "
                      f"open={s['open']:,} reread={s['reread']} inj={s['injected']} {s['cwd']}")


if __name__ == "__main__":
    main(sys.argv[1:])
