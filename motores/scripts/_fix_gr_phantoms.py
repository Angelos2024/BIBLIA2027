"""
_fix_gr_phantoms.py — Remove phantom Greek from token-level fields.

Uses the CATSS .par file as ground truth (not pair.gr_unicode which may
already be corrupted by rebuild from phantom token data).

A "phantom" is any Greek word on a token (prefix_gr or gr_word) that does
NOT appear in the ORIGINAL CATSS Greek for that pair.

Philosophy: This is an alignment, not a translation. Only Greek that the
CATSS .par file assigns to a pair should appear on its tokens.

Usage:
    python _fix_gr_phantoms.py genesis            # dry-run
    python _fix_gr_phantoms.py genesis --apply     # apply
"""
import json, sys, argparse, unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from book_config import resolve
from populate_greek_catss import parse_par, _he_match, _clean_he
sys.stdout.reconfigure(encoding='utf-8')


_SKIP_MARKERS = {'—', '---', '----', '-', '–'}

def _norm(s: str) -> str:
    """Normalize Greek for comparison: strip accents, leading dots, lowercase."""
    import re
    s = re.sub(r'^[.…]+', '', s)  # strip leading dots/ellipsis
    s = re.sub(r'[.…]+$', '', s)  # strip trailing dots/ellipsis
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return s.lower().strip()


def _words(s: str) -> set:
    """Split a Greek string into a set of normalized words."""
    if not s or not s.strip():
        return set()
    result = set()
    for w in s.split():
        n = _norm(w)
        if n and n not in _SKIP_MARKERS:
            result.add(n)
    return result


def fix_phantoms(data: dict, par_verses: dict, dry_run: bool) -> dict:
    stats = {
        'prefix_phantom': 0,
        'stem_phantom': 0,
        'stem_subsequent_cleared': 0,
        'pairs_checked': 0,
        'verses_matched': 0,
        'gr_unicode_fixed': 0,
    }
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

        # Two-pointer matching (same as populate_greek_catss)
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

            catss_gr = pa['gr_unicode'].strip()
            if not catss_gr:
                continue

            stats['pairs_checked'] += 1
            allowed = _words(catss_gr)

            he_words = jp.get('he_words', [])
            pair_changed = False

            for hw_idx, hw in enumerate(he_words):
                # ── Check prefix_gr ──
                pfx_list = hw.get('prefix_gr', [])
                if isinstance(pfx_list, list):
                    for i, pg in enumerate(pfx_list):
                        if not isinstance(pg, str) or not pg.strip():
                            continue
                        if pg.strip() in _SKIP_MARKERS:
                            continue
                        pg_ws = _words(pg)
                        if pg_ws and not pg_ws.issubset(allowed):
                            stats['prefix_phantom'] += 1
                            if len(examples) < 15:
                                he_form = hw.get('he_form', '') or hw.get('prefix_forms', [''])[i] if i < len(hw.get('prefix_forms', [])) else ''
                                examples.append(
                                    f'  {ch}:{vs} prefix "{pg}" on he="{he_form}" NOT in catss="{catss_gr}"')
                            if not dry_run:
                                pfx_list[i] = ''
                                pair_changed = True

                # ── Check gr_word ──
                gr = (hw.get('gr_word') or '').strip()
                if not gr or gr == '----':
                    continue

                gr_ws = _words(gr)

                if hw_idx == 0:
                    # First hw: remove individual phantom words
                    if gr_ws and not gr_ws.issubset(allowed):
                        phantom_words = gr_ws - allowed
                        valid_parts = [w for w in gr.split() if _norm(w) in allowed]
                        stats['stem_phantom'] += len(phantom_words)
                        if len(examples) < 15:
                            examples.append(
                                f'  {ch}:{vs} stem "{gr}" has phantoms {phantom_words} NOT in catss="{catss_gr}"')
                        if not dry_run:
                            hw['gr_word'] = ' '.join(valid_parts) if valid_parts else ''
                            pair_changed = True
                else:
                    # Subsequent hw: clear if not in CATSS Greek
                    if gr_ws and not gr_ws.issubset(allowed):
                        stats['stem_subsequent_cleared'] += 1
                        if len(examples) < 15:
                            he_form = hw.get('he_form', '')
                            examples.append(
                                f'  {ch}:{vs} hw[{hw_idx}] "{gr}" on he="{he_form}" NOT in catss="{catss_gr}"')
                        if not dry_run:
                            hw['gr_word'] = ''
                            hw['gr_source'] = 'catss:cleared_phantom'
                            pair_changed = True

            # Fix pair.gr_unicode to match CATSS original
            current_gr_uni = (jp.get('gr_unicode') or '').strip()
            if pair_changed or _norm(current_gr_uni) != _norm(catss_gr):
                if not dry_run:
                    jp['gr_unicode'] = catss_gr
                    stats['gr_unicode_fixed'] += 1

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
    stats, examples = fix_phantoms(data, par_verses, dry_run)

    mode = 'DRY-RUN' if dry_run else 'APPLY'
    print(f'\n{args.book}: {mode}')
    for k, v in sorted(stats.items()):
        print(f'  {k:30s} {v:>6d}')

    if examples:
        print(f'\nExamples:')
        for ex in examples:
            print(ex)

    total = stats['prefix_phantom'] + stats['stem_phantom'] + stats['stem_subsequent_cleared']
    if not dry_run and total > 0:
        cfg.final_json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'\nGuardado: {cfg.final_json_path.name}')
    elif not dry_run and stats['gr_unicode_fixed'] > 0:
        cfg.final_json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'\nGuardado (solo gr_unicode fix): {cfg.final_json_path.name}')


if __name__ == '__main__':
    main()
