# -*- coding: utf-8 -*-
"""Crea un punto de restauracion: copia el estado actual del proyecto a una
carpeta de respaldo, excluyendo backups previos y caches para no duplicar."""
import os, shutil

SRC = os.path.dirname(os.path.abspath(__file__))
DEST_NAME = "_PUNTO_RESTAURACION_INICIAL_20260613"
DEST = os.path.join(SRC, DEST_NAME)

EXCLUDE_PREFIXES = ("respaldos_fonetica_", "respaldos_reglas_e_")
# Backups previos, caches y assets estaticos pesados (insumos que no cambian
# al editar el motor; siguen en su sitio, solo no se duplican en el respaldo).
EXCLUDE_NAMES = {"_respaldo_json_base", DEST_NAME, "__pycache__", ".git",
                 "dividido"}
MAX_FILE_BYTES = 150 * 1024 * 1024   # se omiten archivos > 150 MB (PDF/zip madre)


def ignore(dirpath, names):
    skip = set()
    for n in names:
        full = os.path.join(dirpath, n)
        if n in EXCLUDE_NAMES or n.startswith(EXCLUDE_PREFIXES):
            skip.add(n)
        elif os.path.isfile(full) and os.path.getsize(full) > MAX_FILE_BYTES:
            skip.add(n)
    return skip


def main():
    if os.path.exists(DEST):
        shutil.rmtree(DEST)
    shutil.copytree(SRC, DEST, ignore=ignore)
    nfiles = sum(len(fs) for _, _, fs in os.walk(DEST))
    size = sum(os.path.getsize(os.path.join(r, f))
               for r, _, fs in os.walk(DEST) for f in fs)
    print(f"Respaldo creado en: {DEST}")
    print(f"Archivos copiados : {nfiles}")
    print(f"Tamano total      : {size/1_048_576:.1f} MB")
    print("DONE")


if __name__ == "__main__":
    main()
