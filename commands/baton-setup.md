---
description: 설치 후 한 번. 내 과거 세션 기록·git 이력으로 baton 문턱과 개인 자료 목록을 제안하고, 고른 것만 설정 파일에 쓴다.
---

`baton-setup` 스킬의 절차를 따른다.

1. `python3 "$CLAUDE_PLUGIN_ROOT/lib/setup_scan.py"`를 현재 저장소에서 돌린다. 읽기만 한다.
2. 결과를 한국어로 옮기되 항목마다 **센 것과 못 센 것을 함께** 보고한다. 0은 "없음"이 아니라 "못 셈"일 수 있다.
3. `AskUserQuestion`으로 한 가지씩 고르게 한다(추천안과 이유 먼저). 고르지 않은 것은 쓰지 않는다.
4. 고른 것만 `setup_scan.py apply ...`로 쓰고, 바뀐 키·위치·되돌리는 법(`--unset <키>`·`--remove-terms-file`·`--remove-trigger`, 환경변수가 우선)을 알린다.
   개인 자료 단어는 명령줄에 적지 않는다 — `--private-terms-file`이나 세션 밖 터미널(스킬 4단계). 스캔 출력도 이 대화 기록에 남는다는 것을 먼저 알린다.

`$ARGUMENTS`가 있으면 그 경로를 저장소 루트로 삼는다.
