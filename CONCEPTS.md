# baton 개념 지도

> 작성: 2026-11-21 · 기준 커밋 `24e3996`(origin/main) · driftmap 스킬 모드 ①(최초 생성)
> **이 지도는 탐색 앵커다. 실제 코드·결정과 다르면 실제가 정답이다.** 다르다는 것을 찾으면 이 지도를 고친다.
> 정해진 것의 출처는 `DECISIONS.md`, 실제 동작의 출처는 코드와 테스트 실행 출력, 설명된 곳은 `README.md`·`docs/NORTH_STAR.md`·스킬 문서다.
> baton이 자기 자신에게 driftmap을 적용한 사례다. 아래 어긋남은 **찾기만 하고 고치지 않았다**(고치는 것은 소유자 승인 뒤, 스킬 절차 7).

## 요약

| # | 개념 | 상태 | 심각도 | 한 줄 |
|---|---|---|---|---|
| 1 | 플러그인 구성과 스킬 이름 | 중복 정본 | 중간 | 스킬 두 개가 폴더·README 이름(`driftmap`·`baton`)과 frontmatter 이름(`ontology`·`handoff`)을 따로 가진다 |
| 2 | 0건과 못 셈의 구분 | 미결 | 중간 | README는 "검사 스크립트가 0건을 냈을 때" 알린다고 하나, 훅은 스크립트 이름과 "없음"이 함께 보이는 모든 Bash 호출에서 울린다 |
| 3 | 규칙 판단과 관찰 로그 | 낡은 문서 | 중간 | 북극성 2절 표는 "3상태 판정 없음"·"runs.jsonl 없음"이라 하나 둘 다 구현돼 있다 |
| 4 | 인계서 검사와 제안 | 낡은 문서 | 낮음 | 북극성 단계 3이 트리거를 `Stop`·`SessionEnd` 둘로 적고 테스트 수가 옛 값이다. 코드는 `Stop`만 |
| 5 | 세션 끊기 알림 | 낡은 문서 | 낮음 | 북극성 단계 S의 "테스트 7개"는 공개 이력 첫 커밋부터 12개다 |
| 6 | 메타 줄과 낡음 계산 | 낡은 문서 | 낮음 | 판정을 "여섯 가지"라 하나 규칙 개념 판정까지 일곱이고, 스킬 문서가 `check.sh` 검사 수를 여섯·다섯으로 둘 다 적는다 |
| 7 | 인계서 on-demand 주입 | 낡은 문서 | 낮음 | 북극성 2절은 "git을 못 찾으면 traceback"이라 하나, git 없이 돌려도 훅 셋 모두 조용히 끝난다 |
| 8 | 새 결정의 '관련' 가리킴 | 낡은 문서 | 낮음 | 북극성 2절이 이 기능을 "커밋 전"으로 적는다. 결정 2건에 `- 관련:` 줄이 없다 |
| 9 | 인계서 상한 200줄·9,000자 | 일치 | — | 주입 훅·검사기·스킬 문서의 값이 같다 |
| 10 | 설정 파일과 우선순위 | 일치 | — | 환경변수 > 저장소 절 > 전역 절 > 기본값, 문서와 코드가 같다 |
| 11 | 공개 경계 — 개인 자료 | 일치 | — | 정본 원문·사례 모음은 gitignore, 인계서 검사가 홈 절대경로·개인 자료 단어를 막는다 |
| 12 | 결정 기록은 사람이 쓴다 | 일치 | — | `/promote`는 후보만 내고 `DECISIONS.md`에 쓰지 않는다 |

## 1. 플러그인 구성과 스킬 이름

- **메타**: 상태=중복 정본 · 확인=2026-11-21(`24e3996`) · 파일=`.claude-plugin/plugin.json`,`.codex-plugin/plugin.json`,`.claude-plugin/marketplace.json`,`hooks/hooks.json`,`skills/driftmap/SKILL.md`,`skills/baton/SKILL.md`,`skills/baton-setup/SKILL.md` · 이웃=없음

- **정해진 것**: 범위는 `DECISIONS.md` 10-01 "beta v1.0 범위" — ① 1.0.0-beta 버전 표기. 스킬 이름에 대한 결정 기록은 없다.
- **실제 동작**:
  - 버전은 매니페스트 세 곳 모두 `1.0.0-beta.1`(`.claude-plugin/plugin.json:3`, `.codex-plugin/plugin.json:3`, `.claude-plugin/marketplace.json:11`). 서로 일치.
  - 스킬 셋·명령 다섯·훅 스크립트 다섯이 매니페스트와 `hooks/hooks.json`에 실제로 등록돼 있다(`hooks/hooks.json:4`, `hooks/hooks.json:18`, `hooks/hooks.json:28`, `hooks/hooks.json:54`).
  - 스킬 frontmatter의 `name`은 `skills/driftmap/SKILL.md:2`가 `ontology`, `skills/baton/SKILL.md:2`가 `handoff`, `skills/baton-setup/SKILL.md:2`가 `baton-setup`.
- **설명된 곳**: `README.md:93`~`README.md:99`는 스킬을 `driftmap`·`baton`으로 부른다. `commands/drift.md:6`도 "driftmap 스킬".
- **어긋남**: 한 스킬에 이름이 둘이다(폴더·README 쪽과 frontmatter 쪽). Claude Code 스킬 목록에는 `baton:driftmap (baton:ontology)`처럼 두 이름이 같이 뜬다. 사용자 수준에 `handoff`·`ontology`라는 이름의 스킬이 따로 있으면 이름이 겹친다 — 이 저장소 소유자 환경에서 실제로 둘이 나란히 목록에 뜬다. Codex에서는 스킬을 이름으로 부르라고 README가 안내하므로 어느 이름이 맞는지가 사용자에게 보이는 문제다. **어느 쪽이 정본인지 소유자가 정해야 한다.**

## 2. 0건과 못 셈의 구분

- **메타**: 상태=미결 · 확인=2026-11-21(`24e3996`) · 파일=`hooks/zero-guard.sh`,`lib/fresh.sh`,`lib/check.sh`,`lib/promote.sh` · 이웃=없음

- **정해진 것**: 결정 기록에 따로 없다. 제품의 기본 원칙으로 README와 북극성 "모든 단계에 공통"(못 센 것은 0이 아니라 "못 셌다")에 있다.
- **실제 동작**:
  - 검사 스크립트 자체는 못 센 경우를 따로 낸다 — 메타 줄 0개면 "계산할 수 없다"로 종료 코드 2(`lib/fresh.sh:41`), 결정 기록 형식을 못 알아보면 "형식 불명 — 0건이 아니라 못 셌다"(`lib/fresh.sh:137`).
  - 훅 `hooks/zero-guard.sh:6`~`hooks/zero-guard.sh:11`은 PostToolUse 입력 전체(명령과 출력) 문자열에 `check.sh`·`fresh.sh`·`promote.sh` 중 하나와 `0건`·`없음`·`메타 줄 0개` 중 하나가 **어디든 같이 있으면** 울린다. 스크립트를 실행했는지, 그 스크립트가 0을 냈는지는 보지 않는다.
  - 재현: `{"tool_input":{"command":"cat lib/fresh.sh"},"tool_response":{"stdout":"없음"}}`을 넣으면 알림이 나온다(2026-11-21 실행). 이 지도를 만드는 세션에서도 `cat`·`grep`·`sed`로 파일을 읽기만 한 호출 대부분에서 울렸다.
- **설명된 곳**: `README.md:132` "검사 스크립트가 0건을 냈을 때 … 상기시킵니다".
- **어긋남**: 코드가 설명보다 훨씬 넓게 울린다(거짓 양성). 이 프로젝트 스스로 "매번 울리는 알람은 곧 무시당한다"고 적어 두었다(`hooks/drift-notice.sh`, 스킬 문서). 실행된 스크립트의 출력만 볼지, 지금처럼 넓게 둘지에 대한 결정이 없다 — **소유자가 정한다.** 문서를 고칠지 코드를 고칠지는 그 결정에 달렸다.

## 3. 규칙 판단과 관찰 로그

- **메타**: 상태=낡은 문서 · 확인=2026-11-21(`24e3996`) · 파일=`lib/rules.py`,`lib/runlog.py`,`hooks/handoff-inject.py`,`commands/baton-explain.md` · 이웃=개념 7(정본)

- **정해진 것**: 북극성 길 단계 1(V0 Observe + Explain). `DECISIONS.md`에 따로 된 항목은 없고, 북극성 3절 단계 1 "상태(09-30)"가 구현 완료라고 적는다.
- **실제 동작**:
  - 판단은 MATCHED/AMBIGUOUS/NO_MATCH 셋(`lib/rules.py:48`), 판단 함수 `lib/rules.py:91`, 판정 버전 `rules-v1`(`lib/rules.py:16`). 인계 트리거 정규식의 정본도 여기다(`lib/rules.py:20`).
  - 훅이 프롬프트마다 판단을 `~/.cache/baton/runs.jsonl`에 남긴다. 프롬프트는 원문 대신 해시·길이만(`hooks/handoff-inject.py:99`). 파일 600, 20MB 넘으면 한 번 돌림(`lib/runlog.py:12`, `lib/runlog.py:26`, `lib/runlog.py:28`).
  - 테스트: `lib/test_rules.py` 11개 통과(2026-11-21 실행).
- **설명된 곳**: `README.md`의 "관찰 로그" 절(코드와 일치). `docs/NORTH_STAR.md:70`·`docs/NORTH_STAR.md:71`(2절 표).
- **어긋남**: 북극성 2절 표는 Decision Layer 칸에 "인터페이스·**3상태 판정**·Jev·Judge 없음", V0 Observe 칸에 "**없음**. 사후 집계기만"이라 적는다. 같은 문서 3절 단계 1과 코드는 둘 다 있다고 말한다. 2절 표가 10-01 구현을 반영하지 않은 것이다 — **낡은 문서**(코드가 앞서 있다). 같은 표의 다른 칸도 같은 원인으로 낡았다(Fallback 칸은 인계서 주입 절, 개념 지도 점검 칸은 '관련' 가리킴 절에 따로 적었다). 이 표 하나가 여러 개념에서 동시에 낡은 것은 개별 실수가 아니라 **갱신 경로의 구멍**이다 — 구현 커밋이 북극성 2절 표를 갱신 대상에 넣지 않았다.

## 4. 인계서 검사와 제안

- **메타**: 상태=낡은 문서 · 확인=2026-11-21(`24e3996`) · 파일=`lib/handoff_check.py`,`hooks/handoff-check.py`,`hooks/hooks.json` · 이웃=개념 9(정본), 개념 10(전제), 개념 11(전제)

- **정해진 것**: `DECISIONS.md` 10-01 "beta v1.0 범위" — 길 단계 3의 인계서 검사기와 결정론 트리거를 넣는다(소유자).
- **실제 동작**:
  - 검사기: 필수 8절(`lib/handoff_check.py:21`)·200줄·9,000자·긴 코드 블록·전체 diff·비밀값·홈 절대경로(`lib/handoff_check.py:37`)·개인 자료 목록(`lib/handoff_check.py:49`). 훅 모드에서는 baton 형식으로 보이는 인계서에만 필수 절을 요구한다(`lib/handoff_check.py:94`).
  - `HANDOFF.md`를 `Write|Edit|MultiEdit`한 직후 검사(`hooks/handoff-check.py:33`, `hooks/hooks.json:28`), 문제가 있으면 모델에 돌려준다.
  - 제안: `Stop`에서만, 마지막 인계서 저장 뒤 다른 파일을 3개 이상 고쳤으면 세션에 한 번(`hooks/handoff-check.py:89`, `hooks/handoff-check.py:100`, `hooks/handoff-check.py:107`). `SessionEnd`에는 등록돼 있지 않다.
  - 테스트: `lib/test_handoff_check.py` 20개 + `hooks/test_handoff_check_hook.py` 11개 통과(2026-11-21 실행). 이 저장소의 루트 `HANDOFF.md`도 검사기를 통과한다("문제 없음").
- **설명된 곳**: `README.md`의 "인계서를 쓰면 바로 검사합니다"(코드와 일치). `docs/NORTH_STAR.md:134`·`docs/NORTH_STAR.md:136`.
- **어긋남**: 북극성 단계 3 본문(`docs/NORTH_STAR.md:136`)이 결정론 트리거를 "`Stop`·`SessionEnd` 훅에서"라고 적는다. 바로 위 상태 줄(`docs/NORTH_STAR.md:134`)은 "`SessionEnd` 대신 `Stop`만"이라 하고 코드도 `Stop`만이다 — 같은 절 안에서 서로 다르다. 상태 줄의 "테스트 18개"는 10-01 커밋 `8834a01` 기준 검사기 테스트만 센 값이고, 지금은 20 + 11개다. **낡은 문서.**

## 5. 세션 끊기 알림

- **메타**: 상태=낡은 문서 · 확인=2026-11-21(`24e3996`) · 파일=`hooks/split-notice.py`,`hooks/hooks.json` · 이웃=개념 10(전제)

- **정해진 것**: `DECISIONS.md` 09-30 "토큰 효율은 세션 끊기를 먼저 한다"(소유자). 문턱 2배·3배와 "권고만"은 세션의 구현 기본값.
- **실제 동작**: `Stop`에서 세션 기록의 첫 호출 맥락과 마지막 호출 맥락을 비교해(`hooks/split-notice.py:19`) 문턱(기본 `2,3`, `hooks/split-notice.py:64`)을 처음 넘을 때만 알린다(`hooks/split-notice.py:92`, `hooks/split-notice.py:103`). `hooks/hooks.json:54`에 등록. 테스트 `hooks/test_split_notice.py` 12개 통과(2026-11-21 실행).
- **설명된 곳**: `README.md`의 "세션이 불어나면 한 번 알립니다"(코드와 일치). `docs/NORTH_STAR.md:101`.
- **어긋남**: 북극성 단계 S 상태 줄(`docs/NORTH_STAR.md:101`)이 "테스트 7개"라 적는다. 공개 이력 첫 커밋 `9a7915c`(10-01)에서 이미 12개였다. 날짜가 박힌 상태 줄이라 그날 값일 수 있지만, 공개 이력 어디에서도 7개였던 적이 없다. **낡은 문서**(낮음).

## 6. 메타 줄과 낡음 계산

- **메타**: 상태=낡은 문서 · 확인=2026-11-21(`24e3996`) · 파일=`lib/concepts.py`,`lib/fresh.sh`,`lib/check.sh`,`lib/lib.sh`,`hooks/drift-notice.sh` · 이웃=개념 8(전제)

- **정해진 것**: 결정 기록에 따로 없다. 스킬 문서(`skills/driftmap/SKILL.md`)가 규칙의 정본 역할을 한다.
- **실제 동작**:
  - 형식을 아는 곳은 파서 하나다(`lib/concepts.py:21`, `lib/concepts.py:22`, `lib/concepts.py:48`).
  - 판정은 커밋 수(`lib/fresh.sh:92`)·기준 없음·기준 소실(`lib/fresh.sh:71`)·경로 소실·미추적(`lib/fresh.sh:76`)·신선(`lib/fresh.sh:94`)에 더해 **규칙 개념 판정**(`lib/fresh.sh:66`)이 있다 — 일곱 가지.
  - `check.sh`의 검사는 [1]~[6] 여섯 가지다(마지막 둘은 '파일' 항목의 지침 파일 섞임과 메타 줄 수).
  - 테스트 `lib/test_fresh.py` 9개, `hooks/test_drift_notice.py` 3개 통과(2026-11-21 실행).
- **설명된 곳**: `README.md:159`, `skills/driftmap/SKILL.md:251`, `skills/driftmap/SKILL.md:259`, `skills/driftmap/SKILL.md:314`, `skills/driftmap/SKILL.md:167`.
- **어긋남** (모두 낡은 문서, 낮음):
  - 판정 수 — `README.md:159`·`skills/driftmap/SKILL.md:314` "여섯 가지"인데 코드에는 규칙 개념 판정이 하나 더 있다.
  - `check.sh` 검사 수 — 스킬 문서가 표에서는 "여섯 가지"(`skills/driftmap/SKILL.md:251`), 바로 아래 본문에서는 "다섯 가지를 본다"(`skills/driftmap/SKILL.md:259`)라 적고 다섯만 나열한다. 코드는 여섯.
  - 간선 종류 — 절 제목은 "네 종류"(`skills/driftmap/SKILL.md:167`)인데 표에는 셋(전제·정본·공유파일)뿐이다.
- **이번에 함께 찾은 잠복 결함 둘** (지금 동작에는 드러나지 않음, 고치지 않음):
  - 파서는 숫자 없는 `##` 절을 마지막 개념 절의 본문으로 읽는다(`lib/concepts.py:48`). 스킬이 권하는 산출물 구성(일치 확인된 것·확인하지 못한 것·유지 규칙을 개념 뒤에 둔다)을 따르면 그 절들이 마지막 개념에 붙는다. 그러면 그 절들 속 "개념 N" 언급이 마지막 개념의 참조로 세어지고, 실험 기능 개념 주입은 마지막 개념을 고르면 뒤 절까지 함께 넣는다. 이 지도로 재면(2026-11-21) 마지막 개념 자체는 8줄·591자인데 주입 텍스트는 뒤 절을 포함해 1,970자다 — 2,000자 상한을 겨우 넘지 않아 실제로 들어간다. 이 지도는 그것을 피하려고 뒤 절에서 개념을 번호 대신 이름으로 부른다.
  - 세션 시작 알림은 `fresh.sh` 출력에서 `신선`이 들어간 줄을 센다(`hooks/drift-notice.sh:53`). 개념 이름에 "신선"이 들어 있으면 그 줄이 판정과 상관없이 신선으로 세어진다. 이 지도는 그래서 이 절 이름을 "낡음 계산"으로 지었다.

## 7. 인계서 on-demand 주입

- **메타**: 상태=낡은 문서 · 확인=2026-11-21(`24e3996`) · 파일=`hooks/handoff-inject.py`,`lib/rules.py`,`hooks/hooks.json` · 이웃=개념 3(정본), 개념 9(정본), 개념 10(전제)

- **정해진 것**: `DECISIONS.md` 09-27 "인계서 주입은 on-demand, 200줄·9,000자"(세션 판정, 200줄은 09-22 소유자 결정).
- **실제 동작**:
  - `UserPromptSubmit`에서 프롬프트가 트리거 말(`lib/rules.py:20`, 설정의 추가 말 포함)에 맞을 때만 주입(`hooks/handoff-inject.py:73`, `hooks/handoff-inject.py:77`). 무관한 프롬프트에는 넣지 않는다.
  - 출력은 Claude Code·Codex 둘 다 받는 JSON `additionalContext`.
  - git이 없을 때: 저장소 루트 계산이 예외를 삼키고 폴더 기준으로 넘어간다(`lib/rules.py:135`, `lib/rules.py:141`). 2026-11-21에 git이 없는 `PATH`로 `handoff-inject.py`·`split-notice.py`·`handoff-check.py`를 돌렸을 때 셋 다 종료 코드 0, 출력 없음.
  - 테스트 `hooks/test_handoff_inject.py` 8개 통과(2026-11-21 실행).
- **설명된 곳**: `README.md`의 "인계서는 물어볼 때만 넣습니다"(코드와 일치). `docs/NORTH_STAR.md:83`.
- **어긋남**: 북극성 2절 표 Fallback 칸(`docs/NORTH_STAR.md:83`)이 "다만 조용하지는 않다 — git을 못 찾으면 traceback을 낸다"고 적는다. 위 실행으로는 traceback이 나지 않는다. **낡은 문서**(낮음). 규칙 판단 절에 적은 것과 같은 표, 같은 원인이다.

## 8. 새 결정의 '관련' 가리킴

- **메타**: 상태=낡은 문서 · 확인=2026-11-21(`24e3996`) · 파일=`lib/fresh.sh`,`lib/concepts.py` · 이웃=개념 6(전제)

- **정해진 것**: 결정 기록에 따로 없다. 스킬 문서 모드 ④ "결정이 움직였는가"가 미구현을 잡는 유일한 경로라고 적는다.
- **실제 동작**: 메타 줄의 확인 해시 이후 `DECISIONS.md`에 새로 들어온 줄 중 `관련` 뒤의 "개념 N"·개념 이름을 찾아 그 개념을 재확인으로 올린다(`lib/fresh.sh:26`, `lib/concepts.py:28`, `lib/concepts.py:133`). 못 이은 것은 "0건이 아니라 못 셌다"로 따로 낸다. 새 결정 중 `- 관련:` 줄이 없는 것을 구멍으로 센다(`lib/fresh.sh:126`).
- **설명된 곳**: `skills/driftmap/SKILL.md` 모드 ④, `docs/NORTH_STAR.md:78`.
- **어긋남**:
  - 북극성 2절 표 개념 지도 점검 칸(`docs/NORTH_STAR.md:78`)이 "새 결정 → 재확인(09-30, **커밋 전**)"이라 적는다. 공개 이력 첫 커밋부터 커밋돼 있다. **낡은 문서**(낮음).
  - **갱신 경로의 구멍**(대신 채우지 않음): `DECISIONS.md` 16개 항목 중 09-22 "인계서 상한 200줄"과 09-22 "진실 신호 없이 라우팅 후보는 시험하지 않는다" 두 항목에 `- 관련:` 줄이 없다. 이 둘이 어느 개념을 건드렸는지는 결정한 사람이 적는다. 특히 앞의 것은 인계서 상한 개념의 "정해진 것"이다.
  - 이 저장소 `DECISIONS.md`의 `관련:` 줄은 개념 번호 대신 파일 경로를 쓴다. 이 지도가 생겼으니 앞으로는 경로에서 개념을 역산할 수 있다(스킬 절차 4).

## 9. 인계서 상한 200줄·9,000자

- **메타**: 상태=일치 · 확인=2026-11-21(`24e3996`) · 파일=`hooks/handoff-inject.py`,`lib/handoff_check.py`,`skills/baton/SKILL.md` · 이웃=개념 4(정본), 개념 7(정본)

- **정해진 것**: `DECISIONS.md` 09-22 "인계서 상한 200줄"(소유자, 이유 칸 비어 있음) · 09-27 "인계서 주입은 on-demand, 200줄·9,000자"(9,000자는 실측: 20,826자는 Claude Code가 파일로 뺐다).
- **실제 동작**: 주입 훅 `hooks/handoff-inject.py:24`·`hooks/handoff-inject.py:25`, 검사기 `lib/handoff_check.py:16`·`lib/handoff_check.py:17` — 네 상수 모두 200·9000. 주입은 넘치면 자르고 잘랐다고 한 줄 붙인다(`hooks/handoff-inject.py:85`).
- **설명된 곳**: `skills/baton/SKILL.md:94`, `README.md`, `docs/NORTH_STAR.md` 1절("Handoff ≤ 200줄").
- **어긋남**: 없음. 값이 코드 두 곳에 따로 박혀 있어(하나를 바꾸면 다른 하나는 그대로) 나중에 갈라질 수 있는 자리다 — 지금은 같다.

## 10. 설정 파일과 우선순위

- **메타**: 상태=일치 · 확인=2026-11-21(`24e3996`) · 파일=`lib/config.py`,`lib/setup_scan.py` · 이웃=개념 4·5·7(전제)

- **정해진 것**: 결정 기록에 따로 없다(`/baton-setup`은 커밋 `24e3996`에서 들어왔다).
- **실제 동작**: `lib/config.py:119` — 환경변수 > 저장소 절 > 전역 절 > 기본값. 관찰 로그 키 둘은 전역만(`lib/config.py:22`). 목록 키는 전역 + 저장소(`lib/config.py:132`). 테스트 `lib/test_config.py` 23개 통과(2026-11-21 실행). 세션 끊기 문턱·인계서 제안 문턱·추가 트리거 말·각 훅의 끄기 스위치가 모두 이 설정을 읽는다.
- **설명된 곳**: `README.md:73`, `skills/baton-setup/SKILL.md`, `commands/baton-setup.md`.
- **어긋남**: 없음.

## 11. 공개 경계 — 개인 자료

- **메타**: 상태=일치 · 확인=2026-11-21(`24e3996`) · 파일=`.gitignore`,`lib/handoff_check.py` · 이웃=개념 4(전제)

- **정해진 것**: `DECISIONS.md` 10-01 "북극성 정본 원문과 사례 모음은 공개 저장소에 올리지 않는다" · 10-01 "개인 자료가 섞인 공개 이력을 새 이력 하나로 바꾼다"(공개 전 검사는 실명·프롬프트 원문·다른 저장소 내용·절대경로·커밋 이력까지 본다). 둘 다 소유자.
- **실제 동작**: `.gitignore`가 `docs/north-star/`와 `observer/research/cases.json`을 뺀다. 인계서 검사기는 홈 절대경로와 사용자가 고른 개인 자료 단어를 막고, 찾은 값 자체는 출력하지 않는다(`lib/handoff_check.py:37`, `lib/handoff_check.py:49`). 관찰 로그는 프롬프트 원문을 남기지 않는다(`hooks/handoff-inject.py:99`).
- **설명된 곳**: `docs/NORTH_STAR.md` 0절(정본 경로는 소유자 로컬 기준이라고 밝힘), `README.md`의 "관찰 로그"·"설치 후 한 번" 절.
- **어긋남**: 없음. `docs/NORTH_STAR.md`의 정본 경로 표는 공개판에 없는 파일을 가리키지만, 바로 아래에 "공개 저장소에는 없다"고 밝혀 두었다 — 끊어진 참조가 아니라 의도된 것.

## 12. 결정 기록은 사람이 쓴다

- **메타**: 상태=일치 · 확인=2026-11-21(`24e3996`) · 파일=`lib/promote.sh`,`commands/promote.md`,`skills/baton/SKILL.md` · 이웃=없음

- **정해진 것**: `DECISIONS.md` 머리말 — "이유 칸이 비어 있는 것은 기록이 없어서다, 추측으로 채우지 않았다". 항목마다 결정 주체(소유자/세션 판정)를 적는다.
- **실제 동작**: `lib/promote.sh`는 과거 인계서를 날짜당 한 판씩 읽어(`lib/promote.sh:37`) 서로 다른 3일 이상 살아남은 항목을 후보로 출력만 한다(`lib/promote.sh:9`, `lib/promote.sh:49`). 파일을 쓰지 않는다. 명령 문서는 "버린 대안·이유는 빈칸으로"(`commands/promote.md:11`).
- **설명된 곳**: `README.md:183` "넘지 않는 선", `skills/baton/SKILL.md`의 "승격은 제안까지만 한다".
- **어긋남**: 없음. 실제 `DECISIONS.md`도 이 규칙을 지킨다 — 이유를 모르는 항목은 "(기록 없음)"으로 비어 있다.

## 일치 확인된 것

근거는 각 개념 절의 실제 동작 면에 있다. 여기에는 따로 대조해 맞았던 것만 모은다.

- 테스트 168개 통과(2026-11-21, `python3 -m unittest discover -s` 네 묶음: hooks 34·lib 83·tools 4·observer/research 47, 건너뜀 3).
- 매니페스트 세 곳의 버전이 같다(`1.0.0-beta.1`).
- README "명령 다섯"은 `commands/` 파일 다섯 개와, "훅 다섯"은 `hooks/hooks.json`에 등록된 스크립트 다섯 개와 맞는다.
- 인계서 템플릿의 8절(`skills/baton/SKILL.md` 템플릿)과 검사기의 필수 절 목록이 같다.
- 루트 `HANDOFF.md`는 검사기를 통과한다(49줄, "문제 없음"). 이 작업은 그 파일을 고치지 않았다.

## 폐기된 개념

없음(최초 생성).

## 확인하지 못한 것

- **Linux에서의 동작.** 모든 실행은 macOS에서 했다.
- **Codex에서 스킬 이름이 어떻게 보이는지.** 플러그인 구성 절의 이름 충돌은 Claude Code 목록에서만 봤다.
- **지도의 링크 자리.** 스킬은 매 세션 읽히는 `AGENTS.md`(또는 `CLAUDE.md`)에서 이 지도를 한 줄로 가리키라고 한다. 이 저장소에는 둘 다 없고, README는 열린 릴리스 PR이 고치는 중이라 이번에는 링크를 걸지 않았다. 세션 시작 훅은 저장소 최상위 두 단계 안의 `CONCEPTS.md`를 스스로 찾으므로 신선도 알림은 링크 없이도 돈다.
- **결정 기록의 이유 칸.** 비어 있는 이유는 추측하지 않았다.

## 유지 규칙

- 먼저 `/drift`(모드 ④)를 돌린다. 재확인 대상이 없으면 열지 않는다.
- 재확인 대상만 다시 대조하고, 대조한 개념의 메타 줄 `확인=`을 그때의 커밋으로 옮긴다. 지도와 코드를 한 커밋에서 같이 고쳤다면 다음 커밋에서 옮긴다.
- 어긋남을 고쳐 닫으면 지우지 말고 상태를 `해소됨(날짜)`로 바꾼다.
- `파일`에는 코드·테스트·산출물만 적는다. `DECISIONS.md`·`HANDOFF.md`·`README.md`는 넣지 않는다(설명된 곳이나 정해진 것의 출처다).
- 간선은 전제·정본만, 양쪽에 적는다. 공유파일 관계는 적지 않는다.
- 뒤쪽 절(이 절 포함)에서는 개념을 번호로 부르지 않는다 — 파서가 이 절들을 마지막 개념의 본문으로 읽는다(메타 줄과 낡음 계산 절의 잠복 결함).
