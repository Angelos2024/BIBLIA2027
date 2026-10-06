# -*- coding: utf-8 -*-
"""Inferir el Strong de tokens que NO lo tienen, a partir del propio corpus.

Muchos tokens (sobre todo formas con sufijo/constructo restauradas por OSHB)
quedaron con strongs="". Sin Strong, el motor de estilo no puede sugerir nada.
Este módulo aprende, de TODOS los tokens que SÍ tienen Strong, qué Strong
corresponde a cada (esqueleto consonántico, morfología); luego:

  • si hay un ganador claro  -> ASIGNA el Strong (solo capítulos ABIERTos).
  • si es ambiguo o sin datos -> lo deja en una LISTA para revisión (lógica
    gramatical/morfológica), exportable con --export.

Uso:
    python motores/scripts/inferir_strongs.py --book genesis --chapter 24
    python motores/scripts/inferir_strongs.py --book genesis --chapter 24 --apply
    python motores/scripts/inferir_strongs.py --book genesis --export tmp/sin_strong.json

NO toca capítulos CERRADOS (candado). NO modifica el campo 'es'. Con --apply
respalda el archivo antes de escribir.
"""
import argparse
import io
import json
import re
import shutil
import sys
import time
import unicodedata
from collections import defaultdict, Counter
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import candado
except Exception:
    candado = None

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / 'data_master'
CACHE = REPO / 'fuentes' / 'inferencia_strongs.json'
_NIQ = re.compile(r'[\u0591-\u05C7]')

MIN_N = 3        # muestras mínimas para sugerir
MIN_PCT = 85.0   # dominancia mínima del Strong ganador (sugerencia)

# Para AUTO-ASIGNAR (--apply) se exige más: solo esqueleto+morfología,
# dominancia >=APPLY_PCT y n>=APPLY_N, y NUNCA nombres divinos/transliterados
# (homógrafos peligrosos: adoni H113 vs Adonai H136, etc.).
APPLY_PCT = 90.0
APPLY_N = 5
# Nombres divinos + homógrafos peligrosos confirmados donde un lexema frecuente
# le roba el esqueleto a uno raro y la asignación quedaría CONTRA el sentido:
#   H7586 שָׁאוּל «Saúl»  vs  H7585 שְׁאוֹל «Sheol»  (esqueleto שאול, Gén 42:38)
#   H578  אָנָה «lamentar» vs H575 אָן/אָנָה «¿a dónde?» (esqueleto אנה, Gén 37:30)
NO_AUTOASIGNAR = {'H136', 'H430', 'H3069', 'H410', 'H3068', 'H1008',
                  'H7586', 'H578'}

# Guarda de HOMÓGRAFO: si el 2º candidato (lexema distinto) del mismo
# (esqueleto[,morf]) tiene una cuota real, la identidad es ambigua → NO
# auto-asignar (se manda a la lista con sugerencia). Evita meter el Strong de
# un lexema frecuente en un homógrafo raro.
HOMOG_PCT = 8.0   # cuota mínima del 2º candidato para considerarlo competidor
HOMOG_N = 3       # y con al menos estas muestras

_index = None    # cache del índice (esqueleto,morf) -> Counter(strong)


def consk(s):
    s = _NIQ.sub('', unicodedata.normalize('NFC', s or ''))
    return ''.join(c for c in s if 0x05D0 <= ord(c) <= 0x05EA)


def _norm_strong(st):
    st = (st or '').strip().upper()
    m = re.match(r'^([HG])0*(\d+)$', st)
    return f'{m.group(1)}{m.group(2)}' if m else st


def _flat(v):
    return [hw for p in (v.get('pairs') or []) for hw in (p.get('he_words') or [])]


def _data_mtime():
    return max((f.stat().st_mtime for f in DATA.glob('*_final.json')), default=0)


def build_index(rebuild=False):
    """Índice ganador (esqueleto[,morf]) -> (strong, pct, n), aprendido de TODOS
    los tokens del corpus que SÍ tienen Strong (la identidad léxica es universal).
    Se cachea en fuentes/inferencia_strongs.json y se rehace si los datos cambian."""
    global _index
    if _index is not None and not rebuild:
        return _index
    if not rebuild and CACHE.exists() and CACHE.stat().st_mtime >= _data_mtime():
        try:
            j = json.loads(CACHE.read_text(encoding='utf-8'))
            _index = ({tuple(k.split('|', 1)): tuple(v) for k, v in j['skm'].items()},
                      {k: tuple(v) for k, v in j['sk'].items()})
            return _index
        except Exception:
            pass
    by_skm = defaultdict(Counter)
    by_sk = defaultdict(Counter)
    for f in sorted(DATA.glob('*_final.json')):
        try:
            d = json.loads(f.read_text(encoding='utf-8'))
        except Exception:
            continue
        for v in d.get('verses', []):
            for hw in _flat(v):
                st = _norm_strong(hw.get('strongs'))
                sk = consk(hw.get('he_form'))
                if not st or not sk:
                    continue
                morph = (hw.get('he_morph') or '').strip()
                by_skm[(sk, morph)][st] += 1
                by_sk[sk][st] += 1

    def win(counter):
        """(strong_ganador, pct, n_total, strong_2º, pct_2º, n_2º). El 2º
        candidato permite detectar homógrafos (esqueleto compartido por dos
        lexemas distintos)."""
        tot = sum(counter.values())
        ordered = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
        st, c = ordered[0]
        r_st, r_c = ordered[1] if len(ordered) > 1 else ('', 0)
        return (st, round(100 * c / tot, 1), tot,
                r_st, round(100 * r_c / tot, 1), r_c)

    skm_win = {k: win(c) for k, c in by_skm.items()}
    sk_win = {k: win(c) for k, c in by_sk.items()}
    _index = (skm_win, sk_win)
    try:
        CACHE.write_text(json.dumps(
            {'_descripcion': 'Índice para inferir Strongs faltantes: (esqueleto|morf) '
                             'y (esqueleto) -> [strong, pct, n]. Generado por '
                             'inferir_strongs.py desde TODO el corpus.',
             'generado': time.strftime('%F %T'),
             'skm': {f'{k[0]}|{k[1]}': list(v) for k, v in skm_win.items()},
             'sk': {k: list(v) for k, v in sk_win.items()}},
            ensure_ascii=False), encoding='utf-8')
    except Exception:
        pass
    return _index


def _homog(w):
    """True si el registro (esqueleto[,morf]) es un HOMÓGRAFO: existe un 2º
    lexema distinto con cuota/muestras reales. Tolerante con cachés antiguas
    (3-tuplas) → sin datos de 2º candidato, asume que no hay homógrafo."""
    if len(w) < 6 or not w[3] or w[3] == w[0]:
        return False
    return w[5] >= HOMOG_N and w[4] >= HOMOG_PCT


def inferir(sk, morph, min_n=MIN_N, min_pct=MIN_PCT):
    """Devuelve (strong, pct, n, via) si hay ganador claro; None si no.
    Prioriza (esqueleto+morfología); si no basta, prueba solo esqueleto con
    dominancia más alta. Si detecta homógrafo, marca la vía con sufijo
    «-homog» para que NO se auto-asigne (solo quede como sugerencia)."""
    if not sk:
        return None
    skm_win, sk_win = build_index()
    w = skm_win.get((sk, morph))
    if w and w[2] >= min_n and w[1] >= min_pct:
        return (w[0], w[1], w[2], 'esq+morf-homog' if _homog(w) else 'esq+morf')
    w = sk_win.get(sk)
    if w and w[2] >= min_n and w[1] >= max(min_pct, 92.0):
        return (w[0], w[1], w[2], 'esqueleto-homog' if _homog(w) else 'esqueleto')
    return None


# ── Inferencia guiada por la GLOSA `es` (2ª capa, opt-in con --use-es) ────────
# Para los tokens que el esqueleto solo no resuelve (funcionales cortos, formas
# raras), la glosa española añade una 3ª clave muy desambiguante. Se blinda con:
#   · coherencia morfológica (el Strong debe ser de la misma clase que el token,
#     así evitamos PRON→H853 (PART) o PREP→H5975 (VERBO));
#   · exclusión de nombres divinos / homógrafos peligrosos (adon/aden/Adonai).
# Índices en memoria (no en disco) para no tocar el esquema de la caché.
_es_idx = None            # (by_skm_full, by_skm_h, by_sk_h)
_strong_mroot = None      # strong -> Counter(morph_root)
DIVINO_ES = {'H136', 'H430', 'H3069', 'H410', 'H3068', 'H1008', 'H113', 'H134',
             'H7586', 'H578'}
# Strongs que NO deben salir de la inferencia por `es`: homógrafos donde la glosa
# española del corpus está sistemáticamente equivocada, o variantes ARAMEAS que
# se cuelan en texto hebreo, envenenando la asignación:
#   H7455 רֹעַ «maldad»  vs  H7453 רֵעַ «compañero» (רֵעֵהוּ mal glosado «maldad»)
#   H3825 לְבַב arameo «corazón»  vs  H3824 לֵבָב hebreo (la Torá es hebreo)
#   H3028 יַד aramea «mano»       vs  H3027 יָד hebrea
NO_ES = {'H7455', 'H3825', 'H3028'}
_PUNT = re.compile(r'[¿?¡!.,;:]')


def _mroot(m):
    return (m or '').split('.')[0]


def _es_head(es):
    es = _PUNT.sub('', (es or '').strip().lower())
    parts = es.split()
    return parts[0] if parts else ''


def _es_norm(es):
    return _PUNT.sub('', (es or '').strip().lower()).strip()


def build_es_index(rebuild=False):
    global _es_idx, _strong_mroot
    if _es_idx is not None and not rebuild:
        return _es_idx, _strong_mroot
    by_skm_full = defaultdict(Counter)
    by_skm_h = defaultdict(Counter)
    by_sk_h = defaultdict(Counter)
    smr = defaultdict(Counter)
    for f in sorted(DATA.glob('*_final.json')):
        try:
            d = json.loads(f.read_text(encoding='utf-8'))
        except Exception:
            continue
        for v in d.get('verses', []):
            for hw in _flat(v):
                st = _norm_strong(hw.get('strongs'))
                sk = consk(hw.get('he_form'))
                if not st or not sk:
                    continue
                m = (hw.get('he_morph') or '').strip()
                smr[st][_mroot(m)] += 1
                es = hw.get('es') or ''
                if not es.strip():
                    continue
                by_skm_full[(sk, m, _es_norm(es))][st] += 1
                by_skm_h[(sk, m, _es_head(es))][st] += 1
                by_sk_h[(sk, _es_head(es))][st] += 1
    _es_idx = (by_skm_full, by_skm_h, by_sk_h)
    _strong_mroot = smr
    return _es_idx, _strong_mroot


def _morph_coherente(strong, token_morph):
    c = _strong_mroot.get(strong)
    if not c:
        return False
    tot = sum(c.values())
    return tot and (c.get(_mroot(token_morph), 0) / tot) >= 0.5


def _win_es(counter):
    tot = sum(counter.values())
    ordered = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    st, c = ordered[0]
    r_c = ordered[1][1] if len(ordered) > 1 else 0
    return st, round(100 * c / tot, 1), tot, round(100 * r_c / tot, 1)


def inferir_es(sk, morph, es):
    """(strong, pct, n, via) usando la glosa `es` como clave, con guardas de
    coherencia morfológica y exclusión de nombres divinos. None si no es seguro."""
    if not sk or not (es or '').strip():
        return None
    (by_skm_full, by_skm_h, by_sk_h), _ = build_es_index()

    def ok(w, minn, minpct, gap):
        return (w[2] >= minn and w[1] >= minpct and (w[1] - w[3]) >= gap
                and w[0] not in DIVINO_ES and w[0] not in NO_ES
                and _morph_coherente(w[0], morph))

    c = by_skm_full.get((sk, morph, _es_norm(es)))
    if c:
        w = _win_es(c)
        if ok(w, 3, 90.0, 20):
            return (w[0], w[1], w[2], 'esq+morf+es')
    c = by_skm_h.get((sk, morph, _es_head(es)))
    if c:
        w = _win_es(c)
        if ok(w, 4, 92.0, 25):
            return (w[0], w[1], w[2], 'esq+morf+esHead')
    c = by_sk_h.get((sk, _es_head(es)))
    if c:
        w = _win_es(c)
        if ok(w, 6, 94.0, 30):
            return (w[0], w[1], w[2], 'esq+esHead')
    return None


def _detect_compact(raw):
    return raw[:4000].count('\n') < 5


def procesar(book, chapter=None, apply=False, export=None, use_es=False):
    path = DATA / f'{book}_final.json'
    if not path.exists():
        print(f'No existe {path}')
        return 1
    raw = path.read_text(encoding='utf-8')
    d = json.loads(raw)

    asignables, ambiguos = [], []
    for v in d.get('verses', []):
        ch = v.get('chapter')
        if chapter is not None and ch != chapter:
            continue
        for pi, p in enumerate(v.get('pairs') or []):
            for wi, hw in enumerate(p.get('he_words') or []):
                if (hw.get('strongs') or '').strip():
                    continue
                he = (hw.get('he_form') or '').strip()
                if not he:
                    continue                        # slot estructural vacío
                es = (hw.get('es') or '').strip()
                sk = consk(he)
                morph = (hw.get('he_morph') or '').strip()
                rec = {'ch': ch, 'vs': v.get('verse'), 'pi': pi, 'wi': wi,
                       'he': he, 'sk': sk, 'morph': morph,
                       'es': es, 'gr': hw.get('gr_word')}
                inf = inferir(sk, morph)
                cerrado = bool(candado and candado.esta_bloqueado(book, ch))
                # AUTO-ASIGNABLE solo si es seguro (esq+morf, alto, no divino).
                auto = bool(inf and inf[3] == 'esq+morf'
                            and inf[0] not in NO_AUTOASIGNAR
                            and inf[1] >= APPLY_PCT and inf[2] >= APPLY_N)
                if auto:
                    rec.update({'strong': inf[0], 'pct': inf[1], 'n': inf[2],
                                'via': inf[3], 'cerrado': cerrado})
                    asignables.append((v, hw, rec))
                    continue
                # 2ª capa: inferencia guiada por `es` (opt-in), con guardas.
                inf_es = inferir_es(sk, morph, es) if use_es else None
                if inf_es:
                    rec.update({'strong': inf_es[0], 'pct': inf_es[1],
                                'n': inf_es[2], 'via': inf_es[3], 'cerrado': cerrado})
                    asignables.append((v, hw, rec))
                    continue
                if inf:                              # sugerencia (no auto) para la lista
                    rec.update({'sugerencia': inf[0], 'pct': inf[1],
                                'n': inf[2], 'via': inf[3]})
                ambiguos.append(rec)

    etiqueta = f'{book} cap {chapter}' if chapter else f'{book} (completo)'
    print(f'═══ INFERIR STRONG · {etiqueta} · {"APPLY" if apply else "REPORTE"} ═══')
    print(f'  Sin strong: {len(asignables)+len(ambiguos)}  ·  '
          f'inferibles: {len(asignables)}  ·  a lista (ambiguo/sin datos): {len(ambiguos)}\n')

    print('■ INFERIBLES (esqueleto+morfología → Strong)')
    for _, _, r in asignables[:80]:
        lk = ' [CERRADO]' if r['cerrado'] else ''
        print(f"   {r['ch']:>3}:{r['vs']:<3} p{r['pi']:>2}/w{r['wi']} {r['he']:<12} "
              f"{r['morph']:<20} → {r['strong']} ({r['pct']}%, n={r['n']}, {r['via']}){lk}")
    if len(asignables) > 80:
        print(f'   … y {len(asignables)-80} más')

    print(f'\n■ A LISTA — revisar por lógica/morfología ({len(ambiguos)})')
    for r in ambiguos[:60]:
        hint = (f" · ¿{r['sugerencia']}? ({r['pct']}%, n={r['n']}, {r['via']})"
                if r.get('sugerencia') else '')
        print(f"   {r['ch']:>3}:{r['vs']:<3} p{r['pi']:>2}/w{r['wi']} {r['he']:<12} "
              f"{r['morph']:<20} · es={r['es']!r}{hint}")
    if len(ambiguos) > 60:
        print(f'   … y {len(ambiguos)-60} más')

    if export:
        Path(export).write_text(json.dumps(
            {'book': book, 'chapter': chapter, 'generated': time.strftime('%F %T'),
             'inferibles': [r for _, _, r in asignables],
             'a_lista': ambiguos}, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'\nEXPORT lista → {export}')

    if not apply:
        print('\n(REPORTE. Use --apply para ASIGNAR los inferibles en capítulos ABIERTOS.)')
        return 0

    n = 0
    for v, hw, r in asignables:
        if r['cerrado']:
            continue                       # candado: no tocar cerrados
        hw['strongs'] = r['strong']
        hw['strongs_source'] = f'inferido:{r["via"]}:{r["pct"]}%'
        n += 1
    if n:
        ts = time.strftime('%Y%m%d_%H%M%S')
        bk = path.with_suffix(f'.json.bak_inferstrong_{ts}')
        shutil.copyfile(path, bk)
        if _detect_compact(raw):
            path.write_text(json.dumps(d, ensure_ascii=False,
                            separators=(',', ':')), encoding='utf-8')
        else:
            path.write_text(json.dumps(d, ensure_ascii=False, indent=1),
                            encoding='utf-8')
        try:
            CACHE.unlink()               # datos cambiaron: refrescar índice
        except OSError:
            pass
        print(f'\nASIGNADOS: {n} strongs (solo capítulos abiertos) · respaldo {bk.name}')
    else:
        print('\nNo hubo strongs asignables en capítulos abiertos.')
    return 0


def main():
    ap = argparse.ArgumentParser(description='Inferir/asignar Strongs faltantes.')
    ap.add_argument('--book', default='genesis')
    ap.add_argument('--chapter', type=int)
    ap.add_argument('--apply', action='store_true',
                    help='asigna los inferibles (solo capítulos ABIERTOS, con respaldo)')
    ap.add_argument('--export', metavar='RUTA.json',
                    help='vuelca la lista (inferibles + a_lista) a JSON')
    ap.add_argument('--build', action='store_true',
                    help='(re)construye el índice de inferencia en caché y sale')
    ap.add_argument('--use-es', action='store_true',
                    help='2ª capa: infiere con la glosa `es` como clave (guardas '
                         'de coherencia morfológica + exclusión de nombres divinos)')
    args = ap.parse_args()
    if args.build:
        skm, sk = build_index(rebuild=True)
        print(f'Índice reconstruido: {len(skm)} (esq+morf) · {len(sk)} (esq) → {CACHE.name}')
        return 0
    return procesar(args.book, args.chapter, args.apply, args.export, args.use_es)


if __name__ == '__main__':
    raise SystemExit(main())
