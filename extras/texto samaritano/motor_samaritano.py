"""
Motor de Lectura Samaritana v4
==============================
Genera hebreo cuadrado niqqudizado con la pronunciación samaritana.

Reglas fonológicas: Ze'ev Ben-Hayyim, "A Grammar of Samaritan Hebrew" (2000)

Input:  SP consonantal (dt-ucph/sp) + MT vocalizado (etcbc/bhsa)
Output: Hebreo cuadrado con niqqud que representa la lectura samaritana

v4 fixes:
- R1: Diptongo -ayim preserva Yod como mater lectionis (no eliminar consonantes)
- R1b: Plural masculino -im -> -em generalizado
- R4: Sheva inicial -> qamats incluso en preposiciones sueltas (n==1)
- R8: Vav conjuncion: shuruq (dagesh-as-vowel) eliminado antes de poner patach
"""
import sys, json, argparse, time, unicodedata
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ============================================================
# HEBREW UNICODE CONSTANTS
# ============================================================
# Niqqud
SHEVA    = '\u05B0'; HATAF_S  = '\u05B1'; HATAF_P  = '\u05B2'
HATAF_Q  = '\u05B3'; CHIRIK   = '\u05B4'; TSERE    = '\u05B5'
SEGOL    = '\u05B6'; PATACH   = '\u05B7'; QAMATS   = '\u05B8'
CHOLAM   = '\u05B9'; CHOLAM_H = '\u05BA'; QUBUTS   = '\u05BB'
DAGESH   = '\u05BC'; RAFE     = '\u05BF'
SHIN_DOT = '\u05C1'; SIN_DOT  = '\u05C2'

ALL_VOWELS = {SHEVA, HATAF_S, HATAF_P, HATAF_Q, CHIRIK, TSERE,
              SEGOL, PATACH, QAMATS, CHOLAM, CHOLAM_H, QUBUTS}

# Consonants
ALEF = '\u05D0'; BET = '\u05D1'; GIMEL = '\u05D2'; DALET = '\u05D3'
HE = '\u05D4'; VAV = '\u05D5'; ZAYIN = '\u05D6'; HET = '\u05D7'
TET = '\u05D8'; YOD = '\u05D9'; KAF_F = '\u05DA'; KAF = '\u05DB'
LAMED = '\u05DC'; MEM_F = '\u05DD'; MEM = '\u05DE'; NUN_F = '\u05DF'
NUN = '\u05E0'; SAMEK = '\u05E1'; AYIN = '\u05E2'; PE_F = '\u05E3'
PE = '\u05E4'; TSADE_F = '\u05E5'; TSADE = '\u05E6'; QOF = '\u05E7'
RESH = '\u05E8'; SHIN = '\u05E9'; TAV = '\u05EA'

GUTTURALS = {ALEF, HE, HET, AYIN}
BGDKPT = {BET, GIMEL, DALET, KAF, PE, TAV}

# Finals mapping
FINAL_MAP = {KAF_F: KAF, MEM_F: MEM, NUN_F: NUN, PE_F: PE, TSADE_F: TSADE}
ALL_CONSONANTS = set(chr(c) for c in range(0x05D0, 0x05EB))


def has_niqqud(text):
    """True if the string carries any vowel point (niqqud U+05B0-U+05BB)."""
    return any('\u05B0' <= c <= '\u05BB' for c in (text or ''))


def feat(F, name, node):
    """Lee una feature morfologica de Text-Fabric de forma segura.
    Devuelve '' si la feature no existe en el corpus o el valor es None.
    Usado para vt (tiempo verbal), ps (persona) y nu (numero), necesarios
    para distinguir we-qatal consecutivo de we+perfecto copulativo (R2)."""
    try:
        obj = getattr(F, name)
    except Exception:
        return ''
    try:
        return obj.v(node) or ''
    except Exception:
        return ''


def normalize_cons(text):
    """Strip all diacritics, keep only consonants for comparison."""
    out = []
    for ch in text:
        cp = ord(ch)
        if 0x05D0 <= cp <= 0x05EA:
            out.append(FINAL_MAP.get(ch, ch))
        elif cp in (0xFB2A, 0xFB2B, 0xFB2C, 0xFB2D):
            out.append(SHIN)
    return ''.join(out)


# ============================================================
# WORD PARSER
# ============================================================
def parse_word(g_word_utf8):
    """Parse vocalized word into [(consonant, [diacritics]), ...]"""
    units = []
    cur_c = None
    cur_d = []

    for ch in g_word_utf8:
        cp = ord(ch)
        # Precomposed forms
        if cp == 0xFB2A:
            if cur_c is not None: units.append((cur_c, cur_d[:]))
            cur_c, cur_d = SHIN, [SHIN_DOT]
        elif cp == 0xFB2B:
            if cur_c is not None: units.append((cur_c, cur_d[:]))
            cur_c, cur_d = SHIN, [SIN_DOT]
        elif cp == 0xFB2C:
            if cur_c is not None: units.append((cur_c, cur_d[:]))
            cur_c, cur_d = SHIN, [DAGESH, SHIN_DOT]
        elif cp == 0xFB2D:
            if cur_c is not None: units.append((cur_c, cur_d[:]))
            cur_c, cur_d = SHIN, [DAGESH, SIN_DOT]
        elif 0x05D0 <= cp <= 0x05EA:
            if cur_c is not None: units.append((cur_c, cur_d[:]))
            cur_c, cur_d = ch, []
        elif cp in (0x05B0, 0x05B1, 0x05B2, 0x05B3, 0x05B4, 0x05B5,
                    0x05B6, 0x05B7, 0x05B8, 0x05B9, 0x05BA, 0x05BB,
                    0x05BC, 0x05BD, 0x05BF, 0x05C1, 0x05C2):
            cur_d.append(ch)
        # Skip cantillation (0591-05AF) and other marks

    if cur_c is not None:
        units.append((cur_c, cur_d[:]))
    return units


def get_vowel(dia):
    for d in dia:
        if d in ALL_VOWELS:
            return d
    return None


def set_vowel(dia, old_v, new_v):
    return [new_v if d == old_v else d for d in dia]


def remove_vowel(dia, v):
    return [d for d in dia if d != v]


def has_dagesh(dia):
    return DAGESH in dia


def rebuild(units):
    """Reconstruct Hebrew string from parsed units."""
    parts = []
    for cons, dia in units:
        parts.append(cons)
        for d in sorted(dia, key=lambda x: (
            0 if x in (SHIN_DOT, SIN_DOT) else
            1 if x == DAGESH else
            2
        )):
            parts.append(d)
    return ''.join(parts)


# ============================================================
# SAMARITAN PHONOLOGICAL RULES (Ben-Hayyim 2000)
# ============================================================
def apply_samaritan_rules(units, pos='', vt='', vs=''):
    """Transform MT vocalization to Samaritan reading.
    vt/vs (tiempo y tema verbal de la BHSA) permiten excepciones morfologicas:
    el participio activo Qal samaritano sigue el patron qåṭel (no el tiberiano
    qōṭēl), por lo que su cholam de 1a silaba se lee å (Ben-Hayyim)."""
    r = [[c, list(d)] for c, d in units]
    n = len(r)
    if n == 0:
        return units
    is_ptc_qal = (vt == 'ptca' and vs == 'qal')

    # ── R1: Diphthong -ayim → -ēm (PRESERVE CONSONANTS) ────
    # שָׁמַיִם → שָּׁמֵיִם (tsere on pre-yod consonant, yod stays mute)
    # Never delete consonants: sp_cons integrity must be maintained
    if n >= 3:
        i = n - 3
        c1, d1 = r[i]; c2, d2 = r[i+1]; c3, d3 = r[i+2]
        v1 = get_vowel(d1); v2 = get_vowel(d2)
        if c2 == YOD and c3 in (MEM, MEM_F):
            if v1 in (PATACH, QAMATS, SEGOL) and v2 in (CHIRIK, None):
                # Change vowel on consonant before yod: patach/qamats → tsere
                r[i][1] = remove_vowel(d1, v1)
                r[i][1].append(TSERE)
                # Yod becomes mute: remove its chirik (keep consonant)
                r[i+1][1] = remove_vowel(d2, CHIRIK) if v2 == CHIRIK else d2[:]
                n = len(r)

    # ── R1b: Plural masc -im → -ēm (generalized) ─────────
    # In Samaritan, masculine plural ending is -ēm, not -īm
    # Case A: ...C(chirik)+yod+mem → ...C(tsere)+yod+mem
    # Case B: ...yod(chirik)+mem → ...yod(tsere)+mem
    # Case C: defective spelling (no yod), chirik on r[-2]
    if n >= 2:
        c_last = r[-1][0]
        if c_last in (MEM, MEM_F):
            # Case B: yod is r[-2] and carries chirik
            if r[-2][0] == YOD and get_vowel(r[-2][1]) == CHIRIK:
                r[-2][1] = set_vowel(r[-2][1], CHIRIK, TSERE)
            # Case A: yod is r[-2] (mute), chirik on r[-3]
            elif n >= 3 and r[-2][0] == YOD and get_vowel(r[-2][1]) is None:
                if get_vowel(r[-3][1]) == CHIRIK:
                    r[-3][1] = set_vowel(r[-3][1], CHIRIK, TSERE)
            # Case C: defective spelling (no yod), chirik on r[-2]
            elif r[-2][0] != YOD and get_vowel(r[-2][1]) == CHIRIK:
                r[-2][1] = set_vowel(r[-2][1], CHIRIK, TSERE)

    # ── R1c: 2ms suffix ךָ (-kha) → -ak ───────────────────
    # In Samaritan, the 2ms suffix is pronounced -ak, not -kha
    if n >= 2:
        if r[-1][0] == KAF_F and get_vowel(r[-1][1]) == QAMATS:
            # Remove qamats from final kaf
            r[-1][1] = remove_vowel(r[-1][1], QAMATS)
            # Add patach to previous consonant if it has no vowel or has sheva
            v_prev = get_vowel(r[-2][1])
            if v_prev in (None, SHEVA):
                r[-2][1] = set_vowel(r[-2][1], SHEVA, PATACH) if v_prev == SHEVA else r[-2][1] + [PATACH]

    # ── R1d: 3ms plural-noun suffix -āyw → -u ─────────────
    # Ben-Hayyim: "his" (pl. nouns) -āyw is read /-u/ in Samaritan
    # אלהָיו (Elohav) → Eluww-u | דברָיו (devarav) → dabbar-u
    # Keep consonants: yod stays mute, vav becomes shuruq (vav+dagesh)
    if n >= 3 and r[-1][0] == VAV and get_vowel(r[-1][1]) is None:
        if r[-2][0] == YOD and get_vowel(r[-2][1]) is None:
            v_prev = get_vowel(r[-3][1])
            if v_prev in (QAMATS, PATACH):
                r[-3][1] = remove_vowel(r[-3][1], v_prev)
                if DAGESH not in r[-1][1]:
                    r[-1][1].append(DAGESH)

    # ── R2: Tsere before silent Alef → Qamats ─────────────
    # רֵאשִׁית → רָאשִׁית (Bereshit → Barashit reading)
    for i in range(n - 1):
        if r[i+1][0] == ALEF and get_vowel(r[i+1][1]) is None:
            if get_vowel(r[i][1]) == TSERE:
                r[i][1] = set_vowel(r[i][1], TSERE, QAMATS)

    # ── R3: Hataf vowels → full vowels (any consonant) ──────
    # Samaritan has no reduced vowels; hatafs become full vowels.
    # Applies to gutturals AND the rare hataf under other consonants.
    for i in range(n):
        c, d = r[i]
        v = get_vowel(d)
        if v == HATAF_S:
            r[i][1] = set_vowel(d, HATAF_S, PATACH)
        elif v == HATAF_P:
            r[i][1] = set_vowel(d, HATAF_P, QAMATS if c in GUTTURALS else PATACH)
        elif v == HATAF_Q:
            r[i][1] = set_vowel(d, HATAF_Q, QAMATS)

    # ── R4: Initial sheva → full vowel ──────────────────────
    # Samaritan doesn't allow sheva mobile at word start
    # בְּרֵאשִׁית → בָּרֵאשִׁית
    # Also applies to single-consonant prepositions: בְּ → בָּ
    if n >= 1:
        v0 = get_vowel(r[0][1])
        if v0 == SHEVA:
            # Non-gutturals → qamats; gutturals (e.g. הְיֵה) → patach
            new_v = PATACH if r[0][0] in GUTTURALS else QAMATS
            r[0][1] = set_vowel(r[0][1], SHEVA, new_v)

    # ── R5: Cholam → qubuts / shuruq ───────────────
    # Ben-Hayyim: historical long o becomes u in Samaritan
    # תֹהוּ → תֻהוּ | תְּהוֹם → תָהוּם
    for i in range(n):
        v = get_vowel(r[i][1])
        if v in (CHOLAM, CHOLAM_H):
            # Excepcion lexica (experto): el cuantificador כל ("todo") ignora el
            # espectro o/u y se normaliza a la clase QAMATS (kål). Cubre כל y sus
            # derivados con prefijo (מכל, לכל, הכל): cholam sobre Kaf seguido de
            # Lamed FINAL. Despues, la capa fonetica lo lee å (acad) / o (hispana
            # por la regla de qamats qatan), igual que el כָּל ya vocalizado.
            if r[i][0] == KAF and i + 1 == n - 1 and r[i+1][0] == LAMED:
                old = CHOLAM if v == CHOLAM else CHOLAM_H
                r[i][1] = set_vowel(r[i][1], old, QAMATS)
                continue
            # Excepcion morfologica (experto): participio activo Qal -> patron
            # qåṭel; el cholam de la raiz se lee å, no u.
            if is_ptc_qal:
                old = CHOLAM if v == CHOLAM else CHOLAM_H
                r[i][1] = set_vowel(r[i][1], old, QAMATS)
                continue
            # If followed by a silent Vav, make it a Shuruq (Vav+Dagesh)
            if i + 1 < n and r[i+1][0] == VAV and get_vowel(r[i+1][1]) is None:
                r[i][1] = remove_vowel(r[i][1], v)
                if DAGESH not in r[i+1][1]:
                    r[i+1][1].append(DAGESH)
            else:
                # Otherwise just change to Qubuts
                old = CHOLAM if v == CHOLAM else CHOLAM_H
                r[i][1] = set_vowel(r[i][1], old, QUBUTS)

    # ── R6: Final sheva is always silent → remove ───────────
    # (but NOT if the word is a single consonant like וְ)
    if n > 1:
        v_last = get_vowel(r[-1][1])
        if v_last == SHEVA:
            r[-1][1] = remove_vowel(r[-1][1], SHEVA)

    # ── R7: Medial sheva after short vowel → silent ─────────
    for i in range(1, n - 1):
        v = get_vowel(r[i][1])
        if v == SHEVA:
            prev_v = get_vowel(r[i-1][1])
            if prev_v in (PATACH, SEGOL, CHIRIK, QUBUTS):
                r[i][1] = remove_vowel(r[i][1], SHEVA)

    # ── R7b: Remaining medial sheva mobile → full vowel (Chirik) ─────────
    # הָיְתָה → הָיִתָה
    for i in range(1, n - 1):
        v = get_vowel(r[i][1])
        if v == SHEVA:
            r[i][1] = set_vowel(r[i][1], SHEVA, CHIRIK)

    # ── R8: Vav conjunction → always gets patach ────────────
    # Samaritan never leaves vav "naked" without a vowel
    # וְ → וַ | ו (bare) → וַ | וּ (shuruq) → וַ
    # Shuruq (וּ) is encoded as vav+dagesh; the dagesh IS the vowel /u/
    if n == 1 and r[0][0] == VAV:
        v = get_vowel(r[0][1])
        if v == SHEVA:
            r[0][1] = set_vowel(r[0][1], SHEVA, PATACH)
        elif v is None:
            if has_dagesh(r[0][1]):
                # Dagesh here = shuruq (vowel u), not dagesh forte
                r[0][1] = [d for d in r[0][1] if d != DAGESH]
            r[0][1].append(PATACH)

    # ── R9: Segol in pausal/stressed → patach ───────────────
    # Samaritan tends to open segol to patach in many positions
    for i in range(n):
        v = get_vowel(r[i][1])
        if v == SEGOL and r[i][0] not in GUTTURALS:
            next_is_end = (i == n - 1) or (i == n - 2 and get_vowel(r[-1][1]) is None)
            if next_is_end:
                r[i][1] = set_vowel(r[i][1], SEGOL, PATACH)

    # ── R10: Qamats hatuf (o sound) stays as qamats ─────────
    # In Samaritan, qamats is always /a/, never /o/
    # (No action needed - qamats stays as-is, but semantically = /a/)

    # ── R11: Tsere before consonant cluster → segol ─────────
    # (Minor rule, skip for now)

    # ── R12: Dagesh hazaq in bgdkpt retained ────────────────
    # Samaritan preserves doubled consonants (dagesh forte)
    # (Already present from MT, no change needed)

    return [tuple(u) for u in r]


# ============================================================
# WORD ALIGNMENT (consonantal matching, not positional)
# ============================================================
MATRES = set('אהוי')  # matres lectionis: differences here are "cheap"

def word_sim(a, b):
    """
    Consonantal similarity in [0,1] using Levenshtein, but edits that
    only insert/delete a mater lectionis (א ה ו י) cost half.
    Handles SP<->MT plene/defective spelling differences gracefully.
    """
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    la, lb = len(a), len(b)
    prev = [0.0] * (lb + 1)
    for j in range(1, lb + 1):
        prev[j] = prev[j-1] + (0.5 if b[j-1] in MATRES else 1.0)
    for i in range(1, la + 1):
        cur = [0.0] * (lb + 1)
        cur[0] = prev[0] + (0.5 if a[i-1] in MATRES else 1.0)
        for j in range(1, lb + 1):
            sub = prev[j-1] + (0.0 if a[i-1] == b[j-1] else 1.0)
            dele = prev[j] + (0.5 if a[i-1] in MATRES else 1.0)
            ins = cur[j-1] + (0.5 if b[j-1] in MATRES else 1.0)
            cur[j] = min(sub, dele, ins)
        prev = cur
    dist = prev[lb]
    return max(0.0, 1.0 - dist / max(la, lb))


def align_words(mt_words_data, sp_words_data, sim_thresh=0.5):
    """
    Optimal global alignment (Needleman-Wunsch) of MT and SP word lists
    by consonantal similarity. Tolerates matres lectionis differences.
    Returns list of (mt_idx_or_None, sp_idx_or_None) pairs.
    Pairs whose similarity is below `sim_thresh` are split into separate
    MT-only / SP-only entries (they are not genuine cognates).
    """
    mt_cons = [normalize_cons(w['cons_utf8']) for w in mt_words_data]
    sp_cons = [normalize_cons(w['cons_utf8']) for w in sp_words_data]
    n, m = len(mt_cons), len(sp_cons)
    GAP = -0.6

    if n == 0:
        return [(None, j) for j in range(m)]
    if m == 0:
        return [(i, None) for i in range(n)]

    # Precompute similarity matrix
    sim = [[word_sim(mt_cons[i], sp_cons[j]) for j in range(m)] for i in range(n)]

    dp = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0] = dp[i-1][0] + GAP
    for j in range(1, m + 1):
        dp[0][j] = dp[0][j-1] + GAP
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            diag = dp[i-1][j-1] + (sim[i-1][j-1] * 2 - 1)  # in [-1, 1]
            up = dp[i-1][j] + GAP
            left = dp[i][j-1] + GAP
            dp[i][j] = max(diag, up, left)

    # Traceback
    i, j = n, m
    alignment = []
    while i > 0 and j > 0:
        diag = dp[i-1][j-1] + (sim[i-1][j-1] * 2 - 1)
        if abs(dp[i][j] - diag) < 1e-9:
            alignment.append((i-1, j-1)); i -= 1; j -= 1
        elif abs(dp[i][j] - (dp[i-1][j] + GAP)) < 1e-9:
            alignment.append((i-1, None)); i -= 1
        else:
            alignment.append((None, j-1)); j -= 1
    while i > 0:
        alignment.append((i-1, None)); i -= 1
    while j > 0:
        alignment.append((None, j-1)); j -= 1
    alignment.reverse()

    # Split low-similarity "substitutions" into separate entries
    result = []
    for mi, si in alignment:
        if mi is not None and si is not None and sim[mi][si] < sim_thresh:
            result.append((mi, None))
            result.append((None, si))
        else:
            result.append((mi, si))
    return result


# ============================================================
# MAIN PROCESSING
# ============================================================
def process_book(book_name, mt_api, sp_api):
    """Process an entire book."""
    mt_F = mt_api.F; mt_T = mt_api.T; mt_L = mt_api.L
    sp_F = sp_api.F; sp_T = sp_api.T; sp_L = sp_api.L

    book_data = {}
    stats = {'verses': 0, 'words_total': 0, 'words_aligned': 0,
             'words_exact': 0, 'words_fuzzy': 0,
             'words_mt_only': 0, 'words_sp_only': 0}

    chapter = 1
    while True:
        verse = 1
        chapter_data = {}
        has_verses = False

        while True:
            mt_v = mt_T.nodeFromSection((book_name, chapter, verse))
            sp_v = sp_T.nodeFromSection((book_name, chapter, verse))

            if mt_v is None and sp_v is None:
                break

            has_verses = True
            stats['verses'] += 1

            mt_words_raw = mt_L.d(mt_v, otype='word') if mt_v else []
            sp_words_raw = sp_L.d(sp_v, otype='word') if sp_v else []

            # Build MT word list. For ketiv forms that carry no vowels
            # (vocalization lives in the qere), use qere_utf8 as the
            # vocalized source while keeping ketiv consonants for alignment.
            mt_wd = []
            for w in mt_words_raw:
                cons = mt_F.g_cons_utf8.v(w)
                if not cons:
                    continue
                gw = mt_F.g_word_utf8.v(w) or ''
                if not has_niqqud(gw):
                    q = mt_F.qere_utf8.v(w)
                    if q and has_niqqud(q):
                        gw = q
                mt_wd.append({'g_word': gw,
                              'cons_utf8': cons,
                              'cons': mt_F.g_cons.v(w) or '',
                              'vt': feat(mt_F, 'vt', w),
                              'vs': feat(mt_F, 'vs', w),
                              'ps': feat(mt_F, 'ps', w),
                              'nu': feat(mt_F, 'nu', w)})

            sp_wd = [{'cons_utf8': sp_F.g_cons_utf8.v(w) or '',
                       'cons': sp_F.g_cons.v(w) or '',
                       'pos': sp_F.sp.v(w) or '',
                       'gloss': sp_F.gloss.v(w) or '',
                       'vt': feat(sp_F, 'vt', w),
                       'vs': feat(sp_F, 'vs', w),
                       'ps': feat(sp_F, 'ps', w),
                       'nu': feat(sp_F, 'nu', w)}
                      for w in sp_words_raw if sp_F.g_cons_utf8.v(w)]

            pairs = align_words(mt_wd, sp_wd)

            verse_words = []
            for mi, si in pairs:
                stats['words_total'] += 1

                if mi is not None and si is not None:
                    stats['words_aligned'] += 1
                    units = parse_word(mt_wd[mi]['g_word'])
                    sam_units = apply_samaritan_rules(
                        units, sp_wd[si].get('pos', ''),
                        vt=mt_wd[mi].get('vt') or sp_wd[si].get('vt', ''),
                        vs=mt_wd[mi].get('vs') or sp_wd[si].get('vs', ''))
                    sam_reading = rebuild(sam_units)

                    mt_n = normalize_cons(mt_wd[mi]['cons_utf8'])
                    sp_n = normalize_cons(sp_wd[si]['cons_utf8'])
                    is_exact = (mt_n == sp_n)
                    score = 1.0 if is_exact else round(word_sim(mt_n, sp_n), 3)
                    if is_exact:
                        stats['words_exact'] += 1
                    else:
                        stats['words_fuzzy'] += 1
                    verse_words.append({
                        'sam_reading': sam_reading,
                        'mt': mt_wd[mi]['g_word'],
                        'sp_cons': sp_wd[si]['cons_utf8'],
                        'pos': sp_wd[si]['pos'],
                        'gloss': sp_wd[si]['gloss'],
                        'vt': mt_wd[mi].get('vt') or sp_wd[si].get('vt', ''),
                        'vs': mt_wd[mi].get('vs') or sp_wd[si].get('vs', ''),
                        'ps': mt_wd[mi].get('ps') or sp_wd[si].get('ps', ''),
                        'nu': mt_wd[mi].get('nu') or sp_wd[si].get('nu', ''),
                        'aligned': is_exact,
                        'match': 'exact' if is_exact else 'fuzzy',
                        'sim': score,
                    })
                elif mi is not None:
                    stats['words_mt_only'] += 1
                    units = parse_word(mt_wd[mi]['g_word'])
                    sam_units = apply_samaritan_rules(
                        units,
                        vt=mt_wd[mi].get('vt', ''),
                        vs=mt_wd[mi].get('vs', ''))
                    verse_words.append({
                        'sam_reading': rebuild(sam_units),
                        'mt': mt_wd[mi]['g_word'],
                        'sp_cons': '',
                        'pos': '', 'gloss': '',
                        'vt': mt_wd[mi].get('vt', ''),
                        'vs': mt_wd[mi].get('vs', ''),
                        'ps': mt_wd[mi].get('ps', ''),
                        'nu': mt_wd[mi].get('nu', ''),
                        'aligned': False,
                        'match': 'mt_only',
                        'sim': 0.0,
                    })
                else:
                    stats['words_sp_only'] += 1
                    verse_words.append({
                        'sam_reading': sp_wd[si]['cons_utf8'],
                        'mt': '',
                        'sp_cons': sp_wd[si]['cons_utf8'],
                        'pos': sp_wd[si]['pos'],
                        'gloss': sp_wd[si]['gloss'],
                        'vt': sp_wd[si].get('vt', ''),
                        'vs': sp_wd[si].get('vs', ''),
                        'ps': sp_wd[si].get('ps', ''),
                        'nu': sp_wd[si].get('nu', ''),
                        'aligned': False,
                        'match': 'sp_only',
                        'sim': 0.0,
                    })

            chapter_data[str(verse)] = {
                'sam_reading': ' '.join(w['sam_reading'] for w in verse_words),
                'mt_vocalized': ' '.join(w['mt'] for w in verse_words if w['mt']),
                'sp_consonantal': ' '.join(w['sp_cons'] for w in verse_words if w['sp_cons']),
                'words': verse_words,
            }

            verse += 1

        if not has_verses:
            break

        book_data[str(chapter)] = chapter_data
        chapter += 1

    return book_data, stats


PENTATEUCH = ['Genesis', 'Exodus', 'Leviticus', 'Numbers', 'Deuteronomy']

RULES_DOC = [
    'R1: Diptongo -ayim -> -em (Yod preservada como mater lectionis)',
    'R1b: Plural masculino -im -> -em (chirik->tsere)',
    'R1c: Sufijo 2ms -kha -> -ak',
    'R1d: Sufijo 3ms plural -ayw -> -u (vav shuruq)',
    'R2: Tsere antes de Alef muda -> Qamats (ej. Bereshit)',
    'R3: Hataf en guturales -> vocal plena',
    'R4: Sheva inicial -> qamats',
    'R5: Cholam -> qubuts/shuruq (excepciones: כל y participio Qal -> qamats/å)',
    'R6: Sheva final eliminado (excepto monosilabos)',
    'R7: Sheva medial tras vocal corta -> silencio',
    'R7b: Sheva medial mobile -> chirik (ej. hayetah)',
    'R8: Vav conjuncion siempre recibe patach/qamats (nunca desnuda)',
    'R9: Segol final -> patach',
]


def main():
    parser = argparse.ArgumentParser(description='Motor de Lectura Samaritana')
    parser.add_argument('--book', default='Genesis',
                        help="Nombre del libro, o 'all' para toda la Tora")
    parser.add_argument('--output', default=None, help='Archivo de salida JSON')
    args = parser.parse_args()

    if args.book.lower() == 'all':
        books = PENTATEUCH
    else:
        books = [args.book]

    t0 = time.time()
    print(f"Motor de Lectura Samaritana v6")
    print(f"Procesando: {', '.join(books)}")
    print()

    print("Cargando BHSA (hebreo vocalizado)...")
    from tf.app import use
    A_mt = use('etcbc/bhsa', silent='deep')

    print("Cargando SP (pentateuco samaritano)...")
    A_sp = use('dt-ucph/sp', silent='deep')

    grand = {'verses': 0, 'words_total': 0, 'words_aligned': 0,
             'words_exact': 0, 'words_fuzzy': 0,
             'words_mt_only': 0, 'words_sp_only': 0}

    for book in books:
        print(f"\nProcesando {book}...")
        bt = time.time()
        book_data, stats = process_book(book, A_mt.api, A_sp.api)
        for k in grand:
            grand[k] += stats.get(k, 0)

        out_path = args.output if (args.output and len(books) == 1) \
            else f'{book.lower()}_lectura_samaritana.json'
        result = {
            'book': book,
            'description': f'Lectura samaritana del {book} en hebreo cuadrado niqqudizado',
            'engine': 'Motor Samaritano v6 (Ben-Hayyim rules + NW aligner)',
            'rules': RULES_DOC,
            'stats': stats,
            'chapters': book_data,
        }
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        tot = max(1, stats['words_total'])
        print(f"  {book}: {stats['verses']} vers, {stats['words_total']} pal, "
              f"empar {stats['words_aligned']/tot*100:.1f}% "
              f"(exact {stats['words_exact']/tot*100:.1f}% + difuso {stats['words_fuzzy']/tot*100:.1f}%) "
              f"-> {out_path}  [{time.time()-bt:.1f}s]")

    if len(books) > 1:
        gt = max(1, grand['words_total'])
        print(f"\n{'='*70}")
        print("TOTAL PENTATEUCO")
        print(f"{'='*70}")
        print(f"  Versiculos:       {grand['verses']}")
        print(f"  Palabras totales: {grand['words_total']}")
        print(f"  Emparejadas:      {grand['words_aligned']} ({grand['words_aligned']/gt*100:.1f}%)")
        print(f"    - exactas:      {grand['words_exact']} ({grand['words_exact']/gt*100:.1f}%)")
        print(f"    - difusas:      {grand['words_fuzzy']} ({grand['words_fuzzy']/gt*100:.1f}%)")
        print(f"  Solo MT:          {grand['words_mt_only']}")
        print(f"  Solo SP:          {grand['words_sp_only']}")
        print(f"  Tiempo total:     {time.time()-t0:.1f}s")
        return

    stats = grand
    book_data = result['chapters']
    out_path = out_path  # last
    elapsed = time.time() - t0
    print(f"Estadisticas:")
    print(f"  Capitulos:        {len(book_data)}")
    print(f"  Versiculos:       {stats['verses']}")
    tot = max(1, stats['words_total'])
    print(f"  Palabras totales: {stats['words_total']}")
    print(f"  Emparejadas:      {stats['words_aligned']} ({stats['words_aligned']/tot*100:.1f}%)")
    print(f"    - exactas:      {stats['words_exact']} ({stats['words_exact']/tot*100:.1f}%)")
    print(f"    - difusas:      {stats['words_fuzzy']} ({stats['words_fuzzy']/tot*100:.1f}%)")
    print(f"  Solo MT:          {stats['words_mt_only']}")
    print(f"  Solo SP:          {stats['words_sp_only']}")
    print(f"  Tiempo:           {elapsed:.1f}s")
    print(f"\nGuardado: {out_path}")

    # Show samples
    print(f"\n{'='*70}")
    print("MUESTRAS")
    print(f"{'='*70}")
    samples = [('1','1'), ('1','2'), ('1','6'), ('1','10'), ('1','27'), ('22','2'), ('49','10')]
    for ch, vs in samples:
        if ch in book_data and vs in book_data[ch]:
            d = book_data[ch][vs]
            print(f"\n  Gen {ch}:{vs}")
            print(f"    MT:  {d['mt_vocalized'][:90]}")
            print(f"    SAM: {d['sam_reading'][:90]}")

    # Validation checks
    print(f"\n{'='*70}")
    print("VALIDACION")
    print(f"{'='*70}")
    for ch_n, vs_n in [('1','1'), ('1','2'), ('1','4')]:
        vd = book_data.get(ch_n, {}).get(vs_n, {})
        if not vd:
            continue
        for w in vd.get('words', []):
            sc = w.get('sp_cons', '')
            sr = w.get('sam_reading', '')
            mt = w.get('mt', '')
            # Prep bet with sheva
            if sc == 'ב' and 'בְּ' in mt:
                print(f"  R4 (prep): mt={mt} -> sam={sr}  (debe ser בָּ)")
            # Elohim plural
            if sc == 'אלהים':
                print(f"  R1b (plural): mt={mt} -> sam={sr}  (debe tener tsere)")
            # Shamayim
            if 'שׁמ' in sc and len(sc) > 3:
                print(f"  R1 (dipt): mt={mt} -> sam={sr}  (yod preservada)")
            # Vav conjunction
            if sc == 'ו':
                has_dag = DAGESH in sr
                print(f"  R8 (vav): mt={mt} -> sam={sr}  dagesh_residual={has_dag}")


if __name__ == '__main__':
    main()
