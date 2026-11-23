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


def from_locale():
    for k in ("LC_ALL", "LC_MESSAGES", "LANG"):
        v = os.environ.get(k)
        if v:
            return "ko" if v.lower().startswith("ko") else "en"
    return "en"


def lang(repo=None):
    v = config.get("BATON_LANG", repo, "").strip().lower()
    return v if v in LANGS else from_locale()


def pick(repo, ko, en):
    """ko if the language for this repo is Korean, otherwise en."""
    return ko if lang(repo) == "ko" else en


if __name__ == "__main__":
    print(lang(sys.argv[1] if len(sys.argv) > 1 else None))
