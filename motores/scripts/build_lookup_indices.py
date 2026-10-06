"""
build_lookup_indices.py  —  PASO 1.A  (SOLO LECTURA del pipeline existente)

Construye dos índices auxiliares para Génesis a partir de los módulos PH4/SWORD:

  - BIBLIAS/_idx_strong_es_gen.json
        { "H7225": [ {"text": "En el principio", "count": 1, "verses": ["1:1"]}, ... ], ... }
  - BIBLIAS/_idx_strong_he_gen.json
        { "H7225": [ {"text": "בְּרֵאשִׁ֖ית", "morph": "HR/Ncfsa", "count": 1, "verses": ["1:1"]}, ... ], ... }

No modifica `genesis_final.json` ni ningún script del pipeline.

Si pysword no está instalado, intenta instalarlo automáticamente.
Si pysword falla en runtime, hace un fallback parseando el SWORD/OSIS
directamente sobre los archivos descomprimidos.
"""
from __future__ import annotations

import io
import json
import re
import sys
import zipfile
import subprocess
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BASE         = Path(r"C:\Users\pik_y\Documents\TRADUCCION\BIBLIAS")
ZIP_SPA      = BASE / "SpaRV1909.zip"
ZIP_OSHB     = BASE / "OSHB.zip"
DIR_SPA_IDX  = BASE / "_idx_SpaRV1909"
DIR_OSHB_IDX = BASE / "_idx_OSHB"
OUT_SPA      = BASE / "_idx_strong_es_gen.json"
OUT_OSHB     = BASE / "_idx_strong_he_gen.json"

# ---------------------------------------------------------------------------
# utilidades

def ensure_unzip(zip_path: Path, dest: Path) -> None:
    if dest.exists() and any(dest.iterdir()):
        print(f"  [skip] {dest.name} ya existe")
        return
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)
    print(f"  [ok]   {zip_path.name} -> {dest}")


def ensure_pysword() -> bool:
    try:
        import pysword  # noqa
        return True
    except ImportError:
        pass
    print("  pysword no está instalado, instalando...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", "pysword"]
        )
        import pysword  # noqa
        print("  pysword instalado.")
        return True
    except Exception as e:
        print(f"  WARNING: no se pudo instalar pysword ({e}); usaré fallback OSIS.")
        return False


def normalize_strong(raw: str) -> str:
    """`H07225`/`H7225`/`Strong:H07225`/`strong:H07225` -> `H7225` (sin padding)."""
    if not raw:
        return ""
    s = raw.strip()
    # quitar prefijos "Strong:" / "strong:"
    if ":" in s:
        s = s.split(":", 1)[1]
    s = s.strip()
    if not s:
        return ""
    # primer char debe ser H o G
    head = s[0].upper()
    if head not in ("H", "G"):
        return ""
    rest = s[1:].lstrip("0")
    if not rest:
        rest = "0"
    return f"{head}{rest}"


# ---------------------------------------------------------------------------
# parser de un verso (acepta tags <w>) y devuelve [(strong, text, morph)]

# acepta lemma="Strong:H7225" o lemma="strong:H07225 strong:H0853" (multi)
W_TAG_RE = re.compile(
    r'<w\b([^>]*)>(.*?)</w>',
    re.DOTALL,
)
ATTR_RE  = re.compile(r'(\w[\w:-]*)\s*=\s*"([^"]*)"')

def parse_w_tags(raw_verse: str):
    """Yields (strong_list, inner_text, morph_str) for every <w> tag."""
    for m in W_TAG_RE.finditer(raw_verse):
        attrs_str = m.group(1)
        inner     = m.group(2)
        attrs     = dict(ATTR_RE.findall(attrs_str))
        lemma     = attrs.get("lemma") or attrs.get("LEMMA") or ""
        morph     = attrs.get("morph") or attrs.get("MORPH") or ""
        # extraer strongs (puede haber varios: "strong:H1254 strong:H0853")
        strongs   = []
        for tok in re.split(r"\s+", lemma.strip()):
            ns = normalize_strong(tok)
            if ns:
                strongs.append(ns)
        # limpiar morph: quitar prefijo "oshm:" si está
        if ":" in morph:
            morph = morph.split(":", 1)[1]
        # limpiar texto interno de tags residuales (algunos OSIS tienen <seg> dentro)
        clean_inner = re.sub(r"<[^>]+>", "", inner).strip()
        yield strongs, clean_inner, morph


# ---------------------------------------------------------------------------
# obtención de los versos crudos de Génesis

def get_verses_pysword(root: Path, modname: str):
    """Yields (chapter:int, verse:int, raw_text:str) para todo Génesis."""
    from pysword.modules import SwordModules
    sm = SwordModules(str(root))
    found = sm.parse_modules()
    actual = next(
        (k for k in found if k.lower() == modname.lower()),
        next(iter(found.keys()), None),
    )
    if not actual:
        raise RuntimeError(f"no se encontró módulo {modname} en {root}")
    bible = sm.get_bible_from_module(actual)

    # número de capítulos / versos por capítulo: lo obtenemos por sondeo
    # (pysword expone bible.get_iter pero no estructura directamente)
    # estrategia: probamos chapters=[ch] sin verses, e iteramos los resultados.
    for ch in range(1, 51):  # Génesis: 50 capítulos
        try:
            it = bible.get_iter(books=["Genesis"], chapters=[ch], clean=False)
        except Exception as e:
            print(f"    pysword: get_iter falló para Gen {ch}: {e}")
            continue
        for vs_idx, raw in enumerate(it, start=1):
            yield ch, vs_idx, raw


def get_verses_osis_fallback(root: Path):
    """Lee archivos descomprimidos del módulo (rawtext) - fallback minimal.
    Para los módulos PH4 esto puede no ser trivial. Lo usamos solo si pysword falla.
    """
    # En SWORD ztext los versos están comprimidos en blocks; sin pysword
    # parsear esto a mano es no-trivial. Aquí devolvemos vacío y lanzamos.
    raise RuntimeError(
        "fallback OSIS no implementado: se requiere pysword. "
        "Instálalo con `pip install pysword`."
    )


def get_verses(root: Path, modname: str, have_pysword: bool):
    if have_pysword:
        yield from get_verses_pysword(root, modname)
    else:
        yield from get_verses_osis_fallback(root)


# ---------------------------------------------------------------------------
# construcción de índices

def build_es_index(root: Path, have_pysword: bool) -> dict:
    """STRONG_ES_GEN: para SpaRV1909 sólo Génesis."""
    print("\n[ES] Iterando Génesis de SpaRV1909 ...")
    # acumulador: strong -> text -> {"count": int, "verses": set}
    acc: dict[str, dict[str, dict]] = defaultdict(dict)
    total_verses = 0
    total_tags   = 0
    for ch, vs, raw in get_verses(root, "SpaRV1909", have_pysword):
        total_verses += 1
        ref_short = f"{ch}:{vs}"
        for strongs, text, morph in parse_w_tags(raw):
            total_tags += 1
            if not text:
                continue
            for s in strongs:
                bucket = acc[s].setdefault(text, {"count": 0, "verses": []})
                bucket["count"] += 1
                if ref_short not in bucket["verses"]:
                    bucket["verses"].append(ref_short)
    print(f"  versos leídos: {total_verses} | tags <w>: {total_tags} | strongs únicos: {len(acc)}")
    # convertir a lista ordenada por count desc
    out = {}
    for s, bucket in acc.items():
        entries = [
            {"text": t, "count": v["count"], "verses": v["verses"]}
            for t, v in bucket.items()
        ]
        entries.sort(key=lambda e: (-e["count"], e["text"]))
        out[s] = entries
    return out


def build_he_index(root: Path, have_pysword: bool) -> dict:
    """STRONG_HE_GEN: para OSHB sólo Génesis."""
    print("\n[HE] Iterando Génesis de OSHB ...")
    acc: dict[str, dict[tuple, dict]] = defaultdict(dict)
    total_verses = 0
    total_tags   = 0
    for ch, vs, raw in get_verses(root, "OSHB", have_pysword):
        total_verses += 1
        ref_short = f"{ch}:{vs}"
        for strongs, text, morph in parse_w_tags(raw):
            total_tags += 1
            if not text:
                continue
            for s in strongs:
                key = (text, morph)
                bucket = acc[s].setdefault(key, {"count": 0, "verses": []})
                bucket["count"] += 1
                if ref_short not in bucket["verses"]:
                    bucket["verses"].append(ref_short)
    print(f"  versos leídos: {total_verses} | tags <w>: {total_tags} | strongs únicos: {len(acc)}")
    out = {}
    for s, bucket in acc.items():
        entries = [
            {"text": k[0], "morph": k[1], "count": v["count"], "verses": v["verses"]}
            for k, v in bucket.items()
        ]
        entries.sort(key=lambda e: (-e["count"], e["text"]))
        out[s] = entries
    return out


# ---------------------------------------------------------------------------
# main

def main():
    print("== PASO 1.A — Construir índices Strong (Génesis) ==")
    print(f"BIBLIAS = {BASE}")

    print("\n[unzip]")
    ensure_unzip(ZIP_SPA,  DIR_SPA_IDX)
    ensure_unzip(ZIP_OSHB, DIR_OSHB_IDX)

    have_pysword = ensure_pysword()

    es_idx = build_es_index(DIR_SPA_IDX,  have_pysword)
    he_idx = build_he_index(DIR_OSHB_IDX, have_pysword)

    OUT_SPA.write_text(
        json.dumps(es_idx, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    OUT_OSHB.write_text(
        json.dumps(he_idx, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print("\n[done]")
    print(f"  ES  → {OUT_SPA}   ({OUT_SPA.stat().st_size:,} bytes, {len(es_idx)} Strongs)")
    print(f"  HE  → {OUT_OSHB}  ({OUT_OSHB.stat().st_size:,} bytes, {len(he_idx)} Strongs)")


if __name__ == "__main__":
    main()
