"""_revisar_espanol.py — Aplica correcciones de género y número a glosas EXISTENTES.

Lee el reporte `data/_fluidez_revisar_<slug>.csv` generado por `_fluidez_espanol.py`
y aplica las correcciones que superen el umbral de confianza:

  - GÉNERO: si el corpus tiene ≥ --min-votes ocurrencias del núcleo español con el
    género contrario al actual, se corrige:
      M -> F : el→la, los→las, del→"de la", al→"a la"
      F -> M : la→el, las→los, "de la"→del, "a la"→al (solo cuando número=SG)
  - NÚMERO: si la terminación del sustantivo español indica claramente número
    distinto al artículo actual:
      "..s" (no excepción) con artículo SG → plural
      sin "..s" (no excepción) con artículo PL → singular
    Se excluyen explícitamente: 'Elohim, nombres propios (capital inicial),
    pluralia tantum conocidos, glosas EN:…, y sustantivos singulares con -s.

Regla de oro: salta posiciones editadas por el usuario (glosas_personales.json).
Escritura atómica + respaldo. Genera reporte de lo aplicado y de lo que queda
pendiente.

Uso:
  python scripts/_revisar_espanol.py --book <slug> [--part 1|2]
                                     [--min-votes 5] [--apply]
  (sin --apply = dry-run)
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import defaultdict, Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from glosas_personales_utils import atomic_write_json, load_registry  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
BACKUP_DIR = DATA / "_fluidez_backup"

# ── Excepciones que NO se corrigen por número ─────────────────────────────────
# Pluralia tantum: palabras que se usan en plural aunque signifiquen algo singular.
PLURALIA_TANTUM = {
    "tinieblas", "aguas", "cielos", "celos", "víveres", "fuerzas", "exequias",
    "nupcias", "parias", "gárgaras", "entrañas", "vísceras", "víveres", "anales",
    "alrededores", "afueras", "inmediaciones",
}
# Singulares que acaban en -s (no son plural).
SING_S = {
    "dios", "elohim", "'elohim", "moisés", "moises", "jesús", "jesus",
    "mes", "país", "pais", "lunes", "martes", "miércoles", "miercoles",
    "jueves", "viernes", "crisis", "análisis", "analisis", "oasis",
    "virus", "atlas", "tórax", "torax", "caos", "tos", "res", "mies",
    "interés", "interes", "ciprés", "cipres", "éxodo", "exodo", "génesis",
    "genesis", "eufrates", "tigris", "calvario", "damasco", "babilonia",
    "egipto", "jordán", "jordan", "sinaí", "sinai", "carmelo",
}
# Núcleos que siempre se omiten (plurales majestáticos / teológicos).
SKIP_NUCLEOS = {"'elohim", "elohim", "yhwh", "adonai", "adonái", "señor"}

# Femeninos con a-/ha- tónica que usan "el" en singular (no cambiar a "la").
A_STRESSED_SG = {
    "agua", "águila", "aguila", "alma", "área", "area", "hambre", "arpa",
    "hacha", "ala", "asta", "aula", "haba", "hada", "ave", "arma", "ancla",
    "alba", "ascua", "asma", "habla",
}
# Estos van con "el" en SG aunque sean femeninos; en PL van con "las".
def correct_article(g: str, n: str, noun: str) -> str:
    if n == "PL":
        return "las" if g == "F" else "los"
    if g == "F" and noun.lower() in A_STRESSED_SG:
        return "el"
    return "la" if g == "F" else "el"

# Tokens de artículo con su género y número.
ART_GN: dict[str, tuple[str, str]] = {
    "el": ("M", "SG"), "la": ("F", "SG"),
    "los": ("M", "PL"), "las": ("F", "PL"),
    "del": ("M", "SG"), "al": ("M", "SG"),
}
ART_M_SG = {"el", "del", "al"}
ART_F_SG = {"la"}
ART_M_PL = {"los"}
ART_F_PL = {"las"}

POSS_GN: dict[str, tuple[str, str]] = {
    "nuestro": ("M", "SG"), "nuestra": ("F", "SG"),
    "nuestros": ("M", "PL"), "nuestras": ("F", "PL"),
    "vuestro": ("M", "SG"), "vuestra": ("F", "SG"),
    "vuestros": ("M", "PL"), "vuestras": ("F", "PL"),
}


def token_to_fem(tok: str) -> str:
    return {"el": "la", "los": "las", "del": "de la", "al": "a la",
            "nuestro": "nuestra", "nuestros": "nuestras",
            "vuestro": "vuestra", "vuestros": "vuestras"}.get(tok, tok)


def token_to_masc(tok: str, num: str) -> str:
    if num == "PL":
        return {"las": "los", "nuestras": "nuestros", "vuestras": "vuestros"}.get(tok, tok)
    return {"la": "el", "de la": "del", "a la": "al",
            "nuestra": "nuestro", "vuestras": "vuestras"}.get(tok, tok)


def token_to_plural(tok: str) -> str:
    return {"el": "los", "la": "las", "del": "los", "al": "los"}.get(tok, tok)


def token_to_singular(tok: str) -> str:
    return {"los": "el", "las": "la"}.get(tok, tok)


def build_es_gender_votes() -> dict[str, Counter]:
    from collections import defaultdict
    votes: dict[str, Counter] = defaultdict(Counter)
    MASC = {"el", "los", "nuestro", "nuestros", "vuestro", "vuestros", "del", "al"}
    FEM = {"la", "las", "nuestra", "nuestras", "vuestra", "vuestras"}
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
                    head = _head(hw.get("es", ""))
                    if not head:
                        continue
                    for tok in (hw.get("prefix_es") or []):
                        t = (tok or "").strip().lower()
                        if t in MASC:
                            votes[head]["M"] += 1
                        elif t in FEM:
                            votes[head]["F"] += 1
                    ps = hw.get("prs_suffix")
                    if ps:
                        t = (ps.get("es") or "").strip().lower()
                        if t in MASC:
                            votes[head]["M"] += 1
                        elif t in FEM:
                            votes[head]["F"] += 1
    return votes


def _head(es: str) -> str:
    t = re.sub(r"[^\wáéíóúüñ' ]", "", (es or "").lower(), flags=re.UNICODE).strip()
    parts = t.split()
    return parts[-1] if parts else ""


def is_proper_noun(nucleus: str) -> bool:
    raw = (nucleus or "").strip()
    if not raw:
        return False
    if raw.startswith("[EN:") or raw.startswith("["):
        return True
    if raw[0].isupper() or raw[0] == "'":
        return True
    return False


def is_verb_gloss(nucleus: str) -> bool:
    verbs = {"fue", "era", "es", "están", "estan", "son", "ser", "estar",
             "hizo", "hace", "dijo", "habló", "hablo", "vino", "vio", "dio",
             "ocupados", "habitaban", "escapado"}
    return (nucleus or "").lower() in verbs


def number_from_spanish(noun: str) -> str | None:
    n = noun.lower()
    if n in SKIP_NUCLEOS or n in PLURALIA_TANTUM:
        return None
    if n in SING_S:
        return "SG"
    if is_proper_noun(noun):
        return None
    if is_verb_gloss(noun):
        return None
    if n.endswith("s") or n.endswith("es"):
        return "PL"
    return "SG"


def build_skip_sets(book: str):
    reg = load_registry()
    prefix_edits: set = set()
    combined_pos: set = set()
    es_edits: set = set()
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


def process_book(slug: str, part: int | None, min_votes: int, apply: bool, no_backup: bool = False):
    path = DATA / f"{slug}_final.json"
    if not path.exists():
        raise SystemExit(f"No existe {path}")

    label = slug if not part else f"{slug}_p{part}"
    revisar_path = DATA / f"_fluidez_revisar_{label}.csv"
    if not revisar_path.exists():
        raise SystemExit(
            f"No existe {revisar_path}\n"
            f"Ejecuta primero: python scripts/_fluidez_espanol.py --book {slug}"
            + (f" --part {part}" if part else "")
        )

    data = json.loads(path.read_text(encoding="utf-8"))
    verses = data.get("verses", [])
    if part:
        max_ch = max((v.get("chapter", 0) for v in verses), default=0)
        half = math.ceil(max_ch / 2)
        cap_rng = range(1, half + 1) if part == 1 else range(half + 1, max_ch + 1)
    else:
        cap_rng = None

    votes = build_es_gender_votes()
    prefix_edits, combined_pos, es_edits = build_skip_sets(slug)

    # Índice directo a he_words para editar en memoria.
    hw_idx: dict[tuple, dict] = {}
    for v in verses:
        ch = v.get("chapter")
        if cap_rng and ch not in cap_rng:
            continue
        for pi, pair in enumerate(v.get("pairs", [])):
            for hi, hw in enumerate(pair.get("he_words", [])):
                hw_idx[(ch, v.get("verse"), pi, hi)] = hw

    # Lee el CSV de revisión.
    revisar_rows = list(csv.DictReader(open(revisar_path, encoding="utf-8-sig")))

    changes: list[tuple] = []
    skipped: list[dict] = []
    counts = Counter()

    for row in revisar_rows:
        try:
            ch, vs = map(int, row["ref"].split(":"))
            pi, hi = int(row["pairIdx"]), int(row["hwIdx"])
        except (ValueError, KeyError):
            continue

        tipo = row.get("tipo", "")
        nucleus = (row.get("es_nucleo") or "").strip()
        cur = (row.get("valor_actual") or "").strip()
        motivos_raw = row.get("motivo", "")
        hw = hw_idx.get((ch, vs, pi, hi))
        if hw is None:
            continue

        # ── Artículo ──────────────────────────────────────────────────────────
        if tipo == "articulo":
            prefix_idx: int | None = None
            es_arr = hw.get("prefix_es") or []
            for idx, tok in enumerate(es_arr):
                if (tok or "").strip().lower() == cur.lower():
                    prefix_idx = idx
                    break
            if prefix_idx is None:
                skipped.append({**row, "_razon": "valor_actual ya no encontrado en prefix_es"})
                continue
            if (ch, vs, pi, hi, prefix_idx) in prefix_edits:
                skipped.append({**row, "_razon": "posicion editada por usuario"})
                continue

            new = cur
            motivos_aplicados = []

            # -- Género --------------------------------------------------------
            if "genero" in motivos_raw and nucleus.lower() not in SKIP_NUCLEOS:
                n_low = nucleus.lower()
                c = votes.get(n_low)
                if c:
                    maj, n_maj = c.most_common(1)[0]
                    cur_g = ART_GN.get(cur.lower(), (None, None))[0]
                    if cur_g and maj != cur_g and n_maj >= min_votes:
                        num = ART_GN.get(cur.lower(), (None, None))[1] or "SG"
                        # Para contracciones (del/al) determinar el artículo correcto
                        # manteniendo la contracción si aplica.
                        if maj == "F":
                            if cur.lower() in ("del", "al"):
                                cand = "de la" if cur.lower() == "del" else "a la"
                            else:
                                cand = correct_article("F", num, n_low)
                        else:
                            if cur.lower() in ("de la", "a la"):
                                cand = "del" if "de" in cur.lower() else "al"
                            else:
                                cand = correct_article("M", num, n_low)
                        if cand and cand != cur.lower():
                            new = cand
                            motivos_aplicados.append(f"genero:{cur_g}->{maj}({n_maj}v)")

            # -- Número --------------------------------------------------------
            if "numero" in motivos_raw:
                base = (new or cur).lower()
                cur_gn = ART_GN.get(base)
                if cur_gn and nucleus.lower() not in A_STRESSED_SG:
                    art_num = cur_gn[1]
                    es_num = number_from_spanish(nucleus)
                    if es_num and es_num != art_num:
                        if es_num == "PL":
                            cand_n = token_to_plural(base)
                        else:
                            cand_n = token_to_singular(base)
                        if cand_n and cand_n != base:
                            new = cand_n
                            motivos_aplicados.append(f"numero:{art_num}->{es_num}")

            if new != cur and motivos_aplicados:
                es_arr[prefix_idx] = new
                changes.append((f"{ch}:{vs}", pi, hi, tipo, row["hebreo"],
                                 nucleus, cur, new, ";".join(motivos_aplicados)))
                counts["articulo"] += 1
            else:
                skipped.append({**row, "_razon": "sin confianza suficiente o excepción"})

        # ── Posesivo ──────────────────────────────────────────────────────────
        elif tipo == "posesivo":
            if (ch, vs, pi, hi) in combined_pos:
                skipped.append({**row, "_razon": "posicion editada por usuario"})
                continue
            ps = hw.get("prs_suffix")
            if not ps:
                skipped.append({**row, "_razon": "sin prs_suffix"})
                continue
            cur_tok = (ps.get("es") or "").strip()
            if cur_tok.lower() != cur.lower():
                skipped.append({**row, "_razon": "valor_actual ya no coincide"})
                continue

            n_low = nucleus.lower()
            c = votes.get(n_low)
            motivos_aplicados = []
            new = cur_tok
            if c:
                maj, n_maj = c.most_common(1)[0]
                pg = POSS_GN.get(cur_tok.lower(), (None, None))
                if pg[0] and maj != pg[0] and n_maj >= min_votes:
                    if maj == "F":
                        cand = {"nuestro": "nuestra", "nuestros": "nuestras",
                                "vuestro": "vuestra", "vuestros": "vuestras"}.get(cur_tok.lower(), cur_tok)
                    else:
                        cand = {"nuestra": "nuestro", "nuestras": "nuestros",
                                "vuestra": "vuestro", "vuestras": "vuestros"}.get(cur_tok.lower(), cur_tok)
                    if cand != cur_tok:
                        new = cand
                        motivos_aplicados.append(f"genero:{pg[0]}->{maj}({n_maj}v)")
            if new != cur_tok and motivos_aplicados:
                ps["es"] = new
                changes.append((f"{ch}:{vs}", pi, hi, tipo, row["hebreo"],
                                 nucleus, cur_tok, new, ";".join(motivos_aplicados)))
                counts["posesivo"] += 1
            else:
                skipped.append({**row, "_razon": "sin confianza suficiente o excepción"})

    # ── Reportes ──────────────────────────────────────────────────────────────
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    applied_path = DATA / f"_revisar_aplicado_{label}.csv"
    pendiente_path = DATA / f"_revisar_pendiente_{label}.csv"
    with open(applied_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ref", "pairIdx", "hwIdx", "tipo", "hebreo",
                    "es_nucleo", "antes", "despues", "motivo_aplicado"])
        for row in changes:
            w.writerow(row)
    with open(pendiente_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ref", "pairIdx", "hwIdx", "tipo", "hebreo",
                    "es_nucleo", "valor_actual", "motivo", "_razon"])
        for row in skipped:
            w.writerow([row.get(k, "") for k in
                        ["ref", "pairIdx", "hwIdx", "tipo", "hebreo",
                         "es_nucleo", "valor_actual", "motivo", "_razon"]])

    print(f"== Revisión ES: {label} (min_votes={min_votes}) ==")
    print(f"  APLICADOS: {len(changes)}")
    for k in sorted(counts):
        print(f"    {k:12s}: {counts[k]}")
    print(f"  omitidos (sin confianza / excepción): {len(skipped)}")
    print(f"  reporte aplicados : {applied_path}")
    print(f"  reporte pendientes: {pendiente_path}")

    if apply:
        if not no_backup:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            bak = BACKUP_DIR / f"{label}_rev_{ts}.json"
            bak.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            print(f"  respaldo: {bak}")
        atomic_write_json(path, data, separators=(",", ":"))
        print("  APLICADO.")
    else:
        print("  DRY-RUN. Usa --apply para escribir los cambios.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--part", type=int, choices=[1, 2], default=None)
    ap.add_argument("--min-votes", type=int, default=5,
                    help="Votos mínimos en corpus para auto-corregir género (default 5)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--no-backup", action="store_true",
                    help="No crear respaldo (uso en pipeline run_motors)")
    args = ap.parse_args()
    process_book(args.book, args.part, args.min_votes, args.apply,
                 getattr(args, "no_backup", False))


if __name__ == "__main__":
    main()
