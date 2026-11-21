#!/usr/bin/env python3
"""개념 지도 ↔ 옵시디언 노트 (docs/CONCEPT_GRAPH.md 3~5절, 소유자 승인 전 설계안의 도구). 결정론·표준 라이브러리만.

  notes.py export <CONCEPTS.md> <노트 폴더>   지도를 노트로 쓴다(이미 있는 파일은 덮어쓰지 않는다)
  notes.py build <노트 폴더>                   노트에서 CONCEPTS.md를 만들어 표준 출력으로
  notes.py check <노트 폴더>                   링크·제목·별칭 겹침·폴더·머리 항목·개인 자료 검사
  notes.py match <노트 폴더> "<프롬프트>"       별칭·제목 적중과 경로 적중을 따로 낸다

노트 폴더는 옵시디언 볼트(설계안의 `concepts/`)다. 경로는 모두 그 폴더 기준.
- 개념 하나 = 노트 하나: `<계산한 폴더>/<파일 이름>.md`. 머리 항목(frontmatter)은 아래 KEYS, 본문은 `# 제목`, 지도의
  메타 줄 뒤 본문 그대로, `## 이웃`. 문자열·목록은 JSON 꼴로 쓴다(YAML로도 맞는 꼴 — 한 줄에 `: `·`#`가 있어도 안 깨진다).
  읽을 때는 따옴표 없는 값과 옵시디언이 고쳐 쓰는 `- 항목` 목록도 받는다.
- `table_name`(선택): 요약표의 개념 칸이 제목과 다를 때만(예: `맥락 조립기` ↔ `맥락 조립기 — 개념 그래프로 고르기`).
  설계안 3절 목록에 없는 항목이다 — 이게 없으면 요약표가 바이트 단위로 같아질 수 없다.
- 개념에 속하지 않는 부분(머리말·요약 절 제목·일치 확인된 것·폐기된 개념·확인하지 못한 것·유지 규칙 등)은 `_색인.md`.
  요약표 자리와 개념 절 자리는 MARK_TABLE·MARK_SECTIONS 주석 한 줄로 남긴다.
- 파일 이름: 제목에서 ILLEGAL(`/ \\ : * ? " < > | # ^ [ ]`·제어 문자 — 운영체제가 금지하거나 옵시디언 링크가 깨지는 글자)을
  `-`로 바꾸고, 앞뒤 공백·마침표를 뗀다. 비면 `개념 N`. `[[링크]]`는 이 파일 이름으로 건다(옵시디언이 링크를 파일 이름으로 푼다).
  원래 제목은 노트의 `# 제목` 줄에 그대로 남는다.
"""
import json, os, posixpath, re, sys, unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import concepts, handoff_check, rules

INDEX = "_색인.md"
MARK_TABLE = "<!-- notes.py: 요약표 자리 — build가 노트에서 만든다 -->"
MARK_SECTIONS = "<!-- notes.py: 개념 절 자리 — build가 노트에서 만든다 -->"
TABLE_HEAD = ["| # | 개념 | 상태 | 심각도 | 한 줄 |", "|---|---|---|---|---|"]
KEYS = ("no", "summary", "aliases", "status", "severity", "checked", "checked_commit", "files", "docs")
META_PREFIX = "- **메타**: "
META_KEYS = ("상태", "확인", "파일", "이웃", "문서", "별칭")  # 생성하는 순서. 별칭은 promote-alias가 맨 뒤에 붙인다
NO_FILES = "없음(규칙 개념)"
ILLEGAL = re.compile(r'[\\/:*?"<>|#^\[\]\x00-\x1f]')
LINK = re.compile(r"\[\[([^\[\]|#]+)(?:[#|][^\[\]]*)?\]\]")
NEIGHBOR_GROUP = re.compile(r"개념\s*(\d{1,2}(?:\s*·\s*\d{1,2})*)(?:\((.*?)\))?")
NEIGHBOR_LINE = re.compile(r"^- (?:(.+?): )?(\[\[.*\]\])\s*$")
CHECKED = re.compile(r"^(.*?)\(`([0-9a-f]{7,40})`\)$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# 요약표 순서(skills/driftmap/SKILL.md 6절 "어긋난 것이 맨 위, 그 안에서 심각도순", 같으면 번호순 — 설계안 3절).
# 어긋남 = 스킬의 "어긋남의 네 종류". 해소됨·일치·폐기됨·확인 못 함은 그 뒤에 번호순으로 섞인다(스킬이 정하지 않아서)
MISMATCH = ("미구현", "낡은 문서", "미결", "중복 정본")
SEVERITY = {"높음": 0, "중간": 1, "낮음": 2}
# 조사(설계안 5절 1단계 목록 그대로). 낱말 끝에서 하나만, 긴 것부터 뗀다. 넉넉히 떼면 부분 문자열 오탐이 돌아온다(설계안 7절 2) —
# 늘릴 때는 실패 사례 테스트를 먼저 박는다. 한계: '고양이'처럼 끝 글자가 조사와 같은 낱말은 '고양' 별칭에 맞는다
PARTICLES = tuple(sorted(("은", "는", "이", "가", "을", "를", "의", "에", "에서", "으로", "로", "와", "과", "도", "만"), key=len, reverse=True))
MIN_ALIAS = 2
WORD = re.compile(r"\w+")
# ponytail: rules.machine_prompt(PR #16)가 이 베이스에 아직 없어 같은 정규식을 둔다. #16이 머지되면 아래 getattr가 그쪽을 쓰고,
# 이 사본은 지운다(정본은 rules.py)
_MACHINE = re.compile(r"\A\s*(?:Another Claude session sent a message:\s*)?<(?:agent-message|cross-session-message|task-notification)\b")
machine_prompt = getattr(rules, "machine_prompt", None) or (lambda prompt: bool(_MACHINE.match(prompt)))


def stem(title, no):
    s = ILLEGAL.sub("-", title).strip(" .")
    return s or "개념 %s" % no


def folder(files):
    """설계안 3절: 모든 파일의 가장 긴 공통 폴더. 첫 칸이 점 폴더이거나, 공통 폴더가 없거나, 파일이 없으면 루트("")."""
    parts = [posixpath.dirname(posixpath.normpath(f.strip().lstrip("/"))).split("/") for f in files if f.strip()]
    if not parts:
        return ""
    common = parts[0]
    for p in parts[1:]:
        n = 0
        while n < min(len(common), len(p)) and common[n] == p[n]:
            n += 1
        common = common[:n]
    common = [c for c in common if c and c != "."]
    if not common or common[0].startswith("."):
        return ""
    return "/".join(common)


# ── CONCEPTS.md → 노트 ────────────────────────────────────────────────

def segments(lines):
    """[(시작, 끝, 개념 번호 또는 None, 제목)] — 제목 줄(코드 펜스 밖 #·##)마다 한 덩어리. 첫 덩어리는 제목 앞 머리말."""
    heads = []
    for i, (line, (fenced, _)) in enumerate(zip(lines, concepts.fences(lines))):
        if fenced:
            continue
        m = concepts.SECTION.match(line)
        if m or concepts.OTHER_HEADING.match(line):
            heads.append((i, m.group(1) if m else None, m.group(2).strip() if m else None))
    out = []
    for k, (i, no, title) in enumerate(heads):
        if k == 0 and i > 0:
            out.append((0, i, None, None))
        end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        out.append((i, end, no, title))
    return out or [(0, len(lines), None, None)]


def split_items(v):
    return [x.strip().strip("`").strip() for x in v.split(",") if x.strip().strip("`").strip()]


def parse_meta(line):
    """메타 줄 → {키: 값}. 모르는 키는 버리지 않고 오류로 낸다(조용히 잃지 않게)."""
    out = {}
    for item in line[len(META_PREFIX):].split(" · "):
        key, eq, val = item.partition("=")
        if not eq or key not in META_KEYS or key in out:
            raise ValueError("메타 줄에서 못 읽은 항목: %r" % item)
        out[key] = val
    return out


def parse_neighbors(v, num):
    """'개념 3(정본), 개념 4·5(전제)' → [(관계, [번호…])]. '없음'이면 []. 못 읽으면 오류."""
    if v.strip() in ("", "없음"):
        return []
    groups = []
    for part in v.split(", "):
        m = NEIGHBOR_GROUP.fullmatch(part.strip())
        if not m:
            raise ValueError("개념 %s의 이웃을 못 읽었다: %r" % (num, part))
        groups.append((m.group(2) or "", [n.strip() for n in m.group(1).split("·")]))
    return groups


def dump(v):
    if isinstance(v, int) or (isinstance(v, str) and DATE.match(v)):
        return str(v)
    return json.dumps(v, ensure_ascii=False)


def to_notes(text):
    """CONCEPTS.md 글 → {노트 폴더 기준 경로: 노트 글}."""
    lines = text.split("\n")
    segs = segments(lines)
    rows = {}
    for line in lines:
        m = concepts.TABLE_ROW.match(line)
        if m and m.group(1) not in rows:
            cells = line.strip()[1:].rstrip("|").split("|", 4)
            rows[m.group(1)] = [c.strip() for c in cells] + [""] * (5 - len(cells))
    stems = {no: stem(title, no) for _, _, no, title in segs if no}
    notes, index, placed = {}, [], False
    for start, end, no, title in segs:
        if not no:
            index.extend(lines[start:end])
            continue
        if not placed:
            index.append(MARK_SECTIONS)
            placed = True
        body = lines[start + 1:end]
        mi = next((i for i, l in enumerate(body) if concepts.META.match(l)), None)
        if mi is None:
            raise ValueError("개념 %s 절에 메타 줄이 없다" % no)
        meta = parse_meta(body[mi])
        rest = body[mi + 1:]
        while rest and not rest[0].strip():
            rest.pop(0)
        while rest and not rest[-1].strip():
            rest.pop()
        checked = CHECKED.match(meta.get("확인", ""))
        row = rows.get(no, ["", title, "", "", ""])
        files = [] if meta.get("파일", "").startswith("없음") else split_items(meta.get("파일", ""))
        fm = {
            "no": int(no), "summary": row[4], "aliases": split_items(meta.get("별칭", "")),
            "status": meta.get("상태", ""), "severity": row[3],
            "checked": checked.group(1) if checked else meta.get("확인", ""),
            "checked_commit": checked.group(2) if checked else "",
            "files": files, "docs": split_items(meta.get("문서", "")),
        }
        if row[1] != title:
            fm["table_name"] = row[1]
        neigh = []
        for rel, nums in parse_neighbors(meta.get("이웃", ""), no):
            links = ", ".join("[[%s]]" % stems.get(n, "개념 %s" % n) for n in nums)
            neigh.append("- %s: %s" % (rel, links) if rel else "- " + links)
        note = ["---"] + ["%s: %s" % (k, dump(v)) for k, v in fm.items()] + ["---", "# " + title, ""]
        note += rest + ["", "## 이웃"] + neigh
        path = posixpath.join(folder(files), stems[no] + ".md")
        if path.casefold() in {p.casefold() for p in notes}:
            raise ValueError("노트 경로가 겹친다: %s — 제목을 먼저 바꾼다" % path)
        notes[path] = "\n".join(note) + "\n"
    # 요약표: 개념 절 밖의 첫 표 덩어리(번호 행이 든 | 줄 묶음)를 자리 표시로 바꾼다
    hit = next((i for i, l in enumerate(index) if concepts.TABLE_ROW.match(l)), None)
    if hit is not None:
        a = b = hit
        while a > 0 and index[a - 1].startswith("|"):
            a -= 1
        while b + 1 < len(index) and index[b + 1].startswith("|"):
            b += 1
        index[a:b + 1] = [MARK_TABLE]
    notes[INDEX] = "\n".join(index)
    return notes


# ── 노트 읽기 ─────────────────────────────────────────────────────────

def load(value):
    v = value.strip()
    if v[:1] in ('"', "["):
        try:
            return json.loads(v)
        except ValueError:
            if v[:1] == "[" and v.endswith("]"):
                return [x.strip().strip("'\"") for x in v[1:-1].split(",") if x.strip()]
    if len(v) >= 2 and v[0] == v[-1] == "'":
        return v[1:-1].replace("''", "'")
    return v


def parse_note(path, text):
    """노트 글 → dict(path, stem, title, fm, body, neighbors=[(관계, [대상 이름…])], errors)."""
    lines = text.split("\n")
    fm, errors, i = {}, [], 0
    if lines and lines[0] == "---":
        end = next((k for k in range(1, len(lines)) if lines[k] == "---"), None)
        if end is None:
            errors.append("머리 항목이 닫히지 않았다")
            end = len(lines)
        key = None
        for line in lines[1:end]:
            item = re.match(r"^\s+-\s*(.*)$", line)
            if item and key is not None:
                if not isinstance(fm.get(key), list):
                    fm[key] = []
                fm[key].append(load(item.group(1)))
                continue
            m = re.match(r"^([A-Za-z_]+):\s?(.*)$", line)
            if m:
                key = m.group(1)
                fm[key] = load(m.group(2)) if m.group(2).strip() else []
        i = end + 1
    title = None
    if i < len(lines) and lines[i].startswith("# "):
        title = lines[i][2:]
        i += 1
        if i < len(lines) and not lines[i].strip():
            i += 1
    rest = lines[i:]
    cut = max((k for k, l in enumerate(rest) if l == "## 이웃"), default=None)
    neighbors = []
    if cut is not None:
        for line in rest[cut + 1:]:
            if not line.strip():
                continue
            m = NEIGHBOR_LINE.match(line)
            if not m:
                errors.append("## 이웃의 줄을 못 읽었다: %r" % line)
                continue
            neighbors.append((m.group(1) or "", [t.strip() for t in LINK.findall(m.group(2))]))
        rest = rest[:cut]
    while rest and not rest[-1].strip():
        rest.pop()
    s = posixpath.splitext(posixpath.basename(path))[0]
    return {"path": path, "stem": s, "title": title if title is not None else s, "fm": fm,
            "body": rest, "neighbors": neighbors, "errors": errors}


def concept_notes(notes):
    return [parse_note(p, t) for p, t in sorted(notes.items()) if posixpath.basename(p) != INDEX]


def as_list(v):
    if isinstance(v, list):
        return [str(x) for x in v]
    return split_items(str(v)) if v not in ("", None) else []


def by_stem(parsed):
    return {n["stem"].casefold(): n for n in parsed}


# ── 노트 → CONCEPTS.md ────────────────────────────────────────────────

def order_key(n):
    fm = n["fm"]
    return (0 if fm.get("status") in MISMATCH else 1, SEVERITY.get(fm.get("severity"), 3), int(fm["no"]))


def to_concepts_md(notes):
    """노트 → CONCEPTS.md 글. 한쪽에만 적힌 [[링크]]는 반대쪽 메타 줄에도 같은 관계 이름으로 낸다(설계안 3절)."""
    index = next((t for p, t in notes.items() if posixpath.basename(p) == INDEX and posixpath.dirname(p) == ""), None)
    if index is None:
        raise ValueError("%s가 없다" % INDEX)
    parsed = concept_notes(notes)
    bad = ["%s: %s" % (n["path"], e) for n in parsed for e in n["errors"]]
    bad += ["%s: 머리 항목 no가 없다" % n["path"] for n in parsed if "no" not in n["fm"]]
    if bad:
        raise ValueError("노트를 못 읽었다 — " + "; ".join(bad))
    for n in parsed:
        n["fm"]["no"] = int(n["fm"]["no"])
    names = by_stem(parsed)
    edges = {}  # 번호 → [(관계, [번호…])] 적힌 순서 그대로
    for n in parsed:
        groups = []
        for rel, targets in n["neighbors"]:
            nums = []
            for t in targets:
                hit = names.get(t.casefold())
                if hit is None:
                    raise ValueError("%s: [[%s]] 노트가 없다" % (n["path"], t))
                nums.append(hit["fm"]["no"])
            groups.append((rel, nums))
        edges[n["fm"]["no"]] = groups
    have = {(a, b) for a, gs in edges.items() for _, ns in gs for b in ns}
    back = {}
    for a, gs in edges.items():
        for rel, ns in gs:
            for b in ns:
                if b != a and (b, a) not in have:
                    back.setdefault(b, {}).setdefault(a, rel)
    sections = []
    for n in sorted(parsed, key=lambda x: x["fm"]["no"]):
        fm, no = n["fm"], n["fm"]["no"]
        groups = list(edges[no]) + [(rel, [a]) for a, rel in sorted(back.get(no, {}).items())]
        neigh = ", ".join("개념 %s%s" % ("·".join(str(x) for x in ns), "(%s)" % rel if rel else "") for rel, ns in groups) or "없음"
        files = as_list(fm.get("files", []))
        items = ["상태=%s" % fm.get("status", ""),
                 "확인=%s%s" % (fm.get("checked", ""), "(`%s`)" % fm["checked_commit"] if fm.get("checked_commit") else ""),
                 "파일=%s" % (",".join("`%s`" % f for f in files) if files else NO_FILES),
                 "이웃=%s" % neigh]
        docs, aliases = as_list(fm.get("docs", [])), as_list(fm.get("aliases", []))
        if docs:
            items.append("문서=%s" % ",".join("`%s`" % d for d in docs))
        if aliases:
            items.append("별칭=%s" % ", ".join(aliases))
        sections += ["## %s. %s" % (no, n["title"]), "", META_PREFIX + " · ".join(items), ""] + n["body"] + [""]
    table = TABLE_HEAD + ["| %s | %s | %s | %s | %s |" % (
        n["fm"]["no"], n["fm"].get("table_name") or n["title"], n["fm"].get("status", ""),
        n["fm"].get("severity", ""), n["fm"].get("summary", "")) for n in sorted(parsed, key=order_key)]
    lines = index.split("\n")
    for mark in (MARK_TABLE, MARK_SECTIONS):
        if lines.count(mark) != 1:
            raise ValueError("%s에 자리 표시가 하나여야 한다: %s" % (INDEX, mark))
    out = []
    for line in lines:
        out += table if line == MARK_TABLE else sections if line == MARK_SECTIONS else [line]
    return "\n".join(out)


# ── 검사 ──────────────────────────────────────────────────────────────

def check(notes, private_terms=()):
    """문제 한 줄씩. 없으면 []."""
    parsed = concept_notes(notes)
    names = by_stem(parsed)
    out = []
    for n in parsed:
        out += ["%s: %s" % (n["path"], e) for e in n["errors"]]
        out += ["%s: 머리 항목 '%s'가 없다" % (n["path"], k) for k in KEYS if k not in n["fm"]]
        want = folder(as_list(n["fm"].get("files", [])))
        have = posixpath.dirname(n["path"])
        if have != want:
            out.append("%s: 노트 폴더가 '%s'인데 files:로 계산한 폴더는 '%s'다 — 옮긴다" % (n["path"], have or "(루트)", want or "(루트)"))
    nos = {}
    for n in parsed:
        nos.setdefault(str(n["fm"].get("no")), []).append(n["path"])
    out += ["no %s가 노트 %d개에 있다: %s" % (k, len(v), ", ".join(v)) for k, v in sorted(nos.items()) if len(v) > 1 and k != "None"]
    seen = {}
    for n in parsed:
        for name in {x.casefold() for x in [n["stem"], n["title"]] + as_list(n["fm"].get("aliases", []))}:
            seen.setdefault(unicodedata.normalize("NFC", name), []).append(n["path"])
    out += ["제목·별칭 '%s'가 노트끼리 겹친다: %s" % (k, ", ".join(v)) for k, v in sorted(seen.items()) if len(v) > 1]
    for path, text in sorted(notes.items()):
        for t in LINK.findall(re.sub(r"`[^`\n]*`", "", text)):
            if t.strip().casefold() not in names:
                out.append("%s: [[%s]] 노트가 없다" % (path, t.strip()))
        kinds = handoff_check.leaks(text, private_terms)
        if kinds:
            out.append("%s: %s로 보이는 것이 있다(값은 출력하지 않는다)" % (path, "·".join(kinds)))
    return out


# ── 찾기 (설계안 5절 1·2단계) ─────────────────────────────────────────

def strip_particle(tok):
    for p in PARTICLES:
        if tok.endswith(p) and len(tok) > len(p):
            return tok[:-len(p)]
    return tok


def words(text):
    return [w.casefold() for w in WORD.findall(unicodedata.normalize("NFC", text))]


def match(notes, prompt):
    """프롬프트 낱말이 노트의 제목·별칭과 낱말 단위로 같은 노트의 번호. 부분 문자열로 맞추지 않는다.
    프롬프트 낱말은 끝의 조사 하나를 떼고도 비교한다. 별칭은 2글자 이상만. 사람이 친 프롬프트가 아니면 []."""
    if machine_prompt(prompt):
        return []
    toks = words(prompt)
    forms = [(t, strip_particle(t)) for t in toks]
    hits = set()
    for n in concept_notes(notes):
        for phrase in [n["title"]] + as_list(n["fm"].get("aliases", [])):
            if len(phrase.strip()) < MIN_ALIAS:
                continue
            want = words(phrase)
            if not want:
                continue
            for i in range(len(forms) - len(want) + 1):
                if all(w in forms[i + k] for k, w in enumerate(want)):
                    hits.add(int(n["fm"]["no"]))
                    break
    return sorted(hits)


def match_paths(notes, prompt):
    """프롬프트에 든 파일 경로를 files:와 맞춘 노트 번호. 별칭 적중과 섞지 않는다(설계안 6절 — 경로 적중은 따로 보고).
    경로 앞에는 영숫자·`_.-`가 없어야 하고(절대 경로의 `/`는 된다), 뒤에는 경로 글자가 이어지지 않아야 한다(한글 조사·`:줄`은 된다).
    ponytail: 앞에 붙은 다른 폴더(`src/lib/x.py`)도 `lib/x.py`로 맞는다 — 저장소 루트를 알면 절대 경로만 루트로 잘라 좁힌다."""
    if machine_prompt(prompt):
        return []
    hits = set()
    for n in concept_notes(notes):
        for f in as_list(n["fm"].get("files", [])):
            if re.search(r"(?<![A-Za-z0-9_.\-])" + re.escape(f) + r"(?![A-Za-z0-9_/\-]|\.[A-Za-z0-9])", prompt):
                hits.add(int(n["fm"]["no"]))
                break
    return sorted(hits)


# ── CLI ───────────────────────────────────────────────────────────────

def read_dir(root):
    out = {}
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if not x.startswith("."))  # .obsidian(사람의 화면 설정)은 노트가 아니다
        for f in files:
            if f.endswith(".md"):
                p = os.path.join(d, f)
                with open(p, encoding="utf-8", newline="") as fh:
                    out[os.path.relpath(p, root).replace(os.sep, "/")] = fh.read()
    return out


def main(argv):
    if len(argv) == 3 and argv[0] == "export":
        with open(argv[1], encoding="utf-8", newline="") as fh:
            notes = to_notes(fh.read())
        clash = [p for p in notes if os.path.exists(os.path.join(argv[2], p))]
        if clash:
            sys.exit("이미 있어서 쓰지 않았다(덮어쓰지 않는다): %s" % ", ".join(clash))
        for p, t in notes.items():
            dest = os.path.join(argv[2], p)
            os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
            with open(dest, "w", encoding="utf-8", newline="") as fh:
                fh.write(t)
        roots = sum(1 for p in notes if p != INDEX and "/" not in p)
        print("노트 %d개(루트 %d · 하위 폴더 %d) + %s → %s" % (len(notes) - 1, roots, len(notes) - 1 - roots, INDEX, argv[2]))
        return 0
    if len(argv) == 2 and argv[0] == "build":
        sys.stdout.write(to_concepts_md(read_dir(argv[1])))
        return 0
    if len(argv) == 2 and argv[0] == "check":
        import config
        problems = check(read_dir(argv[1]), config.terms("private_terms", rules.repo_root(os.path.abspath(argv[1]))))
        print("\n".join(problems) if problems else "문제 없음")
        return 1 if problems else 0
    if len(argv) == 3 and argv[0] == "match":
        notes = read_dir(argv[1])
        titles = {int(n["fm"]["no"]): n["title"] for n in concept_notes(notes) if "no" in n["fm"]}
        for kind, nos in (("별칭", match(notes, argv[2])), ("경로", match_paths(notes, argv[2]))):
            print("%s: %s" % (kind, ", ".join("%d %s" % (no, titles[no]) for no in nos) or "0건"))
        return 0
    sys.exit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
