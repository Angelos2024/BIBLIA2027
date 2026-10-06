"""
process_book.py — Orchestrator end-to-end de un libro.

Ejecuta el pipeline completo para el libro indicado:
  0) preflight       — chequea fuentes (.par, OSHB, snapshot, índices)
  1) indices         — build_lookup_indices_book.py   (índices Strong ES / HE)
  2) parse           — parse_catss.py                 (.par → data/<slug>_full.json)
  3) merge           — merge_book.py                  (full → final, alineación)
  4) corrections     — apply_corrections.py --book    (Global Passes 0-17)
  5) paso5           — paso5_run.py --book            (diagnóstico final)
  6) latam           — apply_latam_spanish.py --book  (español latino/neutro)

Por defecto solo imprime el plan; pasa --run para ejecutar.

Uso:
    python process_book.py --book exodo                              # dry-run del plan completo
    python process_book.py --book exodo --run                        # ejecuta todo
    python process_book.py --book exodo --run --steps parse,merge    # solo dos pasos
    python process_book.py --book exodo --run --skip indices         # omite indices

Pasos disponibles: preflight, indices, parse, merge, corrections, paso5, latam
"""
from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from book_config import resolve, BookConfig  # noqa: E402


STEPS_DEFAULT = ("preflight", "indices", "parse", "merge", "corrections", "paso5", "latam")
STEPS_ALL = STEPS_DEFAULT


def _print_preflight(cfg: BookConfig) -> bool:
    print(f"\n── 0/{len(STEPS_DEFAULT)}  preflight  {cfg.label} ──")
    st = cfg.check_sources()
    rows = [
        ("CATSS .par", cfg.par_path, st["par"]),
        ("OSHB-morph", cfg.oshb_dir, st["oshb"]),
        ("Snapshot",   cfg.snap_dir, st["snapshot"]),
        ("Interlineal",cfg.inter_dir, st["interlineal"]),
        ("idx Strong ES", cfg.idx_es_path, st["idx_es"]),
        ("idx Strong HE", cfg.idx_he_path, st["idx_he"]),
    ]
    for label, path, ok in rows:
        flag = "OK" if ok else "FALTA"
        print(f"  [{flag:>5}] {label:<14} {path}")
    must_have = all(st[k] for k in ("par", "oshb", "snapshot"))
    if not must_have:
        print("\n  ❌ Faltan fuentes obligatorias (.par/OSHB/snapshot).")
        if not st["par"]:
            print(f"     Descarga .par:")
            print(f"       curl -sL \"https://ccat.sas.upenn.edu/gopher/text/religion/biblical/parallel/{cfg.par_filename}\" -o \"{cfg.par_path}\"")
    return must_have


def _run(cmd: list[str], *, dry: bool) -> None:
    print(f"  $ {' '.join(shlex.quote(c) for c in cmd)}")
    if dry:
        return
    t0 = time.perf_counter()
    res = subprocess.run(cmd)
    dt = time.perf_counter() - t0
    if res.returncode != 0:
        raise SystemExit(f"  ❌ exit {res.returncode} (t={dt:.1f}s)")
    print(f"  ✓ ({dt:.1f}s)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--book", required=True)
    ap.add_argument("--run", action="store_true",
                    help="ejecutar de verdad (por defecto solo imprime el plan)")
    ap.add_argument("--steps", default=",".join(STEPS_DEFAULT),
                    help=f"comma-list de pasos a ejecutar ({','.join(STEPS_ALL)})")
    ap.add_argument("--skip", default="",
                    help="comma-list de pasos a omitir")
    args = ap.parse_args()

    cfg = resolve(args.book)
    steps = [s.strip() for s in args.steps.split(",") if s.strip()]
    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    plan = [s for s in steps if s not in skip]

    print(f"== process_book — {cfg.label} ({cfg.slug}) ==")
    print(f"   plan: {' → '.join(plan)}   {'(DRY-RUN)' if not args.run else '(EJECUTAR)'}\n")

    py = sys.executable
    here = str(Path(__file__).resolve().parent)
    scripts = lambda name: [py, f"{here}/{name}"]

    ok_preflight = True
    for step in plan:
        if step == "preflight":
            ok_preflight = _print_preflight(cfg)
            if args.run and not ok_preflight:
                raise SystemExit(1)
        elif step == "indices":
            print(f"\n── indices Strong (ES/HE) ──")
            if cfg.idx_es_path.exists() and cfg.idx_he_path.exists():
                print(f"  [skip] índices ya existen ({cfg.idx_es_path.name}, {cfg.idx_he_path.name})")
            else:
                _run(scripts("build_lookup_indices_book.py") + ["--book", cfg.slug], dry=not args.run)
        elif step == "parse":
            print(f"\n── parse CATSS .par → {cfg.raw_json} ──")
            _run(scripts("parse_catss.py") + ["--book", cfg.slug], dry=not args.run)
        elif step == "merge":
            print(f"\n── merge OSHB + snapshot → {cfg.final_json} ──")
            _run(scripts("merge_book.py") + ["--book", cfg.slug], dry=not args.run)
        elif step == "paso5":
            print(f"\n── Paso 5 (diagnóstico, --book {cfg.slug}) ──")
            _run(scripts("paso5_run.py") + ["--book", cfg.slug], dry=not args.run)
        elif step == "corrections":
            print(f"\n── apply_corrections (Global Passes 0-17, --book {cfg.slug}) ──")
            _run(scripts("apply_corrections.py") + ["--book", cfg.slug], dry=not args.run)
        elif step == "latam":
            print(f"\n── Global Pass 17: español latino/neutro (--book {cfg.slug}) ──")
            _run(scripts("apply_latam_spanish.py") + ["--book", cfg.slug], dry=not args.run)
        else:
            print(f"\n  [warn] paso desconocido: {step!r}")

    print("\nListo.")


if __name__ == "__main__":
    main()
