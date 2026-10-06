"""Fix pair-level Greek overlap: when token[0].gr_word contains text
already assigned to later tokens (via their prefix_gr + gr_word), strip
the overlapping tail from token[0].gr_word.

Usage:
    python _fix_gr_pair_dup.py <slug> --apply
"""
import json, sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

DATA = Path(r'C:\Users\pik_y\Documents\TRADUCCION\data')

APPLY = '--apply' in sys.argv
SLUG = None
for a in sys.argv[1:]:
    if a != '--apply':
        SLUG = a
        break

if not SLUG:
    print('Uso: python _fix_gr_pair_dup.py <slug> [--apply]')
    sys.exit(1)

BOOKS = [SLUG]


def rebuild_gr_unicode(pair):
    parts = []
    for hw in pair.get('he_words', []):
        pfx_list = hw.get('prefix_gr', [])
        if isinstance(pfx_list, list):
            for pg in pfx_list:
                if pg and str(pg).strip() and str(pg).strip() != '---':
                    parts.append(str(pg).strip())
        gr = (hw.get('gr_word') or '').strip()
        if gr and gr != '----':
            parts.append(gr)
        prs = hw.get('prs_suffix', {})
        if isinstance(prs, dict):
            prs_gr = (prs.get('gr_word') or '').strip()
            if prs_gr and prs_gr != '----':
                parts.append(prs_gr)
    return ' '.join(parts) if parts else ''


grand_total = 0

for book in BOOKS:
    fp = DATA / f'{book}_final.json'
    if not fp.exists():
        print(f'  {book}: NOT FOUND')
        continue
    data = json.loads(fp.read_text(encoding='utf-8'))
    fixed = 0

    for v in data['verses']:
        for p in v.get('pairs', []):
            hws = p.get('he_words', [])
            if len(hws) < 2:
                continue

            first_gr = (hws[0].get('gr_word') or '').strip()
            if not first_gr or first_gr == '----':
                continue

            # Collect Greek from later tokens (split into individual words)
            later_words = []
            for hw in hws[1:]:
                pfx = hw.get('prefix_gr', [])
                if isinstance(pfx, list):
                    for pg in pfx:
                        s = str(pg).strip()
                        if s and s != '---':
                            for w in s.split():
                                later_words.append(w)
                gw = (hw.get('gr_word') or '').strip()
                if gw and gw != '----':
                    for w in gw.split():
                        later_words.append(w)
                prs = hw.get('prs_suffix', {})
                if isinstance(prs, dict):
                    prs_gr = (prs.get('gr_word') or '').strip()
                    if prs_gr and prs_gr != '----':
                        for w in prs_gr.split():
                            later_words.append(w)

            if not later_words:
                continue

            first_tokens = first_gr.split()
            later_lower = [w.lower() for w in later_words]

            # Find overlap: tail of first_tokens matches beginning of later_parts
            best_cut = -1
            for cut in range(0, len(first_tokens)):
                tail = [t.lower() for t in first_tokens[cut:]]
                if tail == later_lower[:len(tail)]:
                    best_cut = cut
                    break

            if best_cut >= 0:
                remaining = first_tokens[:best_cut]
                new_gr = ' '.join(remaining) if remaining else '----'
                if APPLY:
                    hws[0]['gr_word'] = new_gr
                fixed += 1

            # Rebuild gr_unicode
            if APPLY:
                p['gr_unicode'] = rebuild_gr_unicode(p)

    grand_total += fixed
    print(f'{book}: {fixed} pair overlaps corregidos')
    if APPLY:
        fp.write_text(json.dumps(data, ensure_ascii=False, indent=None), encoding='utf-8')
        print(f'  Guardado: {fp}')

print(f'\n=== TOTAL: {grand_total} {"(APLICADAS)" if APPLY else "(DRY-RUN)"} ===')
