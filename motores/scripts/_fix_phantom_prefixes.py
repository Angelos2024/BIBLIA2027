"""
_fix_phantom_prefixes.py — Fix empty prefix_forms that create ghost columns.

When prefix_forms[i] is empty but prefix_gr[i] has Greek,
the viewer renders an empty Hebrew column with orphaned Greek.
Fix: merge the orphaned Greek back into gr_word and remove the
empty prefix slot.

Usage:
    python _fix_phantom_prefixes.py genesis
    python _fix_phantom_prefixes.py genesis --apply
"""
import json, sys, pathlib
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).parent))
sys.stdout.reconfigure(encoding='utf-8')
from book_config import resolve


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('book', nargs='?', default='genesis')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('-v', '--verbose', action='store_true')
    args = parser.parse_args()

    dry_run = not args.apply
    cfg = resolve(args.book)
    data = json.loads(cfg.final_json_path.read_text(encoding='utf-8'))

    print(f"Fix phantom prefixes: {cfg.label} ({'DRY-RUN' if dry_run else 'APPLY'})")
    print("=" * 60)

    stats = Counter()

    for v in data['verses']:
        ch, vs = v.get('chapter'), v.get('verse')
        for pi, p in enumerate(v.get('pairs', [])):
            for hi, hw in enumerate(p.get('he_words', [])):
                pf = hw.get('prefix_forms') or []
                pm = hw.get('prefix_morphs') or []
                pe = hw.get('prefix_es') or []
                pgr = hw.get('prefix_gr') or []
                prefs = hw.get('prefixes') or []

                if not pf:
                    continue

                # Find empty prefix slots
                empty_indices = []
                for i in range(len(pf)):
                    form = (pf[i] if i < len(pf) else '').strip()
                    if not form:
                        empty_indices.append(i)

                if not empty_indices:
                    continue

                stats['hw_with_empty_prefix'] += 1

                # Collect orphaned Greek from empty prefix slots
                orphaned_gr = []
                for i in empty_indices:
                    gr_i = (pgr[i] if i < len(pgr) else '').strip()
                    if gr_i:
                        orphaned_gr.append(gr_i)
                        stats['orphaned_gr_rescued'] += 1

                if args.verbose or (dry_run and stats['hw_with_empty_prefix'] <= 10):
                    ref = f"{ch}:{vs}"
                    print(f"\n  [{ref}] pair[{pi}] hw[{hi}]")
                    print(f"    prefix_forms:  {pf}")
                    print(f"    prefix_morphs: {pm}")
                    print(f"    prefix_gr:     {pgr}")
                    print(f"    he_form:       {hw.get('he_form','')}")
                    print(f"    gr_word:       {hw.get('gr_word','')}")
                    print(f"    empty_indices: {empty_indices}")
                    print(f"    orphaned_gr:   {orphaned_gr}")

                if not dry_run:
                    # Merge orphaned Greek into gr_word (prepend)
                    current_gr = (hw.get('gr_word') or '').strip()
                    if orphaned_gr:
                        merged = ' '.join(orphaned_gr)
                        if current_gr:
                            hw['gr_word'] = merged + ' ' + current_gr
                        else:
                            hw['gr_word'] = merged

                    # Remove empty prefix slots (reverse order to preserve indices)
                    for i in sorted(empty_indices, reverse=True):
                        if i < len(pf):
                            pf.pop(i)
                        if i < len(pm):
                            pm.pop(i)
                        if i < len(pe):
                            pe.pop(i)
                        if i < len(pgr):
                            pgr.pop(i)
                        if i < len(prefs):
                            prefs.pop(i)

                    hw['prefix_forms'] = pf
                    hw['prefix_morphs'] = pm
                    hw['prefix_es'] = pe
                    hw['prefix_gr'] = pgr
                    if prefs:
                        hw['prefixes'] = prefs

                    stats['slots_removed'] += len(empty_indices)

    # Also rebuild pair.gr_unicode after changes
    if not dry_run:
        for v in data['verses']:
            for p in v.get('pairs', []):
                parts = []
                for hw in p.get('he_words', []):
                    for g in (hw.get('prefix_gr') or []):
                        g = (g or '').strip()
                        if g and g != '----':
                            parts.append(g)
                    gr = (hw.get('gr_word') or '').strip()
                    if gr and gr != '----':
                        parts.append(gr)
                p['gr_unicode'] = ' '.join(parts)

    print(f"\n{'='*60}")
    for k, cnt in sorted(stats.items()):
        print(f"  {k:30s} {cnt:>6d}")

    if not dry_run:
        cfg.final_json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"\nGuardado: {cfg.final_json_path}")


if __name__ == '__main__':
    main()
