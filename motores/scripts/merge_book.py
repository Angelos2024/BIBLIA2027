"""
merge_book.py — Driver libro-agnóstico de merge_oshb.py.

Sobre-escribe en runtime las rutas globales que `merge_oshb` tenía hard-codeadas
para Génesis (SNAP_DIR, OSHB_DIR, INTER_DIR, IN_FILE, OUT_FILE) usando el
BookConfig solicitado, y luego invoca `merge_oshb.main()` sin tocar la lógica
original (regla A/B/D/E sigue siendo Génesis-only, eso es intencional).

Uso:
    python merge_book.py --book exodo
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from book_config import resolve  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--book", required=True)
    args = ap.parse_args()

    cfg = resolve(args.book)

    import merge_oshb as mo  # noqa: E402

    if not cfg.raw_json_path.exists():
        raise FileNotFoundError(
            f"Falta {cfg.raw_json_path}. Ejecuta primero:\n"
            f"  python parse_catss.py --book {cfg.slug}"
        )

    # Reescribir rutas a las del libro
    mo.SNAP_DIR  = cfg.snap_dir
    mo.OSHB_DIR  = cfg.oshb_dir
    mo.INTER_DIR = cfg.inter_dir
    mo.IN_FILE   = cfg.raw_json_path
    mo.OUT_FILE  = cfg.final_json_path

    print(f"== merge_book — {cfg.label} ==")
    print(f"  IN   : {mo.IN_FILE}")
    print(f"  OSHB : {mo.OSHB_DIR}")
    print(f"  SNAP : {mo.SNAP_DIR}")
    print(f"  OUT  : {mo.OUT_FILE}")

    mo.main()


if __name__ == "__main__":
    main()
