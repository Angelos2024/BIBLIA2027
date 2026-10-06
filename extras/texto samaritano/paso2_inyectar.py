# -*- coding: utf-8 -*-
"""
PASO 2 - Inyeccion de las palabras samaritanas (solo GENESIS).

- Vocaliza los pluses (sp_only) "con el motor": reutiliza la lectura samaritana
  que el motor YA calculo para las ~26.785 palabras EXACTAS de todo el Pentateuco
  (construye un lexico consonantico_SP -> lectura_samaritana). Para los pluses que
  no aparezcan en el lexico, aplica las reglas del motor sobre el consonantico
  como respaldo; lo que quede sin vocalizar se marca para revision (Paso 3).
- Genera un JSON NUEVO (no toca genesis_lectura_samaritana.json) con el flujo de
  palabras inyectado y vocalizado, clasificando cada palabra:
     common (exact) | variant (fuzzy) | plus (sp_only) | omit (mt_only)

Salida: mapeo_genesis/genesis_texto_samaritano.json
        mapeo_genesis/genesis_paso2_stats.json
"""
import json, os, collections

from motor_samaritano import parse_word, apply_samaritan_rules, rebuild

BOOKS = ["genesis", "exodus", "leviticus", "numbers", "deuteronomy"]
SRC_GEN = "genesis_lectura_samaritana.json"
OUT_DIR = "mapeo_genesis"
OUT_JSON = os.path.join(OUT_DIR, "genesis_texto_samaritano.json")
OUT_STATS = os.path.join(OUT_DIR, "genesis_paso2_stats.json")

FINALS = {"\u05DA": "\u05DB", "\u05DD": "\u05DE", "\u05DF": "\u05E0",
          "\u05E3": "\u05E4", "\u05E5": "\u05E6"}


def has_niqqud(s):
    return any(0x05B0 <= ord(c) <= 0x05BB for c in (s or ""))


def normkey(cons):
    return "".join(FINALS.get(c, c) for c in (cons or ""))


def build_lexicon():
    """consonantico_SP -> lectura_samaritana (de palabras EXACTAS ya vocalizadas)."""
    exact = collections.defaultdict(collections.Counter)
    exact_n = collections.defaultdict(collections.Counter)
    fuzzy = collections.defaultdict(collections.Counter)
    for b in BOOKS:
        path = f"{b}_lectura_samaritana.json"
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for ch in data.get("chapters", {}).values():
            for vs in ch.values():
                for w in vs.get("words", []):
                    spc, sam, m = w.get("sp_cons"), w.get("sam_reading"), w.get("match")
                    if not spc or not has_niqqud(sam):
                        continue
                    if m == "exact":
                        exact[spc][sam] += 1
                        exact_n[normkey(spc)][sam] += 1
                    elif m == "fuzzy":
                        fuzzy[spc][sam] += 1
    return exact, exact_n, fuzzy


def vocalize_plus(spc, pos, vt, vs, lex):
    exact, exact_n, fuzzy = lex
    if spc in exact:
        return exact[spc].most_common(1)[0][0], "lexico-exacto"
    if spc in fuzzy:
        return fuzzy[spc].most_common(1)[0][0], "lexico-fuzzy"
    nk = normkey(spc)
    if nk in exact_n:
        return exact_n[nk].most_common(1)[0][0], "lexico-norm"
    # respaldo: reglas del motor sobre el consonantico
    try:
        sam = rebuild(apply_samaritan_rules(parse_word(spc), pos or "", vt=vt or "", vs=vs or ""))
    except Exception:
        sam = spc
    if has_niqqud(sam):
        return sam, "motor-consonantico"
    return spc, "sin-vocalizar"


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    lex = build_lexicon()
    print(f"Lexico exacto: {len(lex[0])} formas | fuzzy: {len(lex[2])} formas")

    with open(SRC_GEN, encoding="utf-8") as f:
        gen = json.load(f)

    out = {"book": "Genesis",
           "description": "Texto samaritano de Genesis: pluses inyectados y vocalizados (Paso 2)",
           "leyenda": {"common": "igual MT/SP", "variant": "variante",
                       "plus": "adicion samaritana (ADD+)", "omit": "omitida por SP"},
           "chapters": {}}

    st = {"plus_total": 0, "plus_vocalizados": 0,
          "fuentes": collections.Counter(), "sin_vocalizar_detalle": []}

    TYPE = {"exact": "common", "fuzzy": "variant",
            "sp_only": "plus", "mt_only": "omit"}

    for ch in sorted(gen["chapters"], key=int):
        out_ch = {}
        for vs in sorted(gen["chapters"][ch], key=int):
            entry = gen["chapters"][ch][vs]
            words_out = []
            for w in entry.get("words", []):
                m = w.get("match")
                typ = TYPE.get(m, m)
                text = w.get("sam_reading", "")
                voc_src = None
                if m == "sp_only":
                    st["plus_total"] += 1
                    text, voc_src = vocalize_plus(
                        w.get("sp_cons", ""), w.get("pos", ""),
                        w.get("vt", ""), w.get("vs", ""), lex)
                    st["fuentes"][voc_src] += 1
                    if voc_src != "sin-vocalizar":
                        st["plus_vocalizados"] += 1
                    else:
                        st["sin_vocalizar_detalle"].append(
                            {"ref": f"{ch}:{vs}", "sp_cons": w.get("sp_cons", ""),
                             "gloss": w.get("gloss", "")})
                wo = {"text": text, "type": typ,
                      "sp_cons": w.get("sp_cons", ""), "mt": w.get("mt", ""),
                      "gloss": w.get("gloss", "")}
                if voc_src:
                    wo["voc_src"] = voc_src
                words_out.append(wo)

            out_ch[vs] = {
                # lectura con TODO inyectado y pluses ya vocalizados
                "reading": " ".join(x["text"] for x in words_out if x["text"]),
                "words": words_out,
            }
        out["chapters"][ch] = out_ch

    out["stats_paso2"] = {
        "plus_total": st["plus_total"],
        "plus_vocalizados": st["plus_vocalizados"],
        "cobertura_%": round(100 * st["plus_vocalizados"] / max(st["plus_total"], 1), 1),
        "fuentes": dict(st["fuentes"]),
    }

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    with open(OUT_STATS, "w", encoding="utf-8") as f:
        json.dump({**out["stats_paso2"],
                   "sin_vocalizar_detalle": st["sin_vocalizar_detalle"]},
                  f, ensure_ascii=False, indent=1)

    print("PASO 2 completado.")
    print(f"  Pluses: {st['plus_total']} | vocalizados: {st['plus_vocalizados']}"
          f" ({out['stats_paso2']['cobertura_%']}%)")
    print(f"  Fuentes de vocalizacion: {dict(st['fuentes'])}")
    if st["sin_vocalizar_detalle"]:
        print(f"  Sin vocalizar ({len(st['sin_vocalizar_detalle'])}):")
        for d in st["sin_vocalizar_detalle"][:15]:
            print(f"     Gn {d['ref']}  {d['sp_cons']}  ({d['gloss']})")
    g48 = out["chapters"]["4"]["8"]
    print("\n  Muestra Gn 4:8 reading:")
    print("   ", g48["reading"])
    print(f"  JSON : {OUT_JSON}")
    print("DONE")


if __name__ == "__main__":
    main()
