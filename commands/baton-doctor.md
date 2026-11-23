---
description: Checks whether this plugin is ready to run in this repo. 이 플러그인이 이 저장소에서 돌 준비가 됐는지 점검한다.
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/lib/config.py)
---

Check the following in order, and for **each one that fails, write one line on what to do about it**. Reply in the
user's language.

```bash
git rev-parse --show-toplevel                                    # is this a git repo
find . -maxdepth 2 -name CONCEPTS.md                             # is there a concept map
grep -c -E '^- \*\*(메타|Meta)\*\*:' <that file>                 # does it have metadata lines (none: freshness can't be computed)
git ls-files --error-unmatch HANDOFF.md                          # is the handoff tracked (not tracked: no promotion review)
ls DECISIONS.md                                                  # is there a decision log
python3 ${CLAUDE_PLUGIN_ROOT}/lib/config.py                      # was /baton-setup run, can the config file be read, output language
```

Run the `config.py` line exactly as written (pre-approved, read only). Claude Code fills in the plugin path when it
loads this file; the plugin-root variable is not set in the shell, so don't replace the path with a shell variable.
Don't answer each item only with works / doesn't work. When something doesn't work, write **what it stops from
working**.
No config file means the thresholds are the author's defaults (recommend `/baton-setup`). If it exists but can't be
read, the hooks run without it: have the user fix or delete it.
Report the output language and where it came from, as the last line of `config.py` prints it: the `BATON_LANG`
environment variable, `BATON_LANG` in the config file, the locale (`LC_ALL`, `LC_MESSAGES`, `LANG`), the macOS
language list (`AppleLanguages`, only when no locale variable is set), or the default (English). To change it, set `BATON_LANG` to `ko`, `en` or `auto`, as an environment variable or with
`/baton-setup` (`python3 ${CLAUDE_PLUGIN_ROOT}/lib/setup_scan.py apply --global --set BATON_LANG=…`, which asks before
it writes).
