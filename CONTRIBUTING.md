# Contributing to baton

Thanks for helping. baton is a Claude Code (and Codex) plugin that tracks where decisions, code, and docs drift apart, and hands sessions over with only what the next one needs. This guide covers how to set up, test, try your change as an installed plugin, and send a pull request.

> 한국어로 이슈·PR을 남겨도 됩니다. Issues and pull requests in Korean are welcome too.

## Before you start

- **Bugs and small fixes**: open a pull request directly, or file a [bug report](https://github.com/sulabo/baton/issues/new?template=bug_report.yml) first if you are not sure it is a bug.
- **New features or behavior changes**: open a [feature request](https://github.com/sulabo/baton/issues/new?template=feature_request.yml) first. Hooks run inside every session, so a change that adds output or context needs a reason and, ideally, a measurement.
- **Security issues**: do not open a public issue. See [SECURITY.md](SECURITY.md).

## Development setup

baton has no third-party dependencies. You need:

- `git`
- `bash`
- Python 3 (standard library only)
- Claude Code and/or Codex, if you want to try the plugin end to end

```bash
git clone https://github.com/sulabo/baton.git
cd baton
```

Layout:

| Path | What lives there |
|---|---|
| `hooks/` | Hook entry points (`hooks.json`) and their tests |
| `lib/` | Shared logic the hooks, commands, and skills call (`rules.py`, `config.py`, `handoff_check.py`, `fresh.sh`, …) |
| `skills/` | `baton`, `driftmap`, `baton-setup` skills |
| `commands/` | Claude Code slash commands (`/drift`, `/promote`, `/baton-doctor`, …) |
| `tools/` | Developer tools such as `stage-plugin.sh` |
| `observer/` | Research and measurement scripts behind the numbers in the README |
| `docs/` | Design notes and research logs |

## Running the tests

Tests use `unittest` and live next to the code they test. Run every suite from the repository root:

```bash
for d in lib hooks tools observer/research; do
  python3 -m unittest discover -s "$d" -p 'test_*.py' || exit 1
done
```

Or a single suite, verbosely:

```bash
python3 -m unittest discover -s hooks -p 'test_*.py' -v
```

A few tests are **skipped on purpose** in a fresh clone: they need local-only experiment data (`.data/`, `observer/research/cases.json`) that is not published. A skip is reported with its reason; a skip is fine, a failure is not.

## Trying your change as an installed plugin

Installing a local marketplace copies the plugin root wholesale. Do not point Claude Code or Codex at your working tree directly — git-ignored data (`.data/`, `.omc/`, `.git`) would be copied into the plugin cache. Stage a clean copy first:

```bash
tools/stage-plugin.sh            # copies tracked + non-ignored files to ~/.cache/baton/plugin
```

Then install from that copy.

Claude Code:

```bash
/plugin marketplace add ~/.cache/baton/plugin
/plugin install baton@baton
```

Codex:

```bash
codex plugin marketplace add ~/.cache/baton/plugin
codex plugin add baton@baton
```

After you change something, run `tools/stage-plugin.sh` again, then:

- Claude Code: `/plugin marketplace update baton`
- Codex: `codex plugin remove baton@baton` then `codex plugin add baton@baton` (Codex only upgrades Git marketplaces)

If you already have baton installed from GitHub, remove it first so you know which copy is running. `/baton-doctor` shows whether the plugin is ready in the current repository.

## Commits and pull requests

- Branch from `main`; one topic per pull request.
- Commit subject: `area: short summary` (for example `hooks: skip injection when HANDOFF.md is empty`). Use the part of the plugin you touched, such as `hooks`, `lib`, `driftmap`, `docs`, or `decisions`. English or Korean are both fine.
- Run the full test suite before you push, and paste the summary lines (`Ran N tests … OK`) into the pull request.
- Add or update a test for any behavior change. A fix should come with a test that fails without it.
- If you change user-facing behavior, update the README and the command or skill text that describes it.
- Do not commit personal data: names, emails, other project names, absolute home paths, session logs, or secrets. If you edit `HANDOFF.md`, run `python3 lib/handoff_check.py HANDOFF.md` — it checks for secrets and home paths among other things.
- Keep `.data/`, `.omc/`, and other ignored folders out of commits.

## Design principles

These are the rules the code already follows. Pull requests are reviewed against them.

1. **No silent zeros.** `git log` on a missing path, a `sed` pattern that matches nothing, a regex that skips non-ASCII paths — all of these return an empty result without an error. A check that finds nothing must also say what it could not count (for example "5 files in an unrecognized format were skipped"), so that "none found" and "could not look" never read the same.
2. **Quiet unless there is something to say.** Hooks speak only when they found something worth acting on. An alarm that rings every session gets ignored.
3. **Every hook has an off switch.** New hook behavior gets a `BATON_*` variable to disable it, and any threshold it uses is configurable.
4. **Humans write the "why".** baton drafts `DECISIONS.md` candidates but never fills in the reason or the rejected alternatives. Those exist only in the head of whoever decided, and a guessed reason is worse than an empty one.
5. **Measure, and say what kind of number it is.** Claims in docs carry their source and label: real-use measurement, snapshot experiment, or estimate from past logs.
6. **Do not log what people typed.** The observation log stores hashes, lengths, and matched rule words, never prompt text.
7. **Add as little context as possible.** Every line a hook injects costs tokens in every turn after it. Prefer not injecting over injecting something partly relevant.

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). By participating you agree to uphold it.
