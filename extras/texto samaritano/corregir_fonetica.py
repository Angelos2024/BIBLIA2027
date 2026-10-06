"""
Corrección fonética de la Lectura Samaritana
=============================================
Aplica dos correcciones post-procesamiento a los 5 JSON:

1. CHOLAM→QAMATS: En segolados nominales, participios qal, sustantivos
   patrón qotel, y las palabras כל, ערב, בקר. El motor R5 las convirtió
   a qubuts (/u/) cuando Ben-Hayyim indica qamats (/a/).
   Nombres propios y Elohim mantienen /u/.

2. DAGESH BKP: Añade dagesh a toda ב, כ/ך, פ/ף sin dagesh.
   En la tradición samaritana no hay espirantización → siempre plosivas.
   Solo BKP (no גדת): enfoque pragmático para lector de hebreo moderno.

Uso: python corregir_fonetica.py
"""
import sys, json, os, shutil, datetime
from collections import Counter
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── Unicode constants ──────────────────────────────
SHEVA='\u05B0'; HATAF_S='\u05B1'; HATAF_P='\u05B2'; HATAF_Q='\u05B3'
CHIRIK='\u05B4'; TSERE='\u05B5'; SEGOL='\u05B6'; PATACH='\u05B7'
QAMATS='\u05B8'; CHOLAM='\u05B9'; CHOLAM_H='\u05BA'; QUBUTS='\u05BB'
DAGESH='\u05BC'; SHIN_DOT='\u05C1'; SIN_DOT='\u05C2'
ALL_VOWELS={SHEVA,HATAF_S,HATAF_P,HATAF_Q,CHIRIK,TSERE,SEGOL,PATACH,QAMATS,CHOLAM,CHOLAM_H,QUBUTS}

BET='\u05D1'; KAF='\u05DB'; KAF_F='\u05DA'; PE='\u05E4'; PE_F='\u05E3'
VAV='\u05D5'; ALEF='\u05D0'; HE='\u05D4'; SHIN='\u05E9'
BKP = {BET, KAF, KAF_F, PE, PE_F}
FINAL_MAP={'\u05DA':'\u05DB','\u05DD':'\u05DE','\u05DF':'\u05E0','\u05E3':'\u05E4','\u05E5':'\u05E6'}

def get_vowel(dia):
    for d in dia:
        if d in ALL_VOWELS: return d
    return None

def set_vowel(dia, old_v, new_v):
    return [new_v if d == old_v else d for d in dia]

def parse(s):
    units=[]; cc=None; cd=[]
    for ch in s:
        cp=ord(ch)
        if cp==0xFB2A:
            if cc is not None: units.append((cc,cd))
            cc=SHIN; cd=[SHIN_DOT]
        elif cp==0xFB2B:
            if cc is not None: units.append((cc,cd))
            cc=SHIN; cd=[SIN_DOT]
        elif cp==0xFB2C:
            if cc is not None: units.append((cc,cd))
            cc=SHIN; cd=[DAGESH,SHIN_DOT]
        elif cp==0xFB2D:
            if cc is not None: units.append((cc,cd))
            cc=SHIN; cd=[DAGESH,SIN_DOT]
        elif 0x05D0<=cp<=0x05EA:
            if cc is not None: units.append((cc,cd))
            cc=ch; cd=[]
        elif ch in ALL_VOWELS or ch in (DAGESH,SHIN_DOT,SIN_DOT,'\u05BD','\u05BF'):
            cd.append(ch)
    if cc is not None: units.append((cc,cd))
    return units

def rebuild(units):
    parts=[]
    for cons, dia in units:
        parts.append(cons)
        for d in sorted(dia, key=lambda x: (
            0 if x in (SHIN_DOT, SIN_DOT) else
            1 if x == DAGESH else 2)):
            parts.append(d)
    return ''.join(parts)

def norm_cons(text):
    out=[]
    for ch in text:
        cp=ord(ch)
        if 0x05D0<=cp<=0x05EA: out.append(FINAL_MAP.get(ch,ch))
        elif cp in (0xFB2A,0xFB2B,0xFB2C,0xFB2D): out.append(SHIN)
    return ''.join(out)

# ── Clasificación (idéntica a auditar_cholam.py) ───
SPECIFIC_A = {'כל'}
SPECIFIC_B = {'ערב', 'בקר'}
ELOHIM_ROOTS = {'אלהימ','אלהיכ','אלהיכמ','אלהי','אלהינו',
                'אלהיהמ','אלהיו','אלהיהנ','אלה','אלהימו'}
APPLY = {'A_KOL','A_SEGOLADO_NOM','A_SEGOLADO_SUFIJO','B_ESPECIFICA',
         'B_PARTICIPIO','B_PARTICIPIO_SUFIJO','B_QOTEL_NOM'}

def classify_word(mt_units, pos, cons_norm):
    if cons_norm in SPECIFIC_A: return 'A_KOL'
    if cons_norm in SPECIFIC_B: return 'B_ESPECIFICA'
    if pos == 'nmpr': return 'D_NOMBRE_PROPIO'
    if cons_norm in ELOHIM_ROOTS: return 'E_ELOHIM'

    for i, (c, d) in enumerate(mt_units):
        v = get_vowel(d)
        if v not in (CHOLAM, CHOLAM_H): continue
        v_next = get_vowel(mt_units[i+1][1]) if i+1 < len(mt_units) else None
        v_after = get_vowel(mt_units[i+2][1]) if i+2 < len(mt_units) else None

        if v_next in (SEGOL, PATACH) and v_after in (None, SHEVA):
            if pos in ('subs','adjv',''): return 'A_SEGOLADO_NOM'
            if pos == 'verb': return 'B_PARTICIPIO'
        if v_next == TSERE and v_after in (None, SHEVA):
            if pos == 'verb': return 'B_PARTICIPIO'
            if pos in ('subs','adjv',''): return 'B_QOTEL_NOM'
        if v_next in (SEGOL, PATACH, TSERE) and v_after is not None and pos in ('subs','adjv'):
            return 'A_SEGOLADO_SUFIJO'
        if v_next in (TSERE,) and v_after is not None and pos == 'verb':
            return 'B_PARTICIPIO_SUFIJO'
    return 'F_OTRO'

# ── Corrección ─────────────────────────────────────
def fix_word(mt_str, sam_str, pos, sp_cons):
    """Aplica correcciones fonéticas a una palabra. Devuelve (new_sam, stats_dict)."""
    stats = Counter()
    mt_u = parse(mt_str)
    sam_u = [[c, list(d)] for c, d in parse(sam_str)]
    cons = norm_cons(sp_cons or mt_str)

    # ─── 1. Cholam fix ───────────────────────────
    has_cholam_conversion = False
    for i in range(min(len(mt_u), len(sam_u))):
        mt_v = get_vowel(mt_u[i][1])
        sam_v = get_vowel(sam_u[i][1])
        if mt_v in (CHOLAM, CHOLAM_H) and sam_v == QUBUTS:
            has_cholam_conversion = True
            break
    if not has_cholam_conversion:
        for i in range(len(mt_u)-1):
            mt_v = get_vowel(mt_u[i][1])
            if mt_v in (CHOLAM, CHOLAM_H):
                if i+1 < len(sam_u) and sam_u[i+1][0] == VAV and DAGESH in sam_u[i+1][1]:
                    has_cholam_conversion = True
                    break

    if has_cholam_conversion:
        cat = classify_word(mt_u, pos, cons)
        if cat in APPLY:
            for i in range(min(len(mt_u), len(sam_u))):
                mt_v = get_vowel(mt_u[i][1])
                sam_v = get_vowel(sam_u[i][1])
                # Case 1: qubuts → qamats
                if mt_v in (CHOLAM, CHOLAM_H) and sam_v == QUBUTS:
                    sam_u[i][1] = set_vowel(sam_u[i][1], QUBUTS, QAMATS)
                    stats['cholam_fix'] += 1
                # Case 2: shuruq → qamats + mater vav
                elif mt_v in (CHOLAM, CHOLAM_H) and sam_v is None:
                    if i+1 < len(sam_u) and sam_u[i+1][0] == VAV and DAGESH in sam_u[i+1][1]:
                        sam_u[i+1][1] = [d for d in sam_u[i+1][1] if d != DAGESH]
                        sam_u[i][1].append(QAMATS)
                        stats['shuruq_fix'] += 1

    # ─── 2. Dagesh BKP ──────────────────────────
    for i in range(len(sam_u)):
        c = sam_u[i][0]
        if c in BKP and DAGESH not in sam_u[i][1]:
            sam_u[i][1].append(DAGESH)
            stats['dagesh_bkp'] += 1

    new_sam = rebuild([(c, tuple(d)) for c, d in sam_u])
    return new_sam, stats

# ── Procesar los 5 libros ─────────────────────────
BASE = r'C:\Users\pik_y\Documents\TRADUCCION\texto samaritano'
ORDER = ['genesis','exodus','leviticus','numbers','deuteronomy']
STAMP = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

grand = Counter()
per_book = {}

for b in ORDER:
    path = os.path.join(BASE, f'{b}_lectura_samaritana.json')
    with open(path, encoding='utf-8') as f:
        data = json.load(f)

    shutil.copy(path, os.path.join(BASE, f'{b}_lectura_samaritana.prefonetica_{STAMP}.json'))

    book_stats = Counter()
    for ch, chap in data['chapters'].items():
        for vs, verse in chap.items():
            verse_changed = False
            for w in verse['words']:
                mt = w.get('mt','')
                sam = w.get('sam_reading','')
                if not sam: continue

                if mt and w.get('match') in ('exact','fuzzy'):
                    new_sam, ws = fix_word(mt, sam, w.get('pos',''), w.get('sp_cons',''))
                else:
                    # Words without MT (sp_only, curado): only apply dagesh BKP
                    sam_u = [[c, list(d)] for c, d in parse(sam)]
                    ws = Counter()
                    for i in range(len(sam_u)):
                        if sam_u[i][0] in BKP and DAGESH not in sam_u[i][1]:
                            sam_u[i][1].append(DAGESH)
                            ws['dagesh_bkp'] += 1
                    new_sam = rebuild([(c, tuple(d)) for c, d in sam_u])

                if new_sam != sam:
                    w['sam_reading'] = new_sam
                    verse_changed = True
                book_stats += ws

            if verse_changed:
                verse['sam_reading'] = ' '.join(w['sam_reading'] for w in verse['words'])

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    per_book[b] = dict(book_stats)
    grand += book_stats

# ── Reporte ────────────────────────────────────────
print(f"{'='*65}")
print(f"CORRECCIÓN FONÉTICA APLICADA")
print(f"{'='*65}")
print(f"\n  Respaldo: *_lectura_samaritana.prefonetica_{STAMP}.json\n")
print(f"  {'Libro':14} {'cholam→qamats':>14} {'shuruq→qamats':>14} {'dagesh BKP':>12}")
print(f"  {'─'*14} {'─'*14} {'─'*14} {'─'*12}")
for b in ORDER:
    s = per_book[b]
    print(f"  {b:14} {s.get('cholam_fix',0):>14} {s.get('shuruq_fix',0):>14} {s.get('dagesh_bkp',0):>12}")
print(f"  {'─'*14} {'─'*14} {'─'*14} {'─'*12}")
print(f"  {'TOTAL':14} {grand.get('cholam_fix',0):>14} {grand.get('shuruq_fix',0):>14} {grand.get('dagesh_bkp',0):>12}")
print(f"\n  Total cambios: {sum(grand.values())}")
