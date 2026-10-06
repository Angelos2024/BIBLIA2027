"""Auditoría LXX por capítulo — cobertura y reparto morfema a morfema (B8).

Comprueba que todas las palabras griegas del verso (CATSS `gr_unicode` en pares
`align` + pares `gk_add`) queden asignadas en `prefix_gr`, `gr_word` o
`prs_suffix.gr_word`, sin deformaciones ni cortes mal posicionados cuando hay
2+ palabras en un par.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata as ud
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent

_GR_PUNCT = ".,·;:·;«»“”\"'()[]᾿΄ʼ"
_ELISION_GR = {"μεθ": "μετ", "μεθ᾿": "μετ", "εφ": "επ", "εφ᾿": "επ"}


def _norm_gr(s: str) -> str:
    if not s:
        return ""
    s = s.strip().strip(_GR_PUNCT)
    if not s or s in ("---", "—", "–", "-", "?"):
        return ""
    s = ud.normalize("NFD", s)
    s = "".join(c for c in s if ud.category(c) != "Mn")
    s = s.lower().strip(_GR_PUNCT)
    return _ELISION_GR.get(s, s)


_HEB_IN_GR = re.compile(r"[\u05D0-\u05EA]")
_META_RAW = ("=", "{", "<", "*", "--", ".$")


def _tokens_from_phrase(phrase: str) -> list[str]:
    out: list[str] = []
    for raw in (phrase or "").split():
        n = _norm_gr(raw)
        if n:
            out.append(n)
    return out


def _gather_assigned(pair: dict) -> list[tuple[str, str, int, int, str]]:
    """Lista ordenada (token_norm, slot_label, pair_idx, hw_idx, raw_gr)."""
    rows: list[tuple[str, str, int, int, str]] = []
    for hi, hw in enumerate(pair.get("he_words") or []):
        raw_id = hw.get("raw") or ""
        for ki, pg in enumerate(hw.get("prefix_gr") or []):
            for tok in _tokens_from_phrase(pg):
                rows.append((tok, f"prefix[{ki}]", hi, ki, pg))
        for tok in _tokens_from_phrase(hw.get("gr_word") or ""):
            rows.append((tok, "stem", hi, -1, hw.get("gr_word") or ""))
        prs = hw.get("prs_suffix") or {}
        if isinstance(prs, dict):
            for tok in _tokens_from_phrase(prs.get("gr_word") or ""):
                rows.append((tok, "prs", hi, -1, prs.get("gr_word") or ""))
        _ = raw_id
    return rows


def _gather_assigned_set(pair: dict) -> Counter[str]:
    c: Counter[str] = Counter()
    for tok, *_ in _gather_assigned(pair):
        c[tok] += 1
    return c


def _pair_source_tokens(pair: dict) -> Counter[str]:
    gr = (pair.get("gr_unicode") or "").strip()
    return Counter(_tokens_from_phrase(gr))


def _has_hebrew_in_greek(s: str) -> bool:
    return bool(s and _HEB_IN_GR.search(s))


def _scan_greek_deform(pair: dict, ref: str, pi: int) -> list[dict]:
    issues: list[dict] = []
    fields: list[tuple[str, str]] = []
    if pair.get("gr_unicode"):
        fields.append(("pair.gr_unicode", pair["gr_unicode"]))
    for hi, hw in enumerate(pair.get("he_words") or []):
        if hw.get("gr_word"):
            fields.append((f"p{pi} h{hi} gr_word", hw["gr_word"]))
        for ki, pg in enumerate(hw.get("prefix_gr") or []):
            if pg:
                fields.append((f"p{pi} h{hi} prefix_gr[{ki}]", pg))
        prs = hw.get("prs_suffix") or {}
        if isinstance(prs, dict) and prs.get("gr_word"):
            fields.append((f"p{pi} h{hi} prs.gr_word", prs["gr_word"]))
    for label, val in fields:
        if _has_hebrew_in_greek(val):
            issues.append({
                "ref": ref, "pair": pi, "type": "gr_deformado_he",
                "detail": f"{label}={val!r}",
            })
    return issues


def _check_multi_word_split(pair: dict, ref: str, pi: int) -> list[dict]:
    """Si gr_unicode tiene 2+ palabras y hay 2+ he_words, detecta dump en un solo slot."""
    issues: list[dict] = []
    src = _tokens_from_phrase(pair.get("gr_unicode") or "")
    if len(src) < 2:
        return issues
    hws = pair.get("he_words") or []
    if len(hws) < 2:
        return issues
    if pair.get("kind") in ("gk_add", "heb_omit"):
        return issues

    slots_with_gr = []
    for hi, hw in enumerate(hws):
        raw = hw.get("raw") or ""
        if raw.startswith(_META_RAW):
            continue
        n_pfx = sum(len(_tokens_from_phrase(x)) for x in (hw.get("prefix_gr") or []))
        n_stem = len(_tokens_from_phrase(hw.get("gr_word") or ""))
        n_prs = 0
        prs = hw.get("prs_suffix") or {}
        if isinstance(prs, dict):
            n_prs = len(_tokens_from_phrase(prs.get("gr_word") or ""))
        total = n_pfx + n_stem + n_prs
        if total:
            slots_with_gr.append((hi, raw, total, hw.get("gr_word") or ""))

    if len(slots_with_gr) == 1 and slots_with_gr[0][2] >= 2 and len(hws) >= 2:
        # Si el par ya cubre todos los tokens de gr_unicode, no marcar mal_partido
        # (p. ej. γυνὴ+αὐτοῦ en h0 y PRON hebreo sin LXX en h1).
        assigned = _gather_assigned_set(pair)
        src_cnt = _pair_source_tokens(pair)
        if all(assigned.get(tok, 0) >= need for tok, need in src_cnt.items()):
            return issues
        hi, raw, cnt, gw = slots_with_gr[0]
        others = [
            h for hj, h in enumerate(hws)
            if hj != hi and not (h.get("raw") or "").startswith(_META_RAW)
        ]
        others_empty = all(
            not _tokens_from_phrase(h.get("gr_word") or "")
            and not any(_tokens_from_phrase(x) for x in (h.get("prefix_gr") or []))
            for h in others
        )
        only_obj_markers = others_empty and all(
            (h.get("he_morph") or "") == "PART.OBJ.DIR" for h in others
        )
        if others_empty and not only_obj_markers and cnt >= len(src):
            issues.append({
                "ref": ref, "pair": pi, "type": "gr_mal_partido",
                "detail": (
                    f"gr_unicode={pair.get('gr_unicode')!r} → todo en h{hi} "
                    f"raw={raw!r} gr_word={gw!r}; {len(hws)} he_words"
                ),
            })
    return issues


def audit_pair(pair: dict, ref: str, pi: int) -> list[dict]:
    issues: list[dict] = []
    kind = pair.get("kind") or "align"

    if kind == "gk_add":
        if not (pair.get("gr_unicode") or "").strip():
            issues.append({
                "ref": ref, "pair": pi, "type": "gk_add_vacio",
                "detail": "gk_add sin gr_unicode",
            })
        return issues

    if kind == "heb_omit":
        return issues

    src = _pair_source_tokens(pair)
    if not src:
        return issues

    assigned = _gather_assigned_set(pair)
    for tok, need in src.items():
        have = assigned.get(tok, 0)
        if have < need:
            issues.append({
                "ref": ref, "pair": pi, "type": "gr_huerfano",
                "detail": f"falta {need - have}× {tok!r} en morfemas "
                f"(gr_unicode={pair.get('gr_unicode')!r})",
            })
    for tok, extra in assigned.items():
        need = src.get(tok, 0)
        if assigned[tok] > need:
            issues.append({
                "ref": ref, "pair": pi, "type": "gr_sobra",
                "detail": f"sobra {assigned[tok] - need}× {tok!r} asignado "
                f"(gr_unicode={pair.get('gr_unicode')!r})",
            })

    issues.extend(_scan_greek_deform(pair, ref, pi))
    issues.extend(_check_multi_word_split(pair, ref, pi))
    return issues


def audit_verse(v: dict) -> tuple[list[dict], str, str]:
    ch = v.get("chapter")
    vn = v.get("verse")
    ref = f"{ch}:{vn}"
    issues: list[dict] = []
    verse_src: Counter[str] = Counter()
    verse_assigned: Counter[str] = Counter()

    for pi, pair in enumerate(v.get("pairs") or []):
        kind = pair.get("kind") or "align"
        if kind == "gk_add":
            verse_src.update(_pair_source_tokens(pair))
            verse_assigned.update(_gather_assigned_set(pair))
        elif kind != "heb_omit":
            verse_src.update(_pair_source_tokens(pair))
            verse_assigned.update(_gather_assigned_set(pair))
        issues.extend(audit_pair(pair, ref, pi))

    for tok, need in verse_src.items():
        have = verse_assigned.get(tok, 0)
        if have < need:
            issues.append({
                "ref": ref, "pair": -1, "type": "verso_gr_incompleto",
                "detail": f"falta {need - have}× {tok!r} a nivel verso",
            })

    src_phrase = " ".join(
        (p.get("gr_unicode") or "").strip()
        for p in v.get("pairs", [])
        if (p.get("gr_unicode") or "").strip()
    )
    assigned_phrase = " ".join(
        t[4] for p in v.get("pairs", [])
        for t in _gather_assigned(p)
    )
    return issues, src_phrase, assigned_phrase


def audit_chapter(data: dict, chapter: int) -> tuple[list[str], int, int, Counter]:
    by_type: Counter[str] = Counter()
    verses_with_issues: list[str] = []
    lines = [f"# Gén {chapter} — auditoría LXX (B8)\n"]
    all_issues: list[dict] = []

    versos = sorted(
        (v for v in data.get("verses", []) if v.get("chapter") == chapter),
        key=lambda v: int(v.get("verse") or 0),
    )

    for v in versos:
        ref = f"{chapter}:{v.get('verse')}"
        issues, src, _ = audit_verse(v)
        if issues:
            verses_with_issues.append(ref)
            all_issues.extend(issues)
            lines.append(f"\n## {ref}")
            lines.append(f"  LXX par: {src[:120]}{'…' if len(src) > 120 else ''}")
            for iss in issues[:10]:
                by_type[iss["type"]] += 1
                lines.append(f"  [{iss['type']}] p{iss['pair']}: {iss['detail']}")
            if len(issues) > 10:
                lines.append(f"  ... +{len(issues) - 10} más")

    for iss in all_issues:
        by_type[iss["type"]] += 0  # ensure keys

    lines.insert(1, f"Versículos con incidencia LXX: {len(verses_with_issues)}/{len(versos)}")
    lines.insert(2, f"Total incidencias: {len(all_issues)} — {dict(by_type)}")

    return lines, len(verses_with_issues), len(all_issues), by_type


def main() -> None:
    ap = argparse.ArgumentParser(description="Auditoría LXX posicionada — capítulo Génesis (B8)")
    ap.add_argument("chapter", type=int)
    ap.add_argument(
        "--data",
        type=Path,
        default=ROOT / "data" / "genesis_final.json",
    )
    ap.add_argument("--verse", type=int, default=0, help="Detalle de un solo verso")
    args = ap.parse_args()

    data = json.loads(args.data.read_text(encoding="utf-8"))

    if args.verse:
        v = next(
            x for x in data["verses"]
            if x.get("chapter") == args.chapter and x.get("verse") == args.verse
        )
        issues, src, asn = audit_verse(v)
        print(f"=== {args.chapter}:{args.verse} ===")
        print(f"LXX pares: {src}")
        print(f"issues={len(issues)}")
        for iss in issues:
            print(f"  [{iss['type']}] p{iss['pair']}: {iss['detail']}")
        return

    lines, versos, total, by_type = audit_chapter(data, args.chapter)
    out = SCRIPTS / f"audit_gen{args.chapter}_lxx.txt"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"written {out}")
    print(f"versos_lxx={versos} incidencias={total}")
    if by_type:
        print(f"tipos={dict(by_type)}")


if __name__ == "__main__":
    main()
