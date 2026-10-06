import json, sys
sys.stdout.reconfigure(encoding='utf-8')
with open(r'C:\Users\pik_y\Documents\TRADUCCION\data\genesis_final.json', encoding='utf-8') as f:
    data = json.load(f)
for v in data['verses']:
    if v.get('chapter')==1 and v.get('verse')==27:
        for i, p in enumerate(v['pairs']):
            for hw in p.get('he_words',[]):
                if hw.get('raw','') in ('B/CLM/W', 'B/CLM'):
                    print(f"=== par {i} raw={hw['raw']} ===")
                    for k, val in hw.items():
                        print(f"  {k} = {val!r}")
                    print()
        break
