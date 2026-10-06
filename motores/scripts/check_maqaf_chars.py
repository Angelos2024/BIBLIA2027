# -*- coding: utf-8 -*-
"""Verifica los codepoints exactos del maqaf en he_form del JSON."""
import json, sys, pathlib
sys.stdout.reconfigure(encoding='utf-8')

MAQAF = '\u05be'
DATA = pathlib.Path(r'C:\Users\pik_y\Documents\TRADUCCION\data\genesis_final.json')
data = json.loads(DATA.read_text(encoding='utf-8'))

# Buscar los primeros 10 he_forms con maqaf y mostrar sus codepoints
found = 0
for verse in data['verses']:
    if found >= 10: break
    for pair in verse.get('pairs', []):
        for hw in pair.get('he_words', []):
            he = hw.get('he_form', '')
            if MAQAF in he:
                ref = f"{verse['chapter']}:{verse['verse']}"
                cps = ' '.join(f'U+{ord(c):04X}({c})' for c in he)
                print(f"{ref:6s}  {he}  →  {cps}")
                found += 1
                if found >= 10: break
        if found >= 10: break

# Verificar si las formas OSHB sin maqaf son distintas de las que sí tienen
print("\n--- Muestra de אֶת con y sin maqaf ---")
for verse in data['verses']:
    for pair in verse.get('pairs', []):
        for hw in pair.get('he_words', []):
            he = hw.get('he_form', '')
            if 'את' in he or 'אֶת' in he:
                ref = f"{verse['chapter']}:{verse['verse']}"
                cps = ' '.join(f'U+{ord(c):04X}' for c in he)
                print(f"{ref:6s}  {he!r}  cps={cps}")
                break
    else: continue
    break
