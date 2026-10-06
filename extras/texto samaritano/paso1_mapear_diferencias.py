# -*- coding: utf-8 -*-
"""
PASO 1 - Mapeo de diferencias MT vs Samaritano cuadrado (solo GENESIS).

Lee genesis_lectura_samaritana.json (que ya trae la alineacion NW del motor con
cada palabra etiquetada: exact / fuzzy / mt_only / sp_only) y consolida las
DIFERENCIAS en archivos limpios y revisables, SIN modificar el motor.

Clasificacion:
  - variante (fuzzy)  : palabra presente en ambos pero con consonantes distintas
  - plus     (sp_only): el samaritano AÑADE (no esta en MT)            -> futuro ADD+
  - omision  (mt_only): el MT la tiene y el samaritano la OMITE        -> futuro ocultar

Salidas en mapeo_genesis/:
  - genesis_mapeo_diferencias.json : por capitulo/verso -> {variantes, plus, omisiones}
  - genesis_diferencias_resumen.txt: reporte legible (un bloque por verso con diffs)
  - genesis_mapeo_stats.json       : totales y diagnostico
"""
import json, os, unicodedata

SRC = "genesis_lectura_samaritana.json"
OUT_DIR = "mapeo_genesis"
JSON_OUT = os.path.join(OUT_DIR, "genesis_mapeo_diferencias.json")
TXT_OUT = os.path.join(OUT_DIR, "genesis_diferencias_resumen.txt")
STATS_OUT = os.path.join(OUT_DIR, "genesis_mapeo_stats.json")


def strip_niqqud(s):
    return "".join(c for c in (s or "") if not (0x0591 <= ord(c) <= 0x05C7))


def has_niqqud(s):
    return any(0x05B0 <= ord(c) <= 0x05BB for c in (s or ""))


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(SRC, encoding="utf-8") as f:
        data = json.load(f)

    chapters = data["chapters"]
    mapeo = {}
    stats = {
        "verses_total": 0, "verses_con_diferencias": 0,
        "variantes": 0, "plus": 0, "omisiones": 0,
        "plus_sin_vocalizar": 0,      # diagnostico para Paso 3
        "top_versos_plus": [],
    }

    for ch in sorted(chapters, key=int):
        for vs in sorted(chapters[ch], key=int):
            entry = chapters[ch][vs]
            words = entry.get("words", [])
            stats["verses_total"] += 1

            variantes, plus, omisiones = [], [], []
            for idx, w in enumerate(words):
                m = w.get("match")
                if m == "fuzzy":
                    variantes.append({
                        "i": idx, "mt": w.get("mt", ""),
                        "sp_cons": w.get("sp_cons", ""),
                        "sam_reading": w.get("sam_reading", ""),
                        "gloss": w.get("gloss", ""), "sim": w.get("sim"),
                    })
                elif m == "sp_only":
                    sam = w.get("sam_reading", "")
                    sin_voc = not has_niqqud(sam)
                    if sin_voc:
                        stats["plus_sin_vocalizar"] += 1
                    plus.append({
                        "i": idx, "sp_cons": w.get("sp_cons", ""),
                        "sam_reading": sam, "gloss": w.get("gloss", ""),
                        "pos": w.get("pos", ""), "sin_vocalizar": sin_voc,
                    })
                elif m == "mt_only":
                    omisiones.append({
                        "i": idx, "mt": w.get("mt", ""),
                        "mt_cons": strip_niqqud(w.get("mt", "")),
                        "sam_reading": w.get("sam_reading", ""),
                        "gloss": w.get("gloss", ""),
                    })

            if variantes or plus or omisiones:
                stats["verses_con_diferencias"] += 1
                stats["variantes"] += len(variantes)
                stats["plus"] += len(plus)
                stats["omisiones"] += len(omisiones)
                mapeo.setdefault(ch, {})[vs] = {
                    "sp_consonantal": entry.get("sp_consonantal", ""),
                    "mt_vocalized": entry.get("mt_vocalized", ""),
                    "variantes": variantes, "plus": plus, "omisiones": omisiones,
                }

    # top versos por cantidad de plus
    top = []
    for ch in mapeo:
        for vs in mapeo[ch]:
            n = len(mapeo[ch][vs]["plus"])
            if n:
                top.append((n, f"Gn {ch}:{vs}"))
    top.sort(reverse=True)
    stats["top_versos_plus"] = [{"verso": r, "plus": n} for n, r in top[:15]]

    with open(JSON_OUT, "w", encoding="utf-8") as f:
        json.dump(mapeo, f, ensure_ascii=False, indent=1)
    with open(STATS_OUT, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=1)

    with open(TXT_OUT, "w", encoding="utf-8") as f:
        f.write("PASO 1 - DIFERENCIAS MT vs SAMARITANO CUADRADO (GENESIS)\n")
        f.write("=" * 60 + "\n")
        f.write(f"Versiculos con diferencias: {stats['verses_con_diferencias']}"
                f" / {stats['verses_total']}\n")
        f.write(f"Variantes: {stats['variantes']} | "
                f"Plus(ADD+): {stats['plus']} | Omisiones: {stats['omisiones']}\n")
        f.write("=" * 60 + "\n\n")
        for ch in sorted(mapeo, key=int):
            for vs in sorted(mapeo[ch], key=int):
                d = mapeo[ch][vs]
                f.write(f"Gn {ch}:{vs}\n")
                for v in d["variantes"]:
                    f.write(f"   VAR  [{v['i']:>2}] {v['mt']}  ->  {v['sp_cons']}"
                            f"   ({v['gloss']}, sim={v['sim']})\n")
                for p in d["plus"]:
                    flag = "  [SIN VOCALIZAR]" if p["sin_vocalizar"] else ""
                    f.write(f"   PLUS [{p['i']:>2}] {p['sp_cons']}"
                            f"   ({p['gloss']}){flag}\n")
                for o in d["omisiones"]:
                    f.write(f"   OMIT [{o['i']:>2}] {o['mt_cons']}"
                            f"   ({o['gloss']})\n")
                f.write("\n")

    print("PASO 1 completado.")
    print(f"  Versiculos con diferencias: {stats['verses_con_diferencias']} / {stats['verses_total']}")
    print(f"  Variantes (fuzzy):          {stats['variantes']}")
    print(f"  Plus (sp_only -> ADD+):     {stats['plus']}")
    print(f"    de los cuales sin vocalizar: {stats['plus_sin_vocalizar']}")
    print(f"  Omisiones (mt_only):        {stats['omisiones']}")
    print(f"  JSON : {JSON_OUT}")
    print(f"  TXT  : {TXT_OUT}")
    print(f"  STATS: {STATS_OUT}")
    print("DONE")


if __name__ == "__main__":
    main()
