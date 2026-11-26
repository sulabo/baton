#!/usr/bin/env python3
"""/baton-setup 스캐너 — 이 사용자의 과거 기록으로 baton 문턱과 개인 자료 목록 후보를 제안한다. 읽기만 한다.

  setup_scan.py [저장소 루트] [--json]     제안만 출력한다. 아무것도 바꾸지 않는다
  setup_scan.py apply [저장소 루트] [--global] [--set 키=값]... [--unset 키]... [--private-term 단어]... [--trigger 말]...
        [--private-terms-file 경로|-] [--remove-terms-file 경로|-] [--remove-term 단어]... [--remove-trigger 말]...
      사용자가 고른 것만 설정 파일(lib/config.py)에 쓴다. --global이면 전역 절, 아니면 이 저장소 절. 값은 키마다 검사한다.
  저장소 루트를 빼면 CLAUDE_PROJECT_DIR, 없으면 지금 폴더. 어느 쪽이든 git 최상위로 모은다(config.repo_key — 훅도 같은 함수를 쓴다).

읽는 것: 이 저장소 최상위 폴더에서 연 Claude Code 세션 기록(~/.claude/projects/*/*.jsonl), git 이력, 추적 파일과
무시되지 않은 미추적 파일(git grep --untracked), 다른 프로젝트 세션 기록의 cwd(프로젝트 이름 후보를 만들려고).
세는 방법은 기존 측정 코드를 그대로 쓴다 — 저장소별 세션 파일은 observer/baton_init.py, 세션 고르기·첫 프롬프트·인계서 재독은
observer/research/usage_week.py, 편집 파일은 hooks/handoff-check.py.
맥락 문턱(BATON_SPLIT_TOKENS)은 이 사용자 기록으로 제안하지 않는다 — 기본값과 그 출처(2026-11-25 재계산)만 보인다.
다만 대화가 첫 문턱에 한 번도 닿지 않고 그 전에 압축됐으면(맥락 창이 작다) 한 줄로 알린다(호출 맥락은 split_sim.call_contexts).
프롬프트 원문은 관찰 로그(~/.cache/baton/runs.jsonl)에 쓰지 않는다. 다만 스캔 출력(트리거 후보 말·개인 자료 후보)과
apply 명령줄은 스킬로 돌리면 에이전트 맥락과 Claude Code 세션 기록에 남는다 — 개인 자료는 --private-terms-file로 넘기거나 세션 밖 터미널에서 돌린다.
"""
import argparse, collections, getpass, glob, importlib.util, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "observer"))
sys.path.insert(0, os.path.join(ROOT, "observer", "research"))
import config, i18n, rules
import baton_init, split_sim, usage_week

_spec = importlib.util.spec_from_file_location("handoff_check_hook", os.path.join(ROOT, "hooks", "handoff-check.py"))
hc = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(hc)

MIN_SESSIONS = 10  # 이보다 적으면 문턱을 바꾸자고 하지 않는다 — 몇 세션의 우연에 문턱이 흔들린다
DEFAULT_TOKENS = "250000,450000"  # 맥락 문턱 기본값(hooks/split-notice.py)
DEFAULT_NUDGE = 3
NUDGE_MARGIN = 0.10
HANDOFF_NAME = re.compile(r"(?i)^handoff.*\.md$")
EMAIL = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
PLACEHOLDER = re.compile(r"(?i)@(example\.(com|org|net)|test|localhost)$")
# ponytail: Codex 세션(~/.codex/sessions)은 세지 않는다 — 저장소에는 파일 연결 검증(observer/measure/codex_join_census.py)만 있고
# 프롬프트·토큰·편집 레코드 형식을 읽는 코드가 없다. 형식을 확인해 usage_week처럼 읽는 함수를 만들면 여기에 더한다
CODEX_NOTE = "Codex 세션은 세지 않음 — Codex 세션 파일의 프롬프트·호출 형식을 이 저장소 코드가 아직 다루지 않는다(observer/baton_init.py와 같은 범위)"
CODEX_NOTE_EN = ("Codex sessions are not counted: this repo's code does not read the prompt and call format of Codex session files yet "
                 "(the same scope as observer/baton_init.py)")
HANGUL = re.compile("[\uac00-\ud7a3\u3131-\u318e]")


def pct(x):
    return f"{x:.0%}"


def num(n, one, many):
    """영어 출력의 단수·복수("1 session", "2 sessions")."""
    return f"{n} {one if n == 1 else many}"


def git(root, *args):
    """git 출력(문자열). 실패하면 None — 0건과 못 셈을 구분하려고."""
    try:
        r = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode in (0, 1) else None  # git grep은 못 찾으면 1


# ── 세션 ──────────────────────────────────────────────────────────────

def load_sessions(root):
    files = baton_init.claude_files_for(root)
    sessions, skipped = usage_week.collect(files=files)
    return sessions, skipped, len(files)


def window(sessions, root, lang=None):
    """첫 맥락 문턱(토큰 규칙일 때)을 넘은 대화 수와, 넘지 못한 채 압축된 대화 수(맥락이 앞 호출의 60% 아래로 떨어짐 —
    split_sim.until_compaction). 기본 문턱은 맥락 창 100만 토큰인 대화에서 나왔다 — 20만 창은 25만 전에 압축된다(리뷰 11-25).
    배수 규칙이거나 훅 모듈을 못 불러왔으면 None."""
    split = hc.split_mod()
    if split is None:
        return None
    bs, by_ratio = split.bands(root)
    if by_ratio:
        return None
    rows = [c for c in (split_sim.call_contexts(x["file"]) for x in sessions) if c]
    passed = [max(c) > bs[0] for c in rows]
    return {"band": bs[0], "label": split.band_label(lang or i18n.lang(root), bs[0]), "counted": len(rows),
            "passed": sum(passed),
            "compacted": sum(not p and len(split_sim.until_compaction(c)) < len(c) for c, p in zip(rows, passed))}


def nudge(sessions, lang=None):
    """인계서(HANDOFF.md)를 쓰기 전에 고친 파일 수(안 썼으면 세션 전체)별로 인계서를 쓴 비율 — 기본 문턱 3을 정한 방법.
    여기서는 대화형 세션만 센다(usage_week 필터). 기본값의 세션 94개 측정은 실험·SDK 세션까지 센 분모라 값이 다를 수 있다."""
    t = config.tr(lang=lang)
    rows, zero, names = [], 0, collections.Counter()
    for s in sessions:
        before, wrote = set(), False
        for fp in hc.edit_paths(s["file"]):
            if HANDOFF_NAME.match(os.path.basename(fp)):
                names[os.path.basename(fp)] += 1
            if hc.wrote_handoff(fp):
                wrote = True
            elif not wrote:
                before.add(os.path.normpath(fp))
        if before:
            rows.append((len(before), wrote))
        else:
            zero += 1
    out = {"counted": len(rows), "excluded": zero,
           "excluded_reason": t("인계서를 쓰기 전 고친 파일 0개 — 제안 대상이 아님",
                                "0 files edited before the handoff was written, so the nudge does not apply"),
           "names": dict(names.most_common()), "recommend": None}
    buckets = []
    for lo, hi, label in ((1, 1, t("1개", "1")), (2, 2, t("2개", "2")), (3, 3, t("3개", "3")), (4, 4, t("4개", "4")),
                          (5, None, t("5개 이상", "5 or more"))):
        b = [w for k, w in rows if k >= lo and (hi is None or k <= hi)]
        buckets.append({"files": label, "sessions": len(b), "wrote": sum(b)})
    out["buckets"] = buckets
    gaps = {}
    for n in range(2, 7):
        low = [w for k, w in rows if k < n]
        high = [w for k, w in rows if k >= n]
        if len(low) >= 3 and len(high) >= 3:
            gaps[n] = sum(high) / len(high) - sum(low) / len(low)
    if len(rows) < MIN_SESSIONS:
        out["reason"] = t(f"센 세션 {len(rows)}개 — {MIN_SESSIONS}개 미만이라 기본값 {DEFAULT_NUDGE} 유지",
                          f"{num(len(rows), 'session', 'sessions')} counted, fewer than {MIN_SESSIONS}, "
                          f"so the default {DEFAULT_NUDGE} stays")
    elif not any(w for _, w in rows):
        out["reason"] = t(f"인계서를 쓴 세션이 0개라 경계를 못 정한다 — 기본값 {DEFAULT_NUDGE} 유지",
                          f"0 sessions wrote a handoff, so there is no boundary to find and the default {DEFAULT_NUDGE} stays")
    elif not gaps:
        out["reason"] = t(f"양쪽(문턱 미만·이상)에 세션이 3개씩 모이는 문턱이 없다 — 기본값 {DEFAULT_NUDGE} 유지",
                          f"no threshold has 3 or more sessions on each side (below it, and at or above it), "
                          f"so the default {DEFAULT_NUDGE} stays")
    else:
        best = max(gaps, key=gaps.get)
        # ponytail: 경계 하나만 본다. 문턱 이상에서 인계서를 10%p 이상 더 쓰고, 그 차이가 기본값 3의 차이보다 10%p 이상 클 때만 바꾼다
        # (잡음으로 문턱이 흔들리지 않게). 기본값 3 쪽에 세션이 3개씩 안 모여 차이를 못 셀 때는 -inf로 쳐서 최선 문턱을 권한다
        if gaps[best] < NUDGE_MARGIN:
            out["reason"] = t(f"고친 파일 수와 인계서 작성 사이에 뚜렷한 경계가 없다(가장 큰 차이 {gaps[best] * 100:+.0f}%p) — "
                              f"기본값 {DEFAULT_NUDGE} 유지",
                              f"no clear boundary between the number of edited files and writing a handoff (largest gap "
                              f"{gaps[best] * 100:+.0f} percentage points), so the default {DEFAULT_NUDGE} stays")
        elif best != DEFAULT_NUDGE and gaps[best] - gaps.get(DEFAULT_NUDGE, float("-inf")) >= NUDGE_MARGIN:
            out["recommend"] = str(best)
            out["reason"] = t(f"{best}개를 경계로 인계서 작성 비율 차이가 가장 크다({gaps[best] * 100:+.0f}%p)",
                              f"the gap in how often a handoff was written is largest at {best} files "
                              f"({gaps[best] * 100:+.0f} percentage points)")
        else:
            gap = gaps.get(DEFAULT_NUDGE, gaps[best]) * 100
            out["reason"] = t(f"기본값 {DEFAULT_NUDGE}이 이미 경계에 가깝다({gap:+.0f}%p) — 유지",
                              f"the default {DEFAULT_NUDGE} is already close to the boundary ({gap:+.0f} percentage points), "
                              f"so it stays")
    return out


phrases = rules.phrases  # 별칭·새 개념 후보(candidates.py)와 같은 정의


def triggers(sessions, root):
    """에이전트가 처음 5호출 안에 HANDOFF.md를 읽었는데 지금 트리거가 첫 프롬프트에 안 맞은 세션들의 자주 나온 말.
    후보마다 그 밖의 사람 프롬프트 중 몇 개에 걸리는지도 센다 — 훅은 모든 프롬프트를 대소문자 무시 부분 문자열로 보므로
    그만큼 인계서가 더 들어간다(그중 일부는 맞는 주입일 수 있다 — 상한)."""
    read = [s for s in sessions if s["reread"] and not rules.trigger_words(root, s["prompt"])]
    hit = collections.Counter()
    for s in read:
        hit.update(phrases(s["prompt"]))
    rid = {id(s) for s in read}
    others = [p.casefold() for s in sessions for i, p in enumerate(s["prompts"]) if not (i == 0 and id(s) in rid)]
    fires = {p: sum(p in q for q in others) for p, n in hit.items() if n >= 2}
    cands = sorted(fires, key=lambda p: (-hit[p], fires[p], p))[:10]
    return {"sessions_read_untriggered": len(read), "other_prompts": len(others),
            "sessions_not_read": sum(1 for s in sessions if not s["reread"] and not s["injected"]),  # 훅이 이미 넣은 세션은 "안 읽음"이 아니다
            "candidates": [{"phrase": p, "read": hit[p], "other_prompts": fires[p]} for p in cands]}


# ── 저장소 ────────────────────────────────────────────────────────────

def other_projects(root):
    """~/.claude/projects 아래 폴더마다 세션 하나의 cwd 끝 이름. 이 저장소는 뺀다."""
    names = set()
    for d in glob.glob(os.path.expanduser("~/.claude/projects/*/")):
        for f in glob.glob(os.path.join(d, "*.jsonl"))[:3]:
            cwd = None
            try:
                with open(f, encoding="utf-8", errors="ignore") as fh:
                    for i, line in enumerate(fh):
                        if i > 50: break
                        try: rec = json.loads(line)
                        except ValueError: continue
                        if isinstance(rec, dict) and isinstance(rec.get("cwd"), str):
                            cwd = rec["cwd"]; break
            except OSError:
                continue
            if cwd:
                if config.repo_key(cwd) != root and not usage_week.experimental(cwd):  # 이 저장소 하위 폴더에서 연 세션도 같은 저장소
                    names.add(os.path.basename(cwd.rstrip("/")))
                break
    return names


def private_candidates(root, lang=None):
    """개인 자료 목록 후보. 사람이 고른다 — 스캐너는 제안만."""
    t = config.tr(root, lang)
    out, notes = [], []

    def files_with(term):
        r = git(root, "grep", "-I", "-i", "-F", "-l", "--untracked", "-e", term)
        return None if r is None else len(r.splitlines())

    log = git(root, "log", "--format=%an%x00%ae%x00%cn%x00%ce")
    seen = set()
    if log is None and git(root, "rev-parse", "--git-dir") is not None:
        notes.append(t("커밋이 아직 없어 git 작성자를 못 셈", "no commits yet, so git authors could not be counted"))
    elif log is None:
        notes.append(t("git 저장소가 아니거나 git이 없어 작성자·추적 파일을 못 셈",
                       "not a git repo, or git is missing, so authors and tracked files could not be counted"))
    else:
        for v in sorted({x.strip() for x in log.replace("\n", "\0").split("\0") if x.strip()}):
            seen.add(v.lower()); out.append({"term": v, "source": t("git 작성자·이메일", "git author or email"), "files": files_with(v)})
    try:
        user = getpass.getuser()
    except Exception:
        user = None
        notes.append(t("OS 사용자 이름을 못 읽음", "could not read the OS user name"))
    if user and user.lower() not in seen:
        seen.add(user.lower()); out.append({"term": user, "source": t("OS 사용자 이름", "OS user name"), "files": files_with(user)})
    proj = other_projects(root)
    if not os.path.isdir(os.path.expanduser("~/.claude/projects")):
        notes.append(t("~/.claude/projects가 없어 다른 프로젝트 이름을 못 셈",
                       "~/.claude/projects is missing, so other project names could not be counted"))
    own = os.path.basename(root).lower()
    shown = 0
    for name in sorted(proj):
        if len(name) < 3 or name.lower() in seen or name.lower() == own or name.lower() in rules.GENERIC_WORDS:
            continue
        n = files_with(name)
        if n:
            seen.add(name.lower()); shown += 1
            out.append({"term": name, "source": t("다른 프로젝트 이름", "other project name"), "files": n})
    notes.append(t(f"다른 프로젝트 {len(proj)}개 이름 중 이 저장소 파일에 나오는 것 {shown}개",
                   f"other project names that appear in this repo's files: {shown} of {len(proj)}"))
    found = git(root, "grep", "-I", "-h", "-o", "-E", "--untracked", "-e", EMAIL)
    if found is not None:
        for e, n in collections.Counter(found.split()).most_common():
            if e.lower() not in seen and not PLACEHOLDER.search(e):
                seen.add(e.lower()); out.append({"term": e, "source": t("파일 속 이메일", "email in a file"), "files": files_with(e)})
    return {"candidates": out, "notes": notes}


def repo_advice(root, lang=None):
    t = config.tr(root, lang)
    tips = []
    if git(root, "rev-parse", "--git-dir") is None:
        return [t("git 저장소가 아니다 — 인계서 승격 검토(/promote)와 개념 지도 신선도(/drift)가 동작하지 않는다",
                  "not a git repo: the handoff promotion review (/promote) and concept map freshness (/drift) do not work")]
    has_handoff = os.path.isfile(os.path.join(root, "HANDOFF.md"))
    tracked = bool((git(root, "ls-files", "HANDOFF.md") or "").strip())
    if has_handoff and not tracked:
        tips.append(t("HANDOFF.md가 git에 추적되지 않는다 — `git add HANDOFF.md` 하지 않으면 승격 검토가 불가능하다",
                      "HANDOFF.md is not tracked by git. The promotion review needs it: run `git add HANDOFF.md`"))
    elif not has_handoff:
        tips.append(t("HANDOFF.md가 아직 없다 — 첫 작업 덩어리가 끝나면 '핸드오프 작성해줘'",
                      "no HANDOFF.md yet. When the first piece of work is done, ask \"write a handoff\""))
    else:
        tips.append(t("HANDOFF.md 추적됨", "HANDOFF.md is tracked"))
    tips.append(t("DECISIONS.md 있음", "DECISIONS.md exists") if os.path.isfile(os.path.join(root, "DECISIONS.md"))
                else t("DECISIONS.md가 없다 — 결정이 인계서에만 살다가 사라질 수 있다. 결정이 나오면 /decision으로 시작한다",
                       "no DECISIONS.md. Decisions may live only in handoffs and get lost. "
                       "When a decision is made, start the file with /decision"))
    if rules.concept_path(root)[0]:
        tips.append(t("CONCEPTS.md 있음", "CONCEPTS.md exists"))
    else:
        commits = (git(root, "rev-list", "--count", "HEAD") or "0").strip() or "0"
        nfiles = len((git(root, "ls-files") or "").splitlines())
        # ponytail: 개념 지도를 권할 크기 기준(커밋 50·파일 30)은 경험칙이다 — 측정한 값이 아니다
        big = int(commits) >= 50 and nfiles >= 30 if commits.isdigit() else False
        tips.append(t(f"CONCEPTS.md 없음 — 커밋 {commits}개·추적 파일 {nfiles}개. "
                      + ("개념 지도를 시작할 만하다(driftmap 스킬, 경험칙 기준 커밋 50·파일 30)" if big
                         else "아직 작아 개념 지도는 미뤄도 된다(경험칙 기준 커밋 50·파일 30)"),
                      f"no CONCEPTS.md (commits: {commits}, tracked files: {nfiles}). "
                      + ("Big enough to start a concept map (driftmap skill; rule of thumb: 50 commits and 30 files)" if big
                         else "Still small, so the concept map can wait (rule of thumb: 50 commits and 30 files)")))
    return tips


def language(sessions, root, lang=None):
    """사람 프롬프트의 언어로 BATON_LANG을 제안한다. 한글이 든 프롬프트는 한국어, 글자가 있는데 한글이 없으면 그 밖의 언어,
    글자가 없는 프롬프트("1", "?")는 안 센다. 한국어가 절반을 넘으면 ko, 절반 미만이면 en, 딱 반이면 제안하지 않는다.
    ponytail: 붙여 넣은 글(오류 출력·문서)도 프롬프트에 들어 있어 섞인다 — 프롬프트 수로 세므로 긴 붙여넣기 하나가 이기지는 않는다.
    지금 언어가 이미 설정(환경변수·설정 파일)으로 같은 값이면 제안하지 않는다. 로캘에서 온 값이면 같아도 써 두기를 권한다
    (로캘이 바뀌거나 비어 있는 실행 환경에서도 그 언어로 나온다)."""
    t = config.tr(root, lang)
    ko = other = skipped = 0
    for s in sessions:
        for p in s["prompts"]:
            if HANGUL.search(p):
                ko += 1
            elif any(c.isalpha() for c in p):
                other += 1
            else:
                skipped += 1
    n = ko + other
    cur, src = i18n.where(root)
    out = {"counted": n, "korean": ko, "other": other, "skipped": skipped, "current": cur, "source": src, "recommend": None}
    srcs = config.language_source(src, t)
    if not n:
        out["reason"] = t("센 프롬프트가 없어 정하지 못한다 — 0건이 아니라 못 셈. 지금 값 유지",
                          "no prompts were counted, so there is nothing to go on (could not count, not 0). The current value stays")
        return out
    if ko * 2 == n:
        out["reason"] = t("한글 프롬프트와 그 밖의 프롬프트가 반반이다 — 지금 값 유지",
                          "half of the prompts are in Korean and half are not, so the current value stays")
        return out
    want = "ko" if ko * 2 > n else "en"
    share = pct(ko / n)
    if want == cur and src in ("env", "config"):
        out["reason"] = t(f"한글 프롬프트 {share} — 이미 {cur}다(정한 곳: {srcs}). 유지",
                          f"{share} of the prompts are in Korean, and the output is already {cur} (source: {srcs}), so it stays")
        return out
    out["recommend"] = want
    if want == cur:
        out["reason"] = t(f"한글 프롬프트 {share} — 지금도 {cur}지만 설정한 값이 아니다(정한 곳: {srcs}). "
                          f"써 두면 로캘이 다르거나 비어 있는 곳에서도 {want}로 나온다",
                          f"{share} of the prompts are in Korean. The output is {cur} now, but it is not set anywhere "
                          f"(source: {srcs}). Writing it keeps {want} where the locale is different or not set")
    else:
        out["reason"] = t(f"한글 프롬프트 {share} — 지금은 {cur}(정한 곳: {srcs})",
                          f"{share} of the prompts are in Korean; the output is {cur} now (source: {srcs})")
    if src == "env":
        out["reason"] += t(". 다만 환경변수 BATON_LANG이 설정 파일보다 우선한다 — 써도 그 환경변수를 지우기 전에는 안 바뀐다",
                           ". But the BATON_LANG environment variable wins over the config file: writing it changes nothing "
                           "until that variable is removed")
    return out


def scan(root):
    lang = i18n.lang(root)  # 이 실행의 출력 언어 — 한 번만 정해 아래로 넘긴다
    t = config.tr(lang=lang)
    sessions, skipped, nfiles = load_sessions(root)
    current = {k: config.get(k, root, None) for k in config.SCALAR_KEYS}
    return {
        "repo": root, "min_sessions": MIN_SESSIONS, "lang": lang,
        "config": {"path": config.path(), "status": config.status(root, lang),
                   "current": {k: v for k, v in current.items() if v is not None}},
        "sessions": {"files": nfiles, "usable": len(sessions), "excluded": skipped},
        "codex": t(CODEX_NOTE, CODEX_NOTE_EN),
        # 배수 규칙인지는 훅과 같은 함수로 정한다(못 쓰는 배수 값은 토큰 기본값 — split-notice.py bands)
        "ratio_rule": (hc.split_mod().bands(root)[1] if hc.split_mod()
                       else current["BATON_SPLIT_RATIOS"] is not None and current["BATON_SPLIT_TOKENS"] is None),
        "window": window(sessions, root, lang),
        "nudge": nudge(sessions, lang),
        "triggers": triggers(sessions, root),
        "private_terms": private_candidates(root, lang),
        "advice": repo_advice(root, lang),
        "language": language(sessions, root, lang),
    }


def render(r):
    t = config.tr(lang=r.get("lang"))
    s, n, tg, p = r["sessions"], r["nudge"], r["triggers"], r["private_terms"]
    ex = s["excluded"]
    cur = r["config"]["current"]
    now = lambda k, d: (t(f" (지금 적용 값 {cur[k]} — 설정 파일·환경변수에서. 그대로 둔다)",
                          f" (value in effect now: {cur[k]}, from the config file or an environment variable. Left as is)")
                        if k in cur else t(f" (지금 적용 값 {d} — 코드 기본값)", f" (value in effect now: {d}, the code default)"))
    L = [t(f"[baton-setup] {r['repo']} — 읽기만 했다. 아무것도 바꾸지 않았다.", f"[baton-setup] {r['repo']}: read only. Nothing was changed."), ""]
    L += [t("설정", "Config")] + [f"  {x}" for x in r["config"]["status"]] + [""]
    L.append(t(f"세션 기록: 이 저장소 폴더의 세션 파일 {s['files']}개 → 쓸 수 있는 세션 {s['usable']}개",
               f"Session logs: {num(s['files'], 'session file', 'session files')} for this repo's folder → "
               f"{num(s['usable'], 'usable session', 'usable sessions')}"))
    L.append(t(f"  제외: 중복 사본 {ex['duplicate']} · 호출/사람 프롬프트 없음 {ex['empty']} · 실험·임시 폴더 {ex['experimental']} · "
               f"claude -p·SDK {ex['non_cli']}",
               f"  Excluded: duplicate copies {ex['duplicate']} · no model calls or no human prompt {ex['empty']} · "
               f"experiment or temp folders {ex['experimental']} · claude -p or SDK {ex['non_cli']}"))
    L.append(f"  {r['codex']}")
    if not s["files"]:
        L.append(t("  이 저장소 폴더에서 연 Claude Code 세션 기록을 못 찾았다 — 0건이 아니라 못 셈"
                   "(다른 폴더에서 열었거나, 기록이 지워졌거나, ~/.claude/projects가 없다)",
                   "  No Claude Code session logs opened in this repo's folder were found. That means could not count, not 0 "
                   "(the sessions were opened in another folder, the logs were deleted, or ~/.claude/projects is missing)"))
    if s["usable"] < r["min_sessions"]:
        L.append(t(f"  표본 {s['usable']}개 — {r['min_sessions']}개 미만이라 문턱은 기본값을 권한다(몇 세션의 우연에 흔들린다)",
                   f"  Sample of {s['usable']}: fewer than {r['min_sessions']}, so the defaults are recommended for the thresholds "
                   f"(a few sessions can swing them by chance)"))
    ratio_rule = r.get("ratio_rule")
    L += ["", t(f"1) 맥락 문턱 BATON_SPLIT_TOKENS (기본 {DEFAULT_TOKENS} — 호출 맥락 토큰)",
                f"1) Context thresholds BATON_SPLIT_TOKENS (default {DEFAULT_TOKENS}, context tokens per call)"),
          t("  2026-11-25 재계산에서 정한 값이다 — 만든 사람 한 명의 대화 50개를 인계서 쓰는 비용까지 넣어 다시 센 추정. "
            "이 사용자 기록으로 따로 제안하지 않는다",
            "  Set by the 2026-11-25 recount: an estimate from one person's 50 sessions that includes the cost of writing the "
            "handoff. No proposal is made from this user's history"),
          t(f"  제안 없음{now('BATON_SPLIT_RATIOS' if ratio_rule else 'BATON_SPLIT_TOKENS', DEFAULT_TOKENS)}",
            f"  No proposal{now('BATON_SPLIT_RATIOS' if ratio_rule else 'BATON_SPLIT_TOKENS', DEFAULT_TOKENS)}")]
    w = r.get("window")
    if w and w["counted"] and not w["passed"] and w["compacted"]:  # 숫자를 권하지는 않는다 — 뒷받침할 계산이 없다
        L.append(t(f"  이 저장소 대화 {w['counted']}개 중 {w['label']}을 넘은 대화가 없고 {w['compacted']}개는 그 전에 압축됐다"
                   f"(맥락이 40% 넘게 줄어듦) — 맥락 창이 작아(20만 토큰 등) 이 규칙이 울리지 않는 것으로 보인다. "
                   f"apply --set BATON_SPLIT_TOKENS=<값>으로 낮출 수는 있지만, 그 크기에서 새로 시작하는 쪽이 더 싼지는 재지 않았다"
                   f"(100만 토큰 창 기록에서 15만은 대개 손해였다)",
                   f"  None of the {w['counted']} sessions in this repo passed {w['label']}, and {w['compacted']} were compacted "
                   f"before that (context dropped by more than 40%), so with a small context window (such as 200K) this rule "
                   f"doesn't fire. You can lower it with apply --set BATON_SPLIT_TOKENS=<value>, but whether starting fresh is "
                   f"cheaper at that size wasn't measured (in the 1M-window sessions, 150K was usually a loss)"))
    if ratio_rule:
        L.append(t("  지금은 예전 배수 규칙(BATON_SPLIT_RATIOS, 첫 호출의 몇 배)이 적용된다. 토큰 기본값으로 돌아가려면 "
                   "apply --unset BATON_SPLIT_RATIOS",
                   "  The older ratio rule (BATON_SPLIT_RATIOS, multiples of the first call) applies now. To go back to the "
                   "token default: apply --unset BATON_SPLIT_RATIOS"))
    L += ["", t(f"2) 인계서 제안 문턱 BATON_HANDOFF_NUDGE_FILES (기본 {DEFAULT_NUDGE})",
                f"2) Handoff nudge threshold BATON_HANDOFF_NUDGE_FILES (default {DEFAULT_NUDGE})"),
          t(f"  센 세션 {n['counted']}개 / 제외 {n['excluded']}개({n['excluded_reason']})",
            f"  {num(n['counted'], 'session', 'sessions')} counted / {n['excluded']} excluded ({n['excluded_reason']})")]
    L += [t(f"    고친 파일 {b['files']}: 세션 {b['sessions']} · 인계서 씀 {b['wrote']}",
            f"    files edited {b['files']}: sessions {b['sessions']} · wrote a handoff {b['wrote']}")
          + (f" ({pct(b['wrote'] / b['sessions'])})" if b["sessions"] else "") for b in n["buckets"]]
    L.append(t(f"  제안: {n['recommend'] or '바꾸지 않음'} — {n['reason']}{now('BATON_HANDOFF_NUDGE_FILES', DEFAULT_NUDGE)}",
               f"  Proposal: {n['recommend'] or 'no change'} — {n['reason']}{now('BATON_HANDOFF_NUDGE_FILES', DEFAULT_NUDGE)}"))
    L += ["", t("3) 실제로 쓴 인계서 파일 이름(설정 아님, 보고만)", "3) Handoff file names actually written (not a setting, report only)")]
    if n["names"]:
        L += [t(f"    {k}: 편집 {v}회", f"    {k}: edits {v}")
              + ("" if k == "HANDOFF.md" else t(" — 주입 훅은 HANDOFF.md만 읽는다", " — the injection hook reads only HANDOFF.md"))
              for k, v in n["names"].items()]
    else:
        L.append(t(f"    세션 {s['usable']}개에서 HANDOFF*.md 편집 0회(이 저장소 폴더의 Claude Code 세션만 셌다)",
                   f"    0 edits to HANDOFF*.md in {num(s['usable'], 'session', 'sessions')} "
                   f"(only Claude Code sessions in this repo's folder were counted)"))
    L += ["", t("4) 인계 트리거 추가 말 후보 BATON_HANDOFF_TRIGGERS_EXTRA",
                "4) Extra handoff trigger phrase candidates BATON_HANDOFF_TRIGGERS_EXTRA"),
          t(f"  처음 5호출 안에 HANDOFF.md를 읽었는데 지금 트리거가 안 맞은 세션 {tg['sessions_read_untriggered']}개 · "
            f"인계서를 안 읽고 주입도 없던 세션 {tg['sessions_not_read']}개 · 그 밖의 사람 프롬프트 {tg['other_prompts']}개",
            f"  Sessions that read HANDOFF.md in their first 5 calls but matched no current trigger: "
            f"{tg['sessions_read_untriggered']} · sessions that neither read the handoff nor had it injected: "
            f"{tg['sessions_not_read']} · other human prompts: {tg['other_prompts']}")]
    if tg["candidates"]:
        L += [t(f"    '{c['phrase']}' — 읽은 세션 첫 프롬프트 {c['read']}개 · 그 밖의 프롬프트 {c['other_prompts']}개에도 걸린다"
                f"(그만큼 인계서가 더 들어간다 — 상한)",
                f"    '{c['phrase']}' — first prompts of such sessions: {c['read']} · other prompts it also matches: "
                f"{c['other_prompts']} (the handoff would go in that many more times; an upper bound)") for c in tg["candidates"]]
    elif tg["sessions_read_untriggered"] < 2:
        L.append(t("    후보 없음이 아니라 표본 부족 — 그런 세션이 2개 이상이어야 반복된 말을 셀 수 있다",
                   "    Not \"no candidates\" but too small a sample: it takes 2 or more such sessions to count repeated phrases"))
    else:
        L.append(t("    두 세션 이상에서 반복된 말이 없다", "    No phrase repeats across two or more sessions"))
    L += ["", t("5) 개인 자료 목록 후보 private_terms (고른 것만 인계서 검사가 막는다)",
                "5) Private-words list candidates private_terms (the handoff check blocks only the ones you pick)")]
    L += [t(f"    {c['term']} — {c['source']} · 이 저장소 파일 {'못 셈' if c['files'] is None else str(c['files']) + '개'}에 나옴",
            f"    {c['term']} — {c['source']} · files in this repo that contain it: "
            + ("could not count" if c["files"] is None else str(c["files"])))
          for c in p["candidates"]] or [t("    후보 0개", "    0 candidates")]
    L += [f"    ({x})" for x in p["notes"]]
    L += ["", t("6) 저장소 권고(보고만)", "6) Repo advice (report only)")] + [f"  - {x}" for x in r["advice"]]
    lg = r["language"]
    L += ["", t("7) 출력 언어 BATON_LANG (ko·en·auto, 기본은 로캘을 따른다)",
                "7) Output language BATON_LANG (ko, en or auto; by default it follows the locale)"),
          t(f"  사람 프롬프트 {lg['counted']}개 중 한글이 든 것 {lg['korean']}개 · 그 밖의 언어 {lg['other']}개"
            f"(글자가 없어 안 센 것 {lg['skipped']}개)",
            f"  Human prompts counted: {lg['counted']} · with Korean: {lg['korean']} · other languages: {lg['other']} "
            f"(not counted, no letters: {lg['skipped']})"),
          t(f"  제안: {lg['recommend'] or '바꾸지 않음'} — {lg['reason']}",
            f"  Proposal: {lg['recommend'] or 'no change'} — {lg['reason']}")]
    return "\n".join(L)


# ── 적용 ──────────────────────────────────────────────────────────────

def here(repo=None):
    """저장소 인자가 없으면 CLAUDE_PROJECT_DIR, 없으면 지금 폴더 — git 최상위로 모은 키."""
    return config.repo_key(repo or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())


def apply(argv):
    t = config.tr(here())  # 도움말용. 저장소 인자를 읽은 뒤 그 저장소 기준으로 한 번 더 정한다
    ap = argparse.ArgumentParser(prog="setup_scan.py apply",
                                 description=t("사용자가 고른 값만 설정 파일에 쓴다", "Write only the values the user picked to the config file"))
    ap.add_argument("repo", nargs="?")
    ap.add_argument("--global", dest="is_global", action="store_true",
                    help=t("전역 절에 쓴다(기본: 이 저장소 절)", "write to the global section (default: this repo's section)"))
    ap.add_argument("--set", action="append", default=[], metavar=t("키=값", "KEY=VALUE"))
    ap.add_argument("--unset", action="append", default=[], metavar=t("키", "KEY"))
    ap.add_argument("--private-term", action="append", default=[], metavar=t("단어", "WORD"))
    ap.add_argument("--private-terms-file", metavar=t("경로", "PATH"),
                    help=t("한 줄에 하나. '-'면 표준 입력 — 단어가 명령줄·세션 기록에 안 남는다",
                           "one per line; '-' reads standard input, so the words stay out of the command line and the session log"))
    ap.add_argument("--remove-term", action="append", default=[], metavar=t("단어", "WORD"))
    ap.add_argument("--remove-terms-file", metavar=t("경로", "PATH"),
                    help=t("뺄 단어 파일(한 줄에 하나, '-'면 표준 입력)", "file of words to remove (one per line; '-' reads standard input)"))
    ap.add_argument("--trigger", action="append", default=[], metavar=t("말", "PHRASE"))
    ap.add_argument("--remove-trigger", action="append", default=[], metavar=t("말", "PHRASE"))
    a = ap.parse_args(argv)
    target = here(a.repo)
    lang = i18n.lang(target)
    t = config.tr(lang=lang)
    sets = {}
    for kv in a.set:
        k, sep, v = kv.partition("=")
        if not sep or k not in config.SCALAR_KEYS:
            ap.error(t(f"모르는 설정: {k or kv} — 쓸 수 있는 키: {', '.join(config.SCALAR_KEYS)}",
                       f"unknown setting: {k or kv}. Keys you can set: {', '.join(config.SCALAR_KEYS)}"))
        why = config.invalid(k, v, lang)
        if why:
            ap.error(f"{k}: {why}")
        sets[k] = os.path.expanduser(v.strip()) if k == "BATON_LOG" else v.strip()  # "~/…"를 펼쳐 둔다
    for k in a.unset:
        if k not in config.SCALAR_KEYS + config.LIST_KEYS:
            ap.error(t(f"모르는 키: {k}", f"unknown key: {k}"))
    def read_terms(path, flag):
        """단어 파일(또는 '-' 표준 입력)의 줄들. BOM은 뗀다. 못 읽으면 단어를 출력하지 않고 멈춘다."""
        if not path:
            return []
        try:
            with (sys.stdin if path == "-" else open(path, encoding="utf-8-sig")) as f:
                return f.read().lstrip("\ufeff").splitlines()
        except UnicodeDecodeError:
            ap.error(t(f"{flag}: UTF-8로 읽히지 않는다 — UTF-8로 저장한 뒤 다시 한다",
                       f"{flag}: not readable as UTF-8. Save the file as UTF-8 and run again"))
        except OSError as e:
            ap.error(t(f"{flag}을 못 읽었다: {e.strerror}", f"could not read {flag}: {e.strerror}"))

    lists = {"add": {"private_terms": a.private_term + read_terms(a.private_terms_file, "--private-terms-file"),
                     "BATON_HANDOFF_TRIGGERS_EXTRA": a.trigger},
             "remove": {"private_terms": a.remove_term + read_terms(a.remove_terms_file, "--remove-terms-file"),
                        "BATON_HANDOFF_TRIGGERS_EXTRA": a.remove_trigger}}
    for op in lists:
        for k in lists[op]:
            items = [x.strip() for x in lists[op][k] if x.strip()]
            if op == "add" and any(config.invalid(k, x, lang) for x in items):
                what = t("개인 자료 단어", "private word") if k == "private_terms" else t("트리거 말", "trigger phrase")
                ap.error(f"{what}: {config.invalid(k, 'x', lang)}")  # 단어는 다시 출력하지 않는다
            lists[op][k] = items
        lists[op] = {k: v for k, v in lists[op].items() if v}
    add, remove = lists["add"], lists["remove"]
    repo = None if a.is_global else target
    if repo and any(k in config.GLOBAL_ONLY for k in list(sets) + a.unset):
        ap.error(t(f"{', '.join(config.GLOBAL_ONLY)}는 전역에만 둔다 — --global을 붙인다",
                   f"{', '.join(config.GLOBAL_ONLY)} can only go in the global section. Add --global"))
    if not (sets or a.unset or add or remove):
        ap.error(t("바꿀 것이 없다", "nothing to change"))
    removed = {}
    try:
        p = config.update(repo, sets, a.unset, add, remove, removed)
    except (ValueError, OSError) as e:
        sys.exit(t(f"[baton-setup] 쓰지 못했다: {e}", f"[baton-setup] Could not write: {e}"))
    where = t("전역 절", "the global section") if repo is None else t(f"저장소 절({repo})", f"the section for {repo}")
    print(t(f"[baton-setup] {p}의 {where}에 썼다(파일 600).", f"[baton-setup] Wrote to {where} in {p} (file mode 600)."))
    for k, v in sets.items():
        print(f"  {k}={v}")
    for k in a.unset:
        print(t(f"  {k} 지움 — 이제 전역 절·코드 기본값을 따른다", f"  {k} removed. The global section or the code default applies now"))
    if "private_terms" in add:
        n = len(add["private_terms"])
        print(t(f"  개인 자료 목록 단어 {n}개 추가(이 출력에는 단어를 적지 않는다)",
                f"  Added {n} {'word' if n == 1 else 'words'} to the private-words list (this output does not show them)"))
    if "BATON_HANDOFF_TRIGGERS_EXTRA" in add:
        print(t(f"  인계 트리거 추가 말 추가: {', '.join(add['BATON_HANDOFF_TRIGGERS_EXTRA'])}",
                f"  Added extra trigger phrases: {', '.join(add['BATON_HANDOFF_TRIGGERS_EXTRA'])}"))
    data = config.load() or {}
    for k, items in remove.items():
        name = (t("개인 자료 목록 단어", "words from the private-words list") if k == "private_terms"
                else t("인계 트리거 추가 말", "extra trigger phrases"))
        gone = removed.get(k, 0)
        print(t(f"  {name} {len(items)}개 중 {gone}개를 {where}에서 뺌", f"  Removed {gone} of {len(items)} {name} from {where}")
              + (t(" — 나머지는 이 절에 없었다", ". The rest were not in this section") if gone < len(items) else ""))
        # 다른 절에 남아 있으면 여전히 적용된다 — 저장소 절에서 뺐으면 전역 절, 전역에서 뺐으면 저장소 절들을 본다
        others = [data.get("global")] if repo else list((data.get("repos") or {}).values())
        drop = {x.casefold() for x in items}
        left = sum(1 for sec in others if isinstance(sec, dict) and isinstance(sec.get(k), list)
                   and any(isinstance(x, str) and x.strip().casefold() in drop for x in sec[k]))
        if left:
            print(t(f"  주의: 뺀 것 일부가 다른 {'전역 절' if repo else f'저장소 절 {left}곳'}에 남아 여전히 적용된다"
                    f"({'--global을 붙여' if repo else '그 저장소에서'} 다시 뺀다)",
                    f"  Note: some of them are still in {'the global section' if repo else f'{left} other repo section(s)'} "
                    f"and still apply (remove them again {'with --global' if repo else 'from that repo'})"))
    print(t("  되돌리기: apply --unset <키> · --remove-terms-file <경로> · --remove-trigger <말>(전역이면 --global). "
            "같은 이름의 환경변수가 설정 파일보다 우선한다",
            "  To undo: apply --unset <key> · --remove-terms-file <path> · --remove-trigger <phrase> (add --global for the "
            "global section). An environment variable with the same name wins over the config file"))


def main(argv):
    if argv and argv[0] == "apply":
        return apply(argv[1:])
    t = config.tr(here())
    ap = argparse.ArgumentParser(description=t(__doc__.splitlines()[0],
                                               "/baton-setup scanner: proposes baton thresholds and private-word candidates "
                                               "from this user's own history. Read only."))
    ap.add_argument("repo", nargs="?")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    r = scan(here(a.repo))
    print(json.dumps(r, ensure_ascii=False, indent=2) if a.json else render(r))


if __name__ == "__main__":
    main(sys.argv[1:])
