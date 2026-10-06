"""Auditoría estructural hebreo vs OSHB — cualquier capítulo de Génesis."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent

from audit_gen5_struct import align_oshb, check_pfx_sfx, flatten_verse, norm_he
from audit_gen6_struct import expand_fused_ot_he_data
from book_config import resolve


def oshb_chapter_path(chapter: int) -> Path:
    book = resolve("genesis")
    return book.oshb_dir / f"{chapter}.json"


def audit_chapter_struct(data: dict, oshb: dict, chapter: int) -> tuple[list[str], int, int, int]:
    """Devuelve (líneas informe, versos_con_incidencia, total_pfx, total_token_diffs)."""
    all_pfx: list[dict] = []
    all_oshb: list[str] = []
    lines = [f"# Gén {chapter} — auditoría estructural hebreo vs OSHB\n"]
    max_vn = max(int(k) for k in oshb) if oshb else 0

    for vn in range(1, max_vn + 1):
        ref = f"{chapter}:{vn}"
        v = next(
            x for x in data["verses"]
            if x.get("chapter") == chapter and x.get("verse") == vn
        )
        oshb_v = oshb.get(str(vn), {})
        flat = flatten_verse(v)
        data_he = expand_fused_ot_he_data(flat)
        oshb_he = [norm_he(x) for x in oshb_v.get("forms", []) if norm_he(x)]
        pfx_issues = check_pfx_sfx(v, ref)
        all_pfx.extend(pfx_issues)
        diff = align_oshb(data_he, oshb_he)
        if diff or pfx_issues:
            all_oshb.append(ref)
            lines.append(f"\n## {ref}")
            lines.append(
                f"  data={len(data_he)} oshb={len(oshb_he)} pfx={len(pfx_issues)} diff={len(diff)}"
            )
            for d in diff[:12]:
                if d["type"] == "faltante_data":
                    lines.append(f"  FALTA [{d['oshb_idx']}]: {d['oshb']!r}")
                elif d["type"] == "extra_data":
                    lines.append(f"  SOBRA [{d['data_idx']}]: {d['data']!r}")
                else:
                    lines.append(
                        f"  DESAL [{d.get('data_idx')}] {d['data']!r} vs "
                        f"[{d.get('oshb_idx')}] {d['oshb']!r}"
                    )
            if len(diff) > 12:
                lines.append(f"  ... +{len(diff) - 12}")
            for pi in pfx_issues[:6]:
                lines.append(f"  PFX: {pi}")

    by_type = Counter(i["type"] for i in all_pfx)
    lines.insert(1, f"Versículos con diff OSHB: {len(all_oshb)}/{max_vn}")
    lines.insert(2, f"Issues prefijo/sufijo: {len(all_pfx)} — {dict(by_type)}")

    total_diffs = sum(
        len(
            align_oshb(
                expand_fused_ot_he_data(
                    flatten_verse(
                        next(
                            x for x in data["verses"]
                            if x.get("chapter") == chapter and x.get("verse") == vn
                        )
                    )
                ),
                [
                    norm_he(x)
                    for x in oshb.get(str(vn), {}).get("forms", [])
                    if norm_he(x)
                ],
            )
        )
        for vn in range(1, max_vn + 1)
    )
    return lines, len(all_oshb), len(all_pfx), total_diffs


def main() -> None:
    ap = argparse.ArgumentParser(description="Auditoría estructural capítulo vs OSHB")
    ap.add_argument("chapter", type=int, help="Número de capítulo (1-50)")
    ap.add_argument(
        "--data",
        type=Path,
        default=ROOT / "data" / "genesis_final.json",
    )
    args = ap.parse_args()

    oshb_path = oshb_chapter_path(args.chapter)
    if not oshb_path.exists():
        sys.stderr.write(f"No existe OSHB: {oshb_path}\n")
        sys.exit(1)

    data = json.loads(args.data.read_text(encoding="utf-8"))
    oshb = json.loads(oshb_path.read_text(encoding="utf-8"))
    lines, versos, pfx, diffs = audit_chapter_struct(data, oshb, args.chapter)

    out = SCRIPTS / f"audit_gen{args.chapter}_struct.txt"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"written {out}")
    print(f"versos={versos} pfx={pfx}")
    print(f"total_token_diffs={diffs}")


if __name__ == "__main__":
    main()
