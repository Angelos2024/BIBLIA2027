import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "dump_v.txt"
data = json.loads(Path("../data/genesis_final.json").read_text(encoding="utf-8"))
lines: list[str] = []
for vn in (6, 10, 13, 18, 23, 26, 27, 30, 31, 32):
    v = next(x for x in data["verses"] if x.get("chapter") == 5 and x.get("verse") == vn)
    lines.append(f"\n5:{vn}")
    for pi, p in enumerate(v["pairs"]):
        hws = p.get("he_words") or []
        if not hws:
            lines.append(f"  p{pi} EMPTY")
            continue
        for hi, hw in enumerate(hws):
            lines.append(f"  p{pi}h{hi} {hw.get('raw')} | {hw.get('he_form')} | {hw.get('he_morph')}")
OUT.write_text("\n".join(lines), encoding="utf-8")
