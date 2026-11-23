#!/usr/bin/env bash
# SessionStart 훅. 개념 지도의 상태를 한 줄로 알린다.
#
# 두 가지를 지킨다.
#  1) 알릴 것이 없으면 조용하다. 매번 울리는 알람은 곧 무시당한다.
#  2) 지도가 있는데 쓸 수 없는 상태면 그것을 알린다. 조용한 것과 구분한다.
#
# 매 세션 도는 훅이라 느리면 안 된다. 전수 계산 대신 메타 줄만 센다.
# 출력은 JSON additionalContext — 일반 stdout은 Claude Code만 맥락에 넣고 Codex는 버린다(10-01 확인, handoff-inject.py와 같은 이유).
set -uo pipefail

emit() {
  python3 -c 'import json, sys; print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": sys.argv[1]}}, ensure_ascii=False))' "$1"
}

ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
MAP=$(find "$ROOT" -maxdepth 2 -name CONCEPTS.md -not -path "*/node_modules/*" 2>/dev/null | head -1)
[ -n "$MAP" ] || exit 0
# 메시지 언어는 한 번만 정하고 자식(concepts.py·fresh.sh)에게 BATON_LANG으로 넘긴다. 순서는 lib/i18n.py
L=$(python3 "$CLAUDE_PLUGIN_ROOT/lib/i18n.py" "$ROOT" 2>/dev/null) || L=en
[ "$L" = ko ] || L=en
export BATON_LANG="$L"

# 개념·메타 줄 수는 파서로 센다 — grep은 코드 펜스 안의 예시 제목·메타 줄까지 세어 "개념 2개 중 메타 줄 1개" 같은 거짓 알림을 냈다(재현 저장소 t6)
PARSER="$CLAUDE_PLUGIN_ROOT/lib/concepts.py"
if ! SECS=$(python3 "$PARSER" "$MAP" sections 2>/dev/null) || ! METAS=$(python3 "$PARSER" "$MAP" meta 2>/dev/null); then
  if [ "$L" = ko ]; then emit "[baton] 개념 지도를 읽지 못했다 — 0건이 아니라 못 셌다. /drift로 직접 본다."
  else emit "[baton] Could not read the concept map — this is not 0, it could not be counted. Run /drift to see it."; fi
  exit 0
fi
CONC=$(printf '%s' "$SECS" | grep -c . | tr -cd '0-9'); CONC=${CONC:-0}
META=$(printf '%s' "$METAS" | grep -c . | tr -cd '0-9'); META=${META:-0}
[ "$CONC" -eq 0 ] && exit 0

# 메타 줄이 없으면 신선도를 못 센다. 이걸 침묵으로 두면 지도가 무용지물인 줄 모른다.
if [ "$META" -eq 0 ]; then
  if [ "$L" = ko ]; then emit "[baton] 개념 지도가 있는데 메타 줄이 없다 (개념 ${CONC}개).
  신선도를 계산할 수 없다 — 0건이 아니라 '모름'이다.
  채우려면: /drift 또는 driftmap 스킬"
  else emit "[baton] The concept map has no metadata lines (concepts: ${CONC}).
  Freshness can't be computed — this is not 0, it is unknown.
  To fill them in: /drift or the driftmap skill"; fi
  exit 0
fi

# 여기서부터가 무거운 계산이다 (개념 수 × git log).
# HEAD와 지도 내용이 그대로면 결과도 그대로이므로 캐시한다.
# 전용 하위 폴더 — baton/ 바로 아래에는 관찰 로그·알림 상태·설치 사본(stage-plugin.sh 기본값)이 있다.
# 10-01 이전에는 baton/ 전체에서 7일 넘은 파일을 지워 그것들까지 지웠다.
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/baton/drift"
# fresh.sh도 키에 넣는다 — 플러그인을 갱신해 출력 형식이 바뀌면 옛 캐시를 읽지 않게. 언어도 — 출력 낱말이 다르다
KEY=$(printf '%s|%s|%s|%s|%s' "$L" "$MAP" \
      "$(git -C "$ROOT" rev-parse HEAD 2>/dev/null)" \
      "$(cksum < "$MAP" 2>/dev/null)" \
      "$(cksum < "$CLAUDE_PLUGIN_ROOT/lib/fresh.sh" 2>/dev/null)" | cksum | tr -d ' ')
CACHE="$CACHE_DIR/$KEY"

if [ -r "$CACHE" ]; then
  OUT=$(cat "$CACHE")
else
  OUT=$("$CLAUDE_PLUGIN_ROOT/lib/fresh.sh" "$MAP" "$ROOT" 2>/dev/null) || exit 0
  mkdir -p "$CACHE_DIR" 2>/dev/null && {
    printf '%s' "$OUT" > "$CACHE" 2>/dev/null
    # 오래된 캐시를 치운다. 키가 바뀌면 파일이 쌓이기만 한다.
    find "$CACHE_DIR" -maxdepth 1 -type f -mtime +7 -delete 2>/dev/null
  }
fi
# 표의 글자를 세지 않고 fresh.sh 끝의 요약 줄을 읽는다. 개념 이름에 '신선'·'재확인'이 들어 있으면 표를 세는 방식은 틀린다(2026-11-21)
# 요약 줄은 두 언어 다 읽는다: '요약: 재확인 N · 신선 M · …' · 'Summary: re-check N · fresh M · …'
SUM=$(echo "$OUT" | grep -E '^(요약: 재확인 [0-9]* · 신선 [0-9]*|Summary: re-check [0-9]* · fresh [0-9]*)' | tail -1)
if [ -z "$SUM" ]; then    # 요약이 없으면 못 센 것이다 — 조용히 두면 "재확인 0건"과 구분되지 않는다
  if [ "$L" = ko ]; then emit "[baton] 개념 지도의 신선도 요약을 못 읽었다 — 0건이 아니라 못 셌다. /drift로 직접 본다."
  else emit "[baton] Could not read the freshness summary of the concept map — this is not 0, it could not be counted. Run /drift to see it."; fi
  exit 0
fi
STALE=$(echo "$SUM" | sed -E 's/^(요약: 재확인|Summary: re-check) ([0-9]*).*/\2/'); STALE=${STALE:-0}
FRESH=$(echo "$SUM" | sed -E 's/.* (신선|fresh) ([0-9]*).*/\2/'); FRESH=${FRESH:-0}
# 파서 경고(fresh.sh의 '주의: 코드 펜스…' · 'Warning: a code fence…')가 있으면 재확인 0건이어도 알린다 — 표에 없는 개념이 있을 수 있다
PWARN=$(echo "$OUT" | grep -E '^(주의: 코드 펜스|Warning: a code fence)' | sed -E 's/^(주의|Warning): //')
[ "$STALE" -eq 0 ] && [ -z "$PWARN" ] && exit 0

if [ "$L" = ko ]; then
  MSG="[baton] 개념 지도에 재확인 대상 ${STALE}건 (신선 ${FRESH}건). 자세히는 /drift"
  [ "$META" -lt "$CONC" ] && MSG="$MSG
  개념 ${CONC}개 중 메타 줄 ${META}개 — 나머지 $((CONC-META))개는 아예 못 센다."
else
  if [ "$STALE" -eq 1 ]; then MSG="[baton] 1 concept in the concept map needs a re-check"
  else MSG="[baton] ${STALE} concepts in the concept map need a re-check"; fi
  MSG="$MSG (${FRESH} fresh). Details: /drift"
  [ "$META" -lt "$CONC" ] && MSG="$MSG
  Only ${META} of ${CONC} concepts have a metadata line — the other $((CONC-META)) can't be counted at all."
fi
[ -n "$PWARN" ] && MSG="$MSG
  ${PWARN}"
emit "$MSG"
exit 0
