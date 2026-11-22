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
import concepts, config

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


def explain(repo, prompt):
    d = decide(repo, prompt)
    h, c, t = d["handoff"], d["concepts"], d["task_type"]
    lines = [f"[baton] 규칙 판단 ({d['version']}) — 저장소 {repo}", ""]
    # 훅(hooks/handoff-inject.py inject_handoff)과 같은 순서로 본다: 끄기 → 트리거 → 파일 → 기계 프롬프트
    if h["state"] == "MATCHED" and config.get("BATON_HANDOFF_INJECT", repo).strip().lower() in ("off", "0", "false", "no"):
        lines.append(f"인계서   MATCHED — 하지만 BATON_HANDOFF_INJECT=off라 넣지 않는다 (맞은 말: {', '.join(h['words'])})")
    elif h["state"] == "MATCHED" and not h["file"]:
        lines.append(f"인계서   MATCHED — 하지만 HANDOFF.md가 없어 못 넣는다 (맞은 말: {', '.join(h['words'])})")
    elif h["state"] == "MATCHED" and d["machine"]:
        lines.append(f"인계서   MATCHED — 하지만 사람이 아니라 다른 세션·작업 알림이 보낸 메시지라 넣지 않는다 (맞은 말: {', '.join(h['words'])})")
    elif h["state"] == "MATCHED":
        lines.append(f"인계서   MATCHED — 넣는다 (맞은 말: {', '.join(h['words'])})")
    else:
        lines.append("인계서   NO_MATCH — 넣지 않는다")
    if c["state"] == "MACHINE":
        lines.append("개념     MACHINE — 다른 세션·작업 알림이 보낸 메시지라 후보를 세지 않았다")
    elif c["state"] == "NO_MAP":
        lines.append("개념     지도 없음(CONCEPTS.md 없거나 못 읽음) — 후보를 못 셌다")
    else:
        names = ", ".join(f"{x['num']}. {x['name']}" for x in c["candidates"]) or "없음"
        lines.append(f"개념     {c['state']} — 후보: {names}")
        lines.append("         (관찰만 한다. 개념 절 주입은 BATON_CONCEPT_INJECT=on이고 후보가 정확히 하나이며 그 절이 2,000자 이하일 때만)")
    tv = t["value"] if isinstance(t["value"], str) else ", ".join(t["value"] or []) or "없음"
    lines.append(f"작업 종류 {t['state']} — {tv}")
    lines.append("도메인   UNCONFIGURED — 사람이 아직 정하지 않았다(못 셈)")
    lines.append("요약만/버릴 것: 아직 없음 — 컨텍스트 조립기는 길 단계 2")
    lines.append("")
    lines.append("판단 경로: rules (Jev 없음 — 길 단계 4 전)")
    return "\n".join(lines)


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
