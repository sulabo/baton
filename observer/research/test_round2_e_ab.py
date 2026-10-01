import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))  # 저장소 루트에서 돌려도 import되게
import round2_e_ab as runner


class RunnerTests(unittest.TestCase):
    def test_source_reset_is_rejected(self):
        with self.assertRaises(ValueError):
            runner.validate_snapshot(Path(__file__).resolve().parents[2])

    def test_concept_arm_is_explicit(self):
        settings = json.loads(runner.settings_for("concept"))
        command = settings["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
        self.assertIn("BATON_CONCEPT_INJECT=on", command)
        self.assertIn("BATON_HANDOFF_INJECT=off", command)

    def test_budget_reaches_cli(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(runner.subprocess, "run") as run:
            run.return_value.returncode = 0
            runner.run_one(directory, "off", str(Path(directory) / "run.jsonl"), 2, max_usd=1.25)
            command = run.call_args.args[0]
            self.assertEqual(command[command.index("--max-budget-usd") + 1], "1.25")
            self.assertIn("--include-hook-events", command)

    def test_resumed_budget_stops_before_reset(self):
        from argparse import Namespace
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "runs.json").write_text(json.dumps([{"arm": "off", "i": 1, "cost_usd": 2, "base": "abc"}]))
            args = Namespace(repo=directory, data=directory, arms="off,concept", n=1, max_usd=2)
            with patch.object(runner, "validate_snapshot"), patch.object(runner, "reset") as reset:
                with self.assertRaises(SystemExit):
                    runner.cmd_run(args)
                reset.assert_not_called()

    def test_outside_paths_flags_home_reads_outside_snapshot(self):
        home = str(Path.home())
        with tempfile.TemporaryDirectory(dir=home) as repo:
            calls = [{"name": "Read", "input": {"file_path": f"{repo}/a.md"}},                     # 안 — 조용
                     {"name": "Read", "input": {"file_path": f"{home}/.claude/x.md"}},            # 하네스 — 조용
                     {"name": "Bash", "input": {"command": 'cd ~/Documents/"다른 저장소" && ls'}},  # 밖 — 잡힘
                     {"name": "Grep", "input": {"path": "/usr/include"}}]                        # 홈 밖 시스템 — 조용
            line = {"type": "assistant", "message": {"content": [dict(type="tool_use", **c) for c in calls]}}
            jl = Path(repo) / "s.jsonl"; jl.write_text(json.dumps(line, ensure_ascii=False) + "\n")
            hits = runner.outside_paths(str(jl), repo)
            self.assertEqual(len(hits), 1); self.assertIn("다른 저장소", hits[0])

    def test_confine_reads_reaches_settings(self):
        with patch.object(runner.subprocess, "run") as run, tempfile.TemporaryDirectory() as d:
            run.return_value.returncode = 0
            runner.run_one(d, "off", str(Path(d) / "o.jsonl"), 3, confine=True)
            cmd = run.call_args.args[0]
            st = json.loads(cmd[cmd.index("--settings") + 1])
            self.assertTrue(st["sandbox"]["enabled"]); self.assertIn("~/", st["sandbox"]["filesystem"]["denyRead"])
            self.assertTrue(st["permissions"]["blockReadsOutsideWorkingDirectories"])

    def _git_repo(self, d):
        repo = Path(d) / "snap"; repo.mkdir()
        runner.subprocess.run(["git", "init", "-q", str(repo)], check=True)
        return repo

    def test_clean_removes_symlinked_state_but_not_its_target(self):
        with tempfile.TemporaryDirectory() as d, patch.object(runner, "validate_snapshot"):
            repo = self._git_repo(d)
            victim = Path(d) / "victim"; (victim / "sub").mkdir(parents=True); (victim / "sub" / "f.txt").write_text("x")
            (repo / ".omc").symlink_to(victim)
            runner.clean_leftovers(str(repo), set())
            self.assertFalse((repo / ".omc").exists() or (repo / ".omc").is_symlink())
            self.assertTrue((victim / "sub" / "f.txt").exists())  # 링크 대상(스냅샷 밖)은 남는다

    def test_clean_keeps_setup_files_when_session_empties_their_folder(self):
        with tempfile.TemporaryDirectory() as d, patch.object(runner, "validate_snapshot"):
            repo = self._git_repo(d)
            (repo / ".gitignore").write_text("*.log\n"); (repo / "a").mkdir()
            (repo / "a" / "keep.txt").write_text("k"); (repo / "a" / "x.log").write_text("setup")
            runner.subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
            before = runner.ignored_set(str(repo))
            (repo / "a" / "keep.txt").unlink(); runner.subprocess.run(["git", "-C", str(repo), "rm", "-q", "--cached", "a/keep.txt"], check=True)
            runner.clean_leftovers(str(repo), before)
            self.assertTrue((repo / "a" / "x.log").exists())

    def test_clean_keeps_setup_folder_when_session_force_adds_inside_it(self):
        with tempfile.TemporaryDirectory() as d, patch.object(runner, "validate_snapshot"):
            repo = self._git_repo(d)
            (repo / ".gitignore").write_text("node_modules/\n")
            for sub in ("lib", "other"): (repo / "node_modules" / sub).mkdir(parents=True); (repo / "node_modules" / sub / "i.js").write_text("x")
            (repo / "node_modules" / "patch.js").write_text("p")
            before = runner.ignored_set(str(repo))
            runner.subprocess.run(["git", "-C", str(repo), "add", "-f", "node_modules/patch.js"], check=True)  # git이 하위 폴더를 따로 보고하게 된다
            runner.clean_leftovers(str(repo), before)
            self.assertTrue((repo / "node_modules" / "lib" / "i.js").exists())


if __name__ == "__main__":
    unittest.main()
