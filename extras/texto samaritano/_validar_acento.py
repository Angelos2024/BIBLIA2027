"""Validacion de la LONGITUD POSICIONAL por acento (Opcion C).
=================================================================
Compara la salida NUEVA del motor contra:
  (1) el VECTOR DE VALIDACION del experto (Genesis 1), y
  (2) la salida ANTERIOR (sin acento) capturada del pipeline, para ver
      EXACTAMENTE que palabras ganan un macron posicional.

No modifica ningun JSON. Solo imprime. Correr con:
    python _validar_acento.py
"""
import json, os, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import motor_gutural_fonetico as mgf

BASE = os.path.dirname(os.path.abspath(__file__))

# ── 1) Vector de validacion del experto (academica; å sin macron) ──
VECTOR = {
    'בָּרָא':       'bårå',
    'רָאשִׁית':     'råšīt',
    'שָּׁמֵים':      'šåmēim',
    'תָהוּם':       'tåum',
    'רוּחַ':        'rūa',
}

print('=' * 66)
print('1) VECTOR DE VALIDACION DEL EXPERTO  (debe seguir intacto)')
print('=' * 66)
ok = True
for heb, exp in VECTOR.items():
    got = mgf.translit_acad_word(heb)
    flag = 'OK ' if got == exp else '!! DIFERENCIA'
    if got != exp:
        ok = False
    print(f'  {flag}  {heb:14}  esperado={exp:10}  motor={got}')
print('  -> aluēim se valida con el sam_reading real del JSON (abajo).')

# ── 2) Antes/Despues sobre Genesis 1:1-3 (palabra por palabra) ──
# Salida ANTERIOR (sin acento), copiada del log del pipeline ya validado.
OLD = {
    '1': ('bå råšīt bårå aluēim ēt a šåmēim wå ēt å åraṣ'),
    '2': ('wå å åraṣ åyitå tū wå bū wå ušak al fånēi tåum wå rūa '
          'aluēim måraefat al fånēi a mēim'),
}

src = os.path.join(BASE, 'genesis_lectura_samaritana_e.json')
if not os.path.exists(src):
    src = os.path.join(BASE, 'genesis_lectura_samaritana.json')
with open(src, encoding='utf-8') as f:
    g = json.load(f)

print('\n' + '=' * 66)
print('2) ANTES -> DESPUES  (Genesis 1:1-3)   [* = cambio por acento]')
print('=' * 66)
total_changes = 0
for vs in ('1', '2', '3'):
    v = g['chapters']['1'][vs]
    words = [w for w in v.get('words', []) if w.get('sam_reading')]
    new_line = ' '.join(mgf.translit_acad_word(w['sam_reading']) for w in words)
    print(f'\nGn 1:{vs}')
    print(f'  AHORA: {new_line}')
    if vs in OLD:
        old_toks = OLD[vs].split(' ')
        new_toks = new_line.split(' ')
        diffs = [(o, n) for o, n in zip(old_toks, new_toks) if o != n]
        total_changes += len(diffs)
        if diffs:
            print('  CAMBIOS:')
            for o, n in diffs:
                print(f'     {o:14} ->  {n}')
        else:
            print('  (sin cambios)')

# ── 3) Palabras clave para que el experto confirme la regla de acento ──
print('\n' + '=' * 66)
print('3) GENESIS 1:3-5  (con la Condicion 1 ya: אור debe dar "ūr")')
print('=' * 66)
for vs in ('3', '4', '5'):
    v = g['chapters']['1'].get(vs, {})
    words = [w for w in v.get('words', []) if w.get('sam_reading')]
    if not words:
        continue
    line = ' '.join(mgf.translit_acad_word(w['sam_reading']) for w in words)
    print(f'\nGn 1:{vs}')
    print(f'  {line}')
    # marca palabras 'or' (אור) -> debe verse ūr
    for w in words:
        if w.get('sp_cons') in ('אור', 'אֹור') or w.get('gloss', '').lower().startswith('light'):
            print(f'     [luz] {w["sam_reading"]} -> {mgf.translit_acad_word(w["sam_reading"])}')

print('\n' + '=' * 66)
print(f'RESUMEN: vector {"OK" if ok else "REVISAR"} | '
      f'cambios en Gn 1:1-2 = {total_changes}')
print('=' * 66)
