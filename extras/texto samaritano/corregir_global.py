"""
Corrección global: 4 patrones residuales
=========================================
1. כֻּל residuales → כָּל (5 tokens)
2. Participios plene con shuruq residual → qamats (77 tokens)
3. Plural femenino -ūt → -āt (1160 tokens)
4. Participio יֵּשַׁב y similares sin vav mater (cholam defectivo con tsere)

Estos patrones escaparon de corregir_fonetica.py porque:
- #1: tenían dagesh (כֻּל) que impedía el match exacto
- #2: eran formas plene (cholam+vav → shuruq) no capturadas por el fix anterior
- #3: patrón nuevo no cubierto (plural femenino -ōt → -āt)
"""
import json, sys, os, shutil, datetime
from collections import Counter
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

SHEVA='\u05B0'; CHIRIK='\u05B4'; TSERE='\u05B5'; SEGOL='\u05B6'
PATACH='\u05B7'; QAMATS='\u05B8'; CHOLAM='\u05B9'; CHOLAM_H='\u05BA'
QUBUTS='\u05BB'; DAGESH='\u05BC'; SHIN_DOT='\u05C1'; SIN_DOT='\u05C2'
ALL_VOWELS={SHEVA,'\u05B1','\u05B2','\u05B3',CHIRIK,TSERE,SEGOL,PATACH,QAMATS,CHOLAM,CHOLAM_H,QUBUTS}
VAV='\u05D5'; TAV='\u05EA'; SHIN='\u05E9'
FINAL_MAP={'\u05DA':'\u05DB','\u05DD':'\u05DE','\u05DF':'\u05E0','\u05E3':'\u05E4','\u05E5':'\u05E6'}

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

def get_vowel(dia):
    for d in dia:
        if d in ALL_VOWELS: return d
    return None

def norm_cons(text):
    out=[]
    for ch in text:
        cp=ord(ch)
        if 0x05D0<=cp<=0x05EA: out.append(FINAL_MAP.get(ch,ch))
        elif cp in (0xFB2A,0xFB2B,0xFB2C,0xFB2D): out.append(SHIN)
    return ''.join(out)

ELOHIM_ROOTS = {'אלהימ','אלהיכ','אלהיכמ','אלהי','אלהינו',
                'אלהיהמ','אלהיו','אלהיהנ','אלה','אלהימו'}

BASE = r'C:\Users\pik_y\Documents\TRADUCCION\texto samaritano'
ORDER = ['genesis','exodus','leviticus','numbers','deuteronomy']
STAMP = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

grand = Counter()

for b in ORDER:
    path = os.path.join(BASE, f'{b}_lectura_samaritana.json')
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    shutil.copy(path, os.path.join(BASE, f'{b}_lectura_samaritana.preglobal_{STAMP}.json'))

    book_stats = Counter()
    for ch, chap in data['chapters'].items():
        for vs, verse in chap.items():
            changed = False
            for w in verse['words']:
                sr = w['sam_reading']
                cons = norm_cons(w.get('sp_cons', '') or w.get('mt', ''))
                pos = w.get('pos', '')
                mt = w.get('mt', '')
                old_sr = sr
                units = [[c, list(d)] for c, d in parse(sr)]

                # ── FIX 1: כֻּל residual → כָּל ─────────────
                if cons == 'כל' and len(units) == 2:
                    v0 = get_vowel(units[0][1])
                    if v0 == QUBUTS:
                        units[0][1] = [DAGESH if d == DAGESH else QAMATS if d == QUBUTS else d for d in units[0][1]]
                        book_stats['kol_fix'] += 1

                # ── FIX 2: Participios plene (shuruq→qamats) ─────
                # Pattern: consonant + vav-shuruq + tsere/segol/chirik
                # These are participles where cholam+vav became shuruq
                # but should be qamats (and vav stays as mater without dagesh)
                if pos == 'verb' and mt and (CHOLAM in mt or CHOLAM_H in mt):
                    mt_u = parse(mt)
                    for i in range(len(mt_u) - 1):
                        mt_v = get_vowel(mt_u[i][1])
                        if mt_v not in (CHOLAM, CHOLAM_H):
                            continue
                        # MT: C+cholam, vav (mater) → SAM should have: C+qamats, vav (mater)
                        # Currently SAM has: C (no vowel), vav+dagesh (shuruq)
                        if i + 1 < len(units) and units[i + 1][0] == VAV and DAGESH in units[i + 1][1]:
                            # Check that this is a participle pattern (tsere on next consonant after vav)
                            if i + 2 < len(mt_u):
                                mt_v2 = get_vowel(mt_u[i + 2][1])
                                if mt_v2 in (TSERE, SEGOL, CHIRIK):
                                    # Don't fix names/Elohim
                                    if pos == 'nmpr' or cons in ELOHIM_ROOTS:
                                        continue
                                    # Remove dagesh from vav (de-shuruq)
                                    units[i + 1][1] = [d for d in units[i + 1][1] if d != DAGESH]
                                    # Add qamats to consonant before vav
                                    if get_vowel(units[i][1]) is None:
                                        units[i][1].append(QAMATS)
                                    book_stats['part_plene_fix'] += 1

                # ── FIX 2b: Participio defectivo con tsere (יֵּשַׁב etc.) ──
                # These are participles without vav mater where cholam
                # somehow became tsere instead of qamats
                if pos == 'verb' and mt and (CHOLAM in mt or CHOLAM_H in mt):
                    mt_u2 = parse(mt)
                    for i in range(min(len(mt_u2), len(units))):
                        mt_v = get_vowel(mt_u2[i][1])
                        sam_v = get_vowel(units[i][1])
                        if mt_v in (CHOLAM, CHOLAM_H) and sam_v == TSERE:
                            if pos != 'nmpr' and cons not in ELOHIM_ROOTS:
                                units[i][1] = [QAMATS if d == TSERE else d for d in units[i][1]]
                                book_stats['part_def_fix'] += 1

                # ── FIX 3: Plural femenino -ūt → -āt ─────────
                # The ending -וֹת/-וּת should be -ָת in Samaritan
                # Pattern: ...vav+dagesh(shuruq) + tav OR ...qubuts + tav
                n = len(units)
                if n >= 2 and units[-1][0] == TAV and pos in ('subs','adjv'):
                    if cons not in ELOHIM_ROOTS and pos != 'nmpr':
                        # Case A: shuruq before tav: ...vav+dagesh, tav
                        if units[-2][0] == VAV and DAGESH in units[-2][1]:
                            # Remove the shuruq-vav entirely and put qamats on the consonant before
                            if n >= 3:
                                prev_v = get_vowel(units[-3][1])
                                # Remove the vav+dagesh unit
                                units.pop(-2)
                                # Add qamats to what's now units[-2] (the consonant before old vav)
                                if get_vowel(units[-2][1]) is None:
                                    units[-2][1].append(QAMATS)
                                elif get_vowel(units[-2][1]) == QUBUTS:
                                    units[-2][1] = [QAMATS if d == QUBUTS else d for d in units[-2][1]]
                                book_stats['fem_plural_shuruq'] += 1
                            else:
                                # Only 2 units (vav+tav), just change vav dagesh to qamats
                                units[-2][1] = [d for d in units[-2][1] if d != DAGESH]
                                units[-2][1].append(QAMATS)
                                book_stats['fem_plural_shuruq'] += 1
                        # Case B: qubuts on consonant before tav (no vav)
                        elif units[-2][0] != VAV and get_vowel(units[-2][1]) == QUBUTS:
                            units[-2][1] = [QAMATS if d == QUBUTS else d for d in units[-2][1]]
                            book_stats['fem_plural_qubuts'] += 1

                new_sr = rebuild([(c, tuple(d)) for c, d in units])
                if new_sr != old_sr:
                    w['sam_reading'] = new_sr
                    changed = True

            if changed:
                verse['sam_reading'] = ' '.join(w['sam_reading'] for w in verse['words'])

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    grand += book_stats
    print(f'{b:14} kol={book_stats.get("kol_fix",0):3} '
          f'part_plene={book_stats.get("part_plene_fix",0):3} '
          f'part_def={book_stats.get("part_def_fix",0):3} '
          f'fem_shuruq={book_stats.get("fem_plural_shuruq",0):4} '
          f'fem_qubuts={book_stats.get("fem_plural_qubuts",0):4}')

print(f'\n{"="*65}')
print(f'CORRECCIÓN GLOBAL APLICADA')
print(f'{"="*65}')
print(f'  Respaldo: *_preglobal_{STAMP}.json')
print(f'  כֻּל→כָּל:            {grand.get("kol_fix",0)}')
print(f'  Participio plene:     {grand.get("part_plene_fix",0)}')
print(f'  Participio defectivo: {grand.get("part_def_fix",0)}')
print(f'  Fem. plural shuruq:  {grand.get("fem_plural_shuruq",0)}')
print(f'  Fem. plural qubuts:  {grand.get("fem_plural_qubuts",0)}')
print(f'  TOTAL cambios:       {sum(grand.values())}')
