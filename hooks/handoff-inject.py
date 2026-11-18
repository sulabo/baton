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
# 한 세션에 같은 인계서는 한 번만 넣는다 — 파일이 바뀌었거나 그 뒤 세션이 압축됐을 때만 다시 넣는다. 사람이 친 프롬프트가 아닌 것
# (다른 세션의 <agent-message>, <task-notification>)에는 넣지 않는다. 11-18 실사용 로그: 주입 263번 중 226번이 같은 세션의 재주입,
# 세션 기록과 대조하니 최소 152번은 다른 세션 메시지가 계기였다(한 세션에 41번, 매번 8~9천 자).
# 끄기: BATON_HANDOFF_INJECT=off. 이 스위치들과 추가 트리거 말은 환경변수 또는 설정 파일에서 읽는다(lib/config.py, /baton-setup).
# 실험: BATON_CONCEPT_INJECT=on 이면 프롬프트가 개념 제목을 가리킬 때 CONCEPTS.md의 해당 절만 넣는다.
#
# 관찰(북극성 길 단계 1): 프롬프트마다 규칙 판단(lib/rules.py)과 실제로 넣은 것을 판단 로그에 한 줄 남긴다.
# 행동은 판단 때문에 바뀌지 않는다. 로그 위치는 BATON_LOG(기본 ~/.cache/baton/runs.jsonl) — 저장소마다 .baton/을 만들지 않으려고
# 사용자 캐시 한 곳에 저장소 이름을 붙여 쓴다(정본 43절은 .baton/runs.jsonl). 끄기: BATON_OBSERVE=off. 로그 실패는 조용히 넘긴다.
import hashlib, json, os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import config, rules, runlog

LIMIT = 200
LIMIT_CHARS = 9000
CONCEPT_LIMIT_CHARS = 2000
TRIGGER = rules.TRIGGER
SEEN_SCAN_MAX = 64 * 1024 * 1024  # 넣은 뒤 세션 기록이 이보다 많이 자랐으면 읽지 않고 다시 넣는다(43MB 세션 기록 실측, 11-18)
SEEN_KEEP_DAYS = 7
# 세션 기록의 압축 경계 줄 — Claude Code `"subtype":"compact_boundary"`(11-18 실제 기록 27개 파일 84건),
# Codex `"type":"compacted"`(~/.codex/sessions 실제 기록 확인). 본문 속 같은 글자는 JSON 이스케이프(\")라 걸리지 않는다.
# ponytail: /rewind·다른 훅의 block으로 넣은 맥락이 빠져도 기록 크기는 그대로라 알아채지 못한다 — 다음 "이어서"에서 안 넣는다.
# 그때는 에이전트가 파일을 직접 읽는다(baton 전 동작). 넣은 줄(hook_additional_context)이 실제로 기록됐는지 보는 쪽으로 올릴 수 있다
COMPACT_MARKS = (b'"subtype":"compact_boundary"', b'"type":"compacted"')
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
    head = CONCEPT_HEAD.format(path=rel)
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
        if size < offset or size - offset > SEEN_SCAN_MAX:
            return True
        with open(transcript, "rb") as f:
            f.seek(offset)
            data = f.read()  # ponytail: 한 번에 읽는다(최대 SEEN_SCAN_MAX, 43MB 실측 30~112ms). 메모리가 문제면 겹치는 조각 읽기로
            return any(m in data for m in COMPACT_MARKS)
    except (OSError, TypeError, ValueError):
        return False


def already_injected(data, sha):
    p = seen_path(data.get("session_id"))
    if not p:
        return False
    try:
        with open(p, encoding="utf-8") as f:
            seen = json.load(f)
        return seen.get("sha") == sha and not compacted_since(data.get("transcript_path"), int(seen.get("offset", 0)))
    except Exception:
        return False  # 기억을 못 읽으면 넣는다 — 예전 동작


def remember_injected(data, sha):
    """넣은 내용의 해시와 그때의 세션 기록 크기를 남긴다. 실패는 조용히 넘긴다(다음에 또 넣을 뿐)."""
    p = seen_path(data.get("session_id"))
    if not p:
        return
    try:
        try:
            offset = os.path.getsize(data.get("transcript_path"))
        except (OSError, TypeError):
            offset = 0
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
            json.dump({"sha": sha, "offset": offset}, f)
        os.replace(tmp, p)
    except Exception:
        pass


def inject_handoff(repo, prompt, data, machine=False):
    """(넣을 텍스트, 넣은 것 dict, 건너뛴 이유). 조건이 안 맞으면 ("", None, None).
    넣을 조건인데 건너뛰면 이유를 남긴다: machine(사람이 친 프롬프트가 아님) · already(이 세션에 같은 내용을 이미 넣음)."""
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
    budget = LIMIT_CHARS - len(HEAD) - 200  # 머리말·꼬리 안내 몫
    keep, used = 0, 0
    for ln in lines[:LIMIT]:
        if used + len(ln) + 1 > budget: break
        keep += 1; used += len(ln) + 1
    out = HEAD + "\n\n" + "\n".join(lines[:keep]) + "\n"
    if keep < len(lines):
        out += (f"\n[baton] 인계서가 {len(lines)}줄이라 {keep}줄까지만 넣었다(상한 {LIMIT}줄·{LIMIT_CHARS}자). "
                f"나머지는 HANDOFF.md {keep + 1}줄부터 — 필요하면 그 부분만 읽는다. 인계서는 짧게 유지한다.\n")
    return out, {"lines": keep, "total": len(lines), "sha": sha}, None


def observe(repo, prompt, data, handoff, concept, skip=None):
    h = handoff or {}
    try:
        runlog.append({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": "prompt", "session_id": data.get("session_id"),
            "repo": repo, "prompt_sha1": hashlib.sha1(prompt.encode("utf-8", "surrogatepass")).hexdigest()[:12],
            "prompt_chars": len(prompt), "decision": rules.decide(repo, prompt),
            "acted": {"handoff_lines": h.get("lines", 0), "handoff_total": h.get("total"),
                      "handoff_skip": skip, "concept": concept},
        })
    except Exception:
        pass  # 관찰이 실패해도 주입과 프롬프트는 그대로 간다


def main():
    data = read_input()
    prompt = data.get("prompt", "")
    if not isinstance(prompt, str) or not prompt:
        return
    repo = rules.repo_root()  # HEAD와 같이 프로세스 cwd 기준(Claude Code는 CLAUDE_PROJECT_DIR, Codex는 세션 cwd에서 훅을 돌린다)
    # 다른 세션·작업 알림이 보낸 메시지에는 인계서도 개념도 넣지 않는다 — 사람이 부른 것이 아니다
    machine = rules.machine_prompt(prompt)
    htext, handoff, skip = inject_handoff(repo, prompt, data, machine)
    ctext, concept = ("", None) if machine else inject_concept(repo, prompt)
    if htext or ctext:
        # 일반 stdout은 Claude Code만 맥락에 넣는다. Codex는 additionalContext만 받는다(10-01 실제 Codex 세션 확인) — 둘 다 받는 JSON으로 낸다
        out = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": htext + ctext}}
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
        sys.stdout.flush()
    observe(repo, prompt, data, handoff, concept, skip)
    if handoff:
        # 맨 끝에 기억한다 — 출력 뒤에 훅이 죽으면 출력이 버려질 수 있다. 그때 기억이 없어야 다음에 다시 넣는다
        remember_injected(data, handoff["sha"])


if __name__ == "__main__":
    main()
