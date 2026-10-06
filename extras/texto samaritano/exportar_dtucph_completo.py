# -*- coding: utf-8 -*-
"""
Exporta el modulo MAS FIEL y COMPLETO del Pentateuco Samaritano:
  DT-UCPH/sp  (editio maior de Stefan Schorch, Text-Fabric v6.1)

A diferencia de extract_samaritan.py (solo consonantico + escritura samaritana),
aqui se exporta TAMBIEN la morfologia de Schorch palabra por palabra:
  - cuadrado (g_cons_utf8)         escritura hebrea cuadrada
  - samaritano                     escritura samaritana original (U+0800)
  - lex / lex_utf8                 lexema
  - gloss                          glosa inglesa
  - sp                             categoria gramatical (part of speech)
  - vt / ps / nu / gn              tiempo verbal / persona / numero / genero

Carga la data OFFLINE desde la cache local (sin tocar la red).
Salidas en data_original/:
  - sp_dtucph_completo.json   estructura libro/capitulo/versiculo con morfologia
  - sp_dtucph.txt             "Ref \t samaritano \t cuadrado" por versiculo
"""
import json, os, sys

LOC = os.path.join(os.environ["USERPROFILE"],
                   "text-fabric-data", "github", "DT-UCPH", "sp", "tf", "6.1")
OUT_DIR = "data_original"
JSON_OUT = os.path.join(OUT_DIR, "sp_dtucph_completo.json")
TXT_OUT = os.path.join(OUT_DIR, "sp_dtucph.txt")

# Reusar el mapeo cuadrado->samaritano ya validado del proyecto
from extract_samaritan import hebrew_to_samaritan

FEATURES = ("g_cons_utf8 lex lex_utf8 gloss sp vt ps nu gn "
            "book chapter verse trailer")


def load_api():
    from tf.fabric import Fabric
    TF = Fabric(locations=LOC, silent="deep")
    api = TF.load(FEATURES, silent="deep")
    if api is False:
        print("ERROR: no se pudo cargar la data de Text-Fabric en", LOC)
        sys.exit(1)
    return api


def fval(F, name, node):
    feat = getattr(F, name, None)
    if feat is None:
        return None
    v = feat.v(node)
    return v if v not in ("", "NA", "absent") else (v or None)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    api = load_api()
    F, L = api.F, api.L

    pent = {}
    n_verses = n_words = 0

    for bk in F.otype.s("book"):
        bname = F.book.v(bk)
        book = {"book": bname, "chapters": {}}
        for ch in L.d(bk, otype="chapter"):
            cnum = str(F.chapter.v(ch))
            chap = {}
            for vs in L.d(ch, otype="verse"):
                vnum = str(F.verse.v(vs))
                words = []
                heb_parts, sam_parts = [], []
                for w in L.d(vs, otype="word"):
                    heb = F.g_cons_utf8.v(w) or ""
                    sam = hebrew_to_samaritan(heb)
                    heb_parts.append(heb)
                    sam_parts.append(sam)
                    words.append({
                        "sam": sam,
                        "heb": heb,
                        "lex": fval(F, "lex_utf8", w),
                        "lex_tr": fval(F, "lex", w),
                        "gloss": fval(F, "gloss", w),
                        "sp": fval(F, "sp", w),
                        "vt": fval(F, "vt", w),
                        "ps": fval(F, "ps", w),
                        "nu": fval(F, "nu", w),
                        "gn": fval(F, "gn", w),
                    })
                    n_words += 1
                chap[vnum] = {
                    "samaritan": " ".join(sam_parts),
                    "hebrew": " ".join(heb_parts),
                    "words": words,
                }
                n_verses += 1
            book["chapters"][cnum] = chap
        pent[bname] = book
        print(f"  {bname}: {len(book['chapters'])} capitulos")

    with open(JSON_OUT, "w", encoding="utf-8") as f:
        json.dump(pent, f, ensure_ascii=False, indent=1)

    with open(TXT_OUT, "w", encoding="utf-8") as f:
        for bname, book in pent.items():
            for cnum, chap in book["chapters"].items():
                for vnum, v in chap.items():
                    f.write(f"{bname} {cnum}:{vnum}\t{v['samaritan']}\t{v['hebrew']}\n")

    print(f"\nListo. Libros: {len(pent)} | Versiculos: {n_verses} | Palabras/morfemas: {n_words}")
    print(f"JSON: {JSON_OUT}")
    print(f"TXT : {TXT_OUT}")
    g11 = pent.get("Genesis", {}).get("chapters", {}).get("1", {}).get("1")
    if g11:
        print("\nMuestra Genesis 1:1")
        print("  samaritano:", g11["samaritan"])
        print("  cuadrado  :", g11["hebrew"])
        print("  palabra[1]:", json.dumps(g11["words"][1], ensure_ascii=False))
    print("DONE")


if __name__ == "__main__":
    main()
