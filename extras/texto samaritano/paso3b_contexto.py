# -*- coding: utf-8 -*-
"""PASO 3b - Volcado de contexto de los versos marcados, para adjudicar
recorridos/duplicados con la secuencia completa de palabras y sus tipos."""
import json, os

SRC = os.path.join("mapeo_genesis", "genesis_texto_samaritano.json")
HALL = os.path.join("mapeo_genesis", "genesis_paso3_hallazgos.json")
OUT = os.path.join("mapeo_genesis", "genesis_paso3_contexto.txt")

TAGS = {"common": " ", "variant": "~", "plus": "+", "omit": "-"}


def main():
    data = json.load(open(SRC, encoding="utf-8"))
    H = json.load(open(HALL, encoding="utf-8"))

    refs = []
    for cat in ("recorridos", "duplicados", "sin_vocalizar"):
        for d in H[cat]:
            r = d["ref"].replace("Gn ", "")
            if (cat, r) not in [(c, x) for c, x in refs]:
                refs.append((cat, r))

    seen = set()
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("PASO 3b - CONTEXTO DE VERSOS MARCADOS\n")
        f.write("Tipos:  (common)  ~variant  +plus  -omit\n")
        f.write("=" * 60 + "\n")
        for cat, r in refs:
            if r in seen:
                continue
            seen.add(r)
            ch, vs = r.split(":")
            entry = data["chapters"][ch][vs]
            f.write(f"\nGn {r}\n")
            for i, w in enumerate(entry["words"]):
                tag = TAGS.get(w["type"], "?")
                disp = w.get("text") or w.get("mt") or w.get("sp_cons")
                f.write(f"   [{i:>2}]{tag} {disp}   ({w.get('gloss','')})\n")
    print("Contexto escrito en", OUT)
    print("DONE")


if __name__ == "__main__":
    main()
