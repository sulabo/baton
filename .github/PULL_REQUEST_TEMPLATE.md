## What and why

<!-- What does this change, and what problem does it solve? Link the issue: "Fixes #123". -->

## How it was tested

<!-- Paste the summary lines from the test run, e.g. "Ran 83 tests ... OK". -->

```text
$ for d in lib hooks tools observer/research; do python3 -m unittest discover -s "$d" -p 'test_*.py' || exit 1; done

```

<!-- If you tried it as an installed plugin (tools/stage-plugin.sh), say in which host: Claude Code / Codex. -->

## Checklist

- [ ] Tests pass locally, and new or changed behavior has a test
- [ ] Checks that can find nothing also report what they could not count (no silent zeros)
- [ ] New hook behavior has a `BATON_*` off switch and stays quiet when there is nothing to say
- [ ] README and command/skill text updated if user-facing behavior changed
- [ ] No personal data, secrets, absolute home paths, or local-only data (`.data/`, `.omc/`) in the diff

<!-- 한국어로 써도 됩니다. -->
