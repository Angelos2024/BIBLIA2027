"""Motor de propagación de glosas españolas entre libros.

Idea: cuando un libro (p. ej. genesis) queda revisado, sus glosas ES se pueden
"copiar" a otro libro (p. ej. exodo) emparejando por la IDENTIDAD de la palabra
(Strong + forma consonántica + morfología). Así se ahorra el llenado manual:
las palabras iguales heredan tu traducción ya pulida.

Qué propaga:
  · RAÍCES (hw['es'])           — el grueso del trabajo.
  · SUFIJOS pronominales (es)   — por morfología (PRS.P3.M.SG -> "su", etc.).
  · PREFIJOS (opcional, --prefijos) — función corta; desactivado por defecto
    porque suele depender del contexto (género del artículo, etc.).

Qué NUNCA toca:
  · H3068 (Tetragrámaton): lo resuelve el enrutado por vocal del motor, no se
    copia (evita poner "Hashem" sobre Adonai/'Elohim).
  · Glosas ya CURADAS a mano en el destino (es_source 'glosa_*', 'regla_*',
    'fix:*'): se respetan; nunca se sobrescriben.

Predicado de llenado en destino (qué celdas se rellenan):
  · modo 'vacios' : solo si el destino está vacío o trae fuga inglesa '[EN:'.
  · modo 'auto'   : además, si el destino viene de relleno AUTOMÁTICO
    (es_source 'auto:*' o sin fuente) — recomendado para ahorrar llenado.
  · modo 'todo'   : sobrescribe todo salvo lo curado a mano en destino.

Solidez "conforme avanzas":
  El motor solo debe aprender de lo que YA revisaste. Usa --hasta N para que
  construya el mapa únicamente con los capítulos 1..N de la fuente. Conforme
  avanzas en Génesis, subes N y el motor "se solidifica": más cobertura, misma
  fiabilidad. Además exige mayoría (--min-ratio) y respeta lo curado a mano.

Uso:
  # Vista previa aprendiendo solo de lo revisado (p. ej. hasta cap. 9):
  python propagar_glosas.py --source genesis --target exodo --modo auto --hasta 9
  # Ver qué claves son ambiguas (no se propagan) hasta cap. 9:
  python propagar_glosas.py --source genesis --hasta 9 --audit
  # Aplicar (con respaldo), ya con Génesis terminado:
  python propagar_glosas.py --source genesis --target exodo --modo auto --apply
  # A TODOS los libros menos la fuente:
  python propagar_glosas.py --source genesis --target ALL --modo auto --apply
"""
from __future__ import annotations
import argparse
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA_DIR = REPO / 'data_master'

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# Fuentes consideradas "curadas a mano" en el DESTINO: nunca se sobrescriben.
CURATED_PREFIXES = ('glosa_', 'regla_', 'fix:')
EN_LEAK = re.compile(r'\[EN:')

# Strongs que NUNCA se propagan (marcadores/partículas o casos especiales):
#   H3068 Tetragrámaton -> lo enruta el motor por vocal.
#   H853  marcador de objeto (אֵת) -> no traducible; debe quedar vacío.
SKIP_STRONGS = {'H3068', 'H853'}


def norm_strong(raw):
    if not raw:
        return ''
    m = re.match(r'^([HG])0*(\d+)', str(raw).upper())
    return f'{m.group(1)}{m.group(2)}' if m else str(raw).upper()


def cons(s):
    return re.sub(r'[^\u05d0-\u05ea]', '', s or '')


def is_en_or_empty(es):
    e = (es or '').strip()
    return (not e) or bool(EN_LEAK.search(e))


def is_curated(src):
    s = (src or '')
    return any(s.startswith(p) for p in CURATED_PREFIXES)


def load_book(slug):
    p = DATA_DIR / f'{slug}_final.json'
    if not p.exists():
        raise SystemExit(f'No existe el libro: {p}')
    return p, json.loads(p.read_text(encoding='utf-8'))


# ── Construcción del mapa de glosas desde la fuente ─────────────────────────
def build_maps(data, max_ch=None, min_count=1, min_ratio=0.5, audit=None):
    """Construye el mapa de glosas desde la fuente. Solidez ("conforme avanzas"):

      · max_ch   : aprende SOLO de capítulos <= max_ch (los ya revisados).
      · curado   : si para una clave hay alguna glosa curada a mano, esa gana.
      · confianza: para claves sin curar, la glosa elegida debe ser MAYORÍA
        (>= min_ratio) y aparecer al menos min_count veces; si hay empate o
        dispersión (palabra polisémica), NO se propaga (se evita el error).
      · audit    : lista (opcional) de claves descartadas por baja confianza.

    Empareja SOLO por Strong (+forma+morfología). Devuelve (stem_strong, suf_map).
    """
    all_c = defaultdict(Counter)   # (strong, cons, morph) -> Counter(es)  todos
    cur_c = defaultdict(Counter)   # idem, solo glosas curadas a mano
    suf_a = defaultdict(Counter)   # suf_morph -> Counter(es)

    for v in data.get('verses', []):
        if max_ch is not None and v.get('chapter', 0) > max_ch:
            continue
        for p in v.get('pairs', []):
            if p.get('kind') == 'gk_add':
                continue
            for w in p.get('he_words', []):
                st = norm_strong(w.get('strongs'))
                if not st or st in SKIP_STRONGS:
                    continue  # sin Strong / Tetragrámaton / marcador objeto
                es = (w.get('es') or '').strip()
                if es and not EN_LEAK.search(es):
                    c = cons(w.get('he_form') or w.get('stem_unicode') or '')
                    mo = (w.get('he_morph') or '').strip()
                    if c:
                        all_c[(st, c, mo)][es] += 1
                        if is_curated(w.get('es_source')):
                            cur_c[(st, c, mo)][es] += 1
                suf = w.get('prs_suffix')
                if isinstance(suf, dict):
                    ses = (suf.get('es') or '').strip()
                    if ses:
                        suf_a[(suf.get('he_morph') or '').strip()][ses] += 1

    stem = {}
    for k, counter in all_c.items():
        if cur_c.get(k):                       # 1) lo que curaste a mano manda
            stem[k] = cur_c[k].most_common(1)[0][0]
            continue
        es, n = counter.most_common(1)[0]      # 2) si no, exige mayoría clara
        total = sum(counter.values())
        if n >= min_count and (n / total) >= min_ratio:
            stem[k] = es
        elif audit is not None:
            audit.append((k, dict(counter)))

    suf = {}
    for k, counter in suf_a.items():
        es, n = counter.most_common(1)[0]
        if n / sum(counter.values()) >= min_ratio:
            suf[k] = es
    return stem, suf


# ── Aplicación al destino ───────────────────────────────────────────────────
def should_fill(es, src, modo):
    if is_curated(src):
        return False                      # nunca pisar lo curado a mano
    if is_en_or_empty(es):
        return True                       # vacío o fuga inglesa: siempre
    if modo == 'vacios':
        return False
    if modo == 'auto':
        s = (src or '')
        return (s == '') or s.startswith('auto')
    if modo == 'todo':
        return True
    return False


def apply_maps(data, maps, modo):
    stem_strong, suf_map = maps
    changes = []
    for v in data.get('verses', []):
        for p in v.get('pairs', []):
            if p.get('kind') == 'gk_add':
                continue
            for w in p.get('he_words', []):
                st = norm_strong(w.get('strongs'))
                if not st or st in SKIP_STRONGS:
                    continue
                c = cons(w.get('he_form') or w.get('stem_unicode') or '')
                mo = (w.get('he_morph') or '').strip()
                cand = None
                if c:
                    cand = stem_strong.get((st, c, mo)) or stem_strong.get((st, c, ''))
                if cand and cand != (w.get('es') or '').strip():
                    if should_fill(w.get('es'), w.get('es_source'), modo):
                        changes.append((v['chapter'], v['verse'], w.get('he_form'),
                                        w.get('es'), cand))
                        w['es'] = cand
                        w['es_source'] = 'propagado'
                # sufijo pronominal (solo si está vacío)
                suf = w.get('prs_suffix')
                if isinstance(suf, dict) and not (suf.get('es') or '').strip():
                    sc = suf_map.get((suf.get('he_morph') or '').strip())
                    if sc:
                        suf['es'] = sc
                        suf['es_source'] = 'propagado'
    return changes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', default='genesis')
    ap.add_argument('--target', default='exodo', help="slug o 'ALL'")
    ap.add_argument('--modo', choices=['vacios', 'auto', 'todo'], default='vacios')
    ap.add_argument('--hasta', type=int, default=None,
                    help='aprende SOLO de capítulos <= N de la fuente (lo revisado)')
    ap.add_argument('--min-count', type=int, default=1,
                    help='mínimo de apariciones de la glosa ganadora')
    ap.add_argument('--min-ratio', type=float, default=0.5,
                    help='la glosa ganadora debe ser >= este porcentaje (0-1)')
    ap.add_argument('--audit', action='store_true',
                    help='lista claves descartadas por baja confianza y termina')
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    _, src_data = load_book(args.source)
    audit_list = [] if args.audit else None
    maps = build_maps(src_data, max_ch=args.hasta, min_count=args.min_count,
                      min_ratio=args.min_ratio, audit=audit_list)
    alcance = f'cap 1-{args.hasta}' if args.hasta else 'todo el libro'
    print(f'Mapa desde {args.source} ({alcance}): '
          f'{len(maps[0])} raíces(Strong+forma+morf) · {len(maps[1])} sufijos '
          f'· confianza>={args.min_ratio:.0%}, min {args.min_count}')

    if args.audit:
        print(f'\n== AUDITORÍA: {len(audit_list)} claves ambiguas descartadas ==')
        for (st, c, mo), opts in sorted(audit_list, key=lambda x: -sum(x[1].values()))[:40]:
            print(f'   {st} {c} {mo}: {opts}')
        return

    if args.target.upper() == 'ALL':
        targets = [p.stem.replace('_final', '') for p in sorted(DATA_DIR.glob('*_final.json'))
                   if p.stem.replace('_final', '') != args.source]
    else:
        targets = [args.target]

    grand = 0
    for slug in targets:
        path, data = load_book(slug)
        changes = apply_maps(data, maps, args.modo)
        grand += len(changes)
        print(f'\n== {slug}: {len(changes)} celdas a rellenar (modo={args.modo}) ==')
        for ch, vs, he, old, new in changes[:15]:
            print(f'   {slug} {ch}:{vs} {he!r}  {old!r} -> {new!r}')
        if len(changes) > 15:
            print(f'   ... (+{len(changes) - 15})')
        if args.apply and changes:
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            shutil.copy2(path, path.with_suffix(f'.json.bak_propagar_{ts}'))
            path.write_text(json.dumps(data, ensure_ascii=False,
                                       separators=(',', ':')), encoding='utf-8')
            print(f'   APLICADO (respaldo .bak_propagar_{ts})')

    print(f'\nTOTAL: {grand} celdas  ·  MODO {"APLICADO" if args.apply else "DRY-RUN"}')


if __name__ == '__main__':
    main()
