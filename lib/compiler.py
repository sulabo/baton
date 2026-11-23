#!/usr/bin/env python3
"""Context Compiler — 북극성 길 단계 2(스펙 17~19절). 프롬프트 하나에 넣을 최소 맥락을 예산 안에서 고른다.

결정론·비용 0. 재료는 저장소에 이미 있는 것만 쓴다.
 - 개념 그래프: CONCEPTS.md. 노드는 개념, 간선은 메타 줄 `이웃`(사람이 적은 전제·정본), 붙은 파일은 `파일`, 별칭은 `별칭`.
   공유 파일로 개념을 잇지 않는다(09-14 간선 폭발). 파일로 개념을 고를 때도 세 개 이상 개념에 걸린 파일은 쓰지 않는다.
 - 씨앗: 인계서의 작업 파일(백틱 경로 중 실제 있는 파일) + 이 세션이 최근 읽고 고친 파일(세션 기록 끝부분).
 - 같은 폴더 최근순: 씨앗과 같은 폴더의 파일을 마지막 커밋 시각순. 10-04 평가에서 커밋 co-change 그래프(0.00)보다 나았다(0.19).
 - 결정: DECISIONS.md 항목 중 고른 개념을 "개념 N"으로 가리키거나 그 개념의 파일을 적은 것의 제목.
후보에서 이 세션이 이미 만진 파일은 뺀다 — 이미 맥락에 있는 파일을 다시 가리키는 것은 아무것도 아끼지 않는다.

select()는 고르기만 하고, render()가 글로 만든다. 기준선(같은 폴더만·인계서만·그래프 뺀 조립기)도 같은 자리에서 함께 계산한다 —
나중에 같은 턴끼리 비교하려고(설계안 7절).
아직 훅에 안 붙었다 — 그림자 모드(select 결과를 관찰 로그에만 남김)·BATON_COMPILER 스위치는 인계서 주입 훅 정리 뒤에 붙인다.
지금은 아래 explain으로만 돈다.

  compiler.py explain "<프롬프트>" [저장소 루트]   고른 것과 그 이유, 넣을 글을 보여 준다(바꾸는 것 없음)
"""
import hashlib, json, os, re, subprocess, sys, time, unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import concepts, i18n, rules

VERSION = "compiler-v1"
# 예산(스펙 19절 예시값). 파일 10개는 평가의 recall@k와 같은 k다.
MAX_CONCEPTS, MAX_FILES, MAX_DECISIONS = 8, 10, 10
MAX_LINES, MAX_CHARS = 300, 4000
HUB_NAMES = {"HANDOFF.md", "DECISIONS.md", "CONCEPTS.md", "README.md", "AGENTS.md", "CLAUDE.md", ".gitignore",
             "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Cargo.lock", "uv.lock", "Gemfile.lock"}
SHARED_MAX = 2             # 이보다 많은 개념에 걸린 파일은 파일→개념 매칭에 안 쓴다
TOUCH_TOOLS = {"Read", "Write", "Edit", "MultiEdit", "NotebookEdit"}
TAIL_BYTES = 512 * 1024    # ponytail: 세션 기록은 끝 512KB만 본다. 긴 세션의 앞부분에서 만진 파일은 "안 만짐"으로 잡힐 수 있다
GIT_LOG_COMMITS = 400      # 최근순 계산에 쓰는 커밋 수
GIT_TIMEOUT = 2            # 훅 시한(10초) 안에서 git 두 번 + 나머지가 끝나게
FAIL_RETRY = 600           # git log가 실패하면 이 초 동안은 다시 부르지 않는다(매 프롬프트 시한 소모 방지)
PATH_TOKEN = re.compile(r"`([^`\s]+)`")
DEC_HEAD = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\s*(.*)$")
DEC_ROW = re.compile(r"^\|\s*\**([A-Z]+[0-9]+)\**\s*\|\s*([^|]*)\|")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
NUM = re.compile(concepts.CONCEPT_WORD + r"\s*(\d{1,2}(?:\s*[·,]\s*\d{1,2})*)")
# 사람(과 모델)이 보는 낱말. 이유 문자열은 로그(summary)에 안 남고 render·explain에만 나온다
WORDS = {
    "ko": {"title": "제목 '%s'", "alias": "별칭 '%s'", "file": "작업 파일 %s", "neighbor_of": "개념 %s의 이웃",
           "concept": "개념 %s", "tag_file": "(작업 파일)", "tag_neighbor": "(이웃)", "handoff": "인계서 작업 파일",
           "folder": "작업 파일과 같은 폴더, 최근 커밋",
           "head": "[baton] 맥락 조립 — 프롬프트와 작업 파일로 고른 탐색 앵커다. 전부 읽지 말고 필요한 것만 연다. 실제 동작은 코드로 확인한다.",
           "concepts": "관련 개념 (%s)", "files": "읽어 볼 만한 파일 (이 세션에서 아직 안 연 것)", "decisions": "관련 결정 (DECISIONS.md)",
           "warn": "[baton] 지도 경고: %s", "none": "[baton] 고른 것 없음 — 넣지 않는다"},
    "en": {"title": "title '%s'", "alias": "alias '%s'", "file": "working file %s", "neighbor_of": "neighbor of concept %s",
           "concept": "concept %s", "tag_file": " (working file)", "tag_neighbor": " (neighbor)", "handoff": "working file in the handoff",
           "folder": "same folder as a working file, recent commit",
           "head": "[baton] Context assembly — navigation anchors picked from the prompt and the working files. Don't read them all; "
                   "open only what you need. Check actual behavior in the code.",
           "concepts": "Related concepts (%s)", "files": "Files worth reading (not opened in this session yet)",
           "decisions": "Related decisions (DECISIONS.md)", "warn": "[baton] map warning: %s", "none": "[baton] Nothing selected — nothing is added"},
}
USAGE_EN = """Context compiler: picks the concepts, files and decisions worth reading for one prompt. Changes nothing.

  compiler.py explain "<prompt>" [repo root]   shows what it picked, why, and the text it would add
"""


def nfc(s):
    """macOS git은 한글 경로를 NFD로, 세션 기록은 NFC로 준다 — 맞추지 않으면 전부 다른 파일로 잡힌다."""
    return unicodedata.normalize("NFC", s)


def is_hub(path):
    return os.path.basename(path) in HUB_NAMES


def rel_in(repo, path):
    """저장소 안 파일이면 저장소 기준 상대 경로(NFC), 아니면 None."""
    if not isinstance(path, str) or not path:
        return None
    root = nfc(os.path.realpath(repo))
    ap = nfc(os.path.realpath(path if os.path.isabs(path) else os.path.join(repo, path)))
    if not ap.startswith(root.rstrip("/") + "/"):
        return None
    return ap[len(root.rstrip("/")) + 1:]


# ── 개념 그래프 ────────────────────────────────────────────────────────

def split_list(v):
    """메타 값 '`a`,`b`' 또는 'a, b' → [a, b]. '없음'·괄호 설명은 버린다."""
    v = re.sub(r"\(.*?\)", "", v or "")
    out = []
    for x in re.split(r"[,，]", v):
        x = x.strip().strip("`").strip()
        if x and x != "없음" and x.lower() != "none" and x != "-":
            out.append(x)
    return out


def graph(repo, lang=None):
    """{"rel": 지도 경로, "nodes": {번호: {name, title, files, neighbors, aliases}}, "warnings": 파서가 못 읽은 부분}
    또는 None(지도 없음·못 읽음). 절 나누기는 concepts.walk(코드 펜스 안 제목은 무시) 그대로.
    메타 줄은 한국어 키·영어 키(files=·neighbors=·aliases=) 둘 다 읽는다. lang은 warnings 문장의 언어."""
    path, rel = rules.concept_path(repo)
    if not path:
        return None
    try:
        lines = concepts.read(path)
    except (OSError, UnicodeDecodeError):
        return None
    nodes = {}
    for num, name, body in concepts.walk(lines):
        meta = next((l for l in body if concepts.META.match(l)), "")
        # 저장소 밖(`../x`·`/etc/x`)은 버리고 `./a`는 `a`로 — 인계서 경로와 같은 rel_in을 거친다
        files = [r for r in (rel_in(repo, f) for f in split_list(concepts.field(meta, "파일"))) if r]
        neighbors = []
        for group in NUM.findall(concepts.field(meta, "이웃")):
            neighbors += [n.strip() for n in re.split(r"[·,]", group) if n.strip() and n.strip() != num]
        nodes[num] = {"name": name, "title": name.split("—")[0].strip(), "files": files,
                      "neighbors": neighbors, "aliases": [a for a in split_list(concepts.field(meta, "별칭")) if len(a) >= 2]}
    return {"rel": rel, "nodes": nodes, "warnings": concepts.warnings(lines, lang)}


def concept_matches(g, prompt, seed_files, lang=None):
    """[(번호, 이유, 종류)] — 종류는 prompt(제목·별칭이 프롬프트에 있음) · file(작업 파일이 그 개념 것) · neighbor(한 칸 이웃).
    prompt 먼저(이유가 많은 순), 그다음 file, 그다음 이웃. 작업 파일 개념은 어느 프롬프트에나 같아 판정 상태에는 안 센다."""
    if not g:
        return []
    w = WORDS[concepts.lang_of(lang)]
    p = prompt.lower()
    owners = {}
    for num, n in g["nodes"].items():
        for f in n["files"]:
            owners.setdefault(f, []).append(num)
    direct, kind = {}, {}
    for num, n in g["nodes"].items():
        why = [w["title"] % t for t in rules.title_words(n["name"]) if t in p][:1]
        why += [w["alias"] % a for a in n["aliases"] if a.lower() in p][:1]
        by_file = [w["file"] % f for f in seed_files
                   if f in n["files"] and not is_hub(f) and len(owners.get(f, [])) <= SHARED_MAX][:1]
        if why or by_file:
            direct[num] = why + by_file
            kind[num] = "prompt" if why else "file"
    order = sorted(direct, key=lambda k: (kind[k] != "prompt", -len(direct[k]), int(k)))
    out = [(k, " · ".join(direct[k]), kind[k]) for k in order]
    seen = set(direct)
    for k in order:
        for nb in g["nodes"][k]["neighbors"]:
            if nb in g["nodes"] and nb not in seen:
                seen.add(nb)
                out.append((nb, w["neighbor_of"] % k, "neighbor"))
    return out[:MAX_CONCEPTS]


# ── 씨앗 ──────────────────────────────────────────────────────────────

def handoff_files(repo):
    """인계서에 백틱으로 적힌 경로 중 저장소 안에 실제 있는 파일(적힌 순서). 허브 파일은 뺀다."""
    path = os.path.join(repo, "HANDOFF.md")
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return []
    out = []
    for tok in PATH_TOKEN.findall(text):
        tok = tok.split(":")[0].rstrip(".,)")  # `a.py:12`·`a.py`의 줄번호 떼기
        if "/" not in tok and "." not in tok:
            continue
        r = rel_in(repo, tok)
        if r and r not in out and not is_hub(r) and os.path.isfile(os.path.join(repo, r)):
            out.append(r)
    return out


def session_files(repo, transcript_path):
    """(이 세션이 만진 저장소 파일 최근 것부터, 끝만 읽은 기록이 있었나). 메인 기록 끝부분과 서브에이전트 기록 끝부분."""
    if not isinstance(transcript_path, str) or not transcript_path.endswith(".jsonl"):
        return [], False
    files = [transcript_path]
    sub = os.path.join(transcript_path[:-len(".jsonl")], "subagents")
    try:
        files += [os.path.join(sub, f) for f in sorted(os.listdir(sub)) if f.endswith(".jsonl")]
    except OSError:
        pass
    hits, cut = [], False
    for f in files:
        try:
            with open(f, "rb") as fh:
                fh.seek(0, 2)
                size = fh.tell()
                cut = cut or size > TAIL_BYTES
                fh.seek(max(0, size - TAIL_BYTES))
                raw = fh.read().decode("utf-8", errors="ignore")
        except OSError:
            continue
        for ln in raw.splitlines():
            if '"tool_use"' not in ln:
                continue
            try:
                d = json.loads(ln)
            except ValueError:
                continue
            m = d.get("message") if isinstance(d, dict) else None
            for b in (m.get("content") if isinstance(m, dict) and isinstance(m.get("content"), list) else []):
                if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") in TOUCH_TOOLS:
                    inp = b.get("input") if isinstance(b.get("input"), dict) else {}
                    r = rel_in(repo, inp.get("file_path") or inp.get("notebook_path"))
                    if r:
                        hits.append((d.get("timestamp") or "", r))
    out = []
    for _, r in sorted(hits, key=lambda t: t[0], reverse=True):
        if r not in out:
            out.append(r)
    return out, cut


# ── 같은 폴더 최근순 ──────────────────────────────────────────────────

def cache_dir():
    """캐시 폴더. 상대 경로 XDG_CACHE_HOME은 무시하고(XDG 규약) $HOME/.cache로. 둘 다 없으면 None — 저장소 안에 만들지 않는다."""
    # ponytail: lib/runlog.py cache_dir는 아직 상대 XDG_CACHE_HOME을 그대로 쓴다. 한 곳으로 합치는 것은 훅 상태 파일까지 걸려 따로 한다
    xdg = os.environ.get("XDG_CACHE_HOME") or ""
    home = os.environ.get("HOME") or ""
    base = xdg if os.path.isabs(xdg) else os.path.join(home, ".cache") if os.path.isabs(home) else ""
    return os.path.join(base, "baton", "compile") if base else None


def git(repo, *args):
    try:
        r = subprocess.run(["git", "-C", repo, "-c", "core.quotepath=false", *args],
                           capture_output=True, text=True, errors="ignore", timeout=GIT_TIMEOUT)
        return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def last_commit_times(repo):
    """(HEAD, {파일: 마지막 커밋 시각} 또는 git을 못 읽었으면 None) — 최근 커밋 GIT_LOG_COMMITS개에서, 경로는 repo 기준(--relative: 하위 폴더에서 열어도 씨앗과 같은 기준).
    HEAD가 같으면 캐시를 쓴다. git log가 실패하면 빈 결과를 HEAD에 묶어 두지 않고, FAIL_RETRY초 뒤에 다시 부른다."""
    head = (git(repo, "rev-parse", "HEAD") or "").strip()
    if not head:
        return "", None
    d = cache_dir()
    cache = os.path.join(d, hashlib.sha1(nfc(os.path.realpath(repo)).encode()).hexdigest()[:16] + ".json") if d else None
    try:
        with open(cache, encoding="utf-8") as f:
            c = json.load(f)
        if c.get("head") == head and isinstance(c.get("times"), dict):
            return head, c["times"]
        if c.get("head") == head and time.time() - float(c.get("failed_at", 0)) < FAIL_RETRY:
            return head, None
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    out = git(repo, "log", f"-n{GIT_LOG_COMMITS}", "--no-renames", "--relative", "--format=%x00%ct", "--name-only", "HEAD")
    times, ct = {}, 0
    for ln in (out or "").splitlines():
        if ln.startswith("\0"):
            ct = int(ln[1:]) if ln[1:].isdigit() else 0
        elif ln.strip():
            times.setdefault(nfc(ln.strip()), ct)
    if cache:
        try:
            os.makedirs(d, mode=0o700, exist_ok=True)
            tmp = cache + ".tmp%d" % os.getpid()
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"head": head, "times": times} if out is not None else {"head": head, "failed_at": time.time()}, f)
            os.replace(tmp, cache)
        except OSError:
            pass  # 캐시는 속도만 바꾼다
    return head, times if out is not None else None


def folder_recent(repo, seeds, times, skip, k):
    """씨앗과 같은 폴더의 파일을 마지막 커밋 시각순으로. 씨앗 순서대로 채운다."""
    out = []
    for s in seeds:
        d = os.path.dirname(s)
        same = sorted((f for f in times if os.path.dirname(f) == d and f not in skip and f not in out
                       and not is_hub(f) and os.path.isfile(os.path.join(repo, f))),
                      key=lambda f: (-times[f], f))
        out += same[:k - len(out)]
        if len(out) >= k:
            break
    return out


# ── 결정 ──────────────────────────────────────────────────────────────

def decision_blocks(lines):
    """[(날짜, 제목, 본문)] — '## 날짜 제목' 절과 결정 ID 표 행(`| P14 | 제목 (날짜) | 본문 |`) 둘 다."""
    out, cur = [], None
    for ln in lines:
        m, r = DEC_HEAD.match(ln), DEC_ROW.match(ln)
        if m:
            cur = [m.group(1), m.group(2).strip(" —-"), ""]
            out.append(cur)
        elif r:
            d = DATE.search(r.group(2))
            out.append([d.group(0) if d else "", f"{r.group(1)} {r.group(2).strip()}", ln])
            cur = None
        elif ln.startswith("#"):
            cur = None
        elif cur is not None:
            cur[2] += ln + "\n"
    return out


def decisions(repo, g, nums):
    """고른 개념에 걸린 결정, 최신부터. 걸림 = 본문이 "개념 N"을 가리키거나 그 개념의 파일 이름을 백틱으로 적음."""
    if not nums:
        return []
    try:
        with open(os.path.join(repo, "DECISIONS.md"), encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return []
    names = {n: {os.path.basename(f) for f in g["nodes"][n]["files"] if not is_hub(f)} for n in nums}
    out = []
    for date, title, body in decision_blocks(lines):
        refs = {x.strip() for grp in NUM.findall(body) for x in re.split(r"[·,]", grp)}
        ticks = {os.path.basename(t.split(":")[0]) for t in PATH_TOKEN.findall(body)}
        hit = [n for n in nums if n in refs or names[n] & ticks]
        if hit:
            out.append({"date": date, "title": title[:100], "concepts": hit})
    out.sort(key=lambda d: d["date"], reverse=True)
    return out[:MAX_DECISIONS]


# ── 고르기와 조립 ─────────────────────────────────────────────────────

# 파일 출처 코드(로그용): p 프롬프트 개념 · h 인계서 · f 작업 파일 개념 · n 이웃 개념 · d 같은 폴더 최근순
SRC = {"": "p", "tag_file": "f", "tag_neighbor": "n"}


def pick(repo, matched, g, hand, folder, skip, lang=None):
    """파일 고르기. 순서: 프롬프트로 맞은 개념의 파일 → 인계서 작업 파일 → 작업 파일로 맞은 개념의 파일 → 이웃 개념의 파일 → 같은 폴더 최근순.
    프롬프트 개념이 맨 앞인 이유: 인계서 파일은 어느 프롬프트에나 같다 — 그것이 먼저 차면 그래프가 보탤 자리가 없다."""
    files, why, src = [], {}, {}
    w = WORDS[concepts.lang_of(lang)]

    def add(f, reason, code):
        if f not in skip and f not in files and len(files) < MAX_FILES and not is_hub(f) \
                and os.path.isfile(os.path.join(repo, f)):
            files.append(f); why[f] = reason; src[f] = code

    def concept_files(kinds, tag):
        for num, _, kind in matched:
            if kind in kinds:
                for f in g["nodes"][num]["files"]:
                    add(f, (w["concept"] % num) + (w[tag] if tag else ""), SRC[tag])

    concept_files(("prompt",), "")
    for f in hand:
        add(f, w["handoff"], "h")
    concept_files(("file",), "tag_file")
    concept_files(("neighbor",), "tag_neighbor")
    for f in folder:
        add(f, w["folder"], "d")
    return files, why, src


def select(repo, prompt, transcript_path=None):
    """맥락 꾸러미(dict). 파일을 쓰지 않는다(최근순 캐시 제외). 이유 문장의 언어는 여기서 한 번 정한다(pack["lang"])."""
    lang = i18n.lang(repo)
    g = graph(repo, lang)
    hand = handoff_files(repo)
    touched, cut = session_files(repo, transcript_path)
    seeds = touched[:5] + [f for f in hand if f not in touched[:5]]
    head, times = last_commit_times(repo)
    git_ok = times is not None
    times = times or {}
    matched = concept_matches(g, prompt, seeds, lang)
    skip = set(touched)
    folder = folder_recent(repo, seeds, times, skip, MAX_FILES)
    files, why, src = pick(repo, matched, g, hand, folder, skip, lang)
    nums = [n for n, _, _ in matched]
    return {
        "version": VERSION, "head": head[:12], "lang": lang,
        "state": "NO_MAP" if g is None else rules.state_of([n for n, _, k in matched if k == "prompt"]),
        "map": g["rel"] if g else None,
        "map_warnings": g["warnings"] if g else [],
        "concepts": [{"num": n, "title": g["nodes"][n]["title"], "why": r, "kind": k} for n, r, k in matched],
        "files": [{"path": f, "why": why[f], "src": src[f]} for f in files],
        "decisions": decisions(repo, g, nums) if g else [],
        "seeds": {"handoff": len(hand), "session": len(touched), "tail_cut": cut, "git_ok": git_ok},
        # 같은 턴의 기준선 — 모두 같은 skip·같은 k. 측정은 이것들과 files를 같은 정답으로 비교한다(설계안 7절).
        # nograph = 개념 그래프만 뺀 조립기. 그래프가 보탠 몫은 files와 이것의 차이다.
        "baselines": {"folder": folder, "handoff": [f for f in hand if f not in skip][:MAX_FILES],
                      "nograph": pick(repo, [], g, hand, folder, skip, lang)[0]},
    }


def render(pack, max_chars=MAX_CHARS):
    """넣을 글. 고른 것이 없으면 "". max_chars를 넘는 줄부터는 버린다(줄 중간에서 자르지 않는다)."""
    if not (pack["concepts"] or pack["files"] or pack["decisions"]):
        return ""
    w = WORDS[concepts.lang_of(pack.get("lang"))]
    L = [w["head"]]
    if pack["concepts"]:
        L += ["", w["concepts"] % pack["map"]] + [f"- {c['num']}. {c['title']} — {c['why']}" for c in pack["concepts"]]
    if pack["files"]:
        L += ["", w["files"]] + [f"- {f['path']} — {f['why']}" for f in pack["files"]]
    if pack["decisions"]:
        L += ["", w["decisions"]] + [f"- {d['date']} {d['title']}" for d in pack["decisions"]]
    out, used = [], 0
    if len(L[0]) + 1 > max_chars:
        return ""
    for ln in L[:MAX_LINES]:
        ln = ln[:200]
        if used + len(ln) + 1 > max_chars:
            break
        out.append(ln); used += len(ln) + 1
    return "\n".join(out) + "\n"


def summary(pack):
    """관찰 로그에 남길 모양 — 경로는 저장소 기준 상대 경로, 프롬프트 원문은 없다."""
    return {"version": pack["version"], "head": pack["head"], "state": pack["state"],
            "concepts": [c["num"] for c in pack["concepts"]], "kinds": [c["kind"] for c in pack["concepts"]],
            "files": [f["path"] for f in pack["files"]], "src": "".join(f["src"] for f in pack["files"]),
            "decisions": len(pack["decisions"]), "seeds": pack["seeds"], "baselines": pack["baselines"]}


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] != "explain":
        sys.exit(__doc__ if concepts.lang_of() == "ko" else USAGE_EN)
    prompt = sys.stdin.read() if sys.argv[2] == "-" else sys.argv[2]
    repo = sys.argv[3] if len(sys.argv) > 3 else rules.repo_root()
    pack = select(repo, prompt.rstrip("\n"), os.environ.get("BATON_TRANSCRIPT"))
    print(json.dumps(summary(pack), ensure_ascii=False, indent=2))
    print()
    words = WORDS[pack["lang"]]
    for w in pack["map_warnings"]:
        print(words["warn"] % w)
    print(render(pack) or words["none"])
