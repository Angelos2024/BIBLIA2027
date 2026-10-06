import json
d = json.load(open('genesis_lectura_samaritana.json', encoding='utf-8'))

def dump(ch, vs):
    v = d['chapters'][ch][vs]
    return [f"{w['sp_cons']} | MT:{w['mt']} | SAM:{w['sam_reading']} | {w.get('gloss','')}" for w in v['words']]

res = {}
for ref in ['1:5', '1:8', '1:13', '1:30']:
    c, vv = ref.split(':')
    res[ref] = dump(c, vv)

open('_dump.txt', 'w', encoding='utf-8').write(json.dumps(res, ensure_ascii=False, indent=1))
print('done')
