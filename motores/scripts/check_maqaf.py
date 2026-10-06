# -*- coding: utf-8 -*-
"""
Auditoría de maqaf (U+05BE ־) en genesis_final.json.
El OSHB incluye ־ nativamente en he_form cuando procede.
Verifica: 1) formas con maqaf vs. formas sin maqaf pero raw lo indica,
          2) muestra ejemplos representativos por capítulo.
"""
import json, sys, collections, pathlib
sys.stdout.reconfigure(encoding='utf-8')

MAQAF = '\u05be'
DATA  = pathlib.Path(r'C:\Users\pik_y\Documents\TRADUCCION\data\genesis_final.json')
data  = json.loads(DATA.read_text(encoding='utf-8'))

# Rastrear todas las formas con maqaf
maqaf_words  = []   # (ref, he_form, es, gr_word)
# Rastrear formas donde he_form está vacío pero el raw CATSS implica maqaf (termina en -)
# excluyendo meta-notaciones
suspect = []

META_PREFIXES = ('=%p', '{!}', '=')

for verse in data['verses']:
    ref = f"{verse['chapter']}:{verse['verse']}"
    for pair in verse.get('pairs', []):
        for hw in pair.get('he_words', []):
            raw = hw.get('raw', '')
            he  = hw.get('he_form', '')
            es  = hw.get('es', '')
            gr  = hw.get('gr_word', '')

            if MAQAF in he:
                maqaf_words.append((ref, he, es, gr))

            # Detectar raw CATSS con maqaf pero he_form sin él y no es meta
            if raw.endswith('-') and MAQAF not in he:
                is_meta = any(raw.startswith(p) for p in META_PREFIXES)
                if not is_meta and he:
                    suspect.append((ref, raw, he, es))

# Contar por forma base
freq = collections.Counter(hw[1] for hw in maqaf_words)
print(f"=== TOTAL he_forms con maqaf: {len(maqaf_words)} ocurrencias, {len(freq)} formas únicas ===\n")

print("Top 20 formas más frecuentes:")
for form, count in freq.most_common(20):
    print(f"  {form:<20}  ×{count}")

print(f"\n=== SOSPECHOSOS: raw termina en '-' pero he_form sin ־ ({len(suspect)}) ===")
for ref, raw, he, es in suspect:
    print(f"  {ref:8s}  raw={raw:<20}  he={he!r}  es={es}")

print(f"\n=== MUESTRA Gen 1:11 (casos זַרְעוֹ־ y בּוֹ) ===")
v111 = next(v for v in data['verses'] if v['chapter']==1 and v['verse']==11)
for pi, p in enumerate(v111['pairs']):
    for hw in p.get('he_words', []):
        he = hw.get('he_form', '')
        if MAQAF in he or hw.get('raw') == 'B/W':
            print(f"  PAIR {pi:02d}  he={he!r}  raw={hw['raw']!r}  es={hw['es']!r}  gr={hw['gr_word']!r}")
