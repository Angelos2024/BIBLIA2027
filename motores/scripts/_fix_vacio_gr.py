"""_fix_vacio_gr.py - Elimina pares con griego "flotante" sin asignar (VACIO_GR).

Problema: algunos pares tienen `gr_unicode` (la LXX SI trae griego) pero ningun
he_word recibio ese griego en `gr_word`/`prefix_gr`. El griego queda visible en la
cabecera azul pero ninguna columna hebrea lo muestra -> "evaporado".

Causa tipica: pares Ketiv/Qere o con marcadores de aparato CATSS (*, **, =, {}),
donde el motor no supo a que variante adjudicar el griego.

Solucion (alineacion de correspondencias, no traduccion):
  - Si gr_unicode es un placeholder no-griego ('?', '·', '', '--') -> la LXX no
    tiene equivalente real: se marca el he_word principal como omision '----' y se
    limpia gr_unicode.
  - Si gr_unicode trae griego real -> se asigna integro al he_word principal del
    par (preferencia: Qere '**', luego forma hebrea mas larga, luego el ultimo
    he_word real). Asi el griego deja de estar huerfano y queda bajo su hebreo.

Nunca toca pares ya asignados ni pares gk_add. Idempotente.

Uso:
    python _fix_vacio_gr.py <slug> [--apply]
"""
import json, sys, re

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
from book_config import resolve

GREEK_RE = re.compile(r'[\u0370-\u03FF\u1F00-\u1FFF]')
PLACEHOLDERS = {'?', '·', '', '--', '---', '----', '""', "''"}


def is_real_he(hw):
    raw = (hw.get('raw') or '')
    he = (hw.get('he_form') or hw.get('full_unicode') or '').strip()
    return bool(he) and raw != 'GKADD'


def has_assigned_greek(hws):
    for hw in hws:
        gw = (hw.get('gr_word') or '').strip()
        if gw and gw != '----':
            return True
        if any((g or '').strip() for g in (hw.get('prefix_gr') or [])):
            return True
    return False


def pick_primary(reals):
    # Qere (raw '**') tiene prioridad sobre Ketiv (raw '*')
    qere = [hw for hw in reals if (hw.get('raw') or '').startswith('**')]
    if qere:
        return qere[-1]
    # forma hebrea mas larga (mas "contenido")
    reals_sorted = sorted(
        reals,
        key=lambda hw: len((hw.get('he_form') or hw.get('full_unicode') or '')),
        reverse=True)
    return reals_sorted[0]


def fix_book(slug, apply):
    cfg = resolve(slug)
    d = json.loads(cfg.final_json_path.read_text(encoding='utf-8'))
    assigned = 0
    omitted = 0
    samples = []
    for v in d['verses']:
        if v.get('is_lxx_add'):
            continue
        for p in v.get('pairs', []):
            if p.get('kind') == 'gk_add':
                continue
            hws = p.get('he_words', [])
            uni = (p.get('gr_unicode') or '').strip()
            if not uni or not hws:
                continue
            if has_assigned_greek(hws):
                continue
            reals = [hw for hw in hws if is_real_he(hw)]
            if not reals:
                continue

            primary = pick_primary(reals)
            ref = f"{v['chapter']}:{v['verse']}"

            if uni in PLACEHOLDERS or not GREEK_RE.search(uni):
                # sin griego real -> omision
                primary['gr_word'] = '----'
                p['gr_unicode'] = ''
                omitted += 1
                if len(samples) < 14:
                    samples.append(f"  {ref} placeholder {uni!r} -> '----' (omision)")
            else:
                primary['gr_word'] = uni
                assigned += 1
                if len(samples) < 14:
                    he = (primary.get('he_form') or primary.get('full_unicode') or '')
                    samples.append(f"  {ref} '{uni}' -> {he!r}")

    print(f"{slug:<12} asignados: {assigned}   omisiones: {omitted}")
    for s in samples:
        print(s)
    if apply and (assigned or omitted):
        cfg.final_json_path.write_text(
            json.dumps(d, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"  -> guardado {cfg.final_json_path.name}")
    return assigned + omitted


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    apply = '--apply' in sys.argv
    slug = args[0] if args else 'genesis'
    fix_book(slug, apply)
