#!/usr/bin/env bash
# SessionStart 훅. 개념 지도의 상태를 한 줄로 알린다.
#
# 두 가지를 지킨다.
#  1) 알릴 것이 없으면 조용하다. 매번 울리는 알람은 곧 무시당한다.
#  2) 지도가 있는데 쓸 수 없는 상태면 그것을 알린다. 조용한 것과 구분한다.
#
# 매 세션 도는 훅이라 느리면 안 된다. 전수 계산 대신 메타 줄만 센다.
# 같은 지도의 같은 알림은 하루에 한 번만 낸다 — 숫자가 바뀌면 문장이 달라져 바로 다시 낸다(11-25 실사용: 같은 숫자를 대화 시작마다
# 약 111번 알렸고 /drift는 한 번도 안 돌렸다. /clear·압축 뒤에도 SessionStart가 돈다). 끄기: BATON_DRIFT_NOTICE=off(환경변수 또는 설정 파일).
# 출력은 JSON additionalContext — 일반 stdout은 Claude Code만 맥락에 넣고 Codex는 버린다(10-01 확인, handoff-inject.py와 같은 이유).
set -uo pipefail

# -I: 현재 폴더(저장소 루트)를 import 경로에 넣지 않는다 — 저장소에 json.py 같은 파일이 있으면 그것을 불러와 실행했다
# SEEN(이 지도·언어에 마지막으로 낸 알림)과 내용이 같고 그 뒤 하루가 안 지났으면 내지 않는다. 낸 뒤에 SEEN을 쓴다
emit() {
  if [ -r "$SEEN" ] && [ "$(cat "$SEEN" 2>/dev/null)" = "$1" ] && [ -n "$(find "$SEEN" -mmin -1440 2>/dev/null)" ]; then
    return 0
  fi
  python3 -I -c 'import json, sys; print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": sys.argv[1]}}, ensure_ascii=False))' "$1"
  mkdir -p "$CACHE_DIR" 2>/dev/null && printf '%s' "$1" > "$SEEN" 2>/dev/null
}

ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
# 끄기 스위치는 다른 훅처럼 lib/config.py로 읽는다(환경변수 > 저장소 절 > 전역 절). 못 읽으면 켠 것으로 본다
SW=$(python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import config; print(config.get("BATON_DRIFT_NOTICE", sys.argv[2]).strip().lower())' \
     "$CLAUDE_PLUGIN_ROOT/lib" "$ROOT" 2>/dev/null)
case "$SW" in off|0|false|no) exit 0 ;; esac
MAP=$(find "$ROOT" -maxdepth 2 -name CONCEPTS.md -not -path "*/node_modules/*" 2>/dev/null | head -1)
[ -n "$MAP" ] || exit 0
# 메시지 언어는 한 번만 정하고 자식(concepts.py·fresh.sh)에게 BATON_LANG으로 넘긴다. 순서는 lib/i18n.py,
# python3가 없으면 lib/lib.sh의 baton_lang_sh(환경변수·로캘)
. "$CLAUDE_PLUGIN_ROOT/lib/lib.sh" 2>/dev/null
L=$(python3 "$CLAUDE_PLUGIN_ROOT/lib/i18n.py" "$ROOT" 2>/dev/null) || L=$(baton_lang_sh 2>/dev/null)
[ "$L" = ko ] || L=en
export BATON_LANG="$L"
# 전용 하위 폴더 — baton/ 바로 아래에는 관찰 로그·알림 상태·설치 사본(stage-plugin.sh 기본값)이 있다.
# 10-01 이전에는 baton/ 전체에서 7일 넘은 파일을 지워 그것들까지 지웠다.
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/baton/drift"
SEEN="$CACHE_DIR/shown-$(printf '%s|%s' "$L" "$MAP" | cksum | tr -d ' ')"

# 개념·메타 줄 수는 파서로 센다 — grep은 코드 펜스 안의 예시 제목·메타 줄까지 세어 "개념 2개 중 메타 줄 1개" 같은 거짓 알림을 냈다(재현 저장소 t6)
PARSER="$CLAUDE_PLUGIN_ROOT/lib/concepts.py"
if ! SECS=$(python3 "$PARSER" "$MAP" sections 2>/dev/null) || ! METAS=$(python3 "$PARSER" "$MAP" meta 2>/dev/null); then
  if [ "$L" = ko ]; then emit "[baton] 개념 지도를 읽지 못해서 바뀐 개념을 셀 수 없어요. /drift로 직접 확인해 보세요."
  else emit "[baton] Couldn't read the concept map, so baton can't tell which concepts changed. Try /drift to check it directly."; fi
  exit 0
fi
CONC=$(printf '%s' "$SECS" | grep -c . | tr -cd '0-9'); CONC=${CONC:-0}
META=$(printf '%s' "$METAS" | grep -c . | tr -cd '0-9'); META=${META:-0}
[ "$CONC" -eq 0 ] && exit 0

# 메타 줄이 없으면 신선도를 못 센다. 이걸 침묵으로 두면 지도가 무용지물인 줄 모른다.
if [ "$META" -eq 0 ]; then
  if [ "$L" = ko ]; then emit "[baton] 개념 지도에 확인 기록(메타 줄)이 없어서 어떤 개념이 바뀌었는지 셀 수 없어요(개념 ${CONC}개).
채우려면 /drift를 실행하거나 \"개념 지도 갱신해 줘\"라고 해 보세요."
  else
    if [ "$CONC" -eq 1 ]; then N_EN="1 concept"; else N_EN="${CONC} concepts"; fi
    emit "[baton] The concept map has no check records (metadata lines), so baton can't tell which concepts changed (${N_EN}).
To fill them in, run /drift or say \"update the concept map\"."
  fi
  exit 0
fi

# 여기서부터가 무거운 계산이다 (개념 수 × git log).
# HEAD와 지도 내용이 그대로면 결과도 그대로이므로 캐시한다(CACHE_DIR은 위).
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
  if [ "$L" = ko ]; then emit "[baton] 개념 지도의 확인 결과를 읽지 못해서 바뀐 개념을 셀 수 없어요. /drift로 직접 확인해 보세요."
  else emit "[baton] Couldn't read the concept map's check results, so baton can't tell which concepts changed. Try /drift to check it directly."; fi
  exit 0
fi
STALE=$(echo "$SUM" | sed -E 's/^(요약: 재확인|Summary: re-check) ([0-9]*).*/\2/'); STALE=${STALE:-0}
FRESH=$(echo "$SUM" | sed -E 's/.* (신선|fresh) ([0-9]*).*/\2/'); FRESH=${FRESH:-0}
# 파서 경고(fresh.sh의 '주의: 코드 펜스…' · 'Warning: a code fence…')가 있으면 재확인 0건이어도 알린다 — 표에 없는 개념이 있을 수 있다
PWARN=$(echo "$OUT" | grep -E '^(주의: 코드 펜스|Warning: a code fence)' | sed -E 's/^(주의|Warning): //')
[ "$STALE" -eq 0 ] && [ -z "$PWARN" ] && exit 0

# 펜스 경고는 줄 번호와 못 읽은 개념 수(concepts.py warnings의 두 숫자)만 꺼내 다시 쓴다. 꺼내지 못하면 경고 원문을 쓴다
PW1=$(printf '%s\n' "$PWARN" | head -1)
FLINE=$(printf '%s\n' "$PW1" | grep -oE '[0-9]+' | sed -n 1p)
FLOST=$(printf '%s\n' "$PW1" | grep -oE '[0-9]+' | sed -n 2p)
GAP=$((CONC-META))
if [ "$L" = ko ]; then
  FENCE="개념 지도의 ${FLINE}번째 줄에서 연 코드 블록이 닫히지 않아서, 그 뒤 개념 ${FLOST}개를 읽지 못했어요."
  [ -n "$FLINE" ] && [ -n "$FLOST" ] || FENCE="개념 지도 일부를 읽지 못했어요: ${PW1}."
  if [ "$STALE" -gt 0 ]; then
    MSG="[baton] 개념 지도에서 다시 확인할 개념이 ${STALE}개 있어요(그대로인 개념 ${FRESH}개). 자세히 보려면 /drift"
    [ -n "$PWARN" ] && MSG="$MSG
$FENCE"
  else MSG="[baton] $FENCE 자세히 보려면 /drift"; fi
  [ "$GAP" -gt 0 ] && MSG="$MSG
개념 ${CONC}개 중 ${GAP}개는 확인 기록(메타 줄)이 없어서 세지 못했어요."
else
  [ "$FLOST" = 1 ] && C_EN="concept" || C_EN="concepts"
  FENCE="In the concept map, a code block opened at line ${FLINE} is never closed, so ${FLOST} ${C_EN} after it couldn't be read."
  [ -n "$FLINE" ] && [ -n "$FLOST" ] || FENCE="Part of the concept map couldn't be read: ${PW1}."
  if [ "$STALE" -gt 0 ]; then
    if [ "$STALE" -eq 1 ]; then MSG="[baton] 1 concept in the concept map needs another look"
    else MSG="[baton] ${STALE} concepts in the concept map need another look"; fi
    MSG="$MSG (${FRESH} unchanged). For details: /drift"
    [ -n "$PWARN" ] && MSG="$MSG
$FENCE"
  else MSG="[baton] $FENCE For details: /drift"; fi
  if [ "$GAP" -eq 1 ]; then MSG="$MSG
1 of ${CONC} concepts has no check record (metadata line), so it wasn't counted."
  elif [ "$GAP" -gt 1 ]; then MSG="$MSG
${GAP} of ${CONC} concepts have no check record (metadata line), so they weren't counted."; fi
fi
emit "$MSG"
exit 0
