#!/usr/bin/env python3
"""인계서 검사기 — 북극성 길 단계 3 "Handoff Validator". HANDOFF.md가 다음 세션이 받기 좋은 모양인지 규칙으로 본다.

보는 것: 필수 8절(스킬 템플릿) · 200줄(소유자 결정 09-22) · 8,700자(주입 훅이 머리말·신선도 한 줄·개념 색인을 붙이고도 전문을 넣는 양) ·
긴 코드 블록 · 전체 diff · 비밀값 · 홈 절대경로(10-01 공개 사고에서 새어 나간 종류) ·
개인 자료 목록(/baton-setup에서 사용자가 고른 이름·이메일 등, 설정 파일의 private_terms).
찾은 값 자체는 출력하지 않는다 — 줄 번호와 종류만. 비밀값을 로그·맥락에 다시 옮기지 않으려고.
경고(막지 않음): "확인된 사실과 결정" 절의 목록 줄마다 [V](직접 확인함)·[?](기억·추정) 표시가 있는지.
절 제목은 한국어·영어 템플릿 둘 다 읽는다(BATON_LANG과 무관). 메시지 언어는 lib/i18n.py가 정한다.

쓰기: python3 lib/handoff_check.py [HANDOFF.md 경로] — 문제가 있으면 한 줄씩 출력하고 종료 코드 1.
경고만 있으면 "경고:"로 시작하는 줄을 출력하고 종료 코드 0.
"""
import os, re, sys, unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config, i18n, rules

MAX_LINES = 200
MAX_CHARS = 8700  # 주입 훅 본문 예산보다 작아야 한다. 지금 예산 = LIMIT_CHARS 9,600 − 머리말 − 신선도 한 줄(최대 rules.FRESHNESS_MAX)
#   − 꼬리 안내 몫 200 ≥ 8,739자, 개념 색인과 같이 들어가면 HANDOFF_KEEP(이 값 + 1). 처음 정할 때는 훅 출력이 9,000자라 예산이
#   8,708자였고, 9,000자 검사기로는 8,709~9,000자 인계서가 검사는 통과하고 주입에서 잘렸다(11-21 로그: 주입 285번 중 163번 잘림).
#   두 값은 lib/test_handoff_check.py InjectBudgetTest가 묶는다 — 한쪽만 바꾸면 테스트가 깨진다.
MAX_CODE_LINES = 20  # ponytail: 정본 26절의 "긴 코드 블록" 수치가 저장소에 없어 정한 기본값. 실사용에서 걸리는 분포를 보고 조정

# (한국어 머리말, 영어 머리말, 보고할 한국어 이름, 영어 이름). 절 제목이 머리말 중 하나로 시작하면(영어는 대소문자 무시) 그 절이 있다고 본다.
# "## E. 실패한 접근법"처럼 번호가 붙어도 받는다. 영어 템플릿은 skills/baton/SKILL.md.
SECTIONS = [
    (("목표",), ("goal",), "목표와 완료 조건", "Goal and done criteria"),
    (("확인된 사실",), ("verified facts",), "확인된 사실과 결정", "Verified facts and decisions"),
    (("관련 파일",), ("files and symbols", "related files"), "관련 파일·심볼", "Files and symbols"),
    (("이미 한 변경",), ("changes made",), "이미 한 변경", "Changes made"),
    (("실패한 접근",), ("failed approach",), "실패한 접근법", "Failed approaches"),
    (("검증 증거",), ("verification evidence",), "검증 증거", "Verification evidence"),
    (("남은 리스크", "다음 행동"), ("risks", "next action", "next step"), "남은 리스크와 다음 행동", "Risks and next actions"),
    (("승격 후보",), ("promotion candidate",), "승격 후보", "Promotion candidates"),
]

HEADING = re.compile(r"^#{2,4}\s+(?:\*\*)?(?:[A-Za-z0-9]{1,3}[.)]\s*)?(.*)")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
FACTS = ("확인된 사실", "verified facts")  # SECTIONS의 같은 절. 주장마다 확인 표시를 보는 절(소문자로 비교)
ITEM = re.compile(r"^\s*(?:[-*+]|\d{1,3}[.)])(?:\s+(.*))?$")  # 목록 줄. 들여쓴 자식도 따로 센다 — 부모에 묶으면 누락을 양쪽으로 놓친다
DEPTH = re.compile(r"^(#{1,6})\s")  # 제목 단계. 사실 절보다 깊은 제목(### 하위 절)은 절 안으로 본다
MARK = re.compile(r"\[[V?]\]")
UNMARKABLE = re.compile(r"`[^`]*`|<!--.*?-->")  # 인라인 코드·주석 안의 [V]는 표시가 아니다
NOTHING = re.compile(r"(?i)^(?:\*\*)?(?:없음|none)(?:\*\*)?[.。]?$")  # 템플릿의 "- 없음"·"- None"은 주장이 아니다
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
# 종류 이름의 영어판. SECRETS의 이름은 다른 모듈·테스트가 키로 쓰므로 한국어 그대로 둔다
KIND_EN = {"비밀 키 블록": "private key block", "API 토큰": "API token", "비밀번호·키 대입": "password or key assignment",
           "홈 절대경로": "absolute home path", "개인 자료 목록 단어": "word from the private-words list"}


def tr(lang):
    """(한국어, 영어) 중 lang 쪽을 고르는 함수. lang이 None이면 i18n.lang()."""
    ko = (lang or i18n.lang()) == "ko"
    return lambda k, e: k if ko else e


def has_section(heads, keys_ko, keys_en):
    return any(h.startswith(keys_ko) or h.casefold().startswith(keys_en) for h in heads)


def names_lang(lines, heads, lang):
    """빠진 절 이름을 어느 언어로 말할지 — 파일이 쓴 언어. 다음 세션이 그 이름 그대로 제목을 달기 때문이다.
    찾은 절이 어느 쪽 머리말로 더 많이 맞았는지, 같으면 첫 줄(written/작성), 그래도 모르면 메시지 언어."""
    ko = sum(1 for k, _, _, _ in SECTIONS if any(h.startswith(k) for h in heads))
    en = sum(1 for _, k, _, _ in SECTIONS if any(h.casefold().startswith(k) for h in heads))
    first = lines[0].casefold() if lines else ""
    if ko != en:
        return "ko" if ko > en else "en"
    return "en" if "written" in first else "ko" if "작성" in first else (lang or i18n.lang())


def term_pattern(terms):
    """개인 자료 단어들을 한 정규식으로. 대소문자 무시, 영숫자 사이에 낀 것(kim → skim)은 안 잡는다. 없으면 None."""
    terms = [unicodedata.normalize("NFC", t) for t in terms if t.strip()]
    if not terms:
        return None
    return re.compile(r"(?<![A-Za-z0-9])(?:%s)(?![A-Za-z0-9])" % "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True)), re.I)


def leaks(text, private_terms=(), lang="ko"):
    """비밀값·홈 경로·개인 자료 목록 단어가 있으면 그 종류만(값은 돌려주지 않는다). 인계서가 아닌 짧은 글(별칭 등)용 — 절·코드 블록·diff 같은 구조 검사는 안 한다.
    lang="en"이면 종류 이름을 영어로(KIND_EN). 기본은 한국어 — 부르는 쪽(notes.py·candidates.py)의 문장이 한국어라서."""
    text = unicodedata.normalize("NFC", text)
    terms = term_pattern(private_terms)
    kinds = [kind for kind, pat in SECRETS if pat.search(text)] + (["개인 자료 목록 단어"] if terms and terms.search(text) else [])
    return kinds if lang == "ko" else [KIND_EN[k] for k in kinds]


def check(text, strict=True, private_terms=(), lang=None):
    """문제 목록(사람이 읽을 한 줄씩). 없으면 빈 목록.
    strict=False(훅): 필수 절 검사는 baton 형식으로 보이는 인계서(제목 "Session Handoff" 또는 필수 절 3개 이상)에만 한다 —
    다른 형식의 HANDOFF.md를 이 템플릿으로 고쳐 쓰게 밀지 않으려고. 길이·비밀값·경로·개인 자료 검사는 늘 한다.
    lang: 메시지 언어(None이면 i18n.lang()). 빠진 절 이름만은 파일이 쓴 언어로(names_lang)."""
    t = tr(lang)
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
                n = i - fence[0] - 1
                out.append(t(f"{fence[0]}줄의 코드 블록이 {n}줄 — {MAX_CODE_LINES}줄 넘는 코드·출력은 경로나 명령으로 바꾼다",
                             f"the code block at line {fence[0]} has {n} lines — replace code or output over {MAX_CODE_LINES} "
                             f"lines with a path or a command"))
            fence = None
        if DIFF.match(ln):
            diff_lines.append(i)
        for kind, pat in SECRETS:
            if pat.search(ln):
                en = KIND_EN[kind]
                out.append(t(f"{i}줄: {kind} 의심 값 — 지우거나 일반 표기(~/, <키>)로 바꾼다",
                             f"line {i}: looks like {'an' if en[0] in 'AEIOUaeiou' else 'a'} {en} — remove it or write it "
                             f"generically (~/, <key>)"))
        if terms:
            found = {m.group(0).casefold() for m in terms.finditer(unicodedata.normalize("NFC", ln))}
            if found:
                term_hits |= found
                term_lines.append(i)
    if fence is not None:
        out.append(t(f"{fence[0]}줄의 코드 블록이 닫히지 않았다 — 뒤쪽 전체가 코드로 읽힌다",
                     f"the code block at line {fence[0]} is not closed — everything after it reads as code"))
    if term_lines:  # 단어 자체는 출력하지 않는다 — 개인 자료를 맥락·로그에 다시 옮기지 않으려고
        at = ', '.join(map(str, term_lines))
        out.append(t(f"개인 자료 목록 단어 {len(term_hits)}개 발견({at}줄) — 지우거나 일반 표기로 바꾼다",
                     f"{len(term_hits)} word(s) from your private-words list found (lines {at}) — remove them or write them "
                     f"generically"))
    missing = [s for s in SECTIONS if not has_section(heads, s[0], s[1])]
    if missing and is_ours(lines, missing, strict):
        i = 2 if names_lang(lines, heads, lang) == "ko" else 3
        out.insert(0, t("필수 절 없음: ", "missing required sections: ") + ", ".join(s[i] for s in missing))

    if len(lines) > MAX_LINES:
        out.append(t(f"{len(lines)}줄 — 상한 {MAX_LINES}줄을 넘는다(넘친 뒤쪽은 다음 세션에 주입되지 않는다)",
                     f"{len(lines)} lines — over the {MAX_LINES}-line limit (the part past it will not be injected into "
                     f"the next session)"))
    if len(text) > MAX_CHARS:
        out.append(t(f"{len(text):,}자 — 상한 {MAX_CHARS:,}자를 넘는다(넘친 뒤쪽은 다음 세션에 주입되지 않는다)",
                     f"{len(text):,} chars — over the {MAX_CHARS:,}-char limit (the part past it will not be injected into "
                     f"the next session)"))
    if diff_lines:
        out.append(t(f"전체 diff로 보이는 줄 {len(diff_lines)}개(첫 줄 {diff_lines[0]}) — 바뀐 파일과 동작 변화만 적는다",
                     f"{len(diff_lines)} lines look like a full diff (first at line {diff_lines[0]}) — write only the "
                     f"changed files and the change in behavior"))
    return out


def is_ours(lines, missing, strict):
    """baton 형식 인계서로 볼지. 다른 형식의 HANDOFF.md에는 템플릿 규칙(필수 절·확인 표시)을 들이밀지 않는다."""
    return strict or "Session Handoff" in (lines[0] if lines else "") or len(SECTIONS) - len(missing) >= 3


def warnings(text, strict=True, lang=None):
    """막지 않는 경고 목록. "확인된 사실과 결정"(영어 템플릿 "Verified facts and decisions") 절의 목록 항목마다 [V]·[?]가 있는지 본다.
    절이 없으면 조용하다(필수 절 검사가 이미 알린다). 절은 있는데 목록 줄이 없거나 목록 밖 줄이 섞이면
    "셀 수 없다"고 따로 알린다 — 못 센 것을 0개로 보고하지 않으려고. lang: 메시지 언어(None이면 i18n.lang())."""
    t = tr(lang)
    lines = text.splitlines()
    heads, fence, comment, section = [], None, False, None  # section: 확인된 사실 절의 (줄 번호, 줄) 목록. None이면 아직 못 만남
    facts_depth = 0  # 사실 절 안이면 그 제목 단계, 밖이면 0
    for i, ln in enumerate(lines, 1):
        f = FENCE.match(ln)
        if fence is not None:
            if f and f.group(1)[0] == fence[0] and len(f.group(1)) >= fence[1] and not f.group(2).strip():
                fence = None
            continue  # 코드 블록 안은 주장으로 세지 않는다
        if comment:
            comment = "-->" not in ln
            continue  # 여러 줄 주석은 통째로 건너뛴다
        if f:
            fence = (f.group(1)[0], len(f.group(1)))
            if facts_depth:
                section.append((i, ln))  # 코드 블록은 표시를 셀 수 없는 덩어리 — 여는 줄을 목록 밖 줄로 센다
            continue
        if COMMENT.match(ln):
            continue
        if "<!--" in ln and "-->" not in ln.split("<!--", 1)[1]:
            comment, ln = True, ln.split("<!--", 1)[0]  # 주석 앞부분만 남긴다
            if not ln.strip():
                continue
        d, h = DEPTH.match(ln), HEADING.match(ln)
        if h:
            heads.append(h.group(1))
        if d:
            depth = len(d.group(1))
            if facts_depth and depth > facts_depth:
                continue  # 하위 절 제목. 그 아래 목록은 계속 사실 절로 센다
            facts_depth = 0
            if h and section is None and h.group(1).casefold().startswith(FACTS):
                facts_depth, section = depth, []
        elif facts_depth:
            section.append((i, ln))
    missing = [s for s in SECTIONS if not has_section(heads, s[0], s[1])]
    if section is None or not is_ours(lines, missing, strict):
        return []

    items, loose, cur = [], [], None  # items: [첫 줄 번호, 항목 글]. loose: 목록에 안 속한 줄 번호
    for i, ln in section:
        m = ITEM.match(ln)
        if m and not FENCE.match(ln):
            cur = [i, (m.group(1) or "").strip()]
            items.append(cur)
        elif not ln.strip():
            cur = None
        elif cur is not None and ln[:1].isspace() and not FENCE.match(ln):
            cur[1] += " " + ln.strip()
        else:
            loose.append(i)
    claims = [it for it in items if not NOTHING.match(it[1])]
    unmarked = [i for i, body in claims if not MARK.search(UNMARKABLE.sub("", body))]
    out = []
    if not items:
        out.append(t("경고: 확인된 사실과 결정 절에 목록 줄이 없어 [V]·[?] 표시를 셀 수 없다 — 주장마다 '- [V] …' 목록 한 줄로 쓴다",
                     "warning: the Verified facts and decisions section has no list items, so its [V]/[?] marks cannot be "
                     "counted — write each claim as one list item, '- [V] …'"))
    elif loose:
        at = ', '.join(map(str, loose))
        out.append(t(f"경고: 확인된 사실과 결정 절에 목록이 아닌 줄 {len(loose)}개({at}줄) — "
                     f"이 줄들의 [V]·[?] 표시는 세지 못했다. 목록 한 줄로 바꾼다",
                     f"warning: {len(loose)} line(s) in the Verified facts and decisions section are not list items "
                     f"(lines {at}) — their [V]/[?] marks were not counted. Make each one a list item"))
    if unmarked:
        at = ', '.join(map(str, unmarked))
        out.append(t(f"경고: 확인된 사실과 결정 절 목록 {len(claims)}개 중 {len(unmarked)}개에 [V]·[?] 표시 없음"
                     f"({at}줄) — 직접 확인했으면 [V], 기억·추정이면 [?]를 붙인다",
                     f"warning: {len(unmarked)} of {len(claims)} items in the Verified facts and decisions section have no "
                     f"[V]/[?] mark (lines {at}) — add [V] if you checked it directly, [?] if it is from memory or a guess"))
    return out


def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def repo_of(path):
    """설정의 저장소 절을 고를 루트. 설정이 없으면 None — 저장소 루트를 찾으러 git을 부르지 않는다."""
    return rules.repo_root(os.path.dirname(os.path.abspath(path))) if config.load() is not None else None


def check_file(path, strict=True, text=None, lang=None):
    """파일 검사. 개인 자료 목록은 그 파일이 든 저장소의 설정(전역 + 저장소 절)에서 읽는다.
    text를 주면 파일을 다시 읽지 않는다(경고 검사와 같은 내용을 보려고). lang이 없으면 그 저장소의 언어."""
    if text is None:
        text = read(path)
    repo = repo_of(path)
    terms = config.terms("private_terms", repo) if repo else []
    return check(text, strict, terms, lang or i18n.lang(repo))


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "HANDOFF.md"
    if not os.path.isfile(p):
        print(tr(None)(f"{p}: 파일 없음", f"{p}: no such file"))
        sys.exit(2)
    lang = i18n.lang(repo_of(p))
    t = tr(lang)
    text = read(p)
    problems = check_file(p, text=text, lang=lang)
    warned = warnings(text, lang=lang)
    for x in problems + warned:
        print(x)
    if not problems:
        print(t(f"{p}: 문제 없음", f"{p}: no problems") + (t(" (경고만 있음 — 막지 않는다)", " (warnings only — not blocking)") if warned else ""))
    sys.exit(1 if problems else 0)
