#!/usr/bin/env python3
import argparse
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import split_sim as s


class SplitSimTest(unittest.TestCase):
    def test_no_cut_below_threshold(self):
        sim, cuts = s.simulate([100, 150, 190], ratio=2.0, handoff=10, reorient=3)
        self.assertEqual((sim, cuts), ([100, 150, 190], 0))

    def test_cut_resets_to_first_plus_handoff_and_adds_reorientation(self):
        sim, cuts = s.simulate([100, 150, 250, 300], ratio=2.0, handoff=10, reorient=2)
        self.assertEqual(cuts, 1)
        self.assertEqual(sim, [100, 150, 110, 110, 110, 160])  # 250에서 끊고 방향 잡기 2회, 이후 +50

    def test_weighted_new_session_only_reuses_fixed_prefix(self):
        # 계속 커지는 세션: 둘째 호출은 앞 100을 캐시로 읽고 50만 새로
        self.assertAlmostEqual(s.weighted([100, 150]), 1.25 * 100 + (0.1 * 100 + 1.25 * 50))
        # 줄어든 호출(새 세션): 고정 앞부분(첫 호출 100)까지만 캐시
        self.assertAlmostEqual(s.weighted([100, 300, 120]), 125 + (10 + 250) + (0.1 * 100 + 1.25 * 20))


class DollarSweepTest(unittest.TestCase):
    """--tokens 달러 손익(2026-11-25): 인계서 쓰기 비용을 넣고 절대 토큰 문턱으로 끊는다."""
    pr = s.PRICES["실험맞춤"]

    def test_handoff_writing_costs_069_at_230k(self):
        for pr in s.PRICES.values():
            self.assertAlmostEqual(6 * 230_000 * pr["read"] / 1e6 + s.fixed_part(pr), 0.69)
        self.assertAlmostEqual(s.fixed_part(self.pr), 0.41262)

    def test_dollars_reads_the_shared_part_and_writes_the_rest(self):
        r, w = self.pr["read"] / 1e6, self.pr["write"] / 1e6
        self.assertAlmostEqual(s.dollars([100, 150], self.pr), 100 * w + (100 * r + 50 * w))

    def test_no_cut_below_threshold_costs_the_same(self):
        ctxs = [100_000, 150_000, 170_000]
        self.assertEqual(s.split_dollars(ctxs, 180_000, self.pr), (s.dollars(ctxs, self.pr), 0))

    def test_cut_call_becomes_writing_then_new_session(self):
        r, w = self.pr["read"] / 1e6, self.pr["write"] / 1e6
        t, cuts = s.split_dollars([100_000, 150_000, 200_000, 210_000], 180_000, self.pr, handoff=4000, reorient=3)
        base = 104_000  # 새 세션 첫 맥락 = 원 세션 첫 맥락 + 인계서
        want = (100_000 * w) + (100_000 * r + 50_000 * w) \
            + (6 * 200_000 * r + s.fixed_part(self.pr)) + (base * w + 3 * base * r) \
            + (base * r + 10_000 * w)  # 끊은 뒤 1만 더 쌓임
        self.assertEqual(cuts, 1)
        self.assertAlmostEqual(t, want)

    def test_no_cut_within_20k_of_the_new_session_start(self):
        # 첫 호출부터 문턱 위인 세션은 새 세션 첫 맥락(첫+인계서)보다 2만 넘게 커져야 끊는다 — 끊자마자 다시 끊지 않게
        self.assertEqual(s.split_dollars([200_000, 210_000], 150_000, self.pr)[1], 0)
        self.assertEqual(s.split_dollars([200_000, 230_000], 150_000, self.pr)[1], 1)

    def test_until_first_compaction(self):
        self.assertEqual(s.until_compaction([100, 200, 300, 150, 400]), [100, 200, 300])
        self.assertEqual(s.until_compaction([100, 200, 130]), [100, 200, 130])  # 60% 이상이면 압축이 아니다

    def test_sweep_counts_sessions_past_each_threshold(self):
        data = [[50_000, 100_000, 300_000] + [300_000] * 20, [50_000, 120_000], [50_000, 260_000, 270_000]]
        few, = s.sweep(data, [250_000], self.pr)
        self.assertEqual(few, (250_000, 2))  # 넘은 세션 3개 미만 — 수만
        T, n, share, med, total, left = s.sweep(data + [data[0]], [250_000], self.pr)[0]
        self.assertEqual((T, n, left), (250_000, 3, 21))
        self.assertTrue(0 <= share <= 1)


class InputTest(unittest.TestCase):
    """리뷰 11-25: --tokens 값 읽기, usage 없는 줄."""

    def test_tokens_arg_takes_raw_tokens_or_thousands(self):
        self.assertEqual(s.tokens_arg("250000,450000"), [250_000, 450_000])  # 설정 키와 같은 꼴
        self.assertEqual(s.tokens_arg("150, 250"), [150_000, 250_000])  # 천 단위
        for bad in ("", ",", "abc", "0", "-5", "2.5"):
            with self.subTest(bad=bad), self.assertRaises(argparse.ArgumentTypeError):
                s.tokens_arg(bad)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):  # 빈 값은 조용히 배수 모드로 가지 않는다
            s.main(["--tokens", ""])

    def test_lines_without_usage_are_not_calls(self):
        # usage가 없는 assistant 줄이 0으로 들어가면 until_compaction이 그 자리를 압축으로 읽어 세션을 일찍 잘랐다
        rows = [{"type": "assistant", "message": {"id": "a", "usage": {"input_tokens": 100}}},
                {"type": "assistant", "message": {"id": "b"}},
                {"type": "assistant", "message": {"id": "c", "usage": {"input_tokens": 0}}},
                {"type": "assistant", "message": {"id": "d", "usage": {"input_tokens": 200}}}, ["not a dict"]]
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            f.write("\n".join(json.dumps(r) for r in rows) + "\n")
        self.addCleanup(os.unlink, f.name)
        self.assertEqual(s.call_contexts(f.name), [100, 200])
        self.assertEqual(s.until_compaction(s.call_contexts(f.name)), [100, 200])


if __name__ == "__main__":
    unittest.main()
