"""Reubica griego de raíz atrapado en prefix_gr (COMB_BAD).

Un slot de prefix_gr solo debe llevar clases de prefijo (CONJ/PREP/ART/PRT...).
Cuando prefix_gr[i] contiene una palabra de contenido (SUBS/VERBO/ADJ/ADV/NUM/PRON)
significa que la raíz griega se cayó al prefijo. Se corrige:

  - si gr_word (raíz) está vacío/----  -> mover ese griego a gr_word y limpiar el slot.
  - si gr_word es un griego de prefijo (καὶ/δὲ/artículo/preposición) -> intercambiar:
        gr_word va al slot de prefijo (con su morph correcta) y la palabra de
        contenido pasa a ser la raíz.
  - en cualquier otro caso (gr_word ya ocupado por contenido) -> no tocar (conservador).

Uso: python _fix_stem_in_prefix.py <slug> [--apply]
"""
import json, sys, re
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
from book_config import resolve

APPLY = '--apply' in sys.argv
SLUG = next((a for a in sys.argv[1:] if a != '--apply'), None)
GREEK = re.compile(r'[\u0370-\u03FF\u1F00-\u1FFF]')
PREFIX_OK = ('CONJ', 'PREP', 'ART', 'PRT', 'INTR', 'ADV',
             'INTERR', 'INTERROG', 'NEG', 'PART', 'REL')

ARTICLES = {'ὁ','ἡ','τὸ','τό','οἱ','αἱ','τὰ','τά','τοῦ','τῆς','τῶν','τὸν','τόν',
            'τὴν','τήν','τοὺς','τούς','τὰς','τάς','τῷ','τῇ','τοῖς','ταῖς','τοὺ'}
CONJS = {'καὶ','καί','δὲ','δέ','τε','ἢ','ἤ','ἀλλὰ','ἀλλά','γὰρ','γάρ','οὖν'}
PREPS = {'ἐν','εἰς','ἐκ','ἐξ','ἀπὸ','ἀπό','πρὸς','πρός','διὰ','διά','κατὰ','κατά',
         'μετὰ','μετά','ἐπὶ','ἐπί','παρὰ','παρά','περὶ','περί','ὑπὸ','ὑπό','σὺν',
         'σύν','ὑπὲρ','ὑπέρ','ἀντὶ','ἀντί','πρὸ','πρό','καθὼς','καθώς','ἕως'}


def prefix_class(word):
    w = (word or '').strip()
    if w in CONJS:
        return 'CONJ'
    if w in ARTICLES:
        return 'ART'
    if w in PREPS:
        return 'PREP'
    return None


def main():
    cfg = resolve(SLUG)
    d = json.loads(cfg.final_json_path.read_text(encoding='utf-8'))
    moved = 0
    swapped = 0
    for v in d['verses']:
        for p in v.get('pairs', []):
            if p.get('kind') == 'gk_add':
                continue
            for hw in p.get('he_words', []):
                pgr = hw.get('prefix_gr') or []
                pm = hw.get('prefix_morphs') or []
                if not pgr:
                    continue
                for i, g in enumerate(pgr):
                    g = (g or '').strip()
                    if not g or not GREEK.search(g):
                        continue
                    morph = (pm[i] if i < len(pm) else '') or ''
                    base = morph.split('.')[0]
                    if not base or base in PREFIX_OK:
                        continue
                    # prefix slot tiene palabra de contenido -> raíz evaporada
                    stem = (hw.get('gr_word') or '').strip()
                    if stem in ('', '----'):
                        if APPLY:
                            hw['gr_word'] = g
                            pgr[i] = ''
                            if i < len(pm):
                                pm[i] = ''
                        moved += 1
                    else:
                        pc = prefix_class(stem)
                        if pc:
                            # intercambio: el prefijo real (stem) sube al slot, contenido baja a raíz
                            if APPLY:
                                pgr[i] = stem
                                if i < len(pm):
                                    pm[i] = pc
                                hw['gr_word'] = g
                            swapped += 1
                        # si stem es contenido real, no tocar
    print(f'{cfg.label}: {moved} raíz movida desde prefijo, {swapped} intercambios prefijo<->raíz '
          + ('(APLICADO)' if APPLY else '(DRY)'))
    if APPLY and (moved or swapped):
        cfg.final_json_path.write_text(json.dumps(d, ensure_ascii=False, indent=None), encoding='utf-8')


if __name__ == '__main__':
    main()
