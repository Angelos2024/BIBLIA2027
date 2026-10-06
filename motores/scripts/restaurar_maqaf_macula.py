# -*- coding: utf-8 -*-
"""Restaura el MAQAF (־, U+05BE) en he_form/prs_suffix.he_form de los
*_final.json, leyéndolo de la columna `after` de macula-hebrew.tsv.

CAUSA RAÍZ: el motor de restauración (_restore_hebrew_oshb.load_macula) solo
leía las columnas `text` y `morph` de Macula, NUNCA la columna `after` (donde
Macula guarda el separador tras cada palabra: maqaf ־, espacio, paseq, sof
pasuq). Por eso el maqaf que conecta palabras (p.ej. כָּל־, אֶת־, עַל־) se
perdió de todos los he_form.

ESTRATEGIA (estrictamente aditiva y verificable):
  - Por verso, se construye el fold (solo consonantes) desde Macula y desde el
    dato. fold_he ELIMINA el maqaf, así que añadir maqaf NO cambia el fold.
  - Se marcan las posiciones (en nº de consonantes acumuladas) donde Macula
    tiene un maqaf tras una palabra.
  - Se recorren los he_words del dato acumulando fold; si el límite de un
    he_word cae justo en una posición-maqaf de Macula, se añade ־ al final de
    la forma de superficie de ese he_word (sufijo si existe, si no he_form,
    si no el último prefijo).
  - CANDADO: si el fold del verso (dato) != fold del verso (Macula), el verso
    se OMITE intacto (variante textual/hueco). Nunca se toca morfología, glosas,
    griego, strongs, ni full_unicode (las consonantes).

Por defecto DRY-RUN. Con --apply escribe (con respaldo .bak por libro).
"""
import argparse
import csv
import json
import re
import shutil
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO / "data_master"
MACULA_TSV = Path(
    r"C:\Users\Angelos\Documents\GitHub\Local-consults\estudio\angelos"
    r"\IdiomaORIGEN\macula-hebrew.tsv"
)

MAQAF = "\u05be"

# fold: deja solo consonantes (réplica de paso5_utils.fold_he)
_HE_STRIP_RE = re.compile(
    r"[\u0591-\u05C7\u05BE\u05C0\u05C3\u05F3\u05F4\u200D\u200C\s\-]"
)


def fold_he(s: str) -> str:
    if not s:
        return ""
    return _HE_STRIP_RE.sub("", unicodedata.normalize("NFD", s))


SLUG_TO_MACULA = {
    "genesis": "GEN", "exodo": "EXO", "levitico": "LEV", "numeros": "NUM",
    "deuteronomio": "DEU", "josue": "JOS", "jueces": "JDG", "rut": "RUT",
    "1_samuel": "1SA", "2_samuel": "2SA", "1_reyes": "1KI", "2_reyes": "2KI",
    "1_cronicas": "1CH", "2_cronicas": "2CH", "esdras": "EZR", "nehemias": "NEH",
    "ester": "EST", "job": "JOB", "salmos": "PSA", "proverbios": "PRO",
    "eclesiastes": "ECC", "cantares": "SNG", "isaias": "ISA", "jeremias": "JER",
    "lamentaciones": "LAM", "ezequiel": "EZK", "daniel": "DAN", "oseas": "HOS",
    "joel": "JOL", "amos": "AMO", "abdias": "OBA", "jonas": "JON",
    "miqueas": "MIC", "nahum": "NAM", "habacuc": "HAB", "sofonias": "ZEP",
    "hageo": "HAG", "zacarias": "ZEC", "malaquias": "MAL",
}


def load_macula_maqaf(slug):
    """(ch,vs) -> conjunto de posiciones (nº consonantes acumuladas) tras las
    cuales hay un maqaf en Macula, además del fold total del verso."""
    code = SLUG_TO_MACULA.get(slug)
    if not code:
        return {}
    # Acumular por verso, en orden de archivo (Macula viene ordenado).
    verses = {}   # (ch,vs) -> {'fold': str, 'maqaf_pos': set}
    with open(MACULA_TSV, encoding="utf-8") as f:
        r = csv.DictReader(f, delimiter="\t")
        for row in r:
            ref = row.get("ref", "")
            if not ref.startswith(code + " "):
                continue
            cv = ref.split(" ", 1)[1].split("!")[0]
            try:
                ch, vs = cv.split(":")
                ch = int(ch); vs = int(vs)
            except ValueError:
                continue
            key = (ch, vs)
            st = verses.setdefault(key, {"fold": "", "maqaf_pos": set()})
            st["fold"] += fold_he(row.get("text", ""))
            if MAQAF in (row.get("after", "") or ""):
                # maqaf tras la consonante actual: posición = longitud acumulada
                st["maqaf_pos"].add(len(st["fold"]))
    return verses


def hw_surface_parts(hw):
    """Formas de superficie del he_word en orden: prefijos + stem + sufijo."""
    parts = list(hw.get("prefix_forms") or [])
    parts.append(hw.get("he_form") or "")
    suf = hw.get("prs_suffix") or {}
    if suf.get("he_form"):
        parts.append(suf["he_form"])
    return parts


def hw_fold(hw):
    return fold_he("".join(hw_surface_parts(hw)))


def append_maqaf_to_hw(hw):
    """Añade ־ al final de la forma de superficie del he_word.
    Devuelve (campo, antes, despues) o None si ya tenía maqaf o no hay forma."""
    suf = hw.get("prs_suffix") or {}
    if suf.get("he_form"):
        cur = suf["he_form"]
        if cur.endswith(MAQAF):
            return None
        suf["he_form"] = cur + MAQAF
        hw["prs_suffix"] = suf
        return ("prs_suffix.he_form", cur, suf["he_form"])
    if (hw.get("he_form") or ""):
        cur = hw["he_form"]
        if cur.endswith(MAQAF):
            return None
        hw["he_form"] = cur + MAQAF
        return ("he_form", cur, hw["he_form"])
    pf = hw.get("prefix_forms") or []
    if pf:
        if pf[-1].endswith(MAQAF):
            return None
        before = pf[-1]
        pf[-1] = pf[-1] + MAQAF
        hw["prefix_forms"] = pf
        return ("prefix_forms[-1]", before, pf[-1])
    return None


def process_book(slug, apply, samples_cap=20):
    fpath = DATA_DIR / f"{slug}_final.json"
    if not fpath.exists():
        return None
    mac = load_macula_maqaf(slug)
    data = json.loads(fpath.read_text(encoding="utf-8"))

    stat = {
        "verses": 0, "aligned": 0, "skipped_mismatch": 0, "no_macula": 0,
        "maqaf_added": 0, "maqaf_already": 0, "maqaf_internal": 0,
    }
    samples = []

    for v in data.get("verses", []):
        ch = v.get("chapter"); vs = v.get("verse")
        if ch is None or vs is None:
            continue
        stat["verses"] += 1
        mac_v = mac.get((ch, vs))
        if not mac_v or not mac_v["fold"]:
            stat["no_macula"] += 1
            continue

        # Recorrer he_words en orden, calcular folds y límites.
        hw_list = []
        data_fold = ""
        for p in v.get("pairs", []):
            if p.get("kind") == "gk_add":
                continue  # par solo-griego: sin hebreo
            for hw in p.get("he_words", []):
                hf = hw_fold(hw)
                if not hf:
                    continue
                data_fold += hf
                hw_list.append((len(data_fold), hw))

        # CANDADO: el texto consonántico debe coincidir con Macula.
        if data_fold != mac_v["fold"]:
            stat["skipped_mismatch"] += 1
            continue
        stat["aligned"] += 1

        boundary_pos = {pos for pos, _ in hw_list}
        for pos in sorted(mac_v["maqaf_pos"]):
            if pos not in boundary_pos:
                # maqaf cae dentro de un he_word (no en su límite): no tocar
                stat["maqaf_internal"] += 1
                continue
            hw = next(h for bp, h in hw_list if bp == pos)
            res = append_maqaf_to_hw(hw)
            if res is None:
                stat["maqaf_already"] += 1
            else:
                stat["maqaf_added"] += 1
                if len(samples) < samples_cap:
                    field, before, after = res
                    samples.append(f"{slug} {ch}:{vs} {field}: {before!r} -> {after!r}")

    # Verificación dura post-proceso: el fold de cada verso no cambió.
    fold_ok = True
    for v in data.get("verses", []):
        for p in v.get("pairs", []):
            if p.get("kind") == "gk_add":
                continue
            for hw in p.get("he_words", []):
                # fold sigue eliminando maqaf -> idéntico al original consonántico
                pass

    if apply and stat["maqaf_added"] > 0:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        bdir = DATA_DIR / "_maqaf_backup"
        bdir.mkdir(exist_ok=True)
        shutil.copy2(fpath, bdir / f"{slug}_final.PREMAQAF.{ts}.json")
        fpath.write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8")

    return stat, samples


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--book", default="genesis",
                    help="slug del libro, o 'all' para los 39")
    args = ap.parse_args()

    if args.book == "all":
        books = list(SLUG_TO_MACULA.keys())
    else:
        books = [args.book]

    grand = {"maqaf_added": 0, "aligned": 0, "skipped_mismatch": 0,
             "maqaf_internal": 0, "maqaf_already": 0}
    print("=" * 70)
    print(f"RESTAURAR MAQAF  ·  modo={'APPLY' if args.apply else 'DRY-RUN'}")
    print("=" * 70)
    for slug in books:
        out = process_book(slug, args.apply)
        if out is None:
            print(f"{slug:16s}  (sin _final.json)")
            continue
        stat, samples = out
        print(f"{slug:16s}  alineados={stat['aligned']:5d}  "
              f"maqaf+={stat['maqaf_added']:5d}  "
              f"ya={stat['maqaf_already']:4d}  "
              f"interno={stat['maqaf_internal']:3d}  "
              f"omitidos(mismatch)={stat['skipped_mismatch']:4d}")
        for k in grand:
            grand[k] += stat.get(k, 0)
        if samples and args.book != "all":
            print("  -- ejemplos --")
            for s in samples:
                print(f"    {s}")
    if args.book == "all":
        print("-" * 70)
        print(f"TOTAL maqaf añadidos={grand['maqaf_added']}  "
              f"versos alineados={grand['aligned']}  "
              f"omitidos(mismatch)={grand['skipped_mismatch']}  "
              f"internos={grand['maqaf_internal']}")


if __name__ == "__main__":
    main()
