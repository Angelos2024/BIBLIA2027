"""
build_rv1960_book.py — Copia RV1960 de angelos al directorio data/<slug>.

Lee `angelos/librosRV1960/<slug>.json` (array[capitulos][versos]) y lo guarda
como `data/rv1960_<slug>.json` para que el visor TRADUCCION/index.html lo
consuma.

Uso:
    python build_rv1960_book.py --book exodo
    python build_rv1960_book.py --book genesis    # idempotente, sobrescribe
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from book_config import resolve  # noqa: E402

ANGELOS = Path(r"C:\Users\Angelos\Documents\GitHub\Local-consults\estudio\angelos")
RV_BASE = ANGELOS / "librosRV1960"
# Salida: data_master/ en la raíz del repo (BIBLIA2027/), donde el visor los lee.
TRAD = Path(__file__).resolve().parent.parent.parent / "data_master"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--book", required=True)
    args = ap.parse_args()

    cfg = resolve(args.book)
    src = RV_BASE / f"{cfg.slug}.json"
    dst = TRAD / f"rv1960_{cfg.slug}.json"

    if not src.exists():
        sys.stderr.write(
            f"[error] no existe {src}\n"
            f"        angelos/librosRV1960/ debería tener {cfg.slug}.json\n"
        )
        sys.exit(1)

    data = json.loads(src.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        sys.stderr.write(
            f"[error] formato inesperado en {src} (no es array de capítulos)\n"
        )
        sys.exit(2)

    print(f"== build_rv1960_book — {cfg.label} ({cfg.slug}) ==")
    print(f"  src: {src}")
    print(f"  dst: {dst}")
    print(f"  capítulos : {len(data)}")
    print(f"  versos    : {sum(len(c) for c in data)}")

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"  → escrito {dst.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
