---
description: Handoff promotion review. Finds constraints that survived several days and decisions that quietly dropped out. 인계서 승격 검토. 여러 날 살아남은 제약과 조용히 빠진 결정을 찾는다.
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/lib/promote.sh *)
---

Run the promotion review script on the current repository. Reply in the user's language.

1. Run `${CLAUDE_PLUGIN_ROOT}/lib/promote.sh <repo path>`.
2. **If some versions could not be counted because of a format mismatch, report that line first.** If you do not
   tell "none" apart from "could not count" for a 0, this review becomes a lie.
3. Sort the candidates by kind. A repeated failure is a constraint; a dropped item is a decision that leaked out.
4. **Do not write `DECISIONS.md` for the owner.** Go only as far as a draft of the decision, and leave "rejected
   alternatives" and "reason" blank. Write them down when the owner tells you.

If `$ARGUMENTS` is given, use that repository.
