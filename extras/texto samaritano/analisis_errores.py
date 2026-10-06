import json
import re
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

with open(r'C:\Users\pik_y\Documents\TRADUCCION\texto samaritano\genesis_lectura_samaritana.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print("=== Análisis de la Vocalización Samaritana en Génesis ===")

# Recolectar estadísticas y ejemplos
sheva_count = 0
initial_sheva = []
final_sheva = []
medial_sheva = []
plural_im = []
diphthong_ayim = []
guttural_hataf = []
suffix_2ms = []

for ch_num, chapter in data['chapters'].items():
    for v_num, verse in chapter.items():
        for word in verse['words']:
            sam = word['sam_reading']
            mt = word['mt']
            sp_cons = word['sp_cons']
            
            # Buscar shevas (U+05B0)
            if '\u05B0' in sam:
                sheva_count += 1
                # Check position of sheva
                parts = sam.split('\u05B0')
                if sam.startswith('\u05B0') or (len(sam)>1 and sam[1] == '\u05B0'):
                    initial_sheva.append((mt, sam))
                elif sam.endswith('\u05B0'):
                    final_sheva.append((mt, sam))
                else:
                    medial_sheva.append((mt, sam))
            
            # Buscar plurales -im vs -em
            if sp_cons.endswith('ים') and len(sp_cons) > 2:
                plural_im.append((mt, sam))
                
            # Sufijo 2ms ךָ
            if mt.endswith('ךָ') or mt.endswith('כָ'):
                suffix_2ms.append((mt, sam))

print(f"Total palabras con Sheva residual: {sheva_count}")
print(f"  Shevas iniciales (deberían ser 0): {len(initial_sheva)}")
if initial_sheva:
    print(f"  Ejemplos: {initial_sheva[:5]}")
    
print(f"  Shevas finales (deberían ser 0): {len(final_sheva)}")
if final_sheva:
    print(f"  Ejemplos: {final_sheva[:5]}")
    
print(f"  Shevas mediales (algunos son quiescentes, válidos): {len(medial_sheva)}")
if medial_sheva:
    print(f"  Ejemplos: {medial_sheva[:10]}")

print("\n--- Revisión de Plurales Masculinos (-im -> -em) ---")
im_count = 0
em_count = 0
for mt, sam in plural_im:
    # Find the last vowel in the word
    last_vowel = None
    for ch in reversed(sam):
        if '\u05B0' <= ch <= '\u05BB':
            last_vowel = ch
            break
            
    if last_vowel == '\u05B4': # Chirik
        im_count += 1
    elif last_vowel == '\u05B5': # Tsere
        em_count += 1
print(f"Plurales con Chirik final (-im, incorrecto): {im_count}")
print(f"Plurales con Tsere final (-em, correcto): {em_count}")
if im_count > 0:
    print("Ejemplos de plurales incorrectos (-im):")
    print([x for x in plural_im if (lambda s: next((c for c in reversed(s) if '\u05B0'<=c<='\u05BB'), None) == '\u05B4')(x[1])][:10])

print("\n--- Revisión de Sufijo 2ms (MT: -kha ךָ) ---")
print("En Samaritano, el sufijo 2ms suele ser -ak (sin vocal final) o -ek.")
print(f"Ejemplos generados: {suffix_2ms[:10]}")

print("\n--- Revisión de Guturales (Ej. אלהים) ---")
elohim_samples = []
for ch_num, chapter in data['chapters'].items():
    for v_num, verse in chapter.items():
        for word in verse['words']:
            if word['sp_cons'] == 'אלהים':
                elohim_samples.append(word['sam_reading'])
print(f"Ejemplos de 'Elohim': {list(set(elohim_samples))[:5]}")

print("\n--- Revisión de la conjunción Vav ---")
vav_samples = []
for ch_num, chapter in data['chapters'].items():
    for v_num, verse in chapter.items():
        for word in verse['words']:
            if word['sp_cons'] == 'ו':
                vav_samples.append(word['sam_reading'])
print(f"Ejemplos de Vav conjunción: {list(set(vav_samples))[:10]}")
