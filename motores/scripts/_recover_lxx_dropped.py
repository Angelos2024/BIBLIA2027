"""Recupera griego de la LXX que se perdió en la alineación.

Cuando la segmentación hebrea del json difiere de la del .par CATSS, parte del
griego de pares 'align' no se asigna a ninguna palabra hebrea y se pierde
(queda solo como '----' en el hebreo). El griego es una capa independiente y NO
debe pasarse por alto: este script detecta ese griego ausente por versículo y lo
reinserta como pares gk_add (capa griega), respetando el orden del .par, sin
tocar el orden ni el contenido hebreo.

Idempotente: elimina sus propios pares (recovered_lxx=True) antes de recalcular.

Uso: python _recover_lxx_dropped.py <slug> [--apply]
"""
import json, sys, re, unicodedata
from collections import Counter
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
from book_config import resolve
from populate_greek_catss import parse_par

APPLY = '--apply' in sys.argv
SLUG = next((a for a in sys.argv[1:] if a != '--apply'), None)
GREEK = re.compile(r'[\u0370-\u03FF\u1F00-\u1FFF]')
DIAC = re.compile(r'[\u0300-\u036f\u0345]')


def norm(t):
    n = unicodedata.normalize('NFD', t.lower())
    n = DIAC.sub('', n)
    n = ''.join(ch for ch in n if ch.isalpha())
    return n.replace('ς', 'σ')


def gk_tokens(s):
    """[(norm, original)] solo de tokens con letras griegas reales."""
    out = []
    for t in (s or '').split():
        if GREEK.search(t):
            n = norm(t)
            if n:
                out.append((n, t))
    return out


def make_pair(text):
    return {
        'he': '', 'he_unicode': '', 'he_note': '',
        'gr': '', 'gr_unicode': text, 'kind': 'gk_add',
        'isApparatusPrefix': False, 'isGreekOmitted': False,
        'recovered_lxx': True,
    }


def main():
    cfg = resolve(SLUG)
    d = json.loads(cfg.final_json_path.read_text(encoding='utf-8'))
    par = parse_par(cfg.par_path, cfg.catss_ref_label)

    recovered = 0
    verses_touched = 0

    # Griego que ya vive en pseudo-versos ADD+ (is_lxx_add): pertenece al mismo
    # cv y NO debe re-insertarse en el verso principal.
    from collections import defaultdict
    addplus_cov = defaultdict(Counter)
    for v in d['verses']:
        if not v.get('is_lxx_add'):
            continue
        cv = (v.get('chapter'), v.get('verse'))
        for p in v.get('pairs', []):
            for n, _ in gk_tokens(p.get('gr_unicode')):
                addplus_cov[cv][n] += 1
            for hw in p.get('he_words', []):
                for pg in (hw.get('prefix_gr') or []):
                    for n, _ in gk_tokens(pg):
                        addplus_cov[cv][n] += 1
                for n, _ in gk_tokens(hw.get('gr_word')):
                    addplus_cov[cv][n] += 1

    for v in d['verses']:
        if v.get('is_lxx_add'):
            continue
        cv = (v.get('chapter'), v.get('verse'))
        par_pairs = par.get(cv)
        if not par_pairs:
            continue

        pairs = v.get('pairs', [])
        # quitar recuperados previos (idempotencia)
        pairs = [p for p in pairs if not p.get('recovered_lxx')]

        # stream de tokens del json en orden, con índice de par
        stream = []  # [norm, pair_idx, alive]
        for idx, p in enumerate(pairs):
            if p.get('kind') == 'gk_add':
                for n, _ in gk_tokens(p.get('gr_unicode')):
                    stream.append([n, idx, True])
                continue
            for hw in p.get('he_words', []):
                for pg in (hw.get('prefix_gr') or []):
                    for n, _ in gk_tokens(pg):
                        stream.append([n, idx, True])
                for n, _ in gk_tokens(hw.get('gr_word')):
                    stream.append([n, idx, True])
                prs = hw.get('prs_suffix') or {}
                if isinstance(prs, dict):
                    for n, _ in gk_tokens(prs.get('gr_word')):
                        stream.append([n, idx, True])

        # índice por token-norm para consumo rápido
        pos = defaultdict(list)
        for si, ent in enumerate(stream):
            pos[ent[0]].append(si)
        extra_cov = Counter(addplus_cov.get(cv, {}))

        def consume(n):
            # 1) cubierto por un pseudo-verso ADD+ (no cambia posición)
            if extra_cov.get(n, 0) > 0:
                extra_cov[n] -= 1
                return ('cov', None)
            # 2) cubierto por un par del verso principal
            for si in pos.get(n, []):
                if stream[si][2]:
                    stream[si][2] = False
                    return ('cov', stream[si][1])
            return None

        # recorrer .par en orden; recolectar residuo con insert_after
        last_jpi = -1
        runs = []        # [(insert_after, [origs])]
        cur = None       # (insert_after, [origs], last_par_idx)
        for pi, pp in enumerate(par_pairs):
            # Saltar dobletes de transposición CATSS (he='{...}'): el griego ahí
            # es la LXX en su propio orden y DUPLICA texto ya alineado. El hebreo
            # manda el orden, así que no lo re-mostramos.
            if '{' in (pp.get('he') or ''):
                continue
            for n, orig in gk_tokens(pp.get('gr_unicode')):
                res = consume(n)
                if res is not None:
                    if res[1] is not None:
                        last_jpi = res[1]
                    # corta el run en curso si había
                    if cur is not None:
                        runs.append((cur[0], cur[1]))
                        cur = None
                else:
                    # residuo
                    if cur is None or cur[2] != pi - 1 and cur[2] != pi:
                        if cur is not None:
                            runs.append((cur[0], cur[1]))
                        cur = [last_jpi, [orig], pi]
                    else:
                        cur[1].append(orig)
                        cur[2] = pi
        if cur is not None:
            runs.append((cur[0], cur[1]))

        if not runs:
            if APPLY:
                v['pairs'] = pairs
            continue

        # construir nueva lista insertando runs tras su insert_after
        by_after = defaultdict(list)
        for after, origs in runs:
            by_after[after].append(' '.join(origs))
            recovered += 1
        new_pairs = []
        for txt in by_after.get(-1, []):
            new_pairs.append(make_pair(txt))
        for idx, p in enumerate(pairs):
            new_pairs.append(p)
            for txt in by_after.get(idx, []):
                new_pairs.append(make_pair(txt))
        if APPLY:
            v['pairs'] = new_pairs
        verses_touched += 1

    print(f'{cfg.label}: {recovered} bloques griegos recuperados en {verses_touched} versos '
          + ('(APLICADO)' if APPLY else '(DRY)'))
    if APPLY:
        cfg.final_json_path.write_text(json.dumps(d, ensure_ascii=False, indent=None), encoding='utf-8')


if __name__ == '__main__':
    main()
