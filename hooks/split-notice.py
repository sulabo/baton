#!/usr/bin/env python3
# 북극성 길 단계 S "세션 끊기" — 이 세션의 호출당 맥락이 시작의 몇 배인지 재는 도구와 알림 문장.
# 2026-11-24부터 Stop 결정은 hooks/handoff-check.py on_stop 한 곳에서 한다(파일 고침 자동 쓰기와 같은 규칙 — 한 Stop이 두 번 묻지
# 않게). 문턱(기본 2배·3배)을 처음 넘으면 모델이 인계서를 남기고 사용자에게 한 줄로 알린다(소유자 결정 11-24: "우리가 강제로
# compact를 하는 건 취지에 안 맞아" — /compact는 권하지 않는다). 이 파일의 main()은 아무것도 내지 않는다(hooks.json 등록은 남아 있다).
#
# 왜 (docs/research/LOOP_PLAN.md "토큰이 어디로 가나"·"세션 끊기 재계산", 2026-09-30):
#  - 실사용 세션 60개에서 비용의 85%(비용 가중)가 맥락이 첫 호출의 2배를 넘은 뒤에 나갔다. 초반 5호출은 2.8%.
#  - 절감 추정(2배 35~45%·3배 30~34%)은 11-24 /compact 맞대기 실험과 맞지 않아 알림에서 뺐다.
#  - 인계서로 새로 시작한 실제 세션은 초반에 다른 세션보다 약 5~9K 토큰만 더 읽었다.
# 정본 8절은 "Handoff는 컨텍스트 크기 때문에 발생하지 않는다"고 했다 — 소유자 결정(09-30)으로 크기를 "권고"로만 더한다.
#
# 문턱마다 한 번. 자동 쓰기를 못 할 때(BATON_HANDOFF_AUTO=off, 남의 형식 HANDOFF.md, 다른 Stop 훅이 턴을 잇는 중)는 사용자에게만 알린다.
# 끄기: BATON_SPLIT_NOTICE=off · 문턱: BATON_SPLIT_RATIOS="2,3"
#   환경변수 또는 설정 파일(lib/config.py, /baton-setup이 사용자 세션 분포로 문턱을 제안해 쓴다)에서 읽는다.
import json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import config, runlog

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


def man(n):
    """토큰 수를 한국어 만·천으로(85,312 → "8만 5천"). 천 아래는 버린다 — 영어 K 표기와 같은 자리."""
    k = n // 1000
    if not k:
        return f"{n:,}"
    hi, lo = divmod(k, 10)
    return " ".join(x for x in (f"{hi:,}만" if hi else "", f"{lo}천" if lo else "") if x)


def notice(lang, band, first, last, saved=False):
    """사용자에게 보이는 알림(systemMessage) — 자동 쓰기를 못 할 때. saved면 이번 턴에 인계서가 이미 갱신돼 있다."""
    if lang == "ko":
        head = f"[baton] 대화가 처음보다 {band:g}배 넘게 길어졌어요({man(first)} → {man(last)} 토큰)."
        if saved:
            return head + " 인계서는 이번 턴에 이미 남겨 뒀어요.\n하던 일이 끝났다면 새 대화에서 \"이어서\"라고 하면 이어 갈 수 있어요."
        return "\n".join([head, "하던 일이 끝났다면 새 대화로 넘어가 보세요.", '넘어가는 법: "인계서 써 줘" → /clear → "이어서"',
                          "이 알림은 한 번만 나와요."])
    head = f"[baton] This conversation is now more than {band:g}× as long as at the start ({first // 1000}K → {last // 1000}K tokens)."
    if saved:
        return (head + " The handoff was already saved in this turn.\n"
                "If you're done with the current task, start a new conversation and say \"where were we\".")
    return "\n".join([head, "If you're done with the current task, try moving to a new conversation.",
                      'To move: "write a handoff" → /clear → "where were we"', "You'll see this notice only once."])


def user_line(lang, band):
    """자동 쓰기 뒤 모델이 사용자에게 그대로 쓸 한 줄(소유자 승인 문장)."""
    if lang == "ko":
        return (f"대화가 처음보다 {band:g}배 넘게 길어져서 인계서를 남겨 뒀어요. "
                f"하던 일이 끝났다면 새 대화에서 \"이어서\"라고 하면 이어 갈 수 있어요.")
    return (f"This conversation is now more than {band:g}× as long as at the start, so I saved a handoff. "
            f"If you're done with the current task, start a new conversation and say \"where were we\".")


def crossed_band(path, repo, sid):
    """(새로 넘은 문턱, 첫 맥락, 마지막 맥락, 비율) 또는 None. 이미 알린 문턱(상태 파일)은 None. 상태는 쓰지 않는다 — 부르는 쪽(mark)."""
    first, last = first_and_last(path)
    if not first or not last:
        return None
    r = last / first
    crossed = [x for x in ratios(repo) if r >= x]
    if not crossed or crossed[-1] in done_bands(sid):
        return None
    return crossed[-1], first, last, r


def state_path(sid):
    # ponytail: 세션마다 작은 상태 파일이 하나씩 쌓인다(정리 안 함). 많아지면 오래된 것부터 지우는 정리를 더한다
    return os.path.join(runlog.cache_dir(), "split", f"{sid}.json")


def done_bands(sid):
    try:
        with open(state_path(sid), encoding="utf-8") as f:
            return set(json.load(f))
    except (OSError, ValueError, TypeError):
        return set()


def mark(sid, band):
    """이 문턱을 알렸다고 남긴다. 못 쓰면 OSError — 한 번만이라는 약속을 못 지키면 아예 알리지 않는다."""
    p = state_path(sid)
    os.makedirs(os.path.dirname(p), mode=0o700, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(sorted(done_bands(sid) | {band}), f)


def main():
    """Stop 결정은 hooks/handoff-check.py on_stop이 한다(한 Stop이 두 번 묻지 않게). 등록이 남아 있어도 아무것도 내지 않는다."""
    return


if __name__ == "__main__":
    main()
