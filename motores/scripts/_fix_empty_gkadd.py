"""_fix_empty_gkadd.py - Elimina pares gk_add fantasma (sin griego real).

Un par gk_add representa una ADICIÓN de la LXX: DEBE contener griego. Si tras el
relleno desde CATSS (_fill_gkadd_greek) su gr_unicode sigue sin ninguna letra
griega (solo '...', '---', '.', combining marks, vacío, etc.), es un artefacto del
aparato CATSS que en el visor aparece como "ADD –". Se elimina el par.

Si un pseudo-verso is_lxx_add queda sin pares tras la limpieza, se elimina el verso.

Uso:
    python _fix_empty_gkadd.py <slug> [--apply]
"""
import json, sys, re

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
from book_config import resolve

GREEK = re.compile(r'[\u0370-\u03FF\u1F00-\u1FFF]')


def fix_book(slug, apply):
    cfg = resolve(slug)
    d = json.loads(cfg.final_json_path.read_text(encoding='utf-8'))
    removed = 0
    verses_dropped = 0
    samples = []
    new_verses = []
    for v in d['verses']:
        pseudo = bool(v.get('is_lxx_add'))
        kept = []
        for p in v.get('pairs', []):
            if p.get('kind') == 'gk_add':
                uni = (p.get('gr_unicode') or '').strip()
                if not GREEK.search(uni):
                    removed += 1
                    if len(samples) < 12:
                        samples.append(f"  {v.get('chapter')}:{v.get('verse')} "
                                       f"{'[ADD+]' if pseudo else ''} uni={uni!r}")
                    continue
            kept.append(p)
        v['pairs'] = kept
        if pseudo and not kept:
            verses_dropped += 1
            continue
        new_verses.append(v)
    d['verses'] = new_verses

    print(f"{slug:<12} gk_add fantasma eliminados: {removed}   pseudo-versos vacíos: {verses_dropped}")
    for s in samples:
        print(s)
    if apply and (removed or verses_dropped):
        cfg.final_json_path.write_text(
            json.dumps(d, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"  -> guardado {cfg.final_json_path.name}")
    return removed


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    apply = '--apply' in sys.argv
    slug = args[0] if args else 'genesis'
    fix_book(slug, apply)
