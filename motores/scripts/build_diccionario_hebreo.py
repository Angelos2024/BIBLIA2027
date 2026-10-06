"""build_diccionario_hebreo.py — Consolida los diccionarios de `dic/Diccionarioboton`.

De todos los archivos `diccionario_*.json` toma SOLO las entradas hebreas
(descarta griego y otros), deduplica por forma VOCALIZADA (mantiene niqqud;
quita cantilación, dagesh, meteg y signos) y escribe un único índice ordenado
para el editor:

    data/diccionario_hebreo.json

Deduplicar por forma vocalizada evita confundir homógrafos con las mismas
consonantes pero distintas vocales (p. ej. אֹון vs אָוֶן), que antes se fusionaban
en una sola entrada.

Cada entrada de salida conserva:
    clave            forma VOCALIZADA (para emparejar con el interlineal)
    clave_consonantal forma sin vocales (referencia/búsqueda)
    texto_hebreo     forma puntuada (la más rica encontrada)
    transliteracion
    equivalencia_espanol
    observacion      (referencia; el editor muestra los 3 campos pedidos)
    fuentes          lista de archivos de donde proviene

Uso:
    python build_diccionario_hebreo.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
ANGELOS = ROOT.parent / "GitHub" / "Local-consults" / "estudio" / "angelos"
DIC_DIR = ANGELOS / "dic" / "Diccionarioboton"
OUT_PATH = ROOT / "data" / "diccionario_hebreo.json"

# Rango de letras hebreas (alef–tav y finales)
HEBREW_LETTER = re.compile(r"[\u05D0-\u05EA]")
GREEK_LETTER = re.compile(r"[\u0370-\u03FF\u1F00-\u1FFF]")
# Niqqud, cantilación y signos de puntuación hebreos a eliminar para la clave
# CONSONÁNTICA (quita TODO: vocales, cantilación, puntos sin/shin, etc.).
_STRIP = re.compile(r"[\u0591-\u05BD\u05BF\u05C1-\u05C7\u05BE\u05C0\u05F3\u05F4]")
# Para la clave VOCALIZADA: quita solo cantilación, dagesh, meteg, rafe y signos,
# pero MANTIENE las vocales (niqqud) y los puntos sin/shin. Debe coincidir con
# traduccion-tokens.vowelKey.
_STRIP_VOWELKEY = re.compile(
    r"[\u0591-\u05AF\u05BC\u05BD\u05BE\u05BF\u05C0\u05C3-\u05C6\u05F3\u05F4]"
)


def clean_consonants(s: str) -> str:
    if not s:
        return ""
    t = _STRIP.sub("", str(s))
    t = re.sub(r"[\s\-־–]+", "", t)
    return t.strip()


def vowel_key(s: str) -> str:
    if not s:
        return ""
    t = _STRIP_VOWELKEY.sub("", str(s))
    t = re.sub(r"[\s\-־–]+", "", t)
    return t.strip()


def is_hebrew_entry(texto: str) -> bool:
    if not texto:
        return False
    # Debe tener al menos una letra hebrea y no ser predominantemente griego.
    if not HEBREW_LETTER.search(texto):
        return False
    heb = len(HEBREW_LETTER.findall(texto))
    gr = len(GREEK_LETTER.findall(texto))
    return heb >= gr


def richness(entry: dict) -> int:
    """Heurística para elegir la entrada más informativa al deduplicar."""
    return (
        len(str(entry.get("equivalencia_espanol") or ""))
        + len(str(entry.get("observacion") or "")) // 4
        + len(str(entry.get("texto_hebreo") or ""))
    )


def main() -> None:
    if not DIC_DIR.exists():
        raise SystemExit(f"No existe el directorio del diccionario: {DIC_DIR}")

    files = sorted(DIC_DIR.glob("diccionario_*.json"))
    print(f"== build_diccionario_hebreo ==")
    print(f"  fuente : {DIC_DIR}")
    print(f"  archivos: {len(files)}")

    by_key: dict[str, dict] = {}
    total_raw = 0
    skipped_greek = 0

    for fp in files:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  [warn] no se pudo leer {fp.name}: {exc}")
            continue
        if not isinstance(data, list):
            continue
        for ent in data:
            if not isinstance(ent, dict):
                continue
            total_raw += 1
            texto = str(ent.get("texto_hebreo") or "").strip()
            if not is_hebrew_entry(texto):
                skipped_greek += 1
                continue
            key = vowel_key(texto)
            if not key:
                continue
            out = {
                "clave": key,
                "clave_consonantal": clean_consonants(texto),
                "texto_hebreo": texto,
                "transliteracion": str(ent.get("transliteracion") or "").strip(),
                "equivalencia_espanol": str(ent.get("equivalencia_espanol") or "").strip(),
                "observacion": str(ent.get("observacion") or "").strip(),
                "fuentes": [fp.stem.replace("diccionario_", "")],
            }
            prev = by_key.get(key)
            if prev is None:
                by_key[key] = out
            else:
                # Mezcla fuentes y conserva la entrada más rica.
                fuentes = sorted(set(prev["fuentes"]) | set(out["fuentes"]))
                winner = out if richness(out) > richness(prev) else prev
                winner = dict(winner)
                winner["fuentes"] = fuentes
                by_key[key] = winner

    # Orden alfabético hebreo por la forma consonántica.
    entries = sorted(by_key.values(), key=lambda e: e["clave"])
    for i, e in enumerate(entries, start=1):
        e["id"] = i

    payload = {
        "_schema": "diccionario-hebreo-v1",
        "_source": "dic/Diccionarioboton",
        "total_entradas": len(entries),
        "entradas": entries,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"  entradas crudas       : {total_raw}")
    print(f"  descartadas (no-hebreo): {skipped_greek}")
    print(f"  hebreas únicas        : {len(entries)}")
    print(f"  → {OUT_PATH}  ({OUT_PATH.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
