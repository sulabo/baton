---
description: Run once after install. Proposes baton thresholds, a private-words list and the output language from your own session history and git history, and writes only what you pick to the config file. 설치 후 한 번. 내 과거 세션 기록·git 이력으로 baton 문턱과 개인 자료 목록을 제안하고, 고른 것만 설정 파일에 쓴다.
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/lib/setup_scan.py), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/lib/config.py)
---

Follow the steps of the `baton-setup` skill. Reply in the user's language.

1. Run `python3 ${CLAUDE_PLUGIN_ROOT}/lib/setup_scan.py` in the current repo, exactly as written (pre-approved). It
   only reads. Claude Code fills in the plugin path when it loads this file; the plugin-root variable is not set in the
   shell, so don't replace the path with a shell variable.
2. Relay the results, and for each item report **what was counted together with what could not be counted**. A 0 may
   mean "could not count", not "none".
3. Use `AskUserQuestion` to let the user pick one thing at a time (recommendation and reason first). Don't write
   anything the user didn't pick.
4. Write only what was picked with `python3 ${CLAUDE_PLUGIN_ROOT}/lib/setup_scan.py apply ...` (not pre-approved: it
   writes the config file, so it asks), and say which keys changed, where, and how to undo it
   (`--unset <key>`, `--remove-terms-file`, `--remove-trigger`; an environment variable wins over the config file).
   Don't put private words on the command line: use `--private-terms-file` or a terminal outside the session (step 4
   of the skill). Tell the user first that the scan output also stays in this conversation's log.

If `$ARGUMENTS` is given, use that path as the repo root (`python3 ${CLAUDE_PLUGIN_ROOT}/lib/setup_scan.py <path>`;
this form is not pre-approved, so it asks).
