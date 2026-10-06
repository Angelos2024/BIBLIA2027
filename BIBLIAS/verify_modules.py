"""Verify Strong's tagging in downloaded SWORD modules.

Writes full UTF-8 results to verify_modules.out so Windows console
charmap problems do not hide Hebrew or accented Spanish output.
"""
from pathlib import Path
import sys, io
from pysword.modules import SwordModules

BASE = Path(r"C:\Users\pik_y\Documents\TRADUCCION\BIBLIAS")
OUT  = BASE / "verify_modules.out"

MODULES = [
    ("SpaRV1909", BASE / "SpaRV1909", "SpaRV1909"),
    ("SpaRV",     BASE / "SpaRV",     "SpaRV"),
    ("OSHB",      BASE / "OSHB",      "OSHB"),
    ("WLC",       BASE / "WLC",       "WLC"),
]

VERSES = [
    ("Genesis", 1, 1),
    ("Genesis", 1, 2),
    ("John",    3, 16),
]

with OUT.open("w", encoding="utf-8") as f:
    def w(s=""):
        f.write(s + "\n")

    for label, root, modname in MODULES:
        w(f"\n========== {label} @ {root.name} ==========")
        if not root.exists():
            w("  (missing root dir)")
            continue
        try:
            sm = SwordModules(str(root))
            found = sm.parse_modules()
            w(f"  modules in package: {list(found.keys())}")
            actual = next((k for k in found if k.lower() == modname.lower()),
                          next(iter(found.keys()), None))
            if not actual:
                w("  no module found")
                continue
            bible = sm.get_bible_from_module(actual)
            for book, ch, vs in VERSES:
                try:
                    raw = list(bible.get_iter(books=[book], chapters=[ch],
                                              verses=[vs], clean=False))
                    for line in raw:
                        w(f"  {book} {ch}:{vs} RAW   : {line}")
                except Exception as e:
                    w(f"  {book} {ch}:{vs} RAW   ERROR: {type(e).__name__}: {e}")
                try:
                    clean = list(bible.get_iter(books=[book], chapters=[ch],
                                                verses=[vs], clean=True))
                    for line in clean:
                        w(f"  {book} {ch}:{vs} CLEAN : {line}")
                except Exception as e:
                    w(f"  {book} {ch}:{vs} CLEAN ERROR: {type(e).__name__}: {e}")
        except Exception as e:
            w(f"  ERROR loading: {type(e).__name__}: {e}")

print(f"Wrote {OUT}")
