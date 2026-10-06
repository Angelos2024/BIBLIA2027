"""Find and fill remaining Spanish gaps using morphology-based + he_form rules."""
import json, sys, re, unicodedata
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

BOOK = sys.argv[1] if len(sys.argv) > 1 else 'deuteronomio'
APPLY = '--apply' in sys.argv

path = Path(rf'C:\Users\pik_y\Documents\TRADUCCION\data\{BOOK}_final.json')
data = json.loads(path.read_text(encoding='utf-8'))

MORPH_ES = {
    'CONJ': 'y',
    'PREP': 'en',
    'PREP.ART': 'en el',
    'ART': 'el',
    'REL': 'que',
    'NEG': 'no',
    'PRON.PR.T': 'el',
    'PRON.DEM': 'este',
    'PRON': '',
    'PART.OBJ.DIR': '(a)',
    'SUF': '',
}

PRS_ES = {
    'PRS.P1.COMMON.SG': 'mí', 'PRS.P1.COMMON.PL': 'nosotros',
    'PRS.P2.M.SG': 'ti', 'PRS.P2.F.SG': 'ti', 'PRS.P2.M.PL': 'ustedes',
    'PRS.P3.M.SG': 'él', 'PRS.P3.F.SG': 'ella', 'PRS.P3.M.PL': 'ellos', 'PRS.P3.F.PL': 'ellas',
    'SUF.DIR': '', 'SUF.PARAG.H': '', 'SUF.PARAG.N': '', 'SUF.PARAG.NUN': '',
}

def strip_niqqud(s):
    return ''.join(c for c in s if unicodedata.category(c) not in ('Mn', 'Cf')).rstrip('\u05BE-')

NPROP_ES = {
    'יהוה': 'YHWH', 'ישראל': 'Israel', 'משה': 'Moisés', 'יהושע': 'Josué',
    'אהרן': 'Aarón', 'יעקב': 'Jacob', 'יצחק': 'Isaac', 'אברהם': 'Abraham',
    'דוד': 'David', 'שאול': 'Saúl', 'יהודה': 'Judá', 'יוסף': 'José',
    'בנימן': 'Benjamín', 'לוי': 'Leví', 'שמעון': 'Simeón', 'ראובן': 'Rubén',
    'גד': 'Gad', 'דן': 'Dan', 'נפתלי': 'Neftalí', 'אשר': 'Aser',
    'זבולן': 'Zabulón', 'יששכר': 'Isacar', 'מנשה': 'Manasés', 'אפרים': 'Efraín',
    'מואב': 'Moab', 'אדום': 'Edom', 'מצרים': 'Egipto', 'בבל': 'Babilonia',
    'ארם': 'Aram', 'סיני': 'Sinaí', 'ציון': 'Sion', 'ירושלם': 'Jerusalén',
    'ירדן': 'Jordán', 'כנען': 'Canaán', 'שכם': 'Siquem', 'חברון': 'Hebrón',
    'בית-לחם': 'Belén', 'גלגל': 'Gilgal', 'שילה': 'Silo', 'עמון': 'Amón',
    'פלשתים': 'filisteos', 'מדין': 'Madián', 'עמלק': 'Amalec',
}

COMMON_HE_ES = {
    'ארץ': 'tierra', 'עיר': 'ciudad', 'בן': 'hijo', 'בני': 'hijos de',
    'אב': 'padre', 'אם': 'madre', 'איש': 'hombre', 'אשה': 'mujer',
    'יום': 'día', 'לילה': 'noche', 'מים': 'agua', 'שמים': 'cielos',
    'דבר': 'palabra', 'כל': 'todo', 'עם': 'pueblo', 'מלך': 'rey',
    'אלהים': 'Dios', 'אלהי': 'Dios de', 'פנים': 'rostro', 'פני': 'ante',
    'יד': 'mano', 'עין': 'ojo', 'עיני': 'ojos de', 'לב': 'corazón',
    'נפש': 'alma', 'דרך': 'camino', 'שם': 'nombre', 'בית': 'casa',
    'קול': 'voz', 'מלחמה': 'guerra', 'חרב': 'espada', 'שנה': 'año',
    'עמני': 'amonita', 'צלול': 'torta', 'אסירים': 'prisioneros',
    'אתי': 'tú', 'תוך': 'en medio de',
}

gaps = []
filled = 0
fill_sources = {'morph': 0, 'nprop': 0, 'common': 0, 'gloss': 0}

# Load Macula gloss fallback (Strong's-keyed)
MACULA = Path(r'C:\Users\pik_y\Documents\GitHub\Local-consults\estudio\angelos\IdiomaORIGEN\macula-hebrew.tsv')
gloss_map = {}
try:
    import csv
    SLUG_TO_MACULA = {
        "genesis": "GEN", "exodo": "EXO", "levitico": "LEV", "numeros": "NUM",
        "deuteronomio": "DEU", "josue": "JOS", "jueces": "JDG", "rut": "RUT",
        "1_samuel": "1SA", "2_samuel": "2SA", "1_reyes": "1KI", "2_reyes": "2KI",
        "1_cronicas": "1CH", "2_cronicas": "2CH", "esdras": "EZR", "nehemias": "NEH",
        "ester": "EST", "job": "JOB", "salmos": "PSA", "proverbios": "PRO",
        "eclesiastes": "ECC", "cantares": "SNG", "isaias": "ISA", "jeremias": "JER",
        "lamentaciones": "LAM", "ezequiel": "EZK", "daniel": "DAN", "oseas": "HOS",
        "joel": "JOL", "amos": "AMO", "abdias": "OBA", "jonas": "JON",
        "miqueas": "MIC", "nahum": "NAM", "habacuc": "HAB", "sofonias": "ZEP",
        "hageo": "HAG", "zacarias": "ZEC", "malaquias": "MAL",
    }
    book_code = SLUG_TO_MACULA.get(BOOK, '')
    if book_code:
        prefix = book_code + ' '
        with open(MACULA, encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                ref = row.get('ref', '')
                if not ref.startswith(prefix):
                    continue
                txt = row.get('text', '').strip()
                gl = row.get('gloss', '').strip()
                if txt and gl:
                    bare = strip_niqqud(txt)
                    if bare not in gloss_map:
                        gloss_map[bare] = gl
except Exception:
    pass

for v in data['verses']:
    ch, vs = v['chapter'], v['verse']
    for pi, p in enumerate(v.get('pairs', [])):
        for hi, hw in enumerate(p.get('he_words', [])):
            es = (hw.get('es') or '').strip()
            hf = (hw.get('he_form') or '').strip()
            hm = (hw.get('he_morph') or '').strip()
            if es or not hf:
                continue
            fill = None
            source = ''
            # 1) Morph-based
            for mkey, mval in MORPH_ES.items():
                if hm == mkey or hm.startswith(mkey + '.'):
                    fill = mval
                    source = 'morph'
                    break
            if not fill:
                for pkey, pval in PRS_ES.items():
                    if hm == pkey:
                        fill = pval
                        source = 'morph'
                        break
            # 2) Known proper nouns
            if not fill:
                bare = strip_niqqud(hf)
                if bare in NPROP_ES:
                    fill = NPROP_ES[bare]
                    source = 'nprop'
            # 3) Common HE words
            if not fill:
                bare = strip_niqqud(hf)
                if bare in COMMON_HE_ES:
                    fill = COMMON_HE_ES[bare]
                    source = 'common'
            # 4) Macula gloss fallback (English → used as-is for Strong's reference)
            if not fill:
                bare = strip_niqqud(hf)
                if bare in gloss_map:
                    fill = gloss_map[bare]
                    source = 'gloss'

            if fill:
                if APPLY:
                    hw['es'] = fill
                filled += 1
                fill_sources[source] = fill_sources.get(source, 0) + 1
            else:
                gaps.append(f'  {ch}:{vs} p{pi}h{hi} he_form={hf} morph={hm}')

print(f'ES gaps analysis: {BOOK} ({"APPLY" if APPLY else "DRY-RUN"})')
print('=' * 60)
print(f'  Filled total:            {filled}')
for src, cnt in sorted(fill_sources.items(), key=lambda x: -x[1]):
    if cnt:
        print(f'    - {src}: {cnt}')
print(f'  Remaining unfillable:    {len(gaps)}')
if gaps:
    print()
    for g in gaps[:30]:
        print(g)
    if len(gaps) > 30:
        print(f'  ... y {len(gaps)-30} mas')

if APPLY:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=None), encoding='utf-8')
    print(f'\nGuardado: {path}')
