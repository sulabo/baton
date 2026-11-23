#!/usr/bin/env bash
# CONCEPTS.md 기계 검사. 사람 판단이 필요 없는 것만 본다.
#   check.sh <CONCEPTS.md 경로>
# 종료코드: 0 = 지적 없음, 1 = 지적 있음, 2 = 못 돌림
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
open_concepts "${1:-}" "check.sh"

N=0
count() { grep -c . || true; }          # 빈 입력에서도 0을 낸다
ko() { [ "$L" = ko ]; }                 # 메시지 언어(open_concepts가 정한 L)

if ko; then
  echo "검사 대상: $(basename "$DIR")/$(basename "$F")"
  echo "저장소 루트: $(basename "$ROOT")"
else
  echo "Checking: $(basename "$DIR")/$(basename "$F")"
  echo "Repo root: $(basename "$ROOT")"
fi
echo

BODY=$(parse sections | cut -f1 | sort -n)
CN=$(echo "$BODY" | count)

# ── 1. 요약표 행 ↔ 본문 절
# 'echo … | grep -q'는 pipefail 아래에서 grep이 먼저 끝나면 echo가 SIGPIPE로 실패해 "없음"으로 읽힌다(부하가 있을 때 가끔) —
# 그래서 here-string으로 넘긴다
if ko; then echo "[1] 요약표와 본문 절이 일대일인가"; else echo "[1] Summary table rows and concept sections match one to one"; fi
TBL=$(parse table | cut -f1 | sort -n | uniq)
if [ -z "$TBL" ]; then
  ROWS=$(parse rows)
  if ko; then echo "    번호 열 없는 표 — 행 수로만 대조: 표 ${ROWS}행 vs 본문 ${CN}절"
  else echo "    The table has no number column — comparing row counts only: table rows ${ROWS} vs sections ${CN}"; fi
  if [ "$ROWS" -ne "$CN" ]; then
    if ko; then echo "    행 수 불일치 (이름으로 직접 대조 필요)"; else echo "    Row counts differ (compare the names by hand)"; fi
    N=$((N+1))
  fi
else
  for n in $TBL;  do grep -qx "$n" <<< "$BODY" || {
    if ko; then echo "    표에만 있고 본문 절 없음: 개념 $n"; else echo "    In the table but has no section: concept $n"; fi; N=$((N+1)); }; done
  for n in $BODY; do grep -qx "$n" <<< "$TBL" || {
    if ko; then echo "    본문에만 있고 표에 없음: 개념 $n"; else echo "    Has a section but is not in the table: concept $n"; fi; N=$((N+1)); }; done
fi

# ── 2. 근거 경로가 신선도 계산에 쓸 수 있는 형태인가
if ko; then echo "[2] 근거 경로가 신선도 계산에 쓸 수 있는가"; else echo "[2] Evidence paths can be used to compute freshness"; fi
BAD=""; TOT=0
while IFS= read -r p; do
  [ -z "$p" ] && continue
  TOT=$((TOT+1))
  msg=$(diagnose_path "$p") || BAD="${BAD}${msg}"$'\n'
done <<< "$(parse evidence)"
if [ -n "$BAD" ]; then
  BC=$(printf '%s' "$BAD" | count)
  printf '%s' "$BAD" | sort
  if ko; then echo "    → 근거 ${TOT}개 중 ${BC}개가 그대로는 신선도 계산 불가"
  else echo "    → ${BC} of ${TOT} evidence paths can't be used to compute freshness as written"; fi
  N=$((N+BC))
elif ko; then
  echo "    지적 없음 (${TOT}개 전부 루트 상대로 추적됨)"
else
  echo "    No findings (evidence paths: ${TOT}, all tracked relative to the repo root)"
fi

# ── 3. 개념 간 참조가 양방향인가
if ko; then echo "[3] 개념 사이 참조가 양방향인가"; else echo "[3] References between concepts go both ways"; fi
REFS=$(parse refs)
ONE=$(echo "$REFS" | while IFS=$'\t' read -r a b; do
  [ -z "$a" ] && continue
  grep -qx "$b	$a" <<< "$REFS" && continue
  if ko; then echo "    한쪽만: 개념 $a 가 개념 $b 를 가리키는데 그쪽에 역참조 없음"
  else echo "    One way only: concept $a points to concept $b, but $b does not point back"; fi
done)
OC=$(echo "$ONE" | count)
[ "$OC" -gt 0 ] && echo "$ONE"
if ko; then echo "    참조 $(echo "$REFS" | count)건 · 한쪽만 ${OC}건"
else echo "    References: $(echo "$REFS" | count) · one way only: ${OC}"; fi
N=$((N+OC))

# ── 4. 상태 어휘 (상태를 적는 자리만 본다. 본문 산문은 보지 않는다)
# 한국어 어휘와 영어 어휘(영어 지도) 둘 다 닫힌 집합이다 — 메시지 언어와 상관없이 둘 다 받는다. 영어는 대소문자 무시
if ko; then echo "[4] 닫힌 상태 어휘 밖의 말을 쓰는가"; else echo "[4] Status words outside the closed list"; fi
STATES=$(parse states)
OUT=0
for st in $(echo "$STATES" | tr ' ' '\v'); do
  s=$(echo "$st" | tr '\v' ' ')
  case "$s" in
    일치|미구현|"낡은 문서"|미결|"중복 정본"|"확인 못 함") continue ;;
    해소됨*|폐기됨*|없음*|규칙*) continue ;;
  esac
  case "$(echo "$s" | tr '[:upper:]' '[:lower:]')" in
    agrees|"not built yet"|"stale doc"|undecided|"two sources of truth"|"could not check") ;;
    resolved*|retired*|none*|rule*) ;;
    *) if ko; then echo "    닫힌 어휘 밖: '$s'"; else echo "    Not in the closed list: '$s'"; fi; OUT=$((OUT+1)) ;;
  esac
done
if [ "$OUT" -eq 0 ]; then
  if ko; then echo "    지적 없음 ($(echo "$STATES" | count)종 확인)"
  else echo "    No findings (distinct values checked: $(echo "$STATES" | count))"; fi
else
  N=$((N+OUT))
fi

# ── 5. '파일' 항목이 실제 동작 근거만 담고 있는가
if ko; then echo "[5] '파일' 항목이 실제 동작 근거만 담고 있는가"; else echo "[5] The files= entry lists only evidence of actual behavior"; fi
GOV='AGENTS\.md|DECISIONS\.md|CLAUDE\.md|TODO\.md'
MIXED=$(parse meta | cut -f6 | grep -E "$GOV" || true)
MIXN=$(echo "$MIXED" | count)
if [ "$MIXN" -gt 0 ]; then
  if ko; then echo "    지침·결정 파일이 섞인 개념 ${MIXN}개 — 신선도 신호가 망가진다"
  else echo "    Concepts that list instruction or decision files: ${MIXN} — this breaks the freshness signal"; fi
  echo "$MIXED" | grep -oE "[^,\`]*($GOV)" | sort | uniq -c | sed 's/^/      /'
  N=$((N+MIXN))
elif ko; then
  echo "    지적 없음"
else
  echo "    No findings"
fi

# ── 6. 메타 줄
if ko; then echo "[6] 메타 줄 (신선도 계산의 전제)"; else echo "[6] Metadata lines (needed to compute freshness)"; fi
MT=$(parse meta | count)
if ko; then echo "    개념 ${CN}개 중 메타 줄 ${MT}개"; else echo "    Concepts: ${CN} · metadata lines: ${MT}"; fi
[ "$MT" -lt "$CN" ] && N=$((N+1))

# ── 7. 파서가 못 읽은 부분
if ko; then echo "[7] 파서가 끝까지 읽었는가 (열린 채 끝난 코드 펜스)"; else echo "[7] The parser read to the end (no code fence left open)"; fi
WARN=$(parse warnings)
if [ -n "$WARN" ]; then
  echo "$WARN" | sed 's/^/    /'
  N=$((N+$(echo "$WARN" | count)))
elif ko; then
  echo "    지적 없음"
else
  echo "    No findings"
fi

echo
if ko; then echo "지적 총 ${N}건"; else echo "Total findings: ${N}"; fi
[ "$N" -gt 0 ] && exit 1 || exit 0
