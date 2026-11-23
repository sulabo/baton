#!/usr/bin/env python3
"""lib/i18n.py: BATON_LANG (env > config) > locale > en."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

LIB = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(LIB, "i18n.py")
LOCALE_KEYS = ("LC_ALL", "LC_MESSAGES", "LANG", "BATON_LANG")


def run(env_extra, config=None):
    with tempfile.TemporaryDirectory() as home:
        env = {k: v for k, v in os.environ.items() if k not in LOCALE_KEYS}
        env.update(HOME=home, XDG_CONFIG_HOME=os.path.join(home, ".config"))
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


if __name__ == "__main__":
    unittest.main()
