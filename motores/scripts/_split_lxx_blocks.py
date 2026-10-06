"""
_split_lxx_blocks.py — Split large gk_add blocks into separate pseudo-verses.

When a verse has 30+ gk_add pairs, extract them into a new pseudo-verse
inserted right after the original. The pseudo-verse has is_lxx_add=true
and lxx_add_label for the viewer to render as "ADD+ LXX" section.

Small gk_add blocks (<30 tokens) remain inline within the original verse.

Usage:
    python _split_lxx_blocks.py genesis            # dry-run
    python _split_lxx_blocks.py genesis --apply     # apply
    python _split_lxx_blocks.py genesis --apply --threshold 50
"""
import json, sys, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from book_config import resolve
sys.stdout.reconfigure(encoding='utf-8')

DEFAULT_THRESHOLD = 30


def _unsplit(data: dict) -> int:
    """Merge any existing ADD+ pseudo-verses back into their parent verse."""
    merged = 0
    new_verses = []
    # Index parent verses by (ch, vs) for fast lookup
    parent_map = {}
    for v in data['verses']:
        if v.get('is_lxx_add'):
            continue
        key = (v.get('chapter', 0), v.get('verse', 0))
        parent_map[key] = v
        new_verses.append(v)

    for v in data['verses']:
        if not v.get('is_lxx_add'):
            continue
        key = (v.get('chapter', 0), v.get('verse', 0))
        parent = parent_map.get(key)
        if parent:
            parent['pairs'] = parent.get('pairs', []) + v.get('pairs', [])
            merged += len(v.get('pairs', []))
        else:
            new_verses.append(v)

    data['verses'] = new_verses
    return merged


def split_lxx_blocks(data: dict, threshold: int, dry_run: bool) -> tuple:
    # Always un-split first for idempotency
    unsplit_count = _unsplit(data) if not dry_run else 0

    stats = {'checked': 0, 'split': 0, 'tokens_moved': 0, 'unsplit': unsplit_count}
    examples = []

    new_verses = []

    for v in data['verses']:
        ch = v.get('chapter', 0)
        vs = v.get('verse', 0)
        stats['checked'] += 1

        if v.get('is_lxx_add'):
            new_verses.append(v)
            continue

        pairs = v.get('pairs', [])
        gk_adds = [p for p in pairs if p.get('kind') == 'gk_add']
        non_adds = [p for p in pairs if p.get('kind') != 'gk_add']

        if len(gk_adds) >= threshold:
            stats['split'] += 1
            stats['tokens_moved'] += len(gk_adds)

            gr_preview = ' '.join(
                (a.get('gr_unicode') or '') for a in gk_adds[:5]
            )[:80]
            if len(examples) < 20:
                examples.append(
                    f'  {ch}:{vs} — {len(gk_adds)} gk_add tokens -> ADD+ LXX section')
                examples.append(f'    preview: {gr_preview}...')

            if not dry_run:
                # Keep only non-add pairs in the original verse
                v['pairs'] = non_adds

                # Create pseudo-verse with the gk_add pairs
                pseudo = {
                    'chapter': ch,
                    'verse': vs,
                    'is_lxx_add': True,
                    'lxx_add_label': f'{ch}:{vs} ADD+ LXX',
                    'pairs': gk_adds,
                }
                new_verses.append(v)
                new_verses.append(pseudo)
            else:
                new_verses.append(v)
        else:
            new_verses.append(v)

    if not dry_run:
        data['verses'] = new_verses

    return stats, examples


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('book')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--threshold', type=int, default=DEFAULT_THRESHOLD,
                    help=f'Minimum gk_add tokens to split (default {DEFAULT_THRESHOLD})')
    args = ap.parse_args()

    cfg = resolve(args.book)
    data = json.loads(cfg.final_json_path.read_text(encoding='utf-8'))

    dry_run = not args.apply
    stats, examples = split_lxx_blocks(data, args.threshold, dry_run)

    mode = 'DRY-RUN' if dry_run else 'APPLY'
    print(f'{args.book}: {mode} (threshold={args.threshold})')
    for k, v in sorted(stats.items()):
        print(f'  {k:20s} {v:>6d}')

    if examples:
        print(f'\nBlocks split:')
        for ex in examples:
            print(ex)

    if not dry_run and stats['split'] > 0:
        cfg.final_json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'\nGuardado: {cfg.final_json_path.name}')


if __name__ == '__main__':
    main()
