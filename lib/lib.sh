# 공통 헬퍼. check.sh · fresh.sh 가 source 한다.
# 이 파일은 단독 실행하지 않는다.

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARSE="$HERE/concepts.py"

# 대상 파일을 읽고 DIR·ROOT를 정한다. 인자가 없거나 파일이 없으면 사용법을 내고 끝낸다.
open_concepts() {           # $1=파일 경로  $2=스크립트 이름  $3=추가 인자 설명
  F="${1:-}"
  if [ -z "$F" ]; then
    echo "사용법: $2 <CONCEPTS.md 경로>${3:+ $3}" >&2
    echo "  예: $2 \"\$PWD/CONCEPTS.md\"" >&2
    echo "  CONCEPTS.md 위치를 모르면: find . -name CONCEPTS.md -not -path \"*/node_modules/*\"" >&2
    exit 2
  fi
  [ -f "$F" ] || { echo "그 경로에 파일이 없다: $F" >&2; exit 2; }
  DIR=$(cd "$(dirname "$F")" && pwd)
  ROOT=$(git -C "$DIR" rev-parse --show-toplevel 2>/dev/null || echo "$DIR")
}

parse() { "$PARSE" "$F" "$1"; }

# 이 저장소가 그 경로를 추적하는가. 디렉터리도 통과시킨다.
tracked() { [ -n "$(git -C "$ROOT" ls-files "$1" 2>/dev/null | head -1)" ]; }

# 근거 경로 하나를 네 갈래로 진단한다. 통과하면 아무것도 출력하지 않는다.
#   경로 누락 / 약칭 / 미추적(중첩 저장소) / 끊어진 참조
diagnose_path() {
  local p="$1" hit rel disk
  tracked "$p" && return 0

  hit=$(git -C "$ROOT" ls-files "*/$p" 2>/dev/null | head -1)
  if [ -n "$hit" ]; then
    echo "    경로 누락: \`$p\` → 루트 상대로는 \`$hit\`"; return 1
  fi
  if [ -e "$ROOT/$p" ] || [ -e "$DIR/$p" ]; then
    echo "    미추적(중첩 저장소): \`$p\` — 그 저장소에서 따로 git log를 돌려야 함"; return 1
  fi

  disk=$(find "$ROOT" -name "*$(basename "$p")" \
           -not -path "*/node_modules/*" -not -path "*/.git/*" 2>/dev/null | head -1)
  if [ -z "$disk" ]; then
    echo "    끊어진 참조: \`$p\` — 같은 이름의 파일이 저장소에 없다"; return 1
  fi
  rel=${disk#"$ROOT"/}
  if tracked "$rel"; then
    echo "    약칭: \`$p\` → 실제 파일은 \`$rel\`"
  else
    echo "    미추적(중첩 저장소): \`$p\` → \`$rel\` — 그 저장소에서 따로 봐야 함"
  fi
  return 1
}
