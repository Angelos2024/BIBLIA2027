"""
book_config.py — Registro maestro de libros (CATSS + OSHB + snapshot + LXX).

Cada libro declara sus rutas y metadatos. Todos los scripts del pipeline
(parse_catss, merge_book, paso5_*, apply_corrections, build_lookup_indices)
deben leer su configuración aquí en lugar de hard-codear rutas.

Convenciones:
- `slug`            : identificador minúsculo sin acentos (genesis, exodo, levitico, …)
- `par_filename`    : nombre dentro de angelos/catss-par/  (ej. 02.Exodus.par)
- `catss_ref_label` : prefijo de versículo del .par CATSS (Gen, Exod, Lev, Num, Deut, …)
- `oshb_chapter_dir`: subcarpeta en oshb-morph/chapters/  (01_Génesis, 02_Éxodo, …)
- `snap_chapter_dir`: subcarpeta en interlinear-snapshot/chapters/ (genesis, exodo, …)
- `inter_chapter_dir`: subcarpeta en interlineal/chapters/ (idem oshb)
- `chapters`        : nº de capítulos del libro (para iteración de índices)
- `pysword_book`    : nombre tal como lo expone pysword en SpaRV1909/OSHB

Para añadir un libro nuevo basta con extender `BOOKS`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


# Raíz heredada de la máquina de ingesta original (puede no existir aquí).
ROOT = Path(r"C:\Users\pik_y\Documents\TRADUCCION")
# Raíz real del repo (BIBLIA2027/), derivada de la ubicación de este archivo.
_REPO = Path(__file__).resolve().parent.parent.parent
# Los _final.json viven en data_master/ del repo. Si existe, se usa esa ruta;
# si no (máquina de ingesta original), se cae a la ruta heredada.
DATA = _REPO / "data_master" if (_REPO / "data_master").exists() else ROOT / "data"
BIBLIAS = _REPO / "fuentes" if (_REPO / "fuentes").exists() else ROOT / "BIBLIAS"
SCRIPTS = ROOT / "scripts"
BACKUPS = _REPO / "fuentes" / "backups" if (_REPO / "fuentes").exists() else ROOT / "backups"

ANGELOS = Path(r"C:\Users\pik_y\Documents\GitHub\Local-consults\estudio\angelos")
CATSS_DIR = ANGELOS / "catss-par"          # .par grandes (descarga manual)
CATSS_SAMPLE_DIR = ANGELOS / "catss-sample"  # solo Génesis (queda en repo)
OSHB_BASE = ANGELOS / "IdiomaORIGEN" / "oshb-morph" / "chapters"
SNAP_BASE = ANGELOS / "IdiomaORIGEN" / "interlinear-snapshot" / "chapters"
INTER_BASE = ANGELOS / "IdiomaORIGEN" / "interlineal" / "chapters"


@dataclass(frozen=True)
class BookConfig:
    slug: str
    label: str
    catss_ref_label: str             # ej. "Gen", "Exod"
    par_filename: str
    oshb_chapter_dir: str            # ej. "01_Génesis"
    snap_chapter_dir: str            # ej. "genesis"
    inter_chapter_dir: str           # ej. "01_Génesis"
    chapters: int
    pysword_book: str                # nombre canónico para pysword

    # Salida y artefactos
    raw_json: str = ""               # <slug>_full.json (parser CATSS)
    final_json: str = ""             # <slug>_final.json (post-merge + correcciones)
    idx_es_json: str = ""            # _idx_strong_es_<slug>.json
    idx_he_json: str = ""            # _idx_strong_he_<slug>.json

    aliases: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw_json", self.raw_json or f"{self.slug}_full.json")
        object.__setattr__(self, "final_json", self.final_json or f"{self.slug}_final.json")
        object.__setattr__(self, "idx_es_json", self.idx_es_json or f"_idx_strong_es_{self.slug}.json")
        object.__setattr__(self, "idx_he_json", self.idx_he_json or f"_idx_strong_he_{self.slug}.json")

    # ── Rutas resueltas ──────────────────────────────────────────────────────
    @property
    def par_path(self) -> Path:
        # Busca en catss-sample/ primero, luego catss-par/
        p = CATSS_SAMPLE_DIR / self.par_filename
        if p.exists():
            return p
        return CATSS_DIR / self.par_filename

    @property
    def oshb_dir(self) -> Path:
        return OSHB_BASE / self.oshb_chapter_dir

    @property
    def snap_dir(self) -> Path:
        return SNAP_BASE / self.snap_chapter_dir

    @property
    def inter_dir(self) -> Path:
        return INTER_BASE / self.inter_chapter_dir

    @property
    def raw_json_path(self) -> Path:
        return DATA / self.raw_json

    @property
    def final_json_path(self) -> Path:
        return DATA / self.final_json

    @property
    def idx_es_path(self) -> Path:
        return BIBLIAS / self.idx_es_json

    @property
    def idx_he_path(self) -> Path:
        return BIBLIAS / self.idx_he_json

    # ── Validación de fuentes ────────────────────────────────────────────────
    def check_sources(self) -> dict[str, bool]:
        return {
            "par": self.par_path.exists(),
            "oshb": self.oshb_dir.exists()
                    and any(self.oshb_dir.glob("*.json")),
            "snapshot": self.snap_dir.exists()
                        and any(self.snap_dir.glob("*.json")),
            "interlineal": self.inter_dir.exists()
                           and any(self.inter_dir.glob("*.json")),
            "idx_es": self.idx_es_path.exists(),
            "idx_he": self.idx_he_path.exists(),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Registro de libros
# ─────────────────────────────────────────────────────────────────────────────
BOOKS: dict[str, BookConfig] = {
    "genesis": BookConfig(
        slug="genesis",
        label="Génesis",
        catss_ref_label="Gen",
        par_filename="01.Genesis.par",
        oshb_chapter_dir="01_Génesis",
        snap_chapter_dir="genesis",
        inter_chapter_dir="01_Génesis",
        chapters=50,
        pysword_book="Genesis",
        idx_es_json="_idx_strong_es_gen.json",   # compat con archivos existentes
        idx_he_json="_idx_strong_he_gen.json",
        aliases=("gen", "génesis", "gn"),
    ),
    "exodo": BookConfig(
        slug="exodo",
        label="Éxodo",
        catss_ref_label="Exod",
        par_filename="02.Exodus.par",
        oshb_chapter_dir="02_Éxodo",
        snap_chapter_dir="exodo",
        inter_chapter_dir="02_Éxodo",
        chapters=40,
        pysword_book="Exodus",
        aliases=("ex", "éxodo", "exodus"),
    ),
    "levitico": BookConfig(
        slug="levitico",
        label="Levítico",
        catss_ref_label="Lev",
        par_filename="03.Lev.par",
        oshb_chapter_dir="03_Levítico",
        snap_chapter_dir="levitico",
        inter_chapter_dir="03_Levítico",
        chapters=27,
        pysword_book="Leviticus",
        aliases=("lv", "levítico", "leviticus"),
    ),
    "numeros": BookConfig(
        slug="numeros",
        label="Números",
        catss_ref_label="Num",
        par_filename="04.Num.par",
        oshb_chapter_dir="04_Números",
        snap_chapter_dir="numeros",
        inter_chapter_dir="04_Números",
        chapters=36,
        pysword_book="Numbers",
        aliases=("nm", "números", "numbers"),
    ),
    "deuteronomio": BookConfig(
        slug="deuteronomio",
        label="Deuteronomio",
        catss_ref_label="Deut",
        par_filename="05.Deut.par",
        oshb_chapter_dir="05_Deuteronomio",
        snap_chapter_dir="deuteronomio",
        inter_chapter_dir="05_Deuteronomio",
        chapters=34,
        pysword_book="Deuteronomy",
        aliases=("dt", "deut"),
    ),
    # ── Profetas anteriores ─────────────────────────────────────────────────
    "josue": BookConfig(
        slug="josue",
        label="Josué",
        catss_ref_label="JoshB",
        par_filename="06.JoshB.par",
        oshb_chapter_dir="06_Josué",
        snap_chapter_dir="josue",
        inter_chapter_dir="06_Josué",
        chapters=24,
        pysword_book="Joshua",
        aliases=("jos", "joshua"),
    ),
    "jueces": BookConfig(
        slug="jueces",
        label="Jueces",
        catss_ref_label="JudgB",
        par_filename="08.JudgesB.par",
        oshb_chapter_dir="07_Jueces",
        snap_chapter_dir="jueces",
        inter_chapter_dir="07_Jueces",
        chapters=21,
        pysword_book="Judges",
        aliases=("jue", "judges"),
    ),
    "rut": BookConfig(
        slug="rut",
        label="Rut",
        catss_ref_label="Ruth",
        par_filename="10.Ruth.par",
        oshb_chapter_dir="08_Rut",
        snap_chapter_dir="rut",
        inter_chapter_dir="08_Rut",
        chapters=4,
        pysword_book="Ruth",
        aliases=("rt", "ruth"),
    ),
    "1_samuel": BookConfig(
        slug="1_samuel",
        label="1 Samuel",
        catss_ref_label="1Sam/K",
        par_filename="11.1Sam.par",
        oshb_chapter_dir="09_1_Samuel",
        snap_chapter_dir="1_samuel",
        inter_chapter_dir="09_1_Samuel",
        chapters=31,
        pysword_book="I Samuel",
        aliases=("1sam", "1samuel"),
    ),
    "2_samuel": BookConfig(
        slug="2_samuel",
        label="2 Samuel",
        catss_ref_label="2Sam/K",
        par_filename="12.2Sam.par",
        oshb_chapter_dir="10_2_Samuel",
        snap_chapter_dir="2_samuel",
        inter_chapter_dir="10_2_Samuel",
        chapters=24,
        pysword_book="II Samuel",
        aliases=("2sam", "2samuel"),
    ),
    "1_reyes": BookConfig(
        slug="1_reyes",
        label="1 Reyes",
        catss_ref_label="1/3Kgs",
        par_filename="13.1Kings.par",
        oshb_chapter_dir="11_1_Reyes",
        snap_chapter_dir="1_reyes",
        inter_chapter_dir="11_1_Reyes",
        chapters=22,
        pysword_book="I Kings",
        aliases=("1rey", "1reyes", "1kings"),
    ),
    "2_reyes": BookConfig(
        slug="2_reyes",
        label="2 Reyes",
        catss_ref_label="2/4Kgs",
        par_filename="14.2Kings.par",
        oshb_chapter_dir="12_2_Reyes",
        snap_chapter_dir="2_reyes",
        inter_chapter_dir="12_2_Reyes",
        chapters=25,
        pysword_book="II Kings",
        aliases=("2rey", "2reyes", "2kings"),
    ),
    # ── Escritos ────────────────────────────────────────────────────────────
    "1_cronicas": BookConfig(
        slug="1_cronicas",
        label="1 Crónicas",
        catss_ref_label="1Chr",
        par_filename="15.1Chron.par",
        oshb_chapter_dir="13_1_Crónicas",
        snap_chapter_dir="1_cronicas",
        inter_chapter_dir="13_1_Crónicas",
        chapters=29,
        pysword_book="I Chronicles",
        aliases=("1cro", "1cronicas", "1chronicles"),
    ),
    "2_cronicas": BookConfig(
        slug="2_cronicas",
        label="2 Crónicas",
        catss_ref_label="2Chr",
        par_filename="16.2Chron.par",
        oshb_chapter_dir="14_2_Crónicas",
        snap_chapter_dir="2_cronicas",
        inter_chapter_dir="14_2_Crónicas",
        chapters=36,
        pysword_book="II Chronicles",
        aliases=("2cro", "2cronicas", "2chronicles"),
    ),
    "esdras": BookConfig(
        slug="esdras",
        label="Esdras",
        catss_ref_label="Ezr",
        par_filename="18.Ezra.par",
        oshb_chapter_dir="15_Esdras",
        snap_chapter_dir="esdras",
        inter_chapter_dir="15_Esdras",
        chapters=10,
        pysword_book="Ezra",
        aliases=("esd", "ezra"),
    ),
    "nehemias": BookConfig(
        slug="nehemias",
        label="Nehemías",
        catss_ref_label="Neh",
        par_filename="19.Neh.par",
        oshb_chapter_dir="16_Nehemías",
        snap_chapter_dir="nehemias",
        inter_chapter_dir="16_Nehemías",
        chapters=13,
        pysword_book="Nehemiah",
        aliases=("neh", "nehemías", "nehemiah"),
    ),
    "ester": BookConfig(
        slug="ester",
        label="Ester",
        catss_ref_label="Esth",
        par_filename="18.Esther.par",
        oshb_chapter_dir="17_Ester",
        snap_chapter_dir="ester",
        inter_chapter_dir="17_Ester",
        chapters=10,
        pysword_book="Esther",
        aliases=("est", "esther"),
    ),
    "job": BookConfig(
        slug="job",
        label="Job",
        catss_ref_label="Job",
        par_filename="26.Job.par",
        oshb_chapter_dir="18_Job",
        snap_chapter_dir="job",
        inter_chapter_dir="18_Job",
        chapters=42,
        pysword_book="Job",
        aliases=("jb",),
    ),
    "salmos": BookConfig(
        slug="salmos",
        label="Salmos",
        catss_ref_label="Ps",
        par_filename="20.Psalms.par",
        oshb_chapter_dir="19_Salmos",
        snap_chapter_dir="salmos",
        inter_chapter_dir="19_Salmos",
        chapters=150,
        pysword_book="Psalms",
        aliases=("sal", "psalm", "psalms"),
    ),
    "proverbios": BookConfig(
        slug="proverbios",
        label="Proverbios",
        catss_ref_label="Prov",
        par_filename="23.Prov.par",
        oshb_chapter_dir="20_Proverbios",
        snap_chapter_dir="proverbios",
        inter_chapter_dir="20_Proverbios",
        chapters=31,
        pysword_book="Proverbs",
        aliases=("prov", "proverbs"),
    ),
    "eclesiastes": BookConfig(
        slug="eclesiastes",
        label="Eclesiastés",
        catss_ref_label="Qoh",
        par_filename="24.Qoh.par",
        oshb_chapter_dir="21_Eclesiastés",
        snap_chapter_dir="eclesiastes",
        inter_chapter_dir="21_Eclesiastés",
        chapters=12,
        pysword_book="Ecclesiastes",
        aliases=("ecl", "eclesiastés", "qoheleth", "ecclesiastes"),
    ),
    "cantares": BookConfig(
        slug="cantares",
        label="Cantares",
        catss_ref_label="Song",
        par_filename="25.Cant.par",
        oshb_chapter_dir="22_Cantares",
        snap_chapter_dir="cantares",
        inter_chapter_dir="22_Cantares",
        chapters=8,
        pysword_book="Song of Solomon",
        aliases=("cnt", "cantar", "song"),
    ),
    # ── Profetas mayores ────────────────────────────────────────────────────
    "isaias": BookConfig(
        slug="isaias",
        label="Isaías",
        catss_ref_label="Isa",
        par_filename="40.Isaiah.par",
        oshb_chapter_dir="23_Isaías",
        snap_chapter_dir="isaias",
        inter_chapter_dir="23_Isaías",
        chapters=66,
        pysword_book="Isaiah",
        aliases=("isa", "isaías", "isaiah"),
    ),
    "jeremias": BookConfig(
        slug="jeremias",
        label="Jeremías",
        catss_ref_label="Jer",
        par_filename="41.Jer.par",
        oshb_chapter_dir="24_Jeremías",
        snap_chapter_dir="jeremias",
        inter_chapter_dir="24_Jeremías",
        chapters=52,
        pysword_book="Jeremiah",
        aliases=("jer", "jeremías", "jeremiah"),
    ),
    "lamentaciones": BookConfig(
        slug="lamentaciones",
        label="Lamentaciones",
        catss_ref_label="Lam",
        par_filename="43.Lam.par",
        oshb_chapter_dir="25_Lamentaciones",
        snap_chapter_dir="lamentaciones",
        inter_chapter_dir="25_Lamentaciones",
        chapters=5,
        pysword_book="Lamentations",
        aliases=("lam", "lamentations"),
    ),
    "ezequiel": BookConfig(
        slug="ezequiel",
        label="Ezequiel",
        catss_ref_label="Ezek",
        par_filename="44.Ezekiel.par",
        oshb_chapter_dir="26_Ezequiel",
        snap_chapter_dir="ezequiel",
        inter_chapter_dir="26_Ezequiel",
        chapters=48,
        pysword_book="Ezekiel",
        aliases=("ezeq", "ezekiel"),
    ),
    "daniel": BookConfig(
        slug="daniel",
        label="Daniel",
        catss_ref_label="Dan",
        par_filename="45.DanielOG.par",
        oshb_chapter_dir="27_Daniel",
        snap_chapter_dir="daniel",
        inter_chapter_dir="27_Daniel",
        chapters=12,
        pysword_book="Daniel",
        aliases=("dan",),
    ),
    # ── Profetas menores (Tré Asar) ─────────────────────────────────────────
    "oseas": BookConfig(
        slug="oseas",
        label="Oseas",
        catss_ref_label="Hos",
        par_filename="28.Hosea.par",
        oshb_chapter_dir="28_Oseas",
        snap_chapter_dir="oseas",
        inter_chapter_dir="28_Oseas",
        chapters=14,
        pysword_book="Hosea",
        aliases=("os", "hosea"),
    ),
    "joel": BookConfig(
        slug="joel",
        label="Joel",
        catss_ref_label="Joel",
        par_filename="31.Joel.par",
        oshb_chapter_dir="29_Joel",
        snap_chapter_dir="joel",
        inter_chapter_dir="29_Joel",
        chapters=4,
        pysword_book="Joel",
        aliases=("jl",),
    ),
    "amos": BookConfig(
        slug="amos",
        label="Amós",
        catss_ref_label="Amos",
        par_filename="30.Amos.par",
        oshb_chapter_dir="30_Amós",
        snap_chapter_dir="amos",
        inter_chapter_dir="30_Amós",
        chapters=9,
        pysword_book="Amos",
        aliases=("am", "amós"),
    ),
    "abdias": BookConfig(
        slug="abdias",
        label="Abdías",
        catss_ref_label="Obad",
        par_filename="33.Obadiah.par",
        oshb_chapter_dir="31_Abdías",
        snap_chapter_dir="abdias",
        inter_chapter_dir="31_Abdías",
        chapters=1,
        pysword_book="Obadiah",
        aliases=("abd", "abdías", "obadiah"),
    ),
    "jonas": BookConfig(
        slug="jonas",
        label="Jonás",
        catss_ref_label="Jonah",
        par_filename="32.Jonah.par",
        oshb_chapter_dir="32_Jonás",
        snap_chapter_dir="jonas",
        inter_chapter_dir="32_Jonás",
        chapters=4,
        pysword_book="Jonah",
        aliases=("jon", "jonás", "jonah"),
    ),
    "miqueas": BookConfig(
        slug="miqueas",
        label="Miqueas",
        catss_ref_label="Mic",
        par_filename="29.Micah.par",
        oshb_chapter_dir="33_Miqueas",
        snap_chapter_dir="miqueas",
        inter_chapter_dir="33_Miqueas",
        chapters=7,
        pysword_book="Micah",
        aliases=("miq", "micah"),
    ),
    "nahum": BookConfig(
        slug="nahum",
        label="Nahúm",
        catss_ref_label="Nah",
        par_filename="34.Nahum.par",
        oshb_chapter_dir="34_Nahúm",
        snap_chapter_dir="nahum",
        inter_chapter_dir="34_Nahúm",
        chapters=3,
        pysword_book="Nahum",
        aliases=("na", "nahúm"),
    ),
    "habacuc": BookConfig(
        slug="habacuc",
        label="Habacuc",
        catss_ref_label="Hab",
        par_filename="35.Hab.par",
        oshb_chapter_dir="35_Habacuc",
        snap_chapter_dir="habacuc",
        inter_chapter_dir="35_Habacuc",
        chapters=3,
        pysword_book="Habakkuk",
        aliases=("hab", "habakkuk"),
    ),
    "sofonias": BookConfig(
        slug="sofonias",
        label="Sofonías",
        catss_ref_label="Zeph",
        par_filename="36.Zeph.par",
        oshb_chapter_dir="36_Sofonías",
        snap_chapter_dir="sofonias",
        inter_chapter_dir="36_Sofonías",
        chapters=3,
        pysword_book="Zephaniah",
        aliases=("sof", "sofonías", "zephaniah"),
    ),
    "hageo": BookConfig(
        slug="hageo",
        label="Hageo",
        catss_ref_label="Hag",
        par_filename="37.Haggai.par",
        oshb_chapter_dir="37_Hageo",
        snap_chapter_dir="hageo",
        inter_chapter_dir="37_Hageo",
        chapters=2,
        pysword_book="Haggai",
        aliases=("hag", "haggai"),
    ),
    "zacarias": BookConfig(
        slug="zacarias",
        label="Zacarías",
        catss_ref_label="Zech",
        par_filename="38.Zech.par",
        oshb_chapter_dir="38_Zacarías",
        snap_chapter_dir="zacarias",
        inter_chapter_dir="38_Zacarías",
        chapters=14,
        pysword_book="Zechariah",
        aliases=("zac", "zacarías", "zechariah"),
    ),
    "malaquias": BookConfig(
        slug="malaquias",
        label="Malaquías",
        catss_ref_label="Mal",
        par_filename="39.Malachi.par",
        oshb_chapter_dir="39_Malaquías",
        snap_chapter_dir="malaquias",
        inter_chapter_dir="39_Malaquías",
        chapters=3,
        pysword_book="Malachi",
        aliases=("mal", "malaquías", "malachi"),
    ),
}


def resolve(name: str) -> BookConfig:
    """Devuelve BookConfig por slug o alias (case-insensitive)."""
    if not name:
        raise KeyError("libro vacío")
    key = name.strip().lower()
    if key in BOOKS:
        return BOOKS[key]
    for cfg in BOOKS.values():
        if key in (a.lower() for a in cfg.aliases):
            return cfg
        if key == cfg.label.lower():
            return cfg
    raise KeyError(f"libro desconocido: {name!r} (slugs: {', '.join(BOOKS)})")


def list_books() -> list[BookConfig]:
    return list(BOOKS.values())


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print("Libros registrados:\n")
    for cfg in list_books():
        st = cfg.check_sources()
        flags = " ".join(
            f"{k}={'✓' if v else '✗'}" for k, v in st.items()
        )
        print(f"  {cfg.slug:<14} {cfg.label:<14} {cfg.chapters:>3} caps  {flags}")
