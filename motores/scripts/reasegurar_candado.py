# -*- coding: utf-8 -*-
"""
Barrido del candado: blinda todos los capítulos cerrados.

- Sella (captura estado actual) los capítulos cerrados que aún no tienen sello.
- Reasegura (restaura desde el sello) los que ya lo tienen, deshaciendo
  cualquier cambio que un proceso haya metido en un capítulo cerrado.

Correr después de CUALQUIER proceso por lotes, y una vez al iniciar sesión:
    python motores/scripts/reasegurar_candado.py
Opcional: --solo-sellar-faltantes  (no restaura, solo crea sellos que falten)
"""
import argparse
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, str(Path(__file__).resolve().parent))
import candado  # noqa: E402

DATA = Path(__file__).resolve().parents[2] / 'data_master'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--solo-sellar-faltantes', action='store_true')
    args = ap.parse_args()

    cfg = candado._load_cfg().get('candados', {})
    if not cfg:
        print('No hay candados definidos.')
        return 0

    for slug in cfg:
        path = DATA / f'{slug}_final.json'
        if not path.exists():
            print(f'[{slug}] archivo no encontrado, salto.')
            continue
        data = json.loads(path.read_text(encoding='utf-8'))
        bloq = sorted(candado.capitulos_bloqueados(slug))
        sellos = candado._load_sellos(slug)

        nuevos = 0
        for cap in bloq:
            if str(cap) not in sellos:
                if candado.sellar(slug, cap, data):
                    nuevos += 1
        sellados_ahora = sorted(int(k) for k in candado._load_sellos(slug))
        print(f'[{slug}] cerrados={bloq} · sellos nuevos={nuevos} · sellados={sellados_ahora}')

        if not args.solo_sellar_faltantes:
            restaurados = candado.reasegurar(slug, data)
            if restaurados:
                candado_bak = path.with_suffix('.json.bak_reaseg')
                candado_bak.write_bytes(path.read_bytes())
                path.write_text(json.dumps(data, ensure_ascii=False,
                                           separators=(',', ':')), encoding='utf-8')
                print(f'   ↻ RESTAURADOS {restaurados} versos desde sello (respaldo {candado_bak.name})')
            else:
                print('   ✓ sin desviaciones en capítulos cerrados')
    print('\nCandados:', candado.resumen())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
