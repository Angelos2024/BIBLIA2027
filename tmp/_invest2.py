# -*- coding: utf-8 -*-
"""Extra facts for investigation."""
import json
from pathlib import Path
from collections import Counter

ROOT = Path(r"C:\Users\Angelos\Desktop\BIBLIA2027")
OUT = ROOT / "tmp" / "_invest_out2.txt"
lines = []
def w(s=""): lines.append(s)

# book_config resolved paths for exodo
import sys
sys.path.insert(0, str(ROOT / "motores" / "scripts"))
from book_config import resolve
cfg = resolve("exodo")
w("=== EXODO book_config paths ===")
w(f"par_path={cfg.par_path} exists={cfg.par_path.exists()}")
w(f"oshb_dir={cfg.oshb_dir} exists={cfg.oshb_dir.exists()}")
w(f"snap_dir={cfg.snap_dir} exists={cfg.snap_dir.exists()}")
w(f"inter_dir={cfg.inter_dir} exists={cfg.inter_dir.exists()}")
w(f"idx_es={cfg.idx_es_path} exists={cfg.idx_es_path.exists()}")
w(f"idx_he={cfg.idx_he_path} exists={cfg.idx_he_path.exists()}")
w(f"final={cfg.final_json_path} exists={cfg.final_json_path.exists()}")
w(f"check_sources={cfg.check_sources()}")

cfgg = resolve("genesis")
w("=== GENESIS book_config paths ===")
w(f"par_path={cfgg.par_path} exists={cfgg.par_path.exists()}")
w(f"oshb_dir={cfgg.oshb_dir} exists={cfgg.oshb_dir.exists()}")
w(f"snap_dir={cfgg.snap_dir} exists={cfgg.snap_dir.exists()}")
w(f"idx_es={cfgg.idx_es_path} exists={cfgg.idx_es_path.exists()}")
w(f"check_sources={cfgg.check_sources()}")

# local fuentes catss
w("=== LOCAL CATSS ===")
local_par = ROOT / "fuentes" / "catss-par" / "02.Exodus.par"
w(f"local_exodus_par={local_par} exists={local_par.exists()} size={local_par.stat().st_size if local_par.exists() else 0}")

# idx in fuentes vs BIBLIAS
w("=== IDX LOCATIONS ===")
for base in [ROOT/"fuentes", ROOT/"BIBLIAS"]:
    hits = list(base.glob("_idx_strong_es_exodo.json")) + list(base.glob("_idx_strong_es_gen.json")) + list(base.glob("_idx_strong_es_genesis.json"))
    w(f"{base.name}: {[h.name for h in hits]}")

# exodo es_source distribution
w("=== EXODO es_source ===")
ex = json.loads((ROOT/"data_master"/"exodo_final.json").read_text(encoding="utf-8"))
src = Counter()
n=0
filled=0
empty=0
for v in ex["verses"]:
    for p in v.get("pairs") or []:
        for hw in p.get("he_words") or []:
            n+=1
            es=(hw.get("es") or "").strip()
            if es: filled+=1
            else: empty+=1
            s=hw.get("es_source")
            src[str(s) if s else "(empty/None)"] += 1
w(f"tokens={n} filled={filled} empty={empty}")
for k,c in src.most_common(40):
    w(f"  {c}\t{k}")

# genesis first verse ALL he_words fields union
w("=== GENESIS 1:1 all he_word field keys ===")
keys=set()
for p in ex["verses"][0]["pairs"] if False else json.loads((ROOT/"data_master"/"genesis_final.json").read_text(encoding="utf-8"))["verses"][0]["pairs"]:
    for hw in p.get("he_words") or []:
        keys |= set(hw.keys())
w(f"keys_sorted={sorted(keys)}")

# dump first verse compact (all pairs abbreviated)
gen = json.loads((ROOT/"data_master"/"genesis_final.json").read_text(encoding="utf-8"))
v0 = gen["verses"][0]
w(f"genesis_1_1_n_pairs={len(v0['pairs'])}")
for i,p in enumerate(v0["pairs"]):
    w(f" pair{i} kind={p.get('kind')} he={p.get('he')} gr={p.get('gr')} n_hw={len(p.get('he_words') or [])}")
    for j,hw in enumerate(p.get("he_words") or []):
        w(f"  hw{j}: he_form={hw.get('he_form')!r} morph={hw.get('he_morph')!r} strongs={hw.get('strongs')!r} es={hw.get('es')!r} es_source={hw.get('es_source')!r} prefix_es={hw.get('prefix_es')!r} gr_word={hw.get('gr_word')!r}")

# how revisar_es sets es_source
w("=== revisar_es es_source assignments ===")
import re
text = (ROOT/"motores"/"scripts"/"revisar_es.py").read_text(encoding="utf-8")
# find patterns
for m in re.finditer(r".{0,40}es_source.{0,80}", text):
    s=m.group(0).replace("\n"," ")
    if "es_source" in s and ("=" in s or "set" in s or "source" in s):
        pass
# more targeted
for i,line in enumerate(text.splitlines(),1):
    if "es_source" in line and ("=" in line or "autofix" in line.lower() or "source" in line):
        if any(x in line for x in ["es_source =", "es_source=", "['es_source']", '["es_source"]', "es_source':"]):
            w(f"L{i}: {line.strip()[:160]}")

# apply_corrections glosas path
w("=== apply_corrections glosas path context ===")
ac = (ROOT/"motores"/"scripts"/"apply_corrections.py").read_text(encoding="utf-8")
for i,line in enumerate(ac.splitlines(),1):
    if "glosas_personales" in line or "estadistica" in line or "refuerzo" in line:
        w(f"L{i}: {line.strip()[:160]}")

# docs PROCESO
w("=== DOC FILES referenced ===")
for name in ["PROCESO_CORRECCIONES.md","REVISION_CAPITULO.md"]:
    hits=list(ROOT.rglob(name))
    w(f"{name}: {[str(h.relative_to(ROOT)) for h in hits]}")

# test coverage detail
w("=== TEST FILE DETAIL ===")
tt=(ROOT/"tests"/"test_revisar_es.py").read_text(encoding="utf-8")
w(f"def_test_count={sum(1 for l in tt.splitlines() if l.strip().startswith('def test_'))}")
for name in ["candado","estilo_usuario","translit_nombres","servidor","aplicar_translit","build_canon"]:
    w(f"mentions_{name}={tt.lower().count(name.lower())}")

# motors/scripts tests
for p in (ROOT/"motores"/"scripts").glob("test_*.py"):
    t=p.read_text(encoding="utf-8")
    w(f"{p.name} lines={len(t.splitlines())} has_main={'if __name__' in t}")
    # first 30 lines summary
    w("  head: "+t.splitlines()[0][:120])

# check if run_motors mentions hebrew_rules / greek_rules / apply_corrections
rm=(ROOT/"motores"/"scripts"/"run_motors.py").read_text(encoding="utf-8")
w(f"run_motors_mentions_hebrew_rules={'hebrew_rules' in rm}")
w(f"run_motors_mentions_greek_rules={'greek_rules' in rm}")
w(f"run_motors_mentions_apply_corrections={'apply_corrections' in rm}")
w(f"run_motors_mentions_hebrew_clean={'hebrew_clean' in rm}")

# process_book includes corrections
pb=(ROOT/"motores"/"scripts"/"process_book.py").read_text(encoding="utf-8")
w(f"process_book_steps_with_corrections={'corrections' in pb}")

# populate absolute paths vs local macula
w(f"local_macula={(ROOT/'fuentes'/'macula-hebrew.tsv').exists()}")
w(f"populate_hardcoded_ANGELOS_macula=C:\\Users\\pik_y\\...\\macula-hebrew.tsv")

# diccionario local?
w("=== DICCIONARIO ===")
for p in list((ROOT/"fuentes").glob("*dic*")) + list(ROOT.glob("**/01Génesis.json"))[:5] + list(ROOT.glob("**/01Genesis.json"))[:5]:
    w(f"  {p.relative_to(ROOT)}")

OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"WROTE {OUT}")
