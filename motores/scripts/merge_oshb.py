"""
merge_oshb.py — Enriquece genesis_full.json con datos del interlinear-snapshot.

Fuente principal : IdiomaORIGEN/interlinear-snapshot/chapters/genesis/<cap>.json
  Contiene por cada morfema hebreo:
    hebrew     — forma con niqqud
    morphology — etiqueta OSHB  (ej. VERBO.QAL.PERF.P3.M.SG)
    spanish    — glosa española (incluyendo artículos: "los","la","y","en"…)
    greek_lxx  — palabra griega Unicode individual alineada al morfema
    lxx_tier   — confianza del alineamiento  ('hint','soft','auto')
    strongs    — número Strong

Estrategia de alineación (Opción C — Token-level consonant alignment)
───────────────────────────────────────────────────────────────────────
En lugar de exigir que el conteo de morphemas CATSS == snapshot, se alinea
ELEMENTO A ELEMENTO usando las consonantes hebreas como clave.

Para cada par CATSS:
  Para cada elemento (prefijo o stem):
    1. Extrae consonantes del elemento CATSS (desde su forma ASCII o unicode)
    2. Busca el primer segmento snapshot (a partir del puntero) cuyas consonantes
       coincidan (exactas, o CATSS contiene sufijo pronominal que amplía el snap)
    3. Si coincide → toma es, gr_word, morph, niqqud del snapshot
    4. Si no coincide → usa niqqud de OSHB, es/gr vacíos (nunca datos erróneos)

Ventajas sobre la estrategia anterior:
  - Antes: si el verso tenía 1 morfema de diferencia → 100% sin griego individual
  - Ahora: solo el token específico queda sin dato; el resto del verso es correcto
  - Cobertura esperada: del 14% al ~85-90% de words con griego por morfema

Correcciones sistemáticas post-merge (aplican a todos los libros)
─────────────────────────────────────────────────────────────────
 1. PREP.ART   — לַ/לָ/בַּ/בָּ/כַּ/כָּ detectados por patrón Unicode
 2. Morph corta — VqAJSM3 → VERBO.QAL.JUSS.P3.M.SG
 3. בֵּין+ἀνὰ μέσον → "entre"
 4. כִּי+ὅτι → "que"
 5. Vav vacío → "y"
 6. Normalización de mayúscula/puntuación
 7. Griego par-level → último stem cuando todos vacíos
13. Reglas de auditoría conservadora (Génesis): conjugación verbal A,
    desambiguación PREP E, marcador --- de omisión LXX B, fusión
    de duplicados adyacentes D. Solo añadiva al final, con marca
    es_source/gr_source en cada token afectado.

Salida: data/genesis_final.json
"""

import json
import re
import sys
from pathlib import Path

# ════════════════════════════════════════════════════════════════════════════
#  NORMALIZACIÓN DE MORFOLOGÍA (short OSHB codes → formato largo)
# ════════════════════════════════════════════════════════════════════════════

_VS = {'q':'QAL','Q':'QAL','N':'NIF','n':'NIF','P':'PIEL','p':'PIEL',
       'u':'PUAL','U':'PUAL','h':'HIF','H':'HIF','R':'HOF','r':'HOF',
       't':'HITP','T':'HITP','D':'QAL','s':'PIEL'}

_VM = {'P':'PERF','I':'IMPF','W':'WAYYIQT','m':'WAYYIQT',
       'J':'JUSS','j':'JUSS','C':'COH','c':'COH','A':'IMPV','a':'IMPV',
       'p':'INFC','f':'INFA','r':'PTCA','v':'PTCA','s':'PTCP'}

_VP = {'1':'P1','2':'P2','3':'P3'}
_VN = {'S':'SG','P':'PL','D':'DU'}
_VG = {'M':'M','F':'F','C':'COMMON','B':'BOTH'}
_VVOICE = {'A','P','M'}

def _expand_short_verb(m: str) -> str:
    """Expande VqAJSM3 → VERBO.QAL.JUSS.P3.M.SG (o formas similares)."""
    if len(m) < 3 or m[1] not in _VS:
        return m
    stem = _VS[m[1]]
    rest = m[2:]
    # Detecta si hay indicador de voz (A/P/M) antes del modo
    if len(rest) >= 2 and rest[0] in _VVOICE and rest[1] in _VM:
        mood = _VM[rest[1]]
        tail = rest[2:]
    elif rest and rest[0] in _VM:
        mood = _VM[rest[0]]
        tail = rest[1:]
    else:
        return m
    person = gender = number = ''
    for ch in tail:
        if ch in _VP and not person:   person = _VP[ch]
        elif ch in _VN and not number: number = _VN[ch]
        elif ch in _VG and not gender: gender = _VG[ch]
    parts = ['VERBO', stem, mood]
    if person: parts.append(person)
    if gender:  parts.append(gender)
    if number:  parts.append(number)
    return '.'.join(parts)


def normalize_morph(morph: str) -> str:
    """
    Si la etiqueta morfológica está en formato corto OSHB (sin puntos),
    la convierte al formato largo usado por el snapshot.
    Ejemplos:
      VqAJSM3 → VERBO.QAL.JUSS.P3.M.SG
      VqAmSM3 → VERBO.QAL.WAYYIQT.P3.M.SG
      VhImP3  → VERBO.HIF.IMPF.P3.M  (si aplica)
    """
    if not morph or '.' in morph:
        return morph          # ya está en formato largo o vacío
    if morph[0] == 'V':
        expanded = _expand_short_verb(morph)
        return expanded if expanded != morph else morph
    return morph

# ─── RUTAS ──────────────────────────────────────────────────────────────────
ANGELOS   = Path(r"C:\Users\pik_y\Documents\GitHub\Local-consults\estudio\angelos")
SNAP_DIR  = ANGELOS / "IdiomaORIGEN" / "interlinear-snapshot" / "chapters" / "genesis"
OSHB_DIR  = ANGELOS / "IdiomaORIGEN" / "oshb-morph"           / "chapters" / "01_Génesis"
INTER_DIR = ANGELOS / "IdiomaORIGEN" / "interlineal"           / "chapters" / "01_Génesis"
IN_FILE   = Path(__file__).parent.parent / "data" / "genesis_full.json"
OUT_FILE  = Path(__file__).parent.parent / "data" / "genesis_final.json"


# ════════════════════════════════════════════════════════════════════════════
#  CORRECCIÓN SISTEMÁTICA 1 — PREP.ART (preposición + artículo amalgamados)
# ════════════════════════════════════════════════════════════════════════════

_PATACH = '\u05B7'  # ַ patach
_QAMETS = '\u05B8'  # ָ qamets
_SEGOL  = '\u05B6'  # ֶ segol
_DAGESH = '\u05BC'  # ּ dagesh / mappiq
_SHVA   = '\u05B0'  # ְ shva

# Preposición simple (con shva) → morph PREP  (no tocar)
# Preposición amalgamada con artículo:
#   ל + vocal_larga  →  לַ/לָ/לֶ
#   ב/כ + dagesh + vocal_larga  →  בַּ/בָּ/כַּ/כָּ

def is_prep_art(form: str) -> bool:
    """True cuando un prefijo preposicional ha absorbido el artículo definido."""
    if not form:
        return False
    c0 = form[0]

    # ל  — vocal de amalgamación: patach/qamets/segol (shva = prep simple)
    if c0 == '\u05DC':            # ל lamed
        return len(form) >= 2 and form[1] in (_PATACH, _QAMETS, _SEGOL)

    # ב o כ — dagesh obligatorio cuando hay amalgamación
    if c0 in ('\u05D1', '\u05DB'):  # ב bet, כ kaf
        return (len(form) >= 3
                and form[1] == _DAGESH
                and form[2] in (_PATACH, _QAMETS))

    return False


def maybe_fix_prep_art(morph: str, form: str) -> str:
    """Devuelve 'PREP.ART' si corresponde, si no devuelve el morph original."""
    if morph in ('PREP', '') and is_prep_art(form):
        return 'PREP.ART'
    return morph


# ════════════════════════════════════════════════════════════════════════════
#  CORRECCIÓN SISTEMÁTICA 3 — Español funcional por alineación griega
# ════════════════════════════════════════════════════════════════════════════

# Cuando una conjunción hebrea está alineada con ciertos griegos, el español
# que suelen dar los interlineales es incorrecto o ambiguo.
# Estos valores son seguros: la correspondencia griega es unívoca.
_GR_ES_CONJ = {
    'ὅτι':   'que',       # כִּי complementivo → "que" (nunca "y")
    'ἵνα':   'para que',
    'ὡς':    'como',
    'ὅταν':  'cuando',
    'εἰ':    'si',
    'ἐάν':   'si',
    'ἕως':   'hasta que',
    'ὅτε':   'cuando',
    'ἐπεί':  'porque',
    'καθώς': 'como',
    'ἐπειδή':'después que',
}

# Preposiciones con traducción determinada por el griego
_GR_ES_PREP = {
    'ἀνὰ μέσον': 'entre',   # בֵּין / בֵין — "between" (no "de")
}

_ES_INFINITIVE_LEAKAGE = {
    # Formas infinitivas/lemáticas que no deben aparecer como glosa de un verbo conjugado
    'ser', 'estar', 'haber', 'tener', 'hacer', 'decir', 'ir', 'dar', 'ver',
    'venir', 'poder', 'querer', 'saber', 'llegar', 'pasar', 'deber', 'poner',
    'parecer', 'quedar', 'creer', 'llevar', 'dejar', 'seguir', 'encontrar',
    'llamar', 'volver', 'tomar', 'conocer', 'vivir', 'sentir', 'tratar',
    'mirar', 'contar', 'empezar', 'crear', 'separar', 'dividir', 'bendecir',
    'hablar', 'caminar', 'salir', 'entrar', 'subir', 'bajar', 'caer',
    'morir', 'nacer', 'partir', 'poner', 'traer', 'producir', 'cubrir',
    # 'dé' excluido: es una forma válida para QAL.PTCA (עֹשֶׂה "que dé")
}

# Participios HIF.PTCA que el snapshot mal asigna como verbos finitos o imperativos
# Mapa: glosa_griega_base → glosa_ES_participio
_GR_PTCA_ES = {
    'σπεῖρον':      'que produce',  # מַזְרִיעַ HIF.PTCA
    # ποιοῦν excluido: עֹשֶׂה QAL.PTCA conserva 'que dé' del snapshot/juss-map
    'βλαστησάτω':   'produzca',              # תַּדְשֵׁא HIF.JUSS (ya OK)
}

def fix_es_by_greek(es: str, morph: str, gr_word: str) -> str:
    """Corrige el español cuando la alineación griega indica otro valor."""
    if not gr_word:
        return es
    gr_strip = gr_word.strip().rstrip('.,·;')

    # Conjunciones / partículas
    if 'CONJ' in morph or 'PART' in morph:
        gr_base = gr_strip.split()[0]
        corrected = _GR_ES_CONJ.get(gr_base)
        if corrected:
            return corrected

    # Preposiciones con traducción determinada por griego compuesto
    if 'PREP' in morph:
        corrected = _GR_ES_PREP.get(gr_strip)
        if corrected:
            return corrected

    # Participios con glosa griega conocida mal asignada como imperativo/infinitivo
    if 'PTCA' in morph and es in _ES_INFINITIVE_LEAKAGE:
        gr_base = gr_strip.split()[0]
        corrected = _GR_PTCA_ES.get(gr_base)
        if corrected:
            return corrected

    return es


# ════════════════════════════════════════════════════════════════════════════
#  CORRECCIÓN SISTEMÁTICA 4 — Vav vacío
# ════════════════════════════════════════════════════════════════════════════

_VAV = '\u05D5'   # ו vav

def default_es_for_prefix(form: str, es: str, morph: str = "") -> str:
    """
    Para prefijos sin español asignado, aplica valores por defecto seguros.
    Solo para partículas invariables bien conocidas.

    IMPORTANTE: nunca aplicar el default de "y" a sufijos pronominales (PRS.*).
    El CATSS pone sufijos como la forma וֹ/וְ en posición de prefijo (ej. )T/W),
    y visualmente se confunden con la conjunción וְ, pero NO lo son.
    Además, si el snapshot ya asignó 'y' a un sufijo PRS, se elimina.
    """
    # Sufijo pronominal: nunca 'y', y si viene con 'y' del snapshot, se borra
    if morph.startswith('PRS') or '+RBS' in morph:
        return '' if es == 'y' else es
    if es:
        return es
    if not form:
        return es
    # Vav conjuntivo (todas las vocalizaciones de וְ/וַ/וּ/וָ/וֽ)
    if form[0] == _VAV:
        return 'y'
    return es


# ─── CARGA ───────────────────────────────────────────────────────────────────

def load_snapshot_chapter(cap: int) -> dict:
    """
    Retorna dict {verso_str: [segmentos]} para el capítulo.
    Estructura del archivo: {verses: {"1": {mt_verse:1, segments:[...]}, ...}}
    """
    p = SNAP_DIR / f"{cap}.json"
    if not p.exists():
        return {}
    raw = json.loads(p.read_text(encoding="utf-8"))
    verses_dict = raw.get("verses", {})
    result = {}
    for verse_key, verse_obj in verses_dict.items():
        segs = verse_obj.get("segments", [])
        segs = [s for s in segs if s.get("visible_in_admin_ui", True)]
        def _sort_key(s):
            try:
                tn = int(s.get("token_num") or 0)
            except (ValueError, TypeError):
                tn = 0
            mi = s.get("morpheme_index") or 0
            return (tn, mi)
        segs.sort(key=_sort_key)
        result[str(verse_key)] = segs
    return result


def load_oshb_chapter(cap: int) -> dict:
    """Retorna dict {verso_str: {forms:[...], morphs:[...]}} para niqqud."""
    p = OSHB_DIR / f"{cap}.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def flat_str(v) -> str:
    """Convierte cualquier valor de glosa a string plano (maneja listas)."""
    if isinstance(v, list):
        parts = [str(x) for x in v if x]
        return parts[0] if len(parts) == 1 else " / ".join(parts)
    return str(v) if v else ""


_RE_TRAILING_PUNCT = re.compile(r'[.,;:!?·]+$')

def normalize_es(es: str) -> str:
    """
    Normaliza una glosa española:
      - Elimina puntuación final (comas, puntos, etc. del interlineal)
      - Pone en minúscula la inicial si es mayúscula artificial de inicio de frase
        (no toca transliteraciones que empiezan con ' como 'Elohim)
    """
    if not es:
        return es
    es = _RE_TRAILING_PUNCT.sub('', es).strip()
    # No tocar transliteraciones (ʿElohim, 'Elohim, etc.)
    if es and es[0] in ("'", "\u02BF", "\u02BE"):
        return es
    # Lowercase inicial si está en mayúscula (capitalización de inicio de frase)
    if es and es[0].isupper():
        es = es[0].lower() + es[1:]
    return es


def load_inter_chapter(cap: int) -> dict:
    """
    Retorna dict {verso_str: [tokens]} del interlineal original.
    Fallback para versículos con mismatch en el snapshot.
    """
    p = INTER_DIR / f"{cap}.json"
    if not p.exists():
        return {}
    raw = json.loads(p.read_text(encoding="utf-8"))
    result = {}
    for k, v in raw.items():
        toks = v.get("tokens", [])
        flat = []
        for t in toks:
            orig   = t.get("orig", "")
            morphs = t.get("morphs", "")
            strg   = t.get("strongs", "")
            glosa  = t.get("es", "")
            if isinstance(orig, list):
                # Token multi-morfema: distribuir las glosas por posición si es posible
                glosa_list = glosa if isinstance(glosa, list) else [glosa] * len(orig)
                for i, o in enumerate(orig):
                    g = glosa_list[i] if i < len(glosa_list) else ""
                    flat.append({
                        "orig": o,
                        "morphs": morphs[i] if isinstance(morphs, list) else morphs,
                        "strongs": flat_str(strg),
                        "es": flat_str(g),
                    })
            else:
                # Token de un solo morfema: si es tiene lista, tomar solo el primero
                es_val = glosa[0] if isinstance(glosa, list) and glosa else flat_str(glosa)
                flat.append({"orig": orig, "morphs": morphs,
                             "strongs": flat_str(strg), "es": flat_str(es_val)})
        result[k] = flat
    return result


def make_seg_from_inter(t: dict, oshb_form="", oshb_morph="") -> dict:
    """Convierte un token del interlineal en un segmento compatible con snapshot."""
    return {
        "hebrew":    oshb_form or t.get("orig", ""),
        "morphology": oshb_morph,
        "spanish":   flat_str(t.get("es", "")),
        "greek_lxx": "",
        "lxx_tier":  "",
        "strongs":   flat_str(t.get("strongs", "")),
    }


# ── Alineación por consonantes ────────────────────────────────────────────────

def consonants(s: str) -> str:
    """Extrae solo las consonantes hebreas de una cadena (sin niqqud ni cantilación)."""
    return "".join(c for c in (s or "") if "\u05D0" <= c <= "\u05EA")


# ── Mapa de consonantes CATSS ASCII → Unicode (prefijos y stems) ──────────────
_CCAT_CONS = {
    ')': 'א', 'B': 'ב', 'G': 'ג', 'D': 'ד', 'H': 'ה',
    'W': 'ו', 'Z': 'ז', 'X': 'ח', '+': 'ט', 'Y': 'י',
    'K': 'כ', 'L': 'ל', 'M': 'מ', 'N': 'נ', 'S': 'ס',
    '(': 'ע', 'P': 'פ', 'C': 'צ', 'Q': 'ק', 'R': 'ר',
    '&': 'שׂ', '$': 'שׁ', 'T': 'ת',
}

def ccat_to_cons(ascii_str: str) -> str:
    """Convierte string ASCII CATSS a consonantes hebreas Unicode (sin niqqud)."""
    return "".join(_CCAT_CONS.get(ch, '') for ch in (ascii_str or ""))


# Sufijos pronominales que se saltan al hacer match de stem+sufijo.
# Incluye formas singulares Y plurales (yod + marcador de pl).
_HEB_SUFFIX_CONS = frozenset({
    # Formas simples (1-2 letras) — singular y sufijos básicos
    'ו', 'ה', 'ם', 'ן', 'ך', 'כ', 'י',
    'הו', 'הם', 'הן', 'הך', 'כם', 'כן',
    'ני', 'נו', 'תי', 'תה', 'תם', 'תן', 'נה',
    # Formas con yod (sufijos en sustantivos plurales)
    'יו',   # 3ms plural: דְּבָרָיו (sus palabras)
    'יה',   # 3fs plural: דְּבָרֶיהָ
    'יהם',  # 3mp plural: דְּבָרֵיהֶם
    'יהן',  # 3fp plural: דְּבָרֵיהֶן
    'יך',   # 2ms plural: דְּבָרֶיךָ
    'יכם',  # 2mp plural
    'ינו',  # 1cp plural: דְּבָרֵינוּ
    'ים',   # ם precedido de yod (variante)
})


# ── Sufijo pronominal → pronombre griego genitivo ─────────────────────────────
# Mapeo cerrado: morfología OSHB → pronombre genitivo griego esperado en LXX
_SUFFIX_TO_GR: dict = {
    'PRS.P3.M.SG':    'αὐτοῦ',
    'PRS.P3.F.SG':    'αὐτῆς',
    'PRS.P3.M.PL':    'αὐτῶν',
    'PRS.P3.F.PL':    'αὐτῶν',
    'PRS.P3.C.PL':    'αὐτῶν',
    'PRS.P2.M.SG':    'σου',
    'PRS.P2.F.SG':    'σου',
    'PRS.P2.M.PL':    'ὑμῶν',
    'PRS.P2.F.PL':    'ὑμῶν',
    'PRS.P2.C.PL':    'ὑμῶν',
    'PRS.P1.SG':      'μου',
    'PRS.P1.C.SG':    'μου',
    'PRS.P1.PL':      'ἡμῶν',
    'PRS.P1.C.PL':    'ἡμῶν',
    # Variantes cortas (sin puntos) que aparecen en snapshot OSHB
    'RBSM3': 'αὐτοῦ', 'RBSF3': 'αὐτῆς',
    'RBPM3': 'αὐτῶν', 'RBPF3': 'αὐτῶν', 'RBPC3': 'αὐτῶν',
    'RBSM2': 'σου',   'RBSF2': 'σου',
    'RBPM2': 'ὑμῶν',  'RBPF2': 'ὑμῶν',
    'RBSM1': 'μου',   'RBSC1': 'μου',   # 1cs (common gender singular)
    'RBPM1': 'ἡμῶν',  'RBPC1': 'ἡμῶν', 'RBSF1': 'μου',
}

# ── Mejora 2: Pronombres ACUSATIVOS para sufijos verbales ────────────────────
# Cuando el padre es un verbo o infinitivo (no un sustantivo), el sufijo pronominal
# en LXX es acusativo (αὐτόν, αὐτήν…) no genitivo (αὐτοῦ, αὐτῆς…).
_SUFFIX_TO_GR_ACC: dict = {
    'PRS.P3.M.SG': 'αὐτόν',   'PRS.P3.F.SG': 'αὐτήν',
    'PRS.P3.M.PL': 'αὐτούς',  'PRS.P3.F.PL': 'αὐτάς',
    'PRS.P3.C.PL': 'αὐτούς',
    'PRS.P2.M.SG': 'σε',      'PRS.P2.F.SG': 'σε',
    'PRS.P2.M.PL': 'ὑμᾶς',   'PRS.P2.F.PL': 'ὑμᾶς',
    'PRS.P1.C.SG': 'με',      'PRS.P1.SG':   'με',
    'PRS.P1.C.PL': 'ἡμᾶς',   'PRS.P1.PL':   'ἡμᾶς',
    'RBSM3': 'αὐτόν', 'RBSF3': 'αὐτήν',
    'RBPM3': 'αὐτούς','RBPF3': 'αὐτάς',
    'RBSM2': 'σε',    'RBSM1': 'με', 'RBSC1': 'με',
    'RBPM1': 'ἡμᾶς', 'RBPC1': 'ἡμᾶς',
}

# Morfologías que indican un padre VERBAL (verbo o infinitivo)
_VERBAL_MORPHS = frozenset({'VERBO', 'VERB'})

def _is_verbal_morph(morph: str) -> bool:
    """True si la morfología indica que el token padre es un verbo/infinitivo."""
    return morph.startswith('VERBO') or morph.startswith('VERB')

# Sufijo pronominal → glosa española por defecto
_SUFFIX_TO_ES: dict = {
    'PRS.P3.M.SG': 'su', 'PRS.P3.F.SG': 'su',
    'PRS.P3.M.PL': 'su', 'PRS.P3.F.PL': 'su', 'PRS.P3.C.PL': 'su',
    'PRS.P2.M.SG': 'tu', 'PRS.P2.F.SG': 'tu',
    'PRS.P2.M.PL': 'vuestro', 'PRS.P2.F.PL': 'vuestro', 'PRS.P2.C.PL': 'vuestro',
    'PRS.P1.SG': 'mi', 'PRS.P1.C.SG': 'mi',
    'PRS.P1.PL': 'nuestro', 'PRS.P1.C.PL': 'nuestro',
    'RBSM3': 'su', 'RBSF3': 'su', 'RBPM3': 'su',
    'RBSM2': 'tu', 'RBSF2': 'tu', 'RBSM1': 'mi',
}


import unicodedata as _ud

def _strip_gr_diacritics(s: str) -> str:
    """Elimina diacríticos griegos para comparación normalizada."""
    return ''.join(c for c in _ud.normalize('NFD', s)
                   if _ud.category(c) != 'Mn')


# Bug 1 fix: letras hebreas que se confunden visualmente con griegas
# Ocurre cuando strings griegos se tipean en teclado con entrada hebrea activa.
_HEB_TO_GR_LOOKALIKE: dict[str, str] = {
    '\u05E8': '\u03C1',  # ר (resh)      → ρ (rho)
    '\u05D7': '\u03C7',  # ח (chet)      → χ (chi)
    '\u05DF': '\u03BD',  # ן (final nun) → ν (nu)
    '\u05E0': '\u03BD',  # נ (nun)       → ν (nu)
    '\u05DE': '\u03BC',  # מ (mem)       → μ (mu)
    '\u05E1': '\u03C3',  # ס (samekh)   → σ (sigma)
    '\u05D3': '\u03B4',  # ד (dalet)    → δ (delta)
    '\u05D0': '\u03B1',  # א (alef)     → α (alpha)
    '\u05D1': '\u03B2',  # ב (bet)      → β (beta)
}
_HEB_RANGE = range(0x05D0, 0x05EB)

def sanitize_greek(s: str) -> str:
    """
    Reemplaza caracteres hebreos 'lookalike' en un string que debe ser griego.
    Solo se aplica a campos gr_word, prefix_gr y similares — NUNCA a campos hebreos.
    """
    if not s or not any(ord(c) in _HEB_RANGE for c in s):
        return s
    return ''.join(_HEB_TO_GR_LOOKALIKE.get(c, c) for c in s)


def divorce_greek(gr_phrase: str, suffix_morph: str,
                  stem_morph: str = "") -> tuple:
    """
    Separa el pronombre griego del par Greek phrase.

    Estrategia:
    1. Si el padre es VERBAL (verbo/infinitivo), busca pronombre ACUSATIVO.
       Ejemplo: הוֹלִידּוֹ → "τὸ γεννῆσαι αὐτόν" → stem="τὸ γεννῆσαι", suf="αὐτόν"
    2. Si el padre es un sustantivo, busca pronombre GENITIVO.
       Ejemplo: זַרְעֹו → "τὸ σπέρμα αὐτοῦ" → stem="τὸ σπέρμα", suf="αὐτοῦ"
    3. En ambos casos, primero prueba el tipo canónico; si no lo encuentra, prueba
       el otro tipo como fallback (LXX a veces usa construcciones inesperadas).

    Busca la palabra desde el FINAL del phrase para cubrir orden LXX invertido.

    Returns:
        (stem_greek, suffix_greek)  — suffix_greek vacío si no se pudo separar.
    """
    if not gr_phrase:
        return gr_phrase, ''

    is_verbal = _is_verbal_morph(stem_morph)

    # Pronombres a buscar: primario y alternativo
    if is_verbal:
        primary_pron   = _SUFFIX_TO_GR_ACC.get(suffix_morph, '')
        secondary_pron = _SUFFIX_TO_GR.get(suffix_morph, '')
    else:
        primary_pron   = _SUFFIX_TO_GR.get(suffix_morph, '')
        secondary_pron = _SUFFIX_TO_GR_ACC.get(suffix_morph, '')

    words       = gr_phrase.split()
    plain_words = [_strip_gr_diacritics(w.strip('.,·;:')) for w in words]

    for expected in (primary_pron, secondary_pron):
        if not expected:
            continue
        pron_words = [_strip_gr_diacritics(w) for w in expected.split()]
        n = len(pron_words)
        # Buscar desde el final (más seguro en LXX — el pronombre suele ir al final)
        for i in range(len(words) - n, -1, -1):
            if plain_words[i:i + n] == pron_words:
                suffix_gr = ' '.join(words[i:i + n])
                stem_gr   = ' '.join(words[:i] + words[i + n:]).strip()
                return stem_gr, suffix_gr

    return gr_phrase, ''  # no se encontró: stem conserva todo, suffix vacío


def _snap_match(snap_cons_list: list, snap_segs: list, ptr: int,
                target_cons: str, lookahead: int = 3):
    """
    Busca el primer segmento snapshot (a partir de ptr) que coincida con target_cons.

    Criterios de coincidencia (en orden de prioridad):
      1. Exacta: snap_cons == target_cons
      2. Stem+sufijo: target empieza con snap (CATSS tiene sufijo pegado al stem)
         → avanza ptr saltando segmentos de sufijo pronominales que siguen
         → retorna el sufijo absorbido para posterior procesamiento

    IMPORTANTE: La antigua Regla 3 ("snap tiene más consonantes que target")
    fue eliminada porque causaba un efecto cascada: cuando el snapshot tenía una
    palabra completa (ej. חַיְתֹו = חיתו) y CATSS tenía solo la raíz (XYT = חית),
    la regla 3 consumía el segmento completo pero dejaba el siguiente elemento CATSS
    (el sufijo W = ו) sin segmento correspondiente. Eso desfasaba snap_ptr para
    todos los pares siguientes del versículo.

    El lookahead se redujo de 6 a 3 para minimizar falsos positivos en salto de puntero.

    Retorna (segmento_o_None, nuevo_ptr, sufijo_absorbido_o_None).
    """
    if not target_cons:
        return None, ptr, None

    for offset in range(lookahead + 1):
        i = ptr + offset
        if i >= len(snap_segs):
            break
        sc = snap_cons_list[i]
        if not sc:
            continue

        # NUEVO: STOP-AT-SUPERSET. Si snap[i] tiene MÁS consonantes que el target Y
        # el target es prefijo del snap (snap = combinado verbo+sufijo/prefijo+sufijo),
        # NO saltamos más allá. Retornar None permite que (a) este elemento CATSS
        # caiga a fallback OSHB y (b) el siguiente CATSS pueda revisar el snap
        # combinado vía _snap_lookup. Evita la cascada de pérdida observada en Gen 5:2.
        if sc.startswith(target_cons) and len(sc) > len(target_cons):
            return None, ptr, None

        # 1. Coincidencia exacta
        if target_cons == sc:
            return snap_segs[i], i + 1, None

        # 2. CATSS stem incluye sufijo pronominal: target='מינו' vs snap_cons='מינ'
        #    Solo aplica a stems de 2+ consonantes para evitar falsos con letras simples.
        if len(sc) >= 2 and target_cons.startswith(sc):
            next_ptr = i + 1
            absorbed_suffix = None
            # Recoger el primer sufijo pronominal que sigue (para inyectarlo como prs_suffix)
            while next_ptr < len(snap_cons_list) and snap_cons_list[next_ptr] in _HEB_SUFFIX_CONS:
                if absorbed_suffix is None:
                    absorbed_suffix = snap_segs[next_ptr]
                next_ptr += 1
            return snap_segs[i], next_ptr, absorbed_suffix

        # Regla 3 ELIMINADA: sc.startswith(target_cons) causaba cascade en versículos complejos.
        # Ejemplo: CATSS XYT (חית) vs snap חַיְתֹו (חיתו) → regla 3 consumía el segmento
        # completo pero el siguiente CATSS elemento (sufijo W=ו) quedaba sin match,
        # desfasando snap_ptr para el resto del versículo.

    return None, ptr, None  # sin coincidencia: no avanzar ptr


# ─── UTILIDADES ─────────────────────────────────────────────────────────────

def catss_element_count(pair: dict) -> int:
    """Cuenta cuántos morfemas OSHB consume este par (prefijos + stem por he_word)."""
    if pair.get("kind") in ("gk_add", "heb_omit"):
        return 0
    total = 0
    for hw in pair.get("he_words", []):
        total += len(hw.get("prefixes", [])) + 1
    return total


def seg_val(seg: dict, key: str, default="") -> str:
    v = seg.get(key, default)
    if v is None:
        return default
    if isinstance(v, list):
        return " / ".join(str(x) for x in v if x)
    return str(v)


# ─── FUSIÓN PRINCIPAL (Token-level consonant alignment) ─────────────────────

def merge_verse(verse: dict, snap_segs: list, oshb_verse: dict) -> None:
    """
    Alineación consonántica token-a-token entre elementos CATSS y segmentos snapshot.

    Para cada elemento (prefijo o stem) del verso:
      - Extrae consonantes del elemento CATSS (desde ASCII o unicode)
      - Busca el segmento snapshot con consonantes coincidentes (avanzando ptr)
      - Si encuentra: asigna es, gr_word, morph, niqqud del snapshot
      - Si no encuentra: usa OSHB para niqqud/morph, deja es/gr vacíos

    Nunca asigna datos de otra posición incorrecta — error aislado al token.
    """
    oshb_forms  = oshb_verse.get("forms",  [])
    oshb_morphs = oshb_verse.get("morphs", [])

    snap_cons_list = [consonants(s.get("hebrew", "")) for s in snap_segs]
    snap_ptr  = 0   # puntero en snapshot (avanza con cada match)
    oshb_ptr  = 0   # puntero en OSHB (avanza siempre, 1 por elemento)

    # ── Snapshot lookup auxiliar: cons → (es, gr, morph) ─────────────────────
    # Permite a post_process_verse rescatar glosas combinadas (ej. "los creó")
    # que no se asignaron porque ningún elemento CATSS hizo match individual
    # con un segmento snapshot combinado (verbo+sufijo en una sola entrada).
    # Solo guarda la PRIMERA aparición de cada cons (evita confusión con homónimos).
    _snap_lookup: dict[str, dict] = {}
    for _i, _seg in enumerate(snap_segs):
        _c = snap_cons_list[_i]
        if _c and _c not in _snap_lookup:
            _snap_lookup[_c] = {
                "hebrew":  seg_val(_seg, "hebrew"),
                "es":      seg_val(_seg, "spanish"),
                "gr":      seg_val(_seg, "greek_lxx"),
                "morph":   seg_val(_seg, "morphology"),
                "strongs": seg_val(_seg, "strongs"),
            }
    verse["_snap_lookup"] = _snap_lookup

    # ── Mejora 1: Anclaje de secuencia relativa para homónimos ───────────────
    # Cuenta cuántas veces aparece cada forma consonántica en CATSS y en snapshot.
    # Para palabras que se repiten, reduce el lookahead a 1 (evita saltar al gemelo).
    from collections import Counter as _Counter
    _catss_cons_freq: dict[str, int] = _Counter()
    for _p in verse.get("pairs", []):
        for _hw in _p.get("he_words", []):
            for _pfx in _hw.get("prefixes", []):
                _c = ccat_to_cons(_pfx)
                if _c: _catss_cons_freq[_c] += 1
            _sc = _hw.get("stem", "")
            if _sc and _sc[0] not in ('=', '%'):
                _c = consonants(_hw.get("stem_unicode","") or ccat_to_cons(_sc))
                if _c: _catss_cons_freq[_c] += 1
    _seen_cons: dict[str, int] = _Counter()   # cuántas veces ya usamos esta forma

    for pair in verse.get("pairs", []):
        if catss_element_count(pair) == 0:
            continue

        for hw in pair.get("he_words", []):
            hw["prefix_forms"]  = []
            hw["prefix_morphs"] = []
            hw["prefix_es"]     = []
            hw["prefix_gr"]     = []
            hw["prefix_tier"]   = []

            # ── Prefijos ──────────────────────────────────────────────────────
            for pfx_ascii in hw.get("prefixes", []):
                # Consonantes del prefijo CATSS (siempre 1 letra, e.g. W→ו, H→ה)
                pfx_cons = ccat_to_cons(pfx_ascii)
                # Fallback OSHB para este slot
                oshb_form  = oshb_forms[oshb_ptr]  if oshb_ptr < len(oshb_forms)  else ""
                oshb_morph = oshb_morphs[oshb_ptr] if oshb_ptr < len(oshb_morphs) else ""

                # Mejora 1: lookahead reducido para homónimos (evita "efecto elástico")
                # Mejora 3: lookahead=1 para prefijos numéricos (rarísimo, por completud)
                _pfx_la = 1 if (_seen_cons.get(pfx_cons, 0) > 0
                                 and _catss_cons_freq.get(pfx_cons, 1) > 1) else 3
                if 'NUM' in oshb_morph:
                    _pfx_la = 1
                _seen_cons[pfx_cons] = _seen_cons.get(pfx_cons, 0) + 1

                seg, snap_ptr, _ = _snap_match(snap_cons_list, snap_segs, snap_ptr,
                                               pfx_cons, lookahead=_pfx_la)

                if seg:
                    hw["prefix_forms"].append(seg_val(seg, "hebrew") or oshb_form)
                    hw["prefix_morphs"].append(seg_val(seg, "morphology") or oshb_morph)
                    hw["prefix_es"].append(seg_val(seg, "spanish"))
                    hw["prefix_gr"].append(seg_val(seg, "greek_lxx"))
                    hw["prefix_tier"].append(seg_val(seg, "lxx_tier"))
                else:
                    hw["prefix_forms"].append(oshb_form)
                    hw["prefix_morphs"].append(oshb_morph)
                    hw["prefix_es"].append("")
                    hw["prefix_gr"].append("")
                    hw["prefix_tier"].append("")

                oshb_ptr += 1

            # ── Stem ──────────────────────────────────────────────────────────
            # Saltar meta-notaciones CATSS como =%p, =KTW, %p, p, q …
            # En CCAT, todos los consonantes hebreos son MAYÚSCULAS.
            # Cualquier stem que sea solo letras minúsculas (ej. 'p', 'q')
            # o que empiece con '=' o '%' es un marcador de referencia paralela,
            # no hebreo real. Crear token vacío SIN consumir oshb_ptr.
            stem_raw = hw.get("stem", "")
            _is_meta = bool(stem_raw and (
                stem_raw[0] in ('=', '%') or
                (stem_raw.isalpha() and stem_raw.islower())
            ))
            if _is_meta:
                # Limpiar TODO el he_word incluyendo prefijos residuales que ya se añadieron.
                # Un stem meta (=KTW, =%p, 'p', 'q'…) invalida el par entero porque
                # los prefijos que aparecen antes del = son también artefactos de la
                # notación CATSS (repetición paralela), no hebreo real independiente.
                hw["he_form"]       = ""
                hw["he_morph"]      = ""
                hw["strongs"]       = ""
                hw["es"]            = ""
                hw["gr_word"]       = ""
                hw["lxx_tier"]      = ""
                hw["prefix_forms"]  = []
                hw["prefix_morphs"] = []
                hw["prefix_es"]     = []
                hw["prefix_gr"]     = []
                hw["prefix_tier"]   = []
                hw["prefixes"]      = []
                # NO avanzar oshb_ptr — este token no existe en OSHB
                continue

            # Consonantes del stem desde su unicode sin niqqud (CATSS ya decodificó)
            stem_cons = consonants(hw.get("stem_unicode", "") or
                                   ccat_to_cons(stem_raw))
            oshb_form  = oshb_forms[oshb_ptr]  if oshb_ptr < len(oshb_forms)  else ""
            oshb_morph = oshb_morphs[oshb_ptr] if oshb_ptr < len(oshb_morphs) else ""

            # Mejora 1: lookahead reducido para stems que se repiten en el versículo
            # Mejora 3: lookahead=1 para stems numéricos (NUM.CARD / NUM.ORD)
            #           — evita que números con homofonía griego-hebrea se desplacen
            _stm_la = 3
            if stem_cons and _seen_cons.get(stem_cons, 0) > 0 and _catss_cons_freq.get(stem_cons, 1) > 1:
                _stm_la = 1   # homónimo: no saltar más de 1 posición
            if 'NUM' in oshb_morph:
                _stm_la = 1   # número: no saltar (LXX y MT pueden diferir en valor)
            _seen_cons[stem_cons] = _seen_cons.get(stem_cons, 0) + 1

            seg, snap_ptr, absorbed_suf = _snap_match(
                snap_cons_list, snap_segs, snap_ptr, stem_cons, lookahead=_stm_la)

            if seg:
                hw["he_form"]  = seg_val(seg, "hebrew")    or oshb_form
                hw["he_morph"] = seg_val(seg, "morphology") or oshb_morph
                hw["strongs"]  = seg_val(seg, "strongs")
                hw["es"]       = seg_val(seg, "spanish")
                hw["gr_word"]  = seg_val(seg, "greek_lxx")
                hw["lxx_tier"] = seg_val(seg, "lxx_tier")
                # Guardar sufijo absorbido para que post_process lo inyecte
                if absorbed_suf is not None:
                    hw["_absorbed_suffix"] = absorbed_suf
            else:
                hw["he_form"]  = oshb_form
                hw["he_morph"] = oshb_morph
                hw["strongs"]  = ""
                hw["es"]       = ""
                hw["gr_word"]  = ""
                hw["lxx_tier"] = ""

            oshb_ptr += 1


# ════════════════════════════════════════════════════════════════════════════
#  POST-PROCESAMIENTO SISTEMÁTICO (aplica a todos los libros)
# ════════════════════════════════════════════════════════════════════════════

# Cantilación hebrea — para extracción de consonantes (uso interno ccat_to_cons).
# NOTE: NO incluye U+05BE (maqaf) en esta versión para evitar conflicto con display.
_CANTILL_RE = re.compile(
    r'[\u0591-\u05AF\u05BD\u05BF\u05C0\u05C1\u05C2\u05C4\u05C5\u05C7\u200C\u200D]'
)

# Maqaf y tropes de cantilación — solo para limpiar formas DE DISPLAY al promover.
# U+05BE = maqaf (־), U+0591-U+05AF = tropes. NO toca shin-dot, sin-dot ni nikud.
_MAQAF_RE = re.compile(r'[\u05BE]')

# Spanish defaults para el marcador de objeto directo + sufijo pronominale
_OBJ_MARKER_ES: dict[str, str] = {
    'PRS.P3.M.SG': 'lo',  'PRS.P3.F.SG': 'la',
    'PRS.P3.M.PL': 'los', 'PRS.P3.F.PL': 'las', 'PRS.P3.C.PL': 'los',
    'PRS.P2.M.SG': 'te',  'PRS.P2.F.SG': 'te',
    'PRS.P2.M.PL': 'os',  'PRS.P2.F.PL': 'os',
    'PRS.P1.C.SG': 'me',  'PRS.P1.SG':   'me',
    'PRS.P1.C.PL': 'nos', 'PRS.P1.PL':   'nos',
    'PRON.OBJ':    'lo',  # forma monolítica del snapshot
}

# Pronombres SUJETO — para sufijos pegados a verbos PASIVOS (Niphal/Hofal).
# En passive, el sufijo marca al SUJETO del verbo: "fueron creados ELLOS"
_SUBJ_MARKER_ES: dict[str, str] = {
    'PRS.P3.M.SG': 'él',     'PRS.P3.F.SG': 'ella',
    'PRS.P3.M.PL': 'ellos',  'PRS.P3.F.PL': 'ellas',
    'PRS.P3.C.PL': 'ellos',
    'PRS.P2.M.SG': 'tú',     'PRS.P2.F.SG': 'tú',
    'PRS.P2.M.PL': 'vosotros','PRS.P2.F.PL': 'vosotras',
    'PRS.P1.C.SG': 'yo',     'PRS.P1.SG':   'yo',
    'PRS.P1.C.PL': 'nosotros','PRS.P1.PL':  'nosotros',
}

# Glosa española para אֵת+suffix (marcador de objeto directo con pronombre).
# Strong's H853 — אֵת sola no se traduce, pero con sufijo significa "a + pron".
_AT_PLUS_SUFFIX_ES: dict[str, str] = {
    'PRS.P3.M.SG': 'a él',       'PRS.P3.F.SG': 'a ella',
    'PRS.P3.M.PL': 'a ellos',    'PRS.P3.F.PL': 'a ellas',
    'PRS.P3.C.PL': 'a ellos',
    'PRS.P2.M.SG': 'a ti',       'PRS.P2.F.SG': 'a ti',
    'PRS.P2.M.PL': 'a vosotros', 'PRS.P2.F.PL': 'a vosotras',
    'PRS.P1.C.SG': 'a mí',       'PRS.P1.SG':   'a mí',
    'PRS.P1.C.PL': 'a nosotros', 'PRS.P1.PL':   'a nosotros',
    'PRON.OBJ':    'a ellos',  # ambigüedad; PRON.OBJ default plural
}

# Verbos auxiliares incompletos — la glosa snapshot suele truncarlos.
# Cuando vemos uno SOLO + verb morph pasivo, sugiere "X creados/hechos/etc"
_INCOMPLETE_AUX_ES = frozenset({'fue', 'fueron', 'siendo', 'ser', 'sido', 'es'})

# Mini-diccionario de raíces hebreas (3 consonantes) → participio pasivo español
# Usado para completar glosas truncadas en Niphal/Hofal infin construct.
# Solo raíces frecuentes en Génesis; ampliable según necesidad.
_HEB_ROOT_PASSIVE_ES: dict[str, str] = {
    'ברא':  'creados',     # bara — crear
    'עשה':  'hechos',      # asah — hacer
    'אמר':  'dichos',      # amar — decir
    'שלח':  'enviados',    # shalach — enviar
    'לקח':  'tomados',     # laqach — tomar
    'ראה':  'vistos',      # ra'ah — ver
    'נתן':  'dados',       # natan — dar
    'בנה':  'edificados',  # banah — construir
    'כתב':  'escritos',    # katav — escribir
    'קרא':  'llamados',    # qara — llamar
    'שמע':  'oídos',       # shama — oír
    'ידע':  'conocidos',   # yada — conocer
    'אהב':  'amados',      # ahav — amar
    'הלך':  'idos',        # halach — ir
    'מות':  'muertos',     # mut — morir
    'חיה':  'vivos',       # chayah — vivir
    'בוא':  'venidos',     # bo — venir
    'יצא':  'salidos',     # yatza — salir
    'עלה':  'subidos',     # alah — subir
    'ירד':  'descendidos', # yarad — descender
}

# Pronombres objeto que pueden aparecer en glosas combinadas tipo "los creó"
# Se usan para dividir cuando snapshot trae "los creó" y necesitamos asignar
# "los" al sufijo PRS y "creó" al verbo promovido. (Corrección 7 fix)
_OBJ_PRONOUNS = frozenset({
    'me', 'te', 'lo', 'la', 'los', 'las', 'nos', 'os',
    'le', 'les',  # variantes dativas
})

def split_combined_es(combined: str) -> tuple[str, str]:
    """
    Divide una glosa española combinada en (parte_verbal, parte_pronombre).

    Ejemplos:
      "los creó"        → ("creó", "los")
      "creó los"        → ("creó", "los")
      "lo bendijo"      → ("bendijo", "lo")
      "los hizo crear"  → ("hizo crear", "los")  # pronombre + multi-word verb
      "fue creado"      → ("fue creado", "")     # no hay pronombre
      "creó"            → ("creó", "")           # solo verbo
      ""                → ("", "")

    El pronombre objeto puede aparecer al INICIO o al FINAL de la glosa.
    Soporta glosas multi-palabra (verbo compuesto) en cualquier dirección.
    """
    s = (combined or "").strip()
    if not s:
        return "", ""
    parts = s.split()
    if len(parts) < 2:
        return s, ""

    # Pronombre al inicio: "los creó" / "los hizo crear" → verbo es el resto
    first_lower = parts[0].lower()
    if first_lower in _OBJ_PRONOUNS:
        return " ".join(parts[1:]).strip(), parts[0]

    # Pronombre al final: "creó los" / "hizo crear los" → verbo es el resto
    last_lower = parts[-1].lower()
    if last_lower in _OBJ_PRONOUNS:
        return " ".join(parts[:-1]).strip(), parts[-1]

    return s, ""


def complete_passive_gloss(verb_es: str, verb_morph: str,
                           verb_form: str) -> str:
    """
    Completa glosas pasivas truncadas tipo "fueron" → "fueron creados".

    Activa solo si:
      - verb_es es exactamente un auxiliar incompleto (fue/fueron/siendo/ser…)
      - verb_morph indica voz pasiva (NIF, HOF) o infinitivo
      - Se puede extraer la raíz consonántica de 3 letras del verb_form
      - La raíz está en _HEB_ROOT_PASSIVE_ES

    Si cualquier condición falla, retorna verb_es sin cambios.
    """
    es_lower = (verb_es or "").strip().lower()
    if es_lower not in _INCOMPLETE_AUX_ES:
        return verb_es
    if not ('NIF' in verb_morph or 'HOF' in verb_morph):
        return verb_es
    # Extraer raíz consonántica (3 letras significativas, omite prefijo ה- del infin.)
    cons = consonants(verb_form)
    # Niphal infinitivo construct empieza con ה (HIBARE'AM → HBR' → R' después de quitar H)
    # Pero la raíz real son las últimas 3 consonantes (o las 3 raíces principales)
    if len(cons) >= 4 and cons[0] == 'ה':
        root_candidate = cons[1:4]  # quitar ה inicial del infinitivo
    else:
        root_candidate = cons[:3]
    completion = _HEB_ROOT_PASSIVE_ES.get(root_candidate)
    if not completion:
        return verb_es
    return f"{verb_es} {completion}"

# Rango Unicode del alfabeto griego (incluye copta extended y diacríticos)
_GREEK_CHAR_RE = re.compile(r'[\u0370-\u03FF\u1F00-\u1FFF]')

def es_has_greek(es_str: str) -> bool:
    """True si el campo español contiene caracteres griegos (contaminación)."""
    return bool(_GREEK_CHAR_RE.search(es_str or ""))

def post_process_verse(verse: dict) -> None:
    """
    Aplica las correcciones sistemáticas sobre un versículo ya fusionado.

    1. PREP.ART  — ajusta morph de prefijos amalgamados
    2. Griego fallback — asigna griego del par al último stem si todos vacíos
    3. Corrección funcional — corrige español por alineación griega (כִּי→ὅτי = "que")
    4. Vav vacío — pone "y" cuando el prefijo וְ/וַ/וּ no tiene español
    5. [NUEVO] Eliminar he_words fantasma (meta-notación CATSS con todo vacío)
    6. [NUEVO] Fusionar PART.OBJ.DIR prefix + PRS stem → forma combinada (ej. אֹתוֹ)
    """
    for pair in verse.get("pairs", []):
        if pair.get("kind") in ("gk_add", "heb_omit"):
            continue

        hw_list = pair.get("he_words", [])

        # ── Corrección 2: ¿todos los stems tienen gr_word vacío? ─────────────
        all_gr_empty = all(
            not hw.get("gr_word", "") and not any(hw.get("prefix_gr", []))
            for hw in hw_list
        )
        pair_gr = pair.get("gr_unicode", "").strip()

        for hw in hw_list:
            n_pfx = len(hw.get("prefixes", []))

            # ── Corrección 1 & 4: prefijos ───────────────────────────────────
            for k in range(n_pfx):
                form  = hw["prefix_forms"][k]  if k < len(hw.get("prefix_forms",  [])) else ""
                morph = hw["prefix_morphs"][k] if k < len(hw.get("prefix_morphs", [])) else ""
                es    = hw["prefix_es"][k]     if k < len(hw.get("prefix_es",     [])) else ""
                gr    = hw["prefix_gr"][k]     if k < len(hw.get("prefix_gr",     [])) else ""

                # 0. Normalizar morfología corta (VqAJSM3 → VERBO.QAL.JUSS.P3.M.SG)
                hw["prefix_morphs"][k] = normalize_morph(morph)
                morph = hw["prefix_morphs"][k]
                # 1. PREP.ART
                hw["prefix_morphs"][k] = maybe_fix_prep_art(morph, form)
                # 4. Vav vacío + normalización (excluye sufijos PRS para no poner 'y')
                hw["prefix_es"][k] = normalize_es(
                    default_es_for_prefix(form, normalize_es(es), morph)
                )
                # 3. Corrección funcional por griego (aplica también a prefijos)
                hw["prefix_es"][k] = fix_es_by_greek(
                    hw["prefix_es"][k],
                    hw["prefix_morphs"][k],
                    gr,
                )

            # ── Corrección 0 + 1: stem ───────────────────────────────────────
            stem_morph = normalize_morph(hw.get("he_morph", ""))
            hw["he_morph"] = stem_morph
            stem_form  = hw.get("he_form", "")
            hw["he_morph"] = maybe_fix_prep_art(stem_morph, stem_form)

            # Normalizar español del stem
            hw["es"] = normalize_es(hw.get("es", ""))
            # Limpiar 'y' incorrecto en stems con morph PRS (sufijo pronominal)
            stem_morph_final = hw.get("he_morph", "")
            if (stem_morph_final.startswith("PRS") or "+RBS" in stem_morph_final) and hw["es"] == "y":
                hw["es"] = ""
            # ── Corrección 3: español del stem por griego ────────────────────
            hw["es"] = fix_es_by_greek(hw.get("es", ""), hw["he_morph"], hw.get("gr_word", ""))

        # ── Corrección 2: asignar griego del par al último stem ───────────────
        # No asignar a stems vacíos, sufijos pronominales (PRS.*) o números (NUM)
        # cuando el griego del par es mucho más largo que esperado para un número.
        # (Mejora 3: evita que números hereden frases griegas largas incorrectas)
        if all_gr_empty and pair_gr:
            # Buscar el último stem con forma hebrea real y morph no-PRS
            target_hw = None
            for hw in reversed(hw_list):
                morph = hw.get("he_morph", "")
                form  = hw.get("he_form", "")
                if form and not morph.startswith("PRS") and "+RBS" not in morph:
                    target_hw = hw
                    break
            if target_hw is None and hw_list:
                target_hw = hw_list[-1]  # último recurso
            if target_hw is not None:
                # Mejora 3: si el stem es un número cardinal/ordinal y el Greek
                # del par parece una frase larga (>2 palabras), no asignar.
                # Un número en LXX suele ser 1-2 palabras griegas.
                tgt_morph = target_hw.get("he_morph", "")
                pair_gr_words = len(pair_gr.split())
                if 'NUM' in tgt_morph and pair_gr_words > 2:
                    pass  # dejar vacío — número con frase larga es probablemente wrong
                elif target_hw.get("gr_source") in ("prep_prs_no_equiv", "lxx_omission"):
                    pass  # Fix 2: no sobreescribir placeholder anti-clon (C14/LXX)
                else:
                    target_hw["gr_word"] = pair_gr

        # ── Inyección de sufijos pronominales absorbidos ──────────────────────
        for hw in hw_list:
            if "_absorbed_suffix" not in hw:
                continue
            suf_seg   = hw.pop("_absorbed_suffix")
            suf_morph = seg_val(suf_seg, "morphology")

            # Nivel 1: el snapshot ya tiene el griego del sufijo dividido
            suf_gr_from_snap = seg_val(suf_seg, "greek_lxx")

            # Validar que el griego del snapshot sea realmente el pronombre esperado
            # (evita asignar griego incorrecto cuando el snapshot tiene datos erróneos)
            stem_morph_for_suf = hw.get("he_morph", "")
            is_verbal_ctx = _is_verbal_morph(stem_morph_for_suf)

            # Mejora 2: validar con acusativo también si contexto verbal
            expected_pron = _SUFFIX_TO_GR.get(suf_morph, '')
            if is_verbal_ctx:
                expected_pron = (_SUFFIX_TO_GR_ACC.get(suf_morph, '')
                                 or _SUFFIX_TO_GR.get(suf_morph, ''))
            snap_is_valid = False
            if suf_gr_from_snap and expected_pron:
                plain_snap  = _strip_gr_diacritics(suf_gr_from_snap)
                plain_pron  = _strip_gr_diacritics(expected_pron)
                snap_is_valid = plain_pron in plain_snap.split()

            if suf_gr_from_snap and snap_is_valid:
                # Nivel 1: snapshot tiene el griego correcto para el sufijo
                suf_gr  = suf_gr_from_snap
                # El stem conserva su gr_word del snapshot (ya es solo la parte nominal)
            else:
                # Nivel 2: buscar el pronombre en el Greek completo del par CATSS
                # Mejora 2: pasamos stem_morph para que divorce_greek sepa si es verbal
                _, suf_gr = divorce_greek(pair_gr, suf_morph, stem_morph_for_suf)
                if not suf_gr:
                    # Nivel 3: intentar en el gr_word del stem (por si incluye el pronombre)
                    stem_candidate, suf_gr = divorce_greek(
                        hw.get("gr_word", ""), suf_morph, stem_morph_for_suf)
                    if suf_gr:
                        hw["gr_word"] = stem_candidate  # stem queda sin el pronombre

            suf_es = (seg_val(suf_seg, "spanish") or
                      _SUFFIX_TO_ES.get(suf_morph, ""))

            hw["prs_suffix"] = {
                "he_form":  seg_val(suf_seg, "hebrew"),
                "he_morph": suf_morph,
                "es":       normalize_es(suf_es),
                "gr_word":  sanitize_greek(suf_gr),
                "strongs":  seg_val(suf_seg, "strongs"),
            }

        # ── Mejora 2 extra: split verbo-prefijo + sufijo-stem ────────────────
        # Patrón: CATSS codifica como "PREFIX = verbo-infinitivo / STEM = sufijo-W"
        # Ej. HWLYD/W → prefix_forms[k]=הוֹלִיד (verbal), he_form=וֹ (PRS)
        # El snapshot pone el griego completo "τὸ γεννῆσαι αὐτὸν" en el STEM.
        # Movemos la parte verbal al último prefijo verbal y el pronombre al stem.
        for hw in hw_list:
            stem_morph_s = hw.get("he_morph", "")
            if not (stem_morph_s.startswith("PRS") or "+RBS" in stem_morph_s):
                continue
            stem_gr = hw.get("gr_word", "")
            if not stem_gr or len(stem_gr.split()) < 2:
                continue  # frase de 1 palabra — no hay nada que separar
            # Buscar el último prefijo con morph verbal (índice k)
            pfx_morphs = hw.get("prefix_morphs", [])
            pfx_grs    = hw.get("prefix_gr", [])
            verb_pfx_k = None
            for k in range(len(pfx_morphs) - 1, -1, -1):
                if _is_verbal_morph(pfx_morphs[k]):
                    verb_pfx_k = k
                    break
            if verb_pfx_k is None:
                continue  # sin prefijo verbal — no aplica
            # El prefijo verbal ya tiene griego asignado? Si sí, no interferir.
            if pfx_grs[verb_pfx_k]:
                continue
            # Intentar separar el pronombre acusativo del stem griego
            stem_part, pron_part = divorce_greek(stem_gr, stem_morph_s,
                                                 pfx_morphs[verb_pfx_k])
            if not pron_part:
                continue  # no se pudo separar — dejar como está
            # Asignar partes separadas
            hw["prefix_gr"][verb_pfx_k] = stem_part  # parte verbal → prefijo
            hw["gr_word"] = pron_part                 # pronombre → stem (sufijo)

    # ── Corrección 5: eliminar he_words fantasma (artefactos meta-notación CATSS)
    # Un he_word vacío (he_form='', he_morph='', gr_word='', sin prefijos con data)
    # puede provenir de un stem meta como 'p' o '=%p'. Limpiarlo evita tarjetas en blanco.
    for pair in verse.get("pairs", []):
        original = pair.get("he_words", [])
        clean = [
            hw for hw in original
            if (hw.get("he_form")
                or any(f for f in hw.get("prefix_forms", []))
                or hw.get("gr_word"))
        ]
        if len(clean) < len(original):
            pair["he_words"] = clean

    # ── Corrección 6: Fusionar PART.OBJ.DIR prefix + PRS/PRON stem → אֹתוֹ-style ──
    # El marcador de objeto directo אֵת/אֹת con sufijo pronominal es un token unitario
    # en hebreo bíblico (אֹתוֹ, אֹתָהּ, אֹתָם…). Cuando CATSS lo tokeniza como
    # prefijo ')T' + stem 'W', y el snapshot lo tiene como 'אֹתוֹ' (un segmento),
    # se produce una tarjeta extra. Fusionamos ambas en UNA tarjeta.
    for pair in verse.get("pairs", []):
        for hw in pair.get("he_words", []):
            pfx_morphs = hw.get("prefix_morphs", [])
            pfx_forms  = hw.get("prefix_forms",  [])
            stem_morph = hw.get("he_morph", "")
            stem_form  = hw.get("he_form",  "")
            # Patrón: exactamente 1 prefijo PART.OBJ.DIR + stem PRS o PRON.OBJ
            is_prs  = stem_morph.startswith("PRS")
            is_pron = stem_morph == "PRON.OBJ"
            if (len(pfx_morphs) == 1
                    and pfx_morphs[0] == "PART.OBJ.DIR"
                    and (is_prs or is_pron)
                    and pfx_forms[0]):
                # 1. FORMA: si el snapshot tiene la forma combinada como un segmento
                # único (cons_prefijo + cons_stem), usar SU hebreo (con niqqud correcto:
                # אֹתָם con cholam+qamets, NO la concatenación malformada אֶתם).
                snap_lookup = verse.get("_snap_lookup", {})
                prefix_cons = consonants(pfx_forms[0])
                stem_cons_v = consonants(stem_form) if stem_form else ""
                combined_cons = prefix_cons + stem_cons_v
                snap_combined = snap_lookup.get(combined_cons)
                if snap_combined and snap_combined.get("hebrew"):
                    combined = snap_combined["hebrew"]
                else:
                    # Fallback: concatenar (puede quedar malformado como אֶתם)
                    prefix_clean = _MAQAF_RE.sub("", pfx_forms[0])
                    combined = prefix_clean + (stem_form or "")

                # 2. ESPAÑOL: usar tabla _AT_PLUS_SUFFIX_ES = "a ellos / a él / etc"
                # (Strong's H853: אֵת sola no se traduce, pero con suf. = "a + pron")
                new_es = _AT_PLUS_SUFFIX_ES.get(stem_morph, "")
                if not new_es:
                    # Fallback al snapshot o al default OBJ
                    new_es = hw.get("es", "") or _OBJ_MARKER_ES.get(stem_morph, "lo")

                # 3. GRIEGO: usar el del stem (αὐτόν, etc.), o del snapshot
                new_gr = hw.get("gr_word", "")
                if not new_gr and snap_combined and snap_combined.get("gr"):
                    new_gr = snap_combined["gr"]

                # Aplicar
                hw["he_form"]  = combined
                hw["he_morph"] = "PART.OBJ.DIR"
                hw["es"]       = normalize_es(new_es)
                hw["gr_word"]  = sanitize_greek(new_gr or "")
                # Limpiar arrays de prefijo para que no se renderice como tarjeta separada.
                # También limpiar "prefixes" (raw CATSS) para que apply_corrections.py
                # no espere slots de prefijo cuando recorra esta he_word.
                hw["prefixes"]      = []
                hw["prefix_forms"]  = []
                hw["prefix_morphs"] = []
                hw["prefix_es"]     = []
                hw["prefix_gr"]     = []
                hw["prefix_tier"]   = []


    # ── Corrección 11: Recuperación de snaps combinados huérfanos ────────────
    # Si una he_word tiene prefix+stem TODOS sin datos del snapshot pero el snap
    # tiene un segmento combinado (cons_prefijo + cons_stem), recuperar SU info
    # y asignarla al PREFIJO (verbo/sustantivo) y al STEM (sufijo PRS).
    # Esto rescata pares como PAIR 02 (BR)/M=ברא+ם → snap[3]=בראם 'los creó').
    snap_lookup_rec = verse.get("_snap_lookup", {})
    for pair in verse.get("pairs", []):
        for hw in pair.get("he_words", []):
            pfx_forms_r  = hw.get("prefix_forms",  [])
            pfx_morphs_r = hw.get("prefix_morphs", [])
            pfx_es_r     = hw.get("prefix_es",     [])
            pfx_gr_r     = hw.get("prefix_gr",     [])
            if not pfx_forms_r:
                continue
            # Solo 1 prefijo (caso típico verbo+suf, partícula+suf, sust+suf)
            if len(pfx_forms_r) != 1:
                continue
            # ¿El stem es PRS o PRON.OBJ? (caso de combinación)
            stem_morph_r = hw.get("he_morph", "")
            stem_form_r  = hw.get("he_form",  "")
            if not (stem_morph_r.startswith("PRS") or stem_morph_r == "PRON.OBJ"):
                continue
            # ¿Está empty el prefijo (no recibió datos del snapshot)?
            pfx_es_empty = not pfx_es_r[0]
            pfx_gr_empty = not pfx_gr_r[0]
            if not (pfx_es_empty and pfx_gr_empty):
                continue
            # Buscar combined en el snapshot lookup
            prefix_cons_r = consonants(pfx_forms_r[0])
            stem_cons_r   = consonants(stem_form_r)
            combined_cons_r = prefix_cons_r + stem_cons_r
            snap_combo_r = snap_lookup_rec.get(combined_cons_r)
            if not snap_combo_r:
                continue
            # Tenemos el snap combinado. Asignar datos.
            combo_es_r    = (snap_combo_r.get("es")    or "").strip()
            combo_gr_r    = (snap_combo_r.get("gr")    or "").strip()
            combo_morph_r = (snap_combo_r.get("morph") or "").strip()
            combo_he_r    = (snap_combo_r.get("hebrew")or "").strip()
            # Si el snap tiene es combinada tipo "los creó", dividir.
            es_verbal, es_pron = split_combined_es(combo_es_r) if combo_es_r else ("","")
            # Asignar al PREFIJO la parte verbal/nominal del snapshot.
            if es_verbal and not pfx_es_r[0]:
                pfx_es_r[0] = es_verbal
            if combo_gr_r and not pfx_gr_r[0]:
                pfx_gr_r[0] = combo_gr_r
            # Si el snapshot tiene morph "específica" para el prefijo
            # (sin compound +R*), usarla; si es compound (V*+R*), normalize_morph
            # la mantendrá compound y la Corrección 7 se encargará.
            if combo_morph_r and pfx_morphs_r[0] in ("", None):
                # Quitar el sufijo "+R*P*" del morph para que quede solo el verbo/sust
                base_morph = combo_morph_r.split("+")[0]
                pfx_morphs_r[0] = base_morph
            # Si el snapshot tiene un pronombre dividido (es_pron), úsalo para el stem.
            # Si NO, dejar el default ya asignado (lo/la/los/etc).
            if es_pron and not hw.get("es"):
                hw["es"] = es_pron

    # ── Corrección 7: VERBAL prefix + PRS stem → stem promovido + prs_suffix ──
    # Cuando CATSS tokeniza VerboPrefijo/SufijoPronom (ej. HBR)/M, BR)/M),
    # la Mejora 2 extra ya asigna el griego correcto a cada parte, pero ambas
    # siguen siendo tarjetas separadas. Esta corrección:
    #   1. Promueve el prefijo verbal → nuevo stem principal
    #   2. Mueve el stem PRS → prs_suffix mini-row
    # Basado en: modulo_sufijos_pronominales_sobre_verbos (reglas gramaticales.txt)
    # El sufijo verbal expresa el objeto directo de la acción (no posesión).
    for pair in verse.get("pairs", []):
        for hw in pair.get("he_words", []):
            pfx_morphs = hw.get("prefix_morphs", [])
            pfx_forms  = hw.get("prefix_forms",  [])
            pfx_es     = hw.get("prefix_es",     [])
            pfx_gr     = hw.get("prefix_gr",     [])
            stem_morph = hw.get("he_morph", "")
            stem_form  = hw.get("he_form",  "")
            stem_gr    = hw.get("gr_word",  "")

            # Evitar doble-procesamiento: si ya tiene prs_suffix, saltar
            if hw.get("prs_suffix"):
                continue

            # El stem debe ser PRS (sufijo objeto) o PRON.OBJ
            is_prs  = stem_morph.startswith("PRS")
            is_pron = stem_morph == "PRON.OBJ"
            if not (is_prs or is_pron):
                continue

            # Buscar el ÚLTIMO prefijo verbal
            verb_pfx_k = None
            for k in range(len(pfx_morphs) - 1, -1, -1):
                if _is_verbal_morph(pfx_morphs[k]):
                    verb_pfx_k = k
                    break
            if verb_pfx_k is None:
                continue

            verb_form  = pfx_forms[verb_pfx_k] if verb_pfx_k < len(pfx_forms)  else ""
            verb_morph = pfx_morphs[verb_pfx_k] if verb_pfx_k < len(pfx_morphs) else ""
            verb_es    = pfx_es[verb_pfx_k]     if verb_pfx_k < len(pfx_es)     else ""
            verb_gr    = pfx_gr[verb_pfx_k]     if verb_pfx_k < len(pfx_gr)     else ""

            if not verb_form:
                continue  # sin forma = no hay que fusionar

            # Limpiar maqaf antes de promover (mantener nikud y shin/sin dots)
            verb_form = _MAQAF_RE.sub("", verb_form)
            if not verb_form:
                continue

            # Determinar tipo de pronombre según voz del verbo:
            # - Activo (Qal/Piel/Hifil…): sufijo es OBJETO → "los/lo/te/etc"
            # - Pasivo (Niphal/Hofal): sufijo es SUJETO → "ellos/él/tú/etc"
            verb_morph_norm = normalize_morph(verb_morph)
            is_passive_verb = ('NIF' in verb_morph_norm or 'HOF' in verb_morph_norm)
            if is_passive_verb:
                prs_es = (_SUBJ_MARKER_ES.get(stem_morph)
                          or _SUFFIX_TO_ES.get(stem_morph, ""))
            else:
                prs_es = (_OBJ_MARKER_ES.get(stem_morph)
                          or _SUFFIX_TO_ES.get(stem_morph, ""))

            # ─── Fix Gen 5:2: rescatar glosa combinada del snapshot ──────────
            # Cuando el snapshot trae verbo+sufijo como UN solo segmento con
            # es="los creó", el match consonántico falla en ambos lados (verbo
            # CATSS ברא vs snap בראם, y stem CATSS ם vs snap בראם).
            # Solución: consultar el lookup snapshot por cons_combinadas
            # (verb_cons + suffix_cons) y dividir la glosa combinada.
            if not verb_es:
                snap_lookup = verse.get("_snap_lookup", {})
                verb_cons   = consonants(verb_form)
                stem_cons   = consonants(stem_form) if stem_form else ""
                combined_cons = verb_cons + stem_cons
                snap_combo = snap_lookup.get(combined_cons)
                if snap_combo:
                    combo_es = (snap_combo.get("es") or "").strip()
                    if combo_es:
                        verbal_part, pron_part = split_combined_es(combo_es)
                        if verbal_part:
                            verb_es = verbal_part
                        # Solo sobrescribir prs_es si dividimos un pronombre objeto
                        # Y el verbo NO es pasivo (en pasivo el sujeto manda).
                        if pron_part and not is_passive_verb:
                            prs_es = pron_part
                    # Bonus: si el griego del verbo también está vacío, rescatar
                    if not verb_gr and snap_combo.get("gr"):
                        verb_gr = snap_combo["gr"]

            # Completar glosa pasiva truncada ("fueron" → "fueron creados")
            verb_es = complete_passive_gloss(verb_es, verb_morph_norm, verb_form)

            # Promover prefijo verbal → stem principal
            hw["he_form"]  = verb_form
            hw["he_morph"] = verb_morph
            hw["es"]       = normalize_es(verb_es)
            hw["gr_word"]  = sanitize_greek(verb_gr)

            # PRS → prs_suffix mini-row
            hw["prs_suffix"] = {
                "he_form":  stem_form,
                "he_morph": stem_morph,
                "es":       normalize_es(prs_es),
                "gr_word":  sanitize_greek(stem_gr),
                "strongs":  "",
            }

            # Eliminar el prefijo verbal de los arrays de prefijo
            for lst_name in ("prefix_forms", "prefix_morphs", "prefix_es",
                             "prefix_gr", "prefix_tier"):
                arr = hw.get(lst_name, [])
                if verb_pfx_k < len(arr):
                    del arr[verb_pfx_k]

            # Si el prefijo era el único, también limpiar la lista raw 'prefixes'
            # para que apply_corrections no espere slots extra
            if not hw.get("prefix_forms"):
                hw["prefixes"] = [p for i, p in enumerate(hw.get("prefixes", []))
                                  if i != verb_pfx_k]

    # ── Corrección 8: SUBS/NOUN prefix + PRS stem → sustantivo con sufijo posesivo ─
    # Patrón: CATSS tokeniza un sustantivo+sufijo como PREFIX=שמ STEM=ם
    # (ej. PAIR 06 שְׁמָם = "su nombre"). La Corrección 7 no actuó porque
    # el prefijo no es verbal. Aquí se fusionan en una sola tarjeta.
    # Basado en: logica_sufijos_pronominales_sustantivos (reglas gramaticales.txt)
    _NOUN_MORPH_STARTS = ("SUBS", "NOUN", "NASC", "NPROP", "NC",
                          "ADJ", "PTCL.REL")
    for pair in verse.get("pairs", []):
        for hw in pair.get("he_words", []):
            # Saltar si ya fue tratado por C7 o ya tiene prs_suffix
            if hw.get("prs_suffix"):
                continue

            pfx_morphs = hw.get("prefix_morphs", [])
            pfx_forms  = hw.get("prefix_forms",  [])
            pfx_es     = hw.get("prefix_es",     [])
            pfx_gr     = hw.get("prefix_gr",     [])
            stem_morph = hw.get("he_morph", "")
            stem_form  = hw.get("he_form",  "")
            stem_gr    = hw.get("gr_word",  "")

            is_prs  = stem_morph.startswith("PRS")
            if not is_prs:
                continue

            # Solo si el stem actual está vacío / es puro sufijo
            # (si ya tiene una forma sustantiva real, no tocar)
            if stem_form and not (len(stem_form) <= 2):
                continue  # stem tiene forma compleja, ignorar

            # Buscar el ÚLTIMO prefijo nominal
            noun_pfx_k = None
            for k in range(len(pfx_morphs) - 1, -1, -1):
                if any(pfx_morphs[k].startswith(s) for s in _NOUN_MORPH_STARTS):
                    noun_pfx_k = k
                    break
            if noun_pfx_k is None:
                continue

            noun_form  = pfx_forms[noun_pfx_k] if noun_pfx_k < len(pfx_forms)  else ""
            noun_morph = pfx_morphs[noun_pfx_k] if noun_pfx_k < len(pfx_morphs) else ""
            noun_gr    = pfx_gr[noun_pfx_k]     if noun_pfx_k < len(pfx_gr)     else ""
            noun_es    = pfx_es[noun_pfx_k]     if noun_pfx_k < len(pfx_es)     else ""

            if not noun_form:
                continue

            # Limpiar maqaf antes de promover (mantener nikud y shin/sin dots)
            noun_form = _MAQAF_RE.sub("", noun_form)
            if not noun_form:
                continue

            prs_es = (_SUFFIX_TO_ES.get(stem_morph, ""))

            # Promover prefijo nominal → stem principal
            hw["he_form"]  = noun_form
            hw["he_morph"] = noun_morph
            hw["es"]       = normalize_es(noun_es)
            hw["gr_word"]  = sanitize_greek(noun_gr or "")

            # PRS → prs_suffix mini-row
            hw["prs_suffix"] = {
                "he_form":  stem_form,
                "he_morph": stem_morph,
                "es":       normalize_es(prs_es),
                "gr_word":  sanitize_greek(stem_gr),
                "strongs":  "",
            }

            # Eliminar el prefijo nominal de los arrays
            for lst_name in ("prefix_forms", "prefix_morphs", "prefix_es",
                             "prefix_gr", "prefix_tier"):
                arr = hw.get(lst_name, [])
                if noun_pfx_k < len(arr):
                    del arr[noun_pfx_k]

            if not hw.get("prefix_forms"):
                hw["prefixes"] = [p for i, p in enumerate(hw.get("prefixes", []))
                                  if i != noun_pfx_k]

    # Limpiar lookup temporal (no debe persistir en el JSON final)
    if "_snap_lookup" in verse:
        del verse["_snap_lookup"]

    # ── Corrección 13: Reglas de auditoría conservadora (Génesis) ────────────
    # Aditiva, después de Correcciones 1-11 y antes del safety-net (9).
    # Solo modifica `es` y `gr_word` en casos exactos de tablas cerradas, con
    # marca `es_source` / `gr_source` para trazabilidad.
    apply_audit_rules(verse)

    # ── Corrección 14: Fusión PREP+PRS cortos (partículas de ≤3 consonantes) ─
    # Aditiva. Solo modifica he_words donde prep+prs forman partícula ≤3 letras.
    # No toca _snap_match, merge_verse, divorce_greek ni Correcciones 1-11.
    _apply_correction_14_short_prep_prs(verse)

    # ── Corrección 9: Validador de alfabeto en campos español (safety-net) ───
    # Si por cualquier ruta de fallback un campo `es` quedó con caracteres
    # griegos (rangos U+0370-03FF o U+1F00-1FFF), significa que hubo un desfase
    # de índices entre fuentes. En ese caso:
    #   1. Mover el texto griego al campo gr_word (si está vacío)
    #   2. Limpiar el campo es a "" (mejor vacío que mostrar griego en español)
    for pair in verse.get("pairs", []):
        for hw in pair.get("he_words", []):
            # Stem
            es_v = hw.get("es", "")
            if es_has_greek(es_v):
                if not hw.get("gr_word"):
                    hw["gr_word"] = sanitize_greek(es_v)
                hw["es"] = ""
            # Prefijos
            for k, pe in enumerate(hw.get("prefix_es", [])):
                if es_has_greek(pe):
                    if k < len(hw.get("prefix_gr", [])) and not hw["prefix_gr"][k]:
                        hw["prefix_gr"][k] = sanitize_greek(pe)
                    hw["prefix_es"][k] = ""
            # PRS suffix mini-row
            sfx = hw.get("prs_suffix")
            if isinstance(sfx, dict) and es_has_greek(sfx.get("es", "")):
                if not sfx.get("gr_word"):
                    sfx["gr_word"] = sanitize_greek(sfx["es"])
                sfx["es"] = ""


# ════════════════════════════════════════════════════════════════════════════
#  CORRECCIÓN 14 — Fusión PREP+PRS cortos en una sola tarjeta
# ════════════════════════════════════════════════════════════════════════════
#
# Partículas preposicionales declinadas de ≤3 consonantes que el parser OSHB
# desglosa en dos slots (prefijo PREP + stem PRS vacío). Se fusionan en UNA
# sola he_word con morph combinado PREP+PRS.X.Y.Z y español completo.
#
# Restricciones: NO toca _snap_match, merge_verse, divorce_greek ni C1-C11.
# Solo modifica `he_form`, `he_morph`, `es`, `gr_word` del he_word afectado
# y limpia los arrays de prefijo.

# Formato: { consonantes_planas: (prep_es, sufijo_es, morph_combinado) }
_SHORT_PREP_PRS = {
    # ב + sufijos
    'בו':  ('en', 'él',        'PREP+PRS.P3.M.SG'),
    'בה':  ('en', 'ella',      'PREP+PRS.P3.F.SG'),
    'בי':  ('en', 'mí',        'PREP+PRS.P1.SG'),
    'בך':  ('en', 'ti',        'PREP+PRS.P2.M.SG'),
    'בם':  ('en', 'ellos',     'PREP+PRS.P3.M.PL'),
    'בן':  ('en', 'ellas',     'PREP+PRS.P3.F.PL'),
    'בנו': ('en', 'nosotros',  'PREP+PRS.P1.PL'),
    # ל + sufijos
    'לו':  ('para', 'él',        'PREP+PRS.P3.M.SG'),
    'לה':  ('para', 'ella',      'PREP+PRS.P3.F.SG'),
    'לי':  ('a', 'mí',           'PREP+PRS.P1.SG'),
    'לך':  ('a', 'ti',           'PREP+PRS.P2.M.SG'),
    'לם':  ('para', 'ellos',     'PREP+PRS.P3.M.PL'),
    'לנו': ('para', 'nosotros',  'PREP+PRS.P1.PL'),
    # כ + sufijos
    'כו':  ('como', 'él',     'PREP+PRS.P3.M.SG'),
    'כה':  ('como', 'ella',   'PREP+PRS.P3.F.SG'),
    'כם':  ('como', 'ellos',  'PREP+PRS.P3.M.PL'),
    # מ + sufijos (casos cortos)
    'מנו': ('de', 'nosotros', 'PREP+PRS.P1.PL'),
}


def _apply_correction_14_short_prep_prs(verse: dict) -> None:
    """Fusiona PREP+PRS cortos en una sola tarjeta cuando forman partícula de ≤3 consonantes."""
    for pair in verse.get('pairs', []):

        # ── CASO A: stem con prefijo PREP, consonantes combinadas en tabla ───
        for hw in pair.get('he_words', []):
            pmorphs = hw.get('prefix_morphs', [])
            pforms  = hw.get('prefix_forms',  [])
            if not pmorphs or pmorphs[-1] != 'PREP':
                continue
            stem_cons = consonants(hw.get('he_form', ''))
            prep_cons = consonants(pforms[-1] if pforms else '')
            combined  = prep_cons + stem_cons
            if combined not in _SHORT_PREP_PRS:
                continue
            prep_es, suf_es, combined_morph = _SHORT_PREP_PRS[combined]
            # Forma combinada: prefix_form (sin maqaf) + stem_form
            prep_form_clean = _MAQAF_RE.sub('', pforms[-1])
            hw['he_form']   = prep_form_clean + (hw.get('he_form') or '')
            hw['he_morph']  = combined_morph
            hw['es']        = f'{prep_es} {suf_es}'
            hw['es_source'] = 'short_prep_prs_fusion'
            # Proteger gr_word vacío para evitar clonado por Corrección 2
            if not hw.get('gr_word'):
                hw['gr_word']   = '---'
                hw['gr_source'] = 'prep_prs_no_equiv'
            # Eliminar el prefijo PREP (absorbido en el stem)
            hw['prefixes']      = hw.get('prefixes',      [])[:-1]
            hw['prefix_forms']  = hw.get('prefix_forms',  [])[:-1]
            hw['prefix_morphs'] = hw.get('prefix_morphs', [])[:-1]
            hw['prefix_es']     = hw.get('prefix_es',     [])[:-1]
            hw['prefix_gr']     = hw.get('prefix_gr',     [])[:-1]
            if 'prefix_tier' in hw:
                hw['prefix_tier'] = hw['prefix_tier'][:-1]

        # ── CASO B: dos he_words consecutivos PREP + PRS dentro del mismo pair
        hw_list = pair.get('he_words', [])
        i = 0
        while i < len(hw_list) - 1:
            h1, h2 = hw_list[i], hw_list[i + 1]
            if (h1.get('he_morph') == 'PREP'
                    and h2.get('he_morph', '').startswith('PRS')):
                c1 = consonants(h1.get('he_form', ''))
                c2 = consonants(h2.get('he_form', ''))
                combined = c1 + c2
                if combined in _SHORT_PREP_PRS:
                    prep_es, suf_es, cmb_morph = _SHORT_PREP_PRS[combined]
                    h2['he_form']   = h1.get('he_form', '') + h2.get('he_form', '')
                    h2['he_morph']  = cmb_morph
                    h2['es']        = f'{prep_es} {suf_es}'
                    h2['es_source'] = 'short_prep_prs_fusion'
                    if not h2.get('gr_word'):
                        h2['gr_word']   = '---'
                        h2['gr_source'] = 'prep_prs_no_equiv'
                    hw_list.pop(i)  # eliminar h1 (PREP sola)
                    continue        # no incrementar i
            i += 1


# ════════════════════════════════════════════════════════════════════════════
#  CORRECCIÓN 13 — Reglas de auditoría conservadora (Génesis cap. 1 baseline)
# ════════════════════════════════════════════════════════════════════════════
#
# Aditiva al final del post_process_verse. NUNCA toca _snap_match, merge_verse,
# divorce_greek ni las Correcciones 1-11. Solo modifica `es` y `gr_word` (con
# su correspondiente `es_source` / `gr_source`) en casos exactos definidos por
# tablas cerradas.
#
# Restricciones:
#   - Solo procesa Génesis (la pipeline ya lo hace, pero verificamos por book).
#   - Cada regla es independiente: si una falla en un token, sigue con el resto.
#   - Conservador: en caso de duda, NO marcar.
#
# ── Logging ──────────────────────────────────────────────────────────────────
# Se acumulan líneas en _AUDIT_LOG_LINES y conteos en _AUDIT_COUNTERS.
# main() escribe el log final a data/audit_log_<timestamp>.txt.

_AUDIT_LOG_LINES: list = []
_AUDIT_COUNTERS: dict = {'A': 0, 'B': 0, 'D': 0, 'E': 0}
_AUDIT_EXAMPLES: dict = {'A': [], 'B': [], 'D': [], 'E': []}
_AUDIT_FORM_BREAKDOWN: dict = {'A': {}, 'E': {}}

# ── Regla A: Conjugación verbal según aspecto/persona/género/número ─────────
# Tabla cerrada: solo verbos frecuentes en Génesis con aspectos comunes.
# Lemma normalizado → forma conjugada.

_LEMMA_INF_NORM: dict = {
    # Lemma original (snapshot) → lemma normalizado para tabla
    'ser':       'ser',
    'estar':     'ser',     # sinónimo: comparten conjugación de "ser/estar"
    'decir':     'decir',
    'ver':       'ver',
    'llamar':    'llamar',
    'hacer':     'hacer',
    'crear':     'crear',
    'separar':   'separar',
    'dividir':   'separar', # sinónimo: ambos vienen de H914 (בדל)
    'dar':       'dar',
    'bendecir':  'bendecir',
}

# (lemma, aspecto, persona, género, número) → forma_conjugada_es
# Fuente: tabla provista por el usuario (auditoría manual cap. 1)
_CONJUG_TABLE: dict = {
    # ─── ser / estar ─────────────────────────────────────────────────────
    ('ser',      'WAYYIQT', 'P3', 'M', 'SG'): 'fue',
    ('ser',      'WAYYIQT', 'P3', 'F', 'SG'): 'fue',
    ('ser',      'WAYYIQT', 'P3', 'M', 'PL'): 'fueron',
    ('ser',      'PERF',    'P3', 'M', 'SG'): 'fue',
    ('ser',      'IMPF',    'P3', 'M', 'SG'): 'será',
    ('ser',      'JUSS',    'P3', 'M', 'SG'): 'sea',
    ('ser',      'IMPV',    'P2', 'M', 'SG'): 'sé',
    # ─── decir ───────────────────────────────────────────────────────────
    ('decir',    'WAYYIQT', 'P3', 'M', 'SG'): 'dijo',
    ('decir',    'WAYYIQT', 'P3', 'F', 'SG'): 'dijo',
    ('decir',    'WAYYIQT', 'P3', 'M', 'PL'): 'dijeron',
    ('decir',    'PERF',    'P3', 'M', 'SG'): 'dijo',
    ('decir',    'IMPF',    'P3', 'M', 'SG'): 'dirá',
    ('decir',    'JUSS',    'P3', 'M', 'SG'): 'diga',
    ('decir',    'IMPV',    'P2', 'M', 'SG'): 'di',
    # ─── ver ─────────────────────────────────────────────────────────────
    ('ver',      'WAYYIQT', 'P3', 'M', 'SG'): 'vio',
    ('ver',      'WAYYIQT', 'P3', 'F', 'SG'): 'vio',
    ('ver',      'WAYYIQT', 'P3', 'M', 'PL'): 'vieron',
    ('ver',      'PERF',    'P3', 'M', 'SG'): 'vio',
    ('ver',      'IMPF',    'P3', 'M', 'SG'): 'verá',
    ('ver',      'JUSS',    'P3', 'M', 'SG'): 'vea',
    ('ver',      'IMPV',    'P2', 'M', 'SG'): 'mira',
    # ─── llamar ──────────────────────────────────────────────────────────
    ('llamar',   'WAYYIQT', 'P3', 'M', 'SG'): 'llamó',
    ('llamar',   'WAYYIQT', 'P3', 'F', 'SG'): 'llamó',
    ('llamar',   'WAYYIQT', 'P3', 'M', 'PL'): 'llamaron',
    ('llamar',   'PERF',    'P3', 'M', 'SG'): 'llamó',
    ('llamar',   'IMPF',    'P3', 'M', 'SG'): 'llamará',
    ('llamar',   'JUSS',    'P3', 'M', 'SG'): 'llame',
    ('llamar',   'IMPV',    'P2', 'M', 'SG'): 'llama',
    # ─── hacer ───────────────────────────────────────────────────────────
    ('hacer',    'WAYYIQT', 'P3', 'M', 'SG'): 'hizo',
    ('hacer',    'WAYYIQT', 'P3', 'F', 'SG'): 'hizo',
    ('hacer',    'WAYYIQT', 'P3', 'M', 'PL'): 'hicieron',
    ('hacer',    'PERF',    'P3', 'M', 'SG'): 'hizo',
    ('hacer',    'IMPF',    'P3', 'M', 'SG'): 'hará',
    ('hacer',    'JUSS',    'P3', 'M', 'SG'): 'haga',
    ('hacer',    'IMPV',    'P2', 'M', 'SG'): 'haz',
    # ─── crear ───────────────────────────────────────────────────────────
    ('crear',    'WAYYIQT', 'P3', 'M', 'SG'): 'creó',
    ('crear',    'WAYYIQT', 'P3', 'F', 'SG'): 'creó',
    ('crear',    'WAYYIQT', 'P3', 'M', 'PL'): 'crearon',
    ('crear',    'PERF',    'P3', 'M', 'SG'): 'creó',
    ('crear',    'IMPF',    'P3', 'M', 'SG'): 'creará',
    ('crear',    'JUSS',    'P3', 'M', 'SG'): 'cree',
    ('crear',    'IMPV',    'P2', 'M', 'SG'): 'crea',
    # ─── separar / dividir ───────────────────────────────────────────────
    ('separar',  'WAYYIQT', 'P3', 'M', 'SG'): 'separó',
    ('separar',  'WAYYIQT', 'P3', 'F', 'SG'): 'separó',
    ('separar',  'WAYYIQT', 'P3', 'M', 'PL'): 'separaron',
    ('separar',  'PERF',    'P3', 'M', 'SG'): 'separó',
    ('separar',  'IMPF',    'P3', 'M', 'SG'): 'separará',
    ('separar',  'JUSS',    'P3', 'M', 'SG'): 'separe',
    ('separar',  'IMPV',    'P2', 'M', 'SG'): 'separa',
    # ─── dar ─────────────────────────────────────────────────────────────
    ('dar',      'WAYYIQT', 'P3', 'M', 'SG'): 'dio',
    ('dar',      'WAYYIQT', 'P3', 'F', 'SG'): 'dio',
    ('dar',      'WAYYIQT', 'P3', 'M', 'PL'): 'dieron',
    ('dar',      'PERF',    'P3', 'M', 'SG'): 'dio',
    ('dar',      'IMPF',    'P3', 'M', 'SG'): 'dará',
    ('dar',      'JUSS',    'P3', 'M', 'SG'): 'dé',
    ('dar',      'IMPV',    'P2', 'M', 'SG'): 'da',
    # ─── bendecir ────────────────────────────────────────────────────────
    ('bendecir', 'WAYYIQT', 'P3', 'M', 'SG'): 'bendijo',
    ('bendecir', 'WAYYIQT', 'P3', 'F', 'SG'): 'bendijo',
    ('bendecir', 'WAYYIQT', 'P3', 'M', 'PL'): 'bendijeron',
    ('bendecir', 'PERF',    'P3', 'M', 'SG'): 'bendijo',
    ('bendecir', 'IMPF',    'P3', 'M', 'SG'): 'bendecirá',
    ('bendecir', 'JUSS',    'P3', 'M', 'SG'): 'bendiga',
    ('bendecir', 'IMPV',    'P2', 'M', 'SG'): 'bendice',
}


def _parse_verb_morph(morph: str) -> tuple:
    """
    Devuelve (aspecto, persona, género, número) a partir de un VERBO.* morph.
    Ejemplo: 'VERBO.QAL.WAYYIQT.P3.M.SG' → ('WAYYIQT', 'P3', 'M', 'SG')
    Si falta algo o no es VERBO, retorna tupla con vacíos.
    """
    if not morph or not morph.startswith('VERBO.'):
        return ('', '', '', '')
    parts = morph.split('.')
    # parts[0]='VERBO', parts[1]=stem (QAL/HIF/...), parts[2]=aspecto
    if len(parts) < 3:
        return ('', '', '', '')
    aspect = parts[2]
    person = ''
    gender = ''
    number = ''
    for p in parts[3:]:
        if p in ('P1', 'P2', 'P3') and not person:
            person = p
        elif p in ('M', 'F', 'C', 'COMMON', 'BOTH') and not gender:
            # Normalizamos 'C'→'COMMON' (raro en VERBO) por simetría
            gender = 'COMMON' if p == 'C' else p
        elif p in ('SG', 'PL', 'DU') and not number:
            number = p
    return (aspect, person, gender, number)


def _normalize_es_lemma(es: str) -> str:
    """Normaliza la glosa española al lemma usado en _CONJUG_TABLE."""
    es_low = (es or '').strip().lower()
    return _LEMMA_INF_NORM.get(es_low, '')


def _apply_rule_A(hw: dict, p_idx: int, w_idx: int,
                  chap: int, vrs: int) -> None:
    """Regla A: conjuga verbos cuyo `es` es lemma infinitivo y el morph indica
    aspecto verbal específico (WAYYIQT, PERF, IMPF, JUSS, IMPV).

    Solo aplica si:
      - hw.es está en _LEMMA_INF_NORM (closed list)
      - hw.he_morph empieza con 'VERBO.'
      - (lemma_norm, aspecto, persona, género, número) está en _CONJUG_TABLE
      - La forma conjugada difiere de hw.es actual (idempotencia)
    """
    morph = hw.get('he_morph', '')
    if not morph.startswith('VERBO.'):
        return
    es = hw.get('es', '')
    lemma = _normalize_es_lemma(es)
    if not lemma:
        return
    aspect, person, gender, number = _parse_verb_morph(morph)
    if not (aspect and person and gender and number):
        return
    key = (lemma, aspect, person, gender, number)
    conj = _CONJUG_TABLE.get(key)
    if not conj or conj == es:
        return
    old_es = es
    hw['es'] = conj
    hw['es_source'] = 'verb_conjugation'
    _AUDIT_COUNTERS['A'] += 1
    line = (f"{chap}:{vrs} {p_idx}.{w_idx} regla=A "
            f"es={old_es!r}->{conj!r} (morph={morph}, form={hw.get('he_form','')})")
    _AUDIT_LOG_LINES.append(line)
    if len(_AUDIT_EXAMPLES['A']) < 5:
        _AUDIT_EXAMPLES['A'].append(line)
    fb = _AUDIT_FORM_BREAKDOWN['A']
    fb[(old_es, conj)] = fb.get((old_es, conj), 0) + 1


# ── Regla B: marcar `---` cuando LXX omite el elemento hebreo ──────────────
# Solo se aplica al STEM principal (he_morph) cuando:
#   - el morph es SUBS / VERBO / ADJ / NUM (núcleos léxicos, no partículas)
#   - hw.gr_word está vacío
#   - el `pair_gr` ya fue distribuido entre OTROS tokens del mismo pair
#     (verificable: existe al menos un he_word con gr_word real, o cualquier
#     prefix_gr no vacío)
#   - el token NO es PRS, NO es PART.OBJ.DIR, y tiene he_form no vacío

_RULE_B_MORPH_PREFIXES = ('SUBS', 'VERBO', 'ADJ', 'NUM')

def _has_real_greek(s: str) -> bool:
    """True si la cadena tiene contenido griego válido (no vacío, no '---', no '—')."""
    if not s:
        return False
    s = s.strip()
    return bool(s) and s not in ('---', '—', '–', '-')


# ── Helpers fix BD (Regla B): detección de griego libre en el pair ─────────
_GR_PUNCT = '.,·;:·;«»“”"\'()[]'

def _norm_gr_token(s: str) -> str:
    """Normaliza un token griego para comparación: strip puntuación, strip
    diacríticos y lowercase. Conservador: si la entrada es vacía o un guion,
    devuelve cadena vacía."""
    if not s:
        return ''
    s = s.strip().strip(_GR_PUNCT)
    if not s or s in ('---', '—', '–', '-', '?'):
        return ''
    return _strip_gr_diacritics(s).lower()


def _gather_assigned_gr(pair: dict) -> set:
    """Recolecta todos los tokens griegos ya asignados (no vacíos, no ---)
    a he_words del pair: gr_word, prefix_gr, prs_suffix.gr_word.
    Devuelve un set de surface forms normalizados (sin diacríticos, minúsculas).
    """
    assigned: set = set()
    for hw in pair.get('he_words', []) or []:
        gw = hw.get('gr_word', '') or ''
        if gw and gw not in ('---', '—', '–', '-'):
            for tok in gw.split():
                n = _norm_gr_token(tok)
                if n:
                    assigned.add(n)
        for pgw in (hw.get('prefix_gr') or []):
            if pgw and pgw not in ('---', '—', '–', '-'):
                for tok in pgw.split():
                    n = _norm_gr_token(tok)
                    if n:
                        assigned.add(n)
        sfx = hw.get('prs_suffix') or {}
        if isinstance(sfx, dict):
            sw = sfx.get('gr_word', '') or ''
            if sw and sw not in ('---', '—', '–', '-'):
                for tok in sw.split():
                    n = _norm_gr_token(tok)
                    if n:
                        assigned.add(n)
    return assigned


def _pair_has_free_greek(pair: dict) -> bool:
    """True si quedan lemmas griegos del pair sin asignar a ningún he_word.

    Iteración sobre `pair.gr_tokens` (autoridad léxica): para cada token,
    se verifica que su forma superficial (`word`) o su lema (`lemma_unicode`)
    aparezca en el set de surface forms ya asignadas a algún he_word del
    mismo pair. Si NINGUNO de los dos está en `assigned`, el lemma quedó
    huérfano → la LXX *sí* tiene el griego pero el motor de alineación lo
    dejó sin asignar → NO es omisión LXX y NO se debe marcar.

    Notas:
      - `gtok['word']` viene en BETA-code CATSS (ej. 'A)RXH=|') mientras
        `assigned` contiene Unicode (ej. 'αρχη'); por construcción la
        primera condición casi siempre se cumple, dejando la decisión al
        chequeo del lema.
      - `lemma_unicode` es la forma canónica (no flexionada) — se compara
        contra surface forms de `assigned`. Coincide cuando el lema es
        invariable (preposiciones, conjunciones, artículos) o cuando el
        surface se da en su forma de lema.
    """
    assigned = _gather_assigned_gr(pair)
    for gtok in pair.get('gr_tokens', []) or []:
        word = _norm_gr_token(gtok.get('word', '') or '')
        lemma = _norm_gr_token(gtok.get('lemma_unicode', '') or '')
        if word and word not in assigned:
            if not lemma or lemma not in assigned:
                return True
    return False


def _apply_rule_B(pair: dict, chap: int, vrs: int, p_idx: int) -> None:
    """Regla B: asigna `gr_word='---'` con `gr_source='lxx_omission'` a stems
    léxicos cuyo griego quedó vacío PERO el pair_gr ya fue distribuido a otros
    tokens del pair. Conservador: requiere he_form no vacío.

    Guard fix BD: NO marcar si quedan lemmas griegos del pair sin asignar a
    ningún he_word. Si hay griego libre, el motor de alineación falló — no
    es omisión LXX y no se debe marcar nada.
    """
    if pair.get('kind') in ('gk_add', 'heb_omit'):
        return
    hw_list = pair.get('he_words', [])
    if not hw_list:
        return
    pair_gr = (pair.get('gr_unicode', '') or '').strip()
    if not pair_gr:
        return  # sin griego del par → caso distinto, no aplicar Regla B
    # ¿algún token del pair tiene griego real ya?
    has_distributed = False
    for hw in hw_list:
        if _has_real_greek(hw.get('gr_word', '')):
            has_distributed = True
            break
        for g in hw.get('prefix_gr', []) or []:
            if _has_real_greek(g):
                has_distributed = True
                break
        if has_distributed:
            break
        sfx = hw.get('prs_suffix') or {}
        if isinstance(sfx, dict) and _has_real_greek(sfx.get('gr_word', '')):
            has_distributed = True
            break
    if not has_distributed:
        return  # pair_gr aún no distribuido — esto es un caso de Corrección 2

    # ── Fix BD: guard de griego libre ────────────────────────────────────────
    # Si quedan surface forms de pair.gr_unicode sin asignar, el motor de
    # alineación dejó griego huérfano. NO marcar nada como omisión LXX,
    # tanto para stems como para prefijos (la regla B nunca toca prefix_gr,
    # pero el guard a nivel de pair los cubre por si la lógica evoluciona).
    if _pair_has_free_greek(pair):
        return

    for w_idx, hw in enumerate(hw_list):
        morph = hw.get('he_morph', '') or ''
        if not any(morph.startswith(s) for s in _RULE_B_MORPH_PREFIXES):
            continue
        if morph.startswith('PRS') or morph == 'PART.OBJ.DIR':
            continue
        if not hw.get('he_form'):
            continue
        gr = (hw.get('gr_word', '') or '').strip()
        if gr:
            continue  # ya tiene griego (real o '---')
        # Saltar si tiene prs_suffix con griego (el griego puede estar dividido)
        sfx = hw.get('prs_suffix') or {}
        if isinstance(sfx, dict) and _has_real_greek(sfx.get('gr_word', '')):
            continue
        hw['gr_word'] = '---'
        hw['gr_source'] = 'lxx_omission'
        _AUDIT_COUNTERS['B'] += 1
        line = (f"{chap}:{vrs} {p_idx}.{w_idx} regla=B "
                f"gr_word=''->'---' (morph={morph}, form={hw.get('he_form','')!r})")
        _AUDIT_LOG_LINES.append(line)
        if len(_AUDIT_EXAMPLES['B']) < 5:
            _AUDIT_EXAMPLES['B'].append(line)


# ── Regla D: fusión de duplicados adyacentes con sólo uno con griego ─────────
# Únicamente DENTRO del mismo pair.he_words[]. NO fusiona entre pairs.

def _norm_heb_dup(s: str) -> str:
    """Normaliza para comparar duplicados: solo consonantes (sin niqud,
    cantilación, maqaf). Reutiliza consonants() ya definida."""
    return consonants(s or '')


def _merge_consumed_into_kept(kept: dict, consumed: dict) -> list:
    """Fix BD (Regla D): al fusionar duplicados adyacentes, transfiere desde
    el `consumed` (el que se descarta) hacia el `kept` (el sobreviviente)
    SOLO los campos que el kept tiene vacíos. Nunca sobrescribe valores.

    Campos cubiertos:
      - es           : glosa española (causa principal de pérdida en el bug)
      - strongs      : código Strong's
      - prefix_es    : lista de glosas de prefijos (solo si la del kept está
                       totalmente vacía, para no romper la estructura visual)

    NO crea campos nuevos. NO modifica gr_word / lxx_tier (ya manejados por
    la lógica existente de Regla D). NO toca he_form, he_morph, prefix_gr,
    prefix_morphs.

    Retorna la lista de nombres de campos transferidos (para logging).
    """
    transferred = []
    if not kept.get('es') and consumed.get('es'):
        kept['es'] = consumed['es']
        # es_source se marca como dup_fusion al final del bloque Regla D
        transferred.append('es')
    if not kept.get('strongs') and consumed.get('strongs'):
        kept['strongs'] = consumed['strongs']
        transferred.append('strongs')
    kept_pes = kept.get('prefix_es') or []
    cons_pes = consumed.get('prefix_es') or []
    if not any(kept_pes) and any(cons_pes):
        kept['prefix_es'] = list(cons_pes)
        transferred.append('prefix_es')
    return transferred


def _apply_rule_D(pair: dict, p_idx: int, chap: int, vrs: int) -> None:
    """Regla D: elimina he_words duplicados adyacentes en el mismo pair cuando
    uno tiene gr_word y el otro no. Mantiene el que conserva morph/niqqud más
    completo. Marca el sobreviviente con es_source='dup_fusion'.

    NO fusiona si ambos tienen gr_word (repetición literaria válida).
    NO fusiona si ninguno tiene gr_word (no es el patrón objetivo).
    """
    if pair.get('kind') in ('gk_add', 'heb_omit'):
        return
    hw_list = pair.get('he_words', [])
    if len(hw_list) < 2:
        return
    new_list = []
    i = 0
    while i < len(hw_list):
        if i + 1 < len(hw_list):
            cur = hw_list[i]
            nxt = hw_list[i + 1]
            cur_cons = _norm_heb_dup(cur.get('he_form', ''))
            nxt_cons = _norm_heb_dup(nxt.get('he_form', ''))
            if cur_cons and cur_cons == nxt_cons:
                cur_has = _has_real_greek(cur.get('gr_word', ''))
                nxt_has = _has_real_greek(nxt.get('gr_word', ''))
                if cur_has != nxt_has:  # exactamente uno tiene griego
                    # Determinar el sobreviviente: el que tenga forma más rica
                    # (más caracteres con niqud/cantilación). En empate, el que
                    # ya tiene griego.
                    cur_form = cur.get('he_form', '')
                    nxt_form = nxt.get('he_form', '')
                    keeper = cur if len(cur_form) >= len(nxt_form) else nxt
                    other = nxt if keeper is cur else cur
                    # Asegurar que el keeper conserve el griego
                    if not _has_real_greek(keeper.get('gr_word', '')):
                        keeper['gr_word'] = other.get('gr_word', '')
                        keeper['lxx_tier'] = other.get('lxx_tier',
                                                       keeper.get('lxx_tier', ''))
                    # Fix BD: transferir es / strongs / prefix_es del consumido
                    # cuando el keeper los tiene vacíos. Debe ejecutarse ANTES
                    # de descartar `other` del array.
                    transferred = _merge_consumed_into_kept(keeper, other)
                    keeper['es_source'] = 'dup_fusion'
                    line = (f"{chap}:{vrs} {p_idx}.{i}+{i+1} regla=D fused "
                            f"(form={keeper.get('he_form','')!r}, "
                            f"keep_gr={keeper.get('gr_word','')!r}, "
                            f"keep_es={keeper.get('es','')!r}, "
                            f"transferred={transferred})")
                    _AUDIT_LOG_LINES.append(line)
                    _AUDIT_COUNTERS['D'] += 1
                    if len(_AUDIT_EXAMPLES['D']) < 10:
                        _AUDIT_EXAMPLES['D'].append(line)
                    new_list.append(keeper)
                    i += 2
                    continue
        new_list.append(hw_list[i])
        i += 1
    if len(new_list) != len(hw_list):
        pair['he_words'] = new_list


# ── Regla E: desambiguación de PREP frecuentes con es='de' ───────────────────
# Solo cambia cuando: he_morph == 'PREP' Y es == 'de' Y la forma consonántica
# del he_form coincide con la tabla cerrada.

_PREP_DISAMBIG: dict = {
    'תחת':  ('bajo',  'H8478'),
    'על':   ('sobre', 'H5921'),
    'אל':   ('a',     'H413'),
    'עם':   ('con',   'H5973'),
    'לפני': ('ante',  'H6440'),
    'אחרי': ('tras',  'H310'),
    'אחר':  ('tras',  'H310'),
    # 'בין' ya está manejado por Corrección 3 (fix_es_by_greek con ἀνὰ μέσον)
    # 'מן' / 'מ' — NO se incluye por la nota: legítimamente "de" en muchos casos
}


def _apply_rule_E(hw: dict, p_idx: int, w_idx: int,
                  chap: int, vrs: int) -> None:
    """Regla E: desambigua PREP cuyo es='de' a un valor más preciso según la
    forma hebrea. Tabla cerrada, no toca מן."""
    morph = hw.get('he_morph', '') or ''
    if morph != 'PREP':
        return
    if (hw.get('es', '') or '').strip() != 'de':
        return
    he_form = hw.get('he_form', '') or ''
    cons = consonants(he_form)
    entry = _PREP_DISAMBIG.get(cons)
    if not entry:
        return
    new_es, _expected_strong = entry
    old_es = hw.get('es', '')
    hw['es'] = new_es
    hw['es_source'] = 'prep_disambig'
    _AUDIT_COUNTERS['E'] += 1
    line = (f"{chap}:{vrs} {p_idx}.{w_idx} regla=E "
            f"es='de'->{new_es!r} (form={he_form!r}, strongs={hw.get('strongs','')})")
    _AUDIT_LOG_LINES.append(line)
    if len(_AUDIT_EXAMPLES['E']) < 5:
        _AUDIT_EXAMPLES['E'].append(line)
    fb = _AUDIT_FORM_BREAKDOWN['E']
    fb[cons] = fb.get(cons, 0) + 1


def apply_audit_rules(verse: dict) -> None:
    """
    Corrección 13: aplica las reglas de auditoría A-E sobre un versículo
    YA post-procesado. Sólo se ejecuta para Génesis (la pipeline ya filtra,
    pero verificamos por seguridad).

    Orden:
      A — Conjugación verbal por morph
      E — Desambiguación PREP es='de'
      B — Marcador --- de omisión LXX
      D — Fusión de duplicados adyacentes en mismo pair

    Cada regla maneja sus propios errores localmente para no romper el verso.
    """
    book = (verse.get('book', '') or '').lower()
    if book and book != 'genesis':
        return
    chap = verse.get('chapter', 0)
    vrs = verse.get('verse', 0)

    pairs = verse.get('pairs', []) or []

    for p_idx, pair in enumerate(pairs):
        if pair.get('kind') in ('gk_add', 'heb_omit'):
            continue
        hw_list = pair.get('he_words', []) or []

        # Reglas A y E: por he_word
        for w_idx, hw in enumerate(hw_list):
            try:
                _apply_rule_A(hw, p_idx, w_idx, chap, vrs)
            except Exception as e:  # noqa: BLE001
                _AUDIT_LOG_LINES.append(
                    f"# [error A] {chap}:{vrs} {p_idx}.{w_idx}: {e}"
                )
            try:
                _apply_rule_E(hw, p_idx, w_idx, chap, vrs)
            except Exception as e:  # noqa: BLE001
                _AUDIT_LOG_LINES.append(
                    f"# [error E] {chap}:{vrs} {p_idx}.{w_idx}: {e}"
                )

        # Regla B: por pair (necesita ver si pair_gr ya fue distribuido)
        try:
            _apply_rule_B(pair, chap, vrs, p_idx)
        except Exception as e:  # noqa: BLE001
            _AUDIT_LOG_LINES.append(
                f"# [error B] {chap}:{vrs} pair {p_idx}: {e}"
            )

        # Regla D: por pair (fusión interna)
        try:
            _apply_rule_D(pair, p_idx, chap, vrs)
        except Exception as e:  # noqa: BLE001
            _AUDIT_LOG_LINES.append(
                f"# [error D] {chap}:{vrs} pair {p_idx}: {e}"
            )


def _sanitize_verse_greek(verse: dict) -> None:
    """
    Bug 1 fix: segunda pasada sobre todos los campos griegos del versículo.
    Reemplaza letras hebreas 'lookalike' (resh ר, nun נ/ן, mem מ …) por sus
    equivalentes griegos correctos (rho ρ, nu ν, mu μ …).
    Aplica a: pair.gr_unicode, pair.lemma_unicode, hw.gr_word, hw.prefix_gr[k],
              hw.prs_suffix.gr_word.
    """
    for pair in verse.get("pairs", []):
        if pair.get("gr_unicode"):
            pair["gr_unicode"] = sanitize_greek(pair["gr_unicode"])
        if pair.get("lemma_unicode"):
            pair["lemma_unicode"] = sanitize_greek(pair["lemma_unicode"])
        for hw in pair.get("he_words", []):
            if hw.get("gr_word"):
                hw["gr_word"] = sanitize_greek(hw["gr_word"])
            for k, gv in enumerate(hw.get("prefix_gr", [])):
                if gv:
                    hw["prefix_gr"][k] = sanitize_greek(gv)
            if isinstance(hw.get("prs_suffix"), dict) and hw["prs_suffix"].get("gr_word"):
                hw["prs_suffix"]["gr_word"] = sanitize_greek(hw["prs_suffix"]["gr_word"])


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    sys.stderr.write(f"Leyendo: {IN_FILE}\n")
    data = json.loads(IN_FILE.read_text(encoding="utf-8"))

    current_chap  = 0
    snap_ch_cache = {}
    oshb_ch_cache = {}
    total_verses  = 0
    snap_matched_words = 0
    total_words        = 0

    for verse in data["verses"]:
        cap = verse["chapter"]
        vrs = str(verse["verse"])

        if cap != current_chap:
            current_chap  = cap
            snap_ch_cache = load_snapshot_chapter(cap)
            oshb_ch_cache = load_oshb_chapter(cap)

        snap_segs = snap_ch_cache.get(vrs, [])
        oshb_v    = oshb_ch_cache.get(vrs, {})

        # Alineación consonántica token-level (funciona con o sin snapshot)
        merge_verse(verse, snap_segs, oshb_v)

        # Correcciones sistemáticas post-merge
        post_process_verse(verse)

        # Bug 1 fix: limpiar Hebrew lookalikes de todos los campos griegos
        _sanitize_verse_greek(verse)
        total_verses += 1

        # Estadísticas de cobertura
        for pair in verse.get("pairs", []):
            for hw in pair.get("he_words", []):
                for gr in hw.get("prefix_gr", []):
                    total_words += 1
                    if gr:
                        snap_matched_words += 1
                total_words += 1
                if hw.get("gr_word"):
                    snap_matched_words += 1

    pct = 100 * snap_matched_words / total_words if total_words else 0
    sys.stderr.write(
        f"Versos procesados: {total_verses}\n"
        f"Palabras con Greek individual: {snap_matched_words}/{total_words} ({pct:.1f}%)\n"
        f"Escribiendo: {OUT_FILE}\n"
    )

    OUT_FILE.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8"
    )

    # ── Escritura del log de auditoría (Corrección 13) ───────────────────────
    from datetime import datetime as _dt
    ts = _dt.now().strftime("%Y%m%d_%H%M%S")
    log_path = Path(__file__).parent.parent / "data" / f"audit_log_{ts}.txt"
    header = [
        f"# Audit log Corrección 13 — generado {ts}",
        f"# Reglas: A=verb_conjugation, B=lxx_omission, D=dup_fusion, E=prep_disambig",
        f"# Conteos: A={_AUDIT_COUNTERS['A']}  B={_AUDIT_COUNTERS['B']}  "
        f"D={_AUDIT_COUNTERS['D']}  E={_AUDIT_COUNTERS['E']}",
        "",
    ]
    if _AUDIT_FORM_BREAKDOWN['A']:
        header.append("# Regla A — top cambios (es viejo → es nuevo : count):")
        items = sorted(_AUDIT_FORM_BREAKDOWN['A'].items(),
                       key=lambda kv: -kv[1])
        for (oe, ne), c in items[:10]:
            header.append(f"#   {oe!r} -> {ne!r} : {c}")
        header.append("")
    if _AUDIT_FORM_BREAKDOWN['E']:
        header.append("# Regla E — formas desambiguadas (cons : count):")
        items = sorted(_AUDIT_FORM_BREAKDOWN['E'].items(),
                       key=lambda kv: -kv[1])
        for cons, c in items:
            header.append(f"#   {cons} : {c}")
        header.append("")

    log_path.write_text(
        "\n".join(header + _AUDIT_LOG_LINES) + "\n",
        encoding="utf-8"
    )
    sys.stderr.write(
        f"Auditoría: A={_AUDIT_COUNTERS['A']} B={_AUDIT_COUNTERS['B']} "
        f"D={_AUDIT_COUNTERS['D']} E={_AUDIT_COUNTERS['E']}  log={log_path}\n"
    )
    sys.stderr.write("Listo.\n")


if __name__ == "__main__":
    main()
