# -*- coding: utf-8 -*-
"""
PASO 4 + PASO 5 (GENESIS).

PASO 4: marca los PLUS (adiciones samaritanas) con ADD+ (flag add=true). Las
        'moved' (transposiciones) NO se marcan: no son adiciones.
PASO 5: las OMISIONES (type 'omit' = palabras del MT que el SP no tiene) se
        OCULTAN del texto visible (ya excluidas del reading) y se REGISTRAN en
        un compendio aparte (historial exacto por verso). Las 'moved_omit' no
        se registran (solo se reubicaron, no se omiten).

Entradas:  mapeo_genesis/genesis_texto_samaritano.json
Salidas:   mapeo_genesis/genesis_samaritano_final.json
           mapeo_genesis/genesis_omisiones.json
           mapeo_genesis/genesis_omisiones.txt
           mapeo_genesis/preview_genesis_addplus.html  (vista visual)
"""
import json, os, html

SRC = os.path.join("mapeo_genesis", "genesis_texto_samaritano.json")
FINAL = os.path.join("mapeo_genesis", "genesis_samaritano_final.json")
OMIT_JSON = os.path.join("mapeo_genesis", "genesis_omisiones.json")
OMIT_TXT = os.path.join("mapeo_genesis", "genesis_omisiones.txt")
PREVIEW = os.path.join("mapeo_genesis", "preview_genesis_addplus.html")


def strip_niqqud(s):
    return "".join(c for c in (s or "") if not (0x0591 <= ord(c) <= 0x05C7))


def main():
    data = json.load(open(SRC, encoding="utf-8"))
    final = {"book": "Genesis",
             "descripcion": "Texto samaritano de Genesis (Pasos 1-5): pluses ADD+ inyectados/vocalizados, "
                            "transposiciones reubicadas, omisiones ocultas y registradas aparte.",
             "leyenda": {"common": "igual MT/SP", "variant": "variante grafica/lexica",
                         "plus": "adicion samaritana (ADD+)", "moved": "reubicada (transposicion)"},
             "chapters": {}}
    omis = {}
    n_add = n_omit = n_verses_omit = 0

    for ch in sorted(data["chapters"], key=int):
        final["chapters"][ch] = {}
        for vs in sorted(data["chapters"][ch], key=int):
            words = data["chapters"][ch][vs]["words"]
            out_words = []
            for w in words:
                t = w["type"]
                if t == "moved_omit":
                    continue  # reubicada: ni visible ni registrada
                if t == "omit":
                    continue  # se maneja como omision (no va en el texto visible)
                wo = {"text": w["text"], "type": t}
                if t == "plus":
                    wo["add"] = True          # PASO 4: marca ADD+
                    n_add += 1
                out_words.append(wo)

            # PASO 5: compendio de omisiones del verso
            vs_omit = [{"i": w_i, "mt": w["mt"], "mt_cons": strip_niqqud(w["mt"]),
                        "gloss": w.get("gloss", "")}
                       for w_i, w in enumerate(words) if w["type"] == "omit"]
            if vs_omit:
                omis.setdefault(ch, {})[vs] = vs_omit
                n_omit += len(vs_omit)
                n_verses_omit += 1

            final["chapters"][ch][vs] = {
                "reading": " ".join(x["text"] for x in out_words if x["text"]),
                "words": out_words,
                "tiene_add": any(x.get("add") for x in out_words),
                "tiene_omision": bool(vs_omit),
            }

    final["stats"] = {"add_plus": n_add, "omisiones": n_omit,
                      "versos_con_omision": n_verses_omit}

    json.dump(final, open(FINAL, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(omis, open(OMIT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    with open(OMIT_TXT, "w", encoding="utf-8") as f:
        f.write("COMPENDIO DE OMISIONES - SP omite respecto al MT (GENESIS)\n")
        f.write("=" * 58 + "\n")
        f.write(f"Total omisiones: {n_omit} en {n_verses_omit} versiculos\n")
        f.write("=" * 58 + "\n\n")
        for ch in sorted(omis, key=int):
            for vs in sorted(omis[ch], key=int):
                pal = "  ".join(f"{o['mt_cons']} ({o['gloss']})" for o in omis[ch][vs])
                f.write(f"Gn {ch}:{vs}  OMITE:  {pal}\n")

    # ---- vista previa HTML (verbos representativos) ----
    demo = [("1", "1"), ("2", "4"), ("4", "8"), ("7", "1"), ("11", "13"), ("30", "36")]
    css = """
    body{font-family:'Segoe UI',sans-serif;background:#faf8f4;color:#222;margin:24px;}
    h1{color:#2c5}.verse{margin:18px 0;padding:12px 16px;background:#fff;border-radius:8px;
       box-shadow:0 1px 4px rgba(0,0,0,.08);}
    .ref{font-weight:700;color:#87651e;margin-bottom:6px;}
    .heb{direction:rtl;font-size:30px;line-height:2.4;font-family:'Times New Roman',serif;}
    .w{display:inline-flex;flex-direction:column;align-items:center;margin:0 4px;vertical-align:bottom;}
    .w .lab{font-size:10px;color:#fff;background:#d9534f;border-radius:4px;padding:0 4px;
            line-height:1.4;margin-bottom:2px;font-family:sans-serif;direction:ltr;}
    .w.moved .lab{background:#5bc0de;}
    .w.variant span{color:#1a5fb4;}
    .omit{direction:rtl;margin-top:8px;font-size:13px;color:#a33;background:#fdf0f0;
          padding:4px 8px;border-radius:6px;}
    """
    def render_verse(ch, vs):
        v = final["chapters"][ch][vs]
        parts = []
        for w in v["words"]:
            cls = "w"
            lab = ""
            if w.get("add"):
                cls += " plus"; lab = "<span class='lab'>ADD+</span>"
            elif w["type"] == "moved":
                cls += " moved"; lab = "<span class='lab'>\u21c4</span>"
            elif w["type"] == "variant":
                cls += " variant"
            parts.append(f"<span class='{cls}'>{lab}<span>{html.escape(w['text'])}</span></span>")
        omit_html = ""
        if ch in omis and vs in omis[ch]:
            pal = "  ".join(html.escape(f"{o['mt_cons']}") for o in omis[ch][vs])
            omit_html = f"<div class='omit'>Omitido por SP: {pal}</div>"
        return (f"<div class='verse'><div class='ref'>Genesis {ch}:{vs}</div>"
                f"<div class='heb'>{''.join(parts)}</div>{omit_html}</div>")

    body = "".join(render_verse(c, v) for c, v in demo)
    htmlpage = (f"<!doctype html><html lang='es'><head><meta charset='utf-8'>"
                f"<title>Genesis Samaritano - ADD+ / Omisiones</title><style>{css}</style></head>"
                f"<body><h1>Genesis Samaritano \u2014 vista previa</h1>"
                f"<p>Rojo <b>ADD+</b>=adicion samaritana &middot; azul \u21c4=reubicada &middot; "
                f"azul texto=variante &middot; caja roja=omitido (oculto del texto, registrado aparte).</p>"
                f"{body}</body></html>")
    open(PREVIEW, "w", encoding="utf-8").write(htmlpage)

    print("PASO 4+5 completado.")
    print(f"  ADD+ (pluses marcados): {n_add}")
    print(f"  Omisiones registradas:  {n_omit} en {n_verses_omit} versiculos")
    print(f"  Final   : {FINAL}")
    print(f"  Omisiones: {OMIT_JSON} / {OMIT_TXT}")
    print(f"  Preview : {PREVIEW}")
    print("DONE")


if __name__ == "__main__":
    main()
