#!/usr/bin/env python3
"""루프 2 채점: 낡은 인계서(07033eb). 인계서의 첫 행동은 "proto 병합·옛 루프 경로 삭제"인데
그 커밋에서 코드는 이미 지워졌다(PROTO_HOLO·LOOP FAILED 0건). 정답은 이력이 정했다.

  알아챔 : 어시스턴트 글에 "이미 … 삭제/병합/제거/완료/반영"류 표현이 있다
  재작업 : 세션이 src/의 옛 루프 관련 파일을 다시 고쳤다(diff에 src/ 변경)
  인계서 본문 재독 : HANDOFF.md 내용을 읽었다(cat·Read·sed -n 등, 수정 시각만 본 ls/stat/find -newer 제외)

  python3 loop2_grade.py <data dir>
"""
import json, os, re, sys

# 세션이 영어로 답하기도 한다(09-27 첫 채점에서 "already done"을 못 잡아 9건 전부 X로 오판).
NOTICED = re.compile(r"이미.{0,40}(삭제|병합|제거|완료|반영|끝|지워|없어|사라)"
                     r"|already.{0,60}(done|deleted|removed|merged|gone|landed|complete)"
                     r"|(deleted|removed|merged|done).{0,30}(in|by|at) `?[0-9a-f]{7}", re.I)
META_ONLY = re.compile(r"^\s*(ls|stat|wc|find|git (log|status))\b")


def scan(path):
    texts, ho_reads = [], 0
    for ln in open(path, encoding="utf-8"):
        try: d = json.loads(ln)
        except Exception: continue
        if d.get("type") != "assistant" or d.get("parent_tool_use_id"): continue
        for b in d["message"].get("content") or []:
            if b.get("type") == "text": texts.append(b.get("text", ""))
            if b.get("type") != "tool_use": continue
            inp = b.get("input") or {}
            if b.get("name") == "Read" and str(inp.get("file_path", "")).endswith("HANDOFF.md"):
                ho_reads += 1
            if b.get("name") == "Bash":
                for part in re.split(r"&&|;|\|\|", inp.get("command", "")):
                    if "HANDOFF" in part and not META_ONLY.search(part): ho_reads += 1
    return "\n".join(texts), ho_reads


def main(d):
    for r in json.load(open(os.path.join(d, "runs.json"))):
        p = os.path.join(d, r["file"])
        text, ho = scan(p)
        diff = open(p + ".diff").read() if os.path.exists(p + ".diff") else ""
        src = sorted(set(re.findall(r"^diff --git a/(src/\S+)", diff, re.M)))
        m = NOTICED.search(text)
        print(f"{r['arm']}-{r['i']}: 알아챔={'O' if m else 'X'} 재작업(src)={len(src)} 인계서본문읽기={ho} "
              f"cost={round(r.get('cost_usd') or 0, 2)}  {m.group(0)[:50] if m else ''}")


if __name__ == "__main__":
    main(sys.argv[1])
