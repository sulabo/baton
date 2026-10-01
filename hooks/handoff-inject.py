#!/usr/bin/env python3
# UserPromptSubmit 훅. 프롬프트가 인계나 진행 상황을 가리킬 때만 HANDOFF.md 전문을 컨텍스트로 넣는다.
#
# 왜 이 모양인가 (docs/research/LOOP_PLAN.md 루프 1, 게임 저장소 n=5):
#  - 상태 질문에 전문을 넣으면 입력 토큰 -45%, 턴 5→3. 인계서를 다시 여는 일이 5/5→0/5.
#  - 인계와 무관한 작업에 넣으면 +11%. 넣은 것이 매 턴 컨텍스트에 남기 때문이다.
#  - 세션 시작 훅은 프롬프트를 못 본다. 그래서 프롬프트 제출 시점에 가린다.
#
# 200줄·9,000자 중 먼저 닿는 곳까지만 넣는다. 줄 상한은 소유자 결정(09-22). 글자 상한은 실측(루프 2):
# 훅 출력이 8,995자일 때는 컨텍스트에 들어갔고 20,826자일 때는 Claude Code가 파일로 빼 두고
# 에이전트가 그 파일을 다시 cat했다 — 넣은 것이 아니라 가리킨 것이 됐다. 정확한 문턱은 확인 못 함.
# 넘치면 잘랐다는 것을 한 줄로 말한다 — 조용히 자르면 뒤쪽에 있는 다음 행동을 "없음"으로 읽는다.
# 끄기: BATON_HANDOFF_INJECT=off
# 실험: BATON_CONCEPT_INJECT=on 이면 프롬프트가 개념 제목을 가리킬 때 CONCEPTS.md의 해당 절만 넣는다.
#
# 관찰(북극성 길 단계 1): 프롬프트마다 규칙 판단(lib/rules.py)과 실제로 넣은 것을 판단 로그에 한 줄 남긴다.
# 행동은 판단 때문에 바뀌지 않는다. 로그 위치는 BATON_LOG(기본 ~/.cache/baton/runs.jsonl) — 저장소마다 .baton/을 만들지 않으려고
# 사용자 캐시 한 곳에 저장소 이름을 붙여 쓴다(정본 43절은 .baton/runs.jsonl). 끄기: BATON_OBSERVE=off. 로그 실패는 조용히 넘긴다.
import hashlib, json, os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import rules, runlog

LIMIT = 200
LIMIT_CHARS = 9000
CONCEPT_LIMIT_CHARS = 2000
TRIGGER = rules.TRIGGER
HEAD = ("[baton] 아래는 이 저장소 HANDOFF.md의 전문이다(프롬프트가 인계·진행 상황을 가리켜 자동 주입). "
        "파일을 다시 열 필요 없다. 그대로 이어서 진행한다.")
CONCEPT_HEAD = ("[baton] 아래는 이 저장소 {path}에서 프롬프트와 맞은 개념 한 절이다"
                "(실험 기능 BATON_CONCEPT_INJECT=on). 개념은 탐색 앵커다. 실제 동작은 필요한 경우 코드로 확인한다.")


def read_input():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def on(name):
    return os.environ.get(name, "").strip().lower() in ("on", "1", "true", "yes")


def off(name):
    return os.environ.get(name, "").strip().lower() in ("off", "0", "false", "no")


def concept_text(num, name, body):
    return "\n".join(["## %s. %s" % (num, name)] + body).rstrip() + "\n"


def inject_concept(repo, prompt):
    """넣을 텍스트와 개념 번호. 안 넣으면 ("", None)."""
    if not on("BATON_CONCEPT_INJECT"):
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
    head = CONCEPT_HEAD.format(path=rel)
    if len(text) + len(head) + 2 > CONCEPT_LIMIT_CHARS:
        return "", None
    return head + "\n\n" + text + "\n", num


def inject_handoff(repo, prompt):
    """넣을 텍스트와 (넣은 줄, 전체 줄). 안 넣으면 ("", None)."""
    if off("BATON_HANDOFF_INJECT"):
        return "", None
    if not TRIGGER.search(prompt):
        return "", None
    path = os.path.join(repo, "HANDOFF.md")
    if not os.path.isfile(path):
        return "", None
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    budget = LIMIT_CHARS - len(HEAD) - 200  # 머리말·꼬리 안내 몫
    keep, used = 0, 0
    for ln in lines[:LIMIT]:
        if used + len(ln) + 1 > budget: break
        keep += 1; used += len(ln) + 1
    out = HEAD + "\n\n" + "\n".join(lines[:keep]) + "\n"
    if keep < len(lines):
        out += (f"\n[baton] 인계서가 {len(lines)}줄이라 {keep}줄까지만 넣었다(상한 {LIMIT}줄·{LIMIT_CHARS}자). "
                f"나머지는 HANDOFF.md {keep + 1}줄부터 — 필요하면 그 부분만 읽는다. 인계서는 짧게 유지한다.\n")
    return out, (keep, len(lines))


def observe(repo, prompt, data, handoff, concept):
    try:
        runlog.append({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": "prompt", "session_id": data.get("session_id"),
            "repo": repo, "prompt_sha1": hashlib.sha1(prompt.encode("utf-8", "surrogatepass")).hexdigest()[:12],
            "prompt_chars": len(prompt), "decision": rules.decide(repo, prompt),
            "acted": {"handoff_lines": handoff[0] if handoff else 0, "handoff_total": handoff[1] if handoff else None,
                      "concept": concept},
        })
    except Exception:
        pass  # 관찰이 실패해도 주입과 프롬프트는 그대로 간다


def main():
    data = read_input()
    prompt = data.get("prompt", "")
    if not isinstance(prompt, str) or not prompt:
        return
    repo = rules.repo_root()  # HEAD와 같이 프로세스 cwd 기준(Claude Code는 CLAUDE_PROJECT_DIR, Codex는 세션 cwd에서 훅을 돌린다)
    htext, handoff = inject_handoff(repo, prompt)
    ctext, concept = inject_concept(repo, prompt)
    if htext or ctext:
        # 일반 stdout은 Claude Code만 맥락에 넣는다. Codex는 additionalContext만 받는다(10-01 실제 Codex 세션 확인) — 둘 다 받는 JSON으로 낸다
        out = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": htext + ctext}}
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
        sys.stdout.flush()
    observe(repo, prompt, data, handoff, concept)


if __name__ == "__main__":
    main()
