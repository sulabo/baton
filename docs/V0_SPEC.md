# BATON V0 — 작업 추출을 먼저 검증하고, 규칙을 채점한다

상태: 5판 (코덱스 4차 검토: 구현 착수 "예". 첫 커밋 전 조건 네 줄 반영)
관계: `NORTH_STAR.md`의 첫 구현 단계. 여기 없는 것은 V0가 아니다.

수치 표기 규칙. **모든 경험적 수치에는 태그가 붙는다.** 설계 파라미터(표본 수, 시간 구간 경계)는 붙이지 않는다.
`[MEASURED]` 쟀고 방법이 적혀 있다 · `[MEASURED, PRE-VALIDATION]` 쟀으나 그 도구 자체가 아직 검증 전 ·
`[ILLUSTRATIVE]` 모양만 보여주는 예시 · `[ESTIMATE]` 추정.

## 한 줄

**프로젝트에 baton을 붙이는 순간, 그 프로젝트의 과거 기록으로 규칙을 시험하고 성적표를 낸다.**
아무것도 바꾸지 않는다. 기다리지도 않는다.

## V0가 답하는 질문 (정확히)

> **과거 작업 기록을 직접 참조하지 않고 구성한 현재 BATON 규칙이,
> 사용자가 과거에 실제로 쓴 작업 표현을 얼마나 설명하는가?**

3판은 "프로젝트 구조만 보고 만든 규칙"이라 했는데 틀린 표현이었다. `baton configure`에서 **사람이**
도메인을 정하므로 규칙은 구조 + 사람의 1회 설정이다. 그 사람은 과거 작업을 기억하고 있다.
이것을 막지 않는다. 제품의 실제 초기 설정이 그렇기 때문이다. 막는 것은 **기록 파일을 열어 보고 규칙을
쓰는 것**과 **채점 결과를 보고 규칙을 고친 뒤 같은 기록으로 다시 채점하는 것**이다.

## 4판 → 5판 (코덱스 4차)

구현 착수 판정 "예". 그 조건으로 다음 넷을 계약에 넣었다.

1. **0-B 문턱 지표는 구간 모집단으로 가중한다.** 구간마다 같은 수를 뽑으면 표본은 25%씩인데 모집단은 다르다.
2. **전역 규칙 v0.1.0의 과거 말뭉치 점수는 author-exposed baseline이다.** 독립 일반화 성능이 아니다.
3. **재현되지 않은 이전 측정은 SUPERSEDED / UNREPRODUCIBLE로 보존하고 원인을 추정하지 않는다.**
   4판의 "`>`→`>=`가 원인"은 증명되지 않은 귀속이었고, 그 변경은 후보를 늘리지 줄이지 않는다.
4. **같은 말뭉치를 본 뒤 고친 규칙의 후속 run은 TUNED_ON_SEEN_CORPUS로 표시한다.** 지문은 추적성이지 누출 방지가 아니다.

그 외: 층별 모집단이 목표보다 작으면 전수 검사하고 EXHAUSTED · 구간마다 population_n/sample_n/sampling/seed 기록 ·
수동 숫자(127/127)를 스크립트 출력으로 대체 · [MEASURED]마다 실행 명령과 스크립트 해시 · 기간의 기준 시각 정의.

## 3판 → 4판

코덱스 3차 검토 반영. 구조는 그대로이고 **측정 경계를 잠그는 장치**가 들어갔다.

- **전역 규칙은 제품에 내장된 일반 분류 체계로 고정한다.** 3판의 "사용자의 말 습관을 보고 손으로 쓴다"는
  누출 경로였다. 그 말 습관을 아는 사람은 기록을 본 사람이다.
- **동결 절차와 지문(fingerprint).** 규칙·도메인 설정·평가 말뭉치의 해시를 `run.json`에 남기고,
  규칙이 바뀌면 새 실행 번호로 기록한다. 덮어쓰지 않는다.
- **표본은 개수가 아니라 층으로 정의한다.** 0-A는 내용 구조별, 0-B는 겹치지 않는 공백 구간별.
- **"330 → 86"이 재현되지 않았다.** 다시 재니 333 → 76이다. 아래에 출처를 전부 적고 이전 숫자를 폐기한다.
- 커밋 어휘 진단은 기본 실행에서 빼고 선택 명령으로 내린다.

## 단계와 동결 순서

```
0.  전역 규칙 = 내장 v0.1.0  (프로젝트를 보기 전에 이미 고정)
1.  STEP 1   프로젝트 규칙 초안 — 구조에서만
2.  configure 사람이 도메인 정의
3.  freeze   rules.yaml · domain config 해시 저장
4.  STEP 0-A 사람 프롬프트 추출 검증
5.  STEP 0-B 작업 경계 검증
6.  STEP 2   규칙 채점
```

**3번 이후 규칙을 고치면 그것은 새 실행(run #2)이다.** 같은 말뭉치로 다시 채점한 결과를
run #1을 덮어 기록하지 않는다.

### 전역 규칙 — 내장, 버전 고정

```yaml
global_rules:
  version: "v0.1.0"
  task_types: [debugging, implementation, design, question, refactor, test, documentation]
  verbs_ko: {debugging: [고쳐, 안 돼, 에러], implementation: [만들어, 추가해], ...}
```

출처는 "사용자의 말 습관"이 아니라 **BATON 제품의 기본 분류**다. 프로젝트 데이터를 본 뒤 바꾸지 않는다.
개인화된 전역 규칙은 V0에 없다. 원하면 V1에서 별도 기능으로, 보정 집합과 검증 집합을 나눠서 한다.

**남는 누출.** 한국어 동사 목록을 쓰는 사람은 이 사용자의 기록을 이미 봤다(이 문서 작성자 포함).
완전히 막을 방법은 다른 사람이 쓰는 것뿐이다. V0의 완화책은 셋이다. 말뭉치 특정 표현이 아니라
**일반 명령형 동사만** 넣는다. 프로젝트 init 전에 고정한다. 이 문단을 스펙에 남긴다.

**이 셋은 제거책이 아니라 완화책이다.** 따라서 현재 과거 말뭉치에서 계산한 전역 규칙 성능은 독립적인
일반화 성능 추정치가 아니라 **author-exposed baseline**으로 취급한다. v0.1.0 동결 이후 새로 발생한
기록에서 처음으로 prospective validation을 할 수 있다. v0.1.0은 변경 불가능한 버전 산출물로 남긴다.

### STEP 1 — 프로젝트 규칙 초안 (구조에서만)

```yaml
domains:
  status: unconfigured
domain_evidence:
  from_concepts: [엔딩 판정, 잔상, 레이저]
  from_agents_md: [그래프 적립 장치]
  from_dirs: [src, specs, sim-tests]
```

과거 기록을 보지 않는다. 커밋 메시지도 보지 않는다. 도메인 자동 제안은 없다.

### configure — 사람이 도메인 정의

```yaml
domains:
  - name: gameplay
    evidence: [엔딩 판정, 잔상]
```

이 단계가 끝나면 `freeze`. 이후 STEP 0-A·0-B·2 동안 `rules.yaml`을 건드리지 않는다.

### STEP 0-A — 사람 프롬프트 추출 검증

`"type":"user"`에는 도구 결과가 섞여 있다. 추출기는 `content`가 문자열이거나, `text` 블록만 있거나,
**`text`+`image` 블록만 있는 것**(tool_result 없음)을 사람 프롬프트로 본다. 길이로 거르지 않는다.

`[MEASURED]` 2026-09-21, 0-A 첫 결함. 스펙이 "text 블록만"이라 적혀 있어 첫 구현이 이미지가 붙은
사람 프롬프트 3건("일단은 1-1이야", "아니 없다니까?")을 버렸다. 고정 측정 스크립트는 받아들여
383 대 386으로 갈렸고, 그 차이로 잡았다. **구현 둘을 대조하는 것이 0-A의 방법 하나다.** 수정 후 일치.
음수 공백(밀리초 순서 뒤바뀜) 2건은 0으로 잡고 `negative_gap_clamped`에 센다.

**표본은 내용 구조별 층화.** 받아들인 쪽과 버린 쪽 각각에서 발견되는 구조마다 뽑는다.

```
accepted:  plain string / text block only / 기타 발견 구조
rejected:  tool_result 포함 / mixed / 기타
각 층 최소 5건. 어느 층을 몇 건 봤는지 기록.
```

이 수는 **초기 오류 탐지용 최소 수작업 예산**이지 통계적 충분성이 아니다.

`[MEASURED, PRE-VALIDATION]` 15자 필터가 버리던 양. 아래 출처 블록의 386 대 333. 즉 추출기가 받아들인
프롬프트의 14%를 길이 필터가 버리고 있었다. "빌드 고쳐줘"류가 거기 있다. 필터를 뺀 근거.

### STEP 0-B — 작업 경계 검증

출처를 분리한다. Claude·Codex 세션은 평가 대상, 커밋은 제외.

**프로젝트 귀속.** 파일 안 `cwd`를 `Path.resolve()` 후 NFC 정규화로 비교.

**Codex 연결.** `history.session_id`와 세션 파일명 끝 UUID를 파싱해 등호 비교. 파일 첫 줄
`payload.session_id`로 교차 확인.

```
[MEASURED] 2026-09-21 · glob sessions/**/*.jsonl (숨김 제외) · 파일명 끝 UUID 정규식 · 등호 비교
  history rows 207 · parse 실패 0 · missing session_id 0 · text 0 · ts 0 · distinct H = 26
  session files S = 127 · 파일명 UUID 파싱 실패 0
  M1 = 26 · M0 = 0 · Mmulti = 0 · P = 26 · C = 26
  교차 확인(연결된 26개): payload.session_id == 파일명 UUID  26 / 26
  교차 확인(파일 전부):   payload.id == 파일명 UUID  127 / 127
  구성: 루트 세션 30 · 포크 스레드 97 (forked_from_id 있음. session_id는 부모, history.jsonl에 없음)
  → 정체성 필드는 payload.id. 5판 초고의 "31/127"은 session_id로 비교한 결과이며 오류가 아니라 포크였다.
  → Codex 프롬프트 추출은 history.jsonl이 아니라 세션 파일을 직접 읽는다. 포크 96개는 history에 없다.
  실행: python3 observer/measure/codex_join_census.py   (script sha256 앞 12자 fe4f5b9ab52c)
  판정: 통과.
  기록: 중간에 "96개 불일치"가 나왔으나 정규식이 payload.id 앞의 다른 id를 잡은 측정 오류였다.
```

**작업 경계 후보.** `SESSION_FIRST`와 `GAP_CANDIDATE`(gap_minutes 기록). 30분을 경계로 정하지 않는다.

**표본은 겹치지 않는 공백 구간별.** 15·30·60분은 중첩 문턱이라 "고르게"가 정의되지 않았다.

```
SESSION_FIRST            최소 10
0  < gap < 15분          최소 10
15 <= gap < 30분         최소 10
30 <= gap < 60분         최소 10
60 <= gap                최소 10
```

같은 라벨로 어느 문턱의 정밀도든 나중에 계산한다. 표본을 늘리려고 구간을 조정하지 않는다.

**문턱 정밀도는 구간 모집단으로 가중한다.** 구간마다 10건씩 뽑으면 표본에서는 각 25%지만 모집단은
(예컨대) 700·100·50·20이다. `[30,60)`과 `[60,∞)` 표본을 합쳐 30분 정밀도라 부르면 틀린다.
그래서 `tasks.jsonl`에 **구간별 모집단 수**를 반드시 남긴다.

모집단이 목표보다 작으면 **전수 검사하고 `EXHAUSTED`** 표시. 구간마다 기록:
```json
{"bucket":"gap_30_60","population_n":47,"sample_n":10,"sampling":"random","seed":20260921}
```
이 표본은 통계적 충분성이 아니라 **초기 오류 탐지용 최소 수작업 예산**이다. "추출기가 검증됐다"고
말하지 않는다.

```
[MEASURED, PRE-VALIDATION] 2026-09-21
  실행: python3 observer/measure/extract_prompts.py '*26-05'   (script sha256 앞 12자 56d37229da86)
  Project root: (문서 프로젝트)
  Source: Claude Code만 · Codex 미포함 · session files 24
  기간: 각 event의 timestamp 기준, 2026-08-22 00:00 이상 ~ 2026-09-22 00:00 미만 (파일 mtime 아님)
  Raw user-type events: 3038
  Extractor accepted (구조 필터만): 386   (observer/baton_init.py extract 도 386. script sha256 앞 12자 e59003094d67)
    그중 15자 이상: 333
  Among 333: SESSION_FIRST 17 · gap>=30분 59 · union 76
  Dedup 없음 · 경계 비교 >= · 0-A 검증 전 출력

Previous measurement: 330 → 86
  Status: SUPERSEDED / UNREPRODUCIBLE
  Reason: 당시 스크립트와 입력 스냅샷이 보존되지 않음
  Known differences: 세션 파일 집합이 바뀜 · 경계 비교 연산자가 다를 수 있음
  Causal attribution: unknown. 위 차이가 330→333, 86→76을 설명하는지 확인할 수 없다.
```

**기간과 입력을 고정한다.** 같은 스크립트라도 파일이 추가되면 값이 달라진다. `run.json`에
`measurement_cutoff`(위 상한)와 `source_manifest_sha256`(스캔한 파일 목록+크기의 해시)를 남긴다.

### STEP 2 — 규칙 채점

층별 최소치 `MATCHED 20 · AMBIGUOUS 20 · NO_MATCH 10`. 예측을 숨기고 라벨. `label_type: SINGLE | MULTI | NONE | UNCLEAR`.

## 성적표 `.baton/calibration.md`

층별 지표만. 아래 숫자는 전부 `[ILLUSTRATIVE]`.

```
[ILLUSTRATIVE]
run #1 · evaluation_status BASELINE · evaluation_type operator-informed retrospective
rules_sha256 ab12… · domain_config_sha256 cd34… · corpus_sha256 ef56… · script_sha256 …
0-B 문턱 지표: 구간 모집단 가중 · 전역 규칙 점수: author-exposed baseline
global_rules v0.1.0 · configured_at … · evaluation_started_at …

STEP 0-A  추출기 (구조별)
  accepted/plain string     XX%  (n)     rejected/tool_result   XX%  (n)
STEP 0-B  경계 (구간별)
  SESSION_FIRST XX% · [0,15) XX% · [15,30) XX% · [30,60) XX% · [60,∞) XX%
STEP 2    프로젝트 규칙 (20/20/10)
  MATCHED 중 맞힘 XX% · AMBIGUOUS 중 단일 XX% (rule ambiguity resolution opportunity)
  AMBIGUOUS 중 MULTI XX% (규칙이 맞음) · NO_MATCH 중 답 있음 XX%
전역 규칙 v0.1.0 (작업 종류, 프로젝트 합산)   MATCHED 중 맞힘 XX%
```

"rule ambiguity resolution opportunity"는 Jev 최대치가 아니다. 규칙 버그일 수 있다.
Jev 가치는 같은 라벨 집합에서 Rules only 대 Rules + Jev 직접 비교로만.

시간 누출(개념 지도가 최근 커짐)은 허용하되 성적표 머리에 적는다. 표본이 적으면 `LOW_SAMPLE`.

## `init` 실행 계약

- `run.json`: `run_status`, `failed_stage`, `reason`, `rules_sha256`, `domain_config_sha256`,
  `corpus_sha256`, `source_manifest_sha256`, `measurement_cutoff`, `script_sha256`,
  `global_rules_version`, `configured_at`, `evaluation_started_at`, **`evaluation_status`**.
- `evaluation_status`: 첫 run은 `BASELINE`. 채점 결과를 본 뒤 규칙을 고친 후속 run은
  **`TUNED_ON_SEEN_CORPUS`**. 그 결과는 개선 작업에는 쓰되 **일반화 성능 주장에는 쓰지 않는다.**
  지문은 추적성을 만들 뿐 누출을 막지 않는다.
- 결과는 임시 파일 후 rename. 규칙 변경 시 `run #N+1`. 덮어쓰지 않는다.
- 모든 경험적 수치는 센 것 · 못 센 것 · 이유 · 태그.

## 선택 진단 (기본 실행 아님)

```
baton diagnose commits
```

커밋 어휘가 프롬프트에 **문자 그대로** 재등장하는 비율만 잰다. "겹침"의 정의(대소문자, 하이픈,
한/영 대응)를 명령 안에 적는다. **결과로 V1 사용 여부를 정하지 않는다.** 어휘가 안 겹쳐도 정보 가치가
없다는 뜻이 아니다.

## V0에 없는 것

훅 · 컨텍스트 제거 · 스킬 필터 · 자동 핸드오프 · 라우팅 · Jev · 그래프·온톨로지 수정 · 기존 스킬 변경 ·
전체 정확도 한 숫자 · 도메인 자동 제안 · 기록으로 규칙 보정 · **개인화 전역 규칙** · 커밋 어휘의 규칙 반영.

## 파일

```
.baton/
  rules.yaml        global(version) + project. domains.status
  tasks.jsonl       source · boundary_type · gap_minutes · SHORT_PROMPT · content_schema · extractor_decision
  labels.jsonl      0-A · 0-B · 2
  calibration.md    run # · 지문 · 태그된 수치
  run.json
```

## 구현 전 재검토 — 코덱스 4차에서 닫힘

1. 층별 예산 → "초기 오류 탐지용"으로 지위 확정, 모집단 부족 시 EXHAUSTED, 구간 메타 기록. 닫힘.
2. 작성자 누출 → 제거가 아니라 완화·공개로 처리. author-exposed baseline 지위. 한국어 목록 유지. 닫힘.
3. 측정 스크립트 고정 → 됨. 실행 명령과 해시를 수치 옆에. 닫힘.

**구현 착수: 예.** 남은 것은 설계가 아니라 추출기와 규칙이 실제로 얼마나 깨지는지 보는 일이다.

──── 끝. 이 줄까지 보였으면 전문이 전달된 것이다. ────
