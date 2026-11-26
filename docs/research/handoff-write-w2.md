# Handoff write cost, W2: the 1.0.3 write against 1.0.1's (pre-registration)

> **Status: pre-registration, written 2026-11-26 before any W2 run, and amended the same day after a review, still
> before any W2 run** (the list is at the end, before the results). $0 of W2's ledger has been spent. Before this
> document was written, four mechanism probes ran in scratch repositories with Haiku ($0.04 together, outside the
> ledger; listed below). The implementation's own smoke tests are listed with their cost in the results section.
> Results will be added below this line without changing the rule.

## Question

W (`compact-vs-handoff-r3.md`, Part 2) measured 1.0.1's handoff write: a median of 5 (baton repo) and 6 (game repo)
assistant calls over a ~220–250k context, warm-normalized $0.670 (baton repo) and $0.570 (game repo) per write. Every
call re-reads the whole context from cache, about $0.05 at that size. 1.0.1's skill text is 23.8 KB (23,773 bytes),
about 8k tokens, and is written to the cache on every write, about $0.06.

W2 measures the 1.0.3 release candidate. Two releases separate it from 1.0.1, and both change the write path.

**What 1.0.2 changed on the write path** (`git diff v1.0.1 v1.0.2 -- skills/baton/SKILL.md hooks/`):
- **The skill** (23.8 KB → 24.7 KB) says to change `HANDOFF.md` with the file-editing tool, not through Bash. It
  describes the checker's size message (over 8,700 characters it says how many to cut and names the two largest
  sections; while the file is over a limit, a save that makes it shorter only warns) and says a size problem blocks
  at most once per turn. It also spells out when the Stop hook asks for a handoff (turn rules; a Bash call that names
  a handoff file and changes `HANDOFF.md` counts as writing it).
- **The handoff checker also runs on Bash calls:** the PostToolUse matcher `Write|Edit|MultiEdit` gains `Bash`, and
  a new PostToolUseFailure entry for `Bash` runs the same checker, which reports a failed call's problems as context
  instead of blocking.
- **The drift notice is shown at most once a day.** `hooks/drift-notice.sh` keeps the same concept-map notice back for
  24 hours, with its state in the cache folder (see Design).

**What 1.0.3 changes in the write:**
1. **The skill fills in the pre-write state when it loads.** The promotion review's short form plus
   `git status --short --branch` and `git log --oneline -3` used to be the first Bash call of every write. Claude
   Code's dynamic context injection now runs them when the skill loads.
2. **Save and commit in one response.** Write `HANDOFF.md` and, in the same assistant message, the commit Bash call.
3. **A shorter skill.** Rationale and evidence move to a reference file next to the skill. Every instruction stays.

The verdict compares the 1.0.1 build with the 1.0.3 build **as wholes**. 1.0.2's changes are in it too, so what the
expectation below credits to the three 1.0.3 changes cannot be tested on its own.

Does the 1.0.3 write cost less than 1.0.1's **without losing any fact W's handoffs carried**?

## Mechanism probes (before this document, scratch repositories, Haiku, $0.04)

- **Dynamic injection works in a plugin skill.** Tried on Claude Code 2.1.332 and on 2.1.331, the version W pinned.
  `${CLAUDE_PLUGIN_ROOT}` is substituted, the command runs in the session's cwd, and its output replaces the line.
- **A failing command breaks the skill.** If the command exits non-zero, the skill does not load ("Shell command
  failed for pattern …"), so the command must exit 0 on every path.
- **A command the permissions do not allow does not break it.** Claude Code puts "[run this first, exactly as
  written, and use its output: …]" in its place, and the model runs it as a Bash call: the 1.0.1 behaviour.
- **Write and Bash in one assistant message run in that order.** A PostToolUse block on the Write still let the Bash
  call run, and the block reason arrived after both results.

## Design (W's, unchanged except where marked)

- **What runs:** W's transition, unchanged: `claude -p "핸드오프 작성해줘" --resume S --fork-session --max-turns 15
  --max-budget-usd 3`. Same snapshots, same switch point B1, 5 runs per repo, alternating repos (W1 baton, W1 game,
  W2 baton, …).
- **Build (new):** the 1.0.3 release candidate, with its version string `1.0.3`. It is staged by `wstage` from the
  release worktree with everything committed, and frozen at the first run, as in W. It carries 1.0.2's and 1.0.3's
  hook changes, so W2 measures the 1.0.3 build's write, not the skill text alone (as W did for 1.0.1). Its manifest
  goes into the next section before W1.
- **Pins (as W):** CLI binary 2.1.331, OMC 5.8.7, `claude-opus-5-5`, effort xhigh. The staged baton is loaded with
  `--plugin-dir` plus `--settings` disabling `baton@baton`. The owner's install is not touched.
- **Version guards (new):** `CVH_BATON=1.0.3` is the staged build. `CVH_BATON_INSTALLED=1.0.1` is the owner's
  install, for preflight and the probe's control session. In W the two were the same string.
- **Data:** a new folder `write-cost-2`, seeded from round 2's handoff arm, as W was. W's own folder is only read.
- **Probe:** W's `wprobe`, unchanged: a control session (the installed 1.0.1) and a staged-build session must load
  the same plugin names, baton skills and hook counts per event, and the owner's files must be byte-identical before
  and after. What it cannot see: the candidate's `hooks/hooks.json` differs from v1.0.1's only in tool-call
  registrations (the PostToolUse matcher gains `Bash`; the PostToolUseFailure entry for `Bash` is new), and the
  probe's per-event hook counts come from one-word sessions that make no tool call, so they cannot show that
  difference. The scripts behind SessionStart (`drift-notice.sh`), UserPromptSubmit (`handoff-inject.py`) and Stop
  (`handoff-check.py`) also changed, and the probe compares no hook output. W2 therefore reports each run's
  PostToolUse and PostToolUseFailure hook counts next to W's.
- **Environment check (new, $0):** once, after the probe and before W1, the lead runs `wenv`. It compares the staged
  probe session's init line with W's baton W1 init line: the plugin names and versions other than baton, the MCP
  server names, the tool count and the skill count, and prints the differences. Any difference is written into
  this document before W1 and reported with the results. `wreport` also prints each run's first-turn input (cache
  creation + cache read + input of the first main-thread call) for W and W2: W's was 243,079 tokens in all five baton
  runs and 222,640 in four game-repo runs (222,932 in W1).
- **Drift-notice state (new):** from 1.0.2, `hooks/drift-notice.sh` keeps a repeated notice back for 24 hours. It
  stores what it last showed in `${XDG_CACHE_HOME:-~/.cache}/baton/drift/shown-<cksum of "<language>|<CONCEPTS.md
  path>">`, outside the snapshot, so the snapshot reset does not clear it. Every W run, in both repos, carried that
  notice (1.0.1 has no such limit); without a reset, only the first session per repo would. Before each W2 run (and
  before a retry after a rate limit), `write_one` removes only those `shown-` files for the snapshot repo's concept
  map, in both languages, and records the removed paths in the run record (`drift_notice_reset`). No other cache
  file is deleted.
- **Budget:** owner cap $20 for this measurement (2026-11-26). Side probes and smoke tests are capped at **$4 in
  total**, inside the $20. The runner's cap `CVH_CAP_USD` is set to $20 minus their reported cost; the W2 probe is
  charged inside it. Smoke tests never resume or fork S and never run in the snapshot repositories W2 uses. The runner
  refuses a call when spent + $3 + $0.50 > cap. A write whose first turn misses the cache cost W $2.2–2.5 raw, so an
  all-cold W2 stops after about 7 runs at a $20 cap (5–6 if the side costs use their whole $4). The verdict uses the
  valid runs.

## Build (filled at staging, before W1)

Staged 2026-11-26 23:22:46 by `wstage` from the release worktree with nothing uncommitted:
- source head `28a7d967ff3c8d80701ccdc613ad71bd9038c68b` (branch `release-1.0.3`), version string `1.0.3`;
- 133 files, tree hash `b7b9e624689fa93b79137819d42529208b940676bd416b46830873c94b30e02e`;
- `skills/baton/SKILL.md` sha256 `77047e1e5e5c87a309e55d8dcc9b22d2d267f0b33dbc31ce524a734851c437bf` (11,948 bytes);
- `hooks/hooks.json` sha256 `87a5a86984484858e21a52a2abf88d1e74cb64b9de56d763b4b876462d07439e`.

Before W1 (W2 ledger $0.50, both probe sessions):
- `preflight` passed: installed baton 1.0.1, OMC 5.8.7, CLI 2.1.331 pinned, opus 5.5 at xhigh, child environment
  clean.
- `wprobe` passed all seven checks. The staged session loaded one baton, 1.0.3, from the staged folder. Hook counts
  per event matched the control's: SessionStart 7, UserPromptSubmit 4, Stop 7. The owner's files were unchanged.
- `wenv` against W's W1 found:
  - the same 7 non-baton plugins and the same 9 MCP servers;
  - **tools 306 → 310** and **non-baton skills 147 → 145**, a drift in the owner's environment since W.

  This adds or removes a few thousand prefix tokens per call, which is small against the expected effect. It is
  reported, not corrected.

Side costs before W1, outside the W2 ledger and inside the owner's $20:
- the lead's mechanism and review probes (Haiku): $0.065;
- an implementation probe for subagent Bash timing (Haiku): $0.015;
- the skill change's smoke test (Sonnet): $0.652;
- total: $0.73.

`CVH_CAP_USD` is therefore $19.20.

## Comparison (pre-stated)

Per repo, W's 5 valid runs (1.0.1) against W2's valid runs:
- **assistant calls** (main-thread API messages; W: 5, 5, 5, 5, 5 in the baton repo; 5, 6, 6, 8, 6 in the game repo);
- **warm-normalized write cost** (`warm_cost`, as in W; W: baton $0.670 ($0.575–0.718), game $0.570
  ($0.558–0.688));
- **raw cost**, descriptive;
- **first-turn input**, descriptive (W: above);
- **required fact markers** in the added lines of each W2 handoff: W's required set (the markers in the added lines
  of every round-2 patch: F1–F6 in the baton repo; F2 and F6 in the game repo). The same markers in the whole file
  are printed next to them, descriptive;
- descriptive, recorded per run by `write_one` from the run's raw stream and printed by `wreport` (for W, read from
  W's raw streams):
  - `state_filled`: the Skill tool result, with the skill text loaded after it, holds `git status --short --branch`
    and `git log --oneline` output and no "[run this first" text (W: 0 of 10);
  - `write_commit_one_message`: the Write/Edit of `HANDOFF.md` and the `git commit` Bash call share one assistant
    message id (W: 0 of 10);
  - `commits`: the number of `git commit` Bash calls (W: 1 in every run);
  - `posttool_blocks`: PostToolUse hook responses with `"decision": "block"` (W: 0);
  - Stop blocks (W: 0);
  - hook counts per event (the run record's `hooks`), with PostToolUse and PostToolUseFailure printed per run;
  - handoff bytes;
  - the drift-notice files removed before the run.

Expectation, stated before any run: about two fewer assistant calls per write (baton 5 → 3, game 6 → 4) and roughly
$0.10 less per write, credited to the three 1.0.3 changes. The rule compares whole builds, so this credit is not
tested. This is not part of the rule.

## Decision rule (pre-stated, before any W2 run)

Valid W2 runs only. W's validity rules are unchanged: invalid means no result line, a rate limit, an error result
other than the turn or budget cap, a broken cost delta, a wrong build loaded, or a tool call into the installed
build. Each repo needs ≥ 3 valid W2 runs, and W's folder ≥ 3 valid W runs, else **inconclusive**. The ratio is the
median warm-normalized cost of the valid W2 runs over that of W's valid runs, per repo.
- **Cheaper than 1.0.1:** the ratio is **≤ 0.90 in both repos**, **and** facts are kept: at most one valid W2
  handoff misses a required marker. A valid run that wrote no handoff misses them all.
- **Not shown cheaper:** facts kept, the median lower in both repos, but the ratio above 0.90 in at least one.
- **Not cheaper:** facts kept, but the median is not lower in both repos.
- **Loses facts:** more than one valid W2 handoff misses a required marker.

**Why a margin.** W's warm costs spread about ±11% around their medians (half the min–max range: baton 10.7%, game
repo 11.4%). W2's runs are compared with runs made a day earlier, five against five. If nothing changed, each repo's
W2 median comes out below W's about half the time, so "lower in both repos" would come out about 25% of the time
without a margin. W's own rule against round 2 stays as it was (no margin).

Reported next to the verdict, pre-stated and not part of it:
- **Mechanism line:** "median assistant calls lower by ≥ 1 in both repos": confirmed or not confirmed.
- **Margin-free line** (descriptive): whether the median is lower in both repos, with the two ratios.

The runner computes the verdict and both lines with `CVH_WREF=<W's folder>` (`wverdict(states, ref_states)`; the
margin is `W2_RATIO = 0.90`, used only with a reference W). It also judges the W2 runs by W's own rule against
round 2, printed as "(secondary: W2 runs by W's rule vs round 2)" and reported as a secondary line. Assistant calls
and raw cost are reported per repo whatever the verdict. Like W, W2 says nothing about next-task correctness.

## Known threats (stated before results)

1. **Not concurrent with W.** W ran on 2026-11-25 and W2 a day later. The CLI binary, OMC, model and effort are
   pinned to W's. The rest of the environment (other plugins, MCP servers, tools, skills) is not pinned; `wenv` and
   the first-turn input show whether it moved.
2. **Cache state** changes raw cost a lot (≈ $1.8 per cold first turn). The verdict uses warm-normalized cost, as W
   did.
3. **The trimmed skill may change handoff quality in ways the markers do not see.** Markers are regexes: present ≠
   correct. n = 5 per repo.
4. **One-message save and commit is a model behaviour,** not a guarantee. W2 reports how often it happened.
5. **Claude Code only.** Codex shows the injection line as text and is told to run it, so a Codex write keeps the
   1.0.1 call count. W2 does not measure Codex.
6. **Whole builds, not single changes.** The verdict cannot say which of 1.0.2's or 1.0.3's changes moved the cost.
7. **The probe does not cover the changed hooks.** Its sessions make no tool call and it compares no hook output, so
   a hook that misbehaves on a tool call shows only in the runs (hook counts, PostToolUse and Stop blocks).
8. **Added-line markers depend on edit style.** In the game repo, B1 already holds a handoff with the markers. A write
   that edits that file and leaves a marker's line untouched adds no line with it, so the run counts as missing that
   fact although the file still states it. W's only miss (game repo W5, F6) was of this kind. A build that edits in
   place more than 1.0.1 did can lose markers by this count alone; `wreport` prints the whole-file markers next to
   the added-line ones.

## Open questions (not settled before the runs)

1. When `HANDOFF.md`'s Write and the commit share one assistant message, does 1.0.2's Bash handoff check fire on the
   commit call, and can it block there?
2. In `-p` sessions (W's init lines record permission mode `auto`), are the skill's injection commands judged by the
   auto-mode classifier, and can that turn the state block into the "[run this first" placeholder? `state_filled`
   shows which happened, not why.

## Amendments before any W2 run (review, 2026-11-26)

An independent review of the pre-registration and runner (commit 4c112c7) asked for the changes below. They were made
and committed before any W2 run, at $0. Amendment n answers the review's finding n.

1. **The probe's hook claim was false.** Reworded (Design, Probe): the probe cannot see the tool-call registrations
   that differ, and the changed SessionStart, UserPromptSubmit and Stop scripts are not compared. Each run's
   PostToolUse and PostToolUseFailure hook counts are printed next to W's.
2. **1.0.2 was left out.** Its write-path changes are listed (Question); the verdict compares whole builds, so the
   expectation's credit to three changes is not tested; PostToolUse check blocks (`posttool_blocks`) are recorded
   per run.
3. **No noise margin.** "Cheaper than 1.0.1" now needs a ratio ≤ 0.90 in both repos; "not shown cheaper" is new; the
   mechanism line and the margin-free line are pre-stated. The runner's margin is the constant `W2_RATIO`, used only
   with a reference W; tests cover ratios 0.89 (cheaper) and 0.91 (not shown cheaper).
4. **Environment drift.** New `$0` command `wenv`, run once after the probe and before W1; `wreport` prints the
   first-turn input for W and W2 (W's values checked from its raw streams).
5. **Drift-notice state outside the snapshot.** `write_one` removes only that notice's `shown-` files for the
   snapshot repo before each run and records what it removed.
6. **Budget text.** Side probes and smoke tests capped at $4 inside the $20; the all-cold stop is about 7 runs, not
   8–9; smoke tests never resume or fork S and never use the W2 snapshots.
7. **Descriptive metrics recorded, not only named.** `write_one` records `state_filled`,
   `write_commit_one_message`, `commits` and `posttool_blocks` from the raw stream (hook counts were already in
   `hooks`); `wreport` prints them; a test checks them on a synthetic stream.
8. **Numbers.** 1.0.1's skill is 23.8 KB (24.7 KB is 1.0.2's); the context is ~220–250k.
9. **Test isolation.** The runner's tests drop `CVH_BATON_INSTALLED` and `CVH_WREF` from the environment, and pass
   with both exported.
10. **Missing reference file.** A repo without a state file in `CVH_WREF` loads as empty, so the verdict says
    inconclusive instead of the report failing.
11. **Labels.** Against a reference the new runs are called W2 ("warm W2 … vs W …"); the round-2 line is tagged
    "(secondary: W2 runs by W's rule vs round 2)".
12. **Build identification.** New section "Build (filled at staging, before W1)".
13. **Added-line markers depend on edit style.** New threat 8; `wreport` prints whole-file markers next to the
    added-line ones.
14. **Launcher.** `run.sh stage` (outside git) runs `preflight` before the paid `wprobe`.

## Amendments before any W2 run (build changes from the code review, 2026-11-26)

An independent code review of the 1.0.3 candidate changed the build after this pre-registration was written. The
items below record what changed and what the lead checked about it before W1, all at $0 of W2's ledger.

15. **The commit is gated by the checker.** The second change now reads: in the same assistant message as the
    Write, one Bash call runs `python3 "…/lib/handoff_check.py" HANDOFF.md && git add HANDOFF.md && git commit …`.
    Without the gate, content the checker blocks (secrets, home paths) would be committed before the check reported
    it. The gate adds no assistant call. `commits` and `write_commit_one_message` still detect the call, by its
    `git commit`.
16. **The injection line is quoted:** `bash "${CLAUDE_PLUGIN_ROOT}/lib/promote.sh" --brief --status .`, with a
    matching `allowed-tools` entry. A probe on CLI 2.1.331 (Haiku, scratch repo, a plugin path containing a space)
    showed the quoted form filled in at load.
17. **Open question 1, about the Write's own check, is settled.** A probe on 2.1.331 put a Write and a Bash in one
    assistant message, with a PostToolUse hook on the Write that slept 1.5 s. The hook finished before the Bash
    started, so the save-time check compares with the commit before this write. (The question as written, about
    the Bash handoff check on the commit call, stays open.)
18. **Other build changes from the same review:**
    - the context-threshold Stop no longer counts a background completion queued into a question-only turn;
    - the dropped-lines warning stops looking at verified facts and next actions (owner decision, 2026-11-26), so a
      write may see fewer warnings and make fewer follow-up edits;
    - `promote.sh` timing and output-order fixes.

    The verdict still compares the 1.0.1 and 1.0.3 builds as wholes (threat 6).

---

## Results (2026-11-26, runs 23:23–23:43)

**Verdict (pre-registered, against W): not shown cheaper.** The median warm-normalized cost per write fell in both
repos, but by less than the 10% the rule asks for:

| | assistant calls per write | warm-normalized cost, median [range] | raw cost, median | handoff bytes, median | required facts kept |
|---|---|---|---|---|---|
| baton repo, W (1.0.1) | 5 (all five) | $0.670 [0.575–0.718] | $0.670 | 8,314 | 5/5 |
| baton repo, W2 (1.0.3) | 3 (all five) | $0.625 [0.531–0.643] | $0.643 | 9,277 | 5/5 |
| game repo, W (1.0.1) | 6 (5–8) | $0.570 [0.558–0.688] | $2.211 | 6,752 | 4/5 |
| game repo, W2 (1.0.3) | 4 (all five) | $0.541 [0.525–0.606] | $0.606 | 6,922 | 4/5 |

- **Ratios W2/W:** 0.93 (baton repo) and 0.95 (game repo). The rule needed ≤ 0.90 in both, so: not shown cheaper.
  The margin-free line, also pre-stated, is "lower in both repos".
- **Mechanism: confirmed.** The median assistant calls per write fell by 2 in both repos (5 → 3, 6 → 4).
- **Facts:** 9 of 10 valid W2 handoffs carry every required marker in their added lines. That is the same count as
  W. The miss is game-repo W4 (F6), the same fact W's one miss lost. The count is by added lines only: W4's whole
  file still states F6, as W's missing handoff did (threat 8).
- **Secondary** (W2's runs by W's rule against round 2): cheaper, with ratios 0.86 and 0.83.
- **All ten runs were valid; there were no retries.**
- **Descriptive:**
  - the skill's state block was filled in at load in 10 of 10 runs;
  - the Write and the gated commit came in one assistant message in 10 of 10;
  - every run made one commit;
  - there were 0 PostToolUse check blocks and 0 Stop blocks.
- **Descriptive, against W:**
  - First-turn input: W2 baton 243,173–243,350 tokens (W: 243,079); game 222,734–222,932 (W: 222,640–222,932).
  - Hook calls per run: PostToolUse:Bash 5 in the baton repo (W: 8; W's W5 had 4, plus 2 PostToolUseFailure). In
    the game repo, PostToolUse:Bash 10 plus Read 5 (W: Bash 8–20). W2 had no PostToolUseFailure.
  - The drift-notice state was reset before 9 runs (one file each). Game-repo W1 had nothing to reset.
  - The environment drift that `wenv` found (tools 306 → 310, non-baton skills 147 → 145) is in the Build section.

**Where the money went** (descriptive; all five runs per cell; the first turn's cache creation is repriced as cache
reads, as `warm_cost` does; components priced as in W, with the rest by subtraction from the warm-normalized cost):

| per write, median | cache reads | cache writes | the rest (output, including thinking) | warm-normalized total |
|---|---|---|---|---|
| baton repo, W → W2 | $0.253 → $0.148 | $0.188 → $0.190 | $0.230 → $0.285 | $0.670 → $0.625 |
| game repo, W → W2 | $0.278 → $0.184 | $0.167 → $0.179 | $0.148 → $0.181 | $0.570 → $0.541 |

- **The call cut did what it was built for.** Re-reading the context cost about 9–10 cents less per write: two
  calls at about 223–245k tokens, close to the pre-stated expectation of about $0.10.
- **Output grew by about 3–6 cents.** Together with slightly larger cache writes, that took back about half to
  two-thirds of the read saving. The net medians fell 4.5 cents (baton repo) and 2.9 cents (game repo).
- **Where the extra output went was not measured.**
  - Most of it is not in visible text or tool inputs. At the median, visible output grew by about 390 characters
    (baton) and about 50 (game). Output tokens grew by about 2,750 and 1,600. So it is probably hidden thinking.
  - The longer handoffs account for a small part: about 960 and 170 bytes, medians over all runs.
  - Per-turn output can't be read from the stream, so whether the one save-and-commit turn thinks more was not
    measured.

**Other observations:**
- **Third-carrier flag.** It fired in all five game-repo runs. Each listed the project's auto-memory folder
  (`ls ~/.claude/projects/<project>/memory`), which preflight had found empty, and every listing came back empty.
  W's game-repo W1, W2, W4 and W5 did the same: the flag fired in four of W's five game-repo runs. Nothing was read
  from the folder.
- **Cold first turns.** Four of the ten writes started cold, costing $2.15–2.41 raw each. The warm-normalized cost
  reprices them, as in W.

**Cost:**
- W2 ledger $13.16: the probe $0.50, the ten writes $12.66.
- Side costs $0.73.
- Total $13.90, inside the owner's $20.

**What this supports:**
- The 1.0.3 write needs two fewer assistant calls.
- At this context size, it spent about 9–10 cents less re-reading the conversation. Its output grew by about 3–6
  cents, for a reason not measured.
- In these runs, the net saving was 5–7%. That is inside the pre-stated noise margin, so W2 does not claim the 1.0.3
  write is cheaper.
- Next-session correctness was not measured.
