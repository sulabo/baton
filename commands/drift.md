---
description: Freshness check of the concept map. Computes which concepts need a re-check, then stops. (개념 지도 신선도 점검 — 재확인 대상만 계산하고 끝낸다.)
---

Run `$CLAUDE_PLUGIN_ROOT/lib/fresh.sh` on the current repo's `CONCEPTS.md`.

Reply in the user's language. `fresh.sh` prints in English or Korean (`BATON_LANG`, then the system locale) and reads a `CONCEPTS.md` written in either language.

1. Find `CONCEPTS.md`. If there is none, point to mode ① (first build) of the `driftmap` skill and stop.
2. Run `fresh.sh <path> <repo root>`.
3. Pass the result on as it is, but **always report what could not be counted along with it.**
   - If there are 0 metadata lines, that is not "0 stale" but "can't be computed".
   - Not tracked, path gone and baseline lost each need a different response.
4. If nothing needs a re-check, stop there. That is the complete report.

If `$ARGUMENTS` is given, use that path as the target.
