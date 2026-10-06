"""
_fix_phantom_hw.py — Remove phantom he_words using CATSS word count.

The merge sometimes consumes extra OSHB segments and creates phantom tokens.
This script compares each pair's he_word count against the CATSS .par pair's
expected word count. If there are too many he_words, trim the extras.

Usage:
    python _fix_phantom_hw.py genesis            # dry-run
    python _fix_phantom_hw.py genesis --apply     # apply
"""
import json, sys, argparse, re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from book_config import resolve
from populate_greek_catss import parse_par, _he_match
sys.stdout.reconfigure(encoding='utf-8')


def hc(s: str) -> str:
    """Hebrew consonant skeleton."""
    return re.sub(r'[\u0591-\u05C7\u05BD\u05BF\u200D\u05BE\uFEFF\u034F]', '', s).strip()


def count_catss_stems(he_raw: str) -> int:
    """Count how many stem words a CATSS Hebrew field represents.
    
    CATSS format:
      - 'ZKR' → 1 stem
      - 'H/$MYM' → 1 stem (H/ is prefix)
      - '(L PNY' → 2 stems (space-separated)
      - '^ )LHYM' → 1 stem (^ is continuation marker)
      - ')T/W ^' → 1 stem (^ at end is continuation)
      - 'W/H/B)YM' → 1 stem (multiple prefixes)
    """
    if not he_raw:
        return 0
    
    # Remove continuation markers
    parts = he_raw.replace('^', '').strip().split()
    
    count = 0
    for part in parts:
        if not part:
            continue
        # A "stem" is the last segment after all '/' prefixes
        # But the whole part counts as ONE word regardless of prefixes
        count += 1
    
    return count


def fix_phantom_hw(data: dict, par_verses: dict, dry_run: bool) -> tuple:
    stats = {'checked': 0, 'removed': 0, 'verses_matched': 0}
    examples = []

    for v in data['verses']:
        ch, vs = v.get('chapter', 0), v.get('verse', 0)
        cv = (ch, vs)
        par_pairs = par_verses.get(cv)
        if not par_pairs:
            continue

        stats['verses_matched'] += 1
        par_aligns = [p for p in par_pairs if p['kind'] == 'align']
        json_pairs = [p for p in v.get('pairs', []) if p.get('kind') == 'align']

        # Match JSON pairs to CATSS pairs
        pi = 0
        for jp in json_pairs:
            json_he = jp.get('he', '')
            
            matched_pi = None
            for scan in range(pi, min(pi + 3, len(par_aligns))):
                if _he_match(json_he, par_aligns[scan]['he']):
                    matched_pi = scan
                    break

            if matched_pi is None:
                continue

            pa = par_aligns[matched_pi]
            pi = matched_pi + 1

            catss_he = pa['he']
            expected_stems = count_catss_stems(catss_he)
            actual_hws = len(jp.get('he_words', []))

            stats['checked'] += 1

            if actual_hws > expected_stems and expected_stems > 0:
                excess = actual_hws - expected_stems
                hws = jp['he_words']
                
                for i in range(actual_hws - 1, actual_hws - 1 - excess, -1):
                    if i < 0:
                        break
                    hw = hws[i]
                    hf = hw.get('he_form', '')
                    gr = hw.get('gr_word', '')
                    stats['removed'] += 1
                    if len(examples) < 30:
                        examples.append(
                            f'  {ch}:{vs} pair he="{catss_he}" expected={expected_stems} '
                            f'actual={actual_hws} REMOVING hw[{i}] he="{hf}" gr="{gr}"')

                if not dry_run:
                    # Remove excess he_words from the end
                    jp['he_words'] = hws[:expected_stems]
                    
                    # Rebuild pair.gr_unicode from remaining tokens
                    parts = []
                    for hw in jp['he_words']:
                        for pg in hw.get('prefix_gr', []):
                            if pg and pg.strip() and pg.strip() not in ('', '----'):
                                parts.append(pg.strip())
                        gr = (hw.get('gr_word') or '').strip()
                        if gr and gr != '----':
                            parts.append(gr)
                        prs = hw.get('prs_suffix', {})
                        prs_gr = (prs.get('gr_word') or '').strip()
                        if prs_gr:
                            parts.append(prs_gr)
                    jp['gr_unicode'] = ' '.join(parts) if parts else jp.get('gr_unicode', '')

    return stats, examples


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('book')
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    cfg = resolve(args.book)
    data = json.loads(cfg.final_json_path.read_text(encoding='utf-8'))

    par_verses = parse_par(cfg.par_path, cfg.catss_ref_label)
    print(f'Parsed {len(par_verses)} verses from {cfg.par_path.name}')

    dry_run = not args.apply
    stats, examples = fix_phantom_hw(data, par_verses, dry_run)

    mode = 'DRY-RUN' if dry_run else 'APPLY'
    print(f'\n{args.book}: {mode}')
    for k, v in sorted(stats.items()):
        print(f'  {k:20s} {v:>6d}')

    if examples:
        print(f'\nPhantom he_words:')
        for ex in examples:
            print(ex)

    if not dry_run and stats['removed'] > 0:
        cfg.final_json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'\nGuardado: {cfg.final_json_path.name}')


if __name__ == '__main__':
    main()
