import json, sys
sys.stdout.reconfigure(encoding='utf-8')
MAQAF = '\u05be'
data = json.loads(open('data/genesis_final.json', encoding='utf-8').read())
for ch, vs in [(1,2),(1,4),(1,11)]:
    v = next(v for v in data['verses'] if v['chapter']==ch and v['verse']==vs)
    found = []
    for p in v['pairs']:
        for hw in p.get('he_words',[]):
            he = hw.get('he_form','')
            if MAQAF in he:
                found.append(he)
    print(f"Gen {ch}:{vs} — maqaf en: {found}")
