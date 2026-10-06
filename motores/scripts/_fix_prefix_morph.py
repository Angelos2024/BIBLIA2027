"""_fix_prefix_morph.py - Corrige prefix_morphs heredados con etiquetas erróneas.

Problema: el parseo CATSS deja a veces en prefix_morphs[i] el morf de la raíz o
del sufijo (p.ej. lamed ל etiquetado 'PRON.P+.X.D', vav ו como 'SUBS.M.PL.C').
El motor hebreo (populate_hebrew_macula.py) solo rellenaba prefijos vacíos, así
que esos valores basura sobrevivían y se muestran en el visor bajo cada prefijo.

Solución: para cada prefix_forms[i], si su morf actual NO es una categoría de
prefijo válida, se re-deriva de la consonante CATSS del prefijo según el mapeo
canónico observado en Génesis:
    W → CONJ      B/K/L/M → PREP      H → ART
Se PRESERVAN los valores ya válidos (CONJ, PREP, ART, PRT, ADV, NEG y el he
interrogativo INTERR/INTERROG), de modo que no se introducen errores nuevos.

Uso:
    python _fix_prefix_morph.py <slug> [--apply]
"""
import json, sys, re

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
from book_config import resolve

# Categorías que SÍ son partículas-prefijo legítimas -> no se tocan.
VALID_PREFIX_BASES = {
    'CONJ', 'PREP', 'ART', 'PRT', 'ADV', 'NEG',
    'INTR', 'INTERR', 'INTERROG', 'PART', 'REL',
}


def _strip_gr(s):
    """Normaliza griego: quita acentos/espíritus/apostrofo, minúsculas."""
    import unicodedata
    s = (s or '').strip().lower().replace('\u2019', '').replace("'", '')
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return s


# Artículo griego (todas las formas), conjunciones y preposiciones propias.
_GR_ART = {'ο', 'η', 'το', 'του', 'της', 'τω', 'τη', 'τον', 'την',
           'οι', 'αι', 'τα', 'τους', 'τας', 'των', 'τοις', 'ταις'}
_GR_CONJ = {'και', 'δε', 'τε', 'αλλα', 'γαρ', 'η', 'ουδε', 'μηδε',
            'ουτε', 'μητε', 'ιδου', 'ιδε'}
_GR_PREP = {'εν', 'εις', 'εκ', 'εξ', 'προς', 'επι', 'επ', 'εφ', 'απο', 'απ',
            'αφ', 'δια', 'δι', 'κατα', 'κατ', 'καθ', 'μετα', 'μετ', 'μεθ',
            'περι', 'υπο', 'υπ', 'υφ', 'παρα', 'παρ', 'συν', 'ανα', 'υπερ',
            'προ', 'αντι', 'ενωπιον', 'ενεκα', 'εως'}


def greek_morph(gr):
    """Deriva la categoría de prefijo desde la palabra griega misma.
    Útil cuando el prefijo hebreo es multi-carácter (preposición separada,
    p.ej. עַל -> ἐπ') o cuando el griego es un artículo determinante."""
    g = _strip_gr(gr)
    if not g:
        return None
    if g in _GR_ART:
        return 'ART'
    if g in _GR_CONJ:
        return 'CONJ'
    if g in _GR_PREP:
        return 'PREP'
    return None

def canonical_morph(cons: str, current_base: str):
    """Devuelve el morf canónico para la consonante de prefijo, o None si no se
    debe cambiar."""
    cons = (cons or '').strip()
    if not cons:
        return None
    # Solo partículas-prefijo inseparables reales (1 consonante CATSS).
    # Los compuestos multi-carácter (LBD, LMYN, ')P') ya están como PREP válido;
    # las entradas largas suelen ser palabras completas mal parseadas -> no tocar.
    if len(cons) != 1:
        return None
    c0 = cons[0]
    if c0 == 'W':
        return 'CONJ'
    if c0 in ('B', 'K', 'L', 'M'):
        return 'PREP'
    if c0 == 'H':
        # he interrogativo: si ya está marcado como interrogativo, conservar
        if current_base in ('INTERR', 'INTERROG'):
            return None
        return 'ART'
    if c0 == '$':
        return 'PRT'  # shin relativo
    return None


def fix_book(slug: str, apply: bool):
    cfg = resolve(slug)
    d = json.loads(cfg.final_json_path.read_text(encoding='utf-8'))
    changed = 0
    samples = []
    for v in d['verses']:
        if v.get('is_lxx_add'):
            continue
        for p in v.get('pairs', []):
            if p.get('kind') == 'gk_add':
                continue
            for hw in p.get('he_words', []):
                prefixes = hw.get('prefixes') or []
                pm = hw.get('prefix_morphs') or []
                pgr = hw.get('prefix_gr') or []
                if not prefixes or not pm:
                    continue
                for i, cons in enumerate(prefixes):
                    if i >= len(pm):
                        break
                    cur = (pm[i] or '').strip()
                    cur_base = cur.split('.')[0]
                    if cur_base in VALID_PREFIX_BASES:
                        continue  # ya es prefijo válido
                    new_morph = canonical_morph(cons, cur_base)
                    if not new_morph:
                        # fallback: derivar del griego del prefijo
                        g = pgr[i] if i < len(pgr) else ''
                        new_morph = greek_morph(g)
                    if not new_morph or new_morph == cur:
                        continue
                    if len(samples) < 12:
                        samples.append(
                            f"  {v['chapter']}:{v['verse']} {cons!r} {cur!r} -> {new_morph}")
                    pm[i] = new_morph
                    changed += 1
                hw['prefix_morphs'] = pm
    print(f"{slug:<12} prefix_morphs corregidos: {changed}")
    for s in samples:
        print(s)
    if apply and changed:
        cfg.final_json_path.write_text(
            json.dumps(d, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"  -> guardado {cfg.final_json_path.name}")
    return changed


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    apply = '--apply' in sys.argv
    slug = args[0] if args else 'genesis'
    fix_book(slug, apply)
