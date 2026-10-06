"""
diagnose_genesis.py  —  PASO 1.B  (SOLO LECTURA del pipeline existente)

Lee `data/genesis_final.json` y los índices construidos por
`build_lookup_indices.py`, y emite un reporte CSV con una fila por token
hebreo (cada `he_word` dentro de cada `pair`).

Salida:
  - scripts/diagnose_genesis.csv

NO modifica `genesis_final.json`, `merge_oshb.py`, `apply_corrections.py`
ni `index.html`.

Columnas del CSV:
  ref, par_idx, hw_idx, raw, he_form, he_morph, strongs, es, gr_word,
  category, suggested_es, suggested_he_form, confidence, source

Categorías (mutuamente excluyentes; se elige UNA según prioridad):
  1. MISSING_STRONG  — strongs vacío  (no se puede sugerir)
  2. MISSING_HE      — he_form vacío / '·' / '.'
  3. MISSING_ES      — es vacío / '?'
  4. MISALIGN_ES     — es no aparece en las top-3 traducciones SpaRV1909 del Strong
  5. MORPH_MISMATCH  — he_form no concuerda con las top-3 formas OSHB del Strong
  6. OK              — todo aparece correcto / no aplica chequeo
"""
from __future__ import annotations

import csv
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT      = Path(r"C:\Users\pik_y\Documents\TRADUCCION")
GEN_JSON  = ROOT / "data" / "genesis_final.json"
IDX_ES    = ROOT / "BIBLIAS" / "_idx_strong_es_gen.json"
IDX_HE    = ROOT / "BIBLIAS" / "_idx_strong_he_gen.json"
OUT_CSV   = ROOT / "scripts" / "diagnose_genesis.csv"

EMPTY_HE  = {"", "·", ".", "—", "-"}
EMPTY_ES  = {"", "?"}

# ---------------------------------------------------------------------------
# normalización

def normalize_strong(raw: str) -> str:
    if not raw:
        return ""
    s = raw.strip()
    if ":" in s:
        s = s.split(":", 1)[1]
    if not s:
        return ""
    head = s[0].upper()
    if head not in ("H", "G"):
        return ""
    rest = s[1:].lstrip("0") or "0"
    return f"{head}{rest}"


def fold_es(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


# caracteres de cantillación/nikud y signos comunes a ignorar para comparación HE
HE_STRIP_RE = re.compile(
    r"[\u0591-\u05C7\u05BE\u05C0\u05C3\u05F3\u05F4\u200D\u200C\s\-\u05BE]"
)

def fold_he(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    return HE_STRIP_RE.sub("", s)


# ---------------------------------------------------------------------------
# chequeos de coincidencia

def es_in_module(token_es: str, entries: list) -> bool:
    """Devuelve True si `token_es` aparece dentro de cualquiera de las top-3
    traducciones del módulo para ese Strong (substring case/acentos-insensible)."""
    if not token_es:
        return False
    needle = fold_es(token_es)
    if not needle:
        return False
    for e in entries[:3]:
        hay = fold_es(e.get("text", ""))
        if not hay:
            continue
        if needle in hay or hay in needle:
            return True
        for w in re.findall(r"[a-z]+", hay):
            if w == needle:
                return True
            # tolerar variaciones cortas (singular/plural, conjugación)
            if (len(w) >= 4 and len(needle) >= 4 and
                (w.startswith(needle[:4]) or needle.startswith(w[:4]))):
                return True
    return False


def he_in_module(token_form: str, entries: list) -> bool:
    if not token_form:
        return False
    n = fold_he(token_form)
    if not n:
        return False
    for e in entries[:3]:
        m = fold_he(e.get("text", ""))
        if not m:
            continue
        if n == m or n in m or m in n:
            return True
    return False


def confidence_from(entries: list) -> str:
    if not entries:
        return "low"
    if len(entries) == 1 and entries[0].get("count", 0) >= 3:
        return "high"
    if len(entries) <= 2:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# main

def main():
    print("== PASO 1.B — Diagnóstico genesis_final.json ==")
    print(f"  cargando {GEN_JSON.name} ...")
    data = json.load(GEN_JSON.open(encoding="utf-8"))

    print(f"  cargando índices Strong ...")
    es_idx = json.load(IDX_ES.open(encoding="utf-8"))
    he_idx = json.load(IDX_HE.open(encoding="utf-8"))
    print(f"    ES Strongs: {len(es_idx)} | HE Strongs: {len(he_idx)}")

    verses = data.get("verses", [])
    print(f"  versos en JSON: {len(verses)}")

    rows               = []
    cat_counts         = Counter()
    per_verse_conflict = Counter()
    misalign_per_strong = Counter()

    for v in verses:
        ref = v.get("ref") or f'{v.get("book","Gen")} {v.get("chapter")}:{v.get("verse")}'
        pairs = v.get("pairs", [])
        for pi, pair in enumerate(pairs):
            hwords = pair.get("he_words", []) or []
            for hi, hw in enumerate(hwords):
                raw      = hw.get("raw", "") or ""
                he_form  = hw.get("he_form", "") or ""
                he_morph = hw.get("he_morph", "") or ""
                strongs  = (hw.get("strongs", "") or "").strip()
                es       = (hw.get("es", "") or "").strip()
                gr_word  = hw.get("gr_word", "") or ""

                strong_norm = normalize_strong(strongs) if strongs else ""

                es_entries = es_idx.get(strong_norm, []) if strong_norm else []
                he_entries = he_idx.get(strong_norm, []) if strong_norm else []

                suggested_es      = es_entries[0]["text"] if es_entries else ""
                suggested_he_form = he_entries[0]["text"] if he_entries else ""

                # ---- elegir categoría (prioridad) -----------------------
                cat        = "OK"
                source     = ""
                confidence = ""

                if not strong_norm:
                    cat = "MISSING_STRONG"
                    source = "none"
                    confidence = "low"
                elif he_form.strip() in EMPTY_HE:
                    cat = "MISSING_HE"
                    source = "OSHB" if he_entries else "none"
                    confidence = confidence_from(he_entries)
                elif es.strip() in EMPTY_ES:
                    cat = "MISSING_ES"
                    source = "SpaRV1909" if es_entries else "none"
                    confidence = confidence_from(es_entries)
                elif es_entries and not es_in_module(es, es_entries):
                    cat = "MISALIGN_ES"
                    source = "SpaRV1909"
                    confidence = confidence_from(es_entries)
                    misalign_per_strong[strong_norm] += 1
                elif he_entries and not he_in_module(he_form, he_entries):
                    cat = "MORPH_MISMATCH"
                    source = "OSHB"
                    confidence = confidence_from(he_entries)
                else:
                    cat = "OK"
                    if es_entries and he_entries:
                        source = "both"
                    elif es_entries:
                        source = "SpaRV1909"
                    elif he_entries:
                        source = "OSHB"
                    else:
                        source = "none"
                    confidence = "high" if (es_entries and he_entries) else "medium"

                cat_counts[cat] += 1
                if cat != "OK":
                    per_verse_conflict[ref] += 1

                rows.append({
                    "ref":               ref,
                    "par_idx":           pi,
                    "hw_idx":            hi,
                    "raw":               raw,
                    "he_form":           he_form,
                    "he_morph":          he_morph,
                    "strongs":           strong_norm or strongs,
                    "es":                es,
                    "gr_word":           gr_word,
                    "category":          cat,
                    "suggested_es":      suggested_es,
                    "suggested_he_form": suggested_he_form,
                    "confidence":        confidence,
                    "source":            source,
                })

    # ---- escribir CSV ----------------------------------------------------
    fieldnames = [
        "ref", "par_idx", "hw_idx", "raw", "he_form", "he_morph",
        "strongs", "es", "gr_word",
        "category", "suggested_es", "suggested_he_form",
        "confidence", "source",
    ]
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
        wr.writeheader()
        wr.writerows(rows)

    # ---- resumen ---------------------------------------------------------
    total = len(rows)
    print("\n========== RESUMEN ==========")
    print(f"Total tokens analizados: {total}")
    print("\nConteo por categoría:")
    for c in ("MISSING_STRONG", "MISSING_HE", "MISSING_ES",
              "MISALIGN_ES", "MORPH_MISMATCH", "OK"):
        n = cat_counts.get(c, 0)
        pct = (100.0 * n / total) if total else 0.0
        print(f"  {c:<16} {n:>6}  ({pct:5.2f}%)")

    print("\nTop 10 versos con más conflictos (categorías != OK):")
    for ref, n in per_verse_conflict.most_common(10):
        print(f"  {ref:<14} {n}")

    print("\nTop 10 Strongs con más MISALIGN_ES:")
    for s, n in misalign_per_strong.most_common(10):
        print(f"  {s:<8} {n}")

    print(f"\nCSV → {OUT_CSV}  ({OUT_CSV.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
