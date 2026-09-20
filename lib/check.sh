#!/usr/bin/env bash
# CONCEPTS.md 기계 검사. 사람 판단이 필요 없는 것만 본다.
#   check.sh <CONCEPTS.md 경로>
# 종료코드: 0 = 지적 없음, 1 = 지적 있음, 2 = 못 돌림
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
open_concepts "${1:-}" "check.sh"

N=0
count() { grep -c . || true; }          # 빈 입력에서도 0을 낸다

echo "검사 대상: $(basename "$DIR")/$(basename "$F")"
echo "저장소 루트: $(basename "$ROOT")"
echo

BODY=$(parse sections | cut -f1 | sort -n)
CN=$(echo "$BODY" | count)

# ── 1. 요약표 행 ↔ 본문 절
echo "[1] 요약표와 본문 절이 일대일인가"
TBL=$(parse table | cut -f1 | sort -n | uniq)
if [ -z "$TBL" ]; then
  ROWS=$(parse rows)
  echo "    번호 열 없는 표 — 행 수로만 대조: 표 ${ROWS}행 vs 본문 ${CN}절"
  if [ "$ROWS" -ne "$CN" ]; then
    echo "    행 수 불일치 (이름으로 직접 대조 필요)"; N=$((N+1))
  fi
else
  for n in $TBL;  do echo "$BODY" | grep -qx "$n" || { echo "    표에만 있고 본문 절 없음: 개념 $n"; N=$((N+1)); }; done
  for n in $BODY; do echo "$TBL"  | grep -qx "$n" || { echo "    본문에만 있고 표에 없음: 개념 $n"; N=$((N+1)); }; done
fi

# ── 2. 근거 경로가 신선도 계산에 쓸 수 있는 형태인가
echo "[2] 근거 경로가 신선도 계산에 쓸 수 있는가"
BAD=""; TOT=0
while IFS= read -r p; do
  [ -z "$p" ] && continue
  TOT=$((TOT+1))
  msg=$(diagnose_path "$p") || BAD="${BAD}${msg}"$'\n'
done <<< "$(parse evidence)"
if [ -n "$BAD" ]; then
  BC=$(printf '%s' "$BAD" | count)
  printf '%s' "$BAD" | sort
  echo "    → 근거 ${TOT}개 중 ${BC}개가 그대로는 신선도 계산 불가"
  N=$((N+BC))
else
  echo "    지적 없음 (${TOT}개 전부 루트 상대로 추적됨)"
fi

# ── 3. 개념 간 참조가 양방향인가
echo "[3] 개념 사이 참조가 양방향인가"
REFS=$(parse refs)
ONE=$(echo "$REFS" | while IFS=$'\t' read -r a b; do
  [ -z "$a" ] && continue
  echo "$REFS" | grep -qx "$b	$a" || echo "    한쪽만: 개념 $a 가 개념 $b 를 가리키는데 그쪽에 역참조 없음"
done)
OC=$(echo "$ONE" | count)
[ "$OC" -gt 0 ] && echo "$ONE"
echo "    참조 $(echo "$REFS" | count)건 · 한쪽만 ${OC}건"
N=$((N+OC))

# ── 4. 상태 어휘 (상태를 적는 자리만 본다. 본문 산문은 보지 않는다)
echo "[4] 닫힌 상태 어휘 밖의 말을 쓰는가"
STATES=$(parse states)
OUT=0
for st in $(echo "$STATES" | tr ' ' '\v'); do
  case "$(echo "$st" | tr '\v' ' ')" in
    일치|미구현|"낡은 문서"|미결|"중복 정본"|"확인 못 함") ;;
    해소됨*|폐기됨*|없음*|규칙*) ;;
    *) echo "    닫힌 어휘 밖: '$(echo "$st" | tr '\v' ' ')'"; OUT=$((OUT+1)) ;;
  esac
done
if [ "$OUT" -eq 0 ]; then
  echo "    지적 없음 ($(echo "$STATES" | count)종 확인)"
else
  N=$((N+OUT))
fi

# ── 5. '파일' 항목이 실제 동작 근거만 담고 있는가
echo "[5] '파일' 항목이 실제 동작 근거만 담고 있는가"
GOV='AGENTS\.md|DECISIONS\.md|CLAUDE\.md|TODO\.md'
MIXED=$(parse meta | cut -f6 | grep -E "$GOV" || true)
MIXN=$(echo "$MIXED" | count)
if [ "$MIXN" -gt 0 ]; then
  echo "    지침·결정 파일이 섞인 개념 ${MIXN}개 — 신선도 신호가 망가진다"
  echo "$MIXED" | grep -oE "[^,\`]*($GOV)" | sort | uniq -c | sed 's/^/      /'
  N=$((N+MIXN))
else
  echo "    지적 없음"
fi

# ── 6. 메타 줄
echo "[6] 메타 줄 (신선도 계산의 전제)"
MT=$(parse meta | count)
echo "    개념 ${CN}개 중 메타 줄 ${MT}개"
[ "$MT" -lt "$CN" ] && N=$((N+1))

echo
echo "지적 총 ${N}건"
[ "$N" -gt 0 ] && exit 1 || exit 0
