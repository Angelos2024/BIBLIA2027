"""
_fix_morph_class.py — Fix morphological category mismatches using Macula class.

Conservative approach: for each Hebrew stem token, lookup its consonants in
the Macula verse data. If ALL Macula morphemes with those consonants agree on
a class that contradicts the current morph category, AND a donor morph with
the correct category exists elsewhere in the book, fix it.

Does NOT use sequential alignment (too fragile). Uses consonant-based lookup.

Usage:
    python _fix_morph_class.py genesis            # dry-run
    python _fix_morph_class.py genesis --apply     # apply
"""
import json, sys, argparse, re
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent))
from book_config import resolve
sys.stdout.reconfigure(encoding='utf-8')

MACULA_TSV = Path(r'C:\Users\pik_y\Documents\GitHub\Local-consults\estudio\angelos\IdiomaORIGEN\macula-hebrew.tsv')

SLUG_TO_MACULA = {
    "genesis": "GEN", "exodo": "EXO", "levitico": "LEV", "numeros": "NUM",
    "deuteronomio": "DEU", "josue": "JOS", "jueces": "JDG", "rut": "RUT",
    "1_samuel": "1SA", "2_samuel": "2SA",
    "1_reyes": "1KI", "2_reyes": "2KI",
    "1_cronicas": "1CH", "2_cronicas": "2CH",
}

CLASS_TO_MORPH_PREFIX = {
    'num':  'NUM',
    'noun': 'SUBS',
    'verb': 'VERBO',
    'cj':   'CONJ',
    'prep': 'PREP',
    'adj':  'ADJ',
    'advb': 'ADV',
    'intj': 'INTJ',
    'nmpr': 'NPROP',
}

MORPH_PREFIX_TO_CLASS = {}
for cls, pfx in CLASS_TO_MORPH_PREFIX.items():
    MORPH_PREFIX_TO_CLASS[pfx] = cls


def hc(s: str) -> str:
    """Hebrew consonant skeleton: strip niqqud/accents/maqaf."""
    return re.sub(r'[\u0591-\u05C7\u05BD\u05BF\u200D\u05BE\uFEFF\u034F]', '', s).strip()


def morph_category(morph: str) -> str:
    """Extract the top-level morph category."""
    if not morph:
        return ''
    parts = morph.split('.')
    return parts[0].upper()


def load_macula_verse_index(book_code: str) -> dict:
    """Load Macula indexed by (ch,vs) → list of {class, text, cons}."""
    result = {}
    with open(MACULA_TSV, encoding='utf-8') as f:
        header = f.readline().strip().split('\t')
        ref_i = header.index('ref')
        cls_i = header.index('class')
        txt_i = header.index('text')
        for line in f:
            cols = line.strip().split('\t')
            if len(cols) <= max(ref_i, cls_i, txt_i):
                continue
            ref = cols[ref_i]
            if not ref.startswith(book_code + ' '):
                continue
            parts = ref.split(' ', 1)[1]
            cv = parts.split('!')[0]
            ch_vs = cv.split(':')
            if len(ch_vs) != 2:
                continue
            try:
                ch, vs = int(ch_vs[0]), int(ch_vs[1])
            except ValueError:
                continue
            text = cols[txt_i]
            result.setdefault((ch, vs), []).append({
                'class': cols[cls_i],
                'text': text,
                'cons': hc(text),
            })
    return result


def fix_morph(data: dict, mac_verses: dict, dry_run: bool):
    stats = {'checked': 0, 'fixed': 0, 'no_donor': 0}
    examples = []

    # Pass 1: build (cons) → {morph_category: [full_morphs]} across ALL verses
    # This gives us donor morphs for any form
    morph_donors = defaultdict(lambda: defaultdict(list))
    for v in data['verses']:
        for p in v.get('pairs', []):
            if p.get('kind') != 'align':
                continue
            for hw in p.get('he_words', []):
                hf = (hw.get('he_form') or '').strip()
                hm = (hw.get('he_morph') or '').strip()
                if hf and hm:
                    cons = hc(hf)
                    cat = morph_category(hm)
                    morph_donors[cons][cat].append(hm)

    # Pass 2: for each stem token, check against Macula class (consonant lookup)
    for v in data['verses']:
        ch, vs = v.get('chapter', 0), v.get('verse', 0)
        mac_list = mac_verses.get((ch, vs), [])
        if not mac_list:
            continue

        # Build consonant → set of classes from Macula for this verse
        cons_to_classes = defaultdict(set)
        for m in mac_list:
            if m['cons']:
                cons_to_classes[m['cons']].add(m['class'])

        for p in v.get('pairs', []):
            if p.get('kind') != 'align':
                continue
            for hw in p.get('he_words', []):
                hf = (hw.get('he_form') or '').strip()
                hm = (hw.get('he_morph') or '').strip()
                if not hf or not hm:
                    continue

                stats['checked'] += 1
                cons = hc(hf)
                if not cons:
                    continue

                mac_classes = cons_to_classes.get(cons, set())
                if not mac_classes:
                    continue

                # Skip ambiguous: if Macula has multiple classes for same form, skip
                if len(mac_classes) > 1:
                    continue

                mac_class = next(iter(mac_classes))
                expected_prefix = CLASS_TO_MORPH_PREFIX.get(mac_class)
                if not expected_prefix:
                    continue

                current_cat = morph_category(hm)
                if current_cat == expected_prefix:
                    continue  # already correct

                # Skip if current morph is a PRS (pronominal suffix) — these are special
                if hm.startswith('PRS') or '+RBS' in hm or '+' in hm:
                    continue

                # Skip ambiguous class pairs (Macula categories that overlap with OSHB)
                if mac_class in ('art', 'pron', 'ptcl'):
                    continue

                # PART ↔ CONJ overlap (particles and conjunctions are ambiguous)
                if (current_cat == 'PART' and expected_prefix == 'CONJ') or \
                   (current_cat == 'CONJ' and expected_prefix == 'PART'):
                    continue

                # ADJ ↔ SUBS overlap (participles can be either)
                if (current_cat == 'ADJ' and expected_prefix == 'SUBS') or \
                   (current_cat == 'SUBS' and expected_prefix == 'ADJ'):
                    continue

                # VERBO → ADJ is fine (participle as adjective)
                if current_cat == 'VERBO' and expected_prefix == 'ADJ':
                    continue

                # NPROP ↔ SUBS overlap (proper nouns vs common nouns)
                if (current_cat == 'NPROP' and expected_prefix == 'SUBS') or \
                   (current_cat == 'SUBS' and expected_prefix == 'NPROP'):
                    continue

                # Skip R-codes (RBP*, RBS*) which are compound morph codes
                if current_cat.startswith('RB'):
                    continue

                # Skip VERBO → SUBS and SUBS → VERBO when participle involved
                if (current_cat == 'SUBS' and expected_prefix == 'VERBO') or \
                   (current_cat == 'VERBO' and expected_prefix == 'SUBS'):
                    if 'PTCA' in hm or 'PTCP' in hm or 'INFC' in hm:
                        continue

                # Skip OMSA and other short codes that are ordinals
                if hm in ('OMSA', 'OFSA', 'OMPA', 'OFPA'):
                    continue

                # Find donor morph with the correct category for this form
                donors = morph_donors.get(cons, {}).get(expected_prefix, [])
                if donors:
                    # Pick the most frequent donor
                    from collections import Counter
                    donor = Counter(donors).most_common(1)[0][0]
                    stats['fixed'] += 1
                    if len(examples) < 30:
                        examples.append(
                            f'  {ch}:{vs} "{hf}" class={mac_class}: [{hm}] -> [{donor}]')
                    if not dry_run:
                        hw['he_morph'] = donor
                else:
                    stats['no_donor'] += 1
                    if len(examples) < 30:
                        examples.append(
                            f'  {ch}:{vs} "{hf}" class={mac_class} morph={hm} NO DONOR (expected {expected_prefix}*)')

    return stats, examples


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('book')
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    cfg = resolve(args.book)
    data = json.loads(cfg.final_json_path.read_text(encoding='utf-8'))

    book_code = SLUG_TO_MACULA.get(cfg.slug)
    if not book_code:
        print(f'No Macula code for {cfg.slug}')
        return

    print(f'Loading Macula for {cfg.label} ({book_code})...')
    mac_verses = load_macula_verse_index(book_code)
    print(f'Loaded {len(mac_verses)} verses')

    dry_run = not args.apply
    stats, examples = fix_morph(data, mac_verses, dry_run)

    mode = 'DRY-RUN' if dry_run else 'APPLY'
    print(f'\n{args.book}: {mode}')
    for k, v in sorted(stats.items()):
        print(f'  {k:20s} {v:>6d}')

    if examples:
        print(f'\nExamples:')
        for ex in examples:
            print(ex)

    if not dry_run and stats['fixed'] > 0:
        cfg.final_json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'\nGuardado: {cfg.final_json_path.name}')


if __name__ == '__main__':
    main()
