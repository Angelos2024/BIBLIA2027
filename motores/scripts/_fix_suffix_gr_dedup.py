"""
_fix_suffix_gr_dedup.py - Clear duplicate Greek in prs_suffix.

When hw.gr_word == hw.prs_suffix.gr_word, the suffix Greek is redundant
and causes double-rendering. Clear prs_suffix.gr_word in those cases.

Usage:
    python _fix_suffix_gr_dedup.py genesis
    python _fix_suffix_gr_dedup.py genesis --apply
"""
import json, sys, pathlib, unicodedata
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

    print(f"Fix suffix Greek dedup: {cfg.label} ({'DRY-RUN' if dry_run else 'APPLY'})")
    print("=" * 50)

    stats = Counter()

    for v in data['verses']:
        for p in v.get('pairs', []):
            for hw in p.get('he_words', []):
                prs = hw.get('prs_suffix')
                if not prs or not isinstance(prs, dict):
                    continue

                main_gr = (hw.get('gr_word') or '').strip()
                suf_gr = (prs.get('gr_word') or '').strip()
                main_nfc = unicodedata.normalize('NFC', main_gr)
                suf_nfc = unicodedata.normalize('NFC', suf_gr)

                if suf_gr:
                    if suf_nfc == main_nfc:
                        stats['exact_dup_cleared'] += 1
                        if not dry_run:
                            prs['gr_word'] = ''
                    elif main_nfc and suf_nfc in main_nfc:
                        stats['contained_dup_cleared'] += 1
                        if not dry_run:
                            prs['gr_word'] = ''
                    else:
                        stats['suffix_gr_kept'] += 1

    for k, cnt in sorted(stats.items()):
        print(f"  {k:25s} {cnt:>6d}")

    if not dry_run and stats:
        cfg.final_json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"\nGuardado: {cfg.final_json_path}")


if __name__ == '__main__':
    main()
