# baton guide

**English** · [한국어](GUIDE.ko.md)

This is the full reference for baton; the short overview is in the [README](../README.md).

- [The problem](#the-problem)
- [What baton does](#what-baton-does): [handoff](#1-handoff-the-last-session-on-one-page), [concept map](#2-concept-map-which-parts-of-the-project-changed), [commands](#commands), [tune it to your history](#tune-it-to-your-history-optional-once)
- [Quick start](#quick-start)
- [Language](#language)
- [How it compares](#how-it-compares)
- [Measured so far](#measured-so-far)
- [In development: the concept graph as Obsidian notes](#in-development-the-concept-graph-as-obsidian-notes)
- [Limitations](#limitations)
- [Privacy and what runs on your machine](#privacy-and-what-runs-on-your-machine)
- [FAQ](#faq)
- [Updating and uninstalling](#updating-and-uninstalling)
- [Background](#background)

## The problem

A new session knows nothing, so the agent starts by reading: the README, your notes, the last handoff, the files around them. In the author's logs, 41 of 42 sessions that opened with a progress question such as "how far did we get?" had the agent re-read `HANDOFF.md` within its first five model calls (a model call is one request the agent sends to the model). Everything it reads stays in the context, and the context keeps growing for the rest of the session. Worse, notes go stale, and the agent trusts a handoff or a doc that no longer matches the code.

## What baton does

baton does two things.

### 1. Handoff: the last session on one page

When you finish a piece of work, ask the agent to "write a handoff". It writes `HANDOFF.md`, and a hook checks the file the moment it is saved. On Claude Code, baton also asks the agent to update the handoff when a piece of work ends (see "Written when a piece of work ends" below). In the next session, ask "where were we?". The hook puts the handoff into context with a line that says how old it is, so the agent doesn't have to look for it.

**What you see.** The first few lines the agent receives, from a demo repo where the handoff was written 11 days ago and 3 commits came after it:

```
[baton] Below is this repo's full HANDOFF.md, injected because the prompt asks about handoff or progress. No need to reopen it. It was written earlier: treat it as a hypothesis, check the one or two claims the next step depends on, then continue with the next action. For Owner decisions, use the recommended default if reversible; ask only about irreversible ones.
[baton] This handoff is as of 2026-11-11 (11 days ago, date in its first line). 3 commits since then are not in it — start with `git log --oneline -3 -- .`. 11 days have passed — first check that the next step still holds.

# Session Handoff (written: 2026-11-11)
```

<details>
<summary>The same lines in Korean</summary>

```
[baton] 아래는 이 저장소 HANDOFF.md의 전문이다(프롬프트가 인계·진행 상황을 가리켜 자동 주입). 파일을 다시 열 필요 없다. 다만 인계서는 작성 시점의 기록이다 — 사실이 아니라 가설로 읽고, 다음 행동이 기대는 주장 한두 개만 git·파일로 확인한 뒤 이어서 진행한다. '소유자 확인' 항목은 되돌릴 수 있으면 권장 기본값대로 진행하고, 되돌릴 수 없는 것만 묻는다.
[baton] 이 인계서는 2026-11-11(11일 전, 첫 줄 작성일) 기준이다. 그 뒤 커밋 3개는 인계서에 없다 — `git log --oneline -3 -- .`부터 본다. 11일 지났다 — 다음 행동이 아직 유효한지부터 확인한다.

# Session Handoff (작성: 2026-11-11)
```

</details>

When a saved handoff has a problem, the agent gets it back to fix (the value it found is never printed):

```
[baton] The HANDOFF.md you just wrote has handoff-check problems. Fix them and save again:
- line 6: looks like an API token — remove it or write it generically (~/, <key>)
- line 6: looks like a password or key assignment — remove it or write it generically (~/, <key>)
- line 7: looks like an absolute home path — remove it or write it generically (~/, <key>)
- 9,277 chars — over the 8,700-char limit (the part past it will not be injected into the next session). Cut 577 more chars — largest sections: Changes made 8,727 chars, Verified facts and decisions 218 chars
```

How it works:

- **Checked on save.** The checker looks at the length (200 lines, 8,700 characters), the eight required sections, code blocks over 20 lines, full diffs, secrets, home-directory paths, and the private words you picked in `/baton-setup`. It hands the problems back to the agent. It also warns, without blocking, when an item under "Verified facts and decisions" is missing `[V]` (checked directly) or `[?]` (from memory or a guess). Run it by hand with `python3 lib/handoff_check.py HANDOFF.md`. A `HANDOFF.md` written by a Bash command (python, for example) gets the same check after that command ends, also when it exits non-zero, if the command names a handoff file (a `.md` name containing `handoff`, such as `HANDOFF.md` or `HANDOFF_track.md`, any case). baton doesn't parse the shell command: it checks the repo-root `HANDOFF.md` when its content differs from what this session last saw and the change happened during this call (the file's modified time is after the call's start in the session log), and says "HANDOFF.md had changed after this Bash call". A change after a call that doesn't name a handoff file (`git checkout`, `git pull` and so on), or one made by another window or a person before the call started, is only remembered, not checked. If the call's start can't be found in the log, only the file-name rule applies. Limits: a script that doesn't name the file writes an unchecked handoff, and a write and a commit in the same call (`python … && git commit`) are checked only after the commit. Over 8,700 characters, the check says how many to cut and names the two largest sections; over 200 lines, how many lines to cut and the two sections with the most lines. While the file is over a limit, a save that is shorter than the last check only warns, and a size problem blocks at most once per turn. Other problems, such as secrets, still block.
- **Dropped lines.** On save, the checker also compares the file with its last committed version (`HANDOFF.md` at `HEAD`) and lists the lines that are gone. It lists every dropped line from "Failed approaches", "Promotion candidates" and "Rejected", because those are meant to last across sessions. From "Verified facts and decisions" and "Risks and next actions" it lists only lines with a decision or constraint word, such as "owner", "decided", "never" or "do not", because finished work is usually deleted there. A line that moved elsewhere in the handoff or into `DECISIONS.md` is not counted as dropped. This is a warning, not a block, and it says nothing while `HANDOFF.md` isn't committed. The rule was tuned on one repo's handoff history; in a 20-line sample, about 20% of the flagged lines were false alarms.
- **Loaded only when you ask.** The hook looks for words about continuing: by default Korean words such as "이어서" (continue), "어디까지" (how far), "인계" (handoff), the word "handoff", and English phrases such as "where were we", "pick up where we left off", "catch me up", and "how far did we get". Other prompts get no handoff. Single English words like "continue" or "status" are left out on purpose: in our own prompt log every extra match they would add came from pasted instructions, tool output, or SQL. A word only has to appear somewhere in the prompt, so a work request that merely mentions "handoff" gets the handoff too.
- **Fits in one piece.** A handoff that passes the check goes in whole. Everything the hook adds (header, freshness line and must-read line included) stays under Claude Code's 10,000-character cap for hook output. Past that cap, Claude Code would save the text to a file and pass on only a preview.
- **Once per session.** The same handoff goes into a session once. It goes in again only if `HANDOFF.md` changed or the session was compacted since (compaction is when a long conversation is replaced by a summary). Messages from other sessions or subagents (`<agent-message>`, `<cross-session-message>`) and task notifications (`<task-notification>`) get nothing, because no person asked.
- **A freshness line.** The date comes from the handoff's first 3 lines, or else from the last commit of `HANDOFF.md`. The commit count is the number of commits that touched this folder since `HANDOFF.md` was last committed. After 7 days, the line also says to check the next step first. When baton can't count (uncommitted edits to the handoff, a shallow clone, or git taking more than 3 seconds), it says so instead of printing "no commits".
- **Must-read entries.** In "Files and symbols", put `(must read)` (or `(필독)`) after up to 3 entries that the next session has to read before acting. When the handoff is injected, those entries go in one line right after the freshness line, so they are seen even if the handoff is cut. The checker warns when more than 3 are marked, and counts that line toward the 8,700-character limit.
- **Written when a piece of work ends (Claude Code).** baton counts the files edited in the session since a handoff was last written in it (or since the session started). Once that reaches 3 (`BATON_HANDOFF_NUDGE_FILES`), the Stop hook, which runs when the agent ends its turn, keeps the turn going once per session and asks the agent to update `HANDOFF.md`. The agent starts from the current file and carries forward every line that is still true, instead of rewriting it from memory. It skips the promotion review, does not commit, and tells you in one line; the save hook runs the check. If the repo has a `HANDOFF.md` in another format, baton only suggests and doesn't rewrite it. This is on by default. `BATON_HANDOFF_AUTO=off` brings back the old behavior: a short suggestion to you, and you decide. `BATON_HANDOFF_NUDGE=off` turns off both for this files-edited rule; the context rule below has its own switch. Writing a named handoff such as `HANDOFF_api.md` counts as writing one, and so does a Bash call after which the save-time check above checked a changed repo-root `HANDOFF.md`, even a write inside a python command that the session log doesn't show. The file's modified time is not used, so a `git checkout` or another window's write doesn't count as writing the handoff; only `HANDOFF.md` is checked and injected.
- **Saved when the context grows (Claude Code).** baton looks at the context sent with each model call. When it passes 250K tokens, and again when it passes 450K (`BATON_SPLIT_TOKENS`, default `250000,450000`), the Stop hook asks the agent once to update `HANDOFF.md` the same way, but only at the end of a turn that did work after the handoff was last written. Work means a file edited with `Write`/`Edit`, an `Agent`/`Task` call whose subagent edited or wrote files (if its record can't be found, read-only kinds such as Explore, Plan or reviewers don't count), or a Bash command that clearly writes a file (`sed -i`, a `>`/`>>` redirect to a path outside temp folders, `tee`, `mv`, `cp`, `git mv`); a Bash command that writes `HANDOFF.md` counts as writing the handoff. A turn that only asks or reads is not stopped, even if an earlier turn did work; the threshold waits and is asked once at the end of the next turn that does work. A turn starts at a human prompt, a message from another session, or a task notification; a background subagent's edits count once, in the turn opened by its completion notification (the one whose `<tool-use-id>` is that delegation's tool_use id). Other notifications and messages from other sessions don't re-check it, and writing a handoff drops delegations still waiting. It also doesn't ask while a new conversation would start almost as large (the context is not yet 24K tokens past the first call; this applies to the older ratio rule too). The agent tells you in one line that, by a recount of the author's sessions, from this size on, starting a new conversation and saying "where were we" is usually cheaper. Below 250K (a lowered threshold) it says only that you can continue in a new conversation, since the recount doesn't back a cost claim there. baton doesn't suggest `/compact`. If the files-edited rule and the context rule fire at the same Stop, the agent is asked once. With `BATON_HANDOFF_AUTO=off` or a `HANDOFF.md` in another format, you get a short notice instead. If you set `BATON_SPLIT_RATIOS` yourself and not `BATON_SPLIT_TOKENS`, the older rule stays: multiples of the context at the first call. The defaults come from sessions with a 1M-token context window. On a 200K window the conversation is compacted before 250K, so the rule doesn't fire. You can lower `BATON_SPLIT_TOKENS`, but whether starting fresh is cheaper at that size wasn't measured (in the 1M-window sessions, 150K was usually a loss). `/baton-setup` says so in one line when your sessions were compacted before reaching the first threshold. `BATON_SPLIT_NOTICE=off` turns this off.
- **`/promote`** lists constraints that survived several days of handoffs as candidates for `DECISIONS.md`. It doesn't write the decision for you: the reasons and the rejected alternatives exist only in the head of whoever decided.

### 2. Concept map: which parts of the project changed

Ask "Build a concept map for this repo". The `driftmap` skill picks the 8–12 ideas that matter, such as a game's scoring rule or your login flow, and writes `CONCEPTS.md`. Each concept is tied to its decision, its code files and its docs, plus the commit it was last checked at. After that, only concepts whose files changed get a second look, and the map records where the decision log, the code, and the docs disagree.

**Concept index, once per session.** If the repo has a `CONCEPTS.md`, the first prompt you type in a session also gets a short index of it, whether or not you asked to continue. It has one line per concept: the name, the subtitle after "—" in its heading if there is one, and up to three of its files. The agent picks from that list. Nothing matches your words against concept titles, because people rarely use the concepts' names.

- **Cost.** At most 1,500 characters per session, and they stay in context on every turn after that. It is on by default; `BATON_CONCEPT_INDEX=off` turns it off.
- **When.** Once per session, and again after a compaction. Never on messages from other sessions or task notifications. Not at all when the hook can't keep its per-session memory (no session id, or an unwritable cache).
- **With the handoff.** When the handoff goes in on the same prompt, the index comes after it and gives way. A handoff that passes the check is never cut for it. If the index doesn't fit, the subtitles go first, then all but the first file, then the last concepts, and a closing line says how many were left out.
- **Effect.** Still being measured. In 24 runs (4 everyday questions, 3 runs each, with and without the index), it helped on 2 questions and did worse on the other 2.

The index from the same demo repo, on a first prompt that doesn't ask to continue:

```
[baton] Index of this repo's concept map (CONCEPTS.md). Open the files of the concept that fits the task first. A concept is a navigation anchor — check actual behavior in the code. The evidence is in that section of CONCEPTS.md.
1. lives — starting number of lives · files: src/lives.ts
2. score — points per coin · files: src/score.ts
3. levels — level list, still empty · files: src/levels.ts
```

<details>
<summary>The same index in Korean</summary>

```
[baton] 이 저장소 개념 지도(CONCEPTS.md) 색인이다. 작업에 맞는 개념의 파일부터 연다. 개념은 탐색 앵커다 — 실제 동작은 코드로 확인한다. 자세한 근거는 CONCEPTS.md의 그 절에.
1. 목숨 — 시작할 때 목숨 수 · 파일: src/lives.ts
2. 점수 — 코인 하나당 점수 · 파일: src/score.ts
3. 레벨 — 레벨 목록, 아직 비어 있음 · 파일: src/levels.ts
```

</details>

**What you see.** In the same demo repo, one commit changed `src/lives.ts`. The next session starts with one line, and `/drift` shows which concepts to revisit:

```
[baton] 2 concepts in the concept map need another look (1 unchanged). For details: /drift
```

The same line comes back at most once a day; when the number of concepts to re-check changes, it shows at once. `BATON_DRIFT_NOTICE=off` turns it off.

```
#    Concept   Status          Verdict
---- --------- --------------- ------------------------------
1    lives     agrees          needs a re-check — 1 commit
2    score     agrees          fresh
3    levels    not built yet   needs a re-check — no baseline

Summary: re-check 2 · fresh 1 · rule concepts 0
```

- Concept 1: a file it depends on changed after the commit it was checked at.
- Concept 2: nothing changed, so it is marked fresh and needs no second look.
- Concept 3 was never checked, so it has no baseline. baton flags it instead of counting it as fresh. When baton can't count something, it says so instead of showing 0.
- "Rule concepts" are concepts with no files, such as a rule that lives only in the decision log.

<details>
<summary>The same output in Korean</summary>

```
[baton] 개념 지도에서 다시 확인할 개념이 2개 있어요(그대로인 개념 1개). 자세히 보려면 /drift
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
- **Meta**: status=agrees · checked=2026-11-20(`9cd1928`) · files=`src/lives.ts` · neighbors=Concept 2(premise) · docs=`docs/guide.md`
```

That is: the status (`agrees`: decision, code, and docs agree; the status words are a closed list of eight), the commit it was checked at (`9cd1928`), the code files it depends on, its neighbors, and the docs that describe it. A Korean map writes the same line with Korean keys, and baton reads both (see [Language](#language)). baton doesn't judge freshness; it counts commits. If none of those files, code or docs, has a commit after `9cd1928`, the concept is fresh and needs no second look. A doc-only change is reported as its own kind of re-check.

There are nine verdicts, and five of them are kinds of "can't tell".

| Verdict | Meaning |
|---|---|
| fresh | No commit since the check. Nothing to re-read |
| needs a re-check — N commits | The files changed |
| needs a re-check — no baseline | No check commit is recorded |
| needs a re-check — baseline lost | The commit is not in this clone (for example, a squashed branch seen from a fresh clone) |
| needs a re-check — baseline outside the current history | The commit exists but is not an ancestor of HEAD (the old commit of a squashed or rebased branch, another branch, a cherry-pick source) |
| needs a re-check — path gone | A file is missing (even one of several) |
| needs a re-check — not tracked | The file is in a nested repo |
| needs a re-check — N doc commits · needs a re-check — N doc paths gone | The code is unchanged, but files listed in `docs=` changed or disappeared |
| rule concept — tracked only through decision changes | A concept with no files. If its recorded commit is lost or outside the history, decision changes can't be counted, so it becomes a re-check. A rule concept whose commit is unknown does not trigger the notice: new maps usually start that way, and an alert on every session would be ignored. `/drift` still shows it as "no baseline, docs not checked" |

A concept that a newer decision points to (through a `Related:` line, `관련:` in Korean) is marked for a re-check as well.

Instruction files such as `AGENTS.md` or `DECISIONS.md` don't go in `files=`. They change almost daily, so a concept that lists them would always need a re-check. Changes to the decision log are tracked on their own.

</details>

### Commands

| Command | What it does |
|---|---|
| `/drift` | Shows which concepts need a re-check, and stops there |
| `/promote` | Lists handoff items worth promoting to the decision log |
| `/baton-setup` | Tunes thresholds, a private-words block list and the output language from your own session history. Writes only what you pick |
| `/baton-doctor` | Checks that this repo is ready: git, `CONCEPTS.md`, metadata lines, tracked handoff, `DECISIONS.md`, config. Shows the output language and where it came from, and warns when a personal skill with the same name as a plugin skill (such as `~/.claude/skills/handoff`) hides it |
| `/baton-explain` | Shows what the rules decide for a prompt. Changes nothing |

### Tune it to your history (optional, once)

The default thresholds come from the author's history. `/baton-setup` runs the same method on yours and proposes changes (on Codex, ask "set up baton" to call the skill). Nothing changes until you pick.

- **What it reads**: Claude Code session logs opened at this repo's top level (`~/.claude/projects`), the git author, tracked files and untracked files that aren't ignored, the working-folder names in other projects' session logs (as candidates for project names), and `HANDOFF.md`, `DECISIONS.md`, `CONCEPTS.md`. Codex sessions aren't counted yet.
- **What it proposes**: the auto-write and nudge threshold (after how many edited files), extra trigger phrases, the output language (`BATON_LANG`, from the share of your past prompts that contain Korean), and a **private-words list** for the checker to block (your name, email, and other project names, only the ones you pick). With fewer than 10 sessions it recommends the defaults. It shows the context thresholds (250K and 450K tokens) and where they come from, but doesn't propose them from your history.
- **What it writes**: only the values you pick, to `~/.config/baton/config.json` (under `XDG_CONFIG_HOME` if set), mode 600, with a per-repo section and a global section.
- **Where private data ends up**: when you run it as a skill, the scan output (the private-word candidates) and the apply command line go into the agent's context and the Claude Code session log. If you don't want that, put the words in a file outside the repo and pass it with `--private-terms-file`, or run it yourself in a terminal outside the session.
- **Order of precedence**: environment variable > repo section > global section > default. `python3 lib/config.py` shows the values in effect.

## Quick start

1. Install, inside Claude Code:

   ```
   /plugin marketplace add sulabo/baton
   /plugin install baton@baton
   ```

   You need `git` and `python3`. From a terminal: `claude plugin marketplace add sulabo/baton && claude plugin install baton@baton`.

2. In a new session, run `/baton-doctor` to check that the repo is ready.
3. When you finish a piece of work, say "write a handoff", then commit `HANDOFF.md`.
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

## Language

baton prints its messages in English or Korean. The setting changes only the messages; files are read in both languages.

**Setting.** `BATON_LANG` takes `en`, `ko`, or `auto`. baton uses the first of these that is set:

1. the `BATON_LANG` environment variable;
2. `BATON_LANG` in the repo section of the config file (`~/.config/baton/config.json`, written by `/baton-setup`);
3. `BATON_LANG` in the global section of that file;
4. the locale: the first of `LC_ALL`, `LC_MESSAGES` and `LANG` that has a value. `ko` on its own or followed by `_`, `.`, `@` or `-` (such as `ko_KR.UTF-8`) means Korean; anything else means English;
5. on macOS, when none of those three is set (for example when Claude Code is started from an app, not a terminal): the first entry of the system language list (`AppleLanguages`), read with the same rule;
6. English.

`auto`, or any value other than `en` and `ko`, means "follow the locale". An empty `BATON_LANG` counts as not set. `/baton-setup` counts how many of your past prompts contain Korean and proposes `ko` or `en`; nothing is written until you pick. `/baton-doctor` shows the language in effect and where it came from.

**Files in both languages.** Whatever the setting, baton reads the English and the Korean forms of its files. Use one form within a file.

`HANDOFF.md` headings (the templates are in [`skills/baton/SKILL.md`](../skills/baton/SKILL.md)):

| English | Korean |
|---|---|
| `# Session Handoff (written: YYYY-MM-DD)` | `# Session Handoff (작성: YYYY-MM-DD)` |
| `## Goal and done criteria` | `## 목표와 완료 조건` |
| `## Verified facts and decisions` | `## 확인된 사실과 결정` |
| `## Files and symbols` | `## 관련 파일·심볼` |
| `## Changes made` | `## 이미 한 변경` |
| `## Failed approaches (do not retry)` | `## 실패한 접근법 (다시 시도 금지)` |
| `## Verification evidence` | `## 검증 증거` |
| `## Risks and next actions` | `## 남은 리스크와 다음 행동` |
| `- Owner decisions:` (sub-list in that section) | `- 소유자 확인:` |
| `## Promotion candidates (to DECISIONS.md)` | `## 승격 후보 (DECISIONS.md로 올릴 것)` |
| `### Rejected (do not raise again)` | `### 기각됨 (다시 올리지 않는다)` |
| `(must read)` | `(필독)` |

`CONCEPTS.md` metadata line:

| English map | Korean map |
|---|---|
| `- **Meta**:` | `- **메타**:` |
| `status=` | `상태=` |
| `checked=` (or `checked=unknown`) | `확인=` (or `확인=미상`) |
| `files=` (`files=none(rule concept)` for a rule concept) | `파일=` (`파일=없음(규칙 개념)`) |
| `neighbors=Concept 2(premise)` | `이웃=개념 2(전제)` |
| `docs=` (`docs=none` for no docs) | `문서=` (`문서=없음`) |
| `aliases=` | `별칭=` |

Status words, a closed list of eight:

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

In `DECISIONS.md`, a `Related:` line (`관련:` in Korean) names the concepts a decision touches.

## How it compares

Facts about other tools come from their own docs and READMEs, read on 2026-11-21 and 2026-11-22.[^reviewed]

| | baton | [claude-mem](https://github.com/thedotmack/claude-mem) | Claude Code built-ins (`CLAUDE.md`, auto memory, `/compact`, `/resume`) | [Basic Memory](https://github.com/basicmachines-co/basic-memory) |
|---|---|---|---|---|
| Main job | Hand a short, checked handoff to the next session; flag which concepts changed | Remember what the agent did across sessions | Carry instructions and the conversation forward | A Markdown knowledge base the agent reads and writes |
| Who writes the record | The agent drafts `HANDOFF.md` and `CONCEPTS.md` when you ask, and updates `HANDOFF.md` when a piece of work ends (Claude Code); decisions are written by a person | Hooks capture tool calls; a second agent writes observations and a session summary | You write `CLAUDE.md`; Claude saves its own notes to auto memory; `/compact` writes a summary | The agent, through MCP tools; the files are plain Markdown |
| What a new session gets | First prompt: the concept index once (≤1,500 chars). When you ask to continue: the handoff once, with a freshness line | A compact index of past work; details are searched on demand | `CLAUDE.md` every session; the first 200 lines or 25 KB of `MEMORY.md`; with `--resume`, the last compaction summary and the messages after it | Lookups through MCP (start-up behavior not reviewed) |
| Where it lives | Plain files in your repo, plus a local log | SQLite, FTS5 and Chroma under `~/.claude-mem` | Files in your project and under `~/.claude` | Markdown files with frontmatter and `[[wikilinks]]`, plus a SQLite index |
| License | MIT | Apache-2.0 | Part of Claude Code | AGPL-3.0 |

None of the tools we reviewed documented the following. This is where baton tries to help; if we missed a tool that does it, please tell us in an issue.

- Putting the handoff into context automatically when a prompt asks to continue: once per session, and never into messages from subagents or other sessions.
- A rule check of the handoff when it is saved (size, required sections, secrets, home paths, private words).
- A last-checked commit per concept, so that unchanged concepts aren't re-read, and flags where the decision log, the code, and the docs disagree.

The closest we found on staleness is [claude-handoff](https://github.com/willseltzer/claude-handoff). Its `/handoff:resume` command asks the agent to run `git status` and `git log` and check whether commits came after the handoff. baton counts those commits in the hook, before the agent reads anything, and puts the result in the first lines.

The tools do different jobs and can be used together. `/compact` and `/resume` keep one conversation going; baton gives a new session a short written handoff. Use claude-mem if you want automatic recall without writing anything.

[^count]: The CHANGELOG's 270 injections in 40 sessions count through 11-20 and include automated sessions. This count covers 10-04 to 11-19 and leaves out automated sessions opened in the home folder.

[^reviewed]: Tools whose docs or READMEs we read for this comparison: Claude Code (memory and sessions docs), Codex (`AGENTS.md` and memories docs), claude-mem, Basic Memory, Cline Memory Bank, Serena, Context7, codegraph, and claude-handoff (its README and `/handoff:resume` command, read 2026-11-22).

## Measured so far

All numbers come from one person's use (the author), on their own repositories. Each has its own period and scope. Commands and sources are in the [CHANGELOG](../CHANGELOG.md) and [docs/research/LOOP_PLAN.md](research/LOOP_PLAN.md).

- **Re-reading the handoff.** We took the sessions that opened with a progress question and checked whether the agent re-read `HANDOFF.md` within its first 5 model calls. Before install it did in **41 of 42** (2026-08-31 to 10-04; 3 of those 41 read only part of it). After install it did in **3 of 11** (10-19 to 11-20; 2 of those 3 read only part of it). Eleven sessions show a direction, not a size.
- **Snapshot runs.** We ran 3 repos, 3–5 runs per condition, with the same prompt within each repo. Progress questions used **40–54% fewer input tokens** with the handoff injected. In one repo (5 runs), an unrelated task with the handoff loaded used about **11% more**. That is why the handoff goes in only when you ask.
- **Tokens did not go down in real use so far.** The first calls of a session cost more after install. Over the same period the fixed context (other plugins and instructions) also grew, so the two effects can't be separated. One cause was ours. From 2026-10-04 to 11-19 the usage log shows **269 injections in 39 sessions, and only 32 of them on a session's first prompt**; the rest put the same handoff in again ([LOOP_PLAN](research/LOOP_PLAN.md)).[^count] The once-per-session rule is meant to fix this. Its effect hasn't been measured yet.
- **Concept index: cost and effect not established yet.** In 24 runs (4 everyday questions × 3 × with and without, isolated), the first tool call aimed at the right file was, on average, call number 1.50 with the index and 2.33 without, with 11% fewer input tokens and 6% lower cost. But the index was better on only 2 of the 4 questions, so the result is inconclusive. In this repo the index takes 1,118 characters per session.
- **Where the cost goes.** We looked at 60 of the author's sessions with 20 or more model calls (2026-08-31 to 09-30, main thread only). **85% of the cost** (weighted by API prices) came from calls made after the context had grown past 2× its size at the first call. A later recount of 50 of the author's sessions (2026-10-01 on, 20 or more calls, up to the first compaction) also counted the cost of writing the handoff. With prices fitted to our experiment, starting fresh at 150K tokens came out ahead in only 24% of the sessions that got that far; at 250K it was 64%, and at 450K 60%. That is why the defaults are 250K and 450K tokens. It is an estimate from one person's sessions that assumes the same work after the split; what starting fresh saves in real use hasn't been measured.

## In development: the concept graph as Obsidian notes

The concept graph (Obsidian notes, the context compiler) doesn't change what the agent sees yet. Some of its code exists. The concept index above is shipped; the graph is not.

The problem it targets is vocabulary. People ask for work in their own words, and those words rarely match concept titles. We tried matching prompt words to concept titles on the author's usage log (one person, one repo). When the matcher picked exactly one concept, it was the right one **0–1% of the time**, across nine variants. The right concept was among the candidates in only 6 of 54 cases. So the experimental concept injection (`BATON_CONCEPT_INJECT`) stays off.

The fix has to come from people. `driftmap` can list alias candidates from your past sessions, and a person picks which ones go into `CONCEPTS.md` as `별칭=` (aliases). Candidates stay in a cache outside the repo (`~/.cache/baton/candidates/`), and prompt text is not kept. On the author's logs this found no usable aliases: too few prompts were followed by opening a concept's files. So the words have to be aliases you add yourself. A context compiler (`python3 lib/compiler.py explain "<prompt>"`) shows which concepts, files and decisions the graph would pick for a prompt. Its code exists, but it is not wired into the hook.

The plan is to keep one note per concept, in a format that also opens in [Obsidian](https://obsidian.md):

- `aliases` in each note's frontmatter hold the words you add for that concept, so the vocabulary is unified (none are learned automatically);
- `[[links]]` between notes are the edges of the graph;
- note folders mirror the code folders, so a note's location says where the code lives;
- `CONCEPTS.md` is generated from the notes, so `/drift` keeps working.

Retrieval would match a prompt against aliases, go to that note, follow one hop of links, and then read the files. None of this works yet. The targets were set before measuring, and the first alias-matching test did not meet them. Design draft: [docs/CONCEPT_GRAPH.md](CONCEPT_GRAPH.md) (Korean, awaiting owner approval).

## Limitations

- Handoff loading answers a few English phrases ("where were we", "pick up where we left off", "catch me up", "how far did we get", "from the last session"), but not a bare "continue". Add your own words with `/baton-setup` (`BATON_HANDOFF_TRIGGERS_EXTRA`).
- The auto-write counts edited files, not finished work. Editing 3 files in the middle of a task also triggers it (once per session).
- Freshness is tracked per file, so an unrelated edit in a listed file still marks the concept for a re-check.
- Only committed history counts. Uncommitted changes are invisible to `/drift` and to the handoff's commit count.
- Reversed decisions aren't detected automatically. We tried it and took it out.
- The first concept map is expensive: every concept needs its metadata line filled in.
- The default thresholds were tuned on a few repositories from a single user, and the 7-day age warning has no measurement behind it yet. `/baton-setup` re-fits the thresholds only when the repo has 10 or more Claude Code sessions.
- Once per session has blind spots. After `/rewind`, or when another hook removed the injected text, baton still thinks the handoff is in context and doesn't add it again; the agent then reads the file itself. Without a readable session log path, a compaction can't be seen either. On Codex, whether `/new` keeps the same session id is unverified; if it does, the first "continue" after `/new` gets no handoff.
- Named handoffs (`HANDOFF_*.md`) count for the auto-write and the nudge but are not checked or injected. A doc named like `handoff-design.md` also counts as a handoff write, which can suppress a nudge.
- The handoff checker misses `postgres://user:pw@host` style URLs, `npm_` and `hf_` tokens, and non-JWT Bearer values. It wrongly flags long `sk-` branch names, CI runner home paths, and secret assignments whose value is a timestamp string.
- If the agent writes `HANDOFF.md` in several `Edit` steps, every intermediate save comes back with "required section missing".
- Handoff loading looks for `HANDOFF.md` at the git top level of the folder the hook runs in. Claude Code runs hooks in the project folder, so this is normally the repo you opened.
- On Codex, the context-growth notice, the handoff auto-write and nudge, and the save-time check don't run (different session log format, and `apply_patch` gives no file path). The skill runs the checker itself instead.

## Privacy and what runs on your machine

- The hooks are Python and shell scripts that run locally: at session start, after `Bash` commands and file edits, on each prompt, and when a turn ends. Read [`hooks/`](../hooks/) before installing if that matters to you.
- The hooks and the scripts they call make no network requests. They read your git history and files in the repo. <!-- Basis: static search of hooks/, lib/, tools/ for urllib, requests, curl, wget, socket, http.client, URLs, and git fetch/pull/push/clone — 0 matches. Not a runtime trace. -->
- The handoff and context-growth hooks append one line to `~/.cache/baton/runs.jsonl` for every prompt, every handoff check, and every notice. The folder is mode 700 and the file 600. Past 20 MB, the log is renamed to `runs.jsonl.1` (replacing the previous one) and a new log starts. A line holds the repo path, what the rules decided, and what was loaded. Prompt text is never stored: only a hash, the length, and the trigger words and concept titles that matched. Turn it off with `BATON_OBSERVE=off`.
- To inject a handoff only once, baton keeps a small file per session under `~/.cache/baton/injected/` (a hash of the handoff and the session log size, mode 600, removed once older than 7 days). Other small cache and per-session state files go in the same folder.
- `/baton-setup` reads more than the hooks do (other projects' folder names, your git author, untracked files), and its scan output can end up in the session log. See [Tune it to your history](#tune-it-to-your-history-optional-once) for what it reads and how to keep private words out of the session.
- The handoff, concept-index and context-growth hooks have off switches (`BATON_HANDOFF_INJECT=off`, `BATON_CONCEPT_INDEX=off`, `BATON_HANDOFF_CHECK=off`, `BATON_HANDOFF_NUDGE=off`, `BATON_SPLIT_NOTICE=off`, `BATON_DRIFT_NOTICE=off` for the concept-map notice at session start, and `BATON_HANDOFF_AUTO=off`, which turns the auto-write back into a suggestion), set as an environment variable or in the config file that `/baton-setup` writes. The zero-count reminder has none, so disable the plugin to stop it (it is a note that appears when one of baton's check scripts prints a zero, asking the agent to tell "really zero" from "couldn't count").

## FAQ

**Does baton send anything over the network?**
No. The hooks read your git history and local files, and write only under `~/.cache/baton/`. See [Privacy](#privacy-and-what-runs-on-your-machine).

**Does it save tokens?**
In snapshot runs, yes, for progress questions. In real use it hasn't shown that yet; see [Measured so far](#measured-so-far).

**How is this different from `/compact` or `/resume`?**
They keep one conversation going, as a summary plus the messages after it. baton is for starting a new session: it gives the agent a short handoff that you can read and edit, and tells it how old that handoff is. You can use both. In our test at a task boundary (a scripted session in the baton repo, 5 runs each), both carried the work over correctly after the handoff fix, and the handoff run cost about 1.7× as much as the `/compact` run (median, with the prompt cache counted as warm; 1.2× on the raw reported cost). A second repo was dropped on 2026-11-25 because its `/compact` runs had also received a handoff. Our pre-registered rule needs two repos, so it gives no verdict. See [docs/research/compact-vs-handoff.md](research/compact-vs-handoff.md#correction-2026-11-25).

**Can I use it in English?**
Yes. Messages are in English unless your locale is Korean; set `BATON_LANG=en` to choose English. English requests start the skills, handoff loading answers phrases such as "where were we" or "pick up where we left off", and English handoffs and concept maps are read like Korean ones. Add more trigger words with `/baton-setup`. See [Language](#language).

**Do I need `DECISIONS.md`?**
No. File freshness works from git history alone. Without a tracked `DECISIONS.md`, `AGENTS.md`, or `CLAUDE.md`, the decision-side check is skipped, so baton can't catch "decided but not built yet", and concepts without files aren't tracked.

**Does it change my files?**
The hooks only print notices and hand problems and requests back to the agent; they don't edit your repo themselves. `CONCEPTS.md` and `HANDOFF.md` are written by the agent when you ask for them. On Claude Code, the agent also updates `HANDOFF.md` when the Stop hook asks (after 3 or more edited files, or when the context passes 250K and 450K tokens and the turn did work since the last handoff), and doesn't commit it (`BATON_HANDOFF_AUTO=off` turns this off). `/baton-setup` writes only `~/.config/baton/config.json`, and only the values you pick.

## Updating and uninstalling

Claude Code (restart after updating):

```bash
claude plugin marketplace update baton
claude plugin update baton@baton
claude plugin uninstall baton@baton        # remove
claude plugin marketplace remove baton     # and forget the marketplace
```

Plugins are read only when Claude Code starts. A window left open keeps running the old version until you restart it. In a window opened on 1.0.2 or later, baton says so once per conversation ("The baton running in this window (…) differs from the installed version (…)"); a window still open on 1.0.1 or a beta has no such notice, so restart it after updating.

Codex:

```bash
codex plugin marketplace upgrade baton
codex plugin remove baton@baton            # remove
codex plugin marketplace remove baton
```

## Background

How the design got here, what was tried and dropped, and what still doesn't work: [docs/NORTH_STAR_배경.md](NORTH_STAR_배경.md) and [docs/NORTH_STAR.md](NORTH_STAR.md) (Korean). Decisions and their reasons: [DECISIONS.md](../DECISIONS.md). Changes per release: [CHANGELOG.md](../CHANGELOG.md).
