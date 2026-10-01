#!/usr/bin/env python3
"""CONCEPTS.md 파서. 스크립트들이 공유한다.

이 파일 하나만 형식을 안다. bash 쪽은 탭으로 구분된 줄만 읽는다.
형식이 바뀌면 여기만 고친다.

  concepts.py <파일> sections   →  번호 \t 이름
  concepts.py <파일> table      →  번호 \t 상태        (번호 열 없는 표면 빈 출력)
  concepts.py <파일> rows       →  요약표 데이터 행 수
  concepts.py <파일> meta       →  번호 \t 상태 \t 날짜 \t 해시 \t 파일들 \t 이웃
  concepts.py <파일> refs       →  가리키는쪽 \t 가리켜지는쪽
  concepts.py <파일> evidence   →  근거로 쓰인 경로 (중복 제거)
  concepts.py <파일> states     →  쓰인 상태 어휘 (중복 제거)
  concepts.py <파일> related    →  stdin의 DECISIONS.md diff에서 새로 들어온 '관련' 줄이 가리킨 개념 번호 (중복 제거)
                                   번호 없이 이름으로 가리켰는데 절 이름과 안 맞으면  ? \t 이름
"""
import io
import re
import sys

SECTION = re.compile(r"^##\s*(\d{1,2})\.\s*(.*)$")
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


def field(line, key):
    """메타 줄에서 한 항목을 꺼낸다. 항목 구분자는 ' · '."""
    m = re.search(key + r"=(.*?)(?: · |$)", line)
    return m.group(1).strip() if m else ""


def read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read().splitlines()


def walk(lines):
    """(개념번호, 이름, 그 절의 줄들)을 차례로 내놓는다."""
    num = name = None
    body = []
    for line in lines:
        m = SECTION.match(line)
        if m:
            if num:
                yield num, name, body
            num, name, body = m.group(1), m.group(2).strip(), []
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


COMMANDS = {
    "sections": cmd_sections, "table": cmd_table, "rows": cmd_rows,
    "meta": cmd_meta, "refs": cmd_refs, "evidence": cmd_evidence,
    "states": cmd_states, "related": cmd_related,
}

if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[2] not in COMMANDS:
        sys.exit(__doc__)
    COMMANDS[sys.argv[2]](read(sys.argv[1]))
