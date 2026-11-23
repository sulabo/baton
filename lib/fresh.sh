#!/usr/bin/env bash
# 모드 ④ 신선도 점검. 메타 줄을 읽어 개념별로 재확인 대상인지 계산한다.
#   fresh.sh <CONCEPTS.md 경로> [저장소 루트]
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
open_concepts "${1:-}" "fresh.sh" "[저장소 루트]" "[repo root]"
[ -n "${2:-}" ] && ROOT="$2"

count() { grep -c . || true; }

# ── 메시지(L은 open_concepts가 정한다). 판정 이름은 lib/test_fresh.py VerdictDocsTest가 이 두 묶음에서 읽어
# 문서의 판정 표와 대조한다. N_* 는 수가 든 조각의 printf 형식이고, 영어는 '단수|복수'다(fmt)
if [ "$L" = ko ]; then
  V_RC="재확인 필요"; V_FRESH="신선"; V_RULE="규칙 개념"; V_TRACK="규칙 개념 — 결정 변동으로만 추적"
  V_NOBASE="기준 없음"; V_LOST="기준 소실"; V_OUTSIDE="기준이 현재 이력 밖"
  V_UNTR="미추적"; V_GONE="경로 소실"; V_DOCS_UNSEEN="문서 못 봄"
  N_COMMIT="커밋 %s건"; N_DOCC="문서 커밋 %s건"; N_GONE="경로 소실 %s개"; N_DOCGONE="문서 경로 소실 %s개"
  N_UNTR="미추적 %s개 제외"; N_DOCUNTR="문서 미추적 %s개 제외"
  PT_FULL="확인 이후 새 결정이 '관련'으로 가리킴"; PT_SHORT="새 결정이 '관련'으로 가리킴"
else
  V_RC="needs a re-check"; V_FRESH="fresh"; V_RULE="rule concept"; V_TRACK="rule concept — tracked only through decision changes"
  V_NOBASE="no baseline"; V_LOST="baseline lost"; V_OUTSIDE="baseline outside the current history"
  V_UNTR="not tracked"; V_GONE="path gone"; V_DOCS_UNSEEN="docs not checked"
  N_COMMIT="%s commit|%s commits"; N_DOCC="%s doc commit|%s doc commits"; N_GONE="%s path gone|%s paths gone"
  N_DOCGONE="%s doc path gone|%s doc paths gone"
  N_UNTR="%s untracked file excluded|%s untracked files excluded"; N_DOCUNTR="%s untracked doc excluded|%s untracked docs excluded"
  PT_FULL="a decision added since the check points to it (Related)"; PT_SHORT="a new decision points to it (Related)"
fi
fmt() {                     # fmt <변수> <형식> <수> — 형식이 '단수|복수'면 수가 1일 때 앞쪽
  local f="$2"
  case "$f" in *"|"*) if [ "$3" -eq 1 ]; then f=${f%%|*}; else f=${f#*|}; fi;; esac
  # shellcheck disable=SC2059
  printf -v "$1" "$f" "$3"
}
# 표. 한국어는 예전 그대로 고정 폭(바이트 기준). 영어는 칸 폭 = 그 칸에서 가장 긴 글 + 2 (docs/GUIDE.md 예시와 같은 모양)
# ponytail: 폭은 글자 수로 센다 — 한글 같은 전각 글자는 화면에서 두 칸이라 영어 표에 한국어 이름이 섞이면 줄이 어긋난다.
#   맞추려면 concepts.py가 unicodedata.east_asian_width로 화면 폭을 내 주게 한다
if [ "$L" = ko ]; then
  row() { printf "%-4s %-22s %-12s %s\n" "$1" "$2" "$3" "$4"; }
else
  WN=7; WS=6                # 'Concept'·'Status'
  row() { printf "%-4s %s%*s %s%*s %s\n" "$1" "$2" $((WN-${#2})) "" "$3" $((WS-${#3})) "" "$4"; }
fi

# 그 개념의 확인 해시 이후 DECISIONS.md에 새로 들어온 '관련' 줄이 이 개념을 가리켰는가 (로드맵 7단계)
POINT_CACHE=$(mktemp -d "${TMPDIR:-/tmp}/baton-fresh.XXXXXX"); trap 'rm -rf "$POINT_CACHE"' EXIT
say() {                     # row와 같되, 가리킴(PT)이면 판정을 재확인으로 올리고 원래 판정을 뒤에 남긴다
  local v="$4"
  if [ -n "${PT:-}" ]; then
    case "$v" in
      "$V_FRESH"*) v="$V_RC — ${PT_FULL}${v#"$V_FRESH"}";;
      "$V_RULE"*)  v="$V_RC — ${PT_FULL} ($V_RULE)";;
      *)           v="$v · ${PT_SHORT}";;
    esac
  fi
  case "$v" in              # 맨 끝 요약 줄용. drift-notice.sh가 표의 글자를 세지 않고 이 줄을 읽는다(개념 이름에 '신선'이 들어가도 안 틀리게)
    "$V_RC"*)    N_STALE=$((N_STALE+1));;
    "$V_FRESH"*) N_FRESH=$((N_FRESH+1));;
    *)           N_RULE=$((N_RULE+1));;
  esac
  row "$1" "$2" "$3" "$v"
}
N_STALE=0; N_FRESH=0; N_RULE=0
# 경로 목록(`a`,`b c`, `d/*.md`)을 배열 P로 나눈다. 쉼표로만 나누므로 공백이 든 경로가 쪼개지지 않고,
# 셸 글롭으로 펼치지 않는다 — 글롭은 그대로 git pathspec으로 넘겨 저장소 루트 기준으로 맞춘다(PR #11 리뷰)
paths_of() {                # $1=목록
  P=()
  local part parts=()
  IFS=, read -ra parts <<< "$1"
  for part in ${parts[@]+"${parts[@]}"}; do
    part=${part//\`/}
    part="${part#"${part%%[![:space:]]*}"}"; part="${part%"${part##*[![:space:]]}"}"
    [ -n "$part" ] && P+=("$part")
  done
  return 0
}
# P를 추적됨(OK)·미추적 수(NU)·사라진 경로(GONE)로 나눈다. 사라진 경로도 git log 대상에 넣는다 —
# 이름을 바꾸거나 지운 커밋이 그 경로의 마지막 커밋으로 잡힌다
classify() {
  OK=(); GONE=(); NU=0
  local f
  for f in ${P[@]+"${P[@]}"}; do
    if tracked "$f"; then OK+=("$f")
    elif [ -e "$ROOT/$f" ]; then NU=$((NU+1))
    else GONE+=("$f"); fi
  done
  return 0
}
commits_since() {           # $1=해시, 나머지=경로들. 경로가 없으면 0
  local h="$1"; shift
  [ "$#" -gt 0 ] || { echo 0; return 0; }
  git -C "$ROOT" log --oneline "$h"..HEAD -- "$@" 2>/dev/null | count
}
# 메타 줄의 '문서' 항목(설명된 곳). 확인 해시 이후 그 파일들의 커밋 수를 DN에, 사라진 문서 경로 수를 DG에,
# 못 본 경로 설명을 DX에 남긴다. 2026-11-21 baton: README를 통째로 다시 쓴 뒤에도 이 항목을 안 읽어 12개 모두 '신선'이 나왔다
docs_moved() {              # $1=해시  $2=문서 목록
  DN=0; DG=0; DX=""
  paths_of "$2"; classify
  DN=$(commits_since "$1" ${OK[@]+"${OK[@]}"} ${GONE[@]+"${GONE[@]}"})
  DG=${#GONE[@]}
  local t
  [ "$NU" -gt 0 ] && { fmt t "$N_DOCUNTR" "$NU"; DX=" ($t)"; }
  [ "$DG" -gt 0 ] && { fmt t "$N_DOCGONE" "$DG"; DX="$DX ($t)"; }
  return 0
}
pointed() {                 # $1=개념 번호  $2=해시
  tracked DECISIONS.md || return 1
  local c="$POINT_CACHE/$2"
  if [ ! -f "$c" ]; then
    # 파서가 실패하면 빈 결과가 "가리킴 없음"처럼 보인다 — 실패 표지를 남겨 아래에서 못 셌다고 알린다
    git -C "$ROOT" diff "$2"..HEAD -- DECISIONS.md 2>/dev/null | parse related > "$c" 2>/dev/null \
      || { if [ "$L" = ko ]; then printf '?\t(파서 실패: 확인 %s 이후 결정)\n' "$2"
           else printf '?\t(parser failed: decisions after check %s)\n' "$2"; fi; } > "$c"
  fi
  grep -qx "$1" "$c"
}

META=$(parse meta)
NMETA=$(echo "$META" | count)
NCONC=$(parse sections | count)

if [ "$NMETA" -eq 0 ]; then
  if [ "$L" = ko ]; then cat <<MSG
메타 줄이 하나도 없다 (개념 ${NCONC}개). **신선도를 계산할 수 없다 — 0건이 아니라 못 셌다.**

먼저 개념마다 제목 아래에 이 줄을 넣는다:
  - **메타**: 상태=… · 확인=YYYY-MM-DD(\`해시\`) · 파일=\`루트상대경로\` · 이웃=…

해시를 모르면 확인=YYYY-MM-DD(해시 미상)으로 두고 나중에 채운다.
파일이 없는 규칙 개념이면 파일=없음(규칙 개념).
MSG
  else cat <<MSG
No metadata lines at all (concepts: ${NCONC}). **Freshness can't be computed — this is not 0, it could not be counted.**

First add this line under each concept's heading:
  - **Meta**: status=… · checked=YYYY-MM-DD(\`hash\`) · files=\`path from the repo root\` · neighbors=…

If you don't know the hash, write checked=YYYY-MM-DD(hash unknown) and fill it in later.
For a rule concept with no files, write files=none(rule concept).
A Korean map uses the same line with Korean keys: - **메타**: 상태=… · 확인=… · 파일=… · 이웃=…
MSG
  fi
  exit 2
fi
if [ "$NMETA" -lt "$NCONC" ]; then
  if [ "$L" = ko ]; then echo "주의: 개념 ${NCONC}개 중 메타 줄 ${NMETA}개. 나머지는 표에 안 나온다."
  else echo "Warning: only ${NMETA} of ${NCONC} concepts have a metadata line. The rest are not in the table."; fi
  echo
fi
# 파서가 조용히 못 읽은 부분(열린 채 끝난 코드 펜스 등). 이게 있으면 표에 없는 개념이 있을 수 있다 — 0건이 아니라 못 셌다
WARN=$(parse warnings)
if [ -n "$WARN" ]; then
  if [ "$L" = ko ]; then echo "$WARN" | sed 's/^/주의: /'; else echo "$WARN" | sed 's/^/Warning: /'; fi
  echo
fi

if [ "$L" = ko ]; then
  row "#" "개념" "상태" "판정"
  printf -- "---- ---------------------- ------------ ------------------------------\n"
else
  while IFS=$'\t' read -r _num name state _rest; do
    [ "${#name}" -gt "$WN" ] && WN=${#name}
    [ "${#state}" -gt "$WS" ] && WS=${#state}
  done <<< "$META"
  WN=$((WN+2)); WS=$((WS+2))
  row "#" "Concept" "Status" "Verdict"
  printf -- "---- %s %s %s\n" "$(printf '%*s' "$WN" '' | tr ' ' -)" "$(printf '%*s' "$WS" '' | tr ' ' -)" \
    "------------------------------"
fi

while IFS=$'\t' read -r num name state _date hash files _neighbors docs; do
  [ -z "$num" ] && continue

  [ "$hash" = "-" ] && hash=""
  [ "$files" = "-" ] && files=""
  [ "${docs:-}" = "-" ] && docs=""

  PT=""; DN=0; DG=0; DX=""; BASE=""   # BASE: 해시를 쓸 수 있는가 — 없음/소실/이력 밖이면 그 이유
  if [ -z "$hash" ]; then BASE="$V_NOBASE"
  elif ! git -C "$ROOT" cat-file -e "$hash" 2>/dev/null; then BASE="$V_LOST"
  elif ! git -C "$ROOT" merge-base --is-ancestor "$hash" HEAD 2>/dev/null; then BASE="$V_OUTSIDE"
  fi
  if [ -z "$BASE" ]; then
    pointed "$num" "$hash" && PT=1
    [ -n "$docs" ] && docs_moved "$hash" "$docs"
  fi
  fmt DCT "$N_DOCC" "$DN"; fmt DGT "$N_DOCGONE" "$DG"
  case "$files" in *없음*|[Nn]one|[Nn]one[\ \(]*)   # 규칙 개념: 파일=없음(규칙 개념) · files=none(rule concept)
    if [ "$DN" -gt 0 ]; then say "$num" "$name" "$state" "$V_RC — $DCT ($V_RULE)${DX}"
    elif [ "$DG" -gt 0 ]; then say "$num" "$name" "$state" "$V_RC — $DGT ($V_RULE)"
    elif [ "$BASE" = "$V_LOST" ] || [ "$BASE" = "$V_OUTSIDE" ]; then
      # 적어 둔 해시를 쓸 수 없으면 결정 변동('관련' 가리킴)도 셀 수 없다 — 규칙 개념이라도 재확인으로 올려 알림이 울리게 한다
      say "$num" "$name" "$state" "$V_RC — ${BASE} ($V_RULE${docs:+ — $V_DOCS_UNSEEN})"
    elif [ -n "$BASE" ] && [ -n "$docs" ]; then say "$num" "$name" "$state" "$V_TRACK (${BASE} — $V_DOCS_UNSEEN)"
    else say "$num" "$name" "$state" "$V_TRACK${DX}"; fi
    continue;; esac
  if [ -n "$BASE" ]; then
    say "$num" "$name" "$state" "$V_RC — ${BASE}"; continue
  fi

  # 추적되는 파일로 계산하고, 미추적은 따로 센다. 사라진 경로도 log에 넣는다
  paths_of "$files"; classify
  untracked=$NU; gone=${#GONE[@]}

  if [ "${#OK[@]}" -eq 0 ] && [ "$gone" -eq 0 ]; then
    if [ "$untracked" -gt 0 ]; then say "$num" "$name" "$state" "$V_RC — $V_UNTR"
    else say "$num" "$name" "$state" "$V_RC — $V_GONE"; fi
    continue
  fi

  extra=""
  [ "$untracked" -gt 0 ] && { fmt t "$N_UNTR" "$untracked"; extra=" ($t)"; }
  n=$(commits_since "$hash" ${OK[@]+"${OK[@]}"} ${GONE[@]+"${GONE[@]}"})
  fmt CT "$N_COMMIT" "$n"; fmt GT "$N_GONE" "$gone"
  dpart=""; [ "$DN" -gt 0 ] && dpart=" · $DCT"
  # 사라진 경로는 코드든 문서든 그 자체가 어긋남이다 — 신선으로 두지 않는다
  if [ "$n" -gt 0 ]; then
    [ "$gone" -gt 0 ] && extra="$extra ($GT)"
    say "$num" "$name" "$state" "$V_RC — $CT${dpart}${extra}${DX}"
  elif [ "$gone" -gt 0 ]; then
    say "$num" "$name" "$state" "$V_RC — $GT${dpart}${extra}${DX}"
  elif [ "$DN" -gt 0 ]; then
    say "$num" "$name" "$state" "$V_RC — $DCT${extra}${DX}"
  elif [ "$DG" -gt 0 ]; then
    say "$num" "$name" "$state" "$V_RC — $DGT${extra}"
  else
    say "$num" "$name" "$state" "$V_FRESH${extra}${DX}"
  fi
done <<< "$META"
echo
# 이 줄의 모양은 hooks/drift-notice.sh가 읽는다(두 언어 다)
if [ "$L" = ko ]; then echo "요약: 재확인 ${N_STALE} · 신선 ${N_FRESH} · 규칙 개념 ${N_RULE}"
else echo "Summary: re-check ${N_STALE} · fresh ${N_FRESH} · rule concepts ${N_RULE}"; fi

UNK=$(cat "$POINT_CACHE"/* 2>/dev/null | grep '^?' | cut -f2 | sort -u)
if [ -n "$UNK" ]; then
  echo
  if [ "$L" = ko ]; then echo "새 결정의 '관련' 중 개념 절과 못 이은 것(이름 불일치·절 없는 번호·파서 실패) — **0건이 아니라 못 셌다**:"
  else echo "Related entries in new decisions that match no concept section (name mismatch, number with no section, parser failure) — **this is not 0, they could not be counted**:"; fi
  echo "$UNK" | sed 's/^/     /'
fi

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
if [ "$L" = ko ]; then echo "결정·지침 변동: 가장 오래된 확인($OLDEST) 이후 커밋 ${DC}건"
else fmt t "$N_COMMIT" "$DC"; echo "Decision and instruction changes: $t since the oldest check ($OLDEST)"; fi
[ "$DC" -eq 0 ] && exit 0
[ -f "$ROOT/DECISIONS.md" ] || exit 0

D=$(git -C "$ROOT" diff "$OLDEST"..HEAD -- DECISIONS.md 2>/dev/null)
HEADN=$(grep -c '^## [0-9]\{4\}-' "$ROOT/DECISIONS.md" 2>/dev/null | tr -cd '0-9')
TABN=$(grep -cE '^\| *[A-Z]+[0-9]+ *\|' "$ROOT/DECISIONS.md" 2>/dev/null | tr -cd '0-9')

if [ "${HEADN:-0}" -ge "${TABN:-0}" ] && [ "${HEADN:-0}" -gt 0 ]; then
  NEWN=$(echo "$D" | grep -c '^+## [0-9]\{4\}-' | tr -cd '0-9')
  RELN=$(echo "$D" | grep -cE '^\+- (관련|[Rr]elated):' | tr -cd '0-9')   # 영어 결정 기록은 '- Related:'
  if [ "$L" = ko ]; then
    echo "  형식: 날짜 헤딩 · 새 결정 ${NEWN}건 · '관련:' 줄 ${RELN}건 · 구멍 $((NEWN-RELN))건"
    [ "$((NEWN-RELN))" -gt 0 ] && echo "  → 관련 줄 없는 결정은 어느 개념을 건드렸는지 알 수 없다. 갱신 경로의 구멍으로 보고한다."
  else
    echo "  Format: dated headings · new decisions ${NEWN} · Related: lines ${RELN} · gaps $((NEWN-RELN))"
    [ "$((NEWN-RELN))" -gt 0 ] && echo "  → A decision without a Related: line doesn't say which concepts it touched. Report it as a gap in the update path."
  fi
elif [ "${TABN:-0}" -gt 0 ]; then
  IDS=$(echo "$D" | grep -oE '^\+\| *[A-Z]+[0-9]+ *\|' | grep -oE '[A-Z]+[0-9]+' | tr '\n' ' ')
  if [ "$L" = ko ]; then
    echo "  형식: 표(결정 ID) · 새 결정 행 $(echo "$IDS" | wc -w | tr -d ' ')건${IDS:+  — $IDS}"
    echo "  → 이 형식에는 '관련:' 줄 관행이 없다. 어느 개념이 걸리는지는 ID를 개념 절에서 찾아 잇는다."
  else
    echo "  Format: table (decision IDs) · new decision rows $(echo "$IDS" | wc -w | tr -d ' ')${IDS:+  — $IDS}"
    echo "  → This format has no Related: lines. To see which concept a decision touches, find its ID in the concept sections."
  fi
  for i in $IDS; do
    grep -q "$i" "$F" && continue
    if [ "$L" = ko ]; then echo "     $i: 개념 지도에 언급 없음 — 어느 개념에 걸리는지 확인 필요"
    else echo "     $i: not mentioned in the concept map — check which concept it touches"; fi
  done
elif [ "$L" = ko ]; then
  echo "  형식 불명 — **0건이 아니라 못 셌다.** DECISIONS.md를 직접 열어 확인한다."
else
  echo "  Unknown format — **this is not 0, it could not be counted.** Open DECISIONS.md and check it directly."
fi
git -C "$ROOT" log --oneline "$OLDEST"..HEAD -- $GOV 2>/dev/null | head -4 | sed 's/^/     /'

# ── 파일 항목에 지침·결정 파일이 섞여 있는가
MIX=$(echo "$META" | cut -f6 | grep -cE 'AGENTS\.md|DECISIONS\.md|CLAUDE\.md|TODO\.md' | tr -cd '0-9')
if [ "${MIX:-0}" -gt 0 ]; then
  if [ "$L" = ko ]; then cat <<MSG

경고: 개념 ${MIX}개의 '파일' 항목에 지침·결정 파일이 섞여 있다.
  그 파일들은 거의 매일 바뀌어서 실제 내용이 가만히 있어도 재확인 대상이 된다.
  '파일'에는 실제 동작 근거(코드·산출물)만 남기고, 결정 변동은 위 전역 검사로 본다.
MSG
  else cat <<MSG

Warning: instruction or decision files are listed in files= (concepts: ${MIX}).
  Those files change almost daily, so the concept needs a re-check even when nothing it describes changed.
  Keep only evidence of actual behavior (code, outputs) in files=. Decision changes are checked above, once for the whole map.
MSG
  fi
fi
