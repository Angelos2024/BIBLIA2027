import json, sys
sys.stdout.reconfigure(encoding='utf-8')
with open(r'C:\Users\pik_y\Documents\TRADUCCION\data\genesis_final.json', encoding='utf-8') as f:
    data = json.load(f)

EMPTY = {'', '.', '·', '-', '--'}

print("=== Tokens con he_form vacío/punto en todo Génesis ===")
count = 0
for v in data['verses']:
    ref = v.get('ref','')
    for i, p in enumerate(v['pairs']):
        for hw in p.get('he_words',[]):
            he = hw.get('he_form','')
            raw = hw.get('raw','')
            es = hw.get('es','')
            gr = hw.get('gr_word','')
            if he.strip() in EMPTY:
                count += 1
                print(f"  {ref} par {i}: raw={raw!r} he={he!r} es={es!r} gr={gr!r}")
        # prefijos con form vacía
        for hw in p.get('he_words',[]):
            for j, pf in enumerate(hw.get('prefix_forms',[])):
                if pf.strip() in EMPTY:
                    print(f"  {ref} par {i} pfx[{j}]: raw={hw.get('raw','')!r} pfx_form={pf!r}")
                    count += 1
print(f"Total tokens problemáticos: {count}")
