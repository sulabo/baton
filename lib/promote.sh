#!/usr/bin/env bash
# 승격 검토. HANDOFF.md 과거 판에서 DECISIONS.md로 올릴 것을 뽑는다.
#   promote.sh [--brief] [저장소 경로] [판수(기본 8)]
#   --brief: 8줄 안의 요약만(중요한 것 먼저, 후보가 없으면 그렇다고 한 줄). 인계서를 쓸 때 스킬이 이것을 부른다 —
#     전체 출력을 tail·head로 자르면 머리 줄·못 센 판 줄이 잘려 다시 부르게 된다(2026-11-24 실험 2차, game 저장소 5번 중 4번)
# 종료코드: 0 = 돌았음, 2 = 못 돌림
set -uo pipefail

BRIEF=0; ARGS=()
for a in "$@"; do   # --brief는 어느 자리에 와도 된다
  if [ "$a" = --brief ]; then BRIEF=1; else ARGS+=("$a"); fi
done
R="${ARGS[0]:-.}"
K="${ARGS[1]:-8}"
THRESHOLD=3          # 서로 다른 N일 이상 살아남으면 승격 후보
WIDTH=55             # 문구가 조금씩 다듬어진 같은 항목을 묶기 위한 절단 폭

die() { printf '%s\n' "$@"; exit 2; }

# 메시지 언어(ko/en, lib/i18n.py) — 한 번만 정한다. 인계서 절 제목은 언어와 무관하게 한국어·영어 둘 다 읽는다.
# python3이 없거나 실패하면 셸에서 같은 순서로 본다: BATON_LANG 환경변수(ko/en) > LC_ALL·LC_MESSAGES·LANG 중 처음 비지 않은 값.
# 로캘이 "ko" 뒤에 끝·_·.·@·- 가 오면 한국어("kok" 같은 다른 언어는 아니다). 설정 파일의 BATON_LANG은 python 없이는 못 읽는다.
# 이 스크립트는 그 밖에는 python이 필요 없어서다(main은 python 없이 한국어로 돌았다 — 리뷰 11-23)
UI=$(python3 "$(dirname "${BASH_SOURCE[0]}")/i18n.py" "$R" 2>/dev/null) || UI=""
if [ "$UI" != ko ] && [ "$UI" != en ]; then
  case "$(printf '%s' "${BATON_LANG:-}" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')" in
    ko) UI=ko ;;
    en) UI=en ;;
    *) case "$(printf '%s' "${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}" | tr '[:upper:]' '[:lower:]')" in
         ko|ko_*|ko.*|ko@*|ko-*) UI=ko ;;
         *) UI=en ;;
       esac ;;
  esac
fi
t() { if [ "$UI" = ko ]; then printf '%s' "$1"; else printf '%s' "$2"; fi; }   # $1=한국어 $2=영어

case "$K" in   # 판수는 1 이상 정수 — 아니면 head가 오류를 내고 0건처럼 보인다
  ''|*[!0-9]*|0|0*) die "$(t "판수는 1 이상 정수여야 한다: $K" "The number of versions must be a whole number of 1 or more: $K")" \
                        "$(t "사용법: promote.sh [--brief] <저장소 경로> [판수]" "Usage: promote.sh [--brief] <repo path> [versions (default 8)]")" ;;
esac

git -C "$R" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  || die "$(t "git 저장소가 아니다: $R" "Not a git repository: $R")" \
         "$(t "사용법: promote.sh [--brief] <저장소 경로> [판수]" "Usage: promote.sh [--brief] <repo path> [versions (default 8)]")"

[ -f "$R/HANDOFF.md" ] || die \
  "$(t "HANDOFF.md가 없다: $R" "No HANDOFF.md: $R")" \
  "$(t "승격 검토는 과거 판을 보는 일이라 인계서가 먼저 있어야 한다." "The promotion review reads past versions of the handoff, so one has to exist first.")" \
  "$(t "이번이 처음이면 인계서부터 쓰고, 다음 번에 이 검토를 돌린다." "If this is the first time, write a handoff now and run this review next time.")"

git -C "$R" ls-files --error-unmatch HANDOFF.md >/dev/null 2>&1 || die \
  "$(t "HANDOFF.md는 있는데 git이 추적하지 않는다. 승격 검토 불가 — 과거 판을 못 본다." \
       "HANDOFF.md exists but git does not track it. No promotion review — past versions cannot be read.")" \
  "$(t "먼저: git -C \"$R\" add HANDOFF.md && git -C \"$R\" commit -m 'chore: 인계서 추적 시작'" \
       "First: git -C \"$R\" add HANDOFF.md && git -C \"$R\" commit -m 'chore: start tracking the handoff'")"

count() { grep -c . || true; }
# 자리표시 항목("- 없음"·"- None"·"- -"·빈 "- ")은 항목이 아니다 — 반복 실패·탈락·기각 목록 어디에도 세지 않는다.
# 판에서 절을 찾았는지(형식 불일치 판정)는 거르기 전 내용으로 본다 — "- 없음"만 있는 절도 절은 있는 것이다
real() { grep -Ev '^- *(\*\*)?(없음|[Nn]one|N/A|-)?(\*\*)?[.。]? *$' || true; }

# 한 판에서 절 하나를 뽑는다. 절 제목은 저장소마다 다르므로 앞머리만 맞춘다.
#   `## E. 실패한 접근법` 처럼 절 기호가 붙어도 잡힌다. 표제는 확장 정규식 — 한국어|영어 템플릿을 둘 다 받는다.
#   확인 표시 [V]·[?]는 떼고 비교한다 — [?]가 [V]로 바뀐 같은 사실을 탈락으로 세지 않으려고.
section() {   # $1=커밋 $2=시작 표제 $3=끝 표제
  git -C "$R" show "$1:HANDOFF.md" 2>/dev/null \
    | sed -En "/^#.*($2)/,/^#.*($3)/p" | grep '^- ' | sed 's/^- \[[V?]\] /- /' | cut -c1-"$WIDTH"
}
FAILED="실패한 접근법|[Ff]ailed approach"; AFTER_FAILED="검증|[Vv]erification"
FACTS="확인된 사실과 결정|[Vv]erified facts"; AFTER_FACTS="관련 파일|[Ff]iles and symbols|[Rr]elated files"

# 같은 날 여러 번 커밋하면 절이 통째로 복붙돼 가짜 반복이 된다. 날짜당 최신 한 판만 쓴다.
DAYS=$(git -C "$R" log --format="%ad %h" --date=short -- HANDOFF.md 2>/dev/null \
         | awk '!seen[$1]++{print $2}' | head -"$K")
NDAY=$(echo "$DAYS" | count)
NCOMMIT=$(git -C "$R" log --format=%h -- HANDOFF.md 2>/dev/null | head -"$K" | count)
# 스테이징만 하고 커밋하지 않은 인계서(첫 커밋 전 저장소 포함): 볼 판이 없다 — 0건이 아니라 못 셈(git의 fatal 줄은 숨긴다)
[ "$NDAY" -gt 0 ] || die "$(t "HANDOFF.md의 커밋된 판이 없어 못 셈 — 0건이 아니라 못 셈. 커밋한 뒤에 이 검토가 돈다." \
                           "HANDOFF.md has no committed version, so nothing could be counted (not 0: uncounted). The review works once it is committed.")"
# --brief면 아래 전체 출력은 버리고 맨 끝에서 요약만 낸다(셈은 같은 코드 그대로). 못 돌릴 때의 안내(위)는 그대로 나간다
[ "$BRIEF" = 1 ] && exec 3>&1 1>/dev/null
t "저장소: $(basename "$R")  ·  검토 ${NDAY}일 (커밋 수로는 ${NCOMMIT}판이지만 날짜당 1판만 센다)" \
  "Repo: $(basename "$R")  ·  reviewed ${NDAY} days (${NCOMMIT} versions by commit, but only one per day is counted)"; echo

# ── A. 반복 실패 — 서로 다른 N일 이상 살아남은 제약
FAILS=""; MISS=0
for sha in $DAYS; do
  body=$(section "$sha" "$FAILED" "$AFTER_FAILED")
  if [ -z "$body" ]; then MISS=$((MISS+1)); else FAILS="${FAILS}${body}"$'\n'; fi
done
echo
t "[A] 반복 실패 — 서로 다른 ${THRESHOLD}일 이상 살아남은 제약" \
  "[A] Repeated failures — constraints that survived on ${THRESHOLD} or more different days"; echo
[ "$MISS" -gt 0 ] && { t "    형식 불일치로 못 센 판 ${MISS}개 (분모는 $((NDAY-MISS))일)" \
                         "    ${MISS} versions could not be counted (format mismatch; denominator $((NDAY-MISS)) days)"; echo; }
REPEATED=$(printf '%s' "$FAILS" | real | sort | uniq -c | sort -rn | awk -v t="$THRESHOLD" '$1>=t')
echo "$REPEATED" | awk -v u="$(t "일:" "days:")" 'NF{$1=$1" "u; print "    "$0}' | head -12
N=$(echo "$REPEATED" | count); t "    → ${N}건" "    → ${N} found"; echo

# ── B. 탈락 — 앞선 판에 2일 이상 있던 상시 제약이 최신판에서 사라짐
echo
t "[B] 탈락 — 상시 제약이 최신판에서 조용히 빠짐" "[B] Dropped — standing constraints that quietly left the latest version"; echo
LATEST=$(echo "$DAYS" | head -1)
NOW=$(section "$LATEST" "$FACTS" "$AFTER_FACTS" | sort -u)
DROPPED=""; MARKED=""; BMISS=0
if [ -z "$NOW" ]; then
  t "    최신판에 '확인된 사실과 결정' 절이 없다 — 이 신호는 못 센다 (0건이 아니라 못 셈)" \
    "    The latest version has no 'Verified facts and decisions' section — this signal cannot be counted (not 0: uncounted)"; echo
else
  PAST_RAW=""; BMISS=0
  for sha in $(echo "$DAYS" | tail -n +2); do
    body=$(section "$sha" "$FACTS" "$AFTER_FACTS")
    if [ -z "$body" ]; then BMISS=$((BMISS+1)); else PAST_RAW="${PAST_RAW}${body}"$'\n'; fi
  done
  [ "$BMISS" -gt 0 ] && { t "    절 구조가 다른 판 ${BMISS}개는 못 셌다 (분모 $((NDAY-1-BMISS))일)" \
                            "    ${BMISS} versions with a different section layout could not be counted (denominator $((NDAY-1-BMISS)) days)"; echo; }

  PAST=$(printf '%s' "$PAST_RAW" | sort | uniq -c \
           | awk '$1>=2{sub(/^ *[0-9]+ /,""); print}' | sort -u)
  DROPPED=$(comm -23 <(printf '%s\n' "$PAST" | real | grep . | sort) <(printf '%s\n' "$NOW" | grep . | sort))

  # 결정 표지가 붙은 것을 위로 — 그쪽이 DECISIONS.md 감이다. 영어 표지는 같은 뜻의 낱말(owner decision·final·forbidden·never·adopted·lifted·canonical)
  MARKED=$(echo "$DROPPED" | grep -E "소유자 결정|확정|금지|절대|채택|해제|정본|[A-Z][0-9]{1,2}\b|\b([Oo]wner decision|[Ff]inal|[Ff]orbidden|[Nn]ever|[Aa]dopted|[Ll]ifted|[Cc]anonical)\b" || true)
  PLAIN=$(comm -23 <(printf '%s\n' "$DROPPED" | grep . | sort) <(printf '%s\n' "$MARKED" | grep . | sort))
  if [ -n "$MARKED" ]; then
    N=$(echo "$MARKED" | count)
    t "    ── 결정 표지가 붙은 것 (${N}건) — 먼저 본다" "    ── With a decision marker (${N}) — look at these first"; echo
    echo "$MARKED" | sed 's/^/      /' | head -10
  fi
  N=$(echo "$PLAIN" | count)
  t "    ── 표지 없는 것 ${N}건 (대개 끝난 작업 메모)" "    ── Without a marker: ${N} (usually notes on finished work)"; echo
  N=$(echo "$DROPPED" | count)
  t "    → 탈락 총 ${N}건. 전부가 승격감은 아니다. 끝난 일인지 살아 있는 제약인지 사람이 가른다" \
    "    → ${N} dropped in total. Not all of them are worth promoting. A person decides which are finished work and which are live constraints"; echo
fi

# ── C. 번복 — 자동 탐지 불가
echo
t "[C] 번복 — 문자열로는 안 잡힌다. 소유자가 알려줄 때만 후보로 올린다." \
  "[C] Reversals — string matching cannot catch them. Raise one only when the owner points it out."; echo
echo
t "기각 목록을 먼저 확인한다: HANDOFF.md 의 '기각됨' 절" "Check the rejected list first: the 'Rejected' section of HANDOFF.md"; echo
REJECTED=$(grep -E -A20 '기각됨|^#+ *[Rr]ejected' "$R/HANDOFF.md" 2>/dev/null | grep '^- ' | real | head -5)
if [ -n "$REJECTED" ]; then echo "$REJECTED" | sed "s/^/    $(t "이미 기각: " "already rejected: ")/"
else t "    (기각 목록 없음)" "    (no rejected list)"; echo; fi

[ "$BRIEF" = 1 ] || exit 0
# ── 요약(--brief): 많아야 8줄. 머리 줄 → 못 센 판 → 후보(반복 실패, 결정 표지 붙은 탈락) → 끝 줄.
# 끝 줄은 " · " 옆에 0이 아닌 수(검토 N일)를 둔다 — 다 셌는데 0인 결과에서 0건 가드(hooks/zero-guard.sh)가 다시 묻지 않게
exec 1>&3 3>&-
NA=$(echo "$REPEATED" | count); NB=$(echo "$DROPPED" | count); NM=$(echo "$MARKED" | count)
NR=$(grep -E -A20 '기각됨|^#+ *[Rr]ejected' "$R/HANDOFF.md" 2>/dev/null | grep '^- ' | real | count)
if [ -n "$NOW" ]; then B=$(t "탈락 ${NB}건(결정 표지 ${NM}건)" "dropped: ${NB} (${NM} with a decision marker)")
else B=$(t "탈락 못 셈" "dropped: not counted"); fi
t "승격 검토(요약) · 검토 ${NDAY}일 · 반복 실패 ${NA}건 · ${B} · 기각 목록 ${NR}개" \
  "Promotion review (brief) · ${NDAY} days reviewed · repeated failures: ${NA} · ${B} · rejected list: ${NR}"; echo
USED=1; GAPS=""
[ "$MISS" -gt 0 ] && GAPS="$(t "반복 실패 형식 불일치 판 ${MISS}개" "repeated failures: ${MISS} versions in another format")"
[ -z "$NOW" ] && GAPS="${GAPS:+$GAPS · }$(t "최신판에 '확인된 사실과 결정' 절 없음" "the latest version has no 'Verified facts and decisions' section")"
[ "$BMISS" -gt 0 ] && GAPS="${GAPS:+$GAPS · }$(t "탈락 절 형식이 다른 판 ${BMISS}개" "dropped: ${BMISS} versions with another section layout")"
if [ -n "$GAPS" ]; then
  t "  못 셈: ${GAPS} — 0건이 아니라 못 셈" "  Not counted: ${GAPS} (not 0: uncounted)"; echo; USED=2
fi
CANDS=$( { echo "$REPEATED" | awk -v u="$(t "일:" " days:")" 'NF{n=$1; $1=""; print "  [A] " n u $0}'
           echo "$MARKED" | awk 'NF{print "  [B] " $0}'; } )
NC=$(echo "$CANDS" | count); ROOM=$((8 - USED))
if [ "$NC" -gt "$ROOM" ]; then
  echo "$CANDS" | head -$((ROOM - 1))
  t "  … 외 $((NC - ROOM + 1))건 — 전체는 --brief 없이 promote.sh" "  … and $((NC - ROOM + 1)) more. Run promote.sh without --brief for all of them"; echo
elif [ "$NC" -gt 0 ]; then
  echo "$CANDS"
elif [ -n "$GAPS" ]; then
  t "  찾은 후보 없음 — 위의 못 센 판 때문에 '없음'이 아니다" "  No candidates found, but because of the versions above that is not 'none'"; echo
elif [ "$NB" -gt 0 ]; then
  t "  올릴 것 없음(결정 표지 붙은 후보 없음) · 표지 없는 탈락 ${NB}건은 대개 끝난 작업 메모 · 검토 ${NDAY}일 모두 셈" \
    "  Nothing to promote (no candidate with a decision marker) · ${NB} dropped without a marker, usually notes on finished work · all ${NDAY} days counted"; echo
elif [ "$NDAY" -lt "$THRESHOLD" ]; then  # 반복 실패는 3일, 탈락은 앞선 2일이 있어야 나온다 — 판이 모자라면 "없음"이라고만 하지 않는다
  t "  올릴 것 없음 · 검토 ${NDAY}일 — ${THRESHOLD}일이 안 돼 후보가 아직 나올 수 없다" \
    "  Nothing to promote · ${NDAY} days reviewed, fewer than ${THRESHOLD}, so no candidate can show up yet"; echo
else
  t "  올릴 것 없음 · 검토 ${NDAY}일 모두 셈" "  Nothing to promote · all ${NDAY} days counted"; echo
fi
