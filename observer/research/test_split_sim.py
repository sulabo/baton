#!/usr/bin/env python3
import os
import sys
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


if __name__ == "__main__":
    unittest.main()
