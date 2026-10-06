"""Auditoría estructural Gén 6 vs OSHB — huecos, orden, prefijos/sufijos."""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "genesis_final.json"
OSHB = Path(
    r"C:\Users\pik_y\Documents\GitHub\Local-consults\estudio\angelos"
    r"\IdiomaORIGEN\oshb-morph\chapters\01_Génesis\6.json"
)
OUT = Path(__file__).resolve().parent

# Reutilizar helpers del cap. 5
from audit_gen5_struct import (
    align_oshb,
    check_pfx_sfx,
    expand_fused_ot_he,
    flatten_verse,
    norm_he,
)


def expand_fused_ot_he_data(flat: list[tuple]) -> list[str]:
    """Expand solo fusiones את+PRS (no el pronombre אתה)."""
    expand = {
        "אתו": ["את", "ו"],
        "אתם": ["את", "ם"],
        "אתה": ["את", "ה"],
        "אתנו": ["את", "נו"],
    }
    out: list[str] = []
    for he, morph, slot, _pi, _hi, raw in flat:
        if raw == "**)HL/W" and slot == "stem":
            out.extend(["אהל", "ה"])
        nh = norm_he(he)
        if not nh:
            continue
        if nh in expand and "PART.OBJ.DIR" in (morph or "") and "PRON" not in (morph or ""):
            out.extend(expand[nh])
        else:
            out.append(nh)
    return out


def main():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    oshb = json.loads(OSHB.read_text(encoding="utf-8"))

    all_pfx = []
    all_oshb = []
    lines = ["# Gén 6 — auditoría estructural hebreo vs OSHB\n"]

    for vn in range(1, 23):
        ref = f"6:{vn}"
        v = next(x for x in data["verses"] if x.get("chapter") == 6 and x.get("verse") == vn)
        oshb_v = oshb.get(str(vn), {})
        oforms = oshb_v.get("forms", [])
        omorphs = oshb_v.get("morphs", [])

        flat = flatten_verse(v)
        data_he = expand_fused_ot_he_data(flat)
        oshb_he = [norm_he(x) for x in oforms if norm_he(x)]

        pfx_issues = check_pfx_sfx(v, ref)
        all_pfx.extend(pfx_issues)

        diff = align_oshb(data_he, oshb_he)
        if diff or pfx_issues:
            lines.append(f"\n## {ref}")
            lines.append(
                f"  data={len(data_he)} oshb={len(oshb_he)} "
                f"pfx_issues={len(pfx_issues)} diff={len(diff)}"
            )
            if len(data_he) != len(oshb_he):
                lines.append(f"  **conteo distinto** data {len(data_he)} vs oshb {len(oshb_he)}")

        for d in diff[:12]:
            if d["type"] == "faltante_data":
                lines.append(f"  FALTA en data [{d['oshb_idx']}]: {d['oshb']!r}")
            elif d["type"] == "extra_data":
                lines.append(f"  SOBRA en data [{d['data_idx']}]: {d['data']!r}")
            else:
                lines.append(
                    f"  DESAL [{d.get('data_idx')}] data={d['data']!r} "
                    f"oshb[{d.get('oshb_idx')}]={d['oshb']!r}"
                )
        if len(diff) > 12:
            lines.append(f"  ... +{len(diff)-12} diffs")

        for iss in pfx_issues:
            lines.append(
                f"  [{iss['type']}] p{iss.get('pair')} h{iss.get('hw', '?')} "
                f"raw={iss.get('raw', '')!r} — {iss['detail']}"
            )

        if diff or pfx_issues:
            all_oshb.append(ref)
            lines.append("  secuencia data:")
            for he, morph, slot, pi, hi, raw in flat:
                nh = norm_he(he)
                if nh:
                    lines.append(f"    p{pi}h{hi} {slot} {nh} ({morph}) raw={raw!r}")
            lines.append("  secuencia oshb:")
            for k, (f, m) in enumerate(zip(oforms, omorphs)):
                lines.append(f"    [{k}] {norm_he(f)} ({m})")

    by_type = Counter(i["type"] for i in all_pfx)
    lines.insert(1, f"Versículos con diff OSHB: {len(all_oshb)}/22")
    lines.insert(2, f"Issues prefijo/sufijo: {len(all_pfx)} — {dict(by_type)}")

    out_path = OUT / "audit_gen6_struct.txt"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"written {out_path}")
    print(f"versos_problematicos={len(all_oshb)} pfx_issues={len(all_pfx)}")
    for k, c in by_type.most_common():
        print(f"  {k}: {c}")


if __name__ == "__main__":
    main()
