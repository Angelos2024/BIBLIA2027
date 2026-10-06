#!/usr/bin/env python3
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(r"C:\Users\pik_y\Documents\TRADUCCION\scripts")))
sys.stdout.reconfigure(encoding="utf-8")

from audit_gen_chapter_lxx import _norm_gr, _tokens_from_phrase, _gather_assigned, _pair_source_tokens

GEN = Path(r"C:\Users\pik_y\Documents\TRADUCCION\data\genesis_final.json")
LXX = Path(
    r"C:\Users\pik_y\Documents\GitHub\Local-consults\estudio\angelos"
    r"\LXX\chapters\Gen\10.json"
)

data = json.loads(GEN.read_text(encoding="utf-8"))
v = next(x for x in data["verses"] if x["chapter"] == 10 and x["verse"] == 1)
lxx = json.loads(LXX.read_text(encoding="utf-8"))["verses"]["1"]

print("=== LXX Rahlfs (17 palabras) ===")
print(" ".join(w["w"] for w in lxx))

print("\n=== genesis_final pairs ===")
all_gr = []
all_assigned = []
for pi, p in enumerate(v["pairs"]):
    kind = p.get("kind", "align")
    gr = (p.get("gr_unicode") or "").strip()
    src = _tokens_from_phrase(gr)
    all_gr.extend(src)
    assigned = _gather_assigned(p)
    ass_toks = [a[0] for a in assigned]
    all_assigned.extend(ass_toks)
    he = (p.get("he_unicode") or p.get("he_note") or "—")[:40]
    print(f"\n[{pi}] kind={kind} he={he!r}")
    print(f"     gr_unicode: {gr!r}")
    print(f"     src_tokens: {src}")
    print(f"     assigned:   {ass_toks}")
    if src and not ass_toks and kind == "align":
        print("     *** GR sin asignar en he_words ***")
    for hi, hw in enumerate(p.get("he_words") or []):
        print(
            f"       hw[{hi}] raw={hw.get('raw')} he={hw.get('he_form')} "
            f"gr_word={hw.get('gr_word')!r} prefix_gr={hw.get('prefix_gr')}"
        )

print("\n=== RESUMEN ===")
lxx_toks = [_norm_gr(w["w"]) for w in lxx]
print("LXX tokens:", lxx_toks)
print("pair gr tokens:", all_gr)
print("assigned tokens:", all_assigned)
from collections import Counter
print("LXX - pair:", Counter(lxx_toks) - Counter(all_gr))
print("pair - assigned:", Counter(all_gr) - Counter(all_assigned))
