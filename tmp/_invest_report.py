# -*- coding: utf-8 -*-
"""Investigation report writer (UTF-8 file; avoids cp1252 console)."""
import json
import os
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(r"C:\Users\Angelos\Desktop\BIBLIA2027")
OUT = ROOT / "tmp" / "_invest_out.txt"
lines = []

def w(s=""):
    lines.append(s)

# --- GIT ---
w("=== GIT ===")
git_dir = ROOT / ".git"
w(f"HAS_GIT={git_dir.exists()}")
if git_dir.exists():
    def g(*args):
        r = subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
        return (r.stdout or "") + (("\n" + r.stderr) if r.stderr else "")
    w("--- log -30 ---")
    w(g("log", "--oneline", "-30"))
    w("--- status short ---")
    st = g("status", "--short")
    w("\n".join(st.splitlines()[:30]))
    w(f"status_lines_total={len(st.splitlines())}")
    w("--- count ---")
    w(g("rev-list", "--count", "HEAD").strip())
    w("--- first ---")
    w(g("log", "--reverse", "--format=%H %ai %s", "-1").strip())
    w("--- last ---")
    w(g("log", "-1", "--format=%H %ai %s").strip())
    w("--- branches ---")
    w(g("branch", "-a"))
    w("--- remote ---")
    w(g("remote", "-v"))

# --- SCHEMA + first verse ---
w("=== GENESIS SCHEMA ===")
gen = ROOT / "data_master" / "genesis_final.json"
# File is minified; load carefully
data = json.loads(gen.read_text(encoding="utf-8"))
for k in ("_schema", "_source", "_parser", "_book", "book", "slug", "label"):
    if k in data:
        w(f"{k}={json.dumps(data[k], ensure_ascii=False)[:2000]}")
# top-level keys
w(f"top_keys={list(data.keys())[:40]}")
verses = data.get("verses") or []
w(f"n_verses={len(verses)}")
if verses:
    v0 = verses[0]
    w(f"first_verse_keys={list(v0.keys())}")
    w(f"first_ref={v0.get('chapter')}:{v0.get('verse')}")
    pairs = v0.get("pairs") or []
    w(f"n_pairs={len(pairs)}")
    if pairs:
        p0 = pairs[0]
        w(f"pair0_keys={list(p0.keys())}")
        hws = p0.get("he_words") or []
        w(f"n_he_words_pair0={len(hws)}")
        if hws:
            w(f"he_word0={json.dumps(hws[0], ensure_ascii=False)[:3000]}")

# es_source counts
w("=== ES_SOURCE COUNTS ===")
src = Counter()
n_tokens = 0
for v in verses:
    for p in v.get("pairs") or []:
        for hw in p.get("he_words") or []:
            n_tokens += 1
            s = hw.get("es_source")
            if s is None or s == "":
                src["(empty/None)"] += 1
            else:
                src[str(s)] += 1
w(f"n_tokens={n_tokens}")
for k, c in src.most_common():
    w(f"  {c}\t{k}")

# --- EXODO ---
w("=== EXODO ===")
for pat in ["exodo*", "exodus*", "shemot*"]:
    pass
ex_files = list((ROOT / "data_master").glob("exodo*")) + list((ROOT / "data_master").glob("exodus*")) + list((ROOT / "data_master").glob("shemot*"))
w(f"exodo_files={[str(p.name) for p in ex_files]}")
ex_path = ROOT / "data_master" / "exodo_final.json"
if ex_path.exists():
    ex = json.loads(ex_path.read_text(encoding="utf-8"))
    for k in ("_schema", "_source", "_parser", "_book", "book", "slug", "label"):
        if k in ex:
            w(f"ex_{k}={json.dumps(ex[k], ensure_ascii=False)[:1500]}")
    w(f"ex_top_keys={list(ex.keys())[:40]}")
    ev = ex.get("verses") or []
    w(f"ex_n_verses={len(ev)}")
    # es populated?
    empty_es = 0
    filled_es = 0
    total_hw = 0
    for v in ev:
        for p in v.get("pairs") or []:
            for hw in p.get("he_words") or []:
                # skip meta?
                total_hw += 1
                es = (hw.get("es") or "").strip()
                if es:
                    filled_es += 1
                else:
                    empty_es += 1
    w(f"ex_total_hw={total_hw} filled_es={filled_es} empty_es={empty_es}")
    # sample first hw with es
    sample = None
    for v in ev[:3]:
        for p in v.get("pairs") or []:
            for hw in p.get("he_words") or []:
                if (hw.get("es") or "").strip():
                    sample = {"ch": v.get("chapter"), "vs": v.get("verse"), "es": hw.get("es"), "es_source": hw.get("es_source"), "he_form": hw.get("he_form"), "strongs": hw.get("strongs")}
                    break
            if sample:
                break
        if sample:
            break
    w(f"ex_sample={json.dumps(sample, ensure_ascii=False)}")

# search _book Exodus / Éxodo
w("=== SEARCH _book Exodus ===")
found = []
for p in (ROOT / "data_master").glob("*_final.json"):
    # peek first 500 chars
    head = p.read_text(encoding="utf-8")[:800]
    if '"Exodus"' in head or '"Éxodo"' in head or '"Exodo"' in head or '"exodo"' in head.lower()[:200]:
        found.append(p.name)
w(f"books_mentioning_exodus={found}")

# --- BAK files ---
w("=== BAK FILES ===")
baks = list((ROOT / "data_master").glob("*.bak_*")) + list((ROOT / "data_master").glob("*.bak*"))
# dedupe
baks = sorted(set(baks), key=lambda p: p.stat().st_mtime)
w(f"n_bak={len(baks)}")
if baks:
    total_sz = sum(p.stat().st_size for p in baks)
    w(f"bak_total_bytes={total_sz}")
    w(f"bak_oldest={baks[0].name} mtime={baks[0].stat().st_mtime}")
    w(f"bak_newest={baks[-1].name} mtime={baks[-1].stat().st_mtime}")
    import datetime
    w(f"bak_oldest_dt={datetime.datetime.fromtimestamp(baks[0].stat().st_mtime)}")
    w(f"bak_newest_dt={datetime.datetime.fromtimestamp(baks[-1].stat().st_mtime)}")

# backup folders
w("=== BACKUP FOLDERS ===")
for pattern in ["backup*", "respaldo*", "old*", "Bak*", "BACKUP*"]:
    hits = list(ROOT.glob(pattern)) + list(ROOT.glob(f"**/{pattern}"))
    # limit
    hits = [h for h in hits if h.is_dir()][:20]
    if hits:
        w(f"{pattern}: {[str(h.relative_to(ROOT)) for h in hits]}")

# --- TESTS ---
w("=== TESTS ===")
tests_dir = ROOT / "tests"
for p in sorted(tests_dir.rglob("*.py")):
    text = p.read_text(encoding="utf-8")
    # count def test_
    n = sum(1 for line in text.splitlines() if line.strip().startswith("def test_"))
    w(f"{p.relative_to(ROOT)}: def_test_={n} bytes={p.stat().st_size}")

# also motores/scripts/test_*.py
for p in sorted((ROOT / "motores" / "scripts").glob("test_*.py")):
    text = p.read_text(encoding="utf-8")
    n = sum(1 for line in text.splitlines() if line.strip().startswith("def test_"))
    w(f"{p.relative_to(ROOT)}: def_test_={n}")

# search for tests of translit/candado/estilo/servidor
w("=== TEST COVERAGE HINTS ===")
for name in ["translit", "candado", "estilo_usuario", "servidor"]:
    hits = []
    for p in list(tests_dir.rglob("*")) + list((ROOT / "motores" / "scripts").glob("test_*.py")):
        if p.is_file() and p.suffix == ".py":
            t = p.read_text(encoding="utf-8")
            if name in t.lower() or name.replace("_", "") in t.lower():
                hits.append(str(p.relative_to(ROOT)))
    w(f"{name}: {hits}")

# MD files summary
w("=== MD FILES ===")
for p in sorted(ROOT.rglob("*.md")):
    if ".pytest_cache" in str(p) or "node_modules" in str(p):
        continue
    try:
        first = ""
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("```"):
                first = line[:120]
                break
        w(f"{p.relative_to(ROOT)} | {first}")
    except Exception as e:
        w(f"{p.relative_to(ROOT)} | ERR {e}")

# absolute path deps existence check
w("=== EXTERNAL PATHS ===")
paths = [
    Path(r"C:\Users\pik_y\Documents\TRADUCCION\BIBLIAS"),
    Path(r"C:\Users\pik_y\Documents\GitHub\Local-consults\estudio\angelos"),
    Path(r"C:\Users\pik_y\Documents\GitHub\Local-consults\estudio\angelos\diccionario\pruebas\01Génesis.json"),
    Path(r"C:\Users\pik_y\Documents\GitHub\Local-consults\estudio\angelos\IdiomaORIGEN\macula-hebrew.tsv"),
    Path(r"C:\Users\pik_y\Documents\TRADUCCION\parabible\scripts"),
]
for p in paths:
    w(f"exists={p.exists()} path={p}")

# check local fuentes for idx
w("=== LOCAL IDX / FUENTES ===")
for pat in ["*_idx*", "*strong*", "rv1960*", "rvr*", "macula*", "catss*", "oshb*"]:
    hits = list(ROOT.rglob(pat))[:15]
    if hits:
        w(f"{pat}: {[str(h.relative_to(ROOT)) for h in hits]}")

OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"WROTE {OUT} lines={len(lines)}")
