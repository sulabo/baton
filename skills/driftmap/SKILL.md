---
name: ontology
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/lib/fresh.sh *) Bash(${CLAUDE_PLUGIN_ROOT}/lib/check.sh *) Bash(python3 ${CLAUDE_PLUGIN_ROOT}/lib/concepts.py *) Bash(python3 ${CLAUDE_PLUGIN_ROOT}/lib/candidates.py scan *)
description: Builds a concept-level graph of the project's knowledge and keeps it fresh. Checks where decisions, code and docs say different things, where there are two sources of truth, and where references are broken, then creates or updates CONCEPTS.md. The output is an LLM wiki that an AI can quote directly. Triggers on English requests such as "build a concept map", "map the concepts in this repo", "find where the docs and code disagree", "check this repo for drift", "concept graph", "is CONCEPTS.md still fresh", "show concept candidates", "alias candidates". Also triggers on Korean requests such as "개념 지도 만들어줘", "지식 정리해줘", "문서랑 코드 안 맞는 거 찾아줘", "온톨로지 점검", "개념 그래프", "신선도 점검", "개념 후보 보여줘", "별칭 후보".
---

# Ontology — concept graph and check-up

## Language

Reply in the user's language. Write CONCEPTS.md in the language of the existing file; if there is none, in the language the user writes in.

The scripts read CONCEPTS.md in both languages, whatever language they print in. A Korean map uses `- **메타**: 상태=… · 확인=… · 파일=… · 이웃=… · 문서=… · 별칭=…`; an English map uses `- **Meta**: status=… · checked=… · files=… · neighbors=… · docs=… · aliases=…`. Don't mix the two in one file. The scripts print in English or Korean depending on `BATON_LANG` (`ko`, `en`, `auto`) and then the system locale.

| Korean map | English map |
|---|---|
| `- **메타**:` | `- **Meta**:` |
| `상태=` · `확인=` · `파일=` · `이웃=` · `문서=` · `별칭=` | `status=` · `checked=` · `files=` · `neighbors=` · `docs=` · `aliases=` |
| `확인=미상` · `확인=YYYY-MM-DD(해시 미상)` | `checked=unknown` · `checked=YYYY-MM-DD(hash unknown)` |
| `파일=없음(규칙 개념)` · `이웃=없음` | `files=none(rule concept)` · `neighbors=none` |
| `이웃=개념 2(전제)` · `개념 3(정본)` | `neighbors=Concept 2(premise)` · `Concept 3(source of truth)` |
| References in prose: `개념 12`, `개념 1·3` | `Concept 12`, `Concept 1·3` |
| `DECISIONS.md` line `- 관련:` | `- Related:` |

## The two jobs of this skill

| Job | What | Output |
|---|---|---|
| **Check-up** | Find, per concept, where decisions, code and docs disagree | A list of mismatches and their kinds |
| **Graph** | Make concepts the nodes and the relations between them the edges, and **keep it fresh** | `CONCEPTS.md` = an LLM wiki the AI quotes directly |

Without the check-up the graph becomes a pretty lie. Without the graph the check-up starts from scratch every time.
They are two sides of one output (`CONCEPTS.md`) and are never built separately.

**Why this skill exists (read this).**
In one project a strategy guide was judged to state an old rule. Then the code was opened, and
**the doc was right.** The mismatch was not in the doc but **between the decision and the implementation** — the change had been decided
but was not in the code yet. **Comparing docs only with other docs mistakes "not built yet" for "stale doc".**
Every step of this skill is designed to prevent that mistake.

**The second reason: a map nobody maintains is worse than no map.**
In observations from 2026-08-31 to 09-06, hand-maintained relation maps (`PROJECT_INDEX.md`, `DOCMAP.md`)
were not opened once in a week. They failed not because they were wrong but **because nothing prompted anyone to open them**.
So the graph in this skill always meets three conditions.

1. **It lives in a file that is already read** — no new file. There is one `CONCEPTS.md`,
   linked from `AGENTS.md`, so it is read in every session.
2. **Keep hand-maintained edges to a minimum** — the only automatic relation is the shared-file relation,
   and it is never stored; it is recomputed when needed. Everything else is a human judgment, but
   the skill picks candidates and asks. Don't overstate this.
3. **Compute freshness from git, not from a feeling** — mode ④.

## Modes — five of them; decide which one first

Whether `CONCEPTS.md` exists settles most cases.

| Mode | When | What it does | Cost |
|---|---|---|---|
| **① First build** | There is no `CONCEPTS.md` | All of steps 1–6. Pick the concepts and fill the four faces and the edges | High |
| **② Check-up** | It exists, and you want to know its current state | Steps 3–5. **Don't touch any file**; write only in the report | Medium |
| **③ Update** | It exists, and something changed since | Steps 3–7. Refill only the concepts that need a re-check | Medium |
| **④ Freshness check** | Often. The default entry point | Looks only at git history and the decision log. Computes which concepts need a re-check, then stops | Almost none (except the first run) |
| **⑤ Candidate review** | It exists, and the user says "show candidates", "alias candidates", "new concept candidates" | Shows the alias and new-concept candidates found in the session logs and puts **only what a person picks** into the map | Low (a script) |

**"Almost none" does not apply to the first run.** An existing `CONCEPTS.md` has no metadata lines,
so every concept starts as `checked=unknown`. The first two or three runs are really mode ①.

**Mode ④ looks at both git history and `DECISIONS.md`.** Looking only at files misses the whole state of
"the code is the same but the decision changed" — that is, "not built yet". That is exactly why this skill exists.

**Mode ④ is the default entry point.** Run ④ first to pick the concepts that need a re-check. If there are none, stop there.
If there are some, take only those into ② or ③. Don't re-check all ten concepts every time.

**The difference between ② and ③ matters.** A check-up is a diagnosis; an update is the treatment.
"What is out of sync right now?" is ②. "Clean it up" is ③. If unsure, start with ②, report, then ask.

**Some signals mode ④ can't catch.** A person has to notice these and come in.

- The concept changed as a whole (the concept list itself has to be redone)
- Many docs were retired at once
- A big implementation finished at once
- Nobody has looked for a long time

## The shape of one concept

A concept is not a file. Things like "ending rule", "whether sync is on", "follower count" —
**things that span several docs and code files and can drift apart** — are concepts.

### The four faces

| Face | What it is | Where to find it |
|---|---|---|
| **Decided** | What the decision log says (binding) | `DECISIONS.md`, `AGENTS.md` |
| **Actual behavior** | Facts shown by the code, tests and real outputs | Source, test run output |
| **Described in** | The docs that describe this concept | README, specs, guides |
| **Mismatch** | Disagreements among the three above, and **their kind** | The comparison |

In a docs or content project (one without code), **the text of the real output counts as "actual behavior"**,
and the face is called `Actual text` instead.

In a Korean map the faces are `정해진 것` · `실제 동작` · `설명된 곳` · `어긋남` (and `실제 표기` for a docs project).

### The metadata line — where the graph and freshness sit

Put one line **right after the heading** of each concept section. It comes before the four faces.
The goal is that an agent gets the state with a single `grep -A2 '^## 3\.'`.

**Leave one blank line** between the heading line and this line (as existing docs already do).

```
- **Meta**: status=not built yet · checked=2026-09-07(`a1b2c3d`) · files=`src/game/levels.ts` · neighbors=Concept 2(premise) · docs=`ROADMAP.md`
```

The same line in a Korean map:

```
- **메타**: 상태=미구현 · 확인=2026-09-07(`a1b2c3d`) · 파일=`src/game/levels.ts` · 이웃=개념 2(전제) · 문서=`ROADMAP.md`
```

| Key (English · Korean) | Rule |
|---|---|
| `status` · `상태` | Pick only from the closed vocabulary below |
| `checked` · `확인` | The date this concept was last compared with the code and **the commit hash at that time**. The baseline for mode ④ |
| `files` · `파일` | **Only the evidence for the actual-behavior face.** Code, tests, the text of outputs. Paths from the repo root |
| `docs` · `문서` | Where it is described (README, specs, guides). Optional. If only these files moved since the check, the verdict is `needs a re-check — N doc commits` on its own. If the code moved too, `· N doc commits` is added after the code verdict |
| `neighbors` · `이웃` | Only premise and source-of-truth edges. Don't write shared files (they are computed). If none, `neighbors=none` |
| `aliases` · `별칭` | Optional. Other words people use for this concept (comma-separated). The context compiler (`lib/compiler.py`) picks the concept when a prompt uses one of these words. Add **only what a person picked in mode ⑤** |

**A file name alone is not a path.** Existing docs write about half of their evidence without a path, like `Builder.swift:13`,
and then `git log` returns 0 at the repo root.
Write paths from the repo root starting at step 3, where the evidence is written.

**Don't put instruction or decision files in `files` — this is what actually broke freshness.**
Files like `AGENTS.md`, `DECISIONS.md`, `CLAUDE.md`, `TODO.md` change almost daily.
If they are in the evidence list, **the concept keeps needing a re-check even when its real content hasn't moved.**

Measured on 2026-09-14 (a docs repo): of 6 re-checks over the last day, **4 were caused by `AGENTS.md` alone.**
Meanwhile the body files that held the real content were attached to 7 concepts and had 0 commits in 7 days.
**The signal came from the wrong place.** An alarm that rings every time is soon ignored, and that is how relation maps die.

Instruction and decision files are the source of the `Decided` face, not of `Actual behavior`. Changes on that side are checked
separately under "Did the decisions move?" below.

**Some concepts have no evidence left once those files are removed. They are not concepts to delete; they are a different kind of concept.**
Things like "data only flows from the ledger to the outputs" or "the process has steps 0–5" are **the rule itself**,
and no separate file holds that rule. Write such a concept like this.

```
- **Meta**: status=not built yet · checked=2026-09-14(`a1b2c3d`) · files=none(rule concept) · neighbors=…
```

(Korean map: `파일=없음(규칙 개념)`.)

A rule concept is not subject to file-based freshness. **It is tracked only by the decision-change check.**
In the 2026-09-14 measurement, 3 of 30 concepts in the docs repo were of this kind.

Before calling something a rule concept, ask once — **is there really no output that shows whether the rule is kept?**
If there is, listing that file is much better. Only when there is none is it a rule concept.

If `checked` has no commit hash, freshness can't be computed. **If you don't know it, don't leave it empty; write `checked=unknown`**
(`확인=미상`) and fill it in at the next update. Severity goes only in the summary table, not in the metadata line — in two places it would drift apart.

### Status — a closed vocabulary of eight words

Don't invent other words. In three projects, `해소됨`, `일치 확인`, `완료` and `종결` were used side by side,
and counting the same thing became impossible.

| English map | Korean map |
|---|---|
| `agrees` | `일치` |
| `not built yet` | `미구현` |
| `stale doc` | `낡은 문서` |
| `undecided` | `미결` |
| `two sources of truth` | `중복 정본` |
| `resolved(date)` | `해소됨(날짜)` |
| `retired(date)` | `폐기됨(날짜)` |
| `could not check` | `확인 못 함` |

When migrating an existing doc, map words like this.

| Word in use now | Where it goes |
|---|---|
| `일치 확인` · `1차 일치` ("agreement confirmed", "first-pass agreement") | `agrees` |
| `완료` · `종결` ("done", "closed") | `resolved(date)` |
| `주의` ("caution") | It means a judgment is needed, so `undecided` or `two sources of truth`, whichever fits the facts |
| `부분 해소` ("partly resolved") | Pick one main status and write the rest as sentences in the mismatch face |

**Don't make compound statuses.** A notation like `not built yet + two sources of truth` really exists;
write only the main status in the metadata line and the rest in the mismatch face.

**Unifying the vocabulary and changing the summary-table columns is a one-time migration, done only in mode ③.** Mode ② doesn't touch them.

## The four kinds of mismatch — the response depends on the name

| Kind | Meaning | Response |
|---|---|---|
| **not built yet** | Decided, but not in the code yet | **Don't fix the doc.** It would then describe behavior that doesn't exist. Limit it with "currently, …" and note what is planned |
| **stale doc** | The code changed, but the doc states the old fact | **Fix the doc** |
| **undecided** | Nothing has been decided at all | A sign that a decision is needed. Ask the owner |
| **two sources of truth** | The same concept has two sources of truth, and which one wins is not settled | Have someone decide which one wins |

**Verdict rule: when a doc differs from the latest decision, always check the code.**
Writing "doc error" without looking at the code misjudges "not built yet".

## Edges — three kinds, and both directions are required

| Kind | Meaning | Direction | Stored? |
|---|---|---|---|
| **premise** | B holds only if A exists | Yes (A→B) | **Written in the metadata line** |
| **source of truth** | A is the source of truth for B | Yes (A→B) | **Written in the metadata line** |
| **shared file** | They use the same file as evidence | No | **Not written.** Computed from the `files` entries each time |

(Korean map: `전제` · `정본` · `공유파일`.)

**Shared-file relations are not stored because they explode.** In one project a single doc was
the evidence for 9 concepts (the value re-measured from the 2026-09-14 file; the 14 cited at first was an error copied from a subagent report without checking the source). Linking every pair gives 36 edges, with 8 neighbors
stuck on each concept, and the one-line metadata rule collapses. With only the `files` entries, this is derived information that can be recomputed at any time,
so it is not stored. Not storing it also means there is no two-way consistency to keep and nothing to re-derive.

**Cross-project edges are not turned on yet.** Turn them on after enough `Related:` lines (`관련:`) have built up in `DECISIONS.md`
(4 in total as of 2026-09-14). Introduced now, they would be empty for most concepts.

**Both directions are required — this one rule turns prose into a graph.**
If concept A's `neighbors` has B, **B's `neighbors` must have A.**
A relation written on one side only is visible only when reading that side, so it is not a graph.

Measured on 2026-09-14 (a game project's `CONCEPTS.md`): 0 `[[links]]`, 10 mentions of "concept N" in prose,
and only one pair of them, concepts 6 and 12, went both ways. The rest were written on one side only.
The relations are not missing; **they are visible from one side only**.

When checking, report an edge that exists on one side only as a **broken edge**.

**Shared-file relations are not stored, but they are computed, because they prevent a failure that already hurt.**
In one project 3 mismatches were concentrated in one folder; the cause was a commit applying a decision that skipped
that folder. Not an individual mistake but a hole in the procedure. When fixing concept A, pick the concepts whose `files` entries overlap
on the spot and make a list of "look at these too".

## Steps

### 1. Survey the terrain

Read `DECISIONS.md` and `AGENTS.md` (or `CLAUDE.md`) first to see **what is binding**.
If the project already set rules for document status (for example, step 1 decision > step 2 code > step 3 reference docs),
**follow those rules as they are.** Don't make new rules.

Skim the doc list and the source structure. Don't read everything; focus on file names, type names and key constants.

### 2. Pick concepts — about ten

The criterion is not "is it a concept?" but **"would a mismatch actually cost a lot?"**
Split into 30 and it can't be maintained. Start from the costliest, 8–12 of them.

Good candidates: numbers repeated in several docs, on/off flags, core rules, structure definitions,
banned wording, attribution and source rules.

### 3. Fill the four faces

- **Don't write the actual-behavior face without `file:line` evidence.** If you couldn't check, write "could not check".
- **Don't estimate numbers; use run output.** Don't count tests; run them and take the number.
- After filling the faces, **fill in the metadata line.** For `files`, take only the file names from the evidence you just wrote.

### 4. Connect edges

1. **Compute shared-file relations (but don't store them).** Collect the `files` entries of all concepts and find files shared by two or more
   concepts. Use the result only as this task's list of "look at these together".
2. **Lift "concept N" mentions in prose into the metadata line.** Find sentences in the body that point to another concept
   and add them to `neighbors`. Judge the kind (premise / source of truth) from context; if unclear, ask.
3. **Read the `Related:` lines (`관련:`) of `DECISIONS.md` to see which decisions touched which concepts.**
   (Cross-project edges themselves stay off until the lines build up.)
4. **Make both directions match.** For premise and source-of-truth edges in the metadata lines that exist on one side only, write them on the other side too.

Looking at the `Related:` lines that actually built up, people write evidence doc paths well, but rarely concept numbers or
other projects. **Don't ask people to write more; derive the concept from the path** —
if a file that a `Related:` line points to is in some concept's `files` entry, that decision and that concept are connected.

### 5. Verify — no self-approval

**If you delegated research to a subagent, its report is unconfirmed until checked against the source.**
Confirm any item you are about to call a defect with `grep` or `Read` yourself before writing it.
Commands that return 0 because a path is wrong, and quotes that don't exist, can be mixed into a report.

**The scripts do the mechanical checks. Don't count by eye.**

The files are laid out like this. `concepts.py` is the only place that knows the `CONCEPTS.md` format;
if the format changes, only that file changes.

| File | What it does |
|---|---|
| `concepts.py` | `CONCEPTS.md` parser. Prints sections, summary table, metadata lines, references and evidence paths as tab-separated lines |
| `lib.sh` | Shared helpers. Repo root, whether a path is tracked, the four-way diagnosis of evidence paths |
| `check.sh` | Seven checks |
| `fresh.sh` | Freshness verdicts and decision changes |


```bash
${CLAUDE_PLUGIN_ROOT}/lib/check.sh <path to CONCEPTS.md>
```

It looks at seven things: whether summary-table rows and body sections match one to one, whether evidence paths have a form
that can be used to compute freshness, whether references between concepts go both ways, whether status words are inside the closed set, whether instruction or decision files are mixed into `files`, whether metadata lines exist, and whether the parser read the file to the end (no code fence left open).

Evidence-path findings come in four kinds — **incomplete path** (fix it to a path from the repo root),
**short name** (a shortened name like `main.md`; fix it to the real file name), **not tracked** (a nested repo),
**broken reference** (no file with that name). Each kind needs a different response, so don't lump them together.
(In Korean output: `경로 누락` · `약칭` · `미추적(중첩 저장소)` · `끊어진 참조`.)

**Don't confirm findings as defects as they are.** The script only compares mechanically and doesn't know meaning.
Items that need human judgment are written only after opening the source and checking.

### 6. Output

Create **`CONCEPTS.md` inside that project** (don't collect them centrally — knowledge that leaves the project
is not read in that project). **Commit it to git** — a map that isn't committed doesn't exist on another machine.

Structure:

1. **Header** — the date written, and a status statement ("if this differs from reality, reality is right")
2. **Summary table** — `| # | Concept | Status | Severity | One line |` (Korean: `| # | 개념 | 상태 | 심각도 | 한 줄 |`). Mismatches at the top, ordered by severity within them
3. **One section per concept** — the metadata line first, then the four faces
4. **Confirmed to agree** — with evidence. **This is an asset too.** If it already exists, don't delete it
5. **Retired concepts** — don't delete them
6. **Not checked** — don't hide them
7. **Maintenance rules**

Severity is `high` · `medium` · `low` (Korean: `높음` · `중간` · `낮음`).

An English skeleton:

```markdown
# Concept map — <project>

Written 2026-11-23. This map is a navigation anchor; where it differs from the code or the decisions, they are right.

## Summary

| # | Concept | Status | Severity | One line |
|---|---|---|---|---|
| 3 | levels | not built yet | high | the decision says 30 levels; the code has 12 |
| 9 | determinism | agrees | — | the same seed gives the same run |

## 3. levels — level list and order

- **Meta**: status=not built yet · checked=2026-09-07(`a1b2c3d`) · files=`src/game/levels.ts` · neighbors=Concept 9(premise) · docs=`ROADMAP.md`

- **Decided**: …
- **Actual behavior**: … (`src/game/levels.ts:12`)
- **Described in**: …
- **Mismatch**: …

## 9. determinism

- **Meta**: status=agrees · checked=2026-09-07(`a1b2c3d`) · files=`src/game/rng.ts` · neighbors=Concept 3(premise)

## Confirmed to agree

## Retired concepts

## Not checked

## Maintenance rules
```

The same skeleton in Korean:

```markdown
# 개념 지도 — <프로젝트>

작성 2026-11-23. 이 지도는 탐색 앵커다. 실제 코드·결정과 다르면 실제가 정답이다.

## 요약

| # | 개념 | 상태 | 심각도 | 한 줄 |
|---|---|---|---|---|
| 3 | 레벨 | 미구현 | 높음 | 결정은 30개, 코드는 12개 |
| 9 | 결정론 | 일치 | — | 같은 시드면 같은 판이 나온다 |

## 3. 레벨 — 레벨 목록과 순서

- **메타**: 상태=미구현 · 확인=2026-09-07(`a1b2c3d`) · 파일=`src/game/levels.ts` · 이웃=개념 9(전제) · 문서=`ROADMAP.md`

- **정해진 것**: …
- **실제 동작**: … (`src/game/levels.ts:12`)
- **설명된 곳**: …
- **어긋남**: …

## 9. 결정론

- **메타**: 상태=일치 · 확인=2026-09-07(`a1b2c3d`) · 파일=`src/game/rng.ts` · 이웃=개념 3(전제)

## 일치 확인된 것

## 폐기된 개념

## 확인하지 못한 것

## 유지 규칙
```

The parser reads `## N. title` as a concept section and ends it at the next numbered section or at any heading without a number,
so the closing sections (confirmed, retired, not checked, maintenance rules) must not have numbers.

**Match summary-table rows and body sections one to one.** A concept that was in the summary table with no body section
has really been found (docs repo #7 and #18). The file doesn't have to be at the root —
a meta-notes project keeps it at `docs/CONCEPTS.md`. Wherever it is, link to that path from `AGENTS.md`.

Then add **a one-line link** to the doc list in `AGENTS.md` (or `CLAUDE.md`).
It is found only if a file read in every session points to it.

This is how the map is read. baton's prompt hook adds a **concept index** once to a session's first human prompt (again after a compaction) —
one line per concept, `N. name — one line · files: first three files (+N)` (`파일:` in Korean output), at most 1,500 characters (`lib/concepts.py index`, turn it off with `BATON_CONCEPT_INDEX=off`).
The agent picks the concept that fits the task from that index and opens its files first (the index is a navigation anchor — check actual behavior in the code). So make names show what the concept is about,
and write **the first file of `files=` as the concept's entry point** (the file to open first). The one-line summary is only what follows ` — ` (a dash with spaces on both sides) in the concept heading (if there is none, only the name) — the summary table's `One line` column records how a mismatch went, so it is not read. To say in one line what a concept is about, add `— description` to its heading.
A concept whose status starts with the word `retired` (or `폐기됨`, `폐기`) is left out of the index, and home-directory absolute paths and `~/` paths are left out of its file list. See the current index with `python3 ${CLAUDE_PLUGIN_ROOT}/lib/concepts.py CONCEPTS.md index`.

### 7. Fixing — only after approval

**Don't fix things on your own.** Report them split by kind.

- **Closed by fixing** (stale docs, numbers) — fix after approval
- **Must ask the owner** (adding a decision to the log after the fact, marking a reversal) — the value of a decision record is not "what"
  but **"why, and what was rejected"**, and only the person who decided has that.
  **What is banned is not "writing it for them" but "filling it in by guessing".** If the owner gives the reason and the rejected alternatives,
  write it with the `/decision` skill. If those two are empty, don't write it
- **Needs a judgment** — lay out options and ask. Attach a recommendation, but don't push it

**Don't delete** resolved items; **mark them "resolved(date)"** (`해소됨(날짜)` in a Korean map).

## Mode ④ — freshness check

A map goes stale not "because it is old" but **"because the files it depends on moved"**. So it can be computed.

**There is a script. Use it instead of combining commands by hand.**

```bash
${CLAUDE_PLUGIN_ROOT}/lib/fresh.sh <path to CONCEPTS.md> [repo root]
```

It reads the metadata lines and gives a verdict per concept. There are nine verdicts: the six below plus three more — baseline outside the history, rule concept, and the doc verdicts. One line is added at the end of the table: `Summary: re-check N · fresh M · rule concepts K` (Korean output: `요약: 재확인 N · 신선 M · 규칙 개념 K`). The session-start notice reads this line.

| Verdict | Korean output | Meaning | Next action |
|---|---|---|---|
| `fresh` | `신선` | No commit to those files since the check | **Don't open it** |
| `needs a re-check — N commits` | `재확인 필요 — 커밋 N건` | The files moved | Look at that concept only |
| `needs a re-check — no baseline` | `재확인 필요 — 기준 없음` | `checked=unknown` | Fill it in this time |
| `needs a re-check — baseline lost` | `재확인 필요 — 기준 소실` | The commit with that hash is not in this repo. Seen when a commit of a squashed or rebased branch is viewed from a fresh clone | Set it again from the date |
| `needs a re-check — baseline outside the current history` | `재확인 필요 — 기준이 현재 이력 밖` | The commit exists but is not an ancestor of HEAD. An old commit left locally after a squash or rebase, a commit on another branch, a cherry-pick source | Set it again to a commit on the current branch. Left as is, there is no baseline to count later changes from |
| `needs a re-check — path gone` | `재확인 필요 — 경로 소실` | A file is missing (even if only some are) | It was moved or deleted. That itself is a mismatch. The commit that deleted or moved it is also counted in the commit count |
| `needs a re-check — not tracked` | `재확인 필요 — 미추적` | The file exists but this repo doesn't track it | A nested repo. Run it there separately |
| `rule concept — tracked only through decision changes` | `규칙 개념 — 결정 변동으로만 추적` | `files=none(rule concept)` | Look at it only through the decision-change check below. With no recorded hash, `(no baseline — docs not checked)` is added. A rule concept whose recorded commit is unknown does not trigger the notice — in a newly built map, rule concepts usually start as `checked=unknown`, and a notice would ring the same alert every session until it is ignored. It shows only in the `/drift` table. If the recorded hash is lost or outside the history, decision changes can't be counted either, and it goes up to `needs a re-check — baseline lost (rule concept)` |
| `needs a re-check — N doc commits` · `needs a re-check — N doc paths gone` | `재확인 필요 — 문서 커밋 N건` · `재확인 필요 — 문서 경로 소실 N개` | The code is the same, but files in the `docs` entry moved or disappeared | Look at the described-in face only (added 2026-11-21) |

With a count of 1, the English output uses the singular: `needs a re-check — 1 commit`, `1 doc commit`, `1 path gone`, `1 doc path gone`.

All six verdicts were reproduced once each in real repos on 2026-09-14 and checked.

`· a new decision points to it (Related)` can follow a verdict (Korean output: `· 새 결정이 '관련'으로 가리킴`). It means that after that concept's check hash,
a line newly added to `DECISIONS.md` has `Concept N` (also `Concept 5·12`) or `Concept "name"` after `Related:` (`개념 N` · `개념 "이름"` after `관련` in Korean). A `- Related:` inside a table cell is caught too.
A concept that was `fresh` goes up to a re-check, and **rule concepts (files=none) are caught this way too.**
If a name doesn't match any concept section heading, a number has no section, or the parser fails, it is listed separately below the table as "not 0, could not count".
Counts (`35 concepts` · `개념 35개`) and negations (`Concept 1 is unchanged` · `개념 1은 변경 없음`) are not counted as pointers.
**If the decision and the concept were changed in the same commit**, the metadata line can't record its own commit hash, so this mark remains. In the next commit, move `checked=` to that commit (the way game repo `d55226b` did) — the same rule as for file-commit verdicts.
Measured on 2026-09-30: in the game repo concept 8, and in the docs repo concept 31, both `fresh`, went up because a new decision pointed to them (all 7 checked against the source were real pointers).

### Did the decisions move? — checked separately from files

Since instruction and decision files were taken out of `files`, changes on that side are checked **once, globally**. Not per concept.

`fresh.sh` reports it below the table. There is no need to run it by hand.

**The `DECISIONS.md` format differs per project. Assuming one format silently gives 0.**
The script tells two formats apart.

| Format | What it looks like | How to connect it to concepts |
|---|---|---|
| Dated headings | `## 2026-09-06 — what was decided` + a `- Related:` line (`- 관련:`) | Derive from the files the `Related:` line points to |
| Table | `\| P22 \| decision name \| content \|` | Find the decision ID in the concept map and connect them |

If it is neither, it says **"Unknown format — not 0, could not count"** and stops. Open the file and check directly.

**Leave this check looking at only one format and it really bites.** On 2026-09-15, in the docs repo, looking only for dated headings
reported "1 new decision"; counted in the table format there were **22**, and **8 of them were not even mentioned in the concept
map.** The only path that catches "not built yet" was missing 21.

When there is a new decision, the concepts it touched **need a re-check even if no file moved.**

**This is the only path that catches "not built yet".** The state where the code is the same and only the decision moved is exactly "not built yet",
and file-based freshness never catches it. Drop this check because decision files were removed from `files`,
and the reason this skill exists is gone.

A new decision without a `Related:` line **doesn't say which concept it touched.** Report that as a hole in the update
path, and don't fill it in yourself.

**Skip steps 1 and 2 and this mode lies quietly.** `git log` gives empty output without an error for a path that doesn't exist
and for a path that isn't tracked. Then **the concept that most urgently needs a look appears the safest.**

Both were confirmed in the 2026-09-14 measurement. A path that didn't exist returned 0, and in the docs repo
`docsrepo/` is a separate repo (`docsrepo/.git`), so it is not tracked by the parent, yet **files inside it
were set as the evidence for concepts.** The files are there, so a path check alone passes.
The files that change most often in that project were about to be reported as "fresh" forever.

One table is enough for the report.

```
| # | Concept | Status | Commits since check | Verdict |
|---|---|---|---|---|
| 3 | skill tree | not built yet | 4 | needs a re-check |
| 9 | determinism | agrees | 0 | fresh |
```

In Korean:

```
| # | 개념 | 상태 | 확인 이후 커밋 | 판정 |
|---|---|---|---|---|
| 3 | 능력 나무 | 미구현 | 4건 | 재확인 필요 |
| 9 | 결정론 | 일치 | 0건 | 신선 |
```

**Stop here if you can.** If nothing needs a re-check, that is the complete report.
If something does, take only those concepts into mode ② or ③.

In a docs or content project with no git history, use file modification times (`ls -l`) instead,
and **write "based on modification times, not hashes" in the report.**

## Mode ⑤ — candidate review (spec section 21: observe → candidates → verify → a person promotes)

The script does the observing, the candidates and the verification deterministically. **The agent shows them, a person picks, and only what was picked is written.**
The evidence and thresholds are in section 8 of `docs/research/ONTOLOGY_DESIGN.md` in the baton repo.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/lib/candidates.py scan <repo root>
```

From this repo's Claude Code session logs (including sessions opened outside the repo that worked on this repo's files), it collects "a human prompt → the files edited in that turn" and gives two kinds. It reads all the session logs once, so it can take tens of seconds.

- **Alias candidates**: a turn edited a concept's `files`, but the prompt didn't match the concept's title or aliases. The phrase from that prompt.
- **New concept candidates**: after a prompt that matched no concept, files that are in no concept's `files` were edited. What it really is is **a group of files**; the phrase is a suggested name.

Both remain only if seen on 3 or more different days, not overlapping existing titles or aliases, and the number of other prompts that phrase matches (misfires) is at most the number of hits.
The candidates are only in a cache outside the repo (`~/.cache/baton/candidates/`), and prompt text is not kept.

**Don't report 0 candidates as "none".** Pass on the per-stage counts of the output as they are — whether too few sessions and turns meant it couldn't count,
or there were observations but the checks dropped them (counts per reason), are different things. If there is a `map warning:` line (`지도 경고:` in Korean output), pass it on too — concepts the parser couldn't read were left out of the candidates.

After a person picks:

| The person's answer | What to do |
|---|---|
| Promote an alias | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/candidates.py promote-alias <number> "<phrase>" <repo root>` — **always quote** the phrase (if a two-word phrase is split, the argument count is wrong and it is refused). It is added only to `aliases=` (`별칭=` in a Korean map) on that concept's metadata line. If the person rephrases it (for example, drops a particle), add the rephrased words. If the phrase contains a secret, a home path, the user name, or a word from the private-words list in the config, it is refused and not written (the map may be public). It also refuses a phrase with `Concept N` in it (it would become a false edge), a section with two metadata lines or whose first metadata line is inside a code fence, and a map the parser can't read to the end — a person cleans those up first |
| Promote a new concept | The script doesn't write it. **Actually open** the candidate files, draft the four faces and the metadata line with steps 3–5 of mode ③, show it, and write it after approval. The name is picked by the person from the suggested phrases, or made up anew |
| Discard | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/candidates.py dismiss <candidate id> <repo root>` — it won't show from the next scan on |
| No answer, or later | Do nothing |

**MERGE, DELETE and REPARENT are not offered as candidates** — a person judges them directly in mode ③.

## AGENTS.md — a first-class target

`AGENTS.md` has a different status from other docs. **It is read automatically in every session, and both Claude and Codex see it.**
If it is wrong, it tells the agent about an architecture that doesn't exist as fact, and that costs the most.
A real case was found where it described a deleted screen class as the architecture.

So this skill does three things for `AGENTS.md`.

1. **Verify every factual claim.** Check that file names, class names, numbers and paths exist.
   `AGENTS.md` has a double status — both `Described in` and `Decided` — so it drifts especially often.
2. **Keep the one-line link to the concept map.**
3. **Check for asymmetric instructions** (below).

**It doesn't create one.** Scanning the directory structure to generate a new `AGENTS.md` is already done by the `deepinit` skill.
This skill **verifies and fixes.** For a project without one, point to `deepinit`.

### Asymmetric instructions — when you also use Codex

This is the state where a rule is visible to only one of the agents. It is not counted as a mismatch, but report it with the same weight.

- **Inside the project**: keep `CLAUDE.md` as one line that imports `AGENTS.md`, and keep the content in `AGENTS.md`.
  Then Codex sees the same thing. If a rule is only in `CLAUDE.md`, report it as **asymmetric**.
- **Global**: on 2026-09-14 the sources of truth were merged into one. `<your shared-rules source of truth>` is the source of truth;
  Claude loads it from `CLAUDE.md`, and for Codex `<your sync script>`
  injects it. So the global side is no longer a matter of counting lists but **a one-line check**.

  ```bash
  <your sync script> --check
  ```

  If it reports a mismatch, **don't fix it by hand; run that script.** If you edit `~/.codex/AGENTS.md` by hand,
  the next `omx setup` erases it (without `--merge-agents` it overwrites the whole file).
  That overwrite is the most common cause of the mismatch.

`deepinit` creates **several, in a hierarchy**, like `src/AGENTS.md`. When there are several,
**only the root `AGENTS.md` is a first-class target.** Look at the lower files only when they are in a concept's `Described in`.

## Connecting — fixing broken references

Along with the concept check, look at the following.

- **Broken references** — references to files or section numbers that don't exist. Parent docs that moved out of the repo
- **Broken edges** — concept relations written on one side only (both directions are required, above)
- **Missing relation links** — this project supplies facts to, or receives them from, another project, but there is no link.
  Make a `## Related projects` section in `DECISIONS.md` (`## 관련 프로젝트` in Korean) and connect them in `[[name]]` form.
  **Write the direction** — "when that side changes, update this side, not the other way round"
- **The `Related:` line of a decision entry** — relations are not written separately but accumulate in one `- Related:` line (`- 관련:`) at the end of each `DECISIONS.md` entry
  (another project's `[[name]]` and direction / the concepts it changes / evidence paths, or `none`) (2026-09-06).
  When checking, if a recent decision lacks this line, report it as **a hole in the update path**. Don't fill it in yourself —
  the person who decided knows what is related
- **Holes in the update path** — the pattern where the same fact is in several files and **only one folder is left out of an update**.
  Don't treat it as an individual error; **report it as a problem in the procedure**

## Receiving what comes from the handoff

When the `/handoff` skill raises promotion candidates and the owner writes a decision into `DECISIONS.md`,
the files that decision's `Related:` line points to let you **derive which concepts are affected.**
When running mode ④, also look at decision entries added since the last check — the concepts those decisions touched
**need a re-check because their `Decided` face changed**, even if no file has moved yet.

This is the path that catches "not built yet". The state where the code didn't move but a decision did is exactly "not built yet".

## Don'ts

- Splitting into 30 concepts (can't be maintained)
- Making a new separate file for the relation map (nobody opened one in a week)
- Storing shared-file relations in the metadata line (they explode around hub files)
- Writing an edge on one side only (that is prose, not a graph)
- Checking paths without checking whether they are tracked (an outside repo comes out as "fresh")
- Fixing files in mode ② (a diagnosis is not a treatment)
- Writing mode ⑤ candidates into `CONCEPTS.md` before a person picks them (prompt phrases leak into a tracked file)
- Inventing new status words (counting becomes impossible)
- Marking severity with symbols (call it by name)
- Judging "doc error" without looking at the code (misjudges "not built yet")
- Confirming a subagent report as a defect without checking the source
- Filling in decision records by guessing
- Closing a "not built yet" by fixing the doc
- Leaving `CONCEPTS.md` uncommitted
- Keeping the output only in a central folder

## Re-running (modes ② and ③)

If `CONCEPTS.md` already exists, **update it instead of writing a new one.** Rewriting it whole erases the
"resolved" history and the record of what couldn't be checked.

1. Run mode ④ first to **narrow down the concepts that need a re-check.**
2. Read the existing `CONCEPTS.md` — what was out of sync last time and what couldn't be checked.
3. **If the concept changed as a whole, redo the concept list first.** Don't delete concepts that are gone;
   mark them "retired(date, reason)". Add the new concepts after them.
4. Add **"resolved(date)"** to resolved items. Don't delete them.
5. **Only in mode ③**: refill the sections of the concepts that need a re-check, and update the metadata line's `checked` to the current commit.
   Don't open concepts that don't need a re-check.
   **In mode ②, don't touch files; write the differences only in the report.**
6. **Only in mode ③**: realign the edges (step 4).
7. In mode ②, report here and stop. In mode ③, go to step 7.

**If the target project is in the middle of a large reorganization, it is better to postpone the update.** Chasing something that changes daily
keeps the map wrong and loses trust. Run it once after the reorganization settles —
at that point it is closer to ① (a rewrite) than to mode ③.

## Limits (honestly)

- This skill was made on 2026-09-02 and written from the results of running the procedure in three real projects
  (12 mismatches and 1 misjudgment came out of them). **It has not yet been verified by invoking it as a skill.**
- **The graph and freshness parts were added on 2026-09-14.** The freshness commands (`git log`, path and tracking checks) were
  run in real repos to see how they work and how they fail. **But the whole skill has never been invoked and run
  end to end.**
- None of the three existing `CONCEPTS.md` files has metadata lines. On the first run every concept starts from `checked=unknown`
  and has to be filled once, and vocabulary unification and summary-table column changes come on top. **The first run is close to mode ①.**
- Freshness is computed **per file** only. An unrelated line changing in the same file still makes it need a re-check
  (a false positive). Line-level tracking is not done — line numbers shift easily.
- **Only committed history is looked at.** Uncommitted changes in the working tree are not caught by mode ④.
- Cross-project edges are designed but not turned on. First see whether `Related:` lines build up.
- If the procedure goes wrong, fix this file.
