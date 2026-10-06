"""convert_morph_to_dotted.py
Convert Macula compact morph codes to dotted descriptive format
matching the style used in Genesis chapters 1-15.

Affects: he_morph, prefix_morphs, prs_suffix.he_morph
Only converts Macula compact codes; already-dotted values are kept as-is.

Usage:
    python convert_morph_to_dotted.py --book levitico              # dry-run
    python convert_morph_to_dotted.py --book levitico --apply      # apply
    python convert_morph_to_dotted.py --book genesis --chapter 16  # single chapter
    python convert_morph_to_dotted.py --book genesis -v            # verbose
"""
import json, sys, argparse
sys.stdout.reconfigure(encoding='utf-8')

from book_config import resolve
from gen_chapter_scope import is_rules_target

# ─── Mapping tables ───────────────────────────────────────────────────────────

VERB_STEM = {
    'q': 'QAL', 'N': 'NIF', 'p': 'PIEL', 'P': 'PUAL',
    'h': 'HIF', 'H': 'HOF', 't': 'HIT',
    'f': 'PILPEL', 'l': 'POLEL', 'k': 'PULAL',
    'm': 'POLAL', 'v': 'HITPOL', 'Q': 'QAL.PAS',
    'r': 'HISHTAPHEL',
}

VERB_TENSE = {
    'p': 'PERF', 'i': 'IMPF', 'w': 'WAYYIQT', 'j': 'JUSS',
    'v': 'IMPV', 'c': 'INFC', 'a': 'INFA', 'h': 'COHORT',
    'q': 'PERF.CONS',
}

GENDER = {'m': 'M', 'f': 'F', 'c': 'COMMON', 'b': 'BOTH'}
NUMBER = {'s': 'SG', 'p': 'PL', 'd': 'DU'}
STATE  = {'a': 'A', 'c': 'C'}

SIMPLE_CODES = {
    'C': 'CONJ', 'R': 'PREP', 'D': 'ADV',
    'Rd': 'PREP.ART',
    'Td': 'ART', 'To': 'PART.OBJ.DIR', 'Tn': 'NEG',
    'Tr': 'REL', 'Te': 'PART.EXH', 'Tm': 'DEM',
    'Ta': 'PART.ACUS', 'Ti': 'INTERR', 'Tj': 'INTJ',
    'Np': 'NPROP',
    'Sd': 'SUF.DIR', 'Sh': 'SUF.PARAG.H', 'Sn': 'SUF.PARAG.N',
}

ALREADY_DOTTED = frozenset({
    'CONJ', 'PREP', 'ART', 'NEG', 'ADV', 'NPROP', 'DEM', 'REL',
    'INTERR', 'INTJ',
})


def _gender(c):
    return GENDER.get(c, c.upper())

def _number(c):
    return NUMBER.get(c, c.upper())

def _state(c):
    return STATE.get(c, c.upper())


def macula_to_dotted(code):
    """Convert a single Macula compact code to dotted descriptive format."""
    if not code or '.' in code:
        return code

    if code in ALREADY_DOTTED:
        return code

    if code in SIMPLE_CODES:
        return SIMPLE_CODES[code]

    first = code[0]

    # ── Verbs: V + stem + tense/ptcp + ... ────────────────────────────
    if first == 'V' and len(code) >= 2:
        stem_c = code[1]
        stem = VERB_STEM.get(stem_c, stem_c.upper())

        if len(code) == 2:
            return f'VERBO.{stem}'

        form_c = code[2]

        # Participles: V + stem + r(active)/s(passive) + gender + number + state
        if form_c in ('r', 's'):
            ptcp = 'PTCP' if form_c == 'r' else 'PTCP.PAS'
            parts = ['VERBO', stem, ptcp]
            if len(code) > 3:
                parts.append(_gender(code[3]))
            if len(code) > 4:
                parts.append(_number(code[4]))
            if len(code) > 5:
                parts.append(_state(code[5]))
            return '.'.join(parts)

        # Finite verbs: V + stem + tense + person + gender + number
        tense = VERB_TENSE.get(form_c, form_c.upper())
        parts = ['VERBO', stem, tense]
        if len(code) > 3:
            parts.append(f'P{code[3]}')
        if len(code) > 4:
            parts.append(_gender(code[4]))
        if len(code) > 5:
            parts.append(_number(code[5]))
        return '.'.join(parts)

    # ── Nouns: N + subtype + gender + number + state ──────────────────
    if first == 'N' and len(code) >= 2:
        sub = code[1]
        if sub == 'p':
            return 'NPROP'
        prefix = 'GENT' if sub == 'g' else 'SUBS'
        parts = [prefix]
        if len(code) > 2:
            parts.append(_gender(code[2]))
        if len(code) > 3:
            parts.append(_number(code[3]))
        if len(code) > 4:
            parts.append(_state(code[4]))
        return '.'.join(parts)

    # ── Adjectives/Numerals: A + type + gender + number + state ───────
    if first == 'A' and len(code) >= 2:
        sub = code[1]
        if sub == 'c':
            prefix = 'NUM.CARD'
        elif sub == 'o':
            prefix = 'NUM.ORD'
        else:
            prefix = 'ADJ'
        parts = [prefix]
        if len(code) > 2:
            parts.append(_gender(code[2]))
        if len(code) > 3:
            parts.append(_number(code[3]))
        if len(code) > 4:
            parts.append(_state(code[4]))
        return '.'.join(parts)

    # ── Pronouns: P + type + person + gender + number ─────────────────
    if first == 'P' and len(code) >= 2:
        sub = code[1]
        type_map = {'p': 'PRON.PERS', 'd': 'PRON.DEM', 'i': 'PRON.INTERR', 'r': 'PRON.REL'}
        prefix = type_map.get(sub, 'PRON')

        if sub == 'd':
            parts = [prefix]
            if len(code) > 3:
                parts.append(_gender(code[3]))
            if len(code) > 4:
                parts.append(_number(code[4]))
            return '.'.join(parts)

        parts = [prefix]
        if len(code) > 2:
            parts.append(f'P{code[2]}')
        if len(code) > 3:
            parts.append(_gender(code[3]))
        if len(code) > 4:
            parts.append(_number(code[4]))
        return '.'.join(parts)

    # ── Suffixes: S + p + person + gender + number ────────────────────
    if first == 'S' and len(code) >= 2:
        sub = code[1]
        if sub == 'p':
            parts = ['PRS']
            if len(code) > 2:
                parts.append(f'P{code[2]}')
            if len(code) > 3:
                parts.append(_gender(code[3]))
            if len(code) > 4:
                parts.append(_number(code[4]))
            return '.'.join(parts)
        return SIMPLE_CODES.get(code, code)

    # ── Particles T + subtype (not in simple map) ────────────────────
    if first == 'T':
        return SIMPLE_CODES.get(code, code)

    return code


# ─── Process data ─────────────────────────────────────────────────────────────
def process_data(data, args):
    stats = {'he_morph': 0, 'prefix_morphs': 0, 'prs_morph': 0, 'detail': []}

    for v in data['verses']:
        ch = v.get('chapter', 0)
        vs = v.get('verse', 0)
        ref = f"{ch}:{vs}"

        if args.chapter and ch != args.chapter:
            continue
        if args.book == 'genesis' and not args.chapter and not args.force and not is_rules_target(ch):
            continue

        for p in v.get('pairs', []):
            for hw in p.get('he_words', []):
                raw = (hw.get('raw') or '').strip()

                # ── he_morph ──
                old = (hw.get('he_morph') or '').strip()
                if old:
                    new = macula_to_dotted(old)
                    if new != old:
                        hw['he_morph'] = new
                        stats['he_morph'] += 1
                        stats['detail'].append(
                            f"  {ref} raw={raw} he_morph: [{old}]→[{new}]")

                # ── prefix_morphs ──
                pm = hw.get('prefix_morphs') or []
                for i, slot in enumerate(pm):
                    old_pm = (slot or '').strip()
                    if old_pm:
                        new_pm = macula_to_dotted(old_pm)
                        if new_pm != old_pm:
                            pm[i] = new_pm
                            stats['prefix_morphs'] += 1
                            stats['detail'].append(
                                f"  {ref} raw={raw} pm[{i}]: [{old_pm}]→[{new_pm}]")
                if pm:
                    hw['prefix_morphs'] = pm

                # ── prs_suffix.he_morph ──
                prs = hw.get('prs_suffix')
                if prs and isinstance(prs, dict):
                    old_sm = (prs.get('he_morph') or '').strip()
                    if old_sm:
                        new_sm = macula_to_dotted(old_sm)
                        if new_sm != old_sm:
                            prs['he_morph'] = new_sm
                            stats['prs_morph'] += 1
                            stats['detail'].append(
                                f"  {ref} raw={raw} prs_morph: [{old_sm}]→[{new_sm}]")

    return stats


def main():
    ap = argparse.ArgumentParser(description='Convert Macula morph codes to dotted format')
    ap.add_argument('--book', default='genesis', help='slug del libro')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--chapter', type=int, default=0)
    ap.add_argument('--force', action='store_true', help='Bypass Genesis ch 1-15 protection')
    ap.add_argument('-v', '--verbose', action='store_true')
    args = ap.parse_args()

    cfg = resolve(args.book)
    data = json.loads(cfg.final_json_path.read_text(encoding='utf-8'))
    stats = process_data(data, args)

    total = stats['he_morph'] + stats['prefix_morphs'] + stats['prs_morph']
    mode = 'APLICANDO' if args.apply else 'DRY RUN'

    print(f'{"=" * 60}')
    print(f'  {mode} — {cfg.label} — Conversion a formato dotted')
    print(f'{"=" * 60}')
    print(f'  he_morph:           {stats["he_morph"]}')
    print(f'  prefix_morphs:      {stats["prefix_morphs"]}')
    print(f'  prs_suffix.he_morph:{stats["prs_morph"]}')
    print(f'  TOTAL cambios:      {total}')

    nd = len(stats['detail'])
    if args.verbose or nd <= 200:
        for d in stats['detail']:
            print(d)
    else:
        print(f'\n  (mostrando 80 de {nd}; usa -v para ver todos)')
        for d in stats['detail'][:80]:
            print(d)
        if nd > 80:
            print(f'  ... y {nd - 80} mas')

    if args.apply and total > 0:
        cfg.final_json_path.write_text(
            json.dumps(data, ensure_ascii=False, separators=(',', ':')),
            encoding='utf-8')
        print(f'\n  Guardado: {cfg.final_json_path}')
    elif not args.apply:
        print(f'\n  (uso: python convert_morph_to_dotted.py --book {cfg.slug} --apply)')


if __name__ == '__main__':
    main()
