#!/usr/bin/env python3
"""인계서 검사기 — 북극성 길 단계 3 "Handoff Validator". HANDOFF.md가 다음 세션이 받기 좋은 모양인지 규칙으로 본다.

보는 것: 필수 8절(스킬 템플릿) · 200줄(소유자 결정 09-22) · 9,000자(넘치면 Claude Code가 훅 출력을 파일로 뺀다) ·
긴 코드 블록 · 전체 diff · 비밀값 · 홈 절대경로(10-01 공개 사고에서 새어 나간 종류).
찾은 값 자체는 출력하지 않는다 — 줄 번호와 종류만. 비밀값을 로그·맥락에 다시 옮기지 않으려고.

쓰기: python3 lib/handoff_check.py [HANDOFF.md 경로] — 문제가 있으면 한 줄씩 출력하고 종료 코드 1.
"""
import os, re, sys

MAX_LINES = 200
MAX_CHARS = 9000
MAX_CODE_LINES = 20  # ponytail: 정본 26절의 "긴 코드 블록" 수치가 저장소에 없어 정한 기본값. 실사용에서 걸리는 분포를 보고 조정

# (절 제목이 이 말 중 하나로 시작하면 그 절이 있다고 본다, 보고할 절 이름). "## E. 실패한 접근법"처럼 번호가 붙어도 받는다.
SECTIONS = [
    (("목표",), "목표와 완료 조건"),
    (("확인된 사실",), "확인된 사실과 결정"),
    (("관련 파일",), "관련 파일·심볼"),
    (("이미 한 변경",), "이미 한 변경"),
    (("실패한 접근",), "실패한 접근법"),
    (("검증 증거",), "검증 증거"),
    (("남은 리스크", "다음 행동"), "남은 리스크와 다음 행동"),
    (("승격 후보",), "승격 후보"),
]

HEADING = re.compile(r"^#{2,4}\s+(?:\*\*)?(?:[A-Za-z0-9]{1,3}[.)]\s*)?(.*)")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
DIFF = re.compile(r"^(diff --git |index [0-9a-f]{7,}\.\.[0-9a-f]{7,}|@@ -\d+(,\d+)? \+\d+(,\d+)? @@)")
# 값은 글자와 숫자가 함께 있어야 비밀값으로 본다 — os.environ·refresh_token.py 같은 코드 이름과 "token 수" 같은 산문을 거르려고
VALUE = r"['\"]?(?=[A-Za-z0-9_\-/+=]*[A-Za-z])(?=[A-Za-z0-9_\-/+=]*\d)[A-Za-z0-9_\-/+=]{8,}(?![A-Za-z0-9_(\[]|\.[A-Za-z_(\[])"  # 뒤에 한글 조사·마침표가 와도 잡는다
SECRETS = [
    ("비밀 키 블록", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("API 토큰", re.compile(r"(?<![\w-])(sk-(ant-)?(?=[A-Za-z0-9_-]*\d)[A-Za-z0-9_-]{32,}|sk_(live|test)_[A-Za-z0-9]{20,}"
                          r"|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|glpat-[A-Za-z0-9_-]{20,}"
                          r"|AKIA[0-9A-Z]{16}|xox[abprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{35}"
                          r"|eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.)")),
    # DB_PASSWORD=… 처럼 앞에 이름이 붙은 환경변수도 잡는다(\b는 _ 뒤에서 안 걸린다)
    ("비밀번호·키 대입", re.compile(r"(?i)(?<![A-Za-z0-9])[A-Za-z0-9_]{0,40}?(password|passwd|secret|api[_-]?key|token|비밀번호|패스워드|토큰)\s*[:=：]\s*" + VALUE)),
    ("홈 절대경로", re.compile(r"(?:(?<![A-Za-z0-9_.~/])|(?<=file://))((/Users/|/home/)(?!Shared\b)[^/\s`'\"]+|/root/)|(?i:[a-z]:\\users\\)")),
]


def check(text, strict=True):
    """문제 목록(사람이 읽을 한 줄씩). 없으면 빈 목록.
    strict=False(훅): 필수 절 검사는 baton 형식으로 보이는 인계서(제목 "Session Handoff" 또는 필수 절 3개 이상)에만 한다 —
    다른 형식의 HANDOFF.md를 이 템플릿으로 고쳐 쓰게 밀지 않으려고. 길이·비밀값·경로 검사는 늘 한다."""
    lines = text.splitlines()
    out = []

    heads, fence = [], None  # fence: 열린 코드 블록의 (줄 번호, 표지 문자, 길이)
    diff_lines = []
    for i, ln in enumerate(lines, 1):
        f = FENCE.match(ln)
        if fence is None:
            if f:
                fence = (i, f.group(1)[0], len(f.group(1)))
            elif HEADING.match(ln):
                heads.append(HEADING.match(ln).group(1))  # 코드 블록 안의 제목(템플릿 예시 등)은 절로 세지 않는다
        elif f and f.group(1)[0] == fence[1] and len(f.group(1)) >= fence[2] and not f.group(2).strip():
            if i - fence[0] - 1 > MAX_CODE_LINES:
                out.append(f"{fence[0]}줄의 코드 블록이 {i - fence[0] - 1}줄 — {MAX_CODE_LINES}줄 넘는 코드·출력은 경로나 명령으로 바꾼다")
            fence = None
        if DIFF.match(ln):
            diff_lines.append(i)
        for kind, pat in SECRETS:
            if pat.search(ln):
                out.append(f"{i}줄: {kind} 의심 값 — 지우거나 일반 표기(~/, <키>)로 바꾼다")
    if fence is not None:
        out.append(f"{fence[0]}줄의 코드 블록이 닫히지 않았다 — 뒤쪽 전체가 코드로 읽힌다")
    missing = [name for keys, name in SECTIONS if not any(h.startswith(keys) for h in heads)]
    ours = strict or "Session Handoff" in (lines[0] if lines else "") or len(SECTIONS) - len(missing) >= 3
    if missing and ours:
        out.insert(0, "필수 절 없음: " + ", ".join(missing))

    if len(lines) > MAX_LINES:
        out.append(f"{len(lines)}줄 — 상한 {MAX_LINES}줄을 넘는다(넘친 뒤쪽은 다음 세션에 주입되지 않는다)")
    if len(text) > MAX_CHARS:
        out.append(f"{len(text):,}자 — 상한 {MAX_CHARS:,}자를 넘는다(넘치면 주입이 파일로 빠진다)")
    if diff_lines:
        out.append(f"전체 diff로 보이는 줄 {len(diff_lines)}개(첫 줄 {diff_lines[0]}) — 바뀐 파일과 동작 변화만 적는다")
    return out


def check_file(path, strict=True):
    with open(path, encoding="utf-8", errors="replace") as f:
        return check(f.read(), strict)


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "HANDOFF.md"
    if not os.path.isfile(p):
        print(f"{p}: 파일 없음")
        sys.exit(2)
    problems = check_file(p)
    for x in problems:
        print(x)
    if not problems:
        print(f"{p}: 문제 없음")
    sys.exit(1 if problems else 0)
