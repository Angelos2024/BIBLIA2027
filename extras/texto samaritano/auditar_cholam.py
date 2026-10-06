"""
Auditoría: cholam convertido a qubuts por R5
=============================================
Encuentra TODAS las palabras donde R5 convirtió cholam→qubuts/shuruq
y las clasifica por patrón fonológico para determinar cuáles deben ser
qamats (/a/) en vez de qubuts (/u/).

Ben-Hayyim distingue:
  - Cholam histórico largo (qal perfecto, infinitivo, etc.) → /u/ correcto
  - Cholam en segolados nominales CoCeC (בֹּקֶר) → /a/ (qamats)
  - Cholam en participios qal CoCeC (שֹׁמֵר) → /a/ (qamats)
  - Cholam en כל, ערב → /a/
  - Nombres propios, Elohim → /u/ siempre
"""
import sys, json, os, re
from collections import defaultdict, Counter
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Unicode constants
SHEVA='\u05B0'; HATAF_S='\u05B1'; HATAF_P='\u05B2'; HATAF_Q='\u05B3'
CHIRIK='\u05B4'; TSERE='\u05B5'; SEGOL='\u05B6'; PATACH='\u05B7'
QAMATS='\u05B8'; CHOLAM='\u05B9'; CHOLAM_H='\u05BA'; QUBUTS='\u05BB'
DAGESH='\u05BC'; SHIN_DOT='\u05C1'; SIN_DOT='\u05C2'
ALL_VOWELS={SHEVA,HATAF_S,HATAF_P,HATAF_Q,CHIRIK,TSERE,SEGOL,PATACH,QAMATS,CHOLAM,CHOLAM_H,QUBUTS}
ALEF='\u05D0'; HE='\u05D4'; VAV='\u05D5'; YOD='\u05D9'
FINAL_MAP={'\u05DA':'\u05DB','\u05DD':'\u05DE','\u05DF':'\u05E0','\u05E3':'\u05E4','\u05E5':'\u05E6'}
SHIN='\u05E9'

def get_vowel(dia):
    for d in dia:
        if d in ALL_VOWELS: return d
    return None

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

def norm_cons(text):
    out=[]
    for ch in text:
        cp=ord(ch)
        if 0x05D0<=cp<=0x05EA: out.append(FINAL_MAP.get(ch,ch))
        elif cp in (0xFB2A,0xFB2B,0xFB2C,0xFB2D): out.append(SHIN)
    return ''.join(out)

# ── Clasificación ──────────────────────────────────
SPECIFIC_A = {'כל'}           # כֹּל → כָּל
SPECIFIC_B = {'ערב', 'בקר'}   # segolados / específicas
ELOHIM_ROOTS = {'אלהים', 'אלהי', 'אלה'}
NMPR_POS = {'nmpr'}

def classify_word(mt_units, pos, cons_norm, gloss):
    """Clasifica una palabra que tuvo cholam→qubuts."""
    if cons_norm in SPECIFIC_A:
        return 'A_KOL'
    if cons_norm in SPECIFIC_B:
        return 'B_ESPECIFICA'
    if pos in NMPR_POS or pos == 'nmpr':
        return 'D_NOMBRE_PROPIO'
    if any(cons_norm.startswith(e) or cons_norm == e for e in ELOHIM_ROOTS):
        return 'E_ELOHIM'

    # Find the cholam position in the MT and analyze surrounding pattern
    for i, (c, d) in enumerate(mt_units):
        v = get_vowel(d)
        if v not in (CHOLAM, CHOLAM_H):
            continue
        # Look at next consonant's vowel
        if i+1 < len(mt_units):
            v_next = get_vowel(mt_units[i+1][1])
        else:
            v_next = None
        if i+2 < len(mt_units):
            v_after = get_vowel(mt_units[i+2][1])
        else:
            v_after = None

        # Segolate nominal: CoCeC (cholam + segol on next, nothing/sheva on last)
        if v_next in (SEGOL, PATACH) and v_after in (None, SHEVA) and pos in ('subs','adjv',''):
            return 'A_SEGOLADO_NOM'
        # Participle qal active: CoCeC with tsere
        if v_next == TSERE and v_after in (None, SHEVA):
            if pos == 'verb':
                return 'B_PARTICIPIO'
            elif pos in ('subs','adjv',''):
                return 'B_QOTEL_NOM'
        # Segolate with suffix: CoCeC + suffix (v_after has a vowel)
        if v_next in (SEGOL, PATACH, TSERE) and v_after is not None and pos in ('subs','adjv'):
            return 'A_SEGOLADO_SUFIJO'
        if v_next in (TSERE,) and v_after is not None and pos == 'verb':
            return 'B_PARTICIPIO_SUFIJO'

    return 'F_OTRO'

# ── Escanear los 5 libros ──────────────────────────
BASE = r'C:\Users\pik_y\Documents\TRADUCCION\texto samaritano'
ORDER = ['genesis','exodus','leviticus','numbers','deuteronomy']

results = defaultdict(lambda: {'count':0, 'forms': Counter(), 'examples': []})
all_forms = []

for b in ORDER:
    with open(os.path.join(BASE, f'{b}_lectura_samaritana.json'), encoding='utf-8') as f:
        data = json.load(f)
    for ch, chap in data['chapters'].items():
        for vs, verse in chap.items():
            for w in verse['words']:
                mt = w.get('mt','')
                sam = w.get('sam_reading','')
                if not mt or not sam: continue
                if w.get('match') not in ('exact','fuzzy'): continue

                mt_u = parse(mt)
                sam_u = parse(sam)
                cons = norm_cons(w.get('sp_cons','') or mt)
                pos = w.get('pos','')
                gloss = w.get('gloss','')

                # Check each consonant position for cholam(MT)→qubuts(SAM) conversion
                has_conversion = False
                for idx in range(min(len(mt_u), len(sam_u))):
                    mt_v = get_vowel(mt_u[idx][1])
                    sam_v = get_vowel(sam_u[idx][1])
                    if mt_v in (CHOLAM, CHOLAM_H) and sam_v == QUBUTS:
                        has_conversion = True
                        break
                # Also check shuruq case: MT cholam+vav → SAM vav+dagesh
                if not has_conversion:
                    for idx in range(len(mt_u)-1):
                        mt_v = get_vowel(mt_u[idx][1])
                        if mt_v in (CHOLAM, CHOLAM_H):
                            if idx+1 < len(sam_u) and sam_u[idx+1][0] == VAV and DAGESH in sam_u[idx+1][1]:
                                has_conversion = True
                                break

                if not has_conversion:
                    continue

                cat = classify_word(mt_u, pos, cons, gloss)
                results[cat]['count'] += 1
                results[cat]['forms'][cons] += 1
                if len(results[cat]['examples']) < 5:
                    results[cat]['examples'].append({
                        'ref': f"{b[:3]} {ch}:{vs}",
                        'mt': mt, 'sam': sam, 'cons': cons,
                        'pos': pos, 'gloss': gloss
                    })

# ── Reporte ────────────────────────────────────────
GROUP_NAMES = {
    'A_KOL': 'כל (kol→kal)',
    'A_SEGOLADO_NOM': 'Segolado nominal CoCeC',
    'A_SEGOLADO_SUFIJO': 'Segolado nominal con sufijo',
    'B_ESPECIFICA': 'Específicas (ערב, בקר)',
    'B_PARTICIPIO': 'Participio qal activo CoCeC',
    'B_PARTICIPIO_SUFIJO': 'Participio con sufijo',
    'B_QOTEL_NOM': 'Sustantivo patrón qotel (CoCeC+tsere)',
    'D_NOMBRE_PROPIO': 'Nombre propio (mantener /u/)',
    'E_ELOHIM': 'Elohim (mantener /u/)',
    'F_OTRO': 'Otro (cholam histórico largo → /u/ correcto)',
}

APPLY = {'A_KOL','A_SEGOLADO_NOM','A_SEGOLADO_SUFIJO','B_ESPECIFICA',
         'B_PARTICIPIO','B_PARTICIPIO_SUFIJO','B_QOTEL_NOM'}
KEEP_U = {'D_NOMBRE_PROPIO','E_ELOHIM','F_OTRO'}

print("="*70)
print("AUDITORÍA: CONVERSIÓN CHOLAM → QUBUTS (R5)")
print("="*70)

total_apply = 0
total_keep = 0

for cat in sorted(results.keys()):
    r = results[cat]
    action = "→ CAMBIAR a qamats /a/" if cat in APPLY else "→ mantener qubuts /u/"
    print(f"\n{'─'*60}")
    print(f"  {GROUP_NAMES.get(cat,cat)}  ({r['count']} tokens)  {action}")
    print(f"  Formas únicas: {len(r['forms'])}")
    top = r['forms'].most_common(15)
    for form, n in top:
        print(f"    {form:16} ×{n}")
    if len(r['forms']) > 15:
        print(f"    ... y {len(r['forms'])-15} formas más")
    print(f"  Ejemplos:")
    for ex in r['examples']:
        print(f"    {ex['ref']:12} MT={ex['mt']:20} → SAM={ex['sam']:20} [{ex['pos']:5}] {ex['gloss']}")
    if cat in APPLY:
        total_apply += r['count']
    else:
        total_keep += r['count']

print(f"\n{'='*70}")
print(f"RESUMEN")
print(f"{'='*70}")
print(f"  Total cholam→qubuts detectados: {total_apply + total_keep}")
print(f"  CAMBIAR a qamats /a/:           {total_apply}  (segolados + participios + כל + ערב/בקר)")
print(f"  Mantener qubuts /u/:            {total_keep}  (nombres propios + Elohim + otros)")
print(f"\n  ¿Aprobar? Ejecutar corregir_fonetica.py para aplicar.")
