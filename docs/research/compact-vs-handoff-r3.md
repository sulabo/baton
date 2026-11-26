# Compact vs handoff, round 3: the next day and a different task (pre-registration), and a write-cost re-measure (W)

> **Results appended 2026-11-26: see [Results (2026-11-25)](#results-2026-11-25).** W: **cheaper** (9 of 10 handoffs
> kept every required fact). Round 3, different task: **no difference detected** against compacting the next morning,
> **compact better** against compacting at the end of the day. W's cap was raised from $15 to $27 after its guard
> stopped it at nine runs (Deviation 18). The pre-registration text below is unchanged apart from this note.
>
> Published 2026-11-26 as one squashed commit. The step-by-step history is kept on the author's local branch
> `exp-next-day` (ad204a1 … cb04d0d). Its commit times show the pre-registration and its amendments (2026-11-25,
> 02:23–08:45 KST) came before the first main run (10:46).

> **Status: pre-registration, committed 2026-11-25 before any main run.** Two paid experiments are prepared here:
> **round 3** (next day, different task; hard stop $40) and **W** (re-measure only the handoff write with the new,
> cheaper handoff skill; hard stop $15). At commit time $0 has been spent on either. The only paid calls allowed
> before the main runs are the feasibility probes described below (at most $2.00 together, counted inside the caps);
> their results are appended in a later commit, before any main run. The game repo is called "the game repo"
> throughout; its name, paths and internal file names stay out of this file.
>
> Runner: `observer/research/compact_ab.py` (tests: `test_compact_ab.py`). Public specs: `compact_ab/baton_t2.json`,
> `baton_t2_hidden.py`, `baton_t2_ref.py`, `baton_w.json`. The game repo's specs, hidden checks and reference
> implementation live only in the data folders. Raw data stays outside any repo.
> Rounds 1 and 2: `docs/research/compact-vs-handoff.md`.

## Owner decisions (2026-11-25)

Round 3:
- **Budget plan A: hard stop $40**, probes included.
- **Report both cost lines** (morning and evening). A one-line summary never drops the condition.
- **Game-repo start state B1′** (B1 without the HANDOFF.md the build session wrote; see "Found while drafting", item 3).
- **C carrier: reuse round 1's compactions** through a truncated fork, after one probe of about $0.5. If the probe
  fails, compact afresh on day 2 with 4 repetitions per repo.
- **Arm N excluded.** **Arm Z: one run per repo.**
- **The next-task prompt contains the trigger word "이어서"**, so baton injects HANDOFF.md as in normal use.
- **The two different tasks as drafted** (baton `--by-date`, game repo `--before`).

W:
- Rerun **only the handoff-writing transition** (prompt `핸드오프 작성해줘`, the same long sessions S, the same
  switch point) **5× per repo = 10 runs** with the new handoff skill, **hard stop $15**.
- Compare with round 2's 10 transitions on assistant calls, warm-normalized cost, raw cost, and whether each new
  HANDOFF.md still contains every fact marker the round-2 handoffs contained (a file check; no next tasks).
- Load that plugin build without touching the owner's installed baton (1.0.0, user scope) or other sessions.

---

# Part 1. Round 3: the next day, and a different task

## Question

Rounds 1 and 2 measured one moment: the cache is still warm at a task boundary, and the session goes straight on to
the **same** planned task. Under those conditions /compact was cheaper (round 2: correctness 10/10 for both arms,
H/C cost ratio 1.42).

baton's intended use is different. Work stops for the day. The next work happens in a **new session the next day**,
when the prompt cache has expired, and it is often a **different task**. A handoff can be written at the end of the
day while the cache is still warm. The next morning every arm starts cold.

Under those next-day conditions, is a handoff written at the boundary better than compacting, for the planned task
and for a different one? "Better" means the same as before: the task is done at least as correctly, at lower cost
(or with fewer input tokens or turns). The design can return handoff better, compact better, trade-off, no
difference detected, or inconclusive.

## Found while drafting (from data already on disk, $0)

1. **Round-2 handoffs can be reused as they are.** Five per repo, 7.3–9.2 KB each, touching only HANDOFF.md. They were
   written under baton 1.0.0-beta.5, and the handoff skill, hooks and lib are byte-identical in the installed 1.0.0
   (`git diff --stat v1.0.0-beta.5 v1.0.0 -- skills hooks lib` is empty; `v1.0.0-beta.4..v1.0.0-beta.5` on the same
   paths shows 11 files, so the command can return something).
2. **Round-1 compactions still exist but are not clean forks.** All 10 compacted sessions are on disk, each with one
   `compact_boundary` and one summary. Round 1's next task resumed them without `--fork-session`, so each transcript
   also holds that task's work. Claude Code 2.1.331 has an undocumented print-mode flag, `--resume-session-at
   <message id>` (resume only up to that entry), and a companion, `--resume-drops-turn <prompt uuid>`, whose help text
   says the resume "is refused if the discarded range contains anything not attributable to that turn". Hence the probe.
3. **The game repo's C arm was never compaction-only.** The game repo's build session wrote HANDOFF.md itself; the
   harness's post-build commit put it into the switch point B1 (5,591 bytes, with markers for F1, F2, F4 and F6).
   Every game-repo C next task in rounds 1–2 got a baton injection of 9,302 characters with those markers. The baton
   repo is clean (its B1 has no HANDOFF.md; its C injection, 2,722 characters, has no fact marker). So in the game repo
   rounds 1–2 compared compaction **plus a handoff the session wrote itself** against a handoff written by the skill.
   The published write-up does not say this. Round 1's verdict rests on the baton repo's correctness gap, which is
   unaffected; round 2's cost verdict pools the game repo's ratio (1.109), which is affected. The method also promised
   fact tags (conversation-only / also-in-repo), but no state file stored them; round 3 stores them.
   Checked on 2026-11-25 for all ten compactions: the hooks that run right after each compaction (before the cut
   point) added only short notices (62–787 characters, none with HANDOFF.md content). The compaction summaries do
   mention HANDOFF.md (game repo 8–11 times, baton 4–6), because S's conversation shows the file being written.
4. **Version drift not in the write-up.** OMC changed from 5.8.4 to 5.8.7 during round 2: all five round-2 baton-repo
   handoff writes loaded 5.8.4, all five game-repo ones 5.8.7. The install now has OMC 5.8.7, baton 1.0.0 and Claude
   Code 2.1.331.
5. **Fact tags at the round-3 start states** (computed 2026-11-25 by the runner, `startstate`, regexes for the rule
   statements in the specs):
   - baton (B1): **F1 conversation-only** (no file has a dotted date), **F3 conversation-only**, F4 and F5 also in the
     repo (the target's docstring says stdlib only and states the Usage rule; a test checks it).
   - game repo (B1′): **F1 conversation-only**; F3's marker hits one unrelated document that tells code in another
     area not to touch the same directory (not the rule for this tool); F4 and F5 also in the repo (the target's header
     and its option table).
   - All five round-2 handoffs per repo carry markers for F1, F3, F4 and F5 in both repos.

## Design overview

| phase | what | spend |
|---|---|---|
| 0 | Re-analysis of the planned task (T1) under next-day cost lines, using round-1 C and round-2 H records | $0 |
| 1 | Offline preflight: grader self-tests, trigger check, version checks, shas, backups, fact tags | $0 |
| 2 | One probe of the truncated-fork path (prompt `OK라고만 답해`, `--max-turns 1`, `--max-budget-usd 1`) | ≈ $0.5 |
| 3 | Pilot per repo: Z1, then the first C/H pair, then the gate | ≈ $9 |
| 4 | Main block: different task (T2), C and H, n = 5 per arm per repo (pilot pair included), or fewer by the gate | ≈ $27 |

**Why T1 needs no new runs.** Under next-day conditions both arms on T1 follow the protocol already run; only cache
state and calendar date differ. H's next task (round 2) was already a new session starting almost cold (first-turn
cache creation 27–43k; only the shared system prefix came from cache). C's next task (round 1) resumed a compacted
session and wrote its context to cache on the first turn (47–65k). Cache state changes cost, not model output, so
Phase 0 reprices costs and keeps the grades. Rerunning T1 would buy only concurrency, for about $50.

## Scenario and arms

Day 1 ends at the switch point of the existing long session S (baton 238,733 tokens; game repo 216,713 tokens), which
is not rebuilt. Day 2 is any time after S's 1-hour cache expired, which happened long ago.

- **C, compact.** Day 2: resume S, `/compact`, then the task prompt in the compacted session.
  - Carrier: round 1's compaction C_i (i = 1–5 per repo) through a truncated fork:
    `claude -p "<T2 prompt>" --resume C_i --resume-session-at <cut> --resume-drops-turn <T1 prompt uuid> --fork-session`.
    `<cut>` is the parentUuid of the first real user prompt after the compact boundary, which was round 1's
    "이어서 해줘" (the runner checks that text). Computed for all ten C_i on 2026-11-25.
    (`--resume-drops-turn` was dropped after the probe, before any main run; see Deviation 1.)
  - Cache state does not change what /compact outputs, so a day-2 compaction has the same distribution as round 1's.
    Its cost comes from round 1's records (see Cost lines). T1 and T2 are paired per compaction instance.
  - **Fallback if the probe fails:** compact afresh on day 2 (`/compact --resume S --fork-session`, cold, about $1.15
    each; runner `transitions --arm C --fresh`), forked again for the task so the carrier stays unchanged, and **n = 4**.
- **H, handoff.** Written on day 1 at the boundary: round 2's handoffs H_i as they are. Day 2: a new session gets the
  task prompt. The write is not repeated (a cold day-2 rewrite costs $2.3–2.5 each and adds nothing; output does not
  depend on cache). T1 and T2 are paired per handoff instance.
- **Z, no carrier (pilot only, outside the verdict).** A new session on the clean start state with no HANDOFF.md gets
  the same prompt. If Z passes the hard checks, T2 does not need what the conversation carried. One run per repo.
- **N (resume without compacting): excluded** by the owner.

## Start state per repo

- **baton:** B1 unchanged. For H, the handoff is written as an untracked HANDOFF.md before the session starts. It is
  the full file the round-2 patch creates (byte-identical to applying the patch, as round 2 did); its sha256 is stored
  and checked before every call.
- **Game repo:** a new switch point **B1′**: a commit with B1's parent, message, author and committer, and B1's tree
  minus HANDOFF.md (B1 itself is kept; B1′ is referenced as `refs/exp/start`). For H, each round-2 patch is applied to
  B1 outside the snapshot, and the resulting full HANDOFF.md is stored with its sha256 and written untracked on B1′.
  Known cost: S's conversation shows that file being written, and the compaction summaries mention it, so a C session
  may look for it and not find it. Reads of HANDOFF.md are recorded per run (threat 3).

## Tasks

### T1, the planned step 4 (re-analysis only)

The original step-4 task, prompt "이어서 해줘", graded with the original hidden checks, kept at $0 through Phase 0.

### T2, a different, unplanned task

Requirements: it is not step 4 and nobody planned it; it needs facts only the conversation carried; it is graded by
scripted hidden checks. F2 and F6 are step-4 facts and cannot carry over. Carried facts: F1 (a fact about the values a
user types), F3 (do-not-touch paths), and F4/F5 (also in the repo, so weak tests of a carrier).

**Prompt, baton (verbatim; same frame in the game repo):**

> 지난번 작업에 이어서 할 건데, 오늘은 계획했던 4단계(날짜 필터)는 미루고 다른 걸 먼저 하자. lib/handoff_stats.py에
> `--by-date` 옵션을 추가해 줘. 날짜가 있는 절마다 한 줄씩, 최신 날짜가 위로 오게 `YYYY-MM-DD open=A done=B` 형식으로
> 출력한다(날짜는 이 형식으로 맞춰서 찍는다). 날짜 없는 절은 뺀다. 날짜 있는 절이 하나도 없으면 `baton: no dated sections`를
> 출력하고 종료 코드 0으로 끝낸다. 나중에 주입 훅에서도 쓸 수 있게 목록을 돌려주는 함수로도 꺼내 줘. 테스트를 추가해서
> 돌리고, 통과하면 커밋해 줘('handoff_stats: by-date'). 지난번에 정한 규칙은 그대로 지키고, 4단계는 아직 하지 마.

(The spec stores it as one line. "지난번" ("last time") is used instead of "어제", because S is several days old.)

- baton: F1 = headings may use `2026.11.20` (conversation-only; the repo's existing date regexes accept only dashes, so
  reusing them misses F1). F3 = hooks/ and lib/rules.py must not be modified; "주입 훅에서도 쓸 수 있게" is a mild pull
  toward hooks/.
- **Game repo, `--before <value>`** (exact wording only in the private spec, same frame): count only decision entries
  dated strictly before the value; "the value's forms and meaning are the same as we agreed for the planned filter"
  (the agreed forms include F1, a month value meaning its 1st day); an exact message for an empty result; pull the date
  interpretation out as a function "so the game code can use it later" (a mild pull toward the do-not-touch paths, F3).
  This T2 is closer to step 4 than baton's.

The installed baton 1.0.0's own trigger rule matches both prompts ("이어서"; the baton prompt also matches "handoff"
inside the file name), checked by the preflight.

**Hidden checks** (outside the snapshot, run on the final working tree, blind to arm by construction):

| check | baton T2 | game repo T2 |
|---|---|---|
| core2 | Fixture with dashed dates out of order, a dateless section and a fenced `## ` line: the lines that report counts are exactly the expected three, newest first, per-section counts; a fixture with no dated section prints `baton: no dated sections`, exit 0, and no count line | A day value gives the expected counts and summary (strict bound, dateless dropped); a no-match value prints the exact empty message, exit 0 |
| F1 | A fixture mixing dotted and dashed headings: dotted dates are recognized and printed with dashes (order-insensitive, so ordering stays core2's job) | A month value counts only entries before its 1st day |
| F3 | forbid_touch `^hooks/`, `^lib/rules\.py$` | forbid_touch the round-1 F3 paths |
| F4 | as round 1 (no dateutil/arrow/pendulum import, no pip install executed, no requirements/pyproject/setup change) | as round 1 (no new package import, manifest and lock unchanged, no install executed) |
| F5 | module docstring `Usage` block names `--by-date` | `--help` exits 0 and names `--before` |

- **correct** (binary) = core2 ∧ F1 ∧ F3 ∧ F4 in both repos. **score** = passed checks / 5. F1 takes F2's role in T1.
- Known weakness, game repo F1: comparing date strings lexically, or a lenient date parser, also gets the month case
  right. So F1 there separates "accepts the month form" from "rejects it as not a date", not "knows the rule" from
  "guessed". Z measures how often a session gets it without a carrier.
- **Diagnostics, not inputs:** step-4 flag in the diff (`--min-date` / the game's step-4 flag), `--since` added, own
  tests pass, files and commits changed, reads of HANDOFF.md, injection seen, Stop-hook blocks, any `compact_boundary`
  in the task, and the existing summary line still working.
- **Grader self-test (passed 2026-11-25, $0, rerun by every preflight):** a reference implementation written outside
  the snapshot passes every hidden check; one mutant per check fails exactly that check (baton: wrong order; dash-only
  dates; Usage without `--by-date`. Game repo: dateless entries kept; month value rejected; help without `--before`);
  synthetic diffs or commands fail exactly F3 (each forbidden path) or F4 (an import; an executed install). Against the
  unmodified start state both hidden scripts give core2 = F1 = F5 = false and the existing summary line true.
  Any later grader fix is applied to all runs from saved diffs and tool calls, and logged.

## Run protocol and guards (unchanged from rounds 1–2 unless marked new)

- One snapshot path per repo, one session at a time (new: a file lock refuses a second runner). Before and after every
  call: kill leftover processes, `git reset --hard` to the start state, clean untracked files, remove `.omc/`, move the
  auto-memory folder out and record the file count, restore `.git/config` after every next-task session.
- Every call: `--output-format stream-json --verbose --include-hook-events`, `BATON_OBSERVE=off`, stdin closed, the
  owner's unchanged global setup, `--max-turns 30` (probe 1), `--max-budget-usd 4` (probe 1).
- **Parent-transcript guard (new):** S and every reused C_i transcript keep size, mtime and sha256 across every call;
  the C_i transcripts were copied into the data folder with their sha256 at seed time. Any change stops the run.
- **Version guard (extended):** `CVH_BATON=1.0.0`, new `CVH_OMC=5.8.7` and `CVH_CLI=2.1.331`, checked on every init
  line, and by the $0 preflight against the installed plugin records and `claude --version`. Any mismatch stops; nothing
  is updated during the run.
- **Per-run cut checks for C (new):** a new session id; neither the T1 prompt's entry nor the T1 prompt text after the
  boundary in the fork; first-turn input within ±10% of the round-1 T1 first turn; parent unchanged. A failed check
  makes the run invalid.
- **Budget:** `CVH_DATA=~/.cache/baton/experiments/next-day`, `CVH_SNAPS=<round-1 snapshots>`, `CVH_PROBE_USD=0`,
  `CVH_CAP_USD=40`. The runner refuses a call when spent + its cap + $0.50 > $40; unknown spend is charged at the cap;
  a ledger is kept. Reused carriers are not charged again; their recorded costs enter only the cost lines.
- **Stops:** two consecutive invalid runs; a rate limit that persists after backoff (2 min, 15 min, or one wait for a
  stated reset time capped at 5.5 h); a hidden-test crash; cleanup failing 5 times; a version mismatch; a
  parent-transcript change.
- **Order:** per repo, Z1, then C and H in the order C H H C C H H C C H (baton) or its mirror (game repo); the first
  C and first H are the pilot pair. Baton runs before the game repo in each block.
- **Exploratory one-reply follow-up** (outside the verdict): a run that leaves the target untouched gets
  "알아서 판단해서 진행해줘" once and is graded again on the cumulative diff. Follow-ups run after all primary runs.

## Cost lines (pre-registered)

Fitted prices, unchanged: input $3.96, 1-hour cache write $8.00, cache read $0.201, output $19.95 per MTok.

- **next_cold** = the day-2 session's Δcost + its first turn's cache reads × (8.00 − 0.201) per MTok (every arm's first
  turn fully cold; about $0.1 conservative against H, whose back-to-back new sessions read 25–29k from cache on their
  first turn against C's 12–14k).
- **compact_morning** = the compaction's Δcost + its cache reads × (3.96 − 0.201) per MTok (nothing warm).
- **compact_evening** = round 1's warm-normalized compaction (`warm_cost`).
- **handoff_evening** = round 2's warm-normalized write (`warm_cost`).

| line | C | H |
|---|---|---|
| **Morning** (C compacts on day 2, the scenario as specified) | compact_morning + next_cold | handoff_evening + next_cold |
| **Evening** (C compacts at the boundary, like H's write; the strongest C) | compact_evening + next_cold | handoff_evening + next_cold |

A **raw** line (recorded transition cost + raw next-task cost) is reported as a sensitivity check.

## Metrics per run

Correctness and score; Δcost; Δ`modelUsage` with uncached input, cache creation, cache read and output separate;
first-turn context and cache read; `num_turns`; wall time; injection seen and its size; Stop-hook blocks; versions
from the init line; the C cut checks; the T2 diagnostics; the start state's fact tags.

## Decision rule (same form as rounds 1–2)

Valid runs only. **Invalid** = a harness failure: no result line, a rate limit, a C fork whose cut checks fail, or an
H run whose stored HANDOFF.md sha does not match before the call. `error_max_turns` is valid and graded.

For each task (T1 from Phase 0, T2 from Phase 4) and each cost line (morning, evening): N = valid runs per arm (the
smaller arm), k_C and k_H = correct counts pooled over repos, r = median over repos of (median cost H / median cost C),
a = max(1, round(N/15)), b = ceil(0.2·N).

- **Handoff better:** (k_H ≥ k_C − a and r ≤ 0.85, with H cheaper in every repo but at most one), or
  (k_H − k_C ≥ b and r ≤ 1.10).
- **Compact better:** the mirror image.
- **Trade-off:** correctness differs by ≥ b one way while cost differs by > 10% the other way.
- **No difference detected:** anything else.
- **Inconclusive:** fewer than 2 repos with ≥ 3 valid pairs each.

Correctness is the same under both lines; only r changes. If the morning and evening verdicts agree, that is the
result for the task. If they differ, the result names the condition, for example "handoff better than compacting the
next morning; compact better if you compact at the end of the day". T1 and T2 are reported separately. Phase 0 is
labeled a re-analysis and printed with the game-repo flag (its C runs had the build-written handoff injected); its
baton-only numbers are descriptive. Z is descriptive. Median and range of score, tokens by kind, cost and turns are
reported per arm and repo whatever the verdict.

**Disclosure.** While budgeting, the drafter worked out Phase 0's likely T1 values from medians: morning H/C ≈ 1.13
(baton) and 0.82 (game repo), median ≈ 0.97 ("no difference detected"); evening ≈ 1.75 and 1.13 ("compact better").
Phase 0 is therefore not blind. The cost lines were defined from first principles, not tuned to these values. T2 was
designed after seeing which facts both carriers kept in T1, and chosen to need conversation-only facts, not to favour
an arm.

## Pilot gate and run counts

In each repo, Z1 and the first C/H pair run first (`next --pilot`). Then `gate` ($0), over both repos:

1. **Z1 correct** in a repo: T2 there does not need the carriers. Revise that repo's T2 once (prompt, fixture or
   temptation) and rerun Z only; the old C1/H1 runs stay as exploratory and excluded; the revision is logged as a
   deviation before the main block. If Z still passes after one revision, that repo's T2 correctness is reported as
   carrier-insensitive next to the verdict.
2. **Both C1 and H1 fail core2** in a repo: a task or grader defect. Fix the grader (regrade all runs) or revise the
   prompt once, and log it.
3. **Run counts:** n is the largest of 5, 4, 3 (under the probe fallback: 4, 3) for which the remaining main-block
   runs, priced at the measured median next-task cost per arm and repo + 10% and simulated in run order against the
   runtime guard (spent + $4 + $0.50 ≤ $40 before each call), would all be allowed. Below 3: stop, inconclusive.

## Budget

Estimates from round 1/2 medians, with T1 next-task costs standing in for T2. Raw spend; reused carriers cost $0 now.

| phase | runs | estimate |
|---|---|---|
| 0 re-analysis, 1 preflight | — | $0 |
| 2 truncated-fork probe | 1 | ≈ $0.5 (≈ 60k first-turn cache write) |
| 3 Z pilot | 1 per repo | ≈ $3.0 |
| 4 C on T2 | 5 per repo | ≈ $15 |
| 4 H on T2 | 5 per repo | ≈ $17.5 |
| exploratory follow-ups | 0–2 | $0–5 |
| **total** | | **≈ $36; plausible $29–48** |

The hard stop is $40, so n = 4 per arm per repo is a likely outcome of the gate. Under the fallback (fresh
compactions, n = 4) the total is ≈ $38.7.

## Known threats (stated before results)

1. **Carriers are reused, not concurrent.** The compactions ran on 11-23/24 under CLI 2.1.330 and OMC 5.8.4 (baton
   has no compaction hook). The handoffs ran on 11-24 under CLI 2.1.331, OMC 5.8.4 (baton repo) or 5.8.7 (game repo),
   and baton beta.5 (skill identical to 1.0.0). All T2 sessions run under one version set. Reused outputs do not
   depend on cache; their costs come from records.
2. **The truncated fork is an undocumented path.** A real morning resume of a compacted session could attach
   different context. The probe and the per-run cut checks verify structure, not equivalence.
3. **B1′ removes a handoff the build session wrote.** The summaries mention that file, so a C session may search for
   it. B1′ is also why round 3's game-repo C differs from rounds 1–2.
4. **T2's carrier dependence is narrow.** Only F1 and F3 are conversation-only; F4/F5 are in the repo; F2/F6 do not
   apply. The game repo's F1 is passable by lenient date handling (see Hidden checks). Z tests this. In the game repo
   T2 is adjacent to step 4, so sessions may build step 4 too (a diagnostic).
5. **The prompt contains a trigger word.** Without it baton's on-demand design injects nothing; that case is not
   measured.
6. **"Next day" means an expired cache only**, not overnight repo changes or different phrasing. The system-prompt
   date moves several days past S's timestamps.
7. **The cost lines are models.** The raw line is reported. Fully-cold normalization of the first turn is
   conservative toward H.
8. **Carried over from rounds 1–2:** scripted S with salient planted facts; one model (opus 5.5); the owner's plugin
   setup (OMC hooks around compaction; the baton 1.0.0 Stop hook can block once in either arm; blocks are counted);
   small n ("no difference" means not detected at this n); costs are Claude Code's client-side estimates.

---

# Part 2. W: re-measure the handoff write with the new handoff skill

## Question

Round 2's handoff arm lost on cost mainly because writing the handoff took about six assistant calls over the full
~220–240k context (warm-normalized $0.65–0.73 per repo against $0.26–0.32 for a compaction). A new handoff skill
(uncommitted on the author's branch `split-econ` at the time of writing) asks for one combined status call, no manual
checker run when the save hook already reported, no `git log` after the commit, and a fixed two-line ending. Does it
make the write cheaper **without losing any fact the round-2 handoffs carried**?

## Design

- **What runs:** only the H transition of rounds 1–2: `claude -p "핸드오프 작성해줘" --resume S --fork-session
  --max-turns 15 --max-budget-usd 3`, in the same snapshot at the same switch point **B1** (the game repo too: W
  repeats round 2's write exactly, so it starts from B1 with its build-written HANDOFF.md, as round 2 did), 5 runs per
  repo, **alternating repos** (W1 baton, W1 game, W2 baton, …) so a budget stop leaves the repos balanced. No next
  tasks.
- **Which build:** the plugin tree on that branch, staged by `wstage` into the W data folder: the files git knows there
  (tracked plus untracked-not-ignored, minus deleted; the list `tools/stage-plugin.sh` uses), read with
  `git --no-optional-locks` so the source tree is not written. A manifest records the source commit, the uncommitted
  file list, the plugin version string, the skill's sha256 and a tree hash (`__pycache__` ignored). **The build is
  frozen at the first W run:** restaging is refused once any W run exists, and every run re-checks the tree hash.
  The build differs from the installed 1.0.0 in the skill and also in two hooks (the save-time checker and the split
  notice) and lib scripts the skill calls, so W measures the new build's handoff write, not the skill text alone.
- **How it loads without touching the install:** every W call adds `--plugin-dir <staged folder>` and `--settings
  <file>` whose only content is `{"enabledPlugins": {"baton@baton": false}}`. Nothing is written to the owner's
  settings, plugin records or installed plugin files, and other sessions keep the installed 1.0.0.
- **Guards (in addition to Part 1's snapshot hygiene, S guard, memory moves, ledger, backoff and two-invalid stop):**
  each init line must list exactly one baton plugin, loaded from the staged folder and not as `baton@baton`, with
  `CVH_BATON=1.0.0` (the staged version string equals the installed one, so the path is the guard), OMC 5.8.7 and CLI
  2.1.331; any tool call that names the installed baton's cache folder makes the run invalid and stops W.
- **Probe (before W, ≈ $0.6, W ledger):** two new one-word sessions in the baton snapshot at B1 (`OK라고만 답해`,
  `--max-turns 1`): a control with the installed setup and one with the staged build. Pass requires all of: the staged
  session lists exactly one baton, from the staged folder; the control lists `baton@baton`; the same plugin names; the
  same baton skills; the same hook counts per hook event (no doubled or missing baton hook); the staged version string
  equals the manifest's; and the owner's settings file, plugin records and installed baton files are byte-identical
  before and after. If it fails, W does not run.
- **Budget:** `CVH_DATA=~/.cache/baton/experiments/write-cost`, `CVH_CAP_USD=15`, probes included. Round 2's ten writes
  cost $15.44 raw because 5 of 10 first turns missed the cache (≈ $1.8 each to rewrite ~230k tokens). With the guard
  (spent + $3 + $0.50 ≤ $15) W may stop after 8–9 runs if as many first turns are cold; the verdict uses the valid runs.

## Comparison (pre-stated)

Per repo, round 2's five transitions against W's valid runs:
- **assistant calls** (main-thread API messages; round 2: 6 (5–7) baton, 6 (6–7) game repo);
- **warm-normalized write cost** (`warm_cost`: Δcost minus the first turn's cache creation repriced as cache reads,
  as in rounds 1–2; round 2: baton $0.726 ($0.647–0.831), game repo $0.653 ($0.641–0.732));
- **raw cost** (round 2: baton $0.831 ($0.726–2.45), game repo $2.27 ($0.682–2.30)), descriptive;
- **fact markers** in each new HANDOFF.md: F1, F2, F4, F6 with round 1's markers, plus F3 (both do-not-touch paths
  named) and F5 (the help/Usage rule). All ten round-2 handoffs contain all six, so the required set is all six in
  both repos.

## Decision rule (pre-stated, before any W run)

Valid W runs only (invalid: no result line, a rate limit, an error result, no HANDOFF.md in the diff, a wrong build
loaded, or a tool call into the installed build). Each repo needs ≥ 3 valid W runs, else **inconclusive**.
- **Cheaper:** the median warm-normalized write cost is lower than round 2's in **both** repos, **and** at most one
  valid W handoff misses any required marker (≥ 9/10 at full n).
- **Loses facts:** more than one valid W handoff misses a required marker.
- **Not cheaper:** facts kept, but the median is not lower in both repos.

Assistant calls and raw cost are reported per repo whatever the verdict. W says nothing about next-task correctness.

## Known threats (W)

1. **Not concurrent with round 2.** OMC was 5.8.4 for round 2's baton-repo writes and 5.8.7 for the game repo's; W
   runs 5.8.7 in both. CLI 2.1.331 in both rounds.
2. **Different loading path.** The staged build is loaded with `--plugin-dir` (another source label and plugin root);
   the probe checks hooks and skills match the installed layout.
3. **The build is a snapshot of work in progress**, frozen at stage time; its manifest identifies it.
4. **Cache state** changes raw cost a lot (≈ $1.8 per cold first turn); the verdict uses warm-normalized cost, as
   round 2's published comparison did.
5. Markers are regexes: present ≠ correct. n = 5 per repo.

---

## Probe results (2026-11-25, before any main run)

Probe spend: **$1.41 of the $2.00 allowed** (round-3 ledger $0.40, W ledger $1.01), counted inside each cap.

**Truncated fork (round 3, baton C5, `OK라고만 답해`, `--max-turns 1`).**
- Attempt 1, as pre-registered with `--resume-drops-turn`: the CLI refused the resume before any API call ($0):
  "range contains a non-furniture attachment … async_hook_response". The discarded range is round 1's T1 turn, and its
  asynchronous PostToolUse hook replies (`{"continue":true}`) are not counted as part of that turn by the CLI.
- Attempt 2, `--resume-session-at` only (Deviation 1): **passed**. Reply "OK"; a new session id; the C5 transcript kept
  its size, mtime and sha256; no T1 entry in the fork; first turn 64,089 tokens (cache creation 50,179, read 13,908)
  against 63,615 in round 1's T1 first turn (+0.7%). Cost $0.404.
- **Parent rule: `t1`.** The child's cumulative usage includes round 1's whole T1 next task, not only the compaction:
  child minus round 1's T1 total equals the probe's own input exactly (64,089 tokens). So every C run is charged
  child − round-1 T1 total, and each C run is also checked for a delta at least 95% of its own main-thread input.
- One probe covers both repos (as pre-registered); each C run still gets its own cut checks.

**Plugin load for W (two one-word sessions in the baton snapshot at B1).**
- Attempt 1 passed every check ($0.607), but both sessions also loaded a session-only plugin that the launching
  terminal injects through `CLAUDE_CODE_PLUGIN_DIRS`, which no round-1/2 run had (Deviation 2). Attempt 2 without it
  ($0.403) **passed every check**:
  - staged session: exactly one baton, `baton@inline` from the staged folder, version string 1.0.0; control: `baton@baton` 1.0.0;
  - the same plugin names otherwise (OMC 5.8.7, the UI plugin, the synced plugin, builtins) and CLI 2.1.331;
  - the same baton skills (`baton:baton`, `baton:baton-setup`, `baton:driftmap`);
  - the same hook counts per event (SessionStart:startup 7, UserPromptSubmit 4, Stop 7);
  - the owner's settings file, plugin records and installed baton 1.0.0 files byte-identical before and after.
- The staged build's `hooks/hooks.json` is byte-identical to the installed 1.0.0's. `write` refuses to run if a
  restaged build's `hooks.json` differs from the probed one (then the probe is rerun first, inside W's cap).

## Deviations before any main run (2026-11-25)

1. **`--resume-drops-turn` dropped; the runner checks the discarded range itself.** For each C_i the entries after
   the cut hold exactly one real user prompt, round 1's "이어서 해줘" (checked for all ten: 236–453 entries each,
   with T1's assistant turns, tool results, 11–26 asynchronous PostToolUse replies, and subagent message queue entries).
   A cut whose range holds any other prompt is refused. The rest of the carrier is unchanged.
2. **Child calls never inherit `CLAUDE_CODE_PLUGIN_DIRS`**, and any call that loads a session-only (`@inline`) plugin
   other than W's staged baton stops the run. Rounds 1–2 loaded none; the variable comes from the launching terminal,
   not from the owner's Claude Code setup. Nothing else in the environment is changed.
3. **Runner additions that change no rule:** an invalid run can be rerun with `--retry-invalid` (raw files and the
   failed record are kept); the probe result is shared by both repos' states; `write` is tied to the probed `hooks.json`;
   a `STOP` file in the data folder stops a runner cleanly before its next call; the gate's n, once decided, is kept
   when a stopped chain is resumed; Z runs get no exploratory follow-up (Z is a descriptive pilot control);
   `wstage --check` refuses W when the handoff worktree changed since staging, until W has started.

## Review amendments (2026-11-25, before any main run)

An independent review of the prepared runner returned NO-GO for both experiments. The amendments below were made
and committed before any main run; Deviation 4's first fresh compaction is the only paid call they needed.

4. **Game repo: fresh compactions on B1′, n = 4 (the pre-registered fallback, approved by the owner).** All five
   reused game-repo compactions carry, between the compact boundary and the cut, a `file` attachment of the
   build-written HANDOFF.md (byte-identical to B1's, with markers for F1, F3, F4 and F5): Claude Code re-attaches
   recently read files after a compaction. B1′ does not remove that copy. The baton repo's compactions carry only
   empty file references and are kept. For the game repo only, C1–C4 are compacted afresh on day 2 on **B1′**
   (`/compact --resume S --fork-session`, cold, about $1.15 each), the reused ones are kept under `reused` for the
   T1 re-analysis, and the task forks each fresh compaction (`--fork-session`, so the carrier stays unchanged).
   The runner refuses a fresh compaction that still re-attaches a file dropped from the start state, and the
   preflight fails any C carrier that has such an attachment (the five reused game-repo carriers fail it; the baton
   carriers pass). The first fresh compaction is checked before the others run (result appended below).
   The game repo therefore runs at most n = 4 pairs; the baton repo keeps up to 5. The four compactions cost about
   $4.6, inside the $40 cap.
5. **Valid runs as pre-registered.** The runner counted `error_max_turns` as invalid, contrary to the method. Valid =
   a result line whose subtype is `success` (and not an error), `error_max_turns` or `error_max_budget_usd`; such
   runs are graded and their cost recorded. Any other error result, a missing result line or a rate limit is
   invalid.
6. **Injection detector.** "Injection seen" matched baton's concept-index line too. It is now two fields:
   `inject_handoff` (the HANDOFF.md header, Korean or English) and `inject_concept` (concept index or section).
   An H run without `inject_handoff` is flagged in the report (not invalid: its HANDOFF.md is still in the tree).
7. **Rate limits restart from the clean start state.** A retry after a rate limit first resets the snapshot and puts
   the carrier back (the cut-off attempt may have edited files). An exploratory follow-up is not retried (it resumes
   a session the attempt already extended): it is recorded invalid and the runner stops.
8. **Ledger.** Before each paid call a pending row charges the call's cap; after it a correction row brings the
   charge to the reported delta. A killed call stays charged at its cap. When a run's delta fails the check that it
   covers at least 95% of the call's own main-thread input, the call is charged at its cap. That check now also
   applies to follow-ups, fresh compactions and W.
9. **W's fact check uses the lines each handoff write added.** In the game repo, B1 already held the build-written
   handoff with all six W markers, so a whole-file check could not fail. Required facts per repo = the markers found
   in the added lines of every round-2 patch there: **baton F1–F6, game repo F2 and F6**. Each W run's patch is
   checked the same way.
10. **W validity classes (no survivorship).** Only harness failures are invalid and rerun: no result line, an error
    result other than the turn or budget cap, a failed delta check, the wrong build loaded, a tool call into the
    installed build. A W run that hits `--max-budget-usd`, ends on the 15-turn cap or writes no HANDOFF.md is a
    **valid failure**: its cost enters the median and it counts as missing every required marker.
11. **Third carrier (diagnostic).** Per run, the runner lists tool calls (subagents included) to session search,
    memory, notepad or wiki tools, or touching the transcript folders or OMC's global state.
12. **Pins.** The CLI binary is resolved once to its versioned executable and checked with `--version` before a
    process's first paid call; children run with `DISABLE_AUTOUPDATER=1`. The model is pinned (`CVH_MODEL=claude-opus-5-5`,
    checked on every init line). **Effort is pinned to xhigh** (`--effort xhigh`, `CVH_EFFORT`): every round-1/2
    session's assistant entries record effort xhigh, while the 11-25 probe session (launched from this preparation
    session's environment) ran at high. The owner's settings file has a top-level `effortLevel` of **medium** and a
    per-model entry of high for opus 5.5; which of these, or the launching environment, set the probe's high was not
    determined. Each call's own assistant entries are checked; any other effort stops the run (corrected by
    Deviation 15). Child calls
    no longer inherit the launcher's session-identity variables (`CLAUDECODE`, `CLAUDE_CODE_SESSION_ID`,
    `CLAUDE_CODE_CHILD_SESSION`, `CLAUDE_CODE_ENTRYPOINT`, the attended, messaging, notes, exec-path and PID
    variables, `CLAUDE_EFFORT`); the names (not values) of the remaining `CLAUDE*`/`ANTHROPIC*` variables are
    recorded per call (today only the owner's settings-defined agent-teams flag).
13. **The "Z1 correct" revision is fixed now.** If a repo's Z1 passes every hard check, `gate --revised <repo>` applies
    the one allowed revision: Z1, C1 and H1 of that repo move to `excluded` (exploratory, never in the verdict), the
    pilot reruns Z1 only, and the pair joins the main block. The revision appends one sentence to the prompt that
    pulls toward the repo's existing date handling, which misses F1:
    - baton: "날짜 인식은 새로 만들지 말고 저장소에 이미 있는 날짜 정규식(lib/compiler.py나 lib/concepts.py)을 재사용해 줘."
      (those regexes accept dashes only);
    - game repo: a sentence asking to reuse the target's own day-only date rule (wording in the private spec).
    If Z1 passes again after the revision, the repo is reported carrier-insensitive and the run continues.
14. **Smaller fixes.** The main block interleaves the repos by pairs (baton pair, game pair, …) so a budget stop
    leaves them balanced; the gate simulates that order. run.sh holds one lock for its whole chain (gate, regrade,
    wstage and preflight included). The preflight reruns the hidden checks on the untouched start state (core2, F1,
    F5 false; the existing summary line true). Baton's F5 now looks only inside the docstring's Usage block (a
    self-test mutant mentions the flag elsewhere in the docstring and must fail). W's leak check also catches `~/` and
    `$HOME/` forms and subagent calls. Before W's first paid call (and before `wprobe`), the staged build's version
    must equal `CVH_BATON` and its skills must equal the probed ones.

Notes the review asked to state:
- **Game-repo F3 tag.** The stored start-state tag for the game repo's F3 is "also-in-repo", from one unrelated
  document that tells code in a different area not to touch the same directory. No file states the rule for this
  tool, so the analysis treats F3 as conversation-only and reports both.
- **core2 is strict.** Every output line that reports counts (`open=`) must be one of the expected lines, in order;
  a dateless, dotted or extra count line fails core2.
- **H sha mismatch.** If a stored HANDOFF.md's sha256 does not match before an H call, the runner stops before the
  call (nothing is run or charged); the run is not recorded as invalid.
- **Added threat (game repo H).** Round 2's game-repo handoffs are edits of the build-written HANDOFF.md (their
  patches modify it), so the game repo's H carrier also contains text the build session wrote. W's game fact check
  (Deviation 9) counts only what each write added.

### Status of the amendments (2026-11-25, before any main run)

- **Deviation 4's check is not done yet.** The first fresh game-repo compaction was not run in this preparation
  session (the session's permission policy refused the paid call). It is the first paid step of the round-3 chain:
  `preflight --before-fresh` (the five reused game carriers are listed as pending, not passed), then
  `transitions --arm C --fresh --n 4`, which stops right after any fresh compaction that still re-attaches
  HANDOFF.md, then the full preflight. If the first one re-attaches it, round 3 stops there and is reported.
- **W build restaged and frozen.** The handoff work was approved and frozen on 2026-11-25; W was restaged from it at
  03:22. The staged tree hash is `b0b45f8e4a3cf90bd5a83dbd250391a3b818652098ead6df8b527b058b7b2abf` (117 files; the
  1.0.0 commit plus 28 uncommitted files; skill sha256 `6546847b…`). `wstage --check` passes. Its `hooks/hooks.json`
  is byte-identical to the probed build's and the installed 1.0.0's, and its version string (1.0.0) and skills
  (baton:baton, baton:baton-setup, baton:driftmap) equal the probed ones, so the plugin-load probe stands.

## Re-review amendments (2026-11-25, before any main run)

15. **Effort checked before the first fresh compaction; external validity.** A compaction records no assistant entry,
    so its effort cannot be verified. Round 3's first paid step is therefore a one-turn probe (a new session in the
    baton snapshot, `OK라고만 답해`, the same call path with `--effort xhigh`, about $0.2) that must record
    `perTurnEffort == xhigh`, or the chain stops before any compaction (a resumed chain reuses a passed probe). The
    pin keeps rounds 1–3 and W comparable, but the owner's everyday effort is lower (the settings' top-level level is
    medium), so the results describe sessions at xhigh: an added threat to external validity.
16. **Round-1/2 data cannot be rewritten by mistake.** `gate` (including `--revised`) and `regrade` refuse to run
    unless `CVH_DATA` is set and every state has a round-3 start state (the default data folder is round 1's). The
    revision is started with `run.sh revise <repo>`, which applies it and continues the chain; the gate's message
    names that command.
17. **Smaller:** both run.sh pin `CVH_CLAUDE_BIN` to the versioned executable; a fresh compaction counts only with a
    compact boundary whose `pre_tokens` > 0 and a positive cost delta.

**Private game-repo files, as committed for round 3 (sha256):** T2 spec `0a981230423eb6f318de8350b061eb7403ef42a15c86000f0d492f9aef40d198`,
hidden checks `c98c97d130dc4f88d9e7aa2595efa99c93818b3dabd728c0bd564070aefa93ae`, reference implementation
`b322136d0ef41b6b7c03ce37d9e297508d5478505af9e22d0ef157c55684f92b`; T2 prompt (UTF-8)
`d9a8a13cfa6f816720fe8ec2132514af61b5f9790bc82cc47823320590c7b98b`, revised prompt
`da32029ae8797e052fdd6819481c3e9e2e7534a9f3a367f601ae23fa952a7f83`.

## Results (2026-11-25)

All main runs finished on 2026-11-25 (W 10:46–15:12, round 3 11:02–16:27 KST). Every call loaded Claude Code 2.1.331,
OMC 5.8.7, opus 5.5 and baton 1.0.0 (W: the staged build) by its init line. Every main-block, W, Z, pilot and
follow-up call, and the effort probe, ran at effort xhigh by its assistant entries; the five feasibility probes run
before effort was pinned ran at high (Deviation 12), and the four fresh compactions record no effort (Deviation 15). No run was invalid and no call was retried.
The Stop hook never blocked in W or in the 12 main-block runs. It blocked once in each of two runs outside the verdict
(the game repo's excluded pilot C1 and its revised Z1). Raw data stays in the two data folders.

### Deviation after a main run started

18. **W's cap, $15 → $27.** The $15 guard stopped W after nine runs, before the game repo's W5, as the pre-registration
    foresaw ("W may stop after 8–9 runs"). The owner raised the cap to $27 on 2026-11-25, and game W5 ran at 15:10,
    about four hours after the other nine. It is reported with them. Without it the game-repo median is $0.584 and the
    verdict is the same.

### W: the handoff write with 1.0.1's skill

**Verdict, by the pre-stated rule: cheaper.** The median warm-normalized write cost is lower than round 2's in both
repos (baton 0.92×, game repo 0.87×), and 9 of 10 W handoffs contain every required marker in the lines they added.

| repo | writes | assistant calls | cost, warm-normalized $ | cost, raw $ | HANDOFF.md size | required markers in the added lines |
|---|---|---|---|---|---|---|
| baton | round 2 (n = 5) | 6 (5–7) | 0.726 (0.647–0.831) | 0.831 (0.726–2.45) | 8.3 KB (7.3–8.7) | 5/5 (F1–F6) |
| baton | W (n = 5) | 5 (5–5) | 0.670 (0.575–0.718) | 0.670 (0.575–2.48) | 8.3 KB (8.2–10.6) | 5/5 (F1–F6) |
| game | round 2 (n = 5) | 6 (6–7) | 0.653 (0.641–0.732) | 2.27 (0.682–2.30) | 7.1 KB (7.0–7.2) | 5/5 (F2, F6) |
| game | W (n = 5) | 6 (5–8) | 0.570 (0.558–0.688) | 2.21 (0.558–2.23) | 6.8 KB (6.2–7.7) | 4/5 (F2, F6) |

Values are median (min–max). "Required markers" follows Deviation 9: baton F1–F6, game repo F2 and F6.

- **Which build.** The staged build (the 1.0.0 commit plus 28 uncommitted files, staged 2026-11-25 03:22) has skills,
  hooks and lib files (tests aside) byte-identical to the `v1.0.1` tag; only the version string differs (1.0.0). So W
  measured 1.0.1's handoff write.
- **The miss.** Game W5's added lines lack F6's marker (the exact empty-result message). The file still holds F6 from
  the build's handoff, which Deviation 9 does not count.
- **Raw cost** barely moved in the game repo because, as in round 2, most of its first turns missed the prompt cache
  (median first-turn cache write about 209k tokens in both rounds). The verdict uses warm-normalized cost, as
  pre-stated.
- **Third carrier (diagnostic).** Four game-repo W runs listed the snapshot's auto-memory folder with Bash; it was
  empty. No run called a session-search, memory, notepad or wiki tool.
- W says nothing about next-task correctness with these handoffs; no next task ran.
- Spend: **$13.99** of $27 (probes $1.01, writes $12.98).

### Round 3: the next day, a different task (T2)

**Verdicts, by the pre-registered rule (both repos, n = 3 pairs each):**
- **Morning line** (the handoff written at the boundary; /compact run the next morning): **no difference detected.**
  k_C = 5/6, k_H = 4/6, r = 0.863 (baton 0.869, game repo 0.856). H was cheaper in both repos, by 13% (baton) and 14%
  (game repo), short of the r ≤ 0.85 the rule asks for, at n = 3 pairs per repo.
- **Evening line** (both written at the boundary while the cache is warm, the strongest C): **compact better.**
  r = 1.325 (baton 1.483, game repo 1.166), so 1/r = 0.75, with C cheaper in both repos.
- **Raw line** (sensitivity): compact better, r = 1.529 (1.706, 1.353).

The two lines disagree, so the result names the condition: against compacting the next morning, the rule detected no
difference (H 13–14% cheaper, short of the 15% it needs, at n = 3); against compacting at the end of the day, /compact
was cheaper than writing the handoff.

**Pilot gate.** In the pilot, the no-carrier run Z1 passed every hard check in both repos, and so did both pilot pairs.
The pre-registered revision (Deviation 13) was applied to both repos, Z1 was rerun, and the six pilot runs moved to
`excluded`. **Two of the four Z runs were not clean no-carrier runs.** With Bash they opened the old long session's
transcript on disk (the folder under `~/.claude/projects/` for the snapshot path) and read the planted rule from it.
That is a third carrier; Deviation 11's diagnostic lists it (`third_carrier`), but the first draft of this report
missed it.
- Baton: the first Z1 read F1 from the transcript ("`2026-11-20`과 `2026.11.20` 두 형식 모두") and passed; that pass
  triggered the revision. The revised Z1 listed the transcript folder but did not read the rule, and failed F1 (dotted
  dates). So the revised T2 needs a carried fact there.
- Game repo: the first Z1 passed without opening the transcript (its auto-memory folder was empty). The revised Z1
  read F1 (a month value means its 1st day) from the transcript and passed. It used 30 turns by the CLI's count (28 main-thread messages); the Stop hook blocked
  it once, and it wrote HANDOFF.md before ending. By the pre-registered rule the repo is reported
  **carrier-insensitive**. The clean evidence for that is the first Z1, on the first prompt, together with the known
  weakness that lenient date handling passes the game repo's F1. Its correct counts say nothing about either
  carrier; its costs still count.
- None of the 12 main-block runs and not the follow-up opened a transcript folder (the same check finds the Z runs'
  calls).
- The gate then set n = 3 per repo from the budget ($17.05 spent, main block projected at $17.85).

| repo | arm | correct | score | cost, morning $ | cost, evening $ | cost, raw $ | next task alone, raw $ | next-task turns (main-thread messages) | next-task first-turn context |
|---|---|---|---|---|---|---|---|---|---|
| baton | C | 2/3 | 1.00 (0.40–1.00) | 2.19 (1.87–2.48) | 1.28 (0.97–1.57) | 2.03 (0.87–2.32) | 0.93 (0.58–1.20) | 10 (3–11) | 64.0k (62.7k–64.7k) |
| baton | H | 1/3 | 0.80 (0.80–1.00) | 1.90 (1.77–2.36) | 1.90 (1.77–2.36) | 3.46 (2.16–3.48) | 1.06 (1.01–1.40) | 11 (11–17) | 55.7k (55.4k–56.1k) |
| game | C | 3/3 | 1.00 (1.00–1.00) | 3.09 (2.61–3.16) | 2.27 (1.79–2.33) | 2.93 (2.45–3.00) | 1.81 (1.30–1.91) | 12 (7–14) | 71.6k (71.2k–72.9k) |
| game | H | 3/3 | 1.00 (1.00–1.00) | 2.65 (2.44–2.81) | 2.65 (2.44–2.81) | 3.97 (2.42–4.21) | 1.68 (1.67–1.94) | 14 (12–15) | 59.6k (59.5k–59.6k) |

Values are median (min–max) per run. Turns count main-thread assistant messages, as in rounds 1–2. (The runner's
report prints `num_turns` from the last result line instead, which undercounts two game-repo H runs whose background
tasks added result lines; their cost is the same on every result line.) The transitions inside these lines: a compaction the next morning cost $1.17
(baton) and $1.18 (game repo); a warm-normalized compaction $0.26 (baton, round 1's) and $0.35 (game repo, the fresh
ones of Deviation 4); a warm-normalized handoff write $0.65 in both repos (round 2's H1–H3).

**What the numbers say.**
- **The morning line turns on the compaction H skips.** Compacting the ~220–240k conversation with a cold cache cost
  about $1.17, against about $0.65 for the handoff write priced as if the cache were warm (warm-normalized; four of
  the six round-2 writes reused here actually started cold). When both happen at the boundary,
  the compaction ($0.26–0.35) is cheaper than the write.
- **The next task itself**: baton H $1.06 vs C $0.93 (H 13% more), game repo H $1.68 vs C $1.81 (H 7% less), at n = 3.
  H sessions started lighter (first turn 56–60k against 64–72k after compaction).

**Failure analysis (baton).** The revision asks the session to reuse the repo's existing date regex, which accepts
dashes only, while the carried rule F1 says headings may use dotted dates. The revised T2 therefore sets a new
instruction against a carried rule.
- **C1** noticed the conflict, changed nothing, and asked which instruction to follow, recommending a new date
  function. After one neutral reply it passed every check (exploratory, $0.82).
- **H1 and H3** followed the new instruction: they reused the dash-only regex, committed, and said in their final
  message that dotted dates are not recognized. Their handoffs state the rule ("날짜는 `2026-11-20`과 `2026.11.20` 둘
  다 받는다", in H1). The fact was carried, and the session settled the conflict in favour of the prompt. Neither
  stopped, so neither got a follow-up.
- C2, C3 and H2 handled dotted dates and passed.
- So the baton repo's one-run gap comes from how a session settled a conflict between the prompt and a carried rule,
  not from a lost fact, at n = 3. Correct within at most one reply (exploratory): baton C 3/3, H 1/3; game repo 3/3
  in both arms.

**Diagnostics.**
- The handoff was injected in every H run (6/6) and in no C run (0/6). The concept-map index went into every run.
- Two of the three game-repo C sessions tried to read HANDOFF.md, which B1′ does not have (threat 3).
- One game-repo H session also added the step-4 flag. It is graded on T2's checks only.
- No compact boundary and no Stop-hook block inside any main-block task, and every session's own tests passed.
- Z runs: two of four read the old transcript (see Pilot gate).

**T1 re-analysis (Phase 0, $0).** Over both repos: morning r = 0.981 (baton 1.121, game repo 0.841), no difference
detected; evening r = 1.449 (1.739, 1.159), compact better; raw r = 1.478, compact better; k_C = k_H = 10/10. These
use the game repo's round-1 C runs, which had the build-written handoff injected. Leaving that repo out, as the
rounds 1–2 correction does, leaves one repo, so the rule gives no verdict. Baton only, descriptive: H/C 1.12 on the
morning line, 1.74 on the evening line.

**Spend.** **$34.36** of $40: probes $0.72 (truncated fork $0.40, effort $0.31), four fresh game-repo compactions
$4.53, next tasks $28.30 (the 12 main-block runs $16.49; the Z and pilot runs $11.81), one follow-up $0.82.

**Threats, after the runs.**
1. **The H arm used round 2's handoffs**, written under beta.5, whose skill equals 1.0.0's, not 1.0.1's. W measured
   1.0.1's write separately; the two were not combined.
2. **The game repo's T2 is carrier-insensitive**, so correctness rests on the baton repo's three pairs. Its revised Z1
   was not a clean control (it read the old transcript).
3. **Small n**: three pairs per repo. "No difference detected" means not detected at this n.
4. **The old transcript is a carrier the protocol did not remove.** The long session's transcript stays on disk (every
   fork's parent), and a new session can find it. Only Z runs did here; a real next-day session could too.
5. Carried over: scripted sessions with salient planted facts, one model at effort xhigh (Deviation 15), the owner's
   plugin setup, and costs that are Claude Code's client-side estimates.
