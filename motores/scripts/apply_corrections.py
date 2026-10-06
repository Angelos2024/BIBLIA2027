"""
apply_corrections.py
====================
Aplica correcciones manuales verificadas y Global Passes sobre <libro>_final.json.

Cada entrada en CORRECTIONS es una lista de tuplas:
    (forma_hebrea, morfología, español, griego_lxx)
en orden secuencial CATSS: para cada par → para cada he_word → prefijos, luego stem.

Los gk_add y heb_omit no tienen elementos CATSS → se saltan automáticamente.

USO POR LIBRO:
    python scripts/apply_corrections.py              # default: genesis
    python scripts/apply_corrections.py --book exodo # cualquier libro registrado en book_config

B2–B4 / B8 (solo un capítulo, más rápido):
    python scripts/apply_corrections.py --chapter 15 --mode hebrew
    python scripts/apply_corrections.py --chapter 15 --mode lxx
    python scripts/run_gen_block.py 15 B4            # pipeline + audit del bloque

Para Génesis se aplican: parches manuales + Global Passes 0-19 + parches por capítulo.
Para otros libros se aplican principalmente Global Passes 0-14 (y 15-19 según disponibilidad).

Documentación del orden de ejecución:
    scripts/PROCESO_CORRECCIONES.md   — passes y puntos de re-aplicación de parches
    scripts/REVISION_CAPITULO.md      — cerrar un capítulo (hebreo → español)
    scripts/audit_chapter_full.py N — auditoría completa de un capítulo
"""

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# Permitir importar book_config (libro-agnóstico)
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from hebrew_clean import (
    ensure_trailing_maqaf,
    normalize_verse_maqaf,
    sanitize_verse_he_forms,
    strip_leading_maqaf,
)

# Directorios externos (módulos bíblicos OSHB / SpaRV1909) para Global Pass 9
BIBLIAS_DIR = Path(r"C:\Users\pik_y\Documents\TRADUCCION\BIBLIAS")

# Bug 1 fix: letras hebreas visualmente similares a griegas
# Limpia strings griegos que pueden haberse escrito con teclado en hebreo activo.
_HEB_TO_GR = {
    '\u05E8': '\u03C1',  # ר → ρ
    '\u05D7': '\u03C7',  # ח → χ
    '\u05DF': '\u03BD',  # ן → ν
    '\u05E0': '\u03BD',  # נ → ν
    '\u05DE': '\u03BC',  # מ → μ
    '\u05E1': '\u03C3',  # ס → σ
    '\u05D3': '\u03B4',  # ד → δ
    '\u05D0': '\u03B1',  # א → α
    '\u05D1': '\u03B2',  # ב → β
}

def _san_gr(s: str) -> str:
    """Reemplaza lookalikes hebreos en un campo que debe ser griego."""
    if not s:
        return s
    return ''.join(_HEB_TO_GR.get(c, c) for c in s)


_META_RAW_PREFIX = ("=", "{", "<", "*", "--", ".$")


def _is_meta_hw(hw: dict) -> bool:
    raw = hw.get("raw") or ""
    if raw in ("GKADD", "=<LXX>"):
        return False
    return raw.startswith(_META_RAW_PREFIX)


def _clear_hw_gr_slots(hw: dict) -> None:
    pfx = hw.get("prefix_gr") or []
    if pfx:
        hw["prefix_gr"] = [""] * len(pfx)
    hw["gr_word"] = ""
    prs = hw.get("prs_suffix")
    if isinstance(prs, dict):
        prs["gr_word"] = ""


def _norm_gr_token(w: str) -> str:
    if not w:
        return ""
    s = w.strip().strip(".,·;:«»\"'()[]")
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


_GR_LXX_PARTICLES = frozenset({
    "και", "δε", "δη", "γαρ", "μεν", "ουν", "τε", "αλλα", "ινα", "οτι",
    "μη", "ου", "ουκ", "νυν", "ει", "εαν", "ωστε", "αρα", "ουν",
})
_GR_LXX_PREPS = frozenset({
    "εν", "επι", "απο", "εις", "εκ", "εξ", "προ", "προς", "μετα", "κατα",
    "υπο", "περι", "δια", "ανα", "συν", "αχρι", "εως", "εναντιον", "εμπροσθεν",
    "οπισω", "εωσ", "αχρι", "παρα", "αντι", "υπερ", "πλην",
})
_GR_LXX_ARTICLES = frozenset({
    "ο", "η", "το", "οι", "αι", "τα", "του", "της", "των", "τον", "την", "τους", "τας",
    "τω", "τῳ", "των",
})


def _gr_token_class(w: str) -> str:
    n = _norm_gr_token(w)
    if not n:
        return "EMPTY"
    if n in _GR_LXX_PARTICLES:
        return "PART"
    if n in _GR_LXX_PREPS:
        return "PREP"
    if n in _GR_LXX_ARTICLES:
        return "ART"
    if len(n) >= 4 and (
        n.endswith((
            "εν", "ον", "ειν", "σεν", "το", "ται", "νται", "μαι", "σθαι", "ησαν",
            "μενος", "ομενος", "αμενος", "ωμενος", "υμενος",
        ))
        or n.endswith(("η", "ε", "ες", "ας", "αν", "ων", "ως", "οι", "αι"))
        or n in ("egeneto", "eipen", "eipan", "epoiesen", "elthen", "estin", "esan", "eiden",
                 "anebe", "apengeilen", "eure", "estratopedeusen")
    ):
        return "VERB"
    if n in ("αυτου", "αυτων", "αυτον", "αυτοις", "αυτην", "αυτω", "σου", "σοι", "μου", "μοι"):
        return "PRON"
    return "NOUN"


def _slot_morph_class(hw: dict, stype: str, sk: int | None) -> str:
    if stype == "prefix":
        pm = (hw.get("prefix_morphs") or [])[sk] if sk is not None else ""
        if pm == "CONJ":
            return "CONJ"
        if pm == "PREP":
            return "PREP"
        if pm == "ART":
            return "ART"
        return "OTHER"
    if stype == "stem":
        m = hw.get("he_morph") or ""
        if "VERBO" in m:
            return "VERB"
        if m == "PREP" or m.startswith("PREP"):
            return "PREP"
        if m.startswith("PRON") or m.startswith("PRS"):
            return "PRON"
        if m == "CONJ":
            return "CONJ"
        return "NOUN"
    if stype == "prs":
        return "PRON"
    return "OTHER"


def _lxx_class_compatible(slot_cls: str, word_cls: str) -> bool:
    if word_cls == "EMPTY":
        return True
    if slot_cls == word_cls:
        return True
    if slot_cls == "CONJ" and word_cls == "PART":
        return True
    if slot_cls == "OTHER" and word_cls in ("NOUN", "VERB", "PART", "PREP"):
        return True
    if slot_cls == "NOUN" and word_cls in ("NOUN", "VERB", "ART"):
        return True
    if slot_cls == "ART" and word_cls == "PREP":
        return True
    if slot_cls == "PREP" and word_cls == "ART":
        return True
    return False


def _pick_gr_word_index(
    want_cls: str,
    words: list[str],
    used: list[bool],
    *,
    allow_any: bool = True,
) -> int | None:
    for wi, w in enumerate(words):
        if used[wi]:
            continue
        if _lxx_class_compatible(want_cls, _gr_token_class(w)):
            return wi
    if not allow_any:
        return None
    if want_cls in ("PREP", "CONJ", "ART"):
        return None
    for wi, _w in enumerate(words):
        if not used[wi]:
            return wi
    return None


def _reorder_gr_words_for_slots(
    slots: list[tuple[dict, str, int | None]],
    words: list[str],
) -> list[str]:
    """Reordena tokens griegos cuando el orden LXX ≠ orden morfológico hebreo."""
    n = len(words)
    if n < 2:
        return words
    m = min(n, len(slots))
    if m < 2:
        return words

    slot_cls = [_slot_morph_class(hw, st, sk) for hw, st, sk in slots[:m]]
    word_cls = [_gr_token_class(w) for w in words[:m]]

    if m == 2:
        for perm in ((0, 1), (1, 0)):
            ok = all(
                _lxx_class_compatible(slot_cls[i], word_cls[perm[i]])
                for i in range(2)
            )
            if ok and perm != (0, 1):
                return [words[perm[0]], words[perm[1]]] + words[m:]
            if ok and perm == (0, 1):
                return words
        # Postpositivo δὲ / οὖν tras verbo (verbo+partícula con slots CONJ+VERB)
        if (
            slot_cls[0] == "CONJ"
            and slot_cls[1] == "VERB"
            and word_cls[0] == "VERB"
            and word_cls[1] == "PART"
        ):
            return [words[1], words[0]] + words[m:]
        # ἐν δὲ — prep+partícula con slots CONJ+PREP
        if (
            slot_cls[0] == "CONJ"
            and slot_cls[1] == "PREP"
            and word_cls[0] == "PREP"
            and word_cls[1] == "PART"
        ):
            return [words[1], words[0]] + words[m:]
    return words


def _iter_hw_gr_slots(hw: dict):
    """Slots griegos en orden: prefijos (salvo אֵת), stem, prs_suffix."""
    pfx_m = hw.get("prefix_morphs") or []
    pfx_f = hw.get("prefix_forms") or []
    for k, pm in enumerate(pfx_m):
        if pm == "PART.OBJ.DIR":
            continue
        if k < len(pfx_f) and not (pfx_f[k] or "").strip():
            continue
        yield ("prefix", k)

    morph = hw.get("he_morph") or ""
    he = (hw.get("he_form") or "").strip()
    prs = hw.get("prs_suffix") if isinstance(hw.get("prs_suffix"), dict) else {}
    prs_he = (prs.get("he_form") or "").strip()

    if he and not morph.startswith("PRS"):
        yield ("stem", None)
    elif morph.startswith("PRS") and he:
        yield ("stem", None)

    if prs_he:
        yield ("prs", None)


def _ensure_prefix_gr_len(hw: dict, k: int) -> None:
    pgr = hw.setdefault("prefix_gr", [])
    while len(pgr) <= k:
        pgr.append("")


def _sync_pair_gr_lxx(pair: dict) -> bool:
    """Reparte pair.gr_unicode en prefix_gr / gr_word / prs_suffix.gr_word (B8)."""
    kind = pair.get("kind") or "align"
    if kind == "heb_omit":
        return False

    gr = (pair.get("gr_unicode") or "").strip()
    if not gr:
        return False

    hws = [hw for hw in (pair.get("he_words") or []) if not _is_meta_hw(hw)]
    if not hws:
        return False

    words = gr.split()
    slots: list[tuple[dict, str, int | None]] = []
    for hw in hws:
        for slot in _iter_hw_gr_slots(hw):
            slots.append((hw, slot[0], slot[1]))

    for hw in hws:
        _clear_hw_gr_slots(hw)

    if not slots:
        hws[-1]["gr_word"] = _san_gr(gr)
        hws[-1]["gr_source"] = "patch_lxx"
        return True

    words = _reorder_gr_words_for_slots(slots, words)
    if len(slots) >= 2 and len(words) >= 2:
        head = _reorder_gr_words_for_slots(slots[:2], words[:2])
        words = head[:2] + words[2:]

    words = _reorder_gr_words_for_slots(slots, words)
    if len(slots) >= 2 and len(words) >= 2:
        head = _reorder_gr_words_for_slots(slots[:2], words[:2])
        words = head[:2] + words[2:]

    used = [False] * len(words)
    for idx, (hw, stype, sk) in enumerate(slots):
        prs_remaining = sum(1 for _, t, _ in slots[idx + 1:] if t == "prs")
        stem_remaining = sum(1 for _, t, _ in slots[idx + 1:] if t == "stem")
        want = _slot_morph_class(hw, stype, sk)

        if stype == "prefix":
            _ensure_prefix_gr_len(hw, sk)
            wi = _pick_gr_word_index(want, words, used)
            if wi is not None:
                used[wi] = True
                hw["prefix_gr"][sk] = _san_gr(words[wi])
            else:
                hw["prefix_gr"][sk] = ""
        elif stype == "stem":
            if stem_remaining == 0:
                chunk_idxs = [wi for wi in range(len(words)) if not used[wi]]
                if prs_remaining:
                    chunk_idxs = chunk_idxs[: max(0, len(chunk_idxs) - prs_remaining)]
                chunk = [words[wi] for wi in chunk_idxs]
                for wi in chunk_idxs:
                    used[wi] = True
                hw["gr_word"] = _san_gr(" ".join(chunk))
            else:
                wi = _pick_gr_word_index(want, words, used)
                if wi is not None:
                    used[wi] = True
                    hw["gr_word"] = _san_gr(words[wi])
                else:
                    hw["gr_word"] = ""
            hw["gr_source"] = "patch_lxx"
        elif stype == "prs":
            wi = _pick_gr_word_index("PRON", words, used, allow_any=True)
            if wi is not None:
                used[wi] = True
                hw.setdefault("prs_suffix", {})["gr_word"] = _san_gr(words[wi])
            else:
                hw.setdefault("prs_suffix", {})["gr_word"] = ""

    return True


def _swap_hw_gr_postpositive(hw: dict) -> bool:
    """Corrige X+δὲ invertido: partícula postpositiva en stem, lexema en CONJ."""
    pgr = hw.get("prefix_gr") or []
    gw = (hw.get("gr_word") or "").strip()
    if not pgr or not gw:
        return False
    pm = (hw.get("prefix_morphs") or [""])[0]
    pt = (pgr[0] or "").strip()
    if not pt:
        return False
    if (
        pm == "CONJ"
        and _gr_token_class(gw) == "PART"
        and _gr_token_class(pt) != "PART"
    ):
        hw["prefix_gr"] = [gw]
        hw["gr_word"] = pt
        hw["gr_source"] = "patch_lxx"
        return True
    return False


def _fix_lone_greek_on_prefix(hw: dict) -> bool:
    """Un solo token griego en prefijo CONJ/PREP con stem vacío → mover al stem."""
    pgr = hw.get("prefix_gr") or []
    pm = hw.get("prefix_morphs") or []
    gw = (hw.get("gr_word") or "").strip()
    if gw or not pgr or not (pgr[0] or "").strip():
        return False
    pt = (pgr[0] or "").strip()
    wcls = _gr_token_class(pt)
    if not pm:
        return False
    if pm[0] == "CONJ" and wcls != "PART":
        hw["prefix_gr"] = [""]
        hw["gr_word"] = pt
        hw["gr_source"] = "patch_lxx"
        return True
    if pm[0] == "PREP" and wcls in ("VERB", "NOUN", "PRON"):
        hw["prefix_gr"] = [""]
        hw["gr_word"] = pt
        hw["gr_source"] = "patch_lxx"
        return True
    return False


def _split_leading_article_stem(hw: dict) -> bool:
    """τὸ/τὴν/τοὺς + resto en stem → ART en prefix_gr + resto en stem."""
    gw = (hw.get("gr_word") or "").strip()
    if not gw or " " not in gw:
        return False
    art, rest = gw.split(None, 1)
    if _gr_token_class(art) != "ART" or not rest.strip():
        return False
    raw = hw.get("raw") or ""
    morph = hw.get("he_morph") or ""
    if raw not in (
        "HWLYD/W", "M/BRK/YK", "W/MQLL/K", "HPRD", "$XT", "NPWC", "HLWK", "R(Y", "R(/Y", "R(/YK",
    ) and "VERBO" not in morph:
        return False
    pgr = list(hw.get("prefix_gr") or [])
    pm = list(hw.get("prefix_morphs") or [])
    pe = list(hw.get("prefix_es") or [])
    if pgr and _gr_token_class(pgr[0] or "") == "ART":
        pgr[0] = art
    else:
        pgr.insert(0, art)
        pm.insert(0, "ART")
        pe.insert(0, "")
    while len(pe) < len(pm):
        pe.append("")
    hw["prefix_gr"] = pgr
    hw["prefix_morphs"] = pm
    hw["prefix_es"] = pe
    hw["gr_word"] = rest.strip()
    hw["gr_source"] = "patch_lxx"
    return True


def _fix_b_prep_article_noun(hw: dict) -> bool:
    """Prep hebrea (ב/ל/מ/כ) sin equivalente griego: artículo → slot ART, PREP vacío."""
    raw = hw.get("raw") or ""
    if not (
        raw.startswith(("B/", "L/", "M/", "K/"))
        or raw in ("K/(PR", "L/PNY", "M/HKWT", "L/)L")
    ):
        return False
    pgr = list(hw.get("prefix_gr") or [])
    pm = list(hw.get("prefix_morphs") or [])
    pe = list(hw.get("prefix_es") or [])
    gw = (hw.get("gr_word") or "").strip()

    def _move_art_to_slot(art_tok: str) -> bool:
        hw["prefix_gr"] = ["", art_tok]
        hw["prefix_morphs"] = ["PREP", "ART"]
        hw["prefix_es"] = [pe[0] if pe else "", pe[1] if len(pe) > 1 else ""]
        hw["gr_source"] = "patch_lxx"
        return True

    if len(pgr) >= 2 and len(pm) >= 2 and pm[0] == "PREP" and pm[1] == "ART":
        if _gr_token_class(pgr[0] or "") == "ART" and _gr_token_class(pgr[1] or "") == "NOUN":
            hw["prefix_gr"] = ["", pgr[0]]
            hw["prefix_morphs"] = ["PREP", "ART"]
            hw["prefix_es"] = [pe[0] if pe else "", pe[1] if len(pe) > 1 else ""]
            hw["gr_word"] = pgr[1]
            hw["gr_source"] = "patch_lxx"
            return True
        if _gr_token_class(pgr[0] or "") == "ART" and not (pgr[1] or "").strip() and gw:
            return _move_art_to_slot(pgr[0])
    if len(pgr) == 1 and pm and pm[0] == "PREP" and _gr_token_class(pgr[0] or "") == "ART":
        return _move_art_to_slot(pgr[0])
    if len(pgr) == 1 and pm and pm[0] == "PREP" and _gr_token_class(pgr[0] or "") == "PART":
        return False
    return False


def _fix_hsyb_object_phrase(hw: dict) -> bool:
    """14:16 H$YB — objeto τὰ ὑπάρχοντα αὐτοῦ fuera del stem verbal."""
    if (hw.get("raw") or "") != "H$YB":
        return False
    gw = (hw.get("gr_word") or "").strip()
    if not gw.startswith("τὰ ") and not gw.startswith("τα "):
        return False
    rest = gw.split(None, 1)[1] if " " in gw else gw
    parts = rest.split()
    prs = ""
    if parts and _gr_token_class(parts[-1]) == "PRON":
        prs = parts[-1]
        rest = " ".join(parts[:-1])
    pgr = list(hw.get("prefix_gr") or [])
    pm = list(hw.get("prefix_morphs") or [])
    pe = list(hw.get("prefix_es") or [])
    if pgr and (pgr[0] or "").strip() == "καὶ":
        pgr.append("τὰ")
        pm.append("ART")
        pe.append("")
    else:
        pgr = ["τὰ"]
        pm = ["ART"]
        pe = [""]
    hw["prefix_gr"] = pgr
    hw["prefix_morphs"] = pm
    hw["prefix_es"] = pe
    hw["gr_word"] = rest
    if prs:
        hw.setdefault("prs_suffix", {})["gr_word"] = prs
    hw["gr_source"] = "patch_lxx"
    return True


def _gen11_fix_xy_lived_lxx(verse: dict) -> None:
    """Genealogía 11: καὶ ἔζησεν + nombre en par siguiente (W/NAME + XY חַי)."""
    pairs = verse.get("pairs", [])
    for i in range(len(pairs) - 1):
        hw0 = ((pairs[i].get("he_words") or [None])[0])
        hw1 = ((pairs[i + 1].get("he_words") or [None])[0])
        if not hw0 or not hw1:
            continue
        if hw1.get("raw") != "XY" or "VERBO" not in (hw1.get("he_morph") or ""):
            continue
        if "NPROP" not in (hw0.get("he_morph") or ""):
            continue
        gr0 = (pairs[i].get("gr_unicode") or "").strip()
        gr1 = (pairs[i + 1].get("gr_unicode") or "").strip()
        if not gr0.startswith("καὶ ") or not gr1:
            continue
        bits = gr0.split(None, 1)
        if len(bits) != 2:
            continue
        conj, verb = bits[0], bits[1]
        pgr0 = list(hw0.get("prefix_gr") or [])
        pm0 = list(hw0.get("prefix_morphs") or [])
        pe0 = list(hw0.get("prefix_es") or [])
        if not pgr0 or (pm0[0] if pm0 else "") != "CONJ":
            pgr0, pm0, pe0 = [conj], ["CONJ"], ["y"]
        else:
            pgr0[0] = conj
        hw0["prefix_gr"] = pgr0
        hw0["prefix_morphs"] = pm0
        hw0["prefix_es"] = pe0
        hw0["gr_word"] = gr1
        hw0["gr_source"] = "patch_lxx"
        hw1["prefix_gr"] = []
        hw1["prefix_morphs"] = []
        hw1["prefix_es"] = []
        hw1["gr_word"] = verb
        hw1["gr_source"] = "patch_lxx"


def _gen14_v14_ylydy_yrdp_lxx(pairs: list) -> None:
    """14:14 — gr_unicode καὶ κατεδίωξεν: par YLYDY → par W/YRDP (antes del sync)."""
    ylydy_p = yrdp_p = None
    for p in pairs:
        for hw in p.get("he_words") or []:
            raw = hw.get("raw") or ""
            if raw == "YLYDY":
                ylydy_p = p
            elif raw == "W/YRDP":
                yrdp_p = p
    if not ylydy_p or not yrdp_p:
        return
    gr = (ylydy_p.get("gr_unicode") or "").strip()
    if not gr:
        return
    if _norm_gr_token(gr.split()[-1]) != "κατεδιωξεν":
        return
    yrdp_p["gr_unicode"] = gr
    ylydy_p["gr_unicode"] = ""
    for hw in ylydy_p.get("he_words") or []:
        _clear_hw_gr_slots(hw)


def _gen14_v17_move_touto_en_gr(pairs: list) -> None:
    """14:17 — gr_unicode τοῦτο ἦν: par )L → par HW)."""
    el_p = hw_p = None
    for p in pairs:
        for hw in p.get("he_words") or []:
            raw = hw.get("raw") or ""
            if raw == ")L" and (hw.get("he_morph") or "").startswith("PREP"):
                el_p = p
            elif raw == "HW)":
                hw_p = p
    if not el_p or not hw_p:
        return
    gr = (el_p.get("gr_unicode") or "").strip()
    if not gr or _norm_gr_token(gr.split()[0]) != "τουτο":
        return
    hw_p["gr_unicode"] = gr
    el_p["gr_unicode"] = ""
    for hw in el_p.get("he_words") or []:
        _clear_hw_gr_slots(hw)


def _fix_greek_prep_in_stem_with_art_prefix(hw: dict) -> bool:
    """Prep griega en stem con artículo en slot PREP (ej. 13:18 παρὰ τὴν δρῦν)."""
    pgr = list(hw.get("prefix_gr") or [])
    pm = list(hw.get("prefix_morphs") or [])
    pe = list(hw.get("prefix_es") or [])
    gw = (hw.get("gr_word") or "").strip()
    if not gw or not pgr or not pm:
        return False
    if pm[0] != "PREP" or _gr_token_class(pgr[0] or "") != "ART":
        return False
    prep_tok = gw.split(None, 1)[0] if gw else ""
    if _gr_token_class(prep_tok) != "PREP" and _gr_token_class(gw) != "PREP":
        return False
    if _gr_token_class(gw) == "PREP":
        prep_tok = gw
        rest = ""
    else:
        rest = gw.split(None, 1)[1].strip() if " " in gw else ""
    art_tok = pgr[0]
    pgr[0] = prep_tok
    if len(pgr) >= 2 and pm[1] == "ART":
        pgr[1] = art_tok
    else:
        pgr = [prep_tok, art_tok]
        pm = ["PREP", "ART"]
        pe = [pe[0] if pe else "", ""]
    hw["prefix_gr"] = pgr
    hw["prefix_morphs"] = pm
    hw["prefix_es"] = pe
    hw["gr_word"] = rest
    hw["gr_source"] = "patch_lxx"
    return True


def _gen14_v17_el_touto_en_lxx(pairs: list) -> None:
    """14:17 — τοῦτο ἦν en prep )L → pron HW)."""
    el_hw = hw_hw = None
    el_pair = None
    for p in pairs:
        for hw in p.get("he_words") or []:
            raw = hw.get("raw") or ""
            if raw == ")L" and (hw.get("he_morph") or "").startswith("PREP"):
                el_hw = hw
                el_pair = p
            elif raw == "HW)":
                hw_hw = hw
    if not el_hw:
        return
    gw = (el_hw.get("gr_word") or "").strip()
    if not gw and el_pair is not None:
        gw = (el_pair.get("gr_unicode") or "").strip()
    if not gw:
        return
    if _norm_gr_token(gw.split()[0]) != "τουτο":
        return
    el_hw["gr_word"] = ""
    el_hw["gr_source"] = "patch_lxx"
    if hw_hw is not None:
        hw_hw["gr_word"] = gw
        hw_hw["gr_source"] = "patch_lxx"
    for p in pairs:
        for hw in p.get("he_words") or []:
            if (hw.get("raw") or "") != "(MQ":
                continue
            stem = (hw.get("gr_word") or "").strip()
            if gw and gw in stem:
                hw["gr_word"] = stem.replace(gw, "").strip()
                if hw["gr_word"].startswith("τὸ "):
                    hw["gr_word"] = hw["gr_word"].split(None, 1)[1]
                hw["gr_source"] = "patch_lxx"


def _split_leading_particle_to_prefix(hw: dict) -> bool:
    """καὶ / ἵνα / τοῦ al inicio del stem → prefix_gr (solo si hay slot compatible)."""
    gw = (hw.get("gr_word") or "").strip()
    if not gw:
        return False
    splits = (
        ("καὶ ", "CONJ", "y"),
        ("ἵνα ", "CONJ", ""),
        ("τοῦ ", "ART", ""),
        ("τὸ ", "ART", ""),
        ("τὴν ", "ART", ""),
    )
    for prefix, morph, es in splits:
        if not gw.startswith(prefix):
            continue
        rest = gw[len(prefix):].strip()
        if not rest:
            continue
        pgr = list(hw.get("prefix_gr") or [])
        pm = list(hw.get("prefix_morphs") or [])
        pe = list(hw.get("prefix_es") or [])
        tok = prefix.strip()
        if morph == "CONJ" and pgr and (pgr[0] or "").strip():
            hw["gr_word"] = rest
            hw["gr_source"] = "patch_lxx"
            return True
        if morph == "ART":
            art_k = next(
                (
                    k for k, m in enumerate(pm)
                    if m == "ART" and (k >= len(pgr) or not (pgr[k] or "").strip())
                ),
                None,
            )
            if art_k is None:
                return False
            while len(pgr) <= art_k:
                pgr.append("")
            while len(pe) <= art_k:
                pe.append("")
            pgr[art_k] = tok
            hw["prefix_gr"] = pgr
            hw["prefix_morphs"] = pm
            hw["prefix_es"] = pe
            hw["gr_word"] = rest
            hw["gr_source"] = "patch_lxx"
            return True
        if not (pgr and (pgr[0] or "").strip()):
            pgr.insert(0, tok)
            pm.insert(0, morph)
            pe.insert(0, es)
            hw["prefix_gr"] = pgr
            hw["prefix_morphs"] = pm
            hw["prefix_es"] = pe
            hw["gr_word"] = rest
            hw["gr_source"] = "patch_lxx"
            return True
        return False
    return False


def _pair_lxx_tokens_counter(pair: dict) -> Counter:
    """Tokens griegos normalizados asignados en un par."""
    c: Counter[str] = Counter()
    for hw in pair.get("he_words") or []:
        if _is_meta_hw(hw):
            continue
        for pg in hw.get("prefix_gr") or []:
            for w in (pg or "").split():
                n = _norm_gr_token(w)
                if n:
                    c[n] += 1
        for w in (hw.get("gr_word") or "").split():
            n = _norm_gr_token(w)
            if n:
                c[n] += 1
        prs = hw.get("prs_suffix") or {}
        if isinstance(prs, dict):
            for w in (prs.get("gr_word") or "").split():
                n = _norm_gr_token(w)
                if n:
                    c[n] += 1
    return c


def _pair_source_tokens_counter(pair: dict) -> Counter:
    c: Counter[str] = Counter()
    for w in ((pair.get("gr_unicode") or "").split()):
        n = _norm_gr_token(w)
        if n:
            c[n] += 1
    return c


def _strip_prs_gr_dup_from_stem(hw: dict) -> bool:
    """Quita del stem tokens ya asignados en prs_suffix.gr_word (evita gr_sobra B8)."""
    prs = hw.get("prs_suffix") or {}
    if not isinstance(prs, dict):
        return False
    prs_gr = (prs.get("gr_word") or "").strip()
    if not prs_gr:
        return False
    prs_norm = {_norm_gr_token(w) for w in prs_gr.split()}
    gw = (hw.get("gr_word") or "").strip()
    if not gw:
        return False
    kept: list[str] = []
    changed = False
    for w in gw.split():
        if _norm_gr_token(w) in prs_norm:
            changed = True
            continue
        kept.append(w)
    if changed:
        hw["gr_word"] = _san_gr(" ".join(kept))
        hw["gr_source"] = "patch_lxx"
    return changed


def _strip_assigned_gr_dup_from_stem(hw: dict) -> bool:
    """Quita del stem tokens ya en prefix_gr o prs (p. ej. ἂν duplicado)."""
    assigned: set[str] = set()
    for pg in hw.get("prefix_gr") or []:
        for w in (pg or "").split():
            n = _norm_gr_token(w)
            if n:
                assigned.add(n)
    prs = hw.get("prs_suffix") or {}
    if isinstance(prs, dict):
        for w in (prs.get("gr_word") or "").split():
            n = _norm_gr_token(w)
            if n:
                assigned.add(n)
    gw = (hw.get("gr_word") or "").strip()
    if not gw:
        return False
    kept: list[str] = []
    changed = False
    for w in gw.split():
        n = _norm_gr_token(w)
        if n in assigned:
            changed = True
            continue
        kept.append(w)
    if changed:
        hw["gr_word"] = _san_gr(" ".join(kept))
        hw["gr_source"] = "patch_lxx"
    return changed


def _dedupe_hw_gr_slots(hw: dict) -> None:
    _strip_prs_gr_dup_from_stem(hw)
    if (hw.get("raw") or "") not in ("GKADD", "=<LXX>"):
        _strip_assigned_gr_dup_from_stem(hw)


def _assign_trailing_pron_to_prs(hw: dict, gr_words: list[str]) -> bool:
    """Mueve pronombre final de gr_word a prs_suffix si hay sufijo hebreo PRS."""
    prs = hw.get("prs_suffix") or {}
    if not isinstance(prs, dict):
        return False
    if not (prs.get("he_form") or "").strip():
        return False
    if (prs.get("gr_word") or "").strip():
        return False
    gw = (hw.get("gr_word") or "").strip()
    if not gw or " " not in gw:
        return False
    parts = gw.split()
    last = parts[-1]
    if _gr_token_class(last) != "PRON":
        return False
    if not any(_norm_gr_token(w) == _norm_gr_token(last) for w in gr_words):
        return False
    prs["gr_word"] = _san_gr(last)
    hw["gr_word"] = _san_gr(" ".join(parts[:-1]))
    hw["prs_suffix"] = prs
    hw["gr_source"] = "patch_lxx"
    return True


def _repair_pair_lxx_coverage(pair: dict) -> bool:
    """Completa tokens LXX faltantes del par según gr_unicode."""
    src = _pair_source_tokens_counter(pair)
    if not src:
        return False
    got = _pair_lxx_tokens_counter(pair)
    if got == src:
        return False

    missing = src - got
    if not missing:
        return False

    gr_words = (pair.get("gr_unicode") or "").split()
    changed = False

    for hw in pair.get("he_words") or []:
        if _is_meta_hw(hw):
            continue
        pm = hw.get("prefix_morphs") or []
        pgr = list(hw.get("prefix_gr") or [])
        pe = list(hw.get("prefix_es") or [])
        for k, morph in enumerate(pm):
            if morph == "PART.OBJ.DIR":
                continue
            if k < len(pgr) and (pgr[k] or "").strip():
                continue
            for wi, raw in enumerate(gr_words):
                n = _norm_gr_token(raw)
                if not n or missing[n] <= 0:
                    continue
                wcls = _gr_token_class(raw)
                slot = "CONJ" if morph == "CONJ" else (
                    "PREP" if morph == "PREP" else ("ART" if morph == "ART" else "OTHER")
                )
                if not _lxx_class_compatible(slot, wcls):
                    continue
                while len(pgr) <= k:
                    pgr.append("")
                while len(pe) <= k:
                    pe.append("")
                pgr[k] = _san_gr(raw)
                missing[n] -= 1
                changed = True
                break
        if changed:
            hw["prefix_gr"] = pgr
            hw["prefix_es"] = pe

    got = _pair_lxx_tokens_counter(pair)
    missing = src - got
    if not missing:
        return changed

    ordered_missing = []
    for raw in gr_words:
        n = _norm_gr_token(raw)
        if n and missing.get(n, 0) > 0:
            ordered_missing.append(_san_gr(raw))
            missing[n] -= 1

    if not ordered_missing:
        return changed

    hws = [hw for hw in (pair.get("he_words") or []) if not _is_meta_hw(hw)]
    if not hws:
        return changed

    for hw in hws:
        prs = hw.get("prs_suffix") or {}
        if not isinstance(prs, dict):
            continue
        prs_he = (prs.get("he_form") or "").strip()
        prs_gr = (prs.get("gr_word") or "").strip()
        if prs_he and not prs_gr:
            for wi, raw in enumerate(gr_words):
                n = _norm_gr_token(raw)
                if not n or missing.get(n, 0) <= 0:
                    continue
                if _gr_token_class(raw) != "PRON":
                    continue
                prs["gr_word"] = _san_gr(raw)
                missing[n] -= 1
                changed = True
                hw["prs_suffix"] = prs
                break

    got = _pair_lxx_tokens_counter(pair)
    missing = src - got
    if not missing:
        return changed

    ordered_missing = []
    for raw in gr_words:
        n = _norm_gr_token(raw)
        if n and missing.get(n, 0) > 0:
            ordered_missing.append(_san_gr(raw))
            missing[n] -= 1

    if not ordered_missing:
        return changed

    hw = hws[-1]
    prs = hw.get("prs_suffix") or {}
    prs_norm: set[str] = set()
    if isinstance(prs, dict) and (prs.get("gr_word") or "").strip():
        prs_norm = {_norm_gr_token(w) for w in (prs.get("gr_word") or "").split()}

    stem_missing: list[str] = []
    for raw in ordered_missing:
        n = _norm_gr_token(raw)
        if n in prs_norm:
            continue
        if (
            isinstance(prs, dict)
            and (prs.get("he_form") or "").strip()
            and not (prs.get("gr_word") or "").strip()
            and _gr_token_class(raw) == "PRON"
        ):
            prs["gr_word"] = _san_gr(raw)
            prs_norm.add(n)
            hw["prs_suffix"] = prs
            changed = True
            continue
        stem_missing.append(raw)

    gw = (hw.get("gr_word") or "").strip()
    if stem_missing or gw:
        hw["gr_word"] = _san_gr(" ".join(stem_missing + ([gw] if gw else [])))
        hw["gr_source"] = "patch_lxx"
        changed = True
    _strip_prs_gr_dup_from_stem(hw)
    if (hw.get("raw") or "") not in ("GKADD", "=<LXX>"):
        _strip_assigned_gr_dup_from_stem(hw)
    return changed


def _post_sync_gr_hw(hw: dict) -> None:
    _swap_hw_gr_postpositive(hw)
    _fix_lone_greek_on_prefix(hw)
    _split_leading_article_stem(hw)
    _fix_b_prep_article_noun(hw)
    _fix_greek_prep_in_stem_with_art_prefix(hw)
    _split_leading_particle_to_prefix(hw)
    _fix_hsyb_object_phrase(hw)


def _pair_has_assignable_hw(pair: dict) -> bool:
    for hw in pair.get("he_words") or []:
        raw = hw.get("raw") or ""
        if raw in ("GKADD", "=<LXX>"):
            continue
        if _is_meta_hw(hw):
            continue
        if raw and not raw.startswith("="):
            return True
    return False


def _ensure_pair_gr_hw_stub(pair: dict) -> bool:
    """Par/gk_add con gr_unicode pero sin he_words asignables → hw mínimo LXX."""
    for hw in pair.get("he_words") or []:
        if (hw.get("raw") or "") == "=<LXX>":
            hw["raw"] = "GKADD"
    gr = (pair.get("gr_unicode") or "").strip()
    if not gr or _pair_has_assignable_hw(pair):
        return False
    words = gr.split()
    stub: dict = {
        "raw": "GKADD",
        "he_form": "",
        "he_morph": "",
        "es_source": "patch_meta",
    }
    if len(words) >= 2 and _gr_token_class(words[0]) in ("PART", "CONJ"):
        stub["prefix_gr"] = [_san_gr(words[0])]
        stub["prefix_morphs"] = ["CONJ"]
        stub["prefix_es"] = ["y"]
        stub["gr_word"] = _san_gr(" ".join(words[1:]))
    elif len(words) >= 2 and _gr_token_class(words[0]) == "PREP":
        stub["prefix_gr"] = [_san_gr(words[0])]
        stub["prefix_morphs"] = ["PREP"]
        stub["prefix_es"] = [""]
        stub["gr_word"] = _san_gr(" ".join(words[1:]))
    else:
        stub["gr_word"] = _san_gr(gr)
    stub["gr_source"] = "patch_lxx"
    pair["he_words"] = [stub]
    return True


def _expand_gr_surfaces_by_tokens(pair: dict) -> bool:
    """Reparte artículos/partículas griegas a prefix_gr (una palabra LXX por slot visible)."""
    if pair.get("kind") in ("gk_add", "heb_omit"):
        return False
    raw_words = (pair.get("gr_unicode") or "").split()
    gtoks = pair.get("gr_tokens") or []
    if len(raw_words) < 2 or len(gtoks) != len(raw_words):
        return False
    hws = [h for h in (pair.get("he_words") or []) if not _is_meta_hw(h)]
    if len(hws) != 1:
        return False
    hw = hws[0]
    surfaces = [_san_gr(w) for w in raw_words]

    prefix_surfaces: list[tuple[str, str]] = []
    stem_surfaces: list[str] = []
    for surf, gt in zip(surfaces, gtoks):
        pos = (gt.get("pos") or "").upper()
        wcls = _gr_token_class(surf)
        if pos in ("RA", "X", "C", "D", "P") or wcls in ("ART", "PART", "CONJ", "PREP"):
            morph = (
                "ART" if pos == "RA" or wcls == "ART"
                else "CONJ" if pos in ("C", "X") or wcls in ("CONJ", "PART")
                else "PREP" if wcls == "PREP"
                else "PART"
            )
            prefix_surfaces.append((surf, morph))
        else:
            stem_surfaces.append(surf)

    if not prefix_surfaces:
        return False

    pgr = list(hw.get("prefix_gr") or [])
    pm = list(hw.get("prefix_morphs") or [])
    pf = list(hw.get("prefix_forms") or [])
    pe = list(hw.get("prefix_es") or [])
    prefixes = list(hw.get("prefixes") or [])

    assigned_prefix = set()
    for pg in pgr:
        for w in (pg or "").split():
            assigned_prefix.add(_norm_gr_token(w))
    gw = (hw.get("gr_word") or "").strip()
    gw_first = _norm_gr_token(gw.split()[0]) if gw else ""

    changed = False
    insert_at = 0
    for surf, morph in prefix_surfaces:
        sn = _norm_gr_token(surf)
        if sn in assigned_prefix:
            continue
        if sn == gw_first and " " in gw:
            rest = " ".join(gw.split()[1:]).strip()
            hw["gr_word"] = rest
            gw = rest
            gw_first = _norm_gr_token(gw.split()[0]) if gw else ""
            changed = True
        while insert_at < len(pgr) and (pgr[insert_at] or "").strip():
            insert_at += 1
        if insert_at < len(pgr):
            pgr[insert_at] = surf
            if insert_at < len(pm):
                pm[insert_at] = morph
            assigned_prefix.add(sn)
            changed = True
            insert_at += 1
        else:
            pf.insert(insert_at, "·")
            pm.insert(insert_at, morph)
            pgr.insert(insert_at, surf)
            pe.insert(insert_at, "")
            prefixes.insert(insert_at, "")
            assigned_prefix.add(sn)
            changed = True
            insert_at += 1

    prs = hw.get("prs_suffix") or {}
    if (
        stem_surfaces
        and isinstance(prs, dict)
        and (prs.get("he_form") or "").strip()
        and not (prs.get("gr_word") or "").strip()
        and _gr_token_class(stem_surfaces[-1]) == "PRON"
    ):
        prs["gr_word"] = _san_gr(stem_surfaces.pop())

    if stem_surfaces:
        new_gw = " ".join(stem_surfaces)
        if gw != new_gw:
            hw["gr_word"] = new_gw
            changed = True

    if isinstance(prs, dict) and prs.get("gr_word"):
        hw["prs_suffix"] = prs
        changed = True
    _dedupe_hw_gr_slots(hw)

    if changed:
        hw["prefix_forms"] = pf
        hw["prefix_morphs"] = pm
        hw["prefix_gr"] = pgr
        hw["prefix_es"] = pe
        hw["prefixes"] = prefixes
        hw["gr_source"] = "patch_lxx"
    return changed


def _fix_lxx_align_verse(verse: dict) -> None:
    """B8 — reparte gr_unicode en prefix_gr / gr_word / prs por morfema."""
    for p in verse.get("pairs", []):
        _ensure_pair_gr_hw_stub(p)
    for p in verse.get("pairs", []):
        _sync_pair_gr_lxx(p)
    for p in verse.get("pairs", []):
        _expand_gr_surfaces_by_tokens(p)
    for p in verse.get("pairs", []):
        for hw in p.get("he_words") or []:
            if _is_meta_hw(hw):
                continue
            _post_sync_gr_hw(hw)
    for p in verse.get("pairs", []):
        _repair_pair_lxx_coverage(p)
    for p in verse.get("pairs", []):
        for hw in p.get("he_words") or []:
            if _is_meta_hw(hw):
                continue
            _dedupe_hw_gr_slots(hw)


def _fix_gen8_lxx_align(verse: dict) -> None:
    _fix_lxx_align_verse(verse)


def _fix_gen9_lxx_align(verse: dict) -> None:
    _fix_lxx_align_verse(verse)


def _fix_gen10_lxx_align(verse: dict) -> None:
    _fix_lxx_align_verse(verse)


def _fix_gen11_lxx_align(verse: dict) -> None:
    _fix_lxx_align_verse(verse)


def _fix_gen12_lxx_align(verse: dict) -> None:
    """B8 — reparto LXX por morfema tras splits OSHB cap. 12."""
    _fix_lxx_align_verse(verse)

# IN_FILE / OUT_FILE se resuelven en main() a partir de --book (default: genesis).
# Estos valores se mantienen como fallback para imports directos del módulo.
IN_FILE  = Path(__file__).parent.parent / "data" / "genesis_final.json"
OUT_FILE = IN_FILE
ACTIVE_BOOK = "genesis"
ACTIVE_LABEL = "Génesis"
ACTIVE_CODE = "Gen"

CORRECTIONS = {

    # ════════════════════════════════════════════════════════════════════
    #  GÉNESIS 1:1  (11 elementos)
    # ════════════════════════════════════════════════════════════════════
    "1:1": [
        # par B/R)$YT → PRE בְּ + STEM רֵאשִׁית
        ("בְּ",       "PREP",                       "en",         "ἐν"),
        ("רֵאשִׁית",  "SUBS.F.SG.A",                "principio",  "ἀרחῇ"),
        # par BR) → STEM בָּרָא
        ("בָּרָא",    "VERBO.QAL.PERF.P3.M.SG",    "creó",       "ἐποίησεν"),
        # par )LHYM → STEM אֱלֹהִים
        ("אֱלֹהִים",  "SUBS.M.PL.A",                "'Elohim",    "ὁ θεὸς"),
        # par )T H/$MYM → STEM אֵת | PRE הַ | STEM שָּׁמַיִם
        ("אֵת",       "PART.OBJ.DIR",               "—",          "—"),
        ("הַ",        "ART",                        "los",        "τὸν"),
        ("שָּׁמַיִם", "SUBS.M.PL.A",                "cielos",     "οὐרανὸן"),
        # par W/)T H/)RC → PRE וְ | STEM אֵת | PRE הָ | STEM אָרֶץ
        ("וְ",        "CONJ",                       "y",          "καὶ"),
        ("אֵת",       "PART.OBJ.DIR",               "—",          "—"),
        ("הָ",        "ART",                        "la",         "τὴן"),
        ("אָרֶץ",     "SUBS.BOTH.SG.A",             "tierra",     "γῆן"),
    ],

    # ════════════════════════════════════════════════════════════════════
    #  GÉNESIS 1:2  (20 elementos) — corrige griego invertido וְ/הָ
    # ════════════════════════════════════════════════════════════════════
    "1:2": [
        ("וְ",        "CONJ",                       "y",          "δὲ"),
        ("הָ",        "ART",                        "la",         "ἡ"),
        ("אָרֶץ",     "SUBS.BOTH.SG.A",             "tierra",     "γῆ"),
        ("הָיְתָה",   "VERBO.QAL.PERF.P3.F.SG",    "estaba",     "ἦν"),
        ("תֹהוּ",     "SUBS.M.SG.A",                "desordenada","ἀόרατος"),
        ("וָ",        "CONJ",                       "y",          "καὶ"),
        ("בֹהוּ",     "SUBS.M.SG.A",                "vacía",      "ἀκατασκεύαστος"),
        ("וְ",        "CONJ",                       "y",          "καὶ"),
        ("חֹשֶׁךְ",   "SUBS.M.SG.A",                "tinieblas",  "σκότος"),
        ("עַל",       "PREP",                       "sobre",      "ἐπάνω"),
        ("פְּנֵי",    "SUBS.BOTH.PL.C",             "la",         "τῆς"),
        ("תְהֹום",    "SUBS.BOTH.SG.A",             "abismo",     "ἀβύσσου"),
        ("וְ",        "CONJ",                       "y",          "καὶ"),
        ("רוּחַ",     "SUBS.BOTH.SG.C",             "espíritu",   "πνεῦμα"),
        ("אֱלֹהִים",  "SUBS.M.PL.A",                "'Elohim",    "θεοῦ"),
        ("מְרַחֶפֶת", "VERBO.PIEL.PTCA.F.SG.A",    "movía",      "ἐπεφέρετο"),
        ("עַל",       "PREP",                       "sobre",      "ἐπάνω"),
        ("פְּנֵי",    "SUBS.BOTH.PL.C",             "la",         "—"),
        ("הַ",        "ART",                        "las",        "τοῦ"),
        ("מָּיִם",    "SUBS.M.PL.A",                "aguas",      "ὕδατος"),
    ],

    # ════════════════════════════════════════════════════════════════════
    #  GÉNESIS 1:3  (8 elementos)
    # ════════════════════════════════════════════════════════════════════
    "1:3": [
        ("וַ",        "CONJ",                       "y",          "καὶ"),
        ("יֹּאמֶר",   "VERBO.QAL.WAYYIQT.P3.M.SG", "dijo",       "εἶπεν"),
        ("אֱלֹהִים",  "SUBS.M.PL.A",                "'Elohim",    "ὁ θεός"),
        ("יְהִי",     "VERBO.QAL.JUSS.P3.M.SG",    "sea",        "γενηθήτω"),
        ("אֹור",      "SUBS.BOTH.SG.A",             "luz",        "φῶς"),
        ("וַ",        "CONJ",                       "y",          "καὶ"),
        ("יְהִי",     "VERBO.QAL.WAYYIQT.P3.M.SG", "fue",        "ἐγένετο"),
        ("אֹור",      "SUBS.BOTH.SG.A",             "luz",        "φῶς"),
    ],

    # ════════════════════════════════════════════════════════════════════
    #  GÉNESIS 1:4  (18 elementos) — כִּי="que", בֵּין="entre"
    # ════════════════════════════════════════════════════════════════════
    "1:4": [
        ("וַ",        "CONJ",                       "y",          "καὶ"),
        ("יַּרְא",    "VERBO.QAL.WAYYIQT.P3.M.SG", "vio",        "εἶδεν"),
        ("אֱלֹהִים",  "SUBS.M.PL.A",                "'Elohim",    "ὁ θεός"),
        ("אֶת",       "PART.OBJ.DIR",               "—",          "—"),
        ("הָ",        "ART",                        "la",         "τὸ"),
        ("אֹור",      "SUBS.BOTH.SG.A",             "luz",        "φῶς"),
        ("כִּי",      "CONJ",                       "que",        "ὅτι"),
        ("טֹוב",      "ADJ.M.SG.A",                 "buena",      "καλόν"),
        ("וַ",        "CONJ",                       "y",          "καὶ"),
        ("יַּבְדֵּל", "VERBO.HIF.WAYYIQT.P3.M.SG", "separó",     "διεχώρισεν"),
        ("אֱלֹהִים",  "SUBS.M.PL.A",                "'Elohim",    "ὁ θεός"),
        ("בֵּין",     "PREP",                       "entre",      "ἀנὰ μέσον"),
        ("הָ",        "ART",                        "la",         "τοῦ"),
        ("אֹור",      "SUBS.BOTH.SG.A",             "luz",        "φωτὸς"),
        ("וּ",        "CONJ",                       "y",          "καὶ"),
        ("בֵין",      "PREP",                       "entre",      "ἀנὰ μέσον"),
        ("הַ",        "ART",                        "las",        "τοῦ"),
        ("חֹשֶׁךְ",   "SUBS.M.SG.A",                "tinieblas",  "σκότους"),
    ],

    # ════════════════════════════════════════════════════════════════════
    #  GÉNESIS 1:5  (19 elementos)
    # ════════════════════════════════════════════════════════════════════
    "1:5": [
        ("וַ",        "CONJ",                       "y",          "καὶ"),
        ("יִּקְרָא",  "VERBO.QAL.WAYYIQT.P3.M.SG", "llamó",      "ἐκάλεσεν"),
        ("אֱלֹהִים",  "SUBS.M.PL.A",                "'Elohim",    "ὁ θεός"),
        ("לָ",        "PREP.ART",                   "al",         "τὸ"),
        ("אֹור",      "SUBS.BOTH.SG.A",             "luz",        "φῶς"),
        ("יֹום",      "SUBS.M.SG.A",                "día",        "ἡμέראן"),
        ("וְ",        "CONJ",                       "y",          "καὶ"),
        ("לַ",        "PREP.ART",                   "a las",      "τὸ"),
        ("חֹשֶׁךְ",   "SUBS.M.SG.A",                "tinieblas",  "σκότος"),
        ("קָרָא",     "VERBO.QAL.PERF.P3.M.SG",    "llamó",      "ἐκάλεσεν"),
        ("לָיְלָה",   "SUBS.M.SG.A",                "noche",      "νύκτα"),
        ("וַ",        "CONJ",                       "y",          "καὶ"),
        ("יְהִי",     "VERBO.QAL.WAYYIQT.P3.M.SG", "fue",        "ἐγένετο"),
        ("עֶרֶב",     "SUBS.M.SG.A",                "tarde",      "ἑσπέρα"),
        ("וַ",        "CONJ",                       "y",          "καὶ"),
        ("יְהִי",     "VERBO.QAL.WAYYIQT.P3.M.SG", "fue",        "ἐγένετο"),
        ("בֹקֶר",     "SUBS.M.SG.A",                "mañana",     "πρωί"),
        ("יֹום",      "SUBS.M.SG.A",                "día",        "ἡμέρα"),
        ("אֶחָד",     "NUM.CARD.M.SG.A",            "uno",        "μία"),
    ],

    # ════════════════════════════════════════════════════════════════════
    #  GÉNESIS 1:6  (16 elementos)
    #  Corrige: VqAJSM3→JUSS, VqAmSM3→WAYYIQT, βēn="entre"
    # ════════════════════════════════════════════════════════════════════
    "1:6": [
        # W/Y)MR
        ("וַ",        "CONJ",                       "y",          "καὶ"),
        ("יֹּאמֶר",   "VERBO.QAL.WAYYIQT.P3.M.SG", "dijo",       "εἶπεν"),
        # )LHYM
        ("אֱלֹהִים",  "SUBS.M.PL.A",                "'Elohim",    "ὁ θεός"),
        # YHY (jussivo)
        ("יְהִי",     "VERBO.QAL.JUSS.P3.M.SG",    "haya",       "γενηθήτω"),
        # RQY(
        ("רָקִיעַ",   "SUBS.M.SG.A",                "expansión",  "στερέωμα"),
        # B/TWK
        ("בְּ",       "PREP",                       "en",         "ἐν"),
        ("תֹוךְ",     "SUBS.M.SG.C",                "medio",      "μέσῳ"),
        # H/MYM
        ("הַ",        "ART",                        "de las",     "τοῦ"),
        ("מָּיִם",    "SUBS.M.PL.A",                "aguas",      "ὕδατος"),
        # W/YHY
        ("וִ",        "CONJ",                       "y",          "καὶ"),
        ("יְהִי",     "VERBO.QAL.JUSS.P3.M.SG",    "sea",        "ἔστω"),
        # MBDYL
        ("מַבְדִּיל", "VERBO.HIF.PTCA.M.SG.A",     "separando",  "διαחωρίζον"),
        # BYN
        ("בֵּין",     "PREP",                       "entre",      "ἀנὰ μέσον"),
        # MYM
        ("מַיִם",     "SUBS.M.PL.A",                "aguas",      "ὕδατος"),
        # L/MYM
        ("לָ",        "PREP.ART",                   "y las",      "καὶ"),
        ("מָיִם",     "SUBS.M.PL.A",                "aguas",      "ὕδατος"),
    ],

    # ════════════════════════════════════════════════════════════════════
    #  GÉNESIS 1:7  (28 elementos, FALLBACK)
    # ════════════════════════════════════════════════════════════════════
    "1:7": [
        # W/Y($H
        ("וַ",        "CONJ",                       "y",          "καὶ"),
        ("יַּעַשׂ",   "VERBO.QAL.WAYYIQT.P3.M.SG", "hizo",       "ἐποίησεν"),
        # )LHYM
        ("אֱלֹהִים",  "SUBS.M.PL.A",                "Dios",       "ὁ θεὸς"),
        # )T H/RQY( → STEM )T | PRE הָ | STEM רָקִיעַ
        ("אֶת",       "PART.OBJ.DIR",               "—",          "—"),
        ("הָ",        "ART",                        "la",         "τὸ"),
        ("רָקִיעַ",   "SUBS.M.SG.A",                "expansión",  "στερέωמα"),
        # W/YBDL
        ("וַ",        "CONJ",                       "y",          "καὶ"),
        ("יַּבְדֵּל", "VERBO.HIF.WAYYIQT.P3.M.SG", "separó",     "διεχώρισεν"),
        # [+ LXX ADD ὁ θεὸς — 0 CATSS]
        # BYN H/MYM → STEM βēn | PRE הַ | STEM מַּיִם
        ("בֵּין",     "PREP",                       "entre",      "ἀנὰ μέσον"),
        ("הַ",        "ART",                        "las",        "τοῦ"),
        ("מַּיִם",    "SUBS.M.PL.A",                "aguas",      "ὕδατος"),
        # )$R
        ("אֲשֶׁר",    "REL",                        "que",        "ὃ ἦν"),
        # M/TTXT → PRE מִ | STEM תַּחַת
        ("מִ",        "PREP",                       "de",         "—"),
        ("תַּחַת",    "PREP",                       "debajo",     "ὑποκάτω"),
        # L/RQY( → PRE לָ | STEM רָקִיעַ
        ("לָ",        "PREP.ART",                   "de la",      "τοῦ"),
        ("רָקִיעַ",   "SUBS.M.SG.A",                "expansión",  "στερεώματος"),
        # W/BYN H/MYM → PRE וּ | STEM βēn | PRE הַ | STEM מַּיִם
        ("וּ",        "CONJ",                       "y",          "καὶ"),
        ("בֵין",      "PREP",                       "entre",      "ἀנὰ μέסον"),
        ("הַ",        "ART",                        "las",        "τοῦ"),
        ("מַּיִם",    "SUBS.M.PL.A",                "aguas",      "ὕδατος"),
        # )$R
        ("אֲשֶׁר",    "REL",                        "que",        "τὸ"),
        # M/(L → PRE מֵ | STEM עַל
        ("מֵ",        "PREP",                       "de",         "—"),
        ("עַל",       "PREP",                       "sobre",      "ἐπάνω"),
        # L/RQY( → PRE לָ | STEM רָקִיעַ
        ("לָ",        "PREP.ART",                   "la",         "τοῦ"),
        ("רָקִיעַ",   "SUBS.M.SG.A",                "expansión",  "στερεώματος"),
        # W/YHY → PRE וַֽ | STEM יְהִי
        ("וַ",        "CONJ",                       "y",          "—"),
        ("יְהִי",     "VERBO.QAL.WAYYIQT.P3.M.SG", "fue",        "—"),
        # KN
        ("כֵן",       "ADV",                        "así",        "—"),
    ],

    # ════════════════════════════════════════════════════════════════════
    #  GÉNESIS 1:8  (14 elementos, FALLBACK)
    # ════════════════════════════════════════════════════════════════════
    "1:8": [
        # W/YQRA → PRE | STEM
        ("וַ",        "CONJ",                       "y",          "καὶ"),
        ("יִּקְרָא",  "VERBO.QAL.WAYYIQT.P3.M.SG", "llamó",      "ἐκάλεσεν"),
        # )LHYM
        ("אֱלֹהִים",  "SUBS.M.PL.A",                "Dios",       "ὁ θεὸς"),
        # L/RQY( → PRE לָֽ | STEM רָקִיעַ
        ("לָ",        "PREP.ART",                   "a la",       "τὸ"),
        ("רָקִיעַ",   "SUBS.M.SG.A",                "expansión",  "στερέωמα"),
        # $MYMM
        ("שָׁמָיִם",  "SUBS.M.PL.A",                "cielos",     "οὐρανόν"),
        # [+ LXX ADD ×4 — 0 CATSS]
        # W/YHY → PRE | STEM
        ("וַ",        "CONJ",                       "y",          "καὶ"),
        ("יְהִי",     "VERBO.QAL.WAYYIQT.P3.M.SG", "fue",        "ἐγένετο"),
        # (RB
        ("עֶרֶב",     "SUBS.M.SG.A",                "tarde",      "ἑσπέρα"),
        # W/YHY → PRE | STEM
        ("וַ",        "CONJ",                       "y",          "καὶ"),
        ("יְהִי",     "VERBO.QAL.WAYYIQT.P3.M.SG", "fue",        "ἐγένετο"),
        # BQR
        ("בֹקֶר",     "SUBS.M.SG.A",                "mañana",     "πρωί"),
        # YWM
        ("יוֹם",      "SUBS.M.SG.A",                "día",        "ἡμέρα"),
        # $NY
        ("שֵׁנִי",    "NUM.ORD.M.SG.A",             "segundo",    "δευτέρα"),
    ],

    # ════════════════════════════════════════════════════════════════════
    #  GÉNESIS 1:9  (20 elementos)
    # ════════════════════════════════════════════════════════════════════
    "1:9": [
        # W/Y)MR → PRE | STEM
        ("וַ",        "CONJ",                       "también",    "καὶ"),
        ("יֹּאמֶר",   "VERBO.QAL.WAYYIQT.P3.M.SG", "dijo",       "εἶπεν"),
        # )LHYM
        ("אֱלֹהִים",  "SUBS.M.PL.A",                "Dios",       "ὁ θεός"),
        # YQWW
        ("יִקָּווּ",  "VERBO.NIF.JUSS.P3.M.PL",    "júntense",   "συναχθήτω"),
        # H/MYM → PRE | STEM
        ("הַ",        "ART",                        "las",        "τὸ"),
        ("מַּיִם",    "SUBS.M.PL.A",                "aguas",      "ὕדωρ"),
        # [+ LXX ADD τὸ — 0 CATSS]
        # M/TTXT → PRE מִ | STEM תַּחַת
        ("מִ",        "PREP",                       "de",         "—"),
        ("תַּחַת",    "PREP",                       "debajo",     "ὑποκάτω"),
        # H/$MYM → PRE | STEM
        ("הַ",        "ART",                        "de los",     "τοῦ"),
        ("שָּׁמַיִם", "SUBS.M.PL.A",                "cielos",     "οὐרανοῦ"),
        # )L
        ("אֶל",       "PREP",                       "en",         "εἰς"),
        # MQWM
        ("מָקוֹם",    "SUBS.M.SG.A",                "lugar",      "συναγωγὴן"),
        # )XD
        ("אֶחָד",     "NUM.CARD.M.SG.A",            "un",         "μίαν"),
        # W/TR)H → PRE | STEM
        ("וְ",        "CONJ",                       "y",          "καὶ"),
        ("תֵרָאֶה",   "VERBO.NIF.IMPF.P3.F.SG",    "descúbrase", "ὀφθήτω"),
        # H/YB$H → PRE | STEM
        ("הַ",        "ART",                        "lo",         "ἡ"),
        ("יַּבָּשָׁה","SUBS.F.SG.A",                "seco",       "ξηρά"),
        # W/YHY → PRE | STEM  (וַיְהִי lleva maqaf porque se une a כֵן)
        ("וַ",         "CONJ",                       "y",          "καὶ"),
        ("יְהִי\u05be","VERBO.QAL.WAYYIQT.P3.M.SG", "fue",        "ἐγένετο"),
        # KN
        ("כֵן",        "ADV",                        "así",        "οὕτως"),
    ],

    # ════════════════════════════════════════════════════════════════════
    #  GÉNESIS 1:10  (18 elementos)
    # ════════════════════════════════════════════════════════════════════
    "1:10": [
        # W/YQRA → PRE | STEM
        ("וַ",        "CONJ",                       "y",          "καὶ"),
        ("יִּקְרָא",  "VERBO.QAL.WAYYIQT.P3.M.SG", "llamó",      "ἐκάλεσεν"),
        # )LHYM
        ("אֱלֹהִים",  "SUBS.M.PL.A",                "Dios",       "ὁ θεὸς"),
        # L/YB$H )RC → PRE לַ | STEM יַּבָּשָׁה | STEM אֶרֶץ
        ("לַ",        "PREP.ART",                   "a lo",       "τὴן"),
        ("יַּבָּשָׁה","SUBS.F.SG.A",                "seco",       "ξηρὰן"),
        ("אֶרֶץ",     "SUBS.BOTH.SG.A",             "tierra",     "γῆן"),
        # W/L/MQWH → PRE וּ | PRE לְ | STEM מִקְוֵה
        ("וּ",        "CONJ",                       "y",          "καὶ"),
        ("לְ",        "PREP",                       "a",          "—"),
        ("מִקְוֵה",   "SUBS.M.SG.C",                "reunión",    "τὰ συστήματα"),
        # H/MYM → PRE | STEM
        ("הַ",        "ART",                        "de las",     "τῶן"),
        ("מַּיִם",    "SUBS.M.PL.A",                "aguas",      "ὑδάτων"),
        # QR)
        ("קָרָא",     "VERBO.QAL.PERF.P3.M.SG",    "llamó",      "ἐκάλεσεν"),
        # YMYM
        ("יַמִּים",   "SUBS.M.PL.A",                "mares",      "θαλάσσας"),
        # W/YR) → PRE | STEM
        ("וַ",        "CONJ",                       "y",          "καὶ"),
        ("יַּרְא",    "VERBO.QAL.WAYYIQT.P3.M.SG", "vio",        "εἶδεν"),
        # )LHYM
        ("אֱלֹהִים",  "SUBS.M.PL.A",                "Dios",       "ὁ θεὸς"),
        # KY-TWB → STEM כִּי | STEM טֽוֹב
        ("כִּי",      "CONJ",                       "que",        "ὅτι"),
        ("טֹוב",      "ADJ.M.SG.A",                 "bueno",      "καλόν"),
    ],

    # ════════════════════════════════════════════════════════════════════
    #  GÉNESIS 1:11  (27 elementos tras eliminar par '=' pre-apply)
    #  Pares '=' se eliminan en main() ANTES de apply_to_verse.
    #  gk_add PAIR 08 se parchea en _patch_gen111() tras apply_to_verse.
    # ════════════════════════════════════════════════════════════════════
    "1:11": [
        # W/Y)MR → PRE | STEM
        ("וַ",        "CONJ",                       "después",    "καὶ"),
        ("יֹּאמֶר",   "VERBO.QAL.WAYYIQT.P3.M.SG", "dijo",       "εἶπεν"),
        # )LHYM
        ("אֱלֹהִים",  "SUBS.M.PL.A",                "Dios",       "ὁ θεός"),
        # TD$) (HIF juss)
        ("תַּדְשֵׁא", "VERBO.HIF.JUSS.P3.F.SG",    "produzca",   "βλαστησάτω"),
        # H/)RC → PRE | STEM
        ("הָ",        "ART",                        "la",         "ἡ"),
        ("אָרֶץ",     "SUBS.BOTH.SG.A",             "tierra",     "γῆ"),
        # D$)
        ("דֶּשֶׁא",   "SUBS.M.SG.A",                "hierba",     "βοτάνην"),
        # (SB
        ("עֵשֶׂב",    "SUBS.M.SG.A",                "hierba",     "χόρτου"),
        # MZRY( (HIF ptca) — participio causativo "que hace producir/siembra"
        ("מַזְרִיעַ", "VERBO.HIF.PTCA.M.SG.A",     "que produce","σπεῖρον"),
        # ZR(
        ("זֶרַע",     "SUBS.M.SG.A",                "semilla",    "σπέρμα"),
        # [gk_add PAIR 08 — 0 CATSS, manejado en _patch_gen111()]
        # (C — ξύλον (no γένος cruzado)
        ("עֵץ",       "SUBS.M.SG.C",                "árbol",      "ξύλον"),
        # PRY — κάρπιμον (no καὶ cruzado)
        ("פְּרִי",    "SUBS.M.SG.A",                "fruto",      "κάρπιμον"),
        # ($H (QAL ptca)
        ("עֹשֶׂה",    "VERBO.QAL.PTCA.M.SG.A",     "dé",         "ποιοῦν"),
        # PRY
        ("פְּרִי",    "SUBS.M.SG.A",                "fruto",      "καρπόν"),
        # L/MYN/W → PRE לְ (idx 0) | PRE מִין (idx 1) | STEM וֹ (prs)
        ("לְ",        "PREP",                       "según",      "κατὰ"),
        ("מִין",      "SUBS.M.SG.C",                "según su especie", "γένος"),
        ("וֹ",        "PRS.P3.M.SG",                "su",         "—"),
        # )$R
        ("אֲשֶׁר",    "REL",                        "que",        "οὗ"),
        # ZR(/W — su semilla (maqaf visual en he_form, gr completo)
        ("זַרְעוֹ",   "SUBS.M.SG.C",                "su semilla", "τὸ σπέρμα αὐτοῦ"),
        # B/W — stem=וֹ, pref=[] tras fusión C14; gr explícito LXX
        ("וֹ",        "PREP+PRS.P3.M.SG",           "en él",      "ἐν αὐτῷ"),
        # (L
        ("עַל",       "PREP",                       "sobre",      "ἐπὶ"),
        # H/)RC → PRE | STEM
        ("הָ",        "ART",                        "la",         "τῆς"),
        ("אָרֶץ",     "SUBS.BOTH.SG.A",             "tierra",     "γῆς"),
        # W/YHY → PRE | STEM
        ("וַ",        "CONJ",                       "y",          "καὶ"),
        ("יְהִי",     "VERBO.QAL.WAYYIQT.P3.M.SG", "fue",        "ἐγένετο"),
        # KN
        ("כֵן",       "ADV",                        "así",        "οὕτως"),
    ],

    # ════════════════════════════════════════════════════════════════════
    #  GÉNESIS 1:12  (26 elementos)
    # ════════════════════════════════════════════════════════════════════
    "1:12": [
        # W/TWCY → PRE | STEM
        ("וַ",        "CONJ",                       "pues",       "καὶ"),
        ("תּוֹצֵא",   "VERBO.HIF.WAYYIQT.P3.F.SG", "produjo",    "ἐξήνεγκεν"),
        # H/)RC → PRE | STEM
        ("הָ",        "ART",                        "la",         "ἡ"),
        ("אָרֶץ",     "SUBS.BOTH.SG.A",             "tierra",     "γῆ"),
        # D$)
        ("דֶּשֶׁא",   "SUBS.M.SG.A",                "hierba",     "βοτάνην"),
        # (SB
        ("עֵשֶׂב",    "SUBS.M.SG.A",                "hierba",     "χόרτου"),
        # MZRY( (HIF ptca)
        ("מַזְרִיעַ", "VERBO.HIF.PTCA.M.SG.A",     "que produce","σπεῖρον"),
        # ZR(
        ("זֶרַע",     "SUBS.M.SG.A",                "semilla",    "σπέρμα"),
        # L/MYN → PRE | STEM
        ("לְ",        "PREP",                       "según",      "κατὰ"),
        ("מִינֵ",     "SUBS.M.SG.C",                "naturaleza", "γένος"),
        # HW (suffix הוּ)
        ("הוּ",       "PRS.P3.M.SG",                "su",         "—"),
        # W/(C → PRE | STEM
        ("וְ",        "CONJ",                       "y",          "καὶ"),
        ("עֵץ",       "SUBS.M.SG.A",                "árbol",      "ξύλον"),
        # [+ LXX ADD κάρπιμον — 0 CATSS]
        # ($H (QAL ptca)
        ("עֹשֶׂה",    "VERBO.QAL.PTCA.M.SG.A",     "da",         "ποιοῦν"),
        # PRY
        ("פְּרִי",    "SUBS.M.SG.A",                "fruto",      "καρπόν"),
        # )$R
        ("אֲשֶׁר",    "REL",                        "cuya",       "οὗ"),
        # ZR(
        ("זַרְע",     "SUBS.M.SG.C",                "semilla",    "τὸ σπέρמα"),
        # W (suffix ו)
        ("וֹ",        "PRS.P3.M.SG",                "su",         "αὐτοῦ"),
        # L/MYN → PRE | STEM
        ("לְ",        "PREP",                       "según",      "κατὰ"),
        ("מִינֵ",     "SUBS.M.SG.C",                "género",     "γένος"),
        # HW (suffix הוּ)
        ("הוּ",       "PRS.P3.M.SG",                "su",         "—"),
        # W/YR) → PRE | STEM
        ("וַ",        "CONJ",                       "y",          "καὶ"),
        ("יַּרְא",    "VERBO.QAL.WAYYIQT.P3.M.SG", "vio",        "εἶδεν"),
        # [+ LXX ADD ×2 — 0 CATSS]
        # )LHYM
        ("אֱלֹהִים",  "SUBS.M.PL.A",                "Dios",       "ὁ θεὸς"),
        # KY-TWB → STEM | STEM
        ("כִּי",      "CONJ",                       "que",        "ὅτι"),
        ("טֹוב",      "ADJ.M.SG.A",                 "bueno",      "καλόν"),
    ],

    # ════════════════════════════════════════════════════════════════════
    #  GÉNESIS 1:13  (8 elementos)
    #  Corrige: VqAmSM3 → VERBO.QAL.WAYYIQT
    # ════════════════════════════════════════════════════════════════════
    "1:13": [
        # W/YHY → PRE | STEM
        ("וַ",        "CONJ",                       "y",          "καὶ"),
        ("יְהִי",     "VERBO.QAL.WAYYIQT.P3.M.SG", "fue",        "ἐγένετο"),
        # (RB
        ("עֶרֶב",     "SUBS.M.SG.A",                "tarde",      "ἑσπέρα"),
        # W/YHY → PRE | STEM
        ("וַ",        "CONJ",                       "y",          "καὶ"),
        ("יְהִי",     "VERBO.QAL.WAYYIQT.P3.M.SG", "fue",        "ἐγένετο"),
        # BQR
        ("בֹקֶר",     "SUBS.M.SG.A",                "mañana",     "πρωί"),
        # YWM
        ("יֹום",      "SUBS.M.SG.A",                "día",        "ἡμέρα"),
        # $LY$Y
        ("שְׁלִישִׁי","NUM.ORD.M.SG.A",             "tercero",    "τρίτη"),
    ],

    # ════════════════════════════════════════════════════════════════════
    #  GÉNESIS 1:14  (30 elementos)
    # ════════════════════════════════════════════════════════════════════
    "1:14": [
        # W/Y)MR → PRE | STEM
        ("וַ",        "CONJ",                       "y",          "καὶ"),
        ("יֹּאמֶר",   "VERBO.QAL.WAYYIQT.P3.M.SG", "dijo",       "εἶπεν"),
        # )LHYM
        ("אֱלֹהִים",  "SUBS.M.PL.A",                "'Elohim",    "θεός"),
        # YHY (juss)
        ("יְהִי",     "VERBO.QAL.JUSS.P3.M.SG",    "haya",       "γενηθήτωσαν"),
        # M)RWT
        ("מְאֹרֹת",   "SUBS.M.PL.A",                "lumbreras",  "φωστῆρες"),
        # B/RQYW( → PRE בִּ | STEM רְקִיעַ
        ("בִּ",       "PREP",                       "en",         "ἐν"),
        ("רְקִיעַ",   "SUBS.M.SG.C",                "expansión",  "τῷ στερεώματι"),
        # H/$MYM → PRE | STEM
        ("הַ",        "ART",                        "de los",     "τοῦ"),
        ("שָּׁמַיִם", "SUBS.M.PL.A",                "cielos",     "οὐρανοῦ"),
        # [+ LXX ADD ×2 — 0 CATSS]
        # L/HBDYL → PRE לְ | STEM הַבְדִּיל
        ("לְ",        "PREP",                       "para",       "εἰς"),
        ("הַבְדִּיל", "VERBO.HIF.INFC",             "separar",    "διαχωρίζειν"),
        # BYN H/YWM → STEM βēn | PRE הַ | STEM יֹּום
        ("בֵּין",     "PREP",                       "entre",      "ἀνὰ μέσον"),
        ("הַ",        "ART",                        "el",         "τῆς"),
        ("יֹּום",     "SUBS.M.SG.A",                "día",        "ἡμέρας"),
        # W/BYN H/LYLH → PRE וּ | STEM βēn | PRE הַ | STEM לָּיְלָה
        ("וּ",        "CONJ",                       "y",          "καὶ"),
        ("בֵין",      "PREP",                       "entre",      "ἀנὰ μέסον"),
        ("הַ",        "ART",                        "la",         "τῆς"),
        ("לָּיְלָה",  "SUBS.M.SG.A",                "noche",      "νυκτὸς"),
        # W/HYW → PRE | STEM
        ("וְ",        "CONJ",                       "y",          "καὶ"),
        ("הָיוּ",     "VERBO.QAL.SEQ.PERF.P3.COMMON.PL", "sirvan","ἔστωσαν"),
        # L/)TWR → PRE לְ | STEM אֹתֹת
        ("לְ",        "PREP",                       "de",         "εἰς"),
        ("אֹתֹת",     "SUBS.BOTH.PL.A",             "señales",    "σημεῖα"),
        # W/L/MW(DYM → PRE וּ | PRE לְ | STEM מֹועֲדִים
        ("וּ",        "CONJ",                       "y",          "καὶ"),
        ("לְ",        "PREP",                       "para",       "εἰς"),
        ("מֹועֲדִים", "SUBS.M.PL.A",                "estaciones", "καιροὺς"),
        # W/L/YMYM → PRE וּ | PRE לְ | STEM יָמִים
        ("וּ",        "CONJ",                       "y",          "καὶ"),
        ("לְ",        "PREP",                       "para",       "εἰς"),
        ("יָמִים",    "SUBS.M.PL.A",                "días",       "ἡμέρας"),
        # W/$NYM → PRE | STEM
        ("וְ",        "CONJ",                       "y",          "καὶ"),
        ("שָׁנִים",   "SUBS.F.PL.A",                "años",       "ἐνιαυτοὺς"),
    ],

    # ════════════════════════════════════════════════════════════════════
    #  GÉNESIS 1:15  (16 elementos)
    #  Corrige: רְקִיעַ="expansión" (no "la"), griego correcto
    # ════════════════════════════════════════════════════════════════════
    # ════════════════════════════════════════════════════════════════════
    #  GÉNESIS 5:1  — corrección de griego en דְּמוּת + אֹתוֹ
    #  Error de datos en interlinear-snapshot: αὐτόν asignado a דְּמוּת
    #  en lugar de a אֹתוֹ.  La fusión PART.OBJ+PRS ya agrupa אֹתוֹ;
    #  solo necesitamos corregir el griego de דְּמוּת aquí.
    # ════════════════════════════════════════════════════════════════════
    "5:1": [
        # PAIR 00: ZH
        ("זֶה",        "PRON.DEM.M.SG",              "este",       "αὕτη"),
        # PAIR 01: SPR
        ("סֵפֶר",      "SUBS.M.SG.C",                "el",         "ἡ"),
        # PAIR 02: TWLDT
        ("תֹּולְדֹת",  "SUBS.F.PL.C",                "generaciones","βίβλος"),
        # PAIR 03: )DM
        ("אָדָם",      "NPROP",                      "Adán",       "γενέσεως"),
        # PAIR 04: B/YWM → PRE בְּ | STEM יֹום
        ("בְּ",        "PREP",                       "en",         "κατ᾿"),
        ("יֹום",       "SUBS.M.SG.C",                "el día",     "ἡμέρᾳ"),
        # PAIR 05: BR)
        ("בְּרֹא",     "VERBO.QAL.INFC",             "creó",       "ἐποίησεν"),
        # PAIR 06: )LHYM  (1er Elohim)
        ("אֱלֹהִים",   "SUBS.M.PL.A",                "'Elohim",    "ὁ θεὸς"),
        # PAIR 07: )DM
        ("אָדָם",      "SUBS.M.SG.A",                "hombre",     "τὸν Αδαμ"),
        # PAIR 08: B/DMWT [p] → PRE בִּ | STEM דְּמוּת | meta-p ya eliminada
        ("בִּ",        "PREP",                       "a",          "κατ᾿"),
        ("דְּמוּת",    "SUBS.F.SG.C",                "semejanza",  "εἰκόνα"),
        # PAIR 09: )LHYM  (2do Elohim — "de Dios")
        ("אֱלֹהִים",   "SUBS.M.PL.A",                "'Elohim",    "θεοῦ"),
        # PAIR 10: (&H
        ("עָשָׂה",     "VERBO.QAL.PERF.P3.M.SG",    "hizo",       "ἐποίησεν"),
        # PAIR 11: )T/W → fusionado por corrección 6 en אֹתוֹ
        ("אֹתוֹ",      "PART.OBJ.DIR",               "lo",         "αὐτόν"),
    ],

    "1:15": [
        # W/HYW → PRE | STEM
        ("וְ",        "CONJ",                       "y",          "καὶ"),
        ("הָיוּ",     "VERBO.QAL.SEQ.PERF.P3.COMMON.PL", "sean", "ἔστωσαν"),
        # L/M)RWT → PRE לִ | STEM מְאֹורֹת
        ("לִ",        "PREP",                       "por",        "εἰς"),
        ("מְאֹורֹת",  "SUBS.M.PL.A",                "lumbreras",  "φαῦσιν"),
        # B/RQYW( → PRE בִּ | STEM רְקִיעַ
        ("בִּ",       "PREP",                       "en",         "ἐν"),
        ("רְקִיעַ",   "SUBS.M.SG.C",                "expansión",  "τῷ στερεώματι"),
        # H/$MYM → PRE | STEM
        ("הַ",        "ART",                        "de los",     "τοῦ"),
        ("שָּׁמַיִם", "SUBS.M.PL.A",                "cielos",     "οὐרανοῦ"),
        # L/H)YR → PRE לְ | STEM הָאִיר
        ("לְ",        "PREP",                       "para",       "ὥστε"),
        ("הָאִיר",    "VERBO.HIF.INFC",             "alumbrar",   "φαίνειν"),
        # (L H/)RC → STEM עַל | PRE הָ | STEM אָרֶץ
        ("עַל",       "PREP",                       "sobre",      "ἐπὶ"),
        ("הָ",        "ART",                        "la",         "τῆς"),
        ("אָרֶץ",     "SUBS.BOTH.SG.A",             "tierra",     "γῆς"),
        # W/YHY → PRE | STEM
        ("וַ",        "CONJ",                       "y",          "καὶ"),
        ("יְהִי",     "VERBO.QAL.WAYYIQT.P3.M.SG", "fue",        "ἐγένετο"),
        # KN
        ("כֵן",       "ADV",                        "así",        "οὕτως"),
    ],

}


# ════════════════════════════════════════════════════════════════════════
#  MOTOR DE APLICACIÓN
# ════════════════════════════════════════════════════════════════════════

def _patch_gen111(verse: dict) -> None:
    """Correcciones puntuales Gen 1:11 por raw — robusto ante cambio de conteo de tokens."""
    # gk_add: inyectar texto LXX si está vacío
    for p in verse["pairs"]:
        if p.get("kind") == "gk_add" and not p.get("gr_unicode", "").strip():
            p["gr_unicode"] = "κατὰ καθ\u02bc ὁμοιότητα"
            break
    # Correcciones por raw
    pry_seen = 0
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            raw = hw.get("raw", "")
            if raw == "W/Y)MR":                  # וַיֹּאמֶר prefix וַ → "y"
                pfx_es = hw.get("prefix_es", [])
                if pfx_es:
                    hw["prefix_es"][0] = "y"
            elif raw == "(&H":                   # עֹשֶׂה QAL.PTCA "que dé"
                if hw.get("es", "") in ("dé", "da", "hace", ""):
                    hw["es"] = "que dé"
            elif raw == "(C":                      # עֵץ árbol → ξύλον
                hw["es"] = "árbol"
                hw["gr_word"] = _san_gr("ξύλον")
            elif raw == "PRY":
                pry_seen += 1
                if pry_seen == 1:                # primer פְּרִי → κάρπιμον
                    hw["es"] = "fruto"
                    hw["gr_word"] = _san_gr("κάρπιμον")
                # segundo PRY ya tiene καρπόν del merge, OK
            elif raw == "ZR(/W":                 # זַרְעוֹ semilla + maqaf
                # he_form = forma COMPLETA del OSHB: raíz + sufijo וֹ + maqaf ─
                # prs_suffix.he_form = '' (vacío) para que el frontend NO lo
                # concatene al stem (ya está incluido en la forma completa).
                # El mini-fila solo muestra morfología/ES/GR del sufijo.
                hw["he_form"] = "זַרְעוֹ\u05be"   # forma OSHB completa + maqaf
                hw["es"] = "semilla"
                hw["gr_word"] = _san_gr("τὸ σπέρμα αὐτוῦ")
                prs = hw.get("prs_suffix")
                if prs:
                    prs["he_form"] = ""           # vacío → no se concatena al stem
                    prs["es"] = "su"
                    prs["gr_word"] = _san_gr("αὐτοῦ")
            elif raw == "B/W":                   # בּוֹ → ἐν αὐτῷ
                hw["he_form"]  = "בּוֹ"            # restaurar bet perdida en fusión C14
                hw["he_morph"] = "PREP+PRS.P3.M.SG"
                hw["es"] = "en él"
                hw["gr_word"] = _san_gr("ἐν αὐτῷ")
                hw.pop("gr_source", None)
                hw.pop("es_source", None)
            # L/MYN/W → ahora cubierto por _apply_myn_suffix_rule() en main()


def _patch_gen116(verse: dict) -> None:
    """Correcciones puntuales Gen 1:16 por raw.

    Problemas identificados:
    - מֶמְשֶׁלֶת (×2, raw=L/MM$LT): es='señorease' → 'dominio'; par 7 tenía gr='δύο' (wrong)
    - גְּדֹלִים (H/GDLYM): gr='' → 'μεγάλους'
    - גָּדֹל (H/GDL): gr='' → 'μέγαν'
    - קָּטֹן (H/Q+N): gr='' → 'ἐλάσσω'
    - כֹּוכָבִים (H/KWKBYM): gr='ἀרחὰס' (sobrante de alineación previa) → 'ἀστέρας'
    """
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            raw = hw.get("raw", "")
            if raw == "L/MM$LT":
                hw["es"] = "dominio"
                hw["gr_word"] = _san_gr("ἀρχὰς")
                # Prefijo לְ → εἰς
                pfx_gr = hw.get("prefix_gr", [])
                if pfx_gr:
                    hw["prefix_gr"][0] = _san_gr("εἰς")
                hw.pop("es_source", None)
                hw.pop("gr_source", None)
            elif raw == "H/GDLYM":
                if not hw.get("gr_word", ""):
                    hw["gr_word"] = _san_gr("μεγάλους")
                pfx_es = hw.get("prefix_es", [])
                if pfx_es and not pfx_es[0]:
                    hw["prefix_es"][0] = "los"
            elif raw == "H/GDL":
                if not hw.get("gr_word", ""):
                    hw["gr_word"] = _san_gr("μέγαν")
                pfx_es = hw.get("prefix_es", [])
                if pfx_es and not pfx_es[0]:
                    hw["prefix_es"][0] = "el"
            elif raw == "H/Q+N":
                if not hw.get("gr_word", ""):
                    hw["gr_word"] = _san_gr("ἐλάσσω")
                # Artículo prefijado ה → "la" (en contexto: la lumbrera menor)
                pfx_morphs = hw.get("prefix_morphs", [])
                pfx_es = hw.get("prefix_es", [])
                for i, pm in enumerate(pfx_morphs):
                    if pm == "ART" and i < len(pfx_es) and not (pfx_es[i] or "").strip():
                        hw["prefix_es"][i] = "la"
            elif raw == "H/KWKBYM":
                hw["gr_word"] = _san_gr("ἀστέρας")


def _patch_gen112(verse: dict) -> None:
    """Correcciones puntuales Gen 1:12 por raw — robustas ante cambio de conteo de tokens."""
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            raw = hw.get("raw", "")
            if raw == "MZRY(":
                # מַזְרִיעַ HIF ptca — cubierto también por Global Pass 3; este bloque
                # asegura el valor correcto incluso si el morph no contiene PTCA.
                hw["es"] = "que produce"
            # L/MYN/HW → ahora cubierto por _apply_myn_suffix_rule() en main()


def _patch_gen126(verse: dict) -> None:
    """Correcciones puntuales Gen 1:26: reestructura B/CLM/NW y K/DMWT/NW.

    El pipeline colocó el stem (צֶלֶם / דְּמוּת) como prefix[1] y el sufijo
    pronominal (נוּ) como he_form.  Hay que invertir: stem → he_form, נוּ → prs_suffix,
    y recortar prefix_* a 1 elemento (solo la preposición).
    """
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            raw = hw.get("raw", "")

            if raw == "B/CLM/NW":
                # Recortar a un solo prefijo (בְּ PREP); quitar CLM mal colocado
                for lst in ("prefixes", "prefix_forms", "prefix_morphs",
                            "prefix_es", "prefix_gr", "prefix_labels",
                            "prefix_tier", "prefix_unicode"):
                    if lst in hw and len(hw[lst]) > 1:
                        hw[lst] = hw[lst][:1]
                hw["prefix_forms"]  = ["בְּ"]
                hw["prefix_morphs"] = ["PREP"]
                hw["prefix_es"]     = ["a"]
                hw["prefix_gr"]     = ["κατ᾿"]
                hw["he_form"]  = "צַלְמֵנוּ"
                hw["he_morph"] = "SUBS.M.SG.C"
                hw["es"]       = "imagen"
                hw["gr_word"]  = "εἰκόνα"
                hw["prs_suffix"] = {
                    "he_form":  "נוּ",
                    "he_morph": "PRS.P1.COMMON.PL",
                    "es":       "nuestra",
                    "gr_word":  "ἡμετέραν",
                }
                hw.pop("es_source", None)
                hw.pop("gr_source", None)

            elif raw == "K/DMWT/NW":
                # Mismo problema: דְּמוּת como prefix[1], נוּ como stem
                for lst in ("prefixes", "prefix_forms", "prefix_morphs",
                            "prefix_es", "prefix_gr", "prefix_labels",
                            "prefix_tier", "prefix_unicode"):
                    if lst in hw and len(hw[lst]) > 1:
                        hw[lst] = hw[lst][:1]
                hw["prefix_forms"]  = ["כִּ"]
                hw["prefix_morphs"] = ["PREP"]
                hw["prefix_es"]     = ["como"]
                hw["prefix_gr"]     = ["καθ᾿"]
                hw["he_form"]  = "דְמוּתֵנוּ"
                hw["he_morph"] = "SUBS.F.SG.C"
                hw["es"]       = "semejanza"
                hw["gr_word"]  = "ὁμοίωσιν"
                hw["prs_suffix"] = {
                    "he_form":  "נוּ",
                    "he_morph": "PRS.P1.COMMON.PL",
                    "es":       "nuestra",
                    "gr_word":  "",
                }
                hw.pop("es_source", None)
                hw.pop("gr_source", None)


def _patch_gen127(verse: dict) -> None:
    """Correcciones puntuales Gen 1:27.

    1. )T/M vacío → restaurar אֹתָם
    2. B/CLM (par 4) tiene un prefijo corrupto בָּרָ֣א (verbo) —
       limpiar todos los prefijos de ese token ya que no son reales.
    """
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            raw = hw.get("raw", "")
            if raw == ")T/M" and not hw.get("he_form", ""):
                hw["he_form"]  = "אֹתָם"
                hw["he_morph"] = "PART.OBJ.DIR"
            elif raw == ")T/W":
                # he_form corrupto ('נְקֵבָ֖ה' por desplazamiento del pipeline) → אֹתוֹ
                hw["he_form"]  = "אֹתוֹ"
                hw["he_morph"] = "PART.OBJ.DIR"
                hw["es"]       = "lo"
                if not hw.get("gr_word", ""):
                    hw["gr_word"] = _san_gr("αὐτόν")
                # Prefijo וּ CONJ sin griego
                pfx_morphs = hw.get("prefix_morphs", [])
                pfx_gr     = hw.get("prefix_gr", [])
                for i, pm in enumerate(pfx_morphs):
                    if pm == "CONJ" and i < len(pfx_gr) and not pfx_gr[i]:
                        hw["prefix_gr"][i] = _san_gr("καὶ")
            elif raw == "B/CLM/W":
                for lst in ("prefixes", "prefix_forms", "prefix_morphs",
                            "prefix_es", "prefix_gr", "prefix_labels",
                            "prefix_tier", "prefix_unicode"):
                    if lst in hw and len(hw[lst]) > 1:
                        hw[lst] = hw[lst][:1]
                hw["prefix_forms"]  = ["בְּ"]
                hw["prefix_morphs"] = ["PREP"]
                hw["prefix_es"]     = ["a"]
                hw["prefix_gr"]     = [_san_gr("κατ᾿")]
                hw["he_form"]  = "צַלְמוֹ"
                hw["he_morph"] = "SUBS.M.SG.C"
                hw["es"]       = "imagen"
                hw["gr_word"]  = _san_gr("εἰκόνα")
                hw["prs_suffix"] = {
                    "he_form":  "וֹ",
                    "he_morph": "PRS.P3.M.SG",
                    "es":       "su",
                    "gr_word":  _san_gr("αὐτοῦ"),
                }
                hw.pop("es_source", None)
                hw.pop("gr_source", None)
            elif raw == "B/CLM":
                # El prefijo בָּרָ֣א es un verbo erróneamente asignado como prefijo
                # de צֶלֶם (en realidad es una palabra independiente del verso).
                # Limpiar todos los slots de prefijo de este token.
                hw["prefixes"]       = []
                hw["prefix_forms"]   = []
                hw["prefix_morphs"]  = []
                hw["prefix_es"]      = []
                hw["prefix_gr"]      = []
                hw["es"]       = ""
                hw["gr_word"]  = "αὐτούς"
                # Limpiar el prefijo vacío ficticio
                for lst in ("prefixes", "prefix_forms", "prefix_morphs",
                            "prefix_es", "prefix_gr", "prefix_labels",
                            "prefix_tier", "prefix_unicode"):
                    if lst in hw:
                        hw[lst] = []
                hw.pop("es_source", None)
                hw.pop("gr_source", None)


def _patch_gen129(verse: dict) -> None:
    """Correcciones puntuales Gen 1:29 — glosas fragmentadas por desalineación SpaRV1909.

    נָתַתִּי לָכֶם → «he dado» + «os» (no «os» + «vuestro»).
    Participios זֹרֵעַ → «que da».  Cierre del verso → «os» + «será» + «para alimento».
    """
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            raw = hw.get("raw", "")
            morph = hw.get("he_morph", "") or ""

            if raw == "HNH":
                hw["es"] = "he aquí"
                hw["es_source"] = "patch"

            elif raw == "NTTY":
                hw["es"] = "he dado"
                hw["strongs"] = "H5414"
                hw["es_source"] = "patch"

            elif raw == "L/KM":
                hw["he_form"] = "לָכֶם"
                hw["he_morph"] = "PREP+PRS.P2.M.PL"
                hw["es"] = "os"
                hw["strongs"] = ""
                for lst in ("prefixes", "prefix_forms", "prefix_morphs",
                            "prefix_es", "prefix_gr", "prefix_labels",
                            "prefix_tier", "prefix_unicode"):
                    if lst in hw:
                        hw[lst] = []
                hw["es_source"] = "patch"

            elif raw == "ZR(" and "PTCA" in morph and hw.get("es") in ("da", ""):
                hw["es"] = "que da"
                hw["es_source"] = "patch"

            elif raw == "YHYH" and hw.get("he_form") == "יִהְיֶה":
                hw["es"] = "será"
                hw["es_source"] = "patch"

            elif raw == "L/)KLH":
                hw["prefix_es"] = ["para"]
                hw["es"] = "alimento"
                hw["es_source"] = "patch"


def _clear_hw_prefix_slots(hw: dict) -> None:
    for lst in ("prefixes", "prefix_forms", "prefix_morphs",
                "prefix_es", "prefix_gr", "prefix_labels",
                "prefix_tier", "prefix_unicode"):
        if lst in hw:
            hw[lst] = []


def _sync_hw_prefix_slots(hw: dict) -> None:
    """B4 — alinea prefix_morphs/es con prefix_forms; limpia huérfanos post-merge."""
    pfx_f = hw.get("prefix_forms") or []
    if not pfx_f or not any(_strip_niqqud(x) for x in pfx_f):
        for key in (
            "prefix_forms", "prefix_morphs", "prefix_es", "prefix_gr",
            "prefix_labels", "prefix_tier", "prefix_unicode", "prefixes",
        ):
            hw.pop(key, None)
        return
    n = len(pfx_f)
    pfx_m = list(hw.get("prefix_morphs") or [])
    pfx_e = list(hw.get("prefix_es") or [])
    if len(pfx_m) != n:
        hw["prefix_morphs"] = (pfx_m + ["?"] * n)[:n]
    if len(pfx_e) != n:
        hw["prefix_es"] = (pfx_e + [""] * n)[:n]
    pfx_g = list(hw.get("prefix_gr") or [])
    if pfx_g and len(pfx_g) != n:
        hw["prefix_gr"] = (pfx_g + [""] * n)[:n]


def _is_catss_meta_raw(raw: str) -> bool:
    """True si el raw es notación CATSS, no un token del TM."""
    raw = (raw or "").strip()
    if raw.startswith(".$") or raw.startswith(".("):
        return True
    return any(raw.startswith(p) for p in ("=", "{", "<", "*", "--"))


def _strip_niqqud(he: str) -> str:
    return re.sub(r"[\u0591-\u05AF]", "", he or "")


def _strip_catss_he_garbage(text: str) -> str:
    """Quita sufijos basura del aparato CATSS en cadenas he_unicode."""
    if not text:
        return text
    t = text.strip()
    t = re.sub(r"\s+צפהצפן\s*ש[ׁ\u05c1]?c\s*$", "", t)
    t = re.sub(r"\s+תשׁ?ובתך\s*qb\s*$", "", t)
    t = re.sub(r"\s+הגה\s*rg\s*$", "", t, flags=re.I)
    t = re.sub(r"\s+עבד\s*rd\s*$", "", t)
    t = re.sub(r"\s+[a-z]{1,3}\s*$", "", t, flags=re.I)
    return t.strip()


def _rebuild_he_unicode_from_words(pair: dict) -> str:
    bits: list[str] = []
    for hw in pair.get("he_words") or []:
        if _is_catss_meta_raw(hw.get("raw") or ""):
            continue
        he = _strip_niqqud(hw.get("he_form") or "")
        if he:
            bits.append(he)
    return "".join(bits)


def _sanitize_catss_pairs(verse: dict) -> int:
    """Limpia he_unicode deformado y elimina he_words meta (.$c, etc.)."""
    changes = 0
    for p in verse.get("pairs", []):
        before = len(p.get("he_words") or [])
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if not _is_catss_meta_raw(hw.get("raw") or "")
        ]
        if len(p.get("he_words") or []) != before:
            changes += 1
        rebuilt = _rebuild_he_unicode_from_words(p)
        if rebuilt:
            new_he = _strip_catss_he_garbage(rebuilt)
            if new_he != (p.get("he_unicode") or ""):
                p["he_unicode"] = new_he
                changes += 1
        elif p.get("he_unicode"):
            new_he = _strip_catss_he_garbage(p["he_unicode"])
            if new_he != p["he_unicode"]:
                p["he_unicode"] = new_he
                changes += 1
        for field in ("he_stem_unicode", "full_unicode"):
            if p.get(field):
                new = _strip_catss_he_garbage(p[field])
                if new != p[field]:
                    p[field] = new
                    changes += 1
    return changes


def _article_es_from_morph(morph: str) -> str:
    """Artículo definido español coherente con la morfología hebrea del término."""
    morph = (morph or "").upper()
    if ".PL" in morph or ".PL." in morph or morph.endswith(".PL"):
        return "las" if "F." in morph else "los"
    if "F." in morph:
        return "la"
    return "el"


# Glosas PREP+PRS fusionadas: una sola lectura (no «para/a él»).
_SLASH_GLOSS_CANON = {
    "para/a él": "para él",
    "para/a ella": "para ella",
    "para/a mí": "a mí",
    "para/a mi": "a mí",
    "para/a ti": "a ti",
    "para/a ellos": "para ellos",
    "para/a nosotros": "para nosotros",
}


def _prs_suffix_redundant(stem_es: str, suf_es: str) -> bool:
    """True si el posesivo del sufijo ya está integrado en la glosa del stem."""
    if not stem_es or not suf_es:
        return False
    sl = suf_es.lower().strip()
    return bool(re.search(rf"(?<!\w){re.escape(sl)}(?!\w)", stem_es.lower()))


_FUSED_PREP_ES = frozenset({
    "contigo", "conmigo", "con él", "con ella", "con ellos", "con nosotros",
    "con ustedes", "con vosotros",
    "a ti", "a mí", "a él", "a ella", "de ti", "de él", "de ella", "con te",
})


def _dedupe_adjacent_es(es: str) -> str:
    """Quita repeticiones adyacentes («su su pie» → «su pie», «la la X» → «la X»)."""
    parts = (es or "").split()
    if len(parts) < 2:
        return es
    dupable = _POSS_ES | _ART_ES | _ENCLITIC_ES | {"con", "de", "a", "y", "no", "te", "ti"}
    out = [parts[0]]
    for w in parts[1:]:
        if w.lower() == out[-1].lower() and w.lower() in dupable:
            continue
        out.append(w)
    return " ".join(out)


def _fix_leading_clitic_verb(es: str, morph: str) -> str:
    """«la tomándola» → «tomándola» cuando el verbo ya lleva el clítico."""
    m = (morph or "").upper()
    if "VERB" not in m and "VERBO" not in m:
        return es
    parts = (es or "").split()
    if len(parts) < 2:
        return es
    lead, rest = parts[0].lower(), " ".join(parts[1:])
    if lead in _ENCLITIC_ES and rest.lower().endswith(lead):
        return rest
    return es


def _stem_integrates_prs(hw: dict) -> bool:
    """True si prs_suffix ya está reflejado en la glosa del stem (no rellenar ni re-fusionar)."""
    stem_es = (hw.get("es") or "").strip()
    prs = hw.get("prs_suffix") or {}
    if not stem_es or not prs.get("he_form"):
        return False
    sl = stem_es.lower()
    if sl in _FUSED_PREP_ES:
        return True
    prs_m = prs.get("he_morph") or ""
    inferred = _prs_es_for_context(hw, prs_m)
    if inferred and _prs_suffix_redundant(stem_es, inferred):
        return True
    words = sl.split()
    if words and words[0] in _POSS_ES:
        return True
    morph = (hw.get("he_morph") or "").upper()
    if "VERB" in morph or "VERBO" in morph:
        for cl in _ENCLITIC_ES:
            if sl.endswith(cl) and len(sl) > len(cl) + 2:
                return True
    return False


def _drop_redundant_prs_suffix(hw: dict) -> bool:
    prs = hw.get("prs_suffix")
    if not prs:
        return False
    if _stem_integrates_prs(hw):
        # Parches OSHB: conservar he_form del sufijo aunque la glosa ya esté fusionada.
        if (hw.get("es_source") or "").strip().lower() == "patch" and prs.get("he_form"):
            prs["es"] = ""
            return False
        hw.pop("prs_suffix", None)
        return True
    stem_es = (hw.get("es") or "").strip()
    suf_es = (prs.get("es") or "").strip()
    if _prs_suffix_redundant(stem_es, suf_es):
        if (hw.get("es_source") or "").strip().lower() == "patch" and prs.get("he_form"):
            prs["es"] = ""
            return False
        hw.pop("prs_suffix", None)
        return True
    he = hw.get("he_form") or ""
    suf_he = (prs.get("he_form") or "").strip()
    if stem_es and suf_he and len(he) > len(suf_he) and he.endswith(suf_he):
        hw.pop("prs_suffix", None)
        return True
    return False


_ART_ES = frozenset({"el", "la", "los", "las", "un", "una", "unos", "unas"})
_ENCLITIC_ES = frozenset({"lo", "la", "los", "las", "me", "te", "se", "le", "les", "nos", "os"})
_POSS_ES = frozenset({
    "su", "sus", "mi", "mis", "tu", "tus",
    "nuestro", "nuestra", "nuestros", "nuestras",
})
_REL_ES = frozenset({"cuya", "cuyo", "cuyos", "cuyas", "que", "quien", "quienes"})

_HE_NOUN_ES: dict[str, str] = {
    "שמ": "nombre",
    "מין": "especie",
    "זרע": "semilla",
    "פרי": "fruto", "פר": "fruto",
    "צאן": "rebaño",
    "מנחת": "ofrenda", "מנח": "ofrenda",
    "אשת": "mujer",
    "דמות": "semejanza",
    "צלמ": "imagen",
    "מעש": "obra",
    "ידי": "manos", "יד": "mano",
}

_STRONG_NOUN_ES: dict[str, str] = {
    "H8034": "nombre", "H4327": "especie", "H2233": "semilla", "H6529": "fruto",
    "H6629": "rebaño", "H4503": "ofrenda", "H802": "mujer", "H1823": "semejanza",
    "H6754": "imagen", "H4639": "obra", "H3027": "mano",
}


def _he_noun_key(hw: dict) -> str:
    he = hw.get("he_form") or hw.get("stem_unicode") or ""
    he = re.sub(r"[\u0591-\u05C7\u05BC\u05C1\u05C2\u05BD]", "", he)
    return he.replace("־", "").replace("-", "").strip()


def _infer_noun_es(hw: dict) -> str | None:
    key = _he_noun_key(hw)
    if key in _HE_NOUN_ES:
        return _HE_NOUN_ES[key]
    for k, v in _HE_NOUN_ES.items():
        if key.startswith(k):
            return v
    return _STRONG_NOUN_ES.get(hw.get("strongs") or "")


def _possessor_before_noun(poss: str, noun: str) -> str:
    p = poss.lower().strip()
    n = noun.strip()
    nl = n.lower()
    if p == "su" and nl.endswith("s"):
        p = "sus"
    elif p == "mi" and nl.endswith("s"):
        p = "mis"
    elif p == "tu" and nl.endswith("s"):
        p = "tus"
    elif p in ("nuestra", "nuestro") and nl.endswith("s"):
        p = "nuestras" if nl.endswith(("as", "es")) or nl in ("manos", "obras") else "nuestros"
    return f"{p} {n}"


def _is_spanish_infinitive(stem_es: str, morph: str) -> bool:
    if "INFC" in morph or "INFA" in morph:
        return True
    return bool(re.search(r"(ar|er|ir)$", stem_es.lower().strip()))


def _merge_prs_reading_gloss(hw: dict) -> bool:
    """Une stem.es + prs_suffix.es en una sola lectura («su nombre», «engendrarlo»…)."""
    prs = hw.get("prs_suffix")
    if not prs:
        return False
    suf_es = (prs.get("es") or "").strip()
    if not suf_es:
        return False
    stem_es = (hw.get("es") or "").strip()
    if not stem_es:
        return False

    morph = hw.get("he_morph") or ""
    sl = stem_es.lower()
    sf = suf_es.lower()
    merged: str | None = None

    if sl in _REL_ES and sf in _POSS_ES:
        prs["es"] = ""
        return True
    elif sl in _ART_ES and sf in _POSS_ES:
        noun = _infer_noun_es(hw)
        if noun:
            merged = _possessor_before_noun(sf, noun)
    elif morph.startswith("SUBS") or "SUBS." in morph:
        if sf in _POSS_ES:
            merged = _possessor_before_noun(sf, stem_es)
    elif "NEG" in morph:
        merged = f"{stem_es} {suf_es}"
    elif morph == "PREP" or morph.startswith("PREP"):
        merged = _prep_prs_reading(stem_es, suf_es)
    elif "VERBO" in morph or morph.startswith("VERB"):
        if sf in ("él", "ella", "ellos", "ellas"):
            merged = stem_es
        elif _is_spanish_infinitive(stem_es, morph) and sf in _ENCLITIC_ES:
            merged = stem_es + suf_es
        elif sf in _ENCLITIC_ES:
            merged = f"{suf_es} {stem_es}"
    else:
        if sf in ("él", "ella", "ellos", "ellas"):
            merged = stem_es
        elif _is_spanish_infinitive(stem_es, morph) and sf in _ENCLITIC_ES:
            merged = stem_es + suf_es
        elif sf in _POSS_ES:
            merged = _possessor_before_noun(sf, stem_es)
        elif sf in _ENCLITIC_ES:
            merged = f"{sf} {stem_es}"
        elif sl == "no":
            merged = f"{stem_es} {suf_es}"

    if not merged or merged.strip().lower() == sl:
        return False
    hw["es"] = merged.strip()
    prs["es"] = ""
    return True


def _prep_prs_reading(stem_es: str, suf_es: str) -> str | None:
    """Lectura natural prep+sufijo: con+te→contigo, a+ti→a ti…"""
    sl = stem_es.lower().strip()
    sf = suf_es.lower().strip()
    fused = {
        ("con", "te"): "contigo",
        ("con", "ti"): "contigo",
        ("con", "mí"): "conmigo",
        ("con", "mi"): "conmigo",
        ("con", "nos"): "con nosotros",
        ("con", "él"): "con él",
        ("con", "ella"): "con ella",
        ("con", "ellos"): "con ellos",
        ("con", "ustedes"): "con ustedes",
        ("con", "vosotros"): "con vosotros",
        ("a", "ti"): "a ti",
        ("a", "mí"): "a mí",
        ("a", "él"): "a él",
        ("a", "ella"): "a ella",
        ("de", "ti"): "de ti",
        ("de", "él"): "de él",
        ("de", "ella"): "de ella",
    }
    if (sl, sf) in fused:
        return fused[(sl, sf)]
    if sl in ("con", "a", "de", "para", "en") and sf in _ENCLITIC_ES | _POSS_ES | {"él", "ella", "ellos", "ellas", "mí"}:
        return f"{stem_es} {suf_es}"
    return None


def _prs_es_for_context(hw: dict, prs_morph: str) -> str:
    """Glosa española del sufijo pronominal según morfología del stem."""
    pm = (prs_morph or "").upper()
    stem_m = (hw.get("he_morph") or "").upper()
    raw = hw.get("raw") or ""

    if stem_m == "PREP" or stem_m.startswith("PREP"):
        prep_prs = {
            "PRS.P1.COMMON.SG": "mí",
            "PRS.P2.M.SG": "te",
            "PRS.P2.F.SG": "ti",
            "PRS.P3.M.SG": "él",
            "PRS.P3.F.SG": "ella",
            "PRS.P1.COMMON.PL": "nosotros",
            "PRS.P3.M.PL": "ellos",
            "PRS.P3.F.PL": "ellas",
        }
        return prep_prs.get(pm, "")

    if "SUBS" in stem_m or raw in ("W/BN/YW", "W/BN/YK", "BN/YK", "BN/YW", "L/M$PXT/YHM"):
        poss = {
            "PRS.P1.COMMON.SG": "mi",
            "PRS.P2.M.SG": "tu",
            "PRS.P2.F.SG": "tu",
            "PRS.P3.M.SG": "su",
            "PRS.P3.F.SG": "su",
            "PRS.P1.COMMON.PL": "nuestro",
            "PRS.P2.M.PL": "vuestro",
            "PRS.P3.M.PL": "sus",
            "PRS.P3.F.PL": "sus",
        }
        return poss.get(pm, "")

    if "VERBO" in stem_m or "VERB" in stem_m:
        obj = {
            "PRS.P3.M.SG": "lo",
            "PRS.P3.F.SG": "la",
            "PRS.P3.M.PL": "los",
            "PRS.P3.F.PL": "las",
            "PRS.P1.COMMON.SG": "me",
            "PRS.P2.M.SG": "te",
            "PRS.P2.F.SG": "te",
        }
        return obj.get(pm, "")

    if "SUBS.BOTH.SG.C" in stem_m or raw in ("YD/W", "RGL/H", "LB/W"):
        return {"PRS.P3.M.SG": "su", "PRS.P3.F.SG": "su"}.get(pm, "")

    return {
        "PRS.P3.M.SG": "su",
        "PRS.P3.F.SG": "su",
        "PRS.P2.M.SG": "tu",
        "PRS.P2.F.SG": "tu",
        "PRS.P3.M.PL": "sus",
    }.get(pm, "")


def _prefix_es_from_slot(prefix_morph: str, prefix_form: str, stem_morph: str) -> str:
    """Glosa española de prefijo hebreo (CONJ/PREP/ART/NEG)."""
    pm = (prefix_morph or "").upper()
    if pm == "CONJ":
        return "y"
    if pm == "NEG":
        return "no"
    if pm == "ART":
        return _article_es_from_morph(stem_morph)
    if pm == "PREP" or pm.startswith("PREP"):
        pf = _gen5_he_key({"he_form": prefix_form or ""})
        prep_map = {
            "ב": "en",
            "לב": "a",
            "בל": "en",
            "ל": "a",
            "לל": "a",
            "מ": "de",
            "מן": "de",
            "ממ": "de",
            "כ": "como",
            "ככ": "como",
            "על": "sobre",
            "עד": "hasta",
            "עם": "con",
            "אל": "a",
            "ש": "que",
        }
        for key, val in prep_map.items():
            if pf == key or pf.startswith(key):
                return val
        return "a"
    return ""


def _polish_chapter_es_glosses(
    data: dict, chapter: int, *, respect_user_gloss: bool = False,
) -> dict[str, int]:
    """Segunda pasada — glosas legibles en prefijos, sufijos y artículos."""
    stats = {"prefix_es": 0, "prs_es": 0, "merged": 0, "art_fix": 0, "dedupe": 0, "skipped": 0}

    for verse in data.get("verses", []):
        if verse.get("chapter") != chapter:
            continue
        for p in verse.get("pairs", []):
            for hw in p.get("he_words", []):
                if respect_user_gloss and _has_user_gloss(hw):
                    stem_morph = hw.get("he_morph") or ""
                    stem_es = (hw.get("es") or "").strip()
                    cleaned = _fix_leading_clitic_verb(_dedupe_adjacent_es(stem_es), stem_morph)
                    if cleaned != stem_es:
                        hw["es"] = cleaned
                        stats["dedupe"] += 1
                    stats["skipped"] += 1
                    continue
                src = (hw.get("es_source") or "").strip().lower()
                if src == "manual":
                    stats["skipped"] += 1
                    continue

                stem_morph = hw.get("he_morph") or ""
                stem_es = (hw.get("es") or "").strip()

                cleaned = _fix_leading_clitic_verb(_dedupe_adjacent_es(stem_es), stem_morph)
                if cleaned != stem_es:
                    hw["es"] = cleaned
                    stem_es = cleaned
                    stats["dedupe"] += 1

                if _stem_integrates_prs(hw):
                    if _drop_redundant_prs_suffix(hw):
                        stats["merged"] += 1
                    continue

                # Corregir lecturas invertidas prep+prs
                if stem_es.lower() in ("te con", "con te", "ti con"):
                    hw["es"] = "con"
                    prs = hw.get("prs_suffix") or {}
                    if not (prs.get("es") or "").strip():
                        prs["es"] = "ti"
                        hw["prs_suffix"] = prs
                    stem_es = "con"

                pfx_m = hw.get("prefix_morphs") or []
                pfx_e = hw.get("prefix_es") or []
                pfx_f = hw.get("prefix_forms") or []
                n = max(len(pfx_m), len(pfx_e), len(pfx_f))
                while len(pfx_e) < n:
                    pfx_e.append("")
                for i, pm in enumerate(pfx_m):
                    cur = (pfx_e[i] if i < len(pfx_e) else "").strip()
                    pf = pfx_f[i] if i < len(pfx_f) else ""
                    if pm == "ART":
                        target = _article_es_from_morph(stem_morph)
                        if cur != target:
                            pfx_e[i] = target
                            stats["art_fix"] += 1
                    elif not cur and pm in ("CONJ", "PREP", "ART", "NEG"):
                        fill = _prefix_es_from_slot(pm, pf, stem_morph)
                        if fill:
                            pfx_e[i] = fill
                            stats["prefix_es"] += 1
                if pfx_e:
                    hw["prefix_es"] = pfx_e

                prs = hw.get("prs_suffix") or {}
                if prs.get("he_form"):
                    prs_m = prs.get("he_morph") or ""
                    if not (prs.get("es") or "").strip() and not _stem_integrates_prs(hw):
                        fill = _prs_es_for_context(hw, prs_m)
                        if fill and not _prs_suffix_redundant(stem_es, fill):
                            prs["es"] = fill
                            stats["prs_es"] += 1

                    stem_es = (hw.get("es") or "").strip()
                    if (stem_morph == "PREP" or stem_morph.startswith("PREP")) and (prs.get("es") or "").strip():
                        merged = _prep_prs_reading(stem_es, prs.get("es", ""))
                        if merged and merged.lower() != stem_es.lower():
                            hw["es"] = merged
                            if (hw.get("es_source") or "").strip().lower() == "patch":
                                prs["es"] = ""
                                hw["prs_suffix"] = prs
                            else:
                                hw.pop("prs_suffix", None)
                            stats["merged"] += 1
                            continue

                if _merge_prs_reading_gloss(hw):
                    stats["merged"] += 1
                elif (hw.get("he_morph") or "").startswith("PREP"):
                    prs = hw.get("prs_suffix") or {}
                    suf = (prs.get("es") or "").strip()
                    stem_es = (hw.get("es") or "").strip()
                    if suf and stem_es:
                        merged = _prep_prs_reading(stem_es, suf)
                        if merged and merged.lower() != stem_es.lower():
                            hw["es"] = merged
                            if (hw.get("es_source") or "").strip().lower() == "patch":
                                prs["es"] = ""
                                hw["prs_suffix"] = prs
                            else:
                                hw.pop("prs_suffix", None)
                            stats["merged"] += 1

                cleaned = _fix_leading_clitic_verb(_dedupe_adjacent_es((hw.get("es") or "").strip()), stem_morph)
                if cleaned != (hw.get("es") or "").strip():
                    hw["es"] = cleaned
                    stats["dedupe"] += 1

                _drop_redundant_prs_suffix(hw)

    return stats


def _polish_gen8_es_glosses(data: dict, *, respect_user_gloss: bool = False) -> dict[str, int]:
    return _polish_chapter_es_glosses(data, 8, respect_user_gloss=respect_user_gloss)


def _polish_gen9_es_glosses(data: dict, *, respect_user_gloss: bool = False) -> dict[str, int]:
    return _polish_chapter_es_glosses(data, 9, respect_user_gloss=respect_user_gloss)


def _polish_gen10_es_glosses(data: dict, *, respect_user_gloss: bool = False) -> dict[str, int]:
    return _polish_chapter_es_glosses(data, 10, respect_user_gloss=respect_user_gloss)


def _polish_gen11_es_glosses(data: dict, *, respect_user_gloss: bool = False) -> dict[str, int]:
    return _polish_chapter_es_glosses(data, 11, respect_user_gloss=respect_user_gloss)


def _polish_gen12_es_glosses(data: dict, *, respect_user_gloss: bool = False) -> dict[str, int]:
    return _polish_chapter_es_glosses(data, 12, respect_user_gloss=respect_user_gloss)


def _polish_gen13_es_glosses(data: dict, *, respect_user_gloss: bool = False) -> dict[str, int]:
    return _polish_chapter_es_glosses(data, 13, respect_user_gloss=respect_user_gloss)


def _polish_gen14_es_glosses(data: dict, *, respect_user_gloss: bool = False) -> dict[str, int]:
    return _polish_chapter_es_glosses(data, 14, respect_user_gloss=respect_user_gloss)


def _polish_gen15_es_glosses(data: dict, *, respect_user_gloss: bool = False) -> dict[str, int]:
    return _polish_chapter_es_glosses(data, 15, respect_user_gloss=respect_user_gloss)


def _polish_gen16_es_glosses(data: dict, *, respect_user_gloss: bool = False) -> dict[str, int]:
    return _polish_chapter_es_glosses(data, 16, respect_user_gloss=respect_user_gloss)

def _polish_gen17_es_glosses(data: dict, *, respect_user_gloss: bool = False) -> dict[str, int]:
    return _polish_chapter_es_glosses(data, 17, respect_user_gloss=respect_user_gloss)

def _polish_gen18_es_glosses(data: dict, *, respect_user_gloss: bool = False) -> dict[str, int]:
    return _polish_chapter_es_glosses(data, 18, respect_user_gloss=respect_user_gloss)

def _polish_gen19_es_glosses(data: dict, *, respect_user_gloss: bool = False) -> dict[str, int]:
    return _polish_chapter_es_glosses(data, 19, respect_user_gloss=respect_user_gloss)

def _polish_gen20_es_glosses(data: dict, *, respect_user_gloss: bool = False) -> dict[str, int]:
    return _polish_chapter_es_glosses(data, 20, respect_user_gloss=respect_user_gloss)

def _polish_gen21_es_glosses(data: dict, *, respect_user_gloss: bool = False) -> dict[str, int]:
    return _polish_chapter_es_glosses(data, 21, respect_user_gloss=respect_user_gloss)

def _polish_gen22_es_glosses(data: dict, *, respect_user_gloss: bool = False) -> dict[str, int]:
    return _polish_chapter_es_glosses(data, 22, respect_user_gloss=respect_user_gloss)

def _polish_gen23_es_glosses(data: dict, *, respect_user_gloss: bool = False) -> dict[str, int]:
    return _polish_chapter_es_glosses(data, 23, respect_user_gloss=respect_user_gloss)

def _polish_gen24_es_glosses(data: dict, *, respect_user_gloss: bool = False) -> dict[str, int]:
    return _polish_chapter_es_glosses(data, 24, respect_user_gloss=respect_user_gloss)

def _polish_gen25_es_glosses(data: dict, *, respect_user_gloss: bool = False) -> dict[str, int]:
    return _polish_chapter_es_glosses(data, 25, respect_user_gloss=respect_user_gloss)

def _polish_gen26_es_glosses(data: dict, *, respect_user_gloss: bool = False) -> dict[str, int]:
    return _polish_chapter_es_glosses(data, 26, respect_user_gloss=respect_user_gloss)

def _polish_gen27_es_glosses(data: dict, *, respect_user_gloss: bool = False) -> dict[str, int]:
    return _polish_chapter_es_glosses(data, 27, respect_user_gloss=respect_user_gloss)

def _polish_gen28_es_glosses(data: dict, *, respect_user_gloss: bool = False) -> dict[str, int]:
    return _polish_chapter_es_glosses(data, 28, respect_user_gloss=respect_user_gloss)

def _polish_gen29_es_glosses(data: dict, *, respect_user_gloss: bool = False) -> dict[str, int]:
    return _polish_chapter_es_glosses(data, 29, respect_user_gloss=respect_user_gloss)

def _polish_gen30_es_glosses(data: dict, *, respect_user_gloss: bool = False) -> dict[str, int]:
    return _polish_chapter_es_glosses(data, 30, respect_user_gloss=respect_user_gloss)


_USER_GLOSS_SOURCES = frozenset({"glosa_personal", "glosa_global", "manual"})

_TAAMIM_RE = re.compile(r"[\u0591-\u05AF]")


def _strip_taamim(he: str) -> str:
    return _TAAMIM_RE.sub("", he or "")


def _is_tetragrammaton(hw: dict) -> bool:
    """True si el token es יהוה (CATSS YHWH o consonantes TM)."""
    raw = (hw.get("raw") or "").upper()
    if "YHWH" in raw:
        return True
    from morph_validate_utils import fold_he
    return fold_he(_strip_taamim(hw.get("he_form") or "")) == "יהוה"


def _yhwh_es_from_form(he_form: str) -> str:
    """Glosa según vocalización qere: Adonai → Hashem; Elohim → 'Elohim."""
    h = _strip_taamim(he_form)
    # Holam en he (יְהֹוָה)
    if re.search(r"ה\u05B9", h) or "הֹ" in h:
        return "'Elohim"
    # יֱהוִה (segol compuesto + hiriq tras Adonai)
    if "\u05B1" in h and re.search(r"ו\u05B4", h):
        return "'Elohim"
    # Vocalización Adonai (יְהוָה y variantes con qamats en vav)
    return "Hashem"


def _load_oshb_forms_by_ref(oshb_dir: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    if not oshb_dir.is_dir():
        return out
    for ch_file in sorted(oshb_dir.glob("*.json")):
        try:
            ch = int(ch_file.stem)
        except ValueError:
            continue
        block = json.loads(ch_file.read_text(encoding="utf-8"))
        for vs, rec in block.items():
            out[f"{ch}:{vs}"] = list(rec.get("forms") or [])
    return out


def _apply_yhwh_vowel_forms(
    data: dict,
    oshb_forms: dict[str, list[str]],
    *,
    respect_user_gloss: bool = False,
) -> dict[str, int]:
    """Inyecta vocalización OSHB en יהוה y alinea glosa Hashem / 'Elohim."""
    from morph_validate_utils import fold_he

    stats = {"he_form": 0, "es": 0, "strongs": 0, "missing_oshb": 0}
    for verse in data.get("verses", []):
        ref = f"{verse.get('chapter')}:{verse.get('verse')}"
        forms = oshb_forms.get(ref, [])
        pointed_queue = [
            strip_leading_maqaf(_strip_taamim(f))
            for f in forms
            if fold_he(strip_leading_maqaf(f)) == "יהוה"
        ]
        qi = 0
        tetragrams: list[dict] = []
        for p in verse.get("pairs", []):
            if p.get("kind") in ("gk_add", "heb_omit"):
                continue
            for hw in p.get("he_words", []):
                if _is_tetragrammaton(hw):
                    tetragrams.append(hw)

        for hw in tetragrams:
            if qi < len(pointed_queue):
                pointed = pointed_queue[qi]
                qi += 1
            else:
                pointed = _strip_taamim(hw.get("he_form") or "")
                if not pointed or not re.search(r"[\u05B0-\u05BD]", pointed):
                    pointed = "יְהוָה"
                    stats["missing_oshb"] += 1

            if (hw.get("he_form") or "") != pointed:
                hw["he_form"] = pointed
                stats["he_form"] += 1

            if hw.get("strongs") != "H3068":
                hw["strongs"] = "H3068"
                stats["strongs"] += 1
            if (hw.get("he_morph") or "") != "NPROP":
                hw["he_morph"] = "NPROP"

            target_es = _yhwh_es_from_form(pointed)
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            if (hw.get("es") or "").strip() != target_es:
                hw["es"] = target_es
                hw["es_source"] = "patch_yhwh"
                stats["es"] += 1

    return stats


def _is_nprop_morph(morph: str) -> bool:
    m = (morph or "").upper()
    return m == "NPROP" or m.startswith("NPROP.")


# Glosas que no son nombres propios aunque el token lleve NPROP (אדם = hombre genérico).
_NPROP_CAP_SKIP_ES = frozenset({
    "hombre", "mujer", "tierra", "dios", "señor", "y", "salgamos",
})

# Formas preferidas con tildes / convención del proyecto (clave en minúsculas).
_NPROP_CANON_ES: dict[str, str] = {
    "adán": "Adán",
    "abel": "Abel",
    "abram": "Abram",
    "ada": "Ada",
    "asiria": "Asiria",
    "caín": "Caín",
    "cainán": "Cainán",
    "cam": "Cam",
    "cus": "Cus",
    "edén": "Edén",
    "enoc": "Enoc",
    "enós": "Enós",
    "eufrates": "Éufrates",
    "eva": "Eva",
    "gihón": "Gihón",
    "hashem": "Hashem",
    "havila": "Havila",
    "hidekel": "Hidekel",
    "irad": "Irad",
    "jabal": "Jabal",
    "jehová": "Jehová",
    "jubal": "Jubal",
    "jared": "Jared",
    "jafet": "Jafet",
    "lamec": "Lamec",
    "mehujael": "Mehujael",
    "metusael": "Metusael",
    "mahalaleel": "Mahalaleel",
    "matusalén": "Matusalén",
    "noé": "Noé",
    "nod": "Nod",
    "naama": "Naama",
    "pisón": "Pisón",
    "set": "Set",
    "sem": "Sem",
    "tubal": "Tubal",
    "tubal-caín": "Tubal-Caín",
    "zila": "Zila",
    "elohim": "Elohim",
    "'elohim": "'Elohim",
}


def _capitalize_proper_name_es(es: str) -> str:
    """Mayúscula inicial en nombres/lugares; respeta 'Elohim y compuestos con guión."""
    es = (es or "").strip()
    if not es:
        return es
    key = es.lower()
    if key in _NPROP_CANON_ES:
        return _NPROP_CANON_ES[key]
    parts = es.split("-")
    out: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            out.append(part)
            continue
        subkey = part.lower()
        if subkey in _NPROP_CANON_ES:
            out.append(_NPROP_CANON_ES[subkey])
            continue
        if part[0] in ("'", "\u02BF", "\u02BE") and len(part) > 1:
            out.append(part[0] + part[1].upper() + part[2:])
        else:
            out.append(part[0].upper() + part[1:])
    return "-".join(out)


def _apply_nprop_capitalization(
    data: dict,
    *,
    chapters: tuple[int, ...] | None = None,
) -> int:
    """Normaliza glosas NPROP con mayúscula inicial (no pisa glosas del editor)."""
    n = 0
    for verse in data.get("verses", []):
        ch = verse.get("chapter", 0)
        if chapters is not None and ch not in chapters:
            continue
        for p in verse.get("pairs", []):
            for hw in p.get("he_words", []):
                if not _is_nprop_morph(hw.get("he_morph") or ""):
                    continue
                if _has_user_gloss(hw):
                    continue
                es = (hw.get("es") or "").strip()
                if not es or es.lower() in _NPROP_CAP_SKIP_ES:
                    continue
                new_es = _capitalize_proper_name_es(es)
                if new_es != es:
                    hw["es"] = new_es
                    src = (hw.get("es_source") or "").strip()
                    if src not in _USER_GLOSS_SOURCES:
                        hw["es_source"] = "patch_nprop_cap"
                    n += 1
    return n


def _has_user_gloss(hw: dict) -> bool:
    return (hw.get("es_source") or "").strip().lower() in _USER_GLOSS_SOURCES


def _set_es_patch(hw: dict, es: str, *, respect_user: bool = False) -> None:
    """Asigna glosa de parche; no pisa glosas del editor si respect_user."""
    if respect_user and _has_user_gloss(hw):
        return
    hw["es"] = es
    hw["es_source"] = "patch"


def _patch_gen2(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Parches estructurales Génesis cap. 2 (desalineación SpaRV1909 / tokens rotos).

    respect_user_gloss: si True, no sobrescribe es con es_source glosa_personal/global/manual
    (usar tras Pass 15 para no revertir ediciones del editor).
    """
    vrs = verse.get("verse", 0)
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            raw = hw.get("raw", "")
            he = (hw.get("he_form") or "").strip()

            if vrs == 1 and raw == "CB)/M":
                hw["he_form"] = "צְבָאָם"
                hw["strongs"] = "H6635"
                hw["he_morph"] = "SUBS.M.SG.C"
                hw["es"] = "su ejército"
                hw.pop("prs_suffix", None)
                hw["es_source"] = "patch"

            elif raw == "ML)KT/W" and vrs in (2, 3):
                # מְלַאכְתּוֹ mal parseada como אֲשֶׁר (CATSS/LXX sangrado)
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "מְלַאכְתּוֹ"
                hw["strongs"] = "H4399"
                hw["he_morph"] = "SUBS.F.SG.C"
                _set_es_patch(hw, "su obra", respect_user=respect_user_gloss)
                hw["gr_word"] = _san_gr("τῶν ἔργων αὐτοῦ")
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif vrs == 2 and raw == "W/Y$BT":
                _set_es_patch(hw, "reposó", respect_user=respect_user_gloss)

            elif vrs == 3:
                if raw == ")T/W":
                    _set_es_patch(hw, "lo", respect_user=respect_user_gloss)
                elif raw == "B/W":
                    hw["gr_word"] = _san_gr("ἐν αὐτῇ")
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"
                elif raw == "BR)":
                    hw["he_form"] = "בָּרָא"
                    hw["strongs"] = "H1254"
                    hw["he_morph"] = "VERBO.QAL.PERF.P3.M.SG"
                    _set_es_patch(hw, "creó", respect_user=respect_user_gloss)
                elif raw == "L/(&WT":
                    hw["strongs"] = "H6213"
                    hw["he_morph"] = "VERBO.QAL.INFC"
                    hw["prefix_es"] = ["para"]
                    _set_es_patch(hw, "hacer", respect_user=respect_user_gloss)
                elif raw == "M/KL":
                    hw["gr_word"] = _san_gr("πάντων")
                    pgr = hw.get("prefix_gr") or []
                    if pgr:
                        pgr[0] = _san_gr("ἀπὸ")
                        hw["prefix_gr"] = pgr
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

            elif vrs == 6 and raw == "PNY":
                hw["he_form"] = "פְּנֵי"
                hw["strongs"] = "H6440"
                hw["he_morph"] = "SUBS.BOTH.PL.C"
                hw["es"] = "delante"
                hw["es_source"] = "patch"

            elif vrs == 7 and raw == "B/)P/YW":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "בְּאַפָּיו"
                hw["he_morph"] = "PREP+SUBS.M.DU.C"
                hw["strongs"] = "H639"
                hw["es"] = "en sus narices"
                hw.pop("prs_suffix", None)
                hw["es_source"] = "patch"

            elif vrs == 17:
                if raw == "KY":
                    hw["es"] = "porque"
                    hw["es_source"] = "patch"
                elif raw == "B/YWM":
                    hw["prefix_es"] = ["en"]
                    hw["es_source"] = "patch"
                elif raw == "M/MN/W" and he.startswith("כ"):
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "מִמֶּנּוּ"
                    hw["he_morph"] = "PREP+PRS.P3.M.SG"
                    hw["es"] = "de ello"
                    hw["es_source"] = "patch"
                elif raw == "M/MN/W" and he.startswith("ת"):
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "תָמוּת"
                    hw["strongs"] = "H4191"
                    hw["he_morph"] = "VERBO.QAL.IMPF.P2.M.SG"
                    hw["es"] = "morirás"
                    hw["es_source"] = "patch"
                elif raw == ")KL/K":
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "מִמֶּנּוּ"
                    hw["he_morph"] = "PREP+PRS.P3.M.SG"
                    hw["es"] = "de ello"
                    hw["es_source"] = "patch"
                elif raw == "MWT":
                    hw["es"] = "morir"
                    hw["es_source"] = "patch"
                elif raw == "TMWT":
                    hw["es"] = "morirás"
                    hw["strongs"] = "H4191"
                    hw["he_morph"] = "VERBO.QAL.IMPF.P2.M.SG"
                    hw["es_source"] = "patch"

            elif vrs == 18:
                if raw == "L/BD/W":
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "לְבַדּוֹ"
                    hw["he_morph"] = "PREP+SUBS.M.SG.C"
                    hw["strongs"] = "H905"
                    hw["es"] = "solo"
                    hw["es_source"] = "patch"
                elif raw == "K/NGD/W":
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "כְּנֶגְדּוֹ"
                    hw["he_morph"] = "PREP+SUBS+PRS.P3.M.SG"
                    hw["strongs"] = "H5048"
                    hw["es"] = "correspondiente a él"
                    hw["es_source"] = "patch"

            elif vrs == 24:
                if raw == ")BY/W":
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "אָבִיו"
                    hw["strongs"] = "H1"
                    hw["he_morph"] = "SUBS.M.SG.C"
                    hw["es"] = "su padre"
                    hw["es_source"] = "patch"
                elif raw == ")M/W":
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "אִמּוֹ"
                    hw["strongs"] = "H517"
                    hw["he_morph"] = "SUBS.F.SG.C"
                    hw["es"] = "su madre"
                    hw["es_source"] = "patch"
                elif raw == "B/)$T/W":
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "בְּאִשְׁתּוֹ"
                    hw["he_morph"] = "PREP+SUBS.F.SG.C"
                    hw["strongs"] = "H802"
                    hw["es"] = "a su mujer"
                    hw["es_source"] = "patch"
                elif raw == "L/B&R":
                    hw["prefix_es"] = ["en"]
                    hw["es_source"] = "patch"

            elif vrs == 19 and raw == "$M/W":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "שְׁמוֹ"
                hw["strongs"] = "H8034"
                hw["he_morph"] = "SUBS.M.SG.C"
                hw["es"] = "su nombre"
                hw["es_source"] = "patch"

            elif vrs == 20 and raw == "K/NGD/W":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "כְּנֶגְדּוֹ"
                hw["he_morph"] = "PREP+SUBS+PRS.P3.M.SG"
                hw["strongs"] = "H5048"
                hw["es"] = "delante de él"
                hw["es_source"] = "patch"

            elif vrs == 21:
                if raw == "M/CL(T/YW":
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "מִצַּלְעֹתָיו"
                    hw["strongs"] = "H6763"
                    hw["he_morph"] = "PREP+SUBS.F.PL.C"
                    hw["es"] = "de su costado"
                    hw.pop("prs_suffix", None)
                    hw["es_source"] = "patch"
                elif raw == "TXT/NH":
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "תַּחְתֶּנָּה"
                    hw["he_morph"] = "PREP+PRS.P3.F.SG"
                    hw["es"] = "debajo de ella"
                    hw["es_source"] = "patch"

            elif vrs == 23 and raw == "M/(CM/Y":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "מֵעֲצָמַי"
                hw["strongs"] = "H6106"
                hw["he_morph"] = "PREP+SUBS.F.PL.C"
                hw["es"] = "de mis huesos"
                hw["es_source"] = "patch"

            elif vrs == 25:
                if raw == "$N/YHM":
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "שְׁנֵיהֶם"
                    hw["he_morph"] = "NUM.CARD.M.DU.C"
                    hw["es"] = "ambos"
                    hw["es_source"] = "patch"
                elif raw == "W/)$T/W":
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "וְאִשְׁתּוֹ"
                    hw["he_morph"] = "CONJ+SUBS.F.SG.C"
                    hw["strongs"] = "H802"
                    hw["es"] = "y su mujer"
                    hw["es_source"] = "patch"


def _patch_gen3(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Parches estructurales Génesis cap. 3 — fusión PRS, sangrado LXX/CATSS."""
    vrs = verse.get("verse", 0)
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            raw = hw.get("raw", "")
            he = (hw.get("he_form") or "").strip()

            if raw == "W/)$T/W":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "וְאִשְׁתּוֹ"
                hw["strongs"] = "H802"
                hw["he_morph"] = "CONJ+SUBS.F.SG.C"
                _set_es_patch(hw, "y su mujer", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "W/L/)$T/W":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "וּלְאִשְׁתּוֹ"
                hw["strongs"] = "H802"
                hw["he_morph"] = "CONJ+PREP+SUBS.F.SG.C"
                _set_es_patch(hw, "y a su mujer", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "$N/YHM":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "שְׁנֵיהֶם"
                hw["he_morph"] = "NUM.CARD.M.DU.C"
                _set_es_patch(hw, "ambos", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "L/)Y$/H":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "לְאִישָׁהּ"
                hw["strongs"] = "H376"
                hw["he_morph"] = "PREP+SUBS.M.SG.C"
                _set_es_patch(hw, "a su marido", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "M/PRY/W":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "מִפִּרְיוֹ"
                hw["strongs"] = "H6529"
                hw["he_morph"] = "PREP+SUBS.M.SG.C"
                _set_es_patch(hw, "de su fruto", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "L/H&KYL":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "לְהַשְׂכִּיל"
                hw["strongs"] = "H7919"
                hw["he_morph"] = "PREP+VERBO.HIF.INFC"
                _set_es_patch(hw, "para entender", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == ")Y/KH":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "אַיֶּכָּה"
                hw["strongs"] = "H335"
                hw["he_morph"] = "PART.INTERR"
                _set_es_patch(hw, "¿dónde estás?", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "L/W" and vrs == 9:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "לוֹ"
                hw["he_morph"] = "PREP+PRS.P3.M.SG"
                _set_es_patch(hw, "a él", respect_user=respect_user_gloss)
                hw["gr_word"] = _san_gr("αὐτῷ")
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "QL/K" and vrs == 10:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "קֹלְךָ"
                hw["strongs"] = "H6963"
                hw["he_morph"] = "SUBS.M.SG.C"
                _set_es_patch(hw, "tu voz", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "(MD/Y" and vrs == 12:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "עִמִּי"
                hw["he_morph"] = "PREP+PRS.P1.COMMON.SG"
                _set_es_patch(hw, "conmigo", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif vrs == 17 and raw in (")DM", "W/L/)DM"):
                hw["strongs"] = "H121"
                hw["he_morph"] = "NPROP"
                if not (hw.get("he_form") or "").strip():
                    hw["he_form"] = "אָדָם"
                _set_es_patch(hw, "Adán", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "M/MN/W":
                if vrs == 17:
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "מִמֶּנּוּ"
                    hw["he_morph"] = "PREP+PRS.P3.M.SG"
                    hw["strongs"] = "H4480"
                    _set_es_patch(hw, "de ello", respect_user=respect_user_gloss)
                    hw.pop("prs_suffix", None)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"
                elif vrs in (5, 11, 22) or not he or he in ("וְ", "לָ"):
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "מִמֶּנּוּ"
                    hw["he_morph"] = "PREP+PRS.P3.M.SG"
                    hw["strongs"] = "H4480"
                    es = "de nosotros" if vrs == 22 else "de ello"
                    _set_es_patch(hw, es, respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

            elif raw == "(YN/YKM" and vrs == 5:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "עֵינֵיכֶם"
                hw["strongs"] = "H5869"
                hw["he_morph"] = "SUBS.BOTH.DU.C"
                _set_es_patch(hw, "vuestros ojos", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == ")KL/KM" and vrs == 5:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "אֲכָלְכֶם"
                hw["strongs"] = "H398"
                hw["he_morph"] = "VERBO.QAL.INFC"
                _set_es_patch(hw, "comáis", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "M/MN/H" and vrs == 19:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "מִמֶּנָּּה"
                hw["he_morph"] = "PREP+PRS.P3.F.SG"
                hw["strongs"] = "H4480"
                _set_es_patch(hw, "de ella", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == ".$c" or (raw or "").startswith(".$"):
                _clear_hw_prefix_slots(hw)
                hw["raw"] = raw  # conservar ref CATSS
                hw["he_form"] = ""
                hw["he_morph"] = ""
                hw["strongs"] = ""
                hw["es"] = ""
                hw.pop("prs_suffix", None)
                hw["es_source"] = "patch_meta"

            elif raw == "GXN/K" and vrs == 14:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "גְּחֹנֶךָ"
                hw["strongs"] = "H1512"
                hw["he_morph"] = "SUBS.M.SG.C"
                _set_es_patch(hw, "tu vientre", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "XY/YK":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "חַיֶּיךָ"
                hw["strongs"] = "H2416"
                hw["he_morph"] = "SUBS.M.PL.C"
                _set_es_patch(hw, "tu vida", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "BYN/K" and vrs == 15:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "בֵּינְךָ"
                hw["he_morph"] = "PREP+PRS.P2.M.SG"
                _set_es_patch(hw, "entre ti", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "ZR(/K" and vrs == 15:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "זַרְעֲךָ"
                hw["strongs"] = "H2233"
                hw["he_morph"] = "SUBS.M.SG.C"
                _set_es_patch(hw, "tu simiente", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "ZR(/H" and vrs == 15:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "זַרְעָהּ"
                hw["strongs"] = "H2233"
                hw["he_morph"] = "SUBS.M.SG.C"
                _set_es_patch(hw, "su simiente", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "Y$WP/K" and vrs == 15:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "יְשׁוּפְךָ"
                hw["strongs"] = "H7779"
                hw["he_morph"] = "VERBO.QAL.IMPF.P3.M.SG"
                _set_es_patch(hw, "te herirá", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "T$WP/NW" and vrs == 15:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "תְּשׁוּפֶנּוּ"
                hw["strongs"] = "H7779"
                hw["he_morph"] = "VERBO.QAL.IMPF.P2.M.SG"
                _set_es_patch(hw, "le herirás", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "(CBWN/K" and vrs == 16:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "עִצְּבֹנֵךְ"
                hw["strongs"] = "H6093"
                hw["he_morph"] = "SUBS.M.SG.C"
                _set_es_patch(hw, "tu dolor", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "W/HRN/K" and vrs == 16:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "וְהֵרֹנֵךְ"
                hw["strongs"] = "H2032"
                hw["he_morph"] = "CONJ+SUBS.M.SG.C"
                _set_es_patch(hw, "y tu gemido", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == ")Y$/K" and vrs == 16:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "אִישֵׁךְ"
                hw["strongs"] = "H376"
                hw["he_morph"] = "SUBS.M.SG.C"
                _set_es_patch(hw, "tu marido", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "T$WQT/K" and vrs == 16:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "תְּשׁוּקָתֵךְ"
                hw["strongs"] = "H8669"
                hw["he_morph"] = "SUBS.F.SG.C"
                _set_es_patch(hw, "tu deseo", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == ")$T/K" and vrs == 17:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "אִשְׁתְּךָ"
                hw["strongs"] = "H802"
                hw["he_morph"] = "SUBS.F.SG.C"
                _set_es_patch(hw, "tu mujer", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "B/(BWR/K" and vrs == 17:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "בַּעֲבוּרֶךָ"
                hw["strongs"] = "H5668"
                hw["he_morph"] = "PREP+SUBS.M.SG.C"
                _set_es_patch(hw, "por tu causa", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == ")P/YK" and vrs == 19:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "אַפֶּיךָ"
                hw["strongs"] = "H639"
                hw["he_morph"] = "SUBS.M.PL.C"
                _set_es_patch(hw, "tu rostro", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "LQX" and vrs == 23:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "שָׁם"
                hw["strongs"] = "H8033"
                hw["he_morph"] = "ADV"
                _set_es_patch(hw, "allí", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "M/KL" and vrs == 1:
                pm = hw.get("prefix_morphs") or []
                if pm and pm[0] != "PREP":
                    _clear_hw_prefix_slots(hw)
                    hw["prefix_forms"] = ["מִ"]
                    hw["prefix_morphs"] = ["PREP"]
                    hw["prefix_es"] = ["de"]
                    hw["prefix_gr"] = [_san_gr("ἀπὸ")]
                    hw["he_form"] = "כֹּל"
                    hw["strongs"] = "H3605"
                    hw["he_morph"] = "SUBS.M.SG.C"
                    _set_es_patch(hw, "todo", respect_user=respect_user_gloss)
                    hw["gr_word"] = _san_gr("πάντων")
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

            elif raw == "W/NPQXW" and vrs == 5:
                pm = hw.get("prefix_morphs") or []
                if pm and pm[0].startswith("VERBO"):
                    _clear_hw_prefix_slots(hw)
                    hw["prefix_forms"] = ["וְ"]
                    hw["prefix_morphs"] = ["CONJ"]
                    hw["prefix_es"] = ["y"]
                    hw["he_form"] = "נִפְקְחוּ"
                    hw["strongs"] = "H6491"
                    hw["he_morph"] = "VERBO.NIF.SEQ.PERF.P3.COMMON.PL"
                    _set_es_patch(hw, "serán abiertos", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

            elif raw == "(M/H" and vrs == 6:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "עִמָּהּ"
                hw["he_morph"] = "PREP+PRS.P3.F.SG"
                _set_es_patch(hw, "con ella", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "W/HW)" and vrs == 16:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "וְהוּא"
                hw["strongs"] = "H1931"
                hw["he_morph"] = "CONJ+PRON.PERS.P3.M.SG"
                _set_es_patch(hw, "y él", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "T)KL/NH" and vrs == 17:
                pm = hw.get("prefix_morphs") or []
                if pm and pm[0].startswith("SUBS"):
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "כֹּל יְמֵי"
                    hw["strongs"] = "H3605"
                    hw["he_morph"] = "SUBS.M.PL.C"
                    _set_es_patch(hw, "todos los días", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

            elif raw == "YD/W" and vrs == 22:
                pm = hw.get("prefix_morphs") or []
                if pm and pm[0].startswith("PRS"):
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "יָדוֹ"
                    hw["strongs"] = "H3027"
                    hw["he_morph"] = "SUBS.F.SG.C"
                    _set_es_patch(hw, "su mano", respect_user=respect_user_gloss)
                    hw.pop("prs_suffix", None)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

            elif raw == "W/LQX" and vrs == 22:
                pm = hw.get("prefix_morphs") or []
                if pm and pm[0].startswith("VERBO"):
                    _clear_hw_prefix_slots(hw)
                    hw["prefix_forms"] = ["וְ"]
                    hw["prefix_morphs"] = ["CONJ"]
                    hw["prefix_es"] = ["y"]
                    hw["he_form"] = "לָקַח"
                    hw["strongs"] = "H3947"
                    hw["he_morph"] = "VERBO.QAL.SEQ.PERF.P3.M.SG"
                    _set_es_patch(hw, "tomará", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

            elif raw == "W/T)KL" and vrs == 6 and not hw.get("strongs"):
                hw["strongs"] = "H398"

    _sanitize_catss_pairs(verse)


def _attach_prs_suffix(hw: dict, suf_he: str, suf_morph: str, suf_es: str) -> None:
    hw["prs_suffix"] = {
        "he_form": suf_he,
        "he_morph": suf_morph,
        "es": suf_es,
        "gr_word": "",
        "strongs": "",
    }


def _new_hrg_w_hw() -> dict:
    """Token CATSS HRG/W (הֲרָג + וֹ) para reconstruir si se perdió en merge."""
    return {
        "raw": "HRG/W",
        "prefixes": ["HRG"],
        "stem": "W",
        "prefix_labels": [],
        "stem_label": "",
        "prefix_unicode": "הרג",
        "stem_unicode": "ו",
        "full_unicode": "הרגו",
        "heb_label": "",
        "he_form": "הֲרָג",
        "he_morph": "VERBO.QAL.PERF.P3.M.SG",
        "strongs": "H2026",
        "es": "mató",
        "es_source": "patch",
        "prs_suffix": {
            "he_form": "וֹ",
            "he_morph": "PRS.P3.M.SG",
            "es": "lo",
            "gr_word": "",
            "strongs": "",
        },
    }


def _fix_gen4_v25(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Post-proceso 4:25 — HRG/W, L/Y espurio, KY/(WD/$T, splits PRS."""
    if verse.get("verse") != 25:
        return
    pairs = verse.get("pairs", [])
    st_n = 0
    for p in pairs:
        hws = p.get("he_words") or []
        raws = [hw.get("raw") for hw in hws]
        if raws == ["KY"] and "HRG" in (p.get("he") or ""):
            hws.append(_new_hrg_w_hw())
            p["he_words"] = hws
        for hw in hws:
            raw = hw.get("raw", "")
            if raw == "(WD":
                hw["he_form"] = "עוֹד"
                hw["he_morph"] = "ADV"
                hw["strongs"] = "H5750"
                _set_es_patch(hw, "aún", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"
            elif raw == "KY":
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    es = (hw.get("es") or "").strip().lower()
                    if es in ("y", ""):
                        _set_es_patch(hw, "porque", respect_user=respect_user_gloss)
            elif raw == "L/Y":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = ""
                hw["he_morph"] = ""
                hw["strongs"] = ""
                hw["es"] = ""
                hw["es_source"] = "patch_meta"
            elif raw == "HRG/W":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "הֲרָג"
                hw["strongs"] = "H2026"
                hw["he_morph"] = "VERBO.QAL.PERF.P3.M.SG"
                _set_es_patch(hw, "mató", respect_user=respect_user_gloss)
                _attach_prs_suffix(hw, "וֹ", "PRS.P3.M.SG", "lo")
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"
            elif raw == "$T":
                st_n += 1
                if st_n == 1:
                    hw["he_form"] = "שֵׁת"
                    hw["strongs"] = "H8352"
                    hw["he_morph"] = "NPROP"
                    _set_es_patch(hw, "Set", respect_user=respect_user_gloss)
                elif st_n == 2:
                    hw["he_form"] = "שָׁת"
                    hw["strongs"] = "H7896"
                    hw["he_morph"] = "VERBO.QAL.PERF.P3.M.SG"
                    _set_es_patch(hw, "sustituyó", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"


def _patch_gen4(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Parches estructurales Génesis cap. 4 — PRS/CATSS, sangrado, nombres."""
    vrs = verse.get("verse", 0)
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            raw = hw.get("raw", "")
            he = (hw.get("he_form") or "").strip()

            if raw == ")$T/W":
                _clear_hw_prefix_slots(hw)
                hw["strongs"] = "H802"
                hw["he_morph"] = "SUBS.F.SG.C"
                if vrs == 25:
                    hw["he_form"] = "אִשְׁתּ"
                    _set_es_patch(hw, "mujer", respect_user=respect_user_gloss)
                    _attach_prs_suffix(hw, "וֹ", "PRS.P3.M.SG", "su")
                else:
                    hw["he_form"] = "אִשְׁתּוֹ"
                    _set_es_patch(hw, "su mujer", respect_user=respect_user_gloss)
                    hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "M/BKRWT" and vrs == 4:
                hw["he_form"] = "בְּכֹרוֹת"
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == ")XY/W":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "אָחִיו"
                hw["strongs"] = "H251"
                hw["he_morph"] = "SUBS.M.SG.C"
                _set_es_patch(hw, "su hermano", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "C)N/W":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "צֹאנ"
                hw["strongs"] = "H6629"
                hw["he_morph"] = "SUBS.BOTH.SG.C"
                _set_es_patch(hw, "rebaño", respect_user=respect_user_gloss)
                _attach_prs_suffix(hw, "וֹ", "PRS.P3.M.SG", "su")
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "W/M/XLB/HN":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["וּ", "מֵ", "חֵלְבֵ"]
                hw["prefix_morphs"] = ["CONJ", "PREP", "SUBS.M.PL.C"]
                hw["prefix_es"] = ["y", "de", "grosura"]
                hw["he_form"] = "הֶן"
                hw["strongs"] = "H2459"
                hw["he_morph"] = "PRS.P3.F.PL"
                _set_es_patch(hw, "de ellas", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "MNXT/W":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "מִנְחָת"
                hw["strongs"] = "H4503"
                hw["he_morph"] = "SUBS.F.SG.C"
                _set_es_patch(hw, "ofrenda", respect_user=respect_user_gloss)
                _attach_prs_suffix(hw, "וֹ", "PRS.P3.M.SG", "su")
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "PN/YK":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "פָּנֶיךָ"
                hw["strongs"] = "H6440"
                hw["he_morph"] = "SUBS.BOTH.PL.C"
                _set_es_patch(hw, "tu rostro", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "W/)L/YK":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "אֵלֶיךָ"
                hw["strongs"] = "H413"
                hw["he_morph"] = "CONJ+PREP+PRS.P2.M.SG"
                _set_es_patch(hw, "y hacia ti", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "T$WQT/W" and vrs == 7:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "תְּשׁוּקָתוֹ"
                hw["strongs"] = "H8669"
                hw["he_morph"] = "SUBS.F.SG.C"
                _set_es_patch(hw, "su deseo", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "W/)TH" and vrs == 7:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "אַתָּה"
                hw["strongs"] = "H859"
                hw["he_morph"] = "PRON.PERS.P2.M.SG"
                _set_es_patch(hw, "tú", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == ")L/Y":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "אֵלַי"
                hw["he_morph"] = "PREP+PRS.P1.COMMON.SG"
                hw["strongs"] = "H413"
                _set_es_patch(hw, "hacia mí", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "M/YD/K":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["מִ"]
                hw["prefix_morphs"] = ["PREP"]
                hw["prefix_es"] = ["de"]
                hw["he_form"] = "יָדְךָ"
                hw["strongs"] = "H3027"
                hw["he_morph"] = "SUBS.BOTH.SG.C"
                _set_es_patch(hw, "tu mano", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "W/M/PN/YK":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["וּ", "מִ"]
                hw["prefix_morphs"] = ["CONJ", "PREP"]
                hw["prefix_es"] = ["y", "de"]
                hw["he_form"] = "פָּנֶיךָ"
                hw["strongs"] = "H6440"
                hw["he_morph"] = "SUBS.BOTH.PL.C"
                _set_es_patch(hw, "tu rostro", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "MC)/Y" and vrs == 14:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "מֹצְאִי"
                hw["strongs"] = "H4672"
                hw["he_morph"] = "VERBO.QAL.PTCA.M.SG.C"
                _set_es_patch(hw, "me halle", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "YHRG/NY":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "יַהַרְגֵנִי"
                hw["strongs"] = "H2026"
                hw["he_morph"] = "VERBO.QAL.IMPF.P3.M.SG"
                _set_es_patch(hw, "me matará", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "MC)/W" and vrs == 15:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "מֹצְאוֹ"
                hw["strongs"] = "H4672"
                hw["he_morph"] = "VERBO.QAL.PTCA.M.SG.C"
                _set_es_patch(hw, "lo halle", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "L/KN" and vrs == 15:
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["לָ"]
                hw["prefix_morphs"] = ["PREP"]
                hw["prefix_es"] = ["por"]
                hw["he_form"] = "כֵּן"
                hw["strongs"] = "H3651"
                hw["he_morph"] = "ADV"
                _set_es_patch(hw, "tanto", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == ")WT" and vrs == 15:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "אוֹת"
                hw["strongs"] = "H226"
                hw["he_morph"] = "SUBS.BOTH.SG.A"
                _set_es_patch(hw, "señal", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "L/N$/YW":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["לְ"]
                hw["prefix_morphs"] = ["PREP"]
                hw["prefix_es"] = ["a"]
                hw["he_form"] = "נָשָׁיו"
                hw["strongs"] = "H802"
                hw["he_morph"] = "SUBS.F.PL.C"
                _set_es_patch(hw, "sus mujeres", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "QWL/Y":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "קוֹלִי"
                hw["strongs"] = "H6963"
                hw["he_morph"] = "SUBS.M.SG.C"
                _set_es_patch(hw, "mi voz", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == ")MRT/Y":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "אִמְרָתִי"
                hw["strongs"] = "H565"
                hw["he_morph"] = "SUBS.F.SG.C"
                _set_es_patch(hw, "mi dicho", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "L/PC(/Y":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["לְ"]
                hw["prefix_morphs"] = ["PREP"]
                hw["prefix_es"] = ["por"]
                hw["he_form"] = "פִצְעִי"
                hw["strongs"] = "H6482"
                hw["he_morph"] = "SUBS.M.SG.C"
                _set_es_patch(hw, "mi herida", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "L/XBRT/Y":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["לְ"]
                hw["prefix_morphs"] = ["PREP"]
                hw["prefix_es"] = ["por"]
                hw["he_form"] = "חַבֻּרָתִי"
                hw["strongs"] = "H2266"
                hw["he_morph"] = "SUBS.F.SG.C"
                _set_es_patch(hw, "mi contusión", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "HBL":
                if not (hw.get("he_form") or "").strip():
                    hw["he_form"] = "הֶבֶל"
                hw["strongs"] = "H1893"
                hw["he_morph"] = "NPROP"
                if (hw.get("es") or "").strip().lower() in ("salgamos", ""):
                    _set_es_patch(hw, "Abel", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "QYN":
                if vrs == 22 and not _strip_niqqud(he):
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "תּוּבַל קַיִן"
                    hw["strongs"] = "H8422"
                    hw["he_morph"] = "NPROP"
                    _set_es_patch(hw, "Tubal-Caín", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"
                elif not hw.get("strongs"):
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "קַיִן"
                    hw["strongs"] = "H7014"
                    hw["he_morph"] = "NPROP"
                    if not (hw.get("es") or "").strip():
                        _set_es_patch(hw, "Caín", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

            elif raw == "HW)" and vrs == 22:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "הִוא"
                hw["strongs"] = "H1931"
                hw["he_morph"] = "PRON.PERS.P3.F.SG"
                _set_es_patch(hw, "ella", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "YLDH" and vrs == 22:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "יָלְדָה"
                hw["strongs"] = "H3205"
                hw["he_morph"] = "VERBO.QAL.PERF.P3.F.SG"
                _set_es_patch(hw, "dio a luz", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "TWBL" and vrs == 22:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "תּוּבַל"
                hw["strongs"] = "H8422"
                hw["he_morph"] = "NPROP"
                if (hw.get("es") or "").strip().lower() in ("", "toda"):
                    _set_es_patch(hw, "Tubal", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == ")XY/K":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "אָחִיךָ"
                hw["strongs"] = "H251"
                hw["he_morph"] = "SUBS.M.SG.C"
                _set_es_patch(hw, "tu hermano", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == ")X/Y" and vrs == 9:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "אָחִי"
                hw["strongs"] = "H251"
                hw["he_morph"] = "SUBS.M.SG.C"
                _set_es_patch(hw, "mi hermano", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "PY/H":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "פִּיהָ"
                hw["strongs"] = "H6310"
                hw["he_morph"] = "SUBS.M.SG.C"
                _set_es_patch(hw, "su boca", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "KX/H":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "כֹחָהּ"
                hw["strongs"] = "H3581"
                hw["he_morph"] = "SUBS.M.SG.C"
                _set_es_patch(hw, "su fuerza", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "(WN/Y" and vrs == 13:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "עֲוֺנִי"
                hw["strongs"] = "H5771"
                hw["he_morph"] = "SUBS.M.SG.C"
                _set_es_patch(hw, "mi iniquidad", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "M/N&)" and vrs == 13:
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["מִ"]
                hw["prefix_morphs"] = ["PREP"]
                hw["prefix_es"] = ["de"]
                hw["he_form"] = "נְּשֹׂא"
                hw["strongs"] = "H5375"
                hw["he_morph"] = "VERBO.QAL.INFC"
                _set_es_patch(hw, "llevar", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "H/LW)":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["הֲ"]
                hw["prefix_morphs"] = ["PART.INTERR"]
                hw["prefix_es"] = ["¿"]
                hw["he_form"] = "לוֹא"
                hw["strongs"] = "H3808"
                hw["he_morph"] = "NEG"
                _set_es_patch(hw, "no", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "L/K" and vrs in (6, 12) and _strip_niqqud(he) in ("ך", "ךְ", ""):
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = ""
                hw["he_morph"] = ""
                hw["strongs"] = ""
                hw["es"] = ""
                hw["es_source"] = "patch_meta"

            elif raw == "L/W" and vrs in (15, 19):
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = ""
                hw["he_morph"] = ""
                hw["strongs"] = ""
                hw["es"] = ""
                hw["es_source"] = "patch_meta"

            elif raw == "L/BLTY" and vrs == 15:
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["לְ"]
                hw["prefix_morphs"] = ["PREP"]
                hw["prefix_es"] = ["para"]
                hw["he_form"] = "בִלְתִּי"
                hw["strongs"] = "H1115"
                hw["he_morph"] = "CONJ"
                _set_es_patch(hw, "que no", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "BN/W":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "בְּנוֹ"
                hw["strongs"] = "H1121"
                hw["he_morph"] = "SUBS.M.SG.C"
                _set_es_patch(hw, "su hijo", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == ")BY":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "אֲבִי"
                hw["strongs"] = "H1"
                hw["he_morph"] = "SUBS.M.SG.C"
                _set_es_patch(hw, "padre", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "PN/YW":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "פָּנָיו"
                hw["strongs"] = "H6440"
                hw["he_morph"] = "SUBS.BOTH.PL.C"
                _set_es_patch(hw, "su semblante", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "$M/W" and vrs == 25:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "שְׁמ"
                hw["strongs"] = "H8034"
                hw["he_morph"] = "SUBS.M.SG.C"
                _set_es_patch(hw, "nombre", respect_user=respect_user_gloss)
                _attach_prs_suffix(hw, "וֹ", "PRS.P3.M.SG", "su")
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "XWH" and vrs == 25:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = ""
                hw["he_morph"] = ""
                hw["strongs"] = ""
                hw["es"] = ""
                hw["es_source"] = "patch_meta"

            elif raw == "W/TLD" and vrs == 25:
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["וַ"]
                hw["prefix_morphs"] = ["CONJ"]
                hw["prefix_es"] = ["y"]
                hw["he_form"] = "תֵּלֶד"
                hw["strongs"] = "H3205"
                hw["he_morph"] = "VERBO.QAL.WAYYIQT.P3.F.SG"
                _set_es_patch(hw, "dio a luz", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "L/Y" and vrs == 25:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = ""
                hw["he_morph"] = ""
                hw["strongs"] = ""
                hw["es"] = ""
                hw["es_source"] = "patch_meta"

            elif raw == "HRG/W" and vrs == 25:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "הֲרָג"
                hw["strongs"] = "H2026"
                hw["he_morph"] = "VERBO.QAL.PERF.P3.M.SG"
                _set_es_patch(hw, "mató", respect_user=respect_user_gloss)
                _attach_prs_suffix(hw, "וֹ", "PRS.P3.M.SG", "lo")
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "(WD" and vrs == 25:
                hw["he_form"] = "עוֹד"
                hw["he_morph"] = "ADV"
                hw["strongs"] = "H5750"
                _set_es_patch(hw, "aún", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "KY" and vrs == 25:
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    es = (hw.get("es") or "").strip().lower()
                    if es in ("y", ""):
                        _set_es_patch(hw, "porque", respect_user=respect_user_gloss)

            elif raw == "GDWL" and vrs == 13:
                hw["he_form"] = "גָּדוֹל"
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "H/)XT" and vrs == 19:
                hw["prefix_es"] = ["la"]
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "H/$NYT" and vrs == 19:
                hw["prefix_es"] = ["la"]
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == ".(x":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = ""
                hw["he_morph"] = ""
                hw["strongs"] = ""
                hw["es"] = ""
                hw["es_source"] = "patch_meta"

    for p in verse.get("pairs", []):
        if p.get("kind") == "heb_omit" and not (p.get("es_gloss") or "").strip():
            p["es_gloss"] = "omisión textual"

    # Quitar duplicados / meta huérfanos tras parches por raw
    if vrs == 15:
        for p in verse.get("pairs", []):
            hws = p.get("he_words") or []
            if len(hws) >= 2 and hws[0].get("raw") == "L/KN" and hws[1].get("raw") == "KN":
                p["he_words"] = [hws[0]]
    if vrs == 25:
        _fix_gen4_v25(verse, respect_user_gloss=respect_user_gloss)
        for p in verse.get("pairs", []):
            hws = p.get("he_words") or []
            if len(hws) >= 2 and hws[0].get("raw") == ")T" and hws[1].get("raw") == "XWH":
                if hws[1].get("es_source") == "patch_meta":
                    p["he_words"] = [hws[0]]

    for p in verse.get("pairs", []):
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if not (
                hw.get("es_source") == "patch_meta"
                and not _strip_niqqud(hw.get("he_form") or "")
            )
        ]

    _sanitize_catss_pairs(verse)

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _merge_prs_reading_gloss(hw)


# Glosas numéricas canónicas — cap. 5 (genealogías); clave = hebreo sin niqqud.
_GEN5_NUM_ES: dict[str, str] = {
    "שלש": "tres", "שלשים": "treinta",
    "ארבע": "cuatro", "ארבעים": "cuarenta",
    "חמש": "cinco", "חמשים": "cincuenta",
    "שש": "seis", "ששים": "sesenta", "שיש": "sesenta",
    "שבע": "siete", "שבעים": "setenta", "שב": "siete",
    "שמנה": "ocho", "שמנ": "ocho", "שמונ": "ocho", "שמונים": "ochenta",
    "תשע": "nueve", "תשעים": "noventa",
    "עשר": "diez", "עשרה": "diez",
    "שתים": "dos", "שנים": "dos",
    "מאת": "ciento", "מאות": "cientos",
}

# Unidad + מאות → forma compuesta española (ochocientos, novecientos…).
_GEN5_HUNDRED_ES: dict[str, str] = {
    "תשע": "novecientos", "שמנה": "ochocientos", "שמנ": "ochocientos",
    "שמונ": "ochocientos", "שבע": "setecientos", "שב": "setecientos",
    "שש": "seiscientos", "חמש": "quinientos", "ארבע": "cuatrocientos",
    "שלש": "trescientos", "שלשים": "trescientos",
    "שבעים": "setecientos", "תשעים": "novecientos",
}


def _gen5_he_key(hw: dict) -> str:
    he = (hw.get("he_form") or hw.get("stem_unicode") or "")
    he = re.sub(r"[\u0591-\u05C7\u05BC\u05C1\u05C2\u05BD]", "", he)
    return he.replace("־", "").replace("-", "").strip()


def _is_gen5_hundreds_stem(hw: dict) -> bool:
    """True solo para מאות (plural); מאת construct no forma centena compuesta."""
    return _gen5_he_key(hw) == "מאות"


def _fix_gen5_numeric_glosses(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Corrige sangrado SpaRV en fórmulas de edad (cap. 5)."""
    for p in verse.get("pairs", []):
        hws = p.get("he_words") or []
        for i, hw in enumerate(hws):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            key = _gen5_he_key(hw)
            morph = (hw.get("he_morph") or "")
            es = (hw.get("es") or "").strip()

            if key in _GEN5_NUM_ES and es in ("ciento", "años", ""):
                _set_es_patch(hw, _GEN5_NUM_ES[key], respect_user=respect_user_gloss)
                if key in ("מאת", "מאות"):
                    hw["strongs"] = "H3967"
                elif not hw.get("strongs"):
                    hw["strongs"] = "H8141"

            elif morph == "SUBS.F.SG.A" and key == "שנה":
                _set_es_patch(hw, "años", respect_user=respect_user_gloss)
                hw["strongs"] = "H8141"
            elif morph == "SUBS.F.PL.A" and key.startswith("שנ"):
                _set_es_patch(hw, "años", respect_user=respect_user_gloss)
                hw["strongs"] = "H8141"

            elif key == "מאת" and es in ("ciento", "años", ""):
                _set_es_patch(hw, "ciento", respect_user=respect_user_gloss)
                hw["strongs"] = "H3967"
                hw["he_morph"] = "CBSC"
            elif key == "מאות" and es in ("ciento", "años", ""):
                _set_es_patch(hw, "cientos", respect_user=respect_user_gloss)
                hw["strongs"] = "H3967"
                hw["he_morph"] = "NUM.CARD.BOTH.PL.A"


def _gen5_shana_hw() -> dict:
    return {
        "raw": "$NH",
        "he_form": "שָׁנָה",
        "strongs": "H8141",
        "he_morph": "SUBS.F.SG.A",
        "es": "años",
        "es_source": "patch",
    }


def _gen5_min_pair(hw: dict) -> dict:
    return {"he_words": [hw], "kind": "word"}


def _gen5_ensure_w_prefix(hw: dict) -> None:
    """Tokens W/* deben llevar ו en prefix_forms, no glosa compuesta en prefix_es."""
    raw = hw.get("raw") or ""
    if not raw.startswith("W/") or not (hw.get("he_form") or "").strip():
        return
    if not (hw.get("prefix_forms") or []):
        hw["prefix_forms"] = ["וַ"]
        hw["prefix_morphs"] = ["CONJ"]
        hw["prefix_es"] = ["y"]
    elif hw.get("prefix_es") and not any(_gen5_he_key({"he_form": x}) for x in (hw.get("prefix_forms") or [])):
        hw["prefix_forms"] = ["וַ"]
        hw["prefix_morphs"] = ["CONJ"]
        hw["prefix_es"] = ["y"]


def _gen5_repair_shana_pair(p: dict) -> None:
    p["he_words"] = [_gen5_shana_hw()]


def _gen5_pair_has_maot(p: dict) -> bool:
    return any(_gen5_he_key(h) == "מאות" for h in p.get("he_words") or [])


def _gen5_is_shana_hw(hw: dict) -> bool:
    return _gen5_he_key(hw) == "שנה" and (hw.get("he_morph") or "").startswith("SUBS.F.SG")


def _fix_gen5_w_prefixes(verse: dict) -> None:
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            _gen5_ensure_w_prefix(hw)


def _fix_gen5_after_maot(verse: dict) -> None:
    """Tras מֵאוֹת debe ir שָׁנָה antes de וַיָּמֹת / וַיּוֹלֵד."""
    pairs = verse.get("pairs", [])
    i = 0
    while i < len(pairs):
        if not _gen5_pair_has_maot(pairs[i]):
            i += 1
            continue
        ni = i + 1
        if ni >= len(pairs):
            break
        np = pairs[ni]
        nhws = np.get("he_words") or []
        if not nhws:
            np["he_words"] = [_gen5_shana_hw()]
            i = ni + 1
            continue
        hw0 = nhws[0]
        raw0 = hw0.get("raw") or ""
        if _gen5_is_shana_hw(hw0):
            i = ni + 1
            continue
        if raw0 in ("W/YMT", "W/YWLD"):
            pairs.insert(ni, _gen5_min_pair(_gen5_shana_hw()))
            i = ni + 2
            continue
        _gen5_repair_shana_pair(np)
        i = ni + 1


def _fix_gen5_empty_pairs(verse: dict) -> None:
    """Elimina pares vacíos; los útiles ya fueron rellenados."""
    verse["pairs"] = [p for p in verse.get("pairs", []) if p.get("he_words")]


def _fix_gen5_v6(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """5:6 — חָמֵשׁ שָׁנִים וּמְאַת שָׁנָה וַיּוֹלֶד אֶת־אֱנוֹשׁ."""
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if hw.get("raw") == "$NYM":
                hw["he_form"] = "שָׁנִים"
                hw["he_morph"] = "SUBS.F.PL.A"
                hw["strongs"] = "H8141"
                _set_es_patch(hw, "años", respect_user=respect_user_gloss)
            elif hw.get("raw") == "W/M)T":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["וּ"]
                hw["prefix_morphs"] = ["CONJ"]
                hw["prefix_es"] = ["y"]
                hw["he_form"] = "מְאַת"
                hw["strongs"] = "H3967"
                hw["he_morph"] = "CBSC"
                _set_es_patch(hw, "ciento", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
            elif hw.get("raw") == "W/YWLD":
                _gen5_ensure_w_prefix(hw)
    for p in verse.get("pairs", []):
        hws = p.get("he_words") or []
        if len(hws) == 1 and hws[0].get("raw") == "$NH" and _gen5_he_key(hws[0]).startswith("אנ"):
            p["he_words"] = []


def _fix_gen5_v18(verse: dict, *, respect_user_gloss: bool = False) -> None:
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if hw.get("raw") == "$NH" and _gen5_he_key(hw).startswith("חנ"):
                _gen5_repair_shana_pair(p)
                break


def _fix_gen5_v23(verse: dict) -> None:
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if hw.get("raw") == "W/$L$":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["וּ"]
                hw["prefix_morphs"] = ["CONJ"]
                hw["prefix_es"] = ["y"]
                hw["he_form"] = "שְׁלֹשׁ"
                hw["strongs"] = "H7969"
                hw["he_morph"] = "CFSA"
                _set_es_patch(hw, "tres", respect_user=False)
    _fix_gen5_after_maot(verse)


def _gen5_preserve_fused_ot(hw: dict, *, respect_user_gloss: bool = False) -> None:
    """Mantiene אֹתוֹ / אֹתָם como un solo token (no partir en את + sufijo)."""
    raw = hw.get("raw") or ""
    fused = {
        ")T/W": ("אֹתוֹ", "PART.OBJ.DIR+PRS.P3.M.SG", "lo"),
        ")T/M": ("אֹתָם", "PART.OBJ.DIR+PRS.P3.M.PL", "los"),
        ")T/H": ("אֹתָהּ", "PART.OBJ.DIR+PRS.P3.F.SG", "la"),
        ")T/NW": ("אֹתָנוּ", "PART.OBJ.DIR+PRS.P1.COMMON.PL", "nos"),
    }
    if raw not in fused:
        return
    he, morph, es = fused[raw]
    _clear_hw_prefix_slots(hw)
    hw["he_form"] = he
    hw["he_morph"] = morph
    _set_es_patch(hw, es, respect_user=respect_user_gloss)
    hw.pop("prs_suffix", None)
    if not (respect_user_gloss and _has_user_gloss(hw)):
        hw["es_source"] = "patch"


def _fix_gen5_v24(verse: dict, *, respect_user_gloss: bool = False) -> None:
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if hw.get("raw") == "W/)YN/NW":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["וְ"]
                hw["prefix_morphs"] = ["CONJ"]
                hw["prefix_es"] = ["y"]
                hw["he_form"] = "אֵינֶ"
                hw["strongs"] = "H369"
                hw["he_morph"] = "NEG"
                _set_es_patch(hw, "no", respect_user=respect_user_gloss)
                _attach_prs_suffix(hw, "נּוּ", "PRS.P3.M.SG", "estaba")
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"
            elif hw.get("raw") == ")T/W":
                _gen5_preserve_fused_ot(hw, respect_user_gloss=respect_user_gloss)


def _fix_gen5_v27(verse: dict) -> None:
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if hw.get("raw") == "W/T$(" and _gen5_he_key(hw) in ("ו", ""):
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["וּ"]
                hw["prefix_morphs"] = ["CONJ"]
                hw["prefix_es"] = ["y"]
                hw["he_form"] = "תְשַׁע"
                hw["strongs"] = "H8672"
                hw["he_morph"] = "CFSA"
                _set_es_patch(hw, "nueve", respect_user=False)
    _fix_gen5_after_maot(verse)


def _fix_gen5_v26(verse: dict) -> None:
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if hw.get("raw") == "W/$B(" and _gen5_he_key(hw) != "ו":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["וּ"]
                hw["prefix_morphs"] = ["CONJ"]
                hw["prefix_es"] = ["y"]
                hw["he_form"] = "שְׁבַע"
                hw["strongs"] = "H7651"
                hw["he_morph"] = "CFSA"
                _set_es_patch(hw, "siete", respect_user=False)


def _fix_gen5_v30(verse: dict) -> None:
    for p in verse.get("pairs", []):
        hws = p.get("he_words") or []
        if len(hws) >= 2 and hws[0].get("raw") == "W/XM$":
            h0, h1 = hws[0], hws[1]
            if _gen5_he_key(h0) == "ו":
                _clear_hw_prefix_slots(h0)
                h0["prefix_forms"] = ["וַ"]
                h0["prefix_morphs"] = ["CONJ"]
                h0["prefix_es"] = ["y"]
                h0["he_form"] = "חֲמֵשׁ"
                h0["strongs"] = "H2568"
                h0["he_morph"] = "CFSA"
                _set_es_patch(h0, "cinco", respect_user=False)
                h1["he_form"] = "מֵאֹת"
                h1["strongs"] = "H3967"
                h1["he_morph"] = "NUM.CARD.BOTH.PL.A"
                h1["raw"] = "M)WT"
        for hw in hws:
            if hw.get("raw") == "$NH" and _gen5_he_key(hw).startswith("בנ"):
                _gen5_repair_shana_pair(p)
                break
    _fix_gen5_after_maot(verse)


def _fix_gen5_v31(verse: dict) -> None:
    for p in verse.get("pairs", []):
        hws = p.get("he_words") or []
        if len(hws) >= 2 and hws[0].get("raw") == "W/$B(" and _gen5_he_key(hws[0]) == "ו":
            _clear_hw_prefix_slots(hws[0])
            hws[0]["prefix_forms"] = ["וּ"]
            hws[0]["prefix_morphs"] = ["CONJ"]
            hws[0]["prefix_es"] = ["y"]
            hws[0]["he_form"] = "שְׁבַע"
            hws[0]["strongs"] = "H7651"
            hws[0]["he_morph"] = "CFSA"
            _set_es_patch(hws[0], "siete", respect_user=False)
    _fix_gen5_after_maot(verse)
    _fix_gen5_w_prefixes(verse)


def _fix_gen5_v32(verse: dict) -> None:
    pairs = verse.get("pairs", [])
    for pi, p in enumerate(pairs):
        if _gen5_pair_has_maot(p):
            ni = pi + 1
            if ni < len(pairs):
                np = pairs[ni]
                if not (np.get("he_words") or []):
                    np["he_words"] = [_gen5_shana_hw()]
                elif not _gen5_is_shana_hw((np.get("he_words") or [{}])[0]):
                    pairs.insert(ni, _gen5_min_pair(_gen5_shana_hw()))
            break
    _fix_gen5_empty_pairs(verse)


def _fix_gen5_after_mat(verse: dict) -> None:
    """Tras מְאַת (CBSC) suele ir שָׁנָה antes del verbo."""
    pairs = verse.get("pairs", [])
    for pi, p in enumerate(pairs):
        hws = p.get("he_words") or []
        if not any(_gen5_he_key(h) == "מאת" for h in hws):
            continue
        ni = pi + 1
        if ni >= len(pairs):
            continue
        np = pairs[ni]
        nhws = np.get("he_words") or []
        if not nhws:
            np["he_words"] = [_gen5_shana_hw()]
        elif nhws[0].get("raw") in ("W/YWLD", "W/YMT") and not _gen5_is_shana_hw(nhws[0]):
            pairs.insert(ni, _gen5_min_pair(_gen5_shana_hw()))


def _fix_gen5_structure(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Post-proceso: orden hebreo, שנה faltantes, prefijos W-, pares vacíos."""
    vrs = verse.get("verse", 0)
    _fix_gen5_w_prefixes(verse)
    if vrs == 6:
        _fix_gen5_v6(verse, respect_user_gloss=respect_user_gloss)
    elif vrs == 18:
        _fix_gen5_v18(verse, respect_user_gloss=respect_user_gloss)
    elif vrs == 23:
        _fix_gen5_v23(verse)
    elif vrs == 24:
        _fix_gen5_v24(verse, respect_user_gloss=respect_user_gloss)
    elif vrs == 27:
        _fix_gen5_v27(verse)
    elif vrs == 26:
        _fix_gen5_v26(verse)
    elif vrs == 30:
        _fix_gen5_v30(verse)
    elif vrs == 31:
        _fix_gen5_v31(verse)
    elif vrs == 32:
        _fix_gen5_v32(verse)
    else:
        _fix_gen5_after_maot(verse)
    _fix_gen5_after_mat(verse)
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            _gen5_preserve_fused_ot(hw, respect_user_gloss=respect_user_gloss)
            raw = hw.get("raw") or ""
            if raw.startswith("W/") and not (hw.get("prefix_forms") or []):
                hek = _gen5_he_key(hw)
                if hek and hek not in ("ו", "את") and not hek.startswith("י"):
                    _clear_hw_prefix_slots(hw)
                    hw["prefix_forms"] = ["וּ"]
                    hw["prefix_morphs"] = ["CONJ"]
                    hw["prefix_es"] = ["y"]
            if hw.get("raw") == "W/YQR)":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["וַ"]
                hw["prefix_morphs"] = ["CONJ"]
                hw["prefix_es"] = ["y"]
                if not (hw.get("he_form") or "").strip():
                    hw["he_form"] = "יִּקְרָא"
                hw.pop("prs_suffix", None)
            elif hw.get("raw") == "$NH" and _gen5_he_key(hw) in ("בנים", "בנות", "ו"):
                _gen5_repair_shana_pair(p)
    _fix_gen5_empty_pairs(verse)


def _fix_gen5_v3(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """5:3 — quitar duplicado שֵׁת si p8 ya tiene el nombre."""
    seen_set = False
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if hw.get("raw") == "$T" and _gen5_he_key(hw) == "שת":
                if seen_set:
                    p["he_words"] = [x for x in p["he_words"] if x is not hw]
                else:
                    seen_set = True
                    _set_es_patch(hw, "Set", respect_user=respect_user_gloss)
                    hw["strongs"] = "H8352"
                    hw["he_morph"] = "NPROP"


def _fix_gen5_v5(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """5:5 — restaurar וּשְׁלֹשִׁים שָׁנָה (token W/$L$YM + par vacío)."""
    for pi, p in enumerate(verse.get("pairs", [])):
        for hw in p.get("he_words", []):
            if hw.get("raw") != "W/$L$YM":
                continue
            _clear_hw_prefix_slots(hw)
            hw["prefix_forms"] = ["וּ"]
            hw["prefix_morphs"] = ["CONJ"]
            hw["prefix_es"] = ["y"]
            hw["he_form"] = "שְׁלֹשִׁים"
            hw["strongs"] = "H7969"
            hw["he_morph"] = "CBPA"
            _set_es_patch(hw, "treinta", respect_user=respect_user_gloss)
            hw.pop("prs_suffix", None)
            if pi + 1 < len(verse["pairs"]):
                np = verse["pairs"][pi + 1]
                if not (np.get("he_words") or []):
                    np["he_words"] = [{
                        "raw": "$NH",
                        "he_form": "שָׁנָה",
                        "strongs": "H8141",
                        "he_morph": "SUBS.F.SG.A",
                        "es": "años",
                        "es_source": "patch",
                    }]


def _fix_gen5_v29(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """5:29 — eliminar YHWH duplicado si )RR/H ya corregido."""
    yhwh_seen = False
    for p in verse.get("pairs", []):
        hws = p.get("he_words") or []
        new_hws = []
        for hw in hws:
            if hw.get("raw") == "YHWH":
                if yhwh_seen:
                    continue
                yhwh_seen = True
            new_hws.append(hw)
        p["he_words"] = new_hws


def _patch_gen5(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Parches estructurales Génesis cap. 5 — genealogías, edades, PRS/CATSS."""
    vrs = verse.get("verse", 0)
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            raw = hw.get("raw", "")

            if raw == "HWLYD/W":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "הוֹלִיד"
                hw["strongs"] = "H3205"
                hw["he_morph"] = "VERBO.HIF.INFC"
                _set_es_patch(hw, "engendrar", respect_user=respect_user_gloss)
                _attach_prs_suffix(hw, "וֹ", "PRS.P3.M.SG", "lo")
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "B/DMWT/W":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["בִּ"]
                hw["prefix_morphs"] = ["PREP"]
                hw["prefix_es"] = ["a"]
                hw["he_form"] = "דְמוּת"
                hw["strongs"] = "H1823"
                hw["he_morph"] = "SUBS.F.SG.C"
                _set_es_patch(hw, "semejanza", respect_user=respect_user_gloss)
                _attach_prs_suffix(hw, "וֹ", "PRS.P3.M.SG", "su")
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "K/CLM/W":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["כְּ"]
                hw["prefix_morphs"] = ["PREP"]
                hw["prefix_es"] = ["como"]
                hw["he_form"] = "צַלְמ"
                hw["strongs"] = "H6754"
                hw["he_morph"] = "SUBS.M.SG.C"
                _set_es_patch(hw, "imagen", respect_user=respect_user_gloss)
                _attach_prs_suffix(hw, "וֹ", "PRS.P3.M.SG", "su")
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "W/M)T":
                he_key = _gen5_he_key(hw)
                if he_key in ("מת", "מאת") or (hw.get("he_morph") or "") == "CBSC":
                    _clear_hw_prefix_slots(hw)
                    hw["prefix_forms"] = ["וּ"]
                    hw["prefix_morphs"] = ["CONJ"]
                    hw["prefix_es"] = ["y"]
                    hw["he_form"] = "מְאַת"
                    hw["strongs"] = "H3967"
                    hw["he_morph"] = "CBSC"
                    _set_es_patch(hw, "ciento", respect_user=respect_user_gloss)
                    hw.pop("prs_suffix", None)
                elif he_key == "את":
                    _clear_hw_prefix_slots(hw)
                    hw["prefix_forms"] = ["וַ"]
                    hw["prefix_morphs"] = ["CONJ"]
                    hw["prefix_es"] = ["y"]
                    hw["he_form"] = "אֶת"
                    hw["strongs"] = "H853"
                    hw["he_morph"] = "PART.OBJ.DIR"
                    _set_es_patch(hw, "", respect_user=respect_user_gloss)
                    hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "$M/W":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "שְׁמ"
                hw["strongs"] = "H8034"
                hw["he_morph"] = "SUBS.M.SG.C"
                _set_es_patch(hw, "nombre", respect_user=respect_user_gloss)
                _attach_prs_suffix(hw, "וֹ", "PRS.P3.M.SG", "su")
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "$M/M":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "שְׁמָ"
                hw["strongs"] = "H8034"
                hw["he_morph"] = "SUBS.M.SG.C"
                _set_es_patch(hw, "su nombre", respect_user=respect_user_gloss)
                _attach_prs_suffix(hw, "ם֙", "PRS.P3.M.PL", "")
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "W/YTHLK":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["וַ"]
                hw["prefix_morphs"] = ["CONJ"]
                hw["prefix_es"] = ["y"]
                hw["he_form"] = "יִּתְהַלֵּךְ"
                hw["strongs"] = "H1980"
                hw["he_morph"] = "VERBO.HIT.WAYYIQT.P3.M.SG"
                _set_es_patch(hw, "caminó", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "W/)YN/NW" and vrs != 24:
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["וְ"]
                hw["prefix_morphs"] = ["CONJ"]
                hw["prefix_es"] = ["y"]
                hw["he_form"] = "אֵינֶ"
                hw["strongs"] = "H369"
                hw["he_morph"] = "NEG"
                _set_es_patch(hw, "no", respect_user=respect_user_gloss)
                _attach_prs_suffix(hw, "נּוּ", "PRS.P3.M.SG", "estaba")
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "YNXM/NW":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "יְנַחֲמֵ"
                hw["strongs"] = "H5162"
                hw["he_morph"] = "VERBO.PIEL.IMPF.P3.M.SG"
                _set_es_patch(hw, "consolará", respect_user=respect_user_gloss)
                _attach_prs_suffix(hw, "נוּ", "PRS.P1.COMMON.PL", "nos")
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "M/M(&/NW":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["מִ"]
                hw["prefix_morphs"] = ["PREP"]
                hw["prefix_es"] = ["de"]
                hw["he_form"] = "מַעֲשֵׂ"
                hw["strongs"] = "H4639"
                hw["he_morph"] = "SUBS.M.SG.C"
                _set_es_patch(hw, "obra", respect_user=respect_user_gloss)
                _attach_prs_suffix(hw, "נוּ", "PRS.P1.COMMON.PL", "nuestra")
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "YD/YNW":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "יָדֵי"
                hw["strongs"] = "H3027"
                hw["he_morph"] = "SUBS.BOTH.DU.C"
                _set_es_patch(hw, "manos", respect_user=respect_user_gloss)
                _attach_prs_suffix(hw, "נוּ", "PRS.P1.COMMON.PL", "nuestras")
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == ")RR/H":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "אֵרְרָ"
                hw["strongs"] = "H779"
                hw["he_morph"] = "VERBO.PIEL.PERF.P3.M.SG"
                _set_es_patch(hw, "maldijo", respect_user=respect_user_gloss)
                _attach_prs_suffix(hw, "הּ", "PRS.P3.F.SG", "la")
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "BN":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "בֵּן"
                hw["strongs"] = "H1121"
                hw["he_morph"] = "SUBS.M.SG.C"
                _set_es_patch(hw, "hijo", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "BR)/M":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "בְּרָאָ"
                hw["he_morph"] = "VERBO.QAL.PERF.P3.M.SG"
                _set_es_patch(hw, "los creó", respect_user=respect_user_gloss)
                _attach_prs_suffix(hw, "ם", "PRS.P3.M.PL", "")
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "HBR)/M":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "הִבָּרְאָ"
                hw["he_morph"] = "VERBO.NIF.INFC"
                _set_es_patch(hw, "fueron creados", respect_user=respect_user_gloss)
                _attach_prs_suffix(hw, "ם", "PRS.P3.M.PL", "")
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "W/$L$YM":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["וּ"]
                hw["prefix_morphs"] = ["CONJ"]
                hw["prefix_es"] = ["y"]
                hw["he_form"] = "שְׁלֹשִׁים"
                hw["strongs"] = "H7969"
                hw["he_morph"] = "CBPA"
                _set_es_patch(hw, "treinta", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "W/YMT":
                _gen5_ensure_w_prefix(hw)
                if (hw.get("prefix_es") or [""])[0] == "y murió":
                    hw["prefix_es"] = ["y"]

            elif raw == "W/YWLD":
                _gen5_ensure_w_prefix(hw)

            elif raw.endswith("}"):
                continue  # huérfanos CATSS — se eliminan al final

            elif raw in ("W/T$(", "W/T$(YM", "W/$MNH", "W/$$YM", "W/$MWNYM", "W/$B(YM", "(&RH"):
                he_key = _gen5_he_key(hw)
                if raw.startswith("W/"):
                    _clear_hw_prefix_slots(hw)
                    hw["prefix_forms"] = ["וּ"]
                    hw["prefix_morphs"] = ["CONJ"]
                    hw["prefix_es"] = ["y"]
                if he_key in _GEN5_NUM_ES:
                    _set_es_patch(hw, _GEN5_NUM_ES[he_key], respect_user=respect_user_gloss)
                    hw["strongs"] = "H8141" if he_key != "מאות" else "H3967"
                    morph_map = {
                        "תשע": "CFSA", "שמנ": "CFSA", "שבע": "CFSA",
                        "שמונה": "NUM.CARD.F.SG.A", "חמש": "NUM.CARD.F.SG.A",
                    }
                    if he_key in morph_map:
                        hw["he_morph"] = morph_map[he_key]
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw in ("M)WT", "T$(", "$L$YM", "XM$", "$TYM", "$B(", "(&RH", "$NYM"):
                he_key = _gen5_he_key(hw)
                if he_key in _GEN5_NUM_ES:
                    _set_es_patch(hw, _GEN5_NUM_ES[he_key], respect_user=respect_user_gloss)
                    if he_key in ("מאת", "מאות"):
                        hw["strongs"] = "H3967"
                        hw["he_morph"] = "NUM.CARD.BOTH.PL.A"
                    elif not hw.get("strongs"):
                        hw["strongs"] = "H8141"
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "$NH" and vrs == 6 and _gen5_he_key(hw).startswith("אנ"):
                hw["he_form"] = "אֱנוֹשׁ"
                hw["strongs"] = "H583"
                hw["he_morph"] = "NPROP"
                _set_es_patch(hw, "Enós", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "W/YQR)" and vrs == 3:
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["וַ"]
                hw["prefix_morphs"] = ["CONJ"]
                hw["prefix_es"] = ["y"]
                if not (hw.get("he_form") or "").strip():
                    hw["he_form"] = "יִּקְרָא"
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

    _fix_gen5_numeric_glosses(verse, respect_user_gloss=respect_user_gloss)

    if vrs == 3:
        _fix_gen5_v3(verse, respect_user_gloss=respect_user_gloss)
    elif vrs == 5:
        _fix_gen5_v5(verse, respect_user_gloss=respect_user_gloss)
    elif vrs == 29:
        _fix_gen5_v29(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if not (
                (hw.get("raw") or "").endswith("}")
                or (
                    hw.get("es_source") == "patch_meta"
                    and not _strip_niqqud(hw.get("he_form") or "")
                )
            )
        ]

    _fix_gen5_structure(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _merge_prs_reading_gloss(hw)

    _sanitize_catss_pairs(verse)


def _gen6_split_at_prs(
    hw: dict,
    *,
    stem_he: str,
    stem_morph: str,
    stem_es: str,
    suf_he: str = "",
    suf_morph: str = "",
    suf_es: str = "",
    strongs: str = "",
    prefix_forms: list | None = None,
    prefix_morphs: list | None = None,
    prefix_es: list | None = None,
    respect_user_gloss: bool = False,
) -> None:
    _clear_hw_prefix_slots(hw)
    if prefix_forms:
        hw["prefix_forms"] = prefix_forms
        hw["prefix_morphs"] = prefix_morphs or []
        hw["prefix_es"] = prefix_es or []
    hw["he_form"] = stem_he
    hw["he_morph"] = stem_morph
    if strongs:
        hw["strongs"] = strongs
    _set_es_patch(hw, stem_es, respect_user=respect_user_gloss)
    if suf_he:
        _attach_prs_suffix(hw, suf_he, suf_morph, suf_es)
    else:
        hw.pop("prs_suffix", None)
    if not (respect_user_gloss and _has_user_gloss(hw)):
        hw["es_source"] = "patch"


def _gen6_reapply_oshb_splits(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Reaplica splits OSHB tras _gen5_preserve_fused_ot (no re-fusionar את+PRS en cap. 6)."""
    vrs = verse.get("verse", 0)
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            raw = hw.get("raw", "")
            if raw == ")T/H":
                _gen6_split_at_prs(
                    hw,
                    stem_he="אֹת",
                    stem_morph="PART.OBJ.DIR",
                    stem_es="",
                    strongs="H853",
                    suf_he="הּ",
                    suf_morph="PRS.P3.F.SG",
                    suf_es="la",
                    respect_user_gloss=respect_user_gloss,
                )
            elif raw == ")T/W" and vrs == 22:
                _gen6_split_at_prs(
                    hw,
                    stem_he="אֵת",
                    stem_morph="PART.OBJ.DIR",
                    stem_es="",
                    strongs="H853",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="lo",
                    respect_user_gloss=respect_user_gloss,
                )


def _fix_gen6_oshb_align(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Alineación morfológica cap. 6 con OSHB — splits PRS, orden, pares espurios."""
    vrs = verse.get("verse", 0)

    for p in verse.get("pairs", []):
        hws = p.get("he_words") or []
        out: list[dict] = []
        for hw in hws:
            raw = hw.get("raw", "")

            if raw == "B/CD/H" and vrs == 16:
                if raw == "B/CD/H#T$YM":
                    out.append(hw)
                    continue
                has_tasim = any(
                    (h.get("raw") or "") == "B/CD/H#T$YM"
                    for h in hws
                )
                es_tasim = (hw.get("es") or "pondrás").strip()
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["בְּ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["en"],
                    stem_he="צִד",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="lado",
                    strongs="H6654",
                    suf_he="הּ",
                    suf_morph="PRS.P3.F.SG",
                    suf_es="",
                    respect_user_gloss=respect_user_gloss,
                )
                out.append(hw)
                if not has_tasim:
                    out.append({
                        "raw": "B/CD/H#T$YM",
                        "he_form": "תָּשִׂים",
                        "he_morph": "VERBO.QAL.IMPF.P2.M.SG",
                        "strongs": "H7760",
                        "es": es_tasim,
                        "es_source": "patch",
                        "prefix_forms": [],
                        "prefix_morphs": [],
                        "prefix_es": [],
                    })
                continue

            if raw == "M/KL" and vrs == 20:
                pfx = hw.get("prefix_forms") or []
                if pfx and _gen5_he_key({"he_form": pfx[0]}) == "כל":
                    _gen6_split_at_prs(
                        hw,
                        prefix_forms=["מִ"],
                        prefix_morphs=["PREP"],
                        prefix_es=["de"],
                        stem_he="כֹּל",
                        stem_morph="SUBS.M.SG.C",
                        stem_es=(hw.get("es") or "todo").strip(),
                        strongs="H3605",
                        respect_user_gloss=respect_user_gloss,
                    )

            if raw == "H/)DMH" and vrs == 20:
                pfx = hw.get("prefix_forms") or []
                if pfx and _gen5_he_key({"he_form": pfx[0]}) in ("הו", "ה"):
                    _clear_hw_prefix_slots(hw)
                    hw["prefix_forms"] = ["הָ"]
                    hw["prefix_morphs"] = ["ART"]
                    hw["prefix_es"] = ["la"]
                    hw["he_form"] = "אֲדָמָה"
                    hw["strongs"] = "H127"
                    hw["he_morph"] = "SUBS.F.SG.A"
                    _set_es_patch(hw, "tierra", respect_user=respect_user_gloss)
                    hw.pop("prs_suffix", None)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

            out.append(hw)
        p["he_words"] = out

    # Pares / tokens espurios vs OSHB
    drop_raws: set[str] = set()
    if vrs == 14:
        drop_raws.add("L/K")
    if vrs == 16:
        drop_raws.add("T&YM")
    if vrs == 21:
        drop_raws.update({"L/K", "W/L/HM"})

    if drop_raws:
        for p in verse.get("pairs", []):
            p["he_words"] = [
                hw for hw in p.get("he_words", [])
                if hw.get("raw") not in drop_raws
            ]

    if vrs == 15:
        for p in verse.get("pairs", []):
            p["he_words"] = [
                hw for hw in p.get("he_words", [])
                if not (hw.get("raw") == "H/TBH" and _gen5_he_key(hw) == "אמה")
            ]

    if vrs == 17:
        for p in verse.get("pairs", []):
            p["he_words"] = [
                hw for hw in p.get("he_words", [])
                if hw.get("raw") != "B/W"
            ]

    if vrs == 6:
        for p in verse.get("pairs", []):
            for hw in p.get("he_words", []):
                if hw.get("raw") == "LB/W":
                    _gen6_split_at_prs(
                        hw,
                        stem_he="לֵב",
                        stem_morph="SUBS.M.SG.C",
                        stem_es="corazón",
                        strongs="H3820",
                        suf_he="וֹ",
                        suf_morph="PRS.P3.M.SG",
                        suf_es="su",
                        respect_user_gloss=respect_user_gloss,
                    )

    if vrs == 12:
        for p in verse.get("pairs", []):
            for hw in p.get("he_words", []):
                if hw.get("raw") == "DRK/W":
                    _gen6_split_at_prs(
                        hw,
                        stem_he="דַּרְכּ",
                        stem_morph="SUBS.BOTH.SG.C",
                        stem_es="camino",
                        strongs="H1870",
                        suf_he="וֹ",
                        suf_morph="PRS.P3.M.SG",
                        suf_es="su",
                        respect_user_gloss=respect_user_gloss,
                    )

    if vrs == 16:
        for p in verse.get("pairs", []):
            seen_tasim = False
            cleaned: list[dict] = []
            for hw in p.get("he_words", []):
                if hw.get("raw") == "B/CD/H#T$YM":
                    if seen_tasim:
                        continue
                    seen_tasim = True
                cleaned.append(hw)
            p["he_words"] = cleaned

    if vrs == 16:
        verse["pairs"] = [
            p for p in verse.get("pairs", [])
            if not (
                len(p.get("he_words") or []) == 1
                and (p["he_words"][0].get("raw") or "") == "T&YM"
            )
        ]

    verse["pairs"] = [
        p for p in verse.get("pairs", [])
        if p.get("he_words")
        or (p.get("gr_unicode") or "").strip()
        or p.get("kind") == "heb_omit"
    ]


def _patch_gen6(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Parches estructurales Génesis cap. 6 — PRS/CATSS, arca, diluvio."""
    vrs = verse.get("verse", 0)
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            raw = hw.get("raw", "")

            if raw == "RWX/Y":
                _gen6_split_at_prs(
                    hw,
                    stem_he="רוּחַ",
                    stem_morph="SUBS.BOTH.SG.C",
                    stem_es="espíritu",
                    strongs="H7307",
                    suf_he="י",
                    suf_morph="PRS.P1.COMMON.SG",
                    suf_es="mi",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "B/$/GM":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["בְּ", "שַׁ"]
                hw["prefix_morphs"] = ["PREP", "REL"]
                hw["prefix_es"] = ["en", "—"]
                hw["he_form"] = "גַּם"
                hw["strongs"] = "H1571"
                hw["he_morph"] = "ADV"
                _set_es_patch(hw, "también", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "H/$MYM":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["הַ"]
                hw["prefix_morphs"] = ["ART"]
                hw["prefix_es"] = ["los"]
                hw["he_form"] = "שָּׁמַיִם"
                hw["strongs"] = "H8064"
                hw["he_morph"] = "SUBS.M.PL.A"
                _set_es_patch(hw, "cielos", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "W/PTX":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["וּ"]
                hw["prefix_morphs"] = ["CONJ"]
                hw["prefix_es"] = ["y"]
                hw["he_form"] = "פֶּתַח"
                hw["strongs"] = "H6607"
                hw["he_morph"] = "SUBS.M.SG.C"
                _set_es_patch(hw, "puerta", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "M/PN/YHM":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["מִ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["de"],
                    stem_he="פְּנֵי",
                    stem_morph="SUBS.BOTH.PL.C",
                    stem_es="delante",
                    strongs="H6440",
                    suf_he="הֶם",
                    suf_morph="PRS.P3.M.PL",
                    suf_es="ellos",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "W/HN/NY":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["וְ"],
                    prefix_morphs=["CONJ"],
                    prefix_es=["y"],
                    stem_he="הִנְ",
                    stem_morph="INTJ",
                    stem_es="he aquí",
                    suf_he="נִי",
                    suf_morph="PRS.P1.COMMON.SG",
                    suf_es="estoy",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "HN/NY":
                _gen6_split_at_prs(
                    hw,
                    stem_he="הִנְנִ",
                    stem_morph="INTJ",
                    stem_es="he aquí",
                    suf_he="י",
                    suf_morph="PRS.P1.COMMON.SG",
                    suf_es="",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "RM&":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "רֶמֶשׂ"
                hw["strongs"] = "H7431"
                hw["he_morph"] = "SUBS.M.SG.A"
                _set_es_patch(hw, "reptil", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "W/(D" and vrs == 7:
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["וְ"]
                hw["prefix_morphs"] = ["CONJ"]
                hw["prefix_es"] = ["y"]
                hw["he_form"] = "עַד"
                hw["strongs"] = "H5704"
                hw["he_morph"] = "PREP"
                _set_es_patch(hw, "hasta", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == ")T/H":
                _gen6_split_at_prs(
                    hw,
                    stem_he="אֹת",
                    stem_morph="PART.OBJ.DIR",
                    stem_es="",
                    strongs="H853",
                    suf_he="הּ",
                    suf_morph="PRS.P3.F.SG",
                    suf_es="la",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "B/DRT/YW":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["בְּ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["en"],
                    stem_he="דֹרֹתִי",
                    stem_morph="SUBS.M.PL.C",
                    stem_es="generaciones",
                    strongs="H1755",
                    suf_he="ו",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "M)H" and vrs == 3:
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["וְ"]
                hw["prefix_morphs"] = ["CONJ"]
                hw["prefix_es"] = ["y"]
                hw["he_form"] = "מֵאָה"
                hw["strongs"] = "H3967"
                hw["he_morph"] = "NUM.CARD.BOTH.SG.A"
                _set_es_patch(hw, "ciento", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "YM/YW":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "יָמָי"
                hw["strongs"] = "H3117"
                hw["he_morph"] = "SUBS.M.PL.C"
                _set_es_patch(hw, "mis días", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "(&YT/M":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "עֲשִׂיתִ"
                hw["strongs"] = "H6213"
                hw["he_morph"] = "VERBO.QAL.PERF.P1.COMMON.SG"
                _set_es_patch(hw, "hice", respect_user=respect_user_gloss)
                _attach_prs_suffix(hw, "ם", "PRS.P3.M.PL", "los")
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "L/NX" and vrs == 13:
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["לְ"]
                hw["prefix_morphs"] = ["PREP"]
                hw["prefix_es"] = ["a"]
                hw["he_form"] = "נֹחַ"
                hw["strongs"] = "H5146"
                hw["he_morph"] = "NPROP"
                _set_es_patch(hw, "Noé", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "L/PN/Y":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["לְ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["a"],
                    stem_he="פָנ",
                    stem_morph="SUBS.BOTH.PL.C",
                    stem_es="rostro",
                    strongs="H6440",
                    suf_he="י",
                    suf_morph="PRS.P1.COMMON.SG",
                    suf_es="mí",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "M$XYT/M":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "מַשְׁחִית"
                hw["strongs"] = "H7843"
                hw["he_morph"] = "VERBO.HIF.PTCA.M.SG.C"
                _set_es_patch(hw, "destruiré", respect_user=respect_user_gloss)
                _attach_prs_suffix(hw, "ם", "PRS.P3.M.PL", "los")
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "RXB/H":
                _gen6_split_at_prs(
                    hw,
                    stem_he="רֹחַב",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="anchura",
                    strongs="H7341",
                    suf_he="הּ",
                    suf_morph="PRS.P3.F.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "QWMT/H":
                _gen6_split_at_prs(
                    hw,
                    stem_he="קוֹמָת",
                    stem_morph="SUBS.F.SG.C",
                    stem_es="altura",
                    strongs="H6967",
                    suf_he="הּ",
                    suf_morph="PRS.P3.F.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "TKL/NH":
                _gen6_split_at_prs(
                    hw,
                    stem_he="תְּכַל",
                    stem_morph="VERBO.PIEL.IMPF.P2.M.SG",
                    stem_es="terminarás",
                    strongs="H3615",
                    suf_he="נָּה",
                    suf_morph="PRS.P3.F.SG",
                    suf_es="la",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "M/L/M(L/H":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["מִ", "לְ"],
                    prefix_morphs=["PREP", "PREP"],
                    prefix_es=["de", "hacia"],
                    stem_he="מַעַל",
                    stem_morph="ADV",
                    stem_es="arriba",
                    strongs="H4605",
                    suf_he="ה",
                    suf_morph="SUF.DIR.HE",
                    suf_es="",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "T(&/H":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "תַּעֲשֶׂ"
                hw["strongs"] = "H6213"
                hw["he_morph"] = "VERBO.QAL.IMPF.P2.M.SG"
                _set_es_patch(hw, "la harás", respect_user=respect_user_gloss)
                _attach_prs_suffix(hw, "הָ", "PRS.P3.F.SG", "")
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "W/BN/YK":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["וּ"],
                    prefix_morphs=["CONJ"],
                    prefix_es=["y"],
                    stem_he="בָנֶי",
                    stem_morph="SUBS.M.PL.C",
                    stem_es="hijos",
                    strongs="H1121",
                    suf_he="ךָ",
                    suf_morph="PRS.P2.M.SG",
                    suf_es="tus",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw in ("W/$T/K", "W/)$T/K"):
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["וְ"],
                    prefix_morphs=["CONJ"],
                    prefix_es=["y"],
                    stem_he="אִשְׁתְּ",
                    stem_morph="SUBS.F.SG.C",
                    stem_es="mujer",
                    strongs="H802",
                    suf_he="ךָ",
                    suf_morph="PRS.P2.M.SG",
                    suf_es="tu",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "BN/YK" and vrs == 18:
                _gen6_split_at_prs(
                    hw,
                    stem_he="בָנֶי",
                    stem_morph="SUBS.M.PL.C",
                    stem_es="hijos",
                    strongs="H1121",
                    suf_he="ךָ",
                    suf_morph="PRS.P2.M.SG",
                    suf_es="tus",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")L/YK":
                _gen6_split_at_prs(
                    hw,
                    stem_he="אֵלַי",
                    stem_morph="PREP",
                    stem_es="a",
                    strongs="H413",
                    suf_he="ךָ",
                    suf_morph="PRS.P2.M.SG",
                    suf_es="ti",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "BRYT/Y":
                _gen6_split_at_prs(
                    hw,
                    stem_he="בְּרִית",
                    stem_morph="SUBS.F.SG.C",
                    stem_es="pacto",
                    strongs="H1285",
                    suf_he="י",
                    suf_morph="PRS.P1.COMMON.SG",
                    suf_es="mi",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")T/K" and vrs in (18, 19):
                _gen6_split_at_prs(
                    hw,
                    stem_he="אֵת",
                    stem_morph="PREP",
                    stem_es="con",
                    strongs="H854",
                    suf_he="ָךְ",
                    suf_morph="PRS.P2.F.SG",
                    suf_es="ti",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")T/W" and vrs == 22:
                _gen6_split_at_prs(
                    hw,
                    stem_he="אֵת",
                    stem_morph="PART.OBJ.DIR",
                    stem_es="",
                    strongs="H853",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="lo",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "W/$L$YM":
                hek = _gen5_he_key(hw)
                if hek.startswith("של") or hek == "ו":
                    _clear_hw_prefix_slots(hw)
                    hw["prefix_forms"] = ["וּ"]
                    hw["prefix_morphs"] = ["CONJ"]
                    hw["prefix_es"] = ["y"]
                    hw["he_form"] = "שְׁלֹשִׁים"
                    hw["strongs"] = "H7970"
                    hw["he_morph"] = "CBPA"
                    _set_es_patch(hw, "treinta", respect_user=respect_user_gloss)
                    hw.pop("prs_suffix", None)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

    _fix_gen6_oshb_align(verse, respect_user_gloss=respect_user_gloss)

    # 6:15 — שלש מאות en el par correcto (Strong/orden)
    if vrs == 15:
        for p in verse.get("pairs", []):
            hws = p.get("he_words") or []
            for hw in hws:
                if hw.get("raw") == "$L$" or _gen5_he_key(hw) == "שלש":
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "שְׁלֹשׁ"
                    hw["strongs"] = "H7969"
                    hw["he_morph"] = "NUM.CARD.F.SG.A"
                    _set_es_patch(hw, "tres", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"
                elif hw.get("raw") in ("M)WT", "M)WH") or _gen5_he_key(hw) == "מאות":
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "מֵאוֹת"
                    hw["strongs"] = "H3967"
                    hw["he_morph"] = "NUM.CARD.BOTH.PL.A"
                    _set_es_patch(hw, "cientos", respect_user=respect_user_gloss)
                    hw.pop("prs_suffix", None)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"
            for hw in hws:
                pfx = hw.get("prefix_forms") or []
                if pfx and _gen5_he_key({"he_form": pfx[0]}) == "מאות":
                    hw["prefix_forms"] = []
                    hw["prefix_morphs"] = []
                    hw["prefix_es"] = []

    # L/HM sobra en 6:1–6:4 frente a OSHB (המה va en par aparte en 6:4).
    if vrs in (1, 2, 4):
        for p in verse.get("pairs", []):
            p["he_words"] = [
                hw for hw in p.get("he_words", [])
                if hw.get("raw") != "L/HM"
            ]

    if vrs == 16:
        for p in verse.get("pairs", []):
            for hw in p.get("he_words", []):
                if hw.get("raw") == "H/TBH":
                    _clear_hw_prefix_slots(hw)
                    hw["prefix_forms"] = ["הַ"]
                    hw["prefix_morphs"] = ["ART"]
                    hw["prefix_es"] = ["la"]
                    hw["he_form"] = "תֵּבָה"
                    hw["strongs"] = "H8392"
                    hw["he_morph"] = "SUBS.F.SG.A"
                    _set_es_patch(hw, "arca", respect_user=respect_user_gloss)
                    hw.pop("prs_suffix", None)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

    for p in verse.get("pairs", []):
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if not (
                (hw.get("raw") or "").endswith("}")
                or (
                    hw.get("es_source") == "patch_meta"
                    and not _strip_niqqud(hw.get("he_form") or "")
                )
            )
        ]
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if (hw.get("he_form") or "").strip()
            or (hw.get("prefix_forms") or [])
            or (hw.get("prs_suffix") or {}).get("he_form")
            or hw.get("raw") in ("=L/MYN/W", "=L/MYN/HW")
        ]

    verse["pairs"] = [
        p for p in verse.get("pairs", [])
        if p.get("he_words")
        or (p.get("gr_unicode") or "").strip()
        or p.get("kind") == "heb_omit"
    ]

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _gen5_preserve_fused_ot(hw, respect_user_gloss=respect_user_gloss)
            _merge_prs_reading_gloss(hw)

    _gen6_reapply_oshb_splits(verse, respect_user_gloss=respect_user_gloss)

    _sanitize_catss_pairs(verse)


def _gen7_reapply_oshb_splits(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Reaplica splits cap. 7 tras _gen5_preserve_fused_ot."""
    vrs = verse.get("verse", 0)
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            raw = hw.get("raw", "")

            if raw == ")T/K":
                _gen6_split_at_prs(
                    hw,
                    stem_he="אֵת",
                    stem_morph="PART.OBJ.DIR",
                    stem_es="",
                    strongs="H853",
                    suf_he="ָךְ",
                    suf_morph="PRS.P2.M.SG",
                    suf_es="te",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")T/W" and vrs == 16:
                _gen6_split_at_prs(
                    hw,
                    stem_he="אֵת",
                    stem_morph="PART.OBJ.DIR",
                    stem_es="",
                    strongs="H853",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="lo",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")T/W" and vrs in (7, 23):
                _gen6_split_at_prs(
                    hw,
                    stem_he="אִתּ",
                    stem_morph="PREP",
                    stem_es="con",
                    strongs="H854",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="él",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")T/M" and vrs == 13:
                _gen6_split_at_prs(
                    hw,
                    stem_he="אִתּ",
                    stem_morph="PREP",
                    stem_es="con",
                    strongs="H854",
                    suf_he="ָם",
                    suf_morph="PRS.P3.M.PL",
                    suf_es="ellos",
                    respect_user_gloss=respect_user_gloss,
                )


def _fix_gen7_oshb_align(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Post-proceso cap. 7 — pares espurios, tokens rotos, orden."""
    vrs = verse.get("verse", 0)

    drop_raws: set[str] = set()
    if vrs == 2:
        drop_raws.add("L/K")

    if drop_raws:
        for p in verse.get("pairs", []):
            p["he_words"] = [
                hw for hw in p.get("he_words", [])
                if hw.get("raw") not in drop_raws
            ]

    if vrs == 9:
        pairs = verse.get("pairs", [])
        for i, p in enumerate(pairs):
            hws = p.get("he_words") or []
            if (
                len(hws) == 1
                and hws[0].get("raw") == "NX"
                and i > 0
            ):
                prev_hws = pairs[i - 1].get("he_words") or []
                if prev_hws and prev_hws[0].get("raw") == ")LHYM":
                    if not any(
                        (h.get("raw") or "") == ")T"
                        for pp in pairs
                        for h in (pp.get("he_words") or [])
                    ):
                        pairs.insert(i, {
                            "he_words": [{
                                "raw": ")T",
                                "he_form": "אֶת",
                                "he_morph": "PART.OBJ.DIR",
                                "strongs": "H853",
                                "es": "",
                                "es_source": "patch",
                                "prefix_forms": [],
                                "prefix_morphs": [],
                                "prefix_es": [],
                            }],
                        })
                    break

    if vrs == 15:
        for p in verse.get("pairs", []):
            p["he_words"] = [
                hw for hw in p.get("he_words", [])
                if hw.get("raw") != "B/W"
            ]

    if vrs == 22:
        for p in verse.get("pairs", []):
            hws = p.get("he_words") or []
            if any(h.get("raw") == "RWX#7:22" for h in hws):
                continue
            new_hws: list[dict] = []
            for hw in hws:
                new_hws.append(hw)
                if hw.get("raw") == "N$MT":
                    new_hws.append({
                        "raw": "RWX#7:22",
                        "he_form": "רוּחַ",
                        "he_morph": "SUBS.BOTH.SG.C",
                        "strongs": "H7307",
                        "es": "espíritu",
                        "es_source": "patch",
                        "prefix_forms": [],
                        "prefix_morphs": [],
                        "prefix_es": [],
                    })
            p["he_words"] = new_hws

    if vrs == 16:
        for p in verse.get("pairs", []):
            hws = p.get("he_words") or []
            if any(h.get("raw") == ")LHYM" for h in hws):
                p["he_words"] = [{
                    "raw": ")LHYM",
                    "he_form": "אֱלֹהִים",
                    "he_morph": "SUBS.M.PL.A",
                    "strongs": "H430",
                    "es": "Dios",
                    "es_source": "patch",
                    "prefix_forms": [],
                    "prefix_morphs": [],
                    "prefix_es": [],
                }]
            for hw in hws:
                if hw.get("raw") == "B/(D/W":
                    _gen6_split_at_prs(
                        hw,
                        stem_he="בַּעֲד",
                        stem_morph="PREP",
                        stem_es="por",
                        strongs="H5704",
                        suf_he="וֹ",
                        suf_morph="PRS.P3.M.SG",
                        suf_es="él",
                        respect_user_gloss=respect_user_gloss,
                    )

    verse["pairs"] = [
        p for p in verse.get("pairs", [])
        if p.get("he_words")
        or (p.get("gr_unicode") or "").strip()
        or p.get("kind") == "heb_omit"
    ]


def _patch_gen7(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Parches estructurales Génesis cap. 7 — PRS, arca, diluvio."""
    vrs = verse.get("verse", 0)
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            raw = hw.get("raw", "")

            if raw == "L/NX":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["לְ"]
                hw["prefix_morphs"] = ["PREP"]
                hw["prefix_es"] = ["a"]
                hw["he_form"] = "נֹחַ"
                hw["strongs"] = "H5146"
                hw["he_morph"] = "NPROP"
                _set_es_patch(hw, "Noé", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "BYT/K":
                _gen6_split_at_prs(
                    hw,
                    stem_he="בֵּית",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="casa",
                    strongs="H1004",
                    suf_he="ךָ",
                    suf_morph="PRS.P2.M.SG",
                    suf_es="tu",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")T/K":
                _gen6_split_at_prs(
                    hw,
                    stem_he="אֵת",
                    stem_morph="PART.OBJ.DIR",
                    stem_es="",
                    strongs="H853",
                    suf_he="ָךְ",
                    suf_morph="PRS.P2.M.SG",
                    suf_es="te",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "L/PN/Y":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["לְ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["a"],
                    stem_he="פָנ",
                    stem_morph="SUBS.BOTH.PL.C",
                    stem_es="rostro",
                    strongs="H6440",
                    suf_he="י",
                    suf_morph="PRS.P1.COMMON.SG",
                    suf_es="mí",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "W/)$T/W":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["וְ"],
                    prefix_morphs=["CONJ"],
                    prefix_es=["y"],
                    stem_he="אִשְׁתּ",
                    stem_morph="SUBS.F.SG.C",
                    stem_es="mujer",
                    strongs="H802",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw in ("CW/HW", "CWH/W"):
                _gen6_split_at_prs(
                    hw,
                    stem_he="צִוָּ",
                    stem_morph="VERBO.PIEL.PERF.P3.M.SG",
                    stem_es="mandó",
                    strongs="H6680",
                    suf_he="הוּ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="le",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "W/BN/YW":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["וּ"],
                    prefix_morphs=["CONJ"],
                    prefix_es=["y"],
                    stem_he="בָנֵי",
                    stem_morph="SUBS.M.PL.C",
                    stem_es="hijos",
                    strongs="H1121",
                    suf_he="ו",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "BN/YW":
                _gen6_split_at_prs(
                    hw,
                    stem_he="בָנֵי",
                    stem_morph="SUBS.M.PL.C",
                    stem_es="hijos",
                    strongs="H1121",
                    suf_he="ו",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")T/W" and vrs == 16:
                _gen6_split_at_prs(
                    hw,
                    stem_he="אֵת",
                    stem_morph="PART.OBJ.DIR",
                    stem_es="",
                    strongs="H853",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="lo",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")T/W" and vrs in (7, 23):
                _gen6_split_at_prs(
                    hw,
                    stem_he="אִתּ",
                    stem_morph="PREP",
                    stem_es="con",
                    strongs="H854",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="él",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")T/M" and vrs == 13:
                _gen6_split_at_prs(
                    hw,
                    stem_he="אִתּ",
                    stem_morph="PREP",
                    stem_es="con",
                    strongs="H854",
                    suf_he="ָם",
                    suf_morph="PRS.P3.M.PL",
                    suf_es="ellos",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "B/(D/W":
                _gen6_split_at_prs(
                    hw,
                    stem_he="בַּעֲד",
                    stem_morph="PREP",
                    stem_es="por",
                    strongs="H5704",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="él",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "M/L/M(L/H":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["מִ", "לְ"],
                    prefix_morphs=["PREP", "PREP"],
                    prefix_es=["de", "hacia"],
                    stem_he="מַעַל",
                    stem_morph="ADV",
                    stem_es="arriba",
                    strongs="H4605",
                    suf_he="ה",
                    suf_morph="SUF.DIR.HE",
                    suf_es="",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "H/MYM":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["הַ"]
                hw["prefix_morphs"] = ["ART"]
                hw["prefix_es"] = ["las"]
                hw["he_form"] = "מַּיִם"
                hw["strongs"] = "H4325"
                hw["he_morph"] = "SUBS.M.PL.A"
                _set_es_patch(hw, "aguas", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "H/+HWRH":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["הַ"]
                hw["prefix_morphs"] = ["ART"]
                hw["prefix_es"] = ["la"]
                hw["he_form"] = "טְּהוֹרָה"
                hw["strongs"] = "H2889"
                hw["he_morph"] = "AFSA"
                _set_es_patch(hw, "limpia", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "W/MN":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["וּ"]
                hw["prefix_morphs"] = ["CONJ"]
                hw["prefix_es"] = ["y"]
                hw["he_form"] = "מִן"
                hw["strongs"] = "H4480"
                hw["he_morph"] = "PREP"
                _set_es_patch(hw, "de", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "MN" and vrs == 8 and _gen5_he_key(hw) != "מן":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "מִן"
                hw["strongs"] = "H4480"
                hw["he_morph"] = "PREP"
                _set_es_patch(hw, "de", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == ")YN/NH" and vrs == 8:
                _gen6_split_at_prs(
                    hw,
                    stem_he="אֵינֶנָּ",
                    stem_morph="NEG",
                    stem_es="no es",
                    strongs="H369",
                    suf_he="ה",
                    suf_morph="PRS.P3.F.SG",
                    suf_es="",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "HW)":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "הִוא"
                hw["strongs"] = "H1931"
                hw["he_morph"] = "PRON.PERS.P3.F.SG"
                _set_es_patch(hw, "ella", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "H/TBH":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["הַ"]
                hw["prefix_morphs"] = ["ART"]
                hw["prefix_es"] = ["la"]
                hw["he_form"] = "תֵּבָה"
                hw["strongs"] = "H8392"
                hw["he_morph"] = "SUBS.F.SG.A"
                _set_es_patch(hw, "arca", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "H/BHMH":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["הַ"]
                hw["prefix_morphs"] = ["ART"]
                hw["prefix_es"] = ["la"]
                hw["he_form"] = "בְּהֵמָה"
                hw["strongs"] = "H929"
                hw["he_morph"] = "SUBS.F.SG.A"
                _set_es_patch(hw, "bestia", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "H/MBWL":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["הַ"]
                hw["prefix_morphs"] = ["ART"]
                hw["prefix_es"] = ["el"]
                hw["he_form"] = "מַבּוּל"
                hw["strongs"] = "H3999"
                hw["he_morph"] = "SUBS.M.SG.A"
                _set_es_patch(hw, "diluvio", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "B/)P/YW":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["בְּ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["en"],
                    stem_he="אַפַּי",
                    stem_morph="SUBS.M.DU.C",
                    stem_es="narices",
                    strongs="H639",
                    suf_he="ו",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

    _fix_gen7_oshb_align(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if not (
                (hw.get("raw") or "").endswith("}")
                or (
                    hw.get("es_source") == "patch_meta"
                    and not _strip_niqqud(hw.get("he_form") or "")
                )
            )
        ]
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if (hw.get("he_form") or "").strip()
            or (hw.get("prefix_forms") or [])
            or (hw.get("prs_suffix") or {}).get("he_form")
            or hw.get("raw") in ("=L/MYN/W", "=L/MYN/HW")
        ]

    verse["pairs"] = [
        p for p in verse.get("pairs", [])
        if p.get("he_words")
        or (p.get("gr_unicode") or "").strip()
        or p.get("kind") == "heb_omit"
    ]

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _gen5_preserve_fused_ot(hw, respect_user_gloss=respect_user_gloss)
            _merge_prs_reading_gloss(hw)

    _gen7_reapply_oshb_splits(verse, respect_user_gloss=respect_user_gloss)

    _sanitize_catss_pairs(verse)


def _gen8_reapply_oshb_splits(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Reaplica splits cap. 8 tras _gen5_preserve_fused_ot."""
    vrs = verse.get("verse", 0)
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            raw = hw.get("raw", "")

            if raw == ")T/K" and vrs == 16:
                _gen6_split_at_prs(
                    hw,
                    stem_he="אִתּ",
                    stem_morph="PREP",
                    stem_es="con",
                    strongs="H854",
                    suf_he="ךְ",
                    suf_morph="PRS.P2.F.SG",
                    suf_es="ti",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")T/K" and vrs == 17:
                pfx = hw.get("prefix_forms") or []
                pfx_key = _gen5_he_key({"he_form": pfx[0]}) if pfx else ""
                if pfx_key in ("ך", "כ"):
                    suf, suf_m, suf_es = "ךְ", "PRS.P2.F.SG", "ti"
                else:
                    suf, suf_m, suf_es = "ךָ", "PRS.P2.M.SG", "te"
                _gen6_split_at_prs(
                    hw,
                    stem_he="אִתּ",
                    stem_morph="PREP",
                    stem_es="con",
                    strongs="H854",
                    suf_he=suf,
                    suf_morph=suf_m,
                    suf_es=suf_es,
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw in ("W/$T/K", "W/)$T/K") and vrs == 16:
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["וְ"],
                    prefix_morphs=["CONJ"],
                    prefix_es=["y"],
                    stem_he="אִשְׁתְּ",
                    stem_morph="SUBS.F.SG.C",
                    stem_es="mujer",
                    strongs="H802",
                    suf_he="ךָ",
                    suf_morph="PRS.P2.M.SG",
                    suf_es="tu",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "W/BN/YK" and vrs == 16:
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["וּ"],
                    prefix_morphs=["CONJ"],
                    prefix_es=["y"],
                    stem_he="בָנֶי",
                    stem_morph="SUBS.M.PL.C",
                    stem_es="hijos",
                    strongs="H1121",
                    suf_he="ךָ",
                    suf_morph="PRS.P2.M.SG",
                    suf_es="tus",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "BN/YK" and vrs == 16:
                _gen6_split_at_prs(
                    hw,
                    stem_he="בָנֶי",
                    stem_morph="SUBS.M.PL.C",
                    stem_es="hijos",
                    strongs="H1121",
                    suf_he="ךָ",
                    suf_morph="PRS.P2.M.SG",
                    suf_es="tus",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")T/W" and vrs in (1, 18):
                _gen6_split_at_prs(
                    hw,
                    stem_he="אִתּ",
                    stem_morph="PREP",
                    stem_es="con",
                    strongs="H854",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="él",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "W/)$T/W" and vrs == 18:
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["וְ"],
                    prefix_morphs=["CONJ"],
                    prefix_es=["y"],
                    stem_he="אִשְׁתּ",
                    stem_morph="SUBS.F.SG.C",
                    stem_es="mujer",
                    strongs="H802",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "M/)T/W" and vrs == 8:
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["מֵ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["de"],
                    stem_he="אִתּ",
                    stem_morph="PREP",
                    stem_es="con",
                    strongs="H854",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="él",
                    respect_user_gloss=respect_user_gloss,
                )


def _fix_gen8_oshb_align(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Post-proceso cap. 8 — orden, tokens rotos, inserciones OSHB."""
    vrs = verse.get("verse", 0)
    pairs = verse.get("pairs", [])

    def _next_nonempty_idx(start: int) -> int | None:
        j = start
        while j < len(pairs):
            if pairs[j].get("he_words"):
                return j
            j += 1
        return None

    def _has_raw(raw: str) -> bool:
        return any(
            (h.get("raw") or "") == raw
            for pp in pairs
            for h in (pp.get("he_words") or [])
        )

    if vrs == 5:
        for i, p in enumerate(pairs):
            hws = p.get("he_words") or []
            if len(hws) == 1 and hws[0].get("raw") == "HYW":
                j = _next_nonempty_idx(i + 1)
                if j is not None and (pairs[j]["he_words"][0].get("raw") or "") == "W/XSWR":
                    if not _has_raw("H/LWK"):
                        hlk = {
                            "raw": "H/LWK",
                            "he_form": "הָלוֹךְ",
                            "he_morph": "VERBO.QAL.INFA",
                            "strongs": "H3212",
                            "es": "yendo",
                            "es_source": "patch",
                            "prefix_forms": [],
                            "prefix_morphs": [],
                            "prefix_es": [],
                        }
                        empty_slot = i + 1
                        if empty_slot < len(pairs) and not pairs[empty_slot].get("he_words"):
                            pairs[empty_slot]["he_words"] = [hlk]
                        else:
                            pairs.insert(j, {"he_words": [hlk]})
                    break

    if vrs == 9:
        for p in verse.get("pairs", []):
            hws = p.get("he_words") or []
            for hi, hw in enumerate(hws):
                if hw.get("raw") != "L/KP":
                    continue
                if hi + 1 < len(hws) and (hws[hi + 1].get("raw") or "") == "RGL/H":
                    break
                if hi + 1 < len(hws):
                    nxt = hws[hi + 1]
                    if _gen5_he_key(nxt).startswith("רגל"):
                        _gen6_split_at_prs(
                            nxt,
                            stem_he="רַגְל",
                            stem_morph="SUBS.F.SG.C",
                            stem_es="pie",
                            strongs="H7272",
                            suf_he="הּ",
                            suf_morph="PRS.P3.F.SG",
                            suf_es="su",
                            respect_user_gloss=respect_user_gloss,
                        )
                    break
                else:
                    hws.insert(hi + 1, {
                        "raw": "RGL/H",
                        "he_form": "רַגְל",
                        "he_morph": "SUBS.F.SG.C",
                        "strongs": "H7272",
                        "es": "pie",
                        "es_source": "patch",
                        "prefix_forms": [],
                        "prefix_morphs": [],
                        "prefix_es": [],
                        "prs_suffix": {
                            "he_form": "הּ",
                            "he_morph": "PRS.P3.F.SG",
                            "es": "su",
                        },
                    })
                    p["he_words"] = hws
                break

    if vrs == 13:
        for p in verse.get("pairs", []):
            for hw in p.get("he_words", []):
                if hw.get("raw") == "B)XD":
                    _clear_hw_prefix_slots(hw)
                    hw["prefix_forms"] = ["בְּ"]
                    hw["prefix_morphs"] = ["PREP"]
                    hw["prefix_es"] = ["en"]
                    hw["he_form"] = "אֶחָד"
                    hw["strongs"] = "H259"
                    hw["he_morph"] = "CMSA"
                    _set_es_patch(hw, "uno", respect_user=respect_user_gloss)
                    hw.pop("prs_suffix", None)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

    if vrs == 17:
        tk_seen = 0
        for p in pairs:
            for hw in p.get("he_words", []):
                if hw.get("raw") != ")T/K":
                    continue
                tk_seen += 1
                if tk_seen == 2:
                    _gen6_split_at_prs(
                        hw,
                        stem_he="אִתּ",
                        stem_morph="PREP",
                        stem_es="con",
                        strongs="H854",
                        suf_he="ךְ",
                        suf_morph="PRS.P2.F.SG",
                        suf_es="ti",
                        respect_user_gloss=respect_user_gloss,
                    )

        for i, p in enumerate(pairs):
            hws = p.get("he_words") or []
            if len(hws) == 1 and hws[0].get("raw") == "H/)RC":
                j = _next_nonempty_idx(i + 1)
                if j is not None and (pairs[j]["he_words"][0].get("raw") or "") == ")T/K":
                    if not _has_raw("H/YTZ#8:17"):
                        imp = {
                            "raw": "H/YTZ#8:17",
                            "he_form": "הַיְצֵא",
                            "he_morph": "VERBO.HIF.IMPV.P2.M.SG",
                            "strongs": "H3318",
                            "es": "saca",
                            "es_source": "patch",
                            "prefix_forms": [],
                            "prefix_morphs": [],
                            "prefix_es": [],
                        }
                        empty_slot = i + 1
                        if empty_slot < len(pairs) and not pairs[empty_slot].get("he_words"):
                            pairs[empty_slot]["he_words"] = [imp]
                        else:
                            pairs.insert(j, {"he_words": [imp]})
                    break

    if vrs == 18:
        for p in pairs:
            for hw in p.get("he_words", []):
                if hw.get("raw") == "BN/YW":
                    pfx = hw.get("prefix_forms") or []
                    if not (hw.get("he_form") or "").strip() and not pfx:
                        _gen6_split_at_prs(
                            hw,
                            stem_he="בָנָי",
                            stem_morph="SUBS.M.PL.C",
                            stem_es="hijos",
                            strongs="H1121",
                            suf_he="ו",
                            suf_morph="PRS.P3.M.SG",
                            suf_es="su",
                            respect_user_gloss=respect_user_gloss,
                        )
                elif hw.get("raw") in ("W/BN/YW", "BN/YW") and not hw.get("strongs"):
                    hw["strongs"] = "H1121"
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"
                if hw.get("raw") == "W/BN/YW" and vrs == 18:
                    _set_es_patch(hw, "hijos", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

    if vrs == 19:
        for p in pairs:
            for hw in p.get("he_words", []):
                if hw.get("raw") == "L/M$PXT/YHM":
                    prs = (hw.get("prs_suffix") or {}).get("he_form", "")
                    if prs == "הֶם" and not (hw.get("he_form") or "").endswith("י"):
                        hw["he_form"] = "מִשְׁפְּחֹתֵי"
                        if not (respect_user_gloss and _has_user_gloss(hw)):
                            hw["es_source"] = "patch"

        for i, p in enumerate(pairs):
            hws = p.get("he_words") or []
            if len(hws) == 1 and hws[0].get("raw") == "L/M$PXT/YHM":
                j = _next_nonempty_idx(i + 1)
                if j is not None and (pairs[j]["he_words"][0].get("raw") or "") == "MN":
                    if not _has_raw("YC)W"):
                        yc = {
                            "raw": "YC)W",
                            "he_form": "יָצְאוּ",
                            "he_morph": "VERBO.QAL.PERF.P3.COMMON.PL",
                            "strongs": "H3318",
                            "es": "salieron",
                            "es_source": "patch",
                            "prefix_forms": [],
                            "prefix_morphs": [],
                            "prefix_es": [],
                        }
                        empty_slot = i + 1
                        if empty_slot < len(pairs) and not pairs[empty_slot].get("he_words"):
                            pairs[empty_slot]["he_words"] = [yc]
                        else:
                            pairs.insert(j, {"he_words": [yc]})
                    break

    verse["pairs"] = [
        p for p in verse.get("pairs", [])
        if p.get("he_words")
        or (p.get("gr_unicode") or "").strip()
        or p.get("kind") == "heb_omit"
    ]


def _patch_gen8(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Parches estructurales Génesis cap. 8 — arca, paloma, salida."""
    vrs = verse.get("verse", 0)
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            raw = hw.get("raw", "")

            if raw == "L/NX":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["לְ"]
                hw["prefix_morphs"] = ["PREP"]
                hw["prefix_es"] = ["a"]
                hw["he_form"] = "נֹחַ"
                hw["strongs"] = "H5146"
                hw["he_morph"] = "NPROP"
                _set_es_patch(hw, "Noé", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == ")T/W" and vrs in (1, 18):
                _gen6_split_at_prs(
                    hw,
                    stem_he="אִתּ",
                    stem_morph="PREP",
                    stem_es="con",
                    strongs="H854",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="él",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "M/)T/W" and vrs == 8:
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["מֵ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["de"],
                    stem_he="אִתּ",
                    stem_morph="PREP",
                    stem_es="con",
                    strongs="H854",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="él",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")L/YW":
                _gen6_split_at_prs(
                    hw,
                    stem_he="אֵלַי",
                    stem_morph="PREP",
                    stem_es="a",
                    strongs="H413",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="él",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "YD/W" and vrs == 9:
                _gen6_split_at_prs(
                    hw,
                    stem_he="יָד",
                    stem_morph="SUBS.BOTH.SG.C",
                    stem_es="mano",
                    strongs="H3027",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "RGL/H" and vrs == 9:
                _gen6_split_at_prs(
                    hw,
                    stem_he="רַגְל",
                    stem_morph="SUBS.F.SG.C",
                    stem_es="pie",
                    strongs="H7272",
                    suf_he="הּ",
                    suf_morph="PRS.P3.F.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "W/YQX/H" and vrs == 9:
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["וַ"],
                    prefix_morphs=["CONJ"],
                    prefix_es=["y"],
                    stem_he="יִּקָּח",
                    stem_morph="VERBO.QAL.WAYYIQT.P3.M.SG",
                    stem_es="tomó",
                    strongs="H3947",
                    suf_he="הָ",
                    suf_morph="PRS.P3.F.SG",
                    suf_es="la",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "H/LWK":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "הָלוֹךְ"
                hw["strongs"] = "H3212"
                hw["he_morph"] = "VERBO.QAL.INFA"
                _set_es_patch(hw, "yendo", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "W/$WB" and vrs == 3:
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["וָ"]
                hw["prefix_morphs"] = ["CONJ"]
                hw["prefix_es"] = ["y"]
                hw["he_form"] = "שׁוֹב"
                hw["strongs"] = "H7725"
                hw["he_morph"] = "VERBO.QAL.INFA"
                _set_es_patch(hw, "volviendo", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "B/PY/H" and vrs == 11:
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["בְּ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["en"],
                    stem_he="פִּי",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="boca",
                    strongs="H6310",
                    suf_he="הָ",
                    suf_morph="PRS.P3.F.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw in ("W/$T/K", "W/)$T/K") and vrs == 16:
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["וְ"],
                    prefix_morphs=["CONJ"],
                    prefix_es=["y"],
                    stem_he="אִשְׁתְּ",
                    stem_morph="SUBS.F.SG.C",
                    stem_es="mujer",
                    strongs="H802",
                    suf_he="ךָ",
                    suf_morph="PRS.P2.M.SG",
                    suf_es="tu",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "W/BN/YK" and vrs == 16:
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["וּ"],
                    prefix_morphs=["CONJ"],
                    prefix_es=["y"],
                    stem_he="בָנֶי",
                    stem_morph="SUBS.M.PL.C",
                    stem_es="hijos",
                    strongs="H1121",
                    suf_he="ךָ",
                    suf_morph="PRS.P2.M.SG",
                    suf_es="tus",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "BN/YK" and vrs == 16:
                _gen6_split_at_prs(
                    hw,
                    stem_he="בָנֶי",
                    stem_morph="SUBS.M.PL.C",
                    stem_es="hijos",
                    strongs="H1121",
                    suf_he="ךָ",
                    suf_morph="PRS.P2.M.SG",
                    suf_es="tus",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")T/K" and vrs == 17:
                pfx = hw.get("prefix_forms") or []
                pfx_key = _gen5_he_key({"he_form": pfx[0]}) if pfx else ""
                if pfx_key in ("ך", "כ"):
                    suf, suf_m, suf_es = "ךְ", "PRS.P2.F.SG", "ti"
                else:
                    suf, suf_m, suf_es = "ךָ", "PRS.P2.M.SG", "te"
                _gen6_split_at_prs(
                    hw,
                    stem_he="אִתּ",
                    stem_morph="PREP",
                    stem_es="con",
                    strongs="H854",
                    suf_he=suf,
                    suf_morph=suf_m,
                    suf_es=suf_es,
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")T/K" and vrs == 16:
                _gen6_split_at_prs(
                    hw,
                    stem_he="אִתּ",
                    stem_morph="PREP",
                    stem_es="con",
                    strongs="H854",
                    suf_he="ךְ",
                    suf_morph="PRS.P2.F.SG",
                    suf_es="ti",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "W/)$T/W" and vrs == 18:
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["וְ"],
                    prefix_morphs=["CONJ"],
                    prefix_es=["y"],
                    stem_he="אִשְׁתּ",
                    stem_morph="SUBS.F.SG.C",
                    stem_es="mujer",
                    strongs="H802",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "BN/YW" and vrs == 18:
                _gen6_split_at_prs(
                    hw,
                    stem_he="בָנָי",
                    stem_morph="SUBS.M.PL.C",
                    stem_es="hijos",
                    strongs="H1121",
                    suf_he="ו",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "W/N$Y" and vrs == 18:
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["וּ"]
                hw["prefix_morphs"] = ["CONJ"]
                hw["prefix_es"] = ["y"]
                hw["he_form"] = "נְשֵׁי"
                hw["strongs"] = "H802"
                hw["he_morph"] = "SUBS.F.PL.C"
                _set_es_patch(hw, "mujeres", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "L/M$PXT/YHM" and vrs == 19:
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["לְ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["por"],
                    stem_he="מִשְׁפְּחֹתֵי",
                    stem_morph="SUBS.F.PL.C",
                    stem_es="familias",
                    strongs="H4940",
                    suf_he="הֶם",
                    suf_morph="PRS.P3.M.PL",
                    suf_es="sus",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "LB/W" and vrs == 21:
                _gen6_split_at_prs(
                    hw,
                    stem_he="לֵב",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="corazón",
                    strongs="H3820",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "(WD" and vrs == 21:
                if _gen5_he_key(hw) in ("את", "את־"):
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "עוֹד"
                    hw["strongs"] = "H5750"
                    hw["he_morph"] = "ADV"
                    _set_es_patch(hw, "más", respect_user=respect_user_gloss)
                    hw.pop("prs_suffix", None)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

            elif raw == "M/N(R/YW" and vrs == 21:
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["מִ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["desde"],
                    stem_he="נְעֻרָי",
                    stem_morph="SUBS.BOTH.PL.C",
                    stem_es="juventud",
                    strongs="H5271",
                    suf_he="ו",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "H/MYM":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["הַ"]
                hw["prefix_morphs"] = ["ART"]
                hw["prefix_es"] = ["las"]
                hw["he_form"] = "מַּיִם"
                hw["strongs"] = "H4325"
                hw["he_morph"] = "SUBS.M.PL.A"
                _set_es_patch(hw, "aguas", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "H/TBH":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["הַ"]
                hw["prefix_morphs"] = ["ART"]
                hw["prefix_es"] = ["la"]
                hw["he_form"] = "תֵּבָה"
                hw["strongs"] = "H8392"
                hw["he_morph"] = "SUBS.F.SG.A"
                _set_es_patch(hw, "arca", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "H/+HWRH":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["הַ"]
                hw["prefix_morphs"] = ["ART"]
                hw["prefix_es"] = ["la"]
                hw["he_form"] = "טְּהוֹרָה"
                hw["strongs"] = "H2889"
                hw["he_morph"] = "AFSA"
                _set_es_patch(hw, "limpia", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

    _fix_gen8_oshb_align(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if not (
                (hw.get("raw") or "").endswith("}")
                or (
                    hw.get("es_source") == "patch_meta"
                    and not _strip_niqqud(hw.get("he_form") or "")
                )
            )
        ]
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if (hw.get("he_form") or "").strip()
            or (hw.get("prefix_forms") or [])
            or (hw.get("prs_suffix") or {}).get("he_form")
            or hw.get("raw") in ("=L/MYN/W", "=L/MYN/HW")
        ]

    verse["pairs"] = [
        p for p in verse.get("pairs", [])
        if p.get("he_words")
        or (p.get("gr_unicode") or "").strip()
        or p.get("kind") == "heb_omit"
    ]

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _gen5_preserve_fused_ot(hw, respect_user_gloss=respect_user_gloss)
            _merge_prs_reading_gloss(hw)

    _gen8_reapply_oshb_splits(verse, respect_user_gloss=respect_user_gloss)

    _fix_gen8_lxx_align(verse)
    _sanitize_catss_pairs(verse)


def _gen9_standalone_vav_hw() -> dict:
    return {
        "raw": "=VAV",
        "he_form": "ו",
        "he_morph": "CONJ",
        "strongs": "",
        "es": "y",
        "es_source": "patch",
        "prefix_forms": [],
        "prefix_morphs": [],
        "prefix_es": [],
    }


def _gen9_reapply_oshb_splits(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Reaplica splits cap. 9 tras _gen5_preserve_fused_ot / merge PRS."""
    vrs = verse.get("verse", 0)
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            raw = hw.get("raw", "")

            if raw in ("BN/YW", "W/BN/YW"):
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=(["וּ"] if raw.startswith("W/") else None),
                    prefix_morphs=(["CONJ"] if raw.startswith("W/") else None),
                    prefix_es=(["y"] if raw.startswith("W/") else None),
                    stem_he="בָנָי",
                    stem_morph="SUBS.M.PL.C",
                    stem_es="hijos",
                    strongs="H1121",
                    suf_he="ו",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")T/KM":
                _gen6_split_at_prs(
                    hw,
                    stem_he="אִתּ",
                    stem_morph="PREP",
                    stem_es="con",
                    strongs="H854",
                    suf_he="כֶם",
                    suf_morph="PRS.P2.M.PL",
                    suf_es="ustedes",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "BRYT/Y":
                _gen6_split_at_prs(
                    hw,
                    stem_he="בְּרִית",
                    stem_morph="SUBS.F.SG.C",
                    stem_es="pacto",
                    strongs="H1285",
                    suf_he="י",
                    suf_morph="PRS.P1.COMMON.SG",
                    suf_es="mi",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "HN/NY":
                _gen6_split_at_prs(
                    hw,
                    stem_he="הִנְנִ",
                    stem_morph="INTJ",
                    stem_es="he aquí",
                    suf_he="י",
                    suf_morph="PRS.P1.COMMON.SG",
                    suf_es="",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "BYN/Y" and vrs in (12, 13, 15, 17):
                _gen6_split_at_prs(
                    hw,
                    stem_he="בֵּינִ",
                    stem_morph="PREP",
                    stem_es="entre",
                    strongs="H996",
                    suf_he="י",
                    suf_morph="PRS.P1.COMMON.SG",
                    suf_es="mí",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "W/BYN/YKM" and vrs in (12, 15):
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["וּ"],
                    prefix_morphs=["CONJ"],
                    prefix_es=["y"],
                    stem_he="בֵינֵי",
                    stem_morph="PREP",
                    stem_es="entre",
                    strongs="H996",
                    suf_he="כֶם",
                    suf_morph="PRS.P2.M.PL",
                    suf_es="ustedes",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "B/NP$/W":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["בְּ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["con"],
                    stem_he="נַפְשׁ",
                    stem_morph="SUBS.BOTH.SG.C",
                    stem_es="alma",
                    strongs="H5315",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "DM/W":
                _gen6_split_at_prs(
                    hw,
                    stem_he="דָמ",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="sangre",
                    strongs="H1818",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "DM/KM":
                _gen6_split_at_prs(
                    hw,
                    stem_he="דִּמְ",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="sangre",
                    strongs="H1818",
                    suf_he="כֶם",
                    suf_morph="PRS.P2.M.PL",
                    suf_es="vuestra",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "DM/W":
                _gen6_split_at_prs(
                    hw,
                    stem_he="דָמ",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="sangre",
                    strongs="H1818",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "L/NP$T/YKM":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["לְ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["por"],
                    stem_he="נַפְשֹׁתֵי",
                    stem_morph="SUBS.BOTH.PL.C",
                    stem_es="vidas",
                    strongs="H5315",
                    suf_he="כֶם",
                    suf_morph="PRS.P2.M.PL",
                    suf_es="vuestras",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")DR$/NW":
                _gen6_split_at_prs(
                    hw,
                    stem_he="אֶדְרֹשׁ",
                    stem_morph="VERBO.QAL.IMPF.P1.COMMON.SG",
                    stem_es="demandaré",
                    strongs="H1875",
                    suf_he="נּוּ",
                    suf_morph="PRS.P1.COMMON.PL",
                    suf_es="lo",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "ZR(/KM":
                _gen6_split_at_prs(
                    hw,
                    stem_he="זַרְע",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="descendencia",
                    strongs="H2233",
                    suf_he="כֶם",
                    suf_morph="PRS.P2.M.PL",
                    suf_es="vuestra",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")XR/YKM":
                _gen6_split_at_prs(
                    hw,
                    stem_he="אַחֲרֵי",
                    stem_morph="PREP",
                    stem_es="después",
                    strongs="H310",
                    suf_he="כֶם",
                    suf_morph="PRS.P2.M.PL",
                    suf_es="de ustedes",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw in ("QST/Y", "Q$T/Y") and vrs == 13:
                _gen6_split_at_prs(
                    hw,
                    stem_he="קַשְׁת",
                    stem_morph="SUBS.F.SG.C",
                    stem_es="arco",
                    strongs="H7198",
                    suf_he="ִי",
                    suf_morph="PRS.P1.COMMON.SG",
                    suf_es="mi",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")T/W" and vrs == 8:
                _gen6_split_at_prs(
                    hw,
                    stem_he="אִתּ",
                    stem_morph="PREP",
                    stem_es="con",
                    strongs="H854",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="él",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")XY/W" or raw == ")X/YW":
                _gen6_split_at_prs(
                    hw,
                    stem_he="אֶחָי" if raw == ")X/YW" else "אָחִי",
                    stem_morph="SUBS.M.PL.C" if raw == ")X/YW" else "SUBS.M.SG.C",
                    stem_es="hermanos" if raw == ")X/YW" else "hermano",
                    strongs="H251",
                    suf_he="ו",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "L/)X/YW":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["לְ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["a"],
                    stem_he="אֶחָי",
                    stem_morph="SUBS.M.PL.C",
                    stem_es="hermanos",
                    strongs="H251",
                    suf_he="ו",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")BY/W" and vrs == 22:
                _gen6_split_at_prs(
                    hw,
                    stem_he="אָבִי",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="padre",
                    strongs="H1",
                    suf_he="ו",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "$N/YHM" and vrs == 23:
                _gen6_split_at_prs(
                    hw,
                    stem_he="שְׁנֵי",
                    stem_morph="NUM.CARD.M.DU.C",
                    stem_es="dos",
                    strongs="H8147",
                    suf_he="הֶם",
                    suf_morph="PRS.P3.M.PL",
                    suf_es="ellos",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")BY/HM":
                _gen6_split_at_prs(
                    hw,
                    stem_he="אֲבִי",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="padre",
                    strongs="H1",
                    suf_he="הֶם",
                    suf_morph="PRS.P3.M.PL",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "W/PN/YHM":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["וּ"],
                    prefix_morphs=["CONJ"],
                    prefix_es=["y"],
                    stem_he="פְנֵי",
                    stem_morph="SUBS.BOTH.PL.C",
                    stem_es="rostro",
                    strongs="H6440",
                    suf_he="הֶם",
                    suf_morph="PRS.P3.M.PL",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "M/YYN/W" and vrs == 24:
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["מִ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["de"],
                    stem_he="יֵינ",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="vino",
                    strongs="H3196",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "BN/W" and vrs == 24:
                _gen6_split_at_prs(
                    hw,
                    stem_he="בְּנ",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="hijo",
                    strongs="H1121",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "AHL/H" and vrs == 21:
                _gen6_split_at_prs(
                    hw,
                    stem_he="אָהֳלֹ",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="tienda",
                    strongs="H168",
                    suf_he="ה",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "B/(NN/Y" and vrs == 14:
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["בְּ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["en"],
                    stem_he="עַנְנִ",
                    stem_morph="VERBO.PIEL.INFC",
                    stem_es="nube",
                    strongs="H6042",
                    suf_he="י",
                    suf_morph="PRS.P1.COMMON.SG",
                    suf_es="",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "W/R)YTY/H" and vrs == 16:
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["וּ"],
                    prefix_morphs=["CONJ"],
                    prefix_es=["y"],
                    stem_he="רְאִיתִי",
                    stem_morph="VERBO.QAL.SEQ.PERF.P1.COMMON.SG",
                    stem_es="he visto",
                    strongs="H7200",
                    suf_he="ה",
                    suf_morph="PRS.P3.F.SG",
                    suf_es="la",
                    respect_user_gloss=respect_user_gloss,
                )


def _fix_gen9_oshb_align(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Post-proceso cap. 9 — tokens rotos, orden, inserciones OSHB."""
    vrs = verse.get("verse", 0)
    pairs = verse.get("pairs", [])

    if vrs == 1:
        for p in pairs:
            p["he_words"] = [hw for hw in p.get("he_words", []) if hw.get("raw") != "L/HM"]
            hws = p.get("he_words") or []
            out: list[dict] = []
            for j, hw in enumerate(hws):
                out.append(hw)
                if hw.get("raw") in ("BN/YW", "W/BN/YW"):
                    nxt = hws[j + 1] if j + 1 < len(hws) else None
                    if nxt and nxt.get("raw") == "W/Y)MR":
                        out.append(_gen9_standalone_vav_hw())
            p["he_words"] = out

    if vrs == 3:
        for p in pairs:
            p["he_words"] = [
                hw for hw in p.get("he_words", [])
                if hw.get("raw") != "L/KM"
                or _gen5_he_key(hw) not in ("כם", "כ")
            ]

    if vrs == 7:
        for p in pairs:
            hws = p.get("he_words") or []
            if any(h.get("raw") == "B/)RC" for h in hws):
                p["he_words"] = [h for h in hws if h.get("raw") != "H/)RC"]
        cleaned: list[dict] = []
        for p in pairs:
            hws = p.get("he_words") or []
            if not hws:
                continue
            keep: list[dict] = []
            for hw in hws:
                raw = hw.get("raw") or ""
                if raw == "H/)RC" and not (hw.get("he_form") or "").strip():
                    continue
                if raw == "B/H" and not (hw.get("he_form") or "").strip():
                    continue
                if raw == "W/RBW" and not (hw.get("he_form") or "").strip():
                    _gen6_split_at_prs(
                        hw,
                        prefix_forms=["וּ"],
                        prefix_morphs=["CONJ"],
                        prefix_es=["y"],
                        stem_he="רְבוּ",
                        stem_morph="VERBO.QAL.IMPV.P2.M.PL",
                        stem_es="multiplicaos",
                        strongs="H7235",
                        respect_user_gloss=respect_user_gloss,
                    )
                keep.append(hw)
            if keep:
                p["he_words"] = keep
                cleaned.append(p)
        pairs[:] = cleaned

    if vrs == 5:
        for p in pairs:
            hws = p.get("he_words") or []
            out: list[dict] = []
            dr_count = 0
            for hw in hws:
                raw = hw.get("raw") or ""
                if raw == ")DR$/NW":
                    dr_count += 1
                    if dr_count == 2 and not (
                        out and out[-1].get("raw") == "=VAV"
                    ):
                        out.append(_gen9_standalone_vav_hw())
                out.append(hw)
            p["he_words"] = out

    if vrs == 9:
        for p in pairs:
            hws = p.get("he_words") or []
            out: list[dict] = []
            for hw in hws:
                if hw.get("raw") == "W/)T" and (hw.get("he_morph") or "") == "PREP":
                    _gen6_split_at_prs(
                        hw,
                        prefix_forms=["וְ"],
                        prefix_morphs=["CONJ"],
                        prefix_es=["y"],
                        stem_he="אֶת",
                        stem_morph="PART.OBJ.DIR",
                        stem_es="",
                        strongs="H853",
                        respect_user_gloss=respect_user_gloss,
                    )
                out.append(hw)
            p["he_words"] = out

    if vrs == 21:
        for p in pairs:
            hws = p.get("he_words") or []
            out: list[dict] = []
            for j, hw in enumerate(hws):
                out.append(hw)
                if hw.get("raw") == "B/TWK":
                    nxt = hws[j + 1] if j + 1 < len(hws) else None
                    if not nxt or nxt.get("raw") != "AHL/H":
                        out.append({
                            "raw": "AHL/H",
                            "he_form": "אָהֳלֹ",
                            "he_morph": "SUBS.M.SG.C",
                            "strongs": "H168",
                            "es": "tienda",
                            "es_source": "patch",
                            "prefix_forms": [],
                            "prefix_morphs": [],
                            "prefix_es": [],
                            "prs_suffix": {
                                "he_form": "ה",
                                "he_morph": "PRS.P3.M.SG",
                                "es": "su",
                            },
                        })
            p["he_words"] = out

    if vrs == 19:
        flat: list[dict] = []
        for p in pairs:
            flat.extend(p.get("he_words") or [])
        rebuilt: list[dict] = []
        for hw in flat:
            raw = hw.get("raw") or ""
            if raw in ("W/M)LH", "M/)LH"):
                if not (rebuilt and rebuilt[-1].get("raw") == "=VAV"):
                    rebuilt.append(_gen9_standalone_vav_hw())
                if raw == "W/M)LH":
                    rebuilt.append({
                        "raw": "M/)LH",
                        "prefix_forms": ["מֵ"],
                        "prefix_morphs": ["PREP"],
                        "prefix_es": ["de"],
                        "he_form": "אֵלֶּה",
                        "he_morph": "PRON.DEM.COMMON.PL",
                        "strongs": "H411",
                        "es": "estos",
                        "es_source": "patch",
                    })
                else:
                    rebuilt.append(hw)
            else:
                rebuilt.append(hw)
        pairs[:] = [_gen5_min_pair(h) for h in rebuilt]

    if vrs == 18:
        for p in pairs:
            for hw in p.get("he_words", []):
                if hw.get("raw") == ")BY":
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "אֲבִי"
                    hw["strongs"] = "H1"
                    hw["he_morph"] = "SUBS.M.SG.C"
                    _set_es_patch(hw, "padre de", respect_user=respect_user_gloss)
                    hw.pop("prs_suffix", None)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

    if vrs == 22:
        for p in pairs:
            hws = p.get("he_words") or []
            out: list[dict] = []
            for hw in hws:
                raw = hw.get("raw") or ""
                if raw == ")BY/W" and _gen5_he_key(hw) in ("ו", "וו"):
                    _gen6_split_at_prs(
                        hw,
                        stem_he="אָבִי",
                        stem_morph="SUBS.M.SG.C",
                        stem_es="padre",
                        strongs="H1",
                        suf_he="ו",
                        suf_morph="PRS.P3.M.SG",
                        suf_es="su",
                        respect_user_gloss=respect_user_gloss,
                    )
                elif raw == ")BY":
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "אֲבִי"
                    hw["strongs"] = "H1"
                    hw["he_morph"] = "SUBS.M.SG.C"
                    _set_es_patch(hw, "padre de", respect_user=respect_user_gloss)
                    hw.pop("prs_suffix", None)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"
                out.append(hw)
            p["he_words"] = out

    if vrs == 24:
        for p in pairs:
            hws = p.get("he_words") or []
            seen_ben = False
            out: list[dict] = []
            for hw in hws:
                raw = hw.get("raw") or ""
                if raw == "L/W":
                    continue
                if raw == "H/Q+N" and seen_ben:
                    continue
                if raw == "BN/W":
                    seen_ben = True
                out.append(hw)
            p["he_words"] = out

    if vrs in (26, 27):
        for p in pairs:
            p["he_words"] = [hw for hw in p.get("he_words", []) if hw.get("raw") != "L/MW"]

    if vrs in (28, 29):
        anchor_raw = "$L$" if vrs == 28 else "T$("
        api: int | None = None
        anchor_hw: dict | None = None
        for pi, p in enumerate(pairs):
            for hw in p.get("he_words") or []:
                if hw.get("raw") == anchor_raw:
                    api = pi
                    anchor_hw = hw
                    break
            if api is not None:
                break
        if api is not None and anchor_hw is not None:
            tail = [
                {
                    "raw": "M)WT",
                    "he_form": "מֵאוֹת",
                    "he_morph": "NUM.CARD.BOTH.PL.A",
                    "strongs": "H3967",
                    "es": "cientos",
                    "es_source": "patch",
                    "prefix_forms": [],
                    "prefix_morphs": [],
                    "prefix_es": [],
                },
                _gen5_shana_hw(),
                _gen9_standalone_vav_hw(),
                {
                    "raw": "XMSYM",
                    "he_form": "חֲמִשִּׁים",
                    "he_morph": "CBPA",
                    "strongs": "H2572",
                    "es": "cincuenta",
                    "es_source": "patch",
                    "prefix_forms": [],
                    "prefix_morphs": [],
                    "prefix_es": [],
                },
                _gen5_shana_hw(),
            ]
            new_pairs = pairs[:api] + [_gen5_min_pair(anchor_hw)]
            new_pairs.extend(_gen5_min_pair(h) for h in tail)
            if vrs == 29:
                for p in pairs[api + 1:]:
                    for hw in p.get("he_words") or []:
                        if hw.get("raw") == "W/YMT":
                            new_pairs.append(p)
                            break
            pairs[:] = new_pairs

    verse["pairs"] = [
        p for p in verse.get("pairs", [])
        if p.get("he_words")
        or (p.get("gr_unicode") or "").strip()
        or p.get("kind") == "heb_omit"
    ]


def _patch_gen9(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Parches estructurales Génesis cap. 9 — pacto, Noé, hijos."""
    vrs = verse.get("verse", 0)
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            raw = hw.get("raw", "")

            if raw == "L/NX":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["לְ"]
                hw["prefix_morphs"] = ["PREP"]
                hw["prefix_es"] = ["a"]
                hw["he_form"] = "נֹחַ"
                hw["strongs"] = "H5146"
                hw["he_morph"] = "NPROP"
                _set_es_patch(hw, "Noé", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw in ("BN/YW", "W/BN/YW"):
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=(["וּ"] if raw.startswith("W/") else None),
                    prefix_morphs=(["CONJ"] if raw.startswith("W/") else None),
                    prefix_es=(["y"] if raw.startswith("W/") else None),
                    stem_he="בָנָי",
                    stem_morph="SUBS.M.PL.C",
                    stem_es="hijos",
                    strongs="H1121",
                    suf_he="ו",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "W/MWR)/KM":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["וּ"],
                    prefix_morphs=["CONJ"],
                    prefix_es=["y"],
                    stem_he="מוֹרַאֲ",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="temor",
                    strongs="H4172",
                    suf_he="כֶם",
                    suf_morph="PRS.P2.M.PL",
                    suf_es="vuestro",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "W/XT/KM":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["וּ"],
                    prefix_morphs=["CONJ"],
                    prefix_es=["y"],
                    stem_he="חִתְּ",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="terror",
                    strongs="H2851",
                    suf_he="כֶם",
                    suf_morph="PRS.P2.M.PL",
                    suf_es="vuestro",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "B/YD/KM":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["בְּ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["en"],
                    stem_he="יֶד",
                    stem_morph="SUBS.BOTH.SG.C",
                    stem_es="mano",
                    strongs="H3027",
                    suf_he="כֶם",
                    suf_morph="PRS.P2.M.PL",
                    suf_es="vuestra",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")K":
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "אַךְ"
                hw["strongs"] = "H389"
                hw["he_morph"] = "PART.AFF"
                _set_es_patch(hw, "solamente", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "B/NP$/W":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["בְּ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["con"],
                    stem_he="נַפְשׁ",
                    stem_morph="SUBS.BOTH.SG.C",
                    stem_es="alma",
                    strongs="H5315",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "DM/KM":
                _gen6_split_at_prs(
                    hw,
                    stem_he="דִּמְ",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="sangre",
                    strongs="H1818",
                    suf_he="כֶם",
                    suf_morph="PRS.P2.M.PL",
                    suf_es="vuestra",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "DM/W":
                _gen6_split_at_prs(
                    hw,
                    stem_he="דָמ",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="sangre",
                    strongs="H1818",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "L/NP$T/YKM":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["לְ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["por"],
                    stem_he="נַפְשֹׁתֵי",
                    stem_morph="SUBS.BOTH.PL.C",
                    stem_es="vidas",
                    strongs="H5315",
                    suf_he="כֶם",
                    suf_morph="PRS.P2.M.PL",
                    suf_es="vuestras",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")DR$/NW":
                _gen6_split_at_prs(
                    hw,
                    stem_he="אֶדְרֹשׁ",
                    stem_morph="VERBO.QAL.IMPF.P1.COMMON.SG",
                    stem_es="demandaré",
                    strongs="H1875",
                    suf_he="נּוּ",
                    suf_morph="PRS.P1.COMMON.PL",
                    suf_es="lo",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "HN/NY":
                _gen6_split_at_prs(
                    hw,
                    stem_he="הִנְנִ",
                    stem_morph="INTJ",
                    stem_es="he aquí",
                    suf_he="י",
                    suf_morph="PRS.P1.COMMON.SG",
                    suf_es="",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "BRYT/Y":
                _gen6_split_at_prs(
                    hw,
                    stem_he="בְּרִית",
                    stem_morph="SUBS.F.SG.C",
                    stem_es="pacto",
                    strongs="H1285",
                    suf_he="י",
                    suf_morph="PRS.P1.COMMON.SG",
                    suf_es="mi",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")T/KM":
                _gen6_split_at_prs(
                    hw,
                    stem_he="אִתּ",
                    stem_morph="PREP",
                    stem_es="con",
                    strongs="H854",
                    suf_he="כֶם",
                    suf_morph="PRS.P2.M.PL",
                    suf_es="ustedes",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "ZR(/KM":
                _gen6_split_at_prs(
                    hw,
                    stem_he="זַרְע",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="descendencia",
                    strongs="H2233",
                    suf_he="כֶם",
                    suf_morph="PRS.P2.M.PL",
                    suf_es="vuestra",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")XR/YKM":
                _gen6_split_at_prs(
                    hw,
                    stem_he="אַחֲרֵי",
                    stem_morph="PREP",
                    stem_es="después",
                    strongs="H310",
                    suf_he="כֶם",
                    suf_morph="PRS.P2.M.PL",
                    suf_es="de ustedes",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "BYN/Y":
                _gen6_split_at_prs(
                    hw,
                    stem_he="בֵּינִ",
                    stem_morph="PREP",
                    stem_es="entre",
                    strongs="H996",
                    suf_he="י",
                    suf_morph="PRS.P1.COMMON.SG",
                    suf_es="mí",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "W/BYN/YKM":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["וּ"],
                    prefix_morphs=["CONJ"],
                    prefix_es=["y"],
                    stem_he="בֵינֵי",
                    stem_morph="PREP",
                    stem_es="entre",
                    strongs="H996",
                    suf_he="כֶם",
                    suf_morph="PRS.P2.M.PL",
                    suf_es="ustedes",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "W/BYN" and vrs in (12, 15):
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["וּ"]
                hw["prefix_morphs"] = ["CONJ"]
                hw["prefix_es"] = ["y"]
                hw["he_form"] = "בֵין"
                hw["strongs"] = "H996"
                hw["he_morph"] = "PREP"
                _set_es_patch(hw, "entre", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw in ("QST/Y", "Q$T/Y") and vrs == 13:
                _gen6_split_at_prs(
                    hw,
                    stem_he="קַשְׁת",
                    stem_morph="SUBS.F.SG.C",
                    stem_es="arco",
                    strongs="H7198",
                    suf_he="ִי",
                    suf_morph="PRS.P1.COMMON.SG",
                    suf_es="mi",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")T/W" and vrs == 8:
                _gen6_split_at_prs(
                    hw,
                    stem_he="אִתּ",
                    stem_morph="PREP",
                    stem_es="con",
                    strongs="H854",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="él",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")BY/W" and vrs == 22:
                _gen6_split_at_prs(
                    hw,
                    stem_he="אָבִי",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="padre",
                    strongs="H1",
                    suf_he="ו",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw in (")XY/W", ")X/YW", "L/)X/YW"):
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=(["לְ"] if raw == "L/)X/YW" else None),
                    prefix_morphs=(["PREP"] if raw == "L/)X/YW" else None),
                    prefix_es=(["a"] if raw == "L/)X/YW" else None),
                    stem_he=(
                        "אֶחָי"
                        if raw in (")X/YW", "L/)X/YW")
                        else "אָחִי"
                    ),
                    stem_morph=(
                        "SUBS.M.PL.C"
                        if raw in (")X/YW", "L/)X/YW")
                        else "SUBS.M.SG.C"
                    ),
                    stem_es=(
                        "hermanos"
                        if raw in (")X/YW", "L/)X/YW")
                        else "hermano"
                    ),
                    strongs="H251",
                    suf_he="ו",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "AHL/H" and vrs == 21:
                _gen6_split_at_prs(
                    hw,
                    stem_he="אָהֳלֹ",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="tienda",
                    strongs="H168",
                    suf_he="ה",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "B/(NN/Y" and vrs == 14:
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["בְּ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["en"],
                    stem_he="עַנְנִ",
                    stem_morph="VERBO.PIEL.INFC",
                    stem_es="nube",
                    strongs="H6042",
                    suf_he="י",
                    suf_morph="PRS.P1.COMMON.SG",
                    suf_es="",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "W/R)YTY/H" and vrs == 16:
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["וּ"],
                    prefix_morphs=["CONJ"],
                    prefix_es=["y"],
                    stem_he="רְאִיתִי",
                    stem_morph="VERBO.QAL.SEQ.PERF.P1.COMMON.SG",
                    stem_es="he visto",
                    strongs="H7200",
                    suf_he="ה",
                    suf_morph="PRS.P3.F.SG",
                    suf_es="la",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "$KM" and vrs == 23:
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "שְׁכֶם"
                hw["strongs"] = "H7926"
                hw["he_morph"] = "SUBS.M.SG.C"
                _set_es_patch(hw, "hombro", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "$N/YHM" and vrs == 23:
                _gen6_split_at_prs(
                    hw,
                    stem_he="שְׁנֵי",
                    stem_morph="NUM.CARD.M.DU.C",
                    stem_es="dos",
                    strongs="H8147",
                    suf_he="הֶם",
                    suf_morph="PRS.P3.M.PL",
                    suf_es="ellos",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")BY/HM":
                _gen6_split_at_prs(
                    hw,
                    stem_he="אֲבִי",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="padre",
                    strongs="H1",
                    suf_he="הֶם",
                    suf_morph="PRS.P3.M.PL",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "W/PN/YHM":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["וּ"],
                    prefix_morphs=["CONJ"],
                    prefix_es=["y"],
                    stem_he="פְנֵי",
                    stem_morph="SUBS.BOTH.PL.C",
                    stem_es="rostro",
                    strongs="H6440",
                    suf_he="הֶם",
                    suf_morph="PRS.P3.M.PL",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "M/YYN/W" and vrs == 24:
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["מִ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["de"],
                    stem_he="יֵינ",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="vino",
                    strongs="H3196",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "BN/W" and vrs == 24:
                _gen6_split_at_prs(
                    hw,
                    stem_he="בְּנ",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="hijo",
                    strongs="H1121",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "H/MBWL":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["הַ"]
                hw["prefix_morphs"] = ["ART"]
                hw["prefix_es"] = ["el"]
                hw["he_form"] = "מַבּוּל"
                hw["strongs"] = "H3999"
                hw["he_morph"] = "SUBS.M.SG.A"
                _set_es_patch(hw, "diluvio", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "H/TBH":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["הַ"]
                hw["prefix_morphs"] = ["ART"]
                hw["prefix_es"] = ["la"]
                hw["he_form"] = "תֵּבָה"
                hw["strongs"] = "H8392"
                hw["he_morph"] = "SUBS.F.SG.A"
                _set_es_patch(hw, "arca", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "H/)RC":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["הַ"]
                hw["prefix_morphs"] = ["ART"]
                hw["prefix_es"] = ["la"]
                hw["he_form"] = "אָרֶץ"
                hw["strongs"] = "H776"
                hw["he_morph"] = "SUBS.BOTH.SG.A"
                _set_es_patch(hw, "tierra", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "H/$MYM":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["הַ"]
                hw["prefix_morphs"] = ["ART"]
                hw["prefix_es"] = ["los"]
                hw["he_form"] = "שָּׁמַיִם"
                hw["strongs"] = "H8064"
                hw["he_morph"] = "SUBS.M.PL.A"
                _set_es_patch(hw, "cielos", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "H/YM":
                _clear_hw_prefix_slots(hw)
                hw["prefix_forms"] = ["הַ"]
                hw["prefix_morphs"] = ["ART"]
                hw["prefix_es"] = ["el"]
                hw["he_form"] = "יָּם"
                hw["strongs"] = "H3220"
                hw["he_morph"] = "SUBS.M.SG.A"
                _set_es_patch(hw, "mar", respect_user=respect_user_gloss)
                hw.pop("prs_suffix", None)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

    _fix_gen9_oshb_align(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if not (
                (hw.get("raw") or "").endswith("}")
                or (
                    hw.get("es_source") == "patch_meta"
                    and not _strip_niqqud(hw.get("he_form") or "")
                )
            )
        ]
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if (hw.get("he_form") or "").strip()
            or (hw.get("prefix_forms") or [])
            or (hw.get("prs_suffix") or {}).get("he_form")
            or hw.get("raw") in ("=L/MYN/W", "=L/MYN/HW")
        ]

    verse["pairs"] = [
        p for p in verse.get("pairs", [])
        if p.get("he_words")
        or (p.get("gr_unicode") or "").strip()
        or p.get("kind") == "heb_omit"
    ]

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _gen5_preserve_fused_ot(hw, respect_user_gloss=respect_user_gloss)
            _merge_prs_reading_gloss(hw)

    _gen9_reapply_oshb_splits(verse, respect_user_gloss=respect_user_gloss)

    _fix_gen9_lxx_align(verse)
    _sanitize_catss_pairs(verse)


def _gen10_reapply_oshb_splits(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Reaplica splits cap. 10 tras merge PRS / preserve_fused_ot."""
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            raw = hw.get("raw", "")

            if raw == "B/)RCT/M":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["בְּ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["en"],
                    stem_he="אַרְצֹת",
                    stem_morph="SUBS.BOTH.PL.C",
                    stem_es="tierras",
                    strongs="H776",
                    suf_he="ם",
                    suf_morph="PRS.P3.M.PL",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "L/M$PXT/M":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["לְ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["según"],
                    stem_he="מִשְׁפְּחֹת",
                    stem_morph="SUBS.F.PL.C",
                    stem_es="familias",
                    strongs="H4940",
                    suf_he="ם",
                    suf_morph="PRS.P3.M.PL",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "L/L$N/W":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["לִ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["según"],
                    stem_he="לְשֹׁנ",
                    stem_morph="SUBS.BOTH.SG.C",
                    stem_es="lengua",
                    strongs="H3956",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "L/L$NT/M":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["לִ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["según"],
                    stem_he="לְשֹׁנֹת",
                    stem_morph="SUBS.BOTH.PL.C",
                    stem_es="lenguas",
                    strongs="H3956",
                    suf_he="ם",
                    suf_morph="PRS.P3.M.PL",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw in ("B/GW/YHM", "L/GW/YHM"):
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=(["בְּ"] if raw.startswith("B/") else ["לְ"]),
                    prefix_morphs=["PREP"],
                    prefix_es=(["en"] if raw.startswith("B/") else ["para"]),
                    stem_he="גּוֹי",
                    stem_morph="SUBS.M.PL.C",
                    stem_es="nación",
                    strongs="H1471",
                    suf_he="הֶם",
                    suf_morph="PRS.P3.M.PL",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "L/TWLDT/M":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["לְ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["según"],
                    stem_he="תוֹלְדֹת",
                    stem_morph="SUBS.F.PL.C",
                    stem_es="generaciones",
                    strongs="H8435",
                    suf_he="ם",
                    suf_morph="PRS.P3.M.PL",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "MMLKT/W":
                _gen6_split_at_prs(
                    hw,
                    stem_he="מַמְלַכְת",
                    stem_morph="SUBS.F.SG.C",
                    stem_es="reino",
                    strongs="H4467",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "BKR/W":
                _gen6_split_at_prs(
                    hw,
                    stem_he="בְּכֹר",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="primogénito",
                    strongs="H1060",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")XY/W":
                _gen6_split_at_prs(
                    hw,
                    stem_he="אָחִי",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="hermano",
                    strongs="H251",
                    suf_he="ו",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "B/YM/YW":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["בְ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["en"],
                    stem_he="יָמָי",
                    stem_morph="SUBS.M.PL.C",
                    stem_es="días",
                    strongs="H3117",
                    suf_he="ו",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "B)/KH":
                _gen6_split_at_prs(
                    hw,
                    stem_he="בֹּאֲ",
                    stem_morph="VERBO.QAL.INFC",
                    stem_es="entrando",
                    strongs="H935",
                    suf_he="כָה",
                    suf_morph="PRS.P2.M.SG",
                    suf_es="",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "GRR/H":
                _gen6_split_at_prs(
                    hw,
                    stem_he="גְרָר",
                    stem_morph="NPROP",
                    stem_es="Gerar",
                    strongs="H1647",
                    suf_he="ה",
                    suf_morph="SUF.DIR.HE",
                    suf_es="",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "SDM/H":
                _gen6_split_at_prs(
                    hw,
                    stem_he="סְדֹמָ",
                    stem_morph="NPROP",
                    stem_es="Sodoma",
                    strongs="H5467",
                    suf_he="ה",
                    suf_morph="SUF.DIR.HE",
                    suf_es="",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "SPR/H":
                _gen6_split_at_prs(
                    hw,
                    stem_he="סְפָר",
                    stem_morph="NPROP",
                    stem_es="Sephar",
                    strongs="H5611",
                    suf_he="ה",
                    suf_morph="SUF.DIR.HE",
                    suf_es="",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "MW$B/M":
                _gen6_split_at_prs(
                    hw,
                    stem_he="מוֹשָׁב",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="habitación",
                    strongs="H4186",
                    suf_he="ם",
                    suf_morph="PRS.P3.M.PL",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )


def _fix_gen10_oshb_align(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Post-proceso cap. 10 — orden, tokens rotos, inserciones OSHB."""
    vrs = verse.get("verse", 0)
    pairs = verse.get("pairs", [])

    if vrs == 1:
        for p in pairs:
            gr_u = (p.get("gr_unicode") or "").strip()
            gr_a = (p.get("gr") or "").upper()
            if "αὐτοῖς" in gr_u or "AU)TOI=S" in gr_a:
                p["kind"] = "gk_add"
                p["he"] = ""
                p["he_unicode"] = ""
                p["he_stem_unicode"] = ""
                p["prefixes"] = ""
                p["he_words"] = []
                if gr_u:
                    p["he_words"] = [
                        {
                            "raw": "GKADD",
                            "gr_word": gr_u,
                            "gr_source": "patch_lxx",
                            "es_source": "patch_meta",
                        }
                    ]
                continue
            p["he_words"] = [
                hw for hw in p.get("he_words", []) if hw.get("raw") != "L/HM"
            ]

    if vrs in (19, 30):
        for p in pairs:
            gr_u = (p.get("gr_unicode") or "").strip()
            if _norm_gr_token(gr_u) != "εως":
                continue
            if (p.get("he_unicode") or "").strip():
                continue
            if any(
                (hw.get("he_form") or "").strip()
                and (hw.get("raw") or "") not in ("GKADD", "=<LXX>")
                for hw in (p.get("he_words") or [])
            ):
                continue
            p["kind"] = "gk_add"
            p["he"] = ""
            p["he_unicode"] = ""
            p["he_stem_unicode"] = ""
            p["prefixes"] = ""
            p["he_words"] = [
                {
                    "raw": "GKADD",
                    "gr_word": gr_u,
                    "gr_source": "patch_lxx",
                    "es_source": "patch_meta",
                }
            ]

    if vrs == 6:
        for p in pairs:
            for hw in p.get("he_words", []):
                if hw.get("raw") == "W/KN(N":
                    _clear_hw_prefix_slots(hw)
                    hw["prefix_forms"] = ["וּ"]
                    hw["prefix_morphs"] = ["CONJ"]
                    hw["prefix_es"] = ["y"]
                    hw["he_form"] = "כְנָעַן"
                    hw["strongs"] = "H3667"
                    hw["he_morph"] = "NPROP"
                    _set_es_patch(hw, "Canaán", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

    if vrs == 11:
        for p in pairs:
            for hw in p.get("he_words", []):
                raw = hw.get("raw") or ""
                if raw == "RXBT":
                    hw["he_form"] = "רְחֹבֹת"
                    hw["strongs"] = "H7343"
                    hw["he_morph"] = "NPROP"
                    _set_es_patch(hw, "Rehobot", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"
                elif raw == "(YR":
                    hw["he_form"] = "עִיר"
                    hw["he_morph"] = "NPROP"
                    hw["strongs"] = "H5892"
                    _set_es_patch(hw, "Ir", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"
                elif raw == "H/)RC":
                    hw["strongs"] = "H776"
                    hw["he_morph"] = "SUBS.BOTH.SG.A"
                    pfx_e = list(hw.get("prefix_es") or ["la"])
                    if pfx_e:
                        pfx_e[0] = "la"
                    else:
                        pfx_e = ["la"]
                    hw["prefix_es"] = pfx_e
                    _set_es_patch(hw, "tierra", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"
                elif raw == "H/HW)":
                    _set_es_patch(hw, "ella", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

    if vrs == 12:
        for p in pairs:
            for hw in p.get("he_words", []):
                if hw.get("raw") == "H/GDLH":
                    hw["strongs"] = "H1419"
                    hw["he_morph"] = "AFSA"
                    hw["prefix_es"] = ["la"]
                    _set_es_patch(hw, "grande", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

    if vrs == 7:
        for p in pairs:
            for hw in p.get("he_words", []):
                if hw.get("raw") == "W/BNY":
                    pfx = hw.get("prefix_forms") or []
                    if pfx and _gen5_he_key({"he_form": pfx[0]}) not in ("ו", "וו"):
                        _clear_hw_prefix_slots(hw)
                        hw["prefix_forms"] = ["וּ"]
                        hw["prefix_morphs"] = ["CONJ"]
                        hw["prefix_es"] = ["y"]
                        hw["he_form"] = "בְנֵי"
                        hw["strongs"] = "H1121"
                        hw["he_morph"] = "SUBS.M.PL.C"
                        _set_es_patch(hw, "hijos", respect_user=respect_user_gloss)
                        if not (respect_user_gloss and _has_user_gloss(hw)):
                            hw["es_source"] = "patch"

    if vrs == 12:
        for p in pairs:
            hws = p.get("he_words") or []
            if any(h.get("raw") == "DSM" for h in hws):
                p["he_words"] = [h for h in hws if h.get("raw") != "DSM"]

    if vrs == 21:
        for p in pairs:
            for hw in p.get("he_words", []):
                if hw.get("raw") == ")BY":
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "אֲבִי"
                    hw["strongs"] = "H1"
                    hw["he_morph"] = "SUBS.M.SG.C"
                    _set_es_patch(hw, "padre de", respect_user=respect_user_gloss)
                    hw.pop("prs_suffix", None)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"
                elif hw.get("raw") == ")XY":
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "אֲחִי"
                    hw["strongs"] = "H251"
                    hw["he_morph"] = "SUBS.M.SG.C"
                    _set_es_patch(hw, "hermano de", respect_user=respect_user_gloss)
                    hw.pop("prs_suffix", None)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

    if vrs == 25:
        for p in pairs:
            hws = p.get("he_words") or []
            out: list[dict] = []
            seen_achi = False
            for hw in hws:
                raw = hw.get("raw") or ""
                if raw == ")XY/W":
                    seen_achi = True
                if seen_achi and raw == "YQ+N" and not (
                    out and out[-1].get("raw") == "=VAV"
                ):
                    out.append(_gen9_standalone_vav_hw())
                out.append(hw)
            p["he_words"] = out

    if vrs == 27:
        for p in pairs:
            hws = p.get("he_words") or []
            p["he_words"] = [h for h in hws if h.get("raw") != ")YZL"]
        for p in pairs:
            hws = p.get("he_words") or []
            if len(hws) == 1 and hws[0].get("raw") == "DQLH":
                dqlh = hws[0]
                p["he_words"] = [
                    {
                        "raw": "W/)T",
                        "prefix_forms": ["וְ"],
                        "prefix_morphs": ["CONJ"],
                        "prefix_es": ["y"],
                        "he_form": "אֶת",
                        "he_morph": "PART.OBJ.DIR",
                        "strongs": "H853",
                        "es": "",
                        "es_source": "patch",
                    },
                    dqlh,
                ]

    verse["pairs"] = [
        p for p in verse.get("pairs", [])
        if p.get("he_words")
        or (p.get("gr_unicode") or "").strip()
        or p.get("kind") == "heb_omit"
    ]


def _fix_gen10_es_glosses(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Correcciones de glosas / metadatos español cap. 10."""
    vrs = verse.get("verse", 0)
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            raw = hw.get("raw") or ""

            if vrs == 5 and raw == "H/GWYM":
                _set_es_patch(hw, "naciones", respect_user=respect_user_gloss)

            elif vrs == 8 and raw == "HXL":
                _set_es_patch(hw, "comenzó", respect_user=respect_user_gloss)

            elif vrs == 9:
                if raw == "(L":
                    hw["strongs"] = "H5921"
                    hw["he_morph"] = "PREP"
                    _set_es_patch(hw, "por", respect_user=respect_user_gloss)
                elif raw == "KN":
                    hw["strongs"] = "H3651"
                    hw["he_morph"] = "PART.DEM"
                    _set_es_patch(hw, "así", respect_user=respect_user_gloss)

            elif vrs == 14 and raw == "M/$M":
                pfx_e = list(hw.get("prefix_es") or [])
                if pfx_e:
                    pfx_e[0] = "de"
                    hw["prefix_es"] = pfx_e

            elif vrs == 19 and raw == "GBWL":
                _set_es_patch(hw, "término", respect_user=respect_user_gloss)

            elif vrs in (21, 25) and raw == "YLD":
                _set_es_patch(hw, "nació", respect_user=respect_user_gloss)


def _patch_gen10(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Parches estructurales Génesis cap. 10 — genealogías, PRS."""
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            raw = hw.get("raw", "")

            if raw == "B/)RCT/M":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["בְּ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["en"],
                    stem_he="אַרְצֹת",
                    stem_morph="SUBS.BOTH.PL.C",
                    stem_es="tierras",
                    strongs="H776",
                    suf_he="ם",
                    suf_morph="PRS.P3.M.PL",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "L/M$PXT/M":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["לְ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["según"],
                    stem_he="מִשְׁפְּחֹת",
                    stem_morph="SUBS.F.PL.C",
                    stem_es="familias",
                    strongs="H4940",
                    suf_he="ם",
                    suf_morph="PRS.P3.M.PL",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "L/L$N/W":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["לִ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["según"],
                    stem_he="לְשֹׁנ",
                    stem_morph="SUBS.BOTH.SG.C",
                    stem_es="lengua",
                    strongs="H3956",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "L/L$NT/M":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["לִ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["según"],
                    stem_he="לְשֹׁנֹת",
                    stem_morph="SUBS.BOTH.PL.C",
                    stem_es="lenguas",
                    strongs="H3956",
                    suf_he="ם",
                    suf_morph="PRS.P3.M.PL",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw in ("B/GW/YHM", "L/GW/YHM"):
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=(["בְּ"] if raw.startswith("B/") else ["לְ"]),
                    prefix_morphs=["PREP"],
                    prefix_es=(["en"] if raw.startswith("B/") else ["para"]),
                    stem_he="גּוֹי",
                    stem_morph="SUBS.M.PL.C",
                    stem_es="nación",
                    strongs="H1471",
                    suf_he="הֶם",
                    suf_morph="PRS.P3.M.PL",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "L/TWLDT/M":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["לְ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["según"],
                    stem_he="תוֹלְדֹת",
                    stem_morph="SUBS.F.PL.C",
                    stem_es="generaciones",
                    strongs="H8435",
                    suf_he="ם",
                    suf_morph="PRS.P3.M.PL",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "MMLKT/W":
                _gen6_split_at_prs(
                    hw,
                    stem_he="מַמְלַכְת",
                    stem_morph="SUBS.F.SG.C",
                    stem_es="reino",
                    strongs="H4467",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "BKR/W":
                _gen6_split_at_prs(
                    hw,
                    stem_he="בְּכֹר",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="primogénito",
                    strongs="H1060",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")XY/W":
                _gen6_split_at_prs(
                    hw,
                    stem_he="אָחִי",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="hermano",
                    strongs="H251",
                    suf_he="ו",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "B/YM/YW":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["בְ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["en"],
                    stem_he="יָמָי",
                    stem_morph="SUBS.M.PL.C",
                    stem_es="días",
                    strongs="H3117",
                    suf_he="ו",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "B)/KH":
                _gen6_split_at_prs(
                    hw,
                    stem_he="בֹּאֲ",
                    stem_morph="VERBO.QAL.INFC",
                    stem_es="entrando",
                    strongs="H935",
                    suf_he="כָה",
                    suf_morph="PRS.P2.M.SG",
                    suf_es="",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "GRR/H":
                _gen6_split_at_prs(
                    hw,
                    stem_he="גְרָר",
                    stem_morph="NPROP",
                    stem_es="Gerar",
                    strongs="H1647",
                    suf_he="ה",
                    suf_morph="SUF.DIR.HE",
                    suf_es="",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "SDM/H":
                _gen6_split_at_prs(
                    hw,
                    stem_he="סְדֹמָ",
                    stem_morph="NPROP",
                    stem_es="Sodoma",
                    strongs="H5467",
                    suf_he="ה",
                    suf_morph="SUF.DIR.HE",
                    suf_es="",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "SPR/H":
                _gen6_split_at_prs(
                    hw,
                    stem_he="סְפָר",
                    stem_morph="NPROP",
                    stem_es="Sephar",
                    strongs="H5611",
                    suf_he="ה",
                    suf_morph="SUF.DIR.HE",
                    suf_es="",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "MW$B/M":
                _gen6_split_at_prs(
                    hw,
                    stem_he="מוֹשָׁב",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="habitación",
                    strongs="H4186",
                    suf_he="ם",
                    suf_morph="PRS.P3.M.PL",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

    _fix_gen10_oshb_align(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen10_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if not (
                (hw.get("raw") or "").endswith("}")
                or (
                    hw.get("es_source") == "patch_meta"
                    and not _strip_niqqud(hw.get("he_form") or "")
                )
            )
        ]
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if (hw.get("he_form") or "").strip()
            or (hw.get("prefix_forms") or [])
            or (hw.get("prs_suffix") or {}).get("he_form")
            or hw.get("raw") in ("=L/MYN/W", "=L/MYN/HW", "=VAV")
        ]

    verse["pairs"] = [
        p for p in verse.get("pairs", [])
        if p.get("he_words")
        or (p.get("gr_unicode") or "").strip()
        or p.get("kind") == "heb_omit"
    ]

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _gen5_preserve_fused_ot(hw, respect_user_gloss=respect_user_gloss)
            _merge_prs_reading_gloss(hw)

    _gen10_reapply_oshb_splits(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen10_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _merge_prs_reading_gloss(hw)
            _drop_redundant_prs_suffix(hw)

    _fix_gen10_lxx_align(verse)
    _sanitize_catss_pairs(verse)

def _gen11_split_haba(hw: dict, *, respect_user_gloss: bool = False) -> None:
    """הָבָ + ה (SUF.PARAG.HE) — ven / vamos."""
    _gen6_split_at_prs(
        hw,
        stem_he="הָבָ",
        stem_morph="VERBO.QAL.IMPV.P2.M.SG",
        stem_es="ven",
        strongs="H3051",
        suf_he="ה",
        suf_morph="SUF.PARAG.HE",
        suf_es="",
        respect_user_gloss=respect_user_gloss,
    )


def _gen11_apply_genealogy_raw(hw: dict, *, respect_user_gloss: bool = False) -> None:
    """Splits compartidos con cap. 5 — genealogías 11:10–32."""
    raw = hw.get("raw", "")

    if raw == "HWLYD/W":
        _clear_hw_prefix_slots(hw)
        hw["he_form"] = "הוֹלִיד"
        hw["strongs"] = "H3205"
        hw["he_morph"] = "VERBO.HIF.INFC"
        _set_es_patch(hw, "engendrar", respect_user=respect_user_gloss)
        _attach_prs_suffix(hw, "וֹ", "PRS.P3.M.SG", "lo")
        if not (respect_user_gloss and _has_user_gloss(hw)):
            hw["es_source"] = "patch"

    elif raw == "W/YWLD":
        _gen5_ensure_w_prefix(hw)

    elif raw == "W/)RB(":
        _clear_hw_prefix_slots(hw)
        hw["prefix_forms"] = ["וְ"]
        hw["prefix_morphs"] = ["CONJ"]
        hw["prefix_es"] = ["y"]
        hw["he_form"] = "אַרְבַּע"
        hw["strongs"] = "H702"
        hw["he_morph"] = "CFSA"
        _set_es_patch(hw, "cuatro", respect_user=respect_user_gloss)
        hw.pop("prs_suffix", None)
        if not (respect_user_gloss and _has_user_gloss(hw)):
            hw["es_source"] = "patch"

    elif raw == "M)WT":
        he_key = _gen5_he_key(hw)
        if he_key in _GEN5_NUM_ES or not he_key or he_key == "ו":
            _clear_hw_prefix_slots(hw)
            hw["he_form"] = "מֵאוֹת"
            hw["strongs"] = "H3967"
            hw["he_morph"] = "NUM.CARD.BOTH.PL.A"
            _set_es_patch(hw, "cientos", respect_user=respect_user_gloss)
            if not (respect_user_gloss and _has_user_gloss(hw)):
                hw["es_source"] = "patch"

    elif raw == "$NH":
        if _gen5_he_key(hw).startswith("בנ"):
            return
        if not _gen5_is_shana_hw(hw):
            hw["he_form"] = "שָׁנָה"
            hw["strongs"] = "H8141"
            hw["he_morph"] = "SUBS.F.SG.A"
            _set_es_patch(hw, "años", respect_user=respect_user_gloss)
            if not (respect_user_gloss and _has_user_gloss(hw)):
                hw["es_source"] = "patch"

    elif raw in ("$NYM", "T$(", "$L$YM", "XM$", "$TYM", "$B(", "(&RH", "W/M)TYM"):
        he_key = _gen5_he_key(hw)
        if raw.startswith("W/") and he_key == "ו":
            _clear_hw_prefix_slots(hw)
            hw["prefix_forms"] = ["וּ"]
            hw["prefix_morphs"] = ["CONJ"]
            hw["prefix_es"] = ["y"]
        if he_key in _GEN5_NUM_ES:
            _set_es_patch(hw, _GEN5_NUM_ES[he_key], respect_user=respect_user_gloss)
            if he_key in ("מאת", "מאות"):
                hw["strongs"] = "H3967"
            elif not hw.get("strongs"):
                hw["strongs"] = "H8141"
        if not (respect_user_gloss and _has_user_gloss(hw)):
            hw["es_source"] = "patch"

    elif raw == "W/M)T":
        he_key = _gen5_he_key(hw)
        if he_key in ("מת", "מאת") or (hw.get("he_morph") or "") == "CBSC":
            _clear_hw_prefix_slots(hw)
            hw["prefix_forms"] = ["וּ"]
            hw["prefix_morphs"] = ["CONJ"]
            hw["prefix_es"] = ["y"]
            hw["he_form"] = "מְאַת"
            hw["strongs"] = "H3967"
            hw["he_morph"] = "CBSC"
            _set_es_patch(hw, "ciento", respect_user=respect_user_gloss)
            hw.pop("prs_suffix", None)
            if not (respect_user_gloss and _has_user_gloss(hw)):
                hw["es_source"] = "patch"


def _gen11_reapply_oshb_splits(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Reaplica splits cap. 11 tras merge PRS / Pass 16."""
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            raw = hw.get("raw", "")

            if raw in ("HBH", "HBA"):
                _gen11_split_haba(hw, respect_user_gloss=respect_user_gloss)

            elif raw == "B/NS(/M":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["בְּ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["en"],
                    stem_he="נָסְעָ",
                    stem_morph="VERBO.QAL.INFC",
                    stem_es="viajando",
                    strongs="H5265",
                    suf_he="ם",
                    suf_morph="PRS.P3.M.PL",
                    suf_es="los",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "R(/HW":
                _gen6_split_at_prs(
                    hw,
                    stem_he="רֵעֵ",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="compañero",
                    strongs="H7453",
                    suf_he="הוּ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw in ("L/KLL/M", "L/KL/M"):
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["לְ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["para"],
                    stem_he="כֻלָּ",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="todos",
                    strongs="H3605",
                    suf_he="ם",
                    suf_morph="PRS.P3.M.PL",
                    suf_es="ellos",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "HXLM":
                _gen6_split_at_prs(
                    hw,
                    stem_he="הַחִלָּ",
                    stem_morph="VERBO.HIF.INFC",
                    stem_es="empezar",
                    strongs="H2490",
                    suf_he="ם",
                    suf_morph="PRS.P3.M.PL",
                    suf_es="los",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "&PT/M":
                _gen6_split_at_prs(
                    hw,
                    stem_he="שְׂפָת",
                    stem_morph="SUBS.F.SG.C",
                    stem_es="labio",
                    strongs="H8193",
                    suf_he="ם",
                    suf_morph="PRS.P3.M.PL",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "W/R)$/W":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["וְ"],
                    prefix_morphs=["CONJ"],
                    prefix_es=["y"],
                    stem_he="רֹאשׁ",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="cumbre",
                    strongs="H7218",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "BN/W":
                _gen6_split_at_prs(
                    hw,
                    stem_he="בְּנ",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="hijo",
                    strongs="H1121",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "KLT/W":
                _gen6_split_at_prs(
                    hw,
                    stem_he="כַּלָּת",
                    stem_morph="SUBS.F.SG.C",
                    stem_es="nuera",
                    strongs="H3618",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")RC/H":
                _gen6_split_at_prs(
                    hw,
                    stem_he="אַרְצָ",
                    stem_morph="SUBS.BOTH.SG.C",
                    stem_es="tierra",
                    strongs="H776",
                    suf_he="ה",
                    suf_morph="SUF.DIR.HE",
                    suf_es="",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw in ("HPYT$/M", "HPYC/M"):
                _gen6_split_at_prs(
                    hw,
                    stem_he="הֱפִיצָ",
                    stem_morph="VERBO.HIF.PERF.P3.M.SG",
                    stem_es="esparció",
                    strongs="H6327",
                    suf_he="ם",
                    suf_morph="PRS.P3.M.PL",
                    suf_es="los",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "W/H/XMR":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["וְ", "הַ"],
                    prefix_morphs=["CONJ", "ART"],
                    prefix_es=["y", "el"],
                    stem_he="חֵמָר",
                    stem_morph="SUBS.M.SG.A",
                    stem_es="asfalto",
                    strongs="H2564",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "$M/H":
                _gen6_split_at_prs(
                    hw,
                    stem_he="שְׁמָ",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="nombre",
                    strongs="H8034",
                    suf_he="הּ",
                    suf_morph="PRS.P3.F.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "M/WLDT/W":
                _gen6_split_at_prs(
                    hw,
                    stem_he="מוֹלַדְת",
                    stem_morph="SUBS.F.SG.C",
                    stem_es="nacimiento",
                    strongs="H4138",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")T/M":
                _gen6_split_at_prs(
                    hw,
                    stem_he="אֹת",
                    stem_morph="PART.OBJ.DIR",
                    stem_es="",
                    strongs="H853",
                    suf_he="ם",
                    suf_morph="PRS.P3.M.PL",
                    suf_es="los",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "W/)BY/W":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["וְ"],
                    prefix_morphs=["CONJ"],
                    prefix_es=["y"],
                    stem_he="אֲבִי",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="padre de",
                    strongs="H1",
                    suf_he="ו",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            _gen11_apply_genealogy_raw(hw, respect_user_gloss=respect_user_gloss)

def _fix_gen11_oshb_align(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Post-proceso cap. 11 — orden, tokens rotos, inserciones OSHB."""
    vrs = verse.get("verse", 0)
    pairs = verse.get("pairs", [])

    if vrs == 3:
        for p in pairs:
            hws = p.get("he_words") or []
            out: list[dict] = []
            for hw in hws:
                raw = hw.get("raw") or ""
                if raw == "L/HM" and _gen5_he_key(hw) in ("הם", "hem"):
                    continue
                elif raw == "L/HM" and not (hw.get("he_form") or "").strip():
                    continue
                elif raw == "W/H/XMR":
                    _gen6_split_at_prs(
                        hw,
                        prefix_forms=["וְ", "הַ"],
                        prefix_morphs=["CONJ", "ART"],
                        prefix_es=["y", "el"],
                        stem_he="חֵמָר",
                        stem_morph="SUBS.M.SG.A",
                        stem_es="asfalto",
                        strongs="H2564",
                        respect_user_gloss=respect_user_gloss,
                    )
                    out.append(hw)
                elif raw == "L/XMR":
                    _clear_hw_prefix_slots(hw)
                    hw["prefix_forms"] = ["לַ"]
                    hw["prefix_morphs"] = ["PREP"]
                    hw["prefix_es"] = ["para"]
                    hw["he_form"] = "חֹמֶר"
                    hw["strongs"] = "H2563"
                    hw["he_morph"] = "SUBS.M.SG.A"
                    _set_es_patch(hw, "cal", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"
                    out.append(hw)
                else:
                    out.append(hw)
            p["he_words"] = out

    if vrs == 4:
        for p in pairs:
            hws = p.get("he_words") or []
            out: list[dict] = []
            for hw in hws:
                raw = hw.get("raw") or ""
                if raw == "L/NW":
                    continue
                if raw == "W/R)$/W":
                    _gen6_split_at_prs(
                        hw,
                        prefix_forms=["וְ"],
                        prefix_morphs=["CONJ"],
                        prefix_es=["y"],
                        stem_he="רֹאשׁ",
                        stem_morph="SUBS.M.SG.C",
                        stem_es="cumbre",
                        strongs="H7218",
                        suf_he="וֹ",
                        suf_morph="PRS.P3.M.SG",
                        suf_es="su",
                        respect_user_gloss=respect_user_gloss,
                    )
                elif raw == "B/$MYM":
                    _clear_hw_prefix_slots(hw)
                    hw["prefix_forms"] = ["בַ"]
                    hw["prefix_morphs"] = ["PREP"]
                    hw["prefix_es"] = ["en"]
                    hw["he_form"] = "שָּׁמַיִם"
                    hw["strongs"] = "H8064"
                    hw["he_morph"] = "SUBS.M.DU.A"
                    _set_es_patch(hw, "cielo", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"
                elif raw == "NPWC":
                    hw["he_form"] = "נָפוּץ"
                    hw["strongs"] = "H6327"
                    hw["he_morph"] = "VERBO.QAL.IMPF.P1.COMMON.PL"
                    _set_es_patch(hw, "seamos esparcidos", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"
                elif raw == "PNY":
                    _clear_hw_prefix_slots(hw)
                    hw["prefix_forms"] = ["עַל"]
                    hw["prefix_morphs"] = ["PREP"]
                    hw["prefix_es"] = ["sobre"]
                    hw["he_form"] = "פְּנֵי"
                    hw["strongs"] = "H6440"
                    hw["he_morph"] = "SUBS.BOTH.PL.C"
                    _set_es_patch(hw, "rostro", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"
                out.append(hw)
            p["he_words"] = out

    if vrs == 6:
        for p in pairs:
            hws = p.get("he_words") or []
            out: list[dict] = []
            for hw in hws:
                raw = hw.get("raw") or ""
                if raw == "M/HM" and _gen5_he_key(hw) in ("הם", "hem"):
                    continue
                if raw in ("L/KLL/M", "L/KL/M"):
                    _gen6_split_at_prs(
                        hw,
                        prefix_forms=["לְ"],
                        prefix_morphs=["PREP"],
                        prefix_es=["para"],
                        stem_he="כֻלָּ",
                        stem_morph="SUBS.M.SG.C",
                        stem_es="todos",
                        strongs="H3605",
                        suf_he="ם",
                        suf_morph="PRS.P3.M.PL",
                        suf_es="ellos",
                        respect_user_gloss=respect_user_gloss,
                    )
                elif raw == "HXLM":
                    _gen6_split_at_prs(
                        hw,
                        stem_he="הַחִלָּ",
                        stem_morph="VERBO.HIF.INFC",
                        stem_es="empezar",
                        strongs="H2490",
                        suf_he="ם",
                        suf_morph="PRS.P3.M.PL",
                        suf_es="los",
                        respect_user_gloss=respect_user_gloss,
                    )
                out.append(hw)
            p["he_words"] = out

    if vrs == 9:
        for p in pairs:
            for hw in p.get("he_words", []):
                raw = hw.get("raw") or ""
                if raw in ("HPYC/M", "HPYT$/M"):
                    _gen6_split_at_prs(
                        hw,
                        stem_he="הֱפִיצָ",
                        stem_morph="VERBO.HIF.PERF.P3.M.SG",
                        stem_es="esparció",
                        strongs="H6327",
                        suf_he="ם",
                        suf_morph="PRS.P3.M.PL",
                        suf_es="los",
                        respect_user_gloss=respect_user_gloss,
                    )

    if vrs == 7:
        for p in pairs:
            hws = p.get("he_words") or []
            out: list[dict] = []
            for hw in hws:
                raw = hw.get("raw") or ""
                if raw == "&PT/M":
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "שְׂפָת"
                    hw["strongs"] = "H8193"
                    hw["he_morph"] = "SUBS.F.SG.C"
                    _set_es_patch(hw, "labio", respect_user=respect_user_gloss)
                    _attach_prs_suffix(hw, "ם", "PRS.P3.M.PL", "su")
                    out.append(hw)
                elif raw == "R(/HW" and (hw.get("prefix_forms") or []):
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "רֵעֵ"
                    hw["strongs"] = "H7453"
                    hw["he_morph"] = "SUBS.M.SG.C"
                    _set_es_patch(hw, "compañero", respect_user=respect_user_gloss)
                    _attach_prs_suffix(hw, "הוּ", "PRS.P3.M.SG", "su")
                    out.append(hw)
                elif raw == ")Y$" and out and out[-1].get("raw") == ")Y$":
                    continue
                else:
                    out.append(hw)
            p["he_words"] = out

    if vrs == 8:
        for p in pairs:
            for hw in p.get("he_words", []):
                if hw.get("raw") == ")T/M" and (hw.get("prefix_forms") or []):
                    _gen6_split_at_prs(
                        hw,
                        stem_he="אֹת",
                        stem_morph="PART.OBJ.DIR",
                        stem_es="",
                        strongs="H853",
                        suf_he="ם",
                        suf_morph="PRS.P3.M.PL",
                        suf_es="los",
                        respect_user_gloss=respect_user_gloss,
                    )

    if vrs == 13:
        for p in pairs:
            hws = p.get("he_words") or []
            for hw in hws:
                raw = hw.get("raw") or ""
                if raw == "W/YWLD" and (hw.get("prefix_forms") or [""])[0] == "וּ":
                    hw["prefix_forms"] = ["וַ"]
                    hw["prefix_morphs"] = ["CONJ"]
                    hw["prefix_es"] = ["y"]
            for hw in hws:
                if hw.get("raw") == "$NH" and _gen5_he_key(hw).startswith("בנ"):
                    _gen5_repair_shana_pair(p)
                    break
        _fix_gen5_after_maot(verse)

    if vrs == 25:
        i = 0
        while i < len(pairs):
            p = pairs[i]
            hws = p.get("he_words") or []
            raws = {hw.get("raw") for hw in hws}
            need_shana_after = (
                "(&RH" in raws
                or any(_gen5_he_key(hw) == "עשרה" for hw in hws)
                or "W/M)T" in raws
            )
            if need_shana_after:
                ni = i + 1
                if ni < len(pairs):
                    nhws = pairs[ni].get("he_words") or []
                    if not nhws or not _gen5_is_shana_hw(nhws[0]):
                        pairs.insert(ni, _gen5_min_pair(_gen5_shana_hw()))
                        i += 1
                else:
                    pairs.append(_gen5_min_pair(_gen5_shana_hw()))
            i += 1

    if vrs == 28:
        for p in pairs:
            hws = [h for h in (p.get("he_words") or []) if h.get("raw") != "=VAV"]
            out: list[dict] = []
            for hw in hws:
                raw = hw.get("raw") or ""
                if raw == ")BY/W":
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "אֲבִי"
                    hw["strongs"] = "H1"
                    hw["he_morph"] = "SUBS.M.SG.C"
                    _set_es_patch(hw, "padre de", respect_user=respect_user_gloss)
                    hw.pop("prs_suffix", None)
                    out.append(hw)
                    out.append(_gen9_standalone_vav_hw())
                elif raw == "MWLDT/W":
                    _gen6_split_at_prs(
                        hw,
                        stem_he="מוֹלַדְתּ",
                        stem_morph="SUBS.F.SG.C",
                        stem_es="nacimiento",
                        strongs="H4138",
                        suf_he="וֹ",
                        suf_morph="PRS.P3.M.SG",
                        suf_es="su",
                        respect_user_gloss=respect_user_gloss,
                    )
                    out.append(hw)
                else:
                    out.append(hw)
            p["he_words"] = out

    if vrs == 29:
        for p in pairs:
            hws = p.get("he_words") or []
            p["he_words"] = [h for h in hws if h.get("raw") != "L/HM"]
            for hw in p.get("he_words", []):
                raw = hw.get("raw") or ""
                if raw == ")BY":
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "אֲבִי"
                    hw["strongs"] = "H1"
                    hw["he_morph"] = "SUBS.M.SG.C"
                    _set_es_patch(hw, "padre de", respect_user=respect_user_gloss)
                    hw.pop("prs_suffix", None)
                elif raw == "W/)BY":
                    _clear_hw_prefix_slots(hw)
                    hw["prefix_forms"] = ["ו"]
                    hw["prefix_morphs"] = ["CONJ"]
                    hw["prefix_es"] = ["y"]
                    hw["he_form"] = "אֲבִי"
                    hw["strongs"] = "H1"
                    hw["he_morph"] = "SUBS.M.SG.C"
                    _set_es_patch(hw, "padre de", respect_user=respect_user_gloss)
                    hw.pop("prs_suffix", None)

    if vrs == 31:
        for p in pairs:
            hws = p.get("he_words") or []
            out: list[dict] = []
            seen_knn = False
            for hw in hws:
                raw = hw.get("raw") or ""
                if raw == "K&DYM" and _gen5_he_key(hw).startswith("כנע"):
                    continue
                if raw == "KN(N" and seen_knn:
                    continue
                if raw == "KN(N":
                    seen_knn = True
                if raw == ")RC/H" and (hw.get("prefix_forms") or []):
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "אַרְצָ"
                    hw["strongs"] = "H776"
                    hw["he_morph"] = "SUBS.BOTH.SG.C"
                    _set_es_patch(hw, "tierra", respect_user=respect_user_gloss)
                    _attach_prs_suffix(hw, "ה", "SUF.DIR.HE", "")
                elif raw == ")T/M" and (hw.get("he_morph") or "").startswith("PREP"):
                    _clear_hw_prefix_slots(hw)
                    hw["prefix_forms"] = ["אִ"]
                    hw["prefix_morphs"] = ["PREP"]
                    hw["prefix_es"] = ["con"]
                    hw["he_form"] = "תָּ"
                    hw["strongs"] = "H854"
                    hw["he_morph"] = "PREP"
                    _set_es_patch(hw, "", respect_user=respect_user_gloss)
                    _attach_prs_suffix(hw, "ם", "PRS.P3.M.PL", "ellos")
                out.append(hw)
            p["he_words"] = out

    if vrs >= 10:
        _fix_gen5_w_prefixes(verse)
        _fix_gen5_after_maot(verse)
        _fix_gen5_empty_pairs(verse)

    verse["pairs"] = [
        p for p in verse.get("pairs", [])
        if p.get("he_words")
        or (p.get("gr_unicode") or "").strip()
        or p.get("kind") == "heb_omit"
    ]


def _fix_gen11_es_glosses(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Correcciones de glosas / metadatos español cap. 11."""
    vrs = verse.get("verse", 0)
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            raw = hw.get("raw") or ""

            if vrs == 3 and raw == "L/XMR":
                _set_es_patch(hw, "cal", respect_user=respect_user_gloss)

            elif vrs == 6:
                if raw == "W/&PH":
                    _set_es_patch(hw, "lengua", respect_user=respect_user_gloss)
                elif raw == ")XT":
                    _set_es_patch(hw, "una", respect_user=respect_user_gloss)
                elif raw == "L)":
                    hw["strongs"] = "H3808"
                    hw["he_morph"] = "NEG"
                    _set_es_patch(hw, "no", respect_user=respect_user_gloss)
                elif raw == "L/(&WT":
                    _set_es_patch(hw, "hacer", respect_user=respect_user_gloss)
                elif raw == "HXLM":
                    _set_es_patch(hw, "empezar", respect_user=respect_user_gloss)
                elif raw == "YZMW":
                    _set_es_patch(hw, "intenten", respect_user=respect_user_gloss)

            elif vrs == 7:
                if raw == "NRDH":
                    _set_es_patch(hw, "descendamos", respect_user=respect_user_gloss)
                elif raw == "Y$M(W":
                    hw["strongs"] = "H8085"
                    hw["he_morph"] = "VERBO.QAL.IMPF.P3.M.PL"
                    _set_es_patch(hw, "oyan", respect_user=respect_user_gloss)
                elif raw == "L)":
                    hw["strongs"] = "H3808"
                    hw["he_morph"] = "NEG"
                    _set_es_patch(hw, "no", respect_user=respect_user_gloss)
                elif raw == ")Y$":
                    hw["strongs"] = "H376"
                    hw["he_morph"] = "SUBS.M.SG.A"
                    _set_es_patch(hw, "hombre", respect_user=respect_user_gloss)
                elif raw == "&PT":
                    hw["strongs"] = "H8193"
                    hw["he_morph"] = "SUBS.F.SG.C"
                    _set_es_patch(hw, "labio", respect_user=respect_user_gloss)

            elif vrs == 9:
                if raw == "(L":
                    hw["strongs"] = "H5921"
                    hw["he_morph"] = "PREP"
                    _set_es_patch(hw, "por", respect_user=respect_user_gloss)
                elif raw == "KN":
                    hw["strongs"] = "H3651"
                    hw["he_morph"] = "PART.DEM"
                    _set_es_patch(hw, "tanto", respect_user=respect_user_gloss)

            elif vrs == 28 and raw == "PNY":
                hw["strongs"] = "H6440"
                hw["he_morph"] = "SUBS.BOTH.PL.C"
                _set_es_patch(hw, "rostro", respect_user=respect_user_gloss)

            elif vrs == 29 and raw in (")BY", "W/)BY"):
                _set_es_patch(hw, "padre de", respect_user=respect_user_gloss)

            elif vrs == 28 and raw == "=VAV":
                _set_es_patch(hw, "y", respect_user=respect_user_gloss)

    _fix_gen5_numeric_glosses(verse, respect_user_gloss=respect_user_gloss)


def _patch_gen11(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Parches estructurales Génesis cap. 11 — Torre de Babel + genealogías."""
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            raw = hw.get("raw", "")

            if raw in ("HBH", "HBA"):
                _gen11_split_haba(hw, respect_user_gloss=respect_user_gloss)

            elif raw == "B/NS(/M":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["בְּ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["en"],
                    stem_he="נָסְעָ",
                    stem_morph="VERBO.QAL.INFC",
                    stem_es="viajando",
                    strongs="H5265",
                    suf_he="ם",
                    suf_morph="PRS.P3.M.PL",
                    suf_es="los",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "R(/HW":
                _gen6_split_at_prs(
                    hw,
                    stem_he="רֵעֵ",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="compañero",
                    strongs="H7453",
                    suf_he="הוּ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw in ("L/KLL/M", "L/KL/M"):
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["לְ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["para"],
                    stem_he="כֻלָּ",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="todos",
                    strongs="H3605",
                    suf_he="ם",
                    suf_morph="PRS.P3.M.PL",
                    suf_es="ellos",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "HXLM":
                _gen6_split_at_prs(
                    hw,
                    stem_he="הַחִלָּ",
                    stem_morph="VERBO.HIF.INFC",
                    stem_es="empezar",
                    strongs="H2490",
                    suf_he="ם",
                    suf_morph="PRS.P3.M.PL",
                    suf_es="los",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "&PT/M":
                _gen6_split_at_prs(
                    hw,
                    stem_he="שְׂפָת",
                    stem_morph="SUBS.F.SG.C",
                    stem_es="labio",
                    strongs="H8193",
                    suf_he="ם",
                    suf_morph="PRS.P3.M.PL",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "W/R)$/W":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["וְ"],
                    prefix_morphs=["CONJ"],
                    prefix_es=["y"],
                    stem_he="רֹאשׁ",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="cumbre",
                    strongs="H7218",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "BN/W":
                _gen6_split_at_prs(
                    hw,
                    stem_he="בְּנ",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="hijo",
                    strongs="H1121",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "KLT/W":
                _gen6_split_at_prs(
                    hw,
                    stem_he="כַּלָּת",
                    stem_morph="SUBS.F.SG.C",
                    stem_es="nuera",
                    strongs="H3618",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")RC/H":
                _gen6_split_at_prs(
                    hw,
                    stem_he="אַרְצָ",
                    stem_morph="SUBS.BOTH.SG.C",
                    stem_es="tierra",
                    strongs="H776",
                    suf_he="ה",
                    suf_morph="SUF.DIR.HE",
                    suf_es="",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw in ("HPYT$/M", "HPYC/M"):
                _gen6_split_at_prs(
                    hw,
                    stem_he="הֱפִיצָ",
                    stem_morph="VERBO.HIF.PERF.P3.M.SG",
                    stem_es="esparció",
                    strongs="H6327",
                    suf_he="ם",
                    suf_morph="PRS.P3.M.PL",
                    suf_es="los",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "W/H/XMR":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["וְ", "הַ"],
                    prefix_morphs=["CONJ", "ART"],
                    prefix_es=["y", "el"],
                    stem_he="חֵמָר",
                    stem_morph="SUBS.M.SG.A",
                    stem_es="asfalto",
                    strongs="H2564",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "$M/H":
                _gen6_split_at_prs(
                    hw,
                    stem_he="שְׁמָ",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="nombre",
                    strongs="H8034",
                    suf_he="הּ",
                    suf_morph="PRS.P3.F.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "M/WLDT/W":
                _gen6_split_at_prs(
                    hw,
                    stem_he="מוֹלַדְת",
                    stem_morph="SUBS.F.SG.C",
                    stem_es="nacimiento",
                    strongs="H4138",
                    suf_he="וֹ",
                    suf_morph="PRS.P3.M.SG",
                    suf_es="su",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == ")T/M":
                _gen6_split_at_prs(
                    hw,
                    stem_he="אֹת",
                    stem_morph="PART.OBJ.DIR",
                    stem_es="",
                    strongs="H853",
                    suf_he="ם",
                    suf_morph="PRS.P3.M.PL",
                    suf_es="los",
                    respect_user_gloss=respect_user_gloss,
                )

            _gen11_apply_genealogy_raw(hw, respect_user_gloss=respect_user_gloss)

    _fix_gen11_oshb_align(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen11_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if not (
                (hw.get("raw") or "").endswith("}")
                or (
                    hw.get("es_source") == "patch_meta"
                    and not _strip_niqqud(hw.get("he_form") or "")
                )
            )
        ]
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if (hw.get("he_form") or "").strip()
            or (hw.get("prefix_forms") or [])
            or (hw.get("prs_suffix") or {}).get("he_form")
            or hw.get("raw") in ("=L/MYN/W", "=L/MYN/HW", "=VAV")
        ]

    verse["pairs"] = [
        p for p in verse.get("pairs", [])
        if p.get("he_words")
        or (p.get("gr_unicode") or "").strip()
        or p.get("kind") == "heb_omit"
    ]

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _gen5_preserve_fused_ot(hw, respect_user_gloss=respect_user_gloss)
            _merge_prs_reading_gloss(hw)

    _gen11_reapply_oshb_splits(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen11_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _merge_prs_reading_gloss(hw)
            _drop_redundant_prs_suffix(hw)

    _fix_gen11_lxx_align(verse)
    _sanitize_catss_pairs(verse)


# Génesis cap. 12 — Abram (plantilla cap. 11)
def _gen12_apply_prs_splits(hw: dict, *, respect_user_gloss: bool = False) -> None:
    """Splits PRS / compuestos frecuentes cap. 12."""
    raw = hw.get("raw", "")

    if raw == ")T/W":
        _gen6_split_at_prs(
            hw,
            stem_he="אֹת",
            stem_morph="PART.OBJ.DIR",
            stem_es="",
            strongs="H853",
            suf_he="וֹ",
            suf_morph="PRS.P3.M.SG",
            suf_es="lo",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == ")T/M":
        _gen6_split_at_prs(
            hw,
            stem_he="אֹת",
            stem_morph="PART.OBJ.DIR",
            stem_es="",
            strongs="H853",
            suf_he="ם",
            suf_morph="PRS.P3.M.PL",
            suf_es="los",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "L/K":
        _gen6_split_at_prs(
            hw,
            stem_he="אַרְצְ",
            stem_morph="SUBS.BOTH.SG.C",
            stem_es="tierra",
            strongs="H776",
            suf_he="ךָ",
            suf_morph="PRS.P2.M.SG",
            suf_es="tu",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == ")BY/K":
        _gen6_split_at_prs(
            hw,
            stem_he="אֲבִי",
            stem_morph="SUBS.M.SG.C",
            stem_es="padre de",
            strongs="H1",
            suf_he="ךָ",
            suf_morph="PRS.P2.M.SG",
            suf_es="tu",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == ")R)/K":
        _gen6_split_at_prs(
            hw,
            stem_he="אַרְאֶ",
            stem_morph="VERBO.HIF.IMPF.P1.COMMON.SG",
            stem_es="te mostraré",
            strongs="H7200",
            suf_he="ךָ",
            suf_morph="PRS.P2.M.SG",
            suf_es="te",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "M/)RC/K":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["מֵ"],
            prefix_morphs=["PREP"],
            prefix_es=["de"],
            stem_he="אַרְצְ",
            stem_morph="SUBS.BOTH.SG.C",
            stem_es="tierra",
            strongs="H776",
            suf_he="ךָ",
            suf_morph="PRS.P2.M.SG",
            suf_es="tu",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "W/M/MWLDT/K":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["וּ", "מִ"],
            prefix_morphs=["CONJ", "PREP"],
            prefix_es=["y", "de"],
            stem_he="מוֹלַדְתּ",
            stem_morph="SUBS.F.SG.C",
            stem_es="nacimiento",
            strongs="H4138",
            suf_he="ךָ",
            suf_morph="PRS.P2.M.SG",
            suf_es="tu",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "W/M/BYT":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["וּ", "מִ"],
            prefix_morphs=["CONJ", "PREP"],
            prefix_es=["y", "de"],
            stem_he="בֵּית",
            stem_morph="SUBS.M.SG.C",
            stem_es="casa",
            strongs="H1004",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "W/)BRK/K":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["וַ"],
            prefix_morphs=["CONJ"],
            prefix_es=["y"],
            stem_he="אֲבָרֶכְ",
            stem_morph="VERBO.PIEL.IMPF.P1.COMMON.SG",
            stem_es="bendeciré",
            strongs="H1288",
            suf_he="ךָ",
            suf_morph="PRS.P2.M.SG",
            suf_es="te",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "$M/K":
        _gen6_split_at_prs(
            hw,
            stem_he="שְׁמֶ",
            stem_morph="SUBS.M.SG.C",
            stem_es="nombre",
            strongs="H8034",
            suf_he="ךָ",
            suf_morph="PRS.P2.M.SG",
            suf_es="tu",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "B/K":
        _clear_hw_prefix_slots(hw)
        hw["he_form"] = "ךָ"
        hw["strongs"] = ""
        hw["he_morph"] = "PRS.P2.M.SG"
        _set_es_patch(hw, "te", respect_user=respect_user_gloss)
        hw.pop("prs_suffix", None)
        if not (respect_user_gloss and _has_user_gloss(hw)):
            hw["es_source"] = "patch"

    elif raw == "W/)BRKH":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["וַ"],
            prefix_morphs=["CONJ"],
            prefix_es=["y"],
            stem_he="אֲבָרֲכָה",
            stem_morph="VERBO.PIEL.IMPF.P1.COMMON.SG",
            stem_es="bendeciré",
            strongs="H1288",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "W/)(&/K":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["וְ"],
            prefix_morphs=["CONJ"],
            prefix_es=["y"],
            stem_he="אֶעֶשׂ",
            stem_morph="VERBO.QAL.IMPF.P1.COMMON.SG",
            stem_es="haré",
            strongs="H6213",
            suf_he="ךָ",
            suf_morph="PRS.P2.M.SG",
            suf_es="te",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "M/BRK/YK":
        _gen6_split_at_prs(
            hw,
            stem_he="מְבָרְכֶי",
            stem_morph="VERBO.PIEL.PTCA.M.PL.C",
            stem_es="a los que te bendicen",
            strongs="H1288",
            suf_he="ךָ",
            suf_morph="PRS.P2.M.SG",
            suf_es="",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "))R":
        _clear_hw_prefix_slots(hw)
        hw["he_form"] = "אָאֹר"
        hw["strongs"] = "H779"
        hw["he_morph"] = "VERBO.QAL.IMPF.P1.COMMON.SG"
        _set_es_patch(hw, "maldeciré", respect_user=respect_user_gloss)
        hw.pop("prs_suffix", None)
        if not (respect_user_gloss and _has_user_gloss(hw)):
            hw["es_source"] = "patch"

    elif raw == ")L/YW":
        _gen6_split_at_prs(
            hw,
            stem_he="אֵלַי",
            stem_morph="PREP",
            stem_es="a",
            strongs="H413",
            suf_he="וֹ",
            suf_morph="PRS.P3.M.SG",
            suf_es="él",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "W/$B(YM":
        _clear_hw_prefix_slots(hw)
        hw["prefix_forms"] = ["וְ"]
        hw["prefix_morphs"] = ["CONJ"]
        hw["prefix_es"] = ["y"]
        hw["he_form"] = "שִׁבְעִים"
        hw["strongs"] = "H7657"
        hw["he_morph"] = "CBPA"
        _set_es_patch(hw, "setenta", respect_user=respect_user_gloss)
        hw.pop("prs_suffix", None)
        if not (respect_user_gloss and _has_user_gloss(hw)):
            hw["es_source"] = "patch"

    elif raw == "B/C)T/W":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["בְ"],
            prefix_morphs=["PREP"],
            prefix_es=["en"],
            stem_he="צֵאת",
            stem_morph="VERBO.QAL.INFC",
            stem_es="salir",
            strongs="H3318",
            suf_he="וֹ",
            suf_morph="PRS.P3.M.SG",
            suf_es="su",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "XM$":
        _clear_hw_prefix_slots(hw)
        hw["he_form"] = "חָמֵשׁ"
        hw["strongs"] = "H2568"
        hw["he_morph"] = "NUM.CARD.F.SG.A"
        _set_es_patch(hw, "cinco", respect_user=respect_user_gloss)
        hw.pop("prs_suffix", None)
        if not (respect_user_gloss and _has_user_gloss(hw)):
            hw["es_source"] = "patch"

    elif raw == "RKW$/M":
        _gen6_split_at_prs(
            hw,
            stem_he="רְכוּשׁ",
            stem_morph="SUBS.M.SG.C",
            stem_es="bienes",
            strongs="H7399",
            suf_he="ם",
            suf_morph="PRS.P3.M.PL",
            suf_es="su",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == ")XY/W":
        _gen6_split_at_prs(
            hw,
            stem_he="אָחִי",
            stem_morph="SUBS.M.SG.C",
            stem_es="hermano de",
            strongs="H251",
            suf_he="וֹ",
            suf_morph="PRS.P3.M.SG",
            suf_es="su",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "W/H/(Y":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["וְ", "הָ"],
            prefix_morphs=["CONJ", "ART"],
            prefix_es=["y", "la"],
            stem_he="עַי",
            stem_morph="NPROP",
            stem_es="Ai",
            strongs="H5857",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "AHL/H":
        _gen6_split_at_prs(
            hw,
            stem_he="אָהֳלֹ",
            stem_morph="SUBS.M.SG.C",
            stem_es="tienda",
            strongs="H168",
            suf_he="ה",
            suf_morph="PRS.P3.M.SG",
            suf_es="su",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == ")$T/W":
        _clear_hw_prefix_slots(hw)
        hw["he_form"] = "אִשְׁתּ"
        hw["strongs"] = "H802"
        hw["he_morph"] = "SUBS.F.SG.C"
        _set_es_patch(hw, "mujer", respect_user=respect_user_gloss)
        _attach_prs_suffix(hw, "וֹ", "PRS.P3.M.SG", "su")
        if not (respect_user_gloss and _has_user_gloss(hw)):
            hw["es_source"] = "patch"

    elif raw == ")T/Y":
        _gen6_split_at_prs(
            hw,
            stem_he="אֹת",
            stem_morph="PART.OBJ.DIR",
            stem_es="",
            strongs="H853",
            suf_he="י",
            suf_morph="PRS.P1.COMMON.SG",
            suf_es="me",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "W/)T/K":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["וְ"],
            prefix_morphs=["CONJ"],
            prefix_es=["y"],
            stem_he="אֹת",
            stem_morph="PART.OBJ.DIR",
            stem_es="",
            strongs="H853",
            suf_he="ךָ",
            suf_morph="PRS.P2.F.SG",
            suf_es="te",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "$NYM":
        _clear_hw_prefix_slots(hw)
        hw["he_form"] = "שָׁנִים"
        hw["strongs"] = "H8141"
        hw["he_morph"] = "SUBS.F.PL.A"
        _set_es_patch(hw, "años", respect_user=respect_user_gloss)
        hw.pop("prs_suffix", None)
        if not (respect_user_gloss and _has_user_gloss(hw)):
            hw["es_source"] = "patch"

    elif raw == ")XT/Y":
        _gen6_split_at_prs(
            hw,
            stem_he="אֲחֹתִ",
            stem_morph="SUBS.F.SG.C",
            stem_es="hermana",
            strongs="H269",
            suf_he="י",
            suf_morph="PRS.P1.COMMON.SG",
            suf_es="mi",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "L/M(N":
        _clear_hw_prefix_slots(hw)
        hw["he_form"] = "לְמַעַן"
        hw["strongs"] = "H4616"
        hw["he_morph"] = "PREP"
        _set_es_patch(hw, "a fin de que", respect_user=respect_user_gloss)
        hw.pop("prs_suffix", None)
        if not (respect_user_gloss and _has_user_gloss(hw)):
            hw["es_source"] = "patch"

    elif raw == "(L/YW":
        _gen6_split_at_prs(
            hw,
            stem_he="עָלָי",
            stem_morph="PREP",
            stem_es="sobre",
            strongs="H5921",
            suf_he="וֹ",
            suf_morph="PRS.P3.M.SG",
            suf_es="él",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "W/)QX":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["וָ"],
            prefix_morphs=["CONJ"],
            prefix_es=["y"],
            stem_he="אֶקַּח",
            stem_morph="VERBO.QAL.WAYYIQT.P1.COMMON.SG",
            stem_es="tomé",
            strongs="H3947",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "NP$/Y":
        _gen6_split_at_prs(
            hw,
            stem_he="נַפְשִׁ",
            stem_morph="SUBS.BOTH.SG.C",
            stem_es="alma",
            strongs="H5315",
            suf_he="י",
            suf_morph="PRS.P1.COMMON.SG",
            suf_es="mi",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "M/YM" and (hw.get("prefix_forms") or [""])[0] in ("וְ", "ו"):
        _clear_hw_prefix_slots(hw)
        hw["prefix_forms"] = ["מִ"]
        hw["prefix_morphs"] = ["PREP"]
        hw["prefix_es"] = ["de"]
        hw["he_form"] = "יָּם"
        hw["strongs"] = "H3220"
        hw["he_morph"] = "SUBS.M.SG.A"
        _set_es_patch(hw, "mar", respect_user=respect_user_gloss)
        if not (respect_user_gloss and _has_user_gloss(hw)):
            hw["es_source"] = "patch"

    elif raw == "W/MQLL/K":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["וּ"],
            prefix_morphs=["CONJ"],
            prefix_es=["y"],
            stem_he="מְקַלֶּלְ",
            stem_morph="VERBO.PIEL.PTCA.M.SG.C",
            stem_es="al que te maldice",
            strongs="H7043",
            suf_he="ךָ",
            suf_morph="PRS.P2.M.SG",
            suf_es="",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw in ("$NH", "W/M)T", "W/M)TYM"):
        _gen11_apply_genealogy_raw(hw, respect_user_gloss=respect_user_gloss)

    elif raw == ")RC/H":
        _gen6_split_at_prs(
            hw,
            stem_he="אַרְצָ",
            stem_morph="SUBS.BOTH.SG.C",
            stem_es="tierra",
            strongs="H776",
            suf_he="ה",
            suf_morph="SUF.DIR.HE",
            suf_es="",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "L/ZR(/K":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["לְ"],
            prefix_morphs=["PREP"],
            prefix_es=["a"],
            stem_he="זַרְעֲ",
            stem_morph="SUBS.M.SG.C",
            stem_es="simiente",
            strongs="H2233",
            suf_he="ךָ",
            suf_morph="PRS.P2.M.SG",
            suf_es="tu",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "H/)RC":
        _clear_hw_prefix_slots(hw)
        hw["prefix_forms"] = ["הַ"]
        hw["prefix_morphs"] = ["ART"]
        hw["prefix_es"] = ["la"]
        hw["he_form"] = "אָרֶץ"
        hw["strongs"] = "H776"
        hw["he_morph"] = "SUBS.BOTH.SG.A"
        _set_es_patch(hw, "tierra", respect_user=respect_user_gloss)
        hw.pop("prs_suffix", None)
        if not (respect_user_gloss and _has_user_gloss(hw)):
            hw["es_source"] = "patch"

    elif raw == "H/HR/H":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["הָ"],
            prefix_morphs=["ART"],
            prefix_es=["el"],
            stem_he="הָרָ",
            stem_morph="SUBS.M.SG.A",
            stem_es="monte",
            strongs="H2022",
            suf_he="ה",
            suf_morph="SUF.DIR.HE",
            suf_es="",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "H/NGB/H":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["הַ"],
            prefix_morphs=["ART"],
            prefix_es=["el"],
            stem_he="נֶגֶב",
            stem_morph="SUBS.M.SG.A",
            stem_es="sur",
            strongs="H5045",
            suf_he="ה",
            suf_morph="SUF.DIR.HE",
            suf_es="",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "MCRYM/H":
        _gen6_split_at_prs(
            hw,
            stem_he="מִצְרָיְמָ",
            stem_morph="NPROP",
            stem_es="Egipto",
            strongs="H4714",
            suf_he="ה",
            suf_morph="SUF.DIR.HE",
            suf_es="",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "BN/W":
        _gen6_split_at_prs(
            hw,
            stem_he="בְּנ",
            stem_morph="SUBS.M.SG.C",
            stem_es="hijo",
            strongs="H1121",
            suf_he="וֹ",
            suf_morph="PRS.P3.M.SG",
            suf_es="su",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "KLT/W":
        _gen6_split_at_prs(
            hw,
            stem_he="כַּלָּת",
            stem_morph="SUBS.F.SG.C",
            stem_es="nuera",
            strongs="H3618",
            suf_he="וֹ",
            suf_morph="PRS.P3.M.SG",
            suf_es="su",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw in ("W/)T", "W/)T/M"):
        _gen6_split_at_prs(
            hw,
            prefix_forms=["וְ"],
            prefix_morphs=["CONJ"],
            prefix_es=["y"],
            stem_he="אֶת",
            stem_morph="PART.OBJ.DIR",
            stem_es="",
            strongs="H853",
            suf_he=("ם" if raw.endswith("/M") else "וֹ"),
            suf_morph=("PRS.P3.M.PL" if raw.endswith("/M") else "PRS.P3.M.SG"),
            suf_es=("los" if raw.endswith("/M") else "lo"),
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == ")T/K":
        he_key = _gen5_he_key(hw)
        if he_key.startswith("את") or he_key in ("", "ך", "כ"):
            _gen6_split_at_prs(
                hw,
                stem_he="אֹת",
                stem_morph="PART.OBJ.DIR",
                stem_es="",
                strongs="H853",
                suf_he="ךָ",
                suf_morph="PRS.P2.F.SG",
                suf_es="te",
                respect_user_gloss=respect_user_gloss,
            )
        else:
            _gen6_split_at_prs(
                hw,
                stem_he="אִתּ",
                stem_morph="PREP",
                stem_es="con",
                strongs="H854",
                suf_he="וֹ",
                suf_morph="PRS.P3.M.SG",
                suf_es="él",
                respect_user_gloss=respect_user_gloss,
            )

    elif raw == "DRK/W":
        _gen6_split_at_prs(
            hw,
            stem_he="דַּרְכּ",
            stem_morph="SUBS.BOTH.SG.C",
            stem_es="camino",
            strongs="H1870",
            suf_he="וֹ",
            suf_morph="PRS.P3.M.SG",
            suf_es="su",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw in ("$NH", "W/M)T", "W/M)TYM"):
        _gen11_apply_genealogy_raw(hw, respect_user_gloss=respect_user_gloss)


def _gen12_tent_hw(*, respect_user_gloss: bool = False) -> dict:
    """אָהֳלֹ + ה — tienda suya (12:8)."""
    hw: dict = {
        "raw": "AHL/H",
        "he_form": "אָהֳלֹ",
        "he_morph": "SUBS.M.SG.C",
        "strongs": "H168",
        "es": "tienda",
        "es_source": "patch",
        "prefix_forms": [],
        "prefix_morphs": [],
        "prefix_es": [],
        "prs_suffix": {
            "he_form": "ה",
            "he_morph": "PRS.P3.M.SG",
            "es": "su",
        },
    }
    if respect_user_gloss:
        hw.pop("es_source", None)
    return hw


def _gen12_miyyam_hw(*, respect_user_gloss: bool = False) -> dict:
    """מִ + יָּם — al oeste (12:8)."""
    hw: dict = {
        "raw": "M/YM",
        "prefix_forms": ["מִ"],
        "prefix_morphs": ["PREP"],
        "prefix_es": ["de"],
        "he_form": "יָּם",
        "he_morph": "SUBS.M.SG.A",
        "strongs": "H3220",
        "es": "mar",
        "es_source": "patch",
    }
    if respect_user_gloss:
        hw.pop("es_source", None)
    return hw


def _gen12_bethel_pair(
    *,
    respect_user_gloss: bool = False,
    byt_form: str | None = None,
    el_form: str | None = None,
) -> dict:
    """בֵּית־ + אֵל — Betel (12:8, 13:3; maqaf trailing en BYT)."""
    return {
        "he_words": [
            {
                "raw": "BYT",
                "he_form": byt_form or "בֵּֽית\u05be",
                "he_morph": "NPROP",
                "strongs": "H1008",
                "es": "Betel",
                "es_source": "patch",
                "prefix_forms": [],
                "prefix_morphs": [],
                "prefix_es": [],
            },
            {
                "raw": ")L",
                "he_form": el_form or "אֵל",
                "he_morph": "NPROP",
                "strongs": "H410",
                "es": "El",
                "es_source": "patch",
                "prefix_forms": [],
                "prefix_morphs": [],
                "prefix_es": [],
            },
        ],
    }


def _gen12_repair_isht_ka_hw(hw: dict, *, respect_user_gloss: bool = False) -> None:
    """אִשְׁתּ + ךָ — evita כפל tras merge PRS (12:18–19)."""
    _clear_hw_prefix_slots(hw)
    hw["he_form"] = "אִשְׁתּ"
    hw["strongs"] = "H802"
    hw["he_morph"] = "SUBS.F.SG.C"
    _set_es_patch(hw, "mujer", respect_user=respect_user_gloss)
    _attach_prs_suffix(hw, "ךָ", "PRS.P2.M.SG", "tu")
    _drop_redundant_prs_suffix(hw)
    if not (respect_user_gloss and _has_user_gloss(hw)):
        hw["es_source"] = "patch"


def _gen12_reapply_oshb_splits(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Reaplica splits cap. 12 tras merge PRS / Pass 16."""
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            _gen12_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)


def _fix_gen12_oshb_align(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Post-proceso cap. 12 — orden, tokens rotos, inserciones OSHB (B2)."""
    vrs = verse.get("verse", 0)
    pairs = verse.get("pairs", [])

    _fix_gen5_w_prefixes(verse)
    _fix_gen5_after_maot(verse)

    if vrs == 1:
        pairs[:] = [
            p for p in pairs
            if not (
                len(p.get("he_words") or []) == 1
                and (p["he_words"][0].get("raw") or "") == "L/K"
            )
        ]

    if vrs == 3:
        for p in pairs:
            hws = p.get("he_words") or []
            p["he_words"] = [h for h in hws if (h.get("raw") or "") != "B/K"]

    if vrs == 4:
        for p in pairs:
            for hw in p.get("he_words") or []:
                raw = hw.get("raw") or ""
                if raw == "XM$":
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "חָמֵשׁ"
                    hw["strongs"] = "H2568"
                    hw["he_morph"] = "NUM.CARD.F.SG.A"
                    _set_es_patch(hw, "cinco", respect_user=respect_user_gloss)
                    hw.pop("prs_suffix", None)
                elif raw == "$NYM":
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "שָׁנִים"
                    hw["strongs"] = "H8141"
                    hw["he_morph"] = "SUBS.F.PL.A"
                    _set_es_patch(hw, "años", respect_user=respect_user_gloss)
                    hw.pop("prs_suffix", None)
                elif raw == "W/$B(YM":
                    _clear_hw_prefix_slots(hw)
                    hw["prefix_forms"] = ["וְ"]
                    hw["prefix_morphs"] = ["CONJ"]
                    hw["prefix_es"] = ["y"]
                    hw["he_form"] = "שִׁבְעִים"
                    hw["strongs"] = "H7657"
                    hw["he_morph"] = "CBPA"
                    _set_es_patch(hw, "setenta", respect_user=respect_user_gloss)
                    hw.pop("prs_suffix", None)
                elif raw == "B/C)T/W":
                    _gen6_split_at_prs(
                        hw,
                        prefix_forms=["בְ"],
                        prefix_morphs=["PREP"],
                        prefix_es=["en"],
                        stem_he="צֵאת",
                        stem_morph="VERBO.QAL.INFC",
                        stem_es="salir",
                        strongs="H3318",
                        suf_he="וֹ",
                        suf_morph="PRS.P3.M.SG",
                        suf_es="su",
                        respect_user_gloss=respect_user_gloss,
                    )

    if vrs == 5:
        for p in pairs:
            hws = p.get("he_words") or []
            out: list[dict] = []
            for hw in hws:
                raw = hw.get("raw") or ""
                if raw == ")XY/W":
                    _gen6_split_at_prs(
                        hw,
                        stem_he="אָחִי",
                        stem_morph="SUBS.M.SG.C",
                        stem_es="hermano de",
                        strongs="H251",
                        suf_he="וֹ",
                        suf_morph="PRS.P3.M.SG",
                        suf_es="su",
                        respect_user_gloss=respect_user_gloss,
                    )
                elif raw == "W/)T" and _gen5_he_key(hw).startswith("את"):
                    _gen6_split_at_prs(
                        hw,
                        prefix_forms=["וְ"],
                        prefix_morphs=["CONJ"],
                        prefix_es=["y"],
                        stem_he="אֶת",
                        stem_morph="PART.OBJ.DIR",
                        stem_es="",
                        strongs="H853",
                        respect_user_gloss=respect_user_gloss,
                    )
                out.append(hw)
            p["he_words"] = out
        flat: list[dict] = []
        for p in pairs:
            flat.extend(p.get("he_words") or [])
        rebuilt: list[dict] = []
        skip_next_vav = False
        for j, hw in enumerate(flat):
            raw = hw.get("raw") or ""
            if skip_next_vav and raw == "=VAV":
                skip_next_vav = False
                continue
            if raw == "W/)T" and _gen5_he_key(hw) == "ו":
                skip_next_vav = True
                continue
            if raw == "W/)T" and j + 1 < len(flat):
                nxt = flat[j + 1]
                if (nxt.get("raw") or "") == "KL" and _gen5_he_key(hw) == "ו":
                    continue
            rebuilt.append(hw)
        pairs[:] = [_gen5_min_pair(h) for h in rebuilt]

    if vrs == 8:
        wy_idx = next(
            (
                i for i, p in enumerate(pairs)
                if any((h.get("raw") or "") == "W/Y+" for h in (p.get("he_words") or []))
            ),
            None,
        )
        if wy_idx is not None:
            head = pairs[:wy_idx]
            tail_rest: list[dict] = []
            for p in pairs[wy_idx + 1 :]:
                hws = p.get("he_words") or []
                raws = {(h.get("raw") or "") for h in hws}
                if any((h.get("raw") or "") == "AHL/H" for h in hws):
                    continue
                if raws in ({"BYT", ")L"}, {"L/BYT", ")L"}):
                    continue
                if any((h.get("raw") or "") == "M/YM" for h in hws):
                    continue
                tail_rest.append(p)
            pairs[:] = head + [
                pairs[wy_idx],
                _gen5_min_pair(_gen12_tent_hw(respect_user_gloss=respect_user_gloss)),
                _gen12_bethel_pair(respect_user_gloss=respect_user_gloss),
                _gen5_min_pair(_gen12_miyyam_hw(respect_user_gloss=respect_user_gloss)),
            ] + tail_rest
            for p in pairs:
                for hw in p.get("he_words") or []:
                    if (hw.get("raw") or "") == "AHL/H":
                        _gen6_split_at_prs(
                            hw,
                            stem_he="אָהֳלֹ",
                            stem_morph="SUBS.M.SG.C",
                            stem_es="tienda",
                            strongs="H168",
                            suf_he="ה",
                            suf_morph="PRS.P3.M.SG",
                            suf_es="su",
                            respect_user_gloss=respect_user_gloss,
                        )

    if vrs == 12:
        for p in pairs:
            for hw in p.get("he_words") or []:
                raw = hw.get("raw") or ""
                if raw == ")T/K":
                    _gen6_split_at_prs(
                        hw,
                        stem_he="אֹת",
                        stem_morph="PART.OBJ.DIR",
                        stem_es="",
                        strongs="H853",
                        suf_he="ךָ",
                        suf_morph="PRS.P2.F.SG",
                        suf_es="te",
                        respect_user_gloss=respect_user_gloss,
                    )
                elif raw == "W/)T/K":
                    _gen6_split_at_prs(
                        hw,
                        prefix_forms=["וְ"],
                        prefix_morphs=["CONJ"],
                        prefix_es=["y"],
                        stem_he="אֹת",
                        stem_morph="PART.OBJ.DIR",
                        stem_es="",
                        strongs="H853",
                        suf_he="ךָ",
                        suf_morph="PRS.P2.F.SG",
                        suf_es="te",
                        respect_user_gloss=respect_user_gloss,
                    )
        for i, p in enumerate(pairs):
            hws = p.get("he_words") or []
            if len(hws) == 1 and (hws[0].get("raw") or "") == "Z)T":
                if i > 0:
                    prev = pairs[i - 1].get("he_words") or []
                    if any((h.get("raw") or "") == ")$T/W" for h in prev):
                        pairs[i - 1]["he_words"].extend(hws)
                        pairs.pop(i)
                        break

    if vrs == 13:
        for p in pairs:
            hws = p.get("he_words") or []
            out13: list[dict] = []
            for hw in hws:
                raw = hw.get("raw") or ""
                if raw == "L/Y" and _gen5_he_key(hw).startswith("נפ"):
                    _gen6_split_at_prs(
                        hw,
                        stem_he="נַפְשִׁ",
                        stem_morph="SUBS.BOTH.SG.C",
                        stem_es="alma",
                        strongs="H5315",
                        suf_he="י",
                        suf_morph="PRS.P1.COMMON.SG",
                        suf_es="mi",
                        respect_user_gloss=respect_user_gloss,
                    )
                elif raw == "B/(BWR/K":
                    _gen6_split_at_prs(
                        hw,
                        prefix_forms=["בְּ"],
                        prefix_morphs=["PREP"],
                        prefix_es=["en"],
                        stem_he="עֲבוּר",
                        stem_morph="SUBS.M.SG.C",
                        stem_es="bien",
                        strongs="H5668",
                        suf_he="ךְ",
                        suf_morph="PRS.P2.F.SG",
                        suf_es="ti",
                        respect_user_gloss=respect_user_gloss,
                    )
                elif raw == "NP$/Y" and not (hw.get("he_form") or "").strip():
                    continue
                out13.append(hw)
            p["he_words"] = out13
        reordered: list[dict] = []
        deferred_nefesh: dict | None = None
        has_nps_y = any(
            any((h.get("raw") or "") == "NP$/Y" for h in (p.get("he_words") or []))
            for p in pairs
        )
        for p in pairs:
            hws = p.get("he_words") or []
            if (
                has_nps_y
                and len(hws) == 1
                and (hws[0].get("raw") or "") == "L/Y"
                and _gen5_he_key(hws[0]).startswith("נפ")
            ):
                continue
            if (
                not has_nps_y
                and len(hws) == 1
                and (hws[0].get("raw") or "") == "L/Y"
                and _gen5_he_key(hws[0]).startswith("נפ")
            ):
                deferred_nefesh = p
                continue
            reordered.append(p)
            if deferred_nefesh and any((h.get("raw") or "") == "W/XYTH" for h in hws):
                reordered.append(deferred_nefesh)
                deferred_nefesh = None
        if deferred_nefesh is not None:
            reordered.append(deferred_nefesh)
        pairs[:] = reordered

    if vrs == 17:
        flat17: list[dict] = []
        for p in pairs:
            for hw in p.get("he_words") or []:
                raw = hw.get("raw") or ""
                if raw == "W/)T":
                    _clear_hw_prefix_slots(hw)
                    hw["prefix_forms"] = ["וְ"]
                    hw["prefix_morphs"] = ["CONJ"]
                    hw["prefix_es"] = ["y"]
                    hw["he_form"] = "אֶת"
                    hw["strongs"] = "H853"
                    hw["he_morph"] = "PART.OBJ.DIR"
                    _set_es_patch(hw, "", respect_user=respect_user_gloss)
                    hw.pop("prs_suffix", None)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"
                elif raw == "BYT/W":
                    _gen6_split_at_prs(
                        hw,
                        stem_he="בֵּית",
                        stem_morph="SUBS.M.SG.C",
                        stem_es="casa",
                        strongs="H1004",
                        suf_he="וֹ",
                        suf_morph="PRS.P3.M.SG",
                        suf_es="su",
                        respect_user_gloss=respect_user_gloss,
                    )
                flat17.append(hw)
        pairs[:] = [_gen5_min_pair(h) for h in flat17]

    if vrs == 16:
        pairs[:] = [
            p for p in pairs
            if not (
                len(p.get("he_words") or []) == 1
                and (p["he_words"][0].get("raw") or "") == "L/W"
            )
        ]

    if vrs == 18:
        flat18: list[dict] = []
        for p in pairs:
            flat18.extend(p.get("he_words") or [])
        out18: list[dict] = []
        i18 = 0
        while i18 < len(flat18):
            hw = flat18[i18]
            raw = hw.get("raw") or ""
            if raw == "L/MH":
                out18.append({
                    "raw": "L)",
                    "he_form": "לֹא",
                    "he_morph": "NEG",
                    "strongs": "",
                    "es": "no",
                    "es_source": "patch",
                })
                out18.append({
                    "raw": "HGDT",
                    "he_form": "הִגַּדְתָּ",
                    "he_morph": "VERBO.HIF.PERF.P2.M.SG",
                    "strongs": "H5046",
                    "es": "declaraste",
                    "es_source": "patch",
                })
                out18.extend([
                    {
                        "raw": "KY",
                        "he_form": "כִּי",
                        "he_morph": "CONJ",
                        "strongs": "H3588",
                        "es": "que",
                        "es_source": "patch",
                    },
                    {
                        "raw": ")$T/K",
                        "he_form": "אִשְׁתּ",
                        "he_morph": "SUBS.F.SG.C",
                        "strongs": "H802",
                        "es": "mujer",
                        "es_source": "patch",
                        "prs_suffix": {
                            "he_form": "ךָ",
                            "he_morph": "PRS.P2.M.SG",
                            "es": "tu",
                        },
                    },
                ])
                i18 += 1
                continue
            if raw in ("L)", "HGDT", "KY", ")$T/K") and any(
                h.get("raw") == "L/MH" for h in flat18
            ):
                i18 += 1
                continue
            if raw == "L/Y" and _gen5_he_key(hw).startswith("ה"):
                out18.append(hw)
                i18 += 1
                continue
            if raw == "HW)" and out18 and out18[-1].get("raw") in ("L/Y", "HW)"):
                i18 += 1
                continue
            if raw == "KY" and out18 and out18[-1].get("raw") == "KY":
                i18 += 1
                continue
            out18.append(hw)
            i18 += 1
        pairs[:] = [_gen5_min_pair(h) for h in out18]
        for p in pairs:
            for hw in p.get("he_words") or []:
                if (hw.get("raw") or "") == "L/Y" and _gen5_he_key(hw).startswith("ה"):
                    hw["raw"] = "HW)"
                    hw.pop("prs_suffix", None)
                if (hw.get("raw") or "") == ")$T/K":
                    _gen12_repair_isht_ka_hw(hw, respect_user_gloss=respect_user_gloss)
                if (hw.get("raw") or "") == "HW)":
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "הִוא"
                    hw["he_morph"] = "PRON.PERS.P3.F.SG"
                    hw["strongs"] = "H1931"
                    hw.pop("prs_suffix", None)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

    if vrs == 19:
        pairs[:] = [
            p for p in pairs
            if not (
                len(p.get("he_words") or []) == 1
                and (p["he_words"][0].get("raw") or "") == "L/)$H"
            )
        ]
        for p in pairs:
            for hw in p.get("he_words") or []:
                raw = hw.get("raw") or ""
                if raw == "W/LK":
                    _gen6_split_at_prs(
                        hw,
                        prefix_forms=["וְ"],
                        prefix_morphs=["CONJ"],
                        prefix_es=["y"],
                        stem_he="לֵךְ",
                        stem_morph="VERBO.QAL.IMPV.M.SG",
                        stem_es="ve",
                        strongs="H3212",
                        respect_user_gloss=respect_user_gloss,
                    )
        for i, p in enumerate(pairs):
            hws = p.get("he_words") or []
            if any((h.get("raw") or "") == "HNH" for h in hws):
                ni = i + 1
                if ni < len(pairs):
                    nhw = pairs[ni].get("he_words") or []
                    if nhw and (nhw[0].get("raw") or "") == ")$T/K":
                        _gen12_repair_isht_ka_hw(nhw[0], respect_user_gloss=respect_user_gloss)
                break

    if vrs == 20:
        flat20: list[dict] = []
        for p in pairs:
            for hw in p.get("he_words") or []:
                raw = hw.get("raw") or ""
                if raw == "W/)T":
                    he_key = _gen5_he_key(hw)
                    if he_key == "ו" and not (hw.get("he_form") or "").strip():
                        continue
                    _clear_hw_prefix_slots(hw)
                    hw["prefix_forms"] = ["וְ"]
                    hw["prefix_morphs"] = ["CONJ"]
                    hw["prefix_es"] = ["y"]
                    hw["he_form"] = "אֶת"
                    hw["strongs"] = "H853"
                    hw["he_morph"] = "PART.OBJ.DIR"
                    _set_es_patch(hw, "", respect_user=respect_user_gloss)
                    hw.pop("prs_suffix", None)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"
                flat20.append(hw)
        pairs[:] = [_gen5_min_pair(h) for h in flat20]

    _fix_gen5_empty_pairs(verse)

    verse["pairs"] = [
        p for p in verse.get("pairs", [])
        if p.get("he_words")
        or (p.get("gr_unicode") or "").strip()
        or p.get("kind") == "heb_omit"
    ]

    if vrs == 18:
        for p in verse.get("pairs", []):
            for hw in p.get("he_words") or []:
                if (hw.get("raw") or "") == ")$T/K":
                    _gen12_repair_isht_ka_hw(hw, respect_user_gloss=respect_user_gloss)
                if (hw.get("raw") or "") == "HW)":
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "הִוא"
                    hw["he_morph"] = "PRON.PERS.P3.F.SG"
                    hw["strongs"] = "H1931"
                    hw.pop("prs_suffix", None)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"


def _gen12_finalize_prep_prs(verse: dict) -> None:
    """Post-merge: lectura prep+PRS fusionada en stem; conserva he_form del prs (OSHB)."""
    fused = {
        "a él", "a el", "sobre él", "sobre el",
        "con él", "con el", "de él", "de el",
    }
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            raw = hw.get("raw") or ""
            prs = hw.get("prs_suffix") or {}
            if not prs.get("he_form"):
                continue
            es = (hw.get("es") or "").strip()
            es_low = es.lower()
            if raw == "(L/YW" and es == "sobre" and (prs.get("es") or "").strip() == "él":
                hw["es"] = "sobre él"
                es_low = "sobre él"
            if es_low in fused:
                prs["es"] = ""
                prs["es_source"] = "patch_meta"


def _fix_gen12_v3_participle_readings(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """12:3 — participios + sufijo -ךָ: evitar «te los que te…» tras merge PRS."""
    if verse.get("verse") != 3:
        return
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            raw = hw.get("raw") or ""
            prs = hw.get("prs_suffix")
            if raw == "M/BRK/YK":
                _set_es_patch(hw, "a los que te bendicen", respect_user=respect_user_gloss)
                if isinstance(prs, dict):
                    prs["es"] = ""
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"
            elif raw == "W/MQLL/K":
                _set_es_patch(hw, "al que te maldice", respect_user=respect_user_gloss)
                if isinstance(prs, dict):
                    prs["es"] = ""
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"


def _fix_gen12_es_glosses(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Correcciones de glosas / metadatos español cap. 12."""
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            raw = hw.get("raw") or ""

            if raw == "HQRYB":
                _set_es_patch(hw, "acercó", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "HW)" and (hw.get("he_morph") or "") == "PRON.PERS.P3.F.SG":
                _set_es_patch(hw, "ella", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif _is_nprop_morph(hw.get("he_morph") or "") and _gen5_he_key(hw) == "אברם":
                if (hw.get("es") or "").strip().lower() != "abram":
                    _set_es_patch(hw, "Abram", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

    _fix_gen12_v3_participle_readings(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen5_numeric_glosses(verse, respect_user_gloss=respect_user_gloss)


def _patch_gen12(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Parches estructurales Génesis cap. 12 — llamada de Abram."""
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            _gen12_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)

    _fix_gen12_oshb_align(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen12_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if not (
                (hw.get("raw") or "").endswith("}")
                or (
                    hw.get("es_source") == "patch_meta"
                    and not _strip_niqqud(hw.get("he_form") or "")
                )
            )
        ]
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if (hw.get("he_form") or "").strip()
            or (hw.get("prefix_forms") or [])
            or (hw.get("prs_suffix") or {}).get("he_form")
            or hw.get("raw") in ("=L/MYN/W", "=L/MYN/HW", "=VAV")
        ]

    verse["pairs"] = [
        p for p in verse.get("pairs", [])
        if p.get("he_words")
        or (p.get("gr_unicode") or "").strip()
        or p.get("kind") == "heb_omit"
    ]

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _gen5_preserve_fused_ot(hw, respect_user_gloss=respect_user_gloss)
            _merge_prs_reading_gloss(hw)

    _gen12_reapply_oshb_splits(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen12_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _merge_prs_reading_gloss(hw)
            _drop_redundant_prs_suffix(hw)

    _fix_gen12_v3_participle_readings(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen12_lxx_align(verse)
    normalize_verse_maqaf(verse)
    _sanitize_catss_pairs(verse)


# Génesis cap. 13 — Abram y Lot (plantilla cap. 12)
def _gen13_prs_k_hw(*, respect_user_gloss: bool = False) -> dict:
    """PRS ךָ suelto (13:8 — tras בֵינֶי / רֹעֶי)."""
    hw: dict = {
        "raw": "=PRS/K",
        "he_form": "ךָ",
        "he_morph": "PRS.P2.M.SG",
        "strongs": "",
        "es": "ti",
        "es_source": "patch",
    }
    if respect_user_gloss:
        hw.pop("es_source", None)
    return hw


def _gen13_ohel_vo_hw(*, respect_user_gloss: bool = False) -> dict:
    """אָֽהֳל + וֹ — su tienda (13:3; artefacto OSHB i>( eliminado)."""
    hw: dict = {
        "raw": "**)HL/W",
        "he_form": "אָֽהֳל",
        "he_morph": "SUBS.M.SG.C",
        "strongs": "H168",
        "es": "tienda",
        "es_source": "patch",
        "prs_suffix": {
            "he_form": "וֹ",
            "he_morph": "PRS.P3.M.SG",
            "es": "su",
        },
    }
    if respect_user_gloss:
        hw.pop("es_source", None)
    return hw


def _gen13_dir_hw(
    raw: str,
    stem_he: str,
    *,
    prefix_forms: list | None = None,
    prefix_morphs: list | None = None,
    prefix_es: list | None = None,
    stem_morph: str = "SUBS.F.SG.A",
    stem_es: str = "",
    strongs: str = "",
    respect_user_gloss: bool = False,
) -> dict:
    """Direccional + ה locativo (13:14)."""
    hw: dict = {
        "raw": raw,
        "he_form": stem_he,
        "he_morph": stem_morph,
        "strongs": strongs,
        "es": stem_es,
        "es_source": "patch",
        "prefix_forms": prefix_forms or [],
        "prefix_morphs": prefix_morphs or [],
        "prefix_es": prefix_es or [],
        "prs_suffix": {
            "he_form": "ה",
            "he_morph": "SUF.DIR.HE",
            "es": "",
        },
    }
    if respect_user_gloss:
        hw.pop("es_source", None)
    return hw


def _gen13_apply_prs_splits(hw: dict, *, respect_user_gloss: bool = False) -> None:
    """Splits PRS / compuestos frecuentes cap. 13 (reutiliza cap. 12 + específicos B2)."""
    _gen12_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)
    raw = hw.get("raw", "")

    if raw == "L/MS(/YW":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["לְ"],
            prefix_morphs=["PREP"],
            prefix_es=["en"],
            stem_he="מַסָּעָי",
            stem_morph="SUBS.M.PL.C",
            stem_es="jornadas",
            strongs="H4550",
            suf_he="ו",
            suf_morph="PRS.P3.M.SG",
            suf_es="su",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "BYN/Y":
        _gen6_split_at_prs(
            hw,
            stem_he="בֵּינִ",
            stem_morph="PREP",
            stem_es="entre",
            strongs="H996",
            suf_he="י",
            suf_morph="PRS.P1.COMMON.SG",
            suf_es="mí",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "W/BYN/YK":
        _clear_hw_prefix_slots(hw)
        hw["prefix_forms"] = ["וּ"]
        hw["prefix_morphs"] = ["CONJ"]
        hw["prefix_es"] = ["y"]
        hw["he_form"] = "בֵּינֶי"
        hw["he_morph"] = "PREP"
        hw["strongs"] = "H996"
        _set_es_patch(hw, "entre", respect_user=respect_user_gloss)
        hw.pop("prs_suffix", None)
        if not (respect_user_gloss and _has_user_gloss(hw)):
            hw["es_source"] = "patch"

    elif raw == "R(/Y":
        _gen6_split_at_prs(
            hw,
            stem_he="רֹעַ",
            stem_morph="VERBO.QAL.PTCA.M.PL.C",
            stem_es="pastores",
            strongs="H7462",
            suf_he="י",
            suf_morph="PRS.P1.COMMON.SG",
            suf_es="míos",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "R(/YK":
        _clear_hw_prefix_slots(hw)
        hw["he_form"] = "רֹעֶי"
        hw["he_morph"] = "VERBO.QAL.PTCA.M.PL.C"
        hw["strongs"] = "H7462"
        _set_es_patch(hw, "pastores", respect_user=respect_user_gloss)
        hw.pop("prs_suffix", None)
        if not (respect_user_gloss and _has_user_gloss(hw)):
            hw["es_source"] = "patch"

    elif raw == "L/PN/YK":
        _clear_hw_prefix_slots(hw)
        hw["prefix_forms"] = ["לְ"]
        hw["prefix_morphs"] = ["PREP"]
        hw["prefix_es"] = ["a"]
        hw["he_form"] = "פָנֶי"
        hw["he_morph"] = "SUBS.BOTH.PL.C"
        hw["strongs"] = "H6440"
        _set_es_patch(hw, "rostro", respect_user=respect_user_gloss)
        hw.pop("prs_suffix", None)
        if not (respect_user_gloss and _has_user_gloss(hw)):
            hw["es_source"] = "patch"

    elif raw == "M/(L/Y":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["מֵ"],
            prefix_morphs=["PREP"],
            prefix_es=["de"],
            stem_he="עָל",
            stem_morph="PREP",
            stem_es="sobre",
            strongs="H5921",
            suf_he="י",
            suf_morph="PRS.P1.COMMON.SG",
            suf_es="mí",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "M/(M/W":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["מֵ"],
            prefix_morphs=["PREP"],
            prefix_es=["de"],
            stem_he="עִמּ",
            stem_morph="PREP",
            stem_es="con",
            strongs="H5973",
            suf_he="וֹ",
            suf_morph="PRS.P3.M.SG",
            suf_es="él",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "(YN/YK":
        _clear_hw_prefix_slots(hw)
        hw["he_form"] = "עֵינֶי"
        hw["he_morph"] = "SUBS.BOTH.DU.C"
        hw["strongs"] = "H5869"
        _set_es_patch(hw, "ojos", respect_user=respect_user_gloss)
        hw.pop("prs_suffix", None)
        if not (respect_user_gloss and _has_user_gloss(hw)):
            hw["es_source"] = "patch"

    elif raw == "(YN/YW":
        _clear_hw_prefix_slots(hw)
        hw["he_form"] = "עֵינָי"
        hw["he_morph"] = "SUBS.BOTH.DU.C"
        hw["strongs"] = "H5869"
        _set_es_patch(hw, "ojos", respect_user=respect_user_gloss)
        _attach_prs_suffix(hw, "ו", "PRS.P3.M.SG", "su")
        if not (respect_user_gloss and _has_user_gloss(hw)):
            hw["es_source"] = "patch"

    elif raw == "KL/H":
        _gen6_split_at_prs(
            hw,
            stem_he="כֻלָּ",
            stem_morph="SUBS.M.SG.C",
            stem_es="toda",
            strongs="H3605",
            suf_he="הּ",
            suf_morph="PRS.P3.F.SG",
            suf_es="la",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == ")TN/NH":
        _gen6_split_at_prs(
            hw,
            stem_he="אֶתְּנֶ",
            stem_morph="VERBO.QAL.IMPF.P1.COMMON.SG",
            stem_es="daré",
            strongs="H5414",
            suf_he="נָּה",
            suf_morph="PRS.P3.F.SG",
            suf_es="la",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "L/)RK/H":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["לְ"],
            prefix_morphs=["PREP"],
            prefix_es=["a"],
            stem_he="אָרְכָּ",
            stem_morph="SUBS.M.SG.C",
            stem_es="longitud",
            strongs="H753",
            suf_he="הּ",
            suf_morph="PRS.P3.F.SG",
            suf_es="su",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "W/L/RXB/H":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["וּ", "לְ"],
            prefix_morphs=["CONJ", "PREP"],
            prefix_es=["y", "a"],
            stem_he="רָחְבָּ",
            stem_morph="SUBS.M.SG.C",
            stem_es="anchura",
            strongs="H7341",
            suf_he="הּ",
            suf_morph="PRS.P3.F.SG",
            suf_es="su",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "W/)YMN/H":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["וְ"],
            prefix_morphs=["CONJ"],
            prefix_es=["y"],
            stem_he="אֵימִנָה",
            stem_morph="VERBO.HIF.COHORT.P1.COMMON.SG",
            stem_es="iré a la derecha",
            strongs="H3231",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "W/)&M)YL/H":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["וְ"],
            prefix_morphs=["CONJ"],
            prefix_es=["y"],
            stem_he="אַשְׂמְאִילָה",
            stem_morph="VERBO.HIF.COHORT.P1.COMMON.SG",
            stem_es="iré a la izquierda",
            strongs="H8041",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "W/)$T/W":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["וְ"],
            prefix_morphs=["CONJ"],
            prefix_es=["y"],
            stem_he="אִשְׁתּ",
            stem_morph="SUBS.F.SG.C",
            stem_es="mujer",
            strongs="H802",
            suf_he="וֹ",
            suf_morph="PRS.P3.M.SG",
            suf_es="su",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "(M/W":
        _gen6_split_at_prs(
            hw,
            stem_he="עִמּ",
            stem_morph="PREP",
            stem_es="con",
            strongs="H5973",
            suf_he="וֹ",
            suf_morph="PRS.P3.M.SG",
            suf_es="él",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "ZR(/K":
        _gen6_split_at_prs(
            hw,
            stem_he="זַרְעֲ",
            stem_morph="SUBS.M.SG.C",
            stem_es="simiente",
            strongs="H2233",
            suf_he="ךָ",
            suf_morph="PRS.P2.M.SG",
            suf_es="tu",
            respect_user_gloss=respect_user_gloss,
        )


def _gen13_finalize_loose_vav(verse: dict) -> None:
    """B4 — fusiona =PRS/V huérfanos en prs_suffix del token anterior."""
    for p in verse.get("pairs", []):
        hws = p.get("he_words") or []
        out: list[dict] = []
        for hw in hws:
            raw = hw.get("raw") or ""
            if raw == "=PRS/V":
                if out and not (out[-1].get("prs_suffix") or {}).get("he_form"):
                    _attach_prs_suffix(out[-1], "ו", "PRS.P3.M.SG", "su")
                continue
            out.append(hw)
        p["he_words"] = out


def _gen13_reapply_oshb_splits(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Reaplica splits cap. 13 tras merge PRS / Pass 16."""
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            _gen13_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)


def _fix_gen13_oshb_align(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Post-proceso cap. 13 — orden, tokens rotos, inserciones OSHB (B2)."""
    vrs = verse.get("verse", 0)
    pairs = verse.get("pairs", [])

    _fix_gen5_w_prefixes(verse)
    _fix_gen5_after_maot(verse)

    if vrs == 1:
        pairs[:] = [
            p for p in pairs
            if not (
                len(p.get("he_words") or []) == 1
                and (p["he_words"][0].get("raw") or "") == "L/W"
            )
        ]
        for p in pairs:
            for hw in p.get("he_words") or []:
                raw = hw.get("raw") or ""
                if raw == "W/)$T/W":
                    _gen6_split_at_prs(
                        hw,
                        prefix_forms=["וְ"],
                        prefix_morphs=["CONJ"],
                        prefix_es=["y"],
                        stem_he="אִשְׁתּ",
                        stem_morph="SUBS.F.SG.C",
                        stem_es="mujer",
                        strongs="H802",
                        suf_he="וֹ",
                        suf_morph="PRS.P3.M.SG",
                        suf_es="su",
                        respect_user_gloss=respect_user_gloss,
                    )
                elif raw == "(M/W":
                    _gen6_split_at_prs(
                        hw,
                        stem_he="עִמּ",
                        stem_morph="PREP",
                        stem_es="con",
                        strongs="H5973",
                        suf_he="וֹ",
                        suf_morph="PRS.P3.M.SG",
                        suf_es="él",
                        respect_user_gloss=respect_user_gloss,
                    )
                elif raw == "H/NGB/H":
                    _gen6_split_at_prs(
                        hw,
                        prefix_forms=["הַ"],
                        prefix_morphs=["ART"],
                        prefix_es=["el"],
                        stem_he="נֶגֶב",
                        stem_morph="SUBS.M.SG.A",
                        stem_es="sur",
                        strongs="H5045",
                        suf_he="ה",
                        suf_morph="SUF.DIR.HE",
                        suf_es="",
                        respect_user_gloss=respect_user_gloss,
                    )

    if vrs == 3:
        for p in pairs:
            for hw in p.get("he_words") or []:
                if (hw.get("raw") or "") == "L/MS(/YW":
                    _gen6_split_at_prs(
                        hw,
                        prefix_forms=["לְ"],
                        prefix_morphs=["PREP"],
                        prefix_es=["en"],
                        stem_he="מַסָּעָי",
                        stem_morph="SUBS.M.PL.C",
                        stem_es="jornadas",
                        strongs="H4550",
                        suf_he="ו",
                        suf_morph="PRS.P3.M.SG",
                        suf_es="su",
                        respect_user_gloss=respect_user_gloss,
                    )
        asher_idx = next(
            (
                i for i, p in enumerate(pairs)
                if any((h.get("raw") or "") == ")$R" for h in (p.get("he_words") or []))
            ),
            None,
        )
        if asher_idx is not None:
            btxlh_p = next(
                (
                    p for p in pairs
                    if any((h.get("raw") or "") == "B/TXLH" for h in (p.get("he_words") or []))
                ),
                _gen5_min_pair({
                    "raw": "B/TXLH",
                    "prefix_forms": ["בַּ"],
                    "prefix_morphs": ["PREP"],
                    "prefix_es": ["en"],
                    "he_form": "תְּחִלָּה",
                    "he_morph": "SUBS.F.SG.A",
                    "strongs": "H8462",
                    "es": "principio",
                    "es_source": "patch",
                }),
            )
            head = pairs[: asher_idx + 1]
            tail_keep: list[dict] = []
            for p in pairs[asher_idx + 1 :]:
                raws = {(h.get("raw") or "") for h in (p.get("he_words") or [])}
                if raws & {"HYH", "$M", "AHL/H", "**)HL/W", "*)HL/H", "B/TXLH", "BYN", "BYT", ")L", "W/BYN", "H/(Y"}:
                    continue
                if not (p.get("he_words") or []):
                    continue
                tail_keep.append(p)
            pairs[:] = head + [
                _gen5_min_pair({
                    "raw": "HYH",
                    "he_form": "הָיָה",
                    "he_morph": "VERBO.QAL.PERF.P3.M.SG",
                    "strongs": "H1961",
                    "es": "había",
                    "es_source": "patch",
                }),
                _gen5_min_pair({
                    "raw": "$M",
                    "he_form": "שָׁם",
                    "he_morph": "ADV",
                    "strongs": "H8033",
                    "es": "allí",
                    "es_source": "patch",
                }),
                _gen5_min_pair(_gen13_ohel_vo_hw(respect_user_gloss=respect_user_gloss)),
                btxlh_p,
                _gen5_min_pair({
                    "raw": "BYN",
                    "he_form": "בֵּין",
                    "he_morph": "PREP",
                    "strongs": "H996",
                    "es": "entre",
                    "es_source": "patch",
                }),
                _gen12_bethel_pair(
                    respect_user_gloss=respect_user_gloss,
                    el_form="אֵ֖ל",
                ),
                _gen5_min_pair({
                    "raw": "W/BYN",
                    "prefix_forms": ["וּ"],
                    "prefix_morphs": ["CONJ"],
                    "prefix_es": ["y"],
                    "he_form": "בֵין",
                    "he_morph": "PREP",
                    "strongs": "H996",
                    "es": "entre",
                    "es_source": "patch",
                }),
                _gen5_min_pair({
                    "raw": "H/(Y",
                    "prefix_forms": ["הָ"],
                    "prefix_morphs": ["ART"],
                    "prefix_es": ["la"],
                    "he_form": "עָי",
                    "he_morph": "NPROP",
                    "strongs": "H5857",
                    "es": "Ai",
                    "es_source": "patch",
                }),
            ] + tail_keep
            for p in pairs:
                for hw in p.get("he_words") or []:
                    raw = hw.get("raw") or ""
                    if raw == "**)HL/W":
                        _gen6_split_at_prs(
                            hw,
                            stem_he="אָֽהֳל",
                            stem_morph="SUBS.M.SG.C",
                            stem_es="tienda",
                            strongs="H168",
                            suf_he="וֹ",
                            suf_morph="PRS.P3.M.SG",
                            suf_es="su",
                            respect_user_gloss=respect_user_gloss,
                        )

    if vrs == 8:
        flat8: list[dict] = []
        for p in pairs:
            for hw in p.get("he_words") or []:
                if (hw.get("raw") or "") == "=PRS/K":
                    continue
                raw = hw.get("raw") or ""
                if raw == "W/BYN/YK":
                    _clear_hw_prefix_slots(hw)
                    hw["prefix_forms"] = ["וּ"]
                    hw["prefix_morphs"] = ["CONJ"]
                    hw["prefix_es"] = ["y"]
                    hw["he_form"] = "בֵּינֶי"
                    hw["he_morph"] = "PREP"
                    hw["strongs"] = "H996"
                    _set_es_patch(hw, "entre", respect_user=respect_user_gloss)
                    hw.pop("prs_suffix", None)
                elif raw == "R(/Y":
                    _gen6_split_at_prs(
                        hw,
                        stem_he="רֹעַ",
                        stem_morph="VERBO.QAL.PTCA.M.PL.C",
                        stem_es="pastores",
                        strongs="H7462",
                        suf_he="י",
                        suf_morph="PRS.P1.COMMON.SG",
                        suf_es="míos",
                        respect_user_gloss=respect_user_gloss,
                    )
                elif raw == "R(/YK":
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "רֹעֶי"
                    hw["he_morph"] = "VERBO.QAL.PTCA.M.PL.C"
                    hw["strongs"] = "H7462"
                    _set_es_patch(hw, "pastores", respect_user=respect_user_gloss)
                    hw.pop("prs_suffix", None)
                flat8.append(hw)
                if raw in ("W/BYN/YK", "R(/YK"):
                    flat8.append(_gen13_prs_k_hw(respect_user_gloss=respect_user_gloss))
        pairs[:] = [_gen5_min_pair(h) for h in flat8]

    if vrs == 9:
        rebuilt9: list[dict] = [
            {
                "he_words": [
                    {
                        "raw": "H/L)",
                        "prefix_forms": ["הֲ"],
                        "prefix_morphs": ["PART.INTERR"],
                        "prefix_es": [""],
                        "he_form": "לֹא",
                        "he_morph": "NEG",
                        "strongs": "H3808",
                        "es": "¿no",
                        "es_source": "patch",
                    },
                ],
                "gr_unicode": "οὐκ ἰδοὺ",
            },
            _gen5_min_pair({
                "raw": "KL",
                "he_form": "כָל\u05be",
                "he_morph": "SUBS.M.SG.C",
                "strongs": "H3605",
                "es": "toda",
                "es_source": "patch",
            }),
            _gen5_min_pair({
                "raw": "H/)RC",
                "prefix_forms": ["הַ"],
                "prefix_morphs": ["ART"],
                "prefix_es": ["la"],
                "he_form": "אָרֶץ",
                "he_morph": "SUBS.BOTH.SG.A",
                "strongs": "H776",
                "es": "tierra",
                "es_source": "patch",
            }),
            _gen5_min_pair({
                "raw": "L/PN/YK",
                "prefix_forms": ["לְ"],
                "prefix_morphs": ["PREP"],
                "prefix_es": ["a"],
                "he_form": "פָנֶי",
                "he_morph": "SUBS.BOTH.PL.C",
                "strongs": "H6440",
                "es": "delante",
                "es_source": "patch",
            }),
            _gen5_min_pair(_gen13_prs_k_hw(respect_user_gloss=respect_user_gloss)),
            _gen5_min_pair({
                "raw": "HPRD",
                "he_form": "הִפָּרֶד",
                "he_morph": "VERBO.NIF.IMPV.P2.M.SG",
                "strongs": "H6504",
                "es": "apártate",
                "es_source": "patch",
            }),
            _gen5_min_pair({
                "raw": "N)",
                "he_form": "נָא",
                "he_morph": "PART.EXH",
                "strongs": "H4994",
                "es": "te ruego",
                "es_source": "patch",
            }),
            _gen5_min_pair({
                "raw": "M/(L/Y",
                "prefix_forms": ["מֵ"],
                "prefix_morphs": ["PREP"],
                "prefix_es": ["de"],
                "he_form": "עָל",
                "he_morph": "PREP",
                "strongs": "H5921",
                "es": "mí",
                "es_source": "patch",
                "prs_suffix": {
                    "he_form": "י",
                    "he_morph": "PRS.P1.COMMON.SG",
                    "es": "mí",
                },
            }),
            _gen5_min_pair({
                "raw": ")M",
                "he_form": "אִם\u05be",
                "he_morph": "CONJ",
                "strongs": "H518",
                "es": "si",
                "es_source": "patch",
            }),
            _gen5_min_pair({
                "raw": "H/&M)L",
                "prefix_forms": ["הַ"],
                "prefix_morphs": ["ART"],
                "prefix_es": ["la"],
                "he_form": "שְּׂמֹאל",
                "he_morph": "SUBS.M.SG.A",
                "strongs": "H8040",
                "es": "izquierda",
                "es_source": "patch",
            }),
            _gen5_min_pair({
                "raw": "W/)YMN/H",
                "prefix_forms": ["וְ"],
                "prefix_morphs": ["CONJ"],
                "prefix_es": ["y"],
                "he_form": "אֵימִנָה",
                "he_morph": "VERBO.HIF.COHORT.P1.COMMON.SG",
                "strongs": "H3231",
                "es": "iré a la derecha",
                "es_source": "patch",
            }),
            _gen5_min_pair({
                "raw": "W/)M",
                "prefix_forms": ["וְ"],
                "prefix_morphs": ["CONJ"],
                "prefix_es": ["y"],
                "he_form": "אִם\u05be",
                "he_morph": "CONJ",
                "strongs": "H518",
                "es": "si",
                "es_source": "patch",
            }),
            _gen5_min_pair({
                "raw": "H/YMYN",
                "prefix_forms": ["הַ"],
                "prefix_morphs": ["ART"],
                "prefix_es": ["la"],
                "he_form": "יָּמִין",
                "he_morph": "SUBS.F.SG.A",
                "strongs": "H3225",
                "es": "derecha",
                "es_source": "patch",
            }),
            _gen5_min_pair({
                "raw": "W/)&M)YL/H",
                "prefix_forms": ["וְ"],
                "prefix_morphs": ["CONJ"],
                "prefix_es": ["y"],
                "he_form": "אַשְׂמְאִילָה",
                "he_morph": "VERBO.HIF.COHORT.P1.COMMON.SG",
                "strongs": "H8041",
                "es": "iré a la izquierda",
                "es_source": "patch",
            }),
        ]
        pairs[:] = rebuilt9
        _gen13_apply_v9_gr_unicode(pairs)

    if vrs == 10:
        flat10: list[dict] = []
        for p in pairs:
            for hw in p.get("he_words") or []:
                raw = hw.get("raw") or ""
                if raw == "=PRS/V":
                    continue
                if _gen5_he_key(hw) == "עיני" and raw != "(YN/YW":
                    continue
                flat10.append(hw)
        out10: list[dict] = []
        seen_ynyw = False
        for hw in flat10:
            raw = hw.get("raw") or ""
            if raw == "(YN/YW":
                if seen_ynyw:
                    continue
                seen_ynyw = True
                _clear_hw_prefix_slots(hw)
                hw["he_form"] = "עֵינָי"
                hw["he_morph"] = "SUBS.BOTH.DU.C"
                hw["strongs"] = "H5869"
                _set_es_patch(hw, "ojos", respect_user=respect_user_gloss)
                _attach_prs_suffix(hw, "ו", "PRS.P3.M.SG", "su")
                out10.append(hw)
            elif raw == "KL/H":
                _gen6_split_at_prs(
                    hw,
                    stem_he="כֻלָּ",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="toda",
                    strongs="H3605",
                    suf_he="הּ",
                    suf_morph="PRS.P3.F.SG",
                    suf_es="la",
                    respect_user_gloss=respect_user_gloss,
                )
                out10.append(hw)
            elif raw == "W/)T" and _gen5_he_key(hw).startswith("את"):
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["וְ"],
                    prefix_morphs=["CONJ"],
                    prefix_es=["y"],
                    stem_he="אֶת",
                    stem_morph="PART.OBJ.DIR",
                    stem_es="",
                    strongs="H853",
                    respect_user_gloss=respect_user_gloss,
                )
                out10.append(hw)
            elif raw == "B)/KH":
                _gen6_split_at_prs(
                    hw,
                    stem_he="בֹּאֲ",
                    stem_morph="VERBO.QAL.INFC",
                    stem_es="entrando",
                    strongs="H935",
                    suf_he="כָה",
                    suf_morph="PRS.P2.M.SG",
                    suf_es="",
                    respect_user_gloss=respect_user_gloss,
                )
                out10.append(hw)
            else:
                out10.append(hw)
        grs10 = [p.get("gr_unicode") or "" for p in pairs]
        pairs[:] = []
        gi = 0
        for hw in out10:
            np = _gen5_min_pair(hw)
            if gi < len(grs10) and grs10[gi]:
                np["gr_unicode"] = grs10[gi]
                gi += 1
            pairs.append(np)

    if vrs == 11:
        pairs[:] = [
            p for p in pairs
            if not (
                len(p.get("he_words") or []) == 1
                and (p["he_words"][0].get("raw") or "") == "L/W"
            )
        ]

    if vrs == 14:
        asher14_idx = next(
            (
                i for i, p in enumerate(pairs)
                if any((h.get("raw") or "") == ")$R" for h in (p.get("he_words") or []))
            ),
            None,
        )
        if asher14_idx is not None:
            head14_flat: list[dict] = []
            for p in pairs[: asher14_idx + 1]:
                for hw in p.get("he_words") or []:
                    if (hw.get("raw") or "") == "=PRS/K":
                        continue
                    raw = hw.get("raw") or ""
                    if raw == "M/(M/W":
                        _gen6_split_at_prs(
                            hw,
                            prefix_forms=["מֵ"],
                            prefix_morphs=["PREP"],
                            prefix_es=["de"],
                            stem_he="עִמּ",
                            stem_morph="PREP",
                            stem_es="con",
                            strongs="H5973",
                            suf_he="וֹ",
                            suf_morph="PRS.P3.M.SG",
                            suf_es="él",
                            respect_user_gloss=respect_user_gloss,
                        )
                    elif raw == "(YN/YK":
                        _clear_hw_prefix_slots(hw)
                        hw["he_form"] = "עֵינֶי"
                        hw["he_morph"] = "SUBS.BOTH.DU.C"
                        hw["strongs"] = "H5869"
                        _set_es_patch(hw, "ojos", respect_user=respect_user_gloss)
                        hw.pop("prs_suffix", None)
                    head14_flat.append(hw)
                    if raw == "(YN/YK":
                        head14_flat.append(_gen13_prs_k_hw(respect_user_gloss=respect_user_gloss))
            tail14: list[dict] = []
            for p in pairs[asher14_idx + 1 :]:
                raws = {(h.get("raw") or "") for h in (p.get("he_words") or [])}
                if raws & {")TH", "(TH", ".)(", "$M", "CPN/H", "W/NGB/H", "W/QDM/H", "W/YM/H"}:
                    continue
                if not (p.get("he_words") or []):
                    continue
                tail14.append(p)
            pairs[:] = [_gen5_min_pair(h) for h in head14_flat] + [
                _gen5_min_pair({
                    "raw": ")TH",
                    "he_form": "אַתָּה",
                    "he_morph": "PRON.PERS.P2.M.SG",
                    "strongs": "H859",
                    "es": "tú",
                    "es_source": "patch",
                }),
                _gen5_min_pair({
                    "raw": "$M",
                    "he_form": "שָׁם",
                    "he_morph": "ADV",
                    "strongs": "H8033",
                    "es": "allí",
                    "es_source": "patch",
                }),
                _gen5_min_pair(_gen13_dir_hw(
                    "CPN/H", "צָפֹנָ", stem_morph="SUBS.F.SG.A",
                    stem_es="norte", strongs="H6828",
                    respect_user_gloss=respect_user_gloss,
                )),
                _gen5_min_pair(_gen13_dir_hw(
                    "W/NGB/H", "נֶגְבָּ",
                    prefix_forms=["וָ"], prefix_morphs=["CONJ"], prefix_es=["y"],
                    stem_morph="SUBS.M.SG.A", stem_es="sur", strongs="H5045",
                    respect_user_gloss=respect_user_gloss,
                )),
                _gen5_min_pair(_gen13_dir_hw(
                    "W/QDM/H", "קֵדְמָ",
                    prefix_forms=["וָ"], prefix_morphs=["CONJ"], prefix_es=["y"],
                    stem_morph="SUBS.M.SG.A", stem_es="este", strongs="H6924",
                    respect_user_gloss=respect_user_gloss,
                )),
                _gen5_min_pair(_gen13_dir_hw(
                    "W/YM/H", "יָמָּ",
                    prefix_forms=["וָ"], prefix_morphs=["CONJ"], prefix_es=["y"],
                    stem_morph="SUBS.M.SG.A", stem_es="mar", strongs="H3220",
                    respect_user_gloss=respect_user_gloss,
                )),
            ] + tail14

    if vrs == 15:
        flat15: list[dict] = []
        for p in pairs:
            for hw in p.get("he_words") or []:
                raw = hw.get("raw") or ""
                if raw == "L/K":
                    continue
                if raw == ")TN/NH":
                    _gen6_split_at_prs(
                        hw,
                        stem_he="אֶתְּנֶ",
                        stem_morph="VERBO.QAL.IMPF.P1.COMMON.SG",
                        stem_es="daré",
                        strongs="H5414",
                        suf_he="נָּה",
                        suf_morph="PRS.P3.F.SG",
                        suf_es="la",
                        respect_user_gloss=respect_user_gloss,
                    )
                elif raw == "W/L/ZR(/K":
                    _gen6_split_at_prs(
                        hw,
                        prefix_forms=["וּ", "לְ"],
                        prefix_morphs=["CONJ", "PREP"],
                        prefix_es=["y", "a"],
                        stem_he="זַרְעֲ",
                        stem_morph="SUBS.M.SG.C",
                        stem_es="simiente",
                        strongs="H2233",
                        suf_he="ךָ",
                        suf_morph="PRS.P2.M.SG",
                        suf_es="tu",
                        respect_user_gloss=respect_user_gloss,
                    )
                elif raw in ("(D", "(WLM"):
                    continue
                flat15.append(hw)
        if not any((h.get("raw") or "") == "(D/(WLM" for h in flat15):
            flat15.extend([
                {
                    "raw": "(D",
                    "he_form": "עַד\u05be",
                    "he_morph": "PREP",
                    "strongs": "H5704",
                    "es": "hasta",
                    "es_source": "patch",
                },
                {
                    "raw": "(WLM",
                    "he_form": "עוֹלָם",
                    "he_morph": "SUBS.M.SG.A",
                    "strongs": "H5769",
                    "es": "siempre",
                    "es_source": "patch",
                },
            ])
        pairs[:] = [_gen5_min_pair(h) for h in flat15]

    if vrs == 17:
        flat17: list[dict] = []
        for p in pairs:
            for hw in p.get("he_words") or []:
                raw = hw.get("raw") or ""
                if raw == "L/K":
                    continue
                if raw == ")TN/NH":
                    _gen6_split_at_prs(
                        hw,
                        stem_he="אֶתְּנֶ",
                        stem_morph="VERBO.QAL.IMPF.P1.COMMON.SG",
                        stem_es="daré",
                        strongs="H5414",
                        suf_he="נָּה",
                        suf_morph="PRS.P3.F.SG",
                        suf_es="la",
                        respect_user_gloss=respect_user_gloss,
                    )
                flat17.append(hw)
        pairs[:] = [_gen5_min_pair(h) for h in flat17]

    if vrs == 16:
        for p in pairs:
            for hw in p.get("he_words") or []:
                if (hw.get("raw") or "") == "ZR(/K":
                    _gen6_split_at_prs(
                        hw,
                        stem_he="זַרְעֲ",
                        stem_morph="SUBS.M.SG.C",
                        stem_es="simiente",
                        strongs="H2233",
                        suf_he="ךָ",
                        suf_morph="PRS.P2.M.SG",
                        suf_es="tu",
                        respect_user_gloss=respect_user_gloss,
                    )

    _gen13_finalize_loose_vav(verse)


def _gen13_finalize_prep_prs(verse: dict) -> None:
    """Post-merge: prep+PRS fusionada; conserva he_form del prs (OSHB)."""
    _gen12_finalize_prep_prs(verse)


def _gen13_apply_v9_gr_unicode(pairs: list[dict]) -> None:
    """Reasigna gr_unicode CATSS en 13:9 (rebuild OSHB desplaza índices)."""
    im_seen = False
    for p in pairs:
        raws = [h.get("raw") or "" for h in p.get("he_words") or []]
        raw = raws[0] if raws else ""
        if raw == "H/L)":
            p["gr_unicode"] = "οὐκ ἰδοὺ"
        elif raw == "KL":
            p["gr_unicode"] = "πᾶσα"
        elif raw == "H/)RC":
            p["gr_unicode"] = "ἡ γῆ"
        elif raw == "L/PN/YK":
            p["gr_unicode"] = "ἐναντίον σού ἐστιν"
        elif raw == "=PRS/K":
            p["gr_unicode"] = ""
        elif raw == "HPRD":
            p["gr_unicode"] = "διαχωρίσθητι"
        elif raw == "N)":
            p["gr_unicode"] = "ἀπ' ἐμοῦ"
        elif raw == "M/(L/Y":
            p["gr_unicode"] = ""
        elif raw == ")M" and not im_seen:
            p["gr_unicode"] = "εἰ σὺ"
            im_seen = True
        elif raw == "H/&M)L":
            p["gr_unicode"] = "εἰς"
        elif raw == "W/)YMN/H":
            p["gr_unicode"] = "ἀριστερά"
        elif raw == "W/)M":
            p["gr_unicode"] = "ἐγὼ εἰς δεξιά"
        elif raw == "H/YMYN":
            p["gr_unicode"] = "εἰ δὲ"
        elif raw == "W/)&M)YL/H":
            p["gr_unicode"] = "σὺ εἰς δεξιά, ἐγὼ εἰς ἀριστερά"


def _gen13_apply_v2_gk_add_yn(pairs: list[dict]) -> None:
    """13:2 — fusiona gk_add ἦν en KBD (gr_unicode, elimina par gk_add)."""
    gk_idx = next(
        (
            i for i, p in enumerate(pairs)
            if p.get("kind") == "gk_add"
            and (p.get("gr_unicode") or "").strip() in ("ἦν", "ην")
        ),
        None,
    )
    if gk_idx is None:
        return
    gk_gr = (pairs[gk_idx].get("gr_unicode") or "").strip()
    for p in pairs:
        for hw in p.get("he_words") or []:
            if (hw.get("raw") or "") != "KBD":
                continue
            stem_gr = (p.get("gr_unicode") or "").strip()
            p["gr_unicode"] = _san_gr(f"{gk_gr} {stem_gr}".strip())
            pairs.pop(gk_idx)
            return


def _fix_gen13_lxx_align(verse: dict) -> None:
    """B8 — reparto LXX por morfema tras splits OSHB cap. 13."""
    vrs = verse.get("verse", 0)
    pairs = verse.get("pairs", [])
    if vrs == 9:
        _gen13_apply_v9_gr_unicode(pairs)
    for p in pairs:
        _sync_pair_gr_lxx(p)
    if vrs == 2:
        _gen13_apply_v2_gk_add_yn(pairs)
        for p in pairs:
            if any((h.get("raw") or "") == "KBD" for h in p.get("he_words") or []):
                _sync_pair_gr_lxx(p)
                break
    for p in pairs:
        _sync_pair_gr_lxx(p)
    for p in pairs:
        for hw in p.get("he_words") or []:
            if _is_meta_hw(hw):
                continue
            _post_sync_gr_hw(hw)
    _fix_lxx_align_verse(verse)


def _fix_gen13_es_glosses(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Correcciones de glosas / metadatos español cap. 13."""
    vrs = verse.get("verse", 0)
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            raw = hw.get("raw") or ""
            morph = hw.get("he_morph") or ""

            if _is_nprop_morph(morph) and _gen5_he_key(hw) == "אברם":
                if (hw.get("es") or "").strip().lower() != "abram":
                    _set_es_patch(hw, "Abram", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

            elif raw == "BYT" and _is_nprop_morph(morph) and not (hw.get("strongs") or "").strip():
                hw["strongs"] = "H1008"
                if not (hw.get("es") or "").strip():
                    _set_es_patch(hw, "Betel", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

            elif raw == ")L" and _is_nprop_morph(morph) and not (hw.get("strongs") or "").strip():
                hw["strongs"] = "H410"
                if not (hw.get("es") or "").strip():
                    _set_es_patch(hw, "El", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

            elif raw == "W/Y)MR" and not (hw.get("strongs") or "").strip():
                hw["strongs"] = "H559"
                if not (hw.get("es") or "").strip():
                    _set_es_patch(hw, "dijo", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

            elif raw == ")N$YM" and not (hw.get("strongs") or "").strip():
                hw["strongs"] = "H582"
                if not (hw.get("es") or "").strip():
                    _set_es_patch(hw, "hombres", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

            elif raw == ")XYM" and not (hw.get("strongs") or "").strip():
                hw["strongs"] = "H251"
                if not (hw.get("es") or "").strip():
                    _set_es_patch(hw, "hermanos", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

            elif raw == "W/BYN" and not (hw.get("strongs") or "").strip():
                hw["strongs"] = "H996"
                if not (hw.get("es") or "").strip():
                    _set_es_patch(hw, "entre", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

            elif raw == "KY" and not (hw.get("strongs") or "").strip():
                hw["strongs"] = "H3588"
                if not (hw.get("es") or "").strip():
                    _set_es_patch(hw, "porque", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

            elif raw == "H/L)":
                pfx_e = list(hw.get("prefix_es") or [])
                pfx_m = list(hw.get("prefix_morphs") or [])
                if pfx_m and pfx_m[0] == "PART.INTERR" and not (pfx_e[0] if pfx_e else "").strip():
                    if pfx_e:
                        pfx_e[0] = "¿"
                    else:
                        pfx_e = ["¿"]
                    hw["prefix_es"] = pfx_e
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw.setdefault("es_source", "patch")

            elif raw == "M/(L/Y":
                _gen6_split_at_prs(
                    hw,
                    prefix_forms=["מֵ"],
                    prefix_morphs=["PREP"],
                    prefix_es=["de"],
                    stem_he="עָל",
                    stem_morph="PREP",
                    stem_es="sobre",
                    strongs="H5921",
                    suf_he="י",
                    suf_morph="PRS.P1.COMMON.SG",
                    suf_es="mí",
                    respect_user_gloss=respect_user_gloss,
                )

            elif vrs == 11 and raw == ")Y$":
                hw["strongs"] = "H376"
                hw["he_morph"] = "SUBS.M.SG.A"
                _set_es_patch(hw, "cada uno", respect_user=respect_user_gloss)
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif raw == "ZR(/K" and _gen5_he_key(hw).startswith("זר"):
                _gen6_split_at_prs(
                    hw,
                    stem_he="זַרְעֲ",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="simiente",
                    strongs="H2233",
                    suf_he="ךָ",
                    suf_morph="PRS.P2.M.SG",
                    suf_es="tu",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "ZR(/K" and not (hw.get("strongs") or "").strip():
                _gen6_split_at_prs(
                    hw,
                    stem_he="זַרְעֲ",
                    stem_morph="SUBS.M.SG.C",
                    stem_es="simiente",
                    strongs="H2233",
                    suf_he="ךָ",
                    suf_morph="PRS.P2.M.SG",
                    suf_es="tu",
                    respect_user_gloss=respect_user_gloss,
                )

            elif raw == "L/MNWT" and not (hw.get("strongs") or "").strip():
                hw["strongs"] = "H4487"
                if not (hw.get("es") or "").strip():
                    _set_es_patch(hw, "contar", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

    _fix_gen5_numeric_glosses(verse, respect_user_gloss=respect_user_gloss)


def _patch_gen13(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Parches estructurales Génesis cap. 13 — separación Abram/Lot."""
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            _gen13_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)

    _fix_gen13_oshb_align(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen13_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if not (
                (hw.get("raw") or "").endswith("}")
                or (
                    hw.get("es_source") == "patch_meta"
                    and not _strip_niqqud(hw.get("he_form") or "")
                )
            )
        ]
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if (hw.get("he_form") or "").strip()
            or (hw.get("prefix_forms") or [])
            or (hw.get("prs_suffix") or {}).get("he_form")
            or hw.get("raw") in ("=L/MYN/W", "=L/MYN/HW", "=VAV")
        ]

    verse["pairs"] = [
        p for p in verse.get("pairs", [])
        if p.get("he_words")
        or (p.get("gr_unicode") or "").strip()
        or p.get("kind") == "heb_omit"
    ]

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _gen5_preserve_fused_ot(hw, respect_user_gloss=respect_user_gloss)
            _merge_prs_reading_gloss(hw)

    _gen13_reapply_oshb_splits(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen13_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _merge_prs_reading_gloss(hw)
            _drop_redundant_prs_suffix(hw)

    _fix_gen13_lxx_align(verse)
    normalize_verse_maqaf(verse)
    sanitize_verse_he_forms(verse)
    _sanitize_catss_pairs(verse)


# Génesis cap. 14 — Abram y los reyes (plantilla cap. 13)
def _gen14_zeboyim_place_pairs(*, respect_user_gloss: bool = False, verse: int | None = None) -> list[dict]:
    """צביים + צְבוֹיִם/צְבוֹיִים tras מֶלֶךְ (14:2, 14:8)."""
    _ = respect_user_gloss
    second_he = "צְבוֹיִם" if verse == 8 else "צְבוֹיִים"
    return [
        _gen5_min_pair({
            "raw": "ZBYM",
            "he_form": "צביים",
            "he_morph": "NPROP",
            "strongs": "",
            "es": "Zeboim",
            "es_source": "patch",
        }),
        _gen5_min_pair({
            "raw": "ZBYM",
            "he_form": second_he,
            "he_morph": "NPROP",
            "strongs": "",
            "es": "Zeboim",
            "es_source": "patch",
        }),
    ]


def _gen14_zeboyim_king_pairs(*, respect_user_gloss: bool = False) -> list[dict]:
    """מֶלֶךְ + צביים + צְבוֹיִם."""
    return [
        _gen5_min_pair({
            "raw": "MLK",
            "he_form": "מֶלֶךְ",
            "he_morph": "SUBS.M.SG.C",
            "strongs": "H4428",
            "es": "rey",
            "es_source": "patch",
        }),
        *_gen14_zeboyim_place_pairs(respect_user_gloss=respect_user_gloss),
    ]


def _gen14_repair_achi_hw(hw: dict, *, respect_user_gloss: bool = False) -> None:
    """אֲחִי — hermano de (no אֲח truncado)."""
    _clear_hw_prefix_slots(hw)
    hw["he_form"] = "אֲחִי"
    hw["he_morph"] = "SUBS.M.SG.C"
    hw["strongs"] = "H251"
    _set_es_patch(hw, "hermano de", respect_user=respect_user_gloss)
    hw.pop("prs_suffix", None)
    if not (respect_user_gloss and _has_user_gloss(hw)):
        hw["es_source"] = "patch"


def _gen14_fix_zeboim_spelling(verse: dict) -> None:
    """OSHB 14:2 → צבויים; 14:8 → צבוים (segunda forma del par)."""
    vrs = verse.get("verse", 0)
    if vrs not in (2, 8):
        return
    second = "צְבוֹיִם" if vrs == 8 else "צְבוֹיִים"
    seen = 0
    for p in verse.get("pairs", []):
        for hw in p.get("he_words") or []:
            if hw.get("raw") != "ZBYM":
                continue
            seen += 1
            if seen == 2:
                hw["he_form"] = second


def _gen14_finalize_loose_vav(verse: dict) -> None:
    """Fusiona waw sueltos (=VAV / .)( / stems ו) en prefijo o par anterior."""
    for p in verse.get("pairs", []):
        hws = p.get("he_words") or []
        out: list[dict] = []
        for hw in hws:
            raw = hw.get("raw") or ""
            he = (hw.get("he_form") or "").strip()
            if raw in ("=VAV", ".)(", "=PRS/V") or (raw.startswith("=") and he in ("ו", "וְ", "וּ")):
                if raw == "=VAV" and len(hws) == 1:
                    out.append(hw)
                    continue
                if out:
                    prev = out[-1]
                    if not (prev.get("prefix_forms") or []):
                        prev["prefix_forms"] = ["וְ"]
                        prev["prefix_morphs"] = ["CONJ"]
                        prev["prefix_es"] = ["y"]
                    elif "ו" not in "".join(prev.get("prefix_forms") or []):
                        prev["prefix_forms"] = list(prev.get("prefix_forms") or []) + ["וְ"]
                        prev["prefix_morphs"] = list(prev.get("prefix_morphs") or []) + ["CONJ"]
                        prev["prefix_es"] = list(prev.get("prefix_es") or []) + ["y"]
                continue
            if he in ("ו", "וְ", "וּ") and not (hw.get("prefix_forms") or []):
                if out:
                    prev = out[-1]
                    pfx = list(prev.get("prefix_forms") or [])
                    pfx.append(he if he != "ו" else "וְ")
                    prev["prefix_forms"] = pfx
                    prev["prefix_morphs"] = list(prev.get("prefix_morphs") or []) + ["CONJ"]
                    prev["prefix_es"] = list(prev.get("prefix_es") or []) + ["y"]
                continue
            out.append(hw)
        p["he_words"] = out


def _gen14_apply_prs_splits(hw: dict, *, respect_user_gloss: bool = False) -> None:
    """Splits PRS / compuestos frecuentes cap. 14."""
    _gen13_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)
    raw = hw.get("raw") or ""

    if raw == ")XY":
        _gen14_repair_achi_hw(hw, respect_user_gloss=respect_user_gloss)

    elif raw == ")XY/W":
        _gen6_split_at_prs(
            hw,
            stem_he="אָחִי",
            stem_morph="SUBS.M.SG.C",
            stem_es="hermano de",
            strongs="H251",
            suf_he="וֹ",
            suf_morph="PRS.P3.M.SG",
            suf_es="su",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "BN/)XY":
        _clear_hw_prefix_slots(hw)
        hw["he_form"] = "בֶּן"
        hw["he_morph"] = "SUBS.M.SG.C"
        hw["strongs"] = "H1121"
        _set_es_patch(hw, "hijo", respect_user=respect_user_gloss)
        hw.pop("prs_suffix", None)
        if not (respect_user_gloss and _has_user_gloss(hw)):
            hw["es_source"] = "patch"

    elif raw == "RK$/W":
        _gen6_split_at_prs(
            hw,
            stem_he="רְכֻשׁ",
            stem_morph="SUBS.M.SG.C",
            stem_es="bienes",
            strongs="H7399",
            suf_he="וֹ",
            suf_morph="PRS.P3.M.SG",
            suf_es="su",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "W/)T" and _gen5_he_key(hw).startswith("את"):
        _gen6_split_at_prs(
            hw,
            prefix_forms=["וְ"],
            prefix_morphs=["CONJ"],
            prefix_es=["y"],
            stem_he="אֵת",
            stem_morph="PART.OBJ.DIR",
            stem_es="",
            strongs="H853",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == ")KL/M":
        _gen6_split_at_prs(
            hw,
            stem_he="אָכְל",
            stem_morph="SUBS.M.SG.C",
            stem_es="comida",
            strongs="H400",
            suf_he="ָם",
            suf_morph="PRS.P3.M.PL",
            suf_es="su",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "W/YK/M":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["וַ"],
            prefix_morphs=["CONJ"],
            prefix_es=["y"],
            stem_he="יַּכּ",
            stem_morph="VERBO.HIF.WAYYIQT.P3.M.SG",
            stem_es="hirió",
            strongs="H5221",
            suf_he="ֵּם",
            suf_morph="PRS.P3.M.PL",
            suf_es="los",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "W/YRDP/M":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["וַ"],
            prefix_morphs=["CONJ"],
            prefix_es=["y"],
            stem_he="יִּרְדְּפ",
            stem_morph="VERBO.QAL.WAYYIQT.P3.M.SG",
            stem_es="persiguió",
            strongs="H7291",
            suf_he="ֵם",
            suf_morph="PRS.P3.M.PL",
            suf_es="los",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "H$YB":
        _clear_hw_prefix_slots(hw)
        hw["he_form"] = "הֵשִׁיב"
        hw["he_morph"] = "VERBO.HIF.PERF.P3.M.SG"
        hw["strongs"] = "H7725"
        _set_es_patch(hw, "restituyó", respect_user=respect_user_gloss)
        hw.pop("prs_suffix", None)
        if not (respect_user_gloss and _has_user_gloss(hw)):
            hw["es_source"] = "patch"

    elif raw == "CR/YK":
        _gen6_split_at_prs(
            hw,
            stem_he="צָרֶי",
            stem_morph="SUBS.M.PL.C",
            stem_es="adversarios",
            strongs="H6862",
            suf_he="ךָ",
            suf_morph="PRS.P2.M.SG",
            suf_es="tus",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "YD/Y":
        _gen6_split_at_prs(
            hw,
            stem_he="יָד",
            stem_morph="SUBS.BOTH.SG.C",
            stem_es="mano",
            strongs="H3027",
            suf_he="ִי",
            suf_morph="PRS.P1.COMMON.SG",
            suf_es="mi",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "B/YD/K":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["בְּ"],
            prefix_morphs=["PREP"],
            prefix_es=["en"],
            stem_he="יָד",
            stem_morph="SUBS.BOTH.SG.C",
            stem_es="mano",
            strongs="H3027",
            suf_he="ֶךָ",
            suf_morph="PRS.P2.M.SG",
            suf_es="tu",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "XLQ/M":
        _gen6_split_at_prs(
            hw,
            stem_he="חֶלְק",
            stem_morph="SUBS.M.SG.C",
            stem_es="parte",
            strongs="H2506",
            suf_he="ָם",
            suf_morph="PRS.P3.M.PL",
            suf_es="su",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "W/YBRK/HW":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["וַ"],
            prefix_morphs=["CONJ"],
            prefix_es=["y"],
            stem_he="יְבָרְכ",
            stem_morph="VERBO.PIEL.WAYYIQT.P3.M.SG",
            stem_es="bendijo",
            strongs="H1288",
            suf_he="ֵהוּ",
            suf_morph="PRS.P3.M.SG",
            suf_es="lo",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "XNYK/YW":
        _gen6_split_at_prs(
            hw,
            stem_he="חֲנִיכ",
            stem_morph="SUBS.M.PL.C",
            stem_es="servidores",
            strongs="H2593",
            suf_he="ָי",
            suf_morph="PRS.P1.COMMON.SG",
            suf_es="mis",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "BYT/W":
        _gen6_split_at_prs(
            hw,
            stem_he="בֵית",
            stem_morph="SUBS.M.SG.C",
            stem_es="casa",
            strongs="H1004",
            suf_he="וֹ",
            suf_morph="PRS.P3.M.SG",
            suf_es="su",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "L/QR)T/W":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["לִ"],
            prefix_morphs=["PREP"],
            prefix_es=["a"],
            stem_he="קְרָאת",
            stem_morph="VERBO.QAL.INFC",
            stem_es="recibir",
            strongs="H7125",
            suf_he="וֹ",
            suf_morph="PRS.P3.M.SG",
            suf_es="lo",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "B/L(DY":
        _gen6_split_at_prs(
            hw,
            stem_he="בִּלְעָד",
            stem_morph="PREP",
            stem_es="excepto",
            strongs="H1107",
            suf_he="ַי",
            suf_morph="PRS.P1.COMMON.SG",
            suf_es="mí",
            respect_user_gloss=respect_user_gloss,
        )


def _gen14_reapply_oshb_splits(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Reaplica splits cap. 14 tras merge PRS / Pass 16."""
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            _gen14_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)


def _fix_gen14_oshb_align(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Post-proceso cap. 14 — orden, tokens rotos, inserciones OSHB (B2)."""
    vrs = verse.get("verse", 0)
    pairs = verse.get("pairs", [])

    _fix_gen5_w_prefixes(verse)
    _fix_gen5_after_maot(verse)

    if vrs in (2, 8):
        cleaned: list[dict] = []
        for p in pairs:
            hws = [
                hw for hw in (p.get("he_words") or [])
                if (hw.get("raw") or "") not in (".)(", "=PRS/V")
            ]
            if not hws:
                if (p.get("gr_unicode") or "").strip() or p.get("kind") == "gk_add":
                    cleaned.append({"kind": p.get("kind", "align"), "he_words": [], "gr_unicode": p.get("gr_unicode") or ""})
                continue
            cp = dict(p)
            cp["he_words"] = hws
            cleaned.append(cp)
        out2: list[dict] = []
        for i, p in enumerate(cleaned):
            out2.append(p)
            hws = p.get("he_words") or []
            if not hws:
                continue
            raws = {h.get("raw") for h in hws}
            j = i + 1
            while j < len(cleaned) and not (cleaned[j].get("he_words") or []):
                j += 1
            nxt_r: set[str] = set()
            if j < len(cleaned):
                nxt_r = {h.get("raw") for h in (cleaned[j].get("he_words") or [])}
            prev_r: set[str] = set()
            for k in range(i - 1, -1, -1):
                ph = cleaned[k].get("he_words") or []
                if ph:
                    prev_r = {h.get("raw") for h in ph}
                    break
            insert = False
            if vrs == 2 and raws == {"MLK"} and nxt_r & {"W/MLK", "BL("}:
                insert = True
            elif (
                vrs == 8
                and raws <= {"W/MLK"}
                and len(hws) == 1
                and prev_r & {")DMH"}
                and (nxt_r & {"BL(", "W/MLK"})
            ):
                insert = True
            if insert:
                out2.extend(
                    _gen14_zeboyim_place_pairs(
                        respect_user_gloss=respect_user_gloss,
                        verse=vrs,
                    )
                )
        pairs[:] = [p for p in out2 if (p.get("he_words") or []) or (p.get("gr_unicode") or "").strip()]

    if vrs == 5:
        for p in pairs:
            hws = p.get("he_words") or []
            cleaned: list[dict] = []
            for hw in hws:
                raw = hw.get("raw") or ""
                if raw == "QRNYN" and _gen5_he_key(hw) == "ה":
                    continue
                if raw == "B/($TRT":
                    _clear_hw_prefix_slots(hw)
                    hw["prefix_forms"] = ["בְּ"]
                    hw["prefix_morphs"] = ["PREP"]
                    hw["prefix_es"] = ["en"]
                    hw["he_form"] = "עַשְׁתְּרֹת"
                    hw["he_morph"] = "NPROP"
                    hw["strongs"] = "H6255"
                    _set_es_patch(hw, "Ashtarot", respect_user=respect_user_gloss)
                elif raw == "QRNYM":
                    hw["he_form"] = "קַרְנַיִם"
                    hw["he_morph"] = "NPROP"
                    hw["strongs"] = "H7163"
                    _set_es_patch(hw, "Karnaim", respect_user=respect_user_gloss)
                    hw.pop("prefix_forms", None)
                cleaned.append(hw)
            p["he_words"] = cleaned
        for p in pairs:
            for hw in p.get("he_words") or []:
                if hw.get("raw") == "B/$WH":
                    _clear_hw_prefix_slots(hw)
                    hw["prefix_forms"] = ["בְּ"]
                    hw["prefix_morphs"] = ["PREP"]
                    hw["prefix_es"] = ["en"]
                    hw["he_form"] = "שָׁוֵה"
                    hw["he_morph"] = "NPROP"
                    hw["strongs"] = "H7741"
                    _set_es_patch(hw, "Shaveh", respect_user=respect_user_gloss)

    if vrs == 7:
        for p in pairs:
            for hw in p.get("he_words") or []:
                if hw.get("raw") == "B/XCCN":
                    p["he_words"] = [
                        {
                            "raw": "B/XCCN",
                            "prefix_forms": ["בְּ"],
                            "prefix_morphs": ["PREP"],
                            "prefix_es": ["en"],
                            "he_form": "חַצְצֹן",
                            "he_morph": "NPROP",
                            "strongs": "H2709",
                            "es": "Hazazon",
                            "es_source": "patch",
                        },
                        {
                            "raw": "TMR",
                            "he_form": "תָּמָר",
                            "he_morph": "NPROP",
                            "strongs": "H8559",
                            "es": "Tamar",
                            "es_source": "patch",
                        },
                    ]

    if vrs == 11:
        for p in pairs:
            hws = [
                hw for hw in (p.get("he_words") or [])
                if (hw.get("raw") or "") not in (".)(", "=VAV")
            ]
            p["he_words"] = hws

    if vrs == 12:
        grs12 = [p.get("gr_unicode") or "" for p in pairs]
        flat12: list[dict] = [
            {"raw": "W/YQXW", "prefix_forms": ["וַ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "יִּקְחוּ", "he_morph": "VERBO.QAL.WAYYIQT.P3.M.PL", "strongs": "H3947",
             "es": "tomaron", "es_source": "patch"},
            {"raw": ")T", "he_form": "אֶת\u05be", "he_morph": "PART.OBJ.DIR", "strongs": "H853", "es": ""},
            {"raw": "LW+", "he_form": "לוֹט", "he_morph": "NPROP", "strongs": "H3876", "es": "Lot", "es_source": "patch"},
            {"raw": "W/)T", "prefix_forms": ["וְ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "אֵת\u05be", "he_morph": "PART.OBJ.DIR", "strongs": "H853", "es": ""},
            {"raw": "RK$/W", "he_form": "רְכֻשׁ", "he_morph": "SUBS.M.SG.C", "strongs": "H7399",
             "es": "bienes", "es_source": "patch",
             "prs_suffix": {"he_form": "וֹ", "he_morph": "PRS.P3.M.SG", "es": "su"}},
            {"raw": "BN", "he_form": "בֶּן\u05be", "he_morph": "SUBS.M.SG.C", "strongs": "H1121", "es": "hijo", "es_source": "patch"},
            {"raw": ")XY", "he_form": "אֲחִי", "he_morph": "SUBS.M.SG.C", "strongs": "H251",
             "es": "hermano de", "es_source": "patch"},
            {"raw": ")BRM", "he_form": "אַבְרָם", "he_morph": "NPROP", "strongs": "H87",
             "es": "Abram", "es_source": "patch"},
            {"raw": "W/YLKW", "prefix_forms": ["וַ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "יֵּלֵכוּ", "he_morph": "VERBO.QAL.WAYYIQT.P3.M.PL", "strongs": "H3212",
             "es": "fueron", "es_source": "patch"},
            {"raw": "W/HW)", "prefix_forms": ["וְ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "הוּא", "he_morph": "PRON.PERS.P3.M.SG", "strongs": "H1931", "es": "él", "es_source": "patch"},
            {"raw": "Y$B", "he_form": "יֹשֵׁב", "he_morph": "VERBO.QAL.PTCA.M.SG.A", "strongs": "H3427",
             "es": "habitaba", "es_source": "patch"},
            {"raw": "B/SDM", "prefix_forms": ["בְּ"], "prefix_morphs": ["PREP"], "prefix_es": ["en"],
             "he_form": "סְדֹם", "he_morph": "NPROP", "strongs": "H5467", "es": "Sodoma", "es_source": "patch"},
        ]
        pairs[:] = []
        gi = 0
        for hw in flat12:
            np = _gen5_min_pair(hw)
            if gi < len(grs12) and grs12[gi]:
                np["gr_unicode"] = grs12[gi]
                gi += 1
            pairs.append(np)

    if vrs == 13:
        flat_src = [hw for p in pairs for hw in p.get("he_words") or []]
        flat13: list[dict] = []
        for idx, hw in enumerate(flat_src):
            raw = hw.get("raw") or ""
            if raw in (")XY", "W/)XY"):
                _gen14_repair_achi_hw(hw, respect_user_gloss=respect_user_gloss)
            flat13.append(hw)
            if raw == ")$KL":
                nxt_raw = (flat_src[idx + 1].get("raw") or "") if idx + 1 < len(flat_src) else ""
                if nxt_raw != "=VAV":
                    flat13.append({
                        "raw": "=VAV", "he_form": "ו", "he_morph": "CONJ",
                        "strongs": "", "es": "y", "es_source": "patch",
                    })
        if flat13:
            grs13 = [p.get("gr_unicode") or "" for p in pairs]
            pairs[:] = []
            gi = 0
            for hw in flat13:
                np = _gen5_min_pair(hw)
                if gi < len(grs13) and grs13[gi]:
                    np["gr_unicode"] = grs13[gi]
                    gi += 1
                pairs.append(np)

    if vrs == 14:
        grs14 = [p.get("gr_unicode") or "" for p in pairs]
        flat14: list[dict] = [
            {"raw": "W/Y$M(", "prefix_forms": ["וַ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "יִּשְׁמַע", "he_morph": "VERBO.QAL.WAYYIQT.P3.M.SG", "strongs": "H8085",
             "es": "oyó", "es_source": "patch"},
            {"raw": ")BRM", "he_form": "אַבְרָם", "he_morph": "NPROP", "strongs": "H87",
             "es": "Abram", "es_source": "patch"},
            {"raw": "KY", "he_form": "כִּי", "he_morph": "CONJ", "strongs": "H3588", "es": "que", "es_source": "patch"},
            {"raw": "N$BH", "he_form": "נִשְׁבָּה", "he_morph": "VERBO.NIF.PERF.P3.M.SG", "strongs": "H7617",
             "es": "fue tomado", "es_source": "patch"},
            {"raw": ")XY", "he_form": "אָחִי", "he_morph": "SUBS.M.SG.C", "strongs": "H251",
             "es": "hermano mío", "es_source": "patch"},
            {"raw": "=VAV", "he_form": "ו", "he_morph": "CONJ", "strongs": "", "es": "y", "es_source": "patch"},
            {"raw": "W/YRQ", "prefix_forms": ["וַ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "יָּרֶק", "he_morph": "VERBO.QAL.WAYYIQT.P3.M.SG", "strongs": "H7324",
             "es": "desplegó", "es_source": "patch"},
            {"raw": ")T", "he_form": "אֶת\u05be", "he_morph": "PART.OBJ.DIR", "strongs": "H853", "es": ""},
            {"raw": "XNYK/YW", "he_form": "חֲנִיכָי", "he_morph": "SUBS.M.PL.C", "strongs": "H2593",
             "es": "servidores míos", "es_source": "patch"},
            {"raw": "=VAV", "he_form": "ו", "he_morph": "CONJ", "strongs": "", "es": "y", "es_source": "patch"},
            {"raw": "YLYDY", "he_form": "יְלִידֵי", "he_morph": "SUBS.M.PL.C", "strongs": "H3211",
             "es": "nascidos", "es_source": "patch"},
            {"raw": "BYT/W", "he_form": "בֵית", "he_morph": "SUBS.M.SG.C", "strongs": "H1004", "es": "casa",
             "es_source": "patch",
             "prs_suffix": {"he_form": "וֹ", "he_morph": "PRS.P3.M.SG", "es": "su"}},
            {"raw": "$MNH", "he_form": "שְׁמֹנָה", "he_morph": "NUM.CARD.M.SG.A", "strongs": "H8083",
             "es": "ocho", "es_source": "patch"},
            {"raw": "(&R", "he_form": "עָשָׂר", "he_morph": "NUM.CARD.M.SG.A", "strongs": "H6240",
             "es": "diez", "es_source": "patch"},
            {"raw": "W/$L$", "prefix_forms": ["וּ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "שְׁלֹשׁ", "he_morph": "CFSA", "strongs": "H7969", "es": "tres", "es_source": "patch"},
            {"raw": "M)WT", "he_form": "מֵאוֹת", "he_morph": "NUM.CARD.BOTH.PL.A", "strongs": "H3967",
             "es": "cientos", "es_source": "patch"},
            {"raw": "W/YRDP", "prefix_forms": ["וַ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "יִּרְדֹּף", "he_morph": "VERBO.QAL.WAYYIQT.P3.M.SG", "strongs": "H7291",
             "es": "persiguió", "es_source": "patch"},
            {"raw": "(D", "he_form": "עַד\u05be", "he_morph": "PREP", "strongs": "H5704", "es": "hasta", "es_source": "patch"},
            {"raw": "DN", "he_form": "דָּן", "he_morph": "NPROP", "strongs": "H1835", "es": "Dan", "es_source": "patch"},
        ]
        pairs[:] = []
        gi = 0
        for hw in flat14:
            np = _gen5_min_pair(hw)
            if gi < len(grs14) and grs14[gi]:
                np["gr_unicode"] = grs14[gi]
                gi += 1
            pairs.append(np)

    if vrs == 16:
        for p in pairs:
            for hw in p.get("he_words") or []:
                if hw.get("raw") == "W/RK$/W":
                    _gen6_split_at_prs(
                        hw,
                        prefix_forms=["וּ"],
                        prefix_morphs=["CONJ"],
                        prefix_es=["y"],
                        stem_he="רְכֻשׁ",
                        stem_morph="SUBS.M.SG.C",
                        stem_es="bienes",
                        strongs="H7399",
                        suf_he="וֹ",
                        suf_morph="PRS.P3.M.SG",
                        suf_es="su",
                        respect_user_gloss=respect_user_gloss,
                    )
                elif hw.get("raw") == "W/GM":
                    _clear_hw_prefix_slots(hw)
                    hw["prefix_forms"] = ["וְ"]
                    hw["prefix_morphs"] = ["CONJ"]
                    hw["prefix_es"] = ["y"]
                    hw["he_form"] = "גַם"
                    hw["he_morph"] = "PART.AFF"
                    hw["strongs"] = "H1571"
                    _set_es_patch(hw, "también", respect_user=respect_user_gloss)
                    hw.pop("prs_suffix", None)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

    if vrs == 17:
        flat_src = [hw for p in pairs for hw in p.get("he_words") or []]
        flat17: list[dict] = []
        for idx, hw in enumerate(flat_src):
            if hw.get("raw") == "L(MR" and _gen5_he_key(hw) in ("ו", "וְ"):
                continue
            flat17.append(hw)
            if (hw.get("raw") or "") == "$WB/W":
                nxt_raw = (flat_src[idx + 1].get("raw") or "") if idx + 1 < len(flat_src) else ""
                if nxt_raw != "=VAV":
                    flat17.append({
                        "raw": "=VAV", "he_form": "ו", "he_morph": "CONJ",
                        "strongs": "", "es": "y", "es_source": "patch",
                    })
        if flat17:
            grs17 = [p.get("gr_unicode") or "" for p in pairs]
            pairs[:] = []
            gi = 0
            for hw in flat17:
                np = _gen5_min_pair(hw)
                if gi < len(grs17) and grs17[gi]:
                    np["gr_unicode"] = grs17[gi]
                    gi += 1
                pairs.append(np)

    if vrs == 19:
        grs19 = [p.get("gr_unicode") or "" for p in pairs]
        flat19: list[dict] = [
            {"raw": "W/YBRK/HW", "prefix_forms": ["וַ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "יְבָרְכ", "he_morph": "VERBO.PIEL.WAYYIQT.P3.M.SG", "strongs": "H1288",
             "es": "bendijo", "es_source": "patch",
             "prs_suffix": {"he_form": "ֵהוּ", "he_morph": "PRS.P3.M.SG", "es": "lo"}},
            {"raw": "W/Y)MR", "prefix_forms": ["וַ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "יֹּאמַר", "he_morph": "VERBO.QAL.WAYYIQT.P3.M.SG", "strongs": "H559",
             "es": "dijo", "es_source": "patch"},
            {"raw": "BRWK", "he_form": "בָּרוּךְ", "he_morph": "VERBO.QAL.PTCP.M.SG.A", "strongs": "H1288",
             "es": "bendito", "es_source": "patch"},
            {"raw": ")BRM", "he_form": "אַבְרָם", "he_morph": "NPROP", "strongs": "H87",
             "es": "Abram", "es_source": "patch"},
            {"raw": "L/)L", "prefix_forms": ["לְ"], "prefix_morphs": ["PREP"], "prefix_es": ["a"],
             "he_form": "אֵל", "he_morph": "SUBS.M.SG.A", "strongs": "H410", "es": "Dios", "es_source": "patch"},
            {"raw": "(LYWN", "he_form": "עֶלְיֹון", "he_morph": "ADJ.M.SG.A", "strongs": "H5945",
             "es": "Altísimo", "es_source": "patch"},
            {"raw": "QNH", "he_form": "קֹנֵה", "he_morph": "VERBO.QAL.PTCA.M.SG.C", "strongs": "H7069",
             "es": "creador", "es_source": "patch"},
            {"raw": "$MYM", "he_form": "שָׁמַיִם", "he_morph": "SUBS.M.PL.A", "strongs": "H8064",
             "es": "cielos", "es_source": "patch"},
            {"raw": "W/)RC", "prefix_forms": ["וָ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "אָרֶץ", "he_morph": "SUBS.BOTH.SG.A", "strongs": "H776", "es": "tierra", "es_source": "patch"},
        ]
        pairs[:] = []
        gi = 0
        for hw in flat19:
            np = _gen5_min_pair(hw)
            if gi < len(grs19) and grs19[gi]:
                np["gr_unicode"] = grs19[gi]
                gi += 1
            pairs.append(np)

    if vrs == 20:
        for p in pairs:
            p["he_words"] = [hw for hw in (p.get("he_words") or []) if (hw.get("raw") or "") != "L/W"]

    if vrs == 21:
        for p in pairs:
            hws = [hw for hw in (p.get("he_words") or []) if (hw.get("raw") or "") not in ("L/K", "H/NP$")]
            if len(hws) == 1 and hws[0].get("raw") == "H/NP$":
                continue
            p["he_words"] = hws
        pairs[:] = [
            p for p in pairs
            if (p.get("he_words") or [])
            or (p.get("gr_unicode") or "").strip()
        ]

    if vrs == 23:
        for p in pairs:
            p["he_words"] = [
                hw for hw in (p.get("he_words") or [])
                if (hw.get("raw") or "") != "L/K"
            ]

    if vrs == 24:
        for p in pairs:
            for hw in p.get("he_words") or []:
                if hw.get("raw") == ")$KL":
                    _clear_hw_prefix_slots(hw)
                    hw["he_form"] = "אֶשְׁכֹּל"
                    hw["he_morph"] = "NPROP"
                    hw["strongs"] = "H812"
                    _set_es_patch(hw, "Eshcol", respect_user=respect_user_gloss)

    drop_raws: set[str] = {".)(", "=PRS/V"}
    if vrs in (21, 23):
        drop_raws.add("L/K")
    if vrs == 21:
        drop_raws.add("W/L/HM")
    for p in pairs:
        p["he_words"] = [hw for hw in (p.get("he_words") or []) if (hw.get("raw") or "") not in drop_raws]

    _gen14_finalize_loose_vav(verse)

    _gen14_fix_zeboim_spelling(verse)

    verse["pairs"] = [
        p for p in pairs
        if p.get("he_words")
        or (p.get("gr_unicode") or "").strip()
        or p.get("kind") in ("heb_omit", "gk_add")
    ]


def _gen14_finalize_prep_prs(verse: dict) -> None:
    _gen12_finalize_prep_prs(verse)


def _fix_gen14_lxx_align(verse: dict) -> None:
    """B8 — reparto LXX por morfema tras splits OSHB cap. 14."""
    vrs = verse.get("verse", 0)
    pairs = verse.get("pairs", [])
    if vrs == 14:
        _gen14_v14_ylydy_yrdp_lxx(pairs)
    if vrs == 17:
        _gen14_v17_move_touto_en_gr(pairs)
    _fix_lxx_align_verse(verse)
    if vrs == 17:
        for p in pairs:
            for hw in p.get("he_words") or []:
                if (hw.get("raw") or "") in (")L", "HW)", "(MQ", "=VAV"):
                    _post_sync_gr_hw(hw)
            _repair_pair_lxx_coverage(p)


def _fix_gen14_es_glosses(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Correcciones de glosas / metadatos español cap. 14 (B5)."""
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            raw = hw.get("raw") or ""
            morph = hw.get("he_morph") or ""

            if _is_nprop_morph(morph) and _gen5_he_key(hw) == "אברם":
                if (hw.get("es") or "").strip().lower() != "abram":
                    _set_es_patch(hw, "Abram", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

            elif _is_nprop_morph(morph) and _gen5_he_key(hw) == "לוט":
                if (hw.get("es") or "").strip().lower() != "lot":
                    _set_es_patch(hw, "Lot", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

    _fix_gen5_numeric_glosses(verse, respect_user_gloss=respect_user_gloss)


def _patch_gen14(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Parches estructurales Génesis cap. 14 — guerra de reyes / Melquisedec."""
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            _gen14_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)

    _fix_gen14_oshb_align(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen14_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if not (
                (hw.get("raw") or "").endswith("}")
                or (
                    hw.get("es_source") == "patch_meta"
                    and not _strip_niqqud(hw.get("he_form") or "")
                )
            )
        ]
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if (hw.get("he_form") or "").strip()
            or (hw.get("prefix_forms") or [])
            or (hw.get("prs_suffix") or {}).get("he_form")
            or hw.get("raw") in ("=L/MYN/W", "=L/MYN/HW", "=VAV")
        ]

    verse["pairs"] = [
        p for p in verse.get("pairs", [])
        if p.get("he_words")
        or (p.get("gr_unicode") or "").strip()
        or p.get("kind") == "heb_omit"
    ]

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _gen5_preserve_fused_ot(hw, respect_user_gloss=respect_user_gloss)
            _merge_prs_reading_gloss(hw)

    _gen14_reapply_oshb_splits(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen14_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _merge_prs_reading_gloss(hw)
            _drop_redundant_prs_suffix(hw)

    _fix_gen14_lxx_align(verse)
    _gen14_finalize_loose_vav(verse)
    normalize_verse_maqaf(verse)
    sanitize_verse_he_forms(verse)
    _gen14_fix_zeboim_spelling(verse)
    _sanitize_catss_pairs(verse)


# Génesis cap. 15 — alianza con Abram (B0 + B2)
def _gen15_trim_prefix_lengths(verse: dict) -> None:
    """Trunca prefix_morphs/es/gr al len(prefix_forms) — evita pfx_array_desalineado."""
    for p in verse.get("pairs", []):
        for hw in p.get("he_words") or []:
            raw = hw.get("raw") or ""
            if raw == "GKADD":
                for key in (
                    "prefix_forms", "prefix_morphs", "prefix_es", "prefix_gr",
                    "prefix_labels", "prefix_tier", "prefix_unicode", "prefixes",
                ):
                    hw.pop(key, None)
                continue
            pf = hw.get("prefix_forms") or []
            if not pf:
                for key in ("prefix_morphs", "prefix_es", "prefix_gr"):
                    hw.pop(key, None)
                continue
            n = len(pf)
            for key in ("prefix_morphs", "prefix_es", "prefix_gr"):
                lst = hw.get(key)
                if isinstance(lst, list) and len(lst) != n:
                    hw[key] = (list(lst) + ([""] if key == "prefix_es" else ["?"]) * n)[:n]
            if raw in ("B/YHWH", "L/ZR(/K") and n == 1:
                hw["prefix_morphs"] = [(hw.get("prefix_morphs") or ["PREP"])[0]]
                hw["prefix_es"] = [(hw.get("prefix_es") or [""])[0]]


def _gen15_strip_dot_prefixes(verse: dict) -> None:
    """Quita prefijos fantasma (·) que desalinean tokens OSHB."""
    for p in verse.get("pairs", []):
        for hw in p.get("he_words") or []:
            hf = (hw.get("he_form") or "").strip()
            if hf.startswith("·"):
                hw["he_form"] = hf.lstrip("·")
            pfx_f = hw.get("prefix_forms") or []
            if not pfx_f:
                continue
            pfx_m = hw.get("prefix_morphs") or []
            pfx_e = hw.get("prefix_es") or []
            clean_f: list[str] = []
            clean_m: list[str] = []
            clean_e: list[str] = []
            for i, pf in enumerate(pfx_f):
                if not pf or _strip_niqqud(pf) in ("", "·"):
                    continue
                clean_f.append(pf)
                if i < len(pfx_m):
                    clean_m.append(pfx_m[i])
                if i < len(pfx_e):
                    clean_e.append(pfx_e[i])
            if clean_f:
                hw["prefix_forms"] = clean_f
                hw["prefix_morphs"] = clean_m
                hw["prefix_es"] = clean_e
            else:
                hw.pop("prefix_forms", None)
                hw.pop("prefix_morphs", None)
                hw.pop("prefix_es", None)


def _gen15_promote_gkadd(verse: dict) -> None:
    """Pares GKADD sin hebreo → kind gk_add (LXX-only, fuera de flatten OSHB)."""
    out: list[dict] = []
    for p in verse.get("pairs", []):
        hws = p.get("he_words") or []
        gk_hws = [hw for hw in hws if (hw.get("raw") or "") == "GKADD"]
        if p.get("kind") == "gk_add" or gk_hws:
            gr = (p.get("gr_unicode") or "").strip()
            if not gr:
                for hw in gk_hws:
                    gr = (hw.get("gr_word") or "").strip()
                    if gr:
                        break
            if gr:
                out.append({
                    "kind": "gk_add",
                    "he_words": [],
                    "gr_unicode": gr,
                    "he": "",
                    "he_unicode": "",
                    "he_stem_unicode": "",
                    "prefixes": "",
                })
                continue
        out.append(p)
    verse["pairs"] = out


def _gen15_scrub_post_lxx_meta(verse: dict) -> None:
    """Quita prefix_gr/morphs/es huérfanos que _fix_lxx_align puede dejar sin prefix_forms."""
    for p in verse.get("pairs", []):
        for hw in p.get("he_words") or []:
            _sync_hw_prefix_slots(hw)
            if not (hw.get("prefix_forms") or []):
                for key in ("prefix_gr", "prefix_labels", "prefix_tier", "prefix_unicode", "prefixes"):
                    hw.pop(key, None)


def _gen15_rebuild_pairs(
    pairs: list,
    flat: list[dict],
    *,
    gk_after: dict[int, str] | None = None,
) -> None:
    """Reconstruye pares alineados OSHB; gk_after inserta gk_add tras índice flat."""
    old = list(pairs)
    gr_queue: list[str] = []
    gk_grs: list[str] = []
    for p in old:
        if p.get("kind") == "gk_add":
            continue
        gr = (p.get("gr_unicode") or "").strip()
        hws = p.get("he_words") or []
        if len(hws) == 1 and (hws[0].get("raw") or "") == "GKADD":
            if gr:
                gk_grs.append(gr)
            continue
        if gr:
            gr_queue.append(gr)

    pairs[:] = []
    gki = 0
    for fi, hw in enumerate(flat):
        np = _gen5_min_pair(dict(hw))
        if gr_queue:
            np["gr_unicode"] = gr_queue.pop(0)
        pairs.append(np)
        extra_gr = (gk_after or {}).get(fi)
        if extra_gr:
            pairs.append({"kind": "gk_add", "he_words": [], "gr_unicode": extra_gr})
        elif not gk_after and gki < len(gk_grs) and fi == len(flat) - 1:
            pairs.append({"kind": "gk_add", "he_words": [], "gr_unicode": gk_grs[gki]})
            gki += 1
    while gr_queue:
        pairs.append({"kind": "align", "he_words": [], "gr_unicode": gr_queue.pop(0)})
    if not gk_after:
        while gki < len(gk_grs):
            pairs.append({"kind": "gk_add", "he_words": [], "gr_unicode": gk_grs[gki]})
            gki += 1


def _gen15_apply_prs_splits(hw: dict, *, respect_user_gloss: bool = False) -> None:
    """Splits PRS / compuestos frecuentes cap. 15."""
    _gen14_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)
    raw = hw.get("raw") or ""

    if raw == "&KR/K":
        _gen6_split_at_prs(
            hw,
            stem_he="שְׂכָר",
            stem_morph="SUBS.M.SG.C",
            stem_es="recompensa",
            strongs="H7939",
            suf_he="ךָ",
            suf_morph="PRS.P2.M.SG",
            suf_es="tu",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == ")DNY":
        _gen6_split_at_prs(
            hw,
            stem_he="אֲדֹנ",
            stem_morph="SUBS.M.PL.C",
            stem_es="Adonai",
            strongs="H113",
            suf_he="י",
            suf_morph="PRS.P1.COMMON.SG",
            suf_es="",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "BYT/Y":
        _gen6_split_at_prs(
            hw,
            stem_he="בֵית",
            stem_morph="SUBS.M.SG.C",
            stem_es="casa",
            strongs="H1004",
            suf_he="ִי",
            suf_morph="PRS.P1.COMMON.SG",
            suf_es="mía",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "YYR$/K":
        _gen6_split_at_prs(
            hw,
            stem_he="יִֽירָשׁ",
            stem_morph="VERBO.QAL.IMPF.P3.M.SG",
            stem_es="heredará",
            strongs="H3423",
            suf_he="ךָ",
            suf_morph="PRS.P2.M.SG",
            suf_es="te",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "M/M(/YK":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["מִ"],
            prefix_morphs=["PREP"],
            prefix_es=["de"],
            stem_he="מֵּעֶי",
            stem_morph="SUBS.M.PL.C",
            stem_es="entrañas",
            strongs="H4578",
            suf_he="ךָ",
            suf_morph="PRS.P2.M.SG",
            suf_es="tus",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "HWC)TY/K":
        _gen6_split_at_prs(
            hw,
            stem_he="הוֹצֵאתִי",
            stem_morph="VERBO.HIF.PERF.P1.COMMON.SG",
            stem_es="saqué",
            strongs="H3318",
            suf_he="ךָ",
            suf_morph="PRS.P2.M.SG",
            suf_es="te",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "L/R$T/H":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["לְ"],
            prefix_morphs=["PREP"],
            prefix_es=["para"],
            stem_he="רִשְׁתּ",
            stem_morph="VERBO.QAL.INFC",
            stem_es="heredar",
            strongs="H3423",
            suf_he="ָהּ",
            suf_morph="PRS.P3.F.SG",
            suf_es="la",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "BTR/W":
        _gen6_split_at_prs(
            hw,
            stem_he="בִּתְר",
            stem_morph="SUBS.M.SG.C",
            stem_es="parte",
            strongs="H1336",
            suf_he="וֹ",
            suf_morph="PRS.P3.M.SG",
            suf_es="su",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "W/(BDW/M":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["וַ"],
            prefix_morphs=["CONJ"],
            prefix_es=["y"],
            stem_he="עֲבָדוּ",
            stem_morph="VERBO.QAL.PERF.P3.COMMON.PL",
            stem_es="servirán",
            strongs="H5647",
            suf_he="ם",
            suf_morph="PRS.P3.M.PL",
            suf_es="los",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "W/(NW":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["וְ"],
            prefix_morphs=["CONJ"],
            prefix_es=["y"],
            stem_he="עִנּוּ",
            stem_morph="VERBO.PIEL.PERF.P3.COMMON.PL",
            stem_es="afligirán",
            strongs="H6031",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw in (")YRH/NH", ")YR$/NH"):
        _gen6_split_at_prs(
            hw,
            stem_he="אִֽירָשׁ",
            stem_morph="VERBO.QAL.IMPF.P1.COMMON.SG",
            stem_es="heredaré",
            strongs="H3423",
            suf_he="נָּה",
            suf_morph="PRS.P3.F.SG",
            suf_es="la",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "QCH/H":
        _gen6_split_at_prs(
            hw,
            stem_he="קְחָ",
            stem_morph="VERBO.QAL.IMPV.P2.M.SG",
            stem_es="toma",
            strongs="H3947",
            suf_he="ה",
            suf_morph="SUF.PARAG.HE",
            suf_es="",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "H/$MYM/H":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["הַ"],
            prefix_morphs=["ART"],
            prefix_es=["los"],
            stem_he="שָּׁמַיְמָ",
            stem_morph="SUBS.M.PL.A",
            stem_es="cielos",
            strongs="H8064",
            suf_he="ה",
            suf_morph="SUF.DIR.HE",
            suf_es="",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "B/MXZH":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["בַּ"],
            prefix_morphs=["PREP"],
            prefix_es=["en"],
            stem_he="מַּחֲזֶה",
            stem_morph="SUBS.M.SG.A",
            stem_es="visión",
            strongs="H4236",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "L/)MR" and not (hw.get("prefix_forms") or []):
        _gen6_split_at_prs(
            hw,
            prefix_forms=["לֵ"],
            prefix_morphs=["PREP"],
            prefix_es=[""],
            stem_he="אמֹר",
            stem_morph="VERBO.QAL.INFC",
            stem_es="diciendo",
            strongs="H559",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == ")BWT/K":
        _gen6_split_at_prs(
            hw,
            stem_he="אֲבֹתֶי",
            stem_morph="SUBS.M.PL.C",
            stem_es="padres",
            strongs="H1",
            suf_he="ךָ",
            suf_morph="PRS.P2.M.SG",
            suf_es="tus",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "L/)BRM":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["לְ"],
            prefix_morphs=["PREP"],
            prefix_es=["a"],
            stem_he="אַבְרָם",
            stem_morph="NPROP",
            stem_es="Abram",
            strongs="H87",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "R(/HW":
        _gen6_split_at_prs(
            hw,
            stem_he="רֵעֵ",
            stem_morph="SUBS.M.SG.C",
            stem_es="compañero",
            strongs="H7453",
            suf_he="הוּ",
            suf_morph="PRS.P3.M.SG",
            suf_es="su",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw in ("W/YX$B/H", "W/YX$BM/H"):
        _gen6_split_at_prs(
            hw,
            prefix_forms=["וַ"],
            prefix_morphs=["CONJ"],
            prefix_es=["y"],
            stem_he="יַּחְשְׁב",
            stem_morph="VERBO.QAL.WAYYIQT.P3.M.SG",
            stem_es="contó",
            strongs="H2803",
            suf_he="ֶהָ",
            suf_morph="PRS.P3.F.SG",
            suf_es="la",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw in ("QCH/H", "QXH"):
        _gen6_split_at_prs(
            hw,
            stem_he="קְחָ",
            stem_morph="VERBO.QAL.IMPV.P2.M.SG",
            stem_es="toma",
            strongs="H3947",
            suf_he="ה",
            suf_morph="SUF.PARAG.HE",
            suf_es="",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw in (")BWT/K", ")BT/YK"):
        _gen6_split_at_prs(
            hw,
            stem_he="אֲבֹתֶי",
            stem_morph="SUBS.M.PL.C",
            stem_es="padres",
            strongs="H1",
            suf_he="ךָ",
            suf_morph="PRS.P2.M.SG",
            suf_es="tus",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "HYBWSY":
        _gen6_split_at_prs(
            hw,
            prefix_forms=["הַ"],
            prefix_morphs=["ART"],
            prefix_es=["el"],
            stem_he="יְבוּסִי",
            stem_morph="GENT.M.SG.A",
            stem_es="jebuseo",
            strongs="H2983",
            respect_user_gloss=respect_user_gloss,
        )

    elif raw == "ZR(/K" and _gen5_he_key(hw).startswith("זר"):
        _gen6_split_at_prs(
            hw,
            stem_he="זַרְעֲ",
            stem_morph="SUBS.M.SG.C",
            stem_es="simiente",
            strongs="H2233",
            suf_he="ךָ",
            suf_morph="PRS.P2.M.SG",
            suf_es="tu",
            respect_user_gloss=respect_user_gloss,
        )


def _gen15_reapply_oshb_splits(verse: dict, *, respect_user_gloss: bool = False) -> None:
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            _gen15_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)


def _gen15_finalize_loose_vav(verse: dict) -> None:
    _gen13_finalize_loose_vav(verse)


_GEN15_OSHB_LEN: dict[int, int] = {
    1: 23, 2: 20, 3: 15, 4: 22, 5: 30, 6: 8, 7: 22, 8: 11,
    9: 18, 10: 26, 11: 12, 12: 19, 13: 24, 14: 16, 15: 12,
    16: 13, 17: 22, 18: 30, 21: 16,
}

# Orden CATSS (raw, ocurrencia) para reordenar pares tras LXX/merge PRS.
_GEN15_PAIR_ORDER: dict[int, list[tuple[str, int]]] = {
    9: [
        ("W/Y)MR", 1), (")L/YW", 1), ("QCH/H", 1), ("QXH", 1), ("(GLH", 1), ("M/L/T", 1),
        ("M/$L$T", 1), ("W/(Z", 1), ("($", 1), ("M/L/T", 2), ("M/$L$T", 2),
        ("W/)YL", 1), ("M/L/$", 1), ("W/TR", 1), ("TRYGH", 1), ("W/GWZL", 1),
        ("W/PRSH", 1), ("PRSH", 1),
    ],
    11: [
        ("W/YRD", 1), ("H/(Y+", 1), ("(L", 1), ("H/PGRYM", 1),
        ("W/Y$B", 1), (")T/M", 1), (")BRM", 1),
    ],
    14: [
        ("W/GM", 1), (")T", 1), ("H/GWY", 1), (")$R", 1), ("Y(BDW", 1), ("DN", 1),
        (")NKY", 1), ("W/)XRY", 1), ("KN", 1), ("YC)W", 1), ("B/RK$", 1), ("GDWL", 1),
    ],
    15: [
        ("W/)TH", 1), ("TBW)", 1), (")L", 1), (")BT/YK", 1), ("B/$LWM", 1), ("TQBR", 1),
        ("B/&YBH", 1), ("+WBH", 1),
    ],
    16: [
        ("W/DWR", 1), ("RBY(Y", 1), ("Y$WBW", 1), ("HNH", 1), ("KY", 1), ("L)", 1),
        ("$LM", 1), ("(WN", 1), ("H/)MRY", 1), ("(D", 1), ("HNH", 2),
    ],
    18: [
        ("B/YWM", 1), ("H/HW)", 1), ("KRT", 1), ("YHWH", 1), (")T", 1), (")BRM", 1),
        ("BRYT", 1), ("L/)MR", 1), ("L/ZR(/K", 1), ("NTTY", 1), (")T", 2), ("H/)RC", 1),
        ("H/Z)T", 1), ("M/NHR", 1), ("MCRYM", 1), ("(D", 1), ("H/NHR", 1), ("H/GDL", 1),
        ("NHR", 1), ("PRT", 1),
    ],
    21: [
        ("W/)T", 1), ("H/)MRY", 1), ("W/)T", 2), ("H/KN(NY", 1),
        ("W/)T", 3), ("H/GRG$Y", 1), ("W/)T", 4), ("HYBWSY", 1),
    ],
}


def _gen15_reorder_pairs(pairs: list, vrs: int) -> bool:
    """Reordena pares align según _GEN15_PAIR_ORDER (conserva gk_add al final)."""
    spec = _GEN15_PAIR_ORDER.get(vrs)
    if not spec:
        return False
    align = [p for p in pairs if p.get("kind") != "gk_add"]
    gk = [p for p in pairs if p.get("kind") == "gk_add"]
    by_raw: dict[str, list[dict]] = {}
    for p in align:
        raw = _gen15_pair_raw(p)
        by_raw.setdefault(raw, []).append(p)
    occ: dict[str, int] = {}
    out: list[dict] = []
    for raw, need_occ in spec:
        occ[raw] = occ.get(raw, 0) + 1
        cands = by_raw.get(raw, [])
        if len(cands) < occ[raw]:
            continue
        out.append(cands[occ[raw] - 1])
    if len(out) < len(spec) - 2:
        return False
    used = set(id(p) for p in out)
    for p in align:
        if id(p) not in used:
            out.append(p)
    pairs[:] = out + gk
    return True


def _gen15_he_token_count(verse: dict) -> int:
    from audit_gen5_struct import flatten_verse
    from audit_gen6_struct import expand_fused_ot_he_data

    return len(expand_fused_ot_he_data(flatten_verse(verse)))


def _gen15_oshb_diff(verse: dict) -> list:
    from audit_gen5_struct import flatten_verse, align_oshb, norm_he
    from audit_gen6_struct import expand_fused_ot_he_data
    from book_config import resolve
    import json

    vrs = verse.get("verse", 0)
    if not hasattr(_gen15_oshb_diff, "_oshb15"):
        oshb_path = resolve("genesis").oshb_dir / "15.json"
        _gen15_oshb_diff._oshb15 = json.loads(oshb_path.read_text(encoding="utf-8"))
    oshb_v = _gen15_oshb_diff._oshb15.get(str(vrs), {})
    flat = flatten_verse(verse)
    data_he = expand_fused_ot_he_data(flat)
    oshb_he = [norm_he(x) for x in oshb_v.get("forms", []) if norm_he(x)]
    return align_oshb(data_he, oshb_he)


def _gen15_needs_flat_rebuild(verse: dict) -> bool:
    if _gen15_pairs_corrupt(verse):
        return True
    if _gen15_oshb_diff(verse):
        return True
    vrs = verse.get("verse", 0)
    if vrs in _GEN15_OSHB_LEN:
        return not _gen15_flat_ok(verse)
    return False


def _gen15_flat_ok(verse: dict) -> bool:
    vrs = verse.get("verse", 0)
    exp = _GEN15_OSHB_LEN.get(vrs)
    if exp is None:
        return True
    return _gen15_he_token_count(verse) == exp


def _gen15_pairs_corrupt(verse: dict) -> bool:
    """Detecta acumulación gk_add / pares rotos post-merge (no cubierto por flat_ok)."""
    vrs = verse.get("verse", 0)
    pairs = verse.get("pairs") or []
    gk = sum(1 for p in pairs if p.get("kind") == "gk_add")
    limits = {1: 2, 4: 2, 5: 2, 13: 6}
    if vrs in limits and gk > limits[vrs]:
        return True
    if vrs == 13 and len(pairs) > 22:
        return True
    return False


def _gen15_pair_raw(p: dict) -> str:
    hws = p.get("he_words") or []
    return (hws[0].get("raw") or "") if hws else ""


def _gen15_apply_lxx_gr_map(pairs: list, vrs: int) -> None:
    """Reasigna gr_unicode CATSS/Rahlfs tras rebuild OSHB (raw + ocurrencia)."""
    _specs: dict[int, list[tuple[str, int, str]]] = {
        1: [
            (")XR", 1, "μετὰ δὲ"), ("H/DBRYM", 1, "τὰ ῥήματα"), ("H/)LH", 1, "ταῦτα"),
            ("HYH", 1, "ἐγενήθη"), ("DBR", 1, "ῥῆμα"), ("YHWH", 1, "κυρίου"),
            (")L", 1, "πρὸς"), (")BRM", 1, "Αβραμ"), ("B/MXZH", 1, "ἐν ὁράματι"),
            ("L/)MR", 1, "λέγων"), (")L", 2, "μὴ"), ("TYR)", 1, "φοβοῦ"),
            (")BRM", 2, "Αβραμ"), (")NKY", 1, "ἐγὼ"), ("MGN", 1, "ὑπερασπίζω σου"),
            ("&KR/K", 1, "ὁ μισθός σου"), ("HRBH", 1, "πολὺς"), ("", 0, "ἔσται"),
            ("M)D", 1, "σφόδρα"),
        ],
        3: [
            ("W/Y)MR", 1, "καὶ εἶπεν"), (")BRM", 1, "Αβραμ"), ("L)", 1, ""),
            ("ZR(", 1, "σπέρμα"), ("W/HNH", 1, "ὁ"), ("BN", 1, "δὲ"),
            ("BYT/Y", 1, "οἰκογενής μου"), ("YWR$", 1, "κληρονομήσει"), (")T/Y", 1, "με"),
            ("HN", 1, "ἐπειδὴ"), ("NTTH", 1, "οὐκ"), ("", 0, "ἐμοὶ ἔδωκας"),
        ],
        4: [
            ("W/HNH", 1, "καὶ εὐθὺς"), ("DBR", 1, "φωνὴ"), ("YHWH", 1, "κυρίου"),
            ("", 0, "ἐγένετο"), (")L/YW", 1, "πρὸς αὐτὸν"), ("L/)MR", 1, "λέγων"),
            ("L)", 1, "οὐ"), ("YYR$/K", 1, "κληρονομήσει"), ("", 0, "σε"),
            ("ZH", 1, "οὗτος"), ("KY", 1, "ἀλλ᾿"), (")M", 1, "ὃς"),
            ("YC)", 1, "ἐξελεύσεται"), ("M/M(/YK", 1, "ἐκ σοῦ"),
            ("HW)", 1, "οὗτος"), ("YYR$/K", 2, "κληρονομήσει"), ("", 0, "σε"),
        ],
        5: [
            ("W/YWC)", 1, "ἐξήγαγεν"), ("", 0, "δὲ"), (")T/W", 1, "αὐτὸν"), ("H/XWC/H", 1, "ἔξω"),
            ("W/Y)MR", 1, "καὶ εἶπεν"), ("", 0, "αὐτῷ"), ("HB+", 1, "ἀνάβλεψον"),
            ("N)", 1, "δὴ"), ("H/$MYM/H", 1, "εἰς τὸν οὐρανὸν"),
            ("W/SPR", 1, "καὶ ἀρίθμησον"), ("H/KWKBYM", 1, "τοὺς ἀστέρας"),
            (")M", 1, "εἰ"), ("TWKL", 1, "δυνήσῃ"), ("L/SPR", 1, "ἐξαριθμῆσαι"),
            (")T/M", 1, "αὐτούς"), ("W/Y)MR", 2, "καὶ εἶπεν"),
            ("KH", 1, "οὕτως"), ("YHYH", 1, "ἔσται"), ("ZR(/K", 1, "τὸ σπέρμα σου"),
        ],
        6: [
            ("W/H)MN", 1, "καὶ ἐπίστευσεν Αβραμ"), ("B/YHWH", 1, "τῷ θεῷ"),
            ("W/YX$B/H", 1, "καὶ ἐλογίσθη αὐτῷ"), ("W/YX$BM/H", 1, "καὶ ἐλογίσθη αὐτῷ"),
            ("CDQH", 1, "εἰς δικαιοσύνην"),
        ],
        9: [
            ("W/Y)MR", 1, "εἶπεν"), ("", 0, "δὲ"), (")L/YW", 1, "αὐτῷ"),
            ("QCH/H", 1, "λαβέ"), ("QXH", 1, "λαβέ"), ("L/Y", 1, "μοι"),
            ("(GLH", 1, "δάμαλιν"), ("PRLH", 1, "δάμαλιν"), ("M/L/T", 1, "τριετίζουσαν"),
            ("M/$L$T", 1, "τριετίζουσαν"), ("W/(Z", 1, "αἶγα"), ("($", 1, "αἶγα"),
            ("M/L/T", 2, "τριετίζουσαν"), ("M/$L$T", 2, "τριετίζουσαν"),
            ("W/)YL", 1, "κριὸν"), ("W/AYL", 1, "κριὸν"), (")YL", 1, "κριὸν"),
            ("M/L/$", 1, "τριετίζοντα"), ("M/L/T", 3, "τριετίζοντα"),
            ("W/TR", 1, "τρυγόνα"), ("W/TRYGH", 1, "τρυγόνα"), ("TRYGH", 1, "τρυγόνα"),
            ("W/GWZL", 1, "περιστεράν"), ("W/PRSH", 1, "περιστεράν"), ("PRSH", 1, "περιστεράν"),
        ],
        11: [
            ("W/YRD", 1, "κατέβη"), ("", 0, "δὲ"), ("H/(Y+", 1, "ὄρνεα"), ("(L", 1, "ἐπὶ"),
            ("H/PGRYM", 1, "τὰ σώματα τὰ διχοτομήματα αὐτῶν"),
            ("W/Y$WB", 1, "συνεκάθισεν"), ("W/Y$B", 1, "συνεκάθισεν"),
            (")T/M", 1, "αὐτοῖς"), (")BRM", 1, "Αβραμ"),
        ],
        12: [
            ("W/YHY", 1, "περὶ δὲ"), ("H/$M$", 1, "ἡλίου"), ("L/BW)", 1, "δυσμὰς"),
            ("W/TRDMH", 1, "ἔκστασις"), ("NPLH", 1, "ἐπέπεσεν"), ("(L", 1, "τῷ"),
            (")BRM", 1, "Αβραμ"), ("W/HNH", 1, "καὶ ἰδοὺ"), (")YMH", 1, "φόβος"),
            ("X$KH", 1, "σκοτεινὸς"), ("GDLH", 1, "μέγας"), ("NPLT", 1, "ἐπιπίπτει"),
            ("(L/YW", 1, "αὐτῷ"),
        ],
        13: [
            ("W/Y)MR", 1, "καὶ ἐρρέθη"), ("L/)BRM", 1, "πρὸς Αβραμ"), ("YD(", 1, "γινώσκων"),
            ("TD(", 1, "γνώσῃ"), ("KY", 1, "ὅτι"), ("GR", 1, "πάροικον"), ("YHYH", 1, "ἔσται"),
            ("ZR(/K", 1, "τὸ σπέρμα σου"), ("B/)RC", 1, "ἐν γῇ"), ("L)", 1, "οὐκ ἰδίᾳ"),
            ("W/(BDW/M", 1, "καὶ δουλώσουσιν"), ("W/(NW", 1, "καὶ κακώσουσιν"),
            ("", 0, "αὐτούς"), ("", 0, "καὶ ταπεινώσουσιν αὐτούς"),
            (")RB(", 1, "τετρακόσια"), ("M)WT", 1, "ἔτη"), ("$NH", 1, "ἔτη"),
        ],
        14: [
            ("W/GY", 1, "τὸ δὲ"), (")M", 1, "ἔθνος"), (")$R", 1, "ᾧ"), ("Y/(BD", 1, "ἐὰν"),
            ("W/(BDW/M", 1, "δουλεύσωσιν"), ("W/DN", 1, "κρινῶ"), (")NY", 1, "ἐγώ"),
            ("W/HNH", 1, "μετὰ δὲ ταῦτα"), ("YC)", 1, "ἐξελεύσονται"),
            ("M/M(/YK", 1, "ὧδε"), ("HW)", 1, "μετὰ"), ("YYR$/K", 1, "ἀποσκευῆς πολλῆς"),
        ],
        15: [
            (")T/H", 1, "σὺ δὲ"), ("W/HLK", 1, "ἀπελεύσῃ"), (")L", 1, "πρὸς"),
            ("H/ABWT", 1, "τοὺς πατέρας σου"), (")BWT/K", 1, "μετ᾿"), ("B/$LM", 1, "εἰρήνης"),
            ("QBR", 1, "ταφεὶς"), ("B/)RC", 1, "ἐν"), ("B/QRH", 1, "γήρει"), ("+WB", 1, "καλῷ"),
        ],
        16: [
            ("W/DWR", 1, "τετάρτη"), ("RBY(Y", 1, "γενεὰ"), ("Y$WBW", 1, "ἀποστραφήσονται"),
            ("HNH", 1, "ὧδε"), ("KY", 1, "οὔπω"), ("L)", 1, "γὰρ"),
            ("$LM", 1, "ἀναπεπλήρωνται"), ("(WN", 1, "αἱ"), ("H/)MRY", 1, "ἁμαρτίαι"),
            ("(D", 1, "τῶν"), ("HNH", 2, "Αμορραίων"), ("", 0, "ἕως τοῦ νῦν"),
        ],
        18: [
            ("B/YWM", 1, "ἐν τῇ ἡμέρᾳ"), ("H/HW)", 1, "ἐκείνῃ"), ("KRT", 1, "διέθετο"),
            ("YHWH", 1, "κύριος"), (")BRM", 1, "τῷ Αβραμ"), ("BRYT", 1, "διαθήκην"),
            ("L/)MR", 1, "λέγων"), ("L/ZR(/K", 1, "τῷ σπέρματί σου"), ("NTTY", 1, "δώσω"),
            (")T", 1, "τὴν"), ("H/)RC", 1, "γῆν"), ("H/Z)T", 1, "ταύτην"),
            ("M/NHR", 1, "ἀπὸ"), ("NHR", 1, "τοῦ"), ("MCRYM", 1, "ποταμοῦ"),
            ("MCY", 1, "Αἰγύπτου"), ("(D", 1, "ἕως"), ("H/NHR", 1, "τοῦ"),
            ("NHR", 2, "ποταμοῦ"), ("H/GDL", 1, "τοῦ"), ("H/GDL", 2, "μεγάλου"),
            ("NHR", 3, "ποταμοῦ"), ("PRT", 1, "Εὐφράτου"), ("PRTH", 1, "Εὐφράτου"),
        ],
        21: [
            ("W/)T", 1, "καὶ τοὺς"), ("H/)MRY", 1, "Αμορραίους"),
            ("W/)T", 2, "καὶ τοὺς"), ("H/KN(NY", 1, "Χαναναίους"),
            ("", 0, "καὶ τοὺς Ευαίους"),
            ("W/)T", 3, "καὶ τοὺς"), ("H/GRG$Y", 1, "Γεργεσαίους"),
            ("W/)T", 4, "καὶ τοὺς"), ("HYBWSY", 1, "Ιεβουσαίους"),
        ],
    }
    spec = _specs.get(vrs)
    if not spec:
        return

    # Quitar gk_add previos; conservar orden OSHB de pares align/word
    align_pairs: list[dict] = []
    for p in pairs:
        if p.get("kind") == "gk_add":
            continue
        align_pairs.append(p)

    occ: dict[str, int] = {}
    gk_after: list[tuple[int, dict]] = []
    insert_after = -1

    def _match(raw: str, need_occ: int) -> tuple[int, dict] | None:
        count = 0
        for ai, p in enumerate(align_pairs):
            if p.get("_gr_map_used"):
                continue
            hws = p.get("he_words") or []
            if not any((hw.get("raw") or "") == raw for hw in hws):
                continue
            count += 1
            if need_occ and count != need_occ:
                continue
            p["_gr_map_used"] = True
            return ai, p
        return None

    for raw, need_occ, gr in spec:
        if raw == "":
            if gr:
                np: dict = {"kind": "gk_add", "he_words": [], "gr_unicode": gr}
                _gen15_ensure_gk_add_stub(np)
                gk_after.append((insert_after, np))
            continue
        hit = _match(raw, need_occ)
        if not hit:
            continue
        ai, p = hit
        insert_after = ai
        if gr:
            p["gr_unicode"] = gr
        else:
            p["gr_unicode"] = ""

    for p in align_pairs:
        p.pop("_gr_map_used", None)

    gk_by_after: dict[int, list[dict]] = {}
    for after_i, gp in gk_after:
        gk_by_after.setdefault(after_i, []).append(gp)

    out: list[dict] = []
    for ai, p in enumerate(align_pairs):
        out.append(p)
        out.extend(gk_by_after.get(ai, []))
    pairs[:] = out


def _gen15_merge_orphan_gk_add(pairs: list) -> None:
    """Fusiona gk_add de un solo token entre pares align (p. ej. 15:6 αβραμ / αὐτῷ)."""
    i = 0
    while i < len(pairs):
        p = pairs[i]
        if p.get("kind") != "gk_add":
            i += 1
            continue
        gr = (p.get("gr_unicode") or "").strip()
        if not gr or " " in gr:
            i += 1
            continue
        merged = False
        if i > 0 and pairs[i - 1].get("kind") != "gk_add":
            prev = pairs[i - 1]
            prev_gr = (prev.get("gr_unicode") or "").strip()
            prev["gr_unicode"] = _san_gr(f"{prev_gr} {gr}".strip())
            pairs.pop(i)
            merged = True
        elif i + 1 < len(pairs) and pairs[i + 1].get("kind") != "gk_add":
            nxt = pairs[i + 1]
            nxt_gr = (nxt.get("gr_unicode") or "").strip()
            nxt["gr_unicode"] = _san_gr(f"{gr} {nxt_gr}".strip())
            pairs.pop(i)
            merged = True
        if not merged:
            i += 1


def _gen15_lxx_load_surface(vrs: int) -> list[str]:
    from fix_lxx_chapters import load_lxx

    lxx_v = load_lxx(15)
    return [w.get("w", "") for w in lxx_v.get(str(vrs), [])]


def _gen15_lxx_batch(verse: dict, lxx_surface: list[str]) -> None:
    """Dedupe / trim / remainder Rahlfs (fix_lxx_chapters)."""
    from fix_lxx_chapters import (
        dedupe_identical_gk_add,
        inject_lxx_remainder,
        promote_gkadd_stubs,
        promote_pronoun_stubs,
        remove_oversized_gk_add,
        trim_gk_add_extra_tokens,
    )

    remove_oversized_gk_add(verse)
    dedupe_identical_gk_add(verse, lxx_surface)
    promote_gkadd_stubs(verse)
    promote_pronoun_stubs(verse)
    trim_gk_add_extra_tokens(verse, lxx_surface)
    dedupe_identical_gk_add(verse, lxx_surface)
    inject_lxx_remainder(verse, lxx_surface, max_chunk=8, max_passes=2)
    trim_gk_add_extra_tokens(verse, lxx_surface)
    dedupe_identical_gk_add(verse, lxx_surface)


def _gen15_dedupe_gk_add(verse: dict) -> None:
    """Elimina gk_add corruptos o duplicados consecutivos (post-rebuild / merge)."""
    out: list[dict] = []
    prev_gr = ""
    for p in verse.get("pairs", []):
        if p.get("kind") != "gk_add":
            prev_gr = ""
            out.append(p)
            continue
        gr = (p.get("gr_unicode") or "").strip()
        if not gr:
            continue
        if "{" in gr or "}" in gr or "\\" in gr:
            continue
        norm = _norm_gr_token(gr)
        if norm and norm == _norm_gr_token(prev_gr):
            continue
        prev_gr = gr
        np: dict = {"kind": "gk_add", "he_words": [], "gr_unicode": gr}
        _gen15_ensure_gk_add_stub(np)
        out.append(np)
    verse["pairs"] = out


def _gen15_sync_prefix_arrays(verse: dict) -> None:
    for p in verse.get("pairs", []):
        for hw in p.get("he_words") or []:
            _sync_hw_prefix_slots(hw)


def _gen15_finalize_prep_prs(verse: dict) -> None:
    _gen12_finalize_prep_prs(verse)


def _gen15_apply_residual_fixes(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Parches ligeros cap. 15 (sin rebuild flat) — post-merge PRS."""
    vrs = verse.get("verse", 0)
    pairs = verse.get("pairs", [])
    drop_raws = {"L/K", "L/Y", "L/W", ".)(", "=PRS/V"}

    if vrs == 6:
        for p in pairs:
            p["he_words"] = [hw for hw in (p.get("he_words") or []) if (hw.get("raw") or "") not in drop_raws]
        for p in pairs:
            p["he_words"] = [
                hw for hw in (p.get("he_words") or [])
                if (hw.get("he_form") or "").strip() not in ("·", "־")
                or (hw.get("prefix_forms") or [])
                or (hw.get("prs_suffix") or {}).get("he_form")
            ]
        for p in pairs:
            for hw in p.get("he_words") or []:
                raw = hw.get("raw") or ""
                if raw == "B/YHWH":
                    _clear_hw_prefix_slots(hw)
                    hw["prefix_forms"] = ["בַּ"]
                    hw["prefix_morphs"] = ["PREP"]
                    hw["prefix_es"] = ["en"]
                    hw["he_form"] = "יְהוָה"
                    hw["he_morph"] = "NPROP"
                    hw["strongs"] = "H3068"
                    _set_es_patch(hw, "YHWH", respect_user=respect_user_gloss)
                    hw.pop("prs_suffix", None)
                elif raw in ("W/YX$B/H", "W/YX$BM/H"):
                    _gen15_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)
                elif raw == "CDQH":
                    _clear_hw_prefix_slots(hw)
        # Un solo token ויחשבה (OSHB 8 formas)
        seen_yx = False
        new_pairs: list[dict] = []
        for p in pairs:
            raw = _gen15_pair_raw(p)
            if raw in ("W/YX$B/H", "W/YX$BM/H"):
                if seen_yx:
                    continue
                seen_yx = True
            new_pairs.append(p)
        pairs[:] = new_pairs

    elif vrs == 9:
        for p in pairs:
            p["he_words"] = [hw for hw in (p.get("he_words") or []) if (hw.get("raw") or "") not in drop_raws]
        for p in pairs:
            for hw in p.get("he_words") or []:
                raw = hw.get("raw") or ""
                if raw in ("QCH/H", "QXH"):
                    _gen15_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)
                elif raw == ")L/YW":
                    _gen15_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)

    elif vrs == 15:
        for p in pairs:
            for hw in p.get("he_words") or []:
                raw = hw.get("raw") or ""
                if raw in (")BWT/K", ")BT/YK"):
                    _clear_hw_prefix_slots(hw)
                    _gen15_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)

    elif vrs == 16:
        for p in pairs:
            for hw in p.get("he_words") or []:
                raw = hw.get("raw") or ""
                if raw in ("(WN", "HNH"):
                    _clear_hw_prefix_slots(hw)
                if raw == "H/)MRY":
                    hw["prefix_forms"] = ["הָ"]
                    hw["prefix_morphs"] = ["ART"]
                    hw["prefix_es"] = ["el"]

    elif vrs == 18:
        for p in pairs:
            p["he_words"] = [hw for hw in (p.get("he_words") or []) if (hw.get("raw") or "") not in drop_raws]
        for p in pairs:
            for hw in p.get("he_words") or []:
                if (hw.get("raw") or "") == "L/ZR(/K":
                    _gen15_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)

    elif vrs == 21:
        for p in pairs:
            hws = p.get("he_words") or []
            cleaned: list[dict] = []
            for hw in hws:
                raw = hw.get("raw") or ""
                if raw in drop_raws:
                    continue
                if raw == "HYBWSY":
                    _gen15_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)
                cleaned.append(hw)
            p["he_words"] = cleaned
        # OSHB: כנעני antes que גרגשי (pares 1↔2)
        align = [p for p in pairs if p.get("kind") != "gk_add"]
        idx_grg = idx_kn = None
        for i, p in enumerate(align):
            raws = {hw.get("raw") for hw in p.get("he_words") or []}
            if "H/GRG$Y" in raws:
                idx_grg = i
            if "H/KN(NY" in raws:
                idx_kn = i
        if idx_grg is not None and idx_kn is not None and idx_grg < idx_kn:
            align[idx_grg], align[idx_kn] = align[idx_kn], align[idx_grg]
            gk = [p for p in pairs if p.get("kind") == "gk_add"]
            pairs[:] = align + gk

    else:
        for p in pairs:
            p["he_words"] = [
                hw for hw in (p.get("he_words") or [])
                if (hw.get("raw") or "") not in drop_raws
            ]


def _gen15_finalize_b4_hebrew(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """B4 hebreo — prefijos/vav/prep+PRS sin tocar reparto LXX morfémico."""
    _gen15_apply_residual_fixes(verse, respect_user_gloss=respect_user_gloss)
    _gen15_strip_dot_prefixes(verse)
    _gen15_sync_prefix_arrays(verse)
    _gen15_finalize_loose_vav(verse)
    _gen15_sync_prefix_arrays(verse)
    _gen15_finalize_prep_prs(verse)
    _gen15_strip_dot_prefixes(verse)
    _gen15_trim_prefix_lengths(verse)


def _gen15_finalize_b4(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """B4 — cierre hebreo: prefijos, vav sueltos, gk_add, prep+PRS."""
    _gen15_finalize_b4_hebrew(verse, respect_user_gloss=respect_user_gloss)
    _gen15_scrub_post_lxx_meta(verse)
    _gen15_promote_gkadd(verse)
    _gen15_dedupe_gk_add(verse)


def _gen15_ensure_gk_add_stub(p: dict) -> None:
    """gk_add debe tener he_words GKADD para que B8 cuente gr_word."""
    if p.get("kind") != "gk_add":
        return
    gr = (p.get("gr_unicode") or "").strip()
    if not gr:
        return
    hws = p.get("he_words") or []
    if hws and any((h.get("raw") or "") == "GKADD" for h in hws):
        for hw in hws:
            if (hw.get("raw") or "") == "GKADD":
                hw["gr_word"] = gr
                hw.setdefault("gr_source", "patch_lxx")
        return
    p["he_words"] = [
        {
            "raw": "GKADD",
            "gr_word": gr,
            "gr_source": "patch_lxx",
            "es_source": "patch_meta",
        }
    ]


def _fix_gen15_oshb_align(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Post-proceso cap. 15 — orden, tokens rotos, inserciones OSHB (B2)."""
    vrs = verse.get("verse", 0)
    pairs = verse.get("pairs", [])

    _fix_gen5_w_prefixes(verse)
    _fix_gen5_after_maot(verse)
    _gen15_strip_dot_prefixes(verse)

    drop_raws = {"L/K", "L/Y", "L/W", ".)(", "=PRS/V"}
    need_flat = _gen15_needs_flat_rebuild(verse)

    if vrs == 1 and need_flat:
        gk_gr = next(
            (
                (p.get("gr_unicode") or "").strip()
                for p in pairs
                if any((h.get("raw") or "") == "GKADD" for h in (p.get("he_words") or []))
            ),
            "",
        )
        flat1: list[dict] = [
            {"raw": ")XR", "he_form": "אַחַר", "he_morph": "PREP", "strongs": "H310",
             "es": "después", "es_source": "patch"},
            {"raw": "H/DBRYM", "prefix_forms": ["הַ"], "prefix_morphs": ["ART"], "prefix_es": ["los"],
             "he_form": "דְּבָרִים", "he_morph": "SUBS.M.PL.A", "strongs": "H1697",
             "es": "palabras", "es_source": "patch"},
            {"raw": "H/)LH", "prefix_forms": ["הָ"], "prefix_morphs": ["ART"], "prefix_es": ["estas"],
             "he_form": "אֵלֶּה", "he_morph": "PRON.DEM.COMMON.PL", "strongs": "H428",
             "es": "estas", "es_source": "patch"},
            {"raw": "HYH", "he_form": "הָיָה", "he_morph": "VERBO.QAL.PERF.P3.M.SG", "strongs": "H1961",
             "es": "fue", "es_source": "patch"},
            {"raw": "DBR", "he_form": "דְבַר־", "he_morph": "SUBS.M.SG.C", "strongs": "H1697",
             "es": "palabra", "es_source": "patch"},
            {"raw": "YHWH", "he_form": "יְהוָה", "he_morph": "NPROP", "strongs": "H3068",
             "es": "YHWH", "es_source": "patch"},
            {"raw": ")L", "he_form": "אֶל־", "he_morph": "PREP", "strongs": "H413", "es": "a", "es_source": "patch"},
            {"raw": ")BRM", "he_form": "אַבְרָם", "he_morph": "NPROP", "strongs": "H87",
             "es": "Abram", "es_source": "patch"},
            {"raw": "B/MXZH", "prefix_forms": ["בַּ"], "prefix_morphs": ["PREP"], "prefix_es": ["en"],
             "he_form": "מַּחֲזֶה", "he_morph": "SUBS.M.SG.A", "strongs": "H4236",
             "es": "visión", "es_source": "patch"},
            {"raw": "L/)MR", "prefix_forms": ["לֵ"], "prefix_morphs": ["PREP"], "prefix_es": [""],
             "he_form": "אמֹר", "he_morph": "VERBO.QAL.INFC", "strongs": "H559",
             "es": "diciendo", "es_source": "patch"},
            {"raw": ")L", "he_form": "אַל־", "he_morph": "NEG", "strongs": "H408",
             "es": "no", "es_source": "patch"},
            {"raw": "TYR)", "he_form": "תִּירָא", "he_morph": "VERBO.QAL.JUSS.P2.M.SG", "strongs": "H3372",
             "es": "temas", "es_source": "patch"},
            {"raw": ")BRM", "he_form": "אַבְרָם", "he_morph": "NPROP", "strongs": "H87",
             "es": "Abram", "es_source": "patch"},
            {"raw": ")NKY", "he_form": "אָנֹכִי", "he_morph": "PRON.PERS.P1.COMMON.SG", "strongs": "H595",
             "es": "yo", "es_source": "patch"},
            {"raw": "MGN", "he_form": "מָגֵן", "he_morph": "SUBS.BOTH.SG.A", "strongs": "H4043",
             "es": "escudo", "es_source": "patch"},
            {"raw": "&KR/K", "he_form": "שְׂכָר", "he_morph": "SUBS.M.SG.C", "strongs": "H7939",
             "es": "recompensa", "es_source": "patch",
             "prs_suffix": {"he_form": "ךָ", "he_morph": "PRS.P2.M.SG", "es": "tu"}},
            {"raw": "HRBH", "he_form": "הַרְבֵּה", "he_morph": "VERBO.HIF.INFA", "strongs": "H7235",
             "es": "mucho", "es_source": "patch"},
            {"raw": "M)D", "he_form": "מְאֹד", "he_morph": "ADV", "strongs": "H3966",
             "es": "muy", "es_source": "patch"},
        ]
        _gen15_rebuild_pairs(pairs, flat1, gk_after={16: gk_gr} if gk_gr else None)

    elif vrs == 2 and need_flat:
        flat2: list[dict] = [
            {"raw": "W/Y)MR", "prefix_forms": ["וַ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "יֹּאמֶר", "he_morph": "VERBO.QAL.WAYYIQT.P3.M.SG", "strongs": "H559",
             "es": "dijo", "es_source": "patch"},
            {"raw": ")BRM", "he_form": "אַבְרָם", "he_morph": "NPROP", "strongs": "H87",
             "es": "Abram", "es_source": "patch"},
            {"raw": ")DNY", "he_form": "אֲדֹנ", "he_morph": "SUBS.M.PL.C", "strongs": "H113",
             "es": "Adonai", "es_source": "patch",
             "prs_suffix": {"he_form": "י", "he_morph": "PRS.P1.COMMON.SG", "es": ""}},
            {"raw": "YHWH", "he_form": "יֱהוִה", "he_morph": "NPROP", "strongs": "H3068",
             "es": "YHWH", "es_source": "patch"},
            {"raw": "MH", "he_form": "מַה־", "he_morph": "PART.INTERR", "strongs": "H4100",
             "es": "qué", "es_source": "patch"},
            {"raw": "TTN", "he_form": "תִּתֶּן", "he_morph": "VERBO.QAL.IMPF.P2.M.SG", "strongs": "H5414",
             "es": "darás", "es_source": "patch"},
            {"raw": "W/)NKY", "prefix_forms": ["וְ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "אָנֹכִי", "he_morph": "PRON.PERS.P1.COMMON.SG", "strongs": "H595",
             "es": "yo", "es_source": "patch"},
            {"raw": "HWLK", "he_form": "הוֹלֵךְ", "he_morph": "VERBO.QAL.PTCA.M.SG.A", "strongs": "H1980",
             "es": "yendo", "es_source": "patch"},
            {"raw": "(RYRY", "he_form": "עֲרִירִי", "he_morph": "ADJ.M.SG.A", "strongs": "H6185",
             "es": "sin hijo", "es_source": "patch"},
            {"raw": "W/BN", "prefix_forms": ["וּ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "בֶן־", "he_morph": "SUBS.M.SG.C", "strongs": "H1121",
             "es": "hijo", "es_source": "patch"},
            {"raw": "M$Q", "he_form": "מֶשֶׁק", "he_morph": "SUBS.M.SG.C", "strongs": "H4943",
             "es": "mayordomo", "es_source": "patch"},
            {"raw": "BYT/Y", "he_form": "בֵית", "he_morph": "SUBS.M.SG.C", "strongs": "H1004",
             "es": "casa", "es_source": "patch",
             "prs_suffix": {"he_form": "ִי", "he_morph": "PRS.P1.COMMON.SG", "es": "mía"}},
            {"raw": "HW)", "he_form": "הוּא", "he_morph": "PRON.PERS.P3.M.SG", "strongs": "H1931",
             "es": "él", "es_source": "patch"},
            {"raw": "DM&Q", "he_form": "דַּמֶּשֶׂק", "he_morph": "NPROP", "strongs": "H1834",
             "es": "Damascus", "es_source": "patch"},
            {"raw": ")LY(ZR", "he_form": "אֱלִיעֶזֶר", "he_morph": "NPROP", "strongs": "H461",
             "es": "Eliezer", "es_source": "patch"},
        ]
        _gen15_rebuild_pairs(pairs, flat2)

    elif vrs == 3 and need_flat:
        flat3: list[dict] = [
            {"raw": "W/Y)MR", "prefix_forms": ["וַ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "יֹּאמֶר", "he_morph": "VERBO.QAL.WAYYIQT.P3.M.SG", "strongs": "H559",
             "es": "dijo", "es_source": "patch"},
            {"raw": ")BRM", "he_form": "אַבְרָם", "he_morph": "NPROP", "strongs": "H87",
             "es": "Abram", "es_source": "patch"},
            {"raw": "HN", "he_form": "הֵן", "he_morph": "PART.DEM", "strongs": "H2005",
             "es": "he aquí", "es_source": "patch"},
            {"raw": "L)", "he_form": "לֹא", "he_morph": "NEG", "strongs": "H3808",
             "es": "no", "es_source": "patch"},
            {"raw": "NTTH", "he_form": "נָתַתָּה", "he_morph": "VERBO.QAL.PERF.P2.M.SG", "strongs": "H5414",
             "es": "has dado", "es_source": "patch"},
            {"raw": "ZR(", "he_form": "זָרַע", "he_morph": "SUBS.M.SG.A", "strongs": "H2233",
             "es": "simiente", "es_source": "patch"},
            {"raw": "W/HNH", "prefix_forms": ["וְ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "הִנֵּה", "he_morph": "PART.DEM", "strongs": "H2009",
             "es": "he aquí", "es_source": "patch"},
            {"raw": "BN", "he_form": "בֶן־", "he_morph": "SUBS.M.SG.C", "strongs": "H1121",
             "es": "hijo", "es_source": "patch"},
            {"raw": "BYT/Y", "he_form": "בֵית", "he_morph": "SUBS.M.SG.C", "strongs": "H1004",
             "es": "casa", "es_source": "patch",
             "prs_suffix": {"he_form": "ִי", "he_morph": "PRS.P1.COMMON.SG", "es": "mía"}},
            {"raw": "YWR$", "he_form": "יוֹרֵשׁ", "he_morph": "VERBO.QAL.PTCA.M.SG.A", "strongs": "H3423",
             "es": "heredero", "es_source": "patch"},
            {"raw": ")T/Y", "he_form": "אֹת", "he_morph": "PART.OBJ.DIR", "strongs": "H853", "es": "",
             "prs_suffix": {"he_form": "ִי", "he_morph": "PRS.P1.COMMON.SG", "es": "me"}},
        ]
        _gen15_rebuild_pairs(pairs, flat3)

    elif vrs == 4 and need_flat:
        gk_gr = next(
            (
                (p.get("gr_unicode") or "").strip()
                for p in pairs
                if any((h.get("raw") or "") == "GKADD" for h in (p.get("he_words") or []))
            ),
            "",
        )
        flat4: list[dict] = [
            {"raw": "W/HNH", "prefix_forms": ["וְ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "הִנֵּה", "he_morph": "PART.DEM", "strongs": "H2009",
             "es": "he aquí", "es_source": "patch"},
            {"raw": "DBR", "he_form": "דְבַר־", "he_morph": "SUBS.M.SG.C", "strongs": "H1697",
             "es": "palabra", "es_source": "patch"},
            {"raw": "YHWH", "he_form": "יְהוָה", "he_morph": "NPROP", "strongs": "H3068",
             "es": "YHWH", "es_source": "patch"},
            {"raw": ")L/YW", "he_form": "אֵלַי", "he_morph": "PREP", "strongs": "H413",
             "es": "a mí", "es_source": "patch",
             "prs_suffix": {"he_form": "וֹ", "he_morph": "PRS.P3.M.SG", "es": ""}},
            {"raw": "L/)MR", "prefix_forms": ["לֵ"], "prefix_morphs": ["PREP"], "prefix_es": [""],
             "he_form": "אמֹר", "he_morph": "VERBO.QAL.INFC", "strongs": "H559",
             "es": "diciendo", "es_source": "patch"},
            {"raw": "L)", "he_form": "לֹא", "he_morph": "NEG", "strongs": "H3808",
             "es": "no", "es_source": "patch"},
            {"raw": "YYR$/K", "he_form": "יִֽירָשׁ", "he_morph": "VERBO.QAL.IMPF.P3.M.SG",
             "strongs": "H3423", "es": "heredará", "es_source": "patch",
             "prs_suffix": {"he_form": "ךָ", "he_morph": "PRS.P2.M.SG", "es": "te"}},
            {"raw": "ZH", "he_form": "זֶה", "he_morph": "PRON.DEM.M.SG", "strongs": "H2088",
             "es": "este", "es_source": "patch"},
            {"raw": "KY", "he_form": "כִּי־", "he_morph": "CONJ", "strongs": "H3588",
             "es": "sino", "es_source": "patch"},
            {"raw": ")M", "he_form": "אִם", "he_morph": "CONJ", "strongs": "H518",
             "es": "si", "es_source": "patch"},
            {"raw": ")$R", "he_form": "אֲשֶׁר", "he_morph": "REL", "strongs": "H834",
             "es": "que", "es_source": "patch"},
            {"raw": "YC)", "he_form": "יֵצֵא", "he_morph": "VERBO.QAL.IMPF.P3.M.SG", "strongs": "H3318",
             "es": "saldrá", "es_source": "patch"},
            {"raw": "M/M(/YK", "prefix_forms": ["מִ"], "prefix_morphs": ["PREP"], "prefix_es": ["de"],
             "he_form": "מֵּעֶי", "he_morph": "SUBS.M.PL.C", "strongs": "H4578",
             "es": "entrañas", "es_source": "patch",
             "prs_suffix": {"he_form": "ךָ", "he_morph": "PRS.P2.M.SG", "es": "tus"}},
            {"raw": "HW)", "he_form": "הוּא", "he_morph": "PRON.PERS.P3.M.SG", "strongs": "H1931",
             "es": "él", "es_source": "patch"},
            {"raw": "YYR$/K", "he_form": "יִֽירָשׁ", "he_morph": "VERBO.QAL.IMPF.P3.M.SG",
             "strongs": "H3423", "es": "heredará", "es_source": "patch",
             "prs_suffix": {"he_form": "ךָ", "he_morph": "PRS.P2.M.SG", "es": "te"}},
        ]
        _gen15_rebuild_pairs(pairs, flat4, gk_after={2: gk_gr} if gk_gr else None)

    elif vrs == 5 and need_flat:
        gk_gr = next(
            (
                (p.get("gr_unicode") or "").strip()
                for p in pairs
                if any((h.get("raw") or "") == "GKADD" for h in (p.get("he_words") or []))
            ),
            "",
        )
        flat5: list[dict] = [
            {"raw": "W/YWC)", "prefix_forms": ["וַ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "יּוֹצֵא", "he_morph": "VERBO.HIF.WAYYIQT.P3.M.SG", "strongs": "H3318",
             "es": "sacó", "es_source": "patch"},
            {"raw": ")T/W", "he_form": "אֹת", "he_morph": "PART.OBJ.DIR", "strongs": "H853", "es": "",
             "prs_suffix": {"he_form": "וֹ", "he_morph": "PRS.P3.M.SG", "es": "lo"}},
            {"raw": "H/XWC/H", "prefix_forms": ["הַ"], "prefix_morphs": ["ART"], "prefix_es": ["el"],
             "he_form": "ח֗וּצָ", "he_morph": "SUBS.M.SG.A", "strongs": "H2351",
             "es": "afuera", "es_source": "patch",
             "prs_suffix": {"he_form": "ה", "he_morph": "SUF.DIR.HE", "es": ""}},
            {"raw": "W/Y)MR", "prefix_forms": ["וַ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "יֹּאמֶר", "he_morph": "VERBO.QAL.WAYYIQT.P3.M.SG", "strongs": "H559",
             "es": "dijo", "es_source": "patch"},
            {"raw": "HB+", "he_form": "הַבֶּט", "he_morph": "VERBO.HIF.IMPV.P2.M.SG", "strongs": "H5027",
             "es": "mira", "es_source": "patch"},
            {"raw": "N)", "he_form": "נָא", "he_morph": "PART.EXH", "strongs": "H4994",
             "es": "ahora", "es_source": "patch"},
            {"raw": "H/$MYM/H", "prefix_forms": ["הַ"], "prefix_morphs": ["ART"], "prefix_es": ["los"],
             "he_form": "שָּׁמַיְמָ", "he_morph": "SUBS.M.PL.A", "strongs": "H8064",
             "es": "cielos", "es_source": "patch",
             "prs_suffix": {"he_form": "ה", "he_morph": "SUF.DIR.HE", "es": ""}},
            {"raw": "W/SPR", "prefix_forms": ["וּ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "סְפֹר", "he_morph": "VERBO.QAL.IMPV.P2.M.SG", "strongs": "H5608",
             "es": "cuenta", "es_source": "patch"},
            {"raw": "H/KWKBYM", "prefix_forms": ["הַ"], "prefix_morphs": ["ART"], "prefix_es": ["las"],
             "he_form": "כּוֹכָבִים", "he_morph": "SUBS.M.PL.A", "strongs": "H3556",
             "es": "estrellas", "es_source": "patch"},
            {"raw": ")M", "he_form": "אִם־", "he_morph": "CONJ", "strongs": "H518",
             "es": "si", "es_source": "patch"},
            {"raw": "TWKL", "he_form": "תּוּכַל", "he_morph": "VERBO.QAL.IMPF.P2.M.SG", "strongs": "H3201",
             "es": "puedes", "es_source": "patch"},
            {"raw": "L/SPR", "prefix_forms": ["לִ"], "prefix_morphs": ["PREP"], "prefix_es": ["para"],
             "he_form": "סְפֹּר", "he_morph": "VERBO.QAL.INFC", "strongs": "H5608",
             "es": "contar", "es_source": "patch"},
            {"raw": ")T/M", "he_form": "אֹת", "he_morph": "PART.OBJ.DIR", "strongs": "H853", "es": "",
             "prs_suffix": {"he_form": "ם", "he_morph": "PRS.P3.M.PL", "es": "los"}},
            {"raw": "W/Y)MR", "prefix_forms": ["וַ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "יֹּאמֶר", "he_morph": "VERBO.QAL.WAYYIQT.P3.M.SG", "strongs": "H559",
             "es": "dijo", "es_source": "patch"},
            {"raw": "KH", "he_form": "כֹּה", "he_morph": "ADV", "strongs": "H3541",
             "es": "así", "es_source": "patch"},
            {"raw": "YHYH", "he_form": "יִהְיֶה", "he_morph": "VERBO.QAL.IMPF.P3.M.SG", "strongs": "H1961",
             "es": "será", "es_source": "patch"},
            {"raw": "ZR(/K", "he_form": "זַרְע", "he_morph": "SUBS.M.SG.C", "strongs": "H2233",
             "es": "simiente", "es_source": "patch",
             "prs_suffix": {"he_form": "ֶךָ", "he_morph": "PRS.P2.M.SG", "es": "tu"}},
        ]
        _gen15_rebuild_pairs(pairs, flat5, gk_after={3: gk_gr} if gk_gr else None)

    elif vrs == 11 and need_flat:
        flat11: list[dict] = [
            {"raw": "W/YRD", "prefix_forms": ["וַ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "יֵּרֶד", "he_morph": "VERBO.QAL.WAYYIQT.P3.M.SG", "strongs": "H3381",
             "es": "descendió", "es_source": "patch"},
            {"raw": "H/(Y+", "prefix_forms": ["הָ"], "prefix_morphs": ["ART"], "prefix_es": ["las"],
             "he_form": "עַיִט", "he_morph": "SUBS.M.SG.A", "strongs": "H5861",
             "es": "aves", "es_source": "patch"},
            {"raw": "(L", "he_form": "עַל־", "he_morph": "PREP", "strongs": "H5921",
             "es": "sobre", "es_source": "patch"},
            {"raw": "H/PGRYM", "prefix_forms": ["הַ"], "prefix_morphs": ["ART"], "prefix_es": ["los"],
             "he_form": "פְּגָרִים", "he_morph": "SUBS.M.PL.A", "strongs": "H6297",
             "es": "cadáveres", "es_source": "patch"},
            {"raw": "W/Y$WB", "prefix_forms": ["וַ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "יַּשֵּׁב", "he_morph": "VERBO.HIF.WAYYIQT.P3.M.SG", "strongs": "H7725",
             "es": "ahuyentó", "es_source": "patch"},
            {"raw": ")T/M", "he_form": "אֹת", "he_morph": "PART.OBJ.DIR", "strongs": "H853", "es": "",
             "prs_suffix": {"he_form": "ם", "he_morph": "PRS.P3.M.PL", "es": "los"}},
            {"raw": ")BRM", "he_form": "אַבְרָם", "he_morph": "NPROP", "strongs": "H87",
             "es": "Abram", "es_source": "patch"},
        ]
        _gen15_rebuild_pairs(pairs, flat11)

    elif vrs == 7 and need_flat:
        flat7: list[dict] = [
            {"raw": "W/Y)MR", "prefix_forms": ["וַ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "יֹּאמֶר", "he_morph": "VERBO.QAL.WAYYIQT.P3.M.SG", "strongs": "H559",
             "es": "dijo", "es_source": "patch"},
            {"raw": ")L/YW", "he_form": "אֵלָי", "he_morph": "PREP", "strongs": "H413",
             "es": "a mí", "es_source": "patch",
             "prs_suffix": {"he_form": "וֹ", "he_morph": "PRS.P3.M.SG", "es": ""}},
            {"raw": ")NY", "he_form": "אֲנִי", "he_morph": "PRON.PERS.P1.COMMON.SG", "strongs": "H589",
             "es": "yo", "es_source": "patch"},
            {"raw": "YHWH", "he_form": "יְהוָה", "he_morph": "NPROP", "strongs": "H3068",
             "es": "YHWH", "es_source": "patch"},
            {"raw": ")$R", "he_form": "אֲשֶׁר", "he_morph": "REL", "strongs": "H834",
             "es": "que", "es_source": "patch"},
            {"raw": "HWC)TY/K", "he_form": "הוֹצֵאתִי", "he_morph": "VERBO.HIF.PERF.P1.COMMON.SG",
             "strongs": "H3318", "es": "saqué", "es_source": "patch",
             "prs_suffix": {"he_form": "ךָ", "he_morph": "PRS.P2.M.SG", "es": "te"}},
            {"raw": "M/)WR", "prefix_forms": ["מֵ"], "prefix_morphs": ["PREP"], "prefix_es": ["de"],
             "he_form": "א֣וּר", "he_morph": "NPROP", "strongs": "H217", "es": "Ur", "es_source": "patch"},
            {"raw": "K&DYM", "he_form": "כַּשְׂדִּים", "he_morph": "NPROP", "strongs": "H3778",
             "es": "de los casitas", "es_source": "patch"},
            {"raw": "L/TT", "prefix_forms": ["לָ"], "prefix_morphs": ["PREP"], "prefix_es": ["para"],
             "he_form": "תֶת", "he_morph": "VERBO.QAL.INFC", "strongs": "H5414",
             "es": "dar", "es_source": "patch"},
            {"raw": ")T", "he_form": "אֶת־", "he_morph": "PART.OBJ.DIR", "strongs": "H853", "es": ""},
            {"raw": "H/)RC", "prefix_forms": ["הָ"], "prefix_morphs": ["ART"], "prefix_es": ["la"],
             "he_form": "אָרֶץ", "he_morph": "SUBS.BOTH.SG.A", "strongs": "H776",
             "es": "tierra", "es_source": "patch"},
            {"raw": "H/Z)T", "prefix_forms": ["הַ"], "prefix_morphs": ["ART"], "prefix_es": ["esta"],
             "he_form": "זֹּאת", "he_morph": "PRON.DEM.F.SG", "strongs": "H2063",
             "es": "esta", "es_source": "patch"},
            {"raw": "L/R$T/H", "prefix_forms": ["לְ"], "prefix_morphs": ["PREP"], "prefix_es": ["para"],
             "he_form": "רִשְׁתּ", "he_morph": "VERBO.QAL.INFC", "strongs": "H3423",
             "es": "heredar", "es_source": "patch",
             "prs_suffix": {"he_form": "ָהּ", "he_morph": "PRS.P3.F.SG", "es": "la"}},
        ]
        _gen15_rebuild_pairs(pairs, flat7)

    elif vrs == 8 and need_flat:
        flat8: list[dict] = [
            {"raw": "W/Y)MR", "prefix_forms": ["וַ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "יֹּאמַר", "he_morph": "VERBO.QAL.WAYYIQT.P3.M.SG", "strongs": "H559",
             "es": "dijo", "es_source": "patch"},
            {"raw": ")DNY", "he_form": "אֲדֹנ", "he_morph": "SUBS.M.PL.C", "strongs": "H113",
             "es": "Adonai", "es_source": "patch",
             "prs_suffix": {"he_form": "י", "he_morph": "PRS.P1.COMMON.SG", "es": ""}},
            {"raw": "YHWH", "he_form": "יֱהוִה", "he_morph": "NPROP", "strongs": "H3068",
             "es": "YHWH", "es_source": "patch"},
            {"raw": "B/MH", "prefix_forms": ["בַּ"], "prefix_morphs": ["PREP"], "prefix_es": ["en"],
             "he_form": "מָּה", "he_morph": "PART.INTERR", "strongs": "H4100",
             "es": "qué", "es_source": "patch"},
            {"raw": ")D(", "he_form": "אֵדַע", "he_morph": "VERBO.QAL.IMPF.P1.COMMON.SG", "strongs": "H3045",
             "es": "sabré", "es_source": "patch"},
            {"raw": "KY", "he_form": "כִּי", "he_morph": "CONJ", "strongs": "H3588",
             "es": "que", "es_source": "patch"},
            {"raw": ")YRH/NH", "he_form": "אִֽירָשׁ", "he_morph": "VERBO.QAL.IMPF.P1.COMMON.SG",
             "strongs": "H3423", "es": "heredaré", "es_source": "patch",
             "prs_suffix": {"he_form": "נָּה", "he_morph": "PRS.P3.F.SG", "es": "la"}},
        ]
        _gen15_rebuild_pairs(pairs, flat8)

    elif vrs == 9 and need_flat:
        flat9: list[dict] = [
            {"raw": "W/Y)MR", "prefix_forms": ["וַ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "יֹּאמֶר", "he_morph": "VERBO.QAL.WAYYIQT.P3.M.SG", "strongs": "H559",
             "es": "dijo", "es_source": "patch"},
            {"raw": ")L/YW", "he_form": "אֵלָיו", "he_morph": "PREP", "strongs": "H413",
             "es": "a él", "es_source": "patch",
             "prs_suffix": {"he_form": "וֹ", "he_morph": "PRS.P3.M.SG", "es": ""}},
            {"raw": "QXH", "he_form": "קְחָ", "he_morph": "VERBO.QAL.IMPV.P2.M.SG", "strongs": "H3947",
             "es": "toma", "es_source": "patch",
             "prs_suffix": {"he_form": "ה", "he_morph": "SUF.PARAG.HE", "es": ""}},
            {"raw": "(GLH", "he_form": "עֶגְלָה", "he_morph": "SUBS.F.SG.A", "strongs": "H5695",
             "es": "becerra", "es_source": "patch"},
            {"raw": "M/$L$T", "he_form": "מְשֻׁלֶּשֶׁת", "he_morph": "ADJ.F.SG.A", "strongs": "H8027",
             "es": "de tres años", "es_source": "patch"},
            {"raw": "W/(Z", "prefix_forms": ["וְ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "עֵז", "he_morph": "SUBS.BOTH.SG.A", "strongs": "H5795",
             "es": "cabra", "es_source": "patch"},
            {"raw": "M/$L$T", "he_form": "מְשֻׁלֶּשֶׁת", "he_morph": "ADJ.F.SG.A", "strongs": "H8027",
             "es": "de tres años", "es_source": "patch"},
            {"raw": "W/)YL", "prefix_forms": ["וְ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "אַיִל", "he_morph": "SUBS.M.SG.A", "strongs": "H352",
             "es": "carnero", "es_source": "patch"},
            {"raw": "M/L/$", "he_form": "מְשֻׁלָּשׁ", "he_morph": "ADJ.M.SG.A", "strongs": "H8027",
             "es": "de tres años", "es_source": "patch"},
            {"raw": "W/TR", "prefix_forms": ["וְ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "תֹּר", "he_morph": "SUBS.COMMON.SG.A", "strongs": "H8449",
             "es": "tórtola", "es_source": "patch"},
            {"raw": "W/GWZL", "prefix_forms": ["וְ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "גּוֹזָל", "he_morph": "SUBS.M.SG.A", "strongs": "H1469",
             "es": "pichón", "es_source": "patch"},
        ]
        _gen15_rebuild_pairs(pairs, flat9)

    elif vrs == 10 and need_flat:
        flat10: list[dict] = [
            {"raw": "W/YQX", "prefix_forms": ["וַ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "יִּקַּח", "he_morph": "VERBO.QAL.WAYYIQT.P3.M.SG", "strongs": "H3947",
             "es": "tomó", "es_source": "patch"},
            {"raw": ")T", "he_form": "אֶת־", "he_morph": "PART.OBJ.DIR", "strongs": "H853", "es": ""},
            {"raw": "KL", "he_form": "כָּל־", "he_morph": "SUBS.M.SG.C", "strongs": "H3605",
             "es": "todo", "es_source": "patch"},
            {"raw": ")LH", "he_form": "אֵלֶּה", "he_morph": "PRON.DEM.COMMON.PL", "strongs": "H428",
             "es": "estos", "es_source": "patch"},
            {"raw": "W/YBTR", "prefix_forms": ["וַ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "יְבַתֵּר", "he_morph": "VERBO.PIEL.WAYYIQT.P3.M.SG", "strongs": "H1334",
             "es": "partió", "es_source": "patch"},
            {"raw": ")T/M", "he_form": "אֹת", "he_morph": "PART.OBJ.DIR", "strongs": "H853", "es": "",
             "prs_suffix": {"he_form": "ם", "he_morph": "PRS.P3.M.PL", "es": "los"}},
            {"raw": "B/TWK", "prefix_forms": ["בַּ"], "prefix_morphs": ["PREP"], "prefix_es": ["en"],
             "he_form": "תָּוֶךְ", "he_morph": "SUBS.M.SG.A", "strongs": "H8432",
             "es": "medio", "es_source": "patch"},
            {"raw": "W/YTN", "prefix_forms": ["וַ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "יִּתֵּן", "he_morph": "VERBO.QAL.WAYYIQT.P3.M.SG", "strongs": "H5414",
             "es": "puso", "es_source": "patch"},
            {"raw": ")Y$", "he_form": "אִישׁ־", "he_morph": "SUBS.M.SG.A", "strongs": "H376",
             "es": "cada uno", "es_source": "patch"},
            {"raw": "BTR/W", "he_form": "בִּתְר", "he_morph": "SUBS.M.SG.C", "strongs": "H1336",
             "es": "parte", "es_source": "patch",
             "prs_suffix": {"he_form": "וֹ", "he_morph": "PRS.P3.M.SG", "es": "su"}},
            {"raw": "L/QR)T", "prefix_forms": ["לִ"], "prefix_morphs": ["PREP"], "prefix_es": ["hacia"],
             "he_form": "קְרַאת", "he_morph": "VERBO.QAL.INFC", "strongs": "H7125",
             "es": "enfrente", "es_source": "patch"},
            {"raw": "R(/HW", "he_form": "רֵעֵ", "he_morph": "SUBS.M.SG.C", "strongs": "H7453",
             "es": "compañero", "es_source": "patch",
             "prs_suffix": {"he_form": "הוּ", "he_morph": "PRS.P3.M.SG", "es": "su"}},
            {"raw": "W/)T", "prefix_forms": ["וְ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "אֶת־", "he_morph": "PART.OBJ.DIR", "strongs": "H853", "es": ""},
            {"raw": "H/CPR", "prefix_forms": ["הַ"], "prefix_morphs": ["ART"], "prefix_es": ["las"],
             "he_form": "צִפֹּר", "he_morph": "SUBS.BOTH.SG.A", "strongs": "H6833",
             "es": "aves", "es_source": "patch"},
            {"raw": "L)", "he_form": "לֹא", "he_morph": "NEG", "strongs": "H3808",
             "es": "no", "es_source": "patch"},
            {"raw": "BTR", "he_form": "בָתָר", "he_morph": "VERBO.QAL.PERF.P3.M.SG", "strongs": "H1334",
             "es": "partió", "es_source": "patch"},
        ]
        _gen15_rebuild_pairs(pairs, flat10)

    elif vrs == 12 and need_flat:
        flat12: list[dict] = [
            {"raw": "W/YHY", "prefix_forms": ["וַ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "יְהִי", "he_morph": "VERBO.QAL.WAYYIQT.P3.M.SG", "strongs": "H1961",
             "es": "fue", "es_source": "patch"},
            {"raw": "H/$M$", "prefix_forms": ["הַ"], "prefix_morphs": ["ART"], "prefix_es": ["el"],
             "he_form": "שֶּׁמֶשׁ", "he_morph": "SUBS.BOTH.SG.A", "strongs": "H8121",
             "es": "sol", "es_source": "patch"},
            {"raw": "L/BW)", "prefix_forms": ["לָ"], "prefix_morphs": ["PREP"], "prefix_es": ["al"],
             "he_form": "בוֹא", "he_morph": "VERBO.QAL.INFC", "strongs": "H935",
             "es": "ponerse", "es_source": "patch"},
            {"raw": "W/TRDMH", "prefix_forms": ["וְ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "תַרְדֵּמָה", "he_morph": "SUBS.F.SG.A", "strongs": "H8639",
             "es": "sueño profundo", "es_source": "patch"},
            {"raw": "NPLH", "he_form": "נָפְלָה", "he_morph": "VERBO.QAL.PERF.P3.F.SG", "strongs": "H5307",
             "es": "cayó", "es_source": "patch"},
            {"raw": "(L", "he_form": "עַל־", "he_morph": "PREP", "strongs": "H5921", "es": "sobre", "es_source": "patch"},
            {"raw": ")BRM", "he_form": "אַבְרָם", "he_morph": "NPROP", "strongs": "H87",
             "es": "Abram", "es_source": "patch"},
            {"raw": "W/HNH", "prefix_forms": ["וְ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "הִנֵּה", "he_morph": "PART.DEM", "strongs": "H2009",
             "es": "he aquí", "es_source": "patch"},
            {"raw": ")YMH", "he_form": "אֵימָה", "he_morph": "SUBS.F.SG.A", "strongs": "H367",
             "es": "terror", "es_source": "patch"},
            {"raw": "X$KH", "he_form": "חֲשֵׁכָה", "he_morph": "SUBS.F.SG.A", "strongs": "H2825",
             "es": "oscuridad", "es_source": "patch"},
            {"raw": "GDLH", "he_form": "גְדֹלָה", "he_morph": "ADJ.F.SG.A", "strongs": "H1419",
             "es": "grande", "es_source": "patch"},
            {"raw": "NPLT", "he_form": "נֹפֶלֶת", "he_morph": "VERBO.QAL.PTCA.F.SG.A", "strongs": "H5307",
             "es": "cayendo", "es_source": "patch"},
            {"raw": "(L/YW", "he_form": "עָלָי", "he_morph": "PREP", "strongs": "H5921",
             "es": "sobre mí", "es_source": "patch",
             "prs_suffix": {"he_form": "וֹ", "he_morph": "PRS.P3.M.SG", "es": ""}},
        ]
        _gen15_rebuild_pairs(pairs, flat12)

    elif vrs == 13 and need_flat:
        flat13: list[dict] = [
            {"raw": "W/Y)MR", "prefix_forms": ["וַ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "יֹּאמֶר", "he_morph": "VERBO.QAL.WAYYIQT.P3.M.SG", "strongs": "H559",
             "es": "dijo", "es_source": "patch"},
            {"raw": "L/)BRM", "prefix_forms": ["לְ"], "prefix_morphs": ["PREP"], "prefix_es": ["a"],
             "he_form": "אַבְרָם", "he_morph": "NPROP", "strongs": "H87",
             "es": "Abram", "es_source": "patch"},
            {"raw": "YD(", "he_form": "יָדֹעַ", "he_morph": "VERBO.QAL.INFA", "strongs": "H3045",
             "es": "saber", "es_source": "patch"},
            {"raw": "TD(", "he_form": "תֵּדַע", "he_morph": "VERBO.QAL.IMPF.P2.M.SG", "strongs": "H3045",
             "es": "sabrás", "es_source": "patch"},
            {"raw": "KY", "he_form": "כִּי־", "he_morph": "CONJ", "strongs": "H3588",
             "es": "que", "es_source": "patch"},
            {"raw": "GR", "he_form": "גֵר", "he_morph": "SUBS.M.SG.A", "strongs": "H1616",
             "es": "extranjero", "es_source": "patch"},
            {"raw": "YHYH", "he_form": "יִהְיֶה", "he_morph": "VERBO.QAL.IMPF.P3.M.SG", "strongs": "H1961",
             "es": "será", "es_source": "patch"},
            {"raw": "ZR(/K", "he_form": "זַרְעֲ", "he_morph": "SUBS.M.SG.C", "strongs": "H2233",
             "es": "simiente", "es_source": "patch",
             "prs_suffix": {"he_form": "ךָ", "he_morph": "PRS.P2.M.SG", "es": "tu"}},
            {"raw": "B/)RC", "prefix_forms": ["בְּ"], "prefix_morphs": ["PREP"], "prefix_es": ["en"],
             "he_form": "אֶרֶץ", "he_morph": "SUBS.BOTH.SG.A", "strongs": "H776",
             "es": "tierra", "es_source": "patch"},
            {"raw": "L)", "he_form": "לֹא", "he_morph": "NEG", "strongs": "H3808",
             "es": "no", "es_source": "patch"},
            {"raw": "W/(BDW/M", "prefix_forms": ["וַ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "עֲבָדוּ", "he_morph": "VERBO.QAL.PERF.P3.COMMON.PL", "strongs": "H5647",
             "es": "servirán", "es_source": "patch",
             "prs_suffix": {"he_form": "ם", "he_morph": "PRS.P3.M.PL", "es": "los"}},
            {"raw": "W/(NW", "prefix_forms": ["וְ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "עִנּוּ", "he_morph": "VERBO.PIEL.PERF.P3.COMMON.PL", "strongs": "H6031",
             "es": "afligirán", "es_source": "patch"},
            {"raw": ")T/M", "he_form": "אֹת", "he_morph": "PART.OBJ.DIR", "strongs": "H853", "es": "",
             "prs_suffix": {"he_form": "ם", "he_morph": "PRS.P3.M.PL", "es": "los"}},
            {"raw": ")RB(", "he_form": "אַרְבַּע", "he_morph": "NUM.CARD.F.SG.A", "strongs": "H702",
             "es": "cuatro", "es_source": "patch"},
            {"raw": "M)WT", "he_form": "מֵאוֹת", "he_morph": "NUM.CARD.BOTH.PL.A", "strongs": "H3967",
             "es": "cientos", "es_source": "patch"},
            {"raw": "$NH", "he_form": "שָׁנָה", "he_morph": "SUBS.F.SG.A", "strongs": "H8141",
             "es": "años", "es_source": "patch"},
        ]
        _gen15_rebuild_pairs(pairs, flat13)

    elif vrs == 17 and need_flat:
        flat17: list[dict] = [
            {"raw": "W/YHY", "prefix_forms": ["וַ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "יְהִי", "he_morph": "VERBO.QAL.WAYYIQT.P3.M.SG", "strongs": "H1961",
             "es": "fue", "es_source": "patch"},
            {"raw": "H/$M$", "prefix_forms": ["הַ"], "prefix_morphs": ["ART"], "prefix_es": ["el"],
             "he_form": "שֶּׁמֶשׁ", "he_morph": "SUBS.BOTH.SG.A", "strongs": "H8121",
             "es": "sol", "es_source": "patch"},
            {"raw": "B)H", "he_form": "בָּאָה", "he_morph": "VERBO.QAL.PERF.P3.F.SG", "strongs": "H935",
             "es": "se puso", "es_source": "patch"},
            {"raw": "W/(L+H", "prefix_forms": ["וַ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "עֲלָטָה", "he_morph": "SUBS.F.SG.A", "strongs": "H5939",
             "es": "oscuridad", "es_source": "patch"},
            {"raw": "HYH", "he_form": "הָיָה", "he_morph": "VERBO.QAL.PERF.P3.M.SG", "strongs": "H1961",
             "es": "hubo", "es_source": "patch"},
            {"raw": "W/HNH", "prefix_forms": ["וְ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "הִנֵּה", "he_morph": "PART.DEM", "strongs": "H2009",
             "es": "he aquí", "es_source": "patch"},
            {"raw": "TNWR", "he_form": "תַנּוּר", "he_morph": "SUBS.M.SG.C", "strongs": "H8574",
             "es": "horno", "es_source": "patch"},
            {"raw": "($N", "he_form": "עָשָׁן", "he_morph": "SUBS.M.SG.A", "strongs": "H6227",
             "es": "humo", "es_source": "patch"},
            {"raw": "W/LPYD", "prefix_forms": ["וְ"], "prefix_morphs": ["CONJ"], "prefix_es": ["y"],
             "he_form": "לַפִּיד", "he_morph": "SUBS.M.SG.C", "strongs": "H3940",
             "es": "antorcha", "es_source": "patch"},
            {"raw": ")$", "he_form": "אֵשׁ", "he_morph": "SUBS.BOTH.SG.A", "strongs": "H784",
             "es": "fuego", "es_source": "patch"},
            {"raw": ")$R", "he_form": "אֲשֶׁר", "he_morph": "REL", "strongs": "H834",
             "es": "que", "es_source": "patch"},
            {"raw": "(BR", "he_form": "עָבַר", "he_morph": "VERBO.QAL.PERF.P3.M.SG", "strongs": "H5674",
             "es": "pasó", "es_source": "patch"},
            {"raw": "BYN", "he_form": "בֵּין", "he_morph": "PREP", "strongs": "H996",
             "es": "entre", "es_source": "patch"},
            {"raw": "H/GZRYM", "prefix_forms": ["הַ"], "prefix_morphs": ["ART"], "prefix_es": ["los"],
             "he_form": "גְּזָרִים", "he_morph": "SUBS.M.PL.A", "strongs": "H1506",
             "es": "pedazos", "es_source": "patch"},
            {"raw": "H/)LH", "prefix_forms": ["הָ"], "prefix_morphs": ["ART"], "prefix_es": ["estos"],
             "he_form": "אֵלֶּה", "he_morph": "PRON.DEM.COMMON.PL", "strongs": "H428",
             "es": "estos", "es_source": "patch"},
        ]
        _gen15_rebuild_pairs(pairs, flat17)

    if vrs in _GEN15_PAIR_ORDER and _gen15_oshb_diff(verse):
        _gen15_reorder_pairs(pairs, vrs)

    _gen15_finalize_b4_hebrew(verse, respect_user_gloss=respect_user_gloss)


def _fix_gen15_lxx_align(verse: dict) -> None:
    """B8 — reparto LXX por morfema tras splits OSHB cap. 15."""
    vrs = verse.get("verse", 0)
    pairs = verse.get("pairs", [])
    lxx_surface = _gen15_lxx_load_surface(vrs)

    _gen15_lxx_batch(verse, lxx_surface)
    _gen15_merge_orphan_gk_add(pairs)
    _gen15_apply_lxx_gr_map(pairs, vrs)
    _gen15_merge_orphan_gk_add(pairs)

    _fix_lxx_align_verse(verse)

    # Tras mapa explícito, solo dedupe/trim (sin inject que reintroduce gk_add)
    from fix_lxx_chapters import dedupe_identical_gk_add, trim_gk_add_extra_tokens

    trim_gk_add_extra_tokens(verse, lxx_surface)
    dedupe_identical_gk_add(verse, lxx_surface)
    _fix_lxx_align_verse(verse)

    for p in pairs:
        _repair_pair_lxx_coverage(p)
        if p.get("kind") == "gk_add":
            _gen15_ensure_gk_add_stub(p)

    _gen15_post_lxx_pair_fixes(pairs, vrs)
    for p in pairs:
        if p.get("kind") == "gk_add":
            _gen15_ensure_gk_add_stub(p)
    _gen15_strip_dot_prefixes(verse)
    _gen15_trim_prefix_lengths(verse)
    for p in pairs:
        _repair_pair_lxx_coverage(p)


def _gen15_post_lxx_pair_fixes(pairs: list, vrs: int) -> None:
    """Correcciones puntuales morfema LXX que _sync_pair_gr_lxx no reparte bien."""
    if vrs == 1:
        # Fix 2nd )L → μή (batch overwrites it to φοβοῦ)
        # Fix 2nd )BRM → Αβραμ (batch overwrites it to ὑπερασπίζω σου)
        al_count = 0
        abram_count = 0
        for p in pairs:
            raw = _gen15_pair_raw(p)
            if raw == ")L":
                al_count += 1
                if al_count == 2:
                    p["gr_unicode"] = "μή"
            elif raw == ")BRM":
                abram_count += 1
                if abram_count == 2:
                    p["gr_unicode"] = "Αβραμ"

    elif vrs == 4:
        # Remove extra σε from HW) pair (should be plain οὗτος)
        for p in pairs:
            if _gen15_pair_raw(p) == "HW)" and "σε" in (p.get("gr_unicode") or ""):
                p["gr_unicode"] = "οὗτος"
                for hw in p.get("he_words") or []:
                    if "σε" in (hw.get("gr_word") or ""):
                        hw["gr_word"] = "οὗτος"

    elif vrs == 9:
        # Add μοι after λαβέ; add καὶ before each animal name (W/ prefix = καί)
        for p in pairs:
            raw = _gen15_pair_raw(p)
            if raw == "QXH":
                p["gr_unicode"] = "λαβέ μοι"
            elif raw == "W/(Z":
                p["gr_unicode"] = "καὶ αἶγα"
            elif raw == "W/)YL":
                p["gr_unicode"] = "καὶ κριὸν"
            elif raw == "W/TR":
                p["gr_unicode"] = "καὶ τρυγόνα"
            elif raw == "W/GWZL":
                p["gr_unicode"] = "καὶ περιστεράν"

    elif vrs == 11:
        for p in pairs:
            if _gen15_pair_raw(p) != "H/PGRYM":
                continue
            hw = (p.get("he_words") or [{}])[0]
            gr = "τὰ σώματα τὰ διχοτομήματα αὐτῶν"
            p["gr_unicode"] = gr
            hw["prefix_gr"] = ["τὰ"]
            hw["gr_word"] = "σώματα τὰ διχοτομήματα αὐτῶν"
            hw["gr_source"] = "patch_lxx"
            break
        for p in pairs:
            raw = _gen15_pair_raw(p)
            if raw in ("W/Y$WB", "W/Y$B"):
                p["gr_unicode"] = "καὶ συνεκάθισεν"
            elif raw == ")T/M":
                p["gr_unicode"] = "αὐτοῖς"
            elif raw == ")BRM":
                p["gr_unicode"] = "Αβραμ"

    elif vrs == 13:
        # Add αὐτούς to first enslavement verb; clear duplicated τετρακόσια/ἔτη
        for p in pairs:
            raw = _gen15_pair_raw(p)
            if raw == "W/(BDW/M":
                p["gr_unicode"] = "καὶ δουλώσουσιν αὐτούς"
            elif raw == ")T/M":
                p["gr_unicode"] = ""
            elif raw == "M)WT":
                p["gr_unicode"] = ""

    elif vrs == 16:
        # Add δὲ after τετάρτη; add Αμορραίων after τῶν
        for p in pairs:
            raw = _gen15_pair_raw(p)
            if raw == "W/DWR":
                p["gr_unicode"] = "τετάρτη δὲ"
            elif raw == "(D":
                p["gr_unicode"] = "τῶν Αμορραίων"

    elif vrs == 18:
        for p in pairs:
            raws = [(hw.get("raw") or "") for hw in p.get("he_words") or []]
            if ")BRM" in raws and ")T" in raws:
                p["gr_unicode"] = "τῷ Αβραμ"
                for hw in p.get("he_words") or []:
                    if hw.get("raw") == ")BRM":
                        hw["prefix_gr"] = ["τῷ"]
                        hw["gr_word"] = "Αβραμ"
                    elif hw.get("raw") == ")T":
                        hw.pop("gr_word", None)
                        hw.pop("prefix_gr", None)
            elif "H/)RC" in raws and ")T" in raws:
                p["gr_unicode"] = "τὴν γῆν"
                for hw in p.get("he_words") or []:
                    if hw.get("raw") == ")T":
                        hw["gr_word"] = "τὴν"
                    elif hw.get("raw") == "H/)RC":
                        hw["gr_word"] = "γῆν"
        # Fix river tokens: spec assigns wrong counts, batch doesn't recover them
        for p in pairs:
            raw = _gen15_pair_raw(p)
            if raw == "M/NHR":
                p["gr_unicode"] = "ἀπὸ τοῦ ποταμοῦ"
                # prefix_gr=['ἀπὸ'] + gr_word='τοῦ ποταμοῦ' → already correct after spec
            elif raw == "MCRYM":
                p["gr_unicode"] = "Αἰγύπτου"
                for hw in p.get("he_words") or []:
                    if "ποταμ" in (hw.get("gr_word") or ""):
                        hw["gr_word"] = "Αἰγύπτου"
            elif raw == "H/NHR":
                p["gr_unicode"] = "τοῦ ποταμοῦ"
                # prefix_gr=['τοῦ'] + gr_word='ποταμοῦ' → already correct
            elif raw == "H/GDL":
                p["gr_unicode"] = "τοῦ μεγάλου"
                # prefix_gr=['τοῦ'] + gr_word='μεγάλου' → already correct
            elif raw == "NHR" and (p.get("gr_unicode") or "").strip() in ("τοῦ", "ποταμοῦ", ""):
                p["gr_unicode"] = "ποταμοῦ"
                for hw in p.get("he_words") or []:
                    gw = (hw.get("gr_word") or "").strip()
                    if "τοῦ" in gw or "του" in gw.lower():
                        hw["gr_word"] = "ποταμοῦ"

    elif vrs == 21:
        # Each ethnic pair needs καὶ τοὺς + name
        for p in pairs:
            if p.get("kind") == "gk_add":
                continue
            raws = [hw.get("raw", "") for hw in (p.get("he_words") or [])]
            if "H/)MRY" in raws:
                p["gr_unicode"] = "καὶ τοὺς Αμορραίους"
            elif "H/KN(NY" in raws:
                p["gr_unicode"] = "καὶ τοὺς Χαναναίους"
            elif "H/GRG$Y" in raws:
                p["gr_unicode"] = "καὶ τοὺς Γεργεσαίους"
            elif "HYBWSY" in raws:
                p["gr_unicode"] = "καὶ τοὺς Ιεβουσαίους"


def _fix_gen15_es_glosses(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Correcciones de glosas / metadatos español cap. 15 (B5)."""
    vrs = verse.get("verse", 0)
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            morph = hw.get("he_morph") or ""
            key = _gen5_he_key(hw)
            raw = hw.get("raw") or ""

            if _is_nprop_morph(morph) and key == "אברם":
                if (hw.get("es") or "").strip().lower() != "abram":
                    _set_es_patch(hw, "Abram", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

            elif _is_nprop_morph(morph) and key in ("שרי", "שׂרי"):
                if (hw.get("es") or "").strip().lower() != "sarai":
                    _set_es_patch(hw, "Sarai", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

            elif _is_nprop_morph(morph) and key == "אליעזר":
                if (hw.get("es") or "").strip().lower() != "eliezer":
                    _set_es_patch(hw, "Eliezer", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

            elif vrs == 2 and key == "דמשק":
                if (hw.get("es") or "").strip().lower() in ("damascus", ""):
                    _set_es_patch(hw, "Damasco", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

            elif vrs == 6 and raw in ("W/YX$B/H", "W/YX$BM/H"):
                _set_es_patch(hw, "le contó", respect_user=respect_user_gloss)
                prs = hw.get("prs_suffix")
                if isinstance(prs, dict) and (prs.get("he_form") or "").strip():
                    prs["es"] = ""
                if not (respect_user_gloss and _has_user_gloss(hw)):
                    hw["es_source"] = "patch"

            elif vrs == 15:
                if raw == "TQBR":
                    _set_es_patch(hw, "serás enterrado", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

            elif vrs == 16:
                if raw == "(WN" and key.startswith("עו"):
                    hw["strongs"] = "H5771"
                    hw["he_morph"] = "SUBS.BOTH.SG.C"
                    if (hw.get("es") or "").strip().lower() in ("amorrheo", "amorreo", ""):
                        _set_es_patch(hw, "iniquidad", respect_user=respect_user_gloss)
                        if not (respect_user_gloss and _has_user_gloss(hw)):
                            hw["es_source"] = "patch"
                elif raw == "L)" and morph.startswith("NEG"):
                    _set_es_patch(hw, "no", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"
                elif raw == "KY" and (hw.get("es") or "").strip() == "y":
                    _set_es_patch(hw, "porque", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

            elif vrs == 18:
                if raw == "H/HW)" and morph.startswith("PRON"):
                    _set_es_patch(hw, "él", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"
                elif raw == ")T" and (
                    morph == "PART.OBJ.DIR"
                    or (hw.get("strongs") or "") in ("H853", "H854")
                ):
                    hw["strongs"] = "H853"
                    hw["he_morph"] = "PART.OBJ.DIR"
                    if (hw.get("es") or "").strip() in ("contigo", ""):
                        _set_es_patch(hw, "", respect_user=respect_user_gloss)
                        if not (respect_user_gloss and _has_user_gloss(hw)):
                            hw["es_source"] = "patch"
                elif raw == "L/)MR":
                    if (hw.get("es") or "").strip().lower() in ("tu semilla", "tu simiente"):
                        hw["es"] = "diciendo"
                        hw["es_source"] = "patch"
                    elif (hw.get("es") or "").strip() != "diciendo":
                        _set_es_patch(hw, "diciendo", respect_user=respect_user_gloss)
                        if not (respect_user_gloss and _has_user_gloss(hw)):
                            hw["es_source"] = "patch"
                elif raw == "H/GDL" and key.startswith("גד"):
                    hw["strongs"] = "H1419"
                    hw["he_morph"] = "AMSA"
                    _set_es_patch(hw, "grande", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"
                elif raw == "H/Z)T":
                    hw["strongs"] = "H2063"
                    hw["he_morph"] = "PRON.DEM.F.SG"
                    _set_es_patch(hw, "esta", respect_user=respect_user_gloss)
                    if not (respect_user_gloss and _has_user_gloss(hw)):
                        hw["es_source"] = "patch"

    _fix_gen5_numeric_glosses(verse, respect_user_gloss=respect_user_gloss)


def _patch_gen15(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Parches estructurales Génesis cap. 15 — alianza / promesa a Abram."""
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            _gen15_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)

    _fix_gen15_oshb_align(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen15_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if not (
                (hw.get("raw") or "").endswith("}")
                or (
                    hw.get("es_source") == "patch_meta"
                    and not _strip_niqqud(hw.get("he_form") or "")
                )
            )
        ]
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if (hw.get("he_form") or "").strip()
            or (hw.get("prefix_forms") or [])
            or (hw.get("prs_suffix") or {}).get("he_form")
            or hw.get("raw") in ("=L/MYN/W", "=L/MYN/HW", "=VAV")
        ]

    verse["pairs"] = [
        p for p in verse.get("pairs", [])
        if p.get("he_words")
        or (p.get("gr_unicode") or "").strip()
        or p.get("kind") in ("heb_omit", "gk_add")
    ]

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _gen5_preserve_fused_ot(hw, respect_user_gloss=respect_user_gloss)
            _merge_prs_reading_gloss(hw)

    _gen15_reapply_oshb_splits(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen15_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _merge_prs_reading_gloss(hw)
            _drop_redundant_prs_suffix(hw)

    _gen15_finalize_b4_hebrew(verse, respect_user_gloss=respect_user_gloss)
    _gen15_promote_gkadd(verse)
    _gen15_dedupe_gk_add(verse)
    _fix_gen15_lxx_align(verse)
    _gen15_dedupe_gk_add(verse)
    normalize_verse_maqaf(verse)
    sanitize_verse_he_forms(verse)
    _sanitize_catss_pairs(verse)



# ── Génesis cap. 16 — Agar e Ismael (B0 stub) ─────────────────────────────────────────
def _gen16_apply_prs_splits(hw: dict, *, respect_user_gloss: bool = False) -> None:
    """PRS splits cap. 16 — Agar e Ismael."""
    raw = hw.get("raw") or ""

    if raw == "$PXT/Y":
        _gen6_split_at_prs(hw, stem_he="שִׁפְחָת", stem_morph="SUBS.F.SG.C",
            stem_es="sierva", strongs="H8198",
            suf_he="ִי", suf_morph="PRS.P1.COMMON.SG", suf_es="mía",
            respect_user_gloss=respect_user_gloss)
    elif raw == "$PXT/H":
        _gen6_split_at_prs(hw, stem_he="שִׁפְחַת", stem_morph="SUBS.F.SG.C",
            stem_es="sierva", strongs="H8198",
            suf_he="הּ", suf_morph="PRS.P3.F.SG", suf_es="su",
            respect_user_gloss=respect_user_gloss)
    elif raw == "$PXT/K":
        _gen6_split_at_prs(hw, stem_he="שִׁפְחָת", stem_morph="SUBS.F.SG.C",
            stem_es="sierva", strongs="H8198",
            suf_he="ֵךְ", suf_morph="PRS.P2.F.SG", suf_es="tu",
            respect_user_gloss=respect_user_gloss)
    elif raw == "GBRT/H":
        _gen6_split_at_prs(hw, stem_he="גְּבִרְתְּ", stem_morph="SUBS.F.SG.C",
            stem_es="señora", strongs="H1404",
            suf_he="הּ", suf_morph="PRS.P3.F.SG", suf_es="su",
            respect_user_gloss=respect_user_gloss)
    elif raw == "GBRT/K":
        _gen6_split_at_prs(hw, stem_he="גְּבִרְתֵּ", stem_morph="SUBS.F.SG.C",
            stem_es="señora", strongs="H1404",
            suf_he="ךְ", suf_morph="PRS.P2.F.SG", suf_es="tu",
            respect_user_gloss=respect_user_gloss)
    elif raw == "GBRT/Y":
        _gen6_split_at_prs(hw, stem_he="גְּבִרְתִּ", stem_morph="SUBS.F.SG.C",
            stem_es="señora", strongs="H1404",
            suf_he="י", suf_morph="PRS.P1.COMMON.SG", suf_es="mi",
            respect_user_gloss=respect_user_gloss)
    elif raw == "XMS/Y":
        _gen6_split_at_prs(hw, stem_he="חָמָס", stem_morph="SUBS.M.SG.ABS",
            stem_es="violencia", strongs="H2555",
            suf_he="י", suf_morph="PRS.P1.COMMON.SG", suf_es="mi",
            respect_user_gloss=respect_user_gloss)
    elif raw == "ZR(/K":
        _gen6_split_at_prs(hw, stem_he="זַרְע", stem_morph="SUBS.M.SG.C",
            stem_es="descendencia", strongs="H2233",
            suf_he="ךְ", suf_morph="PRS.P2.F.SG", suf_es="tu",
            respect_user_gloss=respect_user_gloss)
    elif raw == "BN/W":
        # construct form בְּנ (regular nun) + וֹ; OSHB splits בְּנ + ו
        _gen6_split_at_prs(hw, stem_he="בְּנ", stem_morph="SUBS.M.SG.C",
            stem_es="hijo", strongs="H1121",
            suf_he="וֹ", suf_morph="PRS.P3.M.SG", suf_es="",
            respect_user_gloss=respect_user_gloss)
    elif raw == "$M/H":
        _gen6_split_at_prs(hw, stem_he="שְׁמ", stem_morph="SUBS.M.SG.C",
            stem_es="nombre", strongs="H8034",
            suf_he="הּ", suf_morph="PRS.P3.F.SG", suf_es="",
            respect_user_gloss=respect_user_gloss)
    elif raw == "$M/W":
        # v11 שמו = שמ + וֹ; es_source=patch prevents _drop_redundant_prs_suffix
        _gen6_split_at_prs(hw, stem_he="שְׁמ", stem_morph="SUBS.M.SG.C",
            stem_es="nombre", strongs="H8034",
            suf_he="וֹ", suf_morph="PRS.P3.M.SG", suf_es="",
            respect_user_gloss=respect_user_gloss)
    elif raw == ")X/YW":
        # אֶחָי (brothers pl construct) + ו; OSHB splits אחי + ו
        _gen6_split_at_prs(hw, stem_he="אֶחָי", stem_morph="SUBS.M.PL.C",
            stem_es="hermanos", strongs="H251",
            suf_he="ו", suf_morph="PRS.P3.M.SG", suf_es="",
            respect_user_gloss=respect_user_gloss)
    elif raw == "YD/W":
        _gen6_split_at_prs(hw, stem_he="יָד", stem_morph="SUBS.F.SG.C",
            stem_es="mano", strongs="H3027",
            suf_he="וֹ", suf_morph="PRS.P3.M.SG", suf_es="su",
            respect_user_gloss=respect_user_gloss)
    elif raw == ")Y$/H":
        _gen6_split_at_prs(hw, stem_he="אִישׁ", stem_morph="SUBS.M.SG.C",
            stem_es="esposo", strongs="H376",
            suf_he="הּ", suf_morph="PRS.P3.F.SG", suf_es="su",
            respect_user_gloss=respect_user_gloss)
    elif raw == "W/YMC)/H":
        # v7 וימצאה: ו + ימצא + ה prs; es_source=patch protects PRS
        _gen6_split_at_prs(hw, stem_he="יִּמְצָאָ", stem_morph="VERB.QAL.WAYY.P3.M.SG",
            stem_es="halló",
            prefix_forms=["וַ"], prefix_morphs=["CONJ"], prefix_es=["y"],
            suf_he="הּ", suf_morph="PRS.P3.F.SG", suf_es="",
            respect_user_gloss=respect_user_gloss)
    elif raw == "W/T(N/H":
        # v6 ותענה: ו + תענ + ה prs; clears bogus ['ו','שרי'] prefix
        _gen6_split_at_prs(hw, stem_he="תְּעַנֶּ", stem_morph="VERB.PIL.WAYY.P3.F.SG",
            stem_es="afligió",
            prefix_forms=["וַ"], prefix_morphs=["CONJ"], prefix_es=["y"],
            suf_he="הָ", suf_morph="PRS.P3.F.SG", suf_es="",
            respect_user_gloss=respect_user_gloss)


def _gen16_reapply_oshb_splits(verse: dict, *, respect_user_gloss: bool = False) -> None:
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            _gen16_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)


def _fix_gen16_oshb_align(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Alineación OSHB cap. 16 — Agar e Ismael."""
    vrs = verse.get("verse", 0)

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            raw = hw.get("raw") or ""
            # L/H, L/W, W/L/H → OSHB omits these indirect-object pronoun pairs
            if raw in ("L/H", "L/W", "W/L/H"):
                hw["he_form"] = ""
                for k in ("prefix_forms", "prefix_morphs", "prefix_es",
                          "prefix_gr", "prs_suffix"):
                    hw.pop(k, None)

    if vrs == 1:
        for p in verse.get("pairs", []):
            for hw in p.get("he_words", []):
                raw = hw.get("raw") or ""
                if raw == "W/$M/H":
                    if not (hw.get("he_form") or "").strip():
                        hw["he_form"] = "שְׁמָ"
                        hw["he_morph"] = hw.get("he_morph") or "SUBS.M.SG.C"
                        _attach_prs_suffix(hw, "הּ", "PRS.P3.F.SG", "su")

    elif vrs == 2:
        for p in verse.get("pairs", []):
            for hw in p.get("he_words", []):
                raw = hw.get("raw") or ""
                # )BRM at pair 16 has שרי as he_form (mis-assignment) → fix to אברם
                # Use first-char check because _strip_niqqud doesn't strip vowel points
                if raw == ")BRM" and (hw.get("he_form") or "")[:1] == "ש":
                    hw["he_form"] = "אַבְרָם"
                # M/MN/H: prefix=['מ','נה'] hf='וַ' → prefix=['מִמֶּ'] hf='נָּה'
                elif raw == "M/MN/H":
                    hw["prefix_forms"] = ["מִמֶּ"]
                    hw["prefix_morphs"] = hw.get("prefix_morphs") or ["PREP"]
                    hw["he_form"] = "נָּה"
                    hw.pop("prs_suffix", None)

    elif vrs == 3:
        for p in verse.get("pairs", []):
            for hw in p.get("he_words", []):
                raw = hw.get("raw") or ""
                # L/)$H — missing ל prefix; OSHB has לְ+אִשָּׁה
                if raw == "L/)$H":
                    if not (hw.get("prefix_forms") or []):
                        hw["prefix_forms"] = ["לְ"]
                        hw["prefix_morphs"] = hw.get("prefix_morphs") or ["PREP"]
                        hw["prefix_es"] = hw.get("prefix_es") or [""]

    elif vrs == 6:
        for p in verse.get("pairs", []):
            for hw in p.get("he_words", []):
                raw = hw.get("raw") or ""
                # B/(YN/YK: hf='עינ', prs='יך' → hf='עיניִ', prs='ךְ'
                if raw == "B/(YN/YK":
                    hw["he_form"] = "עֵינַיִ"
                    hw["he_morph"] = hw.get("he_morph") or "SUBS.F.PL.C"
                    hw["prefix_forms"] = ["בְּ"]
                    hw["prefix_morphs"] = ["PREP"]
                    hw["prefix_es"] = hw.get("prefix_es") or ["en"]
                    prs = hw.get("prs_suffix") or {}
                    prs["he_form"] = "ךְ"
                    prs["he_morph"] = prs.get("he_morph") or "PRS.P2.F.SG"
                    hw["prs_suffix"] = prs
                # W/TBRX: pf=['מ'] → pf=['וַ']
                elif raw == "W/TBRX":
                    hw["prefix_forms"] = ["וַ"]
                    hw["prefix_morphs"] = ["CONJ"]
                    hw["prefix_es"] = hw.get("prefix_es") or ["y"]
                # M/PN/YH: hf='פנ' prs='יהָ' → hf='פָּנֵי' prs='הָ'
                elif raw == "M/PN/YH":
                    hw["he_form"] = "פָּנֵי"
                    hw["he_morph"] = hw.get("he_morph") or "SUBS.M.PL.C"
                    prs = hw.get("prs_suffix") or {}
                    prs["he_form"] = "הָ"
                    prs["he_morph"] = prs.get("he_morph") or "PRS.P3.F.SG"
                    hw["prs_suffix"] = prs
                # W/T(N/H and W/YMC)/H handled by _gen16_apply_prs_splits

    elif vrs == 8:
        for p in verse.get("pairs", []):
            for hw in p.get("he_words", []):
                raw = hw.get("raw") or ""
                # W/)N/H: pf=['ו','אנה'] hf='אנה' → pf=['וְ'], hf='אָנָה'
                if raw == "W/)N/H":
                    hw["prefix_forms"] = ["וְ"]
                    hw["prefix_morphs"] = ["CONJ"]
                    hw["prefix_es"] = hw.get("prefix_es") or ["y"]
                    hw["he_form"] = "אָנָה"
                    hw["he_morph"] = hw.get("he_morph") or "ADVE"
                    hw.pop("prs_suffix", None)
                # GBRT/Y → גברת+י
                elif raw == "GBRT/Y":
                    hw["he_form"] = "גְּבִרְתִּ"
                    hw["he_morph"] = hw.get("he_morph") or "SUBS.F.SG.C"
                    hw.pop("prefix_forms", None)
                    hw.pop("prefix_morphs", None)
                    hw.pop("prefix_es", None)
                    if not (hw.get("prs_suffix") or {}).get("he_form"):
                        _attach_prs_suffix(hw, "י", "PRS.P1.COMMON.SG", "mi")

    elif vrs == 9:
        pairs_9 = verse.get("pairs", [])
        n9 = len(pairs_9)
        for pi, p in enumerate(pairs_9):
            for hw in p.get("he_words", []):
                raw = hw.get("raw") or ""
                # GBRT/K → גברת+ך (handled by _gen16_apply_prs_splits)
                # GKADD at last pair = OSHB ידיה: add יָדֵי+הָ
                if raw == "GKADD" and pi == n9 - 1 and not (hw.get("he_form") or "").strip():
                    hw["he_form"] = "יָדֵי"
                    hw["he_morph"] = hw.get("he_morph") or "SUBS.F.DU.C"
                    hw["es_source"] = "patch"
                    if not (hw.get("prs_suffix") or {}).get("he_form"):
                        _attach_prs_suffix(hw, "הָ", "PRS.P3.F.SG", "")

    elif vrs == 11:
        pairs_11 = verse.get("pairs", [])
        n11 = len(pairs_11)
        for pi, p in enumerate(pairs_11):
            for hw in p.get("he_words", []):
                raw = hw.get("raw") or ""
                # HN/K (all variants): pf=['הרה'] hf='ו' → clear pf, hf='הנ', prs='ך'
                if raw in ("HN/K", "HNH/K", "HNK"):
                    hw["he_form"] = "הִנָּ"
                    hw["he_morph"] = hw.get("he_morph") or "PTCP.ABS"
                    hw["prefix_forms"] = []
                    hw["prefix_morphs"] = []
                    hw["prefix_es"] = []
                    if not (hw.get("prs_suffix") or {}).get("he_form"):
                        _attach_prs_suffix(hw, "ךְ", "PRS.P2.F.SG", "te")
                # $M/W handled by _gen16_apply_prs_splits (sets es_source=patch)
                # ')L at last pair → expand to אֶל prefix + עָנְיֵ + ךְ prs
                elif raw == ")L" and pi == n11 - 1:
                    hw["prefix_forms"] = ["אֶל"]
                    hw["prefix_morphs"] = ["PREP"]
                    hw["prefix_es"] = hw.get("prefix_es") or ["a"]
                    hw["he_form"] = "עָנְיֵ"
                    hw["he_morph"] = hw.get("he_morph") or "SUBS.M.SG.C"
                    hw["es_source"] = "patch"
                    if not (hw.get("prs_suffix") or {}).get("he_form"):
                        _attach_prs_suffix(hw, "ךְ", "PRS.P2.F.SG", "")

    elif vrs == 12:
        for p in verse.get("pairs", []):
            for hw in p.get("he_words", []):
                raw = hw.get("raw") or ""
                # B/W → OSHB omits this (not in token list)
                if raw == "B/W":
                    hw["he_form"] = ""
                    for k in ("prefix_forms", "prefix_morphs", "prefix_es", "prs_suffix"):
                        hw.pop(k, None)
                # )X/YW handled by _gen16_apply_prs_splits with אֶחָי + ו

    elif vrs == 13:
        for p in verse.get("pairs", []):
            for hw in p.get("he_words", []):
                raw = hw.get("raw") or ""
                if raw == "R)/Y":
                    hf = hw.get("he_form") or ""
                    pf = hw.get("prefix_forms") or []
                    # P8: pf=['ראי'] hf='כי' → clear pf, hf='ראי'
                    if _strip_niqqud(hf).startswith("כ") or (
                            pf and _strip_niqqud(pf[0]).startswith("ר")):
                        hw["prefix_forms"] = []
                        hw["prefix_morphs"] = []
                        hw["prefix_es"] = []
                        hw["he_form"] = "רֳאִי"
                        hw.pop("prs_suffix", None)
                    # P15: pf=['י'] hf='' → hf='ראִ', prs='י'
                    elif pf and _strip_niqqud(pf[0]) == "י" and not hf.strip():
                        hw["prefix_forms"] = []
                        hw["prefix_morphs"] = []
                        hw["prefix_es"] = []
                        hw["he_form"] = "רֹאִ"
                        _attach_prs_suffix(hw, "י", "PRS.P1.COMMON.SG", "")

    elif vrs == 14:
        for p in verse.get("pairs", []):
            for hw in p.get("he_words", []):
                raw = hw.get("raw") or ""
                # HNH standalone (P4) — already produced by P3 R)/Y prefix; zero this
                if raw == "HNH" and not (hw.get("prefix_forms") or []):
                    hw["he_form"] = ""
                # BYN standalone without ו prefix (P5) — duplicate of P3 R)/Y hf; zero
                elif raw == "BYN" and not (hw.get("prefix_forms") or []):
                    hw["he_form"] = ""
        # Clean up orphaned prefix arrays in empty GKADD pairs (after LXX may set them)
        for p in verse.get("pairs", []):
            for hw in p.get("he_words", []):
                if not (hw.get("he_form") or "").strip() and not (hw.get("prefix_forms") or []):
                    hw.pop("prefix_morphs", None)
                    hw.pop("prefix_es", None)

    elif vrs == 15:
        pass  # BN/W handled by _gen16_apply_prs_splits with בְּנ + וֹ

    elif vrs == 16:
        for p in verse.get("pairs", []):
            for hw in p.get("he_words", []):
                raw = hw.get("raw") or ""
                # $NH: hf='שש' (six) → 'שָׁנָה' (year) — mis-assigned he_form
                if raw == "$NH":
                    hw["he_form"] = "שָׁנָה"
                    hw["he_morph"] = hw.get("he_morph") or "SUBS.F.SG.ABS"
                # W/$$: pf=['שנים'] hf='ב' → pf=['וְ'], hf='שֵׁשׁ'
                elif raw == "W/$$":
                    hw["prefix_forms"] = ["וְ"]
                    hw["prefix_morphs"] = ["CONJ"]
                    hw["prefix_es"] = hw.get("prefix_es") or ["y"]
                    hw["he_form"] = "שֵׁשׁ"
                    hw["he_morph"] = hw.get("he_morph") or "NUM.M.SG.ABS"

    _gen15_strip_dot_prefixes(verse)
    _gen15_trim_prefix_lengths(verse)
    _fix_gen5_w_prefixes(verse)


def _fix_gen16_es_glosses(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Glosas español cap. 16 — pendiente B5."""
    _fix_gen5_numeric_glosses(verse, respect_user_gloss=respect_user_gloss)


def _gen16_finalize_prep_prs(verse: dict) -> None:
    _gen12_finalize_prep_prs(verse)


def _fix_gen16_lxx_align(verse: dict) -> None:
    """B8 reparto LXX cap. 16 — pendiente B8."""
    _fix_lxx_align_verse(verse)


def _patch_gen16(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Parches estructurales Génesis cap. 16 — Agar e Ismael."""
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            _gen16_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)

    _fix_gen16_oshb_align(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen16_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if not (
                (hw.get("raw") or "").endswith("}")
                or (
                    hw.get("es_source") == "patch_meta"
                    and not _strip_niqqud(hw.get("he_form") or "")
                )
            )
        ]
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if (hw.get("he_form") or "").strip()
            or (hw.get("prefix_forms") or [])
            or (hw.get("prs_suffix") or {}).get("he_form")
            or hw.get("raw") in ("=L/MYN/W", "=L/MYN/HW", "=VAV")
        ]

    verse["pairs"] = [
        p for p in verse.get("pairs", [])
        if p.get("he_words")
        or (p.get("gr_unicode") or "").strip()
        or p.get("kind") in ("heb_omit", "gk_add")
    ]

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _gen5_preserve_fused_ot(hw, respect_user_gloss=respect_user_gloss)
            _merge_prs_reading_gloss(hw)

    _gen16_reapply_oshb_splits(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen16_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _merge_prs_reading_gloss(hw)
            _drop_redundant_prs_suffix(hw)

    _gen16_finalize_prep_prs(verse)
    _fix_gen16_lxx_align(verse)
    _gen16_post_lxx_fix(verse)
    _gen15_strip_dot_prefixes(verse)
    normalize_verse_maqaf(verse)
    sanitize_verse_he_forms(verse)
    _sanitize_catss_pairs(verse)


def _gen16_post_lxx_fix(verse: dict) -> None:
    """Fixes to apply after LXX alignment (which may reset GKADD he_forms)."""
    vrs = verse.get("verse", 0)
    if vrs == 9:
        pairs = verse.get("pairs", [])
        n = len(pairs)
        for pi, p in enumerate(pairs):
            for hw in p.get("he_words", []):
                if (hw.get("raw") or "") == "GKADD" and pi == n - 1:
                    hw["he_form"] = "יָדֵי"
                    hw["he_morph"] = hw.get("he_morph") or "SUBS.F.DU.C"
                    hw["es_source"] = "patch"
                    if not (hw.get("prs_suffix") or {}).get("he_form"):
                        _attach_prs_suffix(hw, "הָ", "PRS.P3.F.SG", "")
    # Clean up orphaned prefix_morphs/prefix_es on GKADD pairs with empty prefix_forms
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if not (hw.get("he_form") or "").strip() and not (hw.get("prefix_forms") or []):
                hw.pop("prefix_morphs", None)
                hw.pop("prefix_es", None)


# ── Génesis cap. 17 — Circuncisión y nueva alianza (B0 stub) ─────────────────────────────────────────
def _gen17_apply_prs_splits(hw: dict, *, respect_user_gloss: bool = False) -> None:
    """PRS splits comunes caps. 17-30 — hereda ch16 y añade patrones frecuentes."""
    _gen16_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)

    raw = hw.get("raw") or ""
    prs_hf = (hw.get("prs_suffix") or {}).get("he_form") or ""

    # Corregir $M/H mal partida con sufijo masculino וֹ (bug heredado de ch16)
    if raw == "$M/H" and prs_hf == "וֹ":
        prs = hw.setdefault("prs_suffix", {})
        prs["he_form"] = "הּ"
        prs["he_morph"] = "PRS.P3.F.SG"
        return

    if prs_hf:
        return  # ya tiene PRS split aplicado

    hf = (hw.get("he_form") or "").strip()
    hk = _gen5_he_key({"he_form": hf})

    # ── BRYT/Y — pacto mío ─────────────────────────────────────────────────
    # NOTE: PREP+PRS splits (L/W, L/Y, L/K, L/H, L/HM, L/KM, L/NW, B/W, etc.)
    # are NOT applied globally here because many CATSS entries for these are
    # Greek-only pronoun additions with no corresponding OSHB token.
    # Per-chapter/verse fixes handle specific cases where OSHB coverage is confirmed.
    if raw == "BRYT/Y" and hk == "ברית":
        _gen6_split_at_prs(hw, stem_he="בְּרִיתִ", stem_morph="SUBS.F.SG.C",
                           stem_es="pacto", strongs="H1285",
                           suf_he="י", suf_morph="PRS.P1.COMMON.SG", suf_es="mi",
                           respect_user_gloss=respect_user_gloss)
    # ── BN/Y, BN/H — hijo mío / su hijo(a) ────────────────────────────────
    elif raw == "BN/Y" and hk == "בנ":
        _gen6_split_at_prs(hw, stem_he="בְּנִ", stem_morph="SUBS.M.SG.C",
                           stem_es="hijo", strongs="H1121",
                           suf_he="י", suf_morph="PRS.P1.COMMON.SG", suf_es="mi",
                           respect_user_gloss=respect_user_gloss)
    elif raw == "BN/H" and hk == "בנ":
        _gen6_split_at_prs(hw, stem_he="בְּנ", stem_morph="SUBS.M.SG.C",
                           stem_es="hijo", strongs="H1121",
                           suf_he="הּ", suf_morph="PRS.P3.F.SG", suf_es="su",
                           respect_user_gloss=respect_user_gloss)
    # ── )BY/W, )B/Y, )BY/H — padre ────────────────────────────────────────
    elif raw == ")BY/W" and hk == "אבי":
        _gen6_split_at_prs(hw, stem_he="אָבִי", stem_morph="SUBS.M.SG.C",
                           stem_es="padre", strongs="H1",
                           suf_he="ו", suf_morph="PRS.P3.M.SG", suf_es="su",
                           respect_user_gloss=respect_user_gloss)
    elif raw == ")B/Y" and hk == "אב":
        _gen6_split_at_prs(hw, stem_he="אָב", stem_morph="SUBS.M.SG.C",
                           stem_es="padre", strongs="H1",
                           suf_he="י", suf_morph="PRS.P1.COMMON.SG", suf_es="mi",
                           respect_user_gloss=respect_user_gloss)
    elif raw == ")BY/H" and hk == "אבי":
        _gen6_split_at_prs(hw, stem_he="אָבִ", stem_morph="SUBS.M.SG.C",
                           stem_es="padre", strongs="H1",
                           suf_he="הּ", suf_morph="PRS.P3.F.SG", suf_es="su",
                           respect_user_gloss=respect_user_gloss)
    # ── )WT/K, )T/K, )T/W — partícula obj + PRS ───────────────────────────
    elif raw == ")WT/K" and hk == "אותך":
        _gen6_split_at_prs(hw, stem_he="אֹות", stem_morph="PART.OBJ.DIR",
                           stem_es="", strongs="H853",
                           suf_he="ךָ", suf_morph="PRS.P2.M.SG", suf_es="",
                           respect_user_gloss=respect_user_gloss)
    elif raw == ")T/K" and hk == "אתך":
        _gen6_split_at_prs(hw, stem_he="אֶת", stem_morph="PREP",
                           stem_es="", strongs="H854",
                           suf_he="ךָ", suf_morph="PRS.P2.M.SG", suf_es="",
                           respect_user_gloss=respect_user_gloss)
    elif raw == ")T/W" and hk == "אתו":
        morph = hw.get("he_morph") or ""
        if "PART.OBJ.DIR" not in morph:
            _gen6_split_at_prs(hw, stem_he="אֶת", stem_morph="PREP",
                               stem_es="", strongs="H854",
                               suf_he="וֹ", suf_morph="PRS.P3.M.SG", suf_es="",
                               respect_user_gloss=respect_user_gloss)
    # ── )DN/Y — adoní ──────────────────────────────────────────────────────
    elif raw == ")DN/Y" and hk == "אדנ":
        _gen6_split_at_prs(hw, stem_he="אֲדֹנִ", stem_morph="SUBS.M.SG.C",
                           stem_es="señor", strongs="H113",
                           suf_he="י", suf_morph="PRS.P1.COMMON.SG", suf_es="mi",
                           respect_user_gloss=respect_user_gloss)
    # ── )M/W, )M/H — madre + PRS ──────────────────────────────────────────
    elif raw == ")M/W" and hk == "אמ":
        _gen6_split_at_prs(hw, stem_he="אִמּ", stem_morph="SUBS.F.SG.C",
                           stem_es="madre", strongs="H517",
                           suf_he="וֹ", suf_morph="PRS.P3.M.SG", suf_es="su",
                           respect_user_gloss=respect_user_gloss)
    elif raw == ")M/H" and hk == "אמ":
        _gen6_split_at_prs(hw, stem_he="אִמּ", stem_morph="SUBS.F.SG.C",
                           stem_es="madre", strongs="H517",
                           suf_he="הּ", suf_morph="PRS.P3.F.SG", suf_es="su",
                           respect_user_gloss=respect_user_gloss)
    # ── BT/W, BT/H — hija + PRS ───────────────────────────────────────────
    elif raw == "BT/W" and hk == "בת":
        _gen6_split_at_prs(hw, stem_he="בַּת", stem_morph="SUBS.F.SG.C",
                           stem_es="hija", strongs="H1323",
                           suf_he="וֹ", suf_morph="PRS.P3.M.SG", suf_es="su",
                           respect_user_gloss=respect_user_gloss)
    elif raw == "BT/H" and hk == "בת":
        _gen6_split_at_prs(hw, stem_he="בַּת", stem_morph="SUBS.F.SG.C",
                           stem_es="hija", strongs="H1323",
                           suf_he="הּ", suf_morph="PRS.P3.F.SG", suf_es="su",
                           respect_user_gloss=respect_user_gloss)


def _gen17_reapply_oshb_splits(verse: dict, *, respect_user_gloss: bool = False) -> None:
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            _gen17_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)


def _fix_gen17_oshb_align(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Alineación OSHB cap. 17 — pendiente B2."""
    _gen15_strip_dot_prefixes(verse)
    _gen15_trim_prefix_lengths(verse)
    _fix_gen5_w_prefixes(verse)
    _fix_gen5_after_maot(verse)


def _fix_gen17_es_glosses(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Glosas español cap. 17 — pendiente B5."""
    _fix_gen5_numeric_glosses(verse, respect_user_gloss=respect_user_gloss)


def _gen17_finalize_prep_prs(verse: dict) -> None:
    _gen12_finalize_prep_prs(verse)


def _fix_gen17_lxx_align(verse: dict) -> None:
    """B8 reparto LXX cap. 17 — pendiente B8."""
    _fix_lxx_align_verse(verse)


def _patch_gen17(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Parches estructurales Génesis cap. 17 — Circuncisión y nueva alianza."""
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            _gen17_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)

    _fix_gen17_oshb_align(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen17_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if not (
                (hw.get("raw") or "").endswith("}")
                or (
                    hw.get("es_source") == "patch_meta"
                    and not _strip_niqqud(hw.get("he_form") or "")
                )
            )
        ]
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if (hw.get("he_form") or "").strip()
            or (hw.get("prefix_forms") or [])
            or (hw.get("prs_suffix") or {}).get("he_form")
            or hw.get("raw") in ("=L/MYN/W", "=L/MYN/HW", "=VAV")
        ]

    verse["pairs"] = [
        p for p in verse.get("pairs", [])
        if p.get("he_words")
        or (p.get("gr_unicode") or "").strip()
        or p.get("kind") in ("heb_omit", "gk_add")
    ]

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _gen5_preserve_fused_ot(hw, respect_user_gloss=respect_user_gloss)
            _merge_prs_reading_gloss(hw)

    _gen17_reapply_oshb_splits(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen17_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _merge_prs_reading_gloss(hw)
            _drop_redundant_prs_suffix(hw)

    _gen17_finalize_prep_prs(verse)
    _fix_gen17_lxx_align(verse)
    _gen15_strip_dot_prefixes(verse)
    normalize_verse_maqaf(verse)
    sanitize_verse_he_forms(verse)
    _sanitize_catss_pairs(verse)


# ── Génesis cap. 18 — Las tres visitas / intercesión (B0 stub) ─────────────────────────────────────────
def _gen18_apply_prs_splits(hw: dict, *, respect_user_gloss: bool = False) -> None:
    """PRS splits cap. 18 — hereda ch17."""
    _gen17_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)


def _gen18_reapply_oshb_splits(verse: dict, *, respect_user_gloss: bool = False) -> None:
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            _gen18_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)


def _fix_gen18_oshb_align(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Alineación OSHB cap. 18 — pendiente B2."""
    _gen15_strip_dot_prefixes(verse)
    _gen15_trim_prefix_lengths(verse)
    _fix_gen5_w_prefixes(verse)
    _fix_gen5_after_maot(verse)


def _fix_gen18_es_glosses(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Glosas español cap. 18 — pendiente B5."""
    _fix_gen5_numeric_glosses(verse, respect_user_gloss=respect_user_gloss)


def _gen18_finalize_prep_prs(verse: dict) -> None:
    _gen12_finalize_prep_prs(verse)


def _fix_gen18_lxx_align(verse: dict) -> None:
    """B8 reparto LXX cap. 18 — pendiente B8."""
    _fix_lxx_align_verse(verse)


def _patch_gen18(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Parches estructurales Génesis cap. 18 — Las tres visitas / intercesión."""
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            _gen18_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)

    _fix_gen18_oshb_align(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen18_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if not (
                (hw.get("raw") or "").endswith("}")
                or (
                    hw.get("es_source") == "patch_meta"
                    and not _strip_niqqud(hw.get("he_form") or "")
                )
            )
        ]
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if (hw.get("he_form") or "").strip()
            or (hw.get("prefix_forms") or [])
            or (hw.get("prs_suffix") or {}).get("he_form")
            or hw.get("raw") in ("=L/MYN/W", "=L/MYN/HW", "=VAV")
        ]

    verse["pairs"] = [
        p for p in verse.get("pairs", [])
        if p.get("he_words")
        or (p.get("gr_unicode") or "").strip()
        or p.get("kind") in ("heb_omit", "gk_add")
    ]

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _gen5_preserve_fused_ot(hw, respect_user_gloss=respect_user_gloss)
            _merge_prs_reading_gloss(hw)

    _gen18_reapply_oshb_splits(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen18_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _merge_prs_reading_gloss(hw)
            _drop_redundant_prs_suffix(hw)

    _gen18_finalize_prep_prs(verse)
    _fix_gen18_lxx_align(verse)
    _gen15_strip_dot_prefixes(verse)
    normalize_verse_maqaf(verse)
    sanitize_verse_he_forms(verse)
    _sanitize_catss_pairs(verse)


# ── Génesis cap. 19 — Sodoma y Gomorra (B0 stub) ─────────────────────────────────────────
def _gen19_apply_prs_splits(hw: dict, *, respect_user_gloss: bool = False) -> None:
    """PRS splits cap. 19 — hereda ch17."""
    _gen17_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)


def _gen19_reapply_oshb_splits(verse: dict, *, respect_user_gloss: bool = False) -> None:
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            _gen19_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)


def _fix_gen19_oshb_align(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Alineación OSHB cap. 19 — pendiente B2."""
    _gen15_strip_dot_prefixes(verse)
    _gen15_trim_prefix_lengths(verse)
    _fix_gen5_w_prefixes(verse)
    _fix_gen5_after_maot(verse)


def _fix_gen19_es_glosses(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Glosas español cap. 19 — pendiente B5."""
    _fix_gen5_numeric_glosses(verse, respect_user_gloss=respect_user_gloss)


def _gen19_finalize_prep_prs(verse: dict) -> None:
    _gen12_finalize_prep_prs(verse)


def _fix_gen19_lxx_align(verse: dict) -> None:
    """B8 reparto LXX cap. 19 — pendiente B8."""
    _fix_lxx_align_verse(verse)


def _patch_gen19(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Parches estructurales Génesis cap. 19 — Sodoma y Gomorra."""
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            _gen19_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)

    _fix_gen19_oshb_align(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen19_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if not (
                (hw.get("raw") or "").endswith("}")
                or (
                    hw.get("es_source") == "patch_meta"
                    and not _strip_niqqud(hw.get("he_form") or "")
                )
            )
        ]
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if (hw.get("he_form") or "").strip()
            or (hw.get("prefix_forms") or [])
            or (hw.get("prs_suffix") or {}).get("he_form")
            or hw.get("raw") in ("=L/MYN/W", "=L/MYN/HW", "=VAV")
        ]

    verse["pairs"] = [
        p for p in verse.get("pairs", [])
        if p.get("he_words")
        or (p.get("gr_unicode") or "").strip()
        or p.get("kind") in ("heb_omit", "gk_add")
    ]

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _gen5_preserve_fused_ot(hw, respect_user_gloss=respect_user_gloss)
            _merge_prs_reading_gloss(hw)

    _gen19_reapply_oshb_splits(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen19_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _merge_prs_reading_gloss(hw)
            _drop_redundant_prs_suffix(hw)

    _gen19_finalize_prep_prs(verse)
    _fix_gen19_lxx_align(verse)
    _gen15_strip_dot_prefixes(verse)
    normalize_verse_maqaf(verse)
    sanitize_verse_he_forms(verse)
    _sanitize_catss_pairs(verse)


# ── Génesis cap. 20 — Abraham en Gerar (B0 stub) ─────────────────────────────────────────
def _gen20_apply_prs_splits(hw: dict, *, respect_user_gloss: bool = False) -> None:
    """PRS splits cap. 20 — hereda ch17."""
    _gen17_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)


def _gen20_reapply_oshb_splits(verse: dict, *, respect_user_gloss: bool = False) -> None:
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            _gen20_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)


def _fix_gen20_oshb_align(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Alineación OSHB cap. 20 — pendiente B2."""
    _gen15_strip_dot_prefixes(verse)
    _gen15_trim_prefix_lengths(verse)
    _fix_gen5_w_prefixes(verse)
    _fix_gen5_after_maot(verse)


def _fix_gen20_es_glosses(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Glosas español cap. 20 — pendiente B5."""
    _fix_gen5_numeric_glosses(verse, respect_user_gloss=respect_user_gloss)


def _gen20_finalize_prep_prs(verse: dict) -> None:
    _gen12_finalize_prep_prs(verse)


def _fix_gen20_lxx_align(verse: dict) -> None:
    """B8 reparto LXX cap. 20 — pendiente B8."""
    _fix_lxx_align_verse(verse)


def _patch_gen20(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Parches estructurales Génesis cap. 20 — Abraham en Gerar."""
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            _gen20_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)

    _fix_gen20_oshb_align(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen20_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if not (
                (hw.get("raw") or "").endswith("}")
                or (
                    hw.get("es_source") == "patch_meta"
                    and not _strip_niqqud(hw.get("he_form") or "")
                )
            )
        ]
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if (hw.get("he_form") or "").strip()
            or (hw.get("prefix_forms") or [])
            or (hw.get("prs_suffix") or {}).get("he_form")
            or hw.get("raw") in ("=L/MYN/W", "=L/MYN/HW", "=VAV")
        ]

    verse["pairs"] = [
        p for p in verse.get("pairs", [])
        if p.get("he_words")
        or (p.get("gr_unicode") or "").strip()
        or p.get("kind") in ("heb_omit", "gk_add")
    ]

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _gen5_preserve_fused_ot(hw, respect_user_gloss=respect_user_gloss)
            _merge_prs_reading_gloss(hw)

    _gen20_reapply_oshb_splits(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen20_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _merge_prs_reading_gloss(hw)
            _drop_redundant_prs_suffix(hw)

    _gen20_finalize_prep_prs(verse)
    _fix_gen20_lxx_align(verse)
    _gen15_strip_dot_prefixes(verse)
    normalize_verse_maqaf(verse)
    sanitize_verse_he_forms(verse)
    _sanitize_catss_pairs(verse)


# ── Génesis cap. 21 — Nacimiento de Isaac / Agar en el desierto (B0 stub) ─────────────────────────────────────────
def _gen21_apply_prs_splits(hw: dict, *, respect_user_gloss: bool = False) -> None:
    """PRS splits cap. 21 — hereda ch17."""
    _gen17_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)


def _gen21_reapply_oshb_splits(verse: dict, *, respect_user_gloss: bool = False) -> None:
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            _gen21_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)


def _fix_gen21_oshb_align(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Alineación OSHB cap. 21 — pendiente B2."""
    _gen15_strip_dot_prefixes(verse)
    _gen15_trim_prefix_lengths(verse)
    _fix_gen5_w_prefixes(verse)
    _fix_gen5_after_maot(verse)


def _fix_gen21_es_glosses(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Glosas español cap. 21 — pendiente B5."""
    _fix_gen5_numeric_glosses(verse, respect_user_gloss=respect_user_gloss)


def _gen21_finalize_prep_prs(verse: dict) -> None:
    _gen12_finalize_prep_prs(verse)


def _fix_gen21_lxx_align(verse: dict) -> None:
    """B8 reparto LXX cap. 21 — pendiente B8."""
    _fix_lxx_align_verse(verse)


def _patch_gen21(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Parches estructurales Génesis cap. 21 — Nacimiento de Isaac / Agar en el desierto."""
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            _gen21_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)

    _fix_gen21_oshb_align(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen21_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if not (
                (hw.get("raw") or "").endswith("}")
                or (
                    hw.get("es_source") == "patch_meta"
                    and not _strip_niqqud(hw.get("he_form") or "")
                )
            )
        ]
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if (hw.get("he_form") or "").strip()
            or (hw.get("prefix_forms") or [])
            or (hw.get("prs_suffix") or {}).get("he_form")
            or hw.get("raw") in ("=L/MYN/W", "=L/MYN/HW", "=VAV")
        ]

    verse["pairs"] = [
        p for p in verse.get("pairs", [])
        if p.get("he_words")
        or (p.get("gr_unicode") or "").strip()
        or p.get("kind") in ("heb_omit", "gk_add")
    ]

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _gen5_preserve_fused_ot(hw, respect_user_gloss=respect_user_gloss)
            _merge_prs_reading_gloss(hw)

    _gen21_reapply_oshb_splits(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen21_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _merge_prs_reading_gloss(hw)
            _drop_redundant_prs_suffix(hw)

    _gen21_finalize_prep_prs(verse)
    _fix_gen21_lxx_align(verse)
    _gen15_strip_dot_prefixes(verse)
    normalize_verse_maqaf(verse)
    sanitize_verse_he_forms(verse)
    _sanitize_catss_pairs(verse)


# ── Génesis cap. 22 — Sacrificio de Isaac (Aqedá) (B0 stub) ─────────────────────────────────────────
def _gen22_apply_prs_splits(hw: dict, *, respect_user_gloss: bool = False) -> None:
    """PRS splits cap. 22 — hereda ch17."""
    _gen17_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)


def _gen22_reapply_oshb_splits(verse: dict, *, respect_user_gloss: bool = False) -> None:
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            _gen22_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)


def _fix_gen22_oshb_align(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Alineación OSHB cap. 22 — pendiente B2."""
    _gen15_strip_dot_prefixes(verse)
    _gen15_trim_prefix_lengths(verse)
    _fix_gen5_w_prefixes(verse)
    _fix_gen5_after_maot(verse)


def _fix_gen22_es_glosses(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Glosas español cap. 22 — pendiente B5."""
    _fix_gen5_numeric_glosses(verse, respect_user_gloss=respect_user_gloss)


def _gen22_finalize_prep_prs(verse: dict) -> None:
    _gen12_finalize_prep_prs(verse)


def _fix_gen22_lxx_align(verse: dict) -> None:
    """B8 reparto LXX cap. 22 — pendiente B8."""
    _fix_lxx_align_verse(verse)


def _patch_gen22(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Parches estructurales Génesis cap. 22 — Sacrificio de Isaac (Aqedá)."""
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            _gen22_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)

    _fix_gen22_oshb_align(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen22_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if not (
                (hw.get("raw") or "").endswith("}")
                or (
                    hw.get("es_source") == "patch_meta"
                    and not _strip_niqqud(hw.get("he_form") or "")
                )
            )
        ]
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if (hw.get("he_form") or "").strip()
            or (hw.get("prefix_forms") or [])
            or (hw.get("prs_suffix") or {}).get("he_form")
            or hw.get("raw") in ("=L/MYN/W", "=L/MYN/HW", "=VAV")
        ]

    verse["pairs"] = [
        p for p in verse.get("pairs", [])
        if p.get("he_words")
        or (p.get("gr_unicode") or "").strip()
        or p.get("kind") in ("heb_omit", "gk_add")
    ]

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _gen5_preserve_fused_ot(hw, respect_user_gloss=respect_user_gloss)
            _merge_prs_reading_gloss(hw)

    _gen22_reapply_oshb_splits(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen22_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _merge_prs_reading_gloss(hw)
            _drop_redundant_prs_suffix(hw)

    _gen22_finalize_prep_prs(verse)
    _fix_gen22_lxx_align(verse)
    _gen15_strip_dot_prefixes(verse)
    normalize_verse_maqaf(verse)
    sanitize_verse_he_forms(verse)
    _sanitize_catss_pairs(verse)


# ── Génesis cap. 23 — Muerte y sepultura de Sara (B0 stub) ─────────────────────────────────────────
def _gen23_apply_prs_splits(hw: dict, *, respect_user_gloss: bool = False) -> None:
    """PRS splits cap. 23 — hereda ch17."""
    _gen17_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)


def _gen23_reapply_oshb_splits(verse: dict, *, respect_user_gloss: bool = False) -> None:
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            _gen23_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)


def _fix_gen23_oshb_align(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Alineación OSHB cap. 23 — pendiente B2."""
    _gen15_strip_dot_prefixes(verse)
    _gen15_trim_prefix_lengths(verse)
    _fix_gen5_w_prefixes(verse)
    _fix_gen5_after_maot(verse)


def _fix_gen23_es_glosses(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Glosas español cap. 23 — pendiente B5."""
    _fix_gen5_numeric_glosses(verse, respect_user_gloss=respect_user_gloss)


def _gen23_finalize_prep_prs(verse: dict) -> None:
    _gen12_finalize_prep_prs(verse)


def _fix_gen23_lxx_align(verse: dict) -> None:
    """B8 reparto LXX cap. 23 — pendiente B8."""
    _fix_lxx_align_verse(verse)


def _patch_gen23(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Parches estructurales Génesis cap. 23 — Muerte y sepultura de Sara."""
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            _gen23_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)

    _fix_gen23_oshb_align(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen23_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if not (
                (hw.get("raw") or "").endswith("}")
                or (
                    hw.get("es_source") == "patch_meta"
                    and not _strip_niqqud(hw.get("he_form") or "")
                )
            )
        ]
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if (hw.get("he_form") or "").strip()
            or (hw.get("prefix_forms") or [])
            or (hw.get("prs_suffix") or {}).get("he_form")
            or hw.get("raw") in ("=L/MYN/W", "=L/MYN/HW", "=VAV")
        ]

    verse["pairs"] = [
        p for p in verse.get("pairs", [])
        if p.get("he_words")
        or (p.get("gr_unicode") or "").strip()
        or p.get("kind") in ("heb_omit", "gk_add")
    ]

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _gen5_preserve_fused_ot(hw, respect_user_gloss=respect_user_gloss)
            _merge_prs_reading_gloss(hw)

    _gen23_reapply_oshb_splits(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen23_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _merge_prs_reading_gloss(hw)
            _drop_redundant_prs_suffix(hw)

    _gen23_finalize_prep_prs(verse)
    _fix_gen23_lxx_align(verse)
    _gen15_strip_dot_prefixes(verse)
    normalize_verse_maqaf(verse)
    sanitize_verse_he_forms(verse)
    _sanitize_catss_pairs(verse)


# ── Génesis cap. 24 — Boda de Isaac y Rebeca (B0 stub) ─────────────────────────────────────────
def _gen24_apply_prs_splits(hw: dict, *, respect_user_gloss: bool = False) -> None:
    """PRS splits cap. 24 — hereda ch17."""
    _gen17_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)


def _gen24_reapply_oshb_splits(verse: dict, *, respect_user_gloss: bool = False) -> None:
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            _gen24_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)


def _fix_gen24_oshb_align(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Alineación OSHB cap. 24 — pendiente B2."""
    _gen15_strip_dot_prefixes(verse)
    _gen15_trim_prefix_lengths(verse)
    _fix_gen5_w_prefixes(verse)
    _fix_gen5_after_maot(verse)


def _fix_gen24_es_glosses(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Glosas español cap. 24 — pendiente B5."""
    _fix_gen5_numeric_glosses(verse, respect_user_gloss=respect_user_gloss)


def _gen24_finalize_prep_prs(verse: dict) -> None:
    _gen12_finalize_prep_prs(verse)


def _fix_gen24_lxx_align(verse: dict) -> None:
    """B8 reparto LXX cap. 24 — pendiente B8."""
    _fix_lxx_align_verse(verse)


def _patch_gen24(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Parches estructurales Génesis cap. 24 — Boda de Isaac y Rebeca."""
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            _gen24_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)

    _fix_gen24_oshb_align(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen24_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if not (
                (hw.get("raw") or "").endswith("}")
                or (
                    hw.get("es_source") == "patch_meta"
                    and not _strip_niqqud(hw.get("he_form") or "")
                )
            )
        ]
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if (hw.get("he_form") or "").strip()
            or (hw.get("prefix_forms") or [])
            or (hw.get("prs_suffix") or {}).get("he_form")
            or hw.get("raw") in ("=L/MYN/W", "=L/MYN/HW", "=VAV")
        ]

    verse["pairs"] = [
        p for p in verse.get("pairs", [])
        if p.get("he_words")
        or (p.get("gr_unicode") or "").strip()
        or p.get("kind") in ("heb_omit", "gk_add")
    ]

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _gen5_preserve_fused_ot(hw, respect_user_gloss=respect_user_gloss)
            _merge_prs_reading_gloss(hw)

    _gen24_reapply_oshb_splits(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen24_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _merge_prs_reading_gloss(hw)
            _drop_redundant_prs_suffix(hw)

    _gen24_finalize_prep_prs(verse)
    _fix_gen24_lxx_align(verse)
    _gen15_strip_dot_prefixes(verse)
    normalize_verse_maqaf(verse)
    sanitize_verse_he_forms(verse)
    _sanitize_catss_pairs(verse)


# ── Génesis cap. 25 — Muerte de Abraham / Esaú y Jacob (B0 stub) ─────────────────────────────────────────
def _gen25_apply_prs_splits(hw: dict, *, respect_user_gloss: bool = False) -> None:
    """PRS splits cap. 25 — hereda ch17."""
    _gen17_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)


def _gen25_reapply_oshb_splits(verse: dict, *, respect_user_gloss: bool = False) -> None:
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            _gen25_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)


def _fix_gen25_oshb_align(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Alineación OSHB cap. 25 — pendiente B2."""
    _gen15_strip_dot_prefixes(verse)
    _gen15_trim_prefix_lengths(verse)
    _fix_gen5_w_prefixes(verse)
    _fix_gen5_after_maot(verse)


def _fix_gen25_es_glosses(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Glosas español cap. 25 — pendiente B5."""
    _fix_gen5_numeric_glosses(verse, respect_user_gloss=respect_user_gloss)


def _gen25_finalize_prep_prs(verse: dict) -> None:
    _gen12_finalize_prep_prs(verse)


def _fix_gen25_lxx_align(verse: dict) -> None:
    """B8 reparto LXX cap. 25 — pendiente B8."""
    _fix_lxx_align_verse(verse)


def _patch_gen25(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Parches estructurales Génesis cap. 25 — Muerte de Abraham / Esaú y Jacob."""
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            _gen25_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)

    _fix_gen25_oshb_align(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen25_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if not (
                (hw.get("raw") or "").endswith("}")
                or (
                    hw.get("es_source") == "patch_meta"
                    and not _strip_niqqud(hw.get("he_form") or "")
                )
            )
        ]
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if (hw.get("he_form") or "").strip()
            or (hw.get("prefix_forms") or [])
            or (hw.get("prs_suffix") or {}).get("he_form")
            or hw.get("raw") in ("=L/MYN/W", "=L/MYN/HW", "=VAV")
        ]

    verse["pairs"] = [
        p for p in verse.get("pairs", [])
        if p.get("he_words")
        or (p.get("gr_unicode") or "").strip()
        or p.get("kind") in ("heb_omit", "gk_add")
    ]

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _gen5_preserve_fused_ot(hw, respect_user_gloss=respect_user_gloss)
            _merge_prs_reading_gloss(hw)

    _gen25_reapply_oshb_splits(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen25_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _merge_prs_reading_gloss(hw)
            _drop_redundant_prs_suffix(hw)

    _gen25_finalize_prep_prs(verse)
    _fix_gen25_lxx_align(verse)
    _gen15_strip_dot_prefixes(verse)
    normalize_verse_maqaf(verse)
    sanitize_verse_he_forms(verse)
    _sanitize_catss_pairs(verse)


# ── Génesis cap. 26 — Isaac en Gerar / pozos (B0 stub) ─────────────────────────────────────────
def _gen26_apply_prs_splits(hw: dict, *, respect_user_gloss: bool = False) -> None:
    """PRS splits cap. 26 — hereda ch17."""
    _gen17_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)


def _gen26_reapply_oshb_splits(verse: dict, *, respect_user_gloss: bool = False) -> None:
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            _gen26_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)


def _fix_gen26_oshb_align(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Alineación OSHB cap. 26 — pendiente B2."""
    _gen15_strip_dot_prefixes(verse)
    _gen15_trim_prefix_lengths(verse)
    _fix_gen5_w_prefixes(verse)
    _fix_gen5_after_maot(verse)


def _fix_gen26_es_glosses(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Glosas español cap. 26 — pendiente B5."""
    _fix_gen5_numeric_glosses(verse, respect_user_gloss=respect_user_gloss)


def _gen26_finalize_prep_prs(verse: dict) -> None:
    _gen12_finalize_prep_prs(verse)


def _fix_gen26_lxx_align(verse: dict) -> None:
    """B8 reparto LXX cap. 26 — pendiente B8."""
    _fix_lxx_align_verse(verse)


def _patch_gen26(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Parches estructurales Génesis cap. 26 — Isaac en Gerar / pozos."""
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            _gen26_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)

    _fix_gen26_oshb_align(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen26_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if not (
                (hw.get("raw") or "").endswith("}")
                or (
                    hw.get("es_source") == "patch_meta"
                    and not _strip_niqqud(hw.get("he_form") or "")
                )
            )
        ]
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if (hw.get("he_form") or "").strip()
            or (hw.get("prefix_forms") or [])
            or (hw.get("prs_suffix") or {}).get("he_form")
            or hw.get("raw") in ("=L/MYN/W", "=L/MYN/HW", "=VAV")
        ]

    verse["pairs"] = [
        p for p in verse.get("pairs", [])
        if p.get("he_words")
        or (p.get("gr_unicode") or "").strip()
        or p.get("kind") in ("heb_omit", "gk_add")
    ]

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _gen5_preserve_fused_ot(hw, respect_user_gloss=respect_user_gloss)
            _merge_prs_reading_gloss(hw)

    _gen26_reapply_oshb_splits(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen26_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _merge_prs_reading_gloss(hw)
            _drop_redundant_prs_suffix(hw)

    _gen26_finalize_prep_prs(verse)
    _fix_gen26_lxx_align(verse)
    _gen15_strip_dot_prefixes(verse)
    normalize_verse_maqaf(verse)
    sanitize_verse_he_forms(verse)
    _sanitize_catss_pairs(verse)


# ── Génesis cap. 27 — El engaño de Jacob (B0 stub) ─────────────────────────────────────────
def _gen27_apply_prs_splits(hw: dict, *, respect_user_gloss: bool = False) -> None:
    """PRS splits cap. 27 — hereda ch17."""
    _gen17_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)


def _gen27_reapply_oshb_splits(verse: dict, *, respect_user_gloss: bool = False) -> None:
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            _gen27_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)


def _fix_gen27_oshb_align(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Alineación OSHB cap. 27 — pendiente B2."""
    _gen15_strip_dot_prefixes(verse)
    _gen15_trim_prefix_lengths(verse)
    _fix_gen5_w_prefixes(verse)
    _fix_gen5_after_maot(verse)


def _fix_gen27_es_glosses(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Glosas español cap. 27 — pendiente B5."""
    _fix_gen5_numeric_glosses(verse, respect_user_gloss=respect_user_gloss)


def _gen27_finalize_prep_prs(verse: dict) -> None:
    _gen12_finalize_prep_prs(verse)


def _fix_gen27_lxx_align(verse: dict) -> None:
    """B8 reparto LXX cap. 27 — pendiente B8."""
    _fix_lxx_align_verse(verse)


def _patch_gen27(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Parches estructurales Génesis cap. 27 — El engaño de Jacob."""
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            _gen27_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)

    _fix_gen27_oshb_align(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen27_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if not (
                (hw.get("raw") or "").endswith("}")
                or (
                    hw.get("es_source") == "patch_meta"
                    and not _strip_niqqud(hw.get("he_form") or "")
                )
            )
        ]
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if (hw.get("he_form") or "").strip()
            or (hw.get("prefix_forms") or [])
            or (hw.get("prs_suffix") or {}).get("he_form")
            or hw.get("raw") in ("=L/MYN/W", "=L/MYN/HW", "=VAV")
        ]

    verse["pairs"] = [
        p for p in verse.get("pairs", [])
        if p.get("he_words")
        or (p.get("gr_unicode") or "").strip()
        or p.get("kind") in ("heb_omit", "gk_add")
    ]

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _gen5_preserve_fused_ot(hw, respect_user_gloss=respect_user_gloss)
            _merge_prs_reading_gloss(hw)

    _gen27_reapply_oshb_splits(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen27_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _merge_prs_reading_gloss(hw)
            _drop_redundant_prs_suffix(hw)

    _gen27_finalize_prep_prs(verse)
    _fix_gen27_lxx_align(verse)
    _gen15_strip_dot_prefixes(verse)
    normalize_verse_maqaf(verse)
    sanitize_verse_he_forms(verse)
    _sanitize_catss_pairs(verse)


# ── Génesis cap. 28 — Sueño de Jacob en Betel (B0 stub) ─────────────────────────────────────────
def _gen28_apply_prs_splits(hw: dict, *, respect_user_gloss: bool = False) -> None:
    """PRS splits cap. 28 — hereda ch17."""
    _gen17_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)


def _gen28_reapply_oshb_splits(verse: dict, *, respect_user_gloss: bool = False) -> None:
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            _gen28_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)


def _fix_gen28_oshb_align(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Alineación OSHB cap. 28 — pendiente B2."""
    _gen15_strip_dot_prefixes(verse)
    _gen15_trim_prefix_lengths(verse)
    _fix_gen5_w_prefixes(verse)
    _fix_gen5_after_maot(verse)


def _fix_gen28_es_glosses(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Glosas español cap. 28 — pendiente B5."""
    _fix_gen5_numeric_glosses(verse, respect_user_gloss=respect_user_gloss)


def _gen28_finalize_prep_prs(verse: dict) -> None:
    _gen12_finalize_prep_prs(verse)


def _fix_gen28_lxx_align(verse: dict) -> None:
    """B8 reparto LXX cap. 28 — pendiente B8."""
    _fix_lxx_align_verse(verse)


def _patch_gen28(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Parches estructurales Génesis cap. 28 — Sueño de Jacob en Betel."""
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            _gen28_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)

    _fix_gen28_oshb_align(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen28_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if not (
                (hw.get("raw") or "").endswith("}")
                or (
                    hw.get("es_source") == "patch_meta"
                    and not _strip_niqqud(hw.get("he_form") or "")
                )
            )
        ]
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if (hw.get("he_form") or "").strip()
            or (hw.get("prefix_forms") or [])
            or (hw.get("prs_suffix") or {}).get("he_form")
            or hw.get("raw") in ("=L/MYN/W", "=L/MYN/HW", "=VAV")
        ]

    verse["pairs"] = [
        p for p in verse.get("pairs", [])
        if p.get("he_words")
        or (p.get("gr_unicode") or "").strip()
        or p.get("kind") in ("heb_omit", "gk_add")
    ]

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _gen5_preserve_fused_ot(hw, respect_user_gloss=respect_user_gloss)
            _merge_prs_reading_gloss(hw)

    _gen28_reapply_oshb_splits(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen28_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _merge_prs_reading_gloss(hw)
            _drop_redundant_prs_suffix(hw)

    _gen28_finalize_prep_prs(verse)
    _fix_gen28_lxx_align(verse)
    _gen15_strip_dot_prefixes(verse)
    normalize_verse_maqaf(verse)
    sanitize_verse_he_forms(verse)
    _sanitize_catss_pairs(verse)


# ── Génesis cap. 29 — Jacob y Labán / Lea y Raquel (B0 stub) ─────────────────────────────────────────
def _gen29_apply_prs_splits(hw: dict, *, respect_user_gloss: bool = False) -> None:
    """PRS splits cap. 29 — hereda ch17."""
    _gen17_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)


def _gen29_reapply_oshb_splits(verse: dict, *, respect_user_gloss: bool = False) -> None:
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            _gen29_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)


def _fix_gen29_oshb_align(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Alineación OSHB cap. 29 — pendiente B2."""
    _gen15_strip_dot_prefixes(verse)
    _gen15_trim_prefix_lengths(verse)
    _fix_gen5_w_prefixes(verse)
    _fix_gen5_after_maot(verse)


def _fix_gen29_es_glosses(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Glosas español cap. 29 — pendiente B5."""
    _fix_gen5_numeric_glosses(verse, respect_user_gloss=respect_user_gloss)


def _gen29_finalize_prep_prs(verse: dict) -> None:
    _gen12_finalize_prep_prs(verse)


def _fix_gen29_lxx_align(verse: dict) -> None:
    """B8 reparto LXX cap. 29 — pendiente B8."""
    _fix_lxx_align_verse(verse)


def _patch_gen29(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Parches estructurales Génesis cap. 29 — Jacob y Labán / Lea y Raquel."""
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            _gen29_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)

    _fix_gen29_oshb_align(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen29_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if not (
                (hw.get("raw") or "").endswith("}")
                or (
                    hw.get("es_source") == "patch_meta"
                    and not _strip_niqqud(hw.get("he_form") or "")
                )
            )
        ]
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if (hw.get("he_form") or "").strip()
            or (hw.get("prefix_forms") or [])
            or (hw.get("prs_suffix") or {}).get("he_form")
            or hw.get("raw") in ("=L/MYN/W", "=L/MYN/HW", "=VAV")
        ]

    verse["pairs"] = [
        p for p in verse.get("pairs", [])
        if p.get("he_words")
        or (p.get("gr_unicode") or "").strip()
        or p.get("kind") in ("heb_omit", "gk_add")
    ]

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _gen5_preserve_fused_ot(hw, respect_user_gloss=respect_user_gloss)
            _merge_prs_reading_gloss(hw)

    _gen29_reapply_oshb_splits(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen29_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _merge_prs_reading_gloss(hw)
            _drop_redundant_prs_suffix(hw)

    _gen29_finalize_prep_prs(verse)
    _fix_gen29_lxx_align(verse)
    _gen15_strip_dot_prefixes(verse)
    normalize_verse_maqaf(verse)
    sanitize_verse_he_forms(verse)
    _sanitize_catss_pairs(verse)


# ── Génesis cap. 30 — Hijos de Jacob / ganado moteado (B0 stub) ─────────────────────────────────────────
def _gen30_apply_prs_splits(hw: dict, *, respect_user_gloss: bool = False) -> None:
    """PRS splits cap. 30 — hereda ch17."""
    _gen17_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)


def _gen30_reapply_oshb_splits(verse: dict, *, respect_user_gloss: bool = False) -> None:
    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            _gen30_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)


def _fix_gen30_oshb_align(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Alineación OSHB cap. 30 — pendiente B2."""
    _gen15_strip_dot_prefixes(verse)
    _gen15_trim_prefix_lengths(verse)
    _fix_gen5_w_prefixes(verse)
    _fix_gen5_after_maot(verse)


def _fix_gen30_es_glosses(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Glosas español cap. 30 — pendiente B5."""
    _fix_gen5_numeric_glosses(verse, respect_user_gloss=respect_user_gloss)


def _gen30_finalize_prep_prs(verse: dict) -> None:
    _gen12_finalize_prep_prs(verse)


def _fix_gen30_lxx_align(verse: dict) -> None:
    """B8 reparto LXX cap. 30 — pendiente B8."""
    _fix_lxx_align_verse(verse)


def _patch_gen30(verse: dict, *, respect_user_gloss: bool = False) -> None:
    """Parches estructurales Génesis cap. 30 — Hijos de Jacob / ganado moteado."""
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            _gen30_apply_prs_splits(hw, respect_user_gloss=respect_user_gloss)

    _fix_gen30_oshb_align(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen30_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if not (
                (hw.get("raw") or "").endswith("}")
                or (
                    hw.get("es_source") == "patch_meta"
                    and not _strip_niqqud(hw.get("he_form") or "")
                )
            )
        ]
        p["he_words"] = [
            hw for hw in p.get("he_words", [])
            if (hw.get("he_form") or "").strip()
            or (hw.get("prefix_forms") or [])
            or (hw.get("prs_suffix") or {}).get("he_form")
            or hw.get("raw") in ("=L/MYN/W", "=L/MYN/HW", "=VAV")
        ]

    verse["pairs"] = [
        p for p in verse.get("pairs", [])
        if p.get("he_words")
        or (p.get("gr_unicode") or "").strip()
        or p.get("kind") in ("heb_omit", "gk_add")
    ]

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _gen5_preserve_fused_ot(hw, respect_user_gloss=respect_user_gloss)
            _merge_prs_reading_gloss(hw)

    _gen30_reapply_oshb_splits(verse, respect_user_gloss=respect_user_gloss)
    _fix_gen30_es_glosses(verse, respect_user_gloss=respect_user_gloss)

    for p in verse.get("pairs", []):
        for hw in p.get("he_words", []):
            if respect_user_gloss and _has_user_gloss(hw):
                continue
            _merge_prs_reading_gloss(hw)
            _drop_redundant_prs_suffix(hw)

    _gen30_finalize_prep_prs(verse)
    _fix_gen30_lxx_align(verse)
    _gen15_strip_dot_prefixes(verse)
    normalize_verse_maqaf(verse)
    sanitize_verse_he_forms(verse)
    _sanitize_catss_pairs(verse)

def _patch_gen130(verse: dict) -> None:
    """Correcciones puntuales Gen 1:30 — desplazamientos masivos es/gr.

    Múltiples stems exhiben glosas españolas y griegas que pertenecen a tokens
    vecinos (sangrado por desalineación de la cadena). Cada caso se reasigna a
    partir del TM hebreo y la LXX del verso completo.  Lookups por raw para
    robustez frente a cambios de conteo de tokens.
    """
    for p in verse["pairs"]:
        for hw in p.get("he_words", []):
            raw = hw.get("raw", "")
            he  = hw.get("he_form", "")

            if raw == "(WP":
                # עוֹף "aves" → πετεινοῖς (gr=τοῖς era el artículo del token previo)
                hw["es"] = "aves"
                hw["gr_word"] = _san_gr("πετεινοῖς")
                hw.pop("es_source", None)
                hw.pop("gr_source", None)

            elif raw == "W/L/KL" and he == "כֹל":
                # Tercera ocurrencia de W/L/KL — la única con he_form='כֹל'
                # (las otras dos tienen 'כָל').  gr arrastrado desde (WP → παντὶ.
                hw["gr_word"] = _san_gr("παντὶ")
                hw.pop("gr_source", None)

            elif raw == "RWM&":
                # רוֹמֵשׂ "que se arrastra" (gr ἕρποντι ya correcto)
                hw["es"] = "que se arrastra"
                hw.pop("es_source", None)

            elif raw == "B/W":
                # בּוֹ → "en él" / ἐν ἑαυτῷ (mismo arreglo que Gen 1:11)
                # he_form actual es solo el sufijo waw 'ו'; restauramos forma plena.
                hw["he_form"]  = "בּוֹ"
                hw["he_morph"] = "PREP+PRS.P3.M.SG"
                hw["es"]       = "en él"
                hw["gr_word"]  = _san_gr("ἐν ἑαυτῷ")
                # La bet ya está dentro de he_form → vaciar prefijos para evitar
                # duplicación visual ('בֹּ' + 'בּוֹ').
                for lst in ("prefixes", "prefix_forms", "prefix_morphs",
                            "prefix_es", "prefix_gr", "prefix_labels",
                            "prefix_tier", "prefix_unicode"):
                    if lst in hw:
                        hw[lst] = []
                hw.pop("prs_suffix", None)
                hw.pop("es_source", None)
                hw.pop("gr_source", None)

            elif raw == "XYH":
                # חַיָּה "viviente" → ζωῆς (gr=πάντα arrastrado del siguiente token)
                hw["gr_word"] = _san_gr("ζωῆς")
                hw.pop("gr_source", None)

            elif raw == "KL":
                # כָּל standalone (no las W/L/KL) → "todo" / πάντα
                hw["es"] = "todo"
                hw["gr_word"] = _san_gr("πάντα")
                hw.pop("es_source", None)
                hw.pop("gr_source", None)

            elif raw == "YRQ":
                # יֶרֶק "verde" → χλωρὸν (gr=βρῶσιν arrastrado del siguiente)
                hw["gr_word"] = _san_gr("χλωρὸν")
                hw.pop("gr_source", None)

            elif raw == "L/)KLH":
                # לְאָכְלָה: prefijo לְ="para"/εἰς, stem אָכְלָה="comer"/βρῶσιν.
                # Stem actual tiene gr=εἰς (que pertenece al prefijo).
                hw["es"] = "comer"
                hw["gr_word"] = _san_gr("βρῶσιν")
                pfx_es = hw.get("prefix_es", [])
                if pfx_es:
                    hw["prefix_es"][0] = "para"
                pfx_gr = hw.get("prefix_gr", [])
                if pfx_gr:
                    hw["prefix_gr"][0] = _san_gr("εἰς")
                hw.pop("es_source", None)
                hw.pop("gr_source", None)


def apply_to_verse(verse: dict, corrections: list) -> int:
    idx = 0
    for pair in verse.get("pairs", []):
        for hw in pair.get("he_words", []):
            n_prefix = len(hw.get("prefixes", []))
            for lst in ("prefix_forms", "prefix_morphs", "prefix_es", "prefix_gr"):
                if lst not in hw:
                    hw[lst] = [""] * n_prefix
                while len(hw[lst]) < n_prefix:
                    hw[lst].append("")
            for k in range(n_prefix):
                if idx < len(corrections):
                    he, morph, es, gr = corrections[idx]
                    hw["prefix_forms"][k]  = he
                    hw["prefix_morphs"][k] = morph
                    hw["prefix_es"][k]     = es
                    hw["prefix_gr"][k]     = _san_gr(gr)
                    idx += 1
            if idx < len(corrections):
                he, morph, es, gr = corrections[idx]
                # Preservar maqaf (U+05BE) del OSHB original si la corrección
                # no lo incluye explícitamente — el OSHB es la fuente de verdad
                # para la presencia del maqaf en cada palabra.
                orig_he = hw.get("he_form", "")
                MAQAF = '\u05be'
                if MAQAF in orig_he and MAQAF not in he:
                    he = he + MAQAF
                hw["he_form"]  = he
                hw["he_morph"] = morph
                hw["es"]       = es
                hw["gr_word"]  = _san_gr(gr)
                # Limpiar marcas de auditoría (Corrección 13) si la corrección
                # manual sobreescribe es/gr_word: el `es_source` previo deja de
                # ser fiel a la fuente actual del valor.
                hw.pop("es_source", None)
                hw.pop("gr_source", None)
                idx += 1
    return idx


# ════════════════════════════════════════════════════════════════════════
#  Helpers para Global Pass 9 — corrección MISALIGN_ES por Strong
# ════════════════════════════════════════════════════════════════════════

# Palabras españolas "estructurales": artículos, preposiciones, conjunciones,
# pronombres átonos, demostrativos, relativos y partículas cortas que NUNCA
# son la glosa correcta de un sustantivo/verbo/adjetivo del Antiguo Testamento.
_ES_STRUCTURAL = {
    "el","la","los","las","un","una","unos","unas",
    "de","del","al","a","en","con","por","para","sin","sobre",
    "ante","tras","bajo","entre","hacia","hasta","desde","contra",
    "y","e","o","u","ni","pero","mas",
    "su","sus","mi","mis","tu","tus","nuestro","nuestra","nuestros","nuestras",
    "vuestro","vuestra","vuestros","vuestras",
    "lo","le","les","se","me","te","nos","os",
    "este","esta","estos","estas","esto",
    "ese","esa","esos","esas","eso",
    "aquel","aquella","aquellos","aquellas","aquello",
    "que","quien","quienes","cual","cuales","cuyo","cuya","cuyos","cuyas",
    "no","si",
    # variantes SpaRV1909 con tildes ya removidas
    "mas",
}

# Equivalencias específicas por Strong para evitar falsos positivos.
# Cada conjunto contiene las variantes normalizadas (lowercase, sin tildes,
# sin signos) que son glosas válidas alternativas. Si el `es` actual
# normalizado cae en este conjunto, se considera SINÓNIMO y se omite.
_STRONG_VARIANT_EXTRAS = {
    # Nombres divinos
    "H430":  {"dios","elohim"},
    "H3068": {"jehova","yhwh","yahveh","yahweh","yhvh","senor"},
    "H136":  {"adonai","senor"},
    "H410":  {"dios","el","poderoso"},
    "H7706": {"todopoderoso","shadday","sadai","shaddai"},
    # Variantes ortográficas SpaRV1909 (antiguas) vs modernas
    "H1254": {"creo","crio","creado","criado","crear","creando"},
    "H1961": {"sea","fue","era","sera","haya","ser","sido","sucedio",
              "aconteci","acontecio","fueron","hubo","hizo","hace"},
    "H559":  {"dijo","dicho","diciendo","decir","dice","dije","dira","diran","dirà"},
    "H1696": {"hablo","hablar","dijo","dicho","hablado","hablando"},
    # Pronombre demostrativo
    "H2088": {"este","esta","esto","ese"},
}


def _norm_es(s: str) -> str:
    """Normaliza una glosa española: lowercase, sin tildes, sin signos puntuación."""
    s = (s or "").lower().strip()
    s = "".join(c for c in unicodedata.normalize("NFD", s)
                if unicodedata.category(c) != "Mn")
    for ch in ".,;:¿?¡!«»\"'()[]·—–-":
        s = s.replace(ch, "")
    # Comprimir espacios
    s = " ".join(s.split())
    return s


def _norm_strong(s: str) -> str:
    """Normaliza un código Strong: `H07225a` → `H7225`."""
    if not s:
        return ""
    s = s.strip().upper()
    # Algunos JSON traen múltiples Strong separados por espacios; tomamos el primero.
    s = s.split()[0] if " " in s else s
    if not (s.startswith("H") or s.startswith("G")):
        return ""
    prefix = s[0]
    num = s[1:].rstrip("ABCDabcd")
    num = num.lstrip("0") or "0"
    return f"{prefix}{num}"


def _strong_variants(strong: str, idx: dict, top_k: int = 5):
    """Devuelve (set_variantes_palabra, lista_top_words[(word,count)], total_count).

    Las variantes incluyen:
      - cada palabra de contenido (no estructural) extraída de los top-K phrases
      - phrases enteros normalizados (para coincidencias multi-palabra)
      - extras manuales de `_STRONG_VARIANT_EXTRAS` (nombres divinos, etc.)
    """
    entries = idx.get(strong, [])
    if not entries:
        return set(), [], set(), 0
    total_count = sum(int(e.get("count", 0)) for e in entries)
    top = entries[:top_k]
    word_counts: dict = {}
    phrases_norm: set = set()
    for e in top:
        text = e.get("text", "") or ""
        # Saltar entradas con replacement char (encoding corrupto)
        if "\ufffd" in text:
            continue
        cnt = int(e.get("count", 0))
        phrase_n = _norm_es(text)
        if phrase_n:
            phrases_norm.add(phrase_n)
        for w in text.split():
            nw = _norm_es(w)
            if nw and nw not in _ES_STRUCTURAL and not nw.isdigit():
                word_counts[nw] = word_counts.get(nw, 0) + cnt
    sorted_words = sorted(word_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    variants = set(word_counts.keys()) | _STRONG_VARIANT_EXTRAS.get(strong, set())
    return variants, sorted_words, phrases_norm, total_count


def _is_content_morph(morph: str) -> bool:
    """¿Es una morfología de contenido (sustantivo/verbo/adjetivo/numeral/adverbio)?"""
    if not morph:
        return False
    m = morph.upper()
    for pre in ("SUBS", "VERBO", "ADJ", "NUM", "ADV", "NPROP"):
        if m.startswith(pre):
            return True
    return False


def _normalize_myn_raw(raw: str) -> list[str]:
    """Normaliza raw CATSS con MYN: L/MYN/H, LMYN/H, etc."""
    if not raw or "MYN" not in raw:
        return raw.split("/") if raw else []
    if "/" in raw:
        parts = raw.split("/")
        out = []
        for p in parts:
            if p.startswith("L") and "MYN" in p and p != "MYN":
                out.extend(["L", "MYN"])
                tail = p[p.index("MYN") + 3:]
                if tail:
                    out.append(tail)
            else:
                out.append(p)
        return out
    if raw.startswith("L") and "MYN" in raw:
        idx = raw.index("MYN")
        suffix = raw[idx + 3:]
        parts = ["L", "MYN"]
        if suffix.startswith("/"):
            suffix = suffix[1:]
        if suffix:
            parts.append(suffix)
        return parts
    return raw.split("/")


def _apply_myn_suffix_rule(hw: dict) -> None:
    """Restructura tokens cuyo raw contiene MYN + sufijo pronominal.

    Convierte la estructura de pipeline (MYN como prefijo, sufijo como stem)
    en la estructura canónica: stem=מִין(ֵ/ָ), prs_suffix=sufijo.
    Aplicable globalmente a todo Génesis (y futuros libros).
    """
    _MYN_SUFFIX_MAP = {
        "W":  ("מִין",  "וֹ",  "PRS.P3.M.SG"),   # לְמִינוֹ  "su especie" (m.sg)
        "HW": ("מִינֵ", "הוּ", "PRS.P3.M.SG"),   # לְמִינֵהוּ "su especie" (m.sg enfático)
        "H":  ("מִינָ", "הָ",  "PRS.P3.F.SG"),   # לְמִינָהּ  "su especie" (f.sg)
        "HM": ("מִינֵ", "הֶם", "PRS.P3.M.PL"),   # לְמִינֵהֶם "su especie" (m.pl)
    }
    raw = hw.get("raw", "")
    parts = _normalize_myn_raw(raw)
    if "MYN" not in parts:
        return
    myn_idx = parts.index("MYN")
    suffix_part = parts[-1]
    if suffix_part == "MYN" or suffix_part not in _MYN_SUFFIX_MAP:
        return
    stem_he, prs_he, prs_morph = _MYN_SUFFIX_MAP[suffix_part]

    # Número de prefijos reales que preceden a MYN en el raw (ej. L → 1 prefijo)
    n_pre_myn = myn_idx
    for lst in ("prefix_forms", "prefix_morphs", "prefix_es", "prefix_gr"):
        if lst in hw and len(hw[lst]) > n_pre_myn:
            hw[lst] = hw[lst][:n_pre_myn]
    if len(hw.get("prefixes", [])) > n_pre_myn:
        hw["prefixes"] = hw["prefixes"][:n_pre_myn]

    hw["he_form"]  = stem_he
    hw["he_morph"] = "SUBS.M.SG.C"
    hw["es"]       = "especie"
    hw["gr_word"]  = _san_gr("γένος")

    if not hw.get("prs_suffix"):
        hw["prs_suffix"] = {}
    prs = hw["prs_suffix"]
    prs["he_form"]  = prs_he
    prs["he_morph"] = prs_morph
    prs["es"]       = "su"
    prs["gr_word"]  = "—"


# Caps. Génesis con _patch_genN cableado (B0+).
_GEN_PATCH_BY_CHAPTER: dict[int, object] = {}


def _register_gen_patch(ch: int, fn) -> None:
    _GEN_PATCH_BY_CHAPTER[ch] = fn


def _gen_apply_chapter_patches(
    data: dict,
    *,
    respect_user_gloss: bool = False,
    label: str = "parches estructurales",
    min_ch: int = 2,
) -> None:
    """Aplica _patch_genN solo en caps del alcance (--chapter N)."""
    if ACTIVE_BOOK != "genesis":
        return
    from gen_chapter_scope import in_scope

    for ch in sorted(_GEN_PATCH_BY_CHAPTER):
        if ch < min_ch or not in_scope(ch):
            continue
        fn = _GEN_PATCH_BY_CHAPTER[ch]
        n = 0
        for v in data["verses"]:
            if v.get("chapter") == ch:
                fn(v, respect_user_gloss=respect_user_gloss)
                n += 1
        if n:
            suffix = ""
            if respect_user_gloss:
                suffix = ", sin pisar glosas editor"
            sys.stdout.write(f"  Gen cap. {ch}: {label} en {n} versos{suffix}\n")


def _gen_run_post_re(data: dict, ch: int, *, respect_user_gloss: bool = True) -> int:
    """Reaplica splits OSHB tras merge PRS (chN_re)."""
    from gen_chapter_scope import in_scope, skip_lxx_in_re, skip_spanish_passes

    if not in_scope(ch):
        return 0
    n = 0
    for v in data["verses"]:
        if v.get("chapter") != ch:
            continue
        if ch == 9:
            _gen9_reapply_oshb_splits(v, respect_user_gloss=respect_user_gloss)
            _fix_gen9_oshb_align(v, respect_user_gloss=respect_user_gloss)
        elif ch == 10:
            _gen10_reapply_oshb_splits(v, respect_user_gloss=respect_user_gloss)
            _fix_gen10_oshb_align(v, respect_user_gloss=respect_user_gloss)
            if not skip_spanish_passes():
                _fix_gen10_es_glosses(v, respect_user_gloss=respect_user_gloss)
            if not skip_lxx_in_re():
                _fix_gen10_lxx_align(v)
        elif ch == 11:
            _gen11_reapply_oshb_splits(v, respect_user_gloss=respect_user_gloss)
            _fix_gen11_oshb_align(v, respect_user_gloss=respect_user_gloss)
            if not skip_spanish_passes():
                _fix_gen11_es_glosses(v, respect_user_gloss=respect_user_gloss)
            if not skip_lxx_in_re():
                _fix_gen11_lxx_align(v)
        elif ch == 12:
            _gen12_reapply_oshb_splits(v, respect_user_gloss=respect_user_gloss)
            _fix_gen12_oshb_align(v, respect_user_gloss=respect_user_gloss)
            if not skip_spanish_passes():
                _fix_gen12_es_glosses(v, respect_user_gloss=respect_user_gloss)
            if not skip_lxx_in_re():
                _fix_gen12_lxx_align(v)
        elif ch == 13:
            _gen13_reapply_oshb_splits(v, respect_user_gloss=respect_user_gloss)
            _fix_gen13_oshb_align(v, respect_user_gloss=respect_user_gloss)
            if not skip_spanish_passes():
                _fix_gen13_es_glosses(v, respect_user_gloss=respect_user_gloss)
            if not skip_lxx_in_re():
                _fix_gen13_lxx_align(v)
        elif ch == 14:
            _gen14_reapply_oshb_splits(v, respect_user_gloss=respect_user_gloss)
            _fix_gen14_oshb_align(v, respect_user_gloss=respect_user_gloss)
            if not skip_spanish_passes():
                _fix_gen14_es_glosses(v, respect_user_gloss=respect_user_gloss)
            if not skip_lxx_in_re():
                _fix_gen14_lxx_align(v)
        elif ch == 15:
            _gen15_reapply_oshb_splits(v, respect_user_gloss=respect_user_gloss)
            _fix_gen15_oshb_align(v, respect_user_gloss=respect_user_gloss)
            if not skip_spanish_passes():
                _fix_gen15_es_glosses(v, respect_user_gloss=respect_user_gloss)
            if not skip_lxx_in_re():
                _fix_gen15_lxx_align(v)
        n += 1
    if n:
        sys.stdout.write(
            f"  Gen cap. {ch}: splits OSHB reaplicados ({n} versos, post-merge PRS)\n"
        )
    return n


def _gen_polish_chapter(data: dict, ch: int, polish_fn, label: str) -> None:
    from gen_chapter_scope import in_scope, skip_spanish_passes

    if skip_spanish_passes() or not in_scope(ch):
        return
    stats = polish_fn(data, respect_user_gloss=True)
    if any(stats.values()):
        sys.stdout.write(f"\n  ── Gen cap. {ch}: glosas español ({label}) ──\n")
        for k in ("prefix_es", "prs_es", "merged", "dedupe", "art_fix"):
            if stats.get(k):
                sys.stdout.write(f"    {k:<26}: {stats[k]}\n")
        if stats.get("skipped"):
            sys.stdout.write(f"    Saltados (glosa editor)   : {stats['skipped']}\n")


for _ch, _fn in (
    (2, _patch_gen2),
    (3, _patch_gen3),
    (4, _patch_gen4),
    (5, _patch_gen5),
    (6, _patch_gen6),
    (7, _patch_gen7),
    (8, _patch_gen8),
    (9, _patch_gen9),
    (10, _patch_gen10),
    (11, _patch_gen11),
    (12, _patch_gen12),
    (13, _patch_gen13),
    (14, _patch_gen14),
    (15, _patch_gen15),
    (16, _patch_gen16),
    (17, _patch_gen17),
    (18, _patch_gen18),
    (19, _patch_gen19),
    (20, _patch_gen20),
    (21, _patch_gen21),
    (22, _patch_gen22),
    (23, _patch_gen23),
    (24, _patch_gen24),
    (25, _patch_gen25),
    (26, _patch_gen26),
    (27, _patch_gen27),
    (28, _patch_gen28),
    (29, _patch_gen29),
    (30, _patch_gen30),
):
    _register_gen_patch(_ch, _fn)


def main():
    global IN_FILE, OUT_FILE, ACTIVE_BOOK, ACTIVE_LABEL, ACTIVE_CODE

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--book", default="genesis",
        help="slug del libro (genesis, exodo, levitico, ...)",
    )
    ap.add_argument(
        "--chapter", type=int, default=None, metavar="N",
        help="Solo parches del cap. N (B2–B8). Global passes siguen en todo el libro.",
    )
    ap.add_argument(
        "--mode",
        choices=["full", "hebrew", "lxx", "spanish"],
        default="full",
        help="Con --chapter: hebrew/lxx omiten polish; spanish incluye polish+chN_final.",
    )
    args = ap.parse_args()

    from gen_chapter_scope import set_scope, scope_label, in_scope

    set_scope(args.chapter, args.mode)

    # Resolver paths dinámicos por libro
    try:
        from book_config import resolve as _resolve
        cfg = _resolve(args.book)
        IN_FILE = cfg.final_json_path
        OUT_FILE = cfg.final_json_path
        ACTIVE_BOOK = cfg.slug
        ACTIVE_LABEL = cfg.label
        ACTIVE_CODE = cfg.catss_ref_label
        _idx_path = cfg.idx_es_path
        _oshb_morph_dir = cfg.oshb_dir
    except Exception as e:
        sys.stderr.write(f"  [error] no pude resolver el libro {args.book!r}: {e}\n")
        sys.exit(1)

    sys.stdout.write(f"\n== apply_corrections — {ACTIVE_LABEL} ({ACTIVE_BOOK}) ==\n")
    sys.stdout.write(f"   Alcance: {scope_label()}\n")
    sys.stdout.write(f"   IN  : {IN_FILE.name}\n")
    sys.stdout.write(f"   OSHB: {_oshb_morph_dir.name}\n\n")

    if not IN_FILE.exists():
        sys.stderr.write(
            f"  [error] no existe {IN_FILE}.  Ejecuta antes:\n"
            f"          python scripts/parse_catss.py --book {ACTIVE_BOOK}\n"
            f"          python scripts/merge_book.py --book {ACTIVE_BOOK}\n"
        )
        sys.exit(2)

    data = json.loads(IN_FILE.read_text(encoding="utf-8"))
    applied = skipped = 0

    # Cargar índice Strong→ES (SpaRV1909) para Global Pass 9
    _STRONG_ES_GEN: dict = {}
    try:
        _STRONG_ES_GEN = json.loads(_idx_path.read_text(encoding="utf-8"))
        sys.stdout.write(
            f"  Índice Strong-ES cargado: {len(_STRONG_ES_GEN)} entradas\n"
        )
    except FileNotFoundError:
        sys.stdout.write(
            f"  Aviso: {_idx_path.name} no disponible, Global Pass 9 omitido\n"
        )

    # ── Global Pass 0: sincronizar arrays de prefijos ───────────────────────────
    # El pipeline a veces deja `prefixes` con más elementos que `prefix_forms`,
    # causando que el frontend genere cards vacías por cada slot extra.
    # La fuente de verdad es `prefix_forms` (tiene la grafía hebrea real).
    # Se truncan / rellenan los arrays auxiliares para que TODOS tengan la
    # misma longitud que `prefix_forms`.
    pfx_synced = 0
    for verse in data["verses"]:
        for p in verse.get("pairs", []):
            for hw in p.get("he_words", []):
                n = len(hw.get("prefix_forms", []))
                for key, default in (
                    ("prefixes",       ""),
                    ("prefix_labels",  ""),
                    ("prefix_morphs",  ""),
                    ("prefix_es",      ""),
                    ("prefix_gr",      ""),
                    ("prefix_tier",    ""),
                ):
                    arr = hw.get(key, [])
                    if not isinstance(arr, list):
                        continue
                    if len(arr) > n:
                        hw[key] = arr[:n]
                        pfx_synced += 1
                    elif len(arr) < n:
                        hw[key] = arr + [default] * (n - len(arr))
    if pfx_synced:
        sys.stdout.write(f"  Prefijos sincronizados: {pfx_synced} arrays alineados\n")

    # ── Global Pass 1: eliminar he_words meta-CATSS ──────────────────────────────
    # Prefijos de notación CATSS que marcan tokens NO reales del TM:
    #   '='  → variante textual LXX            '{...?}' → texto incierto
    #   '<'  → referencia cruzada              '*'      → corrección textual
    #   '--' → marcador de alineación vacía    '.$'     → fragmento aparato
    for verse in data["verses"]:
        for p in verse.get("pairs", []):
            p["he_words"] = [
                hw for hw in p.get("he_words", [])
                if hw.get("raw", "") and not _is_catss_meta_raw(hw.get("raw", ""))
            ]

    # ── Correcciones manuales por verso (solo Génesis tiene tabla CORRECTIONS) ──
    if ACTIVE_BOOK == "genesis":
        for key, corrections in CORRECTIONS.items():
            cap_str, vrs_str = key.split(":")
            cap, vrs = int(cap_str), int(vrs_str)
            if args.chapter is not None and cap != args.chapter:
                continue
            verse = next(
                (v for v in data["verses"] if v["chapter"] == cap and v["verse"] == vrs),
                None,
            )
            if verse is None:
                sys.stderr.write(f"  [warn] No encontrado: {key}\n")
                skipped += 1
                continue

            n = apply_to_verse(verse, corrections)
            sys.stdout.write(f"  {ACTIVE_CODE} {key}: {n}/{len(corrections)} elementos corregidos\n")
            applied += 1

            if key == "1:11":
                _patch_gen111(verse)

            if key == "1:12":
                _patch_gen112(verse)

        if in_scope(1):
            # Parche puntual Gen 1:11 por raw (segunda pasada de seguridad)
            v111 = next((v for v in data["verses"] if v.get("chapter") == 1 and v.get("verse") == 11), None)
            if v111:
                _patch_gen111(v111)
                sys.stdout.write("  Gen 1:11: parche por raw aplicado\n")

            # Parche puntual Gen 1:16 por raw
            v116 = next((v for v in data["verses"] if v.get("chapter") == 1 and v.get("verse") == 16), None)
            if v116:
                _patch_gen116(v116)
                sys.stdout.write("  Gen 1:16: parche por raw aplicado\n")

            # Parche puntual Gen 1:26 — B/CLM/NW y K/DMWT/NW
            v126 = next((v for v in data["verses"] if v.get("chapter") == 1 and v.get("verse") == 26), None)
            if v126:
                _patch_gen126(v126)
                sys.stdout.write("  Gen 1:26: parche B/CLM/NW + K/DMWT/NW aplicado\n")

            # Parche puntual Gen 1:27 — punto flotante en )T/M
            v127 = next((v for v in data["verses"] if v.get("chapter") == 1 and v.get("verse") == 27), None)
            if v127:
                _patch_gen127(v127)
                sys.stdout.write("  Gen 1:27: parche )T/M punto flotante aplicado\n")

            # Parche puntual Gen 1:29 — נָתַתִּי + לָכֶם y participios זֹרֵעַ
            v129 = next((v for v in data["verses"] if v.get("chapter") == 1 and v.get("verse") == 29), None)
            if v129:
                _patch_gen129(v129)
                sys.stdout.write("  Gen 1:29: parche NTTY/L/KM + ZR( aplicado\n")

        _gen_apply_chapter_patches(data)

        if in_scope(1):
            # Parche puntual Gen 1:30 — desplazamientos masivos es/gr por sangrado
            v130 = next((v for v in data["verses"] if v.get("chapter") == 1 and v.get("verse") == 30), None)
            if v130:
                _patch_gen130(v130)
                sys.stdout.write("  Gen 1:30: parche masivo de alineamiento aplicado\n")
    else:
        sys.stdout.write(
            f"  [info] No hay tabla CORRECTIONS manuales registrada para {ACTIVE_LABEL}.\n"
            f"         Se aplicarán solo los Global Passes 0-14 (universales).\n"
        )

    # ── Global Pass 2: reestructurar MYN+sufijo → stem מִין + prs_suffix ────────
    # Cubre todos los versículos con לְמִינוֹ, לְמִינֵהוּ, לְמִינָהּ, לְמִינֵהֶם, etc.
    # Para 1:11 y 1:12 ya parchados, la operación es idempotente.
    myn_fixed = 0
    for verse in data["verses"]:
        for p in verse.get("pairs", []):
            for hw in p.get("he_words", []):
                old_es = hw.get("es", "")
                _apply_myn_suffix_rule(hw)
                if hw.get("es") == "especie" and old_es != "especie":
                    myn_fixed += 1
    if myn_fixed:
        sys.stdout.write(f"  MYN+sufijo: {myn_fixed} tokens reestructurados globalmente\n")

    # ── Global Pass 3: MZRY( (HIF PTCA) → "que produce"; ZR( (QAL PTCA) → "que da" ─
    mzry_fixed = 0
    zr_ptca_fixed = 0
    for verse in data["verses"]:
        for p in verse.get("pairs", []):
            for hw in p.get("he_words", []):
                raw = hw.get("raw", "")
                morph = hw.get("he_morph", "") or ""
                if "MZRY(" in raw and "PTCA" in morph:
                    if hw.get("es") != "que produce":
                        hw["es"] = "que produce"
                        mzry_fixed += 1
                elif raw == "ZR(" and "PTCA" in morph and hw.get("es") in ("da", ""):
                    if hw.get("es_source") not in ("manual", "patch"):
                        hw["es"] = "que da"
                        zr_ptca_fixed += 1
    if mzry_fixed:
        sys.stdout.write(f"  MZRY( PTCA: {mzry_fixed} tokens corregidos globalmente\n")
    if zr_ptca_fixed:
        sys.stdout.write(f"  ZR( PTCA: {zr_ptca_fixed} tokens → 'que da'\n")

    # ── Global Pass 5: marcador de objeto directo אֶת — sin glosa española ──────
    # PART.OBJ.DIR no tiene equivalente en español (es marcador gramatical puro).
    # Se asegura es="" tanto en tokens autónomos como en prefijos PART.OBJ.DIR.
    # EXCEPCIÓN: tokens compuestos )T+sufijo PRS (raw contiene '/' o morph
    # comienza con "PART.OBJ.DIR+") se preservan: son manejados por el
    # Global Pass 11, que les asigna la glosa pronominal canónica (lo, los, me…).
    pod_standalone = 0
    pod_prefix = 0
    pod_compound_preserved = 0
    for verse in data["verses"]:
        for p in verse.get("pairs", []):
            for hw in p.get("he_words", []):
                morph = hw.get("he_morph", "")
                raw   = hw.get("raw", "")
                if morph == "PART.OBJ.DIR" or morph.startswith("PART.OBJ.DIR+"):
                    is_compound = ("/" in raw) or morph.startswith("PART.OBJ.DIR+")
                    if is_compound:
                        pod_compound_preserved += 1
                    else:
                        if hw.get("es", ""):
                            hw["es"] = ""
                            pod_standalone += 1
                prefix_morphs = hw.get("prefix_morphs", [])
                prefix_es = hw.get("prefix_es", [])
                for i, pm in enumerate(prefix_morphs):
                    if pm == "PART.OBJ.DIR" and i < len(prefix_es):
                        if prefix_es[i]:
                            prefix_es[i] = ""
                            pod_prefix += 1
    if pod_standalone or pod_prefix or pod_compound_preserved:
        sys.stdout.write(
            f"  PART.OBJ.DIR glosas: {pod_standalone} tokens autónomos + "
            f"{pod_prefix} prefijos vaciados "
            f"({pod_compound_preserved} compuestos )T+sufijo preservados)\n"
        )

    # ── Global Pass 6: rellenar prefix_es vacíos en prefijos ART ────────────────
    # Cuando un prefijo ה tiene prefix_morph='ART' pero prefix_es='', inferir
    # el artículo español desde el artículo griego (prefix_gr) del mismo slot.
    _GR_ART_ES = {
        "ὁ": "el", "ἡ": "la", "τό": "el", "τὸ": "el",
        "τοῦ": "del", "τῆς": "de la",
        "τῷ": "al", "τῇ": "a la",
        "τόν": "el", "τὸν": "el", "τήν": "la", "τὴν": "la",
        "οἱ": "los", "αἱ": "las",
        "τοὺς": "los", "τοῖς": "los", "τάς": "las", "τᾶς": "las",
        "τῶν": "de los",
    }
    art_pfx_fixed = 0
    for verse in data["verses"]:
        for p in verse.get("pairs", []):
            for hw in p.get("he_words", []):
                pfx_morphs = hw.get("prefix_morphs", [])
                pfx_es     = hw.get("prefix_es", [])
                pfx_gr     = hw.get("prefix_gr", [])
                for i, pm in enumerate(pfx_morphs):
                    if pm == "ART" and i < len(pfx_es) and not (pfx_es[i] or "").strip():
                        gr_art = pfx_gr[i].strip() if i < len(pfx_gr) else ""
                        es_art = _GR_ART_ES.get(gr_art, "")
                        if es_art:
                            pfx_es[i] = es_art
                            art_pfx_fixed += 1
                        # Fallback: inferir desde morfología del stem hebreo
                        if not pfx_es[i]:
                            stem_morph = hw.get("he_morph", "")
                            if ".PL" in stem_morph:
                                if "F." in stem_morph or ".F." in stem_morph:
                                    es_art = "las"
                                else:
                                    es_art = "los"
                            else:  # singular (o BOTH)
                                if "F." in stem_morph or ".F." in stem_morph:
                                    es_art = "la"
                                else:
                                    es_art = "el"
                            pfx_es[i] = es_art
                            art_pfx_fixed += 1
    if art_pfx_fixed:
        sys.stdout.write(f"  ART prefix_es: {art_pfx_fixed} artículos completados globalmente\n")

    # ── Global Pass 6c: ART + término — el/la/los/las (no al/del/a la de la LXX) ─
    # El hebreo ה es artículo definido; la LXX a veces arrastra caso (τῇ→«a la»,
    # τοῦ→«del») y rompe la concordancia («a la séptimo»).  Solo pm=='ART' puro.
    art_concord_fixed = 0
    for verse in data["verses"]:
        for p in verse.get("pairs", []):
            for hw in p.get("he_words", []):
                if hw.get("es_source") in ("manual", "patch"):
                    continue
                pfx_morphs = hw.get("prefix_morphs", [])
                pfx_es = hw.get("prefix_es", [])
                morph = hw.get("he_morph", "") or ""
                for i, pm in enumerate(pfx_morphs):
                    if pm != "ART":
                        continue
                    target = _article_es_from_morph(morph)
                    cur = (pfx_es[i] if i < len(pfx_es) else "").strip()
                    if cur != target:
                        while len(pfx_es) <= i:
                            pfx_es.append("")
                        pfx_es[i] = target
                        hw["prefix_es"] = pfx_es
                        art_concord_fixed += 1
    if art_concord_fixed:
        sys.stdout.write(
            f"  ART concordancia (6c): {art_concord_fixed} artículos alineados al hebreo\n"
        )

    # ── Global Pass 6b: prefijos CONJ vacíos en griego → καὶ ────────────────────
    # Las conjunciones hebreas וְ / וּ / וַ casi siempre se traducen como καὶ.
    # Algunos tokens del pipeline tienen prefix_gr='' para esa CONJ.
    conj_pfx_fixed = 0
    for verse in data["verses"]:
        for p in verse.get("pairs", []):
            for hw in p.get("he_words", []):
                pfx_morphs = hw.get("prefix_morphs", [])
                pfx_gr     = hw.get("prefix_gr", [])
                pfx_forms  = hw.get("prefix_forms", [])
                for i, pm in enumerate(pfx_morphs):
                    if pm == "CONJ" and i < len(pfx_gr) and not pfx_gr[i]:
                        pf = pfx_forms[i] if i < len(pfx_forms) else ""
                        # Solo si el prefijo es realmente waw (וְ/וּ/וַ)
                        if pf and pf[0] in ("\u05d5",):  # waw consonante
                            pfx_gr[i] = "καὶ"
                            conj_pfx_fixed += 1
    if conj_pfx_fixed:
        sys.stdout.write(f"  CONJ prefix_gr: {conj_pfx_fixed} waw → καὶ\n")

    # ── Global Pass 7: W/YHY WAYYIQT sin glosa → "fue" ──────────────────────────
    # El fórmula "hubo tarde / hubo mañana" repite W/YHY en el mismo versículo;
    # el segundo token pierde la glosa en el pipeline secuencial.
    wyhy_fixed = 0
    for verse in data["verses"]:
        for p in verse.get("pairs", []):
            for hw in p.get("he_words", []):
                if hw.get("raw", "") == "W/YHY" and not hw.get("es", ""):
                    morph = hw.get("he_morph", "")
                    if "WAYYIQT" in morph or "JUSS" in morph:
                        hw["es"] = "fue"
                        wyhy_fixed += 1
                # prefijo וַ vacío en W/YHY
                if hw.get("raw", "") == "W/YHY":
                    pfx_es = hw.get("prefix_es", [])
                    if pfx_es and not pfx_es[0]:
                        hw["prefix_es"][0] = "y"
    if wyhy_fixed:
        sys.stdout.write(f"  W/YHY sin glosa: {wyhy_fixed} tokens completados globalmente\n")

    # ── Global Pass 8: eliminar tokens fantasma con artefactos CATSS ─────────────
    # Elimina he_words donde:
    #   - he_form está vacío, es '·' o '.' (no hay forma hebrea real)
    #   - Y el raw empieza con =, <, {, -- (notación de artefactos CATSS)
    #   - O el raw está completamente vacío
    # Complemento al Pass 1 (que filtra '='); cubre {…?...}, <…>, -- y cadenas vacías.
    _CATSS_PREFIXES = ("=", "<", "{", "--")
    phantom_removed = 0
    for verse in data["verses"]:
        for p in verse.get("pairs", []):
            before = len(p.get("he_words", []))
            p["he_words"] = [
                hw for hw in p.get("he_words", [])
                if not (
                    (hw.get("he_form", "") in ("", "·", ".")
                     and (not hw.get("raw", "")
                          or hw.get("raw", "").startswith(_CATSS_PREFIXES)))
                )
            ]
            phantom_removed += before - len(p["he_words"])
    if phantom_removed:
        sys.stdout.write(
            f"  Global Pass 8: {phantom_removed} tokens fantasma eliminados\n"
        )

    # ── Global Pass 9: corregir MISALIGN_ES usando índice Strong de SpaRV1909 ──
    # Solo corrige tokens donde el `es` actual es claramente una palabra
    # estructural (artículo / preposición / pronombre / conjunción) mientras la
    # morfología indica contenido (sustantivo/verbo/adjetivo/numeral/adverbio).
    # También admite el caso donde el `es` actual es la traducción esperada de
    # OTRO Strong presente en el mismo verso (señal de desplazamiento).
    # NO toca tokens con es_source ∈ {"manual","patch"}, ni prefijos, ni prs_suffix.
    if _STRONG_ES_GEN:
        # Cache de variantes por Strong para no recomputar
        _var_cache: dict = {}

        def _get_variants(strong: str):
            if strong not in _var_cache:
                _var_cache[strong] = _strong_variants(
                    strong, _STRONG_ES_GEN, top_k=5
                )
            return _var_cache[strong]

        misalign_fixed = 0
        misalign_skipped_safe = 0
        misalign_skipped_manual = 0
        misalign_skipped_uncertain = 0
        misalign_skipped_no_strong = 0
        misalign_skipped_rare = 0
        by_strong = Counter()
        by_verse = Counter()
        examples_changed = []
        examples_skipped = []
        suspicious = []

        for verse in data["verses"]:
            cap = verse.get("chapter", 0)
            vrs = verse.get("verse", 0)
            ref = f"{cap}:{vrs}"

            for p in verse.get("pairs", []):
                for hw in p.get("he_words", []):
                    # 1. Tiene Strong?
                    strong_raw = hw.get("strongs", "") or ""
                    strong = _norm_strong(strong_raw)
                    if not strong:
                        misalign_skipped_no_strong += 1
                        continue
                    # 2. El Strong existe en el índice con ≥3 ocurrencias totales
                    variants, sorted_words, phrases_norm, total_count = \
                        _get_variants(strong)
                    if total_count < 3 or not sorted_words:
                        misalign_skipped_rare += 1
                        continue
                    # 3. es_source no debe ser manual / patch (no pisar parches)
                    src = (hw.get("es_source", "") or "").lower()
                    if src in ("manual", "patch", "ph4:spar v1909",
                               "ph4:sparv1909"):
                        misalign_skipped_manual += 1
                        continue
                    # 4. ¿Discrepancia clara?  (cur_norm no debe ser sinónimo)
                    cur_es = hw.get("es", "") or ""
                    cur_norm = _norm_es(cur_es)
                    if not cur_norm:
                        # Token sin glosa → categoría MISSING_ES (paso 3), no aquí
                        continue
                    # Coincidencia como frase completa
                    if cur_norm in phrases_norm:
                        misalign_skipped_safe += 1
                        continue
                    # Coincidencia como palabra de contenido (solo si cur es
                    # una sola palabra; multi-palabra ya cubierto arriba)
                    if " " not in cur_norm and cur_norm in variants:
                        misalign_skipped_safe += 1
                        if len(examples_skipped) < 30:
                            examples_skipped.append({
                                "ref": ref,
                                "raw": hw.get("raw", ""),
                                "es":  cur_es,
                                "strong": strong,
                                "reason": "sinónimo (variante de Strong)"
                            })
                        continue
                    # 5. Desplazamiento estructural — solo condición (a):
                    #    el `es` actual es claramente una palabra estructural
                    #    (artículo / preposición / conjunción / pronombre átono)
                    #    Y la morfología hebrea indica contenido (SUBS / VERBO / ADJ
                    #    / NUM / ADV / NPROP).
                    #
                    # La condición (b) (es actual es traducción esperada de OTRO
                    # Strong del verso) se desactivó porque encadena errores
                    # cuando los datos tienen `raw`/`he_form`/`strongs`/`he_morph`
                    # mutuamente inconsistentes (ej. Gen 1:12 donde raw=(&H pero
                    # he_form=עֵץ).  Abstenerse cuando los datos no son confiables.
                    morph = (hw.get("he_morph", "") or "").upper()
                    is_content = _is_content_morph(morph)

                    # Comparar contra _ES_STRUCTURAL usando lowercase SIN quitar
                    # tildes — así "bajó" (verbo) NO se confunde con "bajo"
                    # (preposición); "dió" no se confunde con "dio", etc.
                    cur_es_lower = (cur_es or "").lower().strip()
                    cond_a = (
                        " " not in cur_es_lower
                        and cur_es_lower in _ES_STRUCTURAL
                        and is_content
                    )

                    if not cond_a:
                        misalign_skipped_uncertain += 1
                        continue

                    # Sanity-check adicional: si el raw/he_form/Strong no son
                    # coherentes, podríamos estar corrigiendo basura.  Como
                    # señal de baja confianza, exigimos que el Strong sugiera
                    # un single-word top con suficiente peso relativo (>= 30%
                    # del total).  Si no, abstener.
                    top_word, top_cnt = sorted_words[0]
                    if total_count > 0 and (top_cnt / total_count) < 0.20:
                        misalign_skipped_uncertain += 1
                        continue

                    if not top_word or top_word == cur_norm:
                        misalign_skipped_uncertain += 1
                        continue

                    # Aplicar el cambio
                    old_es = hw["es"]
                    hw["es"] = top_word
                    hw["es_source"] = "ph4:SpaRV1909"
                    hw["_es_original"] = old_es
                    misalign_fixed += 1
                    by_strong[strong] += 1
                    by_verse[ref] += 1

                    if len(examples_changed) < 30:
                        examples_changed.append({
                            "ref": ref,
                            "raw": hw.get("raw", ""),
                            "old_es": old_es,
                            "new_es": top_word,
                            "strong": strong,
                            "morph": morph,
                        })

                    # Detectar cambios "sospechosos" (corto→largo o ortografía
                    # muy distinta) para revisión manual.
                    if len(_norm_es(old_es)) <= 3 and len(top_word) >= 6:
                        suspicious.append({
                            "ref": ref,
                            "raw": hw.get("raw", ""),
                            "old_es": old_es,
                            "new_es": top_word,
                            "strong": strong,
                        })

        sys.stdout.write("\n  ── Global Pass 9: MISALIGN_ES (SpaRV1909) ──\n")
        sys.stdout.write(f"    Corregidos                     : {misalign_fixed}\n")
        sys.stdout.write(f"    Saltados (sinónimo válido)     : {misalign_skipped_safe}\n")
        sys.stdout.write(f"    Saltados (es_source manual)    : {misalign_skipped_manual}\n")
        sys.stdout.write(f"    Saltados (incierto / no aplica): {misalign_skipped_uncertain}\n")
        sys.stdout.write(f"    Saltados (sin Strong)          : {misalign_skipped_no_strong}\n")
        sys.stdout.write(f"    Saltados (Strong raro <3 occ)  : {misalign_skipped_rare}\n")

        if by_strong:
            sys.stdout.write("\n    Top 10 Strongs con más correcciones:\n")
            for s, c in by_strong.most_common(10):
                top = _get_variants(s)[1]
                top_word = top[0][0] if top else "?"
                sys.stdout.write(f"      {s} → '{top_word}': {c}\n")

        if by_verse:
            sys.stdout.write("\n    Top 10 versos con más correcciones:\n")
            for v, c in by_verse.most_common(10):
                sys.stdout.write(f"      {ACTIVE_CODE} {v}: {c}\n")

        if examples_changed:
            sys.stdout.write("\n    Ejemplos de 5 correcciones aplicadas:\n")
            for ex in examples_changed[:5]:
                sys.stdout.write(
                    f"      {ACTIVE_CODE} {ex['ref']:>6} raw={ex['raw']:<14} "
                    f"{ex['strong']:<6} "
                    f"'{ex['old_es']}' → '{ex['new_es']}' [{ex['morph']}]\n"
                )

        if examples_skipped:
            sys.stdout.write("\n    Ejemplos de 5 saltados por sinónimo:\n")
            for ex in examples_skipped[:5]:
                sys.stdout.write(
                    f"      {ACTIVE_CODE} {ex['ref']:>6} raw={ex['raw']:<14} "
                    f"{ex['strong']:<6} es='{ex['es']}' ({ex['reason']})\n"
                )

        if suspicious:
            sys.stdout.write(
                f"\n    Cambios sospechosos (corto→largo) — {len(suspicious)} total, "
                f"primeros 10:\n"
            )
            for ex in suspicious[:10]:
                sys.stdout.write(
                    f"      {ACTIVE_CODE} {ex['ref']:>6} raw={ex['raw']:<14} "
                    f"{ex['strong']:<6} '{ex['old_es']}' → '{ex['new_es']}'\n"
                )

        # ── Global Pass 10: completar MISSING_ES desde SpaRV1909 ─────────────
        # Para tokens con `es` vacío ('', '?', '—') y morfología de contenido,
        # asignar la traducción top-1 del Strong si el índice tiene ≥3
        # ocurrencias totales y el top-1 representa ≥25% del peso de los top-5.
        # Reutiliza el cache `_var_cache` y `_get_variants` definidos en Pass 9.
        _PASS10_SKIP_SOURCES = {
            "manual", "patch", "ph4:sparv1909", "auto:otam_rule",
        }
        _PASS10_CONTENT_TAGS = (
            "SUBS", "VERBO", "ADJ", "NUM", "ADV", "NPROP",
            "INTJ", "REL", "PREP",
        )
        missing_es_filled = 0
        missing_es_skipped_no_strong = 0
        missing_es_skipped_low_confidence = 0
        missing_es_skipped_already_filled = 0
        m10_by_strong = Counter()
        m10_examples = []

        for verse in data["verses"]:
            cap = verse.get("chapter", 0)
            vrs = verse.get("verse", 0)
            ref = f"{cap}:{vrs}"
            for p in verse.get("pairs", []):
                for hw in p.get("he_words", []):
                    cur_es = (hw.get("es", "") or "").strip()
                    # 1. es realmente vacío
                    if cur_es not in ("", "?", "—"):
                        missing_es_skipped_already_filled += 1
                        continue
                    # 2. es_source no protegido
                    src = (hw.get("es_source", "") or "").strip().lower()
                    if src in _PASS10_SKIP_SOURCES:
                        missing_es_skipped_already_filled += 1
                        continue
                    # 3. Strong existe y tiene ≥3 ocurrencias en el índice
                    strong_raw = hw.get("strongs", "") or ""
                    strong = _norm_strong(strong_raw)
                    if not strong:
                        missing_es_skipped_no_strong += 1
                        continue
                    variants, sorted_words, phrases_norm, total_count = \
                        _get_variants(strong)
                    if total_count < 3 or not sorted_words:
                        missing_es_skipped_no_strong += 1
                        continue
                    # 4. Top-1 ≥ 25% del peso de los top-5
                    top_word, top_cnt = sorted_words[0]
                    top5_sum = sum(c for _, c in sorted_words[:5])
                    if top5_sum == 0 or (top_cnt / top5_sum) < 0.25:
                        missing_es_skipped_low_confidence += 1
                        continue
                    # 5. Morfología de contenido (contiene cualquiera de las
                    #    etiquetas: SUBS/VERBO/ADJ/NUM/ADV/NPROP/INTJ/REL/PREP)
                    morph = (hw.get("he_morph", "") or "").upper()
                    if not any(tag in morph for tag in _PASS10_CONTENT_TAGS):
                        missing_es_skipped_low_confidence += 1
                        continue
                    # Aplicar
                    hw["es"] = top_word
                    hw["es_source"] = "ph4:SpaRV1909"
                    missing_es_filled += 1
                    m10_by_strong[strong] += 1
                    if len(m10_examples) < 15:
                        m10_examples.append({
                            "ref": ref,
                            "raw": hw.get("raw", ""),
                            "new_es": top_word,
                            "strong": strong,
                            "morph": morph,
                        })

        sys.stdout.write("\n  ── Global Pass 10: MISSING_ES (SpaRV1909) ──\n")
        sys.stdout.write(f"    Completados                    : {missing_es_filled}\n")
        sys.stdout.write(f"    Saltados (sin Strong o raro)   : {missing_es_skipped_no_strong}\n")
        sys.stdout.write(f"    Saltados (baja confianza)      : {missing_es_skipped_low_confidence}\n")
        sys.stdout.write(f"    Saltados (ya con es / source)  : {missing_es_skipped_already_filled}\n")

        if m10_by_strong:
            sys.stdout.write("\n    Top 10 Strongs completados:\n")
            for s, c in m10_by_strong.most_common(10):
                top = _get_variants(s)[1]
                top_word = top[0][0] if top else "?"
                sys.stdout.write(f"      {s} → '{top_word}': {c}\n")

        if m10_examples:
            sys.stdout.write("\n    Ejemplos de 10 completados:\n")
            for ex in m10_examples[:10]:
                sys.stdout.write(
                    f"      {ACTIVE_CODE} {ex['ref']:>6} raw={ex['raw']:<14} "
                    f"{ex['strong']:<6} → '{ex['new_es']}' [{ex['morph']}]\n"
                )

    # ── Global Pass 11: marcador objeto directo )T + sufijo PRS ──────────────
    # Regla determinística: tokens cuyo `raw` está en la tabla canónica reciben
    # he_form, he_morph compuesta (PART.OBJ.DIR+PRS.*) y glosa pronominal
    # ('me', 'te', 'lo', 'la', 'nos', 'os', 'los', 'las') desde la LXX.
    # Se ejecuta DESPUÉS del Pass 10 para que la glosa canónica gane sobre
    # cualquier asignación previa por Strong.
    _OTAM_TABLE = {
        # raw  → (he_form,   he_morph_suf,        es)
        ")T/Y":  ("אֹתִי",   "PRS.P1.COMMON.SG",  "me"),
        ")T/Y!": ("אֹתִי",   "PRS.P1.COMMON.SG",  "me"),
        ")T/K":  ("אֹתְךָ",  "PRS.P2.M.SG",       "te"),
        ")T/KH": ("אֹתְךָ",  "PRS.P2.M.SG",       "te"),
        ")T/KM": ("אֶתְכֶם", "PRS.P2.M.PL",       "os"),
        ")T/KN": ("אֶתְכֶן", "PRS.P2.F.PL",       "os"),
        ")T/W":  ("אֹתוֹ",   "PRS.P3.M.SG",       "lo"),
        ")T/H":  ("אֹתָהּ",  "PRS.P3.F.SG",       "la"),
        ")T/NW": ("אֹתָנוּ", "PRS.P1.COMMON.PL",  "nos"),
        ")T/M":  ("אֹתָם",   "PRS.P3.M.PL",       "los"),
        ")T/HM": ("אֹתָם",   "PRS.P3.M.PL",       "los"),
        ")T/HN": ("אֶתְהֶן", "PRS.P3.F.PL",       "las"),
    }

    otam_fixed = 0
    otam_already_correct = 0
    otam_skipped_manual = 0
    otam_by_suffix = Counter()
    otam_examples = []

    for verse in data["verses"]:
        cap = verse.get("chapter", 0)
        vrs = verse.get("verse", 0)
        ref = f"{cap}:{vrs}"
        for p in verse.get("pairs", []):
            for hw in p.get("he_words", []):
                raw = hw.get("raw", "")
                if raw not in _OTAM_TABLE:
                    continue
                # 1. Preservar parches manuales
                src = (hw.get("es_source", "") or "").strip().lower()
                if src in ("manual", "patch", "glosa_personal", "glosa_global"):
                    otam_skipped_manual += 1
                    continue

                he_form_new, prs_morph_suf, es_canon = _OTAM_TABLE[raw]
                new_morph = f"PART.OBJ.DIR+{prs_morph_suf}"

                old_es    = hw.get("es", "")
                old_form  = hw.get("he_form", "")
                old_morph = hw.get("he_morph", "")

                # 2. Restaurar he_form a forma canónica SIEMPRE
                hw["he_form"] = he_form_new
                # 3. Asignar morfología compuesta
                hw["he_morph"] = new_morph
                # 4. Asignar es desde la tabla salvo que ya haya un valor
                #    NO estructural (caso muy raro: glosa contextual válida)
                cur_es_strip = (old_es or "").strip()
                cur_es_lower = cur_es_strip.lower()
                must_override = (
                    cur_es_strip in ("", "?", "—")
                    or cur_es_lower in _ES_STRUCTURAL
                    or cur_es_lower != es_canon.lower()
                )
                if must_override:
                    hw["es"] = es_canon
                # else: preservar glosa no estructural existente

                # 8. Limpiar prefijos sintéticos (todos forms/morphs vacíos)
                pfx_forms  = hw.get("prefix_forms", []) or []
                pfx_morphs = hw.get("prefix_morphs", []) or []
                if pfx_forms or pfx_morphs:
                    all_garbage = (
                        all(not (f or "").strip() for f in pfx_forms)
                        and all(not (m or "").strip() for m in pfx_morphs)
                    )
                    if all_garbage:
                        for lst in (
                            "prefixes", "prefix_forms", "prefix_morphs",
                            "prefix_es", "prefix_gr", "prefix_labels",
                            "prefix_tier", "prefix_unicode",
                        ):
                            if lst in hw:
                                hw[lst] = []

                # 9. Marcar fuente
                hw["es_source"] = "auto:otam_rule"
                # 10. Guardar original si hubo cambio en es
                if old_es != hw.get("es", "") and "_es_original" not in hw:
                    hw["_es_original"] = old_es

                # Métricas
                otam_by_suffix[raw] += 1
                if (
                    old_form == he_form_new
                    and old_morph == new_morph
                    and old_es == hw.get("es", "")
                ):
                    otam_already_correct += 1
                else:
                    otam_fixed += 1
                    if len(otam_examples) < 15:
                        otam_examples.append({
                            "ref": ref,
                            "raw": raw,
                            "old_form": old_form,
                            "old_es": old_es,
                            "new_es": hw.get("es", ""),
                            "new_morph": new_morph,
                        })

    sys.stdout.write("\n  ── Global Pass 11: )T + sufijo PRS (regla canónica) ──\n")
    sys.stdout.write(f"    Corregidos                     : {otam_fixed}\n")
    sys.stdout.write(f"    Ya correctos (sin cambios)     : {otam_already_correct}\n")
    sys.stdout.write(f"    Saltados (es_source manual)    : {otam_skipped_manual}\n")
    if otam_by_suffix:
        sys.stdout.write("\n    Distribución por sufijo:\n")
        for sfx, c in otam_by_suffix.most_common():
            es_val = _OTAM_TABLE[sfx][2]
            sys.stdout.write(f"      {sfx:<8} → '{es_val}': {c}\n")
    if otam_examples:
        sys.stdout.write("\n    Ejemplos de corrección:\n")
        for ex in otam_examples[:10]:
            sys.stdout.write(
                f"      {ACTIVE_CODE} {ex['ref']:>6} raw={ex['raw']:<8} "
                f"'{ex['old_es']}'→'{ex['new_es']}' [{ex['new_morph']}]\n"
            )

    # ── Global Pass 12: override determinístico de Strongs problemáticos ─────────
    # Tabla de Strongs cuya traducción correcta es inequívoca pero el índice
    # SpaRV1909 puede inducir falsos positivos por alineación ruidosa (p.ej.
    # H996 "entre" se confunde con "convenio" por la frase "pacto entre").
    # Esta tabla solo se aplica si la morfología coincide con el rol esperado.
    _STRONG_OVERRIDE = {
        # Strong : (es_correcto, morph_required_contains)
        # IMPORTANTE: solo Strongs invariables (preposiciones cortas).
        # NO incluir verbos: cambian su forma con la conjugación (futuro,
        # participio, imperativo, etc.) y un override fijo corrompería los datos.
        "H996":  ("entre",   "PREP"),    # בֵּין preposición — falso positivo SpaRV1909 → "convenio"
        "H8318": ("reptil",  "SUBS"),    # שֶׁרֶץ — criatura que se arrastra
    }
    override_fixed = 0
    override_skipped_manual = 0
    override_examples = []
    for verse in data["verses"]:
        ref = f"{verse.get('chapter','')}:{verse.get('verse','')}"
        for p in verse.get("pairs", []):
            for hw in p.get("he_words", []):
                s_raw = hw.get("strongs", "")
                if not s_raw:
                    continue
                s_norm = _norm_strong(s_raw) if "_norm_strong" in dir() else s_raw.upper().lstrip().rstrip("ABab").replace("H0", "H").replace("G0", "G")
                # Normalización simple sin función externa
                s_key = s_raw.strip().upper()
                if s_key.startswith("H") or s_key.startswith("G"):
                    prefix = s_key[0]
                    num = s_key[1:].rstrip("ABab").lstrip("0") or "0"
                    s_key = f"{prefix}{num}"
                ov = _STRONG_OVERRIDE.get(s_key)
                if not ov:
                    continue
                target_es, required_morph = ov
                # Saltar si el usuario marcó manualmente
                if hw.get("es_source") in ("manual", "patch"):
                    override_skipped_manual += 1
                    continue
                morph = hw.get("he_morph", "")
                if required_morph not in morph:
                    continue
                cur_es = hw.get("es", "")
                if cur_es == target_es:
                    continue
                old_es = cur_es
                hw["_es_original"] = hw.get("_es_original", "") or old_es
                hw["es"] = target_es
                hw["es_source"] = "override:strong"
                override_fixed += 1
                if len(override_examples) < 10:
                    override_examples.append({
                        "ref": ref, "raw": hw.get("raw", ""),
                        "strong": s_key, "old_es": old_es, "new_es": target_es,
                    })

    if override_fixed or override_skipped_manual:
        sys.stdout.write("\n  ── Global Pass 12: override Strong determinístico ──\n")
        sys.stdout.write(f"    Corregidos                  : {override_fixed}\n")
        sys.stdout.write(f"    Saltados (es_source manual) : {override_skipped_manual}\n")
        if override_examples:
            sys.stdout.write("    Ejemplos:\n")
            for ex in override_examples[:5]:
                sys.stdout.write(
                    f"      {ACTIVE_CODE} {ex['ref']:>6} raw={ex['raw']:<10} "
                    f"{ex['strong']:<6} '{ex['old_es']}'→'{ex['new_es']}'\n"
                )

    # ── Global Pass 12b: רֹמֶשֶׂת / remesh — glosas fragmentadas (sa, mueva…) ───
    romes_fixed = 0
    _ROMES_BAD = frozenset({"sa", "mueva", "arrastra", ""})
    _ROMES_FEM_OLD = frozenset({"reptil que se arrastra", "que se arrastra", "que se arrastran"})
    for verse in data["verses"]:
        ref = f"{verse.get('chapter', '')}:{verse.get('verse', '')}"
        for p in verse.get("pairs", []):
            for hw in p.get("he_words", []):
                if hw.get("es_source") in ("manual", "patch"):
                    continue
                raw = hw.get("raw", "")
                morph = hw.get("he_morph", "") or ""
                strong = (hw.get("strongs") or "").strip().upper()
                if strong.startswith("H"):
                    strong = "H" + strong[1:].lstrip("0")
                es = (hw.get("es") or "").strip()
                pfx_es = hw.get("prefix_es") or []
                pfx0 = (pfx_es[0] or "").strip() if pfx_es else ""

                is_fem_ptca = (
                    raw == "H/RM&T"
                    or (strong == "H7430" and "PTCA" in morph and "F." in morph)
                )
                is_masc_remes = raw in ("H/RM&", "W/RM&", "RM&") or strong == "H7431"

                if is_fem_ptca and (
                    es in _ROMES_BAD
                    or es in _ROMES_FEM_OLD
                    or pfx0 in ("que", "la", "")
                    or es != "que se arrastran"
                    or pfx0 != "las"
                ):
                    if pfx_es:
                        hw["prefix_es"][0] = "las"
                    hw["es"] = "que se arrastran"
                    if not (hw.get("gr_word") or "").strip() or hw.get("gr_word") == "---":
                        hw["gr_word"] = _san_gr("ἑρπετά")
                    hw["es_source"] = "override:romeset"
                    romes_fixed += 1
                    continue

                if is_masc_remes and "PTCA" in morph and es in _ROMES_BAD:
                    if pfx_es and pfx_es[0] == "que":
                        hw["prefix_es"][0] = ""
                    hw["es"] = "reptil que se arrastra"
                    hw["es_source"] = "override:romeset"
                    romes_fixed += 1
                elif is_masc_remes and morph.startswith("SUBS") and es in ("arrastra", "serpientes", ""):
                    hw["es"] = "reptil"
                    hw["es_source"] = "override:romeset"
                    romes_fixed += 1

    if romes_fixed:
        sys.stdout.write("\n  ── Global Pass 12b: remesh / romeset ──\n")
        sys.stdout.write(f"    Corregidos                  : {romes_fixed}\n")

    # ── Global Pass 13: validación morfológica (Paso 4) — solo anotar ───────────
    # Compara he_morph con oshb-morph (angelos). NO sobrescribe he_morph.
    _scripts_dir = Path(__file__).resolve().parent
    if str(_scripts_dir) not in sys.path:
        sys.path.insert(0, str(_scripts_dir))
    try:
        from morph_validate_utils import (
            compare_morph,
            load_verse_morph_map,
            lookup_verse_morph,
        )
        _verse_morph_map = load_verse_morph_map(_oshb_morph_dir)
        _morph_exact = _morph_minor = _morph_conflict = _morph_no_ref = 0
        _morph_examples = []
        for verse in data["verses"]:
            ref = f"{verse.get('chapter', '')}:{verse.get('verse', '')}"
            for p in verse.get("pairs", []):
                for hw in p.get("he_words", []):
                    he_form = hw.get("he_form", "") or ""
                    he_morph = hw.get("he_morph", "") or ""
                    if not he_morph:
                        continue
                    hit = lookup_verse_morph(_verse_morph_map, ref, he_form)
                    if not hit:
                        _morph_no_ref += 1
                        continue
                    ref_morph, ref_src = hit
                    status = compare_morph(he_morph, ref_morph)
                    if status == "exact":
                        _morph_exact += 1
                        hw.pop("morph_audit", None)
                        hw.pop("morph_ref", None)
                        hw.pop("morph_ref_source", None)
                        continue
                    hw["morph_audit"] = status
                    hw["morph_ref"] = ref_morph
                    hw["morph_ref_source"] = ref_src
                    if status == "minor":
                        _morph_minor += 1
                    else:
                        _morph_conflict += 1
                    if len(_morph_examples) < 10:
                        _morph_examples.append({
                            "ref": ref, "raw": hw.get("raw", ""),
                            "ours": he_morph, "ref_m": ref_morph, "status": status,
                        })
        sys.stdout.write("\n  ── Global Pass 13: validación morfológica (Paso 4) ──\n")
        sys.stdout.write(f"    Coincidencia exacta (sin anotar) : {_morph_exact}\n")
        sys.stdout.write(f"    Anotados minor                   : {_morph_minor}\n")
        sys.stdout.write(f"    Anotados conflict                : {_morph_conflict}\n")
        sys.stdout.write(f"    Sin referencia en versículo      : {_morph_no_ref}\n")
        if _morph_examples:
            sys.stdout.write("    Ejemplos anotados:\n")
            for ex in _morph_examples[:6]:
                sys.stdout.write(
                    f"      {ACTIVE_CODE} {ex['ref']:>6} raw={ex['raw']:<10} "
                    f"[{ex['status']}] {ex['ours']:<22} ref={ex['ref_m']}\n"
                )
    except Exception as _morph_err:
        sys.stdout.write(
            f"\n  ── Global Pass 13: omitido ({_morph_err}) ──\n"
        )

    # ── Global Pass 14: unificación morfológica OSHB (Paso 5.5b) ───────────────
    # Sustituye códigos legacy CATSS y conflictos por oshb-morph alineado.
    # Respeta morph_source manual/patch y composiciones '+' coherentes.
    try:
        from paso5_5_apply_morph_global import (
            apply_conj_w_stem_pass,
            apply_morph_global_pass,
        )
        from morph_validate_utils import load_verse_morph_map

        _gp14_map = load_verse_morph_map(_oshb_morph_dir)
        _gp14 = apply_morph_global_pass(
            data,
            _gp14_map,
            apply=True,
            source_prefix="global_pass_14",
            collect_rows=False,
        )
        _gp14c = _gp14["counts"]
        sys.stdout.write(
            "\n  ── Global Pass 14: morfología OSHB (unificación global) ──\n"
        )
        sys.stdout.write(f"    Tokens actualizados          : {_gp14['applied']}\n")
        sys.stdout.write(f"    Legacy (alineación)          : {_gp14c.get('legacy', 0)}\n")
        sys.stdout.write(f"    Conflicto corregido          : {_gp14c.get('conflict', 0)}\n")
        sys.stdout.write(
            f"    Legacy lookup versículo       : {_gp14c.get('legacy_verse_lookup', 0)}\n"
        )
        sys.stdout.write(
            f"    Prefijo legacy               : {_gp14c.get('legacy_prefix', 0)}\n"
        )
        sys.stdout.write(
            f"    Fusión composición (+)       : {_gp14c.get('fused_compose', 0)}\n"
        )

        _gp14b = apply_conj_w_stem_pass(
            data,
            _gp14_map,
            apply=True,
            source_prefix="global_pass_14b",
            collect_rows=False,
        )
        _gp14bc = _gp14b["counts"]
        sys.stdout.write(
            "\n  ── Global Pass 14b: CONJ/W/C en stem (lookup OSHB) ──\n"
        )
        sys.stdout.write(f"    Candidatos                   : {_gp14b['candidates']}\n")
        sys.stdout.write(f"    Aplicados                    : {_gp14b['applied']}\n")
        sys.stdout.write(
            f"    Sin forma en OSHB            : {_gp14bc.get('skip_no_oshb_fold', 0)}\n"
        )
        sys.stdout.write(
            f"    OSHB no es CONJ              : {_gp14bc.get('skip_oshb_not_conj', 0)}\n"
        )
    except Exception as _gp14_err:
        sys.stdout.write(
            f"\n  ── Global Pass 14/14b: omitido ({_gp14_err}) ──\n"
        )

    # ── Global Pass 15: glosas personalizadas (registro del editor) ───────────
    try:
        from glosas_personales_utils import load_registry, apply_registry_to_interlineal

        _gp15_registry = load_registry()
        _gp15_hits = apply_registry_to_interlineal(data, ACTIVE_BOOK, _gp15_registry)
        if _gp15_hits or _gp15_registry.get("global") or _gp15_registry.get("contexto"):
            sys.stdout.write("\n  ── Global Pass 15: glosas personalizadas ──\n")
            sys.stdout.write(f"    Reglas globales en registro : {len(_gp15_registry.get('global', []))}\n")
            sys.stdout.write(f"    Reglas de contexto (libro)  : {sum(1 for r in _gp15_registry.get('contexto', []) if (r.get('match') or {}).get('book') == ACTIVE_BOOK)}\n")
            sys.stdout.write(f"    Tokens actualizados         : {_gp15_hits}\n")
    except Exception as _gp15_err:
        sys.stdout.write(f"\n  ── Global Pass 15: omitido ({_gp15_err}) ──\n")

    # Reaplicar solo parches estructurales tras glosas personales (Pass 15).
    if ACTIVE_BOOK == "genesis":
        sys.stdout.write("\n")
        _gen_apply_chapter_patches(
            data,
            respect_user_gloss=True,
            label="parches estructurales reaplicados (post-Pass 15)",
        )

    # ── Global Pass 16: glosas legibles — sin duplicar sufijos ni opciones / ───
    slash_fixed = prs_merged = prs_dropped = 0
    for verse in data["verses"]:
        for p in verse.get("pairs", []):
            for hw in p.get("he_words", []):
                if hw.get("es_source") in ("manual",):
                    continue
                es = (hw.get("es") or "").strip()
                if es in _SLASH_GLOSS_CANON:
                    hw["es"] = _SLASH_GLOSS_CANON[es]
                    slash_fixed += 1
                elif "/" in es and es.lower().startswith("para/a "):
                    hw["es"] = es.replace("para/a ", "para ", 1)
                    slash_fixed += 1
                if _merge_prs_reading_gloss(hw):
                    prs_merged += 1
                if _drop_redundant_prs_suffix(hw):
                    prs_dropped += 1
    if slash_fixed or prs_merged or prs_dropped:
        sys.stdout.write("\n  ── Global Pass 16: glosas legibles ──\n")
        sys.stdout.write(f"    Opciones / unificadas         : {slash_fixed}\n")
        sys.stdout.write(f"    Stem+sufijo fusionados        : {prs_merged}\n")
        sys.stdout.write(f"    Sufijos prs redundantes       : {prs_dropped}\n")

    # Sincronizar arrays de prefijos tras parches tardíos (prefix_es huérfanos).
    pfx_late = 0
    for verse in data["verses"]:
        for p in verse.get("pairs", []):
            for hw in p.get("he_words", []):
                n = len(hw.get("prefix_forms", []))
                for key, default in (
                    ("prefixes", ""),
                    ("prefix_labels", ""),
                    ("prefix_morphs", ""),
                    ("prefix_es", ""),
                    ("prefix_gr", ""),
                    ("prefix_tier", ""),
                ):
                    arr = hw.get(key, [])
                    if not isinstance(arr, list):
                        continue
                    if len(arr) != n:
                        hw[key] = (arr[:n] if len(arr) > n else arr + [default] * (n - len(arr)))
                        pfx_late += 1
    if pfx_late:
        sys.stdout.write(f"  Prefijos sincronizados (final): {pfx_late} arrays alineados\n")

    if ACTIVE_BOOK == "genesis":
        _gen_apply_chapter_patches(
            data,
            respect_user_gloss=True,
            label="parches PRS/sufijos reaplicados (post-Pass 16)",
            min_ch=4,
        )

        prs_late_merged = 0
        for verse in data["verses"]:
            for p in verse.get("pairs", []):
                for hw in p.get("he_words", []):
                    if hw.get("es_source") in ("manual",):
                        continue
                    if _merge_prs_reading_gloss(hw):
                        prs_late_merged += 1
        if prs_late_merged:
            sys.stdout.write(
                f"  Glosas stem+sufijo re-fusionadas (post-parches): {prs_late_merged}\n"
            )

        for _ch in range(9, 16):
            _gen_run_post_re(data, _ch)

        _gen_polish_chapter(data, 8, _polish_gen8_es_glosses, "prefijos/sufijos/art.")
        _gen_polish_chapter(data, 9, _polish_gen9_es_glosses, "prefijos/sufijos/art.")

        from gen_chapter_scope import skip_ch_final

        if not skip_ch_final() and in_scope(9):
            ch9_final = 0
            for v in data["verses"]:
                if v.get("chapter") == 9:
                    _gen9_reapply_oshb_splits(v, respect_user_gloss=True)
                    ch9_final += 1
            if ch9_final:
                sys.stdout.write(
                    f"  Gen cap. 9: splits OSHB finales ({ch9_final} versos, post-español)\n"
                )

        _gen_polish_chapter(data, 10, _polish_gen10_es_glosses, "prefijos/sufijos/art.")

        if not skip_ch_final() and in_scope(10):
            ch10_final = 0
            ch10_final_merged = 0
            for v in data["verses"]:
                if v.get("chapter") == 10:
                    _gen10_reapply_oshb_splits(v, respect_user_gloss=True)
                    _fix_gen10_oshb_align(v, respect_user_gloss=True)
                    _fix_gen10_es_glosses(v, respect_user_gloss=True)
                    for p in v.get("pairs", []):
                        for hw in p.get("he_words", []):
                            if _has_user_gloss(hw):
                                continue
                            if _merge_prs_reading_gloss(hw):
                                ch10_final_merged += 1
                            _drop_redundant_prs_suffix(hw)
                    _fix_gen10_lxx_align(v)
                    ch10_final += 1
            if ch10_final:
                sys.stdout.write(
                    f"  Gen cap. 10: splits OSHB finales ({ch10_final} versos, post-español)\n"
                )
            if ch10_final_merged:
                sys.stdout.write(
                    f"  Gen cap. 10: lecturas PRS re-fusionadas post-español: {ch10_final_merged}\n"
                )

        _gen_polish_chapter(data, 11, _polish_gen11_es_glosses, "prefijos/sufijos/art.")

        if not skip_ch_final() and in_scope(11):
            ch11_final = 0
            ch11_final_merged = 0
            for v in data["verses"]:
                if v.get("chapter") == 11:
                    _gen11_reapply_oshb_splits(v, respect_user_gloss=True)
                    _fix_gen11_oshb_align(v, respect_user_gloss=True)
                    _fix_gen11_es_glosses(v, respect_user_gloss=True)
                    for p in v.get("pairs", []):
                        for hw in p.get("he_words", []):
                            if _has_user_gloss(hw):
                                continue
                            if _merge_prs_reading_gloss(hw):
                                ch11_final_merged += 1
                            _drop_redundant_prs_suffix(hw)
                    _fix_gen11_lxx_align(v)
                    ch11_final += 1
            if ch11_final:
                sys.stdout.write(
                    f"  Gen cap. 11: splits OSHB finales ({ch11_final} versos, post-español)\n"
                )
            if ch11_final_merged:
                sys.stdout.write(
                    f"  Gen cap. 11: lecturas PRS re-fusionadas post-español: {ch11_final_merged}\n"
                )

        _gen_polish_chapter(data, 12, _polish_gen12_es_glosses, "prefijos/sufijos/art.")

        if not skip_ch_final() and in_scope(12):
            ch12_final = 0
            ch12_final_merged = 0
            for v in data["verses"]:
                if v.get("chapter") == 12:
                    _gen12_reapply_oshb_splits(v, respect_user_gloss=True)
                    _fix_gen12_oshb_align(v, respect_user_gloss=True)
                    _fix_gen12_es_glosses(v, respect_user_gloss=True)
                    for p in v.get("pairs", []):
                        for hw in p.get("he_words", []):
                            if _has_user_gloss(hw):
                                continue
                            if _merge_prs_reading_gloss(hw):
                                ch12_final_merged += 1
                            _drop_redundant_prs_suffix(hw)
                    _gen12_finalize_prep_prs(v)
                    if v.get("verse") in (17, 18, 20):
                        _fix_gen12_oshb_align(v, respect_user_gloss=True)
                    _fix_gen12_v3_participle_readings(v, respect_user_gloss=True)
                    _fix_gen12_lxx_align(v)
                    normalize_verse_maqaf(v)
                    sanitize_verse_he_forms(v)
                    ch12_final += 1
            if ch12_final:
                sys.stdout.write(
                    f"  Gen cap. 12: splits OSHB finales ({ch12_final} versos, post-español)\n"
                )
            if ch12_final_merged:
                sys.stdout.write(
                    f"  Gen cap. 12: lecturas PRS re-fusionadas post-español: {ch12_final_merged}\n"
                )

        _gen_polish_chapter(data, 13, _polish_gen13_es_glosses, "prefijos/sufijos/art.")

        if not skip_ch_final() and in_scope(13):
            ch13_final = 0
            ch13_final_merged = 0
            for v in data["verses"]:
                if v.get("chapter") == 13:
                    _gen13_reapply_oshb_splits(v, respect_user_gloss=True)
                    _fix_gen13_oshb_align(v, respect_user_gloss=True)
                    _fix_gen13_es_glosses(v, respect_user_gloss=True)
                    for p in v.get("pairs", []):
                        for hw in p.get("he_words", []):
                            if _has_user_gloss(hw):
                                continue
                            if _merge_prs_reading_gloss(hw):
                                ch13_final_merged += 1
                            _drop_redundant_prs_suffix(hw)
                    _gen13_finalize_prep_prs(v)
                    _fix_gen13_lxx_align(v)
                    normalize_verse_maqaf(v)
                    sanitize_verse_he_forms(v)
                    ch13_final += 1
            if ch13_final:
                sys.stdout.write(
                    f"  Gen cap. 13: splits OSHB finales ({ch13_final} versos, post-español)\n"
                )
            if ch13_final_merged:
                sys.stdout.write(
                    f"  Gen cap. 13: lecturas PRS re-fusionadas post-español: {ch13_final_merged}\n"
                )

        _gen_polish_chapter(data, 14, _polish_gen14_es_glosses, "prefijos/sufijos/art.")

        if not skip_ch_final() and in_scope(14):
            ch14_final = 0
            ch14_final_merged = 0
            for v in data["verses"]:
                if v.get("chapter") == 14:
                    _gen14_reapply_oshb_splits(v, respect_user_gloss=True)
                    _fix_gen14_oshb_align(v, respect_user_gloss=True)
                    _fix_gen14_es_glosses(v, respect_user_gloss=True)
                    for p in v.get("pairs", []):
                        for hw in p.get("he_words", []):
                            if _has_user_gloss(hw):
                                continue
                            if _merge_prs_reading_gloss(hw):
                                ch14_final_merged += 1
                            _drop_redundant_prs_suffix(hw)
                    _gen14_finalize_prep_prs(v)
                    _fix_gen14_lxx_align(v)
                    normalize_verse_maqaf(v)
                    sanitize_verse_he_forms(v)
                    _gen14_fix_zeboim_spelling(v)
                    ch14_final += 1
            if ch14_final:
                sys.stdout.write(
                    f"  Gen cap. 14: splits OSHB finales ({ch14_final} versos, post-español)\n"
                )
            if ch14_final_merged:
                sys.stdout.write(
                    f"  Gen cap. 14: lecturas PRS re-fusionadas post-español: {ch14_final_merged}\n"
                )

        _gen_polish_chapter(data, 15, _polish_gen15_es_glosses, "prefijos/sufijos/art.")

        if not skip_ch_final() and in_scope(15):
            ch15_final = 0
            ch15_final_merged = 0
            for v in data["verses"]:
                if v.get("chapter") == 15:
                    _gen15_reapply_oshb_splits(v, respect_user_gloss=True)
                    _fix_gen15_oshb_align(v, respect_user_gloss=True)
                    _fix_gen15_es_glosses(v, respect_user_gloss=True)
                    for p in v.get("pairs", []):
                        for hw in p.get("he_words", []):
                            if _has_user_gloss(hw):
                                continue
                            if _merge_prs_reading_gloss(hw):
                                ch15_final_merged += 1
                            _drop_redundant_prs_suffix(hw)
                    _fix_gen15_oshb_align(v, respect_user_gloss=True)
                    _gen15_finalize_b4_hebrew(v, respect_user_gloss=True)
                    _gen15_promote_gkadd(v)
                    _gen15_dedupe_gk_add(v)
                    _fix_gen15_lxx_align(v)
                    _gen15_dedupe_gk_add(v)
                    _gen15_strip_dot_prefixes(v)
                    _gen15_trim_prefix_lengths(v)
                    normalize_verse_maqaf(v)
                    sanitize_verse_he_forms(v)
                    ch15_final += 1
            if ch15_final:
                sys.stdout.write(
                    f"  Gen cap. 15: splits OSHB finales ({ch15_final} versos, post-español)\n"
                )
            if ch15_final_merged:
                sys.stdout.write(
                    f"  Gen cap. 15: lecturas PRS re-fusionadas post-español: {ch15_final_merged}\n"
                )

        _gen_polish_chapter(data, 16, _polish_gen16_es_glosses, "prefijos/sufijos/art.")

        if not skip_ch_final() and in_scope(16):
            ch16_final = 0
            ch16_final_merged = 0
            for v in data["verses"]:
                if v.get("chapter") == 16:
                    _gen16_reapply_oshb_splits(v, respect_user_gloss=True)
                    _fix_gen16_oshb_align(v, respect_user_gloss=True)
                    _fix_gen16_es_glosses(v, respect_user_gloss=True)
                    for p in v.get("pairs", []):
                        for hw in p.get("he_words", []):
                            if _has_user_gloss(hw):
                                continue
                            if _merge_prs_reading_gloss(hw):
                                ch16_final_merged += 1
                            _drop_redundant_prs_suffix(hw)
                    _gen16_finalize_prep_prs(v)
                    _fix_gen16_lxx_align(v)
                    normalize_verse_maqaf(v)
                    sanitize_verse_he_forms(v)
                    ch16_final += 1
            if ch16_final:
                sys.stdout.write(
                    f"  Gen cap. 16: splits OSHB finales ({ch16_final} versos, post-español)\n"
                )
            if ch16_final_merged:
                sys.stdout.write(
                    f"  Gen cap. 16: lecturas PRS re-fusionadas post-español: {ch16_final_merged}\n"
                )

        _gen_polish_chapter(data, 17, _polish_gen17_es_glosses, "prefijos/sufijos/art.")

        if not skip_ch_final() and in_scope(17):
            ch17_final = 0
            ch17_final_merged = 0
            for v in data["verses"]:
                if v.get("chapter") == 17:
                    _gen17_reapply_oshb_splits(v, respect_user_gloss=True)
                    _fix_gen17_oshb_align(v, respect_user_gloss=True)
                    _fix_gen17_es_glosses(v, respect_user_gloss=True)
                    for p in v.get("pairs", []):
                        for hw in p.get("he_words", []):
                            if _has_user_gloss(hw):
                                continue
                            if _merge_prs_reading_gloss(hw):
                                ch17_final_merged += 1
                            _drop_redundant_prs_suffix(hw)
                    _gen17_finalize_prep_prs(v)
                    _fix_gen17_lxx_align(v)
                    normalize_verse_maqaf(v)
                    sanitize_verse_he_forms(v)
                    ch17_final += 1
            if ch17_final:
                sys.stdout.write(
                    f"  Gen cap. 17: splits OSHB finales ({ch17_final} versos, post-español)\n"
                )
            if ch17_final_merged:
                sys.stdout.write(
                    f"  Gen cap. 17: lecturas PRS re-fusionadas post-español: {ch17_final_merged}\n"
                )

        _gen_polish_chapter(data, 18, _polish_gen18_es_glosses, "prefijos/sufijos/art.")

        if not skip_ch_final() and in_scope(18):
            ch18_final = 0
            ch18_final_merged = 0
            for v in data["verses"]:
                if v.get("chapter") == 18:
                    _gen18_reapply_oshb_splits(v, respect_user_gloss=True)
                    _fix_gen18_oshb_align(v, respect_user_gloss=True)
                    _fix_gen18_es_glosses(v, respect_user_gloss=True)
                    for p in v.get("pairs", []):
                        for hw in p.get("he_words", []):
                            if _has_user_gloss(hw):
                                continue
                            if _merge_prs_reading_gloss(hw):
                                ch18_final_merged += 1
                            _drop_redundant_prs_suffix(hw)
                    _gen18_finalize_prep_prs(v)
                    _fix_gen18_lxx_align(v)
                    normalize_verse_maqaf(v)
                    sanitize_verse_he_forms(v)
                    ch18_final += 1
            if ch18_final:
                sys.stdout.write(
                    f"  Gen cap. 18: splits OSHB finales ({ch18_final} versos, post-español)\n"
                )
            if ch18_final_merged:
                sys.stdout.write(
                    f"  Gen cap. 18: lecturas PRS re-fusionadas post-español: {ch18_final_merged}\n"
                )

        _gen_polish_chapter(data, 19, _polish_gen19_es_glosses, "prefijos/sufijos/art.")

        if not skip_ch_final() and in_scope(19):
            ch19_final = 0
            ch19_final_merged = 0
            for v in data["verses"]:
                if v.get("chapter") == 19:
                    _gen19_reapply_oshb_splits(v, respect_user_gloss=True)
                    _fix_gen19_oshb_align(v, respect_user_gloss=True)
                    _fix_gen19_es_glosses(v, respect_user_gloss=True)
                    for p in v.get("pairs", []):
                        for hw in p.get("he_words", []):
                            if _has_user_gloss(hw):
                                continue
                            if _merge_prs_reading_gloss(hw):
                                ch19_final_merged += 1
                            _drop_redundant_prs_suffix(hw)
                    _gen19_finalize_prep_prs(v)
                    _fix_gen19_lxx_align(v)
                    normalize_verse_maqaf(v)
                    sanitize_verse_he_forms(v)
                    ch19_final += 1
            if ch19_final:
                sys.stdout.write(
                    f"  Gen cap. 19: splits OSHB finales ({ch19_final} versos, post-español)\n"
                )
            if ch19_final_merged:
                sys.stdout.write(
                    f"  Gen cap. 19: lecturas PRS re-fusionadas post-español: {ch19_final_merged}\n"
                )

        _gen_polish_chapter(data, 20, _polish_gen20_es_glosses, "prefijos/sufijos/art.")

        if not skip_ch_final() and in_scope(20):
            ch20_final = 0
            ch20_final_merged = 0
            for v in data["verses"]:
                if v.get("chapter") == 20:
                    _gen20_reapply_oshb_splits(v, respect_user_gloss=True)
                    _fix_gen20_oshb_align(v, respect_user_gloss=True)
                    _fix_gen20_es_glosses(v, respect_user_gloss=True)
                    for p in v.get("pairs", []):
                        for hw in p.get("he_words", []):
                            if _has_user_gloss(hw):
                                continue
                            if _merge_prs_reading_gloss(hw):
                                ch20_final_merged += 1
                            _drop_redundant_prs_suffix(hw)
                    _gen20_finalize_prep_prs(v)
                    _fix_gen20_lxx_align(v)
                    normalize_verse_maqaf(v)
                    sanitize_verse_he_forms(v)
                    ch20_final += 1
            if ch20_final:
                sys.stdout.write(
                    f"  Gen cap. 20: splits OSHB finales ({ch20_final} versos, post-español)\n"
                )
            if ch20_final_merged:
                sys.stdout.write(
                    f"  Gen cap. 20: lecturas PRS re-fusionadas post-español: {ch20_final_merged}\n"
                )

        _gen_polish_chapter(data, 21, _polish_gen21_es_glosses, "prefijos/sufijos/art.")

        if not skip_ch_final() and in_scope(21):
            ch21_final = 0
            ch21_final_merged = 0
            for v in data["verses"]:
                if v.get("chapter") == 21:
                    _gen21_reapply_oshb_splits(v, respect_user_gloss=True)
                    _fix_gen21_oshb_align(v, respect_user_gloss=True)
                    _fix_gen21_es_glosses(v, respect_user_gloss=True)
                    for p in v.get("pairs", []):
                        for hw in p.get("he_words", []):
                            if _has_user_gloss(hw):
                                continue
                            if _merge_prs_reading_gloss(hw):
                                ch21_final_merged += 1
                            _drop_redundant_prs_suffix(hw)
                    _gen21_finalize_prep_prs(v)
                    _fix_gen21_lxx_align(v)
                    normalize_verse_maqaf(v)
                    sanitize_verse_he_forms(v)
                    ch21_final += 1
            if ch21_final:
                sys.stdout.write(
                    f"  Gen cap. 21: splits OSHB finales ({ch21_final} versos, post-español)\n"
                )
            if ch21_final_merged:
                sys.stdout.write(
                    f"  Gen cap. 21: lecturas PRS re-fusionadas post-español: {ch21_final_merged}\n"
                )

        _gen_polish_chapter(data, 22, _polish_gen22_es_glosses, "prefijos/sufijos/art.")

        if not skip_ch_final() and in_scope(22):
            ch22_final = 0
            ch22_final_merged = 0
            for v in data["verses"]:
                if v.get("chapter") == 22:
                    _gen22_reapply_oshb_splits(v, respect_user_gloss=True)
                    _fix_gen22_oshb_align(v, respect_user_gloss=True)
                    _fix_gen22_es_glosses(v, respect_user_gloss=True)
                    for p in v.get("pairs", []):
                        for hw in p.get("he_words", []):
                            if _has_user_gloss(hw):
                                continue
                            if _merge_prs_reading_gloss(hw):
                                ch22_final_merged += 1
                            _drop_redundant_prs_suffix(hw)
                    _gen22_finalize_prep_prs(v)
                    _fix_gen22_lxx_align(v)
                    normalize_verse_maqaf(v)
                    sanitize_verse_he_forms(v)
                    ch22_final += 1
            if ch22_final:
                sys.stdout.write(
                    f"  Gen cap. 22: splits OSHB finales ({ch22_final} versos, post-español)\n"
                )
            if ch22_final_merged:
                sys.stdout.write(
                    f"  Gen cap. 22: lecturas PRS re-fusionadas post-español: {ch22_final_merged}\n"
                )

        _gen_polish_chapter(data, 23, _polish_gen23_es_glosses, "prefijos/sufijos/art.")

        if not skip_ch_final() and in_scope(23):
            ch23_final = 0
            ch23_final_merged = 0
            for v in data["verses"]:
                if v.get("chapter") == 23:
                    _gen23_reapply_oshb_splits(v, respect_user_gloss=True)
                    _fix_gen23_oshb_align(v, respect_user_gloss=True)
                    _fix_gen23_es_glosses(v, respect_user_gloss=True)
                    for p in v.get("pairs", []):
                        for hw in p.get("he_words", []):
                            if _has_user_gloss(hw):
                                continue
                            if _merge_prs_reading_gloss(hw):
                                ch23_final_merged += 1
                            _drop_redundant_prs_suffix(hw)
                    _gen23_finalize_prep_prs(v)
                    _fix_gen23_lxx_align(v)
                    normalize_verse_maqaf(v)
                    sanitize_verse_he_forms(v)
                    ch23_final += 1
            if ch23_final:
                sys.stdout.write(
                    f"  Gen cap. 23: splits OSHB finales ({ch23_final} versos, post-español)\n"
                )
            if ch23_final_merged:
                sys.stdout.write(
                    f"  Gen cap. 23: lecturas PRS re-fusionadas post-español: {ch23_final_merged}\n"
                )

        _gen_polish_chapter(data, 24, _polish_gen24_es_glosses, "prefijos/sufijos/art.")

        if not skip_ch_final() and in_scope(24):
            ch24_final = 0
            ch24_final_merged = 0
            for v in data["verses"]:
                if v.get("chapter") == 24:
                    _gen24_reapply_oshb_splits(v, respect_user_gloss=True)
                    _fix_gen24_oshb_align(v, respect_user_gloss=True)
                    _fix_gen24_es_glosses(v, respect_user_gloss=True)
                    for p in v.get("pairs", []):
                        for hw in p.get("he_words", []):
                            if _has_user_gloss(hw):
                                continue
                            if _merge_prs_reading_gloss(hw):
                                ch24_final_merged += 1
                            _drop_redundant_prs_suffix(hw)
                    _gen24_finalize_prep_prs(v)
                    _fix_gen24_lxx_align(v)
                    normalize_verse_maqaf(v)
                    sanitize_verse_he_forms(v)
                    ch24_final += 1
            if ch24_final:
                sys.stdout.write(
                    f"  Gen cap. 24: splits OSHB finales ({ch24_final} versos, post-español)\n"
                )
            if ch24_final_merged:
                sys.stdout.write(
                    f"  Gen cap. 24: lecturas PRS re-fusionadas post-español: {ch24_final_merged}\n"
                )

        _gen_polish_chapter(data, 25, _polish_gen25_es_glosses, "prefijos/sufijos/art.")

        if not skip_ch_final() and in_scope(25):
            ch25_final = 0
            ch25_final_merged = 0
            for v in data["verses"]:
                if v.get("chapter") == 25:
                    _gen25_reapply_oshb_splits(v, respect_user_gloss=True)
                    _fix_gen25_oshb_align(v, respect_user_gloss=True)
                    _fix_gen25_es_glosses(v, respect_user_gloss=True)
                    for p in v.get("pairs", []):
                        for hw in p.get("he_words", []):
                            if _has_user_gloss(hw):
                                continue
                            if _merge_prs_reading_gloss(hw):
                                ch25_final_merged += 1
                            _drop_redundant_prs_suffix(hw)
                    _gen25_finalize_prep_prs(v)
                    _fix_gen25_lxx_align(v)
                    normalize_verse_maqaf(v)
                    sanitize_verse_he_forms(v)
                    ch25_final += 1
            if ch25_final:
                sys.stdout.write(
                    f"  Gen cap. 25: splits OSHB finales ({ch25_final} versos, post-español)\n"
                )
            if ch25_final_merged:
                sys.stdout.write(
                    f"  Gen cap. 25: lecturas PRS re-fusionadas post-español: {ch25_final_merged}\n"
                )

        _gen_polish_chapter(data, 26, _polish_gen26_es_glosses, "prefijos/sufijos/art.")

        if not skip_ch_final() and in_scope(26):
            ch26_final = 0
            ch26_final_merged = 0
            for v in data["verses"]:
                if v.get("chapter") == 26:
                    _gen26_reapply_oshb_splits(v, respect_user_gloss=True)
                    _fix_gen26_oshb_align(v, respect_user_gloss=True)
                    _fix_gen26_es_glosses(v, respect_user_gloss=True)
                    for p in v.get("pairs", []):
                        for hw in p.get("he_words", []):
                            if _has_user_gloss(hw):
                                continue
                            if _merge_prs_reading_gloss(hw):
                                ch26_final_merged += 1
                            _drop_redundant_prs_suffix(hw)
                    _gen26_finalize_prep_prs(v)
                    _fix_gen26_lxx_align(v)
                    normalize_verse_maqaf(v)
                    sanitize_verse_he_forms(v)
                    ch26_final += 1
            if ch26_final:
                sys.stdout.write(
                    f"  Gen cap. 26: splits OSHB finales ({ch26_final} versos, post-español)\n"
                )
            if ch26_final_merged:
                sys.stdout.write(
                    f"  Gen cap. 26: lecturas PRS re-fusionadas post-español: {ch26_final_merged}\n"
                )

        _gen_polish_chapter(data, 27, _polish_gen27_es_glosses, "prefijos/sufijos/art.")

        if not skip_ch_final() and in_scope(27):
            ch27_final = 0
            ch27_final_merged = 0
            for v in data["verses"]:
                if v.get("chapter") == 27:
                    _gen27_reapply_oshb_splits(v, respect_user_gloss=True)
                    _fix_gen27_oshb_align(v, respect_user_gloss=True)
                    _fix_gen27_es_glosses(v, respect_user_gloss=True)
                    for p in v.get("pairs", []):
                        for hw in p.get("he_words", []):
                            if _has_user_gloss(hw):
                                continue
                            if _merge_prs_reading_gloss(hw):
                                ch27_final_merged += 1
                            _drop_redundant_prs_suffix(hw)
                    _gen27_finalize_prep_prs(v)
                    _fix_gen27_lxx_align(v)
                    normalize_verse_maqaf(v)
                    sanitize_verse_he_forms(v)
                    ch27_final += 1
            if ch27_final:
                sys.stdout.write(
                    f"  Gen cap. 27: splits OSHB finales ({ch27_final} versos, post-español)\n"
                )
            if ch27_final_merged:
                sys.stdout.write(
                    f"  Gen cap. 27: lecturas PRS re-fusionadas post-español: {ch27_final_merged}\n"
                )

        _gen_polish_chapter(data, 28, _polish_gen28_es_glosses, "prefijos/sufijos/art.")

        if not skip_ch_final() and in_scope(28):
            ch28_final = 0
            ch28_final_merged = 0
            for v in data["verses"]:
                if v.get("chapter") == 28:
                    _gen28_reapply_oshb_splits(v, respect_user_gloss=True)
                    _fix_gen28_oshb_align(v, respect_user_gloss=True)
                    _fix_gen28_es_glosses(v, respect_user_gloss=True)
                    for p in v.get("pairs", []):
                        for hw in p.get("he_words", []):
                            if _has_user_gloss(hw):
                                continue
                            if _merge_prs_reading_gloss(hw):
                                ch28_final_merged += 1
                            _drop_redundant_prs_suffix(hw)
                    _gen28_finalize_prep_prs(v)
                    _fix_gen28_lxx_align(v)
                    normalize_verse_maqaf(v)
                    sanitize_verse_he_forms(v)
                    ch28_final += 1
            if ch28_final:
                sys.stdout.write(
                    f"  Gen cap. 28: splits OSHB finales ({ch28_final} versos, post-español)\n"
                )
            if ch28_final_merged:
                sys.stdout.write(
                    f"  Gen cap. 28: lecturas PRS re-fusionadas post-español: {ch28_final_merged}\n"
                )

        _gen_polish_chapter(data, 29, _polish_gen29_es_glosses, "prefijos/sufijos/art.")

        if not skip_ch_final() and in_scope(29):
            ch29_final = 0
            ch29_final_merged = 0
            for v in data["verses"]:
                if v.get("chapter") == 29:
                    _gen29_reapply_oshb_splits(v, respect_user_gloss=True)
                    _fix_gen29_oshb_align(v, respect_user_gloss=True)
                    _fix_gen29_es_glosses(v, respect_user_gloss=True)
                    for p in v.get("pairs", []):
                        for hw in p.get("he_words", []):
                            if _has_user_gloss(hw):
                                continue
                            if _merge_prs_reading_gloss(hw):
                                ch29_final_merged += 1
                            _drop_redundant_prs_suffix(hw)
                    _gen29_finalize_prep_prs(v)
                    _fix_gen29_lxx_align(v)
                    normalize_verse_maqaf(v)
                    sanitize_verse_he_forms(v)
                    ch29_final += 1
            if ch29_final:
                sys.stdout.write(
                    f"  Gen cap. 29: splits OSHB finales ({ch29_final} versos, post-español)\n"
                )
            if ch29_final_merged:
                sys.stdout.write(
                    f"  Gen cap. 29: lecturas PRS re-fusionadas post-español: {ch29_final_merged}\n"
                )

        _gen_polish_chapter(data, 30, _polish_gen30_es_glosses, "prefijos/sufijos/art.")

        if not skip_ch_final() and in_scope(30):
            ch30_final = 0
            ch30_final_merged = 0
            for v in data["verses"]:
                if v.get("chapter") == 30:
                    _gen30_reapply_oshb_splits(v, respect_user_gloss=True)
                    _fix_gen30_oshb_align(v, respect_user_gloss=True)
                    _fix_gen30_es_glosses(v, respect_user_gloss=True)
                    for p in v.get("pairs", []):
                        for hw in p.get("he_words", []):
                            if _has_user_gloss(hw):
                                continue
                            if _merge_prs_reading_gloss(hw):
                                ch30_final_merged += 1
                            _drop_redundant_prs_suffix(hw)
                    _gen30_finalize_prep_prs(v)
                    _fix_gen30_lxx_align(v)
                    normalize_verse_maqaf(v)
                    sanitize_verse_he_forms(v)
                    ch30_final += 1
            if ch30_final:
                sys.stdout.write(
                    f"  Gen cap. 30: splits OSHB finales ({ch30_final} versos, post-español)\n"
                )
            if ch30_final_merged:
                sys.stdout.write(
                    f"  Gen cap. 30: lecturas PRS re-fusionadas post-español: {ch30_final_merged}\n"
                )
    # ── Global Pass 17: español peninsular → latino/neutro (último pass) ───────
    from gen_chapter_scope import skip_pass17

    if not skip_pass17():
        try:
            from es_latam_neutral import apply_to_interlineal, apply_to_rv1960, apply_to_glossas_registry

            _gp17 = apply_to_interlineal(data)
            _gp17_total = sum(_gp17.values())
            _data_dir = IN_FILE.parent
            rv_path = _data_dir / f"rv1960_{ACTIVE_BOOK}.json"
            _gp17_rv = {}
            if rv_path.exists():
                _rv = json.loads(rv_path.read_text(encoding="utf-8"))
                _gp17_rv = apply_to_rv1960(_rv)
                rv_path.write_text(
                    json.dumps(_rv, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8",
                )
                _gp17_total += _gp17_rv.get("verses", 0)
            gloss_path = _data_dir / "glosas_personales.json"
            _gp17_gl = {}
            if gloss_path.exists():
                _gl = json.loads(gloss_path.read_text(encoding="utf-8"))
                _gp17_gl = apply_to_glossas_registry(_gl)
                gloss_path.write_text(
                    json.dumps(_gl, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8",
                )
                _gp17_total += _gp17_gl.get("rules", 0)
            if _gp17_total:
                sys.stdout.write("\n  ── Global Pass 17: español latino/neutro ──\n")
                sys.stdout.write(f"    stem es              : {_gp17.get('stem_es', 0)}\n")
                sys.stdout.write(f"    prefix_es            : {_gp17.get('prefix_es', 0)}\n")
                sys.stdout.write(f"    prs_suffix es        : {_gp17.get('prs_suffix_es', 0)}\n")
                sys.stdout.write(f"    pair es_gloss        : {_gp17.get('pair_es_gloss', 0)}\n")
                if _gp17_rv:
                    sys.stdout.write(f"    rv1960 versos        : {_gp17_rv.get('verses', 0)}\n")
                if _gp17_gl:
                    sys.stdout.write(f"    glosas reglas        : {_gp17_gl.get('rules', 0)}\n")
                sys.stdout.write(f"    Total cambios        : {_gp17_total}\n")
        except Exception as _gp17_err:
            sys.stdout.write(f"\n  ── Global Pass 17: omitido ({_gp17_err}) ──\n")

    # ── Global Pass 18: NPROP — mayúscula en nombres y lugares (Gén 1–15) ───────
    if ACTIVE_BOOK == "genesis":
        _nprop_chs = (
            (args.chapter,) if args.chapter is not None
            else tuple(range(1, 31))
        )
        _gp18 = _apply_nprop_capitalization(data, chapters=_nprop_chs)
        if _gp18:
            sys.stdout.write("\n  ── Global Pass 18: nombres/lugares NPROP ──\n")
            sys.stdout.write(f"    Glosas capitalizadas          : {_gp18}\n")

    # ── Global Pass 19: יהוה — vocalización OSHB + glosa Hashem/'Elohim ───────
    _oshb_forms_map = _load_oshb_forms_by_ref(_oshb_morph_dir)
    _gp19 = _apply_yhwh_vowel_forms(data, _oshb_forms_map)
    if any(_gp19.values()):
        sys.stdout.write("\n  ── Global Pass 19: vocalización יהוה (OSHB) ──\n")
        sys.stdout.write(f"    he_form actualizados           : {_gp19['he_form']}\n")
        sys.stdout.write(f"    Glosas Hashem/'Elohim         : {_gp19['es']}\n")
        sys.stdout.write(f"    Strong H3068 corregidos        : {_gp19['strongs']}\n")
        if _gp19["missing_oshb"]:
            sys.stdout.write(f"    Sin forma OSHB (fallback)      : {_gp19['missing_oshb']}\n")

    _maqaf_norm = sum(normalize_verse_maqaf(v) for v in data.get("verses", []))
    if _maqaf_norm:
        sys.stdout.write(f"\n  Maqaf UI normalizado (post-passes): {_maqaf_norm} ajustes\n")

    OUT_FILE.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    sys.stdout.write(f"\nCorregidos: {applied}  |  No encontrados: {skipped}\n")
    sys.stdout.write(f"JSON: {OUT_FILE}\n")


if __name__ == "__main__":
    main()
