---
name: handoff
description: Write a session handoff (HANDOFF.md). When a piece of work is done, the topic changes, or the conversation gets long, leave the current state in a file so the next session can pick it up. Before writing, scan past handoffs to decide whether anything should be promoted to DECISIONS.md. Triggers on requests such as "write a handoff", "leave a handoff for the next session", "update HANDOFF.md", "review what to promote to DECISIONS.md"; the baton Stop hook can also ask for it once per session. 세션 인계서(HANDOFF.md) 작성. 작업 하나가 끝났거나 주제를 바꾸거나 대화가 길어졌을 때, 다음 세션이 이어받을 수 있게 현재 작업 상태를 파일로 남긴다. 쓰기 전에 과거 인계서를 훑어 DECISIONS.md로 승격할 것이 있는지 함께 판정한다. "핸드오프 작성해줘", "인계서 남겨줘", "승격 검토"에도 발동.
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/lib/promote.sh *) Bash(python3 ${CLAUDE_PLUGIN_ROOT}/lib/handoff_check.py *)
---

# Handoff — writing a session handoff and reviewing promotions

Reply in the user's language. Write HANDOFF.md in the language of the existing file; if there is none, in the
language the user writes in. Both templates are at the end of this file.

## Purpose

Instead of dragging a long conversation on, leave the work state in a short file and pick it up in a new session.
Measured: cost -44.7% compared with a cold start, with accuracy equal or better (internal controlled experiment).
The core value is the "Failed approaches" item — it keeps the next session from repeating the same dead ends.

**Second purpose: promotion review.**
The handoff is overwritten every time, so each version is short-lived. But **what repeats across versions** is not.
If the same judgment was made three times over, it is not session state but a standing rule, and it belongs in
`DECISIONS.md`, not `HANDOFF.md`. It means you are paying to make that judgment again every time.

Past versions are not archived separately. **The git history is the archive.**

## Procedure

### 1. Promotion review (do this before writing)

**The script does it. Do not put git commands together by hand.**

```bash
${CLAUDE_PLUGIN_ROOT}/lib/promote.sh [repo path] [versions (default 8)]
```

If HANDOFF.md is not tracked, the script says so and stops. Put that fact and the advice to run `git add HANDOFF.md`
in your report. While it is untracked, this review can never work.

There are three signals, and **they are different in kind.**

| Signal | What it looks at | Detected automatically |
|---|---|---|
| **Repeated failure** | The same "Failed approaches" item survives on **3 or more different days** | Yes |
| **Dropped** | A standing constraint that was in 2 or more earlier versions is gone from the latest | Yes |
| **Reversal** | A decision is turned around | **No.** Only when the owner points it out |

**Reversal was left out of automatic detection because we tried it and it did not work.** It is a comparison of
meaning, so counting strings cannot catch it. Measurement showed instead that **dropped items are the more valuable
signal**. In one repository, lines like these lived only in the handoff and had quietly dropped out:

```
- These figures are published only rounded (owner decision, date)
- Never push directly to the upstream repository
- Do not put personally identifying information in outputs
```

All three are **decisions the owner made** and belong in `DECISIONS.md`. Even a record of a reversal had dropped out
that way.

Dropped candidates that carry a decision marker (owner decision, final, forbidden, never, adopted, lifted, canonical,
a decision ID; in Korean handoffs 소유자 결정·확정·금지·절대·채택·해제·정본) are listed first. Not all of them are worth
promoting. **A person decides which are finished work and which are live constraints.**

**Count days, not versions. This one choice decides almost the whole signal.**

A handoff is committed several times a day, and each time the "Failed approaches" section is copied over whole.
Measured 2026-09-15: of one repository's last 8 versions, **3 were identical to the version before.**
Counted by commit, that copying shows up as "repetition".

| Unit counted | Items that survived 3 or more times |
|---|---|
| 8 commits | 8 |
| **8 different days** | **1** |

(Measured 2026-09-15. As the handoff history grows, the window of the last 8 versions moves and the same numbers will
not come back. The evidence is the mechanism, not the number: **counting by commit inflates same-day copies into
repetition.**)

**7 of the 8 were by-products of committing several times on the same day.** The remaining one is a real standing
constraint: "do not change figures or attribution in the name of tone". In a game repository, too, 13 went down to 9.

So the script uses **only the latest version of each day**. Surviving on different days means surviving across
several work sessions, and that is the evidence of a standing rule.

| Repeated | Action |
|---|---|
| 3 or more different days | Raise it as a promotion candidate |
| 2 days | Do not promote it. **Shorten it to one line** in the handoff |
| 1 day | Leave it |

**0 can mean "could not count", not "none".** Handoff section headings differ between repositories. One version has
`## E. 실패한 접근법`, another has no such section at all. The script counts the versions where extraction came back
empty as "format mismatch", takes them out of the denominator, and prints that. **Copy that line into your report.**
The script reads both the English and the Korean template headings.

### 2. Write the handoff

Write `HANDOFF.md` at the repo root (overwrite it if it exists — keep only the latest copy). If there is no
repository, write it in the current working directory.

**Update, do not rewrite.** If `HANDOFF.md` exists, start from that file, not from memory: carry forward every line
that is still true, move finished next actions to "Changes made", and delete only what you know is obsolete. Lines
under "Failed approaches", "Promotion candidates" and "Rejected" are meant to survive across sessions. When you save,
the checker compares the file with its last committed version and lists the lines that are gone (a warning, not a
block): lines in those three sections, and lines elsewhere that carry a decision or constraint marker.

**Mark what must be read.** In "Files and symbols", put `(must read)` (Korean: `(필독)`) after the path of at most 3
entries the next session has to read before acting. The injection hook repeats them in one line right after the
freshness line, so they survive truncation. The checker warns when more than 3 are marked.

Fill in the 8 items of the template below. Keep it short — no full conversation, no repeated explanations, no raw
tool output. **Stay within 200 lines and 8,700 characters** (lines: owner decision 2026-09-22; characters: the checker
limit, the amount that still goes in whole after the injection hook adds its header, the freshness line and the
concept index. Hook output over the 10,000-character cap in the Claude Code docs is moved to a file, so the hook keeps
everything, header and freshness line included, within 9,600 characters). When a handoff or status question comes in,
the plugin hook puts this file into context up to 200 lines and 9,600 characters of hook output — anything past that
is left out. Put the next actions near the top.
**The -44.7% cost figure was measured on the 7-item version, before the promotion candidates section existed.** The
8th item was added later.

Honesty: write what is not verified as "unverified", and for partial completion say exactly which part is left. Base
what you write on actual files and command results, not on summaries or memory.

**A handoff is a hypothesis from the time it was written, not a fact.** The next session may read this file days
later, in another folder, in a repository with commits piled up in between. When it injects the file, the hook adds
the written date, how many days ago that was, and the number of commits since; the reader checks only the one or two
claims the next action depends on. The writer has three jobs.

- **Put the written date in the first line** (`written: YYYY-MM-DD`; `작성: YYYY-MM-DD` in a Korean handoff). The hook
  counts the age from this date. Without it, the hook uses the last commit date of HANDOFF.md.
- **Write each next action as a pair: "current state (evidence) → what to do".** A bare command gets run as it is even
  after the state has changed. With the pair, the reader checks the state first and decides the action again if the
  state is different.
  Example: "`split-notice.py` is registered but has never fired in a real window (the installed copy is the 10-04
  version) → reinstall, then check in a new window".
- **Add how each verified fact was checked** (command, file, date), so the reader can check it again the same way.

After writing, run the checker, fix what it reports, then commit.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/lib/handoff_check.py HANDOFF.md
```

It checks the 8 required sections, 200 lines, 8,700 characters (including the must-read line, which goes in twice),
code blocks over 20 lines, full diffs, secrets and absolute home paths. If a list item under "Verified facts and
decisions" ("확인된 사실과 결정" in the Korean template) has no [V] or [?] mark, it warns without blocking. It also warns,
without blocking, about lines dropped since the last committed version and about more than 3 must-read marks. On Claude Code, saving with `Write`/`Edit` makes a hook run the same
check automatically and hand the problems back. Codex's `apply_patch` gives the hook no path, so run it yourself there.

### 3. Commit

Commit `HANDOFF.md`. Without a commit, the next version cannot see this one, and the promotion review does not work.

### 4. Tell the user

Tell the user in two lines.

- "In a new session, start with 'read HANDOFF.md and continue'." (Korean: "새 세션에서 'HANDOFF.md 읽고 이어서 해줘'라고
  시작하세요.")
- If there are promotion candidates: what, why, and which file they go to. **Make a draft only; do not write it
  yourself.**

## When the Stop hook asks

When 3 or more files (`BATON_HANDOFF_NUDGE_FILES`) were edited since the last handoff, the baton Stop hook keeps your
turn going once per session and asks you to write the handoff (`BATON_HANDOFF_AUTO`, on by default; not on Codex).
Then:

- Do step 2 only: update `HANDOFF.md` starting from the current file (do not rewrite it from memory). Keep it short;
  the changes made and the next actions matter most. The save-time check runs by itself when you save (this request
  only comes on Claude Code); fix what it reports, and restore each listed dropped line that is still true.
- Skip the promotion review and do not commit — the user did not ask for either.
- End the turn with one line to the user: the handoff was updated (not committed), and `BATON_HANDOFF_AUTO=off`
  turns this off.

## Templates

English:

```markdown
# Session Handoff (written: YYYY-MM-DD)

## Goal and done criteria
- Goal:
- Done when:

## Verified facts and decisions
<!-- Mark each line [V] (checked directly with a file or command) or [?] (from memory or a guess), and say how you checked it (command, file, date) -->
-

## Files and symbols
<!-- Put (must read) after the path of at most 3 entries the next session has to read before acting -->
- `path` (`path:line` if needed): symbol / why — line numbers shift soon, so put the symbol first

## Changes made
- None, or the exact file + the change in behavior

## Failed approaches (do not retry)
- Approach: why it failed

## Verification evidence
- Command/check:
- Result:

## Risks and next actions
- Risks/blockers:
- Next action: current state (evidence) → what to do

## Promotion candidates (to DECISIONS.md)
- None, or: what / signal (repeated failure in N versions · dropped · reversal the owner mentioned) / hash of the version it rests on

### Rejected (do not raise again)
- None, or: what / date rejected / reason
```

Korean (한국어):

```markdown
# Session Handoff (작성: YYYY-MM-DD)

## 목표와 완료 조건
- 목표:
- 완료 조건:

## 확인된 사실과 결정
<!-- 줄마다 [V](파일·실행으로 직접 확인함) 또는 [?](기억·추정)를 붙이고, 어떻게 확인했는지(명령·파일·날짜)를 적는다 -->
-

## 관련 파일·심볼
<!-- 다음 세션이 행동 전에 꼭 읽어야 할 항목 최대 3개는 경로 뒤에 (필독)을 붙인다 -->
- `경로`(필요하면 `경로:줄`): 심볼 / 이유 — 줄 번호는 곧 밀리므로 심볼을 먼저 적는다

## 이미 한 변경
- 없음, 또는 정확한 파일 + 동작 변화

## 실패한 접근법 (다시 시도 금지)
- 접근: 왜 실패했는지

## 검증 증거
- 명령/확인:
- 결과:

## 남은 리스크와 다음 행동
- 리스크/블로커:
- 다음 행동: 지금 상태(근거) → 할 일

## 승격 후보 (DECISIONS.md로 올릴 것)
- 없음, 또는: 무엇 / 신호(반복 실패 N판 · 탈락 · 소유자가 말한 번복) / 근거 판의 해시

### 기각됨 (다시 올리지 않는다)
- 없음, 또는: 무엇 / 기각일 / 사유
```

**Read the rejected list first, in step 1.** Otherwise the same candidates come back in every version.
In real history, one repository's count of failure items stayed the same for nine versions in a row. Once an item
crosses the threshold, it stays put. If the same eight items come up every time, nobody reads that section any more —
exactly the way the relationship-map document died.

## Promotion stops at a proposal

**What is forbidden is not "writing it for the owner" but "filling it in by guessing".**

The value of a decision record is not "what was decided" but **"why, and what was rejected"**.
The rejected alternatives and the reasons exist only in the head of the person who decided; they cannot be worked out
backwards from the handoff. Filled in by guessing, the most important line is false when someone reads it six months
later.

So the line is here. **When the owner tells you the reason and the rejected alternatives, record them with the
`/decision` skill. If either is missing, do not write the entry.** This means the skill does not add entries on its
own judgment; it does not stop you from writing down what the owner says.

So raise promotion candidates like this.

- **What** — a one-line draft of the decision
- **Why promote** — in which versions and how many times it repeated, with hashes
- **Blank fields** — leave "rejected alternatives" and "reason" blank for the owner to fill in

When the owner writes the decision, suggest adding one `- 관련:` (related) line with it (other projects as `[[name]]`
and direction / the concepts it changes / evidence paths, or `없음` (none) if there are none). That line is where the
decision connects to the concept map — the `/ontology` skill reads it and works out which concepts need a re-check.

## When to use it

- When a piece of work is done / when the topic changes / when the context feels about 70% full.
- The promotion review can be run on its own. For "review what to promote", do step 1 only and report.

## Where HANDOFF ends and DECISIONS begins

| | HANDOFF.md | DECISIONS.md |
|---|---|---|
| Lifetime | Useless once this piece of work is done | Still answers "why?" six months later |
| Copies | Latest one only, overwritten | Accumulates, never deleted |
| About | How far we got | Why we chose this path |
| Written by | The agent | **The owner** |

When in doubt, there is one test. **Will this sentence still be true next week?**
If yes, DECISIONS; if not, HANDOFF.

## Do not

- Write `DECISIONS.md` for the owner
- Fill in rejected alternatives by guessing
- Keep growing a failure item that survived 3 or more versions instead of raising it as a promotion candidate
- Raise a rejected candidate again in the next version (read the rejected list first)
- Read past versions in full (`promote.sh` extracts only the sections)
- Report a 0 from the script as "none" (look at the format-mismatch line first)
- Leave `HANDOFF.md` uncommitted (the next version cannot see this one)
- Paste the full conversation or raw tool output into the handoff
- Rewrite an existing handoff from memory (start from the file; the checker lists what was dropped)

## Limits (honestly)

- The promotion review is implemented as `promote.sh` and was checked by running it on two repositories.
  **On 2026-09-15 the counting unit changed from commits to days** — counting by commit mistook same-day copies for
  repetition, and 7 of 8 items in the docs repository were false. Now it is 1 in the docs repository and 9 in the game
  repository. **The judgment of "so what should be promoted" has never been run end to end, and it has never been
  verified by calling it as a skill.**
- **Automatic reversal detection failed.** We confirmed that string counting cannot catch it and took it out of the
  signals. Raise one only when the owner points it out.
- **The dropped signal works only when the handoff section headings stay the same across versions.** In the game
  repository, 5 of the last 8 versions had a different section layout and could not be counted (the script prints
  that). In repositories whose layout changes often, the denominator of this signal is small.
- **The threshold of 3 versions was set from the distribution of one repository.** Whether other repositories split
  at the same point is not known yet. If there are more than 15 candidates, consider raising the threshold.
- In a repository where git does not track the handoff, the promotion review does not work at all. As checked on
  2026-09-14, `HANDOFF.md` was untracked in one of the three target projects (the app repository) and in one other
  repository. `git add` comes first.
- Deciding "is this the same judgment" is a judgment of meaning, not string matching, so it can miss things.
  What it misses shows up again in the next version, so this is not fatal, but if you are not sure, raise it as a
  candidate and let the owner reject it. Leaving one out costs more.
