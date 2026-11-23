---
name: baton-setup
description: 설치 후 한 번 돌리는 개인화. 이 사용자의 과거 세션 기록·git 이력·인계서를 읽어 baton 문턱(세션 끊기 알림·인계서 제안)과 인계 트리거 말, 인계서 검사가 막을 개인 자료 목록, 출력 언어를 그 사람 분포로 제안하고, 사용자가 고른 것만 설정 파일에 쓴다. "baton 설정해줘", "baton setup", "문턱 내 기록으로 맞춰줘", "개인 자료 목록 만들어줘"에도 발동. Also triggers on English requests such as "set up baton", "tune baton thresholds to my history", "build my private terms list", "set baton's language".
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/lib/setup_scan.py), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/lib/config.py)
---

# Baton Setup — tune baton to your own history

Reply in the user's language. The scanner prints its report in the output language (`BATON_LANG`, otherwise the
locale); relay it in the language the user writes in. This skill writes no `HANDOFF.md` or `CONCEPTS.md`, only the
config file.

## Purpose

baton's thresholds were set on a few of the author's repos. The context-growth notice at 2× and 3× comes from 60
sessions, where "85% of the cost was spent after the context passed 2× the first call". The handoff nudge at 3 files
comes from 94 sessions, where "sessions that edited 1–2 files wrote a handoff 16% of the time, sessions with 3 or more
67%". **Whether other people split at the same points is unknown.**

This skill runs the same methods on **this user's history** and proposes thresholds. It also picks out candidate words
that belong only to this person and must not leak into a handoff (names, emails, other project names), so the handoff
check blocks the ones the user picks. It also proposes the output language from the language of the user's prompts.

**Nothing changes until the user picks.** The scanner only reads.

## Steps

### 1. Scan (read only)

Run it from anywhere inside the repo. The config section is keyed by the git top-level folder, and the hooks find it
with the same function, so the same section applies when Claude Code is opened in a subfolder. A git worktree has its
own top level, so it gets its own section.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/lib/setup_scan.py
```

Run it exactly as written, with no arguments: that form is pre-approved in `allowed-tools`. Claude Code fills in the
plugin path when it loads this file (the plugin-root variable is not set in the shell, so don't replace the path with
a shell variable). `apply` (step 4) writes the config file and is not pre-approved, so it still asks.

What it reads: Claude Code session logs opened at this repo's top level (`~/.claude/projects`), the git author, tracked
files and untracked files that are not ignored (`git grep --untracked`), the working-folder names in other projects'
session logs (as project-name candidates), and `HANDOFF.md`, `DECISIONS.md`, `CONCEPTS.md`.
What it writes: nothing. It doesn't put prompts in the observation log (`~/.cache/baton/runs.jsonl`) either.

**Tell the user first where private data ends up.** When the skill runs the scanner, its output (private-word
candidates, trigger phrase candidates) goes into the agent's context and the Claude Code session log
(`~/.claude/projects`). If the user doesn't want that, have them run it themselves **in another terminal outside the
session** (a command with the `!` prefix also puts its output into the conversation).

### 2. Show the results in the user's language

Relay the seven items of the output as they are, and for each item say **what was counted and what could not be
counted**.

| Item | What | Config key |
|---|---|---|
| 1) Context-growth thresholds | Per session, largest context ÷ first-call context; for each candidate threshold, the sessions that reach it and the cost left after it | `BATON_SPLIT_RATIOS` |
| 2) Handoff nudge threshold | How often a handoff was written, by number of edited files | `BATON_HANDOFF_NUDGE_FILES` |
| 3) Handoff names actually written | Whether names the injection hook doesn't read, such as `HANDOFF-x.md`, were used | none (report only) |
| 4) Extra trigger phrases | Phrases that often appeared in the first prompt of sessions where the agent read the handoff but no current trigger matched | `BATON_HANDOFF_TRIGGERS_EXTRA` |
| 5) Private-word candidates | git author and email, OS user name, other project names that appear in this repo's files, emails in files | `private_terms` |
| 6) Repo advice | Whether `HANDOFF.md` is tracked, whether `DECISIONS.md` and `CONCEPTS.md` exist | none (report only) |
| 7) Output language | Human prompts that contain Korean vs. other languages; the language in effect now and where it came from | `BATON_LANG` |

When you relay:

- **Don't call 0 "none".** If no session logs were found, that is "could not count", not "0". The scanner prints that
  distinction; relay that line.
- **With fewer than 10 sessions, recommend the default thresholds**, and say why (a few sessions can swing them by chance).
- For trigger candidates, always show "also matches N other prompts". The hook checks **every prompt**, not only the
  first one of a session, as a substring, so the handoff also goes into that many prompts that have nothing to do with
  a handoff (injecting it into an unrelated task cost +11% tokens, loop 1). It is an upper bound: some of those may be
  correct injections.
- When a threshold proposal is "no change", also say the value in effect now. It does not mean that a value already
  set should be removed.
- The "recomputed saving" of the context-growth notice is a counterfactual upper-bound estimate. Don't present it as
  a measurement.
- Codex sessions are not counted. When the scanner says so, relay it as is.
- The language proposal counts prompts, not characters: a prompt that contains Korean counts as Korean, a prompt with
  letters but no Korean counts as another language, a prompt with no letters is not counted. More than half Korean
  proposes `ko`, less than half proposes `en`, exactly half proposes nothing. When the language already comes from
  `BATON_LANG` with the same value, it proposes nothing; when it only comes from the locale, it proposes writing it
  so the language stays the same where the locale is different or not set.

### 3. Let the user pick

Ask with `AskUserQuestion` on Claude Code, in plain text on Codex. **One thing at a time**, with the recommendation
and its reason first.

1. The two thresholds: the scanner's proposal / keep the default. If the proposal is "keep the default", skip the
   question.
2. Extra trigger phrases: pick from the candidates (several allowed) / add none.
3. Private-words list: pick from the candidates (several allowed) / type your own / add none.
4. Output language: the scanner's proposal / keep. If the proposal is "no change", skip the question.
5. Scope: this repo only (default) / all repos (global). The output language is about the person, not the repo, so
   recommend global for `BATON_LANG`.

**Don't write anything the user didn't pick.** Don't change a default without asking.

### 4. Write only what was picked

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/lib/setup_scan.py apply \
  --set BATON_SPLIT_RATIOS=2.5,3.5 --set BATON_HANDOFF_NUDGE_FILES=4 --trigger "지난번"
python3 ${CLAUDE_PLUGIN_ROOT}/lib/setup_scan.py apply --global --set BATON_LANG=en
```

- **Don't put private words on the command line.** `--private-term 홍길동` leaves that command in the session log.
  Offer the user two ways: (a) the user writes the picked words in a file, one per line, and you pass it with
  `--private-terms-file <path>`; (b) the user runs `python3 <plugin path>/lib/setup_scan.py apply --private-terms-file -`
  in a terminal outside the session and types the words. If the user says it is fine for the words to stay in the
  conversation, `--private-term` may be used.
- **Keep the word file outside the repo** (for example in the home folder). If it was created inside the repo, delete
  it after apply: once committed, the words it was meant to block are public. Save the file as UTF-8 (a BOM is
  stripped when read).
- To write to the global section, add `--global`. `BATON_OBSERVE` and `BATON_LOG` go only in the global section.
- The keys are the existing environment variable names, and each value is checked per key: threshold ratios are
  numbers of 1 or more separated by commas, the file count is a whole number of 1 or more, switches are on/off
  (1/0, true/false, yes/no), `BATON_LANG` is ko, en or auto (auto follows the locale), trigger phrases and private
  words are at least two characters. A value that breaks a rule is not written, and apply stops.
- If the config file is broken, apply stops without overwriting it. Tell the user, and have them fix or delete it.

### 5. Say what changed and how to undo it

- What was written where: this repo's section or the global section of `~/.config/baton/config.json` (or
  `$XDG_CONFIG_HOME/baton/config.json`), with keys and values.
- Don't print private words again. Say only "N words on the private-words list".
- To undo: a key with `apply --unset <key>`; to remove single list entries, `apply --remove-terms-file <path|->` or
  `apply --remove-trigger <phrase>` (add `--global` for the global section). Pass private words to remove in a file,
  not on the command line, too. Removal ignores case. When the output says "removed M of N" and "still in another
  section and still applies", relay it as is.
- An environment variable with the same name wins over the config file. To turn something off or try a value for a
  while, an environment variable is the fastest way.
- The values in effect now, including the output language and where it came from, are shown by
  `python3 ${CLAUDE_PLUGIN_ROOT}/lib/config.py` (pre-approved, read only).

## Order of precedence

**Environment variable > this repo's section > global section > code default.** For the list keys (`private_terms`,
`BATON_HANDOFF_TRIGGERS_EXTRA`), the repo list is added to the global list (if the `BATON_HANDOFF_TRIGGERS_EXTRA`
environment variable is set, only its comma-separated entries are used). For the output language, when `BATON_LANG`
is not set (or is `auto`), the locale decides (`LC_ALL`, `LC_MESSAGES`, `LANG`; a value starting with `ko` means
Korean), and without a locale it is English.

## Don't

- Write a value the user didn't pick
- Push to change a threshold when the sample is small
- Report what could not be counted as 0 or "none"
- Repeat private words in a summary or report, or put them on the command line without the user's consent
- Edit the config file by hand (the scanner's `apply` keeps mode 600, writes through a temporary file, and keeps
  other repos' sections)

## Limits (honestly)

- **Only Claude Code session logs are counted.** This repo's code doesn't read the Codex session file format yet.
- **Only sessions opened at the repo's top level are counted.** Sessions opened in a subfolder are not in the
  distribution (the config still applies in subfolders).
- **Private data can stay in this conversation.** The scan output and the apply command line go into the session log;
  see "where private data ends up" above.
- The threshold rules carry over the methods that set the defaults, but the original measurements still come from a
  few repos and one person. The original 94-session measurement of the handoff nudge counted experiment and SDK
  sessions in the denominator, while the scanner counts only interactive sessions, so the value can differ even for
  the same person.
- Trigger candidates are word groups with particles left on. '계속해' and '계속' are counted separately.
- Private-word candidates are a heuristic. A name that is also a common word can block the wrong text, so check when
  picking.
- The language proposal looks only at the prompts of this repo's sessions. Pasted text (error output, documents) is
  part of a prompt and counts toward its language.
