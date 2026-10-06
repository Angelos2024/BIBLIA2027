"""Auditoría maqaf por capítulo: OSHB vs sitio + convención UI (trailing)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8")

from audit_maqaf_genesis import count_oshb_maqafs, count_site_maqafs
from hebrew_clean import scan_verse_maqaf_issues

ANGELOS = Path(r"C:\Users\pik_y\Documents\GitHub\Local-consults\estudio\angelos")
OSHB_DIR = ANGELOS / "IdiomaORIGEN" / "oshb-morph" / "chapters" / "01_Génesis"
FINAL = Path(r"C:\Users\pik_y\Documents\TRADUCCION\data\genesis_final.json")


def audit_chapter(chapter: int, *, site_data: dict | None = None) -> dict:
    site_data = site_data or json.loads(FINAL.read_text(encoding="utf-8"))
    site_by_ref = {
        f"{v.get('chapter')}:{v.get('verse')}": v for v in site_data.get("verses", [])
    }
    oshb_file = OSHB_DIR / f"{chapter}.json"
    if not oshb_file.exists():
        raise SystemExit(f"OSHB cap. {chapter} no encontrado: {oshb_file}")

    oshb_chap = json.loads(oshb_file.read_text(encoding="utf-8"))
    deficits = []
    ui_issues: list[str] = []
    total_oshb = total_site = 0

    for vs in sorted(oshb_chap.keys(), key=lambda x: int(x) if x.isdigit() else 9999):
        if not vs.isdigit():
            continue
        ref = f"{chapter}:{vs}"
        n_oshb, ex_oshb = count_oshb_maqafs(oshb_chap[vs])
        site_v = site_by_ref.get(ref)
        n_site, ex_site = count_site_maqafs(site_v) if site_v else (0, [])
        total_oshb += n_oshb
        total_site += n_site
        if n_oshb != n_site:
            deficits.append((ref, n_oshb, n_site, ex_oshb, ex_site))
        if site_v:
            ui_issues.extend(scan_verse_maqaf_issues(site_v))

    return {
        "chapter": chapter,
        "total_oshb": total_oshb,
        "total_site": total_site,
        "deficits": deficits,
        "ui_issues": ui_issues,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Auditoría maqaf por capítulo (Génesis)")
    ap.add_argument("chapter", type=int, nargs="?", default=13)
    args = ap.parse_args()

    r = audit_chapter(args.chapter)
    ch = r["chapter"]
    print(f"\n══════════════════════════════════════════════════════════")
    print(f" MAQAF — Génesis cap. {ch}")
    print(f"══════════════════════════════════════════════════════════")
    print(f" Tokens OSHB con maqaf : {r['total_oshb']}")
    print(f" Tokens site con maqaf : {r['total_site']}")
    print(f" Diferencia (OSHB-site): {r['total_oshb'] - r['total_site']}")
    print(f" Versos con conteo distinto: {len(r['deficits'])}")
    print(f" Incidencias convención UI: {len(r['ui_issues'])}")

    if r["deficits"]:
        print(f"\n--- Versos OSHB ≠ site ---")
        for ref, no, ns, exo, exs in r["deficits"]:
            print(f"  Gen {ref:<6}  OSHB={no:>2}  site={ns:>2}")
            for e in exo[:4]:
                print(f"      OSHB: {e}")
            for e in exs[:4]:
                print(f"      site: {e}")

    if r["ui_issues"]:
        print(f"\n--- Convención UI (leading / Bethel) ---")
        for line in r["ui_issues"]:
            print(f"  {line}")
    elif not r["deficits"]:
        print("\n✓ Sin incidencias maqaf en este capítulo.")


if __name__ == "__main__":
    main()
