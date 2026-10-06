# Génesis 10 — revisión general del capítulo

**Fecha:** 2026-05-31  
**Datos:** `genesis_final.json` vs LXX Rahlfs local, mlxx, BHSA (text-fabric)

---

## Resumen ejecutivo

| Capa | Versos | Estado |
|------|--------|--------|
| **LXX Rahlfs** (multiset + orden + B8) | 32/32 | OK — ningún token griego faltante |
| **mlxx** (conteo morfológico) | 32/32 | OK — `issues=0` en todos |
| **B8** (`audit_gen_chapter_lxx.py`) | 32/32 | OK — 0 incidencias |
| **BHSA hebreo** (conteo + tokens) | 20/32 idénticos | 12 versos estructurales (sufijos/pronominales) |

**Conclusión LXX:** capítulo cerrado en B8 + B8+ (Rahlfs local). Ver `scripts/audit_gen10_lxx_rahlf.txt`.

---

## Correcciones aplicadas en esta sesión

| Verso | Par | Cambio |
|-------|-----|--------|
| 10:1 | 8 | `αὐτοῖς` → `kind: gk_add` (ya estaba en sesión anterior) |
| 10:19 | 4, 9 | `ἕως` oculto en stub `GKADD` → promovido a `gk_add` |
| 10:30 | 3 | `ἕως` oculto → promovido a `gk_add` |

Parches persistentes en `apply_corrections.py` → `_fix_gen10_oshb_align` (vrs 1, 19, 30).

---

## gk_add del capítulo (griego sin hebreo OSHB)

| Verso | Tokens LXX adicionales |
|-------|------------------------|
| 10:1 | αὐτοῖς |
| 10:2 | καὶ ελισα |
| 10:9 | τοῦ θεοῦ |
| 10:18 | τοῦτο |
| 10:19 | ἕως (×2, sin hebreo; el tercer ἕως en par 15 sí alinea con עַד) |
| 10:22 | καὶ καιναν |
| 10:24 | τὸν καιναν, καὶ καιναν, ἐγέννησεν |
| 10:30 | ἕως |
| 10:32 | νῆσοι |

---

## Versos LXX limpios (32/32)

Todos los versos tienen coincidencia exacta de multiset entre LXX Rahlfs y `gr_unicode` agregado por pares. Detalle por verso en `lxx_audit_ch10.json`.

Conteos mlxx = conteos en data (verificado verso a verso):

```
10:1→17  10:2→17  10:3→8   10:4→8   10:5→22  10:6→9   10:7→18  10:8→12
10:9→17  10:10→17 10:11→17 10:12→15 10:13→14 10:14→13 10:15→9  10:16→9
10:17→9  10:18→17 10:19→24 10:20→19 10:21→15 10:22→13 10:23→10 10:24→15
10:25→24 10:26→12 10:27→6  10:28→4  10:29→10 10:30→13 10:31→19 10:32→24
```

---

## Hebreo vs BHSA — 12 versos estructurales

Estos diffs **no afectan la cobertura LXX**; son diferencias de tokenización OSHB/CATSS vs BHSA (sufijos pronominales fusionados vs separados, splits de toponimios):

| Verso | Tipo principal |
|-------|----------------|
| 10:1 | Falta `להם` en data (LXX tiene αὐτοῖς como gk_add) |
| 10:5, 10:20, 10:31 | Sufijos `-ם` separados (`ארצת`+`ם` vs `ארצתם`, etc.) |
| 10:8 | Token vacío BHSA; morfología `גבר` ADJ vs noun |
| 10:10, 10:15, 10:25 | Sufijos `-ו` pronominal separados |
| 10:11 | `רחבת` + `עיר` vs `רחבת עיר` (ya parcheado en pipeline) |
| 10:19, 10:30 | Toponimios compuestos (`בא`+`כה` vs `באכה`, etc.) |
| 10:32 | Sufijos + token vacío BHSA |

Versos con **tokens alineados** pero posibles conflictos morfológicos (GENT vs nmpr, PREP vs noun): 10:9, 10:12–14, 10:18, 10:25.

Detalle completo: `diff_report.md`.

---

## Comandos de re-auditoría

```powershell
cd C:\Users\pik_y\Documents\TRADUCCION\scripts

python audit_gen_chapter_lxx.py 10
python audit_gen_chapter_lxx_rahlf.py 10
python verify_verse_mlxx.py 10 1
python audit_chapter_full.py 10 --skip-pipeline
python diff_genesis10.py   # desde parabible/scripts — BHSA opcional
```

---

## Próximos pasos sugeridos

1. **Hebreo estructural:** unificar tokenización de sufijos pronominales en 10:5, 10:20, 10:31 (patrón ya usado en otros capítulos).
2. **Toponimios 10:19 / 10:30:** fusionar `בא`+`כה` → `באכה` en alineación OSHB si se quiere match exacto con BHSA.
3. **Traducción ES:** `gk_add` no genera tokens en `traduccion-tokens.js` — decidir si añadir glosas manuales para los 14 tokens LXX-only.
4. **Traducción ES:** `gk_add` no genera tokens en `traduccion-tokens.js` — decidir glosas manuales si se desea.
