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
LIB="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)/lib"
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
PLAIN = {".", "source", "time", "exec", "command", "nohup", "nice", "ionice", "sudo", "env", "timeout", "xargs", "rtk", "proxy", "stdbuf"}
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
# 0건 신호는 두 언어 모두 본다 — 검사 스크립트가 어느 언어로 출력했든(BATON_LANG과 무관하게) 잡는다.
# 출력 어디든 0 낱말이 있으면 울리던 것을 구조로 가린다(2026-11-23: 재확인 14건인 fresh.sh 출력에서 울렸다 — 개념 이름
# "0건과 못 셈의 구분"이 든 표 줄과 "결정·지침 변동: … 커밋 0건" 줄에 걸렸다).
#  1) 못 셈 신호(메타 줄 0개·"0이 아니라 못 셌다")는 언제나 울린다 — 이 훅이 있는 이유다. 옆에 0이 아닌 수가 있어도
#     ("Concepts: 3 · metadata lines: 0") 울린다
#  2) 머리 결과 줄(fresh.sh 요약의 재확인 수, check.sh 지적 총수)이 있으면 그것만 본다 — 0이면 울리고, 모두 0이 아니면
#     나머지 줄의 0(부분 수·표 안 이름 글자)은 세부라 울리지 않는다
#  3) 머리 결과 줄이 없으면(promote.sh 등) 줄마다 본다. " · "로 나눈 여러 수 요약 줄에서 0이 아닌 수가 옆에 있는 0은 세지 않는다
# ponytail: promote.sh 목록 줄의 인계서 원문에 "0건"이 있으면 3)에서 울릴 수 있다 — 원문 줄을 구조로 가리려면 promote 출력 형식을 읽어야 한다
ALWAYS = r"메타 줄 0개|0건이 아니라 못 셌|0건이 아니라 못 셈|metadata lines: 0(?![0-9])|No metadata lines at all|\bnot 0\b"
HEAD = r"^\s*(?:요약: 재확인|지적 총|Summary: re-check|Total findings:) ?([0-9]+)"
ZERO = (r"(?<![0-9])0건|없음|재확인 0(?![0-9])"
        r"|(?i:\bno findings\b|re-check 0(?![0-9])|(?<![0-9])0 (?:commits?|found|dropped)\b|[:→] ?0(?![0-9.,])"
        r"|\(no rejected list\)|\b(?:new decisions|new decision rows|lines|gaps) 0(?![0-9]))")
NONZERO = r"(?<![\w.])[1-9][0-9]*(?![0-9.])"
lines = out.splitlines()
heads = [int(m.group(1)) for m in (re.match(HEAD, ln) for ln in lines) if m]
def zero_line(ln):
    if not re.search(ZERO, ln):
        return False
    fields = ln.split(" · ")
    return not any(re.search(ZERO, f) is None and re.search(NONZERO, f) for f in fields)
if any(re.search(ALWAYS, ln) for ln in lines):
    pass
elif heads:
    if all(h > 0 for h in heads):
        sys.exit(0)
elif not any(zero_line(ln) for ln in lines):
    sys.exit(0)
lang = "en"
try:  # 알림 언어(lib/i18n.py). 못 정하면 lib.sh의 baton_lang처럼 en
    sys.path.insert(0, sys.argv[1])
    import i18n
    cwd = d.get("cwd") if isinstance(d.get("cwd"), str) else None
    lang = i18n.lang(os.environ.get("CLAUDE_PROJECT_DIR") or cwd)
except Exception:
    pass
print(lang)
' "$LIB" 2>/dev/null)
# systemMessage는 사용자에게만 보인다. 모델이 읽게 하려면 additionalContext로 넣는다(Claude Code·Codex 공통 PostToolUse 형식)
case "$HIT" in
  ko) MSG="[baton] 0건이 나왔다. 진짜 없는 것인지, 형식이 안 맞아 못 센 것인지 구분해서 보고한다. 형식 불일치 줄을 먼저 확인한다." ;;
  en) MSG="[baton] The output has a zero count. Before you report it, tell whether there really is nothing or whether nothing could be counted because the format did not match. Check the lines that did not match the format first." ;;
  *) exit 0 ;;
esac
printf '{"systemMessage":"%s","hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"%s"}}\n' "$MSG" "$MSG"
