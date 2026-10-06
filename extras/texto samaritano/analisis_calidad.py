"""
Análisis de Calidad - Lectura Samaritana de Génesis
====================================================
Mide el porcentaje de vocalización correcta usando indicadores objetivos.

Como no existe un "gold standard" digital del texto vocalizado samaritano,
medimos la calidad por criterios fonológicos verificables (Ben-Hayyim):
  1. Alineación consonantal MT<->SP
  2. Cobertura de vocalización (cada palabra tiene vocales)
  3. Ausencia de residuos masoréticos (sheva móvil, cholam-o, etc.)
  4. Aplicación correcta de reglas samaritanas
"""
import sys, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Niqqud constants
SHEVA='\u05B0'; HATAF_S='\u05B1'; HATAF_P='\u05B2'; HATAF_Q='\u05B3'
CHIRIK='\u05B4'; TSERE='\u05B5'; SEGOL='\u05B6'; PATACH='\u05B7'
QAMATS='\u05B8'; CHOLAM='\u05B9'; CHOLAM_H='\u05BA'; QUBUTS='\u05BB'
DAGESH='\u05BC'; SHIN_DOT='\u05C1'; SIN_DOT='\u05C2'
ALL_VOWELS={SHEVA,HATAF_S,HATAF_P,HATAF_Q,CHIRIK,TSERE,SEGOL,PATACH,QAMATS,CHOLAM,CHOLAM_H,QUBUTS}
HATAFS={HATAF_S,HATAF_P,HATAF_Q}

ALEF='\u05D0'; HE='\u05D4'; HET='\u05D7'; AYIN='\u05E2'
MEM='\u05DE'; MEM_F='\u05DD'; YOD='\u05D9'; VAV='\u05D5'; KAF_F='\u05DA'
GUTTURALS={ALEF,HE,HET,AYIN}

import os, glob
BASE = r'C:\Users\pik_y\Documents\TRADUCCION\texto samaritano'
if len(sys.argv) > 1:
    files = sys.argv[1:]
else:
    order = ['genesis','exodus','leviticus','numbers','deuteronomy']
    files = [os.path.join(BASE, f'{b}_lectura_samaritana.json') for b in order
             if os.path.exists(os.path.join(BASE, f'{b}_lectura_samaritana.json'))]

# Merge all books into one data structure for combined analysis
data = {'chapters': {}}
_book_idx = 0
for _fp in files:
    with open(_fp, 'r', encoding='utf-8') as f:
        _d = json.load(f)
    for _ch, _cd in _d['chapters'].items():
        data['chapters'][f'{_book_idx}_{_ch}'] = _cd
    _book_idx += 1
print(f"Libros analizados: {', '.join(os.path.basename(x).split('_')[0] for x in files)}\n")

total = 0
aligned = 0
exact = 0
fuzzy = 0
mt_only = 0
sp_only = 0
lex_filled = 0
voc_global = 0

# Quality indicators (problems)
residual_hataf = 0       # hatafs should be gone (R3)
residual_mobile_sheva = 0 # mobile sheva mid-word (R7b should fix)
residual_cholam = 0      # cholam-o should be qubuts/shuruq (R5)
no_vowel_at_all = 0      # multi-consonant word with zero vowels (suspicious)
has_vowels = 0
transformed = 0          # sam differs from MT raw (a rule fired)

# Positive checks
plural_em_ok = 0
plural_im_bad = 0
vav_voweled = 0
vav_total = 0

problem_examples = {'hataf':[], 'mobile_sheva':[], 'cholam':[], 'no_vowel':[]}

def get_vowels_in(s):
    return [c for c in s if c in ALL_VOWELS]

def has_shuruq(s):
    """Shuruq = vav+dagesh acts as the vowel /u/."""
    units = parse(s)
    for c, d in units:
        if c == VAV and DAGESH in d:
            return True
    return False

def parse(s):
    """Parse into (cons,[dia]) units."""
    units=[]; cc=None; cd=[]
    for ch in s:
        cp=ord(ch)
        if 0x05D0<=cp<=0x05EA:
            if cc is not None: units.append((cc,cd))
            cc=ch; cd=[]
        elif ch in ALL_VOWELS or ch in (DAGESH,SHIN_DOT,SIN_DOT):
            cd.append(ch)
    if cc is not None: units.append((cc,cd))
    return units

for ch_num, chapter in data['chapters'].items():
    for v_num, verse in chapter.items():
        for w in verse['words']:
            total += 1
            sam = w['sam_reading']
            mt = w['mt']
            sp = w['sp_cons']

            m = w.get('match', 'exact' if w.get('aligned') else '')
            if m == 'exact':
                exact += 1; aligned += 1
            elif m == 'fuzzy':
                fuzzy += 1; aligned += 1
            elif m == 'mt_only' or (mt and not sp):
                mt_only += 1
            elif m == 'sp_only' or (sp and not mt):
                sp_only += 1
            if w.get('vocal_source') == 'lexicon':
                lex_filled += 1
            # global vocalization coverage over ALL tokens
            if get_vowels_in(sam) or has_shuruq(sam):
                voc_global += 1

            # Skip words with no MT source (can't be vocalized)
            if not mt:
                continue

            units = parse(sam)
            ncons = len(units)
            vowels = get_vowels_in(sam)

            if vowels or has_shuruq(sam):
                has_vowels += 1
            elif ncons > 1:
                no_vowel_at_all += 1
                if len(problem_examples['no_vowel']) < 10:
                    problem_examples['no_vowel'].append((mt, sam))

            # Transformed check
            if sam != mt and sam.replace('\u05bd','') != mt:
                # crude: compare stripped of cantillation
                transformed += 1

            # Residual hataf (should be 0 after R3)
            if any(v in HATAFS for v in vowels):
                residual_hataf += 1
                if len(problem_examples['hataf']) < 10:
                    problem_examples['hataf'].append((mt, sam))

            # Residual cholam (should be qubuts/shuruq after R5)
            if CHOLAM in vowels or CHOLAM_H in vowels:
                residual_cholam += 1
                if len(problem_examples['cholam']) < 10:
                    problem_examples['cholam'].append((mt, sam))

            # Mobile sheva mid-word (sheva not at end, not last consonant)
            for i in range(len(units)-1):
                if SHEVA in units[i][1]:
                    # it's mid-word
                    residual_mobile_sheva += 1
                    if len(problem_examples['mobile_sheva']) < 10:
                        problem_examples['mobile_sheva'].append((mt, sam))
                    break

            # Plural -em vs -im
            if sp.endswith('ים') and len(sp) > 3:
                last_v = None
                for c in reversed(sam):
                    if c in ALL_VOWELS:
                        last_v = c; break
                if last_v == TSERE:
                    plural_em_ok += 1
                elif last_v == CHIRIK:
                    plural_im_bad += 1

            # Vav conjunction
            if sp == 'ו':
                vav_total += 1
                if vowels:
                    vav_voweled += 1

# ============================================================
# REPORT
# ============================================================
vocalizable = total - sp_only  # words that have an MT source to vocalize

print("="*70)
print("ANÁLISIS DE CALIDAD - GÉNESIS (Lectura Samaritana)")
print("="*70)

print(f"\n[1] COBERTURA ESTRUCTURAL")
print(f"  Palabras totales (tokens):        {total}")
print(f"  Emparejadas MT<->SP:              {aligned} ({aligned/total*100:.1f}%)")
print(f"    - exactas:                      {exact} ({exact/total*100:.1f}%)")
print(f"    - difusas (matres lectionis):   {fuzzy} ({fuzzy/total*100:.1f}%)")
print(f"  Vocalizables (con fuente MT):     {vocalizable}")
print(f"  Solo en SP (sin vocalizar):       {sp_only} ({sp_only/total*100:.1f}%)")
print(f"  Solo en MT (plus masoretico):     {mt_only}")

print(f"\n[2] COBERTURA DE VOCALIZACIÓN")
print(f"  Palabras con vocales:             {has_vowels} ({has_vowels/vocalizable*100:.1f}% de vocalizables)")
print(f"  Multi-consonante SIN vocal:       {no_vowel_at_all} ({no_vowel_at_all/vocalizable*100:.2f}%)")

print(f"\n[3] RESIDUOS MASORÉTICOS (errores fonológicos)")
print(f"  Hatafs sin convertir (R3):        {residual_hataf} ({residual_hataf/vocalizable*100:.2f}%)")
print(f"  Sheva móvil medial (R7b):         {residual_mobile_sheva} ({residual_mobile_sheva/vocalizable*100:.2f}%)")
print(f"  Cholam-o sin convertir (R5):      {residual_cholam} ({residual_cholam/vocalizable*100:.2f}%)")

total_problems = no_vowel_at_all + residual_hataf + residual_mobile_sheva + residual_cholam
clean = vocalizable - total_problems
print(f"\n[4] PUNTUACIÓN GLOBAL")
print(f"  Palabras 'limpias' (sin residuos): {clean} de {vocalizable}")
print(f"  >>> CALIDAD FONOLÓGICA:            {clean/vocalizable*100:.1f}%")

print(f"\n[5] VERIFICACIÓN DE REGLAS CLAVE")
tot_plural = plural_em_ok + plural_im_bad
if tot_plural:
    print(f"  Plural masc -em correcto:         {plural_em_ok}/{tot_plural} ({plural_em_ok/tot_plural*100:.1f}%)")
if vav_total:
    print(f"  Vav conjuncion vocalizada:        {vav_voweled}/{vav_total} ({vav_voweled/vav_total*100:.1f}%)")

print(f"\n[6] EJEMPLOS DE RESIDUOS (para depurar)")
for k, ex in problem_examples.items():
    if ex:
        print(f"\n  {k} ({len(ex)} mostrados):")
        for mt, sam in ex[:6]:
            print(f"    MT={mt}  ->  SAM={sam}")

# Composite score
print(f"\n{'='*70}")
print("RESUMEN EJECUTIVO")
print(f"{'='*70}")
align_score = aligned/total*100
phon_score = clean/vocalizable*100
print(f"  Emparejamiento MT<->SP:    {align_score:.1f}%  (exacto {exact/total*100:.1f}% + difuso {fuzzy/total*100:.1f}%)")
print(f"  Rellenado lexico (SP-only):{lex_filled} palabras")
print(f"  Calidad fonologica:        {phon_score:.1f}%")
print(f"  >>> VOCALIZACION TOTAL:    {voc_global}/{total} = {voc_global/total*100:.2f}%  (TODOS los tokens)")
