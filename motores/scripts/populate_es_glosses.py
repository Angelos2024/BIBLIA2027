"""populate_es_glosses.py
Fill empty Spanish glosses (es, prefix_es) using a cascading lookup.

Sources (in priority order):
  1. diccionario/pruebas/01Génesis.json  — he_form -> candidatos[0]
  2. _idx_strong_es_<book>.json          — strongs -> top RV1909 text
  3. Macula Hebrew gloss (English)       — "[EN:gloss]" placeholder

Safety:
  - Only fills EMPTY es / prefix_es slots (never overwrites existing values)
  - Skips gk_add pairs and meta raws
  - Skips protected chapters (Genesis 1-15 only)
  - Never touches Hebrew fields
  - Records es_source for every assignment

Usage:
    python populate_es_glosses.py --book levitico              # dry-run
    python populate_es_glosses.py --book levitico --apply      # apply
    python populate_es_glosses.py --book genesis --chapter 16   # single chapter
"""
import csv, json, sys, argparse, unicodedata
from pathlib import Path
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

from book_config import resolve
from gen_chapter_scope import is_rules_target

ANGELOS = Path(r'C:\Users\pik_y\Documents\GitHub\Local-consults\estudio\angelos')
DIC_GENESIS = ANGELOS / 'diccionario' / 'pruebas' / '01Génesis.json'
MACULA_TSV = ANGELOS / 'IdiomaORIGEN' / 'macula-hebrew.tsv'

SLUG_TO_MACULA = {
    "genesis": "GEN", "exodo": "EXO", "levitico": "LEV", "numeros": "NUM",
    "deuteronomio": "DEU", "josue": "JOS", "jueces": "JDG", "rut": "RUT",
    "1_samuel": "1SA", "2_samuel": "2SA", "1_reyes": "1KI", "2_reyes": "2KI",
    "1_cronicas": "1CH", "2_cronicas": "2CH", "esdras": "EZR", "nehemias": "NEH",
    "ester": "EST", "job": "JOB", "salmos": "PSA", "proverbios": "PRO",
    "eclesiastes": "ECC", "cantares": "SNG", "isaias": "ISA", "jeremias": "JER",
    "lamentaciones": "LAM", "ezequiel": "EZK", "daniel": "DAN", "oseas": "HOS",
    "joel": "JOL", "amos": "AMO", "abdias": "OBA", "jonas": "JON",
    "miqueas": "MIC", "nahum": "NAM", "habacuc": "HAB", "sofonias": "ZEP",
    "hageo": "HAG", "zacarias": "ZEC", "malaquias": "MAL",
}

GKADD_RAWS = frozenset({"GKADD", "=<LXX>"})
META_START = ("=", "{", "<", "*", "--", ".$", ".")
FINAL_MAP = {'ך': 'כ', 'ם': 'מ', 'ן': 'נ', 'ף': 'פ', 'ץ': 'צ'}
CATSS_MAP = {
    ')': 'א', 'B': 'ב', 'G': 'ג', 'D': 'ד', 'H': 'ה',
    'W': 'ו', 'Z': 'ז', 'X': 'ח', '+': 'ט', 'Y': 'י',
    'K': 'כ', 'L': 'ל', 'M': 'מ', 'N': 'נ', 'S': 'ס',
    '(': 'ע', 'P': 'פ', 'C': 'צ', 'Q': 'ק', 'R': 'ר',
    '&': 'ש', '$': 'ש', 'T': 'ת',
}
SUFFIX_POS = frozenset({'suffix'})

# Morph codes where es should remain empty (grammatical markers, not translatable)
SKIP_ES_MORPHS = frozenset({
    'To',   # direct object marker (את)
})


def hc(text):
    """Extract Hebrew consonant skeleton."""
    nfd = unicodedata.normalize('NFD', text or '')
    return ''.join(FINAL_MAP.get(c, c) for c in nfd if '\u05D0' <= c <= '\u05EA')


def strip_cantillation(text):
    """Strip cantillation marks but keep vowel points for precise matching."""
    nfc = unicodedata.normalize('NFC', text or '')
    return ''.join(c for c in nfc if not ('\u0591' <= c <= '\u05AF'))


def catss_to_cons(raw):
    return ''.join(CATSS_MAP.get(c, '') for c in raw.replace('/', ''))


def is_meta(raw):
    if not raw or raw in GKADD_RAWS:
        return True
    return any(raw.startswith(p) for p in META_START)


# ─── PREFIX TABLE ─────────────────────────────────────────────────────────────
PREFIX_BY_CONS = {
    'ו': 'y',
    'ב': 'en',
    'ל': 'a',
    'מ': 'de',
    'כ': 'como',
    'ש': 'que',
}

PREFIX_BY_MORPH = {
    'C': 'y',
    'Td': 'el',
}


def prefix_gloss(form, morph):
    """Resolve prefix Spanish gloss from form consonants or morph code."""
    cons = hc(form)
    if cons in PREFIX_BY_CONS:
        return PREFIX_BY_CONS[cons]
    m = (morph or '').strip()
    if m in PREFIX_BY_MORPH:
        return PREFIX_BY_MORPH[m]
    if m == 'R':
        return PREFIX_BY_CONS.get(cons, '')
    if m.startswith('Td') or m == 'Td':
        return 'el'
    return ''


# ─── LOAD DICCIONARIO GENESIS ─────────────────────────────────────────────────
def load_dic_genesis():
    """Build he_form -> Spanish lookup from 01Génesis.json.
    Returns dict mapping stripped Hebrew text -> first candidate."""
    raw_data = json.loads(DIC_GENESIS.read_text(encoding='utf-8'))
    lookup = {}
    for entry in raw_data:
        heb = (entry.get('texto_hebreo') or '').strip()
        if not heb:
            continue
        cands = entry.get('candidatos') or []
        if not cands:
            eq = (entry.get('equivalencia_espanol') or '').strip()
            if eq:
                first = eq.split('/')[0].strip()
                cands = [first]
        if not cands:
            continue
        key_stripped = strip_cantillation(heb)
        key_cons = hc(heb)
        if key_stripped not in lookup:
            lookup[key_stripped] = cands[0]
        if key_cons and key_cons not in lookup:
            lookup[key_cons] = cands[0]
    return lookup


# ─── LOAD STRONG'S INDEX ──────────────────────────────────────────────────────
def load_strong_idx(idx_path=None):
    """Build strongs -> top Spanish text lookup."""
    if idx_path is None:
        idx_path = resolve('genesis').idx_es_path
    raw = json.loads(idx_path.read_text(encoding='utf-8'))
    lookup = {}
    for strong, entries in raw.items():
        if not entries:
            continue
        top = entries[0]
        if top.get('count', 0) >= 2:
            lookup[strong] = top['text']
    return lookup


def normalize_strong(s):
    """Normalize strong number for lookup: H0087 -> H87, H8297 -> H8297."""
    s = (s or '').strip()
    if not s:
        return ''
    if s.startswith('H'):
        num = s[1:].lstrip('0') or '0'
        return f'H{num}'
    return s


# ─── LOAD MACULA GLOSSES ─────────────────────────────────────────────────────
def load_macula_glosses(book_code: str):
    """Load Macula morphemes indexed by (ch, vs) for gloss extraction."""
    prefix = book_code + ' '
    index = defaultdict(list)
    found = False
    with open(MACULA_TSV, encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            ref = row.get('ref', '')
            if not ref.startswith(prefix):
                if found:
                    break
                continue
            found = True
            parts = ref[len(prefix):].split('!')
            cv = parts[0]
            ch_vs = cv.split(':')
            if len(ch_vs) != 2:
                continue
            try:
                ch, vs = int(ch_vs[0]), int(ch_vs[1])
            except ValueError:
                continue
            index[(ch, vs)].append({
                'text': row.get('text', ''),
                'pos': row.get('pos', ''),
                'gloss': row.get('gloss', ''),
                'xml_id': row.get('xml:id', ''),
            })
    for k in index:
        index[k].sort(key=lambda m: m['xml_id'])
    return dict(index)


def find_match(morphemes, used, expected_cons):
    """Find first group of consecutive unused morphemes matching expected consonants."""
    for start in range(len(morphemes)):
        if used[start]:
            continue
        acc = ''
        for end in range(start, len(morphemes)):
            if used[end]:
                break
            acc += hc(morphemes[end]['text'])
            if acc == expected_cons:
                return start, end + 1
            if len(acc) > len(expected_cons) + 3:
                break
    return None, None


def get_stem_gloss(morphemes, used, expected_cons):
    """Find matching Macula morphemes and return the stem's English gloss."""
    start, end = find_match(morphemes, used, expected_cons)
    if start is None:
        return ''
    consumed = morphemes[start:end]
    for i in range(start, end):
        used[i] = True
    non_suf = [m for m in consumed if m['pos'] not in SUFFIX_POS]
    if not non_suf:
        return ''
    stem = non_suf[-1]
    return (stem.get('gloss') or '').strip()


# ─── PROCESS VERSE ────────────────────────────────────────────────────────────
def process_verse(verse, dic, strong_idx, macula_morphemes, stats):
    ch = verse.get('chapter', 0)
    vs = verse.get('verse', 0)
    ref = f"{ch}:{vs}"

    macula_used = [False] * len(macula_morphemes) if macula_morphemes else []

    for p in verse.get('pairs', []):
        if (p.get('kind') or 'align') != 'align':
            continue

        for hw in p.get('he_words', []):
            raw = (hw.get('raw') or '').strip()
            if is_meta(raw) or not raw:
                continue

            # ── Fill empty prefix_es ──────────────────────────────
            pf = hw.get('prefix_forms') or []
            pe = hw.get('prefix_es') or []
            pm = hw.get('prefix_morphs') or []
            prefix_changed = False

            for i, form in enumerate(pf):
                if i < len(pe) and (pe[i] or '').strip():
                    continue
                morph = pm[i] if i < len(pm) else ''
                gloss = prefix_gloss(form or '', morph)
                if not gloss:
                    continue
                while len(pe) <= i:
                    pe.append('')
                pe[i] = gloss
                prefix_changed = True
                stats['prefix_es'] += 1
                stats['detail'].append(
                    f"  {ref} raw={raw} prefix_es[{i}]: []→[{gloss}] (form={form})")

            if prefix_changed:
                hw['prefix_es'] = pe

            # ── Fill empty stem es ────────────────────────────────
            existing_es = (hw.get('es') or '').strip()
            if existing_es:
                continue

            he_morph = (hw.get('he_morph') or '').strip()
            if he_morph in SKIP_ES_MORPHS:
                continue

            he_form = (hw.get('he_form') or '').strip()
            strongs = (hw.get('strongs') or '').strip()
            expected = hc(hw.get('full_unicode', ''))
            if not expected:
                expected = catss_to_cons(raw)

            # Source 1: Diccionario Genesis by he_form
            if he_form:
                key1 = strip_cantillation(he_form)
                key2 = hc(he_form)
                es = dic.get(key1) or dic.get(key2)
                if es:
                    hw['es'] = es
                    hw['es_source'] = 'auto:dic_genesis'
                    stats['dic'] += 1
                    stats['detail'].append(
                        f"  {ref} raw={raw} es: []→[{es}] (dic_genesis, form={he_form})")
                    continue

            # Source 2: Strong's index
            if strongs:
                norm = normalize_strong(strongs)
                es = strong_idx.get(norm) or strong_idx.get(strongs)
                if es:
                    hw['es'] = es
                    hw['es_source'] = 'auto:strong_idx'
                    stats['strong'] += 1
                    stats['detail'].append(
                        f"  {ref} raw={raw} es: []→[{es}] (strong_idx, {strongs})")
                    continue

            # Source 3: Macula English gloss
            if macula_morphemes and expected:
                gloss = get_stem_gloss(macula_morphemes, macula_used, expected)
                if gloss:
                    clean = gloss.replace('.', ' ').strip()
                    hw['es'] = f'[EN:{clean}]'
                    hw['es_source'] = 'auto:macula_gloss'
                    stats['macula'] += 1
                    stats['detail'].append(
                        f"  {ref} raw={raw} es: []→[[EN:{clean}]] (macula_gloss)")
                    continue

            stats['unfilled'] += 1
            stats['detail'].append(f"  {ref} raw={raw} es: UNFILLED (form={he_form})")


# ─── CLI ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description='Fill Spanish glosses from cascading sources')
    ap.add_argument('--book', default='genesis', help='slug del libro')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--chapter', type=int, default=0)
    ap.add_argument('--force', action='store_true', help='Bypass Genesis ch 1-15 protection')
    ap.add_argument('-v', '--verbose', action='store_true')
    args = ap.parse_args()

    cfg = resolve(args.book)
    book_code = SLUG_TO_MACULA.get(cfg.slug, cfg.slug.upper()[:3])

    print(f'Cargando fuentes para {cfg.label}...')
    dic = load_dic_genesis()
    print(f'  Diccionario Genesis: {len(dic)} entradas')

    IDX_STRONG_ES = cfg.idx_es_path
    strong_idx = load_strong_idx(IDX_STRONG_ES)
    print(f'  Indice Strong ES:    {len(strong_idx)} numeros')

    macula = load_macula_glosses(book_code)
    print(f'  Macula glosses:      {sum(len(v) for v in macula.values())} morfemas')

    data = json.loads(cfg.final_json_path.read_text(encoding='utf-8'))

    stats = {
        'dic': 0, 'strong': 0, 'macula': 0,
        'prefix_es': 0, 'unfilled': 0,
        'verses': 0, 'detail': [],
    }

    for v in data['verses']:
        ch = v.get('chapter', 0)
        if args.chapter and ch != args.chapter:
            continue
        if cfg.slug == 'genesis' and not args.chapter and not args.force and not is_rules_target(ch):
            continue

        morphemes = macula.get((ch, v.get('verse', 0))) or []
        process_verse(v, dic, strong_idx, morphemes, stats)
        stats['verses'] += 1

    total_es = stats['dic'] + stats['strong'] + stats['macula']
    total_all = total_es + stats['prefix_es']
    mode = 'APLICANDO' if args.apply else 'DRY RUN'

    print(f'\n{"=" * 60}')
    print(f'  {mode} — {cfg.label} — Glosas español interlineal')
    print(f'{"=" * 60}')
    print(f'  Versos procesados:  {stats["verses"]}')
    print(f'  ── Stem es llenados ──')
    print(f'  dic_genesis:        {stats["dic"]}')
    print(f'  strong_idx:         {stats["strong"]}')
    print(f'  macula_gloss [EN]:  {stats["macula"]}')
    print(f'  TOTAL es llenados:  {total_es}')
    print(f'  Sin resolver:       {stats["unfilled"]}')
    print(f'  ── Prefix es ──')
    print(f'  prefix_es llenados: {stats["prefix_es"]}')
    print(f'  ── TOTAL cambios:   {total_all}')

    nd = len(stats['detail'])
    if args.verbose or nd <= 200:
        for d in stats['detail']:
            print(d)
    else:
        print(f'\n  (mostrando 80 de {nd}; usa -v para ver todos)')
        for d in stats['detail'][:80]:
            print(d)
        if nd > 80:
            print(f'  ... y {nd - 80} mas')

    if args.apply and total_all > 0:
        cfg.final_json_path.write_text(
            json.dumps(data, ensure_ascii=False, separators=(',', ':')),
            encoding='utf-8')
        print(f'\n  Guardado: {cfg.final_json_path}')
    elif not args.apply:
        print(f'\n  (uso: python populate_es_glosses.py --book {cfg.slug} --apply)')


if __name__ == '__main__':
    main()
