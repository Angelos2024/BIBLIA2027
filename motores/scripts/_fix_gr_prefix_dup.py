"""Strip duplicated Greek prefix from gr_word.

When prefix_gr=['καὶ'] and gr_word='καὶ βενιαμιν', the gr_word should
become just 'βενιαμιν' because the prefix Greek is already stored in
prefix_gr and displayed separately.

Usage:
    python _fix_gr_prefix_dup.py <slug> --apply
"""
import json, sys, re
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
    print('Uso: python _fix_gr_prefix_dup.py <slug> [--apply]')
    sys.exit(1)

BOOKS = [SLUG]

def to_str(val):
    if isinstance(val, list):
        return ' '.join(str(v) for v in val).strip()
    return (val or '').strip()

def norm(s):
    return re.sub(r'\s+', ' ', s.strip().lower())

def strip_prefix_from_gr(prefix_gr_list, gr_word_str):
    """Remove prefix Greek tokens from gr_word if duplicated.

    Handles both simple (prefix_gr=['καὶ'], gr_word='καὶ βενιαμιν')
    and multi-prefix (prefix_gr=['δὲ','ἡ'], gr_word='ἡ δὲ γῆ') cases.
    Tokenizes gr_word and removes leading tokens that match any prefix_gr element.
    """
    pfx_items = [str(v).strip().lower() for v in prefix_gr_list if str(v).strip()]
    gr = gr_word_str.strip()
    if not pfx_items or not gr:
        return gr_word_str

    gr_tokens = gr.split()
    gr_tokens_lower = [t.lower() for t in gr_tokens]

    remaining_pfx = list(pfx_items)
    tokens_to_remove = set()

    # Greedily match prefix elements against leading gr_word tokens
    for i, tok_lower in enumerate(gr_tokens_lower):
        if not remaining_pfx:
            break
        if tok_lower in remaining_pfx:
            remaining_pfx.remove(tok_lower)
            tokens_to_remove.add(i)
        else:
            break

    if not tokens_to_remove:
        return gr_word_str

    result_tokens = [t for i, t in enumerate(gr_tokens) if i not in tokens_to_remove]
    # Si TODOS los tokens del stem coincidían con el prefijo, la raíz no tiene
    # griego propio: se limpia (el prefijo ya contiene esa palabra). Antes esto
    # devolvía el original y dejaba duplicados tipo "καὶ καὶ" / "ὑποκάτω ὑποκάτω".
    return ' '.join(result_tokens)


def rebuild_gr_unicode(pair):
    """Rebuild pair.gr_unicode from he_words prefix_gr + gr_word."""
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
        # Also check prs_suffix gr_word
        prs = hw.get('prs_suffix', {})
        if isinstance(prs, dict):
            prs_gr = (prs.get('gr_word') or '').strip()
            if prs_gr and prs_gr != '----':
                parts.append(prs_gr)
    return ' '.join(parts) if parts else ''


grand_total = 0
gr_unicode_rebuilt = 0

for book in BOOKS:
    fp = DATA / f'{book}_final.json'
    if not fp.exists():
        print(f'  {book}: NOT FOUND')
        continue
    data = json.loads(fp.read_text(encoding='utf-8'))
    fixed = 0

    for v in data['verses']:
        for p in v.get('pairs', []):
            for hw in p.get('he_words', []):
                pfx_list = hw.get('prefix_gr', [])
                gr_word = hw.get('gr_word', '')
                if not isinstance(pfx_list, list) or not pfx_list or not gr_word:
                    continue
                new_gr = strip_prefix_from_gr(pfx_list, gr_word)
                if new_gr != gr_word:
                    if APPLY:
                        hw['gr_word'] = new_gr
                    fixed += 1

            # Rebuild gr_unicode for this pair
            if APPLY:
                new_uni = rebuild_gr_unicode(p)
                if new_uni:
                    p['gr_unicode'] = new_uni
                    gr_unicode_rebuilt += 1

    grand_total += fixed
    print(f'{book}: {fixed} gr_word corregidos')

    if APPLY:
        fp.write_text(json.dumps(data, ensure_ascii=False, indent=None), encoding='utf-8')
        print(f'  Guardado: {fp}')

print(f'\n=== TOTAL: {grand_total} correcciones {"(APLICADAS)" if APPLY else "(DRY-RUN)"} ===')
if APPLY:
    print(f'  gr_unicode reconstruidos: {gr_unicode_rebuilt} pares')
