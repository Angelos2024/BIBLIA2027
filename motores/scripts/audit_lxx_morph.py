"""Auditoría LXX morfológica — detecta griego en slot hebreo incorrecto (caps 10–14).

Complementa audit_gen_chapter_lxx.py (cobertura) con heurísticas de clase:
- partícula (δὲ, καὶ…) en stem de verbo
- verbo (ἐγένετο, εἶπεν…) en prefix CONJ
- preposición griega en slot no-PREP
- intercambio adyacente prefix↔stem mejorable
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata as ud
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent

_GR_PUNCT = ".,·;:«»\"'()[]"


def _norm_gr(s: str) -> str:
    if not s:
        return ""
    s = s.strip().strip(_GR_PUNCT)
    if not s:
        return ""
    s = ud.normalize("NFD", s)
    return "".join(c for c in s if ud.category(c) != "Mn").lower()


def _first_token(s: str) -> str:
    for w in (s or "").split():
        n = _norm_gr(w)
        if n:
            return n
    return ""


# Partículas / conjunciones frecuentes en LXX
_GR_PARTICLES = frozenset({
    "και", "δε", "δη", "γαρ", "μεν", "ουν", "τε", "αλλα", "ινα", "οτι",
    "μη", "ου", "ουκ", "μην", "νυν", "ωστε", "ει", "εαν", "οταν",
})

# Artículos / determinantes
_GR_ARTICLES = frozenset({"ο", "η", "το", "οι", "αι", "τα", "του", "της", "των", "τον", "την", "τους", "τας"})

# Preposiciones frecuentes
_GR_PREPS = frozenset({
    "εν", "επι", "απο", "εις", "εκ", "εξ", "προ", "προς", "μετα", "κατα",
    "υπο", "περι", "δια", "ανα", "συν", "αχρι", "εως", "εναντιον", "εμπροσθεν",
})

_GR_REL_ADVERBS = frozenset({"οθεν", "οπου", "οπως", "οτι", "οταν", "εως"})

# Terminaciones verbales comunes (heurística)
_VERB_SUFFIXES = (
    "εν", "ον", "ειν", "σαι", "ται", "νται", "μαι", "σθαι",
    "σεν", "το", "τε", "ται", "ησαν", "ομεν", "ετε", "ουσι",
)
_VERB_STEMS = frozenset({
    "egeneto", "eipen", "eipan", "egenonto", "ekalesen", "eporeuthe",
    "epoiesen", "egenethe", "estin", "esan", "elthen", "eiden",
})


def _looks_like_particle(tok: str) -> bool:
    return tok in _GR_PARTICLES or tok in _GR_ARTICLES


def _looks_like_prep(tok: str) -> bool:
    return tok in _GR_PREPS


def _looks_like_verb(tok: str) -> bool:
    if tok in _VERB_STEMS:
        return True
    if len(tok) >= 4 and tok.endswith(_VERB_SUFFIXES):
        return True
    # aorist/impf 3sg -εν
    if len(tok) >= 5 and tok.endswith("εν") and tok not in _GR_PREPS:
        return True
    return False


def _morph_class(morph: str) -> str:
    m = morph or ""
    if m == "CONJ" or m.startswith("CONJ"):
        return "CONJ"
    if m == "PREP" or m.startswith("PREP"):
        return "PREP"
    if m == "ART" or m.startswith("ART"):
        return "ART"
    if "VERBO" in m or m.startswith("V."):
        return "VERB"
    if m.startswith("PRON") or m.startswith("PRS"):
        return "PRON"
    if m.startswith("PART."):
        return "PART"
    if "NPROP" in m or "SUBS" in m or "N." in m:
        return "NOUN"
    if "ADJ" in m:
        return "ADJ"
    return "OTHER"


def _slot_gr(hw: dict, slot: str, ki: int = 0) -> str:
    if slot == "prefix":
        pgr = hw.get("prefix_gr") or []
        return pgr[ki] if ki < len(pgr) else ""
    if slot == "stem":
        return hw.get("gr_word") or ""
    if slot == "prs":
        prs = hw.get("prs_suffix") or {}
        return prs.get("gr_word") or "" if isinstance(prs, dict) else ""
    return ""


def _looks_like_accusative_noun(tok: str) -> bool:
    """Acusativo griego -ον/-ον en nombres (no confundir con verbo)."""
    return len(tok) >= 4 and tok.endswith(("ον", "ον", "ην", "αν", "ων"))


def _looks_like_ethnic_adjective(tok: str) -> bool:
    return len(tok) >= 5 and tok.endswith(("αιον", "αῖον", "αιων", "αδιον", "αριον", "αιον"))


def _hebrew_is_nominal(morph: str) -> bool:
    m = morph or ""
    return any(x in m for x in ("SUBS", "NPROP", "N.", "ADJ", "NUM"))


def _audit_hw(hw: dict, ref: str, pi: int, hi: int) -> list[dict]:
    issues: list[dict] = []
    raw = hw.get("raw") or ""
    morph = hw.get("he_morph") or ""
    pfx_m = hw.get("prefix_morphs") or []

    for ki, pm in enumerate(pfx_m):
        if pm == "PART.OBJ.DIR":
            continue
        gr = _slot_gr(hw, "prefix", ki)
        tok = _first_token(gr)
        if not tok:
            continue
        mc = _morph_class(pm)
        if mc == "CONJ" and _looks_like_verb(tok) and not _looks_like_particle(tok):
            issues.append({
                "ref": ref, "pair": pi, "hw": hi, "slot": f"prefix[{ki}]",
                "type": "verb_en_conj",
                "raw": raw, "he_morph": pm, "gr": gr,
                "detail": f"CONJ con verbo griego {gr!r}",
            })
        elif mc == "CONJ" and _looks_like_prep(tok) and tok not in ("και",):
            issues.append({
                "ref": ref, "pair": pi, "hw": hi, "slot": f"prefix[{ki}]",
                "type": "prep_en_conj",
                "raw": raw, "he_morph": pm, "gr": gr,
                "detail": f"CONJ con prep griega {gr!r}",
            })
        elif mc == "PREP" and not _looks_like_prep(tok) and _looks_like_verb(tok):
            issues.append({
                "ref": ref, "pair": pi, "hw": hi, "slot": f"prefix[{ki}]",
                "type": "verb_en_prep",
                "raw": raw, "he_morph": pm, "gr": gr,
                "detail": f"PREP con verbo griego {gr!r}",
            })
        elif mc == "PREP" and _looks_like_particle(tok) and tok not in _GR_PREPS:
            if raw in ("L/MH", "L/(WT", "L/(&WT") and _norm_gr(tok) in ("ινα", "οπως"):
                pass
            else:
                issues.append({
                    "ref": ref, "pair": pi, "hw": hi, "slot": f"prefix[{ki}]",
                    "type": "particula_en_prep",
                    "raw": raw, "he_morph": pm, "gr": gr,
                    "detail": f"PREP con partícula {gr!r}",
                })
        elif mc == "ART" and not _looks_like_particle(tok) and _looks_like_verb(tok):
            if _looks_like_ethnic_adjective(tok):
                pass
            else:
                issues.append({
                    "ref": ref, "pair": pi, "hw": hi, "slot": f"prefix[{ki}]",
                    "type": "verb_en_art",
                    "raw": raw, "he_morph": pm, "gr": gr,
                    "detail": f"ART con verbo {gr!r}",
                })

    stem_gr = hw.get("gr_word") or ""
    stem_tok = _first_token(stem_gr)
    if stem_tok:
        mc = _morph_class(morph)
        if mc == "VERB" and _looks_like_particle(stem_tok) and not _looks_like_verb(stem_tok):
            if stem_tok in ("των", "των") or stem_gr.strip().startswith(("τῶν ", "του ", "τοῦ ")):
                pass
            else:
                issues.append({
                    "ref": ref, "pair": pi, "hw": hi, "slot": "stem",
                    "type": "particula_en_verbo",
                    "raw": raw, "he_morph": morph, "gr": stem_gr,
                    "detail": f"VERBO con partícula griega {stem_gr!r}",
                })
        elif mc in ("NOUN", "NPROP") and _looks_like_verb(stem_tok) and not _looks_like_particle(stem_tok):
            if stem_tok in _GR_REL_ADVERBS:
                pass
            elif raw.startswith("W/") and "NPROP" in morph and stem_tok in (
                "εζησεν", "εγεννησεν", "εγενετο",
            ):
                pass
            elif _hebrew_is_nominal(morph) and (
                _looks_like_accusative_noun(stem_tok)
                or stem_tok.endswith(("αι", "αις", "ας"))
            ):
                pass
            else:
                issues.append({
                    "ref": ref, "pair": pi, "hw": hi, "slot": "stem",
                    "type": "verb_en_nombre",
                    "raw": raw, "he_morph": morph, "gr": stem_gr,
                    "detail": f"NOMBRE con verbo griego {stem_gr!r}",
                })
        elif mc == "PREP" and _looks_like_verb(stem_tok):
            issues.append({
                "ref": ref, "pair": pi, "hw": hi, "slot": "stem",
                "type": "verb_en_prep_stem",
                "raw": raw, "he_morph": morph, "gr": stem_gr,
                "detail": f"PREP stem con verbo {stem_gr!r}",
            })

    # Intercambio adyacente CONJ+VERB: prefix tiene verbo y stem tiene partícula
    if pfx_m and _morph_class(pfx_m[0]) == "CONJ" and _morph_class(morph) == "VERB":
        pgr = _slot_gr(hw, "prefix", 0)
        pt = _first_token(pgr)
        st = _first_token(stem_gr)
        if pt and st and _looks_like_verb(pt) and _looks_like_particle(st):
            issues.append({
                "ref": ref, "pair": pi, "hw": hi, "slot": "swap_conj_verb",
                "type": "swap_conj_verb",
                "raw": raw, "he_morph": morph,
                "gr": f"prefix={pgr!r} stem={stem_gr!r}",
                "detail": f"posible swap: verbo en CONJ, partícula en VERBO",
            })

    return issues


def audit_verse(v: dict) -> list[dict]:
    ch, vn = v.get("chapter"), v.get("verse")
    ref = f"{ch}:{vn}"
    issues: list[dict] = []
    for pi, p in enumerate(v.get("pairs") or []):
        if (p.get("kind") or "align") in ("heb_omit",):
            continue
        for hi, hw in enumerate(p.get("he_words") or []):
            raw = hw.get("raw") or ""
            if raw.startswith("=") or raw.startswith("{") or raw.endswith("}"):
                continue
            issues.extend(_audit_hw(hw, ref, pi, hi))
    return issues


def audit_chapters(data: dict, chapters: list[int]) -> tuple[list[str], Counter, list[dict]]:
    lines = ["# Auditoría LXX morfológica (heurística)\n"]
    all_issues: list[dict] = []
    by_type: Counter[str] = Counter()
    verses_hit: set[str] = set()

    for ch in chapters:
        versos = sorted(
            (v for v in data["verses"] if v.get("chapter") == ch),
            key=lambda v: int(v.get("verse") or 0),
        )
        ch_issues: list[dict] = []
        for v in versos:
            iss = audit_verse(v)
            if iss:
                ref = f"{ch}:{v.get('verse')}"
                verses_hit.add(ref)
                ch_issues.extend(iss)
                all_issues.extend(iss)

        if ch_issues:
            lines.append(f"\n## Capítulo {ch} — {len(ch_issues)} incidencias en {len({i['ref'] for i in ch_issues})} versos")
            by_ref: dict[str, list] = defaultdict(list)
            for i in ch_issues:
                by_ref[i["ref"]].append(i)
            for ref in sorted(by_ref, key=lambda r: (int(r.split(":")[0]), int(r.split(":")[1]))):
                lines.append(f"\n### {ref}")
                for i in by_ref[ref][:8]:
                    by_type[i["type"]] += 1
                    lines.append(
                        f"  [{i['type']}] p{i['pair']} h{i['hw']} {i['slot']} "
                        f"raw={i['raw']!r} — {i['detail']}"
                    )
                if len(by_ref[ref]) > 8:
                    lines.append(f"  ... +{len(by_ref[ref]) - 8} más")

    for i in all_issues:
        by_type[i["type"]] += 0

    lines.insert(1, f"Capítulos: {chapters}")
    lines.insert(2, f"Versículos con incidencia: {len(verses_hit)}")
    lines.insert(3, f"Total incidencias: {len(all_issues)} — {dict(by_type)}")
    return lines, by_type, all_issues


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chapters", default="10,11,12,13,14")
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "genesis_final.json")
    ap.add_argument("--verse", type=str, default="", help="ej. 11:2")
    args = ap.parse_args()

    data = json.loads(args.data.read_text(encoding="utf-8"))

    if args.verse:
        ch, vn = args.verse.split(":")
        v = next(x for x in data["verses"] if x.get("chapter") == int(ch) and x.get("verse") == int(vn))
        issues = audit_verse(v)
        print(f"=== {args.verse} — {len(issues)} incidencias morfológicas ===")
        for i in issues:
            print(f"  [{i['type']}] p{i['pair']} h{i['hw']} {i['slot']}: {i['detail']}")
        return

    chapters = [int(x.strip()) for x in args.chapters.split(",")]
    lines, by_type, all_issues = audit_chapters(data, chapters)
    out = SCRIPTS / "audit_lxx_morph_10_14.txt"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"written {out}")
    print(f"total={len(all_issues)} tipos={dict(by_type)}")


if __name__ == "__main__":
    main()
