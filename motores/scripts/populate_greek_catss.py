"""
populate_greek_catss.py - Populate Greek LXX from CATSS .par file.

Reads the .par file for any book, converts BETA code to Unicode Greek,
and maps each alignment to <book>_final.json pairs.

Usage:
    python populate_greek_catss.py genesis              # dry-run Genesis ch 16-50
    python populate_greek_catss.py exodo --apply        # apply Exodus all chapters
    python populate_greek_catss.py exodo --chapter 5    # single chapter
"""
import json, sys, re, pathlib, unicodedata
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from book_config import resolve
sys.stdout.reconfigure(encoding="utf-8")

PAR_FILE = pathlib.Path(
    r"C:\Users\pik_y\Documents\GitHub\Local-consults\estudio\angelos"
    r"\catss-sample\01.Genesis.par"
)  # legacy default; main() uses book_config paths

# ---------------------------------------------------------------------------
# BETA code → Unicode Greek converter
# ---------------------------------------------------------------------------

_BETA_MAP = {
    'A': 'α', 'B': 'β', 'G': 'γ', 'D': 'δ', 'E': 'ε',
    'Z': 'ζ', 'H': 'η', 'Q': 'θ', 'I': 'ι', 'K': 'κ',
    'L': 'λ', 'M': 'μ', 'N': 'ν', 'C': 'ξ', 'O': 'ο',
    'P': 'π', 'R': 'ρ', 'S': 'σ', 'T': 'τ', 'U': 'υ',
    'F': 'φ', 'X': 'χ', 'Y': 'ψ', 'W': 'ω',
}

_BETA_UPPER = {k: v.upper() for k, v in _BETA_MAP.items()}

_ACCENTS = {
    ')': '\u0313',  # smooth breathing (psili)
    '(': '\u0314',  # rough breathing (dasia)
    '/': '\u0301',  # acute accent (oxia)
    '\\': '\u0300', # grave accent (varia)
    '=': '\u0342',  # circumflex (perispomeni)
    '|': '\u0345',  # iota subscript (ypogegrammeni)
    '+': '\u0308',  # diaeresis
}


def beta_to_unicode(beta: str) -> str:
    """Convert CATSS BETA code to Unicode Greek."""
    if not beta or beta == '---':
        return beta or ''

    # Remove apparatus markers
    beta = re.sub(r'\^', '', beta)
    beta = beta.strip()
    if not beta:
        return ''

    result = []
    i = 0
    upper_next = False

    while i < len(beta):
        ch = beta[i]

        if ch == '*':
            upper_next = True
            i += 1
            continue

        if ch in _BETA_MAP:
            letter = _BETA_UPPER[ch] if upper_next else _BETA_MAP[ch]
            upper_next = False
            result.append(letter)
            i += 1
            continue

        if ch in _ACCENTS:
            result.append(_ACCENTS[ch])
            i += 1
            continue

        if ch in (' ', '-', ',', '.', ';', ':', "'", '"'):
            result.append(ch)
            upper_next = False
            i += 1
            continue

        # Skip unknown characters
        i += 1

    text = ''.join(result)

    # Fix final sigma: σ at end of word → ς
    text = re.sub(r'σ(?=\s|$|[,.:;])', 'ς', text)
    text = re.sub(r'σ(?=[^α-ωάέήίόύώϊϋΐΰᾶῆῖῦῶἀἐἠἰὀὐἁἑἡἱὁὑ\u0300-\u036f]|$)', 'ς', text)

    # Normalize to NFC
    text = unicodedata.normalize('NFC', text)
    return text.strip()


# ---------------------------------------------------------------------------
# Parse .par file
# ---------------------------------------------------------------------------

def parse_par(par_path: pathlib.Path, ref_label: str = None) -> dict[tuple[int, int], list[dict]]:
    """Parse CATSS .par file into {(chapter, verse): [pairs]}.

    ref_label: book prefix in .par (e.g. 'Gen', 'Exod'). Auto-detected if None.
    """
    verses = {}
    current_cv = None
    # Auto-detect ref label from first reference line if not provided
    if not ref_label:
        with open(par_path, encoding='utf-8') as f:
            for probe in f:
                pm = re.match(r'^(\w+)\s+\d+:\d+', probe)
                if pm:
                    ref_label = pm.group(1)
                    break
        if not ref_label:
            ref_label = 'Gen'

    # Capítulo opcional: libros de un solo capítulo (Abdías) usan "Obad N".
    ref_re = re.compile(rf'^{re.escape(ref_label)}\s+(?:(\d+):)?(\d+)')

    with open(par_path, encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n\r')

            m = ref_re.match(line)
            if m:
                current_cv = (int(m.group(1)) if m.group(1) else 1, int(m.group(2)))
                if current_cv not in verses:
                    verses[current_cv] = []
                continue

            if not line.strip() or current_cv is None:
                continue

            # Split Hebrew and Greek by tab
            parts = line.split('\t', 1)
            he_raw = parts[0].strip()
            gr_raw = parts[1].strip() if len(parts) > 1 else ''

            # Determine kind
            if he_raw.startswith('--+'):
                kind = 'gk_add'
                he_clean = ''
                # Clean apparatus references from Greek
                gr_clean = re.sub(r"^['\s]*", '', gr_raw)
            elif gr_raw == '---':
                kind = 'omit'
                he_clean = he_raw
                gr_clean = ''
            else:
                kind = 'align'
                he_clean = he_raw
                gr_clean = gr_raw

            # Remove apparatus references like =;W/YHY <1.7>
            he_clean = re.sub(r'\s*=.*$', '', he_clean).strip()
            he_clean = re.sub(r'\s*<[\d.:]+>.*$', '', he_clean).strip()

            gr_unicode = beta_to_unicode(gr_clean)

            verses[current_cv].append({
                'he': he_clean,
                'gr_beta': gr_clean,
                'gr_unicode': gr_unicode,
                'kind': kind,
            })

    return verses


# ---------------------------------------------------------------------------
# Map .par pairs to genesis_final.json
# ---------------------------------------------------------------------------

_STRIP_APPARATUS = re.compile(r'\s*=[^\s].*$')
_STRIP_BRACES = re.compile(r'\{[^}]*\}')


def _clean_he(he: str) -> str:
    """Normalize Hebrew field for matching: strip apparatus and metadata."""
    he = _STRIP_APPARATUS.sub('', he)
    he = _STRIP_BRACES.sub('', he)
    he = re.sub(r'\s*#\s*$', '', he)
    return he.strip()


def _he_match(json_he: str, par_he: str) -> bool:
    """Check if Hebrew fields match (with normalization)."""
    a = _clean_he(json_he)
    b = _clean_he(par_he)
    if a == b:
        return True
    if a.replace('/', '') == b.replace('/', ''):
        return True
    # Try stripping caret transposition markers
    a2 = a.replace('^', '').strip()
    b2 = b.replace('^', '').strip()
    if a2 == b2 or a2.replace('/', '') == b2.replace('/', ''):
        return True
    return False


def populate(data: dict, par_verses: dict, dry_run: bool, ch_min: int, ch_max: int):
    """Map parsed .par Greek to genesis_final.json pairs.

    ch_min/ch_max control which chapters get ALIGNMENT Greek filled.
    gk_add injection always covers ALL chapters (it only adds new pairs,
    never modifies existing data, so it's safe even in protected ranges).
    """
    stats = defaultdict(int)

    for v in data['verses']:
        # Skip ADD+ LXX pseudo-verses (handled by _split_lxx_blocks.py)
        if v.get('is_lxx_add'):
            continue

        ch = v.get('chapter', 0)
        vs = v.get('verse', 0)

        cv = (ch, vs)
        par_pairs = par_verses.get(cv)
        if not par_pairs:
            if ch_min <= ch <= ch_max:
                stats['verse_missing_par'] += 1
            continue

        json_pairs = v.get('pairs', [])

        par_aligns = [p for p in par_pairs if p['kind'] == 'align']
        par_adds = [p for p in par_pairs if p['kind'] == 'gk_add']

        json_aligns = [(i, p) for i, p in enumerate(json_pairs) if p.get('kind') == 'align']
        json_gkadds = [(i, p) for i, p in enumerate(json_pairs) if p.get('kind') == 'gk_add']

        # ── Alignment Greek: only within ch_min..ch_max ──
        if ch_min <= ch <= ch_max:
            pi = 0
            for ji_idx, (ji, jp) in enumerate(json_aligns):
                json_he = jp.get('he', '')

                matched_pi = None
                for scan in range(pi, min(pi + 3, len(par_aligns))):
                    if _he_match(json_he, par_aligns[scan]['he']):
                        matched_pi = scan
                        break

                if matched_pi is None:
                    stats['he_mismatch'] += 1
                    continue

                pa = par_aligns[matched_pi]
                pi = matched_pi + 1

                gr_uni = pa['gr_unicode']

                if not gr_uni:
                    stats['omission'] += 1
                    if not dry_run:
                        jp['gr_unicode'] = ''
                        for hw in jp.get('he_words', []):
                            raw = (hw.get('raw') or '').strip()
                            if raw and raw != 'GKADD' and not raw.startswith(('=', '{', '<', '*', '--', '.')):
                                hw['gr_word'] = '----'
                                hw['gr_source'] = 'catss:omit'
                    continue

                stats['align_filled'] += 1
                if not dry_run:
                    jp['gr_unicode'] = gr_uni

                    he_words = [hw for hw in jp.get('he_words', [])
                               if (hw.get('raw') or '').strip()
                               and (hw.get('raw') or '').strip() != 'GKADD'
                               and not (hw.get('raw') or '').startswith(('=', '{', '<', '*', '--', '.'))]

                    if len(he_words) == 1:
                        he_words[0]['gr_word'] = gr_uni
                        he_words[0]['gr_source'] = 'catss:par'
                    elif he_words:
                        he_words[0]['gr_word'] = gr_uni
                        he_words[0]['gr_source'] = 'catss:par'
                        for hw in he_words[1:]:
                            hw['gr_word'] = ''
                            hw['gr_source'] = 'catss:par_shared'

        # ── gk_add: ALWAYS process ALL chapters ──
        if json_gkadds:
            for idx, (ji, jp) in enumerate(json_gkadds):
                if idx >= len(par_adds):
                    break
                pa = par_adds[idx]
                gr_uni = pa['gr_unicode']
                if gr_uni:
                    stats['gkadd_filled'] += 1
                    if not dry_run:
                        jp['gr_unicode'] = gr_uni
                        for hw in jp.get('he_words', []):
                            if (hw.get('raw') or '') == 'GKADD':
                                hw['gr_word'] = gr_uni
                                hw['gr_source'] = 'catss:add'
        elif par_adds and not dry_run:
            for pa in par_adds:
                gr_uni = pa['gr_unicode']
                if not gr_uni:
                    continue
                new_pair = {
                    'kind': 'gk_add',
                    'he': '',
                    'gr_unicode': gr_uni,
                    'he_words': [{
                        'raw': 'GKADD',
                        'he_form': '',
                        'he_morph': '',
                        'es': '',
                        'gr_word': gr_uni,
                        'gr_source': 'catss:add',
                        'prefix_gr': [],
                        'prefix_forms': [],
                        'prefix_morphs': [],
                        'prefix_es': [],
                    }],
                }
                json_pairs.append(new_pair)
                stats['gkadd_filled'] = stats.get('gkadd_filled', 0) + 1

        # Count omissions from .par
        if ch_min <= ch <= ch_max:
            for pa in par_pairs:
                if pa['kind'] == 'omit':
                    stats['par_omit_total'] += 1

    return stats


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('book', nargs='?', default='genesis',
                        help='Book slug: genesis, exodo, levitico, ...')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--chapter', type=int, default=0)
    parser.add_argument('--force', action='store_true', help='Bypass Genesis ch 1-15 protection')
    args = parser.parse_args()

    dry_run = not args.apply
    cfg = resolve(args.book)

    ch_min = args.chapter if args.chapter else 1
    ch_max = args.chapter if args.chapter else cfg.chapters

    # Genesis special case: only ch 16-50 (1-15 protected) unless --force
    if cfg.slug == 'genesis' and not args.chapter and not args.force:
        ch_min = 16

    data = json.loads(cfg.final_json_path.read_text(encoding='utf-8'))

    par_path = cfg.par_path
    print(f"Parsing {par_path.name} (ref={cfg.catss_ref_label})...")
    par_verses = parse_par(par_path, cfg.catss_ref_label)
    print(f"  {len(par_verses)} verses parsed from .par")

    print(f"\n{'DRY-RUN' if dry_run else 'APPLY'} - {cfg.label} Greek ch {ch_min}-{ch_max}")
    print("=" * 50)

    stats = populate(data, par_verses, dry_run, ch_min, ch_max)

    for k, cnt in sorted(stats.items()):
        print(f"  {k:25s} {cnt:>6d}")

    gr_filled = 0
    gr_total = 0
    omissions = 0
    gkadd_filled = 0
    for v in data['verses']:
        ch = v.get('chapter', 0)
        if ch < ch_min or ch > ch_max:
            continue
        for p in v.get('pairs', []):
            for hw in p.get('he_words', []):
                raw = (hw.get('raw') or '').strip()
                if raw == 'GKADD':
                    if hw.get('gr_word'):
                        gkadd_filled += 1
                    continue
                if not raw or raw.startswith(('=', '{', '<', '*', '--', '.')):
                    continue
                gr_total += 1
                gw = (hw.get('gr_word') or '').strip()
                if gw and gw != '----':
                    gr_filled += 1
                elif gw == '----':
                    omissions += 1

    cov = gr_filled / gr_total * 100 if gr_total else 0
    print(f"\nCobertura {cfg.label} ch {ch_min}-{ch_max}:")
    print(f"  Tokens hebreos: {gr_total}")
    print(f"  Con griego:     {gr_filled} ({cov:.1f}%)")
    print(f"  Omisiones:      {omissions}")
    print(f"  GKADD:          {gkadd_filled}")
    print(f"  Sin asignar:    {gr_total - gr_filled - omissions}")

    if not dry_run and (stats.get('align_filled', 0) or stats.get('gkadd_filled', 0)):
        cfg.final_json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8'
        )
        print(f"\nGuardado en {cfg.final_json_path}")


if __name__ == '__main__':
    main()
