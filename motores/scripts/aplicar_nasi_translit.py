# -*- coding: utf-8 -*-
"""Motor de transliteración del sustantivo נָשִׂיא (Nasí, H5387) y sus flexiones.

Raíz Nasí ("príncipe/líder"). Translitera SOLO el campo `es` de cada token
cuyo lema sea H5387 (o esqueleto consonántico נשיא… con morfología SUBS),
usando el motor `translit_nombres.transliterar` sobre la forma fusionada
(raíz + sufijo pronominal), de modo que cada flexión reciba su grafía:

    singular abs.  נָשִׂיא        -> Nasí
    singular const. נְשִׂיא        -> Nesí
    plural         נְשִׂיאִ(י)ם   -> Nesi'im
    plural const.  נְשִׂיאֵי       -> Nesi'é
    con sufijos    נְשִׂיאָיו…     -> Nesi'av / Nesi'ehá / …

No toca hebreo, griego, morfología, strongs ni sufijos: únicamente `es`.

Uso:
    python motores/scripts/aplicar_nasi_translit.py --book genesis
    python motores/scripts/aplicar_nasi_translit.py --book genesis --apply
"""
from __future__ import annotations
import argparse, io, json, re, shutil, sys, time, unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / 'visor'))
from translit_nombres import transliterar, he_fusionado_hw  # noqa: E402

DATA_DIR = ROOT / 'data_master'
STRONG_NASI = 'H5387'
STEM_CONSK = 'נשיא'  # esqueleto consonántico de la raíz


def norm_strong(raw: str) -> str:
    m = re.match(r'^([HG])0*(\d+)', str(raw or '').upper())
    return f'{m.group(1)}{m.group(2)}' if m else ''


def consk(s: str) -> str:
    s = unicodedata.normalize('NFC', s or '')
    return ''.join(c for c in s if 0x05D0 <= ord(c) <= 0x05EA)


def es_nasi(hw: dict) -> bool:
    if norm_strong(hw.get('strongs')) == STRONG_NASI:
        return True
    # Respaldo: token sin Strong pero con esqueleto de la raíz y morfología SUBS.
    ck = consk(hw.get('he_form', ''))
    morph = str(hw.get('he_morph') or '')
    return ck.startswith(STEM_CONSK) and morph.startswith('SUBS')


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    ap = argparse.ArgumentParser()
    ap.add_argument('--book', default='genesis')
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    dm = DATA_DIR / f'{args.book}_final.json'
    if not dm.exists():
        print(f'No existe {dm}', file=sys.stderr)
        return 1
    d = json.loads(dm.read_text(encoding='utf-8'))

    cambios = []
    for v in d.get('verses', []):
        ref = v.get('ref') or f"{v.get('chapter')}:{v.get('verse')}"
        for pi, p in enumerate(v.get('pairs') or []):
            if p.get('kind') == 'gk_add':
                continue
            for wi, hw in enumerate(p.get('he_words') or []):
                if not es_nasi(hw):
                    continue
                fused = he_fusionado_hw(hw) or hw.get('he_form') or ''
                esp = transliterar(fused).get('espanol', '')
                if not esp:
                    continue
                old = hw.get('es') or ''
                if old != esp:
                    cambios.append((ref, pi, wi, hw.get('he_form'),
                                    hw.get('he_morph'), old, esp))
                    if args.apply:
                        hw['es'] = esp

    print(f"═══ Motor Nasí (H5387) · {args.book} · {'APPLY' if args.apply else 'DRY-RUN'} ═══")
    print(f"tokens a transliterar: {len(cambios)}")
    for ref, pi, wi, hf, mo, old, new in cambios:
        print(f"  {ref:<10} p{pi}/w{wi}  {hf!r:16} {mo:<16} {old!r:18} -> {new!r}")

    if args.apply and cambios:
        ts = time.strftime('%Y%m%d_%H%M%S')
        bak = dm.with_suffix(f'.json.bak_nasi_{ts}')
        shutil.copyfile(dm, bak)
        dm.write_text(json.dumps(d, ensure_ascii=False, separators=(',', ':')),
                      encoding='utf-8')
        print(f"\nsaved {dm.name}  backup {bak.name}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
