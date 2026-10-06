"""Limpia hebreo espurio latino (artefactos CATSS tipo ',,a') preservando griego.

Tokens donde he_form/full_unicode es solo caracteres latinos (no hebreo) y el
raw es un código CATSS (coma inicial u otro), se vacían en el lado hebreo para
no mostrar 'a' como si fuera hebreo. El griego (p.ej. ηλαμαῖοι) se conserva.

Uso: python _fix_latin_he.py <slug> [--apply]
"""
import json, sys, re
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
from book_config import resolve

APPLY = '--apply' in sys.argv
SLUG = next((a for a in sys.argv[1:] if a != '--apply'), None)
HEBREW = re.compile(r'[\u0590-\u05FF]')
LATIN = re.compile(r'[A-Za-z]')


def is_latin_junk(hw):
    hf = (hw.get('he_form') or '').strip()
    fu = (hw.get('full_unicode') or '').strip()
    cand = hf or fu
    if not cand:
        return False
    # solo latino, sin ningún hebreo
    return bool(LATIN.search(cand)) and not HEBREW.search(cand)


def is_catss_comma_marker(hw):
    """Línea de aparato CATSS (raw tipo ',,a') sin hebreo real.
    Marca un griego de la LXX sin correspondencia hebrea (común en las
    secciones arameas de Daniel/Esdras). No es hebreo: el griego es real."""
    hf = (hw.get('he_form') or '').strip()
    fu = (hw.get('full_unicode') or '').strip()
    if hf or fu:
        return False
    raw = (hw.get('raw') or '')
    return raw.startswith(',') and raw not in ('', 'GKADD')


def has_greek(hw):
    if (hw.get('gr_word') or '').strip() not in ('', '----'):
        return True
    for pg in (hw.get('prefix_gr') or []):
        if (pg or '').strip():
            return True
    prs = hw.get('prs_suffix') or {}
    if isinstance(prs, dict) and (prs.get('gr_word') or '').strip():
        return True
    return False


def main():
    cfg = resolve(SLUG)
    d = json.loads(cfg.final_json_path.read_text(encoding='utf-8'))
    removed = 0
    blanked = 0
    gkadd = 0
    for v in d['verses']:
        for p in v.get('pairs', []):
            hws = p.get('he_words', [])
            new = []
            for hw in hws:
                if is_catss_comma_marker(hw):
                    if has_greek(hw):
                        # griego LXX sin hebreo: tratar como adición (igual que Esdras)
                        gkadd += 1
                        if APPLY:
                            hw['raw'] = 'GKADD'
                            hw['he_form'] = ''
                            if 'full_unicode' in hw:
                                hw['full_unicode'] = ''
                            hw['he_morph'] = ''
                        new.append(hw)
                    else:
                        removed += 1
                        if not APPLY:
                            new.append(hw)
                elif is_latin_junk(hw):
                    if has_greek(hw):
                        # conserva griego (LXX real), vacía el hebreo falso
                        blanked += 1
                        if APPLY:
                            hw['he_form'] = ''
                            if 'full_unicode' in hw:
                                hw['full_unicode'] = ''
                        new.append(hw)
                    else:
                        # fantasma puro: sin hebreo y sin griego
                        removed += 1
                        if not APPLY:
                            new.append(hw)
                        # en APPLY se descarta
                else:
                    new.append(hw)
            if APPLY:
                p['he_words'] = new
    print(f'{cfg.label}: {removed} fantasmas eliminados, {blanked} hebreo-latino vaciado, '
          f'{gkadd} ,,a->GKADD (griego conservado) '
          + ('(APLICADO)' if APPLY else '(DRY)'))
    if APPLY and (removed or blanked or gkadd):
        cfg.final_json_path.write_text(json.dumps(d, ensure_ascii=False, indent=None), encoding='utf-8')


if __name__ == '__main__':
    main()
