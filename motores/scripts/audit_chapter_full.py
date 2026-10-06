"""Auditoría completa de un capítulo — hebreo + glosas + español (una sola invocación)."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent

USER_GLOSS = frozenset({"manual", "glosa_personal", "glosa_global"})
KNOWN_STRONG = {"H3651": "כֵּן", "H5921": "עַל", "H5704": "עַד", "H853": "אֶת"}
_FUSED_PREP_ES = frozenset({
    "a él", "a el", "sobre él", "sobre el",
    "con él", "con el", "de él", "de el", "contigo", "conmigo",
})

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from hebrew_clean import he_form_deformed, is_meta_raw


def scan_he_deformado(data: dict, chapter: int) -> list[str]:
    """B7 — he_form con artefactos OSHB (i>() o mezcla latín/hebreo."""
    issues: list[str] = []
    for v in data["verses"]:
        if v.get("chapter") != chapter:
            continue
        ref = f"{chapter}:{v.get('verse')}"
        for p in v.get("pairs", []):
            for hw in p.get("he_words", []):
                raw = hw.get("raw") or ""
                if is_meta_raw(raw):
                    continue
                he = (hw.get("he_form") or "").strip()
                if he_form_deformed(he):
                    issues.append(f"{ref} {raw} he_deformado stem={he!r}")
                for i, pf in enumerate(hw.get("prefix_forms") or []):
                    if he_form_deformed(pf or ""):
                        issues.append(f"{ref} {raw} he_deformado prefix[{i}]={pf!r}")
                prs = hw.get("prs_suffix") or {}
                if isinstance(prs, dict):
                    ph = (prs.get("he_form") or "").strip()
                    if he_form_deformed(ph):
                        issues.append(f"{ref} {raw} he_deformado prs={ph!r}")
    return issues


def scan_spanish(data: dict, chapter: int) -> list[str]:
    issues: list[str] = []
    for v in data["verses"]:
        if v.get("chapter") != chapter:
            continue
        ref = f"{chapter}:{v.get('verse')}"
        for p in v.get("pairs", []):
            for hw in p.get("he_words", []):
                src = (hw.get("es_source") or "").strip().lower()
                es = (hw.get("es") or "").strip()
                morph = hw.get("he_morph") or ""
                raw = hw.get("raw", "")
                for i, pm in enumerate(hw.get("prefix_morphs") or []):
                    pe = (hw.get("prefix_es") or [""])[i] if i < len(hw.get("prefix_es") or []) else ""
                    if not (pe or "").strip() and pm in ("CONJ", "PREP", "ART", "NEG"):
                        issues.append(f"{ref} {raw} pfx[{i}] {pm} stem={es!r}")
                prs = hw.get("prs_suffix") or {}
                if prs.get("he_form") and not (prs.get("es") or "").strip() and src not in USER_GLOSS:
                    prs_src = (prs.get("es_source") or "").strip().lower()
                    stem_low = es.lower()
                    if prs_src == "patch_meta" or stem_low in _FUSED_PREP_ES:
                        pass
                    elif morph.startswith("PREP") or not es:
                        issues.append(f"{ref} {raw} prs {prs.get('he_morph')} stem={es!r}")
                low = f" {es.lower()} "
                if " su su " in low or " tus tus " in low or " los los " in low:
                    issues.append(f"{ref} {raw} dup {es!r}")
    return issues


def scan_semantic(data: dict, chapter: int) -> list[str]:
    issues: list[str] = []
    for v in data["verses"]:
        if v.get("chapter") != chapter:
            continue
        ref = f"{chapter}:{v.get('verse')}"
        for p in v.get("pairs", []):
            for hw in p.get("he_words", []):
                raw = hw.get("raw", "")
                morph = hw.get("he_morph") or ""
                es = (hw.get("es") or "").strip()
                strong = hw.get("strongs") or ""
                he = (hw.get("he_form") or "").strip()
                if strong in KNOWN_STRONG:
                    nh = re.sub(r"[\u0591-\u05C7\u05BC\u05C1\u05C2\u05BD]", "", he).replace("־", "")
                    exp_n = re.sub(r"[\u0591-\u05C7\u05BC\u05C1\u05C2\u05BD]", "", KNOWN_STRONG[strong])
                    if nh and exp_n and nh != exp_n and not nh.startswith(exp_n):
                        issues.append(f"{ref} {raw} strong={strong} he={he!r}")
                if morph == "PRON.PERS.P3.F.SG" and es.lower() in ("él", "el"):
                    issues.append(f"{ref} {raw} F.SG gloss={es!r}")
                if "PERF.P3.M.SG" in morph and es.lower().endswith("aron"):
                    issues.append(f"{ref} {raw} 3MSg plural {es!r}")
                for i, pm in enumerate(hw.get("prefix_morphs") or []):
                    pe = (hw.get("prefix_es") or [""])[i] if i < len(hw.get("prefix_es") or []) else ""
                    if pm == "PREP" and pe in ("allí", "esta") and not morph.startswith("PREP"):
                        issues.append(f"{ref} {raw} PREP={pe!r} stem={es!r}")
                if morph == "AFSA" and strong == "H5892":
                    issues.append(f"{ref} {raw} AFSA wrong H5892 gloss={es!r}")
    return issues


def main() -> None:
    ap = argparse.ArgumentParser(description="Auditoría completa de capítulo Génesis")
    ap.add_argument("chapter", type=int)
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "genesis_final.json")
    ap.add_argument("--skip-pipeline", action="store_true", help="No ejecutar apply_corrections antes")
    args = ap.parse_args()

    if not args.skip_pipeline:
        print("=== Pipeline apply_corrections (genesis) ===")
        subprocess.run(
            [sys.executable, str(SCRIPTS / "apply_corrections.py"), "--book", "genesis"],
            cwd=str(ROOT),
            check=False,
        )

    print(f"\n=== Estructural OSHB cap. {args.chapter} ===")
    subprocess.run(
        [sys.executable, str(SCRIPTS / "audit_gen_chapter_struct.py"), str(args.chapter)],
        cwd=str(ROOT),
        check=False,
    )

    print(f"\n=== Glosas cap. {args.chapter} ===")
    subprocess.run(
        [sys.executable, str(SCRIPTS / "audit_chapter.py"), str(args.chapter)],
        cwd=str(ROOT),
        check=False,
    )

    print(f"\n=== LXX posicionada cap. {args.chapter} (B8) ===")
    lxx_rc = subprocess.run(
        [sys.executable, str(SCRIPTS / "audit_gen_chapter_lxx.py"), str(args.chapter)],
        cwd=str(ROOT),
        check=False,
    )

    print(f"\n=== LXX Rahlfs cap. {args.chapter} (B8+) ===")
    lxx_rahlf_rc = subprocess.run(
        [sys.executable, str(SCRIPTS / "audit_gen_chapter_lxx_rahlf.py"), str(args.chapter)],
        cwd=str(ROOT),
        check=False,
    )

    data = json.loads(args.data.read_text(encoding="utf-8"))
    he_issues = scan_he_deformado(data, args.chapter)
    es_issues = scan_spanish(data, args.chapter)
    sem_issues = scan_semantic(data, args.chapter)

    print(f"\n=== Hebreo deformado (artefactos OSHB) cap. {args.chapter} (B7) ===")
    print(f"issues: {len(he_issues)}")
    for line in he_issues[:30]:
        print(f"  {line}")

    print(f"\n=== Español prefijos/PRS cap. {args.chapter} ===")
    print(f"issues: {len(es_issues)}")
    for line in es_issues[:30]:
        print(f"  {line}")

    print(f"\n=== Semántica (strongs/género/asignación) cap. {args.chapter} ===")
    print(f"issues: {len(sem_issues)}")
    for line in sem_issues[:30]:
        print(f"  {line}")

    report = SCRIPTS / f"audit_ch{args.chapter}_full.txt"
    lxx_ok = lxx_rc.returncode == 0 and lxx_rahlf_rc.returncode == 0
    report.write_text(
        "\n".join([
            f"# Auditoría completa Gén {args.chapter}",
            "",
            f"lxx_b8_ok={lxx_rc.returncode == 0}",
            f"lxx_rahlf_ok={lxx_rahlf_rc.returncode == 0}",
            "",
            f"he_deformado_issues={len(he_issues)}",
            *he_issues,
            "",
            f"spanish_issues={len(es_issues)}",
            *es_issues,
            "",
            f"semantic_issues={len(sem_issues)}",
            *sem_issues,
        ]),
        encoding="utf-8",
    )
    print(f"\nwritten {report}")

    ok = lxx_ok and not he_issues and not es_issues and not sem_issues
    print("\n=== CRITERIO LISTO ===")
    if ok:
        print("  Hebreo: ver total_token_diffs=0 arriba; he_deformado=0")
        print("  LXX B8 + Rahlfs: 0 incidencias")
        print("  Español: 0 issues en escaneos automáticos")
        print("  Estado: PASA auditoría automática (revisar manualmente si hay par_vacio)")
    else:
        print("  Estado: PENDIENTE — corregir issues listados y re-ejecutar")
        if not lxx_ok:
            print("  LXX: revisar audit_gen{N}_lxx.txt y audit_gen{N}_lxx_rahlf.txt".replace("{N}", str(args.chapter)))


if __name__ == "__main__":
    main()
