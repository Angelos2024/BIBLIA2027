"""
parse_catss.py — Parser CATSS .par genérico (cualquier libro).

Reutiliza la lógica de `parse_genesis.py` pero parametrizada por libro
desde `book_config.py`. La regex de referencia (`Gen`, `Exod`, `Lev`, …)
y las rutas de I/O se toman del BookConfig.

Uso:
    python parse_catss.py --book exodo
    python parse_catss.py --book levitico --out custom/path.json

Salida:
    data/<slug>_full.json  (por defecto)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Reutilizamos toda la maquinaria de parse_genesis.py
import parse_genesis as _g  # noqa: E402
from book_config import BookConfig, resolve  # noqa: E402


def parse_book(cfg: BookConfig) -> dict:
    """Parsea el .par del libro `cfg` usando la lógica heredada de parse_genesis."""
    if not cfg.par_path.exists():
        raise FileNotFoundError(
            f"No se encontró .par para {cfg.label}: {cfg.par_path}\n"
            f"  Descárgalo con: curl -sL "
            f"\"https://ccat.sas.upenn.edu/gopher/text/religion/biblical/parallel/{cfg.par_filename}\""
            f" -o \"{cfg.par_path}\""
        )

    # Sobreescribimos la regex de referencia para este libro.
    # Capítulo opcional: libros de un solo capítulo (Abdías) usan "Obad N"
    # sin "cap:ver"; en ese caso el capítulo es 1.
    ref_re = re.compile(rf"^{re.escape(cfg.catss_ref_label)}\s+(?:(\d+):)?(\d+)\s*$")

    text = cfg.par_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    verses: list[dict] = []
    current_chapter: int | None = None
    current_verse_num: int | None = None
    current_pairs: list[dict] = []
    current_ref: str | None = None

    def flush_verse():
        if current_ref is not None and current_pairs:
            verses.append({
                "book": cfg.label,
                "chapter": current_chapter,
                "verse": current_verse_num,
                "ref": current_ref,
                "pairs": list(current_pairs),
            })

    for line in lines:
        line = line.rstrip("\r\n")
        if not line.strip():
            continue

        m = ref_re.match(line)
        if m:
            flush_verse()
            current_chapter = int(m.group(1)) if m.group(1) else 1
            current_verse_num = int(m.group(2))
            current_ref = f"{cfg.catss_ref_label} {current_chapter}:{current_verse_num}"
            current_pairs = []
            continue

        if "\t" in line:
            parts = line.split("\t", 1)
            he_raw = parts[0]
            gr_raw = parts[1] if len(parts) > 1 else ""
            pair = _g.classify_pair(he_raw, gr_raw)
            current_pairs.append(pair)
        else:
            if line.strip():
                pair = _g.classify_pair(line.strip(), "")
                current_pairs.append(pair)

    flush_verse()

    return {
        "_schema": "catss-par-parsed-v1",
        "_source": (
            "https://ccat.sas.upenn.edu/gopher/text/religion/biblical/parallel/"
            f"{cfg.par_filename}"
        ),
        "_file": cfg.par_filename,
        "_book": cfg.label,
        "_slug": cfg.slug,
        "_parser": "parse_catss.py (inspirado en codykingham/CATSS_parsers)",
        "_greek_utils": f"greek-utils disponible: {_g._HAS_GREEK_UTILS}",
        "verseCount": len(verses),
        "verses": verses,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--book", required=True, help="slug del libro (genesis, exodo, …)")
    ap.add_argument("--out", help="ruta de salida (default: data/<slug>_full.json)")
    args = ap.parse_args()

    cfg = resolve(args.book)
    out_path = Path(args.out) if args.out else cfg.raw_json_path

    print(f"== parse_catss — {cfg.label} ==")
    print(f"  .par   : {cfg.par_path}")
    print(f"  salida : {out_path}")

    data = parse_book(cfg)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Versículos procesados : {data['verseCount']}")
    print(f"greek-utils activo    : {_g._HAS_GREEK_UTILS}")
    if data["verses"]:
        v0 = data["verses"][0]
        print(f"\nMuestra: {v0['ref']}")
        for p in v0["pairs"][:5]:
            print(f"  {p.get('he',''):<20} = {p.get('he_unicode',''):<12} | "
                  f"{p.get('gr',''):<30} = {p.get('gr_unicode','')}")


if __name__ == "__main__":
    main()
