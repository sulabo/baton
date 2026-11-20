# baton

**English** · [한국어](README.ko.md)

**A Claude Code plugin that finds where your project's decisions, code, and docs disagree, one concept at a time.**
Each concept records the commit it was last checked at, so concepts whose files haven't moved since are never re-read.
It also lints your session handoff (`HANDOFF.md`) on save and injects it when a prompt asks to pick up where you left off.

> `1.0.0-beta.2` · Beta. The plugin's messages and skills are written in Korean (see [Limitations](#limitations)).

<!-- DEMO: 20-second GIF of `/drift` after a commit goes here (docs/demo.gif). Until then, the real output below stands in. -->

```
#    개념                 상태       판정
---- ---------------------- ------------ ------------------------------
1    목숨                 구현됨    재확인 필요 — 커밋 1건
2    점수                 구현됨    신선
3    레벨                 미구현    재확인 필요 — 기준 없음
```

<sub>Real `/drift` output from a demo repo, after one commit changed `src/lives.ts`. Concept 1 (lives) needs a re-check — 1 commit since it was verified. Concept 2 (score) is fresh, so it is skipped. Concept 3 (levels) was never verified — reported as "can't tell", not as zero.</sub>

## Install

In Claude Code:

```
/plugin marketplace add sulabo/baton
/plugin install baton@baton
```

You need `git` and `python3`. In a new session, run `/baton-doctor` to check the repo is ready.
Codex (0.155+): `codex plugin marketplace add sulabo/baton`, then `codex plugin add baton@baton`. Codex runs plugin hooks only after you trust them.

## What it does

### Concept map: `driftmap` and `/drift`

Ask "개념 지도 만들어줘" ("build a concept map"). The `driftmap` skill picks the 8–12 concepts that matter in your project and writes `CONCEPTS.md`.
Each concept is checked from four sides: what was decided (decision log), what the code actually does, where it is documented, and where those three disagree.
A disagreement is often not a stale doc — it can be a decision that was made but never implemented. Comparing docs to docs alone would "fix" a correct doc.

Every concept ends with one metadata line:

```
- **메타**: 상태=구현됨 · 확인=2026-11-20(`9cd1928`) · 파일=`src/lives.ts`, `docs/guide.md` · 이웃=개념 2(전제)
```

That is: status, verified at commit `9cd1928`, the files it depends on, and its neighbors. Freshness is then a computation, not a judgment: if none of those files has a commit after `9cd1928`, the concept is fresh and nobody opens it.
When something did move, the session-start hook prints one line, and `/drift` lists exactly which concepts to revisit. If nothing needs a re-check, the hook stays silent.

There are six verdicts, and four of them are kinds of "can't tell": no baseline, baseline lost to a rebase, path gone, file not tracked (nested repo). A count that silently comes out as zero is treated as a bug, not as "nothing found".

### Handoffs (secondary)

- **Check on save.** When the agent writes `HANDOFF.md`, a hook checks the eight required sections, length limits, large code blocks, diffs, secrets, and home-directory paths, and hands the problems back to the agent. It never echoes the secret it found.
- **Inject on request.** When a prompt asks about progress — by default the Korean words "이어서" (continue), "어디까지" (how far), "인계" (handoff), or the English word "handoff" — the hook puts `HANDOFF.md` into context (up to 200 lines / 9,000 characters) so the agent does not search for and re-read it. Unrelated prompts get nothing.
- **Nudges.** One notice when the context grows past 2× and 3× of the first call, and one suggestion to write a handoff after 3 or more files changed.
- **`/promote`** lists constraints that survived several days of handoffs as candidates for `DECISIONS.md`. It does not write the decision for you: the "why" and the rejected alternatives only exist in the head of whoever decided.

### Commands

| Command | What it does |
|---|---|
| `/drift` | Which concepts need a re-check. Stops at zero |
| `/promote` | Handoff items worth promoting to the decision log |
| `/baton-setup` | Tune thresholds and a private-terms block list from your own session history. Writes only what you pick |
| `/baton-doctor` | Is this repo ready (git, `CONCEPTS.md`, metadata lines, tracked handoff, config) |
| `/baton-explain` | Shows what the rules decide for a prompt. Changes nothing |

Every hook has an off switch (`BATON_HANDOFF_INJECT=off`, `BATON_SPLIT_NOTICE=off`, `BATON_HANDOFF_CHECK=off`, …), as an environment variable or in the config file written by `/baton-setup`.

### Observation log

Hooks append one line per decision to `~/.cache/baton/runs.jsonl` (file mode 600). Prompt text is never stored — only a hash, the length, and the trigger words that matched. Turn it off with `BATON_OBSERVE=off`.

## Measured so far

From the author's own use (one person, 2026-10-04 to 11-20). Commands and sources are in the [CHANGELOG](CHANGELOG.md).

- Sessions that started with a progress question and re-read `HANDOFF.md` within the first 5 calls: **41 of 42 before install, 3 of 11 after** (2 of those 3 read only part).
- 270 handoff injections in 40 sessions. The save-time check returned problems on 20 of 38 saves.
- **Tokens did not go down** in real use: the opening calls cost more after install, because the fixed context grew in the same period and the effect could not be separated. In controlled snapshot runs (same repo, same prompt), progress questions used 40–54% fewer input tokens.

## Limitations

- **Korean UI.** Hook messages, skill instructions, and command output are in Korean. Handoff injection triggers on Korean words and "handoff" only — English "continue" or "where were we" does not trigger it. Add your own words with `/baton-setup` (`BATON_HANDOFF_TRIGGERS_EXTRA`).
- Freshness is per file. An unrelated edit in a listed file still marks the concept for a re-check.
- Only committed history counts. Uncommitted changes are invisible.
- Reversed decisions are not detected automatically. It was tried and removed.
- The first concept map is expensive: every concept needs its metadata line filled in.
- Default thresholds come from a few repositories of one person. `/baton-setup` re-fits them to your history only when this repo has 10 or more Claude Code sessions.
- The handoff checker misses `postgres://user:pw@host` style URLs, `npm_` and `hf_` tokens, and non-JWT Bearer values. It falsely flags long `sk-` branch names and CI runner home paths.
- Codex: the context-growth notice, handoff nudge, and save-time check do not run (different session log format; `apply_patch` gives no path). The skill runs the checker itself.
- Hooks are Python and shell scripts that run on your machine. Read `hooks/` before installing if that matters to you.

## Background

How the design got here, what was tried and dropped, and what still does not work: [docs/NORTH_STAR_배경.md](docs/NORTH_STAR_배경.md) and [docs/NORTH_STAR.md](docs/NORTH_STAR.md) (Korean). Decisions and their reasons: [DECISIONS.md](DECISIONS.md).

## License

MIT
