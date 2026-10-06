"""
Analiza las palabras exclusivas del SP (sin contraparte MT) y mide
cuántas podríamos vocalizar usando un léxico construido con las
palabras ya alineadas/vocalizadas de toda la Torá.
"""
import sys, json, os
from collections import Counter, defaultdict
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

FINAL_MAP = {'\u05DA':'\u05DB','\u05DD':'\u05DE','\u05DF':'\u05E0',
             '\u05E3':'\u05E4','\u05E5':'\u05E6'}
SHIN='\u05E9'
def normalize_cons(text):
    out=[]
    for ch in text or '':
        cp=ord(ch)
        if 0x05D0<=cp<=0x05EA: out.append(FINAL_MAP.get(ch,ch))
        elif cp in (0xFB2A,0xFB2B,0xFB2C,0xFB2D): out.append(SHIN)
    return ''.join(out)

BASE=r'C:\Users\pik_y\Documents\TRADUCCION\texto samaritano'
order=['genesis','exodus','leviticus','numbers','deuteronomy']

lexicon=defaultdict(Counter)   # cons_norm -> Counter(sam_reading)
sp_only=[]                      # list of (book,ch,vs,sp_cons,pos,gloss)

for b in order:
    fp=os.path.join(BASE,f'{b