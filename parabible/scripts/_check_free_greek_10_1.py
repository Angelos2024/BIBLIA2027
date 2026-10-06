#!/usr/bin/env python3
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(r"C:\Users\pik_y\Documents\TRADUCCION\scripts")))
from merge_oshb import _pair_has_free_greek, _gather_assigned_gr, _norm_gr_token

data = json.loads(
    Path(r"C:\Users\pik_y\Documents\TRADUCCION\data\genesis_final.json").read_text(
        encoding="utf-8"
    )
)
v = next(x for x in data["verses"] if x["chapter"] == 10 and x["verse"] == 1)
for i, p in enumerate(v["pairs"]):
    free = _pair_has_free_greek(p)
    assigned = _gather_assigned_gr(p)
    gt = p.get("gr_tokens") or []
    print(f"pair {i}: {p.get('gr_unicode', '')[:30]!r} tokens={len(gt)} free={free}")
    if free or i < 3:
        print("  assigned:", sorted(assigned))
        for t in gt:
            word = _norm_gr_token(t.get("word", ""))
            lemma = _norm_gr_token(t.get("lemma_unicode", ""))
            ok = word in assigned or lemma in assigned
            print(f"    {t.get('word')} / {t.get('lemma_unicode')} -> ok={ok}")
