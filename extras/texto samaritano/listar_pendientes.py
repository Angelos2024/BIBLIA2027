"""Lista las palabras sp_only aún sin vocalizar (vocal_source='none')."""
import sys, json, os
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = r'C:\Users\pik_y\Documents\TRADUCCION\texto samaritano'
ORDER = ['genesis','exodus','leviticus','numbers','deuteronomy']

agg = defaultdict(lambda: {'n':0,'pos':set(),'gloss':set(),'refs':[]})
for b in ORDER:
    with open(os.path.join(BASE,f'{b}_lectura_samaritana.json'),encoding='utf-8') as f:
        data=json.load(f)
    for ch,chap in data['chapters'].items():
        for vs,verse in chap.items():
            for w in verse['words']:
                if w.get('match')=='sp_only' and w.get('vocal_source')=='none':
                    k=w['sp_cons']
                    agg[k]['n']+=1
                    agg[k]['pos'].add(w.get('pos',''))
                    agg[k]['gloss'].add(w.get('gloss',''))
                    if len(agg[k]['refs'])<3:
                        agg[k]['refs'].append(f"{b[:3]} {ch}:{vs}")

print(f"Total formas unicas sin resolver: {len(agg)}")
print(f"Total ocurrencias: {sum(v['n'] for v in agg.values())}\n")
for k,v in sorted(agg.items(), key=lambda x:-x[1]['n']):
    pos=','.join(sorted(p for p in v['pos'] if p))
    gl=','.join(sorted(g for g in v['gloss'] if g))
    print(f"  {k:18} x{v['n']:<2} [{pos:6}] {gl:22} {v['refs'][0]}")
