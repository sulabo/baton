"""사람이 고친 인계서를 지킨다(1.0.4) — 저장 검사의 "마지막 커밋판에서 빠진 줄"이 사람이 일부러 지운 줄을 되살리라고 하지 않게.

사람이 지운 줄 = 마지막 AI 저장판에는 있었는데, 사람 프롬프트 직전 파일에는 비슷한 줄도 없는 항목(빠진 줄 검사가 보는 절만).
- AI 판: 저장 검사가 AI의 저장을 검사할 때, 그리고 AI 턴이 끝날 때(Stop — 저장 검사가 못 본 Bash·apply_patch·검사가 꺼진 동안의
  쓰기도) 그 판을 남긴다(saved_by_ai).
- 사람 판: 사람 프롬프트 때 파일이 마지막 AI 판과 다르면, AI 판 항목 중 사라진 것을 사람이 지운 것으로 남긴다(note). 그 뒤 다른 곳만
  고쳐도 AI가 먼저 지운 줄은 사람 몫이 되지 않는다(리뷰 11-28: 커밋판과 견주던 첫 설계의 결함). 사람이 되살린 줄은 기억에서 뺀다.
- 빠진 줄 검사는 사람이 지운 항목을 빼고 알린다(removed). 마지막 커밋판이 그대로일 때만 — 커밋·pull·checkout·reset으로 바뀌면 버린다.
남기는 것은 해시뿐이다: 판의 해시, 항목 본문의 해시, 항목 낱말 열쇠(handoff_check.line_keys)의 해시. 인계서 글은 캐시에 남지 않는다.
기억은 파일마다 둔다(대화마다가 아니다): 사람이 고친 뒤 새 대화를 열어도 그 대화의 AI에게 지운 줄을 되살리라고 하지 않는다.
마지막 AI 판을 모르면(이 컴퓨터의 baton이 그 인계서를 본 적 없음) 아무것도 하지 않는다 — 예전 동작 그대로다.
ponytail(모두 사람이 지운 줄이 다시 경고되는 안전한 쪽): AI가 일하는 턴 도중의 사람 편집, 작업 알림처럼 사람이 치지 않은 프롬프트로
시작한 턴 앞의 편집, 사람이 고친 뒤 프롬프트 전에 같은 폴더의 다른 창이 턴을 끝낸 경우는 AI 것으로 본다.
남은 반대쪽 구멍: 창 B의 AI 쓰기를 그 저장 훅보다 먼저 창 A의 사람 프롬프트가 보면(수백 ms 틈) 그 쓰기가 지운 줄을 사람 것으로 본다.
Stop 없이 끝난 턴(Esc)의, 저장 검사도 Bash 훅도 못 본 쓰기(Codex apply_patch 등)도 그렇다."""
import hashlib, json, math, os, sys, unicodedata

import runlog

READ_MAX = 256 * 1024  # 이보다 큰 인계서는 보지 않는다(빠진 줄 검사가 읽는 양과 같다)


def _key(path):
    real = unicodedata.normalize("NFC", os.path.realpath(path))
    if sys.platform == "darwin":
        real = real.casefold()  # 기본 APFS는 대소문자를 가리지 않는다 — 같은 파일이 열쇠 둘이 되지 않게
    return hashlib.sha1(real.encode("utf-8", "surrogateescape")).hexdigest()[:16]


def _file(path, ext):
    return os.path.join(runlog.cache_dir(), "handoff-files", _key(path) + ext)


def sha(text):
    return hashlib.sha1((text or "").encode("utf-8", "surrogatepass")).hexdigest()[:16]


def hkeys(keys):
    return sorted({hashlib.sha1(k.encode("utf-8", "surrogatepass")).hexdigest()[:10] for k in keys})


def _write(p, d):
    try:
        os.makedirs(os.path.dirname(p), mode=0o700, exist_ok=True)
        tmp = f"{p}.{os.getpid()}.tmp"
        with os.fdopen(os.open(tmp, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.replace(tmp, p)
        return True
    except OSError:
        return False


def _load(p):
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def known(path, text):
    """text가 마지막 AI 판 그대로이고 그 항목도 아는가 — 아니면 Stop이 다시 남긴다(리뷰 11-28 R9: Bash 빠른 길이 남긴 "항목 모름" 판을
    그대로 두면 사람의 다음 편집에서 지운 줄을 세지 못했다)."""
    d = _load(_file(path, ".ai.json"))
    return d.get("sha") == sha(text) and d.get("items") is not None


def saved_by_ai(path, text, items):
    """AI 판을 남긴다. items = [(본문, 낱말 열쇠 집합)] — 빠진 줄 검사가 보는 절의 항목(handoff_check.drop_items).
    None이면 "AI가 썼지만 항목은 모름"(가벼운 Bash 빠른 길) — 그 판에서는 사람이 지운 줄을 새로 셈하지 않는다(안전한 쪽).
    사람이 지운 기억(.person.json)은 건드리지 않는다 — 리뷰 11-28: 턴 끝(Stop)마다 그것을 거두면 첫 Stop에 기억이 사라졌다."""
    return _write(_file(path, ".ai.json"), {"sha": sha(text), "items": None if items is None else [[sha(b), hkeys(k)] for b, k in items]})


def _similar(keys, cands, keep):
    need = math.ceil(keep * len(keys))
    return bool(keys) and any(len(keys & c) >= need for c in cands)


def note(path, text, line_keys, committed, keep):
    """사람 프롬프트 직전 파일 text를 본다(내용마다 한 번).
    - 마지막 AI 판과 다르면: AI 판 항목 중 text에 비슷한 줄이 없는 것을 사람이 지운 줄로 더하고, 그 판을 사람 판으로 남긴다.
    - 어느 쪽이든: 전에 사람이 지운 줄 중 text에 다시 있는 것은 뺀다(사람이 되살렸다 — 그 뒤 AI가 지우면 다시 알려야 한다).
    line_keys(text 줄마다 낱말 열쇠를 돌려주는 함수), committed(마지막 커밋판을 돌려주는 함수), keep(handoff_check.DROP_KEEP)은 부르는 쪽이 준다.
    사람 판을 새로 남겼으면 True. 커밋판을 못 읽으면 아무것도 바꾸지 않는다(빠진 줄 검사는 예전처럼 알린다)."""
    ai = _load(_file(path, ".ai.json"))
    if not ai.get("sha") or text is None or len(text.encode("utf-8", "surrogatepass")) > READ_MAX:
        return False
    s, pf = sha(text), _file(path, ".person.json")
    prev = _load(pf)
    if prev.get("seen") == s or (s == ai["sha"] and not prev.get("removed")):
        return False  # 이 내용은 이미 봤다 / AI 판 그대로이고 기억할 것도 없다 — git을 띄우지 않는다
    try:
        head = sha(committed())
    except Exception:
        return False
    cands = [set(hkeys(k)) for k in line_keys()]
    kept = [[b, ks] for b, ks in (prev.get("removed") or []) if prev.get("head") == head and not _similar(set(ks), cands, keep)]
    mine = s != ai["sha"]
    if mine and ai.get("items") is not None:
        have = {b for b, _ in kept}
        kept += [[b, ks] for b, ks in ai["items"] if b not in have and not _similar(set(ks), cands, keep)]
    _write(pf, {"seen": s, "sha": s if mine else prev.get("sha"), "head": head, "removed": kept})
    return mine


def removed(path, committed_text):
    """사람이 지운 항목 [(본문 해시, 낱말 열쇠 해시 집합)] — 마지막 커밋판이 기억할 때와 같을 때만, 아니면 빈 목록."""
    d = _load(_file(path, ".person.json"))
    if d.get("head") != sha(committed_text):
        return []
    return [(b, set(ks)) for b, ks in d.get("removed") or []]


def matches(body_keys, body, entries, keep):
    """커밋판 항목 하나가 사람이 지운 항목 중 하나인가 — 본문이 같거나 낱말이 비슷하면(커밋 뒤 AI가 조금 고친 줄도, 리뷰 11-28)."""
    h, ks = sha(body), set(hkeys(body_keys))
    # 두 줄 중 긴 쪽 열쇠 수로 센다 — 짧은 쪽으로 세면 사람이 지운 긴 줄이 AI가 지운 짧은 형제 줄까지 거른다(리뷰 11-28 R10d)
    return any(h == b or (ks and rk and len(ks & rk) >= math.ceil(keep * max(len(ks), len(rk)))) for b, rk in entries)


def is_person(path, text):
    """text가 지금 기억한 사람 판 그대로인가 — 주입 때 "사람이 고쳤을 수 있다"고 알릴지 정한다. 턴 끝(Stop)에 AI 판으로 함께
    남아도 내용이 사람 판 그대로면 알린다(리뷰 11-28: 첫 Stop 뒤 알림이 꺼지던 것)."""
    return bool(text) and _load(_file(path, ".person.json")).get("sha") == sha(text)


def prune(days=30):
    """days일 넘게 안 건드린 파일별 기억을 지운다(지운 워크트리 것 등). Stop마다 돈다. 실패는 넘긴다."""
    import time
    d, cut = os.path.join(runlog.cache_dir(), "handoff-files"), time.time() - days * 86400
    try:
        entries = list(os.scandir(d))
    except OSError:
        return
    for e in entries:
        try:
            if e.is_file(follow_symlinks=False) and e.stat(follow_symlinks=False).st_mtime < cut:
                os.remove(e.path)
        except OSError:
            pass
