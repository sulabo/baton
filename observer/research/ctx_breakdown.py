#!/usr/bin/env python3
"""첫 턴 컨텍스트 분해: 한 가지씩 끄고 1턴 세션의 입력 토큰(input+cache_creation+cache_read)을 잰다.
빈 스크래치 폴더에서 돌리므로 프로젝트 지침은 0이다(ratio 조건만 CLAUDE.md를 넣는다).
전역 지침(~/.claude/CLAUDE.md 사슬)은 끌 수 없어서(--bare는 API 키 인증 전용) 직접 재지 않고,
크기를 아는 문서를 프로젝트 CLAUDE.md로 넣었을 때의 증가분으로 글자당 토큰 비율을 재 추정한다.

  python3 ctx_breakdown.py <work dir> [--n 2]
"""
import json, os, shutil, subprocess, sys

OFF_PLUGINS = {"oh-my-claudecode@omc": False, "warp@claude-code-warp": False,
               "ui-ux-pro-max@ui-ux-pro-max-skill": False}
NOMCP = ["--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}']
RATIO_DOC = os.path.expanduser("~/.claude/shared-rules.md")

VARIANTS = {
    "base": ([], None),
    "noplugins": (["--settings", json.dumps({"enabledPlugins": OFF_PLUGINS})], None),
    "noskills": (["--disable-slash-commands"], None),
    "nomcp": (NOMCP, None),
    "alloff": (["--settings", json.dumps({"enabledPlugins": OFF_PLUGINS}), "--disable-slash-commands"] + NOMCP, None),
    "ratio": ([], RATIO_DOC),
}


def run(work, name, extra, claude_md):
    d = os.path.join(work, name)
    os.makedirs(d, exist_ok=True)
    if claude_md: shutil.copy(claude_md, os.path.join(d, "CLAUDE.md"))
    cmd = ["claude", "-p", "한 단어로 답해: ok", "--max-turns", "1", "--output-format", "stream-json", "--verbose"] + extra
    p = subprocess.run(cmd, cwd=d, stdin=subprocess.DEVNULL, capture_output=True, text=True)
    first, init, cost = None, {}, None
    for ln in p.stdout.splitlines():
        try: e = json.loads(ln)
        except Exception: continue
        if e.get("type") == "system" and e.get("subtype") == "init": init = e
        if e.get("type") == "assistant" and first is None:
            u = e["message"].get("usage") or {}
            first = sum(u.get(k, 0) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
        if e.get("type") == "result": cost = e.get("total_cost_usd")
    return dict(variant=name, first=first, cost=cost, plugins=len(init.get("plugins", [])),
                skills=len(init.get("skills", [])), agents=len(init.get("agents", [])),
                tools=len(init.get("tools", [])), mcp=len(init.get("mcp_servers", [])))


def main():
    work = sys.argv[1]; n = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 1
    rows = []
    for i in range(n):
        for name, (extra, md) in VARIANTS.items():
            r = run(work, f"{name}-{i}", extra, md); r["i"] = i; r["variant"] = name; rows.append(r)
            print(json.dumps(r, ensure_ascii=False), flush=True)
    json.dump(rows, open(os.path.join(work, "breakdown.json"), "w"), ensure_ascii=False, indent=1)
    chars = len(open(RATIO_DOC, encoding="utf-8").read())
    # 같은 회차끼리 짝짓는다. MCP 도구 목록이 연결 시점에 따라 달라 회차 간 기준이 흔들린다.
    by = {(r["variant"], r["i"]): r for r in rows}
    pairs = [(by[("ratio", i)], by[("base", i)]) for i in range(n) if ("ratio", i) in by and ("base", i) in by]
    if not pairs:
        print("ratio: 짝지을 base·ratio 회차가 없다 — 비율을 못 셌다(0이 아니라 모름)"); return
    for rt, b in pairs:
        note = "" if rt["tools"] == b["tools"] else f" (도구 수 다름 {b['tools']}→{rt['tools']}, 신뢰 낮음)"
        d = rt["first"] - b["first"]
        print(f"ratio[{b['i']}]: {chars}자 문서 → +{d} 토큰 = {d / chars:.3f} 토큰/자{note}")


if __name__ == "__main__":
    main()
