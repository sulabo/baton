#!/usr/bin/env bash
# 승격 검토. HANDOFF.md 과거 판에서 DECISIONS.md로 올릴 것을 뽑는다.
#   promote.sh [저장소 경로] [판수(기본 8)]
set -uo pipefail
R="${1:-.}"; K="${2:-8}"
git -C "$R" rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
  echo "git 저장소가 아니다: $R"; echo "사용법: promote.sh <저장소 경로> [판수]"; exit 2; }
if [ ! -f "$R/HANDOFF.md" ]; then
  echo "HANDOFF.md가 없다: $R"
  echo "승격 검토는 과거 판을 보는 일이라 인계서가 먼저 있어야 한다."
  echo "이번이 처음이면 인계서부터 쓰고, 다음 번에 이 검토를 돌린다."
  exit 2
fi
git -C "$R" ls-files --error-unmatch HANDOFF.md >/dev/null 2>&1 || {
  echo "HANDOFF.md는 있는데 git이 추적하지 않는다. 승격 검토 불가 — 과거 판을 못 본다."
  echo "먼저: git -C \"$R\" add HANDOFF.md && git -C \"$R\" commit -m 'chore: 인계서 추적 시작'"
  exit 2; }
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
# 같은 날 여러 번 커밋하면 절이 통째로 복붙돼 가짜 반복이 된다. 날짜당 최신 한 판만 쓴다.
git -C "$R" log --format="%ad %h" --date=short -- HANDOFF.md | awk '!seen[$1]++{print $2}' | head -"$K" > "$T/shas"
NV=$(wc -l < "$T/shas" | tr -d ' ')
ALL=$(git -C "$R" log --format=%h -- HANDOFF.md | head -"$K" | wc -l | tr -d ' ')
echo "저장소: $(basename "$R")  ·  검토 ${NV}일 (커밋 수로는 ${ALL}판이지만 날짜당 1판만 센다)"

sec() { git -C "$R" show "$1:HANDOFF.md" 2>/dev/null | sed -n "/^#.*$2/,/^#.*$3/p" | grep '^- ' | cut -c1-55; }

# ── A. 반복 실패 (3판 이상 살아남음)
: > "$T/fail"; MISS=0
while read -r s; do
  B=$(sec "$s" "실패한 접근법" "검증")
  [ -z "$B" ] && { MISS=$((MISS+1)); continue; }
  echo "$B" >> "$T/fail"
done < "$T/shas"
echo
echo "[A] 반복 실패 — 서로 다른 3일 이상 살아남은 제약"
[ "$MISS" -gt 0 ] && echo "    형식 불일치로 못 센 판 ${MISS}개 (분모는 $((NV-MISS))일)"
sort "$T/fail" | uniq -c | sort -rn | awk '$1>=3{$1=$1" 일:";print "    "$0}' | head -12
AC=$(sort "$T/fail" | uniq -c | awk '$1>=3' | wc -l | tr -d ' ')
echo "    → ${AC}건"

# ── B. 탈락 — 앞선 판에 2판 이상 있었는데 최신판에서 사라진 상시 제약
echo
echo "[B] 탈락 — 상시 제약이 최신판에서 조용히 빠짐"
SKIPB=0
NEW=$(head -1 "$T/shas")
sec "$NEW" "확인된 사실과 결정" "관련 파일" | sort -u > "$T/now"
if [ ! -s "$T/now" ]; then
  echo "    최신판에 '확인된 사실과 결정' 절이 없다 — 이 신호는 못 센다 (0건이 아니라 못 셈)"
  echo "    → 건너뜀"; SKIPB=1
fi
: > "$T/raw"; BMISS=0
tail -n +2 "$T/shas" | while read -r s; do
  O=$(sec "$s" "확인된 사실과 결정" "관련 파일")
  [ -z "$O" ] && echo "MISS $s" >> "$T/bmiss" || echo "$O" >> "$T/raw"
done
[ -f "$T/bmiss" ] && BMISS=$(wc -l < "$T/bmiss" | tr -d ' ')
[ "$BMISS" -gt 0 ] && echo "    절 구조가 다른 판 ${BMISS}개는 못 셌다 (분모 $((NV-1-BMISS))판)"
sort "$T/raw" | uniq -c | awk '$1>=2{sub(/^ *[0-9]+ /,"");print}' | sort -u > "$T/past"
comm -23 "$T/past" "$T/now" > "$T/drop"
BC=$(wc -l < "$T/drop" | tr -d ' ')
# 결정 표지가 붙은 것을 위로 올린다 — 그쪽이 DECISIONS.md 감이다
grep -E "소유자 결정|확정|금지|절대|채택|해제|정본|[A-Z][0-9]{1,2}\b" "$T/drop" > "$T/hi" 2>/dev/null || : > "$T/hi"
comm -23 "$T/drop" <(sort "$T/hi") > "$T/lo" 2>/dev/null || : > "$T/lo"
HC=$(wc -l < "$T/hi" | tr -d ' ')
if [ "$HC" -gt 0 ]; then
  echo "    ── 결정 표지가 붙은 것 (${HC}건) — 먼저 본다"
  sed 's/^/      /' "$T/hi" | head -10
fi
echo "    ── 표지 없는 것 $(wc -l < "$T/lo" | tr -d ' ')건 (대개 끝난 작업 메모)"
echo "    → 탈락 총 ${BC}건. 전부가 승격감은 아니다. 끝난 일인지 살아 있는 제약인지 사람이 가른다"

echo
echo "[C] 번복 — 문자열로는 안 잡힌다. 소유자가 알려줄 때만 후보로 올린다."
echo
echo "기각 목록을 먼저 확인한다: HANDOFF.md 의 '기각됨' 절"
grep -A20 '기각됨' "$R/HANDOFF.md" 2>/dev/null | grep '^- ' | head -5 | sed 's/^/    이미 기각: /' || echo "    (기각 목록 없음)"
