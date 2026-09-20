#!/usr/bin/env bash
# 모드 ④ 신선도 점검. 메타 줄을 읽어 개념별로 재확인 대상인지 계산한다.
#   fresh.sh <CONCEPTS.md 경로> [저장소 루트]
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
open_concepts "${1:-}" "fresh.sh" "[저장소 루트]"
[ -n "${2:-}" ] && ROOT="$2"

count() { grep -c . || true; }
row()   { printf "%-4s %-22s %-12s %s\n" "$1" "$2" "$3" "$4"; }

META=$(parse meta)
NMETA=$(echo "$META" | count)
NCONC=$(parse sections | count)

if [ "$NMETA" -eq 0 ]; then
  cat <<MSG
메타 줄이 하나도 없다 (개념 ${NCONC}개). **신선도를 계산할 수 없다 — 0건이 아니라 못 셌다.**

먼저 개념마다 제목 아래에 이 줄을 넣는다:
  - **메타**: 상태=… · 확인=YYYY-MM-DD(\`해시\`) · 파일=\`루트상대경로\` · 이웃=…

해시를 모르면 확인=YYYY-MM-DD(해시 미상)으로 두고 나중에 채운다.
파일이 없는 규칙 개념이면 파일=없음(규칙 개념).
MSG
  exit 2
fi
[ "$NMETA" -lt "$NCONC" ] && { echo "주의: 개념 ${NCONC}개 중 메타 줄 ${NMETA}개. 나머지는 표에 안 나온다."; echo; }

row "#" "개념" "상태" "판정"
printf -- "---- ---------------------- ------------ ------------------------------\n"

while IFS=$'\t' read -r num name state date hash files neighbors; do
  [ -z "$num" ] && continue

  [ "$hash" = "-" ] && hash=""
  [ "$files" = "-" ] && files=""

  case "$files" in *없음*) row "$num" "$name" "$state" "규칙 개념 — 결정 변동으로만 추적"; continue;; esac
  if [ -z "$hash" ]; then
    row "$num" "$name" "$state" "재확인 필요 — 기준 없음"; continue
  fi
  if ! git -C "$ROOT" cat-file -e "$hash" 2>/dev/null; then
    row "$num" "$name" "$state" "재확인 필요 — 기준 소실"; continue
  fi

  # 추적되는 파일로만 계산하고, 빠진 것은 따로 센다
  ok=""; untracked=0; gone=0
  for f in $(echo "$files" | tr -d '`' | tr ',' ' '); do
    if tracked "$f"; then ok="$ok $f"
    elif [ -e "$ROOT/$f" ]; then untracked=$((untracked+1))
    else gone=$((gone+1)); fi
  done

  if [ -z "$ok" ]; then
    [ "$untracked" -gt 0 ] && row "$num" "$name" "$state" "재확인 필요 — 미추적" \
                           || row "$num" "$name" "$state" "재확인 필요 — 경로 소실"
    continue
  fi

  extra=""
  [ "$untracked" -gt 0 ] && extra=" (미추적 ${untracked}개 제외)"
  [ "$gone" -gt 0 ]      && extra="$extra (경로 소실 ${gone}개)"

  n=$(git -C "$ROOT" log --oneline "$hash"..HEAD -- $ok 2>/dev/null | count)
  [ "$n" -gt 0 ] && row "$num" "$name" "$state" "재확인 필요 — 커밋 ${n}건${extra}" \
                 || row "$num" "$name" "$state" "신선${extra}"
done <<< "$META"

# ── 결정이 움직였는가 (전역 1회, 형식 자동 판별)
OLDEST=$(echo "$META" | cut -f5 | grep -v '^-$' | grep . | while read -r h; do
           git -C "$ROOT" log --format="%ct $h" -1 "$h" 2>/dev/null
         done | sort -n | head -1 | awk '{print $2}')
[ -z "$OLDEST" ] && exit 0

GOV=""
for g in DECISIONS.md AGENTS.md CLAUDE.md; do tracked "$g" && GOV="$GOV $g"; done
[ -z "$GOV" ] && exit 0

DC=$(git -C "$ROOT" log --oneline "$OLDEST"..HEAD -- $GOV 2>/dev/null | count)
echo
echo "결정·지침 변동: 가장 오래된 확인($OLDEST) 이후 커밋 ${DC}건"
[ "$DC" -eq 0 ] && exit 0
[ -f "$ROOT/DECISIONS.md" ] || exit 0

D=$(git -C "$ROOT" diff "$OLDEST"..HEAD -- DECISIONS.md 2>/dev/null)
HEADN=$(grep -c '^## [0-9]\{4\}-' "$ROOT/DECISIONS.md" 2>/dev/null | tr -cd '0-9')
TABN=$(grep -cE '^\| *[A-Z]+[0-9]+ *\|' "$ROOT/DECISIONS.md" 2>/dev/null | tr -cd '0-9')

if [ "${HEADN:-0}" -ge "${TABN:-0}" ] && [ "${HEADN:-0}" -gt 0 ]; then
  NEWN=$(echo "$D" | grep -c '^+## [0-9]\{4\}-' | tr -cd '0-9')
  RELN=$(echo "$D" | grep -c '^+- 관련:' | tr -cd '0-9')
  echo "  형식: 날짜 헤딩 · 새 결정 ${NEWN}건 · '관련:' 줄 ${RELN}건 · 구멍 $((NEWN-RELN))건"
  [ "$((NEWN-RELN))" -gt 0 ] && echo "  → 관련 줄 없는 결정은 어느 개념을 건드렸는지 알 수 없다. 갱신 경로의 구멍으로 보고한다."
elif [ "${TABN:-0}" -gt 0 ]; then
  IDS=$(echo "$D" | grep -oE '^\+\| *[A-Z]+[0-9]+ *\|' | grep -oE '[A-Z]+[0-9]+' | tr '\n' ' ')
  echo "  형식: 표(결정 ID) · 새 결정 행 $(echo "$IDS" | wc -w | tr -d ' ')건${IDS:+  — $IDS}"
  echo "  → 이 형식에는 '관련:' 줄 관행이 없다. 어느 개념이 걸리는지는 ID를 개념 절에서 찾아 잇는다."
  for i in $IDS; do
    grep -q "$i" "$F" || echo "     $i: 개념 지도에 언급 없음 — 어느 개념에 걸리는지 확인 필요"
  done
else
  echo "  형식 불명 — **0건이 아니라 못 셌다.** DECISIONS.md를 직접 열어 확인한다."
fi
git -C "$ROOT" log --oneline "$OLDEST"..HEAD -- $GOV 2>/dev/null | head -4 | sed 's/^/     /'

# ── 파일 항목에 지침·결정 파일이 섞여 있는가
MIX=$(echo "$META" | cut -f6 | grep -cE 'AGENTS\.md|DECISIONS\.md|CLAUDE\.md|TODO\.md' | tr -cd '0-9')
if [ "${MIX:-0}" -gt 0 ]; then
  cat <<MSG

경고: 개념 ${MIX}개의 '파일' 항목에 지침·결정 파일이 섞여 있다.
  그 파일들은 거의 매일 바뀌어서 실제 내용이 가만히 있어도 재확인 대상이 된다.
  '파일'에는 실제 동작 근거(코드·산출물)만 남기고, 결정 변동은 위 전역 검사로 본다.
MSG
fi
