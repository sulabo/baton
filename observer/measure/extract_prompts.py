#!/usr/bin/env python3
"""STEP 0 측정: Claude Code 세션 기록에서 사람 프롬프트와 작업 경계 후보를 세고 출처를 찍는다.
   extract_prompts.py <프로젝트 폴더 glob 조각>   예: extract_prompts.py '*26-05'
   출력은 스펙의 [MEASURED, PRE-VALIDATION] 블록과 같은 형식. 추출기 검증(0-A) 전 출력이다."""
import json, glob, os, sys
from datetime import datetime

pat = sys.argv[1] if len(sys.argv) > 1 else "*"
files = sorted(glob.glob(os.path.expanduser(f"~/.claude/projects/{pat}/*.jsonl")))
GAP_SEC = 30 * 60

def human_text(content):
    """content가 문자열이거나 text 블록만이면 사람 프롬프트. tool_result가 섞이면 아니다."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        if any(isinstance(x, dict) and x.get("type") == "tool_result" for x in content):
            return None
        return " ".join(x.get("text", "") for x in content
                        if isinstance(x, dict) and x.get("type") == "text").strip()
    return None

raw = accepted = accepted15 = first = gap = 0
stamps = []
for f in files:
    prev = None
    for line in open(f, encoding="utf-8", errors="ignore"):
        try: d = json.loads(line)
        except json.JSONDecodeError: continue
        if d.get("type") != "user": continue
        raw += 1
        text = human_text(d.get("message", {}).get("content"))
        if not text or text.startswith("<"): continue
        accepted += 1
        try: t = datetime.fromisoformat(d.get("timestamp", "").replace("Z", "+00:00")); stamps.append(t)
        except ValueError: t = None
        if len(text) >= 15:
            accepted15 += 1
            if prev is None: first += 1
            elif t and prev and (t - prev).total_seconds() >= GAP_SEC: gap += 1
        if t: prev = t

print("[MEASURED, PRE-VALIDATION]")
print(f"  Source: Claude Code only · session files {len(files)} · pattern {pat!r}")
if stamps: print(f"  Time range: {min(stamps).date()} ~ {max(stamps).date()}")
print(f"  Raw user-type events: {raw}")
print(f"  Extractor accepted (구조 필터만): {accepted}")
print(f"    그중 15자 이상: {accepted15}")
print(f"  Among 15자 이상: SESSION_FIRST {first} · gap>={GAP_SEC//60}분 {gap} · union {first + gap}")
print(f"  Dedup 없음 · 경계 비교 >= · 0-A 검증 전")
