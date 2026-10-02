#!/usr/bin/env python3
# 북극성 길 단계 3 — 인계서 검사와 결정론 트리거. 이벤트 둘을 한 파일에서 받는다.
#
# PostToolUse(Write|Edit|MultiEdit): 고친 파일이 HANDOFF.md면 lib/handoff_check.py로 검사하고,
#   문제가 있으면 모델에게 돌려준다(decision: block — 쓰기는 이미 됐고, 이유를 보고 고치게 한다).
# Stop: 이 세션이 마지막으로 HANDOFF.md를 쓴 뒤 다른 파일을 N개(기본 3) 이상 고쳤으면, 세션에 한 번 사용자에게 인계서를 제안한다.
#   쓰기는 사람이 정한다. 문턱 3은 로컬 세션 94개 실측(2026-10-01): 1~2개 고친 세션은 인계서를 16% 썼고 3개 이상은 67% 썼다.
#
# 끄기: BATON_HANDOFF_CHECK=off(검사) · BATON_HANDOFF_NUDGE=off(제안) · 문턱: BATON_HANDOFF_NUDGE_FILES=3
#   환경변수 또는 설정 파일(lib/config.py, /baton-setup이 사용자 세션 분포로 문턱을 제안해 쓴다)에서 읽는다.
# Codex의 편집 도구(apply_patch)는 file_path를 주지 않아 여기서 안 잡힌다 — 스킬이 쓴 뒤 검사기를 직접 부른다.
import json, os, re, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import config, handoff_check, rules, runlog

EDIT_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}  # 제안 문턱에 세는 편집. 검사 matcher에 NotebookEdit가 없는 것은 HANDOFF.md를 못 고쳐서다


def off(name, repo):
    return config.get(name, repo).strip().lower() in ("off", "0", "false", "no")


def is_handoff(path):
    return isinstance(path, str) and os.path.basename(path) == "HANDOFF.md"


def repo_of(start):
    """설정 파일의 저장소 절을 고를 루트. 설정이 없으면 git을 부르지 않는다(Codex 훅에는 CLAUDE_PROJECT_DIR가 없다)."""
    return rules.repo_root(start) if config.load() is not None else None


def on_edit(data):
    ti = data.get("tool_input")
    path = ti.get("file_path") if isinstance(ti, dict) else None
    if not is_handoff(path):
        return
    if not os.path.isabs(path) and isinstance(data.get("cwd"), str):
        path = os.path.join(data["cwd"], path)
    if off("BATON_HANDOFF_CHECK", repo_of(os.path.dirname(path) or None)):
        return
    try:
        problems = handoff_check.check_file(path, strict=False)
    except OSError:
        return
    runlog.append({"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": "handoff_check",
                   "session_id": data.get("session_id"), "problems": len(problems)})
    if problems:
        reason = ("[baton] 방금 쓴 HANDOFF.md에 인계서 검사 문제가 있다. 고친 뒤 다시 저장한다:\n- "
                  + "\n- ".join(problems))
        print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))


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
    """이 세션이 마지막으로 HANDOFF.md를 쓴 뒤 고친 다른 파일들."""
    files = set()
    for fp in edit_paths(path):
        if is_handoff(fp):
            files.clear()
        else:
            files.add(os.path.normpath(fp))
    return files


def on_stop(data):
    repo = repo_of(data["cwd"] if isinstance(data.get("cwd"), str) else None)
    if off("BATON_HANDOFF_NUDGE", repo):
        return
    path, sid = data.get("transcript_path"), data.get("session_id")
    if not isinstance(path, str) or not os.path.isfile(path) or not isinstance(sid, str) or not re.fullmatch(r"[\w-]{1,128}", sid):
        return  # sid는 상태 파일 이름이 된다 — 경로 문자가 섞인 값은 받지 않는다
    state = os.path.join(runlog.cache_dir(), "handoff-nudge", sid)
    if os.path.exists(state):
        return  # 세션에 한 번
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
    msg = (f"[baton] 이 세션에서 파일 {len(files)}개를 고쳤는데 HANDOFF.md는 그 뒤로 안 바뀌었다. "
           f"작업 덩어리가 끝났다면 '핸드오프 작성해줘'로 인계서를 남겨 두면 다음 세션이 처음부터 다시 찾지 않는다. "
           f"쓸지는 정하면 된다 — 이 제안은 세션에 한 번만 나온다.")
    print(json.dumps({"systemMessage": msg}, ensure_ascii=False))
    runlog.append({"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": "handoff_nudge", "session_id": sid,
                   "files": len(files)})


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
