"""Auditoría: palabras donde R5 convirtió un cholam del MT en /u/ (qubuts/shuruq).
Separa los segolados qVtl (candidatos a /a-a/) del resto."""
import json, os, re
from collections import defaultdict

BASE = r'C:\Users\pik_y\Documents\TRADUCCION\texto samaritano'
ORDER = ['genesis', 'exodus', 'leviticus', 'numbers', 'deuteronomy']

TEAMIM = re.compile('[\u0591-\u05AF]')
CHOLAM = '\u05B9'; CHOLAM_H = '\u05BA'; QUBUTS = '\u05BB'; SEGOL = '\u05B6'
DAGESH = '\u05BC'; SHEVA = '\u05B0'; PATACH = '\u05B7'
VAV = '\u05D5'
VOWELS = {'\u05B0','\u05B1','\u05B2','\u05B3','\u05B4','\u05B5','\u05B6',
          '\u05B7','\u05B8','\u05B9','\u05BA','\u05BB'}

def strip_t(s): return TEAMIM.sub('', s)

def parse(s):
    units = []; c = None; d = []
    for ch in s:
        if '\u05D0' <= ch <= '\u05EA':
            if c is not None: units.append((c, d))
            c = ch; d = []
        elif ch in VOWELS or ch in (DAGESH, '\u05C1', '\u05C2'):
            d.append(ch)
    if c is not None: units.append((c, d))
    return units

def vowel(d):
    for x in d:
        if x in VOWELS: return x
    return None

def has_u(sam):
    if QUBUTS in sam: return True
    prev = ''
    for ch in sam:
        if ch == DAGESH and prev == VAV: return True
        prev = ch
    return False

def is_segolate(mt_units):
    # cholam en c[i], segol en c[i+1]  -> patrón qVtl
    for i in range(len(mt_units) - 1):
        if vowel(mt_units[i][1]) in (CHOLAM, CHOLAM_H):
            if vowel(mt_units[i+1][1]) == SEGOL:
                return True
    return False

buckets = {k: defaultdict(lambda: {'n': 0, 'ex': None})
           for k in ('subs', 'verb', 'nmpr', 'elohim', 'other_seg', 'nonseg')}

for b in ORDER:
    d = json.load(open(os.path.join(BASE, f'{b}_lectura_samaritana.json'), encoding='utf-8'))
    for ch, chap in d['chapters'].items():
        for vs, verse in chap.items():
            for w in verse['words']:
                mt = strip_t(w.get('mt', ''))
                if CHOLAM not in mt and CHOLAM_H not in mt:
                    continue
                sam = w['sam_reading']
                if not has_u(sam):
                    continue
                pos = w.get('pos', '')
                gloss = w.get('gloss', '')
                key = (w['sp_cons'], gloss)
                if not is_segolate(parse(mt)):
                    cat = 'nonseg'
                elif gloss == 'god(s)':
                    cat = 'elohim'
                elif pos == 'nmpr':
                    cat = 'nmpr'
                elif pos == 'subs':
                    cat = 'subs'
                elif pos == 'verb':
                    cat = 'verb'
                else:
                    cat = 'other_seg'
                bk = buckets[cat][key]
                bk['n'] += 1
                if not bk['ex']:
                    bk['ex'] = (mt, sam, f"{b[:3]} {ch}:{vs}")

def show(title, data, limit=None):
    items = sorted(data.items(), key=lambda x: -x[1]['n'])
    if limit: items = items[:limit]
    lines = [f"\n{'='*80}\n{title}  ({len(data)} formas, {sum(v['n'] for v in data.values())} tokens)\n{'='*80}"]
    for (cons, gloss), info in items:
        mt, sam, ref = info['ex']
        lines.append(f"  {cons:12} x{info['n']:<4} [{gloss:18}] MT:{mt:13} SAM:{sam:13} {ref}")
    return '\n'.join(lines)

out = []
out.append(show("A) SEGOLADOS NOMINALES (pos=subs) -> RECOMIENDO flip a /a-a/", buckets['subs']))
out.append(show("B) PARTICIPIOS/VERBOS segolados (pos=verb) -> TU DECISION", buckets['verb']))
out.append(show("C) OTRA categoria segolada (adjv/etc.) -> revisar", buckets['other_seg']))
out.append(show("D) NOMBRES PROPIOS segolados (Moshe, Goshen...) -> RECOMIENDO mantener /u/", buckets['nmpr']))
out.append(show("E) Formas de ELOHIM segoladas -> mantener /u/ (ya acordado)", buckets['elohim']))
for k in buckets:
    print(f"{k:10}: {len(buckets[k])} formas / {sum(v['n'] for v in buckets[k].values())} tokens")
open('_audit_cholam.txt', 'w', encoding='utf-8').write('\n'.join(out))
print("escrito _audit_cholam.txt")
