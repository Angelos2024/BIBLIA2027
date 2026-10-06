#!/usr/bin/env python3
"""Verifica griego LXX (mlxx + Rahlfs) vs genesis_final — detalle por verso (B8)."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from audit_gen_chapter_lxx import _gather_assigned, _norm_gr, _tokens_from_phrase

MLXX = ROOT / "01.Gen.1.mlxx"
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


def lxx_dir() -> Path:
    env = os.environ.get("LXX_GEN_DIR")
    if env:
        return Path(env)
    return DEFAULT_LXX


def parse_mlxx_verse(text: str, chapter: int, verse: int) -> list[dict]:
    ref = f"Gen {chapter}:{verse}"
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == ref:
            start = i + 1
            break
    if start is None:
        return []
    out: list[dict] = []
    for line in lines[start:]:
        if re.match(r"^Gen \d+:\d+", line.strip()):
            break
        parts = line.split()
        if len(parts) < 4:
            continue
        form, pos, morph, lemma = parts[0], parts[1], parts[2], parts[3]
        out.append({"form_ascii": form, "pos": pos, "morph": morph, "lemma": lemma})
    return out


def load_verse(data_path: Path, chapter: int, verse: int) -> dict:
    data = json.loads(data_path.read_text(encoding="utf-8"))
    return next(
        v for v in data["verses"] if v.get("chapter") == chapter and v.get("verse") == verse
    )


def analyze(data_path: Path, chapter: int, verse: int) -> dict:
    v = load_verse(data_path, chapter, verse)
    mlxx_words = parse_mlxx_verse(MLXX.read_text(encoding="utf-8"), chapter, verse)

    lxx_path = lxx_dir() / f"{chapter}.json"
    lxx_words: list[str] = []
    if lxx_path.exists():
        lxx = json.loads(lxx_path.read_text(encoding="utf-8"))
        lxx_words = [w["w"] for w in lxx["verses"].get(str(verse), [])]

    pair_tokens: list[dict] = []
    all_gr: list[str] = []
    issues: list[dict] = []

    for pi, p in enumerate(v.get("pairs", [])):
        kind = p.get("kind", "align")
        gr = (p.get("gr_unicode") or "").strip()
        toks = _tokens_from_phrase(gr)
        all_gr.extend(toks)
        assigned = [a[0] for a in _gather_assigned(p)]
        he = (p.get("he_unicode") or "").strip()
        hw_empty = all(
            not (hw.get("he_form") or "").strip() for hw in p.get("he_words") or []
        )
        gkadd_stub = any(
            (hw.get("raw") or "") in ("GKADD", "=<LXX>") for hw in p.get("he_words") or []
        )

        pair_tokens.append(
            {
                "pair": pi,
                "kind": kind,
                "he": he or "—",
                "gr_unicode": gr,
                "tokens": toks,
                "assigned": assigned,
            }
        )

        if gr and kind != "gk_add" and (hw_empty or gkadd_stub):
            issues.append(
                {
                    "type": "greek_hidden",
                    "pair": pi,
                    "gr": gr,
                    "detail": "Griego en align con he_words vacío — debería ser gk_add",
                }
            )

    from collections import Counter

    lxx_norm = [_norm_gr(w) for w in lxx_words]
    missing = list(Counter(lxx_norm) - Counter(all_gr))
    for m in missing:
        issues.append(
            {"type": "missing_in_data", "token": m, "detail": "En Rahlfs, no en gr_unicode"}
        )

    return {
        "ref": f"{chapter}:{verse}",
        "lxx_rahlf_words": lxx_words,
        "lxx_token_count": len(lxx_words),
        "mlxx_morph_count": len(mlxx_words),
        "genesis_pair_count": len(v.get("pairs", [])),
        "genesis_gr_token_count": len(all_gr),
        "pairs": pair_tokens,
        "missing_lxx_tokens": missing,
        "issues": issues,
    }


def render_md(report: dict) -> str:
    lines = [
        f"# Verificación LXX — Gén {report['ref']}",
        "",
        f"- Palabras LXX Rahlfs: **{report['lxx_token_count']}**",
        f"- Morfemas mlxx: **{report['mlxx_morph_count']}**",
        f"- Pares genesis_final: **{report['genesis_pair_count']}**",
        f"- Tokens griegos en pares: **{report['genesis_gr_token_count']}**",
    ]
    if report["genesis_pair_count"] != report["lxx_token_count"]:
        lines.append(
            f"- Nota: {report['lxx_token_count']} palabras LXX vs "
            f"{report['genesis_pair_count']} pares (varias palabras griegas por par hebreo)."
        )
    if report["mlxx_morph_count"] != report["lxx_token_count"]:
        lines.append(
            f"- Nota mlxx: {report['mlxx_morph_count']} morfemas vs "
            f"{report['lxx_token_count']} palabras Rahlfs (partículas pueden ir implícitas)."
        )
    lines.extend(
        [
            "",
            "## Texto LXX (Rahlfs)",
            "",
            " ".join(report["lxx_rahlf_words"]),
            "",
            "## Pares",
            "",
            "| # | kind | hebreo | gr_unicode | tokens |",
            "|---|------|--------|------------|--------|",
        ]
    )
    for p in report["pairs"]:
        lines.append(
            f"| {p['pair']} | {p['kind']} | {p['he'][:20]} | {p['gr_unicode'][:40]} | {len(p['tokens'])} |"
        )
    if report["issues"]:
        lines.extend(["", "## Incidencias", ""])
        for i in report["issues"]:
            lines.append(
                f"- **{i['type']}** (par {i.get('pair', '—')}): "
                f"{i.get('gr') or i.get('token', '')} — {i['detail']}"
            )
    else:
        lines.extend(["", "_Sin incidencias._"])
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Verificación LXX verso (Rahlfs + mlxx)")
    ap.add_argument("chapter", type=int)
    ap.add_argument("verse", type=int)
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "genesis_final.json")
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Markdown de salida (default: scripts/audit_genN_VV_lxx_detail.md)",
    )
    args = ap.parse_args()
    out = args.out or SCRIPTS / f"audit_gen{args.chapter}_{args.verse}_lxx_detail.md"
    report = analyze(args.data, args.chapter, args.verse)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_md(report), encoding="utf-8")
    out.with_suffix(".json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"written {out}")
    print(
        f"issues={len(report['issues'])} lxx={report['lxx_token_count']} "
        f"gr_in_data={report['genesis_gr_token_count']}"
    )
    if report["issues"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
