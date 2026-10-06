"""
Utilidades compartidas para Paso 5 (5.1–5.5).
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

ROOT = Path(r"C:\Users\pik_y\Documents\TRADUCCION")
ANGELOS = Path(r"C:\Users\pik_y\Documents\GitHub\Local-consults\estudio\angelos")
SCRIPTS = ROOT / "scripts"

# ── Estado del libro activo (default: Génesis) ───────────────────────────────
# Los scripts paso5_* deben llamar a `set_active_book(slug)` (o pasar --book)
# para procesar otro libro. Las rutas globales (GEN_JSON, OSHB_DIR, SNAP_DIR,
# IDX_ES, IDX_HE) se reescriben al cambiar el libro activo.
ACTIVE_BOOK_SLUG = "genesis"
GEN_JSON = ROOT / "data" / "genesis_final.json"           # data/<slug>_final.json
OSHB_DIR = ANGELOS / "IdiomaORIGEN" / "oshb-morph" / "chapters" / "01_Génesis"
SNAP_DIR = ANGELOS / "IdiomaORIGEN" / "interlinear-snapshot" / "chapters" / "genesis"
IDX_ES = ROOT / "BIBLIAS" / "_idx_strong_es_gen.json"
IDX_HE = ROOT / "BIBLIAS" / "_idx_strong_he_gen.json"


def set_active_book(slug: str) -> None:
    """Cambia el libro activo y reescribe GEN_JSON/OSHB_DIR/SNAP_DIR/IDX_*.

    Si `slug` es 'genesis' (default) las rutas quedan idénticas a las heredadas
    (compatibilidad retro con archivos pre-existentes).
    """
    global ACTIVE_BOOK_SLUG, GEN_JSON, OSHB_DIR, SNAP_DIR, IDX_ES, IDX_HE
    try:
        from book_config import resolve as _resolve
    except ImportError:
        return
    cfg = _resolve(slug)
    ACTIVE_BOOK_SLUG = cfg.slug
    GEN_JSON = cfg.final_json_path
    OSHB_DIR = cfg.oshb_dir
    SNAP_DIR = cfg.snap_dir
    IDX_ES = cfg.idx_es_path
    IDX_HE = cfg.idx_he_path


def add_book_arg(parser) -> None:
    """Agrega `--book` a cualquier argparse.ArgumentParser de paso5_*."""
    parser.add_argument(
        "--book",
        default="genesis",
        help="slug del libro (genesis, exodo, levitico, …)",
    )

HE_STRIP_RE = re.compile(
    r"[\u0591-\u05C7\u05BE\u05C0\u05C3\u05F3\u05F4\u200D\u200C\s\-\u05BE]"
)
EMPTY_HE = {"", "·", ".", "—", "-"}


def fold_he(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    return HE_STRIP_RE.sub("", s)


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


@dataclass
class SiteToken:
    """Un morfema visible en el JSON del sitio."""
    ref: str
    fold: str
    form: str
    morph: str
    es: str
    gr_word: str
    strongs: str
    raw: str
    pair_idx: int
    hw_idx: int
    slot: str  # prefix | stem | suffix
    slot_idx: int = 0
    global_idx: int = -1


@dataclass
class OshbToken:
    """Un morfema en oshb-morph."""
    ref: str
    idx: int
    fold: str
    form: str
    morph: str


def verse_in_chapter(v: dict, chapter: int | None) -> bool:
    if chapter is None:
        return True
    try:
        return int(v.get("chapter", 0)) == chapter
    except (TypeError, ValueError):
        return False


def verse_in_range(
    v: dict,
    chapter: int | None = None,
    from_chapter: int | None = None,
    to_chapter: int | None = None,
) -> bool:
    """Filtro por capítulo exacto o rango [from_chapter .. to_chapter]."""
    try:
        ch = int(v.get("chapter", 0))
    except (TypeError, ValueError):
        return False
    if chapter is not None:
        return ch == chapter
    if from_chapter is not None and ch < from_chapter:
        return False
    if to_chapter is not None and ch > to_chapter:
        return False
    return True


def verse_ref(v: dict) -> str:
    if v.get("ref"):
        tail = str(v["ref"]).replace("Gen", "").strip()
        return tail.split()[-1] if tail else ""
    return f"{v.get('chapter', '')}:{v.get('verse', '')}"


def load_genesis() -> dict:
    """Carga `data/<slug>_final.json` del libro activo (default Génesis)."""
    return json.loads(GEN_JSON.read_text(encoding="utf-8"))


# Alias semántico para libros distintos de Génesis.
load_active = load_genesis


def save_active(data: dict) -> None:
    """Escribe `GEN_JSON` (libro activo) en formato compacto, igual que merge_oshb."""
    GEN_JSON.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def load_idx_es() -> dict:
    """Lee el índice Strong ES del libro activo."""
    if not IDX_ES.exists():
        raise FileNotFoundError(
            f"Falta índice Strong ES: {IDX_ES}\n"
            f"Ejecuta primero: python build_lookup_indices_book.py --book {ACTIVE_BOOK_SLUG}"
        )
    return json.loads(IDX_ES.read_text(encoding="utf-8"))


def load_idx_he() -> dict:
    """Lee el índice Strong HE del libro activo."""
    if not IDX_HE.exists():
        raise FileNotFoundError(
            f"Falta índice Strong HE: {IDX_HE}\n"
            f"Ejecuta primero: python build_lookup_indices_book.py --book {ACTIVE_BOOK_SLUG}"
        )
    return json.loads(IDX_HE.read_text(encoding="utf-8"))


def load_oshb_verse(ch: int, vs: int) -> tuple[list[str], list[str]] | None:
    f = OSHB_DIR / f"{ch}.json"
    if not f.exists():
        return None
    block = json.loads(f.read_text(encoding="utf-8")).get(str(vs))
    if not block:
        return None
    return block.get("forms", []), block.get("morphs", [])


def list_site_tokens(v: dict) -> list[SiteToken]:
    """Lista ordenada de morfemas del sitio (orden de visualización)."""
    out: list[SiteToken] = []
    g = 0
    ref = verse_ref(v)
    for pi, pair in enumerate(v.get("pairs", [])):
        if pair.get("kind") in ("gk_add", "heb_omit"):
            continue
        for hi, hw in enumerate(pair.get("he_words", []) or []):
            raw = hw.get("raw", "") or ""
            strongs = normalize_strong(hw.get("strongs", "") or "")
            for ki, pf in enumerate(hw.get("prefix_forms", []) or []):
                if fold_he(pf) or pf.strip():
                    out.append(SiteToken(
                        ref=ref, fold=fold_he(pf), form=pf,
                        morph=(hw.get("prefix_morphs") or [""])[ki]
                        if ki < len(hw.get("prefix_morphs") or []) else "",
                        es=(hw.get("prefix_es") or [""])[ki]
                        if ki < len(hw.get("prefix_es") or []) else "",
                        gr_word=(hw.get("prefix_gr") or [""])[ki]
                        if ki < len(hw.get("prefix_gr") or []) else "",
                        strongs=strongs, raw=raw, pair_idx=pi, hw_idx=hi,
                        slot="prefix", slot_idx=ki, global_idx=g,
                    ))
                    g += 1
            hf = hw.get("he_form", "") or ""
            if fold_he(hf) or hf.strip() not in EMPTY_HE:
                out.append(SiteToken(
                    ref=ref, fold=fold_he(hf), form=hf,
                    morph=hw.get("he_morph", "") or "",
                    es=hw.get("es", "") or "",
                    gr_word=hw.get("gr_word", "") or "",
                    strongs=strongs, raw=raw, pair_idx=pi, hw_idx=hi,
                    slot="stem", global_idx=g,
                ))
                g += 1
            prs = hw.get("prs_suffix") or {}
            pf = prs.get("he_form", "") or ""
            if fold_he(pf):
                out.append(SiteToken(
                    ref=ref, fold=fold_he(pf), form=pf,
                    morph=prs.get("he_morph", "") or "",
                    es=prs.get("es", "") or "",
                    gr_word=prs.get("gr_word", "") or "",
                    strongs=strongs, raw=raw, pair_idx=pi, hw_idx=hi,
                    slot="suffix", global_idx=g,
                ))
                g += 1
    return out


def iter_site_tokens(v: dict) -> Iterator[SiteToken]:
    yield from list_site_tokens(v)


def iter_oshb_tokens(ch: int, vs: int) -> list[OshbToken]:
    ref = f"{ch}:{vs}"
    loaded = load_oshb_verse(ch, vs)
    if not loaded:
        return []
    forms, morphs = loaded
    out: list[OshbToken] = []
    for i, (form, morph) in enumerate(zip(forms, morphs)):
        if not fold_he(form) and form.strip() in ("־", "-", ""):
            continue
        out.append(OshbToken(
            ref=ref, idx=i, fold=fold_he(form), form=form, morph=morph or "",
        ))
    return out


def site_concatenated(v: dict, with_maqaf: bool = True) -> str:
    parts: list[str] = []
    for t in iter_site_tokens(v):
        f = t.form.strip()
        if not f or f in EMPTY_HE:
            continue
        parts.append(f)
    sep = "\u05be" if with_maqaf else ""
    return sep.join(parts)


def oshb_concatenated(ch: int, vs: int, with_maqaf: bool = True) -> str:
    loaded = load_oshb_verse(ch, vs)
    if not loaded:
        return ""
    forms, _ = loaded
    parts = [f for f in forms if f.strip() and f.strip() not in ("־", "-")]
    sep = "\u05be" if with_maqaf else ""
    return sep.join(parts)


def load_snapshot_verse(ch: int, vs: int) -> list[dict]:
    f = SNAP_DIR / f"{ch}.json"
    if not f.exists():
        return []
    data = json.loads(f.read_text(encoding="utf-8"))
    verse = data.get("verses", {}).get(str(vs), {})
    return verse.get("segments", []) or []


def snapshot_by_fold(ch: int, vs: int) -> dict[str, list[dict]]:
    """fold(hebrew) → lista de segmentos (puede haber homógrafos)."""
    acc: dict[str, list[dict]] = {}
    for seg in load_snapshot_verse(ch, vs):
        key = fold_he(seg.get("hebrew", ""))
        if key:
            acc.setdefault(key, []).append(seg)
    return acc


# ── Alineación LCS por consonantes ──────────────────────────────────────────

@dataclass
class AlignRow:
    ref: str
    kind: str  # match | missing_in_site | extra_in_site | fused
    oshb_idx: int = -1
    oshb_form: str = ""
    oshb_morph: str = ""
    site_pair: int = -1
    site_hw: int = -1
    site_slot: str = ""
    site_form: str = ""
    site_morph: str = ""
    note: str = ""


def verse_has_ins_idx(verse: dict, oshb_idx: int) -> bool:
    tag = f"INS/{oshb_idx}"
    for pair in verse.get("pairs", []) or []:
        if pair.get("he") == tag:
            return True
        for hw in pair.get("he_words", []) or []:
            if (hw.get("raw") or "") == tag:
                return True
    return False


def is_maqaf_continuation(ot: OshbToken, site: list[SiteToken]) -> bool:
    """Morfema OSHB tras maqaf (־…) ya unido al final de una tarjeta del sitio."""
    form = (ot.form or "").strip()
    if not form.startswith("\u05be") and not form.startswith("־"):
        return False
    f = ot.fold
    if not f:
        return True
    for t in site:
        if not t.fold:
            continue
        if t.fold.endswith(f) or (len(t.fold) > len(f) and f in t.fold):
            return True
    return False


def is_oshb_covered_by_fusion(
    oshb_fold: str,
    oshb_idx: int,
    site: list[SiteToken],
    consumed_oshb: set[int],
) -> bool:
    """True si el morfema OSHB ya está dentro de una tarjeta fusionada del sitio."""
    if not oshb_fold or oshb_idx in consumed_oshb:
        return True
    for t in site:
        if not t.fold:
            continue
        if t.fold == oshb_fold:
            return False
        if oshb_fold in t.fold and len(t.fold) > len(oshb_fold):
            return True
    folds = [t.fold for t in site if t.fold]
    for i in range(len(folds)):
        acc = ""
        for j in range(i, min(i + 6, len(folds))):
            acc += folds[j]
            if oshb_fold in acc and len(acc) > len(oshb_fold):
                return True
    return False


def build_insert_hw(ot: OshbToken, seg: dict | None) -> dict:
    seg = seg or {}
    es = (seg.get("spanish") or "").strip()
    gr = (seg.get("greek_lxx") or "").strip()
    morph = ot.morph or ""
    head = morph.split("+")[0] if morph else ""
    if head == "PART.OBJ.DIR" and not es:
        es = ""
        gr = gr or "—"
    return {
        "raw": f"INS/{ot.idx}",
        "he_form": ot.form,
        "he_morph": morph,
        "es": es,
        "gr_word": gr or "—",
        "strongs": (seg.get("strongs") or "").strip(),
        "es_source": "paso5_1:snapshot" if seg else "paso5_1:oshb",
        "prefixes": [],
        "prefix_forms": [],
        "prefix_morphs": [],
        "prefix_es": [],
        "prefix_gr": [],
    }


def build_insert_pair(ot: OshbToken, seg: dict | None) -> dict:
    hw = build_insert_hw(ot, seg)
    form = ot.form
    return {
        "he": f"INS/{ot.idx}",
        "he_unicode": form,
        "he_stem_unicode": fold_he(form),
        "he_words": [hw],
        "he_note": "",
        "gr": "",
        "gr_unicode": "",
        "kind": "align",
        "isApparatusPrefix": False,
        "isGreekOmitted": False,
        "gr_tokens": [],
        "morph_summary": "",
        "lemma_main": "",
        "lemma_unicode": "",
    }


def insert_missing_morpheme_in_verse(
    verse: dict,
    ot: OshbToken,
    after: SiteToken | None,
    before: SiteToken | None,
    seg: dict | None,
) -> bool:
    """
    Inserta un morfema OSHB faltante en la posición correcta del versículo.
    Preferencia: nuevo `pair` entre pares existentes (una tarjeta = un morfema).
    """
    pairs = verse.get("pairs", [])
    if pairs is None:
        return False
    new_pair = build_insert_pair(ot, seg)

    if after is None and before is None:
        pairs.insert(0, new_pair)
        return True

    if after is not None and before is not None and after.pair_idx == before.pair_idx:
        pair = pairs[after.pair_idx]
        if pair.get("kind") in ("gk_add", "heb_omit"):
            pairs.insert(after.pair_idx + 1, new_pair)
            return True
        hws = pair.setdefault("he_words", [])
        ins = after.hw_idx + 1
        if after.slot == "prefix":
            ins = after.hw_idx + 1
        elif after.slot == "stem" and (before.hw_idx > after.hw_idx or before.slot != "suffix"):
            ins = after.hw_idx + 1
        hws.insert(min(ins, len(hws)), build_insert_hw(ot, seg))
        return True

    if after is not None:
        pairs.insert(after.pair_idx + 1, new_pair)
        return True
    if before is not None:
        pairs.insert(before.pair_idx, new_pair)
        return True
    pairs.append(new_pair)
    return True


def align_sequences(
    ref: str,
    oshb: list[OshbToken],
    site: list[SiteToken],
) -> tuple[list[AlignRow], set[int]]:
    """Alineación global (LCS) sobre `fold`. Devuelve filas + índices OSHB consumidos por fusión."""
    a = [t.fold for t in oshb]
    b = [t.fold for t in site]
    n, m = len(a), len(b)
    consumed_oshb: set[int] = set()
    # tabla LCS
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if a[i - 1] == b[j - 1] and a[i - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    # backtrack
    rows: list[AlignRow] = []
    i, j = n, m
    stack: list[AlignRow] = []
    while i > 0 or j > 0:
        if i > 0 and j > 0 and a[i - 1] == b[j - 1] and a[i - 1]:
            ot, st = oshb[i - 1], site[j - 1]
            stack.append(AlignRow(
                ref=ref, kind="match",
                oshb_idx=ot.idx, oshb_form=ot.form, oshb_morph=ot.morph,
                site_pair=st.pair_idx, site_hw=st.hw_idx, site_slot=st.slot,
                site_form=st.form, site_morph=st.morph,
            ))
            i -= 1
            j -= 1
        elif j > 0 and (i == 0 or dp[i][j - 1] >= dp[i - 1][j]):
            st = site[j - 1]
            # ¿fusionado? cubre varios ref consecutivos
            fused = False
            note = ""
            if i > 0 and st.fold:
                acc = ""
                k = i - 1
                while k >= 0 and len(acc) < len(st.fold) + 8:
                    acc = oshb[k].fold + acc
                    if acc == st.fold:
                        fused = True
                        for idx in range(k, i):
                            consumed_oshb.add(oshb[idx].idx)
                        note = f"cubre OSHB[{k}:{i}]"
                        break
                    k -= 1
            stack.append(AlignRow(
                ref=ref,
                kind="fused" if fused else "extra_in_site",
                site_pair=st.pair_idx, site_hw=st.hw_idx, site_slot=st.slot,
                site_form=st.form, site_morph=st.morph,
                note=note if fused else "",
            ))
            j -= 1
        elif i > 0:
            ot = oshb[i - 1]
            stack.append(AlignRow(
                ref=ref, kind="missing_in_site",
                oshb_idx=ot.idx, oshb_form=ot.form, oshb_morph=ot.morph,
            ))
            i -= 1
        else:
            break
    stack.reverse()
    return stack, consumed_oshb


def parse_ref(ref: str) -> tuple[int, int]:
    ch, vs = ref.split(":", 1)
    return int(ch), int(vs)
