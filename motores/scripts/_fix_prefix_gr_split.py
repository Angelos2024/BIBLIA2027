"""
_fix_prefix_gr_split.py - Split Greek from gr_word into prefix_gr arrays.

Problem: hw entries have prefix_morphs (CONJ, PREP, ART) but their Greek
counterparts are packed into gr_word with the stem.
E.g. prefix_morphs=["CONJ"], gr_word="εἶπεν δὲ"
  → prefix_gr should get ["δὲ"], gr_word should become "εἶπεν"

Also handles:
- Postpositive conjunctions (δέ, γάρ, etc.) at non-first positions
- Elided prepositions (ἀπ', μετ', κατ', ἀντ', ὑπ', ἐπ', παρ', ἐφ')
- Multiple prefixes (CONJ+PREP, CONJ+ART, etc.)
- Phantom empty pairs cleanup

Usage:
    python _fix_prefix_gr_split.py genesis
    python _fix_prefix_gr_split.py genesis --apply
"""
import json, sys, pathlib, unicodedata
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from book_config import resolve
sys.stdout.reconfigure(encoding='utf-8')


def nfc(s):
    return unicodedata.normalize('NFC', s.strip())


def norm(w):
    """Normalize Greek word for comparison: NFC, lowercase, strip diacritics."""
    s = unicodedata.normalize('NFD', nfc(w).lower())
    return ''.join(c for c in s if unicodedata.category(c) != 'Mn')


GR_CONJ_FIRST = {
    'και', 'αλλα', 'η', 'ουδε', 'ουτε', 'μηδε', 'μητε', 'ειτε',
    'οτι', 'ινα', 'ωστε', 'επει', 'επειδη', 'διοτι',
}
GR_POSTPOSITIVE = {
    'δε', 'γαρ', 'ουν', 'τε', 'μεν', 'αρα', 'δη',
}
GR_CONJ_ALL = GR_CONJ_FIRST | GR_POSTPOSITIVE

GR_PREP_NORM = {
    'εν', 'εις', 'εκ', 'εξ', 'απο', 'απ', 'αφ',
    'προς', 'επι', 'επ', 'εφ',
    'υπερ', 'υπο', 'υπ',
    'παρα', 'παρ',
    'περι', 'μετα', 'μετ',
    'κατα', 'κατ', 'καθ',
    'δια', 'δι',
    'προ', 'συν',
    'αντι', 'αντ',
    'ανα', 'ως', 'εως', 'αχρι', 'μεχρι',
}

GR_ART_NORM = {
    'ο', 'η', 'το', 'του', 'της', 'τω', 'τη',
    'τον', 'την', 'οι', 'αι', 'τα', 'των',
    'τοις', 'ταις', 'τους', 'τας',
}


def match_conj(gr_words, used):
    """Find a conjunction in gr_words. Check position 0 first, then postpositive."""
    for gi, gw in enumerate(gr_words):
        if gi in used:
            continue
        n = norm(gw.rstrip("'"))
        if n in GR_CONJ_FIRST:
            return gi, gw
    for gi, gw in enumerate(gr_words):
        if gi == 0 or gi in used:
            continue
        n = norm(gw.rstrip("'"))
        if n in GR_POSTPOSITIVE:
            return gi, gw
    return None, None


def match_prep(gr_words, used):
    """Find a preposition in gr_words (prefer first unused)."""
    for gi, gw in enumerate(gr_words):
        if gi in used:
            continue
        n = norm(gw.rstrip("'"))
        if n in GR_PREP_NORM:
            return gi, gw
    return None, None


def match_art(gr_words, used):
    """Find an article in gr_words (prefer first unused)."""
    for gi, gw in enumerate(gr_words):
        if gi in used:
            continue
        n = norm(gw.rstrip("'"))
        if n in GR_ART_NORM:
            return gi, gw
    return None, None


MATCHERS = {
    'CONJ': match_conj,
    'PREP': match_prep,
    'ART':  match_art,
    'PART': match_art,
}


def _morph_matcher(morph):
    """Get matcher from morph tag, handling compound tags like PREP.ART."""
    m = MATCHERS.get(morph)
    if m:
        return m
    for part in morph.split('.'):
        m = MATCHERS.get(part)
        if m:
            return m
    return None

# Hebrew prefix base consonants that imply a specific Greek category,
# regardless of what morph tag they carry (handles tagging errors).
# We strip niqqud to match any vowel pattern.
_HE_CONSONANT_TO_MATCHER = {
    '\u05D5': match_conj,  # ו (vav)
    '\u05D1': match_prep,  # ב (bet)
    '\u05DC': match_prep,  # ל (lamed)
    '\u05DE': match_prep,  # מ (mem)
    '\u05DB': match_prep,  # כ (kaf)
    '\u05D4': match_art,   # ה (he) — article
}


def _form_matcher(form):
    """Get matcher by Hebrew prefix form (strip niqqud, match base consonant)."""
    if not form:
        return None
    base = form[0]
    return _HE_CONSONANT_TO_MATCHER.get(base)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('book', nargs='?', default='genesis')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--verbose', '-v', action='store_true')
    args = parser.parse_args()

    dry_run = not args.apply
    cfg = resolve(args.book)
    data = json.loads(cfg.final_json_path.read_text(encoding='utf-8'))

    print(f"Fix prefix Greek split: {cfg.label} ({'DRY-RUN' if dry_run else 'APPLY'})")
    print("=" * 60)

    stats = Counter()

    for v in data['verses']:
        ch = v.get('chapter', 0)
        vs = v.get('verse', 0)

        for p in v.get('pairs', []):
            for hw in p.get('he_words', []):
                pm = hw.get('prefix_morphs') or []
                if not pm:
                    continue

                gr = (hw.get('gr_word') or '').strip()
                if not gr or gr == '----':
                    continue

                gr_words = gr.split()
                if len(gr_words) < 2:
                    continue

                pgr = hw.get('prefix_gr') or []
                while len(pgr) < len(pm):
                    pgr.append('')

                pf = hw.get('prefix_forms') or []

                any_needs_split = False
                for i, m in enumerate(pm):
                    has_matcher = _morph_matcher(m) is not None
                    if not has_matcher and i < len(pf):
                        has_matcher = _form_matcher(pf[i]) is not None
                    if has_matcher and not (pgr[i] or '').strip():
                        any_needs_split = True
                        break

                if not any_needs_split:
                    continue

                used = set()
                assignments = {}

                for i, m in enumerate(pm):
                    if (pgr[i] or '').strip():
                        continue
                    matcher = _morph_matcher(m)
                    if not matcher and i < len(pf):
                        matcher = _form_matcher(pf[i])
                    if not matcher:
                        continue
                    gi, gw = matcher(gr_words, used)
                    if gi is not None:
                        assignments[i] = (gi, gw)
                        used.add(gi)

                if not assignments:
                    continue

                remaining = [gw for gi, gw in enumerate(gr_words) if gi not in used]
                new_gr = ' '.join(remaining)

                if args.verbose and len(assignments) > 0:
                    print(f"  {ch}:{vs} he={hw.get('he_form','')} "
                          f"morphs={pm} gr={gr} → ", end='')
                    for i, (gi, gw) in sorted(assignments.items()):
                        print(f"pfx[{i}]={gw} ", end='')
                    print(f"stem={new_gr}")

                stats['hw_split'] += 1
                stats['prefix_assigned'] += len(assignments)

                for i, (gi, gw) in assignments.items():
                    morph = pm[i]
                    if _morph_matcher(morph):
                        base = morph.split('.')[0] if '.' in morph else morph
                        if base == 'CONJ' and norm(gw.rstrip("'")) in GR_POSTPOSITIVE:
                            stats['postpositive'] += 1
                        else:
                            stats[f'{base.lower()}_matched'] += 1
                    else:
                        stats['form_heuristic'] += 1

                if not dry_run:
                    for i, (gi, gw) in assignments.items():
                        pgr[i] = gw
                    hw['prefix_gr'] = pgr
                    hw['gr_word'] = new_gr

    print("\nPrefix split stats:")
    for k, cnt in sorted(stats.items()):
        print(f"  {k:25s} {cnt:>6d}")

    # ── Phantom pair cleanup ───────────────────────────────────────────
    print("\nPhantom pair cleanup:")
    phantom = 0
    for v in data['verses']:
        orig = v.get('pairs', [])
        new = []
        for p in orig:
            # NEVER remove gk_add pairs (LXX additions). Their Greek may live
            # only at pair.gr_unicode level, not on hw.gr_word.
            if p.get('kind') == 'gk_add':
                new.append(p)
                continue

            hws = p.get('he_words', [])
            he = (p.get('he', '') or '').strip()

            all_empty = True
            for hw in hws:
                raw = (hw.get('raw') or '').strip()
                he_f = (hw.get('he_form') or hw.get('full_unicode') or '').strip()
                gr = (hw.get('gr_word') or '').strip()
                es = (hw.get('es') or '').strip()
                if raw and raw not in ('', 'GKADD', '--', '----'):
                    all_empty = False
                    break
                if he_f or (gr and gr != '----') or es:
                    all_empty = False
                    break

            if not hws or (all_empty and not he):
                phantom += 1
                if not dry_run:
                    continue
            new.append(p)

        if not dry_run and len(new) < len(orig):
            v['pairs'] = new

    print(f"  phantom pairs removed: {phantom}")

    # ── Summary ────────────────────────────────────────────────────────
    if not dry_run:
        cfg.final_json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"\nGuardado: {cfg.final_json_path}")


if __name__ == '__main__':
    main()
