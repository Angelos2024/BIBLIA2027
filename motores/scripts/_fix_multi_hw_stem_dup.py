"""
_fix_multi_hw_stem_dup.py — Remove duplicated stem Greek across multiple he_words.

Problem: When CATSS maps a compound Hebrew phrase (2+ he_words) to a single
Greek word/phrase, the merge step sometimes copies the same gr_word onto every
he_word stem, producing visual duplication (e.g. חֲמִשָּׁה עָשָׂר both showing
τῇ πεντεκαιδεκάτῃ).

Fix: Within a single align pair, if 2+ he_words carry an identical non-empty
gr_word, keep it on the FIRST he_word and clear the rest (set to "").
This is safe and idempotent — only exact duplicates are collapsed.

Usage:
    python _fix_multi_hw_stem_dup.py 1_reyes            # dry-run
    python _fix_multi_hw_stem_dup.py 1_reyes --apply
"""
import json, sys, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from book_config import resolve
sys.stdout.reconfigure(encoding='utf-8')


def fix_pair(pair) -> int:
    he_words = pair.get('he_words', [])
    if len(he_words) < 2:
        return 0

    # Only consider real stems with Greek
    seen = {}
    fixed = 0
    for hw in he_words:
        gw = (hw.get('gr_word') or '').strip()
        if not gw or gw == '----':
            continue
        key = gw.lower()
        if key in seen:
            # Duplicate of an earlier he_word's stem Greek → clear it
            hw['gr_word'] = ''
            hw['gr_source'] = 'dedup:multi_hw'
            fixed += 1
        else:
            seen[key] = True
    return fixed


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('book')
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    cfg = resolve(args.book)
    data = json.loads(cfg.final_json_path.read_text(encoding='utf-8'))
    dry_run = not args.apply

    total = 0
    pairs_touched = 0
    for v in data['verses']:
        for p in v.get('pairs', []):
            if p.get('kind') == 'gk_add':
                continue
            n = fix_pair(p) if not dry_run else _count_dups(p)
            if n:
                total += n
                pairs_touched += 1

    mode = 'DRY-RUN' if dry_run else 'APPLY'
    print(f'{args.book}: {mode}')
    print(f'  stems cleared (dup): {total}')
    print(f'  pairs touched:       {pairs_touched}')

    if not dry_run and total > 0:
        cfg.final_json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'\nGuardado: {cfg.final_json_path.name}')


def _count_dups(pair) -> int:
    he_words = pair.get('he_words', [])
    if len(he_words) < 2:
        return 0
    seen = set()
    cnt = 0
    for hw in he_words:
        gw = (hw.get('gr_word') or '').strip()
        if not gw or gw == '----':
            continue
        key = gw.lower()
        if key in seen:
            cnt += 1
        else:
            seen.add(key)
    return cnt


if __name__ == '__main__':
    main()
