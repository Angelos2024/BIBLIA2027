"""Reglas de morfología — sistema global para capítulos no protegidos.

Pipeline de reglas:
    2.1  Morfologías alineadas (arrays paralelos, morph presente cuando form presente)
    2.2  CATSS/OSHB estructura correcta (morph tags válidos, prefijos legítimos)
    2.3  Morfologías compuestas (PREP+PRS, PART.OBJ.DIR+PRS) preservadas

Solo afecta a capítulos NO protegidos (>= 16 en Génesis).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from gen_chapter_scope import is_rules_target
from hebrew_clean import is_meta_raw

# ── Constantes morfológicas ──────────────────────────────────────────────

# Morfologías válidas para slots de prefijo (tipo base antes del primer punto)
VALID_PREFIX_BASES = frozenset({
    "CONJ", "PREP", "ART", "PART", "NEG", "REL", "INTG", "SUF",
})

# PRS morph patterns (sufijos pronominales)
PRS_PATTERN = re.compile(r"^PRS\.")

# Compound morph patterns que deben preservarse
COMPOUND_PATTERN = re.compile(r"^(PREP|PART\.OBJ\.DIR|SUBS|CONJ|ADV)\+PRS\.")

# Morph tags válidos de OSHB (primera parte antes del punto)
OSHB_MORPH_ROOTS = frozenset({
    "VERBO", "SUBS", "NPROP", "PREP", "CONJ", "ART", "ADV", "ADJ",
    "PRON", "PRS", "PART", "NUM", "NEG", "REL", "INTG", "SUF",
    "GENT",   # gentilicio
    "INTJ",   # interjección
    "INTERROG",  # interrogativo (variante)
})

# Códigos OSHB cortos no expandidos por normalize_morph (2-5 chars, mayúsc.)
# Ej: AMSA = adj masc sg abs, CFSA = construct fem sg abs, RBPM3 = verb ...
# Se tratan como válidos pero idealmente deberían expandirse.
OSHB_SHORT_CODE = re.compile(r"^[A-Z][A-Za-z0-9]{1,8}$")

# Stems verbales válidos
VERB_STEMS = frozenset({
    "QAL", "NIF", "HIF", "HOF", "HITPA", "PIL", "PILP",
    "HIFIL", "NIFAL", "PIEL", "PUAL", "HITPAEL",
})

# Género/número válidos
GENDER = frozenset({"M", "F", "BOTH", "COMMON"})
NUMBER = frozenset({"SG", "PL", "DU"})
STATE = frozenset({"A", "C", "ABS"})  # absoluto, constructo
PERSON = frozenset({"P1", "P2", "P3"})

HE_LETTER = re.compile(r"[\u05D0-\u05EA]")
NIQQUD_RANGE = re.compile(r"[\u0591-\u05C7\u05BC\u05C1\u05C2\u05BD]")


def _he_consonants(s: str) -> str:
    return NIQQUD_RANGE.sub("", (s or "")).replace("־", "").replace("-", "").strip()


# ── Estadísticas ─────────────────────────────────────────────────────────

class RuleStats:
    def __init__(self):
        self.counts: dict[str, int] = {}
        self.details: dict[str, list[str]] = {}

    def inc(self, rule: str, n: int = 1, detail: str = ""):
        self.counts[rule] = self.counts.get(rule, 0) + n
        if detail:
            self.details.setdefault(rule, []).append(detail)

    def report(self, show_details: int = 0) -> str:
        if not self.counts:
            return "  (sin cambios)"
        lines = []
        for k, v in sorted(self.counts.items()):
            lines.append(f"    {k:<50}: {v}")
            if show_details and k in self.details:
                for d in self.details[k][:show_details]:
                    lines.append(f"      -> {d}")
                if len(self.details[k]) > show_details:
                    lines.append(f"      ... {len(self.details[k]) - show_details} more")
        return "\n".join(lines)

    def total(self) -> int:
        return sum(self.counts.values())


# ═══════════════════════════════════════════════════════════════════════════
# PASO 2.1 — Morfologías alineadas (no desfasadas)
# ═══════════════════════════════════════════════════════════════════════════

def _rule_2_1_prefix_array_length(hw: dict, ref: str, stats: RuleStats) -> None:
    """prefix_forms y prefix_morphs deben tener la misma longitud."""
    pf = hw.get("prefix_forms") or []
    pm = hw.get("prefix_morphs") or []
    pe = hw.get("prefix_es") or []
    raw = hw.get("raw") or ""

    if not pf and not pm:
        return

    if len(pf) != len(pm):
        stats.inc("2.1_pfx_array_misaligned",
                  detail=f"{ref} raw={raw!r} forms={len(pf)} morphs={len(pm)}")
        # Fix: truncate or pad
        n = len(pf)
        if n == 0:
            hw.pop("prefix_morphs", None)
            hw.pop("prefix_es", None)
        else:
            hw["prefix_morphs"] = (list(pm) + [""] * n)[:n]
            if pe:
                hw["prefix_es"] = (list(pe) + [""] * n)[:n]

    if pf and pe and len(pf) != len(pe):
        n = len(pf)
        hw["prefix_es"] = (list(pe) + [""] * n)[:n]
        stats.inc("2.1_pfx_es_array_fixed")


def _rule_2_1_morph_present_when_form(hw: dict, ref: str, stats: RuleStats) -> None:
    """he_form no vacío debe tener he_morph; prs_suffix.he_form debe tener .he_morph."""
    raw = hw.get("raw") or ""
    if is_meta_raw(raw) or raw == "GKADD":
        return

    hf = (hw.get("he_form") or "").strip()
    hm = (hw.get("he_morph") or "").strip()
    if hf and not hm:
        stats.inc("2.1_stem_morph_missing",
                  detail=f"{ref} raw={raw!r} hf={hf!r}")

    prs = hw.get("prs_suffix")
    if isinstance(prs, dict):
        prs_hf = (prs.get("he_form") or "").strip()
        prs_hm = (prs.get("he_morph") or "").strip()
        if prs_hf and not prs_hm:
            stats.inc("2.1_prs_morph_missing",
                      detail=f"{ref} raw={raw!r} prs_hf={prs_hf!r}")


def _rule_2_1_gkadd_cleanup(hw: dict, ref: str, stats: RuleStats) -> None:
    """GKADD no debe tener prefix_morphs huérfanos sin prefix_forms."""
    raw = hw.get("raw") or ""
    if raw != "GKADD":
        return
    pf = hw.get("prefix_forms") or []
    pm = hw.get("prefix_morphs") or []
    if pm and not pf:
        hw.pop("prefix_morphs", None)
        hw.pop("prefix_es", None)
        stats.inc("2.1_gkadd_orphan_morphs_cleaned")


def apply_2_1_morph_alignment(verse: dict, stats: RuleStats) -> None:
    """Paso 2.1: asegurar alineación de morfologías."""
    ref = f"{verse.get('chapter', '?')}:{verse.get('verse', '?')}"
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            _rule_2_1_gkadd_cleanup(hw, ref, stats)
            _rule_2_1_prefix_array_length(hw, ref, stats)
            _rule_2_1_morph_present_when_form(hw, ref, stats)


# ═══════════════════════════════════════════════════════════════════════════
# PASO 2.2 — CATSS/OSHB estructura correcta
# ═══════════════════════════════════════════════════════════════════════════

def _is_valid_prefix_morph(morph: str) -> bool:
    """True si el morph es un tipo legítimo de prefijo hebreo."""
    if not morph:
        return True
    base = morph.split(".")[0]
    if base in VALID_PREFIX_BASES:
        return True
    if morph.startswith("PREP"):
        return True
    return False


def _rule_2_2_bogus_prefix_morph(hw: dict, ref: str, stats: RuleStats) -> None:
    """Detectar morfologías en prefix_morphs que no son tipos de prefijo."""
    pm = hw.get("prefix_morphs") or []
    pf = hw.get("prefix_forms") or []
    raw = hw.get("raw") or ""

    for i, m in enumerate(pm):
        if not m:
            continue
        if _is_valid_prefix_morph(m):
            continue
        f = pf[i] if i < len(pf) else "?"
        if PRS_PATTERN.match(m):
            stats.inc("2.2_prs_in_prefix_slot",
                      detail=f"{ref} raw={raw!r} slot={i} morph={m!r} form={f!r}")
        elif m.startswith("SUBS"):
            stats.inc("2.2_subs_in_prefix_slot",
                      detail=f"{ref} raw={raw!r} slot={i} morph={m!r} form={f!r}")
        elif m.startswith("NPROP"):
            stats.inc("2.2_nprop_in_prefix_slot",
                      detail=f"{ref} raw={raw!r} slot={i} morph={m!r} form={f!r}")
        elif m.startswith("VERBO"):
            stats.inc("2.2_verb_in_prefix_slot",
                      detail=f"{ref} raw={raw!r} slot={i} morph={m!r} form={f!r}")
        elif m.startswith("ADV") or m.startswith("ADJ"):
            stats.inc("2.2_adv_adj_in_prefix_slot",
                      detail=f"{ref} raw={raw!r} slot={i} morph={m!r} form={f!r}")
        elif m.startswith("PRON"):
            stats.inc("2.2_pron_in_prefix_slot",
                      detail=f"{ref} raw={raw!r} slot={i} morph={m!r} form={f!r}")
        elif m.startswith("NUM"):
            stats.inc("2.2_num_in_prefix_slot",
                      detail=f"{ref} raw={raw!r} slot={i} morph={m!r} form={f!r}")
        else:
            stats.inc("2.2_unknown_prefix_morph",
                      detail=f"{ref} raw={raw!r} slot={i} morph={m!r} form={f!r}")


def _rule_2_2_morph_tag_valid(hw: dict, ref: str, stats: RuleStats) -> None:
    """Verificar que he_morph sea un tag OSHB reconocido."""
    hm = (hw.get("he_morph") or "").strip()
    if not hm:
        return
    raw = hw.get("raw") or ""
    if is_meta_raw(raw):
        return

    # Compound morphs con + son OK si ambos lados son válidos
    if "+" in hm:
        return  # validated in 2.3

    root = hm.split(".")[0]
    if root not in OSHB_MORPH_ROOTS:
        if OSHB_SHORT_CODE.match(hm):
            stats.inc("2.2_oshb_short_code_unexpanded",
                      detail=f"{ref} raw={raw!r} morph={hm!r}")
        else:
            stats.inc("2.2_unknown_morph_root",
                      detail=f"{ref} raw={raw!r} morph={hm!r}")


def _rule_2_2_prs_morph_format(hw: dict, ref: str, stats: RuleStats) -> None:
    """prs_suffix.he_morph debe empezar con PRS. o SUF."""
    prs = hw.get("prs_suffix")
    if not isinstance(prs, dict):
        return
    prs_hm = (prs.get("he_morph") or "").strip()
    if not prs_hm:
        return
    raw = hw.get("raw") or ""
    if not prs_hm.startswith("PRS.") and not prs_hm.startswith("SUF."):
        # Some valid cases: CONJ, PART.INTERR in prs_suffix (rare edge cases from merge)
        if prs_hm in ("CONJ", "PART.INTERR"):
            stats.inc("2.2_prs_morph_non_prs_valid",
                      detail=f"{ref} raw={raw!r} prs_morph={prs_hm!r}")
        else:
            stats.inc("2.2_prs_morph_invalid_format",
                      detail=f"{ref} raw={raw!r} prs_morph={prs_hm!r}")


def apply_2_2_catss_oshb_structure(verse: dict, stats: RuleStats) -> None:
    """Paso 2.2: validar estructura CATSS/OSHB de morfologías."""
    ref = f"{verse.get('chapter', '?')}:{verse.get('verse', '?')}"
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if is_meta_raw(hw.get("raw") or ""):
                continue
            _rule_2_2_bogus_prefix_morph(hw, ref, stats)
            _rule_2_2_morph_tag_valid(hw, ref, stats)
            _rule_2_2_prs_morph_format(hw, ref, stats)


# ═══════════════════════════════════════════════════════════════════════════
# PASO 2.3 — Morfologías compuestas (uniones preservadas)
# ═══════════════════════════════════════════════════════════════════════════

def _parse_compound_morph(hm: str) -> list[str]:
    """Separa un morph compuesto en sus partes: 'PREP+PRS.P3.M.SG' -> ['PREP', 'PRS.P3.M.SG']."""
    return hm.split("+") if "+" in hm else [hm]


def _rule_2_3_compound_valid(hw: dict, ref: str, stats: RuleStats) -> None:
    """Verificar que morfologías compuestas tengan partes válidas."""
    hm = (hw.get("he_morph") or "").strip()
    if "+" not in hm:
        return
    raw = hw.get("raw") or ""

    parts = _parse_compound_morph(hm)
    for part in parts:
        root = part.split(".")[0]
        if root not in OSHB_MORPH_ROOTS:
            stats.inc("2.3_compound_invalid_part",
                      detail=f"{ref} raw={raw!r} morph={hm!r} bad_part={part!r}")
            return

    # Verify compound coherence: if has +PRS, should have prs_suffix OR be a fused token
    if "+PRS" in hm:
        prs = hw.get("prs_suffix")
        hf = (hw.get("he_form") or "").strip()
        if prs and (prs.get("he_form") or "").strip():
            # Has both compound morph AND separate prs_suffix — potential double-count
            stats.inc("2.3_compound_plus_prs_suffix",
                      detail=f"{ref} raw={raw!r} morph={hm!r} prs_hf={prs.get('he_form')!r}")
        else:
            stats.inc("2.3_compound_fused_ok")


def _rule_2_3_split_should_have_compound(hw: dict, ref: str, stats: RuleStats) -> None:
    """Si he_morph es PREP simple pero tiene prs_suffix, debería ser PREP+PRS o el PRS debería estar separado."""
    hm = (hw.get("he_morph") or "").strip()
    prs = hw.get("prs_suffix")
    if not isinstance(prs, dict):
        return
    prs_hf = (prs.get("he_form") or "").strip()
    if not prs_hf:
        return

    raw = hw.get("raw") or ""

    # Si el morph ya es compuesto, está bien
    if "+" in hm:
        return

    # Si es PREP o PART.OBJ.DIR con PRS, la convención es:
    # - morph simple en he_morph (PREP, PART.OBJ.DIR)
    # - PRS en prs_suffix.he_morph
    # Esto es CORRECTO cuando están separados
    if hm in ("PREP", "PART.OBJ.DIR"):
        prs_hm = (prs.get("he_morph") or "").strip()
        if prs_hm and prs_hm.startswith("PRS."):
            stats.inc("2.3_proper_split_prep_prs")
        elif prs_hm:
            stats.inc("2.3_prep_with_non_prs_suffix",
                      detail=f"{ref} raw={raw!r} morph={hm!r} prs_morph={prs_hm!r}")


def apply_2_3_compound_morphs(verse: dict, stats: RuleStats) -> None:
    """Paso 2.3: verificar y preservar morfologías compuestas."""
    ref = f"{verse.get('chapter', '?')}:{verse.get('verse', '?')}"
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if is_meta_raw(hw.get("raw") or ""):
                continue
            _rule_2_3_compound_valid(hw, ref, stats)
            _rule_2_3_split_should_have_compound(hw, ref, stats)


# ═══════════════════════════════════════════════════════════════════════════
# PIPELINE PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════

ALL_STEPS = [
    ("2.1  Morfologías alineadas", apply_2_1_morph_alignment),
    ("2.2  CATSS/OSHB estructura", apply_2_2_catss_oshb_structure),
    ("2.3  Morfologías compuestas", apply_2_3_compound_morphs),
]


def apply_morph_rules(
    data: dict,
    *,
    book: str = "genesis",
    steps: list[str] | None = None,
    dry_run: bool = False,
    verbose: bool = True,
    show_details: int = 5,
) -> RuleStats:
    """Ejecuta las reglas de morfología sobre versículos no protegidos."""
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
            f"\n== Reglas de morfología ({book}) ==\n"
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
            sys.stdout.write(f"  {label}:\n{step_stats.report(show_details)}\n\n")
        for k, v_count in step_stats.counts.items():
            stats.inc(k, v_count)

    if verbose:
        sys.stdout.write(f"  TOTAL hallazgos: {stats.total()}\n")

    return stats


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def main():
    import argparse
    import json

    sys.stdout.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser(description="Reglas de morfología")
    ap.add_argument("--book", default="genesis")
    ap.add_argument("--steps", nargs="*", help="Pasos: 2.1 2.2 2.3")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--details", type=int, default=5, help="Ejemplos por regla")
    args = ap.parse_args()

    from book_config import resolve
    cfg = resolve(args.book)

    data = json.loads(cfg.final_json_path.read_text(encoding="utf-8"))
    stats = apply_morph_rules(
        data,
        book=args.book,
        steps=args.steps,
        dry_run=args.dry_run,
        show_details=args.details,
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
