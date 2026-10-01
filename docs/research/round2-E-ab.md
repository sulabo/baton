# Round2-E A/B — 세션 시작 주입이 초반 읽기를 실제로 줄이는가

**결론부터.** 인계서 **전문**을 세션 시작에 주입하면 초반 5턴의 읽기가 준다
(인계서 재독 5/5 → 0/5, 읽은 파일 중앙값 4개 → 1개). 그러나 1라운드에서 설계한
**세 절 카드(3KB)는 줄이지 못했고 오히려 늘렸다**(재독 5/5, 파일 4개 → 5개).
"다음 행동" 절을 더한 네 절 카드(4KB)도 재독 5/5다. 이유는 하나로 모인다 —
**다음 행동이 가리키는 본문은 인계서의 임의의 절에 있어서 고정 절 카드가 담을 수 없다.**

1라운드(`round1-E.md`)의 "카드 2.7KB가 인계서 재독을 대신한다"는 상한 추정은 **기각**이다.
대신할 수 있는 것은 전문(12KB)이고, 크기 비는 0.033이 아니라 **0.15**(12,187 / 82,594)다.

## 설계

같은 첫 프롬프트 `핸드오프 읽고 이어서 해줘`로 실제 `claude -p` 세션을 돌렸다.
대상은 문서 저장소의 **스냅샷 복사본**(커밋 `12cd82a`를 `git archive`로 풀고 새로
`git init`, 원격 없음). 세션마다 `git checkout -- . && git clean -fd`로 되돌렸다. 원본 저장소는
건드리지 않았다(HEAD·`HANDOFF.md` 수정 시각 불변 확인).

| arm | 세션 시작에 주입한 것 | 크기(UTF-8) |
|---|---|---|
| off | 없음 | 0 |
| on | 3절 카드 — 목표·완료 조건 / 관련 파일 / 실패한 접근법. 헤더 "세 절은 이 카드가 전문이다" | 2,755 B |
| full | `HANDOFF.md` 전문 + 헤더 "파일을 다시 열 필요 없다. 그대로 이어서 진행한다" | 12,187 B + 헤더 |
| card4 | 4절 카드 — 위 셋 + 남은 리스크와 다음 행동. 헤더는 full과 같은 문장 | 4,054 B |

주입 통로는 SessionStart 훅(`--settings` JSON으로 그 세션에만 추가). 훅 stdout이 문맥에 들어가는 것은
1턴 파일럿에서 모델이 카드 첫 줄을 그대로 인용해 확인했고, 모든 주입 세션의 stream-json
`hook_response`에 카드가 찍혀 있다(표의 `card` 열).

arm마다 5세션, `--max-turns 6`, 모델 `claude-fable-5-1`, permissionMode auto(사용자 전역 설정 그대로).
실행 순서: off/on 교대 10회(2라운드) → full 5회(3라운드) → card4 5회(4라운드). **full·card4는 off와
교대하지 않았다.** 같은 날 같은 스냅샷이지만 시간 편향은 안 지운 것이다.

측정은 `round1_e.py`와 같은 방식이다 — `Read`의 file_path, `Grep`/`Glob`의 path, **Bash 명령 안의
파일 인자**(cat·sed·grep 전부)를 읽기로 세고, 턴은 API 메시지 id 단위, 메인 스레드만.

## [MEASURED] 초반 5턴 — arm별 (각 n=5)

| arm | 읽은 파일 수 중앙값 / 평균 | 읽은 파일 바이트 중앙값 / 평균 | `HANDOFF.md` 재독 | 턴 수 중앙값 | 세션 비용 평균(USD) |
|---|---|---|---|---|---|
| off | 4.0 / 3.6 | 219,465 / 191,943 | **5/5** | 6.0 | 1.00 |
| on (3절 카드) | 5.0 / 4.8 | 248,628 / 209,441 | **5/5** | 6.0 | 1.05 |
| full (전문) | **1.0 / 1.6** | **91,344 / 124,698** | **0/5** | 4.0 | 0.68 |
| card4 (4절 카드) | 3.0 / 3.0 | 168,627 / 155,737 | **5/5** | 5.0 | 0.88 |

초반 3턴만 보면 차이가 더 벌어진다 — 파일 수 중앙값 off 2 / on 5 / full 1 / card4 2,
바이트 중앙값 off 103,531 / on 248,628 / full 91,344 / card4 103,531.

## [MEASURED] 인계서를 어떻게 다시 읽었나

| arm | 첫 턴 첫 명령 | 재독 형태 |
|---|---|---|
| off | 5 전부 `git status … && cat HANDOFF.md` | 전문 `cat` 5/5 |
| on | 5 전부 `git status … && cat HANDOFF.md`. 둘은 "핸드오프 **전문**을 먼저 확인하겠다"고 말함 | 전문 `cat` 5/5 |
| full | 5 전부 `git status && git log && ls -d 리서치_전달방식_* …` — 인계서 없이 원장으로 직행. 첫 발화 "핸드오프대로 … 이어갑니다" | 없음 0/5 |
| card4 | 5 전부 `grep -n "추론" HANDOFF.md` → `sed -n 1,60p HANDOFF.md` | **부분** 읽기 5/5 (1~60행 = 6,588 B, 전문의 54%) |

card4 다섯 세션의 발화가 같은 말을 한다: "다음 행동은 추론 A~F 답 받기인데, **추론 내용 자체는
카드에 없으니** 인계서에서 확인하겠다." 이 인계서의 추론 A~F는 `## 다음 세션 첫 질문` 절에 있고,
그 절은 템플릿 8항목 어디에도 없다. 고정 절로 뽑는 카드는 이것을 구조적으로 놓친다.

full 세션이 4턴 만에 끝난 것은 실패가 아니다. 인계서의 다음 행동이 "소유자 답 받기"라서
다섯 세션 모두 추론을 다시 제시하고 답을 기다리며 스스로 끝났다. 그게 이어받기의 정답 행동이다.

## 실행 명령

```bash
# 스냅샷 (원격 없음). 세션 기록 폴더는 이 경로로 갈린다
mkdir -p <snapshot> && git -C "<project>" archive 12cd82a | tar -x -C <snapshot> \
  && git -C <snapshot> init -q && git -C <snapshot> add -A && git -C <snapshot> commit -qm snapshot

# 실행 (arm 순서대로 교대, 결과는 <project>/.baton/round2/ — gitignore)
python3 "<baton>/observer/research/round2_e_ab.py" run --repo <snapshot> --data "<project>/.baton/round2" --n 5 --max-turns 6            # off,on
python3 "<baton>/observer/research/round2_e_ab.py" run --repo <snapshot> --data "<project>/.baton/round2" --n 5 --max-turns 6 --arms full
python3 "<baton>/observer/research/round2_e_ab.py" run --repo <snapshot> --data "<project>/.baton/round2" --n 5 --max-turns 6 --arms card4

# 표의 모든 숫자 (K=5, K=3)
python3 "<baton>/observer/research/round2_e_ab.py" count --repo <snapshot> --data "<project>/.baton/round2" --k 5
python3 "<baton>/observer/research/round2_e_ab.py" count --repo <snapshot> --data "<project>/.baton/round2" --k 3

# 카드 자체
python3 "<baton>/observer/card.py" "<project>/HANDOFF.md"                       # 3절, 3072 B 한도
python3 "<baton>/observer/card.py" "<project>/HANDOFF.md" --with-next --limit 6144   # 4절
```

원자료: `<project>/.baton/round2/{off,on,full,card4}-{1..5}.jsonl`(stream-json 원문), `runs.json`(세션 id·비용·턴),
`count-k5.txt`·`count-k3.txt`(집계 출력). 세션 20개 비용 합계 USD 18.02(off 5.01 · on 5.23 · full 3.39 · card4 4.39),
파일럿 2개 1.42.

## 못 센 것 / 조심할 것

- **n=5/arm, 유의성 검정 없음.** 저장소 하나·인계서 한 판이다. 다른 인계서(다음 행동이 템플릿 절 안에서
  끝나는 판)에서는 카드가 통할 수도 있다 — 그러나 그것을 미리 알 방법이 없다는 것이 이 결과의 요지다.
- **바이트는 상한.** `sed -n 1,60p`도 파일 전체 크기로 셌다. card4의 실제 인계서 읽기는 6.6KB지 12KB가 아니다.
  full의 91,344는 `카테고리_트리.md` 한 파일 크기다(다섯 중 셋이 그것만 읽음).
- **on과 card4는 두 가지가 동시에 다르다**(헤더 문장 + 다음 행동 절). 어느 쪽이 부분 읽기로 바꿨는지는 못 가른다.
  full은 헤더가 card4와 같으므로 "헤더만으로는 안 되고 본문이 있어야 한다"까지는 말할 수 있다.
- **full·card4는 off와 교대 실행하지 않았다**(위 설계 절).
- **비용은 턴 수와 얽혀 있다.** full이 싼 것은 주입 12KB를 포함하고도 세션이 일찍 끝나서다.
- 디스크에 없는 읽기 3건(on-4: `~/.claude/mistake-log.md`, 스냅샷에 없는 `리서치_자동화…` 둘). 바이트에서 빠짐.
- 서브에이전트 호출 0건이라 숨은 읽기는 없다.
- `--max-turns` 도달은 `claude`가 rc=1·`error_max_turns`로 끝낸다. 처음 러너가 이걸 실패로 보고 2회 후 멈췄다.
  데이터는 온전했고 기준을 고쳐 재개했다(`runs.json`에 `subtype` 기록).
- API의 `num_turns`(예: on-3이 11)와 메시지 id로 센 턴(6)은 다르다. 표는 후자다.

## 판정

- **후보 E, 3절 카드 설계: 중단.** 안 주는 것보다 나쁘다.
- **후보 E, 전문 주입: 계속 → 구현 후보 확정.** 인계서 재독이 사라지고 초반 읽기가 파일 4 → 1개로 준다.
  이득의 크기는 1라운드 추정보다 작다(비 0.033 → 0.15). 진실 신호 없이 시험할 수 있는 유일한 후보라는
  점은 유지된다 — 분류를 안 하기 때문이다.
- **일반화되는 교훈:** 카드가 무엇을 잘라도 "이어서 해줘"가 필요로 하는 절이 빠질 수 있다. 자를 권한은
  카드가 아니라 **인계서를 쓰는 쪽**에 있다. 주입 크기 = 인계서 길이이므로, 인계서를 짧게 쓰는 규칙이
  곧 비용 규칙이 된다.

구현 전에 소유자가 정할 것: ① 전문 주입을 baton SessionStart 훅으로 넣을지(현재 플러그인은 미설치)
② 크기 상한(예: 16KB 초과 시 앞부분만 + 안내) ③ 대상은 저장소 루트 `HANDOFF.md`만인지
④ 헤더 문장 "파일을 다시 열 필요 없다. 그대로 이어서 진행한다"를 그대로 쓸지.

## 두 번째 저장소(game-old) — 2026-09-27 재실행, 10/10 유효

첫 시도(아래 절)의 결함 셋을 피해 다시 돌렸다. 스냅샷은 작업 트리에서 미추적 포함으로 떠 `<baton>/.data/snapshots/steam`에 두었고
(`specs/STACK-SPIKE.md` 포함 확인), off/full 교대 5+5, `--max-turns 6`. 10세션 전부 `error_max_turns`(정상 종료, rc=1), 한도 걸림 0.

| arm | n | 읽은 파일 수 중앙값(평균) | 바이트 중앙값 | 인계서 읽기(집계기) | 인계서 **본문** 읽기 | 비용 평균 |
|---|---|---|---|---|---|---|
| off | 5 | 7.0 (7.4) | 216,161 | 5/5 | **5/5** (`cat`·Read) | 0.50 |
| full | 5 | 6.0 (6.2) | 205,056 | 1/5 | **0/5** | 0.44 |

- 집계기의 full 1/5(full-1)는 `ls -la … HANDOFF.md … || stat …` — 수정 시각만 봤고 본문은 안 읽었다. 그래서 본문 기준 0/5.
- 방향이 문서 저장소(off 5/5 → full 0/5)와 같다. **두 저장소에서 같은 결과 — 소유자 결정 (a)가 닫혔다.**
- 파일 수는 1개 줄었지만 바이트는 약 5% 차이라 작다. 이 저장소에서 초반 읽기의 대부분은 인계서가 아니라 `DECISIONS.md`(93KB)·`STRUCTURE.md`·`specs/`다.
  즉 전문 주입이 없애는 것은 "인계서 재독"이고, 초반 읽기 전체를 줄이는 효과는 저장소마다 다르다. 토큰 절감을 주장할 때 이 둘을 섞지 않는다.
- 원본 무변경: 10세션 기록에 Write/Edit 0건, 원본 저장소 경로 0건. 같은 시각 원본 저장소의 파일 변경은 소유자가 그 저장소에서 따로 연 세션(`<sid>`)의 것이다.
- 집계기의 "reads outside snapshot 2"는 스냅샷에 없는 `.omc/state`·`.omc/handoffs`를 `ls 2>/dev/null`로 본 것으로 보인다(원본 경로 아님). 확정은 못 했다.
- 비용 USD 4.69.

```bash
python3 observer/research/round2_e_ab.py run   --repo .data/snapshots/steam --data .data/steam-round2b --n 5 --arms off,full
python3 observer/research/round2_e_ab.py count --repo .data/snapshots/steam --data .data/steam-round2b --k 5
```

## 두 번째 저장소 첫 시도(09-22) — 미완, 유효 세션 4개

소유자 결정(09-22): 구현 전에 인계서 구조가 다른 저장소에서 off/full 교대 5+5를 한 번 더 한다.
돌렸으나 **10세션 중 4세션만 유효**하다. 판정을 내리지 않는다.

| run | 유효 | 첫 발화 | 인계서 읽기 |
|---|---|---|---|
| off-1 | ○ | "핸드오프를 읽고 현재 저장소 상태를 확인하겠습니다" | `cat HANDOFF.md` |
| full-1 | ○ | "핸드오프의 다음 행동은 48°/52°와 카메라 추종 충돌 정리 → Godot 스파이크입니다" | `head -5 HANDOFF.md` (머리글만) |
| off-2 | ○ | "핸드오프를 읽고 현재 저장소 상태를 확인하겠습니다" | `cat HANDOFF.md` |
| full-2 | ○ | "핸드오프의 다음 행동 1번부터 이어갑니다" | `head -3 HANDOFF.md` (머리글만) |
| off-3 · full-3 | × | 2턴 뒤 "You've hit your session limit" | — |
| off-4·5 · full-4·5 | × | 1턴, 비용 0, 같은 메시지 | — |

방향은 문서 저장소와 같다 — 전문을 넣은 둘은 인계서를 통째로 읽지 않고 다음 행동으로 바로 갔고, 안 넣은 둘은 `cat`했다.
그러나 n=2라 근거로 쓰지 않는다. 읽은 파일 수도 여기서는 비교하지 않는다(아래 결함 ①이 두 arm의 읽기를 함께 부풀렸다).

**이 실행을 망친 것 셋 — 다시 할 때 전부 피한다.**

1. **스냅샷을 추적 파일만으로 떴다.** 게임 인계서의 다음 행동이 가리키는 `specs/STACK-SPIKE.md`가 미추적이라 스냅샷에 없었고,
   네 세션 전부 그것을 찾아 `find ~/Documents`로 실제 저장소까지 갔다(읽기 전용 명령만 썼고 원본은 무변경 — 수정 시각·`git status`로 확인).
   스냅샷은 작업 트리에서 **미추적 포함, ignore 제외**로 뜬다: `git ls-files -co --exclude-standard -z | tar --null -T - -cf - | tar -x -C <snapshot>`.
2. **세션 사용량 한도.** 5번째 세션부터 한도에 걸렸다(04:16, 07:50 리셋). `claude -p`는 이때 subtype=success·is_error=true로 끝나 러너가
   정상으로 오판했다 — 기준을 고쳤다(`is_error`면 제외). 20세션 넘게 돌리는 날은 한도를 먼저 본다.
3. **스냅샷을 세션 스크래치에 뒀다.** 세션이 날짜를 넘기며 폴더가 비워져 바이트 집계가 불가능해졌다(`missing 49`).
   스냅샷은 `<baton>/.data/`(gitignore) 같은 살아남는 곳에 둔다.

원자료: `<baton>/.data/steam-round2/`(gitignore). 스냅샷은 사라졌고 세션 jsonl만 남았다.

## 소유자 결정 (2026-09-22, A/B 결과를 보고)

- 구현 전에 두 번째 저장소 A/B를 먼저 한다 → 09-22 첫 시도 미완, **09-27 재실행으로 닫힘**(off 본문 재독 5/5 → full 0/5).
- **인계서 상한은 200줄.** 실측으로 200줄은 13~21KB(문서 저장소 96B/줄 → 18KB, 게임 67B/줄 → 13KB, baton 110B/줄 → 21KB).
  훅은 200줄까지 넣고 넘치면 "나머지는 HANDOFF.md에" 한 줄을 붙인다.
- 업무를 세션 단위로 나누면 **업무 단위로 인계서를 나누는** 안을 검토한다. 제안: 루트 `HANDOFF.md`는 항상 하나(진행 중인 업무와
  그 인계서 위치만, 짧게), 업무별 인계서는 `handoffs/<업무>.md`. 훅은 루트만 주입한다 — 프롬프트 "핸드오프 읽고"가 어느 파일인지
  가려낼 수 없기 때문이다. 인계서 스킬(`~/.claude/skills/handoff/SKILL.md`) 변경이 따라와야 한다. **미결.**
