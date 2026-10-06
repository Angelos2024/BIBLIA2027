"""Lista todas las palabras SP-only aún sin vocalizar (vocal_source='none')."""
import sys, json, os
from collections import Counter
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = r'C:\Users\pik_y\Documents\TRADUCCION\texto samaritano'
ORDER = ['genesis','exodus','leviticus','numbers','deuteronomy']

agg = {}
for b in ORDER:
    with open(os.path.join(BASE, f'{b}_lectura_samaritana.json'), encoding='utf-8') as f:
        data = json.load(f)
    for ch, chap in data['chapters'].items():
        for vs, verse in chap.items():
            for w in verse['words']:
                if w.get('vocal_source') == 'none':
                    key = w['sp_cons']
                    if key not in agg:
                        agg[key] = {'n':0,'pos':w.get('pos',''),'gloss':w.get('gloss',''),
                                    'refs':[]}
                    agg[key]['n'] += 1
                    if len(agg[key]['refs']) < 3:
                        agg[key]['refs'].append(f"{b[:3]} {ch}:{vs}")

print(f"Total formas únicas sin resolver: {len(agg)}  (tokens: {sum(v['n'] for v in agg.values())})\n")
for cons, info in sorted(agg.items(), key=lambda x:-x[1]['n']):
    print(f"  {cons:16} x{info['n']:<2} [{info['pos']:5}] {info['gloss']:20} {', '.join(info['refs'])}")
