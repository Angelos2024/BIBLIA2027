"""Reglas del Griego LXX — sistema global para capítulos no protegidos.

Pipeline de reglas:
    4.1  Griego completo sin omisiones de la fuente original LXX
    4.2  Palabras ADD+ (gk_add) con equivalencias hebreo completadas
    4.3  Omisiones LXX — vacíos correctos en hebreo por token
    4.4  Tokens con >1 palabra griega — orden correcto
    4.5  Griego LXX limpio — sin basura/residuos mal extraídos

Solo afecta a capítulos NO protegidos (>= 16 en Génesis).
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from typing import Any

from gen_chapter_scope import is_rules_target
from hebrew_clean import is_meta_raw

# ── Constantes ────────────────────────────────────────────────────────────

GR_LETTER = re.compile(r"[\u0370-\u03FF\u1F00-\u1FFF]")
HE_LETTER = re.compile(r"[\u05D0-\u05EA]")
NIQQUD    = re.compile(r"[\u0591-\u05C7]")

BETA_CODE_RE = re.compile(r"[A-Z]{2,}[/)(\\=|+]")
LONE_DIACRITICS = re.compile(r"^[\u0300-\u036F\u0342\u0345]+$")
ASCII_GARBAGE_RE = re.compile(r"[a-zA-Z0-9]{2,}")

_META_RAW_PREFIX = ("=", "{", "<", "*", "--", ".$")

GKADD_RAWS = frozenset({"GKADD", "=<LXX>"})

GR_ARTICLES = frozenset({
    "ὁ", "ἡ", "τό", "τοῦ", "τῆς", "τῷ", "τῇ", "τόν", "τήν",
    "οἱ", "αἱ", "τά", "τῶν", "τοῖς", "ταῖς", "τούς", "τάς",
})

GR_CONJ_PARTICLES = frozenset({
    "καί", "δέ", "τε", "ἀλλά", "ἤ", "γάρ", "οὖν", "μέν",
    "ὅτι", "εἰ", "ἐάν", "ἵνα", "ὡς", "ὥστε", "μή", "οὐ", "οὐκ", "οὐχ",
})

GR_PREPS = frozenset({
    "ἐν", "ἐπί", "εἰς", "ἐκ", "ἐξ", "ἀπό", "πρός", "μετά",
    "διά", "ὑπέρ", "ὑπό", "κατά", "παρά", "περί", "πρό", "σύν", "ἀντί",
})


# ── Utilidades ────────────────────────────────────────────────────────────

def _is_meta_hw(hw: dict) -> bool:
    raw = hw.get("raw") or ""
    if raw in GKADD_RAWS:
        return False
    return raw.startswith(_META_RAW_PREFIX)


def _norm_gr(s: str) -> str:
    return (s or "").strip().replace("\u00a0", " ")


def _gr_tokens(s: str) -> list[str]:
    return [w for w in _norm_gr(s).split() if w]


def _collect_hw_gr_tokens(hw: dict) -> list[str]:
    """Recoge todos los tokens griegos asignados a un he_word."""
    tokens: list[str] = []
    for g in hw.get("prefix_gr") or []:
        for w in _gr_tokens(g):
            tokens.append(w)
    for w in _gr_tokens(hw.get("gr_word") or ""):
        tokens.append(w)
    prs_gw = (hw.get("prs_suffix") or {}).get("gr_word", "")
    for w in _gr_tokens(prs_gw):
        tokens.append(w)
    return tokens


def _pair_assigned_gr_tokens(pair: dict) -> list[str]:
    """Todos los tokens griegos asignados en el par."""
    tokens: list[str] = []
    for hw in pair.get("he_words") or []:
        if _is_meta_hw(hw):
            continue
        tokens.extend(_collect_hw_gr_tokens(hw))
    return tokens


def _gr_multiset(tokens: list[str]) -> Counter:
    """Multiset normalizado de tokens griegos."""
    return Counter(t.lower() for t in tokens if GR_LETTER.search(t))


# ── Estadísticas ──────────────────────────────────────────────────────────

class RuleStats:
    def __init__(self):
        self.counts: dict[str, int] = {}

    def inc(self, rule: str, n: int = 1):
        self.counts[rule] = self.counts.get(rule, 0) + n

    def report(self) -> str:
        if not self.counts:
            return "  (sin hallazgos)"
        lines = []
        for k, v in sorted(self.counts.items()):
            lines.append(f"    {k:<50}: {v}")
        return "\n".join(lines)

    def total(self) -> int:
        return sum(self.counts.values())


# ═══════════════════════════════════════════════════════════════════════════
# PASO 4.1 — Griego completo sin omisiones de la fuente original LXX
# ═══════════════════════════════════════════════════════════════════════════

def _rule_4_1_gr_unicode_present(pair: dict, stats: RuleStats) -> None:
    """Pares align deben tener gr_unicode no vacío."""
    kind = pair.get("kind") or "align"
    if kind != "align":
        return
    gr = _norm_gr(pair.get("gr_unicode") or "")
    if not gr:
        stats.inc("4.1_align_sin_gr_unicode")


def _rule_4_1_gr_assigned_to_hw(pair: dict, stats: RuleStats) -> None:
    """Si gr_unicode presente, al menos un hw debe tener gr_word asignado."""
    kind = pair.get("kind") or "align"
    if kind == "heb_omit":
        return
    gr = _norm_gr(pair.get("gr_unicode") or "")
    if not gr:
        return
    hws = [hw for hw in (pair.get("he_words") or []) if not _is_meta_hw(hw)]
    if not hws:
        return
    any_assigned = any(
        (hw.get("gr_word") or "").strip()
        or any(g.strip() for g in (hw.get("prefix_gr") or []))
        or ((hw.get("prs_suffix") or {}).get("gr_word") or "").strip()
        for hw in hws
    )
    if not any_assigned:
        stats.inc("4.1_gr_unicode_sin_asignar_a_hw")


def _rule_4_1_token_coverage(pair: dict, stats: RuleStats) -> None:
    """Todos los tokens de gr_unicode deben estar asignados a morpheme slots."""
    kind = pair.get("kind") or "align"
    if kind == "heb_omit":
        return
    gr = _norm_gr(pair.get("gr_unicode") or "")
    if not gr:
        return
    source = _gr_multiset(_gr_tokens(gr))
    assigned = _gr_multiset(_pair_assigned_gr_tokens(pair))
    orphan = source - assigned
    if orphan:
        stats.inc("4.1_gr_token_huerfano", sum(orphan.values()))


def apply_4_1_completeness(verse: dict, stats: RuleStats) -> None:
    for p in verse.get("pairs", []):
        _rule_4_1_gr_unicode_present(p, stats)
        _rule_4_1_gr_assigned_to_hw(p, stats)
        _rule_4_1_token_coverage(p, stats)


# ═══════════════════════════════════════════════════════════════════════════
# PASO 4.2 — Palabras ADD+ (gk_add) con equivalencias hebreo analizadas
# ═══════════════════════════════════════════════════════════════════════════

def _rule_4_2_gkadd_has_gr(pair: dict, stats: RuleStats) -> None:
    """Pares gk_add deben tener gr_unicode no vacío."""
    kind = pair.get("kind") or "align"
    if kind != "gk_add":
        return
    gr = _norm_gr(pair.get("gr_unicode") or "")
    if not gr:
        stats.inc("4.2_gk_add_sin_gr_unicode")


def _rule_4_2_gkadd_stub_present(pair: dict, stats: RuleStats) -> None:
    """gk_add con gr_unicode debe tener stub GKADD con gr_word."""
    kind = pair.get("kind") or "align"
    if kind != "gk_add":
        return
    gr = _norm_gr(pair.get("gr_unicode") or "")
    if not gr:
        return
    hws = pair.get("he_words") or []
    has_stub = any(
        (hw.get("raw") or "") in GKADD_RAWS and (hw.get("gr_word") or "").strip()
        for hw in hws
    )
    if not has_stub:
        stats.inc("4.2_gk_add_sin_stub_GKADD")


def _promote_to_gk_add(pair: dict, stats: RuleStats, *, dry_run: bool) -> None:
    """Promover un par align → gk_add y normalizar su stub GKADD."""
    gr = _norm_gr(pair.get("gr_unicode") or "")
    if not gr:
        return

    if not dry_run:
        pair["kind"] = "gk_add"

        hws = pair.get("he_words") or []
        has_gkadd_stub = any(
            (hw.get("raw") or "") in GKADD_RAWS for hw in hws
        )
        if not has_gkadd_stub:
            words = _gr_tokens(gr)
            stub: dict = {
                "raw": "GKADD",
                "he_form": "",
                "he_morph": "",
                "es_source": "patch_meta",
                "gr_source": "rule_4_2_promote",
            }
            if len(words) >= 2 and words[0] in GR_CONJ_PARTICLES:
                stub["prefix_gr"] = [words[0]]
                stub["prefix_morphs"] = ["CONJ"]
                stub["prefix_es"] = ["y"]
                stub["gr_word"] = " ".join(words[1:])
            elif len(words) >= 2 and words[0] in GR_PREPS:
                stub["prefix_gr"] = [words[0]]
                stub["prefix_morphs"] = ["PREP"]
                stub["prefix_es"] = [""]
                stub["gr_word"] = " ".join(words[1:])
            elif len(words) >= 2 and words[0] in GR_ARTICLES:
                stub["prefix_gr"] = [words[0]]
                stub["prefix_morphs"] = ["ART"]
                stub["prefix_es"] = [""]
                stub["gr_word"] = " ".join(words[1:])
            else:
                stub["gr_word"] = gr
            pair["he_words"] = [stub]
        else:
            for hw in hws:
                if (hw.get("raw") or "") in GKADD_RAWS:
                    if not (hw.get("gr_word") or "").strip():
                        hw["gr_word"] = gr
                        hw["gr_source"] = "rule_4_2_promote"


def _rule_4_2_promote_gkadd_stubs(pair: dict, stats: RuleStats,
                                   *, dry_run: bool = True) -> None:
    """CASO A: align + todos los he_words son GKADD → promover a gk_add."""
    kind = pair.get("kind") or "align"
    if kind != "align":
        return
    gr = _norm_gr(pair.get("gr_unicode") or "")
    if not gr:
        return
    hws = pair.get("he_words") or []
    if not hws:
        return
    all_gkadd = all((hw.get("raw") or "") in GKADD_RAWS for hw in hws)
    if not all_gkadd:
        return
    stats.inc("4.2_FIX_promote_align_gkadd_to_gk_add")
    _promote_to_gk_add(pair, stats, dry_run=dry_run)


def _rule_4_2_promote_empty_he(pair: dict, stats: RuleStats,
                                *, dry_run: bool = True) -> None:
    """CASO C: align + raw hebreo presente pero he_form vacío para todos → promover a gk_add."""
    kind = pair.get("kind") or "align"
    if kind != "align":
        return
    gr = _norm_gr(pair.get("gr_unicode") or "")
    if not gr:
        return
    hws = pair.get("he_words") or []
    if not hws:
        return

    has_real_he = False
    has_non_meta = False
    for hw in hws:
        raw = (hw.get("raw") or "").strip()
        if raw in GKADD_RAWS:
            continue
        if _is_meta_hw(hw):
            continue
        has_non_meta = True
        hf = (hw.get("he_form") or "").strip()
        if hf and HE_LETTER.search(hf):
            has_real_he = True
            break

    if has_non_meta and not has_real_he:
        stats.inc("4.2_FIX_promote_align_empty_he_to_gk_add")
        if not dry_run:
            pair["kind"] = "gk_add"
            for hw in hws:
                raw = (hw.get("raw") or "").strip()
                if raw not in GKADD_RAWS and not _is_meta_hw(hw):
                    hw["raw"] = "GKADD"
                    if not (hw.get("gr_word") or "").strip():
                        hw["gr_word"] = gr
                    hw["gr_source"] = "rule_4_2_promote"


def _rule_4_2_gkadd_he_fields_analyzed(pair: dict, stats: RuleStats) -> None:
    """gk_add stubs deben tener es_gloss informado."""
    kind = pair.get("kind") or "align"
    if kind != "gk_add":
        return
    for hw in pair.get("he_words") or []:
        raw = (hw.get("raw") or "").strip()
        if raw not in GKADD_RAWS:
            continue
        gw = (hw.get("gr_word") or "").strip()
        if gw and not (hw.get("es") or hw.get("es_gloss") or "").strip():
            stats.inc("4.2_gk_add_stub_sin_es_gloss")


def apply_4_2_gk_add(verse: dict, stats: RuleStats,
                      *, dry_run: bool = True) -> None:
    for p in verse.get("pairs", []):
        _rule_4_2_promote_gkadd_stubs(p, stats, dry_run=dry_run)
        _rule_4_2_promote_empty_he(p, stats, dry_run=dry_run)
        _rule_4_2_gkadd_has_gr(p, stats)
        _rule_4_2_gkadd_stub_present(p, stats)
        _rule_4_2_gkadd_he_fields_analyzed(p, stats)


# ═══════════════════════════════════════════════════════════════════════════
# PASO 4.3 — Omisiones LXX: vacíos correctos en hebreo por token
# ═══════════════════════════════════════════════════════════════════════════

def _rule_4_3_heb_omit_gr_empty(pair: dict, stats: RuleStats) -> None:
    """heb_omit pairs no deben tener griego residual en he_words."""
    kind = pair.get("kind") or "align"
    if kind != "heb_omit":
        return
    for hw in pair.get("he_words") or []:
        for field in ("gr_word",):
            val = (hw.get(field) or "").strip()
            if val and GR_LETTER.search(val):
                stats.inc("4.3_heb_omit_con_gr_residual")
        for g in hw.get("prefix_gr") or []:
            if g.strip() and GR_LETTER.search(g):
                stats.inc("4.3_heb_omit_prefix_gr_residual")


def _rule_4_3_align_empty_gr_has_he(pair: dict, stats: RuleStats) -> None:
    """Token align sin griego debe estar marcado correctamente (no confundir con omisión)."""
    kind = pair.get("kind") or "align"
    if kind != "align":
        return
    gr = _norm_gr(pair.get("gr_unicode") or "")
    if gr:
        return
    hws = [hw for hw in (pair.get("he_words") or []) if not _is_meta_hw(hw)]
    has_real_he = any(
        HE_LETTER.search(hw.get("he_form") or "")
        for hw in hws
    )
    if has_real_he:
        stats.inc("4.3_align_con_hebreo_sin_griego_posible_omision")


def apply_4_3_omissions(verse: dict, stats: RuleStats) -> None:
    for p in verse.get("pairs", []):
        _rule_4_3_heb_omit_gr_empty(p, stats)
        _rule_4_3_align_empty_gr_has_he(p, stats)


# ═══════════════════════════════════════════════════════════════════════════
# PASO 4.4 — Tokens multi-palabra griega: orden correcto
# ═══════════════════════════════════════════════════════════════════════════

def _rule_4_4_multiword_gr_word(hw: dict, stats: RuleStats) -> None:
    """gr_word con >1 palabra: verificar que no mezcle categorías incompatibles."""
    gw = _norm_gr(hw.get("gr_word") or "")
    words = _gr_tokens(gw)
    if len(words) <= 1:
        return
    has_article = any(w in GR_ARTICLES for w in words)
    has_prep = any(w in GR_PREPS for w in words)
    has_conj = any(w in GR_CONJ_PARTICLES for w in words)
    if has_article or has_prep or has_conj:
        stats.inc("4.4_gr_word_multipalabra_con_functor")
    else:
        stats.inc("4.4_gr_word_multipalabra_contenido")


def _rule_4_4_pair_order(pair: dict, stats: RuleStats) -> None:
    """Verificar que prefix_gr + gr_word + prs.gr_word respeten el orden de gr_unicode."""
    kind = pair.get("kind") or "align"
    if kind == "heb_omit":
        return
    gr_u = _norm_gr(pair.get("gr_unicode") or "")
    if not gr_u:
        return
    src_tokens = _gr_tokens(gr_u)
    if len(src_tokens) <= 1:
        return

    assigned_tokens = _pair_assigned_gr_tokens(pair)
    if len(assigned_tokens) <= 1:
        return

    src_lower = [t.lower() for t in src_tokens]
    assigned_lower = [t.lower() for t in assigned_tokens if GR_LETTER.search(t)]

    common = [t for t in assigned_lower if t in src_lower]
    if len(common) < 2:
        return

    src_positions = []
    used_positions: set[int] = set()
    for t in common:
        for i, s in enumerate(src_lower):
            if s == t and i not in used_positions:
                src_positions.append(i)
                used_positions.add(i)
                break
        else:
            src_positions.append(-1)

    valid_pos = [p for p in src_positions if p >= 0]
    if len(valid_pos) >= 2:
        inversions = sum(
            1 for i in range(len(valid_pos))
            for j in range(i + 1, len(valid_pos))
            if valid_pos[i] > valid_pos[j]
        )
        if inversions > 0:
            stats.inc("4.4_orden_invertido_vs_gr_unicode")


def apply_4_4_multiword_order(verse: dict, stats: RuleStats) -> None:
    for p in verse.get("pairs", []):
        kind = p.get("kind") or "align"
        if kind == "heb_omit":
            continue
        _rule_4_4_pair_order(p, stats)
        for hw in p.get("he_words") or []:
            if _is_meta_hw(hw):
                continue
            _rule_4_4_multiword_gr_word(hw, stats)


# ═══════════════════════════════════════════════════════════════════════════
# PASO 4.5 — Griego LXX limpio: sin basura ni residuos mal extraídos
# ═══════════════════════════════════════════════════════════════════════════

def _check_gr_field(value: str, field_name: str, stats: RuleStats) -> None:
    """Comprobaciones genéricas de limpieza sobre un campo griego."""
    if not value:
        return
    v = value.strip()
    if not v:
        return

    if HE_LETTER.search(v):
        stats.inc(f"4.5_{field_name}_hebreo_en_campo_griego")

    if NIQQUD.search(v):
        stats.inc(f"4.5_{field_name}_niqqud_en_campo_griego")

    if BETA_CODE_RE.search(v):
        stats.inc(f"4.5_{field_name}_beta_code_residual")

    if LONE_DIACRITICS.match(v):
        stats.inc(f"4.5_{field_name}_diacritico_aislado")

    if ASCII_GARBAGE_RE.search(v) and not GR_LETTER.search(v):
        stats.inc(f"4.5_{field_name}_ascii_sin_griego")


def _rule_4_5_gr_unicode_clean(pair: dict, stats: RuleStats) -> None:
    """gr_unicode del par debe estar limpio."""
    _check_gr_field(pair.get("gr_unicode") or "", "gr_unicode", stats)


def _rule_4_5_gr_word_clean(hw: dict, stats: RuleStats) -> None:
    """gr_word y prefix_gr deben estar limpios."""
    _check_gr_field(hw.get("gr_word") or "", "gr_word", stats)
    for g in hw.get("prefix_gr") or []:
        _check_gr_field(g, "prefix_gr", stats)
    prs_gw = (hw.get("prs_suffix") or {}).get("gr_word", "")
    _check_gr_field(prs_gw, "prs_gr_word", stats)


def _rule_4_5_duplicate_consecutive(hw: dict, stats: RuleStats) -> None:
    """gr_word no debe tener la misma palabra consecutiva duplicada."""
    gw = _norm_gr(hw.get("gr_word") or "")
    words = _gr_tokens(gw)
    if len(words) < 2:
        return
    for i in range(len(words) - 1):
        if words[i].lower() == words[i + 1].lower() and words[i] not in GR_ARTICLES:
            stats.inc("4.5_gr_word_duplicado_consecutivo")
            break


def _rule_4_5_gr_unicode_vs_pair_gr(pair: dict, stats: RuleStats) -> None:
    """Tokens asignados no deben exceder los tokens de gr_unicode (sobras)."""
    kind = pair.get("kind") or "align"
    if kind == "heb_omit":
        return
    gr_u = _norm_gr(pair.get("gr_unicode") or "")
    if not gr_u:
        return
    source = _gr_multiset(_gr_tokens(gr_u))
    assigned = _gr_multiset(_pair_assigned_gr_tokens(pair))
    extra = assigned - source
    if extra:
        stats.inc("4.5_gr_token_sobra_vs_gr_unicode", sum(extra.values()))


def apply_4_5_cleanup(verse: dict, stats: RuleStats) -> None:
    for p in verse.get("pairs", []):
        _rule_4_5_gr_unicode_clean(p, stats)
        _rule_4_5_gr_unicode_vs_pair_gr(p, stats)
        for hw in p.get("he_words") or []:
            if _is_meta_hw(hw):
                continue
            _rule_4_5_gr_word_clean(hw, stats)
            _rule_4_5_duplicate_consecutive(hw, stats)


# ═══════════════════════════════════════════════════════════════════════════
# PIPELINE PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════

ALL_STEPS = [
    ("4.1  Griego completo (sin omisiones)", apply_4_1_completeness),
    ("4.2  ADD+ (gk_add) completadas",       apply_4_2_gk_add),
    ("4.3  Omisiones LXX correctas",         apply_4_3_omissions),
    ("4.4  Multi-palabra orden correcto",     apply_4_4_multiword_order),
    ("4.5  Limpieza general griego",          apply_4_5_cleanup),
]


def apply_greek_rules(
    data: dict,
    *,
    book: str = "genesis",
    steps: list[str] | None = None,
    dry_run: bool = False,
    verbose: bool = True,
) -> RuleStats:
    """Ejecuta las reglas griegas sobre versículos no protegidos.

    Args:
        data: JSON del libro (con "verses")
        book: slug del libro
        steps: lista de pasos a ejecutar (None = todos). Ej: ["4.1", "4.2"]
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
            f"\n== Reglas griegas LXX ({book}) ==\n"
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
            if fn is apply_4_2_gk_add:
                fn(v, step_stats, dry_run=dry_run)
            else:
                fn(v, step_stats)
        if verbose and step_stats.total():
            sys.stdout.write(f"  {label}:\n{step_stats.report()}\n\n")
        for k, v_count in step_stats.counts.items():
            stats.inc(k, v_count)

    if verbose:
        sys.stdout.write(f"  TOTAL hallazgos: {stats.total()}\n")

    return stats


# ═══════════════════════════════════════════════════════════════════════════
# CLI — uso independiente
# ═══════════════════════════════════════════════════════════════════════════

def main():
    import argparse
    import json

    sys.stdout.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser(description="Reglas griegas LXX")
    ap.add_argument("--book", default="genesis")
    ap.add_argument("--steps", nargs="*", help="Pasos a ejecutar (ej: 4.1 4.2)")
    ap.add_argument("--dry-run", action="store_true", help="Solo reportar, no modificar")
    ap.add_argument("--save", action="store_true", help="Guardar cambios en JSON")
    args = ap.parse_args()

    from book_config import resolve
    cfg = resolve(args.book)

    data = json.loads(cfg.final_json_path.read_text(encoding="utf-8"))
    stats = apply_greek_rules(
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
