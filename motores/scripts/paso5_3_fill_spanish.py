"""
Paso 5.3 — Buscar / insertar equivalencias al español

Prioridad: interlinear-snapshot → índice SpaRV1909 (Strong).
Solo tokens con `es` vacío o '?', sin es_source manual/patch.
"""
from __future__ import annotations

import argparse
import csv
import json
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
    load_idx_es,
    normalize_strong,
    parse_ref,
    save_active,
    set_active_book,
    snapshot_by_fold,
    verse_in_range,
    verse_ref,
)


def _add_chapter_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--chapter", type=int, default=None, help="Solo este capítulo")
    ap.add_argument("--from-chapter", type=int, default=None, dest="from_chapter", help="Desde capítulo N")
    ap.add_argument("--to-chapter", type=int, default=None, dest="to_chapter", help="Hasta capítulo N")

OUT_CSV = SCRIPTS / "paso5_3_fill_spanish.csv"
PROTECTED = frozenset({"manual", "patch"})


def _suggest_es(strong: str, fold: str, snap_map: dict, es_idx: dict) -> tuple[str, str, str]:
    segs = snap_map.get(fold, [])
    if segs:
        s = (segs[0].get("spanish") or "").strip()
        if s:
            return s, "snapshot", "high"
    if strong and strong in es_idx:
        entries = es_idx[strong]
        if entries and entries[0].get("count", 0) >= 2:
            return entries[0]["text"], "SpaRV1909", "medium"
    return "", "none", "low"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    _add_chapter_args(ap)
    add_book_arg(ap)
    args = ap.parse_args()
    set_active_book(args.book)

    print(f"== PASO 5.3 — Español (snapshot → Strong) [{args.book}] ==")
    if args.chapter:
        print(f"  Filtro: capítulo {args.chapter}")
    elif args.from_chapter or args.to_chapter:
        print(f"  Filtro: caps {args.from_chapter or 1}–{args.to_chapter or 50}")
    data = load_active()
    try:
        es_idx = load_idx_es()
    except FileNotFoundError as e:
        print(f"  [warn] {e}\n  Continuando solo con snapshot (sin fallback Strong).")
        es_idx = {}

    rows = []
    filled = 0
    counts: Counter = Counter()

    for v in data.get("verses", []):
        if not verse_in_range(
            v, chapter=args.chapter,
            from_chapter=args.from_chapter, to_chapter=args.to_chapter,
        ):
            continue
        ref = verse_ref(v)
        ch, vs = parse_ref(ref)
        snap_map = snapshot_by_fold(ch, vs)
        for pi, pair in enumerate(v.get("pairs", [])):
            if pair.get("kind") in ("gk_add", "heb_omit"):
                continue
            for hi, hw in enumerate(pair.get("he_words", []) or []):
                if hw.get("es_source", "") in PROTECTED:
                    continue
                strong = normalize_strong(hw.get("strongs", "") or "")

                slots = [
                    ("stem", hw.get("he_form", ""), hw.get("he_morph", ""),
                     hw.get("es", ""), "es", None),
                ]
                for ki, pf in enumerate(hw.get("prefix_forms", []) or []):
                    pes = hw.setdefault("prefix_es", [])
                    while len(pes) <= ki:
                        pes.append("")
                    pm = (hw.get("prefix_morphs") or [""])[ki] if ki < len(hw.get("prefix_morphs") or []) else ""
                    slots.append((f"prefix[{ki}]", pf, pm, pes[ki], "prefix_es", ki))

                prs = hw.get("prs_suffix") or {}
                if prs:
                    slots.append((
                        "suffix", prs.get("he_form", ""), prs.get("he_morph", ""),
                        prs.get("es", ""), "prs_suffix.es", None,
                    ))

                for slot_name, form, morph, es_cur, es_key, pfx_i in slots:
                    es_cur = (es_cur or "").strip()
                    if es_cur and es_cur != "?":
                        continue
                    # אֵת marcador: sin glosa (igual que Global Pass 5)
                    m0 = (morph or "").split("+")[0]
                    if m0 == "PART.OBJ.DIR":
                        continue
                    fold = fold_he(form)
                    if not fold and not strong:
                        continue
                    sug, source, conf = _suggest_es(strong, fold, snap_map, es_idx)
                    status = "SUGGESTED" if sug else "MISSING_ES"
                    counts[status] += 1
                    rows.append({
                        "ref": ref, "pair": pi, "hw": hi, "slot": slot_name,
                        "fold": fold, "strongs": strong, "morph": morph,
                        "es_current": es_cur, "es_suggested": sug,
                        "source": source, "confidence": conf,
                    })
                    if args.apply and sug and conf in ("high", "medium"):
                        if es_key == "es":
                            hw["es"] = sug
                            hw["es_source"] = f"paso5_3:{source}"
                        elif es_key == "prefix_es" and pfx_i is not None:
                            hw["prefix_es"][pfx_i] = sug
                        elif es_key == "prs_suffix.es":
                            prs["es"] = sug
                        filled += 1

    if rows:
        with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
            wr = csv.DictWriter(f, fieldnames=rows[0].keys())
            wr.writeheader()
            wr.writerows(rows)

    print(f"Sugerencias: {counts.get('SUGGESTED', 0)} | Sin sugerencia: {counts.get('MISSING_ES', 0)}")
    if args.apply:
        print(f"Rellenados (--apply): {filled}")
        save_active(data)
    else:
        print("(sin --apply: no se modificó el JSON)")
    print(f"CSV → {OUT_CSV}")


if __name__ == "__main__":
    main()
