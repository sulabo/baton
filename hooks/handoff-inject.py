#!/usr/bin/env python3
# UserPromptSubmit 훅. 프롬프트가 인계나 진행 상황을 가리킬 때만 HANDOFF.md 전문을 컨텍스트로 넣는다.
#
# 왜 이 모양인가 (docs/research/LOOP_PLAN.md 루프 1, 게임 저장소 n=5):
#  - 상태 질문에 전문을 넣으면 입력 토큰 -45%, 턴 5→3. 인계서를 다시 여는 일이 5/5→0/5.
#  - 인계와 무관한 작업에 넣으면 +11%. 넣은 것이 매 턴 컨텍스트에 남기 때문이다.
#  - 세션 시작 훅은 프롬프트를 못 본다. 그래서 프롬프트 제출 시점에 가린다.
#
# 200줄과 LIMIT_CHARS(훅 출력 전체) 중 먼저 닿는 곳까지만 넣는다. 줄 상한은 소유자 결정(09-22).
# 글자 상한은 Claude Code 문서의 훅 출력 상한에 여유를 둔 값이다. https://code.claude.com/docs/en/hooks "JSON output"(2026-11-21 확인):
# "A hook's additionalContext, systemMessage, and initialUserMessage strings, and its plain stdout, are capped at 10,000
# characters" — 넘으면 세션 폴더의 파일로 저장하고 경로와 앞 2,000자 미리보기만 넘긴다. "this cap has no setting or environment
# variable to raise it". 실측(루프 2)도 같다: 8,995자는 그대로 들어갔고, 20,826자는 파일로 빠져 에이전트가 그 파일을 다시 cat했다.
# ponytail: 여유 400자. 문서의 "characters"가 UTF-16 단위인지는 확인 못 함 — 그렇다면 이모지처럼 BMP 밖 글자는 둘로 센다.
# 인계서 본문 예산은 머리말·신선도 한 줄(최대 rules.FRESHNESS_MAX)·꼬리 안내 몫을 뺀 나머지다 — 최소 8,724자로(11-24 머리말 문장 추가 뒤)
# 검사기 상한 8,700자(PR #14)를 늘 넘는다. 영어는 머리말이 길어 신선도 상한이 rules.FRESHNESS_MAX_EN이고 최소 8,714자다.
# hooks/test_handoff_inject.py HookOutputBudgetTest가 두 언어의 셈을 묶는다.
# 넘치면 잘랐다는 것을 한 줄로 말한다 — 조용히 자르면 뒤쪽에 있는 다음 행동을 "없음"으로 읽는다.
# 필독 줄: "관련 파일·심볼" 절에서 (필독)·(must read) 표시가 붙은 항목(최대 3개)을 신선도 줄 바로 뒤 한 줄로 올린다
# (lib/handoff_check.py must_read_line) — 잘려도 남고 건너뛰지 않게. 검사기가 이 줄 길이까지 8,700자에 세므로 통과한 인계서는 그대로 전부 들어간다.
# 한 세션에 같은 인계서는 한 번만 넣는다 — 파일이 바뀌었거나 그 뒤 세션이 압축됐을 때만 다시 넣는다. 사람이 친 프롬프트가 아닌 것
# (다른 세션의 <agent-message>, <task-notification>)에는 넣지 않는다. 11-18 실사용 로그: 주입 263번 중 226번이 같은 세션의 재주입,
# 세션 기록과 대조하니 최소 152번은 다른 세션 메시지가 계기였다(한 세션에 41번, 매번 8~9천 자).
# 머리말 바로 뒤에 신선도 한 줄(작성일·며칠 전·그 뒤 커밋 수, lib/rules.py handoff_freshness)을 붙인다 — 인계서는 가설이다.
# "다시 열 필요 없다"는 그대로 둔다(재독 5/5→0/5, 루프 2). 2026-11-08 낡은 백업 폴더의 38일 된 인계서가
# "그대로 이어서 진행한다"와 함께 주입된 일로 그 뒷문장만 "주장 한두 개를 확인한 뒤 진행"으로 바꿨다(재독 영향 미측정).
# 신선도는 실제로 넣을 때만 센다(git 합계 rules.GIT_BUDGET 3초) — machine·already로 건너뛸 때는 git을 부르지 않는다.
# 훅 시한은 10초(hooks.json)다. 신선도는 훅 시작 + HOOK_DEADLINE(8.5초)을 넘겨 쓰지 않고, 시간이 없으면 못 셌다고 적고 넣는다.
# 그 앞의 repo_root(Codex만)·config.repo_key(설정에 저장소 절이 있을 때)는 git이 멈추면 각 5초 — 그 둘만으로 10초에 닿을 수
# 있다(이 기능 전부터, PR #16 기준 Codex+설정 10.1초 실측). 그때 훅이 죽으면 인계서는 조용히 안 들어간다 — 이 PR에서 안 고친다.
# 끄기: BATON_HANDOFF_INJECT=off. 이 스위치들과 추가 트리거 말은 환경변수 또는 설정 파일에서 읽는다(lib/config.py, /baton-setup).
# 개념 색인: 저장소에 CONCEPTS.md가 있으면 세션의 첫 사람 프롬프트에 한 번 개념 색인(lib/concepts.py index — 개념마다
# 이름·제목의 "—" 뒤 한 줄·주요 파일 한 줄, 최대 concepts.INDEX_LIMIT_CHARS자)을 인계서 뒤에 넣는다. 에이전트가 스스로 고른다(북극성 3절 기준선 ②).
# 같은 세션 기억 파일에 index_offset으로 따로 적어, 인계서와 색인이 각자 한 번씩 들어간다. 압축 뒤에는 인계서처럼 다시 넣는다.
# 예산: 색인 몫을 먼저 잡고 인계서 본문 예산을 그만큼 줄이되, HANDOFF_KEEP(검사기 상한 + 끝 줄바꿈) 밑으로는 줄이지 않는다 —
# 검사기를 통과한 인계서는 색인 때문에 더 잘리지 않는다. 둘 다 안 들어가면 색인을 줄이고, 그래도 안 되면 색인을 빼고 인계서를
# 예산을 덜지 않은 판으로 되돌린다(빠질 색인 때문에 인계서를 자르지 않는다). 끄기: BATON_CONCEPT_INDEX=off.
# 무엇이 터져도 색인만 빠진다(fail-open). 세션 기억을 쓸 수 없으면(세션 id 없음·캐시 폴더에 못 씀) 색인을 넣지 않는다 —
# 매 프롬프트 1,500자가 쌓이는 것보다 한 세션 색인을 잃는 쪽이 싸다(인계서는 예전처럼 매번 넣는다).
# ponytail: 같은 세션의 훅 둘이 동시에 기억을 읽고 쓰면 나중 쓴 쪽만 남아 다른 쪽 기억(sha 또는 index_offset)을 잃는다 — 그 내용이
# 한 번 더 들어갈 뿐이다. 잠금(fcntl)으로 올릴 수 있다.
# ponytail: 색인을 넣은 뒤에는 사람 프롬프트마다 세션 기록을 index_offset부터 끝까지 다시 훑어 압축을 찾는다(최대 SEEN_SCAN_MAX,
# 43MB 실측 30~112ms). 넘치면 다시 넣고 offset이 새로 잡힌다. 훑은 끝 위치를 기억해 이어 읽는 쪽으로 올릴 수 있다.
# 실험: BATON_CONCEPT_INJECT=on 이면 프롬프트가 개념 제목을 가리킬 때 CONCEPTS.md의 해당 절만 넣는다.
#
# 관찰(북극성 길 단계 1): 프롬프트마다 규칙 판단(lib/rules.py)과 실제로 넣은 것을 판단 로그에 한 줄 남긴다.
# 행동은 판단 때문에 바뀌지 않는다. 로그 위치는 BATON_LOG(기본 ~/.cache/baton/runs.jsonl) — 저장소마다 .baton/을 만들지 않으려고
# 사용자 캐시 한 곳에 저장소 이름을 붙여 쓴다(정본 43절은 .baton/runs.jsonl). 끄기: BATON_OBSERVE=off. 로그 실패는 조용히 넘긴다.
import hashlib, json, os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import concepts, config, handoff_check, i18n, rules, runlog

LIMIT = 200
LIMIT_CHARS = 9600  # 훅 출력 전체(문서 상한 10,000자 − 여유 400)
TAIL_RESERVE = 200  # 잘렸을 때 붙이는 꼬리 안내 몫
CONCEPT_LIMIT_CHARS = 2000
HANDOFF_KEEP = handoff_check.MAX_CHARS + 1  # 색인 몫 때문에 인계서 본문 예산을 이 밑으로 줄이지 않는다 — 검사기 상한 + 끝 줄바꿈
# (검사기 8,700자 → 8,701. 상수를 따로 두면 검사기와 갈라진다 — 리뷰 MEDIUM-1)
TRIGGER = rules.TRIGGER
SEEN_SCAN_MAX = 64 * 1024 * 1024  # 넣은 뒤 세션 기록이 이보다 많이 자랐으면 읽지 않고 다시 넣는다(43MB 세션 기록 실측, 11-18)
SEEN_KEEP_DAYS = 7
HOOK_DEADLINE = 8.5  # 훅 시작부터 이 초 뒤에는 신선도 git을 부르지 않는다(훅 시한 10초 — 출력·로그 몫을 남긴다)
# 세션 기록의 압축 경계 줄 — Claude Code `"subtype":"compact_boundary"`(11-18 실제 기록 27개 파일 84건),
# Codex `"type":"compacted"`(~/.codex/sessions 실제 기록 확인). 본문 속 같은 글자는 JSON 이스케이프(\")라 걸리지 않는다.
# ponytail: /rewind·다른 훅의 block으로 넣은 맥락이 빠져도 기록 크기는 그대로라 알아채지 못한다 — 다음 "이어서"에서 안 넣는다.
# 그때는 에이전트가 파일을 직접 읽는다(baton 전 동작). 넣은 줄(hook_additional_context)이 실제로 기록됐는지 보는 쪽으로 올릴 수 있다
COMPACT_MARKS = (b'"subtype":"compact_boundary"', b'"type":"compacted"')
HEAD = ("[baton] 아래는 이 저장소 HANDOFF.md의 전문이다(프롬프트가 인계·진행 상황을 가리켜 자동 주입). "
        "파일을 다시 열 필요 없다. 다만 인계서는 작성 시점의 기록이다 — 사실이 아니라 가설로 읽고, "
        "다음 행동이 기대는 주장 한두 개만 git·파일로 확인한 뒤 이어서 진행한다. "
        "'소유자 확인' 항목은 되돌릴 수 있으면 권장 기본값대로 진행하고, 되돌릴 수 없는 것만 묻는다.")
# 마지막 문장(소유자 결정 11-24): compact 맞대기 실험에서 인계서 갈래에서 실패한 경우가 모두 "사용자에게 확인할 것"을 묻고 멈춘 새 대화였다.
# 영어판은 한국어보다 길어 신선도 한 줄 상한을 rules.FRESHNESS_MAX_EN으로 줄인다 — 두 언어 모두 머리말 + 신선도 상한 + 검사기 상한
# + 꼬리 몫이 LIMIT_CHARS 안이다(HookOutputBudgetTest). 문장을 더하면서 영어 머리말을 줄여 썼다(docs/GUIDE.md 예시도 바꿔야 한다)
HEAD_EN = ("[baton] Below is this repo's full HANDOFF.md, injected because the prompt asks about handoff or progress. "
           "No need to reopen it. It was written earlier: treat it as a hypothesis, check the one or two claims the next step "
           "depends on, then continue with the next action. For Owner decisions, use the recommended default if reversible; "
           "ask only about irreversible ones.")
CONCEPT_HEAD = ("[baton] 아래는 이 저장소 {path}에서 프롬프트와 맞은 개념 한 절이다"
                "(실험 기능 BATON_CONCEPT_INJECT=on). 개념은 탐색 앵커다. 실제 동작은 필요한 경우 코드로 확인한다.")
CONCEPT_HEAD_EN = ("[baton] Below is the one concept section in this repo's {path} that matches the prompt "
                   "(experimental feature BATON_CONCEPT_INJECT=on). A concept is a starting point for finding things. "
                   "Check the code when you need the actual behavior.")


def read_input():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def on(name, repo):
    return config.get(name, repo).strip().lower() in ("on", "1", "true", "yes")


def off(name, repo):
    return config.get(name, repo).strip().lower() in ("off", "0", "false", "no")


def concept_text(num, name, body):
    return "\n".join(["## %s. %s" % (num, name)] + body).rstrip() + "\n"


def inject_concept(repo, prompt):
    """넣을 텍스트와 개념 번호. 안 넣으면 ("", None)."""
    if not on("BATON_CONCEPT_INJECT", repo):
        return "", None
    _, rel = rules.concept_path(repo)
    sections = rules.concept_sections(repo)
    if not sections:
        return "", None
    hits = [s for s in sections if rules.concept_hits([s], prompt)]
    if len(hits) != 1:
        return "", None
    num, name, body = hits[0]
    text = concept_text(num, name, body)
    head = i18n.pick(repo, CONCEPT_HEAD, CONCEPT_HEAD_EN).format(path=rel)
    if len(text) + len(head) + 2 > CONCEPT_LIMIT_CHARS:
        return "", None
    return head + "\n\n" + text + "\n", num


def seen_path(session_id):
    """이 세션에 넣은 인계서를 기억하는 파일. 세션 id가 없거나 캐시 폴더를 못 정하면 None(기억 안 함 — 매번 넣는다)."""
    base = runlog.cache_dir()
    if not base or not isinstance(session_id, str) or not session_id:
        return None
    return os.path.join(base, "injected", hashlib.sha1(session_id.encode("utf-8", "surrogatepass")).hexdigest()[:16] + ".json")


def compacted_since(transcript, offset):
    """넣은 뒤 이 세션이 압축됐나. 압축되면 넣은 인계서가 요약 속으로 사라지므로 다시 넣는다.
    세션 기록을 못 읽으면 False(같은 내용을 또 넣지 않는 쪽). 기록이 줄었거나 너무 많이 자랐으면 True(확인 못 함 — 넣는 쪽)."""
    try:
        size = os.path.getsize(transcript)
        if offset < 0 or size < offset or size - offset > SEEN_SCAN_MAX:  # 음수 offset은 깨진 기억 — 넣는다
            return True
        with open(transcript, "rb") as f:
            f.seek(offset)
            data = f.read()  # ponytail: 한 번에 읽는다(최대 SEEN_SCAN_MAX, 43MB 실측 30~112ms). 메모리가 문제면 겹치는 조각 읽기로
            return any(m in data for m in COMPACT_MARKS)
    except (OSError, TypeError, ValueError):
        return False


def read_seen(data):
    """(기억 파일 경로 또는 None, 기억 dict). 못 읽거나 깨졌으면 빈 dict — 넣는 쪽."""
    p = seen_path(data.get("session_id"))
    if not p:
        return None, {}
    try:
        with open(p, encoding="utf-8") as f:
            seen = json.load(f)
        return p, seen if isinstance(seen, dict) else {}
    except Exception:
        return p, {}


def already_injected(data, sha):
    p, seen = read_seen(data)
    if not p or "sha" not in seen:
        return False
    try:
        return seen.get("sha") == sha and not compacted_since(data.get("transcript_path"), int(seen.get("offset", 0)))
    except Exception:
        return False  # 기억을 못 읽으면 넣는다 — 예전 동작


def index_injected(data):
    """이 세션에 개념 색인을 이미 넣었나(그 뒤 압축되지 않았나). 기억이 없거나 깨졌으면 False — 넣는다."""
    p, seen = read_seen(data)
    if not p or "index_offset" not in seen:
        return False
    try:
        return not compacted_since(data.get("transcript_path"), int(seen["index_offset"]))
    except Exception:
        return False


def memory_writable(data):
    """이 세션의 기억 파일을 쓸 수 있나. 세션 id가 없거나 캐시 폴더를 만들거나 쓸 수 없으면 False."""
    p = seen_path(data.get("session_id"))
    if not p:
        return False
    try:
        d = os.path.dirname(p)
        os.makedirs(d, mode=0o700, exist_ok=True)
        return os.access(d, os.W_OK) and (not os.path.exists(p) or os.access(p, os.W_OK))
    except OSError:
        return False


def remember_injected(data, sha=None, index=False):
    """넣은 인계서의 해시와 그때의 세션 기록 크기(offset), 색인을 넣었으면 그때의 크기(index_offset)를 남긴다.
    한 파일에 둘을 같이 두고 안 넣은 쪽 기억은 그대로 둔다. 실패는 조용히 넘긴다(다음에 또 넣을 뿐)."""
    p, seen = read_seen(data)
    if not p:
        return
    try:
        try:
            offset = os.path.getsize(data.get("transcript_path"))
        except (OSError, TypeError):
            offset = 0
        if sha is not None:
            seen.update(sha=sha, offset=offset)
        if index:
            seen["index_offset"] = offset
        d = os.path.dirname(p)
        os.makedirs(d, mode=0o700, exist_ok=True)
        cut = time.time() - SEEN_KEEP_DAYS * 86400
        for e in os.scandir(d):  # 끝난 세션의 기억은 며칠 뒤 지운다. 주입할 때만 돌아 비용이 작다
            try:
                if e.stat().st_mtime < cut:
                    os.remove(e.path)
            except OSError:
                pass
        tmp = f"{p}.{os.getpid()}.tmp"
        with os.fdopen(os.open(tmp, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
            json.dump(seen, f)
        os.replace(tmp, p)
    except Exception:
        pass


def inject_handoff(repo, prompt, data, machine=False, hook_deadline=None, reserve=0):
    """(넣을 텍스트, 넣은 것 dict, 건너뛴 이유). 조건이 안 맞으면 ("", None, None).
    넣을 조건인데 건너뛰면 이유를 남긴다: machine(사람이 친 프롬프트가 아님) · already(이 세션에 같은 내용을 이미 넣음).
    reserve는 같은 출력에 뒤따를 개념 색인 몫 — 본문 예산을 그만큼 줄이되 HANDOFF_KEEP 밑으로는 줄이지 않는다.
    reserve 때문에 더 잘렸으면 넣은 것 dict의 "unreserved"에 예산을 덜지 않은 판 (텍스트, 줄 수)를 둔다 — 색인이 결국 빠지면 그것으로 되돌린다."""
    if off("BATON_HANDOFF_INJECT", repo):
        return "", None, None
    if not rules.trigger_words(repo, prompt):
        return "", None, None
    path = os.path.join(repo, "HANDOFF.md")
    if not os.path.isfile(path):
        return "", None, None
    if machine:
        return "", None, "machine"
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    sha = hashlib.sha1(text.encode("utf-8", "surrogatepass")).hexdigest()[:16]
    if already_injected(data, sha):
        return "", None, "already"
    lines = text.splitlines()
    lang = i18n.lang(repo)
    deadline = None if hook_deadline is None else min(time.monotonic() + rules.GIT_BUDGET, hook_deadline)
    fresh = rules.safe_freshness(repo, text, deadline, lang)
    head = (HEAD if lang == "ko" else HEAD_EN) + "\n" + rules.freshness_line(fresh, lang)
    try:
        must = handoff_check.must_read_line(text, lang)
    except Exception:
        must = ""  # 필독 줄이 깨져도 인계서는 그대로 넣는다
    if must:
        head += "\n" + must
    full = LIMIT_CHARS - len(head) - TAIL_RESERVE  # 신선도 한 줄을 먼저 만들고 실제 길이를 뺀다

    def cut(budget):
        keep, used = 0, 0
        for ln in lines[:LIMIT]:
            if used + len(ln) + 1 > budget: break
            keep += 1; used += len(ln) + 1
        out = head + "\n\n" + "\n".join(lines[:keep]) + "\n"
        if keep < len(lines) and lang == "ko":
            out += (f"\n[baton] 인계서가 {len(lines)}줄이라 {keep}줄까지만 넣었다(상한 {LIMIT}줄·{LIMIT_CHARS}자). "
                    f"나머지는 HANDOFF.md {keep + 1}줄부터 — 필요하면 그 부분만 읽는다. 인계서는 짧게 유지한다.\n")
        elif keep < len(lines):
            out += (f"\n[baton] HANDOFF.md has {len(lines)} lines; only the first {keep} went in (limit {LIMIT} lines, "
                    f"{LIMIT_CHARS:,} chars). The rest starts at line {keep + 1}: read only that part if you need it. "
                    f"Keep the handoff short.\n")
        return out, keep

    out, keep = cut(max(min(full, HANDOFF_KEEP), full - reserve))
    h = {"lines": keep, "total": len(lines), "sha": sha, "days": fresh["days"], "commits_after": fresh["commits_after"]}
    if reserve:
        whole = cut(full)
        if whole[1] != keep:
            h["unreserved"] = whole
    return out, h, None


def concept_index(repo, data, machine):
    """(CONCEPTS.md 본문, 상대 경로, 건너뛴 이유). 넣을 조건이면 이유 None. 이유: off · no_map · machine · already · no_memory."""
    if off("BATON_CONCEPT_INDEX", repo):
        return "", "", "off"
    path, rel = rules.concept_path(repo)
    if not path:
        return "", "", "no_map"
    if machine:
        return "", "", "machine"
    if index_injected(data):
        return "", "", "already"
    if not memory_writable(data):
        return "", "", "no_memory"
    return concepts.read_text(path), rel, None


def observe(repo, prompt, data, handoff, concept, skip=None, index_chars=None, index_skip=None):
    h = handoff or {}
    try:
        runlog.append({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": "prompt", "session_id": data.get("session_id"),
            "repo": repo, "prompt_sha1": hashlib.sha1(prompt.encode("utf-8", "surrogatepass")).hexdigest()[:12],
            "prompt_chars": len(prompt), "decision": rules.decide(repo, prompt),
            "acted": {"handoff_lines": h.get("lines", 0), "handoff_total": h.get("total"),
                      "handoff_days": h.get("days"), "handoff_commits_after": h.get("commits_after"),
                      "handoff_skip": skip, "concept": concept,
                      "concept_index": index_chars, "concept_index_skip": index_skip},
        })
    except Exception:
        pass  # 관찰이 실패해도 주입과 프롬프트는 그대로 간다


def main():
    t0 = time.monotonic()
    data = read_input()
    prompt = data.get("prompt", "")
    if not isinstance(prompt, str) or not prompt:
        return
    repo = rules.repo_root()  # HEAD와 같이 프로세스 cwd 기준(Claude Code는 CLAUDE_PROJECT_DIR, Codex는 세션 cwd에서 훅을 돌린다)
    # 다른 세션·작업 알림이 보낸 메시지에는 인계서도 개념도 넣지 않는다 — 사람이 부른 것이 아니다
    machine = rules.machine_prompt(prompt)
    # 개념 색인 몫을 먼저 잡는다 — 무엇이 터져도 색인만 빠지고 인계서는 그대로 간다
    itext, iskip = "", None
    try:
        mtext, rel, iskip = concept_index(repo, data, machine)
        if iskip is None:
            ilang = i18n.lang(repo)
            itext = concepts.index(mtext, concepts.INDEX_LIMIT_CHARS, rel, lang=ilang)
            iskip = None if itext else "empty"
    except Exception:
        mtext, itext, iskip = "", "", "error"
    htext, handoff, skip = inject_handoff(repo, prompt, data, machine, t0 + HOOK_DEADLINE,
                                          len(itext) + 1 if itext else 0)
    unreserved = handoff.pop("unreserved", None) if handoff else None
    ctext, concept = ("", None) if machine else inject_concept(repo, prompt)
    if itext:
        try:  # 인계서·개념 절 뒤에 남은 자리만 쓴다. 안 맞으면 색인을 줄이고, 그래도 안 되면 뺀다
            sep = 1 if htext else 0
            room = LIMIT_CHARS - len(htext) - len(ctext) - sep - (1 if ctext else 0)
            if len(itext) > room:
                itext = concepts.index(mtext, room, rel, lang=i18n.lang(repo)) if room > 0 else ""
                iskip = None if itext else "budget"
        except Exception:
            itext, iskip = "", "error"
    if unreserved and not itext:  # 색인이 빠졌다 — 색인 몫 때문에 더 자른 인계서를 되돌린다
        htext, handoff["lines"] = unreserved
    if htext or itext or ctext:
        # 일반 stdout은 Claude Code만 맥락에 넣는다. Codex는 additionalContext만 받는다(10-01 실제 Codex 세션 확인) — 둘 다 받는 JSON으로 낸다
        ctx = "\n".join(x for x in (htext, itext, ctext) if x)
        out = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ctx}}
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
        sys.stdout.flush()
    observe(repo, prompt, data, handoff, concept, skip, len(itext) if itext else None, iskip)
    if handoff or itext:
        # 맨 끝에 기억한다 — 출력 뒤에 훅이 죽으면 출력이 버려질 수 있다. 그때 기억이 없어야 다음에 다시 넣는다
        remember_injected(data, handoff["sha"] if handoff else None, bool(itext))


if __name__ == "__main__":
    main()
