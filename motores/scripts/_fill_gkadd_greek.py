"""
_fill_gkadd_greek.py — Fill missing Greek in gk_add pairs from CATSS .par file.

Works on _final.json, including pseudo-verses (is_lxx_add).
Matches gk_add pairs positionally per verse.

Usage:
    python _fill_gkadd_greek.py 1_reyes            # dry-run
    python _fill_gkadd_greek.py 1_reyes --apply
"""
import json, sys, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from book_config import resolve
from populate_greek_catss import parse_par
sys.stdout.reconfigure(encoding='utf-8')


def fill_gkadd_greek(data: dict, par_verses: dict, dry_run: bool) -> dict:
    stats = {'verses': 0, 'pairs_checked': 0, 'filled': 0, 'already_ok': 0}

    # Group all gk_add pairs per (ch, vs) across all verses (including pseudo)
    verse_adds = {}
    for v in data['verses']:
        ch = v.get('chapter', 0)
        vs = v.get('verse', 0)
        key = (ch, vs)
        for p in v.get('pairs', []):
            if p.get('kind') == 'gk_add':
                verse_adds.setdefault(key, []).append(p)

    for cv, json_adds in sorted(verse_adds.items()):
        par_pairs = par_verses.get(cv)
        if not par_pairs:
            continue

        par_adds = [p for p in par_pairs if p['kind'] == 'gk_add']
        stats['verses'] += 1

        for idx, jp in enumerate(json_adds):
            stats['pairs_checked'] += 1
            if (jp.get('gr_unicode') or '').strip():
                stats['already_ok'] += 1
                continue

            if idx < len(par_adds):
                gr_uni = par_adds[idx]['gr_unicode']
                if gr_uni:
                    stats['filled'] += 1
                    if not dry_run:
                        jp['gr_unicode'] = gr_uni
                        for hw in jp.get('he_words', []):
                            if (hw.get('raw') or '') == 'GKADD':
                                hw['gr_word'] = gr_uni
                                hw['gr_source'] = 'catss:add'

    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('book')
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    cfg = resolve(args.book)
    data = json.loads(cfg.final_json_path.read_text(encoding='utf-8'))
    par_verses = parse_par(cfg.par_path, cfg.catss_ref_label)

    dry_run = not args.apply
    stats = fill_gkadd_greek(data, par_verses, dry_run)

    mode = 'DRY-RUN' if dry_run else 'APPLY'
    print(f'{args.book}: {mode}')
    for k, v in sorted(stats.items()):
        print(f'  {k:20s} {v:>6d}')

    if not dry_run and stats['filled'] > 0:
        cfg.final_json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'\nGuardado: {cfg.final_json_path.name}')


if __name__ == '__main__':
    main()
