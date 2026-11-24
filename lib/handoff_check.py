#!/usr/bin/env python3
"""인계서 검사기 — 북극성 길 단계 3 "Handoff Validator". HANDOFF.md가 다음 세션이 받기 좋은 모양인지 규칙으로 본다.

보는 것: 필수 8절(스킬 템플릿) · 200줄(소유자 결정 09-22) · 8,700자(주입 훅이 머리말·신선도 한 줄·개념 색인을 붙이고도 전문을 넣는 양) ·
긴 코드 블록 · 전체 diff · 비밀값 · 홈 절대경로(10-01 공개 사고에서 새어 나간 종류) ·
개인 자료 목록(/baton-setup에서 사용자가 고른 이름·이메일 등, 설정 파일의 private_terms).
찾은 값 자체는 출력하지 않는다 — 줄 번호와 종류만. 비밀값을 로그·맥락에 다시 옮기지 않으려고.
경고(막지 않음): "확인된 사실과 결정" 절의 목록 줄마다 [V](직접 확인함)·[?](기억·추정) 표시가 있는지 ·
필독 표시가 3개를 넘는지 · 마지막 커밋판(git HEAD)에 있던 줄이 빠졌는지(drop_warnings — 미추적이면 말하지 않는다).
절 제목은 한국어·영어 템플릿 둘 다 읽는다(BATON_LANG과 무관). 메시지 언어는 lib/i18n.py가 정한다.

쓰기: python3 lib/handoff_check.py [HANDOFF.md 경로] — 문제가 있으면 한 줄씩 출력하고 종료 코드 1.
경고만 있으면 "경고:"로 시작하는 줄을 출력하고 종료 코드 0.
"""
import math, os, re, subprocess, sys, time, unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config, i18n, rules

MAX_LINES = 200
MAX_CHARS = 8700  # 주입 훅 본문 예산보다 작아야 한다. 지금 예산 = LIMIT_CHARS 9,600 − 머리말 − 신선도 한 줄(최대 rules.FRESHNESS_MAX)
#   − 꼬리 안내 몫 200 ≥ 8,724자(11-24, 전에는 8,739자), 개념 색인과 같이 들어가면 HANDOFF_KEEP(이 값 + 1). 처음 정할 때는 훅 출력이 9,000자라 예산이
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


# 영어 템플릿의 절 제목 그대로(대소문자 무시, 뒤 괄호 설명·굵게 표시는 허용). baton 형식인지 가를 때는 이것만 센다 —
# "## Goal"·"## Related files"·"## Next steps" 같은 흔한 영어 제목은 남의 HANDOFF.md에도 있어, 앞머리로 세면 남의 파일을
# 저장할 때마다 "필수 절 없음"으로 막았다(리뷰 11-23). 형식이 정해진 뒤 절이 있는지는 has_section(앞머리)로 본다. 한국어는 main 그대로 앞머리
EN_EXACT = ("goal and done criteria", "verified facts and decisions", "files and symbols", "changes made",
            "failed approaches", "verification evidence", "risks and next actions", "promotion candidates")


def template_heading(h, name):
    h = h.strip().rstrip("*").strip().casefold()
    return h == name or h.startswith(name + " (")


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
    if missing and is_ours(lines, heads, strict):
        i = 2 if names_lang(lines, heads, lang) == "ko" else 3
        out.insert(0, t("필수 절 없음: ", "missing required sections: ") + ", ".join(s[i] for s in missing))

    if len(lines) > MAX_LINES:
        out.append(t(f"{len(lines)}줄 — 상한 {MAX_LINES}줄을 넘는다(넘친 뒤쪽은 다음 세션에 주입되지 않는다)",
                     f"{len(lines)} lines — over the {MAX_LINES}-line limit (the part past it will not be injected into "
                     f"the next session)"))
    # 필독 줄은 주입 머리말에 한 번 더 들어간다 — 그 몫까지 상한에 센다(통과한 인계서는 늘 전부 들어간다는 약속, HookOutputBudgetTest)
    extra = max(len(must_read_line(text, "ko")), len(must_read_line(text, "en")))
    size = len(text) + (extra + 1 if extra else 0)
    if size > MAX_CHARS:
        out.append(t(f"{size:,}자 — 상한 {MAX_CHARS:,}자를 넘는다(넘친 뒤쪽은 다음 세션에 주입되지 않는다)"
                     + (f" — 필독 줄 {extra + 1:,}자 포함" if extra else ""),
                     f"{size:,} chars — over the {MAX_CHARS:,}-char limit (the part past it will not be injected into "
                     f"the next session)" + (f" — including the {extra + 1:,}-char must-read line" if extra else "")))
    if diff_lines:
        out.append(t(f"전체 diff로 보이는 줄 {len(diff_lines)}개(첫 줄 {diff_lines[0]}) — 바뀐 파일과 동작 변화만 적는다",
                     f"{len(diff_lines)} lines look like a full diff (first at line {diff_lines[0]}) — write only the "
                     f"changed files and the change in behavior"))
    return out


def is_ours(lines, heads, strict):
    """baton 형식 인계서로 볼지. 다른 형식의 HANDOFF.md에는 템플릿 규칙(필수 절·확인 표시·빠진 줄)을 들이밀지 않는다.
    제목 "Session Handoff", 또는 템플릿 절 3개 이상 — 한국어는 앞머리(main과 같다), 영어는 템플릿 제목 그대로(EN_EXACT)."""
    found = sum(1 for (ko, _, _, _), en in zip(SECTIONS, EN_EXACT) if any(h.startswith(ko) or template_heading(h, en) for h in heads))
    return strict or "Session Handoff" in (lines[0] if lines else "") or found >= 3


def headings(text):
    """코드 블록 밖의 절 제목 글(HEADING 그룹 1) 목록."""
    heads, fence = [], None
    for ln in text.splitlines():
        f = FENCE.match(ln)
        if fence is None:
            if f:
                fence = (f.group(1)[0], len(f.group(1)))
            elif HEADING.match(ln):
                heads.append(HEADING.match(ln).group(1))
        elif f and f.group(1)[0] == fence[0] and len(f.group(1)) >= fence[1] and not f.group(2).strip():
            fence = None
    return heads


def looks_ours(text):
    """훅처럼 너그럽게(strict=False) 볼 때 baton 형식 인계서인가."""
    return is_ours(text.splitlines(), headings(text), False)


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
    n = len(must_read(text))
    ours = is_ours(lines, heads, strict)
    too_many = [t(f"경고: 필독 표시가 {n}개 — 주입 맨 앞에는 앞의 {MUST_MAX}개만 올라간다. 행동 전에 꼭 읽을 {MUST_MAX}개만 남긴다",
                  f"warning: {n} entries are marked must read — only the first {MUST_MAX} are shown at the top of the "
                  f"injection. Keep only the {MUST_MAX} that must be read before acting")] if n > MUST_MAX and ours else []
    if section is None or not ours:
        return too_many

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
    return out + too_many


def section_items(text, specs):
    """specs([(한국어 머리말, 영어 머리말)]) 절마다의 목록 항목 [(spec 번호, 줄 번호, 항목 글)]. 코드 블록·주석 안은 건너뛴다.
    절보다 깊은 제목(### 하위 절)은 그 절 안으로 보되, 다른 spec에 맞으면(승격 후보 아래 ### 기각됨) 그 spec으로 바꾼다.
    들여쓴 이어 쓴 줄은 앞 항목에 붙인다."""
    out, fence, comment, cur, depth, item = [], None, False, None, 0, None
    for i, ln in enumerate(text.splitlines(), 1):
        f = FENCE.match(ln)
        if fence is not None:
            if f and f.group(1)[0] == fence[0] and len(f.group(1)) >= fence[1] and not f.group(2).strip():
                fence = None
            continue
        if f:
            fence, item = (f.group(1)[0], len(f.group(1))), None
            continue
        if comment:
            comment = "-->" not in ln
            continue
        if COMMENT.match(ln):
            continue
        if "<!--" in ln and "-->" not in ln.split("<!--", 1)[1]:
            comment, ln = True, ln.split("<!--", 1)[0]
        d, h = DEPTH.match(ln), HEADING.match(ln)
        if d:
            item, level = None, len(d.group(1))
            hit = next((n for n, (ko, en) in enumerate(specs)
                        if h and (h.group(1).startswith(ko) or h.group(1).casefold().startswith(en))), None)
            if hit is not None:
                cur, depth = hit, level
            elif cur is not None and level <= depth:
                cur = None
            continue
        if cur is None:
            continue
        m = ITEM.match(ln)
        if m:
            item = [cur, i, (m.group(1) or "").strip()]
            out.append(item)
        elif item is not None and ln[:1].isspace() and ln.strip():
            item[2] += " " + ln.strip()
        elif not ln.strip():
            item = None
    return [tuple(x) for x in out]


# ── 필독 표시 ─────────────────────────────────────────────────────────
# "관련 파일·심볼"(Files and symbols) 절의 항목에 (필독)·(must read)를 붙이면 주입 훅이 신선도 줄 바로 뒤에 한 줄로 올린다 —
# 인계서가 잘려도 남고, 읽는 쪽이 건너뛰지 않게. 최대 MUST_MAX개(넘으면 경고). 항목은 MUST_ENTRY자에서 자른다
MUST = re.compile(r"\s*\((?:필독|must[ -]?read)\)", re.I)
MUST_MAX = 3
MUST_ENTRY = 120


def must_read(text):
    """필독 표시가 붙은 항목 글(표시는 뺀 것) 목록, 순서대로."""
    return [MUST.sub("", body).strip() for _, _, body in section_items(text, [SECTIONS[2][:2]]) if MUST.search(body)]


def must_read_line(text, lang=None):
    """주입 머리말에 붙일 필독 한 줄. 표시가 없으면 "". 길이는 앞 MUST_MAX개 × MUST_ENTRY자 + 머리말로 묶인다."""
    items = must_read(text)[:MUST_MAX]
    if not items:
        return ""
    parts = [x if len(x) <= MUST_ENTRY else x[:MUST_ENTRY - 1] + "…" for x in items]
    return tr(lang)("[baton] 행동 전에 먼저 읽는다(인계서의 필독 표시): ",
                    "[baton] Read before acting (marked must read in the handoff): ") + " · ".join(parts)


# ── 저장 때 빠진 줄 검사(경고) ─────────────────────────────────────────
# 마지막 커밋판의 사실·실패·다음 행동·승격 후보·기각 절 목록 줄마다, 새 인계서(와 DECISIONS.md) 어느 줄에든 비슷한 줄이 있는지 본다.
# 다른 절로 옮긴 줄(끝난 다음 행동 → 이미 한 변경)·결정 기록으로 올린 줄은 빠진 것이 아니다 — 그래서 같은 절이 아니라 전체에서 찾는다.
# 비슷함: 옛 줄의 낱말 열쇠(line_keys) 중 DROP_KEEP 이상이 한 줄에 있다.
# 어느 절의 줄을 알리나: 이어 가야 하는 절(실패한 접근법·승격 후보·기각됨)은 빠진 줄 모두, 끝난 일을 지우는 게 보통인 절
# (확인된 사실·다음 행동)은 결정·제약 표지(DECISION_MARK)가 있는 줄만.
# 근거(11-23, ~/baton 인계서 커밋판 12개·연속 쌍 11개, 추적 줄 245개): 모든 절·문턱 0.6이면 127줄이 걸렸고 표본 20줄 중 진짜 빠짐은
# 12줄(사실 절은 9줄 중 3줄만 — 대부분 끝난 일). 위 규칙·문턱 0.5·DECISIONS.md 포함이면 64줄, 새 표본에서 오탐 약 20%.
# 0.5~0.6 사이 7줄은 모두 고쳐 쓴 줄이나 끝난 일(오탐), 0.4~0.5 사이에는 진짜 빠짐이 섞였다 — 그래서 0.5.
# ponytail: 한 사람·한 저장소 이력으로 맞춘 값이다. 다른 저장소의 오탐률은 모른다
DROP_SPECS = [s[:2] for s in (SECTIONS[1], SECTIONS[4], SECTIONS[6], SECTIONS[7])] + [(("기각",), ("rejected",))]
DROP_NAMES = [s[2:] for s in (SECTIONS[1], SECTIONS[4], SECTIONS[6], SECTIONS[7])] + [("기각됨", "Rejected")]
DROP_CARRY = {1, 3, 4}  # DROP_SPECS 번호 — 실패한 접근법·승격 후보·기각됨. 나머지 절은 표지가 있는 줄만
DROP_KEEP = 0.5
DROP_LIST = 8  # 경고에 내용을 적는 줄 수. 나머지는 개수만
DROP_SHOW = 100  # 한 줄을 이 글자에서 자른다
# 비용 상한(리뷰 11-23: 빠진 줄 200개 × DECISIONS.md 2만 줄이 11.6초 — 훅 시한 10초를 넘기면 훅이 죽어 비밀값 막기까지 사라졌다).
# 마지막 커밋판·DECISIONS.md는 앞 DROP_READ_MAX바이트만 읽는다(DECISIONS.md는 새 결정이 위에 오는 저장소 기준 — ponytail: 아래에
# 쌓는 저장소면 뒤쪽을 못 본다). 비교는 낱말 열쇠 색인으로 하고, DROP_BUDGET초 안에 못 끝내면 멈추고 못 끝냈다고 말한다
DROP_READ_MAX = 256 * 1024
DROP_BUDGET = 2.0
DECISION_MARK = re.compile(r"소유자|결정|금지|절대|확정|정본|(?i:\bowner\b|\bdecided\b|\bdecision\b|\bnever\b|\bmust not\b|\bdo not\b|\bdon't\b|\bforbidden\b)")
TOKEN = re.compile(r"[0-9a-z가-힣]+")


def line_keys(line):
    """줄의 낱말 열쇠 — 소문자, 두 글자 이상. 한글 낱말은 앞 두 글자(조사·어미가 붙어도 같은 열쇠), 영어는 끝 s를 뗀다.
    [V]·[?] 표시와 마크다운 기호는 무시한다."""
    out = set()
    for w in TOKEN.findall(unicodedata.normalize("NFC", MARK.sub(" ", line)).casefold()):
        if len(w) < 2:
            continue
        if len(w) > 2 and re.fullmatch(r"[가-힣]+", w):
            w = w[:2]
        elif len(w) > 3 and w.endswith("s") and w.isascii() and w.isalpha():
            w = w[:-1]
        out.add(w)
    return out


def dropped(old, new, decisions="", deadline=None):
    """old(마지막 커밋판)의 항목 중 new·decisions(DECISIONS.md 본문)에 비슷한 줄이 없는 것.
    이어 가야 하는 절(DROP_CARRY)은 모두, 나머지 절은 결정·제약 표지가 있는 줄만. 자리표시("- 없음")는 뺀다.
    돌려주는 값: ([(DROP_SPECS 번호, 항목 글)], 본 항목 수, 전체 항목 수). deadline(time.monotonic)이 지나면 거기서 멈춘다.
    비교: 낱말 열쇠 → 줄 번호 색인. 남는 줄이 되려면 옛 줄 열쇠 n개 중 need개가 한 줄에 있어야 하니, 그 줄은 가장 드문 열쇠
    n − need + 1개 중 하나를 꼭 가진다(비둘기집) — 그 열쇠들이 든 줄만 확인한다."""
    cands = [line_keys(ln) for ln in (new + "\n" + decisions).splitlines() if ln.strip()]
    index = {}
    for i, c in enumerate(cands):
        for k in c:
            index.setdefault(k, []).append(i)
    items, seen = [], set()
    for n, _, body in section_items(old, DROP_SPECS):
        keys = line_keys(body)
        if not keys or NOTHING.match(body) or body in seen or not (n in DROP_CARRY or DECISION_MARK.search(body)):
            continue
        seen.add(body)
        items.append((n, body, keys))
    out = []
    for done, (n, body, keys) in enumerate(items):
        if deadline is not None and time.monotonic() > deadline:
            return out, done, len(items)
        need = math.ceil(DROP_KEEP * len(keys))
        rare = sorted(keys, key=lambda k: len(index.get(k, ())))[:len(keys) - need + 1]
        near = set()
        for k in rare:
            near.update(index.get(k, ()))
        if not any(len(keys & cands[i]) >= need for i in near):
            out.append((n, body))
    return out, len(items), len(items)


class ReadFailed(Exception):
    """마지막 커밋판을 못 읽었다 — git이 시한 안에 답하지 않았거나, 못 띄웠거나, 알 수 없는 까닭으로 실패했다.
    미추적·이력 없음(그때는 committed가 None)과 다르다: 못 본 것을 "빠진 줄 없음"으로 말하지 않으려고 따로 알린다."""


# 비교할 이전 판이 원래 없는 경우의 git 메시지(LC_ALL=C로 띄워 영어로 고정). 이것들은 조용히 넘어간다(None).
# 실제 메시지(git 2.x, 11-24 확인): 저장소 아님 · 커밋 없음 · 미추적 · HEAD에 없는 경로
ABSENT = ("not a git repository", "invalid object name", "not a valid object name", "exists on disk, but not in",
          "does not exist in")


def committed(path, timeout=3.0):
    """git HEAD에 있는 같은 파일 내용(앞 DROP_READ_MAX + 1바이트까지 — 넘쳤는지는 부르는 쪽이 길이로 안다).
    미추적·이력 없음·저장소 아님이면 None(그때는 아무 말도 안 한다). 시한 초과·git을 못 띄움·그 밖의 실패면 ReadFailed.
    cat-file이라 textconv를 타지 않는다. 큰 blob을 통째로 메모리에 올리지 않으려고 필요한 만큼만 읽고 git을 끝낸다.
    시한은 timeout초를 넘기지 않는다: git을 새 프로세스 묶음으로 띄우고 select로 시한까지만 읽은 뒤 묶음째 죽인다.
    직계 자식만 죽이면 exec하지 않는 git 감싸개(#!/bin/sh … git "$@") 밑의 손자가 파이프를 잡고 있어 읽기가 시한을 넘겼다
    (리뷰 11-23 재현: 시한 3초에 30.2초 — 훅 시한 10초를 넘겨 비밀값 막기가 사라졌다). stderr는 임시 파일로 받는다(파이프처럼 막히지 않게)."""
    import select, signal, tempfile
    d = os.path.dirname(os.path.abspath(path))
    end = time.monotonic() + max(timeout, 0.0)
    err = tempfile.TemporaryFile()
    try:
        p = subprocess.Popen(["git", "--no-optional-locks", "-C", d, "cat-file", "blob", "HEAD:./" + os.path.basename(path)],
                             stdout=subprocess.PIPE, stderr=err, start_new_session=True,
                             env=dict(os.environ, LC_ALL="C", LANGUAGE=""))
    except Exception as e:
        err.close()
        raise ReadFailed(type(e).__name__) from None  # git이 없거나 못 띄운다
    chunks, size, eof = [], 0, False
    try:
        fd = p.stdout.fileno()
        while size <= DROP_READ_MAX:
            left = end - time.monotonic()
            if left <= 0 or not select.select([fd], [], [], left)[0]:
                break  # 시한
            b = os.read(fd, 65536)
            if not b:
                eof = True
                break
            chunks.append(b)
            size += len(b)
        if eof:
            p.wait(timeout=max(0.01, end - time.monotonic()))
    except Exception:
        pass
    finally:
        killed = p.returncode is None  # 시한 초과·넉넉히 읽음·wait 시한 — 묶음째 끝낸다
        if killed:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except OSError:
                pass
        p.stdout.close()
        try:
            p.wait(timeout=1)
        except Exception:
            pass
    data = b"".join(chunks)
    try:
        if size > DROP_READ_MAX:
            return data[:DROP_READ_MAX + 1].decode("utf-8", "replace")
        if killed or not eof:
            raise ReadFailed("timeout")
        if p.returncode == 0:
            return data.decode("utf-8", "replace")
        err.seek(0)
        msg = err.read(4096).decode("utf-8", "replace")
        if any(a in msg.lower() for a in ABSENT):
            return None
        raise ReadFailed(msg.strip()[:200] or f"exit {p.returncode}")
    finally:
        err.close()


def drop_warnings(path, text, lang=None, old=None, private_terms=None, strict=True, deadline=None):
    """마지막 커밋판보다 빠진 줄 경고(막지 않음). 결정·제약 표지가 있는 줄은 따로 더 세게 말한다. 내용은 DROP_LIST줄까지.
    strict=False(훅)면 baton 형식으로 보이는 인계서에만 한다(looks_ours).
    같은 폴더의 DECISIONS.md(지금 파일)에 옮긴 줄은 빠진 것이 아니다.
    줄이 유출 검사(비밀값·홈 경로·개인 자료 목록)에 걸리면 내용을 적지 않는다(맥락에 다시 옮기지 않으려고).
    deadline(time.monotonic)까지만 쓴다 — 없으면 지금부터 DROP_BUDGET초. 못 끝내거나 앞 DROP_READ_MAX바이트만 봤으면 그렇게 말한다."""
    if not strict and not looks_ours(text):
        return []
    deadline = time.monotonic() + DROP_BUDGET if deadline is None else deadline
    t = tr(lang)
    if old is None:
        try:
            old = committed(path, max(0.0, min(3.0, deadline - time.monotonic())))
        except ReadFailed:  # 못 읽은 것은 0개가 아니다 — 미추적·이력 없음과 달리 한 줄로 알린다
            return [t("빠진 줄은 확인하지 못했어요(이전 판을 읽지 못함).",
                      "Dropped lines weren't checked (couldn't read the previous version).")]
    if not old:
        return []
    cut_old = len(old.encode("utf-8", "replace")) > DROP_READ_MAX
    old = old.encode("utf-8", "replace")[:DROP_READ_MAX].decode("utf-8", "ignore")
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(path)), "DECISIONS.md"), "rb") as f:
            raw = f.read(DROP_READ_MAX + 1)
    except OSError:
        raw = b""
    cut_dec = len(raw) > DROP_READ_MAX
    decisions = raw[:DROP_READ_MAX].decode("utf-8", "ignore")
    gone, done, total = dropped(old, text, decisions, deadline)
    partial = []
    if done < total or cut_old:
        partial.append(t(f"경고: 빠진 줄 검사를 다 못 했다(마지막 커밋판 항목 {total}개 중 {done}개만 봤다"
                         + (", 마지막 커밋판이 커서 앞 256KB만 읽었다" if cut_old else "") + ") — 아래 목록은 일부다. "
                         f"0개여도 '빠진 줄 없음'이 아니다",
                         f"warning: the dropped-lines check did not finish ({done} of {total} items from the last committed "
                         f"version checked" + ("; the last committed version is large, only its first 256 KB was read" if cut_old else "")
                         + ") — any list below is partial, and none listed does not mean nothing was dropped"))
    if not gone:
        return partial
    en = t(False, True)
    if private_terms is None:
        repo = repo_of(path)
        private_terms = config.terms("private_terms", repo) if repo else []
    dec_note = t(" (DECISIONS.md가 커서 앞 256KB만 비교했다)", " (DECISIONS.md is large; only its first 256 KB was compared)") if cut_dec else ""

    def show(group, room):
        lines = []
        for n, body in group[:room]:
            shown = (t("(내용 생략 — 유출 검사에 걸림)", "(content hidden — matched the leak check)")
                     if leaks(body, private_terms) else body if len(body) <= DROP_SHOW else body[:DROP_SHOW - 1] + "…")
            lines.append(f"\n    - [{DROP_NAMES[n][1 if en else 0]}] {shown}")
        if len(group) > room:
            lines.append(t(f"\n    - … 외 {len(group) - room}개", f"\n    - … and {len(group) - room} more"))
        return "".join(lines)

    marked = [g for g in gone if DECISION_MARK.search(g[1])]
    plain = [g for g in gone if not DECISION_MARK.search(g[1])]
    out, room = [], DROP_LIST
    if marked:
        out.append(t(f"경고: 결정·제약으로 보이는 줄 {len(marked)}개가 마지막 커밋판에서 빠졌다 — DECISIONS.md로 옮겼는지 "
                     f"확인하고, 아니면 되살린다:",
                     f"warning: {len(marked)} line(s) that look like a decision or constraint are gone since the last "
                     f"committed version — check that they moved to DECISIONS.md, otherwise restore them:")
                   + dec_note + show(marked, min(len(marked), room)))
        room -= min(len(marked), room)
    if plain:
        out.append(t(f"경고: 마지막 커밋판에 있던 줄 {len(plain)}개가 새 인계서에 없다 — 아직 참이면 되살리고, 끝난 일이면 "
                     f"'이미 한 변경'으로 옮기고, 아니면 알고 지운다:",
                     f"warning: {len(plain)} line(s) from the last committed version are not in the new handoff — keep each "
                     f"one that is still true, move finished work to 'Changes made', or delete it on purpose:")
                   + dec_note + show(plain, room))
    return partial + out


def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def repo_of(path):
    """설정의 저장소 절을 고를 루트. 설정이 없으면 None — 저장소 루트를 찾으러 git을 부르지 않는다."""
    return rules.repo_root(os.path.dirname(os.path.abspath(path))) if config.load() is not None else None


def check_file(path, strict=True, text=None, lang=None, terms=None):
    """파일 검사. 개인 자료 목록은 그 파일이 든 저장소의 설정(전역 + 저장소 절)에서 읽는다.
    text를 주면 파일을 다시 읽지 않는다(경고 검사와 같은 내용을 보려고). lang이 없으면 그 저장소의 언어.
    terms(개인 자료 목록)와 lang을 다 주면 저장소 루트를 찾지 않는다 — 훅이 한 번 찾은 값을 넘긴다(git 호출을 줄이려고)."""
    if text is None:
        text = read(path)
    if terms is None or lang is None:
        repo = repo_of(path)
        terms = (config.terms("private_terms", repo) if repo else []) if terms is None else terms
        lang = lang or i18n.lang(repo)
    return check(text, strict, terms, lang)


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "HANDOFF.md"
    if not os.path.isfile(p):
        print(tr(None)(f"{p}: 파일 없음", f"{p}: no such file"))
        sys.exit(2)
    repo = repo_of(p)
    lang = i18n.lang(repo)
    terms = config.terms("private_terms", repo) if repo else []
    t = tr(lang)
    text = read(p)
    problems = check_file(p, text=text, lang=lang, terms=terms)
    warned = warnings(text, lang=lang)
    try:
        warned += drop_warnings(p, text, lang, private_terms=terms)
    except Exception:
        pass  # 빠진 줄 검사가 깨져도 나머지 검사는 그대로
    for x in problems + warned:
        print(x)
    if not problems:
        print(t(f"{p}: 문제 없음", f"{p}: no problems") + (t(" (경고만 있음 — 막지 않는다)", " (warnings only — not blocking)") if warned else ""))
    sys.exit(1 if problems else 0)
