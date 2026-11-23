# baton 개념 지도

> 작성: 2026-11-21 · 기준 커밋 `7c71c9d`(마지막 후속 PR의 마지막 코드 커밋. merge commit으로 main에 들어가 해시가 남는다) · driftmap 스킬 모드 ①(최초 생성) → 같은 날 모드 ③(갱신)
> **이 지도는 탐색 앵커다. 실제 코드·결정과 다르면 실제가 정답이다.** 다르다는 것을 찾으면 이 지도를 고친다.
> 정해진 것의 출처는 `DECISIONS.md`, 실제 동작의 출처는 코드와 테스트 실행 출력, 설명된 곳은 `README.md`·`docs/NORTH_STAR.md`·스킬 문서다.
> 2026-11-21 같은 날 PR #3·#5·#8이 머지될 때마다 다시 대조했다. 코드 근거는 `fresh.sh`가 재확인으로 올린 개념만 다시 봤다. README 줄 번호는 `fresh.sh`가 보지 않아서 손으로 다시 맞췄다(메타 줄과 낡음 계산 절). README를 두 기둥(인계서·개념 지도) 중심으로 다시 쓴 뒤(브랜치 `readme-read-less`) 줄 번호를 다시 맞췄다.
> 2026-11-21 개념 그래프 이식(`a80a5fd` — 조립기·후보 루프를 `compiler-shadow`에서 main으로) 뒤 `fresh.sh`가 12개 모두를 재확인으로 올렸다. 12개를 다시 대조해 줄 번호를 맞추고 확인 해시를 옮겼고, 맥락 조립기·개념 후보 루프 두 절을 더했다. 리뷰 수정(`6695701`) 뒤 다시 올라온 다섯(1·6·8·13·14)도 다시 대조했다.
> 2026-11-23 영어 UI 병합(`english-ui`, `067a23e` — 영어 메시지·`BATON_LANG`, Stop 때 인계서 자동 갱신, 저장 때 빠진 줄 경고·필독 표시, 두 언어 파일 형식, 1.0.0-beta.4) 뒤 `fresh.sh`가 15개 모두를 재확인으로 올렸다. 15개를 `067a23e`에 대고 다시 대조해 줄 번호·수치를 맞추고, 동작이 바뀐 곳만 사실을 더하고, 확인 해시를 옮겼다. 상태가 바뀐 것: 개념 4(→ 낡은 문서, 북극성 단계 3이 자동 갱신을 모른다), 개념 10(→ 낡은 문서, 가이드의 언어 순서에 macOS 언어 목록이 없다), 개념 6(→ 해소됨, 스킬 문서가 일곱 가지로 고쳐졌다), 개념 2(해소 날짜 → 11-23, 출력 구조로 판단).
> 2026-11-24 사용자에게 보이는 알림을 해요체·쉬운 영어로 다시 쓴 뒤(`386d152` — 세션 끊기·인계서 제안·자동 갱신 끝 줄·0건 가드 사용자 줄·세션 시작 알림, 가이드·CHANGELOG 문구 `57f690d`·`b5f6ec7`) `fresh.sh`가 14개를 재확인으로 올렸다(코드 커밋 4·문서 커밋만 10). `b5f6ec7`에 대고 다시 대조해 옛 알림 문구를 옮겨 적은 곳(개념 2·4·5·6)을 고치고 훅 줄 번호를 맞췄다. 상태가 바뀐 개념은 없다. 문서 커밋만 걸린 10개는 줄 번호와 주장을 다시 봤고 그대로였다(바뀐 문서 줄은 이 열 개념이 가리키지 않는 줄이다 — README 카드 실험 행, 가이드 데모 알림, "하던 일" 문구).
> baton이 자기 자신에게 driftmap을 적용한 사례다. 처음 판(PR #7)은 어긋남을 **찾기만 하고 고치지 않았다**. 소유자 승인 뒤 같은 날 고쳤다(`6b51162`). 고친 항목은 지우지 않고 `해소됨(2026-11-21)`으로 남겼다(스킬 절차 7).

## 요약

| # | 개념 | 상태 | 심각도 | 한 줄 |
|---|---|---|---|---|
| 1 | 플러그인 구성과 스킬 이름 | 중복 정본 | 중간 | 스킬 두 개가 폴더 이름(`driftmap`·`baton`)과 frontmatter 이름(`ontology`·`handoff`)을 따로 가진다. 공개 이름이 바뀌는 일이라 고치지 않고 선택지만 적었다 |
| 4 | 인계서 검사와 제안 | 낡은 문서 | 낮음 | Stop 훅은 이제 기본으로 에이전트에게 인계서를 갱신하게 하는데(`BATON_HANDOFF_AUTO`), 북극성 단계 3은 "제안(쓰기는 사람 승인)"이라 적는다. 이 결정은 `DECISIONS.md`에 없다(소유자가 정할 일). 트리거·테스트 수는 해소됨(2026-11-21) |
| 8 | 새 결정의 '관련' 가리킴 | 미결 | 낮음 | 결정 2건에 `- 관련:` 줄이 없다(결정한 사람이 채운다). "커밋 전" 표기는 해소됨(2026-11-21) |
| 13 | 개념 색인 | 낡은 문서 | 낮음 | 북극성 2절 표와 단계 2 항목이 이 색인(세션에 한 번, 별칭 없음)을 아직 모른다 |
| 14 | 맥락 조립기 | 미구현 | 낮음 | 결정은 훅에 그림자 모드로 붙이는 것까지인데, main에는 조립기 코드만 있다. 훅 연결은 인계서 주입 훅 정리 뒤로 미뤘다 |
| 10 | 설정 파일과 우선순위 | 해소됨(2026-11-23) | 낮음 | 우선순위(환경변수 > 저장소 절 > 전역 절 > 기본값)는 문서와 코드가 같다. 새 `BATON_LANG`도 같은 순서이고, 가이드의 언어 순서에 macOS 시스템 언어 단계와 좁힌 한국어 판정을 더해 코드와 맞췄다. |
| 2 | 0건과 못 셈의 구분 | 해소됨(2026-11-23) | — | 0건 상기 훅이 스크립트를 실제로 실행했고 그 출력의 구조(요약 줄·못 셈 신호)가 0을 말할 때만 울린다 |
| 3 | 규칙 판단과 관찰 로그 | 해소됨(2026-11-21) | — | 북극성 2절 표가 3상태 판정·판단 로그를 "없음"으로 적던 것을 고쳤다 |
| 5 | 세션 끊기 알림 | 해소됨(2026-11-21) | — | 북극성 단계 S의 테스트 수를 고쳤다 |
| 6 | 메타 줄과 낡음 계산 | 해소됨(2026-11-23) | — | 마지막으로 남았던 스킬 문서의 `check.sh` 검사 수가 "일곱"으로 고쳐졌다(`4c4652a`). 데모 출력·문서 항목·파서·세는 방식·예시·판정 수도 해소됨 |
| 7 | 인계서 on-demand 주입 | 해소됨(2026-11-21) | — | 북극성 2절의 "git을 못 찾으면 traceback"을 실제 동작대로 고쳤다 |
| 9 | 인계서 상한 200줄·9,000자 | 해소됨(2026-11-22) | — | 검사기 8,700자, 훅 출력 9,600자. 검사를 통과한 인계서는 신선도 줄·필독 줄·개념 색인이 붙어도, 영어 머리말이어도 전부 들어간다 |
| 11 | 공개 경계 — 개인 자료 | 일치 | — | 정본 원문·사례 모음은 gitignore, 인계서 검사가 홈 절대경로·개인 자료 단어를 막는다 |
| 12 | 결정 기록은 사람이 쓴다 | 일치 | — | `/promote`는 후보만 내고 `DECISIONS.md`에 쓰지 않는다 |
| 15 | 개념 후보 루프 | 일치 | — | 별칭·새 개념 후보는 저장소 밖 캐시에만, `CONCEPTS.md`에는 사람이 고른 별칭만 들어간다 |

## 1. 플러그인 구성과 스킬 이름

- **메타**: 상태=중복 정본 · 확인=2026-11-24(`d584a7c`) · 파일=`.claude-plugin/plugin.json`,`.codex-plugin/plugin.json`,`.claude-plugin/marketplace.json`,`hooks/hooks.json`,`skills/driftmap/SKILL.md`,`skills/baton/SKILL.md`,`skills/baton-setup/SKILL.md`,`tools/check_versions.py` · 이웃=없음 · 문서=`README.md`,`README.ko.md`,`docs/GUIDE.md`,`docs/GUIDE.ko.md`,`commands/drift.md`

- **정해진 것**: 범위는 `DECISIONS.md` 10-01 "beta v1.0 범위" — ① 1.0.0-beta 버전 표기. 스킬 이름에 대한 결정 기록은 없다.
- **실제 동작**:
  - 버전은 매니페스트 세 곳 모두 `1.0.0-beta.4`(`.claude-plugin/plugin.json:3`, `.codex-plugin/plugin.json:3`, `.claude-plugin/marketplace.json:11`, `f770862`). 서로 일치. PR #9부터 `tools/check_versions.py`가 이 세 곳과 CHANGELOG 맨 위 버전이 같은지 CI에서 본다(2026-11-23 실행: `ok: all versions = 1.0.0-beta.4`).
  - 스킬 셋·명령 다섯·훅 스크립트 다섯이 매니페스트와 `hooks/hooks.json`에 실제로 등록돼 있다(`hooks/hooks.json:4`, `hooks/hooks.json:18`, `hooks/hooks.json:28`, `hooks/hooks.json:54`). Claude Code 매니페스트는 PR #3부터 `hooks` 키 없이 기본 위치를 쓰고, Codex 매니페스트는 그대로 적는다(`.codex-plugin/plugin.json:11`).
  - 2026-11-22: 매니페스트 세 곳의 `description`을 새 소개 문구("새 대화마다 프로젝트를 다시 읽지 않게")로 바꿨다(`681afff`). 버전·스킬·명령·훅 등록은 그대로다(`tools/check_versions.py` ok, `claude plugin validate .` 통과).
  - 2026-11-23(beta.4): 스킬·명령 본문이 영어로 바뀌고 description은 영어·한국어 둘 다 적는다(트리거 말도 두 언어). 스킬 셋과 명령 넷(`drift`·`promote`·`baton-setup`·`baton-doctor`)은 frontmatter `allowed-tools`로 읽기 스크립트를 미리 허용하고, 경로는 중괄호 꼴 `${CLAUDE_PLUGIN_ROOT}`로 적는다(`skills/driftmap/SKILL.md:3`, `skills/baton/SKILL.md:4`, `4c4652a`). 플러그인 아이콘 `.claude-plugin/icon.png`가 더해졌다. `claude plugin validate .` 통과(2026-11-23 실행).
  - 스킬 frontmatter의 `name`은 `skills/driftmap/SKILL.md:2`가 `ontology`, `skills/baton/SKILL.md:2`가 `handoff`, `skills/baton-setup/SKILL.md:2`가 `baton-setup` — beta.4에서도 그대로다.
- **설명된 곳**: `docs/GUIDE.md:78`·`docs/GUIDE.md:226`·`docs/GUIDE.md:332`, `docs/GUIDE.ko.md:68`·`docs/GUIDE.ko.md:290`는 개념 지도 스킬을 `driftmap`으로 부른다(PR #8 이후 README에는 인계서 스킬 이름이 따로 나오지 않는다). `commands/drift.md:10`도 "the `driftmap` skill".
- **어긋남**: 한 스킬에 이름이 둘이다(폴더·README 쪽과 frontmatter 쪽). Claude Code 스킬 목록에는 `baton:driftmap (baton:ontology)`처럼 두 이름이 같이 뜬다. 사용자 수준에 `handoff`·`ontology`라는 이름의 스킬이 따로 있으면 이름이 겹친다 — 이 저장소 소유자 환경에서 실제로 둘이 나란히 목록에 뜬다. Codex에서는 스킬을 이름으로 부르라고 README가 안내하므로 어느 이름이 맞는지가 사용자에게 보이는 문제다. **어느 쪽이 정본인지 소유자가 정해야 한다.** 공개 인터페이스가 바뀌는 일이라 2026-11-21 수정에서는 고치지 않았다. 선택지:
  - 가(추천). frontmatter `name`을 폴더 이름(`driftmap`·`baton`)으로 맞춘다. README·명령 문서·홍보 문구가 이미 이 이름을 쓰고, 흔한 사용자 스킬 이름(`handoff`·`ontology`)과 겹치지 않는다. 대가: Codex에서 `ontology`·`handoff`로 부르던 사람은 이름이 바뀐다(공개 1주 안이라 사용자는 적다).
  - 나. 폴더와 README를 frontmatter 이름으로 맞춘다. README·CHANGELOG·명령 문서를 여러 곳 고쳐야 하고, 사용자 스킬과 계속 겹친다.
  - 다. 그대로 두고 README에 "Codex에서는 `ontology`·`handoff`로 보인다"를 적는다. 바꾸는 것이 없지만 이름이 둘인 상태가 남는다.
  - 상태(2026-11-21): 선택지와 추천은 소유자 확인 단계로 넘어갔다. 후속 PR에서도 고치지 않았다.
  - 상태(2026-11-23 재확인): beta.4에서도 그대로다. 이 재확인 세션의 Claude Code 스킬 목록에도 `baton:driftmap (baton:ontology)`·`baton:baton (baton:handoff)`가 사용자 수준 `handoff`·`ontology` 스킬과 나란히 떴다.

## 2. 0건과 못 셈의 구분

- **메타**: 상태=해소됨(2026-11-23) · 확인=2026-11-24(`d584a7c`) · 파일=`hooks/zero-guard.sh`,`lib/fresh.sh`,`lib/check.sh`,`lib/promote.sh`,`hooks/test_zero_guard.py` · 이웃=없음 · 문서=`README.md`,`README.ko.md`,`docs/GUIDE.md`,`docs/GUIDE.ko.md`

- **정해진 것**: 결정 기록에 따로 없다. 제품의 기본 원칙으로 README와 북극성 "모든 단계에 공통"(못 센 것은 0이 아니라 "못 셌다")에 있다.
- **실제 동작**:
  - 검사 스크립트 자체는 못 센 경우를 따로 낸다 — 메타 줄 0개면 "계산할 수 없다"로 종료 코드 2(`lib/fresh.sh:122`, `lib/fresh.sh:143`), 결정 기록 형식을 못 알아보면 "형식 불명 — 0건이 아니라 못 셌다"(`lib/fresh.sh:289`). 영어 출력에서는 "this is not 0, it could not be counted"다.
  - 훅은 두 조건이 다 맞을 때만 울린다. 첫째, 따옴표를 먼저 푼 뒤 `&&`·`;`·`|`에서 나눈 조각 중 하나가 첫 실행 파일로 `check.sh`·`fresh.sh`·`promote.sh`를 돌린다(`hooks/zero-guard.sh:36`, `hooks/zero-guard.sh:54`). 이때 환경변수 대입과 감싸개(`timeout 60`·`sudo -u x`·`nice -n 5`·`env -u X`·`rtk`·`rtk proxy`·`bash -o pipefail`)는 옵션 값까지 건너뛰고 보고, `bash -c "…"`는 그 문자열 안을 다시 본다(`hooks/zero-guard.sh:62`, `hooks/zero-guard.sh:70`). 명령 문장 속의 "0건"이나 `10건`은 세지 않는다.
  - 둘째 조건은 2026-11-23부터 출력의 구조로 본다(`7c534c1`, 두 언어 출력 모두). ① 못 셈 신호(`메타 줄 0개`·"0건이 아니라 못 셌"·`metadata lines: 0`·`not 0`)는 언제나 울린다(`hooks/zero-guard.sh:96`, `hooks/zero-guard.sh:109`). ② 머리 결과 줄(`fresh.sh` 요약의 `재확인 N`, `check.sh`의 `지적 총 N건`, 영어 `Summary: re-check N`·`Total findings: N`)이 있으면 그것만 본다 — 0이면 울리고, 모두 0이 아니면 나머지 줄의 0은 세부라 울리지 않는다(`hooks/zero-guard.sh:97`, `hooks/zero-guard.sh:111`). ③ 머리 결과 줄이 없으면(`promote.sh` 등) 줄마다 보되, ` · `로 나눈 여러 수 요약 줄에서 0이 아닌 수가 옆에 있는 0은 세지 않는다(`hooks/zero-guard.sh:104`, `hooks/zero-guard.sh:114`). 알림 문장은 출력 언어를 따른다(`hooks/zero-guard.sh:117`). 2026-11-24(`386d152`)부터 사용자에게 보이는 줄(`systemMessage`)과 모델이 읽는 지시(`additionalContext`)를 나눈다 — 사용자 줄은 해요체로 무슨 일인지만 말하고("결과가 0이에요. 정말 없는 건지, 형식이 달라 못 센 건지 AI가 확인하게 했어요.", `hooks/zero-guard.sh:130`), 모델 지시("0건이 나왔다. … 구분해서 보고한다")는 그대로다(`hooks/zero-guard.sh:129`, `hooks/zero-guard.sh:135`). 전에는 같은 지시문을 둘 다에 넣었다.
  - 2026-11-23 실행: 이 지도로 돌린 실제 `fresh.sh` 출력(재확인 15건, `결정·지침 변동: … 커밋 0건` 줄 포함)을 작업 사본의 훅에 넣으면 조용하고, 재확인 0인 요약 줄(`요약: 재확인 0 · 신선 15 · …`)을 넣으면 울린다. 같은 세션에서 설치돼 있던 이전 사본은 그 재확인 15건 출력에 울렸다 — 고치기 전 동작이다.
  - 테스트 `hooks/test_zero_guard.py` 21개 통과(2026-11-23 실행, Python 3.14·3.9 둘 다, 14개에서 늘었다. 2026-11-24 사용자 줄을 나눈 뒤 다시 돌려도 21개). 후속 PR에서 `. lib/fresh.sh`·`source lib/fresh.sh`와 xargs 세 형태를 더했다. xargs는 이미 잡히고 있었고 `.`·`source`는 그 전 코드에서 실패했다. 처음 고칠 때 넣은 넷(읽기 호출·출력에만 이름·명령 문장에만 "0건")은 그 전 코드에서 실패했다. PR #11 리뷰가 그 수정이 감싸개 실행을 놓친다는 회귀를 잡았고, 그 때문에 더한 셋(감싸개 8가지·감싼 읽기 명령·`재확인 0`)도 리뷰 전 코드에서 실패했다. 리뷰 전 코드는 `bash -c "grep -n x lib/check.sh"`에도 울렸다.
- **설명된 곳**: 훅 머리말 `hooks/zero-guard.sh:2` "검사 스크립트가 0건을 냈을 때 … 상기시킨다". README는 PR #8부터 "zero-count reminder"·"0건 구분 가드"라는 이름과 끄는 변수가 없다는 사실만 적는다(`docs/GUIDE.md:366`, `docs/GUIDE.ko.md:324`). README 재작성(브랜치 `readme-read-less`)부터는 언제 울리는지도 한 줄로 적는다: 검사 스크립트가 0을 냈을 때, 진짜 없는 것인지 못 센 것인지 가려 말하라고 알린다 — 코드와 일치(구조 판단도 "0을 냈을 때"에 들어간다).
- **어긋남**: 해소됨(2026-11-21, `6b51162`). 전에는 입력 문자열 어디든 스크립트 이름과 "없음"이 같이 있으면 울렸다. 그래서 `{"tool_input":{"command":"cat lib/fresh.sh"},"tool_response":{"stdout":"없음"}}`에도 알림이 났고, 이 지도를 만드는 세션의 읽기 호출 대부분에서 울렸다(거짓 양성). 소유자가 머리말의 뜻대로 코드를 좁히기로 정했다.
  - 해소됨(2026-11-23, `7c534c1`) — 그 뒤에도 출력 어디든 0 낱말이 있으면 울려서, 재확인 14건인 `fresh.sh` 출력에서 울렸다(개념 이름 "0건과 못 셈의 구분"이 든 표 줄과 `결정·지침 변동: … 커밋 0건` 줄에 걸렸다, `hooks/zero-guard.sh:88`). 머리말("검사 스크립트가 0건을 냈을 때")과 어긋나는 거짓 양성이었다. 위 구조 판단으로 고쳤다.

## 3. 규칙 판단과 관찰 로그

- **메타**: 상태=해소됨(2026-11-21) · 확인=2026-11-24(`d584a7c`) · 파일=`lib/rules.py`,`lib/runlog.py`,`hooks/handoff-inject.py`,`commands/baton-explain.md` · 이웃=개념 7(정본) · 문서=`README.md`,`README.ko.md`,`docs/GUIDE.md`,`docs/GUIDE.ko.md`,`docs/NORTH_STAR.md`

- **정해진 것**: 북극성 길 단계 1(V0 Observe + Explain). `DECISIONS.md`에 따로 된 항목은 없고, 북극성 3절 단계 1 "상태(09-30)"가 구현 완료라고 적는다.
- **실제 동작**:
  - 판단은 MATCHED/AMBIGUOUS/NO_MATCH 셋(`lib/rules.py:93`), 판단 함수 `lib/rules.py:136`, 판정 버전 `rules-v1`(`lib/rules.py:16`). 인계 트리거 정규식의 정본도 여기다(`lib/rules.py:22`).
  - 훅이 프롬프트마다 판단을 `~/.cache/baton/runs.jsonl`에 남긴다. 프롬프트는 원문 대신 해시·길이만(`hooks/handoff-inject.py:302`). 파일 600, 20MB 넘으면 한 번 돌림(`lib/runlog.py:12`, `lib/runlog.py:26`, `lib/runlog.py:28`). 인계서를 넣을 조건인데 건너뛰면 `acted.handoff_skip`에 까닭을 남긴다 — `machine`·`already`, 아니면 null(`hooks/handoff-inject.py:306`). 실제로 넣었을 때만 인계서 나이 `acted.handoff_days`·그 뒤 커밋 수 `acted.handoff_commits_after`를 남기고(`hooks/handoff-inject.py:305`), 건너뛰었거나 못 셌으면 null. 개념 색인은 넣은 글자 수 `acted.concept_index`(안 넣었으면 null)와 까닭 `acted.concept_index_skip`(`off`·`no_map`·`machine`·`already`·`no_memory`·`empty`·`budget`·`error`, `hooks/handoff-inject.py:307`, `hooks/handoff-inject.py:282`) — 개념 색인 절. (`no_memory`는 c1f68c2 때도 코드에 있었는데 이 목록에 빠져 있었다.)
  - 사람이 친 프롬프트가 아닌 것(`<agent-message>`·`<cross-session-message>`·`<task-notification>`으로 시작)은 `MACHINE`(`lib/rules.py:35`)이 가린다. 그런 프롬프트는 판단에서도 개념·작업 종류를 세지 않고 `MACHINE` 상태로 남긴다(0이 아니라 안 셈 — 긴 서브에이전트 보고가 후보를 수십 개씩 만들었다). `explain`(`lib/rules.py:188`)은 훅과 같은 순서(끄기 → 트리거 → 파일 → 기계 프롬프트)로 넣지 않는 까닭을 보여 주고, 넣을 때만 훅과 같은 신선도 한 줄을 붙인다(개념 7). 기계 프롬프트의 작업 종류는 "없음"이 아니라 "세지 않았다"로 적는다.
  - 2026-11-23(beta.4): `explain`은 출력 언어(`BATON_LANG`·로캘 — 설정 파일과 우선순위 절)를 따라 한국어 또는 영어로 낸다 — 한국어 문장은 그대로 두고 영어를 옆에 둔다. 판정 이름(MATCHED 등)과 로그 필드는 언어와 상관없이 같다. 명령 문서 `commands/baton-explain.md`는 영어로 바뀌었다.
  - 테스트: `lib/test_rules.py` 34개 통과(2026-11-23 실행, Python 3.14·3.9 둘 다).
- **설명된 곳**: `docs/GUIDE.md:363`, `docs/GUIDE.ko.md:321` — 코드와 일치. `docs/NORTH_STAR.md:70`·`docs/NORTH_STAR.md:71`(2절 표).
- **어긋남**: 해소됨(2026-11-21, `6b51162` — 두 칸을 코드대로 고쳤다). 고치기 전 기록: 북극성 2절 표는 Decision Layer 칸에 "인터페이스·**3상태 판정**·Jev·Judge 없음", V0 Observe 칸에 "**없음**. 사후 집계기만"이라 적는다. 같은 문서 3절 단계 1과 코드는 둘 다 있다고 말한다. 2절 표가 10-01 구현을 반영하지 않은 것이다 — **낡은 문서**(코드가 앞서 있다). 같은 표의 다른 칸도 같은 원인으로 낡았다(Fallback 칸은 인계서 주입 절, 개념 지도 점검 칸은 '관련' 가리킴 절에 따로 적었다). 이 표 하나가 여러 개념에서 동시에 낡은 것은 개별 실수가 아니라 **갱신 경로의 구멍**이다 — 구현 커밋이 북극성 2절 표를 갱신 대상에 넣지 않았다.

## 4. 인계서 검사와 제안

- **메타**: 상태=낡은 문서 · 확인=2026-11-24(`d584a7c`) · 파일=`lib/handoff_check.py`,`hooks/handoff-check.py`,`hooks/hooks.json` · 이웃=개념 9(정본), 개념 10(전제), 개념 11(전제) · 문서=`README.md`,`README.ko.md`,`docs/GUIDE.md`,`docs/GUIDE.ko.md`,`docs/NORTH_STAR.md`

- **정해진 것**: `DECISIONS.md` 10-01 "beta v1.0 범위" — 길 단계 3의 인계서 검사기와 결정론 트리거를 넣는다(소유자). Stop 때 자동 갱신을 기본으로 켠 것은 결정 기록에 없다 — 코드 머리말(`hooks/handoff-check.py:10` "소유자 결정 2026-11-23")과 CHANGELOG beta.4만 적는다.
- **실제 동작**:
  - 검사기: 필수 8절(`lib/handoff_check.py:29`, 절마다 한국어·영어 이름)·200줄·8,700자·긴 코드 블록·전체 diff·비밀값·홈 절대경로(`lib/handoff_check.py:52`)·개인 자료 목록(`lib/handoff_check.py:100`). 훅 모드에서는 baton 형식으로 보이는 인계서(제목 "Session Handoff" 또는 템플릿 절 3개 이상 — 한국어는 앞머리, 영어는 템플릿 제목 그대로)에만 필수 절을 요구한다(`lib/handoff_check.py:189`). PR #6부터 "확인된 사실과 결정"(영어 "Verified facts and decisions") 목록 줄에 [V]·[?] 표시가 없으면 막지 않고 경고만 한다(`lib/handoff_check.py:216`). 메시지는 출력 언어를 따르고, 빠진 절 이름만은 파일이 쓴 언어로 낸다.
  - `HANDOFF.md`를 `Write|Edit|MultiEdit`한 직후 검사(`hooks/handoff-check.py:64`, `hooks/hooks.json:28`), 문제가 있으면 모델에 돌려준다(`decision: block`). 경고만 있으면 막지 않고 `additionalContext`로 알린다(`hooks/handoff-check.py:107`). 출력은 9,600자에서 자른다(`hooks/handoff-check.py:32`).
  - 2026-11-23(beta.4) 저장 때 경고 둘이 더해졌다. **빠진 줄**: 마지막 커밋판(`git cat-file blob HEAD:./HANDOFF.md`)과 비교해, 실패한 접근법·승격 후보·기각됨 절은 빠진 줄 모두, 확인된 사실·다음 행동 절은 결정·제약 표지가 있는 줄만 알린다(`lib/handoff_check.py:486` `drop_warnings`). 같은 폴더 `DECISIONS.md`로 옮긴 줄은 빠진 것으로 치지 않는다. 막지 않는다. 문턱 0.5는 한 저장소 인계서 이력으로 맞춘 값이고 그 표본 20줄에서 오탐 약 20%(코드 주석) — 다른 저장소는 모른다. 시한은 훅 시작 + 8초(`hooks/handoff-check.py:35`) 안에서 최대 2초(`lib/handoff_check.py:385`), 시간이 모자라 건너뛰면 "0개가 아니라 안 봤다"고 적는다(`hooks/handoff-check.py:94`). **필독 표시**: 3개를 넘으면 경고(`lib/handoff_check.py:346`).
  - Stop(`hooks/handoff-check.py:198`): 마지막 인계서 저장 뒤 다른 파일을 3개 이상 고쳤으면 세션에 한 번(`hooks/handoff-check.py:213`, `hooks/handoff-check.py:220`). 2026-11-23부터 기본(`BATON_HANDOFF_AUTO` 켬)은 **자동 갱신** — `decision: block`과 요청문을 내 에이전트가 턴을 끝내지 않고 `HANDOFF.md`를 지금 파일에서 시작해 갱신하게 한다(승격 검토 건너뜀, 커밋 안 함, `hooks/handoff-check.py:172` `auto_reason`, `hooks/handoff-check.py:230`). 끝에 사용자에게 쓸 한 줄은 요청문이 문장째 정해 준다 — "인계서를 고쳐 뒀어요. 이 기능을 끄려면 BATON_HANDOFF_AUTO=off로 설정하세요."(영어 "I updated the handoff. To turn this off, set BATON_HANDOFF_AUTO=off.", `hooks/handoff-check.py:185`, `hooks/handoff-check.py:194`, `386d152`). 전에는 무엇을 알릴지만 말하고 문장은 모델에게 맡겼다. `stop_hook_active`가 참이면 다시 막지 않는다(`hooks/handoff-check.py:204`). 저장소 루트의 `HANDOFF.md`가 baton 형식이 아니면 자동 갱신 대신 제안만 한다(`hooks/handoff-check.py:228`, `hooks/handoff-check.py:251`). `BATON_HANDOFF_AUTO=off`면 예전처럼 사용자에게 짧은 제안(`systemMessage`)만 한다(`hooks/handoff-check.py:235`) — 2026-11-24(`386d152`)부터 해요체 세 줄: "파일을 N개 고쳤는데 인계서는 그대로예요." / "하던 일이 끝났다면 "인계서 써 줘"라고 해 보세요. …" / "이 제안은 한 대화에 한 번만 나와요."(`hooks/handoff-check.py:236`, 영어 `hooks/handoff-check.py:240` — 파일 수에 따라 단수·복수). 로그 이벤트는 `handoff_auto`, 제안은 `handoff_nudge`(대신 제안했으면 `fallback: foreign_handoff`). `SessionEnd`에는 등록돼 있지 않다. Codex에서는 세션 기록에 Claude Code 모양의 편집 줄이 없어 제안도 자동 갱신도 나가지 않는다(코드 주석, 11-23 Codex 기록 확인).
  - 이름 붙은 인계서(`HANDOFF_*.md`·`handoff-*.md`)도 "인계서를 썼다"로 센다(`hooks/handoff-check.py:52`) — 제안 문턱과 `/baton-setup` 분포 둘 다. 검사·주입은 `HANDOFF.md`만 하고, 이름 붙은 인계서를 쓰면 `handoff_write` 이벤트만 남긴다(`hooks/handoff-check.py:69`). 11-21 로그에서 제안을 무시한 것으로 보인 13번 중 5번은 제안 뒤에 이름 붙은 인계서를 썼다.
  - 테스트: `lib/test_handoff_check.py` 53개(1개 건너뜀 — 이 저장소에 `HANDOFF.md`가 없다) + `hooks/test_handoff_check_hook.py` 29개 통과(2026-11-24 실행, Python 3.14·3.9 둘 다, 훅 테스트는 11-23에 28개). 루트 `HANDOFF.md`는 공개 저장소에서 지웠다(`82a7a07`) — 그래서 "이 저장소 인계서가 검사기를 통과한다"는 이제 확인할 대상이 없다.
  - 자동 갱신의 실제 Claude Code 세션 동작은 이 재확인에서 돌려 보지 않았다(테스트만).
- **설명된 곳**: `docs/GUIDE.md:65`·`docs/GUIDE.md:66`·`docs/GUIDE.md:72`, `docs/GUIDE.ko.md:55`·`docs/GUIDE.ko.md:56`·`docs/GUIDE.ko.md:62` — 코드와 일치(가이드의 "검사기를 돌린다"는 저장 훅이 돌리는 것). `skills/baton/SKILL.md` "When the Stop hook asks"(`skills/baton/SKILL.md:162`). `docs/NORTH_STAR.md:134`·`docs/NORTH_STAR.md:136`.
- **어긋남**:
  - **남음(낮음, 2026-11-23 재확인 때 찾음, 고치지 않음)** — **낡은 문서.** 북극성 단계 3의 결정론 트리거(`docs/NORTH_STAR.md:136`)는 Stop 훅이 인계서를 "**제안**(쓰기는 사람 승인)"한다고 적는다. 코드는 2026-11-23부터 기본으로 에이전트가 승인 없이 갱신하고 사용자에게는 뒤에 알린다(제안은 `BATON_HANDOFF_AUTO=off`일 때만). README·가이드·스킬은 이미 새 동작을 적는다. 북극성은 이 작업 범위 밖이라 고치지 않았다. **소유자가 정할 것**: 자동 갱신 기본값을 `DECISIONS.md`에 올릴지(이유·버린 대안은 결정한 사람만 안다 — 대신 쓰지 않는다).
  - 해소됨(2026-11-21) — 북극성 단계 3 본문(`docs/NORTH_STAR.md:136`)이 결정론 트리거를 "`Stop`·`SessionEnd` 훅에서"라고 적는다. 바로 위 상태 줄(`docs/NORTH_STAR.md:134`)은 "`SessionEnd` 대신 `Stop`만"이라 하고 코드도 `Stop`만이다 — 같은 절 안에서 서로 다르다. 상태 줄의 "테스트 18개"는 10-01 커밋 `8834a01` 기준 검사기 테스트만 센 값이고, 지금은 20 + 11개다. **낡은 문서** → 해소됨(2026-11-21, `6b51162`). 두 줄을 "`Stop`만"과 테스트 수로 고쳤다. 처음 고친 수(31개)는 작업하는 사이 PR #6이 머지되면서 바로 낡았다. 이 지도의 `fresh.sh`가 이 개념을 재확인으로 올려서 알았고, 44개(검사기 31·훅 13)로 다시 고쳤다. 날짜를 붙여 둔 이유다.

## 5. 세션 끊기 알림

- **메타**: 상태=해소됨(2026-11-21) · 확인=2026-11-24(`d584a7c`) · 파일=`hooks/split-notice.py`,`hooks/hooks.json` · 이웃=개념 10(전제) · 문서=`README.md`,`README.ko.md`,`docs/GUIDE.md`,`docs/GUIDE.ko.md`,`docs/NORTH_STAR.md`

- **정해진 것**: `DECISIONS.md` 09-30 "토큰 효율은 세션 끊기를 먼저 한다"(소유자). 문턱 2배·3배와 "권고만"은 세션의 구현 기본값.
- **실제 동작**: `Stop`에서 세션 기록의 첫 호출 맥락과 마지막 호출 맥락을 비교해(`hooks/split-notice.py:19`) 문턱(기본 `2,3`, `hooks/split-notice.py:64`)을 처음 넘을 때만 알린다(`hooks/split-notice.py:123`, `hooks/split-notice.py:134`). `hooks/hooks.json:54`에 등록. 2026-11-23(beta.4)부터 알림 문장은 출력 언어를 따른다(개념 10) — 문턱·한 번만 알리는 규칙은 그대로다. 2026-11-24 `386d152`에서 알림을 해요체 네 줄로 다시 썼다(`hooks/split-notice.py:84` `notice`): "대화가 처음보다 N배 길어졌어요(8만 5천 → … 토큰)." / "하던 일이 끝났다면 새 대화로 넘어가 보세요. …" / 넘어가는 법 "인계서 써 줘" → /clear → "이어서" / "이 알림은 한 번만 나와요." 토큰 수는 한국어에서 만·천으로 적는다(`hooks/split-notice.py:75`, 영어는 K). 절감 몫(2배 35~45%, 3배 30~34%)은 재계산 추정이 있는 기본 문턱에서만 말하고(`hooks/split-notice.py:72`), `/baton-setup`이 고른 다른 문턱에서는 말하지 않는다 — 전에는 어느 문턱에서든 두 수치를 다 적었다. 배수는 실제 비율(소수 한 자리) 대신 넘은 문턱을 적는다. 테스트 `hooks/test_split_notice.py` 15개 통과(2026-11-24 실행, Python 3.14·3.9 둘 다, 11-23에는 14개).
- **설명된 곳**: `docs/GUIDE.md:73`, `docs/GUIDE.ko.md:63` — 코드와 일치. `docs/NORTH_STAR.md:101`(날짜 박힌 상태 줄 "12개, 11-21 기준" — 지금은 14개지만 그날 값이라 고칠 대상이 아니다).
- **어긋남**: 북극성 단계 S 상태 줄(`docs/NORTH_STAR.md:101`)이 "테스트 7개"라 적는다. 공개 이력 첫 커밋 `9a7915c`(10-01)에서 이미 12개였다. 날짜가 박힌 상태 줄이라 그날 값일 수 있지만, 공개 이력 어디에서도 7개였던 적이 없다. **낡은 문서**(낮음) → 해소됨(2026-11-21, `6b51162`, "12개, 11-21 기준").

## 6. 메타 줄과 낡음 계산

- **메타**: 상태=해소됨(2026-11-23) · 확인=2026-11-24(`d584a7c`) · 파일=`lib/concepts.py`,`lib/fresh.sh`,`lib/check.sh`,`lib/lib.sh`,`hooks/drift-notice.sh`,`lib/test_fresh.py`,`hooks/test_drift_notice.py` · 이웃=개념 8(전제), 개념 14(전제) · 문서=`README.md`,`README.ko.md`,`docs/GUIDE.md`,`docs/GUIDE.ko.md`,`skills/driftmap/SKILL.md`

- **정해진 것**: 결정 기록에 따로 없다. 스킬 문서(`skills/driftmap/SKILL.md`)가 규칙의 정본 역할을 한다.
- **실제 동작**:
  - 형식을 아는 곳은 파서 하나다(`lib/concepts.py:27`, `lib/concepts.py:32`, `lib/concepts.py:111`). 숫자 없는 `#`·`##` 제목은 개념 절을 닫는다(`lib/concepts.py:29`). 단 ```·~~~ 코드 펜스 안의 줄은 제목으로 보지 않는다(`lib/concepts.py:31`, `lib/concepts.py:94`). 펜스가 열린 채 파일이 끝나면 `warnings`가 알린다(`lib/concepts.py:242`). 2026-11-21부터 `warnings`는 목록을 돌려주는 함수이고, 맥락 조립기와 후보 루프도 이것으로 못 읽은 부분을 낸다(개념 14). 메타 항목은 키 바로 앞이 줄 시작·`:`·`·`일 때만 찾는다(사이 공백 수는 상관없다) — `옛별칭=` 안의 `별칭=`처럼 다른 키 속에서는 안 걸리고, `**메타**:상태=구현`처럼 공백 없이 쓴 줄은 main 이전처럼 읽는다(`lib/concepts.py:57`). 정상으로 닫힌 펜스 안의 `## N.` 예시는 개념이 아니라서 알리지 않는다. `check.sh`는 이를 검사 [7]의 지적으로 세고, `fresh.sh`는 표 위에 `주의:`를 낸다(`lib/fresh.sh:151`). 세션 시작 알림은 재확인이 0건이어도 이때 울린다. 메타 줄의 `문서` 항목도 읽는다(`lib/concepts.py:169`).
  - 2026-11-23(beta.4): 파서는 출력 언어와 상관없이 두 언어 지도를 읽는다 — 메타 줄 `- **메타**:`·`- **Meta**:`(`lib/concepts.py:32`), 키 `상태`·`status` 등(`lib/concepts.py:34`, 영어 키는 대소문자 무시), 개념 가리킴 `개념 N`·`Concept N`(`lib/concepts.py:37`). 규칙 개념은 `파일=없음(규칙 개념)`·`files=none(rule concept)` 둘 다(`lib/fresh.sh:188`). `문서=없음`·`docs=none`은 경로가 아니라 빈 문서 목록으로 읽는다(`lib/concepts.py:169`, `2b72354`) — 전에는 그 개념이 영영 "문서 경로 소실"로 재확인에 묶였다. `fresh.sh`·`check.sh`·세션 알림은 한국어 또는 영어로 낸다(언어는 `lib/lib.sh`의 `open_concepts`가 정한다 — 설정 파일과 우선순위 절). 한국어 표는 예전 고정 폭 그대로이고, 영어는 단수·복수를 가린다(`lib/fresh.sh:29`). `check.sh`의 `echo … | grep -q`를 here-string으로 바꿨다 — `pipefail` 아래에서 가끔 SIGPIPE로 "없음"으로 읽혔다(CHANGELOG beta.4).
  - 판정은 커밋 수(`lib/fresh.sh:213`)·기준 없음(`lib/fresh.sh:179`)·기준 소실(`lib/fresh.sh:180`)·**기준이 현재 이력 밖**(`lib/fresh.sh:181`, HEAD의 조상이 아닌 확인 커밋)·경로 소실·미추적(`lib/fresh.sh:79`, `lib/fresh.sh:206`)·신선(`lib/fresh.sh:227`)·규칙 개념(`lib/fresh.sh:195`)에 **문서 커밋**(`lib/fresh.sh:96`, `lib/fresh.sh:223`)이 더해졌다. 표 끝에 요약 줄이 붙는다(`lib/fresh.sh:232` — 영어 `Summary: re-check N · fresh M · rule concepts K`).
  - 경로는 쉼표로만 나눠 배열에 담고(`lib/fresh.sh:66`) 따옴표째 git에 넘긴다. 그래서 공백이 든 경로가 쪼개지지 않고, 글롭은 셸이 아니라 git이 저장소 루트 기준으로 맞춘다. 사라진 경로(코드든 문서든, 일부만이라도)는 신선으로 두지 않는다. 그 경로도 `git log` 대상에 넣어 지우거나 옮긴 커밋을 센다(`lib/fresh.sh:213`, `lib/fresh.sh:221`). 규칙 개념의 확인 해시가 없으면 `(기준 없음 — 문서 못 봄)`을 붙인다(`lib/fresh.sh:194`). 적어 둔 해시가 소실·이력 밖이면 결정 변동도 셀 수 없으니 `재확인 필요 — 기준 소실 (규칙 개념)`으로 올려 세션 알림이 울리게 한다(`lib/fresh.sh:191`).
  - 세션 시작 알림은 개념 수·메타 줄 수를 grep이 아니라 파서로 세고(`hooks/drift-notice.sh:29`), 판정은 표의 글자 대신 그 요약 줄을 읽는다 — 두 언어 요약 줄 다(`hooks/drift-notice.sh:74`, `hooks/drift-notice.sh:80`, `hooks/drift-notice.sh:81`). 캐시 키에 `fresh.sh`와 출력 언어가 들어 있다(`hooks/drift-notice.sh:56`).
  - 2026-11-24(`386d152`) 세션 시작 알림의 문장을 해요체·쉬운 영어로 다시 썼다. 재확인이 있으면 "개념 지도에서 다시 확인할 개념이 N개 있어요(그대로인 개념 M개). 자세히 보려면 /drift"(`hooks/drift-notice.sh:95`, 영어 "N concepts in the concept map need another look (M unchanged). For details: /drift", `hooks/drift-notice.sh:107`). 열린 펜스 경고는 `concepts.py warnings`의 두 수(줄 번호·못 읽은 개념 수)만 꺼내 문장으로 다시 쓰고, 못 꺼내면 원문을 붙인다(`hooks/drift-notice.sh:87`). 재확인 0건에 펜스 경고만 있으면 그 경고만 낸다(`hooks/drift-notice.sh:98`). 메타 줄 없음·지도 못 읽음·요약 못 읽음도 "확인 기록(메타 줄)이 없어서 … 셀 수 없어요"처럼 무엇을 못 셌는지 말한다(`hooks/drift-notice.sh:30`, `hooks/drift-notice.sh:40`, `hooks/drift-notice.sh:76`) — 전의 "0건이 아니라 못 셌다"·"'모름'이다"를 풀어 쓴 것이라 못 셈을 0과 가르는 규칙은 그대로다. `fresh.sh` 표의 판정 낱말(`재확인 필요`·`신선`)은 바뀌지 않았다.
  - `check.sh`의 검사는 [1]~[7] 일곱 가지다([5] '파일' 항목의 지침 파일 섞임, [6] 메타 줄 수, [7] 열린 채 끝난 코드 펜스 — `lib/check.sh:127`). 끝 줄은 `지적 총 N건`(`lib/check.sh:139`).
  - 테스트 `lib/test_fresh.py` 54개, `hooks/test_drift_notice.py` 24개 통과(2026-11-24 실행, Python 3.14·3.9 둘 다, `XDG_CONFIG_HOME`을 빈 폴더로, 알림 테스트는 11-23에 22개). 2026-11-21 기록: 32개·7개였다(문서 항목 6·파서 2 추가, 리뷰 반영 8 추가, 후속 6 추가, 마지막 후속 2 추가 — 하나는 바꿈). 후속 6개(열린 펜스 경고 둘·제목 수 차이·규칙 개념 기준 소실·판정 문서 둘)와 알림 1개는 그 전 코드에서 실패했다. 처음 고칠 때 넣은 문서 항목 5개·파서 1개·이름 속 '신선' 1개는 그 전 코드에서 실패했다. 리뷰 반영으로 넣은 8개(이름 바뀐 문서·없는 문서 경로·일부 사라진 코드 경로·이력 밖 기준·공백 경로·글롭·규칙 개념의 문서 못 봄·펜스)도 리뷰 전 코드에서 모두 실패했다.
- **설명된 곳**: `docs/GUIDE.md:156`·`docs/GUIDE.md:161`·`docs/GUIDE.md:173`, `docs/GUIDE.ko.md:115`·`docs/GUIDE.ko.md:120`·`docs/GUIDE.ko.md:132`, `skills/driftmap/SKILL.md:291`, `skills/driftmap/SKILL.md:299`, `skills/driftmap/SKILL.md:438`, `skills/driftmap/SKILL.md:205`. 스킬 문서는 2026-11-23부터 영어이고, 두 언어 메타 줄 대응표를 둔다(`skills/driftmap/SKILL.md:13`).
- **어긋남** (모두 해소됨):
  - 해소됨(2026-11-23, `4c4652a`) — `check.sh` 검사 수(2026-11-21 재확인 때 찾음). 코드는 [7](열린 채 끝난 펜스)이 더해져 일곱인데, 스킬 문서는 표와 본문 모두 "여섯 가지"라 적었다 — **낡은 문서**. 이 지도의 실제 동작 면도 "[1]~[6] 여섯"이라 적고 있었다. [7]을 더한 PR이 스킬 문서를 갱신 대상에 넣지 않은 것이다. 이제 표("Seven checks", `skills/driftmap/SKILL.md:291`)와 본문("It looks at seven things", `skills/driftmap/SKILL.md:299`)이 일곱 가지를 [7]까지 나열한다.
  - 해소됨(2026-11-21, `7954eef`) — **PR #11 독립 리뷰가 잡은 것들.** 처음 수정에서 생기거나 남은 것이다. 펜스 안 `# 주석`에서 개념 절이 닫혔다(그 수정이 만든 회귀). 문서 이름을 바꾸거나 지우면 `신선 (문서 경로 소실 N개)`로 끝나고 세션 시작 알림도 울리지 않았다. 다른 가지의 커밋을 기준으로 두면 신선으로 나왔다. 공백이 든 경로가 쪼개졌고, 글롭이 지금 폴더 기준으로 펼쳐졌다. 규칙 개념은 기준이 없을 때 문서를 못 본다는 말이 없었다. 리뷰의 재현 저장소 셋으로 다시 돌려 모두 맞게 나오는 것을 확인했다.
  - 해소됨(2026-11-21, `d0c3642`) — **후속 점검(PR #11 재검증)에서 남은 것.** 펜스가 열린 채 끝나면 그 뒤 개념이 경고 없이 사라졌다(재현 저장소 t4). README의 판정 설명은 "여섯 가지"였는데 스킬 문서는 "아홉 가지"였다 — 이제 README·README.ko·스킬 문서가 같은 아홉 가지를 적고, 테스트(`VerdictDocsTest`)가 `fresh.sh`의 판정 이름과 두 문서를 맞춰 본다. 규칙 개념의 기준 소실은 세션 알림이 안 울렸다.
  - 해소됨(2026-11-21, `7c71c9d`) — **마지막 후속(재현 저장소 t6).** 닫힌 펜스 안의 `## 2.` 예시가 제목 수 차이 경고를 냈다. 세션 알림도 grep으로 세어, 펜스 안 예시까지 개념으로 친 틀린 개수("메타 줄이 모자란다")를 매 세션 냈다. 경고는 열린 채 끝난 펜스에만 남겼고, 알림은 파서로 센다.
  - **관찰(낮음, 고치지 않음)**: 커밋 수는 `git log <확인>..HEAD -- <파일>` 그대로라서 merge commit도 한 건으로 센다. PR #10을 merge한 뒤 시험해 보니 #10과 그 merge가 둘 다 세어져 "문서 커밋 2건"이 됐다. 판정(재확인인지 아닌지)은 맞고 건수만 부푼다. `--no-merges`로 바꿀지는 merge 방식을 정한 뒤에 정한다.
  - 해소됨(2026-11-21) — README 첫 화면의 데모 출력이 상태로 `구현됨`을 보여 줬다(닫힌 어휘 밖). README를 다시 쓰면서 스크래치 폴더의 임시 데모 저장소에서 `fresh.sh`를 실제로 다시 돌린 출력으로 바꿨다(지금 `docs/GUIDE.md:137`~`docs/GUIDE.md:143`, `docs/GUIDE.ko.md:93`~`docs/GUIDE.ko.md:99`). 상태는 `일치`·`미구현`이고 요약 줄도 들어 있다. 영어판 표(`docs/GUIDE.md:115`~`docs/GUIDE.md:121`)는 처음에는 그 출력의 번역이었고, 2026-11-23부터는 영어 출력 모양(상태 `agrees`·`not built yet`, 칸 폭 = 가장 긴 글 + 2)과 같다.
  - 해소됨(2026-11-21) — **README의 메타 줄 예시가 이 스킬의 규칙을 어긴다(중간).** `docs/GUIDE.md:156`·`docs/GUIDE.ko.md:115`(지금 줄)의 예시는 `상태=구현됨`인데, `구현됨`은 닫힌 상태 어휘 여덟 개에 없다. 이 예시를 그대로 베낀 지도는 `check.sh` 검사 [4]에서 지적을 받는다. 같은 예시의 `파일=`에는 문서(`docs/guide.md`)가 들어 있어서, `파일`에는 실제 동작 근거만 둔다는 규칙과도 어긋난다. PR #3에서 들어왔고 PR #8 뒤에도 그대로다. 사용자가 가장 먼저 베끼는 줄이라 이 개념에서 가장 무거웠다. `상태=일치`, `문서=`docs/guide.md``로 고쳤다(2026-11-23부터 영어 가이드의 예시는 영어 메타 줄 `status=agrees` · `docs=`). 스킬 문서의 예시(`ROADMAP.md`를 `파일`에 넣음)도 같이 고쳤다.
  - 해소됨(2026-11-21) — 판정 수: 스킬 문서의 판정 설명(지금 `skills/driftmap/SKILL.md:438`)은 "여섯 가지"라 하는데 코드에는 규칙 개념 판정이 하나 더 있다. README는 PR #8부터 여섯 판정 뒤에 규칙 개념을 따로 설명한다(지금 `docs/GUIDE.md:173`, `docs/GUIDE.ko.md:132`). 그래서 README 쪽은 코드와 맞고, 스킬 문서만 남아 있었다. 지금은 스킬 문서가 규칙 개념·문서 판정을 표에 더해 여덟 가지로 적는다.
  - 해소됨(2026-11-21) — **문서 쪽 근거는 신선도가 안 본다(미구현).** 스킬 문서는 메타 줄에 `문서` 항목을 두고 "신선도에서 낮은 우선순위로 본다"고 적었다(그 규칙 칸은 지금 `skills/driftmap/SKILL.md:125`). 하지만 파서와 `fresh.sh`에는 `문서` 항목을 읽는 코드가 없다. 그래서 PR #8이 README를 통째로 다시 쓴 뒤에도 `fresh.sh`는 12개 모두 신선으로 냈다. 이 지도의 "설명된 곳"에 적은 README 줄 번호 21개(서로 다른 파일:줄 기준)가 전부 다른 줄을 가리키고 있었고, 손으로 다시 찾아 맞췄다(2026-11-21). 이제 `fresh.sh`가 `문서` 항목의 파일이 움직이면 `재확인 필요 — 문서 커밋 N건`을 낸다. 이 지도의 메타 줄에도 `문서=`를 채웠다. 회귀 확인: 이 지도의 확인 해시를 PR #8 직전(`5c185bd`)으로 되돌린 사본을 돌리면, README를 `문서`로 둔 개념이 모두 문서 커밋 재확인으로 뜬다.
  - 해소됨(2026-11-21) — `check.sh` 검사 수: 스킬 문서가 표에서는 "여섯 가지", 바로 아래 본문에서는 "다섯 가지를 본다"라 적고 다섯만 나열했다(그 표·본문은 지금 `skills/driftmap/SKILL.md:291`·`skills/driftmap/SKILL.md:299`). 코드는 여섯.
  - 해소됨(2026-11-21) — 간선 종류: 절 제목은 "네 종류"인데 표에는 셋(전제·정본·공유파일)뿐이었다(그 제목은 지금 `skills/driftmap/SKILL.md:205` "three kinds").
- **이번에 함께 찾은 잠복 결함 둘** — 둘 다 해소됨(2026-11-21, `6b51162`, 회귀 테스트 있음):
  - 파서는 숫자 없는 `##` 절을 마지막 개념 절의 본문으로 읽는다(고치기 전 `walk`). 스킬이 권하는 산출물 구성(일치 확인된 것·확인하지 못한 것·유지 규칙을 개념 뒤에 둔다)을 따르면 그 절들이 마지막 개념에 붙는다. 그러면 그 절들 속 "개념 N" 언급이 마지막 개념의 참조로 세어지고, 실험 기능 개념 주입은 마지막 개념을 고르면 뒤 절까지 함께 넣는다. 이 지도로 재면(2026-11-21) 마지막 개념 자체는 8줄·591자인데 주입 텍스트는 뒤 절을 포함해 1,970자다 — 2,000자 상한을 겨우 넘지 않아 실제로 들어간다. 이 지도는 그것을 피하려고 뒤 절에서 개념을 번호 대신 이름으로 불렀다. 지금은 숫자 없는 `##` 제목에서 절이 닫힌다.
  - 세션 시작 알림은 `fresh.sh` 출력에서 `신선`이 들어간 줄을 센다(고치기 전 줄 53). 개념 이름에 "신선"이 들어 있으면 그 줄이 판정과 상관없이 신선으로 세어진다. 이 지도는 그래서 이 절 이름을 "낡음 계산"으로 지었다. 고친 뒤 `fresh.sh`에 요약 줄이 붙었는데, 그 줄에도 "신선"이 들어 있어서 옛 방식이었다면 더 틀렸을 것이다(테스트에서 `신선 2건`으로 재현).

## 7. 인계서 on-demand 주입

- **메타**: 상태=해소됨(2026-11-21) · 확인=2026-11-24(`d584a7c`) · 파일=`hooks/handoff-inject.py`,`lib/rules.py`,`hooks/hooks.json` · 이웃=개념 3(정본), 개념 9(정본), 개념 10(전제), 개념 13(전제) · 문서=`README.md`,`README.ko.md`,`docs/GUIDE.md`,`docs/GUIDE.ko.md`,`docs/NORTH_STAR.md`,`skills/baton/SKILL.md`

- **정해진 것**: `DECISIONS.md` 09-27 "인계서 주입은 on-demand, 200줄·9,000자"(세션 판정, 200줄은 09-22 소유자 결정). 글자 상한은 2026-11-21에 문서 상한 10,000자를 근거로 훅 출력 9,600자로 올렸다(개념 9) — 결정 기록은 고치지 않았다.
- **실제 동작**:
  - `UserPromptSubmit`에서 프롬프트가 트리거 말(`lib/rules.py:22`, 설정의 추가 말 포함 — PR #10부터 "where were we" 같은 영어 구도 들어간다)에 맞을 때만 주입(`hooks/handoff-inject.py:225`, `hooks/handoff-inject.py:232`). 무관한 프롬프트에는 넣지 않는다.
  - 한 세션에 같은 인계서는 한 번만 넣는다. 세션 id별로 넣은 내용의 해시와 그때 세션 기록 크기를 캐시 `injected/`에 남기고(`hooks/handoff-inject.py:193` `remember_injected`, 파일 600, 7일 지난 것은 지움), 같은 내용이면 그 뒤 세션 기록에 압축 경계(Claude Code `"subtype":"compact_boundary"`, Codex `"type":"compacted"`)가 생겼거나 기록이 줄었거나 64MB 넘게 자랐을 때만 다시 넣는다(`hooks/handoff-inject.py:159` `already_injected`). 세션 기록을 못 읽으면 다시 넣지 않고, 세션 id가 없거나 기억 파일이 깨졌으면 예전처럼 넣는다. 사람이 친 프롬프트가 아닌 것(`lib/rules.py:35` `MACHINE`)에는 인계서도 개념도 넣지 않는다(`hooks/handoff-inject.py:321`). 근거: 11-18 실사용 로그 주입 263번 중 226번이 같은 세션 재주입, 최소 152번이 다른 세션 메시지 계기.
  - 인계서를 "작성 시점의 가설"로 넣는다. 머리말은 "다시 열 필요 없다"를 그대로 두고 "그대로 이어서 진행한다"를 "다음 행동이 기대는 주장 한두 개를 확인한 뒤 진행"으로 바꿨다(`hooks/handoff-inject.py:69`). 바로 아래 신선도 한 줄 — 작성일·며칠 전·HANDOFF.md 마지막 커밋 뒤 이 폴더 커밋 수·못 센 까닭(`lib/rules.py:304` `handoff_freshness`, `lib/rules.py:361` `freshness_line`). 작성일은 첫 3줄(`lib/rules.py:282` `header_date`, `작성:`·`written:` 둘 다), 없으면 HANDOFF.md 마지막 커밋의 author 날짜. 커밋 안 한 수정 중이거나 얕은 복제면 커밋 수를 세지 않고 못 셌다고 적는다. git은 `--no-optional-locks`·`log.showSignature=false`로, 합계 3초(`lib/rules.py:253` `GIT_BUDGET`). 묵은 기준 `STALE_DAYS = 7`은 근거 없는 기본값. 실제로 넣을 때만 센다(`hooks/handoff-inject.py:247`) — `machine`·`already`로 건너뛸 때는 git을 부르지 않는다. 계산이 터져도 주입은 산다(`lib/rules.py:421` `safe_freshness`). 훅 시한은 10초(`hooks/hooks.json:44`). 신선도는 훅 시작 + 8.5초(`hooks/handoff-inject.py:63` `HOOK_DEADLINE`)를 넘겨 git을 부르지 않는다 — 시간이 없으면 "못 셌다(훅 시한)"라고 적고 넣는다. 다만 그 앞의 저장소 루트 계산(Codex만, `lib/rules.py:434`)과 설정 저장소 절 키(`lib/config.py:47` `repo_key`, 설정에 `repos`가 있을 때)는 git이 멈추면 각 5초라 그 둘만으로 10초에 닿을 수 있다 — 이 기능 전부터 있던 문제(리뷰 실측: PR #16 기준 Codex+설정 10.1초, 이 기능에 훅 공통 시한을 넣기 전 13.1초)이고 이 PR에서 고치지 않았다. 훅이 시한에 죽으면 인계서는 조용히 안 들어간다. 느린 git(호출당 1초) 실측은 테스트 `test_slow_git_hook_stays_under_timeout`. 계기: 2026-11-08 낡은 백업 폴더의 38일 된 인계서가 "그대로 이어서 진행한다"와 함께 주입됐다. 머리말 변경이 재독에 주는 영향은 안 쟀다.
  - 2026-11-23(beta.4) **필독 줄**: 인계서 "관련 파일·심볼"(`Files and symbols`) 절에서 `(필독)`·`(must read)` 표시가 붙은 항목을 앞에서 3개까지(항목마다 120자) 신선도 줄 바로 뒤 한 줄로 올린다(`hooks/handoff-inject.py:250`, `lib/handoff_check.py:355` `must_read_line`). 잘려도 남고, 그 줄이 깨져도 인계서는 그대로 넣는다(`hooks/handoff-inject.py:252`).
  - 2026-11-23(beta.4) **언어**: 머리말·신선도 줄·필독 줄·잘림 안내가 출력 언어를 따른다(영어 머리말 `hooks/handoff-inject.py:74` `HEAD_EN`, 영어 신선도 줄 `lib/rules.py:390`, 영어 잘림 안내 `hooks/handoff-inject.py:266`). 영어 머리말이 길어 신선도 줄 상한이 따로 있다(개념 9). 트리거 말은 언어 설정과 상관없이 두 언어 다 본다.
  - 출력은 Claude Code·Codex 둘 다 받는 JSON `additionalContext`(`hooks/handoff-inject.py:350`).
  - git이 없을 때: 저장소 루트 계산이 예외를 삼키고 폴더 기준으로 넘어간다(`lib/rules.py:434`, `lib/rules.py:440`). git이 없는 `PATH`로 `handoff-inject.py`·`split-notice.py`·`handoff-check.py`를 돌렸을 때 셋 다 종료 코드 0, stderr 없음(2026-11-21, 2026-11-23 다시 실행).
  - 테스트 `hooks/test_handoff_inject.py` 41개 중 40개 통과·1개 건너뜀(실험 스냅샷은 소유자 로컬에만 있다, 2026-11-23 실행, Python 3.14·3.9 둘 다 — 영어 주입 `EnglishInjectTest` 5개 포함). 신선도 자체는 `lib/test_rules.py` `FreshnessTest`.
- **설명된 곳**: `docs/GUIDE.md:67`·`docs/GUIDE.md:69`·`docs/GUIDE.md:70`·`docs/GUIDE.md:71`, `docs/GUIDE.ko.md:57`·`docs/GUIDE.ko.md:59`·`docs/GUIDE.ko.md:60`·`docs/GUIDE.ko.md:61` — 코드와 일치. `docs/NORTH_STAR.md:83`. 쓰는 쪽 규칙(첫 줄 작성일, "지금 상태(근거) → 할 일", 확인 방법, 필독 표시)은 `skills/baton/SKILL.md` "A handoff is a hypothesis from the time it was written, not a fact"(`skills/baton/SKILL.md:123`)와 "Mark what must be read"(`skills/baton/SKILL.md:106`).
- **어긋남**: 북극성 2절 표 Fallback 칸(`docs/NORTH_STAR.md:83`)이 "다만 조용하지는 않다 — git을 못 찾으면 traceback을 낸다"고 적는다. 위 실행으로는 traceback이 나지 않는다. **낡은 문서**(낮음) → 해소됨(2026-11-21, `6b51162`). 규칙 판단 절에 적은 것과 같은 표, 같은 원인이다.

## 8. 새 결정의 '관련' 가리킴

- **메타**: 상태=미결 · 확인=2026-11-23(`067a23e`) · 파일=`lib/fresh.sh`,`lib/concepts.py` · 이웃=개념 6(전제) · 문서=`skills/driftmap/SKILL.md`,`docs/NORTH_STAR.md`

- **정해진 것**: 결정 기록에 따로 없다. 스킬 문서 모드 ④ "Did the decisions move?"가 미구현을 잡는 유일한 경로라고 적는다.
- **실제 동작**: 메타 줄의 확인 해시 이후 `DECISIONS.md`에 새로 들어온 줄 중 `관련` 뒤의 "개념 N"·개념 이름을 찾아 그 개념을 재확인으로 올린다(`lib/fresh.sh:106`, `lib/concepts.py:43`, `lib/concepts.py:204`). 2026-11-23(beta.4)부터 영어 결정 기록의 `Related:`(콜론까지 붙은 것만, `lib/concepts.py:49`)와 `Concept N`(`lib/concepts.py:37`)도 같은 방식으로 읽는다. 못 이은 것은 "0건이 아니라 못 셌다"로 따로 낸다. 새 결정 중 `- 관련:`·`- Related:` 줄이 없는 것을 구멍으로 센다(`lib/fresh.sh:266`). 확인 커밋이 HEAD의 조상이 아니면 `DECISIONS.md` 비교를 하지 않는다 — 비교할 기준이 없어서다.
- **설명된 곳**: `skills/driftmap/SKILL.md` 모드 ④(`skills/driftmap/SKILL.md:456`), `docs/NORTH_STAR.md:78`.
- **어긋남**:
  - 북극성 2절 표 개념 지도 점검 칸(`docs/NORTH_STAR.md:78`)이 "새 결정 → 재확인(09-30, **커밋 전**)"이라 적는다. 공개 이력 첫 커밋부터 커밋돼 있다. **낡은 문서**(낮음) → 해소됨(2026-11-21, `6b51162`).
  - **남음 — 갱신 경로의 구멍**(대신 채우지 않음, 그래서 이 개념의 상태가 `미결`): `DECISIONS.md` 22개 항목(2026-11-23 다시 셈. 이전 판은 20개라 적었다 — 11-21 "목표"·11-22 "합격선" 두 항목이 들어오기 전 수다. 두 항목에는 `- 관련:` 줄이 있다) 중 09-22 "인계서 상한 200줄"과 09-22 "진실 신호 없이 라우팅 후보는 시험하지 않는다" 두 항목에 `- 관련:` 줄이 없다. 이 둘이 어느 개념을 건드렸는지는 결정한 사람이 적는다. 특히 앞의 것은 인계서 상한 개념의 "정해진 것"이다.
  - 이 저장소 `DECISIONS.md`의 `관련:` 줄은 개념 번호 대신 파일 경로를 쓴다. 이 지도가 생겼으니 앞으로는 경로에서 개념을 역산할 수 있다(스킬 절차 4).
  - 같은 구멍의 다른 모양(2026-11-23): Stop 때 인계서 자동 갱신을 기본으로 켠 소유자 결정은 `DECISIONS.md` 항목 자체가 없다(인계서 검사와 제안 절). 관련 줄이 없는 것이 아니라 결정이 기록 밖에 있어서, 이 판정으로는 잡히지 않는다.

## 9. 인계서 상한 200줄·9,000자

- **메타**: 상태=해소됨(2026-11-22) · 확인=2026-11-24(`d584a7c`) · 파일=`hooks/handoff-inject.py`,`lib/handoff_check.py`,`skills/baton/SKILL.md` · 이웃=개념 4(정본), 개념 7(정본) · 문서=`README.md`,`README.ko.md`,`docs/GUIDE.md`,`docs/GUIDE.ko.md`,`docs/NORTH_STAR.md`

- **정해진 것**: `DECISIONS.md` 09-22 "인계서 상한 200줄"(소유자, 이유 칸 비어 있음) · 09-27 "인계서 주입은 on-demand, 200줄·9,000자"(9,000자는 실측: 20,826자는 Claude Code가 파일로 뺐다).
- **실제 동작**: 주입 훅은 200줄(`hooks/handoff-inject.py:54`)·훅 출력 전체 9,600자(`hooks/handoff-inject.py:55`), 검사기는 200줄·8,700자(`lib/handoff_check.py:20`·`lib/handoff_check.py:21`). 9,600자는 Claude Code 문서의 훅 맥락 상한 10,000자(https://code.claude.com/docs/en/hooks "JSON output", 2026-11-21 확인 — 넘으면 파일로 빠지고 앞 2,000자 미리보기만 넘어간다, 올리는 설정 없음)에서 여유 400자를 뺀 값이다. 인계서 본문 예산은 머리말·신선도 한 줄(·필독 줄)의 실제 길이와 꼬리 안내 몫 200자를 뺀 나머지이고(`hooks/handoff-inject.py:255`), 같은 출력에 개념 색인이 붙으면 그 몫을 더 빼되 `HANDOFF_KEEP` 밑으로는 줄이지 않는다(`hooks/handoff-inject.py:272`). `HANDOFF_KEEP`은 검사기 상한 + 1이다(`hooks/handoff-inject.py:58` — 8,701자). 그래서 검사기를 통과한 인계서는 색인 때문에 더 잘리지 않고, 둘 다 안 들어가면 색인이 줄거나 빠진다. 색인 몫 때문에 더 자른 뒤 색인이 결국 빠지면 덜지 않은 판으로 되돌린다(`hooks/handoff-inject.py:345`, 개념 색인 절). 신선도 한 줄은 500자를 넘지 않아(`lib/rules.py:254` `FRESHNESS_MAX`) 본문에 늘 8,739자 이상이 남는다(색인이 같이 들어가면 최소 8,701자). 테스트 `hooks/test_handoff_inject.py` `HookOutputBudgetTest`(13개)가 이 셈과 문서 상한을 묶는다. 주입은 넘치면 자르고 잘랐다고 한 줄 붙인다(`hooks/handoff-inject.py:263`).
  - 2026-11-23(beta.4) 두 언어·필독 줄: 영어 머리말(`hooks/handoff-inject.py:74`)이 한국어보다 길어 영어 신선도 줄 상한은 350자이고(`lib/rules.py:257` `FRESHNESS_MAX_EN`), 그래도 본문에 최소 8,712자가 남는다(한국어 8,739자 — 2026-11-23 두 상수로 다시 계산). 필독 줄은 머리말에 한 번 더 들어가므로 검사기가 그 줄 길이까지 8,700자에 센다(`lib/handoff_check.py:175`). 그래서 검사를 통과한 인계서는 어느 언어든, 필독 줄이 있어도 전부 들어간다(`HookOutputBudgetTest`의 영어·필독 테스트).
- **설명된 곳**: `skills/baton/SKILL.md:111`·`skills/baton/SKILL.md:143`, `docs/GUIDE.md:65`·`docs/GUIDE.md:68`, `docs/GUIDE.ko.md:55`·`docs/GUIDE.ko.md:58`, `docs/NORTH_STAR.md` 1절("Handoff ≤ 200줄").
- **어긋남**: 해소됨(2026-11-22, PR #14 머지). 처음에는 검사기도 9,000자였고 주입 예산은 그보다 작은 8,708자(당시 훅 출력 9,000자 − 머리말·안내)여서, 8,709~9,000자 인계서가 검사를 통과하고 주입에서 잘렸다. 사용 로그(10-04~11-21)에서 주입 285번 중 163번이 잘렸고, 200줄을 넘은 것은 6번뿐이라 대부분 글자 예산에서 잘렸다. 그 뒤 PR #19가 훅 출력을 9,600자로 올렸고, PR #14가 검사기를 8,700자로 낮췄다. 이제 검사기를 통과한 인계서는 신선도 한 줄이 가장 길어도, 개념 색인이 같이 들어가도 전부 들어간다. `lib/test_handoff_check.py` `InjectBudgetTest`와 `hooks/test_handoff_inject.py` `HookOutputBudgetTest`가 두 값을 묶는다 — 한쪽만 바꾸면 테스트가 깨진다. 결정 기록 09-27의 "9,000자"는 이 변경 전 수치로 그대로 남아 있다(결정 기록은 사람이 고친다).

## 10. 설정 파일과 우선순위

- **메타**: 상태=해소됨(2026-11-23) · 확인=2026-11-24(`d584a7c`) · 파일=`lib/config.py`,`lib/i18n.py`,`lib/setup_scan.py`,`lib/test_i18n.py` · 이웃=개념 4·5·7·13(전제) · 문서=`README.md`,`README.ko.md`,`docs/GUIDE.md`,`docs/GUIDE.ko.md`,`skills/baton-setup/SKILL.md`,`commands/baton-setup.md`,`commands/baton-doctor.md`

- **정해진 것**: 결정 기록에 따로 없다(`/baton-setup`은 커밋 `24e3996`에서 들어왔다). 출력 언어(`BATON_LANG`)도 결정 기록에 없다(beta.4, `56a94ff`).
- **실제 동작**:
  - `lib/config.py:135` — 환경변수 > 저장소 절 > 전역 절 > 기본값. 관찰 로그 키 둘은 전역만(`lib/config.py:24`). 목록 키는 전역 + 저장소(`lib/config.py:148`). 세션 끊기 문턱·인계서 제안·자동 갱신 문턱·추가 트리거 말·각 훅의 끄기 스위치가 모두 이 설정을 읽는다. beta.4에서 키 둘이 더해졌다 — `BATON_LANG`, `BATON_HANDOFF_AUTO`(`lib/config.py:23`, `3ea1642`).
  - 출력 언어(2026-11-23, `lib/i18n.py:68` `where`): `BATON_LANG` 환경변수(`ko`·`en`) > 설정 파일의 저장소 절 > 전역 절 > 로캘(`LC_ALL`·`LC_MESSAGES`·`LANG` 중 처음 값이 있는 것, `lib/i18n.py:51`) > **로캘 변수가 하나도 없는 macOS에서는 시스템 언어 목록**(`defaults read -g AppleLanguages`의 첫 항목, 1초 시한, `lib/i18n.py:34`) > 영어. 환경변수가 `auto`나 모르는 값이면 설정 파일을 보지 않고 로캘로 간다. 빈 환경변수는 없는 것으로 친다. 한국어 판정은 `ko` 뒤에 끝·`_`·`.`·`@`·`-`가 올 때만이다(`lib/i18n.py:26` — `kok_IN`은 영어). python3가 없으면 셸 쪽이 환경변수·로캘만 본다(`lib/lib.sh:80` `baton_lang_sh`). `/baton-setup`은 지난 프롬프트의 언어를 세어 `BATON_LANG`을 제안하고, `/baton-doctor`(`python3 lib/config.py`)는 지금 언어와 정한 곳을 보여 준다(`lib/config.py:243`).
  - 테스트 `lib/test_config.py` 29개, `lib/test_i18n.py` 18개 통과(2026-11-23 실행, Python 3.14·3.9 둘 다, `XDG_CONFIG_HOME`을 빈 폴더로 — 소유자 설정의 `BATON_LANG=ko`가 끼지 않게).
- **설명된 곳**: `docs/GUIDE.ko.md:158`, `docs/GUIDE.md:199`, 언어 절 `docs/GUIDE.md:230`·`docs/GUIDE.ko.md:188`, `skills/baton-setup/SKILL.md:147`, `commands/baton-doctor.md:26`, `commands/baton-setup.md`.
- **어긋남**:
  - 해소됨(2026-11-23, `1e983ce`) — **낡은 문서였다.** 가이드의 언어 순서가 로캘 다음 바로 영어였고, 코드가 로캘 변수 없는 macOS에서 먼저 읽는 시스템 언어 목록(`AppleLanguages`) 단계와 좁힌 한국어 판정(`kok_IN`은 영어)이 빠져 있었다. 두 가이드의 언어 절(`docs/GUIDE.md:234`~`docs/GUIDE.md:241`, `docs/GUIDE.ko.md:192`~`docs/GUIDE.ko.md:199`)에 그 단계와 규칙, 빈 `BATON_LANG`을 없는 것으로 보는 것을 더했다.
  - 관찰(낮음, 고치지 않음): 가이드·CHANGELOG의 "`ko`로 시작하면 한국어"는 코드보다 넓다(`kok_IN`도 `ko`로 시작한다). 실제로 걸릴 일은 드물다.

## 11. 공개 경계 — 개인 자료

- **메타**: 상태=일치 · 확인=2026-11-24(`d584a7c`) · 파일=`.gitignore`,`lib/handoff_check.py` · 이웃=개념 4(전제), 개념 15(전제) · 문서=`README.md`,`README.ko.md`,`docs/GUIDE.md`,`docs/GUIDE.ko.md`,`docs/NORTH_STAR.md`

- **정해진 것**: `DECISIONS.md` 10-01 "북극성 정본 원문과 사례 모음은 공개 저장소에 올리지 않는다" · 10-01 "개인 자료가 섞인 공개 이력을 새 이력 하나로 바꾼다"(공개 전 검사는 실명·프롬프트 원문·다른 저장소 내용·절대경로·커밋 이력까지 본다). 둘 다 소유자.
- **실제 동작**: `.gitignore`가 `docs/north-star/`와 `observer/research/cases.json`을 뺀다(`.gitignore:7`, `.gitignore:8`). 인계서 검사기는 홈 절대경로와 사용자가 고른 개인 자료 단어를 막고, 찾은 값 자체는 출력하지 않는다(`lib/handoff_check.py:52`, `lib/handoff_check.py:100`). 관찰 로그는 프롬프트 원문을 남기지 않는다(`hooks/handoff-inject.py:302`). 같은 패턴을 짧은 글에 쓰는 `leaks`(`lib/handoff_check.py:108`)로 별칭 승격도 거른다(개념 15). 2026-11-23(beta.4)의 빠진 줄 경고도 옛 줄이 유출 검사(비밀값·홈 경로·개인 자료 단어)에 걸리면 그 내용을 경고에 적지 않는다(`lib/handoff_check.py:530`). 공개 저장소에 남아 있던 10-01자 `HANDOFF.md`는 지웠다(`82a7a07`).
- **설명된 곳**: `docs/NORTH_STAR.md` 0절(정본 경로는 소유자 로컬 기준이라고 밝힘), `docs/GUIDE.md:363`, `docs/GUIDE.ko.md:157`·`docs/GUIDE.ko.md:321`.
- **어긋남**: 없음. `docs/NORTH_STAR.md`의 정본 경로 표는 공개판에 없는 파일을 가리키지만, 바로 아래에 "공개 저장소에는 없다"고 밝혀 두었다 — 끊어진 참조가 아니라 의도된 것.

## 12. 결정 기록은 사람이 쓴다

- **메타**: 상태=일치 · 확인=2026-11-24(`d584a7c`) · 파일=`lib/promote.sh`,`commands/promote.md`,`skills/baton/SKILL.md` · 이웃=없음 · 문서=`README.md`,`README.ko.md`,`docs/GUIDE.md`,`docs/GUIDE.ko.md`

- **정해진 것**: `DECISIONS.md` 머리말 — "이유 칸이 비어 있는 것은 기록이 없어서다, 추측으로 채우지 않았다". 항목마다 결정 주체(소유자/세션 판정)를 적는다.
- **실제 동작**: `lib/promote.sh`는 과거 인계서를 날짜당 한 판씩 읽어(`lib/promote.sh:63`) 서로 다른 3일 이상 살아남은 항목을 후보로 출력만 한다(`lib/promote.sh:9`, `lib/promote.sh:76`). 파일을 쓰지 않는다(2026-11-23 다시 봄 — 쓰기 리다이렉트 없음). 명령 문서는 "rejected alternatives·reason은 빈칸으로", `DECISIONS.md`를 대신 쓰지 않는다(`commands/promote.md:12`). 2026-11-23(beta.4): 절 제목은 한국어·영어 템플릿 둘 다 읽고(`lib/promote.sh:58`), 템플릿 자리표시 `- 없음`·`- None`은 항목으로 세지 않으며(`lib/promote.sh:49`, `83a25c5`), 출력은 출력 언어를 따른다(python3가 없으면 셸이 환경변수·로캘로 정한다, `lib/promote.sh:18`).
- **설명된 곳**: `docs/GUIDE.md:74`, `docs/GUIDE.ko.md:64`, `skills/baton/SKILL.md`의 "Promotion stops at a proposal"(`skills/baton/SKILL.md:258`).
- **어긋남**: 없음. 실제 `DECISIONS.md`도 이 규칙을 지킨다 — 이유를 모르는 항목은 "(기록 없음)"으로 비어 있다.

## 13. 개념 색인 — 에이전트가 고를 개념 목록

- **메타**: 상태=낡은 문서 · 확인=2026-11-24(`d584a7c`) · 파일=`lib/concepts.py`,`hooks/handoff-inject.py`,`lib/rules.py`,`lib/test_concepts_index.py`,`hooks/test_handoff_inject.py` · 이웃=개념 7(전제), 개념 10(전제) · 문서=`README.md`,`README.ko.md`,`docs/GUIDE.md`,`docs/GUIDE.ko.md`,`skills/driftmap/SKILL.md`,`commands/baton-explain.md`

- **정해진 것**: 결정 기록에 따로 없다. `docs/NORTH_STAR.md:111`(3절 "정본에서 벗어나는 선택" 3)의 기준선 ②("메인 모델이 개념 색인(제목·한 줄·별칭)만 보고 스스로 여는 방식", 추가 호출 0)를 구현했다. 별칭은 없다 — 지도에 별칭이 0개다. 계기는 오프라인 평가 — 프롬프트와 개념 제목의 규칙 단어 맞추기는 정밀도 0~1%, 별칭 0개, 로그에서 캐낼 것도 없었다. 사람의 말과 개념 이름이 달라서다.
- **실제 동작**:
  - 색인은 `lib/concepts.py:330` `index` — 개념마다 `N. 이름 — 한 줄 · 파일: a, b, c (+N)`, 머리말 한 줄, 최대 1,500자(`lib/concepts.py:262` `INDEX_LIMIT_CHARS`). 한 줄 요약은 절 제목의 ` — ` 뒤뿐이고, 없으면 이름만 낸다. 요약표의 `한 줄` 칸은 읽지 않는다(`d6b656a`부터) — 그 칸은 개념이 무엇인지가 아니라 어긋남의 경과를 적어서다. 요약표는 폐기된 개념을 빼려고 `상태` 칸만 읽는다(`lib/concepts.py:306` `table_states` — 칸 위치는 머리 줄 이름 `상태`·`status`로). 파일은 `파일=`(영어 지도 `files=`) 값에서 백틱이 있든 없든, 값 안의 ` · `는 앞 키의 이어짐으로 읽는다(`lib/concepts.py:277` `meta_fields`, `lib/concepts.py:292` `meta_files` — concept-notes 브랜치 `lib/notes.py` `parse_meta`의 이음 규칙). 상태의 첫 낱말이 정확히 `폐기`·`폐기됨`·`retired`일 때만 뺀다(`lib/concepts.py:271`). 백틱 안은 통째로 경로 하나로 먼저 꺼내고(줄 번호에 쉼표가 든 경로 — 경로:12,30 꼴 — 도 끊지 않는다) 적힌 순서를 지킨다. 홈 절대경로·`~/`는 뺀다. 본문은 NFC로 맞추고, 요약은 띄어 쓴 ` — ` 뒤만, 제목이 빈 절은 뺀다. 개념은 200개까지만 줄로 내고(나머지는 "… N개 더"로 센다) 줄이는 셈은 개념 수에 비례한다. 넘치면 뒤쪽 개념부터 요약을 떼고 → 첫 파일만 남기고 → 뒤쪽 개념을 빼고 "… N개 더" 한 줄을 남긴다. 결정론·표준 라이브러리만. `concepts.py <지도> index`로 본다.
  - 훅은 세션의 첫 사람 프롬프트에 한 번 넣는다(`hooks/handoff-inject.py:281` `concept_index`). 인계서와 같은 세션 기억 파일에 `index_offset`을 따로 적어(`hooks/handoff-inject.py:193` `remember_injected`) 각자 한 번씩 들어가고, 압축 뒤에는 다시 넣는다(`hooks/handoff-inject.py:169` `index_injected`). 기계 프롬프트에는 넣지 않고 기억도 하지 않아 다음 사람 프롬프트에 들어간다. 세션 기억을 쓸 수 없으면(세션 id 없음·캐시 폴더에 못 씀 — `hooks/handoff-inject.py:180` `memory_writable`) 색인을 넣지 않는다(`no_memory`) — 매 프롬프트 1,500자보다 한 세션 색인을 잃는 쪽이 싸다. 인계서 뒤에 붙고, 색인 몫을 먼저 잡되 검사기를 통과한 인계서는 줄이지 않고 색인을 줄인다(`hooks/handoff-inject.py:339`, `hooks/handoff-inject.py:341`). 색인이 결국 빠지면 인계서는 색인 몫을 덜지 않은 판으로 되돌린다(`hooks/handoff-inject.py:345`). 끄기 `BATON_CONCEPT_INDEX=off`(`lib/config.py:21`). 무엇이 터져도 색인만 빠지고 인계서는 들어간다.
  - `/baton-explain`이 넣을지와 크기(글자·개념 수)를 보여 준다(`lib/rules.py:160` `index_line`). 세션 기억은 보지 않는다.
  - 머리말은 "작업에 맞는 개념의 파일부터 연다. 개념은 탐색 앵커다 — 실제 동작은 코드로 확인한다"(`lib/concepts.py:267` `INDEX_HEAD`) — 인계서·개념 절 머리말과 같은 입장. 처음 판의 "그 파일만 연다"는 탐색을 너무 일찍 멈출 수 있다는 리뷰 지적으로 바꿨다.
  - 2026-11-23(beta.4): 색인은 출력 언어를 따른다 — 머리말(영어 `lib/concepts.py:269` `INDEX_HEAD_EN`)과 `파일:`·`files:`, `… N개 더`·`… N more`. 훅·`/baton-explain`이 정한 언어를 넘긴다(`hooks/handoff-inject.py:328`, `lib/rules.py:160`, `af5f37c`). 영어 지도(`- **Meta**: … files=…`)도 같은 규칙으로 읽는다. 영어 머리말이 더 길어 같은 지도라도 영어 색인이 길다 — 이 지도(이번 판, 15개 개념)는 한국어 1,277자·영어 1,436자(2026-11-23 `concepts.py CONCEPTS.md index`, 둘 다 1,500자 안).
  - 테스트 `lib/test_concepts_index.py` 23개, `hooks/test_handoff_inject.py` `ConceptIndexHookTest` 7개(출력 언어 1개 추가)·`HookOutputBudgetTest` 13개(그중 색인 이름이 붙은 것 3개) 통과(2026-11-23 실행, python3 3.14·`/usr/bin/python3` 3.9). 이 저장소 지도의 색인은 개념 13개·1,118자였다(요약표 칸을 쓰던 판은 1,477자, 머리말을 바꾸기 전 판은 1,092자. PR #20 병합 뒤 15개 개념·1,258자, 2026-11-23 이 판 1,277자). 개념마다 첫 파일이 저장소에 있다(`RealMapTest`).
  - 실측(2026-11-22, `d6b656a` 사본 — 머리말을 바꾸기 전 1,092자 판, `claude -p` sonnet, 도구 Read·Grep·Glob만, 사용자 설정·MCP·스킬 끔): 개념 제목을 피한 일상어 질문 4개 × 색인 있음·없음 × 3회 = 24회, $0.461. 정답 파일을 처음 겨냥한 도구 호출 순번 평균 1.50(범위 1~2) 대 2.33(2~3), 도구 호출 2.08 대 2.92, 모델 호출 2.92 대 3.58, 입력 토큰 21,701 대 24,347, 비용 $0.0186 대 $0.0198. 답은 24회 모두 맞는 파일을 댔다. 질문별로 갈린다 — 설정 우선순위·세션 끊기 질문은 색인 쪽이 도구 1번으로 끝났고(없으면 4번·2번), 인계서 경고·비밀값 질문은 색인 쪽이 모델 호출·토큰을 더 썼다. 같은 질문의 3회는 거의 같은 경로라 반복은 표본을 늘리지 못했다 — 사실상 질문 4개다. 판정: 결론 못 냄(평균은 색인 쪽이 조금 낫지만 질문 넷 중 둘에서만).
- **설명된 곳**: `docs/GUIDE.md:80`, `docs/GUIDE.ko.md:70`, `skills/driftmap/SKILL.md:409`, `commands/baton-explain.md:19`·`commands/baton-explain.md:21`.
- **어긋남**: 북극성 2절 표의 Context Selection 칸(`docs/NORTH_STAR.md:72`)은 "개념 제목 단어가 맞으면 그 절 하나 주입"만 적고 이 색인을 모른다. 단계 2의 개념 색인 항목(`docs/NORTH_STAR.md:127`)도 별칭·이웃을 넣는 설계 그대로다. **낡은 문서**(낮음) — 북극성은 이 작업 범위 밖이라 고치지 않았다(소유자 판단). 그래서 상태는 일치가 아니라 낡은 문서다. **소유자가 정할 것**: 지도에 개념 설명 항목(무엇에 관한 개념인지 한 줄)을 따로 둘까. 지금은 제목의 `—` 뒤만 쓰는데, 이 저장소 개념 13개 중 둘만 그것이 있었다(2026-11-23: 15개 중 넷 — 11·13·14·15번 절). 요약표의 `한 줄` 칸은 어긋남의 경과를 적는 칸이라 대신 쓸 수 없다. 메타 줄에 `설명=`을 더하면 파서·driftmap 스킬·`check.sh`를 같이 고쳐야 하고, 제목에 `— 설명`을 붙이는 쪽은 형식이 그대로다.

## 14. 맥락 조립기 — 개념 그래프로 고르기

- **메타**: 상태=미구현 · 확인=2026-11-24(`d584a7c`) · 파일=`lib/compiler.py`,`lib/test_compiler.py` · 이웃=개념 6(전제), 개념 15(정본) · 문서=`docs/research/ONTOLOGY_DESIGN.md`,`README.md`,`README.ko.md`,`docs/GUIDE.md`,`docs/GUIDE.ko.md`

- **정해진 것**: `DECISIONS.md` 10-07 "개념 그래프를 실측 가능한 수준까지" — 설계안 P4를 `lib/compiler.py`로 만들고 프롬프트 훅에 붙이되 기본은 그림자 모드(고른 것을 판단 로그에만 남김), 간선은 메타 줄 `이웃`만 쓴다(소유자). 10-07 두 번째 — 측정 판정은 그래프 완성 뒤. 커밋 co-change 그래프는 10-04 오프라인 평가에서 기준선을 못 이겨 쓰지 않는다(`docs/research/ONTOLOGY_DESIGN.md` 3-1·3-2절).
- **실제 동작**:
  - 그래프는 `CONCEPTS.md` 메타 줄에서 읽는다: 노드는 개념, 간선은 `이웃`, 붙은 파일은 `파일`, 다른 이름은 `별칭`(`lib/compiler.py:96`). 2026-11-23부터 영어 지도의 키(`files=`·`neighbors=`·`aliases=`)와 `Concept N`도 읽는다. 절 나누기는 파서의 `walk` 그대로이고, 파서가 못 읽은 부분은 `warnings`로 함께 낸다(`lib/compiler.py:117`).
  - 고르기: 제목 단어·별칭·작업 파일로 맞은 개념과 그 이웃 한 칸(`lib/compiler.py:120`). 세 곳 이상 개념에 걸린 파일과 허브 파일은 개념을 고르는 근거가 아니다(`lib/compiler.py:30`). 예산은 개념 수 8·파일 10·결정 10, 글 300줄·4,000자(`lib/compiler.py:26`, `lib/compiler.py:27`). 이 세션이 이미 만진 파일은 뺀다. 같은 자리에서 기준선 셋(같은 폴더만·인계서만·그래프 뺀 조립기)을 함께 계산한다(`lib/compiler.py:359`).
  - 캐시는 저장소 밖 `~/.cache/baton/compile/`. 상대 경로 `XDG_CACHE_HOME`은 무시하고, 절대 경로를 못 정하면 캐시를 만들지 않는다(`lib/compiler.py:216`).
  - 지금 도는 길은 `python3 lib/compiler.py explain "<프롬프트>"` 하나다. `hooks/handoff-inject.py`는 조립기를 부르지 않고(2026-11-23 grep 0건 — 같은 grep이 `lib/rules.py`에서는 2건을 찾는다), `BATON_COMPILER`는 설정 키에도 없다.
  - 테스트 `lib/test_compiler.py` 25개 통과(2026-11-23 실행, Python 3.14·3.9 둘 다). 이 저장소 지도로 `explain "인계서 상한 바꾸기"`를 돌리면 AMBIGUOUS로 4·7·9번 개념 등을 고른다(2026-11-23).
- **설명된 곳**: `docs/research/ONTOLOGY_DESIGN.md` 7절과 머리말, `docs/GUIDE.md:332`, `docs/GUIDE.ko.md:290`.
- **어긋남**: **미구현**(낮음, 미룬 순서). 10-07 결정은 훅에 그림자 모드로 붙이는 것까지인데 main에는 조립기 코드만 있다. 인계서 주입 훅을 다시 쓰는 PR #16·신선도 브랜치 뒤에 붙이기로 했다(`DECISIONS.md` 10-07의 "main 반영" 줄). 그림자 기록을 채점하는 `observer/research/compile_eval.py`(설계안 7절)는 기록이 없으면 늘 "못 셌다"만 내고 Python 3.9에서 시각 오프셋을 못 읽어 이 PR에서 뺐다 — **훅 연결 PR과 함께 돌아온다**(`compiler-shadow`에 있다). 조립 글 머리에서도 아직 없는 스위치(`BATON_COMPILER`) 이름을 뺐다.

## 15. 개념 후보 루프 — 별칭과 새 개념

- **메타**: 상태=일치 · 확인=2026-11-24(`d584a7c`) · 파일=`lib/candidates.py`,`lib/test_candidates.py` · 이웃=개념 14(전제), 개념 11(전제) · 문서=`skills/driftmap/SKILL.md`,`docs/research/ONTOLOGY_DESIGN.md`,`README.md`,`README.ko.md`,`docs/GUIDE.md`,`docs/GUIDE.ko.md`

- **정해진 것**: `DECISIONS.md` 10-07 두 번째 — 개념 그래프 완성은 스펙 21절 루프(관찰 → 저장소 밖 후보 → 결정론 검증 → 사람 승격), 새 개념 신호는 구절 + 안 묶인 파일(소유자). 10-04 ④ — 후보는 `~/.cache/baton/`에만, `CONCEPTS.md`에는 사람이 승격할 때만. 10-08 — 별칭 승격은 개인 자료 검사를 거친다.
- **실제 동작**:
  - `scan`: 이 저장소의 Claude Code 세션 기록(다른 폴더에서 열었어도 기록에 이 저장소 경로가 나오는 세션 포함, SDK 세션 제외)에서 사람 프롬프트 턴과 그 턴에 고친 파일을 모은다(`lib/candidates.py:145`, `lib/candidates.py:191`). 구절은 `rules.phrases`(`lib/rules.py:72`) — `/baton-setup`과 같은 정의다. 2026-11-23부터 영어 불용어(`lib/rules.py:62` `EN_STOP`)를 뺀다(`83a25c5`).
  - 검증: 서로 다른 날 3일 이상, 기존 제목·별칭과 안 겹침, 트리거 말 아님, 오발화 ≤ 적중, 버린 것 아님(`lib/candidates.py:22`, `lib/candidates.py:247`). 후보는 저장소 밖 캐시에만 쓰고, 구절만 남기며 프롬프트 원문은 남기지 않는다(`lib/candidates.py:368`). 0건이면 어느 단계에서 0이 됐는지 낸다.
  - `promote-alias`: 사람이 고른 구절을 그 개념 메타 줄 `별칭=`에만 덧붙인다(`lib/candidates.py:446`). 영어 지도면 `aliases=`에(키는 두 언어 다 찾고, 없으면 메타 줄 언어로 새로 단다 — `lib/candidates.py:30`, `lib/candidates.py:505`). 쓰기 전에 비밀값·홈 경로·개인 자료 단어·이 컴퓨터의 사용자 이름과 홈 폴더 이름을 거르고, 걸린 값은 다시 출력하지 않는다(`lib/candidates.py:459`). `개념 N`·`Concept N`이 든 구절은 가짜 간선이 되므로 거절한다(`lib/candidates.py:455`). 파서가 끝까지 못 읽는 지도에는 쓰지 않는다(`lib/candidates.py:467`). 고를 메타 줄은 읽는 쪽(조립기·`concepts.py meta`)과 같은 규칙 — 절 본문의 첫 메타 줄, 펜스 안 줄 포함 — 으로 찾고, 그 줄이 펜스 안이거나 메타 줄이 둘 이상이면 거절한다(`lib/candidates.py:474`, `lib/candidates.py:491`). 지도는 임시 파일에 쓴 뒤 통째로 바꾼다(`lib/candidates.py:509`). 세션 기록 시각의 `+0900` 꼴 오프셋은 Python 3.9에서도 읽도록 고쳐 읽는다(`lib/candidates.py:28`). 새 개념은 스크립트가 쓰지 않는다. 메시지는 출력 언어를 따른다.
  - 테스트 `lib/test_candidates.py` 35개 통과(2026-11-23 실행, Python 3.14·3.9 둘 다). 관찰 → 승격 → 조립기가 그 별칭으로 개념을 고르기까지 끝까지 가는 테스트가 있다. 실제 기록으로는 소유자 작업 사본에서 세션 1개·관찰 182건이 모두 날 수·파일 문턱에서 빠져 후보 0건(재료 부족)이 나왔다 — 0은 버그가 아니라 재료가 적어서다.
- **설명된 곳**: 스킬 모드 ⑤(`skills/driftmap/SKILL.md:63`, `skills/driftmap/SKILL.md:525`), `docs/research/ONTOLOGY_DESIGN.md` 8절, `docs/GUIDE.md:332`, `docs/GUIDE.ko.md:290`.
- **어긋남**: 없음.

## 일치 확인된 것

근거는 각 개념 절의 실제 동작 면에 있다. 여기에는 따로 대조해 맞았던 것만 모은다.

- 테스트 570개 통과(2026-11-24, `b5f6ec7`에서 Python 3.14.6과 3.9.6 둘 다, 같은 방식. hooks 130·lib 363·tools 12·observer/research 65, 건너뜀 4 — 알림 문장을 다시 쓰며 세션 끊기 1·세션 시작 알림 2·인계서 훅 1개가 늘었다).
- 테스트 566개 통과(2026-11-23, `067a23e`에서 Python 3.14.6과 3.9.6 둘 다, CI와 같은 `git ls-files … | xargs python -m unittest`, `XDG_CONFIG_HOME`을 빈 폴더로·`BATON_LANG` 없이 — 소유자 설정은 `BATON_LANG=ko`다. 네 묶음: hooks 126·lib 363·tools 12·observer/research 65, 건너뜀 4 — 인계서 없음 1·실험 스냅샷 없음 1·`observer/research/test_case_grade.py` 2). 이전 기록: 300개(2026-11-21, `6695701`, hooks 54·lib 173·tools 8·observer/research 65, 건너뜀 3, `compile_eval` 테스트 13개는 그 스크립트와 함께 뺐다). 그때 macOS 기본 bash 3.2로도 `lib/test_fresh.py`·`hooks/test_drift_notice.py`를 돌려 통과했다(이번에는 다시 돌리지 않았다).
- 매니페스트 세 곳의 버전이 같다(`1.0.0-beta.4`, `tools/check_versions.py` ok, 2026-11-23).
- 가이드의 명령 표 다섯 줄(`docs/GUIDE.md:181`, `docs/GUIDE.ko.md:140`)은 `commands/` 파일 다섯 개와 맞는다. 훅 등록은 `hooks/hooks.json`에 스크립트 다섯 개다.
- 인계서 템플릿의 8절(`skills/baton/SKILL.md` 템플릿 — 2026-11-23부터 영어판·한국어판 둘)과 검사기의 필수 절 목록(`lib/handoff_check.py:29`, 절마다 두 언어 이름)이 같다.
- 루트 `HANDOFF.md`는 2026-11-21에 검사기를 통과했다(49줄, "문제 없음"). 2026-11-23 공개 저장소에서 그 파일을 지웠다(`82a7a07`, 10-01자 낡은 인계서) — 지금은 확인할 파일이 없다.

## 폐기된 개념

없음(최초 생성).

## 확인하지 못한 것

- **Linux에서의 동작.** 모든 실행은 macOS에서 했다.
- **Codex에서 스킬 이름이 어떻게 보이는지.** 플러그인 구성 절의 이름 충돌은 Claude Code 목록에서만 봤다.
- **지도의 링크 자리.** 스킬은 매 세션 읽히는 `AGENTS.md`(또는 `CLAUDE.md`)에서 이 지도를 한 줄로 가리키라고 한다. 이 저장소에는 둘 다 없어서 링크를 걸지 않았다(README에 걸지는 소유자 판단). 세션 시작 훅은 저장소 최상위 두 단계 안의 `CONCEPTS.md`를 스스로 찾으므로 신선도 알림은 링크 없이도 돈다.
- **결정 기록의 이유 칸.** 비어 있는 이유는 추측하지 않았다.
- **새 0건 상기 훅의 실제 세션 동작.** 테스트는 Claude Code 형식의 입력(`tool_response`가 `stdout`·`stderr` 객체)과 문자열 응답으로 했다. Codex의 실제 PostToolUse 입력으로는 돌려 보지 않았다.
- **Stop 때 인계서 자동 갱신의 실제 세션 동작.** 2026-11-23 재확인은 테스트(`hooks/test_handoff_check_hook.py`)와 코드 읽기로만 했다. 실제 Claude Code 세션에서 `decision: block`으로 턴이 이어지고 인계서가 갱신되는지는 돌려 보지 않았다.
- **영어 출력의 실제 세션 동작.** 영어 메시지는 테스트로만 확인했다. 이 재확인은 한국어 설정 세션에서 했다.
- **Linux에서의 언어 판정.** macOS 언어 목록 단계는 macOS에서만 돈다. Linux 경로는 테스트(`lib/test_i18n.py`)로만 봤다.

## 유지 규칙

- 먼저 `/drift`(모드 ④)를 돌린다. 재확인 대상이 없으면 열지 않는다.
- 재확인 대상만 다시 대조하고, 대조한 개념의 메타 줄 `확인=`을 그때의 커밋으로 옮긴다. 지도와 코드를 한 커밋에서 같이 고쳤다면 다음 커밋에서 옮긴다.
- 어긋남을 고쳐 닫으면 지우지 말고 상태를 `해소됨(날짜)`로 바꾼다.
- `파일`에는 코드·테스트·산출물만 적는다. `DECISIONS.md`·`HANDOFF.md`·`README.md`는 넣지 않는다(설명된 곳이나 정해진 것의 출처다).
- 간선은 전제·정본만, 양쪽에 적는다. 공유파일 관계는 적지 않는다.
- `문서`에는 그 개념을 설명하는 README·스펙·스킬 문서를 적는다. 문서만 움직이면 `fresh.sh`가 문서 커밋 재확인으로 알린다. 그때는 "설명된 곳" 면의 줄 번호만 다시 맞추면 된다.
