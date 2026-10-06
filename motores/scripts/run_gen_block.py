#!/usr/bin/env python3
"""Wrapper por bloque B0–B8 — pipeline + audits acotados (sin español salvo B5+).

Uso:
    python run_gen_block.py 15 B4
    python run_gen_block.py 15 B2 --skip-pipeline   # solo audit struct
    python run_gen_block.py 15 B1

B5–B7 siguen usando audit_chapter_full.py (español + checklist completo).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent

BLOCKS = frozenset({"B0", "B1", "B2", "B3", "B4", "B8", "B5", "B6", "B7"})

# Bloque → (modo apply_corrections, audits)
_BLOCK_PLAN: dict[str, tuple[str | None, list[str]]] = {
    "B0": ("full", []),
    "B1": (None, ["struct", "es"]),
    "B2": ("hebrew", ["struct"]),
    "B3": ("hebrew", ["struct"]),
    "B4": ("hebrew", ["struct"]),
    "B8": ("lxx", ["struct", "lxx", "lxx_rahlf"]),
    "B5": ("spanish", ["struct", "es"]),
    "B6": ("spanish", ["struct", "es"]),
    "B7": (None, ["full"]),
}


def _run(cmd: list[str], *, cwd: Path = SCRIPTS, capture: bool = False) -> tuple[int, str]:
    print(f"\n>> {' '.join(cmd)}")
    t0 = time.perf_counter()
    if capture:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
        out = (proc.stdout or "") + (proc.stderr or "")
        if out.strip():
            print(out.rstrip())
    else:
        proc = subprocess.run(cmd, cwd=cwd)
        out = ""
    elapsed = time.perf_counter() - t0
    print(f"   ({elapsed:.1f}s, exit={proc.returncode})")
    return proc.returncode, out


def _apply(chapter: int, mode: str) -> int:
    cmd = [
        sys.executable,
        str(SCRIPTS / "apply_corrections.py"),
        "--book", "genesis",
        "--chapter", str(chapter),
        "--mode", mode,
    ]
    rc, _ = _run(cmd)
    return rc


def _apply_full() -> int:
    rc, _ = _run([sys.executable, str(SCRIPTS / "apply_corrections.py"), "--book", "genesis"])
    return rc


def _audit(chapter: int, kind: str) -> tuple[int, str]:
    if kind == "struct":
        rc, out = _run([
            sys.executable, str(SCRIPTS / "audit_gen_chapter_struct.py"), str(chapter),
        ], capture=True)
        return rc, out
    if kind == "es":
        rc, _ = _run([sys.executable, str(SCRIPTS / "audit_chapter.py"), str(chapter)])
        return rc, ""
    if kind == "lxx":
        rc, _ = _run([sys.executable, str(SCRIPTS / "audit_gen_chapter_lxx.py"), str(chapter)])
        return rc, ""
    if kind == "lxx_rahlf":
        rc, _ = _run([sys.executable, str(SCRIPTS / "audit_gen_chapter_lxx_rahlf.py"), str(chapter)])
        return rc, ""
    if kind == "full":
        rc, _ = _run([
            sys.executable,
            str(SCRIPTS / "audit_chapter_full.py"),
            str(chapter),
            "--skip-pipeline",
        ])
        return rc, ""
    raise ValueError(kind)


def _summarize_struct(chapter: int, audit_out: str = "") -> None:
    text = audit_out
    if not text:
        out = SCRIPTS / f"audit_gen{chapter}_struct.txt"
        if out.exists():
            text = out.read_text(encoding="utf-8")
    m_diffs = re.search(r"total_token_diffs=(\d+)", text)
    m_versos = re.search(r"Versículos con diff OSHB: (\d+)/(\d+)", text)
    if m_diffs or m_versos:
        print("\n── Resumen hebreo (struct) ──")
    if m_diffs:
        print(f"   total_token_diffs={m_diffs.group(1)}")
    if m_versos:
        print(f"   versos con diff: {m_versos.group(1)}/{m_versos.group(2)}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Ejecutar bloque de revisión Génesis")
    ap.add_argument("chapter", type=int, help="Número de capítulo")
    ap.add_argument("block", choices=sorted(BLOCKS), help="B0 … B8, B5–B7")
    ap.add_argument(
        "--skip-pipeline",
        action="store_true",
        help="Solo audits (JSON ya actualizado)",
    )
    args = ap.parse_args()

    block = args.block.upper()
    ch = args.chapter
    mode, audits = _BLOCK_PLAN[block]

    print(f"\n== Génesis {ch} · {block} ==")

    if block == "B0":
        if not args.skip_pipeline:
            if _apply_full() != 0:
                sys.exit(1)
        print("\nB0 listo: pipeline sin error. Siguiente: B1 (diagnóstico).")
        return

    if block == "B7":
        cmd = [sys.executable, str(SCRIPTS / "audit_chapter_full.py"), str(ch)]
        if args.skip_pipeline:
            cmd.append("--skip-pipeline")
        rc, _ = _run(cmd)
        sys.exit(rc)

    struct_out = ""
    if not args.skip_pipeline:
        if mode == "full":
            rc = _apply_full()
        elif mode:
            rc = _apply(ch, mode)
        else:
            rc = 0
        if rc != 0:
            sys.exit(rc)

    for kind in audits:
        rc, out = _audit(ch, kind)
        if kind == "struct":
            struct_out = out
        if rc != 0:
            sys.exit(rc)

    if "struct" in audits:
        _summarize_struct(ch, struct_out)

    _next = {
        "B1": "B2 (narrativa) o B3 si hay genealogías",
        "B2": "B3 (genealogías) o B4",
        "B3": "B4 (cierre hebreo total)",
        "B4": "B8 (LXX)",
        "B8": "B5 (español)",
        "B5": "B6 (post-español chN_final)",
        "B6": "B7 (audit full)",
    }
    if block in _next:
        print(f"\n⏸ {block} terminado. Siguiente: {_next[block]}.")


if __name__ == "__main__":
    main()
