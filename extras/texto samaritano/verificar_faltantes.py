# -*- coding: utf-8 -*-
"""Auditoria de completitud del pipeline samaritano de Genesis.
Busca lo que pueda faltar/estar mal. Escribe detalle a archivo (UTF-8) y
un resumen ASCII a consola."""
import json, os, re

BASE = "."
SRCB = "genesis_lectura_samaritana.json"
TXT = os.path.join("mapeo_genesis", "genesis_texto_samaritano.json")
FIN = os.path.join("mapeo_genesis", "genesis_samaritano_final.json")
OMI = os.path.join("mapeo_genesis", "genesis_omisiones.json")
HTML = "_print_genesis_samaritano.html"
OUT = os.path.join("mapeo_genesis", "auditoria_faltantes.txt")


def niq(s):
    return any(0x05B0 <= ord(c) <= 0x05BC for c in (s or ""))


def cons(s):
    return "".join(c for c in (s or "") if 0x05D0 <= ord(c) <= 0x05EA)


rep = []
def log(s): rep.append(s)


base = json.load(open(SRCB, encoding="utf-8"))
txt = json.load(open(TXT, encoding="utf-8"))
fin = json.load(open(FIN, encoding="utf-8"))
omi = json.load(open(OMI, encoding="utf-8"))

# 1) cobertura de capitulos/versiculos
base_v = {(c, v) for c in base["chapters"] for v in base["chapters"][c]}
txt_v = {(c, v) for c in txt["chapters"] for v in txt["chapters"][c]}
fin_v = {(c, v) for c in fin["chapters"] for v in fin["chapters"][c]}
log(f"Capitulos base/txt/fin: {len(base['chapters'])}/{len(txt['chapters'])}/{len(fin['chapters'])}")
log(f"Versiculos base/txt/fin: {len(base_v)}/{len(txt_v)}/{len(fin_v)}")
log(f"Versiculos en base y NO en txt: {sorted(base_v - txt_v)}")
log(f"Versiculos en txt y NO en fin: {sorted(txt_v - fin_v)}")

# 2) integridad por palabra en txt
tipos = {}
sin_voc = []          # visibles sin niqqud (no particulas de 1 letra)
empty_txt = []        # texto vacio en visibles
PARTIC = set("והלכמבשׁשמא")  # tolera 1-letra
for c in txt["chapters"]:
    for v in txt["chapters"][c]:
        ws = txt["chapters"][c][v]["words"]
        for i, w in enumerate(ws):
            tipos[w["type"]] = tipos.get(w["type"], 0) + 1
            if w["type"] in ("common", "variant", "plus", "moved"):
                t = w.get("text", "")
                if not t:
                    empty_txt.append((c, v, i, w["type"]))
                elif not niq(t) and len(cons(t)) > 1:
                    sin_voc.append((c, v, i, w["type"], t))
log(f"\nTipos (txt): {tipos}")
log(f"Visibles SIN vocalizar (>1 consonante): {len(sin_voc)}")
for x in sin_voc[:40]:
    log("   " + json.dumps(x, ensure_ascii=False))
log(f"Visibles con texto vacio: {len(empty_txt)}")
for x in empty_txt[:40]:
    log("   " + json.dumps(x, ensure_ascii=False))

# 3) lecturas finales vacias
empty_reading = [(c, v) for c in fin["chapters"] for v in fin["chapters"][c]
                 if not fin["chapters"][c][v]["reading"].strip()]
log(f"\nVersiculos con reading FINAL vacio: {len(empty_reading)} {empty_reading[:20]}")

# 4) omisiones sin glosa
no_gloss = sum(1 for c in omi for v in omi[c] for o in omi[c][v] if not o.get("gloss"))
tot_omi = sum(len(omi[c][v]) for c in omi for v in omi[c])
log(f"\nOmisiones totales: {tot_omi} | sin glosa: {no_gloss}")

# 5) HTML: conteo de versos renderizados y ADD+
if os.path.exists(HTML):
    h = open(HTML, encoding="utf-8").read()
    log(f"\nHTML versos (.verse): {h.count(chr(34)+'verse'+chr(34)) + h.count('class=\"verse\"')}")
    log(f"HTML ADD+ (class w add): {h.count('w add')}")
    log(f"HTML lineas esp: {h.count('>esp<')}  acad: {h.count('>acad<')}")

# 6) chequeo de versificacion: versiculos por capitulo (busca huecos en numeracion)
huecos = []
for c in sorted(txt["chapters"], key=int):
    nums = sorted(int(v) for v in txt["chapters"][c])
    faltan = [n for n in range(1, max(nums) + 1) if n not in nums]
    if faltan:
        huecos.append((c, faltan))
log(f"\nHuecos de numeracion de versiculos (capitulo, faltan): {huecos}")

# 7) match counts en base
mc = {}
for c in base["chapters"]:
    for v in base["chapters"][c]:
        for w in base["chapters"][c][v]["words"]:
            mc[w["match"]] = mc.get(w["match"], 0) + 1
log(f"\nConteo match en base: {mc}")

open(OUT, "w", encoding="utf-8").write("\n".join(rep))

# resumen ASCII a consola
print("AUDITORIA - resumen")
print(f"  Versiculos base/txt/fin: {len(base_v)}/{len(txt_v)}/{len(fin_v)}")
print(f"  Faltan en txt: {len(base_v - txt_v)} | faltan en fin: {len(txt_v - fin_v)}")
print(f"  Visibles sin vocalizar (>1 cons): {len(sin_voc)}")
print(f"  Visibles texto vacio: {len(empty_txt)}")
print(f"  Reading final vacio: {len(empty_reading)}")
print(f"  Omisiones sin glosa: {no_gloss}/{tot_omi}")
print(f"  Huecos numeracion: {len(huecos)}")
print(f"  Tipos: {tipos}")
print(f"  Detalle: {OUT}")
print("DONE")
