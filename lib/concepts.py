#!/usr/bin/env python3
"""CONCEPTS.md 파서. 스크립트들이 공유한다.

이 파일 하나만 형식을 안다. bash 쪽은 탭으로 구분된 줄만 읽는다.
형식이 바뀌면 여기만 고친다.

  concepts.py <파일> sections   →  번호 \t 이름
  concepts.py <파일> table      →  번호 \t 상태        (번호 열 없는 표면 빈 출력)
  concepts.py <파일> rows       →  요약표 데이터 행 수
  concepts.py <파일> meta       →  번호 \t 이름 \t 상태 \t 날짜 \t 해시 \t 파일들 \t 이웃 \t 문서들
  concepts.py <파일> refs       →  가리키는쪽 \t 가리켜지는쪽
  concepts.py <파일> evidence   →  근거로 쓰인 경로 (중복 제거)
  concepts.py <파일> states     →  쓰인 상태 어휘 (중복 제거)
  concepts.py <파일> related    →  stdin의 DECISIONS.md diff에서 새로 들어온 '관련' 줄이 가리킨 개념 번호 (중복 제거)
                                   번호 없이 이름으로 가리켰는데 절 이름과 안 맞으면  ? \t 이름
  concepts.py <파일> warnings   →  파서가 못 읽은 부분 경고 한 줄씩(열린 채 끝난 코드 펜스)
  concepts.py <파일> index      →  개념 색인(index) — 개념마다 이름·제목의 '—' 뒤 한 줄·주요 파일 한 줄. 훅이 세션 첫 프롬프트에 넣는 것과 같다
"""
import io
import re
import sys
import unicodedata

SECTION = re.compile(r"^##\s*(\d{1,2})\.\s*(.*)$")
# 숫자 없는 #·## 제목(일치 확인된 것·유지 규칙 등)은 개념 절을 닫는다. 안 닫으면 마지막 개념 본문에 붙는다(2026-11-21 baton CONCEPTS.md)
OTHER_HEADING = re.compile(r"^#{1,2}\s")
# 코드 펜스(``` · ~~~). 펜스 안의 '# 주석'·'## 1.'은 제목이 아니다(PR #11 리뷰가 잡은 회귀)
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
META = re.compile(r"^- \*\*메타\*\*:")
# "개념 12", "개념 1·3" 만 잡는다. 문장 안의 일반 · 구분자는 먹지 않는다.
REF = re.compile(r"개념\s*(\d{1,2}(?:\s*[·,]\s*\d{1,2})*)")
# `경로.확장자:줄번호` 형태의 근거
EVIDENCE = re.compile(r"`([A-Za-z0-9_./가-힣-]+\.[a-z][a-z0-9]*):[0-9][0-9,~-]*`")
# related 전용: '관련' 뒤의 개념 가리킴. 개수("개념 35개")·부정("개념 1은 변경 없음")은 가리킴이 아니다
REL_NUM = re.compile(r"개념\s*(\d{1,2}(?:\s*[·,~]\s*\d{1,2})*)(?!\d|\s*(?:개|종|가지))")
REL_NEG = re.compile(r"^\S{0,3}\s*(?:은|는)?\s*(?:변경\s*없|그대로|무관)")
# 개념 "A"·"B" 처럼 이름으로 가리킨 것. 개념 뒤 따옴표 묶음을 다음 '개념' 전까지 전부 잡는다
REL_NAME_RUN = re.compile(r"개념\s*([\"“'‘].*?)(?=개념|$)")
QUOTED = re.compile(r"[\"“'‘]([^\"”'’]{2,40})[\"”'’]")
TABLE_ROW = re.compile(r"^\|\s*\*{0,2}(\d{1,2})\*{0,2}\s*\|")
TABLE_SEP = re.compile(r"^\|[\s:-]+\|")
META_KEY = re.compile(r"^[가-힣A-Za-z_]+$")
TICKED = re.compile(r"`([^`]+)`")


def field(line, key):
    """메타 줄에서 한 항목을 꺼낸다. 항목 구분자는 ' · '."""
    m = re.search(key + r"=(.*?)(?: · |$)", line)
    return m.group(1).strip() if m else ""


def read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read().splitlines()


def read_text(path):
    with io.open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def fences(lines):
    """줄마다 (그 줄이 펜스 안·펜스 경계인가, 그 줄에서 열린 펜스의 시작 줄 번호 또는 None)."""
    fence = None  # 열린 펜스의 (표지 문자, 길이, 시작 줄 번호)
    for i, line in enumerate(lines, 1):
        f = FENCE.match(line)
        if fence is not None:
            if f and f.group(1)[0] == fence[0] and len(f.group(1)) >= fence[1] and not f.group(2).strip():
                fence = None
            yield True, None
        elif f:
            fence = (f.group(1)[0], len(f.group(1)), i)
            yield True, i
        else:
            yield False, None
    yield None, fence[2] if fence else None  # 마지막: 파일 끝에서 열려 있는 펜스의 시작 줄


def walk(lines):
    """(개념번호, 이름, 그 절의 줄들)을 차례로 내놓는다. 개념 절은 다음 개념 절이나 숫자 없는 #·## 제목에서 끝난다.
    코드 펜스 안의 줄은 제목으로 보지 않는다."""
    num = name = None
    body = []
    for line, (fenced, _) in zip(lines, fences(lines)):
        if fenced:
            if num:
                body.append(line)
            continue
        m = SECTION.match(line)
        if m or OTHER_HEADING.match(line):
            if num:
                yield num, name, body
            num, name, body = (m.group(1), m.group(2).strip(), []) if m else (None, None, [])
        elif num:
            body.append(line)
    if num:
        yield num, name, body


def cmd_sections(lines):
    for num, name, _ in walk(lines):
        print("%s\t%s" % (num, name))


def cmd_table(lines):
    for line in lines:
        m = TABLE_ROW.match(line)
        if m:
            cells = [c.strip() for c in line.split("|")]
            state = cells[3] if len(cells) > 3 else ""
            print("%s\t%s" % (m.group(1), state))


def cmd_rows(lines):
    n = sum(1 for l in lines if l.startswith("| ") and not TABLE_SEP.match(l))
    print(max(n - 1, 0))          # 헤더 한 줄을 뺀다


def cmd_meta(lines):
    for num, name, body in walk(lines):
        for line in body:
            if META.match(line):
                date_hash = field(line, "확인")
                d = re.search(r"(\d{4}-\d{2}-\d{2})", date_hash)
                h = re.search(r"`([0-9a-f]{7,40})`", date_hash)
                # 빈 칸은 "-" 로 채운다. 탭은 IFS 공백이라 연속되면 bash가 합쳐 버린다.
                cells = [
                    num,
                    name.split("—")[0].strip()[:20],
                    field(line, "상태") or "?",
                    d.group(1) if d else "",
                    h.group(1) if h else "",
                    field(line, "파일"),
                    field(line, "이웃"),
                    field(line, "문서"),
                ]
                print("\t".join(c if c else "-" for c in cells))
                break


def cmd_refs(lines):
    out = set()
    for num, _, body in walk(lines):
        for line in body:
            for group in REF.findall(line):
                for target in re.split(r"[·,]", group):
                    target = target.strip()
                    if target and target != num:
                        out.add((num, target))
    for a, b in sorted(out, key=lambda x: (int(x[0]), int(x[1]))):
        print("%s\t%s" % (a, b))


def cmd_evidence(lines):
    seen = sorted({m for line in lines for m in EVIDENCE.findall(line)})
    print("\n".join(seen))


def cmd_states(lines):
    out = {field(l, "상태") for l in lines if META.match(l)}
    for line in lines:
        if TABLE_ROW.match(line):
            cells = [c.strip() for c in line.split("|")]
            if len(cells) > 3:
                out.add(cells[3])
    for s in sorted(x for x in out if x):
        print(s)


def cmd_related(lines):
    """새 결정의 '관련' 줄이 가리킨 개념. 줄 앞 '관련'만이 아니라 표 칸 안의 '- 관련:'도 잡는다.
    절에 없는 번호·못 이은 이름은 '?' 줄로 낸다 — 못 센 것을 0으로 두지 않는다."""
    sections = [(num, name.split("—")[0].strip()) for num, name, _ in walk(lines)]
    nums = {n for n, _ in sections}
    hit, unknown = set(), set()
    for line in sys.stdin.read().splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        tail = line.split("관련", 1)
        if len(tail) < 2:
            continue
        tail = tail[1]
        for m in REL_NUM.finditer(tail):
            if REL_NEG.match(tail[m.end():]):
                continue
            for part in re.split(r"[·,]", m.group(1)):
                ends = [int(x) for x in re.split(r"~", part) if x.strip()]
                for n in (range(ends[0], ends[-1] + 1) if len(ends) == 2 else ends):
                    (hit if str(n) in nums else unknown).add(str(n) if str(n) in nums else "개념 %d(절 없음)" % n)
        for run in REL_NAME_RUN.findall(tail):
            for ref in QUOTED.findall(run):
                ref = ref.strip().rstrip("…").strip()
                found = [n for n, head in sections if ref == head or head in ref or (len(ref) >= 4 and head.startswith(ref))]
                if found:
                    hit.update(found)
                else:
                    unknown.add(ref)
    for n in sorted(hit, key=int):
        print(n)
    for ref in sorted(unknown):
        print("?\t%s" % ref)


def cmd_warnings(lines):
    """파서가 조용히 못 읽은 부분. 못 센 것을 0으로 두지 않으려고 따로 낸다(2026-11-21 재검증: 열린 채 끝난 펜스 뒤 개념이 사라졌다).
    정상으로 닫힌 펜스 안의 '## N.'은 예시라서 경고하지 않는다(재현 저장소 t6: 세션마다 거짓 알림이 났다)."""
    *_, (_, open_at) = fences(lines)
    if open_at:
        lost = sum(1 for l in lines[open_at:] if SECTION.match(l))
        print("코드 펜스가 %d줄에서 열린 채 파일이 끝난다 — 그 뒤 개념 %d개를 못 읽었다" % (open_at, lost))


# 개념 색인 — 북극성 3절의 기준선 ②: 메인 모델이 색인만 보고 스스로 고른다(추가 호출 0). 규칙으로 프롬프트와 개념 제목을
# 맞추는 방식은 오프라인 평가에서 정밀도 0~1%였다 — 사람의 말과 개념 이름이 달라서다. 그래서 맞추지 않고 목록을 건넨다.
INDEX_LIMIT_CHARS = 1500
INDEX_FILES = 3      # 개념마다 보이는 파일 수(나머지는 "(+N)")
INDEX_SUMMARY = 60   # 한 줄 요약의 최대 글자(넘으면 "…")
INDEX_MAX_CONCEPTS = 200  # 이보다 많은 개념은 '… N개 더'로만 센다 — 아주 큰 지도로 훅 시한을 넘겨 인계서까지 잃지 않게
# 인계서·개념 절 머리말과 같은 입장: 지도는 가설이다. "그 파일만"이라고 하면 탐색을 너무 일찍 멈춘다(리뷰 MEDIUM-5)
INDEX_HEAD = ("[baton] 이 저장소 개념 지도({path}) 색인이다. 작업에 맞는 개념의 파일부터 연다. "
              "개념은 탐색 앵커다 — 실제 동작은 코드로 확인한다. 자세한 근거는 {path}의 그 절에.")
RETIRED = ("폐기", "폐기됨", "retired")  # 상태의 첫 낱말이 정확히 이것일 때만(스킬 어휘는 '폐기됨(날짜)')
# 색인에 내지 않는 경로: 홈 절대경로(lib/handoff_check.py SECRETS의 '홈 절대경로'와 같은 범위)와 '~/'. 공개 저장소의 지도에
# 남아 있어도 다른 사람 컴퓨터에서는 열리지 않고 사용자 이름을 드러낸다. 같은 범위인지는 lib/test_concepts_index.py가 묶는다
HOME_PATH = re.compile(r"^(?:~/|(?:/Users/|/home/)(?!Shared(?:/|$))[^/\s]+|/root/|[A-Za-z]:\\[Uu]sers\\)")


def meta_fields(line):
    """메타 줄 → {키: 값}. 값 안의 ' · '도 받는다 — '키='로 시작하지 않는 조각은 앞 키 값의 이어짐이다
    (lib/notes.py parse_meta의 이음 규칙, concept-notes 브랜치). field()는 ' · '에서 값을 끊는다."""
    out, cur = {}, None
    for item in META.sub("", line, 1).strip().split(" · "):
        key, eq, val = item.partition("=")
        if eq and META_KEY.match(key.strip()) and key.strip() not in out:
            cur = key.strip()
            out[cur] = val.strip()
        elif cur is not None:
            out[cur] += " · " + item.strip()
    return out


def meta_files(value):
    """'파일=' 값 → 경로 목록. 백틱 안은 통째로 경로 하나다 — 먼저 꺼낸다(`a.py:12,30`의 쉼표에서 끊지 않게). 백틱 밖에 남은 것만
    쉼표·' · '로 나눈다(뒤에 붙은 '(코드)' 같은 설명은 뗀다). 줄 번호(':12')는 뗀다. '없음(규칙 개념)'·'-'는 파일이 없다는 뜻이다.
    홈 절대경로·'~/'는 뺀다(HOME_PATH)."""
    out, cands = [], []
    for m in re.finditer(r"`([^`]+)`|([^`]+)", value):  # 적힌 순서를 지킨다 — 첫 파일이 그 개념의 입구다
        cands += [m.group(1)] if m.group(1) else [re.sub(r"\s*\(.*\)$", "", x) for x in re.split(r"\s*[,·]\s*", m.group(2))]
    for x in cands:
        x = re.sub(r":[0-9][0-9,~-]*$", "", x.strip())
        if x and x != "-" and not x.startswith("없음") and not x.startswith("(") and not HOME_PATH.match(x) and x not in out:
            out.append(x)
    return out


def table_states(lines):
    """요약표 → {번호: 상태}. 폐기된 개념을 빼는 데만 쓴다. 칸 위치는 머리 줄의 이름('상태')으로 찾는다 — 표마다 칸 순서가 다르다.
    머리 줄을 못 찾은 표는 읽지 않는다. '한 줄' 칸은 읽지 않는다 — 실제 지도(이 저장소)에서 그 칸은 개념이 무엇인지가 아니라
    어긋남의 경과("…를 고쳤다")를 적어 파일 찾기에 쓸모가 없었다(2026-11-22 실측)."""
    cols, out = None, {}
    for line in lines:
        if not line.startswith("|"):
            cols = None
            continue
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line)[1:-1]]
        m = TABLE_ROW.match(line)
        if m and cols:
            i = next((cols.index(n) for n in ("상태", "status") if n in cols), None)
            out.setdefault(m.group(1), cells[i] if i is not None and i < len(cells) else "")
        elif not m and not TABLE_SEP.match(line):
            cols = [c.strip("* ").lower() for c in cells]
    return out


def clip(text, n):
    text = re.sub(r"\s+", " ", text.replace("**", "")).strip()
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def index(text, max_chars=INDEX_LIMIT_CHARS, path="CONCEPTS.md"):
    """개념 색인 문자열(끝 줄바꿈 포함). 넣을 개념이 없거나 머리말조차 안 들어가면 "".
    한 줄: 'N. 이름 — 한 줄 요약 · 파일: a.py, b/c.py (+2)'. 요약은 절 제목의 '—' 뒤뿐이다. 없으면 요약 없이 이름만.
    폐기된 개념은 뺀다(메타 줄 상태 또는 요약표 상태). 파일이 없는 개념(규칙 개념)은 파일 부분이 없다.
    max_chars를 넘으면 이 순서로 줄인다: 뒤쪽 개념부터 요약을 뗀다 → 뒤쪽 개념부터 첫 파일만 남긴다 → 뒤쪽 개념을 빼고
    '… N개 더' 한 줄로 남긴다(조용히 자르지 않는다). 결정론·표준 라이브러리만."""
    lines = unicodedata.normalize("NFC", text).splitlines()  # macOS에서 온 NFD 글자도 같은 이름으로
    table = table_states(lines)
    items = []
    for num, name, body in walk(lines):
        meta = next((meta_fields(l) for l in body if META.match(l)), {})
        state = (meta.get("상태", "") or table.get(num, "")).strip()
        if state and re.split(r"[\s(]", state, maxsplit=1)[0].lower() in RETIRED:
            continue
        title, _, sub = name.partition(" — ")
        if not title.strip():
            continue  # 제목 없는 절('## 3.')은 고를 이름이 없다
        items.append((num, title.strip(), clip(sub.strip(), INDEX_SUMMARY), meta_files(meta.get("파일", ""))))
    if not items:
        return ""
    head = INDEX_HEAD.format(path=path)

    def line(item, level):  # level 0 전부 · 1 요약 없음 · 2 요약 없음·첫 파일만
        num, title, summary, files = item
        s = "%s. %s" % (num, title)
        if summary and level == 0:
            s += " — " + summary
        if files:
            k = INDEX_FILES if level < 2 else 1
            s += " · 파일: " + ", ".join(files[:k]) + (" (+%d)" % (len(files) - k) if len(files) > k else "")
        return s

    def more(n):
        return "… %d개 더 — %s 요약표" % (n, path)

    # 줄은 개념마다 세 단계를 미리 만들어 두고 길이 합만 고쳐 간다 — 개념 수에 비례(O(n)). 줄마다 끝 줄바꿈 1자
    shown = items[:INDEX_MAX_CONCEPTS]
    variants = [[line(it, lv) for lv in (0, 1, 2)] for it in shown]
    levels = [0] * len(shown)
    rest = len(items) - len(shown)
    total = len(head) + 1 + sum(len(v[0]) + 1 for v in variants) + (len(more(rest)) + 1 if rest else 0)
    for lv in (1, 2):
        for i in reversed(range(len(shown))):
            if total <= max_chars:
                break
            total += len(variants[i][lv]) - len(variants[i][levels[i]])
            levels[i] = lv
    keep = len(shown)
    while keep and total > max_chars:  # 뒤쪽 개념을 빼고 '… N개 더'로 센다
        total -= len(variants[keep - 1][levels[keep - 1]]) + 1
        if rest:
            total -= len(more(rest)) + 1
        keep, rest = keep - 1, rest + 1
        total += len(more(rest)) + 1
    if not keep:
        return ""
    out = [head] + [variants[i][levels[i]] for i in range(keep)] + ([more(rest)] if rest else [])
    return "\n".join(out) + "\n"


def cmd_index(lines):
    sys.stdout.write(index("\n".join(lines)))


COMMANDS = {
    "sections": cmd_sections, "table": cmd_table, "rows": cmd_rows,
    "meta": cmd_meta, "refs": cmd_refs, "evidence": cmd_evidence,
    "states": cmd_states, "related": cmd_related, "warnings": cmd_warnings,
    "index": cmd_index,
}

if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[2] not in COMMANDS:
        sys.exit(__doc__)
    COMMANDS[sys.argv[2]](read(sys.argv[1]))
