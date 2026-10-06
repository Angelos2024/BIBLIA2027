"""
merge_mlxx.py — Fusiona la morfología griega del CATSS .mlxx con los pares del .par

Lee:
  - data/genesis.json          (generado por parse_genesis.py)
  - 01.Gen.1.mlxx              (capítulos 1-21, en la raíz del proyecto)
  - 02.Gen.2.mlxx (opcional)   (capítulos 22-50, si está disponible)

Produce:
  - data/genesis_full.json     (JSON enriquecido con morfología griega LXX)

Estrategia de alineación:
  Para cada versículo, los tokens griegos del .mlxx y del .par están en el
  mismo orden canónico. Se consumen secuencialmente: se cuentan los tokens
  griegos de cada par del .par (ignorando marcadores de aparato crítico) y
  se toman ese número de tokens consecutivos del .mlxx.
"""

import re
import json
import sys
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# RUTAS
# ─────────────────────────────────────────────────────────────────────────────

BASE       = Path(__file__).parent.parent
IN_JSON    = BASE / "data" / "genesis.json"
MLXX_1     = BASE / "01.Gen.1.mlxx"           # capítulos 1-21
MLXX_2     = BASE / "02.Gen.2.mlxx"           # capítulos 22-50 (opcional)
OUT_JSON   = BASE / "data" / "genesis_full.json"

# ─────────────────────────────────────────────────────────────────────────────
# CONVERSOR BETA CODE → UNICODE (griego, para lemas)
# Reutiliza el mismo enfoque de parse_genesis.py
# ─────────────────────────────────────────────────────────────────────────────

try:
    from greekutils import beta2unicode
    _PRIME_RE = re.compile(r'(?<=[BGDVZQK])/')
    def _beta_to_uni(s: str) -> str:
        if not s:
            return s
        try:
            result = beta2unicode.convert(_PRIME_RE.sub('#', s))
            return re.sub(r'σ(?=\s|$)', 'ς', result)
        except Exception:
            return s
except ImportError:
    def _beta_to_uni(s: str) -> str:
        return s   # sin conversión si no está instalada la librería

# ─────────────────────────────────────────────────────────────────────────────
# DECODIFICADOR DE MORFOLOGÍA GRIEGA CATSS
# ─────────────────────────────────────────────────────────────────────────────

# Parte del discurso (POS)
_POS_LABEL = {
    # Sustantivos por declinación
    'N1':  'SUST', 'N1A': 'SUST', 'N1B': 'SUST', 'N1C': 'SUST',
    'N2':  'SUST', 'N2A': 'SUST',
    'N3':  'SUST', 'N3C': 'SUST', 'N3D': 'SUST', 'N3E': 'SUST',
    'N3F': 'SUST', 'N3G': 'SUST', 'N3H': 'SUST', 'N3M': 'SUST',
    'N3T': 'SUST',
    # Artículo
    'RA':  'ART',
    # Adjetivos
    'A1':  'ADJ',  'A1A': 'ADJ',  'A1B': 'ADJ',
    'A2':  'ADJ',  'A3':  'ADJ',
    # Verbos (diversos paradigmas)
    'VA':  'VERB', 'VAI': 'VERB', 'VAT': 'VERB',
    'VB':  'VERB', 'VBI': 'VERB',
    'VC':  'VERB',
    'V1':  'VERB', 'V1I': 'VERB',
    'V2':  'VERB',
    'V3':  'VERB',
    'V9':  'VERB',
    # Invariables
    'P':   'PREP',
    'C':   'CONJ',
    'D':   'ADV',
    'X':   'PART',
    # Pronombres
    'RP':  'PRON', 'RR':  'PRON', 'RD':  'PRON', 'RI':  'PRON',
    'RF':  'PRON', 'RX':  'PRON',
    # Número
    'M':   'NUM',
}

# Caso (nominativo, genitivo…)
_CASE = {'N': 'NOM', 'G': 'GEN', 'D': 'DAT', 'A': 'AC', 'V': 'VOC'}
# Número
_NUM  = {'S': 'SG', 'P': 'PL', 'D': 'DU'}
# Género
_GEN  = {'M': 'M', 'F': 'F', 'N': 'N'}
# Tiempo verbal
_TENS = {'P': 'PRES', 'I': 'IMPF', 'F': 'FUT', 'A': 'AOR',
          'X': 'PERF', 'Y': 'PLUPER', 'L': 'FUTPERF'}
# Voz verbal
_VOI  = {'A': 'ACT', 'M': 'MED', 'P': 'PAS', 'E': 'MED/PAS'}
# Modo verbal
_MOOD = {'I': 'IND', 'S': 'SUBJ', 'O': 'OPT', 'D': 'IMP',
          'N': 'INF', 'P': 'PART'}
# Persona
_PERS = {'1': '1', '2': '2', '3': '3'}


def decode_morph(pos: str, morph: str) -> str:
    """
    Decodifica los códigos POS y morfológicos del .mlxx a una etiqueta legible.

    Ejemplos:
      'N1', 'DSF'     → 'SUST.DAT.SG.F'
      'VAI', 'AAI3S'  → 'VERB.AOR.ACT.IND.3.SG'
      'RA', 'NSM'     → 'ART.NOM.SG.M'
      'P', ''         → 'PREP'
      'C', ''         → 'CONJ'
    """
    pos_lbl = _POS_LABEL.get(pos, pos)

    if not morph:
        return pos_lbl

    parts = [pos_lbl]

    if pos_lbl in ('PREP', 'CONJ', 'ADV', 'PART'):
        return pos_lbl   # invariables: sin morfología adicional

    if pos_lbl == 'VERB':
        # VERB morph = [TENSE][VOICE][MOOD][PERSON][NUMBER] para formas finitas
        #            = [TENSE][VOICE][MOOD=P][CASE][NUMBER][GENDER] para participios
        #            = [TENSE][VOICE][MOOD=N] para infinitivos
        if len(morph) >= 3:
            t  = _TENS.get(morph[0], morph[0])
            v  = _VOI.get(morph[1],  morph[1])
            m  = _MOOD.get(morph[2], morph[2])
            parts += [t, v, m]
            rest = morph[3:]
            if m == 'PART' and len(rest) >= 3:
                # caso + número + género del participio
                c  = _CASE.get(rest[0], rest[0])
                n  = _NUM.get(rest[1],  rest[1])
                g  = _GEN.get(rest[2],  rest[2])
                parts += [c, n, g]
            elif m in ('IND', 'SUBJ', 'OPT', 'IMP') and len(rest) >= 2:
                p  = _PERS.get(rest[0], rest[0])
                n  = _NUM.get(rest[1],  rest[1])
                parts += [p, n]
        return '.'.join(parts)

    # Para sustantivos, adjetivos, artículos, pronombres:
    # morph = [CASE][NUMBER][GENDER]
    if len(morph) >= 3:
        c = _CASE.get(morph[0], morph[0])
        n = _NUM.get(morph[1],  morph[1])
        g = _GEN.get(morph[2],  morph[2])
        parts += [c, n, g]
    elif len(morph) == 2:
        c = _CASE.get(morph[0], morph[0])
        n = _NUM.get(morph[1],  morph[1])
        parts += [c, n]

    return '.'.join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# PARSER DEL ARCHIVO .MLXX
# ─────────────────────────────────────────────────────────────────────────────

REF_LINE = re.compile(r'^(Gen)\s+(\d+):(\d+)\s*$')


def parse_mlxx(path: Path) -> dict:
    """
    Parsea un archivo .mlxx y devuelve un dict indexado por referencia.

    Retorna:
      { 'Gen 1:1': [
          {'word': 'E)N', 'pos': 'P', 'morph': '', 'lemma': 'E)N',
           'lemma_unicode': 'ἐν', 'morph_label': 'PREP', 'prep': ''},
          ...
        ],
        'Gen 1:2': [...],
        ...
      }
    """
    text = path.read_text(encoding='utf-8', errors='replace')
    lines = text.splitlines()

    index = {}
    current_ref = None
    current_tokens = []

    for raw_line in lines:
        line = raw_line.rstrip('\r\n')

        # Línea en blanco: fin de versículo
        if not line.strip():
            if current_ref and current_tokens:
                index[current_ref] = current_tokens
            current_ref = None
            current_tokens = []
            continue

        # Referencia de versículo
        m = REF_LINE.match(line.strip())
        if m:
            if current_ref and current_tokens:
                index[current_ref] = current_tokens
            current_ref = f"Gen {m.group(2)}:{m.group(3)}"
            current_tokens = []
            continue

        # Línea de token — formato de ANCHO FIJO:
        #  [0:25]  WORD      (25 chars, padded with spaces)
        #  [25:29] POS       (4 chars, padded)
        #  [29:35] MORPH     (6 chars, padded; vacío para palabras invariables)
        #  [35:]   LEMMA [PREP]  (resto, separados por espacios)
        if len(line) < 26:
            continue   # línea demasiado corta para ser un token

        word  = line[0:25].strip()
        pos   = line[25:29].strip() if len(line) > 25 else ''
        morph = line[29:35].strip() if len(line) > 29 else ''
        rest  = line[35:].strip()   if len(line) > 35 else ''

        if not word or not pos:
            continue

        rest_parts = rest.split()
        lemma = rest_parts[0] if rest_parts else ''
        prep  = rest_parts[1] if len(rest_parts) > 1 else ''

        morph_label = decode_morph(pos, morph)
        lemma_uni   = _beta_to_uni(lemma)

        current_tokens.append({
            'word':          word,
            'pos':           pos,
            'morph':         morph,
            'lemma':         lemma,
            'lemma_unicode': lemma_uni,
            'morph_label':   morph_label,
            'prep':          prep,
        })

    # Último versículo del archivo
    if current_ref and current_tokens:
        index[current_ref] = current_tokens

    return index


# ─────────────────────────────────────────────────────────────────────────────
# TOKENIZADOR GRIEGO DEL .PAR
# cuenta cuántos tokens griegos reales hay en una cadena del .par
# ─────────────────────────────────────────────────────────────────────────────

# Caracteres válidos del Beta Code griego
_GK_CHARS = frozenset("ABGDEVZHQIKLMNCOPRSTUJFXYWSV()|/\\=+'*-")

# Marcadores de aparato que deben eliminarse antes de tokenizar
_APPAR_RE = re.compile(
    r'\{[^}]*\}'          # {...}
    r'|\[[^\]]*\]'        # [...]
    r'|<[^>]*>'           # <...>
    r'|---\s*(\'\')?'     # --- o --- ''
    r'|\s[\'\']\s'        # ''
    r'|[\^#~!,;]'         # marcadores individuales
)

def count_gk_tokens(gr_raw: str) -> int:
    """
    Cuenta los tokens griegos reales en una cadena del .par.
    Ignora marcadores de aparato crítico, --- y símbolos especiales.
    """
    if not gr_raw or gr_raw.strip() in ('', "''"):
        return 0
    cleaned = _APPAR_RE.sub(' ', gr_raw)
    count = 0
    for word in cleaned.split():
        word = word.strip("'")
        if word and any(c.upper() in _GK_CHARS for c in word):
            count += 1
    return count


# ─────────────────────────────────────────────────────────────────────────────
# FUSIÓN: par JSON + mlxx index
# ─────────────────────────────────────────────────────────────────────────────

def merge(par_data: dict, mlxx_index: dict) -> dict:
    """
    Añade morfología griega a cada par del .par usando los datos del .mlxx.

    Para cada versículo, consume tokens del .mlxx secuencialmente
    según el número de tokens griegos de cada par del .par.
    """
    mismatches = 0

    for verse in par_data['verses']:
        ref = verse['ref']
        mlxx_tokens = mlxx_index.get(ref, None)
        has_mlxx = mlxx_tokens is not None
        if not has_mlxx:
            mlxx_tokens = []

        ptr = 0   # puntero en la lista de tokens del .mlxx

        for pair in verse['pairs']:
            # Omisiones hebreas no tienen tokens griegos en .mlxx
            if pair.get('kind') == 'heb_omit' or pair.get('isGreekOmitted'):
                pair['gr_tokens'] = []
                continue

            n = count_gk_tokens(pair.get('gr', ''))

            if n == 0 or not has_mlxx:
                pair['gr_tokens'] = []
                continue

            # Tomar n tokens del .mlxx
            if ptr + n <= len(mlxx_tokens):
                segment = mlxx_tokens[ptr: ptr + n]
                ptr += n
            else:
                # Desajuste real: los conteos no coinciden
                segment = mlxx_tokens[ptr:]
                ptr = len(mlxx_tokens)
                mismatches += 1

            pair['gr_tokens'] = segment

            # Calcular etiqueta de morfología resumida para el par:
            # se toma el primer token que no sea artículo, preposición o conjunción
            summary_token = next(
                (t for t in segment if t['pos'] not in ('RA', 'P', 'C', 'D', 'X')),
                segment[0] if segment else None
            )
            if summary_token:
                pair['morph_summary'] = summary_token['morph_label']
                pair['lemma_main']    = summary_token['lemma']
                pair['lemma_unicode'] = summary_token['lemma_unicode']
            else:
                pair['morph_summary'] = segment[0]['morph_label'] if segment else ''
                pair['lemma_main']    = ''
                pair['lemma_unicode'] = ''

        # Solo contar desajuste real si había datos .mlxx y sobraron tokens
        if has_mlxx and ptr < len(mlxx_tokens):
            mismatches += 1

    return par_data, mismatches


# ─────────────────────────────────────────────────────────────────────────────
# PUNTO DE ENTRADA
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print(f"Leyendo JSON base : {IN_JSON}")
    par_data = json.loads(IN_JSON.read_text(encoding='utf-8'))

    # Construir índice .mlxx (Gen 1-21 obligatorio, 22-50 opcional)
    mlxx_index = {}

    if MLXX_1.exists():
        print(f"Leyendo .mlxx     : {MLXX_1}")
        mlxx_index.update(parse_mlxx(MLXX_1))
    else:
        print(f"ERROR: no se encontró {MLXX_1}")
        sys.exit(1)

    if MLXX_2.exists():
        print(f"Leyendo .mlxx     : {MLXX_2}")
        mlxx_index.update(parse_mlxx(MLXX_2))
    else:
        print(f"(Nota: {MLXX_2.name} no está disponible — solo capítulos 1-21 tendrán morfología)")

    print(f"Versículos en .mlxx: {len(mlxx_index)}")

    # Fusionar
    enriched, mismatches = merge(par_data, mlxx_index)
    enriched['_mlxx'] = str(MLXX_1.name)

    # Guardar
    OUT_JSON.write_text(
        json.dumps(enriched, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )

    print(f"Desajustes detectados : {mismatches}")
    print(f"JSON enriquecido en   : {OUT_JSON}")

    # Muestra de Gen 1:1
    v0 = enriched['verses'][0]
    print(f"\nMuestra {v0['ref']}:")
    for p in v0['pairs']:
        toks = p.get('gr_tokens', [])
        morph = p.get('morph_summary', '')
        lemma = p.get('lemma_unicode', '')
        label = f"{morph} / {lemma}" if lemma else morph
        tok_str = ' | '.join(f"{t['word']}({t['morph_label']})" for t in toks)
        print(f"  {p['he']:<20} -> {tok_str:<50}  [{label}]")
