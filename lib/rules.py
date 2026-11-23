#!/usr/bin/env python3
"""RulesProvider — 북극성 길 단계 1(V0 Observe + Explain). docs/NORTH_STAR.md 3절.

판단은 MATCHED(규칙 하나만 맞음) / AMBIGUOUS(둘 이상) / NO_MATCH(없음) 셋으로 낸다 — "confidence"라는 말을 쓰지 않는다(09-21 코덱스).
재료가 없어 판단 못 한 것은 따로 표시한다: NO_MAP(개념 지도 없음) · UNCONFIGURED(도메인을 사람이 아직 안 정함). 둘 다 0건이 아니라 못 셈.
이 모듈은 판단만 한다. 무엇을 실제로 넣을지는 훅이 정하고, 훅의 행동은 이 판단 때문에 바뀌지 않는다(observe).

  rules.py explain "<프롬프트>" [저장소 루트]   판단과 그 근거를 사람이 읽게 보여 준다
  rules.py explain - [저장소 루트] < 파일        프롬프트를 표준 입력으로(따옴표·$()·백틱이 든 프롬프트)
"""
import json, os, re, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import concepts, config, i18n

VERSION = "rules-v1"

# 인계·진행 상황을 가리키는 프롬프트. 훅이 인계서를 넣는 유일한 조건이다(루프 1·2).
# 사용자가 /baton-setup에서 고른 말(설정 BATON_HANDOFF_TRIGGERS_EXTRA)이 이것에 더해진다 — trigger_words.
# 영어는 구 단위로만 넣는다. "continue"·"progress"·"status" 같은 단어 하나는 붙여 넣은 지시문·로그에 흔해서
# 기존 관찰 로그로 재 보니 새로 걸린 것이 모두 오발동이었다(11-21, 복원한 프롬프트 905개 기준).
TRIGGER = re.compile(
    r"핸드오프|인계|이어서|이어가|어디까지|진행 상황|다음에 뭘|다음 할 일|handoff|hand-off"
    r"|\bwhere were we\b"
    r"|\bwhere (?:we|you|i|did we) (?:left|leave) off\b"
    r"|\bpick(?:s|ed|ing)? (?:it |this |things )?(?:back )?up where\b"
    r"|\bcatch me up\b"
    r"|\bhow far (?:did we get|have we (?:got|gotten)|along are we)\b"
    r"|\bfrom (?:the |our )?(?:last|previous) session\b",
    re.I)

# 사람이 친 프롬프트가 아닌 것 — 다른 세션·서브에이전트가 보낸 메시지, 백그라운드 작업 알림. 본문에 "handoff"·"인계"·"이어서"가
# 흔해 트리거에 걸리지만 사람이 인계서를 부른 것이 아니다. 11-18 runs.jsonl·세션 기록 대조: 주입 247번 중 최소 152번이 이것이었다.
# 훅이 받는 프롬프트는 `<agent-message from=…>`로 시작한다(세션 기록의 queue-operation·lastPrompt와 prompt_sha1 대조).
MACHINE = re.compile(r"\A\s*(?:Another Claude session sent a message:\s*)?<(?:agent-message|cross-session-message|task-notification)(?=[\s>/])")


def machine_prompt(prompt):
    return bool(MACHINE.match(prompt))

# 작업 종류 — BATON V0 전역 규칙 v0.1.0. 제품 내장·고정(프로젝트 데이터를 본 뒤 바꾸지 않는다, V0_SPEC).
TASK_TYPES = {
    "debugging":      ["고쳐", "안 돼", "안돼", "에러", "오류", "버그", "실패", "깨졌", "왜 안"],
    "implementation": ["만들어", "추가해", "구현", "넣어", "붙여", "생성"],
    "design":         ["설계", "구조", "아키텍처", "어떻게 할지", "방향"],
    "question":       ["뭐야", "뭔데", "왜", "어때", "설명해", "알려줘", "이해"],
    "refactor":       ["리팩", "정리해", "깔끔", "줄여", "단순"],
    "test":           ["테스트", "검증", "확인해", "돌려"],
    "documentation":  ["문서", "README", "적어", "기록", "정리본"],
}

# 개념 제목에서 빼는 일반어. 이것들로 맞으면 거의 모든 프롬프트에 걸린다.
GENERIC_WORDS = {
    "concepts", "concept", "md", "docs", "doc", "readme", "todo", "handoff",
    "개념", "문서", "결정", "코드", "구현", "동작", "실제", "상태", "확인",
    "파일", "테스트", "검증", "작업", "다음", "현재", "기준", "방식", "정리",
}

WORD = re.compile(r"[0-9A-Za-z가-힣]+")
# 후보 구절(phrases)에서 빼는 영어 기능어·인사말. 이것들로 후보를 내면 /baton-setup 트리거 제안에 "as"·"please"가 올라온다.
# 한국어는 GENERIC_WORDS만 본다(그대로). 개념 제목 매칭(title_words)에는 쓰지 않는다
EN_STOP = {
    "a", "an", "the", "and", "or", "but", "if", "then", "so", "as", "at", "by", "for", "from", "in", "into", "of", "on",
    "to", "with", "about", "is", "are", "was", "were", "be", "been", "am", "do", "does", "did", "have", "has", "had",
    "it", "its", "this", "that", "these", "those", "there", "here", "me", "my", "we", "us", "our", "you", "your",
    "they", "them", "their", "he", "she", "his", "her", "what", "which", "who", "how", "why", "when", "where",
    "can", "could", "would", "should", "will", "may", "might", "must", "not", "no", "yes", "ok", "okay", "please",
    "pls", "thanks", "thank", "just", "also", "now", "let", "lets", "hi", "hey", "up", "out", "all", "some", "any",
}


def phrases(prompt):
    """프롬프트 앞 20단어의 한 단어·두 단어 묶음. 흔한 말·한 글자·숫자는 뺀다."""
    # ponytail: 조사를 떼지 않는다('계속해'와 '계속'을 따로 센다). 앞 20단어만 본다(긴 프롬프트의 본문이 후보를 덮지 않게)
    # 두 단어 묶음은 원문에서 공백 하나로 붙어 있던 것만 — 그래야 그 묶음이 프롬프트에 부분 문자열로 실제로 있다
    # (훅·조립기는 부분 문자열로 맞춘다. 'a.b'·'a,\nb'에서 'a b'를 만들면 승격해도 안 걸린다)
    ms = list(WORD.finditer(prompt))[:20]
    ok = [m.group().lower() if len(m.group()) >= 2 and not m.group().isdigit() and m.group().lower() not in GENERIC_WORDS
          and m.group().lower() not in EN_STOP else None for m in ms]
    out = {w for w in ok if w}
    out |= {f"{ok[i]} {ok[i + 1]}" for i in range(len(ms) - 1)
            if ok[i] and ok[i + 1] and prompt[ms[i].end():ms[i + 1].start()] == " "}
    return out


def trigger_words(repo, prompt):
    """프롬프트에서 맞은 인계 트리거 말(중복 없이 정렬). 기본 TRIGGER + 설정의 추가 말(대소문자 무시 부분 문자열)."""
    p = prompt.casefold()
    extra = {w for w in config.terms("BATON_HANDOFF_TRIGGERS_EXTRA", repo) if w.casefold() in p}
    return sorted(set(TRIGGER.findall(prompt)) | extra)  # 반복은 한 번만 — 로그 한 줄이 커지지 않게


def state_of(hits):
    return "MATCHED" if len(hits) == 1 else "AMBIGUOUS" if hits else "NO_MATCH"


def classify_task_type(text):
    """(상태, 종류 또는 종류 목록 또는 None, 맞은 어휘). 부분 문자열 매칭 — V0의 알려진 한계("왜냐하면"→question)를 그대로 가진다."""
    hits = {t: [v for v in verbs if v in text] for t, verbs in TASK_TYPES.items()}
    hit_types = [t for t, v in hits.items() if v]
    if len(hit_types) == 1: return "MATCHED", hit_types[0], hits[hit_types[0]]
    if len(hit_types) > 1: return "AMBIGUOUS", hit_types, {t: hits[t] for t in hit_types}
    return "NO_MATCH", None, []


def title_words(title):
    title = title.split("—", 1)[0]
    return [w for w in re.findall(r"[0-9A-Za-z가-힣_]+", title.lower())
            if not w.isdigit() and len(w) >= 2 and w not in GENERIC_WORDS]


def concept_path(repo):
    for rel in ("CONCEPTS.md", os.path.join("docs", "CONCEPTS.md")):
        path = os.path.join(repo, rel)
        if os.path.isfile(path):
            return path, rel
    return "", ""


def concept_sections(repo):
    """[(번호, 이름, 본문 줄)] 또는 None(지도가 없거나 못 읽음)."""
    path, _ = concept_path(repo)
    if not path:
        return None
    try:
        return list(concepts.walk(concepts.read(path)))
    except Exception:
        return None


def concept_hits(sections, prompt):
    p = prompt.lower()
    return [(num, name) for num, name, _ in sections if any(w in p for w in title_words(name))]


def decide(repo, prompt):
    """프롬프트 하나에 대한 규칙 판단. 파일을 쓰지 않는다."""
    handoff_file = os.path.isfile(os.path.join(repo, "HANDOFF.md"))
    trig = trigger_words(repo, prompt)
    machine = machine_prompt(prompt)
    if machine:
        # 다른 세션·작업 알림이 보낸 메시지는 개념·작업 종류를 세지 않는다. 긴 서브에이전트 보고가 2글자 제목 단어를
        # 거의 다 덮어 후보가 수십 개씩 찍혔다(11-21 로그: 후보 10개 이상 228건 중 211건). 0이 아니라 "안 셈"이다
        cstate, hits, tstate, tvalue, thits = "MACHINE", [], "MACHINE", None, []
    else:
        sections = concept_sections(repo)
        hits = concept_hits(sections, prompt) if sections is not None else []
        cstate = "NO_MAP" if sections is None else state_of(hits)
        tstate, tvalue, thits = classify_task_type(prompt)
    return {
        "provider": "rules", "version": VERSION, "machine": machine,
        "handoff": {"state": "MATCHED" if trig else "NO_MATCH", "words": trig, "file": handoff_file},
        "concepts": {"state": cstate,
                     "candidates": [{"num": n, "name": name.split("—")[0].strip()} for n, name in hits]},
        "task_type": {"state": tstate, "value": tvalue, "words": thits},
        "domain": {"state": "UNCONFIGURED"},  # 도메인은 사람이 configure에서 정한다(V0_SPEC). 아직 없음
    }


def index_line(repo, machine, lang="ko"):
    """explain의 개념 색인 한 줄 — 훅(hooks/handoff-inject.py concept_index)과 같은 순서: 끄기 → 지도 → 기계 프롬프트."""
    ko = lang == "ko"
    if config.get("BATON_CONCEPT_INDEX", repo).strip().lower() in ("off", "0", "false", "no"):
        return "개념 색인 넣지 않는다 — BATON_CONCEPT_INDEX=off" if ko else "concept index  not injected — BATON_CONCEPT_INDEX=off"
    path, rel = concept_path(repo)
    if not path:
        return ("개념 색인 넣지 않는다 — 개념 지도(CONCEPTS.md)가 없다" if ko
                else "concept index  not injected — there is no concept map (CONCEPTS.md)")
    if machine:
        return ("개념 색인 넣지 않는다 — 다른 세션·작업 알림이 보낸 메시지다" if ko
                else "concept index  not injected — the message came from another session or a task notification")
    try:
        text = concepts.index(concepts.read_text(path), concepts.INDEX_LIMIT_CHARS, rel)
    except Exception as e:
        return (f"개념 색인 못 만들었다({type(e).__name__}) — 훅은 색인 없이 간다" if ko
                else f"concept index  could not be built ({type(e).__name__}) — the hook goes on without it")
    if not text:
        return f"개념 색인 넣지 않는다 — {rel}에 넣을 개념이 없다" if ko else f"concept index  not injected — {rel} has no concepts to list"
    n = sum(1 for l in text.splitlines()[1:] if re.match(r"\d{1,2}\. ", l))
    if ko:
        return (f"개념 색인 넣는다 — {len(text):,}자·개념 {n}개, 세션의 첫 사람 프롬프트에 한 번(압축 뒤 다시). "
                f"이 세션에 이미 넣었으면 안 넣는다. 인계서와 같이 들어가 자리가 모자라면 줄인다")
    return (f"concept index  injected — {len(text):,} chars, {n} concept{'' if n == 1 else 's'}, once on the session's first human prompt "
            f"(again after compaction). Not injected if this session already has it. Shortened if there is not enough room "
            f"next to the handoff")


def explain(repo, prompt):
    d = decide(repo, prompt)
    h, c, t = d["handoff"], d["concepts"], d["task_type"]
    lang = i18n.lang(repo)
    tr = (lambda ko, en: ko) if lang == "ko" else (lambda ko, en: en)  # 한국어 문구는 그대로, 영어는 옆에
    words = ", ".join(h["words"])
    lines = [tr(f"[baton] 규칙 판단 ({d['version']}) — 저장소 {repo}", f"[baton] Rule verdict ({d['version']}) — repo {repo}"), ""]
    # 훅(hooks/handoff-inject.py inject_handoff)과 같은 순서로 본다: 끄기 → 트리거 → 파일 → 기계 프롬프트
    if h["state"] == "MATCHED" and config.get("BATON_HANDOFF_INJECT", repo).strip().lower() in ("off", "0", "false", "no"):
        lines.append(tr(f"인계서   MATCHED — 하지만 BATON_HANDOFF_INJECT=off라 넣지 않는다 (맞은 말: {words})",
                        f"handoff   MATCHED — but not injected because BATON_HANDOFF_INJECT=off (matched: {words})"))
    elif h["state"] == "MATCHED" and not h["file"]:
        lines.append(tr(f"인계서   MATCHED — 하지만 HANDOFF.md가 없어 못 넣는다 (맞은 말: {words})",
                        f"handoff   MATCHED — but there is no HANDOFF.md to inject (matched: {words})"))
    elif h["state"] == "MATCHED" and d["machine"]:
        lines.append(tr(f"인계서   MATCHED — 하지만 사람이 아니라 다른 세션·작업 알림이 보낸 메시지라 넣지 않는다 (맞은 말: {words})",
                        f"handoff   MATCHED — but not injected: the message came from another session or a task notification, "
                        f"not a person (matched: {words})"))
    elif h["state"] == "MATCHED":
        lines.append(tr(f"인계서   MATCHED — 넣는다 (맞은 말: {words})", f"handoff   MATCHED — injected (matched: {words})"))
        try:  # 넣을 때만 신선도를 센다(git 최대 GIT_BUDGET초) — 훅도 같다
            with open(os.path.join(repo, "HANDOFF.md"), encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            lines.append(tr("         ", "          ")
                         + freshness_line(safe_freshness(repo, text, lang=lang), lang).replace("[baton] ", "", 1))
        except OSError:
            pass
    else:
        lines.append(tr("인계서   NO_MATCH — 넣지 않는다", "handoff   NO_MATCH — not injected"))
    if c["state"] == "MACHINE":
        lines.append(tr("개념     MACHINE — 다른 세션·작업 알림이 보낸 메시지라 후보를 세지 않았다",
                        "concepts  MACHINE — sent by another session or a task notification, so candidates were not counted"))
    elif c["state"] == "NO_MAP":
        lines.append(tr("개념     지도 없음(CONCEPTS.md 없거나 못 읽음) — 후보를 못 셌다",
                        "concepts  no map (CONCEPTS.md missing or unreadable) — candidates could not be counted"))
    else:
        names = ", ".join(f"{x['num']}. {x['name']}" for x in c["candidates"]) or tr("없음", "none")
        lines.append(tr(f"개념     {c['state']} — 후보: {names}", f"concepts  {c['state']} — candidates: {names}"))
        lines.append(tr("         (관찰만 한다. 개념 절 주입은 BATON_CONCEPT_INJECT=on이고 후보가 정확히 하나이며 그 절이 2,000자 이하일 때만)",
                        "          (observed only. A concept section goes in only when BATON_CONCEPT_INJECT=on, there is exactly "
                        "one candidate, and the section is 2,000 chars or less)"))
    lines.append(index_line(repo, d["machine"], lang))
    if t["state"] == "MACHINE":  # "없음"이면 0건으로 읽힌다 — 센 적이 없다
        lines.append(tr("작업 종류 MACHINE — 다른 세션·작업 알림이 보낸 메시지라 세지 않았다",
                        "task type MACHINE — sent by another session or a task notification, so not counted"))
    else:
        tv = t["value"] if isinstance(t["value"], str) else ", ".join(t["value"] or []) or tr("없음", "none")
        lines.append(tr(f"작업 종류 {t['state']} — {tv}", f"task type {t['state']} — {tv}"))
    lines.append(tr("도메인   UNCONFIGURED — 사람이 아직 정하지 않았다(못 셈)", "domain    UNCONFIGURED — not set by a person yet (not counted)"))
    lines.append(tr("맥락 조립: lib/compiler.py explain으로 따로 본다 — 아직 훅에 안 붙어 넣지도 로그에 남기지도 않는다",
                    "context assembly: see lib/compiler.py explain — not wired into the hook yet, so nothing is injected or logged"))
    lines.append("")
    lines.append(tr("판단 경로: rules (Jev 없음 — 길 단계 4 전)", "verdict path: rules (no Jev yet — before roadmap step 4)"))
    return "\n".join(lines)


# 인계서는 작성 시점의 가설이다 — 주입하는 순간 "언제 쓴 것인지, 그 뒤 무엇이 바뀌었는지"를 사실로 붙인다.
# 2026-11-08: 낡은 백업 폴더에서 38일 된 인계서가 "그대로 이어서 진행한다"와 함께 두 번 주입됐다.
# 작성일은 첫 3줄에서 찾는다. "작성: 날짜"·"작성일: 날짜"·"written: 날짜"를 먼저, 없으면 그 3줄의 아무 YYYY-MM-DD.
# 표기를 넓게 받는다 — 템플릿은 `작성: YYYY-MM-DD`지만 손으로 쓴 인계서의 다른 표기도 날짜로 읽는다(좁으면 마지막 커밋일로 밀려난다).
WRITTEN = re.compile(r"(?i)(?:작성일?|written|date)\s*[:：]?\s*(\d{4}-\d{2}-\d{2})|(\d{4}-\d{2}-\d{2})")
STALE_DAYS = 7  # ponytail: 근거 없는 기본값. 인계서 나이 분포(관찰 로그 handoff_days)를 보고 조정
# 신선도 git 호출 전체 시한(초). 훅은 여기에 훅 전체 시한(시작 + 8.5초, hooks/handoff-inject.py HOOK_DEADLINE)을 겹쳐
# deadline으로 넘긴다 — 신선도는 그보다 늦게 끝나지 않는다. 그 앞의 repo_root(Codex만)·config.repo_key(설정에 저장소 절이
# 있을 때)는 git 시한이 각 5초라, git이 멈추면 그 둘만으로 훅 시한 10초에 닿을 수 있다(이 기능 전부터, PR #16 기준 10.1초 실측)
GIT_BUDGET = 3.0
FRESHNESS_MAX = 500  # 신선도 한 줄의 상한(자). 함께 나올 수 없는 까닭까지 전부 붙인 과대 추정이 448자다(hooks/test_handoff_inject.py HookOutputBudgetTest) — 실제 줄은 자르지 않는다
# 영어 줄의 상한. 영어 머리말(hooks/handoff-inject.py HEAD_EN)이 더 길어 같은 9,600자 예산 안에 검사기 상한 8,700자를 지키려면 이만큼만 남는다.
# 실제로 함께 나올 수 있는 까닭은 둘까지(잘못된 첫 줄 날짜 + git 쪽 하나)라 가장 긴 실제 줄도 이 안에 든다(HookOutputBudgetTest)
FRESHNESS_MAX_EN = 350

# 못 센 까닭(사람이 읽을 말) — (한국어, 영어). 한국어 문구는 그대로 둔다. NO_DATE는 첫 줄에 작성일이 없을 때 앞에 붙는다
NO_DATE = ("첫 줄에 작성일이 없고 ", "no date in the first lines, and ")
WHY = {
    "bad_date":    ("첫 줄 날짜({})가 잘못됐다", "the date in the first lines ({}) is invalid"),
    "deadline":    ("그 뒤 커밋 수를 못 셌다(훅 시한)", "could not count the commits since then (hook time limit)"),
    "shallow":     ("얕은 복제라 그 뒤 커밋 수를 못 셌다", "shallow clone, so could not count the commits since then"),
    "count":       ("그 뒤 커밋 수를 못 셌다(git 시한 초과 또는 오류)", "could not count the commits since then (git timed out or failed)"),
    "uncommitted": ("HANDOFF.md가 커밋된 적 없어 그 뒤 커밋 수를 못 셌다",
                    "HANDOFF.md was never committed, so could not count the commits since then"),
    "no_git":      ("그 뒤 커밋 수를 못 셌다(git 저장소가 아니거나 시한 초과·오류)",
                    "could not count the commits since then (not a git repo, or git timed out or failed)"),
    "never":       ("HANDOFF.md가 커밋된 적 없다", "HANDOFF.md was never committed"),
    "no_log":      ("git 기록도 못 읽었다", "could not read the git history either"),
    "crash":       ("신선도 계산 실패({})", "freshness check failed ({})"),
}


def unknown_reason(key, lang, *args, no_date=False):
    """못 센 까닭 한 줄. lang이 ko가 아니면 영어."""
    i = 0 if lang == "ko" else 1
    return (NO_DATE[i] if no_date else "") + WHY[key][i].format(*args)


def header_date(text):
    """첫 3줄의 작성일 문자열 또는 None. 이름표가 붙은 날짜를 먼저 고른다."""
    ms = list(WRITTEN.finditer("\n".join(text.splitlines()[:3])))
    labeled = [m.group(1) for m in ms if m.group(1)]
    return (labeled or [m.group(2) for m in ms])[0] if ms else None


def _git(repo, deadline, *args):
    """git 출력(앞뒤 공백 제거) 또는 None. 훅에서 부르므로 남은 시한 안에서만, 실패는 조용히.
    서명 표시(log.showSignature)는 stdout에 섞이고, status는 index.lock을 잡을 수 있어 둘 다 끈다."""
    import time
    left = deadline - time.monotonic()
    if left <= 0.05:
        return None
    try:
        r = subprocess.run(["git", "--no-optional-locks", "-c", "log.showSignature=false", "-C", repo, *args],
                           capture_output=True, text=True, timeout=min(left, 1.5))
    except Exception:
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def handoff_freshness(repo, text, today=None, deadline=None, lang=None):
    """인계서가 얼마나 오래됐나. {"written", "source", "days", "commits_after", "dirty", "unknown"} — 못 센 값은 None.
    written은 첫 3줄의 작성일(header_date), 없거나 잘못된 날짜면 HANDOFF.md를 마지막으로 커밋한 날(source="commit",
    author 날짜 — rebase로 바뀌지 않게). commits_after는 그 커밋 뒤 이 폴더(-- .)를 건드린 커밋 수 — 인계서가 모르는 변경.
    커밋 안 한 수정 중(dirty)이거나 얕은 복제(shallow — 경계 커밋이 HANDOFF.md를 만든 것처럼 보인다)면 세지 않는다.
    unknown은 못 센 까닭(사람이 읽을 말, lang 언어 — 없으면 이 저장소의 언어) 목록. deadline(time.monotonic 기준)이 없으면 지금부터 GIT_BUDGET초."""
    import datetime, time
    lang = lang or i18n.lang(repo)
    today = today or datetime.date.today()
    deadline = time.monotonic() + GIT_BUDGET if deadline is None else deadline
    out = {"written": None, "source": None, "days": None, "commits_after": None, "dirty": None, "unknown": []}

    def valid(day):
        try:
            return datetime.date.fromisoformat(day)
        except (TypeError, ValueError):
            return None

    head = header_date(text)
    if head and valid(head):
        out["written"], out["source"] = head, "header"
    elif head:
        out["unknown"].append(unknown_reason("bad_date", lang, head))
    if deadline - time.monotonic() <= 0.05:  # 훅 시한이 이미 다 됐다 — git을 하나도 부르지 않는다(_git과 같은 문턱)
        out["unknown"].append(unknown_reason("deadline", lang, no_date=not head))
        if out["written"]:
            out["days"] = (today - valid(out["written"])).days
        return out
    last = _git(repo, deadline, "log", "-1", "--format=%H %as", "--", "HANDOFF.md")
    parts = last.split() if last else []
    if len(parts) == 2 and valid(parts[1]):
        sha, day = parts
        if not out["written"]:
            out["written"], out["source"] = day, "commit"
        status = _git(repo, deadline, "status", "--porcelain", "--", "HANDOFF.md")
        out["dirty"] = bool(status) if status is not None else None
        shallow = _git(repo, deadline, "rev-parse", "--is-shallow-repository")
        if out["dirty"] is False and shallow == "false":
            n = _git(repo, deadline, "rev-list", "--count", f"{sha}..HEAD", "--", ".")
            out["commits_after"] = int(n) if n and n.isdigit() else None
        if shallow == "true":
            out["unknown"].append(unknown_reason("shallow", lang))
        elif out["commits_after"] is None and out["dirty"] is not True:
            out["unknown"].append(unknown_reason("count", lang))
    elif out["written"]:
        # 작성일은 있지만 커밋 수는 못 셌다 — 조용히 빼면 "그 뒤 커밋 없음"으로 읽힌다. 시한이 다 됐을 수 있어 git을 더 부르지 않는다
        out["unknown"].append(unknown_reason("uncommitted" if last == "" else "no_git", lang))
    else:
        # log가 비었거나(미추적) 실패했다(커밋이 하나도 없는 저장소도 실패한다) — git 저장소인지로 둘을 가른다
        inside = last == "" or _git(repo, deadline, "rev-parse", "--is-inside-work-tree") == "true"
        # 잘못된 날짜는 앞에서 이미 말했다 — "없다"와 겹쳐 모순되지 않게
        out["unknown"].append(unknown_reason("never" if inside else "no_log", lang, no_date=not head))
    if out["written"]:
        out["days"] = (today - valid(out["written"])).days
    return out


def freshness_line(f, lang=None):
    """주입 머리말 바로 뒤에 붙일 한 줄. 아무것도 못 셌으면 그 까닭을 말한다(빈 줄로 두면 '신선함'으로 읽힌다).
    상한(한국어 FRESHNESS_MAX, 영어 FRESHNESS_MAX_EN)을 넘지 않는다 — 훅이 이 길이만큼 인계서 본문 예산을 덜 쓰므로 길이에 상한이 있어야 한다.
    lang이 없으면 i18n.lang()(저장소 절 없이)."""
    if (lang or i18n.lang()) != "ko":
        return freshness_line_en(f)
    why = " · ".join(f.get("unknown") or [])
    if not f["written"]:
        line = f"[baton] 인계서 작성일을 못 셌다({why or '까닭 모름'}) — 다음 행동이 기대는 사실을 먼저 확인한다."
    else:
        when = "첫 줄 작성일" if f["source"] == "header" else "마지막 커밋일"
        days = f["days"]
        age = "오늘" if days == 0 else f"{days}일 전" if days > 0 else f"{-days}일 뒤 — 날짜 확인 필요"
        parts = [f"[baton] 이 인계서는 {f['written']}({age}, {when}) 기준이다."]
        if f["dirty"]:
            parts.append("커밋 안 한 수정 중이다.")
        elif f["commits_after"]:
            n = f["commits_after"]
            parts.append(f"그 뒤 커밋 {n}개는 인계서에 없다 — `git log --oneline -{min(n, 20)} -- .`부터 본다.")
        elif f["commits_after"] == 0:
            parts.append("그 뒤 커밋은 없다.")
        if why:
            parts.append(why + ".")
        if days >= STALE_DAYS:
            parts.append(f"{days}일 지났다 — 다음 행동이 아직 유효한지부터 확인한다.")
        line = " ".join(parts)
    return line if len(line) <= FRESHNESS_MAX else line[:FRESHNESS_MAX - 1] + "…"


def freshness_line_en(f):
    """freshness_line의 영어판(docs/GUIDE.md의 예시와 같은 문장). 상한은 FRESHNESS_MAX_EN."""
    def plural(n, word):
        return f"{n} {word}" + ("" if n == 1 else "s")

    why = " · ".join(f.get("unknown") or [])
    if not f["written"]:
        line = (f"[baton] Could not tell when this handoff was written ({why or 'reason unknown'}) — "
                f"first check the facts the next step depends on.")
    else:
        when = "date in its first line" if f["source"] == "header" else "date of its last commit"
        days = f["days"]
        age = ("today" if days == 0 else plural(days, "day") + " ago" if days > 0
               else plural(-days, "day") + " in the future — check the date")
        parts = [f"[baton] This handoff is as of {f['written']} ({age}, {when})."]
        if f["dirty"]:
            parts.append("It has uncommitted edits.")
        elif f["commits_after"]:
            n = f["commits_after"]
            parts.append(f"{plural(n, 'commit')} since then {'is' if n == 1 else 'are'} not in it — "
                         f"start with `git log --oneline -{min(n, 20)} -- .`.")
        elif f["commits_after"] == 0:
            parts.append("No commits since then.")
        if why:
            parts.append(why[:1].upper() + why[1:] + ".")
        if days >= STALE_DAYS:
            parts.append(f"{plural(days, 'day')} have passed — first check that the next step still holds.")
        line = " ".join(parts)
    return line if len(line) <= FRESHNESS_MAX_EN else line[:FRESHNESS_MAX_EN - 1] + "…"


def safe_freshness(repo, text, deadline=None, lang=None):
    """훅·explain용. 무엇이 터져도 '못 셌다'로 떨어진다 — 신선도 한 줄 때문에 인계서 주입이 사라지면 안 된다(fail-open)."""
    try:
        return handoff_freshness(repo, text, deadline=deadline, lang=lang)
    except Exception as e:
        try:
            reason = unknown_reason("crash", lang or i18n.lang(repo), type(e).__name__)
        except Exception:
            reason = f"신선도 계산 실패({type(e).__name__})"
        return {"written": None, "source": None, "days": None, "commits_after": None, "dirty": None,
                "unknown": [reason]}


def repo_root(start=None):
    d = os.environ.get("CLAUDE_PROJECT_DIR")
    if d: return d
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, cwd=start, timeout=5)
        top = r.stdout.strip()
    except Exception:  # git이 없거나 멈춤 — 조용히 폴더 기준으로 (훅은 fail-open)
        top = ""
    return top or start or os.getcwd()


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] != "explain":
        sys.exit(__doc__)
    prompt = sys.stdin.read() if sys.argv[2] == "-" else sys.argv[2]
    print(explain(sys.argv[3] if len(sys.argv) > 3 else repo_root(), prompt.rstrip("\n")))
