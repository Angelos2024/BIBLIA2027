# -*- coding: utf-8 -*-
"""Rellena las glosas vacias de las OMISIONES (mt_only) en
mapeo_genesis/genesis_texto_samaritano.json, usando un lexico
consonantes->glosa construido desde las palabras que si tienen glosa
en los 5 libros. Luego hay que re-ejecutar paso4y5 para regenerar el compendio."""
import json, os, collections

BOOKS = ["genesis", "exodus", "leviticus", "numbers", "deuteronomy"]
TXT = os.path.join("mapeo_genesis", "genesis_texto_samaritano.json")
FINALS = {"\u05DA": "\u05DB", "\u05DD": "\u05DE", "\u05DF": "\u05E0",
          "\u05E3": "\u05E4", "\u05E5": "\u05E6"}


# glosas manuales para formas raras/hapax que no recurren en el corpus
MANUAL = {
    "\u05E6\u05D1\u05D9\u05DD": "Zeboiim",        # צבים (topon.)
    "\u05DC\u05E9\u05E2": "Lasha",                 # לשע (topon.)
    "\u05EA\u05E8\u05D9\u05D3": "you grow restless",  # תריד
    "\u05D0\u05DE\u05D4\u05EA": "maidservants",    # אמהת
    "\u05EA\u05D1\u05E7\u05E9\u05E0\u05D4": "you required it",  # תבקשנה
    "\u05D4\u05D5\u05E8\u05D3\u05E0\u05D5": "we brought it down",  # הורדנו
    "\u05EA\u05D7\u05D3": "be united",             # תחד
}


def cons(s):
    return "".join(c for c in (s or "") if 0x05D0 <= ord(c) <= 0x05EA)


def normkey(s):
    return "".join(FINALS.get(c, c) for c in cons(s))


def build_gloss_lex():
    lex = collections.defaultdict(collections.Counter)
    for b in BOOKS:
        p = f"{b}_lectura_samaritana.json"
        if not os.path.exists(p):
            continue
        d = json.load(open(p, encoding="utf-8"))
        for ch in d.get("chapters", {}).values():
            for vs in ch.values():
                for w in vs.get("words", []):
                    g = (w.get("gloss") or "").strip()
                    if not g:
                        continue
                    for src in (w.get("sp_cons"), w.get("mt")):
                        k = normkey(src)
                        if k:
                            lex[k][g] += 1
    return lex


def main():
    global MANUAL
    MANUAL = {normkey(k): v for k, v in MANUAL.items()}
    lex = build_gloss_lex()
    print(f"Lexico de glosas: {len(lex)} formas")
    data = json.load(open(TXT, encoding="utf-8"))

    filled = miss = 0
    still = []
    for ch in data["chapters"]:
        for vs in data["chapters"][ch]:
            for w in data["chapters"][ch][vs]["words"]:
                if w["type"] in ("omit", "moved_omit") and not (w.get("gloss") or "").strip():
                    k = normkey(w.get("mt"))
                    if MANUAL.get(k):
                        w["gloss"] = MANUAL[k]
                        filled += 1
                    elif lex.get(k):
                        w["gloss"] = lex[k].most_common(1)[0][0]
                        filled += 1
                    else:
                        miss += 1
                        still.append((ch, vs, cons(w.get("mt"))))

    json.dump(data, open(TXT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Glosas rellenadas: {filled} | sin resolver: {miss}")
    with open(os.path.join("mapeo_genesis", "_glosas_sin_resolver.txt"), "w", encoding="utf-8") as f:
        for ch, vs, cn in still:
            f.write(f"{ch}:{vs} -> {''.join(cn)}\n")
    print("DONE (re-ejecuta paso4y5 para regenerar el compendio)")


if __name__ == "__main__":
    main()
