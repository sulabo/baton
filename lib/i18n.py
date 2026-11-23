#!/usr/bin/env python3
"""Output language for baton's hooks and scripts: "ko" or "en".

Order: BATON_LANG (environment > repo section > global section of the baton config) > system locale > "en".
BATON_LANG takes ko, en, or auto (auto = follow the locale). Any other value also falls back to the locale.
Locale: the first non-empty of LC_ALL, LC_MESSAGES, LANG (POSIX order). A value starting with "ko" means Korean.

Only the language of messages depends on this. File formats (HANDOFF.md headings, CONCEPTS.md keys) are read
in both languages whatever this says.

  i18n.py [repo root]   prints ko or en (for shell scripts)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402

LANGS = ("ko", "en")


def _locale():
    """(language, "VAR=value" that decided it), or ("en", None) when no locale variable is set."""
    for k in ("LC_ALL", "LC_MESSAGES", "LANG"):
        v = os.environ.get(k)
        if v:
            return ("ko" if v.lower().startswith("ko") else "en"), f"{k}={v}"
    return "en", None


def from_locale():
    return _locale()[0]


def where(repo=None):
    """(language, source). source: "env" (BATON_LANG environment variable), "config" (BATON_LANG in the config file),
    "LANG=ko_KR.UTF-8"-style locale variable, or "default" (nothing set)."""
    v = config.get("BATON_LANG", repo, "").strip().lower()
    if v in LANGS:
        return v, "env" if "BATON_LANG" in os.environ else "config"
    lang_, var = _locale()
    return lang_, var or "default"


def lang(repo=None):
    return where(repo)[0]


def pick(repo, ko, en):
    """ko if the language for this repo is Korean, otherwise en."""
    return ko if lang(repo) == "ko" else en


if __name__ == "__main__":
    print(lang(sys.argv[1] if len(sys.argv) > 1 else None))
