"""Reglas gramaticales del hebreo — sistema global para capítulos no protegidos.

Pipeline de reglas:
    1.2  Divisiones de palabras (artículos, prefijos, sufijos)
    1.2b Maqaf (posicionamiento correcto)
    1.3  Texto completo (sin omisiones de palabras hebreas)
    1.4  Palabras especiales del hebreo
    1.5  Vocalizaciones y puntos masoréticos
    1.6  Revisión general de reglas gramaticales

Solo afecta a capítulos NO protegidos (>= 16 en Génesis).
Los capítulos 1-15, ya cerrados, no son modificados.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from gen_chapter_scope import is_protected, is_rules_target
from hebrew_clean import (
    MAQAF,
    has_leading_maqaf,
    has_trailing_maqaf,
    ensure_trailing_maqaf,
    strip_leading_maqaf,
    strip_trailing_maqaf,
    normalize_verse_maqaf,
    sanitize_verse_he_forms,
    is_meta_raw,
)

# ── Constantes ────────────────────────────────────────────────────────────

HE_LETTER = re.compile(r"[\u05D0-\u05EA]")
NIQQUD_RANGE = re.compile(r"[\u0591-\u05C7\u05BC\u05C1\u05C2\u05BD]")
CANTILLATION = re.compile(r"[\u0591-\u05AF]")

CONJ_VAV_FORMS = frozenset({"וַ", "וְ", "וּ", "וִ", "וָ", "וֹ"})

# Prefijos hebreos válidos (artículo, preposiciones inseparables, conjunción)
VALID_PREFIX_MORPHS = frozenset({
    "ART", "CONJ", "PREP", "PART.OBJ.DIR", "INTG",
})

# Morfologías de prefijo que DEBEN corresponder a un solo carácter hebreo base
SINGLE_CHAR_PREFIX_MORPHS = frozenset({"ART", "CONJ"})


# ── Utilidades ────────────────────────────────────────────────────────────

def _he_consonants(s: str) -> str:
    """Extrae solo consonantes hebreas (sin niqqud, cantillation, maqaf)."""
    return NIQQUD_RANGE.sub("", (s or "")).replace("־", "").replace("-", "").strip()


def _has_hebrew(s: str) -> bool:
    return bool(s and HE_LETTER.search(s))


def _is_empty_hw(hw: dict) -> bool:
    """True si el hw no aporta ningún token hebreo real."""
    hf = (hw.get("he_form") or "").strip()
    pf = hw.get("prefix_forms") or []
    prs = (hw.get("prs_suffix") or {}).get("he_form", "")
    return not hf and not pf and not prs


# ── Estadísticas de ejecución ─────────────────────────────────────────────

class RuleStats:
    """Acumula contadores de cada regla aplicada."""
    def __init__(self):
        self.counts: dict[str, int] = {}

    def inc(self, rule: str, n: int = 1):
        self.counts[rule] = self.counts.get(rule, 0) + n

    def report(self) -> str:
        if not self.counts:
            return "  (sin cambios)"
        lines = []
        for k, v in sorted(self.counts.items()):
            lines.append(f"    {k:<40}: {v}")
        return "\n".join(lines)

    def total(self) -> int:
        return sum(self.counts.values())


# ═══════════════════════════════════════════════════════════════════════════
# PASO 1.2 — Divisiones de palabras: artículos, prefijos, sufijos
# ═══════════════════════════════════════════════════════════════════════════

def _rule_1_2_prefix_array_alignment(hw: dict, stats: RuleStats) -> None:
    """prefix_morphs y prefix_es deben tener la misma longitud que prefix_forms."""
    pf = hw.get("prefix_forms") or []
    if not pf:
        return
    n = len(pf)
    for key, default in (("prefix_morphs", ""), ("prefix_es", "")):
        arr = hw.get(key)
        if not isinstance(arr, list):
            continue
        if len(arr) != n:
            hw[key] = (list(arr) + [default] * n)[:n]
            stats.inc("1.2_prefix_array_aligned")


def _rule_1_2_empty_prefix_cleanup(hw: dict, stats: RuleStats) -> None:
    """Prefijos sin contenido hebreo real deben eliminarse."""
    pf = hw.get("prefix_forms") or []
    if not pf:
        return
    pm = hw.get("prefix_morphs") or []
    pe = hw.get("prefix_es") or []

    clean_f, clean_m, clean_e = [], [], []
    removed = 0
    for i, f in enumerate(pf):
        cons = _he_consonants(f)
        if not cons:
            removed += 1
            continue
        clean_f.append(f)
        clean_m.append(pm[i] if i < len(pm) else "")
        clean_e.append(pe[i] if i < len(pe) else "")

    if removed:
        if clean_f:
            hw["prefix_forms"] = clean_f
            hw["prefix_morphs"] = clean_m
            hw["prefix_es"] = clean_e
        else:
            hw.pop("prefix_forms", None)
            hw.pop("prefix_morphs", None)
            hw.pop("prefix_es", None)
        stats.inc("1.2_empty_prefix_removed", removed)


def _rule_1_2_w_prefix_ensure(hw: dict, stats: RuleStats) -> None:
    """raw que empieza con W/ debe tener וַ/וְ/וּ en prefix_forms[0]."""
    raw = hw.get("raw") or ""
    if not raw.startswith("W/"):
        return
    hf = (hw.get("he_form") or "").strip()
    if not hf:
        return
    pf = hw.get("prefix_forms") or []
    if pf and _he_consonants(pf[0]) == "ו":
        return
    if not pf:
        hw["prefix_forms"] = ["וַ"]
        hw["prefix_morphs"] = ["CONJ"]
        hw["prefix_es"] = hw.get("prefix_es") or ["y"]
        stats.inc("1.2_w_prefix_added")
    elif _he_consonants(pf[0]) != "ו":
        hw["prefix_forms"] = ["וַ"] + pf
        hw["prefix_morphs"] = ["CONJ"] + (hw.get("prefix_morphs") or [])
        hw["prefix_es"] = ["y"] + (hw.get("prefix_es") or [])
        stats.inc("1.2_w_prefix_prepended")


def _rule_1_2_article_prefix(hw: dict, stats: RuleStats) -> None:
    """raw con H/ interior debe tener הַ como prefijo ART."""
    raw = hw.get("raw") or ""
    parts = raw.split("/")
    if len(parts) < 2:
        return
    if "H" not in parts[:-1]:
        return
    h_idx = next((i for i, p in enumerate(parts[:-1]) if p == "H"), None)
    if h_idx is None:
        return
    pf = hw.get("prefix_forms") or []
    pm = hw.get("prefix_morphs") or []
    has_art = any(
        _he_consonants(pf[i]) == "ה" and (pm[i] if i < len(pm) else "") == "ART"
        for i in range(len(pf))
    )
    if has_art:
        return
    has_he_prefix = any(_he_consonants(f) == "ה" for f in pf)
    if has_he_prefix:
        for i, f in enumerate(pf):
            if _he_consonants(f) == "ה" and i < len(pm):
                if pm[i] != "ART":
                    pm[i] = "ART"
                    stats.inc("1.2_article_morph_fixed")
                break


def apply_1_2_word_divisions(verse: dict, stats: RuleStats) -> None:
    """Paso 1.2: reglas de divisiones de palabras."""
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if is_meta_raw(hw.get("raw") or ""):
                continue
            _rule_1_2_prefix_array_alignment(hw, stats)
            _rule_1_2_empty_prefix_cleanup(hw, stats)
            _rule_1_2_w_prefix_ensure(hw, stats)
            _rule_1_2_article_prefix(hw, stats)


# ═══════════════════════════════════════════════════════════════════════════
# PASO 1.2b — Maqaf: posicionamiento correcto
# ═══════════════════════════════════════════════════════════════════════════

def _rule_1_2b_leading_maqaf(verse: dict, stats: RuleStats) -> None:
    """Maqaf inicial en he_form debe moverse al token anterior como trailing."""
    prev = None
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            raw = hw.get("raw") or ""
            if is_meta_raw(raw):
                prev = hw
                continue
            he = hw.get("he_form") or ""
            if has_leading_maqaf(he):
                core = strip_leading_maqaf(he)
                if he != core:
                    hw["he_form"] = core
                    stats.inc("1.2b_leading_maqaf_stripped")
                if prev and not is_meta_raw(prev.get("raw") or ""):
                    prev_he = prev.get("he_form") or ""
                    if prev_he and not has_trailing_maqaf(prev_he):
                        prev["he_form"] = ensure_trailing_maqaf(prev_he)
                        stats.inc("1.2b_trailing_maqaf_added")
            prev = hw


def apply_1_2b_maqaf(verse: dict, stats: RuleStats) -> None:
    """Paso 1.2b: normalización de maqaf."""
    _rule_1_2b_leading_maqaf(verse, stats)


# ═══════════════════════════════════════════════════════════════════════════
# PASO 1.3 — Texto completo: no omitir palabras hebreas
# ═══════════════════════════════════════════════════════════════════════════

def _rule_1_3_stem_not_empty(hw: dict, ref: str, stats: RuleStats) -> None:
    """Un hw con prefijos o PRS pero sin he_form es sospechoso."""
    hf = (hw.get("he_form") or "").strip()
    pf = hw.get("prefix_forms") or []
    prs = (hw.get("prs_suffix") or {}).get("he_form", "")
    raw = hw.get("raw") or ""
    if is_meta_raw(raw) or raw == "GKADD":
        return
    if not hf and (pf or prs):
        stats.inc("1.3_stem_empty_with_affixes")


def _rule_1_3_no_ascii_in_hebrew(hw: dict, stats: RuleStats) -> None:
    """he_form no debe contener letras ASCII mezcladas con hebreo."""
    hf = hw.get("he_form") or ""
    if not hf:
        return
    has_he = HE_LETTER.search(hf)
    has_ascii = re.search(r"[a-zA-Z]", hf)
    if has_he and has_ascii:
        stats.inc("1.3_ascii_in_hebrew_form")


def apply_1_3_completeness(verse: dict, stats: RuleStats) -> None:
    """Paso 1.3: verificar completitud del texto hebreo."""
    ref = f"{verse.get('chapter', '?')}:{verse.get('verse', '?')}"
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            _rule_1_3_stem_not_empty(hw, ref, stats)
            _rule_1_3_no_ascii_in_hebrew(hw, stats)


# ═══════════════════════════════════════════════════════════════════════════
# PASO 1.4 — Palabras especiales del hebreo
# ═══════════════════════════════════════════════════════════════════════════

# Tetragrama YHWH — vocalizaciones aceptables
YHWH_CONSONANTS = "יהוה"
YHWH_ACCEPTABLE = frozenset({
    "יְהוָה", "יְהוָ֗ה", "יְהֹוָה", "יהוה",
})

def _rule_1_4_yhwh_consistency(hw: dict, stats: RuleStats) -> None:
    """YHWH debe tener consonantes correctas y Strong H3068/H3069."""
    raw = hw.get("raw") or ""
    if raw not in ("YHWH", "W/YHWH", "L/YHWH", "B/YHWH"):
        return
    hf = hw.get("he_form") or ""
    cons = _he_consonants(hf)
    if cons and cons != YHWH_CONSONANTS:
        stats.inc("1.4_yhwh_consonants_wrong")
    strongs = hw.get("strongs") or ""
    if strongs and strongs not in ("H3068", "H3069"):
        stats.inc("1.4_yhwh_strongs_wrong")


def apply_1_4_special_words(verse: dict, stats: RuleStats) -> None:
    """Paso 1.4: verificar palabras especiales."""
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            _rule_1_4_yhwh_consistency(hw, stats)


# ═══════════════════════════════════════════════════════════════════════════
# PASO 1.5 — Vocalizaciones y puntos masoréticos
# ═══════════════════════════════════════════════════════════════════════════

def _rule_1_5_encoding_artifacts(hw: dict, stats: RuleStats) -> None:
    """Detectar artefactos de encoding (i>( prefix) en formas hebreas."""
    for field in ("he_form",):
        val = hw.get(field) or ""
        if "i>(" in val:
            stats.inc("1.5_encoding_artifact")
    for pf in (hw.get("prefix_forms") or []):
        if "i>(" in pf:
            stats.inc("1.5_encoding_artifact_prefix")
    prs_hf = (hw.get("prs_suffix") or {}).get("he_form", "")
    if "i>(" in prs_hf:
        stats.inc("1.5_encoding_artifact_prs")


def _rule_1_5_dagesh_without_letter(hw: dict, stats: RuleStats) -> None:
    """Dagesh (U+05BC) sin letra hebrea precedente es sospechoso."""
    hf = hw.get("he_form") or ""
    if not hf:
        return
    for i, ch in enumerate(hf):
        if ch == "\u05BC" and (i == 0 or not HE_LETTER.match(hf[i - 1])):
            stats.inc("1.5_dagesh_orphan")
            break


def apply_1_5_vocalization(verse: dict, stats: RuleStats) -> None:
    """Paso 1.5: verificar vocalizaciones y puntos masoréticos."""
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            _rule_1_5_encoding_artifacts(hw, stats)
            _rule_1_5_dagesh_without_letter(hw, stats)


# ═══════════════════════════════════════════════════════════════════════════
# PASO 1.6 — Revisión general de reglas gramaticales
# ═══════════════════════════════════════════════════════════════════════════

def _rule_1_6_prs_suffix_structure(hw: dict, stats: RuleStats) -> None:
    """prs_suffix debe ser un dict con he_form y he_morph si existe."""
    prs = hw.get("prs_suffix")
    if prs is None:
        return
    if not isinstance(prs, dict):
        stats.inc("1.6_prs_not_dict")
        return
    if not prs.get("he_form"):
        stats.inc("1.6_prs_empty_he_form")
    if not prs.get("he_morph"):
        stats.inc("1.6_prs_empty_he_morph")


def _rule_1_6_morph_present(hw: dict, stats: RuleStats) -> None:
    """he_form no vacío debería tener he_morph."""
    hf = (hw.get("he_form") or "").strip()
    if not hf:
        return
    raw = hw.get("raw") or ""
    if is_meta_raw(raw) or raw == "GKADD":
        return
    morph = (hw.get("he_morph") or "").strip()
    if not morph:
        stats.inc("1.6_morph_missing")


def apply_1_6_general_grammar(verse: dict, stats: RuleStats) -> None:
    """Paso 1.6: reglas gramaticales generales."""
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            _rule_1_6_prs_suffix_structure(hw, stats)
            _rule_1_6_morph_present(hw, stats)


# ═══════════════════════════════════════════════════════════════════════════
# PIPELINE PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════

ALL_STEPS = [
    ("1.2  Divisiones de palabras", apply_1_2_word_divisions),
    ("1.2b Maqaf", apply_1_2b_maqaf),
    ("1.3  Texto completo", apply_1_3_completeness),
    ("1.4  Palabras especiales", apply_1_4_special_words),
    ("1.5  Vocalizaciones", apply_1_5_vocalization),
    ("1.6  Gramática general", apply_1_6_general_grammar),
]


def apply_hebrew_rules(
    data: dict,
    *,
    book: str = "genesis",
    steps: list[str] | None = None,
    dry_run: bool = False,
    verbose: bool = True,
) -> RuleStats:
    """Ejecuta las reglas hebreas sobre todos los versículos no protegidos.

    Args:
        data: JSON del libro (con "verses")
        book: slug del libro
        steps: lista de pasos a ejecutar (None = todos). Ej: ["1.2", "1.2b"]
        dry_run: si True, solo reporta sin modificar
        verbose: imprimir reporte a stdout
    """
    stats = RuleStats()
    target_verses = []

    for v in data.get("verses", []):
        ch = v.get("chapter", 0)
        if not is_rules_target(ch, book):
            continue
        target_verses.append(v)

    if verbose:
        total_verses = len(data.get("verses", []))
        protected = total_verses - len(target_verses)
        sys.stdout.write(
            f"\n== Reglas hebreas ({book}) ==\n"
            f"   Versículos totales  : {total_verses}\n"
            f"   Protegidos (skip)   : {protected}\n"
            f"   Candidatos          : {len(target_verses)}\n"
        )
        if dry_run:
            sys.stdout.write("   MODO: dry_run (solo reporte)\n")
        sys.stdout.write("\n")

    for label, fn in ALL_STEPS:
        step_id = label.split()[0]
        if steps and step_id not in steps:
            continue
        step_stats = RuleStats()
        for v in target_verses:
            fn(v, step_stats)
        if verbose and step_stats.total():
            sys.stdout.write(f"  {label}:\n{step_stats.report()}\n\n")
        for k, v_count in step_stats.counts.items():
            stats.inc(k, v_count)

    if verbose:
        sys.stdout.write(f"  TOTAL cambios/hallazgos: {stats.total()}\n")

    return stats


# ═══════════════════════════════════════════════════════════════════════════
# CLI — uso independiente
# ═══════════════════════════════════════════════════════════════════════════

def main():
    import argparse
    import json

    sys.stdout.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser(description="Reglas gramaticales del hebreo")
    ap.add_argument("--book", default="genesis")
    ap.add_argument("--steps", nargs="*", help="Pasos a ejecutar (ej: 1.2 1.2b)")
    ap.add_argument("--dry-run", action="store_true", help="Solo reportar, no modificar")
    ap.add_argument("--save", action="store_true", help="Guardar cambios en JSON")
    args = ap.parse_args()

    from book_config import resolve
    cfg = resolve(args.book)

    data = json.loads(cfg.final_json_path.read_text(encoding="utf-8"))
    stats = apply_hebrew_rules(
        data,
        book=args.book,
        steps=args.steps,
        dry_run=args.dry_run,
    )

    if args.save and not args.dry_run and stats.total() > 0:
        cfg.final_json_path.write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        sys.stdout.write(f"\n  Guardado: {cfg.final_json_path.name}\n")
    elif not args.save:
        sys.stdout.write("\n  (use --save para guardar cambios)\n")


if __name__ == "__main__":
    main()
