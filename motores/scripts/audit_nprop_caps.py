"""Audita NPROP con glosa española sin mayúscula inicial (Gén 1–4)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "genesis_final.json"
OUT = Path(__file__).resolve().parent / "audit_nprop_caps_gen1-4.txt"

USER_SOURCES = frozenset({"glosa_personal", "glosa_global", "manual"})


def is_nprop(morph: str) -> bool:
    m = (morph or "").upper()
    return m == "NPROP" or m.startswith("NPROP.")


def needs_cap(es: str) -> bool:
    es = (es or "").strip()
    if not es:
        return False
    if es[0] in ("'", "\u02BF", "\u02BE"):
        return len(es) > 1 and es[1].islower()
    return es[0].islower()


def main() -> None:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    issues: list[tuple[str, str, str, str, str, str]] = []
    ok_user: list[tuple[str, str, str]] = []

    for ch in (1, 2, 3, 4):
        for v in data.get("verses", []):
            if v.get("chapter") != ch:
                continue
            ref = v.get("ref", f"Gen {ch}:{v.get('verse')}")
            for p in v.get("pairs", []):
                for hw in p.get("he_words", []):
                    if not is_nprop(hw.get("he_morph") or ""):
                        continue
                    es = (hw.get("es") or "").strip()
                    if not es or not needs_cap(es):
                        continue
                    src = (hw.get("es_source") or "").strip()
                    row = (
                        ref,
                        hw.get("raw") or "",
                        hw.get("strongs") or "",
                        hw.get("he_form") or "",
                        es,
                        src,
                    )
                    if src in USER_SOURCES:
                        ok_user.append(row[:4] + (es,))
                    else:
                        issues.append(row)

    lines = [
        f"# NPROP sin mayúscula inicial — Gén 1–4",
        f"Corregibles: {len(issues)} | Protegidos (glosa editor): {len(ok_user)}",
        "",
        "## A corregir",
    ]
    for ref, raw, strongs, he, es, src in sorted(issues, key=lambda r: (r[0], r[1])):
        lines.append(f"{ref}\t{raw}\t{strongs}\t{es}\t[{src}]")

    if ok_user:
        lines.extend(["", "## Protegidos (no tocar)", ""])
        for ref, raw, strongs, he, es in ok_user:
            lines.append(f"{ref}\t{raw}\t{strongs}\t{es}")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Corregibles: {len(issues)}")
    print(f"Protegidos: {len(ok_user)}")
    print(f"CSV: {OUT}")
    for row in issues[:30]:
        print(f"  {row[0]} {row[3]} -> {row[4]!r}")


if __name__ == "__main__":
    main()
