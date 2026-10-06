"""
validate_morph_genesis.py  —  PASO 4  (validación morfológica)

Compara `he_morph` de genesis_final.json con la referencia OSHB
(oshb-morph de angelos, misma convención que el pipeline).

Salida:
  - scripts/validate_morph_genesis.csv
  - Resumen en consola

NO modifica he_morph. Para anotar el JSON, ejecutar apply_corrections.py
(Global Pass 13 añade morph_audit / morph_ref sin sobrescribir).
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# Importar utilidades del mismo directorio
sys.path.insert(0, str(Path(__file__).resolve().parent))
from morph_validate_utils import (  # noqa: E402
    compare_morph,
    fold_he,
    load_verse_morph_map,
    lookup_verse_morph,
    morph_pos_root,
    normalize_morph,
    normalize_strong,
)

ROOT = Path(r"C:\Users\pik_y\Documents\TRADUCCION")
GEN_JSON = ROOT / "data" / "genesis_final.json"
OSHB_DIR = Path(
    r"C:\Users\pik_y\Documents\GitHub\Local-consults\estudio\angelos"
    r"\IdiomaORIGEN\oshb-morph\chapters\01_Génesis"
)
OUT_CSV = ROOT / "scripts" / "validate_morph_genesis.csv"


def _ref_from_verse(v: dict) -> str:
    if v.get("ref"):
        # "Gen 1:1" → "1:1"
        parts = str(v["ref"]).replace("Gen", "").strip().split()
        if parts:
            return parts[-1]
    return f"{v.get('chapter', '')}:{v.get('verse', '')}"


def main() -> None:
    print("== PASO 4 — Validación morfológica (Génesis) ==")
    print(f"  JSON: {GEN_JSON.name}")
    print(f"  Ref:  {OSHB_DIR}")

    data = json.loads(GEN_JSON.read_text(encoding="utf-8"))
    verse_map = load_verse_morph_map(OSHB_DIR)
    print(f"  Versos OSHB cargados: {len(verse_map)}")

    rows = []
    cat_counts: Counter = Counter()
    conflict_by_root: Counter = Counter()

    for v in data.get("verses", []):
        ref = _ref_from_verse(v)
        for pi, pair in enumerate(v.get("pairs", [])):
            for hi, hw in enumerate(pair.get("he_words", []) or []):
                raw = hw.get("raw", "") or ""
                he_form = hw.get("he_form", "") or ""
                he_morph = hw.get("he_morph", "") or ""
                strongs = normalize_strong(hw.get("strongs", "") or "")

                ref_morph = ""
                ref_source = ""
                status = "NO_REF"
                note = ""

                if not he_morph.strip():
                    status = "EMPTY_OURS"
                    note = "sin he_morph"
                elif not fold_he(he_form):
                    status = "NO_REF"
                    note = "sin he_form para emparejar"
                else:
                    hit = lookup_verse_morph(verse_map, ref, he_form)
                    if hit:
                        ref_morph, ref_source = hit
                        status = compare_morph(he_morph, ref_morph)
                        if status == "minor" and normalize_morph(he_morph) != ref_morph:
                            if "." not in he_morph and "." in ref_morph:
                                note = "formato_corto"
                    else:
                        status = "NO_REF"
                        note = "forma no encontrada en oshb-morph del versículo"

                cat_counts[status] += 1
                if status == "conflict":
                    conflict_by_root[
                        f"{morph_pos_root(he_morph)}→{morph_pos_root(ref_morph)}"
                    ] += 1

                rows.append({
                    "ref": ref,
                    "par_idx": pi,
                    "hw_idx": hi,
                    "raw": raw,
                    "he_form": he_form,
                    "he_morph": he_morph,
                    "he_morph_norm": normalize_morph(he_morph),
                    "strongs": strongs,
                    "ref_morph": ref_morph,
                    "ref_morph_norm": normalize_morph(ref_morph),
                    "ref_source": ref_source,
                    "status": status,
                    "note": note,
                })

                # Prefijos (misma lógica)
                pfx_forms = hw.get("prefix_forms", []) or []
                pfx_morphs = hw.get("prefix_morphs", []) or []
                for ki, (pf, pm) in enumerate(zip(pfx_forms, pfx_morphs)):
                    if not pm.strip():
                        continue
                    hit_p = lookup_verse_morph(verse_map, ref, pf)
                    if hit_p:
                        rm, rs = hit_p
                        st = compare_morph(pm, rm)
                    else:
                        rm, rs, st = "", "", "NO_REF"
                    cat_counts[f"prefix:{st}"] += 1
                    if st == "conflict":
                        rows.append({
                            "ref": ref,
                            "par_idx": pi,
                            "hw_idx": hi,
                            "raw": f"{raw}[pfx{ki}]",
                            "he_form": pf,
                            "he_morph": pm,
                            "he_morph_norm": normalize_morph(pm),
                            "strongs": strongs,
                            "ref_morph": rm,
                            "ref_morph_norm": normalize_morph(rm),
                            "ref_source": rs,
                            "status": f"prefix:{st}",
                            "note": "prefijo",
                        })

    fieldnames = [
        "ref", "par_idx", "hw_idx", "raw", "he_form",
        "he_morph", "he_morph_norm", "strongs",
        "ref_morph", "ref_morph_norm", "ref_source",
        "status", "note",
    ]
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
        wr.writeheader()
        wr.writerows(rows)

    total = len(rows)
    print("\n========== RESUMEN PASO 4 ==========")
    print(f"Filas en CSV (incl. prefijos con conflicto): {total}")
    stem_total = sum(cat_counts.get(k, 0) for k in ("exact", "minor", "conflict", "NO_REF", "EMPTY_OURS"))
    for key in ("exact", "minor", "conflict", "NO_REF", "EMPTY_OURS"):
        n = cat_counts.get(key, 0)
        pct = 100.0 * n / stem_total if stem_total else 0.0
        print(f"  {key:<12} {n:>6}  ({pct:5.1f}%)")
    print("\nTop conflictos POS (nuestro → referencia):")
    for pair, n in conflict_by_root.most_common(12):
        print(f"  {pair:<28} {n}")

    conflicts = [r for r in rows if r["status"] == "conflict"]
    print("\nEjemplos de conflicto (máx. 8):")
    for r in conflicts[:8]:
        print(
            f"  Gen {r['ref']:>6} raw={r['raw']:<10} "
            f"{r['he_morph']:<28} ref={r['ref_morph']:<28} [{r['note']}]"
        )

    print(f"\nCSV → {OUT_CSV}  ({OUT_CSV.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
