#!/usr/bin/env python3
# 북극성 길 단계 3 — 인계서 검사와 결정론 트리거. 이벤트 둘을 한 파일에서 받는다.
#
# PostToolUse(Write|Edit|MultiEdit): 고친 파일이 HANDOFF.md면 lib/handoff_check.py로 검사하고,
#   문제가 있으면 모델에게 돌려준다(decision: block — 쓰기는 이미 됐고, 이유를 보고 고치게 한다).
#   경고만 있으면(확인 표시 [V]·[?] 빠짐·필독 3개 초과·마지막 커밋판에 있던 줄이 빠짐) 막지 않고 additionalContext로 알리기만 한다.
#   둘 다 없으면 통과 한 줄("[baton] HANDOFF.md 검사 통과(N줄·M자).")을 additionalContext로 낸다 — 아무 말이 없으면 모델이 검사기를
#   손으로 다시 돌렸다(2026-11-24 compact 맞대기 실험 2차, 인계서 쓰기 10번 중 10번). 스킬은 이 줄이 보이면 검사기를 다시 돌리지 않게 한다.
#   경고 규칙·빠진 줄 검사 중 하나가 오류로 못 돌았으면 통과라고 하지 않고 "검사 일부를 돌리지 못했어요" 한 줄을 붙인다 — 스킬은 이 줄을
#   "줄 없음"처럼 보고 검사기를 직접 돌린다(리뷰 11-25).
#   빠진 줄은 git HEAD의 HANDOFF.md와 비교한다(lib/handoff_check.py drop_warnings). 미추적·이력 없음이면 아무 말도 안 한다.
#   출력은 OUT_MAX자에서 자른다(Claude Code 훅 출력 상한 10,000자 — 넘으면 파일로 빠진다, hooks/handoff-inject.py 머리 주석).
#   상한(줄·글자)을 넘은 채 줄여 가는 편집은 막지 않는다: 이 대화의 직전 검사보다 짧아졌으면 크기 문제를 경고로 낮추고, 크기로 막는 것은
#   턴에 한 번(Stop과 모든 프롬프트가 표지를 지운다). 11-25 실사용: 상한 넘은 동안 줄이는 편집 18번이 6묶음으로 막혔다(331→54자로 줄인 편집도).
# PostToolUse·PostToolUseFailure(Bash): Bash(python heredoc 등)로 쓴 HANDOFF.md도 같은 검사를 받는다(11-25 실사용: 인계서 쓰기 약 74번이
#   Bash였고, 상한 넘은 인계서가 9번 커밋됐다). 0이 아닌 코드로 끝난 호출(쓴 뒤 실패한 커밋 등)은 PostToolUseFailure로만 온다 — 문서
#   https://code.claude.com/docs/en/hooks(2026-11-26 확인)의 결정 표가 이 이벤트도 top-level decision "block"·reason을 받는다고 적어 같은 출력을
#   쓴다(그 이벤트 절은 additionalContext만 적는다 — 경고·통과는 hookEventName "PostToolUseFailure"의 additionalContext). 셸은 해석하지 않는다 —
#   명령이 인계서 파일 이름(MENTION)을 말했고, 저장소 루트 HANDOFF.md의 내용 해시가 이 대화에서 마지막으로 검사한(또는 본) 것과 다르고,
#   그 변화가 이 호출 중에 생겼을 때만(call_start) "이 Bash 호출 뒤 바뀌어 있었다"며 검사한다. 말하지 않은 호출 뒤의 변화(git checkout·pull·
#   stash)와 호출 전에 다른 창·사람이 고친 것은 기억만 한다(리뷰 11-26). 말하지 않은 호출은 설정·검사 모듈을 불러오지 않는 빠른 길로 끝난다(quiet_bash). 실측(11-26, 이 기계,
#   20번 중앙값): Bash 한 번에 67ms → 43ms, 빈 python3 실행이 30ms — 남은 몫은 이 스크립트 컴파일(약 6ms, 스크립트는 .pyc가 없다)과
#   hashlib import(약 4ms). 무거운 모듈을 안 부르는지는 hooks/test_handoff_check_hook.py test_bash_fast_path_skips_heavy_modules가 지킨다.
#   스킬은 HANDOFF.md를 편집 도구로 고치게 한다 — Bash로 쓴 것은 쓴 뒤에야 검사된다.
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
#   호출 맥락이 25만·45만 토큰(BATON_SPLIT_TOKENS — 문턱과 그 근거·예전 배수 규칙 BATON_SPLIT_RATIOS는 hooks/split-notice.py)을 넘을 때도
#   같은 방식으로 문턱마다 한 번 쓰게 한다(소유자 결정 11-24). 단 마지막 인계서 쓰기 뒤에 넘길 일(work_since_handoff: 편집 도구로 고친
#   파일, 서브에이전트가 실제로 고친 Agent·Task 위임, 파일을 쓰는 Bash 명령)이 하나라도 있을 때만 — 없으면 묻지도 알리지도 않고 문턱도 남기지 않아, 나중에 일한
#   Stop에서 한 번 묻는다(11-25 실사용: 질문만 한 턴 뒤에 인계서를 다시 쓰게 했다). 이번 턴에 인계서를 썼어도 그 뒤에 일했으면 낡았으니
#   묻는다(리뷰 11-25 — 예전의 "이번 턴에 썼으면 알리기만"은 뺐다). Stop 결정은 여기 한 곳 — 두 까닭이 한 Stop에 겹치면 한 번만 묻는다.
#   끄기: BATON_SPLIT_NOTICE=off(맥락 알림 전부), BATON_HANDOFF_AUTO=off(묻지 않고 알리기만).
#   파일 수 까닭(F)은 예전 그대로 편집 도구의 파일만 센다 — 문턱 3과 /baton-setup 분포가 그 수로 재졌다. 다만 Bash로 쓴 인계서에서도
#   처음부터 센다(리뷰 11-25). 넘길 일 세기는 WORK_BUDGET초 안에 — 넘기면 편집 도구만 센다(훅 시한 10초에 죽으면 두 까닭이 다 사라진다).
#   1.0.2(소유자 결정 11-26): 맥락 까닭은 이번 턴에 일했을 때만 묻는다 — 넘길 일은 마지막 인계서 쓰기와 이번 턴의 시작(사람 프롬프트) 중
#   늦은 쪽 뒤에 한 것만 센다. 질문·읽기만 한 턴은 막지 않고 문턱은 남겨 뒀다가 다음에 일한 턴 끝에 묻는다(1.0.1 재돌림: 막힘 10번 중 5번이
#   질문·읽기만 한 턴). 턴은 사람 프롬프트·다른 세션 메시지·작업 알림에서 시작하고, 알림 턴은 뒤에서 돌던 위임을 다시 본다(리뷰 11-26).
#   기록에 안 보이는 인계서 쓰기(Bash 안 python 등)도 쓴 것으로 친다: Bash 검사가 남긴 시각(bash_write_ts)을 기록 줄의 timestamp 사이에
#   넣어, 그 뒤에 한 것만 센다(두 까닭 다 — with_handoff_mark). 파일 mtime은 쓰지 않는다(리뷰 11-26).
#
# 끄기: BATON_HANDOFF_CHECK=off(검사) · BATON_HANDOFF_NUDGE=off(파일 수 까닭의 제안·자동 쓰기 — 맥락 까닭은 BATON_SPLIT_NOTICE) · BATON_HANDOFF_AUTO=off(자동 쓰기 대신 제안)
#   문턱: BATON_HANDOFF_NUDGE_FILES=3. 환경변수 또는 설정 파일(lib/config.py, /baton-setup이 사용자 세션 분포로 문턱을 제안해 쓴다)에서 읽는다.
# Codex의 편집 도구(apply_patch)는 file_path를 주지 않아 여기서 안 잡힌다 — 스킬이 쓴 뒤 검사기를 직접 부른다.
# Codex의 Stop도 제안·자동 쓰기가 나가지 않는다: 세션 기록(~/.codex/sessions)에 Claude Code 모양의 "tool_use" 편집 줄이 없어
#   edit_paths가 0개를 센다(11-23 실제 Codex 기록 확인: "type":"tool_use" 0줄, 편집은 custom_tool_call apply_patch).
import hashlib, json, os, re, sys, time

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PLUGIN, "lib"))
import runlog  # 가볍다(설정 모듈은 runlog.append 안에서 부른다) — 아래 Bash 빠른 길(quiet_bash)은 이것만 쓴다

# Bash 명령이 인계서 파일을 말하나(HANDOFF.md·HANDOFF_트랙.md·handoff-x.md) — 말했을 때만 그 뒤 바뀐 HANDOFF.md를 검사한다. 낱말 handoff만
# 보던 것은 너무 넓었다(리뷰 11-26: baton 저장소 실제 Bash 명령의 37%가 handoff_check·테스트 이름으로 걸렸다)
MENTION = re.compile(r"(?i)handoff[\w-]*\.md")
BASH_EVENTS = ("PostToolUse", "PostToolUseFailure")  # 0이 아닌 코드로 끝난 Bash는 PostToolUseFailure로만 온다(리뷰 11-26: 쓰고 실패한 호출)


def seen_file(sid, path, ext=".json"):
    """대화·파일별 저장 검사 기억 <캐시>/baton/handoff-seen/<sid>/<실제 경로 해시>.json — 마지막으로 검사하거나 본 내용의 해시·글자 수·stat.
    ext=".bash_ts"는 Bash로 쓴 것을 검사한 시각(Stop이 쓴다) — 따로 둬서 겹친 Bash 훅의 읽고-고쳐-쓰기가 지우지 않게(리뷰 11-26).
    파일마다 따로라 다른 워크트리의 HANDOFF.md를 고쳐도 루트 것의 기억과 "직전 검사보다 짧아졌나"가 섞이지 않는다. sid가 이상하면 None.
    30일 넘게 안 건드린 대화 폴더는 Stop이 지운다(prune_seen)."""
    d = runlog.session_dir("handoff-seen", sid)
    real = os.path.realpath(path).encode("utf-8", "surrogateescape")
    return os.path.join(d, hashlib.sha1(real).hexdigest()[:16] + ext) if d else None


def seen(sid, path):
    """이 대화가 path에 대해 남긴 기억(dict). 없거나 깨졌으면 빈 dict."""
    try:
        with open(seen_file(sid, path), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, TypeError, ValueError):
        return {}


def text_sha(text):
    return hashlib.sha1(text.encode("utf-8", "surrogatepass")).hexdigest()[:16]


def write_state(p, body):
    """상태 파일 하나를 임시 파일에 쓴 뒤 바꿔치기한다(폴더 700·파일 600). 썼으면 True."""
    if not p:
        return False
    try:
        os.makedirs(os.path.dirname(p), mode=0o700, exist_ok=True)
        tmp = f"{p}.{os.getpid()}.tmp"
        with os.fdopen(os.open(tmp, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
            f.write(body)
        os.replace(tmp, p)
        return True
    except OSError:
        return False


def remember(sid, path, text):
    """path의 지금 내용(text)을 이 대화가 마지막으로 본 것으로 남긴다. 남겼으면 True. 못 남기면 False — Bash 경로는 그때 검사하지 않는다
    (기억 없이 검사하면 Bash마다 같은 내용을 다시 막는다, 리뷰 11-26)."""
    try:
        st = os.stat(path)
    except OSError:
        return False
    return write_state(seen_file(sid, path), json.dumps({"sha": text_sha(text), "chars": len(text), "stat": [st.st_size, st.st_mtime_ns]}))


def quiet_bash(data):
    """Bash 빠른 길(PostToolUse·PostToolUseFailure) — 맡았으면 True. 명령이 인계서 파일을 말하지 않으면 검사하지 않고, 저장소 루트 HANDOFF.md가 바뀌었으면 새 내용을 조용히
    기억만 한다: git checkout·pull·stash, 다른 창, 사람이 고친 것을 "이 Bash 호출 뒤 바뀌었다"로 막지 않으려고(리뷰 11-26).
    stat이 기억과 같으면 파일도 읽지 않는다. 설정·검사 모듈을 불러오지 않는다(Bash 뒤마다 돈다 — 리뷰 11-26 실측은 머리말).
    저장소 루트는 CLAUDE_PROJECT_DIR만 본다 — 없으면(Codex) 느린 길(on_bash)이 git으로 찾는다.
    ponytail: 인계서 파일을 말하지 않는 스크립트가 HANDOFF.md를 쓰면(python3 gen.py) 검사하지 않는다. BATON_HANDOFF_CHECK=off여도 기억은 남긴다."""
    ti = data.get("tool_input")
    cmd = ti.get("command") if isinstance(ti, dict) else None
    root = os.environ.get("CLAUDE_PROJECT_DIR")
    if data.get("hook_event_name") not in BASH_EVENTS or data.get("tool_name") != "Bash" or not isinstance(cmd, str) \
            or MENTION.search(cmd) or not root:
        return False
    sid, path = data.get("session_id"), os.path.join(root, "HANDOFF.md")
    try:
        st = os.stat(path)
        if seen(sid, path).get("stat") == [st.st_size, st.st_mtime_ns]:
            return True
        with open(path, encoding="utf-8", errors="replace") as f:
            remember(sid, path, f.read())
    except OSError:
        pass
    return True


# 훅으로 돌 때는 stdin을 먼저 읽고, Bash 빠른 길이면 아래 무거운 import 없이 끝낸다(main은 DATA를 받는다)
if __name__ == "__main__":
    try:
        DATA = json.load(sys.stdin)
        if not isinstance(DATA, dict) or quiet_bash(DATA):
            sys.exit(0)
    except Exception:
        sys.exit(0)

import config, handoff_check, i18n, rules

LIST_MAX = 10  # 자동 쓰기 요청에 이름을 적는 파일 수. 나머지는 개수만
OUT_MAX = 9600  # 검사 결과(reason·additionalContext)의 상한 — 주입 훅과 같은 여유
# 저장 검사의 시한(훅 시작부터). 훅 시한은 10초(hooks.json)이고 죽은 훅은 아무것도 내지 않는다 — 그러면 비밀값 막기도 사라진다.
# 그래서 막아야 할 문제(check_file)를 먼저 다 만들고, 빠진 줄 검사는 이 시한까지 남은 시간(최대 handoff_check.DROP_BUDGET초)만 쓴다
HOOK_DEADLINE = 8.0

EDIT_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}  # 제안 문턱에 세는 편집. 검사 matcher에 NotebookEdit가 없는 것은 HANDOFF.md를 못 고쳐서다
_split = []  # split_mod가 한 번 불러온 hooks/split-notice.py(또는 None)


def split_mod():
    """맥락 재기·알림 문장(hooks/split-notice.py). Stop에서만 부른다 — 편집·Bash 뒤마다 불러오면 느리다(리뷰 11-26).
    못 불러오면 None: 저장 검사(비밀값 막기)는 살고 맥락 까닭만 꺼진다. /baton-setup 스캐너(lib/setup_scan.py)도 이것을 쓴다."""
    if not _split:
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("split_notice", os.path.join(PLUGIN, "hooks", "split-notice.py"))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _split.append(mod)
        except Exception:
            _split.append(None)
    return _split[0]


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


def blocked_file(sid):
    """이번 턴에 크기 때문에 막았다는 표지 <캐시>/baton/handoff-seen/<sid>/blocked. 턴이 바뀌면 지운다 — Stop(on_stop)과 사람 프롬프트
    (hooks/handoff-inject.py, 끊긴 턴의 표지가 남지 않게, 리뷰 11-26). sid가 이상하면 None."""
    d = runlog.session_dir("handoff-seen", sid)
    return os.path.join(d, "blocked") if d else None


def prune_seen(days=30):
    """days일 넘게 안 건드린 대화의 저장 검사 기억 폴더(handoff-seen/<sid>)를 지운다 — 대화마다 폴더가 하나씩 남는다(리뷰 11-26,
    drift 캐시가 오래된 파일을 지우는 것과 같은 방식). Stop마다 돈다(폴더 목록 한 번). 실패는 넘긴다."""
    import shutil  # Stop에서만 — Bash 빠른 길이 불러오지 않게
    base, cut = os.path.join(runlog.cache_dir(), "handoff-seen"), time.time() - days * 86400
    try:
        entries = list(os.scandir(base))
    except OSError:
        return
    for e in entries:
        try:
            if runlog.SID.fullmatch(e.name) and e.is_dir(follow_symlinks=False) and e.stat(follow_symlinks=False).st_mtime < cut:
                shutil.rmtree(e.path, ignore_errors=True)
        except OSError:
            pass


def block_once(sid):
    """이번 턴에 크기 때문에 처음 막는가. 표지 파일을 O_EXCL로 만든 쪽만 참이다 — 동시에 저장한 편집 셋이 셋 다 막지 않게.
    sid가 이상하거나 캐시에 못 쓰면 참(예전처럼 막는다)."""
    p = blocked_file(sid)
    if not p:
        return True
    try:
        os.makedirs(os.path.dirname(p), mode=0o700, exist_ok=True)
        os.close(os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
        return True
    except FileExistsError:
        return False
    except OSError:
        return True


def on_edit(data):
    ti = data.get("tool_input")
    path = ti.get("file_path") if isinstance(ti, dict) else None
    if not is_handoff(path):
        if wrote_handoff(path):  # 검사는 안 하지만 썼다는 것은 남긴다 — 제안 효과를 셀 때 빠지지 않게
            runlog.append({"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": "handoff_write",
                           "session_id": data.get("session_id"), "named": True})
        return
    if not os.path.isabs(path) and isinstance(data.get("cwd"), str):
        path = os.path.join(data["cwd"], path)
    check_handoff(path, data, time.monotonic())


def session_start(path, lines=50):
    """세션 기록 앞 lines줄에서 처음 읽히는 timestamp(초) — 이 대화가 시작된 때. 못 찾으면 None."""
    from candidates import when
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            for _, ln in zip(range(lines), f):
                try:
                    d = json.loads(ln)
                except ValueError:
                    continue
                t = when(d.get("timestamp")) if isinstance(d, dict) else None
                if t:
                    return t.timestamp()
    except (OSError, TypeError):
        pass
    return None


CALL_TAIL = 1 << 20  # 이 호출의 시작 시각을 찾을 때 읽는 세션 기록 끝(바이트)


def call_start(path, tool_use_id):
    """이 도구 호출이 시작된 때(초) — 세션 기록 끝 CALL_TAIL바이트에서 그 tool_use id를 담은 assistant 줄의 timestamp. 못 찾으면 None."""
    if not isinstance(tool_use_id, str) or not tool_use_id:
        return None
    from candidates import when
    try:
        with open(path, "rb") as f:
            f.seek(max(0, os.fstat(f.fileno()).st_size - CALL_TAIL))
            lines = f.read().split(b"\n")
    except (OSError, TypeError):
        return None
    needle = tool_use_id.encode("utf-8", "surrogatepass")
    for ln in reversed(lines):
        if needle not in ln:
            continue
        try:
            d = json.loads(ln)
        except ValueError:
            continue
        if isinstance(d, dict) and any(tid == tool_use_id for _, _, tid in tool_blocks(d)):
            t = when(d.get("timestamp"))
            return t.timestamp() if t else None
    return None


def on_bash(data):
    """PostToolUse·PostToolUseFailure(Bash) 느린 길 — 명령이 인계서 파일을 말했거나 CLAUDE_PROJECT_DIR가 없을 때(quiet_bash가 넘긴 것).
    저장소 루트 HANDOFF.md의 내용이 이 대화에서 마지막으로 검사한(또는 본) 것과 다르면: 명령이 인계서 파일을 말했고 그 변화가 이 호출 중에
    생겼으면 편집 도구와 같은 검사를 돌리고, 아니면 기억만 한다. 이 호출 중인지는 파일 mtime과 이 호출의 시작(call_start)을 견준다 —
    호출 전에 다른 창이나 사람이 고친 것을 "이 Bash 호출 뒤 바뀌었다"로 막지 않으려고(리뷰 11-26). 시작을 못 찾으면 명령이 말했는지만 본다.
    처음 보는 파일은 그때 대화가 시작된 뒤에 바뀌었을 때만 검사한다. 셸 명령은 해석하지 않는다.
    ponytail: 저장소 루트의 HANDOFF.md만 본다. 같은 호출 안의 쓰기와 커밋(python … && git commit)은 커밋한 뒤에야 검사된다.
    대화 시작은 세션 기록 첫 줄들의 timestamp — 못 읽으면 처음 본 파일은 검사하지 않는다. 같은 대화의 Bash 둘이 동시에 끝나면 같은 내용을
    두 번 검사할 수 있다."""
    t0, sid = time.monotonic(), data.get("session_id")
    if not runlog.session_dir("handoff-seen", sid):
        return
    root = rules.repo_root(data["cwd"] if isinstance(data.get("cwd"), str) else None)
    if off("BATON_HANDOFF_CHECK", repo_of(root)):
        return
    path = os.path.join(root, "HANDOFF.md")
    try:
        mtime, text = os.stat(path).st_mtime, handoff_check.read(path)
    except OSError:
        return
    prev = seen(sid, path)
    if prev.get("sha") == text_sha(text):
        return
    ti = data.get("tool_input")
    said = isinstance(ti, dict) and isinstance(ti.get("command"), str) and bool(MENTION.search(ti["command"]))
    start = call_start(data.get("transcript_path"), data.get("tool_use_id")) if said else None
    if start is None and said and "sha" not in prev:
        start = session_start(data.get("transcript_path"))
        start = start if start is not None else float("inf")  # 대화 시작도 모르면 처음 본 파일은 기억만
    if not said or (start is not None and mtime < start):  # 말하지 않았거나, 이 호출(또는 대화) 전에 바뀐 파일 — 기억만
        remember(sid, path, text)
        return
    check_handoff(path, data, t0, text=text, bash=True)


def check_handoff(path, data, t0, text=None, bash=False):
    """HANDOFF.md 하나를 검사해 모델에게 돌려준다(막기·경고·통과 한 줄). 편집 도구(on_edit)와 Bash(on_bash)가 같이 쓴다.
    검사한 내용은 이 대화·이 파일의 기억에 남긴다(remember). bash면 쓰기를 본 것이 아니라 호출 뒤에 바뀐 것을 본 것이라 그대로 말하고
    (리뷰 11-26), 그 시각을 <해시>.bash_ts로 남긴다(Stop이 인계서 쓰기로 센다). 그 기억을 못 남기면 아무 말도 하지 않는다 — 한 번만이라는
    약속을 못 지키면 말하지 않는다(split.mark·version_notice와 같은 규칙)."""
    repo = repo_of(os.path.dirname(path) or None)
    if off("BATON_HANDOFF_CHECK", repo):
        return
    lang = i18n.lang(repo)
    t = handoff_check.tr(lang)
    terms = config.terms("private_terms", repo) if repo else []  # 저장소는 한 번만 찾는다 — check_file·빠진 줄 검사에 넘긴다
    try:
        text = handoff_check.read(path) if text is None else text
        problems = handoff_check.check_file(path, strict=False, text=text, lang=lang, terms=terms)
    except OSError:
        return
    sid = data.get("session_id")
    prev = seen(sid, path)
    if not remember(sid, path, text) and bash:
        return
    if bash:  # Stop이 인계서 쓰기로 센다(bash_write_ts). 못 남기면 그 시각만 빠진다
        write_state(seen_file(sid, path, ".bash_ts"), repr(time.time()))
    # 상한을 넘은 채 줄여 가는 편집(머리 주석): 직전 검사보다 짧아졌거나 이번 턴에 이미 크기로 막았으면 크기 문제만 경고로 낮춘다.
    # 비밀값·필수 절 같은 다른 문제는 그대로 막는다
    size = handoff_check.size_problems(text, lang, terms)
    sized, soft = [p for p in problems if p in size], []
    if sized:
        if isinstance(prev.get("chars"), int) and len(text) < prev["chars"]:
            soft = [t("경고(직전 검사보다 짧아져 막지 않음): ", "warning (shorter than at the last check, so not blocking): ") + p
                    for p in sized]
        elif not block_once(sid):
            soft = [t("경고(이번 턴에 이미 한 번 막아 다시 막지 않음): ", "warning (already blocked once this turn, so not blocking "
                      "again): ") + p for p in sized]
        problems = [p for p in problems if p not in sized] if soft else problems
    partial = False  # 경고 규칙·빠진 줄 검사가 오류로 못 돌았나 — 그러면 통과라고 하지 않는다
    try:
        warned = soft + handoff_check.warnings(text, strict=False, lang=lang)
    except Exception:
        warned, partial = soft, True  # 경고 규칙이 깨져도 막아야 할 문제는 그대로 돌려준다
    try:  # 남은 시간만 쓴다. 깨져도 나머지는 그대로
        deadline = min(time.monotonic() + handoff_check.DROP_BUDGET, t0 + HOOK_DEADLINE)
        if deadline - time.monotonic() > 0.2:
            warned += handoff_check.drop_warnings(path, text, lang, private_terms=terms, strict=False, deadline=deadline)
        elif handoff_check.looks_ours(text):  # 안 본 것을 "빠진 줄 없음"으로 읽지 않게
            warned.append(t("경고: 훅 시간이 모자라 빠진 줄 검사를 건너뛰었다 — 빠진 줄 0개가 아니라 안 봤다",
                            "warning: the dropped-lines check was skipped because the hook ran out of time — not zero "
                            "dropped lines, just not checked"))
    except Exception:
        partial = True
    note = t("[baton] HANDOFF.md 검사 일부를 돌리지 못했어요 — 검사기를 직접 돌려 주세요.",
             "[baton] Part of the HANDOFF.md check couldn't run — run the checker yourself.") if partial else ""
    if bash:  # 스킬 규칙을 한 번 더(도구 이름은 쓰지 않는다 — Codex의 편집 도구는 apply_patch다)
        note = "\n".join(x for x in (note, t("[baton] HANDOFF.md는 편집 도구로 고친다 — Bash로 쓰면 쓴 뒤에야 검사된다.",
                                              "[baton] Change HANDOFF.md with your file-editing tool; a Bash write is checked "
                                              "only afterwards.")) if x)
        head = t("[baton] 이 Bash 호출 뒤 HANDOFF.md가 바뀌어 있었다. ", "[baton] HANDOFF.md had changed after this Bash call. ")
        lead = (head + t("인계서 검사 문제가 있다. 고친 뒤 다시 저장한다:\n- ", "It has handoff-check problems. Fix them and save again:\n- "),
                head + t("검사 경고(막지 않음):\n- ", "Handoff-check warnings (not blocking):\n- "),
                head + t("검사 통과({n}줄·{c}자).", "Check passed ({n} lines, {c} chars)."))
    else:
        lead = (t("[baton] 방금 쓴 HANDOFF.md에 인계서 검사 문제가 있다. 고친 뒤 다시 저장한다:\n- ",
                  "[baton] The HANDOFF.md you just wrote has handoff-check problems. Fix them and save again:\n- "),
                t("[baton] 방금 쓴 HANDOFF.md 검사 경고(막지 않음):\n- ",
                  "[baton] Handoff-check warnings for the HANDOFF.md you just wrote (not blocking):\n- "),
                t("[baton] HANDOFF.md 검사 통과({n}줄·{c}자).", "[baton] HANDOFF.md check passed ({n} lines, {c} chars)."))
    event = data.get("hook_event_name") if data.get("hook_event_name") in BASH_EVENTS else "PostToolUse"  # 출력은 받은 이벤트 이름으로
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": "handoff_check",
           "session_id": data.get("session_id"), "problems": len(problems), "warnings": len(warned)}
    rec.update({"tool": "Bash"} if bash else {}, **({"softened": len(soft)} if soft else {}),
               **({"failed_call": True} if event == "PostToolUseFailure" else {}))
    runlog.append(rec)
    if problems:
        reason = lead[0] + "\n- ".join(problems + warned) + ("\n" + note if note else "")
        print(json.dumps({"decision": "block", "reason": capped(reason, t)}, ensure_ascii=False))
    elif warned:  # 경고만이면 막지 않는다 — 맥락에 알리기만 한다(Codex도 이 JSON 모양만 받는다)
        ctx = lead[1] + "\n- ".join(warned) + ("\n" + note if note else "")
        print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": capped(ctx, t)}},
                         ensure_ascii=False))
    else:  # 통과도 한 줄로 알린다(머리 주석). 못 돈 검사가 있으면 통과라고 하지 않는다
        ctx = lead[2].format(n=len(text.splitlines()), c=f"{len(text):,}") if not partial else ""
        ctx = "\n".join(x for x in (ctx, note) if x)
        print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": ctx}}, ensure_ascii=False))

def capped(text, t):
    """OUT_MAX자를 넘으면 자르고 잘랐다고 한 줄 붙인다. 나머지는 검사기를 직접 돌려 본다."""
    if len(text) <= OUT_MAX:
        return text
    note = t("\n[baton] 검사 결과가 길어 잘랐다 — 전체는 python3 lib/handoff_check.py HANDOFF.md",
             "\n[baton] The check output was too long and was cut — run python3 lib/handoff_check.py HANDOFF.md for all of it")
    return text[:OUT_MAX - len(note)] + note


def tool_blocks(d):
    """기록 줄 하나(dict)의 tool_use (이름, 입력, id) — type이 "assistant"인 줄에서만. api-request-blob처럼 앞선 호출을 다시 담은
    줄은 세지 않는다(리뷰 11-25: 인계서 뒤의 blob이 옛 Agent·Edit 호출을 다시 세어 질문만 한 턴을 막았다, 실제 세션 60개 중 1개)."""
    m = d.get("message")
    content = m.get("content") if d.get("type") == "assistant" and isinstance(m, dict) else None
    for b in content if isinstance(content, list) else ():
        if isinstance(b, dict) and b.get("type") == "tool_use":
            yield b.get("name"), b.get("input") if isinstance(b.get("input"), dict) else {}, b.get("id")


MACHINE_ORIGINS = ("peer", "task-notification")  # 기록 줄의 origin.kind — 다른 세션 메시지·작업 알림(isMeta여도 턴을 연다)
TOOL_USE_ID = re.compile(r"<tool-use-id>\s*([\w-]+)\s*</tool-use-id>")  # 끝난 뒤 작업의 알림이 담는 그 작업의 tool_use id


def transcript_events(path):
    """세션 기록을 한 번 읽는다 — ("tool", 사이드체인인가, 이름, 입력, tool_use id, 시각), ("agent", tool_use id, agentId, 시각),
    ("prompt", 알림이 가리키는 tool_use id들, 시각). 시각은 그 줄의 timestamp(초) 또는 None. tool_use는 assistant 줄에서만, 결과(tool_result)는
    user 줄에서만 본다. agentId는 Agent·Task 결과 줄의 toolUseResult에 있고, 그 서브에이전트 기록은 <세션>/subagents/agent-<agentId>.jsonl이다.
    "prompt"는 메인 스레드에서 턴을 여는 줄이다(candidates.human_text와 같은 규칙: 글이거나 text 블록만, 압축 요약·사이드체인 줄은 아님).
    메타 줄(Stop 훅 피드백 등)은 턴을 열지 않는다 — 단 origin.kind가 다른 세션 메시지(peer)·작업 알림(task-notification)이면 연다.
    그런 줄과 본문이 <task-notification>·<agent-message>로 시작하는 줄(rules.machine_prompt)이면 본문의 <tool-use-id>를 함께 낸다
    (사람이 친 프롬프트는 빈 묶음)."""
    from candidates import human_text, when
    with open(path, encoding="utf-8", errors="ignore") as f:
        for ln in f:
            if '"tool_use"' not in ln and '"agentId"' not in ln and ('"user"' not in ln or '"tool_result"' in ln):
                continue
            try:
                d = json.loads(ln)
            except ValueError:
                continue
            if not isinstance(d, dict) or not isinstance(d.get("message"), dict):
                continue
            ts = when(d.get("timestamp"))
            ts = ts.timestamp() if ts else None
            content, tur = d["message"].get("content"), d.get("toolUseResult")
            origin = d["origin"].get("kind") if isinstance(d.get("origin"), dict) else None
            text = human_text(content) if d.get("type") == "user" else None
            if text is not None and not (d.get("isSidechain") or d.get("isCompactSummary")) \
                    and (not d.get("isMeta") or origin in MACHINE_ORIGINS):
                machine = origin in MACHINE_ORIGINS or rules.machine_prompt(text)
                yield "prompt", tuple(TOOL_USE_ID.findall(text)) if machine else (), ts
                continue
            for name, inp, tid in tool_blocks(d):
                yield "tool", bool(d.get("isSidechain")), name, inp, tid, ts
            if d.get("type") == "user" and isinstance(content, list) and isinstance(tur, dict) and isinstance(tur.get("agentId"), str):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        yield "agent", b.get("tool_use_id"), tur["agentId"], ts


def with_handoff_mark(events, written):
    """events에 ("handoff",)를 한 번 끼운다 — written(초)보다 늦은 첫 이벤트 앞에, 그런 이벤트가 없으면 끝에. 시각이 있는 이벤트가
    하나도 없으면(옛 형식·시각 없는 기록) 끼우지 않는다. written은 저장 검사가 "handoff를 말한 Bash 호출 뒤 HANDOFF.md가 바뀌었다"고
    검사한 시각(bash_write_ts, check_handoff)이다 — 기록에 안 보이는 인계서 쓰기(Bash 안 python heredoc 등, 11-25 실사용: 그렇게 쓰고
    커밋한 턴 끝에 다시 "인계서 써라"가 나왔다)를 그때 쓴 것으로 친다. 파일 mtime은 쓰지 않는다 — git checkout·stash pop·다른 창의
    쓰기가 대화에 한 번뿐인 파일 수 제안을 가렸다(리뷰 11-26). ponytail: 한 메시지의 병렬 호출은 같은 시각이라 인계서 쓰기 앞으로 센다."""
    timed = False
    for ev in events:
        if written is not None and ev[-1] is not None:
            if ev[-1] > written:
                yield ("handoff",)
                written = None
            else:
                timed = True
        yield ev
    if written is not None and timed:
        yield ("handoff",)


def tool_uses(path, sidechain=False):
    """메인 스레드(sidechain=False) 또는 서브에이전트 줄(True)의 tool_use (이름, 입력), 순서대로. 모양이 다른 줄은 건너뛴다."""
    for ev in transcript_events(path):
        if ev[0] == "tool" and ev[1] == sidechain:
            yield ev[2], ev[3]


def edit_paths(path):
    """이 세션의 메인 스레드가 편집 도구로 고친 파일 경로, 순서대로. /baton-setup 스캐너도 쓴다."""
    for name, inp in tool_uses(path):
        fp = inp.get("file_path") or inp.get("notebook_path")
        if name in EDIT_TOOLS and isinstance(fp, str):
            yield fp


AGENT_TOOLS = {"Agent", "Task"}
# 서브에이전트 기록을 못 찾을 때 일로 세지 않는 종류 — 읽기만 하는 것들(리뷰 11-25: 질문만 한 턴의 Explore가 막았다)
READ_ONLY_AGENTS = {"explore", "plan", "claude-code-guide", "web-fetch"}
READ_ONLY_WORDS = ("explore", "review", "verif", "critic", "architect", "analyst", "scientist", "document-specialist", "planner", "tracer")
WORK_BUDGET = 4.0  # 넘길 일 세기의 시한(초). Stop 훅 시한은 10초 — 넘으면 편집 도구만 센다
CMD_SCAN = 16384  # Bash 명령 하나에서 보는 글자 수. 넘으면 앞뒤 8KB만(붙여 넣은 긴 글·긴 heredoc)
HEREDOC_OPEN = re.compile(r"(?<!<)<<(?!<)-?[ \t]*['\"]?(\w+)['\"]?")
QUOTED = re.compile(r"'[^']*'|\"(?:[^\"\\]|\\.)*\"")
PLAIN = re.compile(r"[\w./${}~+-]*")  # 따옴표 안이 경로처럼 생겼으면 남긴다("HANDOFF.md") — 아니면 지운다('$1>3')
TESTS = re.compile(r"\(\([^()\n]*\)\)|\[\[[^\n]*?\]\]")  # (( a > b )) · [[ a > b ]]의 >는 리다이렉트가 아니다
REDIR = re.compile(r"(\d*|&)(>>?\|?)(?!&)[ \t]*([^\s;|&<>()]*)")
SEGMENT = re.compile(r"\|\||&&|[;|&\n()]")
WRAPPERS = {"sudo", "env", "xargs", "time", "nice", "nohup", "command", "exec", "rtk", "proxy"}
SCRATCH = ("/dev/", "/tmp/", "/private/tmp/", "/var/folders/", "/private/var/folders/", "$TMPDIR", "${TMPDIR}")
HANDOFF_FILE = re.compile(r"HANDOFF(?:[_-][^/]+)?\.md")


def strip_heredocs(cmd):
    """heredoc 본문 줄을 뺀다 — 여는 줄에서 끝말을 모아, 그 끝말과 같은 줄까지 건너뛴다(줄 단위 한 번, 정규식 되돌이 없음)."""
    out, ends = [], []
    for line in cmd.split("\n"):
        if ends:
            if line.strip() == ends[0]:
                ends.pop(0)
            continue
        out.append(line)
        ends = HEREDOC_OPEN.findall(line)
    return "\n".join(out)


def bash_writes(cmd):
    """Bash 명령 하나가 (파일을 쓰는가, 인계서를 쓰는가). heredoc 본문을 빼고, 경로처럼 생기지 않은 따옴표 안과 (( ))·[[ ]]를 지우고 본다.
    세는 것: 명령 자리의 sed -i·--in-place, tee 대상, cp·mv·git mv의 마지막 인자, 표준 출력 리다이렉트(>, >>, >|, 1>, &>)의 대상.
    대상이 임시 폴더·/dev·$TMPDIR면 일로 안 센다. 대상 파일 이름이 HANDOFF.md·HANDOFF_*.md면 인계서 쓰기(다른 쓰기보다 앞선다).
    ponytail: 셸을 다 읽지는 않는다 — python·node 같은 스크립트 안의 쓰기, 변수로 된 경로, rm·touch·patch·git apply·checkout,
    붙은 숫자(a2>b의 2를 fd로 읽음), 16KB 넘는 명령의 가운데, 값을 받는 감싸개 옵션(sudo -u 이름 cp …, timeout 10 cp …의 값을
    명령으로 읽음), git -C 폴더 mv(mv가 바로 뒤에 와야 한다)는 못 본다. 그런 일만 한 턴은 넘길 일이 없다고 본다."""
    if len(cmd) > CMD_SCAN:
        cmd = cmd[:CMD_SCAN // 2] + "\n" + cmd[-CMD_SCAN // 2:]
    flat = TESTS.sub(" ", QUOTED.sub(lambda m: m.group(0)[1:-1] if PLAIN.fullmatch(m.group(0)[1:-1]) else "''",
                                     strip_heredocs(cmd)))
    hit = {"write": False, "handoff": False}

    def target(t):
        if t and not t.startswith(SCRATCH):
            hit["handoff" if HANDOFF_FILE.fullmatch(os.path.basename(t)) else "write"] = True

    for m in REDIR.finditer(flat):
        if m.group(1) in ("", "1", "&"):  # 2> 같은 다른 fd는 오류 기록이라 세지 않는다
            target(m.group(3))
    for seg in SEGMENT.split(flat):
        words = seg.split()
        i = 0
        while i < len(words) and (re.match(r"\w+=", words[i]) or words[i] in WRAPPERS or (i and words[i].startswith("-"))):
            i += 1
        if i >= len(words):
            continue
        cmd_word, args = os.path.basename(words[i]), [w for w in words[i + 1:] if not w.startswith("-")]
        if cmd_word == "git" and args[:1] == ["mv"]:
            cmd_word, args = "mv", args[1:]
        if cmd_word == "sed" and any(re.match(r"-[A-Za-z]*i", w) or w.startswith("--in-place") for w in words[i + 1:]):
            hit["write"] = True
            for a in args:
                if HANDOFF_FILE.fullmatch(os.path.basename(a)):
                    target(a)
        elif cmd_word == "tee":
            for a in args:
                target(a)
        elif cmd_word in ("cp", "mv") and len(args) >= 2:
            target(args[-1])
    return hit["write"] or hit["handoff"], hit["handoff"]


def call_kind(name, inp):
    """도구 호출 하나 → (인계서 말고 파일을 고쳤나, 인계서를 썼나)."""
    if name == "Bash" and isinstance(inp.get("command"), str):
        writes, handoff = bash_writes(inp["command"])
        return writes and not handoff, handoff
    fp = inp.get("file_path") or inp.get("notebook_path")
    if name in EDIT_TOOLS and isinstance(fp, str):
        return not wrote_handoff(fp), wrote_handoff(fp)
    return False, False


def read_only_agent(kind):
    """서브에이전트 종류가 읽기만 하는 쪽인가(Explore·Plan·…, 이름에 explore·review·verif 등)."""
    k = (kind or "").lower()
    return k.rsplit(":", 1)[-1] in READ_ONLY_AGENTS or any(w in k for w in READ_ONLY_WORDS)


def subagent_writes(sub, deadline=None):
    """서브에이전트 기록에 파일 쓰기가 있나: True·False, 시한을 넘기면 "late", 못 읽거나 읽히는 줄이 하나도 없으면(깨진 기록) None."""
    readable = False
    try:
        with open(sub, encoding="utf-8", errors="ignore") as f:
            for ln in f:
                if deadline is not None and time.monotonic() > deadline:
                    return "late"
                try:
                    d = json.loads(ln)
                except ValueError:
                    continue
                if not isinstance(d, dict):
                    continue
                readable = True
                if any(any(call_kind(name, inp)) for name, inp, _ in tool_blocks(d)):
                    return True
    except OSError:
        return None
    return False if readable else None


def subagent_file(path, agent_id):
    """메인 기록 옆의 서브에이전트 기록 경로(없거나 id가 이상하면 None)."""
    if not (isinstance(agent_id, str) and re.fullmatch(r"[\w-]{1,64}", agent_id)):
        return None
    p = os.path.join(os.path.splitext(path)[0], "subagents", f"agent-{agent_id}.jsonl")
    return p if os.path.isfile(p) else None


def work_since_handoff(path, deadline=None, written=None):
    """맥락 까닭의 "넘길 일": 이번 턴에, 이 세션이 마지막으로 인계서를 쓴 뒤 고친 것(라벨 목록). deadline(monotonic)을 넘기면 None.
    인계서 쓰기(편집 도구·Bash·written — with_handoff_mark)와 턴을 여는 프롬프트(소유자 결정 11-26)에서 처음부터 센다.
    - 메인 스레드: 편집 도구로 고친 파일, 파일을 쓰는 Bash 명령(bash_writes).
    - Agent·Task 호출: 그 서브에이전트가 실제로 고쳤을 때만 — 기록(<세션>/subagents/agent-<id>.jsonl)에 편집이나 쓰기가 있나 본다.
      ponytail: 기록을 못 찾거나 깨졌으면(결과가 아직 없음·옛 형식·읽히는 줄 0개) 메인 기록의 사이드체인 줄에 쓰기가 있으면 일로 세고, 없으면 종류로 가른다 —
      읽기만 하는 종류(read_only_agent)는 안 세고 나머지는 센다. 서브에이전트가 또 맡긴 일은 따라가지 않는다.
      뒤에서 도는 위임(run_in_background)은 그 위임의 tool_use id를 <tool-use-id>에 담은 작업 알림이 연 턴에서 한 번 다시 본다.
      인계서를 쓰면 기다리던 위임도 넘긴 것으로 친다. ponytail: <tool-use-id>가 없는 알림 형식이면 뒤 위임의 일은 세지 못한다."""
    work, agents, side, ids, background = [], [], False, {}, {}
    for ev in with_handoff_mark(transcript_events(path), written):
        if deadline is not None and time.monotonic() > deadline:
            return None
        if ev[0] == "prompt":
            # 턴이 바뀌었다. 작업 알림이 연 턴이면 그 알림의 <tool-use-id>가 가리키는 뒤 위임(run_in_background)만 이 턴에 다시 보고 기다림에서
            # 뺀다 — 그 일이 끝났다고 알리는 턴이다(리뷰 11-26: 알림 턴에서 서브에이전트가 고친 것을 버렸다, 1.0.1은 셌다. 다른 알림·다른 세션
            # 메시지는 위임을 다시 불러오지 않는다)
            work, side = [], False
            agents = [(t, background.pop(t)) for t in ev[1] if t in background]
            continue
        if ev[0] == "handoff":
            work, agents, side = [], [], False
            background.clear()  # 인계서를 쓰면 그 앞의 위임은 넘긴 것으로 친다(리뷰 11-26)
            continue
        if ev[0] == "agent":
            ids[ev[1]] = ev[2]
            continue
        _, sidechain, name, inp, tid, _ = ev
        writes, handoff = call_kind(name, inp)
        if sidechain:
            side = side or writes or handoff  # 옛 형식: 서브에이전트 줄이 메인 기록에 섞여 있다
        elif handoff:
            work, agents, side = [], [], False
            background.clear()
        elif writes:
            work.append(inp.get("file_path") or inp.get("notebook_path") or "Bash")
        elif name in AGENT_TOOLS:
            agents.append((tid, inp.get("subagent_type")))
            if inp.get("run_in_background") is True:
                background[tid] = inp.get("subagent_type")
    if work:
        return work
    for tid, kind in agents:
        sub = subagent_file(path, ids.get(tid))
        wrote = subagent_writes(sub, deadline) if sub else None
        if wrote == "late":
            return None
        if wrote or (wrote is None and (side or not read_only_agent(kind))):
            return [kind or "agent"]
    return []


def edited_since_handoff(path, bash=True, written=None, turn=False):
    """이 세션이 마지막으로 인계서(HANDOFF.md 또는 이름 붙은 인계서)를 쓴 뒤 편집 도구로 고친 다른 파일들(파일 수 까닭 F).
    bash면 Bash로 인계서에 쓴 것도 인계서 쓰기로 보고 처음부터 센다(리뷰 11-25) — 세는 것은 그대로 편집 도구의 파일만.
    written(Bash로 쓴 인계서를 검사한 시각)이 있으면 그 시각에도 인계서를 쓴 것으로 친다(with_handoff_mark). turn이면 사람 프롬프트에서도 처음부터
    센다 — 맥락 까닭이 시한을 넘겨 이것으로 떨어질 때(이번 턴에 한 일만)."""
    files = set()
    for ev in with_handoff_mark(transcript_events(path), written):
        if ev[0] == "handoff" or (turn and ev[0] == "prompt"):
            files.clear()
            continue
        if ev[0] != "tool" or ev[1]:  # 메인 스레드의 도구 호출만
            continue
        name, inp = ev[2], ev[3]
        fp = inp.get("file_path") or inp.get("notebook_path")
        if name in EDIT_TOOLS and isinstance(fp, str):
            if wrote_handoff(fp):
                files.clear()
            else:
                files.add(os.path.normpath(fp))
        elif bash and name == "Bash" and isinstance(inp.get("command"), str) and bash_writes(inp["command"])[1]:
            files.clear()
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
    """모델에게 돌려줄 자동 쓰기 요청. files: 인계서 뒤에 고친 파일(없으면 빈 목록),
    grown: 맥락이 넘은 문턱 (문턱, 첫, 마지막, 배수 규칙인가 — split.crossed_band) 또는 None.
    두 까닭이 겹치면 한 요청에 같이 적는다. 스킬 경로는 플러그인 위치로 적는다.
    검사기를 돌리라고 하지 않는다 — Claude Code에서는 저장 훅이 같은 검사를 돌리고(자동 쓰기는 Claude Code에서만 나간다),
    따옴표 친 절대 경로 명령은 스킬의 allowed-tools와 맞지 않아 중간에 권한 확인이 뜬다(리뷰 11-23)."""
    split = split_mod()  # grown이 있을 때만 쓴다(그때는 on_stop이 이미 불러 왔다)
    skill = os.path.join(PLUGIN, "skills", "baton", "SKILL.md")
    why = []
    if lang == "ko":
        if files:
            why.append(f"이 세션에서 인계서(HANDOFF.md·HANDOFF_*.md)를 마지막으로 쓴 뒤 파일 {len(files)}개를 고쳤다: "
                       f"{file_list(files, cwd, lang)}.")
        if grown:
            band, first, last, by_ratio = grown
            why.append(f"이 대화의 맥락이 처음보다 {band:g}배 넘게 커졌다({split.man(first)} → {split.man(last)} 토큰)." if by_ratio else
                       f"이 대화의 맥락이 {split.band_label(lang, band)}을 넘었다({split.man(first)} → {split.man(last)} 토큰)."
                       + (" 만든 사람의 기록으로 계산하면, 이 크기부터는 이어 가는 것보다 인계서를 쓰고 새 대화로 넘기는 쪽이 대개 더 싸다."
                          if split.claims_cheaper(band, by_ratio) else ""))
        line = split.user_line(lang, grown[0], grown[3]) if grown else "인계서를 고쳐 뒀어요. 이 기능을 끄려면 BATON_HANDOFF_AUTO=off로 설정하세요."
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
        band, first, last, by_ratio = grown
        why.append(f"This conversation's context is now more than {band:g}× its size at the start "
                   f"({first // 1000}K → {last // 1000}K tokens)." if by_ratio else
                   f"This conversation's context passed {split.band_label(lang, band)} ({first // 1000}K → {last // 1000}K tokens)."
                   + (" By a recount of the author's sessions, from this size on, writing a handoff and moving to a new "
                      "conversation is usually cheaper than continuing." if split.claims_cheaper(band, by_ratio) else ""))
    line = split.user_line(lang, grown[0], grown[3]) if grown else "I updated the handoff. To turn this off, set BATON_HANDOFF_AUTO=off."
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
    물을 수 있으면(BATON_HANDOFF_AUTO 켬, HANDOFF.md가 없거나 baton 형식) decision "block" 하나에 두 까닭을 같이 적는다.
    못 물으면 사용자에게 systemMessage 하나로 알린다. 다른 Stop 훅이 턴을 잇는 중(stop_hook_active)이면 묻지도 알리지도 않고 상태도 남기지 않는다 — 다음 턴 끝에 다시 본다. 상태는 까닭마다 따로
    (F: 세션에 한 번 handoff-nudge/<sid>, S: 문턱마다 한 번 split/<sid>.json). S는 이번 턴에, 마지막 인계서 뒤에 넘길 일이 있을 때만 본다.
    크기 막기 표지(block_once)는 여기서 지운다 — 크기로 막는 것은 턴에 한 번."""
    p = blocked_file(data.get("session_id"))
    if p and os.path.exists(p):
        try:
            os.remove(p)
        except OSError:
            pass
    prune_seen()
    cwd = data["cwd"] if isinstance(data.get("cwd"), str) else None
    repo = repo_of(cwd)
    split = split_mod() if not off("BATON_SPLIT_NOTICE", repo) else None
    nudge_on, split_on = not off("BATON_HANDOFF_NUDGE", repo), split is not None
    if not (nudge_on or split_on):
        return
    auto = not off("BATON_HANDOFF_AUTO", repo)
    path, sid = data.get("transcript_path"), data.get("session_id")
    if not isinstance(path, str) or not os.path.isfile(path) or not isinstance(sid, str) or not re.fullmatch(r"[\w-]{1,128}", sid):
        return  # sid는 상태 파일 이름이 된다 — 경로 문자가 섞인 값은 받지 않는다
    state = os.path.join(runlog.cache_dir(), "handoff-nudge", sid)
    written = bash_write_ts(sid, cwd)  # 기록에 안 보이는 인계서 쓰기(Bash 안 python 등)도 쓴 것으로 — with_handoff_mark
    files = []
    if nudge_on and not os.path.exists(state):  # F는 세션에 한 번(제안이든 자동 쓰기든)
        try:
            need = max(1, int(config.get("BATON_HANDOFF_NUDGE_FILES", repo, "3")))
        except ValueError:
            need = 3
        try:
            files = sorted(edited_since_handoff(path, written=written))
        except Exception:
            files = []  # 제안 하나 때문에 턴 끝이 오류로 끝나면 안 된다
        files = files if len(files) >= need else []
    grown = None
    if split_on:
        # 맥락 까닭은 이번 턴에, 마지막 인계서 쓰기 뒤에 넘길 일이 있을 때만 — 없으면 문턱도 남기지 않아(아래 mark를 건너뜀) 나중에 일한
        # Stop에서 그 문턱을 한 번 묻는다(11-25 실사용: 질문만 한 턴 뒤에 인계서를 다시 쓰게 해 소유자가 불편했다 · 소유자 결정 11-26:
        # 질문·읽기만 한 턴은 앞선 턴에 한 일이 있어도 막지 않는다). 이번 턴에 인계서를 썼어도 그 뒤에 일했으면 묻는다 — 예전의
        # "이번 턴에 썼으면 알리기만"(fresh)은 뺐다(리뷰 11-25)
        try:
            work = work_since_handoff(path, time.monotonic() + WORK_BUDGET, written)
            if work is None:  # 시한을 넘겼다(아주 긴 기록) — 편집 도구만 센다. 훅이 시한에 죽으면 두 까닭이 다 사라진다
                work = edited_since_handoff(path, bash=False, written=written, turn=True)
            grown = split.crossed_band(path, repo, sid) if work else None
        except Exception:
            grown = None
    if not files and not grown:
        return
    if auto and data.get("stop_hook_active") is True:
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
    foreign = auto and not ours_or_absent(cwd)
    ask = auto and not foreign  # active는 위에서 돌아갔다(auto일 때)
    ts = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    if ask:
        print(json.dumps({"decision": "block", "reason": auto_reason(files, cwd, lang, grown)}, ensure_ascii=False))
    else:
        msgs = ([split.notice(lang, *grown)] if grown else []) \
            + ([nudge_message(len(files), lang)] if files else [])
        print(json.dumps({"systemMessage": "\n\n".join(msgs)}, ensure_ascii=False))
    if files:
        rec = {"ts": ts, "event": "handoff_auto" if ask else "handoff_nudge", "session_id": sid, "files": len(files)}
        if foreign:
            rec["fallback"] = "foreign_handoff"  # 자동 쓰기 대신 제안한 까닭
        runlog.append(rec)
    if grown:
        rec = {"ts": ts, "event": "split_notice", "session_id": sid, "first_ctx": grown[1], "last_ctx": grown[2],
               "ratio": round(grown[2] / grown[1], 2), "band": grown[0], "mode": "ask" if ask else "notice"}
        if foreign:
            rec["fallback"] = "foreign_handoff"
        runlog.append(rec)


def bash_write_ts(sid, cwd):
    """저장소 루트 HANDOFF.md를 Bash로 쓴 것을 저장 검사가 마지막으로 검사한 시각(초, check_handoff가 <해시>.bash_ts에 남긴다). 없으면 None."""
    try:
        with open(seen_file(sid, os.path.join(rules.repo_root(cwd), "HANDOFF.md"), ".bash_ts"), encoding="utf-8") as f:
            return float(f.read())
    except (OSError, TypeError, ValueError):
        return None


def ours_or_absent(cwd):
    """저장소 루트에 HANDOFF.md가 없거나 baton 형식인가. 못 읽으면 False — 모르는 파일을 다시 쓰게 하지 않는 쪽."""
    try:
        path = os.path.join(rules.repo_root(cwd), "HANDOFF.md")
        return not os.path.isfile(path) or handoff_check.looks_ours(handoff_check.read(path))
    except Exception:
        return False


def main(data):
    if not isinstance(data, dict):
        return
    event = data.get("hook_event_name")
    try:
        if event in BASH_EVENTS and data.get("tool_name") == "Bash":
            on_bash(data)
        elif event == "PostToolUse":
            on_edit(data)
        elif event == "Stop":
            on_stop(data)
    except Exception:
        return  # 검사·제안 때문에 도구 호출이나 턴이 오류로 끝나면 안 된다


if __name__ == "__main__":
    main(DATA)
