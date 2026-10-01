# Session Handoff (작성: 2026-10-01 · v0.2 후보 완성, 개인 자료 정리 뒤 새 이력으로 main 교체 — 소유자 실사용 대기)

## 목표와 완료 조건
- 목표: 1차 목표 v0.2 공개(`DECISIONS.md` 10-01) — ① 작업 정리 ② 세션 끊기 알림 완성 ③ **소유자 설치 후 실사용 2주** ④ 실측을 README에 넣고 v0.2.0 릴리스.
- 지금: ①② 완료. ③ 소유자 설치 대기. ④는 ③ 뒤.
- 저장소는 **비공개**(10-01 전환). 다시 공개할지는 소유자 결정.

## 확인된 사실과 결정
- 결정 기록은 이제 `DECISIONS.md`(10-01 신설). 항목마다 결정 주체(소유자 / 세션 판정)를 적었다. **방향을 바꾸기 전에 먼저 읽는다.**
- 10-01 개인 자료 점검: 옛 공개 main에 소유자의 다른 세션 프롬프트 원문, 커밋 이력에 다른 저장소 절대경로, 공개 예정 문서에 실명 파일명·경력 내용이 있었다 → 비공개 전환 → 파일 정리 → **이 커밋 하나로 main을 새 이력으로 교체**(force-push — 푸시 뒤 `gh api repos/sulabo/baton -q .pushed_at`로 확인).
- **옛 이력(45커밋)과 정리 전 원문은 소유자 로컬 저장소에만 있다** — `~/Documents/바이브 코딩/baton`(브랜치 `roadmap-step2`, 커밋 안 한 변경 포함). 그 저장소는 이제 origin과 이력이 갈라졌다. 백업으로 두고 새로 clone해서 작업한다.
- 로컬 전용(gitignore): `docs/north-star/`(정본 원문 3종) · `observer/research/cases.json`(사례 20건) · `.data/`(실험 스냅샷). 새 clone에는 없다 — 필요하면 위 로컬 저장소에서 복사. 없으면 해당 테스트 3개는 건너뛴다.
- 공개판의 다른 저장소 이름은 일반 표기로 바꿨다: 게임 저장소 = `game`(옛 이름 `game-old`), 앱 저장소 = `app`, 문서 저장소 = `docsrepo`. 사례 ID도 같은 규칙(로컬 `cases.json`은 원래 ID — 대조할 때 주의).

## 관련 파일·심볼
- `hooks/split-notice.py`(Stop 훅, 2배·3배 한 번씩) · `hooks/test_split_notice.py`(12개) · `hooks/hooks.json`(훅 넷)
- `hooks/handoff-inject.py`(인계서 on-demand 주입 + 관찰 로그) · `lib/rules.py` · `lib/runlog.py`(`~/.cache/baton/runs.jsonl`)
- `docs/NORTH_STAR.md`(목표 그림·길) · `docs/research/ROADMAP.md`(측정 부록) · `docs/research/LOOP_PLAN.md`(근거 수치)
- `observer/research/usage_week.py`(설치 전후 비교 집계기) · `split_sim.py`

## 이미 한 변경
- 세션 끊기 알림 등록·테스트 보강(필터·512KB 꼬리·압축 뒤 재알림 없음·상태 못 쓰면 침묵·이상한 줄 fail-open·sid 경로 문자 거부), 문턱별 절감 문구(2배 35~45%, 3배 30~34%).
- `DECISIONS.md` 신설. `NORTH_STAR.md`의 "사람 표본" → 이력 정답(09-22 라벨링 안 함), Jev 켜는 조건을 잴 수 있는 기준(정답률 유지 + 맥락 감소)으로.
- README: 훅 넷·관찰 로그(원문 안 남김)·Codex 설치·실험 기능 조건을 코드와 맞춤.
- 로컬 데이터가 없는 clone에서도 테스트가 통과하게(데이터 의존 테스트 3개 skip).
- 개인 자료 제거: 프롬프트 원문 예시, 실명 파일명, 경력 저장소 내용, 다른 저장소 내부 세부, 저장소 이름.

## 실패한 접근법 (다시 시도 금지)
- **공개 전 검사를 금액 패턴만으로**(09-30) — 실명·프롬프트 원문·경력 내용·다른 저장소 내부·절대경로·커밋 이력을 못 잡았다. 공개 전에는 별도 레인으로 이 전부를 본다.
- **반영일을 결정일로 착각해 기록을 "착오"로 고치기** — 고치기 전에 원문 절을 찾는다.
- **되돌리기 명령에 `git checkout -- .`를 섞어 보내기** — 파일 하나만 백업본으로 되돌린다.
- **rtk가 감싼 `diff`·`git diff` 출력 믿기** — 내용이 달라도 "Files are identical"을 낸다(`command diff`로도). `/usr/bin/diff`·md5로 확인.
- 인계서 이력·소유자 결정을 안 읽고 방향 새로 짜기 / 사람 라벨 전제 평가 / Jev 기준을 오답 교정으로 / 저장소 루트를 로컬 마켓플레이스로 설치(`.data/` 복사).

## 검증 증거
- 테스트 90개 실행 — 87 통과 · 3 skip(로컬 데이터 의존): `python3 -m unittest hooks/test_handoff_inject.py hooks/test_split_notice.py observer/research/test_loop4_grade.py observer/research/test_round2_e_ab.py observer/research/test_case_grade.py observer/research/test_usage_week.py observer/research/test_split_sim.py lib/test_fresh.py lib/test_rules.py tools/test_stage_plugin.py`
- 실제 Claude Code 세션(`claude -p --plugin-dir <사본>`, 전역 설정 안 건드림): 상태 질문에 인계서 주입 → 파일 안 열고 1턴 정답, Stop 알림이 사용자에게 표시, 관찰 로그 두 줄.
- Codex 0.155.1 격리 설치(`CODEX_HOME` 임시) 성공, 훅 넷 등록. **실제 Codex 세션 동작은 미확인.**
- 별도 코드 리뷰(REQUEST CHANGES 16건 → 반영) · 별도 개인 자료 점검(공개됨·공개 예정 → 정리). 정리 뒤 재점검 결과는 커밋 직전 판정에 반영.

## 남은 리스크와 다음 행동
- 다음 행동(소유자):
  1. 설치 — Claude Code: `/plugin marketplace add sulabo/baton` → `/plugin install baton@baton`. 비공개 저장소라 GitHub 인증이 된 환경이어야 받는다. 받기 어려우면 clone 뒤 `tools/stage-plugin.sh` 사본으로 `/plugin marketplace add ~/.cache/baton/plugin`.
  2. 2주 사용. 설치한 날짜가 전후 경계다.
- 다음 행동(세션): 2주 뒤 `observer/research/usage_week.py`로 설치 전후 비교(상태 세션의 첫 5호출 인계서 재독률 — 기준 41/42, 여는 구간 토큰 — 기준 약 357K~401K, 세션 끊기 알림 수·넘긴 세션 비율). 결과를 README에 넣고 v0.2.0.
- 리스크: 세션 끊기 절감은 재계산 추정(실측 아님). 측정은 한 사람의 사용 방식. 옛 공개 기간(09-20~10-01)에 누가 clone했다면 그 사본은 못 지운다.
- 가드: 푸시·설치·전역 수정·공개 전환은 소유자만.

## 승격 후보 (DECISIONS.md로 올릴 것)
- "공개 전 개인 자료 검사는 실명·프롬프트 원문·다른 저장소 내용·절대경로·커밋 이력까지 별도 레인으로" / 신호: 10-01 사고 / 이유는 위 실패한 접근법 / 소유자가 결정으로 올릴지 정한다.

### 기각됨 (다시 올리지 않는다)
- 없음
