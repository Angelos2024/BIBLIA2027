"""Auditoría estructural Gén 5 vs OSHB — huecos, orden, prefijos/sufijos."""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "genesis_final.json"
OSHB = Path(
    r"C:\Users\pik_y\Documents\GitHub\Local-consults\estudio\angelos"
    r"\IdiomaORIGEN\oshb-morph\chapters\01_Génesis\5.json"
)
OUT = Path(__file__).resolve().parent


def norm_he(s: str) -> str:
    if not s:
        return ""
    from hebrew_clean import strip_encoding_artifact

    s = strip_encoding_artifact(s)
    s = re.sub(r"[\u0591-\u05C7\u05BC\u05C1\u05C2\u05BD]", "", s)
    return s.replace("־", "").replace("-", "").strip()


def flatten_hw(hw: dict) -> list[tuple[str, str, str]]:
    """(he, morph, slot) por token expandido."""
    out: list[tuple[str, str, str]] = []
    pfx_f = hw.get("prefix_forms") or []
    pfx_m = hw.get("prefix_morphs") or []
    for i, pf in enumerate(pfx_f):
        morph = pfx_m[i] if i < len(pfx_m) else "?"
        out.append((pf, morph, f"prefix[{i}]"))
    stem = (hw.get("he_form") or "").strip()
    morph = hw.get("he_morph") or "?"
    if stem:
        out.append((stem, morph, "stem"))
    ps = hw.get("prs_suffix") or {}
    if ps.get("he_form"):
        out.append((ps["he_form"], ps.get("he_morph") or "PRS", "prs_suffix"))
    return out


def flatten_verse(v: dict) -> list[tuple[str, str, str, int, int, str]]:
    """(he, morph, slot, pair, hw_idx, raw)."""
    rows = []
    for pi, p in enumerate(v.get("pairs", [])):
        for hi, hw in enumerate(p.get("he_words", [])):
            raw = hw.get("raw") or ""
            for he, morph, slot in flatten_hw(hw):
                rows.append((he, morph, slot, pi, hi, raw))
    return rows


def check_pfx_sfx(v: dict, ref: str) -> list[dict]:
    issues = []
    for pi, p in enumerate(v.get("pairs", [])):
        if not (p.get("he_words") or []):
            if p.get("kind") == "gk_add" or (
                (p.get("gr_unicode") or "").strip()
                and not (p.get("he_unicode") or "").strip()
            ):
                continue
            issues.append({
                "ref": ref, "type": "par_vacio", "pair": pi,
                "detail": "pair sin he_words",
            })
        he_u = (p.get("he_unicode") or "").strip()
        for hi, hw in enumerate(p.get("he_words", [])):
            raw = hw.get("raw") or ""
            pfx_f = hw.get("prefix_forms") or []
            pfx_m = hw.get("prefix_morphs") or []
            pfx_e = hw.get("prefix_es") or []
            stem = (hw.get("he_form") or "").strip()
            ps = hw.get("prs_suffix") or {}

            n = len(pfx_f)
            for key, arr in (
                ("prefix_morphs", pfx_m),
                ("prefix_es", pfx_e),
            ):
                if len(arr) not in (0, n):
                    issues.append({
                        "ref": ref, "type": "pfx_array_desalineado",
                        "pair": pi, "hw": hi, "raw": raw,
                        "detail": f"{key} len={len(arr)} != prefix_forms len={n}",
                    })

            if n and not any(norm_he(x) for x in pfx_f):
                issues.append({
                    "ref": ref, "type": "pfx_vacio", "pair": pi, "hw": hi,
                    "raw": raw, "detail": "prefix_forms vacíos con slots",
                })

            if raw and not norm_he(stem) and not pfx_f and not ps.get("he_form"):
                if not raw.endswith("}"):
                    if raw in ("GKADD", "=<LXX>"):
                        continue
                    issues.append({
                        "ref": ref, "type": "stem_vacio", "pair": pi, "hw": hi,
                        "raw": raw, "detail": "sin hebreo en stem/pfx/prs",
                    })

            # PRS suelto en stem cuando debería ser sufijo
            if stem and norm_he(stem) in ("נו", "נוּ", "ה", "הּ", "ו", "וֹ", "ם", "ם"):
                if not pfx_f:
                    issues.append({
                        "ref": ref, "type": "prs_en_stem", "pair": pi, "hw": hi,
                        "raw": raw, "detail": f"posible sufijo en stem: {stem!r}",
                    })

            # prefix_es con glosa pero prefix vacío
            for i, pe in enumerate(pfx_e):
                pf = pfx_f[i] if i < len(pfx_f) else ""
                if (pe or "").strip() and not norm_he(pf):
                    issues.append({
                        "ref": ref, "type": "pfx_es_sin_he", "pair": pi, "hw": hi,
                        "raw": raw, "detail": f"prefix_es[{i}]={pe!r} sin he",
                    })

            # Stem es solo conj/prep que OSHB separa
            if stem in ("וַ", "וּ", "וְ", "כְּ", "בִּ") and not pfx_f:
                issues.append({
                    "ref": ref, "type": "particula_en_stem", "pair": pi, "hw": hi,
                    "raw": raw, "detail": f"partícula {stem!r} como stem sin prefijo real",
                })

            if ps.get("es") and not ps.get("he_form"):
                issues.append({
                    "ref": ref, "type": "prs_es_sin_he", "pair": pi, "hw": hi,
                    "raw": raw, "detail": "prs_suffix con es pero sin he_form",
                })

    return issues


def expand_fused_ot_he(data_he: list[str]) -> list[str]:
    """Convención del proyecto: אֹתוֹ/אֹתָם fusionados ≡ OSHB את + sufijo."""
    expand = {
        "אתו": ["את", "ו"],
        "אתם": ["את", "ם"],
        "אתה": ["את", "ה"],
        "אתנו": ["את", "נו"],
    }
    out: list[str] = []
    for nh in data_he:
        if nh in expand:
            out.extend(expand[nh])
        else:
            out.append(nh)
    return out


def align_oshb(data_flat: list[str], oshb_flat: list[str]) -> list[dict]:
    """Diff simple por claves normalizadas."""
    issues = []
    i = j = 0
    while i < len(data_flat) or j < len(oshb_flat):
        if i >= len(data_flat):
            issues.append({"type": "faltante_data", "oshb_idx": j, "oshb": oshb_flat[j]})
            j += 1
            continue
        if j >= len(oshb_flat):
            issues.append({"type": "extra_data", "data_idx": i, "data": data_flat[i]})
            i += 1
            continue
        a, b = data_flat[i], oshb_flat[j]
        if a == b:
            i += 1
            j += 1
            continue
        # lookahead 1
        if i + 1 < len(data_flat) and data_flat[i + 1] == b:
            issues.append({"type": "extra_data", "data_idx": i, "data": a})
            i += 1
            continue
        if j + 1 < len(oshb_flat) and a == oshb_flat[j + 1]:
            issues.append({"type": "faltante_data", "oshb_idx": j, "oshb": b})
            j += 1
            continue
        issues.append({"type": "desalineado", "data_idx": i, "data": a, "oshb_idx": j, "oshb": b})
        i += 1
        j += 1
    return issues


def main():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    oshb = json.loads(OSHB.read_text(encoding="utf-8"))

    all_pfx = []
    all_oshb = []
    lines = ["# Gén 5 — auditoría estructural hebreo vs OSHB\n"]

    for vn in range(1, 33):
        ref = f"5:{vn}"
        v = next(x for x in data["verses"] if x.get("chapter") == 5 and x.get("verse") == vn)
        oshb_v = oshb.get(str(vn), {})
        oforms = oshb_v.get("forms", [])
        omorphs = oshb_v.get("morphs", [])

        flat = flatten_verse(v)
        data_he = expand_fused_ot_he([norm_he(x[0]) for x in flat if norm_he(x[0])])
        oshb_he = [norm_he(x) for x in oforms if norm_he(x)]

        pfx_issues = check_pfx_sfx(v, ref)
        all_pfx.extend(pfx_issues)

        diff = align_oshb(data_he, oshb_he)
        if diff or pfx_issues:
            lines.append(f"\n## {ref}")
            lines.append(f"  data={len(data_he)} oshb={len(oshb_he)} pfx_issues={len(pfx_issues)} diff={len(diff)}")
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

        # detalle tokens para versos problemáticos
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
    lines.insert(1, f"Versículos con diff OSHB: {len(all_oshb)}/32")
    lines.insert(2, f"Issues prefijo/sufijo: {len(all_pfx)} — {dict(by_type)}")

    out_path = OUT / "audit_gen5_struct.txt"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"written {out_path}")
    print(f"versos_problematicos={len(all_oshb)} pfx_issues={len(all_pfx)}")
    for k, c in by_type.most_common():
        print(f"  {k}: {c}")


if __name__ == "__main__":
    main()
