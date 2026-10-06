"""Convert *_final.json → interlineal snapshot format for the viewer."""
import sys, json, argparse
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
from book_config import resolve

DEST_DIR = r'C:\Users\pik_y\Documents\GitHub\Local-consults\estudio\angelos\IdiomaORIGEN\interlineal'

SLUG_TO_NUM = {
    'genesis': 1, 'exodo': 2, 'levitico': 3, 'numeros': 4, 'deuteronomio': 5,
    'josue': 6, 'jueces': 7, 'rut': 8, '1_samuel': 9, '2_samuel': 10,
    '1_reyes': 11, '2_reyes': 12, '1_cronicas': 13, '2_cronicas': 14,
    'esdras': 15, 'nehemias': 16, 'ester': 17, 'job': 18, 'salmos': 19,
    'proverbios': 20, 'eclesiastes': 21, 'cantares': 22, 'isaias': 23,
    'jeremias': 24, 'lamentaciones': 25, 'ezequiel': 26, 'daniel': 27,
    'oseas': 28, 'joel': 29, 'amos': 30, 'abdias': 31, 'jonas': 32,
    'miqueas': 33, 'nahum': 34, 'habacuc': 35, 'sofonias': 36,
    'hageo': 37, 'zacarias': 38, 'malaquias': 39,
}

def convert(cfg):
    src = json.loads(cfg.final_json_path.read_text(encoding='utf-8'))
    chapters = {}
    verse_count = 0

    for v in src['verses']:
        ch = str(v['chapter'])
        vs = str(v['verse'])
        verse_count += 1
        if ch not in chapters:
            chapters[ch] = {}

        # ADD+ LXX pseudo-verse: store as separate key with _add suffix
        if v.get('is_lxx_add'):
            gr_words = [
                (p.get('gr_unicode') or '').strip()
                for p in v.get('pairs', [])
                if (p.get('gr_unicode') or '').strip()
            ]
            chapters[ch][vs + '_add'] = {
                'is_lxx_add': True,
                'lxx_add_label': v.get('lxx_add_label', f'{ch}:{vs} ADD+ LXX'),
                'gr_text': ' '.join(gr_words),
                'token_count': len(v.get('pairs', [])),
            }
            continue

        tokens = []
        raw_parts = []

        for pair in v.get('pairs', []):
            he_words = pair.get('he_words', [])
            kind = pair.get('kind', 'align')
            gr_unicode = (pair.get('gr_unicode') or '').strip()

            for hw in he_words:
                he_form = (hw.get('he_form') or '').strip()
                he_morph = (hw.get('he_morph') or '').strip()
                strongs = (hw.get('strongs') or '').strip()
                es = (hw.get('es') or '').strip()
                gr_word = (hw.get('gr_word') or '').strip()
                prefix_forms = hw.get('prefix_forms') or []
                prefix_morphs = hw.get('prefix_morphs') or []
                prefix_es = hw.get('prefix_es') or []
                prefix_gr = hw.get('prefix_gr') or []
                prs = hw.get('prs_suffix') or {}

                for i, pf in enumerate(prefix_forms):
                    pf_str = (pf or '').strip()
                    if not pf_str:
                        continue
                    tok = {'orig': pf_str}
                    if i < len(prefix_morphs) and prefix_morphs[i]:
                        tok['morphs'] = prefix_morphs[i]
                    if i < len(prefix_es) and prefix_es[i]:
                        tok['es'] = prefix_es[i]
                    else:
                        tok['notrans'] = 's/t'
                    if i < len(prefix_gr) and prefix_gr[i]:
                        tok['gr'] = prefix_gr[i]
                    tokens.append(tok)
                    raw_parts.append(pf_str)

                if he_form:
                    tok = {'orig': he_form}
                    if he_morph:
                        tok['morphs'] = he_morph
                    if strongs:
                        tok['strongs'] = strongs
                    if es:
                        tok['es'] = es
                    elif kind == 'gk_add':
                        tok['notrans'] = 's/t'
                    if gr_word and gr_word != '----':
                        tok['gr'] = gr_word
                    elif gr_word == '----':
                        tok['lxx_omit'] = True
                    tokens.append(tok)
                    raw_parts.append(he_form)

                if prs and prs.get('he_form'):
                    prs_form = prs['he_form'].strip()
                    tok = {'orig': prs_form}
                    if prs.get('he_morph'):
                        tok['morphs'] = prs['he_morph']
                    if prs.get('es'):
                        tok['es'] = prs['es']
                    if prs.get('gr_word') and prs['gr_word'] != '----':
                        tok['gr'] = prs['gr_word']
                    tokens.append(tok)
                    raw_parts.append(prs_form)

        for i, t in enumerate(tokens):
            t['num'] = str(i + 1)

        chapters[ch][vs] = {
            'raw': ' '.join(raw_parts),
            'tokens': tokens,
        }

    book_num = SLUG_TO_NUM.get(cfg.slug, 0)
    out = {
        'book_num': book_num,
        'book_name': cfg.label,
        'verses_count': verse_count,
        'chapters': chapters,
    }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('book')
    args = ap.parse_args()

    cfg = resolve(args.book)
    snap = convert(cfg)

    num = SLUG_TO_NUM.get(cfg.slug, 0)
    filename = f'{num:02d}_{cfg.label}.json'

    from pathlib import Path
    outpath = Path(DEST_DIR) / filename
    outpath.write_text(json.dumps(snap, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

    ch_count = len(snap['chapters'])
    v_count = snap['verses_count']
    sz = outpath.stat().st_size
    print(f'Created: {outpath.name}')
    print(f'  Chapters: {ch_count}')
    print(f'  Verses:   {v_count}')
    print(f'  Size:     {sz:,} bytes')

    v1 = snap['chapters']['1']['1']
    print(f'  {cfg.label} 1:1 tokens: {len(v1["tokens"])}')
    if v1['tokens']:
        t0 = v1['tokens'][0]
        print(f'  First token: orig={t0.get("orig")} morphs={t0.get("morphs")} es={t0.get("es","-")}')


if __name__ == '__main__':
    main()
