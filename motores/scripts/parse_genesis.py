"""
parse_genesis.py — Parser de 01.Genesis.par (formato CATSS)
Inspirado en codykingham/CATSS_parsers (github.com/codykingham/CATSS_parsers)

Convierte el archivo .par del CATSS (Universidad de Pensilvania) en un JSON
estructurado compatible con el visor interlineal.

Uso:
    pip install greek-utils==0.2 regex
    python parse_genesis.py

Salida:
    ../data/genesis.json
"""

import re
import json
import sys
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# RUTAS
# ─────────────────────────────────────────────────────────────────────────────

PAR_FILE  = Path(r"C:\Users\pik_y\Documents\GitHub\Local-consults\estudio\angelos\catss-sample\01.Genesis.par")
OUT_FILE  = Path(__file__).parent.parent / "data" / "genesis.json"

# ─────────────────────────────────────────────────────────────────────────────
# TRADUCCIÓN: HEBREO ASCII (CCAT) → UNICODE CONSONÁNTICO
# (sin puntos vocálicos; el .par no los tiene)
# ─────────────────────────────────────────────────────────────────────────────

CCAT_TO_HEB = {
    ')': 'א', 'B': 'ב', 'G': 'ג', 'D': 'ד', 'H': 'ה',
    'W': 'ו', 'Z': 'ז', 'X': 'ח', '+': 'ט', 'Y': 'י',
    'K': 'כ', 'L': 'ל', 'M': 'מ', 'N': 'נ', 'S': 'ס',
    '(': 'ע', 'P': 'פ', 'C': 'צ', 'Q': 'ק', 'R': 'ר',
    '&': 'שׂ', '$': 'שׁ', 'T': 'ת',
    '-': '־', '/': '',   # maqef y separador de prefijo
    '\\': '',            # backslash descartado
    ' ': ' ',
}

# Letras finales: se aplican cuando la letra está al final de palabra
FINAL_FORMS = {
    'מ': 'ם', 'כ': 'ך', 'נ': 'ן', 'פ': 'ף', 'צ': 'ץ',
}

_WORD_END = re.compile(r'([מכנפצ])(?=\s|$)')


def _apply_finals(s: str) -> str:
    return _WORD_END.sub(lambda m: FINAL_FORMS[m.group(1)], s)


def heb_ascii_to_unicode(token: str) -> str:
    """Convierte un token ASCII del CCAT al hebreo Unicode consonántico."""
    out = ''
    for ch in token:
        out += CCAT_TO_HEB.get(ch, ch)
    return _apply_finals(out)


# ─────────────────────────────────────────────────────────────────────────────
# TRADUCCIÓN: BETA CODE GRIEGO → UNICODE
# Usamos greek-utils si está disponible; si no, fallback propio.
# ─────────────────────────────────────────────────────────────────────────────

try:
    from greekutils import beta2unicode  # pip install greek-utils==0.2

    # Algunas raíces en Beta Code usan "/" para la prima; la sustituimos por "#"
    # para que beta2unicode la reconozca como acento agudo sobre consonante.
    _PRIME_RE = re.compile(r'(?<=[BGDVZQK])/')

    def gk_beta_to_unicode(token: str) -> str:
        """Convierte Beta Code a griego Unicode (palabra por palabra para preservar espacios)."""
        if not token or token.strip() in ('---', "''", ''):
            return token
        parts = []
        for word in token.split(' '):
            if not word:
                parts.append('')
                continue
            replaced = _PRIME_RE.sub('#', word)
            try:
                conv = beta2unicode.convert(replaced)
                conv = re.sub(r'σ(?=\s|$|[.,;·])', 'ς', conv)
                parts.append(conv)
            except Exception:
                parts.append(word)
        return ' '.join(parts)

    _HAS_GREEK_UTILS = True

except ImportError:
    _HAS_GREEK_UTILS = False

    # ── Fallback: tabla simplificada Beta → Unicode ──────────────────────────
    # Cubre sólo consonantes básicas y los diacríticos más comunes del LXX.
    # Para producción, instalar greek-utils.

    _BETA_BASE = {
        'A': 'α', 'B': 'β', 'G': 'γ', 'D': 'δ', 'E': 'ε',
        'V': 'ϝ', 'Z': 'ζ', 'H': 'η', 'Q': 'θ', 'I': 'ι',
        'K': 'κ', 'L': 'λ', 'M': 'μ', 'N': 'ν', 'C': 'ξ',
        'O': 'ο', 'P': 'π', 'R': 'ρ', 'S': 'σ', 'T': 'τ',
        'U': 'υ', 'F': 'φ', 'X': 'χ', 'Y': 'ψ', 'W': 'ω',
        'J': 'ς',   # sigma final explícito
    }

    # Combinaciones con diacríticos (orden: espíritu, acento, iota subscrito)
    # Esta tabla cubre los casos más frecuentes del LXX.
    _BETA_COMBO = {
        # ─ alpha ─
        'A/':  'ά', 'A\\': 'ὰ', 'A=': 'ᾶ', 'A|': 'ᾳ',
        'A(/': 'ἄ', 'A(\\': 'ἂ', 'A(=': 'ἆ',
        'A)/': 'ἄ', 'A)\\': 'ἂ', 'A)=': 'ἆ',
        'A)':  'ἀ', 'A(':  'ἁ',
        # ─ epsilon ─
        'E/':  'έ', 'E\\': 'ὲ',
        'E)/': 'ἔ', 'E)\\': 'ἒ', 'E)': 'ἐ',
        'E(/': 'ἕ', 'E(\\': 'ἓ', 'E(': 'ἑ',
        # ─ eta ─
        'H/':  'ή', 'H\\': 'ὴ', 'H=': 'ῆ', 'H|': 'ῃ',
        'H)/': 'ἤ', 'H)\\': 'ἢ', 'H)=': 'ἦ',
        'H(/': 'ἥ', 'H(\\': 'ἣ', 'H(=': 'ἧ',
        'H)':  'ἠ', 'H(':  'ἡ',
        'H=|': 'ῇ', 'H)|': 'ᾐ',
        # ─ iota ─
        'I/':  'ί', 'I\\': 'ὶ', 'I=': 'ῖ',
        'I)/': 'ἴ', 'I)\\': 'ἲ', 'I)=': 'ῖ',
        'I(/': 'ἵ', 'I(\\': 'ἳ',
        'I)':  'ἰ', 'I(':  'ἱ',
        # ─ omicron ─
        'O/':  'ό', 'O\\': 'ὸ',
        'O)/': 'ὄ', 'O)\\': 'ὂ', 'O)': 'ὀ',
        'O(/': 'ὅ', 'O(\\': 'ὃ', 'O(': 'ὁ',
        # ─ upsilon ─
        'U/':  'ύ', 'U\\': 'ὺ', 'U=': 'ῦ',
        'U)/': 'ὔ', 'U)\\': 'ὒ', 'U)': 'ὐ',
        'U(/': 'ὕ', 'U(\\': 'ὓ', 'U(': 'ὑ',
        # ─ omega ─
        'W/':  'ώ', 'W\\': 'ὼ', 'W=': 'ῶ', 'W|': 'ῳ',
        'W)/': 'ὤ', 'W)\\': 'ὢ', 'W)=': 'ὦ',
        'W(/': 'ὥ', 'W(\\': 'ὣ', 'W(=': 'ὧ',
        'W)':  'ὠ', 'W(':  'ὡ',
        'W=|': 'ῷ',
        # ─ rho ─
        'R(':  'ῥ', 'R)': 'ρ',
    }

    def gk_beta_to_unicode(token: str) -> str:
        """Fallback: convierte Beta Code a griego Unicode (sin greek-utils)."""
        if not token or token.strip() in ('---', "''", ''):
            return token
        result = ''
        i = 0
        t = token.upper()
        while i < len(t):
            # Intentar combinaciones largas primero (3 chars)
            matched = False
            for length in (3, 2):
                chunk = t[i:i+length]
                if chunk in _BETA_COMBO:
                    result += _BETA_COMBO[chunk]
                    i += length
                    matched = True
                    break
            if not matched:
                ch = t[i]
                result += _BETA_BASE.get(ch, ch)
                i += 1
        # Sigma final
        result = re.sub(r'σ(?=\s|$)', 'ς', result)
        return result


# ─────────────────────────────────────────────────────────────────────────────
# ANÁLISIS DE PREFIJOS HEBREOS
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# ANÁLISIS MORFOLÓGICO HEBREO — PREFIJOS Y PARTÍCULAS CONOCIDAS
# Fuente: morfología del hebreo bíblico (sistema CCAT)
# NOTA: estas son etiquetas HEB, nunca griegas.
# ─────────────────────────────────────────────────────────────────────────────

HEB_PREFIX_LABELS = {
    'W':  'CONJ.VAV',   # ו waw conjuntivo
    'B':  'PREP.B',     # ב preposición "en/con"
    'L':  'PREP.L',     # ל preposición "a/para"
    'M':  'PREP.M',     # מ preposición "de/desde"
    'H':  'ART.HEB',    # ה artículo determinado
    'K':  'PREP.K',     # כ preposición "como"
    'S':  'REL.SH',     # שׁ relativo (tardío)
}

# Partículas invariables conocidas (stems sin prefijos)
HEB_PARTICLES = {
    ')T':   'PART.OBJ',     # את marcador de objeto directo
    ')$R':  'REL.PRON',     # אשר pronombre relativo
    'KY':   'CONJ',         # כי que/porque/cuando
    'L)':   'NEG',          # לא negación
    'LW)':  'NEG',          # לוא negación (variante)
    'HNH':  'PART.DEIX',    # הנה he aquí
    ')P':   'CONJ.AF',      # אף también/incluso
    ')M':   'CONJ.IF',      # אם si/aunque
    ')K':   'ADV.ONLY',     # אך solo/ciertamente
    'RQ':   'ADV.ONLY',     # רק solo
    'GN':   'ADV.ALSO',     # גם también
    'YT':   'PART.OBJ',     # יֵת (variante aramea de את)
    'PNY':  'NOUN.CONSTR',  # פני "ante/delante de" (constructo)
    '(L':   'PREP',         # על sobre/encima
    ')L':   'PREP',         # אל a/hacia
    'MN':   'PREP',         # מן de/desde
    ')T':   'PART.OBJ',
    'BYN':  'PREP',         # בין entre
    'TXN':  'PREP',         # תחן bajo
}

# Pronombres personales independientes
HEB_PRONOUNS = {
    ')NY': 'PRON.1SG', ')NK': 'PRON.1SG',
    ')NW': 'PRON.1PL',
    'HW)': 'PRON.3MSG', 'HY)': 'PRON.3FSG',
    'HM': 'PRON.3MPL', 'HN': 'PRON.3FPL',
    ')TH': 'PRON.2MSG', ')T': 'PRON.2FSG',
    ')TM': 'PRON.2MPL', ')TN': 'PRON.2FPL',
}

_APPAR_CLEAN = re.compile(r'[=;:<>\[\]{}@*%?.!,#^~]')

# Limpia el griego crudo de marcadores de aparato crítico ({d}, etc.)
_GR_APPAR = re.compile(r'\{[^}]*\}|\[[^\]]*\]|<[^>]*>|[#^~!]')

def _clean_gr_raw(gr_raw: str) -> str:
    """Elimina marcadores de aparato del texto griego antes de la conversión Beta."""
    s = _GR_APPAR.sub(' ', gr_raw)        # reemplaza {d} etc. por espacio
    return re.sub(r'\s+', ' ', s).strip() # colapsa espacios múltiples


def analyze_he_word(ascii_word: str) -> dict:
    """
    Analiza UNA palabra hebrea del .par (sin espacios).
    Separa prefijos de la raíz/stem y asigna etiquetas HEB.

    Retorna dict con:
      raw            — token original ASCII
      prefixes       — lista de prefijos en ASCII (ej. ['W', 'H'])
      stem           — raíz/stem en ASCII (ej. ')RC')
      prefix_labels  — etiquetas HEB de prefijos (ej. ['CONJ.VAV', 'ART.HEB'])
      stem_label     — etiqueta HEB del stem si es partícula conocida (ej. 'PART.OBJ')
      prefix_unicode — prefijo(s) en Unicode hebreo consonántico
      stem_unicode   — stem/raíz en Unicode hebreo consonántico
      full_unicode   — palabra completa Unicode (prefix+stem)
      heb_label      — etiqueta completa para mostrar en UI (ej. 'CONJ.VAV+PART.OBJ')
    """
    clean = _APPAR_CLEAN.sub('', ascii_word).strip()
    if not clean:
        return _empty_he_word(ascii_word)

    parts = clean.split('/')
    if len(parts) > 1:
        prefixes = [p for p in parts[:-1] if p]
        stem     = parts[-1]
    else:
        prefixes = []
        stem     = parts[0]

    prefix_labels = [HEB_PREFIX_LABELS[p] for p in prefixes if p in HEB_PREFIX_LABELS]
    stem_label    = (HEB_PARTICLES.get(stem) or HEB_PRONOUNS.get(stem) or '')

    prefix_unicode = heb_ascii_to_unicode(''.join(prefixes))  # sin / entre ellos
    stem_unicode   = heb_ascii_to_unicode(stem)
    full_unicode   = heb_ascii_to_unicode(clean)  # incluye / → vacío

    # Etiqueta completa para UI
    parts_label = prefix_labels[:]
    if stem_label:
        parts_label.append(stem_label)
    heb_label = '+'.join(parts_label)

    return {
        'raw':            ascii_word,
        'prefixes':       prefixes,
        'stem':           stem,
        'prefix_labels':  prefix_labels,
        'stem_label':     stem_label,
        'prefix_unicode': prefix_unicode,
        'stem_unicode':   stem_unicode,
        'full_unicode':   full_unicode,
        'heb_label':      heb_label,
    }


def _empty_he_word(raw: str) -> dict:
    return {
        'raw': raw, 'prefixes': [], 'stem': '', 'prefix_labels': [],
        'stem_label': '', 'prefix_unicode': '', 'stem_unicode': '',
        'full_unicode': '', 'heb_label': '',
    }


def split_he_token(he_raw: str) -> list:
    """
    Divide el token hebreo de una línea del .par en palabras individuales.
    Cada token del .par puede contener varias palabras separadas por espacios
    (ej. ')T H/$MYM' = partícula + artículo + sustantivo).

    Retorna lista de dicts analyze_he_word() por cada palabra real.
    """
    if not he_raw or he_raw.strip().startswith('--'):
        return []
    words = he_raw.strip().split()
    result = []
    for word in words:
        # Saltar marcadores de aparato puro
        bare = _APPAR_CLEAN.sub('', word).strip()
        if not bare:
            continue
        result.append(analyze_he_word(word))
    return result


def analyze_prefixes(he_ascii: str) -> str:
    """Compatibilidad: etiqueta de prefijos del primer token (UI legado)."""
    words = split_he_token(he_ascii)
    if not words:
        return ''
    labels = []
    for w in words:
        if w['prefix_labels']:
            labels.extend(w['prefix_labels'])
    return '+'.join(labels)


# ─────────────────────────────────────────────────────────────────────────────
# PARSER PRINCIPAL DEL ARCHIVO .PAR
# ─────────────────────────────────────────────────────────────────────────────

REF_LINE = re.compile(r'^Gen\s+(\d+):(\d+)\s*$')

# Marcadores de tipo de par
def classify_pair(he_raw: str, gr_raw: str) -> dict:
    """
    Clasifica y convierte un par hebreo/griego del archivo .par.

    Tipos:
    - 'align'    : par normal hebreo ↔ griego
    - 'gk_add'   : adición griega sin equivalente hebreo (--+)
    - 'heb_omit' : hebreo presente pero omitido en griego (--- en columna griega)
    """
    he_clean = he_raw.strip()
    gr_clean = gr_raw.strip() if gr_raw else ''

    # ── Adición griega (columna A empieza con --+) ──
    if he_clean.startswith('--+'):
        heb_note = he_clean[3:].strip()
        gr_ascii_clean = _clean_gr_raw(gr_clean)
        return {
            'he': '',
            'he_unicode': '',
            'he_note': heb_note,
            'gr': gr_clean,
            'gr_unicode': gk_beta_to_unicode(gr_ascii_clean),
            'kind': 'gk_add',
            'isApparatusPrefix': False,
            'isGreekOmitted': False,
        }

    # ── Omisión hebrea (---) en columna A ──
    if he_clean.startswith('---'):
        gr_ascii_clean = _clean_gr_raw(gr_clean)
        return {
            'he': he_clean,
            'he_unicode': '',
            'he_note': '',
            'gr': gr_clean,
            'gr_unicode': gk_beta_to_unicode(gr_ascii_clean),
            'kind': 'heb_omit',
            'isApparatusPrefix': False,
            'isGreekOmitted': False,
        }

    # ── Par normal ──
    # La columna griega puede contener --- para pasajes omitidos
    is_gk_omit = bool(re.search(r'\b---\b', gr_clean))

    # Convertir hebreo
    # Extraer sólo los caracteres CCAT (descartar aparato crítico)
    he_ascii_clean = re.sub(r'[=;:<>\[\]{}@*%?.!,#^~]', '', he_clean)
    he_ascii_clean = re.sub(r'\s+', ' ', he_ascii_clean).strip()

    he_unicode = heb_ascii_to_unicode(he_ascii_clean)

    # Extraer sólo los caracteres griegos (descartar aparato)
    gr_ascii_clean = re.sub(r'\{[^}]*\}|\[[^\]]*\]|<[^>]*>', '', gr_clean)
    gr_ascii_clean = re.sub(r'[#^~!]', '', gr_ascii_clean)
    gr_ascii_clean = re.sub(r'\s+', ' ', gr_ascii_clean).strip()

    gr_unicode = gk_beta_to_unicode(gr_ascii_clean)

    prefixes  = analyze_prefixes(he_clean)
    he_words  = split_he_token(he_clean)

    # Stem hebreo del token principal (última palabra, sin prefijos)
    he_stem_uni = he_words[-1]['stem_unicode'] if he_words else ''

    return {
        'he': he_clean,
        'he_unicode': he_unicode,
        'he_stem_unicode': he_stem_uni,
        'he_words': he_words,
        'he_note': '',
        'gr': gr_clean,
        'gr_unicode': gr_unicode,
        'prefixes': prefixes,
        'kind': 'align',
        'isApparatusPrefix': False,
        'isGreekOmitted': is_gk_omit,
    }


def parse_par(par_path: Path) -> dict:
    """Parsea el archivo .par completo y devuelve la estructura JSON."""
    text = par_path.read_text(encoding='utf-8', errors='replace')
    lines = text.splitlines()

    verses = []
    current_chapter = None
    current_verse_num = None
    current_pairs = []
    current_ref = None

    def flush_verse():
        if current_ref is not None and current_pairs:
            verses.append({
                'book': 'Genesis',
                'chapter': current_chapter,
                'verse': current_verse_num,
                'ref': current_ref,
                'pairs': list(current_pairs),
            })

    for line in lines:
        line = line.rstrip('\r\n')

        # Línea en blanco: separador entre versículos
        if not line.strip():
            continue

        # ── Línea de referencia ──
        m = REF_LINE.match(line)
        if m:
            flush_verse()
            current_chapter = int(m.group(1))
            current_verse_num = int(m.group(2))
            current_ref = f"Gen {current_chapter}:{current_verse_num}"
            current_pairs = []
            continue

        # ── Línea de datos ──
        if '\t' in line:
            parts = line.split('\t', 1)
            he_raw = parts[0]
            gr_raw = parts[1] if len(parts) > 1 else ''
            pair = classify_pair(he_raw, gr_raw)
            current_pairs.append(pair)
        else:
            # Línea sin tabulador: puede ser un token hebreo sin correspondencia griega
            if line.strip():
                pair = classify_pair(line.strip(), '')
                current_pairs.append(pair)

    # No olvidar el último versículo
    flush_verse()

    return {
        '_schema': 'catss-par-parsed-v1',
        '_source': 'https://ccat.sas.upenn.edu/gopher/text/religion/biblical/parallel/01.Genesis.par',
        '_file': '01.Genesis.par',
        '_book': 'Genesis',
        '_parser': 'parse_genesis.py (inspirado en codykingham/CATSS_parsers)',
        '_greek_utils': f'greek-utils disponible: {_HAS_GREEK_UTILS}',
        'verseCount': len(verses),
        'verses': verses,
    }


# ─────────────────────────────────────────────────────────────────────────────
# PUNTO DE ENTRADA
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print(f"Leyendo: {PAR_FILE}")
    if not PAR_FILE.exists():
        print(f"ERROR: No se encontró el archivo .par en:\n  {PAR_FILE}")
        sys.exit(1)

    data = parse_par(PAR_FILE)

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f"Versículos procesados : {data['verseCount']}")
    print(f"greek-utils activo    : {_HAS_GREEK_UTILS}")
    print(f"JSON guardado en      : {OUT_FILE}")

    # Muestra una muestra del primer versículo
    v0 = data['verses'][0]
    print(f"\nMuestra: {v0['ref']}")
    for p in v0['pairs'][:5]:
        print(f"  {p['he']:<20} = {p['he_unicode']:<12} | {p['gr']:<30} = {p['gr_unicode']}")
