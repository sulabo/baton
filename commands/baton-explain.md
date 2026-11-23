---
description: Shows what the baton rules decide for this prompt — whether the handoff goes in, which concepts are candidates, and the task type. It only shows the verdict and changes nothing. 이 프롬프트에 baton 규칙이 무엇을 판단하는지 보여 준다 — 인계서를 넣을지, 어느 개념이 후보인지, 작업 종류. 판단만 보여 주고 아무것도 바꾸지 않는다.
---

Run it in the current repository with **the prompt passed on standard input** as below, and copy the output as it is.
Do not put the argument directly into a shell string — a prompt with quotes, `$(…)` or backticks would break or run.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/rules.py" explain - <<'BATON_PROMPT'
$ARGUMENTS
BATON_PROMPT
```

- If `$ARGUMENTS` is empty, only say "give me the prompt to judge as the argument" (in the user's language) and stop.
- The verdict states are MATCHED (exactly one rule matched) · AMBIGUOUS (two or more) · NO_MATCH (none); when the
  material is missing, NO_MAP (no concept map) · UNCONFIGURED (no domain set) — the last two are not 0, they mean
  "could not count". MACHINE means the message came from another session or a task notification, so concepts and the
  task type were deliberately not counted. Do not add an interpretation.
- What actually goes in today is the handoff and the concept index (a concept section only with
  `BATON_CONCEPT_INJECT=on`). The rest is observation — step 1 of the North Star roadmap.
- The `concept index` line (`개념 색인` in Korean output) shows whether the index would go in, and its size (characters
  and concepts), if this prompt were the session's first human prompt. This command does not look at the session's
  memory, so in a session that already has the index, it does not actually go in.
- The output language follows `BATON_LANG` (or the system locale). Reply to the user in their language.
