"""
Utilidades compartidas para validación morfológica (Paso 4).
Compara etiquetas del pipeline con referencia OSHB (oshb-morph / índice Strong).
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

ROOT_TRADUCCION = Path(r"C:\Users\pik_y\Documents\TRADUCCION")
IDX_STRONG_HE = ROOT_TRADUCCION / "BIBLIAS" / "_idx_strong_he_gen.json"

# ── Normalización hebrea ────────────────────────────────────────────────────
HE_STRIP_RE = re.compile(
    r"[\u0591-\u05C7\u05BE\u05C0\u05C3\u05F3\u05F4\u200D\u200C\s\-\u05BE]"
)


def fold_he(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    return HE_STRIP_RE.sub("", s)


# ── Expansión morfología verbal corta (copiado de merge_oshb.py) ─────────────
_VS = {
    "q": "QAL", "Q": "QAL",
    "p": "PIEL", "P": "PIEL",
    "h": "HIF", "H": "HIF",
    "n": "NIF", "N": "NIF",
    "o": "HOF", "O": "HOF",
    "t": "HIT", "T": "HIT",
    "l": "POLEL", "L": "POLEL",
}
_VM = {
    "P": "PERF", "I": "IMPF", "W": "WAYYIQT", "m": "WAYYIQT",
    "J": "JUSS", "j": "JUSS", "C": "COH", "c": "COH",
    "A": "IMPV", "a": "IMPV", "p": "INFC", "f": "INFA",
    "r": "PTCA", "v": "PTCA", "s": "PTCP",
}
_VP = {"1": "P1", "2": "P2", "3": "P3"}
_VN = {"S": "SG", "P": "PL", "D": "DU"}
_VG = {"M": "M", "F": "F", "C": "COMMON", "B": "BOTH"}
_VVOICE = {"A", "P", "M"}


def _expand_short_verb(m: str) -> str:
    if len(m) < 3 or m[1] not in _VS:
        return m
    stem = _VS[m[1]]
    rest = m[2:]
    if len(rest) >= 2 and rest[0] in _VVOICE and rest[1] in _VM:
        mood = _VM[rest[1]]
        tail = rest[2:]
    elif rest and rest[0] in _VM:
        mood = _VM[rest[0]]
        tail = rest[1:]
    else:
        return m
    person = gender = number = ""
    for ch in tail:
        if ch in _VP and not person:
            person = _VP[ch]
        elif ch in _VN and not number:
            number = _VN[ch]
        elif ch in _VG and not gender:
            gender = _VG[ch]
    parts = ["VERBO", stem, mood]
    if person:
        parts.append(person)
    if gender:
        parts.append(gender)
    if number:
        parts.append(number)
    return ".".join(parts)


def normalize_morph(morph: str) -> str:
    if not morph:
        return ""
    if "." in morph or "+" in morph:
        return morph
    if morph[0] == "V":
        expanded = _expand_short_verb(morph)
        return expanded if expanded != morph else morph
    return morph


# Familias POS equivalentes (prefijos de etiqueta larga o código corto OSHB)
_POS_ALIASES = {
    "SUBS": {"SUBS", "NOUN", "NASC", "NC", "NPROP", "NP", "OMSA", "OM"},
    "VERBO": {"VERBO", "V"},
    "PREP": {"PREP", "R", "HR"},
    "ART": {"ART", "HT", "HTr", "Td"},
    "CONJ": {"CONJ", "C", "W"},
    "PART": {"PART", "PART.OBJ.DIR"},
    "ADJ": {"ADJ", "A", "HA", "AMPA", "AMSA", "AFSA"},
    "ADV": {"ADV", "D"},
    "NUM": {"NUM"},
    "PRON": {"PRON", "PRS"},
    "REL": {"REL"},
    "NEG": {"NEG"},
}


def morph_pos_root(morph: str) -> str:
    """Raíz POS normalizada para comparación conservadora."""
    m = normalize_morph(morph or "").strip()
    if not m:
        return ""
    # Compuestos: PREP+PRS… → PREP
    head = m.split("+")[0]
    if "." in head:
        return head.split(".")[0].upper()
    # Códigos cortos OSHB / OSHM
    u = head.upper()
    if u.startswith("VERBO") or (len(u) > 1 and u[0] == "V"):
        return "VERBO"
    if u in ("NPROP", "NP"):
        return "NPROP"
    # Etiqueta que ES una raíz canónica (NEG, ADV, NUM, PRON, REL, PART…): resolver
    # ANTES del heurístico startswith("N"), que si no clasificaría NEG («לֹא/אַל»)
    # como SUBS por empezar con N. (NPROP/NP ya se resolvió arriba.)
    if u in _POS_ALIASES:
        return u
    if u.startswith("N") or u.startswith("HN"):
        return "SUBS"
    if u.startswith("R") and u not in ("REL",):
        return "PREP"
    if u in ("CONJ", "C", "W"):
        return "CONJ"
    if u in ("ART", "HT"):
        return "ART"
    if u.startswith("P") and u in ("PREP", "PART", "PRON", "PRS"):
        return u.split(".")[0] if "." in u else (
            "PRON" if u == "PRS" else "PART" if u == "PART" else "PREP"
        )
    if u.startswith("A") and u not in ("ART",):
        if u in ("AMPA", "AMSA", "AFSA", "ADJ"):
            return "ADJ"
    if u in _POS_ALIASES:
        return u
    return u


def pos_families_compatible(a: str, b: str) -> bool:
    if not a or not b:
        return True
    if a == b:
        return True
    for _fam, members in _POS_ALIASES.items():
        if a in members and b in members:
            return True
    return False


# Códigos morfológicos del pipeline CATSS inicial (no OSHB largo)
_LEGACY_PREFIXES = (
    "RBS", "RBP", "RB", "NC", "NP", "HN", "HT", "HTr", "Td", "OM",
    "HA", "AM", "AF", "HR",
)


def is_legacy_pipeline_morph(morph: str) -> bool:
    """True si la etiqueta parece del sistema inicial (corto / OSHM), no VERBO.* OSHB."""
    m = (morph or "").strip()
    if not m or "+" in m:
        return False
    if m.startswith("VERBO.") or m.startswith("PART.") or m.startswith("SUBS."):
        return False
    if m[0] == "V" and "." not in m:
        return True
    head = m.split(".")[0] if "." in m else m
    return any(head.startswith(p) for p in _LEGACY_PREFIXES) or (
        len(head) <= 6 and head.isascii() and head[0].isupper()
    )


def split_composed_morph(morph: str) -> list[str]:
    return [p.strip() for p in (morph or "").split("+") if p.strip()]


def composed_matches_oshb_parts(site_morph: str, oshb_parts: list[str]) -> bool:
    """True si cada parte de PREP+PRS (etc.) coincide con la lista OSHB alineada."""
    parts = split_composed_morph(site_morph)
    if not parts or len(parts) != len(oshb_parts):
        return False
    return all(compare_morph(a, b) != "conflict" for a, b in zip(parts, oshb_parts))


def join_oshb_morphs(morphs: list[str]) -> str:
    return "+".join(m for m in morphs if m)


def load_strong_he_index(path: Path | None = None) -> dict:
    p = path or IDX_STRONG_HE
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


@dataclass
class MorphRefBundle:
    """Referencia resuelta en cascada: Strong → hebreo → morfología OSHB."""
    ref_morph: str = ""
    ref_source: str = "none"  # strong+he | strong | oshb:verse | oshb:align | none
    strong: str = ""
    strong_he_ok: bool = False
    strong_morph: str = ""
    strong_he_text: str = ""
    oshb_verse_morph: str = ""
    oshb_align_morph: str = ""
    strong_oshb_agree: bool = True


def lookup_strong_hebrew(
    he_idx: dict,
    strong: str,
    fold: str,
    ref: str,
) -> tuple[str, str] | None:
    """
    Busca en índice Strong+hebreo (OSHB/SWORD).
    Requiere Strong; si hay fold, la forma debe coincidir (consonantes).
    Prioriza entradas del versículo `ref`.
    """
    if not strong or strong not in he_idx:
        return None
    pool = he_idx[strong]
    if ref:
        by_ref = [e for e in pool if ref in (e.get("verses") or [])]
        if by_ref:
            pool = by_ref
    if fold:
        by_fold = [e for e in pool if fold_he(e.get("text", "")) == fold]
        if not by_fold:
            return None
        pool = by_fold
    if not pool:
        return None
    best = max(pool, key=lambda e: e.get("count", 0))
    morph = (best.get("morph") or "").strip()
    text = (best.get("text") or "").strip()
    if not morph:
        return None
    return morph, text


def resolve_morph_reference(
    ref: str,
    strong: str,
    he_form: str,
    oshb_align_morph: str = "",
    oshb_parts: list[str] | None = None,
    *,
    verse_map: dict | None = None,
    he_idx: dict | None = None,
) -> MorphRefBundle:
    """
    Cascada de convalidación:
      1) Strong + forma hebrea (índice _idx_strong_he_gen)
      2) OSHB del versículo por fold (oshb-morph)
      3) OSHB de la alineación 5.1 (átomos contiguos)
    """
    fold = fold_he(he_form)
    oshb_align = join_oshb_morphs(oshb_parts) if oshb_parts else (oshb_align_morph or "")
    bundle = MorphRefBundle(strong=normalize_strong(strong), oshb_align_morph=oshb_align)

    if he_idx and bundle.strong:
        hit = lookup_strong_hebrew(he_idx, bundle.strong, fold, ref)
        if hit:
            bundle.strong_morph, bundle.strong_he_text = hit
            bundle.strong_he_ok = True

    if verse_map and fold:
        vhit = lookup_verse_morph(verse_map, ref, he_form)
        if vhit:
            bundle.oshb_verse_morph = vhit[0]

    if bundle.strong_he_ok and bundle.strong_morph:
        bundle.ref_morph = bundle.strong_morph
        bundle.ref_source = "strong+he"
    elif bundle.strong and bundle.strong in (he_idx or {}) and bundle.strong_morph:
        bundle.ref_morph = bundle.strong_morph
        bundle.ref_source = "strong"
    elif bundle.oshb_verse_morph:
        bundle.ref_morph = bundle.oshb_verse_morph
        bundle.ref_source = "oshb:verse"
    elif oshb_align:
        bundle.ref_morph = oshb_align
        bundle.ref_source = "oshb:align"

    if bundle.strong_morph and bundle.oshb_verse_morph:
        bundle.strong_oshb_agree = compare_morph(
            bundle.strong_morph, bundle.oshb_verse_morph,
        ) != "conflict"
    return bundle


def classify_morph_pair(
    site_morph: str,
    oshb_morph: str,
    *,
    oshb_parts: list[str] | None = None,
    slot: str = "stem",
    raw: str = "",
) -> tuple[str, str, str]:
    """
    Clasifica sitio vs referencia OSHB.
    Devuelve (issue, action, detail).
    """
    site_morph = (site_morph or "").strip()
    oshb_morph = (oshb_morph or "").strip()
    raw = raw or ""

    if not site_morph:
        return "empty_site", "skip", ""

    if raw.startswith("INS/"):
        if oshb_morph and compare_morph(site_morph, oshb_morph) == "conflict":
            return "ins_vs_oshb", "review", oshb_morph
        return "ins_ok", "ok", oshb_morph

    if "+" in site_morph:
        parts = split_composed_morph(site_morph)
        ref_parts = oshb_parts if oshb_parts else ([oshb_morph] if oshb_morph else [])
        if composed_matches_oshb_parts(site_morph, ref_parts):
            return "composition_plus_ok", "ok", join_oshb_morphs(ref_parts)
        if len(parts) > 1 and len(ref_parts) == 1:
            return "composition_plus_split", "expected_split", oshb_morph
        if len(parts) == 1 and len(ref_parts) > 1:
            return "composition_oshb_split", "expected_compose", join_oshb_morphs(ref_parts)
        return "composition_plus_conflict", "review", join_oshb_morphs(ref_parts)

    if is_legacy_pipeline_morph(site_morph):
        if not oshb_morph:
            return "legacy_no_oshb", "review", ""
        cmp = compare_morph(site_morph, oshb_morph)
        if cmp == "exact":
            return "legacy_exact", "ok", ""
        if cmp == "minor":
            return "legacy_format", "annotate_oshb", oshb_morph
        return "legacy_conflict", "review", oshb_morph

    if not oshb_morph:
        return "site_only", "review", ""

    cmp = compare_morph(site_morph, oshb_morph)
    if cmp == "exact":
        return "oshb_exact", "ok", ""
    if cmp == "minor":
        return "oshb_minor", "optional", oshb_morph

    o_root = morph_pos_root(site_morph)
    r_root = morph_pos_root(oshb_morph)
    if slot == "suffix" and o_root in ("PRS", "PRON") and r_root == "CONJ":
        return "composition_suffix_slot", "expected_option4", oshb_morph
    if o_root in ("PRS", "PRON") and r_root == "CONJ":
        return "composition_suffix_slot", "expected_option4", oshb_morph
    return "oshb_conflict", "review", oshb_morph


def classify_with_cascade(
    site_morph: str,
    bundle: MorphRefBundle,
    *,
    oshb_parts: list[str] | None = None,
    slot: str = "stem",
    raw: str = "",
) -> tuple[str, str, str]:
    """
    Clasifica usando cascada Strong → hebreo → morfología.
    Si Strong+hebreo validan el token, un desacuerdo solo con OSHB alineado no se marca conflicto.
    """
    strong = bundle.strong
    # Strong aplica al lexema (stem); prefijos/sufijos se validan solo con OSHB/alineación
    if strong and slot == "stem" and not bundle.strong_he_ok:
        if not (raw or "").startswith("INS/"):
            return "strong_he_mismatch", "review", f"Strong {strong} sin forma {bundle.strong_he_text or '?'}"

    oshb_for_compare = bundle.oshb_verse_morph or bundle.oshb_align_morph
    if oshb_parts and len(oshb_parts) > 1:
        oshb_for_compare = join_oshb_morphs(oshb_parts)

    issue, action, detail = classify_morph_pair(
        site_morph,
        bundle.ref_morph,
        oshb_parts=oshb_parts if "+" in (site_morph or "") else None,
        slot=slot,
        raw=raw,
    )

    if bundle.ref_source in ("strong+he", "strong") and bundle.ref_morph:
        cmp_s = compare_morph(site_morph, bundle.ref_morph)
        if cmp_s in ("exact", "minor"):
            if issue in ("oshb_conflict", "legacy_conflict") and bundle.strong_oshb_agree is False:
                return "convalidated_strong_he", "ok", bundle.ref_morph
            if issue in ("oshb_conflict", "legacy_conflict"):
                return "convalidated_strong_he", "ok", bundle.ref_morph
            if issue.startswith("legacy_") and cmp_s == "minor":
                return "legacy_strong_ok", "annotate_oshb", bundle.oshb_verse_morph or detail
        elif cmp_s == "conflict" and bundle.ref_source == "strong+he":
            return "strong_morph_conflict", "review", bundle.ref_morph

    if (
        bundle.ref_source in ("oshb:verse", "oshb:align")
        and not bundle.strong_he_ok
        and issue == "oshb_conflict"
        and strong
    ):
        return "oshb_conflict_no_strong_he", "review", detail

    return issue, action, detail


def compare_morph(ours: str, ref: str) -> str:
    """
    Devuelve: exact | minor | conflict
    """
    o_norm = normalize_morph(ours)
    r_norm = normalize_morph(ref)
    if o_norm == r_norm:
        return "exact"
    o_root = morph_pos_root(ours)
    r_root = morph_pos_root(ref)
    if pos_families_compatible(o_root, r_root):
        return "minor"
    return "conflict"


def normalize_strong(raw: str) -> str:
    if not raw:
        return ""
    s = raw.strip()
    if ":" in s:
        s = s.split(":", 1)[1]
    if not s:
        return ""
    head = s[0].upper()
    if head not in ("H", "G"):
        return ""
    rest = s[1:].lstrip("0") or "0"
    return f"{head}{rest}"


def load_verse_morph_map(oshb_dir: Path) -> dict[str, list[tuple[str, str]]]:
    """ref 'cap:vers' → [(fold_he, morph), ...] desde oshb-morph."""
    out: dict[str, list[tuple[str, str]]] = {}
    if not oshb_dir.is_dir():
        return out
    for ch_file in sorted(oshb_dir.glob("*.json")):
        try:
            ch = int(ch_file.stem)
        except ValueError:
            continue
        data = json.loads(ch_file.read_text(encoding="utf-8"))
        for vs, block in data.items():
            ref = f"{ch}:{vs}"
            forms = block.get("forms", [])
            morphs = block.get("morphs", [])
            out[ref] = [
                (fold_he(f), m) for f, m in zip(forms, morphs) if fold_he(f)
            ]
    return out


def lookup_verse_morph(
    verse_map: dict[str, list[tuple[str, str]]],
    ref: str,
    he_form: str,
) -> tuple[str, str] | None:
    """Busca morfología de referencia por ref + forma (consonantes)."""
    entries = verse_map.get(ref)
    if not entries:
        return None
    key = fold_he(he_form)
    if not key:
        return None
    matches = [m for f, m in entries if f == key]
    if not matches:
        return None
    # Si hay varias (homógrafos), tomar la más frecuente en la lista
    from collections import Counter
    best = Counter(matches).most_common(1)[0][0]
    return best, "oshb:verse"
