#!/usr/bin/env bash
# PostToolUse 훅. 검사 스크립트가 0건을 냈을 때 그게 "없음"인지 "못 셌음"인지
# 구분하라고 상기시킨다. 이 플러그인이 존재하는 이유가 그 구분이다.
#
# 울리는 조건은 둘 다다: ① 명령이 check.sh·fresh.sh·promote.sh를 실행했다(명령 조각의 첫 실행 파일)
# ② 그 실행의 출력에 0건 신호가 있다. 2026-11-21 전에는 입력 문자열 어디든 스크립트 이름과 '없음'이 같이 있으면
# 울려서, `cat lib/fresh.sh` 같은 읽기 호출 대부분에서 떴다 — 매번 울리는 알람은 무시당한다.
set -uo pipefail
INPUT=$(cat 2>/dev/null) || exit 0
case "$INPUT" in
  *check.sh*|*fresh.sh*|*promote.sh*) ;;
  *) exit 0 ;;   # 빠른 길: 이름이 아예 없으면 python을 띄우지 않는다
esac
HIT=$(printf '%s' "$INPUT" | python3 -c '
import json, os, re, shlex, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
if not isinstance(d, dict):
    sys.exit(0)
ti = d.get("tool_input")
cmd = ti.get("command") if isinstance(ti, dict) else None
if not isinstance(cmd, str):
    sys.exit(0)
SCRIPTS = {"check.sh", "fresh.sh", "promote.sh"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
# 감싸개마다 값을 받는 옵션. 이 옵션 뒤의 낱말은 실행 파일이 아니다
ARG_OPTS = {"sudo": {"-u", "-g", "-h", "-p", "-U", "-C", "-D", "-r", "-t", "-T"}, "timeout": {"-s", "-k", "--signal", "--kill-after"},
            "nice": {"-n"}, "ionice": {"-c", "-n"}, "env": {"-u", "-C", "-S"}, "xargs": {"-I", "-n", "-P", "-d", "-L", "-s", "-a"}}
PLAIN = {"time", "exec", "command", "nohup", "nice", "ionice", "sudo", "env", "timeout", "xargs", "rtk", "proxy", "stdbuf"}
ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
OPS = re.compile(r"^[;&|()<>\n]+$")
def runs_cmd(cmd, depth=0):
    """따옴표를 먼저 풀고 &&·|·; 같은 연산자에서 조각을 나눈다(따옴표 안의 &&에서 나누지 않게)."""
    if depth >= 4:
        return False
    try:
        lx = shlex.shlex(cmd.replace("\n", " ; "), posix=True, punctuation_chars=True)
        lx.whitespace_split = True
        toks = list(lx)
    except ValueError:
        return False
    seg, segs = [], []
    for t in toks:
        if OPS.match(t):
            segs.append(seg); seg = []
        else:
            seg.append(t)
    segs.append(seg)
    return any(runs_seg(x, depth) for x in segs if x)
def runs_seg(w, depth):
    """명령 조각(낱말 목록)이 검사 스크립트를 실행하는가. 감싸개(timeout·sudo·env·rtk·bash 옵션)는 건너뛰고 실제 실행 파일을 본다.
    bash -c "…"는 그 문자열 안을 다시 본다. cat·grep 같은 읽기 명령이 첫 실행 파일이면 실행이 아니다."""
    i = 0
    while i < len(w):
        b = os.path.basename(w[i])
        if ASSIGN.match(w[i]):
            i += 1; continue
        if b in SHELLS:
            i += 1
            while i < len(w) and w[i][:1] in "-+" and w[i] not in ("-", "--"):
                o = w[i]
                if not o.startswith("--") and "c" in o[1:]:   # -c, -lc, -ec …: 다음 낱말이 명령 문자열
                    return i + 1 < len(w) and runs_cmd(w[i + 1], depth + 1)
                i += 2 if o in ("-o", "+o", "-O", "+O") else 1
            continue
        if b in PLAIN:
            opts = ARG_OPTS.get(b, set())
            i += 1
            while i < len(w) and (w[i].startswith("-") or ASSIGN.match(w[i])):
                i += 2 if w[i] in opts else 1
            if b == "timeout" and i < len(w):
                i += 1                                       # 시간 값
            continue
        return b in SCRIPTS
    return False
if not runs_cmd(cmd):
    sys.exit(0)
r = d.get("tool_response")
if isinstance(r, dict):
    out = "\n".join(str(r.get(k) or "") for k in ("stdout", "stderr", "output"))
else:
    out = r if isinstance(r, str) else ""
if re.search(r"(?<![0-9])0건|없음|메타 줄 0개|재확인 0(?![0-9])", out):
    print("hit")
' 2>/dev/null)
[ "$HIT" = hit ] || exit 0
# systemMessage는 사용자에게만 보인다. 모델이 읽게 하려면 additionalContext로 넣는다(Claude Code·Codex 공통 PostToolUse 형식)
MSG="[baton] 0건이 나왔다. 진짜 없는 것인지, 형식이 안 맞아 못 센 것인지 구분해서 보고한다. 형식 불일치 줄을 먼저 확인한다."
printf '{"systemMessage":"%s","hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"%s"}}\n' "$MSG" "$MSG"
