# baton 개념 지도

> 작성: 2026-11-21 · 기준 커밋 `7c71c9d`(마지막 후속 PR의 마지막 코드 커밋. merge commit으로 main에 들어가 해시가 남는다) · driftmap 스킬 모드 ①(최초 생성) → 같은 날 모드 ③(갱신)
> **이 지도는 탐색 앵커다. 실제 코드·결정과 다르면 실제가 정답이다.** 다르다는 것을 찾으면 이 지도를 고친다.
> 정해진 것의 출처는 `DECISIONS.md`, 실제 동작의 출처는 코드와 테스트 실행 출력, 설명된 곳은 `README.md`·`docs/NORTH_STAR.md`·스킬 문서다.
> 2026-11-21 같은 날 PR #3·#5·#8이 머지될 때마다 다시 대조했다. 코드 근거는 `fresh.sh`가 재확인으로 올린 개념만 다시 봤다. README 줄 번호는 `fresh.sh`가 보지 않아서 손으로 다시 맞췄다(메타 줄과 낡음 계산 절). README를 두 기둥(인계서·개념 지도) 중심으로 다시 쓴 뒤(브랜치 `readme-read-less`) 줄 번호를 다시 맞췄다.
> baton이 자기 자신에게 driftmap을 적용한 사례다. 처음 판(PR #7)은 어긋남을 **찾기만 하고 고치지 않았다**. 소유자 승인 뒤 같은 날 고쳤다(`6b51162`). 고친 항목은 지우지 않고 `해소됨(2026-11-21)`으로 남겼다(스킬 절차 7).

## 요약

| # | 개념 | 상태 | 심각도 | 한 줄 |
|---|---|---|---|---|
| 1 | 플러그인 구성과 스킬 이름 | 중복 정본 | 중간 | 스킬 두 개가 폴더 이름(`driftmap`·`baton`)과 frontmatter 이름(`ontology`·`handoff`)을 따로 가진다. 공개 이름이 바뀌는 일이라 고치지 않고 선택지만 적었다 |
| 8 | 새 결정의 '관련' 가리킴 | 미결 | 낮음 | 결정 2건에 `- 관련:` 줄이 없다(결정한 사람이 채운다). "커밋 전" 표기는 해소됨(2026-11-21) |
| 2 | 0건과 못 셈의 구분 | 해소됨(2026-11-21) | — | 0건 상기 훅이 스크립트를 실제로 실행했고 그 출력에 0건 신호가 있을 때만 울린다 |
| 3 | 규칙 판단과 관찰 로그 | 해소됨(2026-11-21) | — | 북극성 2절 표가 3상태 판정·판단 로그를 "없음"으로 적던 것을 고쳤다 |
| 4 | 인계서 검사와 제안 | 해소됨(2026-11-21) | — | 북극성 단계 3의 트리거(`Stop`만)·테스트 수를 고쳤다 |
| 5 | 세션 끊기 알림 | 해소됨(2026-11-21) | — | 북극성 단계 S의 테스트 수를 고쳤다 |
| 6 | 메타 줄과 낡음 계산 | 해소됨(2026-11-21) | — | 마지막 남은 README 데모 출력의 `구현됨`을 임시 데모 저장소에서 실제로 다시 돌린 출력으로 바꿨다. 문서 항목 미구현·파서·세는 방식·README 예시·스킬 문서 수치도 해소됨 |
| 7 | 인계서 on-demand 주입 | 해소됨(2026-11-21) | — | 북극성 2절의 "git을 못 찾으면 traceback"을 실제 동작대로 고쳤다 |
| 9 | 인계서 상한 200줄·9,000자 | 일치 | — | 주입 훅·검사기·스킬 문서의 값이 같다 |
| 10 | 설정 파일과 우선순위 | 일치 | — | 환경변수 > 저장소 절 > 전역 절 > 기본값, 문서와 코드가 같다 |
| 11 | 공개 경계 — 개인 자료 | 일치 | — | 정본 원문·사례 모음은 gitignore, 인계서 검사가 홈 절대경로·개인 자료 단어를 막는다 |
| 12 | 결정 기록은 사람이 쓴다 | 일치 | — | `/promote`는 후보만 내고 `DECISIONS.md`에 쓰지 않는다 |

## 1. 플러그인 구성과 스킬 이름

- **메타**: 상태=중복 정본 · 확인=2026-11-22(`681afff`) · 파일=`.claude-plugin/plugin.json`,`.codex-plugin/plugin.json`,`.claude-plugin/marketplace.json`,`hooks/hooks.json`,`skills/driftmap/SKILL.md`,`skills/baton/SKILL.md`,`skills/baton-setup/SKILL.md`,`tools/check_versions.py` · 이웃=없음 · 문서=`README.md`,`README.ko.md`,`commands/drift.md`

- **정해진 것**: 범위는 `DECISIONS.md` 10-01 "beta v1.0 범위" — ① 1.0.0-beta 버전 표기. 스킬 이름에 대한 결정 기록은 없다.
- **실제 동작**:
  - 버전은 매니페스트 세 곳 모두 `1.0.0-beta.2`(`.claude-plugin/plugin.json:3`, `.codex-plugin/plugin.json:3`, `.claude-plugin/marketplace.json:11`). 서로 일치. PR #9부터 `tools/check_versions.py`가 이 세 곳과 CHANGELOG 맨 위 버전이 같은지 CI에서 본다(2026-11-21 실행: `ok: all versions = 1.0.0-beta.2`).
  - 스킬 셋·명령 다섯·훅 스크립트 다섯이 매니페스트와 `hooks/hooks.json`에 실제로 등록돼 있다(`hooks/hooks.json:4`, `hooks/hooks.json:18`, `hooks/hooks.json:28`, `hooks/hooks.json:54`). Claude Code 매니페스트는 PR #3부터 `hooks` 키 없이 기본 위치를 쓰고, Codex 매니페스트는 그대로 적는다(`.codex-plugin/plugin.json:11`).
  - 2026-11-22: 매니페스트 세 곳의 `description`을 새 소개 문구("새 대화마다 프로젝트를 다시 읽지 않게")로 바꿨다(`681afff`). 버전·스킬·명령·훅 등록은 그대로다(`tools/check_versions.py` ok, `claude plugin validate .` 통과).
  - 스킬 frontmatter의 `name`은 `skills/driftmap/SKILL.md:2`가 `ontology`, `skills/baton/SKILL.md:2`가 `handoff`, `skills/baton-setup/SKILL.md:2`가 `baton-setup`.
- **설명된 곳**: `README.md:83`·`README.md:203`·`README.md:246`, `README.ko.md:71`·`README.ko.md:214`는 개념 지도 스킬을 `driftmap`으로 부른다(PR #8 이후 README에는 인계서 스킬 이름이 따로 나오지 않는다). `commands/drift.md:7`도 "driftmap 스킬".
- **어긋남**: 한 스킬에 이름이 둘이다(폴더·README 쪽과 frontmatter 쪽). Claude Code 스킬 목록에는 `baton:driftmap (baton:ontology)`처럼 두 이름이 같이 뜬다. 사용자 수준에 `handoff`·`ontology`라는 이름의 스킬이 따로 있으면 이름이 겹친다 — 이 저장소 소유자 환경에서 실제로 둘이 나란히 목록에 뜬다. Codex에서는 스킬을 이름으로 부르라고 README가 안내하므로 어느 이름이 맞는지가 사용자에게 보이는 문제다. **어느 쪽이 정본인지 소유자가 정해야 한다.** 공개 인터페이스가 바뀌는 일이라 2026-11-21 수정에서는 고치지 않았다. 선택지:
  - 가(추천). frontmatter `name`을 폴더 이름(`driftmap`·`baton`)으로 맞춘다. README·명령 문서·홍보 문구가 이미 이 이름을 쓰고, 흔한 사용자 스킬 이름(`handoff`·`ontology`)과 겹치지 않는다. 대가: Codex에서 `ontology`·`handoff`로 부르던 사람은 이름이 바뀐다(공개 1주 안이라 사용자는 적다).
  - 나. 폴더와 README를 frontmatter 이름으로 맞춘다. README·CHANGELOG·명령 문서를 여러 곳 고쳐야 하고, 사용자 스킬과 계속 겹친다.
  - 다. 그대로 두고 README에 "Codex에서는 `ontology`·`handoff`로 보인다"를 적는다. 바꾸는 것이 없지만 이름이 둘인 상태가 남는다.
  - 상태(2026-11-21): 선택지와 추천은 소유자 확인 단계로 넘어갔다. 후속 PR에서도 고치지 않았다.

## 2. 0건과 못 셈의 구분

- **메타**: 상태=해소됨(2026-11-21) · 확인=2026-11-22(`681afff`) · 파일=`hooks/zero-guard.sh`,`lib/fresh.sh`,`lib/check.sh`,`lib/promote.sh`,`hooks/test_zero_guard.py` · 이웃=없음 · 문서=`README.md`,`README.ko.md`

- **정해진 것**: 결정 기록에 따로 없다. 제품의 기본 원칙으로 README와 북극성 "모든 단계에 공통"(못 센 것은 0이 아니라 "못 셌다")에 있다.
- **실제 동작**:
  - 검사 스크립트 자체는 못 센 경우를 따로 낸다 — 메타 줄 0개면 "계산할 수 없다"로 종료 코드 2(`lib/fresh.sh:88`), 결정 기록 형식을 못 알아보면 "형식 불명 — 0건이 아니라 못 셌다"(`lib/fresh.sh:208`).
  - 훅은 두 조건이 다 맞을 때만 울린다. 첫째, 따옴표를 먼저 푼 뒤 `&&`·`;`·`|`에서 나눈 조각 중 하나가 첫 실행 파일로 `check.sh`·`fresh.sh`·`promote.sh`를 돌린다(`hooks/zero-guard.sh:34`, `hooks/zero-guard.sh:52`). 이때 환경변수 대입과 감싸개(`timeout 60`·`sudo -u x`·`nice -n 5`·`env -u X`·`rtk`·`rtk proxy`·`bash -o pipefail`)는 옵션 값까지 건너뛰고 보고, `bash -c "…"`는 그 문자열 안을 다시 본다(`hooks/zero-guard.sh:60`, `hooks/zero-guard.sh:68`). 둘째, 그 출력에 0건 신호(`0건`·`없음`·`메타 줄 0개`·요약 줄의 `재확인 0`)가 있다(`hooks/zero-guard.sh:85`). 명령 문장 속의 "0건"이나 `10건`은 세지 않는다.
  - 테스트 `hooks/test_zero_guard.py` 14개 통과(2026-11-21 실행). 후속 PR에서 `. lib/fresh.sh`·`source lib/fresh.sh`와 xargs 세 형태를 더했다. xargs는 이미 잡히고 있었고 `.`·`source`는 그 전 코드에서 실패했다. 처음 고칠 때 넣은 넷(읽기 호출·출력에만 이름·명령 문장에만 "0건")은 그 전 코드에서 실패했다. PR #11 리뷰가 그 수정이 감싸개 실행을 놓친다는 회귀를 잡았고, 그 때문에 더한 셋(감싸개 8가지·감싼 읽기 명령·`재확인 0`)도 리뷰 전 코드에서 실패했다. 리뷰 전 코드는 `bash -c "grep -n x lib/check.sh"`에도 울렸다.
- **설명된 곳**: 훅 머리말 `hooks/zero-guard.sh:2` "검사 스크립트가 0건을 냈을 때 … 상기시킨다". README는 PR #8부터 "zero-count reminder"·"0건 구분 가드"라는 이름과 끄는 변수가 없다는 사실만 적는다(`README.md:279`, `README.ko.md:247`). README 재작성(브랜치 `readme-read-less`)부터는 언제 울리는지도 한 줄로 적는다: 검사 스크립트가 0을 냈을 때, 진짜 없는 것인지 못 센 것인지 가려 말하라고 알린다 — 코드와 일치.
- **어긋남**: 해소됨(2026-11-21, `6b51162`). 전에는 입력 문자열 어디든 스크립트 이름과 "없음"이 같이 있으면 울렸다. 그래서 `{"tool_input":{"command":"cat lib/fresh.sh"},"tool_response":{"stdout":"없음"}}`에도 알림이 났고, 이 지도를 만드는 세션의 읽기 호출 대부분에서 울렸다(거짓 양성). 소유자가 머리말의 뜻대로 코드를 좁히기로 정했다.

## 3. 규칙 판단과 관찰 로그

- **메타**: 상태=해소됨(2026-11-21) · 확인=2026-11-22(`681afff`) · 파일=`lib/rules.py`,`lib/runlog.py`,`hooks/handoff-inject.py`,`commands/baton-explain.md` · 이웃=개념 7(정본) · 문서=`README.md`,`README.ko.md`,`docs/NORTH_STAR.md`

- **정해진 것**: 북극성 길 단계 1(V0 Observe + Explain). `DECISIONS.md`에 따로 된 항목은 없고, 북극성 3절 단계 1 "상태(09-30)"가 구현 완료라고 적는다.
- **실제 동작**:
  - 판단은 MATCHED/AMBIGUOUS/NO_MATCH 셋(`lib/rules.py:58`), 판단 함수 `lib/rules.py:101`, 판정 버전 `rules-v1`(`lib/rules.py:16`). 인계 트리거 정규식의 정본도 여기다(`lib/rules.py:22`).
  - 훅이 프롬프트마다 판단을 `~/.cache/baton/runs.jsonl`에 남긴다. 프롬프트는 원문 대신 해시·길이만(`hooks/handoff-inject.py:99`). 파일 600, 20MB 넘으면 한 번 돌림(`lib/runlog.py:12`, `lib/runlog.py:26`, `lib/runlog.py:28`).
  - 테스트: `lib/test_rules.py` 12개 통과(2026-11-21, PR #10 머지 뒤 실행).
- **설명된 곳**: `README.md:276`, `README.ko.md:244` — 코드와 일치. `docs/NORTH_STAR.md:70`·`docs/NORTH_STAR.md:71`(2절 표).
- **어긋남**: 해소됨(2026-11-21, `6b51162` — 두 칸을 코드대로 고쳤다). 고치기 전 기록: 북극성 2절 표는 Decision Layer 칸에 "인터페이스·**3상태 판정**·Jev·Judge 없음", V0 Observe 칸에 "**없음**. 사후 집계기만"이라 적는다. 같은 문서 3절 단계 1과 코드는 둘 다 있다고 말한다. 2절 표가 10-01 구현을 반영하지 않은 것이다 — **낡은 문서**(코드가 앞서 있다). 같은 표의 다른 칸도 같은 원인으로 낡았다(Fallback 칸은 인계서 주입 절, 개념 지도 점검 칸은 '관련' 가리킴 절에 따로 적었다). 이 표 하나가 여러 개념에서 동시에 낡은 것은 개별 실수가 아니라 **갱신 경로의 구멍**이다 — 구현 커밋이 북극성 2절 표를 갱신 대상에 넣지 않았다.

## 4. 인계서 검사와 제안

- **메타**: 상태=해소됨(2026-11-21) · 확인=2026-11-22(`681afff`) · 파일=`lib/handoff_check.py`,`hooks/handoff-check.py`,`hooks/hooks.json` · 이웃=개념 9(정본), 개념 10(전제), 개념 11(전제) · 문서=`README.md`,`README.ko.md`,`docs/NORTH_STAR.md`

- **정해진 것**: `DECISIONS.md` 10-01 "beta v1.0 범위" — 길 단계 3의 인계서 검사기와 결정론 트리거를 넣는다(소유자).
- **실제 동작**:
  - 검사기: 필수 8절(`lib/handoff_check.py:23`)·200줄·9,000자·긴 코드 블록·전체 diff·비밀값·홈 절대경로(`lib/handoff_check.py:46`)·개인 자료 목록(`lib/handoff_check.py:58`). 훅 모드에서는 baton 형식으로 보이는 인계서에만 필수 절을 요구한다(`lib/handoff_check.py:115`). PR #6부터 "확인된 사실과 결정" 목록 줄에 [V]·[?] 표시가 없으면 막지 않고 경고만 한다(`lib/handoff_check.py:120`).
  - `HANDOFF.md`를 `Write|Edit|MultiEdit`한 직후 검사(`hooks/handoff-check.py:34`, `hooks/hooks.json:28`), 문제가 있으면 모델에 돌려준다.
  - 제안: `Stop`에서만, 마지막 인계서 저장 뒤 다른 파일을 3개 이상 고쳤으면 세션에 한 번(`hooks/handoff-check.py:99`, `hooks/handoff-check.py:110`, `hooks/handoff-check.py:117`). `SessionEnd`에는 등록돼 있지 않다.
  - 테스트: `lib/test_handoff_check.py` 31개 + `hooks/test_handoff_check_hook.py` 13개 통과(2026-11-21, PR #6 머지 뒤 실행). 이 저장소의 루트 `HANDOFF.md`도 검사기를 통과한다("문제 없음").
- **설명된 곳**: `README.md:73`·`README.md:78`, `README.ko.md:61`·`README.ko.md:66` — PR #14(검사 상한 8,700자)·PR #15(이름 붙은 인계서)가 머지된 뒤의 동작을 적는다. 그 둘이 머지되기 전의 main 코드와는 그 두 군데가 다르다(9,000자, `HANDOFF.md`만 셈). `docs/NORTH_STAR.md:134`·`docs/NORTH_STAR.md:136`.
- **어긋남**: 북극성 단계 3 본문(`docs/NORTH_STAR.md:136`)이 결정론 트리거를 "`Stop`·`SessionEnd` 훅에서"라고 적는다. 바로 위 상태 줄(`docs/NORTH_STAR.md:134`)은 "`SessionEnd` 대신 `Stop`만"이라 하고 코드도 `Stop`만이다 — 같은 절 안에서 서로 다르다. 상태 줄의 "테스트 18개"는 10-01 커밋 `8834a01` 기준 검사기 테스트만 센 값이고, 지금은 20 + 11개다. **낡은 문서** → 해소됨(2026-11-21, `6b51162`). 두 줄을 "`Stop`만"과 테스트 수로 고쳤다. 처음 고친 수(31개)는 작업하는 사이 PR #6이 머지되면서 바로 낡았다. 이 지도의 `fresh.sh`가 이 개념을 재확인으로 올려서 알았고, 44개(검사기 31·훅 13)로 다시 고쳤다. 날짜를 붙여 둔 이유다.

## 5. 세션 끊기 알림

- **메타**: 상태=해소됨(2026-11-21) · 확인=2026-11-22(`681afff`) · 파일=`hooks/split-notice.py`,`hooks/hooks.json` · 이웃=개념 10(전제) · 문서=`README.md`,`README.ko.md`,`docs/NORTH_STAR.md`

- **정해진 것**: `DECISIONS.md` 09-30 "토큰 효율은 세션 끊기를 먼저 한다"(소유자). 문턱 2배·3배와 "권고만"은 세션의 구현 기본값.
- **실제 동작**: `Stop`에서 세션 기록의 첫 호출 맥락과 마지막 호출 맥락을 비교해(`hooks/split-notice.py:19`) 문턱(기본 `2,3`, `hooks/split-notice.py:64`)을 처음 넘을 때만 알린다(`hooks/split-notice.py:92`, `hooks/split-notice.py:103`). `hooks/hooks.json:54`에 등록. 테스트 `hooks/test_split_notice.py` 12개 통과(2026-11-21 실행).
- **설명된 곳**: `README.md:78`, `README.ko.md:66` — 코드와 일치. `docs/NORTH_STAR.md:101`.
- **어긋남**: 북극성 단계 S 상태 줄(`docs/NORTH_STAR.md:101`)이 "테스트 7개"라 적는다. 공개 이력 첫 커밋 `9a7915c`(10-01)에서 이미 12개였다. 날짜가 박힌 상태 줄이라 그날 값일 수 있지만, 공개 이력 어디에서도 7개였던 적이 없다. **낡은 문서**(낮음) → 해소됨(2026-11-21, `6b51162`, "12개, 11-21 기준").

## 6. 메타 줄과 낡음 계산

- **메타**: 상태=해소됨(2026-11-21) · 확인=2026-11-22(`681afff`) · 파일=`lib/concepts.py`,`lib/fresh.sh`,`lib/check.sh`,`lib/lib.sh`,`hooks/drift-notice.sh`,`lib/test_fresh.py`,`hooks/test_drift_notice.py` · 이웃=개념 8(전제) · 문서=`README.md`,`README.ko.md`,`skills/driftmap/SKILL.md`

- **정해진 것**: 결정 기록에 따로 없다. 스킬 문서(`skills/driftmap/SKILL.md`)가 규칙의 정본 역할을 한다.
- **실제 동작**:
  - 형식을 아는 곳은 파서 하나다(`lib/concepts.py:22`, `lib/concepts.py:27`, `lib/concepts.py:70`). 숫자 없는 `#`·`##` 제목은 개념 절을 닫는다(`lib/concepts.py:24`). 단 ```·~~~ 코드 펜스 안의 줄은 제목으로 보지 않는다(`lib/concepts.py:26`, `lib/concepts.py:53`). 펜스가 열린 채 파일이 끝나면 `warnings`가 알린다(`lib/concepts.py:195`). 정상으로 닫힌 펜스 안의 `## N.` 예시는 개념이 아니라서 알리지 않는다. `check.sh`는 이를 검사 [7]의 지적으로 세고, `fresh.sh`는 표 위에 `주의:`를 낸다(`lib/fresh.sh:102`). 세션 시작 알림은 재확인이 0건이어도 이때 울린다. 메타 줄의 `문서` 항목도 읽는다(`lib/concepts.py:126`).
  - 판정은 커밋 수(`lib/fresh.sh:149`)·기준 없음·기준 소실(`lib/fresh.sh:117`)·**기준이 현재 이력 밖**(`lib/fresh.sh:118`, HEAD의 조상이 아닌 확인 커밋)·경로 소실·미추적(`lib/fresh.sh:47`)·신선(`lib/fresh.sh:162`)·규칙 개념(`lib/fresh.sh:131`)에 **문서 커밋**(`lib/fresh.sh:64`, `lib/fresh.sh:158`)이 더해졌다. 표 끝에 요약 줄이 붙는다(`lib/fresh.sh:166`).
  - 경로는 쉼표로만 나눠 배열에 담고(`lib/fresh.sh:34`) 따옴표째 git에 넘긴다. 그래서 공백이 든 경로가 쪼개지지 않고, 글롭은 셸이 아니라 git이 저장소 루트 기준으로 맞춘다. 사라진 경로(코드든 문서든, 일부만이라도)는 신선으로 두지 않는다. 그 경로도 `git log` 대상에 넣어 지우거나 옮긴 커밋을 센다(`lib/fresh.sh:156`). 규칙 개념의 확인 해시가 없으면 `(기준 없음 — 문서 못 봄)`을 붙인다(`lib/fresh.sh:130`). 적어 둔 해시가 소실·이력 밖이면 결정 변동도 셀 수 없으니 `재확인 필요 — 기준 소실 (규칙 개념)`으로 올려 세션 알림이 울리게 한다(`lib/fresh.sh:127`).
  - 세션 시작 알림은 개념 수·메타 줄 수를 grep이 아니라 파서로 세고, 판정은 표의 글자 대신 그 요약 줄을 읽는다(`hooks/drift-notice.sh:61`, `hooks/drift-notice.sh:66`, `hooks/drift-notice.sh:67`). 캐시 키에 `fresh.sh`가 들어 있다(`hooks/drift-notice.sh:44`).
  - `check.sh`의 검사는 [1]~[6] 여섯 가지다(마지막 둘은 '파일' 항목의 지침 파일 섞임과 메타 줄 수).
  - 테스트 `lib/test_fresh.py` 32개(문서 항목 6·파서 2 추가, 리뷰 반영 8 추가, 후속 6 추가, 마지막 후속 2 추가 — 하나는 바꿈), `hooks/test_drift_notice.py` 7개 통과(2026-11-21 실행). 후속 6개(열린 펜스 경고 둘·제목 수 차이·규칙 개념 기준 소실·판정 문서 둘)와 알림 1개는 그 전 코드에서 실패했다. 처음 고칠 때 넣은 문서 항목 5개·파서 1개·이름 속 '신선' 1개는 그 전 코드에서 실패했다. 리뷰 반영으로 넣은 8개(이름 바뀐 문서·없는 문서 경로·일부 사라진 코드 경로·이력 밖 기준·공백 경로·글롭·규칙 개념의 문서 못 봄·펜스)도 리뷰 전 코드에서 모두 실패했다.
- **설명된 곳**: `README.md:133`·`README.md:138`·`README.md:150`, `README.ko.md:102`·`README.ko.md:107`·`README.ko.md:119`, `skills/driftmap/SKILL.md:251`, `skills/driftmap/SKILL.md:259`, `skills/driftmap/SKILL.md:314`, `skills/driftmap/SKILL.md:167`.
- **어긋남** (모두 해소됨):
  - 해소됨(2026-11-21, `7954eef`) — **PR #11 독립 리뷰가 잡은 것들.** 처음 수정에서 생기거나 남은 것이다. 펜스 안 `# 주석`에서 개념 절이 닫혔다(그 수정이 만든 회귀). 문서 이름을 바꾸거나 지우면 `신선 (문서 경로 소실 N개)`로 끝나고 세션 시작 알림도 울리지 않았다. 다른 가지의 커밋을 기준으로 두면 신선으로 나왔다. 공백이 든 경로가 쪼개졌고, 글롭이 지금 폴더 기준으로 펼쳐졌다. 규칙 개념은 기준이 없을 때 문서를 못 본다는 말이 없었다. 리뷰의 재현 저장소 셋으로 다시 돌려 모두 맞게 나오는 것을 확인했다.
  - 해소됨(2026-11-21, `d0c3642`) — **후속 점검(PR #11 재검증)에서 남은 것.** 펜스가 열린 채 끝나면 그 뒤 개념이 경고 없이 사라졌다(재현 저장소 t4). README의 판정 설명은 "여섯 가지"였는데 스킬 문서는 "아홉 가지"였다 — 이제 README·README.ko·스킬 문서가 같은 아홉 가지를 적고, 테스트(`VerdictDocsTest`)가 `fresh.sh`의 판정 이름과 두 문서를 맞춰 본다. 규칙 개념의 기준 소실은 세션 알림이 안 울렸다.
  - 해소됨(2026-11-21, `7c71c9d`) — **마지막 후속(재현 저장소 t6).** 닫힌 펜스 안의 `## 2.` 예시가 제목 수 차이 경고를 냈다. 세션 알림도 grep으로 세어, 펜스 안 예시까지 개념으로 친 틀린 개수("메타 줄이 모자란다")를 매 세션 냈다. 경고는 열린 채 끝난 펜스에만 남겼고, 알림은 파서로 센다.
  - **관찰(낮음, 고치지 않음)**: 커밋 수는 `git log <확인>..HEAD -- <파일>` 그대로라서 merge commit도 한 건으로 센다. PR #10을 merge한 뒤 시험해 보니 #10과 그 merge가 둘 다 세어져 "문서 커밋 2건"이 됐다. 판정(재확인인지 아닌지)은 맞고 건수만 부푼다. `--no-merges`로 바꿀지는 merge 방식을 정한 뒤에 정한다.
  - 해소됨(2026-11-21) — README 첫 화면의 데모 출력이 상태로 `구현됨`을 보여 줬다(닫힌 어휘 밖). README를 다시 쓰면서 스크래치 폴더의 임시 데모 저장소에서 `fresh.sh`를 실제로 다시 돌린 출력으로 바꿨다(`README.md:114`~`README.md:120`, `README.ko.md:80`~`README.ko.md:86`). 상태는 `일치`·`미구현`이고 요약 줄도 들어 있다. 영어판 표(`README.md:92`~`README.md:98`)는 그 출력의 번역이다.
  - 해소됨(2026-11-21) — **README의 메타 줄 예시가 이 스킬의 규칙을 어긴다(중간).** `README.md:133`·`README.ko.md:102`의 예시는 `상태=구현됨`인데, `구현됨`은 닫힌 상태 어휘 여덟 개에 없다. 이 예시를 그대로 베낀 지도는 `check.sh` 검사 [4]에서 지적을 받는다. 같은 예시의 `파일=`에는 문서(`docs/guide.md`)가 들어 있어서, `파일`에는 실제 동작 근거만 둔다는 규칙과도 어긋난다. PR #3에서 들어왔고 PR #8 뒤에도 그대로다. 사용자가 가장 먼저 베끼는 줄이라 이 개념에서 가장 무거웠다. `상태=일치`, `문서=`docs/guide.md``로 고쳤다. 스킬 문서의 예시(`ROADMAP.md`를 `파일`에 넣음)도 같이 고쳤다.
  - 해소됨(2026-11-21) — 판정 수: `skills/driftmap/SKILL.md:314`는 "여섯 가지"라 하는데 코드에는 규칙 개념 판정이 하나 더 있다. README는 PR #8부터 여섯 판정 뒤에 규칙 개념을 따로 설명한다(`README.md:150`, `README.ko.md:119`). 그래서 README 쪽은 코드와 맞고, 스킬 문서만 남아 있었다. 지금은 스킬 문서가 규칙 개념·문서 판정을 표에 더해 여덟 가지로 적는다.
  - 해소됨(2026-11-21) — **문서 쪽 근거는 신선도가 안 본다(미구현).** 스킬 문서는 메타 줄에 `문서` 항목을 두고 "신선도에서 낮은 우선순위로 본다"고 적는다(`skills/driftmap/SKILL.md:99`). 하지만 파서와 `fresh.sh`에는 `문서` 항목을 읽는 코드가 없다. 그래서 PR #8이 README를 통째로 다시 쓴 뒤에도 `fresh.sh`는 12개 모두 신선으로 냈다. 이 지도의 "설명된 곳"에 적은 README 줄 번호 21개(서로 다른 파일:줄 기준)가 전부 다른 줄을 가리키고 있었고, 손으로 다시 찾아 맞췄다(2026-11-21). 이제 `fresh.sh`가 `문서` 항목의 파일이 움직이면 `재확인 필요 — 문서 커밋 N건`을 낸다. 이 지도의 메타 줄에도 `문서=`를 채웠다. 회귀 확인: 이 지도의 확인 해시를 PR #8 직전(`5c185bd`)으로 되돌린 사본을 돌리면, README를 `문서`로 둔 개념이 모두 문서 커밋 재확인으로 뜬다.
  - 해소됨(2026-11-21) — `check.sh` 검사 수: 스킬 문서가 표에서는 "여섯 가지"(`skills/driftmap/SKILL.md:251`), 바로 아래 본문에서는 "다섯 가지를 본다"(`skills/driftmap/SKILL.md:259`)라 적고 다섯만 나열한다. 코드는 여섯.
  - 해소됨(2026-11-21) — 간선 종류: 절 제목은 "네 종류"(`skills/driftmap/SKILL.md:167`)인데 표에는 셋(전제·정본·공유파일)뿐이다.
- **이번에 함께 찾은 잠복 결함 둘** — 둘 다 해소됨(2026-11-21, `6b51162`, 회귀 테스트 있음):
  - 파서는 숫자 없는 `##` 절을 마지막 개념 절의 본문으로 읽는다(고치기 전 `walk`). 스킬이 권하는 산출물 구성(일치 확인된 것·확인하지 못한 것·유지 규칙을 개념 뒤에 둔다)을 따르면 그 절들이 마지막 개념에 붙는다. 그러면 그 절들 속 "개념 N" 언급이 마지막 개념의 참조로 세어지고, 실험 기능 개념 주입은 마지막 개념을 고르면 뒤 절까지 함께 넣는다. 이 지도로 재면(2026-11-21) 마지막 개념 자체는 8줄·591자인데 주입 텍스트는 뒤 절을 포함해 1,970자다 — 2,000자 상한을 겨우 넘지 않아 실제로 들어간다. 이 지도는 그것을 피하려고 뒤 절에서 개념을 번호 대신 이름으로 불렀다. 지금은 숫자 없는 `##` 제목에서 절이 닫힌다.
  - 세션 시작 알림은 `fresh.sh` 출력에서 `신선`이 들어간 줄을 센다(고치기 전 줄 53). 개념 이름에 "신선"이 들어 있으면 그 줄이 판정과 상관없이 신선으로 세어진다. 이 지도는 그래서 이 절 이름을 "낡음 계산"으로 지었다. 고친 뒤 `fresh.sh`에 요약 줄이 붙었는데, 그 줄에도 "신선"이 들어 있어서 옛 방식이었다면 더 틀렸을 것이다(테스트에서 `신선 2건`으로 재현).

## 7. 인계서 on-demand 주입

- **메타**: 상태=해소됨(2026-11-21) · 확인=2026-11-22(`681afff`) · 파일=`hooks/handoff-inject.py`,`lib/rules.py`,`hooks/hooks.json` · 이웃=개념 3(정본), 개념 9(정본), 개념 10(전제) · 문서=`README.md`,`README.ko.md`,`docs/NORTH_STAR.md`

- **정해진 것**: `DECISIONS.md` 09-27 "인계서 주입은 on-demand, 200줄·9,000자"(세션 판정, 200줄은 09-22 소유자 결정).
- **실제 동작**:
  - `UserPromptSubmit`에서 프롬프트가 트리거 말(`lib/rules.py:22`, 설정의 추가 말 포함 — PR #10부터 "where were we" 같은 영어 구도 들어간다)에 맞을 때만 주입(`hooks/handoff-inject.py:73`, `hooks/handoff-inject.py:77`). 무관한 프롬프트에는 넣지 않는다.
  - 출력은 Claude Code·Codex 둘 다 받는 JSON `additionalContext`.
  - git이 없을 때: 저장소 루트 계산이 예외를 삼키고 폴더 기준으로 넘어간다(`lib/rules.py:145`, `lib/rules.py:151`). 2026-11-21에 git이 없는 `PATH`로 `handoff-inject.py`·`split-notice.py`·`handoff-check.py`를 돌렸을 때 셋 다 종료 코드 0, 출력 없음.
  - 테스트 `hooks/test_handoff_inject.py` 8개 통과(2026-11-21 실행).
- **설명된 곳**: `README.md:74`·`README.md:76`·`README.md:77`, `README.ko.md:62`·`README.ko.md:64`·`README.ko.md:65` — PR #16(한 세션에 한 번, 사람이 친 프롬프트만)과 PR #19(브랜치 `handoff-freshness`, 머리말 뒤 신선도 한 줄, 훅 출력 상한 10,000자 기준 예산)이 머지된 뒤의 동작을 적는다. 그 둘이 머지되기 전의 main 코드는 매 트리거 프롬프트에 넣고 신선도 줄이 없다. `docs/NORTH_STAR.md:83`.
- **어긋남**: 북극성 2절 표 Fallback 칸(`docs/NORTH_STAR.md:83`)이 "다만 조용하지는 않다 — git을 못 찾으면 traceback을 낸다"고 적는다. 위 실행으로는 traceback이 나지 않는다. **낡은 문서**(낮음) → 해소됨(2026-11-21, `6b51162`). 규칙 판단 절에 적은 것과 같은 표, 같은 원인이다.

## 8. 새 결정의 '관련' 가리킴

- **메타**: 상태=미결 · 확인=2026-11-22(`681afff`) · 파일=`lib/fresh.sh`,`lib/concepts.py` · 이웃=개념 6(전제) · 문서=`skills/driftmap/SKILL.md`,`docs/NORTH_STAR.md`

- **정해진 것**: 결정 기록에 따로 없다. 스킬 문서 모드 ④ "결정이 움직였는가"가 미구현을 잡는 유일한 경로라고 적는다.
- **실제 동작**: 메타 줄의 확인 해시 이후 `DECISIONS.md`에 새로 들어온 줄 중 `관련` 뒤의 "개념 N"·개념 이름을 찾아 그 개념을 재확인으로 올린다(`lib/fresh.sh:73`, `lib/concepts.py:33`, `lib/concepts.py:161`). 못 이은 것은 "0건이 아니라 못 셌다"로 따로 낸다. 새 결정 중 `- 관련:` 줄이 없는 것을 구멍으로 센다(`lib/fresh.sh:197`). 확인 커밋이 HEAD의 조상이 아니면 `DECISIONS.md` 비교를 하지 않는다 — 비교할 기준이 없어서다.
- **설명된 곳**: `skills/driftmap/SKILL.md` 모드 ④, `docs/NORTH_STAR.md:78`.
- **어긋남**:
  - 북극성 2절 표 개념 지도 점검 칸(`docs/NORTH_STAR.md:78`)이 "새 결정 → 재확인(09-30, **커밋 전**)"이라 적는다. 공개 이력 첫 커밋부터 커밋돼 있다. **낡은 문서**(낮음) → 해소됨(2026-11-21, `6b51162`).
  - **남음 — 갱신 경로의 구멍**(대신 채우지 않음, 그래서 이 개념의 상태가 `미결`): `DECISIONS.md` 16개 항목 중 09-22 "인계서 상한 200줄"과 09-22 "진실 신호 없이 라우팅 후보는 시험하지 않는다" 두 항목에 `- 관련:` 줄이 없다. 이 둘이 어느 개념을 건드렸는지는 결정한 사람이 적는다. 특히 앞의 것은 인계서 상한 개념의 "정해진 것"이다.
  - 이 저장소 `DECISIONS.md`의 `관련:` 줄은 개념 번호 대신 파일 경로를 쓴다. 이 지도가 생겼으니 앞으로는 경로에서 개념을 역산할 수 있다(스킬 절차 4).

## 9. 인계서 상한 200줄·9,000자

- **메타**: 상태=일치 · 확인=2026-11-22(`681afff`) · 파일=`hooks/handoff-inject.py`,`lib/handoff_check.py`,`skills/baton/SKILL.md` · 이웃=개념 4(정본), 개념 7(정본) · 문서=`README.md`,`README.ko.md`,`docs/NORTH_STAR.md`

- **정해진 것**: `DECISIONS.md` 09-22 "인계서 상한 200줄"(소유자, 이유 칸 비어 있음) · 09-27 "인계서 주입은 on-demand, 200줄·9,000자"(9,000자는 실측: 20,826자는 Claude Code가 파일로 뺐다).
- **실제 동작**: 주입 훅 `hooks/handoff-inject.py:24`·`hooks/handoff-inject.py:25`, 검사기 `lib/handoff_check.py:18`·`lib/handoff_check.py:19` — 네 상수 모두 200·9000. 주입은 넘치면 자르고 잘랐다고 한 줄 붙인다(`hooks/handoff-inject.py:85`).
- **설명된 곳**: `skills/baton/SKILL.md:94`, `README.md:73`·`README.md:75`, `README.ko.md:61`·`README.ko.md:63`(검사 상한 8,700자는 PR #14, 훅 출력 전체 10,000자 상한 안에 통째로 들어간다는 것은 PR #19 머지 뒤의 동작. 그 전 main은 검사기 9,000자·주입 9,000자), `docs/NORTH_STAR.md` 1절("Handoff ≤ 200줄").
- **어긋남**: 없음. 값이 코드 두 곳에 따로 박혀 있어(하나를 바꾸면 다른 하나는 그대로) 나중에 갈라질 수 있는 자리다 — 지금은 같다.

## 10. 설정 파일과 우선순위

- **메타**: 상태=일치 · 확인=2026-11-22(`681afff`) · 파일=`lib/config.py`,`lib/setup_scan.py` · 이웃=개념 4·5·7(전제) · 문서=`README.md`,`README.ko.md`,`skills/baton-setup/SKILL.md`,`commands/baton-setup.md`

- **정해진 것**: 결정 기록에 따로 없다(`/baton-setup`은 커밋 `24e3996`에서 들어왔다).
- **실제 동작**: `lib/config.py:119` — 환경변수 > 저장소 절 > 전역 절 > 기본값. 관찰 로그 키 둘은 전역만(`lib/config.py:22`). 목록 키는 전역 + 저장소(`lib/config.py:132`). 테스트 `lib/test_config.py` 23개 통과(2026-11-21 실행). 세션 끊기 문턱·인계서 제안 문턱·추가 트리거 말·각 훅의 끄기 스위치가 모두 이 설정을 읽는다.
- **설명된 곳**: `README.ko.md:145`, `README.md:176`, `skills/baton-setup/SKILL.md`, `commands/baton-setup.md`.
- **어긋남**: 없음.

## 11. 공개 경계 — 개인 자료

- **메타**: 상태=일치 · 확인=2026-11-22(`681afff`) · 파일=`.gitignore`,`lib/handoff_check.py` · 이웃=개념 4(전제) · 문서=`README.md`,`README.ko.md`,`docs/NORTH_STAR.md`

- **정해진 것**: `DECISIONS.md` 10-01 "북극성 정본 원문과 사례 모음은 공개 저장소에 올리지 않는다" · 10-01 "개인 자료가 섞인 공개 이력을 새 이력 하나로 바꾼다"(공개 전 검사는 실명·프롬프트 원문·다른 저장소 내용·절대경로·커밋 이력까지 본다). 둘 다 소유자.
- **실제 동작**: `.gitignore`가 `docs/north-star/`와 `observer/research/cases.json`을 뺀다. 인계서 검사기는 홈 절대경로와 사용자가 고른 개인 자료 단어를 막고, 찾은 값 자체는 출력하지 않는다(`lib/handoff_check.py:46`, `lib/handoff_check.py:58`). 관찰 로그는 프롬프트 원문을 남기지 않는다(`hooks/handoff-inject.py:99`).
- **설명된 곳**: `docs/NORTH_STAR.md` 0절(정본 경로는 소유자 로컬 기준이라고 밝힘), `README.md:276`, `README.ko.md:144`·`README.ko.md:244`.
- **어긋남**: 없음. `docs/NORTH_STAR.md`의 정본 경로 표는 공개판에 없는 파일을 가리키지만, 바로 아래에 "공개 저장소에는 없다"고 밝혀 두었다 — 끊어진 참조가 아니라 의도된 것.

## 12. 결정 기록은 사람이 쓴다

- **메타**: 상태=일치 · 확인=2026-11-22(`681afff`) · 파일=`lib/promote.sh`,`commands/promote.md`,`skills/baton/SKILL.md` · 이웃=없음 · 문서=`README.md`,`README.ko.md`

- **정해진 것**: `DECISIONS.md` 머리말 — "이유 칸이 비어 있는 것은 기록이 없어서다, 추측으로 채우지 않았다". 항목마다 결정 주체(소유자/세션 판정)를 적는다.
- **실제 동작**: `lib/promote.sh`는 과거 인계서를 날짜당 한 판씩 읽어(`lib/promote.sh:38`) 서로 다른 3일 이상 살아남은 항목을 후보로 출력만 한다(`lib/promote.sh:9`, `lib/promote.sh:50`). 파일을 쓰지 않는다. 명령 문서는 "버린 대안·이유는 빈칸으로"(`commands/promote.md:11`).
- **설명된 곳**: `README.md:79`, `README.ko.md:67`, `skills/baton/SKILL.md`의 "승격은 제안까지만 한다".
- **어긋남**: 없음. 실제 `DECISIONS.md`도 이 규칙을 지킨다 — 이유를 모르는 항목은 "(기록 없음)"으로 비어 있다.

## 일치 확인된 것

근거는 각 개념 절의 실제 동작 면에 있다. 여기에는 따로 대조해 맞았던 것만 모은다.

- 테스트 230개 통과(2026-11-21, `7c71c9d`에서 `python3 -m unittest discover -s` 네 묶음: hooks 54·lib 120·tools 8·observer/research 48, 건너뜀 3). macOS 기본 bash 3.2로도 `lib/test_fresh.py`·`hooks/test_drift_notice.py`를 돌려 통과했다.
- 매니페스트 세 곳의 버전이 같다(`1.0.0-beta.2`).
- README의 명령 표 다섯 줄(`README.md:158`, `README.ko.md:127`)은 `commands/` 파일 다섯 개와 맞는다. 훅 등록은 `hooks/hooks.json`에 스크립트 다섯 개다.
- 인계서 템플릿의 8절(`skills/baton/SKILL.md` 템플릿)과 검사기의 필수 절 목록이 같다.
- 루트 `HANDOFF.md`는 검사기를 통과한다(49줄, "문제 없음"). 이 작업은 그 파일을 고치지 않았다.

## 폐기된 개념

없음(최초 생성).

## 확인하지 못한 것

- **Linux에서의 동작.** 모든 실행은 macOS에서 했다.
- **Codex에서 스킬 이름이 어떻게 보이는지.** 플러그인 구성 절의 이름 충돌은 Claude Code 목록에서만 봤다.
- **지도의 링크 자리.** 스킬은 매 세션 읽히는 `AGENTS.md`(또는 `CLAUDE.md`)에서 이 지도를 한 줄로 가리키라고 한다. 이 저장소에는 둘 다 없어서 링크를 걸지 않았다(README에 걸지는 소유자 판단). 세션 시작 훅은 저장소 최상위 두 단계 안의 `CONCEPTS.md`를 스스로 찾으므로 신선도 알림은 링크 없이도 돈다.
- **결정 기록의 이유 칸.** 비어 있는 이유는 추측하지 않았다.
- **새 0건 상기 훅의 실제 세션 동작.** 테스트는 Claude Code 형식의 입력(`tool_response`가 `stdout`·`stderr` 객체)과 문자열 응답으로 했다. Codex의 실제 PostToolUse 입력으로는 돌려 보지 않았다.

## 유지 규칙

- 먼저 `/drift`(모드 ④)를 돌린다. 재확인 대상이 없으면 열지 않는다.
- 재확인 대상만 다시 대조하고, 대조한 개념의 메타 줄 `확인=`을 그때의 커밋으로 옮긴다. 지도와 코드를 한 커밋에서 같이 고쳤다면 다음 커밋에서 옮긴다.
- 어긋남을 고쳐 닫으면 지우지 말고 상태를 `해소됨(날짜)`로 바꾼다.
- `파일`에는 코드·테스트·산출물만 적는다. `DECISIONS.md`·`HANDOFF.md`·`README.md`는 넣지 않는다(설명된 곳이나 정해진 것의 출처다).
- 간선은 전제·정본만, 양쪽에 적는다. 공유파일 관계는 적지 않는다.
- `문서`에는 그 개념을 설명하는 README·스펙·스킬 문서를 적는다. 문서만 움직이면 `fresh.sh`가 문서 커밋 재확인으로 알린다. 그때는 "설명된 곳" 면의 줄 번호만 다시 맞추면 된다.
