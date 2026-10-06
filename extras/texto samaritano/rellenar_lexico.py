"""
Rellenado léxico de palabras exclusivas del SP
===============================================
Las palabras que solo existen en el Pentateuco Samaritano (sin contraparte
masorética) no pueden vocalizarse derivándolas del MT. Pero la inmensa
mayoría son ARMONIZACIONES: repeticiones de frases/palabras que SÍ aparecen
vocalizadas en otra parte de la Torá.

Este script:
  1. Construye un léxico global a partir de las ~110k palabras ya vocalizadas
     (forma consonántica + categoría gramatical -> lectura samaritana más frecuente).
  2. Rellena las palabras 'sp_only' buscándolas en ese léxico.
  3. Reescribe los 5 JSON marcando la fuente ('vocal_source': 'lexicon').

Uso: ejecutar DESPUÉS de generar los 5 libros con motor_samaritano.py
"""
import sys, json, os, re
from collections import Counter, defaultdict
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Niqqud / marks
NIQQUD = lambda c: '\u05B0' <= c <= '\u05BB'
DAGESH = '\u05BC'
TEAMIM = re.compile('[\u0591-\u05AF]')  # cantillation marks
SHIN_DOT = '\u05C1'; SIN_DOT = '\u05C2'
VAV = '\u05D5'

def normalize_cons(text):
    out = []
    for ch in text:
        cp = ord(ch)
        if 0x05D0 <= cp <= 0x05EA:
            # map finals to base
            fmap = {'\u05DA':'\u05DB','\u05DD':'\u05DE','\u05DF':'\u05E0',
                    '\u05E3':'\u05E4','\u05E5':'\u05E6'}
            out.append(fmap.get(ch, ch))
        elif cp in (0xFB2A, 0xFB2B):
            out.append('\u05E9')
    return ''.join(out)

def strip_teamim(s):
    return TEAMIM.sub('', s)

def is_vocalized(s):
    if any(NIQQUD(c) for c in s):
        return True
    # shuruq = vav + dagesh
    prev = ''
    for c in s:
        if c == DAGESH and prev == VAV:
            return True
        prev = c
    return False

BASE = r'C:\Users\pik_y\Documents\TRADUCCION\texto samaritano'
ORDER = ['genesis','exodus','leviticus','numbers','deuteronomy']
paths = {b: os.path.join(BASE, f'{b}_lectura_samaritana.json') for b in ORDER}

# ── 1. Load all books ────────────────────────────────────
books = {}
for b in ORDER:
    with open(paths[b], encoding='utf-8') as f:
        books[b] = json.load(f)

# ── 2. Build global lexicon ──────────────────────────────
# key (cons, pos) -> Counter(reading)   and   cons -> Counter(reading)
lex_pos = defaultdict(Counter)
lex_any = defaultdict(Counter)

for b in ORDER:
    for ch, chap in books[b]['chapters'].items():
        for vs, verse in chap.items():
            for w in verse['words']:
                sr = w['sam_reading']
                if not is_vocalized(sr):
                    continue
                reading = strip_teamim(sr)
                cons = normalize_cons(reading)
                if not cons:
                    continue
                pos = w.get('pos', '')
                lex_pos[(cons, pos)][reading] += 1
                lex_any[cons][reading] += 1

print(f"Léxico construido: {len(lex_any)} formas consonánticas únicas")

# ── 3. Fill sp_only words ────────────────────────────────
def lookup(cons, pos):
    """Return (reading, confidence, source) or (None, 0, None)."""
    if pos and (cons, pos) in lex_pos:
        ctr = lex_pos[(cons, pos)]
        rd, n = ctr.most_common(1)[0]
        return rd, n / sum(ctr.values()), 'lex_pos'
    if cons in lex_any:
        ctr = lex_any[cons]
        rd, n = ctr.most_common(1)[0]
        return rd, n / sum(ctr.values()), 'lex_any'
    return None, 0.0, None

totals = Counter()
unresolved = Counter()
per_book = {}

for b in ORDER:
    filled = 0; missed = 0
    for ch, chap in books[b]['chapters'].items():
        for vs, verse in chap.items():
            changed = False
            for w in verse['words']:
                if w.get('match') != 'sp_only':
                    continue
                if is_vocalized(w['sam_reading']):
                    continue
                cons = normalize_cons(w['sp_cons'])
                rd, conf, src = lookup(cons, w.get('pos', ''))
                if rd and rd != w['sam_reading']:
                    w['sam_reading'] = rd
                    w['vocal_source'] = 'lexicon'
                    w['sim'] = round(conf, 3)
                    filled += 1; changed = True
                else:
                    w['vocal_source'] = 'none'
                    missed += 1
                    unresolved[w['sp_cons']] += 1
            if changed:
                verse['sam_reading'] = ' '.join(x['sam_reading'] for x in verse['words'])
    per_book[b] = (filled, missed)
    totals['filled'] += filled; totals['missed'] += missed

# ── 4. Write back ────────────────────────────────────────
for b in ORDER:
    books[b].setdefault('stats', {})['lexicon_filled'] = per_book[b][0]
    books[b]['stats']['lexicon_unresolved'] = per_book[b][1]
    with open(paths[b], 'w', encoding='utf-8') as f:
        json.dump(books[b], f, ensure_ascii=False, indent=2)

# ── 5. Report ────────────────────────────────────────────
print(f"\n{'='*60}\nRELLENADO LÉXICO DE PALABRAS SP-ONLY\n{'='*60}")
for b in ORDER:
    fl, ms = per_book[b]
    tot = fl + ms
    pct = fl/tot*100 if tot else 0
    print(f"  {b:13} rellenadas={fl:5}  sin resolver={ms:4}  ({pct:.1f}%)")
T = totals['filled'] + totals['missed']
print(f"  {'TOTAL':13} rellenadas={totals['filled']:5}  sin resolver={totals['missed']:4}  ({totals['filled']/T*100:.1f}%)")

print(f"\n  Top 20 sin resolver (consonantal, frecuencia):")
for cons, n in unresolved.most_common(20):
    print(f"    {cons:20} x{n}")
