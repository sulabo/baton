---
name: handoff
description: Write a session handoff (HANDOFF.md). When a piece of work is done, the topic changes, or the conversation gets long, leave the current state in a file so the next session can pick it up. Before writing, scan past handoffs to decide whether anything should be promoted to DECISIONS.md. Triggers on requests such as "write a handoff", "leave a handoff for the next session", "update HANDOFF.md", "review what to promote to DECISIONS.md"; the baton Stop hook can also ask for it once per session. 세션 인계서(HANDOFF.md) 작성. 작업 하나가 끝났거나 주제를 바꾸거나 대화가 길어졌을 때, 다음 세션이 이어받을 수 있게 현재 작업 상태를 파일로 남긴다. 쓰기 전에 과거 인계서를 훑어 DECISIONS.md로 승격할 것이 있는지 함께 판정한다. "핸드오프 작성해줘", "인계서 남겨줘", "승격 검토"에도 발동.
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/lib/promote.sh *) Bash(python3 ${CLAUDE_PLUGIN_ROOT}/lib/handoff_check.py *)
---

# Handoff — writing a session handoff and reviewing promotions

Reply in the user's language. Write HANDOFF.md in the language of the existing file, or else the user's. Both
templates are at the end. The why behind each rule is in `REFERENCE.md` in this skill's folder: read it only when you
need it.

## Procedure

### 1. Promotion review and repo state (filled in when this skill loads)

!`${CLAUDE_PLUGIN_ROOT}/lib/promote.sh --brief --status .`

Above: `git status --short --branch` and `git log --oneline -3` of the repo root, then the short promotion review (at
most 8 lines). **Do not run them again or put git commands together by hand.** If the line above still shows a command
instead of its output (Codex, or a permission rule), run it as one Bash call, adding anything else you need to check.
Run the full form, `${CLAUDE_PLUGIN_ROOT}/lib/promote.sh [repo path] [versions (default 8)]`, only for a promotion
review on its own or when the summary says there are more candidates than it shows. If HANDOFF.md is not tracked,
report that with the advice to run `git add HANDOFF.md`.

Signals: **repeated failure**, a "Failed approaches" item on 3 or more different days: raise it as a promotion
candidate (on 2 days do not promote it but **shorten it to one line** in the handoff; on 1 day leave it). **Dropped**,
a standing constraint from 2 or more earlier versions gone from the latest: marked ones come first, and a person
decides which are finished work and which live constraints. **Reversal** is not detected: raise one only when the
owner points it out.

**0 can mean "could not count", not "none"**: copy the script's format-mismatch line into your report. **Read the
rejected list first.**

### 2. Write and commit the handoff

Write `HANDOFF.md` at the repo root (with no repository, in the current folder), keeping only the latest copy.
**Update, do not rewrite:** start from the existing file, not from memory — carry forward every line that is still
true, move finished next actions to "Changes made", and delete only what you know is obsolete. Lines under "Failed
approaches", "Promotion candidates" and "Rejected" are meant to survive across sessions.

Fill in the 8 items of the template. Keep it short: no full conversation, repeated explanations or raw tool output.
**Stay within 200 lines and 8,700 characters**, with no code block over 20 lines, full diff, secret or absolute home
path. Put the next actions near the top. Put `(must read)` (Korean: `(필독)`) after the path of at most 3 "Files and
symbols" entries the next session must read before acting. Write what is not verified as "unverified"; for partial
completion say exactly which part is left. Base what you write on files and command results, not on summaries or
memory.

- **Every line under "Verified facts and decisions" starts with `[V]`** (seen in a file or a command result) **or
  `[?]`** (memory, a summary or a guess), with how it was checked (command, file, date).
- **Facts already confirmed.** A fact you already saw in a command output or a file in this conversation is `[V]`
  without running the command again — **unless you edited a file that fact depends on after you saw it**; then check
  it again or write `[?]`. Anything known only from a compaction summary is `[?]`, as is anything you remember but did
  not see in this conversation. Check anything new in one Bash call before you write.
- **First line: the written date** (`written: YYYY-MM-DD`; `작성: YYYY-MM-DD` in Korean).
- **Each next action is a pair, "current state (evidence) → what to do"**, that the next session can do without
  asking. Do not write "confirm with the user". What truly needs the owner goes under **Owner decisions** (Korean:
  **소유자 확인**) in "Risks and next actions": one item each, with a **recommended default** and whether it is reversible.
  The next session takes the default when reversible and asks only when irreversible, destructive or outward-facing
  (pushing, publishing, deleting, sending, spending money). Nothing for the owner: write "None".

**Save and commit in one response.** If `HANDOFF.md` exists and you have not read it with the Read tool in this
conversation (a hook-injected copy does not count), Read it first: Write and Edit refuse a file not read. Then call
Write (or Edit) and, in the same response right after it, the commit:

```bash
git add HANDOFF.md && git commit -m "handoff: <topic>" -- HANDOFF.md
```

Never write `HANDOFF.md` through Bash (a python heredoc, `cat >`, `sed -i`): it is checked only afterwards. Do not run
`git log` or `git show` after the commit: its one line, `[branch sha] handoff: …`, is the evidence.

**Then look for the `[baton] HANDOFF.md` check line** from the save hook. "check passed (N lines, M chars)" (Korean:
"검사 통과"): **do not run the checker yourself**. Problems: fix only those and commit again; warnings alone need no
second commit unless you fix something. No such line (Codex: `apply_patch` gives the hook no path), or a line saying
part of the check couldn't run (Korean: "검사 일부를 돌리지 못했어요"): run
`python3 ${CLAUDE_PLUGIN_ROOT}/lib/handoff_check.py HANDOFF.md`, fix what it reports, and commit again if you changed
the file.

### 3. Tell the user

End with **exactly these two lines** and nothing else (no list of what you wrote):

- "In a new session, start with 'read HANDOFF.md and continue'." (Korean: "새 세션에서 'HANDOFF.md 읽고 이어서 해줘'라고 시작하세요.")
- The promotion candidates in one line: what, why, and which file they go to (**a draft only; do not write it
  yourself**), or "No promotion candidates." (Korean: "승격 후보 없음.")

## When the Stop hook asks

On Claude Code, the baton Stop hook may keep your turn going and ask you to write the handoff (after 3 or more file
edits, or when the context has grown large; the rules are in `REFERENCE.md`). Then:

- Do step 2 without the commit: update `HANDOFF.md` starting from the current file (do not rewrite it from memory).
  Keep it short; the changes made and the next actions matter most. If the save-time check says the check passed, do
  not run the checker; if it says part of the check couldn't run, run the checker; otherwise fix what it reports, and
  restore each listed dropped line that is still true.
- Check anything you need in one Bash call before you write (there is no step 1 call on this path: if step 1 shows a
  command instead of its output, do not run it).
- Skip the promotion review and do not commit. Never suggest `/compact`.
- End the turn with the one line to the user that the request gives you, word for word.

## Templates

English:

```markdown
# Session Handoff (written: YYYY-MM-DD)

## Goal and done criteria
- Goal:
- Done when:

## Verified facts and decisions
<!-- Start every line with [V] (checked directly with a file or command) or [?] (from memory or a guess), and say how you checked it (command, file, date) -->
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
- Next action: current state (evidence) → what to do (the next session does it without asking)
- Owner decisions:
  - None, or: what / recommended default / reversible: yes or no

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
<!-- 모든 줄을 [V](파일·실행으로 직접 확인함) 또는 [?](기억·추정)로 시작하고, 어떻게 확인했는지(명령·파일·날짜)를 적는다 -->
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
- 다음 행동: 지금 상태(근거) → 할 일 (다음 세션이 묻지 않고 바로 한다)
- 소유자 확인:
  - 없음, 또는: 무엇 / 권장 기본값 / 되돌릴 수 있나: 예·아니오

## 승격 후보 (DECISIONS.md로 올릴 것)
- 없음, 또는: 무엇 / 신호(반복 실패 N판 · 탈락 · 소유자가 말한 번복) / 근거 판의 해시

### 기각됨 (다시 올리지 않는다)
- 없음, 또는: 무엇 / 기각일 / 사유
```

## Promotion stops at a proposal

What is forbidden is not "writing it for the owner" but **"filling it in by guessing"**. **When the owner tells you
the reason and the rejected alternatives, record them with the `/decision` skill; if either is missing, do not write
the entry.** Raise each candidate with **what** (a one-line draft), **why promote** (which versions, how many times,
hashes) and **blank fields** ("rejected alternatives", "reason") for the owner. When the owner writes it, suggest one
`- 관련:` (related) line (other projects as `[[name]]` and direction / concepts it changes / evidence paths, or `없음`)
for the `/ontology` skill. Not sure it is the same judgment? Raise it; the owner can reject it. **Still true next
week?** Then `DECISIONS.md` (the owner's); if not, `HANDOFF.md`.

## When to use it

When a piece of work is done, when the topic changes, or when the context feels about 70% full. For "review what to
promote" on its own, do step 1 only and report.

## Do not

- Write "ask the user" or "confirm with the owner" as a next action
- Write `DECISIONS.md` for the owner, or fill in rejected alternatives by guessing
- Keep growing a failure item that survived 3 or more days instead of raising it
- Raise a rejected candidate again
- Read past versions in full (`promote.sh` extracts the sections)
- Pipe `promote.sh --brief` through `head`/`tail`, or run it again when step 1 shows its output
- Run the checker after a `[baton] HANDOFF.md` check line appeared, or `git log`/`git show` after committing
- Report a 0 from the script as "none"
- Leave `HANDOFF.md` uncommitted
- Paste the full conversation or raw tool output into the handoff
- Rewrite an existing handoff from memory
