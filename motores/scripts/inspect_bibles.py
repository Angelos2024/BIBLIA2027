"""Inspecciona los módulos PH4/MyBible descargados en BIBLIAS/."""
import io
import os
import sys
import zipfile
import sqlite3
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BIBLIAS = Path(r"C:\Users\pik_y\Documents\TRADUCCION\BIBLIAS")


def extract_zip(zip_path: Path, dest: Path):
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)
        print(f"  Extraído {zip_path.name} → {dest}")
        for n in zf.namelist():
            print(f"    · {n}")


def inspect_sqlite(db_path: Path, label: str):
    print(f"\n=== {label}: {db_path.name} ===")
    if not db_path.exists():
        print("  (no existe)")
        return
    print(f"  Tamaño: {db_path.stat().st_size:,} bytes")
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        print(f"  Tablas: {tables}")
        for t in tables:
            try:
                cur.execute(f"PRAGMA table_info({t})")
                cols = [r[1] for r in cur.fetchall()]
                cur.execute(f"SELECT COUNT(*) FROM {t}")
                cnt = cur.fetchone()[0]
                print(f"    [{t}] {cnt} filas · cols: {cols}")
                cur.execute(f"SELECT * FROM {t} LIMIT 3")
                rows = cur.fetchall()
                for r in rows:
                    txt = str(r)
                    if len(txt) > 220:
                        txt = txt[:217] + "..."
                    print(f"      sample: {txt}")
            except Exception as e:
                print(f"    [{t}] error: {e}")
        conn.close()
    except Exception as e:
        print(f"  Error: {e}")


def main():
    print("ARCHIVOS EN BIBLIAS/")
    for p in sorted(BIBLIAS.iterdir()):
        print(f"  {p.name}  ({p.stat().st_size:,} bytes)")

    # 1. LBLA.zip → extraer si no está extraído
    lbla_zip = BIBLIAS / "Bible_Espanol_LBLA.zip"
    lbla_dest = BIBLIAS / "_extracted_LBLA"
    if lbla_zip.exists() and not lbla_dest.exists():
        print("\n[1/3] Extrayendo LBLA...")
        extract_zip(lbla_zip, lbla_dest)
    elif lbla_dest.exists():
        print(f"\n[1/3] LBLA ya extraída en {lbla_dest}")
        for p in lbla_dest.rglob("*"):
            if p.is_file():
                print(f"    · {p.relative_to(lbla_dest)} ({p.stat().st_size:,} bytes)")

    # 2. RVR1960+.rar — Python no extrae .rar de fábrica, dejarlo para después
    rar_file = BIBLIAS / "02-RVR1960+.rar"
    print(f"\n[2/3] RVR1960+.rar — {rar_file.stat().st_size:,} bytes")
    print("    Nota: .rar requiere WinRAR/7zip; lo manejo en un segundo paso si lo necesitas.")

    # 3. BTX4 — ya están como .mybible (SQLite)
    print("\n[3/3] BTX4 — formato MyBible (.mybible = SQLite)")
    inspect_sqlite(BIBLIAS / "BTX4.bbl.mybible", "BTX4 Bible")
    inspect_sqlite(BIBLIAS / "BTX4.dct.mybible", "BTX4 Dictionary")

    # 4. Inspeccionar los .SQLite3 dentro de LBLA extraído
    if lbla_dest.exists():
        for p in lbla_dest.rglob("*"):
            if p.is_file() and p.suffix.lower() in (".sqlite3", ".db", ".bbl", ".mybible"):
                inspect_sqlite(p, f"LBLA")


if __name__ == "__main__":
    main()
