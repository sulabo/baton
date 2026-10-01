# Session Handoff (작성: 2026-10-01 · beta v1.0 범위 확정, 단계 3 검증기·버전·README·Codex 확인 완료, 커밋 전)

## 목표와 완료 조건
- 목표: **beta v1.0 (10-04까지)** — 범위는 소유자가 10-01에 정함(`DECISIONS.md` 맨 위): ① 1.0.0-beta 표기 ② README 사용 가이드·추정치 표시 ③ 실제 Codex 세션 확인 ④ 길 단계 3 인계서 검사기·결정론 트리거. 2주 실사용 측정은 beta를 만든 **뒤**.
- 지금: ①~④ 구현·검증 끝, 브랜치 `beta-v1` 커밋·푸시·PR(소유자 승인 10-01). 남은 것: PR 머지 → 태그 `v1.0.0-beta.1` → 소유자 설치.

## 확인된 사실과 결정
- 작업 사본은 `~/baton`(새 clone). `~/Documents/바이브 코딩/baton`은 옛 이력 백업이고 10-01 현재 macOS 권한으로 `~/Documents` 전체가 막혀 있다.
- **Codex는 훅의 일반 stdout을 맥락에 넣지 않는다** — `hookSpecificOutput.additionalContext` JSON만 받는다(0.155.1 실제 세션: 일반 출력이면 "모른다", JSON이면 인계서의 다음 행동을 정답). Claude Code도 JSON을 그대로 받는다(도구 호출 0회로 정답). 그래서 `handoff-inject.py`를 JSON 출력으로 바꿨다.
- Codex에서 `Stop` 훅은 돌지만 세션 기록 형식이 달라 세션 끊기 알림·인계서 제안은 조용하다. `apply_patch`는 경로를 안 줘 인계서 자동 검사도 안 걸린다 → 스킬이 검사기를 직접 돌린다.
- 인계서 제안 문턱 3개 = 로컬 세션 94개 실측: 1~2개 고친 세션은 인계서를 16%, 3개 이상은 67% 썼다.
- 공개판 사례 ID는 별칭(game·app·docsrepo). 로컬 전용 파일(`docs/north-star/`·`cases.json`·`.data/`)은 새 clone에 없다 — 데이터 의존 테스트 3개 skip.

## 관련 파일·심볼
- `lib/handoff_check.py`: `check()` — 필수 8절·200줄·9,000자·20줄 넘는 코드 블록·닫히지 않은 블록·diff·비밀값·홈 절대경로. CLI 종료 코드 1이면 문제.
- `hooks/handoff-check.py`: PostToolUse(Write|Edit|MultiEdit)면 검사 → `decision: block`으로 모델에 반환, Stop이면 세션에 한 번 제안. 끄기 `BATON_HANDOFF_CHECK`·`BATON_HANDOFF_NUDGE`, 문턱 `BATON_HANDOFF_NUDGE_FILES`.
- `hooks/handoff-inject.py`: 출력이 JSON(`additionalContext`)으로 바뀜. `hooks/hooks.json`: 훅 다섯.
- `skills/baton/SKILL.md` 절차 2 끝에 검사기 실행 추가. `tools/stage-plugin.sh`: Codex 갱신 안내 수정.

## 이미 한 변경
- 단계 3 검사기·훅·테스트(`lib/test_handoff_check.py`, `hooks/test_handoff_check_hook.py`).
- `hooks/drift-notice.sh`: JSON 출력(Codex·Claude Code 실제 세션에서 모델이 알림 내용으로 답함) + **캐시 정리 버그 수정** — 전에는 `~/.cache/baton/` 전체에서 7일 넘은 파일을 지워 관찰 로그·설치 사본까지 지웠다(재현함). 이제 `baton/drift/`만. 테스트 `hooks/test_drift_notice.py`(옛 코드에서 실패 확인).
- 버전 0.1.0 → `1.0.0-beta.1`(`.claude-plugin/plugin.json`·`marketplace.json`, `.codex-plugin/plugin.json`). `claude plugin validate` 둘 다 통과.
- README: "쓰는 법" 절, 훅 다섯, 효과 수치의 성격(추정·스냅샷·실사용 전) 한계, Codex 확인 문구. `docs/NORTH_STAR.md` 단계 3 상태. `DECISIONS.md` 10-01 범위 항목.

## 실패한 접근법 (다시 시도 금지)
- **Codex 훅을 일반 stdout으로 출력** — 훅은 돌고 로그도 남지만 모델 맥락에 안 들어간다. 로그의 `handoff_lines`만 보고 "동작한다"고 판정하지 않는다 — 모델 답으로 확인한다.
- **`~/Documents` 안에서 `codex plugin ...` 실행** — 셸 cwd가 막힌 폴더라 실패하고 캐시가 옛 사본으로 남는다. `cd ~` 뒤 실행하고 캐시를 사본과 `/usr/bin/diff -rq`로 대조.
- **로컬 마켓플레이스에 `codex plugin marketplace upgrade`** — Git 마켓플레이스 전용. remove → add.
- 공개 전 검사를 금액 패턴만으로 / `git checkout -- .` 섞어 되돌리기 / rtk가 감싼 `diff` 믿기(`/usr/bin/diff`·md5로).

## 검증 증거
- 테스트: `python3 -m unittest hooks/test_handoff_inject.py hooks/test_split_notice.py hooks/test_handoff_check_hook.py hooks/test_drift_notice.py observer/research/test_loop4_grade.py observer/research/test_round2_e_ab.py observer/research/test_case_grade.py observer/research/test_usage_week.py observer/research/test_split_sim.py lib/test_fresh.py lib/test_rules.py lib/test_handoff_check.py tools/test_stage_plugin.py` → OK, skip 3(로컬 데이터).
- 실제 Claude Code 세션(`claude -p --plugin-dir <사본>`): 엉성한 인계서 저장 → 훅이 "필수 절 없음" 반환 / 파일 3개 생성 → 인계서 제안 표시 / 상태 질문 → JSON 주입으로 도구 0회 정답. 관찰 로그 `handoff_check`·`handoff_nudge`·`prompt` 확인.
- 실제 Codex 0.155.1 세션(격리 `CODEX_HOME`, `--dangerously-bypass-hook-trust`): JSON 주입으로 정답.
- 별도 코드 리뷰 1차 REQUEST CHANGES(비밀값 환경변수 형식 누락 등 11건) → 반영. 2차 REQUEST CHANGES(긴 줄에서 정규식 7~10초, 조사·마침표 뒤 비밀값 누락, 콜론·한글 바로 뒤 홈 경로 누락, 다른 형식 HANDOFF.md에 템플릿 강요) → 반영·테스트 추가(119개 OK, skip 3). 2차 개인 자료 점검: 새 유출 없음. **3차 리뷰는 안 돌렸다.**

## 남은 리스크와 다음 행동
- 다음 행동(세션): PR 머지는 소유자 확인 뒤 → 태그 `v1.0.0-beta.1`.
- 다음 행동(소유자): 설치 — `/plugin marketplace add sulabo/baton` → `/plugin install baton@baton`. 설치일이 실측 전후 경계. 며칠 뒤 `observer/research/usage_week.py`로 첫 비교.
- 리스크: drift-notice 수정은 별도 리뷰를 안 거쳤다(테스트·실제 세션만). 인계서를 여러 번 `Edit`로 나눠 쓰면 중간 저장마다 "필수 절 없음"이 돌아온다(의도된 동작으로 둠). 세션 끊기 절감은 재계산 추정. 검사기의 알려진 오탐: 32자 넘는 `sk-` 브랜치 이름, CI 러너의 홈 경로, 시각 문자열을 값으로 둔 secret 대입. 놓치는 것: `postgres://user:pw@host`·`npm_`·`hf_`·Bearer 비JWT. Bash로 쓴 HANDOFF.md는 제안 카운트를 리셋하지 않는다. `LIMIT_CHARS` 9,000자는 일반 stdout 기준 실측 — JSON 출력에서는 재측정 안 함.
- 가드: 푸시·설치·전역 수정·공개 전환은 소유자만.

## 승격 후보 (DECISIONS.md로 올릴 것)
- "공개 전 개인 자료 검사는 실명·프롬프트 원문·다른 저장소 내용·절대경로·커밋 이력까지 별도 레인으로" / 신호: 10-01 사고(이번 판에도 별도 레인 점검을 돌림) / 소유자가 결정으로 올릴지 정한다.
- "훅 동작 확인은 로그가 아니라 모델 답으로" / 신호: 10-01 Codex — 로그는 주입했다고 했지만 모델은 못 받았다 / 이유·버린 대안은 소유자가 채운다.

### 기각됨 (다시 올리지 않는다)
- 없음
