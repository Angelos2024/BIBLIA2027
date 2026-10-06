"""
Paso 5.4 — Insertar equivalencias LXX (griego)

Prioridad: interlinear-snapshot (greek_lxx por morfema).
No sobrescribe gr_word / prefix_gr existentes.
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
    parse_ref,
    save_active,
    set_active_book,
    snapshot_by_fold,
    verse_in_range,
    verse_ref,
)


def _add_chapter_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--chapter", type=int, default=None)
    ap.add_argument("--from-chapter", type=int, default=None, dest="from_chapter")
    ap.add_argument("--to-chapter", type=int, default=None, dest="to_chapter")

OUT_CSV = SCRIPTS / "paso5_4_fill_lxx.csv"


def _empty_gr(g: str) -> bool:
    g = (g or "").strip()
    return not g or g in ("—", "-", "?")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    _add_chapter_args(ap)
    add_book_arg(ap)
    args = ap.parse_args()
    set_active_book(args.book)

    print(f"== PASO 5.4 — Griego LXX (snapshot) [{args.book}] ==")
    if args.chapter:
        print(f"  Filtro: capítulo {args.chapter}")
    elif args.from_chapter or args.to_chapter:
        print(f"  Filtro: caps {args.from_chapter or 1}–{args.to_chapter or 50}")
    data = load_active()
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
                slots = [("stem", hw.get("he_form", ""), hw.get("gr_word", ""), "gr_word", None)]
                for ki, pf in enumerate(hw.get("prefix_forms", []) or []):
                    pgr = hw.setdefault("prefix_gr", [])
                    while len(pgr) <= ki:
                        pgr.append("")
                    slots.append((f"prefix[{ki}]", pf, pgr[ki], "prefix_gr", ki))
                prs = hw.get("prs_suffix") or {}
                if prs:
                    slots.append(("suffix", prs.get("he_form", ""), prs.get("gr_word", ""), "prs.gr", None))

                for slot_name, form, gr_cur, gr_key, pfx_i in slots:
                    if not _empty_gr(gr_cur):
                        continue
                    fold = fold_he(form)
                    segs = snap_map.get(fold, [])
                    if not segs:
                        counts["NO_LXX"] += 1
                        continue
                    gk = (segs[0].get("greek_lxx") or "").strip()
                    if _empty_gr(gk):
                        counts["NO_LXX"] += 1
                        continue
                    counts["SUGGESTED"] += 1
                    rows.append({
                        "ref": ref, "pair": pi, "hw": hi, "slot": slot_name,
                        "fold": fold, "gr_current": gr_cur, "gr_suggested": gk,
                        "lxx_tier": segs[0].get("lxx_tier", ""),
                    })
                    if args.apply:
                        if gr_key == "gr_word":
                            hw["gr_word"] = gk
                            hw["gr_source"] = "paso5_4:snapshot"
                        elif gr_key == "prefix_gr" and pfx_i is not None:
                            hw["prefix_gr"][pfx_i] = gk
                        elif gr_key == "prs.gr":
                            prs["gr_word"] = gk
                        filled += 1

    if rows:
        with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
            wr = csv.DictWriter(f, fieldnames=rows[0].keys())
            wr.writeheader()
            wr.writerows(rows)

    print(f"Sugerencias LXX: {counts.get('SUGGESTED', 0)} | Sin griego en snapshot: {counts.get('NO_LXX', 0)}")
    if args.apply:
        print(f"Rellenados: {filled}")
        save_active(data)
    else:
        print("(sin --apply)")
    print(f"CSV → {OUT_CSV}")


if __name__ == "__main__":
    main()
