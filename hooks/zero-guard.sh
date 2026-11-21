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
WRAPPERS = {"bash", "sh", "zsh", "env", "time", "exec", "command", "nohup"}
def runs_script(segment):
    try:
        words = shlex.split(segment, comments=True)
    except ValueError:
        return False
    for w in words:
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w) or w in WRAPPERS or w.startswith("-"):
            continue  # 앞의 환경변수 대입·bash 같은 감싸개·그 옵션은 건너뛰고 실제 실행 파일을 본다
        return os.path.basename(w) in SCRIPTS
    return False
if not any(runs_script(s) for s in re.split(r"&&|\|\||[;|\n&()]", cmd)):
    sys.exit(0)
r = d.get("tool_response")
if isinstance(r, dict):
    out = "\n".join(str(r.get(k) or "") for k in ("stdout", "stderr", "output"))
else:
    out = r if isinstance(r, str) else ""
if re.search(r"(?<![0-9])0건|없음|메타 줄 0개", out):
    print("hit")
' 2>/dev/null)
[ "$HIT" = hit ] || exit 0
# systemMessage는 사용자에게만 보인다. 모델이 읽게 하려면 additionalContext로 넣는다(Claude Code·Codex 공통 PostToolUse 형식)
MSG="[baton] 0건이 나왔다. 진짜 없는 것인지, 형식이 안 맞아 못 센 것인지 구분해서 보고한다. 형식 불일치 줄을 먼저 확인한다."
printf '{"systemMessage":"%s","hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"%s"}}\n' "$MSG" "$MSG"
