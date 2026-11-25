#!/usr/bin/env python3
"""site/: 영어판과 한국어판(ko/)은 손으로 맞춘 두 벌이다. 요소 id·측정 숫자·서로 가리키는 링크가 갈라지면 실패한다."""
import os
import re
import unittest

SITE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "site")


def read(*parts):
    with open(os.path.join(SITE, *parts), encoding="utf-8") as f:
        return f.read()


def measured_numbers(page):
    """'지금까지 잰 것' 절의 숫자 집합. 말로 쓴 수(Eleven)와 단위(×·배)는 판마다 달라 숫자만 센다."""
    m = re.search(r'<section class="measured.*?</section>', page, re.S)
    assert m, "measured section not found"
    text = re.sub(r"<[^>]+>", " ", m.group(0))
    return set(re.findall(r"\d[\d,]*", text))


class SitePagesTest(unittest.TestCase):
    def setUp(self):
        self.en = read("index.html")
        self.ko = read("ko", "index.html")

    def test_same_element_ids(self):
        ids = lambda p: sorted(re.findall(r'\bid="([^"]+)"', p))
        self.assertEqual(ids(self.en), ids(self.ko))

    def test_same_measured_numbers(self):
        en, ko = measured_numbers(self.en), measured_numbers(self.ko)
        self.assertIn("269", en)  # 숫자를 실제로 뽑고 있는지
        self.assertEqual(en, ko)

    def test_language_links_point_at_each_other(self):
        self.assertIn('<html lang="en">', self.en)
        self.assertIn('<html lang="ko">', self.ko)
        self.assertIn('href="ko/" hreflang="ko"', self.en)
        self.assertIn('href="../" hreflang="en"', self.ko)
        for page in (self.en, self.ko):
            self.assertIn('hreflang="ko" href="https://sulabo.github.io/baton/ko/"', page)

    def test_share_preview_meta(self):
        meta = lambda p, k: re.search(r'<meta (?:property|name)="%s" content="([^"]*)">' % re.escape(k), p).group(1)
        canon = lambda p: re.search(r'<link rel="canonical" href="([^"]+)">', p).group(1)
        self.assertEqual(meta(self.en, "og:image"), meta(self.ko, "og:image"))
        self.assertTrue(os.path.isfile(os.path.join(SITE, meta(self.en, "og:image").rsplit("/", 1)[1])))
        for page in (self.en, self.ko):
            self.assertEqual(meta(page, "og:url"), canon(page))
            self.assertEqual(meta(page, "twitter:card"), "summary_large_image")


ROOT = os.path.dirname(SITE)


def doc(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


class ContextRuleDocsTest(unittest.TestCase):
    """맥락 문턱 규칙(2026-11-25)을 설명하는 문서들. 리뷰 11-25에서 빠졌던 조건이 다시 빠지지 않게 본다."""

    def test_site_mentions_the_work_condition_wherever_it_names_the_thresholds(self):
        # 조건은 "마지막 인계서 뒤의 일"(고침·파일을 쓰는 명령·맡긴 일 속 고침) — 리뷰 11-25
        for page, num, cond in ((read("index.html"), "250K", "work since the last handoff"),
                                (read("ko", "index.html"), "25만", "마지막 인계서 뒤에 한 일")):
            blocks = re.findall(r"<(?:p|details)[ >].*?</(?:p|details)>", page, re.S)
            hits = [b for b in blocks if num in b]
            self.assertGreaterEqual(len(hits), 3, num)  # 비용 절 한 곳 + FAQ 두 곳
            for b in hits:
                self.assertIn(cond, b, b[:120])

    def test_small_window_note_in_readme_guide_and_skill(self):
        # 리뷰 11-25: "낮춰라"는 근거가 없다 — 낮출 수는 있지만 그 크기에서 더 싼지는 재지 않았다고 쓴다
        en_words, ko_words = ("1M-token", "200K window", "wasn't measured", "150K was usually a loss"), ("100만 토큰", "20만 토큰", "재지 않았")
        for parts, words in ((("README.md",), en_words), (("README.ko.md",), ko_words), (("docs", "GUIDE.md"), en_words),
                             (("docs", "GUIDE.ko.md"), ko_words), (("skills", "baton", "SKILL.md"), en_words),
                             (("CHANGELOG.md",), ko_words)):
            text = " ".join(doc(*parts).split())
            for w in words:
                self.assertIn(w, text, parts)
            for bad in ("so set `BATON_SPLIT_TOKENS` lower", "낮게 정해 주세요", "더 낮게 정합니다", "낮게 정합니다", "낮춰야"):
                self.assertNotIn(bad, text, parts)

    def test_current_default_in_concepts_and_north_star(self):
        concept = doc("CONCEPTS.md").split("## 5. 세션 끊기 알림", 1)[1].split("\n## ", 1)[0]
        self.assertIn("BATON_SPLIT_TOKENS=250000,450000", concept)
        self.assertNotIn("기본 `2,3`", concept)
        self.assertIn("2026-11-25부터 호출 맥락 25만·45만 토큰", doc("docs", "NORTH_STAR.md"))

    def test_changelog_gives_denominators_not_most(self):
        entry = doc("CHANGELOG.md").split("## [1.0.1]", 1)[1].split("\n## [", 1)[0]
        self.assertIn("그 크기에 닿은 대화 중 열에 여섯쯤", entry)
        self.assertNotIn("대부분의 대화에서", entry)


if __name__ == "__main__":
    unittest.main()
