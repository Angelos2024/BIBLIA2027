"""
Verifica la fidelidad del corpus respecto al Pentateuco Samaritano (SP):
  - Conteo de capitulos y versos por libro, comparado con el Masoretico (MT).
  - Totales de palabras exclusivas SP / exclusivas MT (variantes a nivel palabra).
  - Revision de pasajes-clave donde el SP difiere notablemente del MT
    (mandamiento del Gerizim, Dt 27:4 Gerizim vs Ebal, genealogias Gn 5 y 11).
  - Detector de posibles EXPANSIONES: versos cuyo texto consonantico SP es
    mucho mas largo que el masoretico (indicio de "plus" samaritano).

Solo lectura. No modifica nada.
"""
import json, os, sys, unicodedata

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.abspath(__file__))
ORDER = ['genesis', 'exodus', 'leviticus', 'numbers', 'deuteronomy']

# Conteo canonico de versos del Texto Masoretico (MT)
MT_VERSES = {
    'genesis': 1533, 'exodus': 1213, 'leviticus': 859,
    'numbers': 1288, 'deuteronomy': 955,
}
MT_CHAPTERS = {
    'genesis': 50, 'exodus': 40, 'leviticus': 27,
    'numbers': 36, 'deuteronomy': 34,
}

# Pasajes donde el SP presenta diferencias famosas frente al MT
PASAJES = {
    'exodus': [('20', '17'), ('20', '21')],
    'deuteronomy': [('5', '18'), ('5', '21'), ('27', '4'), ('11', '29')],
    'genesis': [('5', '3'), ('5', '6'), ('11', '12'), ('11', '14')],
}

def cons_len(s):
    """Cuenta solo consonantes (ignora niqqud/marcas y espacios)."""
    return sum(1 for ch in s if not unicodedata.category(ch).startswith('M')
               and not ch.isspace())

print('=' * 72)
print('VERIFICACION DE FIDELIDAD AL PENTATEUCO SAMARITANO')
print('=' * 72)

tot_v = 0
for b in ORDER:
    path = os.path.join(BASE, f'{b}_lectura_samaritana.json')
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    chaps = data['chapters']
    nch = len(chaps)
    nv = sum(len(chaps[c]) for c in chaps)
    tot_v += nv
    st = data.get('stats', {})
    print(f'\n## {b.upper()}')
    print(f'  Capitulos: {nch:>4}  (MT: {MT_CHAPTERS[b]})')
    print(f'  Versos:    {nv:>4}  (MT: {MT_VERSES[b]})  diff={nv-MT_VERSES[b]:+d}')
    print(f'  Palabras totales: {st.get("words_total","?")}  '
          f'SP-only: {st.get("words_sp_only","?")}  '
          f'MT-only: {st.get("words_mt_only","?")}')

print('\n' + '=' * 72)
print(f'TOTAL DE VERSOS: {tot_v}  (MT Tora: {sum(MT_VERSES.values())})')
print('=' * 72)

# ── Pasajes clave ──
print('\n\n### PASAJES CLAVE (SP vs MT) ###')
for b, refs in PASAJES.items():
    path = os.path.join(BASE, f'{b}_lectura_samaritana.json')
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    chaps = data['chapters']
    for ch, vs in refs:
        v = chaps.get(ch, {}).get(vs)
        print(f'\n-- {b} {ch}:{vs} --')
        if not v:
            print('   (no existe en el corpus)')
            continue
        spc = v.get('sp_consonantal', '')
        mtv = v.get('mt_vocalized', '')
        print(f'   SP cons ({cons_len(spc)} cons): {spc}')
        print(f'   MT voc  ({cons_len(mtv)} cons): {mtv}')

# ── Detector de expansiones ──
print('\n\n### POSIBLES EXPANSIONES (SP mucho mas largo que MT en un verso) ###')
print('Criterio: consonantes_SP - consonantes_MT >= 15 en el mismo verso\n')
flag = 0
for b in ORDER:
    path = os.path.join(BASE, f'{b}_lectura_samaritana.json')
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    chaps = data['chapters']
    for ch in sorted(chaps, key=int):
        for vs in sorted(chaps[ch], key=int):
            v = chaps[ch][vs]
            spc = v.get('sp_consonantal', '')
            mtv = v.get('mt_vocalized', '')
            d = cons_len(spc) - cons_len(mtv)
            if d >= 15:
                flag += 1
                print(f'  {b} {ch}:{vs}  (+{d} cons)')
print(f'\nTotal de versos marcados como posible expansion: {flag}')
print('\n(Si flag~0 => el corpus NO contiene las grandes expansiones del SP;')
print(' sigue la versificacion y extension del MT, con variantes solo de palabra.)')
