# 변경 기록

이 파일은 사용자가 알아야 할 변화만 적습니다. 왜 그렇게 정했는지는 `DECISIONS.md`, 실험 수치는 `docs/research/LOOP_PLAN.md`에 있습니다.
버전은 [유의적 버전](https://semver.org/lang/ko/)을 따릅니다. `1.0.0` 정식판은 만든 사람 말고 다른 사람의 실사용 기록이 생긴 뒤에 냅니다.

## [Unreleased]

### 추가
- **개념 색인.** 저장소에 `CONCEPTS.md`가 있으면 세션의 첫 사람 프롬프트에 개념마다 이름·제목의 "—" 뒤 한 줄(있을 때만)·주요 파일(최대 셋)을 한 줄씩 적은 색인을 한 번 넣습니다(1,500자 이하, 압축 뒤 다시). 에이전트가 그중 작업에 맞는 개념을 골라 그 파일만 엽니다. 인계서와 같이 들어가면 인계서 뒤에 붙고, 자리가 모자라면 색인을 줄입니다(8,700자 인계서는 그대로 다 들어갑니다). 끄기: `BATON_CONCEPT_INDEX=off`. `/baton-explain`이 넣을지와 크기를 보여 줍니다.

### 바뀜
- 인계서를 넣을 때 **작성 시점의 가설**이라고 함께 알립니다. 머리말 바로 아래 한 줄에 작성일과 며칠 전인지, `HANDOFF.md`를 마지막으로 커밋한 뒤 이 폴더에 들어온 커밋 수를 붙이고, 7일이 지났으면 다음 행동이 아직 유효한지부터 확인하라고 적습니다. 셀 수 없으면(커밋 안 한 수정 중·얕은 복제·git 시간 초과) 못 셌다고 적고, 그래도 인계서는 넣습니다.
- 주입 글자 상한을 훅 출력 9,000자에서 9,600자로 올렸습니다. Claude Code 문서가 훅 맥락 상한을 10,000자로 밝히고 있어(넘으면 파일로 빠짐) 그 아래에 여유 400자를 뒀습니다. 신선도 한 줄이 가장 길어도 인계서 본문에 8,739자 이상이 남습니다.

## [1.0.0-beta.2] — 2026-11-20

처음 쓰는 사람이 설치하고 바로 써 볼 수 있게 정리한 첫 공개 릴리스입니다. `1.0.0-beta.1`(태그만 있고 릴리스 노트는 없었음)에 아래가 더해졌습니다.

### 추가
- **`/baton-setup`** — 설치 후 한 번. 이 저장소의 Claude Code 세션 기록과 git 이력을 **읽기만** 해서 세션 끊기 알림 문턱, 인계서 제안 문턱, 인계서를 넣을 말 추가, 인계서 검사가 막을 개인 자료(이름·이메일 등) 후보를 제안합니다. 고른 값만 `~/.config/baton/config.json`(파일 600)에 씁니다. 세션이 10개 미만이면 기본값을 그대로 권합니다.
- 설정 파일 우선순위: 환경변수 > 저장소 절 > 전역 절 > 기본값. 지금 값은 `python3 lib/config.py`로 봅니다.
- 인계서 검사가 `/baton-setup`에서 고른 개인 자료 단어도 막습니다. 찾은 단어는 다시 출력하지 않습니다.
- `/baton-doctor`가 설정 파일이 읽히는지도 봅니다.
- `CHANGELOG.md`. 영어 `README.md`(한 줄 정의·설치·실제 `/drift` 출력·Limitations)와 한국어 전문 `README.ko.md`.
- `.github/workflows/traffic.yml` — GitHub 트래픽(조회·클론·유입 경로·많이 본 경로)을 매일 `traffic-data` 브랜치에 JSON으로 쌓습니다. 트래픽 API는 14일치만 남기 때문입니다. 소유자가 `TRAFFIC_TOKEN` 시크릿(fine-grained, Administration: Read-only)을 등록해야 돕니다. 플러그인 동작과는 무관합니다.

### 바뀐 것
- 버전 표기 `1.0.0-beta.1` → `1.0.0-beta.2` (Claude Code·Codex 매니페스트 셋).
- 소개의 중심을 개념 지도(driftmap)로 옮겼습니다. 매니페스트 설명은 영어 우선입니다.
- 훅 명령의 경로 표기를 `"$CLAUDE_PLUGIN_ROOT"/hooks/…`에서 `"${CLAUDE_PLUGIN_ROOT}/hooks/…"`로 바꿨습니다(공식 플러그인 디렉터리 사전 점검 표기). 셸에서는 같은 값입니다.
- `.claude-plugin/plugin.json`에서 `hooks` 필드를 뺐습니다. Claude Code는 `hooks/hooks.json`을 자동으로 읽고, 디렉터리 점검은 이 필드를 경고로 냅니다. Codex 매니페스트에는 그대로 둡니다.
- 관찰 로그 경로 `BATON_LOG`의 `~`를 펼칩니다.

### 실사용 측정 (만든 사람 한 명, 처음 공개하는 수치)

기간이 수치마다 다릅니다. 설치 전은 2026-08-31 ~ 10-04(W36~W40), 설치 뒤 세션 기록은 10-19 ~ 11-20(W43~W47), 관찰 로그는 설치일 10-04부터 **11-20 20:10(KST)까지**입니다. 세 값 모두 11-20 저녁에 잰 값이라 나중에 다시 돌리면 늘어납니다 — 아래 명령은 같은 기간으로 자릅니다. 다른 사람의 사용 방식에서도 같은지는 아직 모릅니다.

| 무엇을 | 설치 전 | 설치 뒤 | 출처 |
|---|---|---|---|
| "이어서·어디까지"로 시작한 세션 중 첫 5호출 안에 에이전트가 `HANDOFF.md`를 다시 연 세션 | 42개 중 41개 (W36~W40) | 11개 중 3개, 그중 2개는 일부만 (W43~W47) | 설치 전: `docs/research/LOOP_PLAN.md` "정정" 절 · 설치 뒤: `python3 observer/research/usage_week.py --since 2026-08-31 --until 2026-11-20` |
| 같은 세션의 앞 5호출 입력 토큰(주별 중앙값) | 339K~404K | 446K~494K | 같은 명령 |
| 첫 호출 컨텍스트(주별 중앙값) | 61K~71K | 77K~87K | 같은 명령 |
| 인계서 주입 | — | 프롬프트 2,197개 중 270번(세션 40개, 저장소 5곳 · 자동 실행 세션도 섞여 있음) | `~/.cache/baton/runs.jsonl`의 `event=prompt`·`acted.handoff_lines>0` (아래 명령) |
| 인계서 저장 시 검사 | — | 38번 중 20번 문제를 돌려줌 | 같은 로그의 `event=handoff_check`·`problems>0` (아래 명령) |

관찰 로그 수치를 같은 시각으로 자르는 명령:

```sh
jq -s '[.[] | select(.ts <= "2026-11-20T20:10:10+0900")] as $r
  | ($r | map(select(.event == "prompt"))) as $p
  | ($p | map(select((.acted.handoff_lines // 0) > 0))) as $i
  | {prompts: ($p | length), injected: ($i | length), sessions: ($i | map(.session_id) | unique | length),
     checks: ($r | map(select(.event == "handoff_check")) | length),
     problems: ($r | map(select(.event == "handoff_check" and .problems > 0)) | length)}' ~/.cache/baton/runs.jsonl
# → {"prompts":2197,"injected":270,"sessions":40,"checks":38,"problems":20}
```

- **세션 기록 수치는 기록이 남아 있는 동안만 다시 나옵니다.** Claude Code는 세션 기록을 기본 30일 뒤 지웁니다(`cleanupPeriodDays`). 11-21에 같은 명령을 다시 돌리자 W43의 상태 세션 1개가 이미 빠져 있었습니다(나머지 주는 같은 값).

- **다시 여는 일은 줄었지만 토큰은 줄지 않았습니다.** 같은 기간 첫 호출부터 고정 맥락이 커져(다른 플러그인·지침) 주입 효과와 분리하지 못했습니다. 스냅샷 실험(같은 저장소·같은 프롬프트)에서는 상태 질문 입력 토큰이 40~54% 줄었습니다(`docs/research/LOOP_PLAN.md` 루프 1·2).
- 설치 전 세션 기록은 Claude Code가 지워서 지금은 다시 잴 수 없습니다. 설치 전 값은 09-30에 같은 집계기로 잰 기록입니다.
- 설치 뒤 표본은 11개 세션입니다. 방향을 보여 줄 뿐 효과의 크기를 말하기에는 적습니다.

### 알려진 한계
- 훅 메시지·스킬·명령 출력은 한국어입니다. 인계서 주입의 기본 트리거도 한국어 말과 `handoff`뿐이라 영어 "continue"에는 반응하지 않습니다. `/baton-setup`(`BATON_HANDOFF_TRIGGERS_EXTRA`)으로 말을 더할 수 있습니다.
- 인계서 검사기의 오탐: 32자 넘는 `sk-` 브랜치 이름, CI 러너의 홈 경로, 시각 문자열을 값으로 둔 secret 대입. 놓치는 것: `postgres://user:pw@host`, `npm_`·`hf_` 토큰, JWT가 아닌 Bearer 값.
- 인계서를 `Edit`로 여러 번 나눠 쓰면 중간 저장마다 "필수 절 없음"이 돌아옵니다.
- 인계서 주입은 훅이 실행된 폴더의 git 최상위에서 `HANDOFF.md`를 찾습니다. Claude Code는 프로젝트 폴더에서 훅을 돌리므로 평소에는 문제가 없습니다.
- Codex: 세션 끊기 알림·인계서 제안·저장 시 자동 검사는 돌지 않습니다(세션 기록 형식과 `apply_patch` 차이). 스킬이 검사기를 직접 돌립니다. `/baton-setup`은 Codex 세션을 세지 않습니다.

## [1.0.0-beta.1] — 2026-10-01

태그 `v1.0.0-beta.1`. GitHub 릴리스는 만들지 않았습니다.

### 추가
- **인계서 검사기** (`lib/handoff_check.py`, 훅 `hooks/handoff-check.py`) — `HANDOFF.md`를 저장하면 필수 8절·200줄·9,000자·20줄 넘는 코드 블록·전체 diff·비밀값·홈 절대경로를 보고 에이전트에게 돌려줍니다.
- **인계서 제안** — 세션에서 파일을 3개 이상 고쳤는데 인계서가 그대로면 세션에 한 번 제안합니다. 문턱 3은 세션 94개에서 1~2개 고친 세션은 인계서를 16%, 3개 이상은 67% 썼던 경계입니다.
- README "쓰는 법" 절과 효과 수치의 성격(추정·스냅샷) 표기.

### 바뀐 것
- 인계서 주입·개념 지도 알림 훅의 출력을 일반 출력에서 `additionalContext` JSON으로 바꿨습니다. Codex는 일반 출력을 모델 맥락에 넣지 않습니다(0.155.1 실제 세션으로 확인).

### 고친 것
- 개념 지도 알림의 캐시 정리가 `~/.cache/baton/` 전체에서 7일 넘은 파일을 지워 관찰 로그와 설치 사본까지 지우던 문제. 이제 `~/.cache/baton/drift/`만 지웁니다.

## 첫 공개 (2026-10-01, 버전 표기 0.1.0)

- 훅 넷: 개념 지도 신선도 알림, 0건 구분 가드, 인계서 on-demand 주입(+관찰 로그), 세션 끊기 알림.
- 스킬 `driftmap`·`baton`, 명령 `/drift`·`/promote`·`/baton-doctor`·`/baton-explain`.
- Claude Code·Codex 매니페스트, 설치 사본 스크립트(`tools/stage-plugin.sh`).
- 개인 자료를 정리하며 공개 저장소 이력을 이 커밋 하나로 새로 시작했습니다(`DECISIONS.md` 2026-10-01).

[1.0.0-beta.2]: https://github.com/sulabo/baton/compare/v1.0.0-beta.1...v1.0.0-beta.2
[1.0.0-beta.1]: https://github.com/sulabo/baton/releases/tag/v1.0.0-beta.1
