"""_apply_glosas_personales.py — Re-aplica las glosas personales del editor.

Toma `data/glosas_personales.json` (el REGISTRO durable de todo lo que editaste
en el editor: reglas globales y por contexto) y lo vuelve a aplicar sobre el
`<libro>_final.json`. Así, al regenerar un libro con run_motors, tus ediciones
del español NUNCA se pierden: el registro manda y se reimprime al final.

Uso:
    python _apply_glosas_personales.py <slug> --apply
    python _apply_glosas_personales.py <slug>            (dry-run, solo reporta)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).resolve().parent))

from book_config import resolve  # noqa: E402
from glosas_personales_utils import (  # noqa: E402
    load_registry,
    apply_registry_to_interlineal,
    atomic_write_json,
)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('book', help='slug del libro')
    ap.add_argument('--apply', action='store_true', help='escribir cambios')
    args = ap.parse_args()

    cfg = resolve(args.book)
    path = cfg.final_json_path
    if not path.exists():
        print(f'{cfg.label}: no existe {path.name} — omitido')
        return

    registry = load_registry()
    n_global = len(registry.get('global', []))
    n_ctx = sum(
        1 for r in registry.get('contexto', [])
        if (r.get('match') or {}).get('book') == cfg.slug
    )
    if n_global == 0 and n_ctx == 0:
        print(f'{cfg.label}: sin reglas personales aplicables (global=0, contexto=0)')
        return

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    hits = apply_registry_to_interlineal(data, cfg.slug, registry)

    # Auto-capitalizar nombres propios (NPROP) con es en minúscula
    cap_count = 0
    for verse in data.get('verses', []):
        for pair in verse.get('pairs', []):
            for hw in pair.get('he_words', []):
                morph = (hw.get('he_morph') or '').strip()
                if 'NPROP' not in morph:
                    continue
                es = (hw.get('es') or '').strip()
                if es and es[0].islower():
                    hw['es'] = es[0].upper() + es[1:]
                    cap_count += 1

    if args.apply:
        atomic_write_json(path, data, separators=(',', ':'))
        estado = 'APLICADO'
    else:
        estado = 'DRY'

    cap_info = f', capitaliz={cap_count}' if cap_count else ''
    print(
        f'{cfg.label}: glosas personales reaplicadas — '
        f'{hits} tokens (global={n_global}, contexto[{cfg.slug}]={n_ctx}{cap_info}) ({estado})'
    )


if __name__ == '__main__':
    main()
