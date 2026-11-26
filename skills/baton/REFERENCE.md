# Handoff skill — reference

`SKILL.md` says what to do. This file keeps the reasons and the measurements behind those rules, moved out of the
skill in 1.0.3 so that the skill itself stays small. Read it when the why matters: the owner asks, or a rule seems not
to fit the situation. Nothing here changes what the skill tells you to do.

## Purpose

Instead of dragging a long conversation on, leave the work state in a short file and pick it up in a new session.
Measured: cost -44.7% compared with a cold start, with accuracy equal or better (internal controlled experiment).
The core value is the "Failed approaches" item — it keeps the next session from repeating the same dead ends.
**The -44.7% cost figure was measured on the 7-item version, before the promotion candidates section existed.** The
8th item was added later.

**Second purpose: promotion review.**
The handoff is overwritten every time, so each version is short-lived. But **what repeats across versions** is not.
If the same judgment was made three times over, it is not session state but a standing rule, and it belongs in
`DECISIONS.md`, not `HANDOFF.md`. It means you are paying to make that judgment again every time.

Past versions are not archived separately. **The git history is the archive.**

## Why a write takes so few calls (1.0.3)

In 10 real handoff writes with 1.0.1 (Opus, about 230–250K tokens of context), a write always went: the skill, one
Bash call (`promote.sh --brief`, `git status`, `git log`), `Write` HANDOFF.md, one Bash call for the commit, and the
final two lines. That is 5–6 assistant calls. Each call reads the whole context again from the prompt cache, about
$0.05 at that size. The skill text was 24.7 KB (about 8K tokens) and was written to the cache on every write, about
$0.06. A write with a warm cache cost about $0.42–0.57.

1.0.3 changes three things. The expected effect is fewer calls and a smaller cache write; the real cost has not been
measured yet.

- **Step 1 is filled in when the skill loads.** Claude Code's dynamic context injection runs the line made of an
  exclamation mark and a command in backticks, and puts its output in place of the line, so the promotion review and
  `git status`/`git log` cost no call. `${CLAUDE_PLUGIN_ROOT}` is substituted, and the command runs in the session's
  folder; `promote.sh` moves up to the repo root itself. If the permission rules don't allow the command, Claude Code
  asks the model to run it first, and Codex shows the line as it is: in both cases the model runs it as one Bash call.
- **`promote.sh --brief` always exits 0.** If an injected command exits non-zero, Claude Code fails to load the whole
  skill ("Shell command failed for pattern …"), and no handoff can be written. So every path that cannot run (not a
  repo, no or untracked HANDOFF.md, no committed version, git errors, an unreadable file) says why in its output and
  exits 0; stderr goes to stdout; after 10 seconds (`BATON_PROMOTE_TIMEOUT`) it stops and says it was not counted.
  The full form still exits 2 when it cannot run.
- **Save and commit in one response.** Probed on Claude Code 2.1.332: in one assistant message, `Write` ran and then
  the Bash call, in that order; a PostToolUse block on the `Write` still let the Bash call run, and the block reason
  arrived afterwards. So a problem the save check finds is fixed with a second commit, and warnings alone need none.
  `Write` and `Edit` refuse a file that was not opened with the Read tool in the conversation; the copy that the
  injection hook puts into context does not count, so a handoff not yet read is read first.
- **The skill moved its explanations here**, from 24.7 KB to under 12 KB.

Why not to pipe `promote.sh --brief` through `head` or `tail`: cut output is what made earlier runs call it a second
time (2026-11-24 experiment 2: 4 of 5 runs in one repository). The short form was made for that reason: at most 8 lines,
the most important first, one line when there is nothing to promote.

## Promotion review

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
empty as "format mismatch", takes them out of the denominator, and prints that. The script reads both the English and
the Korean template headings.

If HANDOFF.md is not tracked, the script says so and stops: while it is untracked, this review can never work.

**Why read the rejected list first.** Otherwise the same candidates come back in every version. In real history, one
repository's count of failure items stayed the same for nine versions in a row. Once an item crosses the threshold,
it stays put. If the same eight items come up every time, nobody reads that section any more — exactly the way the
relationship-map document died.

## Writing the handoff

**Why 200 lines and 8,700 characters.** Lines: owner decision 2026-09-22. Characters: the checker limit, the amount
that still goes in whole after the injection hook adds its header, the freshness line and the concept index. Hook
output over the 10,000-character cap in the Claude Code docs is moved to a file, so the hook keeps everything, header
and freshness line included, within 9,600 characters. When a handoff or status question comes in, the plugin hook puts
this file into context up to 200 lines and 9,600 characters of hook output — anything past that is left out. That is
why the next actions go near the top.

**Must-read marks.** The injection hook repeats the `(must read)` entries in one line right after the freshness line,
so they survive truncation. The checker warns when more than 3 are marked, and counts that line twice toward the
8,700 characters (it goes in twice).

**[V] and [?].** A line without a mark costs an extra edit after the check.

**A handoff is a hypothesis from the time it was written, not a fact.** The next session may read this file days
later, in another folder, in a repository with commits piled up in between. When it injects the file, the hook adds
the written date, how many days ago that was, and the number of commits since; the reader checks only the one or two
claims the next action depends on. The writer has three jobs.

- **The written date in the first line.** The hook counts the age from this date. Without it, the hook uses the last
  commit date of HANDOFF.md.
- **Each next action as a pair: "current state (evidence) → what to do".** A bare command gets run as it is even
  after the state has changed. With the pair, the reader checks the state first and decides the action again if the
  state is different. Example: "`split-notice.py` is registered but has never fired in a real window (the installed
  copy is the 10-04 version) → reinstall, then check in a new window".
- **Next actions the next session can do without asking.** In a 2026-11-24 experiment, every failed handoff run was a
  new session that stopped to ask the questions its handoff told it to ask. Hence the **Owner decisions** sub-list,
  with a recommended default and whether the action is reversible.

Each verified fact says how it was checked (command, file, date), so the reader can check it again the same way.

**Why not through Bash.** A Bash write is checked only afterwards, by the hook that runs after a Bash call that names
a handoff file.

**What the checker does.** It checks the 8 required sections, 200 lines, 8,700 characters (including the must-read
line, which goes in twice), code blocks over 20 lines, full diffs, secrets and absolute home paths. Over 8,700
characters, it says how many to cut and names the two largest sections; while the file is over a limit, a save that
makes it shorter than the last check only warns, and a size problem blocks at most once per turn. If a list item under
"Verified facts and decisions" ("확인된 사실과 결정" in the Korean template) has no [V] or [?] mark, it warns without
blocking. It also warns, without blocking, about lines dropped since the last committed version (lines in "Failed
approaches", "Promotion candidates" and "Rejected"; "Verified facts and decisions" and "Risks and next actions" are
not checked) and about more than 3 must-read marks. On Claude Code, saving with `Write`/`Edit` makes a hook run the
checker and add one line to the context: "check passed (N lines, M chars)", or the problems and warnings. Codex's
`apply_patch` gives the hook no path, so no check line appears there.

**Why commit.** The `-- HANDOFF.md` keeps files the user had already staged out of this commit. Without a commit, the
next version cannot see this one, and the promotion review does not work. The commit prints one line,
`[branch sha] handoff: …`, so `git log` or `git show` afterwards adds nothing.

## Stop hook

When 3 or more files (`BATON_HANDOFF_NUDGE_FILES`) were edited since the last handoff, the baton Stop hook keeps your
turn going once per session and asks you to write the handoff (`BATON_HANDOFF_AUTO`, on by default; not on Codex).
This request only comes on Claude Code, where the save-time check runs by itself. There is no step 1 call on this
path: the user did not ask for a promotion review or a commit.

The same hook also asks once when the context of a model call passes 250K tokens and again at 450K
(`BATON_SPLIT_TOKENS`, `BATON_SPLIT_NOTICE`), but only at the end of a turn that did work after the handoff was last
written (a turn that only asked or read is not stopped; the threshold waits for the next turn that does work): a file
edited with `Write`/`Edit`, an `Agent`/`Task` call whose subagent edited or wrote files (read-only kinds such as
Explore don't count when its record can't be found), or a Bash command that clearly writes a file (`sed -i`, a
`>`/`>>` redirect to a path outside temp folders, `tee`, `mv`, `cp`, `git mv`). A Bash command that writes
`HANDOFF.md` counts as writing the handoff, and so does a Bash call that names a handoff file and during which the
repo-root `HANDOFF.md` changed (so a write inside a python heredoc counts too). A turn starts at a human prompt, a
message from another session or a task notification (Stop hook feedback stays in the same turn); a background
subagent's edits count once, in the turn opened by its completion notification (matched by `<tool-use-id>`). It also
doesn't ask when the new conversation would start almost as large (the context is not yet 24K tokens past the first
call; also under the ratio rule). Then the line tells the user the handoff was saved; from 250K up it adds that, by a
recount of the author's sessions, a new conversation is usually cheaper from this size on (below 250K it makes no cost
claim). The 250K and 450K defaults come from sessions with a 1M-token context window; with a 200K window the
conversation is compacted before 250K and the rule doesn't fire; `BATON_SPLIT_TOKENS` can be lowered, but whether that
is cheaper at that size wasn't measured (in the 1M-window sessions, 150K was usually a loss). A user who set only
`BATON_SPLIT_RATIOS` keeps the older rule (multiples of the first call's context) and its wording. Never suggest
`/compact`. One Stop asks at most once, for both reasons together.

## Promotion stops at a proposal

The value of a decision record is not "what was decided" but **"why, and what was rejected"**. The rejected
alternatives and the reasons exist only in the head of the person who decided; they cannot be worked out backwards
from the handoff. Filled in by guessing, the most important line is false when someone reads it six months later.
That is why the skill does not add entries on its own judgment, but does not stop you from writing down what the
owner says.

The `- 관련:` (related) line is where the decision connects to the concept map — the `/ontology` skill reads it and
works out which concepts need a re-check.

## Where HANDOFF ends and DECISIONS begins

| | HANDOFF.md | DECISIONS.md |
|---|---|---|
| Lifetime | Useless once this piece of work is done | Still answers "why?" six months later |
| Copies | Latest one only, overwritten | Accumulates, never deleted |
| About | How far we got | Why we chose this path |
| Written by | The agent | **The owner** |

When in doubt, there is one test. **Will this sentence still be true next week?**
If yes, DECISIONS; if not, HANDOFF.

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
- The step 1 block shows the state when the skill loaded. If the skill was loaded long before the write and files
  changed since, that state is old; the "Facts already confirmed" rule covers it (check again, or write `[?]`).
