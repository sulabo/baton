#!/usr/bin/env bash
# SessionStart 훅. 개념 지도의 상태를 한 줄로 알린다.
#
# 두 가지를 지킨다.
#  1) 알릴 것이 없으면 조용하다. 매번 울리는 알람은 곧 무시당한다.
#  2) 지도가 있는데 쓸 수 없는 상태면 그것을 알린다. 조용한 것과 구분한다.
#
# 매 세션 도는 훅이라 느리면 안 된다. 전수 계산 대신 메타 줄만 센다.
set -uo pipefail

ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
MAP=$(find "$ROOT" -maxdepth 2 -name CONCEPTS.md -not -path "*/node_modules/*" 2>/dev/null | head -1)
[ -n "$MAP" ] || exit 0

CONC=$(grep -c '^## [0-9]\{1,\}\.' "$MAP" 2>/dev/null | tr -cd '0-9'); CONC=${CONC:-0}
META=$(grep -c '^- \*\*메타\*\*:' "$MAP" 2>/dev/null | tr -cd '0-9'); META=${META:-0}
[ "$CONC" -eq 0 ] && exit 0

# 메타 줄이 없으면 신선도를 못 센다. 이걸 침묵으로 두면 지도가 무용지물인 줄 모른다.
if [ "$META" -eq 0 ]; then
  echo "[baton] 개념 지도가 있는데 메타 줄이 없다 (개념 ${CONC}개)."
  echo "  신선도를 계산할 수 없다 — 0건이 아니라 '모름'이다."
  echo "  채우려면: /drift 또는 driftmap 스킬"
  exit 0
fi

# 여기서부터가 무거운 계산이다 (개념 수 × git log).
# HEAD와 지도 내용이 그대로면 결과도 그대로이므로 캐시한다.
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/baton"
KEY=$(printf '%s|%s|%s' "$MAP" \
      "$(git -C "$ROOT" rev-parse HEAD 2>/dev/null)" \
      "$(cksum < "$MAP" 2>/dev/null)" | cksum | tr -d ' ')
CACHE="$CACHE_DIR/$KEY"

if [ -r "$CACHE" ]; then
  OUT=$(cat "$CACHE")
else
  OUT=$("$CLAUDE_PLUGIN_ROOT/lib/fresh.sh" "$MAP" "$ROOT" 2>/dev/null) || exit 0
  mkdir -p "$CACHE_DIR" 2>/dev/null && {
    printf '%s' "$OUT" > "$CACHE" 2>/dev/null
    # 오래된 캐시를 치운다. 키가 바뀌면 파일이 쌓이기만 한다.
    find "$CACHE_DIR" -type f -mtime +7 -delete 2>/dev/null
  }
fi
STALE=$(echo "$OUT" | grep -c '재확인 필요' | tr -cd '0-9'); STALE=${STALE:-0}
FRESH=$(echo "$OUT" | grep -c '신선'      | tr -cd '0-9'); FRESH=${FRESH:-0}
[ "$STALE" -eq 0 ] && exit 0

echo "[baton] 개념 지도에 재확인 대상 ${STALE}건 (신선 ${FRESH}건). 자세히는 /drift"
[ "$META" -lt "$CONC" ] && echo "  개념 ${CONC}개 중 메타 줄 ${META}개 — 나머지 $((CONC-META))개는 아예 못 센다."
exit 0
