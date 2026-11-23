#!/usr/bin/env python3
"""baton 설정 파일 — /baton-setup에서 사용자가 승인한 값만 들어 있다. 훅과 lib이 환경변수 대신 이것으로 읽는다.

위치: ${XDG_CONFIG_HOME:-$HOME/.config}/baton/config.json
모양: {"version": 1, "global": {...}, "repos": {"<git 최상위 폴더 — 실제 경로·NFC>": {...}}}
저장소 절의 키는 늘 repo_key()로 만든다 — 쓰는 쪽(apply)과 읽는 쪽(훅)이 같은 함수를 쓴다. 하위 폴더에서 열어도 git 최상위로 모인다.
키는 기존 환경변수 이름 그대로(값은 환경변수처럼 문자열), 목록 키는 private_terms·BATON_HANDOFF_TRIGGERS_EXTRA.
우선순위: 실제 환경변수 > 저장소 절 > 전역 절 > 코드 기본값. 목록 키는 전역 목록에 저장소 목록을 더한다.

읽기: 파일 없음·못 읽음·깨진 JSON·너무 큼(1MB 초과)·타입 틀림·HOME 없음은 전부 "설정 없음"으로 친다. 훅이 죽거나 stdout에 쓰면 안 된다.
쓰기: 폴더는 새로 만들 때 700, 파일 600, 임시 파일에 쓴 뒤 바꿔치기(다른 저장소 절은 그대로, 심볼릭 링크면 가리키는 파일에).
깨진 파일은 덮어쓰지 않는다.

  config.py [저장소 루트]   설정 파일 위치와 읽히는지, 이 저장소에 적용되는 값을 보여 준다(바꾸는 것 없음)
"""
import copy, json, math, os, subprocess, sys, tempfile, unicodedata

VERSION = 1
LIST_KEYS = ("private_terms", "BATON_HANDOFF_TRIGGERS_EXTRA")
SCALAR_KEYS = ("BATON_SPLIT_NOTICE", "BATON_SPLIT_RATIOS", "BATON_HANDOFF_INJECT", "BATON_CONCEPT_INJECT",
               "BATON_CONCEPT_INDEX",
               "BATON_HANDOFF_CHECK", "BATON_HANDOFF_NUDGE", "BATON_HANDOFF_NUDGE_FILES", "BATON_OBSERVE", "BATON_LOG",
               "BATON_LANG", "BATON_HANDOFF_AUTO")
GLOBAL_ONLY = ("BATON_OBSERVE", "BATON_LOG")  # 관찰 로그는 저장소를 모르는 자리에서도 쓰여 전역만 읽는다
SWITCH_KEYS = ("BATON_SPLIT_NOTICE", "BATON_HANDOFF_INJECT", "BATON_CONCEPT_INJECT", "BATON_CONCEPT_INDEX", "BATON_HANDOFF_CHECK",
               "BATON_HANDOFF_NUDGE", "BATON_HANDOFF_AUTO", "BATON_OBSERVE")
SWITCH_VALUES = ("on", "off", "1", "0", "true", "false", "yes", "no")  # 훅의 on()/off()가 알아듣는 값
MAX_BYTES = 1024 * 1024
_tops = {}    # 경로 → 저장소 절 키(프로세스 안 캐시)
_loaded = {}  # 파일 서명 → 파싱 결과(프로세스 안 캐시)


def path():
    """설정 파일 경로. HOME·XDG_CONFIG_HOME이 둘 다 없으면 None."""
    base = os.environ.get("XDG_CONFIG_HOME") or (os.path.join(os.environ["HOME"], ".config") if os.environ.get("HOME") else "")
    return os.path.join(base, "baton", "config.json") if base else None


def repo_key(repo):
    """저장소 절의 키 — 그 경로가 든 git 최상위 폴더(git이 아니면 그 경로), 실제 경로·NFC(baton_init.norm과 같은 정규화).
    CLAUDE_PROJECT_DIR가 하위 폴더여도 apply가 쓴 절과 같은 키가 된다. 워크트리는 최상위가 따로라 절도 따로다.
    git은 설정 파일이 있을 때만 불린다(sections·update·status만 부른다). 프로세스 안에서 경로마다 한 번."""
    d = os.path.realpath(os.path.expanduser(str(repo)))
    if d not in _tops:
        top = ""
        try:
            r = subprocess.run(["git", "-C", d, "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=5)
            top = r.stdout.strip() if r.returncode == 0 else ""
        except Exception:
            pass  # git이 없거나 멈춤 — 경로 그대로
        _tops[d] = unicodedata.normalize("NFC", os.path.realpath(top or d))
    return _tops[d]


def load():
    """설정 전체(dict). 없거나 못 읽거나 1MB를 넘거나 모양이 틀리면 None. 파일이 그대로면 프로세스 안에서 한 번만 파싱한다."""
    p = path()
    if not p:
        return None
    try:
        st = os.stat(p)
        sig = (p, st.st_ino, st.st_size, st.st_mtime_ns)
        if sig in _loaded:
            return _loaded[sig]
        data = None
        if st.st_size <= MAX_BYTES:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
    except Exception:  # 깊게 중첩된 JSON은 RecursionError — 무엇이든 "설정 없음"
        return None
    data = data if isinstance(data, dict) else None
    _loaded.clear()
    _loaded[sig] = data
    return data


def tr(repo=None, lang=None):
    """한국어·영어 문장 중 출력 언어(lib/i18n.py) 쪽을 고르는 함수. lang을 주면 그것을 쓴다.
    i18n이 이 모듈을 불러오므로 맨 위가 아니라 여기서 부른다."""
    import i18n
    ko = (lang or i18n.lang(repo)) == "ko"
    return lambda k, e: k if ko else e


def invalid(key, value, lang=None):
    """apply가 받을 수 없는 값이면 이유(한 줄), 받을 수 있으면 None. 훅이 조용히 기본값으로 떨어지는 값을 미리 막는다.
    lang: 이유의 언어("ko"/"en"). 없으면 lib/i18n.py로 정한다."""
    v = value.strip()
    why = None
    if key == "BATON_SPLIT_RATIOS":
        try:
            xs = [float(x) for x in v.split(",")]
        except ValueError:
            xs = []
        if not xs or not all(math.isfinite(x) and x >= 1 for x in xs):
            why = ("쉼표로 나눈 1 이상 숫자여야 한다(예: 2,3)", "must be numbers of 1 or more, separated by commas (for example 2,3)")
    elif key == "BATON_HANDOFF_NUDGE_FILES":
        if not (v.isdigit() and int(v) >= 1):
            why = ("1 이상 정수여야 한다", "must be a whole number of 1 or more")
    elif key in SWITCH_KEYS:
        if v.lower() not in SWITCH_VALUES:
            why = (f"{'/'.join(SWITCH_VALUES)} 중 하나여야 한다", f"must be one of {'/'.join(SWITCH_VALUES)}")
    elif key == "BATON_LANG":
        if v.lower() not in ("ko", "en", "auto"):
            why = ("ko, en, auto 중 하나여야 한다", "must be one of ko, en, auto")
    elif key == "BATON_LOG":
        if not os.path.isabs(os.path.expanduser(v)):
            why = ("절대 경로여야 한다", "must be an absolute path")
    elif key in LIST_KEYS:
        if len(v) < 2:
            why = ("두 글자 이상이어야 한다(한 글자는 거의 모든 글에 걸린다)",
                   "must be at least two characters long (a single character matches almost any text)")
    else:
        why = ("모르는 키", "unknown key")
    return tr(lang=lang)(*why) if why else None


def sections(repo=None):
    """적용 순서대로 [저장소 절, 전역 절]. dict가 아닌 절은 뺀다."""
    data = load() or {}
    out = []
    repos = data.get("repos")
    if repo and isinstance(repos, dict):
        try:
            sec = repos.get(repo_key(repo))
        except (OSError, ValueError):
            sec = None
        if isinstance(sec, dict):
            out.append(sec)
    if isinstance(data.get("global"), dict):
        out.append(data["global"])
    return out


def get(name, repo=None, default="", env=True):
    """환경변수 > 저장소 절 > 전역 절 > default. 값은 환경변수와 같은 모양(문자열). env=False면 환경변수를 건너뛴다."""
    v = os.environ.get(name) if env else None
    if v is not None:
        return v
    secs = sections(None if name in GLOBAL_ONLY else repo)
    for sec in secs:
        x = sec.get(name)
        if isinstance(x, (str, int, float)) and not isinstance(x, bool):
            return str(x)
    return default


def terms(name, repo=None):
    """목록 설정. BATON_ 환경변수가 있으면 그것(쉼표 구분)만, 없으면 전역 목록 + 저장소 목록. 문자열이 아닌 항목·빈 항목은 버린다."""
    if name.startswith("BATON_") and name in os.environ:
        items = os.environ[name].split(",")
    else:
        items = []
        for sec in reversed(sections(repo)):  # 전역 먼저, 저장소가 더한다
            x = sec.get(name)
            if isinstance(x, list):
                items += x
    out = []
    for x in items:
        x = x.replace("\ufeff", "").strip() if isinstance(x, str) else ""  # BOM이 붙은 단어는 안 맞는다 — 떼고 본다
        if x and x not in out:
            out.append(x)
    return out


def update(repo=None, set_=None, unset=(), add=None, remove=None, removed=None):
    """승인된 값만 쓴다. repo가 있으면 그 저장소 절, 없으면 전역 절. 쓴 파일 경로를 돌려준다.
    set_: {키: 문자열} 덮어씀 · unset: 지울 키 · add/remove: {목록 키: [항목]} 기존 목록에 더함(중복 제외)/뺌(대소문자 무시 — 검사도 그렇게 맞춘다).
    removed: dict를 주면 {목록 키: 실제로 뺀 항목 수}를 채운다."""
    p = path()
    if not p:
        raise ValueError(tr(repo)("HOME·XDG_CONFIG_HOME이 없어 설정 파일 위치를 정할 수 없다",
                                  "neither HOME nor XDG_CONFIG_HOME is set, so there is no place for the config file"))
    data = {"version": VERSION, "global": {}, "repos": {}}
    if os.path.exists(p):
        old = load()
        if old is None:
            raise ValueError(tr(repo)(f"{p}를 읽을 수 없거나 JSON이 깨져 있다 — 덮어쓰지 않는다. 고치거나 지운 뒤 다시 한다",
                                      f"{p} can't be read or is not valid JSON. Not overwriting it. Fix or delete it, then run again"))
        data.update(copy.deepcopy(old))  # 캐시된 객체를 고치지 않는다 — 쓰기가 실패하면 옛 값이 그대로 보여야 한다
    if not isinstance(data.get("repos"), dict) or not isinstance(data.get("global"), dict):
        raise ValueError(tr(repo)(f"{p}의 global·repos가 객체가 아니다 — 덮어쓰지 않는다",
                                  f"global or repos in {p} is not an object. Not overwriting it"))
    sec = data["repos"].setdefault(repo_key(repo), {}) if repo else data["global"]
    if not isinstance(sec, dict):
        raise ValueError(tr(repo)(f"{p}의 이 저장소 절이 객체가 아니다 — 덮어쓰지 않는다",
                                  f"this repo's section in {p} is not an object. Not overwriting it"))
    for k, v in (set_ or {}).items():
        sec[k] = str(v)
    for k in unset:
        sec.pop(k, None)
    for k, items in (add or {}).items():
        cur = sec.get(k) if isinstance(sec.get(k), list) else []
        sec[k] = cur + [x for x in items if x not in cur]
    for k, items in (remove or {}).items():
        drop = {x.casefold() for x in items}
        cur = sec.get(k) if isinstance(sec.get(k), list) else []
        keep = [x for x in cur if not (isinstance(x, str) and x.strip().casefold() in drop)]
        if removed is not None:
            removed[k] = len(cur) - len(keep)
        if keep:
            sec[k] = keep
        else:
            sec.pop(k, None)
    if repo and not sec:
        data["repos"].pop(repo_key(repo))
    p = os.path.realpath(p)  # 심볼릭 링크(점파일 저장소 등)는 링크를 일반 파일로 바꾸지 않고 가리키는 파일에 쓴다
    d = os.path.dirname(p)
    if not os.path.isdir(d):
        os.makedirs(d, mode=0o700)
        os.chmod(d, 0o700)  # makedirs의 mode는 umask를 탄다
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".config.json.")  # mkstemp는 600으로 만든다
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    _loaded.clear()
    return p


def language_source(src, t):
    """lib/i18n.py where()의 source를 사람이 읽는 말로."""
    if src == "env":
        src = t("환경변수 BATON_LANG", "the BATON_LANG environment variable")
    elif src == "config":
        src = t("설정 파일의 BATON_LANG", "BATON_LANG in the config file")
    elif src.startswith("AppleLanguages="):
        src = t(f"macOS 언어 목록 {src}", f"the macOS language list, {src}")
    elif src == "default":
        src = t("기본값 — BATON_LANG도 로캘 변수도 없다", "the default, as neither BATON_LANG nor a locale variable is set")
    else:
        src = t(f"로캘 {src}", f"the locale, {src}")
    return src


def language_line(repo, t):
    """출력 언어와 그것을 정한 곳 한 줄."""
    import i18n
    lang, src = i18n.where(repo)
    return t(f"출력 언어: {lang}(정한 곳: {language_source(src, t)})", f"Output language: {lang} (source: {language_source(src, t)})")


def status(repo=None, lang=None):
    """사람이 읽는 설정 상태 몇 줄. 마지막 줄은 출력 언어와 그것을 정한 곳. lang: 이 줄들의 언어(없으면 i18n으로 정한다)."""
    t = tr(repo, lang)
    p = path()
    if not p:
        return [t("설정 파일: 위치를 못 정함(HOME·XDG_CONFIG_HOME 없음) — 코드 기본값과 환경변수만 쓴다",
                  "Config file: no location (neither HOME nor XDG_CONFIG_HOME is set). Only code defaults and environment "
                  "variables apply"), language_line(repo, t)]
    if not os.path.exists(p):
        return [t(f"설정 파일: 없음({p}) — /baton-setup을 아직 안 돌렸다. 코드 기본값과 환경변수만 쓴다",
                  f"Config file: none ({p}). /baton-setup has not been run. Only code defaults and environment variables apply"),
                language_line(repo, t)]
    data = load()
    if data is None:
        return [t(f"설정 파일: 있지만 못 읽음({p}) — 깨진 JSON이거나 권한 문제. 훅은 설정 없이 돈다",
                  f"Config file: present but unreadable ({p}): broken JSON or a permission problem. The hooks run without it"),
                language_line(repo, t)]
    lines = [t(f"설정 파일: 읽힘({p}, 권한 {oct(os.stat(p).st_mode & 0o777)[2:]})",
               f"Config file: read ({p}, mode {oct(os.stat(p).st_mode & 0o777)[2:]})")]
    if repo:
        repos = data.get("repos") if isinstance(data.get("repos"), dict) else {}
        has = repo_key(repo) in repos
        lines.append(t(f"이 저장소 절: {'있음' if has else '없음'}", f"Section for this repo: {'yes' if has else 'no'}"))
        for k in SCALAR_KEYS:
            v = get(k, repo, None)
            if v is not None:
                lines.append(f"  {k}={v}{t(' (환경변수)', ' (environment variable)') if k in os.environ else ''}")
        for k in LIST_KEYS:
            n = len(terms(k, repo))
            if n:  # 개인 자료 단어 자체는 다시 출력하지 않는다
                lines.append(t(f"  {k}: {n}개", f"  {k}: {n} {'entry' if n == 1 else 'entries'}"))
    return lines + [language_line(repo, t)]


if __name__ == "__main__":
    # 경로를 안 주면 훅처럼 CLAUDE_PROJECT_DIR, 없으면 지금 폴더 — 어느 쪽이든 repo_key가 git 최상위로 모은다
    print("\n".join(status(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())))
