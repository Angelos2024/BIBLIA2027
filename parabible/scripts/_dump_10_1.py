#!/usr/bin/env python3
import json
from pathlib import Path

data = json.loads(Path(r"C:\Users\pik_y\Documents\TRADUCCION\data\genesis_final.json").read_text(encoding="utf-8"))
v = next(x for x in data["verses"] if x["chapter"] == 10 and x["verse"] == 1)
lxx = "αὗται δὲ αἱ γενέσεις τῶν υἱῶν Νωε Σημ Χαμ Ιαφεθ καὶ ἐγενήθησαν αὐτοῖς υἱοὶ μετὰ τὸν κατακλυσμόν".split()
print("Expected LXX tokens:", len(lxx), lxx)
print()
for i, p in enumerate(v["pairs"]):
    gr = (p.get("gr_unicode") or "").strip()
    if not gr:
        continue
    kind = p.get("kind", "align")
    print(f"=== pair {i} kind={kind} gr={gr!r} ===")
    for j, hw in enumerate(p.get("he_words") or []):
        print(
            f"  hw{j}: he={hw.get('he_form') or hw.get('full_unicode')!r} "
            f"gr_word={hw.get('gr_word')!r} prefix_gr={hw.get('prefix_gr')}"
        )
