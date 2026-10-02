---
description: 이 플러그인이 이 저장소에서 돌 준비가 됐는지 점검한다.
---

아래를 순서대로 확인하고 **안 되는 것마다 무엇을 하면 되는지** 한 줄씩 적어라.

```bash
git rev-parse --show-toplevel                      # git 저장소인가
find . -maxdepth 2 -name CONCEPTS.md               # 개념 지도가 있는가
grep -c '^- \*\*메타\*\*:' <그 파일>                # 메타 줄이 있는가 (없으면 신선도 불가)
git ls-files --error-unmatch HANDOFF.md            # 인계서가 추적되는가 (안 되면 승격 불가)
ls DECISIONS.md                                     # 결정 기록이 있는가
python3 "$CLAUDE_PLUGIN_ROOT/lib/config.py"         # /baton-setup을 돌렸는가, 설정 파일이 읽히는가
```

각 항목은 **된다/안 된다**로만 답하지 말고, 안 되면 그것 때문에 **무엇을 못 하게 되는지**를 적는다.
설정 파일이 없으면 문턱이 만든 사람의 기본값이라는 뜻이다(`/baton-setup` 권고). 있는데 못 읽으면 훅은 설정 없이 돈다 — 고치거나 지우게 한다.
