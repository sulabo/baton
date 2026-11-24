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
#   맥락이 처음의 2배·3배(BATON_SPLIT_RATIOS)를 넘을 때도 같은 방식으로 한 번 쓰게 한다(소유자 결정 11-24, 측정·문장은
#   hooks/split-notice.py). Stop 결정은 여기 한 곳 — 두 까닭이 한 Stop에 겹치면 한 번만 묻고, 이번 턴에 인계서를 이미 고쳤고 그 뒤 파일을
#   문턱만큼 더 고치지 않았으면 묻지 않고 알리기만 한다. 끄기: BATON_SPLIT_NOTICE=off(맥락 알림 전부), BATON_HANDOFF_AUTO=off(묻지 않고 알리기만).
#
# 끄기: BATON_HANDOFF_CHECK=off(검사) · BATON_HANDOFF_NUDGE=off(파일 수 까닭의 제안·자동 쓰기 — 맥락 까닭은 BATON_SPLIT_NOTICE) · BATON_HANDOFF_AUTO=off(자동 쓰기 대신 제안)
#   문턱: BATON_HANDOFF_NUDGE_FILES=3. 환경변수 또는 설정 파일(lib/config.py, /baton-setup이 사용자 세션 분포로 문턱을 제안해 쓴다)에서 읽는다.
# Codex의 편집 도구(apply_patch)는 file_path를 주지 않아 여기서 안 잡힌다 — 스킬이 쓴 뒤 검사기를 직접 부른다.
# Codex의 Stop도 제안·자동 쓰기가 나가지 않는다: 세션 기록(~/.codex/sessions)에 Claude Code 모양의 "tool_use" 편집 줄이 없어
#   edit_paths가 0개를 센다(11-23 실제 Codex 기록 확인: "type":"tool_use" 0줄, 편집은 custom_tool_call apply_patch).
import json, os, re, sys, time

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PLUGIN, "lib"))
import config, handoff_check, i18n, rules, runlog
import importlib.util

try:  # 맥락 재기·알림 문장(Stop 결정은 on_stop 한 곳). 못 불러도 저장 검사(비밀값 막기)는 살아야 한다 — 맥락 까닭만 끈다
    _spec = importlib.util.spec_from_file_location("split_notice", os.path.join(PLUGIN, "hooks", "split-notice.py"))
    split = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(split)
except Exception:
    split = None

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


def turn_wrote_handoff(path):
    """마지막 사람 프롬프트 뒤에 메인 스레드가 인계서를 썼나(이번 턴). 도구 결과·메타 줄은 사람 프롬프트가 아니다."""
    wrote = False
    with open(path, encoding="utf-8", errors="ignore") as f:
        for ln in f:
            if '"user"' not in ln and '"tool_use"' not in ln:
                continue
            try:
                d = json.loads(ln)
            except ValueError:
                continue
            if not isinstance(d, dict) or d.get("isSidechain") or not isinstance(d.get("message"), dict):
                continue
            c = d["message"].get("content")
            if d.get("type") == "user" and not d.get("isMeta"):
                if isinstance(c, str) or (isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "text" for b in c)):
                    wrote = False
            elif isinstance(c, list):
                for b in c:
                    if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") in EDIT_TOOLS:
                        inp = b.get("input") if isinstance(b.get("input"), dict) else {}
                        if wrote_handoff(inp.get("file_path")):
                            wrote = True
    return wrote


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


def auto_reason(files, cwd, lang, grown=None):
    """모델에게 돌려줄 자동 쓰기 요청. files: 인계서 뒤에 고친 파일(없으면 빈 목록), grown: 맥락이 넘은 문턱 (배수, 첫, 마지막) 또는 None.
    두 까닭이 겹치면 한 요청에 같이 적는다. 스킬 경로는 플러그인 위치로 적는다.
    검사기를 돌리라고 하지 않는다 — Claude Code에서는 저장 훅이 같은 검사를 돌리고(자동 쓰기는 Claude Code에서만 나간다),
    따옴표 친 절대 경로 명령은 스킬의 allowed-tools와 맞지 않아 중간에 권한 확인이 뜬다(리뷰 11-23)."""
    skill = os.path.join(PLUGIN, "skills", "baton", "SKILL.md")
    why = []
    if lang == "ko":
        if files:
            why.append(f"이 세션에서 인계서(HANDOFF.md·HANDOFF_*.md)를 마지막으로 쓴 뒤 파일 {len(files)}개를 고쳤다: "
                       f"{file_list(files, cwd, lang)}.")
        if grown:
            band, first, last = grown
            why.append(f"이 대화의 맥락이 처음보다 {band:g}배 넘게 커졌다({split.man(first)} → {split.man(last)} 토큰).")
        line = split.user_line(lang, grown[0]) if grown else "인계서를 고쳐 뒀어요. 이 기능을 끄려면 BATON_HANDOFF_AUTO=off로 설정하세요."
        return ("[baton] " + " ".join(why) + " "
                f"지금 baton 인계서 스킬({skill}의 'When the Stop hook asks' 절)대로 저장소 루트의 HANDOFF.md를 쓰거나 갱신한다 — "
                f"기억으로 새로 쓰지 말고 지금 HANDOFF.md에서 시작해 아직 참인 줄은 그대로 옮긴다. "
                f"짧게 쓴다 — 저장하면 저장 검사가 문제와 마지막 커밋판에서 빠진 줄을 알려 준다. "
                f"승격 검토는 건너뛰고 커밋하지 않는다. " + ("/compact는 권하지 않는다. " if grown else "")
                + f"그다음 사용자에게 이 한 줄만 쓰고 턴을 끝낸다: \"{line}\" "
                + ("이 요청은 맥락 문턱마다 한 번만 나온다." if grown else "이 요청은 세션에 한 번만 나온다."))
    if files:
        why.append(f"You edited {len(files)} files in this session since the handoff (HANDOFF.md or HANDOFF_*.md) was last "
                   f"written: {file_list(files, cwd, lang)}.")
    if grown:
        band, first, last = grown
        why.append(f"This conversation's context is now more than {band:g}× its size at the start "
                   f"({first // 1000}K → {last // 1000}K tokens).")
    line = split.user_line(lang, grown[0]) if grown else "I updated the handoff. To turn this off, set BATON_HANDOFF_AUTO=off."
    return ("[baton] " + " ".join(why) + " "
            f"Write or update HANDOFF.md at the repo root now, following the baton handoff skill ({skill}, "
            f"section 'When the Stop hook asks'). Start from the current HANDOFF.md and carry forward every line that is still "
            f"true; do not rewrite it from memory. Keep it short. When you save it, the save-time check reports problems "
            f"and lines dropped since the last committed version. "
            f"Skip the promotion review and do not commit. " + ("Do not suggest /compact. " if grown else "")
            + f"Then end your turn with exactly this one line to the user: \"{line}\" "
            + ("baton asks for this once per context threshold." if grown else "baton asks for this once per session."))


def nudge_message(n, lang):
    """자동 쓰기를 못 할 때 사용자에게 보이는 파일 고침 제안."""
    if lang == "ko":
        return (f"[baton] 파일을 {n}개 고쳤는데 인계서는 그대로예요.\n"
                f"하던 일이 끝났다면 \"인계서 써 줘\"라고 해 보세요. 다음 대화가 처음부터 다시 찾지 않아도 돼요.\n"
                f"이 제안은 한 대화에 한 번만 나와요.")
    return (f"[baton] You changed {n} {'file' if n == 1 else 'files'}, but the handoff hasn't changed.\n"
            f"If you're done with the current task, try saying \"write a handoff\". "
            f"The next conversation won't have to search from scratch.\n"
            f"You'll see this suggestion only once per conversation.")


def on_stop(data):
    """Stop 결정 한 곳 — 까닭 둘(파일 고침 F·맥락 문턱 S)을 함께 보고 한 Stop에 많아야 한 번 묻는다.
    물을 수 있으면(BATON_HANDOFF_AUTO 켬, 이번 턴에 인계서를 고친 뒤 그대로인 게 아님, HANDOFF.md가 없거나 baton 형식)
    decision "block" 하나에 두 까닭을 같이 적는다. 못 물으면 사용자에게 systemMessage 하나로 알린다. 다른 Stop 훅이 턴을 잇는 중
    (stop_hook_active)이면 묻지도 알리지도 않고 상태도 남기지 않는다 — 다음 턴 끝에 다시 본다. 상태는 까닭마다 따로
    (F: 세션에 한 번 handoff-nudge/<sid>, S: 문턱마다 한 번 split/<sid>.json)."""
    cwd = data["cwd"] if isinstance(data.get("cwd"), str) else None
    repo = repo_of(cwd)
    nudge_on, split_on = not off("BATON_HANDOFF_NUDGE", repo), split is not None and not off("BATON_SPLIT_NOTICE", repo)
    if not (nudge_on or split_on):
        return
    auto = not off("BATON_HANDOFF_AUTO", repo)
    path, sid = data.get("transcript_path"), data.get("session_id")
    if not isinstance(path, str) or not os.path.isfile(path) or not isinstance(sid, str) or not re.fullmatch(r"[\w-]{1,128}", sid):
        return  # sid는 상태 파일 이름이 된다 — 경로 문자가 섞인 값은 받지 않는다
    state = os.path.join(runlog.cache_dir(), "handoff-nudge", sid)
    files = []
    if nudge_on and not os.path.exists(state):  # F는 세션에 한 번(제안이든 자동 쓰기든)
        try:
            need = max(1, int(config.get("BATON_HANDOFF_NUDGE_FILES", repo, "3")))
        except ValueError:
            need = 3
        try:
            files = sorted(edited_since_handoff(path))
        except Exception:
            files = []  # 제안 하나 때문에 턴 끝이 오류로 끝나면 안 된다
        files = files if len(files) >= need else []
    grown = None
    if split_on:
        try:
            hit = split.crossed_band(path, repo, sid)
        except Exception:
            hit = None
        if hit:
            grown, ratio = hit[:3], hit[3]
    if not files and not grown:
        return
    try:
        written = turn_wrote_handoff(path)
    except Exception:
        written = False
    # fresh: 이번 턴에 인계서를 고쳤고 그 뒤로 문턱만큼 고친 파일은 없다 — 맥락 까닭은 알리기만 한다.
    # files가 있으면 마지막 인계서 쓰기 뒤에 고친 것이라(edited_since_handoff) 이번 턴에 썼어도 다시 낡았다 — 묻는다(리뷰 11-24)
    fresh = written and not files
    active = data.get("stop_hook_active") is True
    if auto and active and not fresh:
        return  # 다른 Stop 훅 때문에 이미 이어서 일하는 중 — 막지도 알리지도 않는다. 상태를 남기지 않아 다음 턴 끝에 다시 본다
    try:  # 한 번만 묻는다는 약속을 못 지키면 아예 말하지 않는다. 맥락 상태를 먼저(깨진 상태 파일이 흔한 쪽).
        # ponytail: 맥락 상태를 쓴 뒤 파일 상태 쓰기만 실패하면 그 문턱은 알리지 못하고 넘어간다(같은 캐시 폴더라 드묾)
        if grown:
            split.mark(sid, grown[0])
        if files:
            os.makedirs(os.path.dirname(state), mode=0o700, exist_ok=True)
            open(state, "w").close()
    except Exception:  # OSError, 깨진 상태 파일(sorted의 TypeError 등)
        return
    lang = i18n.lang(repo)
    foreign = auto and not fresh and not ours_or_absent(cwd)
    ask = auto and not fresh and not foreign  # active는 위에서 돌아갔다(auto일 때)
    ts = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    if ask:
        print(json.dumps({"decision": "block", "reason": auto_reason(files, cwd, lang, grown)}, ensure_ascii=False))
    else:
        msgs = ([split.notice(lang, grown[0], grown[1], grown[2], saved=fresh)] if grown else []) \
            + ([nudge_message(len(files), lang)] if files else [])
        print(json.dumps({"systemMessage": "\n\n".join(msgs)}, ensure_ascii=False))
    if files:
        rec = {"ts": ts, "event": "handoff_auto" if ask else "handoff_nudge", "session_id": sid, "files": len(files)}
        if foreign:
            rec["fallback"] = "foreign_handoff"  # 자동 쓰기 대신 제안한 까닭
        runlog.append(rec)
    if grown:
        rec = {"ts": ts, "event": "split_notice", "session_id": sid, "first_ctx": grown[1], "last_ctx": grown[2],
               "ratio": round(ratio, 2), "band": grown[0], "mode": "ask" if ask else "saved" if fresh else "notice"}
        if foreign:
            rec["fallback"] = "foreign_handoff"
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
