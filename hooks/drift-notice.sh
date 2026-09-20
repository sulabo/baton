#!/usr/bin/env bash
# SessionStart 훅. 개념 지도가 있는 저장소면 재확인 대상이 몇 개인지만 알린다.
# 없으면 조용히 끝낸다. 매번 울리는 알람은 곧 무시당한다.
set -uo pipefail
ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
MAP=$(find "$ROOT" -maxdepth 2 -name CONCEPTS.md -not -path "*/node_modules/*" 2>/dev/null | head -1)
[ -n "$MAP" ] || exit 0

OUT=$("$CLAUDE_PLUGIN_ROOT/lib/fresh.sh" "$MAP" "$ROOT" 2>/dev/null) || exit 0
STALE=$(echo "$OUT" | grep -c '재확인 필요' || true)
FRESH=$(echo "$OUT" | grep -c '신선' || true)
[ "${STALE:-0}" -eq 0 ] && exit 0

cat <<MSG
[driftguard] 개념 지도에 재확인 대상 ${STALE}건 (신선 ${FRESH}건).
  전부 보려면: \$CLAUDE_PLUGIN_ROOT/lib/fresh.sh "$MAP"
  이 수는 커밋된 이력만 본 것이다. 작업 트리의 미커밋 변경은 안 잡힌다.
MSG
