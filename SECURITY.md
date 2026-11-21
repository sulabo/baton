# Security Policy

## Supported versions

baton is in beta. Security fixes go into the latest release only.

| Version | Supported |
|---|---|
| Latest `1.0.0-beta.x` release | Yes |
| Anything older | No — please upgrade |

## What counts as a security issue

baton runs hooks inside every Claude Code or Codex session and reads local files such as session logs, `HANDOFF.md`, and `~/.config/baton/config.json`. Please report privately if you find, for example:

- a hook or script that runs commands or code taken from repository content or prompts
- personal data or prompt text leaking into the observation log (`~/.cache/baton/runs.jsonl`), injected context, or files baton writes
- secrets or personal terms that `lib/handoff_check.py` is supposed to block but lets through
- files written with permissions wider than documented (the config and log files should be `600`)

## Reporting a vulnerability

Please **do not open a public issue** for a security problem.

Report it through GitHub's private vulnerability reporting:

1. Go to <https://github.com/sulabo/baton/security/advisories/new> (or the repository's **Security** tab → **Report a vulnerability**).
2. Describe the issue, the affected version, and steps to reproduce. Leave out real secrets or personal data — a placeholder is enough.

Only the maintainers can see the report. We aim to acknowledge reports within 7 days. Once a fix is ready, we will publish an advisory and credit you unless you prefer to stay anonymous.

If the reporting form is not available, open a public issue that says only "Requesting a private security contact" — no details — and the maintainer will reach out.

> 보안 문제는 공개 이슈 대신 위 비공개 신고 양식으로 알려 주세요.
