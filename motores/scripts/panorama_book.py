"""Métricas de calidad de un libro procesado (similar al panorama de Génesis).

Mide cobertura ES, GR, morfología (canónica vs legacy), Strong, OSHB.

Uso:
    python panorama_book.py --book exodo
    python panorama_book.py --book genesis
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from book_config import resolve  # noqa: E402

# Heurística: "legacy" = códigos CATSS/OSHM cortos (`Vqp3ms`, `NCMSC`, etc.)
# canónico = formato pipeline (`VERBO.QAL.PERF.P3.M.SG`, `SUBS.M.SG.C`)
_LEGACY_RE = re.compile(r"^(V[qpndhoNDHOL]|NC[MFcCBu][SP][CAa])")
_CANONICAL_PREFIXES = ("VERBO.", "SUBS.", "ADJ.", "NUM.", "ART", "CONJ", "PREP",
                       "PRON.", "PRS.", "PART.", "REL", "INTJ", "ADV", "NPROP",
                       "AMSA", "AFSA", "AMPA", "AFPA", "OMSA", "OFSA")
EMPTY_ES = {"", "?", "—", "-"}
EMPTY_GR = {"", "?", "—", "-", "---"}


def is_canonical_morph(m: str) -> bool:
    if not m:
        return False
    # composiciones con + (PREP+PRS, PART.OBJ.DIR+PRS.P3.M.SG, etc.)
    parts = m.split("+")
    return all(any(p.startswith(pref) for pref in _CANONICAL_PREFIXES) for p in parts if p)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--book", default="exodo")
    args = ap.parse_args()

    cfg = resolve(args.book)
    if not cfg.final_json_path.exists():
        sys.stderr.write(f"  [error] no existe {cfg.final_json_path}\n")
        sys.exit(1)

    data = json.loads(cfg.final_json_path.read_text(encoding="utf-8"))
    verses = data.get("verses", [])

    n_verses = len(verses)
    n_pairs = 0
    n_he_words = 0
    n_morphemes = 0  # cualquier slot con forma hebrea (prefijos + stem + suffix)

    es_ok = es_empty = 0
    gr_ok = gr_empty = 0
    morph_canonical = morph_legacy = morph_empty = 0
    strong_ok = strong_empty = 0

    morph_audit_counter = Counter()
    morph_source_counter = Counter()
    es_source_counter = Counter()
    gr_source_counter = Counter()

    for v in verses:
        for pair in v.get("pairs", []) or []:
            n_pairs += 1
            for hw in pair.get("he_words", []) or []:
                n_he_words += 1

                # Prefijos: cada slot con forma cuenta
                pmorphs = hw.get("prefix_morphs", []) or []
                pforms = hw.get("prefix_forms", []) or []
                pes = hw.get("prefix_es", []) or []
                pgr = hw.get("prefix_gr", []) or []
                for i, pm in enumerate(pmorphs):
                    pf = pforms[i] if i < len(pforms) else ""
                    if not pf:
                        continue
                    n_morphemes += 1
                    pe = pes[i] if i < len(pes) else ""
                    pg = pgr[i] if i < len(pgr) else ""
                    es_ok += 1 if pe and pe not in EMPTY_ES else 0
                    es_empty += 1 if (not pe or pe in EMPTY_ES) else 0
                    gr_ok += 1 if pg and pg not in EMPTY_GR else 0
                    gr_empty += 1 if (not pg or pg in EMPTY_GR) else 0
                    if not pm:
                        morph_empty += 1
                    elif is_canonical_morph(pm):
                        morph_canonical += 1
                    else:
                        morph_legacy += 1

                # Stem
                he_form = hw.get("he_form", "") or ""
                if he_form:
                    n_morphemes += 1
                    es = hw.get("es", "") or ""
                    gr = hw.get("gr_word", "") or ""
                    morph = hw.get("he_morph", "") or ""
                    strong = hw.get("strongs", "") or ""

                    es_ok += 1 if es and es not in EMPTY_ES else 0
                    es_empty += 1 if (not es or es in EMPTY_ES) else 0
                    gr_ok += 1 if gr and gr not in EMPTY_GR else 0
                    gr_empty += 1 if (not gr or gr in EMPTY_GR) else 0
                    if not morph:
                        morph_empty += 1
                    elif is_canonical_morph(morph):
                        morph_canonical += 1
                    else:
                        morph_legacy += 1
                    strong_ok += 1 if strong else 0
                    strong_empty += 1 if not strong else 0

                    if hw.get("morph_audit"):
                        morph_audit_counter[hw["morph_audit"]] += 1
                    if hw.get("morph_source"):
                        morph_source_counter[hw["morph_source"]] += 1
                    if hw.get("es_source"):
                        es_source_counter[hw["es_source"]] += 1
                    if hw.get("gr_source"):
                        gr_source_counter[hw["gr_source"]] += 1

                # Sufijo PRS
                prs = hw.get("prs_suffix") or {}
                if prs.get("he_form"):
                    n_morphemes += 1
                    es = prs.get("es", "") or ""
                    gr = prs.get("gr_word", "") or ""
                    morph = prs.get("he_morph", "") or ""
                    es_ok += 1 if es and es not in EMPTY_ES else 0
                    es_empty += 1 if (not es or es in EMPTY_ES) else 0
                    gr_ok += 1 if gr and gr not in EMPTY_GR else 0
                    gr_empty += 1 if (not gr or gr in EMPTY_GR) else 0
                    if not morph:
                        morph_empty += 1
                    elif is_canonical_morph(morph):
                        morph_canonical += 1
                    else:
                        morph_legacy += 1

    def pct(n, total):
        return f"{(100.0 * n / total):.1f}%" if total else "—"

    print(f"\n══════════════════════════════════════════════════════════════")
    print(f" PANORAMA — {cfg.label} ({cfg.slug})")
    print(f"══════════════════════════════════════════════════════════════")
    print(f" Versículos              : {n_verses}")
    print(f" Pairs                   : {n_pairs}")
    print(f" he_words                : {n_he_words}")
    print(f" Morfemas (slots)        : {n_morphemes}")
    print()
    print(f" Cobertura ES (slots)    : {pct(es_ok, n_morphemes)}  ({es_ok}/{n_morphemes})")
    print(f"   vacíos / ?            : {pct(es_empty, n_morphemes)}  ({es_empty})")
    print(f" Cobertura GR-LXX        : {pct(gr_ok, n_morphemes)}  ({gr_ok}/{n_morphemes})")
    print(f"   vacíos / ?            : {pct(gr_empty, n_morphemes)}  ({gr_empty})")
    print(f" Morfología canónica     : {pct(morph_canonical, n_morphemes)}  ({morph_canonical})")
    print(f"   formato legacy CATSS  : {pct(morph_legacy, n_morphemes)}  ({morph_legacy})")
    print(f"   sin morfología        : {pct(morph_empty, n_morphemes)}  ({morph_empty})")
    print()
    print(f" Stems con Strong        : {pct(strong_ok, strong_ok+strong_empty)}  ({strong_ok}/{strong_ok+strong_empty})")
    print()

    if morph_audit_counter:
        print(f" morph_audit (top 8):")
        for tag, c in morph_audit_counter.most_common(8):
            print(f"   {tag:<30} {c}")

    if morph_source_counter:
        print(f"\n morph_source (top 8):")
        for tag, c in morph_source_counter.most_common(8):
            print(f"   {tag:<30} {c}")

    if es_source_counter:
        print(f"\n es_source (top 8):")
        for tag, c in es_source_counter.most_common(8):
            print(f"   {tag:<30} {c}")

    if gr_source_counter:
        print(f"\n gr_source (top 8):")
        for tag, c in gr_source_counter.most_common(8):
            print(f"   {tag:<30} {c}")


if __name__ == "__main__":
    main()
