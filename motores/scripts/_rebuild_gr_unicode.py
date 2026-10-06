"""
_rebuild_gr_unicode.py - Rebuild pair.gr_unicode from hw-level Greek data.

pair.gr_unicode was cleared to fix visual duplication, but the viewer's
running LXX text and word count depend on it. This script rebuilds it
from the authoritative hw-level fields: prefix_gr + gr_word.

Usage:
    python _rebuild_gr_unicode.py genesis
    python _rebuild_gr_unicode.py genesis --apply
"""
import json, sys, pathlib
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from book_config import resolve
sys.stdout.reconfigure(encoding='utf-8')


def collect_pair_greek(pair):
    """Collect all Greek from hw-level data into a single string for pair.gr_unicode."""
    parts = []
    for hw in pair.get('he_words', []):
        pgr = hw.get('prefix_gr') or []
        for g in pgr:
            g = (g or '').strip()
            if g and g != '----':
                parts.append(g)

        gr = (hw.get('gr_word') or '').strip()
        if gr and gr != '----':
            parts.append(gr)

    return ' '.join(parts)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('book', nargs='?', default='genesis')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()

    dry_run = not args.apply
    cfg = resolve(args.book)
    data = json.loads(cfg.final_json_path.read_text(encoding='utf-8'))

    print(f"Rebuild pair.gr_unicode: {cfg.label} ({'DRY-RUN' if dry_run else 'APPLY'})")
    print("=" * 60)

    stats = Counter()

    for v in data['verses']:
        for p in v.get('pairs', []):
            # Los pares gk_add llevan el griego añadido en pair.gr_unicode y NO
            # tienen he_words: reconstruirlos los borraría. Nunca tocarlos.
            if p.get('kind') == 'gk_add':
                stats['gkadd_skipped'] += 1
                continue
            old_gr = (p.get('gr_unicode') or '').strip()
            new_gr = collect_pair_greek(p)

            if new_gr and not old_gr:
                stats['rebuilt_from_empty'] += 1
            elif new_gr and old_gr and new_gr != old_gr:
                stats['updated'] += 1
            elif not new_gr and not old_gr:
                stats['both_empty'] += 1
            elif new_gr == old_gr:
                stats['unchanged'] += 1
            elif not new_gr and old_gr:
                stats['cleared'] += 1

            if not dry_run:
                p['gr_unicode'] = new_gr

    for k, cnt in sorted(stats.items()):
        print(f"  {k:25s} {cnt:>6d}")

    total_gr = stats.get('rebuilt_from_empty', 0) + stats.get('updated', 0) + stats.get('unchanged', 0)
    print(f"\n  Total pairs with Greek: {total_gr}")

    if not dry_run:
        cfg.final_json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"\nGuardado: {cfg.final_json_path}")


if __name__ == '__main__':
    main()
