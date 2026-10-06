"""
Paso 5.2 — Verificar texto hebreo completo vs tokens del sitio

Compara la cadena concatenada de oshb-morph con la del JSON (prefijos+stems+sufijos).
Reporta versículos OK, divergencia de consonantes, o longitud distinta.
"""
from __future__ import annotations

import csv
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paso5_utils import (  # noqa: E402
    SCRIPTS,
    add_book_arg,
    fold_he,
    load_active,
    oshb_concatenated,
    parse_ref,
    set_active_book,
    site_concatenated,
    verse_ref,
)

OUT_CSV = SCRIPTS / "paso5_2_verify_hebrew_text.csv"


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    add_book_arg(ap)
    args = ap.parse_args()
    set_active_book(args.book)

    print(f"== PASO 5.2 — Texto hebreo completo OSHB vs sitio [{args.book}] ==")
    data = load_active()
    rows = []
    counts: Counter = Counter()

    for v in data.get("verses", []):
        ref = verse_ref(v)
        try:
            ch, vs = parse_ref(ref)
        except ValueError:
            continue
        oshb_plain = fold_he(oshb_concatenated(ch, vs, with_maqaf=False))
        site_plain = fold_he(site_concatenated(v, with_maqaf=False))
        oshb_maq = fold_he(oshb_concatenated(ch, vs, with_maqaf=True))
        site_maq = fold_he(site_concatenated(v, with_maqaf=True))

        if not oshb_plain:
            status = "NO_OSHB"
        elif oshb_plain == site_plain:
            status = "OK"
        elif oshb_maq == site_maq:
            status = "OK_MAQAF_ONLY"
        elif oshb_plain in site_plain or site_plain in oshb_plain:
            status = "SUBSTRING"
        else:
            # primer punto de divergencia
            status = "MISMATCH"
            for i, (a, b) in enumerate(zip(oshb_plain, site_plain)):
                if a != b:
                    break
            else:
                i = min(len(oshb_plain), len(site_plain))

        counts[status] += 1
        rows.append({
            "ref": ref,
            "status": status,
            "len_oshb": len(oshb_plain),
            "len_site": len(site_plain),
            "oshb_preview": oshb_concatenated(ch, vs, False)[:80],
            "site_preview": site_concatenated(v, False)[:80],
        })

    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=rows[0].keys() if rows else [])
        wr.writeheader()
        wr.writerows(rows)

    total = len(rows)
    print(f"Versos: {total}")
    for k in ("OK", "OK_MAQAF_ONLY", "SUBSTRING", "MISMATCH", "NO_OSHB"):
        n = counts.get(k, 0)
        pct = 100.0 * n / total if total else 0
        print(f"  {k:<16} {n:>5}  ({pct:5.1f}%)")

    bad = [r for r in rows if r["status"] in ("MISMATCH", "SUBSTRING")]
    print("\nEjemplos a revisar (máx. 8):")
    for r in bad[:8]:
        print(f"  {r['ref']}: {r['status']} len {r['len_oshb']}/{r['len_site']}")

    print(f"\nCSV → {OUT_CSV}")


if __name__ == "__main__":
    main()
