#!/usr/bin/env python3
"""lib/i18n.py: BATON_LANG (env > config) > locale > en."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

LIB = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, LIB)
import i18n  # noqa: E402
SCRIPT = os.path.join(LIB, "i18n.py")
LOCALE_KEYS = ("LC_ALL", "LC_MESSAGES", "LANG", "BATON_LANG")


def run(env_extra, config=None):
    """i18n.py를 따로 띄운다. PATH에 아무것도 없게 해 macOS의 defaults(AppleLanguages)도 못 읽는 자리 — 로캘 변수만 본다."""
    with tempfile.TemporaryDirectory() as home:
        env = {k: v for k, v in os.environ.items() if k not in LOCALE_KEYS}
        env.update(HOME=home, XDG_CONFIG_HOME=os.path.join(home, ".config"), PATH=home)
        if config is not None:
            d = os.path.join(home, ".config", "baton")
            os.makedirs(d)
            with open(os.path.join(d, "config.json"), "w") as f:
                json.dump({"version": 1, "global": config}, f)
        env.update(env_extra)
        r = subprocess.run([sys.executable, SCRIPT], capture_output=True, text=True, env=env, cwd=home)
        return r.stdout.strip()


class LangTest(unittest.TestCase):
    def test_default_without_locale_is_english(self):
        self.assertEqual(run({}), "en")

    def test_locale_decides_when_unset(self):
        self.assertEqual(run({"LANG": "ko_KR.UTF-8"}), "ko")
        self.assertEqual(run({"LANG": "en_US.UTF-8"}), "en")
        self.assertEqual(run({"LANG": "C.UTF-8"}), "en")

    def test_locale_order_is_posix(self):
        self.assertEqual(run({"LANG": "en_US.UTF-8", "LC_ALL": "ko_KR.UTF-8"}), "ko")
        self.assertEqual(run({"LANG": "ko_KR.UTF-8", "LC_MESSAGES": "en_US.UTF-8"}), "en")

    def test_env_wins_over_locale(self):
        self.assertEqual(run({"LANG": "en_US.UTF-8", "BATON_LANG": "ko"}), "ko")
        self.assertEqual(run({"LANG": "ko_KR.UTF-8", "BATON_LANG": "EN"}), "en")

    def test_auto_and_unknown_values_follow_locale(self):
        self.assertEqual(run({"LANG": "ko_KR.UTF-8", "BATON_LANG": "auto"}), "ko")
        self.assertEqual(run({"LANG": "en_US.UTF-8", "BATON_LANG": "fr"}), "en")

    def test_global_config_is_read(self):
        self.assertEqual(run({"LANG": "en_US.UTF-8"}, {"BATON_LANG": "ko"}), "ko")
        self.assertEqual(run({"LANG": "ko_KR.UTF-8", "BATON_LANG": "en"}, {"BATON_LANG": "ko"}), "en")

    def test_config_rejects_other_values(self):
        sys.path.insert(0, LIB)
        import config
        self.assertIsNone(config.invalid("BATON_LANG", "ko"))
        self.assertIsNone(config.invalid("BATON_LANG", "auto"))
        self.assertIsNotNone(config.invalid("BATON_LANG", "kr"))


class WhereTest(unittest.TestCase):
    """where(): 언어와 그것을 정한 곳. lang()은 where()의 첫 값이라 둘이 어긋나지 않는다."""

    def where(self, env, config=None, apple=None):
        """apple: macOS 언어 목록의 첫 항목인 척하는 값(None이면 못 읽음)."""
        with tempfile.TemporaryDirectory() as home:
            e = {k: v for k, v in os.environ.items() if k not in LOCALE_KEYS}
            e.update(HOME=home, XDG_CONFIG_HOME=os.path.join(home, ".config"), **env)
            if config is not None:
                os.makedirs(os.path.join(home, ".config", "baton"))
                with open(os.path.join(home, ".config", "baton", "config.json"), "w") as f:
                    json.dump({"version": 1, "global": config}, f)
            with mock.patch.dict(os.environ, e, clear=True), mock.patch.object(i18n, "_apple_languages", lambda: apple):
                got = i18n.where()
                self.assertEqual(i18n.lang(), got[0])
                return got

    def test_sources(self):
        self.assertEqual(self.where({"BATON_LANG": "ko"}), ("ko", "env"))
        self.assertEqual(self.where({"LANG": "en_US.UTF-8"}, {"BATON_LANG": "ko"}), ("ko", "config"))
        self.assertEqual(self.where({"LANG": "ko_KR.UTF-8", "BATON_LANG": "auto"}, {"BATON_LANG": "en"}), ("ko", "LANG=ko_KR.UTF-8"))
        self.assertEqual(self.where({"LC_MESSAGES": "C.UTF-8", "LANG": "ko_KR.UTF-8"}), ("en", "LC_MESSAGES=C.UTF-8"))
        self.assertEqual(self.where({}), ("en", "default"))

    def test_empty_env_does_not_hide_config(self):
        for empty in ("", "  "):
            self.assertEqual(self.where({"BATON_LANG": empty, "LANG": "en_US.UTF-8"}, {"BATON_LANG": "ko"}), ("ko", "config"))
            self.assertEqual(self.where({"BATON_LANG": empty, "LANG": "ko_KR.UTF-8"}), ("ko", "LANG=ko_KR.UTF-8"))
        self.assertEqual(run({"BATON_LANG": "", "LANG": "en_US.UTF-8"}, {"BATON_LANG": "ko"}), "ko")

    def test_korean_rule_is_ko_then_separator(self):
        for v, want in (("ko", "ko"), ("KO", "ko"), ("ko_KR.UTF-8", "ko"), ("ko.UTF-8", "ko"), ("ko@x", "ko"), ("ko-KR", "ko"),
                        ("kok_IN", "en"), ("kok", "en"), ("korean", "en"), ("C.UTF-8", "en"), ("en_US.UTF-8", "en")):
            with self.subTest(v=v):
                self.assertEqual(self.where({"LANG": v})[0], want)
                self.assertEqual(self.where({}, apple=v)[0], want)

    def test_apple_languages_when_no_locale(self):
        self.assertEqual(self.where({}, apple="ko-KR"), ("ko", "AppleLanguages=ko-KR"))
        self.assertEqual(self.where({}, apple="en-US"), ("en", "AppleLanguages=en-US"))
        self.assertEqual(self.where({"BATON_LANG": "en"}, apple="ko-KR"), ("en", "env"))


class AppleLanguagesTest(unittest.TestCase):
    """macOS에서 로캘 변수가 하나도 없을 때만 defaults read -g AppleLanguages를 1초 안에 읽는다. 무슨 실패든 None(→ en)."""

    def setUp(self):
        i18n._apple_languages.cache_clear()
        self.addCleanup(i18n._apple_languages.cache_clear)
        env = {k: v for k, v in os.environ.items() if k not in LOCALE_KEYS}
        env["XDG_CONFIG_HOME"] = os.path.join(os.devnull, "none")  # 실제 설정 파일의 BATON_LANG을 읽지 않는다
        p = mock.patch.dict(os.environ, env, clear=True)
        p.start(); self.addCleanup(p.stop)

    def fake(self, stdout="", code=0, exc=None):
        calls = []

        def run_(args, **kw):
            calls.append((args, kw))
            if exc:
                raise exc
            return subprocess.CompletedProcess(args, code, stdout, "")
        return calls, mock.patch.object(i18n.subprocess, "run", run_)

    def test_reads_first_entry_on_macos(self):
        calls, p = self.fake('(\n    "ko-KR",\n    "en-US"\n)\n')
        with p, mock.patch.object(i18n.sys, "platform", "darwin"):
            self.assertEqual(i18n.where(), ("ko", "AppleLanguages=ko-KR"))
            self.assertEqual(i18n.where(), ("ko", "AppleLanguages=ko-KR"))
        self.assertEqual(len(calls), 1)  # 한 실행에 한 번만 띄운다
        self.assertEqual(calls[0][0], ["defaults", "read", "-g", "AppleLanguages"])
        self.assertEqual(calls[0][1]["timeout"], 1)

    def test_bare_entry(self):
        calls, p = self.fake("(\n    en,\n    ko\n)\n")
        with p, mock.patch.object(i18n.sys, "platform", "darwin"):
            self.assertEqual(i18n.where(), ("en", "AppleLanguages=en"))

    def test_not_read_when_a_locale_variable_is_set(self):
        for k in ("LC_ALL", "LC_MESSAGES", "LANG"):
            calls, p = self.fake('(\n    "ko-KR"\n)')
            with p, mock.patch.object(i18n.sys, "platform", "darwin"), mock.patch.dict(os.environ, {k: "C.UTF-8"}):
                self.assertEqual(i18n.where(), ("en", f"{k}=C.UTF-8"))
            self.assertEqual(calls, [], k)

    def test_not_read_off_macos(self):
        calls, p = self.fake('(\n    "ko-KR"\n)')
        with p, mock.patch.object(i18n.sys, "platform", "linux"):
            self.assertEqual(i18n.where(), ("en", "default"))
        self.assertEqual(calls, [])

    def test_any_failure_is_english(self):
        for kw in ({"exc": FileNotFoundError()}, {"exc": subprocess.TimeoutExpired("defaults", 1)}, {"code": 1},
                   {"stdout": ""}, {"stdout": "(\n)\n"}):
            i18n._apple_languages.cache_clear()
            calls, p = self.fake(**kw)
            with p, mock.patch.object(i18n.sys, "platform", "darwin"):
                self.assertEqual(i18n.where(), ("en", "default"), kw)


class ShellFallbackTest(unittest.TestCase):
    """lib/lib.sh baton_lang: python3가 없으면 BATON_LANG 환경변수 > 로캘(LC_ALL·LC_MESSAGES·LANG 중 처음 비지 않은 것) > en.
    한국어 규칙은 i18n.py와 같다(kok_IN은 한국어가 아니다)."""

    def lang(self, env, python=False):
        with tempfile.TemporaryDirectory() as d:
            bin_ = os.path.join(d, "bin")
            os.makedirs(bin_)
            for tool in ("dirname",) + (("python3",) if python else ()):  # lib.sh가 HERE를 정할 때 dirname을 쓴다
                os.symlink(sys.executable if tool == "python3" else shutil.which(tool), os.path.join(bin_, tool))
            e = {"PATH": bin_, "HOME": d, "XDG_CONFIG_HOME": os.path.join(d, "none")}
            e.update(env)
            r = subprocess.run(["/bin/bash", "-c", '. "$1"; command -v python3 >/dev/null && echo has-python; ROOT=. baton_lang',
                                "x", os.path.join(LIB, "lib.sh")], capture_output=True, text=True, env=e, cwd=d)
            self.assertEqual(r.returncode, 0, r.stderr)
            out = r.stdout.split()
            self.assertEqual("has-python" in out, python)  # python3가 정말 없는 자리에서 돌았다
            return out[-1]

    def test_without_python_uses_locale(self):
        cases = [({"LANG": "ko_KR.UTF-8"}, "ko"), ({"LANG": "ko-KR"}, "ko"), ({"LANG": "kok_IN"}, "en"), ({"LANG": "C.UTF-8"}, "en"),
                 ({}, "en"), ({"LC_ALL": "C.UTF-8", "LANG": "ko_KR.UTF-8"}, "en"), ({"LC_ALL": "", "LC_MESSAGES": "ko_KR"}, "ko"),
                 ({"BATON_LANG": "ko", "LANG": "C.UTF-8"}, "ko"), ({"BATON_LANG": "EN", "LANG": "ko_KR.UTF-8"}, "en"),
                 ({"BATON_LANG": "auto", "LANG": "ko_KR.UTF-8"}, "ko")]
        for env, want in cases:
            with self.subTest(env=env):
                self.assertEqual(self.lang(env), want)

    def test_with_python_same_rule(self):
        for env, want in (({"LANG": "kok_IN"}, "en"), ({"LANG": "ko_KR.UTF-8"}, "ko"), ({"BATON_LANG": "", "LANG": "ko"}, "ko")):
            with self.subTest(env=env):
                self.assertEqual(self.lang(env, python=True), want)


if __name__ == "__main__":
    unittest.main()
