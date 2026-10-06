"""
Ejecutar todos los motores para un libro bíblico.

Uso:
    python run_motors.py --book exodo
    python run_motors.py --book josue --skip-base   (si ya existe _final.json)
    python run_motors.py --book genesis --force      (incluye ch 1-15 de Génesis)
"""
import argparse, subprocess, sys, time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

SCRIPTS = Path(__file__).parent
PYTHON  = sys.executable

STEPS = [
    # (description, script, args_template)
    # {book} and {slug} are replaced at runtime
    ("BASE: indices + parse + merge",
     "process_book.py", ["--book", "{slug}", "--run", "--steps", "indices,parse,merge"]),

    # MOTOR 1: reconstruye la capa hebrea (he_words/morfología) desde Macula MT.
    # Reemplaza al antiguo populate_hebrew_macula.py: además de poblar formas,
    # corrige faltantes/duplicados de CATSS y respeta candado de griego/español.
    ("MOTOR 1: Hebreo (Macula, reconstrucción)",
     "_restore_hebrew_oshb.py", ["--book", "{slug}", "--source", "macula", "--mode", "strict", "--apply"]),

    ("MOTOR 2: Morfología (dotted)",
     "convert_morph_to_dotted.py", ["--book", "{slug}", "--apply"]),

    ("MOTOR 3: Griego LXX (CATSS)",
     "populate_greek_catss.py", ["{slug}", "--apply"]),

    ("  3a. Dedup griego",
     "_fix_gr_dedup.py", ["{slug}", "--apply"]),

    ("  3b. Dedup sufijos",
     "_fix_suffix_gr_dedup.py", ["{slug}", "--apply"]),

    ("  3c. Phantom prefixes",
     "_fix_phantom_prefixes.py", ["{slug}", "--apply"]),

    ("  3d. Limpiar artefactos",
     "_clean_greek_artifacts.py", ["{slug}", "--apply"]),

    ("  3e. Dedup prefijo griego",
     "_fix_gr_prefix_dup.py", ["{slug}", "--apply"]),

    ("  3f. Dedup overlap par griego",
     "_fix_gr_pair_dup.py", ["{slug}", "--apply"]),

    ("  3g. Fix fantasmas griegos (CATSS truth)",
     "_fix_gr_phantoms.py", ["{slug}", "--apply"]),

    ("  3h. Rebuild gr_unicode",
     "_rebuild_gr_unicode.py", ["{slug}", "--apply"]),

    ("  3h2. Dedup stems multi-he_word",
     "_fix_multi_hw_stem_dup.py", ["{slug}", "--apply"]),

    ("  3i. Split Greek to prefixes",
     "_fix_prefix_gr_split.py", ["{slug}", "--apply"]),

    ("  3i2. Dedup prefijo griego (post-split)",
     "_fix_gr_prefix_dup.py", ["{slug}", "--apply"]),

    ("  3i2b. Reubicar pronombres mal puestos en prefijo (αὐτοῦ, μου...) -> gr_word",
     "_fix_pron_prefix.py", ["{slug}", "--apply"]),

    ("  3i2c. Reubicar raíz griega atrapada en prefijo (SUBS/VERBO...) -> gr_word",
     "_fix_stem_in_prefix.py", ["{slug}", "--apply"]),

    ("  3i3. Corregir prefix_morphs heredados (W->CONJ, B/K/L/M->PREP, H->ART, griego)",
     "_fix_prefix_morph.py", ["{slug}", "--apply"]),

    ("  3i4. Dedup prefix_gr (intra + dup-de-raíz + consecutivo a nivel de par)",
     "_fix_prefix_gr_dedup.py", ["{slug}", "--apply"]),

    ("  3j. Rebuild gr_unicode (post-split)",
     "_rebuild_gr_unicode.py", ["{slug}", "--apply"]),

    ("  3k. Colapsar duplicados consecutivos + placeholders",
     "_fix_gr_internal_dup.py", ["{slug}", "--apply"]),

    ("  3l. Asignar griego flotante a su hebreo / VACÍO ('?'-> omisión)",
     "_fix_vacio_gr.py", ["{slug}", "--apply"]),

    ("MOTOR 4: Español (glosas)",
     "populate_es_glosses.py", ["--book", "{slug}", "--apply"]),

    ("LIMPIEZA: Phantoms CATSS",
     "_clean_catss_phantoms.py", ["{slug}", "--apply"]),

    ("LIMPIEZA: Hebreo-latino (arameo CATSS ',,a')",
     "_fix_latin_he.py", ["{slug}", "--apply"]),

    ("LIMPIEZA: Rellenar ES desde morfología",
     "_fill_es_gaps.py", ["{slug}", "--apply"]),

    ("FIX: Morph class (Macula validation)",
     "_fix_morph_class.py", ["{slug}", "--apply"]),

    ("FIX: Crossed alignment (pronoun<->noun swap)",
     "_fix_crossed_alignment.py", ["{slug}", "--apply"]),

    ("FIX: Phantom he_words (CATSS word count)",
     "_fix_phantom_hw.py", ["{slug}", "--apply"]),

    ("FIX: Dedup prefix_gr final (tras crossed/phantom)",
     "_fix_prefix_gr_dedup.py", ["{slug}", "--apply"]),

    ("REBUILD: gr_unicode final",
     "_rebuild_gr_unicode.py", ["{slug}", "--apply"]),

    ("FIX: Fill gk_add Greek (CATSS .par)",
     "_fill_gkadd_greek.py", ["{slug}", "--apply"]),

    ("FIX: Eliminar gk_add fantasma (ADD sin griego real)",
     "_fix_empty_gkadd.py", ["{slug}", "--apply"]),

    ("SPLIT: Bloques ADD+ LXX grandes",
     "_split_lxx_blocks.py", ["{slug}", "--apply"]),

    ("RECUPERAR: griego LXX perdido en alineación -> gk_add (sin pasar por alto)",
     "_recover_lxx_dropped.py", ["{slug}", "--apply"]),

    ("RESTAURAR EN: reemplazar [EN:...] con glosa ES (usuario > corpus > tabla)",
     "_restaurar_en.py", ["--book", "{slug}", "--apply", "--no-backup"]),

    ("FLUIDEZ ES: completar artículos/preposiciones/posesivos vacíos (género/número del español)",
     "_fluidez_espanol.py", ["--book", "{slug}", "--apply", "--no-backup"]),

    ("REVISIÓN ES: corregir género/número en glosas existentes (confianza corpus ≥5v)",
     "_revisar_espanol.py", ["--book", "{slug}", "--min-votes", "5", "--apply", "--no-backup"]),

    ("GLOSAS PERSONALES: reaplicar ediciones del editor (registro manda, no se pierden)",
     "_apply_glosas_personales.py", ["{slug}", "--apply"]),

    ("SNAPSHOT: viewer JSON",
     "_convert_final_to_snapshot.py", ["{slug}"]),

    ("RV1960: generar JSON",
     "build_rv1960_book.py", ["--book", "{slug}"]),

    ("AUDITORÍA: resultado final",
     "_audit_book.py", ["{slug}"]),
]


def run_step(desc, script, args, force=False):
    cmd = [PYTHON, str(SCRIPTS / script)] + args
    # _restore_hebrew_oshb.py (MOTOR 1) reconstruye todos los capítulos desde
    # Macula y NO acepta --force (no tiene protección de capítulos), por eso se
    # excluye de la lista de --force.
    if force and script in (
        "convert_morph_to_dotted.py",
        "populate_greek_catss.py",
        "populate_es_glosses.py",
    ):
        cmd.append("--force")

    print(f"\n{'='*60}")
    print(f"  {desc}")
    print(f"  $ {' '.join(cmd)}")
    print(f"{'='*60}")

    import os
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    t0 = time.time()
    result = subprocess.run(cmd, capture_output=False, env=env)
    elapsed = time.time() - t0

    if result.returncode != 0:
        print(f"\n  *** ERROR (exit {result.returncode}) en {script} — abortando ***")
        return False
    print(f"  OK ({elapsed:.1f}s)")
    return True


def main():
    ap = argparse.ArgumentParser(description="Ejecutar todos los motores para un libro")
    ap.add_argument("--book", required=True, help="slug del libro (genesis, exodo, levitico, ...)")
    ap.add_argument("--force", action="store_true", help="Bypass protección Génesis ch 1-15")
    ap.add_argument("--skip-base", action="store_true",
                    help="Omitir indices/parse/merge (si _final.json ya existe)")
    args = ap.parse_args()

    slug = args.book.lower().strip()

    from book_config import resolve
    cfg = resolve(slug)
    final_exists = cfg.final_json_path.exists()

    if args.skip_base and not final_exists:
        print(f"\n  [!] No existe {cfg.final_json_path.name} — se ejecutara la base primero.\n")
        args.skip_base = False

    if not args.skip_base and final_exists:
        print(f"\n  [info] {cfg.final_json_path.name} ya existe — se regenerara desde cero.\n")

    print(f"\n{'#'*60}")
    print(f"  PIPELINE COMPLETO -- {slug.upper()}")
    print(f"  Force: {args.force}  |  Skip base: {args.skip_base}")
    print(f"{'#'*60}")

    t_total = time.time()

    for desc, script, step_args in STEPS:
        if args.skip_base and script == "process_book.py":
            print(f"\n  [skip] {desc}")
            continue

        real_args = [a.replace("{slug}", slug) for a in step_args]
        ok = run_step(desc, script, real_args, force=args.force)
        if not ok:
            print(f"\n*** Pipeline abortado por error en: {desc} ***")
            sys.exit(1)

    elapsed_total = time.time() - t_total
    print(f"\n{'#'*60}")
    print(f"  PIPELINE COMPLETO — {slug.upper()} — {elapsed_total:.0f}s total")
    print(f"{'#'*60}")


if __name__ == "__main__":
    main()
