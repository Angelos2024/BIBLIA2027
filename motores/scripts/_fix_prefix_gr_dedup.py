"""Elimina griego duplicado dentro de arrays prefix_gr (causa de DUP_UNI).

Dos patrones de duplicación que el resto de motores no cubren:
  (a) entradas consecutivas idénticas en prefix_gr  ej. ['ὧν','ὧν']
  (b) un token de prefix_gr que ya aparece dentro de gr_word de la misma palabra
      ej. prefix_gr=['τούτοις','τούτοις'] con gr_word='καὶ τούτοις'

En ambos casos se VACÍA el griego del slot (pgr[i]=''), conservando el slot y su
prefix_morph para no romper la alineación con los prefijos hebreos.

Uso: python _fix_prefix_gr_dedup.py <slug> [--apply]
"""
import json, sys, re
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
from book_config import resolve

APPLY = '--apply' in sys.argv
SLUG = next((a for a in sys.argv[1:] if a != '--apply'), None)
GREEK = re.compile(r'[\u0370-\u03FF\u1F00-\u1FFF]')
DIAC = re.compile(r'[\u0300-\u036f\u0345]')


def norm(s):
    import unicodedata
    s = unicodedata.normalize('NFD', (s or '').strip().lower())
    s = DIAC.sub('', s)
    return ''.join(ch for ch in s if ch.isalpha())


def iter_prefix_slots(pair):
    """Devuelve (setter, getter) ordenados solo para slots prefix_gr (1 token)."""
    slots = []
    for hw in pair.get('he_words', []):
        pgr = hw.get('prefix_gr')
        if not isinstance(pgr, list):
            continue
        for i in range(len(pgr)):
            slots.append((hw, i))
    return slots


def main():
    cfg = resolve(SLUG)
    d = json.loads(cfg.final_json_path.read_text(encoding='utf-8'))
    consec = 0
    instem = 0
    pairlvl = 0
    for v in d['verses']:
        for p in v.get('pairs', []):
            if p.get('kind') == 'gk_add':
                continue

            # (a) por-palabra: vaciar prefijo que duplica un token de su propia raíz
            #     o que se repite consecutivo dentro del mismo array.
            for hw in p.get('he_words', []):
                pgr = hw.get('prefix_gr') or []
                if not pgr:
                    continue
                stem_toks = {norm(t) for t in (hw.get('gr_word') or '').split() if GREEK.search(t)}
                prev = None
                for i, g in enumerate(pgr):
                    g = (g or '').strip()
                    if not g or not GREEK.search(g):
                        prev = None if not g else prev
                        continue
                    gn = norm(g)
                    if prev is not None and gn == prev:
                        if APPLY:
                            pgr[i] = ''
                        consec += 1
                        continue
                    if gn and gn in stem_toks:
                        if APPLY:
                            pgr[i] = ''
                        instem += 1
                        prev = None
                        continue
                    prev = gn

            # (b) a nivel de par: recorre TODOS los slots griegos en orden
            #     (prefix_gr -> gr_word -> prs) y vacía cualquier slot de UN solo
            #     token (prefijo, raíz o sufijo) que repite el último token
            #     emitido por el slot anterior. Los slots multi-token nunca se
            #     vacían (solo actualizan el contexto) para no perder texto.
            prev_last = None
            for hw in p.get('he_words', []):
                pgr = hw.get('prefix_gr') or []
                for i, g in enumerate(pgr):
                    g = (g or '').strip()
                    if not g or not GREEK.search(g):
                        continue
                    toks = g.split()
                    if len(toks) == 1 and prev_last is not None and norm(g) == prev_last:
                        if APPLY:
                            pgr[i] = ''
                        pairlvl += 1
                        continue
                    prev_last = norm(toks[-1])

                gw = (hw.get('gr_word') or '').strip()
                if gw and GREEK.search(gw):
                    toks = [t for t in gw.split() if GREEK.search(t)]
                    if len(toks) == 1 and prev_last is not None and norm(gw) == prev_last:
                        if APPLY:
                            hw['gr_word'] = ''
                        pairlvl += 1
                    elif toks:
                        prev_last = norm(toks[-1])

                prs = hw.get('prs_suffix') or {}
                if isinstance(prs, dict):
                    pg = (prs.get('gr_word') or '').strip()
                    if pg and GREEK.search(pg):
                        toks = [t for t in pg.split() if GREEK.search(t)]
                        if len(toks) == 1 and prev_last is not None and norm(pg) == prev_last:
                            if APPLY:
                                prs['gr_word'] = ''
                            pairlvl += 1
                        elif toks:
                            prev_last = norm(toks[-1])

    print(f'{cfg.label}: {consec} consec(intra), {instem} dup-de-raíz, {pairlvl} consec(par) vaciados '
          + ('(APLICADO)' if APPLY else '(DRY)'))
    if APPLY and (consec or instem or pairlvl):
        cfg.final_json_path.write_text(json.dumps(d, ensure_ascii=False, indent=None), encoding='utf-8')


if __name__ == '__main__':
    main()
