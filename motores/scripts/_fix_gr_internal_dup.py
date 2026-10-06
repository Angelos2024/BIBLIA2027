"""Colapsa tokens griegos idénticos consecutivos y normaliza placeholders.

- gr_word 'ὑμῖν ὑμῖν' -> 'ὑμῖν'  (duplicación interna por prefijo+sufijo)
- prefix_gr / prs gr_word igual.
- placeholders '—' / '–' (em/en dash sueltos) -> '----' (marcador de omisión),
  para que no contaminen el texto corrido.
- reconstruye pair.gr_unicode colapsando además duplicados consecutivos
  que surjan al concatenar prefijo + raíz de he_words distintos.

Uso: python _fix_gr_internal_dup.py <slug> [--apply]
"""
import json, sys, re
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
from book_config import resolve

APPLY = '--apply' in sys.argv
SLUG = next((a for a in sys.argv[1:] if a != '--apply'), None)
DASH_ONLY = re.compile(r'^[\u2012-\u2015\u2212\-]+$')  # —, –, ‒, ―, −, -
DASH_TOK = re.compile(r'^[\u2012-\u2015\u2212]+$')      # — – ‒ ― −  (no incluye '-' ASCII para no tocar '----')


def strip_stray_dashes(s):
    """Quita tokens que son solo guion tipográfico (— –) cuando la cadena
    tiene además contenido real. Si TODO son guiones, deja el valor intacto
    (lo maneja normalize_placeholder -> '----')."""
    if not s:
        return s
    toks = s.split()
    if len(toks) < 2:
        return s
    nondash = [t for t in toks if not DASH_TOK.match(t)]
    if not nondash:
        return s
    return ' '.join(nondash)


def collapse_consec(s):
    if not s or s == '----':
        return s
    toks = s.split()
    out = []
    for t in toks:
        if out and out[-1] == t:
            continue
        out.append(t)
    return ' '.join(out)


LETTERS_RE = re.compile(r'[\u0370-\u03FF\u1F00-\u1FFFA-Za-z\u05D0-\u05EA]')
SYMBOLS_ONLY = re.compile(r'^[^\w\u0370-\u03FF\u1F00-\u1FFF\u05D0-\u05EA]+$')


def normalize_placeholder(s):
    """Convierte cualquier token SIN letra real (griega/latina/hebrea) — solo
    símbolos/puntuación: '—', '–', '?', '...', '.', '+', '·' … — en el marcador
    de omisión '----'. Preserva '----' y cualquier cadena con contenido real."""
    if not s:
        return s
    st = s.strip()
    if not st or st == '----':
        return s
    if not LETTERS_RE.search(st) and (DASH_ONLY.match(st) or SYMBOLS_ONLY.match(st)
                                      or not any(ch.isalnum() for ch in st)):
        return '----'
    return s


def fix_field(s):
    s = normalize_placeholder(s)
    s = strip_stray_dashes(s)
    s = collapse_consec(s)
    return s


def rebuild_uni(pair):
    GREEK = re.compile(r'[\u0370-\u03FF\u1F00-\u1FFF]')
    parts = []
    for hw in pair.get('he_words', []):
        for pg in (hw.get('prefix_gr') or []):
            pg = (pg or '').strip()
            if pg and GREEK.search(pg):
                parts.append(pg)
        gr = (hw.get('gr_word') or '').strip()
        if gr and GREEK.search(gr):
            parts.append(gr)
        prs = hw.get('prs_suffix') or {}
        if isinstance(prs, dict):
            pg = (prs.get('gr_word') or '').strip()
            if pg and GREEK.search(pg):
                parts.append(pg)
    # colapsar duplicados consecutivos a nivel de token
    flat = ' '.join(parts).split()
    out = []
    for t in flat:
        if out and out[-1] == t:
            continue
        out.append(t)
    return ' '.join(out)


def main():
    cfg = resolve(SLUG)
    d = json.loads(cfg.final_json_path.read_text(encoding='utf-8'))
    stats = {'gr_word': 0, 'prefix_gr': 0, 'prs_gr': 0, 'placeholder': 0, 'uni': 0}
    for v in d['verses']:
        for p in v.get('pairs', []):
            # gk_add: el griego añadido vive en pair.gr_unicode (sin he_words).
            # No reconstruir ni tocar para no borrarlo.
            if p.get('kind') == 'gk_add':
                continue
            for hw in p.get('he_words', []):
                old = hw.get('gr_word') or ''
                new = fix_field(old)
                if new != old:
                    if new == '----' and old.strip() != '----':
                        stats['placeholder'] += 1
                    else:
                        stats['gr_word'] += 1
                    if APPLY:
                        hw['gr_word'] = new
                pgr = hw.get('prefix_gr') or []
                for i, pg in enumerate(pgr):
                    new = fix_field(pg or '')
                    if new != (pg or ''):
                        stats['prefix_gr'] += 1
                        if APPLY:
                            pgr[i] = new
                prs = hw.get('prs_suffix') or {}
                if isinstance(prs, dict) and prs.get('gr_word'):
                    new = fix_field(prs['gr_word'])
                    if new != prs['gr_word']:
                        stats['prs_gr'] += 1
                        if APPLY:
                            prs['gr_word'] = new
            if APPLY:
                old_uni = p.get('gr_unicode') or ''
                new_uni = rebuild_uni(p)
                if new_uni != old_uni:
                    stats['uni'] += 1
                    p['gr_unicode'] = new_uni
    print(f'{cfg.label}: ' + ' '.join(f'{k}={v}' for k, v in stats.items())
          + (' (APLICADO)' if APPLY else ' (DRY)'))
    if APPLY:
        cfg.final_json_path.write_text(json.dumps(d, ensure_ascii=False, indent=None), encoding='utf-8')


if __name__ == '__main__':
    main()
