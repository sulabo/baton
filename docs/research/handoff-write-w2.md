# Handoff write cost, W2: the 1.0.3 write against 1.0.1's (pre-registration)

> **Status: pre-registration, written 2026-11-26 before any W2 run.** $0 of W2's ledger has been spent. Before this
> document was written, four mechanism probes ran in scratch repositories with Haiku ($0.04 together, outside the
> ledger; listed below). The implementation's own smoke tests are listed with their cost in the results section.
> Results will be added below this line without changing the rule.

## Question

W (`compact-vs-handoff-r3.md`, Part 2) measured 1.0.1's handoff write: 5–6 assistant calls over a ~230–250k
context, warm-normalized $0.670 (baton repo) and $0.570 (game repo) per write. Every call re-reads the whole context
from cache, about $0.05 at that size. The skill text is 24.7 KB, about 8k tokens, and is written to the cache on
every write, about $0.06. The 1.0.3 build makes three changes to the write:

1. **The skill fills in the pre-write state when it loads.** The promotion review's short form plus
   `git status --short --branch` and `git log --oneline -3` used to be the first Bash call of every write. Claude
   Code's dynamic context injection now runs them when the skill loads.
2. **Save and commit in one response.** Write `HANDOFF.md` and, in the same assistant message, the commit Bash call.
3. **A shorter skill.** Rationale and evidence move to a reference file next to the skill. Every instruction stays.

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
  release worktree with everything committed, and frozen at the first run, as in W. It also carries 1.0.3's hook
  fixes, so W2 measures the 1.0.3 build's write, not the skill text alone (as W did for 1.0.1).
- **Pins (as W):** CLI binary 2.1.331, OMC 5.8.7, `claude-opus-5-5`, effort xhigh. The staged baton is loaded with
  `--plugin-dir` plus `--settings` disabling `baton@baton`. The owner's install is not touched.
- **Version guards (new):** `CVH_BATON=1.0.3` is the staged build. `CVH_BATON_INSTALLED=1.0.1` is the owner's
  install, for preflight and the probe's control session. In W the two were the same string.
- **Data:** a new folder `write-cost-2`, seeded from round 2's handoff arm, as W was. W's own folder is only read.
- **Probe:** W's `wprobe`, unchanged: a control session and a staged-build session must load the same plugin names,
  baton skills and hook counts per event, and the owner's files must be byte-identical before and after. The hooks
  that differ between 1.0.1 and the candidate fire on tool calls only, and the probe sessions make none.
- **Budget:** owner cap $20 for this measurement (2026-11-26), side probes and smoke tests included. The runner's
  cap `CVH_CAP_USD` is set to $20 minus their reported cost. It refuses a call when spent + $3 + $0.50 > cap, so W2
  may stop after 8–9 runs if many first turns miss the cache, as W foresaw. The verdict uses the valid runs.

## Comparison (pre-stated)

Per repo, W's 5 valid runs (1.0.1) against W2's valid runs:
- **assistant calls** (main-thread API messages; W: 5, 5, 5, 5, 5 in the baton repo; 5, 6, 6, 8, 6 in the game repo);
- **warm-normalized write cost** (`warm_cost`, as in W; W: baton $0.670 ($0.575–0.718), game $0.570
  ($0.558–0.688));
- **raw cost**, descriptive;
- **required fact markers** in the added lines of each W2 handoff: W's required set (the markers in the added lines
  of every round-2 patch: F1–F6 in the baton repo; F2 and F6 in the game repo);
- descriptive:
  - whether the skill's state block was filled in;
  - whether Write and the commit came in one message;
  - second commits;
  - Stop blocks;
  - handoff bytes.

Expectation, stated before any run: about two fewer assistant calls per write (baton 5 → 3, game 6 → 4) and roughly
$0.10 less per write. This is not part of the rule.

## Decision rule (pre-stated, before any W2 run)

Valid W2 runs only. W's validity rules are unchanged: invalid means no result line, a rate limit, an error result
other than the turn or budget cap, a broken cost delta, a wrong build loaded, or a tool call into the installed
build. Each repo needs ≥ 3 valid W2 runs, else **inconclusive**.
- **Cheaper than 1.0.1:** the median warm-normalized cost of the valid W2 runs is lower than W's in **both** repos,
  **and** at most one valid W2 handoff misses a required marker. A valid run that wrote no handoff misses them all.
- **Loses facts:** more than one valid W2 handoff misses a required marker.
- **Not cheaper:** facts kept, but the median is not lower in both repos.

The runner computes this with `CVH_WREF=<W's folder>` (`wverdict(states, ref_states)`). It also prints W's original
verdict against round 2, reported as a secondary line. Assistant calls and raw cost are reported per repo whatever
the verdict. Like W, W2 says nothing about next-task correctness.

## Known threats (stated before results)

1. **Not concurrent with W.** W ran on 2026-11-25 and W2 a day later. The CLI binary, OMC, model and effort are
   pinned to W's.
2. **Cache state** changes raw cost a lot (≈ $1.8 per cold first turn). The verdict uses warm-normalized cost, as W
   did.
3. **The trimmed skill may change handoff quality in ways the markers do not see.** Markers are regexes: present ≠
   correct. n = 5 per repo.
4. **One-message save and commit is a model behaviour,** not a guarantee. W2 reports how often it happened.
5. **Claude Code only.** Codex shows the injection line as text and is told to run it, so a Codex write keeps the
   1.0.1 call count. W2 does not measure Codex.

---

## Results

(Not run yet.)
