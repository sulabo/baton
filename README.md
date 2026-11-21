<!-- HERO (visual draft pending owner approval): logo + short demo of a new session that gets the handoff with its freshness line, then `/drift` after a commit (docs/demo.gif). No image until the owner approves it. -->

# baton

**English** · [한국어](README.ko.md)

**Stop your AI agent from re-reading your project every new session.**

Pick up the last session from a one-page handoff, and find the files you need through a project map.

[![CI](https://github.com/sulabo/baton/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/sulabo/baton/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/sulabo/baton?include_prereleases)](https://github.com/sulabo/baton/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

baton is a plugin for people who work on one project across many Claude Code or Codex sessions. It runs as local hooks (small scripts that run at set moments) and works on two plain files in your repo: `HANDOFF.md` and `CONCEPTS.md`. Using it is simple: install it, say "write a handoff" when a chunk of work is done, and ask "where were we?" in the next session. To install, run `/plugin marketplace add sulabo/baton` and then `/plugin install baton@baton` inside Claude Code ([Quick start](#quick-start)). The concept map (`CONCEPTS.md`) lists the core concepts with their files and the commit each was last checked at; section 2 below explains it.

> **Beta** (`1.0.0-beta.2`). Messages and skill instructions are in Korean for now, and all numbers below come from one person's use. See [Limitations](#limitations).

## The problem

A new session knows nothing, so the agent starts by reading: the README, your notes, the last handoff, the files around them. In the author's logs, 41 of 42 sessions that opened with a progress question such as "how far did we get?" had the agent re-read `HANDOFF.md` within its first five model calls. Everything it reads stays in the context, and the context keeps growing for the rest of the session. Worse, notes go stale, and the agent trusts a handoff or a doc that no longer matches the code.

## What baton does

baton does two things.

### 1. Handoff: the last session on one page

At the end of a chunk of work, ask the agent to "write a handoff". It writes `HANDOFF.md`, and a hook checks the file the moment it is saved. In the next session, ask "where were we?". The hook puts the handoff into context with a line that says how old it is, so the agent doesn't have to look for it.

**What you see.** The first lines the agent receives, from a demo repo where the handoff was written 10 days ago and 3 commits came after it (translated; the plugin prints Korean for now):

```
[baton] Below is the full HANDOFF.md of this repo (injected because the prompt asks about handoff or progress). No need to open the file again. But a handoff is a record from when it was written: read it as a hypothesis, not a fact, and check only the one or two claims the next step depends on with git or the files before you continue.
[baton] This handoff is as of 2026-11-11 (10 days ago, date in its first line). 3 commits since then are not in it — start with `git log --oneline -3 -- .`. 10 days have passed — first check that the next step still holds.

# Session Handoff (작성: 2026-11-11)
```

<details>
<summary>The same lines as printed</summary>

```
[baton] 아래는 이 저장소 HANDOFF.md의 전문이다(프롬프트가 인계·진행 상황을 가리켜 자동 주입). 파일을 다시 열 필요 없다. 다만 인계서는 작성 시점의 기록이다 — 사실이 아니라 가설로 읽고, 다음 행동이 기대는 주장 한두 개만 git·파일로 확인한 뒤 이어서 진행한다.
[baton] 이 인계서는 2026-11-11(10일 전, 첫 줄 작성일) 기준이다. 그 뒤 커밋 3개는 인계서에 없다 — `git log --oneline -3 -- .`부터 본다. 10일 지났다 — 다음 행동이 아직 유효한지부터 확인한다.

# Session Handoff (작성: 2026-11-11)
```

</details>

When a saved handoff has a problem, the agent gets it back to fix (translated; the value it found is never printed):

```
[baton] The HANDOFF.md you just wrote has handoff-check problems. Fix them and save again:
- line 6: looks like an API token — remove it or write it generically (~/, <key>)
- line 6: looks like a password or key assignment — remove it or write it generically (~/, <key>)
- line 7: looks like an absolute home path — remove it or write it generically (~/, <key>)
- 9,277 chars — over the 8,700-char limit (the part past it will not be injected into the next session)
```

How it works:

- **Checked on save.** The checker looks at 200 lines and 8,700 characters, the eight required sections, code blocks over 20 lines, full diffs, secrets, home-directory paths, and the private words you picked in `/baton-setup`. It hands the problems back to the agent. It also warns, without blocking, when an item under "확인된 사실과 결정" (confirmed facts and decisions) is missing `[V]` (checked directly) or `[?]` (from memory or a guess). Run it by hand with `python3 lib/handoff_check.py HANDOFF.md`.
- **Loaded only when you ask.** The hook looks for words about continuing: by default Korean words such as "이어서" (continue), "어디까지" (how far), "인계" (handoff), the word "handoff", and English phrases such as "where were we", "pick up where we left off", "catch me up", and "how far did we get". Other prompts get nothing. Single English words like "continue" or "status" are left out on purpose: in our own prompt log every extra match they would add came from pasted instructions, tool output, or SQL. The match is a plain substring, so a work request that merely mentions "handoff" gets the handoff too.
- **Once per session.** The same handoff goes into a session once. It goes in again only if `HANDOFF.md` changed or the session was compacted since. Messages from other sessions or subagents (`<agent-message>`, `<cross-session-message>`) and task notifications (`<task-notification>`) get nothing, because no person asked.
- **A freshness line.** The date comes from the handoff's first 3 lines, or else from the last commit of `HANDOFF.md`. The commit count is the number of commits that touched this folder since `HANDOFF.md` was last committed. After 7 days, the line also says to check the next step first. When baton can't count (uncommitted edits to the handoff, a shallow clone, or git taking more than 3 seconds), it says so instead of printing "no commits".
- **Nudges.** When the context reaches 2×, and again 3×, its size at the first call, a notice suggests writing a handoff and starting fresh. Once 3 or more files have changed since the last handoff, it suggests writing one, once per session. Writing a named handoff such as `HANDOFF_api.md` counts; only `HANDOFF.md` is checked and injected.
- **`/promote`** lists constraints that survived several days of handoffs as candidates for `DECISIONS.md`. It doesn't write the decision for you: the reasons and the rejected alternatives exist only in the head of whoever decided.

### 2. Concept map: which parts of the project changed

Ask "Build a concept map for this repo". The `driftmap` skill picks the 8–12 ideas that matter, such as a game's scoring rule or your login flow, and writes `CONCEPTS.md`. Each concept is tied to its decision, its code files and its docs, plus the commit it was last checked at. After that, only concepts whose files changed get a second look, and the map records where the decision log, the code, and the docs disagree.

**What you see.** In the same demo repo, one commit changed `src/lives.ts`. The next session starts with one line, and `/drift` shows which concepts to revisit (translated):

```
[baton] 2 concepts in the concept map need a re-check (1 fresh). Details: /drift
```

```
#    Concept   Status          Verdict
---- --------- --------------- ------------------------------
1    lives     agrees          needs a re-check — 1 commit
2    score     agrees          fresh
3    levels    not built yet   needs a re-check — no baseline

Summary: re-check 2 · fresh 1 · rule concepts 0
```

- Concept 1: a file it depends on changed after the commit it was checked at.
- Concept 2: nothing changed, so nobody opens it.
- Concept 3 was never checked, so it has no baseline. baton flags it instead of counting it as fresh. A count that silently comes out as zero is treated as a bug, not as "nothing found".

<details>
<summary>The same output as printed</summary>

```
[baton] 개념 지도에 재확인 대상 2건 (신선 1건). 자세히는 /drift
```

```
#    개념                 상태       판정
---- ---------------------- ------------ ------------------------------
1    목숨                 일치       재확인 필요 — 커밋 1건
2    점수                 일치       신선
3    레벨                 미구현    재확인 필요 — 기준 없음

요약: 재확인 2 · 신선 1 · 규칙 개념 0
```

</details>

<details>
<summary><strong>How the map decides what is fresh</strong></summary>

A disagreement is often not a stale doc. It can be a decision that was made but never built, so comparing docs only with other docs would "fix" a doc that was right. That is why each concept is compared across three sources: the decision log, the code, and the docs.

Every concept ends with one metadata line:

```
- **메타**: 상태=일치 · 확인=2026-11-20(`9cd1928`) · 파일=`src/lives.ts` · 이웃=개념 2(전제) · 문서=`docs/guide.md`
```

That is: the status (`일치`: decision, code, and docs agree; the status words are a closed list of eight), the commit it was checked at (`9cd1928`), the code files it depends on, its neighbors, and the docs that describe it. Freshness is then a computation, not a judgment. If none of those files, code or docs, has a commit after `9cd1928`, the concept is fresh and nobody opens it. A doc-only change is reported as its own kind of re-check.

There are nine verdicts. Two are plain answers: fresh, or needs a re-check because N commits touched the files. Five are kinds of "can't tell", printed as "needs a re-check" with the reason: no baseline; baseline lost (the commit is not in this clone, for example a squashed branch seen from a fresh clone); baseline outside the current history (the commit exists but is not an ancestor of HEAD: the old commit of a squashed or rebased branch, another branch, a cherry-pick source); path gone (even one of several); and file not tracked (nested repo).
One verdict is for the docs: when only the files listed in `문서=` moved or disappeared, it says so on its own (doc commits, doc path gone). The last is for a concept with no files (a rule), which is tracked only through changes to the decision log. If a rule's recorded commit is lost or outside the history, it becomes a re-check too, because decision changes can't be counted without it. A rule concept whose commit is unknown does not trigger the notice: new maps usually start that way, and an alert on every session would be ignored. `/drift` still shows it as "no baseline, docs not checked". A concept that a newer decision points to is marked for a re-check as well.

Instruction files such as `AGENTS.md` or `DECISIONS.md` don't go in `파일=`. They change almost daily, so a concept that lists them would always need a re-check. Changes to the decision log are tracked on their own.

</details>

### Commands

| Command | What it does |
|---|---|
| `/drift` | Lists the concepts that need a re-check, and nothing else |
| `/promote` | Lists handoff items worth promoting to the decision log |
| `/baton-setup` | Tunes thresholds and a private-words block list from your own session history. Writes only what you pick |
| `/baton-doctor` | Checks that this repo is ready: git, `CONCEPTS.md`, metadata lines, tracked handoff, `DECISIONS.md`, config |
| `/baton-explain` | Shows what the rules decide for a prompt. Changes nothing |

### Tune it to your history (optional, once)

The default thresholds come from the author's history. `/baton-setup` runs the same method on yours: it reads this repo's Claude Code session logs and git history, and proposes the context-growth thresholds, the nudge threshold, extra trigger phrases, and private words for the checker to block. It writes only the values you pick, to `~/.config/baton/config.json` (mode 600). With fewer than 10 sessions it recommends the defaults. Order of precedence: environment variable > repo section > global section > default. `python3 lib/config.py` shows the values in effect.

## Quick start

1. Install, inside Claude Code:

   ```
   /plugin marketplace add sulabo/baton
   /plugin install baton@baton
   ```

   You need `git` and `python3`. From a terminal: `claude plugin marketplace add sulabo/baton && claude plugin install baton@baton`.

2. In a new session, run `/baton-doctor` to check that the repo is ready.
3. When a chunk of work is done, say "write a handoff", then commit `HANDOFF.md`.
4. In the next session (or after `/clear`), ask "where were we?". The handoff goes in with its freshness line.
5. Say "Build a concept map for this repo". After later commits, run `/drift` to see which concepts to revisit. A decision log (`DECISIONS.md`) is optional; see the [FAQ](#faq).
   <!-- Checked 2026-11-21 with `claude -p --plugin-dir`: this request and "Check this repo for drift between docs and code." both invoked baton:driftmap. -->

<details>
<summary><strong>Codex</strong> (0.155+)</summary>

```bash
codex plugin marketplace add sulabo/baton
codex plugin add baton@baton
```

Codex runs plugin hooks only after you mark them as trusted. The Codex plugin ships the skills and hooks but not the slash commands, so ask for the skill instead of `/drift` or `/promote` (for example, a freshness check with the `driftmap` skill).

</details>

## How it compares

Facts about other tools come from their own docs and READMEs, read on 2026-11-21.

| | baton | [claude-mem](https://github.com/thedotmack/claude-mem) | Claude Code built-ins (`CLAUDE.md`, auto memory, `/compact`, `/resume`) | [Basic Memory](https://github.com/basicmachines-co/basic-memory) |
|---|---|---|---|---|
| Main job | Hand a short, checked handoff to the next session; flag which concepts changed | Remember what the agent did across sessions | Carry instructions and the conversation forward | A Markdown knowledge base the agent reads and writes |
| Who writes the record | The agent drafts `HANDOFF.md` and `CONCEPTS.md` when you ask; decisions are written by a person | Hooks capture tool calls; a second agent writes observations and a session summary | You write `CLAUDE.md`; Claude saves its own notes to auto memory; `/compact` writes a summary | The agent, through MCP tools; the files are plain Markdown |
| What a new session gets | Nothing until the prompt asks to continue; then the handoff, once, with a freshness line | A compact index of past work; details are searched on demand | `CLAUDE.md` every session; the first 200 lines or 25 KB of `MEMORY.md`; with `--resume`, the last compaction summary and the messages after it | Lookups through MCP (start-up behavior not reviewed) |
| Where it lives | Plain files in your repo, plus a local log | SQLite, FTS5 and Chroma under `~/.claude-mem` | Files in your project and under `~/.claude` | Markdown files with frontmatter and `[[wikilinks]]`, plus a SQLite index |
| License | MIT | Apache-2.0 | Part of Claude Code | AGPL-3.0 |

None of the tools we reviewed documented the following. This is where baton tries to help; if we missed a tool that does it, please tell us in an issue.

- Injecting a handoff only when the prompt asks to continue, once per session, and never into messages from subagents or other sessions.
- A line in the handoff itself that says when it was written and how many commits came after it.
- A rule check of the handoff when it is saved (size, required sections, secrets, home paths, private words).
- A last-checked commit per concept, so that unchanged concepts aren't re-read, and flags where the decision log, the code, and the docs disagree.

The tools do different jobs and can be used together. `/compact` and `/resume` keep one conversation going; baton gives a new session a short written handoff. Use claude-mem if you want automatic recall without writing anything.

## Measured so far

All numbers come from one person's use (the author), on their own repositories. Each has its own period and scope. Commands and sources are in the [CHANGELOG](CHANGELOG.md) and [docs/research/LOOP_PLAN.md](docs/research/LOOP_PLAN.md).

- **Re-reading the handoff.** Of the sessions that opened with a progress question, the agent re-read `HANDOFF.md` within its first 5 model calls in **41 of 42 before install** (2026-08-31 to 10-04) and **3 of 11 after** (10-19 to 11-20; 2 of those 3 read only part of it). Eleven sessions show a direction, not a size.
- **Snapshot runs** (same repo, same prompt, repeated). Progress questions used **40–54% fewer input tokens** with the handoff injected. An unrelated task with the handoff loaded used about **11% more**. That is why the handoff goes in only when you ask.
- **Tokens did not go down in real use so far.** The first calls of a session cost more after install. Over the same period the fixed context (other plugins and instructions) also grew, so the two effects can't be separated. One cause was ours: the usage log up to 11-19 shows the same handoff injected again and again, **263 injections across 37 sessions, only 30 of them on a session's first prompt**. The once-per-session rule fixes this. Replaying the past log with the new rules gives 265 → 55–104 injections; that is an estimate, not a measurement.
- **Where the cost goes.** Across 60 of the author's sessions, **85% of the cost** (weighted by API prices) came from calls made after the context had grown past 2× its size at the first call. That is why baton nudges you at 2× and 3× to write a handoff and start fresh.

## In development: the concept graph as Obsidian notes

This part is a design, not a feature. It is not built or verified yet.

The problem it targets is vocabulary. People ask for work in their own words, and those words rarely match concept titles. We tried matching prompt words to concept titles on the author's usage log (one person, one repo). When the matcher picked exactly one concept, it was the right one **0–1% of the time**, across nine variants. The right concept was among the candidates in only 6 of 54 cases. So the experimental concept injection (`BATON_CONCEPT_INJECT`) stays off. We also tried to learn the missing words from the same logs, and there was too little to learn from: very few prompts were followed by opening a concept's files. The vocabulary has to come from people, as aliases you add yourself.

The plan is to keep one note per concept, in a format that also opens in [Obsidian](https://obsidian.md):

- `aliases` in each note's frontmatter hold the words you add for that concept, so the vocabulary is unified (none are learned automatically);
- `[[links]]` between notes are the edges of the graph;
- note folders mirror the code folders, so a note's location says where the code lives;
- `CONCEPTS.md` is generated from the notes, so `/drift` keeps working.

Retrieval would match a prompt against aliases, go to that note, follow one hop of links, and then read the files. None of this works yet: targets were set before measuring, and the first alias-matching test did not meet them. Design draft: [docs/CONCEPT_GRAPH.md](docs/CONCEPT_GRAPH.md) (Korean, awaiting owner approval).

## Limitations

- **Korean UI.** Hook messages, skill instructions, and command output are in Korean. English requests do start the skills, and handoff loading answers a few English phrases ("where were we", "pick up where we left off", "catch me up", "how far did we get", "from the last session"), but not a bare "continue". Add your own words with `/baton-setup` (`BATON_HANDOFF_TRIGGERS_EXTRA`).
- Freshness is tracked per file, so an unrelated edit in a listed file still marks the concept for a re-check.
- Only committed history counts. Uncommitted changes are invisible to `/drift` and to the handoff's commit count.
- Reversed decisions aren't detected automatically. We tried it and took it out.
- The first concept map is expensive: every concept needs its metadata line filled in.
- The default thresholds were tuned on a few repositories from a single user, and the 7-day age warning has no measurement behind it yet. `/baton-setup` re-fits the thresholds only when the repo has 10 or more Claude Code sessions.
- The save-time check allows 8,700 characters, but with the freshness line the injection has room for about 8,500. A handoff close to the limit loses its last lines, and the hook says where it stopped.
- Once per session has blind spots. After `/rewind`, or when another hook removed the injected text, baton still thinks the handoff is in context and doesn't add it again; the agent then reads the file itself. Without a readable session log path, a compaction can't be seen either. On Codex, whether `/new` keeps the same session id is unverified; if it does, the first "continue" after `/new` gets no handoff.
- Named handoffs (`HANDOFF_*.md`) count for the nudge but are not checked or injected. A doc named like `handoff-design.md` also counts as a handoff write, which can suppress a nudge.
- The handoff checker misses `postgres://user:pw@host` style URLs, `npm_` and `hf_` tokens, and non-JWT Bearer values. It wrongly flags long `sk-` branch names, CI runner home paths, and secret assignments whose value is a timestamp string.
- If the agent writes `HANDOFF.md` in several `Edit` steps, every intermediate save comes back with "required section missing".
- Handoff loading looks for `HANDOFF.md` at the git top level of the folder the hook runs in. Claude Code runs hooks in the project folder, so this is normally the repo you opened.
- On Codex, the context-growth notice, the handoff nudge, and the save-time check don't run (different session log format, and `apply_patch` gives no file path). The skill runs the checker itself instead.

## Privacy and what runs on your machine

- The hooks are Python and shell scripts that run locally: at session start, after `Bash` commands and file edits, on each prompt, and when a turn ends. Read [`hooks/`](hooks/) before installing if that matters to you.
- The hooks and the scripts they call make no network requests. They read your git history and files in the repo. <!-- Basis: static search of hooks/, lib/, tools/ for urllib, requests, curl, wget, socket, http.client, URLs, and git fetch/pull/push/clone — 0 matches. Not a runtime trace. -->
- The handoff and context-growth hooks append one line to `~/.cache/baton/runs.jsonl` for every prompt, every handoff check, and every notice (folder 700, file 600, rotated once past 20 MB). A line holds the repo path, what the rules decided, and what was loaded. Prompt text is never stored: only a hash, the length, and the trigger words and concept titles that matched. Turn it off with `BATON_OBSERVE=off`.
- To inject a handoff only once, baton keeps a small file per session under `~/.cache/baton/injected/` (a hash of the handoff and the session log size, mode 600, removed once older than 7 days). Other small cache and per-session state files go in the same folder.
- The handoff and context-growth hooks have off switches (`BATON_HANDOFF_INJECT=off`, `BATON_HANDOFF_CHECK=off`, `BATON_HANDOFF_NUDGE=off`, `BATON_SPLIT_NOTICE=off`), set as an environment variable or in the config file that `/baton-setup` writes. The session-start notice and the zero-count reminder have none; disable the plugin to stop them.

## FAQ

**Does baton send anything over the network?**
No. The hooks read your git history and local files, and write only under `~/.cache/baton/`. See [Privacy](#privacy-and-what-runs-on-your-machine).

**Does it save tokens?**
In snapshot runs, yes, for progress questions. In real use it hasn't shown that yet; see [Measured so far](#measured-so-far).

**How is this different from `/compact` or `/resume`?**
They keep one conversation going, as a summary plus the messages after it. baton is for starting a new session: it gives the agent a short handoff that you can read and edit, and tells it how old that handoff is. You can use both.

**Can I use it in English?**
Yes, with Korean output for now. English requests start the skills, and handoff loading answers phrases such as "where were we" or "pick up where we left off". Add more trigger words with `/baton-setup`.

**Do I need `DECISIONS.md`?**
No. File freshness works from git history alone. Without a tracked `DECISIONS.md`, `AGENTS.md`, or `CLAUDE.md`, the decision-side check is skipped, so baton can't catch "decided but not built yet", and concepts without files aren't tracked.

**Does it change my files?**
The hooks only print notices and hand problems back to the agent; they don't edit your repo. `CONCEPTS.md` and `HANDOFF.md` are written by the agent when you ask for them. `/baton-setup` writes only `~/.config/baton/config.json`, and only the values you pick.

## Updating and uninstalling

Claude Code (restart after updating):

```bash
claude plugin marketplace update baton
claude plugin update baton@baton
claude plugin uninstall baton@baton        # remove
claude plugin marketplace remove baton     # and forget the marketplace
```

Codex:

```bash
codex plugin marketplace upgrade baton
codex plugin remove baton@baton            # remove
codex plugin marketplace remove baton
```

## Background

How the design got here, what was tried and dropped, and what still doesn't work: [docs/NORTH_STAR_배경.md](docs/NORTH_STAR_배경.md) and [docs/NORTH_STAR.md](docs/NORTH_STAR.md) (Korean). Decisions and their reasons: [DECISIONS.md](DECISIONS.md). Changes per release: [CHANGELOG.md](CHANGELOG.md).

## Contributing

Bug reports and pull requests are welcome. Open an [issue](https://github.com/sulabo/baton/issues) first for anything large. Please don't post secrets or security problems in a public issue.
<!-- Link CONTRIBUTING.md and SECURITY.md here once PR #4 is merged. -->

## License

[MIT](LICENSE)
