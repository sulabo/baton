#!/usr/bin/env bash
# PostToolUse 훅. 검사 스크립트가 0건을 냈을 때 그게 "없음"인지 "못 셌음"인지
# 구분하라고 상기시킨다. 이 플러그인이 존재하는 이유가 그 구분이다.
set -uo pipefail
INPUT=$(cat 2>/dev/null) || exit 0
case "$INPUT" in
  *check.sh*|*fresh.sh*|*promote.sh*) ;;
  *) exit 0 ;;
esac
case "$INPUT" in
  *"0건"*|*"없음"*|*"메타 줄 0개"*)
    # systemMessage는 사용자에게만 보인다. 모델이 읽게 하려면 additionalContext로 넣는다(Claude Code·Codex 공통 PostToolUse 형식)
    MSG="[baton] 0건이 나왔다. 진짜 없는 것인지, 형식이 안 맞아 못 센 것인지 구분해서 보고한다. 형식 불일치 줄을 먼저 확인한다."
    printf '{"systemMessage":"%s","hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"%s"}}\n' "$MSG" "$MSG"
    ;;
  *) exit 0 ;;
esac
