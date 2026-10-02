#!/usr/bin/env python3
# Stop 훅 — 북극성 길 단계 S "세션 끊기". 턴이 끝날 때 이 세션의 호출당 맥락이 시작의 몇 배인지 보고,
# 문턱(기본 2배·3배)을 처음 넘을 때 한 번씩만 사용자에게 "여기서 넘기면 싸다"고 알린다. 넘길지는 사람이 정한다.
#
# 왜 (docs/research/LOOP_PLAN.md "토큰이 어디로 가나"·"세션 끊기 재계산", 2026-09-30):
#  - 실사용 세션 60개에서 비용의 85%(비용 가중)가 맥락이 첫 호출의 2배를 넘은 뒤에 나갔다. 초반 5호출은 2.8%.
#  - 2배에서 인계서로 새 세션을 열었다면 비용 약 35~45% 절감(재계산 추정 — 실측 아님).
#  - 인계서로 새로 시작한 실제 세션은 초반에 다른 세션보다 약 5~9K 토큰만 더 읽었다.
# 정본 8절은 "Handoff는 컨텍스트 크기 때문에 발생하지 않는다"고 했다 — 소유자 결정(09-30)으로 크기를 "권고"로만 더한다.
#
# 알림은 사용자에게만 보인다(systemMessage). 모델의 행동은 바꾸지 않는다. 매번 울리는 알람은 무시당하므로 문턱마다 한 번.
# 끄기: BATON_SPLIT_NOTICE=off · 문턱: BATON_SPLIT_RATIOS="2,3"
#   환경변수 또는 설정 파일(lib/config.py, /baton-setup이 사용자 세션 분포로 문턱을 제안해 쓴다)에서 읽는다.
import json, os, re, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import config, rules, runlog

TOKEN_KEYS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
TAIL_BYTES = 512 * 1024


def ctx_of(line):
    """메인 스레드 assistant 줄이면 맥락 토큰, 아니면 None. 모양이 다른 줄은 None(기록 형식이 바뀌어도 훅이 죽지 않게)."""
    if '"assistant"' not in line:
        return None
    try:
        d = json.loads(line)
    except ValueError:
        return None
    if not isinstance(d, dict) or d.get("type") != "assistant" or d.get("isSidechain"):
        return None
    m = d.get("message")
    if not isinstance(m, dict) or m.get("model") == "<synthetic>":
        return None
    u = m.get("usage")
    if not isinstance(u, dict):
        return None
    try:
        return sum(int(u.get(k) or 0) for k in TOKEN_KEYS)
    except (TypeError, ValueError):
        return None


def first_and_last(path):
    """(첫 호출 맥락, 마지막 호출 맥락). 앞은 첫 assistant까지만, 뒤는 끝 512KB만 읽는다."""
    first = last = None
    with open(path, encoding="utf-8", errors="ignore") as f:
        for ln in f:
            r = ctx_of(ln)
            if r:
                first = r; break
        size = os.fstat(f.fileno()).st_size
        f.seek(max(size - TAIL_BYTES, 0))
        if size > TAIL_BYTES:
            f.readline()  # 잘린 줄 버림
        for ln in f:
            r = ctx_of(ln)
            if r:
                last = r
    return first, last


def ratios(repo):
    try:
        return sorted(float(x) for x in config.get("BATON_SPLIT_RATIOS", repo, "2,3").split(",") if x.strip())
    except ValueError:
        return [2.0, 3.0]


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    if not isinstance(data, dict):
        return
    # 설정 파일이 없으면 저장소 루트를 찾으러 git을 부르지 않는다(Codex 훅에는 CLAUDE_PROJECT_DIR가 없다)
    repo = rules.repo_root(data["cwd"] if isinstance(data.get("cwd"), str) else None) if config.load() is not None else None
    if config.get("BATON_SPLIT_NOTICE", repo).strip().lower() in ("off", "0", "false", "no"):
        return
    path, sid = data.get("transcript_path"), data.get("session_id")
    if not isinstance(path, str) or not os.path.isfile(path) or not isinstance(sid, str) or not re.fullmatch(r"[\w-]{1,128}", sid):
        return  # sid는 상태 파일 이름이 된다 — 경로 문자가 섞인 값은 받지 않는다
    try:
        first, last = first_and_last(path)
    except Exception:
        return  # 알림 하나 때문에 턴 끝이 오류로 끝나면 안 된다
    if not first or not last:
        return
    r = last / first
    crossed = [x for x in ratios(repo) if r >= x]
    if not crossed:
        return
    band = crossed[-1]
    # ponytail: 세션마다 작은 상태 파일이 하나씩 쌓인다(정리 안 함). 많아지면 오래된 것부터 지우는 정리를 더한다
    state = os.path.join(runlog.cache_dir(), "split", f"{sid}.json")
    try:
        with open(state, encoding="utf-8") as f:
            done = set(json.load(f))
    except (OSError, ValueError, TypeError):
        done = set()
    if band in done:
        return
    try:
        os.makedirs(os.path.dirname(state), mode=0o700, exist_ok=True)
        with open(state, "w", encoding="utf-8") as f:
            json.dump(sorted(done | {band}), f)
    except OSError:
        return  # 한 번만 알린다는 약속을 못 지키면 아예 알리지 않는다
    msg = (f"[baton] 이 세션은 호출당 맥락이 {last // 1000}K — 시작({first // 1000}K)의 {r:.1f}배다. "
           f"지금 작업 덩어리가 끝났다면 인계서를 쓰고 /clear 뒤 '이어서'로 넘기면 다음 호출부터 다시 약 {first // 1000}K에서 시작한다 "
           f"(재계산 추정: 2배에서 끊는 세션은 비용 약 35~45%, 3배면 약 30~34% 절감). "
           f"넘기지 않아도 된다 — 이 알림은 {band:g}배에서 한 번만 나온다.")
    print(json.dumps({"systemMessage": msg}, ensure_ascii=False))
    runlog.append({"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": "split_notice", "session_id": sid,
                   "first_ctx": first, "last_ctx": last, "ratio": round(r, 2), "band": band})


if __name__ == "__main__":
    main()
