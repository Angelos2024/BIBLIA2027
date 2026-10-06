"""
Diagnóstico profundo de residuos en los 5 libros.
Lista las palabras concretas que aún fallan, agrupadas por tipo de error,
para poder corregir el motor con precisión.
"""
import sys, json, os
from collections import Counter
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

SHEVA='\u05B0'; HATAF_S='\u05B1'; HATAF_P='\u05B2'; HATAF_Q='\u05B3'
CHIRIK='\u05B4'; TSERE='\u05B5'; SEGOL='\u05B6'; PATACH='\u05B7'
QAMATS='\u05B8'; CHOLAM='\u05B9'; CHOLAM_H='\u05BA'; QUBUTS='\u05BB'
DAGESH='\u05BC'; SHIN_DOT='\u05C1'; SIN_DOT='\u05C2'
ALL_VOWELS={SHEVA,HATAF_S,HATAF_P,HATAF_Q,CHIRIK,TSERE,SEGOL,PATACH,QAMATS,CHOLAM,CHOLAM_H,QUBUTS}
HATAFS={HATAF_S,HATAF_P,HATAF_Q}
ALEF='\u05D0'; HE='\u05D4'; HET='\u05D7'; AYIN='\u05E2'
MEM='\u05DE'; MEM_F='\u05DD'; YOD='\u05D9'; VAV='\u05D5'
GUTTURALS={ALEF,HE,HET,AYIN}

BASE = r'C:\Users\pik_y\Documents\TRADUCCION\texto samaritano'
order = ['genesis','exodus','leviticus','numbers','deuteronomy']

def parse(s):
    units=[]; cc=None; cd=[]
    for ch in s:
        if 0x05D0<=ord(ch)<=0x05EA:
            if cc is not None: units.append((cc,cd))
            cc=ch; cd=[]
        elif ch in ALL_VOWELS or ch in (DAGESH,SHIN_DOT,SIN_DOT):
            cd.append(ch)
    if cc is not None: units.append((cc,cd))
    return units

def has_shuruq(s):
    return any(c==VAV and DAGESH in d for c,d in parse(s))

plural_bad=[]; vav_bad=[]; novowel=[]; hataf_bad=[]; sheva_bad=[]
final_seg=Counter()

for b in order:
    fp=os.path.join(BASE,f'{b}_lectura_samaritana.json')
    if not os.path.exists(fp): continue
    with open(fp,encoding='utf-8') as f: data=json.load(f)
    for ch,chap in data['chapters'].items():
        for vs,verse in chap.items():
            for w in verse['words']:
                sam=w['sam_reading']; mt=w['mt']; sp=w['sp_cons']
                if not mt: continue
                units=parse(sam); vowels=[c for c in sam if c in ALL_VOWELS]
                ref=f"{b[:3]} {ch}:{vs}"
                # plural -im not converted (genuine masc plural -im ending)
                # Pattern: ...(chirik) yod mem  -> should be tsere (-em)
                # Exclude -um verb suffixes (vav+dagesh = shuruq before mem)
                if (len(units) >= 3 and units[-1][0] in (MEM, MEM_F)
                        and units[-2][0] == YOD and CHIRIK in units[-2][1]):
                    plural_bad.append((ref,mt,sam))
                # vav conj not voweled
                if sp=='ו' and not vowels and not has_shuruq(sam):
                    vav_bad.append((ref,mt,sam))
                # no vowel multi-consonant
                if len(units)>1 and not vowels and not has_shuruq(sam):
                    novowel.append((ref,mt,sam))
                # residual hataf
                if any(v in HATAFS for v in vowels):
                    hataf_bad.append((ref,mt,sam))
                # residual mobile sheva (not last)
                for i in range(len(units)-1):
                    if SHEVA in units[i][1]:
                        sheva_bad.append((ref,mt,sam)); break

def show(title, lst, n=25):
    print(f"\n{'='*60}\n{title}: {len(lst)}\n{'='*60}")
    for ref,mt,sam in lst[:n]:
        print(f"  {ref:14} MT={mt}  ->  SAM={sam}")

show("PLURAL -im SIN CONVERTIR (deberia -em)", plural_bad)
show("VAV CONJUNCION DESNUDA", vav_bad)
show("MULTI-CONSONANTE SIN VOCAL", novowel)
show("HATAF RESIDUAL", hataf_bad)
show("SHEVA MOVIL RESIDUAL", sheva_bad)

print(f"\n{'='*60}\nRESUMEN")
print(f"  plural_bad={len(plural_bad)}  vav_bad={len(vav_bad)}  novowel={len(novowel)}  hataf={len(hataf_bad)}  sheva={len(sheva_bad)}")
