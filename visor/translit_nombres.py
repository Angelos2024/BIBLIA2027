# -*- coding: utf-8 -*-
"""
Motor de transliteración de nombres propios hebreos -> latín.
Dos capas (Manual de Transliteración de Nombres Hebreos):

  1) academica : estricta / reversible (SBL-like). Conserva guturales (ʾ/ʿ),
     He final muda (h), begadkefat (b/v, k/ḵ, p/f, t/ṯ), sibilantes (š/ś/ṣ),
     duplicación por dagesh forte, vocales largas con macrón (ā ē ī ō ū),
     matres lectionis. SIN tilde de acento (usa cantidad vocálica).

  2) espanol : adaptación fonética para interfaz/búsqueda. Het y Kaf-rafe -> J,
     guturales mudas omitidas, He final muda omitida, Tzade -> Tz, Shin -> Sh,
     Sin -> S, consonantes geminadas normalizadas a simple, y TILDE de acento
     tónico colocada según:
        - acento tónico = posición del te'am Unicode (U+0591..U+05AE) sobre la
          consonante que inicia la sílaba tónica; si no hay te'am, regla
          estructural (segolado -> llana; resto -> aguda).
        - inyección RAE: aguda + termina en vocal/n/s -> tilde; llana + termina
          en otra consonante -> tilde; resto -> sin tilde gráfica.

NO altera datos crudos: recibe la he_form y devuelve cadenas nuevas.
"""

# ── rangos / puntos ────────────────────────────────────────────────────────
TEAMIM_LO, TEAMIM_HI = 0x0591, 0x05AE          # acentos de cantilación (tonicidad)
METEG, RAFE = 0x05BD, 0x05BF
PATAH, QAMATS, SEGOL, TSERE = 0x05B7, 0x05B8, 0x05B6, 0x05B5
HIRIQ, HOLAM, HOLAM_HASER, QUBUTS = 0x05B4, 0x05B9, 0x05BA, 0x05BB
SHEVA = 0x05B0
HATAF_SEGOL, HATAF_PATAH, HATAF_QAMATS = 0x05B1, 0x05B2, 0x05B3
QAMATS_QATAN = 0x05C7
DAGESH, SHIN_DOT, SIN_DOT = 0x05BC, 0x05C1, 0x05C2

FULL_VOWELS = {PATAH, QAMATS, SEGOL, TSERE, HIRIQ, HOLAM, HOLAM_HASER,
               QUBUTS, QAMATS_QATAN}
REDUCED_VOWELS = {SHEVA, HATAF_SEGOL, HATAF_PATAH, HATAF_QAMATS}
ALL_VOWELS = FULL_VOWELS | REDUCED_VOWELS

GUTTURALS = set('אהחע')
NO_GEMINATE = set('אהחער')  # guturales + resh no geminan
BEGADKEFAT = set(['ב', 'ג', 'ד', 'כ', 'ך', 'פ', 'ף', 'ת'])
FINALS = {'ך': 'כ', 'ם': 'מ', 'ן': 'נ', 'ף': 'פ', 'ץ': 'צ'}

VOWEL_ACUTE = {'a': 'á', 'e': 'é', 'i': 'í', 'o': 'ó', 'u': 'ú'}


def _strip_for_letters(s):
    """Quita te'amim, meteg, rafe y puntuación; conserva consonantes, niqqud,
    dagesh y puntos shin/sin."""
    out = []
    for ch in s:
        o = ord(ch)
        if TEAMIM_LO <= o <= TEAMIM_HI:      # cantilación
            continue
        if o in (METEG, RAFE):
            continue
        if o in (0x05BE, 0x05C0, 0x05C3, 0x05C4, 0x05C5, 0x05C6, 0x05F3, 0x05F4):
            continue
        if ch in (' ', '\u00A0'):
            continue
        out.append(ch)
    return ''.join(out)


def _has_teamim(s):
    return any(TEAMIM_LO <= ord(ch) <= TEAMIM_HI for ch in s)


def _parse_units(s):
    """Lista de unidades {c, marks:set, teamim:bool} en orden."""
    units = []
    cur = None
    for ch in s:
        o = ord(ch)
        if 0x05D0 <= o <= 0x05EA:            # consonante base
            if cur:
                units.append(cur)
            cur = {'c': ch, 'marks': [], 'teamim': False}
        elif cur is not None:
            if o in ALL_VOWELS or o in (DAGESH, SHIN_DOT, SIN_DOT):
                cur['marks'].append(o)
            elif TEAMIM_LO <= o <= TEAMIM_HI:
                cur['teamim'] = True
    if cur:
        units.append(cur)
    return units


def _vowel_of(u):
    for m in u['marks']:
        if m in ALL_VOWELS:
            return m
    return None


def transliterar(he_form):
    """Devuelve dict con 'academica', 'espanol' y 'consonantes'."""
    if not he_form:
        return {'academica': '', 'espanol': '', 'consonantes': ''}

    teamim_present = _has_teamim(he_form)
    clean = _strip_for_letters(he_form)
    raw_units = _parse_units(clean)
    # te'amim sobre qué unidad (índice) — recalcular sobre original
    team_idx = None
    # mapear te'amim a unidades: recorrer original y contar consonantes
    ci = -1
    for ch in he_form:
        o = ord(ch)
        if 0x05D0 <= o <= 0x05EA:
            ci += 1
        elif TEAMIM_LO <= o <= TEAMIM_HI and ci >= 0:
            team_idx = ci   # último te'am gana (acento principal suele ser el tónico)

    n = len(raw_units)
    if n == 0:
        return {'academica': '', 'espanol': '', 'consonantes': ''}

    # ── resolución de matres lectionis (vav/yod) ──
    units = []
    for u in raw_units:
        units.append({'c': u['c'], 'v': _vowel_of(u),
                      'dag': DAGESH in u['marks'],
                      'shin': SHIN_DOT in u['marks'],
                      'sin': SIN_DOT in u['marks'],
                      'skip': False, 'long': False, 'mater_e': False})
    for i, u in enumerate(units):
        if u['c'] == 'ו' and not u['shin'] and not u['sin']:
            # holam male escrito sobre la vav (וֹ)
            if u['v'] in (HOLAM, HOLAM_HASER):
                if i > 0 and units[i-1]['v'] is None and not units[i-1]['skip']:
                    units[i-1]['v'] = HOLAM; units[i-1]['long'] = True; u['skip'] = True
                # si prev ya tiene vocal -> vav consonante con holam (se queda)
            # shuruq (solo dagesh, sin vocal)
            elif u['v'] is None and u['dag']:
                if i > 0 and units[i-1]['v'] is None and not units[i-1]['skip']:
                    units[i-1]['v'] = QUBUTS; units[i-1]['long'] = True
                    units[i-1]['_shuruq'] = True; u['skip'] = True
                else:
                    u['_standalone_u'] = True; u['dag'] = False
            # vav desnuda como mater de jólem previo (consonante+jólem+vav: יֹו, חֹו)
            elif u['v'] is None and not u['dag']:
                if i > 0 and not units[i-1]['skip'] and units[i-1]['v'] in (HOLAM, HOLAM_HASER):
                    units[i-1]['long'] = True; u['skip'] = True
                # si no, vav consonante (p.ej. עֵשָׂו -> Esav) se queda
        elif u['c'] == 'י' and u['v'] is None and not u['dag'] and not u['shin'] and not u['sin']:
            if i > 0 and not units[i-1]['skip']:
                pv = units[i-1]['v']
                if pv == HIRIQ:
                    units[i-1]['long'] = True; u['skip'] = True
                elif pv in (TSERE, SEGOL):
                    units[i-1]['long'] = True; units[i-1]['mater_e'] = True; u['skip'] = True
                # patah/qamats + yod -> diptongo: yod se queda como semivocal

    live = [u for u in units if not u['skip']]

    # ── pátaj furtiva: gutural final (ח/ע, o ה con mappiq) con pátaj tras
    #    vocal -> se pronuncia ANTES de la consonante y no forma sílaba propia.
    if len(live) >= 2:
        last = live[-1]
        if last['c'] in ('ח', 'ע') and last['v'] == PATAH and not last['dag']:
            if live[-2]['v'] in FULL_VOWELS:
                last['furtive'] = True

    # ── sílabas (núcleos de vocal plena) ──
    full_pos = [k for k, u in enumerate(live)
                if u['v'] in FULL_VOWELS and not u.get('furtive')]
    total_syl = len(full_pos)

    # ── tonicidad ──
    stressed_syl = None
    if teamim_present and team_idx is not None:
        # mapear team_idx (índice de consonante en original) a 'live'
        # construir correspondencia: índice original consonante -> índice en units
        # raw_units está alineado con units (antes de skip). team_idx indexa raw_units.
        if 0 <= team_idx < len(units):
            # localizar en 'live' la primera vocal plena en/ tras esa unidad
            tgt = units[team_idx]
            if not tgt['skip']:
                try:
                    live_idx = live.index(tgt)
                except ValueError:
                    live_idx = 0
            else:
                live_idx = 0
            # primera vocal plena a partir de live_idx
            cand = [s for s, p in enumerate(full_pos) if p >= live_idx]
            stressed_syl = cand[0] if cand else (total_syl - 1 if total_syl else None)
    if stressed_syl is None and total_syl:
        # estructural: segolado -> llana
        # Patrón segolado clásico (Mélej, Séfer, Ná'ar, Yáfet, Yáred, Bóqer…):
        # dos vocales plenas en consonantes ADYACENTES (distancia 1), última
        # consonante muda (sin vocal o con sheva muda), y última vocal del
        # núcleo es segol o patah. La penúltima puede ser segol/tsere/patah/
        # qamats/holam/hiriq según el patrón (CéCeC, CáCaC, CēCeC, CāCeC, CōCeC).
        # En palabras sufijadas (זַרְעֲכֶם) las vocales NO son adyacentes,
        # así que la regla aguda por defecto se mantiene.
        seg = False
        if total_syl >= 2:
            last_v = live[full_pos[-1]]['v']
            prev_v = live[full_pos[-2]]['v']
            adyacentes = (full_pos[-1] - full_pos[-2]) == 1
            ultima_muda = (live[-1]['v'] in (None, SHEVA))
            seg_finals = (SEGOL, PATAH)
            seg_prevs = (SEGOL, TSERE, PATAH, QAMATS, HOLAM, HOLAM_HASER, HIRIQ)
            if (last_v in seg_finals and prev_v in seg_prevs
                    and adyacentes and ultima_muda):
                seg = True
        stressed_syl = (total_syl - 2) if seg else (total_syl - 1)

    # ── He locale / femenino -áh (qamats + he muda) ───────────────────────────
    #   · he_fem: qamats TÓNICO en he final (אֲדָמָה -> 'Adamáh).
    #   · he_locale: qamats ÁTONO de dirección "-ah" (מִצְרַיְמָה -> Mitzráymah).
    #     SOLO se activa cuando hay he muda real al final (trailing_mute).
    #     No se activa para cualquier consonante + qamats final (p. ej. ךָ del
    #     sufijo P2.M.SG en זַרְעֲךָ → debe ser Zar'ajá, no Zar'ajáh).
    he_locale = False
    he_fem = False
    qamats_at_surface_end = False
    if total_syl >= 1:
        last_full = live[full_pos[-1]]
        after = live[full_pos[-1] + 1:]
        trailing_mute = bool(after) and all(
            (u['c'] in ('ה', 'א') and u['v'] is None and not u['dag'])
            for u in after)
        qamats_at_surface_end = (
            last_full['v'] == QAMATS and last_full is live[-1])
        if last_full['v'] == QAMATS and (trailing_mute or qamats_at_surface_end):
            if live[-1]['c'] == 'ה' and live[-1]['v'] == QAMATS:
                he_fem = True
            elif trailing_mute and stressed_syl == total_syl - 1:
                # Femenino -áh tónico (Adamáh, 'Amoráh, Saráh…)
                he_fem = True
            elif trailing_mute:
                # Locativo con hei muda real al final (Mitzráymah, Sedómah…).
                he_locale = True
                last_full['he_locale'] = True
                if not teamim_present and stressed_syl == total_syl - 1 and total_syl >= 2:
                    stressed_syl = total_syl - 2
            # else: qamats sobre cualquier otra consonante final → sin marca de h.

    # ── render ──
    def cons_acad(u, geminate, hard):
        c = u['c']; base = FINALS.get(c, c)
        m = {'א': 'ʾ', 'ב': 'b' if hard else 'v', 'ג': 'g', 'ד': 'd', 'ה': 'h',
             'ו': 'w', 'ז': 'z', 'ח': 'ḥ', 'ט': 'ṭ', 'י': 'y',
             'כ': 'k' if hard else 'ḵ', 'ל': 'l', 'מ': 'm', 'נ': 'n', 'ס': 's',
             'ע': 'ʿ', 'פ': 'p' if hard else 'f', 'צ': 'ṣ', 'ק': 'q', 'ר': 'r',
             'ש': 'ś' if u['sin'] else 'š', 'ת': 't' if hard else 'ṯ'}
        r = m.get(base, base)
        if geminate:
            r = r + r
        return r

    def cons_esp(u, geminate, hard):
        # Español: NUNCA gemina. Álef/Ayin mudas -> apóstrofo ' como marca
        # glotal (estilo personal: 'Elohim, Mejuya'el, 'Avraham).
        c = u['c']; base = FINALS.get(c, c)
        m = {'א': "'", 'ב': 'b' if hard else 'v', 'ג': 'g', 'ד': 'd', 'ה': 'h',
             'ו': 'v', 'ז': 'z', 'ח': 'j', 'ט': 't', 'י': 'y',
             'כ': 'k' if hard else 'j', 'ל': 'l', 'מ': 'm', 'נ': 'n', 'ס': 's',
             'ע': "'", 'פ': 'p' if hard else 'f', 'צ': 'tz', 'ק': 'q', 'ר': 'r',
             'ש': 's' if u['sin'] else 'sh', 'ת': 't'}
        return m.get(base, base)

    def vow_acad(u):
        v = u['v']
        if v is None:
            return ''
        if v == PATAH: return 'a'
        if v == QAMATS: return 'ā'
        if v == QAMATS_QATAN: return 'o'
        if v == SEGOL: return 'ē' if u['long'] else 'e'
        if v == TSERE: return 'ē'
        if v == HIRIQ: return 'ī' if u['long'] else 'i'
        if v in (HOLAM, HOLAM_HASER): return 'ō'
        if v == QUBUTS: return 'ū' if u.get('_shuruq') or u['long'] else 'u'
        if v == HATAF_SEGOL: return 'ĕ'
        if v == HATAF_PATAH: return 'ă'
        if v == HATAF_QAMATS: return 'ŏ'
        if v == SHEVA: return 'ə'   # se decide vocal/mudo abajo
        return ''

    def vow_esp(u):
        v = u['v']
        if v is None: return ''
        if v in (PATAH, QAMATS, HATAF_PATAH): return 'a'
        if v in (QAMATS_QATAN, HATAF_QAMATS): return 'o'
        if v in (SEGOL, TSERE, HATAF_SEGOL): return 'e'
        if v == HIRIQ: return 'i'
        if v in (HOLAM, HOLAM_HASER): return 'o'
        if v == QUBUTS: return 'u'
        if v == SHEVA: return 'e'   # si vocal
        return ''

    # sheva vocal/mudo
    def sheva_is_vocal(idx):
        u = live[idx]
        if u['v'] != SHEVA:
            return False
        if idx == 0:
            return True
        if u['dag'] and u['c'] not in NO_GEMINATE:  # dagesh forte
            return True
        prev = live[idx-1]
        if prev['v'] == SHEVA:    # 2ª de dos shevás
            return True
        if prev['v'] is None:     # tras consonante sin vocal (sílaba cerrada)
            return True
        return False

    # geminación (dagesh forte) por unidad
    def is_forte(idx):
        u = live[idx]
        if not u['dag'] or u['c'] in NO_GEMINATE:
            return False
        if idx == 0:
            return False
        prev = live[idx-1]
        # forte si la consonante previa cerró sílaba abierta (tenía vocal)
        if prev['v'] in FULL_VOWELS:
            return True
        if prev['v'] == SHEVA and sheva_is_vocal(idx-1):
            return True
        return False

    acad = []
    esp_parts = []          # (texto, nucleo_char_or_None)
    nucleus_syl_positions = []   # índice (en esp_parts) del núcleo de cada vocal plena

    for idx, u in enumerate(live):
        forte = is_forte(idx)
        base = FINALS.get(u['c'], u['c'])
        # begadkefat: oclusiva si dagesh, geminada, o inicial de palabra
        hard = u['dag'] or forte or (idx == 0 and base in BEGADKEFAT)
        # academica
        a_c = cons_acad(u, forte, hard)
        a_v = vow_acad(u)
        if u['v'] == SHEVA and not sheva_is_vocal(idx):
            a_v = ''
        if u.get('mater_e'):
            a_v = 'ê'
        # espanol
        e_c = cons_esp(u, forte, hard)
        if u['v'] == SHEVA and not sheva_is_vocal(idx):
            e_v = ''
        else:
            e_v = vow_esp(u)
        # shuruq inicial standalone
        if u.get('_standalone_u'):
            a_c = ''; a_v = 'ū'; e_c = ''; e_v = 'u'
        # diptongo patah/qamats + yod semivocal (yod sin vocal)
        if u['c'] == 'י' and u['v'] is None and not u.get('_standalone_u'):
            a_c = 'y'; a_v = ''; e_c = 'i'; e_v = ''
        # pátaj furtiva: vocal antes de la consonante gutural
        if u.get('furtive'):
            acad.append(a_v + a_c)
            esp_parts.append([e_v + e_c, None])
            continue
        acad.append(a_c + a_v)
        text = e_c + e_v
        nucleo_idx = len(e_c) if (u['v'] in FULL_VOWELS and e_v) else None
        esp_parts.append([text, nucleo_idx])
        if u['v'] in FULL_VOWELS and not u.get('furtive'):
            nucleus_syl_positions.append(len(esp_parts) - 1)

    academica = ''.join(acad)

    # ── terminación fonética (para regla RAE), basada en unidades ──
    def mute_final_he(u, prev_has_vowel):
        return (u['c'] == 'ה' and not u['dag'] and u['v'] is None and prev_has_vowel)

    ends_vns = False
    lu = live[-1]
    prev_v = live[-2]['v'] if len(live) >= 2 else None
    quiescent_aleph = (lu['c'] == 'א' and lu['v'] is None and prev_v is not None)
    if mute_final_he(lu, prev_v is not None) or quiescent_aleph:
        ends_vns = True                      # termina en vocal (he/álef muda)
    elif lu.get('furtive'):
        ends_vns = False                     # termina en gutural (j) -> otra consonante
    elif lu['v'] in FULL_VOWELS:
        ends_vns = True                      # termina en vocal
    else:
        # consonante final (sin vocal o con shevá/vocal reducida muda)
        base = FINALS.get(lu['c'], lu['c'])
        if base == 'נ':
            ends_vns = True                  # n
        elif base == 'ס' or (base == 'ש' and lu['sin']):
            ends_vns = True                  # s
        else:
            ends_vns = False

    esp = ''.join(p[0] for p in esp_parts)

    # Locativo -ah: para tilde RAE cierra en consonante (…mah), no en vocal átona.
    if he_locale:
        ends_vns = False

    # Pataj furtivo final (נֹחַ -> Nóaj):
    furtive_final = (
        len(live) >= 2
        and live[-1].get('furtive')
        and live[-2]['v'] in FULL_VOWELS
        and total_syl == 1
    )

    if total_syl and stressed_syl is not None and not he_fem:
        from_end = total_syl - 1 - stressed_syl
        do_accent = False
        if furtive_final:
            do_accent = True
            stressed_syl = 0
            from_end = total_syl - 1
        elif from_end >= 2:
            do_accent = True
        elif from_end == 0:
            do_accent = ends_vns
        elif from_end == 1:
            do_accent = not ends_vns
        if do_accent:
            part_idx = nucleus_syl_positions[stressed_syl]
            text, nuc = esp_parts[part_idx]
            if nuc is not None and nuc < len(text):
                v = text[nuc]
                if v in VOWEL_ACUTE:
                    esp_parts[part_idx][0] = text[:nuc] + VOWEL_ACUTE[v] + text[nuc+1:]
            esp = ''.join(p[0] for p in esp_parts)

    # Femenino -áh tónico (Adamáh, Saráh…): tilde en la vocal final.
    if he_fem and nucleus_syl_positions:
        part_idx = nucleus_syl_positions[-1]
        text, nuc = esp_parts[part_idx]
        if nuc is not None and nuc < len(text):
            v = text[nuc]
            if v in VOWEL_ACUTE:
                esp_parts[part_idx][0] = text[:nuc] + VOWEL_ACUTE[v] + text[nuc+1:]
        esp = ''.join(p[0] for p in esp_parts)

    # He direccional omitida en la forma (סְדֹמָ + sufijo ה -> Sedómah).
    if he_locale and qamats_at_surface_end and not esp.endswith('h'):
        esp = esp + 'h'

    # capitalizar (nombres propios)
    def cap(s):
        for i, ch in enumerate(s):
            if ch.isalpha():
                return s[:i] + s[i].upper() + s[i+1:]
        return s

    # limpieza de apóstrofos: colapsar dobles y quitar el final colgante
    while "''" in esp:
        esp = esp.replace("''", "'")
    if esp.endswith("'"):
        esp = esp[:-1]

    consonantes = ''.join(FINALS.get(u['c'], u['c']) for u in raw_units)
    return {'academica': cap(academica), 'espanol': cap(esp), 'consonantes': consonantes}


MAQAF_CHARS = ('\u05BE', '-', '־')


def has_trailing_maqaf(he_form: str) -> bool:
    s = (he_form or '').rstrip()
    return bool(s) and s[-1] in MAQAF_CHARS


def has_leading_maqaf(he_form: str) -> bool:
    s = (he_form or '').lstrip()
    return bool(s) and s[0] in MAQAF_CHARS


def strip_maqaf_edges(he_form: str) -> str:
    s = (he_form or '').strip()
    while s and s[0] in MAQAF_CHARS:
        s = s[1:].lstrip()
    while s and s[-1] in MAQAF_CHARS:
        s = s[:-1].rstrip()
    return s


def fused_he_form(partes_he: list[str]) -> str:
    """Une eslabones maqaf en una sola cadena hebrea (sin signos ־)."""
    return ''.join(strip_maqaf_edges(h) for h in partes_he)


def _consk(s: str) -> str:
    return ''.join(c for c in (s or '') if 0x05D0 <= ord(c) <= 0x05EA)


# Grafía española canónica de topónimos partidos por maqaf (esqueleto fusionado).
# Alineado con glosas personales (p. ej. H1008 -> «Beit-») y segunda parte en minúscula.
MAQAF_ESP_CANON: dict[str, list[str]] = {
    'ביתאל': ['Beit-', 'el'],
}

# NPROP sin Strong en datos: esqueleto fusionado -> Strong.
NPROP_INFER_STRONGS: dict[str, str] = {
    'מצרימה': 'H4714',
    'מצרים': 'H4714',
}

# GENT sin Strong (o Strong de topónimo confundido): esqueleto -> Strong gentilicio.
GENT_INFER_STRONGS: dict[str, str] = {
    'מצרים': 'H4713',
}

# Grafía española preferida para locativos -áh (he direccional).
LOCATIV_ESP_CANON: dict[str, str] = {
    'מצרימה': 'Mitzráymah',
}


def _sufijo_es_he_direccional(hw: dict) -> bool:
    """True si prs_suffix es ה locativa (SUF / SUF.DIR.HE), p. ej. MCRYM/H."""
    suf = hw.get('prs_suffix') or {}
    if not suf:
        return False
    if _consk(suf.get('he_form') or '') != 'ה':
        return False
    morph = (suf.get('he_morph') or '')
    return morph == 'SUF' or morph.startswith('SUF.')


def he_fusionado_hw(hw: dict) -> str:
    """Raíz + sufijo pronominal/locativo para lectura completa."""
    stem = hw.get('he_form') or ''
    suf = (hw.get('prs_suffix') or {}).get('he_form') or ''
    return stem + suf


def inferir_strongs_nprop(hw: dict) -> str:
    st = (hw.get('strongs') or '').strip()
    morph = hw.get('he_morph') or ''
    if morph.startswith('GENT.'):
        sk = _consk(hw.get('he_form') or '')
        if sk in GENT_INFER_STRONGS:
            return GENT_INFER_STRONGS[sk]
        return st
    if st:
        return st
    for key in (he_fusionado_hw(hw), hw.get('he_form') or ''):
        sk = _consk(key)
        if sk in NPROP_INFER_STRONGS:
            return NPROP_INFER_STRONGS[sk]
    return ''


def es_nprop_o_gent(morph: str) -> bool:
    """True si el token es nombre propio (persona/lugar) o gentilicio."""
    m = morph or ''
    return m == 'NPROP' or m.startswith('GENT.')


def transliterar_locativo_nprop(hw: dict) -> dict | None:
    """Translitera NPROP con -áh direccional (מִצְרַיְמָה, סְדֹמָה + sufijo ה…)."""
    if (hw.get('he_morph') or '') != 'NPROP':
        return None
    if not _sufijo_es_he_direccional(hw):
        return None
    fused = he_fusionado_hw(hw)
    tr = transliterar(fused)
    esp = tr['espanol']
    acad = tr['academica']
    canon = LOCATIV_ESP_CANON.get(_consk(fused))
    if canon:
        esp = canon
    if not esp:
        return None
    return {'academica': acad, 'espanol': esp, 'consonantes': tr.get('consonantes') or ''}


def transliterar_maqaf_partes(partes_he: list[str]) -> list[dict]:
    """Translitera cada eslabón de un nombre propio unido por maqaf.

    Cuando la regla de maqaf del visor deja toda la glosa en el
    primer token, cada eslabón recibe su propia capa ``espanol`` / ``academica``.
    Los eslabones enlazantes llevan guion final (Beit-, Beer-, …). Si el nombre
    tiene entrada en ``MAQAF_ESP_CANON``, se usa esa grafía (p. ej. Beit- + el).
    """
    n = len(partes_he)
    out: list[dict] = []
    for i, hf in enumerate(partes_he):
        tr = transliterar(hf)
        esp = tr['espanol']
        acad = tr['academica']
        if i < n - 1 and has_trailing_maqaf(hf) and esp and not esp.endswith('-'):
            esp = esp + '-'
        out.append({
            'academica': acad,
            'espanol': esp,
            'consonantes': tr.get('consonantes') or '',
            'eslabon_enlace': i < n - 1,
        })
    fused = _consk(fused_he_form(partes_he))
    canon = MAQAF_ESP_CANON.get(fused)
    if canon and len(canon) == n:
        for item, esp_canon in zip(out, canon):
            item['espanol'] = esp_canon
    return out


if __name__ == '__main__':
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    tests = ['צִלָּה', 'לֶמֶךְ', 'קַיִן', 'חֲנוֹךְ', 'הֶבֶל', 'שְׁלֹמֹה', 'שָׂרָה',
             'יַעֲקֹב', 'יוֹסֵף', 'אַבְרָהָם', 'יִצְחָק', 'יִשְׂרָאֵל', 'יְהוּדָה',
             'דָּוִד', 'נֹחַ', 'פַּרְעֹה', 'עֵדֶן', 'רִבְקָה', 'רָחֵל', 'שֵׁת',
             'אֱנוֹשׁ', 'תּוּבַל', 'נַעֲמָה', 'עִירָד', 'מְתוּשָׁאֵל', 'בִּנְיָמִין',
             'סְדֹ֧מָ', 'גְרָ֖רָ', 'סְפָ֖רָ']
    for t in tests:
        r = transliterar(t)
        print(f"{t}  ->  acad={r['academica']!r}  esp={r['espanol']!r}")
