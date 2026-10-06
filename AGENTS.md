# BIBLIA2027 — Guía del proyecto y contrato de seguridad

Editor interlineal **hebreo–griego–español**. El objetivo es afinar la glosa
española (`es`) respetando de forma **absoluta** el texto hebreo, el griego, los
Strong's y la morfología. Este documento fija qué se puede tocar y qué NO.

## Estructura

- `data_master/<libro>_final.json` — datos por versículo. **Están MINIFICADOS**
  (sin saltos de línea). Al reescribir hay que **preservar ese formato** (nada de
  reindentar: causaría un diff gigante y cambiaría el orden de la base).
  - Cada token está en `verses[].pairs[].he_words[]` con campos:
    `he_form`, `he_morph`, `strongs` (INTOCABLES) · `es`, `es_source`,
    `prefix_es`, `prs_suffix.es` (lado español, editables) · `prs_suffix.he_form`,
    `prs_suffix.he_morph`, `prs_suffix.gr_word`, `prefix_morphs` (INTOCABLES).
- `motores/scripts/` — motores. El principal (edición diaria) es `revisar_es.py`.
  - **Pipeline de CONSTRUCCIÓN (legacy)**: `run_motors.py`, `apply_corrections.py`,
    `hebrew_rules.py`, `greek_rules.py`, `hebrew_clean.py`, `populate_es_glosses.py`
    y `parabible/` sirven para **generar un libro nuevo desde cero** (capa hebrea/
    griega/morfología + glosa inicial). **NO** son el corrector de español ni deben
    correrse sobre datos ya cerrados: no consultan el candado ni la barrera de
    inmutabilidad y `apply_corrections.py` aún referencia rutas de otra máquina. El
    refinamiento del lado español es EXCLUSIVAMENTE `revisar_es.py`.
- `fuentes/` — reglas y estado: `glosas_personales.json` (reglas global/contexto),
  `estadistica_glosas.json` (estilo aprendido), `refuerzo_estilo.json` (verdes:
  tu español antes→después; el hebreo solo identifica el token),
  `candado_capitulos.json` + `candado_sellos/` (bloqueo de capítulos),
  `inferencia_strongs.json`.
- `visor/` — UI del editor (`index.html`) servida en `http://localhost:7080/`.
- `tests/test_revisar_es.py` — suite del motor español (runner propio, sin pytest).

## Motor de español — `motores/scripts/revisar_es.py`

Decodifica la morfología hebrea (autoridad) para revisar/corregir la glosa
española. **Contrato duro** (verificado en ejecución):

- SOLO puede modificar: `es`, `es_source`, `prefix_es`, `prs_suffix.es`.
- NUNCA toca: `he_form`, `he_morph`, `strongs`, griego, sufijo hebreo,
  `prefix_morphs`, ni el ORDEN de versos/pares/palabras.
- **Barrera de inmutabilidad**: en `--apply`, tras aplicar, `_huella_intocable` /
  `_verificar_intocable` comparan todo lo INTOCABLE antes/después. Si algo cambió,
  **ABORTA sin escribir** (código de salida 2). Añade tokens al lado español o
  no toca nada.

### AUTOFIX (ERROR objetivo, se aplica) vs REPORTE (elección de ESTILO/léxico)

Distinción rectora (definida por el usuario): **un error** (artículo/preposición
equivocados, género/número/tiempo/persona mal de la MISMA palabra, mayúscula de un
nombre propio) se **auto-corrige**. Una **diferencia de estilo** entre sinónimos
(«beber» vs «abrevar», que significan lo mismo) **no** se corrige a mano: solo la
decide la **estadística de ESTILO** según tu uso acumulado en capítulos cerrados.

- **AUTOFIX** (`AUTOFIX` set): `CANON, PENINSULAR, CONSTRUCT, POSES, CONCORD,
  PRON, PREPRON, HOMOGRAF, EUFONIA, VAV, KI, PEN, CONJUGA, PUNTOCOMA, TIEMPOVERBAL, REFLEX,
  TRANSLIT, GLOSAFUNC, CONTAGIO, REFUERZO`. Correcciones inequívocas e idempotentes (cada op verifica el valor previo).
  - `REFUERZO` — marca **verde** del visor: un error de español que tú ya
    corregiste. El hebreo solo identifica el token; se anota `es_antes`→`es_despues`
    en `fuentes/refuerzo_estilo.json` y el motor **auto-aplica** esa glosa a la
    misma forma (Strong+morfología). No es ESTILO estadístico: es tu corrección
    explícita.
  - `GLOSAFUNC` — **corrupción del build**: un lexema de CONTENIDO (SUBS/ADJ/VERBO)
    cuya glosa RAÍZ es una palabra FUNCIONAL pura (y/de/el/que/su…) —un sustantivo
    no puede ser «y»—; o su SUFIJO posesivo (PRS.\* sobre SUBS/ADJ) glosado con una
    funcional NO posesiva («madre y»→«su madre», Gén 27:13). Era el **hueco de
    eficiencia principal**: `ESTILO` se **abstenía** en lexemas «ambiguos»
    (mujer/esposa…) y la corrupción pasaba en SILENCIO. Ahora se **DETECTA siempre**
    (reporte). **Autofix** solo el subconjunto SEGURO: (raíz) la glosa preferida
    POR-FORMA de tu estadística —que ya desambigua SG/PL/constructo: H802.SG.C→«mujer»,
    no «mujeres»/«tabernáculo»— si es una palabra de contenido ÚNICA y limpia, NOMINAL
    (SUBS/ADJ), con `n≥6` y `pct≥50`; (sufijo) el posesivo que fija la MORFOLOGÍA del
    sufijo (`spanish_poss`, concordando con el sustantivo). Verbos, multipalabra
    («hijo de») y baja confianza → **reporte con candidato** (el lexema/tiempo lo
    eliges tú). Cruza con tu estadística para NO marcar glosas que sí usas (numeral
    «un» de H259). Validado: **0 autofix** en los capítulos de Génesis ya cerrados.
    Ver `check_glosafunc`, `check_suf_func`, `_GLOSA_FUNC`, `estilo_usuario.glosa_conocida`.
 - `VAV` — el vav del **WAYYIQTOL** es el vav CONSECUTIVO narrativo: su prefijo
 `CONJ` tiene UNA sola glosa correcta, «y» (o «e» eufónico, que resuelve
 `EUFONIA`). **Cualquier otra glosa del vav se auto-corrige a «y»**, porque el
 wayyiqtol NO admite subordinación en el propio vav: ni PROPÓSITO/FINAL («para
 que»/«para»/«a fin de que»…: «para que luchaban»→«y luchaban», 25:22), ni
 SUBORDINANTE/CONDICIONAL («que»/«si»/«como»/«hasta que»: «que preguntaron»→«y
 preguntaron», 26:7), ni —peor— una corrupción del build («su»/«sus»/«ella a»…).
 El matiz subordinante que a veces acompaña (`וַיְהִי כַּאֲשֶׁר` = «y sucedió
 CUANDO…») lo aporta SIEMPRE el término siguiente (`אֲשֶׁר`/infinitivo con prefijo
 כ), nunca el vav; por eso normalizar el vav a «y» no pierde nada. El propósito
 solo cabe ante volitivo (cohortativo/yusivo/imperfectivo), que NO es wayyiqtol y
 NO se toca. El prefijo CONJ VACÍO se deja a otra pasada (glosa ausente, no
 corrupción del sentido). Ver `_VAV_PROPOSITO`, `check_vav_wayyiqtol`.
 - `KI` — el lexema `כִּי` (H3588) es una CONJUNCIÓN SUBORDINANTE
 (que/porque/cuando/pues/ciertamente/sino…) y **JAMÁS** la copulativa «y» (esa es
 el waw `ו`). Detectar la «y» es determinista; el valor correcto NO (depende del
 contexto), así que —como el **default «a» de `PREPRON`**— se **suple el default
 «que»** (glosa más común) y el usuario ajusta a mano el causal «porque» / temporal
 «cuando» donde el contexto lo pida. Dos correcciones: (a) «y» **espuria en el
 prefijo** de un `כי` cuya grafía NO empieza por vav → se **quita** (basura del
 build; solo `וְכִי` con vav real llevaría conjunción); (b) el propio lexema glosado
 «y» → «que» («y preguntaron [los hombres] … y [que]»→«… que», Gén 26:7). Se
 identifica por Strong H3588 o por esqueleto `כי`. Alcance validado: 88 autofix en
 capítulos abiertos de Génesis; el capítulo cerrado se respeta (candado). Ver
 `_es_ki`, `_KI_DEFAULT`, `check_ki`.
 - `PEN` — el lexema `פֶּן` (H6435, gr. μήποτε) es una CONJUNCIÓN de
 APRENSIÓN / finalidad negativa (no sea que / para que no / quizá / tal vez / por
 si acaso) y **JAMÁS** la copulativa «y» (esa es el waw `ו`). Espejo exacto de `KI`:
 detectar la «y» es determinista, el valor exacto depende del contexto → se **suple
 el default «no sea que»** (lectura canónica) y el usuario ajusta a mano «quizá» /
 «para que no» donde el contexto lo pida (Gén 26:9 → «quizá», lectura del editor).
 Dos correcciones: (a) «y» **espuria en el prefijo** de un `פן` cuya grafía NO
 empieza por vav → se **quita**; (b) el propio lexema glosado «y» → «no sea que».
 Se identifica por Strong H6435 o por esqueleto `פן`. Alcance en Génesis: 6 tokens
 «y» corregidos (26:9→«quizá»; 31:24/31:31/38:11/38:23/42:4→«no sea que»). Ver
 `_es_pen`, `_PEN_DEFAULT`, `check_pen`.
  - `PRON` — además de (a) preposición+pronombre redundante ante sufijo y (b)
    presentativo `הִנֵּה`+sufijo (heme/helos aquí), (c) valida el **PRONOMBRE PERSONAL
    independiente** (`PRON.PERS`): el género y el número los fija la **morfología**,
    no el esqueleto. `הִוא` —grafía **pentateucal** escrita con vav, idéntica al
    masculino `הוּא`— es FEMENINO por morfología (`P3.F.SG`) → «ella», aunque parezca
    masculino (Gén 26:7/26:9 quedaron «él»). AUTOFIX estrecho: **solo 3ª persona** y
    solo si la glosa es EXACTAMENTE otro pronombre-sujeto de 3ª (él/ella/ellos/ellas)
    que CONTRADICE la morfología; nunca toca glosas contextuales (multi-palabra) ni
    1ª/2ª persona (convención editorial tú/usted, vosotros/ustedes). Ver `check_pron`.
  - `PREPRON` — **principio único**: el único render correcto de una PREP con
    sufijo pronominal es «`<preposición>` `<pronombre tónico>`». El **pronombre lo
    fija SIEMPRE la morfología** del sufijo (autoridad). La **preposición**: si la
    raíz ya es preposición válida se **respeta** (incluida tu elección a/para de
    ל); si no lo es, se deriva del esqueleto (אל→«a», ב→«en», מן→«de», על→«sobre»,
    אחר→«tras», עד→«hasta»; עם/את→«con» con fusión conmigo/contigo/consigo vía
    `HOMOGRAF`). Unifica y auto-corrige: «un mí»→«a mí», «su ellos»→«en ellos»,
    «a mí él»→«a él» (artefacto de constructo אֵלֵי/עֲלֵי), «su en»→«en ellos»,
    «para y»→«para él», «a»(+sufijo)→«a mí», «la ella»→«a ella». NO toca frases
    legítimas («por causa de») ni «a mí» 1ª sg sin sufijo. Con **ל de raíz basura**
    (un/su/y/artículo, sin preposición que respetar) ya **NO se deja en reporte**:
    se **suple «a» + pronombre** («un mí»→«a mí», «su naciones»→«a ella») —dejar
    «un mí» es un error puro—. La elección **a↔para** sigue siendo ESTILO tuyo:
    donde la raíz YA trae «para»/«a» válida se **respeta**; el default «a» solo
    entra cuando la raíz es basura, y puedes cambiarlo a «para» a mano. `HOMOGRAF`
    normaliza además `הִנֵּה` (H2009) glosado «aquí» → «he aquí»; el ADVERBIO
    `שָׁם`/`שָׁמָּה` glosado «nombre» (confusión con el SUSTANTIVO שֵׁם) → «allí»/«allá»
    —por MORFOLOGÍA ADV, aunque el Strong quede mal etiquetado (Gén 26:25)—; y la
    **fusión conmigo/contigo** cuando la raíz de עם/את YA es «con» (válida) pero el
    sufijo de 1ª/2ª sg no quedó fusionado y el render sale roto («te con»/«con ti»
    → «contigo», Gén 26:3/26:24). Solo 1ª/2ª sg (3ª/plural «con él/nosotros…» ya
    correctos NO se tocan; el prefijo «de» de מֵעִם se conserva). Y el **acusativo
    `אֵת` H853** (marcador de OBJETO DIRECTO, HOMÓGRAFO del `אֵת` H854 «con») con
    sufijo pronominal glosado «con» —confusión H853↔H854— se reconstruye
    «a + tónico» (tu uso dominante «a él/a ella/a ti/a ellos»; el pronombre lo fija
    la MORFOLOGÍA del sufijo, op `idiom`). El acusativo NUNCA es «con». `SINTAXIS`
    (reporte) de `לְ`-posesivo y de `אֵת` H853-«con» ahora **defiere**: solo reporta el
    residuo que PREPRON/HOMOGRAF NO autocorrigen (evita el doble listado de un error
    que `--apply` ya arregla). Ver `check_sintaxis`.
  - `CONCORD` incluye artículo (`el/la/los/las`) por **género** (solo cuando es
    seguro; excepciones tribu/maná/día/mano/agua… y género común escriba/levita…
    tabuladas; adverbios/gerundios/glosas rotas excluidos) y por **número**, que
    lo fija la **morfología hebrea** (no el heurístico español → evita «los
    eufrates»). Ver `_articulable`, `expected_article`, `GENERO_AMBIGUO`, `ADV_INVAR`.
    También concuerda un **demostrativo SUELTO** (este/esta/estos/estas, ese/esa…,
    aquel/aquella…): el **número** lo fija el **hebreo** (`.PL/.DU`→plural) y el
    **género**, el **sustantivo referente ESPAÑOL** (no el hebreo: `דּוֹר` masc →
    «generación» fem → «esta»). La **dirección** se elige por adyacencia: si el
    token de contenido inmediatamente ANTERIOR es un SUBS/ADJ, el demostrativo es
    **atributivo** y va tras su sustantivo («la tierra esta», `הָאָרֶץ הַזֹּאת`) → ese
    manda; si no (abre cláusula: «estas [son] años/hijos», `אֵלֶּה`), es
    **predicativo** → primer SUBS/ADJ hacia adelante, saltando cópula «son»/pronombre
    `הֵם`/artículo y cortando en verbo finito. Así «estas años»→«estos años»
    (25:16-17) pero «tierra esta» (fem) NO se toca aunque el siguiente token sea
    masc (15:18). Solo cuando el referente tiene género ES seguro; neutros
    (esto/eso/aquello) nunca se tocan. **Cubre además el demostrativo PENTATEUCAL
    `הַהוּא`/`הַהִוא`**, que el morfólogo etiqueta `PRON.PERS` (no `DEM`): «tierra …
    aquel» (`הִוא` fem, 2:12) → «aquella» por el referente ESPAÑOL «tierra». Como el
    género lo fija el sustantivo español, NO rompe «aquella noche»/«aquel año»/«aquel
    tiempo» (`לילה`/`שנה`/`עת` divergen de género con noche/año/tiempo). Para
    `PRON.PERS` solo corrige el uso **ATRIBUTIVO** (sustantivo común inmediatamente
    ANTES); excluye el **copulativo** «Luz … esta [es] Bet-El» (35:6: referente
    PROPIO → sin certeza). ⚠ Límite conocido del detector de referente: en
    predicativo puede tomar un sustantivo hacia adelante equivocado (31:43 «estas
    [hijas]… día») y no reconoce divergencia de NÚMERO esp. (33:8 «estos grupos», זֶה
    sg) → esos casos se REVISAN a mano. Ver `demo_referent_gender`, `DEMO_FAM`,
    `DEMO_TABLE`.
  - `CONSTRUCT` añade el nexo genitivo «… de» a un constructo (`.C`) SIN sufijo
    («hijos»→«hijos de», si tu ESTILO no lo contradice), y su **inverso**
    (`check_de_espuria`) **quita** una «de/del» final espuria de un nombre que YA
    lleva **sufijo posesivo proclítico** (su/mi/tu…): con posesivo el genitivo ya
    está dado, «su mujer de»→«su mujer» (25:21). Guarda dura: solo «NOMBRE de» (2
    palabras), cabeza NO preposicional (excluye לִפְנֵי «antes de», אַחֲרֵי
    «después de»… que piden «… de él/ellos»), y sufijo PRONOMINAL real (no
    paragógico/locativo). Multi-palabra queda a `LARGO` (reporte).
  - `TRANSLIT` auto-aplica **solo la mayúscula** de un nombre propio/gentilicio de
    una palabra («cananeos»→«Cananeos»). El resto de TRANSLIT (sin glosa, [EN:],
    hebreo, topónimo compuesto) sigue en reporte. Además **suple la transliteración
    de LEXEMAS COMUNES** listados en `fuentes/transliteraciones_lexemas.json` (tabla
`_LEXEMA_TRANSLIT`, hoy `goy` H1471 y `'Elohim` H430): el motor fonético
 `translit_nombres.py` solo cubre NPROP/GENT, así que un `SUBS` transliterado por
 decisión editorial (goy→Goy/Goyim) lo suple aquí. Estrecho y determinista: exige
 Strong + morfología, **solo FORMA ABSOLUTA** (el constructo `.C` —grafía «Goyei»—
 se deja a mano) y solo cuando la glosa actual es una **traducción conocida**
 (naciones/nación/gente/pueblo…); nunca pisa una translit ya puesta ni glosas fuera
 del set. **H430 (`'Elohim`, apelativo divino)**: mismo mecanismo, pero el set
 autorizado es **solo «dios»** (singular, Dios verdadero) → `'Elohim` (esa forma
 exacta, con apóstrofo del álef). Deja intacto el **plural pagano «dioses»** (dioses
 ajenos, 35:2/35:4) y el **constructo «dios de»** (grafía `'Elohei` / `'Elohim de`,
 decisión editorial → lo LISTA `MORPH_MISMATCH` con cap:verso, como `Goyei`).
 `MORPH_MISMATCH` **defiere** el absoluto al autofix de `TRANSLIT` (no lo doble-lista).
  - `CONTAGIO` — **MIXTO** (autofix VERIFICADO + reporte/listado). Caza la glosa
    copiada del vecino en el build: un stem de CONTENIDO (SUBS/ADJ/VERBO) cuya `es`
    es IDÉNTICA a la del stem de contenido ANTERIOR pero con **Strong Y raíz
    consonántica DISTINTOS** → la glosa se contagió (47:14 `שֶּׁבֶר` «grano» quedó
    «tierra», de `אֶרֶץ`; 36:6 `יֵּלֶךְ` «ir» quedó «tierra»; 41:12 `נַעַר` «joven»
    quedó «siervo»). Alta precisión: `_misma_raiz` pliega **formas finales** (ם≠מ…) y
    descarta la variante con afijo (שֵׁם/שְׁמִ, צֶלֶם/צַלְמ); `_CONTAGIO_STOP` excluye
    numerales/medidas/cuantificadores; y si la glosa actual es una **glosa
    conocida-correcta** del lexema en tu estadística (`glosa_conocida`) NO es
    contagio → se descarta (evita marcar «siervo» de `נַעַר` que sí usas).
    **AUTOFIX solo el subconjunto que el Strong/raíz VERIFICA** (`_contagio_finding`):
    la preferida POR-FORMA de una palabra de contenido NOMINAL (SUBS/ADJ), limpia, de
    UNA palabra, con `n≥6` y `pct≥50`, distinta del contagiado y ausente del token.
    **Verbos, multipalabra o sin lexema fiable → REPORTE con candidato** (el
    lexema/tiempo lo eliges tú). En capítulos ABIERTOS el `--apply` corrige el
    subconjunto verificado al pasar; en **capítulos CERRADOS el candado impide
    escribir y el hallazgo queda LISTADO con marcador `[CANDADO]`** (cap:verso) para
    que lo corrijas a mano. El marcador `[CANDADO]` se muestra en el reporte de
    **cualquier** categoría cuyo hallazgo caiga en un capítulo cerrado. Complementa a
    `RECORRIDO` (par inmediatamente adyacente). Ver `check_contagio`,
    `_contagio_finding`, `_misma_raiz`, `_raiz_norm`, `_CONTAGIO_STOP`.

- **REPORTE** (léxico/estilo): `MORPH_MISMATCH, MORFO, ESTILO, SINSTRONG, LARGO,
  RECORRIDO, SINTAXIS, VACIO, CORTO, DOBLE, MALFORM, RENDER, ENCLIT, YHWH`.
  - `MORPH_MISMATCH` detecta un SUBS/ADJ glosado con **verbo conjugado** aunque el
    verbo lleve un **clítico antepuesto** (se/me/te/nos/le/les): «se aproximó» sobre
    קֶרֶב (H7130, «interior») → reporte con sugerencia léxica (el sustantivo lo
    eliges tú). Ver `_LEAD_CLITICS`.
  - `MORFO` — además del tiempo (wayyiqtol≠futuro, yiqtol≠pretérito) marca el
    **participio pasado suelto CON objeto** sobre un verbo finito ACTIVO
    (QAL/PIEL/HIF): «los cegado», «te tocado» (Gén 26:15/26:29). El objeto enclítico
    prueba que es verbo finito transitivo → pretérito («los cegaron», «te tocamos»).
    Exigir el objeto evita falsos positivos de participios legítimos SIN objeto
    (perfecto «hemos hallado», adjetival «avanzado en días», «había bendecido»); los
    binyanim pasivos (NIF/PUAL/HOF/HIT) no se marcan. Reporte (no auto-fix:
    irregulares/causativo pueden cambiar el lexema). Ver `_PART_RE`, `_part_pret`.
    También (señal **d**) marca un **PRONOMBRE SUJETO explícito** en la glosa que
    contradice la **persona/número** de la morfología verbal: «él estuvo» (3ª sg) en
    un verbo `P3.PL` (Gén 26:8 `אָרְכוּ` «se alargaron», que quedó «después que él
    estuvo»); «yo recibí» en 3ª sg (43:23), «yo» en 3ª sg (27:25). Alta precisión: el
    pronombre sujeto es inequívoco (`él/ella/ellos/ellas/yo/nosotros/tú/vosotros`,
    con tilde para `tú`/`él`) y NO va tras preposición (excluye oblicuos «a él»). NO
    evalúa número por la sola terminación del verbo (colectivos/imperativos-en-`n`
    dan falsos positivos). Ver `_SUBJ_PRON_PN`.
  - `ENCLIT` — verbo NO-finito (INFINITIVO o IMPERATIVO) con el **pronombre objeto
    antepuesto** como proclítico; en español va ENCLÍTICO y unido. INF: unión
    mecánica y se sugiere («la llorar»→«llorarla»). IMPV: la unión desplaza el
    acento («me alimenta»→«aliméntame», Gén 25:30 הַלְעִיטֵנִי) → reporte con forma
    aproximada, sin auto-fix (la acentuación la fijas tú); el clítico «se» se deja
    a `REFLEX`. Ver `check_enclit`.

**Por qué el tiempo verbal solo es autofix en QAL** (`TIEMPOVERBAL`/`_tiempo_autofix`):
en Hifil/Piel el verbo suele ser **causativo** y cambia el lexema, no solo el
tiempo (`הִשְׁקָתָה` = «abrevó/dio de beber», no «bebió»; `הִשְׁבִּיעַ` = «hizo jurar»,
no «juró»). Convertir solo el tiempo metería un error de lexema → esos casos van a
REPORTE y el lexema correcto lo decide ESTILO.

**Regla de oro del diseño**: si un caso es ambiguo (p.ej. `אֲחֹת` = "hermana" vs.
"otra" en el modismo `אִשָּׁה אֶל־אֲחֹתָהּ`), va a REPORTE, no a autofix. Preferimos
no corregir antes que romper algo ya correcto.

## Candado (capítulos cerrados) — `candado.py`

Un capítulo CERRADO queda **bloqueado**: ningún proceso puede modificarlo. Solo
se abre/cierra con el botón del visor. Dos capas: (1) `esta_bloqueado()` que todo
escritor consulta y salta; (2) SELLOS + `reasegurar()` que restaura el capítulo
sellado antes de guardar, aunque un proceso "olvide" consultar el candado.

## Orden de trabajo por capítulo (Motor ES ≠ colores)

Secuencia **fija**. El texto personal **no** es requisito del Motor ES.

1. **Motor ES** (`revisar_es.py` / botón del visor): informe o `--apply` de
   AUTOFIX. El usuario revisa y corrige a mano lo que el motor no resuelve.
2. **Texto fluido personal** en `data_master/traduccion_personal_<libro>.json`
   (en el visor **sustituye** a la RVR1960), cuando el interlineal ya está
   revisado. Completo = `data[capítulo-1]` con todos los versos no vacíos.
3. **Colores al final** (rojo transliterar, azul globalizar, verde refuerzo).
   No son el Motor ES.

## Reglas para cualquier cambio

1. **No toques hebreo/griego/strongs/morfología/orden.** Solo el lado español.
2. **Respeta el candado**: nunca modifiques capítulos cerrados.
3. **Preserva el formato minificado** de `data_master/*.json` al escribir.
4. **Determinista → autofix; ambiguo → reporte.** Ante la duda, reporte.
5. **Añade tests** por cada refuerzo y corre la suite completa (0 fallos):
   `python tests/test_revisar_es.py`
6. Correr el motor: `python motores/scripts/revisar_es.py --book <libro>
   --chapter <n>` (dry-run) · añade `--apply` para corregir solo AUTOFIX (hace
   respaldo `.bak_...` y verifica la barrera de inmutabilidad). Respeta el
   candado; el texto personal no es requisito de esta corrida.

## Verificación de no-regresión

Antes de dar por bueno un cambio: (a) suite de tests en verde; (b) barrido del
corpus simulando los autofix sin renders malformados (None/inglés/palabras
repetidas/homógrafos residuales/vacíos). La barrera de inmutabilidad es la última
línea: si un cambio tocara algo indebido, el `--apply` aborta.
