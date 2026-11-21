<!-- HERO: logo + 20-second demo GIF of `/drift` after a commit (docs/demo.gif). Visuals need owner approval first. -->

# baton

**English** · [한국어](README.ko.md)

[![CI](https://github.com/sulabo/baton/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/sulabo/baton/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/sulabo/baton?include_prereleases)](https://github.com/sulabo/baton/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Find where your decision log, code, and docs disagree — and re-check only what changed.**

baton is a plugin for Claude Code and Codex. It keeps a small concept map of your project — 8–12 core ideas such as a game's scoring rule or your login flow, each tied to the files that implement and describe it — records the commit each concept was last verified at, and tells you at session start when concepts need a re-check. It also checks your session handoff (`HANDOFF.md`) when it is saved, and loads it into context when you ask to pick up where you left off.

> **Beta** (`1.0.0-beta.2`). Messages and skill instructions are in Korean for now — see [Limitations](#limitations).

## Why

Coding agents trust what they read. When `DECISIONS.md` says one thing, the code does another, and the docs describe a third, the agent has to pick one, and it often picks the stale one.

Re-reading everything each session is expensive. Re-reading nothing is how drift creeps in. baton keeps track of *where* each concept lives and *when* it was last checked, so only the concepts whose files changed get a second look.

## Quick start

1. Install, inside Claude Code:

   ```
   /plugin marketplace add sulabo/baton
   /plugin install baton@baton
   ```

   You need `git` and `python3`.

2. In a new session, run `/baton-doctor` to check that the repo is ready.
3. Ask Claude to build a concept map — for example, "Build a concept map for this repo." The `driftmap` skill picks the 8–12 concepts that matter and writes `CONCEPTS.md`. A decision log (`DECISIONS.md`) is optional — see the [FAQ](#faq).
   <!-- Checked 2026-11-21 with `claude -p --plugin-dir`: this request and "Check this repo for drift between docs and code." both invoked baton:driftmap. -->
4. Commit as usual. When a file behind a concept changes, the next session starts with a one-line notice.
5. Run `/drift` to see exactly which concepts to revisit.

<details>
<summary><strong>Codex</strong> (0.155+)</summary>

```bash
codex plugin marketplace add sulabo/baton
codex plugin add baton@baton
```

Codex runs plugin hooks only after you mark them as trusted. The Codex plugin ships the skills and hooks but not the slash commands, so ask for the skill instead of `/drift` or `/promote` (for example, a freshness check with the `driftmap` skill).

</details>

<details>
<summary><strong>From the terminal</strong></summary>

```bash
claude plugin marketplace add sulabo/baton && claude plugin install baton@baton
```

</details>

## What you see

<!-- DEMO: the GIF goes here once approved. Until then, the output below stands in. -->

`/drift` in a demo repo, after one commit changed `src/lives.ts` (translated — the plugin prints this table in Korean for now):

```
#    Concept   Status          Verdict
---- --------- --------------- ------------------------------
1    lives     implemented     needs a re-check — 1 commit
2    score     implemented     fresh
3    levels    not built yet   needs a re-check — no baseline
```

- Concept 1: a file it depends on changed after the commit it was verified at.
- Concept 2: nothing changed, so it is skipped. Nobody opens it.
- Concept 3 was never verified, so it has no baseline. baton flags it instead of counting it as fresh. A count that silently comes out as zero is treated as a bug, not as "nothing found".

<details>
<summary>The same output as printed</summary>

```
#    개념                 상태       판정
---- ---------------------- ------------ ------------------------------
1    목숨                 구현됨    재확인 필요 — 커밋 1건
2    점수                 구현됨    신선
3    레벨                 미구현    재확인 필요 — 기준 없음
```

</details>

## How it compares

| | baton | [claude-mem](https://github.com/thedotmack/claude-mem) | Claude Code built-in (`CLAUDE.md`, auto memory, `/resume`) |
|---|---|---|---|
| Main job | Find where decisions, code, and docs disagree | Remember what your agent did across sessions | Carry instructions and past conversations forward |
| How the record is made | The agent drafts `CONCEPTS.md` and `HANDOFF.md`; a person writes the decisions | A second agent takes notes while you work | You write `CLAUDE.md`; Claude can save its own notes |
| What a new session gets | A notice when concepts need a re-check, and the handoff when you ask for it | A short index of past work; details are searched on demand | The instructions, plus a past conversation if you resume one |
| Runs on | Local Python and shell hooks, your git history | A local worker service; optional cloud sync (see its README) | Built in |

Use claude-mem if you want automatic recall of past sessions. Use baton if you want to know which parts of your project's written knowledge are no longer true.

## Features

### Concept map: `driftmap` and `/drift`

Each concept in `CONCEPTS.md` is compared across three sources — the decision log, the code, and the docs — and the entry records where they disagree. A disagreement is often not a stale doc. It can be a decision that was made but never implemented, so comparing docs only with other docs would "fix" a doc that was right.

Every concept ends with one metadata line:

```
- **메타**: 상태=일치 · 확인=2026-11-20(`9cd1928`) · 파일=`src/lives.ts` · 이웃=개념 2(전제) · 문서=`docs/guide.md`
```

That is: the status (`일치` — decision, code, and docs agree; the status words are a closed list of eight), the commit it was verified at (`9cd1928`), the code files it depends on, its neighbors, and the docs that describe it. Freshness is then a computation, not a judgment. If none of those files — code or docs — has a commit after `9cd1928`, the concept is fresh and nobody opens it. A doc-only change is reported as its own kind of re-check.

There are nine verdicts. Two are plain answers: fresh, or needs a re-check because N commits touched the files. Five are kinds of "can't tell", printed as "needs a re-check" with the reason: no baseline; baseline lost (the commit is not in this clone, for example a squashed branch seen from a fresh clone); baseline outside the current history (the commit exists but is not an ancestor of HEAD: the old commit of a squashed or rebased branch, another branch, a cherry-pick source); path gone (even one of several); and file not tracked (nested repo).
One verdict is for the docs: when only the files listed in `문서=` moved or disappeared, it says so on its own (doc commits, doc path gone). The last is for a concept with no files (a rule), which is tracked only through changes to the decision log. If a rule's recorded commit is lost or outside the history, it becomes a re-check too, because decision changes can't be counted without it. A rule concept whose commit is unknown does not trigger the notice: new maps usually start that way, and an alert on every session would be ignored. `/drift` still shows it as "no baseline, docs not checked". A concept that a newer decision points to is marked for a re-check as well.

### Handoffs

- **Checked on save.** When the agent writes `HANDOFF.md`, a hook checks the eight required sections, the length limits, large code blocks, diffs, secrets, and home-directory paths, then hands the problems back to the agent. It never prints the secret it found. It also warns, without blocking, when an item under "확인된 사실과 결정" (confirmed facts and decisions) is missing `[V]` (checked directly) or `[?]` (from memory or a guess).
- **Loaded on request.** When a prompt asks about progress — by default Korean words such as "이어서" (continue), "어디까지" (how far), "인계" (handoff), the word "handoff", or English phrases such as "where were we", "pick up where we left off", "catch me up", and "how far did we get" — the hook puts `HANDOFF.md` into context (up to 200 lines or 9,000 characters), so the agent doesn't have to find and re-read it. It goes in as a hypothesis, not a fact: one line under the header gives the date the handoff was written (a `YYYY-MM-DD` date in its first 3 lines — the template's title has `작성: YYYY-MM-DD` — or else the last commit of `HANDOFF.md`), how many days ago that was, and how many commits have touched this folder since `HANDOFF.md` was last committed. If there are such commits, it points the agent to them; after 7 days it also says to check first that the next step still holds. When it can't count — the handoff has uncommitted edits, the clone is shallow, or git ran out of time (3 seconds at most, less when the hook is already slow) — it says it couldn't count rather than "no commits". The agent is asked to check only the one or two claims the next step depends on, not to re-verify the whole handoff. This came after a 38-day-old handoff in a stale backup folder was loaded together with "carry on as is". The same handoff goes into a session only once; it goes in again only if `HANDOFF.md` changed or the session was compacted since (when the hook gets no readable session log path, it cannot see a compaction and does not re-inject). Messages from other sessions or subagents (`<agent-message>`, `<cross-session-message>`) and task notifications (`<task-notification>`) get nothing, because no person asked. Prompts without those words get nothing. Single English words like "continue" or "status" are left out on purpose: in our own prompt log every extra match they would add came from pasted instructions, tool output, or SQL. The match is a plain substring, so a work request that merely mentions "handoff" or "인계" gets the handoff too — and that costs: in a snapshot run, loading it into an unrelated task used 11% more input tokens.
- **Nudges.** A notice when the context reaches 2×, and again at 3×, its size at the first call, and one suggestion to write a handoff once 3 or more files have changed and the handoff hasn't.
- **`/promote`** lists constraints that survived several days of handoffs as candidates for `DECISIONS.md`. It doesn't write the decision for you: the reasons and the rejected alternatives exist only in the head of whoever decided.

### Commands

| Command | What it does |
|---|---|
| `/drift` | Lists the concepts that need a re-check, and nothing else |
| `/promote` | Lists handoff items worth promoting to the decision log |
| `/baton-setup` | Tunes thresholds and a private-terms block list from your own session history. Writes only what you pick |
| `/baton-doctor` | Checks that this repo is ready: git, `CONCEPTS.md`, metadata lines, tracked handoff, `DECISIONS.md`, config |
| `/baton-explain` | Shows what the rules decide for a prompt. Changes nothing |

## Privacy and what runs on your machine

- The hooks are Python and shell scripts that run locally: at session start, after `Bash` commands and file edits, on each prompt, and when a turn ends. Read [`hooks/`](hooks/) before installing if that matters to you.
- The hooks and the scripts they call make no network requests. They read your git history and files in the repo. <!-- Basis: static search of hooks/, lib/, tools/ for urllib, requests, curl, wget, socket, http.client, URLs, and git fetch/pull/push/clone — 0 matches. Not a runtime trace. -->
- The handoff and context-growth hooks append one line to `~/.cache/baton/runs.jsonl` for every prompt, every handoff check, and every notice (folder 700, file 600, rotated once past 20 MB). Small cache and per-session state files go in the same folder. A line holds the repo path, what the rules decided, and what was loaded. Prompt text is never stored — only a hash, the length, and the trigger words and concept titles that matched. Turn it off with `BATON_OBSERVE=off`.
- The handoff and context-growth hooks have off switches (`BATON_HANDOFF_INJECT=off`, `BATON_HANDOFF_CHECK=off`, `BATON_HANDOFF_NUDGE=off`, `BATON_SPLIT_NOTICE=off`), set as an environment variable or in the config file that `/baton-setup` writes. The session-start notice and the zero-count reminder have none; disable the plugin to stop them.

## Measured so far

From the author's own use (one person), counted on the evening of 2026-11-20 (KST). Each number has its own period; commands and sources are in the [CHANGELOG](CHANGELOG.md).

- Sessions that opened with a progress question and re-read `HANDOFF.md` within the first 5 model calls: **41 of 42 before install** (2026-08-31 to 10-04), **3 of 11 after** (10-19 to 11-20; 2 of those 3 read only part of it).
- From install (10-04) to 11-20: 270 handoff injections across 40 sessions. The save-time check returned problems on 20 of 38 saves.
- **Tokens did not go down in real use.** The first calls of a session cost more after install. Over the same period the fixed context (other plugins and instructions) also grew, so the two effects can't be separated. In controlled snapshot runs (same repo, same prompt), progress questions used 40–54% fewer input tokens.

## Limitations

- **Korean UI.** Hook messages, skill instructions, and command output are in Korean. English requests do start the skills, and handoff loading answers a few English phrases ("where were we", "pick up where we left off", "catch me up", "how far did we get", "from the last session") — but not a bare "continue". Add your own words with `/baton-setup` (`BATON_HANDOFF_TRIGGERS_EXTRA`).
- Freshness is tracked per file, so an unrelated edit in a listed file still marks the concept for a re-check.
- Only committed history counts. Uncommitted changes are invisible.
- Reversed decisions aren't detected automatically. We tried it and took it out.
- The first concept map is expensive: every concept needs its metadata line filled in.
- The default thresholds were tuned on a few repositories from a single user. `/baton-setup` re-fits them to your history only when the repo has 10 or more Claude Code sessions.
- The handoff checker misses `postgres://user:pw@host` style URLs, `npm_` and `hf_` tokens, and non-JWT Bearer values. It wrongly flags long `sk-` branch names, CI runner home paths, and secret assignments whose value is a timestamp string.
- If the agent writes `HANDOFF.md` in several `Edit` steps, every intermediate save comes back with "required section missing".
- Handoff loading looks for `HANDOFF.md` at the git top level of the folder the hook runs in. Claude Code runs hooks in the project folder, so this is normally the repo you opened.
- On Codex, the context-growth notice, the handoff nudge, and the save-time check don't run (different session log format, and `apply_patch` gives no file path). The skill runs the checker itself instead.

## FAQ

**Does baton send anything over the network?**
No. The hooks read your git history and local files, and write only under `~/.cache/baton/`. See [Privacy](#privacy-and-what-runs-on-your-machine).

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

Bug reports and pull requests are welcome — open an [issue](https://github.com/sulabo/baton/issues) first for anything large. Please don't post secrets or security problems in a public issue.
<!-- Link CONTRIBUTING.md and SECURITY.md here once PR #4 is merged. -->

## License

[MIT](LICENSE)
