"""
_fix_crossed_alignment.py — Fix crossed Greek alignment on pronouns/object markers.

When CATSS maps positionally and assigns divine-name Greek (ὁ θεός, κύριος)
to a pronoun/object-marker (אֹתוֹ, אֹתָם, etc.) while the actual divine-name
Hebrew word (אֱלֹהִים, יְהוָה, אֲדֹנָי) has empty Greek, swap them.

General pattern detected:
  - hw_A is a pronoun or object marker (את+suffix, הוּא, etc.)
  - hw_A.gr_word contains a divine/noun that semantically belongs to hw_B
  - hw_B is a noun (אֱלֹהִים, יְהוָה, etc.) with empty gr_word
  - hw_B immediately follows hw_A in the same verse

This is a CATSS positional alignment override for semantic correctness.

Usage:
    python _fix_crossed_alignment.py genesis            # dry-run
    python _fix_crossed_alignment.py genesis --apply     # apply
"""
import json, sys, argparse, re, unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from book_config import resolve
sys.stdout.reconfigure(encoding='utf-8')


def hc(s: str) -> str:
    """Hebrew consonant skeleton."""
    return re.sub(r'[\u0591-\u05C7\u05BD\u05BF\u200D\u05BE\uFEFF\u034F]', '', s).strip()


# Object markers / pronouns that typically don't carry their own Greek noun
_OBJ_FORMS = {
    'את', 'אות', 'את', 'אתו', 'אתם', 'אתה', 'אתן', 'אתך', 'אתי',
    'אתנו', 'אתכם', 'אתהן', 'אתהם',
}

_OBJ_MORPH_STARTS = ('PART.OBJ', 'PRS')

# Greek that indicates divine names
_DIVINE_GR = {'θεος', 'θεου', 'θεω', 'θεον', 'κυριος', 'κυριου', 'κυριω', 'κυριον'}

# Hebrew divine names
_DIVINE_HE_CONS = {'אלהים', 'יהוה', 'אדני', 'אל', 'שדי', 'אלוה'}


def _norm_gr(s: str) -> str:
    """Normalize Greek: strip accents, lowercase."""
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return s.lower().strip()


def _gr_has_divine(gr: str) -> bool:
    """Check if Greek contains a divine name."""
    for w in gr.split():
        nw = _norm_gr(w)
        # Remove article
        nw = re.sub(r'^[οοὁἡτ][ηονυ]?[νυσ]?$', '', nw)  # articles
        if nw in _DIVINE_GR:
            return True
    # Also check without splitting (for compound forms)
    full = _norm_gr(gr)
    for dg in _DIVINE_GR:
        if dg in full:
            return True
    return False


def _is_obj_marker(hw: dict) -> bool:
    """Check if a he_word is an object marker or pronoun."""
    morph = (hw.get('he_morph') or '').strip()
    if any(morph.startswith(p) for p in _OBJ_MORPH_STARTS):
        return True
    form = hc(hw.get('he_form') or '')
    if form in _OBJ_FORMS:
        return True
    raw = hc(hw.get('raw') or '').replace('/', '')
    if raw in _OBJ_FORMS:
        return True
    return False


def _is_divine_he(hw: dict) -> bool:
    """Check if a he_word is a divine name."""
    form = hc(hw.get('he_form') or '')
    return form in _DIVINE_HE_CONS


def fix_crossed(data: dict, dry_run: bool) -> tuple:
    stats = {'fixed': 0, 'checked': 0}
    examples = []

    for v in data['verses']:
        ch, vs = v.get('chapter', 0), v.get('verse', 0)
        pairs = [p for p in v.get('pairs', []) if p.get('kind') == 'align']

        # Flatten all he_words with pair reference
        flat = []
        for pi, p in enumerate(pairs):
            for hi, hw in enumerate(p.get('he_words', [])):
                flat.append((pi, hi, hw, p))

        stats['checked'] += len(flat)

        for idx in range(len(flat) - 1):
            pi_a, hi_a, hw_a, p_a = flat[idx]
            pi_b, hi_b, hw_b, p_b = flat[idx + 1]

            gr_a = (hw_a.get('gr_word') or '').strip()
            gr_b = (hw_b.get('gr_word') or '').strip()

            if not gr_a or gr_a == '----':
                continue
            if gr_b and gr_b != '----':
                continue

            # Pattern: hw_a is object/pronoun with divine Greek,
            #          hw_b is divine name with empty Greek
            if _is_obj_marker(hw_a) and _gr_has_divine(gr_a) and _is_divine_he(hw_b):
                stats['fixed'] += 1
                he_a = hw_a.get('he_form', '')
                he_b = hw_b.get('he_form', '')
                if len(examples) < 30:
                    examples.append(
                        f'  {ch}:{vs} "{he_a}" gr="{gr_a}" -> "" | "{he_b}" gr="" -> "{gr_a}"')

                if not dry_run:
                    hw_b['gr_word'] = gr_a
                    hw_b['gr_source'] = hw_a.get('gr_source', 'catss:par')
                    hw_a['gr_word'] = ''
                    hw_a['gr_source'] = 'catss:crossed_fix'

                    # Also fix pair-level gr_unicode
                    if pi_a != pi_b:
                        # Move Greek from pair_a to pair_b
                        p_a_gr = (p_a.get('gr_unicode') or '').strip()
                        p_b_gr = (p_b.get('gr_unicode') or '').strip()

                        # Remove the divine Greek from pair_a's gr_unicode
                        remaining_a = []
                        moved_words = gr_a.split()
                        p_a_words = p_a_gr.split() if p_a_gr else []
                        for w in p_a_words:
                            if w in moved_words:
                                moved_words.remove(w)
                            else:
                                remaining_a.append(w)
                        p_a['gr_unicode'] = ' '.join(remaining_a)

                        # Add to pair_b's gr_unicode
                        if p_b_gr and p_b_gr != '----':
                            p_b['gr_unicode'] = gr_a + ' ' + p_b_gr
                        else:
                            p_b['gr_unicode'] = gr_a

    return stats, examples


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('book')
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    cfg = resolve(args.book)
    data = json.loads(cfg.final_json_path.read_text(encoding='utf-8'))

    dry_run = not args.apply
    stats, examples = fix_crossed(data, dry_run)

    mode = 'DRY-RUN' if dry_run else 'APPLY'
    print(f'{args.book}: {mode}')
    for k, v in sorted(stats.items()):
        print(f'  {k:20s} {v:>6d}')

    if examples:
        print(f'\nCrossed alignments found:')
        for ex in examples:
            print(ex)

    if not dry_run and stats['fixed'] > 0:
        cfg.final_json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'\nGuardado: {cfg.final_json_path.name}')


if __name__ == '__main__':
    main()
