"""
Motor Gutural Fonetico (capa de TRANSCRIPCION)  -- NO DESTRUCTIVO
================================================================

==================  MAPA UNIFICADO DEL MOTOR  ==================
El motor samaritano esta dividido en 3 CAPAS, cada regla vive en UN solo sitio
(no hay reglas duplicadas ni "sueltas" repartidas entre archivos):

  CAPA 1 - VOCALIZACION  (motor_samaritano.py)
      Reconstruye 'sam_reading' (hebreo cuadrado vocalizado) desde los corpus
      BHSA (masoretico) + SP (samaritano) y aplica las reglas fonologicas
      base R1-R9 (o->u, sheva, BKP, diptongos, etc.). Tambien exporta la
      morfologia (vt/ps/nu) que necesitan las capas siguientes.

  CAPA 2 - VOCAL /a/ vs /e/  (reglas_e_samaritano.py)
      Post-proceso NO destructivo sobre 'sam_reading'. Decide cuando una /a/
      tiberiana muta a /e/ samaritana:
        R2 we-qatal  : perfecto consecutivo (usa vt/ps/nu + acento masoretico).
        R3 *ay       : contraccion del diptongo historico (mayim -> meim...).
      Casos ambiguos (3a pers., 2pl, dual sin contraste de acento) -> /a/.

  CAPA 3 - TRANSCRIPCION LATINA  (ESTE ARCHIVO)
      Convierte 'sam_reading' a alfabeto latino en DOBLE LINEA, modelando el
      enmudecimiento de las guturales (Alef, He, Het, Ayin) segun la tradicion
      oral de Nablus (Ben-Hayyim 2000):
        G1 He (ה)  -> MUDA (solo deja la vocal).
        G2 Het (ח) -> MUDA, con transicion/alargamiento vocalico.
        G3 Ayin(ע) -> muda (la vocal queda).
        G4 Alef(א) -> muda; su vocal se conserva / fusiona.
        G5 Contraccion de vocales adyacentes tras caer gutural/mater:
             - iguales  -> larga con macron (u+u -> ū = 'tū').
             - distintas -> hiato: glide (u + vocal anterior = 'eluēim') o
               encuentro natural (å + u -> 'åu' = 'tåum').
           Las conversiones de base (cholam->u, sheva->å, plural -im->-ēim) ya
           vienen resueltas de la Capa 1 (motor_samaritano), por eso el colapso
           aqui es limpio y desacoplado.
        Lc Alargamiento COMPENSATORIO: gutural FINAL que cae -> la vocal
           precedente se alarga (Condicion B del experto; p.ej. rūaḥ -> rūa).
        ACENTO + LONGITUD POSICIONAL (Opcion C, ver _accent_lengthen):
           Acento PREDECIBLE en la penultima silaba (paroxitono). El macron
           posicional se inyecta SOLO en la silaba ABIERTA y TONICA cuando la
           vocal NO esta ya protegida (mater/plural/contraccion/compensatorio).
           Toda otra silaba (cerrada, o abierta atona) queda CORTA; la å nunca
           lleva macron. El silabificador trata el glide 'u' y los diptongos
           (lista cerrada åu/au/ēi/ei) con los Ajustes 1-4 del experto.
      Inventario vocalico cerrado (experto): [a, å, ā, e, ē, i, ī, o, u, ū];
      SIN schwa (ə). qamats -> å. Dos salidas:
        * LINEA ACADEMICA  (translit_acad_*): cualidad + longitud, å, sh=š, ts=ṣ.
        * LINEA HISPANA    (translit_hisp_*): lectura fluida en espanol (sin
          macrones ni å; sh/ts). Unica concesion editorial: el qamats QATAN se
          aplana a 'o' (kol, jojma...) SOLO por legibilidad -> ver is_qatan().

  PRESENTACION  (generar_pdf_html_v3.py)
      NO define transcripcion propia: importa ESTE archivo como unica fuente.

FUENTE: Ze'ev Ben-Hayyim (2000), "A Grammar of Samaritan Hebrew", Magnes Press /
Eisenbrauns. Acento y cantidad vocalica: cap. 4 (§§4.1-4.4).
NOTA (longitud): se marca por (a) longitud INHERENTE -- contraccion (G5), mater
lectionis y alargamiento compensatorio por gutural caida (Lc) -- y (b) longitud
POSICIONAL por acento: silaba ABIERTA + TONICA (penultima) en vocal breve no
protegida (ver _accent_lengthen). Cerrada o abierta atona -> corta; å sin macron.

SEGURIDAD (no destructivo):
  - NO modifica motor_samaritano.py ni ningun otro script.
  - NO toca el hebreo cuadrado: 'sam_reading' queda intacto (visor y PDF previos
    siguen igual).
  - Respalda con fecha los 5 JSON ANTES de leer y escribe la capa fonetica en
    ARCHIVOS NUEVOS: *_lectura_samaritana_fonetica.json (no sobrescribe).
"""
import json, os, sys, shutil, datetime

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.abspath(__file__))
ORDER = ['genesis', 'exodus', 'leviticus', 'numbers', 'deuteronomy']

# ── Unicode ───────────────────────────────────────────
SHEVA='\u05B0'; HATAF_S='\u05B1'; HATAF_P='\u05B2'; HATAF_Q='\u05B3'
CHIRIK='\u05B4'; TSERE='\u05B5'; SEGOL='\u05B6'; PATACH='\u05B7'
QAMATS='\u05B8'; CHOLAM='\u05B9'; CHOLAM_H='\u05BA'; QUBUTS='\u05BB'
DAGESH='\u05BC'; SHIN_DOT='\u05C1'; SIN_DOT='\u05C2'
ALL_VOWELS={SHEVA,HATAF_S,HATAF_P,HATAF_Q,CHIRIK,TSERE,SEGOL,PATACH,
            QAMATS,CHOLAM,CHOLAM_H,QUBUTS}

ALEF='\u05D0'; BET='\u05D1'; GIMEL='\u05D2'; DALET='\u05D3'; HE='\u05D4'
VAV='\u05D5'; ZAYIN='\u05D6'; HET='\u05D7'; TET='\u05D8'; YOD='\u05D9'
KAF_F='\u05DA'; KAF='\u05DB'; LAMED='\u05DC'; MEM_F='\u05DD'; MEM='\u05DE'
NUN_F='\u05DF'; NUN='\u05E0'; SAMEK='\u05E1'; AYIN='\u05E2'; PE_F='\u05E3'
PE='\u05E4'; TSADE_F='\u05E5'; TSADE='\u05E6'; QOF='\u05E7'; RESH='\u05E8'
SHIN='\u05E9'; TAV='\u05EA'

# Guturales que se ENMUDECEN en la lectura samaritana (G1-G4)
GUTTURALS_SILENT = {ALEF, HE, HET, AYIN}

# Consonante -> latin (fonetica samaritana; pe fricativa /f/, sin espirantizacion en BGDK)
CONS_LAT = {
    BET:'b', GIMEL:'g', DALET:'d', VAV:'w', ZAYIN:'z', TET:'ṭ', YOD:'y',
    KAF:'k', KAF_F:'k', LAMED:'l', MEM:'m', MEM_F:'m', NUN:'n', NUN_F:'n',
    SAMEK:'s', PE:'f', PE_F:'f', TSADE:'ṣ', TSADE_F:'ṣ', QOF:'q', RESH:'r',
    TAV:'t',
}

# Vocal -> latin (LINEA ACADEMICA). Inventario cerrado (decision del experto):
#   [a, å, ā, e, ē, i, ī, o, u, ū]  -- SIN schwa (ə) y SIN breves.
#   - qamats -> å (a posterior/velar, no lleva macron: es cualidad).
#   - sheva  -> se OMITE (en samaritano no hay fonema schwa; Ben-Hayyim).
#   - hatafs -> vocal plena de su cualidad (sin breve), porque van en guturales mudas.
#   - tsere/chirik: la LONGITUD (macron) surge de tres fuentes que SI podemos
#     calcular hoy: contraccion de vocales (G5), mater lectionis y alargamiento
#     COMPENSATORIO al caer una gutural final (Condicion B / Lc, ver translit_word).
#     La longitud meramente POSICIONAL (silaba abierta tonica/pretonica =
#     Condicion A del experto) depende del ACENTO y queda pendiente del punto 3.
VOWEL_LAT = {
    PATACH:'a', QAMATS:'å', SEGOL:'e', TSERE:'ē', CHIRIK:'i',
    CHOLAM:'o', CHOLAM_H:'o', QUBUTS:'u',
    HATAF_S:'e', HATAF_P:'a', HATAF_Q:'o',
}

LONG = {'a':'ā','å':'å','e':'ē','ē':'ē','i':'ī','o':'ō','u':'ū'}

# Vocales BREVES que el acento puede alargar posicionalmente (NUNCA la å, que es
# cualidad y por decision del experto jamas lleva macron por codificacion).
SHORT_LENGTHENABLE = {'a', 'e', 'i', 'o', 'u'}
# Diccionario DURO de diptongos (Ben-Hayyim; lista cerrada dada por el experto).
# Cualquier otro encuentro de vocales que no sea glide se parte en HIATO (V-V).
DIPHTHONGS = {'åu', 'au', 'ēi', 'ei'}
_HIGH = {'u', 'ū', 'i', 'ī'}      # vocales altas (para el "eco" de gutural, Ajuste 3)
_BACK = {'o', 'u'}                # vocales posteriores (origen del glide labial)
_FRONT = {'i', 'ī', 'e', 'ē'}     # vocales anteriores (destino del glide)


def _lengthen(vstr):
    """Alarga (macron) la ULTIMA vocal de un token vocalico: 'u'->'ū', 'a'->'ā'.
    'å' ya es cualidad larga y no cambia. Usado por el alargamiento compensatorio."""
    if not vstr:
        return vstr
    return vstr[:-1] + LONG.get(vstr[-1], vstr[-1])


def _combine_vowels(t1, t2):
    """Resuelve DOS nucleos vocalicos en contacto (tipico al caer una gutural o
    mater) y devuelve una LISTA de tokens tipados (kind, valor, protegida):
    'v' = nucleo vocalico, 'g' = glide (cuenta como consonante al silabificar).
    'protegida'=True marca longitud INHERENTE (contraccion/diptongo): inmune al
    acortamiento posicional. Ajustes del silabificador (Ben-Hayyim, cap. 4):
      - Ajuste 3 (eco de gutural): vocal ALTA (u/ū/i/ī) + 'a' -> HIATO (rū-a),
        no es diptongo; quedan dos nucleos para que rū sea silaba abierta.
      - Vocales IGUALES -> contraccion: un solo nucleo largo (u+u -> ū = 'tū').
      - GLIDE (Ajuste 2): posterior (o/u) + anterior (i/ī/e/ē) -> el primero pasa
        a semiconsonante 'u' (cuenta como CONSONANTE al silabificar) + nucleo
        anterior (p.ej. אלהים: u + ē -> 'u'(glide) + 'ē' -> 'aluēim').
      - DIPTONGO (lista cerrada): un solo nucleo (תהום: å + u -> 'åu' = 'tåum').
      - Red de seguridad: cholam crudo 'o' + 'u' -> 'ū'.
      - Ajuste 4 (defecto): cualquier otro encuentro -> HIATO (dos nucleos)."""
    v1, v2 = t1[1], t2[1]
    a, b = v1[-1], v2[-1]
    if a in _HIGH and b == 'a':                 # Ajuste 3: eco de gutural -> hiato
        return [t1, t2]
    if a == b:                                  # contraccion: un nucleo largo
        return [('v', v1[:-1] + LONG.get(a, a), True)]
    if a in _BACK and b in _FRONT:              # Ajuste 2: glide labial
        return [('g', 'u', False), ('v', v2, True)]
    combo = v1 + v2
    if combo in DIPHTHONGS:                     # diptongo: un solo nucleo
        return [('v', combo, True)]
    if a == 'o' and b == 'u':                   # red de seguridad (cholam crudo)
        return [('v', v1[:-1] + 'ū', True)]
    return [t1, t2]                             # Ajuste 4: defecto -> hiato

# Mapa LINEA ACADEMICA -> LINEA HISPANA (lectura fluida: sin macrones ni å, sh/ts).
_TO_HISP = {
    ord('š'): 'sh', ord('ṣ'): 'ts', ord('ṭ'): 't',
    ord('å'): 'a', ord('ā'): 'a', ord('ē'): 'e', ord('ī'): 'i',
    ord('ō'): 'o', ord('ū'): 'u',
}


def to_hispana(acad):
    """Convierte la transcripcion academica en la hispana simplificada."""
    return (acad or '').translate(_TO_HISP)


# ── Qamats Qatan (concesion de LEGIBILIDAD solo para la linea HISPANA) ──
# El qamats tiberiano se lee SIEMPRE /å/ en samaritano (linea academica).
# Pero en la linea hispana, por inteligibilidad para el lector espanol, el
# qamats QATAN se aplana a 'o' (p.ej. כָּל -> "kol", חכמה -> "jojma").
# OJO: 'o' NO es fonetica samaritana real; es una concesion editorial.
#
# Deteccion (segun el experto, cubre >98%):
#   Regla 1 (automatica, sobre el 'mt'): QAMATS + consonante con HATAF QAMATS
#           -> el primer qamats es qatan (aholo, poolo, tsohoraim, tooro).
#   Regla 2 (lista curada por esqueleto consonantico): sustantivos/segolados
#           con qamats en silaba trabada (chokma, korban, okla, orma, ...).
#   Regla 3 (kol y derivados): el token כל se captura por esqueleto; los
#           prefijos (mi-, le-, ha-) van como tokens separados en el corpus.
# En palabras marcadas se aplana SOLO el PRIMER qamats (el qatan); los demas
# qamats quedan como /a/ (gadol). La academica nunca se toca (siempre å).
FINAL_MAP = {'\u05DA': '\u05DB', '\u05DD': '\u05DE', '\u05DF': '\u05E0',
             '\u05E3': '\u05E4', '\u05E5': '\u05E6'}


def skeleton(s):
    """Esqueleto consonantico (sin niqqud, finales normalizadas)."""
    out = []
    for ch in s or '':
        cp = ord(ch)
        if 0x05D0 <= cp <= 0x05EA:
            out.append(FINAL_MAP.get(ch, ch))
        elif cp in (0xFB2A, 0xFB2B, 0xFB2C, 0xFB2D):
            out.append(SHIN)
    return ''.join(out)


# Lista curada (ampliable con la que entregue el experto). Se normaliza por
# esqueleto, asi que da igual escribirlas con o sin finales/niqqud.
_QATAN_RAW = [
    'כל',                                            # kol (constructo)
    'חכמה', 'קרבן', 'אכלה', 'ערמה', 'קדקדו',         # sustantivos/segolados
    'תכנית', 'חפני', 'עמרי',                          # + nombres propios
    'שמרה', 'אסרה', 'רנו',                            # formas verbales (cholam->qatan)
]
QATAN_WORDS = {skeleton(w) for w in _QATAN_RAW}


def _has_qatan_pattern(mt):
    """Regla 1: QAMATS seguido (consonante siguiente) de HATAF QAMATS."""
    units = parse(mt or '')
    for i in range(len(units) - 1):
        if QAMATS in units[i][1] and HATAF_Q in units[i + 1][1]:
            return True
    return False


def is_qatan(sam_reading, mt=''):
    """True si el primer qamats debe leerse 'o' en la linea hispana."""
    return (skeleton(sam_reading) in QATAN_WORDS) or _has_qatan_pattern(mt)


def parse(s):
    """Divide en unidades (consonante, [diacriticos])."""
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


def get_vowel(dia):
    for d in dia:
        if d in ALL_VOWELS:
            return d
    return None


def _accent_lengthen(out):
    """Longitud POSICIONAL por acento (regla cruzada del experto, Opcion C;
    Ben-Hayyim 2000, cap. 4 'The Accent and Quantity of Vowels', §§4.1-4.4).

    El acento samaritano es PREDECIBLE: cae en la PENULTIMA silaba fonetica
    (paroxitono), sin formas pausales. Los monosilabos llevan el acento en su
    unica silaba. (La rara excepcion oxitona por gutural intermedia/final caida
    afecta a una silaba que ya es LARGA por alargamiento compensatorio -> ya
    lleva macron de todos modos, asi que NO cambia la salida de longitud.)

    Regla de longitud (se aplica SOLO a la linea academica):
      * Vocales PROTEGIDAS (longitud inherente: mater lectionis, plural/dual
        -ēm/-ēim, contraccion historica, alargamiento compensatorio) ya llegan
        aqui con macron o como diptongo -> no son 'breves' y NO se tocan.
      * Vocal BREVE no protegida: lleva macron SOLO si su silaba es ABIERTA y
        ademas es la TONICA (penultima). Cerrada (tonica o atona) y abierta atona
        -> CORTA. La 'å' jamas lleva macron (cualidad, no longitud).
    Implementacion: solo puede alargar el nucleo de la silaba penultima, y solo
    si es una vocal breve simple {a,e,i,o,u} en silaba abierta."""
    nuclei = [i for i, t in enumerate(out) if t[0] == 'v']
    if len(nuclei) < 2:
        return out                       # monosilabo: sin macron posicional
    t = nuclei[-2]                        # nucleo TONICO (penultimo)
    nxt = nuclei[-1]                      # nucleo siguiente
    # Silaba abierta si entre el nucleo tonico y el siguiente hay <=1 consonante
    # (glide incluido): 0/1 cons -> abierta (V-CV o hiato); >=2 -> cerrada (VC-CV).
    ncons = sum(1 for tk in out[t + 1:nxt] if tk[0] in ('c', 'g'))
    if ncons <= 1:
        _, val, prot = out[t]
        if not prot and val in SHORT_LENGTHENABLE:  # breve simple no protegida (no å, no larga)
            out[t] = ('v', LONG[val], False)
    return out


def _inherent_lengthen(out):
    """Condicion 1 (longitud INHERENTE): toda vocal PROTEGIDA (mater lectionis,
    plural/dual, contraccion, compensatorio) lleva macron SIEMPRE, sin importar
    posicion ni acento (p.ej. אור -> 'ūr', no 'ur'). Diptongos y vocales ya
    largas quedan igual; la å nunca lleva macron."""
    for i, (k, val, prot) in enumerate(out):
        if k == 'v' and prot and val in SHORT_LENGTHENABLE:
            out[i] = ('v', LONG[val], True)
    return out


def translit_word(s, flatten_first_qamats=False):
    """Transcripcion latina con guturales enmudecidas (G1-G5) + longitud por
    acento (Opcion C). flatten_first_qamats=True (solo linea hispana de palabras
    qatan): el PRIMER qamats se aplana a 'o'; los demas qamats quedan en å/a."""
    # Maqaf: el samaritano es INMUNE al maqaf (cada palabra lexica conserva su
    # propio acento penultimo). Se trata cada parte como token independiente.
    if '\u05BE' in s:
        return '\u05BE'.join(
            translit_word(p, flatten_first_qamats) for p in s.split('\u05BE') if p)
    units = parse(s)
    toks = []  # tokens TIPADOS (kind, valor, protegida): 'c'=cons, 'v'=vocal.
    _flat = {'on': flatten_first_qamats}

    def vlat(v):
        if _flat['on'] and v == QAMATS:
            _flat['on'] = False   # solo el PRIMER qamats
            return 'o'
        return VOWEL_LAT.get(v, '')

    for i, (c, d) in enumerate(units):
        v = get_vowel(d)
        is_shuruq = (c == VAV and DAGESH in d and v is None)
        is_mater_yod = (c == YOD and v is None)
        is_mater_vav = (c == VAV and v is None and DAGESH not in d)

        # Shuruq: vav+dagesh sin vocal = /u/ (mater -> longitud INHERENTE)
        if is_shuruq:
            toks.append(('v', 'u', True))
            continue

        # G1-G4: gutural enmudecida -> no aporta consonante.
        if c in GUTTURALS_SILENT:
            # Condicion B (Lc): alargamiento COMPENSATORIO. Si la gutural es
            # FINAL de palabra, cerraba la silaba; al enmudecer, la silaba se
            # abre y la vocal PRECEDENTE se alarga (macron) y queda PROTEGIDA.
            if i == len(units) - 1:
                for k in range(len(toks) - 1, -1, -1):
                    if toks[k][0] == 'v':
                        toks[k] = ('v', _lengthen(toks[k][1]), True)
                        break
            if v is not None and v != SHEVA:    # conserva su vocal (p.ej. patach furtiva, breve)
                toks.append(('v', vlat(v), False))
            continue

        # Matres lectionis (yod/vav mudas) -> vocal de transicion (longitud INHERENTE)
        if is_mater_yod:
            toks.append(('v', 'i', True))
            continue
        if is_mater_vav:
            toks.append(('v', 'o', True))
            continue

        # Consonante normal
        if c == SHIN:
            lat = 's' if SIN_DOT in d else 'š'
        else:
            lat = CONS_LAT.get(c, '')
        if lat:
            toks.append(('c', lat, False))
        if v is not None and v != SHEVA:
            toks.append(('v', vlat(v), False))   # vocal de base: longitud POSICIONAL
        # sheva: se OMITE (sin fonema schwa). El motor ya resolvio las shevas
        # relevantes a vocal plena o elision antes de esta transcripcion.

    # G5: fusion de vocales adyacentes (tipico tras caer una gutural). Produce
    # tokens TIPADOS: ('c', cons), ('g', glide labial) y ('v', nucleo vocalico)
    # -- glide y consonante cuentan igual al silabificar; los diptongos quedan
    # como UN solo nucleo. Asi el silabificador puede contar silabas de verdad.
    out = []
    for tok in toks:
        if tok[0] == 'v' and tok[1] and out and out[-1][0] == 'v':
            prev = out.pop()
            out.extend(_combine_vowels(prev, tok))
        else:
            out.append(tok)

    # Condicion 1: longitud INHERENTE (vocales protegidas -> macron siempre).
    out = _inherent_lengthen(out)
    # Condicion 2: longitud POSICIONAL (macron de la silaba abierta TONICA).
    out = _accent_lengthen(out)
    return ''.join(tok[1] for tok in out)


def translit_verse(sam_reading):
    return ' '.join(translit_word(w) for w in sam_reading.split(' ') if w)


# ── DOBLE LINEA DE SALIDA (academica + hispana) ──
def translit_acad_word(s):
    """Linea ACADEMICA: cualidad (a/å/e/i/o/u) + longitud por contraccion/mater
    (ā/ē/ī/ō/ū), guturales mudas, sin schwa. Ej.: 'bå råšīt bårå aluēim'."""
    return translit_word(s)


def translit_acad_verse(s):
    return translit_verse(s)


def translit_hisp_word(s, mt=''):
    """Linea HISPANA: lectura fluida en espanol (sin macrones ni å; sh/ts).
    Ej.: 'ba rashit bara aluim'. En palabras de qamats qatan (lista curada +
    patron hataf del 'mt'), el PRIMER qamats se aplana a 'o' SOLO por
    legibilidad (p.ej. כָּל -> 'kol', חכמה -> 'jojma', אכלה -> 'okla')."""
    return to_hispana(translit_word(s, flatten_first_qamats=is_qatan(s, mt)))


def translit_hisp_verse(s):
    """Verso hispana a partir del string (solo lista curada; sin patron hataf,
    que requiere el 'mt' por palabra). Para el patron hataf, construye el verso
    palabra por palabra pasando w['mt'] (ver main() y el generador de PDF)."""
    return ' '.join(translit_hisp_word(w) for w in s.split(' ') if w)


def main():
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_dir = os.path.join(BASE, f'respaldos_fonetica_{stamp}')
    os.makedirs(backup_dir, exist_ok=True)
    print(f'Respaldos en: {backup_dir}')

    for b in ORDER:
        # Cadena del motor: usa el JSON con reglas /e/ (Capa 2) si existe;
        # si no, el JSON base (Capa 1). Asi la fonetica refleja R2/R3 igual
        # que el PDF v3 (que tambien prefiere *_e.json).
        src_e = os.path.join(BASE, f'{b}_lectura_samaritana_e.json')
        src_base = os.path.join(BASE, f'{b}_lectura_samaritana.json')
        src = src_e if os.path.exists(src_e) else src_base
        if not os.path.exists(src):
            print(f'  [SALTADO] no existe: {src_base}')
            continue
        print(f'  fuente {b:14} -> {os.path.basename(src)}')

        # 1) RESPALDO de la fuente (no se modifica el original)
        shutil.copy2(src, os.path.join(backup_dir, os.path.basename(src)))

        # 2) Cargar y anadir capa fonetica
        with open(src, encoding='utf-8') as f:
            data = json.load(f)

        nverses = 0
        for ch, chap in data['chapters'].items():
            for vs, verse in chap.items():
                words = verse.get('words', [])
                for w in words:
                    sr = w.get('sam_reading', '')
                    acad = translit_acad_word(sr) if sr else ''
                    w['transcripcion_academica'] = acad
                    w['transcripcion_hispana'] = (
                        translit_hisp_word(sr, w.get('mt', '')) if sr else '')
                    w['fonetica'] = acad  # alias retrocompatible
                if words:
                    verse['transcripcion_academica'] = ' '.join(
                        w['transcripcion_academica'] for w in words
                        if w.get('transcripcion_academica'))
                    verse['transcripcion_hispana'] = ' '.join(
                        w['transcripcion_hispana'] for w in words
                        if w.get('transcripcion_hispana'))
                else:
                    sr_v = verse.get('sam_reading', '')
                    verse['transcripcion_academica'] = translit_acad_verse(sr_v)
                    verse['transcripcion_hispana'] = translit_hisp_verse(sr_v)
                verse['fonetica'] = verse['transcripcion_academica']
                nverses += 1

        data['fonetica_engine'] = ('Motor Gutural Fonetico v2 (guturales mudas G1-G5; '
                                   'doble linea academica/hispana; sin schwa)')

        # 3) Escribir ARCHIVO NUEVO (originales intactos)
        out = os.path.join(BASE, f'{b}_lectura_samaritana_fonetica.json')
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f'  {b:14} {nverses:>5} versos -> {os.path.basename(out)}')

    # ── Muestra de validacion (Genesis 1:1-2) ──
    gen = os.path.join(BASE, 'genesis_lectura_samaritana_fonetica.json')
    if os.path.exists(gen):
        with open(gen, encoding='utf-8') as f:
            g = json.load(f)
        print('\n' + '=' * 60)
        print('MUESTRA  Genesis 1:1-2  (doble linea)')
        print('=' * 60)
        for vs in ('1', '2'):
            v = g['chapters']['1'][vs]
            print(f'\nGn 1:{vs}')
            print(f'  Hebreo:    {v["sam_reading"]}')
            print(f'  Academica: {v["transcripcion_academica"]}')
            print(f'  Hispana:   {v["transcripcion_hispana"]}')


if __name__ == '__main__':
    main()
