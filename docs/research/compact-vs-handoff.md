# Compact vs handoff at a task boundary

> Published 2026-11-24 as one squashed commit. The step-by-step history, whose commit times show each
> pre-registration came before the runs it covers, is kept on the author's local branch `exp-compact`
> (31f4243 … 42b17d3); it names the private game repo, so it isn't pushed.
>
> **Corrected 2026-11-25.** In the game repo the `/compact` arm also received a handoff, so that repo is left out
> and both verdicts become "inconclusive" under the pre-registered rule. See
> [Correction (2026-11-25)](#correction-2026-11-25). The original text below is unchanged.
>
> **Follow-ups 2026-11-25:** round 3 (the next day, a different task) and W (the handoff write in 1.0.1). See
> [Round 3 and W](#round-3-and-w-2026-11-25).

**Question.** A long Claude Code session reaches a task boundary and work continues. Is it better to
write a handoff (baton's `HANDOFF.md`) and start a **new** session, or to run `/compact` and keep going in the
**same** session? "Better" means the next task is done at least as correctly, with fewer input tokens, lower
cost, or fewer turns. The design can return "handoff better", "no difference", or "compact better".

Runner: `observer/research/compact_ab.py` (tests: `test_compact_ab.py`). Raw stream-json, transcripts and
per-run records live outside any repo (`~/.cache/baton/experiments/compact-vs-handoff/`). Only aggregate
numbers appear here.

## Method (pre-registered 2026-11-23, before any experiment run)

### Feasibility probes (Claude Code 2.1.330, opus 5.5, owner's setup with OMC + baton 1.0.0-beta.3)

- `/compact` is **not documented** for `-p` mode, but it runs: `claude -p "/compact" --resume S --fork-session`
  emits a `compact_boundary` event (`trigger: manual`, `pre_tokens`, `post_tokens`), fires the PreCompact and
  SessionStart:compact hooks, and returns a new session id. S's transcript is unchanged (size and mtime checked).
  A follow-up turn on the compacted session recalled both planted facts. The runner treats a missing
  `compact_boundary` as a failed transition.
- `total_cost_usd` and `modelUsage` of a resumed or forked session **include the parent's usage**
  (checked on 6 parent→child pairs). Every phase is charged child minus parent.
- The `/compact` result reports `usage` = 0 and `num_turns` = 0. Its tokens exist only in `modelUsage`.
- Forks reuse the parent's prompt cache (1-hour TTL). The compaction request sends the conversation uncached.
- Baton's UserPromptSubmit hook injects `HANDOFF.md` in `-p` mode. The prompt "이어서 해줘" ("continue")
  matches its trigger.
- The owner's own opus 5.5 sessions (aggregate of local transcripts) auto-compacted 60 times at 204k–969k
  tokens (median 301k). There were no manual compactions.
- Probes cost $2.90, counted inside the $80 cap.

### Long-session state (scripted, not a real past session)

Each repo gets **one** long session S, built from a fixed prompt list (`compact_ab/<repo>.json`) in a snapshot
with no remote. The script works through a 4-step feature: plan, steps 1–3 with commits, one failed approach
and its revert, long test output, and exploratory reads. It stops after agreeing on step 4, the next task.
Reading prompts are added until the main-thread context reaches **≥ 200k tokens**, the low end of the owner's
real opus compaction points. The build is invalid if it contains any `compact_boundary`. Real past sessions were
not used: they lack ground truth, their repo state can't be rebuilt, their transcripts are private, and they
hold absolute paths into live repos.

Six facts are planted in the conversation, in the same pattern in every repo:

| fact | planted | applies to step 4 |
|---|---|---|
| F1 early detail | first prompt | an input format the next task must accept |
| F2 name decision | plan prompt | the option's name. The forbidden alternative is the obvious default |
| F3 do-not-touch | mid-build | paths that must not be modified |
| F4 rejected approach | a third-party package is tried, missing, ruled out | no third-party dependency |
| F5 process rule | step 3 | a help/docstring block must list every option |
| F6 late criterion | final prompt only | an exact message for the empty result |

After the build, each fact's marker is grepped in the repo and tagged conversation-only or also-in-repo.
Both groups are reported.

### Arms (the same snapshot path, one session at a time, transitions first)

- **C (compact)**: `claude -p "/compact" --resume S --fork-session`, then `claude -p "이어서 해줘" --resume C_i`.
- **H (handoff)**: `claude -p "핸드오프 작성해줘" --resume S --fork-session --max-turns 15` (baton's handoff
  skill). The resulting diff (HANDOFF.md, possibly DECISIONS.md) is saved, then reapplied uncommitted before a
  **new** session `claude -p "이어서 해줘"`.
- Every call runs with `--output-format stream-json --verbose --include-hook-events`, `BATON_OBSERVE=off`,
  stdin closed, and the owner's unchanged global setup. Each call gets `--max-budget-usd`
  (build/transition 2, next task 4). Next tasks get `--max-turns 30`.
- Before every phase: `git reset --hard` to the switch point, clean untracked files, remove harness state
  (`.omc/`), kill leftover processes, and move any auto-memory folder for the snapshot's project out of the way.
  Auto-memory would otherwise be a third carrier of facts. No documented switch to turn auto-memory off was
  found, so the folder (`~/.claude/projects/<encoded snapshot path>/memory/`) is moved into the data folder
  before and after every phase, and the moved file counts are recorded. One snapshot path per repo is shared
  by all of its phases, instead of a fresh path per run. S's transcript holds absolute paths into the build
  directory, so a fork running elsewhere could read or edit that shared copy.
- **Order**: all 10 transitions per repo run as one block right after the build, to keep S's cache warm, then
  the 10 next tasks. Both blocks are counterbalanced: C H H C C H H C C H, with the mirror order in the second repo.
- Target n = 5 per arm per repo. Repos: baton (Python plugin, public) and a private TypeScript game repo. The
  game repo is taken from the read-only round2 snapshot of its 2026-09-27 working tree, because the live copy
  is no longer on disk. A third repo runs only if the projected cost still fits under the cap after the first
  two. After the first next-task pair, the run counts are recalculated from measured costs.

### Grading (scripted, blind to arm by construction)

The hidden acceptance checks live outside the snapshot and run against the final working tree. Diff rules
use case_grade's diff parser on the next-task-only diff.

- `core`: the step-4 filter gives the planned counts under the planned option name (dateless entries excluded,
  inclusive bound).
- One check each for F1–F6. F3 and F4 are diff/command rules; the rest are executable checks.
- **correct** (binary) = core ∧ F2 ∧ F3 ∧ F4. **score** = passed checks / 7.
- Diagnostics, not inputs: whether the filter works under any common flag name, whether the session's own
  tests pass, and which files and commits changed.

### Metrics per run

Transition and next task are recorded separately, then summed. Cost is Δ`total_cost_usd` (a client-side
estimate). Tokens are Δ`modelUsage`: uncached input, cache creation and cache read **kept separate**, plus
output. Also recorded: first-turn context of the next task, `num_turns`, wall time, and hook injection seen.

### Budget

Hard stop at **$77 of reported cost, probes included** (the owner approved $80). The runner refuses to start
a phase when spent + that phase's `--max-budget-usd` + $0.50 > $77. Unknown spend (no result line) is charged at the cap.
A ledger lives in the data folder. Rate-limit or overload errors back off (2 min, then 15 min); a third failure
in a row stops the run. Two consecutive invalid runs also stop it.

### Decision rule (pre-registered)

Valid runs only. Invalid means a harness failure: no result line, a rate limit, a transition without a
boundary or without HANDOFF.md. `error_max_turns` is a valid, graded run. Let N be the valid runs per arm,
k_C and k_H the correct counts pooled over repos, and r the median over repos of (median total cost H /
median total cost C). Define a = max(1, round(N/15)) and b = ceil(0.2·N).

- **Handoff better**: (k_H ≥ k_C − a and r ≤ 0.85, with H cheaper in every repo but at most one)
  or (k_H − k_C ≥ b and r ≤ 1.10).
- **Compact better**: the mirror image (k_C ≥ k_H − a and 1/r ≤ 0.85 …) or (k_C − k_H ≥ b and 1/r ≤ 1.10).
- **Trade-off**: correctness differs by ≥ b one way while cost differs by > 10% the other way.
- **No difference detected**: anything else.
- A verdict needs ≥ 2 repos with ≥ 3 valid pairs each. Otherwise the result is **inconclusive**.
- Median and range of score, input tokens (per kind), cost and turns are reported per arm and per repo
  whatever the verdict.

### Known threats (stated before results)

- Scripted sessions are cleaner than real ones, and planted facts are more salient than real ones.
- Manual `/compact` at a clean task boundary differs from the owner's reality (all automatic, often mid-task).
- At 200k the switch point is at the low end of real opus compaction points, so effects may grow with length.
- One model and the owner's plugin setup: OMC hooks fire around compaction, and baton's skill writes the handoff.
- n is small. "No difference" means "not detected at this n".
- Costs are Claude Code's estimates, not billing.

### Deviations (recorded 2026-11-24, after the baton transitions and before any next-task result)

1. **Cost used by the verdict.** A harness crash (a plugin hook still writing `.omc/state` broke cleanup)
   paused the run for 15 h after transition C1, so S's 1-hour prompt cache expired. Two more facts then
   showed up. First, the compaction request never writes cache: C1 read 237,700 of 239,748 tokens from the
   build's cache for $0.29, while later compactions sent about 227k tokens uncached for about $1.1. Second,
   a fork's session-start prefix was not always stable: H4 ran 2 minutes after a warm H3 and still missed
   the cache. Transition cost therefore partly measured cache state, not the arm. At a real task boundary
   the cache is warm, which is what the pre-registered "run right after the build" intended. So the verdict
   uses **warm-normalized transition cost** + raw next-task cost:
   - C reprices its uncached input as cache reads.
   - H reprices its first turn's cache creation as cache reads.

   The repricing uses prices fitted from the four probes (input $3.96, 1-hour cache write $8.00, cache read
   $0.201, output $19.95 per MTok). Applied to the cold compactions it gives $0.24–0.27, against $0.28 for
   the one warm compaction. The verdict on raw reported cost is reported too, as a sensitivity check.
   Cache state does not change model output, so correctness is unaffected.
2. **Transition cap 2 → 3 USD.** Two cold H forks (H1, H4) hit `--max-budget-usd 2`
   (`error_max_budget_usd`) before writing HANDOFF.md. They were rerun. The failed attempts stay in the data
   and in the ledger.

3. **Exploratory measure (not in the verdict), added after the pilot pair.** Pilot H1's handoff listed
   undecided points to "confirm with the user before implementing". The new session asked four questions and
   stopped without changing anything, so it is graded incorrect, as pre-registered. Any run (either arm) that
   leaves the target file untouched now gets one neutral reply in the same session, "알아서 판단해서 진행해줘"
   ("use your judgment and proceed"), and is graded again on the cumulative diff. This gives "correct after at
   most one reply" and its extra cost.

## Correction (2026-11-25)

**In the game repo, the `/compact` arm also received a handoff. That repo is therefore left out. By the
pre-registered rule, both rounds' verdicts change from "compact better" to inconclusive.** The results sections
below are kept as published on 2026-11-24.

**What happened.**
- The snapshot step removed the game repo's own `HANDOFF.md`, as planned. During the long-session build,
  baton 1.0.0-beta.4's automatic handoff update fired once. At build step 5 its Stop hook blocked the turn,
  because the session had changed 4 files since a handoff was last written, and asked the agent to write
  `HANDOFF.md`. The agent wrote it, and the next four build prompts, the final one included, edited it again.
- After the build, the runner commits whatever the build left uncommitted. That commit put this `HANDOFF.md`
  (51 lines, 3,520 characters) into the switch point, the commit every phase resets to (`B1` in the runner).
  The file contains the markers of F1, F2, F4 and F6 (F3 and F5 have no marker).
- Every game-repo C next task started from that commit with "이어서 해줘", which matches baton's injection
  trigger. In each of the 5 runs, baton injected that file in full (4,487 characters with its header lines).
  So the game-repo C arm measured "/compact plus the build's handoff", not /compact alone.
- A second path, found in review the same day, carried the same file. Right after each game-repo compaction
  (C1–C5), Claude Code re-attached recently read files to the compacted session as `file` attachments, and one
  of them is this `HANDOFF.md`, byte-identical to the switch point's copy. The five baton-repo compacted
  sessions hold only path references (`compact_file_reference`) and no file content.
- The H arm was affected differently. In the game repo, every H transition (5 per round) updated the build's
  `HANDOFF.md` instead of creating one; in the baton repo, all 10 created it. The game-repo next session still
  got its own arm's handoff, as designed, but that handoff started from one written inside the build. So
  game-repo H is not the same condition as baton-repo H either.
- The baton-repo build ran under beta.3, which only suggests a handoff to the user. Its switch point has no
  `HANDOFF.md`. Baton's handoff-injection header ("[baton] 아래는 …") appears in 1 UserPromptSubmit
  `hook_response` event in each of the 5 game-repo C next tasks, and in none of the 5 baton-repo C next tasks.
  (A plain `grep -o … | wc -l` gives 2 per game-repo run, because the same text is in both the `output` and
  the `stdout` field of that one event.) In the baton repo both arms got the same concept-map index.
- Round 2 reused round 1's C rows (`compact_ab.py seed`), so its game-repo ratio (1.109) compares round-2 H
  with this same C arm.

**How it was found, and why the runner missed it.** It was found on 2026-11-25 by counting that header per
prompt-hook event in each next-task stream. The runner's `inject` flag is true when any `[baton]` text comes
back from the prompt hook. The baton repo's concept-map index also starts with `[baton]`, so the flag was true
in every next task of both rounds and could not tell a handoff injection from the index. Threat 2 below ("the
automatic-handoff Stop block never fired in any run") holds for the graded runs, but the block did fire once in
the game-repo build.

**What it affects.**
- Both published verdicts. Round 1's correctness gap came from the baton repo alone (the game repo was 5/5 in
  both arms). Round 2's "compact better on cost" used the game-repo ratio 1.109 as one of its two repo ratios.
- The game-repo C row in both tables, and every comparison against it.
- The "1.1–1.7×" figure on the README, the guides and the homepage. It was the two round-2 repo ratios
  (1.109 and 1.735). The 1.0.0 release notes keep their text, with a correction note above it.
- The clause "writing it alone cost about 2–3× a compaction" was removed from the guides and the homepage.
  It pooled the round-2 warm-normalized transition cost over both repos (about 2.0× game, 2.8× baton). In the
  baton repo alone it is about 2.8× warm-normalized but about 0.75× on the reported cost, because four of the
  five compactions ran after the prompt cache had expired.

**What it does not affect.**
- The baton-repo rows in both rounds, the grading, the cost accounting and the budget.
- Round 1's failure analysis (three baton H runs stopped to ask), and round 2's finding that this behaviour did
  not recur (baton H 2/5 → 5/5).

**Recomputed** ($0, from the saved records with `compact_ab.py report`; `--repo baton` for the baton-only rows).

| | round 1 | round 2 |
|---|---|---|
| as published, both repos | compact better: k_C 10/10, k_H 7/10, r = 1.058 (per repo 0.766 and 1.35); raw-cost sensitivity r = 1.065 (per repo 0.787 and 1.344) | compact better: k_C 10/10, k_H 10/10, r = 1.422 (per repo 1.735 and 1.109); raw-cost sensitivity r = 1.478 (per repo 1.165 and 1.79) |
| baton repo only, by the rule | inconclusive | inconclusive |
| baton repo only, descriptive | C 5/5, H 2/5 correct. H/C median cost 0.766 warm-normalized ($1.18 vs $1.54), 0.787 raw ($1.88 vs $2.39) | C 5/5 (round 1), H 5/5 correct. H/C median cost 1.735 warm-normalized ($2.67 vs $1.54), 1.165 raw ($2.78 vs $2.39) |

In round 1, baton H looks cheaper only because its three failed runs stopped early (see "What the numbers
say"). In round 2, the raw ratio is lower than the warm-normalized one because four of the five baton
compactions ran after S's prompt cache had expired (Deviation 1), which raises C's raw cost.

**What the rule says.** With the game repo left out, only the baton repo has ≥ 3 valid pairs, and a verdict
needs ≥ 2 such repos. By the pre-registered rule, both rounds are **inconclusive**. No other rule is applied.
The baton-repo numbers are descriptive only: n = 5 in one repo shows what happened in these runs, not a general
cost ratio.

## Results (2026-11-24)

**Verdict, computed by the pre-registered rule: compact better.** k_C = 10/10 correct, k_H = 7/10. The
correctness gap of 3 runs meets b = 2, and the cost ratio stays within the 10% limit (r = median over repos of
H/C median cost = 1.058; per repo 0.766 and 1.35). The raw-cost sensitivity check gives the same verdict
(r = 1.065). The verdict comes from correctness, not cost.

- **Baton**: H failed 3 of 5 runs.
- **Game repo**: both arms were 5/5 correct, but H cost 35% more.

Cost alone would have said "no difference".

N = 5 valid runs per arm per repo (20 primary runs). Total spend was **$69.25** of the $77 stop, probes
included: probes $2.90, builds $8.88, transitions $19.44, next tasks $29.81, exploratory follow-ups $8.22.

| repo | arm | correct | score | cost, warm-normalized $ | cost, raw $ | input tokens (all kinds) | cache read | cache creation | next-task first-turn context | next-task turns (main-thread messages) |
|---|---|---|---|---|---|---|---|---|---|---|
| baton (Python) | C | 5/5 | 1.00 (1.00–1.00) | 1.54 (1.41–1.64) | 2.39 (1.54–2.49) | 1,273,574 (1,041,411–1,296,258) | 927,000 (898,457–937,699) | 133,103 (114,082–142,277) | 62,126 (61,251–63,615) | 10 (8–11) |
| baton (Python) | H | 2/5 | 0.29 (0.29–1.00) | 1.18 (1.16–2.05) | 1.88 (1.17–2.93) | 1,956,106 (1,741,978–2,650,887) | 1,895,144 (1,660,557–2,508,896) | 141,947 (60,942–290,889) | 52,433 (52,031–54,594) | 4 (3–13) |
| game (TypeScript) | C | 5/5 | 1.00 (1.00–1.00) | 2.06 (1.86–2.54) | 2.07 (1.87–2.55) | 1,841,592 (1,555,695–2,224,740) | 1,672,902 (1,386,252–2,053,545) | 166,978 (145,725–173,517) | 76,511 (73,636–77,561) | 14 (11–17) |
| game (TypeScript) | H | 5/5 | 1.00 (1.00–1.00) | 2.78 (2.52–3.25) | 2.78 (2.56–3.25) | 3,444,648 (2,946,251–4,095,245) | 3,249,078 (2,773,931–3,900,627) | 183,910 (171,025–195,515) | 56,149 (56,015–56,333) | 17 (14–20) |

Values are median (min–max) per run. Cost and tokens are transition + next task. Builds: baton 11 prompts →
238,733 tokens ($3.91); game 9 prompts → 216,713 tokens ($4.97). Compaction took the context from
239,748 → ~18.6k (baton) and 217,610 → ~20.9k (game). The handoffs were about 7.6 KB (baton) and 6.8 KB (game).

### What the numbers say

- **Compaction kept everything that mattered here.** All 10 C runs passed all 7 checks, including F1, the
  detail planted in the very first prompt.
- **Handoff runs start lighter but do not cost less overall.** The next task starts at about 52–56k tokens
  against 62–77k after compaction. But writing the handoff is a multi-turn job over the full ~240k context:
  six turns of cache reads against one compaction call. So H uses more input tokens in both repos, mostly
  cheap cache reads. In the game repo H was also slower and costlier on the next task itself ($2.12 vs $1.72).
  Counting correct runs only, H cost more in both repos: baton $1.96 vs $1.54, game $2.78 vs $2.06.
- **Baton H looks cheaper ($1.18 vs $1.54) only because its failures stopped early.**

### Failure analysis

All three incorrect H runs (baton H1, H4, H5) **stopped without touching any file**. Each handoff, written
by baton's handoff skill in the transition, listed undecided points to confirm with the user before
implementing. The new session asked those questions, with recommendations, and ended its turn. No C run
stopped to ask. The game-repo handoffs did not produce this behaviour.

### Exploratory: one neutral reply (not part of the verdict)

Runs that left the target untouched (baton H1, H4, H5; no C run) got one reply, "알아서 판단해서 진행해줘":
- H1 and H5 then passed all checks, for an extra $2.24 and $2.77.
- H4's follow-up was cut off by the account's 5-hour usage limit after 447 s and is **invalid**.

Correct within at most one reply: C 10/10, H 9/10 with H4 counted as a failure. The extra round trip cost
more than the whole C run.

### Grader correction (after the runs, before the write-up)

The `forbid_bash` rule (F4: "never run npm/pip install") originally matched the phrase anywhere in a Bash
command. Game H2 never ran an install; it quoted the rule inside a heredoc that wrote HANDOFF.md, and the
grader marked F4 failed. The gate now matches only at the start of a command segment, the way
`case_grade.py` decides a command was executed. A test covers both cases, and all 20 runs plus the follow-ups
were regraded from the saved diffs, tool calls and hidden-test results. Only game H2 changed (incorrect →
correct). Before the fix the verdict was the same (k_H = 6/10).

### Threats to validity (after the runs)

1. **Baton version mix.** The owner's install was updated from 1.0.0-beta.3 to beta.4 at about 03:35 KST
   during the run. By each run's init line: baton-repo C1–C2 and H1–H2 loaded beta.3; C3–C5, H3–H5 and every
   game-repo run loaded beta.4. Baton-repo transitions all ran before the update.
2. **beta.4's automatic-handoff Stop block never fired** in any run: a separate search of every Stop
   hook_response found none. The positive control: the split notice appears 4 times in C runs. The split notice is
   shown to the user only, so it cannot change model behaviour.
3. **Narrow scope.** One task type (a step-4 CLI option after three implemented steps), opus 5.5 only,
   2 repos, n = 5 per arm, and the owner's plugin setup (OMC hooks around compaction, baton's handoff skill
   and injection). The baton result rests on one behaviour: questions the handoff told the next session to
   ask, which a single-prompt protocol counts as failure. Interactive use would cost one extra reply, as in
   the exploratory measure.
4. **Run conditions.** A harness crash stalled the run for 15 h after the first transition, and later
   baton transitions ran with a cold cache. Transition cost is warm-normalized for the verdict, and the raw
   cost gives the same verdict. A 5-hour usage limit interrupted one exploratory follow-up.
5. **Carriers outside the arms.** Sessions wrote auto-memory (game build, H2, H3, H4). The folder was moved
   out before and after every phase, and every run started with 0 memory files.
6. **Scripted sessions.** The long sessions are scripted and the planted facts are explicit, so real
   sessions may lose more in either carrier. The switch point (217k–240k tokens) is at the low end of the
   owner's real opus compaction points (median 301k).

## Round 2: handoff arm only, after the beta.5 fix (pre-registered 2026-11-24, before any round-2 run)

**Why.** Round 1's handoff failures all came from one behaviour: the handoff listed points to confirm with the
user, and the new session asked them and stopped. baton 1.0.0-beta.5 changes this. The handoff skill now writes
next actions that can be done without asking, and moves owner questions into an "Owner decisions" sub-list with
a recommended default. The injection header adds: use the default when it can be undone, and ask only about
irreversible steps. The owner decided (2026-11-24) to rerun only the handoff arm and to publish both rounds
together.

**What runs.**
- Same snapshots, same long sessions S (not rebuilt), same next-task prompt, graders and hidden checks.
- Only arm H, H1–H5 per repo: transitions first, then next tasks, then the exploratory one-reply follow-up for
  runs that leave the target untouched, as in round 1.
- Data folder: `~/.cache/baton/experiments/compact-vs-handoff-r2/`. `compact_ab.py seed` copies each round-1
  state with its build and C rows only. Round 1's records are only read; its snapshot working trees are
  reused (reset to the switch point before every phase, as in round 1).
- Environment: `CVH_DATA=<round-2 folder> CVH_CAP_USD=40 CVH_PROBE_USD=0 CVH_BATON=1.0.0-beta.5`.
  `CVH_SNAPS` points at round 1's `snapshots/` (added after the first launch stopped at the snapshot check, before any
  claude call; $0 spent).

**Guards.**
- Hard stop at $40 of reported cost for round 2. The runner refuses a phase whose cap could cross it.
- Every phase must load baton 1.0.0-beta.5. The runner stops on any other version, and the plugin is not
  updated during the run.
- Two consecutive invalid runs stop the run, and so does a rate limit that persists after backoff.

**Decision rule.** Round 1's rule, unchanged: round-2 H against round-1 C, pooled over the two repos. Both
rounds' tables are reported side by side, and round 1's verdict stands as the round-1 result.

**Known threats (stated before results).**
1. **Not concurrent.** C ran on 2026-11-24 under baton beta.3/beta.4; H runs later under beta.5. The model
   and Claude Code version may differ; each run's init line is recorded (`baton`, and the CLI version).
2. **The Stop hook changed in beta.5.** When the context passes 2× its first call, the Stop hook now blocks
   once and asks the agent to update HANDOFF.md; in round 1 that notice was shown to the user only. A round-2
   next task that grows past 2× (its first call is about 52–56k) pays for that extra handoff write, which
   round-1 C did not. Stop blocks are counted per run (`stop_blocks`) and reported. A beta.5 C arm would also
   meet this block, so the comparison is "beta.5 H vs pre-beta.5 C", not "beta.5 vs beta.5".
3. The fix targets a behaviour seen in one repo (baton). The game repo had no H failure in round 1.
4. n = 5 per repo, as in round 1.

## Round 2 results (2026-11-24)

> Corrected 2026-11-25: the game-repo C rows below are not a /compact-only arm, and without that repo the verdict
> is inconclusive. See [Correction (2026-11-25)](#correction-2026-11-25).

**Verdict, by the pre-registered rule: compact better, now on cost instead of correctness.** k_C = 10/10
(round 1), k_H = 10/10 (round 2). Correctness is tied, and H cost more in both repos: r = median over repos of
H/C median cost = 1.422 (per repo 1.735 and 1.109). C was cheaper in every repo, and 1/r = 0.70 ≤ 0.85, so the
"compact better" branch applies. The raw-cost sensitivity check gives the same verdict (r = 1.478).

- **The targeted failure did not recur.** Baton-repo H went from 2/5 (round 1, beta.3/beta.4) to 5/5 (beta.5). With n = 5 this shows the behaviour is gone in these runs, not how large the fix's effect is. No H run stopped to ask, so no
  exploratory follow-up ran. The game repo stayed 5/5.
- **Handoffs still cost more.** Writing the handoff reads the whole ~220–240k context over about six turns.
  Its warm-normalized cost was a median of $0.65–0.73 per repo (range $0.64–0.83) against $0.26–0.32 for a compaction (range $0.24–0.36). In the baton repo the next task
  itself also cost more ($1.94 against $1.27).

| repo | arm (round) | correct | score | cost, warm-normalized $ | cost, raw $ | input tokens (all kinds) | cache read | cache creation | next-task first-turn context | next-task turns (main-thread messages) |
|---|---|---|---|---|---|---|---|---|---|---|
| baton (Python) | C (1) | 5/5 | 1.00 (1.00–1.00) | 1.54 (1.41–1.64) | 2.39 (1.54–2.49) | 1,273,574 | 927,000 | 133,103 | 62,126 | 10 (8–11) |
| baton (Python) | H (2) | 5/5 | 1.00 (1.00–1.00) | 2.67 (1.83–3.28) | 2.78 (2.11–5.08) | 3,243,785 (2,300,954–3,699,618) | 3,077,239 | 174,383 | 54,703 | 15 (12–19) |
| game (TypeScript) | C (1) | 5/5 | 1.00 (1.00–1.00) | 2.06 (1.86–2.54) | 2.07 (1.87–2.55) | 1,841,592 | 1,672,902 | 166,978 | 76,511 | 14 (11–17) |
| game (TypeScript) | H (2) | 5/5 | 1.00 (1.00–1.00) | 2.29 (1.95–3.41) | 3.71 (1.95–5.05) | 3,224,534 (2,821,486–4,083,219) | 2,840,664 | 372,952 | 56,456 | 14 (12–21) |

Values are median (min–max) per run; the C rows are round 1's. Round 2 spent **$33.61** of its $40 stop
(transitions $15.44, next tasks $18.17, no follow-ups). Handoffs were 7.3–8.7 KB (baton) and 7.0–7.2 KB (game).

**Checks on the pre-stated threats.**
- **Baton version:** all 20 round-2 calls loaded 1.0.0-beta.5 (init line). The version guard never tripped.
- **Stop hook:** it never blocked. One run (game H1, 56k → 118k) crossed 2×, but its session had already updated
  HANDOFF.md in that turn, so beta.5 only showed the user its "already saved" notice. Seven of the ten next-task sessions updated HANDOFF.md on their own before ending (baton H1 and H3, all five game runs). That extra write likely adds to H's cost here; the data doesn't separate it.
- **Not concurrent:** C ran within about the previous 24 hours (2026-11-23 11:03 to 11-24 07:30; round 2 started 11-24 20:23), under beta.3 (baton transitions, some next tasks) and beta.4. The two rounds used the same snapshots,
  the same long sessions and the same model (opus 5.5). Claude Code: round 1 mostly 2.1.330 (its last three game next-task runs 2.1.331), round 2 all 2.1.331.

**What this says.** In these 10 runs no handoff run lost work, but continuing with /compact was cheaper.
A handoff's advantage, a page a person can read and edit, isn't measured here.

## Round 3 and W (2026-11-25)

Two follow-ups, each pre-registered before its main run, with method, deviations and full tables in
[compact-vs-handoff-r3.md](compact-vs-handoff-r3.md#results-2026-11-25). Both reuse the long sessions S above.

- **W, the handoff write in 1.0.1** (5 writes per repo, a build byte-identical to `v1.0.1` in skills, hooks and lib):
  **cheaper** by the pre-stated rule. Median warm-normalized cost per write $0.726 → $0.670 (baton) and $0.653 →
  $0.570 (game repo); assistant calls 6 → 5 and 6 → 6. Nine of the ten handoffs kept every fact marker the round-2
  handoffs had added; one game-repo write missed one.
- **Round 3, the next day and a different task** (the cache has expired; the game repo's start state no longer holds
  the build's handoff, and its compactions were redone on it; 2 repos, 3 pairs each): correct C 5/6, H 4/6.
  - Against compacting the next morning: **no difference detected** (H/C cost 0.86; H was 13–14% cheaper in both
    repos, short of the rule's 15%, at n = 3).
  - Against compacting at the end of the day: **compact better** (H/C cost 1.32).
  - In the game repo a control run with neither carrier passed on the first prompt (its rerun on the revised prompt
    read the rule from the old session's transcript on disk instead), so that repo's correctness does not separate
    the arms. Baton's
    two H misses had the rule in their handoff but followed the prompt's instruction instead.
