# -*- coding: utf-8 -*-
"""Quita es_source='spider:logosklogos' sin tocar es ni hebreo."""
import json
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data_master'
TAG = 'spider:logosklogos'
DRY = '--apply' not in __import__('sys').argv

def strip_spider_tag(obj: dict) -> bool:
    changed = False
    if obj.get('es_source') == TAG:
        del obj['es_source']
        changed = True
    return changed

total = 0
for path in sorted(DATA.glob('*_final.json')):
    data = json.loads(path.read_text(encoding='utf-8'))
    n = 0
    for v in data.get('verses') or []:
        for p in v.get('pairs') or []:
            for hw in p.get('he_words') or []:
                if strip_spider_tag(hw):
                    n += 1
                ps = hw.get('prs_suffix')
                if isinstance(ps, dict) and strip_spider_tag(ps):
                    n += 1
    if n:
        print(f'{path.name}: {n} etiquetas')
        total += n
        if not DRY:
            ts = time.strftime('%Y%m%d_%H%M%S')
            bak = path.with_suffix(f'.json.bak_strip_spider_tag_{ts}')
            shutil.copyfile(path, bak)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
            print(f'  -> saved, backup {bak.name}')

print(f'\n{"DRY-RUN" if DRY else "APPLY"} total: {total}')
if DRY and total:
    print('Ejecuta con --apply para guardar.')
