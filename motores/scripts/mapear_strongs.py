"""Genera el MAPEO y LISTA de los Strong disponibles en el interlineal.

Recorre todos los data_master/*_final.json y agrega, por número Strong:
  - total de ocurrencias (solo raíces/stems con Strong)
  - glosas distintas (equivalencias) con su conteo  -> detecta "equivalencias distintas"
  - formas hebreas y formas consonánticas distintas
  - morfologías distintas
  - libros donde aparece

Salidas:
  fuentes/mapa_strongs.json   -> mapa completo {strong: {...}}  (consumible por el visor)
  fuentes/mapa_strongs.csv    -> lista plana ordenada por nº de equivalencias y frecuencia
  _mapa_strongs_report.txt    -> resumen + Strongs con MÚLTIPLES equivalencias (a revisar)

Uso:
  python mapear_strongs.py
"""
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA_DIR = REPO / 'data_master'
FUENTES = REPO / 'fuentes'

_CONS_RE1 = re.compile(r'[\u0591-\u05BD\u05BF\u05C1-\u05C7\u05BE\u05C0\u05F3\u05F4]')
_CONS_RE2 = re.compile(r'[\s\-\u05BE\u2013]+')


def consonants_only(s):
    if not s:
        return ''
    return _CONS_RE2.sub('', _CONS_RE1.sub('', s)).strip()


def norm_strong(raw):
    if not raw:
        return ''
    m = re.match(r'^([HG])0*(\d+)', str(raw).strip().upper())
    return f'{m.group(1)}{m.group(2)}' if m else str(raw).strip().upper()


def main():
    glosses = defaultdict(Counter)      # strong -> Counter(es)
    forms = defaultdict(Counter)        # strong -> Counter(he_form)
    morphs = defaultdict(set)           # strong -> {morph}
    books = defaultdict(set)            # strong -> {book}
    totals = Counter()                  # strong -> total

    for fp in sorted(DATA_DIR.glob('*_final.json')):
        slug = fp.stem.replace('_final', '')
        try:
            data = json.loads(fp.read_text(encoding='utf-8'))
        except Exception:
            continue
        for v in data.get('verses', []):
            for p in v.get('pairs', []):
                if p.get('kind') == 'gk_add':
                    continue
                for hw in p.get('he_words', []):
                    st = norm_strong(hw.get('strongs', ''))
                    if not st:
                        continue
                    es = (hw.get('es') or '').strip()
                    glosses[st][es if es else '∅'] += 1
                    he = hw.get('he_form') or ''
                    if he:
                        forms[st][he] += 1
                    if hw.get('he_morph'):
                        morphs[st].add(hw['he_morph'])
                    books[st].add(slug)
                    totals[st] += 1

    mapa = {}
    for st in sorted(totals):
        gl = glosses[st].most_common()
        distinct_es = [g for g, _ in gl if g != '∅']
        mapa[st] = {
            'total': totals[st],
            'distinct_glosses': len(distinct_es),
            'multiple_equiv': len(distinct_es) > 1,
            'glosses': [{'es': g, 'count': c} for g, c in gl],
            'forms': sorted(forms[st].keys()),
            'consonant_forms': sorted({consonants_only(f) for f in forms[st]}),
            'morphs': sorted(morphs[st]),
            'books': sorted(books[st]),
        }

    FUENTES.mkdir(parents=True, exist_ok=True)
    (FUENTES / 'mapa_strongs.json').write_text(
        json.dumps(mapa, ensure_ascii=False, indent=2), encoding='utf-8')

    # CSV plano: una fila por Strong
    with open(FUENTES / 'mapa_strongs.csv', 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['strong', 'total', 'n_equivalencias', 'multiple',
                    'glosas (es:count)', 'formas', 'morfos', 'libros'])
        for st, m in sorted(mapa.items(),
                            key=lambda kv: (-kv[1]['distinct_glosses'], -kv[1]['total'])):
            w.writerow([
                st, m['total'], m['distinct_glosses'],
                'SI' if m['multiple_equiv'] else '',
                ' | '.join(f"{g['es']}:{g['count']}" for g in m['glosses']),
                ' '.join(m['forms'][:8]),
                ' '.join(m['morphs'][:8]),
                ' '.join(m['books']),
            ])

    multi = [(st, m) for st, m in mapa.items() if m['multiple_equiv']]
    multi.sort(key=lambda kv: (-kv[1]['distinct_glosses'], -kv[1]['total']))

    report = []
    report.append(f'Strongs distintos: {len(mapa)}')
    report.append(f'Ocurrencias totales (con Strong): {sum(totals.values())}')
    report.append(f'Strongs con MÚLTIPLES equivalencias: {len(multi)}')
    report.append('')
    report.append('=== TOP Strongs con equivalencias distintas (revisar) ===')
    for st, m in multi[:120]:
        gl = ', '.join(f"{g['es']!r}×{g['count']}" for g in m['glosses'] if g['es'] != '∅')
        report.append(f"{st}  total={m['total']}  equiv={m['distinct_glosses']}  formas={' '.join(m['consonant_forms'][:4])}")
        report.append(f"      {gl}")
    (REPO / '_mapa_strongs_report.txt').write_text('\n'.join(report), encoding='utf-8')

    print(f"strongs={len(mapa)} multi_equiv={len(multi)} "
          f"occ={sum(totals.values())}")


if __name__ == '__main__':
    main()
