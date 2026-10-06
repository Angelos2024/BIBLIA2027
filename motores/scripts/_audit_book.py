"""Full audit of a processed book's _final.json."""
import sys, json, argparse
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
from book_config import resolve


def audit(cfg):
    data = json.loads(cfg.final_json_path.read_text(encoding='utf-8'))

    total_hw = 0
    he_filled = 0
    morph_filled = 0
    morph_dotted = 0
    gr_filled = 0
    gr_omit = 0
    es_filled = 0
    pairs_with_gr = 0
    pairs_total = 0
    phantom_prefix = 0
    diaeresis = 0
    dots = 0
    dashes = 0
    empty_quotes = 0
    braces = 0
    all_omit_verses = []

    for v in data['verses']:
        ch, vs = v.get('chapter', 0), v.get('verse', 0)
        pairs_total_v = 0
        gr_v = 0

        for p in v.get('pairs', []):
            pairs_total += 1
            pairs_total_v += 1
            gu = (p.get('gr_unicode') or '').strip()
            if gu:
                pairs_with_gr += 1
                gr_v += 1
            if '\u0308' in gu: diaeresis += 1
            if '...' in gu: dots += 1
            if '--' in gu and gu != '----': dashes += 1
            if "''" in gu: empty_quotes += 1
            if '{' in gu or '}' in gu: braces += 1

            for hw in p.get('he_words', []):
                raw = (hw.get('raw') or '').strip()
                if not raw or raw in ('GKADD',) or raw.startswith(('=', '{', '<', '*', '.')):
                    continue
                total_hw += 1

                hf = (hw.get('he_form') or '').strip()
                if hf: he_filled += 1

                hm = (hw.get('he_morph') or '').strip()
                if hm: morph_filled += 1
                if hm and '.' in hm: morph_dotted += 1

                gw = (hw.get('gr_word') or '').strip()
                if gw and gw != '----':
                    gr_filled += 1
                elif gw == '----':
                    gr_omit += 1
                if '\u0308' in gw: diaeresis += 1
                if '...' in gw: dots += 1
                if '--' in gw and gw != '----': dashes += 1
                if "''" in gw: empty_quotes += 1

                es = (hw.get('es') or '').strip()
                if es: es_filled += 1

                pf = hw.get('prefix_forms') or []
                for pfi in pf:
                    if not (pfi or '').strip():
                        phantom_prefix += 1

        if pairs_total_v > 0 and gr_v == 0:
            all_omit_verses.append(f'{ch}:{vs}')

    pct = lambda a, b: f'{a/b*100:.1f}%' if b else '0%'

    print(f'=== {cfg.label} — Auditoría completa ===')
    print(f'  Versículos:      {len(data["verses"])}')
    print(f'  Pares totales:   {pairs_total}')
    print(f'  Tokens hebreos:  {total_hw}')
    print()
    print(f'  Hebreo (he_form):   {he_filled}/{total_hw} ({pct(he_filled, total_hw)})')
    print(f'  Morfología:         {morph_filled}/{total_hw} ({pct(morph_filled, total_hw)})')
    if morph_filled:
        print(f'  Morph dotted:       {morph_dotted}/{morph_filled} ({pct(morph_dotted, morph_filled)})')
    print(f'  Griego (gr_word):   {gr_filled}/{total_hw} ({pct(gr_filled, total_hw)})')
    print(f'  Griego omisiones:   {gr_omit}')
    print(f'  Español (es):       {es_filled}/{total_hw} ({pct(es_filled, total_hw)})')
    print()
    print(f'  gr_unicode pares:   {pairs_with_gr}/{pairs_total}')
    print(f'  Phantom prefixes:   {phantom_prefix}')
    print()
    print(f'  Artefactos griegos restantes:')
    print(f'    Diéresis (U+0308): {diaeresis}')
    print(f'    Puntos (...):      {dots}')
    print(f'    Guiones (--/---):  {dashes}')
    print(f'    Comillas vac (\'\'):  {empty_quotes}')
    print(f'    Llaves ({{}}):      {braces}')
    print()
    if all_omit_verses:
        print(f'  Versos sin griego:  {len(all_omit_verses)}')
        if len(all_omit_verses) <= 10:
            print(f'    {all_omit_verses}')
        else:
            print(f'    {all_omit_verses[:10]} ... +{len(all_omit_verses)-10} más')
    else:
        print(f'  Versos sin griego:  0')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('book')
    args = ap.parse_args()
    cfg = resolve(args.book)
    audit(cfg)


if __name__ == '__main__':
    main()
