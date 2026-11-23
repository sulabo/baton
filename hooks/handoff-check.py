#!/usr/bin/env python3
# 북극성 길 단계 3 — 인계서 검사와 결정론 트리거. 이벤트 둘을 한 파일에서 받는다.
#
# PostToolUse(Write|Edit|MultiEdit): 고친 파일이 HANDOFF.md면 lib/handoff_check.py로 검사하고,
#   문제가 있으면 모델에게 돌려준다(decision: block — 쓰기는 이미 됐고, 이유를 보고 고치게 한다).
#   경고만 있으면(확인 표시 [V]·[?] 빠짐·필독 3개 초과·마지막 커밋판에 있던 줄이 빠짐) 막지 않고 additionalContext로 알리기만 한다.
#   빠진 줄은 git HEAD의 HANDOFF.md와 비교한다(lib/handoff_check.py drop_warnings). 미추적·이력 없음이면 아무 말도 안 한다.
#   출력은 OUT_MAX자에서 자른다(Claude Code 훅 출력 상한 10,000자 — 넘으면 파일로 빠진다, hooks/handoff-inject.py 머리 주석).
# Stop: 이 세션이 마지막으로 인계서(HANDOFF.md 또는 HANDOFF_*.md)를 쓴 뒤 다른 파일을 N개(기본 3) 이상 고쳤으면, 세션에 한 번
#   모델에게 지금 인계서를 쓰라고 한다(BATON_HANDOFF_AUTO, 기본 켬 — 소유자 결정 2026-11-23). Stop 훅이 decision "block"과
#   reason을 내면 Claude가 멈추지 않고 reason을 받아 이어서 일한다. https://code.claude.com/docs/en/hooks Stop(2026-11-23 확인):
#   "`"block"` prevents Claude from stopping" · "`reason` | Required when `decision` is `"block"`. Tells Claude why it should continue"
#   · "`stop_hook_active` field is `true` when Claude Code is already continuing as a result of a stop hook. Check this value ...
#   to avoid blocking on a condition that will never resolve." — 그래서 stop_hook_active가 참이면 막지 않는다(상태도 안 남긴다).
#   BATON_HANDOFF_AUTO=off면 예전처럼 사용자에게 한 번 제안만 한다(systemMessage, 쓰기는 사람이 정한다).
#   저장소 루트의 HANDOFF.md가 baton 형식이 아니면(handoff_check.looks_ours) 자동 쓰기 대신 제안만 한다 — 남의 형식 파일을
#   모델이 우리 템플릿으로 다시 쓰게 하지 않으려고(리뷰 11-23). HANDOFF.md가 없거나 baton 형식이면 자동 쓰기.
#   문턱 3은 로컬 세션 94개 실측(2026-10-01): 1~2개 고친 세션은 인계서를 16% 썼고 3개 이상은 67% 썼다.
#
# 끄기: BATON_HANDOFF_CHECK=off(검사) · BATON_HANDOFF_NUDGE=off(제안·자동 쓰기 둘 다) · BATON_HANDOFF_AUTO=off(자동 쓰기 대신 제안)
#   문턱: BATON_HANDOFF_NUDGE_FILES=3. 환경변수 또는 설정 파일(lib/config.py, /baton-setup이 사용자 세션 분포로 문턱을 제안해 쓴다)에서 읽는다.
# Codex의 편집 도구(apply_patch)는 file_path를 주지 않아 여기서 안 잡힌다 — 스킬이 쓴 뒤 검사기를 직접 부른다.
# Codex의 Stop도 제안·자동 쓰기가 나가지 않는다: 세션 기록(~/.codex/sessions)에 Claude Code 모양의 "tool_use" 편집 줄이 없어
#   edit_paths가 0개를 센다(11-23 실제 Codex 기록 확인: "type":"tool_use" 0줄, 편집은 custom_tool_call apply_patch).
import json, os, re, sys, time

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PLUGIN, "lib"))
import config, handoff_check, i18n, rules, runlog

LIST_MAX = 10  # 자동 쓰기 요청에 이름을 적는 파일 수. 나머지는 개수만
OUT_MAX = 9600  # 검사 결과(reason·additionalContext)의 상한 — 주입 훅과 같은 여유
# 저장 검사의 시한(훅 시작부터). 훅 시한은 10초(hooks.json)이고 죽은 훅은 아무것도 내지 않는다 — 그러면 비밀값 막기도 사라진다.
# 그래서 막아야 할 문제(check_file)를 먼저 다 만들고, 빠진 줄 검사는 이 시한까지 남은 시간(최대 handoff_check.DROP_BUDGET초)만 쓴다
HOOK_DEADLINE = 8.0

EDIT_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}  # 제안 문턱에 세는 편집. 검사 matcher에 NotebookEdit가 없는 것은 HANDOFF.md를 못 고쳐서다


def off(name, repo):
    return config.get(name, repo).strip().lower() in ("off", "0", "false", "no")


NAMED = re.compile(r"(?i)handoff[_-].+\.md")  # 이름 붙은 인계서(HANDOFF_트랙.md). 주입·검사는 HANDOFF.md만 한다


def is_handoff(path):
    """주입 훅이 읽고 검사기가 보는 인계서."""
    return isinstance(path, str) and os.path.basename(path) == "HANDOFF.md"


def wrote_handoff(path):
    """인계서를 쓴 편집 — HANDOFF.md와 이름 붙은 인계서 둘 다. 제안 문턱과 /baton-setup 분포는 이것으로 센다.
    HANDOFF.md만 세면 트랙마다 HANDOFF_*.md를 쓰는 사람은 인계서를 쓴 뒤에도 '안 썼다'로 잡힌다
    (11-21 로그: 제안을 무시한 것으로 보인 13번 중 5번은 제안 뒤에 이름 붙은 인계서를 썼다)."""
    return is_handoff(path) or (isinstance(path, str) and bool(NAMED.fullmatch(os.path.basename(path))))


def repo_of(start):
    """설정 파일의 저장소 절을 고를 루트. 설정이 없으면 git을 부르지 않는다(Codex 훅에는 CLAUDE_PROJECT_DIR가 없다)."""
    return rules.repo_root(start) if config.load() is not None else None


def on_edit(data):
    t0 = time.monotonic()
    ti = data.get("tool_input")
    path = ti.get("file_path") if isinstance(ti, dict) else None
    if not is_handoff(path):
        if wrote_handoff(path):  # 검사는 안 하지만 썼다는 것은 남긴다 — 제안 효과를 셀 때 빠지지 않게
            runlog.append({"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": "handoff_write",
                           "session_id": data.get("session_id"), "named": True})
        return
    if not os.path.isabs(path) and isinstance(data.get("cwd"), str):
        path = os.path.join(data["cwd"], path)
    repo = repo_of(os.path.dirname(path) or None)
    if off("BATON_HANDOFF_CHECK", repo):
        return
    lang = i18n.lang(repo)
    t = handoff_check.tr(lang)
    terms = config.terms("private_terms", repo) if repo else []  # 저장소는 한 번만 찾는다 — check_file·빠진 줄 검사에 넘긴다
    try:
        text = handoff_check.read(path)
        problems = handoff_check.check_file(path, strict=False, text=text, lang=lang, terms=terms)
    except OSError:
        return
    try:
        warned = handoff_check.warnings(text, strict=False, lang=lang)
    except Exception:
        warned = []  # 경고 규칙이 깨져도 막아야 할 문제는 그대로 돌려준다
    try:  # 남은 시간만 쓴다. 깨져도 나머지는 그대로
        deadline = min(time.monotonic() + handoff_check.DROP_BUDGET, t0 + HOOK_DEADLINE)
        if deadline - time.monotonic() > 0.2:
            warned += handoff_check.drop_warnings(path, text, lang, private_terms=terms, strict=False, deadline=deadline)
        elif handoff_check.looks_ours(text):  # 안 본 것을 "빠진 줄 없음"으로 읽지 않게
            warned.append(t("경고: 훅 시간이 모자라 빠진 줄 검사를 건너뛰었다 — 빠진 줄 0개가 아니라 안 봤다",
                            "warning: the dropped-lines check was skipped because the hook ran out of time — not zero "
                            "dropped lines, just not checked"))
    except Exception:
        pass
    runlog.append({"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": "handoff_check",
                   "session_id": data.get("session_id"), "problems": len(problems), "warnings": len(warned)})
    if problems:
        reason = (t("[baton] 방금 쓴 HANDOFF.md에 인계서 검사 문제가 있다. 고친 뒤 다시 저장한다:\n- ",
                    "[baton] The HANDOFF.md you just wrote has handoff-check problems. Fix them and save again:\n- ")
                  + "\n- ".join(problems + warned))
        print(json.dumps({"decision": "block", "reason": capped(reason, t)}, ensure_ascii=False))
    elif warned:  # 경고만이면 막지 않는다 — 맥락에 알리기만 한다(Codex도 이 JSON 모양만 받는다)
        ctx = t("[baton] 방금 쓴 HANDOFF.md 검사 경고(막지 않음):\n- ",
                "[baton] Handoff-check warnings for the HANDOFF.md you just wrote (not blocking):\n- ") + "\n- ".join(warned)
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": capped(ctx, t)}},
                         ensure_ascii=False))


def capped(text, t):
    """OUT_MAX자를 넘으면 자르고 잘랐다고 한 줄 붙인다. 나머지는 검사기를 직접 돌려 본다."""
    if len(text) <= OUT_MAX:
        return text
    note = t("\n[baton] 검사 결과가 길어 잘랐다 — 전체는 python3 lib/handoff_check.py HANDOFF.md",
             "\n[baton] The check output was too long and was cut — run python3 lib/handoff_check.py HANDOFF.md for all of it")
    return text[:OUT_MAX - len(note)] + note


def edit_paths(path):
    """이 세션의 메인 스레드가 편집한 파일 경로, 순서대로. 모양이 다른 줄은 건너뛴다. /baton-setup 스캐너도 쓴다."""
    with open(path, encoding="utf-8", errors="ignore") as f:
        for ln in f:
            if '"tool_use"' not in ln:
                continue
            try:
                d = json.loads(ln)
            except ValueError:
                continue
            if not isinstance(d, dict) or d.get("isSidechain") or not isinstance(d.get("message"), dict):
                continue  # 서브에이전트 편집은 세지 않는다(split-notice와 같은 기준)
            content = d["message"].get("content")
            if not isinstance(content, list):
                continue
            for b in content:
                if not (isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") in EDIT_TOOLS):
                    continue
                inp = b.get("input") if isinstance(b.get("input"), dict) else {}
                fp = inp.get("file_path") or inp.get("notebook_path")
                if isinstance(fp, str):
                    yield fp


def edited_since_handoff(path):
    """이 세션이 마지막으로 인계서(HANDOFF.md 또는 이름 붙은 인계서)를 쓴 뒤 고친 다른 파일들."""
    files = set()
    for fp in edit_paths(path):
        if wrote_handoff(fp):
            files.clear()
        else:
            files.add(os.path.normpath(fp))
    return files


def file_list(files, cwd, lang):
    """자동 쓰기 요청에 적을 파일 목록 — cwd 아래면 상대 경로, 앞 LIST_MAX개만."""
    def show(p):
        if isinstance(cwd, str) and os.path.isabs(p) and os.path.commonpath([os.path.abspath(cwd), p]) == os.path.abspath(cwd):
            return os.path.relpath(p, cwd)
        return p
    names = sorted(show(p) for p in files)
    more = len(names) - LIST_MAX
    out = ", ".join(names[:LIST_MAX])
    if more > 0:
        out += f" 외 {more}개" if lang == "ko" else f", and {more} more"
    return out


def auto_reason(files, cwd, lang):
    """모델에게 돌려줄 자동 쓰기 요청. 스킬 경로는 플러그인 위치로 적는다.
    검사기를 돌리라고 하지 않는다 — Claude Code에서는 저장 훅이 같은 검사를 돌리고(자동 쓰기는 Claude Code에서만 나간다),
    따옴표 친 절대 경로 명령은 스킬의 allowed-tools와 맞지 않아 중간에 권한 확인이 뜬다(리뷰 11-23)."""
    skill = os.path.join(PLUGIN, "skills", "baton", "SKILL.md")
    listed = file_list(files, cwd, lang)
    if lang == "ko":
        return (f"[baton] 이 세션에서 인계서(HANDOFF.md·HANDOFF_*.md)를 마지막으로 쓴 뒤 파일 {len(files)}개를 고쳤다: {listed}. "
                f"지금 baton 인계서 스킬({skill}의 'When the Stop hook asks' 절)대로 저장소 루트의 HANDOFF.md를 쓰거나 갱신한다 — "
                f"기억으로 새로 쓰지 말고 지금 HANDOFF.md에서 시작해 아직 참인 줄은 그대로 옮긴다. "
                f"짧게 쓴다 — 저장하면 저장 검사가 문제와 마지막 커밋판에서 빠진 줄을 알려 준다. "
                f"승격 검토는 건너뛰고 커밋하지 않는다. "
                f"그다음 사용자에게 인계서를 갱신했다는 것과 BATON_HANDOFF_AUTO=off로 끌 수 있다는 것을 한 줄로 알리고 턴을 끝낸다. "
                f"이 요청은 세션에 한 번만 나온다.")
    return (f"[baton] You edited {len(files)} files in this session since the handoff (HANDOFF.md or HANDOFF_*.md) was last "
            f"written: {listed}. Write or update HANDOFF.md at the repo root now, following the baton handoff skill ({skill}, "
            f"section 'When the Stop hook asks'). Start from the current HANDOFF.md and carry forward every line that is still "
            f"true; do not rewrite it from memory. Keep it short. When you save it, the save-time check reports problems "
            f"and lines dropped since the last committed version. "
            f"Skip the promotion review and do not commit. "
            f"Then end your turn with one line to the user saying the handoff was updated and that BATON_HANDOFF_AUTO=off "
            f"turns this off. baton asks for this once per session.")


def on_stop(data):
    cwd = data["cwd"] if isinstance(data.get("cwd"), str) else None
    repo = repo_of(cwd)
    if off("BATON_HANDOFF_NUDGE", repo):
        return
    auto = not off("BATON_HANDOFF_AUTO", repo)
    if auto and data.get("stop_hook_active") is True:
        return  # Stop 훅 때문에 이미 이어서 일하는 중이다 — 또 막지 않는다. 상태를 남기지 않아 다음 턴 끝에 다시 본다
    path, sid = data.get("transcript_path"), data.get("session_id")
    if not isinstance(path, str) or not os.path.isfile(path) or not isinstance(sid, str) or not re.fullmatch(r"[\w-]{1,128}", sid):
        return  # sid는 상태 파일 이름이 된다 — 경로 문자가 섞인 값은 받지 않는다
    state = os.path.join(runlog.cache_dir(), "handoff-nudge", sid)
    if os.path.exists(state):
        return  # 세션에 한 번(제안이든 자동 쓰기든)
    try:
        need = max(1, int(config.get("BATON_HANDOFF_NUDGE_FILES", repo, "3")))
    except ValueError:
        need = 3
    try:
        files = edited_since_handoff(path)
    except Exception:
        return  # 제안 하나 때문에 턴 끝이 오류로 끝나면 안 된다
    if len(files) < need:
        return
    try:
        os.makedirs(os.path.dirname(state), mode=0o700, exist_ok=True)
        open(state, "w").close()
    except OSError:
        return  # 한 번만 알린다는 약속을 못 지키면 아예 알리지 않는다
    lang = i18n.lang(repo)
    foreign = auto and not ours_or_absent(cwd)
    if auto and not foreign:
        print(json.dumps({"decision": "block", "reason": auto_reason(files, cwd, lang)}, ensure_ascii=False))
        runlog.append({"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": "handoff_auto", "session_id": sid,
                       "files": len(files)})
        return
    if lang == "ko":
        msg = (f"[baton] 이 세션에서 파일 {len(files)}개를 고쳤는데 인계서(HANDOFF.md·HANDOFF_*.md)는 그 뒤로 안 바뀌었다. "
               f"작업 덩어리가 끝났다면 '핸드오프 작성해줘'로 인계서를 남겨 두면 다음 세션이 처음부터 다시 찾지 않는다. "
               f"쓸지는 정하면 된다 — 이 제안은 세션에 한 번만 나온다.")
    else:
        msg = (f"[baton] You edited {len(files)} files in this session, and the handoff (HANDOFF.md or HANDOFF_*.md) has not "
               f"changed since. If a piece of work is done, ask for 'write a handoff' so the next session does not have to "
               f"search from scratch. It is your call — this suggestion appears once per session.")
    print(json.dumps({"systemMessage": msg}, ensure_ascii=False))
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": "handoff_nudge", "session_id": sid, "files": len(files)}
    if foreign:
        rec["fallback"] = "foreign_handoff"  # 자동 쓰기 대신 제안한 까닭
    runlog.append(rec)


def ours_or_absent(cwd):
    """저장소 루트에 HANDOFF.md가 없거나 baton 형식인가. 못 읽으면 False — 모르는 파일을 다시 쓰게 하지 않는 쪽."""
    try:
        path = os.path.join(rules.repo_root(cwd), "HANDOFF.md")
        return not os.path.isfile(path) or handoff_check.looks_ours(handoff_check.read(path))
    except Exception:
        return False


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    if not isinstance(data, dict):
        return
    event = data.get("hook_event_name")
    try:
        if event == "PostToolUse":
            on_edit(data)
        elif event == "Stop":
            on_stop(data)
    except Exception:
        return  # 검사·제안 때문에 도구 호출이나 턴이 오류로 끝나면 안 된다


if __name__ == "__main__":
    main()
