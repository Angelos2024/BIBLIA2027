"""
Reglas de mutacion a /e/ (capa de aproximacion)  -- NO DESTRUCTIVO
==================================================================
Implementa, sobre los JSON existentes, dos reglas del experto para decidir
cuando una /a/ samaritana debe leerse /e/:

  R2  Perfecto consecutivo (we-qatal): la 1a vocal radical /a/ -> /e/.
      RUTA DEL PUENTE DE DATOS (recomendada por el experto): el texto
      consonantico NO distingue we-qatal consecutivo de we+perfecto
      copulativo. La unica senal fiable es la MORFOLOGIA + el ACENTO
      masoretico. Por eso R2 ahora exige:
        1) pos == verb  Y  vt == 'perf'            (no wayyiqtol/imperfecto)
        2) una waw conjuntiva (adjunta o token previo)
        3) persona/numero con CONTRASTE de acento:
             1cs (p1 sg), 2ms/2fs (p2 sg), 1cp (p1 pl)
           -> en esas formas el perfecto simple es GRAVE (penultima) y el
              consecutivo es AGUDO (ultima). Se lee el acento del campo 'mt'.
        4) acento masoretico en la ULTIMA silaba (te'amim) -> consecutivo.
      Si el acento cae en la penultima -> copulativo -> se mantiene /a/.

      Personas SIN contraste de acento (2mp/2fp, 3a persona, dual): ni el
      acento ni las consonantes las distinguen (igual que dice el experto).
      Quedan en DEFAULT_AMBIG (por defecto 'a' = no se tocan). Editable.

      NOTA: requiere correr antes el motor actualizado (motor_samaritano.py)
      para que los JSON traigan vt/ps/nu. Si faltan, R2 usa un FALLBACK por
      puntuado de la waw (aproximado) y avisa.

  R3  Segolados con diptongo historico *ay -> /e/  (lexico curado).
      Ej.: bayit (בית) -> bet ;  mayim ya lo cubre el motor (R1).

SEGURIDAD:
  - NO modifica el motor ni los JSON originales.
  - Escribe ARCHIVOS NUEVOS: *_lectura_samaritana_e.json
  - Hace respaldos con fecha de los originales.
  - Imprime un REPORTE de cambios (con ejemplos de Genesis) para revision.

LIMITES (revisable):
  - 2mp/2fp/3a persona: no disambiguables por acento -> DEFAULT_AMBIG.
  - La Regla 4 (gutural en silaba trabada postonica) NO se incluye: requiere
    silabificacion completa, no presente en el corpus.
"""
import json, os, sys, shutil, datetime
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.abspath(__file__))
ORDER = ['genesis', 'exodus', 'leviticus', 'numbers', 'deuteronomy']

# ── Unicode ──
SHEVA='\u05B0'; HATAF_S='\u05B1'; HATAF_P='\u05B2'; HATAF_Q='\u05B3'
CHIRIK='\u05B4'; TSERE='\u05B5'; SEGOL='\u05B6'; PATACH='\u05B7'
QAMATS='\u05B8'; CHOLAM='\u05B9'; CHOLAM_H='\u05BA'; QUBUTS='\u05BB'
DAGESH='\u05BC'; SHIN_DOT='\u05C1'; SIN_DOT='\u05C2'
ALL_VOWELS={SHEVA,HATAF_S,HATAF_P,HATAF_Q,CHIRIK,TSERE,SEGOL,PATACH,
            QAMATS,CHOLAM,CHOLAM_H,QUBUTS}
# Vocales plenas (las que portan el acento tonico; sheva y hatafs no cuentan)
FULL_VOWELS={CHIRIK,TSERE,SEGOL,PATACH,QAMATS,CHOLAM,CHOLAM_H,QUBUTS}
VAV='\u05D5'; YOD='\u05D9'; SHIN='\u05E9'
FINAL_MAP={'\u05DA':'\u05DB','\u05DD':'\u05DE','\u05DF':'\u05E0','\u05E3':'\u05E4','\u05E5':'\u05E6'}

# ── Te'amim (acentos de cantilacion) U+0591..U+05AE ──
TEAMIM={chr(c) for c in range(0x0591, 0x05AF)}
# Acentos POSPOSITIVOS: se dibujan sobre la ULTIMA letra sin importar la tonica
# (no sirven para ubicar el acento). zarqa, pashta, telisha qetana, sinnor, segolta.
POSTPOS={'\u0598','\u0599','\u05A9','\u05AE','\u0592'}
# Acentos PREPOSITIVOS: sobre la PRIMERA letra. telisha gedola, dehi, yetiv.
PREPOS={'\u05A0','\u05AD','\u059A'}

# Conjunto de personas/numeros del perfecto cuyo acento DISTINGUE simple
# (grave/penultima) de consecutivo (agudo/ultima): 1cs, 2ms/2fs, 1cp.
def has_stress_contrast(ps, nu):
    return (ps == 'p1' and nu in ('sg', 'pl')) or (ps == 'p2' and nu == 'sg')

# Que hacer con perfectos+waw cuya persona NO tiene contraste de acento
# (2mp/2fp, 3a persona, dual): 'a' = conservador (no cambiar) ; 'e' = aplicar.
DEFAULT_AMBIG = 'a'


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
        for x in sorted(dia, key=lambda y:(0 if y in (SHIN_DOT,SIN_DOT) else 1 if y==DAGESH else 2)):
            parts.append(x)
    return ''.join(parts)


def get_vowel(dia):
    for d in dia:
        if d in ALL_VOWELS:
            return d
    return None


def set_vowel_unit(dia, old_v, new_v):
    return [new_v if d == old_v else d for d in dia]


def norm_cons(text):
    out=[]
    for ch in text or '':
        cp=ord(ch)
        if 0x05D0<=cp<=0x05EA: out.append(FINAL_MAP.get(ch,ch))
        elif cp in (0xFB2A,0xFB2B,0xFB2C,0xFB2D): out.append(SHIN)
    return ''.join(out)


def parse_teamim(s):
    """Como parse(), pero CONSERVA los te'amim (acentos) en cada unidad.
    Devuelve [(consonante, [diacriticos...])] incluyendo acentos U+0591..U+05AE."""
    units=[]; cc=None; cd=[]
    for ch in s or '':
        cp=ord(ch)
        if cp in (0xFB2A,0xFB2B,0xFB2C,0xFB2D):
            if cc is not None: units.append((cc,cd))
            cc=SHIN; cd=[]
        elif 0x05D0<=cp<=0x05EA:
            if cc is not None: units.append((cc,cd))
            cc=ch; cd=[]
        elif 0x0591<=cp<=0x05BF or ch in (SHIN_DOT,SIN_DOT):
            cd.append(ch)
    if cc is not None: units.append((cc,cd))
    return units


def stress_position(mt):
    """Ubica el acento tonico principal segun los te'amim del campo 'mt'.
    Devuelve 'ultima' (agudo), 'penult' (grave) o None (no determinable).

    - 'ultima'  -> acento sobre la ultima silaba con vocal plena.
    - 'penult'  -> acento sobre una silaba anterior.
    - None      -> sin acento fiable (solo acentos pre/posposicionales, o
                   ninguno): no se puede decidir; el llamador sera conservador.
    """
    units = parse_teamim(mt)
    if not units:
        return None
    fv = [i for i, (c, d) in enumerate(units)
          if any(v in d for v in FULL_VOWELS)]
    if not fv:
        return None
    last_fv = fv[-1]
    acc_idx = None
    for i, (c, d) in enumerate(units):
        teams = [x for x in d if x in TEAMIM]
        if not teams:
            continue
        # ignoramos acentos pre/posposicionales: no marcan la tonica
        if any(x not in POSTPOS and x not in PREPOS for x in teams):
            acc_idx = i
            break
    if acc_idx is None or acc_idx not in fv:
        return None
    return 'ultima' if acc_idx == last_fv else 'penult'


# ── R3: lexico curado de segolados con *ay (revisable/expandible) ──
_AY_RAW = ['בית', 'זית', 'ליל', 'לילה', 'עין', 'מעין', 'איל', 'חיל']
AY_SEGOLATES = {norm_cons(x) for x in _AY_RAW}


def apply_R3(word, report):
    """Segolado *ay: primera patach/qamats ANTES de yod -> tsere."""
    skel = norm_cons(word.get('sp_cons') or word.get('mt', ''))
    if skel not in AY_SEGOLATES:
        return False
    u = [[c, list(d)] for c, d in parse(word['sam_reading'])]
    for i in range(len(u) - 1):
        if u[i+1][0] == YOD and get_vowel(u[i][1]) in (PATACH, QAMATS):
            old = get_vowel(u[i][1])
            u[i][1] = set_vowel_unit(u[i][1], old, TSERE)
            new = rebuild([(c, tuple(d)) for c, d in u])
            report.append(('R3', word['sam_reading'], new, word.get('mt', '')))
            word['sam_reading'] = new
            return True
    return False


def waw_class(mt_waw, attached):
    """Clasifica una waw por su puntuado MT: 'consec' (wayyiqtol) / 'weqatal' / None."""
    u = parse(mt_waw)
    if not u or u[0][0] != VAV:
        return None
    v = get_vowel(u[0][1])
    if attached:
        # wayyiqtol: waw+patach y daguesh en la consonante siguiente
        if v == PATACH and len(u) > 1 and DAGESH in u[1][1]:
            return 'consec'
        if v == SHEVA:
            return 'weqatal'
        return None
    # waw separada
    if v == PATACH:
        return 'consec'
    if v == SHEVA:
        return 'weqatal'
    return None


# Diagnostico de R2 (se imprime al final) y aviso unico de fallback.
R2_STATS = Counter()
_warned = {'vt_missing': False}


def _waw_present(words, idx):
    """(present, attached): el verbo lleva waw conjuntiva (adjunta o token previo)."""
    w = words[idx]
    umt = parse(w.get('mt', ''))
    if umt and umt[0][0] == VAV:
        return True, True
    if idx > 0:
        pw = words[idx - 1]
        if norm_cons(pw.get('sp_cons') or pw.get('mt', '')) == 'ו':
            return True, False
    return False, False


def _apply_e(w, mt, report):
    """Cambia la 1a vocal radical /a/ (patach/qamats) -> /e/ (tsere)."""
    u = [[c, list(d)] for c, d in parse(w['sam_reading'])]
    start = 1 if (u and u[0][0] == VAV) else 0   # saltar waw adjunta
    for i in range(start, len(u)):
        v = get_vowel(u[i][1])
        if v in (PATACH, QAMATS):
            u[i][1] = set_vowel_unit(u[i][1], v, TSERE)
            new = rebuild([(c, tuple(d)) for c, d in u])
            report.append(('R2', w['sam_reading'], new, mt))
            w['sam_reading'] = new
            return True
        if v is not None:
            return False   # la 1a vocal radical no es /a/ -> no forzar
    return False


def apply_R2(words, idx, report):
    """We-qatal -> 1a vocal radical /a/->/e/, via MORFOLOGIA (vt/ps/nu) + ACENTO.
    Si faltan vt/ps/nu (motor viejo) usa un FALLBACK por puntuado de la waw."""
    w = words[idx]
    if w.get('pos') != 'verb':
        return False
    mt = w.get('mt', '')
    present, attached = _waw_present(words, idx)
    if not present:
        return False   # sin waw no hay we-qatal

    vt = w.get('vt', '')
    ps = w.get('ps', '')
    nu = w.get('nu', '')

    # ── FALLBACK: JSON sin morfologia (corre motor_samaritano.py para la ruta completa) ──
    if not vt:
        if not _warned['vt_missing']:
            print('  [AVISO] Los JSON no traen vt/ps/nu: R2 usa FALLBACK por '
                  'puntuado de la waw (aproximado, puede sobre-aplicar).')
            print('          Re-corre motor_samaritano.py --book all para la ruta completa.\n')
            _warned['vt_missing'] = True
        waw_mt = mt if attached else words[idx - 1].get('mt', '')
        if waw_class(waw_mt, attached) != 'weqatal':
            return False
        R2_STATS['fallback'] += 1
        return _apply_e(w, mt, report)

    # ── RUTA COMPLETA: morfologia presente ──
    if vt != 'perf':
        return False   # wayyiqtol (wayq), imperfecto, participio, etc. -> no aplica

    if has_stress_contrast(ps, nu):
        st = stress_position(mt)
        if st == 'ultima':
            R2_STATS['contraste_ultima(aplica)'] += 1
            return _apply_e(w, mt, report)
        if st == 'penult':
            R2_STATS['contraste_penult(copulativo->a)'] += 1
            return False
        R2_STATS['contraste_acento_indeterminado(->a)'] += 1
        return False
    else:
        # 2mp/2fp, 3a persona, dual: ni acento ni consonantes disambiguan.
        R2_STATS['sin_contraste(ambiguo)'] += 1
        if DEFAULT_AMBIG == 'e':
            return _apply_e(w, mt, report)
        return False


def main():
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_dir = os.path.join(BASE, f'respaldos_reglas_e_{stamp}')
    os.makedirs(backup_dir, exist_ok=True)
    print(f'Respaldos en: {backup_dir}\n')

    grand = Counter()
    examples = []

    for b in ORDER:
        src = os.path.join(BASE, f'{b}_lectura_samaritana.json')
        if not os.path.exists(src):
            print(f'  [SALTADO] {src}'); continue
        shutil.copy2(src, os.path.join(backup_dir, f'{b}_lectura_samaritana.json'))

        with open(src, encoding='utf-8') as f:
            data = json.load(f)

        book_rep = []
        for ch, chap in data['chapters'].items():
            for vs, verse in chap.items():
                words = verse.get('words', [])
                changed = False
                for idx in range(len(words)):
                    before = len(book_rep)
                    r3 = apply_R3(words[idx], book_rep)
                    r2 = apply_R2(words, idx, book_rep)
                    if r3 or r2:
                        changed = True
                        if b == 'genesis' and len(examples) < 12:
                            kind = book_rep[-1][0]
                            examples.append((kind, f'Gn {ch}:{vs}', book_rep[-1][3],
                                             book_rep[-1][1], book_rep[-1][2]))
                if changed:
                    verse['sam_reading'] = ' '.join(w['sam_reading'] for w in words)

        cnt = Counter(r[0] for r in book_rep)
        grand += cnt
        out = os.path.join(BASE, f'{b}_lectura_samaritana_e.json')
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f'  {b:14}  R2={cnt.get("R2",0):>4}  R3={cnt.get("R3",0):>4}  -> {os.path.basename(out)}')

    print('\n' + '=' * 60)
    print(f'TOTAL  R2 (we-qatal a->e): {grand.get("R2",0)}   R3 (*ay->e): {grand.get("R3",0)}')
    print('=' * 60)

    print(f'\nDiagnostico R2 (DEFAULT_AMBIG = {DEFAULT_AMBIG!r}):')
    if not R2_STATS:
        print('  (sin verbos+waw evaluados)')
    for k in sorted(R2_STATS):
        print(f'  {k:38} {R2_STATS[k]:>5}')
    if R2_STATS.get('fallback'):
        print('  -> Se uso FALLBACK: re-corre motor_samaritano.py para vt/ps/nu y vuelve a correr esto.')
    print('  Leyenda:')
    print('   contraste_ultima(aplica)            = 1cs/2ms/2fs/1cp con acento agudo -> CONSECUTIVO -> /e/')
    print('   contraste_penult(copulativo->a)     = mismas formas pero acento grave -> COPULATIVO -> /a/')
    print('   contraste_acento_indeterminado(->a) = acento no legible -> conservador /a/')
    print('   sin_contraste(ambiguo)              = 2mp/2fp/3a/dual -> no disambiguable -> DEFAULT_AMBIG')

    print('\nEjemplos en Genesis  [regla | ref | MT | antes -> despues]:')
    for kind, ref, mt, before, after in examples:
        print(f'  {kind} {ref}:  {mt}   {before} -> {after}')
    print('\nRevisa estos cambios. Los originales NO se tocaron; la salida esta en')
    print('*_lectura_samaritana_e.json. Si te convencen, el PDF v3 los usara.')


if __name__ == '__main__':
    main()
