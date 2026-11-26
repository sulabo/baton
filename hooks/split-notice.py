#!/usr/bin/env python3
# 북극성 길 단계 S "세션 끊기" — 이 세션의 호출당 맥락을 재는 도구와 알림 문장.
# 2026-11-24부터 Stop 결정은 hooks/handoff-check.py on_stop 한 곳에서 한다(파일 고침 자동 쓰기와 같은 규칙 — 한 Stop이 두 번 묻지
# 않게). 문턱을 처음 넘으면 모델이 인계서를 남기고 사용자에게 한 줄로 알린다(소유자 결정 11-24: "우리가 강제로
# compact를 하는 건 취지에 안 맞아" — /compact는 권하지 않는다). 이 파일은 hooks.json에 등록하지 않는다(handoff-check.py가 불러 쓴다).
# 2026-11-25부터: 인계서를 마지막으로 쓴 뒤 고친 파일이 하나라도 있을 때만 묻는다(on_stop), 문턱 기본값은 호출 맥락의 절대 토큰 수.
#
# 문턱 기본 25만·45만 토큰(BATON_SPLIT_TOKENS)인 까닭 (docs/research/LOOP_PLAN.md "2026-11-25 끊기 손익 재계산"):
#  - 예전 기본(첫 호출의 2배·3배)은 소유자 첫 호출 맥락 중앙값 약 7만 6천이라 2배가 약 15만 — 거기서 끊으면 대개 손해였다.
#  - 소유자 실제 세션 50개(2026-10-01~, 호출 20회 이상, 첫 압축 전까지)를 인계서 쓰기 비용까지 넣어 다시 셌다(observer/research/split_sim.py
#    --tokens). 인계서 쓰기 = 끊는 시점 맥락을 6번 캐시 읽기 + 고정분(23만에서 $0.69가 되게 맞춤, docs/research/compact-vs-handoff.md).
#    실험에 맞춘 단가(캐시 읽기 $0.201·1시간 캐시 쓰기 $8.00 /MTok)로 끊어서 이득 본 세션 비율(손익 중앙값):
#    15만 24%(-$1.05) · 20만 44%(-$0.53) · 25만 64%(+$1.37) · 30만 68% · 35만 84% · 40만 71% · 45만 60%(+$1.77) · 50만 80%.
#    표준 단가 비율(읽기 0.396·5분 쓰기 4.95)로는 더 일찍 남는다(15만 51% · 20만 62% · 25만 84%).
#  - 그래서 25만은 비관적인 단가로도 그 크기에 닿은 세션의 열에 여섯쯤에서 끊는 쪽이 싸지기 시작하는 자리, 45만은 소유자가 직접 느낀
#    문턱(1M 창의 45~50%)이고 역시 이득이다. 세션은 1M 맥락 창에서 나왔다 — 200K 창은 25만 전에 자동 압축되어 이 규칙이 울리지 않는다.
#    BATON_SPLIT_TOKENS를 낮출 수는 있지만 그 크기에서 더 싼지는 재지 않았다(1M 창 기록에서 15만은 대개 손해, 200K 창의 대안은 압축이고
#    11-24 맞대기 실험에서는 /compact가 더 쌌다). 그래서 "대개 더 싸다"는 말은 CLAIM_MIN(25만) 이상 문턱에서만 하고, 그 아래는 중립 문장이다(리뷰 11-25).
#  - 한 사람의 기록이고 가정이 있는 추정이다(끊은 뒤에도 같은 일을 한다, 방향 잡기 3호출, 새 세션 앞부분은 전부 캐시 쓰기).
# 그 전 근거(2026-09-30, 세션 60개): 비용의 85%(비용 가중)가 맥락이 첫 호출의 2배를 넘은 뒤에 나갔다. 절감 추정(2배 35~45%)은
# 인계서 쓰기 비용을 빼고 센 것이라 11-24 /compact 맞대기 실험과 맞지 않아 알림에서 뺐다.
# 정본 8절은 "Handoff는 컨텍스트 크기 때문에 발생하지 않는다"고 했다 — 소유자 결정(09-30)으로 크기를 "권고"로만 더한다.
#
# 문턱마다 한 번. 자동 쓰기를 못 할 때(BATON_HANDOFF_AUTO=off, 남의 형식 HANDOFF.md)는 사용자에게만 알린다. 다른 Stop 훅이 턴을 잇는 중이면 말하지 않고 다음 턴 끝에 다시 본다.
# 끄기: BATON_SPLIT_NOTICE=off · 문턱: BATON_SPLIT_TOKENS="250000,450000"(호출 맥락 토큰)
#   BATON_SPLIT_RATIOS(첫 호출의 몇 배)를 직접 정해 두고 BATON_SPLIT_TOKENS는 안 정한 사용자는 예전 배수 규칙과 문장 그대로.
#   환경변수 또는 설정 파일(lib/config.py, /baton-setup이 쓴다)에서 읽는다.
import json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import config, runlog

TOKEN_KEYS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
TAIL_BYTES = 512 * 1024
DEFAULT_TOKENS = "250000,450000"
# 새 대화가 거의 같은 크기로 시작하면 넘겨 봐야 줄지 않는다 — 마지막 맥락이 첫 호출 + 인계서(4천) + 여유(2만)를 넘을 때만 묻는다.
# observer/research/split_sim.py split_dollars의 끊기 조건(cur > first + handoff + 20_000)과 같은 수다
# 배수 규칙(BATON_SPLIT_RATIOS)에도 같이 쓴다
MIN_GAIN = 24000
CLAIM_MIN = 250000  # 재계산이 "끊는 쪽이 대개 싸다"를 뒷받침하는 가장 낮은 문턱. 이 아래 토큰 문턱과 배수 규칙은 비용을 말하지 않는다


def claims_cheaper(band, by_ratio=False):
    """이 문턱에서 "만든 사람의 기록으로 계산하면 … 대개 더 싸다"를 말해도 되나."""
    return not by_ratio and band >= CLAIM_MIN


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


def bands(repo):
    """(문턱 목록, 배수 규칙인가). 기본은 호출 맥락 토큰(BATON_SPLIT_TOKENS). BATON_SPLIT_TOKENS는 안 정하고 BATON_SPLIT_RATIOS만
    직접 정했으면 예전 배수 규칙. 값 검사는 /baton-setup apply와 같은 config.invalid — 못 쓰는 값(0·음수·250_000·빈 값, 배수의 abc)은
    새 토큰 기본값으로 돌아간다."""
    tokens, ratios = config.get("BATON_SPLIT_TOKENS", repo, None), config.get("BATON_SPLIT_RATIOS", repo, None)
    if tokens is None and ratios is not None and not config.invalid("BATON_SPLIT_RATIOS", ratios, "en"):
        return sorted(float(x) for x in ratios.split(",")), True
    if tokens is None or config.invalid("BATON_SPLIT_TOKENS", tokens, "en"):
        tokens = DEFAULT_TOKENS
    return sorted(int(x) for x in tokens.split(",")), False


def man(n):
    """토큰 수를 한국어 만·천으로(85,312 → "8만 5천"). 천 아래는 버린다 — 영어 K 표기와 같은 자리."""
    k = n // 1000
    if not k:
        return f"{n:,}"
    hi, lo = divmod(k, 10)
    return " ".join(x for x in (f"{hi:,}만" if hi else "", f"{lo}천" if lo else "") if x)


def band_label(lang, band):
    """토큰 문턱을 말로("25만 토큰"·"250K tokens")."""
    return f"{man(band)} 토큰" if lang == "ko" else f"{band // 1000}K tokens"


def notice(lang, band, first, last, by_ratio=False):
    """사용자에게 보이는 알림(systemMessage) — 자동 쓰기를 못 할 때. by_ratio면 예전 배수 규칙의 머리 줄.
    비용 문장은 claims_cheaper일 때만, 아니면 중립 문장."""
    ko = lang == "ko"
    if by_ratio:
        head = (f"[baton] 대화가 처음보다 {band:g}배 넘게 길어졌어요({man(first)} → {man(last)} 토큰)." if ko else
                f"[baton] This conversation is now more than {band:g}× as long as at the start ({first // 1000}K → {last // 1000}K tokens).")
    else:
        head = (f"[baton] 대화가 {band_label(lang, band)}을 넘었어요({man(first)} → {man(last)} 토큰)." if ko else
                f"[baton] The conversation passed {band_label(lang, band)} ({first // 1000}K → {last // 1000}K tokens).")
    if claims_cheaper(band, by_ratio):
        why = ("만든 사람의 기록으로 계산하면, 이 크기부터는 새 대화로 넘어가는 쪽이 대개 더 싸요." if ko else
               "By a recount of the author's sessions, from this size on, moving to a new conversation is usually cheaper.")
    else:
        why = "하던 일이 끝났다면 새 대화로 넘어가 보세요." if ko else "If you're done with the current task, try moving to a new conversation."
    if ko:
        return "\n".join([head, why, '넘어가는 법: "인계서 써 줘" → /clear → "이어서"', "이 알림은 한 번만 나와요."])
    return "\n".join([head, why, 'To move: "write a handoff" → /clear → "where were we"', "You'll see this notice only once."])


def user_line(lang, band, by_ratio=False):
    """자동 쓰기 뒤 모델이 사용자에게 그대로 쓸 한 줄. by_ratio면 예전 배수 규칙의 문장. 비용 문장은 claims_cheaper일 때만."""
    if by_ratio:
        if lang == "ko":
            return (f"대화가 처음보다 {band:g}배 넘게 길어져서 인계서를 남겨 뒀어요. "
                    f"하던 일이 끝났다면 새 대화에서 \"이어서\"라고 하면 이어 갈 수 있어요.")
        return (f"This conversation is now more than {band:g}× as long as at the start, so I saved a handoff. "
                f"If you're done with the current task, start a new conversation and say \"where were we\".")
    label = band_label(lang, band)
    if claims_cheaper(band):
        if lang == "ko":
            return (f"대화가 {label}을 넘어서 인계서를 남겨 뒀어요. 만든 사람의 기록으로 계산하면, 이 크기부터는 새 대화에서 "
                    f"\"이어서\"라고 하는 쪽이 대개 더 싸요.")
        return (f"The conversation passed {label}, so I saved a handoff. By a recount of the author's sessions, from this size on, "
                f"starting a new conversation and saying \"where were we\" is usually cheaper.")
    if lang == "ko":
        return f"대화가 {label}을 넘어서 인계서를 남겨 뒀어요. 하던 일이 끝났다면 새 대화에서 \"이어서\"라고 하면 이어 갈 수 있어요."
    return (f"The conversation passed {label}, so I saved a handoff. If you're done with this, you can continue in a new "
            f"conversation by saying \"where were we\".")


def crossed_band(path, repo, sid):
    """(새로 넘은 문턱, 첫 맥락, 마지막 맥락, 배수 규칙인가) 또는 None. 토큰 문턱은 마지막 호출 맥락이 그 값을 넘을 때,
    배수 문턱은 마지막 ÷ 첫 호출 맥락이 그 값 이상일 때. 마지막이 첫 + MIN_GAIN 이하이거나 그 문턱 또는 더 높은 문턱을 이미 알렸으면
    (상태 파일) None — 한 번에 25만·45만을 넘어 45만만 알렸으면 압축 뒤 25만~45만에서 25만을 다시 묻지 않는다(11-25 노트).
    상태는 쓰지 않는다 — 부르는 쪽(mark)."""
    first, last = first_and_last(path)
    if not first or not last or last <= first + MIN_GAIN:
        return None
    bs, by_ratio = bands(repo)
    crossed = [b for b in bs if (last / first >= b if by_ratio else last > b)]
    done = done_bands(sid)
    if not crossed or any(b in done for b in bs if b >= crossed[-1]):
        return None
    return crossed[-1], first, last, by_ratio


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
    """Stop 결정은 hooks/handoff-check.py on_stop이 한다(한 Stop이 두 번 묻지 않게). 직접 실행해도 아무것도 내지 않는다(옛 설치본 hooks.json 대비)."""
    return


if __name__ == "__main__":
    main()
