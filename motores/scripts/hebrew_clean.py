"""Limpieza y detección de artefactos OSHB en campos hebreos (B2–B4 / B7)."""
from __future__ import annotations

import re

_OSHB_ENC_PREFIX = re.compile(r"^i>\(")
_ASCII_IN_HE = re.compile(r"[a-zA-Z]")
_HEB_LETTER = re.compile(r"[\u05D0-\u05EA]")

META_RAW_PREFIX = ("=", "{", "<", "*", "--", ".$")


def strip_encoding_artifact(s: str) -> str:
    """Quita prefijo i>( de formas OSHB corruptas."""
    if not s:
        return s
    return _OSHB_ENC_PREFIX.sub("", s)


def has_encoding_artifact(s: str) -> bool:
    return bool(s and "i>(" in s)


def is_meta_raw(raw: str) -> bool:
    r = raw or ""
    return r.startswith(META_RAW_PREFIX) or r.startswith(".$")


def he_form_deformed(s: str) -> bool:
    """True si he_form no es hebreo limpio para UI."""
    if not (s or "").strip():
        return False
    if has_encoding_artifact(s):
        return True
    return bool(_ASCII_IN_HE.search(s) and _HEB_LETTER.search(s))


def sanitize_hw_he_forms(hw: dict) -> bool:
    """Normaliza he_form / prefix_forms / prs_suffix.he_form; devuelve si hubo cambio."""
    changed = False
    hf = hw.get("he_form")
    if hf and has_encoding_artifact(hf):
        hw["he_form"] = strip_encoding_artifact(hf)
        changed = True
    pfx = hw.get("prefix_forms") or []
    for i, pf in enumerate(pfx):
        if pf and has_encoding_artifact(pf):
            pfx[i] = strip_encoding_artifact(pf)
            changed = True
    prs = hw.get("prs_suffix")
    if isinstance(prs, dict):
        ph = prs.get("he_form")
        if ph and has_encoding_artifact(ph):
            prs["he_form"] = strip_encoding_artifact(ph)
            changed = True
    if changed:
        hw["he_source"] = "patch_oshb"
    return changed


def sanitize_verse_he_forms(verse: dict) -> int:
    n = 0
    for p in verse.get("pairs", []):
        for hw in p.get("he_words") or []:
            if sanitize_hw_he_forms(hw):
                n += 1
    return n


# Maqaf (U+05BE) — OSHB suele ponerlo al inicio del token siguiente; la UI usa trailing en el anterior.
MAQAF = "\u05be"
MAQAF_CHARS = frozenset({MAQAF, "־", "-"})


def has_leading_maqaf(s: str) -> bool:
    return bool(s) and s[0] in MAQAF_CHARS


def has_trailing_maqaf(s: str) -> bool:
    return bool(s) and s[-1] in MAQAF_CHARS


def strip_leading_maqaf(s: str) -> str:
    s = s or ""
    while s and s[0] in MAQAF_CHARS:
        s = s[1:]
    return s


def strip_trailing_maqaf(s: str) -> str:
    s = s or ""
    while s and s[-1] in MAQAF_CHARS:
        s = s[:-1]
    return s


def ensure_trailing_maqaf(s: str) -> str:
    core = strip_trailing_maqaf(strip_leading_maqaf(s))
    if not core:
        return s or ""
    return core + MAQAF


def _mark_hw_maqaf_patched(hw: dict) -> None:
    if not hw.get("he_source"):
        hw["he_source"] = "patch_oshb"


def normalize_bethel_pair_maqaf(pair: dict) -> bool:
    """BYT + )L → בֵּֽית־ + אֵל (maqaf final en la primera parte)."""
    hws = pair.get("he_words") or []
    byt = el = None
    for hw in hws:
        raw = hw.get("raw") or ""
        if is_meta_raw(raw):
            continue
        if raw == "BYT":
            byt = hw
        elif raw == ")L":
            el = hw
    if not (byt and el):
        return False

    changed = False
    new_byt = ensure_trailing_maqaf(byt.get("he_form") or "")
    el_core = strip_leading_maqaf(strip_trailing_maqaf(el.get("he_form") or ""))
    if byt.get("he_form") != new_byt:
        byt["he_form"] = new_byt
        changed = True
    if el.get("he_form") != el_core:
        el["he_form"] = el_core
        changed = True
    if changed:
        _mark_hw_maqaf_patched(byt)
        _mark_hw_maqaf_patched(el)
    return changed


def normalize_leading_maqaf_in_verse(verse: dict) -> int:
    """Mueve maqaf inicial OSHB al token anterior (trailing)."""
    n = 0
    prev: dict | None = None
    for p in verse.get("pairs", []):
        for hw in p.get("he_words") or []:
            raw = hw.get("raw") or ""
            if is_meta_raw(raw):
                prev = hw
                continue
            he = hw.get("he_form") or ""
            if not has_leading_maqaf(he):
                prev = hw
                continue
            core = strip_leading_maqaf(he)
            if he != core:
                hw["he_form"] = core
                _mark_hw_maqaf_patched(hw)
                n += 1
            if prev is not None and not is_meta_raw(prev.get("raw") or ""):
                prev_he = prev.get("he_form") or ""
                if prev_he and not has_trailing_maqaf(prev_he):
                    new_prev = ensure_trailing_maqaf(prev_he)
                    if prev_he != new_prev:
                        prev["he_form"] = new_prev
                        _mark_hw_maqaf_patched(prev)
                        n += 1
            prev = hw
    return n


def normalize_leading_maqaf_surfaces(verse: dict) -> int:
    """Mueve el maqaf inicial al surface previo, cubriendo prefijos y sufijos.

    A diferencia de ``normalize_leading_maqaf_in_verse`` (que solo mira ``he_form``),
    recorre TODAS las superficies en orden de lectura — prefix_forms, stem y
    prs_suffix.he_form — y arregla el maqaf inicial redundante del artículo
    (ej. ``מִן־`` + ``־הַ`` → ``מִן־`` + ``הַ``). El maqaf siempre es trailing en la
    palabra previa no vacía.
    """
    # slots en orden de lectura: (kind, container, key_or_idx, owner_hw)
    slots: list[tuple] = []
    for p in verse.get("pairs", []):
        for hw in p.get("he_words") or []:
            if is_meta_raw(hw.get("raw") or ""):
                continue
            pf = hw.get("prefix_forms")
            if isinstance(pf, list):
                for i in range(len(pf)):
                    slots.append(("list", pf, i, hw))
            slots.append(("dict", hw, "he_form", hw))
            prs = hw.get("prs_suffix")
            if isinstance(prs, dict):
                slots.append(("dict", prs, "he_form", hw))

    def _get(s) -> str:
        kind, cont, key, _ = s
        return ((cont[key] if kind == "list" else cont.get(key)) or "")

    def _set(s, val: str) -> None:
        kind, cont, key, owner = s
        cont[key] = val
        _mark_hw_maqaf_patched(owner)

    n = 0
    for idx, s in enumerate(slots):
        val = _get(s)
        if not has_leading_maqaf(val):
            continue
        core = strip_leading_maqaf(val)
        if core != val:
            _set(s, core)
            n += 1
        # buscar la superficie previa no vacía para dejarle el maqaf trailing
        j = idx - 1
        while j >= 0 and not _get(slots[j]).strip():
            j -= 1
        if j >= 0:
            pv = _get(slots[j])
            if pv and not has_trailing_maqaf(pv):
                _set(slots[j], ensure_trailing_maqaf(pv))
                n += 1
    return n


def normalize_verse_maqaf(verse: dict) -> int:
    """Normaliza posición del maqaf en un verso (convención UI: trailing en anterior)."""
    n = 0
    for p in verse.get("pairs", []):
        if normalize_bethel_pair_maqaf(p):
            n += 1
    n += normalize_leading_maqaf_in_verse(verse)
    n += normalize_leading_maqaf_surfaces(verse)
    for p in verse.get("pairs", []):
        if normalize_bethel_pair_maqaf(p):
            n += 1
    return n


def scan_verse_maqaf_issues(verse: dict) -> list[str]:
    """Detecta stems con maqaf inicial sin trailing en el token previo."""
    issues: list[str] = []
    prev: dict | None = None
    ch, vs = verse.get("chapter"), verse.get("verse")
    ref = f"{ch}:{vs}"
    for pi, p in enumerate(verse.get("pairs", [])):
        for hi, hw in enumerate(p.get("he_words") or []):
            raw = hw.get("raw") or ""
            if is_meta_raw(raw):
                prev = hw
                continue
            he = hw.get("he_form") or ""
            if has_leading_maqaf(he):
                prev_label = (prev.get("raw") if prev else "?") if prev else "—"
                issues.append(
                    f"{ref} p{pi}.h{hi} raw={raw!r} leading_maqaf={he!r} prev={prev_label!r}"
                )
            if raw == "BYT":
                el_hw = next(
                    (
                        x
                        for x in (p.get("he_words") or [])
                        if (x.get("raw") or "") == ")L" and not is_meta_raw(x.get("raw") or "")
                    ),
                    None,
                )
                if el_hw and not has_trailing_maqaf(he):
                    issues.append(f"{ref} p{pi} Bethel BYT sin trailing maqaf: {he!r}")
                if el_hw and has_leading_maqaf(el_hw.get("he_form") or ""):
                    issues.append(
                        f"{ref} p{pi} Bethel )L con leading maqaf: {el_hw.get('he_form')!r}"
                    )
            prev = hw
    return issues
