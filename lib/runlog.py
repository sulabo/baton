"""관찰 로그 한 줄 쓰기 — 훅들이 공유한다. 실패는 조용히 넘긴다(로그 때문에 훅 동작이 바뀌면 안 된다).

위치: BATON_LOG, 없으면 ~/.cache/baton/runs.jsonl. 저장소마다 .baton/을 만들지 않으려고 사용자 캐시 한 곳에 쓴다(정본 43절과 다름).
저장소 경로·개념 이름이 담기므로 폴더 700·파일 600. 끄기: BATON_OBSERVE=off.
두 값은 환경변수 또는 설정 파일의 전역 절에서 읽는다(lib/config.py — 저장소 절은 안 본다).
"""
import json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

LOG_MAX = 20 * 1024 * 1024
SID = re.compile(r"[\w-]{1,128}")  # 세션 id — 상태 폴더 이름이 된다. 경로 문자가 섞인 값은 받지 않는다


def cache_dir():
    return os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "baton")


def session_dir(kind, sid):
    """캐시 아래 대화별 상태 폴더 <캐시>/baton/<kind>/<sid>. sid가 폴더 이름이 될 수 없으면 None. 훅 둘이 같은 자리를 보게 한 곳에서 정한다
    (handoff-seen: hooks/handoff-check.py가 쓰고, 사람 프롬프트마다 hooks/handoff-inject.py가 크기 막기 표지를 지운다)."""
    return os.path.join(cache_dir(), kind, sid) if isinstance(sid, str) and SID.fullmatch(sid) else None


def append(rec):
    try:
        import config  # 여기서만 부른다 — Bash 뒤마다 도는 훅의 빠른 길(hooks/handoff-check.py)이 설정 모듈을 불러오지 않게
        if config.get("BATON_OBSERVE").strip().lower() in ("off", "0", "false", "no"):
            return
        path = os.path.expanduser(config.get("BATON_LOG")) or os.path.join(cache_dir(), "runs.jsonl")  # "~/…"가 지금 폴더 안 ~/에 생기지 않게
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        # ponytail: 크기 상한만 둔다(LOG_MAX 넘으면 .1로 한 번 돌림). 기간별 보존이 필요해지면 날짜별 파일로 바꾼다
        if os.path.exists(path) and os.path.getsize(path) > LOG_MAX:
            os.replace(path, path + ".1")
        fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass
