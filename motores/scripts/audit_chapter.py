"""Auditoría de glosas hebreo→español por capítulo."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "genesis_final.json"


def clean_he(s: str | None) -> str:
    if not s:
        return ""
    t = re.sub(r"[\u0591-\u05AF]", "", str(s))
    t = re.sub(r"[\u05BE\u05C0]", "", t)
    t = re.sub(r"[\u05C3-\u05C6]", "", t)
    t = re.sub(r"^[\s\-–־]+", "", t)
    t = re.sub(r"[\s\-–־]+$", "", t)
    return t.strip()


def is_intentional_empty(hw: dict, slot: str, prefix_morph: str = "") -> bool:
    morph = hw.get("he_morph", "") or ""
    if slot == "stem":
        if morph == "PART.OBJ.DIR" or morph.startswith("PART.OBJ.DIR+"):
            return True
        raw = hw.get("raw", "")
        if raw in ("=L/MYN/W", "=L/MYN/HW") or raw.startswith("="):
            return True
        if (hw.get("es_source") or "").strip().lower() == "patch_meta":
            return True
    if slot == "prefix" and prefix_morph == "PART.OBJ.DIR":
        return True
    return False


def classify_issue(hw: dict, slot: str, es: str, prefix_morph: str = "", prefix_form: str = "") -> str:
    if is_intentional_empty(hw, slot, prefix_morph):
        return "ok_marcador"
    if es:
        return "ok"
    morph = hw.get("he_morph", "") or ""
    strong = hw.get("strongs", "") or ""
    raw = hw.get("raw", "")

    if not strong and not clean_he(hw.get("he_form") or prefix_form):
        return "error_sin_forma"
    if raw.startswith("=") or raw.startswith("{") or raw.startswith("<"):
        return "error_meta_catss"
    if "MYN" in raw and slot == "stem":
        return "error_myn_sin_glosa"
    if prefix_morph == "ART":
        return "error_art_vacio"
    if morph == "PREP" or morph.startswith("PREP"):
        return "error_prep_vacio"
    if morph.startswith("CONJ") or prefix_morph == "CONJ":
        return "error_conj_vacio"
    if not strong:
        return "error_sin_strong"
    return "error_sin_glosa"


def audit_chapter(data: dict, chapter: int) -> list[dict]:
    rows = []
    for v in data.get("verses", []):
        if v.get("chapter") != chapter:
            continue
        ref = f"{chapter}:{v.get('verse')}"
        for pi, p in enumerate(v.get("pairs", [])):
            kind = p.get("kind", "")
            if kind == "gk_add":
                gr = (p.get("gr_unicode") or "").strip()
                rows.append({
                    "ref": ref, "slot": "gk_add", "he": "—", "strongs": "—",
                    "morph": kind, "es": gr or "—", "estado": "ok" if gr else "error_gk_add_vacio",
                    "nota": "Texto griego añadido LXX",
                })
                continue
            if kind == "heb_omit":
                he = clean_he(p.get("he_unicode", ""))
                es = (p.get("es_gloss") or "").strip()
                rows.append({
                    "ref": ref, "slot": "heb_omit", "he": he or "—", "strongs": "—",
                    "morph": "heb_omit", "es": es or "—",
                    "estado": "ok" if es else "error_heb_omit_vacio",
                    "nota": "Omisión hebrea",
                })
                continue

            for hi, hw in enumerate(p.get("he_words", [])):
                he_stem = clean_he(hw.get("he_form") or hw.get("stem_unicode") or "")
                es_stem = (hw.get("es") or "").strip()
                src = hw.get("es_source", "") or ""
                estado = classify_issue(hw, "stem", es_stem)
                nota = ""
                if estado == "ok_marcador":
                    if (src or "").lower() == "patch_meta":
                        nota = "slot duplicado OSHB — sin glosa ES"
                    else:
                        nota = "אֵת — sin glosa (marcador gramatical)"
                elif src:
                    nota = f"fuente: {src}"

                prs = hw.get("prs_suffix") or {}
                es_display = es_stem
                if prs and (prs.get("es") or "").strip():
                    es_display = f"{es_stem} + suf[{prs.get('es')}]".strip(" +")

                rows.append({
                    "ref": ref, "slot": f"stem p{pi}", "he": he_stem or "—",
                    "strongs": hw.get("strongs") or "—", "morph": hw.get("he_morph") or "—",
                    "es": es_display or "—", "estado": estado, "nota": nota,
                })

                for i, pf in enumerate(hw.get("prefix_forms") or []):
                    pe = (hw.get("prefix_es") or [""])[i] if i < len(hw.get("prefix_es") or []) else ""
                    pe = (pe or "").strip()
                    pm = (hw.get("prefix_morphs") or [""])[i] if i < len(hw.get("prefix_morphs") or []) else ""
                    estado_p = classify_issue(hw, "prefix", pe, pm, pf)
                    nota_p = ""
                    if estado_p == "ok_marcador":
                        nota_p = "marcador OBJ.DIR"
                    rows.append({
                        "ref": ref, "slot": f"prefix[{i}] p{pi}", "he": clean_he(pf) or "—",
                        "strongs": "—", "morph": pm or "—",
                        "es": pe or "—", "estado": estado_p, "nota": nota_p,
                    })
    return rows


def main():
    chapter = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    data = json.loads(DATA.read_text(encoding="utf-8"))
    rows = audit_chapter(data, chapter)

    ok = [r for r in rows if r["estado"] in ("ok", "ok_marcador")]
    issues = [r for r in rows if r["estado"] not in ("ok", "ok_marcador")]

    print(f"# Génesis {chapter} — auditoría de glosas\n")
    print(f"Total tokens: {len(rows)} | OK: {len(ok)} | Problemas: {len(issues)}\n")

    if issues:
        print("## Problemas (vacíos o errores)\n")
        print("| Versículo | Slot | Hebreo | Strong | Morf | ES actual | Estado |")
        print("|-----------|------|--------|--------|------|-----------|--------|")
        for r in issues:
            he = r["he"].replace("|", "\\|")
            es = r["es"].replace("|", "\\|")
            print(f"| {r['ref']} | {r['slot']} | {he} | {r['strongs']} | {r['morph']} | {es} | {r['estado']} |")

    print("\n## Resumen por tipo de problema\n")
    from collections import Counter
    c = Counter(r["estado"] for r in issues)
    for k, n in c.most_common():
        print(f"- {k}: {n}")

    # Versículos con al menos un problema
    bad_refs = sorted(set(r["ref"] for r in issues), key=lambda x: int(x.split(":")[1]))
    print(f"\nVersículos con problemas ({len(bad_refs)}): {', '.join(bad_refs)}")

    # Guardar CSV para referencia
    out = Path(__file__).parent / f"audit_genesis_ch{chapter}.csv"
    import csv
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ref", "slot", "he", "strongs", "morph", "es", "estado", "nota"])
        w.writeheader()
        w.writerows(rows)
    print(f"\nCSV completo: {out}")


if __name__ == "__main__":
    main()
