# Recopilación post-motor · Génesis 25→50
Corrida: `--apply` 25-50 (981 arreglos) · respaldo `genesis_final.json.bak_revisar_es_20260812_142659`

## ✅ REFUERZO DEL MOTOR COMPLETADO (2026-08-12 · 16:16)
Todo lo hallado (R1–R13 + BUG2) se convirtió en lógica GENERAL del motor (no parches
puntuales), con tests anti-regresión (95 motor + 55 latam, todo verde). Segundo pase
`--apply` 25-50 = **243 arreglos** · respaldo `...bak_revisar_es_20260812_161623`.

Reparación previa de corrupciones del 1er pase: **22 posesivos BUG2** restaurados desde
respaldo + **3 «de» sobre verbo/adverbio** revertidos (28:8/29:7/36:18). 27:8 ya revertido.

| Ítem | Antes | Ahora (motor) |
|---|---|---|
| BUG2 | `check_poses` ignoraba número → «mi padre» por «nuestro» | **el sufijo hebreo manda**: `poss_rehome` reconstruye persona+número y concuerda (mi↔nuestro/su/tu) — 160 autofix |
| R8 | «su mi padre» quedaba en reporte | mismo `poss_rehome`: despoja el posesivo espurio de la raíz |
| R5 | עם(PREP) «pueblo» solo reporte | **autofix** «con» (+ fusión con·mí/ti/sí → conmigo/contigo/consigo) — ~40 |
| R13 | ילד «luz» solo reporte | **autofix** «dio/dar/dará/dieron a luz» según tiempo — 26 |
| R1 | RECORRIDO falso positivo en repetición hebrea | omite si esqueleto = vecino (אדם/בין/קול) |
| R2 | TIEMPOVERBAL solo -ar/tabulado | + **-er/-ir regulares** (abrir→abrió); excluye stem-changers |
| R3 | HOMOGRAF שם solo si «poner» | (mantiene) שם/שמה ADV→allí, שֵׁם→nombre |
| R6 | ESTILO sugería a nombres propios | guarda `looks_proper` + NPROP (no «Sheba→siete») |
| R10 | dios/el minúscula sin señal | **reporte** en MORPH_MISMATCH (no autofix: hay dioses ajenos) |
| R11 | PRON despojaba VERBO (29:19) | **guarda**: PRON nunca sobre VERBO |
| R4 | CORTO sin pista | reporte + palabra probable (lexema/estadística) |
| CONSTRUCT | añadía «de» a glosa verbal/adverbial | **guarda**: no «de» sobre adverbio/verbo (todavía/parecían) |

Verificado en datos: 31:1 «de nuestro padre», 27:22 «su padre», 26:20 «con él»,
26:28 «contigo», 29:32 «dio a luz», 30:3 «dará a luz», 26:18 «abrió».
Restan (por diseño): CONCORD de artículos (reporte), 7 CONSTRUCT PROTEGIDOS (respetados),
2 POSES ambiguos (reporte), MORPH_MISMATCH/MORFO/ESTILO (criterio del usuario).

## 🔴🔴 BUG GRAVE ENCONTRADO Y CORREGIDO DE RAÍZ
- **PENINSULAR corrompía datos con léxico moderno de España.** `es_latam_neutral.py::_LEXICON`
  mapeaba vocabulario actual (ordenador→computadora, coche→carro, zumo→jugo, **mando→"control remoto"**…).
  Varios "orígenes" son HOMÓGRAFOS de palabras bíblicas: **mando** (verbo, צוה), **piso** (pisar),
  **vale** (valer), grifo, coger… En 27:8 `מְצַוָּה` "mando" → **"control remoto"**.
  - FIX: `_LEXICON` **desactivado** (={}) para el corpus bíblico; se conserva la conversión
    GRAMATICAL (vosotros→ustedes, -áis/-éis/-asteis…, imperativos, os→les, vuestro→su).
  - 27:8 revertido a "mando". Escaneo 25-50: **solo ese token** fue afectado por el léxico.
  - Tests: latam 55/55, motor 70/70.

## Candidatos a REFORZAR el motor (transversales)
- [R8] **POSES posesivo corto apilado**: raíz "mi padre/hermano" + sufijo su/tu → "su mi padre". Hoy
  queda "(sin sug)" por conflicto de persona; el sufijo es la autoridad → despojar la raíz ("padre").
  Muy recurrente (12+ en cap 27: אָבִי/אָחִי).
- [R9] MORPH_MISMATCH homógrafos: 27:25 `למען` "bendiga" (recorrido), 27:45 `שני` "escarlata"→"dos/años de".
- [R1] **RECORRIDO falso positivo** cuando la forma hebrea se repite de verdad (אדם אדם 25:30; בין…בין 26:28). Debe omitir si `he_form` (esqueleto) es idéntico al vecino, aunque falte el Strong.
- [R2] **TIEMPOVERBAL autofix** solo cubre QAL -ar/irregulares tabulados. Ampliar a **-er/-ir regulares** (p.ej. abrir→abrió, 26:18).
- [R3] **HOMOGRAF** solo corrige שם glosado como "poner/puso". Extender a שָׁם(ADV) glosado **"nombre"→"allí"** (26:25).
- [R4] **CORTO grave**: sustantivo glosado SOLO **"y"** (perdió la palabra de contenido): esposa/padre/tienda/hermano (7:5, 18:9, 25:8, 31:4). Subir prioridad (tipo VACIO) y ligar a recuperar lexema.
- [R5] **עם (PREP) "pueblo"→"con"**: 6 casos en cap 26. Evaluar autofix de raíz (hoy solo reporte).
- [R6] **ESTILO** no debe sugerir número para NOMBRES propios homógrafos (Sheba/Shibá 26:33 "siete").
- [R7] **PENINSULAR + tiempo**: al pasar vosotros→ustedes debe respetar el tiempo hebreo (26:27 venís→"vienen" pero QATAL=pasado→"vinieron").

## CAP 25 — limpio (motor cambió 0)
- SINTAXIS 25:23 `לְ` "su"→tónica (reporte).
- RECORRIDO 25:30 `אדם` "rojo rojo" = repetición real → FALSO POSITIVO [R1].
- ESTILO: 18 (construct "de"↔sin de, Qédem, campo). No errores.

## CAP 26 — 37 cambios del motor; revisados
### Errores NUEVOS dejados/introducidos por el motor
- 26:24 `אֱלֹהֵי` → "dios de" pero debe ser **"Dios de"** (Dios de Abraham; minúscula preexistente + CONSTRUCT).
- 26:27 `בָּאתֶם` → "vienen" (PENINSULAR arregló dialecto) pero QATAL=pasado → **"vinieron"** [R7].
- 26:34 `בֶּן` → "hijo de (cuarenta años)"; idiom de edad, prefieres **"hombre de"**.
### Deberían haberse resuelto y NO (reporte, recurrentes)
- עם PREP "pueblo"→con: 26:3,16,20,28,29(x2) [R5].
- CORTO "su y" (contenido perdido): esposa 26:7, padre 26:18, tienda 26:25, hermano 26:31 [R4].
- Posesivo apilado "su/tu mi padre": 26:3, 26:24 (אבי).
- MORFO 26:18 `יַּחְפֹּר` "abrir"→"abrió" (no autofix por ser -ir) [R2].
- HOMOGRAF 26:25 `שָׁם` "nombre"→"allí" [R3].
- 26:34(p0) `יְהִי` verbo glosado "de" (recorrido de preposición) — verbo sin glosa.
- SINTAXIS לְ "su"→tónica: 26:18(x2),26:22,26:30.
### Falsos positivos
- RECORRIDO 26:28 `בין…בין` "entre" repetido = repetición real [R1].
### CONCORD artículo (reporte seguro): 26:3,26:4,26:12,26:24 (los/el ante demostrativo).
### ESTILO (24): estilo; OJO 26:33 "seba/beerseba"→"siete" es SUGERENCIA ERRÓNEA (nombre propio) [R6].

## CAP 27 — 38 cambios del motor; revisados
### Errores NUEVOS por el motor
- **27:8 `מְצַוָּה` "mando"→"control remoto"** (bug PENINSULAR) → CORREGIDO Y REVERTIDO. Ver arriba.
- Resto de cambios (37) correctos: CONSTRUCT «de», strip pronombre PREP, su→sus (ojos/manos), idiom הנני "heme aquí".
### Deberían haberse resuelto y NO (reporte)
- **CORTO/RENDER "su y"** (contenido perdido, MUY recurrente): בְּנ/אִמּ/אָבִי/קֹל glosados solo "y" (27:5,14,18,30,31,38,39…).
- **POSES "su/tu mi padre"** [R8]: 27:9,10,22,23,29,30,31,32,34(x2),37 — raíz con posesivo corto + sufijo.
- MORPH_MISMATCH: 27:25 `למען` "bendiga"; 27:44 `עמ` "pueblo"→con; 27:45 `שני` "escarlata"→"dos/años de" [R9].
- CORTO verbo/adj: 27:25 `תברכ`→"yo"; 27:15 `סמכתי`→"y" (recorrido); 27:38 `אחת`→"una".
- SINTAXIS לְ "su/tu"→tónica: 27:13, 27:37.
- RENDER RVR remanente: 27:20 "mi por si acaso".
### Falsos positivos / seguros
- RECORRIDO 27:22 `קול/ידי` "voz/manos" repetido (posible repetición real) [R1].
- CONCORD 27:9 "el rebaños"→"los" (reporte).
### ESTILO (29): estilo; he aquí/ahora, dijo/respondió, hiciste/hecho.

## CAP 28 — 23 cambios; revisados
### Errores nuevos/empeorados
- 28:8 `עֵינֵי` "parecían"→"parecían de" (CONSTRUCT sobre glosa verbal errónea; debía ser "ojos de").
- 28:13 `אֱלֹהֵי` "dios de"×2 → "Dios de" [R10].
### Reporte
- CORTO "su y": אָבִי 28:7, אִמּ 28:7, שְּׁנָת 28:16 [R4].
- MORPH_MISMATCH: 28:2 `לְ`"ir"; 28:19 `עלי`"daré"; 28:15 `עמ`"pueblo"→con; 28:20 `עמדי`"parado"→conmigo.
- MORFO 28:3 `יַפְרְ` Hif "fructificar"→finito. 28:5 `יָמָּ` "la al oeste". TRANSLIT 28:19 `אֵל`"el"→"'El".
- SINTAXIS לְ→tónica 28:15,22; DOBLE 28:20 "en en".
### ESTILO (17): 28:21 `אלהים`"dios"→"'Elohim" [R10].

## Nuevo transversal
- [R10] **Nombre divino en minúscula**: אלהים/אלהי/אל glosado "dios"/"el" refiriéndose a Dios → "Dios"/"'Elohim"/"'El". Recurrente (26:24, 28:13, 28:19, 28:21).
- [R11] **PRON/strip no debe correr sobre morfología VERBO** (29:19 תתי VERBO "a ella"→"a").
- [R12] **Inglés residual en datos** ("that" en 29:32); MALFORM lo detecta pero es report-only.

## CAP 29 — 33 cambios; revisados
### Errores nuevos/empeorados
- 29:7 `עֵת` "todavía"→"todavía de" (CONSTRUCT sobre glosa mala; debía ser "tiempo de").
- 29:19 `תִּתִּי` VERBO "a ella"→"a" (PRON sobre verbo) [R11].
### Datos a corregir (motor lo detectó)
- 29:32 `כִּי` "that" — INGLÉS sin traducir → "porque/ciertamente" [R12].
### Reporte
- CORTO "su y": אִמּ 29:10, קֹל 29:11, בֵּית 29:13, בִתּ 29:23 [R4]. Verbo "y/a": קְרָאת 29:13, תִּתִּ 29:19.
- POSES "su mi padre": 29:12,13 [R8]. MORPH_MISMATCH עמ→con (29:9,14,25,30), עמדי→conmigo (29:19,27).
- CONCORD צאן "las/el"→"los" (29:3,7,8,9); 29:19 "los cosas". SINTAXIS לְ→tónica (29:4,5,6,19).
### Menores
- 29:17 `יפת` "lindo" vs "hermoso" (inconsistencia). EUFONIA 29:13 "e vayan" no aplicó (revisar).
### ESTILO (18): Qédem/oriente, rebaños/ovejas, asuntos/cosas, tarde/noche.

## CAP 30 — 25 cambios; todos sanos (borderline 30:37 מחשף "descubriendo de")
### Reporte
- CORTO "su y": בֵּן 30:7, אִמּ 30:14, בַדּ 30:40; verbo קְרָאת 30:16 [R4].
- RECORRIDO verbo: 30:20 `יזבלני` "me mi marido"; 30:15 `לָ` "¿Es".
- MORPH_MISMATCH: עמ→con (30:15,16,19); 30:34 `לוּ` "a él"→"ojalá/si tan solo".
- POSES "sus mis hijos" 30:35 [R8]. MORFO 30:31 `ארעה`→finito. CONCORD צאן→los (30:38-42).
- RECORRIDO 30:36 בין repetido = real [R1].
### ESTILO (29): `תלד/ילד` "luz"→"dio a luz" (30:10,12,17,23,25) [R13]; hijas/mujeres.

## Nuevo transversal
- [R13] **Verbo de parto `ילד/תלד` glosado "luz"** → "dio a luz" (truncado de "dar a luz"). Recurrente, recuperable (autofix candidato).

## 🔴🔴 BUG #2 (check_poses) — CORRUPCIÓN DE PERSONA/NÚMERO
- `check_poses` (líneas 1075-1078) compara SOLO persona (1/2/3), **ignora número**.
  → raíz "mi/mis" (1ª SING) + sufijo hebreo "nuestro/nuestros" (1ª PLURAL) se tratan como
    redundantes → **borra el sufijo correcto** y deja "mi/mis" → renderiza "MI padre" cuando
    el texto dice "NUESTRO padre". El sufijo hebreo es la autoridad.
- Alcance en 25-50: **33 sufijos borrados**; **~22 corrupción real 1ª pl** (mi/mis + nuestro):
  31:1×2,31:14,31:16×2,31:32, 34:9,34:16,34:21, 37:26,37:27, 42:13,42:21,42:32×2,
  43:4,43:28, 44:25,44:26×2,44:31, 46:34. (Los 11 de 3ª pers. "sus ovejas"+"su" quedaron BIEN.)
- FIX pendiente (a confirmar): (a) guard número en check_poses; (b) corregir los 22 tokens
  con el respaldo → raíz "nuestro/nuestros/nuestra/nuestras + sustantivo" (según género/nº del nombre).

## CAP 31 — 59 cambios; revisados
### Errores nuevos por el motor
- **BUG #2 arriba**: 31:1×2,31:14,31:16×2,31:32 "mi/mis"↔"nuestro" (persona equivocada).
- 31:5,29,42,53 `אלהי` "dios de" → "Dios de" [R10].
### Reporte (recurrentes)
- POSES "su mi padre" (sin sug): 31:5,6,7,9,19,23,29,30,32,37,41,43,46,53,54 [R8].
- MORPH_MISMATCH עמ→con / עמדי→conmigo (múltiples). CORTO "su y": 31:5,12 etc [R4].
- CONCORD צאן→los (31:8,10,12,43); 31:21 "el eufrates"→"los". SINTAXIS לְ→tónica.
