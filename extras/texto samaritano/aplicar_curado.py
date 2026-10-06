"""
Aplicación del diccionario curado a los 5 libros
=================================================
Tras motor_samaritano.py y rellenar_lexico.py quedan ~73 tokens (palabras
genuinamente exclusivas del SP) con vocal_source='none'. Este paso aplica las
reconstrucciones eruditas de diccionario_curado.json a esas palabras.

  - Empareja por consonantes exactas (clave = w['sp_cons']).
  - Solo toca palabras 'sp_only' aún no vocalizadas.
  - Marca w['vocal_source'] = 'curado' y w['sim'] = 1.0.
  - Actualiza el verse['sam_reading'].
  - Crea un respaldo con marca de tiempo antes de reescribir.

Uso: ejecutar DESPUÉS de rellenar_lexico.py
"""
import sys, json, os, re, shutil, datetime
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

NIQQUD = lambda c: '\u05B0' <= c <= '\u05BB'
DAGESH = '\u05BC'
VAV = '\u05D5'

def norm_key(s):
    """Canonicaliza shin/sin: el corpus usa precompuestos U+FB2A/FB2B,
    el diccionario usa shin base (U+05E9) + punto combinante."""
    return s.replace('\uFB2A', '\u05E9\u05C1').replace('\uFB2B', '\u05E9\u05C2')

def is_vocalized(s):
    if any(NIQQUD(c) for c in s):
        return True
    prev = ''
    for c in s:
        if c == DAGESH and prev == VAV:
            return True
        prev = c
    return False

BASE = r'C:\Users\pik_y\Documents\TRADUCCION\texto samaritano'
ORDER = ['genesis', 'exodus', 'leviticus', 'numbers', 'deuteronomy']
paths = {b: os.path.join(BASE, f'{b}_lectura_samaritana.json') for b in ORDER}

with open(os.path.join(BASE, 'diccionario_curado.json'), encoding='utf-8') as f:
    curado_raw = json.load(f)['entradas']
curado = {norm_key(k): v for k, v in curado_raw.items()}
print(f"Diccionario curado: {len(curado)} entradas")

STAMP = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

per_book = {}
total_filled = 0
total_missed = 0
missed_forms = {}

for b in ORDER:
    with open(paths[b], encoding='utf-8') as f:
        data = json.load(f)

    # Respaldo con marca de tiempo (no pisa los .bak.json existentes)
    shutil.copy(paths[b], os.path.join(BASE, f'{b}_lectura_samaritana.precurado_{STAMP}.json'))

    filled = 0
    missed = 0
    for ch, chap in data['chapters'].items():
        for vs, verse in chap.items():
            changed = False
            for w in verse['words']:
                if w.get('match') != 'sp_only':
                    continue
                if is_vocalized(w['sam_reading']):
                    continue
                rd = curado.get(norm_key(w['sp_cons']))
                if rd:
                    w['sam_reading'] = rd
                    w['vocal_source'] = 'curado'
                    w['sim'] = 1.0
                    filled += 1
                    changed = True
                else:
                    missed += 1
                    missed_forms[w['sp_cons']] = missed_forms.get(w['sp_cons'], 0) + 1
            if changed:
                verse['sam_reading'] = ' '.join(x['sam_reading'] for x in verse['words'])

    data.setdefault('stats', {})['curado_filled'] = filled
    with open(paths[b], 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    per_book[b] = (filled, missed)
    total_filled += filled
    total_missed += missed

print(f"\n{'='*60}\nAPLICACIÓN DEL DICCIONARIO CURADO\n{'='*60}")
for b in ORDER:
    fl, ms = per_book[b]
    print(f"  {b:13} curadas={fl:3}  sin resolver={ms:3}")
print(f"  {'TOTAL':13} curadas={total_filled:3}  sin resolver={total_missed:3}")
print(f"\n  Respaldo: *_lectura_samaritana.precurado_{STAMP}.json")

if missed_forms:
    print(f"\n  Formas aún sin entrada en el diccionario ({len(missed_forms)}):")
    for cons, n in sorted(missed_forms.items(), key=lambda x: -x[1]):
        print(f"    {cons:20} x{n}")
