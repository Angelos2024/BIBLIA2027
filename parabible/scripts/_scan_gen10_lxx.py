#!/usr/bin/env python3
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
data = json.loads(
    Path(r"C:\Users\pik_y\Documents\TRADUCCION\data\genesis_final.json").read_text(
        encoding="utf-8"
    )
)
verses = [v for v in data["verses"] if v.get("chapter") == 10]
gk_adds = []
for v in verses:
    ref = f"10:{v['verse']}"
    for pi, p in enumerate(v.get("pairs", [])):
        if p.get("kind") == "gk_add":
            gk_adds.append(
                {
                    "ref": ref,
                    "pi": pi,
                    "gr": (p.get("gr_unicode") or "").strip(),
                }
            )

mlxx = data.get("_mlxx") or {}
ch10_mlxx = {k: v for k, v in mlxx.items() if k.startswith("10:") or ":10:" in k}

print("verses", len(verses))
print("gk_add in genesis_final ch10:", len(gk_adds))
for x in gk_adds:
    print(" ", x)

print("_mlxx keys for ch10:", len(ch10_mlxx))
for k in sorted(ch10_mlxx, key=lambda x: (int(x.split(":")[0]), int(x.split(":")[1])) if ":" in x else (0, 0))[:15]:
    print(" ", k, "->", (ch10_mlxx[k] or "")[:80])
