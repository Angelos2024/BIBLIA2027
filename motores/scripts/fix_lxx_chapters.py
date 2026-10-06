#!/usr/bin/env python3
"""Repara LXX caps 8–15: reparto morfema, gk_add stubs, cola Rahlfs."""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from apply_corrections import (  # noqa: E402
    _fix_lxx_align_verse,
    _is_meta_hw,
    _norm_gr_token,
    _san_gr,
)
from audit_gen_chapter_lxx import _gather_assigned, _norm_gr, _tokens_from_phrase

DEFAULT_LXX = (
    ROOT.parent
    / "GitHub"
    / "Local-consults"
    / "estudio"
    / "angelos"
    / "LXX"
    / "chapters"
    / "Gen"
)

_STUB_HE_RAW = frozenset({"GKADD", "=<LXX>", "L/HM"})
_PROMOTE_GR_FRAGMENTS = frozenset({
    "αυτων", "αυτου", "αυτοις", "αυτην", "αυτο",
    "εαυτων", "εαυτοις", "εαυτον", "εαυτοις",
    "εξ αυτων", "εαυτοις",
})


def lxx_root() -> Path:
    env = os.environ.get("LXX_GEN_DIR")
    return Path(env) if env else DEFAULT_LXX


def load_lxx(chapter: int) -> dict[str, list[dict]]:
    p = lxx_root() / f"{chapter}.json"
    return json.loads(p.read_text(encoding="utf-8")).get("verses") or {}


def verse_data_gr_tokens(verse: dict) -> list[str]:
    out: list[str] = []
    for p in verse.get("pairs", []):
        if p.get("kind") == "heb_omit":
            continue
        out.extend(_tokens_from_phrase(p.get("gr_unicode") or ""))
    return out


def verse_has_greek(verse: dict) -> bool:
    return bool(verse_data_gr_tokens(verse))


def inject_lxx_word_only_verse(verse: dict, lxx_surface: list[str]) -> list[str]:
    """Verso sin griego alguno (solo kind=word) → un gk_add con LXX Rahlfs completo."""
    fixes: list[str] = []
    if verse_has_greek(verse):
        return fixes
    pairs = verse.get("pairs") or []
    if not pairs or not lxx_surface:
        return fixes
    ch, vn = verse.get("chapter"), verse.get("verse")
    phrase = " ".join(_san_gr(w) for w in lxx_surface if (w or "").strip())
    if not phrase:
        return fixes
    verse.setdefault("pairs", []).append(
        {
            "kind": "gk_add",
            "he": "",
            "he_unicode": "",
            "he_stem_unicode": "",
            "gr_unicode": phrase,
            "gr": "",
            "he_words": [
                {
                    "raw": "GKADD",
                    "gr_word": phrase,
                    "gr_source": "patch_lxx_word_only",
                    "es_source": "patch_meta",
                }
            ],
        }
    )
    fixes.append(f"{ch}:{vn} +gk_add word-only ({len(lxx_surface)} tok)")
    return fixes


def dedupe_identical_gk_add(verse: dict, lxx_surface: list[str] | None = None) -> list[str]:
    """Elimina gk_add duplicados solo si el verso sigue cubierto respecto a Rahlfs."""
    fixes: list[str] = []
    ch, vn = verse.get("chapter"), verse.get("verse")
    pairs = verse.get("pairs") or []
    seen: set[str] = set()
    kept: list[dict] = []

    def _still_ok(test_pairs: list[dict]) -> bool:
        if not lxx_surface:
            return True
        tmp = {"pairs": test_pairs}
        return not _ordered_missing_tokens(tmp, lxx_surface)

    for pi, p in enumerate(pairs):
        if p.get("kind") != "gk_add":
            kept.append(p)
            continue
        gr = (p.get("gr_unicode") or "").strip()
        if gr and gr in seen:
            trial = kept + pairs[pi + 1 :]
            if _still_ok(trial):
                fixes.append(f"{ch}:{vn} drop duplicate gk_add[{pi}] ({gr[:30]})")
                continue
        if gr:
            seen.add(gr)
        kept.append(p)
    if len(kept) != len(pairs):
        verse["pairs"] = kept
    return fixes


def promote_gkadd_stubs(verse: dict) -> list[str]:
    """GKADD stub + kind=align → gk_add; limpia he huérfano."""
    fixes: list[str] = []
    ch, vn = verse.get("chapter"), verse.get("verse")
    for pi, p in enumerate(verse.get("pairs", [])):
        if p.get("kind") == "gk_add":
            continue
        gr = (p.get("gr_unicode") or "").strip()
        if not gr:
            continue
        hws = p.get("he_words") or []
        gk_stub = any((h.get("raw") or "") in _STUB_HE_RAW for h in hws)
        hw_empty = all(not (h.get("he_form") or "").strip() for h in hws if not _is_meta_hw(h))
        he = (p.get("he_unicode") or "").strip()

        if gk_stub or (hw_empty and not he):
            p["kind"] = "gk_add"
            p["he"] = ""
            p["he_unicode"] = ""
            p["he_stem_unicode"] = ""
            p["prefixes"] = ""
            p["he_words"] = [
                {
                    "raw": "GKADD",
                    "gr_word": gr,
                    "gr_source": "patch_lxx",
                    "es_source": "patch_meta",
                }
            ]
            fixes.append(f"{ch}:{vn} pair[{pi}] → gk_add ({gr})")
            continue

        if gk_stub and he:
            p["kind"] = "gk_add"
            p["he"] = ""
            p["he_unicode"] = ""
            p["he_stem_unicode"] = ""
            p["prefixes"] = ""
            p["he_words"] = [
                {
                    "raw": "GKADD",
                    "gr_word": gr,
                    "gr_source": "patch_lxx",
                    "es_source": "patch_meta",
                }
            ]
            fixes.append(f"{ch}:{vn} pair[{pi}] stub+he → gk_add ({gr})")

    return fixes


def promote_pronoun_stubs(verse: dict) -> list[str]:
    """Griego reflexivo/demo en par align con hebreo residual → gk_add."""
    fixes: list[str] = []
    ch, vn = verse.get("chapter"), verse.get("verse")
    for pi, p in enumerate(verse.get("pairs", [])):
        if p.get("kind") != "align":
            continue
        gr = (p.get("gr_unicode") or "").strip()
        if not gr:
            continue
        gn = _norm_gr_token(gr)
        if gn not in _PROMOTE_GR_FRAGMENTS and not any(
            gn.startswith(x + " ") or gn == x for x in ("αυτ", "εαυτ", "εξ αυτ")
        ):
            continue
        he = (p.get("he_unicode") or "").strip()
        if not he and not any((h.get("he_form") or "").strip() for h in p.get("he_words") or []):
            continue
        p["kind"] = "gk_add"
        p["he"] = ""
        p["he_unicode"] = ""
        p["he_stem_unicode"] = ""
        p["prefixes"] = ""
        p["he_words"] = [
            {
                "raw": "GKADD",
                "gr_word": gr,
                "gr_source": "patch_lxx",
                "es_source": "patch_meta",
            }
        ]
        fixes.append(f"{ch}:{vn} pair[{pi}] pron→gk_add ({gr})")
    return fixes


def _ordered_missing_tokens(verse: dict, lxx_surface: list[str]) -> list[str]:
    data_norm = verse_data_gr_tokens(verse)
    lxx_norm = [_norm_gr(w) for w in lxx_surface if _norm_gr(w)]
    missing = list((Counter(lxx_norm) - Counter(data_norm)).elements())
    if not missing:
        return []
    ordered: list[str] = []
    mc = Counter(missing)
    for w in lxx_surface:
        n = _norm_gr(w)
        if mc.get(n, 0) > 0:
            ordered.append(_san_gr(w))
            mc[n] -= 1
    return ordered


def _append_gk_add(verse: dict, phrase: str, gr_source: str = "patch_lxx_remainder") -> None:
    verse.setdefault("pairs", []).append(
        {
            "kind": "gk_add",
            "he": "",
            "he_unicode": "",
            "he_stem_unicode": "",
            "gr_unicode": phrase,
            "gr": "",
            "he_words": [
                {
                    "raw": "GKADD",
                    "gr_word": phrase,
                    "gr_source": gr_source,
                    "es_source": "patch_meta",
                }
            ],
        }
    )


def inject_lxx_remainder(
    verse: dict,
    lxx_surface: list[str],
    *,
    max_chunk: int = 12,
    max_passes: int = 4,
) -> list[str]:
    """Inyecta gk_add con todos los tokens Rahlfs aún faltantes (en colas ≤max_chunk)."""
    fixes: list[str] = []
    ch, vn = verse.get("chapter"), verse.get("verse")
    for _ in range(max_passes):
        ordered = _ordered_missing_tokens(verse, lxx_surface)
        if not ordered:
            break
        chunk = ordered[:max_chunk]
        phrase = " ".join(chunk)
        is_kainan = any(_norm_gr(w) == "καιναν" for w in chunk)
        src = "patch_lxx_variant" if is_kainan else "patch_lxx_remainder"
        _append_gk_add(verse, phrase, gr_source=src)
        fixes.append(
            f"{ch}:{vn} +gk_add remainder ({len(chunk)} tok: {phrase[:55]}{'…' if len(phrase) > 55 else ''})"
        )
    return fixes


def inject_missing_lxx_gk_add(verse: dict, lxx_surface: list[str]) -> list[str]:
    """Alias conservador — delega en inject_lxx_remainder (colas cortas primero)."""
    return inject_lxx_remainder(verse, lxx_surface, max_chunk=6, max_passes=2)


def remove_oversized_gk_add(verse: dict, max_tokens: int = 6) -> list[str]:
    """Elimina gk_add batch con cola LXX demasiado larga (variante vs CATSS)."""
    fixes: list[str] = []
    ch, vn = verse.get("chapter"), verse.get("verse")
    kept: list[dict] = []
    for pi, p in enumerate(verse.get("pairs", [])):
        if p.get("kind") != "gk_add":
            kept.append(p)
            continue
        gr = (p.get("gr_unicode") or "").strip()
        n = len(gr.split()) if gr else 0
        src = "patch_lxx"
        hws = p.get("he_words") or []
        if hws:
            src = hws[0].get("gr_source") or "patch_lxx"
        if src in ("patch_lxx_word_only", "patch_lxx_variant", "patch_lxx_remainder"):
            kept.append(p)
            continue
        if n > max_tokens and src == "patch_lxx":
            # Bloques LXX completos sin hebreo — _fix_lxx_align retag a patch_lxx
            if not (p.get("he_unicode") or "").strip() and not any(
                (hw.get("he_form") or "").strip() for hw in hws if not _is_meta_hw(hw)
            ):
                kept.append(p)
                continue
            fixes.append(f"{ch}:{vn} drop gk_add[{pi}] ({n} tok)")
            continue
        kept.append(p)
    if len(kept) != len(verse.get("pairs", [])):
        verse["pairs"] = kept
    return fixes


def trim_gk_add_extra_tokens(verse: dict, lxx_surface: list[str]) -> list[str]:
    """Recorta tokens sobrantes en gk_add (p. ej. μετ᾿ duplicado en 12:4)."""
    fixes: list[str] = []
    ch, vn = verse.get("chapter"), verse.get("verse")
    data_norm = verse_data_gr_tokens(verse)
    lxx_norm = [_norm_gr(w) for w in lxx_surface if _norm_gr(w)]
    extra = Counter(data_norm) - Counter(lxx_norm)
    if not extra:
        return fixes

    for pi, p in enumerate(verse.get("pairs", [])):
        if p.get("kind") != "gk_add":
            continue
        gr = (p.get("gr_unicode") or "").strip()
        if not gr:
            continue
        words = gr.split()
        new_words: list[str] = []
        trimmed = False
        extra_work = Counter(extra)
        for w in words:
            n = _norm_gr(w)
            if n and extra_work.get(n, 0) > 0:
                extra_work[n] -= 1
                trimmed = True
                continue
            new_words.append(w)
        if trimmed and new_words:
            new_gr = " ".join(_san_gr(w) for w in new_words)
            p["gr_unicode"] = new_gr
            for hw in p.get("he_words") or []:
                if (hw.get("raw") or "") in ("GKADD", "=<LXX>"):
                    hw["gr_word"] = new_gr
            fixes.append(f"{ch}:{vn} trim gk_add[{pi}] → ({new_gr[:40]})")
            # recalc extra after trim
            data_norm = verse_data_gr_tokens(verse)
            extra = Counter(data_norm) - Counter(lxx_norm)
            if not extra:
                break
    return fixes


def fix_verse(verse: dict, lxx_surface: list[str], *, inject: bool = True) -> list[str]:
    fixes: list[str] = []
    fixes.extend(remove_oversized_gk_add(verse))
    fixes.extend(inject_lxx_word_only_verse(verse, lxx_surface))
    fixes.extend(dedupe_identical_gk_add(verse, lxx_surface))
    promote_gkadd_stubs(verse)
    promote_pronoun_stubs(verse)
    _fix_lxx_align_verse(verse)
    fixes.extend(promote_gkadd_stubs(verse))
    fixes.extend(promote_pronoun_stubs(verse))
    if inject:
        fixes.extend(inject_lxx_remainder(verse, lxx_surface))
    fixes.extend(trim_gk_add_extra_tokens(verse, lxx_surface))
    fixes.extend(dedupe_identical_gk_add(verse, lxx_surface))
    _fix_lxx_align_verse(verse)
    return fixes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chapters", default="8-14", help="e.g. 8-14 or 8,9,10")
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "genesis_final.json")
    ap.add_argument("--no-inject", action="store_true", help="omitir cola Rahlfs gk_add")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if "-" in args.chapters:
        a, b = args.chapters.split("-", 1)
        chapters = list(range(int(a), int(b) + 1))
    else:
        chapters = [int(x) for x in args.chapters.split(",")]

    data = json.loads(args.data.read_text(encoding="utf-8"))
    all_fixes: list[str] = []

    for ch in chapters:
        lxx_v = load_lxx(ch)
        for verse in data.get("verses", []):
            if verse.get("chapter") != ch:
                continue
            vn = str(verse.get("verse"))
            surface = [w.get("w", "") for w in lxx_v.get(vn, [])]
            all_fixes.extend(fix_verse(verse, surface, inject=not args.no_inject))

    print(f"fixes={len(all_fixes)}")
    for f in all_fixes[:80]:
        print(f"  {f}")
    if len(all_fixes) > 80:
        print(f"  ... +{len(all_fixes) - 80} más")

    if not args.dry_run and all_fixes:
        args.data.write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        print(f"saved {args.data}")


if __name__ == "__main__":
    main()
