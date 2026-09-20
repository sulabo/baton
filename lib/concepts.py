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
TABLE_ROW = re.compile(r"^\|\s*\*{0,2}(\d{1,2})\*{0,2}\s*\|")
TABLE_SEP = re.compile(r"^\|[\s:-]+\|")


def field(line, key):
    """메타 줄에서 한 항목을 꺼낸다. 항목 구분자는 ' · '."""
    m = re.search(key + r"=(.*?)(?: · |$)", line)
    return m.group(1).strip() if m else ""


def read(path):
    return io.open(path, encoding="utf-8").read().splitlines()


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


COMMANDS = {
    "sections": cmd_sections, "table": cmd_table, "rows": cmd_rows,
    "meta": cmd_meta, "refs": cmd_refs, "evidence": cmd_evidence,
    "states": cmd_states,
}

if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[2] not in COMMANDS:
        sys.exit(__doc__)
    COMMANDS[sys.argv[2]](read(sys.argv[1]))
