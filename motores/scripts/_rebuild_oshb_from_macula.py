"""
_rebuild_oshb_from_macula.py
Regenera los archivos OSHB morph (1 JSON por capítulo) desde macula-hebrew.tsv.

Protege: Génesis y Éxodo (no los toca).
Elimina: archivos erróneos en dirs 03-39.
Genera: archivos correctos con forms[] y morphs[] en formato dotted descriptivo.

Uso:
    python _rebuild_oshb_from_macula.py           # dry-run
    python _rebuild_oshb_from_macula.py --apply    # aplica cambios
"""
import sys, csv, json, argparse, shutil
from pathlib import Path
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

TSV = Path(r"C:\Users\pik_y\Documents\GitHub\Local-consults\estudio\angelos"
           r"\IdiomaORIGEN\macula-hebrew.tsv")
OSHB_BASE = Path(r"C:\Users\pik_y\Documents\GitHub\Local-consults\estudio\angelos"
                 r"\IdiomaORIGEN\oshb-morph\chapters")

PROTECTED = {"01_Génesis", "02_Éxodo"}

MACULA_TO_SLUG = {
    "GEN": "genesis", "EXO": "exodo", "LEV": "levitico", "NUM": "numeros",
    "DEU": "deuteronomio", "JOS": "josue", "JDG": "jueces", "RUT": "rut",
    "1SA": "1_samuel", "2SA": "2_samuel", "1KI": "1_reyes", "2KI": "2_reyes",
    "1CH": "1_cronicas", "2CH": "2_cronicas", "EZR": "esdras", "NEH": "nehemias",
    "EST": "ester", "JOB": "job", "PSA": "salmos", "PRO": "proverbios",
    "ECC": "eclesiastes", "SNG": "cantares", "ISA": "isaias", "JER": "jeremias",
    "LAM": "lamentaciones", "EZK": "ezequiel", "DAN": "daniel", "HOS": "oseas",
    "JOL": "joel", "AMO": "amos", "OBA": "abdias", "JON": "jonas",
    "MIC": "miqueas", "NAM": "nahum", "HAB": "habacuc", "ZEP": "sofonias",
    "HAG": "hageo", "ZEC": "zacarias", "MAL": "malaquias",
}

SLUG_TO_DIR = {
    "genesis": "01_Génesis", "exodo": "02_Éxodo", "levitico": "03_Levítico",
    "numeros": "04_Números", "deuteronomio": "05_Deuteronomio",
    "josue": "06_Josué", "jueces": "07_Jueces", "rut": "08_Rut",
    "1_samuel": "09_1_Samuel", "2_samuel": "10_2_Samuel",
    "1_reyes": "11_1_Reyes", "2_reyes": "12_2_Reyes",
    "1_cronicas": "13_1_Crónicas", "2_cronicas": "14_2_Crónicas",
    "esdras": "15_Esdras", "nehemias": "16_Nehemías",
    "ester": "17_Ester", "job": "18_Job", "salmos": "19_Salmos",
    "proverbios": "20_Proverbios", "eclesiastes": "21_Eclesiastés",
    "cantares": "22_Cantares", "isaias": "23_Isaías", "jeremias": "24_Jeremías",
    "lamentaciones": "25_Lamentaciones", "ezequiel": "26_Ezequiel",
    "daniel": "27_Daniel", "oseas": "28_Oseas", "joel": "29_Joel",
    "amos": "30_Amós", "abdias": "31_Abdías", "jonas": "32_Jonás",
    "miqueas": "33_Miqueas", "nahum": "34_Nahúm", "habacuc": "35_Habacuc",
    "sofonias": "36_Sofonías", "hageo": "37_Hageo", "zacarias": "38_Zacarías",
    "malaquias": "39_Malaquías",
}

# ─── Morph conversion helpers ──────────────────────────────────────────────

_STEM = {
    "qal": "QAL", "niphal": "NIF", "piel": "PIEL", "pual": "PUAL",
    "hiphil": "HIF", "hophal": "HOF", "hithpael": "HIT",
    "polel": "POLEL", "polal": "POLAL", "hithpolel": "HITPOLEL",
    "pilpel": "PILPEL", "pulal": "PULAL", "palel": "PALEL",
    "tiphil": "TIPHIL", "nithpael": "NITHPAEL", "pealal": "PEALAL",
    "pilel": "PILEL", "hithpalel": "HITPALEL", "hithpoel": "HITPOEL",
    "poal": "POAL", "poel": "POEL", "hothpaal": "HOTHPAAL",
    "hishtaphel": "HISHTAPHEL", "nitpael": "NITPAEL",
    "palpel": "PALPEL", "tiphal": "TIPHAL",
}
_TYPE = {
    "perfect": "PERF", "imperfect": "IMPF", "yiqtol": "IMPF",
    "wayyiqtol": "WAYYIQT", "weqatal": "SEQ.PERF",
    "imperative": "IMPV", "infinitive construct": "INFC",
    "infinitive absolute": "INFA",
    "participle active": "PTCA", "participle passive": "PTCP",
    "participle": "PTCA", "cohortative": "COHORT", "jussive": "JUSS",
    "sequential perfect": "SEQ.PERF",
}
_PERSON = {"first": "P1", "second": "P2", "third": "P3"}
_GENDER = {"masculine": "M", "feminine": "F", "both": "BOTH", "common": "COMMON"}
_NUMBER = {"singular": "SG", "plural": "PL", "dual": "DU"}
_STATE  = {"absolute": "A", "construct": "C", "determined": "D"}


def to_dotted(pos, stem, typ, person, gender, number, state):
    """Convert Macula TSV fields to dotted descriptive morph label."""
    g = _GENDER.get(gender, "")
    n = _NUMBER.get(number, "")
    s = _STATE.get(state, "")
    p = _PERSON.get(person, "")

    if pos == "conjunction":
        return "CONJ"
    if pos == "preposition":
        return "PREP"
    if pos == "article":
        return "ART"

    if pos == "noun":
        if typ == "proper":
            return "NPROP"
        if typ == "gentilic":
            parts = ["GENT"]
            if g: parts.append(g)
            if n: parts.append(n)
            if s: parts.append(s)
            return ".".join(parts)
        parts = ["SUBS"]
        if g: parts.append(g)
        if n: parts.append(n)
        if s: parts.append(s)
        return ".".join(parts)

    if pos == "verb":
        st = _STEM.get(stem, stem.upper() if stem else "")
        t  = _TYPE.get(typ, typ.upper().replace(" ", ".") if typ else "")
        parts = ["VERBO"]
        if st: parts.append(st)
        if t:  parts.append(t)
        if p:  parts.append(p)
        if g:  parts.append(g)
        if n:  parts.append(n)
        return ".".join(parts)

    if pos == "adjective":
        parts = ["ADJ"]
        if g: parts.append(g)
        if n: parts.append(n)
        if s: parts.append(s)
        return ".".join(parts)

    if pos == "suffix":
        if typ == "pronominal":
            parts = ["PRS"]
            if p: parts.append(p)
            if g: parts.append(g)
            if n: parts.append(n)
            return ".".join(parts)
        if typ == "directional":
            return "SUF.DIR.HE"
        if typ == "paragogic nun":
            return "SUF.PARAG.NUN"
        if typ == "paragogic he":
            return "SUF.PARAG.HE"
        return "SUF"

    if pos == "pronoun":
        if typ == "personal":
            parts = ["PRON.PERS"]
            if p: parts.append(p)
            if g: parts.append(g)
            if n: parts.append(n)
            return ".".join(parts)
        if typ == "demonstrative":
            parts = ["PRON.DEM"]
            if g: parts.append(g)
            if n: parts.append(n)
            return ".".join(parts)
        if typ == "interrogative":
            return "PRON.INT"
        if typ == "relative":
            return "REL"
        if typ == "indefinite":
            return "PRON.INDEF"
        return "PRON"

    if pos == "particle":
        if typ == "negative":
            return "NEG"
        if typ == "object marker":
            return "PART.OBJ.DIR"
        if typ == "relative":
            return "REL"
        if typ == "interjection":
            return "INTJ"
        if typ == "demonstrative":
            return "PART.DEM"
        if typ == "interrogative":
            return "PART.INT"
        if typ == "affirmation":
            return "PART.AFFIRM"
        if typ == "exhortation":
            return "PART.EXHORT"
        return "PART"

    if pos == "adverb":
        return "ADV"
    if pos == "interjection":
        return "INTJ"
    if pos == "numeral":
        parts = ["NUM"]
        if typ == "cardinal":
            parts.append("CARD")
        elif typ == "ordinal":
            parts.append("ORD")
        if g: parts.append(g)
        if n: parts.append(n)
        if s: parts.append(s)
        return ".".join(parts)

    return pos.upper() if pos else "?"


# ─── Main ──────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Aplica cambios (default: dry-run)")
    args = ap.parse_args()

    print(f"Leyendo {TSV.name} ...")
    # book_code → chapter → verse → [(text, morph_dotted)]
    data = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    total_rows = 0

    with open(TSV, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            ref = row.get("ref", "")
            if " " not in ref:
                continue
            book_code, rest = ref.split(" ", 1)
            if book_code not in MACULA_TO_SLUG:
                continue
            slug = MACULA_TO_SLUG[book_code]
            if slug in ("genesis", "exodo"):
                continue

            parts = rest.split("!")
            cv = parts[0]
            ch_vs = cv.split(":")
            if len(ch_vs) != 2:
                continue
            try:
                ch = int(ch_vs[0])
                vs = int(ch_vs[1])
            except ValueError:
                continue

            text = row.get("text", "")
            pos = row.get("pos", "")
            stem = row.get("stem", "")
            typ = row.get("type", "")
            person = row.get("person", "")
            gender = row.get("gender", "")
            number = row.get("number", "")
            state = row.get("state", "")

            dotted = to_dotted(pos, stem, typ, person, gender, number, state)
            data[slug][ch][vs].append((text, dotted))
            total_rows += 1

    print(f"  {total_rows:,} morfemas leídos para {len(data)} libros (excl. Gén/Éx)")

    # ── Phase 1: Clean wrong files in dirs 3-39 ──
    cleaned = 0
    for slug, dirname in SLUG_TO_DIR.items():
        if dirname in PROTECTED:
            continue
        d = OSHB_BASE / dirname
        if not d.exists():
            continue
        for f in d.glob("*.json"):
            if args.apply:
                f.unlink()
            cleaned += 1

    mode = "APLICANDO" if args.apply else "DRY RUN"
    print(f"\n=== {mode}: Limpieza ===")
    print(f"  Archivos erróneos eliminados: {cleaned}")

    # ── Phase 2: Write correct files ──
    written = 0
    for slug in sorted(data.keys()):
        dirname = SLUG_TO_DIR.get(slug)
        if not dirname:
            print(f"  WARN: no dir for {slug}")
            continue
        d = OSHB_BASE / dirname
        if not d.exists():
            if args.apply:
                d.mkdir(parents=True, exist_ok=True)
            print(f"  Creando directorio: {dirname}")

        chapters = data[slug]
        for ch in sorted(chapters.keys()):
            verses = chapters[ch]
            ch_data = {}
            for vs in sorted(verses.keys()):
                morphemes = verses[vs]
                ch_data[str(vs)] = {
                    "forms":  [m[0] for m in morphemes],
                    "morphs": [m[1] for m in morphemes],
                }

            out_path = d / f"{ch}.json"
            if args.apply:
                out_path.write_text(
                    json.dumps(ch_data, ensure_ascii=False, indent=None),
                    encoding="utf-8"
                )
            written += 1

    print(f"\n=== {mode}: Generación ===")
    print(f"  Archivos de capítulo generados: {written}")

    # ── Summary per book ──
    print(f"\n=== Resumen por libro ===")
    for slug in sorted(data.keys()):
        chapters = data[slug]
        total_morphemes = sum(len(m) for ch in chapters.values() for m in ch.values())
        total_verses = sum(len(ch) for ch in chapters.values())
        print(f"  {slug:18s}  {len(chapters):>3} caps  {total_verses:>5} versos  "
              f"{total_morphemes:>7} morfemas")

    if not args.apply:
        print(f"\n  Usa --apply para ejecutar los cambios.")


if __name__ == "__main__":
    main()
