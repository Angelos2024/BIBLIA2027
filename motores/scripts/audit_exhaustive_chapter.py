"""Auditoría exhaustiva: tokens con hebreo/morf/es/LXX incompletos."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "genesis_final.json"

META_PREFIXES = ("=", "{", "<", "*", "--", ".")


def clean_he(s):
    if not s:
        return ""
    t = re.sub(r"[\u0591-\u05AF]", "", str(s))
    t = re.sub(r"[\u05BE\u05C0\u05C3-\u05C6]", "", t)
    return t.strip()


def is_pod(hw):
    morph = hw.get("he_morph") or ""
    return morph == "PART.OBJ.DIR" or morph.startswith("PART.OBJ.DIR+")


def audit_token(ref, pair_i, hw_i, hw, slot, prefix_morph="", prefix_form=""):
    issues = []
    he = clean_he(hw.get("he_form") or prefix_form)
    es = (hw.get("es") or "").strip()
    morph = hw.get("he_morph") or prefix_morph or ""
    strong = hw.get("strongs") or ""
    gr = hw.get("gr_word") or ""
    raw = hw.get("raw") or ""

    if raw.startswith(META_PREFIXES):
        return issues
    if is_pod(hw) and slot == "stem":
        return issues
    if prefix_morph == "PART.OBJ.DIR":
        return issues

    if not he:
        issues.append("sin_hebreo")
    if not morph and he:
        issues.append("sin_morfologia")
    if not es and not is_pod(hw):
        if slot == "prefix" and prefix_morph in ("ART", "CONJ", "PREP"):
            if prefix_morph == "ART":
                issues.append("art_sin_es")
            elif prefix_morph == "CONJ" and not es:
                issues.append("conj_sin_es")
            elif prefix_morph == "PREP" and not es:
                issues.append("prep_sin_es")
        elif slot == "stem":
            issues.append("sin_es")
    if not gr or gr == "---":
        if slot == "stem" and he and not is_pod(hw):
            issues.append("sin_lxx")
    if morph == "REL" and he and not strong:
        issues.append("rel_sin_strong")
    if "/" in es:
        issues.append("es_opciones")
    if es in ("que", "") and raw in ("ML)KT/W", "YWM", "B/W") and he and "א" not in he:
        issues.append("posible_mal_parseo")

    prs = hw.get("prs_suffix") or {}
    if prs:
        phe = clean_he(prs.get("he_form"))
        pes = (prs.get("es") or "").strip()
        if phe and not pes and es and pes.lower() in es.lower().split():
            issues.append("prs_redundante")
        elif phe and pes and es and re.search(rf"(?<!\w){re.escape(pes.lower())}(?!\w)", es.lower()):
            issues.append("prs_redundante")

    return [(ref, pair_i, hw_i, slot, raw, he, morph, es, gr, issue) for issue in issues]


def audit_chapter(data, chapter):
    rows = []
    for v in data["verses"]:
        if v.get("chapter") != chapter:
            continue
        ref = f"{chapter}:{v.get('verse')}"
        for pi, p in enumerate(v.get("pairs", [])):
            if p.get("kind") in ("gk_add", "heb_omit"):
                continue
            for hi, hw in enumerate(p.get("he_words", [])):
                rows.extend(audit_token(ref, pi, hi, hw, "stem"))
                for i, pm in enumerate(hw.get("prefix_morphs") or []):
                    pf = (hw.get("prefix_forms") or [""])[i] if i < len(hw.get("prefix_forms") or []) else ""
                    rows.extend(audit_token(ref, pi, hi, hw, "prefix", pm, pf))
    return rows


def dump_verse(data, chapter, verse):
    v = next(x for x in data["verses"] if x["chapter"] == chapter and x["verse"] == verse)
    rows = []
    for pi, p in enumerate(v["pairs"]):
        for hi, hw in enumerate(p.get("he_words", [])):
            pfx = hw.get("prefix_es") or []
            pm = hw.get("prefix_morphs") or []
            pf = hw.get("prefix_forms") or []
            pg = hw.get("prefix_gr") or []
            for i in range(max(len(pm), 1)):
                rows.append({
                    "pair": pi, "hw": hi, "slot": f"prefix[{i}]" if pm else "stem",
                    "raw": hw.get("raw"),
                    "prefix_form": pf[i] if i < len(pf) else "",
                    "prefix_morph": pm[i] if i < len(pm) else "",
                    "he_form": hw.get("he_form"),
                    "he_morph": hw.get("he_morph"),
                    "strongs": hw.get("strongs"),
                    "prefix_es": pfx[i] if i < len(pfx) else "",
                    "es": hw.get("es"),
                    "gr_word": hw.get("gr_word"),
                    "prefix_gr": pg[i] if i < len(pg) else "",
                    "prs": hw.get("prs_suffix"),
                    "es_source": hw.get("es_source"),
                })
            if pm:
                rows.append({
                    "pair": pi, "hw": hi, "slot": "stem",
                    "raw": hw.get("raw"),
                    "he_form": hw.get("he_form"),
                    "he_morph": hw.get("he_morph"),
                    "strongs": hw.get("strongs"),
                    "es": hw.get("es"),
                    "gr_word": hw.get("gr_word"),
                    "prs": hw.get("prs_suffix"),
                    "es_source": hw.get("es_source"),
                })
    return rows


def main():
    cap = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    data = json.loads(DATA.read_text(encoding="utf-8"))
    rows = audit_chapter(data, cap)
    out_dir = Path(__file__).resolve().parent

    if len(sys.argv) > 2:
        vrs = int(sys.argv[2])
        dump = dump_verse(data, cap, vrs)
        (out_dir / f"dump_{cap}_{vrs}.json").write_text(
            json.dumps(dump, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    by_issue = {}
    for r in rows:
        by_issue.setdefault(r[9], []).append(r)

    report = [f"# Génesis {cap} — auditoría exhaustiva\n", f"Total problemas: {len(rows)}\n"]
    for kind, items in sorted(by_issue.items(), key=lambda x: -len(x[1])):
        report.append(f"## {kind}: {len(items)}")
        for r in items[:20]:
            report.append(
                f"  {r[0]} p{r[1]} {r[3]} raw={r[4]} morph={r[6]} es={r[7]} gr={r[8]}"
            )
        if len(items) > 20:
            report.append(f"  ... +{len(items)-20} más")
        report.append("")

    csv_lines = ["ref,pair,hw,slot,raw,he,morph,es,gr,issue"]
    for r in rows:
        csv_lines.append(",".join(str(x).replace(",", ";") for x in r))
    (out_dir / f"audit_exhaustive_gen{cap}.csv").write_text(
        "\n".join(csv_lines), encoding="utf-8"
    )
    (out_dir / f"audit_exhaustive_gen{cap}.txt").write_text(
        "\n".join(report), encoding="utf-8"
    )
    if len(sys.argv) > 2:
        report.append(f"Dump {cap}:{sys.argv[2]} -> dump_{cap}_{sys.argv[2]}.json")
    print("\n".join(report))


if __name__ == "__main__":
    main()
