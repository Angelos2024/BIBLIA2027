"""_fix_pron_prefix.py - Reubica pronombres griegos mal colocados en prefix_gr.

Los únicos prefijos hebreos inseparables son ו/ב/כ/ל/מ/ה/שׁ (CONJ/PREP/ART/PRT).
Un pronombre griego (αὐτοῦ, αὐτῶν, μου, σου…) NUNCA es un prefijo: si el motor de
split lo dejó en `prefix_gr`, es un artefacto. Corresponde al sufijo pronominal
hebreo y debe ir en `gr_word`, no como prefijo.

Solución: por cada prefix_gr que sea un pronombre griego, se mueve al `gr_word`
del mismo he_word (preservando orden) y se vacía el slot del prefijo. El
`gr_unicode` del par no cambia (el token sigue presente, solo cambia de columna
interna), así que no hace falta reconstruirlo.

Uso:
    python _fix_pron_prefix.py <slug> [--apply]
"""
import json, sys, unicodedata

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
from book_config import resolve


def _strip_gr(s):
    s = (s or '').strip().lower().replace('\u2019', '').replace("'", '')
    s = unicodedata.normalize('NFD', s)
    return ''.join(c for c in s if not unicodedata.combining(c))


_PRON = {
    'αυτου', 'αυτων', 'αυτης', 'αυτω', 'αυτον', 'αυτην', 'αυτο', 'αυτος',
    'αυτη', 'αυτοι', 'αυται', 'αυτους', 'αυτας', 'αυτα', 'αυτοις', 'αυταις',
    'εαυτου', 'εαυτων', 'εαυτω', 'εαυτον', 'εαυτης',
    'μου', 'μοι', 'με', 'εμου', 'εμοι', 'εμε',
    'σου', 'σοι', 'σε',
    'ημων', 'ημιν', 'ημας', 'υμων', 'υμιν', 'υμας',
}

# Cuantificador πᾶς ("todo") -> traduce siempre el hebreo כל; nunca es prefijo.
_PAS = {
    'πας', 'πασα', 'παν', 'παντα', 'παντες', 'πασαι', 'παντων', 'πασων',
    'παντος', 'πασης', 'παντι', 'παση', 'παντας', 'πασας', 'πασιν', 'πασι',
}


def _is_kol(hw):
    raw = (hw.get('raw') or '').lstrip('*=').strip()
    return raw in ('KL', 'KWL', 'KL/', 'KWL/')


def fix_book(slug, apply):
    cfg = resolve(slug)
    d = json.loads(cfg.final_json_path.read_text(encoding='utf-8'))
    moved = 0
    samples = []
    for v in d['verses']:
        if v.get('is_lxx_add'):
            continue
        for p in v.get('pairs', []):
            if p.get('kind') == 'gk_add':
                continue
            hws = p.get('he_words', [])
            for hw in hws:
                pgr = hw.get('prefix_gr') or []
                if not pgr:
                    continue
                for i, g in enumerate(pgr):
                    g = (g or '').strip()
                    gn = _strip_gr(g)
                    if not g or (gn not in _PRON and gn not in _PAS):
                        continue
                    # πᾶς ("todo") prefiere el hermano כל con hueco/omisión
                    target = hw
                    if gn in _PAS:
                        for sib in hws:
                            if sib is hw:
                                continue
                            if _is_kol(sib) and (sib.get('gr_word') or '').strip() in ('', '----'):
                                target = sib
                                break
                    tgw = (target.get('gr_word') or '').strip()
                    if not tgw or tgw == '----':
                        target['gr_word'] = g
                    elif gn not in {_strip_gr(t) for t in tgw.split()}:
                        target['gr_word'] = (tgw + ' ' + g).strip()
                    pgr[i] = ''
                    moved += 1
                    if len(samples) < 12:
                        kind = 'pron' if gn in _PRON else 'πᾶς'
                        samples.append(f"  {v['chapter']}:{v['verse']} {kind} '{g}' prefix -> gr_word")
                hw['prefix_gr'] = pgr
    print(f"{slug:<12} pronombres reubicados: {moved}")
    for s in samples:
        print(s)
    if apply and moved:
        cfg.final_json_path.write_text(
            json.dumps(d, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"  -> guardado {cfg.final_json_path.name}")
    return moved


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    apply = '--apply' in sys.argv
    slug = args[0] if args else 'genesis'
    fix_book(slug, apply)
