#!/usr/bin/env bash
# 승격 검토. HANDOFF.md 과거 판에서 DECISIONS.md로 올릴 것을 뽑는다.
#   promote.sh [저장소 경로] [판수(기본 8)]
# 종료코드: 0 = 돌았음, 2 = 못 돌림
set -uo pipefail

R="${1:-.}"
K="${2:-8}"
THRESHOLD=3          # 서로 다른 N일 이상 살아남으면 승격 후보
WIDTH=55             # 문구가 조금씩 다듬어진 같은 항목을 묶기 위한 절단 폭

die() { printf '%s\n' "$@"; exit 2; }

git -C "$R" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  || die "git 저장소가 아니다: $R" "사용법: promote.sh <저장소 경로> [판수]"

[ -f "$R/HANDOFF.md" ] || die \
  "HANDOFF.md가 없다: $R" \
  "승격 검토는 과거 판을 보는 일이라 인계서가 먼저 있어야 한다." \
  "이번이 처음이면 인계서부터 쓰고, 다음 번에 이 검토를 돌린다."

git -C "$R" ls-files --error-unmatch HANDOFF.md >/dev/null 2>&1 || die \
  "HANDOFF.md는 있는데 git이 추적하지 않는다. 승격 검토 불가 — 과거 판을 못 본다." \
  "먼저: git -C \"$R\" add HANDOFF.md && git -C \"$R\" commit -m 'chore: 인계서 추적 시작'"

count() { grep -c . || true; }

# 한 판에서 절 하나를 뽑는다. 절 제목은 저장소마다 다르므로 앞머리만 맞춘다.
#   `## E. 실패한 접근법` 처럼 절 기호가 붙어도 잡힌다.
section() {   # $1=커밋 $2=시작 표제 $3=끝 표제
  git -C "$R" show "$1:HANDOFF.md" 2>/dev/null \
    | sed -n "/^#.*$2/,/^#.*$3/p" | grep '^- ' | cut -c1-"$WIDTH"
}

# 같은 날 여러 번 커밋하면 절이 통째로 복붙돼 가짜 반복이 된다. 날짜당 최신 한 판만 쓴다.
DAYS=$(git -C "$R" log --format="%ad %h" --date=short -- HANDOFF.md \
         | awk '!seen[$1]++{print $2}' | head -"$K")
NDAY=$(echo "$DAYS" | count)
NCOMMIT=$(git -C "$R" log --format=%h -- HANDOFF.md | head -"$K" | count)
echo "저장소: $(basename "$R")  ·  검토 ${NDAY}일 (커밋 수로는 ${NCOMMIT}판이지만 날짜당 1판만 센다)"

# ── A. 반복 실패 — 서로 다른 N일 이상 살아남은 제약
FAILS=""; MISS=0
for sha in $DAYS; do
  body=$(section "$sha" "실패한 접근법" "검증")
  if [ -z "$body" ]; then MISS=$((MISS+1)); else FAILS="${FAILS}${body}"$'\n'; fi
done
echo
echo "[A] 반복 실패 — 서로 다른 ${THRESHOLD}일 이상 살아남은 제약"
[ "$MISS" -gt 0 ] && echo "    형식 불일치로 못 센 판 ${MISS}개 (분모는 $((NDAY-MISS))일)"
REPEATED=$(printf '%s' "$FAILS" | sort | uniq -c | sort -rn | awk -v t="$THRESHOLD" '$1>=t')
echo "$REPEATED" | awk 'NF{$1=$1" 일:"; print "    "$0}' | head -12
echo "    → $(echo "$REPEATED" | count)건"

# ── B. 탈락 — 앞선 판에 2일 이상 있던 상시 제약이 최신판에서 사라짐
echo
echo "[B] 탈락 — 상시 제약이 최신판에서 조용히 빠짐"
LATEST=$(echo "$DAYS" | head -1)
NOW=$(section "$LATEST" "확인된 사실과 결정" "관련 파일" | sort -u)
if [ -z "$NOW" ]; then
  echo "    최신판에 '확인된 사실과 결정' 절이 없다 — 이 신호는 못 센다 (0건이 아니라 못 셈)"
else
  PAST_RAW=""; BMISS=0
  for sha in $(echo "$DAYS" | tail -n +2); do
    body=$(section "$sha" "확인된 사실과 결정" "관련 파일")
    if [ -z "$body" ]; then BMISS=$((BMISS+1)); else PAST_RAW="${PAST_RAW}${body}"$'\n'; fi
  done
  [ "$BMISS" -gt 0 ] && echo "    절 구조가 다른 판 ${BMISS}개는 못 셌다 (분모 $((NDAY-1-BMISS))일)"

  PAST=$(printf '%s' "$PAST_RAW" | sort | uniq -c \
           | awk '$1>=2{sub(/^ *[0-9]+ /,""); print}' | sort -u)
  DROPPED=$(comm -23 <(printf '%s\n' "$PAST" | grep . | sort) <(printf '%s\n' "$NOW" | grep . | sort))

  # 결정 표지가 붙은 것을 위로 — 그쪽이 DECISIONS.md 감이다
  MARKED=$(echo "$DROPPED" | grep -E "소유자 결정|확정|금지|절대|채택|해제|정본|[A-Z][0-9]{1,2}\b" || true)
  PLAIN=$(comm -23 <(printf '%s\n' "$DROPPED" | grep . | sort) <(printf '%s\n' "$MARKED" | grep . | sort))
  if [ -n "$MARKED" ]; then
    echo "    ── 결정 표지가 붙은 것 ($(echo "$MARKED" | count)건) — 먼저 본다"
    echo "$MARKED" | sed 's/^/      /' | head -10
  fi
  echo "    ── 표지 없는 것 $(echo "$PLAIN" | count)건 (대개 끝난 작업 메모)"
  echo "    → 탈락 총 $(echo "$DROPPED" | count)건. 전부가 승격감은 아니다. 끝난 일인지 살아 있는 제약인지 사람이 가른다"
fi

# ── C. 번복 — 자동 탐지 불가
echo
echo "[C] 번복 — 문자열로는 안 잡힌다. 소유자가 알려줄 때만 후보로 올린다."
echo
echo "기각 목록을 먼저 확인한다: HANDOFF.md 의 '기각됨' 절"
REJECTED=$(grep -A20 '기각됨' "$R/HANDOFF.md" 2>/dev/null | grep '^- ' | head -5)
if [ -n "$REJECTED" ]; then echo "$REJECTED" | sed 's/^/    이미 기각: /'; else echo "    (기각 목록 없음)"; fi
