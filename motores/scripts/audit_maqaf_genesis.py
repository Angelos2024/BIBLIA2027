"""Audita la cobertura de maqaf de OSHB vs el sitio en TODO Génesis.

Para cada verso:
 - Cuenta tokens OSHB que tienen maqaf (al inicio o al final)
 - Cuenta tokens del sitio que tienen maqaf (en prefix_forms, he_form o prs_suffix.he_form)
 - Reporta versos con un déficit (más maqafs en OSHB que en el sitio)

No modifica datos.
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ANGELOS = Path(r"C:\Users\pik_y\Documents\GitHub\Local-consults\estudio\angelos")
OSHB_DIR = ANGELOS / "IdiomaORIGEN" / "oshb-morph" / "chapters" / "01_Génesis"
TRAD = Path(r"C:\Users\pik_y\Documents\TRADUCCION")
FINAL = TRAD / "data" / "genesis_final.json"

MAQAF = "\u05be"


def count_oshb_maqafs(oshb_verse_json):
    """Cuenta tokens OSHB con maqaf (prefix o suffix). Devuelve (n, ejemplos)."""
    n = 0
    ex = []
    forms = oshb_verse_json.get("forms", [])
    for i, f in enumerate(forms):
        if MAQAF in f:
            n += 1
            ex.append(f"[{i}]{f!r}")
    return n, ex


def count_site_maqafs(site_verse):
    n = 0
    ex = []
    for pi, pair in enumerate(site_verse.get("pairs", []) or []):
        for hi, hw in enumerate(pair.get("he_words", []) or []):
            for ki, pf in enumerate(hw.get("prefix_forms", []) or []):
                if MAQAF in pf:
                    n += 1
                    ex.append(f"p{pi}.{hi}.pfx[{ki}]={pf!r}")
            sf = hw.get("he_form", "")
            if MAQAF in sf:
                n += 1
                ex.append(f"p{pi}.{hi}.stem={sf!r}")
            prs = hw.get("prs_suffix") or {}
            if prs.get("he_form") and MAQAF in prs["he_form"]:
                n += 1
                ex.append(f"p{pi}.{hi}.suf={prs['he_form']!r}")
    return n, ex


def main():
    site_data = json.loads(FINAL.read_text(encoding="utf-8"))
    site_by_ref = {f"{v.get('chapter')}:{v.get('verse')}": v for v in site_data.get("verses", [])}

    total_oshb = 0
    total_site = 0
    deficit_verses = []  # (ref, n_oshb, n_site)
    only_oshb = []       # versos donde OSHB tiene >0 maqafs y sitio tiene 0

    for ch in range(1, 51):
        oshb_file = OSHB_DIR / f"{ch}.json"
        if not oshb_file.exists():
            continue
        oshb_chap = json.loads(oshb_file.read_text(encoding="utf-8"))
        for vs in sorted(oshb_chap.keys(), key=lambda x: int(x) if x.isdigit() else 9999):
            if not vs.isdigit():
                continue
            ref = f"{ch}:{vs}"
            n_oshb, ex_oshb = count_oshb_maqafs(oshb_chap[vs])
            site_v = site_by_ref.get(ref)
            n_site, ex_site = (count_site_maqafs(site_v) if site_v else (0, []))
            total_oshb += n_oshb
            total_site += n_site
            if n_oshb > n_site:
                deficit_verses.append((ref, n_oshb, n_site, ex_oshb, ex_site))
            if n_oshb > 0 and n_site == 0:
                only_oshb.append((ref, n_oshb, ex_oshb))

    print(f"\n══════════════════════════════════════════════════════════")
    print(f" AUDITORÍA MAQAF — Génesis (OSHB vs genesis_final.json)")
    print(f"══════════════════════════════════════════════════════════")
    print(f" Tokens OSHB con maqaf : {total_oshb}")
    print(f" Tokens site con maqaf : {total_site}")
    print(f" Déficit (OSHB > site) : {total_oshb - total_site}")
    print(f" Versos con déficit    : {len(deficit_verses)}")
    print(f" Versos OSHB con maqaf y sitio sin: {len(only_oshb)}")

    print(f"\n--- Primeros 25 versos con déficit ---")
    for ref, no, ns, exo, exs in deficit_verses[:25]:
        print(f"  Gen {ref:<6}  OSHB={no:>2}  site={ns:>2}")
        for e in exo[:5]:
            print(f"      OSHB: {e}")
        for e in exs[:3]:
            print(f"      site: {e}")

    if only_oshb:
        print(f"\n--- Versos con maqaf en OSHB pero ninguno en el sitio (primeros 15) ---")
        for ref, no, exo in only_oshb[:15]:
            print(f"  Gen {ref:<6}  OSHB={no}  ejemplos: {', '.join(exo[:5])}")


if __name__ == "__main__":
    main()
