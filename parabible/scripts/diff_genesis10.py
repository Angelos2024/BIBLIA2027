#!/usr/bin/env python3
"""Cruza BHSA local (Parabible) con genesis_final.json — Génesis 10."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

TRAD_ROOT = Path(__file__).resolve().parent.parent.parent
PARABIBLE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TRAD_ROOT / "scripts"))

from audit_gen5_struct import align_oshb, flatten_verse, norm_he  # noqa: E402
from audit_gen6_struct import expand_fused_ot_he_data  # noqa: E402

DEFAULT_DATA = TRAD_ROOT / "data" / "genesis_final.json"
DEFAULT_BHSA = PARABIBLE_ROOT / "genesis" / "10" / "bhsa_words.json"
DEFAULT_OUT = PARABIBLE_ROOT / "genesis" / "10"

def morph_compatible(bhsa_pos: str | None, he_morph: str | None) -> bool | None:
    """True/False si hay conflicto real; None = no comparar."""
    if not bhsa_pos or not he_morph:
        return None
    bp = bhsa_pos.lower()
    hm = he_morph.upper()

    if bp == "nmpr":
        return "NPROP" in hm or "N.PROPER" in hm or "PROPER" in hm
    if bp in ("noun", "subs"):
        return hm.startswith("SUBS") or hm.startswith("N.")
    if bp == "adjv":
        return "ADJ" in hm
    if bp == "verb":
        return hm.startswith("VERBO") or hm.startswith("V.")
    if bp == "art":
        return hm == "ART" or hm.startswith("ART")
    if bp == "prep":
        # BHSA etiqueta את como prep; nuestro pipeline usa PART.OBJ.DIR
        if "PART.OBJ.DIR" in hm:
            return True
        return hm.startswith("PREP")
    if bp == "conj":
        return hm.startswith("CONJ")
    if bp == "prde":
        return "PRON.DEM" in hm or "PRDE" in hm or "PRON" in hm
    return None


def flatten_verse_meta(v: dict) -> list[dict]:
    """Tokens hebreos del JSON del proyecto con metadatos por slot."""
    rows: list[dict] = []
    for pi, p in enumerate(v.get("pairs", [])):
        kind = p.get("kind") or "align"
        if kind in ("gk_add", "heb_omit"):
            continue
        for hi, hw in enumerate(p.get("he_words", [])):
            raw = hw.get("raw") or ""
            pfx_f = hw.get("prefix_forms") or []
            pfx_m = hw.get("prefix_morphs") or []
            for i, pf in enumerate(pfx_f):
                rows.append(
                    {
                        "he": pf,
                        "he_norm": norm_he(pf),
                        "morph": pfx_m[i] if i < len(pfx_m) else "?",
                        "slot": f"prefix[{i}]",
                        "pair": pi,
                        "hw": hi,
                        "raw": raw,
                        "strongs": hw.get("strongs") or "",
                        "es": "",
                        "slot_kind": "prefix",
                    }
                )
            stem = (hw.get("he_form") or "").strip()
            if stem:
                rows.append(
                    {
                        "he": stem,
                        "he_norm": norm_he(stem),
                        "morph": hw.get("he_morph") or "?",
                        "slot": "stem",
                        "pair": pi,
                        "hw": hi,
                        "raw": raw,
                        "strongs": hw.get("strongs") or "",
                        "es": (hw.get("es") or "").strip(),
                        "slot_kind": "stem",
                    }
                )
            ps = hw.get("prs_suffix") or {}
            if ps.get("he_form"):
                rows.append(
                    {
                        "he": ps["he_form"],
                        "he_norm": norm_he(ps["he_form"]),
                        "morph": ps.get("he_morph") or "PRS",
                        "slot": "prs_suffix",
                        "pair": pi,
                        "hw": hi,
                        "raw": raw,
                        "strongs": "",
                        "es": (ps.get("es") or "").strip(),
                        "slot_kind": "prs_suffix",
                    }
                )
    return rows


def expand_data_tokens(meta_rows: list[dict]) -> list[dict]:
    """Aplica expand_fused_ot_he_data conservando metadatos alineables."""
    flat = [
        (r["he"], r["morph"], r["slot"], r["pair"], r["hw"], r["raw"])
        for r in meta_rows
    ]
    expanded_he = expand_fused_ot_he_data(flat)
    # Reconstruir filas expandidas (את+PRS → 2 tokens; copia meta del stem)
    out: list[dict] = []
    mi = 0
    expand_map = {
        "אתו": ["את", "ו"],
        "אתם": ["את", "ם"],
        "אתה": ["את", "ה"],
        "אתנו": ["את", "נו"],
    }
    for row in meta_rows:
        nh = row["he_norm"]
        if not nh:
            continue
        morph = row["morph"] or ""
        if (
            nh in expand_map
            and "PART.OBJ.DIR" in morph
            and "PRON" not in morph
            and row["slot"] == "stem"
        ):
            for piece in expand_map[nh]:
                out.append({**row, "he_norm": piece, "he": piece, "expanded_from": nh})
        elif row["raw"] == "**)HL/W" and row["slot"] == "stem":
            out.append({**row, "he_norm": "אהל", "he": "אהל"})
            out.append({**row, "he_norm": "ה", "he": "ה", "slot": "prs_suffix"})
        else:
            out.append(row)
        mi += 1
    # Si expand_fused cambió conteo, preferir secuencia canónica del helper
    if [r["he_norm"] for r in out] != expanded_he:
        # fallback: tokens sin meta extra
        out = [{"he_norm": h, "he": h, "morph": "?", "slot": "?"} for h in expanded_he]
    return out


def bhsa_by_verse(bhsa_words: list[dict]) -> dict[int, list[dict]]:
    by_v: dict[int, list[dict]] = defaultdict(list)
    for w in bhsa_words:
        by_v[int(w["verse"])].append(w)
    return dict(by_v)


def compare_verse(
    ref: str,
    data_tokens: list[dict],
    bhsa_tokens: list[dict],
) -> dict:
    data_he = [t["he_norm"] for t in data_tokens if t.get("he_norm")]
    bhsa_he = [norm_he(w.get("text") or "") for w in bhsa_tokens]

    diff = align_oshb(data_he, bhsa_he)
    morph_flags: list[dict] = []

    # Comparar morfología/gloss donde el alineador marca match implícito
    paired = min(len(data_he), len(bhsa_he))
    for i in range(paired):
        if data_he[i] == bhsa_he[i]:
            dt = data_tokens[i] if i < len(data_tokens) else {}
            bt = bhsa_tokens[i]
            bpos = bt.get("part_of_speech")
            hm = dt.get("morph")
            ok = morph_compatible(bpos, hm)
            if ok is False:
                morph_flags.append(
                    {
                        "idx": i,
                        "he": data_he[i],
                        "data_morph": hm,
                        "bhsa_pos": bpos,
                        "bhsa_gloss": bt.get("gloss"),
                        "data_es": dt.get("es"),
                        "data_strongs": dt.get("strongs"),
                        "bhsa_lexeme": bt.get("lexeme"),
                    }
                )

    return {
        "ref": ref,
        "data_count": len(data_he),
        "bhsa_count": len(bhsa_he),
        "count_match": len(data_he) == len(bhsa_he),
        "token_diffs": diff,
        "morph_mismatches": morph_flags,
        "data_he": data_he,
        "bhsa_he": bhsa_he,
        "bhsa_glosses": [w.get("gloss") for w in bhsa_tokens],
    }


def render_markdown(results: list[dict], summary: dict) -> str:
    lines = [
        "# Génesis 10 — diff genesis_final vs BHSA (local)",
        "",
        f"- Versos analizados: **{summary['verse_count']}**",
        f"- Versos con diff de conteo: **{summary['verses_count_mismatch']}**",
        f"- Versos con diff de tokens (alineación): **{summary['verses_token_diff']}**",
        f"- Versos idénticos (conteo + tokens): **{summary['verses_clean']}**",
        f"- Flags morfología (posible): **{summary['morph_flags']}**",
        "",
        "## Versos con incidencias",
        "",
    ]

    for r in results:
        structural = not r["count_match"] or r["token_diffs"]
        morph_only = r["morph_mismatches"] and not structural
        if not structural and not morph_only:
            continue
        lines.append(f"### {r['ref']} — data={r['data_count']} bhsa={r['bhsa_count']}")
        if not r["count_match"]:
            lines.append("- **Conteo distinto**")
        for d in r["token_diffs"][:20]:
            t = d["type"]
            if t == "faltante_data":
                lines.append(f"- FALTA en data [{d['oshb_idx']}]: `{d['oshb']}` (BHSA)")
            elif t == "extra_data":
                lines.append(f"- SOBRA en data [{d['data_idx']}]: `{d['data']}`")
            else:
                lines.append(
                    f"- DESAL [{d.get('data_idx')}] `{d['data']}` vs "
                    f"[{d.get('oshb_idx')}] `{d['oshb']}`"
                )
        if len(r["token_diffs"]) > 20:
            lines.append(f"- … +{len(r['token_diffs']) - 20} diffs")
        if morph_only:
            lines.append("- _Tokens alineados; posibles conflictos morfológicos:_")
        for m in r["morph_mismatches"][:8]:
            lines.append(
                f"- MORPH [{m['idx']}] `{m['he']}`: "
                f"data={m['data_morph']!r} bhsa={m['bhsa_pos']!r} "
                f"gloss={m['bhsa_gloss']!r}"
            )
        lines.append("")

    if summary["verses_clean"] == summary["verse_count"]:
        lines.append("_Sin incidencias estructurales — conteo y tokens coinciden en todos los versos._")

    return "\n".join(lines)


def run_diff(
    data_path: Path,
    bhsa_path: Path,
    out_dir: Path,
    chapter: int = 10,
) -> dict:
    data = json.loads(data_path.read_text(encoding="utf-8"))
    bhsa_words = json.loads(bhsa_path.read_text(encoding="utf-8"))
    bhsa_map = bhsa_by_verse(bhsa_words)

    verses = sorted(
        (v for v in data.get("verses", []) if v.get("chapter") == chapter),
        key=lambda v: int(v.get("verse") or 0),
    )
    if not verses:
        raise RuntimeError(f"Sin versos capítulo {chapter} en {data_path}")

    results: list[dict] = []
    for v in verses:
        vn = int(v["verse"])
        ref = f"{chapter}:{vn}"
        meta = flatten_verse_meta(v)
        data_tokens = expand_data_tokens(meta)
        bhsa_tokens = bhsa_map.get(vn, [])
        results.append(compare_verse(ref, data_tokens, bhsa_tokens))

    summary = {
        "chapter": chapter,
        "verse_count": len(results),
        "data_source": str(data_path),
        "bhsa_source": str(bhsa_path),
        "verses_count_mismatch": sum(1 for r in results if not r["count_match"]),
        "verses_token_diff": sum(1 for r in results if r["token_diffs"]),
        "verses_clean": sum(
            1
            for r in results
            if r["count_match"] and not r["token_diffs"]
        ),
        "morph_flags": sum(len(r["morph_mismatches"]) for r in results),
        "token_diff_types": dict(
            Counter(d["type"] for r in results for d in r["token_diffs"])
        ),
        "verses_with_issues": [
            r["ref"]
            for r in results
            if not r["count_match"] or r["token_diffs"] or r["morph_mismatches"]
        ],
        "verses_structural_issues": [
            r["ref"] for r in results if not r["count_match"] or r["token_diffs"]
        ],
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "diff_summary.json"
    details_path = out_dir / "diff_details.json"
    md_path = out_dir / "diff_report.md"

    # details sin repetir listas largas en summary
    details = []
    for r in results:
        details.append(
            {
                k: v
                for k, v in r.items()
                if k not in ("data_he", "bhsa_he", "bhsa_glosses")
            }
        )

    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    details_path.write_text(
        json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md_path.write_text(render_markdown(results, summary), encoding="utf-8")

    print(f"written {summary_path}")
    print(f"written {details_path}")
    print(f"written {md_path}")
    print(
        f"versos={summary['verse_count']} "
        f"clean={summary['verses_clean']} "
        f"count_mismatch={summary['verses_count_mismatch']} "
        f"token_diff={summary['verses_token_diff']} "
        f"morph_flags={summary['morph_flags']}"
    )
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Diff genesis_final vs BHSA (local)")
    ap.add_argument("--chapter", type=int, default=10)
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA)
    ap.add_argument("--bhsa", type=Path, default=DEFAULT_BHSA)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    run_diff(args.data, args.bhsa, args.out, args.chapter)


if __name__ == "__main__":
    main()
