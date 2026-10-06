# Referencia BHSA local (piloto Génesis 10)

Export morfológico **ETCBC/BHSA** vía text-fabric para contrastar con `genesis_final.json`.
Las **auditorías de revisión** (B0–B7/B8) viven en `../scripts/` — no en esta carpeta.

## Estructura

```
parabible/
  README.md
  genesis/10/
    bhsa_words.json, bhsa_verses.json, meta.json
    diff_report.md              # diff BHSA vs genesis_final
  scripts/
    export_bhsa_chapter.py      # export BHSA por capítulo
    diff_genesis10.py           # diff hebreo vs BHSA
```

## Auditorías integradas (scripts/)

| Comando | Bloque |
|---------|--------|
| `audit_gen_chapter_struct.py N` | B1–B4 hebreo vs OSHB |
| `audit_gen_chapter_lxx.py N` | B8 morfema |
| `audit_gen_chapter_lxx_rahlf.py N` | B8+ Rahlfs + greek_hidden |
| `verify_verse_mlxx.py N V` | Detalle verso |
| `audit_chapter_full.py N` | B7 (incluye B8 + B8+) |

Ver [REVISION_CAPITULO.md](../scripts/REVISION_CAPITULO.md).

## Export BHSA

```powershell
cd C:\Users\pik_y\Documents\TRADUCCION\parabible\scripts
python export_bhsa_chapter.py --book Genesis --chapter 10
python diff_genesis10.py
```

Corpus: **ETCBC/bhsa** (text-fabric). CC BY-NC 4.0.
