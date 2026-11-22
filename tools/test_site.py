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


if __name__ == "__main__":
    unittest.main()
