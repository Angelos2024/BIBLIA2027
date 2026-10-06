#!/usr/bin/env python3
"""Re-aplica parches cap. 10 v1 y guarda genesis_final."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(r"C:\Users\pik_y\Documents\TRADUCCION\scripts")))
sys.stdout.reconfigure(encoding="utf-8")

from apply_corrections import _fix_gen10_oshb_align, _fix_gen10_lxx_align

GEN = Path(r"C:\Users\pik_y\Documents\TRADUCCION\data\genesis_final.json")
data = json.loads(GEN.read_text(encoding="utf-8"))
v = next(x for x in data["verses"] if x.get("chapter") == 10 and x.get("verse") == 1)
_fix_gen10_oshb_align(v)
_fix_gen10_lxx_align(v)
GEN.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print("pair 8 kind:", v["pairs"][8].get("kind"), "gr:", v["pairs"][8].get("gr_unicode"))
