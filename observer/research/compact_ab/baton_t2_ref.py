#!/usr/bin/env python3
"""Reference implementation for the baton T2 grader self-test (never copied into a snapshot).

Usage:
  python3 lib/handoff_stats.py <path> [--by-date]

  --by-date   one line per dated section, newest first: YYYY-MM-DD open=A done=B
"""
import argparse, re

DATE = re.compile(r"^(\d{4})[-.](\d{2})[-.](\d{2})")
TASK = re.compile(r"^\s*- \[([ xX])\]")


def sections(text):
    out, fenced = [], False
    for ln in text.splitlines():
        if ln.lstrip().startswith("```"):
            fenced = not fenced
        if not fenced and ln.startswith("## "):
            out.append([ln[3:].strip(), []])
        elif out:
            out[-1][1].append((fenced, ln))
    return out


def by_date(text):
    rows = []
    for title, body in sections(text):
        m = DATE.match(title)
        if not m:
            continue
        marks = [TASK.match(ln) for f, ln in body if not f]
        rows.append(("-".join(m.groups()), sum(1 for x in marks if x and x.group(1) == " "),
                     sum(1 for x in marks if x and x.group(1) != " ")))
    return sorted(rows, reverse=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--by-date", action="store_true")
    a = ap.parse_args()
    text = open(a.path, encoding="utf-8").read()
    if a.by_date:
        rows = by_date(text)
        if not rows:
            print("baton: no dated sections")
        for d, o, n in rows:
            print(f"{d} open={o} done={n}")
        return
    secs = sections(text)
    marks = [TASK.match(ln) for _, body in secs for f, ln in body if not f]
    print(f"baton: sections={len(secs)} open={sum(1 for x in marks if x and x.group(1) == ' ')}"
          f" done={sum(1 for x in marks if x and x.group(1) != ' ')}")


main()
