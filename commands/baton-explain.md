---
description: 이 프롬프트에 baton 규칙이 무엇을 판단하는지 보여 준다 — 인계서를 넣을지, 어느 개념이 후보인지, 작업 종류. 판단만 보여 주고 아무것도 바꾸지 않는다.
---

아래처럼 **프롬프트를 표준 입력으로** 넘겨 현재 저장소에서 돌리고, 출력을 그대로 옮겨라. 인자를 셸 문자열에 직접 넣지 않는다 — 따옴표·`$(…)`·백틱이 든 프롬프트가 깨지거나 실행된다.

```bash
python3 "$CLAUDE_PLUGIN_ROOT/lib/rules.py" explain - <<'BATON_PROMPT'
$ARGUMENTS
BATON_PROMPT
```

- `$ARGUMENTS`가 비어 있으면 "판단할 프롬프트를 인자로 달라"고만 말하고 멈춘다.
- 판단 상태는 MATCHED(규칙 하나만 맞음) · AMBIGUOUS(둘 이상) · NO_MATCH(없음), 재료가 없으면 NO_MAP(개념 지도 없음) · UNCONFIGURED(도메인 미설정) — 뒤의 둘은 0건이 아니라 못 셈. 해석을 덧붙이지 않는다.
- 지금 실제로 넣는 것은 인계서뿐이다(개념 절은 `BATON_CONCEPT_INJECT=on`일 때만). 나머지는 관찰이다 — 북극성 길 단계 1.
