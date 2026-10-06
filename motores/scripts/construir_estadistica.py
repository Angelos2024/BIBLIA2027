# -*- coding: utf-8 -*-
"""
Modelo estadístico de la redacción del usuario ("tu forma de escribir").

Aprende, a partir de los CAPÍTULOS CERRADOS (candado) —que son el estilo ya
finalizado y aprobado—, qué palabra española usa el usuario con MAYOR
frecuencia para cada palabra hebrea, distinguiendo forma/tiempo por morfología.

Genera fuentes/estadistica_glosas.json con, por cada (Strong, morfología):
   - glosas rankeadas por conteo y porcentaje
   - la "preferida" (mayor %) + n muestras + si es ambigua (polisémica)
y un nivel por lema (solo Strong) como respaldo.

Se REALIMENTA solo: cada vez que cierras capítulos y corres este script, el
modelo crece. Correr:
    python motores/scripts/construir_estadistica.py
    python motores/scripts/construir_estadistica.py --incluir-abiertos   (todo el corpus)
"""
import argparse
import io
import json
import re
import sys
import unicodedata
from collections import defaultdict, Counter
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, str(Path(__file__).resolve().parent))
import candado  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / 'data_master'
OUT = REPO / 'fuentes' / 'estadistica_glosas.json'

_NIQ = re.compile(r'[\u0591-\u05C7]')


def consk(s):
    s = _NIQ.sub('', s or '')
    return ''.join(c for c in s if 0x05D0 <= ord(c) <= 0x05EA)


def norm_es(s):
    return unicodedata.normalize('NFC', (s or '').strip())


def _norm_strong(st):
    st = (st or '').strip().upper()
    m = re.match(r'^([HG])0*(\d+)$', st)
    return f'{m.group(1)}{m.group(2)}' if m else st


def cargar_translit_strongs():
    """Strongs que se TRANSLITERAN por decisión editorial (no son elección de
    estilo, no deben entrar al modelo): tetragrámaton, apelativos divinos y la
    lista maestra fuentes/transliteraciones_lexemas.json. Se lee en cada build
    para mantenerse sincronizado."""
    excl = {'H3068', 'H430', 'H3069', 'H410', 'H1008', 'H136'}
    try:
        t = json.loads((REPO / 'fuentes' / 'transliteraciones_lexemas.json')
                       .read_text(encoding='utf-8'))
        for lx in t.get('lexemas', []):
            for s in lx.get('strongs', []):
                excl.add(_norm_strong(s))
    except Exception:
        pass
    return excl


def cargar_translit_skeletons():
    """Esqueletos consonánticos que se transliteran (para excluir del índice por
    esqueleto, que sí incluye tokens SIN strong). Tetragrámaton + raíces de la
    lista maestra. NO se añade 'אל' porque colisiona con la preposición אֶל."""
    sks = {'יהוה'}
    try:
        t = json.loads((REPO / 'fuentes' / 'transliteraciones_lexemas.json')
                       .read_text(encoding='utf-8'))
        for lx in t.get('lexemas', []):
            r = (lx.get('root') or '').strip()
            if r and r != 'אל':
                sks.add(r)
    except Exception:
        pass
    return sks


def construir(incluir_abiertos=False, min_n=2, verbose=True):
    """Construye estadistica_glosas.json. Devuelve (n_strongs, n_formas)."""
    class _A:
        pass
    args = _A()
    args.incluir_abiertos = incluir_abiertos
    args.min_n = min_n
    return _run(args, verbose)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--incluir-abiertos', action='store_true',
                    help='usa TODO el corpus (no solo capítulos cerrados)')
    ap.add_argument('--min-n', type=int, default=2,
                    help='muestras mínimas para registrar una (Strong,morf)')
    args = ap.parse_args()
    _run(args, verbose=True)
    return 0


def _run(args, verbose=True):
    # strongs -> morph -> Counter(glosa)   y   strongs -> Counter(glosa)
    by_sm = defaultdict(lambda: defaultdict(Counter))
    by_s = defaultdict(Counter)
    # contexto: st -> morph -> esqueleto_vecino -> Counter(glosa)  (prev y next)
    by_ctx_prev = defaultdict(lambda: defaultdict(lambda: defaultdict(Counter)))
    by_ctx_next = defaultdict(lambda: defaultdict(lambda: defaultdict(Counter)))
    # índice POR ESQUELETO consonántico (respaldo cuando el token no tiene Strong)
    by_skm = defaultdict(lambda: defaultdict(Counter))
    by_ctx_prev_sk = defaultdict(lambda: defaultdict(lambda: defaultdict(Counter)))
    by_ctx_next_sk = defaultdict(lambda: defaultdict(lambda: defaultdict(Counter)))
    fuentes_caps = defaultdict(set)   # libro -> set caps usados
    translit_strongs = cargar_translit_strongs()
    translit_sks = cargar_translit_skeletons()
    n_excl_translit = 0

    for f in sorted(DATA.glob('*_final.json')):
        slug = f.name.replace('_final.json', '')
        cerrados = candado.capitulos_bloqueados(slug)
        if not args.incluir_abiertos and not cerrados:
            continue
        d = json.loads(f.read_text(encoding='utf-8'))
        for v in d['verses']:
            ch = v.get('chapter')
            if not args.incluir_abiertos and ch not in cerrados:
                continue
            # tokens en orden lineal del versículo (para vecinos prev/next)
            flat = [hw for p in (v.get('pairs') or [])
                    if p.get('kind') != 'gk_add'
                    for hw in (p.get('he_words') or [])]
            for i, hw in enumerate(flat):
                es = norm_es(hw.get('es'))
                if not es:
                    continue
                morph = (hw.get('he_morph') or '').strip()
                st = _norm_strong(hw.get('strongs'))
                sk = consk(hw.get('he_form'))
                # EXCLUIR transliteraciones (no son elección de estilo):
                # nombres propios/gentilicios y lexemas/raíces transliterados.
                if ('NPROP' in morph or 'GENT' in morph
                        or (st and st in translit_strongs) or sk in translit_sks):
                    n_excl_translit += 1
                    continue
                # vecinos por esqueleto consonántico; '∅' marca borde de versículo.
                prev_ck = consk(flat[i - 1].get('he_form')) if i > 0 else '∅'
                next_ck = consk(flat[i + 1].get('he_form')) if i + 1 < len(flat) else '∅'
                prev_ck = prev_ck or '∅'
                next_ck = next_ck or '∅'
                if st:                                  # índice por Strong
                    by_sm[st][morph][es] += 1
                    by_s[st][es] += 1
                    by_ctx_prev[st][morph][prev_ck][es] += 1
                    by_ctx_next[st][morph][next_ck][es] += 1
                if sk:                                  # índice por esqueleto (fallback)
                    by_skm[sk][morph][es] += 1
                    by_ctx_prev_sk[sk][morph][prev_ck][es] += 1
                    by_ctx_next_sk[sk][morph][next_ck][es] += 1
                fuentes_caps[slug].add(ch)

    def rank(counter):
        tot = sum(counter.values())
        items = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
        return tot, [{'es': g, 'n': c, 'pct': round(100 * c / tot, 1)} for g, c in items]

    def ctx_winners(by_ck, min_n, min_pct=60.0):
        """Por cada esqueleto vecino, el ganador claro (n>=min_n, pct>=min_pct).
        Devuelve {esqueleto: {es, pct, n}} — solo contextos que DESAMBIGUAN."""
        out = {}
        for ckey, counter in by_ck.items():
            tot = sum(counter.values())
            if tot < min_n:
                continue
            g, c = max(counter.items(), key=lambda kv: (kv[1], kv[0]))
            pct = round(100 * c / tot, 1)
            if pct >= min_pct:
                out[ckey] = {'es': g, 'pct': pct, 'n': tot}
        return out

    model = {}
    for st, morphs in by_sm.items():
        tot_s, rank_s = rank(by_s[st])
        entry = {
            'total': tot_s,
            'lema_preferida': rank_s[0]['es'] if rank_s else None,
            'lema_pct': rank_s[0]['pct'] if rank_s else None,
            'lema_glosas': rank_s[:6],
            'lema_ambiguo': len([g for g in rank_s if g['n'] >= args.min_n]) > 1,
            'formas': {},
        }
        for morph, counter in morphs.items():
            tot, ranked = rank(counter)
            if tot < args.min_n:
                continue
            ambigua = len([g for g in ranked if g['n'] >= args.min_n]) > 1
            fe = {
                'total': tot,
                'preferida': ranked[0]['es'],
                'pct': ranked[0]['pct'],
                'ambigua': ambigua,
                'glosas': ranked[:6],
            }
            # Solo para formas AMBIGUAS aporta el contexto: qué glosa gana según
            # el vecino (esto es lo que hace que el modelo "aprenda tu criterio
            # por contexto" en vez de rendirse cuando usas varios términos).
            if ambigua:
                cp = ctx_winners(by_ctx_prev[st][morph], args.min_n)
                cn = ctx_winners(by_ctx_next[st][morph], args.min_n)
                if cp or cn:
                    fe['ctx'] = {'prev': cp, 'next': cn}
            entry['formas'][morph] = fe
        model[st] = entry

    # Índice por esqueleto (respaldo): solo combinaciones con señal suficiente.
    sk_model = {}
    sk_min = max(args.min_n, 3)
    for sk, morphs in by_skm.items():
        forms = {}
        for morph, counter in morphs.items():
            tot, ranked = rank(counter)
            if tot < sk_min:
                continue
            ambigua = len([g for g in ranked if g['n'] >= args.min_n]) > 1
            fe = {'total': tot, 'preferida': ranked[0]['es'],
                  'pct': ranked[0]['pct'], 'ambigua': ambigua,
                  'glosas': ranked[:5]}
            if ambigua:
                cp = ctx_winners(by_ctx_prev_sk[sk][morph], args.min_n)
                cn = ctx_winners(by_ctx_next_sk[sk][morph], args.min_n)
                if cp or cn:
                    fe['ctx'] = {'prev': cp, 'next': cn}
            forms[morph] = fe
        if forms:
            sk_model[sk] = forms

    payload = {
        'version': 1,
        'generado': __import__('datetime').date.today().isoformat(),
        '_descripcion': 'Modelo de frecuencia de glosas ES según la redacción del usuario. '
                        'Fuente: capítulos CERRADOS (candado) salvo --incluir-abiertos. '
                        'Clave: Strong -> morfología -> glosa preferida (mayor %). '
                        'Para formas AMBIGUAS se añade "ctx" {prev,next}: ganador por '
                        'esqueleto consonántico del vecino (desambiguación por contexto). '
                        'Lo usa revisar_es.py (ESTILO) para sugerir según tu uso y contexto. '
                        '"por_esqueleto" es el mismo modelo pero indexado por esqueleto '
                        'consonántico: respaldo para tokens SIN Strong (p.ej. מלאך→mensajero).',
        'fuente': {'solo_cerrados': not args.incluir_abiertos,
                   'min_n': args.min_n,
                   'capitulos': {k: sorted(v) for k, v in sorted(fuentes_caps.items())}},
        'lexemas': model,
        'por_esqueleto': sk_model,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')

    n_forms = sum(len(e['formas']) for e in model.values())
    if verbose:
        print(f'Modelo escrito: {OUT.name}')
        print(f'  Strongs: {len(model)}  ·  formas (Strong×morf): {n_forms}')
        print(f'  Esqueletos (fallback sin strong): {len(sk_model)}')
        print(f'  Excluidos por transliteración (NPROP/GENT/tetragr/lexemas): {n_excl_translit}')
        print(f'  Fuente: {"TODO el corpus" if args.incluir_abiertos else "capítulos cerrados"}')
        for k, v in sorted(fuentes_caps.items()):
            print(f'    {k}: {len(v)} capítulos')
        print('\n  Ejemplos (Strong · morf → preferida):')
        shown = 0
        for st, e in model.items():
            for morph, fe in e['formas'].items():
                if fe['total'] >= 5 and not fe['ambigua']:
                    print(f'    {st:7s} {morph:28s} → {fe["preferida"]!r} ({fe["pct"]}%, n={fe["total"]})')
                    shown += 1
            if shown >= 12:
                break
    return len(model), n_forms


if __name__ == '__main__':
    raise SystemExit(main())
