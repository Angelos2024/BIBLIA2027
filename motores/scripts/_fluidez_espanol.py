"""_fluidez_espanol.py — Completa el ESPAÑOL funcional VACÍO del interlineal.

Rellena SOLO glosas vacías de palabras funcionales (no toca nada ya escrito):
  - Artículo definido (prefijo ART.HEB, forma הַ/הָ/הֶ): el/la/los/las.
    El הֲ interrogativo (hataf-patah) se respeta.
  - Conjunción ו vacía -> "y" (eufonía y->e ante i-/hi-).
  - Preposiciones vacías -> canónico: ב->en, ל->a, מ->de, כ->como.
  - Sufijos posesivos vacíos (prs_suffix, SOLO host nominal): mi/mis, tu/tus,
    su/sus, nuestro/a/os/as. (P2 plural "vuestro/su" es ambiguo: se omite y se
    reporta.) Los sufijos sobre verbos (pronombre objeto) NO se tocan.

GÉNERO y NÚMERO se infieren del SUSTANTIVO ESPAÑOL (no del hebreo, porque
"tierra/tinieblas/cielos/vida/agua" no concuerdan con el género/número hebreo):
  - Género: del corpus (artículos/posesivos ya curados) y, si no hay dato, por
    terminación. Casos "el agua" (femenino con a-/ha- tónica) contemplados.
  - Número: del propio sustantivo español (p. ej. "cielos" -> plural); el hebreo
    solo como respaldo si el español es ambiguo.

NUNCA modifica glosas ya escritas, ni hebreo/he_morph/griego/LXX/lema 'es'. Salta
posiciones editadas por el usuario (glosas_personales.json). Escritura atómica +
respaldo. Genera dos reportes: cambios y "revisar" (posibles desacuerdos en
glosas existentes, para revisión MANUAL; no se cambian).

Uso:
  python scripts/_fluidez_espanol.py --book <slug> [--part 1|2] [--apply]
  (sin --apply = dry-run: solo escribe los reportes)
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from glosas_personales_utils import atomic_write_json, load_registry  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
BACKUP_DIR = DATA / "_fluidez_backup"

HATAF_PATAH = "\u05B2"  # ה interrogativo
PREP_DEFAULT = {"PREP.B": "en", "PREP.L": "a", "PREP.M": "de", "PREP.K": "como"}
MASC_TOKENS = {"el", "los", "nuestro", "nuestros", "vuestro", "vuestros", "del", "al"}
FEM_TOKENS = {"la", "las", "nuestra", "nuestras", "vuestra", "vuestras"}
SG_ART = {"el", "la", "del", "al"}
PL_ART = {"los", "las"}

A_STRESSED = {
    "agua", "aguila", "águila", "alma", "area", "área", "hambre", "arpa",
    "hacha", "ala", "asta", "aula", "haba", "hada", "ave", "arma", "ancla",
    "aria", "ascua", "asma", "acta", "aya", "habla", "alba", "aula",
}
_FEM_END = ("ción", "sión", "dad", "tad", "tud", "umbre", "eza", "ez", "triz",
            "itis", "sis", "ncia", "ud")
_MASC_A_EXC = {"dia", "día", "mapa", "planeta", "clima", "idioma", "problema",
               "tema", "sistema", "poema", "programa", "profeta", "patriarca",
               "dilema", "drama", "enigma", "mesias", "mesías"}
# Sustantivos singulares que terminan en 's' (no son plural).
SING_S = {"dios", "elohim", "'elohim", "moises", "moisés", "jesus", "jesús",
          "mes", "pais", "país", "lunes", "martes", "miercoles", "miércoles",
          "jueves", "viernes", "crisis", "analisis", "análisis", "oasis",
          "virus", "atlas", "torax", "tórax", "caos", "tos", "res", "mies",
          "interes", "interés", "cipres", "ciprés", "exodo", "génesis", "genesis"}


def number_from_morph(he_morph: str) -> str:
    toks = (he_morph or "").split(".")
    if "PL" in toks or "DU" in toks or "P" in toks:
        return "PL"
    return "SG"


def is_nominal(he_morph: str) -> bool:
    return (he_morph or "").split(".")[0] in ("SUBS", "ADJ", "GENT")


def es_head_noun(es: str) -> str:
    t = re.sub(r"[^\wáéíóúüñ' ]", "", (es or "").lower(), flags=re.UNICODE).strip()
    parts = t.split()
    return parts[-1] if parts else ""


def gender_from_token(tok: str) -> str | None:
    t = (tok or "").strip().lower()
    if t in MASC_TOKENS:
        return "M"
    if t in FEM_TOKENS:
        return "F"
    return None


def number_from_article(tok: str) -> str | None:
    t = (tok or "").strip().lower()
    if t in SG_ART:
        return "SG"
    if t in PL_ART:
        return "PL"
    return None


def heuristic_gender(noun: str) -> str:
    n = noun.lower()
    if n in _MASC_A_EXC:
        return "M"
    if n.endswith(_FEM_END):
        return "F"
    if n.endswith("a") or n.endswith("as"):
        return "F"
    return "M"


def spanish_number(noun: str, he_morph: str) -> str:
    n = noun.lower()
    if not n:
        return number_from_morph(he_morph)
    if n in SING_S:
        return "SG"
    if n.endswith("s"):
        return "PL"
    return "SG"


def build_es_gender() -> dict[str, Counter]:
    votes: dict[str, Counter] = defaultdict(Counter)
    for path in sorted(DATA.glob("*_final.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for v in data.get("verses", []):
            for pair in v.get("pairs", []):
                if pair.get("kind") in ("gk_add", "heb_omit"):
                    continue
                for hw in pair.get("he_words", []):
                    head = es_head_noun(hw.get("es", ""))
                    if not head:
                        continue
                    for tok in (hw.get("prefix_es") or []):
                        g = gender_from_token(tok)
                        if g:
                            votes[head][g] += 1
                    ps = hw.get("prs_suffix")
                    if ps:
                        g = gender_from_token(ps.get("es", ""))
                        if g:
                            votes[head][g] += 1
    return votes


def spanish_gender(noun: str, votes: dict[str, Counter]) -> tuple[str, str]:
    c = votes.get(noun)
    if c:
        return c.most_common(1)[0][0], "corpus"
    return heuristic_gender(noun), "heuristica"


def article_token(g: str, n: str, noun: str) -> str:
    if n == "PL":
        return "las" if g == "F" else "los"
    if g == "F":
        return "el" if noun in A_STRESSED else "la"
    return "el"


def euphonic_y(next_es: str) -> str:
    t = (next_es or "").strip().lower()
    if (t.startswith("i") or t.startswith("hi")) and not t.startswith("hie"):
        return "e"
    return "y"


def possessive_token(person, suf_num, g, n) -> str | None:
    if person == "P1" and suf_num == "SG":
        return "mis" if n == "PL" else "mi"
    if person == "P2" and suf_num == "SG":
        return "tus" if n == "PL" else "tu"
    if person == "P3":
        return "sus" if n == "PL" else "su"
    if person == "P1" and suf_num == "PL":
        base = "nuestra" if g == "F" else "nuestro"
        return base + ("s" if n == "PL" else "")
    # P2.PL (vuestro/su) ambiguo -> se omite
    return None


def parse_suffix_person(suf_morph: str) -> tuple[str | None, str | None]:
    toks = (suf_morph or "").split(".")
    person = None
    for t in toks:
        if t in ("P1", "P2", "P3"):
            person = t
    if "PL" in toks:
        sn = "PL"
    elif "SG" in toks:
        sn = "SG"
    else:
        sn = None
    return person, sn


def build_skip_sets(book: str):
    reg = load_registry()
    prefix_edits = set()
    combined_pos = set()
    es_edits = set()  # ediciones manuales del campo 'es' principal
    for r in reg.get("contexto", []):
        m = r.get("match") or {}
        if m.get("book") != book:
            continue
        base = (m.get("chapter"), m.get("verse"), m.get("pairIdx"), m.get("hwIdx"))
        if m.get("field") == "prefix_es":
            prefix_edits.add(base + (m.get("prefixIdx"),))
        if m.get("combined"):
            combined_pos.add(base)
        if m.get("role") == "stem" or (not m.get("field") and not m.get("combined")):
            es_edits.add(base)
    return prefix_edits, combined_pos, es_edits


def process_book(slug: str, part: int | None, apply: bool, no_backup: bool = False):
    path = DATA / f"{slug}_final.json"
    if not path.exists():
        raise SystemExit(f"No existe {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    verses = data.get("verses", [])

    label = slug
    if part:
        max_ch = max((v.get("chapter", 0) for v in verses), default=0)
        half = math.ceil(max_ch / 2)
        if part == 1:
            verses_sel = [v for v in verses if v.get("chapter", 0) <= half]
        else:
            verses_sel = [v for v in verses if v.get("chapter", 0) > half]
        label = f"{slug}_p{part}"
    else:
        verses_sel = verses

    votes = build_es_gender()
    prefix_edits, combined_pos, es_edits = build_skip_sets(slug)
    changes = []
    review = []
    counts = Counter()
    omit_verb_suffix = 0
    omit_p2pl = 0

    def flag_gender(head, tok_gender):
        c = votes.get(head)
        if not c:
            return None
        maj, n_maj = c.most_common(1)[0]
        if maj != tok_gender and n_maj >= 3:
            return maj
        return None

    for v in verses_sel:
        ch, vs = v.get("chapter"), v.get("verse")
        for pi, pair in enumerate(v.get("pairs", [])):
            if pair.get("kind") in ("gk_add", "heb_omit"):
                continue
            for hi, hw in enumerate(pair.get("he_words", [])):
                head = es_head_noun(hw.get("es", ""))
                snum = spanish_number(head, hw.get("he_morph", ""))
                labels = hw.get("prefix_labels") or []
                morphs = hw.get("prefix_morphs") or []
                forms = hw.get("prefix_forms") or []
                es = hw.get("prefix_es")
                if es is None:
                    es = []
                    hw["prefix_es"] = es
                while len(es) < len(hw.get("prefixes") or []):
                    es.append("")

                for i in range(len(hw.get("prefixes") or [])):
                    if (ch, vs, pi, hi, i) in prefix_edits:
                        continue
                    lab = (labels[i] if i < len(labels) else "") or (morphs[i] if i < len(morphs) else "")
                    form = forms[i] if i < len(forms) else ""
                    cur = (es[i] if i < len(es) else "") or ""

                    if lab == "ART.HEB" and HATAF_PATAH not in form:
                        if cur == "":
                            g, gsrc = spanish_gender(head, votes)
                            new = article_token(g, snum, head)
                            es[i] = new
                            changes.append((f"{ch}:{vs}", pi, hi, "articulo", form, "", new, gsrc))
                            counts["articulo"] += 1
                        else:
                            tg = gender_from_token(cur)
                            tn = number_from_article(cur)
                            why = []
                            if tg:
                                fg = flag_gender(head, tg)
                                if fg:
                                    why.append(f"genero?{tg}->{fg}")
                            if tn and tn != snum:
                                why.append(f"numero?{tn}->es:{snum}")
                            if why:
                                review.append((f"{ch}:{vs}", pi, hi, "articulo", form,
                                               hw.get("es"), cur, ";".join(why)))
                    elif lab == "CONJ.VAV" and cur == "":
                        nxt = ""
                        for j in range(i + 1, len(es)):
                            if (es[j] or "").strip():
                                nxt = es[j]
                                break
                        if not nxt:
                            nxt = hw.get("es") or ""
                        es[i] = euphonic_y(nxt)
                        changes.append((f"{ch}:{vs}", pi, hi, "conjuncion", form, "", es[i], ""))
                        counts["conjuncion"] += 1
                    elif lab in PREP_DEFAULT and cur == "":
                        es[i] = PREP_DEFAULT[lab]
                        changes.append((f"{ch}:{vs}", pi, hi, "preposicion", form, "", es[i], ""))
                        counts["preposicion"] += 1

                # ── Partícula DOM אֵת (PART.OBJ.DIR) → siempre vacío ──────────
                # Solo cuando es la partícula pura (sin sufijo pronominal).
                # Si tiene prs_suffix, es la forma pronominal אֹתִי/אֹתוֹ… cuya
                # traducción (me/lo/te…) se almacena en hw['es'] y debe conservarse.
                if hw.get("he_morph") == "PART.OBJ.DIR":
                    cur_es = (hw.get("es") or "").strip()
                    has_pron_suffix = bool(hw.get("prs_suffix"))
                    if cur_es and not has_pron_suffix and (ch, vs, pi, hi) not in es_edits:
                        hw["es"] = ""
                        changes.append((f"{ch}:{vs}", pi, hi, "dom_clear",
                                        hw.get("he_form", ""), cur_es, "", ""))
                        counts["dom_clear"] += 1

                ps = hw.get("prs_suffix")
                if ps and (ch, vs, pi, hi) not in combined_pos:
                    sm = ps.get("he_morph", "")
                    cur = (ps.get("es") or "")
                    if sm.startswith("PRS") and is_nominal(hw.get("he_morph", "")):
                        person, sn = parse_suffix_person(sm)
                        if cur == "":
                            if person == "P2" and sn == "PL":
                                omit_p2pl += 1
                            else:
                                g, gsrc = spanish_gender(head, votes)
                                cand = possessive_token(person, sn, g, snum)
                                if cand:
                                    ps["es"] = cand
                                    changes.append((f"{ch}:{vs}", pi, hi, "posesivo",
                                                    ps.get("he_form", ""), "", cand, gsrc))
                                    counts["posesivo"] += 1
                        else:
                            tg = gender_from_token(cur)
                            why = []
                            if tg:
                                fg = flag_gender(head, tg)
                                if fg:
                                    why.append(f"genero?{tg}->{fg}")
                            if why:
                                review.append((f"{ch}:{vs}", pi, hi, "posesivo",
                                               ps.get("he_form", ""), hw.get("es"), cur, ";".join(why)))
                    elif sm.startswith("PRS"):
                        omit_verb_suffix += 1

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    report = DATA / f"_fluidez_report_{label}.csv"
    with open(report, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ref", "pairIdx", "hwIdx", "tipo", "hebreo", "antes", "despues", "fuente_genero"])
        for row in changes:
            w.writerow(row)
    rev_path = DATA / f"_fluidez_revisar_{label}.csv"
    with open(rev_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ref", "pairIdx", "hwIdx", "tipo", "hebreo", "es_nucleo", "valor_actual", "motivo"])
        for row in review:
            w.writerow(row)

    print(f"== Fluidez ES: {label} ==")
    print(f"  RELLENOS (vacios completados): {len(changes)}")
    for k in sorted(counts):
        print(f"    {k:12s}: {counts[k]}")
    print(f"  omitidos: sufijo en verbo={omit_verb_suffix}  posesivo P2pl(vuestro/su ambiguo)={omit_p2pl}")
    print(f"  REVISAR (posibles desacuerdos en glosas existentes, NO modificadas): {len(review)}")
    print(f"  reporte cambios : {report}")
    print(f"  reporte revisar : {rev_path}")

    if apply:
        if not no_backup:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            bak = BACKUP_DIR / f"{label}_{ts}.json"
            bak.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            print(f"  respaldo: {bak}")
        atomic_write_json(path, data, separators=(",", ":"))
        print("  APLICADO.")
    else:
        print("  DRY-RUN (no se escribió el _final.json). Usa --apply para aplicar.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--part", type=int, choices=[1, 2], default=None)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--no-backup", action="store_true",
                    help="No crear respaldo (uso en pipeline run_motors)")
    args = ap.parse_args()
    process_book(args.book, args.part, args.apply, args.no_backup)


if __name__ == "__main__":
    main()
