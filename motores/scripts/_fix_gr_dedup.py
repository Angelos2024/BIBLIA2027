"""
_fix_gr_dedup.py - Remove duplicate Greek at pair level.

When hw.gr_word already has Greek assigned, pair.gr_unicode is redundant
and causes double-rendering in the viewer. Clear it.

Usage:
    python _fix_gr_dedup.py genesis
    python _fix_gr_dedup.py genesis --apply
"""
import json, sys, pathlib
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from book_config import resolve
sys.stdout.reconfigure(encoding='utf-8')


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('book', nargs='?', default='genesis')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()

    dry_run = not args.apply
    cfg = resolve(args.book)
    data = json.loads(cfg.final_json_path.read_text(encoding='utf-8'))

    print(f"Dedup Greek: {cfg.label} ({'DRY-RUN' if dry_run else 'APPLY'})")
    print("=" * 50)

    stats = Counter()

    for v in data['verses']:
        for p in v.get('pairs', []):
            pair_gr = (p.get('gr_unicode') or '').strip()
            if not pair_gr:
                continue

            # Check if any hw already has Greek
            hws_with_gr = []
            for hw in p.get('he_words', []):
                gr = (hw.get('gr_word') or '').strip()
                if gr and gr != '----':
                    hws_with_gr.append(gr)

            if hws_with_gr:
                stats['pair_gr_cleared'] += 1
                if not dry_run:
                    p['gr_unicode'] = ''

            # Also clear other redundant pair-level Greek fields
            for fld in ('gr', 'gr_tokens', 'morph_summary', 'lemma_main', 'lemma_unicode'):
                if p.get(fld) and str(p[fld]).strip():
                    stats['pair_field_cleared'] += 1
                    if not dry_run:
                        p[fld] = '' if isinstance(p[fld], str) else []

    for k, cnt in sorted(stats.items()):
        print(f"  {k:25s} {cnt:>6d}")

    if not dry_run and stats:
        cfg.final_json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"\nGuardado: {cfg.final_json_path}")


if __name__ == '__main__':
    main()
