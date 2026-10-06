# -*- coding: utf-8 -*-
"""Aplica NPROP.M.SG.A para אֲדֹנָי (Adonai divino) POR REGLA en libros donde
se verificó que todo qamats+P1 es divino.

REGLA de selección:
    consk empieza con אדנ / אדונ
    AND qamats bajo el ן final
    AND prs_suffix.he_morph contiene 'P1'   (excluye P3 'su señor' humano)
    (hiriq/tsere/segol humanos ya quedan fuera por no ser qamats)

Transformación por token:
    he_form <- he_form + prs_suffix.he_form (yod, con cantilación)
    he_morph <- NPROP.M.SG.A
    strongs  <- H136 (garantizado; los vacíos se completan)
    es       <- 'Adonai'
    prs_suffix <- {}
    es_source <- 'motor:adonai-morph'
    prefix_es intacto

Uso: python aplicar_adonai_nprop_regla.py libro1.json [libro2.json ...]
"""
from __future__ import annotations
import json, shutil, time, sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

NIQ=re.compile(r'[\u0591-\u05C7]')
QAMATS='\u05B8'
def consk(s): return ''.join(c for c in NIQ.sub('',s or '') if 0x05D0<=ord(c)<=0x05EA)
def qam_final_nun(hf):
    last=-1
    for i,c in enumerate(hf):
        if c in ('נ','ן'): last=i
    if last==-1: return False
    j=last+1; niq=''
    while j<len(hf) and 0x0591<=ord(hf[j])<=0x05C7: niq+=hf[j]; j+=1
    return QAMATS in niq

def backup(path):
    bkp=f"{path}.bak-adonai-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(path,bkp); return bkp

def procesar(path):
    b=backup(path)
    print(f'\n{"="*64}\n{path}\n[BACKUP] {b}')
    d=json.load(open(path,encoding='utf-8'))
    verses=d['verses'] if isinstance(d,dict) else d
    hechos=[]
    for v in verses:
        ch=v.get('chapter'); vs=v.get('verse')
        for pi,p in enumerate(v.get('pairs') or []):
            for wi,hw in enumerate(p.get('he_words') or []):
                hf=hw.get('he_form','')
                cs=consk(hf)
                if not (cs.startswith('אדנ') or cs.startswith('אדונ')): continue
                if not qam_final_nun(hf): continue
                prs=hw.get('prs_suffix') or {}
                prs_m=prs.get('he_morph','') if isinstance(prs,dict) else ''
                if 'P1' not in prs_m:   # excluye P3 humano y sin-prs
                    continue
                yod=prs.get('he_form','') if isinstance(prs,dict) else ''
                st_old=hw.get('strongs') or ''
                hw['he_form']=hf+yod if yod else hf
                hw['he_morph']='NPROP.M.SG.A'
                hw['strongs']='H136'
                hw['es']='Adonai'
                hw['prs_suffix']={}
                hw['es_source']='motor:adonai-morph'
                hechos.append((ch,vs,pi,wi,st_old))
    with open(path,'w',encoding='utf-8') as f:
        json.dump(d,f,ensure_ascii=False,indent=2)
    print(f'  aplicados: {len(hechos)}')
    for ch,vs,pi,wi,st in hechos:
        print(f'    {ch}:{vs} p{pi}/w{wi}  (st {st or "∅"}->H136)')
    return len(hechos)

def main():
    libros=sys.argv[1:]
    if not libros:
        print('Uso: aplicar_adonai_nprop_regla.py <archivo.json> ...'); return
    total=sum(procesar(p) for p in libros)
    print(f'\n═══ TOTAL aplicados: {total} tokens ═══')

if __name__=='__main__':
    main()
