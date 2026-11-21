#!/usr/bin/env python3
"""인계서 검사기 — 북극성 길 단계 3 "Handoff Validator". HANDOFF.md가 다음 세션이 받기 좋은 모양인지 규칙으로 본다.

보는 것: 필수 8절(스킬 템플릿) · 200줄(소유자 결정 09-22) · 9,000자(넘치면 Claude Code가 훅 출력을 파일로 뺀다) ·
긴 코드 블록 · 전체 diff · 비밀값 · 홈 절대경로(10-01 공개 사고에서 새어 나간 종류) ·
개인 자료 목록(/baton-setup에서 사용자가 고른 이름·이메일 등, 설정 파일의 private_terms).
찾은 값 자체는 출력하지 않는다 — 줄 번호와 종류만. 비밀값을 로그·맥락에 다시 옮기지 않으려고.
경고(막지 않음): "확인된 사실과 결정" 절의 목록 줄마다 [V](직접 확인함)·[?](기억·추정) 표시가 있는지.

쓰기: python3 lib/handoff_check.py [HANDOFF.md 경로] — 문제가 있으면 한 줄씩 출력하고 종료 코드 1.
경고만 있으면 "경고:"로 시작하는 줄을 출력하고 종료 코드 0.
"""
import os, re, sys, unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config, rules

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
FACTS = ("확인된 사실",)  # SECTIONS의 같은 절. 주장마다 확인 표시를 보는 절
ITEM = re.compile(r"^ ?(?:[-*+]|\d{1,3}[.)])(?:\s+(.*))?$")  # 들여쓰지 않은 목록 줄. 들여쓴 줄은 위 항목에 이어 붙는다
MARK = re.compile(r"\[[V?]\]")
NOTHING = re.compile(r"^(?:\*\*)?없음(?:\*\*)?[.。]?$")  # 템플릿의 "- 없음"은 주장이 아니다
COMMENT = re.compile(r"^\s*<!--.*-->\s*$")  # 템플릿 안내 주석. 주장도, 못 센 줄도 아니다
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


def term_pattern(terms):
    """개인 자료 단어들을 한 정규식으로. 대소문자 무시, 영숫자 사이에 낀 것(kim → skim)은 안 잡는다. 없으면 None."""
    terms = [unicodedata.normalize("NFC", t) for t in terms if t.strip()]
    if not terms:
        return None
    return re.compile(r"(?<![A-Za-z0-9])(?:%s)(?![A-Za-z0-9])" % "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True)), re.I)


def check(text, strict=True, private_terms=()):
    """문제 목록(사람이 읽을 한 줄씩). 없으면 빈 목록.
    strict=False(훅): 필수 절 검사는 baton 형식으로 보이는 인계서(제목 "Session Handoff" 또는 필수 절 3개 이상)에만 한다 —
    다른 형식의 HANDOFF.md를 이 템플릿으로 고쳐 쓰게 밀지 않으려고. 길이·비밀값·경로·개인 자료 검사는 늘 한다."""
    lines = text.splitlines()
    out = []
    terms = term_pattern(private_terms)
    term_hits, term_lines = set(), []

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
        if terms:
            found = {m.group(0).casefold() for m in terms.finditer(unicodedata.normalize("NFC", ln))}
            if found:
                term_hits |= found
                term_lines.append(i)
    if fence is not None:
        out.append(f"{fence[0]}줄의 코드 블록이 닫히지 않았다 — 뒤쪽 전체가 코드로 읽힌다")
    if term_lines:  # 단어 자체는 출력하지 않는다 — 개인 자료를 맥락·로그에 다시 옮기지 않으려고
        out.append(f"개인 자료 목록 단어 {len(term_hits)}개 발견({', '.join(map(str, term_lines))}줄) — 지우거나 일반 표기로 바꾼다")
    missing = [name for keys, name in SECTIONS if not any(h.startswith(keys) for h in heads)]
    if missing and is_ours(lines, missing, strict):
        out.insert(0, "필수 절 없음: " + ", ".join(missing))

    if len(lines) > MAX_LINES:
        out.append(f"{len(lines)}줄 — 상한 {MAX_LINES}줄을 넘는다(넘친 뒤쪽은 다음 세션에 주입되지 않는다)")
    if len(text) > MAX_CHARS:
        out.append(f"{len(text):,}자 — 상한 {MAX_CHARS:,}자를 넘는다(넘치면 주입이 파일로 빠진다)")
    if diff_lines:
        out.append(f"전체 diff로 보이는 줄 {len(diff_lines)}개(첫 줄 {diff_lines[0]}) — 바뀐 파일과 동작 변화만 적는다")
    return out


def is_ours(lines, missing, strict):
    """baton 형식 인계서로 볼지. 다른 형식의 HANDOFF.md에는 템플릿 규칙(필수 절·확인 표시)을 들이밀지 않는다."""
    return strict or "Session Handoff" in (lines[0] if lines else "") or len(SECTIONS) - len(missing) >= 3


def warnings(text, strict=True):
    """막지 않는 경고 목록. "확인된 사실과 결정" 절의 목록 항목마다 [V]·[?]가 있는지 본다.
    절이 없으면 조용하다(필수 절 검사가 이미 알린다). 절은 있는데 목록 줄이 없거나 목록 밖 줄이 섞이면
    "셀 수 없다"고 따로 알린다 — 못 센 것을 0개로 보고하지 않으려고."""
    lines = text.splitlines()
    heads, fence, section = [], None, None  # section: 확인된 사실 절의 (줄 번호, 줄) 목록. None이면 아직 못 만남
    in_facts = False
    for i, ln in enumerate(lines, 1):
        f = FENCE.match(ln)
        if fence is None and f:
            fence = (f.group(1)[0], len(f.group(1)))
            continue
        if fence is not None:
            if f and f.group(1)[0] == fence[0] and len(f.group(1)) >= fence[1] and not f.group(2).strip():
                fence = None
            continue  # 코드 블록 안은 주장으로 세지 않는다
        h = HEADING.match(ln)
        if h:
            heads.append(h.group(1))
            in_facts = section is None and h.group(1).startswith(FACTS)
            if in_facts:
                section = []
        elif in_facts and not COMMENT.match(ln):
            section.append((i, ln))
    missing = [name for keys, name in SECTIONS if not any(x.startswith(keys) for x in heads)]
    if section is None or not is_ours(lines, missing, strict):
        return []

    items, loose, cur = [], [], None  # items: [첫 줄 번호, 항목 글]. loose: 목록에 안 속한 줄 번호
    for i, ln in section:
        m = ITEM.match(ln)
        if m:
            cur = [i, (m.group(1) or "").strip()]
            items.append(cur)
        elif not ln.strip():
            cur = None
        elif cur is not None and ln[:1].isspace():
            cur[1] += " " + ln.strip()
        else:
            loose.append(i)
    claims = [it for it in items if not NOTHING.match(it[1])]
    unmarked = [i for i, body in claims if not MARK.search(body)]
    out = []
    if not items:
        out.append("경고: 확인된 사실과 결정 절에 목록 줄이 없어 [V]·[?] 표시를 셀 수 없다 — 주장마다 '- [V] …' 목록 한 줄로 쓴다")
    elif loose:
        out.append(f"경고: 확인된 사실과 결정 절에 목록이 아닌 줄 {len(loose)}개({', '.join(map(str, loose))}줄) — "
                   f"이 줄들의 [V]·[?] 표시는 세지 못했다. 목록 한 줄로 바꾼다")
    if unmarked:
        out.append(f"경고: 확인된 사실과 결정 절 목록 {len(claims)}개 중 {len(unmarked)}개에 [V]·[?] 표시 없음"
                   f"({', '.join(map(str, unmarked))}줄) — 직접 확인했으면 [V], 기억·추정이면 [?]를 붙인다")
    return out


def check_file(path, strict=True):
    """파일 검사. 개인 자료 목록은 그 파일이 든 저장소의 설정(전역 + 저장소 절)에서 읽는다."""
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    terms = []
    if config.load() is not None:  # 설정이 없으면 저장소 루트를 찾으러 git을 부르지 않는다
        terms = config.terms("private_terms", rules.repo_root(os.path.dirname(os.path.abspath(path))))
    return check(text, strict, terms)


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "HANDOFF.md"
    if not os.path.isfile(p):
        print(f"{p}: 파일 없음")
        sys.exit(2)
    problems = check_file(p)
    with open(p, encoding="utf-8", errors="replace") as f:
        warned = warnings(f.read())
    for x in problems + warned:
        print(x)
    if not problems:
        print(f"{p}: 문제 없음" + (" (경고만 있음 — 막지 않는다)" if warned else ""))
    sys.exit(1 if problems else 0)
