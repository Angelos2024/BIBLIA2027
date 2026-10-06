# -*- coding: utf-8 -*-
"""Propagación de glosas canónicas del rango revisado al rango futuro.

Toma como FUENTE el rango Gen 1:1 – Gen 14:12 (configurable) donde las glosas
ya están revisadas/corregidas por el usuario. Construye un canon de glosas
consistentes por clave (Strong, morph, prefix_es, prs_suffix.es) y lo
propaga al rango DESTINO (Gen 14:13 – 50:26 por defecto) escribiendo SOLO
el campo `es`.

Diseño
──────
* Una glosa es "canónica" cuando todas las ocurrencias en el rango fuente con
  la misma clave tienen el MISMO valor `es` (no se promedia, no se vota: solo
  unanimidad). Se exige al menos `--min-fuente` apariciones (2 por defecto).
* Se IGNORA todo NPROP/GENT (motor de transliteración aparte) y el
  Tetragrámaton (motor propio).
* Se RESPETA todo token del rango destino que tenga regla contextual personal
  (no se sobrescribe).
* La clave incluye `prefix_es` y `prs_suffix.es` para no mezclar variantes
  con/sin prefijos o sufijos pronominales (que afectan la glosa).
* Solo se toca el campo `es` de la palabra hebrea (stem). Hebrew, morfología,
  Strong, prefijos, sufijos, griego y métricas quedan intactos.

Uso
───
    # Auditoría/dry-run de Gen 1:1–14:12 → Gen 14:13–50:26
    python motores/scripts/propagar_glosas_canonicas.py --book genesis

    # Aplicar
    python motores/scripts/propagar_glosas_canonicas.py --book genesis --apply

    # Cambiar rangos
    python motores/scripts/propagar_glosas_canonicas.py --book genesis \
        --from 1:1 --to 14:12 --target-from 14:13 --target-to 50:26
"""
from __future__ import annotations

import argparse
import io
import json
import re
import shutil
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DATA = ROOT / 'data_master'
GLOSAS = ROOT / 'fuentes' / 'glosas_personales.json'

NIQ = re.compile(r'[\u0591-\u05C7]')


def consk(s: str) -> str:
    return ''.join(c for c in NIQ.sub('', s or '') if 0x05D0 <= ord(c) <= 0x05EA)


def parse_ref(s: str) -> tuple[int, int]:
    """Parsea 'cap:vers' a (ch, vs)."""
    if ':' not in s:
        return (int(s), 1)
    ch, vs = s.split(':', 1)
    return (int(ch), int(vs))


def in_range(ch: int, vs: int, lo: tuple[int, int], hi: tuple[int, int]) -> bool:
    if (ch, vs) < lo:
        return False
    if (ch, vs) > hi:
        return False
    return True


def es_nprop_o_gent(morph: str) -> bool:
    return morph == 'NPROP' or morph.startswith('GENT.')


def es_tetragramaton(hw: dict) -> bool:
    return consk(hw.get('he_form') or '') in ('יהוה', 'יהויה')


def prefix_es_tuple(hw: dict) -> tuple[str, ...]:
    pl = hw.get('prefix_es') or []
    if not isinstance(pl, list):
        return ()
    return tuple(str(x or '') for x in pl)


def prs_es(hw: dict) -> str:
    prs = hw.get('prs_suffix') or {}
    if isinstance(prs, dict):
        return str(prs.get('es') or '')
    return ''


def build_canon(
    d: dict,
    rango: tuple[tuple[int, int], tuple[int, int]],
    min_fuente: int,
) -> tuple[dict, dict]:
    """Construye:
      canon[key] = glosa_es  (cuando todas las ocurrencias coinciden y son ≥ min_fuente).
      vistos[key] = Counter de glosas vistas (para diagnóstico).
    Clave: (strong, morph, prefix_es_tuple, prs_es, consk).
    """
    visto: dict[tuple, Counter] = defaultdict(Counter)
    lo, hi = rango
    for v in d['verses']:
        ch, vs = v['chapter'], v['verse']
        if not in_range(ch, vs, lo, hi):
            continue
        for pi, p in enumerate(v.get('pairs') or []):
            for wi, hw in enumerate(p.get('he_words') or []):
                m = hw.get('he_morph') or ''
                if es_nprop_o_gent(m):
                    continue
                if es_tetragramaton(hw):
                    continue
                st = (hw.get('strongs') or '').strip()
                if not st:
                    continue
                es = (hw.get('es') or '').strip()
                if not es:
                    continue
                key = (st, m, prefix_es_tuple(hw), prs_es(hw), consk(hw.get('he_form') or ''))
                visto[key][es] += 1
    canon: dict[tuple, str] = {}
    for key, cnt in visto.items():
        total = sum(cnt.values())
        if total < min_fuente:
            continue
        if len(cnt) == 1:
            canon[key] = next(iter(cnt))
    return canon, visto


def cargar_ctx_protegidos(slug: str) -> set[tuple]:
    """Tokens (ch, vs, pi, wi) con regla contextual personal en `book=slug`."""
    if not GLOSAS.exists():
        return set()
    reg = json.loads(GLOSAS.read_text(encoding='utf-8'))
    prot = set()
    for r in reg.get('contexto') or []:
        m = r.get('match') or {}
        if m.get('book') == slug and m.get('role') == 'stem':
            prot.add((m.get('chapter'), m.get('verse'), m.get('pairIdx'), m.get('hwIdx')))
    return prot


def cargar_global_protegidos() -> set[str]:
    """Strongs con regla global personal (no se tocan)."""
    if not GLOSAS.exists():
        return set()
    reg = json.loads(GLOSAS.read_text(encoding='utf-8'))
    prot = set()
    for r in reg.get('global') or []:
        st = ((r.get('match') or {}).get('strongs') or '').strip()
        if st:
            prot.add(st)
    return prot


def proponer_cambios(
    d: dict,
    canon: dict,
    rango_destino: tuple[tuple[int, int], tuple[int, int]],
    ctx_prot: set[tuple],
    glob_prot: set[str],
) -> list[dict]:
    """Lista de cambios propuestos en el rango destino."""
    cambios = []
    lo, hi = rango_destino
    for v in d['verses']:
        ch, vs = v['chapter'], v['verse']
        if not in_range(ch, vs, lo, hi):
            continue
        for pi, p in enumerate(v.get('pairs') or []):
            for wi, hw in enumerate(p.get('he_words') or []):
                m = hw.get('he_morph') or ''
                if es_nprop_o_gent(m) or es_tetragramaton(hw):
                    continue
                st = (hw.get('strongs') or '').strip()
                if not st:
                    continue
                if st in glob_prot:
                    # ya gestionado por regla global: confiamos en su efecto
                    continue
                if (ch, vs, pi, wi) in ctx_prot:
                    continue
                key = (st, m, prefix_es_tuple(hw), prs_es(hw), consk(hw.get('he_form') or ''))
                if key not in canon:
                    continue
                viejo = (hw.get('es') or '').strip()
                nuevo = canon[key]
                if viejo == nuevo:
                    continue
                cambios.append({
                    'ch': ch, 'vs': vs, 'pi': pi, 'wi': wi,
                    'he_form': hw.get('he_form') or '',
                    'morph': m, 'strong': st,
                    'prefix_es': hw.get('prefix_es') or [],
                    'prs_es': prs_es(hw),
                    'viejo': viejo, 'nuevo': nuevo,
                })
    return cambios


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    ap = argparse.ArgumentParser()
    ap.add_argument('--book', default='genesis')
    ap.add_argument('--from', dest='src_from', default='1:1',
                    help='Inicio del rango fuente (ya revisado), formato cap:vers.')
    ap.add_argument('--to', dest='src_to', default='14:12',
                    help='Fin del rango fuente, formato cap:vers.')
    ap.add_argument('--target-from', default='14:13',
                    help='Inicio del rango destino.')
    ap.add_argument('--target-to', default='50:26',
                    help='Fin del rango destino.')
    ap.add_argument('--min-fuente', type=int, default=2,
                    help='Apariciones mínimas en fuente para considerar canónica.')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--max-detalle', type=int, default=50,
                    help='Filas detalladas a mostrar (0 = todas).')
    args = ap.parse_args()

    dm = DATA / f'{args.book}_final.json'
    if not dm.exists():
        print(f'No existe {dm}', file=sys.stderr)
        return 1

    d = json.loads(dm.read_text(encoding='utf-8'))
    rango_src = (parse_ref(args.src_from), parse_ref(args.src_to))
    rango_dst = (parse_ref(args.target_from), parse_ref(args.target_to))

    canon, visto = build_canon(d, rango_src, args.min_fuente)
    inconsistentes = {k: cnt for k, cnt in visto.items()
                      if k not in canon and sum(cnt.values()) >= args.min_fuente}

    ctx_prot = cargar_ctx_protegidos(args.book)
    glob_prot = cargar_global_protegidos()

    cambios = proponer_cambios(d, canon, rango_dst, ctx_prot, glob_prot)

    print(f"═══ PROPAGACIÓN DE GLOSAS CANÓNICAS ({'APPLY' if args.apply else 'DRY-RUN'}) ═══")
    print(f"  Fuente : {args.book} {args.src_from} → {args.src_to}")
    print(f"  Destino: {args.book} {args.target_from} → {args.target_to}")
    print(f"  Mínimo de apariciones en fuente para canon: {args.min_fuente}")
    print()
    print(f"Canon construido: {len(canon)} claves únicas con glosa consistente")
    print(f"Claves inconsistentes (varias glosas en fuente): {len(inconsistentes)}")
    print(f"Reglas globales personales (saltadas): {len(glob_prot)} Strongs")
    print(f"Reglas contextuales personales en {args.book}: {len(ctx_prot)} tokens")
    print()
    print(f"Cambios propuestos en rango destino: {len(cambios)}")
    if not cambios:
        return 0

    # Agrupar por Strong/morph para vista rápida
    por_strong = defaultdict(list)
    for c in cambios:
        por_strong[(c['strong'], c['morph'])].append(c)
    print("\n── Resumen por (Strong, morph) ──")
    items = sorted(por_strong.items(), key=lambda x: -len(x[1]))
    for (st, m), lista in items[:30]:
        ej = lista[0]
        viejos = Counter(c['viejo'] for c in lista)
        ej_viejo = ', '.join(f"{k!r}x{v}" for k, v in viejos.most_common(3))
        print(f"  {st:<8} {m:<22} n={len(lista):<4} "
              f"old[{ej_viejo}]  ->  new={ej['nuevo']!r}")
    if len(items) > 30:
        print(f"  ... y {len(items)-30} grupos más")

    if args.max_detalle:
        print("\n── Detalle (primeros) ──")
        for c in cambios[:args.max_detalle]:
            pref = ''.join(p+' ' for p in (c['prefix_es'] or []))
            prs = f"+{c['prs_es']}" if c['prs_es'] else ''
            print(f"  {c['ch']:>2}:{c['vs']:<2} p{c['pi']:>2}/w{c['wi']}  "
                  f"{c['he_form']:<18} {c['morph']:<22} {c['strong']:<7}  "
                  f"{pref!r:<10}{prs:<10}  {c['viejo']!r:<28} -> {c['nuevo']!r}")
        if len(cambios) > args.max_detalle:
            print(f"  ... y {len(cambios)-args.max_detalle} más")

    if args.apply:
        # aplicar
        idx = {(c['ch'], c['vs'], c['pi'], c['wi']): c['nuevo'] for c in cambios}
        applied = 0
        for v in d['verses']:
            ch, vs = v['chapter'], v['verse']
            for pi, p in enumerate(v.get('pairs') or []):
                for wi, hw in enumerate(p.get('he_words') or []):
                    key = (ch, vs, pi, wi)
                    if key in idx:
                        hw['es'] = idx[key]
                        applied += 1
        ts = time.strftime('%Y%m%d_%H%M%S')
        bak = dm.with_suffix(f'.json.bak_propagar_{ts}')
        shutil.copyfile(dm, bak)
        dm.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding='utf-8')
        print(f"\nAPLICADOS: {applied} cambios. backup {bak.name}")

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
