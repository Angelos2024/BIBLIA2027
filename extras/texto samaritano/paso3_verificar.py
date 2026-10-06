# -*- coding: utf-8 -*-
"""
PASO 3 - Verificacion / QA de las inyecciones (GENESIS).

Detecta problemas en mapeo_genesis/genesis_texto_samaritano.json:
  A) pluses sin vocalizar (text == consonantico)
  B) RECORRIDOS: en un mismo verso, un 'plus' y una 'omit' con las MISMAS
     consonantes -> el alineador probablemente partio una palabra compartida
     (deberia ser 'common', no plus+omit).
  C) DUPLICADOS: un 'plus' con las mismas consonantes que una palabra vecina
     'common'/'variant' (posible insercion espuria por desfase).
  D) MALFORMACIONES: text vacio, espacios dobles, niqqud sin consonante,
     reading con espacios al inicio/fin o dobles.
"""
import json, os, unicodedata

SRC = os.path.join("mapeo_genesis", "genesis_texto_samaritano.json")
OUT = os.path.join("mapeo_genesis", "genesis_paso3_verificacion.txt")
OUT_JSON = os.path.join("mapeo_genesis", "genesis_paso3_hallazgos.json")

FINALS = {"\u05DA": "\u05DB", "\u05DD": "\u05DE", "\u05DF": "\u05E0",
          "\u05E3": "\u05E4", "\u05E5": "\u05E6"}


def strip_niqqud(s):
    return "".join(c for c in (s or "") if not (0x0591 <= ord(c) <= 0x05C7))


def cons_only(s):
    return "".join(c for c in strip_niqqud(s) if 0x05D0 <= ord(c) <= 0x05EA)


def normkey(s):
    return "".join(FINALS.get(c, c) for c in cons_only(s))


def has_niqqud(s):
    return any(0x05B0 <= ord(c) <= 0x05BB for c in (s or ""))


def main():
    with open(SRC, encoding="utf-8") as f:
        data = json.load(f)

    H = {"sin_vocalizar": [], "recorridos": [], "duplicados": [], "malformaciones": []}

    for ch in sorted(data["chapters"], key=int):
        for vs in sorted(data["chapters"][ch], key=int):
            ref = f"Gn {ch}:{vs}"
            entry = data["chapters"][ch][vs]
            words = entry["words"]

            # claves por tipo
            omit_keys = {normkey(w["mt"]): w for w in words if w["type"] == "omit"}
            for i, w in enumerate(words):
                t, text = w["type"], w.get("text", "")
                if t == "plus":
                    if w.get("voc_src") == "sin-vocalizar" or not has_niqqud(text):
                        H["sin_vocalizar"].append({"ref": ref, "i": i,
                            "sp_cons": w["sp_cons"], "gloss": w["gloss"]})
                    pk = normkey(w["sp_cons"])
                    # B) recorrido: mismo verso tiene una omit con misma consonante
                    if pk and pk in omit_keys:
                        H["recorridos"].append({"ref": ref, "i": i,
                            "cons": w["sp_cons"], "gloss": w["gloss"]})
                    # C) duplicado: vecino common/variant con misma consonante
                    for j in (i - 1, i + 1):
                        if 0 <= j < len(words):
                            nb = words[j]
                            if nb["type"] in ("common", "variant"):
                                nbk = normkey(nb["sp_cons"] or nb["mt"])
                                if pk and pk == nbk:
                                    H["duplicados"].append({"ref": ref, "i": i,
                                        "cons": w["sp_cons"], "vecino": j,
                                        "gloss": w["gloss"]})
                                    break
                # D) malformaciones por palabra
                if t != "omit" and not text:
                    H["malformaciones"].append({"ref": ref, "i": i, "tipo": "texto_vacio"})
                if "  " in text:
                    H["malformaciones"].append({"ref": ref, "i": i, "tipo": "espacio_doble", "text": text})

            # D) malformaciones del reading
            r = entry.get("reading", "")
            if r != r.strip() or "  " in r:
                H["malformaciones"].append({"ref": ref, "tipo": "reading_espacios"})

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(H, f, ensure_ascii=False, indent=1)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("PASO 3 - VERIFICACION DE INYECCIONES (GENESIS)\n")
        f.write("=" * 55 + "\n")
        for k in ("sin_vocalizar", "recorridos", "duplicados", "malformaciones"):
            f.write(f"\n## {k.upper()}  ({len(H[k])})\n")
            for d in H[k]:
                f.write("   " + json.dumps(d, ensure_ascii=False) + "\n")

    print("PASO 3 completado.")
    for k in ("sin_vocalizar", "recorridos", "duplicados", "malformaciones"):
        print(f"  {k:16}: {len(H[k])}")
    if H["recorridos"]:
        print("\n  Recorridos (muestra):")
        for d in H["recorridos"][:10]:
            print(f"     {d['ref']}  {d['cons']}  ({d['gloss']})")
    if H["duplicados"]:
        print("\n  Duplicados (muestra):")
        for d in H["duplicados"][:10]:
            print(f"     {d['ref']}  {d['cons']}  ({d['gloss']})")
    print(f"\n  Detalle: {OUT}")
    print("DONE")


if __name__ == "__main__":
    main()
