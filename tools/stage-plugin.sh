#!/usr/bin/env bash
# 설치용 깨끗한 사본을 만든다. Claude Code·Codex 모두 로컬 마켓플레이스를 설치할 때 플러그인 루트를 통째로 복사한다.
# 저장소 루트를 그대로 주면 gitignore된 .data/(실험 스냅샷 2.6G — 원본 저장소 사본 포함)·.git·.omc까지 캐시로 들어간다(2026-09-30 실측).
# 그래서 git이 아는 파일(추적 + 무시 안 된 새 파일, 작업 트리에서 지운 것은 뺌)만 옮긴 사본을 설치 원본으로 쓴다.
#   tools/stage-plugin.sh [대상 폴더]   기본: ~/.cache/baton/plugin
# 갱신: 다시 돌린 뒤 Claude Code는 /plugin marketplace update baton, Codex는 codex plugin remove baton@baton → codex plugin add baton@baton
#   (Codex의 marketplace upgrade는 Git 마켓플레이스만 받는다 — 로컬 사본에는 "not configured as a Git marketplace", 10-01 확인)
set -euo pipefail
SRC=$(git -C "$(dirname "${BASH_SOURCE[0]}")/.." rev-parse --show-toplevel)
DST="${1:-${XDG_CACHE_HOME:-$HOME/.cache}/baton/plugin}"
MARK=.baton-stage

case "/$DST/" in */../*|*/./*) echo "대상 경로에 . 이나 .. 가 있다 — 절대 경로로 준다: $DST" >&2; exit 2;; esac
# 저장소 안(무시된 중첩 저장소 포함)이면 거부한다. 한글 경로는 NFC/NFD가 섞여 셸 문자열 비교가 빗나가므로(09-30 실제로 뚫림)
# 가장 가까운 기존 조상의 실제 경로를 정규화해 비교한다
inside=$(python3 - "$SRC" "$DST" <<'PY'
import os, sys, unicodedata
n = lambda p: unicodedata.normalize("NFC", os.path.realpath(p))
src, dst = n(sys.argv[1]), sys.argv[2]
while not os.path.isdir(dst): dst = os.path.dirname(dst)
dst = n(dst)
print("yes" if dst == src or dst.startswith(src + os.sep) else "no")
PY
)
[ "$inside" = yes ] && { echo "대상이 저장소 안이다: $DST" >&2; exit 2; }
[ -e "$DST" ] && [ ! -f "$DST/$MARK" ] && { echo "대상이 이 스크립트가 만든 폴더가 아니다(표지 없음): $DST" >&2; exit 2; }

# 목록: 추적+무시 안 된 새 파일 − 작업 트리에서 지운 것. 추적 안 된 중첩 저장소는 "폴더/"로 나와 통째로 복사되므로 거부한다
LIST=$(mktemp); trap 'rm -f "$LIST"' EXIT
python3 - "$SRC" > "$LIST" <<'PY'
import subprocess, sys
g = lambda *a: [p for p in subprocess.run(["git", "-C", sys.argv[1], *a], capture_output=True, check=True).stdout.split(b"\0") if p]
gone = set(g("ls-files", "-d", "-z"))
keep = [p for p in g("ls-files", "-co", "--exclude-standard", "-z") if p not in gone]
dirs = [p for p in keep if p.endswith(b"/")]
if dirs:
    sys.stderr.write("추적 안 된 폴더(중첩 저장소일 수 있음)가 있어 멈춘다: %s\n" % b", ".join(dirs).decode("utf-8", "replace")); sys.exit(3)
sys.stdout.buffer.write(b"\0".join(keep))
PY

rm -rf "$DST"; mkdir -p "$DST"
git -C "$SRC" rev-parse --short HEAD > "$DST/$MARK"   # 표지를 먼저 — 복사가 도중에 실패해도 다음 실행이 이 폴더를 치울 수 있다
(cd "$SRC" && tar -c --null -T "$LIST" -f -) | tar xf - -C "$DST"
n=$(find "$DST" -type f | wc -l | tr -d ' ')
echo "사본: $DST (파일 ${n}개, $(du -sh "$DST" | cut -f1), 기준 $(cat "$DST/$MARK")$(git -C "$SRC" diff --quiet HEAD || echo ' + 커밋 안 한 변경'))"
