#!/usr/bin/env python3
"""Codex history.jsonl → sessions/*.jsonl 연결 전수 검증. 스펙 [MEASURED] 블록과 같은 형식.
   파일명 끝 UUID를 파싱해 등호 비교하고, 첫 줄 payload.session_id로 교차 확인한다."""
import json, glob, os, re

H = os.path.expanduser("~/.codex/history.jsonl")
S = sorted(glob.glob(os.path.expanduser("~/.codex/sessions/**/*.jsonl"), recursive=True))
UUID = re.compile(r"([0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12})\.jsonl$")

rows = bad = 0; ids = []; missing = {"session_id": 0, "text": 0, "ts": 0}
for line in open(H, encoding="utf-8", errors="ignore"):
    if not line.strip(): continue
    try: d = json.loads(line); rows += 1
    except json.JSONDecodeError: bad += 1; continue
    for k in missing:
        if not d.get(k): missing[k] += 1
    if d.get("session_id"): ids.append(d["session_id"])
Hd = set(ids)

by_id = {}; unparsed = 0
for f in S:
    m = UUID.search(os.path.basename(f))
    if m: by_id.setdefault(m.group(1), []).append(f)
    else: unparsed += 1

m1 = sum(1 for h in Hd if len(by_id.get(h, [])) == 1)
m0 = sum(1 for h in Hd if h not in by_id)
mm = sum(1 for h in Hd if len(by_id.get(h, [])) > 1)
parsed = with_cwd = cross = 0
for h in Hd:
    fs = by_id.get(h, [])
    if len(fs) != 1: continue
    try:
        first = json.loads(open(fs[0], encoding="utf-8", errors="ignore").readline()); parsed += 1
        if first.get("payload", {}).get("session_id") == h: cross += 1
        if '"cwd"' in open(fs[0], encoding="utf-8", errors="ignore").read(50000): with_cwd += 1
    except (json.JSONDecodeError, OSError): pass

print("[MEASURED]")
print("  방법: glob sessions/**/*.jsonl (숨김 제외) · 파일명 끝 UUID 정규식 · 등호 비교")
print(f"  history rows {rows} · parse 실패 {bad} · missing session_id {missing['session_id']} · text {missing['text']} · ts {missing['ts']} · distinct H = {len(Hd)}")
print(f"  session files S = {len(S)} · 파일명 UUID 파싱 실패 {unparsed}")
print(f"  M1 = {m1} · M0 = {m0} · Mmulti = {mm} · P = {parsed} · C = {with_cwd}")
print(f"  교차 확인: payload.session_id == 파일명 UUID  {cross} / {m1}")
print(f"  판정: {'통과' if mm == 0 else '실패'} (Mmulti = 0 필수)")
