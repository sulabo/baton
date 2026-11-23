#!/usr/bin/env python3
"""Output language for baton's hooks and scripts: "ko" or "en".

Order: BATON_LANG (environment > repo section > global section of the baton config) > system locale > "en".
BATON_LANG takes ko, en, or auto (auto = follow the locale). Any other value also falls back to the locale.
An empty BATON_LANG in the environment counts as unset, so it doesn't hide the config value.
Locale: the first non-empty of LC_ALL, LC_MESSAGES, LANG (POSIX order). When none is set on macOS (an app started
outside a terminal), the first entry of `defaults read -g AppleLanguages`. A value means Korean when it is "ko" or
starts with "ko" followed by _ . @ or - (case-insensitive), so "ko_KR.UTF-8" and "ko-KR" are Korean, "kok_IN" is not.

Only the language of messages depends on this. File formats (HANDOFF.md headings, CONCEPTS.md keys) are read
in both languages whatever this says.

  i18n.py [repo root]   prints ko or en (for shell scripts)
"""
import functools
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402

LANGS = ("ko", "en")
KOREAN = re.compile(r"ko(?:$|[_.@-])", re.I)  # lib/lib.sh baton_lang_sh와 같은 규칙


def is_korean(value):
    return bool(KOREAN.match(value))


@functools.lru_cache(maxsize=None)
def _apple_languages():
    """macOS 시스템 언어 목록의 첫 항목("ko-KR"). macOS가 아니거나 못 읽으면(없음·1초 넘김·형식 다름) None. 실행마다 한 번."""
    if sys.platform != "darwin":
        return None
    try:
        r = subprocess.run(["defaults", "read", "-g", "AppleLanguages"], capture_output=True, text=True, timeout=1)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    for line in r.stdout.splitlines():  # (\n    "ko-KR",\n    "en-US"\n)
        v = line.strip().rstrip(",").strip().strip('"')
        if v and v not in ("(", ")"):
            return v
    return None


def _locale():
    """(language, "VAR=value" that decided it), or ("en", None) when nothing is set.
    AppleLanguages is read only when no locale variable is set."""
    for k in ("LC_ALL", "LC_MESSAGES", "LANG"):
        v = os.environ.get(k)
        if v:
            return ("ko" if is_korean(v) else "en"), f"{k}={v}"
    v = _apple_languages()
    if v:
        return ("ko" if is_korean(v) else "en"), f"AppleLanguages={v}"
    return "en", None


def from_locale():
    return _locale()[0]


def where(repo=None):
    """(language, source). source: "env" (BATON_LANG environment variable), "config" (BATON_LANG in the config file),
    "LANG=ko_KR.UTF-8"-style locale variable, "AppleLanguages=ko-KR" (macOS, no locale variable), or "default"."""
    v = os.environ.get("BATON_LANG", "").strip().lower()
    if v:  # 환경변수가 이긴다 — auto나 모르는 값이면 로캘로
        if v in LANGS:
            return v, "env"
    else:  # 비어 있는 환경변수는 없는 것으로 — 설정 파일 값을 가리지 않게
        v = config.get("BATON_LANG", repo, "", env=False).strip().lower()
        if v in LANGS:
            return v, "config"
    lang_, var = _locale()
    return lang_, var or "default"


def lang(repo=None):
    return where(repo)[0]


def pick(repo, ko, en):
    """ko if the language for this repo is Korean, otherwise en."""
    return ko if lang(repo) == "ko" else en


if __name__ == "__main__":
    print(lang(sys.argv[1] if len(sys.argv) > 1 else None))
