#!/usr/bin/env python3
"""세션 시작 상태 카드 — 직전 HANDOFF.md에서 세 절만 뽑는다.

절: 목표·완료 조건 / 관련 파일 / 실패한 접근법(다시 시도 금지).
크기: 기본 3072바이트(UTF-8) 안. 넘치면 실패 절 → 파일 절 순으로 뒤에서 줄을 덜어낸다.
용도: SessionStart 훅의 stdout으로 주입한다. 인계서 재독을 대신하는 것이 목적이므로
      "인계서를 다시 읽어라"는 말은 넣지 않는다.

사용: python3 card.py <HANDOFF.md> [--limit 3072] [--with-next]
  --with-next  "다음 행동(남은 리스크와 다음 행동)" 절을 넣는다. 한도는 함께 올려 준다(예: --limit 6144).
후보 E(2라운드 A/B)용. 절 제목 정규식은 observer/research/round1_e.py와 같다.
"""
import re, sys, os

SEC_GOAL  = re.compile(r"^#+.*(목표|완료 조건)")
SEC_FILES = re.compile(r"^#+.*관련 파일")
SEC_NEVER = re.compile(r"^#+.*(실패한 접근|다시 시도 금지|다시 하지 말)")
SEC_NEXT  = re.compile(r"^#+.*(다음 행동|남은 리스크)")
ORDER = (SEC_GOAL, SEC_FILES, SEC_NEVER)          # 3절 카드 (2라운드 'on' arm)
ORDER4 = (SEC_GOAL, SEC_NEXT, SEC_FILES, SEC_NEVER)  # 4절 카드 (--with-next): 다음 행동 포함

def split_sections(text):
    secs, cur, body = [], None, []
    for ln in text.splitlines():
        if ln.startswith("#"):
            if cur is not None: secs.append((cur, body))
            cur, body = ln, []
        else:
            body.append(ln)
    if cur is not None: secs.append((cur, body))
    return secs

def pick(text, order=ORDER):
    """절을 order 순서로. 같은 종류가 여럿이면 처음 것만."""
    got = {}
    for head, body in split_sections(text):
        for i, rx in enumerate(order):
            if i not in got and rx.search(head):
                lines = [l.rstrip() for l in body]
                while lines and not lines[-1]: lines.pop()
                while lines and not lines[0]: lines.pop(0)
                got[i] = (head.lstrip("#").strip(), lines)
    return [got[i] for i in range(len(order)) if i in got]

def render(sections, title):
    out = [title, ""]
    for head, lines in sections:
        out.append("### " + head)
        out.extend(lines)
        out.append("")
    return "\n".join(out).rstrip() + "\n"

def build(text, source, limit, with_next=False):
    order = ORDER4 if with_next else ORDER
    secs = pick(text, order)
    if not secs:
        return None
    first = text.splitlines()[0] if text else ""
    m = re.search(r"작성:\s*([0-9-]+)", first)
    stamp = m.group(1) if m else "날짜 미상"
    names = "목표·다음 행동·관련 파일·다시 하지 말 것 네 절" if with_next else "목표·관련 파일·다시 하지 말 것 세 절"
    # 2라운드 실측: "카드가 전문이다"만으로는 인계서를 다시 연다(5/5). 전문 주입에 붙인
    # "파일을 다시 열 필요 없다. 그대로 이어서 진행한다"가 0/5를 만들었으므로 같은 문장을 쓴다.
    title = (f"[baton 카드] 직전 인계서({os.path.basename(source)}, 작성 {stamp})의 "
             f"{names}을 그대로 옮긴 것이다. 파일을 다시 열 필요 없다. 그대로 이어서 진행한다.")
    card = render(secs, title)
    # 넘치면 뒤 절부터 한 줄씩 덜어낸다. 목표 절(과 다음 행동 절)은 안 건드린다.
    trimmed = False
    for idx in reversed(range(2 if with_next else 1, len(secs))):
        while len(card.encode("utf-8")) > limit and idx < len(secs) and secs[idx][1]:
            secs[idx][1].pop(); trimmed = True
            card = render(secs, title)
    if trimmed:
        card = card.rstrip() + "\n(카드 크기 한도로 뒷부분 생략)\n"
    return card

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    limit = 3072
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    if not args:
        print(__doc__, file=sys.stderr); sys.exit(2)
    path = args[0]
    if not os.path.isfile(path):
        sys.exit(0)  # 인계서가 없으면 조용히. 훅에서 실패로 보이면 안 된다.
    text = open(path, encoding="utf-8").read()
    card = build(text, path, limit, with_next="--with-next" in sys.argv)
    if card is None:
        sys.exit(0)  # 세 절 중 하나도 없으면 카드 없음 — 침묵
    sys.stdout.write(card)

if __name__ == "__main__":
    main()
