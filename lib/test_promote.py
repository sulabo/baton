#!/usr/bin/env python3
"""승격 검토(promote.sh). 확인 표시 [V]·[?]만 바뀐 같은 사실은 B절 "탈락"으로 세지 않는다."""
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROMOTE = os.path.join(HERE, "promote.sh")


def handoff(*facts):
    return "# Session Handoff\n\n## 확인된 사실과 결정\n" + "".join(f"- {x}\n" for x in facts) + "\n## 관련 파일·심볼\n- a\n"


class PromoteTest(unittest.TestCase):
    def repo(self, versions):
        """판마다 하루씩 다른 날짜로 HANDOFF.md를 커밋한 저장소."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        r = tmp.name
        git = ["git", "-C", r, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false"]
        subprocess.run(["git", "init", "-q", r], check=True)
        for day, text in enumerate(versions, 1):
            with open(os.path.join(r, "HANDOFF.md"), "w", encoding="utf-8") as f:
                f.write(text)
            date = f"2026-10-0{day}T10:00:00+0900"
            env = dict(os.environ, GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
            subprocess.run(git + ["add", "HANDOFF.md"], check=True)
            subprocess.run(git + ["commit", "-q", "-m", "x"], check=True, env=env)
        return r

    def run_promote(self, r):
        p = subprocess.run(["bash", PROMOTE, r], capture_output=True, text=True, check=False)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return p.stdout

    def test_mark_change_is_not_a_drop(self):
        # 리뷰(11-21) 재현 저장소와 같은 이력: [?]로 이틀 있던 사실이 최신판에서 [V]로 확인됐다
        out = self.run_promote(self.repo([
            handoff("[?] 배포는 금지 상태가 유지된다"),
            handoff("[?] 배포는 금지 상태가 유지된다", "[V] 기타"),
            handoff("[V] 배포는 금지 상태가 유지된다"),
        ]))
        self.assertIn("탈락 총 0건", out)
        self.assertNotIn("배포는 금지", out.split("[B]", 1)[1].split("[C]", 1)[0])

    def test_real_drop_still_reported(self):
        out = self.run_promote(self.repo([
            handoff("[?] 배포는 금지 상태가 유지된다"),
            handoff("[V] 배포는 금지 상태가 유지된다"),
            handoff("[V] 다른 사실"),
        ]))
        self.assertIn("탈락 총 1건", out)
        self.assertIn("- 배포는 금지 상태가 유지된다", out)


if __name__ == "__main__":
    unittest.main()
