"""
build_lookup_indices_book.py — PASO 1.A genérico (cualquier libro).

Construye los índices Strong (ES / HE) restringidos al libro indicado, leyendo
los módulos PH4/SWORD ya descomprimidos (`_idx_SpaRV1909` / `_idx_OSHB`).

Salida (en BIBLIAS/):
    _idx_strong_es_<slug>.json
    _idx_strong_he_<slug>.json

Uso:
    python build_lookup_indices_book.py --book exodo
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_lookup_indices as bli  # noqa: E402
from book_config import resolve  # noqa: E402


def _verses_for_book(root: Path, modname: str, pysword_book: str, chapters: int):
    """Como `bli.get_verses_pysword`, pero parametrizado por libro y nº de capítulos."""
    from pysword.modules import SwordModules
    sm = SwordModules(str(root))
    found = sm.parse_modules()
    actual = next(
        (k for k in found if k.lower() == modname.lower()),
        next(iter(found.keys()), None),
    )
    if not actual:
        raise RuntimeError(f"no se encontró módulo {modname} en {root}")
    bible = sm.get_bible_from_module(actual)
    for ch in range(1, chapters + 1):
        try:
            it = bible.get_iter(books=[pysword_book], chapters=[ch], clean=False)
            # pysword valida el capítulo de forma perezosa al consumir el
            # iterador; materializamos aquí para capturar el desfase de
            # versificación (p.ej. Joel MT=4 caps vs RV/KJV=3 caps).
            verses = list(it)
        except Exception as e:
            print(f"    pysword: capítulo {pysword_book} {ch} no disponible: {e}")
            continue
        for vs_idx, raw in enumerate(verses, start=1):
            yield ch, vs_idx, raw


def _build_es(root: Path, pysword_book: str, chapters: int) -> dict:
    print(f"\n[ES] Iterando {pysword_book} de SpaRV1909 …")
    acc: dict[str, dict[str, dict]] = defaultdict(dict)
    total_verses = 0
    for ch, vs, raw in _verses_for_book(root, "SpaRV1909", pysword_book, chapters):
        total_verses += 1
        ref_short = f"{ch}:{vs}"
        for strongs, text, _morph in bli.parse_w_tags(raw):
            if not text:
                continue
            for s in strongs:
                bucket = acc[s].setdefault(text, {"count": 0, "verses": []})
                bucket["count"] += 1
                if ref_short not in bucket["verses"]:
                    bucket["verses"].append(ref_short)
    print(f"  versos leídos: {total_verses} | strongs únicos: {len(acc)}")
    out = {}
    for s, bucket in acc.items():
        entries = [
            {"text": t, "count": v["count"], "verses": v["verses"]}
            for t, v in bucket.items()
        ]
        entries.sort(key=lambda e: (-e["count"], e["text"]))
        out[s] = entries
    return out


def _build_he(root: Path, pysword_book: str, chapters: int) -> dict:
    print(f"\n[HE] Iterando {pysword_book} de OSHB …")
    acc: dict[str, dict[tuple, dict]] = defaultdict(dict)
    total_verses = 0
    for ch, vs, raw in _verses_for_book(root, "OSHB", pysword_book, chapters):
        total_verses += 1
        ref_short = f"{ch}:{vs}"
        for strongs, text, morph in bli.parse_w_tags(raw):
            if not text:
                continue
            for s in strongs:
                key = (text, morph)
                bucket = acc[s].setdefault(key, {"count": 0, "verses": []})
                bucket["count"] += 1
                if ref_short not in bucket["verses"]:
                    bucket["verses"].append(ref_short)
    print(f"  versos leídos: {total_verses} | strongs únicos: {len(acc)}")
    out = {}
    for s, bucket in acc.items():
        entries = [
            {"text": k[0], "morph": k[1], "count": v["count"], "verses": v["verses"]}
            for k, v in bucket.items()
        ]
        entries.sort(key=lambda e: (-e["count"], e["text"]))
        out[s] = entries
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--book", required=True)
    args = ap.parse_args()

    cfg = resolve(args.book)
    print(f"== build_lookup_indices_book — {cfg.label} ==")
    print(f"  BIBLIAS = {bli.BASE}")

    print("\n[unzip]")
    bli.ensure_unzip(bli.ZIP_SPA, bli.DIR_SPA_IDX)
    bli.ensure_unzip(bli.ZIP_OSHB, bli.DIR_OSHB_IDX)

    if not bli.ensure_pysword():
        raise RuntimeError("pysword es requerido; instálalo con `pip install pysword`.")

    es_idx = _build_es(bli.DIR_SPA_IDX, cfg.pysword_book, cfg.chapters)
    he_idx = _build_he(bli.DIR_OSHB_IDX, cfg.pysword_book, cfg.chapters)

    cfg.idx_es_path.write_text(
        json.dumps(es_idx, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    cfg.idx_he_path.write_text(
        json.dumps(he_idx, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print("\n[done]")
    print(f"  ES  → {cfg.idx_es_path}  ({cfg.idx_es_path.stat().st_size:,} bytes, {len(es_idx)} Strongs)")
    print(f"  HE  → {cfg.idx_he_path}  ({cfg.idx_he_path.stat().st_size:,} bytes, {len(he_idx)} Strongs)")


if __name__ == "__main__":
    main()
