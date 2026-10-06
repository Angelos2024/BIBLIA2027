# -*- coding: utf-8 -*-
"""
PASO 3c - Reestructuracion de inyecciones (GENESIS).

1) TRANSPOSICIONES: un 'plus' con gemelo 'omit' de las MISMAS consonantes en el
   verso, donde el plus esta AISLADO (tirada de pluses <= UMBRAL). Se reclasifican:
     plus  -> 'moved'       (visible, SIN ADD+: no es adicion, solo se reubico)
     omit  -> 'moved_omit'  (oculto y NO se registra como omision)
   Las adiciones largas y variantes de numero (Gn 11, 30:36) quedan intactas
   porque su plus esta dentro de una tirada larga.

2) VOCALIZACION de pluses sin niqqud: primero por el gemelo vocalizado del mismo
   verso; si no hay, por el corpus (forma mas frecuente con esas consonantes).

3) Recalcula 'reading' = TEXTO SAMARITANO visible = common + variant + plus + moved
   (excluye omisiones genuinas y moved_omit).

Sobrescribe mapeo_genesis/genesis_texto_samaritano.json y escribe un reporte.
"""
import json, os, collections

BOOKS = ["genesis", "exodus", "leviticus", "numbers", "deuteronomy"]
F = os.path.join("mapeo_genesis", "genesis_texto_samaritano.json")
REPORT = os.path.join("mapeo_genesis", "genesis_paso3_reestructura.txt")
RUN_MAX = 3  # tirada maxima de pluses para considerar 'aislado'

FINALS = {"\u05DA": "\u05DB", "\u05DD": "\u05DE", "\u05DF": "\u05E0",
          "\u05E3": "\u05E4", "\u05E5": "\u05E6"}


def cons_only(s):
    return "".join(c for c in (s or "") if 0x05D0 <= ord(c) <= 0x05EA)


def normkey(s):
    return "".join(FINALS.get(c, c) for c in cons_only(s))


def has_niqqud(s):
    # incluye dagesh 05BC: el shuruq (vav+dagesh) es la unica marca en formas
    # como יוּם / עוּף / קוּם; el consonantico crudo no tiene ninguna marca.
    return any(0x05B0 <= ord(c) <= 0x05BC for c in (s or ""))


def build_corpus_voc():
    m = collections.defaultdict(collections.Counter)
    for b in BOOKS:
        p = f"{b}_lectura_samaritana.json"
        if not os.path.exists(p):
            continue
        d = json.load(open(p, encoding="utf-8"))
        for ch in d.get("chapters", {}).values():
            for vs in ch.values():
                for w in vs.get("words", []):
                    sam = w.get("sam_reading", "")
                    if has_niqqud(sam):
                        m[normkey(sam)][sam] += 1
    return m


def plus_run_len(words, i):
    """Longitud de la tirada contigua de type=='plus' que contiene a i."""
    if words[i]["type"] != "plus":
        return 0
    a = i
    while a - 1 >= 0 and words[a - 1]["type"] == "plus":
        a -= 1
    b = i
    while b + 1 < len(words) and words[b + 1]["type"] == "plus":
        b += 1
    return b - a + 1


def main():
    data = json.load(open(F, encoding="utf-8"))
    corpus = build_corpus_voc()

    rep = {"transposiciones": [], "vocalizados": []}
    n_moved = n_voc = 0

    for ch in sorted(data["chapters"], key=int):
        for vs in sorted(data["chapters"][ch], key=int):
            words = data["chapters"][ch][vs]["words"]

            # --- 1) transposiciones ---
            omit_by_key = collections.defaultdict(list)
            for j, w in enumerate(words):
                if w["type"] == "omit":
                    omit_by_key[normkey(w["mt"])].append(j)
            used = set()
            for i, w in enumerate(words):
                if w["type"] != "plus":
                    continue
                if plus_run_len(words, i) > RUN_MAX:
                    continue
                k = normkey(w["sp_cons"])
                cand = [j for j in omit_by_key.get(k, []) if j not in used]
                if cand:
                    j = cand[0]
                    used.add(j)
                    w["type"] = "moved"
                    words[j]["type"] = "moved_omit"
                    n_moved += 1
                    rep["transposiciones"].append(
                        {"ref": f"Gn {ch}:{vs}", "plus_i": i, "omit_i": j,
                         "cons": w["sp_cons"]})

            # --- 2) vocalizacion de pluses sin niqqud ---
            voc_in_verse = collections.defaultdict(list)
            for w in words:
                if has_niqqud(w.get("text", "")):
                    voc_in_verse[normkey(w["text"])].append(w["text"])
            for w in words:
                if w["type"] in ("plus", "moved") and not has_niqqud(w.get("text", "")):
                    k = normkey(w["sp_cons"])
                    src = None
                    if voc_in_verse.get(k):
                        w["text"] = voc_in_verse[k][0]; src = "gemelo"
                    elif corpus.get(k):
                        w["text"] = corpus[k].most_common(1)[0][0]; src = "corpus"
                    if src:
                        w["voc_src"] = src
                        n_voc += 1
                        rep["vocalizados"].append(
                            {"ref": f"Gn {ch}:{vs}", "cons": w["sp_cons"],
                             "text": w["text"], "src": src})

            # --- 3) recalcular reading visible (texto samaritano) ---
            data["chapters"][ch][vs]["reading"] = " ".join(
                w["text"] for w in words
                if w["type"] in ("common", "variant", "plus", "moved") and w.get("text"))

    # recuento de tipos
    tipos = collections.Counter()
    for ch in data["chapters"].values():
        for vs in ch.values():
            for w in vs["words"]:
                tipos[w["type"]] += 1
    data["stats_paso3"] = {"transposiciones_reclasificadas": n_moved,
                           "pluses_vocalizados_extra": n_voc,
                           "tipos": dict(tipos)}

    json.dump(data, open(F, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("PASO 3c - REESTRUCTURACION (GENESIS)\n" + "=" * 50 + "\n")
        f.write(f"\nTransposiciones reclasificadas a 'moved': {n_moved}\n")
        for d in rep["transposiciones"]:
            f.write("   " + json.dumps(d, ensure_ascii=False) + "\n")
        f.write(f"\nPluses vocalizados (extra): {n_voc}\n")
        for d in rep["vocalizados"]:
            f.write("   " + json.dumps(d, ensure_ascii=False) + "\n")
        f.write(f"\nConteo de tipos: {json.dumps(dict(tipos), ensure_ascii=False)}\n")

    print("PASO 3c completado.")
    print(f"  Transposiciones -> moved: {n_moved}")
    print(f"  Pluses vocalizados extra: {n_voc}")
    print(f"  Tipos: {dict(tipos)}")
    print(f"  Reporte: {REPORT}")
    print("DONE")


if __name__ == "__main__":
    main()
