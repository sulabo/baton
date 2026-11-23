#!/usr/bin/env python3
"""개념 지도 후보 — 스펙 21절 루프(관찰 → 후보 → 결정론 검증 → 사람 승격)의 앞 세 단계. 설계안(docs/research/ONTOLOGY_DESIGN.md) 8절.

결정론·비용 0. 이 저장소의 Claude Code 세션 기록에서 "사람 프롬프트 하나 → 그 턴에 고친 파일"을 모아 두 종류 후보를 낸다.
 - 별칭: 개념 C의 파일을 고친 턴인데 프롬프트가 C의 제목·별칭으로는 안 맞았다 → 그 프롬프트의 구절이 C의 별칭 후보.
 - 새 개념: 어느 개념에도 안 맞는 프롬프트 뒤에 어느 개념에도 없는 파일을 고쳤다 → 구절(이름 제안) + 그 파일 묶음.
후보는 저장소 밖 캐시에만 쓴다. 프롬프트 원문은 남기지 않는다(구절만). CONCEPTS.md는 사람이 고른 별칭만 promote-alias로 쓴다.
세션 기록 전체를 읽으므로 훅에서는 부르지 않는다.

  candidates.py scan [저장소 루트] [--json]          후보를 다시 만들어 캐시에 쓰고 보여 준다
  candidates.py promote-alias <번호> "<구절>" <저장소 루트>  사람이 고른 별칭을 그 개념 메타 줄의 별칭=에 덧붙인다(인자 셋 정확히)
  candidates.py dismiss <후보 id> [저장소 루트]       사람이 버린 후보 — 다음 scan부터 안 낸다
"""
import collections, getpass, glob, hashlib, json, os, re, sys, tempfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compiler, concepts, config, handoff_check, i18n, rules

VERSION = "candidates-v1"
# 설계안 8절에서 데이터 보기 전에 고정한 값
MIN_DAYS = 3               # 서로 다른 날 — promote.sh와 같은 문턱
MIN_FILE_TURNS = 2         # 새 개념 후보의 파일·관련 개념은 그 구절의 턴 중 이만큼 이상에서 고쳐져야 한다
MAX_ALIASES_PER_CONCEPT, MAX_CONCEPTS, MAX_FILES, MAX_NAMES = 5, 10, 5, 3
EDIT_TOOLS = compiler.TOUCH_TOOLS - {"Read"}
CHUNK = 1 << 23            # 세션 기록 원문 검색 단위(8MB)
NOT_HUMAN = ("This session is being continued", "Another Claude session sent", "[Request interrupted")
OFFSET = re.compile(r"([+-]\d{2})(\d{2})$")
BAD_ALIAS = re.compile(r"[,，()`\r\n\t]| · |^없음$|^-$|(?i:^none$)")  # 메타 줄 구분자·split_list가 버리는 값
ALIAS_KEY = re.compile(r"(?:^|[:·])\s*(?:별칭|aliases)=(.*?)(?= · |$)", re.I)  # concepts.field와 같은 키 앞 규칙, 두 언어
# 사람이 보는 문장. 한국어는 예전 그대로
MSG = {
    "ko": {
        "usage": __doc__.strip().split("\n\n")[-1],
        "head": "개념 지도 후보 ({map}, HEAD {head})", "no_map_name": "지도 없음",
        "input": "재료: 세션 {sessions}개({by}) · 턴 {turns} · 사람 프롬프트 턴 {prompt_turns} · 파일 고친 턴 {edit_turns}"
                 " · 개념 파일 고친 턴 {concept_turns} · 안 묶인 파일 고친 턴 {unbound_turns}",
        "observed": "관찰: 별칭 (개념, 구절) {alias_observed}개 · 새 개념 구절 {concept_observed}개 → 검증 탈락 {rejected}",
        "none": "없음", "map_warn": "지도 경고: {w} — 그 개념들은 후보 계산에서 빠졌다",
        "why_input": "재료 부족 — 못 셌다", "why_map": "개념 지도가 없다",
        "why_zero": "관찰 0 — 개념 파일을 고친 턴은 모두 이미 제목·별칭으로 맞았고, 안 묶인 파일을 고친 턴은 없었거나 개념에 맞는 프롬프트였다",
        "why_dropped": "관찰은 있었으나 검증에서 모두 빠졌다 — 사유별 수는 위 줄", "zero": "후보 0건 ({why})",
        "alias_head": "\n별칭 후보 (id · 개념 · 구절 · 서로 다른 날 · 적중 · 오발화)",
        "alias_row": "  {id}  개념 {concept} {title}  '{phrase}'  {days}일 · {hits} · {misfires}",
        "new_head": "\n새 개념 후보 (id · 이름 제안 · 파일 · 관련 개념 · 서로 다른 날 · 적중 · 오발화)",
        "concept": "개념 {n}", "new_row": "  {id}  {names}\n      파일 {files} · 관련 {rel} · {days}일 · {hits} · {misfires}",
        "cache": "\n캐시: {cache}  (CONCEPTS.md는 안 바뀜 — 승격은 사람이 고른 것만)",
        "no_cache": "캐시 폴더를 정할 수 없다(절대 경로인 XDG_CACHE_HOME·HOME이 없음) — 저장소 안에는 쓰지 않는다",
        "bad_alias": "별칭은 두 글자 이상이고 쉼표·괄호·백틱·' · '·줄바꿈이 없어야 한다(메타 줄 구분자)",
        "ref_alias": "별칭에 '개념 N'이 있으면 지도 파서가 그것을 개념 사이 참조로 센다(가짜 간선) — 번호 없이 쓴다",
        "leak": "별칭에 {hits}로 보이는 것이 있어 쓰지 않았다(지도는 공개될 수 있다) — 지우거나 일반 표기로 바꾼다",
        "no_concepts": "CONCEPTS.md가 없다", "unreadable": "{rel}을 파서가 끝까지 못 읽는다({w}) — 그것부터 고친다",
        "dup_heads": "{rel}에 개념 {num} 절이 {heads}개다 — 조립기는 마지막 절을 읽으므로 번호를 먼저 바로잡는다",
        "no_meta": "{rel}에 개념 {num}의 메타 줄이 없다",
        "multi_meta": "{rel}의 개념 {num} 절에 메타 줄이 {n}개이거나 첫 메타 줄이 코드 펜스 안이다 — "
                      "읽는 쪽이 어느 줄을 쓸지 어긋나므로 사람이 먼저 하나로 정리한다",
        "dup_alias": "개념 {num}에 이미 별칭 '{phrase}'가 있다", "no_cand": "캐시에 후보 {cid}가 없다 — scan을 먼저 돌린다",
        "promoted": "바꾼 메타 줄:\n", "dismissed": "버림: {label} — 다음 scan부터 안 낸다",
    },
    "en": {
        "usage": "  candidates.py scan [repo root] [--json]          rebuild the candidates, write them to the cache and show them\n"
                 "  candidates.py promote-alias <number> \"<phrase>\" <repo root>  add the alias a person picked to aliases= on that"
                 " concept's metadata line (exactly three arguments)\n"
                 "  candidates.py dismiss <candidate id> [repo root]   a candidate a person rejected — later scans won't show it",
        "head": "Concept map candidates ({map}, HEAD {head})", "no_map_name": "no map",
        "input": "Input: sessions {sessions} ({by}) · turns {turns} · turns with a human prompt {prompt_turns}"
                 " · turns that edited files {edit_turns} · turns that edited concept files {concept_turns}"
                 " · turns that edited files in no concept {unbound_turns}",
        "observed": "Observed: aliases (concept, phrase) {alias_observed} · new-concept phrases {concept_observed}"
                    " → dropped by the checks {rejected}",
        "none": "none", "map_warn": "map warning: {w} — those concepts were left out of the candidates",
        "why_input": "not enough input — could not count", "why_map": "there is no concept map",
        "why_zero": "nothing observed — every turn that edited a concept's files already matched its title or an alias, and turns that"
                    " edited files in no concept either didn't exist or followed a prompt that matched a concept",
        "why_dropped": "there were observations, but the checks dropped all of them — the counts by reason are in the line above",
        "zero": "No candidates ({why})",
        "alias_head": "\nAlias candidates (id · concept · phrase · distinct days · hits · misfires)",
        "alias_row": "  {id}  concept {concept} {title}  '{phrase}'  {days} days · {hits} · {misfires}",
        "new_head": "\nNew concept candidates (id · suggested names · files · related concepts · distinct days · hits · misfires)",
        "concept": "concept {n}", "new_row": "  {id}  {names}\n      files {files} · related {rel} · {days} days · {hits} · {misfires}",
        "cache": "\nCache: {cache}  (CONCEPTS.md is unchanged — only what a person picks is promoted)",
        "no_cache": "Can't choose a cache folder (no absolute XDG_CACHE_HOME or HOME) — candidates are never written inside the repo",
        "bad_alias": "An alias needs at least two characters and no comma, parentheses, backtick, ' · ' or line break"
                     " (they separate the metadata line)",
        "ref_alias": "An alias that contains 'concept N' would be counted by the map parser as a reference between concepts"
                     " (a false edge) — write it without the number",
        "leak": "The alias contains what looks like {hits}, so it was not written (the map may be public) — remove it or use a"
                " generic word",
        "no_concepts": "There is no CONCEPTS.md", "unreadable": "The parser can't read {rel} to the end ({w}) — fix that first",
        "dup_heads": "{rel} has {heads} sections for concept {num} — the compiler reads the last one, so fix the numbers first",
        "no_meta": "Concept {num} in {rel} has no metadata line",
        "multi_meta": "Concept {num} in {rel} has {n} metadata lines, or its first metadata line is inside a code fence —"
                      " readers could use different lines, so a person should merge them into one first",
        "dup_alias": "Concept {num} already has the alias '{phrase}'", "no_cand": "No candidate {cid} in the cache — run scan first",
        "promoted": "Changed metadata line:\n", "dismissed": "Dismissed: {label} — later scans won't show it",
    },
}


def words(lang=None):
    return MSG[concepts.lang_of(lang)]


def claude_projects():
    base = os.environ.get("CLAUDE_CONFIG_DIR") or (os.path.join(os.environ["HOME"], ".claude") if os.environ.get("HOME") else "")
    return os.path.join(base, "projects") if base else None


def when(ts):
    """시각(타임존 없으면 UTC로 본다). 못 읽으면 None."""
    try:
        # Python 3.9의 fromisoformat은 'Z'와 콜론 없는 오프셋('+0900')을 못 읽는다 — '+00:00'·'+09:00'으로 바꿔 넘긴다
        t = datetime.fromisoformat(OFFSET.sub(r"\1:\2", ts.replace("Z", "+00:00")))
    except (AttributeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def human_text(content):
    """문자열이거나 text 블록만이면 사람 프롬프트. tool_result가 섞이면 아니다(observer/measure/extract_prompts.py와 같은 규칙)."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list) and not any(isinstance(x, dict) and x.get("type") == "tool_result" for x in content):
        return " ".join(x.get("text", "") for x in content if isinstance(x, dict) and x.get("type") == "text").strip()
    return None


# ── 관찰: 세션 기록 → 턴 ──────────────────────────────────────────────

def mentions(path, needle):
    """세션 기록 원문에 needle(바이트)이 있나 — JSON을 풀기 전에 싸게 거른다."""
    try:
        with open(path, "rb") as fh:
            tail = b""
            for chunk in iter(lambda: fh.read(CHUNK), b""):
                buf = tail + chunk
                if needle in buf:
                    return True
                tail = buf[-(len(needle) - 1):] if len(needle) > 1 else b""  # 청크가 needle보다 짧아도 경계에 걸친 것을 찾는다
    except OSError:
        pass
    return False


def session_files(repo):
    """(이 저장소의 세션 기록 경로들, 건너뛴·포함 사유별 수).
    포함: 첫 cwd가 저장소 안인 세션 + 다른 폴더에서 열었지만 기록에 저장소 경로가 나오는 세션(저장소 밖에서 열고 이 저장소 파일을 고친 작업).
    다른 폴더 세션의 다른 일 프롬프트는 오발화 분모에만 들어간다 — 후보를 덜 내는 쪽(보수적)."""
    # ponytail: 모든 세션 기록을 한 번 훑는다(2.9GB에서 수십 초). 오프라인 명령이라 감수, 느려지면 날짜로 자른다
    root = compiler.nfc(os.path.realpath(repo)).rstrip("/")
    needle = (root + "/").encode("utf-8")
    base = claude_projects()
    counts = collections.Counter()
    if not base:
        return [], counts
    by_id = {}
    for f in glob.glob(os.path.join(glob.escape(base), "*", "*.jsonl")):
        by_id.setdefault(os.path.basename(f), []).append(f)
    out = []
    for sid in sorted(by_id):
        f = max(by_id[sid], key=os.path.getsize)  # 폴더 이름 변경으로 생긴 사본 — 가장 긴 것
        cwd = entry = None
        try:
            with open(f, encoding="utf-8", errors="ignore") as fh:
                for ln in fh:
                    try:
                        d = json.loads(ln)
                    except ValueError:
                        continue
                    if isinstance(d, dict):
                        cwd = cwd or d.get("cwd")
                        entry = entry or d.get("entrypoint")
                    if cwd and entry:
                        break
        except OSError:
            counts["unreadable"] += 1
            continue
        c = compiler.nfc(os.path.realpath(cwd)) if isinstance(cwd, str) else ""
        inside = c == root or c.startswith(root + "/")
        if not inside and not mentions(f, needle):
            continue  # 이 저장소와 무관한 세션 — 세지 않는다
        counts["duplicate"] += len(by_id[sid]) - 1
        if isinstance(entry, str) and entry.startswith("sdk"):
            counts["non_cli"] += 1       # claude -p·SDK
        else:
            counts["opened_here" if inside else "opened_elsewhere"] += 1
            out.append(f)
    return out, counts


def read_turns(repo, path):
    """[{"day", "text"(슬래시 명령이면 None), "files"(그 턴에 고친 저장소 파일, 허브 제외), "uid"(프롬프트 기록 id)}] — 메인의 사람 프롬프트가 턴 경계, 고친 것은 메인+서브에이전트."""
    prompts, edits = [], []
    files = [path] + sorted(glob.glob(os.path.join(glob.escape(path[:-len(".jsonl")]), "subagents", "*.jsonl")))
    for i, f in enumerate(files):
        try:
            fh = open(f, encoding="utf-8", errors="ignore")
        except OSError:
            continue
        with fh:
            for ln in fh:
                try:
                    d = json.loads(ln)
                except ValueError:
                    continue
                if not isinstance(d, dict):
                    continue
                t = when(d.get("timestamp"))
                if t is None:
                    continue
                if i == 0 and d.get("type") == "user" and not d.get("isMeta") and not d.get("isCompactSummary") \
                        and not d.get("isSidechain"):
                    text = human_text((d.get("message") or {}).get("content"))
                    if text and text.lstrip().startswith("<command-"):
                        prompts.append((t, None, d.get("uuid")))  # 슬래시 명령 — 턴 경계로만
                    elif text and not text.startswith("<") and not text.startswith(NOT_HUMAN):
                        prompts.append((t, text, d.get("uuid")))
                m = d.get("message") if d.get("type") == "assistant" else None
                for b in (m.get("content") if isinstance(m, dict) and isinstance(m.get("content"), list) else []):
                    if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") in EDIT_TOOLS:
                        inp = b.get("input") if isinstance(b.get("input"), dict) else {}
                        r = compiler.rel_in(repo, inp.get("file_path") or inp.get("notebook_path"))
                        if r and not compiler.is_hub(r):
                            edits.append((t, r))
    prompts.sort(key=lambda x: x[0])
    edits.sort(key=lambda x: x[0])
    turns, k = [], 0
    for n, (t, text, uid) in enumerate(prompts):
        end = prompts[n + 1][0] if n + 1 < len(prompts) else None
        while k < len(edits) and edits[k][0] < t:
            k += 1  # 첫 프롬프트 전의 편집은 어느 턴에도 안 넣는다
        got = set()
        while k < len(edits) and (end is None or edits[k][0] < end):
            got.add(edits[k][1])
            k += 1
        turns.append({"day": t.astimezone().date().isoformat(), "text": text, "files": got, "uid": uid})
    return turns


# ── 후보와 검증 ───────────────────────────────────────────────────────

def cand_id(key):
    # ponytail: 새 개념 후보의 key는 파일 묶음이라, 문턱을 넘는 파일이 하나 늘면 id가 바뀌어 버린 후보가 다시 나온다. 잦으면 겹침 기준으로 바꾼다
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]


def build(repo, turns, dismissed=(), lang=None):
    """턴 목록 → 후보 dict(단계별 수 포함). 세션 기록을 안 읽어 테스트하기 쉽게 따로 둔다. lang은 지도 경고 문장의 언어."""
    g = compiler.graph(repo, lang)
    nodes = g["nodes"] if g else {}
    owners = {}
    for num, n in nodes.items():
        for f in n["files"]:
            owners.setdefault(f, []).append(num)
    # 개념의 근거 파일 — 조립기와 같은 규칙: 허브·세 개 이상 개념에 걸린 파일은 그 개념의 근거가 아니다
    own = {num: {f for f in n["files"] if not compiler.is_hub(f) and len(owners[f]) <= compiler.SHARED_MAX}
           for num, n in nodes.items()}
    known = {w.casefold() for n in nodes.values() for w in rules.title_words(n["name"]) + n["aliases"]}

    def matched(text):
        p = text.lower()
        return {num for num, n in nodes.items()
                if any(w in p for w in rules.title_words(n["name"])) or any(a.lower() in p for a in n["aliases"])}

    out = compiler.git(repo, "ls-files", "-z")
    # 안 묶인 파일은 git이 추적하는 파일만 — .omc/·작업 트리 같은 운영 파일이 새 개념 후보를 차지하지 않게. git이 없으면 지금 있는 파일
    tracked = {compiler.nfc(x) for x in out.split("\0") if x} if out is not None else None

    def unbound(f):
        return f not in owners and (f in tracked if tracked is not None else os.path.isfile(os.path.join(repo, f)))

    texts = [t for t in turns if t["text"]]
    for t in texts:
        t["_p"] = t["text"].casefold()
        t["_c"] = {num for num, fs in own.items() if t["files"] & fs}
        t["_u"] = {f for f in t["files"] if unbound(f)}
        t["_m"] = matched(t["text"])
    counts = {"turns": len(turns), "prompt_turns": len(texts), "edit_turns": sum(1 for t in texts if t["files"]),
              "concept_turns": sum(1 for t in texts if t["_c"]), "unbound_turns": sum(1 for t in texts if t["_u"]),
              "concepts": len(nodes), "unbound_basis": "git_tracked" if tracked is not None else "exists_now(git 실패)"}

    alias_obs, new_obs = collections.defaultdict(list), collections.defaultdict(list)
    trig = set()
    for t in texts:
        phs = rules.phrases(t["text"])
        if t["_c"] - t["_m"] or (t["_u"] and not t["_m"]):
            trig |= {ph for ph in phs if rules.TRIGGER.search(ph)}
        phs = {ph for ph in phs if not rules.TRIGGER.search(ph)}
        for num in t["_c"] - t["_m"]:
            for ph in phs:
                alias_obs[(num, ph)].append(t)
        if t["_u"] and not t["_m"]:
            for ph in phs:
                new_obs[ph].append(t)
    counts["alias_observed"], counts["concept_observed"] = len(alias_obs), len(new_obs)

    rejected = collections.Counter({"trigger": len(trig)} if trig else {})
    gone = set(dismissed)

    def fires(ph, hit):
        """그 구절이 든 사람 프롬프트 중 맞는 턴이 아닌 것의 수 — 조립기가 그 구절로 잘못 고르게 될 횟수."""
        return sum(1 for t in texts if ph in t["_p"] and not hit(t))

    def dup(ph):
        return any(ph == w or w in ph or ph in w for w in known)

    def check(key, ph, days, hits, mis):
        reason = ("days" if len(days) < MIN_DAYS else "duplicate" if dup(ph) else
                  "misfire" if mis > hits else "dismissed" if cand_id(key) in gone else None)
        if reason:
            rejected[reason] += 1
        return reason is None

    aliases = collections.defaultdict(list)
    for (num, ph), ts in alias_obs.items():
        days = {t["day"] for t in ts}
        if len(days) < MIN_DAYS:  # 대부분 여기서 빠진다 — 오발화 계산(프롬프트 전체 훑기)을 하기 전에 거른다
            rejected["days"] += 1
            continue
        mis = fires(ph, lambda t, num=num: num in t["_c"])
        key = f"alias|{num}|{ph}"
        if check(key, ph, days, len(ts), mis):
            aliases[num].append({"id": cand_id(key), "concept": num, "title": nodes[num]["title"], "phrase": ph,
                                 "days": len(days), "hits": len(ts), "misfires": mis})
    alias_out = []
    for num in sorted(aliases, key=int):
        alias_out += sorted(aliases[num], key=lambda c: (-c["days"], c["misfires"], c["phrase"]))[:MAX_ALIASES_PER_CONCEPT]

    groups = {}
    for ph in sorted(new_obs):
        ts = new_obs[ph]
        fc = collections.Counter(f for t in ts for f in t["_u"])
        files = sorted([f for f, c in fc.items() if c >= MIN_FILE_TURNS], key=lambda f: (-fc[f], f))[:MAX_FILES]
        if not files:
            rejected["no_files"] += 1
            continue
        fs = set(files)
        hit_turns = [t for t in ts if t["_u"] & fs]
        days = {t["day"] for t in hit_turns}
        if len(days) < MIN_DAYS:
            rejected["days"] += 1
            continue
        mis = fires(ph, lambda t: bool(t["files"] & fs))
        key = "concept|" + "|".join(sorted(files))
        if not check(key, ph, days, len(hit_turns), mis):
            continue
        g_ = groups.setdefault(key, {"id": cand_id(key), "files": files, "names": [], "_turns": {}})
        g_["names"].append({"phrase": ph, "days": len(days), "hits": len(hit_turns), "misfires": mis})
        g_["_turns"].update((id(t), t) for t in ts)
    concept_out = []
    for g_ in groups.values():
        # 관련 개념 = 묶음에 합쳐진 구절들이 든 턴 전부에서 MIN_FILE_TURNS턴 이상 파일이 고쳐진 기존 개념
        rc = collections.Counter(num for t in g_.pop("_turns").values() for num in t["_c"])
        g_["related"] = sorted([n for n, c in rc.items() if c >= MIN_FILE_TURNS], key=int)
        g_["names"].sort(key=lambda c: (-c["days"], c["misfires"], -c["hits"], c["phrase"]))
        best = g_["names"][0]
        g_.update(days=best["days"], hits=best["hits"], misfires=best["misfires"])
        g_["names"] = g_["names"][:MAX_NAMES]
        concept_out.append(g_)
    concept_out = sorted(concept_out, key=lambda c: (-c["days"], c["misfires"], c["names"][0]["phrase"]))[:MAX_CONCEPTS]
    return {"version": VERSION, "map": g["rel"] if g else None, "map_warnings": g["warnings"] if g else [],
            "counts": counts, "rejected": dict(rejected),
            "aliases": alias_out, "concepts": concept_out}


# ── 캐시 ──────────────────────────────────────────────────────────────

def cache_path(repo):
    d = compiler.cache_dir()
    if not d:
        return None
    name = hashlib.sha1(compiler.nfc(os.path.realpath(repo)).encode()).hexdigest()[:16] + ".json"
    return os.path.join(os.path.dirname(d), "candidates", name)


def load(repo):
    p = cache_path(repo)
    try:
        with open(p, encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except (TypeError, OSError, ValueError):
        return {}


def save(repo, data, lang=None):
    p = cache_path(repo)
    if not p:
        raise OSError(words(lang)["no_cache"])
    os.makedirs(os.path.dirname(p), mode=0o700, exist_ok=True)  # 구절은 프롬프트에서 나온 것 — 조립기 캐시와 같은 권한
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, p)
    return p


def scan(repo, lang=None):
    paths, by = session_files(repo)
    turns, seen = [], set()
    for p in paths:
        for t in read_turns(repo, p):
            if t["uid"] and t["uid"] in seen:
                by["turn_copied"] += 1  # --resume·fork로 다른 기록에 복사된 같은 프롬프트 — 한 번만 센다
                continue
            seen.add(t["uid"])
            turns.append(t)
    dismissed = load(repo).get("dismissed") or []
    out = build(repo, turns, {d.get("id") for d in dismissed if isinstance(d, dict)}, lang)
    out["counts"] = {"sessions": len(paths), **out["counts"]}
    out.update(generated=datetime.now().astimezone().isoformat(timespec="seconds"),
               head=(compiler.git(repo, "rev-parse", "--short", "HEAD") or "").strip() or None,
               sessions_by={k: v for k, v in by.items() if v}, dismissed=dismissed)
    out["cache"] = save(repo, out, lang)
    return out


def render(d, lang=None):
    c, rj, w = d["counts"], d["rejected"], words(lang)
    out = [w["head"].format(map=d.get("map") or w["no_map_name"], head=d.get("head") or "?"),
           w["input"].format(**{**c, "sessions": c.get("sessions", "?"), "by": d.get("sessions_by") or {}}),
           w["observed"].format(rejected=rj or w["none"], **c)]
    out += [w["map_warn"].format(w=x) for x in d.get("map_warnings") or []]
    if not d["aliases"] and not d["concepts"]:
        why = (w["why_input"] if not c["prompt_turns"] or not c["edit_turns"] else
               w["why_map"] if not c["concepts"] else
               w["why_zero"] if not c["alias_observed"] and not c["concept_observed"] else
               w["why_dropped"])
        out.append(w["zero"].format(why=why))
    if d["aliases"]:
        out.append(w["alias_head"])
        out += [w["alias_row"].format(**a) for a in d["aliases"]]
    if d["concepts"]:
        out.append(w["new_head"])
        for k in d["concepts"]:
            names = ", ".join(f"'{n['phrase']}'" for n in k["names"])
            rel = ", ".join(w["concept"].format(n=n) for n in k["related"]) or w["none"]
            out.append(w["new_row"].format(id=k["id"], names=names, files=", ".join(k["files"]), rel=rel,
                                           days=k["days"], hits=k["hits"], misfires=k["misfires"]))
    out.append(w["cache"].format(cache=d.get("cache")))
    return "\n".join(out)


# ── 사람 승격 ─────────────────────────────────────────────────────────

def promote_alias(repo, num, phrase, lang=None):
    """그 개념 메타 줄의 별칭=에 phrase를 덧붙인다. 다른 내용은 안 건드린다. 반환: 바뀐 메타 줄.
    영어 메타 줄(- **Meta**:)이면 aliases=에 붙인다 — 지도에 이미 쓰인 언어를 따른다."""
    w = words(lang)
    phrase = phrase.strip()
    if len(phrase) < 2 or BAD_ALIAS.search(phrase):
        raise ValueError(w["bad_alias"])
    # 별칭은 프롬프트에서 나와 공개될 수 있는 CONCEPTS.md에 들어간다 — 인계서 검사와 같은 비밀값·홈 경로·개인 자료 목록으로 거른다.
    # 걸린 값 자체는 다시 출력하지 않는다(종류만)
    if concepts.REF.search(phrase):
        raise ValueError(w["ref_alias"])
    # 이 컴퓨터의 사용자 이름·홈 폴더 이름도 개인 자료다(홈 경로 패턴은 절대 경로 꼴만 잡는다)
    me = [getpass.getuser(), os.path.basename((os.environ.get("HOME") or "").rstrip("/"))]
    hits = handoff_check.leaks(phrase, config.terms("private_terms", repo) + [t for t in me if t], lang=concepts.lang_of(lang))
    if hits:
        raise ValueError(w["leak"].format(hits="·".join(hits)))
    path, rel = rules.concept_path(repo)
    if not path:
        raise ValueError(w["no_concepts"])
    with open(path, encoding="utf-8", newline="") as fh:
        lines = fh.read().split("\n")
    lost = concepts.warnings(lines, concepts.lang_of(lang))
    if lost:
        raise ValueError(w["unreadable"].format(rel=rel, w=lost[0]))
    # 고를 메타 줄은 읽는 쪽(compiler.graph·concepts.py meta)과 같은 규칙으로 찾는다: concepts.walk의 절 본문에서 첫 메타 줄.
    # walk는 펜스 안 줄도 본문에 넣으므로 펜스 안 메타 줄도 후보로 센다 — 그 줄이 첫 줄이거나 메타 줄이 둘 이상이면
    # 읽는 쪽과 쓰는 쪽이 다른 줄을 볼 수 있어 거절한다
    cur, metas, heads = None, [], 0
    for i, (ln, (fenced, _)) in enumerate(zip(lines, concepts.fences(lines))):
        if fenced:
            if cur == str(num) and concepts.META.match(ln):
                metas.append((i, True))
            continue
        m = concepts.SECTION.match(ln)
        if m:
            cur = m.group(1)
            heads += cur == str(num)
        elif concepts.OTHER_HEADING.match(ln):
            cur = None
        elif cur == str(num) and concepts.META.match(ln):
            metas.append((i, False))
    if heads > 1:
        raise ValueError(w["dup_heads"].format(rel=rel, num=num, heads=heads))
    if not metas:
        raise ValueError(w["no_meta"].format(rel=rel, num=num))
    if len(metas) > 1 or metas[0][1]:
        raise ValueError(w["multi_meta"].format(rel=rel, num=num, n=len(metas)))
    idx = metas[0][0]
    line = lines[idx].rstrip("\r")
    cr = lines[idx][len(line):]
    m = ALIAS_KEY.search(line)
    if m:
        have = compiler.split_list(m.group(1))
        if phrase.casefold() in {a.casefold() for a in have}:
            raise ValueError(w["dup_alias"].format(num=num, phrase=phrase))
        old = m.group(1).rstrip()
        # 사람이 적은 값(괄호 설명·백틱 등)은 그대로 두고 뒤에만 붙인다. 비었거나 '없음'·'none'·'-'이면 그 자리를 바꾼다
        line = line[:m.start(1)] + (phrase if old in ("", "없음", "-") or old.lower() == "none" else f"{old}, {phrase}") + line[m.end(1):]
    else:
        key = "aliases" if line.startswith("- **Meta**") else "별칭"
        line = line.rstrip() + f" · {key}={phrase}"
    lines[idx] = line + cr
    # 통째로 바꿔 쓴다 — 쓰다 멈춰도 지도가 반쯤 잘린 채 남지 않게. 권한은 원래 파일 것을 이어받는다
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".CONCEPTS.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write("\n".join(lines))
        os.chmod(tmp, os.stat(path).st_mode & 0o7777)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return line


def dismiss(repo, cid, lang=None):
    d = load(repo)
    for kind in ("aliases", "concepts"):
        for c in d.get(kind) or []:
            if c.get("id") == cid:
                d[kind].remove(c)
                label = c.get("phrase") or ", ".join(n["phrase"] for n in c.get("names", []))
                d.setdefault("dismissed", []).append({"id": cid, "kind": kind, "label": label})
                save(repo, d, lang)
                return label
    raise ValueError(words(lang)["no_cand"].format(cid=cid))


def main(argv):
    if not argv or argv[0] not in ("scan", "promote-alias", "dismiss"):
        print(words()["usage"])
        return 2
    cmd, rest = argv[0], [a for a in argv[1:] if a != "--json"]
    need = {"scan": 0, "promote-alias": 2, "dismiss": 1}[cmd]
    # 쓰는 명령은 저장소를 꼭 받고 인자 수가 정확해야 한다 — 따옴표 없는 두 단어 구절이 쪼개지거나 구절을 빼먹으면
    # 경로가 구절로, 현재 폴더가 저장소로 읽혀 엉뚱한 지도에 쓰게 된다
    if len(rest) < need or (cmd == "promote-alias" and len(rest) != 3):
        print(words()["usage"])
        return 2
    repo = rest[need] if len(rest) > need else rules.repo_root()
    lang = i18n.lang(repo)  # 한 번만 정한다
    w = words(lang)
    try:
        if cmd == "scan":
            d = scan(repo, lang)
            print(json.dumps(d, ensure_ascii=False, indent=1) if "--json" in argv else render(d, lang))
        elif cmd == "promote-alias":
            print(w["promoted"] + promote_alias(repo, rest[0], rest[1], lang))
        else:
            print(w["dismissed"].format(label=dismiss(repo, rest[0], lang)))
    except (ValueError, OSError) as e:
        print(f"candidates: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
